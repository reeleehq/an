# an.audio.shared_mixing

The fleet’s shared audio component, `mixing`, as `an` imports it.

`mixing` is a core dependency (an#611), so the way a part of it goes missing
is a `mixing` older than that part. [`mixing_too_old()`](#an.audio.shared_mixing.mixing_too_old) is the one wording
of that failure, used around the lazy imports in [`an.audio.loudness`](an.audio.loudness.html.md#module-an.audio.loudness)
(`mixing.loudness`) and [`an.audio.effects`](an.audio.effects.html.md#module-an.audio.effects) (`mixing.filtergraph`). The
imports themselves stay written out where they are, so the licence firewall
(`tests/test_captions.py::test_an_never_imports_mixing`) still reads them.

```pycon
>>> with mixing_too_old(needed_for="testing", error=RuntimeError):
...     from mixing import no_such_part
Traceback (most recent call last):
  ...
RuntimeError: testing needs mixing.no_such_part, which the installed mixing is too old to have: `pip install -U mixing`
```

### Module Attributes

| [`MIXING`](#an.audio.shared_mixing.MIXING)       | The package, and what the user runs when theirs predates a part `an` needs.   |
|---------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`INSTALL_HINT`](#an.audio.shared_mixing.INSTALL_HINT) |                                                                               |

### Functions

| [`mixing_too_old`](#an.audio.shared_mixing.mixing_too_old)(\*, needed_for, error)   | Run an import of a part of `mixing`; an `ImportError` becomes `error`, saying the installed `mixing` is too old when it lacks the part, else what failed.   |
|------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|

### an.audio.shared_mixing.INSTALL_HINT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'pip install mixing'*

… and when it is not installed at all (an install with `--no-deps`).

### an.audio.shared_mixing.MIXING *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'mixing'*

The package, and what the user runs when theirs predates a part `an` needs.

### an.audio.shared_mixing.mixing_too_old(, needed_for, error)

Run an import of a part of `mixing`; an `ImportError` becomes
`error`, saying the installed `mixing` is too old when it lacks the
part, else what failed.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]
