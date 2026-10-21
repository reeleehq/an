"""The stage's side of the scene space (ADR 0007): measuring a member's
extent, and lowering a whole scene for the compiler.

The IR layer (:mod:`an.ir.space`) projects points and sizes; what it cannot
know is how big an entity's art is. This module measures that the way the
runtime would draw it, without a browser: it compiles the entity's specimen
shot alone and takes the union of its nodes' boxes
(:func:`an.stage.timeline.node_box`, an#445), relative to the entity's own
placement point. Any registered entity kind with a specimen is measured
the same way, so a genre's rig and the core's props get one rule.

:func:`lower_scene` is the one call the pipeline's entry points make
(`an render`, `an preview`, `an probe`, `an validate`, the orchestrator):
extents, film starts, then :func:`an.ir.space.lower_space`.
"""

from __future__ import annotations

import warnings
from typing import Any, Mapping

from an.ir.schema import AssetRef, SceneIR, Space, stage_specimen
from an.ir.space import Box, Lowered, SpaceError, has_space, lower_space

__all__ = ["lower_scene", "member_extents", "native_box"]


def native_box(
    ref: AssetRef, mall: Mapping[str, Mapping] | None, *, width: int, height: int
) -> Box | None:
    """The box ``ref``'s art occupies at ``stage.scale`` 1, ``(x0, y0, x1, y1)``
    in scene pixels relative to its placement point; ``None`` when it draws
    nothing that can be measured (an unknown ref drawn as a placeholder is
    still measured: that is what the shot would show).

    >>> from an.ir.schema import AssetRef
    >>> native_box(AssetRef(kind="voice", id="v", store="voices", ref="v"), {}, width=320, height=240) is None
    True
    """
    from an.genres.registry import entity_kind
    from an.stage import STAGE_RENDERER_NAMES
    from an.stage.compile import compile_shot
    from an.stage.timeline import node_box, screen_position
    from an.stage.tree import walk_document

    kind = entity_kind(ref.kind)
    specimen = getattr(kind, "specimen", None) if kind is not None else None
    if specimen is None:
        if ref.kind == "voice":
            return None
        specimen = stage_specimen
    bare = ref.model_copy(update={"stage": None})
    shot = specimen(bare)
    if shot.renderer not in STAGE_RENDERER_NAMES:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = compile_shot(shot, mall=mall or {}, width=width, height=height)
    try:
        ox, oy = screen_position(doc, ref.id)
    except Exception:  # noqa: BLE001 — not drawn on the stage
        return None
    boxes = [
        box
        for path, _node in walk_document(doc)
        if (path == ref.id or path.startswith(ref.id + "/"))
        and (box := node_box(doc, path)) is not None
    ]
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes) - ox,
        min(b[1] for b in boxes) - oy,
        max(b[2] for b in boxes) - ox,
        max(b[3] for b in boxes) - oy,
    )


def member_extents(
    space: Space | None,
    mall: Mapping[str, Mapping] | None,
    *,
    width: int,
    height: int,
) -> dict[str, Box | None]:
    """``{id: native box}`` for every positioned or attached member and every
    stream of ``space`` (environments draw plates, not a box, and are left
    out). A member whose art cannot be measured maps to ``None``.
    """
    out: dict[str, Box | None] = {}
    if space is None:
        return out
    for member in space.members:
        if member.kind == "environment":
            continue
        out[member.id] = native_box(member, mall, width=width, height=height)
    if space.travel is not None:
        for stream in space.travel.streams:
            ref = AssetRef(
                kind=stream.kind, id=stream.id, store=stream.store, ref=stream.ref
            )
            out[stream.id] = native_box(ref, mall, width=width, height=height)
    return out


def lower_scene(
    scene: SceneIR,
    mall: Mapping[str, Mapping] | None,
    *,
    fps: float | None = None,
    film_starts: list[float] | None = None,
) -> Lowered:
    """``scene`` as the compiler should see it: every framed shot's placements
    derived from the space (:func:`an.ir.space.lower_space`), with the
    members' extents measured here and each shot's film start from the
    assembled timeline (so a travel's streams keep phase across cuts). A scene
    without a space comes back as it is, at no cost.

    Raises :class:`an.ir.space.SpaceError` for a viewpoint that cannot be
    resolved; `an validate` reports the same error instead of raising.

    >>> lower_scene(SceneIR(), {}).scene.timeline
    []
    """
    if not has_space(scene):
        return Lowered(scene, [])
    width = int(scene.meta.resolution.width)
    height = int(scene.meta.resolution.height)
    extents = member_extents(scene.space, mall, width=width, height=height)
    if film_starts is None:
        film_starts = _film_starts(scene, fps=fps)
    return lower_space(scene, extents=extents, film_starts=film_starts, fps=fps)


def _film_starts(scene: SceneIR, *, fps: float | None) -> list[float] | None:
    """Each shot's start in the film, dissolves overlapped (`an.assemble`);
    ``None`` (the shot sum) when the shots cannot be laid out, which is the
    assembly check's finding, not this one's."""
    from an.assemble import AssemblyError, film_timeline

    rate = float(fps if fps is not None else scene.meta.fps)
    try:
        laid_out = film_timeline(
            list(scene.timeline), fps=rate, closing=scene.meta.closing_transition
        )
    except AssemblyError:
        return None
    return [laid_out.start_seconds(i) for i in range(len(scene.timeline))]


def space_report(lowered: Lowered) -> list[dict[str, Any]]:
    """What `an space show` prints: per framed shot, its entities as the
    compiler sees them (id, kind, at, scale, after) and the lowering's notes."""
    rows: list[dict[str, Any]] = []
    for i, shot in enumerate(lowered.scene.timeline):
        if shot.viewpoint is None:
            continue
        rows.append(
            {
                "shot": shot.id,
                "viewpoint": shot.viewpoint
                if isinstance(shot.viewpoint, str)
                else shot.viewpoint.model_dump(),
                "entities": [
                    {
                        "id": e.id,
                        "kind": e.kind,
                        "at": list(e.stage.at)
                        if e.stage is not None and e.stage.at is not None
                        else None,
                        "scale": e.stage.scale if e.stage is not None else None,
                        "after": e.stage.after if e.stage is not None else None,
                    }
                    for e in shot.entities
                ],
                "actions": len(shot.actions),
                "notes": [
                    {
                        "severity": n.severity,
                        "kind": n.kind,
                        "entity": n.entity,
                        "message": n.message,
                    }
                    for n in lowered.notes_for(i)
                ],
            }
        )
    return rows
