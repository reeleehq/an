# an.verify.holds

The hold checks: what `an validate` says about a shot’s holds (an#502, catalogue A1 and A4).

Three constraints on the one interface ([`an.verify.constraints.Constraint`](an.verify.constraints.html.md#an.verify.constraints.Constraint)),
over the compiled shot (the hold layer, [`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold), records what it
did in `meta.extensions.solve.holds`):

- `hold_conflict` (error): the holds do not add up: a hand puts down what
  it does not hold, a socket gets a second item, one hand does two things at
  once, a verb names an item that is not in the shot;
- `unreachable_hold` (error): a hand does not arrive where it takes or puts
  its item (even bending as far as its `lean` allows), with how far it
  stays short and which way to move the carrier;
- `floating_item` (warning): an item that a hand takes from the floor (or
  from a body’s surface the holds name: `crate@surface`, an#536) hovers
  above it (or sinks into it) before it is taken, and a released item
  with no ground below it or no gravity, that stays in the air.

All three are silent for a shot that holds nothing.

```pycon
>>> [c.name for c in HOLD_CONSTRAINTS]
['hold_conflict', 'unreachable_hold', 'floating_item']
```

### Module Attributes

| [`HOLD_CONSTRAINTS`](#an.verify.holds.HOLD_CONSTRAINTS)   | The hold checks, in the order they run.   |
|---------------------------------------------------------------------|-------------------------------------------|

### an.verify.holds.HOLD_CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](an.verify.constraints.html.md#an.verify.constraints.Constraint), ...]* *= (Constraint(name='hold_conflict', check=<function check_hold_conflict>, stage='shot', order=255.0, description='what holds each item, and when, adds up (grasp, place, release, handover, swap)', term=None), Constraint(name='unreachable_hold', check=<function check_unreachable_hold>, stage='shot', order=255.0, description='a hand arrives where it takes or puts its item (an#502)', term=None), Constraint(name='floating_item', check=<function check_floating_item>, stage='shot', order=255.0, description='an item taken from the floor lies on it, and a released item comes down (catalogue A1)', term=None))*

The hold checks, in the order they run.
