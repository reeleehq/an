"""The fleet's shared audio component, :mod:`mixing`, as ``an`` imports it.

``mixing`` is a core dependency (an#611), so the one way a part of it can be
missing is a ``mixing`` older than that part. :func:`mixing_module` is the one
import of such a part, used by :mod:`an.audio.loudness` (``mixing.loudness``)
and :mod:`an.audio.effects` (``mixing.filtergraph``), and the one wording of
that failure: upgrade ``mixing``.

>>> mixing_module("loudness", needed_for="leveling voices", error=RuntimeError).__name__
'mixing.loudness'
"""

from __future__ import annotations

import importlib
from types import ModuleType

#: What the user runs when the installed ``mixing`` predates a part ``an`` needs.
UPGRADE_HINT: str = "pip install -U mixing"


def mixing_module(
    name: str, *, needed_for: str, error: type[Exception]
) -> ModuleType:
    """``mixing.<name>``, or ``error`` saying that ``needed_for`` needs it and
    the installed ``mixing`` is too old to have it.

    >>> mixing_module("no_such_part", needed_for="testing", error=RuntimeError)
    Traceback (most recent call last):
      ...
    RuntimeError: testing needs mixing.no_such_part, which the installed mixing is too old to have: `pip install -U mixing` (No module named 'mixing.no_such_part')
    """
    try:
        return importlib.import_module(f"mixing.{name}")
    except ImportError as e:
        raise error(
            f"{needed_for} needs mixing.{name}, which the installed mixing is too "
            f"old to have: `{UPGRADE_HINT}` ({e})"
        ) from e
