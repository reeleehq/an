# Holding things: grasp, place, release, handover, swap

Anything one body picks up, carries, puts down or hands to another: a character taking a cup off a table, a figurine given a musket, a crane lowering a crate. Five action kinds (an#502), core, so they work on any rig; the cut-out genre names a character's hands (`stu@hand_r`, see the `cutan` skill).

**The model.** At every instant an item is held by exactly one thing: a body's point (a hand, a socket of another prop), the ground, a stage point, or nothing (in flight). A verb changes the holder, and the hand moves the way a hand would:

- **reach** — the hand's point swings to the goal on an arc about its shoulder, minimum-jerk eased (`reach` seconds, default 0.4; a long reach wants a longer `reach`, or it is fast);
- **contact** — at the frame it arrives the item changes holder, keeping its exact pose (no slide, no jump);
- **retract** — the hand goes back to where the shot has it (`retract` seconds, default 0.35), carrying the item or empty;
- **lean** — when the goal is out of the arm's reach, the body the arm hangs from (a torso, about its own pivot: the hip) bends by the least angle that brings it in reach, up to `lean` degrees (default 60), rising with the reach and falling with the retract; what rides on it (head, other arm) bends with it, the legs stay planted.

A carried item turns, mirrors and squashes with the hand that holds it (a character turning round carries it round). Nothing is ever cheated: a hand that cannot arrive is an `an validate` error that says how far it stays short and which way to move the carrier.

## The verbs

```yaml
- {kind: grasp, by: stu@hand_r, item: musket, start: 2.0}                 # take it from wherever it is
- {kind: place, item: musket, onto: nap/arm_r/weapon, start: 7.0}          # into a socket, aligned with it
- {kind: place, item: book, onto: ground@-860, start: 9.0}                 # lie it on the floor at x -860
- {kind: release, item: musket, at: 13.4, onto: ground@-420, arc: 60}      # toss it to land at x -420
- {kind: release, item: cup, at: 5.0}                                      # drop it: falls with the hand's velocity
- {kind: handover, item: cup, to: jo@hand_l, meet: 0.5, start: 4.0}        # both reach; jo takes it in the middle
- {kind: swap, holder: nap/arm_r/weapon, take: musket, give: sword, by: stu@hand_r, start: 10.4}
- {kind: place, item: musket, onto: nap/arm_r/weapon, start: 14.0, rotation: -0.1}   # aimed: the barrel at the stage angle -0.1
```

| field | on | means | default |
|---|---|---|---|
| `by` | grasp, swap (place, handover: optional) | the moving point: `entity@hand_r` (a genre's named point: **use it for characters**, it stays the hand when the rig gains a forearm or a hand bone), `entity/part@bone`, `entity/part@u,v`, or `entity/part` (that part's far end from its pivot) | place/handover/release: whoever holds the item |
| `item` | all | the entity held; `item@grip` names the point (a bone of its rig, or `u,v` of its drawing) | its `grip` bone, else its stage point; on the ground, its lowest painted point |
| `onto` | place, release | `ground` (straight down), `ground@x`, a socket `nap/arm_r/weapon` / `stand@hand`, or `world@x,y` | release: the ground below |
| `to` | handover | the receiver's point | |
| `meet` | handover | where the hands meet, from the giver's (1: into the receiver's point, which does not move) | 1 |
| `reach`, `retract` | grasp, place, handover, swap | seconds out and back | 0.4, 0.35 |
| `lean` | grasp, place, handover, swap | most degrees the body may bend | 60 |
| `align` | grasp, handover, swap | over the retract the item turns to how the hand holds things (drawn as it is, along the hand's part, as a socket holds it); `false` keeps the angle it was taken at | true |
| `rotation` | place, release, swap (the give) | the item's rotation where it comes to rest (radians, the stage's). Into a socket it is how the item is **aimed** there (a musket pointed at someone, a sabre raised): it arrives at that angle, grip on the socket, and from then on turns with the socket | as it last lay on the ground, else its nearest quarter turn; a socket's own |
| `arc` | release | how high a toss rises above its higher end (px) | 40 |
| `lag` | swap | how long after the taking hand the giving hand starts | 0.25 |

A `swap` is a `grasp` (by `by`, of `take`) and a `place` (of `give`, by whichever hand holds it, onto `holder`, at the swap's `rotation`) a beat apart: the socket is emptied before the new item arrives.

**Aiming what a socket holds.** A socket aligns every item the same way (its own frame, the item drawn as it is), so two items drawn differently (a musket barrel-down, a sabre tip-up) point different ways in one hand. Give the place (or the swap) a `rotation`: the stage angle the item rests at. Work it out from the art: the item's grip-to-tip direction at rotation 0, turned clockwise (y down) to where it should point.

## The ground and what holds an item at the start

- `solve: {ground: 502}` in the ` ```yaml shot ` block is the floor line (stage y, down positive). Unset, a hand puts things on the floor its own body stands on (the bottom of its rig's root parts).
- `overrides: {held_by: ground}` on an item entity: it lies on the floor when the shot opens, its lowest PAINTED pixel on the line (a raster's transparent margin does not float). Its x and rotation are what you staged.
- `overrides: {held_by: nap/arm_r/weapon}`: it starts in that socket (its grip there, aligned with it); `held_by: stu@hand_r`: in that hand. Not `on:` — YAML reads `on` as `true`.
- `overrides: {held_by: nap/arm_r/weapon, held_rotation: -0.98}`: it starts in that socket **aimed** at that stage angle (what a place's `rotation` would have left it at), then turns with the socket: a shot that continues another opens on the musket still pointed at Hannibal. Only beside a socket or a hand; an item on the ground lies at its staged rotation (`an validate` refuses `held_rotation` there).
- An item named by no `held_by` stays where it is staged until a hand takes it; `an validate` warns when it hovers above (or sinks into) the floor at that moment.

## What `an validate` says

- `hold_conflict` (error, the render refuses too): a hand puts down what it does not hold, takes what it already holds, still holds something else (a part that moves is one hand, whatever point of it is named), starts a second gesture before its first is over, or would reach its goal after the shot ends; a socket that still holds an item receives another (take it first, or `swap`); a verb names an item that is not in the shot; an item that is itself held holds another (not built).
- `unreachable_hold` (error): `'stu@hand_l' cannot put 'sword' on 'nap/arm_r/weapon' at 11.17 s: it stays 21.7 px short, bent 59.27°, ... Move stu about 22 px to the right`. Fix the staging, never the hold.
- `floating_item` (warning): the item lay above or below the floor when it was taken (`held_by: ground` fixes it); a released item with no ground below or no gravity stays in the air.
- `unknown_body` (error): a `by`, `onto`, `to`, `holder` or `held_by` that names nothing.

## Things to know

- **Draw order follows the holder** (an#537): while a hand or a socket holds an item, the item draws just above the part that holds it (over the arm that carries it, under whatever the carrier draws over that arm; with the figurine once it is put in its hand), and back at its staged place (its entity order, `stage.after` included) once it is on the ground or in the air. Its `stage.after` only decides where it draws while nothing holds it.
- **Gravity for a fall** is the shot's or the style pack's (`gravity:`), else 980 px/s² down; `solve: {gravity: none}` makes a released item stay where it was let go (a warning).
- **A catch:** a `release` and another hand's `grasp` of the same item at the same instant: the release comes first, the other hand catches it where it was let go.
- **Two gestures that bend one body opposite ways at once** cannot both arrive; `unreachable_hold` says which other gesture bends it the other way. Do them one after the other.
- **Reading the result:** `meta.extensions.solve.holds` in the compiled shot lists each gesture (`contact`, `gap`, `lean`) and each item's holders over time; `an probe <dir> --shot ID --at <contact>` shows the frame the item changes hands.
- **Holders that never move a hand are held still** (a figurine's arm is not solved); a character that gestures is solved like any puppet (ADR 0008): in pose mode the parts nothing acts on keep the angles you gave them.
- The hold layer runs in the `solve` compile pass (`an/stage/hold.py`); the solver moves the hand (a `pull` whose goal moves frame by frame), the hold layer moves the item.
