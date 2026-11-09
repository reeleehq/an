# Support, contacts and foot skate: the specification for catalogue rank 2 (A1 + B3)

Session `support-spec-519`, 2026-11-09, for [reeleehq/an#519](https://github.com/reeleehq/an/issues/519) rank 2; part of the epic [reeleehq/an#497](https://github.com/reeleehq/an/issues/497). Design space: `misc/docs/constraints_catalogue.md` §A1 (support and contact), §B3 (contact-conditioned motion), §D2 (contact shadows, which consumes this). Decisions this builds on: ADR 0008 (the constraint layer: joints, the `Constraint` interface, `an.kinematics`), ADR 0009 (the scene world), `misc/docs/design_principles.md` (reuse over re-definition; core vs genre; capability-based applicability). The issue row asked for a joint specification with puppet-research (an#512, now built: `an/ir/joints.py`, `an/stage/solve.py`, `an/kinematics/`) and with scene space (ADR 0009, `an/ir/world.py`); this document is that specification, written so the next session builds rank 2 without a design question. Every claim about what exists cites the file it was read in.

## 0. Summary

- **The declaration is a joint type, not a new list.** A support is `{type: support, a: <body>[@contact], b: <surface>}` in the places joints already live (`Shot.joints`, `AssetRef.joints`, a descriptor's `joints:`; `an/ir/schema.py` `JointSpec`), joined and unjoined in time by the existing `join`/`unjoin` verbs. It is the one-sided `contact` joint ADR 0008 decision 3 already names, plus the requirement that something touches. `held_by: ground | <body>@surface`, `place onto: …` and `solve: {ground: y}` (an#502, an#536) are kept as they are: they are the *derivation* face of the same relation for items, and the new check reads the surfaces they already parse.
- **Contacts come from the asset through one core seam.** `EntityKind.contacts(descriptor)` (API level 18), the twin of `EntityKind.landmarks` (`an/genres/registry.py:185-193`): named points of a rig that touch what it stands on. The core's fallback chain needs no genre: a prop's `metadata.contacts` (a `(u, v)` per name), else its rig's declared `origin` (where it stands, an#338/an#601), else the lowest point of its ink (`an.stage.hold.ink_points`). `cutan` fills the hook for characters with `foot_l`/`foot_r` as the far ends of `leg_l`/`leg_r`, exactly as `character_landmarks` derives `hand_l`/`hand_r` from the arms (`cutan/characters/hands.py`); a factory rig has no foot bone, and that is the v1 answer.
- **Surfaces are one `Line`.** The hold layer's `Line` (a point and a unit direction whose normal points into the support; `an/stage/hold.py:418-460`) already represents the floor (`_ground_line`), a member's `surface_l`/`surface_r` segment or ink top (`_surface_at`), and a stage segment; `_above` is the signed distance to it. These move to a small core module `an/stage/surface_line.py` and become the one residual both the lint and a later solver term read. The scene world gains an optional `World.ground` (a horizontal plane in world units) that lowers to a per-member floor line at the member's depth.
- **Two checks, lint-only in v1.** `support` (A1: penetration and floating; error when declared, warning when inferred from a standing rig) and `skate` (B3: drift of a held contact along its surface per frame, measured in the surface's own frame so a member carried by a moving frame does not skate; same severities; inferred only under a style pack that declares `gravity`). Both run on the compiled shot at the solve's frame grid, order 252/253, between the joint checks (250) and the hold checks (255). Tolerances are fractions of the entity's height with a named pixel floor. `floating_item` keeps its name and is re-expressed on the shared residual. No solver term in v1: supports are kept apart from the solve's joints (`Declarations.supports`, §6.2), so a shot declaring only supports compiles byte-identically; the term is specified for the PR that adds it.
- **Five PRs**: 1a the surface module (a pure move out of `hold.py`); 1b declaration + contacts seam + `support`; 2 core `skate`; 3 `cutan` contacts; 4 core `World.ground`. The solver term, impacts, B4's unsupported falls and D2 are follow-ups that consume `an.stage.support.supports_at`, specified in §6. The maintainer's open decisions are §8.

## 1. What ships today, read as the pieces of this feature

| Piece | Where | What it is | What it is not |
|---|---|---|---|
| `JointSpec` type `contact` | `an/ir/schema.py` `JointSpec` (`"contact"` in `type`; `SEGMENT_JOINT_TYPES`), lowered to `an.kinematics.Contact` in `an/stage/solve.py` (`row = Contact(pa, pb, pe, …)`), measured by `_segment_gap(one_sided=True)` (`an/stage/solve.py:2426`) | a point `a` kept on the free side of the segment `b`–`end`, or on it; `b`/`end` may be `world@x,y` stage points | nothing requires the point to touch (a floating foot has gap 0); `b` cannot name the floor line or a body's surface |
| `Shot.solve.ground` | `an/ir/schema.py` `SolveSettings.ground` (stage `y`, down positive) | the floor line `place onto: ground`, a `release` and `held_by: ground` use | not read by any check on a body; unset, the floor is where the carrier stands (`_ground_at`, `an/stage/hold.py:1308`) |
| `held_by`, `place onto` | `an/ir/holds.py` (`GROUND`, `SURFACE`), `an/stage/hold.py` (`ON_OVERRIDE`, `_is_surface_target`, `_surface_holder`, `_on_line`, `_on_ground`) | the derivation: an item's lowest ink point laid on the ground or on a body's supporting segment (`SURFACE_BONES = ("surface_l", "surface_r")`, else the top edge of the part's ink), the surface's tilt turning its rest angle | for items only (an item is not a body of the puppet: `an/stage/hold.py` module docstring); nothing for a character's feet |
| `floating_item` | `an/verify/holds.py` `check_floating_item`, from `_nearest_support` and the `floating` entries of `_report` (`an/stage/hold.py:2650-2760`) | an item a hand first takes from the floor or a named surface hovers above it (within `FLOAT_BAND_PX`) or sinks into it, at the take instant | nothing before or after that instant; nothing about bodies |
| Standing entities | `_standing_entities` (`an/stage/hold.py:1341`, an#601): a rig that declares `origin` (an#338, `an/stage/rig.py` `rig_origin`) and one of whose parts' painted bottom touches that point as the shot opens (within `SUPPORT_TOLERANCE_PX`) | the inferred floor of a carrier: its stage point | not a check; not exposed |
| `EntityKind.landmarks` | `an/genres/registry.py:185-193`; resolved in `landmarks_of`, an inner closure of `build_puppet` (`an/stage/solve.py:911`; `entity@name`, a bone of that name wins) | named points that are not bones: `cutan`'s `hand_l`/`hand_r` as the far end of the arm chain (`cutan/characters/hands.py` `character_landmarks`) | no notion of which points touch the ground |
| `EntityKind.shot_sizes` | `an/genres/registry.py:194-204`; called by `an.stage.world.member_shot_sizes` (`an/stage/world.py:108`) with a try/except that records why a hook's answer was dropped | the pattern for a genre giving the core a rig fact | — |
| The scene world | `an/ir/schema.py` `World`, `WorldMember.at` (where the entity's placement point stands: a character's feet), `Frame`; `an/ir/world.py` `Projection.project`, `_perspective_note` (catalogue A6: a member is taken to stand on the horizontal plane through its own world position) | members at world positions, projected to `stage.at` | no ground plane (catalogue §5.5); A6 assumes one through each member |
| The solve's frame grid | `an.stage.solve.frame_times(duration, fps=, step_hz=)` (`an/stage/solve.py:1458`) | the instants `joint_violation` measures at (`joint_residuals`) | — |
| Rest instants of a chain | `an.timing.timeline.key_times` and `cut_timeline` (`an/timing/timeline.py:253, 305`, an#719), as the `light` check uses them | where a pose can change course; between two keys where nothing moves, nothing moves | — |
| Contact instants | `cutan.impacts` (`cutan/impacts/truth.py`: `t_impact`, `kind: surface`, the bracketing frames) | exact ground truth for a stick or ball striking a surface, as `an` scenes | not a lint; a fixture generator (catalogue B3 Subsumes) |
| Walk contacts | `cutan/motion.py` (`PROFILE_SINK_SHARE`, `body_cycle`: Williams' four poses between two CONTACTS) | the gait knows its step boundaries | it emits nothing a check can read |

The upshot: the surface vocabulary, the signed-distance residual, the floor line, the one-sided joint and the per-frame grid all exist. What is missing is (a) a declaration that says *this body rests on that surface*, (b) a way for the core to know *which points of a body are its contacts*, (c) a check that reads (a) and (b) at every frame, and (d) a floor in the world.

## 2. The declaration

### 2.1 A `support` joint

`JointSpec.type` gains `"support"`. A support is a `contact` that must also touch: at every joined instant, no contact point of `a` is below the surface `b`, and at least one is on it.

```yaml
joints:
  - {type: support, a: paul, b: ground}                       # every contact of paul (its feet) on the floor line
  - {type: support, a: cup@base, b: table@surface}            # a prop's base on a member's supporting segment
  - {type: support, a: paul@foot_l, b: ground, name: left}    # one foot, so a gait can unjoin it
  - {type: contact, a: ball@base, b: world@-400,300, end: world@400,300}   # as today: on or above a stage segment
```

`a` is a body reference as `JointSpec` defines it (`an/ir/schema.py` `JointSpec` docstring: a node path or an entity with one root part, `@` a fraction, a bone, or a landmark). Two additions. `@<contact>` resolves through the new contacts seam (§3) when no bone or landmark has that name (§3.1), so nothing that resolves today changes. For **`support` only**, `a` with **no `@`** means **all of the body's contacts**; `contact` keeps its shipped meaning, where a bare `a` is the body's pivot (the `JointSpec` docstring: "With no `@` the point is the body's pivot for `a`"), so no existing `contact` changes what it measures. The per-type reading has a precedent in `hinge`, whose lone `a` means the part's own joint. An entity with several root parts (`ned`) resolves each contact to the part that carries it, as `_bone_carrier` does for a bone named on such an entity (`an/stage/solve.py:1304`).

`b` is a **surface reference** (new: `SURFACE_REFS`, for `support` only in v1: a `contact` stays in `Declarations.joints`, lowered by `build_puppet`'s `locate`, which resolves entities, bones, landmarks and `world@x,y` only, so it keeps `world@` + `end` until the solver term of PR 5): `ground` (the shot's floor line, §4.1), `<body>@surface` or `<body>@surface@f` (the hold layer's grammar, `an/stage/hold.py` `_is_surface_target`, `_surface_holder`), or `world@x,y` with `end: world@x2,y2` (today's segment). `_well_formed` changes from "`end` iff a segment type" to "`end` iff `b` is a `world@` point" for `contact` and `support`; `slide` is unchanged (it always needs `end`, `an/ir/schema.py` `JointSpec`). A `support` whose `a` or `b` names a body, a contact or a surface that is not in the shot is reported by the **`support` check itself**, not by `unknown_body`: `unknown_body` is gated on `shot_declares_solve` and reads the compile's `UnknownBodyError` (`an/verify/joints.py:56-78`), and a support never reaches the solve's resolver (§6.2), so it would see neither. `supports_at` resolves each support's references and returns the ones that do not resolve as problems (`(where, message)`, `unknown_body`'s wording and the contacts chain of §3.2), which the `support` check reports as errors at `{ctx.path}/{where}` before measuring anything.

`from`/`until` are not fields: a support's phases are `join`/`unjoin` on its `name` (`an/ir/joints.py`), the way every joint's are. A `support` with no verbs is joined for the whole shot.

`give` is accepted (a soft contact for the later term) and ignored by the lint. `limits`, `length`, `mode` are refused on a `support` as they are on a `contact` today.

### 2.2 Where it is declared

Everywhere a `JointSpec` is: `Shot.joints`, `AssetRef.joints` (`a` relative to the entity: `{type: support, b: ground}` on an entity, with `a` defaulting to the entity itself, i.e. all its contacts), and a descriptor's `joints:` (`an/stage/solve.py` `declarations`: descriptors' joints first, then entities', then the shot's). The `scene.md` form is the shot block's `joints:` list, already serialised and read by `an/ir/sync.py` (`shot_yaml["joints"]`). No new `scene.md` grammar.

The read path for an item (`held_by`, `place`, `release`) is unchanged and remains the derivation. A `support` on an item that the hold layer also moves is **not refused**: the check measures the item where the hold layer puts it, and finds it on its surface by construction, which is the catalogue's "the solver's output is re-linted".

### 2.3 Why a joint type, not `Shot.supports` or `overrides.supported_by`

`Shot.welds` (`an/ir/schema.py` `Weld`: "a declaration only: a lint reads it, nothing is composed from it") is the precedent for a lint-only list beside the joints, and `Shot.supports` would copy it. It is rejected here because ADR 0008 decision 3 already names `contact` as a joint type and decision 7 says every joint type is a constraint with a check and an optional term: a support has a term in the solver today (`an.kinematics.Contact`) and the derivation form in the hold layer (`_on_line`), so it belongs with the joints; putting it beside them would be the duplication the catalogue's Subsumes rule exists to stop. `overrides: {supported_by: …}` is rejected because it cannot be unjoined in time (a foot lifts) and because `held_by` already occupies that slot for items with a different meaning (the hold layer MOVES what `held_by` names; a check must not).

### 2.4 Inferred supports (no declaration)

An entity is **taken to stand** on a shot's floor when the rule of an#601 holds (`_standing_entities`, generalised): its kind gives contacts, or its rig declares `origin`, or its ink hull was read, and its lowest contact is within the support tolerance (§4.3) of the floor line as the shot opens. A contact whose source is `box` (§3.2 step 4: no hull was read, only the box's corners) never infers a stance: a box's bottom edge is a margin, not a foot. An item of the shot's holds (`hold_declarations(shot).items`, `an/stage/hold.py:276`) is never inferred: it is the hold layer's, and `floating_item` reports it. A member of a shot that has no floor (§4.1) is not inferred.

## 3. Where contacts come from: the `contacts` seam

### 3.1 The hook

```python
#: ``(descriptor) -> {name: (slot, point)}``: the named points of this kind's rigs
#: that touch what the rig stands on (catalogue A1, an#519): a character's
#: ``foot_l`` is the far end of its left leg. The same shape as ``landmarks``:
#: ``point`` is ``(u, v)``, a fraction of that slot's drawing, or ``None`` for the
#: slot's far end from its pivot. A bone or slot of that name wins. ``None``: the
#: kind names none, and the core derives one (``an.stage.support.contacts_of``).
#: Since ``an.genres.API_LEVEL`` 18.
contacts: Callable[[Any], Mapping[str, tuple[str, tuple[float, float] | None]]] | None = None
```

Added to `EntityKind` (`an/genres/registry.py`) after `shot_sizes`; `API_LEVEL` 18 with its line in `an/genres/__init__.py`'s ledger. Read by one core function, `an.stage.support.contacts_of(entity, mall, *, rig) -> dict[str, tuple[str, tuple[float, float] | None]]` (new module, §6.1), called by the check (through `supports_at`) and by the solve's point resolver, so that any joint or verb naming `paul@foot_l` resolves it like `paul@hand_l`. That resolver's `landmarks_of` is an inner closure of `build_puppet` (`an/stage/solve.py:911`), reading the kind's `landmarks` hook through `entity_kind`, so the contacts lookup is threaded into that closure: after the landmarks hook, the closure calls `contacts_of(entity, mall, rig=rigs[eid])` (cached in the same `landmark_cache`), and a landmark of the same name wins. Like `member_shot_sizes`, a hook that raises gives nothing and the reason is recorded on the report (`an/stage/world.py:137-146` is the pattern).

### 3.2 The core's fallback chain (no genre needed)

In order, the first that applies:

1. **The hook's answer**, when the kind registers one and it returns a non-empty mapping.
2. **`metadata.contacts`** on the descriptor: `{name: [u, v]}` fractions of the ROOT part's drawing (`{"base": [0.5, 1.0]}`: the bottom centre), the way `metadata.body_attachment` carries sockets (`cutan/body_attachment.py`) and `metadata.shaded_side` carries art facts (`an/verify/constraints.py` `_shaded_side`). Descriptors are `extra="allow"` (`an/stage/rig.py` `RigModel`; `cutan/characters/schema.py` `CharacterDescriptor.metadata`), so this is additive and persists today. A prop's `contacts.base` is the catalogue's socket-like `(u, v)`.
3. **The rig's `origin`** (`an.stage.rig.rig_origin`, declared): one contact named `origin` at the entity's local `(0, 0)`, the point an#338 defines as where the rig stands and `_standing_entities` already trusts. This is what a factory character gives before `cutan` ships its hook, and what any `stand_on_feet` character gives (`cutan/characters/factory.py` `stand_on_feet`).
4. **The lowest ink point** of the root parts (`an.stage.hold.ink_points`; `_ground_at`'s last resort): what `held_by: ground` rests an item by today, so an item and its `support` agree by construction. `ink_points` returns the alpha hull only for a raster it can read, and the bare corners of the part's box for SVG art and for any texture it cannot path (`an/stage/hold.py:527-560`: the `.svg` test, a failed `texture_source`, a missing file, an unreadable hull). The contact is named `ink` when a hull was read and **`box`** when only the corners were; the two are measured alike for a declared support, and §2.4 never infers a stance from `box`. `contacts_of` reports which, so the check's message can say "measured on `cup`'s box, not its ink: declare `metadata.contacts`".

A `support` whose `a` names a contact the chain does not give (`cup@base` on a prop with no `metadata.contacts`) is a `support` error (§2.1) naming the chain: "declare `metadata.contacts: {base: [u, v]}`, or name no point to use its ink".

### 3.3 Characters, in `cutan`

`cutan/characters/feet.py` (new, beside `hands.py`): `FEET: dict[str, str] = {"foot_l": "leg_l", "foot_r": "leg_r"}` (the rig contract's leg names, `WALK_LEG_NAMES[0]` in `cutan/motion.py`), and `character_contacts(desc)`, the mirror of `character_landmarks`: a `foot_l` bone is the core's (skipped); a `foot_l` slot is that slot's bottom centre (`FOOT_SOLE = (0.5, 1.0)`, the sole, not the centre a hand uses); else the deepest slot under the leg's bone, far end (`None`). A rig with no leg slots (a robe whose `hem` halves are its leg slots is still covered: the hem's far end is its bottom) returns `{}` and the core falls to the origin. Registered on `CHARACTER` in `cutan/genre.py` beside `landmarks=character_landmarks`, behind `require_api_level(18)`.

**What v1 uses for a factory rig without foot bones**: the far end of each leg slot from its pivot (the hip): the leg's drawn bottom. For a swinging leg that point sweeps an arc about the hip, so a hip-swing walk's feet leave the floor at the contact pose by `L·(1 − cos stride)` and are lowest at passing. That is the geometry of a cut-out hip swing, and the check will say so (§8 (f)); it is not a reason to measure something other than the foot.

## 4. Surfaces, and how a contact is measured against one

### 4.1 Three surfaces, one `Line`

`an/stage/surface_line.py` (new, core) takes from `an/stage/hold.py` without change of behaviour: `Line`, `ground_line(y)`, `line_through(a, b)` (the normal turned to point down into the support), `above(matrix, points, line)` (the signed distance of the lowest of `points` to the line along its normal: positive above, negative sunk) and `lift`; `hold.py` imports them (its names `_ground_line`, `_above`, `_lift`, `_line_through` kept as aliases until its tests move). `surface_at(ref, *, ctx) -> Line` resolves a surface reference at an instant:

| `b` | Stage space | Scene space (a shot with a viewpoint, ADR 0009) |
|---|---|---|
| `ground` | `Shot.solve.ground` when set (`SolveSettings.ground`), else **the member's own floor**: the per-entity `overrides.ground` the world lowering writes (below), else the stance point of the entity as the shot opens (`_ground_at`'s rule: `origin`-placed, its stage `y`; else the bottom of its root parts' ink), reported once as info ("no floor declared; measured against where `paul` stands as the shot opens") | `World.ground: g` (new, optional: the world `y` of the floor plane in the `world` frame, metres down positive as every world `y` is) projects, for a member at world `(x, ·, z)`, to the stage line through `Projection.project((x, g, z))` (`an/ir/world.py` `Projection`), which `lower_world` writes as `overrides.ground` (`an.base.GROUND_OVERRIDE`, a core override key) on each positioned member; a member whose `at_y`/`at_z` moves, or whose frame moves relative to the viewpoint's, gets it keyed per frame the way `_plane_keys` keys a plane (an#598), with the skate reference point of §4.2 beside it. Unset, scene space has no floor and the stage rule applies |
| `<body>@surface[@f]` | `_surface_at` (`an/stage/hold.py:1560`): the body's `surface_l`/`surface_r` bones (`SURFACE_BONES`), else the top edge of the part's ink, in the body's frame at that instant, so it tilts and moves with the body | the same: the body is lowered to the stage before compile (ADR 0009 decision 3) |
| `world@x,y` + `end` | `line_through(a, b)` on two stage points | the same (stage points) |

A `world@` segment is bounded: a contact past its ends is off it and nothing is measured (`_segment_gap`'s rule: "off the segment's ends: nothing to stand on, nothing broken"). A body's surface is bounded the same way (`_fraction_on` in `(0, 1)`, `_nearest_support`). The floor line is unbounded.

### 4.2 The residual

For a support `S` with contacts `C` and surface `L` at instant `t`: `d_c(t) = above(M_c(t), {p_c}, L(t))` for each contact `c` (`M_c` its part's world matrix from `evaluate_timeline` at `t`, composed by `an.stage.timeline._node_chain`/`transform_of` as `joint_residuals` does; `p_c` the contact's local point, the far end being the part's drawn extent from its pivot as `landmarks_of` resolves `None`). Then

- **penetration** `= max(0, −min_c d_c(t))`: how far the deepest contact is sunk;
- **floating** `= max(0, min_c d_c(t))`: how far above the surface the lowest contact is;
- **skate** (`c` held at `t_k` and `t_{k−1}`, §5.2) `= |s_c(t_k) − s_c(t_{k−1})|`, per frame, where `s_c(t) = τ(t) · (P_c(t) − R(t))` is the contact's **foot parameter along the surface**: the position of the foot of its normal on `L(t)`, measured from a reference point `R(t)` of the surface, along the line's unit direction `τ(t)`. `R` is a point fixed in the surface's own frame: for `<body>@surface` the segment's first end (the `surface_l` bone, else the left end of the ink top: `_surface_at`'s `a`, which moves and tilts with the body); for `World.ground` the stage projection, at `t`, of the member's opening ground point `(x₀, g, z₀)` held in the frame the member stands in (written by `lower_world` with the floor, §4.1, PR 4); for `solve.ground`, the member's own floor and a `world@` segment, a stage point (the line's point `(0, y)` for a floor, `b` for a segment), since the stage has no frames.

Skate is therefore the catalogue's Group E rule applied to B3 ("within a frame, every constraint in groups A to D is evaluated in that frame's coordinates": `misc/docs/constraints_catalogue.md` §2 Group E), not a stage displacement. A stage displacement would be wrong whenever the surface's frame moves relative to the viewpoint's: `lower_world` keys per-frame stage positions for a member whose frame is not static relative to the viewpoint's (`an/ir/world.py:2660-2665`, `tree.is_static`), which under a travel or a dolly is every member not riding with the camera, so a character standing in a passing car, any member under a dolly, or a figure on a pushed crate's `@surface` would all "skate" while standing still on what carries them.

The `contact` joint's residual is the penetration alone (`_segment_gap(one_sided=True)` is `max(0, −depth)`); a `support` adds floating.

### 4.3 Instants and tolerances

**Instants.** A declared support is measured at every instant of `frame_times(shot.duration, fps=doc.meta.fps, step_hz=...)` with the shot's resolved step rate (`Shot.step_hz`, else `Meta.step_hz`, as `solve_pass`'s `state.step_hz`) at which it is joined (the rule of `_joined_at`, `an/stage/solve.py:1509`, applied to its `support_verbs`, §6.2), the grid `joint_violation` uses, so the two cannot disagree about when. An inferred support is measured at the shot's opening instant and at the **rest instants** of the entity: every instant on the grid lying between two consecutive `key_times` of the entity's chains (`cut_timeline` to its nodes, as `_light_onsets` does) at which no selected channel is changing; a walking or jumping entity nothing declares is not judged mid-motion. Skate (§5.2) is measured on the full grid for declared supports and, for inferred ones, on the frames where the contact is held on both sides.

**Tolerances**, named at module top, as fractions of the supported entity's **height** (its root parts' union box at the shot's open, `node_box`; catalogue §5.3: relative to the member's extent, so a wide and a close-up agree), each with a **pixel floor**, because a fraction of a small prop's height is sub-pixel (0.02 of a 30 px cup is 0.6 px, below what a frame can show and below the solver's own rejoin blend):

- `SUPPORT_TOLERANCE: float = 0.02` of the height, either way (4 px on a 200 px figure), floored at `SUPPORT_FLOOR_PX: float = 2.0`. The tolerance a check applies is `support_tolerance(height) = max(SUPPORT_TOLERANCE * height, SUPPORT_FLOOR_PX)`. The floor is the width of an#636's rejoin blend (`an.kinematics.solver.DFLT_REJOIN_BLEND_PX = 2.0`, mirrored by `an.verify.joints.REJOIN_TOLERANCE_PX`): the gap below which the solver itself treats two points as joined, so a support is not held tighter than a joint.
- `FLOAT_BAND: float = 0.4` of the height: an inferred stance is not inferred beyond it (the hold layer's `FLOAT_BAND_PX = 80` is the item form); a declared support is held to the support tolerance whatever the gap.
- `SKATE_TOLERANCE: float = 0.005` of the height **per frame** (1 px per frame on a 200 px figure; PhysDiff's definition is per adjacent frame pair [catalogue ref. 10]).

`an.stage.hold.SUPPORT_TOLERANCE_PX = 1.0` stays: it is for placements the hold layer *derives*, which are exact by construction. It and the check's `SUPPORT_TOLERANCE` (a fraction) and `SUPPORT_FLOOR_PX` (the check's floor, in `an/verify/support.py`) are three names for three things, so no reader confuses them. The numbers above are initial values to be calibrated on the corpus in PR 1b and PR 2 (acceptance: the core corpus stays clean, §7).

## 5. The checks

### 5.1 `support` (catalogue A1)

Module `an/verify/support.py`, `SUPPORT = Constraint("support", check_support, order=SUPPORT_CHECK_ORDER, term=None, description=…)`, `SUPPORT_CHECK_ORDER: float = 252.0` (after `unknown_body`/`unreachable_pin`/`joint_violation` at 250, which report broken declarations first; before the hold checks at 255). Registered as the other constraint modules are (`_register()` on import; `an/ir/__init__.py` imports it after `an.verify.holds`).

Gate: silent when the shot declares no `support` and no entity is taken to stand (§2.4) on a shot with a floor; silent when the shot did not compile (`compile_outcome`, `not_compiled` reports that).

Per declared support, per joined frame, from `an.stage.support.supports_at` (§6.1):

- penetration above `support_tolerance(height)` (§4.3) → **error** at `{ctx.path}/{where}` (the support's `where`, as `declarations` records it): "`paul`'s `foot_r` is 9 px into `ground` (y 240) from 1.20 s to 1.45 s. Raise `paul` (its `stage.at` y or the tween on `paul:y`), or lower the floor (`solve: {ground: …}`)".
- floating above `support_tolerance(height)` → **error**: "`cup` floats 14 px above `table@surface` from 0.00 s to 2.00 s: nothing it stands on reaches it. Put it down (`overrides: {held_by: table@surface}` lays it there), or `unjoin` the support while it is carried".
- Spans are reported with `_spans(times, broken)` as `joint_violation` does, worst value per span.

Per inferred stance (warning, same messages prefixed "`paul` stands on … as the shot opens, but"), at rest instants only.

What it does not report: an item of the shot's holds (`floating_item`'s), an entity `overrides: {airborne: {from, until}}` within its flight (`AIRBORNE_OVERRIDE`, `an/verify/constraints.py:1682`), an unjoined span.

### 5.2 `skate` (catalogue B3 i)

Same module, `SKATE = Constraint("skate", check_skate, order=SKATE_CHECK_ORDER)`, `SKATE_CHECK_ORDER: float = 253.0`.

A contact is **held** at frame `k` when its support is joined at `t_k` and `|d_c(t_k)| ≤ support_tolerance(height)` (it is on the surface). For every pair of adjacent frames at which `c` is held, the change of its foot parameter along the surface (§4.2: measured from the surface's reference point, so a member carried by a moving car, a dolly or a pushed crate does not skate) above `SKATE_TOLERANCE × height` is a skate frame; spans of skate frames are reported once each: "`paul`'s `foot_l` slides 3.2 px per frame along `ground` from 0.50 s to 0.75 s while it stands on it (foot skate). Plant it (`unjoin` the foot's support while it swings, or keep `paul:x` still while it is down)".

Severity: **error** for a declared support, **warning** for an inferred stance, and the inferred form runs only under a style pack that declares `gravity` (the `gravity` check's gate, `_gravity_of`, `an/verify/constraints.py:1744`): a cartoon style with no gravity glides by right (catalogue B4's "a style decision and must be declarable"; the puppetry research's "gravity is a style, not a law", `misc/docs/research/puppeteering_2026-10.md` §2).

Exempt: a contact from the fallback chain's `origin`, `ink` or `box` (§3.2 steps 3 and 4) and a prop's `base`: a body that glides on its stance point (the `glide` locomotion method, `cutan/characters/methods.py`, the chain's requirement-free end) has no foot to skate, and a pushed crate slides; skate is about a contact that belongs to a part that moves relative to the body (a leg, a hoof: the hook's contacts). An `airborne` span is exempt.

Impacts (B3 ii) are **not** in rank 2: `supports_at` records the normal velocity of each contact at a `join` instant so a later `impact` check (velocity reverses or reaches zero within one frame; `cutan.impacts` ground truth as its fixtures) reads this module and adds nothing to it.

### 5.3 What they subsume, and the order within the stage

- `floating_item` (`an/verify/holds.py`) **keeps its name** and is re-expressed on the shared residual: `_nearest_support` computes `above` with `an.stage.surface.above` (it already calls `_above`; the move makes it the same function the `support` check calls). Its scope stays the item at its take instant, where the hand's `g.kc` is the right instant and `held_by` the right fix; `support` never measures a hold item, so no finding is doubled. This is ADR 0008 decision 7's treatment of `cut_continuity`: re-expressed, not renamed.
- `gravity`'s missing half (B4 "unsupported falls": a member neither supported, attached nor airborne that hovers) becomes buildable: `supports_at` is its "is supported at `t`". Not in rank 2.
- `_standing_entities` (`an/stage/hold.py`) is re-expressed on `contacts_of` so the hold layer and the check agree about who stands where.

Order within the `shot` stage after this: core checks (targets 90 … dialogue 130), the catalogue's constraints at `DFLT_ORDER` 200, joints 250, **support 252, skate 253**, holds 255.

## 6. The pure functions, the term and what D2 consumes

### 6.1 `an/stage/support.py`

```python
@dataclass(frozen=True)
class ContactState:
    name: str                      # "foot_l", "base", "origin", "ink", "box"
    part: str                      # the node path that carries it
    at: tuple[float, float]        # its stage point at t
    above: float                   # signed distance to the surface along its normal (+ above, − sunk)
    held: bool                     # joined and |above| <= tolerance
    tangent_speed: float | None    # |change of s_c| (§4.2), px per frame in the surface's frame; None at the first frame or when not held on both sides

@dataclass(frozen=True)
class SupportState:
    entity: str
    joint: str | None              # the support's id; None when inferred
    t: float
    surface: Line                  # the resolved line at t
    surface_ref: str               # "ground", "table@surface", "world@…"
    contacts: tuple[ContactState, ...]
    joined: bool

def contacts_of(entity, mall, *, rig=None) -> dict[str, tuple[str, tuple[float, float] | None]]: ...
def supports_at(doc, shot, mall, *, times=None, inferred=True) -> tuple[list[SupportState], list[tuple[str, str]]]: ...
    # the states, and (where, message) for each reference that does not resolve (§2.1)
```

`supports_at` is the pure function under both checks (the catalogue's "one residual function for the lint and the solver"), with doctests on the hold fixture. It evaluates the compiled timeline once per instant and shares the pose across supports, as `_light_onsets` does.

### 6.2 The solver term: none in v1, specified for PR 5

v1 is **lint-only**, and that needs supports kept apart from the solve's joints, not merely skipped by the lowering loop. Today `shot_declares_solve` is `not declarations(...).empty` and `Declarations.empty` is false for any joint at all (`an/stage/solve.py:243-273`), and `build_puppet` raises on a `join`/`unjoin` naming an id that is no joint row (`an/stage/solve.py:1216-1224`). So a support stored in `Declarations.joints` would make a support-only shot run the solve pass (not byte-identical), and `unjoin left` on a support would be a compile error. The specification:

- `declarations()` (`an/stage/solve.py:366`) puts a `JointSpec` of type `support`, from any of its three sources, in a new field **`Declarations.supports: list[DeclaredJoint]`**, never in `joints`; and a `join`/`unjoin` whose `joint` is a support's id in **`Declarations.support_verbs: list[Verb]`**, never in `verbs` (with `verbs=True`, `solve_pass` reads every verb, `an/stage/solve.py:1935`). `Declarations.empty` ignores both fields.
- `build_puppet` seeds the support ids into `ids` before the check at `:1216-1224`, so a verb naming a support, should one reach it, is not "no joint of this shot"; it builds no row for it.
- `_has_verb(shot)` (`an/stage/solve.py:319`) ignores a `join`/`unjoin` whose `joint` names only a support declared in the shot's or its entities' `joints` (a descriptor's supports are routed by `declarations` as above), so `shot_declares_solve`'s `verbs=` gate stays off for a shot whose only declarations are supports and their verbs; `solve_pass` then exits at `decl.empty` (`:1935-1936`) once `declarations` routes supports and their verbs away (its earlier return at `:1909-1919` tests `shot.joints` directly and is not the gate here).
- `_joined_at` is not reused for supports (it reads a `Puppet`'s events); `supports_at` builds the same `{id: [(t, joined)]}` from `support_verbs` and applies the same rule.

A shot whose only joints are supports therefore compiles byte-identically with and without them (the byte-identity test of an#512 extends to a scene declaring only supports and a `join`/`unjoin` of one). No pixel changes, no browser lane.

The term, when it comes (PR 5, labelled `run-browser-tests`): a `support` lowers to an `an.kinematics.Contact` row (penetration enforced for a body the solve moves; `give` its compliance), and the floating half is a **derivation** in pose mode, where nothing pulls down: a body nothing else drives at that frame is lifted by `−min_c d_c` along the normal (`surface.lift`), the way `_on_line` places an item, before the joints are projected; in dynamic mode gravity settles it onto the contact. `term=joint_term` then (`an/verify/joints.py` `joint_term` → `joint_residuals`, which already measures `Contact` rows). The puppetry research's row for this is "Catto's Soft Step for contacts when P5's contact lint grows a solver term" (`misc/docs/research/puppeteering_2026-10.md` §6 row 1). `SOLVER_VERSION` bumps; `solve_knobs` already digests the declarations.

### 6.3 What D2 (contact shadows, rank 16) consumes

D2 is a compile pass that adds a synthetic ellipse node per supported member (an#519 comment, 2026-10-26): its x tracks copy the caster's, its y is pinned to the floor. From this spec it reads, per frame, the states `supports_at(doc, shot, mall)` returns: for each `SupportState`, the **anchor** is the foot of the normal from the lowest contact onto `surface` (for several held contacts, the midpoint of their feet on the line, the ellipse spanning them); the **tilt** is the line's direction (a shadow on a tilted crate lies along it); the **height** is `min_c above` (the shadow shrinks and fades as a jumping member rises; it stays on the floor, which is why the floor must be a surface and not the member's own `y`); the **light** offset along the ground is `meta.light`'s (D1, `an/ir/schema.py` `SceneLight.vector`). D2 adds nothing to the declaration: a member with a declared or inferred support gets a shadow where the style asks for one (`shadow: contact`), and `World.ground` (PR 4) is what gives a member walking toward the camera a floor that follows its depth.

## 7. The build plan

Each PR carries its changelog fragment (`misc/changelog.d/<date>-an519-<slug>.md`), the architecture row in `misc/docs/architecture_as_built.md` §0 (the "Constraint layer" row gains `support`/`skate`; the "Holding things" row notes the surface module), and a `Status` update in the catalogue. PRs 1a, 1b, 2 and 4 are core-only (`an`); PR 3 is `cutan`'s. 1a before 1b; 1b before 2 and 3 (the hook must exist); 4 independent of 2 and 3.

**PR 1a (`an`): the surface module, a pure move.**

`an/stage/surface_line.py` takes `Line`, `ground_line`, `line_through`, `above` and `lift` from `an/stage/hold.py` (`Line` at `:418-420`, `_ground_line` `:423`, `_line_through` `:427`, `_above` `:441`, `_lift` `:1505`) without a change of behaviour; `hold.py` imports them under its old underscore names, its doctests move with the functions, and `tests/test_holds.py` is unchanged and passes as it is (the acceptance). No pixel changes. One cost to name in the PR body: the shot cache's `code` part digests the source of every module the render path reaches (`an.stage.cache_key.render_code_digest`, `an.stage.hold` among them, and the new module joins the walk), so this PR, like any edit there, makes every cached shot re-render once; nothing else in a key moves.

**PR 1b (`an`): the `support` joint, the contacts seam, the `support` check.**

`JointSpec` type `support`, `SURFACE_REFS` for `support`, the `_well_formed` rule, bare `a` on a `support` meaning all contacts (§2.1); `Declarations.supports` and `support_verbs`, the ids seeded in `build_puppet`, `_has_verb` ignoring support-only verbs (§6.2); `EntityKind.contacts`, `API_LEVEL` 18; `an/stage/support.py` (`contacts_of`, with the `ink`/`box` distinction, and `supports_at`, which reports its own unresolved references); `an/verify/support.py` (`SUPPORT`, `SUPPORT_FLOOR_PX`); the contacts lookup threaded into `build_puppet`'s `landmarks_of` closure (`an/stage/solve.py:911`); `_standing_entities` and `_nearest_support` on the shared functions; the `an-spec` skill's line on what holds what (`.claude/skills/an-spec/SKILL.md`, the `joints:` item) gains "what stands on what".

Fixtures: `tests/_hold_fixture.py` extended with `metadata.contacts: {base: [0.5, 1.0]}` on `stick` and a `table` prop with `surface_l`/`surface_r` (the `crate` serves); `tests/test_support.py`: the figure (its `origin` at the root bone: its contact is `origin`) on `solve: {ground: GROUND}` with `{type: support, a: figure, b: ground}` reports nothing; the same with `unjoin` and `join` of it mid-shot compiles (no "no joint of this shot") and is not judged while unjoined; a support naming `nobody` as `b` is a `support` error naming it; `stage.at` 10 px higher → one `floating` error naming the distance; 10 px lower → one `penetration` error; the figure tweened up 60 px over the shot → an error span starting where the gap passes tolerance; the stick on `crate@surface` by `support` reports nothing when `held_by: crate@surface` lays it there, and floats when staged above; an inferred stance (no joint) reports a warning only at rest instants (a `y` tween mid-shot is not judged while moving); a shot with no floor and no world reports the info line once; a hold item is never doubled with `floating_item`; an SVG prop with no `metadata.contacts` is measured on its `box` when declared and never inferred to stand; a 30 px prop 1.5 px off its surface is clean (the 2 px floor) and 3 px off is an error.

Acceptance: `an validate` on the fixture says *`figure` floats 10 px above `ground`* with the fix, and the core corpus (`an.bench.core_corpus.CORE_FIXTURES`) stays clean; a scene declaring only supports, and a `join`/`unjoin` of one, compiles byte-identically to one declaring none (`shot_declares_solve` is false for it).

**PR 2 (`an`): the `skate` check.**

`an/verify/support.py` gains `SKATE`; `supports_at` gains `held` and `tangent_speed` (the change of the foot parameter `s_c` from the surface's reference point, §4.2); the pack gate for the inferred form.

Fixtures: the figure's `leg_l` far end declared as `metadata.contacts: {foot_l: …}` on the fixture's leg slot (a two-contact figure) with `{type: support, a: figure@foot_l, b: ground, name: left}`; `figure:x` tweened 40 px over 1 s while standing → one `skate` error span; the same with `unjoin left` over the move → clean; the same with no joint under a pack with `gravity: down 980` → a warning, under a pack without → silent; a prop pushed along the floor by `tween x` with `support a: stick@base` → silent (base is exempt); the figure standing still with `support a: figure@foot_l, b: crate@surface` while the crate is tweened 40 px → silent (its foot parameter from the crate's `surface_l` does not change).

Acceptance: the factory corpus's walks are run through `an validate` and their skate findings written into the PR body as measured numbers (§8 (f)), with the inferred form silent on the corpus as shipped (no corpus pack declares gravity) and the core corpus clean.

**PR 3 (`cutan`): characters' feet.**

`cutan/characters/feet.py` (`FEET`, `FOOT_SOLE`, `character_contacts`), registered on `CHARACTER` behind `require_api_level(18)`; the `cutan-dev-rig-contract` skill gains the foot row (a `foot_l`/`foot_r` slot or bone is read first); `an character capabilities` lists the contacts.

Fixtures: the factory rig (`cutan/characters/schema.py` default slots: `leg_l`, `leg_r` on their bones) gives `{foot_l: ("leg_l", None), foot_r: ("leg_r", None)}`; a rig with `foot_l` slots gives their soles; a hem robe gives its hem halves; a legless rig gives `{}` and the core's `origin` stands in (asserted through `an.stage.support.contacts_of`).

Acceptance: a factory character standing on `solve: {ground: y}` with `{type: support, a: stu, b: ground}` validates clean at rest; `stage.at` raised 10 px gives the floating error naming `foot_l`/`foot_r`; a side-view `walk` on the same shot gives the measured floating/skate spans of the hip swing in the PR body, and a filed cutan issue for the gait presets to emit `join`/`unjoin` per foot and to derive the body's `y` from the planted leg (the term's first consumer).

**PR 4 (`an`, label `run-browser-tests`): the world's ground.**

`World.ground: float | None` (omitted when unset, like every world field); `lower_world` writes `overrides.ground` per positioned member from `Projection.project((x, g, z))`, keyed per frame for a member whose `at_y`/`at_z` moves or whose frame is not static relative to the viewpoint's (the `_plane_keys` pattern), together with the skate reference point of §4.2 (the stage projection of the member's opening ground point held in its own frame, keyed the same way); no `world` note for a member off the floor: the `support` check's inferred stance (§2.4, §5.1) already reports it, and two findings on one member for one fact is the doubling §5.3 exists to prevent; the hold layer's `_ground_at` reads `overrides.ground` before the stance rule (this is the pixel change: a `place onto: ground` under a world lands on the world's floor); `an world show` prints the floor.

Fixtures: `tests/test_world.py` gains a two-member world on `ground: 1.75` seen from a viewpoint: both members' `overrides.ground` equal their `stage.at` y (a member stands where its feet project); a member a few centimetres above the floor (within `FLOAT_BAND`) gets the `support` check's inferred warning and no `world` note; a member riding a travelling frame (a car) gets a keyed floor and reference point, and standing still in it reports no skate; a member tweened in `at_z` toward the camera gets a keyed floor whose stage `y` grows.

Acceptance: the shot cache key moves only for shots whose world declares `ground` (the compiled document carries the override); a world without `ground` lowers byte-identically.

**Follow-ups, filed under an#497, not rank 2**: PR 5 the term (§6.2); `impact` (B3 ii) on `supports_at`; B4's unsupported falls; D2 (rank 16) consuming §6.3; `support_top` as an alias of `surface_l`/`surface_r` for art that declares a `v` only (the architecture row's "Not built: a `metadata.support_top`").

## 8. Open decisions for the maintainer

Each is a question, the recommendation, and why in one line.

- **(a) Is an unjoined support airborne?** Recommendation: no. Why: `unjoin` only suspends the lint for that span; a jump that must read as a flight declares `overrides: {airborne: {from, until}}` (B4, `AIRBORNE_OVERRIDE`, `an/verify/constraints.py:1682`), which the `gravity` check then holds to a parabola.
- **(b) A bare `a` on a `support`: all of the body's contacts, or require `@<contact>`?** Recommendation: all contacts. Why: "paul stands on the ground" is the common sentence and names both feet; `contact` keeps its shipped bare-`a`-is-the-pivot meaning, so nothing existing changes (§2.1).
- **(c) The tolerance's unit for props.** Recommendation: a fraction of the entity's height with a named pixel floor, `max(SUPPORT_TOLERANCE × height, SUPPORT_FLOOR_PX)`, the floor 2 px. Why: a fraction keeps a wide and a close-up in agreement (catalogue §5.3), and the floor, equal to an#636's rejoin blend, stops a small prop being held to a sub-pixel gap the solver itself would call joined (§4.3).
- **(d) The skate reference.** Recommendation: the surface's frame: the change of the contact's foot parameter along the surface from a point fixed in it (`surface_l` for a body, the projected opening ground point for `World.ground`, the stage origin for `solve.ground`). Why: a stage displacement makes a passenger, a member under a dolly and a figure on a pushed crate all skate while standing still (catalogue Group E, §4.2).
- **(e) Agree the remaining choices as recommended:** lint-only v1 (§6.2); the joint type as the declaration's home, not a `Shot.supports` list (§2.3); a separate `EntityKind.contacts` hook, not a flag on `landmarks` (§3.1); keep `floating_item`'s name, re-expressed on the shared residual (§5.3); `World.ground` now, in PR 4. Why: each keeps one home per fact (a support has a term and a derivation already, contacts must be absent for a kind with none, `floating_item`'s instant and fix are the item's), and the floor is small and needed by A6, D2 and a member walking in depth.
- **(f) Inferred skate, and the hip-swing walk.** Recommendation: infer skate only under a style pack that declares `gravity`; measure the factory walk's hip-swing (feet off the floor by `L·(1 − cos stride)` at the contact pose, sliding near passing) in PR 2 and PR 3 before filing any planted-leg derivation in `cutan`. Why: a cartoon style that glides is right by declaration (catalogue B4), and the derivation (the gait's per-foot `join`/`unjoin`, the body's `y` following the planted leg) should be sized on measured numbers, not tuned by hand.

## 9. Fleet-search record (fleet-protocol)

Read directly for this specification: `an/verify/constraints.py` (`Constraint`, `DFLT_ORDER`, `compile_outcome`, the `gravity` and `light` checks as the patterns for gates and rest instants), `an/verify/joints.py` (`JOINT_CHECK_ORDER`, `joint_term`, `check_joint_violation`), `an/verify/holds.py` (`floating_item`), `an/stage/hold.py` (`Line`, `_above`, `_ground_line`, `_line_through`, `_on_line`, `_surface_at`, `_ground_at`, `_standing_entities`, `_nearest_support`, `_report`, `SURFACE_BONES`, `SUPPORT_TOLERANCE_PX`, `FLOAT_BAND_PX`), `an/stage/solve.py` (`declarations`, `build_puppet`, `landmarks_of`, the point resolver, `joint_residuals`, `_segment_gap`, `frame_times`, `shot_declares_solve`, `solve_knobs`), `an/ir/schema.py` (`JointSpec`, `SolveSettings`, `Weld`, `World`, `WorldMember`, `Frame`, `SceneLight`), `an/ir/holds.py`, `an/ir/joints.py`, `an/ir/world.py` (`Projection`, `_perspective_note`, `ground_scale`), `an/stage/world.py` (`member_shot_sizes`), `an/stage/rig.py` (`rig_origin`, `rig_structure`, `RigModel`), `an/genres/registry.py` (`EntityKind`), `an/genres/__init__.py` (`API_LEVEL`), `an/kinematics/joints.py` (`Contact`), `an/timing/timeline.py` (`key_times`, `cut_timeline`), `tests/_hold_fixture.py`, `tests/test_holds.py`, `tests/test_constraints.py`; in `cutan` (read-only): `cutan/characters/hands.py`, `cutan/characters/framing.py`, `cutan/characters/factory.py` (`stand_on_feet`), `cutan/characters/schema.py` (the default slots), `cutan/genre.py`, `cutan/motion.py` (the walk's contacts), `cutan/impacts/__init__.py` and `truth.py`, `cutan/verify/body.py`; docs: `misc/docs/constraints_catalogue.md` §A1, §B3, §B4, §D2, §3, §5; ADR 0008; ADR 0009; `misc/docs/architecture_as_built.md` §0 rows "Constraint layer v0", "Joints in the IR and the `solve` pass", "Holding things", "Kinematics solver", "The scene space"; `misc/docs/research/puppeteering_2026-10.md` §2, §4, §6. No existing component outside `an`/`cutan` was found for contact lints (the catalogue's §6 record covers the fleet search for the whole programme; nothing has changed since).
