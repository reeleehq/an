# an.adapters.cutout.gaze

Ambient saccades for a cutout rig’s pupils: a seeded generator (an#99, epic #9 Wave 6).

Pure Python, no renderer. Given an entity’s name, a shot’s duration and its
frame rate, produce a **step** track of pupil offsets — where the eyes rest,
and when they jump — that the face solver adds onto the pupil nodes’ `x` /
`y` beside any authored gaze. Steps, not tweens: at 24 fps a frame is
41.7 ms and a small saccade is 20–200 ms, so a jump between two frames is the
honest rendering (the way the compiled blink squash samples at frame times).

The statistics are **design values**, labelled so: the canonical source
(“Eyes Alive”, Lee, Badler & Badler, SIGGRAPH 2002) was unreachable when this
was designed, and nothing was transcribed from memory. Fixation lengths are
right-skewed with a ~200 ms peak and a long tail, so they are drawn from a
gamma clipped to `[FIXATION_MIN_S, FIXATION_MAX_S]`; amplitudes are mostly
small with a rare large jump and a horizontal bias; and a jump above
`BLINK_COUPLED_AMPLITUDE` is moved to the centre of the nearest blink window
within `BLINK_COUPLING_WINDOW_S` when one exists, because gaze-evoked blinks
hide the pop.

Seeding follows the blink pattern — a pure function of the entity name — so
renaming a character re-seeds its saccades (the recorded blink hazard); the
seed is stamped into the compiled scene’s `meta` beside `blink_phases`.
Integer seeding of [`random.Random`](https://docs.python.org/3/library/random.html#random.Random) is version-stable.

```pycon
>>> track = saccade_track("gale", duration=2.0, fps=24)
>>> track[0].time, all(t.time <= 2.0 for t in track)
(0.0, True)
>>> track == saccade_track("gale", duration=2.0, fps=24)  # deterministic
True
>>> track != saccade_track("nora", duration=2.0, fps=24)  # per entity
True
```

### Module Attributes

| [`GAZE_SALT`](#an.adapters.cutout.gaze.GAZE_SALT)   | XOR'd into the entity-name hash so saccades and blinks never share a seed.   |
|--------------------------------------------------------------|------------------------------------------------------------------------------|

### Functions

| [`gaze_seed`](#an.adapters.cutout.gaze.gaze_seed)(entity_id)                               | The generator's seed for an entity — a pure function of its name.   |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`saccade_track`](#an.adapters.cutout.gaze.saccade_track)(entity_id, \*, duration, fps[, ...]) | Step keyframes on frame times, seeded by `entity_id`.               |

### Classes

| [`GazeStep`](#an.adapters.cutout.gaze.GazeStep)(time, x, y)   | The pupils rest at `(x, y)` (axis units) from `time` on.   |
|-------------------------------------------------------------------------|------------------------------------------------------------|

### an.adapters.cutout.gaze.GAZE_SALT *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 27182*

XOR’d into the entity-name hash so saccades and blinks never share a seed.

### *class* an.adapters.cutout.gaze.GazeStep(time, x, y)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The pupils rest at `(x, y)` (axis units) from `time` on.

### an.adapters.cutout.gaze.gaze_seed(entity_id)

The generator’s seed for an entity — a pure function of its name.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> gaze_seed("gale") == gaze_seed("gale") and gaze_seed("gale") != gaze_seed("nora")
True
```

### an.adapters.cutout.gaze.saccade_track(entity_id, , duration, fps, blink_windows=None, amplitude=1.0)

Step keyframes on frame times, seeded by `entity_id`.

`amplitude` scales every jump (0 = the eyes hold centre; the design
values assume 1). `blink_windows` are the entity’s compiled blink
windows, for the coupling rule.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`GazeStep`](#an.adapters.cutout.gaze.GazeStep)]
