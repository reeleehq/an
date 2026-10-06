# an.adapters.manim_adapter

ManimRenderer — a whole-shot renderer for opaque Manim scene files (an#279).

A Manim shot names a Python scene file and a `Scene` class in it; `an` runs
that file as it is and treats the result like any other rendered shot:

```yaml
## Shot chart (manim)
```yaml shot
options: {source: bar_chart, scene: BarChartStory}
```
```

`options.source` is a key of the project’s `sources` store
(`assets/sources/bar_chart.py`); `options.scene` the class (optional when the
file defines exactly one). The shot has NO IR inside it — it is (a)-level opaque
source on the structured ↔ semantic spectrum — and gets everything around it
from the core: narration (a dialogue line with an off-screen speaker, muxed under
the picture), captions in the sidecar, sound cues, transitions, film assembly,
the shot cache.

**The files a scene reads.** The render runs in a staged copy of the WHOLE
`sources` folder (`assets/sources/` and everything under it), so a scene
imports a sibling module or loads `ImageMobject("bars/logo.png")` by a path
relative to its own file, and every one of those bytes is in both keys below.
A file read from OUTSIDE that folder — a literal absolute path, or one computed
(`Path.home() / "data.csv"`, an environment variable, a helper) — is
RECORDED as the render runs (manimkit’s `record_reads`: an audit hook in the
render’s child process, an#291) and stored with the measurement as a trace
(`read_trace()`): each file’s digest, `absent` for one looked for and
missing, and each listed folder’s names. A stored picture is reused only while
its trace still holds (`stale_reads()`), and the shot key has a `reads`
part, so editing such a file re-renders the picture and the shot, and leaving it
alone reuses both. A literal outside path is still a finding at its line: the
cache sees it now, but another machine will not have it.

**Manim owns its clock** (core study §4.2): only the file’s own `play` and
`wait` calls decide how long it runs. The renderer implements
`measure_duration` (`ClockOwningRenderer`); the
measurement is derived data, kept in the `measurements` store under the
**picture key** — what decides Manim’s own output and length: the bytes of the
sources folder, the entry file, the scene, the Manim and manimkit versions, the
quality preset and, only for a file that uses LaTeX, whether TeX is available.
Never the film’s fps or size, the encode, or this module’s code: those change
how the picture is CONFORMED, not what Manim draws. The core applies it in memory
([`an.measurements`](an.measurements.md#module-an.measurements)); the author’s scene is never rewritten.

**The picture is cached apart from the shot.** Manim’s raw video is stored by
its own sha256 (`pictures` store), named by the measurement record under the
picture key, so a change that is not to the picture —
narration, the film’s fps, the background pad, an `an` upgrade — re-conforms
and re-muxes without running Manim. The shot key ([`manim_shot_inputs()`](#an.adapters.manim_adapter.manim_shot_inputs))
is the picture key’s inputs plus the conform and encode knobs, the muxed audio
and the render path’s code; the machine is the separate environment part
([`manim_environment()`](#an.adapters.manim_adapter.manim_environment)).

**Findings** — manimkit’s layout warnings, lint and errors, a file read the
cache cannot see, a preset whose frame rate the film’s does not divide — are
[`Finding`](an.verify.md#an.verify.Finding) s located by `file:line` (`Finding.location`),
stored with the measurement (so a reused shot still reports them) and routed by
the core to `an render`’s warnings, `render_reports/<output>.json`,
`orchestrate` and `an validate`.

**Capabilities** (ADR 0002, environment subject): `env.manim` (`manim` and
`manimkit` importable) is required — absent, [`ManimNotInstalledError`](#an.adapters.manim_adapter.ManimNotInstalledError)
with the install command. `env.latex` is required only by a file that uses
LaTeX; absent, the scene renders in manimkit’s `no_latex` mode, so a LaTeX use
fails AT ITS LINE with the remedy instead of deep inside a TeX run.

```pycon
>>> spec = ManimShotSpec.from_options({"source": "chart", "scene": "Chart"})
>>> spec.source, spec.scene, spec.quality
('chart', 'Chart', None)
>>> choose_quality(fps=30, resolution=(1280, 720))
'm'
```

### Module Attributes

| [`DEFAULT_SOURCE_STORE`](#an.adapters.manim_adapter.DEFAULT_SOURCE_STORE)   | The project store a shot's `options.source` is a key of.           |
|-------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`CONTACT_SHEET_STORE`](#an.adapters.manim_adapter.CONTACT_SHEET_STORE)    | Derived, content-keyed stores (see the module docstring).          |
| [`QUALITY_PRESETS`](#an.adapters.manim_adapter.QUALITY_PRESETS)        | Manim Community Edition's presets (`-ql` … `-qk`), smallest first. |

### Functions

| [`choose_quality`](#an.adapters.manim_adapter.choose_quality)(\*, fps, resolution)   | The smallest Manim preset that is at least as tall and as fast as the film.                              |
|----------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| [`manim_environment`](#an.adapters.manim_adapter.manim_environment)()                   | The Manim render's machine: Manim's stack, ffmpeg, LaTeX, fonts, the ISA.                                |
| [`manim_shot_inputs`](#an.adapters.manim_adapter.manim_shot_inputs)(shot, ctx)          | The Manim renderer's [`ShotKeyer`](an.build.keys.md#an.build.keys.ShotKeyer). |
| [`store_source_resolver`](#an.adapters.manim_adapter.store_source_resolver)([store])        | The default resolver: `options.source` is a key of the mall's `store`.                                   |

### Classes

| [`ManimQuality`](#an.adapters.manim_adapter.ManimQuality)(letter, width, height, fps)           | One of Manim's quality presets: its letter, pixel size and frame rate.       |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`ManimRenderer`](#an.adapters.manim_adapter.ManimRenderer)(\*[, render_check, source_resolver]) | Manim Community Edition, through `manimkit`: an opaque-source shot renderer. |
| [`ManimShotSpec`](#an.adapters.manim_adapter.ManimShotSpec)(source[, scene, quality, ...])       | What a Manim shot's `options` say, checked.                                  |
| [`SourceFile`](#an.adapters.manim_adapter.SourceFile)(key, entry, closure, display)           | A scene file and its closure, as a resolver read them.                       |

### Exceptions

| [`ManimNotInstalledError`](#an.adapters.manim_adapter.ManimNotInstalledError)   | `manim` / `manimkit` are not importable (`env.manim` is absent).   |
|---------------------------------------------------------------------------|--------------------------------------------------------------------|
| [`ManimRenderError`](#an.adapters.manim_adapter.ManimRenderError)         | A Manim shot could not be rendered.                                |

### an.adapters.manim_adapter.CONTACT_SHEET_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'contact_sheets'*

Derived, content-keyed stores (see the module docstring).

### an.adapters.manim_adapter.DEFAULT_SOURCE_STORE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'sources'*

The project store a shot’s `options.source` is a key of.

### *exception* an.adapters.manim_adapter.ManimNotInstalledError

Bases: [`ManimRenderError`](#an.adapters.manim_adapter.ManimRenderError), [`ImportError`](https://docs.python.org/3/builtins/exceptions.html#ImportError)

`manim` / `manimkit` are not importable (`env.manim` is absent).

### *class* an.adapters.manim_adapter.ManimQuality(letter, width, height, fps)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One of Manim’s quality presets: its letter, pixel size and frame rate.

### *exception* an.adapters.manim_adapter.ManimRenderError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A Manim shot could not be rendered. Carries the [file:line](file:line) and the fix.

### *class* an.adapters.manim_adapter.ManimRenderer(, render_check=None, source_resolver=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Manim Community Edition, through `manimkit`: an opaque-source shot renderer.

Implements [`Renderer`](an.adapters.md#an.adapters.Renderer) and
`ClockOwningRenderer`. Seams: `render_check`
(default `manimkit.render_check()`, imported on first use) and
`source_resolver` (default: the project’s `sources` store,
[`store_source_resolver()`](#an.adapters.manim_adapter.store_source_resolver)). The shot cache keys a shot through the
REGISTERED instance’s resolver; a subclass registers its own keyer
(`register_shot_keyer(name, manim_shot_inputs, renderer_type=Sub)`).

#### measure_duration(shot, ctx, , render=True, force=False)

Manim’s length of this shot’s scene, from the `measurements` store,
or rendered now (and stored) when there is none — or when `force`.

* **Return type:**
  `DurationMeasurement` | [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### probe_frames(shot, ctx, times)

The film’s frames of `shot` at each of `times`, from its STORED picture (an#347).

Manim owns its clock and renders a whole scene at once, so `an
probe` never runs it: the picture a render stored is conformed
exactly as [`render()`](#an.adapters.manim_adapter.ManimRenderer.render) conforms it, and the frames showing at
`times` are read out. With no stored picture it refuses, naming the
render that stores one.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

#### render(shot, ctx)

Render `shot` for exactly `shot.duration` (`an.render` settles it
to the measured length, or longer to hold for its narration).

* **Return type:**
  [`RenderResult`](an.adapters.md#an.adapters.RenderResult)

#### stored_reads(key, ctx)

The read trace stored with picture `key` (`None`: none stored,
or not recorded). Reads stores only; never renders.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### *class* an.adapters.manim_adapter.ManimShotSpec(source, scene=None, quality=None, background='#000000', timeout=600.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a Manim shot’s `options` say, checked.

```pycon
>>> ManimShotSpec.from_options({"source": "s", "quality": "z"})
Traceback (most recent call last):
...
an.adapters.manim_adapter.ManimRenderError: options.quality must be one of ['l', 'm', 'h', 'p', 'k'] (Manim's presets), got 'z'
```

### an.adapters.manim_adapter.QUALITY_PRESETS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [ManimQuality](#an.adapters.manim_adapter.ManimQuality)]* *= {'h': ManimQuality(letter='h', width=1920, height=1080, fps=60), 'k': ManimQuality(letter='k', width=3840, height=2160, fps=60), 'l': ManimQuality(letter='l', width=854, height=480, fps=15), 'm': ManimQuality(letter='m', width=1280, height=720, fps=30), 'p': ManimQuality(letter='p', width=2560, height=1440, fps=60)}*

Manim Community Edition’s presets (`-ql` … `-qk`), smallest first.

### *class* an.adapters.manim_adapter.SourceFile(key, entry, closure, display)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A scene file and its closure, as a resolver read them.

`closure` is every file the render stages into its working directory —
`{relative path: bytes}`, the entry file included as `entry` — and
`digest` covers all of it, so a sibling module or an image the scene
loads relatively is in the keys. `display` is how a finding names the
entry (`assets/sources/chart.py`; never an absolute path).

### an.adapters.manim_adapter.choose_quality(, fps, resolution)

The smallest Manim preset that is at least as tall and as fast as the film.

The picture is then resampled and scaled to exactly the film’s rate and size,
so a smaller preset would be upscaled (blur) or frame-doubled (judder).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> choose_quality(fps=15, resolution=(640, 360)), choose_quality(fps=30, resolution=(1920, 1080))
('l', 'h')
>>> choose_quality(fps=120, resolution=(8000, 4000))  # nothing is enough: the largest
'k'
```

### an.adapters.manim_adapter.manim_environment()

The Manim render’s machine: Manim’s stack, ffmpeg, LaTeX, fonts, the ISA.

Python package versions (Manim draws with Cairo and Pango through pycairo
and ManimPango, and writes with PyAV), the full `ffmpeg -version` banner
(the conform and the encode), the LaTeX and dvisvgm builds (a formula’s
glyphs), the installed font set, and the ISA and OS family. Never a path.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.manim_adapter.manim_shot_inputs(shot, ctx)

The Manim renderer’s [`ShotKeyer`](an.build.keys.md#an.build.keys.ShotKeyer).

Named parts: `source` (every file of the sources folder the render
stages), `manim` (the picture’s other inputs: entry, scene, Manim and
manimkit versions, quality, LaTeX mode — `picture_inputs()`), `knobs`
(fps, size, background and the encode: pixel format, x264 argv, scale
filter, faststart), `audio` (the dialogue muxed under it and the frame
count it is cut to — a held narration moves it), `code`
(`render_code_digest()`) and `reads` (what the files the picture’s
render read outside the sources folder hold NOW —
`current_reads_digest()` of the trace stored with the picture; an#291).
Raises what the render would for a bad shot.

* **Return type:**
  [`ShotKeyInputs`](an.build.keys.md#an.build.keys.ShotKeyInputs)

### an.adapters.manim_adapter.store_source_resolver(store='sources')

The default resolver: `options.source` is a key of the mall’s `store`.

* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`ManimShotSpec`](#an.adapters.manim_adapter.ManimShotSpec), [`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]], [`SourceFile`](#an.adapters.manim_adapter.SourceFile)]

```pycon
>>> resolve = store_source_resolver()
>>> resolve(ManimShotSpec("chart"), {"sources": {"chart": b"x = 1"}}).data
b'x = 1'
```
