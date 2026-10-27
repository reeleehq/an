"""Acquire a licensed music library with provenance (an#470): offline, every
network step behind its seam."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import subprocess

import pytest

from an.music_library import (
    ACQUIRED,
    FAILED,
    KEPT,
    MUSIC_LIBRARIES,
    WISHLIST,
    MusicLibraryError,
    MusicToolMissing,
    acquire,
    attribution_text,
    ffprobe_verify,
    kept_digests,
    titles_by_library,
    titles_from_json,
    tracks_table,
    wayback,
)


class Fetcher:
    """Serves bytes per URL; a URL it does not know is a 403."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise OSError(f"HTTP Error 403: Forbidden ({url})")
        return self.pages[url]


def _ok(data):
    """A verifier that accepts any non-empty file as 1.5 s of audio."""
    if not data:
        raise MusicLibraryError("empty")
    return 1.5


def _url(title):
    return MUSIC_LIBRARIES["incompetech"].track_url(title)


def _acquire(titles, fetch, **kw):
    kw.setdefault("out", {})
    return acquire(
        "incompetech", titles, fetch=fetch, verify=_ok, sleep=lambda s: None, **kw
    )


def test_titles_are_fetched_verified_and_recorded_with_their_licence():
    fetch, pauses, store = Fetcher({_url("A"): b"aa", _url("B"): b"bb"}), [], {}
    rows = acquire(
        "incompetech", ["A", "B"], out=store, fetch=fetch, verify=_ok,
        sleep=pauses.append, pause=2.0,
    )  # fmt: skip
    assert [(r.title, r.status, r.file) for r in rows] == [
        ("A", ACQUIRED, "A.mp3"),
        ("B", ACQUIRED, "B.mp3"),
    ]
    assert store == {"A.mp3": b"aa", "B.mp3": b"bb"}
    src = rows[0].source
    assert (src.license, src.author, src.url) == (
        "cc-by-4.0",
        "Kevin MacLeod",
        _url("A"),
    )
    assert src.sha256 == hashlib.sha256(b"aa").hexdigest()
    assert pauses == [2.0], "one pause: the second request to the same host"
    assert attribution_text(rows).startswith('"A" Kevin MacLeod (incompetech.com)\n')


def test_the_archive_copy_is_recorded_as_where_the_bytes_came_from():
    """The site refuses; the Internet Archive serves. The row says so: `url` is
    the archive's, `source_page_url` the library's, and no pause is spent
    switching hosts."""
    fetch, pauses = Fetcher({wayback(_url("A")): b"aa"}), []
    (row,) = acquire(
        "incompetech", ["A"], out={}, fetch=fetch, verify=_ok, sleep=pauses.append
    )
    assert row.status == ACQUIRED and pauses == []
    assert row.source.url == wayback(_url("A"))
    assert row.source.source_page_url == _url("A")
    assert row.source.model_extra["mirror"] == "wayback"


def test_a_lost_title_is_a_failed_row_and_the_batch_goes_on():
    store = {}
    rows = _acquire(["Gone", "A"], Fetcher({_url("A"): b"aa"}), out=store)
    assert [r.status for r in rows] == [FAILED, ACQUIRED]
    assert "direct: HTTP Error 403" in rows[0].error and "wayback:" in rows[0].error
    assert "Gone.mp3" not in store
    assert attribution_text(rows).count("Kevin MacLeod") == 1, "only what was acquired"


def test_a_file_that_is_not_audio_is_not_kept():
    fetch = Fetcher({_url("A"): b"", wayback(_url("A")): b""})
    store = {}
    (row,) = _acquire(["A"], fetch, out=store)
    assert row.status == FAILED and "empty" in row.error and store == {}


def test_a_store_that_refuses_a_file_fails_that_title_only():
    class Refusing(dict):
        def __setitem__(self, k, v):
            if k.startswith("Bad"):
                raise KeyError(f"cannot store {k}")
            super().__setitem__(k, v)

    store = Refusing()
    rows = _acquire(
        ["Bad", "Good"], Fetcher({_url("Bad"): b"b", _url("Good"): b"g"}), out=store
    )
    assert [r.status for r in rows] == [FAILED, ACQUIRED] and list(store) == [
        "Good.mp3"
    ]


def test_a_title_with_a_path_in_it_stays_in_the_folder(tmp_path):
    rows = acquire(
        "incompetech", ["AC/DC", "../../escape"], out=tmp_path / "o",
        fetch=Fetcher({_url("AC/DC"): b"a", _url("../../escape"): b"e"}),
        verify=_ok, sleep=lambda s: None,
    )  # fmt: skip
    assert [r.file for r in rows] == ["AC-DC.mp3", "-..-escape.mp3"]
    assert sorted(p.name for p in (tmp_path / "o").iterdir()) == [
        "-..-escape.mp3",
        "AC-DC.mp3",
    ]


def test_two_titles_that_share_a_file_are_refused():
    with pytest.raises(MusicLibraryError, match="both be saved"):
        _acquire(["Song", "SONG"], Fetcher({}))


def test_a_rerun_keeps_only_what_the_previous_table_recorded():
    fetch = Fetcher({_url("A"): b"aa", _url("B"): b"new"})
    store = {"A.mp3": b"aa", "B.mp3": b"someone else's file"}
    kept = {"A.mp3": hashlib.sha256(b"aa").hexdigest()}
    rows = _acquire(["A", "B"], fetch, out=store, kept=kept)
    assert [r.status for r in rows] == [KEPT, ACQUIRED]
    assert fetch.calls == [_url("B")], "A not fetched again"
    assert (
        rows[0].source.sha256 == kept["A.mp3"] and rows[0].source.license == "cc-by-4.0"
    )
    assert store["B.mp3"] == b"new", "an unrecorded file is not stamped with a licence"
    assert kept_digests(tracks_table(rows)) == {
        "A.mp3": kept["A.mp3"],
        "B.mp3": hashlib.sha256(b"new").hexdigest(),
    }


def test_a_paid_library_is_a_wishlist_and_downloads_nothing():
    fetch = Fetcher({})
    rows = acquire("epidemic_sound", ["Night Owl"], out={}, fetch=fetch, verify=_ok)
    assert [(r.status, r.source.license, r.file) for r in rows] == [
        (WISHLIST, None, None)
    ]
    assert fetch.calls == [] and attribution_text(rows) == ""


def test_metadata_rides_the_row_into_the_tracks_table():
    titles = {
        "A": {"credited_by": ["vid1", "vid2"], "feel": "Bright", "tags": {"k": 1}}
    }
    rows = _acquire(titles, Fetcher({_url("A"): b"aa"}))
    (row,) = csv.DictReader(io.StringIO(tracks_table(rows)))
    assert row["credited_by"] == "vid1; vid2" and row["feel"] == "Bright"
    assert row["tags"] == '{"k": 1}' and "extra" not in row
    assert row["license"] == "cc-by-4.0" and row["duration_s"] == "1.5"
    for clash in ({"license": "cc0-1.0"}, {"status": "acquired"}):
        with pytest.raises(MusicLibraryError, match="drop them"):
            _acquire({"A": clash}, Fetcher({}))


@pytest.mark.parametrize("bad", ["Sneaky Snitch", ["A", ""], {"A": "Bright"}])
def test_titles_of_the_wrong_shape_are_refused(bad):
    with pytest.raises(MusicLibraryError):
        _acquire(bad, Fetcher({}))


@pytest.mark.parametrize(
    "text", ['"Sneaky Snitch"', "3", '{"A": "Bright"}', "[1, 2]", "{nope"]
)
def test_a_titles_file_names_the_shapes_it_accepts(text):
    with pytest.raises(MusicLibraryError):
        titles_from_json(text)


def test_an_unknown_library_names_the_registered_ones():
    with pytest.raises(MusicLibraryError, match="incompetech"):
        acquire("audionautix", ["A"], out={})


def test_without_ffprobe_nothing_is_downloaded(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    fetch = Fetcher({_url("A"): b"aa"})
    with pytest.raises(MusicToolMissing, match="ffprobe"):
        acquire("incompetech", ["A"], out={}, fetch=fetch)
    assert fetch.calls == []


@pytest.mark.parametrize(
    "description, expected",
    [
        (  # the attribution form the licence asks for: what attribution_text writes
            MUSIC_LIBRARIES["incompetech"].attribution_for("Sneaky Snitch"),
            {"incompetech": ["Sneaky Snitch"]},
        ),
        (
            "Music by Kevin MacLeod (incompetech.com):\n0:00 Sneaky Snitch\n"
            "1:23 - Fluffing a Duck\nhttps://incompetech.com\n\nSubscribe!",
            {"incompetech": ["Sneaky Snitch", "Fluffing a Duck"]},
        ),
        (
            'Music: Kevin MacLeod\nSong: "Monkeys Spinning Monkeys"\n'
            "Licensed under Creative Commons: By Attribution 4.0",
            {"incompetech": ["Monkeys Spinning Monkeys"]},
        ),
        (
            "From Artlist:\n• Golden Hour\n\nThanks for watching",
            {"artlist": ["Golden Hour"]},
        ),
        ("No credits here.\nJust words.", {}),
    ],
)
def test_titles_by_library_reads_real_credit_formats(description, expected):
    assert titles_by_library(description) == expected


def _mp3(tmp_path):
    path = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", str(path)],
        check=True,
    )
    return path.read_bytes()


@pytest.mark.ffmpeg
def test_ffprobe_verify_reads_audio_and_refuses_an_error_page(tmp_path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not on PATH")
    assert ffprobe_verify(_mp3(tmp_path)) == pytest.approx(1.0, abs=0.1)
    for bad in (b"<html>403 Forbidden</html>", b""):
        with pytest.raises(MusicLibraryError):
            ffprobe_verify(bad)


@pytest.mark.ffmpeg
def test_the_command_writes_files_table_and_attribution_and_resumes(
    tmp_path, monkeypatch
):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not on PATH")
    import urllib.request

    from an.music_cli import add_library

    audio, opened = _mp3(tmp_path), []

    class Response(io.BytesIO):
        headers = {"Content-Type": "audio/mpeg"}

    def urlopen(req, timeout=None):
        opened.append(req.full_url)
        return Response(audio)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    titles = tmp_path / "usage.json"
    titles.write_text(json.dumps(["Sneaky Snitch"]), encoding="utf-8")
    out = tmp_path / "macleod"
    said = add_library("incompetech", titles_from=str(titles), out=str(out), pause=0.0)
    assert said.startswith("incompetech: 1 acquired")
    assert (out / "Sneaky Snitch.mp3").read_bytes() == audio
    assert "Sneaky Snitch" in (out / "tracks.csv").read_text(encoding="utf-8")
    assert "Creative Commons" in (out / "ATTRIBUTION.md").read_text(encoding="utf-8")
    again = add_library("incompetech", titles_from=str(titles), out=str(out), pause=0.0)
    assert again.startswith("incompetech: 1 kept") and len(opened) == 1
    with pytest.raises(SystemExit, match="registered"):
        add_library("audionautix", titles_from=str(titles), out=str(out))

    from an.cli_status import exit_code_of

    def refuse(req, timeout=None):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    titles.write_text(json.dumps(["Sneaky Snitch", "Gone"]), encoding="utf-8")
    said = add_library("incompetech", titles_from=str(titles), out=str(out), pause=0.0)
    assert exit_code_of(said) == 1 and "Gone: direct: HTTP Error 403" in said
