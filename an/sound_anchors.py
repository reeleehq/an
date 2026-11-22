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
- ``at: {when: musket, event: land}`` — the instant an item's hold event
  happens in the compiled shot (the hold report's ``events``: ``grasp``,
  ``place``, ``contact``, ``release``, ``land``, ``bounce``, ``rest``; and a
  ``topple``'s, :mod:`an.stage.topple`), ``nth`` picking the n-th; plus
  ``offset``. A swap's clink lands on the frame the sabre reaches the socket,
  wherever the timing of the reach moves it;
- ``at: {when: book/body, changes: state, to: page_l}`` — the instant of the
  shot's ``nth`` ``set`` (or ``tween``) of that node's property (to that value,
  when ``to`` is given), read from the shot's own actions: no stage document
  is needed, so it works in any shot (an#815); plus ``offset``. A page-turn
  sound follows the page wherever its ``set`` is retimed;
- ``until: {cue: scratch, offset: 0.12}`` — the cue ends at that cue's start
  plus ``offset`` (its ``duration`` is derived).

A cue's second is where its sound's **sync point** goes (``sync`` in its
``sound.json``, :func:`an.sounds.set_sync`: a clip whose clink comes 0.78 s
after a scrape is placed 0.78 s early), so an anchored hit sounds on its frame.

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

__all__ = [
    "SoundAnchorError",
    "anchor_in_document",
    "change_in_shot",
    "crossing_in_document",
    "event_in_document",
    "resolve_cue_anchors",
]

#: The kind a resolved cue's finding is filed under in the render report.
SOUND_FINDING_KIND: str = "sound"


class SoundAnchorError(ValueError):
    """A cue's anchor cannot be resolved: the message says which and why."""


def has_anchors(scene: SceneIR) -> bool:
    """Whether any cue of ``scene`` is timed by the picture or ends at another cue."""
    cues = [*scene.meta.sounds, *(c for s in scene.timeline for c in s.sounds)]
    return any(isinstance(c.at, CueAnchor) or c.until is not None for c in cues)


def _stage_document(shot: Any, ctx: Any, renderer: Any) -> Any:
    from an.stage import draws_on_stage
    from an.stage.cache_key import compiled_document

    if not draws_on_stage(shot):
        raise SoundAnchorError(
            f"shot {shot.id!r} is drawn by {getattr(renderer, 'name', renderer)!r}: "
            "a cue can be timed by the picture only in a stage shot (whose "
            "positions an can compute); give it `at:` in seconds"
        )
    return compiled_document(shot, ctx)


def crossing_in_document(
    doc: Any,
    anchor: CueAnchor,
    *,
    shot_id: str,
    fps: float,
    duration: float,
    where: str,
) -> float:
    """Shot-local seconds at which ``anchor.when``'s centre first reaches ``anchor.reaches``, in a compiled stage document."""
    from an.stage.timeline import (
        evaluate_timeline,
        screen_position,
        timeline_from_scene,
    )

    timeline = timeline_from_scene(doc)
    axis, target = anchor.axis
    index = 0 if axis == "x" else 1
    frames = frame_count(duration, fps)
    previous: tuple[float, float] | None = None
    seen: list[float] = []
    for k in range(frames):
        t = k / fps
        try:
            at = screen_position(doc, anchor.when, pose=evaluate_timeline(timeline, t))
        except (KeyError, ValueError) as e:
            raise SoundAnchorError(
                f"{where}: shot {shot_id!r} has no node {anchor.when!r} on screen "
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
        f"{shot_id!r} (its {axis} runs {low:.1f}..{high:.1f} px over the shot)"
    )


def document_events(doc: Any) -> list[dict[str, Any]]:
    """Every event a compiled stage document records, in time order: by
    convention, the ``events`` list of any report in ``meta.extensions``, at
    its top or one level down (the hold layer's is ``solve.holds.events``,
    the topple pass's ``topple.events``), so a new source registers nothing here."""
    ext = getattr(getattr(doc, "meta", None), "extensions", None) or {}
    events: list[dict[str, Any]] = []

    def take(report: Any) -> None:
        if isinstance(report, dict) and isinstance(report.get("events"), list):
            events.extend(
                e for e in report["events"] if isinstance(e, dict) and "at" in e
            )

    for report in ext.values():
        take(report)
        if isinstance(report, dict):
            for sub in report.values():
                take(sub)
    return sorted(events, key=lambda e: e["at"])


def event_in_document(
    doc: Any, anchor: CueAnchor, *, shot_id: str, where: str
) -> float:
    """Shot-local seconds of ``anchor``'s hold event (the ``nth`` ``event`` of
    item ``when``) in a compiled stage document."""
    events = document_events(doc)
    if not events:
        raise SoundAnchorError(
            f"{where}: shot {shot_id!r} records no hold or topple events, so "
            f"{anchor.describe()!r} cannot be found (an event anchor needs a "
            "grasp, place, release, swap or topple in the shot)"
        )
    from an.ir.events import ALIASES

    names = ALIASES.get(anchor.event, (anchor.event,))
    mine = [e for e in events if e.get("item") == anchor.when]
    matching = [e for e in mine if e["event"] in names]
    if len(matching) >= anchor.nth:
        return float(matching[anchor.nth - 1]["at"])
    if mine:
        have = ", ".join(f"{e['event']} {e['at']:.2f}" for e in mine)
        found = f"the events of {anchor.when!r} in shot {shot_id!r}: {have}"
    else:
        items = sorted({e.get("item") for e in events})
        found = f"no events of {anchor.when!r} in shot {shot_id!r}; items with events: {items}"
    raise SoundAnchorError(
        f"{where}: {anchor.describe()!r} does not happen ({len(matching)} "
        f"{anchor.event} event(s), #{anchor.nth} asked): {found}"
    )


_NO_VALUE = object()


#: How YAML 1.1 spells a boolean: an unquoted ``to: on`` in ``scene.md`` reads
#: as ``True``, while the ``set`` it means stores ``value: 'on'``.
_YAML_BOOLS: dict[bool, frozenset[str]] = {
    True: frozenset({"on", "yes", "y", "true"}),
    False: frozenset({"off", "no", "n", "false"}),
}


def _same_value(a: Any, b: Any) -> bool:
    """Whether an action's value is the anchor's ``to``: numbers within float
    noise, a boolean never a number, and a boolean the string YAML read it from.

    >>> _same_value("on", True), _same_value(True, "Off"), _same_value(1, True)
    (True, False, False)
    >>> _same_value(0.1 + 0.2, 0.3)
    True
    """
    import math

    if isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, bool) and isinstance(b, bool):
            return a is b
        flag, word = (a, b) if isinstance(a, bool) else (b, a)
        return isinstance(word, str) and word.strip().lower() in _YAML_BOOLS[flag]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def change_in_shot(
    shot: Any,
    anchor: CueAnchor,
    *,
    where: str,
    play_extent: Any = None,
) -> float:
    """Shot-local seconds of ``anchor``'s authored change: the start of the
    ``nth`` ``set`` or ``tween`` of ``shot`` whose target is ``anchor.when``
    and property ``anchor.changes`` (and whose value, a set's ``value`` or a
    tween's ``to_value``, is ``anchor.to`` when given), in time order.
    ``play_extent`` is the compile's (:func:`an.stage.compile.play_extent_of`),
    so a ``set`` after a natural-length ``play`` in a ``sequence`` is timed
    where the picture has it.

    >>> from an.ir.schema import SetAction, Shot
    >>> shot = Shot(id="s", actions=[
    ...     SetAction(target="book/body", property="state", value="page_l", at=1.5),
    ...     SetAction(target="book/body", property="state", value="page_r", at=3.0),
    ... ])
    >>> change_in_shot(shot, CueAnchor(when="book/body", changes="state", to="page_r"), where="x")
    3.0
    >>> change_in_shot(shot, CueAnchor(when="book/body", changes="state", nth=2), where="x")
    3.0
    """
    from an.ir.compose import flatten

    changes = []
    for action in shot.actions:
        for flat in flatten(action, play_extent=play_extent):
            a = flat.action
            if getattr(a, "property", None) != anchor.changes:
                continue
            value = getattr(a, "value", getattr(a, "to_value", _NO_VALUE))
            if value is _NO_VALUE:
                continue
            changes.append((float(flat.start), getattr(a, "target", None), value))
    changes.sort(key=lambda c: c[0])
    mine = [c for c in changes if c[1] == anchor.when]
    matching = [c for c in mine if anchor.to is None or _same_value(c[2], anchor.to)]
    if len(matching) >= anchor.nth:
        return matching[anchor.nth - 1][0]
    if mine:
        have = ", ".join(f"{v!r} at {t:.2f} s" for t, _w, v in mine)
        found = f"its {anchor.changes!r} changes in shot {shot.id!r}: {have}"
    else:
        targets = sorted({str(w) for _t, w, _v in changes})
        found = (
            f"no set or tween of {anchor.when}:{anchor.changes} in shot {shot.id!r}"
            + (
                f"; the nodes whose {anchor.changes!r} it changes: {targets}"
                if targets
                else ""
            )
        )
    raise SoundAnchorError(
        f"{where}: {anchor.describe()!r} does not happen ({len(matching)} such "
        f"change(s), #{anchor.nth} asked): {found}"
    )


def anchor_in_document(
    doc: Any,
    anchor: CueAnchor,
    *,
    shot_id: str,
    fps: float,
    duration: float,
    where: str,
    shot: Any = None,
    mall: Any = None,
) -> float:
    """Shot-local seconds of ``anchor`` (an event, an authored change of
    ``shot``, or a crossing), before its ``offset``."""
    if anchor.changes is not None:
        return _change(doc, shot, anchor, where=where, mall=mall)
    if anchor.event is not None:
        return event_in_document(doc, anchor, shot_id=shot_id, where=where)
    return crossing_in_document(
        doc, anchor, shot_id=shot_id, fps=fps, duration=duration, where=where
    )


def _change(
    doc: Any, shot: Any, anchor: CueAnchor, *, where: str, mall: Any = None
) -> float:
    """:func:`change_in_shot`, with the play extent ``doc`` was compiled with
    when there is one (a shot no stage draws flattens with the default)."""
    if shot is None:
        raise SoundAnchorError(
            f"{where}: {anchor.describe()!r} is read from the shot's actions, "
            "and none were given"
        )
    extent = None
    if doc is not None:
        from an.stage.compile import play_extent_of

        extent = play_extent_of(doc, shot, mall)
    return change_in_shot(shot, anchor, where=where, play_extent=extent)


def _crossing(
    shot: Any, ctx: Any, renderer: Any, anchor: CueAnchor, *, where: str
) -> float:
    """Shot-local seconds of ``anchor``: its authored change, its event, or
    when ``anchor.when``'s centre first reaches ``anchor.reaches``."""
    if anchor.changes is not None:
        from an.stage import draws_on_stage
        from an.stage.cache_key import compiled_document

        doc = compiled_document(shot, ctx) if draws_on_stage(shot) else None
        return _change(doc, shot, anchor, where=where, mall=getattr(ctx, "mall", None))
    return anchor_in_document(
        _stage_document(shot, ctx, renderer),
        anchor,
        shot_id=shot.id,
        fps=float(ctx.fps),
        duration=shot.duration,
        where=where,
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
    root = anchor.when.split("/", 1)[0].split("@", 1)[0]
    casting = [
        i
        for i, shot in enumerate(scene.timeline)
        if any(e.id == root for e in shot.entities)
    ]
    if anchor.changes is not None:  # the first shot that has the change (an#815)
        for i in casting:
            try:
                change_in_shot(scene.timeline[i], anchor, where="")
            except SoundAnchorError:
                continue
            return i
    if casting:
        return casting[0]
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
        findings.append(
            Finding(
                severity="info",
                ir_path=f"{path}/at",
                description=(
                    f"{cue.sound} at {t:.2f} s ({anchor.describe()}"
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
