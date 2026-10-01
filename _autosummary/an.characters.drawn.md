# an.characters.drawn

What the character factory wrote, as it wrote it: the in-memory log behind its record of drawn bytes.

The machine’s record of bytes the factory drew (an#269,
`an.library.registry.record_generated`) verifies the factory’s stamps in the
asset library. It must hold the digests of bytes the factory itself produced,
never of whatever sits on disk when it finishes: a file swapped in while
`new_character` runs is not the factory’s drawing. So every file the factory
writes goes through [`write_text()`](#an.characters.drawn.write_text) / [`write_bytes()`](#an.characters.drawn.write_bytes), which write it AND,
while a [`drawing()`](#an.characters.drawn.drawing) is open in this context, log the SHA-256 of the exact
bytes written — computed in memory at write time.

```pycon
>>> import tempfile, pathlib
>>> with tempfile.TemporaryDirectory() as d, drawing() as log:
...     p = pathlib.Path(d) / "a.svg"
...     write_text(p, "<svg/>")
...     log[str(p.resolve())] == hashlib.sha256(b"<svg/>").hexdigest()
True
```

### Functions

| [`drawing`](#an.characters.drawn.drawing)()                              | Log `{resolved path: sha256}` of every file written through this module, in this context.                           |
|-----------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [`write_bytes`](#an.characters.drawn.write_bytes)(path, data)                | Write `data` to `path`, logging its digest if a [`drawing()`](#an.characters.drawn.drawing) is open. |
| [`write_text`](#an.characters.drawn.write_text)(path, text, \*[, encoding]) | Write `text` as `Path.write_text` does (newlines as the platform writes them), logged.                              |

### an.characters.drawn.drawing()

Log `{resolved path: sha256}` of every file written through this module, in this context.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.characters.drawn.write_bytes(path, data)

Write `data` to `path`, logging its digest if a [`drawing()`](#an.characters.drawn.drawing) is open.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.characters.drawn.write_text(path, text, , encoding='utf-8')

Write `text` as `Path.write_text` does (newlines as the platform writes them), logged.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
