"""Acquire a licensed music library with provenance (an#470), through an's
bridge to foley (an#656): offline, every network step behind its seam.

The library is foley's (``foley.sources.music_library``); what these pin is the
behaviour an relies on, read through :func:`an.music_library.asset_source`
where a row's provenance is an's ``AssetSource``."""

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
    asset_source,
    attribution_text,
    kept_digests,
    probe_verify,
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
        sleep=pauses.append, clock=lambda: 0.0, pause=2.0,
    )  # fmt: skip
    assert [(r.title, r.status, r.file) for r in rows] == [
        ("A", ACQUIRED, "A.mp3"),
        ("B", ACQUIRED, "B.mp3"),
    ]
    assert store == {"A.mp3": b"aa", "B.mp3": b"bb"}
    src = asset_source(rows[0])
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
    src = asset_source(row)
    assert src.url == wayback(_url("A"))
    assert src.source_page_url == _url("A")
    assert src.model_extra["mirror"] == "wayback"
    assert src.model_extra["rights_verified"] is True


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
    src = asset_source(rows[0])
    assert src.sha256 == kept["A.mp3"] and src.license == "cc-by-4.0"
    assert store["B.mp3"] == b"new", "an unrecorded file is not stamped with a licence"
    assert kept_digests(tracks_table(rows)) == {
        "A.mp3": kept["A.mp3"],
        "B.mp3": hashlib.sha256(b"new").hexdigest(),
    }


def test_a_paid_library_is_a_wishlist_and_downloads_nothing():
    fetch = Fetcher({})
    rows = acquire("epidemic_sound", ["Night Owl"], out={}, fetch=fetch, verify=_ok)
    assert [(r.status, asset_source(r).license, r.file) for r in rows] == [
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
    # The table is foley's, in foley's licence ids; the AssetSource is an's.
    assert row["license"] == "CC-BY-4.0" and row["duration_s"] == "1.5"
    assert asset_source(rows[0]).license == "cc-by-4.0"
    assert asset_source(row).model_extra["feel"] == "Bright", "a table row bridges too"
    flags = ("rights_verified", "commercial_ok")
    assert [asset_source(row).model_extra[k] for k in flags] == [
        asset_source(rows[0]).model_extra[k] for k in flags
    ], "a licence flag read back from CSV is a boolean, as the track's is"
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
    from foley.sources.music_library import verify

    monkeypatch.setattr(verify, "probe_available", lambda: False)
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
def test_probe_verify_reads_audio_and_refuses_an_error_page(tmp_path):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not on PATH")
    assert probe_verify(_mp3(tmp_path)) == pytest.approx(1.0, abs=0.1)
    for bad in (b"<html>403 Forbidden</html>", b""):
        with pytest.raises(MusicLibraryError):
            probe_verify(bad)


@pytest.mark.ffmpeg
def test_the_command_writes_files_table_and_attribution_and_resumes(
    tmp_path, monkeypatch
):
    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not on PATH")
    from foley.sources.music_library import fetch

    from an.music_cli import add_library

    audio, opened = _mp3(tmp_path), []

    class Response:
        def __init__(self, status_code, content=b"", kind="audio/mpeg"):
            self.status_code, self.content = status_code, content
            self.headers = {"Content-Type": kind}

    def serve(method, url, **kw):  # foley's transport: (method, url) -> response
        opened.append(url)
        return Response(200, audio)

    monkeypatch.setattr(fetch, "requests_transport", serve)
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

    def refuse(method, url, **kw):
        return Response(403, b"Forbidden", kind="text/plain")

    monkeypatch.setattr(fetch, "requests_transport", refuse)
    titles.write_text(json.dumps(["Sneaky Snitch", "Gone"]), encoding="utf-8")
    said = add_library("incompetech", titles_from=str(titles), out=str(out), pause=0.0)
    assert exit_code_of(said) == 1 and "Gone: direct: HTTP 403" in said


def test_a_title_its_licence_refuses_makes_the_command_exit_1(tmp_path, monkeypatch):
    """A refused title is a row with why, and the command says so with exit 1, as
    for a failed one (an#656 review)."""
    import an.music_library
    from foley.sources.music_library import REFUSED, AcquiredTrack, track_license

    from an.cli_status import exit_code_of
    from an.music_cli import add_library

    lib = MUSIC_LIBRARIES["incompetech"]

    def refuse_all(library, titles, **kw):
        why = "refused for the intended use: not for this use"
        return [
            AcquiredTrack(t, library, REFUSED, track_license(lib, t), error=why)
            for t in titles
        ]

    monkeypatch.setattr(an.music_library, "acquire", refuse_all)
    titles = tmp_path / "usage.json"
    titles.write_text(json.dumps(["Sneaky Snitch"]), encoding="utf-8")
    said = add_library("incompetech", titles_from=str(titles), out=str(tmp_path / "o"))
    assert exit_code_of(said) == 1
    assert "1 refused" in said and "Sneaky Snitch: refused for the intended use" in said
    assert "refused" in (tmp_path / "o" / "tracks.csv").read_text(encoding="utf-8")


@pytest.mark.ffmpeg
def test_an_acquired_track_goes_into_the_sounds_store_without_a_fetch(tmp_path):
    """an#623: the verified file a row names is cut into the project's sounds
    store with the row as its provenance (library, licence, attribution) and
    the cut; nothing is fetched. A wishlist row, a missing file and bytes that
    no longer match the row's digest are refused."""
    from an.music_library import add_track_to_sounds
    from an.stores.sounds import SoundsStore

    audio = _mp3(tmp_path)
    files: dict = {}
    # as `an music use` reads it: a tracks.csv line
    (row,) = csv.DictReader(io.StringIO(tracks_table(_acquire(
        ["Sneaky Snitch"], Fetcher({_url("Sneaky Snitch"): audio}), out=files
    ))))  # fmt: skip
    sounds = SoundsStore(tmp_path / "sounds")
    asset = add_track_to_sounds(
        sounds, "theme", row, files, start=0.2, duration=0.5, fade_out=0.1
    )
    assert asset.duration == pytest.approx(0.5, abs=0.02)
    src = asset.source
    assert (src.provider, src.id, src.license) == ("incompetech", "Sneaky Snitch", "cc-by-4.0")
    # the library file the licence covers; `sha256` would be the stored bytes'
    assert src.model_extra["file_sha256"] == hashlib.sha256(audio).hexdigest()
    assert src.sha256 is None and src.cacheable is True  # from the registry
    assert src.model_extra["cut"] == {"start": 0.2, "end": 0.7, "fade_out": 0.1}
    assert "theme" in sounds

    with pytest.raises(MusicLibraryError, match="holds no file"):
        add_track_to_sounds(sounds, "x", {**row, "status": WISHLIST}, files)
    with pytest.raises(MusicLibraryError, match="holds no file"):
        add_track_to_sounds(sounds, "x", {**row, "file": ""}, files)
    with pytest.raises(MusicLibraryError, match="not in the library folder"):
        add_track_to_sounds(sounds, "x", row, {})
    with pytest.raises(MusicLibraryError, match="does not match the sha256"):
        add_track_to_sounds(sounds, "x", row, {row["file"]: audio + b"x"})


@pytest.mark.ffmpeg
def test_the_use_command_reads_the_tracks_table_and_names_what_it_lists(tmp_path):
    """`an music use <project> <out> <title> <key>` (an#623)."""
    from an.music_cli import TRACKS_TABLE, use
    from an.project import init, load

    audio = _mp3(tmp_path)
    out = tmp_path / "macleod"
    files = {}
    rows = _acquire(["Sneaky Snitch"], Fetcher({_url("Sneaky Snitch"): audio}), out=files)
    out.mkdir()
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / TRACKS_TABLE).write_text(tracks_table(rows), encoding="utf-8")
    project = init(tmp_path / "film")
    said = use(str(project), "theme", str(out), "Sneaky Snitch", duration=0.5)
    assert said.startswith("sounds/theme: 0.50 s of 'Sneaky Snitch' (incompetech) [cc-by-4.0]")
    assert "theme" in load(project).mall["sounds"]
    with pytest.raises(SystemExit, match="no track 'Gone'.*Sneaky Snitch"):
        use(str(project), "x", str(out), "Gone")
    with pytest.raises(SystemExit, match="no tracks.csv"):
        use(str(project), "x", str(tmp_path / "empty"), "Sneaky Snitch")
    with pytest.raises(SystemExit, match="an music use: .*"):  # a cut past the end
        use(str(project), "x", str(out), "Sneaky Snitch", start=60.0)


def test_a_tracks_table_row_cannot_grant_rights_and_reads_with_a_bom():
    """an#623 review: a row's licence is rebuilt from the library's registry,
    whatever its `license` cell says, and a column named like a source field
    (`cost_usd`, `cacheable`, `id`) never sets that field. A table an editor
    saved with a byte-order mark reads the same."""
    from an.music_library import track_from_row, track_row

    (track,) = _acquire(["Sneaky Snitch"], Fetcher({_url("Sneaky Snitch"): b"x"}))
    row = {**track.row(), "license": "CC0-1.0", "cost_usd": "0", "cacheable": "False",
           "id": "spoofed", "feel": "sneaky"}  # fmt: skip
    src = asset_source(track_from_row(row))
    assert (src.id, src.license, src.cost_usd, src.cacheable) == (
        "Sneaky Snitch", "cc-by-4.0", None, True,
    )  # fmt: skip
    assert src.model_extra["feel"] == "sneaky"
    text = "\ufeff" + tracks_table([track]).replace("\n", "\r\n")
    assert track_row(text, "Sneaky Snitch")["file"] == track.file
    with pytest.raises(MusicLibraryError, match="no library 'audionautix'"):
        track_from_row({**row, "library": "audionautix"})
