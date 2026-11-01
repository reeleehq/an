"""Old import paths that stay LIVE after a move WITHIN ``an``: reads and rebinding reach the new home.

Only moves inside the distribution (an#247) keep an old path. A module that LEFT
for the ``cutan`` genre package (P8, an#225) has no old path any more (an#321):
import it from ``cutan``.

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
import sys
import types
from collections.abc import Iterable, Mapping

__all__ = [
    "alias_module",
    "aliased_to",
    "forward_module_attributes",
    "forwarded_names",
]

#: Attribute on a shimmed module holding ``{old name: (target module, new name)}``.
_FORWARDS_ATTR: str = "__an_forwards__"
#: Attribute on a WHOLE-module alias holding its target module's name.
_ALIAS_ATTR: str = "__an_alias_of__"


class _Forwarded:
    """A forwarded name as a data descriptor on its shimmed module's class:
    read, rebound and deleted on the target module.

    A data descriptor is what the name IS -- the alias holds no value of its
    own -- and it is what a tool that restores an attribute needs to see:
    pytest's ``monkeypatch`` (9.2+) reads the value to put back from the
    instance ``__dict__`` unless the type has a data descriptor for the name,
    so without one its ``undo`` DELETES the target's real global (an#690).
    """

    def __init__(self, target: str, name: str) -> None:
        self.target, self.name = target, name

    def __get__(self, module, owner=None):
        if module is None:
            return self
        return getattr(importlib.import_module(self.target), self.name)

    def __set__(self, module, value) -> None:
        setattr(importlib.import_module(self.target), self.name, value)

    def __delete__(self, module) -> None:
        delattr(importlib.import_module(self.target), self.name)


def _forwarding_class(module: types.ModuleType) -> type:
    """``module``'s own subclass of :class:`_ForwardingModule` (swapped in on
    first use), where its forwarded names are declared as descriptors."""
    cls = type(module)
    if cls is _ForwardingModule or not issubclass(cls, _ForwardingModule):
        cls = type(f"_ForwardingModule[{module.__name__}]", (_ForwardingModule,), {})
        module.__class__ = cls
    return cls


def _declare(module: types.ModuleType, forwards: Mapping[str, tuple[str, str]]) -> None:
    """Declare ``{old name: (target, new name)}`` as descriptors on ``module``'s class."""
    cls = _forwarding_class(module)
    for old, (target, new) in forwards.items():
        setattr(cls, old, _Forwarded(target, new))


def _route(module: types.ModuleType, name: str) -> tuple[str, str] | None:
    """Where ``name`` lives, if not on ``module``: a named forward, or the
    whole-module alias. A function, not a method: a method would be a class
    attribute a declared name of the same spelling could hide (an#690)."""
    own = types.ModuleType.__getattribute__(module, "__dict__")
    forwards = own.get(_FORWARDS_ATTR, {})
    if name in forwards:
        return forwards[name]
    alias = own.get(_ALIAS_ATTR)
    if alias is not None and not (name.startswith("__") and name.endswith("__")):
        return alias, name
    if alias is not None and name == "__all__":
        return alias, name
    return None


class _ForwardingModule(types.ModuleType):
    """A module whose forwarded names live in another module."""

    def __getattr__(self, name: str):
        # Only reached for names NOT in the module's own namespace, and not
        # declared: a name an aliased target gained after `alias_module`.
        route = _route(self, name)
        if route is None:
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")
        value = getattr(importlib.import_module(route[0]), route[1])
        if not name.startswith("__"):  # declared now, so a restore sees it (an#690)
            _declare(self, {name: route})
        return value

    def __setattr__(self, name: str, value) -> None:
        route = _route(self, name)
        if route is not None and name not in self.__dict__:
            setattr(importlib.import_module(route[0]), route[1], value)
            return
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        route = _route(self, name)
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
    forwards = dict(module.__dict__.get(_FORWARDS_ATTR, {}))
    for old, new in mapping.items():
        module.__dict__.pop(old, None)
        forwards[old] = (target, new)
    _declare(module, forwards)
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
    # Every name the target has now is declared (an#690); one it gains later
    # is still forwarded, through `__getattr__`.
    own = module.__dict__
    _declare(
        module,
        {
            name: (target, name)
            for name in {*vars(real), *forwarded_names(real)}  # a chain of shims
            if name not in own and not (name.startswith("__") and name.endswith("__"))
        },
    )
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
