"""`an render` reports what it learns at render time (an#254).

Two end-user tests lost a render to the same silence: a synthesized line ran
past its shot (into a dissolve), `an render` printed only "rendered: …", and
only a later `an validate` said so. Render is when a line's real length becomes
known, so it now runs the post-synthesis checks itself — the SAME functions
`an validate` runs — and reports them, with the render's other warnings, in
`render_reports/<name>.json` and in the CLI's summary.

No browser and no ffmpeg: the shot render is a stand-in that writes a few
bytes, the TTS returns a WAV of a stated length, and the concat/assembly are
stubbed. What is under test is the reporting, not the pixels.
"""

from __future__ import annotations

import io
import json
import shutil
import warnings
import wave
from pathlib import Path

import pytest

from an import init
from an.adapters._base import RenderResult
from an.audio.tts import AudioClip
from an.ir.schema import AssetRef, Dialogue, Meta, Resolution, SceneIR, Shot, Transition
from an.project import load

_FPS = 12
_BOB = AssetRef(kind="character", id="bob", store="characters", ref="bob")


def _wav(seconds: float, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(round(seconds * rate)))
    return buf.getvalue()


class _LongTTS:
    """A 'real' voice: every line lasts ``seconds``, whatever the estimate says."""

    name = "long"

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def synthesize(self, text, voice_id="default", **kw):
        return AudioClip(bytes_=_wav(self.seconds), duration=self.seconds, transcript=text)

    def list_voices(self):
        return []


@pytest.fixture
def fake_render(monkeypatch):
    """The shot render, the concat and the assembly, without a browser or ffmpeg."""
    import an.render as render_mod
    from an.adapters.cutout.render import CutoutRenderer

    rendered: list[str] = []

    def render(self, shot, ctx):
        # Compiles exactly as the real renderer does (its warnings, its strict
        # refusals), then draws nothing.
        from an.adapters.cutout.cache_key import compiled_document

        compiled_document(shot, ctx)
        rendered.append(shot.id)
        work = Path(ctx.work_dir) / f"shot_{shot.id}"
        work.mkdir(parents=True, exist_ok=True)
        out = work / f"{shot.id}.mp4"
        out.write_bytes(f"mp4 of {shot.id}".encode())
        return RenderResult(mp4_path=out, duration=shot.duration)

    def assemble(scene, results, output_path, **kw):
        Path(output_path).write_bytes(b"assembled")

    monkeypatch.setattr(CutoutRenderer, "render", render)
    monkeypatch.setattr(
        render_mod, "_ffmpeg_concat", lambda inputs, out: shutil.copy(list(inputs)[0], out)
    )
    monkeypatch.setattr(render_mod, "assemble_film", assemble)
    monkeypatch.setattr(
        render_mod, "_film_parts", lambda windows, *a, **k: [None] * len(windows)
    )
    return rendered


def _project(tmp_path, *shots: Shot, characters=()):
    root = init(tmp_path / "p")
    if characters:
        from an.characters.factory import new_character

        for name in characters:
            new_character(root / "assets" / "characters", name=name, use_dicebear=False)
    project = load(root)
    project.mall["scenes"]["main"] = SceneIR(
        meta=Meta(fps=_FPS, resolution=Resolution(width=160, height=120)),
        timeline=list(shots),
    )
    return root


def _hi_shot(duration: float = 2.0, **kw) -> Shot:
    return Shot(
        id="hello",
        renderer="cutout",
        duration=duration,
        dialogue=[Dialogue(speaker="bob", text="Hi!")],
        **kw,
    )


def _kinds(root, *, prefix: str = ""):
    """``(kinds, findings)`` the render reported, those whose kind starts with
    ``prefix`` (the offscreen ``bob`` also draws a no-mouth compile note)."""
    from an.render import render_findings

    report = json.loads(load(root).mall["render_reports"]["main"])
    pairs = [
        (r["kind"], f)
        for r, f in zip(report["findings"], render_findings(root))
        if r["kind"].startswith(prefix)
    ]
    return [k for k, _ in pairs], [f for _, f in pairs]


# -----------------------------------------------------------------------------
# The costly case: a line that is longer than validate could know
# -----------------------------------------------------------------------------


def test_a_line_synthesized_past_its_shot_is_reported_by_the_render(tmp_path, fake_render):
    from an.orchestrate import validate_project
    from an.render import render_project

    root = _project(tmp_path, _hi_shot(duration=1.0))
    before = validate_project(root)
    assert not [f for f in before.findings if "cut off" in f.description]  # the estimate fits

    render_project(root, tts=_LongTTS(1.6), incremental=False, echo_warnings=False)
    kinds, findings = _kinds(root, prefix="dialogue")
    assert kinds == ["dialogue_fits"]
    (f,) = findings
    assert f.severity == "warning" and f.ir_path == "timeline/0/dialogue/0"
    assert "ends at 1.60s as synthesized" in f.description and "cut off" in f.description
    # The fix a real voice's padding calls for is named.
    assert "trim_silence" in f.description

    # ONE source of truth: what `an validate` now says is the same sentence.
    after = validate_project(root)
    assert [g.description for g in after.findings if g.ir_path == f.ir_path] == [
        f.description
    ]


def test_the_pipeline_does_not_announce_what_the_render_reports(tmp_path, fake_render, capsys):
    from an.render import render_project

    root = _project(tmp_path, _hi_shot(duration=1.0))
    render_project(root, tts=_LongTTS(1.6), incremental=False, echo_warnings=False)
    assert "cut off" not in capsys.readouterr().err


def test_a_line_heard_during_a_dissolve_is_reported(tmp_path, fake_render):
    from an.render import render_project

    first = _hi_shot(duration=2.0)
    second = Shot(
        id="after",
        renderer="cutout",
        duration=2.0,
        transition=Transition(kind="dissolve", duration=0.5),
    )
    root = _project(tmp_path, first, second)
    render_project(root, tts=_LongTTS(1.8), incremental=False, echo_warnings=False)
    kinds, findings = _kinds(root, prefix="dialogue")
    assert kinds == ["dialogue_in_dissolve"]
    assert findings[0].ir_path == "timeline/0/dialogue/0"
    assert "dissolve into shot 'after' (1.50-2s)" in findings[0].description
    assert "0.00-1.80s" in findings[0].description


def test_a_clean_render_reports_nothing(tmp_path, fake_render):
    from an.render import format_render_findings, render_findings, render_project

    root = _project(tmp_path, _hi_shot(duration=3.0, entities=[_BOB]), characters=("bob",))
    render_project(root, tts=_LongTTS(1.0), incremental=False, echo_warnings=False)
    assert render_findings(root) == [] and format_render_findings(root) == []


# -----------------------------------------------------------------------------
# The render's own warnings: substitutions and stand-ins
# -----------------------------------------------------------------------------


def _stand_in_scene(tmp_path):
    shot = Shot(
        id="cast",
        renderer="cutout",
        duration=1.0,
        entities=[AssetRef(kind="character", id="ghost", store="characters", ref="ghost")],
    )
    return _project(tmp_path, shot)


def test_a_stand_in_is_a_finding_addressed_to_its_shot(tmp_path, fake_render):
    from an.render import render_project

    root = _stand_in_scene(tmp_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        render_project(root, incremental=False, echo_warnings=False)
    assert not [w for w in caught if w.category.__name__ == "CutoutCompileWarning"]
    kinds, findings = _kinds(root)
    assert "CutoutCompileWarning" in kinds
    stand_in = findings[kinds.index("CutoutCompileWarning")]
    assert stand_in.ir_path == "timeline/0" and "stand-in" in stand_in.description
    # The explanation after the first paragraph stays in the warning, not the summary.
    assert "Pass strict_assets=True" not in stand_in.description


def test_the_python_api_still_warns_by_default(tmp_path, fake_render):
    from an.adapters.cutout.compile import CutoutCompileWarning
    from an.render import render_project

    root = _stand_in_scene(tmp_path)
    with pytest.warns(CutoutCompileWarning, match="stand-in"):
        render_project(root, incremental=False)


def test_strict_assets_still_refuses_before_any_shot_renders(tmp_path, fake_render):
    from an.adapters.cutout.compile import CutoutCompileError
    from an.render import render_project

    root = _stand_in_scene(tmp_path)
    with pytest.raises(CutoutCompileError, match="stand-in"):
        render_project(root, strict_assets=True, echo_warnings=False)
    assert fake_render == []


def test_a_failed_render_still_shows_its_warnings(tmp_path, fake_render, monkeypatch):
    """`echo_warnings=False` hides what the summary will list — but a render
    that fails has no summary, so what it warned is warned anyway."""
    from an.adapters.cutout.compile import CutoutCompileWarning
    import an.render as render_mod

    root = _stand_in_scene(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("concat failed")

    monkeypatch.setattr(render_mod, "_ffmpeg_concat", boom)
    with pytest.warns(CutoutCompileWarning), pytest.raises(RuntimeError, match="concat"):
        render_mod.render_project(root, incremental=False, echo_warnings=False)


# -----------------------------------------------------------------------------
# The CLI summary
# -----------------------------------------------------------------------------


def test_an_render_prints_the_findings_grouped_with_their_fix(tmp_path, fake_render, monkeypatch):
    from an import tools
    from an.audio import providers

    monkeypatch.setitem(providers.TTS_FACTORIES, "long", lambda: _LongTTS(1.6))
    root = _project(tmp_path, _hi_shot(duration=1.0))
    out = tools.render(str(root), tts="long")
    lines = out.splitlines()
    assert lines[0].startswith("rendered: ")
    at = next(i for i, l in enumerate(lines) if l.startswith("findings: "))
    assert lines[at] == "findings: 2 warnings (all in artifacts/render_reports/main.json)"
    assert lines[at + 1] == "  dialogue that does not fit its shot (1):"
    assert lines[at + 2].startswith("    timeline/0/dialogue/0: line 0 (bob) ends at 1.60s")
    assert "Lengthen the shot" in lines[at + 2]
    # The render's own warning, after it, addressed to the shot it names.
    assert lines[at + 3] == "  stand-ins, substitutions and compile notes (1):"
    assert lines[at + 4].startswith("    timeline/0: shot 'hello' dialogue line 0 is spoken by 'bob'")


def test_the_summary_is_short(tmp_path):
    from an.render import format_render_findings

    records = [
        {"severity": "warning", "ir_path": f"timeline/{i}", "description": f"d{i}",
         "kind": "CutoutCompileWarning"}
        for i in range(8)
    ] + [{"severity": "info", "ir_path": "timeline", "description": "fyi", "kind": "measurement"}]
    mall = {"render_reports": {"main": json.dumps({"findings": records})}}
    lines = format_render_findings(mall, max_per_group=3)
    assert lines[0].startswith("findings: 8 warnings")
    assert lines[1] == "  stand-ins, substitutions and compile notes (8):"
    assert lines[-1] == "    ... and 5 more" and len(lines) == 6
    assert not any("fyi" in l for l in lines)  # info is in the report, not the summary


# -----------------------------------------------------------------------------
# What the report may say: no machine's paths (an#254 review M2)
# -----------------------------------------------------------------------------


def test_the_report_names_no_absolute_path(tmp_path, fake_render, monkeypatch):
    import an.render as render_mod
    from an.adapters.cutout.render import CutoutRenderer
    from an.build.shot_cache import ShotCacheWarning

    real = CutoutRenderer.render  # the fake's

    def render(self, shot, ctx):
        root = load(tmp_path / "p").root
        warnings.warn(
            f"shot {shot.id!r}: art was not found at {root}/assets/characters/bob/x.png "
            f"(log in {Path.home()}/an.log)",
            ShotCacheWarning,
        )
        return real(self, shot, ctx)

    monkeypatch.setattr(CutoutRenderer, "render", render)
    root = _project(tmp_path, _hi_shot(duration=3.0, entities=[_BOB]), characters=("bob",))
    render_mod.render_project(root, tts=_LongTTS(1.0), incremental=False, echo_warnings=False)
    raw = load(root).mall["render_reports"]["main"].decode()
    assert str(root) not in raw and str(Path.home()) not in raw
    assert "assets/characters/bob/x.png" in raw and "~/an.log" in raw


def test_an_init_keeps_render_reports_out_of_git(tmp_path):
    from an.project import PROJECT_GITIGNORE

    root = init(tmp_path / "p")
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "artifacts/render_reports/" in lines
    # Idempotent, and a project's own lines are kept.
    (root / ".gitignore").write_text("output/\n" + "\n".join(lines) + "\n", encoding="utf-8")
    init(root, force=True)
    assert (root / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "output/",
        *PROJECT_GITIGNORE,
    ]


# -----------------------------------------------------------------------------
# Which checks run again after synthesis
# -----------------------------------------------------------------------------


def test_every_post_synthesis_check_is_a_registered_check():
    """The render runs them BY NAME through validate's registry, so a name that
    registers nothing would silently drop a check."""
    from an.genres import load as load_genres
    from an.genres.registry import check_names
    from an.ir.validate import POST_SYNTHESIS_CHECKS

    load_genres()
    assert set(POST_SYNTHESIS_CHECKS) <= set(check_names())


def test_a_line_spoken_while_a_view_hides_the_mouth_is_rerun_after_synthesis(monkeypatch):
    """`cutout.hidden_mouth_while_speaking` reads the line's real span: run after
    synthesis, it is reported under its own kind."""
    import an.ir.validate as v
    from an.genres import load as load_genres

    load_genres()
    calls = []
    monkeypatch.setattr(
        v,
        "_check_hidden_mouth_while_speaking",
        lambda shot, path, report, resolved, stores: (
            calls.append(path),
            report.add("warning", f"{path}/dialogue/0", "hidden"),
        ),
    )
    scene = SceneIR(meta=Meta(fps=12), timeline=[_hi_shot(duration=2.0)])
    found = v.post_synthesis_findings(scene)
    assert ("cutout.hidden_mouth_while_speaking", "timeline/0/dialogue/0") in [
        (k, f.ir_path) for k, f in found
    ]
