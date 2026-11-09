# an.stage.support

Supports: what a body rests on, and how far it is from resting there (an#519, catalogue A1).

A `support` joint ([`an.ir.schema.JointSpec`](an.ir.schema.html.md#an.ir.schema.JointSpec), `type: support`) says a
body’s contact points rest on a surface: `ground` (the shot’s floor line),
`<body>@surface[@f]` (a body’s supporting segment, the hold layer’s grammar)
or a `world@x,y` segment with `end`. This module is the pure measurement
under the `support` check ([`an.verify.support`](an.verify.support.html.md#module-an.verify.support)):

- [`contacts_of()`](#an.stage.support.contacts_of): the named points of an entity that touch what it stands
  on, by one fallback chain: the entity kind’s hook
  ([`an.genres.EntityKind.contacts`](an.genres.html.md#an.genres.EntityKind.contacts): a character’s feet), else the
  descriptor’s `metadata.contacts` (`{name: [u, v]}`, fractions of the root
  part’s drawing), else the rig’s declared `origin` when a part rests on it
  (an#601’s rule: where the rig stands, not where it is held), else the lowest
  point of its root parts’ ink: `ink` when a raster’s alpha hull was read,
  `box` when only the corners of its box were (SVG art), which is measured
  for a declared support but never makes an entity be taken to stand.
- [`supports_at()`](#an.stage.support.supports_at): every declared support of a compiled shot, and every
  entity taken to stand on its floor, as [`SupportState`](#an.stage.support.SupportState) records per
  instant: each contact’s signed distance to the surface along its normal
  ([`an.stage.surface_line.lowest_on()`](an.stage.surface_line.html.md#an.stage.surface_line.lowest_on)’s sign: positive above, negative
  sunk), whether it is a **limb**’s (on a part that is not one of the body’s
  roots), where its foot on the surface lies along it (`along`, in the
  surface’s own frame) and how far that foot **slid** along it since the grid
  instant before while the contact was held there (the `skate` check’s
  measure, an#519 PR 2), with the references that do not resolve returned as
  `(where, message)`.

A named point (`cup@base`, `paul@foot_l`) is resolved by the solve’s own
resolver ([`an.stage.solve.locate_point()`](an.stage.solve.html.md#an.stage.solve.locate_point)), so a `pin` and a `support`
naming one contact name one point ([`an.stage.solve.contact_point()`](an.stage.solve.html.md#an.stage.solve.contact_point)); a
`<body>@surface` is the hold layer’s segment
([`an.stage.surface_line.body_surface()`](an.stage.surface_line.html.md#an.stage.surface_line.body_surface)).

Tolerances are fractions of the entity’s height with a pixel floor
([`support_tolerance()`](#an.stage.support.support_tolerance)): a wide and a close-up agree, and a small prop is
not held to a gap below what a frame shows.

```pycon
>>> support_tolerance(200.0), support_tolerance(30.0)
(4.0, 2.0)
```

### Module Attributes

| [`CONTACT_SOURCES`](#an.stage.support.CONTACT_SOURCES)       | Where an entity's contacts come from, in the order the chain tries them.                                                                                                                                                                                                                      |
|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CONTACTS_KEY`](#an.stage.support.CONTACTS_KEY)          | The descriptor's `metadata` key that names a prop's contacts.                                                                                                                                                                                                                                 |
| [`SUPPORT_TOLERANCE`](#an.stage.support.SUPPORT_TOLERANCE)     | How far a contact may be off its surface, either way, as a fraction of the entity's height (4 px on a 200 px figure).                                                                                                                                                                         |
| [`SUPPORT_FLOOR_PX`](#an.stage.support.SUPPORT_FLOOR_PX)      | the solver's own rejoin blend ([`an.kinematics.solver.DFLT_REJOIN_BLEND_PX`](an.kinematics.solver.html.md#an.kinematics.solver.DFLT_REJOIN_BLEND_PX)), below which it calls two points joined; a small prop is not held tighter than a joint.                                  |
| [`SKATE_TOLERANCE`](#an.stage.support.SKATE_TOLERANCE)       | How fast a held contact's foot may move along its surface, in the surface's own frame, as a fraction of the entity's height PER SECOND (24 px/s on a 200 px figure: 1 px a frame at 24 fps, 0.4 px at 60).                                                                                    |
| [`SKATE_FLOOR_PX`](#an.stage.support.SKATE_FLOOR_PX)        | The least skate speed tolerance, in px per second (half a pixel a frame at 24 fps: a fraction of a small body's height is less).                                                                                                                                                              |
| [`SKATE_DRIFT_TOLERANCE`](#an.stage.support.SKATE_DRIFT_TOLERANCE) | How far a held contact's foot may drift along its surface over one stance (from where it was planted, while it stays held), as a fraction of the entity's height (6 px on a 200 px figure): a slow skate under the speed tolerance still adds up to a foot that is not where it was put down. |
| [`SKATE_DRIFT_FLOOR_PX`](#an.stage.support.SKATE_DRIFT_FLOOR_PX)  | the support's own floor ([`SUPPORT_FLOOR_PX`](#an.stage.support.SUPPORT_FLOOR_PX)), below which two points are one.                                                                                                                                                                  |
| [`SKATE_LIFT`](#an.stage.support.SKATE_LIFT)            | A step between two instants whose foot moves along the surface's normal by more than this fraction of how far it moves along the surface is a lift-off or a landing (a foot leaving the floor while still within the support tolerance of it), not a slide: it is not measured for skate.     |

### Functions

| [`support_tolerance`](#an.stage.support.support_tolerance)(height, \*[, tolerance, floor])   | How far a contact of an entity `height` px tall may be off its surface: `tolerance` of its height, never under `floor` px.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`skate_tolerance`](#an.stage.support.skate_tolerance)(height, \*[, tolerance, floor])     | How fast (px per second) a held contact of an entity `height` px tall may slide along its surface: `tolerance` of its height per second, never under `floor`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| [`skate_drift_tolerance`](#an.stage.support.skate_drift_tolerance)(height, \*[, ...])            | How far (px) a held contact of an entity `height` px tall may drift along its surface over one stance: `tolerance` of its height, never under `floor`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| [`contacts_of`](#an.stage.support.contacts_of)(entity, mall, \*[, rig, ...])           | `entity`'s contacts, by the chain: the kind's hook, `metadata.contacts`, the rig's `origin` (when a root part's painted bottom rests on it, read in `doc`), else the lowest ink of its root parts: `ink` when `doc` shows a raster whose alpha hull was read, else `box`.                                                                                                                                                                                                                                                                                                                                                            |
| [`contacts_on_parts`](#an.stage.support.contacts_on_parts)(entity, desc, \*, rig)            | The contacts the chain names on a part of `entity`'s rig (the hook's, else `metadata.contacts`, a root-part fraction put on the first root): what the point resolver ([`an.stage.solve.locate_point()`](an.stage.solve.html.md#an.stage.solve.locate_point)) names after a rig's landmarks, so a joint, a verb or a support may name `paul@foot_l` as it names `paul@hand_l`.                                                                                                                                                                                                                                   |
| [`supports_at`](#an.stage.support.supports_at)(doc, shot, mall, \*[, times, ...])      | Every declared support of `shot` in its compiled document `doc` at every instant of `times` (default: the solve's frame grid, `an.stage.solve.frame_times()`), joined or not; and, with `inferred`, every entity taken to stand on the shot's floor (`solve: {ground: y}`) as it opens: its lowest contact within [`support_tolerance()`](#an.stage.support.support_tolerance) (`tolerance` of its height, `floor` px at least) of the floor then, measured at that instant and its rest instants (`rest_only`, the `support` check's rule) or at every instant (the `skate` check's, which judges a stance while it moves). |

### Classes

| [`Contacts`](#an.stage.support.Contacts)(source, points[, note])                  | An entity's contacts and where the chain found them.                        |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`ContactState`](#an.stage.support.ContactState)(name, part, at, above[, limb, ...])  | One contact at one instant.                                                 |
| [`SupportState`](#an.stage.support.SupportState)(entity, joint, where, frame, t, ...) | One support (declared, or a stance taken as the shot opens) at one instant. |

### an.stage.support.CONTACTS_KEY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'contacts'*

The descriptor’s `metadata` key that names a prop’s contacts.

### an.stage.support.CONTACT_SOURCES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('hook', 'metadata', 'origin', 'ink', 'box')*

Where an entity’s contacts come from, in the order the chain tries them.

### *class* an.stage.support.ContactState(name, part, at, above, limb=False, along=0.0, slid=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One contact at one instant.

#### above *: [float](https://docs.python.org/3/builtins/functions.html#float)*

Its signed distance to the surface along the normal (+ above, - sunk).

#### along *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.0*

where
the foot of its normal falls along the surface from a point fixed in it,
in the surface’s units (a body’s surface: its own units from the
segment’s first end, so it neither moves nor flips with the body; the
floor and a stage segment: stage px from the floor’s `(0, y)` or the
segment’s `a`).

* **Type:**
  Its foot parameter along the surface, in the surface’s own frame

#### at *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), [float](https://docs.python.org/3/builtins/functions.html#float)]*

Its stage point (the lowest of its points, for `ink` or `box`).

#### limb *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

its node is not the entity’s own nor one of its
root parts (a leg hinged to the body, a hoof), so it moves relative to
the body and can skate. A body’s own stance point (its `origin`, the
ink of its roots, a prop’s `base`, a bone on a root part) cannot: a
body that glides or is pushed slides on it by right.

* **Type:**
  Whether it is a limb’s

#### part *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The node path that carries it.

#### slid *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

How far (stage px, signed along the surface) its foot moved along the
surface, in the surface’s own frame, since the grid’s previous instant
(so a body carried by what it stands on does not move); `None` unless
it was held at both (its support joined, within the support tolerance of
the surface) and the step was not a lift-off or a landing
([`SKATE_LIFT`](#an.stage.support.SKATE_LIFT)).

### *class* an.stage.support.Contacts(source, points, note='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An entity’s contacts and where the chain found them.

```pycon
>>> Contacts("origin", {"origin": ("", None)}).names
('origin',)
```

#### note *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

Why a kind’s hook gave nothing it could use (it raised), else `""`.

### an.stage.support.SKATE_DRIFT_FLOOR_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 2.0*

the support’s own floor
([`SUPPORT_FLOOR_PX`](#an.stage.support.SUPPORT_FLOOR_PX)), below which two points are one.

* **Type:**
  The least drift tolerance, in px

### an.stage.support.SKATE_DRIFT_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.03*

How far a held contact’s foot may drift along its surface over one stance
(from where it was planted, while it stays held), as a fraction of the
entity’s height (6 px on a 200 px figure): a slow skate under the speed
tolerance still adds up to a foot that is not where it was put down.

### an.stage.support.SKATE_FLOOR_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 12.0*

The least skate speed tolerance, in px per second (half a pixel a frame at
24 fps: a fraction of a small body’s height is less).

### an.stage.support.SKATE_LIFT *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.25*

A step between two instants whose foot moves along the surface’s normal by
more than this fraction of how far it moves along the surface is a lift-off
or a landing (a foot leaving the floor while still within the support
tolerance of it), not a slide: it is not measured for skate.

### an.stage.support.SKATE_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.12*

How fast a held contact’s foot may move along its surface, in the surface’s
own frame, as a fraction of the entity’s height PER SECOND (24 px/s on a
200 px figure: 1 px a frame at 24 fps, 0.4 px at 60). A speed, so one slide
gets one verdict at any frame rate or step rate.

### an.stage.support.SUPPORT_FLOOR_PX *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 2.0*

the solver’s own rejoin blend
([`an.kinematics.solver.DFLT_REJOIN_BLEND_PX`](an.kinematics.solver.html.md#an.kinematics.solver.DFLT_REJOIN_BLEND_PX)), below which it calls two
points joined; a small prop is not held tighter than a joint.

* **Type:**
  The least tolerance, in px

### an.stage.support.SUPPORT_TOLERANCE *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.02*

How far a contact may be off its surface, either way, as a fraction of the
entity’s height (4 px on a 200 px figure).

### *class* an.stage.support.SupportState(entity, joint, where, frame, t, surface, surface_ref, contacts, joined, height, source, named='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One support (declared, or a stance taken as the shot opens) at one instant.

```pycon
>>> s = SupportState("cup", None, "entities", 0, 0.0, ((0.0, 0.0), (1.0, 0.0)), "ground",
...     (ContactState("base", "cup", (0.0, -3.0), 3.0),), True, 30.0, "metadata")
>>> s.lowest, s.inferred
(3.0, True)
```

#### contacts *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[ContactState](#an.stage.support.ContactState), ...]*

The contacts measured (one past a bounded surface’s ends is not).

#### frame *: [int](https://docs.python.org/3/builtins/functions.html#int)*

The instant’s index on the shot’s frame grid, and its time.

#### height *: [float](https://docs.python.org/3/builtins/functions.html#float)*

what its tolerance is a fraction of.

* **Type:**
  The entity’s height as the shot opens (px)

#### joint *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The support’s id; `None` when inferred.

#### *property* lowest *: [float](https://docs.python.org/3/builtins/functions.html#float) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The least distance of a contact above the surface; `None`, none measured.

#### named *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

The contact named in the reference, or `""` for all of them.

#### source *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Where its contacts came from ([`CONTACT_SOURCES`](#an.stage.support.CONTACT_SOURCES); a point named by
bone, landmark or fraction is `point`).

#### where *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Where it is declared (`joints/0`, `entities/1/joints/0`, …).

### an.stage.support.contacts_of(entity, mall, , rig=None, descriptor=None, doc=None)

`entity`’s contacts, by the chain: the kind’s hook, `metadata.contacts`,
the rig’s `origin` (when a root part’s painted bottom rests on it, read
in `doc`), else the lowest ink of its root parts: `ink` when `doc`
shows a raster whose alpha hull was read, else `box`.

```pycon
>>> from types import SimpleNamespace as NS
>>> contacts_of(NS(kind="prop", store=None, ref="x"), {}, descriptor={"origin": [0, 0]})
Contacts(source='origin', points={'origin': ('', None)}, note='')
>>> contacts_of(NS(kind="prop", store=None, ref="x"), {}).source
'box'
```

* **Return type:**
  [`Contacts`](#an.stage.support.Contacts)

### an.stage.support.contacts_on_parts(entity, desc, , rig)

The contacts the chain names on a part of `entity`’s rig (the hook’s,
else `metadata.contacts`, a root-part fraction put on the first root):
what the point resolver ([`an.stage.solve.locate_point()`](an.stage.solve.html.md#an.stage.solve.locate_point)) names after
a rig’s landmarks, so a joint, a verb or a support may name `paul@foot_l`
as it names `paul@hand_l`.

```pycon
>>> from types import SimpleNamespace as NS
>>> contacts_on_parts(NS(kind="prop"), {"metadata": {"contacts": {"base": [0.5, 1]}}}, rig=NS(roots=("body",)))
{'base': ('body', (0.5, 1.0))}
```

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)]]

### an.stage.support.skate_drift_tolerance(height, , tolerance=0.03, floor=2.0)

How far (px) a held contact of an entity `height` px tall may drift
along its surface over one stance: `tolerance` of its height, never under
`floor`.

```pycon
>>> skate_drift_tolerance(200.0), skate_drift_tolerance(40.0)
(6.0, 2.0)
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.stage.support.skate_tolerance(height, , tolerance=0.12, floor=12.0)

How fast (px per second) a held contact of an entity `height` px tall
may slide along its surface: `tolerance` of its height per second, never
under `floor`.

```pycon
>>> skate_tolerance(200.0), skate_tolerance(40.0)
(24.0, 12.0)
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.stage.support.support_tolerance(height, , tolerance=0.02, floor=2.0)

How far a contact of an entity `height` px tall may be off its surface:
`tolerance` of its height, never under `floor` px.

```pycon
>>> support_tolerance(500.0), support_tolerance(500.0, tolerance=0.05, floor=30.0)
(10.0, 30.0)
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.stage.support.supports_at(doc, shot, mall, , times=None, inferred=True, rest_only=True, tolerance=0.02, floor=2.0, lift=0.25)

Every declared support of `shot` in its compiled document `doc` at
every instant of `times` (default: the solve’s frame grid,
`an.stage.solve.frame_times()`), joined or not; and, with
`inferred`, every entity taken to stand on the shot’s floor
(`solve: {ground: y}`) as it opens: its lowest contact within
[`support_tolerance()`](#an.stage.support.support_tolerance) (`tolerance` of its height, `floor` px at
least) of the floor then, measured at that instant and its rest instants
(`rest_only`, the `support` check’s rule) or at every instant (the
`skate` check’s, which judges a stance while it moves).

A contact is held at an instant its support is joined and it is within
that tolerance of the surface; its `slid` is how far (stage px) its foot
parameter along the surface (`along`, in the surface’s own frame) changed
since the grid’s previous instant, when it was held at both and its motion
along the surface’s normal was at most `lift` of that (more is a foot
leaving or meeting the surface). Returns the states and `(where,
message)` for each reference that does not resolve (no state is made for
it).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`SupportState`](#an.stage.support.SupportState)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]]
