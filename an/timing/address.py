"""The address grammar: one way to name an animatable value, in every genre.

::

    <entity>[/<node>…]:<field>[@<qualifier>]

- ``entity`` — what the scene holds (a character, a prop, the camera, a view);
- ``/<node>…`` — a path inside it (``charlie/left_arm``); ``root`` is the
  stage's reserved scene root, which the camera lowers onto;
- ``field`` — a property the entity kind's property space declares
  (:mod:`an.timing.spaces`). It may be a **dotted** path (``view:light.color``),
  and a dotted segment names a declared field, never a member *inside* a
  composite value: an ``orbit`` interpolates as one value, so
  ``view:camera.azimuth`` is addressable only if the space declares
  ``camera.azimuth`` itself;
- ``@<qualifier>`` — a variant of the field (``mouth:viseme@happy``, a variant
  swap set), which the stage already emits.

The compiled form's ``(target, property)`` pair is exactly
``(entity/nodes, field@qualifier)``, and the golden vectors key every state by
the address string.

>>> a = parse_address("charlie/head/mouth:viseme@happy")
>>> a.entity, a.nodes, a.field, a.qualifier
('charlie', ('head', 'mouth'), 'viseme', 'happy')
>>> a.target, a.property
('charlie/head/mouth', 'viseme@happy')
>>> str(parse_address("view:light.color")), parse_address("view:light.color").field_path
('view:light.color', ('light', 'color'))
>>> str(Address.of("root", "pivot_x"))
'root:pivot_x'
>>> parse_address("charlie:")
Traceback (most recent call last):
 ...
an.timing.address.AddressError: 'charlie:': the field is empty
"""

from __future__ import annotations

from dataclasses import dataclass

#: Separators of the grammar; none of them may appear inside a name.
ENTITY_FIELD_SEP: str = ":"
NODE_SEP: str = "/"
FIELD_SEP: str = "."
QUALIFIER_SEP: str = "@"
_RESERVED: tuple[str, ...] = (ENTITY_FIELD_SEP, NODE_SEP, QUALIFIER_SEP)


class AddressError(ValueError):
    """A string is not an address under the grammar."""


@dataclass(frozen=True, slots=True)
class Address:
    """A parsed address. ``str(address)`` writes it back unchanged."""

    entity: str
    nodes: tuple[str, ...] = ()
    field: str = ""
    qualifier: str | None = None

    @property
    def target(self) -> str:
        """The compiled form's ``target``: the entity and its node path."""
        return NODE_SEP.join((self.entity, *self.nodes))

    @property
    def field_path(self) -> tuple[str, ...]:
        """The dotted field, split."""
        return tuple(self.field.split(FIELD_SEP))

    # Defined last: inside the class body this name shadows the builtin.
    @property
    def property(self) -> str:
        """The compiled form's ``property``: the field and its qualifier."""
        if self.qualifier is None:
            return self.field
        return f"{self.field}{QUALIFIER_SEP}{self.qualifier}"

    def __str__(self) -> str:
        return f"{self.target}{ENTITY_FIELD_SEP}{self.property}"

    @classmethod
    def of(cls, target: str, prop: str) -> Address:
        """The address of a compiled ``(target, property)`` pair (validated)."""
        return parse_address(f"{target}{ENTITY_FIELD_SEP}{prop}")


def _name_problem(name: str, what: str, *, allow: str = "") -> str | None:
    if not name:
        return f"the {what} is empty"
    if name != name.strip():
        return f"the {what} {name!r} has leading or trailing whitespace"
    bad = [c for c in _RESERVED if c in name and c not in allow]
    if bad:
        return f"the {what} {name!r} contains {bad[0]!r}"
    return None


def parse_address(text: str) -> Address:
    """``text`` as an :class:`Address`; raises :class:`AddressError` naming the fault.

    >>> parse_address("charlie/left_arm:rotation").target
    'charlie/left_arm'
    >>> parse_address("a::b")
    Traceback (most recent call last):
     ...
    an.timing.address.AddressError: 'a::b': an address has exactly one ':', found 2
    """
    if not isinstance(text, str):
        raise AddressError(f"an address is a string, got {type(text).__name__}")
    n_colons = text.count(ENTITY_FIELD_SEP)
    if n_colons != 1:
        raise AddressError(
            f"{text!r}: an address has exactly one {ENTITY_FIELD_SEP!r}, found {n_colons}"
        )
    path, prop = text.split(ENTITY_FIELD_SEP)
    entity, *nodes = path.split(NODE_SEP)
    problems = [_name_problem(entity, "entity")]
    problems += [_name_problem(n, "node") for n in nodes]
    if prop.count(QUALIFIER_SEP) > 1:
        problems.append(f"the property {prop!r} has more than one {QUALIFIER_SEP!r}")
    field, _, qualifier = prop.partition(QUALIFIER_SEP)
    problems.append(_name_problem(field, "field"))
    if field:
        problems += [
            _name_problem(seg, "field segment") for seg in field.split(FIELD_SEP)
        ]
    if QUALIFIER_SEP in prop:
        problems.append(_name_problem(qualifier, "qualifier"))
    problem = next((p for p in problems if p), None)
    if problem:
        raise AddressError(f"{text!r}: {problem}")
    return Address(
        entity, tuple(nodes), field, qualifier if QUALIFIER_SEP in prop else None
    )


def format_address(target: str, prop: str) -> str:
    """The address string of a compiled ``(target, property)`` pair, unvalidated
    (the fast path for keying states; :meth:`Address.of` validates)."""
    return f"{target}{ENTITY_FIELD_SEP}{prop}"
