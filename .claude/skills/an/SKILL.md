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

- `an init <dir>` — create a fresh project on disk: `scene.md` (a `yaml meta` block only — no shots yet), `ir/scene.json`, and the store folders under `assets/`. Defaults: **1920x1080, 30 fps**; change `resolution:`/`fps:` in the meta block (1280x720 renders roughly twice as fast). **`an init --id <id>`** creates it at the default location for an agent-made video: `~/.local/share/cutan/projects/<id>/` (the cut-out genre's root, beside the library its characters come from; `--package an` for a genre-neutral one). Use it whenever the user names no directory — never put a project in a session or agent-work folder, or in a repository.
- `an validate <dir>` — schema + semantic validation, including the asset-library pins: a scene `library:` that disagrees with `assets.lock.json` is a warning (fix the scene line it names), and a checked-out asset edited since is an `info` (a fork).
- `an sync <dir>` — reconcile `scene.md` ↔ `ir/scene.json` (newer file wins).
- `an render <dir> [--tts NAME] [--lipsync NAME] [--parallel auto|N] [--strict-assets] [--step-hz N] [--force-render] [--no-cache] [--cache-frames]` — full pipeline: validate → audio → render per shot → ffmpeg-concat (or, with transitions or sounds, `an.assemble`) → `output/main.mp4`. TTS and lip-sync providers are pluggable: `--tts elevenlabs` (needs `ELEVEN_API_KEY`) for real speech, `--lipsync whisper` (needs `faster-whisper`) for word-aligned visemes, `--lipsync rhubarb` (needs the rhubarb binary) for full phoneme alignment. Whatever the provider, the compiler runs the co-articulation passes over its raw track before emitting the mouth channel (an#97: duplicates merged, sub-frame tongue shapes dropped, every shape 2/24 s ahead of its sound, a beat to close before rest, and a 0.14 s minimum hold that VOTES — the shape with the largest in-window span × dominance wins and shows from the window start — instead of dropping late arrivals). Rhubarb's recognizer follows the language: `an render --language en` (the default) uses `pocketSphinx` with the transcript, any other tag `phonetic` without one; `make_lipsync("rhubarb", language=…)` in Python (an#96). Defaults are offline. Switching providers auto-re-synthesizes the affected lines. `--parallel auto` runs each shot in its own thread (Phase 11c; ~N× wall-time speedup on N-shot scenes; capped at min(shots, cpu, 4)). `--strict-assets` refuses to draw a **stand-in** for an asset the project's stores don't supply — the placeholder rig for a missing character descriptor, the default backdrop for an unknown environment ref. Without it you get a warning and a plausible render of a *different* picture (an#33); use it whenever the output is going to be measured or compared. `--step-hz N` (an#89) renders authored tweens **stepped** — pose updates N times a second on a shot-wide grid (every tween in a shot shares it; a tween's own start and end are pose changes too, so an off-grid start or end changes pose on that frame as well), so at 30 fps `15` is "on twos" and `10` "on threes" (the Spider-Verse look: characters on twos, camera and simulation on ones); it overrides the scene's `meta.step_hz` for this render, a shot's own `step_hz` still wins, and the camera, blinks, `play` clips and swap channels are never stepped. Default: smooth. **`an render` rewrites `scene.md`** when the scene has dialogue: the audio pipeline stamps each line's timing and writes the scene back through the store, which regenerates `scene.md` from the IR — prose and YAML comments are dropped, flow mappings (`{kind: set, ...}`) become block style, and defaults (`author`, `resolution`, `default_renderer`) are written out. Re-read the file after a render before editing it, keep notes elsewhere, or edit through `mall["scenes"]["main"]`. **`an render` is incremental** (ADR 0004): a shot whose inputs are unchanged since an earlier render — its compiled document, the bytes of every asset in the project, its dialogue audio, the runtime, every render setting, and this machine's browser/Playwright/ffmpeg — is reused from the project's shot cache (`artifacts/shot_cache/`) instead of rendered, and the CLI prints which shots were `rendered` and which `reused`. Editing one shot re-renders that shot; editing any asset re-renders every shot (until reads are recorded per shot); a film with transitions or a sound layer re-renders its shots (their frames are not cached by default; `--cache-frames` caches them, at hundreds of MB per 1080p shot). The summary line says why each rendered shot was not reused. `--force-render` renders every shot anyway; `--no-cache` neither reads nor writes the cache. In Python: `render_project(dir, incremental=ShotCache())` and read `cache.report` (`from an.build import ShotCache`). The shot id is never the key, so renaming a shot reuses it.
- `an iterate <dir> "<instruction>"` — free-text edit. Sends the current scene + instruction to Claude (Opus 4.7 + adaptive thinking), parses a structured patch list, validates against the schema, and persists the new scene to disk; the next `an render` re-renders exactly the shots whose content changed (found by digest, not by the model's `affected_shots` list, which is only reported). Needs `ANTHROPIC_API_KEY`. Pass `--no-apply-changes` for a dry run.
- `an preview <dir> [--shot ID] [--no-browser]` — live preview in a browser. Spins up an HTTP server, compiles the chosen shot (default: first), polls `scene.md` / `ir/scene.json` for changes, and the browser auto-reloads via a 500 ms `Last-Modified` poll. Lossy: visuals only, no audio. Honours the scene's / shot's `step_hz` (no flag of its own). Blocks until Ctrl-C. Use it for quick iteration on layout / blocking before `an render`.
- `an character new <name> [--out-dir DIR] [--seed S] [--style adventurer] [--offline] [--mouth-variants happy,sad] [--palette skin=#..,hair=#..,clothing=#..,leg=#..,accessory=#..] [--build regular|squat|tall|stick] [--head-scale 1.3] [--hat none|cap|beanie|bowler|bicorne] [--sash] [--no-views]` — create a character at `DIR/<name>`; **`DIR` defaults to `./assets/characters` relative to the CURRENT directory, not to any project** — run it from the project root or pass `--out-dir <project>/assets/characters` (every `an character` subcommand that names a character takes `--out-dir` the same way). It writes with parts/ (the body, brows, and the sclera/pupil/lid eye stack), the 9-shape mouth set (plus a `viseme@happy` and `viseme@sad` variant set by default — the mouth forms the expression presets prefer; `an character mouths --variants angry` adds more), and `character.json`. By default fetches a DiceBear avatar; `--offline` uses a deterministic geometric fallback (no network). **For production scenes with dialogue, prefer `--offline` or hand-rig a character following the Pose Animator convention (see `examples/promote_demo/`).** **Give every character its own look**: `--palette` (StylePack role names; unset roles keep the seed's colours), `--build` (`squat` = round body on short legs, `stick` = small blocky body on stick limbs, `tall`), `--head-scale` (head and whole face together), `--hat` (offline head only) and `--sash`, in the `accessory` colour. An `--offline` character also gets its **turnaround** — `front`, `three_quarter`, `side`, `back` (see *Turning and facing*); `--no-views` leaves it out. Defaults reproduce the old character exactly (views only ADD parts and descriptor keys). DiceBear avatars have eyes/brows/mouth baked into the head SVG, so the cutout adapter suppresses the overlay mouth + viseme channel for them — audio plays but the mouth doesn't move. Treat DiceBear as a bootstrap path only.
- `an character add-views <name>` — give an older `--offline` character its turnaround (an#197); refused for DiceBear or hand-drawn heads.
- `an character add-gaze <name>` — give an older character the eye stack (sclera/pupil/lid) so gaze and ambient saccades move its pupils (new characters get it by default); `an character mouths <name> [--variants happy,sad]` — regenerate the 9-shape default mouth set and its `viseme@<form>` variants (declared in the descriptor) (`mouth_a` … `mouth_x`). Variants are ADDED: sets already declared stay declared, so `--variants angry` on a new character gives it `happy`, `sad` and `angry`. It also redraws the neutral set, so run it before hand-editing mouth art, not after. **When `an validate`/`an render` warns `<name> declares no 'viseme@angry' set`**, a dialogue `[angry]` (or an `expression`) wants a mouth form the character lacks: the face still works, the mouth just uses the neutral shapes; `an character mouths <name> --variants angry` fixes it.
- `an character validate <name>` — check parts, mouth set, pivots, descriptor.
- `an character silhouette <name> [--other <name2>]` — render a black silhouette PNG; with `--other`, also computes IoU between the two silhouettes (Disney silhouette test).
- `an character preview <name> [--open-browser]` — write `preview.html` cycling all 9 visemes with breath/head-tilt animation.
- `an character record <name> [--duration 8] [--width 640] [--height 480]` — record `preview.html` to mp4 via Playwright + ffmpeg. Produces `<character_dir>/preview.mp4` (or `--output PATH`). Real video file showing the new SVG art animating.
- `an check` — diagnose system deps (ffmpeg, node, rhubarb, playwright, elevenlabs, manim).

Python surface (everything in `an.__all__`):

- **Genres load explicitly** (an#241): the cut-out genre — `play`, `expression`, the `character` entity kind and the `[emotion]` dialogue sugar — is registered by `an.load(project)` and the `an` CLI, never by `import an`. A script that parses or builds scenes WITHOUT `an.load` (e.g. `SceneIR.model_validate(...)`, `markdown_to_ir(...)`, `compile_shot(...)` on its own) calls `an.genres.load()` first; otherwise a `kind: play` stays an unregistered `ExtensionAction` and validate/flatten/compile refuse it with an error naming the genre.

- Scene IR: `SceneIR`, `Shot`, `Dialogue`, `AssetRef`, `Camera`, `Resolution`, `Meta`.
- Composition: `sequence`, `parallel`, `stagger`, `delay`, `loop`, `tween`, `set_`, `play`, `flatten`. `stagger(0.2, a, b, c)` starts each action 0.2 s after the previous one starts (a crowd entering one by one; sugar over `parallel` + `delay`, so the scene document holds only those). **`play` resolves against the target character's descriptor `animations`** (an#7): `play("maya", "idle_breath")` compiles the seeded breath — three sine tracks, torso bob (±2 view-box px), head tilt (±0.5°, a quarter cycle behind) and a slower weight shift (±1.5 px), all on the animation's **6 s** cycle — into channels around the rig's rest pose; because `idle_breath` loops, a play with no `duration` runs to the **shot end** (a bounded loop is `duration=…`). `play("maya", "blink")` swaps the eyelids through the same swap path as compiled blinks. `loop=None` uses the animation's own `loop`. Resolution is `an.characters.play`, shared by `an validate` and the compiler, so both refuse the same plays with the same words: an undeclared name (the declared ones listed), a bone with no slot of its own, an unknown bone property, a frame naming art that is not on disk, a face slot suppressed by `face_overlay: false`.
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

**From `scene.md`, play a preset by NAME** (an#166): `{kind: play, target: charlie, animation: hop, args: {height: 30}, start: 1.0}`. A `play` whose name the character's descriptor does not declare — or any `play` on an entity with no descriptor (the procedural placeholder, a prop) — falls back to `an.motion.PRESETS`. **A descriptor animation of the same name wins.** The compiler builds the preset at the pose the moved node HAS at the play's start (an#212) — its built rest (stage placement, layout) overridden by the sets and tweens before it — so no `rest=` is ever needed (a `shake` on the right-hand character of two stays centred on its `x = 110`, and a `hop` after a move hops from where the move left it; the entrances `slide_in` and `pop_in` land on the built pose, their home, wherever they start). `args` are the preset's keyword parameters (`height`, `amplitude`, `cycles`, `part`, `angle`, …; never `rest`, `parts` or `target`); `duration` stretches the whole move to that length, `speed` divides it (not both); `loop: true` is refused (a preset is a one-shot — use its own `cycles`/`count`/`steps`). `an validate` and the compiler give the same verdict (`an.characters.play.play_problems`): an unknown name lists both the descriptor's animations and the presets; an unknown parameter lists the accepted ones; a node the rig does not build (`point` on `charlie/arm_r`) lists the built ones. In a `sequence`, a preset play with no `duration` occupies the preset's own length divided by `speed`, so `sequence(play("maya", "hop"), play("maya", "nod"))` runs the nod after the hop (or place each with `start:`); `an validate` warns when one runs past the shot end. For `point`, the target is the arm node (`charlie/right_arm` on the placeholder, whose limbs are rects hung from their joint, so a rotation pivots at the shoulder like a descriptor rig's bone — an#173).

| Preset | Moves | Target |
|---|---|---|
| `pop_in` | `scale_x`/`scale_y` 0 → rest, overshooting (`OVERSHOOT` Bézier) | entity |
| `hop` | `y` up by `height` and back | entity |
| `shake` | `x` side to side `cycles` times | entity |
| `nod` | `rotation` of `<entity>/<part>` (`part="head"`), `count` dips | entity (+ part) |
| `point` | `rotation` of an arm out, `hold`, back | the ARM node: `charlie/right_arm` (procedural), `carl/arm_l` / `carl/arm_r` (descriptor). **Sign:** front view — `arm_l` (viewer's left) points out with a POSITIVE `angle` (`1.7`), `arm_r` (viewer's right) with a NEGATIVE one (`-1.7`); a wave alternates `-2.1`/`-1.5` on `arm_r`. Right-facing profile (`view: side`) — the far arm is hidden, the near arm is `arm_r` and points AHEAD with a negative angle (`-1.7`); facing left (negative entity `scale_x`) it is still `arm_r`, still negative, mirrored with the character. See *Addressing a character's parts* |
| `slide_in` / `slide_out` | `x` from / to `distance` px off `from_side`/`to_side` | entity |
| `squash_stretch` | `scale_x`/`scale_y` squash, stretch, settle | entity |
| `waddle` | per step: `rotation` rock ± `angle` and `y` bob by `lift`; `travel` moves `x`; `angle=0` is a plain bob | entity |
| `turn` | `scale_x` squashes to 0, the `view` swaps at that midpoint, `scale_x` opens again (negative for `direction: left`); `to` = `front` / `three_quarter` / `side` / `back`, `from_direction` = which way it faced before (played by name, inferred from the timeline when omitted) | entity (needs a `view` set: *Turning and facing*) |
| `walk` (an#214) | the body travels on `x` to `to_x` (absolute) or by `distance` (signed; `direction: left/right` sets the sign) FROM WHERE IT IS at the play's start, bobbing `bob` px once per step; legs: in a `side`/`three_quarter` view each swings `stride` rad about the hip (around the profile's splay), in opposition; in any other view the stepping leg rises `lift` px; arms swing `arm_swing` against the legs; no legs (the procedural placeholder, a blob) → the body rocks `rock` rad instead. **`gait`** (an#220): `legs` (the above), `hem` — the leg slots are the two halves of a robe's hem: facing the camera they TILT in turn by `hem_tilt` rad (0.24) about the hip while the body sways `rock` and bobs (in profile they swing like legs); `rock` — no leg moves. Unset: the descriptor's `gait`, else `legs`/`rock` by whether the rig builds legs — so a robe figure declares `"gait": "hem"` in its `character.json` once. `view` is read off the timeline (the last `turn`/`set` of `view`) unless given, else the descriptor's **`rest_view`** (an#220: a character carved in profile declares `"rest_view": "side"` and walks as a profile with nothing passed); `legs`/`arms` default to the first built pair of `leg_l`/`leg_r` (rig contract) or `left_leg`/`right_leg` (placeholder). Length = `steps × step_s`: `steps` given, else `|distance| / step_length`, else 6 for a `to_x` walk (a play's length must be known before it is placed — give `steps` for a pace). It does NOT turn the character: `turn` first, then walk (a profile faces right; mirror with `direction: left` on the turn to walk left) | entity (+ its limbs) |

All parameters are keyword-only with module-constant defaults (`DFLT_*`); `an.motion.PRESETS` is the name → function table. Rules that bite:

- **In Python, values are absolute, so a preset needs the node's rest** (a `play` from `scene.md` reads it for you). `rest=None` is the identity pose — right for rotations, and for `y`/scale of an entity with no `stage` placement. An entity's `x` is laid out (`-110`/`110` for two characters), so a move on `x` in a multi-character shot, or anything on a staged entity, takes `rest=rest_pose(shot, "charlie", mall=mall)`, which reads the value off the compiler's own scene builder. For `nod`/`point`, pass the PART's rest (`rest_pose(shot, "charlie/head")`).
- **An unknown target is an error** (an#193): `an validate` resolves every `set`/`tween` target against the node tree the compiler builds and names the real path (`'ned/left_brow' is not a node of the built scene; did you mean 'ned/head/left_brow'?`), and the compiler raises the same message before any browser starts; `rest_pose` raises for it up front. The rigs are flat and name their arms differently — see *Addressing a character's parts*.
- **`scene.md` drops composition trees.** A preset composed in Python survives a `scene.md` edit as `as_leaves(preset, start=t)` — top-level tweens with `start:`, which round-trip; a `play` of its name is simpler still.
- **Presets write their own easings**, so a scene `default_easing` does not reach them.
- **Each preset ends with a `set` pinning every property it moved at its end value.** Frames sample `i / fps` and the runtime holds the last pose applied, so a tween ending between frames would leave the property off by part of its last segment (under `step_hz`, by all of it). The `set` holds until the next tween on that property.
- Presets are ordinary tweens, so `step_hz` steps them — the jerky South Park look is `sequence(...)` plus `step_hz`. A segment shorter than one step (a default `shake` has 57 ms segments) mostly vanishes under `step_hz` 10–15; lengthen `duration` or lower `cycles` for a stepped shot.

## Turning and facing

An `an character new --offline` character carries a **turnaround** (an#197): a `view` swap set with keys `front` (its rest), `three_quarter`, `side` and `back`, drawn on the head and torso, plus a **pose per view** in the descriptor's `swap_poses`: the back hides the whole face, the profile hides the far eye and arm and slides the near eye and the mouth to the edge, the three-quarter shifts the face toward the facing side. `side` is drawn facing the **viewer's right**; a negative `scale_x` on the character root mirrors it to face left.

- **A turn:** `{kind: play, target: ned, animation: turn, args: {to: back}, start: 1.2}` — `scale_x` squashes through 0 and the view swaps at the edge-on midpoint (0.3 s by default; `duration` stretches it). Face a profile left with `args: {to: side, direction: left}`. **A turn played by name opens from where the timeline left the character** (an#203): the compiler reads the latest earlier `scale_x` on the entity (an earlier turn, or your own set/tween) and fills in `from_direction`, so a chain needs none by hand:

  ```yaml
  # front -> side (facing left) -> back, one character, one shot
  - {kind: play, target: ned, animation: turn, args: {to: side, direction: left}, start: 1.0}
  - {kind: play, target: ned, animation: turn, args: {to: back}, start: 2.5}
  - {kind: play, target: ned, animation: turn, args: {to: front}, start: 4.0}
  ```

  An explicit `from_direction` is kept, and `an validate` warns when it contradicts the timeline (the character would flip to the other side before turning). In Python, `an.motion.turn(...)` builds the tweens straight away and cannot see the timeline: pass `from_direction` there, or append the `PlayAction` instead.
- **A cut to a view** (no animation): `{kind: set, target: ned, property: view, value: side, at: 0.0}` — on the CHARACTER itself, which the compiler fans out to every slot the set draws on and poses the face; add `{kind: set, target: ned, property: scale_x, value: -1.4, at: 0.0}` (minus the stage scale) to face left.
- **A view holds for its shot only.** Every shot is compiled on its own (by design), so a character that turned its back at the end of one shot needs the `set … view back` (and any negative `scale_x`) again at `at: 0.0` in the next. `an validate` warns when a character ends a shot turned (a view other than `front`, or facing left) and the very next shot has it without setting its view (or its `scale_x`, for the facing) at 0, and gives the line; setting them there — to `front` and a positive `scale_x` for a deliberate reset — silences it.
- **Legs in profile:** the side view keeps both legs — the near one (`leg_r`) forward and drawn over the far one (`leg_l`), overlapping at the hip, feet apart — so a walk in profile has two legs to alternate (rotate `leg_l`/`leg_r` about the hip; the view's own splay is the rest your tweens override while they run). A character given its views before an#203 keeps the old one-leg profile until `an character add-views <name>` is run again (it rewrites the poses; the art is unchanged).
- **Looking at someone:** in Python, `an.motion.face_toward(shot, "ned", "carl", view="side", mall=mall)` returns the `turn` whose `direction` points at `carl`'s stage position.
- The face keeps working in every view: blinks and gaze run on the visible eye (a posed pupil still follows `gaze_x`), and lip-sync runs on the mouth in `front`, `three_quarter` and `side`; under `back` the mouth is hidden with the rest of the face, so a line said with the back turned is heard, not seen.
- **Never hide a face with `alpha` sets on `ned/head/left_eye`, `…/left_pupil`, `…/mouth` …** — that is what the view's pose is for, and a hand-set alpha on a face node overrides the view (authored wins) until the shot ends.
- **A face drawn differently in a view gets its own set, not a hide** (an#220): declare `eyelid@side` (`{OPEN, CLOSED}` → the profile's eye attachments, carried by the eye slots) and `viseme@side` (the profile's mouth shapes, on the mouth slot) and whenever `side` is in force the lids (blinks, expressions, a played `blink`) and the mouth (lines that start in it, and its rest between them) draw from them — the same for any view key (`eyelid@back` …). A view set lacking a key a line uses falls back to the plain set with a warning. A profile head carved with its eye and mouth baked in: carve them out as these per-view parts instead of hiding the face slots in `swap_poses` — **`an validate` warns when a line is spoken while the speaker's view hides its mouth** (alpha 0).
- **Characters made before an#202 (the turnaround) need `an character add-views <name>`** before any `view` set or `turn`; validate and compile both say so. A DiceBear or hand-drawn head cannot be turned by the factory; `an character contract` says how an illustrator declares views (`asset_sets.view` + `swap_poses`).

## Markdown surface

`scene.md` supports these fenced blocks:

- ` ```yaml meta ` — title, duration, fps, resolution, default_renderer, notes, and optional `step_hz` (stepped timing for tweens: `0 < step_hz <= fps`; `15` at 30 fps = "on twos") and `default_easing` (an#166): the easing of every authored `tween` that names none — `linear` for a snappy style, `[0.34, 1.56, 0.64, 1.0]` for an overshoot. Precedence: the tween's own `easing` > `default_easing` > the built-in `ease_in_out`. A tween that writes `easing: ease_in_out` keeps it under any default. It reaches authored tweens only — not motion presets, the camera, blinks or `play` clips — and an unknown name is a validate error. Also optional `sounds` (film-time sound cues — see *Transitions and sound* below). And optional `captions` (see *Captions* below).
- ` ```yaml shot ` — duration, camera, options, and optional `step_hz` (overrides the scene's for this shot). `camera: {move: …}` takes any of the nine the compiler implements — `hold`, `push_in`, `pull_out`, `zoom_in`, `zoom_out` and, since an#109, `pan_left`, `pan_right`, `tilt_up`, `tilt_down`. A move is sugar for `camera: {keys: [...]}`, which is the same code path written out; write `keys` for any distance other than the third-of-a-frame a pan travels. An unrecognised move **raises**.
- ` ```yaml entities ` — list of AssetRef-shaped dicts. `kind` ∈ `character | environment | voice` (an#106 retired `style`: it selected nothing, and the word named the renderer; art direction arrives as a StylePack, #112). Environment refs: `park | indoor | night | sunset | default`.
  - **`kind: prop` renders** since an#108. A prop is an `an.props.PropDescriptor` in the `props` store (`assets/props/<ref>/prop.json` beside a `parts/` folder) — same rig machinery as a character, different defaults: one bone, one slot, no face, no blink. Two states are the swap-channel machinery a viseme uses (`asset_sets: {lamp: {off, on}}` plus `set lamp on`). Placement is `stage: {at: [x, y], scale: s}` on the entity. **There is no placeholder rig**: the built-in placeholder is a humanoid, so an unresolvable prop raises rather than drawing a person where the lamp should be. A prop whose `skins` give its slots no attachment draws nothing and is a stand-in (a warning; an error under `--strict-assets`, an#211) — give it `skins: {default: {slots: {body: {body: {path: parts/body.png}}}}}`. **Draw order among characters and props is ENTITY order**: list a prop before a character to put it behind them, after to put it in front. Environment planes are behind both unless `characters_after` names a plane.
  - **A stroked path is a prop too** (an#160): a document with `kind: PathDescriptor` in the props store (`assets/props/<ref>/prop.json`, no `parts/`), placed as an ordinary `kind: prop` entity. It is the map-arrow / route / border / connector / timeline primitive: `points` in scene pixels (a polyline, or `curve: cubic` for chained Béziers, `p0 c1 c2 p1 c1 c2 p2 …`), `color` (`#rrggbb`), `width`, `cap`/`join`, `arrowhead: true` (with optional `head_length`/`head_width` in pixels; default 3.5× and 3× the width), and the initial `trim_start`/`trim_end`. **Draw-on is an ordinary tween**: `{kind: tween, target: <id>, property: trim_end, from: 0, to: 1}` — trim is in fractions of **arc length**, so the tip moves at constant speed along the route whatever its shape; the arrowhead sits on the moving tip, oriented along the leg it is on, and grows in while the visible length is shorter than it. Start a draw-on hidden with `trim_end: 0` in the document; a trim tween with no `from` starts from the document's own value, so `{kind: tween, target: route, property: trim_end, to: 1}` is then a draw-on. Set-but-inert fields raise (`head_length` without `arrowhead`, `samples_per_segment` on a polyline, a zero-length path). The entity's `overrides` are merged over the stored document and validated strictly — reuse one arrow style with per-shot `points`; an unknown key **raises**. `trim_start`/`trim_end` on anything that is not a path **raises** at validate and compile. Not a StylePack role yet (`color` is explicit).
  - **Art direction is a `StylePack`** (an#112): a document in the `styles` store, named by `style_pack:` in `yaml meta`. `roles` maps a role — `skin`, `clothing`, `hair`, `leg`, `pupil`, `accessory`, `sky`, `ground`, `stroke` — to a hex colour; `entities` overrides one character. It recolours what the COMPILER decides **and every `an character new --offline` character**, whose descriptor tags which colour in which part plays which role (`colour_roles`). Hand-drawn art is untagged and keeps its colours, and a DiceBear character's skin and hair stay its own; the compiler says so in one line. Never regex-edit generated `parts/*.svg` to recolour — pass `--palette` at creation or set the role in the pack. A pack may not name `lip`/`mouth_fill`/`teeth`/`tongue`/`eye_sclera`: they are `runtime.js` literals, and declaring one is **refused** rather than ignored. A declared pack that is missing **raises** — art direction the author asked for and did not get is a different picture that renders happily.
  - **Surface treatments are a StylePack's second job** (an#163): `surface: {outline: {width, color, nested}, shadow: {dx, dy, color, alpha, nested}, glow: {color, radius, intensity}}` applies to every character and prop; `entity_surfaces: {<id>: {...}}` overrides it key by key (`{glow: {...}}` adds a glow to one entity, `{outline: false}` removes the outline from one — `false`, not `null`, which an `exclude_none` dump drops); `grain: {amount, seed, tile}` lays one static paper grain over the frame (multiplied, so it only darkens, by at most `amount`). All are compiled into the scene document — copies of each part drawn behind it, a gradient sprite, a seeded texture — so they follow every tween, `play` and lip-sync swap with nothing extra to author, and **they reach every SVG character, tagged or not**. Widths and offsets are in the rig's own pixels (they scale with the character's `stage.scale`); the grain's `tile` is in frame pixels. The outline and shadow go on the top-level pieces only unless `nested: true` (face features); a procedural rig's eyes and mouth never get them. **Fading a treated part darkens it** (the copies are drawn separately, and a group fade would need a filter); the compiler warns when an `alpha` channel FADES one. Hiding or showing one (every key 0 or 1, stepped — a `set alpha 0`, or a view's pose hiding the far arm) is exact and does not warn: the copies share the part's container. An entity `tint` also tints its glow. On SVG art the treatment colour is a multiply (exact for black). The shadow's offset turns with its part. An unknown treatment key or a colour that is not `#rrggbb` **raises**.
  - **Text is a prop too** (an#155) — title cards, labels, word-by-word reveals. A document with `kind: TextDescriptor` in the props store (`assets/props/<ref>/prop.json`), placed as a `kind: prop` entity whose `overrides` usually carry the words (`overrides: {text: "Paris"}` — one stored style, many labels). Fields: `text` (newlines break lines), `layer` (`world` — in the scene, moves with the camera — or `overlay` — a layer the camera cannot touch: a title holds still through a push-in), `unit` (`word` | `glyph` | `line`: what one animatable node is), `size` (fraction of frame HEIGHT, default 0.06), `color` (`#rrggbb`), `align`, `max_width` (fraction of frame width, wraps), `leading`, `tracking` (em, `unit: glyph` only), `anchor` (overlay only: `top`, `bottom`, `center`, `top-left`, … inside the title-safe area; a world block is placed with `stage.at`), `font`. **Every unit is a node**: `title/word_0`, `title/word_1`, … (spaces are not units), so a reveal is ordinary tweens on `alpha`/`scale_x`/`scale_y`/`rotation` per unit (`x`/`y` are absolute and hold each unit's place in the line — a shared `y` tween stacks every word on one baseline; read a unit's offset with `an.motion.rest_pose`); a unit that starts later needs a `set` to its starting value at 0 or it shows until its turn — `an.text.reveal_units("title", n, "alpha", to=1, from_=0, duration=0.3, step=0.15)` writes both for you (extend `shot.actions` with it). **Fonts:** leave `font` unset for the built-in face (Aileron, CC0 — the same on every machine); otherwise `font` is a font FILE (`.ttf`/`.otf`/`.ttc`), absolute or relative to the text's own folder in `assets/props/<ref>/`. A family name like `Helvetica` is refused (it would depend on what the machine has installed); a missing file, a file that is not a font, and a character the face has no glyph for (the built-in face is printable ASCII plus curly quotes, `…` and `©«°±´·»` — an en/em dash or `é` raises) all **raise** — nothing falls back. A target naming a unit the block does not build (`word_5` of a three-word title) raises at validate and compile, listing the units.
  - **Two environment paths.** A store entry that is an `an.environments.EnvironmentDescriptor` **with planes** builds them, in list order (an#110): each plane has a `depth` — Godot's ratio, `1.0` = the character plane (emits nothing), `0` = does not pan, `>1` = foreground. **Depth compensates translation only**; a zoom is uniform across every plane, so pair a `depth = 0` plate with a pan rather than a push-in (depth-aware zoom is the dolly, not yet built) — and `characters_after` names the plane the characters stand in front of. An unknown key **on a plane raises** (`Plane` is `extra="forbid"`). Anything else — a free-form `meta.json`, a preset name — takes the legacy preset-override path, which reads exactly `sky_color`, `ground_color`, `ground_y` and **warns-and-drops** the rest. That is an intersection filter, not a refusal, and it is deliberate: the store's natural shape includes `name`/`description`/`tags`. So a `planes:` key on a document that does not declare `kind: EnvironmentDescriptor` still vanishes with a warning.
  - **Raster art** (an#211): an image plane's `src` and a character or prop part's attachment `path` may be `.png` (with alpha), `.jpg`/`.jpeg` or `.webp` as well as `.svg` — sized from the image header, loaded by PixiJS natively, addressed by a content digest (a re-carved file is a new texture). **A plane's declared `size` is its box** and wins over the art's own extent; `fit` (`contain` keeps the aspect, `stretch` fills) fits the art into it. A raster part is placed and scaled like an SVG part — one pixel is one view_box unit — **unless its attachment declares `width` and/or `height` (view_box units, an#220): a declared size wins**, so art carved at any resolution is sized without resampling; one of the two is enough (the other follows the art's aspect), and with both the art is contained, never stretched (`an character validate` says when the two aspects disagree). It gets outline/shadow treatments, and is **not** recoloured by a StylePack (a warning says so once). Each swap key (viseme, eyelid, view, any set) keeps its own box, anchor and offset, so keys may be drawn on different canvases. Do not wrap a PNG in an SVG `<image>`: `an character validate` refuses that in parts.
  - **Framing** (an#211): `an validate` warns when a camera key (or the resting frame) shows scene area no plane covers — the plate's edge showing as background colour — naming the key and the uncovered side. Parallax is included (a `depth = 0` plate is pinned in frame; a `depth = 1` plate moves with the world). Fix with a bigger `size`, an `offset`, or less camera move.
  - **A ref the stores can't supply gets a stand-in, and says so.** A character with no descriptor renders the placeholder rig; an environment ref that is neither a store entry nor a built-in preset (`park`/`indoor`/`night`/`sunset`/`default`) renders the default backdrop. Both warn, and both are recorded per entity in the compiled scene's `asset_resolution`. Pass `--strict-assets` to make them fatal.
- ` ```yaml actions ` — list of `tween` / `set` / `play` action dicts. Optional `start` (seconds) wraps a leaf in `sequence(delay(start), action)` so flatten gives correct absolute times. `{kind: play, target: maya, animation: idle_breath}` plays a descriptor animation (`duration`/`loop`/`speed` optional) — or, for a name the descriptor does not declare, a motion preset with optional `args` (see *Motion presets*): a non-looping one fills its natural duration (a descriptor animation's, or a preset's), a looping one with no `duration` runs to the shot end. Inside a `sequence`, a play without `duration` occupies its **natural length** — a motion preset's own length, or a non-looping descriptor animation's `duration`, both over `speed` — so the next sibling starts when it ends; a **looping** one runs to the shot end and has **zero width**, so give it an explicit `duration` when something must follow it inside the loop's window (`an.characters.play.play_extent` is the one resolver; `an validate` and the compiler pass the entity's descriptor to it). An `expression` action (`- kind: expression / target: <entity> / preset: happy [/ axes: {brow_height_l: 0.5}] [/ intensity] [/ duration] [/ blend]`) holds a face on a character, silent or speaking; `duration` omitted runs to the shot end. A `face_overlay: false` character (DiceBear) refuses one at validate. `axes: {gaze_x: 1.0}` turns the pupils (a rig without the eye stack ignores it); every rig with pupils also makes small ambient saccades of its own, seeded by the character's name.
  - **Transform properties:** `x`, `y`, `rotation`, `rotation_rad`, `scale_x`, `scale_y`, `skew_x`, `skew_y`, `pivot_x`, `pivot_y`, `alpha`, and — on a stroked path only — `trim_start`, `trim_end`. **Units:** `x`/`y` are scene pixels (see *Units and staging*); `rotation` is **radians** (`rotation_rad` is the same property; a descriptor's `rotation_deg` is the rig's rest pose in degrees and is not animatable); scales and `alpha` are factors. Any other property names a **swap set** (next bullets) and is refused at compile unless the target's descriptor declares it.
  - **`tint`** (an#62) is the one property whose value is a **colour**: a `#rrggbb` string, applied as a per-node **multiply**, and it cascades to the target's parts the way `alpha` does. Its rest value is `#ffffff` — white, i.e. no tint — so a tween with no `from` starts from the tint in force (untinted if none was set). A tween between two colours interpolates **per channel in sRGB**, because the compiler expands one authored `tint` into three numeric channels; you never see those unless you read a compiled document, and writing them directly is legal but not the intended surface. It is a multiply over the art that is there, **not** art direction: recolouring a rig's roles is `an.styles.StylePack`, which decides the colours before they are drawn. A tint to `#ff0000` makes everything red-tinted, including the eyes and the mouth.
  - **`alpha` is the entrance/exit primitive** — it cascades, so a tween on the character root fades every part of it. `{kind: tween, target: charlie, property: alpha, to: 0.0, duration: 1.0}`.
  - **A `tween` with no `from` starts from the value the property HAS at the tween's start** (an#212): the node's built pose — its `stage` placement, the laid-out `x` of a second character — overridden by the `set`s and tweens before it on the same target and property, as the runtime plays them (a tween still running governs; otherwise the latest write holds). So `set x -800` then `tween x to 0` (no `from`) walks in from -800, a bob `tween y to <y-8>` on a staged character starts where it stands, and a chain of `to`-only tweens is continuous. With nothing before it, that is the built rest: `1.0` for `scale_x` / `scale_y` / `alpha`, `0.0` for the rest. Motion presets played by name start from the same pose. Descriptor `play` clips are not part of it — give `from` explicitly after one.
  - **A property outside the transform vocabulary names a SWAP SET** (an#87): `{kind: set, target: gale/left_hand, property: hands, value: fist, at: 1.0}` swaps that node's art to the `fist` key of the character's declared `hands` asset set, holding until the next action (set or tween) on the same target/property, or the shot end. The set and key must be **declared in the descriptor's `asset_sets`** — an undeclared name or key is refused at compile with the declared ones listed. `viseme` is just such a set (lip-sync drives it automatically); a procedural (descriptor-less) rig supports only `viseme` on its mouth. Swap channels are always step-interpolated — an authored easing on a swap tween is forced to `step` with a warning.
- **`Shot.narration` is declared by the IR and NOT implemented** — a shot carrying it raises. For a narrator, use a dialogue line whose speaker is not an entity in the shot: it gets audio and no lip-sync, and warns to say so.
- **Transitions and sound** (an#163, `an.assemble`) — two optional keys in ` ```yaml shot ` and one in ` ```yaml meta `:
  - `transition: {kind: cut|fade|dissolve, duration: 0.5, color: "#000000"}` says how the shot is **entered**. Omitted = a hard cut. `fade` dips through `color` — half its duration out of the previous shot, half into this one (on the first shot, a fade up over the whole duration) — and **holds** the film's length. `dissolve` overlaps the two shots by `duration`, so the film is that much **shorter** than the sum of its shots; both play in full, each keeps its dialogue on its own frames, and both shots' audio is heard in the overlap (validate warns about a line inside one). Not on the first shot. A shot must be long enough to hold its own transition and the next shot's (validate error; render refuses before any browser launches). Transitions are composed on the frames (exact integer blends) and the film muxed once; `an preview` does not show them.
  - `sounds: [{sound: <key>, at, duration, gain_db, loop, fade_in, fade_out, duck_db}]` — cues from the project's **`sounds` store**. In a shot they are SHOT-local (they move with the shot); in `meta` they are FILM time. A music bed is `{sound: bed, loop: true, duck_db: -12, fade_in: 1, fade_out: 1}`: `loop` without `duration` runs to the end of the film (meta) or the shot; `duck_db` drops it under every dialogue line with a linear ramp (`duck_attack` before the line, `duck_release` after; lines closer than both stay ducked). The mix is rebuilt from sources and the picture is copied untouched.
  - **Sounds enter through the store, with provenance**: `an.sounds.add_sound(mall["sounds"], key, wav_bytes, source=AssetSource(...))` (WAV only; convert with ffmpeg). The licence is attached to the bytes' sha256 and `an credits` lists it; an unknown licence is reported UNVERIFIED. `pd`/`public-domain`/`cc0-*` read as nothing owed; `all-rights-reserved` (or "all rights reserved — private study only") is **NOT PUBLISHABLE**: `an credits` opens with it and a render that uses it ends with a `PrivateStudyWarning` (an#211). An environment's planes may each carry their own `source` (a carved plate plus a CC0 prop credits both), and so may a character's or prop's **attachments** (an#220: `skins.default.slots.<slot>.<attachment>.source` — a figure whose head came from one clip and body from another credits both; `an credits` lists each part by its path, and a private-study part makes the render NOT PUBLISHABLE like any other). **Ship no third-party audio you have not read the licence of** — `an.sounds.synth_tone` / `synth_hit` / `synth_bed` make deterministic stand-ins offline; add one with `source=an.sounds.SYNTH_SOURCE` (CC0, generated locally), as in the recipe below. A scene with neither key renders byte-identically to before. Not built: wipes/morphs, a closing fade to black, stereo, per-character voice effects (pitch).
- **Voice effects** (an#163, `an.audio.effects`) — a voice document in the `voices` store may carry `effects: {pitch_semitones: 4}` (±12; `0` or absent is no effect; an unknown key or out-of-range value is a validate error and raises at render). The line's voice names the document — its own `voice_ref`, else its character's (next bullet). The shift runs on the synthesized audio BEFORE lip-sync (visemes are aligned on the audio the viewer hears) and keeps the duration, so word timings hold. The chain is stock ffmpeg (`asetrate` + `atempo`, bit-exact WAV out): deterministic, but a crude shifter; `rubberband` is deliberately not used because its output varies by build and the audio is content-hash cached. The audio key gains the effect only when one is declared, so a project without effects keeps every key; the raw TTS stays cached under its own key, so changing the pitch never re-calls the provider. Needs the `ffmpeg` binary, and a missing one is an error, never silently unshifted speech.
- **A voice per character** (an#194, `an.audio.voices`) — a dialogue line is spoken by, first hit wins: the line's own `voice_ref` (Python / `ir/scene.json`; `scene.md` has no per-line syntax), else the `voice_ref` of the character entity whose `id` is the line's `speaker` — read from its descriptor (`new_character(..., voice_ref="carl_voice")`), with the entity's `overrides: {voice_ref: ...}` winning for that shot — else `default`. The name is a key of the `voices` store; a voice document may name the TTS provider's own voice with `voice_id` (a `say -v` name for `--tts mac_say`, a voice id for ElevenLabs) and carry `effects`. A speaker that is not an entity of the shot (an off-screen narrator) gets `default`. Nothing declared keeps every audio cache key. A voice name with no document in the store is handed to the provider AS IS — `say -v carl_voice` fails at render — so `an validate` warns about one; the `--tts` flag picks the provider; a document's `provider` field SCOPES its provider-specific keys (`voice_id`, and ElevenLabs's `model_id`/`voice_settings`/`seed`) to that provider — rendered under another `--tts`, the line gets that provider's default voice instead of a foreign id (an#209). Example under *A project from nothing → Voices*.
- **Captions** (an#175, `an.captions`) — `captions: {}` in ` ```yaml meta ` (or `{highlight: "#c0392b", color: "#1a1a1a", size: 0.05, anchor: bottom, max_chars: 42, max_lines: 2}`) captions every dialogue and narration line from the **word timings the lip-sync provider kept**: burned into the picture at the bottom of the title-safe area (camera-immune), paged by sentence and by 42-character lines, the spoken word lit when `highlight` is set, AND written as SubRip to `output/main.srt` beside the mp4 — from one cue list, in film time (a dissolve moves later cues). Timings come from `--lipsync whisper` or `WordTimingsLipSync`; the offline and Rhubarb providers keep none, so their lines are spread evenly with a `CaptionTimingWarning` (`strict: true` makes it an error). `burn: false` = sidecar only; `sidecar: false` = picture only. The caption blocks are added at render time and never appear in `scene.json`; don't author `caption_<k>` entities yourself (the ids are taken). The embedded face lacks `—`/`é`: such a line raises when captions are on. Not built: WebVTT, a backing scrim, speaker labels, captions in `an preview`.
- ` ```dialogue ` — `speaker [emotion] {direction} (timing): text` per line; the bracketed emotion, the braced delivery direction (comma-separated cues such as `{sighs, annoyed}`, an#209 — performed by an expressive ElevenLabs voice, see *Voices → Expressive ElevenLabs voices*; never spoken as words, never in captions) and the parenthesised timing are each optional, in any order. Timing is `(pause 1.5)` — seconds of silence after the previous line ends — or `(at 3.0)` — a start in shot seconds (see *Dialogue timing*); before the colon, parentheses hold only timing, so `maya (warm): …` is refused (after the colon it is all text: `stan: (whispers) hi` is fine). Emotion is an expression preset — `neutral | happy | sad | angry | surprised | afraid | disgusted | thinking | skeptical | amused` (an unknown name is a validate ERROR). It is sugar for an `expression` over the line: the face solver moves the brows (height and angle), picks the eyelid key, and selects the mouth's `viseme@<form>` set for the line's visemes.

## A project from nothing

Everything a render needs, created from Python or the CLI — no file from the `an` repo required. Run the recipe, write the scene, validate, render.

### Units and staging

- **Stage coordinates are scene pixels from the frame CENTRE, y DOWN.** Scene pixels are output pixels: nothing rescales with `meta.resolution`, so the same numbers fill more of a 1280x720 frame than of a 1920x1080 one. Path `points`, plane `offset`/`size`, `stage.at`, a `hop`'s `height` and every `x`/`y` tween use them. Text `size` is the exception: a fraction of frame height.
- **An `an character new --offline` character is about 265 px tall at `stage.scale: 1`**: its drawn art runs from about 170 px above its origin to 95 px below. At scale `s` placed at `stage.at: [x, y]`, its top is at `y − 170·s`. The top edge of the frame is at `−height/2`, so keep `y − 170·s − hop_height` above it — divided by the camera's zoom when one runs (`push_in` ends at 1.25x about the frame centre, `zoom_in` at 1.5x). At 1280x720 a two-shot is `scale` 1.2-1.5 at `x = ±230`; a single close is `scale` 1.8-2.0 at `y` 60-120 (lower is closer to the bottom edge).
- `hop` `height`, `shake` `amplitude`, `slide_in` `distance` are scene pixels, not multiplied by the entity's `stage.scale`.

### Addressing a character's parts

A target is `<entity id>/<node>` and the rigs are FLAT except the face, whose parts are children of the head: `ned/head/mouth`, never `ned/mouth`. The node paths each rig builds, for an entity with id `c` (generated from the code; `tests/test_skill_rig_paths.py` fails if this list drifts):

<!-- rig-paths:begin (generated by tests/test_skill_rig_paths.py; do not edit by hand) -->
| rig | node paths |
|---|---|
| `an character new --offline` (default) | `c`, `c/arm_l`, `c/arm_r`, `c/head`, `c/head/left_brow`, `c/head/left_eye`, `c/head/left_pupil`, `c/head/left_sclera`, `c/head/mouth`, `c/head/right_brow`, `c/head/right_eye`, `c/head/right_pupil`, `c/head/right_sclera`, `c/leg_l`, `c/leg_r`, `c/torso` |
| `new_character(..., gaze=False)` | `c`, `c/arm_l`, `c/arm_r`, `c/head`, `c/head/left_brow`, `c/head/left_eye`, `c/head/mouth`, `c/head/right_brow`, `c/head/right_eye`, `c/leg_l`, `c/leg_r`, `c/torso` |
| no descriptor (the placeholder rig) | `c`, `c/head`, `c/head/hair`, `c/head/left_brow`, `c/head/left_eye`, `c/head/mouth`, `c/head/right_brow`, `c/head/right_eye`, `c/left_arm`, `c/right_arm`, `c/torso` |
<!-- rig-paths:end -->

- **Rotation is radians, clockwise on screen** (y points down). An arm hangs from its shoulder, so a positive `rotation` swings its hand toward the viewer's LEFT: on an `an character new` character `arm_l` hangs on the viewer's left and `arm_r` on the right, so `+1.2` raises `arm_l` out to the side and swings `arm_r` across the chest, and `arm_r` is raised with a NEGATIVE angle (`-2.1` is up and out; alternate `-2.1`/`-1.5` for a wave). Another rig may put its arms the other way round: read the side off `an.motion.rest_pose(shot, "c/arm_r", mall=mall)["x"]` (negative is the viewer's left).
- `scale_x: -1` on the entity mirrors the whole character (a turn to face the other way): the arms swap sides on screen, and each is still raised by the same sign — `arm_l` with a positive angle, now on the viewer's right.

### Voices

One voice document per character, each bound from its descriptor; the pitch is an effect on the voice, and `voice_id` picks the provider's voice (here macOS `say` voices, for `an render --tts mac_say`; under the default offline TTS they are silent but still distinct keys):

```python
from an.characters import new_character

ch = root / "assets" / "characters"
new_character(ch, name="carl", use_dicebear=False, voice_ref="carl_voice")
new_character(ch, name="ned", use_dicebear=False, voice_ref="ned_voice")
mall["voices"]["carl_voice"] = {"voice_id": "Junior", "effects": {"pitch_semitones": 5}}
mall["voices"]["ned_voice"] = {"voice_id": "Ralph", "effects": {"pitch_semitones": 2}}
```

Then `carl: Hi!` and `ned: Bye.` in a ```` ```dialogue ```` block speak in two voices at two pitches. For one shot only, an entity's `overrides: {voice_ref: ned_whisper}` re-voices it.

#### Expressive ElevenLabs voices

For real, acted speech render with `--tts elevenlabs` (needs `ELEVEN_API_KEY` or `ELEVENLABS_API_KEY` and `pip install elevenlabs`). Browse voices with `an voices list --provider elevenlabs [--search british]` (Python: `an.audio.cli.browse_voices("elevenlabs", search=...)`); the first column is the `voice_id`. A voice document for ElevenLabs may declare (an#209):

- `provider: elevenlabs` — scopes the keys below to that provider (an offline or `mac_say` preview then speaks in its own default voice);
- `voice_id` — from `an voices list`;
- `model_id` — `eleven_v3` (or `eleven_v4`, `eleven_v4_turbo`, `eleven_v3_conversational`) is the expressive family and the only one that performs audio tags; `eleven_multilingual_v2` is steady and takes `style`; the default when unset is `eleven_turbo_v2_5` (fast, flat);
- `voice_settings` — any of `stability` (0–1; lower = more emotional range, v3 reads only 0.0 "Creative", 0.5 "Natural" and 1.0 "Robust", rounding anything else to the nearest), `similarity_boost` (0–1), `style` (0–1, multilingual_v2), `use_speaker_boost` (bool), `speed` (0.7–1.2); an unknown key or out-of-range value is an `an validate` error;
- `seed` — a non-negative int for more repeatable re-synthesis.

On an audio-tag model a line's `[emotion]` (except `neutral`) and its `{direction}` cues are sent as inline tags — `laura [happy] {excited}: Hi!` is spoken as `[happy] [excited] Hi!`. Any cue works (`sighs`, `whispers`, `laughs`, `clears throat`, `sarcastic`, `deadpan`). Tags never enter `text`, so captions, `.srt` and lip-sync alignment see only the words. On a non-tag model a `{direction}` is dropped with a warning (`an validate` says so) and `[emotion]` stays a face-only cue. The audio cache key includes model, settings, seed and tags, so changing any of them re-synthesizes that line only; a voice declaring none of them keeps every key it had.

Two characters — an eager one and a flat, annoyed one:

```python
new_character(ch, name="laura", use_dicebear=False, voice_ref="laura_voice")
new_character(ch, name="callum", use_dicebear=False, voice_ref="callum_voice")
mall["voices"]["laura_voice"] = {
    "provider": "elevenlabs",
    "voice_id": "FGY2WhTYpPnrIDTdsKH5",  # Laura — enthusiast, quirky
    "model_id": "eleven_v3",
    "voice_settings": {"stability": 0.0},  # Creative: big swings
}
mall["voices"]["callum_voice"] = {
    "provider": "elevenlabs",
    "voice_id": "N2lVS1w4EtoT3dr4eOWO",  # Callum — husky trickster
    "model_id": "eleven_v3",
    "voice_settings": {"stability": 0.5, "speed": 0.95},
}
```

```dialogue
laura [happy] {excited}: Oh my gosh, we are finally going to the fair!
callum {sighs, annoyed}: Great. Crowds. My favourite.
```

then `an render <dir> --tts elevenlabs --lipsync whisper`. Voice ids are account-visible voices at the time of writing — pick your own with `an voices list`. Each line is one billed request, cached by content, so re-rendering an unchanged line costs nothing.

### Dialogue timing

- A shot's lines play **back to back from the shot start** unless a line says otherwise. **A beat is a pause, not a shot**: `maya (pause 1.5): Bye.` holds 1.5 s of silence after the previous line ends, and every later line moves with it; `maya (at 3.0): Bye.` starts the line at 3.0 s into the shot, and the next line follows it. One line takes one or the other. The audio, the mouth, captions and music ducking all follow, and a reaction during the pause is an ordinary action with a `start` (an `expression` with `axes: {gaze_x: …}` for a look, a `play` of `nod`). Splitting a line into its own shot just to get a pause adds cuts a style did not ask for.
- The audio pipeline stamps `start` and `duration` into `ir/scene.json`; `start` is **re-derived from `pause`/`at` on every render and preview** (`an.audio.pipeline.retime_dialogue`), so editing a pause re-times the shot without re-synthesizing anything. Never set `start` yourself — write `pause` or `at` (in `an iterate`, patch `timeline/N/dialogue/K/pause`).
- **A recipe for "X says hi. Y pauses, looks at X, says bye."** — one shot, sized to hold the lines plus the pause:

  ```dialogue
  stan: Hi, Kyle.
  kyle (pause 1.5): Bye.
  ```
  with `{kind: expression, target: kyle, preset: skeptical, axes: {gaze_x: -1.0}, start: 0.7, duration: 1.5}` in ` ```yaml actions ` for the look (gaze toward a character on the left is negative).
- The offline voice is **silent** and lasts 0.05 s + 0.06 s per non-space character, at least 0.4 s (`an.audio.offline_tts.estimate_speech_duration(text)`), so you can size shots before rendering. A real voice (`--tts elevenlabs`, or `--tts mac_say` — a free local voice on macOS) is usually a little slower.
- The shot's audio stops at the shot end. `an validate` warns when a line would run past it — pauses and `at`s included: from the estimate before any synthesis, from the real timing after a render. It also warns when an `at` makes a speaker start a line before their previous one ends (two speakers talking over each other is fine).
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

for name in (
    "stan",
    "kyle",
):  # = `an character new <name> --offline --out-dir my_film/assets/characters`
    new_character(root / "assets" / "characters", name=name, use_dicebear=False)

# A title card: one fill plane with no `size` covers the canvas; depth 0 never pans.
mall["environments"]["card"] = EnvironmentDescriptor(
    name="card",
    planes=[Plane(name="bg", art=PlaneArt(kind="fill", color="#040404"), depth=0.0)],
).model_dump(mode="json")

# A map: sea, land, and a WHITE territory, so a `tint` tween can colour it (tint multiplies).
mall["environments"]["map"] = EnvironmentDescriptor(
    name="map",
    planes=[
        Plane(name="sea", art=PlaneArt(kind="fill", color="#a7b1b9"), depth=0.0),
        # depth 1.0 = the character plane: pans exactly with props (the route, labels)
        Plane(
            name="land",
            art=PlaneArt(kind="fill", color="#cda469"),
            depth=1.0,
            size=(1100, 420),
        ),
        Plane(
            name="west",
            art=PlaneArt(kind="fill", color="#ffffff"),
            depth=1.0,
            offset=(-250, 0),
            size=(400, 300),
        ),
    ],
).model_dump(mode="json")

# Words: an overlay title (the camera never moves it) and a reusable world label.
mall["props"]["date"] = TextDescriptor(
    name="date",
    text="OCTOBER 1ST, 2026",
    layer="overlay",
    unit="line",
    size=0.1,
    color="#ffffff",
).model_dump(mode="json")
mall["props"]["label"] = TextDescriptor(
    name="label", text="label", size=0.05, color="#1a1a1a"
).model_dump(mode="json")

# A route arrow that starts hidden (trim_end 0), drawn on by a trim_end tween.
mall["props"]["route"] = PathDescriptor(
    name="route",
    points=[(-300, 60), (0, -40), (260, 30)],
    arrowhead=True,
    trim_end=0.0,
    color="#ba5f31",
    width=10,
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
2. **Run `an init <dir>`** in their target directory (creates the project tree) — or `an init --id <id>` when they name none (it lands under `~/.local/share/cutan/projects/`).
3. **Make the assets and write `scene.md`** — *A project from nothing* above is the whole kit: the recipe for characters, text, paths, planes, StylePacks and sounds, and a complete scene to start from. A character with no descriptor renders as a placeholder rig (with a warning); `--strict-assets` makes that an error.
4. **Run `an validate <dir>`** and surface any findings (warnings about unresolved voice/character refs are fine if assets aren't promoted yet).
5. **Run `an render <dir>`** for the offline default, or `an render <dir> --tts elevenlabs --lipsync whisper` for real speech with word-aligned visemes (best quality without external binaries).
6. For iterative tweaks, prefer **`an iterate <dir> "<plain-English change>"`** over hand-editing scene.md — it's the spec's signature loop. Nothing needs invalidating: the next `an render` re-renders only the shots whose inputs changed and reuses the rest.

**"In the style of X"** (South Park, OverSimplified, Kurzgesagt, Gilliam, Reiniger, Norstein): use the **`an-style`** skill — a style spec per look (live settings, measured targets, and what `an` cannot do yet), and `an.verify.style` (`StyleLintVerifier`) to measure the render against the targets.

## Reusing assets: the library (`an library`)

Assets outlive their videos in a **library** (ADR 0005): one per package, at `~/.local/share/an` (core) or a genre's own root such as `~/.local/share/cutan` (cut-out characters, props and stages go there: `--package cutan`), overridable with `AN_HOME` / `CUTAN_HOME` or `--root`. Never keep reusable assets in a session folder or a repository; publish them. Every library this machine has ever written is recorded in a registry that no environment variable moves, so private study material binds every other library wherever it sits; a library written at a custom `--root` by an `an` older than that registry is recorded on its next publish, or by `an.library.api.reindex(open_library(<pkg>, root=<root>))`. Agent-made projects default to `<root>/projects/<project_id>/` (`an init --id <id>`, `an.library.project_dir`).

- **Publish** a finished asset folder (as it sits in a project): `an library publish assets/characters/alice character.alice-reiniger --package cutan --style reiniger --family alice --origin carved --license all-rights-reserved-private-study --provider "<film>"`. Ids are `<kind>.<slug>`; a different look of the same character is a sibling id in the same `--family`, not a folder. Publishing unchanged content makes no new version; an edit makes `v002`. Give provenance (`--license`/`--provider`, or `source` in the descriptor): without it the asset is `unknown`, which is never publishable. A declared licence counts beside the descriptor's own source, the previous version's, and whatever any library on this machine says about the same file bytes. Copying carved parts into a new asset keeps them private. Label carved parts per part, with the file's `sha256`, when one character mixes carved and drawn art. A character from `an character new --offline` is stamped as the factory's own `cc0` work, descriptor and parts, so it publishes `free` with no `--license`; a stamp speaks only for the bytes it pins, so a part re-drawn or re-carved since is `unknown` until you label it (`--license`/`--provider` for the asset, or a per-part source). The strictest wins: a new version or a `cc0` label never relaxes private art. Only an explicit relicence relaxes it (`--relicense-by <who> --relicense-reason <why> --license …`), and it is recorded on the version. `--expect-head new` refuses an id that already exists, so a different character is never merged into it.
- **Find** by facets — AND across facets, OR within one (comma-separated): `an library find --package cutan --kind character --style reiniger --affords limbs.legs,swap.view:side --near`. `--affords` terms are capabilities derived from the rig, never typed by hand: `limbs.legs`, `limbs.arms`, `swap.view` (`:side`, `:back`, …), `face.mouth` (`:rhubarb9`); an unknown name is refused with the close ones. Whether a character can walk on legs is `limbs.legs` (every character walks: legless ones rock). `--near` lists what nearly fits with the missing capability and its remedy (e.g. `an character add-views`). `--rights publishable` excludes private and unknown assets. `an library vocabulary` lists every facet value and capability: map the director's words onto those terms, and record the mapping in `.an/decisions.jsonl`.
- **Check out** into a project: `an library checkout <dir> cutan:character.alice-reiniger@v002` (the `cutan:` prefix selects the library; no `--package` needed). The files land in the project's own store (`assets/characters/alice-reiniger/`), byte for byte, with the pin in `assets.lock.json`; the command prints the `yaml entities` line to cast it (`library: "cutan:…@v002"` beside the usual `ref`). The copy carries its rights: `an credits` and the render's private-study warning see private material exactly as in the library. Editing the checked-out copy forks it (a re-checkout then refuses without `--overwrite`; `an validate` reports it as `info`); `an library publish` of that folder sends the edit back as a new version derived from the one checked out. A character made in the project and just published is linked by checking it out into the same project (`publish` prints that command); it is recognised as unedited, no `--overwrite`. **`assets.lock.json` is the record of which version the project holds**; the scene's `library:` must say the same, and `an validate` warns when it does not — after re-checking out a newer version, update the `library:` line it names. Never hand-type `@latest` into a scene: it is refused; the checkout prints the pinned line.
- **Show** one asset: `an library show cutan:character.alice-reiniger` (versions, rights with reasons, affordances).
- **Promote** an asset to the core library so another genre can reuse it: `an library promote cutan:character.x`. Private and unknown material is refused unless `--allow-restricted`: carved study material stays where it is. If the core library already has an unrelated asset with that id, pass `--as-id`.

Python: `from an.library import open_library, search_path, publish_dir, find, checkout` — the same functions. `an credits <dir>` lists what `an` made itself (factory characters, synthesized sounds) apart from third-party work.

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

This is principle 1 of `an`'s design principles (`misc/docs/design_principles.md` in the repo) applied to you: when you turn the director's words ("she walks in nervously") into typed values (a `walk` with a shorter stride), record the words, the values you chose and why, so a re-render never has to re-interpret them. The same principles say every aspect has a default that applies to any character: when the director asks for something a character's rig cannot do (a legged walk on a robe figure, lip sync on a baked face), say what structure is missing and how to add it (`an character add-views`, separate leg parts, a hand-rigged face), and meanwhile use what does apply (the `walk` preset falls back to a rock on a legless figure; a baked face has no speech default yet, so tell the director the mouth will not move) — never let an aspect drop out silently.

## What to never do

- Never write directly to `ir/scene.json` — edit `scene.md` and run `sync`, OR use `mall["scenes"]["main"] = scene_ir` (which writes both files and equalizes mtimes).
- Never inline large assets into the IR; reference them by store key via `AssetRef`.
- Never claim a render produced something it didn't — `an render` returns the mp4 path; if it fails, surface the actual error from the renderer.
- Never bypass the audio pipeline by manually constructing viseme tracks unless the user is debugging — `produce_audio_for_scene` runs automatically inside `render` when needed.
