"""Kits (an#226): a pinned set of library assets, checked out into a project in one call.

Temporary roots only: ``AN_HOME`` / ``CUTAN_HOME`` and ``XDG_DATA_HOME`` point
into ``tmp_path``, and the libraries are built in memory or under ``tmp_path``.
The members are synthetic: two doc-only assets (a style and a voice) and one
prop with a file.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.library import (
    CheckoutError,
    Kit,
    LibraryError,
    checkout,
    checkout_kit,
    open_library,
    publish,
    publish_kit,
    verify_checkout,
)
from an.library.lock import LOCKFILE_NAME, ProjectLock
from an.project import init as init_project
from an.stores import build_project_mall

CC0 = {"provider": "an-tests", "license": "cc0-1.0"}


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def library():
    lib = open_library("an", records={}, versions={}, blobs={})
    publish(lib, "style.noir", {"palette": ["#000", "#fff"]}, source=CC0)
    publish(lib, "voice.narrator", {"provider": "say", "voice_id": "x"}, source=CC0)
    publish(
        lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.svg": b"<svg/>"}, source=CC0
    )
    return lib


@pytest.fixture
def project(tmp_path):
    return init_project(tmp_path / "proj")


def _kit(library, **kwargs):
    return publish_kit(
        library,
        "kit.noir-base",
        ["style.noir", "voice.narrator", ("prop.lamp", "desk-lamp")],
        source=CC0,
        **kwargs,
    )


def test_a_kit_pins_latest_members_and_reads_back_as_a_document(library):
    publish(library, "style.noir", {"palette": ["#111"]}, source=CC0)  # -> v002
    result = _kit(library, note="what a noir short starts from")
    assert str(result.ref) == "an:kit.noir-base@v001"
    doc = Kit.model_validate(library.versions["kit.noir-base@v001"]["doc"])
    assert [(m.ref, m.key) for m in doc.members] == [
        ("style.noir@v002", None),
        ("voice.narrator@v001", None),
        ("prop.lamp@v001", "desk-lamp"),
    ]
    assert (doc.kind, doc.name, doc.note) == (
        "Kit",
        "noir-base",
        "what a noir short starts from",
    )
    # A later head of a member does not move the published kit version.
    publish(library, "style.noir", {"palette": ["#222"]}, source=CC0)
    assert Kit.model_validate(library.versions["kit.noir-base@v001"]["doc"]).members[
        0
    ].ref == ("style.noir@v002")


def test_the_kits_rights_are_its_own_and_not_its_members(library):
    publish(
        library,
        "style.carved",
        {"x": 1},
        source={"provider": "a-film", "license": "all-rights-reserved-private-study"},
    )
    r = publish_kit(library, "kit.mixed", ["style.carved"], source=CC0)
    assert r.rights.license_class == "free"
    assert (
        publish_kit(library, "kit.unsourced", ["style.noir"]).rights.license_class
        == "unknown"
    )


def test_publishing_the_same_kit_again_makes_no_version(library):
    _kit(library)
    assert _kit(library).created is False


def test_checkout_kit_lands_every_member_pinned_and_records_the_kit(library, project):
    _kit(library)
    results = checkout_kit(library, project, "kit.noir-base")
    assert [(r.store, r.key, r.changed) for r in results] == [
        ("styles", "noir", True),
        ("voices", "narrator", True),
        ("props", "desk-lamp", True),
    ]
    mall = build_project_mall(project)
    assert "noir" in mall["styles"] and "narrator" in mall["voices"]
    assert (project / "assets" / "props" / "desk-lamp" / "parts" / "lamp.svg").is_file()
    lock = ProjectLock(project)
    assert {k: lock[k]["library"] for k in lock} == {
        "styles/noir": "an:style.noir@v001",
        "voices/narrator": "an:voice.narrator@v001",
        "props/desk-lamp": "an:prop.lamp@v001",
    }
    record = lock.kits["kit.noir-base"]
    assert record["library"] == "an:kit.noir-base@v001"
    assert record["members"] == ["styles/noir", "voices/narrator", "props/desk-lamp"]
    on_disk = json.loads((project / LOCKFILE_NAME).read_text(encoding="utf-8"))
    assert set(on_disk) == {"kind", "schema_version", "assets", "kits"}
    # The pins stay verifiable; the kit section is not mistaken for a pin.
    assert verify_checkout(library, project) == {
        "styles/noir": [],
        "voices/narrator": [],
        "props/desk-lamp": [],
    }


def test_a_lockfile_without_kits_reads_and_writes_as_before(library, project):
    checkout(library, project, "style.noir")
    assert set(json.loads((project / LOCKFILE_NAME).read_text())) == {
        "kind",
        "schema_version",
        "assets",
    }
    ProjectLock(project).kits["kit.x"] = {"library": "an:kit.x@v001"}
    checkout(library, project, "voice.narrator")  # an asset write keeps the kits
    assert ProjectLock(project).kits["kit.x"] == {"library": "an:kit.x@v001"}


def test_checking_out_the_same_kit_twice_is_idempotent(library, project):
    _kit(library)
    checkout_kit(library, project, "kit.noir-base")
    before = (project / LOCKFILE_NAME).read_text(encoding="utf-8")
    again = checkout_kit(library, project, "kit.noir-base")
    assert [r.changed for r in again] == [False, False, False]
    assert (project / LOCKFILE_NAME).read_text(encoding="utf-8") == before


def test_a_missing_member_writes_nothing(library, project):
    doc = {"kind": "Kit", "schema_version": "0.1.0", "name": "ghosty"}
    members = [
        {"ref": "style.noir@v001", "key": None},
        {"ref": "voice.ghost@v001", "key": None},
    ]
    publish(library, "kit.ghosty", {**doc, "members": members}, source=CC0)
    with pytest.raises(CheckoutError, match="voice.ghost@v001 cannot be found"):
        checkout_kit(library, project, "kit.ghosty")
    assert not (project / LOCKFILE_NAME).exists()
    assert list(build_project_mall(project)["styles"]) == []


def test_a_fork_among_the_members_refuses_the_kit_before_anything_is_written(
    library, project
):
    _kit(library)
    mall = build_project_mall(project, ensure=True)
    mall["props"]["desk-lamp"] = {"name": "my own lamp"}
    with pytest.raises(CheckoutError, match="props/desk-lamp"):
        checkout_kit(library, project, "kit.noir-base")
    assert list(mall["styles"]) == [] and not (project / LOCKFILE_NAME).exists()
    results = checkout_kit(library, project, "kit.noir-base", overwrite=True)
    assert len(results) == 3


def test_a_nested_kit_is_refused_at_publish_and_at_checkout(library, project):
    _kit(library)
    with pytest.raises(LibraryError, match="kits do not nest"):
        publish_kit(library, "kit.outer", ["kit.noir-base"], source=CC0)
    # A hand-written document that nests is refused by the check-out.
    publish(
        library,
        "kit.sneaky",
        {
            "kind": "Kit",
            "schema_version": "0.1.0",
            "name": "sneaky",
            "members": [{"ref": "kit.noir-base@v001", "key": None}],
        },
        source=CC0,
    )
    with pytest.raises(CheckoutError, match="kits do not nest"):
        checkout_kit(library, project, "kit.sneaky")
    assert not (project / LOCKFILE_NAME).exists()


def test_two_members_for_one_slot_are_refused(library):
    with pytest.raises(LibraryError, match="styles/noir"):
        publish_kit(library, "kit.twice", ["style.noir@v001", "style.noir"])
    publish_kit(
        library, "kit.beside", ["style.noir", ("style.noir", "noir-2")], source=CC0
    )


def test_publish_refuses_what_cannot_be_checked_out(library):
    publish(library, "motion.walk", {"x": 1}, source=CC0)
    with pytest.raises(LibraryError, match="no project store"):
        publish_kit(library, "kit.m", ["motion.walk"], source=CC0)
    with pytest.raises(LibraryError, match="cannot be found"):
        publish_kit(library, "kit.m", ["style.nope"], source=CC0)
    with pytest.raises(LibraryError, match="at least one"):
        publish_kit(library, "kit.m", [], source=CC0)


def test_checkout_of_a_kit_points_at_checkout_kit(library, project):
    _kit(library)
    with pytest.raises(CheckoutError, match="checkout_kit"):
        checkout(library, project, "kit.noir-base")
    with pytest.raises(CheckoutError, match="not a kit"):
        checkout_kit(library, project, "style.noir")


def test_members_resolve_in_the_kits_own_library_first_then_the_search_path(
    tmp_path, project
):
    core = open_library("an", records={}, versions={}, blobs={})
    study = open_library("cutan", records={}, versions={}, blobs={})
    publish(core, "style.noir", {"from": "core"}, source=CC0)
    publish(study, "style.noir", {"from": "study"}, source=CC0)
    publish(core, "voice.narrator", {"provider": "say"}, source=CC0)
    publish_kit(
        study,
        "kit.base",
        ["style.noir", "voice.narrator"],
        search=[core],
        source=CC0,
    )
    refs = [m["ref"] for m in study.versions["kit.base@v001"]["doc"]["members"]]
    assert refs == ["style.noir@v001", "an:voice.narrator@v001"]
    checkout_kit([core, study], project, "cutan:kit.base")
    assert build_project_mall(project)["styles"]["noir"]["from"] == "study"
    assert ProjectLock(project)["voices/narrator"]["library"] == (
        "an:voice.narrator@v001"
    )


def test_the_cli_publishes_and_checks_out_a_kit(tmp_path, project):
    runner = CliRunner()
    app = build_app()
    lib = open_library("an")
    publish(lib, "style.noir", {"palette": ["#000"]}, source=CC0)
    publish(
        lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.svg": b"<svg/>"}, source=CC0
    )
    r = runner.invoke(
        app,
        [
            "library",
            "kit",
            "an",
            "kit.noir-base",
            "style.noir,prop.lamp",
            "--key-for",
            "prop.lamp=desk-lamp",
            "--license",
            "cc0-1.0",
            "--provider",
            "an-tests",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "an:kit.noir-base@v001 [free]" in r.output
    assert "prop.lamp@v001 as desk-lamp" in r.output
    r = runner.invoke(app, ["library", "checkout", str(project), "kit.noir-base"])
    assert r.exit_code == 0, r.output
    assert "kit kit.noir-base: 2 members" in r.output
    assert "checked out: an:prop.lamp@v001 -> props/desk-lamp" in r.output
    # Only castable entities get a line; a style is not an entity.
    assert "- {id: desk-lamp, kind: prop, store: props, ref: desk-lamp" in r.output
    assert "id: noir" not in r.output
    assert ProjectLock(project).kits["kit.noir-base"]["members"] == [
        "styles/noir",
        "props/desk-lamp",
    ]
    r = runner.invoke(
        app, ["library", "checkout", str(project), "kit.noir-base", "--key", "x"]
    )
    assert r.exit_code == 1 and "--key" in r.output
    r = runner.invoke(
        app,
        ["library", "kit", "an", "kit.bad", "style.noir", "--key-for", "voice.x=y"],
    )
    assert r.exit_code == 1 and "--key-for" in r.output
