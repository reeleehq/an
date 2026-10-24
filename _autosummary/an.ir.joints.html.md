# an.ir.joints

The constraint layer’s verbs: `pin`, `pull`, `join` and `unjoin` (ADR 0008, an#512).

A joint ([`an.ir.schema.JointSpec`](an.ir.schema.html.md#an.ir.schema.JointSpec)) says how two bodies stay together;
these four action kinds say what happens to them over time, and they are the
puppeteer’s whole repertoire:

- `pin` (a rod, a nail): a point of a body is held exactly at a point (of
  another body, or of the stage) for a span, or refused when it is out of
  reach (`an validate` reports `unreachable_pin`);
- `pull` (a string): a point is drawn as close as the joints allow toward a
  point, or along a path over the span, with a `give`;
- `join` / `unjoin`: a declared joint’s state from an instant on (a
  hand lets go of a cup; it is caught again).

None of them makes a clip. The `solve` compile pass ([`an.stage.solve`](an.stage.solve.html.md#module-an.stage.solve))
reads them beside the joints and emits the keys of the bodies they move; the
actions pass drops them (their `_SolverOnly` lowering).

```pycon
>>> from an.ir.compose import flatten, sequence, delay
>>> [(f.start, f.end, f.action.kind) for f in flatten(sequence(delay(1.0), pin("paul/fore_r@hand", "wheel@grip", duration=2.0)))]
[(1.0, 3.0, 'pin')]
>>> [(f.start, f.action.kind) for f in flatten(sequence(delay(1.0), unjoin("grip", at=0.5)))]
[(1.5, 'unjoin')]
```

These kinds are the core’s (ADR 0001’s test: a data-visualisation genre pins a
label to a bar without saying character), registered when [`an.ir`](an.ir.html.md#module-an.ir) loads.

### Module Attributes

| [`DFLT_PULL_GIVE`](#an.ir.joints.DFLT_PULL_GIVE)     | not at all.            |
|---------------------------------------------------------------------|------------------------|
| [`JOINT_ACTION_KINDS`](#an.ir.joints.JOINT_ACTION_KINDS) | The verbs' kind names. |

### Functions

| [`pin`](#an.ir.joints.pin)(point, to, \*[, duration])    | `point` held at `to`.                                         |
|------------------------------------------------------------------------------------|---------------------------------------------------------------|
| [`pull`](#an.ir.joints.pull)(point, to, \*[, over, give]) | `point` drawn toward `to` (a point, a body point, or a path). |
| [`join`](#an.ir.joints.join)(joint, \*[, at])             | Rejoin the joint named `joint` at `at`.                       |
| [`unjoin`](#an.ir.joints.unjoin)(joint, \*[, at])           | Let go of the joint named `joint` at `at`.                    |

### Classes

| [`PinAction`](#an.ir.joints.PinAction)(\*[, name, kind, duration])    | `point` (`body[@point]`) held exactly at `to` for `duration` seconds (`None`: to the shot's end).                                                                                                                                                     |
|-------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`PullAction`](#an.ir.joints.PullAction)(\*[, name, kind, over, give]) | `point` drawn toward `to` (a point, or a path of stage points walked at an even speed over the span) for `over` seconds (`None`: to the shot's end), as close as the joints allow; `give` is the string's softness (compliance, px per unit of pull). |
| [`JoinAction`](#an.ir.joints.JoinAction)(\*[, name, kind, at])         | The declared joint named `joint` is enforced from `at` on.                                                                                                                                                                                            |
| [`UnjoinAction`](#an.ir.joints.UnjoinAction)(\*[, name, kind, at])       | The declared joint named `joint` lets go from `at` on.                                                                                                                                                                                                |

### an.ir.joints.DFLT_PULL_GIVE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.0*

not at all. A reachable point is
met exactly; an unreachable one is given up for the frame before any joint of
the structure is (the solver drops the last-declared joint of a conflict), so
the chain reaches toward it as far as its joints allow, and nothing is torn.
A positive `give` is a soft string, which yields in proportion to the masses
it pulls (a compliance, px per unit of pull).

* **Type:**
  How soft a `pull` is when it says nothing

### an.ir.joints.JOINT_ACTION_KINDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('pin', 'pull', 'join', 'unjoin')*

The verbs’ kind names.

### *class* an.ir.joints.JoinAction(, name=None, kind='join', joint, at=0.0, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

The declared joint named `joint` is enforced from `at` on.

```pycon
>>> JoinAction(joint="grip", at=1.0).at
1.0
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.joints.PinAction(, name=None, kind='pin', point, to, duration=None, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

`point` (`body[@point]`) held exactly at `to` for `duration`
seconds (`None`: to the shot’s end). It frees the body `point` is on
for the span: a pinned cup goes to the hand, wherever it was staged.

```pycon
>>> PinAction(point="cup", to="paul/fore_r@hand").to
'paul/fore_r@hand'
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.joints.PullAction(, name=None, kind='pull', point, to, over=None, give=0.0, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

`point` drawn toward `to` (a point, or a path of stage points walked
at an even speed over the span) for `over` seconds (`None`: to the
shot’s end), as close as the joints allow; `give` is the string’s
softness (compliance, px per unit of pull).

```pycon
>>> PullAction(point="puppet/hand_l", to=[[0, -200], [100, -200]], over=2.0).over
2.0
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.ir.joints.UnjoinAction(, name=None, kind='unjoin', joint, at=0.0, \*\*extra_data)

Bases: [`ExtensionAction`](an.ir.schema.html.md#an.ir.schema.ExtensionAction)

The declared joint named `joint` lets go from `at` on.

```pycon
>>> UnjoinAction(joint="grip").kind
'unjoin'
```

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow', 'populate_by_name': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.ir.joints.join(joint, , at=0.0)

Rejoin the joint named `joint` at `at`.

```pycon
>>> join("grip", at=2.0).at
2.0
```

* **Return type:**
  [`JoinAction`](#an.ir.joints.JoinAction)

### an.ir.joints.pin(point, to, , duration=None)

`point` held at `to`. `to` is `body[@point]` or `(x, y)`.

```pycon
>>> pin("cup", (10.0, -40.0)).to
(10.0, -40.0)
```

* **Return type:**
  [`PinAction`](#an.ir.joints.PinAction)

### an.ir.joints.pull(point, to, , over=None, give=0.0)

`point` drawn toward `to` (a point, a body point, or a path).

```pycon
>>> pull("kite", "world@0,-300", over=1.0).give == DFLT_PULL_GIVE
True
```

* **Return type:**
  [`PullAction`](#an.ir.joints.PullAction)

### an.ir.joints.unjoin(joint, , at=0.0)

Let go of the joint named `joint` at `at`.

```pycon
>>> unjoin("grip").joint
'grip'
```

* **Return type:**
  [`UnjoinAction`](#an.ir.joints.UnjoinAction)
