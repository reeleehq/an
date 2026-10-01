"""The stage engine's easing vocabulary — a view of :mod:`an.timing.easing`.

The curves, their solvers and the full registry live in the timing kernel
(:mod:`an.timing.easing`). This module keeps the path every stage caller already
imports, and it states what the STAGE implements: ``runtime.js`` evaluates the
legacy names in :data:`an.base.EASING_PRESETS` and a cubic-Bézier control
4-tuple, nothing else, so :func:`apply_easing` here refuses any other name. That
refusal is what ``an validate`` and the compiler use to say "the evaluators know
this easing" — a curve the kernel knows but the stage runtime does not would
otherwise surface as a throw in the browser.

>>> apply_easing("linear", 0.5)
0.5
>>> round(apply_easing("ease_in_out", 0.5), 6)
0.5
>>> round(apply_easing([0.0, 0.0, 1.0, 1.0], 0.5), 6)
0.5
>>> apply_easing("ease-in", 0.5)
Traceback (most recent call last):
 ...
an.timing.easing.UnknownEasingError: unknown easing preset 'ease-in'; known: ['ease', 'ease_in', 'ease_in_out', 'ease_out', 'linear', 'step']
"""

from __future__ import annotations

from typing import Callable

from an.base import EASING_PRESETS, EasingSpec
from an.timing import easing as _kernel
from an.timing.easing import legacy_cubic_bezier as cubic_bezier

__all__ = ["EASING_FUNCS", "apply_easing", "cubic_bezier"]

#: The easings the stage runtime implements (``runtime.js`` ``EASINGS``), each
#: the kernel registry's own curve.
EASING_FUNCS: dict[str, Callable[[float], float]] = {
    name: _kernel.easing_entry(name).curve for name in EASING_PRESETS
}


def apply_easing(spec: EasingSpec | None, t: float) -> float:
    """Apply an easing the STAGE implements to ``t`` in ``[0, 1]``.

    - ``None`` → linear (passthrough)
    - a string preset name (must be a key of ``EASING_FUNCS``)
    - a 4-element sequence of cubic-Bézier control points (the legacy solver)

    Raises ``ValueError`` for unknown preset names or malformed sequences.

    >>> apply_easing(None, 0.25)
    0.25
    >>> apply_easing("step", 0.99)
    0.0
    >>> apply_easing("step", 1.0)
    1.0
    """
    return _kernel.apply_easing(spec, t, names=EASING_FUNCS)
