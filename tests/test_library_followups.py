"""The asset library's follow-ups after P5: pins in ``an validate``, the root registry, the end-user test's UX.

- an#240: the lockfile is a project store (``mall["library_lock"]``) and the
  single source of truth for a pin; ``an validate`` reports a scene ``library:``
  that disagrees with it, and an edited check-out as ``info``.
- an#249: a machine registry of library roots, independent of the environment,
  so private bytes in a library at a custom root (or under a since-changed
  ``<PKG>_HOME`` / ``XDG_DATA_HOME``) still bind every other library — plus the
  review's ride-along nits R4-N1..N4.
- an#251: ``an init --id``, namespaced check-out with no ``--package``, publish
  then check out into the same project, the factory's descriptor-level stamp,
  and ``an credits`` wording.

Temporary roots only: the library roots point into ``tmp_path``, and the root
``conftest.py`` points the registry there too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.characters.factory import (
    FACTORY_PROVIDER,
    new_character,
    stamp_factory_parts,
)
from an.characters.validate import validate_character
from an.credits import collect_credits
from an.library import (
    RightsRefusal,
    checkout,
    open_library,
    promote,
    publish,
    publish_dir,
)
from an.library import api as library_api
from an.library import registry
from an.library.floor import BlobFloor, machine_libraries
from an.library.lock import ProjectLock
from an.library.registry import RegistryError, register_root, registered_roots
from an.orchestrate import validate_project
from an.project import init as init_project
from an.stores import build_project_mall
from an.tools import init as init_cli

PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
CARVED = b"\x89PNG carved from a film, frame 1204"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def project(tmp_path) -> Path:
    return init_project(tmp_path / "proj")


def _run(*args: str):
    return runner.invoke(build_app(), list(args))


def _cast(project: Path, *, library: str | None) -> None:
    pin = f', library: "{library}"' if library else ""
    (project / "scene.md").write_text(
        "# Cast\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1.0\n```\n\n"
        "```yaml entities\n"
        f"- {{id: alice, kind: character, store: characters, ref: alice{pin}}}\n"
        "```\n",
        encoding="utf-8",
    )


def _library_findings(report) -> list:
    return [
        f
        for f in report.findings
        if "library" in f.ir_path or f.ir_path.startswith("assets.lock.json")
    ]


def _published_alice(tmp_path: Path, *, versions: int = 1):
    """A factory character published to the on-disk ``cutan`` library."""
    folder = new_character(tmp_path / "art", name="alice", use_dicebear=False).parent
    lib = open_library("cutan")
    publish_dir(lib, folder, "character.alice")
    for n in range(2, versions + 1):
        (folder / "notes.txt").write_text(f"take {n}", encoding="utf-8")
        publish_dir(lib, folder, "character.alice")
    return lib, folder


# ============================================================ an#240: the pin


def test_the_lockfile_is_a_project_store_and_checkout_writes_through_it(
    tmp_path, project
):
    mall = build_project_mall(project)
    assert isinstance(mall["library_lock"], ProjectLock)
    lib, _ = _published_alice(tmp_path)
    injected: dict = {}
    checkout(lib, project, "cutan:character.alice@v001", mall={**mall, "library_lock": injected})
    assert injected["characters/alice"]["library"] == "cutan:character.alice@v001"
    assert not (project / "assets.lock.json").exists()  # the mall's store, not a side file


def test_a_cast_checkout_validates_clean(tmp_path, project):
    lib, _ = _published_alice(tmp_path)
    result = checkout(lib, project, "cutan:character.alice@v001")
    _cast(project, library=result.asset_ref().library)
    report = validate_project(project)
    assert report.passed
    assert report.findings == []


def test_validate_reports_a_stale_library_pin(tmp_path, project):
    """The end-user test's costly miss: the scene said v001, files and lockfile v002."""
    lib, _ = _published_alice(tmp_path, versions=2)
    checkout(lib, project, "cutan:character.alice@v002")
    _cast(project, library="cutan:character.alice@v001")
    findings = _library_findings(validate_project(project))
    assert [(f.severity, f.ir_path) for f in findings] == [
        ("warning", "timeline/0/entities/0/library")
    ]
    assert "checked out from cutan:character.alice@v002" in findings[0].description
    assert 'set library: "cutan:character.alice@v002"' in findings[0].description


def test_validate_reports_a_library_pin_the_lockfile_does_not_hold(project):
    _cast(project, library="cutan:character.alice@v001")
    findings = _library_findings(validate_project(project))
    assert [f.severity for f in findings] == ["warning"]
    assert "not pinned in the lockfile" in findings[0].description


def test_validate_reports_an_edited_checkout_as_info(tmp_path, project):
    lib, _ = _published_alice(tmp_path)
    checkout(lib, project, "cutan:character.alice@v001")
    _cast(project, library=None)
    (project / "assets" / "characters" / "alice" / "parts" / "head.svg").write_text(
        "<svg>re-drawn</svg>", encoding="utf-8"
    )
    report = validate_project(project)
    findings = _library_findings(report)
    assert report.passed
    assert [(f.severity, f.ir_path) for f in findings] == [
        ("info", "assets.lock.json/characters/alice")
    ]
    assert "parts/head.svg edited" in findings[0].description


def test_an_unreadable_lockfile_is_a_finding_not_a_traceback(project):
    _cast(project, library="cutan:character.alice@v001")
    (project / "assets.lock.json").write_text("{not json", encoding="utf-8")
    findings = _library_findings(validate_project(project))
    assert [f.ir_path for f in findings] == ["assets.lock.json"]
    assert "cannot be read" in findings[0].description


# ============================================================ an#249: the registry


def test_private_bytes_at_a_custom_root_bind_after_the_environment_changes(
    tmp_path, monkeypatch
):
    """R4-S1, as the issue states it: publish private at an explicit root, unset
    every ``*_HOME``, change ``XDG_DATA_HOME``, then publish the same bytes as
    cc0 into ``an``: it must come out ``private``."""
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    for var in ("AN_HOME", "CUTAN_HOME"):
        monkeypatch.delenv(var)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "elsewhere"))
    core = open_library("an")
    stool = publish(core, "prop.stool", {"name": "stool"}, {"parts/stool.png": CARVED}, source=CC0)
    assert stool.rights.license_class == "private"
    assert any("same bytes as cutan:prop.chair@v001" in r for r in stool.rights.reasons)
    with pytest.raises(RightsRefusal):
        promote([core], "prop.stool", to=open_library("teamshare", root=tmp_path / "share"))


def test_without_the_registry_the_same_bytes_would_escape(tmp_path, monkeypatch):
    """The control for the test above: the registry is what closes it."""
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    monkeypatch.setattr(registry, "machine_registry_path", lambda: tmp_path / "empty.jsonl")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "elsewhere"))
    stool = publish(open_library("an"), "prop.stool", {"name": "s"}, {"parts/s.png": CARVED}, source=CC0)
    assert stool.rights.license_class == "free"


def test_the_registry_location_ignores_the_environment(monkeypatch, tmp_path):
    before = registry._account_home()
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "fake-xdg"))
    monkeypatch.setenv("AN_HOME", str(tmp_path / "fake-an"))
    assert registry._account_home() == before


def test_a_write_the_registry_cannot_record_is_refused(tmp_path, monkeypatch):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setattr(
        registry, "machine_registry_path", lambda: blocker / "reg" / "roots.jsonl"
    )
    lib = open_library("cutan", root=tmp_path / "study-lib")
    with pytest.raises(RegistryError, match="nothing was written"):
        publish(lib, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    assert "prop.chair" not in lib.records
    assert len(lib.blobs) == 0


def test_registered_roots_that_vanished_are_skipped(tmp_path):
    reg = tmp_path / "roots.jsonl"
    register_root("cutan", tmp_path / "gone", registry=reg)
    with reg.open("a", encoding="utf-8") as f:
        f.write('{"package": "cutan", "ro')  # a torn last line
    assert [r.name for _, r in registered_roots(registry=reg)] == ["gone"]
    assert all(lib.root != tmp_path / "gone" for lib in machine_libraries())


def test_reindex_registers_a_library_made_before_the_registry(tmp_path, monkeypatch):
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    fresh = tmp_path / "fresh-registry.jsonl"
    monkeypatch.setattr(registry, "machine_registry_path", lambda: fresh)
    assert list(registered_roots()) == []
    library_api.reindex(study)
    assert [(p, r) for p, r in registered_roots()] == [
        ("cutan", (tmp_path / "study-lib").resolve())
    ]


def test_two_libraries_sharing_a_name_keep_the_stricter_statement(tmp_path):
    """The default ``cutan`` and a registered ``cutan`` at a custom root can hold
    the same asset key; the floor keeps the stricter statement, not the later."""
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    default = open_library("cutan")
    for n in range(3):  # a higher version number, a looser statement
        publish(default, "prop.chair", {"name": f"chair {n}"}, {"parts/chair.png": CARVED},
                relicense={"by": "tests", "reason": "a looser twin"} if n == 2 else None,
                source=CC0)
    digest = library_api.ContentRef.from_json(
        library_api.read_version(study, "prop.chair", "v001")["files"]["parts/chair.png"]
    ).item_id
    statements = BlobFloor([default, study], discover=False).statements(digest)
    assert statements["cutan:prop.chair"]["class"] == "private"


def test_reindex_never_empties_the_floor_midway(tmp_path, monkeypatch):
    """R4-N4: a crash while rebuilding leaves the old statements in place."""
    lib = open_library("cutan", root=tmp_path / "study-lib")
    publish(lib, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    publish(lib, "prop.desk", {"name": "desk"}, {"parts/desk.png": b"desk"}, source=PRIVATE)
    store = lib.blob_rights
    before = {d: store[d] for d in store}
    real_setitem = type(store).__setitem__
    calls = []

    def crash_after_one(self, key, value):
        calls.append(key)
        if len(calls) > 1:
            raise RuntimeError("power cut")
        return real_setitem(self, key, value)

    monkeypatch.setattr(type(store), "__setitem__", crash_after_one)
    with pytest.raises(RuntimeError):
        library_api.reindex(lib)
    monkeypatch.undo()
    assert set(before) <= set(lib.blob_rights)


def test_a_version_label_is_computed_once_however_many_files(monkeypatch):
    """R4-N3: the asset label walks the lineage; it is the same for every file."""
    lib = open_library("cutan", records={}, versions={}, blobs={})
    calls = []
    real = library_api._own_label_class

    def counting(libraries, version):
        calls.append(version.get("version"))
        return real(libraries, version)

    monkeypatch.setattr(library_api, "_own_label_class", counting)
    files = {f"parts/p{i}.png": f"part {i}".encode() for i in range(12)}
    publish(lib, "prop.kit", {"name": "kit"}, files, source=PRIVATE)
    assert calls == ["v001"]


# ------------------------------------------------- R4-N1, R4-N2: factory stamps


def test_stamping_names_the_parts_it_drew(tmp_path):
    """R4-N1: no default that re-stamps a re-carved part as the factory's cc0."""
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    with pytest.raises(TypeError):
        stamp_factory_parts(char)  # type: ignore[call-arg]
    (char / "parts" / "head.svg").write_bytes(CARVED)
    stamp_factory_parts(char, {"parts/torso.svg"})
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    heads = [
        att["source"]["sha256"]
        for skin in doc["skins"].values()
        for slot in skin["slots"].values()
        for att in slot.values()
        if att["path"] == "parts/head.svg"
    ]
    assert heads and all(h != library_api.content_hash(CARVED) for h in heads)


def test_credits_check_a_factory_stamp_against_its_file(tmp_path, project):
    """R4-N2: a stale stamp no longer hides a re-carved part from `an credits`."""
    new_character(project / "assets" / "characters", name="amy", use_dicebear=False)
    mall = build_project_mall(project)
    assert all(e.own_work for e in collect_credits(mall).entries)
    (project / "assets" / "characters" / "amy" / "parts" / "head.svg").write_bytes(CARVED)
    unverified = collect_credits(mall).unverified
    assert [e.asset for e in unverified] == ["characters/amy/parts/head.svg"]
    assert "no longer matches" in unverified[0].source.extra["reason"]


# ============================================================ an#251: UX


def test_init_by_id_lands_under_the_genre_root(tmp_path):
    out = init_cli("alice-and-bob", id=True)
    assert out.endswith(str((tmp_path / "roots" / "cutan" / "projects" / "alice-and-bob").resolve()))
    out = init_cli("explainer", id=True, package="an")
    assert out.endswith(str((tmp_path / "roots" / "an" / "projects" / "explainer").resolve()))
    with pytest.raises(SystemExit, match="one folder name"):
        init_cli("../escape", id=True)
    r = _run("init", "--id", "from-the-shell")
    assert r.exit_code == 0, r.output
    assert (tmp_path / "roots" / "cutan" / "projects" / "from-the-shell" / "scene.md").is_file()


def test_a_namespaced_reference_selects_its_library_without_package(tmp_path, project):
    """The skill's own example, `an library checkout . cutan:character.x@v001`."""
    _published_alice(tmp_path)
    r = _run("library", "checkout", str(project), "cutan:character.alice@v001")
    assert r.exit_code == 0, r.output
    assert 'library: "cutan:character.alice@v001"' in r.output
    r = _run("library", "show", "cutan:character.alice")
    assert r.exit_code == 0 and "cutan:character.alice@v001" in r.output


def test_publish_then_checkout_into_the_same_project_links_it(project):
    """The natural first flow on an empty library: the published folder IS the version."""
    folder = new_character(project / "assets" / "characters", name="alice", use_dicebear=False).parent
    r = _run("library", "publish", str(folder), "character.alice", "--package", "cutan")
    assert r.exit_code == 0, r.output
    assert f"an library checkout {project} cutan:character.alice@v001" in r.output
    r = _run("library", "checkout", str(project), "cutan:character.alice@v001")
    assert r.exit_code == 0, r.output
    assert ProjectLock(project)["characters/alice"]["library"] == "cutan:character.alice@v001"
    # unedited, it publishes back as the same version
    lib = open_library("cutan")
    assert not publish_dir(lib, folder, "character.alice").created
    # an edit is a fork: refused, and the refusal names the CLI flags
    (folder / "parts" / "head.svg").write_text("<svg>edited</svg>", encoding="utf-8")
    r = _run("library", "checkout", str(project), "cutan:character.alice@v001")
    assert r.exit_code != 0
    assert "--overwrite" in r.output and "--key" in r.output


def test_a_fresh_character_passes_its_own_provenance_check(tmp_path):
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    report = validate_character(char)
    assert not [f for f in report.findings if "AssetSource" in f.description]
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    assert doc["source"]["provider"] == FACTORY_PROVIDER
    assert doc["source"]["sha256"] == library_api.content_hash((char / "amy.svg").read_bytes())


def test_the_factory_stamp_speaks_only_for_the_bytes_it_drew(tmp_path):
    """The descriptor stamp makes a pristine character free with no flags — and
    never a re-carved one: a file no stamp pins is unknown in the library."""
    lib = open_library("cutan")
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    assert publish_dir(lib, char, "character.amy").rights.license_class == "free"
    (char / "parts" / "head.svg").write_bytes(CARVED)
    carved = publish_dir(lib, char, "character.amy-carved")
    assert carved.rights.license_class == "unknown"
    assert any("parts/head.svg" in r for r in carved.rights.reasons)
    private = publish_dir(lib, char, "character.amy-study", source=PRIVATE)
    assert private.rights.license_class == "private"
    # a file no stamp ever named (added by hand) is not the factory's either
    fresh = new_character(tmp_path / "b", name="bea", use_dicebear=False).parent
    (fresh / "parts" / "hat.png").write_bytes(b"a hat nobody labelled")
    added = publish_dir(lib, fresh, "character.bea-hat")
    assert added.rights.license_class == "unknown"
    assert any("parts/hat.png" in r for r in added.rights.reasons)


def test_credits_after_a_v002_checkout_list_each_obligation_once(tmp_path, project):
    """an#251 item 5: a previous version that says exactly what the copy says is
    not a second credit, and a generated character is not "third-party"."""
    folder = new_character(tmp_path / "art", name="alice", use_dicebear=False).parent
    lib = open_library("cutan")
    publish_dir(lib, folder, "character.alice", source=CC0)
    (folder / "notes.txt").write_text("v2", encoding="utf-8")
    publish_dir(lib, folder, "character.alice")
    checkout(lib, project, "cutan:character.alice@v002")
    report = collect_credits(build_project_mall(project))
    assert [e.asset for e in report.entries] == ["characters/alice"]
    new_character(project / "assets" / "characters", name="bob", use_dicebear=False)
    text = collect_credits(build_project_mall(project)).format()
    assert text.splitlines()[0] == (
        "credits: 1 third-party asset(s); 1 asset(s) made by an itself (nothing owed)."
    )


def test_a_claim_that_only_names_the_factory_is_not_its_stamp():
    """Only the factory's own record (its provider AND its cc0) gives way to an
    asset-level source; a private licence under the factory's name still binds."""
    lib = open_library("cutan", records={}, versions={}, blobs={})
    doc = {"name": "lamp", "source": {"provider": FACTORY_PROVIDER, "license": "all-rights-reserved"}}
    r = publish(lib, "prop.lamp", doc, {"parts/lamp.svg": b"<svg>lamp</svg>"}, source=CC0)
    assert r.rights.license_class == "private"
