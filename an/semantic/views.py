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
    "MULTIPLANE",
    "ORBIT_3D",
    "ORBIT_DECL",
    "ViewField",
    "ViewSpace",
    "view_space",
]

#: How a view field interpolates: ``linear``, ``log`` (a zoom: equal ratios
#: take equal time) or ``angle`` (the shortest arc).
SCALES: tuple[str, ...] = ("linear", "log", "angle")


@dataclass(frozen=True)
class ViewField:
    """One axis of a view space: its name, unit, how it interpolates, its rest value.

    A scalar axis says how it interpolates with ``scale``; an axis whose value
    is not one number (an orbit, a colour, a vector) carries its field
    ``kind`` (:mod:`an.timing.kinds`) instead, built from the property
    declaration it shares with an engine's property space
    (:meth:`from_decl`), so the two are one thing (an#788).
    """

    name: str
    unit: str
    scale: str = "linear"
    rest: Any = 0.0
    description: str = ""
    kind: Any = None  # an an.timing.kinds.FieldKind, or None for a scalar

    def __post_init__(self) -> None:
        if self.scale not in SCALES:
            raise ValueError(f"view field {self.name!r}: scale must be one of {SCALES}")
        if self.kind is not None and self.scale != "linear":
            raise ValueError(
                f"view field {self.name!r}: a field with a kind interpolates by its kind; "
                f"drop scale={self.scale!r}"
            )

    @classmethod
    def from_decl(cls, decl: Any, *, rest: Any) -> "ViewField":
        """The view field a property declaration (:class:`an.timing.spaces.FieldDecl`)
        makes: its name, kind, unit and description, at ``rest``."""
        return cls(
            decl.pattern,
            decl.unit or "",
            rest=rest,
            description=decl.description,
            kind=decl.kind,
        )

    @property
    def field_kind(self) -> Any:
        """The field kind that interpolates this axis: its own, else the one its
        ``scale`` names (``linear`` and ``log`` numbers, a shortest-arc angle).

        >>> ViewField("zoom", "ratio", "log").field_kind
        NumberKind(space='log')
        >>> ViewField("roll", "rad", "angle").field_kind
        AngleKind(unit='rad', wrap=True)
        """
        from an.timing.kinds import ANGLE_UNITS, AngleKind, NumberKind

        if self.kind is not None:
            return self.kind
        if self.scale == "angle":
            if self.unit not in ANGLE_UNITS:
                raise ValueError(
                    f"view field {self.name!r}: an angle's unit must be one of {ANGLE_UNITS}, "
                    f"got {self.unit!r}"
                )
            return AngleKind(unit=self.unit)
        return NumberKind(space=self.scale)

    def decl(self) -> Any:
        """This axis as a property declaration (:class:`an.timing.spaces.FieldDecl`)."""
        from an.timing.spaces import FieldDecl

        return FieldDecl(
            self.name,
            self.field_kind,
            unit=self.unit or None,
            description=self.description,
        )

    def schema(self) -> dict[str, Any]:
        if self.kind is not None:
            out = {
                **self.kind.value_schema(),
                "kind": self.kind.to_spec(),
                "unit": self.unit,
                "default": self.rest,
            }
        else:
            out = {
                "type": "number",
                "unit": self.unit,
                "scale": self.scale,
                "default": self.rest,
            }
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class ViewSpace:
    """A declared view space: its vocabulary entry and the engine capability to lower it."""

    entry: Entry
    capability: Capability
    fields: tuple[ViewField, ...] = ()

    @property
    def requirement(self) -> str:
        return self.capability.name

    def property_space(self) -> Any:
        """The space as an engine's property space (:class:`an.timing.spaces.PropertySpace`,
        ``view.<name>``): each axis's declaration, the one an engine whose state
        this view space moves registers (an#788).

        >>> [(d.pattern, d.kind.to_spec()) for d in ORBIT_3D.property_space().fields]
        [('orbit', {'kind': 'orbit'})]
        """
        from an.timing.spaces import PropertySpace

        return PropertySpace(
            self.entry.id,
            tuple(f.decl() for f in self.fields),
            description=self.entry.description,
        )


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
        usage="axes: "
        + ", ".join(
            f"{f.name} ({f.unit}, {f.kind.name if f.kind is not None else f.scale})"
            for f in fields
        ),
        params={"type": "object", "properties": {f.name: f.schema() for f in fields}},
        levels=frozenset({"a"}),
    )
    capability = Capability(
        f"space.{name}",
        f"the engine lowers moves through the {name} view space: {description}",
        f"render with an engine that lowers the {name} view space",
        subject="engine",
    )
    return ViewSpace(entry, capability, fields)


#: The 2D framing space: where the frame is, how close, how rolled. Every
#: engine that shows a flat picture lowers it — by cropping pixels (burns) or by
#: re-rendering into the frame (the stage engine).
FRAMING_2D_FIELDS: tuple[ViewField, ...] = (
    ViewField("x", "frame widths", description="+x moves the view right"),
    ViewField("y", "frame heights", description="+y moves the view down"),
    ViewField("zoom", "ratio", "log", 1.0, "on-screen magnification; > 1 is closer"),
    ViewField("rotation", "rad", "angle", description="the view's roll"),
)
FRAMING_2D: ViewSpace = view_space(
    "framing2d",
    FRAMING_2D_FIELDS,
    description="a 2D framing of a flat picture: position, zoom (log), roll (angle)",
)

#: The multiplane space (an#478): the 2D framing plus how far the camera has
#: travelled into a scene of planes at depths, so each plane grows by its own
#: depth. A crop engine cannot lower it (its pixels have no depth); the stage
#: engine does, from its planes' parallax factors.
MULTIPLANE: ViewSpace = view_space(
    "multiplane",
    (
        *FRAMING_2D_FIELDS,
        ViewField(
            "dolly",
            "character-plane distance",
            description="travel toward the scene; 0.2 is a fifth of the way to the character plane",
        ),
    ),
    description="a 2D framing that also travels in depth through planes (a dolly)",
)


#: The orbit camera, declared ONCE (an#788): the field kind the timing kernel
#: interpolates (:class:`an.timing.kinds.OrbitKind`, degrees, as previz's camera
#: field), and the one axis of the ``orbit3d`` view space. An engine whose state
#: an orbit moves registers it in its property space
#: (``ORBIT_3D.property_space()``).
def _orbit_decl() -> Any:
    from an.timing.kinds import OrbitKind
    from an.timing.spaces import FieldDecl

    kind = OrbitKind()
    return FieldDecl(
        "orbit",
        kind,
        unit=kind.unit,  # its angles' unit; distance and target say theirs in the schema
        description="a camera on a sphere around its target: {azimuth, elevation, distance, target?}",
    )


ORBIT_DECL: Any = _orbit_decl()

#: The 3D orbit space: a camera on a sphere around a target (previz's turntable),
#: one ``orbit`` value, version 2 (version 1 split it into radian scalars and a
#: flattened target, which matched neither the kernel's kind nor previz).
ORBIT_3D: ViewSpace = view_space(
    "orbit3d",
    (
        ViewField.from_decl(
            ORBIT_DECL,
            rest={
                "azimuth": 0.0,
                "elevation": 0.0,
                "distance": 1.0,
                "target": [0.0, 0.0, 0.0],
            },
        ),
    ),
    description="an orbit camera around a 3D target: azimuth and elevation (angles), distance (log)",
    version="2",
)

#: The view spaces the core declares (registered by :mod:`an.semantic.seeds`).
CORE_VIEW_SPACES: tuple[ViewSpace, ...] = (FRAMING_2D, MULTIPLANE, ORBIT_3D)
