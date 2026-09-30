"""Colour roles: which colour literal in which part is skin, clothing, hair…

A `StylePack` maps a role to a colour. For the procedural rig the compiler
decides every colour, so the mapping is a lookup. For SVG art the colours live
inside the drawings, and a pack could only reach them by guessing which literal
means what — inferring a role from a pixel, which is what produced an#99's
wrong-tone lid. So the roles are recorded at the SOURCE instead: the character
factory knows which fill it drew as skin and which as clothing, and it writes
that down in the descriptor's ``colour_roles``::

    {"parts/torso.svg": {"#a83249": "clothing", "#3b2a1a": "hair"}}

This is **palette swapping**, the indexed-colour technique 2D games have used
since sprites: a part is keyed by the literal it was drawn in, and a swap
rewrites that literal. Keyed per PART, not per character, because one literal
can mean two things in two drawings (the default pupil and a near-black hair
are both ``#1a1a1a``). The one limit it inherits is the classic one: within a
single part, two roles must be drawn in two distinct literals — the factory
guarantees it (:func:`distinct_literal`), and an illustrator tagging their own
art is told so by the descriptor validator.

The compiler applies it (:func:`recolour_svg`) at compile time: the tagged
part's SVG text is rewritten, and the result becomes a new, content-addressed
inline texture. Art with no roles — hand-drawn, DiceBear — is untouched, and
the compiler says so.

>>> recolour_svg('<rect fill="#A83249" stroke="#222"/>', {"#a83249": "#123456"})
'<rect fill="#123456" stroke="#222"/>'
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, Mapping, Optional

__all__ = [
    "ColourRoles",
    "normalise_hex",
    "recolour_svg",
    "role_recolouring",
    "distinct_literal",
]

#: ``{part path: {"#rrggbb": role}}`` — the descriptor field's shape.
ColourRoles = dict[str, dict[str, str]]

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

#: The SVG presentation attributes that carry a paint colour. A colour is only
#: rewritten where it is USED as one — never a bare ``#abc`` token, which in
#: SVG is just as often a fragment reference (``href="#abc"``, ``url(#def)``).
_PAINT_PROPERTIES = "fill|stroke|stop-color|flood-color|lighting-color|color"
#: ``fill="#abc"`` — the attribute form. The lookbehind keeps ``data-fill`` out.
_PAINT_ATTR = re.compile(
    rf"(?<![\w:-])((?:{_PAINT_PROPERTIES})\s*=\s*)([\"'])\s*"
    r"(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\s*\2"
)
#: ``fill: #abc`` — inside a ``style`` attribute or a ``<style>`` block.
_PAINT_DECL = re.compile(
    rf"(?<![\w-])((?:{_PAINT_PROPERTIES})\s*:\s*)(#[0-9a-fA-F]{{6}}|#[0-9a-fA-F]{{3}})(?![0-9a-fA-F])"
)


def normalise_hex(colour: str) -> str:
    """``'#ABC'`` -> ``'#aabbcc'``: the one spelling a literal is keyed by.

    >>> normalise_hex("#A83249"), normalise_hex("#fa0")
    ('#a83249', '#ffaa00')
    >>> normalise_hex("red")
    Traceback (most recent call last):
    ...
    ValueError: 'red' is not a #rgb or #rrggbb colour
    """
    if not isinstance(colour, str) or not _HEX.match(colour.strip()):
        raise ValueError(f"{colour!r} is not a #rgb or #rrggbb colour")
    c = colour.strip().lower()
    if len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c


@lru_cache(maxsize=1024)
def _recolour_cached(svg: str, swaps: tuple[tuple[str, str], ...]) -> str:
    table = dict(swaps)

    def attr(m: re.Match) -> str:
        new = table.get(normalise_hex(m.group(3)))
        return (
            m.group(0) if new is None else f"{m.group(1)}{m.group(2)}{new}{m.group(2)}"
        )

    def decl(m: re.Match) -> str:
        new = table.get(normalise_hex(m.group(2)))
        return m.group(0) if new is None else f"{m.group(1)}{new}"

    return _PAINT_DECL.sub(decl, _PAINT_ATTR.sub(attr, svg))


def recolour_svg(svg: str, swaps: Mapping[str, str]) -> str:
    """``svg`` with every paint use of an old literal replaced by its new one.

    Only paint colours are touched (``fill``, ``stroke``, gradient stops…, as an
    attribute or a style declaration); everything else — geometry, ids,
    fragment references — stays byte-for-byte. Literals match case- and
    length-insensitively (``#FA0`` is ``#ffaa00``). Deterministic, and cached by
    content: the same text and swaps are rewritten once per process.

    >>> recolour_svg('<g style="fill:#fa0;stroke:#000"><use href="#fa0"/></g>',
    ...              {"#ffaa00": "#010203"})
    '<g style="fill:#010203;stroke:#000"><use href="#fa0"/></g>'
    >>> recolour_svg('<rect data-fill="#aaa" fill="#aaa"/>', {"#aaaaaa": "#bbbbbb"})
    '<rect data-fill="#aaa" fill="#bbbbbb"/>'
    """
    swaps_ = tuple(
        sorted((normalise_hex(k), normalise_hex(v)) for k, v in swaps.items())
    )
    if not swaps_:
        return svg
    return _recolour_cached(svg, swaps_)


def role_recolouring(
    roles: Mapping[str, str], colour_for: Callable[[str], Optional[str]]
) -> dict[str, str]:
    """``{old literal: new colour}`` for the roles ``colour_for`` sets.

    ``colour_for(role)`` is the pack's lookup (per entity); a role it leaves
    unset keeps its literal, and a role set to the colour it already has is not
    a swap — so a pack that changes nothing produces nothing to rewrite.

    >>> role_recolouring({"#a83249": "clothing", "#3b2a1a": "hair"},
    ...                  {"clothing": "#202028"}.get)
    {'#a83249': '#202028'}
    """
    out: dict[str, str] = {}
    for literal, role in roles.items():
        new = colour_for(role)
        if new is None:
            continue
        old, new = normalise_hex(literal), normalise_hex(new)
        if old != new:
            out[old] = new
    return out


def distinct_literal(colour: str, taken: set[str]) -> str:
    """``colour``, nudged by the smallest step until no literal in ``taken``
    has it — the one rule palette swapping needs within a part.

    Two roles drawn in one literal cannot be told apart by a swap, and neither
    can a role and an untagged detail (a shoe, an outline) that happens to share
    it. One step in one channel is invisible and makes the key exact.

    >>> distinct_literal("#222222", {"#222222"})
    '#222223'
    >>> distinct_literal("#ffffff", {"#ffffff", "#fffffe"})
    '#fffffd'
    >>> distinct_literal("#123456", {"#abcdef"})
    '#123456'
    """
    c = normalise_hex(colour)
    taken_ = {normalise_hex(t) for t in taken}
    r, g, b = (int(c[i : i + 2], 16) for i in (1, 3, 5))
    step = 0
    while c in taken_:
        step += 1
        for delta in (step, -step):
            nb = b + delta
            if 0 <= nb <= 255:
                cand = f"#{r:02x}{g:02x}{nb:02x}"
                if cand not in taken_:
                    return cand
        if step > 255:
            raise ValueError(f"no free literal near {colour!r}")
    return c
