# an.ir.holds

Holding things: `grasp`, `place`, `release`, `handover` and `swap` (an#502, catalogue A4).

A **hold** says what carries an item over a span of a shot: a hand (any point
of a body), a socket of another body (a figurine’s hand), the ground, a point
of the stage, or nothing (it is in flight). These five action kinds change
holds, and each one moves the holder the way a hand would, so the change
reads as handled rather than teleported:

- `grasp`: the holder’s point (`by`) **reaches** the item’s grip over
  `reach` seconds, takes it at the instant it arrives (the item keeps the
  pose it has at that instant: no slide, no jump), and **retracts** to where
  the shot would have it over `retract` seconds, carrying it. The item is
  taken from whatever held it: the ground, a socket, another hand (a
  hand-over between two hands is the receiver’s `grasp`).
- `place`: the hand that holds the item brings it `onto` a target over
  `reach` seconds (its contact point onto the ground at floor height, its
  grip into a socket, aligned with the socket’s frame), lets it go there, and
  retracts empty.
- `release`: the hand lets go at `at`; the item falls under gravity with
  the velocity it had and lands on the ground at its rest angle, or is tossed
  `onto: ground@x` on an arc of height `arc`.
- `handover`: `place` into another holder’s point (`to`), or, with
  `meet` below 1, both hands reach toward each other and the receiver takes
  it where they meet.
- `swap`: a hand takes the item a holder has (`take`) and the hand
  holding another item gives it in its place (`give`), a beat later.

A reach that cannot arrive is never cheated: the body it hangs from may bend
(`lean`, degrees; the chain’s root turns about its own pivot, the way a
figure bends at the hip), and beyond that `an validate` says how far the
hand stays short and where to stand instead.

None of these makes a clip: the `solve` compile pass reads them
([`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold)) and emits the holders’ and the items’ keys.

```pycon
>>> from an.ir.compose import flatten, sequence, delay
>>> [(f.start, f.end, f.action.kind) for f in flatten(sequence(delay(1.0), grasp("paul/arm_r", "cup")))]
[(1.0, 1.75, 'grasp')]
>>> [(f.start, f.action.kind) for f in flatten(sequence(delay(2.0), release("cup", at=0.5)))]
[(2.5, 'release')]
>>> [(round(f.start, 2), f.action.kind) for f in flatten(swap("nap/hand", take="musket", give="sword", by="stu@hand_r"))]
[(0.0, 'grasp'), (0.25, 'place')]
```

These kinds are the core’s (ADR 0001’s test: a robot arm putting a box on a
shelf needs them without saying character), registered when [`an.ir`](an.ir.html.md#module-an.ir) loads.

### Module Attributes

| [`DFLT_REACH`](#an.ir.holds.DFLT_REACH)        | a deliberate reach at arm's length, about two thirds of a second there and back.                                            |
|--------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_RETRACT`](#an.ir.holds.DFLT_RETRACT)      | How long the hand takes to come back to where the shot has it (s).                                                          |
| [`DFLT_LEAN_DEG`](#an.ir.holds.DFLT_LEAN_DEG)     | a figure bent well over at the hip.                                                                                         |
| [`DFLT_TOSS_ARC`](#an.ir.holds.DFLT_TOSS_ARC)     | How high a toss rises above the higher of its two ends (scene px).                                                          |
| [`DFLT_SWAP_LAG`](#an.ir.holds.DFLT_SWAP_LAG)     | In a `swap`, how long after the taking hand starts the giving hand starts (s): it arrives a beat after the socket is empty. |
| [`GROUND`](#an.ir.holds.GROUND)            | The name of the floor in a target (`ground`, `ground@x`).                                                                   |
| [`HOLD_ACTION_KINDS`](#an.ir.holds.HOLD_ACTION_KINDS) | The kinds' names.                                                                                                           |
| [`GESTURE_KINDS`](#an.ir.holds.GESTURE_KINDS)     | The kinds that move a hand (a reach and a retract), as flattened leaves.                                                    |

### Functions

| [`grasp`](#an.ir.holds.grasp)(by, item, \*[, reach, retract, lean, align])   | `by` takes `item`.                                               |
|-------------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`place`](#an.ir.holds.place)(item, onto, \*[, by, rotation, reach, ...])    | The hand holding `item` puts it `onto` a target.                 |
| [`release`](#an.ir.holds.release)(item, \*[, at, onto, arc, rotation])         | Let `item` go at `at` (a drop, or a toss `onto: ground@x`).      |
| [`handover`](#an.ir.holds.handover)(item, to, \*[, by, meet, reach, ...])       | Give `item` to `to`.                                             |
| [`swap`](#an.ir.holds.swap)(holder, \*, take, give, by[, lag, ...])         | `by` takes `take` from `holder`; `give` goes there in its place. |

### Classes

| [`GraspAction`](#an.ir.holds.GraspAction)(\*[, name, kind, reach, retract, ...])   | `by` (a body's point: a hand) reaches `item`'s grip and takes it.                                                                                                                                       |
|-------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PlaceAction`](#an.ir.holds.PlaceAction)(\*[, name, kind, by, rotation, ...])     | The hand holding `item` puts it `onto` a target and lets it go.                                                                                                                                         |
| [`ReleaseAction`](#an.ir.holds.ReleaseAction)(\*[, name, kind, at, onto, ...])       | The hand holding `item` lets it go at `at`: it falls with the velocity it had onto the ground, or is tossed `onto: ground@x` on an arc `arc` px high, and lands at `rotation` (default: as in `place`). |
| [`HandoverAction`](#an.ir.holds.HandoverAction)(\*[, name, kind, by, meet, ...])      | The hand holding `item` gives it to `to` (a hand, or a socket).                                                                                                                                         |
| [`SwapAction`](#an.ir.holds.SwapAction)(\*[, name, kind, lag, reach, ...])        | `by` takes `take` from `holder` and the hand holding `give` puts that there, `lag` seconds later: a `grasp` and a `place`.                                                                              |

### an.ir.holds.DFLT_LEAN_DEG *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 60.0*

a figure
bent well over at the hip. `0` never bends.

* **Type:**
  How far the body a hand hangs from may turn to reach (degrees)

### an.ir.holds.DFLT_REACH *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.4*

a
deliberate reach at arm’s length, about two thirds of a second there and back.

* **Type:**
  How long a hand takes to reach what it takes or where it puts it (s)

### an.ir.holds.DFLT_RETRACT *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.35*

How long the hand takes to come back to where the shot has it (s).

### an.ir.holds.DFLT_SWAP_LAG *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.25*

In a `swap`, how long after the taking hand starts the giving hand starts
(s): it arrives a beat after the socket is empty.

### an.ir.holds.DFLT_TOSS_ARC *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 40.0*

How high a toss rises above the higher of its two ends (scene px).

### an.ir.holds.GESTURE_KINDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('grasp', 'place', 'handover')*

The kinds that move a hand (a reach and a retract), as flattened leaves.

### an.ir.holds.GROUND *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'ground'*

The name of the floor in a target (`ground`, `ground@x`).

### *class* an.ir.holds.GraspAction(, name=None, kind='grasp', by, item, reach=0.4, retract=0.35, lean=60.0, align=True, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

`by` (a body’s point: a hand) reaches `item`’s grip and takes it.

`item` is an entity id, with `@<point>` the grip (a bone of its rig,
or `u,v` a fraction of its drawing); unset: its `grip` bone, else its
stage point. `by` with no `@` is the far end of the body (an arm’s
hand). The item is held from `start + reach` on, and over the retract it
turns to how the hand holds things (`align`): drawn as it is, upright
along the hand’s part, the way a socket holds it; `align: false` keeps
the angle it was taken at.

```pycon
>>> GraspAction(by="stu@hand_r", item="musket").reach == DFLT_REACH
True
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.holds.HOLD_ACTION_KINDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('grasp', 'place', 'release', 'handover', 'swap')*

The kinds’ names.

### *class* an.ir.holds.HandoverAction(, name=None, kind='handover', item, to, by=None, meet=1.0, reach=0.4, retract=0.35, lean=60.0, align=True, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

The hand holding `item` gives it to `to` (a hand, or a socket).

`meet` is where the two meet, as a fraction of the way from the giver’s
hand to the receiver’s: `1` (the default) puts it into the receiver’s
point, which does not move (a figurine’s hand, a waiting hand); below 1
both hands reach and the receiver takes it where they meet (and turns it
as a `grasp` does, `align`).

```pycon
>>> HandoverAction(item="sword", to="nap/arm_r/weapon").meet
1.0
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.holds.PlaceAction(, name=None, kind='place', item, onto, by=None, rotation=None, reach=0.4, retract=0.35, lean=60.0, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

The hand holding `item` puts it `onto` a target and lets it go.

`onto` is `ground` (straight down, at floor height), `ground@x` (at
stage `x`), a body’s point (a socket: the item’s grip goes there, its
frame aligned with the socket’s) or `world@x,y` (hung on a point).
`item@<point>` names the item’s point that touches the target (default:
its grip on a socket, its lowest point on the ground). `rotation`: the
item’s rotation where it rests (radians, the stage’s; default: the angle it
last rested at on the ground, else the nearest quarter turn; a socket’s own).

```pycon
>>> PlaceAction(item="musket", onto="nap/arm_r/weapon").by is None
True
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.holds.ReleaseAction(, name=None, kind='release', item, at=0.0, onto=None, arc=40.0, rotation=None, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

The hand holding `item` lets it go at `at`: it falls with the
velocity it had onto the ground, or is tossed `onto: ground@x` on an
arc `arc` px high, and lands at `rotation` (default: as in `place`).

```pycon
>>> ReleaseAction(item="cup", at=1.0).onto is None
True
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.holds.SwapAction(, name=None, kind='swap', holder, take, give, by, lag=0.25, reach=0.4, retract=0.35, lean=60.0, align=True, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

`by` takes `take` from `holder` and the hand holding `give`
puts that there, `lag` seconds later: a `grasp` and a `place`.

```pycon
>>> SwapAction(holder="nap/hand", take="musket", give="sword", by="stu@hand_r").lag == DFLT_SWAP_LAG
True
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.holds.grasp(by, item, , reach=0.4, retract=0.35, lean=60.0, align=True)

`by` takes `item`.

```pycon
>>> grasp("stu@hand_r", "musket@grip").item
'musket@grip'
```

* **Return type:**
  [`GraspAction`](#an.ir.holds.GraspAction)

### an.ir.holds.handover(item, to, , by=None, meet=1.0, reach=0.4, retract=0.35, lean=60.0, align=True)

Give `item` to `to`.

```pycon
>>> handover("cup", "jo@hand_l", meet=0.5).meet
0.5
```

* **Return type:**
  [`HandoverAction`](#an.ir.holds.HandoverAction)

### an.ir.holds.place(item, onto, , by=None, rotation=None, reach=0.4, retract=0.35, lean=60.0)

The hand holding `item` puts it `onto` a target.

```pycon
>>> place("book", "ground@-860").onto
'ground@-860'
```

* **Return type:**
  [`PlaceAction`](#an.ir.holds.PlaceAction)

### an.ir.holds.release(item, , at=0.0, onto=None, arc=40.0, rotation=None)

Let `item` go at `at` (a drop, or a toss `onto: ground@x`).

```pycon
>>> release("musket", onto="ground@-620", arc=60).arc
60.0
```

* **Return type:**
  [`ReleaseAction`](#an.ir.holds.ReleaseAction)

### an.ir.holds.swap(holder, , take, give, by, lag=0.25, reach=0.4, retract=0.35, lean=60.0, align=True)

`by` takes `take` from `holder`; `give` goes there in its place.

```pycon
>>> swap("nap/hand", take="musket", give="sword", by="stu@hand_r").give
'sword'
```

* **Return type:**
  [`SwapAction`](#an.ir.holds.SwapAction)
