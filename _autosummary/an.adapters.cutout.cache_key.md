# an.adapters.cutout.cache_key

What a cut-out shot render reads: the keyer behind its shot-cache key (ADR 0004).

The cut-out render is a pure function of these, and of nothing else:

- **the compiled document** — `compile_shot()` with exactly the arguments
  the stage engine passes (`StageEngine.open`, since an#247); digested as `scene_contract_sha256`, so the
  cache key and the bench’s contract hash agree about what “the same document”
  means while staying two different things (the key covers more);
- **the bytes of every texture it stages** — SVG included. Raster art already
  carries its digest in the document (an#211); SVG art is addressed by path,
  so an SVG edited in place would otherwise leave the key unchanged. The
  digests go into the KEY only: the wire shape and `scene_contract_sha256`
  do not move (ADR 0004 decision 2);
- **the version of every easing the document names** (an#239 item 1): a
  compiled keyframe carries a bare name, so a v2 of a curve would change
  pixels under an unchanged document;
- **the dialogue audio it muxes** — each line’s `audio_ref`,
  `viseme_ref`, start and the digest of the bytes the store returns for it,
  and the picture’s length the mux cuts to;
- **the JS runtime** (`runtime_sha256`) and **every render knob**, each
  RESOLVED the way the render resolves it (`pix_fmt=None` is the module
  default at call time, which is what the bench’s lever rebinds), plus the
  pinned Chromium and x264 argv.
- **the render path’s Python source** ([`render_code_digest()`](#an.adapters.cutout.cache_key.render_code_digest)): the
  capture loop, the canvas readback, the supersample and shutter resolves, the
  audio mux — everything that turns the document into an mp4 after compile.
  The Python twin of `runtime_sha256`: an `an` upgrade that changes how a
  shot is encoded (an#195 did, with no knob and no runtime change) re-renders
  every shot instead of serving an old mp4. Computed by walking the imports
  from the REGISTERED renderer’s own modules ([`render_path_roots()`](#an.adapters.cutout.cache_key.render_path_roots): the
  renderer class, the frame stage its `render` comes from, its engine), and
  through the string targets of `an._shims.forward_module_attributes()`,
  so a new helper module – or a module that became a pure re-export shim –
  cannot fall outside it.

The machine — Chromium build, Playwright, the full ffmpeg build and the x264
build it encodes with, ISA — is the separate environment part
([`cutout_environment()`](#an.adapters.cutout.cache_key.cutout_environment)), never mixed into the content. Fonts: a text
unit’s glyphs are outlined in Python and travel INSIDE the document (`data:`
srcs), so a different face is a different compiled digest; but SVG ART may
carry its own `<text>`, which Chromium draws with the machine’s fonts — so a
shot that stages such a part gets a `fonts` part, a digest of the installed
font set ([`system_fonts_digest()`](#an.adapters.cutout.cache_key.system_fonts_digest)).

### Module Attributes

| [`EASING_KEYS`](#an.adapters.cutout.cache_key.EASING_KEYS)          | Keys in the compiled document whose string value names an easing.                                                                       |
|-----------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`RENDER_PATH_ROOT`](#an.adapters.cutout.cache_key.RENDER_PATH_ROOT)     | The cut-out renderer's historical module (the stage engine and `CutoutRenderer` live there until an#247 PR B moves them to `an.stage`). |
| [`RENDER_PATH_EXCLUDED`](#an.adapters.cutout.cache_key.RENDER_PATH_EXCLUDED) | Modules the walk does NOT enter, each with the reason its change is already in the key some other way.                                  |
| [`SVG_TEXT_MARKERS`](#an.adapters.cutout.cache_key.SVG_TEXT_MARKERS)     | A byte sequence that marks an SVG part drawing text with the MACHINE's fonts.                                                           |
| [`FORWARDING_CALL`](#an.adapters.cutout.cache_key.FORWARDING_CALL)      | The call that makes an old module's names LIVE aliases of another module's (`an._shims`).                                               |
| [`FONT_DIRS`](#an.adapters.cutout.cache_key.FONT_DIRS)            | Font folders listed when `fc-list` is absent.                                                                                           |

### Functions

| [`compiled_document`](#an.adapters.cutout.cache_key.compiled_document)(shot, ctx)          | The document the stage engine (`StageEngine.open`) will compile for `shot` under `ctx`.                                                                                                                |
|----------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`cutout_environment`](#an.adapters.cutout.cache_key.cutout_environment)()                  | The cut-out render's machine: the bench's own probes, minus what is not identity.                                                                                                                      |
| [`cutout_shot_inputs`](#an.adapters.cutout.cache_key.cutout_shot_inputs)(shot, ctx)         | The cut-out renderer's [`ShotKeyer`](an.build.keys.md#an.build.keys.ShotKeyer).                                                                                             |
| [`easing_versions`](#an.adapters.cutout.cache_key.easing_versions)(doc)                  | `{name: version}` for every registered easing the compiled document names.                                                                                                                             |
| [`ffmpeg_build`](#an.adapters.cutout.cache_key.ffmpeg_build)()                        | The whole `ffmpeg -version` (every library's version and the configure line), not its first line: the banner is unchanged by `brew upgrade x264`, which swaps the dynamically linked encoder under it. |
| [`muxed_audio`](#an.adapters.cutout.cache_key.muxed_audio)(shot, ctx)                | What `_mux_shot` lays under the picture, as data: one entry per muxed line.                                                                                                                            |
| [`render_code_digest`](#an.adapters.cutout.cache_key.render_code_digest)()                  | sha256 over the source of every module on the render path (by module name).                                                                                                                            |
| [`render_knobs`](#an.adapters.cutout.cache_key.render_knobs)(shot, ctx)               | Every `RenderContext` knob, resolved the way the frame stage resolves it.                                                                                                                              |
| [`render_path_modules`](#an.adapters.cutout.cache_key.render_path_modules)([root, excluded]) | `{module: source path}` for every `an` module the render path reaches.                                                                                                                                 |
| [`render_path_roots`](#an.adapters.cutout.cache_key.render_path_roots)([renderer_type])    | The modules a renderer's render path starts from, read off the renderer itself.                                                                                                                        |
| [`system_fonts_digest`](#an.adapters.cutout.cache_key.system_fonts_digest)()                 | A digest of the fonts this machine can draw SVG `<text>` with; once per process.                                                                                                                       |
| [`texture_digests`](#an.adapters.cutout.cache_key.texture_digests)(scene_json, mall)     | `{alias: sha256 of the bytes staged for it}` for every texture the document declares.                                                                                                                  |
| [`x264_build`](#an.adapters.cutout.cache_key.x264_build)()                          | The x264 build that ACTUALLY encodes: one 16x16 frame, its SEI read back.                                                                                                                              |

### an.adapters.cutout.cache_key.EASING_KEYS *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'easing'})*

Keys in the compiled document whose string value names an easing.

### an.adapters.cutout.cache_key.FONT_DIRS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]]* *= {'Darwin': ('/System/Library/Fonts', '/Library/Fonts', '~/Library/Fonts'), 'Linux': ('/usr/share/fonts', '/usr/local/share/fonts', '~/.local/share/fonts', '~/.fonts'), 'Windows': ('C:/Windows/Fonts',)}*

Font folders listed when `fc-list` is absent.

### an.adapters.cutout.cache_key.FORWARDING_CALL *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'forward_module_attributes'*

The call that makes an old module’s names LIVE aliases of another module’s
(`an._shims`). Its target is a STRING, invisible to an import walk.

### an.adapters.cutout.cache_key.RENDER_PATH_EXCLUDED *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'an.adapters._base': 'the RenderContext/RenderResult types; their values are \`knobs\`', 'an.adapters.cutout.compile': 'its output is the \`compiled\` part', 'an.adapters.cutout.serialize': 'its output is the \`compiled\` part', 'an.adapters.cutout.text': 'compile-side; only INLINE_SRC_PREFIX is read at render', 'an.ir.schema': 'the IR model; what it means for a render reaches \`compiled\`/\`knobs\`'}*

Modules the walk does NOT enter, each with the reason its change is already
in the key some other way. Everything else it reaches is hashed.

### an.adapters.cutout.cache_key.RENDER_PATH_ROOT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an.adapters.cutout.render'*

The cut-out renderer’s historical module (the stage engine and
`CutoutRenderer` live there until an#247 PR B moves them to `an.stage`).
The walk is no longer rooted HERE alone: [`render_path_roots()`](#an.adapters.cutout.cache_key.render_path_roots) derives
the roots from the registered renderer, and this module is one of them.

### an.adapters.cutout.cache_key.SVG_TEXT_MARKERS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[bytes](https://docs.python.org/3/builtins/stdtypes.html#bytes), ...]* *= (b'<text', b':text')*

A byte sequence that marks an SVG part drawing text with the MACHINE’s fonts.

### an.adapters.cutout.cache_key.compiled_document(shot, ctx)

The document the stage engine (`StageEngine.open`) will compile for `shot` under `ctx`.

The SAME call, argument for argument — `tests/test_shot_cache.py` pins the
two against each other, so a knob added to one and not the other fails
there rather than in a stale render.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.adapters.cutout.cache_key.cutout_environment()

The cut-out render’s machine: the bench’s own probes, minus what is not identity.

Chromium’s build and WebGL identity (one browser launch), Playwright, the
full ffmpeg build and the x264 build it encodes with (one 16x16 encode),
the ISA and OS family, and the Python imaging stack the frame stage decodes
and resolves with. The executable PATH is left out — it names a home
directory, not a build. A failed probe is recorded as its error, never as
“fine”.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.cutout.cache_key.cutout_shot_inputs(shot, ctx)

The cut-out renderer’s [`ShotKeyer`](an.build.keys.md#an.build.keys.ShotKeyer).

Compiles the shot (timed, as `compile_s`) and digests everything the
render reads beside the document. Compile warnings are re-emitted only when
asked: on a cache MISS the render compiles again and warns itself, so the
engine collects them here (`details["warnings"]`) and replays them only
for a shot it reuses, where they would otherwise never be seen.

* **Return type:**
  [`ShotKeyInputs`](an.build.keys.md#an.build.keys.ShotKeyInputs)

### an.adapters.cutout.cache_key.easing_versions(doc)

`{name: version}` for every registered easing the compiled document names.

A parametrised spec (`cubic-bezier(...)`) or a control-point list carries
its meaning in the document itself and has no version; a name the registry
does not know is left to the compiler, which refuses it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`int`](https://docs.python.org/3/builtins/functions.html#int)]

```pycon
>>> easing_versions({"animations": {"a": {"channels": [{"keyframes": [
...     {"time": 0, "value": 0, "easing": "ease_in_out"},
...     {"time": 1, "value": 1, "easing": [0.1, 0.2, 0.3, 0.4]}]}]}}})
{'ease_in_out': 1}
```

### an.adapters.cutout.cache_key.ffmpeg_build()

The whole `ffmpeg -version` (every library’s version and the configure
line), not its first line: the banner is unchanged by `brew upgrade x264`,
which swaps the dynamically linked encoder under it.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.cutout.cache_key.muxed_audio(shot, ctx)

What `_mux_shot` lays under the picture, as data: one entry per muxed line.

Mirrors `_stage_audio_inputs`: a line without an `audio_ref` or a start
is not muxed, and neither is one whose ref the store does not hold. The
bytes’ digest sits beside the ref because the ref keys the SYNTHESIS
inputs, not the bytes, and the mux reads the bytes.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.cutout.cache_key.render_code_digest()

sha256 over the source of every module on the render path (by module name).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.adapters.cutout.cache_key.render_knobs(shot, ctx)

Every `RenderContext` knob, resolved the way the frame stage resolves it.

Validated here too — an invalid `pix_fmt` or supersample factor raises
the render’s own error before anything launches.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.adapters.cutout.cache_key.render_path_modules(root=None, , excluded={'an.adapters._base': 'the RenderContext/RenderResult types; their values are \`knobs\`', 'an.adapters.cutout.compile': 'its output is the \`compiled\` part', 'an.adapters.cutout.serialize': 'its output is the \`compiled\` part', 'an.adapters.cutout.text': 'compile-side; only INLINE_SRC_PREFIX is read at render', 'an.ir.schema': 'the IR model; what it means for a render reaches \`compiled\`/\`knobs\`'})

`{module: source path}` for every `an` module the render path reaches.

`root` is one module name or several; `None` is [`render_path_roots()`](#an.adapters.cutout.cache_key.render_path_roots).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

```pycon
>>> mods = render_path_modules()
>>> "an.adapters.cutout.canvas_capture" in mods and "an.adapters.cutout.compile" not in mods
True
>>> {"an.engines.capture", "an.media.mp4"} <= set(mods)
True
```

### an.adapters.cutout.cache_key.render_path_roots(renderer_type=None)

The modules a renderer’s render path starts from, read off the renderer itself.

The renderer class’s module, the module its `render` method is defined in
(the core frame stage, for a `FrameStageRenderer`), and its default
engine’s module – so moving the renderer (an#247 PR B) or turning its old
module into a pure shim moves the roots with it. `None` is the cut-out
renderer, plus [`RENDER_PATH_ROOT`](#an.adapters.cutout.cache_key.RENDER_PATH_ROOT).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

```pycon
>>> "an.engines.frame_stage" in render_path_roots()
True
```

### an.adapters.cutout.cache_key.system_fonts_digest()

A digest of the fonts this machine can draw SVG `<text>` with; once per process.

`fc-list` where fontconfig exists (Linux, and macOS with it installed);
otherwise the listing (name, size, mtime) of the platform’s font folders.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.adapters.cutout.cache_key.texture_digests(scene_json, mall)

`{alias: sha256 of the bytes staged for it}` for every texture the document declares.

Resolved exactly as `_stage_scene_assets` resolves them — the prefix map,
the store’s root, the versioned `src` stripped — so what is digested is
what is staged. Inline (`data:`) textures are already in the document and
are skipped; anything unresolvable is `ABSENT` with its `src`, so
it still moves the key the day it appears.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.adapters.cutout.cache_key.x264_build()

The x264 build that ACTUALLY encodes: one 16x16 frame, its SEI read back.

The bench’s own comparability key (`an.bench.environment.x264_sei`), so
the cache and the ledger agree about what “the same encoder” means.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
