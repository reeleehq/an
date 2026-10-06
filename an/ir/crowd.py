"""Crowds: many placed copies of one asset, and an action copied across them (an#437).

An army of unit icons, a swarm of blobs, a grid of data points: one asset
placed many times, moved together or in a ripple. Like ``sequence`` and
``parallel`` these are authoring combinators that flatten to the canonical
form: :func:`crowd` returns ordinary entities (``AssetRef`` s with a
``stage`` placement) and :func:`fan_out` ordinary actions, so the scene
document, ``scene.md`` and every renderer see nothing new.

>>> members = crowd("army", ref="soldier", count=6, layout="grid", area=(-300, 0, 300, 200))
>>> [m.id for m in members]
['army_0', 'army_1', 'army_2', 'army_3', 'army_4', 'army_5']
>>> [m.stage.at for m in members]
[(-225.0, 50.0), (-75.0, 50.0), (75.0, 50.0), (225.0, 50.0), (-75.0, 150.0), (75.0, 150.0)]
>>> from an.ir.compose import tween, stagger, flatten
>>> hop = tween("army", "y", to=-40.0, duration=0.3)
>>> [(f.action.target, f.start) for f in flatten(stagger(0.1, *fan_out(hop, members[:3])))]
[('army_0', 0.0), ('army_1', 0.1), ('army_2', 0.2)]

Members are listed back row first (the smallest ``y``: the top of the
frame), so a nearer row draws over a farther one, and they are numbered in
that order. Every placement is deterministic: the same arguments and
``seed`` give the same crowd on every machine.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from typing import Any

from an.genres.registry import entity_kind
from an.ir.schema import AssetRef, StagePlacement

__all__ = ["CROWD_LAYOUTS", "DFLT_CROWD_AREA", "crowd", "fan_out", "member_id"]

#: How a crowd fills its area: a grid of rows (an army, a data grid), one row
#: (a chorus line), or a seeded scatter (a swarm, a crowd at a rally).
CROWD_LAYOUTS: tuple[str, ...] = ("grid", "row", "scatter")
#: Where a crowd stands when no area is given, in scene pixels about the stage
#: centre: a band below the centre of a 1280×720 frame.
DFLT_CROWD_AREA: tuple[float, float, float, float] = (-480.0, -60.0, 480.0, 240.0)


def member_id(crowd_id: str, k: int) -> str:
    """The id of a crowd's ``k``-th member.

    >>> member_id("army", 3)
    'army_3'
    """
    return f"{crowd_id}_{k}"


def crowd(
    id: str,
    *,
    ref: str,
    count: int,
    kind: str = "prop",
    store: str | None = None,
    layout: str = "grid",
    area: Sequence[float] = DFLT_CROWD_AREA,
    scale: float = 1.0,
    scale_jitter: float = 0.0,
    jitter: float = 0.0,
    seed: int = 0,
) -> list[AssetRef]:
    """``count`` entities of one asset (``kind``/``store``/``ref``) placed in ``area``.

    id: the crowd's name; member ``k`` is ``<id>_<k>`` (:func:`member_id`)
    ref: the asset every member draws
    count: how many (at least 1)
    kind: the entity kind (``prop``, or a genre's, such as ``character``)
    store: the store the asset lives in (default: the kind's registered store)
    layout: ``grid`` (rows filled from the back), ``row`` or ``scatter``
    area: ``(x0, y0, x1, y1)`` in scene pixels about the stage centre; a
        member's stage point stands inside it
    scale: every member's stage scale
    scale_jitter: each member's scale varies by up to this fraction (``0.1``: ±10%)
    jitter: each grid or row member moves by up to this fraction of its cell
    seed: the scatter and the jitters are drawn from it

    >>> [m.stage.at for m in crowd("line", ref="dot", count=3, layout="row", area=(0, 0, 300, 100))]
    [(50.0, 50.0), (150.0, 50.0), (250.0, 50.0)]
    >>> crowd("x", ref="dot", count=0)
    Traceback (most recent call last):
    ...
    ValueError: a crowd needs at least one member; got count=0
    """
    if count < 1:
        raise ValueError(f"a crowd needs at least one member; got count={count}")
    if layout not in CROWD_LAYOUTS:
        raise ValueError(
            f"unknown crowd layout {layout!r}; known: {', '.join(CROWD_LAYOUTS)}"
        )
    x0, y0, x1, y1 = (float(v) for v in area)
    if not (x1 > x0 and y1 > y0):
        raise ValueError(
            f"a crowd's area (x0, y0, x1, y1) must have x1 > x0 and y1 > y0; got {tuple(area)}"
        )
    for name, value in (("jitter", jitter), ("scale_jitter", scale_jitter)):
        if not 0.0 <= value < 1.0:
            raise ValueError(f"{name} is a fraction in [0, 1); got {value}")
    if store is None:
        registered = entity_kind(kind)
        store = registered.store if registered is not None else None
        if store is None:
            raise ValueError(
                f"entity kind {kind!r} has no registered store: pass store="
            )
    rng = random.Random(seed)
    points = _layout_points(layout, count, (x0, y0, x1, y1), jitter=jitter, rng=rng)
    return [
        AssetRef(
            kind=kind,
            id=member_id(id, k),
            store=store,
            ref=ref,
            stage=StagePlacement(
                at=(round(x, 3), round(y, 3)),
                scale=round(scale * (1.0 + scale_jitter * rng.uniform(-1.0, 1.0)), 4)
                if scale_jitter
                else scale,
            ),
        )
        for k, (x, y) in enumerate(points)
    ]


def _layout_points(
    layout: str,
    count: int,
    area: tuple[float, float, float, float],
    *,
    jitter: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    """The members' stage points, back row (smallest y) first."""
    x0, y0, x1, y1 = area
    w, h = x1 - x0, y1 - y0
    if layout == "scatter":
        points = [(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(count)]
        return sorted(points, key=lambda p: (p[1], p[0]))
    if layout == "row":
        cols, rows = count, 1
    else:  # a grid as square as the area's aspect allows
        cols = max(1, min(count, round(math.sqrt(count * w / h))))
        rows = math.ceil(count / cols)
    cw, ch = w / cols, h / rows
    points = []
    for k in range(count):
        r, c = divmod(k, cols)
        in_row = min(cols, count - r * cols)  # a partial last row is centred
        x = x0 + (c + 0.5 + (cols - in_row) / 2) * cw
        y = y0 + (r + 0.5) * ch
        if jitter:
            x += jitter * cw * rng.uniform(-0.5, 0.5)
            y += jitter * ch * rng.uniform(-0.5, 0.5)
        points.append((x, y))
    return points


def fan_out(
    action: Any, members: Iterable[AssetRef | str], *, crowd_id: str | None = None
) -> list[Any]:
    """A copy of ``action`` per member, its targets moved from the crowd to the member.

    action: any action, leaf or composite; every target naming the crowd
        (``army``, or a node of it, ``army/arm_l``) is rewritten
    members: the crowd's members (``AssetRef`` s or ids), in order
    crowd_id: the crowd's name (default: read off the first member's id,
        ``army_0`` -> ``army``)

    Pair it with :func:`an.ir.compose.stagger` for a ripple through the ranks,
    or :func:`~an.ir.compose.parallel` for the crowd moving as one.

    >>> from an.ir.compose import tween
    >>> [a.target for a in fan_out(tween("army/arm_l", "rotation", to=1.0, duration=0.5), ["army_0", "army_1"])]
    ['army_0/arm_l', 'army_1/arm_l']
    """
    ids = [m.id if isinstance(m, AssetRef) else str(m) for m in members]
    if not ids:
        return []
    if crowd_id is None:
        crowd_id = ids[0].rsplit("_", 1)[0]
    return [_retarget(action, crowd_id, member) for member in ids]


def _retarget(action: Any, old: str, new: str) -> Any:
    """``action`` with every target on entity ``old`` moved to ``new`` (composites recursively)."""
    update: dict[str, Any] = {}
    target = getattr(action, "target", None)
    if isinstance(target, str) and (target == old or target.startswith(old + "/")):
        update["target"] = new + target[len(old) :]
    children = getattr(action, "children", None)
    if children is not None:
        update["children"] = [_retarget(c, old, new) for c in children]
    child = getattr(action, "child", None)
    if child is not None and hasattr(child, "model_copy"):
        update["child"] = _retarget(child, old, new)
    return action.model_copy(update=update) if update else action.model_copy()
