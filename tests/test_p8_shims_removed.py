"""The P8 import shims are gone (an#321): no old ``an`` path serves what moved to ``cutan``.

Everything the cut-out genre owns is imported from ``cutan`` (an#225). An old
module path is an ordinary missing module, and an old name on a module that
stayed is an ordinary missing attribute -- with or without ``cutan`` installed.
"""

from __future__ import annotations

import importlib

import pytest

#: The old module paths of what moved to ``cutan`` (an#225).
OLD_MODULES: tuple[str, ...] = (
    "an.characters",
    "an.expression",
    "an.impacts",
    "an.genre",
    "an.genres.cutout",
    "an.library.character",
    "an.verify.style",
    "an.audio.injectable_lipsync",
    "an.audio.offline_lipsync",
    "an.audio.rhubarb_lipsync",
    "an.audio.whisper_lipsync",
    "an.adapters.cutout.gaze",
    "an.adapters.cutout.coarticulate",
)

#: ``(module that stayed, name that moved)``.
OLD_NAMES: tuple[tuple[str, str], ...] = (
    ("an", "play"),
    ("an.ir", "play"),
    ("an.ir", "expression"),
    ("an.ir.compose", "default_play_extent"),
    ("an.ir.schema", "PlayAction"),
    ("an.ir.schema", "ExpressionAction"),
    ("an.audio", "OfflineLipSync"),
    ("an.verify", "StyleLintVerifier"),
    ("an.motion", "nod"),
    ("an.motion", "walk"),
)


@pytest.mark.parametrize("name", OLD_MODULES)
def test_an_old_module_path_is_not_found(name):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(name)


@pytest.mark.parametrize("module, name", OLD_NAMES)
def test_an_old_name_is_not_an_attribute(module, name):
    with pytest.raises(AttributeError):
        getattr(importlib.import_module(module), name)


def test_the_shim_module_keeps_only_the_within_core_aliases():
    from an import _shims

    assert set(_shims.__all__) == {
        "alias_module",
        "aliased_to",
        "forward_module_attributes",
        "forwarded_names",
    }
