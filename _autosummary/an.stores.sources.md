# an.stores.sources

The project’s opaque scene sources: files a whole-shot renderer runs as they are.

A Manim shot (`Shot(renderer="manim", options={"source": "chart"})`) names a
key here; the file is `assets/sources/chart.py`. The store is the ONE place
the renderer reads it from (pillar 7), and what it reads is what its shot-cache
key digests, so an edit to the file re-renders the shot.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = SourcesStore(d)
...     store["chart"] = b"from manim import *\n"
...     list(store), store.path_of("chart").name
(['chart'], 'chart.py')
```

### Classes

| [`SourcesStore`](#an.stores.sources.SourcesStore)(root_dir)   | Python scene sources (`.py` bytes) — a Manim scene file per key.   |
|---------------------------------------------------------------------------|--------------------------------------------------------------------|

### *class* an.stores.sources.SourcesStore(root_dir)

Bases: `_BlobStore`

Python scene sources (`.py` bytes) — a Manim scene file per key.
