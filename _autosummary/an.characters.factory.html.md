# an.characters.factory

High-level entry points: build and inspect a character.

The [`new_character()`](#an.characters.factory.new_character) function wires together fetching/wrapping art,
slicing it into per-part SVGs, generating the default mouth set, and
writing a complete character directory + `character.json` descriptor.

Checking one is [`an.characters.validate`](an.characters.validate.html.md#module-an.characters.validate)’s job, not this module’s — it
opens every part and reports [`an.verify._base.Finding`](an.verify.html.md#an.verify.Finding) s, so a character
problem routes the way every other verifier’s does (an#78).

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     descriptor_path = new_character(d, name='nobody', use_dicebear=False)
...     descriptor_path.parent.name, descriptor_path.name
('nobody', 'character.json')
```

### Module Attributes

| [`EYE_CANVAS`](#an.characters.factory.EYE_CANVAS)   | The eye's geometry in its 64x32 canvas, shared by the four synthesizers so the sclera, the pupil and the lid outline agree (an#99).   |
|---------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| [`GAZE_PARTS`](#an.characters.factory.GAZE_PARTS)   | The parts a rig gains with `an character add-gaze`.                                                                                   |

### Functions

| [`add_gaze`](#an.characters.factory.add_gaze)(char_dir, \*[, skin, overwrite_eyes])   | Give a character the eye stack (an#99): three sibling slots per eye under the head — `<side>_sclera` (white fill) below `<side>_pupil` below `<side>_eye` (the existing slot, now the lid, drawn above the pupil) — with synthesized parts, an outline-only open eye, a FILLED closed lid, the `gaze_travel` clamp, and draw orders that put the lid over the pupil.   |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`declare_mouth_variants`](#an.characters.factory.declare_mouth_variants)(descriptor, variants)     | Declare a `viseme@<form>` set per variant on `descriptor` — the set's keys map to `mouth_<shape>_<form>` attachments, which are added to the default skin's `mouth` slot with the neutral mouth's geometry.                                                                                                                                                            |
| [`gaze_travel_for`](#an.characters.factory.gaze_travel_for)([rx, ry, pupil_r])               | The pupil's travel per axis, in view-box units: the sclera's clearance minus the pupil's radius — the semi-axes of the inner ellipse the gaze axes' unit circle maps onto.                                                                                                                                                                                             |
| [`new_character`](#an.characters.factory.new_character)(out_dir, \*, name[, seed, ...])    | Build a complete character on disk.                                                                                                                                                                                                                                                                                                                                    |

### an.characters.factory.EYE_CANVAS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]* *= (64, 32)*

The eye’s geometry in its 64x32 canvas, shared by the four synthesizers so
the sclera, the pupil and the lid outline agree (an#99).

### an.characters.factory.GAZE_PARTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('sclera_l', 'sclera_r', 'pupil_l', 'pupil_r')*

The parts a rig gains with `an character add-gaze`. Optional — never in
`REQUIRED_PARTS`: a pre-Wave-6 rig without them still renders, and gaze is
a no-op on it.

### an.characters.factory.add_gaze(char_dir, , skin=None, overwrite_eyes=False)

Give a character the eye stack (an#99): three sibling slots per eye under
the head — `<side>_sclera` (white fill) below `<side>_pupil` below
`<side>_eye` (the existing slot, now the lid, drawn above the pupil) —
with synthesized parts, an outline-only open eye, a FILLED closed lid, the
`gaze_travel` clamp, and draw orders that put the lid over the pupil.
Idempotent: a rig that already has the stack is rewritten to the same
state. Returns the descriptor path.

The open and closed eye parts are REWRITTEN (outline-only, filled lid), so
on a rig whose eyes are not this factory’s drawings — a promoted hand rig —
it refuses unless `overwrite_eyes=True`: the stack’s geometry is the
synthesized eye’s, and an illustrator’s eyes would be silently replaced
(an#99 review). Such a rig wants its own outline-only open eye, filled
lid, sclera and pupil parts drawn to its own geometry.

This is the **expand** step for a pre-Wave-6 descriptor: no migration
inserts pupil slots, because their art would be absent and absent art is
fatal under `strict_assets` — every existing character would stop
rendering on the bench.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.characters.factory.declare_mouth_variants(descriptor, variants)

Declare a `viseme@<form>` set per variant on `descriptor` — the set’s
keys map to `mouth_<shape>_<form>` attachments, which are added to the
default skin’s `mouth` slot with the neutral mouth’s geometry. The
neutral set is the SSOT for which shapes exist; a variant mirrors it.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.characters.factory.gaze_travel_for(rx=14, ry=10, pupil_r=5)

The pupil’s travel per axis, in view-box units: the sclera’s clearance
minus the pupil’s radius — the semi-axes of the inner ellipse the gaze
axes’ unit circle maps onto. The compiler clamps the summed gaze to 0.95
of that circle (`GAZE_ELLIPSE_MARGIN`), which is what keeps the pupil disc
inside the white at every angle without a runtime mask.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

```pycon
>>> gaze_travel_for()
{'x': 9.0, 'y': 5.0}
```

### an.characters.factory.new_character(out_dir, , name, seed=None, style='lorelei', voice_ref=None, use_dicebear=True, acknowledge_attribution=False, overwrite=False, mouth_variants=None, gaze=True)

Build a complete character on disk.

`gaze` (an#99) adds the eye stack — sclera and pupil slots under each
lid, a filled closed lid, the `gaze_travel` clamp — through
[`add_gaze()`](#an.characters.factory.add_gaze), so `gaze_x`/`gaze_y` and the ambient saccades reach the
pupils. Off, the eye is the single pre-stack drawing.

`mouth_variants` (an#98) — `{form: smile offset}` — writes one more
9-shape mouth set per form (`mouth_<shape>_<form>.svg`) and declares it
as the `viseme@<form>` swap set, with its attachments in the default
skin’s `mouth` slot, so an expression preset preferring that form
selects it. `None` means [`DEFAULT_MOUTH_VARIANTS`](an.characters.mouth_set.html.md#an.characters.mouth_set.DEFAULT_MOUTH_VARIANTS)
(happy, sad); `{}` means the neutral set only.

Steps:

1. Fetch a DiceBear avatar (skip if `use_dicebear=False` — useful for
   offline tests).
2. Wrap it into the canonical `an` cutout SVG (skeleton + illustration
   groups), saved as `<name>.svg`.
3. Slice each part into `parts/<part>.svg`.
4. Write the 9-shape default mouth set into `parts/mouth/`.
5. Synthesize a few derived parts (open/closed eyes, brows) so the
   character is complete out of the box.
6. Emit a `character.json` descriptor.

Returns the path to the created `character.json`.

Raises [`FileExistsError`](https://docs.python.org/3/builtins/exceptions.html#FileExistsError) if `out_dir/name` already exists and
`overwrite=False`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
