# an.timing.grid

The step grid: the instants a stepped tween updates its pose, as a pure rule (an#89, an#784).

A timing policy, not a renderer’s choice: every implementation of the timing
kernel that plays a stepped shot (“on twos”, `step_hz`) must put the pose
changes on the same instants, so it lives here beside the kernel and is
published in the contract as `step_grid.json` ([`an.timing.contract`](an.timing.contract.html.md#module-an.timing.contract)),
which previz’s TypeScript kernel asserts. [`an.frame_clock`](an.frame_clock.html.md#module-an.frame_clock) re-exports it
and builds the solve’s and the camera’s grids on it.

```pycon
>>> step_times(0.0, 0.25, 10)
[0.0, 0.1, 0.2, 0.25]
```

### Module Attributes

| [`STEP_GRID_EPS`](#an.timing.grid.STEP_GRID_EPS)   | A step instant this close to the end of a span is not a step of it (`0.25 s × 12 Hz` is 3 steps, not 4, whatever the float product rounds to).   |
|------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`step_times`](#an.timing.grid.step_times)(start, duration, step_hz)   | Clip-local times at which a stepped tween updates its pose (an#89).   |
|-----------------------------------------------------------------------------------------|-----------------------------------------------------------------------|

### an.timing.grid.STEP_GRID_EPS *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 1e-09*

A step instant this close to the end of a span is not a step of it
(`0.25 s × 12 Hz` is 3 steps, not 4, whatever the float product rounds to).

### an.timing.grid.step_times(start, duration, step_hz)

Clip-local times at which a stepped tween updates its pose (an#89).

The grid is SHOT-wide — multiples of `1/step_hz` on the shot’s clock,
shared by every tween in the shot — not the tween’s own: “on twos” means
every character changes pose on the same frames, so a tween starting at
0.033 s updates at the next grid point, not 0.033 s later. (Shots compile
independently, so the grid restarts at each cut.) Local 0 (the tween’s
start) and `duration` (where the end value lands) are always present, so
a tween shorter than one step is a single step to its end value.

`step_hz` must be positive: with a non-positive rate the walk below never
reaches `duration` — an infinite loop, not an error — so it is refused.

```pycon
>>> step_times(0.0, 0.3, 10)
[0.0, 0.1, 0.2, 0.3]
>>> [round(t, 3) for t in step_times(0.05, 0.3, 10)]
[0.0, 0.05, 0.15, 0.25, 0.3]
>>> step_times(0.0, 0.02, 10)
[0.0, 0.02]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]
