"""``an init --id`` asks the library package where a new project goes (API level 7, reeleehq/cutan#91).

A library package registers ``projects.dir.<library>``
(:data:`an.genres.PROJECT_DIR_SERVICE_PREFIX`); the core computes its own
default (:func:`an.library.root.project_dir`) and hands it over, so a library
with nothing to say returns it unchanged. An explicit ``--root`` never consults
the service: the user said where. Core-only: no genre is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from an.genres import PROJECT_DIR_SERVICE_PREFIX
from an.genres.registry import register_service, unregister_owner
from an.library.root import project_dir
from an.tools import init as init_cli

LIBRARY = "demo_lib"
OWNER = "demo_lib_placement"


@pytest.fixture
def placed(tmp_path, monkeypatch):
    """A ``projects.dir.demo_lib`` service that records its call and answers elsewhere."""
    monkeypatch.setenv("DEMO_LIB_HOME", str(tmp_path / "roots" / LIBRARY))
    calls: list[tuple[str, Path]] = []

    def place(project_id: str, *, default: Path) -> Path:
        calls.append((project_id, default))
        return tmp_path / "elsewhere" / project_id

    register_service(PROJECT_DIR_SERVICE_PREFIX + LIBRARY, place, owner=OWNER)
    try:
        yield calls
    finally:
        unregister_owner(OWNER)


def test_the_library_package_places_the_project(tmp_path, placed):
    out = init_cli("p1", id=True, package=LIBRARY)
    assert out.endswith(str((tmp_path / "elsewhere" / "p1").resolve()))
    assert (tmp_path / "elsewhere" / "p1" / "scene.md").is_file()
    # The core's own answer travels with the call, computed by its own rule.
    assert placed == [("p1", project_dir("p1", package=LIBRARY))]


def test_an_explicit_root_is_the_users_word(tmp_path, placed):
    out = init_cli("p2", id=True, package=LIBRARY, root=str(tmp_path / "r"))
    assert out.endswith(str((tmp_path / "r" / "projects" / "p2").resolve()))
    assert placed == []


def test_a_bad_id_is_refused_before_any_service_runs(placed):
    with pytest.raises(SystemExit, match="one folder name"):
        init_cli("../escape", id=True, package=LIBRARY)
    assert placed == []


def test_no_service_means_the_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_LIB_HOME", str(tmp_path / "roots" / LIBRARY))
    out = init_cli("p3", id=True, package=LIBRARY)
    assert out.endswith(str((tmp_path / "roots" / LIBRARY / "projects" / "p3").resolve()))
