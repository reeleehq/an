"""A world from a shot placed by hand (an#514): the inverse of the projection.

A scene placed by hand (every production written before ADR 0009) adopts a
`world` without being re-authored: each placed entity of a *master* shot is
stood at one depth ``Z`` in front of a camera at the origin looking down
``+z``, with its screen position and scale inverted through the pinhole
(:mod:`an.ir.world`):

    x = sx · Z / f        y = sy · Z / f        height = scale · native · Z / f

so the world lowers back to exactly the placements the shot already has, and
the master's own ``stage`` lines agree with it (the ``viewpoint`` check says
nothing). ``Z`` defaults to the depth at which the tallest placed entity is
:data:`DFLT_SUBJECT_HEIGHT` tall, so the world's units read as metres. Every
member is at the same depth: depth is what the other shots' viewpoints add
by hand; this only gives them a world to frame.

>>> from an.ir.schema import AssetRef, Shot, StagePlacement
>>> shot = Shot(id="master", duration=1.0, entities=[
...     AssetRef(kind="prop", id="lamp", store="props", ref="lamp",
...              stage=StagePlacement(at=(100.0, 50.0), scale=0.5))])
>>> seeded = world_from_shot(shot, extents={"lamp": (-10.0, -200.0, 10.0, 0.0)}, focal=500.0)
>>> m = seeded.world.members[0]
>>> m.at, m.height, seeded.depth
((1.7, 0.85, 8.5), 1.7, 8.5)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from an.ir.schema import Shot, Viewpoint, World, WorldMember
from an.ir.world import Extents

__all__ = ["DFLT_SUBJECT_HEIGHT", "SeededWorld", "world_from_shot"]

#: How tall the tallest placed entity is in the seeded world, by default:
#: a person, in metres (the world's units are metres: `DFLT_WORLD_GRAVITY`).
DFLT_SUBJECT_HEIGHT: float = 1.7


@dataclass(frozen=True)
class SeededWorld:
    """What :func:`world_from_shot` derived: the world, the master's viewpoint,
    the depth every member stands at, and the entities it left out (``{id:
    why}``), which stay listed in the shot and placed by hand."""

    world: World
    viewpoint: Viewpoint
    depth: float
    skipped: dict[str, str] = field(default_factory=dict)


def world_from_shot(
    shot: Shot,
    *,
    extents: Extents,
    focal: float,
    depth: float | None = None,
    subject_height: float = DFLT_SUBJECT_HEIGHT,
) -> SeededWorld:
    """The world ``shot``'s hand placements are a view of, from a camera at the
    origin with focal length ``focal`` (pixels): every entity with a
    ``stage.at`` becomes a member at ``depth`` (default: where the tallest is
    ``subject_height`` tall), every environment a member as it is; an entity
    with no ``stage.at``, or whose art ``extents`` could not measure, is left
    out (``skipped``). The viewpoint is that camera.

    Raises ``ValueError`` when nothing in the shot is placed by hand, or for a
    non-positive ``depth``, ``focal`` or ``subject_height``."""
    for name, v in (("focal", focal), ("subject_height", subject_height)):
        if not v > 0:
            raise ValueError(f"`{name}` must be positive, not {v!r}")
    if depth is not None and not depth > 0:
        raise ValueError(f"`depth` must be positive, not {depth!r}")
    skipped: dict[str, str] = {}
    placed = []  # (entity, (sx, sy), scale, native height)
    for e in shot.entities:
        if e.kind == "environment":
            continue
        if e.stage is None or e.stage.at is None:
            skipped[e.id] = "it has no `stage.at` (the compiler lays it out)"
            continue
        box = extents.get(e.id)
        if box is None or box[3] - box[1] <= 0:
            skipped[e.id] = "its art could not be measured"
            continue
        sx, sy = (float(v) for v in e.stage.at)
        placed.append((e, (sx, sy), float(e.stage.scale), box[3] - box[1]))
    if not placed:
        raise ValueError(
            f"shot {shot.id!r} places nothing by hand (no entity with a `stage.at` "
            "whose art can be measured): there is no view to invert"
        )
    if depth is None:
        tallest = max(scale * native for _e, _at, scale, native in placed)
        depth = subject_height * focal / tallest
    k = depth / focal  # world units per screen pixel at that depth
    members = [
        WorldMember(
            kind=e.kind,
            id=e.id,
            store=e.store,
            ref=e.ref,
            overrides=e.overrides,
            library=e.library,
            joints=e.joints,
            at=(_tidy(sx * k), _tidy(sy * k), _tidy(depth)),
            height=_tidy(scale * native * k),
            after=e.stage.after,
        )
        for e, (sx, sy), scale, native in placed
    ]
    environments = [
        WorldMember(**e.model_dump(exclude={"stage"}, exclude_none=True))
        for e in shot.entities
        if e.kind == "environment"
    ]
    return SeededWorld(
        world=World(members=[*environments, *members]),
        viewpoint=Viewpoint(at=(0.0, 0.0, 0.0), focal=focal),
        depth=depth,
        skipped=skipped,
    )


#: Significant digits a derived coordinate is written with: far below a
#: pixel at any depth a shot frames, and short enough to read in `scene.md`.
_DIGITS: int = 9


def _tidy(v: float) -> float:
    """``v`` rounded to :data:`_DIGITS` significant digits (``0.1 * 3`` reads as 0.3)."""
    return float(f"{v:.{_DIGITS}g}")
