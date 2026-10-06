"""Stage timeline helpers: the compiled scene as a `Timeline`, and screen space.

The evaluation itself — tracks of placed clips, write groups, the pure pose —
moved to :mod:`an.timing.timeline` (the timing kernel). This module re-exports
it so every existing caller keeps its import path, and keeps what is the STAGE's
own: reading a compiled ``CutoutSceneJSON`` (:func:`timeline_from_scene`) and
composing node transforms into canvas positions (:func:`screen_position`).

>>> from an.timing.channel import Channel, Keyframe
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

from an.base import PLANE_REST_VALUES
from an.stage.serialize import TransformJSON
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
    from an.stage.serialize import CutoutSceneJSON, NodeJSON

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

    `compile_shot` produces a serialisable document (`an.stage.serialize`)
    for the JS runtime; this rebuilds the *evaluable* form, so a caller can ask
    what a compiled scene's pose is at time `t` without a browser. It is the
    Python side of the parity contract: `evaluate_timeline` over this object is
    the executable spec `runtime.js` is tested against. The reading itself is the
    kernel's (:func:`an.timing.timeline.timeline_from_compiled`), which carries
    `loop_mode` and keeps a list-valued `easing` a tuple.

    >>> from an.stage.compile import compile_shot
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


#: The frame height a ``perspective`` is measured in when no scene says (px).
DFLT_FRAME_HEIGHT: float = 1080.0
#: ``perspective``'s rest value: the eye one frame height from the hinge.
PLANE_PERSPECTIVE_REST: float = PLANE_REST_VALUES["perspective"]


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
    #: The plane's tilt (an#314, radians; positive = the top recedes) and the
    #: eye's distance from the hinge in scene px (``perspective`` × the frame
    #: height). The projection is applied to ``local − pivot``, before the 2D
    #: transform, exactly as `runtime.js` "Planes" draws it.
    rotation_x: float = 0.0
    eye_distance: float = 0.0

    def project(self, q: tuple[float, float]) -> tuple[float, float]:
        """A plane point ``q = local − pivot`` as the tilted plane shows it.

        ``k = f / (f − q_y·sin θ)``, ``P(q) = (k·q_x, k·q_y·cos θ)``: the hinge
        row (``q_y = 0``) is unmoved, and a row up a receding plane is pulled
        toward the horizon at ``f·cot θ`` above it.

        >>> t = Transform2D(rotation_x=math.pi / 3, eye_distance=1000.0)
        >>> t.project((100.0, 0.0))
        (100.0, 0.0)
        >>> x, y = t.project((100.0, -500.0))
        >>> x < 100.0 and -500.0 < y < 0.0
        True

        A point behind the eye (or a plane edge-on, or no eye distance) is one
        the runtime does not draw, so it has no position:

        >>> t.project((0.0, 5000.0))
        Traceback (most recent call last):
        ...
        ValueError: plane point (0.0, 5000.0) is not drawn: ...
        """
        if not self.rotation_x:
            return q
        sin_t, cos_t = math.sin(self.rotation_x), math.cos(self.rotation_x)
        depth = self.eye_distance - q[1] * sin_t
        if not self.eye_distance > 0 or cos_t <= 0 or depth <= 0:
            raise ValueError(
                f"plane point {q} is not drawn: the runtime draws a plane only "
                "with a positive eye distance, short of edge-on, and in front of "
                f"the eye (eye_distance={self.eye_distance}, rotation_x="
                f"{self.rotation_x}); the near clip at 8x magnification is the "
                "runtime's alone"
            )
        k = self.eye_distance / depth
        return k * q[0], k * q[1] * cos_t

    def unproject(self, p: tuple[float, float]) -> tuple[float, float]:
        """The inverse of :meth:`project`.

        >>> t = Transform2D(rotation_x=1.0, eye_distance=800.0)
        >>> [round(v, 9) for v in t.unproject(t.project((40.0, -300.0)))]
        [40.0, -300.0]
        """
        if not self.rotation_x:
            return p
        sin_t, cos_t = math.sin(self.rotation_x), math.cos(self.rotation_x)
        f = self.eye_distance
        qy = p[1] * f / (f * cos_t + p[1] * sin_t)
        k = f / (f - qy * sin_t)
        return p[0] / k, qy

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
        qx, qy = self.unproject((px / self.scale_x, py / self.scale_y))
        return qx + self.pivot_x, qy + self.pivot_y

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
        lx, ly = self.project((point[0] - self.pivot_x, point[1] - self.pivot_y))
        sx, sy = lx * self.scale_x, ly * self.scale_y
        if self.rotation:
            cos_r, sin_r = math.cos(self.rotation), math.sin(self.rotation)
            sx, sy = sx * cos_r - sy * sin_r, sx * sin_r + sy * cos_r
        return self.x + sx, self.y + sy


def transform_of(
    node: NodeJSON | None,
    pose: Pose | None = None,
    *,
    frame_height: float = DFLT_FRAME_HEIGHT,
) -> Transform2D:
    """A node's transform, with ``pose`` overriding what the document declares.

    The runtime applies a pose value by assigning the property on the display
    object, so a channel REPLACES the declared value rather than adding to it —
    which is why the parallax compensation carries the plane's own offset in
    every keyframe instead of an offset from it. ``frame_height`` turns a
    ``perspective`` (in frame heights, an#314) into the eye's distance.
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
    values["rotation_x"] = 0.0
    perspective = PLANE_PERSPECTIVE_REST
    if pose:
        for (_target, prop), value in pose.items():
            if not isinstance(value, (int, float)):
                continue
            if prop in values:
                values[prop] = float(value)
            elif prop == "perspective":
                perspective = float(value)
    return Transform2D(**values, eye_distance=perspective * frame_height)


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

    >>> from an.stage.serialize import CutoutSceneJSON, NodeJSON, TimelineJSON, TransformJSON
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
            at = transform_of(
                node, _pose_for(pose, node_path), frame_height=scene.meta.height
            ).apply(at)
        return at[0] + scene.meta.width / 2.0, at[1] + scene.meta.height / 2.0
    chain = _node_chain(scene.scene, path)
    at = point
    for node, node_path in reversed(chain[1:]):
        at = transform_of(
            node, _pose_for(pose, node_path), frame_height=scene.meta.height
        ).apply(at)
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
    """``[(node, its path)]`` from ``root`` down to the node at ``path``, every
    container on the way included (:func:`an.stage.tree.chain`: the runtime's
    rule, ``scope`` included, an#343).

    Raises rather than returning an empty chain: a path that names no node is a
    caller error, and silently measuring the root's position instead is the
    kind of plausible wrong answer this package refuses elsewhere.
    """
    from an.stage.tree import chain

    return chain(root, path)
