# Plan: make `an` the structured-animation core, and split out `cutan`

*Written 2026-10-01 by the lead of the 2026-09-29 → 10-01 push, for the next lead session to execute. Status: active. Tracking epic: see "Tracking" below.*

This is an execution plan, not a design. The designs it executes are already in the repository; read them before starting a phase. When this plan and a design disagree, the design wins and this plan is corrected in the same PR.

## 0. Read first (in this order)

1. `misc/docs/design_principles.md` — the four principles every change is checked against: the structured ↔ semantic specification spectrum; capability-based applicability with a default for every aspect; reuse over re-definition (core vs genre); domain terminology.
2. `misc/docs/core_from_three_genres.md` — what the core is, inferred from cut-out (`an`), Manim (`manimkit`) and view-state animation (`previz`): the timing kernel as a cross-language contract, the open document model, three renderer tiers, "no engine is core", the module map (§5) and the order of work (§6).
3. `misc/docs/adr/` — ADRs 0001–0005 (accepted below) and their index.
4. `misc/docs/framework_review_2026-10.md` (includes the glossary) and `misc/docs/cutout_framework_review_2026-10.md`.
5. `misc/docs/asset_library_design.md` and `misc/docs/research/cutout_asset_management.md`.
6. `misc/docs/cutout_styles_research.md` and `.claude/skills/an-style/` — the "study the masters" work so far.

## 1. Decisions taken (2026-10-01)

The maintainer chose the package name and delegated the remaining decisions to the lead, who took them as follows. ADRs 0001–0005 move to **Accepted** with these choices.

| # | Decision | Choice |
|---|---|---|
| 1 | Name of the cut-out genre package | **`cutan`** (maintainer's choice). Future genres follow the stem + `an` scheme where it reads well (`vizan`, `mathan` were free on 2026-10-01). |
| 2 | ADR 0001 — core/genre split | **Accepted**, as revised with the three-genre evidence: groundwork inside `an` first (§6 of the core study), then `cutan`. The stage runtime is not core: it ships as `an.stage` behind an `an[stage]` extra and an import firewall. A small core corpus (paths, text, planes, camera, transitions) stays in `an`. Interim fallback if `cutan` is delayed: cut-out stays a subpackage of `an` behind the same firewall test. |
| 3 | Core study §7 decisions 1–5 and 7 | **Accepted** as recommended (timing kernel contract in JSON Schema + golden vectors, Python `an.timing` + TypeScript `previz`; declared field kinds; the easing canon; no engine is core; Manim opaque-source shots as the first non-cut-out renderer, before `cutan` exists; contract files live in `an`). Decision 6 (where a math-viz genre lives) **deferred**. |
| 4 | ADR 0002 — capabilities with defaults | **Accepted.** One capability registry over assets, engines and environment; every aspect has a universal default; requesting an inapplicable model proposes the applicable ones or the structure that would enable it. First clients: locomotion (an#224) and a default speaking motion for baked faces. |
| 5 | ADR 0003 — specification spectrum | **Accepted.** At and below the scene document everything is deterministic and versioned. Above it, ONE vocabulary registry (shaped like `previz`'s formulas) generates the `an iterate` prompt and the MCP surface for every genre. |
| 6 | ADR 0004 — incremental re-processing | **Accepted, first step only:** a content-keyed shot cache (keyed on a hash of the compiled shot plus the render knobs, never on `shot.id`), on `lacing`'s storage model. `nw` deferred until its folder layout and heavy dependencies are optional. |
| 7 | ADR 0005 — asset library | **Accepted**, with these settings: **one library root per package** — `an`'s core library at `~/.local/share/an` (genre-neutral assets: voices, sounds, fonts, text styles, generic plates and props) and `cutan`'s at `~/.local/share/cutan` — composed as an ordered **search path** (ADR 0005 decision 1): a genre reads its own library first, then the core library, then any other genre libraries the user lists. This keeps each package's storage its own while letting a character made in `cutan` be reused by another genre by reference, since the stores are abstract and federate as one read view. Writes go to the owning library. An asset reused across genres can be promoted to the core library. Asset ids are namespaced by library when federated (`cutan:character.alice-reiniger@v003`). Check-out into the project is the v1 default; readable ids; agent-made projects live under `<root>/projects/`, never in agent-work folders. |
| 8 | `config2py` | **Vendor** the data-folder resolution (root argument → `<PKG>_HOME` → platform data folder) as a small module in `an.library`; take the dependency only if more than that is needed. |
| 9 | Raw source clips downloaded for study | Delete them after an#226 has migrated the carved parts and the measurements into the library and verified re-renders. Carved parts stay, marked private study / NOT PUBLISHABLE. New public-domain study material comes from public-domain prints (e.g. the Internet Archive), not from YouTube rips (see the private legal report). |
| 10 | The 22 older bench ledger rows that record an absolute home path | Redact that one field in place to `~/…`, with a CHANGELOG note (git history keeps the old value). |

## 2. Phases

Each phase is one or more issues and PRs. Model guidance: **Opus** for building and for every independent adversarial review of a kernel, IR or storage change; **Sonnet** for docs, migrations, mechanical moves and checks; **Fable** only for a genuinely hard design decision, briefly (one consult per decision). Every phase ends merged (landing is pre-authorised; see the `landing-a-branch` skill).

| Phase | What | Depends on | Model | Issue |
|---|---|---|---|---|
| P0 | Record the decisions: ADR statuses (done in the PR that adds this plan), ADR 0005 addendum for per-package roots + search path; redact the 22 ledger rows (decision 10) | — | Sonnet | file |
| P1 | **Timing kernel contract** (core study §6 step 1): `an/timing`; the field-kind registry reproducing today's behaviour exactly; contract files `easing.json`, `kinds.json`, `timeline.schema.json`, `compiled.schema.json`, `timing_vectors.json` seeded from `previz`'s golden cases plus `an`'s parity cases. Gate: unchanged contract hashes AND parity tests AND pure-pose tests AND decoded-pixel goldens | — | Opus + Opus review | file |
| P2 | **Open the document model**: open action union and entity kinds with property spaces; genre registration through entry points (`an.genres`); the cut-out actions register as a genre, still inside `an` | P1 | Opus + Opus review | file |
| P3 | **Engine seam and firewall** (§6 step 2): `Engine` protocol, `frame_stage_renderer`, `an.stage` as the first engine behind `an[stage]`; the import-firewall test (no core module imports `an.stage`, a genre, Playwright, Manim or `manimkit` at module level) | P2 | Opus | file |
| P4 | **First non-cut-out renderer** (§6 step 3): Manim opaque-source shots through `manimkit`; the core corpus on `an.stage` (paths, text, planes, camera, transitions). Proves `an` renders without cut-out code | P3 | Opus | file |
| P5 | **Asset library** `an.library` per ADR 0005 with decision 7's per-package roots and search path; vendored root resolution (decision 8); `publish`, `find`, `checkout`, capability facets from ADR 0002's analysers | P0 (can run parallel to P1–P3) | Opus | file |
| P6 | **Shot cache** (ADR 0004 step 1), content-keyed, on `lacing`'s storage model; `iterate` stops re-rendering unchanged shots; tests that a one-line edit re-renders one shot | P2 | Opus | file |
| P7 | **Capability registry + vocabulary registry** (ADRs 0002, 0003): one registry for requirements/affordances/defaults with "propose applicable / propose enabling structure"; one vocabulary registry generating the `iterate` prompt and an MCP server (`py2mcp`) | P2 (P5 for asset facets) | Opus (+ one Fable consult on the registry shape) | file |
| P8 | **Create `cutan`** (an#225): repo `t/cutan` (public, MIT, wads, `priv pkg add-package`); move the cut-out modules per the core study's module map §5 with expand → migrate → contract (`an` re-exports with deprecation warnings for one release cycle); cut-out skills, demos, corpus scenes and the `an-style` work move with their code; `an`'s CLAUDE.md and architecture doc shrink to the core | P1–P4 (P5–P7 may land on either side; prefer before) | Opus lead for the move + Sonnet for mechanical moves | an#225 |
| P9 | **Migrate the carved assets** (an#226) into `cutan`'s library; verify re-renders from library references; then decision 9's deletions | P5, P8 | Sonnet | an#226 |
| P10 | **Locomotion models** (an#224) in `cutan` as the first client of the capability registry (legged walk → hop → glide default chain; hem gait; profile walks) | P7, P8 | Opus | an#224 |
| P11 | **Study the masters** (an#223): ≥ 26 sources with written analyses and video examples, a method × source matrix; methods feed the capability/method taxonomy and the style specs. Research only; can run any time | — | Opus (research) | an#223 |

Parallel lanes once P0 is in: **P1 → P2 → (P3 → P4) and (P6) and (P7)**; **P5** alongside; **P11** alongside. Then P8, then P9 and P10.

**Cross-repo follow-ups** (each in its own repository and session; file an issue there, don't edit from here): `previz` asserts the shared timing vectors; `shaping` validates its tracks against `timeline.schema.json`; `burns` takes its easing from the shared tables.

## 3. Standing rules for the executing lead

- **Principles in every brief.** Every worker brief names `misc/docs/design_principles.md` and asks the worker to say, in its PR, where its change sits on the structured ↔ semantic spectrum and what capabilities and defaults it declares.
- **One worktree per worker**, under `.claude/worktrees/<name>`, on disjoint files, with the split written into each brief; the main checkout stays on `main` and is **pulled before any end-user test** (a stale checkout cost a round on 2026-09-30). In a worktree, scripts need `PYTHONPATH=.` (the editable finder resolves `an` to the main checkout); pytest from the worktree root is fine.
- **Gates.** Kernel changes: the four checks of the core study §3. Pixel changes: the `run-browser-tests` label (via `gh api … labels`). Every claim of "corpus hashes unchanged" is checked by the bless-record guard added in an#222. Independent review before merge for anything touching the kernel, the IR, storage, the renderer or the audio cache.
- **End-user tests after each user-visible phase.** A fresh agent given only the skills renders the Alice & Bob script (Appendix A) in at least one style; its friction report becomes the next fixes. This loop found most of the real bugs of 2026-09-30.
- **Storage.** Never put an app's data or a session's assets in an agent-work folder or a repository: assets go to the library (P5); working notes go to `$PP/_agent_work/<corpus>/<date>-<topic>/`. Copyrighted carved material is private study only, never committed, never published.
- **Ledger and reporting.** Keep a crowsnest ledger (`~/.local/share/crowsnest/ledger/<your name>.md`) with the state, landed, in flight and spawns (with models) at the top; reply to the lookout in at most five lines.

## 4. Done when

- `an` has no module that imports cut-out code (firewall test green), renders a Manim shot and the core corpus without `cutan` installed, and evaluates timelines through the contract that `previz` also asserts.
- `cutan` is on PyPI, depends on `an`, and renders every former cut-out demo and the Alice & Bob scene in three styles from library assets.
- The library serves both packages through the search path; the carved assets live there, and the session folders are gone.
- A requested-but-inapplicable behaviour (a legged walk on a legless character) produces a proposal, not an error or a silent default; and every aspect has a default.
- The `iterate` prompt and the MCP tools are generated from one vocabulary registry.

## Tracking

The epic issue that links every phase issue is created alongside this plan; the executing lead files each phase's issue as it starts it and adds it to the epic as a sub-issue.

## Appendix A — the Alice & Bob end-user test script (the maintainer's, verbatim)

Two characters: Alice and Bob.

Alice is standing, looking towards audience.
Bob comes in from the left, walking all the way to her.
Bob stops and says "Hi!".
Alice looks slightly annoyed. Pauses. Then says "Bye" and walks away to the right of the screen, off the screen.
Bob stays there, and blinks.

Voices: ElevenLabs, good and expressive (Bob eager, Alice flat and slightly annoyed). Art: carved from the source being studied, plus props found with `illustration`, all with provenance in the library. The renders of 2026-09-30/10-01 in three styles (South Park, OverSimplified, Lotte Reiniger) are the baseline to beat.
