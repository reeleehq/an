"""The fleet's shared audio component, :mod:`mixing`, as ``an`` imports it.

``mixing`` is a core dependency (an#611), so the way a part of it goes missing
is a ``mixing`` older than that part. :func:`mixing_too_old` is the one wording
of that failure, used around the lazy imports in :mod:`an.audio.loudness`
(``mixing.loudness``) and :mod:`an.audio.effects` (``mixing.filtergraph``). The
imports themselves stay written out where they are, so the licence firewall
(``tests/test_captions.py::test_an_never_imports_mixing``) still reads them.

>>> with mixing_too_old(needed_for="testing", error=RuntimeError):
...     from mixing import no_such_part
Traceback (most recent call last):
  ...
RuntimeError: testing needs mixing.no_such_part, which the installed mixing is too old to have: `pip install -U mixing`
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

#: The package, and what the user runs when theirs predates a part ``an`` needs.
MIXING: str = "mixing"
UPGRADE_HINT: str = "pip install -U mixing"
#: ... and when it is not installed at all (an install with ``--no-deps``).
INSTALL_HINT: str = "pip install mixing"
#: How Python words ``from mixing import part`` failing on ``part``.
_CANNOT_IMPORT = re.compile(r"cannot import name '(\w+)'")


def _missing_part(e: ImportError) -> str | None:
    """The ``mixing.<part>`` an import of ``mixing`` failed to find, ``None``
    when the failure is something else (``mixing`` itself absent, or a module
    it imports). ``from mixing import part`` raises a plain ``ImportError``
    named ``mixing``; ``import mixing.part`` a ``ModuleNotFoundError`` named
    ``mixing.part``."""
    name = e.name or ""
    if name.startswith(f"{MIXING}."):
        return name
    if name == MIXING and not isinstance(e, ModuleNotFoundError):
        # `name_from` is Python 3.12+; before, only the message names the part.
        part = getattr(e, "name_from", None) or _CANNOT_IMPORT.search(str(e))
        if isinstance(part, re.Match):
            part = part.group(1)
        return f"{MIXING}.{part}" if part else None
    return None


@contextmanager
def mixing_too_old(*, needed_for: str, error: type[Exception]) -> Iterator[None]:
    """Run an import of a part of ``mixing``; an ``ImportError`` becomes
    ``error``, saying the installed ``mixing`` is too old when it lacks the
    part, else what failed."""
    try:
        yield
    except ImportError as e:
        part = _missing_part(e)
        if part is None:
            hint = f": `{INSTALL_HINT}`" if e.name == MIXING else ""
            raise error(
                f"{needed_for} needs {MIXING}, which failed to import ({e}){hint}"
            ) from e
        raise error(
            f"{needed_for} needs {part}, which the installed {MIXING} is too old "
            f"to have: `{UPGRADE_HINT}`"
        ) from e
