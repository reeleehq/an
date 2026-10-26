# Structural constraints that force consistency in cut-out animation: a catalogue beyond joints

Session `constraints-research`, 2026-10-21, for `puppet-lead`; part of the epic [reeleehq/an#497](https://github.com/reeleehq/an/issues/497), a constraint layer under structured animation. This document catalogues the constraints, other than joints, that make a structured (cut-out) animation read as one consistent world, and for each says what it prevents, how to declare it, how to check it with a deterministic lint, and how to enforce it as a solver term or a derivation rule. It ends with a ranked build list for the lead, a map from the vocabularies of the 2D tools, and the fleet-search record.

## 0. Summary

- **One model.** Every constraint here is a residual over a world state: the static declarations (members, sizes, attachments, surfaces, the light) plus the pose of every node at a sampled instant, plus geometry derived from them. A constraint has three faces that share one declaration: *declare* (a line in `scene.md` or in an asset's metadata), *check* (evaluate the residual on sampled frames and report a `Finding`), *enforce* (a term in the per-frame solve, or a rule that derives the value so the residual is zero by construction). The lint and the solver must read the same declaration, or they will disagree the way two draw orders did before `an.stage.environments` removed the second one. The lead's decision for the epic fixes the interface: one declarative constraint statement in `an`, with a `check` (a lint run through the `SemanticCheck` registry in `an.genres.registry`, with `ValidationContext` and `Finding`) and an optional `term` (the solver's residual); every constraint ships as a lint before it is a term, and generalises an existing check rather than duplicating it (each entry's **Subsumes** line).
- **Derive before you lint, lint before you solve.** Body continuity and scene space already follow this: placement derived from the body, framing derived from the world. The lints catch what was authored by hand; the solver is for the cases where constraints compete (a hand on a wheel while the body sits on a seat while the arm has a length).
- **The viewer's checklist is the lint's checklist.** The cognitive-science benchmarks of intuitive physics test exactly four things in a scene: object permanence, shape constancy, spatio-temporal continuity and solidity [1,2]. A violation of any of them is what a viewer notices as "wrong" before they can say why. Those four, plus support, light and film grammar, are the catalogue's spine.
- **Twenty-two constraints in five groups**: within a frame (support, solidity, draw order from depth, attachment, rigidity and volume, ground-plane perspective, view agreement), within a shot (continuity, smoothness and arcs, contact-conditioned motion, gravity and settling, anticipation and follow-through, cadence and holds, causality and audio-visual synchrony), across cuts (permanence and state carry-over, identity constancy, size-relation constancy, screen direction and the 30-degree rule, eyelines, phase continuity), light (one light, shadows anchored at contact), and frames of reference (one line, deferred to `planes-research`).
- **What exists** in `an`/`cutan` today covers parts of seven of them (cut continuity, framing, draw-order validity, body attachment and its consistency, the style cadence lint, the step grid, sound anchors, screen direction in flight). The rest is missing, and most of the missing lints need no new declaration: they run on the compiled document and the evaluated timeline, which the core already builds without a browser.
- **Build first** (section 3): spatio-temporal continuity within a shot, support and foot skate, solidity between declared solids, draw order monotone in depth once scene space lands, cadence from the IR for a style, causality of sound cues, the light declaration with shaded-side art metadata, and object permanence across cuts. Each is a `SemanticCheck` over `an.motion.stage_poses` / `an.timing.timeline.evaluate_timeline` / `an.stage.timeline.node_box`, the primitives the body lint already composes.

## 1. One model: constraints as residuals over a world state

### 1.1 The state

The state at an instant `t` of a shot is what the compiler and the timing kernel already produce, and nothing more needs inventing to lint against it:

- **Declarations** (static): the shot's entities and their `stage` placements; scene-space members with world positions and sizes when the ADR 0007 branch lands; the rig of every character (bones, slots, attachments, `an.stage.rig`); the environment's planes and their parallax depth; asset metadata (today `body_attachment`; this catalogue adds `contacts`, `shaded_side`, `mirror_safe`, `support_top`); the scene's sounds and their anchors; the style spec.
- **Pose** (dynamic): `evaluate_timeline(timeline, t)` is a pure function of `t` (an#185) and returns every node's transform; `an.motion.stage_poses` gives the rest pose of every built node; the `FrameClock` says at which instants a frame samples the scene, so a lint and the render cannot disagree about when.
- **Derived geometry**: `an.stage.timeline.screen_position` and `node_box` compose a node's point or box up the tree and through the camera, so a lint can ask where a foot is on the canvas, and whether two boxes overlap, with no browser.

A constraint is then a function `C(declarations, pose_t, pose_{t-1}, ...) -> residual`, with a tolerance, a scope (frame, shot, scene, cut) and a severity. The owner's principle that joints are the model of the body applies to everything else as well: a seat is a surface, a hand holding a cup is a weld, a cast shadow is a projection of a contact point, a style's holds are a constraint on the derivative of the pose. None of them is about a car or a human body.

### 1.2 The three faces

| Face | What it is | Where it runs today | The principle |
|---|---|---|---|
| **Declare** | one line in `scene.md` (a `constraints:` list at scene or shot level) or a field in an asset's metadata | `an.ir.schema` (additive, `extra="allow"`) and the asset documents | declared once, in the owner's units (the body's bones, the world's metres, the art's `(u, v)`), never per shot |
| **Check** | a lint: evaluate `C` on the sampled instants, report a `Finding` with `ir_path`, severity and the derived value that would satisfy it | the `SemanticCheck` registry (`an.genres.registry`; the core's checks are registered in `an.ir.validate` with stages `scene`, shot and `finish`; genres register their own, as `cutan.verify.body` does) | deterministic first; a vision model only for what the declaration cannot carry (cutan#95) |
| **Enforce** | a term in the per-frame solve (`C = 0` as an equality, `C >= 0` as an inequality, with a compliance for soft ones, the XPBD form [3,4]); or a derivation rule that writes the value so `C` holds by construction (body placement, scene-space lowering) | the solver `puppet-research` designs; the lowering passes in `an.ir.space` and the compile passes | the same declaration object feeds the lint and the solver; the solver's output is re-linted (the body lint already re-checks derived placements) |

Enforcement has three known shapes, which Gleicher's taxonomy of constraint-based motion editing names: per-key (constrain the keys, interpolate between), per-frame inverse kinematics plus filtering (solve every frame, then smooth), and spacetime (one optimisation over the whole motion with the constraints and an objective) [5]. Witkin and Kass's spacetime formulation is the general case, where the principles of animation (anticipation, squash and stretch) fall out of the objective rather than being authored [6]. For a frame-exact, deterministic render the recommendation is per-frame solve plus a smoothing filter, with spacetime reserved for a later seam: it is what the owner described ("define sequences of positions of some elements and have the others resolve according to the joins"), and it is the form every 2D tool ships [7,8,9].

### 1.3 What already exists, read as instances of the model

Read the other way, each entry in section 2 carries a **Subsumes** line naming the existing check it generalises; the rule is generalise, never duplicate.

| Existing check | Catalogue entry | What it covers | What it does not |
|---|---|---|---|
| `cut_continuity` (an#394; `x`, `y`, `scale_x`, `scale_y`; 1 px / 0.01 tolerance; consecutive shots; a deliberate opening `set` exempts) | C1 | a placement that jumps at a cut | presence, held items, state; scene-space amends it so two different viewpoints are not compared |
| `screen_direction` (ADR 0007 branch, in flight) | C4 | left/right order flipping across a cut | the 30-degree rule; eyelines (filed to cutan) |
| `framing` (an#211) | A6-adjacent | the camera showing past a plate's edge | nothing about the cast |
| `stage_after`, `chain_draw_order_problems`, paint orders (an#430) | A3 | a draw anchor that exists and has no cycle; a paint order the engine can honour | draw order agreeing with depth |
| `body_attachment`, `body_attachment_consistency` (cutan#101) | A4, C3 | a body prop meeting its bones; its ratio and anchor constant across shots | any attachment that is not a body prop; motion during the shot (cutan#98) |
| `cutan.verify.style` (cadence, cuts, palette, measured on frames) | B6 | holds, pose changes per second, on ones/twos/threes, against a style's targets | a pre-render check on the IR's tweens |
| `step_hz` (an#89) | B6 | the pose grid is coarser than the frame rate | — |
| `CueAnchor` (`an.sound_anchors`) | B7 | a sound placed when a property reaches a value | a sound authored at a time that precedes its cause |
| `easings` checks | B2 | an easing the evaluators know | smoothness of the resulting trajectory |
| `cutan.impacts` ground truth | B3, B7 | exact contact instants for scoring estimators | a lint over an authored scene |
| `cutan.compile.gaze` saccades | C5 | ambient eye motion | an eyeline toward the other character |

## 2. The catalogue

Each entry: **Prevents** (the error class, with the plot-car instance where one exists), **Declare**, **Check** (the deterministic lint: inputs, when it can run, tolerance, severity), **Enforce** (solver term or derivation), **Status** in `an`/`cutan`.

Tolerances below are named, never literal: `SUPPORT_TOLERANCE`, `SKATE_TOLERANCE`, `OVERLAP_TOLERANCE` and so on, as fractions of the frame height or of the subject's extent, at module top, like `CUT_CONTINUITY_TOLERANCE` and `DFLT_TOLERANCE` are today.

### Group A: within a frame

#### A1. Support and contact

**Prevents.** A character floating above the seat, standing half a head below the floor, a cup hovering beside the table it is "on". Of PhysDiff's three physics errors, two are this one: *penetration* (the lowest point below the support) and *floating* (the lowest point above it) [10].

**Declare.** A support relation names a supported thing, a contact point on it and a surface: `{kind: support, of: paul, at: feet, on: seat}`. The contact point comes from the asset: a character's rig declares `contacts: {feet: [...]}` in its own units (the factory rig has `leg_l`/`leg_r` and no foot bone, so for v1 a leg's far end is the contact; a prop declares `contacts.base` as a `(u, v)` on the art, like a socket). The surface is a member's `support_top` (a `v` on its art), a plane's ground line, or a bare `y`. Under scene space, a surface is a horizontal line at a world depth.

**Check.** On the compiled stage at the shot's start (as the body lint does), and at every sampled instant while the relation holds: the signed distance from the contact point to the surface, along the surface's normal, must be within `SUPPORT_TOLERANCE`; below is penetration, above is floating. Needs `node_box`/`screen_position` and the contact declaration. Severity: error when the relation is declared, warning when inferred (a character on a ground plane with no declaration, bottom of box far from the ground line).

**Enforce.** The inequality `n · (p_contact - p_surface) >= 0` with a unilateral solve (the contact constraint of rigid-body simulation [11] in its position-based form [3]), or the derivation: place the supported member's `y` so the contact lands on the surface, the way the body pass places a prop by its sockets. Moho's "lock" of a bone to the floor and Blender's Floor constraint are this rule in two tools [8,12].

**Subsumes.** Nothing existing; the first constraint of its group. The walk presets' contact instants become its input.

**Status.** Partial (an#502): a stage shot's floor line is `solve: {ground: y}`; an item `overrides: {held_by: ground}`, put down by `place`, or landing after a `release` rests with the lowest point of its painted pixels (the texture's alpha hull) on it, by derivation; the `floating_item` check warns when an item a hand takes hovers above it or sinks into it. Characters' feet, `support_top` on members and scene space's ground are missing.

#### A2. Solidity: non-penetration

**Prevents.** Two characters' torsos interpenetrating, a prop drawn through a body it is beside, a hand through a wheel rim. IntPhys names this *solidity*: two objects cannot occupy the same space [2]. In 2D the art overlaps by design when one thing is behind another, so the constraint is about members declared to share a depth band.

**Declare.** `{kind: solid, among: [paul, jerry, wheel]}`; with scene space, members within `SOLID_DEPTH_BAND` of each other are solid by default and `among` is the override. A member may carry a collision shape: its `node_box` by default, an art-declared polygon later.

**Check.** At sampled instants: the overlap area (or penetration depth, box against box) between any two solids must be under `OVERLAP_TOLERANCE` of the smaller box, except at declared contacts (A1, A4) and held items. Severity: warning (boxes are upper bounds on painted pixels under `fit: contain`, so an overlap of boxes is evidence, not proof).

**Enforce.** The unilateral distance constraint between shapes [3,11]; in a per-frame solve it is the term that keeps a pinned hand from pushing the arm through the torso.

**Subsumes.** Nothing existing; the body lint's "limbs are not crossed" is a rig-internal special case it should absorb.

**Status.** Shipped as the `solidity` check (an#509, `an/verify/constraints.py`): characters and props whose boxes overlap by more than a quarter of the smaller, with no `stage.after` on either, warn; `overrides: {solid: false}` opts out; path and text props are drawings, not solids.

#### A3. Occlusion and draw order from depth

**Prevents.** The far character painted over the near one; a prop behind the body in one shot and in front in the next; a limb changing paint order mid-shot without a view change. Occlusion is also how a viewer reads depth, so a wrong order moves things in the viewer's world.

**Declare.** Nothing new when scene space is in: draw order is derived from `z` (far first), which ADR 0007 states. Without scene space, `stage.after` is the declaration. A rig's per-view paint order is the genre's (`chain_paint_order`).

**Check.** Two of them. (i) *Monotone in depth*: the order the compiler paints members is non-decreasing in `z`; a hand `after` that contradicts the world is a warning naming both. (ii) *Stable across the scene*: for every pair of members both present in two shots, the painted order is the same unless their `z` order changed or a view swap happened; a flip is a warning. Runs on the compiled document (`walk_document` order), no browser.

**Enforce.** A derivation rule, not a solver term: draw order is a function of depth, and a style that wants otherwise says so with `after`.

**Subsumes.** `StagePlacement.after` and `after_problems` (an#344) as the mechanism and its validity check; `chain_draw_order_problems` and the paint-order capability check (an#430) as preconditions; ADR 0007's "draw order is depth" rule as the derivation.

**Status.** Part (ii) shipped as the `draw_order` check (an#510, `an/verify/constraints.py`): a pair painted one way in a shot and the other way in a later one warns unless `stage.after` changed for either. Part (i), painted order against world depth, is not built (a world's members are skipped: depth already derives their order).

#### A4. Attachment and parenting (the weld)

**Prevents.** A hat sliding off a head that moves, a cup that stays when the hand goes, a steering wheel whose hands do not come from the driver's shoulders (the plot-car wheel; cutan#101 fixed the body case).

**Declare.** Scene space has `attached: {to, at?, scale?}`; the cut-out genre has `body_attachment` sockets. The general form is a *weld* between a point on the carrier and a point on the carried, in each one's own units: `{kind: held, by: paul/hand_r, item: cup, at: {carrier: [u, v], item: [u, v]}}`, with `from`/`until` instants for pick-up and release (an attach is a joint; a release is the owner's "unjoin").

**Check.** At every sampled instant in the interval, the two points coincide on the canvas within `WELD_TOLERANCE`; the item's rotation follows the carrier's unless `free_rotation`; an item attached to a node not on stage is an error. The body lint's per-shot check is this with sockets; cutan#98 (checking through motion) is this lint over time.

**Enforce.** A derivation: the carried node's transform is composed from the carrier's (parenting). When the rig is flat (arms are siblings of the torso) and the carried thing must also satisfy A1 or A2, it becomes a solver equality constraint (a pin joint between two bodies, which is `puppet-research`'s model).

**Subsumes.** `cutout.body_attachment` (cutan#101: the per-shot socket, view and relation check, with sockets as the weld points) and ADR 0007's `attached: {to, at, scale}` member (the weld declared in the world); cutan#98 (checking through motion) is this entry's time dimension.

**Status.** The general held-item weld shipped as `Shot.welds` and the `held_item` check (the item stays at its offset from the carrier drawn centre between pick-up and release, sampled through motion). The composing derivation shipped as the hold verbs (an#502: `grasp`, `place`, `release`, `handover`, `swap`, `an/stage/hold.py`): an item follows its holder's solved transform, rotation and mirror included, between a pick-up and a release that keep its world pose, with the hand reaching it. Partial otherwise: body props (cutan#101), scene-space attachments.

#### A5. Rigidity, size and volume conservation

**Prevents.** A part that stretches because a tween scaled `scale_x` alone; a character whose head grows across a shot; an arm that lengthens to reach (the fix the Kovar footskate cleanup allows, but only slightly and deliberately [13]). IntPhys calls the cross-cut version *shape constancy* [1].

**Declare.** A rigid part is the default; deformation is declared: `{kind: deformable, of: ball, preserve: volume}` or a style's `squash_stretch: true`. A rig's bone lengths are the rigidity declaration for a chain.

**Check.** (i) *Rigid*: at every sampled instant a node declared rigid has `scale_x == scale_y` within `RIGID_TOLERANCE` and the distance between any two of its joints equals the rest distance. (ii) *Volume*: under declared squash and stretch, `scale_x * scale_y` stays within `VOLUME_TOLERANCE` of 1 (Lasseter's statement of the principle: the shape changes, the volume does not [14]). (iii) *Size across shots*: in the character's units, the ratio of two members' sizes is the same in every shot (the body lint does this for body props; scene space makes it true for everything by derivation).

**Enforce.** A distance constraint per rigid pair [3]; for a deformable cut-out, the as-rigid-as-possible energy is the term that keeps a dragged mesh looking like paper rather than rubber [15]; volume as a constraint on the product of scales, which Blender exposes as Maintain Volume [12] and Chenney et al. derive from velocity and collision for cartoon squash [16].

**Subsumes.** The `scale_tolerance` half of `cutout.body_attachment` and the size half of `cutout.body_attachment_consistency` (a body prop's size relative to its character, within and across shots) are instances of (iii).

**Status.** (i) aspect and (ii) volume within a shot shipped as the `rigidity` check, opt-in per entity (`overrides: {rigid: true}`, `{preserve_volume: true}`) because the `squash_stretch` preset deforms on purpose; the rest-distance between joints waits on the kinematic layer. Body ratio across shots belongs to the body lint.

#### A6. Ground-plane perspective: feet, horizon and scale

**Prevents.** A character standing lower in the frame but drawn larger, a near tree smaller than a far one, two characters on one ground plane at the same `y` with different scales (the wheel/Paul ratio drift between framings is the attachment case of this).

**Declare.** A horizon per shot or environment (`horizon_y`) and a ground plane; with scene space both come from the viewpoint (`vanish`), and nothing more is declared.

**Check.** For every member standing on the ground plane, the pair (contact `y`, on-screen height) must satisfy the single-view relation: heights are proportional to the distance from the contact point to the horizon line [17]. Two standing members whose ratios disagree beyond `PERSPECTIVE_TOLERANCE` are a warning naming the scale each should have. Runs on the compiled stage; needs A1's contact points.

**Enforce.** Derivation by scene space's projection: `scale = size / native × f / depth`. Under scene space this entry is a lint on hand placements that override the world.

**Subsumes.** ADR 0007's `viewpoint` check ("a hand placement that disagrees with the world"): the perspective relation is what that disagreement measures for members on one ground plane; `framing` (an#211) stays beside it as the plate's own check.

**Status.** Missing as a lint; the derivation is in flight (ADR 0007).

#### A7. View and facing agreement with the viewpoint

**Prevents.** Art drawn from the driver's seat laid over a driver seen through the windscreen (the plot-car wheel, caught by cutan#101 for body props); a character in `front` view when the camera is behind them; a `side` walk cycle while the viewpoint is frontal.

**Declare.** The character's view swap set and the shot's viewpoint. Nothing new.

**Check.** The angle between the viewpoint's look direction and the character's facing picks a view (`front`, `three_quarter`, `side`, `back`) by a table; a view in force that disagrees is a warning naming the one the angle picks. ADR 0007 files this in `cutan` (view selection from the viewpoint).

**Enforce.** Derivation: select the view from the angle; the swap is written by the lowering.

**Subsumes.** The view-agreement part of `cutout.body_attachment` (art drawn in a view the character is not in; `first_person` with the character on screen); ADR 0007 files the character case to `cutan`.

**Status.** Partial (body props). Filed, not built, for characters.

### Group B: within a shot

#### B1. Spatio-temporal continuity

**Prevents.** A node that teleports mid-shot because a `set` landed in the middle of a tween, or two tweens on the same property do not meet; a member that vanishes for a frame. IntPhys: *spatio-temporal continuity*, an object reappearing where its motion does not allow [1,2].

**Declare.** Nothing; continuity is the default. A deliberate jump is a `set` with a named reason, which `cut_continuity` already recognises at a shot's start (`_DELIBERATE`).

**Check.** On the evaluated timeline at the frame clock's instants: for every node and property, the per-frame displacement must be under `JUMP_TOLERANCE` (a fraction of the node's extent per frame) unless a `set` on that property is at that instant; a visual whose swap key changes and back within one frame is a flicker. Severity: warning, with the instant and both values. The flat timeline makes this a loop over channels, not a search.

**Enforce.** A solver has no term for this; the fix is on the author's side (the lint names the colliding actions). In the solver, continuity comes from solving every frame from the previous frame's state.

**Subsumes.** Nothing existing within a shot; it is the within-shot twin of `cut_continuity` (an#394), and the two should share the deliberate-jump vocabulary (`_DELIBERATE`) and the tolerances.

**Status.** Shipped as the `continuity` check (an#508, `an/verify/constraints.py`); `an validate` warns on a mid-shot jump and on a value held for under a frame. Every input existed (`evaluate_timeline`, `FrameClock`).

#### B2. Smoothness, ease and arcs

**Prevents.** Mechanical motion: linear tweens with corners at every key, a limb that stops dead, a head that moves in straight lines. Two of the twelve principles are this: slow in and slow out, and arcs [14,18].

**Declare.** A style's `easing` list already constrains the vocabulary; add a smoothness target per style: `smoothness: {sparc: [low, high]}` or a jerk budget, measured like cadence is.

**Check.** On evaluated trajectories of a node's anchor: finite-difference velocity, acceleration and jerk per frame; the metric is the spectral arc length or the log dimensionless jerk, the two smoothness measures shown to be valid, consistent and reliable [19,20]; a C0 corner at a key where the velocity direction flips without a declared contact (B3) is a warning. *Arcs*: the curvature of the path between two keys of a limb's tip should be non-zero and of one sign for a move declared as an arc (a preset such as `point` can declare it). These are measured targets in the style spec, not hard errors, exactly as `cutan.verify.style` treats cadence.

**Enforce.** Per-frame solve plus a low-pass filter over the solved trajectory (Gleicher's second category [5]); or a minimum-jerk interpolant between pinned keys, which is the bell-shaped velocity profile human reaching has [21]; spacetime for the full version [6].

**Subsumes.** The easing checks (`_check_tween_easings`, `_check_default_easing_reach`) as the vocabulary gate; the measurement follows `cutan.verify.style`'s targets-and-estimators contract.

**Status.** Smoothness shipped as the `motion_style` check: the pack's `motion.smoothness.max` against the log dimensionless jerk of each move. Arcs are missing.

#### B3. Contact-conditioned motion: no foot skate, impulses at impact

**Prevents.** Feet sliding on the ground during a walk (foot skate, the third PhysDiff error [10,13]); a hand on a wheel that drifts along the rim; a ball that passes through the floor instead of bouncing; a character whose body keeps going after the feet stop.

**Declare.** A1's support relation with an interval gives the contact phases; a gait preset can emit them (the walk presets already know their contact instants: "the body sinking after contact"). An impact is a declared event or a derived one (the contact point reaches the surface with a downward velocity).

**Check.** (i) *Skate*: while a contact holds, the contact point's tangential displacement per frame is under `SKATE_TOLERANCE` (the PhysDiff definition: horizontal drift of a foot in contact across two adjacent frames [10]). (ii) *Impact*: at a declared impact instant the normal velocity reverses or goes to zero within one frame; an object whose normal velocity continues through the surface is penetration. `cutan.impacts` has the ground-truth model (the frame clock, the bracketing frames) to express the instant exactly.

**Enforce.** Friction as a constraint that pins the tangential position of a contact for the phase (position-based friction [3]); Kovar's cleanup is the per-frame IK that keeps the foot planted and adjusts the chain smoothly [13]. Chenney's cartoon simulation adds the squash at the impact from the velocity [16].

**Subsumes.** Nothing existing as a lint; `cutan.impacts`' ground truth (frame clock, bracketing frames) is its fixture generator, and cutan#98's "checking during motion" is the same loop over A1 and A4 declarations.

**Status.** Missing as lints; the ground-truth side exists for test fixtures.

#### B4. Gravity and settling

**Prevents.** A dropped cup that stops in the air; a hanging thing (a pendant, a sleeve, a rope) that points sideways while nothing holds it; a thrown object moving in a straight line. The classic cartoon exception (a body suspended in space stays there until it notices [22]) is a *style* decision and must be declarable, which the owner asked for ("gravity, optional, for the style").

**Declare.** Scene-level `gravity: {direction: [0, 1], strength: g}` or `gravity: none` in the style spec; per member `airborne: {from, until}` for a throw; a hanging member declares its pivot (a joint) and that it hangs.

**Check.** (i) *Unsupported falls*: a member that is neither supported (A1), attached (A4) nor declared airborne, and whose vertical velocity is zero for more than `HOVER_FRAMES`, is a warning. (ii) *Ballistic*: while airborne, the second difference of `y` is constant and positive within `BALLISTIC_TOLERANCE` (the trajectory is a parabola); a straight-line throw is a warning. (iii) *Hangs*: a hanging member's long axis points along gravity when its pivot is at rest, within `HANG_TOLERANCE`.

**Enforce.** The external force term in the solver (gravity in XPBD, Spine's physics constraints and Moho's bone dynamics for the hanging and settling case [3,7,8]); for the derivation form, a hanging member's rotation is set from its pivot's acceleration.

**Subsumes.** Nothing existing; `puppet-research`'s gravity-to-settle-among-options is the solver side of this entry.

**Status.** (ii) ballistic and the hover half of (i) shipped as the `gravity` check, for entities that declare `airborne` under a pack that declares `gravity`. Unsupported falls (need supports, A1) and hangs (need joints) are missing.

#### B5. Anticipation, follow-through and overlapping action

**Prevents.** A character that starts a big move with no wind-up, stops all parts at once, moves every part at the same rate. Thomas and Johnston's principles [18]; Lasseter's restatement for computer animation [14]. These are the ones most easily lost when an agent writes tweens from instructions.

**Declare.** As style targets, like cadence: `anticipation_frames: [low, high]`, `overlap_lag_frames: [low, high]` per style (South Park has almost none; Reiniger has long settles). As presets: `pop_in`'s overshoot and `_settled` already encode follow-through; a preset can declare its anticipation.

**Check.** On evaluated trajectories: for a move of a parent node larger than `BIG_MOVE` there is a counter-move within `ANTICIPATION_WINDOW` before it (sign of velocity opposite, small); after the parent stops, child nodes with declared `follows` (hair, sleeves, a held item) stop later by a lag in the target range; the lag between parent and child velocity peaks is the overlap. Measured, reported against the style's range as a warning.

**Enforce.** Follow-through and overlap come free from a solver with secondary dynamics (a spring on the child: Spine physics, Moho dynamics, Blender's and Harmony's equivalents [7,8,9,12]); anticipation comes from spacetime optimisation [6] or from a preset.

**Subsumes.** Nothing as a check; the presets' overshoot and `_settled` landings are the authored form.

**Status.** Anticipation shipped in the `motion_style` check (`motion.anticipation`: a counter-move of a frame range ends where a big move starts). Overlap and follow-through (`follows`) are missing.

#### B6. Cadence and holds: timing as a constraint

**Prevents.** A South Park scene that eases smoothly, an OverSimplified scene with no holds, a Reiniger scene on ones. The cut-out styles were measured on this exact axis and the style specs carry the targets: OverSimplified is bursts of 4 to 12 frames then a hold (`tween_duration_s: [0.13, 0.4]`, `default_easing: ease_out`, no `step_hz`), South Park is stepped.

**Declare.** Already declared: the style spec's `tween_duration_s`, `easing`, `step_hz`, and the cadence targets.

**Check.** Two tiers. (i) *Pre-render, on the IR*: every tween's duration within the style's `tween_duration_s`; a gap between consecutive changes of any node shorter than `MIN_HOLD` where the style says bursts-and-holds; an easing outside the style's list; `step_hz` as the style says. Deterministic, cheap, before any render. (ii) *Post-render, on frames*: what `cutan.verify.style` does today (identical-frame share, pose changes per second, on ones/twos/threes), kept as the measured truth because a render can differ from the IR (a saccade, a blink).

**Enforce.** Derivation: a style's `step_hz` resamples every tween to the grid (exists); a hold policy that snaps tween durations into the range and inserts holds is the add.

**Subsumes.** `cutan.verify.style` (the measured tier, unchanged) and `step_hz` (an#89) as the grid rule; the pre-render tier reads the same style spec.

**Status.** Partial: the post-render measurement exists; the pre-render IR lint does not.

#### B7. Causality and audio-visual synchrony

**Prevents.** The thud before the hit; the mouth moving after the voice; a reaction shot before the action; the bullet holes before the shots (a famous continuity error of exactly this kind [23]).

**Declare.** Sound cues already anchor to a property reaching a value (`CueAnchor`); a cue authored at a time instead names its cause: `cause: {when: ball/y, reaches: {y: 310}}`. Dialogue carries word timings.

**Check.** (i) *Order*: an effect's instant is not before its cause's instant. (ii) *Tolerance*: the offset between a sound and its visible cause is within the detectability window of audio-visual synchrony, about +45 ms sound-ahead to −125 ms sound-behind for speech-like material [24,25] (sign convention varies by source: state it). Beyond the window is a warning; sound ahead of its cause beyond `CAUSE_TOLERANCE` is an error (an effect before its cause). (iii) *Lip sync* is this constraint between viseme track and audio, already produced by content hash; the lint is a consistency check that the two refs came from the same input.

**Enforce.** Derivation: anchor the sound to the event (exists); the solver contributes the exact contact instant (B3) so the anchor lands on the frame of impact.

**Subsumes.** `CueAnchor` / `an.sound_anchors` (the derivation) and the dialogue-fits checks (`dialogue_fits`) as the timing preconditions.

**Status.** Partial. Anchors shipped; (i) order and (ii) tolerance shipped as the `causality` check for a shot cue that declares `cause`. The dialogue and lip-sync consistency check (iii) is missing.

### Group C: across cuts

#### C1. Object permanence and state carry-over

**Prevents.** A character present in shot 1 and 3 but not 2 with no exit; a cup full in the close-up and empty in the wide; a hat on, then off, then on; a window open then closed. IntPhys's *permanence* [1,2]; the script supervisor's job in live action, where props and costume are the commonest continuity errors and a change is an error unless time passing explains it [23,26].

**Declare.** The world (scene space) says who exists; a shot says `hide` for what is out of frame; an exit is an action (`slide_out`) or a `set` of visibility. State is a swap key or a property with a declared *persistence*: `persistent: [cup/level, hat/worn]` at scene level, meaning its value carries across cuts unless changed on screen.

**Check.** (i) *Presence*: an entity present in shots `i` and `i+k`, absent from the shots between while the film clock is continuous (no transition declaring time passing, no `time_jump`), with no exit or entrance action, is a warning. (ii) *State*: for every persistent property, the value at the end of a shot equals the value at the start of the next shot the entity appears in, unless an action changes it on screen; `cut_continuity` is this for `x`, `y` and scale between consecutive shots. (iii) *Uniqueness*: one member drawn twice in one shot is an error.

**Enforce.** Derivation: scene space adds members in frame; a persistent property's start value is copied from the last shot that showed it (the lowering fills the start state, as it fills `stage`).

**Subsumes.** `cut_continuity` (an#394) as the placement case of (ii), amended by ADR 0007 (no comparison across two different viewpoints); the uniqueness check extends `entity_refs`.

**Status.** Presence (i) and uniqueness (iii) shipped as the `object_permanence` check, with `Transition.time_jump`; persistent state (ii) is missing. Placements between consecutive shots are `cut_continuity`.

#### C2. Identity constancy

**Prevents.** The same character drawn from two art versions in one scene; a colour that differs per shot; a mirrored character whose text, parting, scar or watch changes hands (mirroring flips handedness, which the body lint already knows for body props).

**Declare.** The asset library's versions and the lockfile already fix identity per project. Art declares `mirror_safe: false` when a flip changes it.

**Check.** (i) Every shot's entity for one member resolves to the same asset version (the lockfile makes this an error when it does not). (ii) A `mirror` of an asset with `mirror_safe: false` is a warning. (iii) Post-render: a member's palette (the style lint's measurement, restricted to the member's box) is the same across shots within `PALETTE_TOLERANCE`.

**Enforce.** Derivation: one reference per member in the world, resolved once.

**Subsumes.** The library lockfile check (`an.stores.library_lock`, checked by `an validate`) and the mirrored-prop rule of `cutout.body_attachment` ("a mirrored character carries a mirrored prop").

**Status.** Partial (library lock). The mirror flag and the per-member palette are missing.

#### C3. Size-relation constancy

**Prevents.** The wheel/Paul ratio changing between the two-shot and the close-up (the plot-car case, cutan#101 for body props); a prop that is half a character tall in one shot and a third in the next.

**Declare.** Sizes in the world (scene space); nothing per shot.

**Check.** For every pair of members both present in two shots, the ratio of their on-screen heights, corrected by the depth ratio the viewpoints give, is constant within `RATIO_TOLERANCE`. `body_attachment_consistency` is this for body props in the character's units.

**Enforce.** Derivation by projection from the world (ADR 0007).

**Subsumes.** `cutout.body_attachment_consistency` (cutan#101: size and anchor drift of a body prop across shots) as the body case; ADR 0007's `viewpoint` check for members the world places.

**Status.** Partial (body props); general form arrives with scene space; the lint on hand overrides is what remains.

#### C4. Screen direction and the 30-degree rule

**Prevents.** Crossing the line (two characters swapping sides at a cut); a jump cut (two consecutive shots of one subject from nearly the same angle and size).

**Declare.** Viewpoints (scene space). Nothing more.

**Check.** (i) *Line*: `screen_direction` (in flight) flags a left/right flip of two present entities. (ii) *30 degrees*: two consecutive shots with the same subject whose viewpoints differ by less than `JUMP_CUT_ANGLE` in look direction and less than `JUMP_CUT_SIZE` in subject size are a jump cut, a warning (the convention: move at least 30 degrees or change the size substantially [27,28]). Deterministic from two viewpoints, which is only possible once shots are viewpoints onto one world.

**Enforce.** None; it is a note to the author (or a planner that picks coverage from the named viewpoints).

**Subsumes.** ADR 0007's `screen_direction` check (the line); the 30-degree rule is a second check on the same two viewpoints.

**Status.** The 30-degree rule shipped as the `jump_cut` check (`an/verify/constraints.py`): consecutive shots whose viewpoints frame the same world subject warn when the look directions differ by under 30° and the subject's apparent size by under x1.3. The line (i) is `screen_direction`.

#### C5. Eyelines and gaze

**Prevents.** Two characters in conversation looking away from each other across a cut; a character looking at a thing that is on the other side of the frame; a reaction shot whose gaze does not match the cut (the eyeline match [27,28]).

**Declare.** `looks_at: jerry` on a character per shot or per dialogue line (dialogue already has `direction`); the rest is in the world.

**Check.** The pupil offset's sign and the head's facing agree with the target's screen side (and, with scene space, its direction in the world) within `GAZE_TOLERANCE`; across a cut, a character looking off screen is matched by the target being on that side in the next shot. Runs on the compiled face nodes (the genre's).

**Enforce.** Derivation: the gaze and facing are set from the target's position (a look-at constraint, the cut-out version of IK aiming); saccades (existing) are added on top.

**Subsumes.** Nothing as a check; `cutan.compile.gaze` (saccades) and the dialogue `direction` field are what it reads and adds to.

**Status.** Missing (filed to cutan by ADR 0007).

#### C6. Match on action and phase continuity

**Prevents.** A walk cycle that restarts at the cut; roadside poles that reset phase when the framing changes (the plot-car streams); an arm halfway through a gesture that starts over.

**Declare.** Nothing; film time is one clock. A loop declares its period.

**Check.** For a loop or stream present across a cut, its phase at the cut's instant in film time is continuous within `PHASE_TOLERANCE`; a cyclic preset (walk) running across the cut continues its cycle.

**Enforce.** Derivation: instances positioned by film time, not per shot (ADR 0007 states this for streams); the same rule for cyclic presets is the add.

**Subsumes.** ADR 0007's rule that stream instances are positioned by film time (the derivation for streams).

**Status.** Partial (streams, in flight); cyclic presets across cuts are missing.

### Group D: light

#### D1. One light direction per scene; shading agrees

**Prevents.** A character lit from the left beside a prop lit from the right; a plate with a morning sun and a character with a noon highlight; a close-up whose shading side flips from the wide. In forensics, inconsistent shading and shadows are a deterministic feasibility test: a set of shadow constraints with no common light source proves manipulation [29]. For generated art this is the common failure, since each image is lit by its own prompt.

**Declare.** Scene-level `light: {direction: [dx, dy], elevation?: deg}` (or named: `key: upper_left`). Art declares its shaded side in metadata, `shaded_side: left|right|top|bottom|flat`, next to `body_attachment`; `cutan.art_brief` puts the light into the prompt so generated art matches, and the declaration records what was asked.

**Check.** Every drawn member's `shaded_side` (mirrored when the member is mirrored) agrees with the scene's light within a quadrant; `flat` art is exempt; a disagreement is a warning that names the member and the side the light implies. Runs on declarations only. A measured version (dark pixel share on the left vs right half of the member's box, with the style lint's estimators) is a second tier.

**Enforce.** Derivation into the art brief (ask the generator for the right light); for a procedural shade, a drop-shadow filter direction derived from the light.

**Subsumes.** Nothing as a check; `cutan.art_brief` (cutan#93) is where the declaration reaches the generator.

**Status.** Missing.

#### D2. Cast shadows anchored at contact and consistent with the light

**Prevents.** A character with a contact shadow while floating, or none while standing; a shadow that stays while the character walks; a shadow on the wrong side of the light. A cast shadow's position is what tells the viewer where an object is in depth: moving only the shadow changes whether a ball looks like it rises or recedes [30]. A shadow is therefore the picture's support cue and belongs to A1, not to decoration.

**Declare.** `shadow: contact` on a supported member (a flattened ellipse at the contact point) or `shadow: cast` (a skewed silhouette along the light); the light from D1; the surface from A1.

**Check.** A member's shadow node is anchored at its contact point on the surface, offset along the light's ground projection; it follows the member every frame (a weld, A4); a supported member with no shadow where the style asks for one is a warning. Runs on the compiled tree.

**Enforce.** Derivation: the shadow is a compile-pass product of the contact point, the surface and the light (a synthetic node, like the stage's `__band` containers), never authored.

**Subsumes.** Nothing existing; it composes A1 (the contact), A4 (the weld to the caster) and D1 (the light).

**Status.** Missing.

### Group E: frames of reference

One constraint only, stated here because the others depend on it and `planes-research` owns the model: every member belongs to exactly one frame at a time (the vehicle, the stage, the far plane); a change of frame is an explicit event (thrown out of the window, stepping off the platform); within a frame, every constraint in groups A to D is evaluated in that frame's coordinates (the seat supports Paul in the car's frame, not the road's). The check is that a member with constraints in two frames at one instant is an error, and that a frame change is accompanied by a velocity hand-over (B1 continuity holds in the stage frame across the change). `planes-research` should take this line as its contract with the catalogue.

## 3. What to build first: a ranked list for the lead

Ranked by (a) how often the error class reached a viewer in the two plot-car rounds, (b) whether a new declaration is needed, (c) whether every input exists today in the compiled document and the timing kernel. All of these are `SemanticCheck`s registered in `an.ir.validate` (core) or by the genre (`cutan`), with the same shape as `cutan.verify.body`: compile the shot's stage once, sample the timeline, measure with `node_box`/`screen_position`.

| Rank | Lint | Entry | Needs a new declaration? | Inputs today | Home | Size | Shipped |
|---|---|---|---|---|---|---|---|
| 1 | spatio-temporal continuity within a shot (no mid-shot jump, no one-frame flicker) | B1 | no | `evaluate_timeline`, `FrameClock` | `an` | small | an#508 |
| 2 | support, penetration, floating and foot skate | A1, B3 | yes: `contacts` on assets, `support` relation, a surface (`y`, a member's `support_top`, scene-space ground) | `node_box`, rig bones | contacts in the rig: `cutan`; the relation and surface: `an` | medium |  |
| 3 | solidity between declared solids | A2 | yes: `solid` (default from depth band once scene space lands) | `node_box` | `an` | small | an#509 |
| 4 | draw order monotone in depth and stable across shots | A3 | no (with scene space) | compiled tree, `z` | `an` | small | an#510 (ii) |
| 5 | pre-render cadence lint from the IR against the style (tween durations, holds, easing list) | B6 | no (style specs carry it) | flat timeline, style spec | `cutan` | small |  |
| 6 | causality and audio-visual tolerance for sound cues and dialogue | B7 | `cause` on timed cues | cues, anchors, word timings | `an` | small |  |
| 7 | the light declaration with `shaded_side` art metadata, plus the art-brief hook | D1 | yes | declarations only | `an` (declaration), `cutan` (art brief) | small |  |
| 8 | object permanence: presence across shots, persistent state, uniqueness | C1 | `persistent`, `time_jump` on a transition | scene timeline | `an` | medium |  |
| 9 | the 30-degree rule over viewpoints | C4 | no (scene space) | viewpoints | `an` | small |  |
| 10 | held items as welds with pick-up and release, checked through motion (closes cutan#98's shape for props) | A4 | `held` | `screen_position` | `an` (weld), `cutan` (hands) | medium |  |
| 11 | rigidity and volume under squash | A5 | `deformable` | evaluated scales, bone rests | `an` | small |  |
| 12 | eyeline and look-at | C5 | `looks_at` | face nodes | `cutan` | medium |  |
| 13 | smoothness, arcs, anticipation and overlap as measured style targets | B2, B5 | style targets | evaluated trajectories | `cutan` (targets), `an` (measure) | medium |  |
| 14 | gravity: hover, ballistic, hang | B4 | `gravity`, `airborne` | evaluated trajectories | `an` | medium |  |
| 15 | ground-plane perspective on hand overrides | A6 | no (scene space) | contacts, horizon | `an` | small |  |
| 16 | contact shadows as a derived node | D2 | `shadow` | contacts, light | `an` | medium |  |

Three remarks for the split. Ranks 1, 3, 4, 6, 9 and 11 are pure core and touch no genre file, so they can be one worker in one `an` worktree, disjoint from scene space's files (`an/ir/space.py`, `an/stage/space.py`) if the checks live in a new module (`an/ir/constraints.py` or wherever the lead's ADR puts the declaration schema) rather than appended to `validate.py`. Rank 2 is the one with the biggest payoff and the one most entangled with `puppet-research`'s solver (contacts are the solver's unilateral constraints) and with scene space (the surface is a world object): it should be specified jointly before either builds. Rank 5 is the cheapest win for the styles and sits entirely in `cutan`.

## 4. The same constraints in the tools practitioners use

The 2D tools state these constraints under their own names; the mapping shows the catalogue is not invented. Harmony's constraint nodes pull a drawing to two or three peg pivots (a rod, or a weld to two points) with an `Active` weight, and a Transformation Switch multiplies into that weight [9]. Moho has angle limits on bones (joint limits), inverse-kinematics locking of a foot to the floor (A1), target bones (a pin), and bone dynamics, a spring that gives follow-through for free (B5) [8]. Spine applies its constraints in tree order, with IK, transform and path constraints, and since 4.2 physics constraints for secondary motion with a deterministic mode for the editor (B5, B4); its draw order is a keyed property of the skeleton (A3) [7,31]. Rive ships IK, distance, transform, rotation, scale and follow-path constraints [32]. Blender's constraint list has Child Of (A4), Floor (A1), Maintain Volume (A5), Limit Location/Rotation (joint limits) and Follow Path [12]. None of them ships a *lint*: they enforce in the editor and leave consistency across shots and the film-grammar rules to the person. That is the gap this programme fills, and why the check face matters as much as the enforce face for an agent-authored film.

## 5. Open questions for the lead

1. **Decided by the lead (an#497).** One constraint interface in `an`: a declarative statement with a `check` run through the `SemanticCheck` registry and an optional `term`; a lint before a term; existing checks generalised, never duplicated. What this catalogue adds to the decision: the kinds and their fields (section 2), and the proposal that a kind's `check` and `term` evaluate one residual function, so the lint and the solver cannot disagree about what "satisfied" means. The `constraints:` list is scene-level data like `space`, so `an.ir.schema` (additive) is its natural home, with genres contributing kinds (contacts on a rig are the genre's).
2. **Where the residuals live if the solver is its own package.** If a 2D constraint solver is independently reusable (per the brief and architecture-first), the residual functions of A1, A2, A4, A5, B3 and B4 belong there and `an` imports them for the `check`; if not, they live beside the schema. Either way one definition.
3. **Tolerances in whose units.** Body continuity chose the character's units (a fraction of the shoulder span). The general rule proposed here: tolerances relative to the constrained member's extent, never in pixels, so a close-up and a wide agree.
4. **Severity policy.** Declared and violated: error. Inferred (no declaration, but the world implies it): warning. Measured style targets: warning, as cadence is. The owner's "frames cannot violate the physical constraints unless explicitly unjoined" argues for errors on declared joints and contacts; the deliberate exceptions are declared (`airborne`, `unjoin`, cartoon gravity in the style).
5. **Scene space's surface.** A1 needs a surface; scene space has `y` in the world and planes with parallax but no ground line. The smallest add is a `ground: y` on the space (or per plane) and `support_top` on members; worth agreeing with `scene-space` and `planes-research` before rank 2 starts.

## 6. Fleet-search record (fleet-protocol)

- **Group and routing.** `g_av`; its "where does this go?" table routes structured animation to `an` and anything cut-out to `cutan`; verification is `an.verify` / the `SemanticCheck` registry; measured style targets are `cutan.verify.style` and `an.verify.prosody` (the pattern for every measured constraint above).
- **Components searched.** `ir discover packages` and `ir discover skills` for "animation constraints contact collision solver", "lint consistency check continuity physics", "animation constraints physics continuity lint": both corpora empty on this machine (not built; not absence). `priv skills-index -r -f constraint`: 24 hits, none about physical or continuity constraints (`artful-shot-schedule`'s "model-constraint-aware" is a video model's clip caps and character counts, a different thing); `-f physics`: none. `projreg search` for constraint, physics, collision: no hits. Read directly: `an.ir.validate` (the registry and the checks listed in 1.3), `an.stage.timeline` (`screen_position`, `node_box`), `an.timing.timeline` (`evaluate_timeline`), `an.frame_clock`, `an.stage.environments`, `an.stage.rig`, `an.motion.stage_poses`, `cutan.verify.body` and `cutan.body_attachment` (from `origin/main`, the merged PR 101), `cutan.verify.style`, `cutan.styles/*.yaml`, `cutan.impacts`, `cutan.compile.gaze`, ADR 0007 in the scene-space worktree.
- **Verdict on new code.** Nothing was written in this session; the catalogue is the deliverable. Every lint in section 3 is a composition of existing primitives plus one declaration; none needs a new combinator. If a 2D constraint solver is built (`puppet-research`), the residuals of A1, A2, A4, A5, B3 and B4 are its constraint functions and should be defined once there.

## REFERENCES

1. Riochet R, Castro MY, Bernard M, Lerer A, Fergus R, Izard V, Dupoux E. IntPhys 2019: A benchmark for visual intuitive physics understanding. arXiv:1803.07616. [arxiv.org/abs/1803.07616](https://ar5iv.labs.arxiv.org/html/1803.07616)
2. Bordes F, et al. IntPhys 2: Benchmarking intuitive physics understanding in complex synthetic environments. Meta FAIR, 2025. arXiv:2506.09849. [arxiv.org/abs/2506.09849](https://arxiv.org/abs/2506.09849v1)
3. Macklin M, Müller M, Chentanez N. XPBD: position-based simulation of compliant constrained dynamics. Proc. Motion in Games (MIG '16). ACM; 2016. p. 49–54. [doi:10.1145/2994258.2994272](https://doi.org/10.1145/2994258.2994272)
4. Towards generalized position-based dynamics. arXiv:2511.23131 (2025), on the linear-compliance limit of PBD constraints. [arxiv.org/html/2511.23131v1](https://arxiv.org/html/2511.23131v1)
5. Gleicher M. Comparing constraint-based motion editing methods. Graphical Models. 2001;63(2):107–134. [doi:10.1006/gmod.2001.0549](https://graphics.cs.wisc.edu/Papers/2001/Gle01/); full text [compare-journal.pdf](https://research.cs.wisc.edu/graphics/Papers/Gleicher/Mocap/compare-journal.pdf)
6. Witkin A, Kass M. Spacetime constraints. Computer Graphics (SIGGRAPH '88). 1988;22(4):159–168. [ri.cmu.edu](https://www.ri.cmu.edu/publications/spacetime-constraints); PDF [alecjacobson.com](https://alecjacobson.com/seminar/witkin-and-kass-1988.pdf)
7. Esoteric Software. Spine user guide: Constraints; Path constraints; Physics constraints. [spine-constraints](https://fr.esotericsoftware.com/spine-constraints), [spine-path-constraints](https://eu.esotericsoftware.com/spine-path-constraints), [spine-physics-constraints](https://esotericsoftware.com/spine-physics-constraints)
8. Lost Marble. Moho manual: Tutorial 3.2 Bone constraints (angle limits); Tutorial 3.3 Bone dynamics; Moho tips on IK locking. [tut03/02](https://www.lostmarble.com/moho/manual/tut03/02/), [tut03/03](https://lostmarble.com/moho/manual/tut03/03/index.html), [monash.edu mohotips](https://users.monash.edu.au/~myless/catnap/mohotips/moho4/bones.html)
9. Toon Boom. Harmony 22 Premium reference: Two-Points Constraint node; Three-Points Constraint node; Constraint Switch node. [two-point-constraint-node](https://docs.toonboom.com/help/harmony-22/premium/reference/node/constraint/two-point-constraint-node.html), [three-point-constraint-node](https://docs.toonboom.com/help/harmony-20/premium/reference/node/constraint/three-point-constraint-node.html), [constraint-switch-node](https://docs.toonboom.com/help/harmony-24/premium/reference/node/constraint/constraint-switch-node.html)
10. Yuan Y, Song J, Iqbal U, Vahdat A, Kautz J. PhysDiff: Physics-guided human motion diffusion model. ICCV 2023 (appendix: penetration, floating and skating metrics). [arxiv.org/abs/2212.02500](https://arxiv.org/pdf/2212.02500)
11. Baraff D. Fast contact force computation for nonpenetrating rigid bodies. Proc. SIGGRAPH '94. ACM; 1994. p. 23–34. [ri.cmu.edu](https://ri.cmu.edu/?p=16017); PDF [cs277.stanford.edu](https://cs277.stanford.edu/resources/papers/Baraff1994.pdf)
12. Blender Foundation. Blender manual: Constraints (Transform: Limit Location, Maintain Volume; Relationship: Child Of, Floor, Follow Path). [docs.blender.org 3.4](https://docs.blender.org/manual/en/3.4/animation/constraints/index.html)
13. Kovar L, Schreiner J, Gleicher M. Footskate cleanup for motion capture editing. Proc. ACM SIGGRAPH Symposium on Computer Animation; 2002. [research.cs.wisc.edu](https://research.cs.wisc.edu/graphics/Gallery/kovar.vol/Cleanup); solver library [FootskateSolver](https://research.cs.wisc.edu/graphics/Gallery/FootskateSolver)
14. Lasseter J. Principles of traditional animation applied to 3D computer animation. Computer Graphics (SIGGRAPH '87). 1987;21(4):35–44. [PDF evl.uic.edu](https://www.evl.uic.edu/aej/527/papers/lasseter.pdf); summary [SIGGRAPH HyperGraph](https://education.siggraph.org/static/HyperGraph/animation/character_animation/principles/prin_trad_anim.htm)
15. Igarashi T, Moscovich T, Hughes JF. As-rigid-as-possible shape manipulation. ACM Trans. Graph. (SIGGRAPH 2005). 2005;24(3):1134–1141. [project page](https://www-ui.is.s.u-tokyo.ac.jp/~takeo/research/rigid); demo [Deform2D](https://www.dgp.toronto.edu/~rms/software/Deform2D/index.html)
16. Chenney S, Pingel M, Iverson R, Szymanski M. Simulating cartoon style animation. Proc. NPAR 2002. ACM; 2002. p. 133–138. [doi:10.1145/508530.508553](https://dx.doi.org/10.1145/508530.508553); project page [pages.cs.wisc.edu](https://pages.cs.wisc.edu/~schenney/research/npar/cartoon/index.html)
17. Criminisi A, Reid I, Zisserman A. Single view metrology. Int. J. Computer Vision. 2000;40(2):123–148. [microsoft.com/research](https://www.microsoft.com/en-us/research/publication/single-view-metrology-4/)
18. Thomas F, Johnston O. The Illusion of Life: Disney Animation. Abbeville Press; 1981 (the twelve principles). Summary: [Wikipedia, Twelve basic principles of animation](https://en.wikipedia.org/wiki/Twelve_basic_principles_of_animation); [Follow through and overlapping action](https://en.wikipedia.org/wiki/Follow_through_and_overlapping_action)
19. Balasubramanian S, Melendez-Calderon A, Roby-Brami A, Burdet E. On the analysis of movement smoothness. J. NeuroEngineering and Rehabilitation. 2015;12:112. [doi:10.1186/s12984-015-0090-9](https://pmc.ncbi.nlm.nih.gov/articles/PMC4674971)
20. Melendez-Calderon A, Shirota C, Balasubramanian S. Estimating movement smoothness from inertial measurement units. Front. Bioeng. Biotechnol. 2021;8:558771. [frontiersin.org](https://www.frontiersin.org/journals/bioengineering-and-biotechnology/articles/10.3389/fbioe.2020.558771/full)
21. Flash T, Hogan N. The coordination of arm movements: an experimentally confirmed mathematical model. J. Neuroscience. 1985;5(7):1688–1703. Summary and derivation: [Duarte, The minimum jerk hypothesis](https://nbviewer.jupyter.org/github/demotu/BMC/blob/master/notebooks/MinimumJerkHypothesis.ipynb)
22. O'Donnell M. O'Donnell's laws of cartoon motion. Esquire, June 1980 (attribution per Wikipedia; a later list circulates with the author given as unknown). [Wikipedia, Cartoon physics](https://en.wikipedia.org/wiki/Cartoon_physics)
23. Netflix Backlot. Continuity error (definition and the Pulp Fiction example). [backlothelp.netflix.com](https://backlothelp.netflix.com/hc/en-us/articles/115000495911-Continuity-Error)
24. ITU-R. Recommendation BT.1359: Relative timing of sound and vision for broadcasting (detectability about +45 ms / −125 ms, acceptability about +90 ms / −185 ms; positive = sound ahead). [itu.int PDF](https://itu.int/dms_pubrec/itu-r/rec/bt/R-REC-BT.1359-0-199802-S!!PDF-E.pdf)
25. NTIA/ITS. Audio-video synchronization (sign convention note: positive = audio lags video). [its.ntia.gov 11-474](https://its.ntia.gov/publications/download/11-474.pdf); TV Technology, Managing lip sync (the ATSC +15/−45 ms limit). [tvtechnology.com](https://www.tvtechnology.com/opinions/managing-lip-sync-265013)
26. ScreenSkills. National Occupational Standard SKSC32: Monitor script coverage, continuity and technical camera details during shooting. [ukstandards.org.uk](https://www.ukstandards.org.uk/en/nos-finder/SKSC32/monitor-script-coverage%2C-continuity-and-technical-camera-details-during-shooting); The Wire, How script supervisors keep film continuity in check. [livewire.thewire.in](https://livewire.thewire.in/livewire/script-supervisors-film-continuity-coffee-cups/)
27. FilmDaft. What is the 180-degree rule in film? [filmdaft.com](https://filmdaft.com/understanding-the-180-degree-rule-in-media/)
28. Epidemic Sound. What is continuity editing? 12 techniques (180-degree rule, 30-degree rule, eyeline match, jump cut, match on action). [epidemicsound.com](https://www.epidemicsound.com/blog/what-is-continuity-editing/)
29. Kee E, O'Brien JF, Farid H. Exposing photo manipulation with inconsistent shadows. ACM Trans. Graph. 2013;32(4):28. [PDF farid.berkeley.edu](https://farid.berkeley.edu/downloads/publications/tog13/tog13.pdf); follow-up with shading, 2014: [tog14.pdf](https://farid.berkeley.edu/downloads/publications/tog14.pdf)
30. Kersten D, Mamassian P, Knill DC. Moving cast shadows induce apparent motion in depth. Perception. 1997;26(2):171–192. [doi:10.1068/p260171](https://journals.sagepub.com/doi/10.1068/p260171); demos [kerstenlab.psych.umn.edu](https://kerstenlab.psych.umn.edu/demos/shadows)
31. Esoteric Software. Spine 4.2: the physics revolution (release post). [esotericsoftware.com/blog](https://uk.esotericsoftware.com/blog)
32. Rive. Constraints (IK, distance, transform, rotation, scale, follow path): runtime source `follow_path_constraint.cpp`, rive-cpp. [skia.googlesource.com mirror](https://skia.googlesource.com/external/github.com/rive-app/rive-cpp/+/bcf11938d31f13a99a2d1515912ed0b22ec20527/src/constraints/follow_path_constraint.cpp); lesson index [Rive 101](https://backup.hollywoodcamerawork.com/rive-101-6-8-rotation-constraint.html)

Internal evidence (not public): the plot-car ledger rounds 1 and 2; cutan PR 101 and its report; ADR 0007 (`an`, branch `scene-space`); `cutan/styles/oversimplified.yaml` and the style lint's measured targets; `an.ir.validate` checks listed in section 1.3.
