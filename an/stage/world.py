"""The stage's side of the scene world (ADR 0009): measuring a member's
extent, and lowering a whole scene for the compiler.

The IR layer (:mod:`an.ir.world`) projects points and sizes; what it cannot
know is how big an entity's art is. This module measures that the way the
runtime would draw it, without a browser: it compiles the entity's specimen
shot alone and takes the union of its nodes' boxes
(:func:`an.stage.timeline.node_box`, an#445), relative to the entity's own
placement point. Any registered entity kind with a specimen is measured
the same way, so a genre's rig and the core's props get one rule.

:func:`lower_scene` is the one call the pipeline's entry points make
(`an render`, `an preview`, `an probe`, `an validate`, the orchestrator):
extents, film starts, then :func:`an.ir.world.lower_world`.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import warnings
from typing import TYPE_CHECKING, Any, Mapping

from an.ir.schema import AssetRef, SceneIR, World, stage_specimen
from an.ir.world import Box, Lowered, WorldError, has_world, lower_world

if TYPE_CHECKING:
    from an.ir.world_from_shot import SeededMembers

__all__ = [
    "lower_scene",
    "seed_world",
    "lowered_or_same",
    "member_extents",
    "native_box",
    "world_report",
]


#: Entity kinds the stage draws nothing for: what no shot places.
UNDRAWN_KINDS: frozenset[str] = frozenset({"voice"})


def draws(ref: AssetRef) -> bool:
    """Whether the stage draws ``ref`` (an environment, a prop, a character:
    anything but :data:`UNDRAWN_KINDS`).

    >>> draws(AssetRef(kind="voice", id="v", store="voices", ref="v"))
    False
    """
    return ref.kind not in UNDRAWN_KINDS


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

    if not draws(ref):
        return None
    kind = entity_kind(ref.kind)
    specimen = getattr(kind, "specimen", None) if kind is not None else None
    if specimen is None:
        specimen = stage_specimen
    # Alone in its specimen: no placement, and no joint to an entity that is
    # not there (a hand holding a prop would not compile, an#514 review).
    bare = ref.model_copy(update={"stage": None, "joints": []})
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
    world: World | None,
    mall: Mapping[str, Mapping] | None,
    *,
    width: int,
    height: int,
    problems: dict[str, str] | None = None,
) -> dict[str, Box | None]:
    """``{id: native box}`` for every positioned or attached member and every
    stream of ``world`` (environments draw plates, not a box, and are left
    out). A member whose art cannot be measured maps to ``None`` — a missing
    ref, an unregistered kind, a compile that refuses — and ``problems`` (an
    out-parameter, like the compiler's ``textures``) records why, so the
    lowering can say it instead of a traceback (ADR 0009: validate reports).
    """
    out: dict[str, Box | None] = {}
    if world is None:
        return out

    def measure(ref: AssetRef) -> Box | None:
        try:
            return native_box(ref, mall, width=width, height=height)
        except Exception as e:  # noqa: BLE001 — a measurement that cannot be made is a note
            if problems is not None:
                problems[ref.id] = f"{type(e).__name__}: {e}"
            return None

    for member in world.members:
        if member.kind == "environment":
            continue
        out[member.id] = measure(member)
    if world.travel is not None:
        for stream in world.travel.streams:
            out[stream.id] = measure(
                AssetRef(
                    kind=stream.kind, id=stream.id, store=stream.store, ref=stream.ref
                )
            )
    return out


def plane_geometry(
    world: World | None, mall: Mapping[str, Mapping] | None
) -> dict[str, dict[str, tuple[tuple[float, float], Box | None]]]:
    """``{member id: {plane: (offset, box)}}`` for every environment member of
    ``world`` that gives a plane a world depth (an#503): where each of its
    planes sits on screen (``Plane.offset``), which is where the lowering
    anchors a plane at a depth, and the box it draws around that point
    (:func:`an.stage.environments.plane_rect`; ``None`` for an image whose
    drawn size depends on art not measured here), which says when it is on
    screen. An environment that cannot be read is left out (the compiler and
    the validator say why).

    >>> doc = {"kind": "EnvironmentDescriptor", "name": "e",
    ...        "planes": [{"name": "hill", "offset": [0, 80], "size": [320, 80]}]}
    >>> from an.ir.schema import World, WorldMember
    >>> world = World(members=[WorldMember(kind="environment", id="set",
    ...     store="environments", ref="e", depths={"hill": 20.0})])
    >>> plane_geometry(world, {"environments": {"e": doc}})
    {'set': {'hill': ((0.0, 80.0), (-160.0, -40.0, 160.0, 40.0))}}
    """
    from an.stage.environments import (
        environment_from_document,
        plane_art_size,
        plane_rect,
    )

    store = (mall or {}).get("environments") or {}
    root = getattr(store, "_root", None)

    def geometry(plane, ref: str) -> tuple[tuple[float, float], Box | None]:
        ox, oy = (float(v) for v in plane.offset)
        rect = plane_rect(
            plane.model_copy(update={"parallax": None, "depth": 1.0}),
            plane_art_size(root, ref, plane),  # an image's own extent (an#599)
        )
        box = (
            None
            if rect is None
            else (rect[0] - ox, rect[1] - oy, rect[2] - ox, rect[3] - oy)
        )
        return (ox, oy), box

    out: dict[str, dict[str, tuple[tuple[float, float], Box | None]]] = {}
    for member in world.members if world is not None else ():
        if not member.depths:
            continue
        try:
            env = environment_from_document(store[member.ref])
        except Exception:  # noqa: BLE001 — a missing or malformed environment is another check's
            continue
        out[member.id] = {p.name: geometry(p, member.ref) for p in env.planes}
    return out


def seed_world(
    scene: SceneIR,
    mall: Mapping[str, Mapping] | None,
    shot_id: str,
    *,
    focal: float | None = None,
    depth: float | None = None,
) -> tuple[SceneIR, "SeededMembers"]:
    """``scene`` with a world derived from its hand-placed shot ``shot_id``
    (:func:`an.ir.world_from_shot.seed_members`, an#514): the members, and one
    viewpoint named after the shot, a camera at the origin with ``focal``
    (pixels; default: the default field of view, so the world frames the same
    at any resolution). The shot names that viewpoint and keeps its own
    ``stage`` lines, which agree with the world. The art is measured here,
    as the lowering measures it (:func:`native_box`; a measurement that fails
    leaves the entity out, said in ``skipped``).

    Raises ``ValueError`` for a scene that already has a world, an unknown
    shot or one that already names a viewpoint, and what
    :func:`~an.ir.world_from_shot.seed_members` refuses.

    >>> seed_world(SceneIR(), {}, "a")
    Traceback (most recent call last):
    ...
    ValueError: no shot 'a' in the scene (its shots: [])
    """
    from an.ir.schema import Viewpoint
    from an.ir.world import focal_length
    from an.ir.world_from_shot import seed_members

    if scene.world is not None:
        raise ValueError(
            "the scene already has a `world`: a world is derived from a shot once; "
            "add members or viewpoints to it by hand"
        )
    index = next((i for i, s in enumerate(scene.timeline) if s.id == shot_id), None)
    if index is None:
        raise ValueError(
            f"no shot {shot_id!r} in the scene (its shots: "
            f"{[s.id for s in scene.timeline]})"
        )
    shot = scene.timeline[index]
    if shot.viewpoint is not None:
        raise ValueError(f"shot {shot_id!r} already names a viewpoint")
    width = int(scene.meta.resolution.width)
    height = int(scene.meta.resolution.height)
    drawn = [e for e in shot.entities if e.kind != "environment" and draws(e)]
    extents: dict[str, Box | None] = {}
    for e in drawn:
        try:
            extents[e.id] = native_box(e, mall, width=width, height=height)
        except Exception:  # noqa: BLE001 — unmeasured is a reason to leave it out, as `member_extents` says
            extents[e.id] = None
    lens = Viewpoint(at=(0.0, 0.0, 0.0), focal=focal)
    seeded = seed_members(
        shot, extents=extents, focal=focal_length(lens, width=width), depth=depth
    )
    world = World(members=seeded.members, viewpoints={shot_id: lens})
    timeline = list(scene.timeline)
    timeline[index] = shot.model_copy(update={"viewpoint": shot_id})
    return scene.model_copy(update={"world": world, "timeline": timeline}), seeded


def lower_scene(
    scene: SceneIR,
    mall: Mapping[str, Mapping] | None,
    *,
    fps: float | None = None,
    film_starts: list[float] | None = None,
    project_dir: str | Path | None = None,
    continues: bool = True,
) -> Lowered:
    """``scene`` as the compiler should see it: every framed shot's placements
    derived from the world (:func:`an.ir.world.lower_world`), with the
    members' extents measured here and each shot's film start from the
    assembled timeline (so a travel's streams keep phase across cuts). A scene
    without a world comes back as it is, at no cost. Then every shot's
    ``continue:`` is resolved (:func:`an.continuity.continue_shots`, an#542):
    a shot that continues another opens as that one ends (``project_dir``:
    where a sibling scene file is read; default the mall's; ``continues``:
    off for the world alone, as `an validate` reports the two apart).

    Raises :class:`an.ir.world.WorldError` for a viewpoint that cannot be
    resolved; `an validate` reports the same error instead of raising.

    >>> lower_scene(SceneIR(), {}).scene.timeline
    []
    """
    lowered = _lower_world(scene, mall, fps=fps, film_starts=film_starts)
    return (
        with_continues(lowered, mall, fps=fps, project_dir=project_dir)
        if continues
        else lowered
    )


def with_continues(
    lowered: Lowered,
    mall: Mapping[str, Mapping] | None,
    *,
    fps: float | None = None,
    project_dir: str | Path | None = None,
) -> Lowered:
    """``lowered`` with every ``continue:`` resolved (an#542), and how many
    actions each continued shot gained in front of the author's."""
    from an.continuity import continue_shots

    continued = continue_shots(lowered.scene, mall, fps=fps, project_dir=project_dir)
    if continued is lowered.scene:
        return lowered
    carried = {
        i: len(new.actions) - len(old.actions)
        for i, (old, new) in enumerate(zip(lowered.scene.timeline, continued.timeline))
        if new is not old
    }
    return dataclasses.replace(lowered, scene=continued, carried=carried)


def lower_scene_world(
    scene: SceneIR, mall: Mapping[str, Mapping] | None, *, fps: float | None = None
) -> SceneIR:
    """``scene`` lowered through its world only: what a continuation reads a
    sibling scene file as (:func:`an.continuity.continue_shots`)."""
    return _lower_world(scene, mall, fps=fps, film_starts=None).scene


def _lower_world(
    scene: SceneIR,
    mall: Mapping[str, Mapping] | None,
    *,
    fps: float | None,
    film_starts: list[float] | None,
) -> Lowered:
    """The world half of :func:`lower_scene`."""
    if not has_world(scene):
        return Lowered(scene, [])
    width = int(scene.meta.resolution.width)
    height = int(scene.meta.resolution.height)
    problems: dict[str, str] = {}
    extents = member_extents(
        scene.world, mall, width=width, height=height, problems=problems
    )
    if film_starts is None:
        film_starts = _film_starts(scene, fps=fps)
    return lower_world(
        scene,
        extents=extents,
        film_starts=film_starts,
        fps=fps,
        extent_problems=problems,
        plane_geometry=plane_geometry(scene.world, mall),
    )


def lowered_or_same(
    scene: SceneIR, mall: Mapping[str, Mapping] | None, *, fps: float | None = None
) -> SceneIR:
    """The lowered scene, or ``scene`` itself when it has no world or its
    world cannot be lowered: for the walks that must see what a framed shot
    draws (credits, publishability) but are not where a world error is
    reported (validate is)."""
    from an.continuity import ContinuityError

    try:
        return lower_scene(scene, mall, fps=fps).scene
    except ContinuityError:  # reported by validate; the world still lowers
        try:
            return lower_scene(scene, mall, fps=fps, continues=False).scene
        except Exception:  # noqa: BLE001 — reported by validate, not here
            return scene
    except Exception:  # noqa: BLE001 — reported by validate, not here
        return scene


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


def world_report(lowered: Lowered) -> list[dict[str, Any]]:
    """What `an world show` prints: per framed shot, its entities as the
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
