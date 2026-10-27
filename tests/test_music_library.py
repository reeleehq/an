"""Acquire a licensed music library with provenance (an#470): offline, every
network step behind its seam."""

from __future__ import annotations

import csv
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
    acquire,
    attribution_text,
    direct,
    ffprobe_verify,
    wayback,
    write_tracks_table,
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


def _ok(path):
    """A verifier that accepts any non-empty file as 1.5 s of audio."""
    if not path.read_bytes():
        raise MusicLibraryError("empty")
    return 1.5


INCOMPETECH = MUSIC_LIBRARIES["incompetech"]


def _url(title):
    return INCOMPETECH.track_url(title)


def test_titles_are_fetched_verified_and_recorded_with_their_licence(tmp_path):
    fetch = Fetcher({_url("A"): b"aa", _url("B"): b"bb"})
    pauses = []
    rows = acquire(
        "incompetech", ["A", "B"], out=tmp_path, fetch=fetch, verify=_ok,
        sleep=pauses.append, pause=2.0,
    )  # fmt: skip
    assert [(r.title, r.status, r.file) for r in rows] == [
        ("A", ACQUIRED, "A.mp3"),
        ("B", ACQUIRED, "B.mp3"),
    ]
    assert (tmp_path / "B.mp3").read_bytes() == b"bb"
    src = rows[0].source
    assert (src.license, src.author, src.url) == (
        "cc-by-4.0",
        "Kevin MacLeod",
        _url("A"),
    )
    assert src.sha256 == __import__("hashlib").sha256(b"aa").hexdigest()
    assert pauses == [2.0], "one pause, between the two downloads"
    assert attribution_text(rows).startswith('"A" Kevin MacLeod (incompetech.com)\n')


def test_a_refused_site_falls_back_to_the_archive_and_a_lost_title_is_a_failed_row(
    tmp_path,
):
    fetch = Fetcher({wayback(_url("A")): b"aa"})
    rows = acquire(
        "incompetech",
        ["A", "Gone"],
        out=tmp_path,
        fetch=fetch,
        verify=_ok,
        sleep=lambda s: None,
    )
    assert [r.status for r in rows] == [ACQUIRED, FAILED]
    assert fetch.calls[:2] == [_url("A"), wayback(_url("A"))]
    assert "direct: HTTP Error 403" in rows[1].error and "wayback:" in rows[1].error
    assert not (tmp_path / "Gone.mp3").exists(), "nothing half-written is left"
    assert attribution_text(rows).count("Kevin MacLeod") == 1, "only what was acquired"


def test_a_file_that_is_not_audio_is_not_kept(tmp_path):
    fetch = Fetcher({_url("A"): b"", wayback(_url("A")): b""})
    (row,) = acquire(
        "incompetech",
        ["A"],
        out=tmp_path,
        fetch=fetch,
        verify=_ok,
        sleep=lambda s: None,
    )
    assert row.status == FAILED and "empty" in row.error


def test_a_rerun_keeps_what_is_there_and_fetches_nothing(tmp_path):
    (tmp_path / "A.mp3").write_bytes(b"aa")
    fetch = Fetcher({})
    (row,) = acquire("incompetech", ["A"], out=tmp_path, fetch=fetch, verify=_ok)
    assert row.status == KEPT and fetch.calls == [] and row.source.sha256


def test_a_paid_library_is_a_wishlist_and_downloads_nothing(tmp_path):
    fetch = Fetcher({})
    rows = acquire(
        "epidemic_sound", ["Night Owl"], out=tmp_path, fetch=fetch, verify=_ok
    )
    assert [(r.status, r.source.license, r.file) for r in rows] == [
        (WISHLIST, None, None)
    ]
    assert fetch.calls == [] and attribution_text(rows) == ""


def test_metadata_rides_the_row_into_the_tracks_table(tmp_path):
    fetch = Fetcher({_url("A"): b"aa"})
    titles = {"A": {"credited_by": ["vid1", "vid2"], "feel": "Bright"}}
    rows = acquire("incompetech", titles, out=tmp_path, fetch=fetch, verify=_ok)
    table = write_tracks_table(rows, tmp_path / "tracks.csv")
    (row,) = csv.DictReader(table.open(encoding="utf-8"))
    assert row["credited_by"] == "vid1; vid2" and row["feel"] == "Bright"
    assert row["license"] == "cc-by-4.0" and row["duration_s"] == "1.5"
    with pytest.raises(MusicLibraryError, match="license"):
        acquire(
            "incompetech",
            {"A": {"license": "cc0-1.0"}},
            out=tmp_path,
            fetch=fetch,
            verify=_ok,
        )


def test_an_unknown_library_names_the_registered_ones(tmp_path):
    with pytest.raises(MusicLibraryError, match="incompetech"):
        acquire("audionautix", ["A"], out=tmp_path)


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
    good = tmp_path / "good.mp3"
    good.write_bytes(_mp3(tmp_path))
    assert ffprobe_verify(good) == pytest.approx(1.0, abs=0.1)
    page = tmp_path / "page.mp3"
    page.write_bytes(b"<html>403 Forbidden</html>")
    with pytest.raises(MusicLibraryError):
        ffprobe_verify(page)


@pytest.mark.ffmpeg
def test_the_command_writes_files_table_and_attribution(tmp_path, monkeypatch):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not on PATH")
    import io
    import urllib.request

    from an.music_cli import add_library

    audio = _mp3(tmp_path)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda req, timeout=None: io.BytesIO(audio)
    )
    titles = tmp_path / "usage.json"
    titles.write_text(json.dumps(["Sneaky Snitch"]), encoding="utf-8")
    out = tmp_path / "macleod"
    said = add_library("incompetech", str(titles), str(out), pause=0.0)
    assert said.startswith("incompetech: 1 acquired")
    assert (out / "Sneaky Snitch.mp3").exists()
    assert "Sneaky Snitch" in (out / "tracks.csv").read_text(encoding="utf-8")
    assert "Creative Commons" in (out / "ATTRIBUTION.md").read_text(encoding="utf-8")

