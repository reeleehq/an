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

# A module that MOVED OUT to a genre package (`an._shims.moved_to_package`,
# an#225) holds no code, and importing it needs that package, which the core
# lane does not install. Found by the same STATIC reading the shot-cache walk
# uses (a top-level call, by AST -- not a text match, which would also drop a
# module that merely mentions the call in a docstring).
from an._shims import declared_moves as _declared_moves  # noqa: E402


def _moved_shim_files(here: _Path) -> list[str]:
    """Paths (relative to ``here``, the package dir) of its moved modules' old files."""
    out = []
    for module in _declared_moves(here):
        rel = _Path(*module.split(".")[1:])
        for candidate in (rel / "__init__.py", rel.with_suffix(".py")):
            if (here / candidate).is_file():
                out.append(str(candidate))
    return out


collect_ignore += _moved_shim_files(_Path(__file__).parent)
