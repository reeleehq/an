# an.probe

`an probe`: a shot’s frame at chosen instants, through the very path `render` draws it (an#347).

Looking at one moment of a shot used to mean a whole render, or a throwaway
script that staged the scene its own way and drew something else. A probe
prepares the shot exactly as [`an.render.render()`](an.render.html.md#an.render.render) does (`_prepare_shots`:
settled length, burned captions, the style pack, the resolved knobs), then asks
the shot’s own renderer for the frames showing at the instants given:

- a frame-stage renderer (the stage engine, the cut-out renderer) opens the
  session `render` opens and captures through
  [`an.engines.capture.capture_frames()`](an.engines.capture.html.md#an.engines.capture.capture_frames) — supersample, frame clock and
  > canvas readback included — only the frames asked for
  > ([`an.engines.frame_stage.FrameStageRenderer.probe_frames()`](an.engines.frame_stage.html.md#an.engines.frame_stage.FrameStageRenderer.probe_frames));
- a renderer that owns its clock (Manim) serves the frames from the picture a
  render stored, or refuses with the remedy;
- any other renderer refuses: it has no `probe_frames`.

Speech plays as the last render (or synthesis) stamped it: a probe never
synthesises a line. Nothing is cached, written to the shot cache or archived.

**Rights.** A frame showing material that is not publishable (`an credits`
for the shot says private or unknown) is refused at a path inside a git work
tree that does not ignore it; the default folder, `artifacts/probes/`, is
ignored by `an init` and added to an older project’s `.gitignore`.

### Functions

| [`frame`](#an.probe.frame)(project, shot, t, \*\*kwargs)             | PNG bytes of shot `shot`'s film frame at `t` seconds (see [`frames()`](#an.probe.frames)).   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`frames`](#an.probe.frames)(project, shot, times, \*[, supersample]) | PNG bytes of shot `shot`'s film frame at each of `times` (seconds into the shot).                                       |
| [`probe`](#an.probe.probe)(project_dir, shot, at, \*[, out, ...])    | Write shot `shot`'s frames at `at` to one PNG (a grid for several instants).                                            |

### Exceptions

| [`ProbeError`](#an.probe.ProbeError)   | A probe cannot draw what was asked: the message says why and what to do.   |
|---------------------------------------------------------------|----------------------------------------------------------------------------|

### *exception* an.probe.ProbeError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A probe cannot draw what was asked: the message says why and what to do.

### an.probe.frame(project, shot, t, \*\*kwargs)

PNG bytes of shot `shot`’s film frame at `t` seconds (see [`frames()`](#an.probe.frames)).

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.probe.frames(project, shot, times, , supersample=1)

PNG bytes of shot `shot`’s film frame at each of `times` (seconds into the shot).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

project: a loaded [`Project`](an.project.html.md#an.project.Project) or its folder
supersample: as `an render --supersample` (the frame is the film’s only

> if it matches the render’s)

### an.probe.probe(project_dir, shot, at, , out=None, columns=None, supersample=1, allow_private_here=False)

Write shot `shot`’s frames at `at` to one PNG (a grid for several instants).

out: the PNG to write (default `<project>/artifacts/probes/<shot>@<t>.png`)
columns: cells per row of a grid (default: a square grid)
allow_private_here: write not-publishable frames inside a git work tree

> that does not ignore the path
* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
