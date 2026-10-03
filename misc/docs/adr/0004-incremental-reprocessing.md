# ADR 0004 — Incremental re-processing through a content-addressed build graph

**Status:** Accepted, 2026-10-01 (the maintainer delegated the decision; choices recorded in `misc/docs/plan_core_and_cutan_2026-10.md` §1) · **Decider:** the maintainer · **Related:** pillar 11 (`CLAUDE.md`), `architecture_as_built.md` §6, Wave 5 research §12, `an/genre.py`, the sibling packages `lacing` and `nw`, ADR 0001, ADR 0002, ADR 0003, the asset-library design (`misc/docs/asset_library_design.md`, ADR 0005)

## Context

The vision makes this a requirement, not a nice-to-have. A draft must always be adjustable without re-processing everything: change one line of dialogue, one colour in a style pack, one character's art or one shot's camera, and only what depends on it is redone. The fleet's linked-artifact packages, `lacing` and `nw`, exist for this purpose.

### What `an` does today

- **Audio is incremental.** TTS audio and viseme tracks are keyed by content hashes, stamped on the IR (`audio_ref`, `viseme_ref`), and read back.
- **Pictures are not.**
  - The per-shot mp4 store is **write-only**: `render_project` renders every shot, every time.
  - `an iterate` "invalidates" shots by deleting entries from a store that nothing reads.
  - `shot.id` is chosen by the author, so it is not a content key.

### Ingredients that already exist

- `scene_contract_sha256` hashes the compiled shot document.
- `runtime_sha256` identifies the runtime.
- The bench's environment probe records the Chromium build, the ffmpeg identity and the ISA.
- Text records each font's identity.

### Gaps

1. **SVG art is keyed by path.**
   - Raster art has been content-addressed since an#211: a digest goes into the texture alias and the src.
   - SVG art keeps a plain alias, deliberately, so that existing documents stay byte-identical.
   - So editing an SVG drawing in place does not change the compiled document.
2. **The shot render reads more than the compiled document.**
   - It muxes dialogue audio fetched by `audio_ref`.
   - Its pixels depend on the browser build, the Playwright version, ffmpeg and the fonts.
3. **Art bypasses the mall.**
   - `_raster_digest` and the art-size probe read the filesystem behind the store (`store._root`).
   - So a wrapper that records reads through the mall would see nothing for art.
   - This is the same gap as "`dol` is declared but never imported".
4. **Nothing reads a cache before rendering.**

### What the fleet offers

**`lacing`** (dependencies: pydantic, intervaltree, `cw`, `dol`):
- `Artifact`: a content-addressed artifact record. `asset_id` is the SHA-256 of the bytes, and the record carries W3C-PROV-style provenance.
- `ArtifactStore`: a `MutableMapping` catalog plus a blob store, both injected `dol` mappings.
- `annotation_value_digest`: a canonical digest of a value, which enables **early cutoff**.

**`nw`** (built on lacing):
- A `Transform` protocol, with `impl_version` salting its cache keys.
- Deterministic fan-out keys.
- `freshness`: verifying traces in the style of Salsa and Shake. Each derived write records the digests of its inputs; staleness is checked by comparing digests, never mtimes.

**Where `nw` does not fit yet:**
- Its project layout is hard-wired (`_scope_paths`).
- Its dependency closure is heavy (`falaw`, `au`, `artful`, `xdol`).
- Its shot workflow is built for music videos.
- `an/genre.py` already declares `an`'s genre to `nw` as *planned*.

## Decision

1. **An explicit build graph in the core, over these stages.** Each stage is a pure function of the digests of its inputs.

   ```
   scene document ─▶ per-shot IR slice (after semantic resolution, ADR 0003)
   dialogue line ──▶ TTS audio ──▶ word timings ──▶ (genre) visemes
   per-shot IR slice + assets it reads + style + vocabulary versions + capability derivation ─▶ compiled shot document   ◀── early cutoff here
   compiled shot document + its audio + runtime + render environment + render knobs ─▶ shot mp4
   shot mp4s + transitions + sound + captions ─▶ film
   ```

2. **Every key covers everything that changes the output.**
   - **The compile key** folds in:
     - the IR slice;
     - the **content digest of every texture**, SVG included;
     - the documents the shot reads;
     - the vocabulary-entry versions (ADR 0003);
     - the capability derivation (ADR 0002);
     - the compiler's `impl_version`.

     The texture digests go into the *cache key only*. The compiled document's wire shape, and therefore `scene_contract_sha256`, stays as it is, so bench comparability is untouched. The contract hash and the cache key are distinct things and must never be conflated.
   - **The shot key** is:
     - the compiled digest;
     - the set of `audio_ref` / `viseme_ref` the shot muxes;
     - `runtime_sha256`;
     - a separate **environment digest** (Chromium build, Playwright version, ffmpeg identity, the font identities), taken from the probes the bench and `an.determinism` already run;
     - every `RenderContext` knob (fps, resolution, supersample, `pix_fmt`, step, capture path, frame samples, `strict_assets`).

     Keeping the environment digest separate means a machine change invalidates renders without pretending the content changed.
   - **`shot.id` is never a key** (pillar 11).

3. **A shot's inputs are recorded, not assumed.**
   - The mall handed to `compile_shot` is wrapped in a view that records which keys are read; those reads become the shot's dependency edges.
   - That only works once art bytes are read *through* the stores. Routing them there is the asset library's job (ADR 0005), and it comes first.
   - Until then, every shot depends on every asset in its project. That is safe, but it loses the per-character saving, and it is the behaviour of the first slice.
   - **As built (an#316, 2026-10-03):** read recording landed before the asset library's routing, because for the cut-out renderer the routing is not needed for correctness: art read by path behind the store reaches the pixels only through `assets.textures`, whose bytes are already the `textures` key part. The keyer compiles against a recording view of the mall (`an.build.reads`), and the shot depends on the asset entries it read (the `assets` part) plus the library lockfile. A renderer that cannot vouch that its reads go through the mall (Manim, an#291) keeps the whole-project fallback.

4. **Data model: `lacing`'s.**
   - Artifacts are recorded as `lacing.Artifact`s (content id plus provenance).
   - The per-stage stores are `ArtifactStore`s composed from `dol` mappings. This is consistent with pillar 7 and with the asset library.
   - `lacing`'s dependencies are light enough for the core. If that is refused, the same shape is implemented in `an` behind an adapter.

5. **Engine: a seam, defaulting to a built-in verifying-trace memo; `nw` as an optional backend.**
   - The core declares one keyword seam, `incremental=`.
   - Its default is an in-process implementation of verifying traces with early cutoff over the stores above. This is the algorithm `nw.freshness` uses, applied to `an`'s stage list.
   - An `nw`-backed implementation (an `nw.Transform` per stage, through `an.genre`) becomes possible once `nw`'s layout coupling and heavy dependencies are optional.
   - `an` never imports `nw` outside `an.genre`.

6. **Invalidation is by digest, never by deletion.**
   - `an iterate` stops deleting from the shots store.
   - A changed input produces a different key.
   - Today's `artifacts/shots/<shot.id>` entries are ignored by the new cache, and may be deleted.
   - Garbage collection of unreachable blobs is a separate, explicit command.

7. **Granularity is the shot for pictures, and the line for audio.**
   - Re-capturing only part of a shot (the frames whose time range changed) is possible, because the compiled pose is a pure function of time (an#185).
   - It is deferred until a measurement shows that shot granularity is too coarse.

## Alternatives considered

- **Adopt `nw` wholesale now.** It fulfils the vision's wording most directly. Rejected for now, for four reasons:
  - `nw`'s project layout is hard-wired;
  - its dependency closure pulls in paid-generation clients;
  - everything must be a `lacing` annotation on a time interval, which suits shots and lines but not assets;
  - its graph lives in a SQLite file beside the project, a second persistence path next to the mall.

  `nw` is kept as the planned backend behind the seam.
- **Fold SVG digests into the texture alias**, as raster art does. Simplest key. Rejected: it moves the contract hash of every corpus scene that has SVG art, and breaks bench comparability. Folding them into the cache key only (Decision 2) gets the same correctness.
- **Rebuild when files' mtimes change (Make-style).** Rejected:
  - `scene.md` and `scene.json` mtimes are deliberately equalised;
  - art is edited in place;
  - mtimes do not survive a copy, or a sync between machines.

  The raster digest's memo is keyed on (path, mtime, size). That is acceptable *as a memo of a digest*, never as the cache key itself.
- **An external build system** (DVC, Bazel, Snakemake). Rejected: a second graph language outside the IR.
- **OpenTimelineIO for the film stage** (shots, transitions, sound as an OTIO timeline). Attractive as an *export*, for interchange with editors. Rejected as the internal model: `an.assemble`'s frame-exact `film_timeline` is the specification, and OTIO would add a second one.
- **Do nothing.** Rejected by the vision.

## Consequences

- **Gains.**
  - Editing a line re-synthesises that line and re-renders only its shot.
  - Editing a character's art re-renders only the shots that read it, once reads are recorded.
  - Editing a style role, or a preset, re-renders only the shots whose compile key changed.
- **Costs.**
  - Hashing art on every compile.
  - A read-recording mall wrapper.
  - An environment digest.
  - A garbage-collection command.
  - "Compiling takes milliseconds" is an estimate. The first slice measures compile time against render time, per corpus scene.
- **Doc fix.** `architecture_as_built.md` §5.2 used to say the next render "regenerates only the invalidated shots". That sentence was false. It now says the deletion is inert, and it changes again when this ADR's first slice lands.

## First slice

A read-side shot cache keyed as in Decision 2, with every shot depending on its whole project (Decision 3's fallback). `render_project` skips any shot whose key is already present.

The tests:
- edit one shot of a two-shot scene, and exactly one shot renders;
- edit an SVG part in place, and the shot that uses it renders;
- change the environment digest, and every shot renders;
- record compile and render wall time per shot.

Read recording, `lacing` artifacts and the `nw` backend follow, in that order.

## Related

- Pillar 11 in `CLAUDE.md`.
- `misc/docs/framework_review_2026-10.md` §0, finding 2.
- ADR 0005 and `misc/docs/asset_library_design.md`: where the stores live, pinned asset versions (whose manifest hashes are ready-made dependency keys for the compile key), and the reference mode that routes art through the store.
