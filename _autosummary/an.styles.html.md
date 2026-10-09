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
(`CharacterDescriptor.colour_roles`, see `an.characters.colour_roles`),
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

**Surface treatments** (an#163 gap 5) are the pack’s second job: an outline, a
paper-gap drop shadow and a glow per drawable entity ([`SurfaceTreatment`](#an.styles.SurfaceTreatment),
`surface` with a per-entity `entity_surfaces` override), and one static
paper grain over the frame ([`Grain`](#an.styles.Grain)). Every one is a COMPILE-TIME
expansion into ordinary document content — underlay copies of a part’s own
visual, a gradient sprite, a seeded noise tile — never a runtime filter, and
never anything random at render time. `an.stage.surface` does the
expanding. The outline and the shadow reach ANY SVG art, role-tagged or not:
they copy a part’s texture rather than recolour it. Every width and offset is in
the rig’s own pixels, so a treatment scales with the character like paper would.

### Module Attributes

| [`REACHABLE_ROLES`](#an.styles.REACHABLE_ROLES)   | Roles a pack can actually change, because the COMPILER decides them and stamps them into the document the runtime draws.   |
|--------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| [`UNREACHABLE_ROLES`](#an.styles.UNREACHABLE_ROLES) | Roles a pack must NOT declare, with what makes each unreachable.                                                           |

### Functions

| [`resolve_palette`](#an.styles.resolve_palette)(pack, entity, default)   | `(skin, clothing, hair)` for one entity under `pack`.          |
|-------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| [`surface_for`](#an.styles.surface_for)(pack, entity)                | The treatments `entity` gets under `pack`, or `None` for none. |

### Classes

| [`StylePack`](#an.styles.StylePack)(\*\*data)        | Art direction for a project.                                             |
|-----------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`Outline`](#an.styles.Outline)(\*\*data)          | A darker, dilated copy drawn behind each part.                           |
| [`PaperShadow`](#an.styles.PaperShadow)(\*\*data)      | The "no-platen" paper-gap shadow: an offset, darkened copy of each part. |
| [`Glow`](#an.styles.Glow)(\*\*data)             | An additive radial-gradient sprite behind an entity.                     |
| [`Grain`](#an.styles.Grain)(\*\*data)            | One static paper-grain texture over the whole frame.                     |
| [`SurfaceTreatment`](#an.styles.SurfaceTreatment)(\*\*data) | Which treatments an entity gets.                                         |

### *class* an.styles.Glow(\*\*data)

Bases: `_Treatment`

An additive radial-gradient sprite behind an entity.

Its box is the entity’s drawn box grown by `radius`, and the gradient is
an ELLIPSE over that box: it holds `intensity` out to the entity’s box
along its shorter axis and fades to nothing at the edge — so on a tall
entity the halo is fainter at the top and bottom than at the sides.
Drawn with the engine’s native ADD blend (PixiJS 7 does it in the blend
equation, no filter), as the entity’s first child, so it moves with the
entity and lights the background around it, not the entity itself.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.styles.Grain(\*\*data)

Bases: `_Treatment`

One static paper-grain texture over the whole frame.

Seeded noise generated at COMPILE time (`an.stage.surface`),
tiled on the camera-immune overlay under any text, and MULTIPLIED onto the
frame — so it only ever darkens, by at most `amount`. The same seed is the
same grain on every frame and every machine; nothing is random at render
time.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.styles.Outline(\*\*data)

Bases: `_Treatment`

A darker, dilated copy drawn behind each part.

On a procedural part (rect, ellipse) it is the part’s own shape grown by
`width` — exact for a rect (rounded corners of radius `width`, which is
what dilating by a disk gives) and, for an ellipse, the ellipse with both
radii grown (exact on the axes and for circles). On an SVG part it is a
ring of copies of the part’s texture offset by `width` in
`an.stage.surface.OUTLINE_RING` directions, drawn in `color`
as a `tint`: tint MULTIPLIES, so the outline is exactly `color` where the
art is white and darker elsewhere — exact everywhere for black, and within a
few levels of it for the default near-black.

`nested` extends it to parts nested inside another part (face features
on the head). Off by default: the pieces of a cut-out are the paper; the
face is drawn on them. A procedural eye or mouth never gets one (they are
not copyable shapes); an SVG rig’s eyes and mouth do, under `nested`.

**Fading a treated part darkens it.** The copies are opaque and drawn
separately, so at `alpha` 0.5 the part shows its outline colour through
itself rather than the background. A group fade needs the subtree drawn to
a texture first (a filter), which this package refuses; the compiler warns
when an `alpha` channel reaches a treated part.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.styles.PaperShadow(\*\*data)

Bases: `_Treatment`

The “no-platen” paper-gap shadow: an offset, darkened copy of each part.

The copy sits in the part’s own container, so it follows every tween,
`play` and swap of the part with no channel of its own. The offset is
therefore in the PART’s frame: a part that rotates takes its shadow round
with it (a light fixed to the paper, not the room) — invisible at the
small offsets this is for, and a limit to know for a large one.

With an outline, the shadow is grown by the outline width so it shows past
the outline rather than hiding under it: exactly the outlined silhouette on
a procedural part; on an SVG part one copy scaled about the art’s centre, so
it grows the art’s BOX by the width (one copy, because translucent copies
would compound where they overlap).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.styles.REACHABLE_ROLES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'accessory', 'clothing', 'ground', 'hair', 'leg', 'pupil', 'skin', 'sky', 'stroke'})*

Roles a pack can actually change, because the COMPILER decides them and
stamps them into the document the runtime draws.

`skin`, `clothing` and `hair` are `_CHARACTER_PALETTES`’ three components;
`leg` and `pupil` are the compiler’s own literals (`DFLT_LEG_COLOUR`,
`DFLT_PUPIL_COLOUR`); `sky` and `ground` are the environment presets’;
`stroke` is a stroked path’s default colour (`an.stage.paths.DFLT_STROKE_COLOUR`,
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

#### entity_surfaces *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [SurfaceTreatment](#an.styles.SurfaceTreatment)]*

`{entity id: SurfaceTreatment}` — per-entity, key-by-key override of
`surface`.

#### gradient_for(role)

The pack’s gradient for `role`, or `None` (the plane keeps its own paint).

* **Return type:**
  [`Gradient`](an.paint.html.md#an.paint.Gradient) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> pack = StylePack(name="reiniger", gradients={"glass": {
...     "type": "radial", "stops": ["#fff4d6", "#e0a050"]}})
>>> pack.gradient_for("glass").type, pack.gradient_for("sky"), pack.gradient_for(None)
('radial', None, None)
```

#### gradients *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Gradient](an.paint.html.md#an.paint.Gradient)]*

`{role: Gradient}`. A stage plane that
names a `role` (`PlaneArt.role`) is drawn with the pack’s gradient
for it – how a style paints every environment’s backdrop as backlit
glass or a dusk sky without editing the environments. Role names are the
environments’ own, so they are free-form; a role no plane names simply
paints nothing in that scene.

* **Type:**
  **Gradient roles** (an#275)

#### grain *: [Grain](#an.styles.Grain) | [None](https://docs.python.org/3/builtins/constants.html#None)*

One static paper grain over the frame; `None` = none.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

#### policy *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

per aspect, the
methods it prefers, in order (`{"locomotion": ["loco.bounce"]}`: this
show bounces even when its characters have legs). The first that
applies wins; a shot’s own `policy` comes first, an author’s request
before both. `None` (the default) leaves every aspect to its chain,
and is not serialized, so a pack without one dumps as before.

* **Type:**
  The style’s **policy** (ADR 0002 decision 4, an#348)

#### roles *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

`{role: "#rrggbb"}`. Hex strings, not colour objects — see the module
docstring for why a second representation is a liability here.

#### surface *: [SurfaceTreatment](#an.styles.SurfaceTreatment) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Surface treatments for every drawable entity (characters and props);
`None` = none. See [`SurfaceTreatment`](#an.styles.SurfaceTreatment) and [`surface_for()`](#an.styles.surface_for).

### *class* an.styles.SurfaceTreatment(\*\*data)

Bases: `_Treatment`

Which treatments an entity gets. Each is off when absent.

In `StylePack.entity_surfaces` an entry OVERRIDES the pack’s `surface`
key by key, for the keys it sets: `{"glow": {...}}` adds a glow and keeps
the pack’s outline; `{"outline": false}` removes the outline. Which keys
were set survives a dump (only they are serialized), so a pack written with
`model_dump()` and read back means the same thing. `null` switches one
off too, but a dump with `exclude_none=True` drops it — and the override
then silently inherits the pack’s treatment — so `false` is the spelling
to store.

```pycon
>>> SurfaceTreatment(glow={}).model_dump()
{'glow': {'color': '#fff4c2', 'radius': 60.0, 'intensity': 0.5}}
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.styles.UNREACHABLE_ROLES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'eye_sclera': 'runtime.js draws the eye white as a literal 0xffffff in makeEye', 'lip': "cutan's runtime script \`_LIP_COLOR\`, drawn by makeMouth and never read from the document", 'mouth_fill': "cutan's runtime script \`_MOUTH_FILL\`", 'teeth': 'runtime.js \`_TEETH_COLOR\`', 'tongue': 'runtime.js \`_TONGUE_COLOR\`'}*

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

### an.styles.surface_for(pack, entity)

The treatments `entity` gets under `pack`, or `None` for none.

`None` is the answer for no pack, a pack without treatments, and an
entity whose override switched everything off — which is what keeps every
such scene’s compiled document byte-identical to before an#163.

* **Return type:**
  [`SurfaceTreatment`](#an.styles.SurfaceTreatment) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> pack = StylePack(name="sp", surface={"outline": {}},
...                  entity_surfaces={"sun": {"glow": {}}, "bob": {"outline": False}})
>>> sorted(surface_for(pack, "sun").model_dump())
['glow', 'outline']
>>> surface_for(pack, "bob") is None
True
>>> surface_for(pack, "maya").outline.width
3.0
>>> surface_for(None, "maya") is None
True
```
