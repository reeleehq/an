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
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError:
        return
    # A checkout that ran the old package keeps its untracked `__pycache__/`
    # folder, which imports as an empty namespace package: nothing is served.
    assert getattr(module, "__file__", None) is None, f"{name} still serves code"


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


def test_a_genre_that_imports_a_removed_path_is_told_to_upgrade(tmp_path, monkeypatch):
    """An old cutan with this an: the entry point does not import; say what to do."""
    import sys
    import textwrap
    from importlib.metadata import EntryPoint

    from an import genres

    (tmp_path / "old_genre_pkg.py").write_text(
        textwrap.dedent("import an.characters  # a path an no longer serves\nGENRE = None\n"),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("old_genre_pkg", None)
    ep = EntryPoint("old", "old_genre_pkg:GENRE", genres.ENTRY_POINT_GROUP)
    with pytest.raises(genres.GenreError, match="upgrade the genre package"):
        genres._resolve(ep)
