# Puppeteering for structured animation: traditions, tools, mechanics, a measured solver comparison, and the design for `an.kinematics`

*2026-10-21 · session `puppet-research` · for the epic [reeleehq/an#497](https://github.com/reeleehq/an/issues/497) · companion files (the prototype and its measurements): `puppeteering_2026-10/{puppet_solver.py,measure.py,compare.py,measurements.json,comparison.json}` beside this file. Every number marked **measured** was produced by those scripts on this machine (pure Python, CPython 3.12, one core); everything else is **claimed** by the cited source.*

## 0. Summary

**What a puppet is, in every tradition and every tool, is the same four things:** rigid pieces (bodies), explicit joins between them (joints, with a bend range), a small number of points the puppeteer actually holds (controls: rods push and pull a point exactly, strings pull a point but cannot push), and a field that settles whatever is not held (gravity, or its deliberate absence). Marionettes make gravity the main actor and hold five to ten points [1,2,3]; rod and shadow puppets hold three points and let the rest hang or trail [4,5,7,8]; bunraku splits the holding among three people by body region [9,10]; Reiniger and Norstein build the same thing out of cardboard, lead and wire and move it a frame at a time [15,16,17]; Harmony, Moho, Spine, Rive, Live2D and Character Animator rebuild it as bones, pivots, IK targets, nails, constraints and physics tags [23–36]. The owner's instruction (frames cannot violate the joins unless we unjoin; sequences of positions for some elements, the rest resolved by the joins, gravity settling among options) is exactly this model, and it is also exactly what the position-based family of solvers computes [47,48,49,50].

**The measured method choice.** For the chains a cut-out puppet has (two or three links, a target, a bend range), four methods were run on the same 48-frame reach task. All four are bitwise deterministic across runs. The analytic two-bone solve is exact (3e-14 px) and the cheapest (7 µs) but has no notion of a limit: it picks a bend side, and the wrong side violates the elbow range by 113 degrees. FABRIK converges in 3 iterations at 20 µs but has no limits either, and its tail is long (one 3-link case out of 200 hit a 500-iteration cap at 1e-3 px). CCD with per-joint clamps respects the limits exactly at 11 iterations and 204 µs. A position-based solve (particles at the joints, sticks for the parts, the target as a goal, a hinge limit, warm-started from the previous frame) respects the limits, reaches the target to 9e-7 px in 6 rounds at 467 µs, and is the only one of the four that also does strings, rods, gravity and unjoining in the same loop. On soft constraints, XPBD's claim [49] reproduced exactly: the extension of an elastic rod was identical (0.196 px) at 1, 2, 8 and 32 iterations, where the plain-PBD stiffness varied by 1.09 px over the same range. A gravity puppet costs 1.4 ms per frame in pure Python for 11 joints, 10 parts, 5 strings and 4 limits (240 frames, bitwise identical on rerun). **Recommendation: a hybrid in one module.** Position-based projection (XPBD form, so soft drivers have an iteration-independent stiffness) with hinge-limit projection is the general solver; the analytic two-bone solve is used as the *initial guess* for a two-link chain with one goal (it makes the common case converge in one round and makes the bend side an explicit, lintable choice); FABRIK and CCD are not needed as separate code paths. Determinism comes from fixed order, fixed counts, fixed substeps and no data-dependent branching on time, and is held by a bitwise test (§4.5).

**The design (§5)** maps onto the epic's nouns: a `Body` is a rig part or any node; a `Joint` is the child bone's position between a part and its parent (the artist's pivots, read at last), or a declared pin, hinge, weld, rod or string; a `Driver` is any authored tween on a body or on a control point, plus gravity; the `solve` pass evaluates the authored timeline at every frame (as `camera_follow_keys` already does), solves the bodies that have joints, and emits per-frame keys honouring `step_hz`; everything else in the engine is unchanged, and a scene without joints compiles byte-for-byte as today. Two solve modes: `pose` (kinematic goals, no gravity, stateless per frame apart from the warm start) and `dynamic` (gravity, strings, inertia; history-dependent, baked from frame 0 at a fixed substep). The one rule every tradition enforces and every tool documents: a target beyond reach is refused or softened, never solved (measured: a hard pin beyond reach leaves a permanent 13 px conflict).

## 1. Puppetry traditions: what each one holds, joins and lets hang

| Tradition | Bodies and joints | What the puppeteer holds (controls) | Gravity's role | What it teaches the model | Status |
|---|---|---|---|---|---|
| **Marionette** (European string puppet) | a jointed wooden or cloth figure; head, torso, upper/lower arms, hands, thighs, shins, feet | about ten strings from a control (horizontal "airplane" or vertical Czech style); the shoulder (or head) strings carry the weight and are mostly kept still; hand strings on the same bar as wrists and elbows; knee strings on a separate rocker that tilts to walk [1] | the whole figure hangs; motion is "a complex coupled pendulum system" governed by "gravity, string tension, and articulation constraints" [2,3] | a string is a *unilateral* distance constraint from a moving anchor (taut pulls, slack does nothing); the support strings are near-static, the acting strings move; weight distribution (lead in feet and hands) is part of the rig | claimed |
| **Rod puppet / wayang golek** | carved head on a central rod through a torso, cloth body, jointed arms | one central rod (head and body), one rod to each hand [5,6] | arms hang when their rods rest | a rod is a *bilateral* position target: it pushes and pulls a point exactly | claimed |
| **Javanese wayang kulit** | flat buffalo-hide figures, "movable joints", arms in two pieces at shoulder and elbow [4,5] | the central `cempurit` (two parts: a handle and a clamp that follows the figure's waist, neck and ears) and one rod per hand; the manipulation styles `mecut`, `membat`, `nggebug` (whip-like, springy, stiff) are named [6] | the flat figure is held against a screen; hanging arms trail the body | a *planar* puppet: all joints are hinges in one plane, no depth; the holding style is a per-driver stiffness; a figure's rest is "leaning on the rod" | claimed |
| **Chinese shadow puppets (piying)** | thin, scraped leather; limbs "jointed with fibre at the shoulders, elbows and hips", some at the wrists; figures of several pieces [7,8] | three rods: "a balance rod on the neck and two movement rods on the arms"; rolling the rod between thumb and finger changes a joint's orientation; raising the balance rod lifts the whole figure [7] | legs and lower body hang from the balance point and swing | three held points animate a ten-piece figure; most joints are never touched directly | claimed |
| **Bunraku** | near-life-size figure; head on a neck handle with internal controls, arms and legs hung from a shoulder board by strings; female puppets often have no legs [9] | three puppeteers: `omozukai` (head via a handle reached through the back, and the right arm), `hidarizukai` (left arm via a rod, the `sashigane`), `ashizukai` (legs and feet) [9,10] | the costume hangs; the feet are placed | the *division of control by body region*, each with its own driver; drivers can be independent streams over one jointed body | claimed |
| **Toy theatre** (juvenile drama) | flat printed figures on card, usually unjointed, two or three inches high [11,12] | "tin slides attached to long wires" pushed in from the wings; side wings, backdrop, trapdoor [11] | none: figures slide on a plane | the degenerate case: one body, one translation driver, planes as frames; worth having as a style (nothing bends) | claimed |
| **Stop-motion armature** | machined ball-and-socket, hinge, swivel and universal joints [14] | the animator's hands, one pose per frame | joints are *friction-held*: "enough tension so that everything stays where you move it", set with a wrench, balanced by ankle tension [13] | the pose mode: a held joint keeps its value until moved; nothing falls between frames unless the animator lets it | claimed |

Three cross-tradition rules fall out and become requirements in §5: (a) *controls are few and joints are many* (three rods for ten joints; ten strings for twenty), so the authoring surface should let a writer drive a handful of points and never type a joint angle; (b) *rods and strings are different constraints*, bilateral position targets versus unilateral maximum distances, and a solver that offers only one of them cannot make a marionette; (c) *gravity is a style, not a law*: Reiniger's silhouettes hang and swing [15], Gilliam's cut-outs float and snap [18], South Park's paper never falls [20,21], a shadow puppet's free leg trails. Whether, and how hard, the free degrees of freedom settle is a per-style knob with "none" as a legitimate value.

## 2. Puppeteering-like animation: hand-made and digital

### 2.1 The hand-made lineage

**Reiniger.** Figures sketched, then cut from "medium-strong cardboard", some parts "cut from thinly rolled lead to provide extra strength", "all connected using small hinges constructed from fuse wire"; "characters requiring a lot of movement needed more fully articulated parts, and versions were made in different sizes for close-up or distant framing" [15]. Backlit on the glass of her `tricktisch`, a stack of glass planes under an overhead camera, "which makes the wire hinges disappear" [16]. Two design facts for us: the joint is a physical hinge at an explicit point (an#497's `Joint`, and the artist's pivot the current rig discards), and the *same character exists at several sizes for several framings*, which is what the body-continuity work (cutan#101) now enforces by measurement [63].

**Norstein.** Cut-outs on "a series of glass planes about a meter deep (one every 25–30 cm)" that "can move horizontally as well as toward and away from the camera" [17]: nested frames of reference realised in glass. His figures are famously many-pieced, but no source reached here documents the wolf's joint count; the claim is left out.

**Gilliam.** The 1974 do-it-yourself demonstration: photographs and engravings cut up, "a glass panel laid over the cutouts", pieces moved under the rostrum camera a frame at a time [18]; cut-out joints are generically "a rivet or pin, which act as mechanical linkage producing fixed motion" [19]. Gilliam's style is the *weightless* one: a joint turns because a hand turned it, nothing hangs.

**South Park.** The pilot was "hand animated by a very small team" from construction paper [20]; from the second episode the show moved to computers (PowerAnimator, then Maya) while keeping the paper look, with "characters built as layered pieces with a small gap between parts, as would occur in real cut-out animation" [21,22]. The gap between parts is a draw-order and offset convention: pieces overlap at their joints and the top piece hides the hinge. That is already the stage's `paint_order`; it becomes a constraint (occlusion at a joint) in the constraints catalogue.

### 2.2 What the 2D rigging tools expose (and the words they use)

| Tool | Joint and chain model | Reaching a target | Limits and holds | Physics | Statement about determinism | Status |
|---|---|---|---|---|---|---|
| **Toon Boom Harmony** | the peg hierarchy *is* the chain: "Harmony uses the rigging hierarchy already created in the Timeline view"; "IK only works on a hierarchy where the pivots are properly set" [23] | the IK tool: pull a hand or foot, the connected parts follow; chain modes Simple, Direct Chain, All Chain [24] | **IK Nails** "temporarily pin a part in translation or rotation"; **Edit Min/Max Angle** on elbows, knees, ankles; **Stiffness** per part; **Enable Translation If Top of Hierarchy**; **Exclude from IK**; **IK Keyframe** sets where a constraint starts [24] | none in IK (bone and curve deformers are separate) | keyframes written onto pegs; replayable | claimed |
| **Moho** | bones with parents; **Smart Bones** (bone angle drives other properties); target bones since v10 | `M_Skeleton:IKAngleSolver(boneID, target, iterMultiplier, allowTwoBoneShortcut, allowBoneStretching)`: an iterative solver with an explicit two-bone shortcut and optional stretch [25] | bone angle constraints | bone dynamics (secondary motion) | iterative, iteration multiplier exposed | claimed |
| **Spine** | bones in a tree; constraints evaluated in a user-ordered list | **IK constraint**: one or two bones, "constraining three or more bones is not supported"; `mix` blends FK and IK (and warns the shortest-path interpolation can flip the bend); `softness` slows the bones near full extension ("with 0 softness, IK bones may move very quickly just before the target goes out of range"); `stretch` scales the bones when the target is "greater than the constrained bones' lengths"; `compress` for one bone; `bend direction` (positive) keyable [26] | transform constraints copy a target's rotation/translation/scale/shear with mixes [28]; path constraints move bones along a path [29] | **physics constraints** (4.2): inertia, strength, damping, mass, wind, gravity, limit, mix, `FPS` ("30–60 is usually a good range"); "intended mostly for runtime use" [27] | the editor has a `Deterministic` mode that "applies physics from frame 0 on every edit, so each frame shows a consistent pose", at a CPU cost; otherwise scrubbing "fast-forwards from frame 0" [27] | claimed |
| **Rive** | bone chains; constraints are objects on a target | **IK constraint** with `Bone Count` ("how far up the bone chain the IK constraint should reach") and `Strength` to blend FK and IK; "if a bone has two IK constraints and both have a Strength of 100%, the lower constraint overrides the one above it" [32] | translation, scale, rotation, distance and transform constraints "set limits on these properties" or "copy properties from one object to another" [33] | none built in (state machines drive) | runtime solves per frame from the current state | claimed |
| **Live2D Cubism** | not bones: deformers and parameters | no IK; parameters are driven | parameter ranges | **physics** as pendulum groups: input parameters are "the part that suspends the thread", outputs written back to parameters, multi-stage pendulums with numbered stages; `Calculate FPS` default 60 and "changing the Calculate FPS setting will change the output result" [30,31] | explicit: the result depends on the calculation rate | claimed |
| **Adobe Character Animator** | layer groups with an **origin handle**; **attach styles** `Weld` (default), `Hinge`, `Free`; "independent groups with Dangle handles that use Free can fall when the puppet first appears" [34] | **Limb IK**: handles at shoulder, elbow, wrist (hip, knee, heel, toe); `Bend Strength`, `Auto Arm Bend`, `Elbow Flip Threshold`, `Elbow Strength` (at 0 "Limb IK does nothing for the elbow") [36] | fixed and draggable handle tags (secondary sources) | **Dangle** handles ("like a metal ball that makes parts bounce, sway and slide", `Stiffness`), `Dynamic` and `Collide` tags "obey gravity and bump into one another", wind, gravity, bounciness; "handles on the puppet act as particles that get dynamically simulated" [35] | live performance capture; physics is simulated, not keyed | claimed |
| **After Effects puppet tools** | a triangle mesh under the artwork: "the area within an outline is automatically divided into a mesh of triangles when you place the first pin" | position pins (and, in the Advanced engine, rotation and scale pins) | **starch pins** "stiffen parts of the image so they are distorted less"; "use as few pins as possible" [37] | none | deterministic deformation from the pins | claimed |

What converges across the table: **a chain is the parenting hierarchy itself** (Harmony, Spine, Rive), never a second structure; **IK is one or two bones deep** in production tools (Spine refuses three; Character Animator's limb has exactly three handles; Moho ships a two-bone shortcut); **a nail or a fixed handle is the pin** ("pin some elements, solve the rest" is a first-class tool in Harmony and After Effects); **limits are per joint and edited at the joint** (Harmony's Edit Min/Max Angle); **a soft mix between FK and IK is a trap** (Spine documents the flip; Character Animator ships an elbow-flip threshold), so the bend side should be a discrete, authored choice, not an interpolated one; **physics is time-stepped at a declared rate** and the two tools that care about repeatability (Spine, Live2D) say so explicitly and pay for it by re-simulating from frame 0. Every one of these is adopted in §5.

### 2.3 Digital puppetry, performance capture and the research line

- **Waldo C. Graphic (1988)**: a digital puppet driven in real time by an eight-degree-of-freedom mechanical arm, composited live with physical puppets, re-rendered at full resolution afterwards; the Henson Digital Performance Studio grew out of it [38,66]. Sturman's 1998 survey names the field "computer puppetry" and covers the TV and film history [39].
- **Shin, Lee, Shin and Gleicher (2001)**: computer puppetry as *retargeting under importance*: a Kalman filter on the capture, "a dynamic importance measure for end-effectors" by proximity to the environment, and a real-time IK solver, used in broadcast [40]. The idea we keep: *which point matters now* (the hand near the wheel, the foot on the ground) is a per-frame weight on a goal, not a fixed rig property.
- **Barnes et al., Video Puppetry (2008)**: paper cut-outs tracked by an overhead camera at about 30 fps and redrawn on a new background with the hands removed; users preferred it to a mouse and to traditional puppetry for simple stories [41]. A cut-out puppet animated by *moving a few pieces* and re-rendering is the owner's "AI translates instructions into parametric commands" with a human in the loop.
- **Igarashi, Moscovich and Hughes (2005)** and **Meta's Animated Drawings (2023)**: pin a few vertices, solve the rest as-rigid-as-possible [42]; a children's drawing becomes an animatable figure by detecting joints and deforming the mesh with ARAP under retargeted motion capture [43]. That is the *deformable* version of "pin some, solve the rest"; for rigid cut-outs the same statement is a rigid-body constraint solve, which is why §5 keeps bodies rigid and leaves ARAP for a later soft-part seam.
- **Zimmermann et al., PuppetMaster (2019)**: a marionette simulated as coupled pendulums under gravity, string tension and joint constraints, with a trajectory planner producing the puppeteer's (a robot's) actions for a target motion [3]. The inverse problem of ours (we have the controls and want the pose; they had the pose and wanted the controls) and a confirmation that strings-plus-gravity is a well-posed dynamical model.
- **Witkin and Kass, Spacetime constraints (1988)**: the animator states goals and constraints over a whole interval, physics supplies the equations, optimisation finds a motion that is both valid and expressive (anticipation and follow-through emerge) [53]. Far heavier than we need per frame, but it is the principled version of "sequences of positions for some elements, the rest resolved": the goals are sparse in time, the solve fills in between. §5's `dynamic` mode is the cheap local approximation (no look-ahead); a spacetime solve is the known upgrade if a style needs anticipation that physics alone does not give.
- **Shadow play in software**: a SIGGRAPH 2003 sketch simulated Chinese shadow play visually [65]; a 2014 system drove a rendered figure from "three rods" held in front of a Kinect [64]. Three held points, again.
- **Language models writing animation programs**: Keyframer (Apple, 2024) has an LLM generate animation code for an SVG from a prompt and finds that users iterate in a "decomposed" style, refining goals from each output [58]; MoVer (Stanford, 2025) adds a verification DSL so the LLM also writes a checker, raising correct animations from 58.8 % to 93.6 % over up to 50 correction rounds [59]. The lesson for us is structural: the model should emit *drivers over a constrained puppet* (few, checkable parameters), not raw channel values, and the lints of P2/P5 are the MoVer-style verifier.

## 3. Mechanics: the solver families and what each buys

### 3.1 Bodies, joints and the constraint graph

A 2D rigid body has three degrees of freedom (x, y, rotation). A pin (hinge) joint removes two; a weld removes three; a slide (groove) removes one translational; a rod (fixed distance between two points) removes one; a string (distance at most L) removes one *only while taut*; a hinge limit removes nothing until reached. Chipmunk's vocabulary is the cleanest small catalogue: `PinJoint` (rigid bar), `PivotJoint` (shared point), `SlideJoint` (min and max distance: "inside the range it does nothing, while outside it behaves like a rope or a spacer"), `GrooveJoint`, `DampedSpring`, `RotaryLimitJoint`, `RatchetJoint`, `GearJoint`, `SimpleMotor` [54]. A tree of bodies joined by pins is a kinematic chain; `an.stage.rig` already refuses cycles ("a rig is a tree, forward kinematics only"), which is right for the *rig* and wrong for the *scene*: two hands on one steering wheel, or a character on a swing, close a loop, and a position-based solver handles loops without special code because it never builds a chain, it projects constraints [47,48].

### 3.2 Inverse kinematics on a chain

- **Analytic two-bone**: the law of cosines gives both angles in closed form; the bend side is a sign; unreachable when the distance exceeds l1 + l2 or is below |l1 − l2|. Exact, branch-free, and what every tool's limb IK is underneath [25,26,36]. Measured: 3e-14 px worst error over 1000 random reachable targets, 7 µs per solve.
- **CCD** (Wang and Chen 1991 [46]): from the tip joint to the root, rotate each link to point its tip at the target; clamp each relative angle to its limit as you go. Simple, limits are natural, converges linearly, can look "whippy" on long chains. Measured: 11 iterations median, limits respected exactly, 204 µs per frame on the two-link task.
- **FABRIK** (Aristidou and Lasenby 2011 [44]): "finds each joint position via locating a point on a line", a backward then a forward pass; "converges in few iterations with low computational cost"; constraints are described in the paper but are a separate, more involved procedure. Measured: median 3–6 iterations across 3-, 5-, 8- and 16-link chains at 0.1 px and 1e-3 px tolerances; the tail is long (max 86–409 iterations; one 3-link case hit the 500 cap at 1e-3 px, a near-singular target); 20 µs per frame on the two-link task; no limits in this implementation.
- **Jacobian methods** (transpose, pseudoinverse, damped least squares; Buss's survey [45]): general, handle multiple goals and orientation, need a small linear solve per iteration and damping near singularities. Not measured; for two- and three-link planar chains they buy nothing over the above, and they are the fallback if a long multi-goal chain (a tentacle, a rope of text) ever needs it.

### 3.3 Position-based solvers: joints, limits, strings, rods and gravity in one loop

Jakobsen's 2001 formulation [47]: particles store current and previous positions ("a velocity-less representation", "quite stable since the velocity is implicitly given"); a *stick* holds two particles at a distance by moving them directly; constraints are satisfied "by consecutively satisfying various local constraints and then repeating" (relaxation), and the loop "can be stopped at any time"; "let two rigid bodies share a particle, and they will be connected by a pin joint"; angular limits were done with conditional sticks; "in this way, one can implement inverse kinematics" by forcing a particle to a target inside the relaxation loop. Müller et al. (2007) generalised this to arbitrary constraints and named it position-based dynamics [48]. Its known flaw: "constraints become arbitrarily stiff as the iteration count increases, or as the time step decreases" [49]; XPBD (Macklin, Müller, Chentanez 2016) fixes it with a compliance α per constraint and an accumulated Lagrange multiplier, so stiffness is "time step and iteration count independent" [49]. Müller et al. (2020) extend XPBD to full rigid bodies with joints and angle limits [50], and a 2023 survey collects the joint and limit formulations [68]. Catto's 2024 Solver2D compared eight Gauss–Seidel solvers on stress tests and chose a sub-stepped soft-constraint solver ("Soft Step") for Box2D v3, noting that "smaller time steps are more effective than more iterations" and that his XPBD implementation struggled with friction [51]; soft constraints there are tuned by a natural frequency and damping ratio [52]. For a puppet (no friction, no stacking, a dozen bodies) the differences between XPBD and Soft Step do not matter; what matters is XPBD's iteration-independent softness for *drivers* (a string that gives, a lazy rod), measured in §4.3.

### 3.4 Strings and rods: forces or position targets?

The puppetry answer is both, by kind. A **rod** is a hard position (and sometimes orientation) target on one point: in solver terms a pin with infinite mass that moves on an authored path, or equivalently an authored tween on a control point. A **string** is a unilateral distance constraint from a moving anchor: taut it is a hard inequality, slack it is nothing; a *soft* string (the puppeteer's wrist giving) is the same constraint with compliance. Modelling strings as spring *forces* instead (Character Animator's dangle [35], Spine's physics [27]) gives secondary motion but makes "the hand is exactly here" impossible to state; modelling rods as forces makes exact placement a tuning problem. So: targets and inequalities, with compliance as the one softness knob, and forces only for gravity and wind. Gravity itself is a per-substep displacement g·h² in position-based form, which is also how "settle among options" is realised: the free degrees of freedom fall until the constraints stop them.

### 3.5 Pin some elements, solve the rest; unjoin and rejoin

"Pin" is Harmony's nail [24], After Effects' pin [37], Spine's target at mix 100 [26], Jakobsen's forced particle [47]. In the solve it is a body or point with inverse mass zero whose position is read from the authored timeline each frame; everything else has inverse mass one and is projected. **Unjoining** is removing a constraint from the active set at time t; **rejoining** is adding it, after which the first projection pulls the pieces together over a few iterations (a visible snap unless the author also drives them close, which is what a human puppeteer does). Character Animator's attach styles `Weld`/`Hinge`/`Free` are exactly a joint's three states [34]; Spine animates `mix` to 0 and back [26]. The constraint set is therefore a piecewise-constant function of time, part of the authored scene, and part of the cache key.

### 3.6 Determinism and frame-exact renders

Two separate requirements, often conflated. **Repeatability** (the same inputs give the same frames on the same machine) needs a fixed step, a fixed iteration count, a fixed constraint order and no data-dependent early exit that depends on timing: Fiedler's rule that the renderer should produce time and "the simulation consumes it in discrete dt sized steps", with leftover time carried in an accumulator and never thrown away [55]; Spine and Live2D both state that their result depends on the simulation rate [27,30]. **Portability** (the same frames on another machine) is weaker than people assume: CPython's `math.sin` "just wraps C's sin function, so it inherits the behaviour of the platform libm" and whether it is correctly rounded "is entirely platform dependent" [56]; transcendental functions "differ in the last ulp between macOS, glibc, MSVC and wasm" [57]. The consequences for us: (a) the baked keys are the artefact, computed once at compile and stored in the document, so a render never re-simulates; (b) the shot-cache key already carries an environment digest, so a libm difference re-renders rather than silently differing; (c) values are quantised before they are written (1e-6 px, 1e-7 rad), which makes the stored document identical across machines whenever the last-ulp noise is below the quantum, and makes the bitwise test in §4.5 meaningful on the document rather than on floats in memory. Measured: every solver here is bitwise identical across runs (`repr` of every float equal) with no effort beyond fixed order and counts.

## 4. The measured comparison

All runs: `puppeteering_2026-10/compare.py` and `puppeteering_2026-10/measure.py`, pure Python 3.12 on this server, no numpy. Times are indicative of algorithmic cost, not of the numpy implementation to be built; the ratios are what matter.

### 4.1 Task A: a two-link arm (42.4 + 30 px) reaching 48 targets on a circle of radius 55 px, elbow range [−150°, −30°]

| Method | Worst tip error (px) | Worst limit violation (°) | Worst frame-to-frame link change (°) | Iterations (median / max) | µs per frame | Bitwise identical rerun |
|---|---|---|---|---|---|---|
| Analytic two-bone, bend = +1 | 2.9e-14 | 0.0 | 7.50 | closed form | 7 | yes |
| Analytic two-bone, bend = −1 | 2.9e-14 | 112.7 | 7.50 | closed form | 7 | yes |
| CCD with per-joint clamps | 6.9e-4 | 0.0 | 7.50 | 11 / 12 | 204 | yes |
| FABRIK (no limits) | 5.4e-5 | 0.0 (by geometry, unenforced) | 7.50 | 3 / 4 | 20 | yes |
| PBD: sticks + goal + hinge limit, warm start | 9.0e-7 | 0.0 | 7.50 | 6 / 7 rounds of 8 | 467 | yes |

The target moves 7.5° per frame and every method follows it with 7.50° of link change: no popping in any of them on a reachable path. The analytic solve is a *fact about the geometry*, the bend side an *authored choice*; the 112.7° row is the wrong choice, not an error, and is why the design makes the bend side explicit and lintable.

### 4.2 Task A′: the same arm, a target 85 px away (reach 72.4 px)

| Method | What happens | Residual |
|---|---|---|
| Analytic | returns `None` | refused |
| CCD with clamps | straightens toward the target, stops at the limit | 15.4 px tip error after 100 iterations |
| FABRIK | points the chain at the target in one pass | 13.0 px |
| PBD with a hard pin at both ends | sticks and pins fight forever | 13.0 px of permanent stick error |

**Rule: an unreachable rod is a lint error** ("hand pinned 85 px from a 72 px shoulder; move the grip or lengthen the arm"), and a *goal* (a string with zero length) is how a writer asks for "as close as it can get". Spine's `softness` and `stretch` [26] are the two sanctioned softenings; cutan#97 already specifies refusal [62].

### 4.3 Task C: a weight on an elastic rod, extension at rest versus solver iterations

| Solver | 1 iteration | 2 | 8 | 32 | Spread |
|---|---|---|---|---|---|
| PBD, stiffness 0.2 | 1.089 px | 0.484 | 0.055 | 0.0002 | **1.089 px** |
| XPBD, compliance 2e-4 | 0.196 px | 0.196 | 0.196 | 0.196 | **0.000 px** |

Macklin et al.'s claim [49] reproduced to the digit: with XPBD a soft driver means the same thing whatever the iteration budget, so a style's "lazy string" is a number an author can keep.

### 4.4 Tasks B and D: gravity

| Case | Result |
|---|---|
| 3-, 6-, 12-stick chain hung from a pin, started horizontal, damped to rest | tip within 0.04 % of vertical; 301 / 602 / 1203 steps to rest (25 / 117 / 269 ms); worst stick error 0.02 / 0.12 / 0.33 px; bitwise identical rerun |
| 6-stick chain, pin moving 40 px sideways, re-settled every frame (pose mode with gravity) | 0.40 px worst error against the closed form (every link vertical); 302 steps median per frame; 47 ms per frame |
| 11-joint marionette (10 parts, 5 strings from a bobbing, swaying bar, 4 hinge limits), 240 frames at 24 fps, 4 substeps, 8 iterations (dynamic mode) | 1.42 ms per frame, 0.34 s total; worst constraint error after the last iteration 0.36 px; worst hinge violation 0.01°; bitwise identical rerun |
| the same marionette, hands pinned by rods at reachable points, legs settled under gravity | 575 steps, 275 ms; hands exactly at target; worst stick error 0.16 px; feet below the pelvis |

Two conclusions. "Settle to rest at every frame" is thirty times the cost of "step the dynamics once per frame" and gives a dead pose (no follow-through), so **gravity means `dynamic` mode**, baked sequentially from frame 0 with a warm start; `pose` mode is for kinematic goals without gravity, where it costs six rounds. And Gauss–Seidel's slow propagation down a chain (steps scale with length squared) is the known cost of position-based relaxation [47,51]; sub-stepping, not more iterations, is the cheaper remedy [51].

### 4.5 Determinism, as a test

Every method above was run twice from the same inputs and compared with `repr` on every output float: identical in all cases. The test to ship with P1: solve the marionette for 240 frames twice in one process and once in a fresh interpreter, assert the quantised key arrays are equal byte for byte; include the iteration count, substep count, solver version and constraint order in the digest, so that a change to any of them is a cache miss rather than a silent drift.

### 4.6 The method choice, stated

| Need | Choice | Why (measured) |
|---|---|---|
| a two-link chain reaching a grip (cutan#97) | analytic two-bone as the initial guess, then the general projection with the hinge limit | exact and 7 µs; limits and goal sharing come from the projection; the bend side is explicit |
| longer chains, loops, two hands on one prop | position-based projection (Gauss–Seidel, fixed order) | handles loops and multiple goals without chains; CCD and FABRIK would need separate code paths and still lack strings and gravity |
| strings, soft rods, a lazy puppeteer | XPBD compliance on drivers | iteration-independent stiffness (spread 0.000 px vs 1.089 px) |
| gravity, swing, follow-through | `dynamic` mode: Verlet, 4 substeps, 8 iterations, damping as a style knob, baked from frame 0 | 1.4 ms per frame pure Python; settle-per-frame is 33× dearer and lifeless |
| kinematic goals only | `pose` mode: projection to convergence with warm start, no gravity | 6 rounds; stateless apart from the warm start |
| frame-exactness | emit per-frame keys at the shot's fps (honouring `step_hz`), quantised | the runtime stays a seekable keyframe player |

## 5. Design: `an.kinematics` and the `solve` pass

This follows the lead's decisions (epic #497 [61]): a pure-numpy module in `an` with no IR imports; a compile pass between `face` (500) and `camera_follow` (550) emitting per-frame keys the way `camera_follow_keys` does; channels replace values; `evaluate_timeline` is pure in t; `fit_channel` is available for compaction; no scipy; cutan#97 is the first consumer.

### 5.1 One-command definition of v1

`an render` on a scene where a character with `nesting: bones` and a split arm (upper, fore, hand) has `pin: {point: hand_r, to: wheel/grip_r}` over a shot produces a film in which the hand sits on the grip in every frame, the elbow bends the declared way, and `an validate` refuses the same scene when the grip is out of reach. A scene without a joint, pin or gravity compiles byte-for-byte as today (test: digest equality over the corpus).

### 5.2 Data model (numpy, no IR)

```python
# an/kinematics/__init__.py  (sketch; names are proposals for the lead)
Bodies:   positions (n, 2) float64, angles (n,), inv_mass (n,)  # pivot = the body's joint to its parent (the child bone's position)
Joints:   pin(a, b, anchor_a, anchor_b) | hinge(pin + lo, hi about rest) | weld(pin + fixed relative angle)
          | rod(a, pa, b, pb, length, compliance=0) | string(a, pa, anchor, max_length, compliance=0)
          each with `active: (t0, t1)` spans; a joint to the world has b = WORLD
Drivers:  target(body or point, path: t -> (x, y)[, angle])      # rods and nails; inverse mass 0 while active
          goal(point, path, compliance)                           # a tight string: as close as it can
          gravity(gx, gy) ; damping                               # a style's field
Solve:    solve(bodies, joints, drivers, times, *, mode="pose"|"dynamic", substeps=4, iterations=8, seed) -> keys (frames, n, 3)
```

Internally the solver is particle-based like the prototype: a body's joint points are particles, the body is the set of sticks between them (a one-joint part gets a tip particle at its extent), a pin is a shared particle, a hinge limit is an angle projection at the shared particle, drivers set or pull particles. Body angles are recovered from the particle pairs after the solve. This keeps every constraint a few lines of numpy and makes loops free. `seed` exists only for the one stochastic thing a style may ask for (a tremor), which is drawn once per frame from a counter-based generator, never from global state.

### 5.3 How a rig becomes bodies and joints (`an.stage.rig`, core; props and characters alike)

- Each slot's node is a body; its pivot is its bone's position (already the node origin; the artist's `extract_pivots` coordinates stop being discarded, rig contract §4).
- `Bone.parent` gives a pin joint at the child bone's position between the child body and the parent body. `nesting: bones` is the forward-kinematic reading of the same joint; the solver writes local rotations in that mode and (x, y, rotation) per part in flat mode, so the solve works on today's flat rigs too.
- A hinge range is declared on the bone (`limits: [lo, hi]` degrees *about the rest angle*, the convention the prototype adopted after hand-typed signs measured 88 px of conflict), and defaults to none.
- `metadata.body_attachment` sockets (cutan#101) lower to pins between the prop body and the named bones, without changing their persisted shape. A prop's `grip` points (cutan#97) are the same declaration from the prop's side.

### 5.4 The `solve` compile pass (order 525, between `face` and `camera_follow`)

1. Collect the shot's bodies and the joints active in it; if none, return (byte identity).
2. Assemble the document so far and evaluate it at every frame of the shot's grid (`evaluate_timeline` at k / fps, or the `step_hz` grid when set): the authored `set`/`tween`/`play` values on driven bodies and control points *are* the drivers (no new syntax for a target: a tween on `wheel/grip_r` or on a control node is a path).
3. Run `an.kinematics.solve` over the frames (sequentially, warm-started; `dynamic` mode when any gravity or string is active, `pose` otherwise, overridable per shot).
4. Emit one key per frame per solved channel (`rotation`, and `x`, `y` for roots and flat-mode parts), `easing: "linear"`, exactly as `camera_follow_keys` emits camera keys; optionally compact them with `fit_channel` under a declared tolerance (0.25 px default) when the shot is long.
5. Record `solver_version`, mode, substeps, iterations and the active constraint digest as render knobs (`an/stage/cache_key.py::render_knobs`).

Because the keys replace channel values, a solved channel wins over the authored tween on the same channel for that span, which is the intended semantics of a joint ("frames cannot violate the join"); `an validate` reports the overridden spans as info.

### 5.5 Authoring surface (scene.md), kept to what a writer says to a puppeteer

```yaml
# on an entity (character or prop), in its block or its descriptor
joints:
  - hinge: {part: forearm_r, limits: [-150, -30]}        # about the rest angle; the bone's pivot is the pin
  - pin:   {point: hand_r, to: wheel/grip_r}             # a nail; refused when out of reach
  - string:{point: head, to: bar/head, max: 100, give: 0.0}
style:
  gravity: down 980          # or `gravity: none` (Gilliam, South Park); a style spec default
  damping: 0.02
# actions
- {kind: pull, target: charlie/hand_l, to: [x, y], over: 0.5}   # a goal (a tight string), the common verb
- {kind: unjoin, target: charlie/hand_r, at: 3.0}               # the join stops; rejoin with `join`
- {kind: tween, target: bar, property: x, ...}                   # moving the control bar moves every string
```

Three verbs cover the traditions: `pull` (string: as close as it can), `pin` (rod or nail: exactly here, or refuse), `join`/`unjoin`. Every existing preset keeps working; a preset that names a joint (a `point` on a split arm) becomes a `pull` on the hand.

### 5.6 Seams and surfaces (architecture-first)

| # | Seam | v1 default | Replacement you can point at |
|---|---|---|---|
| 1 | the projection step for a constraint kind | numpy Gauss–Seidel with XPBD compliance | Catto's Soft Step for contacts when P5's contact lint grows a solver term [51] |
| 2 | the chain initial guess | analytic two-bone when a chain is two links with one goal | FABRIK for a longer single chain (prototype in `puppeteering_2026-10/puppet_solver.py`) |
| 3 | key compaction | one linear key per frame | `fit_channel` (scene-space branch) under a tolerance |
| 4 | the gravity field | a constant vector per shot or style | the frame's acceleration from planes-research's `Frame(parent, motion)` (P4) |

NOT seams: substep and iteration counts (constants, in the cache key), the quantum, the particle representation. Surfaces: CLI needs nothing new (`an validate`, `an render`); MCP and skills get the three verbs through the existing action-kind registry; a frontend would need the per-frame keys only, which it already consumes.

### 5.7 Tests to ship with P1 and P2

- doctests on every constraint projection with a hand-checkable number (as in the prototype);
- the bitwise test (§4.5), in-process and cross-process;
- byte identity of the corpus without joints;
- the unreachable-pin refusal, with the distance and the remedy in the message;
- a two-hand loop (both hands pinned to one prop) solving to under 0.5 px without a chain;
- parity: the emitted keys evaluated through `evaluate_timeline` reproduce the solver's poses at every frame.

## 6. Open questions for the lead and the owner

1. **Default mode when gravity is set by a style but a shot only pins hands**: `dynamic` (follow-through, cheaper) or `pose` (dead-still between keys, the stop-motion look)? Recommendation: `dynamic`, with `pose` as the style's "armature" option.
2. **Where the hinge range lives**: on the bone (rig document, shared by every scene) or on the scene's `joints:` (per production)? Recommendation: the bone, overridable in the scene.
3. **Rejoin snap**: when a joint rejoins at a distance, do we lint (the author must drive the pieces together first) or blend over N frames? Recommendation: lint at 2 px, blend below.
4. **ARAP soft parts** (cloth, hair) are out of v1; the seam is a body kind, not a solver change.

## REFERENCES

1. UNIMA. Marionette (string puppet). World Encyclopedia of Puppetry Arts. [https://wepa.unima.org/en/?p=10085](https://wepa.unima.org/en/?p=10085)
2. Northwestern University Robotics. Robotic marionettes. [https://www.robotics.northwestern.edu/research/topics/scalable-algorithms-for-physical-systems/robotic-marionettes.html](https://www.robotics.northwestern.edu/research/topics/scalable-algorithms-for-physical-systems/robotic-marionettes.html)
3. Zimmermann S, Poranne R, Bern JM, Coros S. PuppetMaster: robotic animation of marionettes. ACM Trans Graph. 2019;38(4). [https://history.siggraph.org/?p=100164](https://history.siggraph.org/?p=100164)
4. Museum of International Folk Art. How wayang kulit are made. [https://online.internationalfolkart.org/dancingshadows/making-puppets.html](https://online.internationalfolkart.org/dancingshadows/making-puppets.html)
5. Wikipedia. Wayang kulit. [https://en.wikipedia.org/wiki/Wayang_kulit](https://en.wikipedia.org/wiki/Wayang_kulit)
6. Indonesian vocational textbook (BSE) on wayang handling: cempurit and gapit. [https://epaper.myedisi.com/bse/54004/index_40.html](https://epaper.myedisi.com/bse/54004/index_40.html)
7. Stanford CCRMA. The manipulation of shadow play puppets. [https://ccrma.stanford.edu/~bt5/shadow/text-puppet_manipulation.html](https://ccrma.stanford.edu/~bt5/shadow/text-puppet_manipulation.html)
8. Museum of Anthropology, UBC. Shadow puppet 3338/8 a-c (three rods; fibre joints). [https://www.rrncommunity.org/items/624067/print](https://www.rrncommunity.org/items/624067/print)
9. Wikipedia. Bunraku. [https://en.wikipedia.org/wiki/Bunraku](https://en.wikipedia.org/wiki/Bunraku)
10. Japan Foundation Performing Arts Network. Kanjuro Kiritake III (interview). [https://performingarts.jpf.go.jp/en/?p=6941](https://performingarts.jpf.go.jp/en/?p=6941)
11. Craftsmanship Magazine. The rise and fall of toy theatre. [https://craftsmanship.net/?p=30851](https://craftsmanship.net/?p=30851)
12. UNIMA. Toy theatre. World Encyclopedia of Puppetry Arts. [https://wepa.unima.org/en/?p=13620](https://wepa.unima.org/en/?p=13620)
13. Storm the Castle. Ball and socket armatures for stop motion. [https://stormthecastle.com/stop-motion-animation/ball-and-socket-armatures.htm](https://stormthecastle.com/stop-motion-animation/ball-and-socket-armatures.htm)
14. Shaw T. Stop-motion armature machining: a construction manual. McFarland. [https://mcfarlandbooks.com/?p=13436](https://mcfarlandbooks.com/?p=13436)
15. BFI. Object of the week: Lotte Reiniger's cut-out figures and backgrounds for Cinderella. [https://www.bfi.org.uk/inside-the-archive/features/object-week-lotte-reiniger-cut-out-figures-backgrounds-cinderella](https://www.bfi.org.uk/inside-the-archive/features/object-week-lotte-reiniger-cut-out-figures-backgrounds-cinderella)
16. Library of Congress, Inside Adams. Lotte Reiniger. 2025. [https://blogs.loc.gov/inside_adams/2025/04/lotte-reiniger/](https://blogs.loc.gov/inside_adams/2025/04/lotte-reiniger/)
17. USC School of Cinematic Arts. Yuri Norstein (the glass-plane technique). [https://cinema.usc.edu/news/article.cfm?id=9838](https://cinema.usc.edu/news/article.cfm?id=9838)
18. Make:. How-to: cut-out animation with Monty Python's Terry Gilliam (1974 BBC demonstration). [https://makezine.com/article/craft/how-to_cut-out_animation_with/](https://makezine.com/article/craft/how-to_cut-out_animation_with/)
19. Wikipedia. Cutout animation. [https://en.wikipedia.org/wiki/Cutout_animation](https://en.wikipedia.org/wiki/Cutout_animation)
20. South Park Studios. FAQ: do you still use construction paper to animate the show? [https://southpark.cc.com/news/712d55/faq-do-you-still-use-construction-paper-to-animate-the-show](https://southpark.cc.com/news/712d55/faq-do-you-still-use-construction-paper-to-animate-the-show)
21. Animation World Network. Using computers to simulate cut-out animation techniques: South Park and Blue's Clues. [https://www.awn.com/animationworld/dig-using-computers-simulate-cut-out-animation-techniques-south-park-and-blues-clues](https://www.awn.com/animationworld/dig-using-computers-simulate-cut-out-animation-techniques-south-park-and-blues-clues)
22. Engadget. Macworld|iWorld's South Park talk. 2012. [https://www.engadget.com/2012-01-30-macworld-iworlds-south-park-talk.html](https://www.engadget.com/2012-01-30-macworld-iworlds-south-park-talk.html)
23. Toon Boom. Harmony 20 Premium: About inverse kinematics. [https://docs.toonboom.com/help/harmony-20/premium/cut-out-animation/about-inverse-kinematic.html](https://docs.toonboom.com/help/harmony-20/premium/cut-out-animation/about-inverse-kinematic.html)
24. Toon Boom. Harmony 20 Premium: Inverse kinematics tool properties. [https://docs.toonboom.com/help/harmony-20/premium/reference/tool-properties/inverse-kinematics-tool-properties.html](https://docs.toonboom.com/help/harmony-20/premium/reference/tool-properties/inverse-kinematics-tool-properties.html)
25. Moho scripting reference. M_Skeleton:IKAngleSolver. [https://mohoscripting.com/methods/m_skeleton-ikanglesolver](https://mohoscripting.com/methods/m_skeleton-ikanglesolver)
26. Esoteric Software. Spine user guide: IK constraints. [https://esotericsoftware.com/spine-ik-constraints](https://esotericsoftware.com/spine-ik-constraints)
27. Esoteric Software. Spine user guide: Physics constraints. [https://esotericsoftware.com/spine-physics-constraints](https://esotericsoftware.com/spine-physics-constraints)
28. Esoteric Software. Spine user guide: Transform constraints. [https://esotericsoftware.com/spine-transform-constraints](https://esotericsoftware.com/spine-transform-constraints)
29. Esoteric Software. Spine user guide: Path constraints. [https://eu.esotericsoftware.com/spine-path-constraints](https://eu.esotericsoftware.com/spine-path-constraints)
30. Live2D. Cubism Editor manual: Physics settings. [https://docs.live2d.com/en/cubism-editor-manual/physics-operation/](https://docs.live2d.com/en/cubism-editor-manual/physics-operation/)
31. Live2D. Cubism SDK manual: Physics. [https://docs.live2d.com/en/cubism-sdk-manual/physics](https://docs.live2d.com/en/cubism-sdk-manual/physics)
32. Rive. IK constraint. [https://rive.app/community/doc/ik-constraint/doclOLGcy3yB](https://rive.app/community/doc/ik-constraint/doclOLGcy3yB)
33. Rive. Constraints overview. [https://rive.app/docs/editor/constraints/constraints-overview](https://rive.app/docs/editor/constraints/constraints-overview)
34. Adobe. Character Animator: Mesh, attachments, and handles. [https://helpx.adobe.com/adobe-character-animator/desktop/rigging/attachment-and-handles.html](https://helpx.adobe.com/adobe-character-animator/desktop/rigging/attachment-and-handles.html)
35. Adobe. Character Animator: Behaviors, physical simulations. [https://helpx.adobe.com/ee/adobe-character-animator/desktop/behaviors/learn-more-about-behaviors/physical-simulations.html](https://helpx.adobe.com/ee/adobe-character-animator/desktop/behaviors/learn-more-about-behaviors/physical-simulations.html)
36. Adobe. Character Animator: Body behaviors (Limb IK). [https://helpx.adobe.com/adobe-character-animator/using/behaviors/body-directly-controlled.html](https://helpx.adobe.com/adobe-character-animator/using/behaviors/body-directly-controlled.html)
37. Adobe. After Effects: Animating with Puppet tools. [https://helpx.adobe.com/si/after-effects/desktop/animate-in-after-effects/animate-with-puppet-tools/animating-puppet-tools.html](https://helpx.adobe.com/si/after-effects/desktop/animate-in-after-effects/animate-with-puppet-tools/animating-puppet-tools.html)
38. Wikipedia. Digital puppetry (Waldo C. Graphic). [https://en.wikipedia.org/wiki/Digital_puppetry](https://en.wikipedia.org/wiki/Digital_puppetry)
39. Sturman DJ. Computer puppetry. IEEE Comput Graph Appl. 1998;18(1):38–45. doi:10.1109/38.637269. [https://www.academia.edu/2469727/Computer_puppetry](https://www.academia.edu/2469727/Computer_puppetry)
40. Shin HJ, Lee J, Shin SY, Gleicher M. Computer puppetry: an importance-based approach. ACM Trans Graph. 2001;20(2):67–94. [https://graphics.cs.wisc.edu/Papers/2001/SLGS01/](https://graphics.cs.wisc.edu/Papers/2001/SLGS01/)
41. Barnes C, Jacobs DE, Sanders J, Goldman DB, Rusinkiewicz S, Finkelstein A, Agrawala M. Video puppetry: a performative interface for cutout animation. ACM Trans Graph (SIGGRAPH Asia). 2008;27(5). [https://pixl.cs.princeton.edu/pubs/Barnes_2008_VPA/index.php](https://pixl.cs.princeton.edu/pubs/Barnes_2008_VPA/index.php)
42. Igarashi T, Moscovich T, Hughes JF. As-rigid-as-possible shape manipulation. ACM Trans Graph. 2005;24(3). [https://www-ui.is.s.u-tokyo.ac.jp/~takeo/research/rigid](https://www-ui.is.s.u-tokyo.ac.jp/~takeo/research/rigid)
43. Smith HJ, Zheng Q, Li Y, Jain S, Hodgins JK. A method for animating children's drawings of the human figure. arXiv:2303.12741. 2023. [https://arxiv.org/abs/2303.12741](https://arxiv.org/abs/2303.12741)
44. Aristidou A, Lasenby J. FABRIK: a fast, iterative solver for the inverse kinematics problem. Graph Models. 2011;73(5):243–260. doi:10.1016/j.gmod.2011.05.003. [https://www.andreasaristidou.com/FABRIK](https://www.andreasaristidou.com/FABRIK)
45. Buss SR. Introduction to inverse kinematics with Jacobian transpose, pseudoinverse and damped least squares methods. Unpublished survey, 2009 revision. [https://mathweb.ucsd.edu/~sbuss/ResearchWeb/ikmethods/iksurvey.pdf](https://mathweb.ucsd.edu/~sbuss/ResearchWeb/ikmethods/iksurvey.pdf)
46. Wang LCT, Chen CC. A combined optimization method for solving the inverse kinematics problem of mechanical manipulators. IEEE Trans Robot Autom. 1991;7(4):489–499. doi:10.1109/70.86079.
47. Jakobsen T. Advanced character physics. Game Developers Conference 2001; reprint. [https://www.gamedeveloper.com/programming/advanced-character-physics](https://www.gamedeveloper.com/programming/advanced-character-physics)
48. Müller M, Heidelberger B, Hennix M, Ratcliff J. Position based dynamics. J Vis Commun Image Represent. 2007;18(2):109–118. [https://matthias-research.github.io/pages/publications/posBasedDyn.pdf](https://matthias-research.github.io/pages/publications/posBasedDyn.pdf)
49. Macklin M, Müller M, Chentanez N. XPBD: position-based simulation of compliant constrained dynamics. Proc Motion in Games (MIG '16). 2016:49–54. doi:10.1145/2994258.2994272. [https://matthias-research.github.io/pages/publications/XPBD.pdf](https://matthias-research.github.io/pages/publications/XPBD.pdf)
50. Müller M, Macklin M, Chentanez N, Jeschke S, Kim TY. Detailed rigid body simulation with extended position based dynamics. Comput Graph Forum. 2020;39(8). doi:10.1111/cgf.14105. [https://diglib.eg.org/handle/10.1111/cgf14105](https://diglib.eg.org/handle/10.1111/cgf14105)
51. Catto E. Solver2D. box2d.org, 2024. [https://box2d.org/posts/2024/02/solver2d/](https://box2d.org/posts/2024/02/solver2d/)
52. Catto E. Soft constraints. Game Developers Conference 2011. [https://box2d.org/files/ErinCatto_SoftConstraints_GDC2011.pdf](https://box2d.org/files/ErinCatto_SoftConstraints_GDC2011.pdf)
53. Witkin A, Kass M. Spacetime constraints. Comput Graph (SIGGRAPH). 1988;22(4):159–168. [https://www.ri.cmu.edu/publications/spacetime-constraints](https://www.ri.cmu.edu/publications/spacetime-constraints)
54. Pymunk tutorial. Constraints and joints. [https://pymunk-tutorial.readthedocs.io/en/latest/joint/joint.html](https://pymunk-tutorial.readthedocs.io/en/latest/joint/joint.html)
55. Fiedler G. Fix your timestep. Gaffer on Games. [https://gafferongames.com/post/fix_your_timestep/](https://gafferongames.com/post/fix_your_timestep/)
56. Dickinson M. Re: [issue35880] math.sin has no backward error. python docs list, 2019. [https://mail.python.org/pipermail/docs/2019-February/039223.html](https://mail.python.org/pipermail/docs/2019-February/039223.html)
57. alice-det-math documentation (libm last-ulp differences across platforms). [https://docs.rs/alice-det-math](https://docs.rs/alice-det-math)
58. Tseng T, Cheng R, Nichols J. Keyframer: empowering animation design using large language models. arXiv:2402.06071. 2024. [https://arxiv.org/abs/2402.06071](https://arxiv.org/abs/2402.06071)
59. Ma J, Agrawala M. MoVer: motion verification for motion graphics animations. arXiv:2502.13372. 2025. [https://arxiv.org/abs/2502.13372](https://arxiv.org/abs/2502.13372)
60. Thomas F, Johnston O. The illusion of life: Disney animation. Abbeville; 1981. (follow-through and overlapping action)
61. reeleehq/an. Epic: a constraint layer under structured animation. Issue 497. [https://github.com/reeleehq/an/issues/497](https://github.com/reeleehq/an/issues/497)
62. reeleehq/cutan. Rig arms that reach a prop's grip points (two-bone IK). Issue 97. [https://github.com/reeleehq/cutan/issues/97](https://github.com/reeleehq/cutan/issues/97)
63. reeleehq/cutan. Body continuity for generated art. Pull request 101. [https://github.com/reeleehq/cutan/pull/101](https://github.com/reeleehq/cutan/pull/101)
64. Chen X, Zhang M, Pan Z. Interaction and animation simulation of digital shadow play. J Image Graph. 2014;19(10):1490–1499. doi:10.11834/jig.20141011. [https://www.cjig.cn/zh/article/doi/10.11834/jig.20141011/](https://www.cjig.cn/zh/article/doi/10.11834/jig.20141011/)
65. Zhu Y, Li C, Shen I, Ma K, Stompel A. A new form of traditional art: visual simulation of Chinese shadow play. SIGGRAPH 2003 sketches. [https://history.siggraph.org/?p=142936](https://history.siggraph.org/?p=142936)
66. Henson Digital Puppetry wiki. Henson Digital Performance Studio. [https://hdps.fandom.com/wiki/Henson_Digital_Performance_Studio](https://hdps.fandom.com/wiki/Henson_Digital_Performance_Studio)
67. Jakobsen's method in Hitman: Codename 47. Wikipedia, Ragdoll physics. [https://en.wikipedia.org/wiki/Ragdoll_physics](https://en.wikipedia.org/wiki/Ragdoll_physics)
68. Survey of rigid body simulation with extended position based dynamics. arXiv:2311.09327. 2023. [https://arxiv.org/abs/2311.09327](https://arxiv.org/abs/2311.09327)
