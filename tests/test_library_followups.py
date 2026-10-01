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
    find,
    open_library,
    promote,
    publish,
    publish_dir,
)
from an.library import api as library_api
from an.library import registry
from an.library.floor import BlobFloor, machine_libraries
from an.library.lock import ProjectLock
from an.library.registry import (
    RegistryError,
    RegistryWarning,
    register_root,
    registered_roots,
)
from an.library.registry import _account_home as _REAL_ACCOUNT_HOME
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
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))  # Windows' data folder


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


def _study_chair(tmp_path, *, name: str = "study-lib"):
    study = open_library("cutan", root=tmp_path / name)
    publish(study, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    return study


def _cc0_stool():
    return publish(
        open_library("an"), "prop.stool", {"name": "s"}, {"parts/s.png": CARVED}, source=CC0
    )


def test_without_the_machine_record_the_same_bytes_would_escape(tmp_path, monkeypatch):
    """The control for the test above: the registry and its memory are what close it."""
    _study_chair(tmp_path)
    monkeypatch.setattr(registry, "_account_home", lambda: tmp_path / "another-account")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "elsewhere"))
    assert _cc0_stool().rights.license_class == "free"


@pytest.mark.parametrize("move", ["the study library", "the registry file"])
def test_moving_a_study_library_or_the_registry_relaxes_nothing(tmp_path, monkeypatch, move):
    """S3: the floor keeps the last-known statements per digest, not only live roots."""
    _study_chair(tmp_path)
    if move == "the study library":
        (tmp_path / "study-lib").rename(tmp_path / "study-moved")
    else:
        path = registry.machine_registry_path()
        path.rename(path.with_name("moved-away.jsonl"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "elsewhere"))
    stool = _cc0_stool()
    assert stool.rights.license_class == "private"
    assert any("cutan:prop.chair" in r for r in stool.rights.reasons)


def test_a_relicence_still_speaks_in_the_machine_memory(tmp_path):
    study = _study_chair(tmp_path)
    publish(
        study, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=CC0,
        relicense={"by": "tests", "reason": "bought the licence"},
    )
    assert _cc0_stool().rights.license_class == "free"


def test_the_registry_location_ignores_the_environment(monkeypatch, tmp_path):
    """M05/M06: the real path logic, with only the account home redirected."""
    expected = registry.machine_registry_path()
    assert expected.parent == registry.machine_registry_dir()
    for var, value in {
        "HOME": tmp_path / "fake-home",
        "XDG_DATA_HOME": tmp_path / "fake-xdg",
        "AN_HOME": tmp_path / "fake-an",
        "AN_REGISTRY": tmp_path / "fake-registry",
        "LOCALAPPDATA": tmp_path / "fake-local",
    }.items():
        monkeypatch.setenv(var, str(value))
    assert registry.machine_registry_path() == expected
    assert str(tmp_path) not in str(registry.machine_registry_dir())


def test_the_account_home_ignores_home(monkeypatch, tmp_path):
    before = _REAL_ACCOUNT_HOME()
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    assert _REAL_ACCOUNT_HOME() == before


def test_a_write_the_registry_cannot_record_is_refused(tmp_path, monkeypatch):
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setattr(registry, "_account_home", lambda: blocker)
    lib = open_library("cutan", root=tmp_path / "study-lib")
    with pytest.raises(RegistryError, match="nothing (was written|proceeds)"):
        publish(lib, "prop.chair", {"name": "chair"}, {"parts/chair.png": CARVED}, source=PRIVATE)
    assert "prop.chair" not in lib.records
    assert len(lib.blobs) == 0


def test_an_unreadable_registry_is_an_error_not_an_empty_one(tmp_path):
    """M10: a registry that exists but cannot be read fails closed, for writes and reads."""
    _study_chair(tmp_path)
    path = registry.machine_registry_path()
    path.unlink()
    path.mkdir()  # still there, but no longer readable as a file
    with pytest.raises(RegistryError, match="cannot be read"):
        _cc0_stool()
    with pytest.raises(RegistryError, match="cannot be read"):
        find(open_library("an"), kind="prop")


def test_an_undecodable_registry_line_is_skipped_not_a_traceback(tmp_path):
    reg = tmp_path / "roots.jsonl"
    reg.write_bytes(b"\xff\xfe garbage\n")
    register_root("cutan", tmp_path / "study", registry=reg)
    assert [r.name for _, r in registered_roots(registry=reg)] == ["study"]


def test_a_torn_line_does_not_swallow_the_next_registration(tmp_path):
    """N2: a crash mid-append must not eat the next root."""
    reg = tmp_path / "roots.jsonl"
    register_root("cutan", tmp_path / "first", registry=reg)
    with reg.open("a", encoding="utf-8") as f:
        f.write('{"package": "cutan", "ro')  # torn
    register_root("cutan", tmp_path / "second", registry=reg)
    assert [r.name for _, r in registered_roots(registry=reg)] == ["first", "second"]


def test_registered_roots_are_read_once_each(tmp_path):
    """M28: duplicate lines (two racing registrations) read as one root."""
    reg = tmp_path / "roots.jsonl"
    line = json.dumps({"package": "cutan", "root": str(tmp_path / "x")})
    reg.write_text(f"{line}\n{line}\n", encoding="utf-8")
    assert len(list(registered_roots(registry=reg))) == 1


def test_registered_roots_that_vanished_are_skipped(tmp_path):
    reg = tmp_path / "roots.jsonl"
    register_root("cutan", tmp_path / "gone", registry=reg)
    with reg.open("a", encoding="utf-8") as f:
        f.write('{"package": "cutan", "ro')  # a torn last line
    assert [r.name for _, r in registered_roots(registry=reg)] == ["gone"]
    assert all(lib.root != tmp_path / "gone" for lib in machine_libraries())


def test_reindex_registers_a_library_made_before_the_registry(tmp_path):
    study = _study_chair(tmp_path)
    registry.machine_registry_path().unlink()
    assert list(registered_roots()) == []
    library_api.reindex(study)
    assert ("cutan", (tmp_path / "study-lib").resolve()) in list(registered_roots())


def test_a_lost_registry_is_rebuilt_from_discovery_with_a_warning(tmp_path):
    publish(open_library("cutan"), "prop.vase", {"name": "v"}, source=PRIVATE)
    registry.machine_registry_path().unlink()
    with pytest.warns(RegistryWarning, match="did not exist"):
        publish(open_library("an"), "prop.cup", {"name": "c"}, source=CC0)
    assert {p for p, _ in registered_roots()} == {"an", "cutan"}


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

    def counting(libraries, version, **kw):
        calls.append(version.get("version"))
        return real(libraries, version, **kw)

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
    """S7: the core names no genre — the genre names its own library package."""
    out = init_cli("alice-and-bob", id=True, genre="cutout_animation")
    assert out.endswith(str((tmp_path / "roots" / "cutan" / "projects" / "alice-and-bob").resolve()))
    out = init_cli("explainer", id=True)  # no genre: the core's root
    assert out.endswith(str((tmp_path / "roots" / "an" / "projects" / "explainer").resolve()))
    out = init_cli("forced", id=True, genre="cutout_animation", package="an")
    assert out.endswith(str((tmp_path / "roots" / "an" / "projects" / "forced").resolve()))
    with pytest.raises(SystemExit, match="one folder name"):
        init_cli("../escape", id=True)
    with pytest.raises(SystemExit, match="no genre named"):
        init_cli("x", id=True, genre="nonesuch")
    with pytest.raises(SystemExit, match="by --id only"):
        init_cli(str(tmp_path / "plain"), genre="cutout_animation")
    r = _run("init", "--id", "from-the-shell", "--genre", "cutout_animation")
    assert r.exit_code == 0, r.output
    assert (tmp_path / "roots" / "cutan" / "projects" / "from-the-shell" / "scene.md").is_file()


def test_the_core_names_no_genre_package():
    from an.genres import genre_library
    from an.genres.cutout import CUTOUT
    from an.library import root

    assert CUTOUT.library == "cutan"
    assert genre_library("cutout_animation") == "cutan"
    assert genre_library(None) == genre_library("nonesuch") == "an"
    assert "cutan" not in root.project_dir.__defaults__ + tuple(
        (root.project_dir.__kwdefaults__ or {}).values()
    )


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
    publish_dir(lib, folder, "character.alice", source=CC0)  # v002 says it again
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


# ============================================================ review-259


def _strip_descriptor_stamp(char: Path, source=None) -> None:
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    if source is None:
        doc.pop("source", None)
    else:
        doc["source"] = source
    (char / "character.json").write_text(json.dumps(doc), encoding="utf-8")


def test_a_carried_label_does_not_cover_bytes_it_never_saw(tmp_path):
    """S1: v001 labelled cc0 explicitly; a head re-carved with unseen bytes and
    published with no flags is unknown, not free."""
    lib = open_library("cutan", records={}, versions={}, blobs={})
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    assert publish_dir(lib, char, "character.amy", source=CC0).rights.license_class == "free"
    (char / "parts" / "head.svg").write_bytes(b"<svg>a head nobody has seen</svg>")
    v2 = publish_dir(lib, char, "character.amy")
    assert v2.rights.license_class == "unknown"
    assert any("parts/head.svg" in r for r in v2.rights.reasons)
    # and the check-out carries it into the project's credits
    project = init_project(tmp_path / "proj")
    checkout(lib, project, "cutan:character.amy@v002")
    unverified = collect_credits(build_project_mall(project)).unverified
    assert any("parts/head.svg" in e.asset for e in unverified)


def test_a_generated_descriptor_source_speaks_only_for_what_it_pins(tmp_path):
    """S1, DiceBear: a generator's source does not cover a re-carved part."""
    from an.characters.factory import stamp_generated_head
    from an.characters.licenses import dicebear_source

    lib = open_library("cutan", records={}, versions={}, blobs={})
    char = new_character(tmp_path, name="dee", use_dicebear=False).parent
    _strip_descriptor_stamp(char)
    stamp_generated_head(char, dicebear_source("lorelei", seed="dee"))
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    assert doc["source"]["provider"] == "dicebear" and doc["source"]["sha256"]
    fresh = publish_dir(lib, char, "character.dee")
    assert fresh.rights.license_class in ("free", "attribution")
    (char / "parts" / "torso.svg").write_bytes(b"<svg>re-carved torso</svg>")
    assert publish_dir(lib, char, "character.dee-carved").rights.license_class == "unknown"
    # a legacy DiceBear source with no digest does not cover a stale stamp either
    legacy = new_character(tmp_path / "legacy", name="lee", use_dicebear=False).parent
    _strip_descriptor_stamp(legacy, source=dicebear_source("lorelei", seed="lee").model_dump(mode="json", exclude_none=True))
    (legacy / "parts" / "torso.svg").write_bytes(b"<svg>re-carved torso 2</svg>")
    assert publish_dir(lib, legacy, "character.lee").rights.license_class == "unknown"


@pytest.mark.parametrize("study_first", [True, False])
def test_a_fresh_character_is_free_whatever_was_published_before(tmp_path, study_first):
    """S2: the source drawing is itemised by the factory's descriptor stamp, so a
    study library's statement about the same drawing does not bind it."""
    lib = open_library("cutan")

    def study():
        char = new_character(tmp_path / "study", name="alice", use_dicebear=False).parent
        (char / "parts" / "head.svg").write_bytes(CARVED)
        return publish_dir(lib, char, "character.alice-study", source=PRIVATE)

    def fresh():
        char = new_character(tmp_path / "fresh", name="alice", use_dicebear=False).parent
        return publish_dir(lib, char, "character.alice")

    if study_first:
        assert study().rights.license_class == "private"
        assert fresh().rights.license_class == "free"
    else:
        assert fresh().rights.license_class == "free"
        assert study().rights.license_class == "private"


def test_an_edited_source_drawing_is_unknown(tmp_path):
    """M13: the descriptor stamp pins the drawing's bytes, not its name."""
    lib = open_library("cutan", records={}, versions={}, blobs={})
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    with (char / "amy.svg").open("ab") as f:
        f.write(b"<!-- edited -->")
    r = publish_dir(lib, char, "character.amy")
    assert r.rights.license_class == "unknown"
    assert any("amy.svg" in reason for reason in r.rights.reasons)


def test_a_hand_added_file_anywhere_is_unknown(tmp_path):
    """M14: not only under parts/."""
    lib = open_library("cutan", records={}, versions={}, blobs={})
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    (char / "reference.png").write_bytes(b"a reference image")
    r = publish_dir(lib, char, "character.amy")
    assert r.rights.license_class == "unknown"
    assert any("reference.png" in reason for reason in r.rights.reasons)


def test_a_pin_into_another_library_is_a_disagreement(tmp_path, project):
    """M16: `an:` in the scene against a `cutan:` lockfile pin."""
    lib, _ = _published_alice(tmp_path)
    checkout(lib, project, "cutan:character.alice@v001")
    _cast(project, library="an:character.alice@v001")
    findings = _library_findings(validate_project(project))
    assert [f.severity for f in findings] == ["warning"]
    assert "checked out from cutan:character.alice@v001" in findings[0].description


def test_root_locates_the_library_the_reference_names(tmp_path, project):
    """S4: `--root` with a `cutan:` reference opens cutan there, not `an`."""
    study = open_library("cutan", root=tmp_path / "study")
    default = open_library("cutan")
    publish(study, "prop.x", {"name": "the study x"})
    publish(default, "prop.x", {"name": "the other x"})
    r = _run("library", "checkout", str(project), "cutan:prop.x@v001", "--root", str(tmp_path / "study"))
    assert r.exit_code == 0, r.output
    doc = build_project_mall(project)["props"]["x"]
    assert doc["name"] == "the study x"
    r = _run("library", "show", "cutan:prop.x", "--root", str(tmp_path / "study"), "--json-out")
    assert json.loads(r.output)["version"]["doc"]["name"] == "the study x"


def test_a_checkout_from_a_custom_root_is_unverifiable_not_edited(tmp_path, project):
    """S5: validate looks at the default root; a same-named other asset there is
    not the pinned version, and the advice never says to check it out."""
    study = open_library("cutan", root=tmp_path / "study")
    publish(study, "prop.x", {"name": "the study x"}, {"parts/x.svg": b"<svg>study</svg>"})
    checkout([study], project, "cutan:prop.x@v001")
    _cast(project, library=None)
    findings = _library_findings(validate_project(project))
    assert [f.severity for f in findings] == ["info"]
    assert "not found" in findings[0].description and "--overwrite" not in findings[0].description
    publish(open_library("cutan"), "prop.x", {"name": "the other x"}, {"parts/x.svg": b"<svg>other</svg>"})
    findings = _library_findings(validate_project(project))
    assert [f.severity for f in findings] == ["info"]
    assert "different version" in findings[0].description
    assert "edited" not in findings[0].description


def test_render_runs_the_pin_check(tmp_path, project, monkeypatch):
    """S5: a stale pin warns at render, and is refused under --strict-assets."""
    import an.render as render_mod
    from an.library.checkout import LibraryPinError, LibraryPinWarning

    lib, _ = _published_alice(tmp_path, versions=2)
    checkout(lib, project, "cutan:character.alice@v002")
    _cast(project, library="cutan:character.alice@v001")
    monkeypatch.setattr(render_mod, "render", lambda project, **kw: Path("rendered.mp4"))
    with pytest.raises(LibraryPinError, match="v002"):
        render_mod.render_project(project, strict_assets=True)
    with pytest.warns(LibraryPinWarning, match="checked out from cutan:character.alice@v002"):
        assert render_mod.render_project(project) == Path("rendered.mp4")


def test_os_clutter_never_makes_a_copy_look_edited(project):
    """S6: Finder's .DS_Store in the folder, before publish and after check-out."""
    folder = new_character(project / "assets" / "characters", name="alice", use_dicebear=False).parent
    (folder / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    (folder / "parts" / "Thumbs.db").write_bytes(b"windows was here")
    lib = open_library("cutan")
    publish_dir(lib, folder, "character.alice")
    r = _run("library", "checkout", str(project), "cutan:character.alice@v001")
    assert r.exit_code == 0, r.output
    (folder / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1 touched")
    _cast(project, library="cutan:character.alice@v001")
    report = validate_project(project)
    assert _library_findings(report) == []


def test_regenerated_mouths_stay_the_factorys_work(project):
    """`an character mouths` re-stamps what it redraws."""
    from an.characters.cli import mouths

    chars = project / "assets" / "characters"
    new_character(chars, name="amy", use_dicebear=False)
    mouths("amy", out_dir=str(chars), palette='{"lip": "#aa4444"}')
    report = collect_credits(build_project_mall(project))
    assert report.unverified == []


def test_publish_registers_its_root_before_anything_else(tmp_path):
    _study_chair(tmp_path)
    assert ("cutan", (tmp_path / "study-lib").resolve()) in list(registered_roots())


def test_a_namespaced_reference_joins_an_explicit_package_path(tmp_path, project):
    _published_alice(tmp_path)
    r = _run("library", "checkout", str(project), "cutan:character.alice@v001", "--package", "an")
    assert r.exit_code == 0, r.output


def test_a_dicebear_character_is_pinned_to_dicebears_bytes(tmp_path, monkeypatch):
    """S1: the factory pins DiceBear's source on the head it drew and the drawing."""
    from an.characters import factory

    monkeypatch.setattr(
        factory,
        "fetch_dicebear",
        lambda seed, style: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#e0b090"/></svg>',
    )
    char = new_character(tmp_path, name="dee", use_dicebear=True).parent
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    assert doc["source"]["provider"] == "dicebear"
    assert doc["source"]["sha256"] == library_api.content_hash((char / "dee.svg").read_bytes())
    heads = [
        att["source"]
        for skin in doc["skins"].values()
        for slot in skin["slots"].values()
        for att in slot.values()
        if att["path"] == "parts/head.svg"
    ]
    assert heads and all(
        h["provider"] == "dicebear"
        and h["sha256"] == library_api.content_hash((char / "parts" / "head.svg").read_bytes())
        for h in heads
    )
    report = collect_credits({"characters": {"dee": doc}})
    assert [e.asset for e in report.entries] == ["characters/dee"]  # one credit, not two


def test_a_stale_private_part_claim_still_binds_in_credits(tmp_path, project):
    """A per-part source pinned to other bytes speaks for nothing — but a private
    one is never relabelled `unknown` in the credits (stricter stays)."""
    char = new_character(project / "assets" / "characters", name="amy", use_dicebear=False).parent
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    for skin in doc["skins"].values():
        for slot in skin["slots"].values():
            for att in slot.values():
                if att["path"] == "parts/head.svg":
                    att["source"] = {**PRIVATE, "sha256": "0" * 64}
    (char / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    report = collect_credits(build_project_mall(project))
    assert [e.license_class for e in report.entries if e.asset.endswith("parts/head.svg")] == ["private"]
