# an.assemble

Film assembly: rendered shots → one film, with transitions and a sound layer.

Every shot renders in isolation (`an.render`); this module decides how the
shots meet and what is heard over them. It runs only when a scene asks for it
— a non-`cut` [`Transition`](an.ir.schema.md#an.ir.schema.Transition) or any
[`SoundCue`](an.ir.schema.md#an.ir.schema.SoundCue) — so a scene with neither takes the old
`_ffmpeg_concat` path, byte for byte ([`needs_assembly()`](#an.assemble.needs_assembly)).

**Where each part happens, and why there.**

- *Picture*: transitions are composed in the FRAME STAGE, on the per-shot PNGs,
  in exact integer arithmetic, and encoded by the same
  `an.media.mp4.mux_frames` every shot uses. Composing in ffmpeg (`xfade`)
  would decode already-encoded shots and re-encode them — a second generation
  of x264 loss on every frame of the film, not just the transition — and would
  retire the render pipeline’s “ffmpeg never touches a frame” clause.
- *The picture is a stream-copy concat of SEGMENTS* (an#260), each encoded
  once from PNGs: a shot no transition touches is its own mp4’s video stream,
  copied; a shot a transition touches contributes the encoded span between its
  windows (its *body*) plus the PNGs inside them; each run of composed frames
  is encoded on its own. So a reused shot needs its mp4 (and, at a transition,
  its body and window PNGs, a few dozen frames) — never every frame it has
  ([`shot_windows()`](#an.assemble.shot_windows), [`ShotParts`](#an.assemble.ShotParts)). The film’s frame `i` is at
  `i / fps` and decodes to exactly what its segment decodes to (measured,
  an#260; [`MIN_SEGMENT_FRAMES`](#an.assemble.MIN_SEGMENT_FRAMES) is why no segment is shorter than three).
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

### Module Attributes

| [`MIN_SEGMENT_FRAMES`](#an.assemble.MIN_SEGMENT_FRAMES)   | The fewest frames a segment of a MULTI-segment picture may have.   |
|-----------------------------------------------------------------------|--------------------------------------------------------------------|

### Functions

| [`assemble_film`](#an.assemble.assemble_film)(scene, shot_results, output, ...)   | Assemble rendered shots into `output`: the picture as a concat of segments (transitions composed in), then the mix.                                                             |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`duck_gain`](#an.assemble.duck_gain)(t, spans, \*, duck_db, attack, release) | The linear gain a ducked cue plays at, at film time `t` — the spec the ffmpeg expressions (`_duck_expressions()`) are written from.                                             |
| [`film_duration`](#an.assemble.film_duration)(scene, \*[, fps])                   | Seconds the delivered film runs: the shots' durations, minus each dissolve's overlap.                                                                                           |
| [`film_timeline`](#an.assemble.film_timeline)(shots, \*, fps)                     | Lay `shots` end to end, overlapping each dissolve.                                                                                                                              |
| [`needs_assembly`](#an.assemble.needs_assembly)(scene, \*[, fps])                  | True when the scene asks for anything beyond hard cuts and shot audio.                                                                                                          |
| [`picture_segments`](#an.assemble.picture_segments)(timeline, windows)               | The film's picture as segments, in film order.                                                                                                                                  |
| [`shot_parts`](#an.assemble.shot_parts)(frames, window, \*, fps, work_dir)     | A rendered shot's [`ShotParts`](#an.assemble.ShotParts) for `window`, from its frames.                                                                     |
| [`shot_windows`](#an.assemble.shot_windows)(timeline, \*[, min_segment_frames])  | Each shot's [`ShotWindow`](#an.assemble.ShotWindow): the frames its transitions touch, widened until every segment of the picture has `min_segment_frames`. |
| [`transition_problems`](#an.assemble.transition_problems)(shots, fps)                   | Every reason these shots' transitions cannot be assembled, as `(shot index, message)`.                                                                                          |

### Classes

| [`FilmTimeline`](#an.assemble.FilmTimeline)(fps, frames, starts, ...)   | Where each shot's frames land in the film, and what blends them.                                                                                                                                                                                       |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`Segment`](#an.assemble.Segment)(kind, shot, start, stop)         | One independently encoded run of the film's picture, film frames `[start, stop)`: a whole shot's own stream (`"shot"`), a shot's encoded body (`"body"`), or a run of PNGs composed here (`"frames"`).                                                 |
| [`ShotParts`](#an.assemble.ShotParts)(window, frames[, body])        | What a film takes from a shot its transitions touch: the PNGs inside its [`ShotWindow`](#an.assemble.ShotWindow) (`frames`: shot-local index -> path) and its body, encoded once (`body`; `None` when the window covers the shot). |
| [`ShotWindow`](#an.assemble.ShotWindow)(frames[, head, tail])         | Which of one shot's `frames` its film needs as PNGs: the first `head` and the last `tail`.                                                                                                                                                             |

### Exceptions

| [`AssemblyError`](#an.assemble.AssemblyError)   | The shots cannot be assembled as the scene asks.   |
|------------------------------------------------------------------|----------------------------------------------------|

### *exception* an.assemble.AssemblyError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The shots cannot be assembled as the scene asks. Carries the fix.

### *class* an.assemble.FilmTimeline(fps, frames, starts, dissolve_in, fade_in, fade_out, fade_in_color, fade_out_color, total_frames)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Where each shot’s frames land in the film, and what blends them.

`dissolve_in[i]` — frames shot `i` overlaps the previous shot by.
`fade_in[i]` — frames at shot `i`’s head that fade up from a colour.
`fade_out[i]` — frames at shot `i`’s tail that fade to a colour (the
NEXT shot’s fade colour).

#### end_seconds(i)

Film time just after shot `i`’s last frame.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

#### start_seconds(i)

Film time of shot `i`’s first frame.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

### an.assemble.MIN_SEGMENT_FRAMES *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 3*

The fewest frames a segment of a MULTI-segment picture may have. Measured on
ffmpeg 9.0.1 / libx264 with the pinned argv (an#260): a stream of three or
more frames carries a two-frame B-pyramid decode delay (its first DTS is two
frames before its first PTS) whatever its content, and a stream of one or
two frames carries none. The concat demuxer offsets every file alike, so a
delay-free segment between two delayed ones leaves the DTS going backwards;
the muxer patches that with one-tick packets, and a constant-rate decode of
the film then shows a frame twice. [`shot_windows()`](#an.assemble.shot_windows) widens every short
run instead, so each segment of a multi-segment picture has the delay.

### *class* an.assemble.Segment(kind, shot, start, stop)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One independently encoded run of the film’s picture, film frames
`[start, stop)`: a whole shot’s own stream (`"shot"`), a shot’s
encoded body (`"body"`), or a run of PNGs composed here (`"frames"`).

### *class* an.assemble.ShotParts(window, frames, body=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a film takes from a shot its transitions touch: the PNGs inside
its [`ShotWindow`](#an.assemble.ShotWindow) (`frames`: shot-local index -> path) and its
body, encoded once (`body`; `None` when the window covers the shot).

### *class* an.assemble.ShotWindow(frames, head=0, tail=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Which of one shot’s `frames` its film needs as PNGs: the first
`head` and the last `tail`.

Between them is the shot’s *body*, which the film takes as one encoded
span. A shot with an empty window (`whole`) is taken as its own
mp4’s video stream, so it needs no frame at all.

```pycon
>>> w = ShotWindow(frames=10, head=0, tail=4)
>>> w.whole, w.body, w.png_indices
(False, (0, 6), (6, 7, 8, 9))
```

#### *property* body *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]*

the shot-local frames taken as one encoded span.

* **Type:**
  `(first, stop)`

#### *property* png_indices *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[int](https://docs.python.org/3/builtins/functions.html#int), ...]*

The shot-local frames the film needs as PNGs.

### an.assemble.assemble_film(scene, shot_results, output, , fps, mall, work_dir, pix_fmt=None, parts=None)

Assemble rendered shots into `output`: the picture as a concat of
segments (transitions composed in), then the mix.

`shot_results` are the renderers’ `RenderResult`s, in timeline order. A
shot no transition touches contributes its mp4 alone. A shot one touches
needs its :class:`ShotParts` for its [`shot_windows()`](#an.assemble.shot_windows) window: pass them
in `parts` (a reused shot’s come from the shot cache), or the shot’s
`frame_manifest` must hold its frames, from which they are built.

**Why not one mux of every frame**, as before an#260: the picture depended
on every frame of every shot, so a film with a dissolve or a music bed
could reuse no shot without caching all of its PNGs — hundreds of MB per
1080p shot. The segment concat puts frame `i` at `i / fps` exactly as
the one mux did (measured, an#260), and each frame decodes to exactly what
its own segment decodes to.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.assemble.duck_gain(t, spans, , duck_db, attack, release)

The linear gain a ducked cue plays at, at film time `t` — the spec the
ffmpeg expressions (`_duck_expressions()`) are written from.

Full level away from dialogue; `duck_db` down while a line plays; a linear
ramp over `attack` seconds BEFORE each line (so its first syllable is
already clear) and `release` seconds after.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

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
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

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
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> from an.ir.schema import Meta, SceneIR, Shot, Transition
>>> needs_assembly(SceneIR(timeline=[Shot(id="a"), Shot(id="b")]))
False
>>> needs_assembly(SceneIR(timeline=[
...     Shot(id="a"), Shot(id="b", transition=Transition(kind="fade", duration=0.0))]))
False
```

### an.assemble.picture_segments(timeline, windows)

The film’s picture as segments, in film order.

A film frame is part of a shot’s body when exactly one shot shows it and
that frame is outside the shot’s window; every other frame (a blend, a
fade, or a frame a window was widened over) is composed from PNGs.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Segment`](#an.assemble.Segment)]

```pycon
>>> from an.ir.schema import Shot, Transition
>>> tl = film_timeline([Shot(id="a", duration=1.0), Shot(id="b", duration=1.0,
...     transition=Transition(kind="dissolve", duration=0.4))], fps=10)
>>> [(s.kind, s.shot, s.start, s.stop) for s in picture_segments(tl, shot_windows(tl))]
[('body', 0, 0, 6), ('frames', None, 6, 10), ('body', 1, 10, 16)]
```

### an.assemble.shot_parts(frames, window, , fps, work_dir, pix_fmt=None)

A rendered shot’s [`ShotParts`](#an.assemble.ShotParts) for `window`, from its frames.

The body is encoded by `an.media.mp4.mux_frames` — the shot mux’s own
encoder and argv — from the body’s PNGs, renumbered from zero in
`work_dir`. The window’s PNGs are referenced where they are.

* **Return type:**
  [`ShotParts`](#an.assemble.ShotParts)

### an.assemble.shot_windows(timeline, , min_segment_frames=3)

Each shot’s [`ShotWindow`](#an.assemble.ShotWindow): the frames its transitions touch,
widened until every segment of the picture has `min_segment_frames`.

A pure function of the timeline, so the render loop, the shot cache and
the garbage collector all agree on what a shot’s film needs from it. A
picture of one segment has no minimum (there is nothing to concatenate).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`ShotWindow`](#an.assemble.ShotWindow), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> from an.ir.schema import Shot, Transition
>>> d = Transition(kind="dissolve", duration=0.1)   # one frame at 10 fps
>>> tl = film_timeline([Shot(id="a", duration=1.0), Shot(id="b", duration=1.0,
...     transition=d)], fps=10)
>>> [(w.head, w.tail) for w in shot_windows(tl)]   # the 1-frame run, widened to 3
[(0, 1), (3, 0)]
```

### an.assemble.transition_problems(shots, fps)

Every reason these shots’ transitions cannot be assembled, as
`(shot index, message)`. The ONE list `an validate` reports and
[`film_timeline()`](#an.assemble.film_timeline) raises on, so the two cannot disagree.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

```pycon
>>> from an.ir.schema import Shot, Transition
>>> transition_problems([Shot(id="a", transition=Transition(kind="dissolve"))], fps=30)
[(0, "shot 'a' is the first shot, so a dissolve has nothing to dissolve from; use a fade (from a colour) or a cut")]
```
