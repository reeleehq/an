# Cut-out framework review — October 2026

**Status:** review for the maintainer, 2026-10-01, companion to `misc/docs/framework_review_2026-10.md` (whose §1 glossary defines the terms used here). This document is about the **cut-out genre**. When the genre moves to its own package (an#225), this document goes with it.

**The question.** Do we have a clear theory — a framework — that can handle *any* cut-out animation? What is the asset architecture? For a character: the art, the rig, the replacement animation, the views, the expressions and mouth chart, the locomotion and actions — and the ins and outs of defining each, as built, planned and missing. For each: where it sits between structured and semantic specification, and how capability-based applicability with defaults should apply.

**Short answer.** Not yet a theory; a strong mechanism. `an` has one general mechanism that is genuinely theory-shaped: a **flat tree of slots** whose **transforms** are keyed by channels and whose **drawings** are substituted by **swap channels**, all compiled ahead of time into one property timeline. Replacement animation of mouths, eyelids, hands, views and prop states rides that one mechanism with no per-set code (an#87, proven by a fixture whose set names appear nowhere in the code). What is missing is (1) the parts of the cut-out state space the representation cannot express yet — a real transform **hierarchy**, keyed **draw order**, **deformation**, **masks**, **FX**; and (2) a shared theory of *what a behaviour requires of a character*. §1 proposes the theory, §2–3 audit against it, §4–5 place each aspect on the specification spectrum and the capability model.

---

## 1. A theory of cut-out animation

### 1.1 The state space

A cut-out frame is fully described, part by part, by five things:

1. **Transform** — position, rotation, scale, skew, pivot, composed down a **hierarchy** (a forearm moves with the upper arm).
2. **Drawing** — which drawing the part shows right now (**replacement animation**: a mouth shape, a hand pose, a three-quarter head).
3. **Order** — which part is in front (**draw order**, which a turn or an arm crossing the body changes).
4. **Shape** — the drawing's own deformation (a **mesh**/free-form deformation, a bend, a squash that is more than a scale), plus **masks** that clip one part by another.
5. **Surface** — colour (tint, palette role), opacity, and treatments (outline, shadow, glow, texture).

Plus the things around the parts: the **set** (planes with parallax), the **camera**, **FX** (particles, smears, speed lines), **text/graphics**, and **sound**.

Every cut-out tool is some subset of that space. A style is a choice of *which* dimensions it uses and *how* it times them: South Park uses transform + drawing on a flat rig, held on twos and threes; Reiniger uses transform over a deep hierarchy with black surfaces; Norstein uses transform + shape + surface (soft edges, layered translucency) under a multiplane camera; Gilliam uses transform + drawing with photo art and hard cuts.

### 1.2 The animation operators

Anything that changes the state over time is one of:

| Operator | What it does | `an` today |
|---|---|---|
| **Key / tween** | interpolate a transform or surface value | `set`, `tween`, easing, `step_hz` |
| **Substitution** | change a part's drawing (stepped, never blended) | swap channels |
| **Pose** | change several parts' transforms *and* drawings together, as one keyed state | `swap_poses` (a pose per swap key), whole-character swaps |
| **Clip / action / cycle** | a reusable timed bundle of the above, possibly looping | descriptor `animations` (`play`), motion presets |
| **Procedure** | values computed from parameters (a walk from stride and step time, a breath, a saccade, secondary motion) | presets expand to tweens at compile time; gaze saccades; sine idle tracks |
| **Constraint** | values computed from other values (IK, look-at, attach a prop to a hand) | none |
| **Layering** | combining several contributions to one property (additive over a base, override, mix) | later-wins everywhere, except the face solver, which sums |
| **Timing** | resampling onto a grid (on twos), holds, exposure | `step_hz` (one grid per shot) |

### 1.3 The asset architecture

| Asset kind | Domain term | What defines it | `an` today |
|---|---|---|---|
| **Character** | rigged puppet | art + rig + controls + action library + voice (§2) | `characters` store, `CharacterDescriptor` |
| **Prop** | prop | art + a small rig + **states** (swap sets) | `props` store, `PropDescriptor` (one bone, one slot; states as swap sets) |
| **Set / environment** | background, layout, multiplane | planes (art, depth, size, fit, anchor) + where characters stand | `environments` store, `EnvironmentDescriptor` + `Plane` |
| **Camera** | camera / camera rig | moves and keys per shot; a library of named moves | shot-level `Camera`, `CAMERA_MOVES` (not an asset) |
| **FX** | effects animation | particle emitters, smears, impact stars, dust, speed lines, rain | **missing** |
| **Text and graphics** | titles, cards, lower thirds, labels, maps, diagrams | typeset text, stroked paths, filled regions | `TextDescriptor`, `PathDescriptor` (as props); filled shapes and maps missing |
| **Audio** | voice, SFX, music bed | voice documents, sound cues, beds | `voices`, `sounds` stores |
| **Style** | style guide / show bible | palette roles, surface treatments, cadence and staging targets, construction rules | `StylePack` + `an-style` YAML specs (the compiler reads the pack, not the spec) |
| **Action library** | actions / templates | reusable clips and cycles, retargetable to compatible rigs | Python presets + per-descriptor animations; no stored, shared library |
| **Rig templates / construction kits** | character templates, model packs | a skeleton + slot layout + swap-set schema that art can be dropped into | the factory's `BodyBuild` and the art-package contract; not a stored template |
| **Crowds** | crowd instancing | one asset placed many times with variation | **missing** (an#163 gap 6) |

Reuse across videos and styles (principle 3) is the asset library's job — flat, tagged, addressed by key — and is designed separately (`misc/docs/asset_library_design.md`, ADR 0005: flat readable ids, immutable versions, content-addressed files, capability facets derived by ADR 0002's analyser; motion clips are their own kind declaring `requires`).

### 1.4 Coverage of the six measured masters

| Style | Dimensions it needs | Expressible today | Missing in the representation |
|---|---|---|---|
| South Park | transform + drawing, flat rig, twos/threes, outline/shadow/grain | yes | — (art and motion vocabulary, not representation) |
| OverSimplified | transform + drawing, bursts on ones, text, maps, crowds | mostly | filled regions, crowd instancing, narration (`Shot.narration` still raises) |
| Kurzgesagt | transform + surface (glow), layered planes, ambient motion, dolly | mostly | depth-aware zoom (dolly), ambient-motion library |
| Gilliam | transform + drawing, photo art, pop-ups, hard cuts | mostly | morph transitions; photo-to-parts ingestion |
| Reiniger | transform over a **deep hierarchy**, black surfaces, intertitles | partly | **hierarchy** (rigs are flat), keyed draw order |
| Norstein | transform + **shape** + **surface** (soft edges, translucent layers), multiplane | partly | **deformation**, soft edges / masks, dolly |

So the representation is complete for flat-puppet styles and incomplete for articulated and painterly ones. The next study (an#223) should be read against §1.1's five dimensions: for each master, *which dimensions and which operators*, so the methods can be mixed.

---

## 2. The character, aspect by aspect

For each aspect: **as built**, **how you define it** (the ins and outs), **planned**, **missing**.

### 2.1 Art (drawings, attachments)

- **Built.** `Attachment(path, anchor, x, y, width, height, source)`: SVG or raster (PNG/JPEG/WebP) parts; declared size wins and is fitted uniformly (`attachment_box`); one rig scale per character from `view_box`; per-attachment licence `source`, listed by `an credits` (all-rights-reserved art is marked not publishable); `colour_roles` tags SVG literals with palette roles so a `StylePack` can recolour them; `face_overlay: false` declares a face baked into the head art.
- **How you define it.** Generate (`an character new`, with `build`, `head_scale`, `hat`, `sash`, `palette`, mouth variants, views), fetch (DiceBear, a bootstrap only), or draw to the art-package contract (`an character contract` prints the brief; `an character validate` checks a delivery offline; `promote` / `extract_part` cut parts out of one SVG with a `<g id="skeleton">` of pivot circles). Skills: `an-art-package`, `an-dev-rig-contract`.
- **Planned.** Named-layer PSD/SVG/Krita import, nine-slice props, rope limbs (Wave 9 remainder, no issue); EXIF orientation (an#218).
- **Missing.** Recolouring raster art; any check that a part is the *right* part.

### 2.2 Rig (skeleton, pivots, slots, draw order)

- **Built.** `Bone(name, parent, x, y, rotation_deg, scale_x, scale_y, pivot)`, `Slot(name, bone, draw_order, attachment)`, `Skin`. The compiler builds a **flat** tree: bone parent chains place parts at rest, but bone rotation and scale are not inherited, and only one level of nesting exists (a slot hangs under the slot sharing its bone's name — which is why the face moves with the head while the arms are siblings of the torso). Pivots are attachment anchors. Draw order is static. `BodyBuild` keeps bones and art in one record so they cannot disagree. Procedural placeholder rig for characters with no descriptor.
- **How you define it.** In `character.json` (bones, slots, skins), usually generated by the factory or `promote`. Animate by path: `<entity>/<slot>:<property>`.
- **Planned.** Hierarchical puppet rigs (an#163 gap 11).
- **Missing.** A transform hierarchy; keyed draw order; **IK** and constraints (deliberately not scheduled in an#9); attach points (a prop in a hand); mesh deformation.
- **Assessment.** Flat-by-design is right for South Park and OverSimplified and wrong for Reiniger. The hierarchy should be added as an *option of the rig*, which the capability registry then exposes (`rig.hierarchy` as a capability a method can require), not as a new default.

### 2.3 Replacement animation (swap sets)

- **Built.** `asset_sets {set: {KEY: attachment}}`, projected onto every slot whose skin carries those attachments; one runtime applier (`applySwap`); always stepped; per-key geometry (`asset_geometry`); undeclared sets and keys fail at compile, validate and runtime. Whole-character swaps fan a set on the entity out to every slot it projects onto; `swap_poses` key per-slot transforms to a swap key (a pose swap). Descriptor `play` slot tracks resolve to one set each.
- **How you define it.** Declare the set in the descriptor; put a drawing per key in the skin; author a `set` whose `property` is the set name and whose `value` is the key, targeting the slot (`charlie/head`) or, for a whole-character swap, the entity (`charlie`). Skill: `an-dev-swap-channels`.
- **Missing.** **Skin switching** (only the default skin is drawn); two sets on one sprite resolve by name order (a known hazard).
- **Assessment.** The best-founded part of the framework. Keep it in the core (data viz needs state swaps too: an icon's states); the character-specific conventions (views, eyelids, mouths, hands) stay in the genre.

### 2.4 Views (turnarounds)

- **Built.** `view` set over `front`, `three_quarter`, `side`, `back`; factory-drawn turnarounds with `view_poses`; `add-views` for older characters; `rest_view`; the `turn` preset (squeeze `scale_x` through 0, swap at the midpoint, mirrored for left); `resolve_turns` infers direction from the timeline; per-view face sets (`eyelid@side`, `viseme@side`); validate warns about hidden mouths and view continuity across shots.
- **How you define it.** Draw per-view art as keys of the `view` set (plus per-view face sets if the face changes), declare `rest_view` if the default art is not the front, author a `play` of `turn` or a `set` of the `view` set.
- **Planned.** A head-turn library (an#163 gap 9).
- **Missing.** Views carried across shots; head-only turns; rotational in-betweens (only a swap at the midpoint).

### 2.5 Expressions and the mouth chart

- **Built.** Expression **axes** (brows, lids, gaze, mouth form, intensity) and ten **presets**; the **binding** is derived from the slots the rig has; the compile-time **face solver** sums contributions into one channel per node and property (lid = min(expression, blink)); blinks compiled as lid swaps when closed-eye art exists, else a squash; gaze with seeded saccades; the 9-shape **mouth chart** (Rhubarb A–H, X) with `viseme@<form>` variants chosen per line by emotion; co-articulation passes (lead, decay, close-after-speech, a dominance-voted minimum hold).
- **How you define it.** Mouth set and variants from `an character mouths`; eye stack from `add-gaze`; optional `expression_binding` to override the derived one; author `[emotion]` on a line or an `expression` action. Skills: `an-dev-expression`, `an-dev-lipsync`.
- **Planned.** The emotion-judge cassette (an#171); deferred axes (`brow_squeeze`, `squint`, head yaw/pitch).
- **Missing.** Any speech for a baked face (`face_overlay: false` — the mouth stays frozen); body posture as part of an expression; head turn as an axis.

### 2.6 Locomotion and actions

- **Built.** `an.motion` presets (`pop_in`, `hop`, `shake`, `nod`, `point`, `slide_in/out`, `squash_stretch`, `waddle`, `turn`, `walk`) that expand to plain tweens at compile time, played by name from `scene.md` starting from the pose the node has at that moment; `walk` picks its view from the timeline and its gait from the descriptor (`legs` swing in profile or lift in front view; `hem` tilts robe halves; `rock` for a legless figure); descriptor animations (sine/step/linear bone and slot tracks), looping with `loop: true`.
- **How you define it.** Name a preset with `args`, or add an animation to the descriptor (a descriptor animation of the same name wins over the preset).
- **Planned.** Locomotion methods with declared requirements and capability-based selection (an#224); per-placement loop override (an#94).
- **Missing.** Run, shuffle, glide as gaits; contact/passing poses; a stored, shareable action library; looping presets; retargeting (an action authored for one rig applied to another with matching affordances); animation layering (an additive walk under a gesture).

---

## 3. Against the established tools

| Concept (tool) | `an` name | State |
|---|---|---|
| Bones (all) | `Bone` | rest position only; no inherited rotation/scale; flat nodes |
| Slots, attachments (Spine) | `Slot`, `Attachment` | built |
| Skins (Spine) | `Skin` | declared; only the default is drawn |
| Draw-order keys (Spine) | — | static only |
| Drawing substitution / switch layers / attachment keys | swap channels | **built, the core mechanism** |
| Smart bones / corrective drawings (Moho) | `swap_poses`; `expression_binding` | partial: corrective per discrete key only, never driven by a continuous angle |
| Master controllers (Harmony) | expression axes; the `view` fan-out | face and view only |
| Pegs (Harmony) | entity container + per-slot transform | no separate pegs, no deep hierarchy |
| Actions / templates | descriptor `animations`, presets | presets are code, not a stored library |
| Animation mixing, track layering (Spine) | — | missing (face solver excepted) |
| Events (Spine) | — | missing (`SoundCue` is time-based) |
| IK, transform/path constraints | — | missing |
| Mesh / free-form deformation, weights | — | missing |
| Clipping masks | — | missing |
| Physics / secondary motion | — | missing (sine idles only) |
| Cut-out character breakdown (Harmony) | `promote`, `extract_part`, the skeleton group, `an character contract` | built |

---

## 4. Structured ↔ semantic, per cut-out aspect

Levels as in `misc/docs/design_principles.md`: (a) typed field → formula; (b-name) a name resolved by lookup; (b-LLM) words resolved by an LLM/agent and recorded; (c) a goal verified after rendering.

| Aspect | Today | Should be |
|---|---|---|
| Art | (a) documents; (c) structural validation | + (b-LLM) "a grumpy baker in South Park style" → factory knobs / art brief; (c) a vision check that each part is the part it claims to be |
| Rig | (a) | (a) only — a rig is a precise instruction; (b) only through templates ("biped, robe") |
| Swap sets | (a); keys are names | (a); (b-name) key aliases (`smile` → the chart's shape) |
| Views | (a) `set view`; (b-name) `turn to: back` | + (b-LLM) "she turns to face him" → `turn` with `face_toward` (already computes direction) |
| Expressions | (b-name) `[happy]`; (a) axes; (c) emotion judge (cassette unrecorded), expression goldens | the model for every other aspect: keep all three levels, record the judge |
| Mouth / lip sync | (a) providers produce visemes; (b-name) mouth forms by emotion | + (c) a sync check (audio/mouth offset) |
| Locomotion | (b-name) `play: walk` + (a) args | + (b-LLM) "walks in nervously" → gait + stride + pose; (c) "feet do not slide" (foot-contact check) |
| Actions | (b-name) preset or descriptor animation | + a stored action library searchable by description (b-LLM over registry descriptions) |
| Style | (b) an agent applies a YAML spec by hand; (a) `StylePack`; (c) style lint | a style document the compiler reads: `live` = (a), `targets` = (c), `guidance` = (b-LLM) |
| Staging, acting | (a) placements and tweens | (b-LLM) direction ("she backs away as he advances") → tweens; (c) overlap and framing lint |

---

## 5. Capability-based applicability — today and the general mechanism

Every aspect below is a registry of **methods** with a **default chain** (and an optional per-style **policy** that reorders it), as proposed in ADR 0002. "Requires" lists what the method needs the asset to afford. The last link of each chain requires nothing, so every character gets every aspect.

| Aspect | Today (scattered mechanisms) | Proposed methods (requires) → default chain |
|---|---|---|
| Locomotion | `walk` + `gait` (`legs` / `hem` / `rock`), `_limb_pair` finds legs by name, `rest_view` | legged cycle (leg pair with hip pivots; profile or three-quarter view for stride) → hem sway (two hem slots) → waddle (a body) → hop (nothing) → glide (nothing). an#224 builds this |
| Speech | visemes need a mouth slot with a `viseme` set; `face_overlay: false` suppresses the mouth (frozen face) | mouth chart (mouth slot + viseme set; per-view sets when views exist) → jaw flap (a jaw or head part) → body pulse on syllables (nothing). **Today's frozen-mouth case gets a default** |
| Blink | lid swap if closed-eye art, else squash | lid swap (eyelid set) → squash (eye parts) → none (nothing) |
| Expression | binding derived from slots; gaze no-op without pupils; refusal on a baked face | full face (brows, lids, mouth forms) → partial (whatever parts exist, axes without a binding dropped *and recorded*) → posture-only (head tilt, body squash) |
| Turn | `turn` requires a `view` set (hint: `add-views`) | view swap (view set) → mirror flip (nothing) |
| Gesture (point, wave) | `point` targets an arm by name | arm swing (arm slot) → whole-body lean (nothing) |
| Hold an object | — | attach point (hand bone) → overlap placement (nothing) |
| Hierarchical motion (Reiniger) | — | nested rig (hierarchy affordance) → flat approximation |
| Recolour | roles reach only tagged art; raster cannot be recoloured | tagged SVG roles → whole-part tint (nothing) |
| Surface treatments | outline as a ring of texture copies for any SVG | exact (procedural shapes) → approximate copies (any art) |

What the creator gets:

- with no specification, every aspect applies its default to any character;
- asked "which walks can she do?", the system lists the applicable methods;
- asked for one she cannot do, the system names the missing structure, and how to add it (draw a `view` set, split the legs, add hip pivots), and meanwhile renders the default **with the substitution recorded**.

---

## 6. What to do next, in order

1. Build the capability registry in the core and move today's private chains onto it (ADR 0002); an#224 is its first new client.
2. Give speech a universal default, so a baked face no longer speaks with a frozen mouth.
3. Add the missing state-space dimensions in order of the masters they unlock: **hierarchy** and **keyed draw order** (Reiniger, and any arm crossing a body), then **masks and soft edges** (Norstein), then **deformation**. Expose each as an affordance, never as a new default.
4. Make the action library a stored, tagged asset kind in the asset library (ADR 0005 already makes motion clips a kind that declares `requires`), retargeted by affordances.
5. Add **FX** as an asset kind (particles and smears as compile-time expansions, deterministic like the surface treatments).
6. Read an#223's master studies against §1.1–1.2, so each master is described as *dimensions × operators × timing*, ready to be mixed.
