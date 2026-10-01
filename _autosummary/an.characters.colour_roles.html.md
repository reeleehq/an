# an.characters.colour_roles

Colour roles: which colour literal in which part is skin, clothing, hair…

A `StylePack` maps a role to a colour. For the procedural rig the compiler
decides every colour, so the mapping is a lookup. For SVG art the colours live
inside the drawings, and a pack could only reach them by guessing which literal
means what — inferring a role from a pixel, which is what produced an#99’s
wrong-tone lid. So the roles are recorded at the SOURCE instead: the character
factory knows which fill it drew as skin and which as clothing, and it writes
that down in the descriptor’s `colour_roles`:

```default
{"parts/torso.svg": {"#a83249": "clothing", "#3b2a1a": "hair"}}
```

This is **palette swapping**, the indexed-colour technique 2D games have used
since sprites: a part is keyed by the literal it was drawn in, and a swap
rewrites that literal. Keyed per PART, not per character, because one literal
can mean two things in two drawings (the default pupil and a near-black hair
are both `#1a1a1a`). The one limit it inherits is the classic one: within a
single part, two roles must be drawn in two distinct literals — the factory
guarantees it ([`distinct_literal()`](#an.characters.colour_roles.distinct_literal)), and an illustrator tagging their own
art is told so by the descriptor validator.

The compiler applies it ([`recolour_svg()`](#an.characters.colour_roles.recolour_svg)) at compile time: the tagged
part’s SVG text is rewritten, and the result becomes a new, content-addressed
inline texture. Art with no roles — hand-drawn, DiceBear — is untouched, and
the compiler says so.

```pycon
>>> recolour_svg('<rect fill="#A83249" stroke="#222"/>', {"#a83249": "#123456"})
'<rect fill="#123456" stroke="#222"/>'
```

### Module Attributes

| [`ColourRoles`](#an.characters.colour_roles.ColourRoles)   | `{part path: {"#rrggbb": role}}` — the descriptor field's shape.   |
|----------------------------------------------------------------|--------------------------------------------------------------------|

### Functions

| [`normalise_hex`](#an.characters.colour_roles.normalise_hex)(colour)               | `'#ABC'` -> `'#aabbcc'`: the one spelling a literal is keyed by.                                                              |
|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [`recolour_svg`](#an.characters.colour_roles.recolour_svg)(svg, swaps)            | `svg` with every paint use of an old literal replaced by its new one.                                                         |
| [`role_recolouring`](#an.characters.colour_roles.role_recolouring)(roles, colour_for) | `{old literal: new colour}` for the roles `colour_for` sets.                                                                  |
| [`distinct_literal`](#an.characters.colour_roles.distinct_literal)(colour, taken)     | `colour`, nudged by the smallest step until no literal in `taken` has it — the one rule palette swapping needs within a part. |

### an.characters.colour_roles.ColourRoles

`{part path: {"#rrggbb": role}}` — the descriptor field’s shape.

alias of `dict`[`str`, `dict`[`str`, `str`]]

### an.characters.colour_roles.distinct_literal(colour, taken)

`colour`, nudged by the smallest step until no literal in `taken`
has it — the one rule palette swapping needs within a part.

Two roles drawn in one literal cannot be told apart by a swap, and neither
can a role and an untagged detail (a shoe, an outline) that happens to share
it. One step in one channel is invisible and makes the key exact.

* **Return type:**
  `str`

```pycon
>>> distinct_literal("#222222", {"#222222"})
'#222223'
>>> distinct_literal("#ffffff", {"#ffffff", "#fffffe"})
'#fffffd'
>>> distinct_literal("#123456", {"#abcdef"})
'#123456'
```

### an.characters.colour_roles.normalise_hex(colour)

`'#ABC'` -> `'#aabbcc'`: the one spelling a literal is keyed by.

* **Return type:**
  `str`

```pycon
>>> normalise_hex("#A83249"), normalise_hex("#fa0")
('#a83249', '#ffaa00')
>>> normalise_hex("red")
Traceback (most recent call last):
...
ValueError: 'red' is not a #rgb or #rrggbb colour
```

### an.characters.colour_roles.recolour_svg(svg, swaps)

`svg` with every paint use of an old literal replaced by its new one.

Only paint colours are touched (`fill`, `stroke`, gradient stops…, as an
attribute or a style declaration); everything else — geometry, ids,
fragment references — stays byte-for-byte. Literals match case- and
length-insensitively (`#FA0` is `#ffaa00`). Deterministic, and cached by
content: the same text and swaps are rewritten once per process.

* **Return type:**
  `str`

```pycon
>>> recolour_svg('<g style="fill:#fa0;stroke:#000"><use href="#fa0"/></g>',
...              {"#ffaa00": "#010203"})
'<g style="fill:#010203;stroke:#000"><use href="#fa0"/></g>'
>>> recolour_svg('<rect data-fill="#aaa" fill="#aaa"/>', {"#aaaaaa": "#bbbbbb"})
'<rect data-fill="#aaa" fill="#bbbbbb"/>'
```

### an.characters.colour_roles.role_recolouring(roles, colour_for)

`{old literal: new colour}` for the roles `colour_for` sets.

`colour_for(role)` is the pack’s lookup (per entity); a role it leaves
unset keeps its literal, and a role set to the colour it already has is not
a swap — so a pack that changes nothing produces nothing to rewrite.

* **Return type:**
  `dict`[`str`, `str`]

```pycon
>>> role_recolouring({"#a83249": "clothing", "#3b2a1a": "hair"},
...                  {"clothing": "#202028"}.get)
{'#a83249': '#202028'}
```
