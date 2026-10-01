"""The Manim renderer: opaque-source shots through manimkit (an#279).

Three tiers, by what the machine has:

- **no dependency**: options, quality, locating findings in the source, the
  declared-duration rule, validation, capabilities, the keyer registration,
  the prose-preserving duration patch;
- **ffmpeg** (``ffmpeg`` marker): the whole path — measurement, the derived
  stores, conform, hold, mux, the shot and picture caches, film assembly with a
  dissolve and narration, findings routed to validate/orchestrate/MCP — with
  manimkit's ``render_check`` replaced by a FAKE that writes a real mp4 with
  ffmpeg, so everything ``an`` does around Manim runs without Manim installed;
- **Manim installed** (skipped otherwise; CI does not install it): the real
  render, a layout warning located at its line, and — with a browser — the
  proof film mixing a Manim shot and a stage shot.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from an.adapters._base import ClockOwningRenderer, RenderContext
from an.adapters import manim_adapter as ma
from an.adapters.manim_adapter import (
    ManimRenderError,
    ManimRenderer,
    ManimShotSpec,
    SourceFile,
    choose_quality,
    report_findings,
)
from an.ir.schema import Dialogue, Meta, SceneIR, Shot, Transition
from an.measurements import MeasurementError, ShotFindingWarning, declared_duration
from an.stores import build_project_mall

HAS_MANIM = all(importlib.util.find_spec(m) is not None for m in ("manim", "manimkit"))

LINEAR = b"""from manim import *

class Chart(Scene):
    def construct(self):
        t = Text("hi")
        self.play(Write(t))
        self.wait(0.5)
"""
#: A scene that reads a file beside it — the fake renderer makes the file's
#: number the video's length, so a staged, keyed read is observable.
READS_DATA = b"""from manim import *

class Chart(Scene):
    def construct(self):
        seconds = float(open("data/seconds.txt").read())
        self.wait(seconds)
"""
SCENE_MD_PROSE = "Director's notes: keep it calm.  <!-- TODO: colours -->"
LONG_LINE = "This narration line runs well past the end of the very short scene it is laid under."


def _src(key: str, data: bytes, **more: bytes) -> SourceFile:
    return SourceFile(key, f"{key}.py", {f"{key}.py": data, **more}, f"assets/sources/{key}.py")


# -----------------------------------------------------------------------------
# No dependency
# -----------------------------------------------------------------------------


def test_options_are_checked_with_the_fix_in_the_message():
    with pytest.raises(ManimRenderError, match="options.source"):
        ManimShotSpec.from_options({})
    with pytest.raises(ManimRenderError, match="Scene class"):
        ManimShotSpec.from_options({"source": "s", "scene": "not a class"})
    with pytest.raises(ManimRenderError, match="#rrggbb"):
        ManimShotSpec.from_options({"source": "s", "background": "black"})
    assert ManimShotSpec.from_options({"source": "s", "quality": "h"}).quality == "h"


def test_quality_is_the_smallest_preset_at_least_as_tall_and_fast_as_the_film():
    assert choose_quality(fps=30, resolution=(640, 360)) == "m"  # l is only 15 fps
    assert choose_quality(fps=24, resolution=(1280, 720)) == "m"
    assert choose_quality(fps=30, resolution=(1920, 1080)) == "h"


def test_a_finding_is_located_at_the_play_it_was_checked_after():
    report = SimpleNamespace(
        ok=True,
        lint=["line 5: something old"],
        timeline=[{"t0": 0.0, "t1": 1.0, "what": "Write"}, {"t0": 1.0, "t1": 1.5, "what": "wait"}],
        layout_warnings=[{"t": 1.0, "kind": "cut-off", "message": "Text('hi') is cut off"}],
    )
    found = report_findings(report, _src("chart", LINEAR), scene="Chart")
    assert [(f.severity, f.location) for f in found] == [
        ("warning", "assets/sources/chart.py:6"),
        ("warning", "assets/sources/chart.py:5"),
    ]
    assert found[0].ir_path == "options/source"  # shot-relative; the core addresses it


def test_non_linear_beats_are_located_at_construct_never_guessed():
    looped = b"""class S(Scene):
    def construct(self):
        for i in range(3):
            self.play(Write(Text(str(i))))
"""
    report = SimpleNamespace(
        ok=True, lint=[], timeline=[{"t0": 0, "t1": 1}] * 3,
        layout_warnings=[{"t": 1.0, "kind": "overlap", "message": "m"}],
    )  # fmt: skip
    (f,) = report_findings(report, _src("s", looped))
    assert f.location == "assets/sources/s.py:2"


def test_a_failed_render_is_an_error_at_the_users_last_line():
    report = SimpleNamespace(
        ok=False, lint=[], timeline=[], layout_warnings=[], error="NameError: x",
        error_kind="python", user_frames=["line 5: t = Text(x)"], hint="", latex_log="",
    )  # fmt: skip
    (f,) = report_findings(report, _src("c", LINEAR))
    assert (f.severity, f.location) == ("error", "assets/sources/c.py:5")
    assert "NameError" in f.description


def test_a_file_read_the_cache_cannot_see_is_a_finding_at_its_line():
    code = b"from manim import *\nlogo = ImageMobject('/Users/someone/logo.png')\nok = 'data/x.csv'\n"
    report = SimpleNamespace(ok=True, lint=[], timeline=[], layout_warnings=[])
    found = report_findings(report, _src("c", code, **{"data/x.csv": b"1"}))
    assert [(f.location, "logo.png" in f.description) for f in found] == [
        ("assets/sources/c.py:2", True)
    ]


def test_the_declared_duration_rule():
    """The schema's placeholder is not a declaration; an explicit value is."""
    assert declared_duration(Shot(id="a", renderer="manim")) is None
    assert declared_duration(Shot(id="a", renderer="manim", duration=4.0)) == 4.0


def test_the_renderer_owns_its_clock_and_says_so_by_its_member():
    from an.capabilities.subjects import engine_affordances

    assert isinstance(ManimRenderer(), ClockOwningRenderer)
    assert "engine.measure_duration" in engine_affordances(ManimRenderer())
    assert "engine.measure_duration" not in engine_affordances("cutout")


def test_env_manim_needs_both_packages():
    from an.capabilities.subjects import environment_affordances

    def probe(modules):
        return {"which": set(), "env": set(), "modules": set(modules), "browsers": False}

    assert "env.manim" not in environment_affordances(probe=probe({"manim"}))
    assert "env.manim" not in environment_affordances(probe=probe({"manimkit"}))
    assert "env.manim" in environment_affordances(probe=probe({"manim", "manimkit"}))


def test_requirements_derive_latex_from_the_source():
    assert ma.source_requirements("Text('a')") == ("env.manim",)
    assert ma.source_requirements("MathTex(r'e^{i\\pi}')") == ("env.manim", "env.latex")


def test_the_keyer_is_registered_for_this_class_only():
    from an.build.keys import shot_keyer_for

    assert shot_keyer_for(ManimRenderer()) is not None

    class Watermarked(ManimRenderer):
        pass

    assert shot_keyer_for(Watermarked()) is None


def test_validate_names_a_malformed_manim_shot():
    from an.ir.validate import validate_semantic

    scene = SceneIR(
        timeline=[Shot(id="m", renderer="manim", options={"scene": "X", "colour": 1})]
    )
    report = validate_semantic(scene)
    errors = [f for f in report.findings if f.severity == "error"]
    assert any("options.source" in f.description and f.ir_path == "timeline/0/options" for f in errors)


def test_the_duration_patch_keeps_every_other_byte_of_scene_md(tmp_path):
    from an.stores.scenes import ScenesStore

    store = ScenesStore(tmp_path)
    store["main"] = SceneIR(timeline=[Shot(id="a", renderer="manim", options={"source": "a"})])
    md = (
        store.md_path.read_text(encoding="utf-8")
        .replace("## Shot a (manim)\n", f"## Shot a (manim)\n\n{SCENE_MD_PROSE}\n")
        .replace("duration: 5.0\n", "duration: 5.0  # the placeholder\n")
    )
    store.md_path.write_text(md, encoding="utf-8")
    store.patch_shot_durations({"a": 3.25})
    after = store.md_path.read_text(encoding="utf-8")
    assert SCENE_MD_PROSE in after
    assert [ln for ln in after.splitlines() if ln not in md.splitlines()] == [
        "duration: 3.25  # the placeholder"
    ]
    assert store["main"].timeline[0].duration == 3.25


# -----------------------------------------------------------------------------
# ffmpeg: everything around Manim, with a fake render_check
# -----------------------------------------------------------------------------


class FakeRenderCheck:
    """manimkit's ``render_check``, played by ffmpeg: a 16:9 test pattern at the
    preset's rate, ``seconds`` long — or as long as the number in
    ``data/seconds.txt`` beside the scene file, when that file is there."""

    def __init__(self, seconds: float = 2.0) -> None:
        self.seconds = seconds
        self.calls = 0

    def __call__(self, file, scene=None, *, quality, n_frames, out_dir, no_latex, timeout):
        self.calls += 1
        seconds = self.seconds
        data = Path(file).parent / "data" / "seconds.txt"
        if data.is_file():
            seconds = float(data.read_text(encoding="utf-8"))
        q = ma.QUALITY_PRESETS[quality]
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        video, sheet = out_dir / "scene.mp4", out_dir / "sheet.png"
        for args in (
            ["-f", "lavfi", "-i", f"testsrc=size={q.width}x{q.height}:rate={q.fps}:duration={seconds}",
             "-pix_fmt", "yuv420p", str(video)],
            ["-f", "lavfi", "-i", "color=c=gray:s=96x54", "-frames:v", "1", str(sheet)],
        ):  # fmt: skip
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)
        return SimpleNamespace(
            ok=True, video=str(video), contact_sheet=str(sheet), duration=seconds,
            timeline=[{"t0": 0.0, "t1": seconds, "what": "Write"}],
            layout_warnings=[{"t": seconds, "kind": "cut-off", "message": "Text cut"}],
            lint=[], error=None, error_kind=None, user_frames=[],
        )  # fmt: skip


@pytest.fixture
def fake(monkeypatch):
    """The fake renderer behind the REGISTERED instance; the Manim version (a
    key input) pinned, so this runs where Manim is not installed."""
    monkeypatch.setattr(ma, "manim_version", lambda: "0.0.0-fake")
    check = FakeRenderCheck(seconds=2.0)
    monkeypatch.setattr(ma, "_manimkit_render_check", lambda: check)
    return check


def _ctx(mall, tmp_path, **kw):
    kw.setdefault("fps", 30)
    return RenderContext(mall=mall, work_dir=tmp_path / "work", resolution=(640, 360), **kw)


def _project(root: Path, *, shots: list[Shot], prose: bool = True, **meta) -> Path:
    from an.project import init

    init(root)
    mall = build_project_mall(root)
    mall["sources"]["a"] = LINEAR
    mall["sources"]["b"] = LINEAR + b"# the second scene\n"
    meta = {"title": "t", "fps": 30, "resolution": {"width": 640, "height": 360}, **meta}
    mall["scenes"]["main"] = SceneIR(meta=Meta(**meta), timeline=shots)
    if prose:  # an author's words and comments, which no render may touch
        md = (root / "scene.md").read_text(encoding="utf-8")
        md = md.replace("## Shot a (manim)\n", f"## Shot a (manim)\n\n{SCENE_MD_PROSE}\n", 1)
        (root / "scene.md").write_text(md, encoding="utf-8")
    return root


def _render(root: Path, **kwargs):
    from an.render import render_project

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = render_project(root, **kwargs)
    return out, [w for w in caught if issubclass(w.category, ShotFindingWarning)]


def _frames(path: Path) -> int:
    return int(
        subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
             "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )  # fmt: skip


def _audio_seconds(path: Path) -> float:
    return float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )  # fmt: skip


@pytest.mark.ffmpeg
def test_a_render_never_rewrites_the_authors_scene(tmp_path, fake):
    """H1: the measurement is derived data; scene.md and scene.json keep what the author wrote."""
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    md, js = (root / "scene.md").read_bytes(), (root / "ir" / "scene.json").read_bytes()
    out, _ = _render(root)
    assert (root / "scene.md").read_bytes() == md and (root / "ir" / "scene.json").read_bytes() == js
    assert _frames(out) == 60  # laid out at the MEASURED 2.0 s, not the 5.0 s placeholder
    assert len(list(build_project_mall(root)["measurements"])) == 1


@pytest.mark.ffmpeg
def test_fps_alternation_neither_runs_manim_again_nor_touches_the_scene(tmp_path, fake):
    """H2: the picture key is what decides Manim's output — not the film's fps."""
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    md = (root / "scene.md").read_bytes()
    frames = [_frames(_render(root, fps=fps)[0]) for fps in (None, 24, None, 24)]
    assert frames == [60, 48, 60, 48]
    assert fake.calls == 1
    assert (root / "scene.md").read_bytes() == md


@pytest.mark.ffmpeg
def test_narration_longer_than_the_picture_holds_the_last_frame_and_says_so(tmp_path, fake):
    """H3: never cut silently — held with a warning, or refused under strict."""
    fake.seconds = 1.0
    shot = Shot(
        id="a", renderer="manim", options={"source": "a"},
        dialogue=[Dialogue(speaker="narrator", text=LONG_LINE)],
    )  # fmt: skip
    root = _project(tmp_path / "p", shots=[shot])
    out, warned = _render(root)
    from an.audio.offline_tts import estimate_speech_duration

    spoken = estimate_speech_duration(LONG_LINE)
    assert spoken > 3.0
    assert _audio_seconds(out) >= spoken - 0.05  # nothing cut
    assert _frames(out) == round(spoken * 30)
    assert any("HELD" in str(w.message) for w in warned)
    report = json.loads(build_project_mall(root)["render_reports"]["main"])
    assert any("HELD" in f["description"] for f in report["findings"])
    with pytest.raises(MeasurementError, match="strict mode"):
        _render(root, strict_assets=True)


@pytest.mark.ffmpeg
def test_a_file_the_scene_reads_is_staged_and_keyed_and_cold_is_cold(tmp_path, fake):
    """H4: a changed data file re-renders; `incremental=False` serves nothing stale."""
    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    mall = build_project_mall(root)
    mall["sources"]["a"] = READS_DATA
    data = root / "assets" / "sources" / "data" / "seconds.txt"
    data.parent.mkdir(parents=True)
    data.write_text("1.0", encoding="utf-8")
    assert _frames(_render(root)[0]) == 30
    data.write_text("2.0", encoding="utf-8")  # the scene's input changed, not its code
    assert _frames(_render(root)[0]) == 60
    calls = fake.calls
    _render(root, incremental=False)
    _render(root, incremental=False)
    assert fake.calls == calls + 2  # cold renders run Manim; nothing hidden is reused


@pytest.mark.ffmpeg
def test_the_shot_key_moves_with_each_input_and_the_picture_key_only_with_the_picture(
    tmp_path, fake
):
    """M1: no part of the key can be dropped without a test noticing."""
    mall = build_project_mall(tmp_path, ensure=True)
    mall["sources"]["a"] = LINEAR
    mall["audio"]["k1"] = b"RIFF-one"
    mall["audio"]["k2"] = b"RIFF-two"
    base = Shot(id="a", renderer="manim", duration=2.0, options={"source": "a"},
                dialogue=[Dialogue(speaker="n", text="x", audio_ref="k1", start=0.0, duration=1.0)])  # fmt: skip
    ctx = _ctx(mall, tmp_path)

    def parts(shot=base, c=ctx):
        return ma.manim_shot_inputs(shot, c).parts

    def pkey(shot=base, c=ctx):
        spec, source = ManimRenderer().resolve(shot, c)
        return ma.picture_key(ma.picture_inputs(spec, source, c))

    p0, k0 = parts(), pkey()
    assert set(p0) == {"source", "manim", "knobs", "audio", "code"}
    mall["sources"]["a"] = LINEAR + b"# edited\n"
    assert parts()["source"] != p0["source"] and pkey() != k0
    mall["sources"]["a"] = LINEAR
    mall["sources"]["helper"] = b"X = 1\n"  # a sibling module the scene may import
    assert parts()["source"] != p0["source"] and pkey() != k0
    del mall["sources"]["helper"]
    voiced = base.model_copy(update={"dialogue": [base.dialogue[0].model_copy(update={"audio_ref": "k2"})]})
    assert parts(voiced)["audio"] != p0["audio"] and pkey(voiced) == k0
    longer = base.model_copy(update={"duration": 3.0})  # a held narration
    assert parts(longer)["audio"] != p0["audio"]
    padded = base.model_copy(update={"options": {"source": "a", "background": "#112233"}})
    assert parts(padded)["knobs"] != p0["knobs"] and pkey(padded) == k0
    at24 = _ctx(mall, tmp_path, fps=24)
    assert parts(c=at24)["knobs"] != p0["knobs"] and pkey(c=at24) == k0
    sharper = base.model_copy(update={"options": {"source": "a", "quality": "h"}})
    assert parts(sharper)["manim"] != p0["manim"] and pkey(sharper) != k0


@pytest.mark.ffmpeg
def test_a_narration_edit_remuxes_without_running_manim(tmp_path, fake):
    """M4: the picture is cached apart from the shot."""
    from an.build import ShotCache

    shot = Shot(id="a", renderer="manim", options={"source": "a"},
                dialogue=[Dialogue(speaker="narrator", text="Short.")])  # fmt: skip
    root = _project(tmp_path / "p", shots=[shot], prose=False)
    _render(root)
    mall = build_project_mall(root)
    scene = mall["scenes"]["main"]
    scene.timeline[0].dialogue[0].text = "Shorter."
    mall["scenes"]["main"] = scene
    engine = ShotCache()
    _render(root, incremental=engine)
    assert engine.report.rendered == ["a"]  # the shot changed …
    assert fake.calls == 1  # … but not its picture


@pytest.mark.ffmpeg
def test_an_edited_source_of_the_same_length_is_rendered_again(tmp_path, fake):
    from an.build import ShotCache

    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    _render(root)
    build_project_mall(root)["sources"]["a"] = LINEAR + b"# same length, other code\n"
    engine = ShotCache()
    _render(root, incremental=engine)
    assert engine.report.rendered == ["a"] and fake.calls == 2


@pytest.mark.ffmpeg
def test_an_unchanged_manim_film_is_reused_and_still_reports_its_findings(tmp_path, fake):
    from an.build import ShotCache

    shots = [Shot(id="a", renderer="manim", options={"source": "a"}),
             Shot(id="b", renderer="manim", options={"source": "b"})]  # fmt: skip
    root = _project(tmp_path / "p", shots=shots)
    _render(root)
    engine = ShotCache()
    _, warned = _render(root, incremental=engine)
    assert fake.calls == 2 and engine.report.reused == ["a", "b"]
    assert any("assets/sources/a.py:6" in str(w.message) for w in warned)  # replayed


@pytest.mark.ffmpeg
def test_findings_reach_validate_orchestrate_and_mcp(tmp_path, fake):
    """M2: located findings are routed, not only warned."""
    from an.mcp.tools import validate_scene
    from an.orchestrate import orchestrate, validate_project

    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", duration=4.0, options={"source": "a"})])
    before = validate_project(root)
    assert any("unknown until the first render" in f.description for f in before.findings)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ShotFindingWarning)
        result = orchestrate(root, verifiers=[])
    located = [f for v in result.verifications for f in v.findings if f.location]
    assert any(f.location == "assets/sources/a.py:6" and f.ir_path == "timeline/0/options/source" for f in located)
    after = validate_project(root)
    assert any(f.location == "assets/sources/a.py:6" for f in after.findings)
    assert any("declares 4 s" in f.description for f in after.findings)
    mcp = validate_scene(str(root))
    assert any(f["location"] == "assets/sources/a.py:6" for f in mcp["findings"])


@pytest.mark.ffmpeg
def test_accept_measured_writes_the_duration_and_keeps_the_prose(tmp_path, fake):
    from an.tools import sync

    root = _project(tmp_path / "p", shots=[Shot(id="a", renderer="manim", options={"source": "a"})])
    _render(root)
    assert "a=2s" in sync(str(root), accept_measured=True)
    md = (root / "scene.md").read_text(encoding="utf-8")
    assert SCENE_MD_PROSE in md and "duration: 2" in md
    assert build_project_mall(root)["scenes"]["main"].timeline[0].duration == 2.0
    _, warned = _render(root)
    assert not any("declares" in str(w.message) for w in warned)  # accepted == measured


@pytest.mark.ffmpeg
def test_the_keyer_reads_through_the_registered_renderers_resolver(tmp_path, fake, monkeypatch):
    """M3: a renderer with another source resolver is keyed on ITS source."""
    from an.adapters._base import _DEFAULT_REGISTRY

    generated = _src("gen", LINEAR + b"# generated by a genre\n")
    custom = ManimRenderer(source_resolver=lambda spec, mall: generated)
    monkeypatch.setitem(_DEFAULT_REGISTRY._by_name, "manim", custom)
    mall = build_project_mall(tmp_path, ensure=True)  # no "gen" in its sources store
    shot = Shot(id="g", renderer="manim", duration=2.0, options={"source": "gen"})
    assert ma.manim_shot_inputs(shot, _ctx(mall, tmp_path)).parts["source"] == generated.digest


@pytest.mark.ffmpeg
def test_render_conforms_to_the_film_and_records_the_contact_sheet(tmp_path, fake):
    mall = build_project_mall(tmp_path, ensure=True)
    mall["sources"]["chart"] = LINEAR
    shot = Shot(id="m", renderer="manim", duration=2.0, options={"source": "chart"})
    result = ManimRenderer().render(shot, _ctx(mall, tmp_path))
    assert len(result.frame_manifest) == 60 and result.duration == pytest.approx(2.0)
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,nb_frames",
             "-of", "json", str(result.mp4_path)],
            capture_output=True, text=True, check=True,
        ).stdout
    )  # fmt: skip
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["nb_frames"]) == (640, 360, "60")
    assert any(s["codec_type"] == "audio" for s in probe["streams"])
    sheet = result.provenance["manim"]["contact_sheet"]
    assert sheet["store"] == "contact_sheets" and sheet["key"] in mall["contact_sheets"]


@pytest.mark.ffmpeg
def test_a_film_of_manim_shots_with_a_dissolve_and_narration(tmp_path, fake):
    """The film lays out on the MEASURED durations."""
    shots = [
        Shot(id="a", renderer="manim", options={"source": "a"},
             dialogue=[Dialogue(speaker="narrator", text="Watch the bars.")]),
        Shot(id="b", renderer="manim", options={"source": "b"},
             transition=Transition(kind="dissolve", duration=0.5)),
    ]  # fmt: skip
    root = _project(tmp_path / "p", shots=shots, duration=10.0)
    out, _ = _render(root)
    assert _frames(out) == 105  # 60 + 60 - 15 overlapping frames


# -----------------------------------------------------------------------------
# Manim installed (a developer machine; not CI)
# -----------------------------------------------------------------------------

WIDE = b"""from manim import *

class Hello(Scene):
    def construct(self):
        t = Text("Hello", font_size=48)
        self.play(Write(t), run_time=1.0)
        wide = Text("This line is far too wide to fit on the frame at all", font_size=72)
        self.play(FadeIn(wide.next_to(t, DOWN)))
        self.wait(0.5)
"""


@pytest.mark.ffmpeg
@pytest.mark.skipif(not HAS_MANIM, reason="manim + manimkit not installed (pip install 'an[manim]')")
def test_real_manim_render_measures_and_locates_a_cut_off_line(tmp_path):
    mall = build_project_mall(tmp_path, ensure=True)
    mall["sources"]["hello"] = WIDE
    ctx = _ctx(mall, tmp_path)
    r = ManimRenderer()
    m = r.measure_duration(Shot(id="h", renderer="manim", options={"source": "hello"}), ctx)
    assert m.duration == pytest.approx(2.5)
    assert any(
        f.location == "assets/sources/hello.py:8" and "[cut-off]" in f.description for f in m.findings
    )
    result = r.render(Shot(id="h", renderer="manim", duration=m.duration, options={"source": "hello"}), ctx)
    assert len(result.frame_manifest) == 75
    assert result.provenance["manim"]["contact_sheet"]["key"] in mall["contact_sheets"]


@pytest.mark.browser
@pytest.mark.ffmpeg
@pytest.mark.skipif(not HAS_MANIM, reason="manim + manimkit not installed (pip install 'an[manim]')")
def test_proof_film_mixes_a_manim_shot_and_a_stage_shot_with_a_dissolve(tmp_path):
    """an#279's proof: narration over a Manim shot, a dissolve, a stage shot."""
    from an.environments import EnvironmentDescriptor, Plane, PlaneArt
    from an.ir.schema import AssetRef
    from an.project import init
    from an.render import render_project
    from an.text import TextDescriptor

    root = tmp_path / "mixed"
    init(root)
    mall = build_project_mall(root)
    mall["sources"]["chart"] = LINEAR
    mall["environments"]["card"] = EnvironmentDescriptor(
        name="card", planes=[Plane(name="bg", art=PlaneArt(kind="fill", color="#202040"), depth=0.0)]
    ).model_dump(mode="json")
    mall["props"]["title"] = TextDescriptor(
        name="title", text="AND THEN", layer="overlay", unit="line", size=0.12, color="#ffffff"
    ).model_dump(mode="json")
    mall["scenes"]["main"] = SceneIR(
        meta=Meta(title="mixed", fps=30, resolution={"width": 640, "height": 360}),
        timeline=[
            Shot(id="chart", renderer="manim", options={"source": "chart", "scene": "Chart"},
                 dialogue=[Dialogue(speaker="narrator", text="Hi.")]),
            Shot(id="card", renderer="cutout", duration=2.0,
                 transition=Transition(kind="dissolve", duration=0.5),
                 entities=[AssetRef(kind="environment", id="bg", store="environments", ref="card"),
                           AssetRef(kind="prop", id="title", store="props", ref="title")]),
        ],
    )  # fmt: skip
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ShotFindingWarning)
        out = render_project(root, strict_assets=True)
    (key,) = list(build_project_mall(root)["measurements"])
    measured = json.loads(build_project_mall(root)["measurements"][key])["duration"]
    assert _frames(out) == round(measured * 30) + 60 - 15
