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
        from an.characters.factory import new_character

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


def test_without_the_project_fallback_only_the_drawing_shot_rerenders(tmp_path, fake_render):
    """The texture digests alone are precise: with decision 3's whole-project
    dependency switched off, an SVG edit re-renders only the shot whose
    document stages that file — the behaviour read recording will make the
    default."""
    amy = AssetRef(kind="character", id="amy", store="characters", ref="amy")
    root = _project(
        tmp_path, _shot("with_amy", 10.0, entities=[amy]), _shot("empty", 20.0), character=True
    )
    precise = lambda: ShotCache(environment=_env(), project_digest=False)  # noqa: E731
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
    assert {"compiled", "textures", "easings", "audio", "runtime", "knobs",
            "environment", "project", "renderer"} == set(rec.inputs)


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


class _Named:
    name = "cutout"


def test_an_assembled_film_reuses_a_shot_only_with_its_frames(tmp_path):
    """A transition or a sound layer builds the film from frames, which an mp4
    cannot give back losslessly, so the frames are an entry of their own."""
    import an.adapters  # noqa: F401 — registers the cut-out keyer

    store = in_memory_shot_cache_store()
    ctx = RenderContext(mall={"audio": {}}, work_dir=tmp_path, fps=_FPS, resolution=(160, 120))
    shot = _shot("a", 10.0)
    fake = _FakeCutoutRender()

    engine = ShotCache(store, environment=_env())
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


def test_the_project_digest_covers_sidecar_art_not_only_the_mapping(tmp_path):
    root = init(tmp_path / "p")
    from an.characters.factory import new_character

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
