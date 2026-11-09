# an.stage.surface_line

Surface lines: what a thing stands on, as a line on the stage (an#519).

A *support line* is a point on it and its unit direction, turned so that its
normal `(-dy, dx)` points DOWN the screen, into the support. The floor is a
level line ([`ground_line()`](#an.stage.surface_line.ground_line)); a body’s top edge or a stage segment is the
line through its two ends ([`line_through()`](#an.stage.surface_line.line_through)). Measured against one:

- [`above()`](#an.stage.surface_line.above): how far the lowest of some points (a part’s corners or ink,
  under its world matrix) is above the line, along its normal; negative when
  sunk into it.
- [`lift()`](#an.stage.surface_line.lift): a world matrix moved along the line’s normal by such a
  distance, which is how an item is laid exactly on what carries it.

The hold layer ([`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold)) lays items on the floor and on bodies’
surfaces with these; they live here so that other measurements of standing
(the support and skate checks of an#519) use the same lines, the same normal
and the same sign.

```pycon
>>> floor = ground_line(100.0)
>>> above((1, 0, 0, 1, 0, 0), [(0.0, 90.0)], floor)  # 10 px above the floor
10.0
>>> lift((1, 0, 0, 1, 0.0, 0.0), floor, 10.0)[4:]  # moved down onto it
(0.0, 10.0)
```

### Module Attributes

| [`Line`](#an.stage.surface_line.Line)   | a point on it and its unit direction, turned so that its normal `(-dy, dx)` points DOWN the screen (into the support).   |
|---------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`ground_line`](#an.stage.surface_line.ground_line)(ground)     | The level floor at stage `y` `ground`: its normal points down.                                        |
|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| [`line_through`](#an.stage.surface_line.line_through)(a, b)      | The support line through `a` and `b`, whichever end is named first.                                   |
| [`above`](#an.stage.surface_line.above)(m, corners, line) | How far the lowest of `corners` under `m` is above `line`, along its normal (negative: sunk into it). |
| [`lift`](#an.stage.surface_line.lift)(m, line, distance) | `m` moved `distance` along `line`'s normal (down onto it when positive).                              |

### an.stage.surface_line.Line

a point on it and its unit direction, turned so that its
normal `(-dy, dx)` points DOWN the screen (into the support).

* **Type:**
  A support line

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
