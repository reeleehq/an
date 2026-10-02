"""The shot cache's code key covers a genre's code (an#294, an#225).

A genre is reached by REGISTRATION (compile passes, lowerings, entity hooks,
services, runtime scripts), not by an import from ``an``, so the static walk from
the renderer cannot see it. Once the cut-out genre left for ``cutan``, a ``cutan``
upgrade that changed a pixel would otherwise leave the old cached shots valid:
the stale hit this key exists to prevent. A change to a genre package's source
must change :func:`an.stage.cache_key.render_code_digest`.
"""

from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

from an.genres import EntityKind, Genre, register_genre, without_genres
from an.stage import cache_key

_HOOKS = textwrap.dedent(
    '''
    def swap_declaration(entity, mall):
        return None  # VERSION
    '''
)


@pytest.fixture
def synthetic_genre(tmp_path, monkeypatch):
    """A genre package outside ``an`` that registers one entity-kind hook."""
    pkg = tmp_path / "_keygenre"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "hooks.py").write_text(_HOOKS, encoding="utf-8")
    (pkg / "unrelated.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    hooks = importlib.import_module("_keygenre.hooks")
    try:
        with without_genres():
            register_genre(
                Genre(
                    "keyed_genre",
                    entity_kinds=(EntityKind("widget", swap_declaration=hooks.swap_declaration),),
                )
            )
            yield pkg
    finally:
        for name in [m for m in sys.modules if m == "_keygenre" or m.startswith("_keygenre.")]:
            del sys.modules[name]


def test_a_genre_packages_modules_are_on_the_render_path(synthetic_genre):
    mods = cache_key.render_path_modules()
    assert {"_keygenre.hooks", "_keygenre.unrelated"} <= set(mods)


@pytest.mark.parametrize("module", ["hooks.py", "unrelated.py"])
def test_editing_a_genre_module_changes_the_code_key(synthetic_genre, module):
    """Any module of a package that registered a hook, not just the hook's own file:
    over-keying costs one re-render, under-keying serves a stale shot."""
    before = cache_key.render_code_digest()
    path = synthetic_genre / module
    path.write_text(path.read_text(encoding="utf-8") + "\n# an edit\n", encoding="utf-8")
    assert cache_key.render_code_digest() != before


def test_a_core_only_process_keys_no_genre_code():
    with without_genres():
        assert not [m for m in cache_key.render_path_modules() if m.startswith("_keygenre")]


@pytest.mark.genre("cutout_animation")
def test_the_cut_out_genres_code_is_in_the_key():
    """The real thing: ``cutan``'s compile passes, lowering and visuals script are keyed."""
    from an.genres import load

    load()
    mods = cache_key.render_path_modules()
    assert {"cutan.compile.passes", "cutan.compile.lowering", "cutan.characters.play"} <= set(mods)
