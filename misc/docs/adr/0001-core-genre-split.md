# ADR 0001 — `an` is the core; genres are packages that depend on it

**Status:** Proposed, 2026-10-01 · **Decider:** the maintainer · **Related:** an#225 (the split), an#9 (the epic that built the cut-out genre), `misc/docs/framework_review_2026-10.md` §2–3 (the measured coupling), ADR 0002, ADR 0003, ADR 0004

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

## Decision

1. **The boundary rule.** A thing belongs in `an` if a data-viz or math-viz genre would need it unchanged, that is, if it can be stated without the words character, face, mouth, rig or a style's name. Otherwise it belongs in the genre package. Review §3.1 applies the rule module by module.

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

5. **The shared stage runtime stays in the core.** The 2D keyframed scene-graph player (`runtime.js`, its JSON contract, the Playwright frame capture) is about 90% genre-neutral, and data viz and math viz need its paths, text, planes and camera. The procedural `mouth` and `eye` visuals move to the genre.

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
     - the core corpus.
   - **(b) Create the genre package.** Move the cut-out modules, and leave warning re-export shims in `an`.
   - **(c) Remove the shims** one release later.

   Steps (b) and (c) wait until step (a) and Decision 7 are in place. An `an[cutout]` extra that depends on the genre package keeps the one-command install. The genre declares the lowest `an` it supports; `an` itself pins nothing.

9. **Persisted identifiers do not change.** These all stay as they are:
   - `renderer: cutout`;
   - the document-kind names;
   - the `cutout_animation` genre slug registered with `nw`;
   - the compiled document's wire shape, which the bench hash-pins.

   The split moves files. It renames nothing that is stored.

## Alternatives considered

- **Keep one package, with a `an.genres.cutout` subpackage, and enforce the boundary with an import rule.** An import linter, for example a contract that `an` must not import `an.genres.*`, enforced in CI.
  - Its engineering merits are real: one release, one CI, the pixel gate stays where it is, and no version ratchet across repositories.
  - Step 8(a) is the same work either way, which is why it comes first.
  - Not chosen as the end state, for two reasons. The maintainer asked for a package per mature genre. And a separate package is the only boundary a downstream user can see and depend on, for instance a data-viz user who installs `an` without the cut-out weight (Playwright pins, character tooling).
  - **It is the right interim state if step (b) is not reached soon.**
- **Extract the core under a new name (`an-core`) and leave `an` as the cut-out package.** This keeps today's `pip install an` users on cut-out. Rejected: the vision names `an` as the core, and a genre-neutral core should own the short name.
- **A third package for the stage runtime,** shared by cut-out, data viz and math viz. Defensible later, if a genre needs a different runtime. Rejected for now: there is no second consumer yet.
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
  - The core can no longer import genre code.
  - One vocabulary, one capability registry and one build graph serve every genre.
- **Costs.**
  - Step 8(a) is large: `schema.py`, `compile.py`, `validate.py`, `sync.py` and `render.py` all change.
  - There are two repositories to release in step.
  - Tests and doctests that use `renderer="cutout"` inside core modules must move, or switch to the core test renderer.
- **Stays awkward.**
  - `Dialogue` carries `emotion` and `viseme_*`. In v1 they remain optional fields that the core ignores. A later schema version, with a migration, moves them into a genre extension namespace.
  - The bench and impacts move with the cut-out genre. Their pixel-generic modules (metrics, PNG, ledger, compare) serve the core corpus too, so they stay in the core.

## First slice

Make the action union open (Decision 2): `ExtensionAction` plus a callable discriminator, with the registry consulted by `flatten`, `duration_of`, validate and the compiler. `PlayAction` and `ExpressionAction` then register from `an/characters` and `an/expression`, still inside `an`. The gate: every corpus contract hash unchanged, and a test that a document with `kind: play` validates only after `an.genres.load()`, or the in-repo registration, has run.

## Related

- Review: `misc/docs/framework_review_2026-10.md` §2–3.
- Cut-out review: `misc/docs/cutout_framework_review_2026-10.md`.
- Principles: `misc/docs/design_principles.md`, principle 3.
