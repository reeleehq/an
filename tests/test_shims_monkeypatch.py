"""An `an._shims` alias survives a monkeypatch's undo (an#690).

pytest 9.2's ``MonkeyPatch.setattr`` reads the value to restore from the
instance ``__dict__`` unless the type has a data descriptor for the name; a
forwarded name lives on the target module, so without one ``undo`` deleted the
target's real global and every later test failed on it. These tests run the
undo on whatever pytest is installed, and check the descriptor directly, so
they do not depend on the version.
"""

from __future__ import annotations

import inspect
import sys
import types

import pytest

from an._shims import alias_module, forward_module_attributes


@pytest.fixture
def modules():
    new = types.ModuleType("_shim_mp_new")
    new.KNOB, new.LATER = 1, None
    old = types.ModuleType("_shim_mp_old")
    whole = types.ModuleType("_shim_mp_whole")
    sys.modules.update({m.__name__: m for m in (new, old, whole)})
    forward_module_attributes("_shim_mp_old", "_shim_mp_new", {"OLD_KNOB": "KNOB"})
    alias_module("_shim_mp_whole", "_shim_mp_new")
    yield new, old, whole
    for m in (new, old, whole):
        del sys.modules[m.__name__]


def test_a_forwarded_name_is_a_data_descriptor_of_its_module(modules):
    _, old, whole = modules
    for module, name in ((old, "OLD_KNOB"), (whole, "KNOB")):
        attr = inspect.getattr_static(type(module), name)
        assert hasattr(type(attr), "__set__") and hasattr(type(attr), "__delete__")


def test_undoing_a_monkeypatch_on_an_alias_restores_the_target(modules):
    new, old, whole = modules
    for module, name in ((old, "OLD_KNOB"), (whole, "KNOB")):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(module, name, 99)
            assert new.KNOB == 99  # the lever reaches the global the code reads
        assert new.KNOB == 1 and getattr(module, name) == 1


def test_an_alias_of_a_shimmed_module_declares_the_names_it_forwards():
    """``an.adapters.cutout.render`` aliases ``an.stage.render``, whose
    ``DEFAULT_PIX_FMT`` is itself forwarded to ``an.media.mp4``: the chain
    survives an undo too."""
    import an.adapters.cutout.render as old
    import an.media.mp4 as mp4

    before = mp4.DEFAULT_PIX_FMT
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(old, "DEFAULT_PIX_FMT", "gray")
        assert mp4.DEFAULT_PIX_FMT == "gray"
    assert mp4.DEFAULT_PIX_FMT == before == old.DEFAULT_PIX_FMT


def test_two_aliases_do_not_share_their_declared_names(modules):
    _, old, whole = modules
    assert type(old) is not type(whole)
    assert "KNOB" not in vars(type(old)) and "OLD_KNOB" not in vars(type(whole))
