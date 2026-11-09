# an.verify.support

The `support` check: a body declared to rest on a surface does (an#519, catalogue A1).

One constraint on the one interface ([`an.verify.constraints.Constraint`](an.verify.constraints.html.md#an.verify.constraints.Constraint)),
lint-only (no solver term in v1), over the compiled shot, measured by the pure
function [`an.stage.support.supports_at()`](an.stage.support.html.md#an.stage.support.supports_at):

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

```pycon
>>> SUPPORT.name, SUPPORT.order, SUPPORT.term is None
('support', 252.0, True)
```

### Module Attributes

| [`SUPPORT_CHECK_ORDER`](#an.verify.support.SUPPORT_CHECK_ORDER)   | after the joint checks (250), which report broken declarations first, before the hold checks (255).   |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| [`SUPPORT_CONSTRAINTS`](#an.verify.support.SUPPORT_CONSTRAINTS)   | The support checks, in the order they run.                                                            |

### Functions

| [`support_findings`](#an.verify.support.support_findings)(states, \*, times, shot[, ...])   | `(severity, where, message)` for each span of frames a support does not hold in `states` ([`an.stage.support.supports_at()`](an.stage.support.html.md#an.stage.support.supports_at)'s), the worst distance of the span named; `times` is the grid the states' frames index.   |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### an.verify.support.SUPPORT_CHECK_ORDER *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 252.0*

after the joint checks (250),
which report broken declarations first, before the hold checks (255).

* **Type:**
  Where the support check runs within a shot

### an.verify.support.SUPPORT_CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](an.verify.constraints.html.md#an.verify.constraints.Constraint), ...]* *= (Constraint(name='support', check=<function check_support>, stage='shot', order=252.0, description='a body declared to rest on a surface neither sinks into it nor floats above it (catalogue A1, an#519)', term=None),)*

The support checks, in the order they run.

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
