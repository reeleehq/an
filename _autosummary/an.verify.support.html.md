# an.verify.support

The `support` and `skate` checks: a body declared to rest on a surface does, and its feet do not slide on it (an#519, catalogue A1 and B3).

Two constraints on the one interface ([`an.verify.constraints.Constraint`](an.verify.constraints.html.md#an.verify.constraints.Constraint)),
lint-only (no solver term in v1), over the compiled shot, measured by the pure
function [`an.stage.support.supports_at()`](an.stage.support.html.md#an.stage.support.supports_at). `support` (order 252):

- a declared `support` joint (`{type: support, a: paul, b: ground}`) whose
  contacts sink into its surface (**penetration**) or whose lowest contact is
  above it (**floating**) by more than [`an.stage.support.support_tolerance()`](an.stage.support.html.md#an.stage.support.support_tolerance)
  of the entity’s height, at any frame of the solve’s grid at which it is
  joined, is an **error** span; a reference it cannot resolve is an error too
  (the solve never sees a support, so `unknown_body` cannot say it);
- an entity nothing declares, taken to stand on the shot’s floor
  (`solve: {ground: y}`) as it opens, is held to it at its rest instants
  (between two keys where nothing of it moves), as a **warning**;
- `b: ground` on a shot with no floor is measured against where the entity
  stands as the shot opens, said once as `info`.

Not judged: an unjoined span (`unjoin` suspends the support: it is not a
flight), an entity’s declared flight (`overrides.airborne`), an item the
hold layer moves when nothing declares a support on it (`floating_item`’s).

`skate` (order 253, catalogue B3 i): a limb’s contact (one whose node is not
the entity’s own nor one of its root parts: a foot on a leg hinged to the
body) **held** on its surface (its support joined, within the support
tolerance) is foot skate when, between two instants of the grid at which it
is held, its foot slides along the surface faster than
[`an.stage.support.skate_tolerance()`](an.stage.support.html.md#an.stage.support.skate_tolerance) (a fraction of the entity’s height
per SECOND, so one slide gets one verdict at 24 or 60 fps), or when, over one
stance, it drifts from where it was planted by more than
[`an.stage.support.skate_drift_tolerance()`](an.stage.support.html.md#an.stage.support.skate_drift_tolerance) (a slow skate adds up). A step
on a `step_hz` grid is reported per step, not per frame. A step whose foot
moves along the surface’s normal by more than
[`an.stage.support.SKATE_LIFT`](an.stage.support.html.md#an.stage.support.SKATE_LIFT) of its slide is a lift-off or a landing,
not measured. The slide is measured in the surface’s own frame (a body’s
surface: in the body’s own units from its first end, so a figure standing on
a pushed or mirrored crate does not skate; the floor: from the stage’s
origin). An error for a declared support; for an entity taken to stand on
the floor, a warning, and only under a style pack that declares `gravity`
(a cartoon style that glides is right by declaration). A body’s own stance
point (`origin`, the ink of its roots, a prop’s `base`, a bone on a root
part) never skates: a pushed crate or a gliding figure slides on it by right.
In a shot a world frames, a member whose frame moves relative to the
viewpoint’s is not judged on `ground` (the stage floor does not stay under
it; `World.ground`, an#519 PR 4, measures it): said once as `info`.

```pycon
>>> SUPPORT.name, SUPPORT.order, SUPPORT.term is None
('support', 252.0, True)
>>> SKATE.name, SKATE.order, SKATE.term is None
('skate', 253.0, True)
```

### Module Attributes

| [`SUPPORT_CHECK_ORDER`](#an.verify.support.SUPPORT_CHECK_ORDER)   | after the joint checks (250), which report broken declarations first, before the hold checks (255).   |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| [`SKATE_CHECK_ORDER`](#an.verify.support.SKATE_CHECK_ORDER)     | just after the support check, whose broken references it does not repeat.                             |
| [`SUPPORT_CONSTRAINTS`](#an.verify.support.SUPPORT_CONSTRAINTS)   | The support checks, in the order they run.                                                            |

### Functions

| [`support_findings`](#an.verify.support.support_findings)(states, \*, times, shot[, ...])   | `(severity, where, message)` for each span of frames a support does not hold in `states` ([`an.stage.support.supports_at()`](an.stage.support.html.md#an.stage.support.supports_at)'s), the worst distance of the span named; `times` is the grid the states' frames index.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`skate_findings`](#an.verify.support.skate_findings)(states, \*, times, shot[, ...])     | `(severity, where, message)` for each span over which a limb's contact held on its surface slides along it faster than [`an.stage.support.skate_tolerance()`](an.stage.support.html.md#an.stage.support.skate_tolerance) (`tolerance` of the entity's height per second, default `SKATE_TOLERANCE`; `floor` px/s at least, default `SKATE_FLOOR_PX`), the fastest step of the span named; and for each stance (a run of held steps) with no such span over which it drifts from where it was planted by more than [`an.stage.support.skate_drift_tolerance()`](an.stage.support.html.md#an.stage.support.skate_drift_tolerance) (`drift` of the height, default `SKATE_DRIFT_TOLERANCE`; `drift_floor` px at least, default `SKATE_DRIFT_FLOOR_PX`). |

### an.verify.support.SKATE_CHECK_ORDER *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 253.0*

just after the support check, whose broken
references it does not repeat.

* **Type:**
  Where the skate check runs

### an.verify.support.SUPPORT_CHECK_ORDER *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 252.0*

after the joint checks (250),
which report broken declarations first, before the hold checks (255).

* **Type:**
  Where the support check runs within a shot

### an.verify.support.SUPPORT_CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](an.verify.constraints.html.md#an.verify.constraints.Constraint), ...]* *= (Constraint(name='support', check=<function check_support>, stage='shot', order=252.0, description='a body declared to rest on a surface neither sinks into it nor floats above it (catalogue A1, an#519)', term=None), Constraint(name='skate', check=<function check_skate>, stage='shot', order=253.0, description="a foot held on its surface does not slide along it, measured in the surface's own frame (catalogue B3, an#519)", term=None))*

The support checks, in the order they run.

### an.verify.support.skate_findings(states, , times, shot, step_hz=None, tolerance=None, floor=None, drift=None, drift_floor=None)

`(severity, where, message)` for each span over which a limb’s contact
held on its surface slides along it faster than
[`an.stage.support.skate_tolerance()`](an.stage.support.html.md#an.stage.support.skate_tolerance) (`tolerance` of the entity’s
height per second, default `SKATE_TOLERANCE`; `floor` px/s at
least, default `SKATE_FLOOR_PX`), the fastest step of the span named;
and for each stance (a run of held steps) with no such span over which it
drifts from where it was planted by more than
[`an.stage.support.skate_drift_tolerance()`](an.stage.support.html.md#an.stage.support.skate_drift_tolerance) (`drift` of the height,
default `SKATE_DRIFT_TOLERANCE`; `drift_floor` px at least, default
`SKATE_DRIFT_FLOOR_PX`). `times` is the grid the states’ frames
index; `step_hz` says it is a step grid, so a step is reported as one
(a pop on twos is not half of it per frame).

```pycon
>>> from an.stage.support import ContactState, SupportState
>>> from types import SimpleNamespace as NS
>>> def at(k, slid):
...     foot = ContactState("foot_l", "fig/leg_l", (0.0, 0.0), 0.0, limb=True, slid=slid)
...     return SupportState("fig", "left", "joints/0", k, k / 10, ((0.0, 0.0), (1.0, 0.0)),
...         "ground", (foot,), True, 200.0, "metadata")
>>> [m[:2] for m in skate_findings([at(0, None), at(1, 3.0), at(2, 0.0)],
...     times=[0.0, 0.1, 0.2], shot=NS(entities=[], duration=1.0))]
[('error', 'joints/0')]
>>> [(sev, m.split(" along ")[0]) for sev, _w, m in skate_findings(
...     [at(k, 0.5 if k else None) for k in range(20)],
...     times=[k / 10 for k in range(20)], shot=NS(entities=[], duration=2.0))]
[('error', "`fig`'s `foot_l` drifts 9.5 px")]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.verify.support.support_findings(states, , times, shot, tolerance=None, floor=None)

`(severity, where, message)` for each span of frames a support does not
hold in `states` ([`an.stage.support.supports_at()`](an.stage.support.html.md#an.stage.support.supports_at)’s), the worst
distance of the span named; `times` is the grid the states’ frames index.
A contact is off its surface beyond
[`an.stage.support.support_tolerance()`](an.stage.support.html.md#an.stage.support.support_tolerance): `tolerance` of the entity’s
height (default `SUPPORT_TOLERANCE`), `floor` px at least (default
`SUPPORT_FLOOR_PX`).

```pycon
>>> from an.stage.support import ContactState, SupportState
>>> from types import SimpleNamespace as NS
>>> def at(k, gap):
...     return SupportState("cup", "cup", "joints/0", k, k / 10, ((0.0, 0.0), (1.0, 0.0)),
...         "ground", (ContactState("base", "cup", (0.0, -gap), gap),), True, 30.0, "metadata")
>>> [m[:2] for m in support_findings([at(0, 0.0), at(1, 5.0), at(2, 6.0)],
...     times=[0.0, 0.1, 0.2], shot=NS(entities=[], duration=1.0))]
[('error', 'joints/0')]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
