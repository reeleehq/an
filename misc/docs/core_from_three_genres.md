# The core of structured animation, inferred from three genres

**Status:** study for the maintainer, 2026-10-01. It revises ADR 0001 (still *Proposed*) and adds an addendum to `misc/docs/framework_review_2026-10.md`. The terms are those of that review's glossary (§1); the principles are `misc/docs/design_principles.md`.

**What it answers.** The October review measured `an` alone and concluded that about 45% of it is cut-out code and about 10% is clean core. That is a fact about one package. It does not say what the core of structured animation *is*, because one genre cannot show which of its parts are general. This study looks at three genres that the fleet already builds, each with a different engine, and keeps what they share:

| Genre | Package | Language, size (2026-10-01) | Engine | How a piece is authored |
|---|---|---|---|---|
| **Cut-out animation** | `an` | Python, ~52k lines; plus a 1.4k-line JS runtime | its own 2D scene-graph player (PixiJS) in headless Chromium | `scene.md` → `ir/scene.json` (a typed scene graph), actions and combinators |
| **Mathematical and explainer animation** | `manimkit` (agent kit around Manim Community Edition) | Python, ~2.2k lines of code, plus a corpus of ~450 scenes | Manim (Cairo/OpenGL, its own ffmpeg writer) | an agent writes a Python `Scene` with `self.play(...)` calls |
| **View-state animation** (a camera or any engine parameter moving between captured states) | `previz` (private TypeScript package, v1) | TypeScript, ~7.1k lines | any engine behind an adapter (WebGL viewer, chart, map, a built-in demo rasteriser) | a sequence of captured keyframes, or a **formula** that generates one |

Three smaller siblings are used as further evidence where they bear on a concept: `burns` (Ken Burns moves over a still; Python with a TypeScript port, pinned by golden vectors), `walkthru` (app tours from command lists; a live, non-seekable engine), and `shaping` (2D figures to parametric 3D objects; its animation tracks copy `an`'s format, and its app now animates through `previz`).

Nothing in those repositories was changed. Facts about Manim itself are from its public API as `manimkit` uses it.

---

## 0. Findings in one page

1. **The three genres share one evaluation model, and only one.** Every genre that can answer "what is on screen at time *t*" does it the same way: a set of **addressed properties**, each with a **field kind** that picks its interpolator, keyed over time with **easing**, flattened to absolute times, and evaluated by a pure function `at(t) → state`. `an` calls the result a `Pose` (`(target, property) → value`); `previz` calls it a view state returned by `reel.at(t)`; `burns` calls it `BurnsPath.evaluate(t)`. This **timing kernel** is the heart of the core, and today it is implemented five times: in `an` (Python and the JS runtime, bit-for-bit), in `previz` (TypeScript), in `burns` (Python and TypeScript) and in `shaping` (a copy of `an`'s track format).
2. **`previz` is ahead of `an` on the kernel; `an` is ahead on everything around it.** `previz` declares field kinds (seven: number in linear or log space, angle on the shortest arc, vector, quaternion, OKLab colour, orbit, discrete), publishes a JSON Schema and golden vectors, and states its engine contract as a capability ladder. `an` decides interpolation by the runtime type of the value (number lerps, anything else holds), has two kinds, and has no published schema. `an`, in turn, has what `previz` deliberately left out: the scene document and its migrations, shots and film assembly, narration, captions and sound, verifiers, stores, and a semantic layer in the making. The core should take the kernel's *contract* from `previz` and the rest from `an`.
3. **Manim does not fit the kernel, and that is informative.** Manim's state is a set of Python objects mutated by `play` calls; there is no address, no `at(t)`, and no way to seek. Time exists only as the cumulative `run_time` of the `play` and `wait` calls. So Manim joins the core **as a back-end that renders a whole shot** (it owns its clock, like any offline renderer), not as an engine the core can drive frame by frame. What the core gives a Manim shot anyway is large: narration, captions, sound, assembly with other shots, verification, caching, the library and the semantic layer.
4. **The renderer protocol needs three tiers.** `an`'s `Renderer` (shot → mp4) is the outer one, and Manim lives there. Inside it, a **seekable engine** (`state` or `t` → frame; `an`'s stage runtime, `previz` engines, `burns`) lets the core own the clock, the capture loop and the encoder. A **live engine** (`walkthru` driving an app, `previz`'s unbuilt `live` rung) can only be played forward and recorded. `previz` already reads an engine's tier from which members it implements, which is ADR 0002's "affordances are derived, never declared", applied to engines.
5. **Verification is shared in shape and split in practice.** `manimkit` checks rendered geometry after every `play` (text cut off, text overlapping text, text crossed by a shape, shapes off-screen) and tiles the settled beats into a contact sheet an agent looks at. `an` checks the IR (framing, durations, references) and measures pixels (bench, media QA, vision LM) but never reads the bounds of what it actually drew. `previz` verifies its kernel by golden vectors. The core needs all three families behind the one `Verifier`/`Finding` protocol, and an engine needs an optional `bounds` member for the geometric one.
6. **The semantic layer has the same entry shape in all three.** A `previz` **formula** (`id`, `title`, one-sentence `description`, a Zod parameter schema with defaults, `build(params, base) → sequence`), an `an` motion preset (`play: walk` with `args`), and a `manimkit` corpus scene (a title, `tags:`, a description, runnable code) are each a named, parametrised, described recipe that expands to plain timeline content. ADR 0003's vocabulary entry should be designed to be isomorphic to the `previz` formula, so one registry generates the iterate prompt, the MCP tools and the skill docs for every genre. `manimkit`'s example retrieval (BM25 with a `scorer=` seam) is the (b-LLM) resolver aid the other genres lack.
7. **What changes in ADR 0001.** (a) The boundary test is now three genres, not hypothetical ones. (b) The **timing kernel is a cross-language contract** (JSON Schema plus golden vectors) with two implementations, Python in `an.timing` and TypeScript in `previz`, instead of code extracted from `adapters/cutout`. Its contract covers both levels `an` evaluates today, the authored flat timeline and the compiled tracks, clips and channels. (c) **No engine is core**: the 2D stage runtime stays in the `an` distribution as `an.stage`, the default engine, behind an optional extra and a firewall test, instead of being "in the core" (ADR 0001 Decision 5 and the review's §8 Decision 2 both change). (d) Manim plugs in first as an opaque-source shot renderer via `manimkit`, which is the first test that the core renders without the cut-out genre installed. (e) Entity kinds declare **property spaces**, which is what makes the open IR of Decision 2 checkable.

---

## 1. The three pipelines side by side

| Stage | Cut-out (`an`) | Explainer (Manim + `manimkit`) | View state (`previz`) |
|---|---|---|---|
| Intent | `scene.md`: shots, dialogue, actions in a fenced block | a storyboard table of beats with seconds per beat (the `manimkit` skill's step 1) | the user captures views in an app, or picks a formula and its parameters |
| Document | `ir/scene.json`: `SceneIR` → `Shot` → entities, actions, dialogue; versioned, migrated per kind | none: the Python `Scene` file is the only artifact | `previz.sequence` JSON: `space`, `defaults`, `keyframes`; integer `version`, migration registry |
| Retrieval aid | name lookups (presets) | BM25 search over ~450 working scenes; `show` prints one to adapt | the formula list |
| Static check | `an validate` (semantic checks on the IR) | `manimkit lint` (removed APIs, ManimGL names, undefined names) | `compile` (unknown fields, undeclared fields listed, values checked against kinds) |
| Evaluation | `flatten` → channels → `evaluate_timeline(t)` (Python spec, JS runtime) | none outside Manim: each `play` interpolates its mobjects over `run_time` with a `rate_func` | `compile(sequence)` → reel → `at(t)` |
| Engine | 2D stage runtime: `anLoadScene`, `anSetTime(t)`, canvas capture | Manim's renderer, frame after frame | `Engine.render(state)` or `apply` + `capture` |
| Capture and encode | Playwright, supersample, shutter, ffmpeg with pinned BT.709/x264 flags | Manim's movie writer: partial movie files per `play`, joined by ffmpeg | sinks: GIF, MP4/WebM (WebCodecs or an ffmpeg pipe), PNG sequence; dwells collapse |
| Film | `an.assemble`: shots, transitions, sound, captions | one video per scene (or per section) | one take per reel |
| Rendered check | media QA, vision LM, bench metrics | layout probe after each beat, contact sheet, duration, LaTeX log excerpt | golden vectors of `at(t)` |

---

## 2. Concept by concept

Each subsection says how the genres do it today, what they share, where they disagree, and the recommended **core contract**. "Core" means `an` after the split; "genre" means `cutan` (the cut-out package, an#225) or a later genre package.

### 2.1 Document model and versioning

| `an` | Manim / `manimkit` | `previz` | Others |
|---|---|---|---|
| Pydantic `SceneIR`, `extra="allow"` on read, omit-when-unset serialisers, a semver `version`, migrations keyed **per document kind** (`register_migration(kind, src, dst)`) | the Python file; `manimkit` records only a hash of it (`source_hash`, "UNCHANGED since the last render") | Zod schema, committed JSON Schema with a drift test, `format` + integer `version`, a migration map | `burns`: `SPEC_VERSION = 1`, snake_case, "never change `toDict()` field names"; `walkthru`: Pydantic first, JSON Schema → Zod codegen, camelCase, `extra="forbid"` |

**Shared:** a self-describing envelope (a kind or format name plus a version), a migration path on read, and a schema that another language can check.

**Disagree:** semver string vs integer; Pydantic-first vs Zod-first; snake_case vs camelCase; tolerant vs strict reads. Manim has no document at all.

**Core contract.** Every persisted document has `{kind, version}` and a migration chain in `an.ir.migrate` (already the right shape, keyed per kind). Each document kind commits a JSON Schema generated from its model, with a drift test; the authoring language is a per-kind choice, and the JSON Schema plus golden vectors is the contract, never one language's types. Casing is per document kind; the shared vocabulary (kind names, easing names, units) travels as *values*, so casing never collides. Tolerant reads (`extra="allow"`) for documents people edit; strict for machine-only ones. A Manim shot's document is its `Shot` in the scene IR, with the source file referenced by content hash, so the scene, not the code, is versioned.

### 2.2 Entities and property-path addressing

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| `charlie/left_arm:rotation`: a slash path to a node, a colon, a property; entities are `AssetRef`s of a closed set of kinds; the transform vocabulary (`TRANSFORM_PROPERTIES`) is one fixed list | Python variables pointing at `Mobject`s; nothing is addressable from outside the code | a view state is one nested JSON mapping, addressed by dotted paths (`camera.azimuth`); the engine is the one implicit entity | `shaping`: a property path into its `Design`; `walkthru`: element locators, not property paths |

**Shared:** where a genre can be edited after the fact, it is because a value has a stable address. Manim's lack of addresses is exactly why an agent-written Manim scene can only be edited by rewriting code.

**Disagree:** slash-and-colon vs dotted; a fixed property list per node vs an open nested state.

**Core contract.** One grammar: `<entity>[/<node>…]:<field>[@<qualifier>]`, where `<field>` may be a dotted path. The node path is `an`'s; the `@qualifier` is what `an` already emits for variant swap sets (`viseme@happy`); the dotted field path is how a `previz` view state fits, as the property space of one entity (`view:light.color`). A dotted segment names a declared **field**, never a member *inside* a composite kind: `previz` interpolates an `orbit` as one value and does not tween `azimuth` on its own, so `view:camera.azimuth` is addressable only if the space declares `camera.azimuth` as its own field. An **entity kind** registers its **property space**: property pattern → field kind (§2.3), plus three things the generic validator needs: **aliases and write groups** (`rotation` and `rotation_rad` write the same thing; the swap sets of one visual share a group, `_SHARED_WRITES` and `write_group` in `an/adapters/cutout/timeline.py`), a **unit or coordinate space** per numeric field (stage pixels, Manim scene units, `burns`' normalised window), without which moving a captured camera from one engine to another is meaningless, and the **display / build** split of §2.14. `an`'s `TRANSFORM_PROPERTIES` becomes the property space of the stage engine's `node`; a `previz` `Space` is a property space as it stands; a future Manim genre registers the properties its compiler can drive (`position`, `color`, `opacity`, `points`). `root` is a reserved node (camera channels already lower onto it in `runtime.js`). Validation of an action's target against the space is then generic, which is what ADR 0001's open IR needs: with `kind: str` in the schema, the space is what still catches a typo.

### 2.3 Field kinds, keyframes, tweens and easing (the numeric-vs-categorical rule)

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| Two kinds chosen by the **runtime value**: numbers lerp through the leaving keyframe's easing; anything else holds `a` on `[a.time, b.time)` and switches at `b.time`, compared on time, never on an eased parameter; `bool` refused; `tint` authored as one value and expanded to three sRGB scalars | each animation interpolates points and colours componentwise (RGB) between a start and a target copy, through a `rate_func` (default `smooth`); `Transform` first aligns point counts so shapes can morph; adding or removing a mobject is the only discrete change | seven **declared** kinds; "the declared kind picks the interpolator, runtime values never do"; undeclared fields are discrete; discrete values switch when normalised time `tau >= switchAt` (default 0.5), on time, never the eased progress | `burns`: rectangles lerped in `(x, y, w, h)`; `shaping` (through `previz`): orbit camera, log zoom, OKLab colours |
| Easing: named polynomials (`ease`, `ease_in`, `ease_in_out` quadratic, `step`) or a cubic Bézier (Newton, 8 steps); the easing leaves a keyframe | `rate_func`: `smooth`, `linear`, `there_and_back`, `rush_into`, … | CSS Easing names with the exact CSS control points, `cubic-bezier`, `steps(n, …)`; Newton then bisection; per-transition and per-field timing | `burns`: CSS names, bisection, one easing for the whole path; `shaping`'s own copy: cubic `ease_in_out` |

**Shared:** the split between values that interpolate and values that hold, and the rule that the hold never switches on an *eased* parameter (an overshooting curve would otherwise flip it twice). `an` and `previz` reached that rule independently. They differ one step further: `previz` switches on the raw normalised time `tau = (t - start) / span`, which `an` rejected after an#86 because that division can round up to 1.0 while `t < b.time`; `an` compares `t >= b.time` with no arithmetic at all.

**Disagree:**
- **Where the kind comes from.** `an` infers it from the value; `previz` reads a declaration. Declaration is better: it is what lets a number be an angle (shortest arc) or a log-space zoom, and it is what a property space (§2.2) provides anyway.
- **When a discrete value switches.** `an` at the end of the segment, `previz` at the middle by default (0.5). Both are legitimate: a replacement drawing must not appear before its key (cut-out), while a toggled layer between two captured views reads best at the middle of the move.
- **Colour.** `an` lerps sRGB components; `previz` mixes in OKLab; Manim lerps RGB.
- **Easing names.** The same word means different curves: `an`'s `ease` and `ease_in_out` are the quadratic ease-in-out (0.125 at t = 0.25), CSS `ease` is 0.41 and CSS `ease-in-out` 0.129 there; `shaping`'s `ease_in_out` is cubic.
- **Where easing lives.** On the segment (`an`, `previz`) or on the whole path (`burns`, whose `evaluate(t) == geometry(easing(t))`); `walkthru` keeps easing out of its schema altogether, as renderer domain.

**Core contract.**
- A **field-kind registry** (`an.timing.kinds`), seeded with `previz`'s seven kinds, each parametrised: `number(space=linear|log)`, `angle(unit, wrap)`, `vector`, `quaternion`, `color(space=srgb|oklab)`, `orbit`, `discrete(switch_at)`. Genres add kinds (a Manim genre's `points`, morphing two outlines after aligning their point counts).
- **Discrete is defined on time, not on a ratio.** A discrete segment from `a` to `b` shows `b` iff `t >= a.time + switch_at · span`, and `switch_at == 1` is evaluated as `t >= b.time` directly, with no arithmetic, which is `an`'s an#86 rule. The shared vectors include the boundary case where `(t - a.time) / span` rounds to 1.0 while `t < b.time`; `previz` changes its comparison to match (a one-ULP change at its boundaries).
- **Declared kinds only.** An undeclared property is `discrete`, as in `previz`. `an`'s current behaviour is reproduced by declaration: the stage node's transform properties, `tint_r/g/b` and the camera's `x`, `y`, `zoom` and `rotation` are plain `number` (linear), and swap channels, including every `@`-qualified set (pattern `*@*`), are `discrete(switch_at=1)`. `tint` itself stays what it is today, an authoring sugar that the stage compiler expands into three numeric channels (`_expand_tint_actions`) before any channel exists, so the wire shape does not change; `color(space=…)` is for new genres and new engines, not a re-declaration of `tint`.
- **One easing registry**, versioned per ADR 0003. Hyphenated CSS names mean exactly the CSS curves; `an`'s underscore names stay as legacy entries with their stated polynomial curves (never silently aliased to CSS); Manim's rate functions are entries too, so a scene can be rendered on the stage engine or by Manim with the same curve. `cubic-bezier(...)` and `steps(n, position)` are parametrised entries. The **solver** is part of an entry: `an`'s 4-tuple Bézier (8 Newton steps, no bisection) and `previz`'s `cubic-bezier` (Newton, then bisection to 1e-12) do not agree to 1e-9 for every control point, so `an`'s stays a named legacy solver until its pixel goldens are re-blessed under the stricter one.
- **Segment easing is canonical** (the curve of a segment between two keys); a path-level timing remap (`burns`) and per-field timing (`previz`) are front-end features that lower to segment easings or a time remap. Whether the easing is written on the leaving key (`an`) or on the arriving transition (`previz`) is a front-end choice; the flat form stores it on the segment.
- **Stepping** (`step_hz`, animating on twos) stays separate from easing: it resamples the evaluated curve onto a grid, it is not a curve.

### 2.4 Composition, authoring front-ends and the flat timeline

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| `sequence`, `parallel`, `delay`, `loop` over `set`, `tween`, `play`, `expression` → `flatten` → `FlatAction(start, end, action)` with absolute seconds; renderers see only the flat form | `self.play(a, b)` is a parallel block; consecutive `play`s are a sequence; `AnimationGroup`, `Succession`, `LaggedStart(lag_ratio)` (a **stagger**); `wait` is a delay; updaters derive values from other values | an ordered list of keyframes; each is reached by a **transition** (duration, timing, route, per-field overrides) and held for a **dwell**; no absolute times stored; **formulas** generate sequences; `compose` runs formulas one after another or on disjoint fields at once | `walkthru`: steps with durations, cues anchored to steps (no absolute time in the document); `burns`: two or more keyframes in normalised time |

**Shared:** relative authoring, absolute evaluation. Every genre authors with relative durations (a sequence of beats) and evaluates against absolute time. Every genre also has a *named, parametrised recipe* that expands to plain content (presets, formulas, Manim's animation classes such as `GrowFromEdge` or `Indicate`).

**Disagree:** property-based authoring (`an` tweens one property at a time) vs state-based authoring (`previz` captures a whole state and carries omitted fields forward); a stagger combinator exists in Manim and `previz`'s `compose`, not in `an`; derived values (Manim updaters, cut-out "attach this prop to that hand", inverse kinematics) exist only in Manim.

**Core contract.**
- **Two canonical levels, both in the contract.** `an` already has them, and the kernel needs both:
  - the **authored flat timeline**: `an`'s `FlatAction` list, generalised to `(start, end, address, change)` where a change is `set` or `tween(from?, to, easing)`. This is the level `shaping` copied; the core publishes it as `timeline.schema.json` so the copy can be validated instead of trusted;
  - the **compiled evaluation form**: tracks of placed clips (start, duration, speed, recorded blend ramps), clips with a loop mode (`once`, `loop`, `ping_pong`), channels of keyframes (`an/adapters/cutout/{timeline,clip,channel}.py`), with `an`'s evaluation rules: a clip is **active** on `[start, end]` inclusive, later wins by track order then clip order; an ended clip's final value is **held**; a property nothing has started is **at rest** and absent from the result; write groups keep only the most recently written key. This is what `runtime.js` evaluates and what the golden vectors exercise; the core publishes it as `compiled.schema.json`.
- **Several front-ends lower to it**, and nothing downstream knows which one was used: `an`'s combinators; a **keyframe sequence** front-end (`previz`'s model: each transition becomes a tween of every field that changes, each dwell a hold; carry-forward and back-fill happen before lowering); **beats** (Manim-style `play`/`wait` blocks, which are `parallel` inside `sequence`); and **recipes** (presets, formulas), which expand to any of these.
- Add **`stagger(lag, *actions)`** as a core combinator (Manim's `LaggedStart`, `previz`'s compose, the cut-out crowd entrance).
- Reserve, do not build, **derived channels**: a property computed from other properties' values after channel evaluation (a pure function of `value_of(address)` terms), evaluated inside `at(t)` so seeking still works. Manim needs them for every tracker-driven graph and label. Inverse kinematics and "attach this prop to that hand" are *not* kernel features: they need rig geometry, so they stay stage or genre compile passes (cut-out review §1.2, "Constraint"). The word "expression" is avoided here because `ExpressionAction` already means a face.

### 2.5 Evaluation and the time model

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| `Seconds = float` at the IR; `frame_count = max(1, round(duration * fps))` per shot; frame *k* at `k / fps`; `FrameClock` adds shutter and jitter; the runtime seeks by `anSetTime(t)` | time is the cumulative `run_time` of `play` and `wait`, each rounded up to whole frames (hence `manimkit`'s rule: durations in multiples of 0.2 s so drafts and finals have the same length) | seconds; frame *k* at `t = k / fps` on an integer clock; segment frame counts rounded **cumulatively** so the total never drifts; segments half-open; clamped outside `[0, duration]` | `burns`: normalised `t` in [0, 1], duration given at render time; `walkthru`: integer milliseconds, relative to anchors |

**Shared:** float seconds as the unit people write, an integer frame clock underneath, `k / fps` sampling.

**Disagree:**
- **The frame clock.** `an` samples exactly `t = k / fps` with `frame_count = max(1, round(duration · fps))`. `previz` rounds each segment's bounds to frames cumulatively and samples each segment at its own normalised time, so every keyframe lands on a frame exactly and every sample is within half a frame of `k / fps` (`src/core/frames.ts`). Manim rounds each animation up to whole frames, and drifts unless durations are frame multiples.
- **What `at(t)` returns.** `an`'s pose is **sparse**: a property no clip has started is absent, and the node shows its own built value. `previz` returns a **total** state: omitted fields carry forward, and fields that first appear later are back-filled into earlier keyframes.
- **Boundaries.** Within one `an` channel, keys are half-open (`[a.time, b.time)`); across clips, a clip is active on `[s, e]` inclusive and a tie at `t == e` goes to the later track or clip. `previz` segments are half-open throughout.
- Normalised time (`burns`) and milliseconds (`walkthru`) are front-end units.

**Core contract.** Seconds (float) at every document boundary. `at(t)` is pure and clamped. The kernel's clock is `an`'s: frame *k* at `k / fps`, `frame_count = max(1, round(duration · fps))`; `previz`'s boundary snapping is a sampler option of the front-end, not the kernel (adopting it would move every `an` pixel golden). `at(t)` is **sparse plus a rest state**: the result lists only the properties some clip has written, and each entity's property space supplies its rest values; `previz`'s back-fill lowers to "rest = the first keyframe's value", and a total state is `rest` overlaid with the sparse result. Boundaries follow `an`'s two rules (half-open keys inside a channel; inclusive clip ends resolved by later-wins), and the vectors include a cross-track boundary case. A renderer that owns its clock (Manim) *produces* the duration rather than receiving it (§4.2). Rational time stays where pillar 5 puts it: audio.

### 2.6 Camera

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| `Camera(move, keys)`: `CameraKey(at, x, y, zoom, rotation, easing)`; nine named moves are sugar over keys ("one code path, two front doors"); planes add parallax | `MovingCameraScene`: the camera frame is a mobject (position, width) animated like any other; `ThreeDScene`: `phi`, `theta`, distance, ambient rotation | the camera is just fields of the view state; the `orbit` kind interpolates azimuth on the shortest arc, elevation clamped, distance in log, target componentwise; turntable is a formula | `burns`: a normalised crop rectangle and eight moves with different names and magnitudes; `walkthru`: focus rectangle in CSS pixels plus zoom, rendered as cuts |

**Shared:** a camera is a set of animatable properties plus a library of named moves. Manim and `previz` both treat it as an ordinary entity; only `an` gives it a special schema type.

**Disagree:** zoom lerped linearly (`an`, `burns`) or in log space (`previz`); 2D framing vs 3D orbit; three move tables with overlapping names (`push_in` exists in `an` and `burns` with different magnitudes).

**Core contract.** The camera is an entity whose property space the core ships in two standard forms: a **2D framing camera** (`x`, `y`, `zoom` as `number(space=log)`, `rotation` as `angle`) and a **3D orbit camera** (`orbit`). Named moves are vocabulary entries that expand to keys (one table, ADR 0003; `burns` and `walkthru` consume it rather than keep their own). `an`'s `Shot.camera` stays as the authoring sugar and lowers to that entity's channels; the cut-out genre declares its zoom and rotation as plain `number` so its output does not change, and new genres get log zoom and shortest-arc rotation by default.

### 2.7 The renderer protocol: whole-shot, seekable, live

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| `Renderer` Protocol (`name`, `supported_renderers`, `can_render(shot)`, `render(shot, ctx) → RenderResult` with an mp4) and a name-keyed registry; inside the cut-out renderer, a seekable engine (`anSetTime(t)`, then capture) | a whole-scene batch renderer that owns its clock; `manimkit.render_check` runs it in a child process (a crashing or hanging scene cannot take the caller down) and returns a report | `Engine<S>`: `apply` required; `render`, `capture`, `read`, `animateTo`, `element`, `project`, `space`, `traits` optional; **capabilities are read from which members exist**; a capture ladder `engine` → `region` → `native` (player only) → `live` (never a silent fallback) | `burns`: `RenderBackend` registry (`pillow`, `ffmpeg`); `walkthru`: nine ports, a real-time player and recorder |

**Shared:** a protocol plus a name-keyed registry, in every package; the core never imports a back-end.

**Disagree:** who owns the clock. Manim owns it; `an`'s runtime and `previz` engines let the caller own it; `walkthru`'s live app cannot be sought at all.

**Core contract.** Three tiers, each a protocol:
1. **`Renderer`** (exists): shot → media file plus provenance. Every back-end is reachable through it, so assembly, captions, sound and caching treat all shots alike. Manim lives here.
2. **`Engine`** (new, `previz`'s meaning of the word): a seekable engine that turns a state, or a time over a loaded document, into a frame. The core supplies `frame_stage_renderer(engine)`, which turns any engine into a `Renderer` using the core's `FrameClock`, capture loop, supersampling and encoder. `an`'s stage runtime becomes the first `Engine`; a `previz` engine reached through a browser page is the second (§4.3).
3. **Live engine**: `apply`, `settle`, `capture` in real time, with constant-rate resampling (`walkthru`'s recorder). Declared, not built in the first slice.

An engine's tier and features (alpha, `bounds` for layout checks, `project` for anchored overlays) are derived from the members it implements, never from a flag (§2.13). Engines come in two drive modes, both legal: **time-driven** (the engine receives the compiled channels and a time, and evaluates them itself, as `runtime.js` does) and **state-driven** (the core evaluates `at(t)` and hands the engine a state, as `previz` does). Time-driven engines must be conformance-tested against the kernel's golden vectors, so a time-driven engine exposes a read-back member, `state(t)`, returning the state it evaluated; `runtime.js` is tested today by extracting its functions and comparing them bit for bit with the Python (the parity tests), which is the same check reached from the inside.

### 2.8 Capture and delivery

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| Playwright canvas capture (`toDataURL`, ~10 ms per 1080p frame), block-mean supersampling, shutter samples, ffmpeg with pinned BT.709, x264 and faststart flags; `an.assemble`: transitions, sound mix with ducking, burned or sidecar captions; GIF recipe in the demo builder | partial movie files per `play`, joined by ffmpeg; `-ql` / `-qm` / `-qh` presets; sections | sinks: GIF (`gifenc`), MP4/WebM via WebCodecs and Mediabunny in the browser, an ffmpeg pipe in Node, PNG; dwells collapse to one frame with a long delay | `burns`: moviepy, ffmpeg filter graph with a measured sample ladder, WebCodecs; `walkthru`: screencast JPEG → constant-rate schedule → ffmpeg, TV range, GIF palette graph |

**Shared:** the same encoder lessons were learned three times (TV range, BT.709 tagging, even dimensions, faststart on every leg, a 12 fps / 480 px palette GIF with no dithering for flat art).

**Core contract.** `an.media` holds the frame **sinks** (MP4 with the pinned argv, GIF with one palette recipe, PNG sequence) and the **film assembly**. Assembly consumes media from any `Renderer`, so a Manim shot and a cut-out shot can share a film with a dissolve between them. Browser-side sinks (WebCodecs) belong to the TypeScript side (`previz`) and are not duplicated in Python.

### 2.9 Audio and narration

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| TTS providers, voices, effects, content-keyed audio, **word timings** (`WordTimingProvider`), `Dialogue` and `Narration`, captions, sound cues, ducking; visemes and co-articulation for mouths | `Scene.add_sound`; the community plugin `manim-voiceover` sets each `play`'s `run_time` from the spoken duration, with bookmarks inside the text; `manimkit` does not touch audio | none (out of scope for v1) | `walkthru`: narration segments anchored to steps, with TTS and word timings; `burns`: a film-level audio track |

**Shared:** narration is how explainers and tours are paced. In the explainer genre the voice usually *sets* the timing: a beat lasts as long as its sentence.

**Disagree:** absolute placement (`an`'s `Dialogue.start`) vs anchoring to a step or beat (`walkthru`, `manim-voiceover` bookmarks).

**Core contract.** Speech, voices, word timings, narration, captions, sound and ducking are core (as ADR 0001 already says). Add one thing the explainer genre needs: **timing from audio**, a constraint that sets a beat's duration from its narration line, and anchors (an action starts at word *n* of a line). It is a **resolution pass** that runs after audio synthesis and writes the resolved durations and start times *into* the IR (as `sync` writes `scene.json`), with the audio digests it used, so `flatten` stays a pure function of the IR (pillar 3) and never reads a TTS provider's output. Mouths stay genre.

### 2.10 Verification and the bench

| `an` | Manim / `manimkit` | `previz` | Others |
|---|---|---|---|
| `Verifier` + `Finding(severity, ir_path, description, suggested_fix)`; IR checks (`validate_semantic`, `_check_framing`, durations); media QA (silence, frozen frames); vision LM on sampled frames; style lint against measured targets; the bench (decoded-pixel goldens, contract hashes, metrics ledger) | static lint of the code; a **layout probe after every beat** on the real mobjects' bounds (cut-off, overlap, cramped, text-on-shape, off-screen); a **contact sheet** of the settled beats for an agent to look at; the real duration; concise errors pointing at the user's lines | golden vectors (`compile(sequence).at(t)` within 1e-9); compile warnings for undeclared fields; "a declared field nothing reads is a bug" | `burns`: golden vectors across two languages plus a pixel-box vector; `walkthru`: firewall and guardrail tests |

**Shared:** three families of checks, each present somewhere and none present everywhere: **contract** checks (does the kernel compute the agreed values?), **static** checks (is the document or code well-formed?), **rendered** checks (does the result look right: geometry, pixels, a model's judgement).

**Core contract.** One `Verifier`/`Finding` protocol (exists), with the `Finding` pointing at an **address**, an IR path, or, for an opaque source such as a Manim scene file, a **source location** (`file:line`, which is what `manimkit` reports), so a fix routes to the lowest layer that can make it (pillar 10). The core ships: the contract checks (golden vectors for the kernel); the IR checks that are genre-free; a **geometric layout verifier** that reads per-beat bounds `(address, box, role: text|shape)` from any engine that implements an optional `bounds(state)` member (`manimkit`'s probe is the Manim implementation of the same check; `an`'s stage runtime can report PixiJS bounds); the **contact sheet** as a standard artifact of every render (frames at beat ends, labelled with time), which is what an agent is told to open; media QA; the vision-LM verifier; and the generic bench modules (decoded-pixel comparison, ledger, contract hash, metrics). Cut-out style lint and the cut-out corpus go with `cutan`.

### 2.11 The semantic layer, the vocabulary and MCP

| `an` | Manim / `manimkit` | `previz` | Others |
|---|---|---|---|
| module-level dicts (`motion.PRESETS`, expression presets, `CAMERA_MOVES`, easings); `an iterate` with a hand-written prompt; ADR 0003 proposes one versioned registry and a curated MCP surface | a corpus of ~450 scenes with headers (title, `tags:`, description), BM25 search with a `scorer=` seam, an agent skill teaching the loop | **formulas**: `id`, `title`, a one-sentence `description` written for a person or an agent, Zod `params` with defaults, `build(params, {base, space}) → sequence`; **command records** `{id, title, params, execute}` that "a registry projects" to MCP | `burns`: named moves with a `RESOLVER_IMPL_VERSION`; `shaping`: genres and transforms as objects with Zod parameter schemas and generated dials |

**Shared:** a named, versioned, described, parametrised recipe whose parameters are a schema with defaults; plus a command list that every surface (CLI, MCP, UI) is projected from.

**Disagree:** expansion at authoring time (`previz` formulas may be kept as a call or expanded; `manimkit` code is copied and adapted) vs at compile time (`an`'s presets stay names in the IR). ADR 0003 already settles it: names may stay in the IR with a version; descriptions are resolved before the IR.

**Core contract.** ADR 0003's vocabulary entry, shaped to be isomorphic to a `previz` formula: `id`, `version`, `kind` (action, preset/formula, easing, camera move, entity kind, field kind), `title`, `description`, `params` (JSON Schema with defaults), `examples`, `requires` (capabilities, §2.13), accepted spectrum levels, and `expand(params, context) → timeline content`. JSON-describable, so a TypeScript package can export its formulas into the registry and an MCP client sees one list. Add **example corpora** as a first-class resolver aid: `manimkit`'s search (dependency-free BM25 over titles, tags and identifiers, `scorer=` seam) is generic code; each genre contributes a corpus, and a (b-LLM) resolver retrieves examples before writing typed values. Commands are data (`previz`'s record shape, `an`'s `_dispatch_funcs`), and MCP is one projection of them.

### 2.12 Storage and the asset library (ADR 0005)

| `an` | Manim / `manimkit` | `previz` | Others |
|---|---|---|---|
| per-project mall of hand-written `MutableMapping`s; ADR 0005 designs a cross-project library: flat ids, immutable versions, content-addressed blobs, derived affordance facets | the shipped corpus (curated, gallery with attribution, harvested API docstrings) is a read-only library of examples; renders go to a per-file output folder | "not a seam": the document is JSON and the caller stores it | `shaping`: a zodal store seam (localStorage → S3/Supabase); `walkthru`: `AssetRef(uri, mime, rights)` |

**Shared:** reusable things with provenance and rights (`manimkit`'s gallery `NOTICE.md`, `walkthru`'s `AssetRights`, `an`'s `AssetSource`).

**Core contract.** ADR 0005 unchanged in mechanism. Its kinds widen: an explainer genre's reusable assets are **scene templates, examples, LaTeX snippets and colour themes**; a view-state genre's are **sequences, formulas and engine spaces**. **Examples** are a library kind (searchable, versioned, with rights), which is where `manimkit`'s corpus would live if it joined. The library stays in the core.

### 2.13 Capability registry (ADR 0002)

| `an` | Manim / `manimkit` | `previz` | Others |
|---|---|---|---|
| one-off checks inferring what a rig affords (`play_problems`, `gait`, `resolve_mouth_set`, …); ADR 0002 proposes one registry with derived affordances and default chains | **environment** capabilities: `manimkit check` reports what is installed (manim, LaTeX, `dvisvgm`) and how to install it; `--no-latex` filters the corpus to scenes that render without TeX and makes any LaTeX use fail | **engine** capabilities read from implemented members ("a flag can never disagree with the code"); formulas apply to a state that has the fields they address | `burns`: `on_aspect_mismatch`; `walkthru`: an unmet readiness gate aborts the run |

**Shared:** a recipe *requires* something of what it is applied to, and the answer is *derived*, never typed by hand.

**Core contract.** ADR 0002's registry and matcher, with **three subjects** instead of one: an **asset** (what its rig and art afford), an **engine or renderer** (which tier, `bounds`, alpha, which field kinds it can draw), and the **environment** (LaTeX, a browser, ffmpeg, an API key). A vocabulary entry's `requires` can name any of the three (`requires: [env.latex]` for a TeX-typeset label; `requires: [space.orbit]` for turntable; `requires: [limbs.legs]` for a legged walk). The default chains and recorded substitutions apply to all three: no LaTeX, so a `MathTex` label falls back to plain text with a recorded substitution, which is `manimkit`'s `--no-latex` path generalised.

### 2.14 Incremental re-rendering (ADR 0004)

| `an` | Manim | `previz` | Others |
|---|---|---|---|
| audio is content-keyed; the shot store is write-only; ADR 0004 proposes a digest-keyed build graph | Manim caches a partial movie file per `play`, keyed by a hash of the call and the mobjects, and rebuilds only the changed ones (unless caching is disabled); `manimkit` reports whether the source changed since the last render | dwell frames collapse (identical frames are not recomputed); no cache across runs | `shaping`: display fields (colour, camera) never change the build key, so recolouring does not rebuild geometry; `burns`: `RESOLVER_IMPL_VERSION` ("a lock, not a receipt") |

**Shared:** content keys salted with an implementation version, and a split between inputs that change the build and inputs that only change the display.

**Core contract.** ADR 0004 unchanged in mechanism. The cache unit depends on the renderer tier: a whole-shot renderer (Manim) is cached per shot, keyed on the scene file's content hash, the Manim version and the render knobs, and keeps its own finer cache inside; a seekable engine can later re-capture only part of a shot, because `at(t)` is pure; but under held semantics (§2.4) an edit to a clip changes every later frame that holds its final value, so the re-captured range for an address runs from the edit to the end of the shot, not just the edited span. Adopt `shaping`'s split explicitly: each property space marks properties as **display** (re-evaluate, never re-compile) or **build** (re-compile).

### 2.15 Genre registration

| `an` | `manimkit` | `previz` | Others |
|---|---|---|---|
| `an/genre.py` declares `cutout_animation` to `nw` as *planned*; ADR 0001 proposes `an.genres` entry points and registries | none (a standalone kit) | none (engines are adapter objects passed in) | `shaping`: a genre is one plain object (`id`, `title`, input slots, a Zod `params`, `build`), and "a new genre is one file" |

**Core contract.** ADR 0001's explicit discovery (`an.genres.load()` reading the `an.genres` entry point), with the genre itself a plain declarative object, as in `shaping`: it lists the entity kinds (with property spaces), field kinds, action kinds, compile passes, vocabulary entries, capability vocabulary, verifiers, store kinds and CLI namespace it registers. A genre is then inspectable before it is loaded, which MCP and the docs generator need.

---

## 3. The core contract, assembled

The core is a contract before it is code. It has five parts; only the first must exist in two languages.

| Layer | What it is | Where |
|---|---|---|
| **K. Timing kernel** | address grammar; field-kind registry (`switch_at`, colour space, log space); easing registry with solvers; the authored flat timeline and the compiled form (tracks, placed clips, loop modes, channels, active / held / at-rest, write groups); sparse `at(t)` plus rest; the frame clock | contract files (JSON Schema + golden vectors) in `an`; Python `an.timing`; TypeScript in `previz`; `runtime.js` stays a bit-exact mirror of `an.timing` |
| **D. Documents** | `{kind, version}` envelope, migrations per kind, the scene IR (open action union, entity kinds with property spaces), shots, narration, sound, captions | `an.ir` |
| **R. Rendering** | `Renderer` (whole shot), `Engine` (seekable), live engine; `frame_stage_renderer`; sinks and film assembly | `an.adapters._base`, new `an.engines`, `an.media`, `an.assemble`, `an.render` |
| **S. Services** | vocabulary + MCP (ADR 0003), capabilities over assets, engines and environment (ADR 0002), the library (ADR 0005), the build graph (ADR 0004), verifiers, stores, genre discovery | `an.semantic`, `an.capabilities`, `an.library`, `an.build`, `an.verify`, `an.stores`, `an.genres` |
| **E. Default engine** | the 2D stage runtime (paths, text, raster and SVG art, planes, camera, surface treatments) | `an.stage`, shipped with `an` behind an `an[stage]` extra, **outside the core firewall** |

The **contract files** are what the family study recommended and what `burns` and `previz` already practise: `easing.json` (the registry's curves, with sample values), `kinds.json` (each field kind, with sample interpolations), `timeline.schema.json` (the authored flat timeline, which `shaping` validates its tracks against), `compiled.schema.json` (tracks, clips and channels, which the vectors evaluate), and one `timing_vectors.json` (documents and the state at a list of times; numbers within 1e-9, everything else exact; sample times include every segment boundary and midpoint, as `previz`'s file does). `previz`'s golden format is the template, and its existing cases become the seed. The contract lives in `an` because `an` is public and the core; `previz`, `burns` and `shaping` copy the files and assert them, as `burns`' two languages already do.

**The gate for kernel changes.** `scene_contract_sha256` hashes the compiled document (keyframes and easing specs), never an evaluated pose or a pixel, so an unchanged hash proves only that the *document* did not move. A change to how the document is *evaluated* (the solver, the discrete rule, the sampler) can leave every hash intact and still move pixels. Every kernel change is therefore gated on four things: unchanged contract hashes, the Python/JS parity tests, the pure-pose tests, and the decoded-pixel goldens.

**The firewall.** A test asserts that no core module imports `an.stage`, a genre package, Playwright, Manim or `manimkit` at module level (the `walkthru` firewall test is the pattern). Back-ends are optional dependencies with install-hinting typed errors, like the ElevenLabs provider today. The core *corpus* (ADR 0001 Decision 7) is rendered by `an.stage`, so the core's own CI installs `an[stage]`; the firewall is about imports, not about which extras CI installs.

---

## 4. Each genre as a client of the core

### 4.1 Cut-out: `cutan`

`cutan` is the first genre package (an#225, name chosen). It registers: the `character` entity kind and its property space (the stage node's transform properties plus swap channels as `discrete(switch_at=1)`); `PlayAction` and `ExpressionAction`; the rig, face, viseme, blink, gaze and swap-pose compile passes over `an.stage`'s compiler; the mouth and eye visual kinds of the runtime; locomotion, speech, blink and turn methods with their requirements (ADR 0002); its vocabulary (motion presets that need parts, expression presets); the cut-out style lint; and the `an character …` CLI namespace. Its renderer name stays `cutout` (a persisted identifier): `an.stage`'s renderer claims both `stage` and `cutout`, and a `cutout` shot that uses a cut-out kind fails validation with "install `cutan`" when the genre is absent.

### 4.2 Mathematical and explainer animation: Manim, in two steps

**Step 1, opaque-source shots (now).** Replace the title-card skeleton in `an/adapters/manim_adapter.py` with a `Renderer` that renders a shot from a scene file: `Shot(renderer="manim", options={"source": <library or project key>, "scene": "BarChartStory"})`. It delegates to `manimkit.render_check` (a soft dependency, typed install hint), records the contact sheet and layout warnings as `Finding`s (located by source line), and keys its cache on the source's content hash plus the Manim version and quality. The shot gets narration, captions, sound, transitions and film assembly from the core, with no IR inside it. An opaque shot's duration cannot be authored, because only Manim's own `play` and `wait` calls decide it: `shot.duration` is optional for such a shot, filled from the reported duration after the render and written back into the IR (a `Finding` only when an author declared a value and the render disagrees beyond one frame). This is the cheapest proof that the core works without `cutan`.

**Step 2, a math-viz genre on the core (when it is wanted).** Entity kinds for axes, function graphs, number lines, typeset formulas, arrows and shapes, with property spaces; action kinds `create` (draw-on, which is the stage's `trim`), `write`, `transform` (morph, a `points` field kind), `indicate`; vocabulary seeded from `manimkit`'s corpus; derived channels for tracker-driven values (§2.4). It compiles to Manim code through the step-1 renderer, and the subset the stage engine can draw (paths, text, typeset formulas as SVG, the camera) can render on `an.stage` with the same timeline, so the two back-ends can be compared against the same golden vectors. Where it lives is open: `manimkit` could register it through the `an.genres` entry point behind an extra (it already owns the corpus and the checks), or it could be its own package. The rule of ADR 0001 applies: it breaks off when it has developed enough.

### 4.3 View-state animation: `previz`

`previz` stays a separate TypeScript package. It plays two roles in the core:

1. **The TypeScript implementation of the timing kernel.** Its field kinds, easing registry and `at(t)` are the reference the contract files are seeded from, and it asserts the shared `timing_vectors.json`. This is the end of the five-copies problem: one contract, two implementations, every other copy (`shaping`'s tracks, `burns`' easing) validated against it.
2. **A back-end for shots whose entity is an engine view.** A shot with one entity of kind `view` (its property space is the `previz` space) and tweens on its properties exports to a `previz.sequence` document (each segment of the flat timeline is a transition) and renders through the `previz` CLI or a browser page with the engine adapter, wrapped by `frame_stage_renderer` or as a whole-shot `Renderer`. The reverse also holds: a `previz` sequence lowers to the core's flat timeline, so a captured camera move from an app can open a cut-out or explainer shot.

`previz` formulas export to the vocabulary registry as JSON-described entries (`id`, `title`, `description`, `params` schema), so an MCP client of `an` can list them; their `build` runs on the TypeScript side.

### 4.4 The smaller siblings

- **`burns`** is a seekable engine (state = a crop rectangle over a still) with a ready-made golden-vector suite; under the core, its easing table is the CSS entries of the shared registry, and its eight moves are vocabulary entries next to `an`'s nine camera moves in one table.
- **`walkthru`** is the live tier's worked example (commands, readiness gates, real-time capture with constant-rate resampling) and the precedent for anchoring narration to steps. Its guardrail against the "inner-platform effect" is a useful check on the core: the canonical timeline stays small (set and tween over addressed properties), and everything richer is a front-end or a vocabulary entry that lowers to it.
- **`shaping`** validates its animation tracks against `timeline.schema.json`, and its "display vs build" field split becomes part of the property space (§2.14). Its genre-as-object shape is the model for `an.genres`.

---

## 5. Module map: what stays in the core, what goes to `an.stage`, what goes to `cutan`

Three destinations. **core** is `an` behind the firewall; **stage** is `an.stage`, shipped with `an` as the default engine but outside the firewall; **cutan** is the genre package. "Split" means the module is divided along the line given.

| Today | Destination | Note |
|---|---|---|
| `an/ir/schema.py` | core, split | core: envelope, `Meta`, `Shot`, `AssetRef` (open `kind`), `SetAction`, `TweenAction`, combinators, `ExtensionAction`, `Camera`, `Transition`, `SoundCue`, `Captions`, `Narration`, core `Dialogue` fields; cutan: `PlayAction`, `ExpressionAction`, later the `Dialogue` viseme and emotion fields (migrated) |
| `an/ir/{migrate,compose,camera,assets}.py` | core | `compose` loses `default_play_extent` (registered by cutan); gains `stagger` |
| `an/ir/sync.py` | core, split | the `scene.md` framework is core; the `[emotion]` sugar registers from cutan |
| `an/ir/validate.py` | core, split | genre-free checks stay; `_check_turns`, `_check_hidden_mouth_while_speaking`, `_check_view_continuity`, `_check_whole_character_swap` and the swap-set conventions register from cutan |
| `an/adapters/cutout/{easing,channel,clip,timeline}.py` | core → `an/timing/` | plus the new field-kind registry and the contract files |
| `an/frame_clock.py`, `an/determinism.py` | core | |
| `an/adapters/_base.py`, `an/render.py`, `an/assemble.py`, `an/orchestrate.py` | core | `render.py` stops importing the cut-out compiler; new `an/engines/` for the `Engine` protocol and `frame_stage_renderer` |
| ffmpeg helpers in `an/adapters/cutout/render.py`, constants in `an/base.py`, the GIF recipe in `misc/demos/build_demos.py` | core → `an/media/` | one sink per format |
| `an/adapters/cutout/{supersample,shutter}.py` | core → `an/media/` | frame-stage operations, engine-independent |
| `an/adapters/cutout/{serialize,render,canvas_capture,runtime_files,path,text,surface,fidelity}.py`, `an/data/cutout_runtime/` (minus the mouth and eye visuals) | stage | the wire shape keeps its field names, so no contract hash moves |
| `an/adapters/cutout/compile.py` | stage + cutan | scene building, camera, parallax, paths, text, stepping, tint and surface passes to stage; rig, face, viseme, blink, gaze, swap-pose passes to cutan, through a compile-pass registry |
| `an/adapters/cutout/{coarticulate,gaze}.py` | cutan | |
| `an/paths.py`, `an/text.py`, `an/raster.py`, `an/environments.py`, `an/props.py` | stage | drawables, planes and props with states are what the stage engine draws for every genre |
| `an/preview.py` | stage | |
| `an/styles.py` | core, split | palette and surface roles are core; roles that name body parts go to cutan |
| `an/motion.py` | core, split | requirement-free macros (`pop_in`, `slide_in/out`, `shake`, `squash_stretch`, `hop`) core; `walk`, `turn`, `nod`, `point`, `waddle` cutan |
| `an/characters/`, `an/expression/`, `an/impacts/` | cutan | |
| `an/audio/` | core, split | TTS, voices, effects, pipeline, providers, Whisper word timings core; `rhubarb_lipsync`, `offline_lipsync` and the viseme half of `injectable_lipsync` cutan (a post-audio hook) |
| `an/verify/` | core, split | `style.py` cutan; `vision.py` loses its expression-preset import; new geometric layout verifier and contact sheet |
| `an/bench/` | core + stage + cutan | `metrics`, `png`, `imageio`, `ledger`, `registry`, `compare`, `environment`, `golden`, `masks` core; `contract.py` (it hashes the stage's compiled document), `stage.py` and `palette.py` stage, until the contract hash is generalised to any renderer's compiled artifact; the cut-out corpus, `capture`, `run`, `mutants`, `mutations` cutan until the core corpus exists |
| `an/stores/`, `an/project.py` | core, split | generic stores core; `characters` store cutan |
| `an/captions.py`, `an/credits.py`, `an/sounds.py`, `an/iterate.py`, `an/live_api.py`, `an/tools.py`, `an/check_requirements.py`, `an/base.py` | core | `iterate.py`'s prompt becomes generated (ADR 0003) |
| `an/genre.py` | core → `an/genres/` | the registry and discovery; the `cutout_animation` declaration moves to cutan |
| `an/adapters/manim_adapter.py` | core (optional back-end) | rewritten as §4.2 step 1, delegating to `manimkit` |
| `an/adapters/{remotion_adapter,whiteboard}.py` | core (optional back-ends) | unchanged stubs |

---

## 6. What this changes, and the order of work

ADR 0001 is revised (same status, *Proposed*) with: the three-genre boundary test; the timing kernel as a cross-language contract; "no engine is core" (the stage runtime moves from "in the core" to `an.stage` behind the firewall); the three renderer tiers; property spaces on entity kinds; and the Manim and `previz` relations of §4. The order of work gains three steps, all inside `an`, all before `cutan` exists:

1. **The kernel contract.** Move timing to `an/timing`; add the field-kind registry (declared kinds reproducing today's behaviour exactly); write the contract files seeded from `previz`'s golden cases plus `an`'s parity cases (including the an#86 boundary case and a cross-track boundary); the gate is §3's four checks (contract hashes, parity tests, pure-pose tests, pixel goldens), not the hashes alone.
2. **The firewall and the engine seam.** The `Engine` protocol and `frame_stage_renderer`; `an.stage` as the first engine; the import firewall test.
3. **The first non-cut-out renderer.** The opaque-source Manim renderer (§4.2 step 1), plus the core corpus of ADR 0001 Decision 7 (paths, text, planes, camera, transitions on the stage engine). Together they show that `an` renders without cut-out code.

Work outside `an`, each in its own repository and session: `previz` asserts the shared vectors; `shaping` validates its tracks against `timeline.schema.json`; `burns` takes its easing and moves from the shared tables.

## 7. Decisions for the maintainer

| # | Decision | Recommendation |
|---|---|---|
| 1 | Accept the timing kernel as a cross-language contract (JSON Schema + golden vectors) with Python (`an.timing`) and TypeScript (`previz`) implementations | **Accept.** It ends five drifting copies, and `previz`'s format already exists |
| 2 | Declared field kinds, seeded from `previz`'s seven, with `discrete(switch_at)` (defined on time) and `color(space)` parameters; `an`'s behaviour reproduced by declarations, `tint` left as a compiler expansion | **Accept.** No compiled document changes; gated as in §3 |
| 3 | Easing canon: CSS names mean CSS curves; `an`'s names stay as their own versioned curves; Manim rate functions as entries | **Accept** |
| 4 | "No engine is core": the stage runtime ships with `an` as `an.stage` behind an extra and a firewall (revises ADR 0001 Decision 5 and review Decision 2) | **Accept.** A data-viz user still gets it with one install; the core stays testable without a browser |
| 5 | Manim step 1 (opaque-source shots through `manimkit`) as the first non-cut-out renderer | **Accept**, before `cutan` is created |
| 6 | Where a math-viz genre lives when it is built: inside `manimkit` (registered behind an extra) or its own package | **Defer** until step 2 is wanted |
| 7 | The contract files live in `an` (public) and `previz` copies them, rather than `previz` owning them | **Accept.** `previz` is private; the core contract must be readable by every consumer |

---

## 8. Independent review

An independent reviewer (fresh context, no access to this study's reasoning) checked the core contract against the code of `an`, `manimkit`, `previz` and `shaping`. Every point was verified against the source and addressed in this version:

| Finding | Answer |
|---|---|
| Unchanged contract hashes prove nothing about evaluation: the hash covers the compiled document, not poses or pixels | §3: kernel changes are gated on hashes, parity tests, pure-pose tests and pixel goldens |
| Declaring `tint` as `color(srgb)` would change the wire shape; today it is expanded to three numbers before channels exist | §2.3: `tint` stays a compiler expansion; `tint_r/g/b` are `number`; `color(space)` is for new genres |
| `previz`'s discrete rule (`tau >= switchAt`) is the ratio `an` rejected in an#86 | §2.3: discrete is defined on time; `switch_at == 1` is `t >= b.time`; `previz` changes to match; the vectors carry the boundary case |
| The "flat timeline" conflated the authored and compiled levels; clips, loops, held values and write groups were missing from the kernel | §2.4 and §3: two levels, two schemas; the compiled level's semantics are kernel content |
| Sparse vs total `at(t)` | §2.5: sparse plus a rest state; `previz`'s back-fill lowers to it |
| `previz` does not sample at `k / fps`; adopting its rounding would move `an`'s pixels | §2.5: the kernel keeps `an`'s clock; snapping is a front-end sampler option |
| Inclusive clip ends are not literally half-open | §2.5: both rules stated, a cross-track vector added |
| Timing from audio inside `flatten` breaks pillar 3 | §2.9: a resolution pass writes into the IR; `flatten` stays pure |
| An opaque Manim shot's duration cannot be authored | §4.2: filled from the render and written back |
| The address grammar missed `@` qualifiers, aliases and write groups, and conflated fields with kind members | §2.2: `@qualifier`, aliases and write groups in the property space, dotted segments name fields only |
| Camera rotation was a second, undeclared exemption | §2.3: all four camera properties declared `number` for cut-out |
| An undeclared swap set would default to `switch_at = 0.5` | §2.3: the stage declares `*@*` as `discrete(switch_at=1)` |
| The two Bézier solvers do not agree to 1e-9 | §2.3: the solver is part of the easing entry; `an`'s stays a legacy solver |
| Time-driven engines need a read-back for conformance | §2.7: `state(t)` |
| Partial re-capture is wider than the edited span under held semantics | §2.14 |
| IK and attachments over-reach the kernel; "expression" collides | §2.4: derived channels are pure value functions only; the word changed |
| `bench/contract.py` hashes the stage wire shape; the core corpus needs `an[stage]` | §5 and §3 |
| Opaque sources need a source-line locator | §2.10 |
| Property spaces need units | §2.2 |


## Sources

- `an` at 0.1.126: `CLAUDE.md`, `misc/docs/framework_review_2026-10.md`, `misc/docs/cutout_framework_review_2026-10.md`, `misc/docs/design_principles.md`, ADRs 0001–0005, `misc/docs/asset_library_design.md`, and the modules named above.
- [`manimkit`](https://github.com/thorwhalen/manimkit) 0.0.3: `README.md`, `manimkit/render.py`, `manimkit/_runner.py` (the layout probe), `manimkit/corpus.py`, `manimkit/search.py`, the shipped skill.
- `previz` v1 (private): its design record, `src/core/{types,timing,compile,kinds}.ts`, `golden/README.md`, `golden/vectors.json`, the README's engine interface.
- [`shaping`](https://github.com/thorwhalen/shaping): `docs/architecture.md` (§3, §7, §10, §11) and its ADRs 0001–0002.
- [`burns`](https://github.com/thorwhalen/burns) and [`walkthru`](https://github.com/thorwhalen/walkthru), through the 2026-09-29 family study of `an`, `burns` and `walkthru`.
- Manim Community Edition's public API as used by `manimkit` (`Scene.play`, `wait`, `run_time`, `rate_func`, `AnimationGroup`, `Succession`, `LaggedStart`, `Transform`, `ValueTracker` and updaters, `MovingCameraScene`, `ThreeDScene`, partial-movie caching), and the community plugin `manim-voiceover`.
