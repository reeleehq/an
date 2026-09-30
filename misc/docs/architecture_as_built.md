# `an` — As-Built Architecture

> **What this is.** A snapshot of the system as it exists in the repo today, intended as the canonical reference for both human contributors and AI agents working in `an`. The seven research reports next to this file (`report 0...`, `report 1...`, etc.) describe the *design space*; this doc describes *what was actually built*. When the two disagree, the code is authoritative — fix this doc.
>
> **This is the only capability map.** The capability table lives in §0 below and nowhere else (`CLAUDE.md` deliberately carries none). Add a row to §0 when a capability ships.
>
> Currency: written 2026-05-02, after Phase 10 (iterate loop); §0 and §10 refreshed 2026-09-29; §0 again 2026-09-30. Update on each substantive change.

---

## 0. Capability map

What exists, and where, moved here from `CLAUDE.md` (an#156) so there is one map, not two. This replaces the old phase table on purpose — phase tables drift. Rows name the shipping issue; read the module map (§3) for where each piece sits.

| Capability | Lives in | State |
|---|---|---|
| Scene IR: schema, composition, validate, migrate, md↔json sync; `play` of a descriptor animation resolved by `an.characters.play` — the one resolver `an validate` and the compiler share (an#7) | `an/ir/`, `an/characters/play.py` | shipped |
| Project layout + dol-backed mall (characters, props, environments, voices, styles, scenes, artifacts, decisions) | `an/project.py`, `an/stores/` | shipped |
| CLI `an {init,validate,sync,render,iterate,preview,check}` + `an character {new,mouths,add-gaze,validate,silhouette,preview,record}` + `an impacts {clip,clip-set}` | `an/tools.py`, `an/__main__.py`, `an/characters/cli.py` | shipped |
| Cutout backend: easing, channels, clips, timeline (the executable spec of the runtime's evaluation, parity-tested under node), JSON contract, `compile_shot` with generic **swap channels** (any property outside the transform vocabulary names a declared asset set, projected per slot — an#87) and **`play`** (a descriptor animation → a per-instance clip: bone tracks as deviations around the built rest, slot tracks as one swap set each; a looping play with no `duration` runs to the shot end — an#7), headless Playwright+ffmpeg render — application is `runtime.js` only (an#86) | `an/adapters/cutout/` | shipped — the real v0.1 renderer |
| JS runtime: PixiJS v7, procedural rig, SVG-sprite rig, generic swap channels (`applySwap` — any declared asset set, `viseme` included; an#87); blinks are COMPILED channels since an#88 (eyelid swap where closed art resolves, `scale_y` squash otherwise) | `an/data/cutout_runtime/{index.html,runtime.js,preview.html}` | shipped |
| TTS providers `offline` / `elevenlabs` / `mac_say` | `an/audio/{offline_tts,elevenlabs_tts,mac_say_tts}.py`, factories in `an/audio/providers.py` | shipped |
| Lip-sync providers `offline` / `whisper` / `rhubarb`, plus `WordTimingsLipSync` for injecting precomputed word timings | `an/audio/{offline_lipsync,whisper_lipsync,rhubarb_lipsync,injectable_lipsync}.py` | shipped |
| Audio pipeline with content-hash caching and provider-swap re-synthesis | `an/audio/pipeline.py` | shipped |
| Verifiers: layout lint, media quality, vision-LM, human-in-the-loop (+ ffmpeg/SSIM helpers) | `an/verify/{layout,media_quality,vision,human}.py`, `an/verify/media.py` | shipped |
| **Style lint + style specs**: `an.verify.style.StyleLintVerifier` measures a render the way the cut-out styles research measured six real styles — held-frame share, the one/two/three-plus change-interval histogram, longest hold, cuts per minute and mean shot (cuts taken from the IR), saturation, dark-pixel share, top-16 colour coverage — and warns per missed `[low, high]` target with the knob that moves it; numpy + ffmpeg only; a failure to measure reports at `FAILURE_SEVERITY`. The specs are skill files (`.claude/skills/an-style/styles/*.yaml`: `live` settings checked against the code by `tests/test_style_specs.py`, measured `targets`, `guidance` for what `an` cannot do), NOT a document the compiler reads — that is gap 1 of an#163 | `an/verify/style.py`, `.claude/skills/an-style/`, `misc/docs/cutout_styles_research.md` | shipped |
| Project render: per-shot dispatch through the registry, shot cache, ffmpeg concat | `an/render.py` — `render_project()` / `render()` | shipped (no stub, no `NotImplementedError`) |
| Orchestration `validate → pre-verify → audio → render → post-verify` | `an/orchestrate.py` — `orchestrate()` → `OrchestratorReport` | shipped |
| Per-shot parallel rendering, `an render --parallel auto\|N` | `an/render.py` — `_resolve_parallel`, `_render_one` | shipped |
| Free-text edit loop: instruction → Claude → JSON patches → validated IR → selective cache invalidation | `an/iterate.py` — `iterate()` | shipped (needs `ANTHROPIC_API_KEY`) |
| Character authoring: descriptor schema, SVG utils, 9-shape mouth set **plus `viseme@<form>` variant sets** (`happy`/`sad` by default, `an character new --mouth-variants`, `an character mouths --variants`), DiceBear client, idle/blink, silhouette test, factory, promote, preview recording; `an character validate` checks the variants | `an/characters/` | shipped |
| SVG-texture character rendering (descriptors drive real sprites, not procedural rects) | `an/adapters/cutout/compile.py` (`svg_sprite` visuals) + `runtime.js` `makeSvgSprite` | shipped |
| Live preview with file-watch reload, `an preview <dir>` | `an/preview.py` — `preview_project()`, `preview.html` | shipped (visuals only, no audio) |
| Metrics ledger: `an bench` renders a fixed corpus and writes one row per (date, commit) | `an/bench/` — `run_bench()`, `METRICS`, `build_scene_block()` | shipped (an#36) |
| Golden corpus: 26 committed PNGs across ten scenes, compared on DECODED pixels, `an bench --bless "<reason>"` | `an/bench/{png,golden}.py`, `misc/bench/{corpus,golden}/` | shipped (an#38) |
| Row comparison: `an bench-compare`, per-mutation signs, refuses incomparable rows | `an/bench/compare.py` | shipped (an#40) |
| Mutation levers (`high_crf`, `disabled_aa`, `supersample`) + the guard-mutant registry, `an bench-mutants` | `an/bench/{mutations,mutants}.py` | shipped (an#41, an#56) |
| Determinism perimeter: the runtime probes, `an/determinism.py` judges, enforced by default | `an/data/cutout_runtime/runtime.js` `anDeterminismReport` + `an/determinism.py` | shipped (an#37) |
| Camera: nine named moves (`hold`, `push_in`, `pull_out`, `zoom_in`, `zoom_out`, and since an#109 `pan_left`, `pan_right`, `tilt_up`, `tilt_down`) plus explicit `Camera.keys` — **one code path, two front doors**, resolved by `an.ir.camera.camera_keys`, which validate calls too — one table, not two reconciled by a test. `root.pivot` IS the 2D camera (PixiJS composes `world = position + M·(local − pivot)`) and was already runtime-applied, so translation was a **compiler** change with zero runtime change. Only properties that VARY get a channel, which is what keeps the five zoom moves byte-identical to their pre-an#109 documents. An authored channel on a camera-driven `root` property **raises** — camera clips are appended last and the evaluators are later-wins, so the collision was silently discarding the author's value | `an/adapters/cutout/compile.py` — `camera_keys`, `_add_camera_clips`, `CAMERA_MOVES` | shipped |
| **Multiplane environments** (an#110): an `an.environments.EnvironmentDescriptor` with `planes`, **list order = draw order** (the runtime has no `zIndex`, so a `z` field would be a second ordering it could not honour). Each plane's `depth` is Godot's parallax RATIO — `1.0` is the character plane and **emits nothing**, `0` does not PAN, `>1` is foreground. **Depth governs translation only**: `root.scale` multiplies the whole composed expression, so no per-plane factor can cancel a zoom — a `depth = 0` plate still grows under `push_in`. Depth-aware zoom is the dolly, deferred with its reason; `parallax` is the per-axis override; larger depth = nearer = faster, which is the INVERSE of Unity's z-derived convention. `characters_after` names the plane the characters stand in front of, which is how a foreground plane became reachable at all — the old builder ran environments and characters in two separate loops, so no entity order could interleave them. Compensation is `plane.x = x0 + (1 − f)·cam_x`, emitted after the camera, and an authored channel on a compensated plane **raises** for the same reason the camera's does. `Plane` is `extra="forbid"` while the document holding it is `extra="allow"`: the store's natural shape includes `name`/`tags`, but a plane is a precise instruction to draw something. A document without planes takes the legacy preset path **byte-identically** | `an/environments.py`, `an/adapters/cutout/compile.py` — `_build_plane_subtree`, `_add_parallax_clips` | shipped |
| **StylePack** (an#112): art direction as a document, and the first reader the `styles` store has ever had. `an.styles.StylePack` maps a role to a hex colour (`roles`), with per-entity overrides, named by `meta.style_pack`. It recolours what the **compiler** decides — the character palette, legs, pupils (all three now asserted to reach the document by a per-role test —  shipped declared-reachable and wired to nothing), the environment presets' sky and ground — and **does not recolour SVG art**: that needs role tagging the descriptor does not have, and inferring a role from a pixel is what produced an#99's wrong-tone lid, so the compiler **warns naming the rigs it could not reach**. A pack may not declare `lip`/`mouth_fill`/`teeth`/`tongue`/`eye_sclera` — `runtime.js` literals, refused at construction because a role that silently does nothing is worse than an absent one. Byte-identity rests on two omit-when-unset serializers written in the SAME commit as their fields, this being the one Wave 7 feature that could have moved every corpus hash | `an/styles.py`, `an/adapters/cutout/compile.py` — `style_pack_for`, `resolve_palette` | shipped |
| **Stroked paths** (an#160, Wave 9's first slice): a path is a **prop** whose document is an `an.paths.PathDescriptor` (props store, placed as `kind: prop`; no scene-IR change), overrides merged and validated strictly by `resolve_path` — the one resolver compile and validate share. Polyline or chained cubic Béziers, **flattened in the compiler** so the wire (`VisualJSON.path`, omit-when-unset — no corpus hash moved) carries one geometry. `trim_start`/`trim_end` are in `TRANSFORM_PROPERTIES` (fractions of arc length; a trim tween with no `from` starts at the document's value), refused on any non-path target at compile, validate and runtime. The arrowhead sits on the trimmed tip along the incoming leg and grows in. `path_geometry` is the executable spec of `runtime.js::pathGeometry`, parity-tested under node with **exact** equality (IEEE `+ - * / sqrt` only, no trig). Not yet a StylePack role | `an/paths.py`, `an/adapters/cutout/path.py`, `compile.py` — `_build_path_subtree`, `_check_trim_target`; `runtime.js` — `pathGeometry`, `drawPath`, `applyTrim` | shipped (an#160) |
| **Text on screen** (an#155, Wave 8's first slice): a text block is a **prop** whose document is an `an.text.TextDescriptor` (the stroked-path shape: props store, `kind: prop`, overrides merged strictly by `resolve_text`, no scene-IR change). **`tituli` is the typesetter** — shaping, metrics, wrapping, alignment, the title-safe anchors — and `an` consumes its placed `Run`s: each unit (`unit: word`/`glyph`/`line`) becomes one node `<id>/word_<i>` whose visual is an ordinary `svg_sprite`, its texture a `data:` URI holding that unit's glyph contours (`tituli.run_outline`, fontTools) — **the runtime never rasterises a font** and the compiled document is self-contained. Units animate with ordinary tweens; `an.text.stagger` generates the per-unit `set` hold + delayed `tween` (leaf shapes, so it survives `scene.md`). **Two layers**: `layer: world` is in the scene; `layer: overlay` goes in `CutoutSceneJSON.overlay`, a second top-level container `runtime.js` centres but never indexes, so no channel — the camera included — reaches it (`screen_position` composes it the same way). **Fonts**: default is Pillow's embedded Aileron (CC0) requested via `tituli.EMBEDDED` (never scans installed fonts); `font:` must be a FILE (a family name is refused as machine-dependent); a missing/unusable file, a relative path with no on-disk store, or a glyph the face lacks RAISES at compile and is an error in validate; the face's sha256 and Pillow layout engine are recorded in `meta.fonts`; `nodeIndex` is one namespace for both layers, so a text id `root`/`overlay`, an overlay id equal to a scene entity's, and duplicate text ids are refused at compile and validate. `overlay` and `meta.fonts` are omit-when-unset — no corpus hash moved | `an/text.py`, `an/adapters/cutout/text.py`, `compile.py` — `_build_text_block`, `_check_text_unit_targets`; `runtime.js` (overlay container); `validate.py` — `_check_text_blocks` | shipped (an#155) |
| **Motion presets** (`an.motion`): `pop_in`, `hop`, `shake`, `nod`, `point`, `slide_in`, `slide_out`, `squash_stretch`, `waddle` — authoring macros that expand to plain `tween`s through `sequence`/`parallel`, each ending with a settling `set` (frames sample `i / fps` and the runtime holds the last pose, so a move ending between frames would otherwise stop short). Called from Python, no IR field and no runtime change: the compiler sees only the tweens. Values are absolute, so presets take `rest=` — `rest_pose(shot, target)` reads it off the compiler's own scene builder (an entity's `x` is laid out). `as_leaves` makes a preset survive `scene.md`, which drops composition trees. **By name from `scene.md`** (an#166): a `play` whose name the descriptor does not declare — or any `play` on an entity with no descriptor (procedural rig, prop) — falls back to `PRESETS`, decided by `an.characters.play.play_problems`/`play_source`, the one resolver validate and compile share; **a descriptor animation of the same name wins**. The compiler (`_expand_preset_plays`) replaces the play with the preset's flat tweens and settling sets BEFORE anything else looks, at the moved node's BUILT rest (`vocab.node_transforms`), so no `rest=`; `PlayAction.args` (omit-when-unset) are the preset's keyword parameters, `duration` stretches and `speed` divides, `loop` is refused. Being tweens, a preset play is stepped by `step_hz` (a descriptor `play` clip is not). Validate checks the moved node against the compiler's own stage build (`an.motion.stage_poses`), says so when that build fails rather than passing, and warns when a preset play runs past the shot end. Like every `play`, one with no `duration` is zero-width inside a `sequence` (`flatten` cannot know which source wins) | `an/motion.py`, `an/characters/play.py`, `an/adapters/cutout/compile.py` | shipped |
| **Scene default easing** (an#166): `Meta.default_easing` (omit-when-unset) is the curve of every authored tween that names none — precedence tween > `meta.default_easing` > built-in `ease_in_out`, stated once in `TweenAction.resolved_easing`. "Unset" is `"easing" not in model_fields_set`: `TweenAction.easing` keeps its `"ease_in_out"` default for readers, `compose.tween` defaults to the `INHERIT` sentinel, and a wrap serializer omits an unset easing so the distinction survives `scene.json`; the `scene.md` writer emits `easing:` exactly when set (`ease_in_out` included). Threaded `RenderContext.default_easing` → `compile_shot(default_easing=)`, preview too, re-checked at compile. Reaches authored tweens only (not presets, camera, blinks, `play` clips). No shot-level override: style is a scene's. Unset, every corpus and example contract hash is unchanged (compared before/after at landing) | `an/ir/schema.py`, `an/adapters/cutout/compile.py` — `_build_anim_for` | shipped |
| Supersampling, opt-in — `resolution: k` + `autoDensity: false`, resolved by an exact k x k block mean in the frame stage; `an render --supersample N` | `an/adapters/cutout/supersample.py`, `RenderContext.supersample` | shipped (an#58) |
| Stepped timing, opt-in — `Meta.step_hz` / `Shot.step_hz` (shot wins; `an render --step-hz N`): authored tweens resampled (sample-and-hold of the eased curve) onto a shot-wide pose grid of step-eased keyframes (15 at 30 fps = "on twos", 10 = "on threes"); camera, blinks, `play` clips and swap channels exempt **by construction** (separate emission sites); stamped into `meta.step_hz` only when set, so an unstepped scene's contract hash is unchanged. **No bench lever, on measurement**: stepping moves `scene_contract_sha256` on every scene with a tween (the resampled keyframes are the contract), so `bench-compare` refuses a stepped row at comparability before any family is examined — unlike `pix_fmt`, which stayed comparable and *failed* its exam — and outside the comparer every family moves with the pose content, in both directions. The human side-by-side is the `stepped-timing` demo (its frame strip is committed at `misc/docs/step_hz_side_by_side.png`); the default stays smooth and only the maintainer flips it (an#89) | `an/adapters/cutout/compile.py` — `step_times`, `_stepped_keyframes`; `an/ir/schema.py` | shipped (an#89) |
| **Expression (an#98)**: `ExpressionAction` leaf + dialogue `[emotion]` sugar (in memory only) → `an/expression/` (ten axes, ten presets, the binding, `resolve_mouth_set`, the provider seam) → the compile-time **face solver** `_add_face_clips`: one channel per (node, property), brows summed over rest, lids `min(expression, blink)` off one ladder, the mouth's `viseme@<form>` set selected per line; untouched entities get their an#88 blink clips VERBATIM (all seven pre-existing corpus contract hashes unchanged, asserted). **Gaze (an#99)**: the eye stack (sclera → pupil → lid slots, `an character add-gaze`, the descriptor's `gaze_travel` clamp), `gaze_x`/`gaze_y` as expression axes, ambient saccades from `an/adapters/cutout/gaze.py` (step keyframes on frame times, seeded by the entity name, `meta.gaze_seeds`); a rig without pupils takes gaze as a byte-identical no-op. Environment backdrops, per-character palettes | `an/expression/`, `an/adapters/cutout/{compile,gaze}.py` | shipped |
| **Frame clock** (`RenderContext.frame_samples`): per output frame, the scene instants to capture and average — an open shutter (motion blur) and capture jitter. `None` is the old `i / fps` single sample, byte for byte (asserted call-for-call with a fake page); the temporal mean is exact and rounds half-to-even like the spatial one. `an.frame_clock.FrameClock` builds the instants and is the SAME object the impact ground truth records, so the two cannot disagree | `an/frame_clock.py`, `an/adapters/cutout/shutter.py`, `_capture_frames` | shipped |
| **Impact harness** (`an.impacts`): a stick or ball striking a surface or the air on a tempo grid (tempo changes, accents, AR(1) humanisation), rendered through the cutout backend with a `FrameClock`. The sidecar keeps `t_grid` (intended), `t_impact` (executed, continuous seconds — a segment boundary at its exact float) and the frames apart; keypoints come from the COMPILED document via `screen_position` at every sample instant, cross-checked against the analytic stroke, and the renderer's staged document is compared with the truth's — a disagreement raises `TruthMismatch`. **A blurred frame's keypoint is the AVERAGE over its samples** — at a surface contact (a V) mid-exposure is up to 6 px off, exactly where estimators are scored. Objects move through `StrokeChannel`s, each affine in stroke height `h` (the exactness contract). `render=False` needs no browser. Pixels verified within 0.46 px of the keypoints in the browser lane | `an/impacts/`, `an impacts clip / clip-set` | shipped |
| Manim backend | `an/adapters/manim_adapter.py` | **title card only** — see gaps |
| Remotion backend | `an/adapters/remotion_adapter.py` | stub — raises `RemotionRenderError` documenting what a real impl needs |
| Whiteboard backend | `an/adapters/whiteboard.py` | stub — raises `WhiteboardRenderError` |

---

## 1. The story in 30 seconds

You write a `scene.md`. You run `an render <dir>`. An mp4 lands in `output/main.mp4` with audible dialogue, a sky/grass background, two distinct cartoon characters, animated mouths over real ElevenLabs speech aligned by Whisper word-timestamps, eye-blinks, faces driven by the expression solver (each line's `[emotion]`, or an `expression` action — brows, lids, mouth form, and the pupils' gaze with ambient saccades), and a slow camera push-in.

You say `an iterate <dir> "make Maya's response more affectionate"`. Claude (Opus 4.7) returns surgical JSON patches against the IR, validates them against the schema, persists, and invalidates only the affected shot's cache so the next render only redoes that shot.

Both flows pass through the same Scene IR — the single source of truth.

---

## 2. Three-layer IR (the architectural pillar)

Information flows downward. Verification feedback flows upward. Render Code is disposable.

```
Narrative Layer  scene.md                ← human-edited markdown (yaml meta, yaml shot, yaml entities, yaml actions, dialogue)
                       ↕ (an sync — newer-mtime wins, equalize on write)
Scene Graph      ir/scene.json           ← Pydantic-validated, the SSOT
                       ↓ (an.adapters.cutout.compile_shot)
Render Code      cutout JSON for JS      ← regenerated per render, never edited
                       ↓ (an.adapters.cutout.render — Playwright + ffmpeg)
                  output/main.mp4
```

The `iterate` loop closes the cycle: free-text → Claude → patches against `ir/scene.json` → re-render only affected shots.

---

## 3. Module map

```
an/
├── __init__.py              public API (curated __all__)
├── __main__.py              typer CLI entry point, wired programmatically
├── base.py                  type aliases, version constants, easing presets
├── util.py                  internal helpers (hashing, file I/O, time math)
├── tools.py                 user-facing CLI funcs + _dispatch_funcs
├── project.py               init / load / save Project + on-disk layout
├── render.py                project-level render orchestration + ffmpeg concat
├── orchestrate.py           validate → audio → render → verify; thin re-export of iterate
├── iterate.py               free-text → Claude (Opus 4.7) → JSON patches → IR mutation
├── check_requirements.py    diagnose ffmpeg/node/playwright/elevenlabs/manim/rhubarb/etc.
├── determinism.py           judges the runtime's determinism probe; enforced by default
├── live_api.py              the ONE "yes, this run may spend money" switch (an#63)
├── props.py                 PropDescriptor — a prop is NOT a character with a
│                            different kind: an unresolvable prop RAISES where a
│                            character falls back to the placeholder rig (an#108)
├── paths.py                 PathDescriptor — a stroked path is a prop document
│                            (props store); overrides merged strictly by
│                            resolve_path, shared by compile and validate (an#160)
├── text.py                  TextDescriptor — a text block is a prop document;
│                            tituli typesets it, each unit becomes an SVG-sprite
│                            node; layer world|overlay; fonts fail loudly (an#155)
├── environments.py          EnvironmentDescriptor + Plane: list order is draw
│                            order, `depth` is Godot's parallax RATIO and governs
│                            TRANSLATION only, `characters_after` names the plane
│                            the characters stand in front of (an#110)
├── styles.py                StylePack — the styles store's first reader ever;
│                            REACHABLE_ROLES / UNREACHABLE_ROLES, checked against
│                            the literals read out of runtime.js (an#112)
├── preview.py               live-reloading browser preview; compiles WITH the pack
├── frame_clock.py           FrameClock: WHEN each output frame samples scene time —
│                            exposure (shutter), capture jitter, phase. Feeds
│                            RenderContext.frame_samples AND the impact ground truth
├── impacts/                 synthetic impact clips + exact ground truth (for scoring
│   │                        sub-frame onset estimators); never imported by __init__
│   ├── performance.py       TempoMap (piecewise-linear BPM in beats, exact integral),
│   │                        perform(): t_grid (intended) vs t_impact (executed)
│   ├── stroke.py            events -> h(t), quadratic easings only; surface = V at
│   │                        contact, air = braked turning point
│   ├── objects.py           stick / ball / surface as generated PROPS (k = 1); motion
│   │                        through StrokeChannels, each AFFINE in h (the contract)
│   ├── truth.py             keypoints from the COMPILED doc (timeline + screen_position)
│   │                        at every sample, averaged per frame (what a blurred frame
│   │                        SHOWS), cross-checked against the analytic stroke; refuses drift
│   ├── clip.py              ImpactClipSpec -> Scene IR -> truth (+ render) -> files
│   └── cli.py               `an impacts clip | clip-set`
├── genre.py                 genre descriptors
├── credits.py               credits rendering
│
├── bench/                   the measurement instrument (an#36) — never imported by __init__
│   ├── corpus.py            fixtures + pinned render knobs; the render-path assertion
│   ├── capture.py           render one fixture into a throwaway copy
│   ├── imageio.py           the four PINNED ffmpeg decodes + the lossless re-encode
│   ├── masks.py             edge / flat / held / ring, all from the REFERENCE frames
│   ├── metrics.py           pure numpy, no I/O — runs unmarked in the default CI leg
│   ├── palette.py           derive the declared colour set; mirrors runtime.js's rule
│   ├── registry.py          the metric declaration table: family, side, per-mutation sign
│   ├── ledger.py            the three blocks, and the guards that keep them readable
│   ├── contract.py          scene_contract_sha256 — the comparability key
│   ├── png.py               filter-0 writer + full-filter reader; numpy + stdlib only
│   ├── golden.py            the golden gate and `--bless`; compares DECODED pixels
│   ├── compare.py           two rows in, a verdict or a REFUSAL out (an#40)
│   ├── mutations.py         the levers, through seams the shipped code has
│   ├── mutants.py           guard mutants as DATA, so the proof re-runs; a killed
│   │                        sweep restores (SIGTERM raises) and the next run names
│   │                        a leftover as one (SIGKILL cannot be caught) — an#67
│   ├── environment.py       the environment tuple, split by comparison scope
│   └── run.py               capture -> panel -> row
│
├── ir/                      Scene IR (the SSOT)
│   ├── schema.py            Pydantic models: SceneIR, Shot, Action, Dialogue, AssetRef, ...
│   ├── compose.py           sequence/parallel/delay/loop/tween/set_/play + flatten
│   ├── camera.py            camera_keys: the NINE moves and Camera.keys resolved
│   │                        by ONE function, which validate calls too — one table,
│   │                        not two reconciled by a test (an#109)
│   ├── validate.py          schema + semantic validation, ValidationReport
│   ├── migrate.py           versioned migration registry (chained); scenes are
│   │                        migrated on read by sync.scene_from_json_doc (an#105)
│   └── sync.py              markdown_to_ir / ir_to_markdown / sync (mtime-newer-wins)
│
├── stores/                  dol-backed project mall (MutableMapping facades)
│   ├── __init__.py          build_project_mall(project_dir) factory
│   ├── _common.py           JsonDirStore, JsonSidecarStore, _BlobStore base classes
│   ├── characters.py        sidecar-folder store (character.json + per-part art)
│   ├── props.py             sidecar-folder store (prop.json + per-part art) — the
│   │                        same shape, a different store, because the rig builder
│   │                        takes the store as an argument (an#108)
│   ├── environments.py      sidecar-folder store
│   ├── voices.py            JSON-only store
│   ├── styles.py            JSON-only store
│   ├── scenes.py            wraps scene.md + ir/scene.json pair (mtime equalization)
│   ├── artifacts.py         BlobStore: audio (.wav), visemes (.json), shots (.mp4),
│   │                        previews (.mp4), output (.mp4) — content-hash keyed
│   └── decisions.py         append-only JSONL log
│
├── adapters/                Renderer Protocol implementations
│   ├── _base.py             Renderer Protocol, RendererRegistry, RenderContext, RenderResult
│   ├── cutout/              the v0.1 backend (real)
│   │   ├── easing.py        named presets + cubic-Bézier + dispatcher
│   │   ├── channel.py       Keyframe, Channel, binary-search evaluation
│   │   ├── clip.py          Clip + LoopMode + Pose/merge_poses, evaluate(clip, t) -> Pose
│   │   ├── timeline.py      Track, PlacedClip, Timeline, evaluate_timeline -> Pose,
│   │   │                    timeline_from_scene (compiled doc -> evaluable Timeline)
│   │   │                    (these four are the EXECUTABLE SPEC of the runtime's
│   │   │                    evaluation — application is runtime.js only; the Python
│   │   │                    applier and scene graph were deleted in an#86, with
│   │   │                    node-backed parity tests pinning evaluateChannel+wrapTime)
│   │   ├── serialize.py     Pydantic models for the JS-runtime JSON contract
│   │   │                    (VisualJSON.asset_sets = per-node swap-set projection, an#87)
│   │   ├── compile.py       Shot -> CutoutSceneJSON (the bridge); projects asset_sets
│   │   │                    onto slots, validates authored swaps, sets -> hold channels
│   │   ├── path.py          stroked-path geometry: Bézier flattening + the exact
│   │   │                    spec of runtime.js pathGeometry (trim, arrowhead)
│   │   ├── shutter.py       the TEMPORAL frame-stage resolve: average a frame's
│   │   │                    sample instants (RenderContext.frame_samples); one
│   │   │                    instant keeps the old bytes
│   │   ├── render.py        Playwright headless capture + ffmpeg mux + audio overlay
│   │   │                    (rasteriser PINNED — `DETERMINISTIC_CHROMIUM_ARGS`, an#31)
│   │   └── runtime_files.py importlib.resources locator for the bundled JS runtime
│   ├── manim_adapter.py     real (when manim installed) — generates a title-card scene
│   ├── remotion_adapter.py  skeleton — clear NotImplementedError pending Phase 6+
│   └── whiteboard.py        stub
│
├── audio/                   TTS + lip-sync providers
│   ├── tts.py               TTSProvider Protocol + AudioClip, VoiceMeta
│   ├── lipsync.py           LipSyncProvider Protocol + Viseme, VisemeTrack
│   ├── offline_tts.py       OfflineTTS — silent WAV proportional to text length
│   ├── elevenlabs_tts.py    ElevenLabsTTS — needs ELEVEN_API_KEY
│   ├── offline_lipsync.py   OfflineLipSync — char→viseme distribution
│   ├── rhubarb_lipsync.py   RhubarbLipSync — wraps the rhubarb binary
│   ├── whisper_lipsync.py   WhisperLipSync — faster-whisper word timestamps
│   ├── pipeline.py          produce_audio_for_dialogue / _scene; content-hash caching
│   └── providers.py         make_tts / make_lipsync factories (string → instance)
│
├── verify/                  Verifier Protocol implementations
│   ├── _base.py             Verifier Protocol, Finding, VerificationReport, Severity
│   ├── layout.py            LayoutLintVerifier (IR-only structural checks)
│   ├── human.py             HumanInTheLoopVerifier (opens mp4, stdin y/N/r)
│   ├── media.py             helpers: detect_silence, audio_volume, ssim, extract_frames, transcribe
│   ├── media_quality.py     MediaQualityVerifier (silent audio, dialogue gaps, frozen frames)
│   └── vision.py            VisionLMVerifier (Claude vision QA)
│
└── data/                    bundled non-Python resources
    └── cutout_runtime/
        ├── index.html       loads PixiJS v7 + runtime.js
        ├── runtime.js       applySwap (the ONE swap path — any declared set, viseme incl.),
        │                    drawMouthShape, channel/timeline eval (blinks are compiled
        │                    channels since an#88 — no runtime blink pass)
        └── README.md
```

---

## 4. The six `Protocol`s and their implementations

| Protocol | Purpose | Implementations |
|---|---|---|
| `Renderer` | per-shot mp4 production | `CutoutRenderer` (real), `ManimRenderer` (real when manim installed), `RemotionRenderer` (skeleton), `WhiteboardRenderer` (stub) |
| `TTSProvider` | text → audio | `OfflineTTS` (silent placeholder), `ElevenLabsTTS` (real, needs `ELEVEN_API_KEY`) |
| `LipSyncProvider` | audio → viseme track (+ `words` when the provider has them, an#96) | `OfflineLipSync` (char-distribution), `WhisperLipSync` (word-aligned, needs `faster-whisper`), `RhubarbLipSync` (phoneme-aligned, needs `rhubarb` binary; recognizer follows the language). The compiler runs `an/adapters/cutout/coarticulate.py` over the raw track before emission (an#97): merge, suppress sub-frame tongue shapes, two-frame lead, decay before rest, and a minimum hold that votes |
| `Verifier` | verify IR ± render | `LayoutLintVerifier`, `MediaQualityVerifier`, `VisionLMVerifier`, `HumanInTheLoopVerifier` |

All four protocols are runtime-checkable; new implementations register via factories or `register_renderer(...)`.

---

## 5. The three control flows

### 5.1 `an render <dir>` (validate → audio → render → verify)

```
Project.load(dir)
├─ sync()                                        ← reconcile scene.md / ir/scene.json
├─ load SceneIR from mall["scenes"]["main"]
│
└─ render() in an/render.py
   ├─ if any dialogue & auto_audio:
   │     produce_audio_for_scene(scene, mall, tts=…, lipsync=…)
   │     ↳ stamps dialogue.audio_ref + dialogue.viseme_ref + dialogue.start + dialogue.duration + dialogue.word_timings (the provider's words, line-relative, when it has any — an#96)
   │     ↳ persists wav bytes to mall["audio"][hash], visemes JSON to mall["visemes"][hash]
   │     ↳ writes scene back to mall["scenes"]["main"] (mtime equalized)
   │
   ├─ for each shot in scene.timeline:
   │     renderer = RendererRegistry.find_for(shot)        ← matches on shot.renderer
   │     result = renderer.render(shot, ctx)
   │     ↳ cutout: compile_shot(shot, mall) → CutoutSceneJSON
   │              → spin Chromium via Playwright
   │              → load runtime + JSON
   │              → for each frame: anSetTime(t) + screenshot canvas
   │                (t = i/fps, or each of ctx.frame_samples[i], averaged)
   │              → ffmpeg mux PNG sequence → silent.mp4
   │              → ffmpeg overlay dialogue audio (anullsrc base + adelay+amix per line)
   │              → shot.mp4
   │     mall["shots"][shot.id] = mp4 bytes
   │
   ├─ ffmpeg concat per-shot mp4s → output/<name>.mp4
   └─ mall["output"][name] = mp4 bytes
```

Default verifier chain (when called via `orchestrate()`): `LayoutLintVerifier` (pre + post), `MediaQualityVerifier` (post). `VisionLMVerifier` and `HumanInTheLoopVerifier` are opt-in.

### 5.2 `an iterate <dir> "<instruction>"` (free-text → IR patches)

```
Project.load(dir)
└─ iterate(dir, instruction) in an/iterate.py
   ├─ build IterateResponse JSON schema as the reply contract
   ├─ Anthropic.messages.create(
   │     model="claude-opus-4-7",
   │     thinking={"type": "adaptive"},
   │     system=<stable IR-shape primer>,
   │     messages=[scene_json_dump (cached), schema_hint (cached), instruction]
   │   )
   ├─ parse reply leniently → IterateResponse
   ├─ apply patches to deep-copy of ir.json (set / append / delete by JSON-pointer path)
   ├─ SceneIR.model_validate(new_dict) + validate_schema + validate_semantic
   ├─ if valid:
   │     for shot_id in affected_shots: del mall["shots"][shot_id]   ← cache invalidation
   │     mall["scenes"]["main"] = new_scene
   │     mall["decisions"].append({kind: "iterate", instruction, summary, patches})
   └─ return IterateResult(success, summary, patches, affected_shots, new_scene, validation)
```

Then `an render` regenerates only the invalidated shots, reusing the rest from `mall["shots"]`.

### 5.3 `an validate <dir>` (cheap pre-flight)

`load(dir)` → `validate_schema(scene)` + `validate_semantic(scene, available_voices=…, available_characters=…)` → `ValidationReport`. No side effects.

---

## 6. Caching: content-hash everywhere, cache invalidation by deletion

The system caches at every boundary that's expensive to recompute. Cache keys are content hashes — never timestamps, never counters.

| Cache | Key | Computed by |
|---|---|---|
| TTS audio | `_stable_hash({text, voice_id, tts.name})` | `pipeline._load_or_synthesize` |
| Viseme tracks | `_stable_hash({audio_key, lipsync.name, transcript})` | `pipeline._load_or_align` |
| Per-shot mp4s | `shot.id` (the IR slice IS the input) | `render.render` — **write-only, see below** |
| Final mp4 | `output_name` | `render.render` |
| Anthropic prompt cache | scene JSON + schema hint (`cache_control: ephemeral`) | `iterate._call_claude` |

The hash is stamped onto the IR (`Dialogue.audio_ref`, `Dialogue.viseme_ref`) so the orchestrator can detect provider changes — when you swap `--tts elevenlabs` for the offline default, the new expected hash mismatches the stored one, triggering re-synthesis without an explicit force flag.

Cache invalidation is by **deletion** (`del mall["shots"][shot_id]`). There is no cache versioning; the keys are deterministic so collisions across versions are impossible.

**Correction (an#31): the per-shot mp4 cache has no read path.** `mall["shots"]` is written at `an/render.py:222` and deleted at `an/iterate.py:268`, and nothing in the package reads it — so "re-render misses the cache and recomputes" describes a miss that every render already takes. This paragraph previously said otherwise, and the consequence is load-bearing for Wave 2: a benchmark harness needs **no cache-busting machinery for pixel metrics**, because every render is already cold. Either wire the read or drop the store — but do not build against the cache described here until one of those happens. (The *audio* caches two rows above are real, are read, and do warm between runs, so they affect wall-time measurements.)

---

## 7. Key invariants to preserve

These are load-bearing. Breaking them breaks the system in subtle ways.

1. **`scene.md` and `ir/scene.json` mtimes are equalized after every store write.** Otherwise `sync` flip-flops between md and json on each load and pipeline-injected state (viseme tracks, audio_refs) gets stripped. See `ScenesStore.__setitem__` and `sync()`'s "newer wins" tolerance band.
2. **The synthetic root container in the JS runtime is not indexed.** `compile.py` emits target paths starting with the entity name (`charlie/head/mouth`), not `root/charlie/head/mouth`. The runtime's `animaLoadScene` skips the synthetic root when populating `nodeIndex`.
3. **Multiple characters are spread along x in `_layout_character_positions(n)`.** A previous bug placed every character at (0, 0) so they overlapped. The default spread is 220px; characters with the same `entity.id` between renders keep their position because the spread is index-based.
4. **Composition trees flatten to canonical FlatActions for verification and rendering.** The DSL (`sequence`, `parallel`, …) is for authoring; `flatten()` produces absolute-time `FlatAction`s that downstream stages consume. Don't reason about composition nesting at render time.
5. **`extra="allow"` on every Pydantic IR model.** Forward-compat: an older reader of a newer document survives. The cost: typos in field names don't error.
6. **`anima*` JS API names were renamed to `an*` during the package rename.** `window.anLoadScene`, `anSetTime`, etc. The Python side calls these via `page.evaluate`; both must stay synced.
7. **The ScenesStore's `"main"` key is the only supported key.** Multi-scene projects are a future feature.
8. **A substituted asset is recorded, never merely substituted.** A character whose ref is not in `mall["characters"]` gets the placeholder rig; an environment ref that names neither a store entry nor a built-in preset gets the default backdrop. Both are legitimate — an asset-less project must render — and both used to be *silent*, which is not (an#33). `compile_shot` now appends one `AssetResolutionJSON` per drawable entity to `CutoutSceneJSON.asset_resolution`, warns (`CutoutCompileWarning`) on any `fallback=True`, and raises under `strict_assets=True`. The record is load-bearing rather than decorative: a missing descriptor and a deliberately-procedural character compile to the **same scene tree**, so nothing downstream of the compiler can tell them apart. `strict_assets` threads `an render --strict-assets` → `render_project` → `render` → `RenderContext.strict_assets` → `compile_shot`; `misc/bench/crossarch.py` sets it, because a pixel measurement of the wrong picture is worse than no measurement.
9. **A ledger row's comparability is decided by its provenance, not by its numbers.** Two rows measured on different scenes, or on different x264 builds, are not "one better and one worse" — every metric in them is mutually uninterpretable. Render-side metrics are comparable across machines (pixels are ISA- and OS-invariant at a pinned Chromium build); encode-side metrics are **machine-scoped and must be refused rather than banded**, because a band wide enough to absorb an x264 build change would swallow `flat_field_deviation`'s entire crf18->23 signal. The deciding fields are `scene_contract_sha256`, `environment.encode_side.x264_sei` (verbatim) and `.isa`. Two of the four value states are null and they mean different things: `gated` (the comparison is impossible) is not `unavailable` (the check did not run), and neither is "no change", which is a prediction that can never count.
10. **A verifier that could not run must not report `passed=True`.** `VerificationReport.add` flips `passed` only on `"error"`, so an `info` Finding on a failure path is byte-identical to a clean review — which is how a dead model id, a 500, a refusal and an unparseable reply all came back as "vision LM reported no issues" (an#39). `info` is reserved for *not configured* (no key, no SDK, no render); configured-and-broken reports at `an.verify.vision.FAILURE_SEVERITY`. Relatedly, `_parse_issues` returns `None` for "no verdict" and `[]` for "empty verdict", because collapsing them is what made a refusal indistinguishable from a pass.
11. **The determinism perimeter is observed on every render and enforced by default.** `runtime.js`'s `anDeterminismReport` reports the capture page, whether any PixiJS ticker is running, every node carrying a filter, and the per-entity blink phases; `an/determinism.py::capture_violations` judges — a pure function of that dict, so the rule is testable with no browser. The report lands in `RenderResult.provenance["determinism"]` beside the verbatim Chromium and x264 argv. A breach raises `CutoutRenderError`; `AN_DETERMINISTIC=0` downgrades it to a recorded fact. The three things it watches are deterministic *by accident* today: the app is built `autoStart: false`, nothing attaches a filter, and the capture page is `index.html` while `preview.html` (seven clock calls) is staged into the same directory. **The blink phase is a pure function of the entity NAME** — renaming a corpus character re-phases every blink and moves every pixel metric — which is why the phases are stamped rather than merely correct.

---

## 8. The CLI surface

```
an init <dir>                 — create a fresh project
an validate <dir>             — schema + semantic validation
an sync <dir>                 — reconcile scene.md ↔ ir/scene.json
an render <dir>               — full pipeline → output/main.mp4
   --tts {offline,elevenlabs}
   --lipsync {offline,whisper,rhubarb}
   --output-name NAME
   --parallel {N,auto}
   --strict-assets           (fail instead of drawing a stand-in — an#33)
an iterate <dir> "<instruction>"   — free-text edit via Claude (needs ANTHROPIC_API_KEY)
   --no-apply-changes        (dry run)
   --model claude-opus-4-7   (override)
an check                      — diagnose system deps
an bench                      — render the fixed corpus, write a metrics ledger row
   --scenes NAME,NAME
   --out PATH
   --keep-render PATH        (keep the throwaway render tree instead of deleting it)
   --quiet                   (print only the ledger path)
   --bless "<reason>"        (re-write the golden frames, recording this reason)
   --compare PATH            (compare this run against a baseline row)
an bench-compare              — two ledger rows in, a verdict or a REFUSAL out
   --before PATH --after PATH   (default: the two newest committed rows,
                                 ordered by `generated_at`, not by filename)
   --mutation NAME           (evaluate the per-mutation predictions instead)
   --strict                  (exit nonzero on a regression, an unmet criterion,
                              or a row it cannot read at all)
   --raw                     (JSON instead of the human digest)
an bench-mutants              — break each guard on purpose; the named test must go red
   --names A,B
   --quiet
an impacts clip OUT_DIR       — one synthetic impact clip + ground-truth sidecar
   --object stick|ball --kind surface|air --tempo 100|0:90,16:120
   --fps --exposure --timestamp-jitter-sd --jitter-sd --no-render
an impacts clip-set OUT_DIR   — the product of objects x kinds x fps x shutter, + index.json
```

All built via `typer` over the SSOT list `an.tools._dispatch_funcs` — wired
programmatically in `an/__main__.py`, never as decorators on the functions, so
the business layer carries no CLI types. Typer (MIT) replaced argh (LGPL-3.0)
in an#45; `argcomplete` went with it, since it hooks argparse specifically —
shell completion is now `an --install-completion`.

---

## 9. The `scene.md` markdown contract

```markdown
# <title>

```yaml meta
title: ...
duration: 12
fps: 24
resolution: { width: 640, height: 360 }
default_renderer: cutout
```

## Shot s1 (cutout)

```yaml shot
duration: 6
camera:
  move: push_in        # hold | push_in | pull_out | zoom_in | zoom_out
```

```yaml entities
- { kind: environment, id: park_bg, store: environments, ref: park }   # park | indoor | night | sunset | default
- { kind: character,   id: charlie, store: characters,   ref: charlie-v1 }
- { kind: character,   id: maya,    store: characters,   ref: maya-v1 }
```

```yaml actions
- { kind: tween, target: charlie, property: x, from: -110, to: -80, duration: 2.0, easing: ease_in_out }
- { kind: tween, target: charlie/torso, property: rotation, to: 0.05, duration: 0.5, start: 1.0 }
- { kind: set,   target: maya/head, property: y, value: -10, at: 3.0 }
```

```dialogue
charlie [thinking]: Did you ever wonder why we always meet here?
maya [amused]: Because the pigeons trust us.
```
```

The `[emotion]` brackets on dialogue lines are sugar for an `expression` leaf over the line (an#98): `an/expression/presets.py` holds the presets (`neutral / happy / sad / angry / surprised / afraid / disgusted / thinking / skeptical / amused`), the face solver `_add_face_clips` in compile.py sums them into one channel per `(node, property)` — brows, lids, and the mouth's `viseme@<form>` set — and an unknown name is a validate error, not a silent neutral.

---

## 10. What hasn't shipped

This section previously listed four "phases that haven't shipped yet" — real
character art, per-shot parallel rendering, live preview, and asset promotion.
**All four have since shipped** (`svg_sprite` visuals in `compile.py` +
`makeSvgSprite` in `runtime.js`; `an render --parallel auto|N` via
`_resolve_parallel`; `an preview` via `preview_project()`; and promotion as
`an.characters.promote` — not `an.assets.promote`, which never existed). They
are described in their own sections above.

What genuinely remains, in rough priority order (each item re-checked against the code on 2026-09-29; the full gap and sharp-edge list is `misc/docs/sharp_edges.md`):

1. **A real shot-to-Manim compiler.** `_render_script` in
   `an/adapters/manim_adapter.py` emits a single `Text(title)` title card of the
   right duration. No entity, action, dialogue or camera information from the
   Shot reaches the generated script. Translating the flat timeline into Manim
   constructs is unstarted design work, not a wiring job.
2. **`ping_pong` has no emitter, and placements cannot override a clip's
   loop.** Both evaluators honour all three `loop_mode`s (`runtime.js`
   `wrapTime`, `clip.py` `_wrap_time`), and since an#7 a `play` of a looping
   descriptor animation compiles to `loop_mode="loop"` (`_resolve_play`) — so
   the old line here, "nothing ever emits a non-default loop_mode", is closed.
   What remains: no compiler path writes `ping_pong`, and `PlacedClipJSON` has
   no `loop_mode` of its own (issue #7's step 2, deferred until clip dedup
   exists; per-instance `__play__{n}` clips make it unnecessary today —
   tracked as an#94).
3. **Lip-sync for face-baked characters.** A descriptor declaring
   `face_overlay: false` (DiceBear avatars; the 0.3.0 migration derives it from
   the old provenance string) has the face baked into the head SVG, so the
   compiler suppresses both the overlay mouth and the viseme channel. Those characters speak without
   moving their mouths. Hand-rigging (see `examples/promote_demo/`) is the
   production path today.
4. **Multi-scene projects.** `"main"` is the only key the scenes store supports.
5. **The default timing is smooth, and the ledger cannot argue otherwise.**
   `step_hz` (an#89) steps authored tweens on demand (`Meta.step_hz` /
   `Shot.step_hz` / `an render --step-hz`), camera and blinks exempt by
   construction. Whether to flip the default to "on twos" is a temporal,
   aesthetic judgement: measured, stepping moves the scene contract hash on
   every scene with a tween, so `bench-compare` refuses a stepped row before
   any family is examined, and outside the comparer the per-frame families
   move with the pose content in both directions — no lever could be
   registered (the `pix_fmt` precedent, one step earlier). Epic #9's Decision
   5 asked for "the ledger and a human A/B agreeing"; the ledger half is
   withdrawn on that measurement. The A/B is the `stepped-timing` demo, with
   its frame strip committed at `misc/docs/step_hz_side_by_side.png` (smooth
   left, 6 Hz right); the flip is a one-line PR that only the maintainer
   makes, and it has not been made.
6. **A real `an validate` for everything the renderer refuses.** The pre-flight
   reports the IR-level refusals (unknown `camera.move`, `narration`; `prop`
   entities stopped being one in an#108, which made them drawable, and
   `_DRAWABLE_ENTITY_KINDS` is pinned equal to the compiler's dispatch by test;
   `play` is resolved against the target's descriptor animations
   since an#7), and since an#109 it no longer duplicates the compiler's camera
   list — both call `an.ir.camera.camera_keys`, so a move that validates cannot
   then raise at compile. It still cannot see rig-level problems: a speaker
   whose character has no head is discovered at compile time. Since an#111 it
   also **warns** when a camera translates over a stage with no depth — the
   render is correct, the whole picture slides, and that is also exactly what a
   flattened parallax looks like.

---

## 11. Test architecture

Run `pytest -q` for the current count — a number written here only goes stale.
The suite is layered:

- **Doctests** in module docstrings cover the public API of each module (composition flatten times, channel snap semantics, easing endpoints, etc.).
- **Pytest** for cross-cutting checks: store roundtrips, IR migration chaining, sync flip-flop regression, mall conformance, multi-shot concat audio, multi-character render distinct.
- **Live API tests** are gated on an explicit positive opt-in — `AN_LIVE_API_TESTS=1` **and** `CI` unset — not on a key being present. That distinction is the whole point: the previous "skip-if-key-missing" gate was satisfied by every developer machine and every agent session that had sourced a shell profile, so a plain `pytest -q` once made real, billed ElevenLabs calls and reported PASSED. The switch is defined in the **package** (`an/live_api.py`) rather than in `conftest.py`, because the test suite is not the only thing that must refuse to spend unasked: `examples/character_gallery/build.py` reads the same predicate before choosing ElevenLabs (an#63 — it chose on key-presence alone, and an example is the first thing a new user runs, on a clean checkout where the audio cache is cold), and an example cannot import a conftest.
- **The suite is offline and hermetic, and a guard enforces it.** `tests/conftest.py` refuses *and records* non-loopback socket use; `hermetic_browser` does the same at the Playwright layer, because a socket patch cannot see Chromium.
- **Silent discards raise.** Seven places that accepted something and produced nothing now raise typed errors; `an validate` reports the IR-level ones before any money or browser is spent. See `misc/docs/wave1_verification.md` §4.
- **End-to-end render tests** (skip-if-ffmpeg-or-chromium-missing) that produce real mp4s and assert structural properties (audio stream present, frames change, characters distinct).

The project's CI runs the offline subset; a developer machine with all dependencies installed runs the full suite (~70s).

---

## 12. References to the design space

The seven research reports next to this file describe the design space:

- `report 0 - Text-to-Structured-Animation.md` — orchestrator architecture, IR layering, MoVer-style verification (the spec's spine)
- `report 1 - The 2D cutout animation ecosystem...md` — JS-side ecosystem survey (PixiJS chosen)
- `report 2 - Animation interchange formats...md` — schema-level analysis of 12 animation formats (informed the IR shape)
- `report 3 - Facial Animation, Lip Sync & Expression Systems...md` — viseme conventions, Rhubarb, Cohen-Massaro
- `report 5 - Scene Graph Architecture & Animation System Design Patterns.md` — Python sketch for the cutout backend (closest to what was actually built)
- `dsl_design_patterns_report.md` — DSL design (informed the Pydantic IR + composition primitives)
- `Annotation systems...md` — interval data structures, rational time, A/V sync

When a subsystem is being extended, read the matching report before designing.

---

## 13. Related packages

- [`shaping`](https://github.com/thorwhalen/shaping) — turns 2D figures into parametrized 3D objects (to view, animate, 3D-print or engrave), in the browser. Its ADR 0002 records the relationship: its animation tracks use `an`'s model (a property path into the document, `set` / `tween` with an easing, combinators flattened to absolute times), with the JSON shape kept compatible so a track written for one can be read by the other. **Neither package depends on the other**; the link is a shared format and shared research, not an import, so a change to the track format here is a change to check against `shaping`. What `an` may want from it: turntable and parameter-sweep renders of 3D objects as scene assets, and its 2D-to-3D transforms to give depth to flat artwork.
- [`tituli`](https://github.com/thorwhalen/tituli) — text in video (title cards, credits, captions with attribution, lower thirds, calligrams) from one layout model, rendered with Pillow and composited with ffmpeg. The boundary: `tituli` owns typesetting (and typeset text frames for video `an` did not render); `an` owns the scene, its timeline and the rig, and `an/credits.py` only works out what a project owes, not how it is typeset. Since an#155 `an` depends on it (plus `fonttools`, its `outlines` extra, declared by name): `an.text.layout_text` takes tituli's placed `Run`s and each run's contours (`run_outline`) and compiles them into SVG-sprite nodes.
