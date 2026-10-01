# an.preview

Live preview server: render a project’s current scene in a browser, reloading on edit.

The [`preview_project()`](#an.preview.preview_project) function spins up a local HTTP server pointed at
a freshly-compiled cutout scene JSON, then watches `scene.md` /
`ir/scene.json` for changes and recompiles. The browser polls
`scene.json` every ~500 ms (HEAD request, `Last-Modified` header) and
re-calls `window.anLoadScene` whenever the file changes.

Lossy by design: shows the runtime canvas only — no audio mux, no final
mp4. Use `an render` once you’re happy with the look.

```pycon
>>> from an.preview import _stage_preview
>>> callable(_stage_preview)
True
```

### Functions

| [`preview_project`](#an.preview.preview_project)(project_dir, \*[, shot_id, ...])   | Serve a live preview of `project_dir` from a local HTTP server.   |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|

### Classes

| [`PreviewStaging`](#an.preview.PreviewStaging)(runtime_dir, scene_json_path, ...)   | Outcome of staging a preview's runtime + initial compiled scene.   |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|

### Exceptions

| [`PreviewError`](#an.preview.PreviewError)   | Raised when a preview cannot be staged or served.   |
|-----------------------------------------------------------------|-----------------------------------------------------|

### *exception* an.preview.PreviewError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when a preview cannot be staged or served.

### *class* an.preview.PreviewStaging(runtime_dir, scene_json_path, shot_id)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of staging a preview’s runtime + initial compiled scene.

### an.preview.preview_project(project_dir, , shot_id=None, open_browser=True, poll_interval_s=0.5)

Serve a live preview of `project_dir` from a local HTTP server.

Compiles the chosen shot (default: first shot in the timeline) to its
runtime JSON, stages the cutout JS runtime + any SVG character
textures, and serves the result on a free port. A daemon watcher
thread polls `scene.md` / `ir/scene.json` mtimes and recompiles
when either changes; the browser sees the new compiled scene via its
own ~500 ms HEAD-request poll.

Blocks the calling thread until interrupted (Ctrl-C). Returns the
base URL after teardown.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
