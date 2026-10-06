# A project from nothing: units, staging and parts

Reference for the `an` skill (`../SKILL.md`: the index and the essentials).

## A project from nothing

Everything a render needs, created from Python or the CLI — no file from the `an` repo required. Run the recipe, write the scene, validate, render.

### Units and staging

- **Stage coordinates are scene pixels from the frame CENTRE, y DOWN.** Scene pixels are output pixels: nothing rescales with `meta.resolution`, so the same numbers fill more of a 1280x720 frame than of a 1920x1080 one. Path `points`, plane `offset`/`size`, `stage.at`, a `hop`'s `height` and every `x`/`y` tween use them. Text `size` is the exception: a fraction of frame height.
- **An `an character new --offline` character is about 265 px tall at `stage.scale: 1`** (the regular build): its drawn art runs from about 170 px above its stage point to 95 px below. **The stage point is not the feet**: the compiler places a rig by the middle of its bones (between the neck and the feet), so the depth of the feet depends on the build and the head scale — at `stage.scale: 1`, top / feet: `regular` 169 / 94 px, `squat` 127 / 52 (153 / 55 at `--head-scale 1.3`), `tall` 193 / 119, `stick` 150 / 75 (210 / 82 at `--head-scale 1.7`). `an character new` prints the numbers for the character it made (`cutan.characters.factory.stage_extent(desc)` in Python, `desc` the model or the `character.json` dict). **Or make it with `an character new --feet-origin`** (an#285): the rig then declares its `origin` at its feet, so `stage.at` is where it stands and every build placed at one `y` stands on one floor line. To stand two builds on one floor, give each `y = floor − feet·s`. At scale `s` placed at `stage.at: [x, y]`, its top is at `y − top·s` (170 for the regular build). The top edge of the frame is at `−height/2`, so keep `y − top·s − hop_height` above it — divided by the camera's zoom when one runs (`push_in` ends at 1.25x about the frame centre, `zoom_in` at 1.5x). At 1280x720 a two-shot is `scale` 1.2-1.5 at `x = ±230`; a single close is `scale` 1.8-2.0 at `y` 60-120 (lower is closer to the bottom edge).
- `hop` `height`, `shake` `amplitude`, `slide_in` `distance` are scene pixels, not multiplied by the entity's `stage.scale`.

### Addressing a character's parts

A target is `<entity id>/<node>`. The node paths each cut-out rig builds, and the rules for rotation and mirroring, are in the `cutan` skill (**Addressing a character's parts**).
