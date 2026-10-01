# an.stage.runtime_files

Locate the bundled cutout JS runtime files.

The runtime ships under `an/stage/runtime/` and is consumed by the
headless renderer in Phase 2C. This module exposes paths so callers don’t
hard-code the layout.

```pycon
>>> p = runtime_dir()
>>> p.is_dir()
True
>>> (p / "index.html").is_file()
True
```

### Functions

| [`runtime_dir`](#an.stage.runtime_files.runtime_dir)()        | Return the directory containing index.html + runtime.js.   |
|-----------------------------------------------------------------------|------------------------------------------------------------|
| [`runtime_index_html`](#an.stage.runtime_files.runtime_index_html)() | Path to `index.html`.                                      |
| [`runtime_js`](#an.stage.runtime_files.runtime_js)()         | Path to `runtime.js`.                                      |

### an.stage.runtime_files.runtime_dir()

Return the directory containing index.html + runtime.js.

Uses importlib.resources so it works from a wheel install too.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.stage.runtime_files.runtime_index_html()

Path to `index.html`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.stage.runtime_files.runtime_js()

Path to `runtime.js`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
