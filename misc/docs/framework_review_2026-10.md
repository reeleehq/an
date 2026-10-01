# Framework review — structured animation, October 2026

**Status:** review for the maintainer, 2026-10-01. Proposals here are carried by four ADRs in `misc/docs/adr/` (all *Proposed*: the maintainer decides). The cut-out half of the review is `misc/docs/cutout_framework_review_2026-10.md`. The four principles it applies are `misc/docs/design_principles.md`. The asset library and its storage are designed separately (`misc/docs/asset_library_design.md`, ADR 0005), and this review does not repeat them.

**What it answers.** How well does `an`, as built, separate a **core** that every structured-animation genre needs (shapes, transforms, timing, composition, the semantic/MCP layer, storage, incremental re-rendering) from the **genre**-specific parts (cut-out rigs, faces, lip sync, styles)? What did the plans say, and what of them is done, obsolete or ahead? Where does each aspect sit between structured and semantic specification? And how far is `an` from capability-based applicability with defaults?

Numbers below (line counts, module counts) were measured on `main` at 0.1.124. Terms are defined in §1 and used in that sense throughout.

---

## 0. Findings in one page

1. **`an` is a cut-out animation package with a genre-neutral core buried inside it.** About 45% of the package's ~52k lines are cut-out-specific (characters, faces, the cut-out compiler and runtime, motion presets, styles), another ~24% are instruments built on the cut-out renderer (bench, impacts), and only ~10% is clean core. The ~14% in between is core-shaped code that hard-codes cut-out knowledge: `an/ir/validate.py` (1.9k lines) imports characters, expression and the cut-out compiler; `an/render.py` imports the cut-out compiler; the IR's `Action` union, `AssetRef.kind` and `RendererName` are **closed**, so a genre cannot add an action, an entity kind or a renderer name without editing the core. The split is feasible, but it needs a set of registries (§3) before a package boundary can exist. The one extension point that already works the right way is the per-kind migration registry (`register_kind` / `register_migration`), and it is the template for the rest.
2. **Two promises in the docs are not true today, and both bear on the vision.** (a) *"Persistence via dol-backed MutableMappings"* (pillar 7): `dol` is a declared dependency that **no module imports** — the stores are hand-rolled `MutableMapping`s. (b) *"Adjust after a draft without re-processing everything"*: only audio is incremental. The per-shot mp4 store is write-only, every `an render` renders every shot, and `an iterate`'s "invalidation" deletes entries nothing reads. The building blocks for real incremental re-rendering exist in the fleet (`lacing`'s content-addressed `ArtifactStore`; `nw`'s verifying traces with early cutoff) and in `an` (`scene_contract_sha256`, `runtime_sha256`), but nothing joins them (ADR 0004).
3. **Capability checks exist, but each is a one-off.** `play_problems`, `preset_swap_problems`, `expression_problems`, `default_binding`, `resolve_mouth_set`, the walk's `_limb_pair` + `gait` chain, and the blink's swap-or-squash choice each infer, privately, what a rig affords from slot and set names. The face system comes closest to the principle: its binding is derived from the rig, and an absent part degrades to a no-op. Walking and speaking do not meet it: a character with a baked face speaks with a frozen mouth, and no "default speech" applies to anything. One requirements/affordances registry with per-aspect default chains (ADR 0002) would subsume all of them. an#224 (locomotion methods) is the first client.
4. **The semantic layer exists in three disconnected places and is defined zero times.** Name lookups (`[happy]`, `play: walk`, `turn to: back`, preset environments), an LLM pass over the whole IR (`an iterate`, whose system prompt hand-lists the cut-out vocabulary), and after-the-fact checks (style lint, the emotion judge, `an character validate`) share no vocabulary registry. There is no MCP surface at all, although report 0 made one its Phase 1. ADR 0003 places one vocabulary registry in the core, generating the iterate prompt, the MCP tools/resources and the skill docs, and fixes the rule that below the IR everything is deterministic and versioned: names may stay in the IR with a version, LLM descriptions never reach the compiler.
5. **The family re-defines timing.** The animation-track format is hand-copied into `shaping`; `burns` copies `an`'s camera layout; `previz`, `burns` and `walkthru` use CSS easing names; `shaping`'s `ease_in_out` is cubic where `an`'s is quadratic under the same name; and `an`'s own `ease` docstring claims to match CSS `ease` while returning the quadratic ease-in-out. Principle 3 ("define once") argues for the core publishing one easing table, one track-format JSON Schema and one camera-move table that the siblings consume (§3.4).

The decisions this asks of the maintainer are in §8.

---

## 1. Glossary — plain words to domain terms

Used consistently in this review, the cut-out review, the ADRs and `design_principles.md`. "Harmony" = Toon Boom Harmony, the dominant TV cut-out tool; "Moho" = Moho (formerly Anime Studio); "Spine" = Esoteric Spine, the game-animation standard whose data model `an`'s character descriptor follows. The last column is the name in `an` today.

| Plain word | Domain term | Meaning | Harmony / Moho / Spine | `an` today |
|---|---|---|---|---|
| sub-genre, a look, a way of doing it | **style** (captured in a **style guide** / **show bible**); here a **genre** is the broader kind (cut-out, data-viz, math-viz) and a **style** a look within it | the choices — art, rig, timing, staging, surface — that make a show recognisable | — | `StylePack` (colours, surface treatments) + the `an-style` YAML **style specs** (measured targets) |
| shapes | **drawables**: **parts** / **pieces** (cut-out), **artwork**, **graphic primitives** (data/math viz) | the flat things that are drawn | Harmony *drawings*, Moho *vector/image layers*, Spine *attachments* | attachments (SVG/raster), procedural rect/ellipse visuals, `PathDescriptor`, `TextDescriptor`, fill planes |
| how the shapes connect | **rig**: a **skeleton** of **bones** (Harmony: **pegs**) with **pivots**, and **parenting** | the hierarchy that makes parts move together | Harmony pegs + pivots, Moho bones, Spine bones | `Bone`, `Attachment.anchor`; rigs are **flat** (see the cut-out review) |
| a place a shape sits | **slot** (a draw-order position holding one attachment at a time) | lets the drawing change while the transform stays | Harmony drawing layer, Spine slot | `Slot` |
| what's in front of what | **draw order** / **z-order** | layering | Harmony Z, Spine draw order (keyable) | static slot order; plane list order; no keyed draw order |
| swapping one drawing for another | **replacement animation** / **drawing substitution** | changing a part's drawing over time (mouths, hands, eyes) | Harmony drawing substitution, Moho switch layer, Spine attachment key | **swap set** (`asset_sets`) and swap channels |
| a whole re-dressed version of a character | **skin** (Spine), **costume** | an alternative set of attachments for every slot | Spine skins | `Skin` (only the default is ever drawn) |
| front / side / back of a character | **turnaround** of **views** (front, three-quarter, profile, back), drawn on a **model sheet** | | Harmony per-angle breakdown, Moho switch-layer angles | `view` swap set, `rest_view`, `turn` preset |
| the faces a character makes | **expression sheet**; the controls are the **facial rig** | | Harmony master controllers | expression axes + presets, the face solver |
| the mouth shapes | **mouth chart** (Preston Blair / Hanna-Barbera); each shape a **viseme**; fitting them to speech is **lip sync** (**phoneme breakdown**) | | Harmony lip-sync detection, Moho Papagayo | 9-shape viseme set (Rhubarb A–H, X), `viseme@<form>` variants, co-articulation |
| how they move | **animation**: **keys** (**keyframes**), **in-betweens** (**tweens**), **easing** (**slow in / slow out**), **timing** and **spacing** | | all | `tween`, `set`, easing presets |
| choppy vs smooth | animating **on ones / twos / threes** (**limited** / **stepped** animation), **holds** | how many frames each pose is held | Harmony exposure | `step_hz` |
| a reusable movement | an **action** / **animation clip**; a **cycle** when it loops | | Moho actions, Spine animations, Harmony templates | descriptor `animations` (`play`), motion presets |
| walking | **locomotion**; a **walk cycle** of **contact / down / passing / up** poses; the leg style is the **gait** | | | `walk` preset, `gait: legs / hem / rock` |
| a few key poses held | **pose-to-pose** with **holds**; replacing the whole body drawing is a **pose swap** | | | whole-character swap + `swap_poses` |
| the world | the **set** / **background (BG)** / **layout**, split into **planes** (**multiplane**) moving with **parallax** | | Harmony multiplane, camera peg | `EnvironmentDescriptor`, `Plane`, `depth` |
| things in the world | **props** (and **set dressing**) | | | props store, `PropDescriptor` |
| the viewpoint moving | **camera moves**: **pan, tilt, truck / dolly, push-in, pull-out, zoom**; **framing**, **title-safe** area | | Harmony camera peg | nine named moves + `Camera.keys` |
| smoke, sparkles, speed lines | **FX** / **effects animation** (particles, smears, impact stars, dust) | | Harmony effect modules, Moho particles | not built |
| the look of the surface | **surface treatment** / **compositing** (outline, drop shadow, glow, texture, grain) | | Harmony effect nodes | `SurfaceTreatment`, `Grain` |
| between shots | **transitions** (cut, fade, dissolve, wipe) in the **edit** | | | `Shot.transition` |
| from script to video | **script → storyboard → animatic → layout → animation → compositing → edit**; the timing document is the **exposure sheet** (**X-sheet**, **dope sheet**) | | Harmony X-sheet | `scene.md` → `ir/scene.json` → compiled shot → frames → mp4 |
| setting up a shot before animating it | **layout** / **staging** / **blocking** | | | stage placement, `stage_poses` |
| a quick visual plan | **previz** (previsualisation), **animatic** | | | sibling package `previz` |
| "this walk needs legs" | the behaviour's **requirements** (preconditions) against the asset's **affordances** (capabilities); matching them is **rig compatibility**; moving an animation to another rig is **retargeting** | | Spine animations key named bones; Harmony templates need matching node names | ad hoc: `play_problems`, `gait`, `face_overlay`, … |
| what happens when nothing is said | the **default**; applying it in place of a requested **method** is a **substitution** (always recorded) | | | stand-ins recorded in `asset_resolution` |
| adjust without redoing everything | **incremental rebuild** / **non-destructive editing**, by a **dependency graph** with **invalidation** and **early cutoff**; in production, a **retake** | | | audio caches only |
| say it in words vs in numbers | **semantic** specification (natural-language **direction**, **intent**, **goals**) vs **structured** specification (typed **parameters**) | | | `[emotion]`, preset names, `an iterate`; style lint |
| the part every genre shares | the **core** (here: `an`) | | | — |

---

## 2. The layers as built

The pipeline is the three-layer IR of pillar 1: **narrative** (`scene.md`, human-edited) ↔ **scene graph** (`ir/scene.json`, the SSOT) → **render code** (a per-backend compiled document, disposable) → frames → mp4. The table classifies each layer by how cleanly it separates core from genre. "Core" means a data-viz or math-viz genre would need the same thing unchanged.

| Layer | Where | What it is | Core / genre today | Coupling to cut (examples) |
|---|---|---|---|---|
| **IR** (scene graph) | `an/ir/schema.py`, `migrate.py`, `sync.py`, `validate.py`, `camera.py`, `assets.py` | Pydantic `SceneIR` → `Shot` → entities (`AssetRef`) + actions + dialogue; versioned, `extra="allow"`, migrated on read | **Mixed.** Neutral: `SceneIR`, `Meta`, `Shot`, `SetAction`, `TweenAction`, the combinators, `Camera`, `Transition`, `SoundCue`, `Captions`, most of `Dialogue`. Cut-out: `PlayAction`, `ExpressionAction`, `Dialogue.emotion` / `viseme_*`, `AssetRef.kind = "character"`, `Meta.style_pack`, `renderer` defaulting to `"cutout"` | The `Action` union is a closed discriminated union; `AssetRef.kind` and `RendererName` are closed `Literal`s. The list of action kinds is repeated at six dispatch sites (sync reader and writer, `compose.duration_of`, the compiler, validate, the iterate prompt). `validate_semantic` is one 1.9k-line function calling cut-out checks (`_check_turns`, `_check_hidden_mouth_while_speaking`, …) and the cut-out compiler's own target resolution |
| **Composition** | `an/ir/compose.py` | `sequence`, `parallel`, `delay`, `loop`, `tween`, `set_`, `play` → `flatten` → absolute-time `FlatAction`s (pillar 3) | **Core**, nearly clean | `default_play_extent` imports `an.characters.play`; `duration_of` special-cases `ExpressionAction` |
| **Timing evaluation** | `an/adapters/cutout/{easing,channel,clip,timeline}.py` | easing presets + cubic Bézier, keyframe channels, clips, timeline evaluation — the executable spec of the runtime, parity-tested | **Core in substance, filed under cut-out.** `characters.play`, `impacts`, and `validate` reach into `adapters.cutout` for easing | Move to a core `an/timing/`; no wire change |
| **Compile** (IR → render code) | `an/adapters/cutout/compile.py` (5.7k lines, 11% of the package) | one shot → `CutoutSceneJSON`: builds the stage tree, rigs, planes, paths, text; camera and parallax clips; tint/trim expansion; stepped timing; face solver; visemes; blinks; gaze; swap fan-out; surface treatments | **Mixed in one module.** Scene building, camera, parallax, paths, text, stepping and tint are genre-neutral; the rig, face, viseme, blink, gaze and swap-pose passes are cut-out | Needs a compile-pass registry (`compile_shot` calling registered passes) before a package boundary can cut it |
| **Runtime** (render code player) | `an/data/cutout_runtime/runtime.js` (1.4k lines, vendored PixiJS 7) | loads the compiled document, evaluates channels, applies swaps, draws paths and text, captures frames | **~90% a generic 2D keyframed scene-graph player.** Only the procedural `mouth` / `eye` visuals (~50 lines) are rig-specific | `registerVisualKind`-style hook for genre visuals. The wire shape is hash-pinned by the bench (`scene_contract_sha256`), so the split must not rename it |
| **Render orchestration** | `an/render.py`, `an/assemble.py`, `an/adapters/_base.py` | `Renderer` Protocol + registry (shot → mp4), per-shot dispatch, ffmpeg concat or frame-stage assembly (transitions, sound mix, captions) | **Core, with leaks.** The `Renderer` seam is clean and open | `render.py` imports `style_pack_for` from the cut-out compiler and tests `shot.renderer != "cutout"` for captions; `assemble.py` borrows `_ffmpeg_mux` from the cut-out renderer; `RenderContext.style_pack` is typed as the cut-out `StylePack` |
| **Stores / mall** | `an/stores/`, `an/project.py` | 14 `MutableMapping` stores built by `build_project_mall`; content-keyed audio/viseme blobs; decisions log | **Mixed.** Generic: scenes, voices, sounds, decisions, audio, shots, output, captions. Cut-out: characters, props, environments, styles, visemes | The store list is closed (overrides can swap a store, not declare one). **`dol` is never imported**, despite pillar 7 |
| **Audio** | `an/audio/` | TTS providers (offline, ElevenLabs, `say`), voices, effects, the content-hash pipeline; lip-sync providers (offline, Whisper, Rhubarb, injected word timings) | **Split down the middle.** Speech, voices and **word timings** are core (narration and captions serve every genre); visemes are cut-out | `pipeline.py` imports the lip-sync providers eagerly and stamps `Dialogue.viseme_track`. Word timings need a core home (`WordTimingProvider` exists as a protocol) |
| **Verify** | `an/verify/` | `Verifier` Protocol + `Finding(severity, ir_path, …)`; layout lint, media QA, vision LM, human, style lint | **Core**, except `style.py` (cut-out style targets) | `vision.py` imports the expression presets |
| **Semantic** | `an/iterate.py`, `[emotion]` sugar in `ir/sync.py`, `an/expression/provider.py`, preset dicts | free text → Claude → JSON-pointer patches on the IR; names → presets | **Core mechanism, cut-out vocabulary.** No registry; vocabularies are module-level dicts (`motion.PRESETS`, `expression.presets.PRESETS`, `CAMERA_MOVES`, `EASING_FUNCS`) | The iterate system prompt hand-lists the cut-out vocabulary. No MCP surface (ADR 0003) |
| **Surfaces** | `an/tools.py`, `an/__main__.py` (typer over `_dispatch_funcs`), `an preview` | CLI; a live preview page | **Core shape (dispatch over plain functions), cut-out content** | `tools.py` eagerly wires the `an character` namespace and the cut-out preview. MCP would be one more dispatcher over the same list |
| **Instruments** | `an/bench/` (11k lines), `an/impacts/` | metrics ledger, golden corpus, mutation harness; synthetic impact clips with ground truth | **Built on the cut-out renderer.** The metric, PNG, ledger, registry and compare modules are pixel-generic | capture/run/golden import the cut-out compiler and renderer |
| **Genre declaration** | `an/genre.py` | declares `cutout_animation` to `nw` as a *planned* genre | the right *shape* for a genre-as-package seam | its docstring proposes an `nw.renderers` Strategy, which epic an#9 later superseded with "the seam is `nw.Transform`"; neither is built |

**Reading of the table.** The architecture's *pillars* are genre-neutral — three-layer IR, combinators that flatten, path-based targeting, protocols for everything external, typed findings routed to the lowest layer. That is why the split is possible at all. The *implementation* grew around one renderer: epic an#9 said outright that "all nine waves go into the one renderer", and every wave did. The result is a genre-neutral **design** and a cut-out **codebase**.

---

## 3. Proposal: the core/genre split

Carried by ADR 0001. In short:

### 3.1 The boundary rule

A thing belongs in the **core** (`an`) if a data-viz or math-viz genre would need it unchanged; otherwise it belongs in the genre package. When in doubt, the test is: *can it be stated without the words character, face, mouth, rig, or a style's name?*

| `an` (core) keeps | The cut-out genre package takes |
|---|---|
| IR envelope and the genre-neutral models; composition and `flatten`; migration registry; `scene.md` sync framework | `PlayAction` and `ExpressionAction` (registered as action kinds); `character` (registered as an entity kind); the `[emotion]` sugar (registered md sugar) |
| Timing: easing table, channels, clips, timeline evaluation (moved out of `adapters/cutout`); `step_hz`; frame clock | Descriptor animations (`play`), motion presets that need parts (`walk`, `turn`, `nod`, `point`, `waddle`) |
| Shapes and transforms: the transform vocabulary, paths, text (tituli), fill planes, the generic transform macros (`pop_in`, `slide_in/out`, `shake`, `squash_stretch`, `hop`) | Characters: descriptor, factory, art package contract, promote, DiceBear; props' rig shape |
| Staging: camera (`camera_keys`), planes and parallax, transitions | Faces: expression axes, presets, the face solver, gaze, blinks |
| The **stage runtime** (the 2D keyframed scene-graph player and its JSON contract, minus the mouth/eye visuals) and the Playwright frame capture | Lip sync: viseme sets, co-articulation, Rhubarb/offline viseme providers, the visemes store |
| Speech: TTS providers, voices, effects, **word timings**; sound layer; captions; credits/licence records | Swap-set conventions specific to characters (views, eyelids, hands), `swap_poses`, whole-character swaps (the swap *channel* mechanism itself is generic and stays in core) |
| Stores framework (made really `dol`-based) + generic stores; the asset library (`an.library`, ADR 0005) | `StylePack` roles that name body parts; the `an-style` specs; style lint targets |
| Render orchestration, `Renderer` protocol, assembly, ffmpeg helpers (`an/media`) | The cut-out compile passes (rig, face, visemes, blinks, gaze, swap poses, surface treatments) registered into core's compile-pass list |
| Verify protocol + generic verifiers | `verify.style`, `an character …` CLI namespace, cut-out skills, demos, corpus, bench capture, impacts |
| **New:** registries (action kinds, entity kinds, stores, compile passes, runtime visual kinds, semantic checks, md sugar, vocabulary, capability methods, CLI namespaces), discovered explicitly (`an.genres.load()`) from an `an.genres` entry point | Registers itself through that entry point on install |
| **New:** the semantic layer and MCP surface (ADR 0003), the capability registry (ADR 0002), the incremental build graph (ADR 0004) | Contributes vocabulary, capability methods and requirements |

### 3.2 What stays awkward, and the proposed answer

- **`Dialogue` carries cut-out fields** (`emotion`, `viseme_track`, `viseme_ref`). Keep them as optional fields the core ignores in v1 (the schema already tolerates unknown fields); move them to a genre extension namespace in a later, migrated, schema version. A speech line is core; its mouth is not.
- **`LipSyncProvider` also yields word timings**, which core captions need. Re-home alignment (Whisper, injected timings) as a core `WordTimingProvider`; the viseme step becomes a cut-out post-audio pass.
- **The wire shape is hash-pinned** by the bench (`scene_contract_sha256`, `runtime_sha256`). The split moves files, never renames wire fields, so no ledger row is retired.
- **`compile.py` is one 5.7k-line module.** The internal refactor (a compile-pass registry) has to land *before* the package boundary, inside `an`, with byte-identical corpus hashes as the gate.
- **The placeholder rig** is what a core-only render of an unknown entity falls back to today. In core it becomes a genre-free placeholder (a labelled box); the cut-out package registers the head-torso-limbs placeholder.

### 3.3 Order of work (expand → migrate → contract)

1. **Seams inside `an`** (no new repo, no wire change, corpus hashes unchanged): registries; move timing to `an/timing`, ffmpeg helpers to `an/media`; split `validate_semantic` into registered checks; compile-pass registry; generate the iterate prompt from the vocabulary registry.
2. **Create the genre package** (name pending, an#225), move the cut-out modules, leave re-export shims in `an` that warn.
3. **Contract:** remove the shims after one release. `pip install an` then renders data-viz-shaped scenes (paths, text, planes, camera) with no cut-out installed; `an[cutout]` (an extra depending on the genre package) keeps the old one-command install.

Persisted identifiers stay: `renderer: cutout`, the document kind names, and the genre slug `cutout_animation` already registered with `nw`.

### 3.4 The siblings, under "define once"

| Package | What it is | Relation under the split |
|---|---|---|
| `tituli` | typesetting for video (layout, runs, glyph outlines) | stays the typesetter; `an` core consumes it for text (unchanged) |
| `shaping` | 2D figures → parametric 3D objects, in the browser | its animation tracks are a hand copy of `an`'s format (ADR 0002 there), already drifting (`ease_in_out` cubic vs quadratic). Core should **publish** the track format as a JSON Schema and an easing table with reference values, and `shaping` validate against them |
| `previz` | keyframes over the state of any rendering engine → GIF/MP4 | a sibling `an` would consume as a `Renderer`; it owns no shapes. It re-implements easing with CSS names. Same remedy: one easing table with an alias map (CSS names ↔ `an` names, with the curves stated) |
| `burns` | Ken Burns films from stills | copies `an`'s camera layout and move names with different constants. Candidate consumer of a published core camera-move table |
| `walkthru` | app tours from command lists | its own IR and camera keyframes (easing strings never evaluated). Same consumer story |
| `manimkit` | agent toolkit for writing Manim | stays outside: its engine is Manim. A math-viz genre built on `an` would compile *to* Manim through a `Renderer`, and could call `manimkit`'s checks |
| `lacing`, `nw` | linked artifacts: content-addressed artifacts with provenance; dependency-tracked regeneration | the incremental-rebuild engine `an` lacks (ADR 0004) |

The `previz` research (2026-09-29) recommended that a general parametrized-animation tool be a *separate* package that `an` consumes. That does not conflict with "an is the core": `previz` animates opaque engine state (a 3D viewer's camera, a map's viewport), not drawables, so it is a renderer-side sibling. What should not be separate is the *vocabulary* they share — easing, tracks, camera moves — and that is what the core should publish.

---

## 4. Plans, done, obsolete, ahead

### 4.1 The plan lineage

| When | Plan | Proposed |
|---|---|---|
| spring 2026 | `report 0 - Text-to-Structured-Animation.md` | An agentic tool for **educational** video: the three-layer IR, a **pedagogical scene description** (function plots, morphs), an **MCP server** (`plan_scenes`, `render_scene`, `verify_animation`, `edit_scene`, `preview_frame`, …), edit routing by layer, **Manim as the sole backend** in Phase 1 |
| 2026-05-01/02 | the Phase 1–12 build | IR, stores, CLI, the cut-out runtime, audio, visemes, verifiers, Manim/Remotion/whiteboard skeletons, `an iterate`, character tools, SVG runtime, parallel render, preview, promote |
| 2026-05-02 | `Real Character Art for an — …Upgrade Plan.md` | Pose-Animator SVGs, DiceBear, a 9-mouth chart → descriptor + promote + idle/blink + atlas → multi-skin, maybe mesh deformation, Rive export |
| 2026-08-20 | **epic an#9** (cut-out animation quality) | nine waves (floor, instrument, lever, rig contract, swap channels, faces, stage, words on screen, shapes and supply) + a throughput track, six maintainer decisions, and an explicit *not covered* list (mesh, IK, other backends, multi-scene, generative art, a visual editor) |
| 2026-08-21 → 27 | `wave1_verification.md`, `wave2…7_research.md` | measured records that correct the epic where they disagree |
| 2026-09-29 | `cutout_styles_research.md` + an#163 | six masters measured; twelve ranked gaps |
| 2026-09-29/30 | the roadmap push | Wave 8–9 slices and most of an#163, outside the wave cycle |
| 2026-10-01 | the maintainer's vision; an#223, an#224, an#225, an#226 | `an` as core; cut-out as the first genre package; capability-based applicability; semantic layer defined once; incremental re-rendering; a reusable asset library |

### 4.2 Done

Waves 1–7 of an#9 in full (an#10–17, an#22–41, an#54–59, an#73–79, an#86–89, an#96–99, an#105–112). Wave 8 as built differently: text as a prop typeset by `tituli` (an#155), captions (an#175, an#200). Wave 9's first slice: stroked paths with trim, arrowheads, dashes (an#160, an#161 partly). The throughput track: canvas capture as the default (an#192). From an#163: style specs and style lint (gap 1), the sound layer (gap 2), motion presets and default easing (gap 4, an#166), surface treatments (gap 5), fade and dissolve (gap 7), turnarounds (gap 9, an#197, an#203). From end-user runs: dialogue timing (an#187), expressive voices (an#209), raster art and licence classes (an#211), from-less tweens (an#212), mouth rest (an#213), `walk` (an#214), carved-art gaps (an#220).

### 4.3 Obsolete or superseded

| Item | Superseded by | Evidence |
|---|---|---|
| Report 0's Manim-first, LLM-writes-render-code roadmap | `an` compiles a strict IR to a cut-out runtime; agent-written Manim moved to `manimkit` | an#9's *not covered* list ("all nine waves go into the one renderer"); the manimkit notes |
| Report 0's MCP server (Phase 1) | nothing — **never built** | no `mcp` anywhere in `an/` or `pyproject.toml`. The vision now asks for it again (ADR 0003) |
| The character-art plan's `an.assets.promote`, TexturePacker atlas, "add smile/neutral mouth overlays" | `an.characters.promote`; no atlas (per-seat licence); `viseme@<form>` variant sets (an#98) | `architecture_as_built.md` §10; an#9 licence table |
| Wave 3 brief (lanczos, `-tune animation`, "stop encoding twice", "key the shot cache on the renderer") | block-mean supersampling; the shots store found write-only | struck in the an#9 body; `wave3_research.md` |
| All twelve originally proposed Wave 2 metrics | the measured metric set | `wave2_research.md` |
| Wave 6's "additive offsets on rig channels" | the compile-time face solver | an#9 comment, 2026-08-24 |
| Wave 8's runtime text, bundled font, PixiJS v8 / BitmapText (Decision 4) | glyphs as compile-time SVG sprites from `tituli` | an#155; `architecture_as_built.md` §13 |
| Decision 2 (depend on `mixing` for SubRip) | a pinned mirror of `mixing.srt` in `captions.py` | `architecture_as_built.md` §0 |
| Decision 5 (flip to stepped timing when ledger and A/B agree) | the ledger half withdrawn on measurement; the flip is the maintainer's | `architecture_as_built.md` §10 item 5 |
| `an/genre.py`'s "register an `nw.renderers` Strategy" | an#9: "the federation seam is `nw.Transform`" | stale docstring; neither built |
| "`an iterate` invalidates only the affected shot, so the next render redoes only that shot" | nothing; the shots store has no read path | pillar 11; `architecture_as_built.md` §6 (§5.2 corrected with this review) |
| an#9 as the live tracker | an#163 and the push notes | an#9 comments stop at Wave 7 (2026-08-27) |
| "`an` is a leaf renderer with a small dependency set" (an#9's "what lives outside `an`") | the 2026-10-01 vision: `an` is the core of a family | an#225 |

### 4.4 Ahead

- **The framework work (new):** core/genre split (an#225, blocked on the name); capability-selected locomotion (an#224); study the masters (an#223); the asset library (ADR 0005, an#227) and migration (an#226); the ADRs in this PR; the semantic registry and MCP surface; incremental re-rendering. The last two have no issue yet.
- **Cut-out (an#163 open gaps):** text polish (3), crowds and map layers (6), dolly / shake / follow (8), silhouette mode (10), **hierarchical puppet rigs** (11), photo cut-out ingestion (12); wipes and morphs; soft-edged treatments.
- **Paths (an#161 remainder):** variable width, closed/filled shapes, arc-length sampling, a hand-drawn wobble ("boil") layer.
- **Wave 9 remainder, no issue:** nine-slice props, rope limbs, named-layer PSD/SVG/Krita import.
- **IR:** `Shot.narration` still raises (it is the OverSimplified narrator); multi-scene projects; placement-level loop override (an#94).
- **Other genres:** a real shot-to-Manim compiler; the Remotion and whiteboard stubs.
- **Small:** EXIF orientation (an#218); the emotion cassette (an#171, needs a human with a key); a quantiser-matched chroma lever (an#181).

---

## 5. Structured ↔ semantic, per core aspect

Levels as in `design_principles.md`: **(a)** typed field → formula; **(b)** words resolved to (a), either by **name lookup** (b-name, deterministic) or by an **LLM/agent** (b-LLM, recorded); **(c)** a goal verified after rendering. The cut-out aspects (art, rig, swaps, views, faces, mouth, locomotion, style) are tabled in the cut-out review.

| Aspect | Today | Should be |
|---|---|---|
| Shot timing, durations | (a) | (a); (b-LLM) "hold on her reaction a beat longer" → `pause`/`duration`; (c) pacing targets (cuts per minute, mean shot) — already measured by style lint |
| Tweens, sets, easing | (a); easing (b-name) | unchanged; one easing table published by the core (§3.4) |
| Composition (`sequence`, `parallel`, stagger) | (a) in Python; leaves only in `scene.md` | (a); (b-name) for named stagger/entrance patterns |
| Camera | (a) `keys`; (b-name) nine moves | add (b-LLM) "follow her", "slow push as tension rises" → keys; (c) framing goals ("both faces in frame", already partly `_check_framing`) |
| Staging / layout | (a) `stage` placement, layout spread | (b-LLM) "they face each other across the table" → placements; (c) overlap/occlusion lint (MoVer-style, report 0 §6.1) |
| Transitions, sound | (a); (b-name) kinds | unchanged; (b-name) for sound cues from a tagged library |
| Speech (voice, delivery) | (a) voice docs; (b-name) `[emotion]`, `{direction}` as ElevenLabs audio tags | (c) a delivery check (the emotion judge pattern) |
| Captions, text | (a) | (b-name) caption styles as presets |
| Whole-scene edits | (b-LLM) `an iterate`, one prompt over the whole IR | routed through the vocabulary registry (ADR 0003): the LLM sees only registered vocabulary, writes typed values, and its decision is recorded with provenance |
| Style | (b) an agent applies a YAML spec by hand; (a) `StylePack`; (c) style lint | a style document the compiler reads (an#163 gap 1), whose `live` settings are (a) and whose `targets` are (c) |

The structural rule (ADR 0003): **below the IR, everything is deterministic and versioned.** A (b-name) name may stay in the IR, with its vocabulary entry's version in the compile key; a (b-LLM) description is resolved at authoring time into typed values, recorded in a resolutions store, so re-rendering never re-asks an LLM; (c) is checked after rendering by a `Verifier`, whose `Finding` routes the fix to the lowest layer that can make it (pillar 10).

---

## 6. Capability-based applicability, as a general mechanism

The cut-out review lists, aspect by aspect, what exists. The general mechanism ADR 0002 proposes:

- **Affordances are derived, never hand-maintained.** `affordances(asset) → set of capabilities`, computed from the descriptor: limb pairs with pivots, a mouth slot with a viseme set (and which chart), eyelid art, pupils, each declared view, each swap set and key, rig depth, declared facts (`gait`, `rest_view`, `face_overlay`). The handful of declared facts (`face_overlay`, `rest_view`, `gait`) stay as *overrides* of the derivation.
- **Requirements are data.** Each **method** of an **aspect** (locomotion: legged walk, hem sway, hop, glide; speech: mouth chart, jaw flap, body pulse; blink: lid swap, squash, none; turn: view swap, flip, none; expression; entrance; camera follow; …) declares what it requires, its parameters with defaults, and how to *remedy* each missing requirement ("add a `view` set: `an character add-views`").
- **One matcher, three questions:** *which methods apply to this asset?*; *why does this one not, and what would make it apply?*; *resolve this aspect for this asset* (the requested method if applicable, else the style's **policy** order, else the aspect's **default chain**, whose last link requires nothing — or is a recorded no-op where the aspect makes no sense for the asset kind).
- **Every aspect has a universal default**, so nothing silently does nothing. Today two aspects fail that test: speech on a face-baked character (the mouth stays frozen; the default should be a requirement-free body or jaw pulse on the syllables) and lip sync on the placeholder rig for non-viseme sets.
- **Substitutions are recorded**, generalising the existing `asset_resolution` record and the strict-assets switch.
- **Core vs genre:** the registry, matcher and recording are core; the capability vocabulary and the methods are per genre. Data viz has the same shape: a "grow from baseline" entrance requires a bar with a baseline; a "draw on" requires a path.

an#224 (locomotion methods) is the first client; it should be built *on* this registry rather than as another private chain.

---

## 7. Other findings worth fixing (small)

- `an/adapters/cutout/easing.py::_ease`'s docstring says it "matches CSS `ease`"; it returns the quadratic ease-in-out (at t = 0.25 it gives 0.125, CSS `ease` about 0.41). Fix the docstring, or add a real CSS-`ease` Bézier under that name. The second changes every corpus scene that names `ease`.
- `architecture_as_built.md` §5.2 described `an iterate`'s cache invalidation as effective ("Then `an render` regenerates only the invalidated shots"), contradicting its own §6 and pillar 11 in `CLAUDE.md`. Corrected in the same PR as this review.
- `an/genre.py`'s docstring proposes the seam an#9 later superseded.
- Pillar 7 says "dol-backed"; no module imports `dol`. Either make the stores `dol` stores (ADR 0005 does so for the library, and its reference mode needs the renderer to stage art through the store instead of `store._root` — which ADR 0004's read recording needs too) or change the pillar.

---

## 8. Decisions for the maintainer

| # | Decision | Recommendation |
|---|---|---|
| 1 | Accept the core/genre boundary rule and the order of work (ADR 0001): seams inside `an` first, then the new package, then remove shims | **Accept.** Step 1 is valuable even if the split were never made, and it is the step that de-risks the rest |
| 2 | Where the shared **stage runtime** (the 2D scene-graph player, its JSON contract, frame capture) lives: in `an` core, or a third package | **In `an` core.** Data-viz and math-viz both need paths, text, planes and a camera; a third package adds a boundary nobody needs yet |
| 3 | Accept the capability registry with per-aspect default chains (ADR 0002), and make an#224 its first client | **Accept**, with the rule "no new private `if rig has X` chain" |
| 4 | Accept the spectrum rule "below the IR everything is deterministic and versioned: names stay in the IR with versions, LLM descriptions are resolved at authoring time and recorded" and the core vocabulary registry + MCP surface (ADR 0003) | **Accept.** Build the registry first (it de-duplicates the iterate prompt now), the MCP surface second |
| 5 | Incremental re-rendering (ADR 0004): adopt `lacing`'s `ArtifactStore` and `nw`'s freshness model behind an `an` build-graph seam, with a content-hash shot cache as the first slice | **Accept the seam and the first slice; defer the `nw` backend** until `nw`'s project-layout coupling and heavy dependencies are optional |
| 6 | The genre package's name (an#225) | the naming worker's report decides; this review only needs it to be a name the cut-out genre can keep |
