"""View spaces: what a camera move moves through, defined once for every engine (an#257).

A camera move (``push_in``, ``pan_left``, an orbit) is not a crop, a zoom or a
parameter tween: it is a **path through a view space**, which each engine
lowers its own way —

- a **crop engine** (``burns``, a still or a video) moves a rectangle over
  fixed pixels, so pushing in loses resolution;
- a **render engine** (the stage engine of ``an``/``cutan``, vector art)
  re-renders the scene into the rectangle, so pushing in loses nothing;
- a **parameter engine** (``previz``) moves a vector of view parameters — an
  orbit camera in 3D, a chart's axis domain.

So the vocabulary defines each move once, over an abstract space, and an engine
affords the space it can lower (``space.framing2d`` is an engine capability,
:mod:`an.capabilities.subjects`). The core declares two spaces; a genre or a
package declares more (an n-dimensional one) with :func:`view_space`, and
registers moves over them into the same ``camera_move`` table — so ``push_in``
means one thing everywhere, and ``burns``' moves and ``previz``'s camera
formulas join it instead of redefining it.

>>> FRAMING_2D.entry.id, FRAMING_2D.capability.name, FRAMING_2D.entry.params["properties"]["zoom"]["scale"]
('view.framing2d', 'space.framing2d', 'log')
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from an.capabilities import Capability
from an.semantic.entries import Entry

__all__ = [
    "FRAMING_2D",
    "ORBIT_3D",
    "ViewField",
    "ViewSpace",
    "view_space",
]

#: How a view field interpolates: ``linear``, ``log`` (a zoom: equal ratios
#: take equal time) or ``angle`` (the shortest arc).
SCALES: tuple[str, ...] = ("linear", "log", "angle")


@dataclass(frozen=True)
class ViewField:
    """One axis of a view space: its name, unit, how it interpolates, its rest value."""

    name: str
    unit: str
    scale: str = "linear"
    rest: float = 0.0
    description: str = ""

    def __post_init__(self) -> None:
        if self.scale not in SCALES:
            raise ValueError(f"view field {self.name!r}: scale must be one of {SCALES}")

    def schema(self) -> dict[str, Any]:
        out = {"type": "number", "unit": self.unit, "scale": self.scale, "default": self.rest}
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class ViewSpace:
    """A declared view space: its vocabulary entry and the engine capability to lower it."""

    entry: Entry
    capability: Capability

    @property
    def requirement(self) -> str:
        return self.capability.name


def view_space(
    name: str,
    fields: Iterable[ViewField],
    *,
    description: str,
    version: str = "1",
) -> ViewSpace:
    """Declare a view space: an entry ``view.<name>`` and an engine capability ``space.<name>``.

    Register both through a :class:`an.genres.Genre` (``vocabulary`` and
    ``capabilities``) or, for the core's, directly.
    """
    fields = tuple(fields)
    entry = Entry(
        f"view.{name}",
        "view_space",
        version=version,
        name=name,
        description=description,
        usage="axes: " + ", ".join(f"{f.name} ({f.unit}, {f.scale})" for f in fields),
        params={"type": "object", "properties": {f.name: f.schema() for f in fields}},
        levels=frozenset({"a"}),
    )
    capability = Capability(
        f"space.{name}",
        f"the engine lowers moves through the {name} view space: {description}",
        f"render with an engine that lowers the {name} view space",
        subject="engine",
    )
    return ViewSpace(entry, capability)


#: The 2D framing space: where the frame is, how close, how rolled. Every
#: engine that shows a flat picture lowers it — by cropping pixels (burns) or by
#: re-rendering into the frame (the stage engine).
FRAMING_2D: ViewSpace = view_space(
    "framing2d",
    (
        ViewField("x", "frame widths", description="+x moves the view right"),
        ViewField("y", "frame heights", description="+y moves the view down"),
        ViewField("zoom", "ratio", "log", 1.0, "on-screen magnification; > 1 is closer"),
        ViewField("rotation", "rad", "angle", description="the view's roll"),
    ),
    description="a 2D framing of a flat picture: position, zoom (log), roll (angle)",
)

#: The 3D orbit space: a camera on a sphere around a target (previz's turntable).
ORBIT_3D: ViewSpace = view_space(
    "orbit3d",
    (
        ViewField("azimuth", "rad", "angle", description="around the target"),
        ViewField("elevation", "rad", "angle", description="above the target's horizon"),
        ViewField("distance", "scene units", "log", 1.0, "from the target"),
        ViewField("target_x", "scene units"),
        ViewField("target_y", "scene units"),
        ViewField("target_z", "scene units"),
    ),
    description="an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)",
)

#: The view spaces the core declares (registered by :mod:`an.semantic.seeds`).
CORE_VIEW_SPACES: tuple[ViewSpace, ...] = (FRAMING_2D, ORBIT_3D)
