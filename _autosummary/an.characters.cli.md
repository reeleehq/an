# an.characters.cli

User-facing character CLI subcommands.

Wired into the top-level `an` dispatcher via `character_*` dispatch-friendly
functions in [`an.tools`](an.tools.md#module-an.tools). Each function here takes plain strings/bools
and returns a string for terminal display.

Subcommands (used as `an character <verb> ...`):

- `new`       — generate a fresh character from DiceBear or fallback art.
- `mouths`    — regenerate the 9-shape default mouth set.
- `validate`  — completeness check.
- `silhouette`— rasterize silhouettes; for two characters, also IoU.
- `preview`   — open an HTML viewer cycling visemes + idle animation.

### Functions

| [`add_gaze`](#an.characters.cli.add_gaze)(name[, out_dir, overwrite_eyes])         | Give `name` the eye stack (an#99): sclera and pupil slots under each lid, a filled closed lid, and the `gaze_travel` clamp — so `gaze_x` / `gaze_y` and the ambient saccades move its pupils.   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`contract`](#an.characters.cli.contract)()                                        | Print the art-package contract an illustrator must satisfy.                                                                                                                                     |
| [`mouths`](#an.characters.cli.mouths)(name[, out_dir, palette, variants])        | Regenerate the default 9-shape mouth set for `name`, plus its `viseme@<form>` variants, and declare them in the descriptor.                                                                     |
| [`new`](#an.characters.cli.new)(name[, out_dir, seed, style, voice_ref, ...]) | Create a new character at `out_dir`/`name`.                                                                                                                                                     |
| [`preview`](#an.characters.cli.preview)(name[, out_dir, open_browser])            | Render a small HTML viewer that previews all visemes + idle animation.                                                                                                                          |
| [`record`](#an.characters.cli.record)(name[, out_dir, output, duration, ...])    | Record a character's preview HTML to mp4.                                                                                                                                                       |
| [`silhouette`](#an.characters.cli.silhouette)(name[, other, out_dir, output, size])  | Render a black silhouette for `name` (and optionally compare to `other`).                                                                                                                       |
| [`validate`](#an.characters.cli.validate)(name[, out_dir])                         | Validate a character's directory structure and descriptor.                                                                                                                                      |

### an.characters.cli.add_gaze(name, out_dir='', overwrite_eyes=False)

Give `name` the eye stack (an#99): sclera and pupil slots under each
lid, a filled closed lid, and the `gaze_travel` clamp — so `gaze_x` /
`gaze_y` and the ambient saccades move its pupils. The expand step for a
character made before Wave 6; idempotent on one that has it.

name: character id
out_dir: parent directory; defaults to ./assets/characters
overwrite_eyes: replace hand-drawn eye parts with the synthesized outline

> and filled lid (refused otherwise — a promoted rig’s eyes are not the
> factory’s to redraw)
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.contract()

Print the art-package contract an illustrator must satisfy.

**Derived from the schema and the validator, never hand-written**, so it
cannot drift from what `an character validate` actually enforces — a
contract that disagrees with its checker is worse than none, because it
gets a human paid for work that cannot land.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.mouths(name, out_dir='', palette='', variants='happy,sad')

Regenerate the default 9-shape mouth set for `name`, plus its
`viseme@<form>` variants, and declare them in the descriptor.

Useful when you want to reset a character’s mouth art to the offline
fallback (e.g. after experimenting with hand-drawn mouths), or to give a
pre-an#98 character the variant sets its expressions prefer.

name: character id
out_dir: parent directory; defaults to ./assets/characters
palette: optional JSON string to override colors, e.g. ‘{“lip”:”#a44”}’
variants: comma-separated mouth forms (see `an character new`); “” = none

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.new(name, out_dir='', seed='', style='lorelei', voice_ref='', offline=False, acknowledge_attribution=False, overwrite=False, mouth_variants='happy,sad')

Create a new character at `out_dir`/`name`.

name: character id (used as the directory name and descriptor ‘name’)
out_dir: parent directory; defaults to ./assets/characters
seed: deterministic seed for DiceBear; defaults to `name`
style: DiceBear style. The default is CC0 — no attribution duty. Some styles

> are CC BY 4.0 and oblige whoever ships the video to credit the artist;
> those need –acknowledge-attribution. Run `an credits <project>` to see
> what a project owes.

voice_ref: voice id stored in the descriptor’s `voice_ref` field
offline: skip DiceBear and use the deterministic geometric fallback
acknowledge_attribution: accept the attribution duty of a CC BY style
overwrite: replace an existing directory at the target
mouth_variants: comma-separated mouth forms to draw as `viseme@<form>`

> sets (an#98) — a form an expression preset prefers (happy, sad, angry,
> surprised, afraid, disgusted); “” for the neutral set only
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.preview(name, out_dir='', open_browser=False)

Render a small HTML viewer that previews all visemes + idle animation.

The page includes the head SVG, cycles through `mouth_a … mouth_x`
once a second, and shows a ±2 px sine-wave breath on the head. Useful
for eyeballing a character’s mouth set before integrating into the
main runtime.

name: character id
out_dir: parent directory; defaults to ./assets/characters
open_browser: also open the file in the default browser

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.record(name, out_dir='', output='', duration=8.0, width=640, height=480)

Record a character’s preview HTML to mp4.

Real video file showing the new SVG character art animating: cycles
through all 9 visemes and applies the breath/head-tilt animation.

name: character id
out_dir: parent directory; defaults to ./assets/characters
output: output mp4 path; defaults to <character_dir>/preview.mp4
duration: recording length in seconds (default 8)
width / height: video resolution (default 640x480)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.silhouette(name, other='', out_dir='', output='', size=512)

Render a black silhouette for `name` (and optionally compare to `other`).

When two names are given, prints both silhouettes’ paths and an IoU
score (0..1; lower means more visually distinct).

name: character id
other: optional second character to compare against
out_dir: parent directory; defaults to ./assets/characters
output: output PNG path; defaults to <character_dir>/silhouette.png
size: square output size in pixels (default 512)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.cli.validate(name, out_dir='')

Validate a character’s directory structure and descriptor.

name: character id
out_dir: parent directory; defaults to ./assets/characters

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
