"""Old import paths that stay LIVE after a move: reads and rebinding both reach the new home.

A plain re-export (``from an.media.mp4 import DEFAULT_PIX_FMT``) copies a
*binding*. For a function or a class that is all an old path needs. For a module
global that something rebinds from outside it is a trap, and this repository
has several of them on purpose: the bench's levers rebind
``DETERMINISTIC_X264_ARGS`` and ``DEFAULT_PIX_FMT`` on the render module, and
tests rebind a module's own ``subprocess`` name or stub a seam such as
``_ensure_ffmpeg_available``. After a move the code that READS the global lives
in the new module, so a rebinding of the old path's copy changes nothing the
product reads -- silently: the lever still "applies", the test still runs, and
both measure the unchanged code. That is the failure the
``an-dev-render-pipeline`` skill warns about for a default argument, reached by
a different door.

:func:`forward_module_attributes` closes that door. The listed names are
removed from the old module's namespace, and the module's class is swapped for
one whose attribute access forwards them to the new module, so

- ``old.NAME`` and ``from old import NAME`` read the new module's CURRENT value;
- ``old.NAME = value`` (a lever, ``monkeypatch.setattr``) rebinds the new
  module's global, which is the one the product reads at call time.

>>> import sys, types
>>> new = types.ModuleType("_shim_demo_new"); new.KNOB = 1
>>> old = types.ModuleType("_shim_demo_old")
>>> sys.modules["_shim_demo_new"], sys.modules["_shim_demo_old"] = new, old
>>> forward_module_attributes("_shim_demo_old", "_shim_demo_new", {"OLD_KNOB": "KNOB"})
>>> old.OLD_KNOB
1
>>> old.OLD_KNOB = 2   # a lever pulled on the old path...
>>> new.KNOB           # ...reaches the global the new module reads
2
>>> del sys.modules["_shim_demo_new"], sys.modules["_shim_demo_old"]
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import types
import warnings
from collections.abc import Iterable, Mapping

__all__ = [
    "GenreNotInstalledError",
    "MovedModuleWarning",
    "alias_module",
    "aliased_to",
    "forward_module_attributes",
    "forwarded_names",
    "moved_to_package",
    "moved_targets",
]

#: Attribute on a shimmed module holding ``{old name: (target module, new name)}``.
_FORWARDS_ATTR: str = "__an_forwards__"
#: Attribute on a WHOLE-module alias holding its target module's name.
_ALIAS_ATTR: str = "__an_alias_of__"


class _ForwardingModule(types.ModuleType):
    """A module whose forwarded names live in another module."""

    def _route(self, name: str) -> tuple[str, str] | None:
        """Where ``name`` lives, if not here: a named forward, or the whole-module alias."""
        own = types.ModuleType.__getattribute__(self, "__dict__")
        forwards = own.get(_FORWARDS_ATTR, {})
        if name in forwards:
            return forwards[name]
        alias = own.get(_ALIAS_ATTR)
        if alias is not None and not (name.startswith("__") and name.endswith("__")):
            return alias, name
        if alias is not None and name == "__all__":
            return alias, name
        return None

    def __getattr__(self, name: str):
        # Only reached for names NOT in the module's own namespace, which is
        # why `forward_module_attributes` deletes each forwarded name first.
        route = self._route(name)
        if route is not None:
            return getattr(importlib.import_module(route[0]), route[1])
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value) -> None:
        route = self._route(name)
        if route is not None and name not in self.__dict__:
            setattr(importlib.import_module(route[0]), route[1], value)
            return
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        route = self._route(name)
        if route is not None and name not in self.__dict__:
            delattr(importlib.import_module(route[0]), route[1])
            return
        super().__delattr__(name)

    def __dir__(self) -> list[str]:
        return sorted(
            set(super().__dir__()) | set(self.__dict__.get(_FORWARDS_ATTR, {}))
        )


def forward_module_attributes(
    module_name: str, target: str, names: Iterable[str] | Mapping[str, str]
) -> None:
    """Make ``names`` on ``module_name`` live aliases of attributes of ``target``.

    ``names`` is an iterable of names kept as they are, or a mapping
    ``{old name: new name}`` for a name the move also renamed. Call it at the
    END of the old module (after anything that would otherwise rebind a
    forwarded name), with ``__name__``. Idempotent per name; a later call adds
    names, possibly towards another target.

    The module's own code must not read a forwarded name as a bare global: a
    function's global lookup goes to the module ``__dict__`` and never to
    ``__getattr__``, so it would raise ``NameError``. Read it through the
    target module (``_mp4.DEFAULT_PIX_FMT``), which is the point anyway.
    """
    module = sys.modules[module_name]
    mapping = dict(names) if isinstance(names, Mapping) else {n: n for n in names}
    importlib.import_module(target)  # fail now, not at first access
    if not isinstance(module, _ForwardingModule):
        module.__class__ = _ForwardingModule
    forwards = dict(module.__dict__.get(_FORWARDS_ATTR, {}))
    for old, new in mapping.items():
        module.__dict__.pop(old, None)
        forwards[old] = (target, new)
    types.ModuleType.__setattr__(module, _FORWARDS_ATTR, forwards)


def forwarded_names(module: types.ModuleType) -> dict[str, tuple[str, str]]:
    """``{old name: (target module, new name)}`` for a shimmed module, else ``{}``.

    >>> forwarded_names(types.ModuleType("plain"))
    {}
    """
    return dict(module.__dict__.get(_FORWARDS_ATTR, {}))


def alias_module(module_name: str, target: str) -> None:
    """Make the WHOLE module ``module_name`` a live alias of ``target``.

    For a module that moved as a whole (an#247: ``an/adapters/cutout/render.py``
    -> ``an/stage/render.py``). Every name the old module does not define itself
    is read from, and rebound on, ``target`` -- a lever, a ``monkeypatch``, a
    ``from old import name`` all reach the module the code now runs in. The
    old module keeps its own ``__name__`` and ``__spec__``; its ``__file__`` is
    the target's, so ``inspect.getsource(old)`` is the code that runs.

    Call it as the old module's last statement, with ``__name__``.

    >>> import sys, types
    >>> new = types.ModuleType("_alias_demo_new"); new.KNOB = 1
    >>> old = types.ModuleType("_alias_demo_old")
    >>> sys.modules["_alias_demo_new"], sys.modules["_alias_demo_old"] = new, old
    >>> alias_module("_alias_demo_old", "_alias_demo_new")
    >>> old.KNOB, aliased_to(old)
    (1, '_alias_demo_new')
    >>> old.KNOB = 3; new.KNOB
    3
    >>> del sys.modules["_alias_demo_new"], sys.modules["_alias_demo_old"]
    """
    module = sys.modules[module_name]
    real = importlib.import_module(target)  # fail now, not at first access
    if not isinstance(module, _ForwardingModule):
        module.__class__ = _ForwardingModule
    types.ModuleType.__setattr__(module, _ALIAS_ATTR, target)
    # The SOURCE of the old name is the new module's: `inspect.getsource(old)`
    # and anything reading `old.__file__` must see the code that runs, not
    # the three-line shim. (The import system's own record, `__spec__`, still
    # names the shim file; `an/conftest.py` keeps doctest collection off it.)
    if getattr(real, "__file__", None):
        types.ModuleType.__setattr__(module, "__file__", real.__file__)


def aliased_to(module: types.ModuleType) -> str | None:
    """The module a whole-module alias forwards to, else ``None``."""
    return module.__dict__.get(_ALIAS_ATTR)


# -----------------------------------------------------------------------------
# Moves OUT of the distribution: a module or package that now lives in a genre
# package (P8, an#225: `an.characters` -> `cutan.characters`).
# -----------------------------------------------------------------------------

#: The distribution a moved module goes to, by default (ADR 0001: the cut-out
#: genre package), and the ``an`` extra that installs it.
DFLT_MOVED_DISTRIBUTION: str = "cutan"
DFLT_MOVED_EXTRA: str = "cutout"


class MovedModuleWarning(DeprecationWarning):
    """An old ``an`` import path of a module that moved to a genre package.

    Its own class, so a test configuration can turn exactly this into an error
    (``an``'s own code must never import through an old path) without touching
    any other deprecation.
    """


class GenreNotInstalledError(ModuleNotFoundError):
    """An old ``an`` path names a module that moved to a package not installed here.

    A ``ModuleNotFoundError`` (so ``except ImportError`` still works), with the
    install command in its message rather than a bare "No module named".
    """


class _MovedFinder(importlib.abc.MetaPathFinder):
    """Maps every ``<old>.<sub>`` import to ``<new>.<sub>``, for each registered move."""

    def __init__(self) -> None:
        self.moves: dict[str, tuple[str, str, str]] = {}

    def find_spec(self, fullname, path=None, target=None):
        for old, (new, distribution, extra) in self.moves.items():
            if fullname.startswith(old + "."):
                loader = _MovedLoader(
                    fullname,
                    new + fullname[len(old) :],
                    distribution=distribution,
                    extra=extra,
                )
                return importlib.util.spec_from_loader(fullname, loader)
        return None


class _MovedLoader(importlib.abc.Loader):
    """Loads an old name as the NEW module object itself (no second copy)."""

    def __init__(self, old: str, new: str, *, distribution: str, extra: str) -> None:
        self.old, self.new = old, new
        self.distribution, self.extra = distribution, extra

    def create_module(self, spec):
        return _import_moved(
            self.old, self.new, distribution=self.distribution, extra=self.extra
        )

    def exec_module(self, module) -> None:
        """Nothing to run: the module was imported under its new name."""


_FINDER = _MovedFinder()


def _import_moved(
    old: str, new: str, *, distribution: str, extra: str
) -> types.ModuleType:
    top = new.split(".", 1)[0]
    try:
        module = importlib.import_module(new)
    except ModuleNotFoundError as e:
        # Only the ABSENT DISTRIBUTION gets the install hint; a missing module
        # inside an installed one is a real error and propagates as it is.
        if e.name == top and importlib.util.find_spec(top) is None:
            raise GenreNotInstalledError(
                f"`{old}` moved to `{new}`, in the `{distribution}` package, "
                f'which is not installed. Install it: pip install "an[{extra}]" '
                f"(or pip install {distribution}).",
                name=old,
            ) from e
        raise
    warnings.warn(
        f"`{old}` moved to `{new}` (the `{distribution}` package); import it from "
        "there. The old path is a live alias, removed once nothing imports it.",
        MovedModuleWarning,
        stacklevel=3,
    )
    return module


def moved_to_package(
    module_name: str,
    target: str,
    *,
    distribution: str = DFLT_MOVED_DISTRIBUTION,
    extra: str = DFLT_MOVED_EXTRA,
) -> None:
    """Make ``module_name`` -- and, for a package, every submodule of it -- the
    module ``target`` that now lives in another distribution.

    Call it as the ONLY statement of the old module (or the old package's
    ``__init__``), with ``__name__``. After it:

    - ``import old`` and ``import old.sub`` return the NEW module objects
      themselves (``old.sub is new.sub``): one copy, so no class, registry or
      document kind is ever defined twice, and rebinding a name (a lever,
      ``monkeypatch``) rebinds it where the code runs;
    - each old name warns once, with :class:`MovedModuleWarning`;
    - if ``distribution`` is not installed, the import raises
      :class:`GenreNotInstalledError` naming ``pip install "an[<extra>]"``.

    Unlike :func:`alias_module` the old file holds no code at all, which is
    what lets the code leave this distribution.

    >>> import sys, types, warnings
    >>> new = types.ModuleType("_moved_demo_new"); new.KNOB = 1
    >>> sys.modules["_moved_demo_new"] = new
    >>> sys.modules["_moved_demo_old"] = types.ModuleType("_moved_demo_old")
    >>> with warnings.catch_warnings(record=True) as seen:
    ...     warnings.simplefilter("always")
    ...     moved_to_package("_moved_demo_old", "_moved_demo_new", distribution="demo")
    >>> sys.modules["_moved_demo_old"] is new, seen[0].category.__name__
    (True, 'MovedModuleWarning')
    >>> moved_targets()["_moved_demo_old"]
    '_moved_demo_new'
    >>> _forget_move("_moved_demo_old")
    >>> del sys.modules["_moved_demo_new"], sys.modules["_moved_demo_old"]
    """
    module = _import_moved(module_name, target, distribution=distribution, extra=extra)
    _FINDER.moves[module_name] = (target, distribution, extra)
    if _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)
    # The import system re-reads `sys.modules[name]` after running the old
    # module's body, so this is what `import old` returns.
    sys.modules[module_name] = module


def moved_targets() -> dict[str, str]:
    """``{old module: new module}`` for every move registered in this process."""
    return {old: new for old, (new, _d, _e) in _FINDER.moves.items()}


def _forget_move(module_name: str) -> None:
    """Drop a registered move (tests and doctests only)."""
    _FINDER.moves.pop(module_name, None)
