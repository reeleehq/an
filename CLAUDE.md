# Working in the an repo

**`an` is the core; the cut-out genre is the separate package [`cutan`](https://github.com/thorwhalen/cutan)** (`pip install "an[cutout]"`, since an#225): rigged characters, faces and expressions, lip-sync, impacts and the style lint, with their tests, corpus, examples, demos and skills. The core reaches a genre only through registered hooks (`architecture_as_built.md` §0a) and never imports it: `tests/test_import_firewall.py` has an empty allow-list. Work on a character, a face, a viseme or a style belongs in the `cutan` repository.

This file orients an AI agent doing engineering work *on* an itself. If you're using an from a downstream project, see `.claude/skills/an/SKILL.md` instead.

**The canonical current-state map is `misc/docs/architecture_as_built.md`** — the capability table (§0, the only one), module map, the three control flows, load-bearing invariants, caching strategy. Read it before any non-trivial change. This file is only the orientation layer above it; when the two disagree, the code is authoritative and both get fixed. Gaps, the full never-do list and the CI perimeter are in `misc/docs/sharp_edges.md`.

**Design principles — check every change against them:** `misc/docs/design_principles.md` (structured ↔ semantic spectrum; capability-based applicability with defaults; reuse over re-definition, core vs genre; domain terminology). Decisions behind them (accepted 2026-10-01): `misc/docs/adr/`; the plan executing them: `misc/docs/plan_core_and_cutan_2026-10.md`.

## Where things live

- **Source:** `an/` (the package). **Tests:** `tests/` — doctests cover the public API, pytest the cross-cutting and end-to-end checks; CI runs both (`--doctest-modules`, an#61). Never write a test count into a doc.
- **Reference research:** `misc/docs/` — the numbered reports and the character-art plan describe the *design space*, not current state; read the matching one before designing a subsystem.
- **Wave records (fact, not design space):** `misc/docs/wave{1_verification,2_research,3_research,4_research,5_research,6_research,7_research}.md`. Measured, so where one contradicts its epic's brief, the record wins; read the relevant one before building on that area (bench, golden corpus, render pipeline, faces, stage). What each contradicts: `misc/docs/sharp_edges.md`.
- **Project skills:** `.claude/skills/` — `an` (downstream), `an-spec`, `an-dev` (read alongside this file), and `an-dev-{bench,render-pipeline,stage,path,text,runtime-assets,licensing}` for their areas: read the matching one before touching a pixel, an encode flag, the camera or planes. The cut-out skills (`an-style`, `an-art-package`, `an-dev-{expression,lipsync,rig-contract,swap-channels}`) are one-paragraph stubs pointing to `cutan-*` in the `cutan` repository.
- **Related packages:** [`shaping`](https://github.com/thorwhalen/shaping) (shares `an`'s animation-track format; no dependency either way, so check a track-format change against it) and [`tituli`](https://github.com/thorwhalen/tituli) (text in video). The structured-animation family also includes [`previz`](https://github.com/thorwhalen/previz) (TypeScript: the kernel's twin, asserting `an/data/timing/` — thorwhalen/previz#3 — and a view engine whose entity is a vector of engine parameters; direction in an#257), [`burns`](https://github.com/thorwhalen/burns) (the crop engine for camera moves over a still or a video, burns#24) and [`jy`](https://github.com/i2mint/jy) (the Python-to-JS bridge; the JS-to-Python direction is still to be named). A camera move is a move of a view through a parameter space, defined once in the shared vocabulary and lowered per engine (an#257). See §13 of `misc/docs/architecture_as_built.md`.
- **AI changelog:** `misc/CHANGELOG.md` — one line under today's date per non-trivial chunk.
- **Demos and examples:** the cut-out gallery (`misc/demos/`) and `examples/` moved to `cutan`; the core corpus is `misc/bench/corpus/` (`an.bench.core_corpus`). **A new user-facing capability gets a demo** (in `cutan` for anything a character does).

## Architectural pillars (locked in)

1. **Three-layer IR.** `scene.md` (Narrative, human-edited) ↔ `ir/scene.json` (Scene Graph, agent-edited, the SSOT) → render code (per-backend, disposable). Information flows downward; verification feedback flows upward.
2. **Schema evolution from day one.** Versioning envelope, `extra="allow"` on inbound, additive-only changes, the chained registry in `an/ir/migrate.py` (`register_migration(kind, src, dst)`), keyed **per document kind** because this repo versions two of them independently — the scene IR (`version`) and the character descriptor (`schema_version`) — and both sit at `0.1.0`, so a `(src, dst)`-only key ran the wrong migration against the wrong document (an#77). A kind declares where its version lives via `DocumentKind`, and self-registers on import of the package owning its schema (the character descriptor's is `cutan`'s, registered when its genre loads). Round-trip stability is tested.
3. **Composition combinators flatten to a canonical timeline.** Authoring is fluent (`sequence`, `parallel`, `tween`); the canonical form is the flat list of `FlatAction`s with absolute times. Verifiers and renderers see only the flat form — never reason about composition nesting at render time.
4. **Path-based property targeting.** `"charlie/left_arm:rotation"` so animation generalizes across renderers. (The rigs are FLAT — arms are siblings of the torso, not children. The old `charlie/torso/left_arm` example named a node nothing builds, which stopped being harmless once an unknown target began to raise.)
5. **Time in seconds (float)** at the IR boundary; rational time only where audio drift matters.
6. **Everything external behind a `Protocol`.** `Renderer` (`an/adapters/_base.py`), `Engine` (`an/engines/protocol.py`: a seekable engine the core's `frame_stage_renderer` turns into a `Renderer`; capabilities read from its members), `TTSProvider` (`an/audio/tts.py`), `LipSyncProvider` and `WordTimingProvider` (`an/audio/lipsync.py`; the providers are `cutan`'s, registered as `lipsync.<name>` services), `Verifier` (`an/verify/_base.py`). Several implementations now exist per protocol; they are selected by name through the factories in `an/audio/providers.py` or via `register_renderer(...)` at import time.
7. **Persistence via dol-backed `MutableMapping`s** organized into the project mall (`an.build_project_mall`). No ad-hoc file I/O outside the stores.
8. **Dispatch to interface.** Plain Python functions are the business logic; the CLI is a thin **typer** dispatcher over `an.tools._dispatch_funcs`, wired PROGRAMMATICALLY (never as decorators on the functions, which would put `click` types in the business layer), plus `an.tools._dispatch_namespaces` for the core sub-namespaces (`voices`, `library`, `cache`); a genre adds its own (`an character ...`) through the `cli.<namespace>` service.
9. **Verification is a swappable `Verifier`.** Same interface for lint, media QA, vision-LM and human-in-the-loop.
10. **Typed error routing.** `Finding(severity, ir_path, description, suggested_fix)` so the orchestrator routes each fix to the lowest IR layer that can make it.
11. **Content-hash caching; invalidation by digest, never deletion.** Audio: `Dialogue.audio_ref` / `Dialogue.viseme_ref` are content-keyed and read back (`an/audio/pipeline.py`). Shots (an#242, ADR 0004 first slice): `render_project` reuses a shot whose key has an entry in `mall["shot_cache"]` (`lacing` artifacts, `an/build/`); the key digests the compiled document, its textures' bytes (SVG included, key only), its easing versions, its muxed audio, `runtime_sha256`, the render path's Python source (plus every module of a package that registered a genre hook: `genre_code_modules`), the renderer's registered class, every resolved render knob, a separate environment digest and every project asset — **never `shot.id`**. A new pixel-changing knob must reach `an/stage/cache_key.py::render_knobs`. `render()` is cold by default because the bench calls it. `mall["shots"]` (keyed by `shot.id`) is an archive nothing reads, and `iterate` no longer deletes from it.

## Code conventions

- `an.__all__` is **curated** — it exposes the IR, composition, project and diagnostics surface. The pipeline entry points are deliberately *not* re-exported at top level: use `an.render.render_project`, `an.orchestrate.orchestrate`, `an.iterate.iterate`, `an.stage.preview.preview_project`. Internals are underscore-prefixed.
- Keyword-only arguments past the 2nd or 3rd position; no magic numbers; defaults at module top.
- No globals, no service locators — pass the mall in.
- Functional over OOP; OOP only for orchestrators and stateful sessions.
- Errors are informative and wrap subprocess failures at the facade boundary as a typed error (`CutoutRenderError`, `ManimRenderError`, `MacSayTTSError`, …), never a bare `NotImplementedError`.
- Doctests for public API functions; pytest for cross-cutting and integration checks.
- Local packages have **no declared dependency versions** (e.g. `"dol"` not `"dol>=0.3"`).

## Invariants (the rest: `misc/docs/sharp_edges.md`)

- Never edit `ir/scene.json` by hand — edit `scene.md` and run `sync`, or assign through the store (`mall["scenes"]["main"] = scene_ir`). Never break the md/json mtime equalization in `ScenesStore.__setitem__`.
- Never bump `SCHEMA_VERSION` without registering a migration in `an/ir/migrate.py` AND a read path that runs it (`an.ir.sync.scene_from_json_doc`).
- Never let a verifier report success when it failed to run: a configured-and-broken verifier reports at `an.verify.vision.FAILURE_SEVERITY` or higher, never `info`.
- Never let a cassette miss fall through to a real API call; never claim a render produced something it didn't.
- Never `pip install <name>` a local-ecosystem package; use `pip install -e <path> --no-deps`.
- Never introduce a bare `NotImplementedError`; stubs raise typed, install-hinting errors.
- **No browser test runs on an unlabelled PR.** A PR that can change a pixel (runtime, stage compiler/serializer, render path, ffmpeg flags, rig) gets the `run-browser-tests` label: `gh api -X POST repos/thorwhalen/an/issues/<N>/labels -f 'labels[]=run-browser-tests'` (NOT `gh pr edit --add-label`, which exits 0 and applies nothing). **Never write that a rendering behaviour is "verified in CI"** — say where: a developer machine, a labelled PR, or an on-demand run.

## Per-PR housekeeping

- Append a one-line entry under today's date in `misc/CHANGELOG.md`.
- If the change moves the system's actual shape, update `misc/docs/architecture_as_built.md` in the same PR — it is the doc everything else routes to.
- Update the matching skill in `.claude/skills/` if the user-facing surface changed.
- Log non-trivial unblessed design decisions: in the PR description for repo-level work, in `.an/decisions.jsonl` (via `mall["decisions"]`) for project-level work.
