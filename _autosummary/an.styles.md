# an.styles

StylePack: art direction as a document, and the first reader the styles store has had.

The `styles` store was nine lines with no consumer — `rg '["styles"]'` found
only the mall wiring — while colour lived in three disconnected places: the
compiler’s `_CHARACTER_PALETTES`, six literals inside `runtime.js`, and the
character factory, which carried *two disagreeing* palette tables. an#106
retired `AssetRef(kind="style")` because it selected nothing. This is what the
word was reserved for.

**A pack recolours SVG art only where the art says what its colours are.**
The character factory records, per part, which literal it drew as which role
(`CharacterDescriptor.colour_roles`, see [`an.characters.colour_roles`](an.characters.colour_roles.md#module-an.characters.colour_roles)),
and the compiler rewrites exactly those literals into a new, content-addressed
inline texture — palette swapping. Untagged art (hand-drawn, DiceBear) is left
alone and the compiler warns once, naming it: a pack would otherwise have to
infer a role from a pixel, which is what produced an#99’s wrong-tone lid. So
the four reasons this module once gave for never touching SVG reduce to one
that still holds — no tags, no recolour. (The texture is inline, so staging and
content addressing are unaffected; the substitution rewrites paint attributes
only, never geometry or ids.)

**A pack must not declare a role it cannot change.** `lip`, `mouth_fill`,
`teeth`, `tongue` and the eye’s white are literals inside `runtime.js`; a role
that resolves to nothing is worse than an absent one, and [`UNREACHABLE_ROLES`](#an.styles.UNREACHABLE_ROLES)
plus its test is what keeps the list honest.

\*\*No `line.width`.\*\* A first draft carried one, and nothing read it: the
procedural rig’s stroke is a `runtime.js` literal and an SVG rig’s is inside
its drawing, so the field was written, serialized, and consumed nowhere — the
same shape this module refuses in `UNREACHABLE_ROLES`, and a rule is not a rule
if it exempts the module that states it. It comes back when something reads it.

Colours are **hex strings**, deliberately not DTCG colour objects:
`bench/palette.py` mirrors `runtime.js` verbatim, and a second colour
representation doubles the surface on which the two can silently diverge.

### Module Attributes

| [`REACHABLE_ROLES`](#an.styles.REACHABLE_ROLES)   | Roles a pack can actually change, because the COMPILER decides them and stamps them into the document the runtime draws.   |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| [`UNREACHABLE_ROLES`](#an.styles.UNREACHABLE_ROLES) | Roles a pack must NOT declare, with what makes each unreachable.                                                           |

### Functions

| [`resolve_palette`](#an.styles.resolve_palette)(pack, entity, default)   | `(skin, clothing, hair)` for one entity under `pack`.   |
|-------------------------------------------------------------------------------------------|---------------------------------------------------------|

### Classes

| [`StylePack`](#an.styles.StylePack)(\*\*data)   | Art direction for a project.   |
|------------------------------------------------------------------------|--------------------------------|

### an.styles.REACHABLE_ROLES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'accessory', 'clothing', 'ground', 'hair', 'leg', 'pupil', 'skin', 'sky', 'stroke'})*

Roles a pack can actually change, because the COMPILER decides them and
stamps them into the document the runtime draws.

`skin`, `clothing` and `hair` are `_CHARACTER_PALETTES`’ three components;
`leg` and `pupil` are the compiler’s own literals (`DFLT_LEG_COLOUR`,
`DFLT_PUPIL_COLOUR`); `sky` and `ground` are the environment presets’;
`stroke` is a stroked path’s default colour (`an.paths.DFLT_STROKE_COLOUR`,
an#161) — the arrowhead is filled in the same colour, so it is not a second
role. A path that names its own `color` is art and is left alone.
`accessory` (a hat, a sash) exists only in role-tagged SVG art — the
factory’s `colour_roles` — and reaches the document through the recoloured
texture, as do the SVG rig’s `skin`, `clothing`, `hair`, `leg` and `pupil`.

Every one of these is compiled with a marker colour and asserted to reach
the document by `tests/test_styles.py`. `pupil` shipped in this set wired to
NOTHING (an#112 review) because the guard checked set membership against the
set it was checking — a declared-reachable role that reaches nothing is the
same defect as an unreachable one, and it needs the same kind of test.

### *class* an.styles.StylePack(\*\*data)

Bases: `BaseModel`

Art direction for a project. Saved in the `styles` store.

```pycon
>>> pack = StylePack(name="noir", roles={"skin": "#d8d8d8", "clothing": "#202028"})
>>> pack.colour_for("skin")
'#d8d8d8'
>>> pack.colour_for("hair") is None
True
```

Per-entity overrides win over roles, which is what makes a pack usable on a
scene where one character must stay off-palette:

```pycon
>>> pack = StylePack(name="noir", roles={"skin": "#d8d8d8"},
...                  entities={"maya": {"skin": "#f4c89a"}})
>>> pack.colour_for("skin", entity="maya"), pack.colour_for("skin", entity="bob")
('#f4c89a', '#d8d8d8')
```

A role the renderer cannot reach is refused at construction, not ignored:

```pycon
>>> StylePack(name="x", roles={"lip": "#800000"})
Traceback (most recent call last):
...
pydantic_core._pydantic_core.ValidationError: ...
```

#### colour_for(role, , entity=None)

The colour for `role`, or `None` when the pack does not set it.

`None` rather than a default: the caller holds today’s literal, and a
pack that does not mention a role must leave it exactly as it was —
which is what keeps a scene with no pack byte-identical.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### entities *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

`{entity id: {role: "#rrggbb"}}` — a per-entity override of `roles`.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True, 'validate_by_alias': True, 'validate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### roles *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

`{role: "#rrggbb"}`. Hex strings, not colour objects — see the module
docstring for why a second representation is a liability here.

### an.styles.UNREACHABLE_ROLES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'eye_sclera': 'runtime.js draws the eye white as a literal 0xffffff in makeEye', 'lip': 'runtime.js \`_LIP_COLOR\`, drawn by makeMouth and never read from the document', 'mouth_fill': 'runtime.js \`_MOUTH_FILL\`', 'teeth': 'runtime.js \`_TEETH_COLOR\`', 'tongue': 'runtime.js \`_TONGUE_COLOR\`'}*

Roles a pack must NOT declare, with what makes each unreachable. These are
`runtime.js` literals: `_LIP_COLOR`, `_MOUTH_FILL`, `_TEETH_COLOR`,
`_TONGUE_COLOR`, and the eye white’s `0xffffff` — none of them read anything
from the compiled document, so a pack that named them would be accepted,
change nothing, and say nothing. `tests/test_styles.py` reads the literals
out of `runtime.js` so this list cannot quietly stop matching it.

### an.styles.resolve_palette(pack, entity, default)

`(skin, clothing, hair)` for one entity under `pack`.

A **lookup with a default**, not a rewrite: with no pack, or with a pack
that mentions none of the three, the caller’s own literals come back
unchanged and the compiled document does not move a byte.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> resolve_palette(None, "maya", ("#f4c89a", "#3a6ea5", "#3b2a1a"))
('#f4c89a', '#3a6ea5', '#3b2a1a')
>>> pack = StylePack(name="noir", roles={"clothing": "#202028"})
>>> resolve_palette(pack, "maya", ("#f4c89a", "#3a6ea5", "#3b2a1a"))
('#f4c89a', '#202028', '#3b2a1a')
```
