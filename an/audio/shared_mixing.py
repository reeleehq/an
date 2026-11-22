"""The fleet's shared audio component, :mod:`mixing`, as ``an`` imports it.

``mixing`` is a core dependency (an#611), so the way a part of it goes missing
is a ``mixing`` older than that part. :func:`mixing_too_old` is the one wording
of that failure, used around the lazy imports in :mod:`an.audio.loudness`
(``mixing.loudness``) and :mod:`an.audio.effects` (``mixing.filtergraph``). The
imports themselves stay written out where they are, so the licence firewall
(``tests/test_captions.py::test_an_never_imports_mixing``) still reads them.

A keyword ``an`` passes cannot be found by importing a name: an older function
takes the call and fails on it. :func:`lacks_keywords` asks the function's
signature instead (``level_group(subject=)``, mixing#171, an#765), and
:func:`mixing_problem` and :mod:`an.audio.loudness` word a missing one as a
``mixing`` too old, like a missing part.

>>> with mixing_too_old(needed_for="testing", error=RuntimeError):
...     from mixing import no_such_part
Traceback (most recent call last):
  ...
RuntimeError: testing needs mixing.no_such_part, which the installed mixing is too old to have: `pip install -U mixing`

A name missing from a module that exists is named in full:

>>> with mixing_too_old(needed_for="testing", error=RuntimeError):
...     from mixing.loudness import no_such_name
Traceback (most recent call last):
  ...
RuntimeError: testing needs mixing.loudness.no_such_name, which the installed mixing is too old to have: `pip install -U mixing`
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from functools import lru_cache

#: The package, and what the user runs when theirs predates a part ``an`` needs.
MIXING: str = "mixing"
UPGRADE_HINT: str = "pip install -U mixing"
#: ... and when it is not installed at all (an install with ``--no-deps``).
INSTALL_HINT: str = "pip install mixing"
#: The keywords ``an`` passes to :func:`mixing.loudness.level_group`: ``subject``
#: names the voice in its ``GainCappedWarning`` (mixing#171, an#765).
LEVEL_GROUP_KEYWORDS: tuple[str, ...] = ("subject",)
#: How Python words ``from mixing import part`` failing on ``part``.
_CANNOT_IMPORT = re.compile(r"cannot import name '(\w+)'")


class MixingTooOldWarning(UserWarning):
    """The installed ``mixing`` lacks a part ``an`` uses (or is absent)."""


def _missing_part(e: ImportError) -> str | None:
    """The ``mixing.<part>`` an import of ``mixing`` failed to find, ``None``
    when the failure is something else (``mixing`` itself absent, or a module
    it imports). ``from mixing import part`` (or ``from mixing.module import
    name``) raises a plain ``ImportError`` named for the module it searched,
    the missing name only in its message; ``import mixing.part`` a
    ``ModuleNotFoundError`` named ``mixing.part``.

    >>> _missing_part(ImportError(
    ...     "cannot import name 'group_lufs' from 'mixing.loudness'", name="mixing.loudness"))
    'mixing.loudness.group_lufs'
    >>> _missing_part(ImportError("cannot import name 'loudness' from 'mixing'", name="mixing"))
    'mixing.loudness'
    >>> _missing_part(ModuleNotFoundError("No module named 'mixing.loudness'", name="mixing.loudness"))
    'mixing.loudness'
    >>> _missing_part(ModuleNotFoundError("No module named 'mixing'", name="mixing")) is None
    True
    """
    name = e.name or ""
    if name != MIXING and not name.startswith(f"{MIXING}."):
        return None  # not mixing's own module: something it imports failed
    if isinstance(e, ModuleNotFoundError):
        return None if name == MIXING else name
    # `name_from` is Python 3.12+; before, only the message names the part.
    part = getattr(e, "name_from", None) or _CANNOT_IMPORT.search(str(e))
    if isinstance(part, re.Match):
        part = part.group(1)
    if part:
        return f"{name}.{part}"
    return None if name == MIXING else name


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


def lacks_keywords(func: Callable[..., object], keywords: Iterable[str]) -> list[str]:
    """The ``keywords`` ``func`` does not take (none when it takes ``**kwargs``,
    or when its signature cannot be read: the call then says for itself).

    >>> def old(segments, rate, *, target_lufs): ...
    >>> lacks_keywords(old, ["target_lufs", "subject"])
    ['subject']
    >>> lacks_keywords(lambda *a, **kw: None, ["subject"])
    []
    """
    import inspect

    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return []
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return []
    return [k for k in keywords if k not in params]


def keywords_too_old(
    func: Callable[..., object], keywords: Iterable[str], *, needed_for: str
) -> str | None:
    """Why ``func`` (a function of ``mixing``) cannot serve ``needed_for``: the
    keywords of ``keywords`` it does not take, worded as a ``mixing`` too old;
    ``None`` when it takes them all.

    >>> def level_group(segments, rate): ...
    >>> level_group.__module__ = "mixing.loudness"
    >>> keywords_too_old(level_group, ["subject"], needed_for="testing")
    'testing needs mixing.loudness.level_group(subject=), which the installed mixing is too old to have: `pip install -U mixing`'
    """
    missing = lacks_keywords(func, keywords)
    if not missing:
        return None
    module = getattr(func, "__module__", MIXING)
    name = f"{module}.{getattr(func, '__qualname__', func)}"
    said = ", ".join(f"{k}=" for k in missing)
    return (
        f"{needed_for} needs {name}({said}), which the installed {MIXING} is too "
        f"old to have: `{UPGRADE_HINT}`"
    )


def mixing_problem() -> str | None:
    """Why the installed ``mixing`` cannot serve ``an``: a part it uses is
    missing (``mixing.loudness`` with ``group_lufs`` and ``GainCappedWarning``,
    an#699; ``mixing.filtergraph``), a keyword ``an`` passes is not taken
    (``level_group(subject=)``, an#765), or it is absent;
    ``None`` when it can. Asked of the code, not of a version number: an
    editable install's metadata keeps the version it was installed at (an#644).
    """
    try:
        with mixing_too_old(needed_for="an", error=RuntimeError):
            from mixing import loudness  # noqa: F401
            from mixing.filtergraph import resample_pitch_filter  # noqa: F401
            from mixing.loudness import GainCappedWarning, group_lufs  # noqa: F401
    except RuntimeError as e:
        return str(e)
    return keywords_too_old(loudness.level_group, LEVEL_GROUP_KEYWORDS, needed_for="an")


@lru_cache(maxsize=None)
def warn_if_mixing_too_old() -> None:
    """Say once per process, before anything is billed, that the installed
    ``mixing`` cannot serve ``an`` (:func:`mixing_problem`): the entry points
    that may bill (a render, ``an voices design``, ``audition`` and
    ``reroll``) call it, so an old ``mixing`` is not found after synthesis
    (an#644). :func:`mixing_too_old` stays the backstop at each import."""
    problem = mixing_problem()
    if problem:
        warnings.warn(problem, MixingTooOldWarning, stacklevel=3)
