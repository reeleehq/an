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
(else the tallest placed entity) is :data:`DFLT_SUBJECT_HEIGHT` tall. A thing
placed several times is ONE thing at several depths, its largest placement
at ``Z`` and the others farther by their scale (an#603), so a second viewpoint
sees them parallax; a thing placed once takes the depth the master's drawing
order needs (listed first = farthest). When the copies' depths contradict
that order, every member stands at ``Z`` and :attr:`SeededMembers.flat` says
why. The camera itself, the lens and the scene file are the stage's
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

import json

from collections.abc import Collection
from dataclasses import dataclass, field

from an.ir.schema import Shot, WorldMember
from an.ir.world import Extents, member_of

__all__ = ["DFLT_SUBJECT_HEIGHT", "SeededMembers", "seed_members"]

#: How tall the tallest placed character (else the tallest placed entity) is
#: in the seeded world, by default: a person, in metres (the world's units are
#: metres: `DFLT_WORLD_GRAVITY`).
DFLT_SUBJECT_HEIGHT: float = 1.7


@dataclass(frozen=True)
class SeededMembers:
    """What :func:`seed_members` derived: the members (environments first, as
    listed), the depth the placed ones stand at, and the drawn entities it left
    out (``{id: why}``), which stay listed in the shot and placed by hand."""

    members: list[WorldMember]
    depth: float
    skipped: dict[str, str] = field(default_factory=dict)
    #: Why the copies of one thing could not take the depths their scales say
    #: (an#603), so every member stands at ``depth``; ``None`` when they did.
    flat: str | None = None


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
    with a ``stage.at`` becomes a member (:func:`_depths`: ``depth``, default
    where the tallest character, else the tallest thing, is
    :data:`DFLT_SUBJECT_HEIGHT` tall), every environment a member
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
    defaulted = depth is None
    if defaulted:
        depth = DFLT_SUBJECT_HEIGHT * focal / _reference_height(placed)
    depths, flat = _depths(placed, depth)
    if defaulted:
        # The order may have pushed the reference (the person) deeper: a uniform
        # rescale keeps every projection, the order and the copies' ratios, and
        # stands it at DFLT_SUBJECT_HEIGHT again.
        ref = _reference_index(placed)
        depths = [z * depth / depths[ref] for z in depths]
    members = []
    for (_i, e, (sx, sy), scale, native), z in zip(placed, depths):
        k = z / focal  # world units per screen pixel at that depth
        members.append(
            member_of(
                e,
                at=(_tidy(sx * k), _tidy(sy * k), _tidy(z)),
                height=_tidy(scale * native * k),
            )
        )
    environments = [member_of(e) for e in shot.entities if e.kind == "environment"]
    return SeededMembers([*environments, *members], depth, skipped, flat)


def _depths(placed, depth: float) -> tuple[list[float], str | None]:
    """Each placed member's depth, and why they are all ``depth`` when they are.

    A thing placed several times (same store, ref, library and overrides, same
    measured height: :func:`_thing`) is ONE thing at several depths: its largest
    placement at ``depth``, a copy drawn at half that scale twice as far
    (an#603). Those depths are fixed. A thing placed once may stand anywhere on
    its line of sight and still project as placed, so it takes the depth the
    draw order needs: the lowering draws far first, and the master lists back
    to front, so each member is at least as deep as everything listed after
    it, and at least ``depth``. A member drawn ``after`` an anchor is placed by
    that anchor, not by its depth, and is left out of the order. When two
    fixed copies are listed against their depths, the master could not come
    back drawn as it was: every member stands at ``depth``."""
    largest: dict[tuple, float] = {}
    count: dict[tuple, int] = {}
    for _i, e, _at, scale, native in placed:
        key = _thing(e, native)
        largest[key] = max(largest.get(key, 0.0), scale)
        count[key] = count.get(key, 0) + 1
    fixed = [
        depth * largest[_thing(e, n)] / scale if count[_thing(e, n)] > 1 else None
        for _i, e, _at, scale, n in placed
    ]
    out: list[float] = [depth] * len(placed)
    deepest = 0.0  # of everything listed after
    for j in range(len(placed) - 1, -1, -1):
        e = placed[j][1]
        ordered = e.stage is None or e.stage.after is None
        if fixed[j] is not None:
            if ordered and fixed[j] < deepest - _DEPTH_EPS * deepest:
                return [depth] * len(placed), (
                    f"{e.id!r} would be drawn behind something farther than it: with "
                    "each thing's largest copy at one depth, its copies' depths do not "
                    "keep the master's drawing order, so every member stands at depth "
                    f"{depth:.4g} (move members along their line of sight to give them "
                    "depth by hand)"
                )
            out[j] = fixed[j]
        else:
            out[j] = max(depth, deepest) if ordered else depth
        if ordered:
            deepest = max(deepest, out[j])
    return out, None


def _thing(e, native: float) -> tuple:
    """What makes two placements one thing: the same art, the same size."""
    overrides = json.dumps(e.overrides or {}, sort_keys=True, default=str)
    return (
        e.store,
        e.ref,
        json.dumps(e.library, sort_keys=True, default=str),
        overrides,
        round(native, 6),
    )


#: The kind whose tallest placement sets the default depth (a person).
CHARACTER_KIND: str = "character"
#: A relative slack when comparing two recovered depths.
_DEPTH_EPS: float = 1e-9


def _reference_index(placed) -> int:
    """Which placement the default depth makes :data:`DFLT_SUBJECT_HEIGHT`
    tall: the tallest placed character when there is one (a person, which is
    what the default height is), else the tallest placed thing (an#603: a sun
    or a building would make the world's units read as something else)."""
    people = [j for j, (_i, e, *_r) in enumerate(placed) if e.kind == CHARACTER_KIND]
    pool = people or range(len(placed))
    return max(pool, key=lambda j: placed[j][3] * placed[j][4])


def _reference_height(placed) -> float:
    """The screen height of :func:`_reference_index`'s placement."""
    _i, _e, _at, scale, native = placed[_reference_index(placed)]
    return scale * native


#: Significant digits a derived coordinate is written with: far below a
#: pixel at any depth a shot frames, and short enough to read in `scene.md`.
_DIGITS: int = 9


def _tidy(v: float) -> float:
    """``v`` rounded to :data:`_DIGITS` significant digits (``0.1 * 3`` reads as 0.3)."""
    return float(f"{v:.{_DIGITS}g}")
