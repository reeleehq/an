"""Orchestrator: validate → audio → render → verify.

Phase 5 ships ``orchestrate(project_dir, ...)`` — the high-level flow that
ties together validation, audio synthesis, rendering, and verification.
The full iterative edit loop (free-text "make Maya's laugh longer" →
re-render only the affected shot) lives in the ``an`` skill, which calls
into these primitives.

>>> from an.orchestrate import OrchestratorReport
>>> r = OrchestratorReport()
>>> r.success
True
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from an.ir.schema import SceneIR
from an.ir.validate import (
    ValidationReport,
    validate_schema,
    validate_semantic,
)
from an.ir.migrate import DocumentMigrationError
from an.ir.sync import SceneValidationError
from an.project import Project, load
from an.render import render_project as _render_project
from an.verify._base import Verifier, VerificationReport
from an.verify.layout import LayoutLintVerifier
from an.verify.media_quality import MediaQualityVerifier


@dataclass(slots=True)
class OrchestratorReport:
    """Outcome of an end-to-end orchestrated run."""

    success: bool = True
    output_path: Path | None = None
    validation: ValidationReport | None = None
    verifications: list[VerificationReport] = field(default_factory=list)
    error: str | None = None
    #: The project root, when known: descriptions are compared with their
    #: paths made portable (the render report stores them so; an#309).
    root: Path | None = None

    def merge_verification(self, vr: VerificationReport) -> None:
        """Add ``vr`` — less any finding this report already holds: the render
        report repeats what the pre-render validation found (a synthesized
        line still past its shot), and one finding is reported once (an#309).
        The SAME finding: severity, path, location and description (its paths
        made portable) — so a render that escalates a warning to an error, or
        locates it elsewhere, is reported. ``vr``'s verdict is kept."""
        seen = {self._identity(f) for f in self._findings()}
        fresh = [f for f in vr.findings if self._identity(f) not in seen]
        if len(fresh) != len(vr.findings):
            vr = VerificationReport(passed=vr.passed, findings=fresh)
        self.verifications.append(vr)
        if not vr.passed:
            self.success = False

    def _identity(self, f) -> tuple:
        from an.render import portable_text

        description = f.description
        if self.root is not None:
            description = portable_text(description, root=self.root)
        return (f.severity, f.ir_path, getattr(f, "location", None), description)

    def _findings(self):
        if self.validation is not None:
            yield from self.validation.findings
        for v in self.verifications:
            yield from v.findings


def validate_project(
    project_dir: str | Path, *, fps: float | None = None
) -> ValidationReport:
    """Schema + semantic validation of the scene at ``project_dir``.

    ``fps`` is the frame rate the render will use when it is not the scene's
    (``an.render.render_project(fps=)``): the checks that depend on it
    (``step_hz``, the dialogue timing) are made against it (an#435).

    A ``scene.md`` that does not PARSE — a dialogue line in no accepted shape
    (an#96), a malformed YAML block — is a Finding, not a traceback: `an
    validate` exists to print findings, and it used to be the one tool that
    stack-dumped on the error it should report.

    ``fps`` is the frame rate the render will use when it is not the scene's
    (``an render --fps``): the checks that depend on it (``step_hz``, a line
    heard during a dissolve) use it, as the render will (an#435).
    """
    try:
        # Kinds are REPORTED here, as findings, not refused at load.
        project: Project = load(project_dir, check_kinds=False)
    except (DocumentMigrationError, SceneValidationError) as e:
        # NOT "scene.md does not parse": the md may be perfect and the stored
        # JSON from another build. Routing an agent to edit the file that is
        # fine is the failure `Finding.ir_path` exists to prevent (an#105).
        report = ValidationReport()
        report.add("error", "ir/scene.json", str(e))
        return report
    except ValueError as e:
        report = ValidationReport()
        report.add("error", "scene.md", f"scene.md does not parse: {e}")
        return report
    schema_report = validate_schema(project.scene)
    # Clock-owned shots (Manim) are judged at their MEASURED length, from the
    # derived store only — validate never renders (an#279).
    from an.measurements import render_context_for, settle_durations

    try:
        scene, measured = settle_durations(
            project.scene, render_context_for(project), render=False
        )
    except Exception as e:  # noqa: BLE001 — a finding, never a traceback
        scene, measured = project.scene, []
        schema_report.add(
            "warning", "timeline", f"measured durations could not be read: {e}"
        )
    for f in measured:
        schema_report.add(f.severity, f.ir_path, f.description, location=f.location)
    semantic_report = validate_semantic(
        scene,
        available_voices=project.mall.get("voices"),
        available_characters=project.mall.get("characters"),
        available_props=project.mall.get("props"),
        available_environments=project.mall.get("environments"),
        available_styles=project.mall.get("styles"),
        available_sounds=project.mall.get("sounds"),
        available_library_lock=project.mall.get("library_lock"),
        fps=fps,
    )
    return schema_report.merge(semantic_report)


def render_project(project_dir: str | Path, **kwargs: Any) -> Path:
    """Render the project's scene to a single mp4 under ``output/`` — the
    orchestrator's name for :func:`an.render.render_project`, every keyword
    forwarded.

    It used to re-declare the leaf's parameters, and the two drifted: the CLI
    (`an render`) passed `supersample`, `pix_fmt`, `step_hz` and `language`
    here from the day each flag landed, and this wrapper refused all four with
    a ``TypeError`` — invisible because the CLI test stubbed THIS function
    rather than the leaf (an#98 review). A pass-through cannot drift.
    """
    return _render_project(project_dir, **kwargs)


def orchestrate(
    project_dir: str | Path,
    *,
    output_name: str = "main",
    verifiers: Sequence[Verifier] | None = None,
    skip_render: bool = False,
    tts: str | object | None = None,
    lipsync: str | object = "offline",
    parallel: int | str | None = None,
    language: str = "en",
) -> OrchestratorReport:
    """Run the full pipeline. Returns a structured outcome.

    Phases:
      1. Validate (schema + semantic). Hard fail if the schema is broken.
      2. Pre-render verifiers (any that accept ``render=None``).
      3. Render (audio is auto-run inside `render` when needed).
      4. Post-render verifiers.

    ``verifiers`` defaults to ``[LayoutLintVerifier(), MediaQualityVerifier()]``
    — the second one is why `an.verify.media.ssim`'s threshold is load-bearing
    and must not be retuned casually. Pass an empty list
    to skip verification, or include ``HumanInTheLoopVerifier()`` to prompt.
    ``skip_render=True`` runs validation + lint only.

    ``tts`` and ``lipsync`` accept either a provider name string or a
    provider instance — useful for callers (e.g. ``muvid``) that want
    to inject a :class:`an.audio.WordTimingsLipSync` driven by their
    own alignment store, instead of letting ``an`` re-transcribe. ``tts``
    defaults to each voice's own provider (an#305), as ``an render`` does.
    """
    report = OrchestratorReport(root=Path(project_dir))
    if verifiers is None:
        verifiers = [LayoutLintVerifier(), MediaQualityVerifier()]

    # --- 1. validation ------------------------------------------------------
    try:
        report.validation = validate_project(project_dir)
    except Exception as e:
        report.success = False
        report.error = f"validation crashed: {e!r}"
        return report
    if not report.validation.passed:
        report.success = False
        report.error = "schema/semantic validation failed"
        return report

    # --- 2. pre-render verifiers (run on IR alone) --------------------------
    project = load(project_dir)
    for v in verifiers:
        try:
            vr = v.verify(project.scene, None)
            report.merge_verification(vr)
        except Exception as e:
            partial = VerificationReport()
            partial.add("warning", f"<{v.name}>", f"verifier crashed pre-render: {e!r}")
            report.merge_verification(partial)

    if skip_render or report.success is False:
        return report

    # --- 3. render ----------------------------------------------------------
    try:
        report.output_path = _render_project(
            project_dir,
            output_name=output_name,
            tts=tts,
            lipsync=lipsync,
            language=language,
            parallel=parallel,
        )
    except Exception as e:
        report.success = False
        report.error = f"render failed: {e!r}"
        return report

    # --- 4. post-render verifiers (with the actual mp4) ---------------------
    project = load(project_dir)
    from an.adapters._base import RenderResult

    from an.assemble import film_duration
    from an.measurements import render_context_for, settle_durations

    # The scene AS RENDERED: clock-owned shots at their measured length, from
    # the derived store the render just filled (an#279).
    scene, _ = settle_durations(
        project.scene, render_context_for(project), render=False
    )
    # The DELIVERED length: a dissolve overlaps its shots (an#163), so the
    # film can be shorter than meta.duration's sum of shots.
    rr = RenderResult(mp4_path=report.output_path, duration=film_duration(scene))
    # What the render itself found (a Manim shot's layout warnings, located by
    # file:line; a held last frame) — `render_reports/<output>.json` (an#279).
    report.merge_verification(_render_report(project.mall, output_name))
    for v in verifiers:
        try:
            vr = v.verify(scene, rr)
            report.merge_verification(vr)
        except Exception as e:
            partial = VerificationReport()
            partial.add(
                "warning", f"<{v.name}>", f"verifier crashed post-render: {e!r}"
            )
            report.merge_verification(partial)

    return report


def _render_report(mall, output_name: str) -> VerificationReport:
    """The findings ``an render`` recorded for ``output_name``, as a report."""
    import json

    report = VerificationReport()
    store = mall.get("render_reports")
    if store is None or output_name not in store:
        return report
    for f in json.loads(store[output_name]).get("findings", []):
        report.add(
            f["severity"],
            f["ir_path"],
            f["description"],
            f.get("suggested_fix"),
            location=f.get("location"),
        )
    return report


def iterate(project_dir: str | Path, instruction: str, **kwargs):
    """Apply a free-text edit instruction. Returns an IterateResult.

    Thin re-export for consistency with the rest of the orchestrator surface;
    the real implementation lives in ``an.iterate``.
    """
    from an.iterate import iterate as _iterate

    return _iterate(project_dir, instruction, **kwargs)
