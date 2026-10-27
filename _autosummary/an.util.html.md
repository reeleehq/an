# an.util

Internal helpers: file I/O, hashing, time arithmetic, light path utilities.

Nothing here is part of the public API — everything is underscore-prefixed
or used only by sibling an modules.

### Module Attributes

| [`WINDOWS_RESERVED_NAMES`](#an.util.WINDOWS_RESERVED_NAMES)   | Names Windows refuses as a file whatever the extension (`con`, `nul.mp4`), compared case-insensitively; `0` and the superscript digits are reserved too.   |
|---------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`is_windows_reserved`](#an.util.is_windows_reserved)(name)   | Whether Windows reserves `name` (its part before the first dot) for a device.   |
|------------------------------------------------------------------------------|---------------------------------------------------------------------------------|

### an.util.WINDOWS_RESERVED_NAMES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'aux', 'com0', 'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9', 'com²', 'com³', 'com¹', 'con', 'lpt0', 'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9', 'lpt²', 'lpt³', 'lpt¹', 'nul', 'prn'})*

Names Windows refuses as a file whatever the extension (`con`, `nul.mp4`),
compared case-insensitively; `0` and the superscript digits are reserved too.

### an.util.is_windows_reserved(name)

Whether Windows reserves `name` (its part before the first dot) for a device.

```pycon
>>> is_windows_reserved("NUL.mp4"), is_windows_reserved("console")
(True, False)
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
