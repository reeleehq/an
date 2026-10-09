# ADR 0002 — Capability-based applicability, with a universal default for every aspect

**Status:** Accepted, 2026-10-01 (the maintainer delegated the decision; choices recorded in `misc/docs/plan_core_and_cutan_2026-10.md` §1) · **Decider:** the maintainer · **Related:** an#224 (locomotion methods, the first client), an#214 and an#220 (`walk`, `gait`, `rest_view`), an#197 (views), an#98 (expression binding), ADR 0001, ADR 0003, ADR 0004, `misc/docs/cutout_framework_review_2026-10.md` §5

## Context

Design principle 2 says:
- Some behaviours need structure: a legged walk needs legs. Others apply to anything, such as a glide or a hop.
- The framework must know what each behaviour **requires**, and what each asset **affords**.
- Every aspect has a default that applies to anything.
- When a creator wants something else, the system proposes what fits their asset, or helps them add the structure that makes the wanted one fit.
- This holds for every aspect, not only walking.

Today the knowledge exists but is scattered. Each consumer works out privately, from slot and set names, what a rig affords:

| Consumer | What it does today |
|---|---|
| `play_problems`, `preset_problems`, `preset_swap_problems` | check whether a play can run on the target |
| `expression_problems` | refuses a baked face |
| `default_binding` | derives the face binding from the slots |
| `resolve_mouth_set` | runs a mouth-variant fallback chain |
| `_limb_pair` + the `gait` chain | descriptor `gait`, else `legs` if a leg pair exists, else `rock` |
| blinks | lid swap if closed-eye art exists, else a squash |
| `asset_resolution` + `--strict-assets` | records stand-ins |

Only a handful of facts are declared: `face_overlay`, `rest_view`, `gait`, `gaze_travel`, `colour_roles` and `expression_binding`.

One aspect has no universal default at all. A character whose face is baked into its art (`face_overlay: false`) speaks with a frozen mouth.

## Decision

1. **Vocabulary.** These words take the production sense (glossary in `framework_review_2026-10.md` §1). "Model" is avoided: it already means an LLM model (ADR 0003) and a *model sheet*.
   - An **aspect** is something every asset of a kind gets: locomotion, speech, blink, expression, turn, gesture, entrance, recolour, …
   - A **method** is one way of realising an aspect: legged cycle, hem sway, hop, glide.
   - A **capability** is a named, possibly parametrised fact about an asset, such as `limbs.legs` (with hip pivots), `face.mouth` (chart `rhubarb9`), `swap.view` (keys `front,side`), `rig.hierarchy`, `face.eyelids`.
   - Capability names use one dotted grammar. They are registered and versioned like document kinds, because substitution records and the asset library's facets persist them.

2. **Affordances are derived from the asset, never hand-maintained beside it.**
   - `affordances(asset) → set[Capability]` is computed from the descriptor and the art present: slots, pivots, swap sets and keys, rig depth.
   - The derivation reads art (whether a closed-eye drawing exists, for example), so its result is a **compile input**. It is digested into the compile key of ADR 0004, never trusted from a cache keyed on names.
   - Declared facts (`gait`, `rest_view`, `face_overlay`) remain, as explicit **overrides** of the derivation, and the derivation reports which overrides it used.
   - A rig taxonomy (biped, robe figure, blob) is offered as named bundles of capabilities. This is the Rigify "metarig" idea: a template that declares its own structure. A method may require a bundle, but matching is always done on capabilities.

3. **Requirements are data on the method.** A method declares:
   - `requires`: capability predicates;
   - its parameters, with defaults;
   - an `expand` step, to typed actions (ADR 0003);
   - a **remedy** for each requirement: what would add the capability, and the command where one exists (`an character add-views`; "split the legs into two slots with hip pivots").

4. **One matcher, three queries, and a policy.**
   - `applicable(aspect, asset)` lists the methods that apply.
   - `why_not(method, asset)` lists the missing capabilities, each with its remedy.
   - `resolve(aspect, asset, requested=None, *, policy=None)` returns:
     - the requested method, if it applies;
     - otherwise, the first applicable method in the policy's order for that aspect;
     - otherwise, the aspect's **default chain**.

   Every substitution is recorded.

   A **policy** is how a style says "this show hops even when its characters have legs" (South Park). A first-applicable chain cannot say that. Policies live on the style document. Their precedence is: the author's explicit request, then the asset's own declaration, then the shot, then the style, then the aspect's default chain.

   **A declaration outranks a policy** (decided by the maintainer on 2026-10-09, cutan#36). When an asset declares the method for an aspect (a character's `gait` or `speech`, the field `Aspect.declared_by` names) and the shot's or the style's policy orders another, the declaration wins: it counts as the request when the author requested nothing. A statement about one character is more specific than a style's default, so a character keeps its personality across styles. A declaration the asset cannot honour falls back like any request, and is recorded as a substitution. The switch is `an.semantic.matcher.DECLARED_OUTRANKS_POLICY` (`True`); reading this decision the other way (the style winning) needs a new decision, not a flip of the flag.

5. **Every aspect's chain ends in a method that requires nothing.**
   - Every asset gets every aspect *that makes sense for its kind*.
   - Where an aspect does not apply to an asset kind at all (expression on a prop), the last link is an explicit, recorded **no-op**, never silence.
   - Speech gains a requirement-free last link: a body or jaw pulse on the syllables.

6. **Substitutions are recorded, never silent.**
   - The record generalises today's `asset_resolution`.
   - A substitution is a warning, and `--strict-assets` makes it fatal.
   - The same holds when a requested method is replaced by a default.

7. **Placement (ADR 0001).**
   - The registry, matcher, policy resolution, substitution record and query surface (Python, CLI, MCP) are **core**.
   - The capability vocabulary and the methods are contributed by each genre.
   - The same shape serves data viz: a "grow from baseline" entrance requires a bar with a baseline; a "draw on" requires a path.
   - It also serves non-character cut-out assets: parallax requires planes with depth; a prop's "switch on" requires an `on` state.

8. **No new private chain.**
   - A behaviour that needs structure declares it in the registry, instead of adding another `if rig has X` branch.
   - The existing mechanisms in *Context* move onto the registry one at a time.
   - The gate for each move is byte-identical output.

## Alternatives considered

- **Keep per-behaviour checks, and add a "capabilities" document.** Zero engineering. Rejected:
  - the knowledge stays duplicated;
  - nothing can answer "which walks apply to her?";
  - the frozen-mouth case shows that private chains miss aspects.
- **A capability manifest written by the author** (a `capabilities:` list in the descriptor). Rejected as the source of truth, because it drifts from the art. Kept only as overrides.
- **A rig taxonomy as the mechanism** (biped / quadruped / robe). Kept as a convenience on top of capabilities (Decision 2). Rejected as the mechanism, because hybrids must still match: a robe figure with arms is neither category.
- **Spine-style name matching.** An animation applies when the bones and slots it keys exist on the rig. This is the minimum `an` already does implicitly. It cannot express a *kind* of structure (a profile view, closed-eye art) or offer a remedy.
- **Fail when a method does not apply.** That is correct under `--strict-assets`. Rejected as the default: the vision asks for a draft that always renders.

## Consequences

- **Gains.**
  - The creator sees what is possible for each asset, and what to add to unlock more.
  - Agents have one query, instead of reading compiler internals.
  - an#224 and every later aspect plug into the same mechanism.
  - A test can assert that every chain ends in a requirement-free method or a recorded no-op.
- **Costs.**
  - Migrating the existing chains without moving a pixel needs care.
  - Capability names become persisted identifiers.
  - The affordance derivation becomes a compile input that ADR 0004 must key.
- **Interaction with the asset library (ADR 0005).** The library snapshots this ADR's `affordances(asset)` as a facet on each version, recomputes it when the analyser's version changes, and offers near misses with remedies (`find(…, affords=…, near=True)`). The analyser is this ADR's derivation, shared, never a second one.

## First slice

The registry and matcher in core, with two aspects:

- **Locomotion.** Migrate today's `walk`/`gait` chain unchanged, then let an#224 extend it with the policy hook.
- **Speech.** Add the requirement-free default for baked faces.

Plus `an character capabilities <name>`, which prints the affordances and, per aspect, the applicable methods and the `why_not` of the rest.

## Related

- `misc/docs/design_principles.md`, principle 2.
- `misc/docs/cutout_framework_review_2026-10.md` §5, which lists the default chain for each aspect.
