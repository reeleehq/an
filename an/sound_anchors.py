"""Sound cues timed by the picture (an#317): ``at: {when: <node>, reaches: {y: px}}`` and ``until:``.

A record scratch has to land when the last line of a crawl becomes readable.
Writing that second into the scene means solving the crawl's geometry outside
``an``, and every layout change moves the picture away from the sound. Here the
cue names the event instead, and :func:`resolve_cue_anchors` finds the second
when the film is laid out:

- ``at: {when: crawl/line_7, reaches: {y: 840}}`` — the first instant the
  node's on-screen centre crosses that frame row (or ``x`` column), from the
  very document the stage renders (``compiled_document``), through the camera,
  parallax and a crawl's tilt (:func:`an.stage.timeline.screen_position`),
  sampled at every film frame and interpolated between the two that straddle
  it; plus ``offset``;
- ``until: {cue: scratch, offset: 0.12}`` — the cue ends at that cue's start
  plus ``offset`` (its ``duration`` is derived).

It runs on the in-memory settled copy of the scene (as the measured shot
lengths do, :mod:`an.measurements`): ``scene.md`` keeps the anchor, never the
second. Each resolved cue is reported as an ``info`` finding — "scratch at
33.03 s (crawl/line_7 reached y=840)" — which the render report records. An
anchor that cannot be resolved (no such node, never reached, a shot no stage
draws) refuses before any browser launches.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from an.frame_clock import frame_count
from an.ir.schema import CueAnchor, SceneIR, SoundCue
from an.verify._base import Finding

__all__ = ["SoundAnchorError", "resolve_cue_anchors"]

#: The kind a resolved cue's finding is filed under in the render report.
SOUND_FINDING_KIND: str = "sound"


class SoundAnchorError(ValueError):
    """A cue's anchor cannot be resolved: the message says which and why."""


def has_anchors(scene: SceneIR) -> bool:
    """Whether any cue of ``scene`` is timed by the picture or ends at another cue."""
    cues = [*scene.meta.sounds, *(c for s in scene.timeline for c in s.sounds)]
    return any(isinstance(c.at, CueAnchor) or c.until is not None for c in cues)


def _stage_document(shot: Any, ctx: Any, renderer: Any) -> Any:
    engine = getattr(renderer, "engine", None)
    if getattr(engine, "name", None) != "stage":
        raise SoundAnchorError(
            f"shot {shot.id!r} is drawn by {getattr(renderer, 'name', renderer)!r}: "
            "a cue can be timed by the picture only in a stage shot (whose "
            "positions an can compute); give it `at:` in seconds"
        )
    from an.stage.cache_key import compiled_document

    return compiled_document(shot, ctx)


def _crossing(
    shot: Any, ctx: Any, renderer: Any, anchor: CueAnchor, *, where: str
) -> float:
    """Shot-local seconds at which ``anchor.when``'s centre first reaches ``anchor.reaches``."""
    from an.stage.timeline import (
        evaluate_timeline,
        screen_position,
        timeline_from_scene,
    )

    doc = _stage_document(shot, ctx, renderer)
    timeline = timeline_from_scene(doc)
    axis, target = anchor.axis
    index = 0 if axis == "x" else 1
    fps = float(ctx.fps)
    frames = frame_count(shot.duration, ctx.fps)
    previous: tuple[float, float] | None = None
    seen: list[float] = []
    for k in range(frames):
        t = k / fps
        try:
            at = screen_position(doc, anchor.when, pose=evaluate_timeline(timeline, t))
        except (KeyError, ValueError) as e:
            raise SoundAnchorError(
                f"{where}: shot {shot.id!r} has no node {anchor.when!r} on screen "
                f"at {t:.3f} s ({type(e).__name__}: {e}); name a node the shot "
                "draws (a text block's lines are <block>/line_0, line_1, …)"
            ) from e
        gap = at[index] - target
        seen.append(at[index])
        if gap == 0:
            return t
        if previous is not None and (previous[1] < 0) != (gap < 0):
            t0, g0 = previous
            return t0 + (t - t0) * (g0 / (g0 - gap))  # linear between the two frames
        previous = (t, gap)
    low, high = (min(seen), max(seen)) if seen else (float("nan"),) * 2
    raise SoundAnchorError(
        f"{where}: {anchor.when!r} never reaches {axis}={target:g} in shot "
        f"{shot.id!r} (its {axis} runs {low:.1f}..{high:.1f} px over the shot)"
    )


def _shot_with(
    scene: SceneIR, anchor: CueAnchor, renderers: Sequence[Any], ctx: Any
) -> int:
    """The index of the shot a ``meta.sounds`` anchor looks in."""
    ids = [s.id for s in scene.timeline]
    if anchor.shot is not None:
        if anchor.shot not in ids:
            raise SoundAnchorError(
                f"meta.sounds anchor names shot {anchor.shot!r}; the shots are {ids}"
            )
        return ids.index(anchor.shot)
    root = anchor.when.split("/", 1)[0]
    for i, shot in enumerate(scene.timeline):
        if any(e.id == root for e in shot.entities):
            return i
    raise SoundAnchorError(
        f"meta.sounds anchor {anchor.when!r}: no shot casts {root!r}; add "
        f"`shot: <id>` to the anchor (the shots are {ids})"
    )


def _until(cues: list[SoundCue], where: str) -> list[SoundCue]:
    """``cues`` with every ``until`` turned into a ``duration``."""
    out = []
    for j, cue in enumerate(cues):
        if cue.until is None:
            out.append(cue)
            continue
        target = next((c for c in cues if c.sound == cue.until.cue), None)
        if target is None:
            raise SoundAnchorError(
                f"{where}/{j}: `until` names cue {cue.until.cue!r}, which is not "
                f"in the same list (its sounds: {[c.sound for c in cues]})"
            )
        end = float(target.at) + cue.until.offset
        if end <= float(cue.at):
            raise SoundAnchorError(
                f"{where}/{j}: {cue.sound!r} would end at {end:.3f} s, not after "
                f"it starts ({float(cue.at):.3f} s)"
            )
        out.append(cue.model_copy(update={"duration": end - float(cue.at)}))
    return out


def resolve_cue_anchors(
    scene: SceneIR,
    ctx: Any,
    renderers: Sequence[Any],
    *,
    film_starts: Sequence[float],
) -> tuple[SceneIR, list[Finding]]:
    """``scene`` (a copy) with every anchored ``at`` resolved to seconds and every ``until`` to a duration.

    ctx: the render context the shots are compiled under
    renderers: each shot's renderer, in timeline order
    film_starts: each shot's start in film time (a ``meta.sounds`` anchor's
        shot-local second is moved there)
    """
    if not has_anchors(scene):
        return scene, []
    findings: list[Finding] = []

    def resolve(cue: SoundCue, i: int, *, path: str, film: bool) -> SoundCue:
        if not isinstance(cue.at, CueAnchor):
            return cue
        anchor = cue.at
        shot_index = _shot_with(scene, anchor, renderers, ctx) if film else i
        local = _crossing(
            scene.timeline[shot_index], ctx, renderers[shot_index], anchor, where=path
        )
        t = max(0.0, local + anchor.offset + (film_starts[shot_index] if film else 0.0))
        axis, value = anchor.axis
        findings.append(
            Finding(
                severity="info",
                ir_path=f"{path}/at",
                description=(
                    f"{cue.sound} at {t:.2f} s ({anchor.when} reached {axis}={value:g}"
                    + (f", {anchor.offset:+g} s" if anchor.offset else "")
                    + ")"
                ),
            )
        )
        return cue.model_copy(update={"at": t})

    meta = _until(
        [
            resolve(c, 0, path=f"meta/sounds/{j}", film=True)
            for j, c in enumerate(scene.meta.sounds)
        ],
        "meta/sounds",
    )
    shots = [
        shot.model_copy(
            update={
                "sounds": _until(
                    [
                        resolve(c, i, path=f"timeline/{i}/sounds/{j}", film=False)
                        for j, c in enumerate(shot.sounds)
                    ],
                    f"timeline/{i}/sounds",
                )
            }
        )
        for i, shot in enumerate(scene.timeline)
    ]
    resolved = scene.model_copy(
        update={
            "meta": scene.meta.model_copy(update={"sounds": meta}),
            "timeline": shots,
        }
    )
    return resolved, findings


def unresolved(cues: Iterable[SoundCue]) -> list[SoundCue]:
    """The cues whose time is still an anchor (a validator reads them apart)."""
    return [c for c in cues if isinstance(c.at, CueAnchor)]
