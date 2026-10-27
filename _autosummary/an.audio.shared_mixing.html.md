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

| [`mixing_problem`](#an.audio.shared_mixing.mixing_problem)()                      | Why the installed `mixing` cannot serve `an`: a part it uses is missing (`mixing.loudness`, `mixing.filtergraph`), or it is absent; `None` when it can.                                                                                                                                                                       |
|----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`mixing_too_old`](#an.audio.shared_mixing.mixing_too_old)(\*, needed_for, error) | Run an import of a part of `mixing`; an `ImportError` becomes `error`, saying the installed `mixing` is too old when it lacks the part, else what failed.                                                                                                                                                                     |
| [`warn_if_mixing_too_old`](#an.audio.shared_mixing.warn_if_mixing_too_old)()              | Say once per process, before anything is billed, that the installed `mixing` cannot serve `an` ([`mixing_problem()`](#an.audio.shared_mixing.mixing_problem)): the entry points that may bill (a render, `an voices design`, `audition` and `reroll`) call it, so an old `mixing` is not found after synthesis (an#644). |

### Exceptions

| [`MixingTooOldWarning`](#an.audio.shared_mixing.MixingTooOldWarning)   | The installed `mixing` lacks a part `an` uses (or is absent).   |
|------------------------------------------------------------------------|-----------------------------------------------------------------|

### an.audio.shared_mixing.INSTALL_HINT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'pip install mixing'*

… and when it is not installed at all (an install with `--no-deps`).

### an.audio.shared_mixing.MIXING *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'mixing'*

The package, and what the user runs when theirs predates a part `an` needs.

### *exception* an.audio.shared_mixing.MixingTooOldWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

The installed `mixing` lacks a part `an` uses (or is absent).

### an.audio.shared_mixing.mixing_problem()

Why the installed `mixing` cannot serve `an`: a part it uses is
missing (`mixing.loudness`, `mixing.filtergraph`), or it is absent;
`None` when it can. Asked of the code, not of a version number: an
editable install’s metadata keeps the version it was installed at (an#644).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.audio.shared_mixing.mixing_too_old(, needed_for, error)

Run an import of a part of `mixing`; an `ImportError` becomes
`error`, saying the installed `mixing` is too old when it lacks the
part, else what failed.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[`None`](https://docs.python.org/3/builtins/constants.html#None)]

### an.audio.shared_mixing.warn_if_mixing_too_old()

Say once per process, before anything is billed, that the installed
`mixing` cannot serve `an` ([`mixing_problem()`](#an.audio.shared_mixing.mixing_problem)): the entry points
that may bill (a render, `an voices design`, `audition` and
`reroll`) call it, so an old `mixing` is not found after synthesis
(an#644). [`mixing_too_old()`](#an.audio.shared_mixing.mixing_too_old) stays the backstop at each import.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
