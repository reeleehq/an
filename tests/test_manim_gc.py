"""`an cache gc` collects the Manim stores — pictures, measurements, contact
sheets — the way it collects the shot cache (an#299).

Runs with ffmpeg and the fake ``render_check`` of ``test_manim_renderer`` (no
Manim): the stores, the keys and the collection are all real.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

import pytest

from an.adapters import manim_adapter as ma
from an.build.gc import cache_info, collect_garbage
from an.ir.schema import Shot
from an.stores import build_project_mall
from tests.test_manim_renderer import LINEAR, FakeRenderCheck, _project, _render

#: Collections run "a minute from now": what a test wrote a moment ago is past
#: the protection horizon.
_LATER = 60.0


class SheetPerSource(FakeRenderCheck):
    """The fake renderer, with a picture and a contact sheet that differ per
    scene file (a real one shows the scene), so old ones are entries of their own."""

    def __call__(self, file, scene=None, *, record_reads=False, **kw):
        report = super().__call__(file, scene, **kw)
        report.reads = [] if record_reads else None  # it reads nothing outside
        colour = hashlib.sha256(Path(file).read_bytes()).hexdigest()[:6]
        q = ma.QUALITY_PRESETS[kw["quality"]]
        for args in (
            [f"color=c=0x{colour}:s=96x54", "-frames:v", "1", report.contact_sheet],
            [f"color=c=0x{colour}:s={q.width}x{q.height}:r={q.fps}:d={self.seconds}",
             "-pix_fmt", "yuv420p", report.video],
        ):  # fmt: skip
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", *args], check=True
            )
        return report


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(ma, "manim_version", lambda: "0.0.0-fake")
    check = SheetPerSource(seconds=1.0)
    monkeypatch.setattr(ma, "_manimkit_render_check", lambda: check)
    return check


def _stores(root) -> dict[str, set[str]]:
    mall = build_project_mall(root)
    return {name: set(mall[name]) for name in ("measurements", "pictures", "contact_sheets")}


def _named(root) -> dict[str, set[str]]:
    """What the CURRENT measurement records name."""
    mall = build_project_mall(root)
    records = [json.loads(mall["measurements"][k]) for k in mall["measurements"]]
    return {
        "pictures": {r["picture"] for r in records},
        "contact_sheets": {r["contact_sheet"] for r in records if r.get("contact_sheet")},
    }


def _edited_three_times(tmp_path):
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    sources = build_project_mall(root)["sources"]
    for version in (b"", b"# v2\n", b"# v3\n"):
        sources["a"] = LINEAR + version
        _render(root)
    return root


@pytest.mark.ffmpeg
def test_gc_collects_what_old_edits_of_a_manim_source_left_in_its_stores(tmp_path, fake):
    root = _edited_three_times(tmp_path)
    before = _stores(root)
    assert {k: len(v) for k, v in before.items()} == {
        "measurements": 3, "pictures": 3, "contact_sheets": 3,
    }  # fmt: skip
    assert _stores(root) == before and collect_garbage(
        root, dry_run=True, now=time.time() + _LATER
    ).deleted_derived  # a dry run reports …
    assert _stores(root) == before  # … and deletes nothing
    collect_garbage(root, now=time.time() + _LATER)
    after = _stores(root)
    assert {k: len(v) for k, v in after.items()} == {
        "measurements": 1, "pictures": 1, "contact_sheets": 1,
    }  # fmt: skip
    assert after["pictures"] == _named(root)["pictures"]
    assert after["contact_sheets"] == _named(root)["contact_sheets"]
    calls = fake.calls
    _render(root)
    assert fake.calls == calls  # warm: the current picture is still there


@pytest.mark.ffmpeg
def test_cache_info_reports_the_manim_stores(tmp_path, fake):
    root = _edited_three_times(tmp_path)
    info = cache_info(root, now=time.time() + _LATER)
    text = info.summary()
    for name in ("pictures", "measurements", "contact_sheets"):
        assert name in text
    assert info.derived["pictures"].entries == 3
    assert info.derived["pictures"].unreachable_entries == 2


@pytest.mark.ffmpeg
def test_what_a_recorded_render_used_is_kept_until_its_root_expires(tmp_path, fake):
    """A render under other knobs (here 24 fps) recorded a root naming its shot;
    that shot's provenance names its picture, which the CURRENT scene under
    those knobs no longer reads after an edit — kept until the root expires."""
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    sources = build_project_mall(root)["sources"]
    _render(root, fps=24)
    first = _named(root)["pictures"]
    sources["a"] = LINEAR + b"# v2\n"
    _render(root)
    _render(root, fps=24)  # replaces the 24 fps root: v1 is now history
    v2 = _named(root)["pictures"] - first
    sources["a"] = LINEAR + b"# v3\n"
    _render(root)  # the 24 fps root still names its v2 shot
    collect_garbage(root, now=time.time() + _LATER)
    left = _stores(root)["pictures"]
    assert not first & left  # v1: nothing names it
    assert len(v2) == 1 and v2 <= left and len(left) == 2  # v2 (the root's) and v3
    collect_garbage(root, now=time.time() + _LATER + 10, max_age=1.0)
    assert not v2 & _stores(root)["pictures"]  # the root expired: v2 goes
    assert len(_stores(root)["pictures"]) == 1


@pytest.mark.ffmpeg
def test_a_record_written_during_the_collection_keeps_what_it_names(tmp_path, fake):
    """A render racing the collection: its new record is protected, and so is
    the (older) picture it names, however old that file is."""
    import os

    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    mall = build_project_mall(root)
    _render(root)
    (first,) = list(mall["measurements"])
    picture = json.loads(mall["measurements"][first])["picture"]
    mall["sources"]["a"] = LINEAR + b"# v2\n"
    _render(root)
    later = time.time() + 2 * _LATER
    os.utime(mall["measurements"].path_of(first), (later, later))  # "just written"
    collect_garbage(root, now=time.time() + _LATER)
    assert first in set(mall["measurements"])
    assert picture in set(mall["pictures"])  # an hour-old file, named by a fresh record


@pytest.mark.ffmpeg
def test_max_age_keeps_young_manim_history(tmp_path, fake):
    root = _edited_three_times(tmp_path)
    report = collect_garbage(root, now=time.time() + _LATER, max_age=3600.0)
    assert report.deleted_derived == {} and len(_stores(root)["pictures"]) == 3


@pytest.mark.ffmpeg
def test_the_scene_alone_keeps_its_picture_when_the_shot_cache_is_gone(tmp_path, fake):
    """Reachability computed from the CURRENT scene, not only from what the
    shot cache's records name: with every shot entry gone, the picture the
    scene reads stays, and the next render runs no Manim."""
    import shutil

    root = _edited_three_times(tmp_path)
    shutil.rmtree(Path(root) / "artifacts" / "shot_cache")
    collect_garbage(root, now=time.time() + _LATER, force=True)
    assert len(_stores(root)["pictures"]) == 1
    calls = fake.calls
    _render(root)
    assert fake.calls == calls


@pytest.mark.ffmpeg
def test_max_age_keeps_manim_history_no_shot_entry_names(tmp_path, fake):
    """Cold renders (`incremental=False`) write pictures no shot entry names;
    `--max-age` still keeps the young ones, and no cap deletes them."""
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    sources = build_project_mall(root)["sources"]
    _render(root)
    sources["a"] = LINEAR + b"# v2\n"
    _render(root, incremental=False)
    sources["a"] = LINEAR + b"# v3\n"
    _render(root)
    assert len(_stores(root)["pictures"]) == 3
    collect_garbage(root, now=time.time() + _LATER, max_age=3600.0)
    assert len(_stores(root)["pictures"]) == 3  # all young: kept
    collect_garbage(root, now=time.time() + _LATER)
    assert len(_stores(root)["pictures"]) == 1


# -----------------------------------------------------------------------------
# The adversarial review's cases (an#299)
# -----------------------------------------------------------------------------


def _files(root, store: str) -> dict[str, int]:
    folder = Path(root) / "artifacts" / store
    return {p.name: p.stat().st_size for p in folder.iterdir() if p.is_file()}


def _total(root) -> int:
    base = Path(root) / "artifacts"
    return sum(
        p.stat().st_size
        for name in ("shot_cache", "measurements", "pictures", "contact_sheets")
        for p in (base / name).rglob("*")
        if p.is_file()
    )


@pytest.mark.ffmpeg
def test_max_size_counts_a_record_with_the_picture_it_names(tmp_path, fake):
    """A record (a few hundred bytes) that fits must not drag in its picture
    uncounted: the cap keeps a record with what it names, or neither."""
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    sources = build_project_mall(root)["sources"]
    _render(root, incremental=False)  # v1: no shot entry names it
    stores = ("measurements", "pictures", "contact_sheets")
    v1 = {s: _files(root, s) for s in stores}
    sources["a"] = LINEAR + b"# v2\n"
    _render(root)
    blobs = sum(p.stat().st_size for p in (Path(root) / "artifacts/shot_cache/blobs").iterdir())
    current = sum(n for s in stores for k, n in _files(root, s).items() if k not in v1[s])
    # Room for v1's record and sheet, not for its picture.
    cap = blobs + current + sum(v1["measurements"].values()) + sum(v1["contact_sheets"].values())
    roomy = collect_garbage(  # room for the whole unit: v1 is kept, record and picture
        root, dry_run=True, now=time.time() + _LATER, max_size=cap + sum(v1["pictures"].values())
    )
    assert roomy.deleted_derived == {}
    collect_garbage(root, now=time.time() + _LATER, max_size=cap)
    assert not set(v1["pictures"]) & set(_files(root, "pictures"))
    assert not set(v1["measurements"]) & set(_files(root, "measurements"))
    collect_garbage(root, now=time.time() + _LATER, max_size=cap + 10**6)  # nothing left to keep
    assert len(_files(root, "pictures")) == 1


@pytest.mark.ffmpeg
def test_a_record_written_after_the_listing_keeps_the_old_picture_it_names(
    tmp_path, fake, monkeypatch
):
    """A render racing the collection writes a record (after gc listed the
    stores) naming a picture that already existed: that picture stays."""
    import an.build.gc as gc

    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    mall = build_project_mall(root)
    _render(root)
    (v1,) = list(mall["measurements"])
    picture = json.loads(mall["measurements"][v1])["picture"]
    mall["sources"]["a"] = LINEAR + b"# v2\n"
    _render(root)
    listed = gc._derived_inventory

    def listing_then_a_render_writes(m, stores):
        out = listed(m, stores)
        m["measurements"]["f" * 64] = json.dumps({"picture": picture}).encode()
        return out

    monkeypatch.setattr(gc, "_derived_inventory", listing_then_a_render_writes)
    collect_garbage(root, now=time.time() + _LATER)
    assert picture in set(mall["pictures"])


@pytest.mark.ffmpeg
def test_reusing_a_stored_picture_refreshes_its_age(tmp_path, fake):
    """`_raw` finds the picture already stored (same bytes) and touches it, so
    a collection's last-moment check sees it as just written."""
    import os

    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    mall = build_project_mall(root)
    _render(root)
    (name,) = list(mall["pictures"])
    path = mall["pictures"].path_of(name)
    os.utime(path, (1_000_000, 1_000_000))
    _render(root, incremental=False)  # Manim again: the same bytes
    assert path.stat().st_mtime > 1_000_000


@pytest.mark.ffmpeg
def test_an_unreadable_record_stops_what_records_name_from_being_deleted(tmp_path, fake):
    root = _edited_three_times(tmp_path)
    mall = build_project_mall(root)
    import os

    mall["measurements"]["e" * 64] = b'{"picture": "half wri'  # a render, mid-write
    later = time.time() + 2 * _LATER
    os.utime(mall["measurements"].path_of("e" * 64), (later, later))
    report = collect_garbage(root, now=time.time() + _LATER)
    assert len(set(mall["pictures"])) == 3
    assert any("unreadable" in f for f in report.failed)


def test_a_store_has_one_owner_and_a_declaration_is_complete():
    from an.build.derived import (
        DerivedStores,
        DerivedStoresRegistrationError,
        register_derived_stores,
        registered_derived_stores,
    )

    assert "manim" in registered_derived_stores()
    ok = dict(entries=lambda r, s, c: set(), provenance=lambda p: {}, names=lambda d: {})
    with pytest.raises(DerivedStoresRegistrationError, match="belong to renderer 'manim'"):
        register_derived_stores(
            "another", DerivedStores(record_store="measurements", named_stores=(), **ok)
        )
    with pytest.raises(DerivedStoresRegistrationError, match="callable"):
        DerivedStores(record_store="r", named_stores=(), **{**ok, "names": None})
