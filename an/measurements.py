"""Measured durations: shots whose renderer, not their author, decides their length.

A whole-shot renderer that **owns its clock** (Manim: only the scene file's own
``play`` and ``wait`` calls fix its length) implements ``measure_duration``
(:class:`~an.adapters._base.ClockOwningRenderer`). Its answer is DERIVED data:

- it lives in a derived store keyed by the shot's content (the renderer's
  ``measurements`` store), never in ``scene.md`` or ``ir/scene.json`` — a render
  never rewrites what the author wrote (an#279 review, H1);
- :func:`settle_durations` applies it IN MEMORY, to a copy of the scene, before
  anything reads ``shot.duration`` — the film timeline, captions, the sound
  layer, the cache keys — so the film's layout is a pure function of the IR
  and the measurements;
- ``an sync --accept-measured`` (:func:`accept_measured`) takes it into the
  authored scene on request, patching each shot's ``duration:`` line in place.

This is how core study §4.2's "written back into the IR" is resolved: the IR the
render LAYS OUT holds the measured length; the IR the author OWNS is untouched
unless they accept it.

**Narration longer than the picture is never cut silently.** A shot's settled
length is ``max(measured, end of its dialogue)``: the renderer holds its last
frame for the difference, and a warning says so — or, under ``strict``
(``--strict-assets``, which already refuses stand-ins), the render is refused.

>>> declared_duration(Shot(id="a", renderer="manim")) is None   # the schema's placeholder
True
>>> declared_duration(Shot(id="a", renderer="manim", duration=3.0))
3.0
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from an.base import DEFAULT_DURATION
from an.ir.schema import SceneIR, Shot

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.adapters._base import RenderContext
    from an.verify._base import Finding

__all__ = [
    "MeasurementError",
    "ShotFindingWarning",
    "accept_measured",
    "clock_owner_for",
    "declared_duration",
    "settle_durations",
    "warn_findings",
]

#: How far ``meta.duration`` may sit from the shots' sum and still be read as
#: "the sum" (the layout lint's own tolerance), so a settled shot moves it too.
META_DURATION_TOLERANCE_S: float = 0.01


class MeasurementError(RuntimeError):
    """A measured shot cannot be laid out as asked (e.g. a hold under strict mode)."""


class ShotFindingWarning(UserWarning):
    """A finding about a shot, warned by ``an render`` — located by ``file:line``
    when the thing to fix is an opaque source (a Manim scene file)."""


def clock_owner_for(shot: Shot, registry: Any = None) -> Any | None:
    """The registered renderer of ``shot`` if it owns its clock, else ``None``."""
    if registry is None:
        from an.adapters._base import _DEFAULT_REGISTRY as registry
    renderer = registry.find_for(shot)
    return renderer if callable(getattr(renderer, "measure_duration", None)) else None


def declared_duration(shot: Shot) -> float | None:
    """The duration the AUTHOR wrote, or ``None``.

    ``scene.md`` fills the schema's placeholder (:data:`an.base.DEFAULT_DURATION`)
    into a shot that writes no ``duration:``, so that value reads as "not
    declared" — an explicit ``duration: 5`` is indistinguishable from it.
    """
    if "duration" not in shot.model_fields_set or shot.duration == DEFAULT_DURATION:
        return None
    return float(shot.duration)


def _dialogue_end(shot: Shot) -> float:
    """Where the shot's last line ends: real durations once synthesized, the
    offline voice's estimate before (the validator's own layout rule)."""
    from an.ir.validate import _dialogue_layout

    return max((end for *_rest, end, _est in _dialogue_layout(shot)), default=0.0)


def _finding(*args: Any, **kwargs: Any) -> "Finding":
    from an.verify._base import Finding

    return Finding(*args, **kwargs)


def _absolute(finding: Any, index: int) -> "Finding":
    """A renderer's shot-relative finding, addressed in the scene."""
    rel = finding.ir_path.strip("/")
    return _finding(
        finding.severity,
        f"timeline/{index}/{rel}" if rel else f"timeline/{index}",
        finding.description,
        finding.suggested_fix,
        location=finding.location,
    )


def settle_durations(
    scene: SceneIR,
    ctx: "RenderContext",
    *,
    render: bool,
    force: bool = False,
    strict: bool = False,
    registry: Any = None,
) -> tuple[SceneIR, list["Finding"]]:
    """A COPY of ``scene`` whose clock-owned shots carry their settled length,
    and the findings about them. ``scene`` itself is never modified.

    ``render=False`` (``an validate``) uses stored measurements only: a shot
    never measured is reported as "length unknown until rendered" and judged
    against nothing. ``render=True`` (``an render``) measures what is not
    stored; ``force`` measures everything afresh.
    """
    timeline = list(scene.timeline)
    findings: list[Finding] = []
    changed = False
    fps = float(ctx.fps)
    for i, shot in enumerate(timeline):
        renderer = clock_owner_for(shot, registry)
        if renderer is None:
            continue
        m = renderer.measure_duration(shot, ctx, render=render, force=force)
        end = _dialogue_end(shot)
        declared = declared_duration(shot)
        if m is None:
            findings.append(
                _finding(
                    "info",
                    f"timeline/{i}/duration",
                    f"shot {shot.id!r} is drawn by {shot.renderer!r}, which decides "
                    "its length; it is unknown until the first render, so nothing "
                    "is judged against it yet",
                )
            )
            # Judge against nothing: long enough for its own dialogue.
            length = max(declared or 0.0, end) or float(shot.duration)
        else:
            findings.extend(_absolute(f, i) for f in m.findings)
            length = float(m.duration)
            if declared is not None and abs(declared - length) > 1.0 / fps:
                findings.append(
                    _finding(
                        "warning",
                        f"timeline/{i}/duration",
                        f"shot {shot.id!r} declares {declared:g} s but its content "
                        f"runs {length:g} s; the {shot.renderer!r} renderer decides "
                        f"a shot's length, so the film uses {length:g} s",
                        "drop `duration:` from the shot (or `an sync "
                        "--accept-measured`), or change the content's own timing",
                    )
                )
            if end > length + 1.0 / fps:
                held = end - length
                if strict:
                    raise MeasurementError(
                        f"shot {shot.id!r}: its dialogue ends at {end:.2f} s but its "
                        f"content runs {length:.2f} s; the last frame would be held "
                        f"for {held:.2f} s, which strict mode refuses. Lengthen the "
                        "content (a `self.wait()` at the end of a Manim scene) or "
                        "shorten the narration"
                    )
                findings.append(
                    _finding(
                        "warning",
                        f"timeline/{i}/dialogue",
                        f"shot {shot.id!r}: the dialogue ends at {end:.2f} s but the "
                        f"content runs {length:.2f} s, so its last frame is HELD for "
                        f"{held:.2f} s",
                        "lengthen the content (a `self.wait()` at the end of a Manim "
                        "scene) or shorten the narration",
                    )
                )
                length = end
        if abs(length - shot.duration) > 1e-9:
            timeline[i] = shot.model_copy(update={"duration": length})
            changed = True
    if not changed:
        return scene, findings
    meta = scene.meta
    out = scene.model_copy(update={"timeline": timeline})
    from an.assemble import film_duration

    before = (film_duration(scene, fps=fps), sum(s.duration for s in scene.timeline))
    if any(abs(meta.duration - b) <= META_DURATION_TOLERANCE_S for b in before):
        out.meta = meta.model_copy(update={"duration": film_duration(out, fps=fps)})
    return out, findings


def warn_findings(findings: Iterable["Finding"], *, stacklevel: int = 3) -> None:
    """Warn each finding as a :class:`ShotFindingWarning` (``location: …``)."""
    for f in findings:
        if f.severity == "info":
            continue
        where = f"{f.location}: " if getattr(f, "location", None) else ""
        fix = f" ({f.suggested_fix})" if f.suggested_fix else ""
        warnings.warn(
            f"{f.ir_path}: {where}{f.description}{fix}",
            ShotFindingWarning,
            stacklevel=stacklevel,
        )


def findings_record(
    findings: Iterable[Any],
    *,
    kind: str | None = None,
    text: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    """JSON-able findings — THE render report's shape, its one writer (an#309):
    each ``Finding``'s fields plus its ``kind``. ``findings`` are ``Finding`` s
    (each of ``kind``) or ``(kind, Finding)`` pairs (a render's, of many kinds);
    ``text`` maps every text field (the render makes paths portable).

    >>> from an.verify._base import Finding
    >>> findings_record([Finding("info", "timeline/0", "x")], kind="measurement")[0]["kind"]
    'measurement'
    """
    from dataclasses import asdict

    out = []
    for item in findings:
        k, f = item if isinstance(item, tuple) else (kind, item)
        fields = asdict(f)
        if text is not None:
            fields = {n: text(v) if isinstance(v, str) else v for n, v in fields.items()}
        out.append({**fields, "kind": k})
    return out


def render_context_for(project: Any, **overrides: Any) -> "RenderContext":
    """The context a measurement is looked up in for ``project``'s scene, at its
    declared fps and size (what ``an render`` uses without overrides)."""
    from an.adapters._base import RenderContext
    from an.base import DEFAULT_FPS, DEFAULT_RESOLUTION

    meta = project.scene.meta
    kwargs: dict[str, Any] = {
        "mall": project.mall,
        "work_dir": Path(project.root) / ".an" / "render_work",
        "fps": meta.fps or DEFAULT_FPS,
        "resolution": (
            meta.resolution.width or DEFAULT_RESOLUTION[0],
            meta.resolution.height or DEFAULT_RESOLUTION[1],
        ),
    }
    kwargs.update(overrides)
    return RenderContext(**kwargs)


def accept_measured(project_dir: str | Path) -> dict[str, float]:
    """Write each clock-owned shot's MEASURED length into the authored scene.

    Only stored measurements (render first); only shots whose scene duration
    differs. Each ``duration:`` line is patched in place through
    :meth:`an.stores.scenes.ScenesStore.patch_shot_durations`, so the prose and
    comments of ``scene.md`` are kept. Returns ``{shot id: seconds}`` written.
    """
    from an.project import load

    project = load(project_dir)
    ctx = render_context_for(project)
    accepted: dict[str, float] = {}
    for shot in project.scene.timeline:
        renderer = clock_owner_for(shot)
        if renderer is None:
            continue
        m = renderer.measure_duration(shot, ctx, render=False)
        if m is not None and abs(float(m.duration) - shot.duration) > 1e-9:
            accepted[shot.id] = float(m.duration)
    if accepted:
        project.mall["scenes"].patch_shot_durations(accepted)
    return accepted


def report_to_mapping(findings: Iterable["Finding"]) -> Mapping[str, Any]:
    return {"findings": findings_record(findings, kind="measurement")}
