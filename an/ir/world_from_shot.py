"""World members from a shot placed by hand (an#514): the projection inverted.

A scene placed by hand (every production written before ADR 0009) adopts a
`world` without being re-authored: each placed entity of a *master* shot is
stood at one depth ``Z`` in front of a camera at the origin looking down
``+z``, with its screen position and scale inverted through the pinhole
(:mod:`an.ir.world`):

    x = sx · Z / f        y = sy · Z / f        height = scale · native · Z / f

so the world lowers back to exactly the placements the shot already has, and
the master's own ``stage`` lines agree with it (the ``viewpoint`` check says
nothing). ``Z`` defaults to the depth at which the tallest placed character
(else the tallest placed entity) is :data:`DFLT_SUBJECT_HEIGHT` tall. A ref
placed once stands at ``Z``; a ref placed several times is ONE thing, one
height, at several depths, its largest placement at ``Z`` and the others
farther by their scale (an#603), so a second viewpoint sees them parallax,
when those depths agree with the order the master draws them in (listed first
= farthest; else every member stands at ``Z``, so the master is unchanged). Any
other depth is the author's to say, by moving a member along its line of sight
(``at`` and ``height`` scaled together keep it where the master shows it). The camera itself, the lens and the scene file are the stage's
(:func:`an.stage.world.seed_world`).

>>> from an.ir.schema import AssetRef, Shot, StagePlacement
>>> shot = Shot(id="master", duration=1.0, entities=[
...     AssetRef(kind="prop", id="lamp", store="props", ref="lamp",
...              stage=StagePlacement(at=(100.0, 50.0), scale=0.5))])
>>> seeded = seed_members(shot, extents={"lamp": (-10.0, -200.0, 10.0, 0.0)}, focal=500.0)
>>> m = seeded.members[0]
>>> m.at, m.height, seeded.depth
((1.7, 0.85, 8.5), 1.7, 8.5)
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from an.ir.schema import Shot, WorldMember
from an.ir.world import Extents, member_of

__all__ = ["DFLT_SUBJECT_HEIGHT", "SeededMembers", "seed_members"]

#: How tall the tallest placed entity is in the seeded world, by default:
#: a person, in metres (the world's units are metres: `DFLT_WORLD_GRAVITY`).
DFLT_SUBJECT_HEIGHT: float = 1.7


@dataclass(frozen=True)
class SeededMembers:
    """What :func:`seed_members` derived: the members (environments first, as
    listed), the depth the placed ones stand at, and the drawn entities it left
    out (``{id: why}``), which stay listed in the shot and placed by hand."""

    members: list[WorldMember]
    depth: float
    skipped: dict[str, str] = field(default_factory=dict)


def seed_members(
    shot: Shot,
    *,
    extents: Extents,
    focal: float,
    depth: float | None = None,
    drawn: Collection[str] | None = None,
) -> SeededMembers:
    """The world members ``shot``'s hand placements are a view of, from a
    camera at the origin with focal length ``focal`` (pixels): every entity
    with a ``stage.at`` becomes a member at ``depth`` (default: where the
    tallest is :data:`DFLT_SUBJECT_HEIGHT` tall), every environment a member
    as it is. ``extents`` is each entity's native box (``None``: unmeasured);
    ``drawn`` the ids of the entities the stage draws (default: every one
    ``extents`` names), the others (a voice) being no member of a picture.

    Raises ``ValueError`` when nothing is placed by hand, for a non-positive
    ``depth`` or ``focal``, and for a drawn entity left out (no ``stage.at``,
    or unmeasured) that is listed before a member: a framed shot draws its
    members first, so it would move on top of them."""
    if not focal > 0:
        raise ValueError(f"`focal` must be positive, not {focal!r}")
    if depth is not None and not depth > 0:
        raise ValueError(f"`depth` must be positive, not {depth!r}")
    drawn = set(extents) if drawn is None else set(drawn)
    skipped: dict[str, str] = {}
    placed = []  # (index, entity, (sx, sy), scale, native height)
    for i, e in enumerate(shot.entities):
        if e.kind == "environment" or e.id not in drawn:
            continue
        box = extents.get(e.id)
        if e.stage is None or e.stage.at is None:
            skipped[e.id] = "it has no `stage.at` (the compiler lays it out)"
        elif box is None or box[3] - box[1] <= 0:
            skipped[e.id] = "its art could not be measured"
        else:
            at = tuple(float(v) for v in e.stage.at)
            placed.append((i, e, at, float(e.stage.scale), box[3] - box[1]))
    last = max((i for i, *_ in placed), default=-1)
    for i, e in enumerate(shot.entities):
        if e.id in skipped and i < last:
            raise ValueError(
                f"{e.id!r} would be left out ({skipped[e.id]}) and it is listed before "
                "entities that become members: a framed shot draws its members first, "
                f"so it would move on top of them. Give {e.id!r} a `stage.at`, or list "
                "it after them."
            )
    if not placed:
        raise ValueError(
            f"shot {shot.id!r} places nothing by hand (no entity with a `stage.at` "
            "whose art can be measured): there is no view to invert"
        )
    if depth is None:
        depth = DFLT_SUBJECT_HEIGHT * focal / _reference_height(placed)
    # One height per ref: a ref placed at several scales is one thing at several
    # depths (an#603). Its largest placement stands at `depth`; one drawn at
    # half that scale stands twice as far, and every one projects as placed.
    largest: dict[str, float] = {}
    for _i, e, _at, scale, _native in placed:
        largest[e.ref] = max(largest.get(e.ref, 0.0), scale)
    depths = [depth * largest[e.ref] / scale for _i, e, _at, scale, _n in placed]
    # The lowering draws far first, so recovered depths must agree with the
    # master's own drawing order (listed first = behind): else the master would
    # come back drawn differently, and every member stays at one depth.
    by_depth = all(a >= b for a, b in zip(depths, depths[1:]))
    members = []
    for _i, e, (sx, sy), scale, native in placed:
        z = depth * largest[e.ref] / scale if by_depth else depth
        k = z / focal  # world units per screen pixel at that depth
        members.append(
            member_of(
                e,
                at=(_tidy(sx * k), _tidy(sy * k), _tidy(z)),
                height=_tidy(
                    (largest[e.ref] if by_depth else scale) * native * depth / focal
                ),
            )
        )
    environments = [member_of(e) for e in shot.entities if e.kind == "environment"]
    return SeededMembers([*environments, *members], depth, skipped)


def _reference_height(placed) -> float:
    """The screen height the default depth makes :data:`DFLT_SUBJECT_HEIGHT`
    tall: the tallest placed character when there is one (a person, which is
    what the default height is), else the tallest placed thing (an#603: a sun
    or a building would make the world's units read as something else)."""
    people = [
        scale * native for _i, e, _at, scale, native in placed if e.kind == "character"
    ]
    return max(people or [scale * native for *_, scale, native in placed])


#: Significant digits a derived coordinate is written with: far below a
#: pixel at any depth a shot frames, and short enough to read in `scene.md`.
_DIGITS: int = 9


def _tidy(v: float) -> float:
    """``v`` rounded to :data:`_DIGITS` significant digits (``0.1 * 3`` reads as 0.3)."""
    return float(f"{v:.{_DIGITS}g}")
