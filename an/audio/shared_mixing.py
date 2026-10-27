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
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

#: The package, and what the user runs when theirs predates a part ``an`` needs.
MIXING: str = "mixing"
UPGRADE_HINT: str = "pip install -U mixing"
#: ... and when it is not installed at all (an install with ``--no-deps``).
INSTALL_HINT: str = "pip install mixing"
#: How Python words ``from mixing import part`` failing on ``part``.
_CANNOT_IMPORT = re.compile(r"cannot import name '(\w+)'")
#: The oldest ``mixing`` with every part ``an`` uses: ``mixing.loudness``
#: (0.0.64, an#563) and ``mixing.filtergraph.resample_pitch_filter`` (0.0.72,
#: an#611). A local package declares no version floor, so it is checked here
#: (an#644).
MIN_MIXING: str = "0.0.72"


class MixingTooOldWarning(UserWarning):
    """The installed ``mixing`` is older than :data:`MIN_MIXING` (or absent)."""


def _release(version: str) -> tuple[int, ...] | None:
    """The numeric release of ``version`` (``"0.0.72.dev1"`` -> ``(0, 0, 72)``),
    ``None`` when it does not start with one.

    >>> _release("0.0.72"), _release("1.2rc1"), _release("unknown")
    ((0, 0, 72), (1, 2), None)
    """
    m = re.match(r"\d+(?:\.\d+)*", version)
    return tuple(int(p) for p in m.group(0).split(".")) if m else None


def mixing_version_problem(
    *, minimum: str = MIN_MIXING, installed: str | None = None
) -> str | None:
    """Why the installed ``mixing`` cannot serve ``an`` (older than
    ``minimum``, or not installed), or ``None``. ``installed`` defaults to the
    distribution's version; one that is not a release number is not judged.

    >>> mixing_version_problem(installed="0.0.60")
    'mixing 0.0.60 is older than 0.0.72, which an needs (mixing.loudness, mixing.filtergraph): `pip install -U mixing`'
    >>> mixing_version_problem(installed="0.0.81") is None
    True
    """
    if installed is None:
        from importlib.metadata import PackageNotFoundError, version

        try:
            installed = version(MIXING)
        except PackageNotFoundError:
            return f"{MIXING} is not installed, and an needs it: `{INSTALL_HINT}`"
    have, need = _release(installed), _release(minimum)
    if have is None or need is None or have >= need:
        return None
    return (
        f"{MIXING} {installed} is older than {minimum}, which an needs "
        f"(mixing.loudness, mixing.filtergraph): `{UPGRADE_HINT}`"
    )


@lru_cache(maxsize=None)
def warn_if_mixing_too_old() -> None:
    """Say once per process, before anything is billed, that the installed
    ``mixing`` is too old (:func:`mixing_version_problem`): the entry points
    that may bill (a render, ``an voices design`` and ``audition``) call it,
    so an old ``mixing`` is not found after synthesis (an#644).
    :func:`mixing_too_old` stays the backstop at the import."""
    problem = mixing_version_problem()
    if problem:
        warnings.warn(problem, MixingTooOldWarning, stacklevel=3)


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
