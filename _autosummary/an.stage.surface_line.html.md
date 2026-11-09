# an.stage.surface_line

Surface lines: what a thing stands on, as a line on the stage (an#519).

A *support line* is a point on it and its unit direction, turned so that its
normal `(-dy, dx)` points DOWN the screen, into the support. The floor is a
level line ([`ground_line()`](#an.stage.surface_line.ground_line)); a body’s top edge or a stage segment is the
line through its two ends ([`line_through()`](#an.stage.surface_line.line_through)). Measured against one:

- [`lowest_on()`](#an.stage.surface_line.lowest_on): the lowest of some points (a part’s corners or ink,
  under its world matrix) against the line, and how far above it that point
  is, along its normal; negative when sunk into it. [`above()`](#an.stage.surface_line.above) is the
  distance alone.
- [`lift()`](#an.stage.surface_line.lift): a world matrix moved along the line’s normal by such a
  distance, which is how an item is laid exactly on what carries it.

A body’s own surface (`<body>@surface`, an#536) is the segment
[`body_surface()`](#an.stage.surface_line.body_surface) reads off its rig ([`SURFACE_BONES`](#an.stage.surface_line.SURFACE_BONES)) or the top of
its ink. The hold layer ([`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold)) lays items on the floor and on
bodies’ surfaces with these; they live here so that other measurements of
standing (the support and skate checks of an#519, [`an.stage.support`](an.stage.support.html.md#module-an.stage.support))
use the same lines, the same segment, the same normal and the same sign.

```pycon
>>> floor = ground_line(100.0)
>>> above((1, 0, 0, 1, 0, 0), [(0.0, 90.0)], floor)  # 10 px above the floor
10.0
>>> lift((1, 0, 0, 1, 0.0, 0.0), floor, 10.0)[4:]  # moved down onto it
(0.0, 10.0)
```

### Module Attributes

| [`SURFACE_BONES`](#an.stage.surface_line.SURFACE_BONES)   | The bones a body declares its supporting surface by (an#536), its two ends in the art's terms (left, right): what `<body>@surface` lays an item on.   |
|------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Line`](#an.stage.surface_line.Line)            | a point on it and its unit direction, turned so that its normal `(-dy, dx)` points DOWN the screen (into the support).                                |
| [`Segment`](#an.stage.surface_line.Segment)         | its two ends.                                                                                                                                         |

### Functions

| [`ground_line`](#an.stage.surface_line.ground_line)(ground)                          | The level floor at stage `y` `ground`: its normal points down.                                                                                                                                                                                                                                                           |
|-----------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`line_through`](#an.stage.surface_line.line_through)(a, b)                           | The support line through `a` and `b`, whichever end is named first.                                                                                                                                                                                                                                                      |
| [`lowest_on`](#an.stage.surface_line.lowest_on)(m, points, line)                   | The lowest of `points` under `m` against `line` (the farthest along its normal, into it; the first of equals), and how far above the line it is (negative: sunk into it).                                                                                                                                                |
| [`above`](#an.stage.surface_line.above)(m, corners, line)                      | How far the lowest of `corners` under `m` is above `line`, along its normal (negative: sunk into it).                                                                                                                                                                                                                    |
| [`lift`](#an.stage.surface_line.lift)(m, line, distance)                      | `m` moved `distance` along `line`'s normal (down onto it when positive).                                                                                                                                                                                                                                                 |
| [`body_surface`](#an.stage.surface_line.body_surface)(doc, nodes, mall, \*, rig, ...) | `<body>@surface`'s segment (an#536): its two ends in node `frame`'s own coordinates (default: `node`'s), from the rig's [`SURFACE_BONES`](#an.stage.surface_line.SURFACE_BONES) when it declares them, else the top edge of `node`'s ink, mapped by `to_frame` (`node`'s frame in `frame`'s; none: they are one). |

### an.stage.surface_line.Line

a point on it and its unit direction, turned so that its
normal `(-dy, dx)` points DOWN the screen (into the support).

* **Type:**
  A support line

alias of [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.surface_line.SURFACE_BONES *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= ('surface_l', 'surface_r')*

The bones a body declares its supporting surface by (an#536), its two ends
in the art’s terms (left, right): what `<body>@surface` lays an item on.
Undeclared, the surface is the top edge of the part’s ink.

### an.stage.surface_line.Segment

its two ends.

* **Type:**
  A bounded surface

alias of [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.surface_line.above(m, corners, line)

How far the lowest of `corners` under `m` is above `line`, along
its normal (negative: sunk into it). On the ground, `ground - lowest`.

```pycon
>>> square = [(0.0, 0.0), (2.0, 0.0), (0.0, 2.0), (2.0, 2.0)]
>>> above((1, 0, 0, 1, 0, 0), square, ground_line(5.0))
3.0
```

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.stage.surface_line.body_surface(doc, nodes, mall, , rig, entity, node, frame=None, to_frame=None)

`<body>@surface`’s segment (an#536): its two ends in node `frame`’s
own coordinates (default: `node`’s), from the rig’s [`SURFACE_BONES`](#an.stage.surface_line.SURFACE_BONES)
when it declares them, else the top edge of `node`’s ink, mapped by
`to_frame` (`node`’s frame in `frame`’s; none: they are one). Returns
why, instead, when the rig names it wrongly.

```pycon
>>> from an.stage.serialize import NodeJSON, VisualJSON
>>> art = {"crate": NodeJSON(name="crate", visual=VisualJSON(width=10, height=4))}
>>> body_surface(None, art, None, rig=None, entity="crate", node="crate")
((-5.0, -2.0), (5.0, -2.0))
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]] | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.stage.surface_line.ground_line(ground)

The level floor at stage `y` `ground`: its normal points down.

```pycon
>>> ground_line(5.0)
((0.0, 5.0), (1.0, 0.0))
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.surface_line.lift(m, line, distance)

`m` moved `distance` along `line`’s normal (down onto it when positive).

```pycon
>>> lift((1, 0, 0, 1, 2.0, 3.0), ground_line(10.0), 4.0)[4:]
(2.0, 7.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.stage.surface_line.line_through(a, b)

The support line through `a` and `b`, whichever end is named first.

```pycon
>>> line_through((10.0, 5.0), (0.0, 5.0))
((10.0, 5.0), (1.0, 0.0))
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

### an.stage.surface_line.lowest_on(m, points, line)

The lowest of `points` under `m` against `line` (the farthest
along its normal, into it; the first of equals), and how far above the
line it is (negative: sunk into it).

```pycon
>>> lowest_on((1, 0, 0, 1, 0, 0), [(0.0, 0.0), (2.0, 3.0)], ground_line(5.0))
((2.0, 3.0), 2.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)], [`float`](https://docs.python.org/3/builtins/functions.html#float)]
