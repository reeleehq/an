# ADR 0003 — The structured ↔ semantic specification spectrum, and one semantic layer for all genres

**Status:** Proposed, 2026-10-01 · **Decider:** the maintainer · **Related:** `misc/docs/design_principles.md` (principle 1), `misc/docs/framework_review_2026-10.md` §5, `misc/docs/cutout_framework_review_2026-10.md` §4, `report 0 - Text-to-Structured-Animation.md` §5.2–5.3 (edit routing and the MCP design), pillars 1, 9 and 10, ADR 0001, ADR 0002, ADR 0004

## Context

Design principle 1 weighs two kinds of specification. Structured specification gives predictability, especially when agents drive the tools; LLMs make looser, semantically rich specification usable. For every aspect, the framework must say which of three levels it accepts, and how the loose ones resolve to the structured one:

- **(a)** a typed field that routes to a formula;
- **(b)** words resolved to a field or formula;
- **(c)** a goal the result is checked against afterwards.

The vision also requires the semantic layer and its MCP surface to be defined **once**, for every genre.

What exists today is spread over three places that share nothing:

- **(b) by name lookup.**
  - The names: `[happy]`, `play: walk`, `turn to: back`, named environments, camera moves and easings.
  - The vocabularies are module-level dicts: `motion.PRESETS`, `expression.presets.PRESETS`, `CAMERA_MOVES`, `EASING_FUNCS`.
  - The names stay in the IR and are resolved **below** it, by the compiler, which imports the presets and the expression provider.
  - A name's meaning can change under it. `walk` changed in an#214 and again in an#220, so an old scene that says `play: walk` renders differently today.
- **(b) by LLM.** `an iterate` sends the whole IR plus an instruction to Claude and gets JSON-pointer patches back. Its system prompt hand-lists the cut-out vocabulary, a fourth copy of knowledge that already lives in the schema, `sync` and validate.
- **(c).**
  - The style lint, against measured targets.
  - The emotion judge. It is built, but its cassette is unrecorded (an#171).
  - `an character validate`.
  - The vision-LM verifier.
- **No MCP surface at all,** although report 0 made one its first phase.

## Decision

1. **Three levels; (b) has two resolvers.**

   | Level | What it is |
   |---|---|
   | **(a) structured** | A typed IR field |
   | **(b-name)** | A name in a registered vocabulary, resolved deterministically |
   | **(b-LLM)** | A description, resolved by an LLM or an agent |
   | **(c) goal** | A statement, checked after rendering by a `Verifier` |

2. **Below the IR, everything is deterministic *and versioned*. Nothing below the IR ever calls an LLM.**
   - **(b-name) may stay in the IR as a name,** as `play: walk` and `[happy]` do today. Expanding presets at sync time would make `scene.md` unreadable and throw away the author's intent.
   - **Every vocabulary entry carries a version.** The versions of the entries a shot uses are folded into that shot's compile key (ADR 0004) and stamped into the compiled document. When the meaning of a name changes, the shot is re-rendered and the change is visible; it is never silent.
   - **An author can pin an entry's version, or freeze its expansion into plain tweens.** Use this when a scene must never move.
   - **(b-LLM) is resolved at authoring time, before validation.** Its output is written into the IR as typed values or as (b-name) references. The renderer never calls a model.

3. **LLM resolutions are recorded in a `resolutions` store.**
   - **Not in the decisions log,** which is append-only and keyed by position.
   - **Key.** A hash of the input words, the digest of the shot slice they apply to, and the digests of the descriptors they reference. Keying on the whole scene is rejected: any edit anywhere would re-ask the LLM for every resolution.
   - **Record.** Resolver id, model id, the input, the output values, and the IR paths written.
   - **Re-render and re-sync** reuse the record and never re-ask.
   - **Editing the words** produces a new key, so the next sync resolves again.
   - **Hand-editing a resolved value** supersedes the record. The edit wins, the record is marked superseded, and a decision entry says so. The IR stays the single source of truth.

4. **Goals are first-class and must be checkable.**
   - A (c) goal attaches to the scene, a shot or an entity, and names its verifier.
   - When the goal fails, the verifier's `Finding` routes the fix to the lowest layer that can make it (pillar 10). That may mean re-running the (b) resolver, with the finding as context, a bounded number of times.
   - A goal with no verifier is a comment, and the validator says so.

5. **Every field and method declares what it accepts.** For each entry, the vocabulary registry carries:
   - the levels it accepts;
   - its version;
   - its JSON schema;
   - a one-line description in domain terms;
   - examples;
   - its capability requirements (ADR 0002).

   A field that accepts only (a) — a rig, a pivot, a frame rate — says so, and no resolver will invent one.

6. **One vocabulary registry, in the core (`an.semantic`).** Genres contribute entries (ADR 0001). Three things are **generated** from it, never written by hand:
   - the `an iterate` system prompt;
   - the MCP surface;
   - the vocabulary section of the downstream skill.

   **The MCP surface is a curated list, not all of `_dispatch_funcs`.**
   - *Queries:* vocabulary, schema, `validate`, the capability queries `applicable` / `why_not` (ADR 0002), describe-an-asset.
   - *Edits:* apply a typed patch; resolve a description.
   - *Long-running work* (render, bench) is exposed only as a job you start and then poll, never as a blocking tool. Bench stays CLI-only.

7. **Where semantic text lives in the documents.**
   - The narrative layer (`scene.md`) may carry (b) text and (c) goals beside the structured blocks: a `direction:` on an action, a `goals:` list on a shot.
   - `sync` keeps them, and the resolver fills the structured blocks from them.
   - The scene graph (`scene.json`) holds the resolved values and a reference to each resolution record.

## Alternatives considered

- **Keep semantics in agent skills only.** This is today's practice for styles. Rejected: the vocabulary is copied into prose, resolutions are not recorded, and no MCP surface can be generated from it.
- **Resolve (b-LLM) in the compiler at render time.** Rejected: renders become non-deterministic and cost money on every run, and the golden corpus and contract hashes stop meaning anything.
- **Expand every (b-name) to (a) at sync time.** Perfect reproducibility. Rejected as the default (Decision 2): the narrative layer becomes a wall of tweens. Kept as the opt-in "freeze".
- **A separate semantic package shared with `previz`, `burns` and `walkthru`.** Possible later. Rejected for now, because the entries reference IR types that live in `an`.
- **A free-form LLM patcher with no registry** (today's `an iterate`). Kept, as a consumer of the registry.

## Consequences

- **Gains.**
  - One definition of the vocabulary serves the schema, the LLM, the MCP surface and the docs.
  - Renders are reproducible even when an LLM authored the scene.
  - A preset's meaning can change without silently changing old scenes.
  - Goals make "make it look like South Park" something that can fail.
- **Costs.**
  - Registry descriptions become load-bearing, because LLM output depends on them.
  - Two new persisted document kinds: resolution records and vocabulary versions.
  - Version-keyed recompiles: changing a preset re-renders every shot that uses it, which is the point.

## First slice

1. `an.semantic.Vocabulary`, with versioned entries for today's named vocabularies: motion presets, expression presets, camera moves, easings, action kinds and entity kinds.
2. Generate the `an iterate` prompt from it. A test checks the generated prompt against today's before the hand-written one is deleted.
3. Then the curated MCP surface.

The `resolutions` store comes with the first (b-LLM) resolver.

## Related

- `misc/docs/design_principles.md`, principle 1.
- The per-aspect tables: `framework_review_2026-10.md` §5 and `cutout_framework_review_2026-10.md` §4.
