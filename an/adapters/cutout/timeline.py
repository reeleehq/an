"""Stage timeline helpers: the compiled scene as a `Timeline`, and screen space.

The evaluation itself — tracks of placed clips, write groups, the pure pose —
moved to :mod:`an.timing.timeline` (the timing kernel). This module re-exports
it so every existing caller keeps its import path, and keeps what is the STAGE's
own: reading a compiled ``CutoutSceneJSON`` (:func:`timeline_from_scene`) and
composing node transforms into canvas positions (:func:`screen_position`).

>>> from an.adapters.cutout.channel import Channel, Keyframe
>>> from an.adapters.cutout.clip import Clip
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch])
>>> tl = Timeline(duration=2.0, tracks=[Track("a", clips=[PlacedClip(clip, start_time=0.5)])])
>>> evaluate_timeline(tl, 1.0)[("a", "x")]
5.0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from an.adapters.cutout.serialize import TransformJSON
from an.timing.channel import Channel, Keyframe
from an.timing.clip import Clip, LoopMode, Pose, merge_poses
from an.timing.timeline import (
    SWAP_WRITE_GROUP,
    PlacedClip,
    Timeline,
    Track,
    clip_from_json,
    evaluate_timeline,
    timeline_from_compiled,
    write_group,
)

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.adapters.cutout.serialize import CutoutSceneJSON, NodeJSON

__all__ = [
    "Channel",
    "Keyframe",
    "Clip",
    "LoopMode",
    "Pose",
    "merge_poses",
    "PlacedClip",
    "Track",
    "Timeline",
    "SWAP_WRITE_GROUP",
    "write_group",
    "evaluate_timeline",
    "clip_from_json",
    "timeline_from_scene",
    "Transform2D",
    "transform_of",
    "screen_position",
]


def timeline_from_scene(scene: CutoutSceneJSON) -> Timeline:
    """The compiled scene's `timeline`/`animations` as an evaluable `Timeline`.

    `compile_shot` produces a serialisable document (`an.adapters.cutout.serialize`)
    for the JS runtime; this rebuilds the *evaluable* form, so a caller can ask
    what a compiled scene's pose is at time `t` without a browser. It is the
    Python side of the parity contract: `evaluate_timeline` over this object is
    the executable spec `runtime.js` is tested against. The reading itself is the
    kernel's (:func:`an.timing.timeline.timeline_from_compiled`), which carries
    `loop_mode` and keeps a list-valued `easing` a tuple.

    >>> from an.adapters.cutout.compile import compile_shot
    >>> from an.ir.compose import tween
    >>> from an.ir.schema import Shot
    >>> shot = Shot(id="s1", renderer="cutout", duration=2.0,
    ...             actions=[tween("root", "x", 10.0, 1.0, from_=0.0)])
    >>> scene = compile_shot(shot, mall=None, fps=24)
    >>> evaluate_timeline(timeline_from_scene(scene), 0.5)[("root", "x")]
    5.0
    """
    return timeline_from_compiled(scene)


# --- screen space -------------------------------------------------------------
#
# `evaluate_timeline` returns a POSE — `{(target, property): value}` — and a
# pose is not a position. Nothing in `an/` composed one until an#111, which is
# why the pan measurement could not be written: a rigid pan on `root` leaves
# every plane's LOCAL x at zero, so a local channel reads "no parallax" for a
# stage that is parallaxing correctly.


@dataclass(frozen=True, slots=True)
class Transform2D:
    """One node's local transform, in the runtime's own vocabulary.

    Field names and defaults mirror `applyTransform` in `runtime.js` exactly —
    `x`, `y`, `rotation`, `scale_x`, `scale_y`, `pivot_x`, `pivot_y` — because
    the point of this class is to agree with the vendored engine rather than to
    re-derive it. `skew` is deliberately absent: PixiJS composes skew into the
    same matrix, but no emitter in this package produces a skew channel, and a
    field nothing writes is a claim this compositor cannot honour.
    """

    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    pivot_x: float = 0.0
    pivot_y: float = 0.0

    def unapply(self, point: tuple[float, float]) -> tuple[float, float]:
        """The inverse of :meth:`apply` — a parent-space point, in local space.

        >>> t = Transform2D(x=10.0, pivot_x=3.0, scale_x=2.0, rotation=0.4)
        >>> round(t.unapply(t.apply((7.0, -2.0)))[0], 9)
        7.0
        """
        px, py = point[0] - self.x, point[1] - self.y
        if self.rotation:
            cos_r, sin_r = math.cos(-self.rotation), math.sin(-self.rotation)
            px, py = px * cos_r - py * sin_r, px * sin_r + py * cos_r
        return px / self.scale_x + self.pivot_x, py / self.scale_y + self.pivot_y

    def apply(self, point: tuple[float, float]) -> tuple[float, float]:
        """This node's local point, in its PARENT's coordinates.

        ``world = position + M·(local − pivot)`` — the composition PixiJS
        performs, and the reason `root.pivot` is a 2D camera: moving the pivot
        moves everything the node contains, in the opposite direction.

        >>> Transform2D(x=10.0).apply((0.0, 0.0))
        (10.0, 0.0)
        >>> Transform2D(pivot_x=25.0).apply((0.0, 0.0))
        (-25.0, 0.0)
        >>> Transform2D(scale_x=2.0).apply((5.0, 0.0))
        (10.0, 0.0)
        """
        lx, ly = point[0] - self.pivot_x, point[1] - self.pivot_y
        sx, sy = lx * self.scale_x, ly * self.scale_y
        if self.rotation:
            cos_r, sin_r = math.cos(self.rotation), math.sin(self.rotation)
            sx, sy = sx * cos_r - sy * sin_r, sx * sin_r + sy * cos_r
        return self.x + sx, self.y + sy


def transform_of(node: NodeJSON | None, pose: Pose | None = None) -> Transform2D:
    """A node's transform, with ``pose`` overriding what the document declares.

    The runtime applies a pose value by assigning the property on the display
    object, so a channel REPLACES the declared value rather than adding to it —
    which is why the parallax compensation carries the plane's own offset in
    every keyframe instead of an offset from it.
    """
    t = node.transform if node is not None else TransformJSON()
    values = {
        "x": t.x,
        "y": t.y,
        "rotation": t.rotation,
        "scale_x": t.scale_x,
        "scale_y": t.scale_y,
        "pivot_x": t.pivot_x,
        "pivot_y": t.pivot_y,
    }
    if pose:
        for (_target, prop), value in pose.items():
            if prop in values and isinstance(value, (int, float)):
                values[prop] = float(value)
    return Transform2D(**values)


def screen_position(
    scene: CutoutSceneJSON,
    path: str,
    *,
    pose: Pose | None = None,
    point: tuple[float, float] = (0.0, 0.0),
) -> tuple[float, float]:
    """Where ``point`` in ``path``'s local space lands on the canvas.

    The composition the runtime performs, walked from the node up to `root`
    and then offset by the canvas centre — which is where `runtime.js` places
    the root container.

    ``pose`` is keyed by the FULL path (`"street/hills"`), matching what
    `evaluate_timeline` returns, and each node reads only its own entry.

    >>> from an.adapters.cutout.serialize import CutoutSceneJSON, NodeJSON, TimelineJSON, TransformJSON
    >>> scene = CutoutSceneJSON(
    ...     scene=NodeJSON(name="root", children=[
    ...         NodeJSON(name="hill", transform=TransformJSON(x=40.0))]),
    ...     timeline=TimelineJSON(duration=1.0),
    ... )
    >>> scene.meta.width, scene.meta.height = 320, 240
    >>> screen_position(scene, "hill")
    (200.0, 120.0)

    …and moving the camera's pivot moves it the other way, which is the whole
    reason `root.pivot` is the camera:

    >>> screen_position(scene, "hill", pose={("root", "pivot_x"): 25.0})
    (175.0, 120.0)
    """
    overlay = getattr(scene, "overlay", None)
    if overlay is not None and path.split("/", 1)[0] in {
        c.name for c in overlay.children
    }:
        # The overlay (an#155): the runtime centres it like `root` but never
        # indexes it, so NO pose — the camera's included — reaches its
        # container. Only the path's own nodes compose.
        at = point
        for node, node_path in reversed(_node_chain(overlay, path)[1:]):
            at = transform_of(node, _pose_for(pose, node_path)).apply(at)
        return at[0] + scene.meta.width / 2.0, at[1] + scene.meta.height / 2.0
    chain = _node_chain(scene.scene, path)
    at = point
    for node, node_path in reversed(chain[1:]):
        at = transform_of(node, _pose_for(pose, node_path)).apply(at)
    # The root LAST, and from the pose alone. `runtime.js` builds its own root
    # container at the canvas centre and says so: "Do NOT apply its transform".
    # What it does apply to that container is pose channels — which is exactly
    # how the camera works, since `root.pivot` is the camera. Composing the
    # document root's declared transform as well would diverge from the engine
    # the moment anything wrote one (an#111 review, L1).
    root, root_path = chain[0]
    at = transform_of(_ROOT_AT_REST, _pose_for(pose, root_path)).apply(at)
    return at[0] + scene.meta.width / 2.0, at[1] + scene.meta.height / 2.0


#: A stand-in for the runtime's own root container: identity, because that is
#: what `runtime.js` creates before applying any pose to it.
_ROOT_AT_REST: Any = None


def _pose_for(pose: Pose | None, path: str) -> Pose | None:
    """The pose entries for one node, re-keyed to its bare name."""
    if not pose:
        return None
    name = path.rsplit("/", 1)[-1]
    return {
        (name, prop): value for (target, prop), value in pose.items() if target == path
    }


def _node_chain(root: NodeJSON, path: str) -> list[tuple[NodeJSON, str]]:
    """``[(node, its path)]`` from ``path`` up to and including the root.

    Raises rather than returning an empty chain: a path that names no node is a
    caller error, and silently measuring the root's position instead is the
    kind of plausible wrong answer this package refuses elsewhere.
    """
    chain: list[tuple[NodeJSON, str]] = [(root, root.name)]
    node = root
    walked: list[str] = []
    for part in path.split("/"):
        found = next((c for c in node.children if c.name == part), None)
        if found is None:
            where = "/".join(walked) or root.name
            raise KeyError(
                f"no node {part!r} under {where!r}; it has "
                f"{[c.name for c in node.children]}"
            )
        walked.append(part)
        node = found
        chain.append((node, "/".join(walked)))
    return chain
