# an.verify.joints

The joint checks: what `an validate` says about a shot’s joints (ADR 0008, an#512).

Three constraints on the one interface ([`an.verify.constraints.Constraint`](an.verify.constraints.html.md#an.verify.constraints.Constraint)),
each a lint over the compiled shot whose `term` is the solver’s residual
([`an.stage.solve.joint_residuals()`](an.stage.solve.html.md#an.stage.solve.joint_residuals), the same measure the `solve` pass
drives to zero):

- `unknown_body` (error): a joint or a verb names a body, a point or a joint
  the shot does not have;
- `unreachable_pin` (error): a `pin` the joints cannot meet, with how far
  the chain reaches and where in reach to put the target;
- `joint_violation` (warning): a joined joint that does not hold in the
  compiled output (authored motion pulled it apart, or a hinge is bent past
  its range), with the time and the two bodies; a rejoin that closes more
  than [`REJOIN_TOLERANCE_PX`](#an.verify.joints.REJOIN_TOLERANCE_PX) in one frame (below that it reads as a
  blend); and, as `info`, the authored spans a solved channel replaces.

All three are silent for a shot that declares no joint and no verb, and they
run after the constraint catalogue’s lints (order `JOINT_CHECK_ORDER`).

```pycon
>>> [c.name for c in JOINT_CONSTRAINTS]
['unknown_body', 'unreachable_pin', 'joint_violation']
```

### Module Attributes

| [`JOINT_TOLERANCE_PX`](#an.verify.joints.JOINT_TOLERANCE_PX)   | the solver's own tolerance ([`an.kinematics.solver.DFLT_TOLERANCE`](an.kinematics.solver.html.md#an.kinematics.solver.DFLT_TOLERANCE)).   |
|-----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`REJOIN_TOLERANCE_PX`](#an.verify.joints.REJOIN_TOLERANCE_PX)  | A rejoin closing a gap wider than this in one frame is a visible snap (owner decision 9 on an#497: a lint at 2 px, a blend below it).                    |
| [`JOINT_CONSTRAINTS`](#an.verify.joints.JOINT_CONSTRAINTS)    | The joint checks, in the order they run.                                                                                                                 |

### an.verify.joints.JOINT_CONSTRAINTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Constraint](an.verify.constraints.html.md#an.verify.constraints.Constraint), ...]* *= (Constraint(name='unknown_body', check=<function check_unknown_body>, stage='shot', order=250.0, description='a joint or a verb names a body, a point or a joint the shot has (ADR 0008)', term=None), Constraint(name='unreachable_pin', check=<function check_unreachable_pin>, stage='shot', order=250.0, description='a pin is within reach of the joints that hold the body it moves (ADR 0008)', term=<function joint_term>), Constraint(name='joint_violation', check=<function check_joint_violation>, stage='shot', order=250.0, description='a joined joint holds at every frame of the compiled shot (ADR 0008)', term=<function joint_term>))*

The joint checks, in the order they run.

### an.verify.joints.JOINT_TOLERANCE_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.25*

the
solver’s own tolerance ([`an.kinematics.solver.DFLT_TOLERANCE`](an.kinematics.solver.html.md#an.kinematics.solver.DFLT_TOLERANCE)).

* **Type:**
  How far apart a joint’s two points may be in the compiled output (px)

### an.verify.joints.REJOIN_TOLERANCE_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 2.0*

A rejoin closing a gap wider than this in one frame is a visible snap (owner
decision 9 on an#497: a lint at 2 px, a blend below it).
