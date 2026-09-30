---
name: an-dev-swap-channels
description: How swap channels work in the `an` repo — the one generic replacement-animation mechanism (an#87) that viseme, eyelid, hands, body_facing, view and every future set ride, plus whole-character swaps and `swap_poses` (an#197). Use when touching `asset_sets`, the per-slot projection in `compile.py`, `applySwap`/`applyProperty` in `runtime.js`, `VisualJSON.asset_sets`, swap validation, texture aliases, or when adding a new swap set or authoring swaps from scene.md. Triggers on "swap channel", "asset set", "attachment swap", "texture swap", "viseme special case", "the mouth doesn't change", "unknown swap key", "add a hands set", "turnaround", "body_facing", "eyelid".
---

# Swap channels: one implementation, sets as data

**Authority: `misc/docs/wave5_research.md` (measured 2026-08-24).** When this file
and that one disagree, the research doc wins; when the code disagrees with both,
the code wins and you fix the other two. The wave that built this is epic #9
Wave 5; the build is an#87 (PR-B), on the ground an#86 (PR-A) prepared.

## The one-paragraph model

A channel whose property is **not** a transform (`x`, `rotation`, `alpha`, …)
names a **swap set**. The descriptor declares sets as
`asset_sets: {set: {KEY: attachment_name}}`; the compiler **projects** each set
onto every slot whose attachments carry its values and stamps the resolved
`{set: {KEY: texture_alias}}` onto that node's `VisualJSON.asset_sets`; the
runtime's `applyProperty` default case finds the node's child visual whose
`_anAssetSets` (texture swap) or `_anDrawSets` (procedural redraw) contains the
property and applies the key — or **throws naming node, set, and known keys**.
`viseme` is a conventional set name riding this path; so is everything else.
There is no other swap implementation, and the epic forbids a second.

## Load-bearing decisions (each measured; do not relitigate casually)

1. **The property IS the set name** (scheme i). `property="swap"` was rejected
   (two sets on one node collide on the `target::swap` pose key with an
   emission-order winner nothing pins); `swap:<set>` buys nothing over the
   reservation check. Corollary: a set name must not collide with
   `an.base.TRANSFORM_PROPERTIES` or contain `::`/`/` — the static switch
   would silently shadow it. Enforced by `an.base.swap_set_name_problem` at
   compile (`_swap_vocabulary`) and in `an character validate`.
2. **Binding is projection, not declaration.** `asset_sets` carries no slot
   field; the skin IS the binding. A set may project onto several slots — that
   is how ONE `eyelid` set drives both eye slots, whose attachments share the
   per-slot keys `open`/`closed` (the 0.3.0 migration renamed them from
   `eye_l_open` for exactly this). **Gotcha**: sharing attachment names is
   what OPTS a slot into a set — give a hand slot an attachment named `open`
   and the eyelid set will project onto it. Per-slot attachment names are the
   membership mechanism, name them deliberately.
3. **Texture aliases are slot-qualified** (`{entity}.{slot}.{attachment}`).
   The old `{entity}.{attachment}` space was silently first-wins on cross-slot
   collision, and shared per-slot keys make collisions the NORM.
4. **Swap channels are stepped by FORMAT** (Spine's attachment keyframes carry
   `{time, name}`, no curve field). The compiler forces `easing="step"` on a
   swap tween and warns; the evaluator additionally snaps non-numeric values
   on TIME (`t >= b.time`), so easing could not move a swap even if emitted
   (an#86 — the eased and raw-parameter snaps were both measured wrong).
5. **The value domain is loud.** Authored swap on an undeclared set/key →
   `CutoutCompileError` naming the declared ones (also caught pre-render by
   `an/ir/validate.py::_check_swap_references`). A **used** key whose art is
   missing → dropped with a warning AND a fallback record (fatal under
   `strict_assets`); an unreferenced inventory gap stays a mute 'incomplete' —
   usage-aware escalation, deliberately NOT the blanket rule (which would
   brick every rig without closed-eye art). The runtime throw is for
   hand-written scenes: compiled scenes are total by construction.
6. **Sets compile to HOLD channels — until the next action.** `set` actions
   on one (target, property) merge into a step channel that holds from each
   set until the next action on that target/property: the next set joins as
   a keyframe, a tween ENDS the hold at its start (so the tween governs and
   its end value persists after it), and with nothing following the hold
   runs to the shot end. Holding to the shot end regardless was measured to
   let a `set` mask every later tween on the property (the clip lands after
   the tween clips and evaluation is later-wins). Never reintroduce the
   0.001s placement window either: a set at a non-frame-aligned time silently
   never fired, and persistence was an accident of stateful forward rendering.
7. **A swap carries the texture AND, when it differs, the key's geometry**
   (an#211). The node's transform and the sprite's box/anchor are baked from
   the DRAWN attachment; a key whose own box (its art's extent x the rig's one
   uniform scale `k`), anchor or offset differs is listed in
   `VisualJSON.asset_geometry` (`{asset_id: {width, height, anchor_x,
   anchor_y, x, y}}`, omit-when-unset — a rig whose keys share one canvas
   emits nothing, so no corpus hash moved). `applySwap` → `applyKeyGeometry`
   re-boxes, re-anchors and re-places the sprite with the texture (the built
   geometry is restored for any unlisted key and by the rest-restore path);
   `refitToBox` still re-fits every other swap (keep it — without it every key
   inherits the previous texture's scale). The offset lives on the SPRITE,
   inside the slot's container, so channels and `swap_poses` on the node are
   untouched, and `fitUnderlay` adds `main.x/y` so outline/shadow copies
   follow. Before this a closed mouth drawn on a thin canvas squashed every
   open mouth to a fraction of a pixel, and validate only compared DECLARED
   geometry, so it never saw it.
8. **Preload needs nothing.** Every attachment of every slot of the active
   skin is registered/staged/loaded up front, precisely so a swap's texture
   is GPU-ready when the key changes. Cross-skin swaps are out of scope.

## Adding a new set (a data change, by design)

1. Declare it in the descriptor: `asset_sets["props"] = {KEY: attachment}`.
2. Put the attachments (and their files) in the slot(s) that should swap.
3. Author `{kind: set, target: <entity>/<node>, property: props, value: KEY}`.

No compiler, runtime, serialize, or schema change — for a set in YOUR
descriptor. (The shipped DEFAULT rig's `eyelid` set needed a schema event, because
"the skin is the binding" means slots one set drives together must share
attachment names, and the default eye slots did not.) The proof of the claim is
`tests/test_swap_channels.py::test_the_renderer_knows_nothing_about_the_fixture_sets`
— the committed fixture (`tests/fixtures/characters/gale/`, `hands` +
`body_facing`) animates with zero occurrences of its set names in either file.
If your new set needed code, you broke the generalisation; stop and fix that.

## The mutation-tested traps (keep them killed)

- **(a)** non-step easing on a swap tween → forced to step, with a warning
  (`test_trap_a_...`); the evaluator's time-based snap is pinned by
  `test_cutout_channel_parity.py`.
- **(b)** unknown swap key → loud at every layer: compile
  (`test_trap_b_an_undeclared_key_...`), runtime
  (`test_trap_b_the_runtime_throws_...` — executed against the extracted
  `applySwap`, not grepped). The old viseme path had SEVEN silent failure
  paths (research §1); do not reintroduce any as a "fallback".

## Where things live

| What | Where |
|---|---|
| Declared sets, eyelid keys, 0.3.0 migration | `an/characters/schema.py` |
| Projection + aliases + swap checks + hold channels | `an/adapters/cutout/compile.py` (`_swap_vocabulary`, `_check_swap_action`, `_build_svg_character_subtree`, `_compile_actions`) |
| Wire carrier | `serialize.py::VisualJSON.asset_sets` |
| The one applier | `runtime.js::applySwap` (+ `applyProperty` default case; `_anDrawSets` for the procedural mouth) |
| Pre-render validation | `an/ir/validate.py::_check_swap_references` (transform list duplicated-and-pinned); `an/characters/validate.py::_check_asset_sets` |
| Proof fixture + tests | `tests/fixtures/characters/gale/`, `tests/test_swap_channels.py` |
| Demo | `misc/demos/build_demos.py::_build_swap_channels` |

## Whole-character swaps and `swap_poses` (an#197)

A `set` of a swap set on the ENTITY itself (`{kind: set, target: ned,
property: view, value: side}`) is fanned out by `_fan_out_entity_swaps` into
the same `set` on every path `swap_capable_paths(entity, set)` returns, each
then checked like an authored swap; it only fires for a descriptor character
whose root node does not carry the set. Each fan-out is recorded, and
`_swap_pose_layer` turns the descriptor's `swap_poses[set][key][slot]`
(`SlotPose`: `x`/`y` offsets in view_box units, a `rotation` added in
radians and never scaled — an#203, how the profile splays its legs —
`scale_x`/`scale_y`/`alpha` factors) into step curves per (node, property) — a slot posed under any key
of the set returns to rest under the others. The face solver takes a posed
entity down its solver path and FOLDS a curve into any channel it drives
(the pupil's gaze `x` is summed onto the posed `x`, never a second channel
fighting it); the rest ride its `__face__` clip as step channels. Nothing
names `view`: it is the factory's convention (`an.characters.schema.
VIEW_CHANNEL`), and the `gale` fixture's `body_facing` turns the same way
(`tests/test_motion.py`). This is the "multi-slot turnaround" the Wave 5
ruling deferred — done as a fan-out plus data, not a skin switch. View art
on the default part's canvas emits no per-key geometry; art on another canvas
is placed by its own box (point 7).
A `turn` PLAYED by name reads the timeline before it: `an.characters.play.
resolve_turns` (shared by compile's `_expand_preset_plays` and `an validate`)
fills in `from_direction` from the latest earlier `scale_x` on the entity, so
chained turns need nothing by hand; a pose's `alpha` step to 0 is a hide, not
a fade, so it never trips the surface-treatment fade warning (an#203).
Tests: `tests/test_turnaround.py`.

## Per-view face sets (an#220)

`<set>@<view>` — `eyelid@side`, `viseme@side` — is the face drawn for a view:
a declared set whose base (`eyelid`) is declared and whose suffix is a key of
the `view` set (or the descriptor's `rest_view`); `an.characters.schema.
view_variant_sets` is the one reader, and `declared_mouth_variants` excludes
these so `viseme@side` is never taken for a mouth form. The compiler reads the
view timeline off the fan-out record (`_view_spans`: the latest `view` swap,
else `rest_view`) and, ONLY for an entity with a per-view set that some span
actually shows (every other scene compiles byte-identically):

- **lids** — the entity takes the face-solver path; an eye whose view set has
  `OPEN`+`CLOSED` art gets one `__face_lid__` clip per view span on that
  span's set (`_lid_span_clips`) instead of one `eyelid` channel;
- **lines** — `_line_view_set` picks the set at the line's start (the view
  before the expression chain; a missing key falls back to `viseme` with a
  warning), and `_line_view_segments` splits the line's clip at every view
  change inside it, so a line spoken through a turn changes mouth with it;
- **the silent mouth** — `hold_clips(..., exact=True)` holds each span's set
  rest outside the lines; the expression holds step aside over the view's
  spans (`holes`);
- **a descriptor `play`** (a blink) — `_resolve_play(view=...)` swaps on the
  variant when the node carries it with every key the track uses. Known limit:
  the view is read at the play's START, so a play running across a turn keeps
  its first view's set to its end (a blink is 0.18 s; it is not split);
- **authored lids** — an authored `eyelid` channel no longer switches the
  per-view lid clips off (the profile's art would never show); they carry no
  auto-blink then (an#88), and the authored clips still win where they play.

**The trap this design avoids:** two swap sets playing at one instant on one
sprite share the `<swap>` write group and tie on "most recently written", so
they resolve by NAME order — `eyelid@side` beats `eyelid` regardless of the
view. Every per-view clip therefore ends `_VIEW_SPAN_EDGE_S` before the next
view's span begins (exact edges, not frame-snapped), so at each instant exactly
one of them is playing and the latest-written one shows. Tests:
`tests/test_carved_art_gaps.py`.

## `play` rides the same channels (an#7)

A `play` of a descriptor animation compiles slot tracks into swap channels on
exactly these sets — `an.characters.play.resolve_play` picks the ONE set whose
keys name every frame's attachment (two candidates is an error naming both) and
the compiler emits `ChannelJSON(property=<set>, value=<KEY>)` like an authored
`set`. Bone tracks become transform channels around the built node's rest.
Resolution is shared with `an validate`; when you change what a slot or set
can carry, change it there, not in `compile.py`.
