---
name: an
description: Use whenever the user wants to author, edit, render, or iterate on a structured animation, cartoon, explainer video, or motion graphic via the an Python package. Triggers on "make a cartoon", "animate", "render a scene", "let's build a video", "an init", "an validate", "an render", or any request that maps to the chat-driven director workflow.
---

# an — top-level orchestrator

`an` is a Python package that turns a directorial chat conversation into rendered video. The user is the **director**; you are the **assistant orchestrator**; backends (cutout, Manim, Remotion, whiteboard) are the **executors**.

This skill is self-contained: *A project from nothing* below has a complete `scene.md` and the Python that creates every asset document, so nothing here needs the `an` source repo. Paths such as `misc/docs/…`, `misc/demos/…` and `examples/…` are in that repo (github.com/thorwhalen/an) — background for someone changing `an`, not steps you need.

## What works today

The full pipeline is wired and runs **without API keys** by default (offline TTS produces silent audio, offline lip-sync deterministically generates viseme tracks). Real speech via `ElevenLabsTTS`, word-aligned visemes via `WhisperLipSync`, full phoneme alignment via `RhubarbLipSync`, and free-text editing via `an iterate` (Claude Opus 4.7) plug in once the user sets the relevant env vars.

CLI surface:

- `an init <dir>` — create a fresh project on disk: `scene.md` (a `yaml meta` block only — no shots yet), `ir/scene.json`, and the store folders under `assets/`. Defaults: **1920x1080, 30 fps**; change `resolution:`/`fps:` in the meta block (1280x720 renders roughly twice as fast).
- `an validate <dir>` — schema + semantic validation.
- `an sync <dir>` — reconcile `scene.md` ↔ `ir/scene.json` (newer file wins).
- `an render <dir> [--tts NAME] [--lipsync NAME] [--parallel auto|N] [--strict-assets] [--step-hz N]` — full pipeline: validate → audio → render per shot → ffmpeg-concat (or, with transitions or sounds, `an.assemble`) → `output/main.mp4`. TTS and lip-sync providers are pluggable: `--tts elevenlabs` (needs `ELEVEN_API_KEY`) for real speech, `--lipsync whisper` (needs `faster-whisper`) for word-aligned visemes, `--lipsync rhubarb` (needs the rhubarb binary) for full phoneme alignment. Whatever the provider, the compiler runs the co-articulation passes over its raw track before emitting the mouth channel (an#97: duplicates merged, sub-frame tongue shapes dropped, every shape 2/24 s ahead of its sound, a beat to close before rest, and a 0.14 s minimum hold that VOTES — the shape with the largest in-window span × dominance wins and shows from the window start — instead of dropping late arrivals). Rhubarb's recognizer follows the language: `an render --language en` (the default) uses `pocketSphinx` with the transcript, any other tag `phonetic` without one; `make_lipsync("rhubarb", language=…)` in Python (an#96). Defaults are offline. Switching providers auto-re-synthesizes the affected lines. `--parallel auto` runs each shot in its own thread (Phase 11c; ~N× wall-time speedup on N-shot scenes; capped at min(shots, cpu, 4)). `--strict-assets` refuses to draw a **stand-in** for an asset the project's stores don't supply — the placeholder rig for a missing character descriptor, the default backdrop for an unknown environment ref. Without it you get a warning and a plausible render of a *different* picture (an#33); use it whenever the output is going to be measured or compared. `--step-hz N` (an#89) renders authored tweens **stepped** — pose updates N times a second on a shot-wide grid (every tween in a shot shares it; a tween's own start and end are pose changes too, so an off-grid start or end changes pose on that frame as well), so at 30 fps `15` is "on twos" and `10` "on threes" (the Spider-Verse look: characters on twos, camera and simulation on ones); it overrides the scene's `meta.step_hz` for this render, a shot's own `step_hz` still wins, and the camera, blinks, `play` clips and swap channels are never stepped. Default: smooth.
- `an iterate <dir> "<instruction>"` — free-text edit. Sends the current scene + instruction to Claude (Opus 4.7 + adaptive thinking), parses a structured patch list, validates against the schema, persists the new scene to disk, and invalidates affected shots' caches so the next render only redoes those shots. Needs `ANTHROPIC_API_KEY`. Pass `--no-apply-changes` for a dry run.
- `an preview <dir> [--shot ID] [--no-browser]` — live preview in a browser. Spins up an HTTP server, compiles the chosen shot (default: first), polls `scene.md` / `ir/scene.json` for changes, and the browser auto-reloads via a 500 ms `Last-Modified` poll. Lossy: visuals only, no audio. Honours the scene's / shot's `step_hz` (no flag of its own). Blocks until Ctrl-C. Use it for quick iteration on layout / blocking before `an render`.
- `an character new <name> [--out-dir DIR] [--seed S] [--style adventurer] [--offline] [--mouth-variants happy,sad]` — create a character at `DIR/<name>`; **`DIR` defaults to `./assets/characters` relative to the CURRENT directory, not to any project** — run it from the project root or pass `--out-dir <project>/assets/characters` (every `an character` subcommand that names a character takes `--out-dir` the same way). It writes with parts/ (the body, brows, and the sclera/pupil/lid eye stack), the 9-shape mouth set (plus a `viseme@happy` and `viseme@sad` variant set by default — the mouth forms the expression presets prefer; `an character mouths --variants angry` adds more), and `character.json`. By default fetches a DiceBear avatar; `--offline` uses a deterministic geometric fallback (no network). **For production scenes with dialogue, prefer `--offline` or hand-rig a character following the Pose Animator convention (see `examples/promote_demo/`).** DiceBear avatars have eyes/brows/mouth baked into the head SVG, so the cutout adapter suppresses the overlay mouth + viseme channel for them — audio plays but the mouth doesn't move. Treat DiceBear as a bootstrap path only.
- `an character add-gaze <name>` — give an older character the eye stack (sclera/pupil/lid) so gaze and ambient saccades move its pupils (new characters get it by default); `an character mouths <name> [--variants happy,sad]` — regenerate the 9-shape default mouth set and its `viseme@<form>` variants (declared in the descriptor) (`mouth_a` … `mouth_x`). Variants are ADDED: sets already declared stay declared, so `--variants angry` on a new character gives it `happy`, `sad` and `angry`. It also redraws the neutral set, so run it before hand-editing mouth art, not after. **When `an validate`/`an render` warns `<name> declares no 'viseme@angry' set`**, a dialogue `[angry]` (or an `expression`) wants a mouth form the character lacks: the face still works, the mouth just uses the neutral shapes; `an character mouths <name> --variants angry` fixes it.
- `an character validate <name>` — check parts, mouth set, pivots, descriptor.
- `an character silhouette <name> [--other <name2>]` — render a black silhouette PNG; with `--other`, also computes IoU between the two silhouettes (Disney silhouette test).
- `an character preview <name> [--open-browser]` — write `preview.html` cycling all 9 visemes with breath/head-tilt animation.
- `an character record <name> [--duration 8] [--width 640] [--height 480]` — record `preview.html` to mp4 via Playwright + ffmpeg. Produces `<character_dir>/preview.mp4` (or `--output PATH`). Real video file showing the new SVG art animating.
- `an check` — diagnose system deps (ffmpeg, node, rhubarb, playwright, elevenlabs, manim).

Python surface (everything in `an.__all__`):

- Scene IR: `SceneIR`, `Shot`, `Dialogue`, `AssetRef`, `Camera`, `Resolution`, `Meta`.
- Composition: `sequence`, `parallel`, `delay`, `loop`, `tween`, `set_`, `play`, `flatten`. **`play` resolves against the target character's descriptor `animations`** (an#7): `play("maya", "idle_breath")` compiles the seeded breath — three sine tracks, torso bob (±2 view-box px), head tilt (±0.5°, a quarter cycle behind) and a slower weight shift (±1.5 px), all on the animation's **6 s** cycle — into channels around the rig's rest pose; because `idle_breath` loops, a play with no `duration` runs to the **shot end** (a bounded loop is `duration=…`). `play("maya", "blink")` swaps the eyelids through the same swap path as compiled blinks. `loop=None` uses the animation's own `loop`. Resolution is `an.characters.play`, shared by `an validate` and the compiler, so both refuse the same plays with the same words: an undeclared name (the declared ones listed), a bone with no slot of its own, an unknown bone property, a frame naming art that is not on disk, a face slot suppressed by `face_overlay: false`.
- Project: `init`, `load`, `save`, `Project`, `build_project_mall`.
- Sync: `markdown_to_ir`, `ir_to_markdown`.
- Validation: `validate_schema`, `validate_semantic`.
- Diagnostics: `check_requirements`.
- Audio (in `an.audio`): `OfflineTTS`, `ElevenLabsTTS`, `OfflineLipSync`, `WhisperLipSync`, `RhubarbLipSync`, `WordTimingsLipSync` + `StaticWordTimings` (inject pre-computed `(text, start, end)` tuples — skips transcription entirely), `produce_audio_for_scene`, `make_tts`, `make_lipsync`. The `WordTimingProvider` protocol is the structural contract; any object exposing `name: str` + `words_for(audio, transcript=)` works as a provider.
- Verify (in `an.verify`): `LayoutLintVerifier`, `HumanInTheLoopVerifier`, `MediaQualityVerifier`, `VisionLMVerifier`.
- Orchestrate (in `an.orchestrate`): `orchestrate(project_dir, *, tts="offline", lipsync="offline", parallel=None, ...) -> OrchestratorReport`, `iterate(project_dir, instruction) -> IterateResult`. `tts` and `lipsync` accept either provider-name strings or instances — pass a `WordTimingsLipSync(...)` to inject pre-computed timings instead of running whisper.

Backends registered: `cutout` (real, with face rig + a compile-time FACE SOLVER (an#98: `expression` actions and dialogue `[emotion]` sugar summed into one channel per (node, property) — brows, eyelids, the mouth's `viseme@<form>` set) + compiled blinks (an eyelid swap where the rig has closed-eye art, a squash otherwise — an authored eye channel overrides them) + bezier mouth shapes per viseme + swap channels + environment backdrops), `manim` (works if `manim` installed), `remotion` (skeleton), `whiteboard` (stub).

## Motion presets (`an.motion`)

A vocabulary of cut-out moves: each preset is a Python function that expands to ordinary `tween`s through `sequence`/`parallel`, so the timeline, `an validate` and the renderer see nothing new. Compose them like any action: `sequence(pop_in("maya"), hop("maya"), nod("maya"))`.

**From `scene.md`, play a preset by NAME** (an#166): `{kind: play, target: charlie, animation: hop, args: {height: 30}, start: 1.0}`. A `play` whose name the character's descriptor does not declare — or any `play` on an entity with no descriptor (the procedural placeholder, a prop) — falls back to `an.motion.PRESETS`. **A descriptor animation of the same name wins.** The compiler builds the preset at the moved node's BUILT rest pose, so no `rest=` is ever needed (a `shake` on the right-hand character of two stays centred on its `x = 110`). `args` are the preset's keyword parameters (`height`, `amplitude`, `cycles`, `part`, `angle`, …; never `rest` or `target`); `duration` stretches the whole move to that length, `speed` divides it (not both); `loop: true` is refused (a preset is a one-shot — use its own `cycles`/`count`/`steps`). `an validate` and the compiler give the same verdict (`an.characters.play.play_problems`): an unknown name lists both the descriptor's animations and the presets; an unknown parameter lists the accepted ones; a node the rig does not build (`point` on `charlie/arm_r`) lists the built ones. **Place preset plays with `start:`, not a `sequence`**: like every `play` with no `duration`, a preset play is zero-width there, so two in a row overlap; `an validate` warns when one runs past the shot end. For `point`, the target is the arm node (`charlie/right_arm` on the placeholder, whose limbs are rects hung from their joint, so a rotation pivots at the shoulder like a descriptor rig's bone — an#173).

| Preset | Moves | Target |
|---|---|---|
| `pop_in` | `scale_x`/`scale_y` 0 → rest, overshooting (`OVERSHOOT` Bézier) | entity |
| `hop` | `y` up by `height` and back | entity |
| `shake` | `x` side to side `cycles` times | entity |
| `nod` | `rotation` of `<entity>/<part>` (`part="head"`), `count` dips | entity (+ part) |
| `point` | `rotation` of an arm out, `hold`, back | the ARM node: `charlie/right_arm` (procedural), `maya/arm_r` (descriptor; pass a positive `angle`, that arm hangs on the viewer's left) |
| `slide_in` / `slide_out` | `x` from / to `distance` px off `from_side`/`to_side` | entity |
| `squash_stretch` | `scale_x`/`scale_y` squash, stretch, settle | entity |
| `waddle` | per step: `rotation` rock ± `angle` and `y` bob by `lift`; `travel` moves `x`; `angle=0` is a plain bob | entity |

All parameters are keyword-only with module-constant defaults (`DFLT_*`); `an.motion.PRESETS` is the name → function table. Rules that bite:

- **In Python, values are absolute, so a preset needs the node's rest** (a `play` from `scene.md` reads it for you). `rest=None` is the identity pose — right for rotations, and for `y`/scale of an entity with no `stage` placement. An entity's `x` is laid out (`-110`/`110` for two characters), so a move on `x` in a multi-character shot, or anything on a staged entity, takes `rest=rest_pose(shot, "charlie", mall=mall)`, which reads the value off the compiler's own scene builder. For `nod`/`point`, pass the PART's rest (`rest_pose(shot, "charlie/head")`).
- **An unknown target makes the render throw** (the runtime refuses an unknown node); `rest_pose` raises for it up front. The rigs are flat and name their arms differently (see `point`).
- **`scene.md` drops composition trees.** A preset composed in Python survives a `scene.md` edit as `as_leaves(preset, start=t)` — top-level tweens with `start:`, which round-trip; a `play` of its name is simpler still.
- **Presets write their own easings**, so a scene `default_easing` does not reach them.
- **Each preset ends with a `set` pinning every property it moved at its end value.** Frames sample `i / fps` and the runtime holds the last pose applied, so a tween ending between frames would leave the property off by part of its last segment (under `step_hz`, by all of it). The `set` holds until the next tween on that property.
- Presets are ordinary tweens, so `step_hz` steps them — the jerky South Park look is `sequence(...)` plus `step_hz`. A segment shorter than one step (a default `shake` has 57 ms segments) mostly vanishes under `step_hz` 10–15; lengthen `duration` or lower `cycles` for a stepped shot.

## Markdown surface

`scene.md` supports these fenced blocks:

- ` ```yaml meta ` — title, duration, fps, resolution, default_renderer, notes, and optional `step_hz` (stepped timing for tweens: `0 < step_hz <= fps`; `15` at 30 fps = "on twos") and `default_easing` (an#166): the easing of every authored `tween` that names none — `linear` for a snappy style, `[0.34, 1.56, 0.64, 1.0]` for an overshoot. Precedence: the tween's own `easing` > `default_easing` > the built-in `ease_in_out`. A tween that writes `easing: ease_in_out` keeps it under any default. It reaches authored tweens only — not motion presets, the camera, blinks or `play` clips — and an unknown name is a validate error. Also optional `sounds` (film-time sound cues — see *Transitions and sound* below).
- ` ```yaml shot ` — duration, camera, options, and optional `step_hz` (overrides the scene's for this shot). `camera: {move: …}` takes any of the nine the compiler implements — `hold`, `push_in`, `pull_out`, `zoom_in`, `zoom_out` and, since an#109, `pan_left`, `pan_right`, `tilt_up`, `tilt_down`. A move is sugar for `camera: {keys: [...]}`, which is the same code path written out; write `keys` for any distance other than the third-of-a-frame a pan travels. An unrecognised move **raises**.
- ` ```yaml entities ` — list of AssetRef-shaped dicts. `kind` ∈ `character | environment | voice` (an#106 retired `style`: it selected nothing, and the word named the renderer; art direction arrives as a StylePack, #112). Environment refs: `park | indoor | night | sunset | default`.
  - **`kind: prop` renders** since an#108. A prop is an `an.props.PropDescriptor` in the `props` store (`assets/props/<ref>/prop.json` beside a `parts/` folder) — same rig machinery as a character, different defaults: one bone, one slot, no face, no blink. Two states are the swap-channel machinery a viseme uses (`asset_sets: {lamp: {off, on}}` plus `set lamp on`). Placement is `stage: {at: [x, y], scale: s}` on the entity. **There is no placeholder rig**: the built-in placeholder is a humanoid, so an unresolvable prop raises rather than drawing a person where the lamp should be.
  - **A stroked path is a prop too** (an#160): a document with `kind: PathDescriptor` in the props store (`assets/props/<ref>/prop.json`, no `parts/`), placed as an ordinary `kind: prop` entity. It is the map-arrow / route / border / connector / timeline primitive: `points` in scene pixels (a polyline, or `curve: cubic` for chained Béziers, `p0 c1 c2 p1 c1 c2 p2 …`), `color` (`#rrggbb`), `width`, `cap`/`join`, `arrowhead: true` (with optional `head_length`/`head_width` in pixels; default 3.5× and 3× the width), and the initial `trim_start`/`trim_end`. **Draw-on is an ordinary tween**: `{kind: tween, target: <id>, property: trim_end, from: 0, to: 1}` — trim is in fractions of **arc length**, so the tip moves at constant speed along the route whatever its shape; the arrowhead sits on the moving tip, oriented along the leg it is on, and grows in while the visible length is shorter than it. Start a draw-on hidden with `trim_end: 0` in the document; a trim tween with no `from` starts from the document's own value, so `{kind: tween, target: route, property: trim_end, to: 1}` is then a draw-on. Set-but-inert fields raise (`head_length` without `arrowhead`, `samples_per_segment` on a polyline, a zero-length path). The entity's `overrides` are merged over the stored document and validated strictly — reuse one arrow style with per-shot `points`; an unknown key **raises**. `trim_start`/`trim_end` on anything that is not a path **raises** at validate and compile. Not a StylePack role yet (`color` is explicit).
  - **Art direction is a `StylePack`** (an#112): a document in the `styles` store, named by `style_pack:` in `yaml meta`. `roles` maps a role — `skin`, `clothing`, `hair`, `leg`, `pupil`, `sky`, `ground` — to a hex colour; `entities` overrides one character. It recolours what the COMPILER decides and **not SVG art** (those colours are inside the drawings; the compiler warns naming the rigs it could not reach). Nothing recolours SVG today — a pack seam in the character factory is the obvious home and is not built — so recolour an SVG rig by editing its art or generating it in the colours you want. A pack may not name `lip`/`mouth_fill`/`teeth`/`tongue`/`eye_sclera`: they are `runtime.js` literals, and declaring one is **refused** rather than ignored. A declared pack that is missing **raises** — art direction the author asked for and did not get is a different picture that renders happily.
  - **Text is a prop too** (an#155) — title cards, labels, word-by-word reveals. A document with `kind: TextDescriptor` in the props store (`assets/props/<ref>/prop.json`), placed as a `kind: prop` entity whose `overrides` usually carry the words (`overrides: {text: "Paris"}` — one stored style, many labels). Fields: `text` (newlines break lines), `layer` (`world` — in the scene, moves with the camera — or `overlay` — a layer the camera cannot touch: a title holds still through a push-in), `unit` (`word` | `glyph` | `line`: what one animatable node is), `size` (fraction of frame HEIGHT, default 0.06), `color` (`#rrggbb`), `align`, `max_width` (fraction of frame width, wraps), `leading`, `tracking` (em, `unit: glyph` only), `anchor` (overlay only: `top`, `bottom`, `center`, `top-left`, … inside the title-safe area; a world block is placed with `stage.at`), `font`. **Every unit is a node**: `title/word_0`, `title/word_1`, … (spaces are not units), so a reveal is ordinary tweens on `alpha`/`scale_x`/`scale_y`/`rotation` per unit (`x`/`y` are absolute and hold each unit's place in the line — a shared `y` tween stacks every word on one baseline; read a unit's offset with `an.motion.rest_pose`); a unit that starts later needs a `set` to its starting value at 0 or it shows until its turn — `an.text.stagger("title", n, "alpha", to=1, from_=0, duration=0.3, step=0.15)` writes both for you (extend `shot.actions` with it). **Fonts:** leave `font` unset for the built-in face (Aileron, CC0 — the same on every machine); otherwise `font` is a font FILE (`.ttf`/`.otf`/`.ttc`), absolute or relative to the text's own folder in `assets/props/<ref>/`. A family name like `Helvetica` is refused (it would depend on what the machine has installed); a missing file, a file that is not a font, and a character the face has no glyph for (the built-in face is printable ASCII plus curly quotes, `…` and `©«°±´·»` — an en/em dash or `é` raises) all **raise** — nothing falls back. A target naming a unit the block does not build (`word_5` of a three-word title) raises at validate and compile, listing the units.
  - **Two environment paths.** A store entry that is an `an.environments.EnvironmentDescriptor` **with planes** builds them, in list order (an#110): each plane has a `depth` — Godot's ratio, `1.0` = the character plane (emits nothing), `0` = does not pan, `>1` = foreground. **Depth compensates translation only**; a zoom is uniform across every plane, so pair a `depth = 0` plate with a pan rather than a push-in (depth-aware zoom is the dolly, not yet built) — and `characters_after` names the plane the characters stand in front of. An unknown key **on a plane raises** (`Plane` is `extra="forbid"`). Anything else — a free-form `meta.json`, a preset name — takes the legacy preset-override path, which reads exactly `sky_color`, `ground_color`, `ground_y` and **warns-and-drops** the rest. That is an intersection filter, not a refusal, and it is deliberate: the store's natural shape includes `name`/`description`/`tags`. So a `planes:` key on a document that does not declare `kind: EnvironmentDescriptor` still vanishes with a warning.
  - **A ref the stores can't supply gets a stand-in, and says so.** A character with no descriptor renders the placeholder rig; an environment ref that is neither a store entry nor a built-in preset (`park`/`indoor`/`night`/`sunset`/`default`) renders the default backdrop. Both warn, and both are recorded per entity in the compiled scene's `asset_resolution`. Pass `--strict-assets` to make them fatal.
- ` ```yaml actions ` — list of `tween` / `set` / `play` action dicts. Optional `start` (seconds) wraps a leaf in `sequence(delay(start), action)` so flatten gives correct absolute times. `{kind: play, target: maya, animation: idle_breath}` plays a descriptor animation (`duration`/`loop`/`speed` optional) — or, for a name the descriptor does not declare, a motion preset with optional `args` (see *Motion presets*): a non-looping one fills its natural duration (a descriptor animation's, or a preset's), a looping one with no `duration` runs to the shot end. Inside a `sequence`, a play without `duration` has **zero width** — the next sibling starts at the same instant — so give it an explicit `duration` when something must follow it. An `expression` action (`- kind: expression / target: <entity> / preset: happy [/ axes: {brow_height_l: 0.5}] [/ intensity] [/ duration] [/ blend]`) holds a face on a character, silent or speaking; `duration` omitted runs to the shot end. A `face_overlay: false` character (DiceBear) refuses one at validate. `axes: {gaze_x: 1.0}` turns the pupils (a rig without the eye stack ignores it); every rig with pupils also makes small ambient saccades of its own, seeded by the character's name.
  - **Transform properties:** `x`, `y`, `rotation`, `rotation_rad`, `scale_x`, `scale_y`, `skew_x`, `skew_y`, `pivot_x`, `pivot_y`, `alpha`, and — on a stroked path only — `trim_start`, `trim_end`. **Units:** `x`/`y` are scene pixels (see *Units and staging*); `rotation` is **radians** (`rotation_rad` is the same property; a descriptor's `rotation_deg` is the rig's rest pose in degrees and is not animatable); scales and `alpha` are factors. Any other property names a **swap set** (next bullets) and is refused at compile unless the target's descriptor declares it.
  - **`tint`** (an#62) is the one property whose value is a **colour**: a `#rrggbb` string, applied as a per-node **multiply**, and it cascades to the target's parts the way `alpha` does. Its rest value is `#ffffff` — white, i.e. no tint — so a tween with no `from` starts untinted. A tween between two colours interpolates **per channel in sRGB**, because the compiler expands one authored `tint` into three numeric channels; you never see those unless you read a compiled document, and writing them directly is legal but not the intended surface. It is a multiply over the art that is there, **not** art direction: recolouring a rig's roles is `an.styles.StylePack`, which decides the colours before they are drawn. A tint to `#ff0000` makes everything red-tinted, including the eyes and the mouth.
  - **`alpha` is the entrance/exit primitive** — it cascades, so a tween on the character root fades every part of it. `{kind: tween, target: charlie, property: alpha, to: 0.0, duration: 1.0}`.
  - **A `tween` with no `from` starts from the property's *rest* value**, which is `1.0` for `scale_x` / `scale_y` / `alpha` and `0.0` for the rest — not `0.0` for everything.
  - **A property outside the transform vocabulary names a SWAP SET** (an#87): `{kind: set, target: gale/left_hand, property: hands, value: fist, at: 1.0}` swaps that node's art to the `fist` key of the character's declared `hands` asset set, holding until the next action (set or tween) on the same target/property, or the shot end. The set and key must be **declared in the descriptor's `asset_sets`** — an undeclared name or key is refused at compile with the declared ones listed. `viseme` is just such a set (lip-sync drives it automatically); a procedural (descriptor-less) rig supports only `viseme` on its mouth. Swap channels are always step-interpolated — an authored easing on a swap tween is forced to `step` with a warning.
- **`Shot.narration` is declared by the IR and NOT implemented** — a shot carrying it raises. For a narrator, use a dialogue line whose speaker is not an entity in the shot: it gets audio and no lip-sync, and warns to say so.
- **Transitions and sound** (an#163, `an.assemble`) — two optional keys in ` ```yaml shot ` and one in ` ```yaml meta `:
  - `transition: {kind: cut|fade|dissolve, duration: 0.5, color: "#000000"}` says how the shot is **entered**. Omitted = a hard cut. `fade` dips through `color` — half its duration out of the previous shot, half into this one (on the first shot, a fade up over the whole duration) — and **holds** the film's length. `dissolve` overlaps the two shots by `duration`, so the film is that much **shorter** than the sum of its shots; both play in full, each keeps its dialogue on its own frames, and both shots' audio is heard in the overlap (validate warns about a line inside one). Not on the first shot. A shot must be long enough to hold its own transition and the next shot's (validate error; render refuses before any browser launches). Transitions are composed on the frames (exact integer blends) and the film muxed once; `an preview` does not show them.
  - `sounds: [{sound: <key>, at, duration, gain_db, loop, fade_in, fade_out, duck_db}]` — cues from the project's **`sounds` store**. In a shot they are SHOT-local (they move with the shot); in `meta` they are FILM time. A music bed is `{sound: bed, loop: true, duck_db: -12, fade_in: 1, fade_out: 1}`: `loop` without `duration` runs to the end of the film (meta) or the shot; `duck_db` drops it under every dialogue line with a linear ramp (`duck_attack` before the line, `duck_release` after; lines closer than both stay ducked). The mix is rebuilt from sources and the picture is copied untouched.
  - **Sounds enter through the store, with provenance**: `an.sounds.add_sound(mall["sounds"], key, wav_bytes, source=AssetSource(...))` (WAV only; convert with ffmpeg). The licence is attached to the bytes' sha256 and `an credits` lists it; an unknown licence is reported UNVERIFIED. **Ship no third-party audio you have not read the licence of** — `an.sounds.synth_tone` / `synth_hit` / `synth_bed` make deterministic stand-ins offline; add one with `source=an.sounds.SYNTH_SOURCE` (CC0, generated locally), as in the recipe below. A scene with neither key renders byte-identically to before. Not built: wipes/morphs, a closing fade to black, stereo, per-character voice effects (pitch).
- **Voice effects** (an#163, `an.audio.effects`) — a voice document in the `voices` store may carry `effects: {pitch_semitones: 4}` (±12; `0` or absent is no effect; an unknown key or out-of-range value is a validate error and raises at render). The line's `voice_ref` names the document. The shift runs on the synthesized audio BEFORE lip-sync (visemes are aligned on the audio the viewer hears) and keeps the duration, so word timings hold. The chain is stock ffmpeg (`asetrate` + `atempo`, bit-exact WAV out): deterministic, but a crude shifter; `rubberband` is deliberately not used because its output varies by build and the audio is content-hash cached. The audio key gains the effect only when one is declared, so a project without effects keeps every key; the raw TTS stays cached under its own key, so changing the pitch never re-calls the provider. Needs the `ffmpeg` binary, and a missing one is an error, never silently unshifted speech.
- ` ```dialogue ` — `speaker [emotion]: text` per line. Emotion is an expression preset — `neutral | happy | sad | angry | surprised | afraid | disgusted | thinking | skeptical | amused` (an unknown name is a validate ERROR). It is sugar for an `expression` over the line: the face solver moves the brows (height and angle), picks the eyelid key, and selects the mouth's `viseme@<form>` set for the line's visemes.

## A project from nothing

Everything a render needs, created from Python or the CLI — no file from the `an` repo required. Run the recipe, write the scene, validate, render.

### Units and staging

- **Stage coordinates are scene pixels from the frame CENTRE, y DOWN.** Scene pixels are output pixels: nothing rescales with `meta.resolution`, so the same numbers fill more of a 1280x720 frame than of a 1920x1080 one. Path `points`, plane `offset`/`size`, `stage.at`, a `hop`'s `height` and every `x`/`y` tween use them. Text `size` is the exception: a fraction of frame height.
- **An `an character new --offline` character is about 265 px tall at `stage.scale: 1`**: its drawn art runs from about 170 px above its origin to 95 px below. At scale `s` placed at `stage.at: [x, y]`, its top is at `y − 170·s`. The top edge of the frame is at `−height/2`, so keep `y − 170·s − hop_height` above it — divided by the camera's zoom when one runs (`push_in` ends at 1.25x about the frame centre, `zoom_in` at 1.5x). At 1280x720 a two-shot is `scale` 1.2-1.5 at `x = ±230`; a single close is `scale` 1.8-2.0 at `y` 60-120 (lower is closer to the bottom edge).
- `hop` `height`, `shake` `amplitude`, `slide_in` `distance` are scene pixels, not multiplied by the entity's `stage.scale`.

### Dialogue timing

- A shot's lines play **back to back from the shot start**; the audio pipeline sets each line's start and duration when it synthesizes. `scene.md` has no start offset or pause per line yet (an#187) — put a pause between lines by splitting them across shots, or leave the silence at the shot's end.
- The offline voice is **silent** and lasts 0.05 s + 0.06 s per non-space character, at least 0.4 s (`an.audio.offline_tts.estimate_speech_duration(text)`), so you can size shots before rendering. A real voice (`--tts elevenlabs`, or `--tts mac_say` — a free local voice on macOS) is usually a little slower.
- The shot's audio stops at the shot end. `an validate` warns when a line would run past it: from the estimate before any synthesis, from the real timing after a render.
- There is no narrator track (`Shot.narration` raises). A narrator is a dialogue line whose speaker is not an entity in the shot — audio, no lip-sync, and a warning saying so. A shot with no dialogue is silent unless a `sounds` cue plays.

### The assets: one recipe

Text, paths, plane environments and StylePacks are pydantic documents; `model_dump(mode="json")` into the project's store writes the file the compiler reads (`assets/props/<key>/prop.json`, `assets/environments/<key>/meta.json`, `assets/styles/<key>.json`). The dump holds only what you set, so it always loads back.

<!-- skill-test: recipe -->
```python
from pathlib import Path

from an.characters import new_character
from an.environments import EnvironmentDescriptor, Plane, PlaneArt
from an.paths import PathDescriptor
from an.project import init
from an.sounds import SYNTH_SOURCE, add_sound, synth_bed
from an.stores import build_project_mall
from an.styles import StylePack
from an.text import TextDescriptor

root = init(Path("my_film"))  # = `an init my_film`
mall = build_project_mall(root)

for name in ("stan", "kyle"):  # = `an character new <name> --offline --out-dir my_film/assets/characters`
    new_character(root / "assets" / "characters", name=name, use_dicebear=False)

# A title card: one fill plane with no `size` covers the canvas; depth 0 never pans.
mall["environments"]["card"] = EnvironmentDescriptor(
    name="card", planes=[Plane(name="bg", art=PlaneArt(kind="fill", color="#040404"), depth=0.0)]
).model_dump(mode="json")

# A map: sea, land, and a WHITE territory, so a `tint` tween can colour it (tint multiplies).
mall["environments"]["map"] = EnvironmentDescriptor(
    name="map",
    planes=[
        Plane(name="sea", art=PlaneArt(kind="fill", color="#a7b1b9"), depth=0.0),
        # depth 1.0 = the character plane: pans exactly with props (the route, labels)
        Plane(name="land", art=PlaneArt(kind="fill", color="#cda469"), depth=1.0, size=(1100, 420)),
        Plane(name="west", art=PlaneArt(kind="fill", color="#ffffff"), depth=1.0,
              offset=(-250, 0), size=(400, 300)),
    ],
).model_dump(mode="json")

# Words: an overlay title (the camera never moves it) and a reusable world label.
mall["props"]["date"] = TextDescriptor(
    name="date", text="OCTOBER 1ST, 2026", layer="overlay", unit="line",
    size=0.1, color="#ffffff",
).model_dump(mode="json")
mall["props"]["label"] = TextDescriptor(
    name="label", text="label", size=0.05, color="#1a1a1a"
).model_dump(mode="json")

# A route arrow that starts hidden (trim_end 0), drawn on by a trim_end tween.
mall["props"]["route"] = PathDescriptor(
    name="route", points=[(-300, 60), (0, -40), (260, 30)], arrowhead=True,
    trim_end=0.0, color="#ba5f31", width=10,
).model_dump(mode="json")

# Art direction, named by `style_pack:` in the meta block.
mall["styles"]["south_park"] = StylePack(
    name="south_park", roles={"sky": "#c0c6c7", "ground": "#987a43"}
).model_dump(mode="json")

# A sound: WAV bytes plus where they came from. synth_bed is an honest stand-in.
add_sound(mall["sounds"], "bed", synth_bed(12.0), source=SYNTH_SOURCE)
```

Every document refuses what it cannot draw: a `TextDescriptor` needs `name` and `text`, an `anchor` is overlay-only, a `PathDescriptor` refuses `gap`/`dash_offset` without `dash` and `head_length` without `arrowhead`, a `Plane` refuses an unknown key.

### A minimal complete `scene.md`

Three shots — a date card, a map with a route drawn on and a territory changing colour, and a two-shot with dialogue — using the recipe's assets. A property holds its REST value until its first action, so anything that should start somewhere else (the title's `alpha`, the territory's first colour) gets a `set` at 0. A shot is `## Shot <id> (cutout)` followed by its fenced blocks; entities are `{kind, id, store, ref}` plus optional `stage`/`overrides`; a text unit is addressed `<id>/line_0` (or `word_N`, `glyph_N`) and a plane `<environment id>/<plane name>`.

<!-- skill-test: scene -->
````markdown
# The Vending Machine

```yaml meta
title: The Vending Machine
duration: 12.0
fps: 24
resolution: {width: 1280, height: 720}
default_renderer: cutout
default_easing: linear
style_pack: south_park
sounds:
  - {sound: bed, loop: true, gain_db: -8, duck_db: -12, fade_in: 1.0, fade_out: 1.0}
```

## Shot card (cutout)

```yaml shot
duration: 2.0
camera: {move: hold}
```

```yaml entities
- {kind: environment, id: bg, store: environments, ref: card}
- {kind: prop, id: date, store: props, ref: date}
```

```yaml actions
- {kind: set, target: date/line_0, property: alpha, value: 0.0, at: 0.0}
- {kind: tween, target: date/line_0, property: alpha, from: 0.0, to: 1.0, duration: 0.5, start: 0.2}
```

## Shot map (cutout)

```yaml shot
duration: 3.0
camera: {move: pan_right}
```

```yaml entities
- {kind: environment, id: map, store: environments, ref: map}
- {kind: prop, id: route, store: props, ref: route}
- {kind: prop, id: west_label, store: props, ref: label, overrides: {text: West}, stage: {at: [-250, -110]}}
```

```yaml actions
- {kind: tween, target: route, property: trim_end, to: 1.0, duration: 1.5, start: 0.5}
- {kind: set, target: map/west, property: tint, value: "#ba5f31", at: 0.0}
- {kind: tween, target: map/west, property: tint, to: "#3a5fa0", duration: 1.0, start: 1.5}
```

## Shot talk (cutout)

```yaml shot
duration: 7.0
camera: {move: hold}
```

```yaml entities
- {kind: environment, id: set, store: environments, ref: indoor}
- {kind: character, id: stan, store: characters, ref: stan, stage: {at: [-230, 40], scale: 1.4}}
- {kind: character, id: kyle, store: characters, ref: kyle, stage: {at: [230, 40], scale: 1.4}}
```

```yaml actions
- {kind: tween, target: stan/head, property: rotation, to: 0.15, duration: 0.2, start: 0.3}
- {kind: tween, target: stan/head, property: rotation, to: 0.0, duration: 0.2, start: 0.8}
- {kind: play, target: kyle, animation: hop, args: {height: 30}, start: 4.0}
```

```dialogue
stan: Dude, the school replaced the cafeteria.
kyle [happy]: Then we're rich! I have a quarter!
```
````

Then `an validate my_film` and `an render my_film --strict-assets`. `tests/test_skill_recipe.py` in the `an` repo runs this recipe and this scene, so they stay true.

## When the user wants to make a video right now

1. **Use the `an-spec` skill** to interview them and produce a draft `scene.md` (characters, dialogue, art style, voice intent, pacing, camera).
2. **Run `an init <dir>`** in their target directory (creates the project tree).
3. **Make the assets and write `scene.md`** — *A project from nothing* above is the whole kit: the recipe for characters, text, paths, planes, StylePacks and sounds, and a complete scene to start from. A character with no descriptor renders as a placeholder rig (with a warning); `--strict-assets` makes that an error.
4. **Run `an validate <dir>`** and surface any findings (warnings about unresolved voice/character refs are fine if assets aren't promoted yet).
5. **Run `an render <dir>`** for the offline default, or `an render <dir> --tts elevenlabs --lipsync whisper` for real speech with word-aligned visemes (best quality without external binaries).
6. For iterative tweaks, prefer **`an iterate <dir> "<plain-English change>"`** over hand-editing scene.md — it's the spec's signature loop. Cache invalidation is automatic; the next `an render` regenerates only the affected shots.

**"In the style of X"** (South Park, OverSimplified, Kurzgesagt, Gilliam, Reiniger, Norstein): use the **`an-style`** skill — a style spec per look (live settings, measured targets, and what `an` cannot do yet), and `an.verify.style` (`StyleLintVerifier`) to measure the render against the targets.

## When the user wants controlled test footage (impacts, timing ground truth)

`an.impacts` generates structured clips of a stick or ball striking a surface, or striking the air (a braked stroke with no contact), on a known tempo grid — with a sidecar keeping the **intended** grid time (`t_grid`), the **executed** impact time (`t_impact`, continuous seconds) and **what each frame shows** (exposure interval, sample instants, keypoints) apart. Use it when someone wants to test whether events can be recovered beyond the frame rate; do not hand-author such scenes.

- `an impacts clip OUT --kind air --fps 30 --exposure 0.5 --jitter-sd 0.012 [--tempo 0:90,16:120] [--no-render]`; `an impacts clip-set OUT --fps 24,30,60` for a benchmark set with `index.json`.
- Python: `write_impact_clip(ImpactClipSpec(...), out_dir, render=True)`; `plan_impact_clip(spec)` for the events/stroke/frames without I/O. `render=False` needs no browser.
- The camera is `an.frame_clock.FrameClock` (fps, exposure, samples, jitter_sd = when frames are taken, report_noise_sd = noise on the reported timestamp, phase, timestamps), reaching the renderer as `RenderContext.frame_samples` — usable for motion blur on any render. With an open shutter a frame's keypoints are the AVERAGE over its exposure; `keypoints_mid` is the mid-exposure position.
- Schema: the `an/impacts/truth.py` module docstring.
- Write rendered sets OUTSIDE any repo (e.g. `~/.local/share/<project>/synthetic/`); they are data.

## When to consult docs

- **Start here** (in the `an` repo, when changing `an` itself): `misc/docs/architecture_as_built.md` — module map, the 3 control flows (render / iterate / validate), key invariants, content-hash caching strategy.
- For IR field semantics: `an/ir/schema.py` is the SSOT.
- For composition flatten semantics: `an/ir/compose.py` (has doctests).
- For audio pipeline: `an/audio/pipeline.py`.
- For cutout backend internals: `an/adapters/cutout/{compile,render,channel,clip,timeline}.py`.
- For the iterate loop's prompt design: `an/iterate.py` (the system prompt + IterateResponse schema).
- For backend research and design rationale (NOT current state): the seven reports in `misc/docs/report*.md`. Read the matching one before designing or extending a subsystem.

## What to write to `.an/decisions.jsonl`

Whenever you make a non-trivial design decision the user hasn't blessed (asset choice, default style, durations, voice pick), append a decision entry via `mall["decisions"].append(kind=..., body=...)` and surface it in your next reply.

## What to never do

- Never write directly to `ir/scene.json` — edit `scene.md` and run `sync`, OR use `mall["scenes"]["main"] = scene_ir` (which writes both files and equalizes mtimes).
- Never inline large assets into the IR; reference them by store key via `AssetRef`.
- Never claim a render produced something it didn't — `an render` returns the mp4 path; if it fails, surface the actual error from the renderer.
- Never bypass the audio pipeline by manually constructing viseme tracks unless the user is debugging — `produce_audio_for_scene` runs automatically inside `render` when needed.
