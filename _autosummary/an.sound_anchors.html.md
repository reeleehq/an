# an.sound_anchors

Sound cues timed by the picture (an#317): `at: {when: <node>, reaches: {y: px}}` and `until:`.

A record scratch has to land when the last line of a crawl becomes readable.
Writing that second into the scene means solving the crawl’s geometry outside
`an`, and every layout change moves the picture away from the sound. Here the
cue names the event instead, and [`resolve_cue_anchors()`](#an.sound_anchors.resolve_cue_anchors) finds the second
when the film is laid out:

- `at: {when: crawl/line_7, reaches: {y: 840}}` — the first instant the
  node’s on-screen centre crosses that frame row (or `x` column), from the
  very document the stage renders (`compiled_document`), through the camera,
  parallax and a crawl’s tilt ([`an.stage.timeline.screen_position()`](an.stage.timeline.html.md#an.stage.timeline.screen_position)),
  sampled at every film frame and interpolated between the two that straddle
  it; plus `offset`;
- `until: {cue: scratch, offset: 0.12}` — the cue ends at that cue’s start
  plus `offset` (its `duration` is derived).

It runs on the in-memory settled copy of the scene (as the measured shot
lengths do, [`an.measurements`](an.measurements.html.md#module-an.measurements)): `scene.md` keeps the anchor, never the
second. Each resolved cue is reported as an `info` finding — “scratch at
33.03 s (crawl/line_7 reached y=840)” — which the render report records. An
anchor that cannot be resolved (no such node, never reached, a shot no stage
draws) refuses before any browser launches.

### Functions

| [`resolve_cue_anchors`](#an.sound_anchors.resolve_cue_anchors)(scene, ctx, renderers, ...)   | `scene` (a copy) with every anchored `at` resolved to seconds and every `until` to a duration.   |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|

### Exceptions

| [`SoundAnchorError`](#an.sound_anchors.SoundAnchorError)   | A cue's anchor cannot be resolved: the message says which and why.   |
|---------------------------------------------------------------------|----------------------------------------------------------------------|

### *exception* an.sound_anchors.SoundAnchorError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A cue’s anchor cannot be resolved: the message says which and why.

### an.sound_anchors.resolve_cue_anchors(scene, ctx, renderers, , film_starts)

`scene` (a copy) with every anchored `at` resolved to seconds and every `until` to a duration.

ctx: the render context the shots are compiled under
renderers: each shot’s renderer, in timeline order
film_starts: each shot’s start in film time (a `meta.sounds` anchor’s

> shot-local second is moved there)
* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`SceneIR`](an.ir.schema.html.md#an.ir.schema.SceneIR), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Finding`](an.verify.html.md#an.verify.Finding)]]
