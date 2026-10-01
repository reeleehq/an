"""Collection rules for the package's own doctests.

`an` is in `testpaths` so CI's `--doctest-modules` reaches the package (an#61).
That flag **imports every module it scans**, which makes one module a problem:
`an.genre` declares this package's production genre to `nw`, and says so in its
own docstring — it is opt-in, `an/__init__.py` never imports it, and `an` gains
no hard dependency on `nw` as a result. CI installs no optional extras, so
importing it there raises `ModuleNotFoundError`.

So it is collected **where `nw` is available and skipped where it is not**,
rather than excluded outright. It carries no doctests today, but a rule that
silently drops a module whenever someone adds one is the an#22 failure in
miniature, so the skip is conditional on the actual reason.

`tests/test_doctest_gate.py` asserts that `an.genre` remains the *only* module
under `an/` importing an undeclared dependency at module level — a new one would
break CI collection the same way, and is much easier to catch here than there.
"""

collect_ignore: list[str] = []

# An old path that is now a whole-module LIVE alias (an#247, `an._shims.alias_module`)
# carries no code and no doctest of its own, and its `__file__` names the module
# it aliases -- which pytest's import-by-path refuses as a mismatch. Its target
# is collected under its own path.
from pathlib import Path as _Path  # noqa: E402

collect_ignore += [
    str(_p.relative_to(_Path(__file__).parent))
    for _p in _Path(__file__).parent.rglob("*.py")
    if "alias_module(__name__," in _p.read_text(encoding="utf-8")
]

try:  # pragma: no cover - depends on the environment, not the code
    import nw  # noqa: F401
except ImportError:  # pragma: no cover
    collect_ignore.append("genre.py")
