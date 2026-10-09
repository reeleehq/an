# A project from nothing: units, staging and parts

Reference for the `an` skill (`../SKILL.md`: the index and the essentials).

## A project from nothing

Everything a render needs, created from Python or the CLI — no file from the `an` repo required. Run the recipe, write the scene, validate, render.

### Units and staging

- **Stage coordinates are scene pixels from the frame CENTRE, y DOWN.** Scene pixels are output pixels: nothing rescales with `meta.resolution`, so the same numbers fill more of a 1280x720 frame than of a 1920x1080 one. Path `points`, plane `offset`/`size`, `stage.at`, a `hop`'s `height` and every `x`/`y` tween use them. Text `size` is the exception: a fraction of frame height.
- **An `an character new --offline` character is about 265 px tall at `stage.scale: 1`** (the regular build). **It stands on its feet**: `an character new` declares the rig's `origin` at its feet (an#285, by default since 2026-10-09), so `stage.at: [x, y]` is where its feet touch the floor, and every build placed at one `y` stands on one floor line; its art runs about 265 px above that point (`top`; per build at `stage.scale: 1`: `regular` 264, `squat` 179, `tall` 312, `stick` 225). `an character new` prints the numbers for the character it made (`cutan.characters.factory.stage_extent(desc)` in Python: `feet` is then 0). **A character made before then, or with `--no-feet-origin`, is placed by the middle of its bones**, not its feet: the depth of the feet below `stage.at` depends on the build and head scale (top / feet at `stage.scale: 1`: `regular` 169 / 94 px, `squat` 127 / 52 (153 / 55 at `--head-scale 1.3`), `tall` 193 / 119, `stick` 150 / 75 (210 / 82 at `--head-scale 1.7`)). Existing characters are never converted implicitly; `an character feet-origin <name>` converts one and prints how much to add to its `stage.at` y in a scene made before (`--undo` goes back). For such a character, to stand it on a floor give it `y = floor − feet·s`. At scale `s` placed at `stage.at: [x, y]`, its top is at `y − top·s` (`top` 264 for a new regular character, 170 for one placed by its bones). The top edge of the frame is at `−height/2`, so keep `y − top·s − hop_height` above it — divided by the camera's zoom when one runs (`push_in` ends at 1.25x about the frame centre, `zoom_in` at 1.5x). At 1280x720 a two-shot is `scale` 1.2-1.5 at `x = ±230`; a single close is `scale` 1.8-2.0 with its feet below the frame: `y` 240-300 for a character standing on its feet (60-120 for one placed by its bones; lower is closer to the bottom edge).
- `hop` `height`, `shake` `amplitude`, `slide_in` `distance` are scene pixels, not multiplied by the entity's `stage.scale`.
- **What is in front of what (depth), three tools** (an#458):
  1. **Entity order** for characters and props: later in `entities` draws in front. "Presenter behind the desk" is the presenter listed BEFORE the desk; "desk behind the presenter" is the desk listed first.
  2. **`stage: {after: <anchor>}`** to put an entity BETWEEN two others: right after a plane (`<environment>/<plane>`, e.g. `set/back_wall`) or after another entity id. Example: a desk between the wall plate and the presenter is `{kind: prop, id: desk, store: props, ref: desk, stage: {at: [0, 180], after: set/back_wall}}`, while the presenter stays in ordinary entity order, in front of everything.
  3. **`characters_after`** on an environment, which names the plane the characters stand in front of (a foreground plane after it covers them).
  When a brief's depth can be read two ways ("behind the desk"), say which reading you chose in your reply, because each is one line to flip.

### Addressing a character's parts

A target is `<entity id>/<node>`. The node paths each cut-out rig builds, and the rules for rotation and mirroring, are in the `cutan` skill (**Addressing a character's parts**).
