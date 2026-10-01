# an.timing.flat

The authored flat timeline: `(start, end, address, change)` rows.

The upper of the kernel’s two canonical levels (core study §2.4). Every authoring
front-end — `an`’s combinators, a keyframe sequence, Manim-style beats, recipes —
lowers to this list with absolute seconds, and a compiler lowers it to the
compiled form ([`an.timing.timeline`](an.timing.timeline.html.md#module-an.timing.timeline)). It is what `timeline.schema.json`
describes and what a package that copies `an`’s track format (`shaping`)
validates against.

A **change** is `set` (a value from `start` on) or `tween` (from an
optional `from` — absent means “from whatever the property has at `start`” —
to `to`, through an `easing`). Genre actions (a `play`, an `expression`)
are not changes: a genre lowers them before this level.

```pycon
>>> from types import SimpleNamespace as NS
>>> rows = [NS(start=0.0, end=1.0, action=NS(kind="tween", target="charlie/left_arm",
...     property="rotation", to_value=0.5, from_value=None, easing="ease_in_out"))]
>>> flat_timeline_doc(rows)["actions"]
[{'start': 0.0, 'end': 1.0, 'address': 'charlie/left_arm:rotation', 'change': {'kind': 'tween', 'to': 0.5, 'easing': 'ease_in_out'}}]
```

### Module Attributes

| [`FLAT_TIMELINE_FORMAT`](#an.timing.flat.FLAT_TIMELINE_FORMAT)   | The document's self-description (`{kind, version}` envelope, core study §2.1).   |
|-------------------------------------------------------------------------|----------------------------------------------------------------------------------|

### Functions

| [`change_of`](#an.timing.flat.change_of)(action, \*[, default_easing])    | The `change` of one leaf action (any object with the IR's attribute names).   |
|---------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`flat_timeline_doc`](#an.timing.flat.flat_timeline_doc)(flat_actions, \*[, ...]) | A `timeline.schema.json` document from flat actions.                          |

### Exceptions

| [`UnsupportedChangeError`](#an.timing.flat.UnsupportedChangeError)   | A flat action is not a `set` or a `tween` (a genre action not yet lowered).   |
|---------------------------------------------------------------------------|-------------------------------------------------------------------------------|

### an.timing.flat.FLAT_TIMELINE_FORMAT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an.timeline'*

The document’s self-description (`{kind, version}` envelope, core study §2.1).

### *exception* an.timing.flat.UnsupportedChangeError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A flat action is not a `set` or a `tween` (a genre action not yet lowered).

### an.timing.flat.change_of(action, , default_easing=None)

The `change` of one leaf action (any object with the IR’s attribute names).

A tween’s easing is written RESOLVED and always (`null` is linear): the
tween’s own, else `default_easing` (the scene’s `meta.default_easing`),
else the IR default — the precedence `TweenAction.resolved_easing` states,
so the flat document says what compiles (an#166).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.timing.flat.flat_timeline_doc(flat_actions, , duration=None, default_easing=None, skip_other=False)

A `timeline.schema.json` document from flat actions.

Each item has `start`, `end` and a leaf `action` with `kind`,
`target`, `property` and the change’s values — the shape of
`an.ir.compose.flatten`’s output, read by attribute so this module does not
import the IR. `default_easing` is the scene’s `meta.default_easing`.
`skip_other` drops non-change actions instead of raising.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
