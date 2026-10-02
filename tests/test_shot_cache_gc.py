"""Shot-cache garbage collection (an#274) and assembled films that reuse their
shots without whole-frame entries (an#260).

The GC tests run with NO browser and NO ffmpeg: the cut-out keyer is real, the
render is the `test_shot_cache` stand-in, and the environment is stated rather
than probed — so "kept" and "deleted" are statements about reachability. The
assembled-film tests run the real per-shot mux and the real film assembly
(``ffmpeg``-marked) under a stand-in that paints each shot one colour.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
from pathlib import Path

import numpy as np
import pytest

from an.assemble import (
    MIN_SEGMENT_FRAMES,
    ShotWindow,
    film_timeline,
    picture_segments,
    shot_windows,
)
from an.build import ShotCache
from an.build.gc import (
    CacheGcError,
    cache_info,
    collect_garbage,
    inventory,
    parse_age,
    parse_size,
)
from an.build.shot_cache import FRAMES_SUFFIX, PARTS_INFIX, ROOT_PREFIX
from an.ir.schema import Meta, Resolution, SceneIR, Shot, SoundCue, Transition
from an.project import load
from tests.test_voice_provider import eleven  # noqa: F401 — the fixture, by name
from tests.test_shot_cache import (  # noqa: F401 — the fixture, by name
    _ENV,
    _FPS,
    _env,
    _project,
    _render,
    _set_shots,
    _shot,
    fake_render,
)

#: Collections run "a minute from now", so entries the test wrote a moment ago
#: are past the protection horizon (which spares what was written in the last
#: `CLOCK_SLACK_S` seconds — a render's own writes).
_LATER = 60.0


def _gc(root, **kw):
    kw.setdefault("now", time.time() + _LATER)
    return collect_garbage(root, engine=ShotCache(environment=_env()), **kw)


def _ids(root) -> set[str]:
    return set(load(root).mall["shot_cache"])


def _keys(report) -> list[str]:
    return [o.key for o in report.outcomes]


# -----------------------------------------------------------------------------
# What is kept
# -----------------------------------------------------------------------------


def test_gc_deletes_what_an_edit_left_behind_and_nothing_the_scene_reads(
    tmp_path, fake_render
):
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    first, _ = _render(root, fake_render)
    _set_shots(root, _shot("a", 10.0), _shot("b", 25.0))  # edit b
    second, _ = _render(root, fake_render)
    old_b, = set(_keys(first)) - set(_keys(second))

    report = _gc(root)
    assert [e.id for e in report.deleted] == [old_b]
    assert old_b not in _ids(root)
    # Nothing the current scene reads is gone: a warm render renders nothing.
    third, rendered = _render(root, fake_render)
    assert rendered == [] and third.reused == ["a", "b"]


def test_a_dry_run_reports_the_same_and_deletes_nothing(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    before = _ids(root)
    dry = _gc(root, dry_run=True)
    assert dry.deleted and dry.freed_bytes > 0 and _ids(root) == before
    real = _gc(root)
    assert [e.id for e in real.deleted] == [e.id for e in dry.deleted]
    assert real.freed_bytes == dry.freed_bytes


def test_the_current_scene_is_kept_even_when_no_render_recorded_it(tmp_path, fake_render):
    """Revert an edit without rendering: the reverted-to entry is reachable
    from the current scene although the latest render's root names the edit."""
    root = _project(tmp_path, _shot("a", 10.0))
    v1, _ = _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    v2, _ = _render(root, fake_render)
    _set_shots(root, _shot("a", 10.0))  # back to v1, not rendered

    _gc(root)
    assert set(_keys(v1)) <= _ids(root)  # the current scene's
    assert set(_keys(v2)) <= _ids(root)  # the latest render's (its root)
    _, rendered = _render(root, fake_render)
    assert rendered == []


def _drop_roots(root) -> None:
    """Make the cache look as if no render had recorded a root (a pre-an#274
    cache). Unlinked directly: `dol.Files` deletion would use the OS trash."""
    for f in (Path(root) / "artifacts/shot_cache/catalog").glob(f"{ROOT_PREFIX}*.json"):
        f.unlink()


def test_a_cache_with_no_root_is_refused_unless_forced(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    report, _ = _render(root, fake_render)
    _drop_roots(root)
    before = _ids(root)
    with pytest.raises(CacheGcError, match="no render of this project"):
        _gc(root)
    assert _ids(root) == before
    assert _gc(root, force=True).deleted == []  # forced: the current scene stays
    assert set(_keys(report)) <= _ids(root)


def _edit_md(root, old: str, new: str) -> None:
    """Edit scene.md as a person would, so the next load re-syncs the IR from it."""
    md = Path(root) / "scene.md"
    text = md.read_text(encoding="utf-8")
    assert old in text, text[:400]
    md.write_text(text.replace(old, new, 1), encoding="utf-8")
    later = time.time() + 5
    os.utime(md, (later, later))


def _speaking(root):
    from an.ir.schema import Dialogue

    shot = _shot("a", 10.0)
    shot.dialogue = [Dialogue(speaker="x", text="hello there", start=0.1)]
    _set_shots(root, shot, _shot("b", 20.0))


@pytest.mark.genre("cutout_animation")
def test_an_md_edit_that_drops_the_audio_stamps_keeps_what_the_next_render_reuses(
    tmp_path, fake_render
):
    """an#280 review G1: re-syncing from scene.md clears every dialogue stamp;
    the next render re-stamps the same audio from the stores and reuses its
    shots, so the collector must key them the same way — even with no root."""
    root = _project(tmp_path, _shot("a", 10.0))
    _speaking(root)
    report, _ = _render(root, fake_render)
    _drop_roots(root)
    title = load(root).scene.meta.title or ""
    _edit_md(root, f"# {title}", f"# {title}!")
    assert load(root).scene.timeline[0].dialogue[0].audio_ref is None  # stamps gone
    assert _gc(root, force=True).deleted == []
    _, rendered = _render(root, fake_render)
    assert rendered == []


@pytest.mark.genre("cutout_animation")
def test_a_line_whose_audio_is_not_cached_makes_gc_refuse(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _speaking(root)
    _render(root, fake_render)
    _edit_md(root, "hello there", "hello again")
    before = _ids(root)
    with pytest.raises(CacheGcError, match="not in the audio store"):
        _gc(root)
    assert _ids(root) == before


def test_max_age_never_drops_the_current_scene_under_a_recorded_knob_set(
    tmp_path, fake_render
):
    """an#280 review G2: an old root stops naming its entries, but its knob set
    is still recomputed, so the unchanged scene's master survives."""
    root = _project(tmp_path, _shot("a", 10.0))
    master, _ = _render(root, fake_render, output_name="master", pix_fmt="yuv444p")
    assert _gc(root, max_age=1.0).deleted == []
    assert set(_keys(master)) <= _ids(root)
    again, rendered = _render(root, fake_render, output_name="master", pix_fmt="yuv444p")
    assert rendered == []


def test_two_projects_sharing_a_store_keep_each_others_entries(tmp_path, fake_render):
    """an#280 review G3: a root is per project."""
    b = _project(tmp_path / "b", _shot("a", 10.0), _shot("b", 20.0))
    c = _project(tmp_path / "c", _shot("a", 10.0), _shot("b", 99.0))
    shared = b / "artifacts" / "shot_cache"
    target = c / "artifacts" / "shot_cache"
    import shutil

    shutil.rmtree(target)
    target.symlink_to(shared, target_is_directory=True)
    rb, _ = _render(b, fake_render)
    _render(c, fake_render)
    _gc(c)
    assert set(_keys(rb)) <= _ids(b)


def test_a_render_under_other_knobs_keeps_its_entries(tmp_path, fake_render):
    """The 4:4:4 master and the 4:2:0 delivery: both renders' shots stay, and
    a later master render reuses its own."""
    root = _project(tmp_path, _shot("a", 10.0))
    master, _ = _render(root, fake_render, pix_fmt="yuv444p")
    _render(root, fake_render)
    assert _gc(root).deleted == []
    again, rendered = _render(root, fake_render, pix_fmt="yuv444p")
    assert rendered == [] and _keys(again) == _keys(master)


def test_entries_a_render_on_another_machine_used_are_kept(tmp_path, fake_render, monkeypatch):
    """A synced project: this machine cannot recompute the other's keys (its
    environment differs), so the other render's root is what keeps them."""
    import an.build.shot_cache as sc

    root = _project(tmp_path, _shot("a", 10.0))
    with monkeypatch.context() as m:
        m.setattr(sc, "machine_id", lambda: "the-other-mac")
        elsewhere, _ = _render(root, fake_render, cache=ShotCache(environment=_env("f" * 64)))
    _render(root, fake_render)  # this machine
    _gc(root)
    assert set(_keys(elsewhere)) <= _ids(root)


def test_an_upgrade_on_this_machine_does_not_pin_the_old_entries(tmp_path, fake_render):
    """The same machine, a new browser: the new render's root REPLACES the old
    one, so the entries keyed on the old environment become collectable."""
    root = _project(tmp_path, _shot("a", 10.0))
    before, _ = _render(root, fake_render, cache=ShotCache(environment=_env("f" * 64)))
    _render(root, fake_render)  # upgraded: environment e
    assert sum(k.startswith(ROOT_PREFIX) for k in _ids(root)) == 1
    assert [e.id for e in _gc(root).deleted] == _keys(before)


def test_a_shared_blob_outlives_the_record_that_is_collected(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    report, _ = _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    rec = store[_keys(report)[0]]
    store["0" * 64] = rec.model_copy(update={"shot_key": "0" * 64})  # unreachable twin
    deleted = _gc(root)
    assert [e.id for e in deleted.deleted] == ["0" * 64]
    assert deleted.freed_bytes == 0 and store.has_blob(rec.asset_id)


def test_whole_frame_entries_no_render_reads_are_collected(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    report, _ = _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    key = _keys(report)[0]
    blob = store.put_blob(b"a zip of every frame")
    store[key + FRAMES_SUFFIX] = store[key].model_copy(
        update={"asset_id": blob, "role": "frames"}
    )
    gone = _gc(root)
    assert [e.role for e in gone.deleted] == ["frames"] and not store.has_blob(blob)


# -----------------------------------------------------------------------------
# What is never deleted, and how
# -----------------------------------------------------------------------------


def test_nothing_written_since_a_live_render_began_is_collected(tmp_path, fake_render):
    """A render in progress has written entries its root does not name yet;
    the run's live marker protects everything written after it started."""
    root = _project(tmp_path, _shot("a", 10.0))
    v1, _ = _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    run = root / ".an" / "render_work" / "runs" / "in_progress"
    run.mkdir(parents=True)
    marker = run / ".live"
    marker.write_text(str(os.getpid()), encoding="utf-8")  # this process: alive, not done
    started = time.time() - 3600
    os.utime(marker, (started, started))

    assert _gc(root).deleted == []
    assert set(_keys(v1)) <= _ids(root)
    marker.unlink()  # the render finished
    assert [e.id for e in _gc(root).deleted] == _keys(v1)


def test_entries_written_during_the_collection_are_left_alone(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    v1, _ = _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    report = collect_garbage(root, engine=ShotCache(environment=_env()), now=time.time())
    assert report.deleted == [] and _keys(v1)[0] in report.kept_protected


def _two_generations(tmp_path, fake):
    root = _project(tmp_path, _shot("a", 10.0))
    v1, _ = _render(root, fake)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake)
    return root, _keys(v1)[0]


def test_a_record_written_after_the_horizon_is_kept_whatever_its_file_says(
    tmp_path, fake_render
):
    """The provenance time alone protects it (its file is back-dated)."""
    root, old = _two_generations(tmp_path, fake_render)
    rec = load(root).mall["shot_cache"][old]
    written = float(rec.provenance.generated_at_time.to_seconds())
    f = root / "artifacts/shot_cache/catalog" / f"{old}.json"
    os.utime(f, (written - 3600, written - 3600))
    report = collect_garbage(root, engine=ShotCache(environment=_env()), now=written + 1)
    assert old in report.kept_protected and old in _ids(root)


def test_a_record_rewritten_since_the_listing_is_kept(tmp_path, fake_render):
    """Its provenance says old, its file says new (a concurrent --force-render
    re-recorded the key): the last-moment mtime check keeps it."""
    root, old = _two_generations(tmp_path, fake_render)
    f = root / "artifacts/shot_cache/catalog" / f"{old}.json"
    future = time.time() + 3600
    os.utime(f, (future, future))
    _gc(root)
    assert old in _ids(root)


def test_a_blob_rewritten_during_the_collection_is_kept(tmp_path, fake_render, monkeypatch):
    import an.build.gc as gc_mod

    root, old = _two_generations(tmp_path, fake_render)
    store = load(root).mall["shot_cache"]
    blob = store.blob_path(store[old].asset_id)
    real = gc_mod._remove_record

    def and_a_render_rewrites_the_blob(*a, **k):
        done = real(*a, **k)
        future = time.time() + 3600
        os.utime(blob, (future, future))
        return done

    monkeypatch.setattr(gc_mod, "_remove_record", and_a_render_rewrites_the_blob)
    _gc(root)
    assert blob.exists()


def test_gc_refuses_rather_than_guesses_when_the_scene_cannot_be_keyed(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    before = _ids(root)

    def broken(_name):
        raise RuntimeError("no browser here")

    with pytest.raises(CacheGcError, match="nothing was deleted"):
        collect_garbage(root, engine=ShotCache(environment=broken), now=time.time() + _LATER)
    assert _ids(root) == before


def test_deletion_is_permanent_not_a_trip_to_the_trash(tmp_path, fake_render, monkeypatch):
    import dol.trash

    def no_trash(*a, **k):
        raise AssertionError("moved to the trash: frees nothing")

    monkeypatch.setattr(dol.trash, "default_delete_func", no_trash)
    root = _project(tmp_path, _shot("a", 10.0))
    v1, _ = _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    blob = store.blob_path(store[_keys(v1)[0]].asset_id)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    assert _gc(root).deleted
    assert not blob.exists()
    assert not (root / "artifacts/shot_cache/catalog" / f"{_keys(v1)[0]}.json").exists()


def test_an_orphan_blob_is_collected_only_once_it_predates_the_horizon(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    orphan = store.put_blob(b"a render crashed between blob and record")
    assert collect_garbage(
        root, engine=ShotCache(environment=_env()), now=time.time()
    ).deleted_blobs == {}
    assert store.has_blob(orphan)
    assert orphan in _gc(root).deleted_blobs and not store.has_blob(orphan)


def test_a_blob_collected_under_a_lookup_is_a_miss(tmp_path):
    """What a render racing a collection sees: the record is there, the blob
    is gone (or vanishes between `has_blob` and `get_blob`) — a miss."""
    from tests.test_shot_cache import _FakeCutoutRender, _Named, _ctx

    from an.build import in_memory_shot_cache_store

    store = in_memory_shot_cache_store()
    engine = ShotCache(store, environment=_env())
    ctx, shot, fake = _ctx(tmp_path), _shot("a", 10.0), _FakeCutoutRender()
    engine.begin({})
    plan = engine.plan(shot, _Named(), ctx)
    engine.record(plan, fake(None, shot, ctx), render_s=0.1)

    def vanished(_h):
        raise FileNotFoundError(_h)

    store.get_blob = vanished
    engine.begin({})
    again = engine.plan(shot, _Named(), ctx)
    assert again.cached is None and "missing" in again.reason


# -----------------------------------------------------------------------------
# Caps
# -----------------------------------------------------------------------------


def _generations(tmp_path, fake, n):
    root = _project(tmp_path, _shot("a", 10.0))
    keys = []
    for g in range(n):
        _set_shots(root, _shot("a", 10.0 + g))
        report, _ = _render(root, fake)
        keys.append(_keys(report)[0])
        time.sleep(0.01)  # distinct write times
    return root, keys


def test_max_size_keeps_the_newest_unreachable_entries_that_fit(tmp_path, fake_render):
    root, (g0, g1, g2) = _generations(tmp_path, fake_render, 3)
    store = load(root).mall["shot_cache"]
    size = lambda k: store[k].bytes_size  # noqa: E731
    report = _gc(root, max_size=size(g2) + size(g1))
    assert [e.id for e in report.deleted] == [g0] and report.kept_retained == 1
    assert {g1, g2} <= _ids(root)


def test_max_size_never_removes_a_reachable_entry(tmp_path, fake_render):
    root, (g0, g1) = _generations(tmp_path, fake_render, 2)
    _gc(root, max_size=1)
    assert g1 in _ids(root) and g0 not in _ids(root)


def test_max_age_keeps_young_unreachable_entries(tmp_path, fake_render):
    root, (g0, g1) = _generations(tmp_path, fake_render, 2)
    assert _gc(root, max_age=parse_age("1d")).deleted == []
    # Older than the cap: g0. The root stays (roots are never collected: its
    # knob set must keep being recomputed), and g1, which the scene reads.
    gone = _gc(root, max_age=1.0).deleted
    assert [e.id for e in gone] == [g0] and g1 in _ids(root)


def test_sizes_and_ages_parse_as_people_write_them():
    assert parse_size("1G") == 1024**3 and parse_size("10 mb") == 10 * 1024**2
    assert parse_age("2w") == 14 * 86400
    with pytest.raises(ValueError):
        parse_size("lots")
    with pytest.raises(ValueError):
        parse_age("7")


# -----------------------------------------------------------------------------
# info, the CLI, the render summary
# -----------------------------------------------------------------------------


def test_info_says_how_much_is_reachable(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    info = cache_info(root, engine=ShotCache(environment=_env()))
    assert info.by_role["mp4"][0] == 2 and info.by_role["root"][0] == 1
    assert info.reachable[0] == 2 and info.unreachable[0] == 1  # mp4 + root; old mp4
    assert info.unreachable[1] > 0 and "unreachable: 1 entries" in info.summary()


def test_info_never_fails_on_reachability(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)

    def broken(_name):
        raise RuntimeError("no browser here")

    info = cache_info(root, engine=ShotCache(environment=broken))
    assert info.reachable is None and "no browser here" in info.summary()


def test_the_cache_namespace_is_on_the_cli(tmp_path, fake_render, monkeypatch):
    from typer.testing import CliRunner

    import an.build.gc as gc_mod
    from an.__main__ import build_app
    from an.tools import _dispatch_funcs, _dispatch_namespaces

    assert [f.__name__ for f in _dispatch_namespaces["cache"]] == ["info", "gc"]
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    _set_shots(root, _shot("a", 11.0))
    _render(root, fake_render)
    monkeypatch.setattr(gc_mod, "ShotCache", lambda store=None: ShotCache(store, environment=_env()))
    real = gc_mod.collect_garbage
    monkeypatch.setattr(
        gc_mod, "collect_garbage",
        lambda d, **kw: real(d, now=time.time() + _LATER, **kw),
    )  # fmt: skip
    import an.build.cli as cli

    monkeypatch.setattr(cli, "collect_garbage", gc_mod.collect_garbage)
    app = build_app(_dispatch_funcs, _dispatch_namespaces)
    dry = CliRunner().invoke(app, ["cache", "gc", str(root), "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "would delete 1 entries (1 mp4)" in dry.output
    before = _ids(root)
    out = CliRunner().invoke(app, ["cache", "gc", str(root), "--max-size", "huge"])
    assert out.exit_code != 0 and "not a size" in out.output and _ids(root) == before


def test_the_render_summary_says_how_big_the_cache_is(tmp_path, fake_render, monkeypatch):
    import an.build as build
    import an.tools as tools

    root = _project(tmp_path, _shot("a", 10.0))
    monkeypatch.setattr(build, "ShotCache", lambda **kw: ShotCache(environment=_env(), **kw))
    text = tools.render(str(root))
    assert "\nshot cache: " in text and " entries" in text and "an cache gc" in text


# -----------------------------------------------------------------------------
# Film windows (an#260): pure
# -----------------------------------------------------------------------------


def _random_timeline(rng):
    shots = []
    for i in range(rng.randint(1, 6)):
        t = None
        if i and rng.random() < 0.6:
            t = Transition(
                kind=rng.choice(["dissolve", "fade", "cut"]),
                duration=rng.choice([0.1, 0.2, 0.3, 0.5]),
                color="#000000",
            )
        elif not i and rng.random() < 0.3:
            t = Transition(kind="fade", duration=0.2, color="#000000")
        shots.append(Shot(id=f"s{i}", duration=rng.choice([0.1, 0.2, 0.3, 0.6, 1.0, 2.0]), transition=t))
    return shots


def test_every_segment_of_a_multi_segment_picture_has_the_b_frame_delay():
    """`MIN_SEGMENT_FRAMES`, on 2000 random films: windows cover every frame a
    transition touches; segments tile the film; none is short."""
    from an.assemble import AssemblyError

    rng = random.Random(260)
    checked = 0
    for _ in range(2000):
        shots = _random_timeline(rng)
        try:
            tl = film_timeline(shots, fps=10)
        except AssemblyError:
            continue
        windows = shot_windows(tl)
        segments = picture_segments(tl, windows)
        assert segments[0].start == 0 and segments[-1].stop == tl.total_frames
        assert all(a.stop == b.start for a, b in zip(segments, segments[1:]))
        if len(segments) > 1:
            assert min(len(s) for s in segments) >= MIN_SEGMENT_FRAMES, (shots, segments)
        for i, w in enumerate(windows):
            assert w.head >= tl.dissolve_in[i] + tl.fade_in[i]
            nxt = tl.dissolve_in[i + 1] if i + 1 < len(windows) else 0
            assert w.tail >= tl.fade_out[i] + nxt
            assert w.head + w.tail <= w.frames
        checked += 1
    assert checked > 1000


def test_a_film_of_cuts_and_sound_takes_every_shot_whole():
    tl = film_timeline([Shot(id="a", duration=1.0), Shot(id="b", duration=0.5)], fps=10)
    windows = shot_windows(tl)
    assert all(w.whole for w in windows)
    assert [s.kind for s in picture_segments(tl, windows)] == ["shot", "shot"]


def test_a_shot_too_short_to_stand_alone_is_taken_as_frames():
    tl = film_timeline(
        [Shot(id="a", duration=1.0), Shot(id="b", duration=0.1), Shot(id="c", duration=1.0)],
        fps=10,
    )
    windows = shot_windows(tl)
    assert windows[1] == ShotWindow(frames=1, head=1, tail=0)
    assert min(len(s) for s in picture_segments(tl, windows)) >= MIN_SEGMENT_FRAMES


def test_a_parts_id_names_the_window():
    from an.build.shot_cache import parts_entry_id

    ids = {
        parts_entry_id("k" * 64, ShotWindow(frames=10, head=h, tail=t))
        for h, t in [(0, 3), (3, 0), (1, 3), (0, 4)]
    }
    assert len(ids) == 4


def test_a_parts_zip_for_another_window_is_a_miss(tmp_path):
    import zipfile

    from an.build.shot_cache import _unpack_parts

    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("body.mp4", b"x")
        for j in (6, 7, 8):  # one frame short of a 4-frame tail
            zf.writestr(f"frames/frame_{j:06d}.png", b"png")
    window = ShotWindow(frames=10, head=0, tail=4)
    assert _unpack_parts(z.read_bytes(), window, tmp_path / "out") is None
    ok = tmp_path / "ok.zip"
    with zipfile.ZipFile(ok, "w") as zf:
        zf.writestr("body.mp4", b"x")
        for j in (6, 7, 8, 9):
            zf.writestr(f"frames/frame_{j:06d}.png", b"png")
    parts = _unpack_parts(ok.read_bytes(), window, tmp_path / "out2")
    assert sorted(parts.frames) == [6, 7, 8, 9] and parts.body.name == "body.mp4"


def test_parts_cut_for_another_window_are_refused_by_the_film(tmp_path):
    from an.adapters._base import RenderResult
    from an.assemble import AssemblyError, ShotParts, assemble_film

    d = Transition(kind="dissolve", duration=0.4)
    scene = SceneIR(
        meta=Meta(fps=10),
        timeline=[Shot(id="a", duration=1.0), Shot(id="b", duration=1.0, transition=d)],
    )
    wrong = ShotParts(window=ShotWindow(frames=10, head=0, tail=3), frames={}, body=None)
    results = [RenderResult(mp4_path=tmp_path / "x.mp4", duration=1.0)] * 2
    with pytest.raises(AssemblyError, match="parts are for"):
        assemble_film(
            scene, results, tmp_path / "o.mp4", fps=10, mall={}, work_dir=tmp_path,
            parts=[wrong, None],
        )  # fmt: skip


# -----------------------------------------------------------------------------
# Assembled films, for real (ffmpeg)
# -----------------------------------------------------------------------------

_SIZE = (160, 96)


class _SolidCutout:
    """`CutoutRenderer.render`'s stand-in: one colour per shot (brightened by
    its tween target, so an edit changes the picture) through the REAL mux."""

    def __init__(self) -> None:
        self.rendered: list[str] = []

    def __call__(self, renderer_self, shot, ctx):
        from PIL import Image

        from an.adapters._base import RenderResult
        from an.adapters.cutout.render import DEFAULT_FRAME_PNG_PATTERN, _mux_shot
        from an.frame_clock import frame_count

        self.rendered.append(shot.id)
        work = Path(ctx.work_dir) / f"shot_{shot.id}"
        frames = work / "frames"
        frames.mkdir(parents=True, exist_ok=True)
        n = frame_count(shot.duration, ctx.fps)
        w, h = ctx.resolution
        seed = sum(map(ord, shot.id))
        base = np.random.default_rng(seed).integers(0, 255, size=(h, w, 3), dtype=np.uint8)
        for i in range(n):
            # Content that MOVES (the an#280 reviewer's): x264 then ends a
            # stream on a P-frame, the case whose truncated edit list put
            # frames early at every join (F1).
            a = np.roll(base, i * 3, axis=1).copy()
            a[:, : w // 4] = (i * 37 + seed) % 256
            Image.fromarray(a).save(frames / (DEFAULT_FRAME_PNG_PATTERN % i), format="PNG")
        out = work / f"{shot.id}.mp4"
        _mux_shot(frames, shot, ctx, work, out, n_frames=n)
        return RenderResult(
            mp4_path=out, duration=shot.duration,
            frame_manifest=sorted(frames.glob("*.png")),
        )  # fmt: skip


@pytest.fixture
def solid(monkeypatch):
    from an.adapters.cutout.render import CutoutRenderer

    fake = _SolidCutout()
    monkeypatch.setattr(CutoutRenderer, "render", lambda self, shot, ctx: fake(self, shot, ctx))
    return fake


def _dshot(sid: str, x: float, duration: float) -> Shot:
    from an.ir.compose import tween

    return Shot(
        id=sid, renderer="cutout", duration=duration,
        actions=[tween("root", "x", to=x, duration=duration)],
    )  # fmt: skip


def _film(tmp_path, shots, *, sounds=False, fps=10):
    from an import init
    from an.sounds import SYNTH_SOURCE, add_sound, synth_tone

    root = init(tmp_path / "film")
    project = load(root)
    meta = Meta(fps=fps, resolution=Resolution(width=_SIZE[0], height=_SIZE[1]))
    if sounds:
        meta = meta.model_copy(update={"sounds": [SoundCue(sound="bed", loop=True)]})
        add_sound(project.mall["sounds"], "bed", synth_tone(220.0, 0.5, amplitude=0.2),
                  source=SYNTH_SOURCE)  # fmt: skip
    project.mall["scenes"]["main"] = SceneIR(meta=meta, timeline=list(shots))
    return root


def _render_film(root, fake):
    from an.render import render_project

    fake.rendered.clear()
    cache = ShotCache(environment=_env())
    out = render_project(root, incremental=cache)
    return cache.report, list(fake.rendered), out.read_bytes(), out


def _avg_rate(mp4: Path) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
         "stream=avg_frame_rate", "-of", "csv=p=0", str(mp4)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip


def _probe(mp4: Path, fps: float) -> tuple[int, int, float]:
    """(frames, frames a constant-rate decode yields, worst PTS error vs i/fps)."""
    pts = [
        float(f["pts_time"])
        for f in json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
             "frame=pts_time", "-of", "json", str(mp4)],
            capture_output=True, text=True, check=True).stdout)["frames"]
    ]  # fmt: skip
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(mp4), "-f", "rawvideo",
         "-pix_fmt", "gray", "-"], capture_output=True, check=True,
    ).stdout  # fmt: skip
    cfr = len(raw) // (_SIZE[0] * _SIZE[1])
    return len(pts), cfr, max(abs(t - i / fps) for i, t in enumerate(pts))


@pytest.mark.ffmpeg
def test_a_film_with_a_sound_bed_reuses_its_shots_by_default(tmp_path, solid):
    root = _film(tmp_path, [_shot("a", 1.0), _dshot("b", 2.0, 1.5)], sounds=True)
    cold, rendered, film, out = _render_film(root, solid)
    assert rendered == ["a", "b"]
    warm, rendered, again, _ = _render_film(root, solid)
    assert rendered == [] and warm.reused == ["a", "b"]
    assert again == film  # the delivered bytes do not depend on the cache
    roles = {e.role for e in inventory(load(root).mall["shot_cache"])}
    assert roles == {"mp4", "root"}  # a cut film needs no frames, no parts
    assert _probe(out, 10)[:2] == (25, 25)


@pytest.mark.ffmpeg
def test_a_film_with_a_dissolve_reuses_its_shots_and_stores_only_its_windows(tmp_path, solid):
    d = Transition(kind="dissolve", duration=0.4)
    shots = [_shot("a", 1.0), _shot("b", 1.0).model_copy(update={"transition": d})]
    root = _film(tmp_path, shots)
    _, rendered, film, out = _render_film(root, solid)
    assert rendered == ["a", "b"]
    warm, rendered, again, _ = _render_film(root, solid)
    assert rendered == [] and warm.reused == ["a", "b"] and again == film
    store = load(root).mall["shot_cache"]
    parts = [k for k in store if PARTS_INFIX in k]
    assert len(parts) == 2 and not any(k.endswith(FRAMES_SUFFIX) for k in store)
    assert _probe(out, 10)[:2] == (16, 16)

    # Edit b: a is reused WITH its parts, b re-renders.
    shots[1] = _shot("b", 30.0).model_copy(update={"transition": d})
    _set_shots(root, *shots)
    edited, rendered, _, _ = _render_film(root, solid)
    assert rendered == ["b"] and edited.reused == ["a"]


@pytest.mark.ffmpeg
def test_short_segments_never_reach_the_concat(tmp_path, solid):
    """A one-frame dissolve and a one-frame shot: without the widening, a
    1-2-frame segment between long ones leaves DTS going backwards and a
    constant-rate decode shows a frame twice (measured, an#260)."""
    one = Transition(kind="dissolve", duration=0.1)
    shots = [
        _shot("a", 1.0),
        _shot("b", 1.0).model_copy(update={"transition": one}),
        _dshot("c", 1.0, 0.1),
        _shot("a2", 1.0),
    ]
    root = _film(tmp_path, shots, sounds=True)
    _, _, film, out = _render_film(root, solid)
    total = film_timeline(shots, fps=10).total_frames
    frames, cfr, err = _probe(out, 10)
    assert frames == cfr == total and err < 1e-3
    _, rendered, again, _ = _render_film(root, solid)
    assert rendered == [] and again == film


@pytest.mark.ffmpeg
def test_joins_keep_every_frame_on_the_grid_and_the_rate_whole(tmp_path, solid):
    """an#280 review F1: at 24 fps, moving content, segments of n != 0 mod 3
    frames — without stated segment durations every join put the later frames
    up to 1 ms early, cumulatively, and the film's average rate was not 24/1."""
    d = Transition(kind="dissolve", duration=0.125)
    shots = [
        _dshot(sid, float(k), dur).model_copy(update={"transition": d if k else None})
        for k, (sid, dur) in enumerate(
            [("a", 0.95), ("b", 1.2), ("c", 0.7), ("a2", 1.45), ("b2", 0.8)]
        )
    ]
    root = _film(tmp_path, shots, sounds=True, fps=24)
    _, _, _, out = _render_film(root, solid)
    total = film_timeline(shots, fps=24).total_frames
    frames, cfr, err = _probe(out, 24)
    assert frames == cfr == total
    assert err < 1e-4, err
    assert _avg_rate(out) == "24/1"


@pytest.mark.ffmpeg
def test_a_shot_whose_mp4_does_not_match_the_film_is_refused(tmp_path, solid, monkeypatch):
    """an#280 review F2: a renderer that writes only an mp4 (Manim's 480p15)
    must not be stream-copied into a film it does not match."""
    from an.adapters._base import RenderResult
    from an.adapters.cutout.render import CutoutRenderer
    from an.assemble import AssemblyError
    from an.media.mp4 import mux_frames

    def render(self, shot, ctx):
        if shot.id != "m":
            return solid(self, shot, ctx)
        from PIL import Image

        work = Path(ctx.work_dir) / "mp4_only"
        (work / "f").mkdir(parents=True, exist_ok=True)
        for i in range(15):
            Image.new("RGB", (320, 240), (9, 9, 9)).save(work / "f" / f"frame_{i:06d}.png")
        out = work / "m.mp4"
        mux_frames(work / "f", 15, out)
        return RenderResult(mp4_path=out, duration=shot.duration)  # no frames

    monkeypatch.setattr(CutoutRenderer, "render", render)
    root = _film(tmp_path, [_shot("a", 1.0), _shot("m", 2.0)], sounds=True)
    with pytest.raises(AssemblyError, match="shot 1"):
        _render_film(root, solid)


@pytest.mark.ffmpeg
def test_a_forced_collection_keeps_the_current_scenes_parts(tmp_path, solid):
    """With no root, only the recomputed keys protect a dissolve's parts."""
    d = Transition(kind="dissolve", duration=0.4)
    shots = [_shot("a", 1.0), _shot("b", 1.0).model_copy(update={"transition": d})]
    root = _film(tmp_path, shots)
    _render_film(root, solid)
    _drop_roots(root)
    assert _gc(root, force=True).deleted == []
    _, rendered, _, _ = _render_film(root, solid)
    assert rendered == []


def test_cache_frames_is_deprecated_in_python_and_on_the_cli(tmp_path, fake_render, monkeypatch):
    import an.build as build
    import an.tools as tools

    with pytest.deprecated_call(match="next release"):
        ShotCache(cache_frames=True)
    root = _project(tmp_path, _shot("a", 10.0))
    monkeypatch.setattr(
        build, "ShotCache",
        lambda **kw: ShotCache(environment=_env(), **kw),
    )  # fmt: skip
    with pytest.deprecated_call():
        text = tools.render(str(root), cache_frames=True)
    assert "--cache-frames is deprecated" in text


# -----------------------------------------------------------------------------
# A renderer that owns its clock (Manim, an#279), in an assembled film
# -----------------------------------------------------------------------------


def _manim_film(tmp_path):
    """A fake-Manim shot (its length is MEASURED: 2 s, though it declares
    none) dissolving into a cut-out shot, under a looped bed, at 30 fps."""
    from an.sounds import SYNTH_SOURCE, add_sound, synth_tone
    from an.stores import build_project_mall
    from tests.test_manim_renderer import LINEAR

    root = _film(tmp_path, [], sounds=False, fps=30)
    mall = build_project_mall(root)
    mall["sources"]["chart"] = LINEAR
    add_sound(mall["sounds"], "bed", synth_tone(220.0, 0.5, amplitude=0.2), source=SYNTH_SOURCE)
    mall["scenes"]["main"] = SceneIR(
        meta=Meta(fps=30, resolution=Resolution(width=_SIZE[0], height=_SIZE[1]),
                  sounds=[SoundCue(sound="bed", loop=True)]),
        timeline=[
            Shot(id="chart", renderer="manim", options={"source": "chart"}),
            _dshot("c", 5.0, 1.0).model_copy(
                update={"transition": Transition(kind="dissolve", duration=0.5)}),
        ],
    )  # fmt: skip
    return root


@pytest.mark.ffmpeg
def test_a_manim_shot_dissolving_into_a_cutout_shot_assembles_and_is_reused(
    tmp_path, solid, monkeypatch
):
    from tests.test_manim_renderer import FakeRenderCheck
    import an.adapters.manim_adapter as ma

    monkeypatch.setattr(ma, "manim_version", lambda: "0.0.0-fake")
    check = FakeRenderCheck(seconds=2.0)
    monkeypatch.setattr(ma, "_manimkit_render_check", lambda: check)
    root = _manim_film(tmp_path)
    _, rendered, film, out = _render_film(root, solid)
    frames, cfr, err = _probe(out, 30)
    assert frames == cfr == 60 + 30 - 15 and err < 1e-4  # measured 2 s, 1 s, 0.5 s overlap
    assert _avg_rate(out) == "30/1"
    calls = check.calls
    warm, rendered, again, _ = _render_film(root, solid)
    assert warm.reused == ["chart", "c"] and rendered == [] and check.calls == calls
    assert again == film


@pytest.mark.ffmpeg
def test_a_forced_collection_keeps_the_manim_shots_entries(tmp_path, solid, monkeypatch):
    """The collector keys the Manim shot at its MEASURED length (read from the
    measurements store, never by running Manim); keyed at its authored length
    it would lose the shot's mp4 and parts (an#280 review, round 2)."""
    from tests.test_manim_renderer import FakeRenderCheck
    import an.adapters.manim_adapter as ma

    monkeypatch.setattr(ma, "manim_version", lambda: "0.0.0-fake")
    check = FakeRenderCheck(seconds=2.0)
    monkeypatch.setattr(ma, "_manimkit_render_check", lambda: check)
    root = _manim_film(tmp_path)
    _render_film(root, solid)
    _drop_roots(root)
    calls = check.calls
    assert _gc(root, force=True).deleted == []
    assert check.calls == calls  # the collection ran no Manim
    warm, rendered, _, _ = _render_film(root, solid)
    assert warm.reused == ["chart", "c"] and check.calls == calls


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    "size,n,match",
    [((320, 240), 10, "stream differs"), (_SIZE, 7, "holds 7 frames")],
)
def test_a_shot_stream_of_the_right_rate_but_wrong_shape_is_refused(
    tmp_path, solid, monkeypatch, size, n, match
):
    """F2's two other checks: the size (and every other stream field), and the
    frame count a stream copy cannot change."""
    from an.adapters._base import RenderResult
    from an.adapters.cutout.render import CutoutRenderer
    from an.assemble import AssemblyError
    from an.media.mp4 import mux_frames

    def render(self, shot, ctx):
        if shot.id != "m":
            return solid(self, shot, ctx)
        from PIL import Image

        work = Path(ctx.work_dir) / "mp4_only"
        (work / "f").mkdir(parents=True, exist_ok=True)
        for i in range(n):
            Image.new("RGB", size, (9, 9, i)).save(work / "f" / f"frame_{i:06d}.png")
        out = work / "m.mp4"
        mux_frames(work / "f", ctx.fps, out)
        return RenderResult(mp4_path=out, duration=shot.duration)

    monkeypatch.setattr(CutoutRenderer, "render", render)
    root = _film(tmp_path, [_shot("a", 1.0), _shot("m", 2.0)], sounds=True)
    with pytest.raises(AssemblyError, match=match):
        _render_film(root, solid)


def test_a_fresh_process_finds_the_renderers_through_the_lazy_registry(tmp_path, fake_render):
    """GC keys shots through the renderer registry's real lookup, so a process
    that imported no adapter (the CLI) still loads them and keeps the scene."""
    import sys

    root, old = _two_generations(tmp_path, fake_render)
    code = (
        "import time, json\n"
        "from an.build import ShotCache\n"
        "from an.build.gc import collect_garbage\n"
        f"r = collect_garbage({str(root)!r}, dry_run=True, now=time.time() + 60,\n"
        f"    engine=ShotCache(environment=lambda name: {_ENV!r}))\n"
        "print(json.dumps([[e.id for e in r.deleted], r.kept_reachable]))\n"
    )
    import an

    env = {**os.environ, "PYTHONPATH": str(Path(an.__file__).parent.parent)}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    ).stdout
    deleted, kept = json.loads(out.strip().splitlines()[-1])
    assert deleted == [old] and kept >= 2  # the current mp4 and the root


# -----------------------------------------------------------------------------
# an#306: each recorded render's own providers, never a hypothetical default
# -----------------------------------------------------------------------------


def _voiced(root, *texts: str, voice: dict | None = None) -> None:
    """One shot per text, each with one line in voice `bob`."""
    from an.ir.schema import Dialogue

    shots = []
    for i, text in enumerate(texts):
        shot = _shot(f"s{i}", 10.0 + i)
        shot.duration = 3.0
        shot.dialogue = [Dialogue(speaker="x", text=text, voice_ref="bob")]
        shots.append(shot)
    _set_shots(root, *shots)
    if voice is not None:
        load(root).mall["voices"]["bob"] = voice


def test_gc_and_info_work_right_after_an_elevenlabs_render(tmp_path, fake_render, eleven):
    """The end-user report: `--tts elevenlabs` for a voice that names no
    provider, then `an cache info/gc` failed keying the scene under offline."""
    root = _project(tmp_path, _shot("a", 10.0))
    _voiced(root, "hello there", "and again")
    first, _ = _render(root, fake_render, tts="elevenlabs")
    info = cache_info(root, engine=ShotCache(environment=_env()))
    assert info.reachable is not None and info.unreachable[0] == 0
    assert "not keyed under 2 knob set(s) (tts=offline, tts=voice)" in info.summary()
    report = _gc(root)
    assert report.deleted == [] and "not keyed under" in report.summary()
    _, rendered = _render(root, fake_render, tts="elevenlabs")
    assert rendered == [] and len(eleven.requests) == 2  # nothing re-billed


def test_a_voice_that_names_elevenlabs_is_kept_under_a_plain_render(
    tmp_path, fake_render, eleven
):
    root = _project(tmp_path, _shot("a", 10.0))
    _voiced(root, "hello there", voice={"provider": "elevenlabs", "voice_id": "TX3"})
    report, _ = _render(root, fake_render, tts="elevenlabs")
    _drop_roots(root)  # no root: only the plain render's knob sets speak
    assert _gc(root, force=True).deleted == []
    _, rendered = _render(root, fake_render)  # plain: the voice's own provider
    assert rendered == [] and len(eleven.requests) == 1


def test_a_knob_set_missing_a_lines_audio_keeps_what_its_render_used(
    tmp_path, fake_render, eleven
):
    """Rendered offline once, then ElevenLabs; a line edited and re-rendered
    with ElevenLabs only. The offline knob set cannot key the edited shot, so
    it is skipped — and its root keeps the unchanged shot's offline entry even
    when --max-age has expired it."""
    root = _project(tmp_path, _shot("a", 10.0))
    _voiced(root, "hello there", "stays the same")
    offline, _ = _render(root, fake_render, tts="offline")
    _render(root, fake_render, tts="elevenlabs")
    _voiced(root, "hello again", "stays the same")
    _render(root, fake_render, tts="elevenlabs")
    report = _gc(root, max_age=1.0)
    # offline (recorded) and a plain render's (bob names no provider: offline)
    assert sorted(p["tts"] for p, _ in report.reach.skipped) == ["offline", "voice"]
    assert "hello again" in report.reach.skipped[0][1]
    assert set(_keys(offline)) <= _ids(root)  # what the offline render used
    _, rendered = _render(root, fake_render, tts="offline")
    assert rendered == ["s0"]  # the edited shot only: its offline line is new
