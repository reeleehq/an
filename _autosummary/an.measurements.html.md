# an.measurements

Measured durations: shots whose renderer, not their author, decides their length.

A whole-shot renderer that **owns its clock** (Manim: only the scene file’s own
`play` and `wait` calls fix its length) implements `measure_duration`
(`ClockOwningRenderer`). Its answer is DERIVED data:

- it lives in a derived store keyed by the shot’s content (the renderer’s
  `measurements` store), never in `scene.md` or `ir/scene.json` — a render
  never rewrites what the author wrote (an#279 review, H1);
- [`settle_durations()`](#an.measurements.settle_durations) applies it IN MEMORY, to a copy of the scene, before
  anything reads `shot.duration` — the film timeline, captions, the sound
  layer, the cache keys — so the film’s layout is a pure function of the IR
  and the measurements;
- `an sync --accept-measured` ([`accept_measured()`](#an.measurements.accept_measured)) takes it into the
  authored scene on request, patching each shot’s `duration:` line in place.

This is how core study §4.2’s “written back into the IR” is resolved: the IR the
render LAYS OUT holds the measured length; the IR the author OWNS is untouched
unless they accept it.

**Narration longer than the picture is never cut silently.** A shot’s settled
length is `max(measured, end of its dialogue)`: the renderer holds its last
frame for the difference, and a warning says so — or, under `strict`
(`--strict-assets`, which already refuses stand-ins), the render is refused.

```pycon
>>> declared_duration(Shot(id="a", renderer="manim")) is None   # the schema's placeholder
True
>>> declared_duration(Shot(id="a", renderer="manim", duration=3.0))
3.0
```

### Module Attributes

| [`UNMEASURED_FIX`](#an.measurements.UNMEASURED_FIX)   | What the finding of a clock-owned shot never measured suggests; also what marks it ([`is_unmeasured()`](#an.measurements.is_unmeasured)): its length is a placeholder.   |
|-------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`accept_measured`](#an.measurements.accept_measured)(project_dir, \*[, scene_file])   | Write each clock-owned shot's MEASURED length into the authored scene.                                                                                                                |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`clock_owner_for`](#an.measurements.clock_owner_for)(shot[, registry])                | The registered renderer of `shot` if it owns its clock, else `None`.                                                                                                                  |
| [`declared_duration`](#an.measurements.declared_duration)(shot)                          | The duration the AUTHOR wrote, or `None`.                                                                                                                                             |
| [`is_unmeasured`](#an.measurements.is_unmeasured)(finding)                           | Whether `finding` (one of [`settle_durations()`](#an.measurements.settle_durations)') says a shot's length is a placeholder: its renderer decides it and never measured it. |
| [`settle_durations`](#an.measurements.settle_durations)(scene, ctx, \*, render[, ...])  | A COPY of `scene` whose clock-owned shots carry their settled length, and the findings about them.                                                                                    |
| [`warn_findings`](#an.measurements.warn_findings)(findings, \*[, stacklevel])        | Warn each finding as a [`ShotFindingWarning`](#an.measurements.ShotFindingWarning) (`location: …`).                                                                           |

### Exceptions

| [`MeasurementError`](#an.measurements.MeasurementError)      | A measured shot cannot be laid out as asked (e.g. a hold under strict mode).                                                              |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| [`ShotFindingWarning`](#an.measurements.ShotFindingWarning)    | A finding about a shot, warned by `an render` — located by `file:line` when the thing to fix is an opaque source (a Manim scene file).    |
| [`UnmeasuredLengthError`](#an.measurements.UnmeasuredLengthError) | A clock-owned shot was never measured, so its length (and every later shot's start) is a placeholder, and the caller did not accept that. |

### *exception* an.measurements.MeasurementError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A measured shot cannot be laid out as asked (e.g. a hold under strict mode).

### *exception* an.measurements.ShotFindingWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

A finding about a shot, warned by `an render` — located by `file:line`
when the thing to fix is an opaque source (a Manim scene file).

### an.measurements.UNMEASURED_FIX *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'render the project once (\`an render\`) so its renderer measures the shot'*

What the finding of a clock-owned shot never measured suggests; also what
marks it ([`is_unmeasured()`](#an.measurements.is_unmeasured)): its length is a placeholder.

### *exception* an.measurements.UnmeasuredLengthError

Bases: [`MeasurementError`](#an.measurements.MeasurementError)

A clock-owned shot was never measured, so its length (and every later
shot’s start) is a placeholder, and the caller did not accept that.

### an.measurements.accept_measured(project_dir, , scene_file='scene.md')

Write each clock-owned shot’s MEASURED length into the authored scene.

Only stored measurements (render first); only shots whose scene duration
differs. Each `duration:` line is patched in place through
[`an.stores.scenes.ScenesStore.patch_shot_durations()`](an.stores.scenes.html.md#an.stores.scenes.ScenesStore.patch_shot_durations), so the prose and
comments of `scene.md` are kept. Returns `{shot id: seconds}` written.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.measurements.clock_owner_for(shot, registry=None)

The registered renderer of `shot` if it owns its clock, else `None`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.measurements.declared_duration(shot)

The duration the AUTHOR wrote, or `None`.

`scene.md` fills the schema’s placeholder (`an.base.DEFAULT_DURATION`)
into a shot that writes no `duration:`, so that value reads as “not
declared” — an explicit `duration: 5` is indistinguishable from it.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.measurements.is_unmeasured(finding)

Whether `finding` (one of [`settle_durations()`](#an.measurements.settle_durations)’) says a shot’s
length is a placeholder: its renderer decides it and never measured it.

```pycon
>>> from types import SimpleNamespace as NS
>>> is_unmeasured(NS(suggested_fix=UNMEASURED_FIX)), is_unmeasured(NS(suggested_fix=None))
(True, False)
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### an.measurements.settle_durations(scene, ctx, , render, force=False, strict=False, registry=None)

A COPY of `scene` whose clock-owned shots carry their settled length,
and the findings about them. `scene` itself is never modified.

`render=False` (`an validate`) uses stored measurements only: a shot
never measured is reported as “length unknown until rendered” and judged
against nothing. `render=True` (`an render`) measures what is not
stored; `force` measures everything afresh.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Finding`](an.verify.html.md#an.verify.Finding)]]

### an.measurements.warn_findings(findings, , stacklevel=3)

Warn each finding as a [`ShotFindingWarning`](#an.measurements.ShotFindingWarning) (`location: …`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
