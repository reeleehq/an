"""Collection rules for the package's own doctests.

`an` is in `testpaths` so CI's `--doctest-modules` reaches the package (an#61).
That flag **imports every module it scans**, which makes one module a problem:
`tests/test_doctest_gate.py` asserts that no module under `an/` imports an
undeclared dependency at module level — one would break CI collection (which
installs no optional extras) the same way, and is much easier to catch there than
here. (The one such module, the `nw` declaration of the cut-out genre, moved to
`cutan`, which skips it when `nw` is absent.)
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
