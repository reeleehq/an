"""The things that strike: a stick and a ball, as ordinary `an` props.

An :class:`ImpactObject` is data: the prop to draw, where it stands, the ONE
property the stroke animates and the affine map from stroke height ``h`` to
that property's value, and the named keypoints a tracker would report. Being
affine is the whole contract — it is what lets :mod:`an.impacts.stroke` reason
in ``h`` while the renderer tweens the property, with no approximation between
them.

The objects are real props (an#108), stored in a real props store and drawn by
the real cutout rig builder, so the harness exercises the same path an
animation does. Their art is generated here as plain SVG, sized so the rig's
view-box factor is exactly 1 (``view_box`` height = the compiler's
``SCENE_PX_PER_VIEW_BOX``): one SVG pixel is one scene pixel, and a keypoint's
local coordinates are read straight off the drawing.

Coordinates are scene pixels relative to the canvas centre, ``y`` down — the
space `StagePlacement.at` and the camera use. Rotation is in radians,
clockwise-positive on screen, as PixiJS applies it.

>>> s = stick()
>>> s.property, s.value(0.0) == s.contact_value
('rotation', True)
>>> round(s.value(1.0) - s.value(0.0), 6) == -s.stroke_extent
True
>>> ball().property
'y'
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import math

from an.adapters.cutout.compile import SCENE_PX_PER_VIEW_BOX
from an.characters.schema import Attachment, Skin, Slot
from an.props import DFLT_PROP_BONE, DFLT_PROP_SLOT, PropDescriptor

__all__ = [
    "DEFAULT_OBJECT_COLOR",
    "DEFAULT_SURFACE_COLOR",
    "IMPACT_OBJECTS",
    "ImpactObject",
    "PropArt",
    "ball",
    "impact_object",
    "stick",
]

DEFAULT_OBJECT_COLOR: str = "#111827"
DEFAULT_SURFACE_COLOR: str = "#9ca3af"
_PART = "parts/body.svg"


@dataclass(frozen=True, slots=True)
class PropArt:
    """A prop's descriptor and its SVG parts — what goes into a props store."""

    ref: str
    descriptor: dict
    parts: Mapping[str, str]  # relative path -> SVG text


@dataclass(frozen=True, slots=True)
class ImpactObject:
    """One striking object, its surface, and how the stroke moves it."""

    name: str
    art: PropArt
    at: tuple[float, float]
    property: str
    contact_value: float
    #: How far ``h = 1`` moves ``property`` AWAY from contact (radians or px).
    stroke_extent: float
    #: Local points in the entity's frame, by name. What a tracker would report.
    keypoints: Mapping[str, tuple[float, float]]
    #: The keypoint that does the striking (a stick's tip, a ball's bottom).
    impact_keypoint: str
    surface_art: PropArt | None = None
    surface_at: tuple[float, float] | None = None
    params: Mapping[str, float] = field(default_factory=dict)

    def value(self, h: float) -> float:
        """The animated property's value at stroke height ``h`` (affine in ``h``)."""
        return self.contact_value - self.stroke_extent * h


def _prop_art(ref: str, svg: str, *, anchor: tuple[float, float]) -> PropArt:
    body = Attachment(path=_PART, anchor=anchor)
    desc = PropDescriptor(
        name=ref,
        view_box=(0, 0, int(SCENE_PX_PER_VIEW_BOX), int(SCENE_PX_PER_VIEW_BOX)),
        slots=[Slot(name=DFLT_PROP_SLOT, bone=DFLT_PROP_BONE, draw_order=0, attachment="body")],
        skins={"default": Skin(slots={DFLT_PROP_SLOT: {"body": body}})},
        metadata={"generated_by": "an.impacts"},
    )
    return PropArt(ref, desc.model_dump(mode="json"), {_PART: svg})


def _svg(width: float, height: float, shape: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" '
        f'viewBox="0 0 {width:g} {height:g}">{shape}</svg>\n'
    )


def _slab(width: float, height: float, color: str) -> PropArt:
    """A flat surface whose TOP edge sits at the entity's origin."""
    svg = _svg(width, height, f'<rect width="{width:g}" height="{height:g}" fill="{color}"/>')
    return _prop_art("impact-surface", svg, anchor=(0.5, 0.0))


def stick(
    *,
    length: float = 200.0,
    thickness: float = 12.0,
    pivot: tuple[float, float] = (-120.0, -30.0),
    contact_angle: float = 0.35,
    swing: float = 0.95,
    color: str = DEFAULT_OBJECT_COLOR,
    surface_color: str = DEFAULT_SURFACE_COLOR,
    surface_size: tuple[float, float] = (140.0, 24.0),
) -> ImpactObject:
    """A drumstick rotating about ``pivot`` (its butt — the hand).

    At contact it points ``contact_angle`` radians below horizontal; a full
    stroke raises it by ``swing`` radians. Keypoints: ``pivot`` and ``tip``
    (the end of its axis). The surface's top meets the stick's lower edge at
    the tip.
    """
    radius = thickness / 2.0
    svg = _svg(
        length,
        thickness,
        f'<rect width="{length:g}" height="{thickness:g}" rx="{radius:g}" fill="{color}"/>',
    )
    art = _prop_art("impact-stick", svg, anchor=(0.0, 0.5))
    # The lower edge at the tip, rotated to the contact angle, is the surface top.
    c, s = math.cos(contact_angle), math.sin(contact_angle)
    edge_x = pivot[0] + length * c - radius * s
    edge_y = pivot[1] + length * s + radius * c
    return ImpactObject(
        name="stick",
        art=art,
        at=pivot,
        property="rotation",
        contact_value=contact_angle,
        stroke_extent=swing,
        keypoints={"pivot": (0.0, 0.0), "tip": (length, 0.0)},
        impact_keypoint="tip",
        surface_art=_slab(*surface_size, surface_color),
        surface_at=(edge_x, edge_y),
        params={"length": length, "thickness": thickness},
    )


def ball(
    *,
    radius: float = 18.0,
    x: float = 0.0,
    floor_y: float = 90.0,
    drop: float = 170.0,
    color: str = DEFAULT_OBJECT_COLOR,
    surface_color: str = DEFAULT_SURFACE_COLOR,
    surface_size: tuple[float, float] = (160.0, 24.0),
) -> ImpactObject:
    """A ball moving vertically onto a floor whose top is at ``floor_y``.

    A full stroke lifts it ``drop`` pixels. Keypoints: ``center`` and
    ``bottom`` (its contact point).
    """
    d = 2.0 * radius
    svg = _svg(d, d, f'<circle cx="{radius:g}" cy="{radius:g}" r="{radius:g}" fill="{color}"/>')
    art = _prop_art("impact-ball", svg, anchor=(0.5, 0.5))
    contact_y = floor_y - radius
    return ImpactObject(
        name="ball",
        art=art,
        at=(x, contact_y),
        property="y",
        contact_value=contact_y,
        stroke_extent=drop,
        keypoints={"center": (0.0, 0.0), "bottom": (0.0, radius)},
        impact_keypoint="bottom",
        surface_art=_slab(*surface_size, surface_color),
        surface_at=(x, floor_y),
        params={"radius": radius},
    )


#: Name -> factory. The registry the clip spec and the CLI resolve names through.
IMPACT_OBJECTS: dict[str, Callable[..., ImpactObject]] = {"stick": stick, "ball": ball}


def impact_object(name: str, **kwargs) -> ImpactObject:
    """Build a registered object by name.

    >>> impact_object("ball").name
    'ball'
    >>> impact_object("hammer")
    Traceback (most recent call last):
      ...
    KeyError: "no impact object 'hammer'; known: ['ball', 'stick']"
    """
    if name not in IMPACT_OBJECTS:
        raise KeyError(f"no impact object {name!r}; known: {sorted(IMPACT_OBJECTS)}")
    return IMPACT_OBJECTS[name](**kwargs)
