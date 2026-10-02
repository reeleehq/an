"""The content-keyed shot cache (ADR 0004 first slice, an#242).

Most of these run with NO browser and NO ffmpeg: the cut-out keyer is real (it
compiles every shot, digests the art and the knobs), and only the render itself
is a stand-in that writes a few bytes and counts its calls — so "exactly one
shot renders" is a statement about the key, which is what is under test. The
one end-to-end render is `browser`-marked, like every other render test.
"""

from __future__ import annotations

import os
import shutil
import time
import zipfile
from pathlib import Path

import pytest

from an import init
from an.adapters._base import RenderContext, RenderResult
from an.build import (
    BuildReport,
    ShotCache,
    compose_shot_key,
    in_memory_shot_cache_store,
    project_assets_digest,
    resolve_incremental,
)
from an.ir.compose import tween
from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, Shot
from an.project import load

_FPS = 12
_ENV = "e" * 64


def _env(digest: str = _ENV):
    """An environment seam that states the machine rather than probing it."""
    return lambda renderer_name: digest


class _FakeCutoutRender:
    """Stands in for `CutoutRenderer.render`: no browser, a few honest bytes."""

    def __init__(self) -> None:
        self.rendered: list[str] = []

    def __call__(self, renderer_self, shot, ctx):
        self.rendered.append(shot.id)
        work = Path(ctx.work_dir) / f"shot_{shot.id}"
        frames = work / "frames"
        frames.mkdir(parents=True, exist_ok=True)
        n = max(1, round(shot.duration * ctx.fps))
        for i in range(n):
            (frames / f"frame_{i:06d}.png").write_bytes(f"{shot.id}:{i}".encode())
        out = work / f"{shot.id}.mp4"
        out.write_bytes(f"mp4 of {shot.id} @ {time.time_ns()}".encode())
        return RenderResult(
            mp4_path=out,
            duration=shot.duration,
            frame_manifest=sorted(frames.glob("*.png")),
            provenance={"shot_id": shot.id},
        )


@pytest.fixture
def fake_render(monkeypatch):
    import an.render as render_mod
    from an.adapters.cutout.render import CutoutRenderer

    fake = _FakeCutoutRender()
    monkeypatch.setattr(
        CutoutRenderer, "render", lambda self, shot, ctx: fake(self, shot, ctx)
    )
    monkeypatch.setattr(
        render_mod, "_ffmpeg_concat", lambda inputs, out: shutil.copy(list(inputs)[0], out)
    )
    return fake


def _shot(sid: str, x: float, *, entities=()) -> Shot:
    return Shot(
        id=sid,
        renderer="cutout",
        duration=1.0,
        entities=list(entities),
        actions=[tween("root", "x", to=x, duration=1.0)],
    )


def _project(tmp_path, *shots: Shot, character: bool = False):
    root = init(tmp_path / "p")
    if character:
        from cutan.characters.factory import new_character

        new_character(root / "assets" / "characters", name="amy", use_dicebear=False)
    project = load(root)
    project.mall["scenes"]["main"] = SceneIR(
        meta=Meta(fps=_FPS, resolution=Resolution(width=160, height=120)),
        timeline=list(shots),
    )
    return root


def _set_shots(root, *shots: Shot) -> None:
    project = load(root)
    scene = project.scene
    scene.timeline = list(shots)
    project.mall["scenes"]["main"] = scene


def _render(root, fake, **kw) -> tuple[BuildReport, list[str]]:
    from an.render import render_project

    fake.rendered.clear()
    cache = kw.pop("cache", None) or ShotCache(environment=_env())
    render_project(root, incremental=cache, **kw)
    return cache.report, list(fake.rendered)


# -----------------------------------------------------------------------------
# ADR 0004's first-slice tests
# -----------------------------------------------------------------------------


def test_an_unchanged_project_renders_nothing_the_second_time(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    report, rendered = _render(root, fake_render)
    assert rendered == ["a", "b"] and report.reused == []
    report, rendered = _render(root, fake_render)
    assert rendered == [] and report.reused == ["a", "b"]
    assert report.summary() == "2 shot(s): 0 rendered (-), 2 reused (a, b)"


def test_editing_one_shot_of_two_renders_exactly_that_shot(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    _render(root, fake_render)
    _set_shots(root, _shot("a", 10.0), _shot("b", 25.0))
    report, rendered = _render(root, fake_render)
    assert rendered == ["b"]
    assert report.reused == ["a"]
    # The film is still assembled from both, in timeline order.
    out = root / "output" / "main.mp4"
    assert out.exists()


def test_the_key_is_never_the_shot_id(tmp_path, fake_render):
    """Renaming a shot changes nothing it renders, so it is reused; giving a
    shot another shot's content makes it that shot's entry."""
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    _render(root, fake_render)
    _set_shots(root, _shot("renamed", 10.0), _shot("b", 20.0))
    report, rendered = _render(root, fake_render)
    assert rendered == [] and report.reused == ["renamed", "b"]


@pytest.mark.genre("cutout_animation")
def test_editing_an_svg_part_in_place_rerenders_the_shot_that_draws_it(tmp_path, fake_render):
    amy = AssetRef(kind="character", id="amy", store="characters", ref="amy")
    root = _project(
        tmp_path, _shot("with_amy", 10.0, entities=[amy]), _shot("empty", 20.0), character=True
    )
    _render(root, fake_render)

    parts = sorted((root / "assets" / "characters" / "amy" / "parts").glob("*.svg"))
    assert parts, "the factory character has SVG parts"
    part = parts[0]
    before = part.stat()
    part.write_text(part.read_text(encoding="utf-8").replace("<svg", "<svg data-edit='1'", 1), encoding="utf-8")
    # In place, same path: the compiled document cannot see this edit (SVG
    # art keeps a plain alias), only the texture digests can.
    os.utime(part, ns=(before.st_atime_ns, before.st_mtime_ns + 10**9))

    report, rendered = _render(root, fake_render)
    assert "with_amy" in rendered
    # Decision 3's fallback: every shot depends on every asset in the project,
    # so the shot that does not draw Amy re-renders too — until reads are
    # recorded. The precise half is already in the key: see the next test.
    assert rendered == ["with_amy", "empty"]


@pytest.mark.genre("cutout_animation")
def test_without_the_project_fallback_only_the_drawing_shot_rerenders(tmp_path, fake_render):
    """The texture digests alone are precise: with decision 3's whole-project
    dependency switched off, an SVG edit re-renders only the shot whose
    document stages that file — the behaviour read recording will make the
    default."""
    amy = AssetRef(kind="character", id="amy", store="characters", ref="amy")
    root = _project(
        tmp_path, _shot("with_amy", 10.0, entities=[amy]), _shot("empty", 20.0), character=True
    )
    precise = lambda: ShotCache(environment=_env(), dependencies=None)  # noqa: E731
    _render(root, fake_render, cache=precise())
    part = sorted((root / "assets" / "characters" / "amy" / "parts").glob("*.svg"))[0]
    st = part.stat()
    part.write_text(part.read_text(encoding="utf-8") + "\n<!-- edit -->\n", encoding="utf-8")
    os.utime(part, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    report, rendered = _render(root, fake_render, cache=precise())
    assert rendered == ["with_amy"] and report.reused == ["empty"]
    (outcome,) = [o for o in report.outcomes if o.shot_id == "with_amy"]
    assert outcome.status == "rendered"


def test_the_library_lockfile_is_a_dependency_of_every_shot_before_it_is_in_the_mall(
    tmp_path, fake_render
):
    """A re-pin in `assets.lock.json` (the asset library's lockfile, P5) changes
    what is checked out, so it moves every key — read by its PATH, because its
    store registration in the mall (an#240) lands separately."""
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    assert "assets.lock.json" not in str(sorted(load(root).mall))
    _render(root, fake_render)
    (root / "assets.lock.json").write_text('{"pins": {}}', encoding="utf-8")
    _, rendered = _render(root, fake_render)
    assert rendered == ["a", "b"]
    _, rendered = _render(root, fake_render)
    assert rendered == []
    lock = root / "assets.lock.json"
    st = lock.stat()
    lock.write_text('{"pins": {"characters/amy": "v002"}}', encoding="utf-8")
    os.utime(lock, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    _, rendered = _render(root, fake_render)
    assert rendered == ["a", "b"]


def test_a_changed_environment_renders_every_shot(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    _render(root, fake_render)
    other_machine = ShotCache(environment=_env("f" * 64))
    report, rendered = _render(root, fake_render, cache=other_machine)
    assert rendered == ["a", "b"] and report.reused == []


def test_a_render_knob_is_in_the_key(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    _, rendered = _render(root, fake_render, pix_fmt="yuv444p")
    assert rendered == ["a"]
    _, rendered = _render(root, fake_render, pix_fmt="yuv444p")
    assert rendered == []


def test_compile_and_render_wall_times_are_recorded_per_shot(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    report, _ = _render(root, fake_render)
    for o in report.outcomes:
        assert o.compile_s is not None and o.compile_s > 0
        assert o.key_s is not None and o.key_s >= o.compile_s
        assert o.render_s is not None and o.render_s >= 0
    report, _ = _render(root, fake_render)
    for o in report.outcomes:
        assert o.render_s is None and o.cached_render_s is not None
    table = report.timing_table()
    assert table.splitlines()[0].startswith("| shot | status | compile s")
    # ...and on the entry itself, beside the named key parts.
    store = load(root).mall["shot_cache"]
    rec = store[report.outcomes[0].key]
    assert {"compile_s", "render_s", "key_s"} <= set(rec.timings)
    core_parts = {"compiled", "textures", "easings", "audio", "runtime", "code", "knobs",
                  "environment", "project", "renderer", "vocabulary"}
    # A loaded genre that registered runtime scripts (the cut-out mouth and eye) adds its
    # staged code as one more named part.
    assert core_parts <= set(rec.inputs) <= core_parts | {"runtime_extensions"}


def test_force_render_renders_every_shot_and_no_cache_writes_nothing(tmp_path, fake_render):
    root = _project(tmp_path, _shot("a", 10.0))
    _render(root, fake_render)
    _, rendered = _render(root, fake_render, force_render=True)
    assert rendered == ["a"]

    root2 = _project(tmp_path / "two", _shot("a", 10.0))
    from an.render import render_project

    render_project(root2, incremental=False)
    assert list(load(root2).mall["shot_cache"]) == []


def test_iterate_no_longer_deletes_from_the_shots_store():
    """Decision 6: invalidation is by digest. The deletion was inert (nothing
    read the store) and is gone; `affected_shots` is recorded, never acted on."""
    import inspect

    from an import iterate

    src = inspect.getsource(iterate.iterate)
    assert 'del project.mall["shots"]' not in src


# -----------------------------------------------------------------------------
# The engine and the record, without a project
# -----------------------------------------------------------------------------


def _Named():
    """The real cut-out renderer: the keyer is bound to its class (review S4)."""
    from an.adapters.cutout.render import CutoutRenderer

    return CutoutRenderer()


def test_an_assembled_film_reuses_a_shot_only_with_its_frames(tmp_path):
    """A transition or a sound layer builds the film from frames, which an mp4
    cannot give back losslessly, so the frames are an entry of their own."""
    import an.adapters  # noqa: F401 — registers the cut-out keyer

    store = in_memory_shot_cache_store()
    ctx = RenderContext(mall={"audio": {}}, work_dir=tmp_path, fps=_FPS, resolution=(160, 120))
    shot = _shot("a", 10.0)
    fake = _FakeCutoutRender()

    engine = ShotCache(store, environment=_env(), cache_frames=True)
    engine.begin({})
    plan = engine.plan(shot, _Named(), ctx, needs_frames=False)
    engine.record(plan, fake(None, shot, ctx), render_s=0.5)

    engine.begin({})
    assert engine.plan(shot, _Named(), ctx, needs_frames=False).cached is not None
    framed = engine.plan(shot, _Named(), ctx, needs_frames=True)
    assert framed.cached is None and "frames" in framed.reason
    result = fake(None, shot, ctx)
    engine.record(framed, result, render_s=0.5)

    engine.begin({})
    again = engine.plan(shot, _Named(), ctx, needs_frames=True)
    assert again.cached is not None
    got = [p.read_bytes() for p in again.cached.frame_manifest]
    assert got == [p.read_bytes() for p in result.frame_manifest]
    assert again.cached.duration == shot.duration


def test_an_entry_is_a_lacing_artifact_with_its_inputs_as_provenance(tmp_path):
    from lacing import Artifact

    import an.adapters  # noqa: F401

    store = in_memory_shot_cache_store()
    ctx = RenderContext(mall={}, work_dir=tmp_path, fps=_FPS, resolution=(160, 120))
    shot = _shot("a", 10.0)
    engine = ShotCache(store, environment=_env())
    engine.begin({})
    plan = engine.plan(shot, _Named(), ctx)
    result = _FakeCutoutRender()(None, shot, ctx)
    engine.record(plan, result, render_s=0.25)
    rec = store[plan.key]
    assert isinstance(rec, Artifact)
    assert rec.asset_id == __import__("hashlib").sha256(result.mp4_path.read_bytes()).hexdigest()
    assert rec.kind == "video" and rec.shot_id == "a" and rec.shot_key == plan.key
    assert set(str(d) for d in rec.provenance.was_derived_from) <= set(plan.inputs.values())
    assert rec.timings["render_s"] == 0.25


def test_a_renderer_with_no_keyer_is_never_cached(tmp_path):
    class _Opaque:
        name = "opaque-backend"

    engine = ShotCache(in_memory_shot_cache_store(), environment=_env())
    engine.begin({})
    plan = engine.plan(_shot("a", 1.0), _Opaque(), RenderContext(mall={}, work_dir=tmp_path))
    assert plan.key is None and "no shot keyer" in plan.reason


def test_the_key_moves_with_an_easing_version(monkeypatch):
    """an#239 item 1: compiled keyframes carry bare easing names, so a v2 of a
    curve must reach the key some other way."""
    from dataclasses import replace

    from an.adapters.cutout.cache_key import easing_versions
    from an.timing import easing as easing_mod

    doc = {"animations": {"x": {"channels": [{"keyframes": [{"easing": "ease_in_out"}]}]}}}
    before = easing_versions(doc)
    entry = easing_mod.easing_entry("ease_in_out")
    monkeypatch.setitem(easing_mod._REGISTRY, "ease_in_out", replace(entry, version=entry.version + 1))
    assert easing_versions(doc) != before


def test_the_keyer_compiles_exactly_what_the_renderer_compiles(tmp_path, monkeypatch):
    """The drift guard: `compiled_document` and `CutoutRenderer.render` must
    pass `compile_shot` the same arguments, or a knob would reach the picture
    without reaching the key."""
    import sys
    import types

    from an.adapters.cutout import cache_key
    from an.adapters.cutout import compile as compile_mod
    from an.adapters.cutout import render as render_mod
    from an.styles import StylePack

    calls = []

    class _Stop(Exception):
        pass

    def spy(shot, mall=None, **kw):
        calls.append((shot, mall, kw))
        raise _Stop

    monkeypatch.setattr(render_mod, "compile_shot", spy)
    monkeypatch.setattr(compile_mod, "compile_shot", spy)
    monkeypatch.setattr(render_mod, "_ensure_ffmpeg_available", lambda: None)
    fake_pw = types.ModuleType("playwright.sync_api")
    fake_pw.sync_playwright = None
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_pw)

    ctx = RenderContext(
        mall={"x": {}}, work_dir=tmp_path, fps=23.976, resolution=(200, 100),
        strict_assets=True, step_hz=8.0, default_easing="linear",
        style_pack=StylePack(name="p"),
    )
    shot = _shot("a", 1.0)
    for call in (lambda: render_mod.CutoutRenderer().render(shot, ctx),
                 lambda: cache_key.compiled_document(shot, ctx)):
        with pytest.raises(_Stop):
            call()
    (s1, m1, kw1), (s2, m2, kw2) = calls
    assert s1 is s2 and m1 is m2 and kw1 == kw2


@pytest.mark.genre("cutout_animation")
def test_the_project_digest_covers_sidecar_art_not_only_the_mapping(tmp_path):
    root = init(tmp_path / "p")
    from cutan.characters.factory import new_character

    new_character(root / "assets" / "characters", name="amy", use_dicebear=False)
    mall = load(root).mall
    before = project_assets_digest(mall)
    part = sorted((root / "assets" / "characters" / "amy" / "parts").glob("*.svg"))[0]
    st = part.stat()
    part.write_bytes(part.read_bytes() + b"\n")
    os.utime(part, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert project_assets_digest(mall) != before
    # An OS's folder metadata is not an asset.
    (root / "assets" / "characters" / ".DS_Store").write_bytes(b"x")
    after = project_assets_digest(mall)
    (root / "assets" / "characters" / ".DS_Store").write_bytes(b"y")
    assert project_assets_digest(mall) == after


def test_resolve_incremental_refuses_a_non_engine():
    with pytest.raises(TypeError, match="IncrementalEngine"):
        resolve_incremental("yes")
    assert len(compose_shot_key({"a": "b"})) == 64


# -----------------------------------------------------------------------------
# End to end, with a browser
# -----------------------------------------------------------------------------


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_real_second_render_reuses_both_shots_byte_for_byte(tmp_path):
    from an.render import render_project

    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 20.0))
    first = ShotCache()
    out = render_project(root, incremental=first)
    first_bytes = out.read_bytes()
    shots_before = {k: load(root).mall["shots"][k] for k in ("a", "b")}
    assert first.report.rendered == ["a", "b"]

    second = ShotCache()
    out = render_project(root, incremental=second)
    assert second.report.reused == ["a", "b"]
    assert {k: load(root).mall["shots"][k] for k in ("a", "b")} == shots_before
    assert out.read_bytes() == first_bytes


# -----------------------------------------------------------------------------
# The an#243 review: blockers, stale-hit paths, and one test per key part
# -----------------------------------------------------------------------------


def _key(shot, ctx, *, engine=None, renderer=None):
    """The key a fresh engine computes for ``shot`` under ``ctx`` (no lookup)."""
    import an.adapters  # noqa: F401 — registers the cut-out keyer

    engine = engine or ShotCache(in_memory_shot_cache_store(), environment=_env())
    engine.begin({})
    return engine.plan(shot, renderer or _Named(), ctx, force=True).key


def _ctx(tmp_path, **kw):
    base = dict(mall={"audio": {}}, work_dir=tmp_path, fps=_FPS, resolution=(160, 120))
    base.update(kw)
    return RenderContext(**base)


@pytest.mark.parametrize("cache_frames", [False, True])
def test_two_identical_shots_render_warm_without_sharing_files(tmp_path, fake_render, cache_frames):
    """B1: identical shots share a KEY, never a materialisation directory."""
    root = _project(tmp_path, _shot("a", 10.0), _shot("b", 10.0))
    cache = lambda: ShotCache(environment=_env(), cache_frames=cache_frames)  # noqa: E731
    _render(root, fake_render, cache=cache())
    report, rendered = _render(root, fake_render, cache=cache())
    assert rendered == [] and report.reused == ["a", "b"]
    report, rendered = _render(root, fake_render, cache=cache())  # and again
    assert report.reused == ["a", "b"]
    assert {o.key for o in report.outcomes} == {report.outcomes[0].key}


def test_two_identical_shots_of_an_assembled_film_reuse_their_own_frames(tmp_path):
    import an.adapters  # noqa: F401

    store = in_memory_shot_cache_store()
    ctx = _ctx(tmp_path)
    a, b = _shot("a", 10.0), _shot("b", 10.0)
    fake = _FakeCutoutRender()
    engine = ShotCache(store, environment=_env(), cache_frames=True)
    engine.begin({})
    plan = engine.plan(a, _Named(), ctx, needs_frames=True)
    engine.record(plan, fake(None, a, ctx), render_s=0.1)
    engine.begin({})
    pa = engine.plan(a, _Named(), ctx, needs_frames=True)
    pb = engine.plan(b, _Named(), ctx, needs_frames=True)
    for p in (pa, pb):
        assert p.cached is not None
        assert p.cached.mp4_path.exists() and all(f.exists() for f in p.cached.frame_manifest)
    assert pa.cached.mp4_path != pb.cached.mp4_path
    assert pb.cached.provenance["shot_id"] == "b"  # N2: the shot it is FOR


def test_an_assembled_film_is_not_cached_unless_frames_are(tmp_path):
    import an.adapters  # noqa: F401

    engine = ShotCache(in_memory_shot_cache_store(), environment=_env())
    engine.begin({})
    plan = engine.plan(_shot("a", 1.0), _Named(), _ctx(tmp_path), needs_frames=True)
    assert plan.key is None and "frames not cached" in plan.reason


def test_cached_renders_each_work_in_their_own_directory(tmp_path, fake_render):
    """S1: two renders of one project must never write the same shot file."""
    from an.adapters.cutout.render import CutoutRenderer

    seen = []
    original = CutoutRenderer.render

    def spy(self, shot, ctx):
        seen.append(Path(ctx.work_dir))
        return original(self, shot, ctx)

    import pytest as _pytest  # noqa: F401

    mp = _pytest.MonkeyPatch()
    mp.setattr(CutoutRenderer, "render", spy)
    try:
        root = _project(tmp_path, _shot("a", 10.0))
        _render(root, fake_render, force_render=True)
        _render(root, fake_render, force_render=True)
    finally:
        mp.undo()
    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(p.parent.name == "runs" for p in seen)


def test_a_damaged_blob_is_a_miss_not_a_film(tmp_path, fake_render):
    """N1: the blob's id IS its sha256; a mismatch is a miss."""
    root = _project(tmp_path, _shot("a", 10.0))
    report, _ = _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    rec = store[report.outcomes[0].key]
    store.blob_path(rec.asset_id).write_bytes(b"garbage")
    report, rendered = _render(root, fake_render)
    assert rendered == ["a"] and "does not match" in report.outcomes[0].reason


def test_a_missing_blob_is_a_miss(tmp_path):
    import an.adapters  # noqa: F401

    store = in_memory_shot_cache_store()
    ctx = _ctx(tmp_path)
    shot = _shot("a", 1.0)
    engine = ShotCache(store, environment=_env())
    engine.begin({})
    plan = engine.plan(shot, _Named(), ctx)
    engine.record(plan, _FakeCutoutRender()(None, shot, ctx), render_s=0.1)
    del store.blobs[store[plan.key].asset_id]
    engine.begin({})
    assert engine.plan(shot, _Named(), ctx).cached is None


@pytest.mark.genre("cutout_animation")
def test_a_same_size_edit_with_its_mtime_restored_is_seen_in_one_process(tmp_path, fake_render):
    """S2: no (path, mtime, size) memo decides a key — through the texture
    digests (no project dependency) and through the project digest alike."""
    amy = AssetRef(kind="character", id="amy", store="characters", ref="amy")
    root = _project(tmp_path, _shot("with_amy", 10.0, entities=[amy]), character=True)
    modes = {
        "textures": lambda: ShotCache(environment=_env(), dependencies=None),
        "project": lambda: ShotCache(environment=_env()),
    }
    for make in modes.values():
        _render(root, fake_render, cache=make())
    part = sorted((root / "assets" / "characters" / "amy" / "parts").glob("*.svg"))[0]
    st = part.stat()
    data = part.read_bytes()
    i = data.index(b"#") + 1
    swapped = data[:i] + (b"0" if data[i:i + 1] != b"0" else b"1") + data[i + 1:]
    assert len(swapped) == len(data) and swapped != data
    part.write_bytes(swapped)
    os.utime(part, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert part.stat().st_mtime_ns == st.st_mtime_ns and part.stat().st_size == st.st_size
    for mode, make in modes.items():
        _, rendered = _render(root, fake_render, cache=make())
        assert rendered == ["with_amy"], mode


def test_a_subclass_borrowing_the_name_is_never_cached(tmp_path):
    """S4: the keyer describes ONE implementation."""
    from an.adapters.cutout.render import CutoutRenderer

    class Watermarked(CutoutRenderer):
        pass

    engine = ShotCache(in_memory_shot_cache_store(), environment=_env())
    engine.begin({})
    plan = engine.plan(_shot("a", 1.0), Watermarked(), _ctx(tmp_path))
    assert plan.key is None and "Watermarked" in plan.reason


def test_a_keyer_is_never_replaced_silently_and_parts_are_additive(tmp_path, monkeypatch):
    """S7: a second registration is refused; a part is added, and moves the key."""
    from an.build import keys

    entry = keys._KEYERS["cutout"]
    monkeypatch.setitem(keys._KEYERS, "cutout", keys._KeyerEntry(
        keyer=entry.keyer, environment=entry.environment,
        renderer_type=entry.renderer_type, parts=dict(entry.parts)))
    with pytest.raises(keys.ShotKeyerRegistrationError, match="already registered"):
        keys.register_shot_keyer("cutout", entry.keyer)
    shot, ctx = _shot("a", 1.0), _ctx(tmp_path)
    before = _key(shot, ctx)
    keys.register_shot_key_part("cutout", "demo_part", lambda shot, ctx: "v" * 64)
    assert _key(shot, ctx) != before
    with pytest.raises(keys.ShotKeyerRegistrationError):
        keys.register_shot_key_part("cutout", "demo_part", lambda shot, ctx: "w" * 64)
    # The keyer's identity is in the key: the same parts from another keyer
    # (a different implementation) never answer for the first one's entries.
    with_part = _key(shot, ctx)

    def another_keyer(shot, ctx):
        return entry.keyer(shot, ctx)

    keys.register_shot_keyer("cutout", another_keyer, environment=entry.environment,
                             renderer_type=entry.renderer_type, replace=True)
    assert _key(shot, ctx) != with_part


def test_the_render_path_code_is_in_the_key(tmp_path, monkeypatch):
    """B2: the Python half of the render reaches the key without a hand bump."""
    from an.adapters.cutout import cache_key

    shot, ctx = _shot("a", 1.0), _ctx(tmp_path)
    before = _key(shot, ctx)
    monkeypatch.setattr(cache_key, "render_code_digest", lambda: "c" * 64)
    assert _key(shot, ctx) != before


def test_the_render_path_walk_reaches_every_module_the_renderer_imports():
    """B2: a new helper imported by the render module cannot fall outside the code part."""
    import ast
    import importlib.util

    from an.adapters.cutout.cache_key import (
        RENDER_PATH_EXCLUDED,
        RENDER_PATH_ROOT,
        _module_imports,
        render_path_modules,
    )

    mods = render_path_modules()
    for must in ("an.adapters.cutout.render", "an.adapters.cutout.canvas_capture",
                 "an.adapters.cutout.supersample", "an.adapters.cutout.shutter",
                 "an.adapters.cutout.runtime_files", "an.base", "an.determinism"):
        assert must in mods
    src = Path(importlib.util.find_spec(RENDER_PATH_ROOT).origin).read_bytes()
    for name in _module_imports(ast.parse(src), RENDER_PATH_ROOT):
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            continue
        if spec is not None and spec.origin and spec.origin.endswith(".py"):
            assert name in mods or name in RENDER_PATH_EXCLUDED, name


def test_the_render_path_walk_reaches_what_the_frame_stage_runs():
    """an#247: the capture loop, the resolves and the mux live in the core and
    are reached from the old render module only through LIVE aliases, whose
    targets are strings. Every one of them, the frame stage the renderer's
    `render` comes from, and the engine's module must be in the code part."""
    from an._shims import forwarded_names
    from an.adapters.cutout import render
    from an.adapters.cutout.cache_key import render_path_modules, render_path_roots
    from an.engines.frame_stage import FrameStageRenderer

    mods = render_path_modules()
    renderer = render.CutoutRenderer()
    required = {
        FrameStageRenderer.__module__,
        type(renderer).__module__,
        type(renderer).render.__module__,
        type(renderer.engine).__module__,
        "an.engines.capture",
        "an.engines.protocol",
        "an.media.mp4",
        "an.media.frames",
        "an.media.supersample",
        "an.media.shutter",
        "an._shims",
    }
    for name in list(mods):
        try:
            module = __import__(name, fromlist=["_"])
        except ModuleNotFoundError:
            continue  # a keyed module of a genre package that needs an optional dependency (cutan.nw: nw)
        required |= {target for target, _ in forwarded_names(module).values()}
    missing = sorted(required - set(mods))
    assert not missing, f"render-path modules outside the code key: {missing}"
    assert set(render_path_roots()) <= set(mods)


def test_the_render_path_walk_follows_a_module_that_is_only_a_shim(tmp_path, monkeypatch):
    """an#247 PR B turns the old render module into a pure re-export shim: no
    `import` of the new home, only `forward_module_attributes(...)` with a
    string target. The walk must still reach the target."""
    from an.adapters.cutout.cache_key import render_path_modules

    (tmp_path / "an_pure_shim_probe.py").write_text(
        "from an._shims import forward_module_attributes\n"
        'forward_module_attributes(__name__, "an.media.mp4", ["DEFAULT_PIX_FMT"])\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    mods = render_path_modules("an_pure_shim_probe")
    assert {"an.media.mp4", "an.media.frames", "an._shims"} <= set(mods)


def test_the_code_digest_moves_when_a_source_byte_does(tmp_path):
    from an.adapters.cutout.cache_key import _source_facts

    f = tmp_path / "m.py"
    f.write_text("X = 1\n", encoding="utf-8")
    a = _source_facts(f, "an.m")[0]
    st = f.stat()
    f.write_text("X = 2\n", encoding="utf-8")
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))  # same size, same mtime
    assert _source_facts(f, "an.m")[0] != a


def test_the_impl_salt_is_in_the_key(monkeypatch):
    from an.build import keys

    before = keys.compose_shot_key({"a": "b"})
    monkeypatch.setattr(keys, "SHOT_KEY_IMPL_VERSION", keys.SHOT_KEY_IMPL_VERSION + 1)
    assert keys.compose_shot_key({"a": "b"}) != before


def test_the_runtime_is_in_the_key(tmp_path, monkeypatch):
    import an.bench.environment as env

    shot, ctx = _shot("a", 1.0), _ctx(tmp_path)
    before = _key(shot, ctx)
    monkeypatch.setattr(env, "runtime_sha256", lambda: "r" * 64)
    assert _key(shot, ctx) != before


def test_an_easing_version_reaches_the_key(tmp_path, monkeypatch):
    from dataclasses import replace

    from an.timing import easing as easing_mod

    shot, ctx = _shot("a", 1.0), _ctx(tmp_path)  # a tween: ease_in_out by default
    before = _key(shot, ctx)
    entry = easing_mod.easing_entry("ease_in_out")
    monkeypatch.setitem(easing_mod._REGISTRY, "ease_in_out", replace(entry, version=entry.version + 1))
    assert _key(shot, ctx) != before


def _speaking_shot(**line):
    from an.ir.schema import Dialogue

    kw = dict(speaker="c", text="hi", audio_ref="ref1", viseme_ref="vis1", start=0.2, duration=0.5)
    kw.update(line)
    return Shot(id="a", renderer="cutout", duration=1.0, dialogue=[Dialogue(**kw)])


@pytest.mark.parametrize(
    "change",
    ["bytes", "start", "audio_ref", "viseme_ref", "picture"],
)
def test_the_muxed_audio_is_in_the_key(tmp_path, change):
    from an.adapters.cutout.cache_key import muxed_audio

    audio = {"ref1": b"RIFF-one", "ref2": b"RIFF-one"}
    ctx = _ctx(tmp_path, mall={"audio": dict(audio)})
    base = muxed_audio(_speaking_shot(), ctx)
    if change == "bytes":
        other = muxed_audio(_speaking_shot(), _ctx(tmp_path, mall={"audio": {"ref1": b"RIFF-two"}}))
    elif change == "start":
        other = muxed_audio(_speaking_shot(start=0.4), ctx)
    elif change == "audio_ref":
        other = muxed_audio(_speaking_shot(audio_ref="ref2"), ctx)
    elif change == "viseme_ref":
        other = muxed_audio(_speaking_shot(viseme_ref="vis2"), ctx)
    else:
        other = muxed_audio(_speaking_shot(), _ctx(tmp_path, mall={"audio": dict(audio)}, fps=23.976))
    assert other != base


def test_a_resynthesised_line_rerenders_its_shot(tmp_path):
    """The audio part, through the key: new bytes under the same ref re-render."""
    shot = _speaking_shot()
    k1 = _key(shot, _ctx(tmp_path, mall={"audio": {"ref1": b"RIFF-one"}}))
    k2 = _key(shot, _ctx(tmp_path, mall={"audio": {"ref1": b"RIFF-two"}}))
    k3 = _key(_speaking_shot(start=0.6), _ctx(tmp_path, mall={"audio": {"ref1": b"RIFF-one"}}))
    assert len({k1, k2, k3}) == 3


_KNOB_CHANGES = {
    "supersample": dict(supersample=2),
    "capture": dict(capture="screenshot"),
    "frame_samples": dict(frame_samples=tuple((i / _FPS + 0.01,) for i in range(_FPS))),
    "fps": dict(fps=12.5),
    "resolution": dict(resolution=(200, 120)),
    "strict_assets": dict(strict_assets=True),
    "extra": dict(extra={"x": 1}),
    "pix_fmt": dict(pix_fmt="yuv444p"),
    "step_hz": dict(step_hz=6.0),
}


@pytest.mark.parametrize("knob", sorted(_KNOB_CHANGES))
def test_every_render_knob_is_in_the_key(tmp_path, knob):
    shot = _shot("a", 1.0)
    assert _key(shot, _ctx(tmp_path, **_KNOB_CHANGES[knob])) != _key(shot, _ctx(tmp_path))


def test_a_non_integer_fps_that_compiles_identically_still_moves_the_key(tmp_path):
    """23.976 and 24 compile to the same document (its grid is integral)."""
    from an.adapters.cutout.cache_key import compiled_document

    shot = _shot("a", 1.0)
    a, b = _ctx(tmp_path, fps=24), _ctx(tmp_path, fps=23.976)
    assert compiled_document(shot, a) == compiled_document(shot, b)
    assert _key(shot, a) != _key(shot, b)


@pytest.mark.parametrize("name", ["DETERMINISTIC_X264_ARGS", "DETERMINISTIC_CHROMIUM_ARGS"])
def test_the_pinned_argv_is_in_the_key(tmp_path, monkeypatch, name):
    from an.adapters.cutout import render as render_mod

    shot, ctx = _shot("a", 1.0), _ctx(tmp_path)
    before = _key(shot, ctx)
    monkeypatch.setattr(render_mod, name, (*getattr(render_mod, name), "--lever"))
    assert _key(shot, ctx) != before


def test_svg_art_that_draws_text_keys_on_the_machines_fonts(tmp_path, monkeypatch):
    """S3: Chromium draws an SVG <text> with system fonts."""
    from an.adapters.cutout import cache_key
    from an.adapters.cutout.serialize import AssetJSON, AssetsJSON, CutoutSceneJSON, NodeJSON, TimelineJSON

    root = tmp_path / "characters"
    (root / "amy" / "parts").mkdir(parents=True)
    (root / "amy" / "parts" / "sign.svg").write_text("<svg><text>HI</text></svg>", encoding="utf-8")
    (root / "amy" / "parts" / "arm.svg").write_text("<svg><rect/></svg>", encoding="utf-8")

    class _Store:
        _root = root

    def doc(*names):
        return CutoutSceneJSON(
            scene=NodeJSON(name="root"), timeline=TimelineJSON(duration=1.0, tracks=[]),
            assets=AssetsJSON(textures={n: AssetJSON(src=f"characters/amy/parts/{n}.svg") for n in names}),
        )

    digests = cache_key.texture_digests(doc("sign", "arm"), {"characters": _Store()})
    assert digests["sign"].endswith(":text") and not digests["arm"].endswith(":text")
    monkeypatch.setattr(cache_key, "_FONTS", {})
    assert len(cache_key.system_fonts_digest()) == 64


@pytest.mark.genre("cutout_animation")
def test_compile_warnings_are_replayed_on_a_reused_shot(tmp_path, fake_render):
    """an#33: a stand-in must stay audible when its shot is reused."""
    from an.adapters.cutout.compile import CutoutCompileWarning

    ghost = AssetRef(kind="character", id="ghost", store="characters", ref="ghost")
    root = _project(tmp_path, _shot("a", 10.0, entities=[ghost]))
    import warnings

    with warnings.catch_warnings():
        # On a miss the RENDERER compiles and warns; the stand-in render here
        # does not compile, so only the reuse below can warn.
        warnings.simplefilter("ignore")
        _render(root, fake_render)
    with pytest.warns(CutoutCompileWarning):
        report, rendered = _render(root, fake_render)
    assert rendered == [] and report.reused == ["a"]


def test_the_environment_is_memoised_per_renderer(monkeypatch):
    from an.build import keys, shot_cache

    monkeypatch.setattr(shot_cache, "_ENVIRONMENTS", {})
    for name, record in (("probe-a", {"m": 1}), ("probe-b", {"m": 2})):
        monkeypatch.setitem(keys._KEYERS, name, keys._KeyerEntry(
            keyer=lambda shot, ctx: None, environment=lambda r=record: r))
    assert shot_cache.default_environment_digest("probe-a") != shot_cache.default_environment_digest("probe-b")


@pytest.mark.genre("cutout_animation")
def test_measuring_callers_render_cold_explicitly(monkeypatch, tmp_path):
    """The ruling on `render()`: the bench says `incremental=False` itself."""
    import an.render as render_mod
    from an.bench import capture as capture_mod
    from an.bench.corpus import DFLT_FIXTURES
    from an.bench.paths import repo_root

    seen = {}

    class _Stop(Exception):
        pass

    def spy(project, **kw):
        seen.update(kw)
        raise _Stop

    monkeypatch.setattr(render_mod, "render", spy)
    name = sorted(DFLT_FIXTURES)[0]
    with pytest.raises(_Stop):
        capture_mod.capture_fixture(name, DFLT_FIXTURES[name], repo_root=repo_root(), keep_render=tmp_path / "k")
    assert seen["incremental"] is False
    # The cross-arch capture and the demo gallery are scripts, not modules:
    # their calls are checked in the source.
    repo = repo_root()
    crossarch = (repo / "misc" / "bench" / "crossarch.py").read_text(encoding="utf-8")
    assert "render(project, **CAPTURE_RENDER_KWARGS, incremental=False)" in crossarch


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_the_real_environment_probe_names_its_builds():
    from an.adapters.cutout.cache_key import cutout_environment

    env = cutout_environment()
    assert env["browser"].get("chromium_build"), env["browser"]
    assert env["x264"] and env["x264"].startswith("core ")
    assert "libavcodec" in env["ffmpeg"]["version"]


def test_the_lockfile_name_is_the_asset_librarys_own():
    """One fact, two places until an#240 registers the lockfile in the mall."""
    from an.build import PROJECT_ROOT_FILES
    from an.library.lock import LOCKFILE_NAME

    assert LOCKFILE_NAME in PROJECT_ROOT_FILES


# -----------------------------------------------------------------------------
# Round 2 of the an#243 review
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "duration,fps_a,fps_b", [(2.5, 23.6, 24.4), (33.3333, 29.97, 30.0)]
)
def test_two_rates_that_compile_and_mux_alike_still_key_apart(tmp_path, duration, fps_a, fps_b):
    """R2-3: the document's grid is integral and `picture_seconds` can agree
    (59/23.6 == 61/24.4), yet the renders have different frame counts — only
    the `fps` knob tells them apart."""
    from an.adapters.cutout.cache_key import compiled_document, muxed_audio

    shot = Shot(id="a", renderer="cutout", duration=duration,
                actions=[tween("root", "x", to=10.0, duration=1.0)])
    a, b = _ctx(tmp_path, fps=fps_a), _ctx(tmp_path, fps=fps_b)
    assert round(duration * fps_a) != round(duration * fps_b)
    assert compiled_document(shot, a) == compiled_document(shot, b)
    ma, mb = muxed_audio(shot, a), muxed_audio(shot, b)
    assert ma["lines"] == mb["lines"]
    assert ma["picture_seconds"] == pytest.approx(mb["picture_seconds"], abs=1e-3)
    assert _key(shot, a) != _key(shot, b)


@pytest.mark.genre("cutout_animation")
def test_svg_text_puts_the_machines_fonts_in_the_key(tmp_path, monkeypatch):
    """R2-3: a part drawing `<text>` keys on the font set; one without does not."""
    from an.adapters.cutout import cache_key

    amy = AssetRef(kind="character", id="amy", store="characters", ref="amy")
    root = _project(tmp_path, _shot("a", 10.0, entities=[amy]), character=True)
    mall = load(root).mall
    ctx = _ctx(tmp_path, mall=mall)
    shot = _shot("a", 10.0, entities=[amy])

    monkeypatch.setattr(cache_key, "system_fonts_digest", lambda: "1" * 64)
    plain_1 = _key(shot, ctx)
    monkeypatch.setattr(cache_key, "system_fonts_digest", lambda: "2" * 64)
    assert _key(shot, ctx) == plain_1  # no <text>: the font set is irrelevant

    part = sorted((root / "assets" / "characters" / "amy" / "parts").glob("*.svg"))[0]
    part.write_text(part.read_text(encoding="utf-8").replace("</svg>", "<text>HI</text></svg>"), encoding="utf-8")
    with_text_2 = _key(shot, ctx)
    monkeypatch.setattr(cache_key, "system_fonts_digest", lambda: "1" * 64)
    assert _key(shot, ctx) != with_text_2  # a font change moves the key


def test_the_walk_sees_function_local_imports():
    import ast

    from an.adapters.cutout.cache_key import _module_imports

    src = "def f():\n    from an.helper_mod import thing\n    import an.other_mod\n"
    found = _module_imports(ast.parse(src), "an.adapters.cutout.render")
    assert {"an.helper_mod", "an.other_mod"} <= found


def test_frames_are_never_stored_unless_asked(tmp_path):
    import an.adapters  # noqa: F401
    from an.build.shot_cache import FRAMES_NOT_CACHED

    store = in_memory_shot_cache_store()
    ctx, shot = _ctx(tmp_path), _shot("a", 1.0)
    engine = ShotCache(store, environment=_env())
    engine.begin({})
    plan = engine.plan(shot, _Named(), ctx, needs_frames=True)
    engine.record(plan, _FakeCutoutRender()(None, shot, ctx), render_s=0.1)
    assert plan.reason == FRAMES_NOT_CACHED
    assert not any(str(k).endswith(".frames") for k in store)
    assert "pass --cache-frames" in engine.finish().summary()


def test_the_cli_offers_cache_frames(monkeypatch):
    from an import orchestrate, tools

    seen = {}
    monkeypatch.setattr(orchestrate, "_render_project", lambda d, **kw: seen.update(kw) or Path("o.mp4"))
    tools.render("proj", cache_frames=True)
    assert seen["incremental"].cache_frames is True
    tools.render("proj")
    assert seen["incremental"].cache_frames is False


def test_finished_runs_are_removed_promptly_and_a_live_one_is_kept(tmp_path, fake_render):
    """R2-2: no run's frames linger for hours; a run in progress is untouched."""
    root = _project(tmp_path, _shot("a", 10.0))
    runs = root / ".an" / "render_work" / "runs"
    live = runs / "someone_else_rendering"
    live.mkdir(parents=True)
    (live / ".live").write_text(str(os.getppid()), encoding="utf-8")  # a live pid
    for x in (11.0, 12.0, 13.0):
        _set_shots(root, _shot("a", x))
        _render(root, fake_render)
    left = sorted(p.name for p in runs.iterdir())
    assert len(left) == 2 and "someone_else_rendering" in left
    (latest,) = [p for p in runs.iterdir() if p != live]
    assert (latest / ".done").exists()


def test_reregistering_the_same_keyer_is_idempotent(monkeypatch):
    """R2-4: `importlib.reload` / autoreload re-executes the registration."""
    from an.build import keys

    entry = keys._KEYERS["cutout"]
    monkeypatch.setitem(keys._KEYERS, "cutout", entry)
    keys.register_shot_keyer("cutout", entry.keyer, environment=entry.environment,
                             renderer_type=entry.renderer_type)
    assert keys._KEYERS["cutout"].identity() == entry.identity()


def test_record_itself_refuses_frames_unless_asked(tmp_path):
    """Defence in depth: even a keyed plan that needs frames (built by another
    engine, or a later plan path) stores none when `cache_frames` is off."""
    import an.adapters  # noqa: F401
    from an.build import ShotPlan

    store = in_memory_shot_cache_store()
    ctx, shot = _ctx(tmp_path), _shot("a", 1.0)
    engine = ShotCache(store, environment=_env())
    engine.begin({})
    plan = ShotPlan("a", "cutout", key="k" * 64, inputs={}, needs_frames=True)
    engine.record(plan, _FakeCutoutRender()(None, shot, ctx), render_s=0.1)
    assert "k" * 64 in store and ("k" * 64) + ".frames" not in store
