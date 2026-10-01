# Design principles

The four principles every change to `an` — and to any genre package built on it — is checked against. They come from the maintainer's vision for structured animation (October 2026). Each has a *how to apply* rule an agent can follow without asking. The reasoning, the as-built state and the proposals behind them are in `misc/docs/framework_review_2026-10.md` and the ADRs in `misc/docs/adr/`; the domain terms are defined in that review's glossary.

The aim behind all four: not to imitate one studio's look, but to find the underlying **methods** (rigging, replacement animation, timing, staging, surface treatment) that produce the looks, so they can be mixed and matched into new **sub-genres** of structured animation, specified from a script with minimal boilerplate, and adjusted after a draft without re-processing everything.

## 1. The structured ↔ semantic specification spectrum

Every aspect of a production (a pose, a walk, a camera move, a colour, a mouth shape, a timing) can be specified at one of three levels:

- **(a) Structured** — a typed field whose value routes to a formula (`tween rotation 0.3 over 0.5 s ease_in_out`, `gait: hem`, `step_hz: 12`). Deterministic and predictable; the only level a renderer ever sees.
- **(b) Semantic, resolved** — words that a resolver turns into (a): a **name** looked up in a versioned registry (`[happy]` → an expression preset, `play: walk` → a motion preset), or a **description** an LLM or agent resolves at authoring time (`"make her walk in nervously"` → a `walk` with a shorter stride and a hunched pose), with the resolution recorded.
- **(c) Semantic goal** — what the result should achieve (`"she should look surprised when the door opens"`, `"South Park cadence"`), checked *after* rendering by a verifier, which routes a fix back down to (a) or (b).

**How to apply.** For each field or behaviour you add, state which of (a)/(b)/(c) it accepts and how (b) and (c) resolve to (a). Below the scene IR everything is deterministic and versioned: a (b-name) name may stay in the IR (`play: walk`), but every vocabulary entry carries a version that the compile key includes, so changing what a name means re-renders visibly instead of silently; a (b-LLM) description never reaches the compiler — it is resolved at authoring time into typed values, and the resolution (resolver, model id, input words, output, IR paths) is recorded in a resolutions store, so a re-render never re-asks an LLM. A hand edit of a resolved value wins and supersedes the record. A (c) goal always has a verifier that can fail; a goal with no verifier is a comment, not a specification. The resolver and verifier seams live in the core, once, for every genre (ADR 0003).

## 2. Capability-based applicability, with defaults

A behaviour (a walk, a turn, a lip-sync, a blink, an expression, a hand gesture) **requires** certain structure of the asset it is applied to — a legged walk needs two leg slots with pivots at the hip; a mouth-chart lip-sync needs a mouth slot with a viseme swap set. An asset **affords** what its rig and art provide. Some behaviours require nothing (a glide, a hop, a squash-and-stretch, a slide-in apply to any drawable).

**How to apply.** (i) Every aspect has a default that applies to *anything*: if no walk method is named, the character still walks (the default is the requirement-free one — a hop/glide/rock); if no mouth chart exists, speech still reads (e.g. a jaw bob or a body pulse) rather than failing or being silently skipped. (ii) A behaviour declares its requirements as data, an asset's affordances are derived from its descriptor (never hand-maintained beside it), and one matcher answers "which methods apply to this asset?" and "what is missing for this method to apply?"; a style may set a policy ("this show hops even when its characters have legs") that reorders the choice. (iii) When a creator asks for a method their asset does not afford, the system says what structure would make it applicable (and, where it can, offers to add it), and meanwhile falls back to the default *with a recorded substitution*, never silently. Where an aspect makes no sense for an asset kind (an expression on a prop), the last link is an explicit, recorded no-op. Do not write another per-behaviour `if rig has X` branch: add a requirement to the registry (ADR 0002).

## 3. Reuse over re-definition

Shapes, transforms (translate, rotate, scale, skew, opacity, tint, trim), timing (easing, stepping, holds, cycles), composition (sequence, parallel, stagger), staging (camera, planes, parallax), the semantic layer and its MCP surface, storage, and incremental re-rendering are defined **once**, in the core, and shared by every genre — cut-out animation, data visualisation, mathematical-concept visualisation. Assets (characters, props, set elements, voices, style packs) are reused across videos and across styles.

**How to apply.** Before adding a field, type or function, ask: would a data-viz or math-viz genre need the same thing? If yes, it belongs in the core and must not mention a rig, a face or a mouth. Genre code extends the core through registration (new entity kinds, new actions, new properties, new resolvers, new requirements), never by editing a core `if kind == ...` chain. Assets are addressed by key through a store, tagged rather than nested under one video or one style, so the same character can appear in two styles (ADR 0001; storage and reuse: ADR 0005 and `misc/docs/asset_library_design.md`).

## 4. Domain terminology

Code, docs, skills and messages use the proper terms of animation production (cut-out animation, rigging, replacement animation, turnaround, exposure, layout, …) as used by Toon Boom Harmony, Moho and Spine and by the production literature, and the glossary maps the maintainer's plain words to them.

**How to apply.** Name a new concept with the established term (a `swap set` is replacement animation / drawing substitution; a `view` is a turnaround angle; a `play` is an action/animation clip; stepping is animating on twos). When `an` already uses a non-standard name, keep the code name stable (persisted identifiers are hard to rename) but give the standard term in the docstring and the glossary. When you write for the maintainer, use the domain term and, the first time, the plain word beside it.
