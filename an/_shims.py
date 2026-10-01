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
import sys
import types
from collections.abc import Iterable, Mapping

__all__ = ["forward_module_attributes", "forwarded_names"]

#: Attribute on a shimmed module holding ``{old name: (target module, new name)}``.
_FORWARDS_ATTR: str = "__an_forwards__"


class _ForwardingModule(types.ModuleType):
    """A module whose forwarded names live in another module."""

    def __getattr__(self, name: str):
        # Only reached for names NOT in the module's own namespace, which is
        # why `forward_module_attributes` deletes each forwarded name first.
        forwards = types.ModuleType.__getattribute__(self, "__dict__").get(
            _FORWARDS_ATTR, {}
        )
        if name in forwards:
            target, new_name = forwards[name]
            return getattr(importlib.import_module(target), new_name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value) -> None:
        forwards = self.__dict__.get(_FORWARDS_ATTR, {})
        if name in forwards:
            target, new_name = forwards[name]
            setattr(importlib.import_module(target), new_name, value)
            return
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        forwards = self.__dict__.get(_FORWARDS_ATTR, {})
        if name in forwards:
            target, new_name = forwards[name]
            delattr(importlib.import_module(target), new_name)
            return
        super().__delattr__(name)

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(self.__dict__.get(_FORWARDS_ATTR, {})))


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
