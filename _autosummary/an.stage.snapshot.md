# an.stage.snapshot

Rasterise art files to PNG in the browser the stage already uses (an#347).

`an library sheet --parts` tiles an asset’s part files; most cut-out parts
are SVG, which nothing in the core can decode. Chromium draws them exactly as
the stage will. Raster parts (PNG, JPEG, WebP, GIF) are drawn the same way, so
one path serves every format the stage loads.

### Functions

| [`rasterise`](#an.stage.snapshot.rasterise)(files, \*, size)   | PNG bytes of each `(path, data)` art file, fitted into a `size` square, transparent behind.   |
|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|

### an.stage.snapshot.rasterise(files, , size)

PNG bytes of each `(path, data)` art file, fitted into a `size` square, transparent behind.

Raises [`ImportError`](https://docs.python.org/3/builtins/exceptions.html#ImportError) with the install hint when the stage extra is absent.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]
