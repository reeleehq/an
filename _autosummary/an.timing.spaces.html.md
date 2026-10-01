# an.timing.spaces

Property spaces: what an entity kind’s properties ARE, declared once.

A **property space** is the registration unit an entity kind hands the kernel
(ADR 0001 decision 11): for each property pattern, its **field kind** (the
interpolator, [`an.timing.kinds`](an.timing.kinds.html.md#module-an.timing.kinds)), its **write group** (aliases that set the
same thing — `rotation_rad` is `rotation`; every swap set of one visual
replaces the same drawing), and its **unit** (stage pixels, radians, a ratio),
without which moving a value from one engine to another is meaningless.

Patterns are exact property names or `fnmatch` globs (`*@*`). An exact name
wins; globs are tried in declaration order. A property the space does not declare
is [`DiscreteKind`](an.timing.kinds.html.md#an.timing.kinds.DiscreteKind) at the default switch point, and writes
only itself.

Two spaces are seeded here, and they reproduce today’s output EXACTLY:

- `stage.node` — a node of the 2D stage engine: every name in
  `an.base.TRANSFORM_PROPERTIES` is `number` (linear), including
  > `tint_r/g/b` (`tint` itself stays the compiler’s authoring sugar, expanded
  > into those three before any channel exists, so the wire shape does not move);
  > every other property names a swap set, `*@*` included, and is
  > `discrete(switch_at=1)`.
- `stage.camera` — the stage’s 2D framing camera: `x`, `y`, `zoom`,
  `rotation`, all plain `number` (the compiler lowers them onto `root`’s
  pivot, scale and rotation channels). New genres get log zoom and shortest-arc
  rotation by declaring their own camera space, not by changing this one.

Genres register their own spaces with [`register_space()`](#an.timing.spaces.register_space) (P2: through the
`an.genres` entry point), without editing this module.

```pycon
>>> node = get_space("stage.node")
>>> node.kind_of("x"), node.kind_of("viseme@happy")
(NumberKind(space='linear'), DiscreteKind(switch_at=1))
>>> node.write_group("rotation_rad"), node.write_group("hands"), node.unit_of("rotation")
('rotation', '<swap>', 'rad')
>>> PropertySpace("demo", ()).kind_of("anything")  # undeclared: discrete
DiscreteKind(switch_at=0.5)
```

### Module Attributes

| [`SWAP_WRITE_GROUP`](#an.timing.spaces.SWAP_WRITE_GROUP)       | they all replace the one drawing the node carries (`viseme` and `viseme@happy` both set the mouth's texture, an#88).                                                                                                          |
|-------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`SWAP_KIND`](#an.timing.spaces.SWAP_KIND)              | A replacement drawing never appears before its own key (an#86).                                                                                                                                                               |
| [`STAGE_NODE_UNITS`](#an.timing.spaces.STAGE_NODE_UNITS)       | What the stage node's transform properties are measured in.                                                                                                                                                                   |
| [`STAGE_NODE_ALIASES`](#an.timing.spaces.STAGE_NODE_ALIASES)     | Properties that write another property's value on the same node.                                                                                                                                                              |
| [`CORE_OWNER`](#an.timing.spaces.CORE_OWNER)             | Who registered the seeded spaces (only these reach the contract files).                                                                                                                                                       |
| [`DFLT_VALUE_TYPED_SPACE`](#an.timing.spaces.DFLT_VALUE_TYPED_SPACE) | The space whose write groups the value-typed rule (`space=None`) uses: the stage engine's node, resolved BY NAME at call time, so moving the stage's registration (P3: into `an.stage`) or replacing it needs no kernel edit. |
| [`SpaceLike`](#an.timing.spaces.SpaceLike)              | one space for every target, a registered space's name, or a per-target resolver (P2: target -> its entity kind's space).                                                                                                      |
| [`STAGE_NODE`](#an.timing.spaces.STAGE_NODE)             | P3 moves their registration into `an.stage`.                                                                                                                                                                                  |

### Functions

| `get_space`(name)                                                                            |                                                                               |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`register_space`](#an.timing.spaces.register_space)(space, \*[, replace, owner]) | Register `space` under its name (how an entity kind declares its properties). |
| [`space_from_json`](#an.timing.spaces.space_from_json)(doc)                        | A space from its JSON form (what `PropertySpace.to_json()` writes).           |
| [`space_names`](#an.timing.spaces.space_names)(\*[, owner])                    | The registered space names in registration order; only `owner`'s when given.  |
| [`space_resolver`](#an.timing.spaces.space_resolver)(space)                       | `space` as a `target -> PropertySpace` function.                              |

### Classes

| [`FieldDecl`](#an.timing.spaces.FieldDecl)(pattern, kind[, unit, writes, ...])   | One declaration of a property space: pattern -> kind, write group, unit.     |
|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`PropertySpace`](#an.timing.spaces.PropertySpace)(name[, fields, version, ...])     | An entity kind's properties: declarations, matched exact-first then by glob. |

### Exceptions

| [`SpaceError`](#an.timing.spaces.SpaceError)   | A property space is malformed, unknown, or already registered.   |
|---------------------------------------------------------------|------------------------------------------------------------------|

### an.timing.spaces.CORE_OWNER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an'*

Who registered the seeded spaces (only these reach the contract files).

### an.timing.spaces.DFLT_VALUE_TYPED_SPACE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'stage.node'*

The space whose write groups the value-typed rule (`space=None`) uses:
the stage engine’s node, resolved BY NAME at call time, so moving the stage’s
registration (P3: into `an.stage`) or replacing it needs no kernel edit.

### *class* an.timing.spaces.FieldDecl(pattern, kind, unit=None, writes=None, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One declaration of a property space: pattern -> kind, write group, unit.

#### writes *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

The write group this property belongs to; `None` means itself.

### *class* an.timing.spaces.PropertySpace(name, fields=(), version=1, description='', undeclared=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An entity kind’s properties: declarations, matched exact-first then by glob.

#### declaration(prop)

The declaration governing `prop`, or `None`.

* **Return type:**
  [`FieldDecl`](#an.timing.spaces.FieldDecl) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### undeclared *: [FieldKind](an.timing.kinds.html.md#an.timing.kinds.FieldKind)*

The kind of a property no declaration matches.

### an.timing.spaces.STAGE_NODE *: [PropertySpace](#an.timing.spaces.PropertySpace)* *= PropertySpace(name='stage.node', fields=(FieldDecl(pattern='alpha', kind=NumberKind(space='linear'), unit='fraction', writes=None, description=''), FieldDecl(pattern='dash_offset', kind=NumberKind(space='linear'), unit='px', writes=None, description=''), FieldDecl(pattern='pivot_x', kind=NumberKind(space='linear'), unit='px', writes=None, description=''), FieldDecl(pattern='pivot_y', kind=NumberKind(space='linear'), unit='px', writes=None, description=''), FieldDecl(pattern='rotation', kind=NumberKind(space='linear'), unit='rad', writes=None, description=''), FieldDecl(pattern='rotation_rad', kind=NumberKind(space='linear'), unit='rad', writes='rotation', description=''), FieldDecl(pattern='scale_x', kind=NumberKind(space='linear'), unit='ratio', writes=None, description=''), FieldDecl(pattern='scale_y', kind=NumberKind(space='linear'), unit='ratio', writes=None, description=''), FieldDecl(pattern='skew_x', kind=NumberKind(space='linear'), unit='rad', writes=None, description=''), FieldDecl(pattern='skew_y', kind=NumberKind(space='linear'), unit='rad', writes=None, description=''), FieldDecl(pattern='tint_b', kind=NumberKind(space='linear'), unit='fraction', writes=None, description=''), FieldDecl(pattern='tint_g', kind=NumberKind(space='linear'), unit='fraction', writes=None, description=''), FieldDecl(pattern='tint_r', kind=NumberKind(space='linear'), unit='fraction', writes=None, description=''), FieldDecl(pattern='trim_end', kind=NumberKind(space='linear'), unit='fraction', writes=None, description=''), FieldDecl(pattern='trim_start', kind=NumberKind(space='linear'), unit='fraction', writes=None, description=''), FieldDecl(pattern='x', kind=NumberKind(space='linear'), unit='px', writes=None, description=''), FieldDecl(pattern='y', kind=NumberKind(space='linear'), unit='px', writes=None, description=''), FieldDecl(pattern='\*@\*', kind=DiscreteKind(switch_at=1), unit=None, writes='<swap>', description='a variant swap set (viseme@happy): replacement animation'), FieldDecl(pattern='\*', kind=DiscreteKind(switch_at=1), unit=None, writes='<swap>', description='any other property names a swap set: replacement animation')), version=1, description='a node of the 2D stage engine: transform properties interpolate as plain numbers; every other property is a swap set that switches at its own key', undeclared=DiscreteKind(switch_at=0.5))*

P3 moves their registration
into `an.stage`. Kernel code resolves them by name (`get_space`).

* **Type:**
  Provisional handles on the seeded stage spaces

### an.timing.spaces.STAGE_NODE_ALIASES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'rotation_rad': 'rotation'}*

Properties that write another property’s value on the same node.

### an.timing.spaces.STAGE_NODE_UNITS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'alpha': 'fraction', 'dash_offset': 'px', 'pivot_x': 'px', 'pivot_y': 'px', 'rotation': 'rad', 'rotation_rad': 'rad', 'scale_x': 'ratio', 'scale_y': 'ratio', 'skew_x': 'rad', 'skew_y': 'rad', 'tint_b': 'fraction', 'tint_g': 'fraction', 'tint_r': 'fraction', 'trim_end': 'fraction', 'trim_start': 'fraction', 'x': 'px', 'y': 'px'}*

What the stage node’s transform properties are measured in.

### an.timing.spaces.SWAP_KIND *: [DiscreteKind](an.timing.kinds.html.md#an.timing.kinds.DiscreteKind)* *= DiscreteKind(switch_at=1)*

A replacement drawing never appears before its own key (an#86).

### an.timing.spaces.SWAP_WRITE_GROUP *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '<swap>'*

they all replace the
one drawing the node carries (`viseme` and `viseme@happy` both set the
mouth’s texture, an#88).

* **Type:**
  The write group every swap set on a stage node shares

### *exception* an.timing.spaces.SpaceError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A property space is malformed, unknown, or already registered.

### an.timing.spaces.SpaceLike

one space for every target, a
registered space’s name, or a per-target resolver (P2: target -> its entity
kind’s space).

* **Type:**
  What an evaluator accepts as “the space”

alias of [`PropertySpace`](#an.timing.spaces.PropertySpace) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | `Callable`[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`PropertySpace`](#an.timing.spaces.PropertySpace)]

### an.timing.spaces.register_space(space, , replace=False, owner=None)

Register `space` under its name (how an entity kind declares its properties).

`owner` names who registered it; only [`CORE_OWNER`](#an.timing.spaces.CORE_OWNER)’s spaces reach
`an`’s contract files, so an installed genre never edits the core contract.

* **Return type:**
  [`PropertySpace`](#an.timing.spaces.PropertySpace)

### an.timing.spaces.space_from_json(doc)

A space from its JSON form (what `PropertySpace.to_json()` writes).

* **Return type:**
  [`PropertySpace`](#an.timing.spaces.PropertySpace)

### an.timing.spaces.space_names(, owner=None)

The registered space names in registration order; only `owner`’s when given.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.timing.spaces.space_resolver(space)

`space` as a `target -> PropertySpace` function.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`PropertySpace`](#an.timing.spaces.PropertySpace)]
