# ADR 0001 — `an` is the core; genres are packages that depend on it

**Status:** Accepted, 2026-10-01 (the maintainer delegated the decision; choices recorded in `misc/docs/plan_core_and_cutan_2026-10.md` §1) · **Decider:** the maintainer · **Related:** an#225 (the split), an#9 (the epic that built the cut-out genre), `misc/docs/framework_review_2026-10.md` §2–3 (the measured coupling), `misc/docs/core_from_three_genres.md` (the three-genre evidence), ADR 0002, ADR 0003, ADR 0004

**Revised 2026-10-01 with manimkit/previz evidence.** The first version inferred the core from `an` alone. The revision tests it against two more genres the fleet already builds, Manim-based explainer animation (`manimkit`) and view-state animation (`previz`), with `burns`, `walkthru` and `shaping` as further evidence (`misc/docs/core_from_three_genres.md`). What changed: the boundary test (Decision 1); Decision 5, which no longer puts the stage runtime inside the core; and the new Decisions 10–14 (the timing kernel as a cross-language contract, declared field kinds and property spaces, three renderer tiers, how Manim and `previz` plug in, the import firewall). Decision 8(a) gains three steps. The status is unchanged.

## Context

The maintainer's vision (2026-10-01):
- Structured animation covers cut-out animation, data visualisation and mathematical-concept visualisation.
- All of them define **drawables** and apply **transforms** over time. Those transforms must not be defined three times, and neither must the **semantic layer** that turns a description into transforms, nor its MCP surface.
- `an` becomes the **core** for every genre. A genre that has developed enough breaks off into its own package that depends on `an`.
- Cut-out animation is the first such genre. Its package name is still open (an#225).

Measured on 0.1.124 (review §2), of about 52k lines:
- about 45% is cut-out-specific;
- about 24% is instruments built on the cut-out renderer;
- about 10% is clean core;
- about 14% is core-shaped modules that hard-code cut-out knowledge.

The architectural *pillars* are genre-neutral. The *code* is not. Closed vocabularies are the main obstacles:
- The IR's `Action` is a closed Pydantic discriminated union (`an/ir/schema.py`), consumed when `Shot` is defined.
- `compose.flatten` / `duration_of` raise on any other type.
- `AssetRef.kind` is a closed `Literal`, and so is `RendererName` (`an/base.py`). Meanwhile `register_renderer` is already open, so the IR rejects renderer names the registry would accept.
- The action-kind list is repeated at six dispatch sites: the sync reader and writer, `duration_of`, the compiler, validate, and the iterate prompt.
- `validate_semantic` is one function that imports characters, expression and the cut-out compiler.
- `render.py` imports the cut-out compiler.
- The timing evaluator (easing, channels, clips, timeline) lives under `adapters/cutout/`.
- The 5.7k-line `compile.py` mixes neutral scene building with the rig, face and viseme passes.

One extension point already has the right shape: the per-kind migration registry (`register_kind`, `register_migration`). Characters, props, environments, styles, paths and text all self-register into it.

**Evidence from the other genres (added in the revision).** One genre cannot show which of its parts are general; three can. Compared concept by concept (`core_from_three_genres.md` §2):
- **All three share one evaluation model:** addressed properties, each with a field kind that picks its interpolator, keyed over time with easing, flattened to absolute times, evaluated by a pure `at(t)`. `an` calls the result a `Pose`; `previz` a view state from `reel.at(t)`; `burns` `evaluate(t)`. This **timing kernel** exists in five copies today (`an` in Python and JS, `previz`, `burns` in two languages, and `shaping`'s copy of `an`'s track format), already drifting (`ease_in_out` is quadratic in `an`, cubic in `shaping`, the CSS curve in `previz` and `burns`).
- **`previz` is ahead on the kernel:** seven *declared* field kinds (linear and log numbers, shortest-arc angles, vectors, quaternions, OKLab colours, orbits, discrete with a `switchAt`), a committed JSON Schema and golden vectors, and an engine contract whose capabilities are read from the members an engine implements. `an` chooses the interpolator from the runtime type of the value and has two kinds.
- **`an` is ahead on everything around the kernel:** the versioned scene document, shots and film assembly, narration, captions and sound, verifiers, stores, the semantic layer in the making.
- **Manim does not fit the kernel.** Its state is Python objects mutated by `play` calls, with no addresses, no `at(t)` and no seeking. It can join only as a back-end that renders a whole shot and owns its clock.
- **Verification is three families** (contract, static, rendered), each present somewhere and none everywhere: `manimkit` checks rendered geometry after every beat and builds a contact sheet; `an` checks the IR and measures pixels; `previz` checks its kernel with golden vectors.

## Decision

1. **The boundary rule.** A thing belongs in `an` if a data-viz or math-viz genre would need it unchanged, that is, if it can be stated without the words character, face, mouth, rig or a style's name. Otherwise it belongs in the genre package. Review §3.1 applies the rule module by module.

   *Revised:* the test is now three real genres rather than hypothetical ones. A concept is core if at least two of cut-out (`an`), explainer (Manim via `manimkit`) and view-state (`previz`) animation need it in the same form, or if it is a contract every back-end must meet (time, addresses, field kinds, easing, the frame clock). It must also be statable without naming an engine (PixiJS, Manim, a WebGL viewer). `core_from_three_genres.md` §5 applies the revised rule module by module, with three destinations: the core, `an.stage` and `cutan`.

2. **The IR is open at the type level; genres register, never edit.** A registry that rebuilds the Pydantic `Action` union whenever a kind registers would be an ordering trap:
   - `Shot` and every cached `TypeAdapter` would need `model_rebuild()`;
   - a document with `kind: play` would fail validation if the genre had not been imported yet;
   - discovery triggered from inside `an.ir.schema` would make the genre import the schema back, a cycle.

   Instead:
   - The schema's action union holds the core kinds plus one open member, `ExtensionAction` (`kind: str`, `extra="allow"`). A callable discriminator selects it for any kind the core does not define.
   - Registered kinds are validated by their own models through the registry: at `validate_semantic`, at `flatten`, and in the compiler. An unregistered kind is an error naming the genre packages that could provide it.
   - `AssetRef.kind` and `renderer` become `str` in the schema and are validated against their registries in `validate_semantic`, not by the schema.

3. **Discovery is explicit, never at import time.** `an.genres.load()` reads the `an.genres` entry points. It is called by `Project.load`, by the CLI entry and by the MCP entry, and it can be called directly. Importing `an` alone loads nothing.

4. **Registries, in two batches.** The first batch is what the split needs:
   - action kinds, each with its `flatten`, duration, and `scene.md` reader/writer hooks;
   - entity kinds;
   - compile passes;
   - semantic-validation checks;
   - a post-audio hook (where the viseme step attaches);
   - the vocabulary registry (ADR 0003);
   - the capability registry (ADR 0002).

   The second batch is deferred until a second genre needs it: stores (overrides can already swap one), CLI namespaces (already a dict in `an/tools.py`), and runtime visual kinds (two procedural kinds today, about 25 lines of `runtime.js`).

5. **The shared stage runtime stays in the `an` distribution, but outside the core.** *(Revised; the first version said "stays in the core".)* The 2D keyframed scene-graph player (`runtime.js`, its JSON contract, the Playwright frame capture) is about 90% genre-neutral, and data viz and math viz need its paths, text, planes and camera, so it ships with `an` as **`an.stage`**, the default engine. But the other genres show it is one engine among several: Manim draws explainer shots and `previz` engines draw view states, and neither uses it. So `an.stage` sits behind an `an[stage]` extra (Playwright), and the core never imports it (Decision 14). The procedural `mouth` and `eye` visuals move to the genre.

6. **Speech is core; the mouth is genre.** TTS, voices, word timings, captions and the sound layer stay in `an`. Visemes, co-articulation, the face solver, expressions, gaze and blinks move to the genre.

7. **The pixel gate stays with the core.** Before any module leaves:
   - The core keeps a **core corpus**: paths, text, planes, camera and transitions, rendered by the stage runtime with no character, and with goldens and contract hashes of its own.
   - The genre's corpus runs against `an`'s default branch on a schedule and on demand. A core release that breaks it is reverted or followed by a genre release the same day.
   - The `run-browser-tests` rule applies in both repositories.

8. **Order of work: expand → migrate → contract.** The gate for every step is byte-identical corpus contract hashes.
   - **(a) Seams inside `an`:**
     - the open IR (Decision 2);
     - the first-batch registries;
     - timing moved to `an/timing`, and ffmpeg helpers moved to `an/media`;
     - `validate_semantic` split into registered checks;
     - a compile-pass registry;
     - the core corpus;
     - *(added in the revision)* the kernel contract: the field-kind registry, with declarations that reproduce today's behaviour exactly, and the contract files of Decision 10;
     - *(added)* the `Engine` protocol, `frame_stage_renderer`, `an.stage` as the first engine, and the import firewall test (Decisions 12 and 14);
     - *(added)* the first non-cut-out renderer: Manim opaque-source shots (Decision 13). With the core corpus, it shows that `an` renders without cut-out code before any module leaves.
   - **(b) Create the genre package.** Move the cut-out modules, and leave warning re-export shims in `an`.
   - **(c) Remove the shims** one release later.

   Steps (b) and (c) wait until step (a) and Decision 7 are in place. An `an[cutout]` extra that depends on the genre package keeps the one-command install. The genre declares the lowest `an` it supports; `an` itself pins nothing.

9. **Persisted identifiers do not change.** These all stay as they are:
   - `renderer: cutout`;
   - the document-kind names;
   - the `cutout_animation` genre slug registered with `nw`;
   - the compiled document's wire shape, which the bench hash-pins.

   The split moves files. It renames nothing that is stored. `an.stage`'s renderer claims both `stage` (new) and `cutout` (persisted); a `cutout` shot that uses a cut-out kind fails validation with an install hint when `cutan` is absent.

10. **The timing kernel is a cross-language contract, not a module.** *(Added in the revision.)*
    - Its content: the address grammar, the field-kind registry, the easing registry (each entry with its solver), the authored flat timeline *and* the compiled form `an` evaluates (tracks, placed clips, loop modes, channels; active / held / at-rest; write groups), a sparse `at(t)` plus rest values, and `an`'s frame clock (`k / fps`, `max(1, round(duration · fps))`) (`core_from_three_genres.md` §2.2–2.5).
    - Its contract files live in `an` (public, the core): `easing.json`, `kinds.json`, `timeline.schema.json`, `compiled.schema.json` and `timing_vectors.json` (documents and the state at a list of times; numbers within 1e-9, everything else exact). `previz`'s golden format is the template and its cases the seed.
    - The gate for a kernel change is not the contract hash alone, which covers the compiled document and not its evaluation: hashes, the Python/JS parity tests, the pure-pose tests and the decoded-pixel goldens.
    - Two implementations assert the vectors: Python in `an.timing`, TypeScript in `previz`. `runtime.js` stays a bit-exact mirror of `an.timing` through its existing parity tests. `shaping` validates its tracks against `timeline.schema.json`; `burns` takes its easing from the shared table.
    - Easing names: CSS names mean exactly the CSS curves; `an`'s underscore names stay as their own versioned curves (never silently aliased); Manim's rate functions are entries too.

11. **Entity kinds declare property spaces; field kinds are declared, never inferred.** *(Added.)*
    - An address is `<entity>[/<node>…]:<field>[@<qualifier>]`, the field possibly a dotted path; a `previz` view state is the property space of one entity.
    - An entity kind registers its property space: property pattern → field kind, plus aliases and write groups, a unit per numeric field, and the display / build split. Validation of an action's target against it is generic, which is what keeps the open IR of Decision 2 strict.
    - The kinds are seeded from `previz`'s seven, parametrised: `number(space)`, `angle`, `vector`, `quaternion`, `color(space)`, `orbit`, `discrete(switch_at)`. An undeclared property is `discrete`. Discrete is defined on *time*: `b` shows iff `t >= a.time + switch_at · span`, and `switch_at == 1` is `t >= b.time` with no arithmetic (the an#86 rule, which `previz` adopts).
    - `an`'s current output is reproduced by declaration: the stage node's transform properties, `tint_r/g/b` and the camera's `x`, `y`, `zoom`, `rotation` are plain `number`; swap channels, including every `@`-qualified set, are `discrete(switch_at=1)`. `tint` stays a compiler expansion into three numbers, so the wire shape does not change. New genres get log zoom, shortest-arc angles and OKLab colour by default.

12. **Three renderer tiers.** *(Added.)*
    - **`Renderer`** (exists): shot → media file. Every back-end is reachable through it, so assembly, captions, sound and caching treat all shots alike.
    - **`Engine`** (new): a seekable engine, state or time → frame. `frame_stage_renderer(engine)` turns one into a `Renderer` with the core's clock, capture loop, supersampling and sinks. Engines are time-driven (they evaluate the channels themselves, as `runtime.js` does, and must pass the kernel vectors) or state-driven (the core evaluates `at(t)`, as `previz` does).
    - **Live engine:** apply, settle, capture in real time (`walkthru`). Declared, not built.
    - An engine's tier and features (alpha, `bounds` for the layout verifier, `project` for anchored overlays) are derived from the members it implements (ADR 0002 applied to engines).

13. **How the other genres plug in.** *(Added.)*
    - **Manim, step 1:** the title-card skeleton becomes a `Renderer` for opaque-source shots (`options.source`, `options.scene`), delegating to `manimkit` as a soft dependency; its layout warnings and contact sheet become `Finding`s located by source line, its duration is filled from the render and written back (it cannot be authored), and its cache key is the source's content hash plus the Manim version and quality. **Step 2**, when wanted: a math-viz genre with entity kinds (axes, graphs, formulas), action kinds (`create`, `write`, `transform`, `indicate`) and vocabulary seeded from `manimkit`'s corpus, compiling to Manim and, for the subset it can draw, to `an.stage`. Whether it lives in `manimkit` behind an extra or in its own package is deferred.
    - **`previz`** stays a separate TypeScript package: the TypeScript implementation of the kernel (Decision 10), a back-end for shots whose entity is an engine view (exported to a `previz.sequence`), and a source of vocabulary entries (its formulas, exported as JSON-described entries for ADR 0003's registry and MCP).

14. **The import firewall.** *(Added.)* A test asserts that no core module imports `an.stage`, a genre package, Playwright, Manim or `manimkit` at module level. Back-ends are optional, with typed, install-hinting errors.

## Alternatives considered

- **Keep one package, with a `an.genres.cutout` subpackage, and enforce the boundary with an import rule.** An import linter, for example a contract that `an` must not import `an.genres.*`, enforced in CI.
  - Its engineering merits are real: one release, one CI, the pixel gate stays where it is, and no version ratchet across repositories.
  - Step 8(a) is the same work either way, which is why it comes first.
  - Not chosen as the end state, for two reasons. The maintainer asked for a package per mature genre. And a separate package is the only boundary a downstream user can see and depend on, for instance a data-viz user who installs `an` without the cut-out weight (Playwright pins, character tooling).
  - **It is the right interim state if step (b) is not reached soon.**
- **Extract the core under a new name (`an-core`) and leave `an` as the cut-out package.** This keeps today's `pip install an` users on cut-out. Rejected: the vision names `an` as the core, and a genre-neutral core should own the short name.
- **A third package for the stage runtime,** shared by cut-out, data viz and math viz. Defensible later, if a genre needs a different runtime. Rejected for now: there is no second consumer yet. *(Revision:)* the three-genre evidence shows the other genres use *other* engines rather than this one, so the runtime is not shared core; `an.stage` inside the `an` distribution, behind an extra and a firewall (Decision 5), gives the same boundary without a third repository.
- **Make `previz` the core** (it has the better kernel). *(Added.)* Rejected: `previz` is TypeScript-only, private, and deliberately has no scene document, shots, narration, verifiers or stores. Its kernel contract is adopted instead (Decision 10).
- **Compile an IR to Manim before supporting opaque Manim scenes.** *(Added.)* Rejected as the first step: it is the expensive half, and opaque-source shots already give Manim the core's narration, assembly, caching and verification, and prove the core renders without `cutan`.
- **Keep inferring the interpolator from the value's runtime type** (today's `an`). *(Added.)* Rejected: it cannot express an angle, a log zoom or a colour space, and `previz` showed that declaration is what makes those possible. Declarations reproduce today's output exactly.
- **Split per layer** (an IR package, a render package, …). Rejected: it cuts along the seams that already work and leaves the cut-out knowledge where it is.
- **Pydantic union rebuilt at registration.** Rejected for the ordering reasons in Decision 2.
- **`pluggy` hooks instead of entry points plus registries.** `pluggy` gives ordered, multi-implementation hooks with a declared spec, and it would suit the compile passes. Not chosen yet. Entry points are standard library and enough for discovery, and a hook spec can wrap the compile-pass registry later without changing any genre.
- **Lottie or Rive as the compiled wire format** instead of the bespoke compiled shot document. That would give portable players and editor round-trips. Rejected for now:
  - the bench hash-pins the current contract;
  - neither format has `an`'s swap channels or its stepped timing as first-class concepts;
  - an exporter can be added later as a second `Renderer`.

## Consequences

- **Gains.**
  - A data-viz or math-viz genre can start without touching core dispatch code.
  - *(Revision)* One timing contract replaces five drifting copies across the fleet, and Manim and `previz` shots join the same film, narration and verification as cut-out shots.
  - The core can no longer import genre code.
  - One vocabulary, one capability registry and one build graph serve every genre.
- **Costs.**
  - Step 8(a) is large: `schema.py`, `compile.py`, `validate.py`, `sync.py` and `render.py` all change.
  - *(Revision)* The contract files bind two languages: a change of meaning in the kernel is a coordinated change in `an` and `previz`, guarded by the shared vectors.
  - There are two repositories to release in step.
  - Tests and doctests that use `renderer="cutout"` inside core modules must move, or switch to the core test renderer.
- **Stays awkward.**
  - `Dialogue` carries `emotion` and `viseme_*`. In v1 they remain optional fields that the core ignores. A later schema version, with a migration, moves them into a genre extension namespace.
  - The bench and impacts move with the cut-out genre. Their pixel-generic modules (metrics, PNG, ledger, compare) serve the core corpus too, so they stay in the core.

## First slice

Make the action union open (Decision 2): `ExtensionAction` plus a callable discriminator, with the registry consulted by `flatten`, `duration_of`, validate and the compiler. `PlayAction` and `ExpressionAction` then register from `an/characters` and `an/expression`, still inside `an`. The gate: every corpus contract hash unchanged, and a test that a document with `kind: play` validates only after `an.genres.load()`, or the in-repo registration, has run.

*(Revision)* A second first slice, independent of the first and as cheap: move timing to `an/timing`, add the field-kind registry with the declarations of Decision 11, and commit `timing_vectors.json` seeded from `previz`'s cases and `an`'s parity cases. Gate: contract hashes unchanged, and the vectors pass in Python.

## Related

- Review: `misc/docs/framework_review_2026-10.md` §2–3, and its fleet-level addendum.
- Three-genre evidence: `misc/docs/core_from_three_genres.md`.
- Cut-out review: `misc/docs/cutout_framework_review_2026-10.md`.
- Principles: `misc/docs/design_principles.md`, principle 3.
