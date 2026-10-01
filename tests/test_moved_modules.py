"""Modules that LEAVE the distribution (P8, an#225): `an._shims.moved_to_package`.

The old path must give the new module objects themselves (one copy: no class,
registry entry or document kind defined twice), for the package and every
submodule; warn with its own category; and, when the genre package is absent,
fail with the install command instead of a bare "No module named".
"""

from __future__ import annotations

import importlib
import sys
import textwrap
import warnings

import pytest

from an import _shims
from an._shims import GenreNotInstalledError, MovedModuleWarning


@pytest.fixture
def moved_tree(tmp_path, monkeypatch, request):
    """An old package whose ``__init__`` is only the shim, and its new home."""
    tag = request.node.name.replace("[", "_").replace("]", "_")
    old, new = f"_mv_old_{tag}", f"_mv_new_{tag}"
    (tmp_path / new).mkdir()
    (tmp_path / new / "__init__.py").write_text("WHERE = 'new'\n")
    (tmp_path / new / "sub.py").write_text(
        textwrap.dedent(
            """
            KNOB = 1
            class Thing:
                pass
            def read_knob():
                return KNOB
            """
        )
    )
    (tmp_path / old).mkdir()
    (tmp_path / old / "__init__.py").write_text(
        f"from an._shims import moved_to_package\nmoved_to_package(__name__, {new!r})\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield old, new
    _shims._forget_move(old)
    for name in [m for m in sys.modules if m.split(".")[0] in (old, new)]:
        del sys.modules[name]


def test_the_old_package_and_its_submodules_are_the_new_objects(moved_tree):
    old, new = moved_tree
    with pytest.warns(MovedModuleWarning):
        pkg = importlib.import_module(old)
    with pytest.warns(MovedModuleWarning):
        sub = importlib.import_module(f"{old}.sub")
    assert pkg is importlib.import_module(new)
    assert sub is importlib.import_module(f"{new}.sub")
    assert getattr(importlib.import_module(old), "sub") is sub


def test_a_name_imported_through_the_old_path_is_the_same_class(moved_tree):
    old, new = moved_tree
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MovedModuleWarning)
        Thing = importlib.import_module(f"{old}.sub").Thing
    assert Thing is importlib.import_module(f"{new}.sub").Thing


def test_rebinding_through_the_old_path_reaches_the_code_that_runs(moved_tree, monkeypatch):
    old, new = moved_tree
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MovedModuleWarning)
        old_sub = importlib.import_module(f"{old}.sub")
    monkeypatch.setattr(old_sub, "KNOB", 7)
    assert importlib.import_module(f"{new}.sub").read_knob() == 7


def test_a_missing_genre_package_names_the_install_command(tmp_path, monkeypatch):
    (tmp_path / "_mv_orphan").mkdir()
    (tmp_path / "_mv_orphan" / "__init__.py").write_text(
        "from an._shims import moved_to_package\n"
        "moved_to_package(__name__, '_mv_not_installed_anywhere.characters')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(GenreNotInstalledError) as info:
        importlib.import_module("_mv_orphan")
    assert isinstance(info.value, ImportError)
    assert 'an[cutout]' in str(info.value) and "_mv_not_installed_anywhere" in str(info.value)
    sys.modules.pop("_mv_orphan", None)


def test_a_missing_module_inside_an_installed_package_is_not_an_install_problem(moved_tree):
    old, _new = moved_tree
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MovedModuleWarning)
        importlib.import_module(old)
        with pytest.raises(ModuleNotFoundError) as info:
            importlib.import_module(f"{old}.no_such_submodule")
    assert not isinstance(info.value, GenreNotInstalledError)


def test_doctest_collection_skips_moved_shims():
    """`--doctest-modules` imports every file under `an/`; a moved shim would
    import the genre package, absent in the core lane (`an/conftest.py`)."""
    from pathlib import Path

    conftest = (Path(__file__).resolve().parents[1] / "an" / "conftest.py").read_text()
    assert "moved_to_package(__name__," in conftest
