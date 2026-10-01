"""Modules that LEAVE the distribution (P8, an#225): `an._shims.moved_to_package`.

The old path must give the new module objects themselves (one copy: no class,
registry entry or document kind defined twice), for the package and every
submodule, each keeping its OWN spec; warn with its own category at the
importer's line; and fail with an actionable, typed error when the genre package
is absent or too old. The moves are also read STATICALLY -- by the shot-cache
code walk, the old-path guard and doctest collection -- and those readers are
held here too (review of an#298).
"""

from __future__ import annotations

import ast
import importlib
import importlib.resources
import importlib.util
import sys
import textwrap
import warnings
from pathlib import Path

import pytest

from an import _shims
from an._shims import (
    GenreNotInstalledError,
    GenrePackageTooOldError,
    MovedModuleWarning,
    declared_moves,
    moved_to_package,
)

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def _shim(new: str, **kwargs) -> str:
    extra = "".join(f", {k}={v!r}" for k, v in kwargs.items())
    return f"from an._shims import moved_to_package\nmoved_to_package(__name__, {new!r}{extra})\n"


@pytest.fixture
def tree(tmp_path, monkeypatch, request):
    """A fresh old/new package pair per test, cleaned out of sys.modules after."""
    tag = "".join(c if c.isalnum() else "_" for c in request.node.name)
    old, new = f"_mv_old_{tag}", f"_mv_new_{tag}"
    _write(tmp_path / new / "__init__.py", "WHERE = 'new'\n")
    _write(
        tmp_path / new / "sub.py",
        """
        KNOB = 1
        class Thing:
            pass
        def read_knob():
            return KNOB
        """,
    )
    _write(tmp_path / new / "inner" / "__init__.py", "")
    _write(tmp_path / new / "inner" / "deep.py", "X = 1\n")
    _write(tmp_path / new / "inner" / "data.txt", "payload\n")
    _write(tmp_path / old / "__init__.py", _shim(new))
    monkeypatch.syspath_prepend(str(tmp_path))
    yield old, new, tmp_path
    _shims._forget_move(old)
    for name in [m for m in sys.modules if m.split(".")[0] in (old, new)]:
        del sys.modules[name]


def _quietly(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MovedModuleWarning)
        return importlib.import_module(name)


# -- identity -----------------------------------------------------------------


def test_the_old_package_and_its_submodules_are_the_new_objects(tree):
    old, new, _ = tree
    with pytest.warns(MovedModuleWarning):
        pkg = importlib.import_module(old)
    with pytest.warns(MovedModuleWarning):
        sub = importlib.import_module(f"{old}.sub")
    assert pkg is importlib.import_module(new)
    assert sub is importlib.import_module(f"{new}.sub")
    assert importlib.import_module(old).sub is sub


def test_a_name_imported_through_the_old_path_is_the_same_class(tree):
    old, new, _ = tree
    assert _quietly(f"{old}.sub").Thing is importlib.import_module(f"{new}.sub").Thing


def test_rebinding_through_the_old_path_reaches_the_code_that_runs(tree, monkeypatch):
    old, new, _ = tree
    monkeypatch.setattr(_quietly(f"{old}.sub"), "KNOB", 7)
    assert importlib.import_module(f"{new}.sub").read_knob() == 7


# -- S1: the new module keeps its own spec ------------------------------------


def test_an_old_path_import_leaves_the_new_modules_spec_intact(tree):
    """`module_from_spec` overwrites `__spec__` with the OLD name's (no origin):
    `importlib.resources`, `find_spec(new).origin` (the shot-cache code walk)
    and `reload` all broke after one old-path import (review of an#298, S1)."""
    old, new, tmp = tree
    importlib.import_module(f"{new}.inner.deep")  # new path first: the harder case
    _quietly(f"{old}.inner.deep")
    deep = sys.modules[f"{new}.inner.deep"]
    assert deep.__spec__.name == f"{new}.inner.deep"
    assert importlib.util.find_spec(f"{new}.inner.deep").origin == str(tmp / new / "inner" / "deep.py")
    listed = {p.name for p in importlib.resources.files(f"{new}.inner").iterdir()}
    assert {"deep.py", "data.txt"} <= listed
    assert importlib.reload(deep).__name__ == f"{new}.inner.deep"


# -- errors: absent, too old, typo --------------------------------------------


def test_a_missing_genre_package_names_the_install_command(tmp_path, monkeypatch):
    _write(tmp_path / "_mv_orphan" / "__init__.py", _shim("_mv_not_installed_anywhere.characters"))
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(GenreNotInstalledError) as info:
        importlib.import_module("_mv_orphan")
    assert isinstance(info.value, ImportError)
    assert "an[cutout]" in str(info.value) and "_mv_not_installed_anywhere" in str(info.value)
    assert not isinstance(info.value, GenrePackageTooOldError)
    sys.modules.pop("_mv_orphan", None)


def test_an_installed_genre_package_without_the_target_is_too_old(tmp_path, monkeypatch):
    """`pip install -U an` with an older `cutan`: an upgrade hint, not
    "No module named" (review of an#298, M1)."""
    _write(tmp_path / "_mv_oldgenre" / "__init__.py", "")
    _write(tmp_path / "_mv_toonew" / "__init__.py", _shim("_mv_oldgenre.impacts", distribution="_mv_oldgenre"))
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(GenrePackageTooOldError) as info:
        importlib.import_module("_mv_toonew")
    assert "pip install -U _mv_oldgenre" in str(info.value)
    for name in ("_mv_toonew", "_mv_oldgenre"):
        sys.modules.pop(name, None)


def test_a_missing_module_inside_an_installed_package_is_not_an_install_problem(tree):
    old, _new, _ = tree
    _quietly(old)
    with pytest.raises(ModuleNotFoundError) as info:
        _quietly(f"{old}.no_such_submodule")
    assert not isinstance(info.value, GenreNotInstalledError)


# -- M2: the warning points at the importer ------------------------------------


@pytest.mark.parametrize("form", ["import old", "from old import sub", "import old.sub"])
def test_the_warning_is_attributed_to_the_importers_line(tree, form):
    """With Python's default filters a warning shows only where it is attributed;
    attributing it to the shim's own file made `from an.characters import X`
    silent outside pytest (review of an#298, M2)."""
    old, _new, _ = tree
    code = form.replace("old", old)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        exec(compile(code, str(HERE), "exec"), {"__name__": "an_importer_outside_an"})
    moved = [w for w in seen if issubclass(w.category, MovedModuleWarning)]
    assert moved, f"`{form}` warned nothing"
    assert all(Path(w.filename).resolve() == HERE for w in moved), [w.filename for w in moved]


# -- L1: longest prefix, per-submodule override --------------------------------


def test_a_package_move_can_send_one_submodule_elsewhere(tmp_path, monkeypatch):
    _write(tmp_path / "_mv_dst_a" / "__init__.py", "")
    _write(tmp_path / "_mv_dst_a" / "kept.py", "WHERE = 'a'\n")
    _write(tmp_path / "_mv_dst_b" / "__init__.py", "")
    _write(tmp_path / "_mv_dst_b" / "passes.py", "WHERE = 'b'\n")
    _write(
        tmp_path / "_mv_src" / "__init__.py",
        _shim("_mv_dst_a", submodules={"compile_passes": "_mv_dst_b.passes"}),
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert _quietly("_mv_src.kept").WHERE == "a"
        assert _quietly("_mv_src.compile_passes").WHERE == "b"
        assert declared_moves(tmp_path / "_mv_src") == {
            "_mv_src": "_mv_dst_a",
            "_mv_src.compile_passes": "_mv_dst_b.passes",
        }
    finally:
        _shims._forget_move("_mv_src")
        for name in [m for m in sys.modules if m.split(".")[0].startswith(("_mv_src", "_mv_dst_"))]:
            del sys.modules[name]


# -- the static readers ---------------------------------------------------------


def test_declared_moves_reads_source_and_never_imports(tmp_path):
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "gone" / "__init__.py", _shim("elsewhere.gone"))
    _write(tmp_path / "pkg" / "single.py", _shim("elsewhere.single"))
    _write(tmp_path / "pkg" / "mentions.py", '"""Calls moved_to_package(__name__, "x") in prose."""\n')
    assert declared_moves(tmp_path / "pkg") == {
        "pkg.gone": "elsewhere.gone",
        "pkg.single": "elsewhere.single",
    }
    assert "pkg" not in sys.modules


def test_doctest_collection_skips_moved_shims_and_only_them(tmp_path):
    """`--doctest-modules` would import a shim, which needs the genre package; a
    module that merely MENTIONS the call keeps its doctests (an AST match, not text)."""
    import an.conftest as an_conftest

    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "gone" / "__init__.py", _shim("elsewhere.gone"))
    _write(tmp_path / "pkg" / "single.py", _shim("elsewhere.single"))
    _write(tmp_path / "pkg" / "mentions.py", '"""moved_to_package(__name__, "x")"""\n')
    ignored = {Path(p).as_posix() for p in an_conftest._moved_shim_files(tmp_path / "pkg")}
    assert ignored == {"gone/__init__.py", "single.py"}


def test_the_shot_cache_walk_keys_a_b1_mover_under_its_new_name(tmp_path, monkeypatch):
    """`an.audio.offline_lipsync` is on today's render path and moves in B1.
    Once moved, the walk must key the code that RUNS (the new module, and what it
    imports in its own package), under any warnings filter, without importing the
    old name (review of an#298, S2; an#294)."""
    from an.stage import cache_key

    real = (ROOT / "an" / "audio" / "offline_lipsync.py").read_text(encoding="utf-8")
    _write(tmp_path / "_mv_genre" / "__init__.py", "")
    _write(tmp_path / "_mv_genre" / "audio" / "__init__.py", "")
    _write(tmp_path / "_mv_genre" / "audio" / "offline_lipsync.py", real + "\nfrom _mv_genre.audio import helper\n")
    _write(tmp_path / "_mv_genre" / "audio" / "helper.py", "X = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    moves = {"an.audio.offline_lipsync": "_mv_genre.audio.offline_lipsync"}
    looked_up = []
    original = cache_key._quiet_find_spec

    def recording(name):
        looked_up.append(name)
        return original(name)

    assert "an.audio.offline_lipsync" in cache_key.render_path_modules(moves={})  # today
    monkeypatch.setattr(cache_key, "_quiet_find_spec", recording)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        mods = cache_key.render_path_modules(moves=moves)
    assert "_mv_genre.audio.offline_lipsync" in mods
    assert "_mv_genre.audio.helper" in mods
    assert "an.audio.offline_lipsync" not in looked_up
    sys.modules.pop("_mv_genre", None)


# -- M3: nothing in `an` (or its tests) imports an old path ---------------------


#: Test files that import old paths ON PURPOSE (a compatibility test of a shim).
OLD_PATH_IMPORTERS_ALLOWED: frozenset[str] = frozenset()


def old_path_imports(paths, moves) -> list[str]:
    """``file:line -> name`` for every import of a moved name, by AST.

    The warning-as-error filter catches only the FIRST import of each old name
    in a process (later ones hit `sys.modules`), and `from old import name` may
    never warn at all; only a static pass gives "an never imports an old path"
    (review of an#298, M3).
    """
    out = []
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                if any(name == o or name.startswith(o + ".") for o in moves):
                    out.append(f"{path}:{node.lineno} -> {name}")
                    break
    return out


def test_the_old_path_guard_sees_every_import_form(tmp_path):
    src = tmp_path / "user.py"
    _write(src, "import an.gone.x\nfrom an.gone import y\nfrom an import gone\nimport an.kept\n")
    hits = old_path_imports([src], {"an.gone": "cutan.gone"})
    assert [h.split(":")[-1].split(" -> ")[1] for h in hits] == ["an.gone.x", "an.gone", "an.gone"]


def test_nothing_in_an_or_its_tests_imports_a_moved_path():
    moves = declared_moves()
    shim_files = {
        (ROOT / "an").joinpath(*m.split(".")[1:]) for m in moves
    }
    paths = [
        p
        for p in sorted([*(ROOT / "an").rglob("*.py"), *(ROOT / "tests").rglob("*.py")])
        if ".claude" not in p.relative_to(ROOT).parts
        and p.name not in OLD_PATH_IMPORTERS_ALLOWED
        and p.parent not in shim_files
        and p.with_suffix("") not in shim_files
    ]
    hits = old_path_imports(paths, moves)
    assert not hits, "import the new path instead:\n  " + "\n  ".join(hits)
