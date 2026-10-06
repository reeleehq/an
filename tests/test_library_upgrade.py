"""Re-checking out a newer version of the same asset (an#346).

An entry pinned to an earlier version of the asset asked for — the same asset
by LINEAGE, never by name — is never copied beside. Without ``upgrade`` the
check-out refuses and names the command; with it an unedited entry is updated
in place (only the files the earlier version named are replaced) and the pin
moves; an edited one refuses either way. ``test_checkout_is_idempotent_and_never_clobbers_a_fork``
(tests/test_library.py) is the older rule this keeps, unchanged.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from an.library import CheckoutError, checkout, open_library, publish_dir
from an.library.cli import _link_command
from an.library.kits import checkout_kit, publish_kit
from an.project import init
from an.stores.library_lock import ProjectLock

ROOT = Path(__file__).resolve().parents[1]
LAMP = ROOT / "misc" / "bench" / "corpus" / "prop_swap" / "assets" / "props" / "lamp"
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


def _memory(name: str = "an"):
    return open_library(name, records={}, versions={}, blobs={})


def _art(tmp_path: Path, name: str, *, extra: bool = False, edit: str = "") -> Path:
    folder = Path(shutil.copytree(LAMP, tmp_path / "art" / name))
    if extra:
        (folder / "parts" / "extra.svg").write_text("<svg>extra</svg>", encoding="utf-8")
    if edit:
        (folder / "parts" / "on.svg").write_text(edit, encoding="utf-8")
    return folder


def _two_versions(tmp_path: Path, lib):
    """v001 (with an extra file) and v002 (on.svg redrawn, the extra dropped)."""
    publish_dir(lib, _art(tmp_path, "v1", extra=True), "prop.lamp-x", source=CC0)
    publish_dir(lib, _art(tmp_path, "v2", edit="<svg>lit</svg>"), "prop.lamp-x", source=CC0)


@pytest.fixture
def project(tmp_path):
    return init(tmp_path / "proj")


def _entry(project: Path, key: str = "lamp") -> Path:
    return project / "assets" / "props" / key


def test_an_unedited_older_copy_refuses_naming_upgrade_and_upgrade_updates_it_in_place(
    tmp_path, project
):
    lib = _memory()
    _two_versions(tmp_path, lib)
    assert checkout(lib, project, "an:prop.lamp-x@v001", key="lamp").key == "lamp"
    draft = _entry(project) / ".wip" / "draft.svg"
    draft.parent.mkdir()
    draft.write_text("<svg>mine</svg>", encoding="utf-8")
    with pytest.raises(CheckoutError, match="--upgrade"):
        checkout(lib, project, "an:prop.lamp-x@v002")
    assert not _entry(project, "lamp-x").exists()  # never a copy beside it
    result = checkout(lib, project, "an:prop.lamp-x@v002", upgrade=True)
    assert (result.key, result.changed) == ("lamp", True)
    assert ProjectLock(project)["props/lamp"]["library"] == "an:prop.lamp-x@v002"
    assert (_entry(project) / "parts" / "on.svg").read_text(encoding="utf-8") == "<svg>lit</svg>"
    assert not (_entry(project) / "parts" / "extra.svg").exists()  # the old version's file
    assert draft.read_text(encoding="utf-8") == "<svg>mine</svg>"  # never seen by drift: kept
    assert not _entry(project, "lamp-x").exists()


def test_an_edited_older_copy_refuses_with_or_without_upgrade(tmp_path, project):
    lib = _memory()
    _two_versions(tmp_path, lib)
    checkout(lib, project, "an:prop.lamp-x@v001", key="lamp")
    (_entry(project) / "parts" / "off.svg").write_text("<svg>forked</svg>", encoding="utf-8")
    for upgrade in (False, True):
        with pytest.raises(CheckoutError, match="publish it first"):
            checkout(lib, project, "an:prop.lamp-x@v002", upgrade=upgrade)
    assert not _entry(project, "lamp-x").exists()
    # The way out the refusal names.
    assert checkout(lib, project, "an:prop.lamp-x@v002", key="lamp", overwrite=True).changed


def test_the_folder_a_version_was_published_from_is_linked_and_the_hint_says_so(
    tmp_path, project
):
    lib = _memory()
    folder = Path(shutil.copytree(LAMP, _entry(project)))
    publish_dir(lib, folder, "prop.lamp-x", source=CC0)
    assert _link_command(project, folder, _ref("an:prop.lamp-x@v001")).endswith("--key lamp")
    checkout(lib, project, "an:prop.lamp-x@v001", key="lamp")
    (folder / "parts" / "on.svg").write_text("<svg>lit</svg>", encoding="utf-8")
    publish_dir(lib, folder, "prop.lamp-x")
    hint = _link_command(project, folder, _ref("an:prop.lamp-x@v002"))
    assert hint.endswith("--key lamp --upgrade")
    result = checkout(lib, project, "an:prop.lamp-x@v002")
    assert result.key == "lamp" and not _entry(project, "lamp-x").exists()
    assert ProjectLock(project)["props/lamp"]["library"] == "an:prop.lamp-x@v002"


def test_two_older_copies_refuse_unless_key_names_one(tmp_path, project):
    lib = _memory()
    _two_versions(tmp_path, lib)
    checkout(lib, project, "an:prop.lamp-x@v001", key="lamp")
    checkout(lib, project, "an:prop.lamp-x@v001", key="lamp-twin")
    with pytest.raises(CheckoutError, match="props/lamp, props/lamp-twin"):
        checkout(lib, project, "an:prop.lamp-x@v002", upgrade=True)
    assert checkout(lib, project, "an:prop.lamp-x@v002", key="lamp-twin", upgrade=True).key == "lamp-twin"
    assert ProjectLock(project)["props/lamp"]["library"] == "an:prop.lamp-x@v001"


def test_a_same_named_librarys_asset_is_never_taken_over(tmp_path, project):
    """Identity by lineage: another library named `an` holding prop.lamp-x is another asset."""
    mine, theirs = _memory(), _memory()
    publish_dir(mine, _art(tmp_path, "mine"), "prop.lamp-x", source=CC0)
    checkout(mine, project, "an:prop.lamp-x@v001", key="lamp")
    _two_versions(tmp_path, theirs)
    for upgrade in (False, True):
        with pytest.raises(CheckoutError, match="overwrite"):
            checkout(theirs, project, "an:prop.lamp-x@v002", key="lamp", upgrade=upgrade)
    assert ProjectLock(project)["props/lamp"]["library"] == "an:prop.lamp-x@v001"


def test_a_downgrade_is_not_an_upgrade(tmp_path, project):
    lib = _memory()
    _two_versions(tmp_path, lib)
    checkout(lib, project, "an:prop.lamp-x@v002", key="lamp")
    with pytest.raises(CheckoutError, match="overwrite"):
        checkout(lib, project, "an:prop.lamp-x@v001", key="lamp", upgrade=True)


def test_a_kit_member_is_upgraded_in_place_and_its_refusal_names_no_key(tmp_path, project):
    lib = _memory()
    publish_dir(lib, _art(tmp_path, "v1"), "prop.lamp-x", source=CC0)
    publish_kit(lib, "kit.desk", [("an:prop.lamp-x@v001", "lamp")], source=CC0)
    checkout_kit(lib, project, "an:kit.desk@v001")
    publish_dir(lib, _art(tmp_path, "v2", edit="<svg>lit</svg>"), "prop.lamp-x", source=CC0)
    publish_kit(lib, "kit.desk", [("an:prop.lamp-x@v002", "lamp")], source=CC0)
    with pytest.raises(CheckoutError, match="--upgrade") as refused:
        checkout_kit(lib, project, "an:kit.desk@v002")
    assert "--key" not in str(refused.value)
    checkout_kit(lib, project, "an:kit.desk@v002", upgrade=True)
    assert ProjectLock(project)["props/lamp"]["library"] == "an:prop.lamp-x@v002"


def _ref(text: str):
    from an.library.ids import parse_ref

    return parse_ref(text)
