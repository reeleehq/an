# an.assemble

Film assembly: rendered shots → one film, with transitions and a sound layer.

Every shot renders in isolation (`an.render`); this module decides how the
shots meet and what is heard over them. It runs only when a scene asks for it
— a non-`cut` [`Transition`](an.ir.schema.md#an.ir.schema.Transition) or any
[`SoundCue`](an.ir.schema.md#an.ir.schema.SoundCue) — so a scene with neither takes the old
`_ffmpeg_concat` path, byte for byte ([`needs_assembly()`](#an.assemble.needs_assembly)).

**Where each part happens, and why there.**

- *Picture*: transitions are composed in the FRAME STAGE, on the per-shot PNGs,
  in exact integer arithmetic, and the film is muxed ONCE by the same
  `_ffmpeg_mux` every shot uses. Composing in ffmpeg (`xfade`) would decode
  already-encoded shots and re-encode them — a second generation of x264 loss
  on every frame of the film, not just the transition — and would retire the
  render pipeline’s “ffmpeg never touches a frame” clause. A frame no
  transition touches is copied byte for byte: Chromium’s own PNG.
- *Sound*: the film’s audio is rebuilt from SOURCES — every dialogue line’s
  cached WAV and every cue’s asset, placed in film time — in one ffmpeg mix,
  then muxed onto the picture with `-c:v copy`. Mixing onto the shots’
  already-encoded AAC would be a second audio generation for the dialogue.

**The timeline is frame-exact.** Shot `i` occupies `frame_count(duration,
fps)` frames (the renderer’s own rule) starting at film frame
`FilmTimeline.starts` `[i]`; audio is placed at `start / fps` plus
its shot-local time, so a line stays on the frames it was lip-synced to
whatever the transitions do.

```pycon
>>> from an.ir.schema import Shot, Transition
>>> tl = film_timeline(
...     [Shot(id="a", duration=2.0),
...      Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5))],
...     fps=10,
... )
>>> tl.starts, tl.total_frames   # b starts 5 frames early: the film is 0.5 s shorter
((0, 15), 35)
```

### Functions

| [`assemble_film`](#an.assemble.assemble_film)(scene, shot_results, output, ...)   | Assemble rendered shots into `output`: the picture from the shots' frames (transitions composed in), muxed once, then the mix.      |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| [`duck_gain`](#an.assemble.duck_gain)(t, spans, \*, duck_db, attack, release) | The linear gain a ducked cue plays at, at film time `t` — the spec the ffmpeg expressions (`_duck_expressions()`) are written from. |
| [`film_duration`](#an.assemble.film_duration)(scene, \*[, fps])                   | Seconds the delivered film runs: the shots' durations, minus each dissolve's overlap.                                               |
| [`film_timeline`](#an.assemble.film_timeline)(shots, \*, fps)                     | Lay `shots` end to end, overlapping each dissolve.                                                                                  |
| [`needs_assembly`](#an.assemble.needs_assembly)(scene, \*[, fps])                  | True when the scene asks for anything beyond hard cuts and shot audio.                                                              |
| [`transition_problems`](#an.assemble.transition_problems)(shots, fps)                   | Every reason these shots' transitions cannot be assembled, as `(shot index, message)`.                                              |

### Classes

| [`FilmTimeline`](#an.assemble.FilmTimeline)(fps, frames, starts, ...)   | Where each shot's frames land in the film, and what blends them.   |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------|

### Exceptions

| [`AssemblyError`](#an.assemble.AssemblyError)   | The shots cannot be assembled as the scene asks.   |
|------------------------------------------------------------------|----------------------------------------------------|

### *exception* an.assemble.AssemblyError

Bases: `RuntimeError`

The shots cannot be assembled as the scene asks. Carries the fix.

### *class* an.assemble.FilmTimeline(fps, frames, starts, dissolve_in, fade_in, fade_out, fade_in_color, fade_out_color, total_frames)

Bases: `object`

Where each shot’s frames land in the film, and what blends them.

`dissolve_in[i]` — frames shot `i` overlaps the previous shot by.
`fade_in[i]` — frames at shot `i`’s head that fade up from a colour.
`fade_out[i]` — frames at shot `i`’s tail that fade to a colour (the
NEXT shot’s fade colour).

#### end_seconds(i)

Film time just after shot `i`’s last frame.

* **Return type:**
  `float`

#### start_seconds(i)

Film time of shot `i`’s first frame.

* **Return type:**
  `float`

### an.assemble.assemble_film(scene, shot_results, output, , fps, mall, work_dir, pix_fmt=None)

Assemble rendered shots into `output`: the picture from the shots’
frames (transitions composed in), muxed once, then the mix.

`shot_results` are the renderers’ `RenderResult`s, in timeline order;
each must carry its frames (``frame_manifest``), so a renderer that only
produces an mp4 cannot take part in an assembled film.

* **Return type:**
  `Path`

### an.assemble.duck_gain(t, spans, , duck_db, attack, release)

The linear gain a ducked cue plays at, at film time `t` — the spec the
ffmpeg expressions (`_duck_expressions()`) are written from.

Full level away from dialogue; `duck_db` down while a line plays; a linear
ramp over `attack` seconds BEFORE each line (so its first syllable is
already clear) and `release` seconds after.

* **Return type:**
  `float`

```pycon
>>> spans = [(1.0, 2.0)]
>>> [round(duck_gain(t, spans, duck_db=-20, attack=0.5, release=0.5), 3)
...  for t in (0.0, 0.75, 1.5, 2.25, 3.0)]
[1.0, 0.55, 0.1, 0.55, 1.0]
```

### an.assemble.film_duration(scene, , fps=None)

Seconds the delivered film runs: the shots’ durations, minus each
dissolve’s overlap. Exactly `sum(durations)` for a scene without one, so
every existing document’s arithmetic is unchanged.

* **Return type:**
  `float`

```pycon
>>> from an.ir.schema import SceneIR, Shot, Transition
>>> film_duration(SceneIR(timeline=[Shot(id="a", duration=2.0),
...     Shot(id="b", duration=2.0, transition=Transition(kind="dissolve", duration=0.5))]))
3.5
```

### an.assemble.film_timeline(shots, , fps)

Lay `shots` end to end, overlapping each dissolve. Raises
[`AssemblyError`](#an.assemble.AssemblyError) on any [`transition_problems()`](#an.assemble.transition_problems).

* **Return type:**
  [`FilmTimeline`](#an.assemble.FilmTimeline)

### an.assemble.needs_assembly(scene, , fps=None)

True when the scene asks for anything beyond hard cuts and shot audio.

Decided on FRAMES at the render’s rate (`fps`, default the scene’s): a
transition that rounds to zero frames asks for nothing, and must not cost a
scene its byte-identical concat.

* **Return type:**
  `bool`

```pycon
>>> from an.ir.schema import Meta, SceneIR, Shot, Transition
>>> needs_assembly(SceneIR(timeline=[Shot(id="a"), Shot(id="b")]))
False
>>> needs_assembly(SceneIR(timeline=[
...     Shot(id="a"), Shot(id="b", transition=Transition(kind="fade", duration=0.0))]))
False
```

### an.assemble.transition_problems(shots, fps)

Every reason these shots’ transitions cannot be assembled, as
`(shot index, message)`. The ONE list `an validate` reports and
[`film_timeline()`](#an.assemble.film_timeline) raises on, so the two cannot disagree.

* **Return type:**
  `list`[`tuple`[`int`, `str`]]

```pycon
>>> from an.ir.schema import Shot, Transition
>>> transition_problems([Shot(id="a", transition=Transition(kind="dissolve"))], fps=30)
[(0, "shot 'a' is the first shot, so a dissolve has nothing to dissolve from; use a fade (from a colour) or a cut")]
```
