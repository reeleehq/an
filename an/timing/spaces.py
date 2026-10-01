"""Property spaces: what an entity kind's properties ARE, declared once.

A **property space** is the registration unit an entity kind hands the kernel
(ADR 0001 decision 11): for each property pattern, its **field kind** (the
interpolator, :mod:`an.timing.kinds`), its **write group** (aliases that set the
same thing — ``rotation_rad`` is ``rotation``; every swap set of one visual
replaces the same drawing), and its **unit** (stage pixels, radians, a ratio),
without which moving a value from one engine to another is meaningless.

Patterns are exact property names or ``fnmatch`` globs (``*@*``). An exact name
wins; globs are tried in declaration order. A property the space does not declare
is :class:`~an.timing.kinds.DiscreteKind` at the default switch point, and writes
only itself.

Two spaces are seeded here, and they reproduce today's output EXACTLY:

- ``stage.node`` — a node of the 2D stage engine: every name in
  :data:`an.base.TRANSFORM_PROPERTIES` is ``number`` (linear), including
  ``tint_r/g/b`` (``tint`` itself stays the compiler's authoring sugar, expanded
  into those three before any channel exists, so the wire shape does not move);
  every other property names a swap set, ``*@*`` included, and is
  ``discrete(switch_at=1)``.
- ``stage.camera`` — the stage's 2D framing camera: ``x``, ``y``, ``zoom``,
  ``rotation``, all plain ``number`` (the compiler lowers them onto ``root``'s
  pivot, scale and rotation channels). New genres get log zoom and shortest-arc
  rotation by declaring their own camera space, not by changing this one.

Genres register their own spaces with :func:`register_space` (P2: through the
``an.genres`` entry point), without editing this module.

>>> node = get_space("stage.node")
>>> node.kind_of("x"), node.kind_of("viseme@happy")
(NumberKind(space='linear'), DiscreteKind(switch_at=1))
>>> node.write_group("rotation_rad"), node.write_group("hands"), node.unit_of("rotation")
('rotation', '<swap>', 'rad')
>>> PropertySpace("demo", ()).kind_of("anything")  # undeclared: discrete
DiscreteKind(switch_at=0.5)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Callable, Mapping, Union

from an.base import TRANSFORM_PROPERTIES
from an.timing.kinds import DiscreteKind, FieldKind, NumberKind, kind_from_spec

#: The write group every swap set on a stage node shares: they all replace the
#: one drawing the node carries (``viseme`` and ``viseme@happy`` both set the
#: mouth's texture, an#88).
SWAP_WRITE_GROUP: str = "<swap>"

#: A replacement drawing never appears before its own key (an#86).
SWAP_KIND: DiscreteKind = DiscreteKind(switch_at=1)

#: What the stage node's transform properties are measured in.
STAGE_NODE_UNITS: dict[str, str] = {
    "x": "px",
    "y": "px",
    "pivot_x": "px",
    "pivot_y": "px",
    "rotation": "rad",
    "rotation_rad": "rad",
    "skew_x": "rad",
    "skew_y": "rad",
    "scale_x": "ratio",
    "scale_y": "ratio",
    "tint_r": "fraction",
    "tint_g": "fraction",
    "tint_b": "fraction",
    "alpha": "fraction",
    "trim_start": "fraction",
    "trim_end": "fraction",
    "dash_offset": "px",
}

#: Properties that write another property's value on the same node.
STAGE_NODE_ALIASES: dict[str, str] = {"rotation_rad": "rotation"}


class SpaceError(ValueError):
    """A property space is malformed, unknown, or already registered."""


@dataclass(frozen=True)
class FieldDecl:
    """One declaration of a property space: pattern -> kind, write group, unit."""

    pattern: str
    kind: FieldKind
    unit: str | None = None
    #: The write group this property belongs to; ``None`` means itself.
    writes: str | None = None
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"pattern": self.pattern, "spec": self.kind.to_spec()}
        if self.unit is not None:
            out["unit"] = self.unit
        if self.writes is not None:
            out["writes"] = self.writes
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class PropertySpace:
    """An entity kind's properties: declarations, matched exact-first then by glob."""

    name: str
    fields: tuple[FieldDecl, ...] = ()
    version: int = 1
    description: str = ""
    #: The kind of a property no declaration matches.
    undeclared: FieldKind = field(default_factory=DiscreteKind)
    #: Resolved declarations, per property (evaluators ask once per key per frame).
    _resolved: dict = field(
        default_factory=dict, init=False, repr=False, compare=False, hash=False
    )

    def declaration(self, prop: str) -> FieldDecl | None:
        """The declaration governing ``prop``, or ``None``."""
        try:
            return self._resolved[prop]
        except KeyError:
            decl = self._resolved[prop] = _match(self.fields, prop)
            return decl

    def kind_of(self, prop: str) -> FieldKind:
        decl = self.declaration(prop)
        return self.undeclared if decl is None else decl.kind

    def write_group(self, prop: str) -> str:
        decl = self.declaration(prop)
        if decl is None or decl.writes is None:
            return prop
        return decl.writes

    def unit_of(self, prop: str) -> str | None:
        decl = self.declaration(prop)
        return None if decl is None else decl.unit

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "fields": [d.to_json() for d in self.fields],
        }
        if self.undeclared != DiscreteKind():
            out["undeclared"] = self.undeclared.to_spec()
        if self.description:
            out["description"] = self.description
        return out


def _match(decls: tuple[FieldDecl, ...], prop: str) -> FieldDecl | None:
    globs = []
    for decl in decls:
        if decl.pattern == prop:
            return decl
        if any(c in decl.pattern for c in "*?["):
            globs.append(decl)
    return next((d for d in globs if fnmatchcase(prop, d.pattern)), None)


def space_from_json(doc: Mapping[str, Any]) -> PropertySpace:
    """A space from its JSON form (what :meth:`PropertySpace.to_json` writes)."""
    try:
        decls = tuple(
            FieldDecl(
                d["pattern"],
                kind_from_spec(d["spec"]),
                unit=d.get("unit"),
                writes=d.get("writes"),
                description=d.get("description", ""),
            )
            for d in doc.get("fields", ())
        )
    except KeyError as e:
        raise SpaceError(f"a space field needs {e.args[0]!r}: {doc!r}") from e
    extra = {}
    if "undeclared" in doc:
        extra["undeclared"] = kind_from_spec(doc["undeclared"])
    return PropertySpace(
        doc.get("name", "inline"),
        decls,
        version=doc.get("version", 1),
        description=doc.get("description", ""),
        **extra,
    )


# -----------------------------------------------------------------------------
# The registry
# -----------------------------------------------------------------------------

_REGISTRY: dict[str, PropertySpace] = {}


def register_space(space: PropertySpace, *, replace: bool = False) -> PropertySpace:
    """Register ``space`` under its name (how an entity kind declares its properties)."""
    if not replace and space.name in _REGISTRY:
        raise SpaceError(f"property space {space.name!r} is already registered")
    _REGISTRY[space.name] = space
    return space


def get_space(name: str) -> PropertySpace:
    try:
        return _REGISTRY[name]
    except KeyError as e:
        raise SpaceError(
            f"unknown property space {name!r}; known: {sorted(_REGISTRY)}"
        ) from e


def space_names() -> tuple[str, ...]:
    return tuple(_REGISTRY)


#: What an evaluator accepts as "the space": one space for every target, a
#: registered space's name, or a per-target resolver (P2: target -> its entity
#: kind's space).
SpaceLike = Union[PropertySpace, str, Callable[[str], PropertySpace]]


def space_resolver(space: SpaceLike) -> Callable[[str], PropertySpace]:
    """``space`` as a ``target -> PropertySpace`` function."""
    if isinstance(space, PropertySpace):
        return lambda _target: space
    if isinstance(space, str):
        resolved = get_space(space)
        return lambda _target: resolved
    if callable(space):
        return space
    raise SpaceError(f"not a property space, a space name or a resolver: {space!r}")


# -----------------------------------------------------------------------------
# The seeds
# -----------------------------------------------------------------------------


def _stage_node() -> PropertySpace:
    missing = TRANSFORM_PROPERTIES - STAGE_NODE_UNITS.keys()
    if missing:
        raise SpaceError(f"stage.node: no unit declared for {sorted(missing)}")
    numeric = tuple(
        FieldDecl(
            prop,
            NumberKind(),
            unit=STAGE_NODE_UNITS[prop],
            writes=STAGE_NODE_ALIASES.get(prop),
        )
        for prop in sorted(TRANSFORM_PROPERTIES)
    )
    swaps = (
        FieldDecl(
            "*@*",
            SWAP_KIND,
            writes=SWAP_WRITE_GROUP,
            description="a variant swap set (viseme@happy): replacement animation",
        ),
        FieldDecl(
            "*",
            SWAP_KIND,
            writes=SWAP_WRITE_GROUP,
            description="any other property names a swap set: replacement animation",
        ),
    )
    return PropertySpace(
        "stage.node",
        numeric + swaps,
        description=(
            "a node of the 2D stage engine: transform properties interpolate as "
            "plain numbers; every other property is a swap set that switches at "
            "its own key"
        ),
    )


def _stage_camera() -> PropertySpace:
    units = {"x": "px", "y": "px", "zoom": "ratio", "rotation": "rad"}
    return PropertySpace(
        "stage.camera",
        tuple(FieldDecl(prop, NumberKind(), unit=unit) for prop, unit in units.items()),
        description=(
            "the 2D stage's framing camera (lowered onto root.pivot, root.scale and "
            "root.rotation); all plain numbers, reproducing the cut-out output"
        ),
    )


STAGE_NODE: PropertySpace = register_space(_stage_node())
STAGE_CAMERA: PropertySpace = register_space(_stage_camera())
