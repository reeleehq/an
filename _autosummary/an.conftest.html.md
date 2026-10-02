# an.conftest

Collection rules for the package’s own doctests.

`an` is in `testpaths` so CI’s `--doctest-modules` reaches the package (an#61).
That flag **imports every module it scans**, which makes one module a problem:
`tests/test_doctest_gate.py` asserts that no module under `an/` imports an
undeclared dependency at module level — one would break CI collection (which
installs no optional extras) the same way, and is much easier to catch there than
here. (The one such module, the `nw` declaration of the cut-out genre, moved to
`cutan`, which skips it when `nw` is absent.)
