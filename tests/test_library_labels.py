"""Labelling bytes nobody labelled, and the credits of an edited check-out (an#263, an#264).

- an#263: once a version is ``unknown`` because a file was never labelled (or
  no source was ever recorded), an explicit ``source=`` with a recorded
  ``relabel`` (who, why) answers those gaps of the asset's own version chain.
  It is a first statement, never a relaxation: it answers nothing anyone
  stated — a private licence, a per-part source, a parent, another asset's
  statement about the same bytes (the floor).
- an#264: in a checked-out copy, the label the library carried speaks only for
  the bytes it was declared on, so ``an credits`` and a publish of the copy
  agree about an edited or added file.
- Ride-alongs: an unreadable statement memory refuses (R2b-N1); the registry
  warning fires whenever it is created from nothing (R2b-N2); a legacy
  generated source with no digest speaks for nothing (R2b-N3).

Temporary roots only: the library roots point into ``tmp_path``, and the root
``conftest.py`` points the machine registry there too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.characters.factory import new_character
from an.credits import collect_credits
from an.library import LibraryError, checkout, open_library, publish, publish_dir
from an.library import api as library_api
from an.library import registry
from an.library.registry import RegistryError, RegistryWarning
from an.project import init as init_project
from an.stores import build_project_mall

PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
LABEL = {"by": "tests", "reason": "re-carved the head myself"}
CARVED = b"<svg>a head nobody has seen</svg>"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


def _memory(name: str = "cutan"):
    return open_library(name, records={}, versions={}, blobs={})


def _character(tmp_path: Path, name: str = "amy") -> Path:
    return new_character(tmp_path / f"art-{name}", name=name, use_dicebear=False).parent


def _unlabelled_v002(lib, char: Path, asset_id: str = "character.amy"):
    """v001 labelled cc0 explicitly, then a re-carved head published with no flags."""
    assert publish_dir(lib, char, asset_id, source=CC0).rights.license_class == "free"
    (char / "parts" / "head.svg").write_bytes(CARVED)
    v2 = publish_dir(lib, char, asset_id)
    assert v2.rights.license_class == "unknown"
    return v2


# ============================================================ an#263


def test_an_explicit_license_alone_does_not_answer_an_earlier_gap(tmp_path):
    """The issue's reproduction, and the hint the reasons now carry."""
    lib = _memory()
    char = _character(tmp_path)
    _unlabelled_v002(lib, char)
    v3 = publish_dir(lib, char, "character.amy", source=CC0)
    assert v3.rights.license_class == "unknown"
    assert any(
        "parts/head.svg" in r and "--relabel-by" in r for r in v3.rights.reasons
    ), v3.rights.reasons


def test_a_recorded_label_answers_the_unlabelled_bytes(tmp_path):
    lib = _memory()
    char = _character(tmp_path)
    _unlabelled_v002(lib, char)
    v3 = publish_dir(lib, char, "character.amy", source=CC0, relabel=LABEL)
    assert (str(v3.ref), v3.rights.license_class) == ("cutan:character.amy@v003", "free")
    assert "labelled by tests: re-carved the head myself" in v3.rights.reasons
    stored = library_api.read_version(lib, "character.amy", "v003")
    assert stored["relabel"] == LABEL
    assert library_api.version_manifest(stored) == stored["manifest_sha256"]
    # who labelled, and why, is part of the version identity (a tampered label fails check-out)
    assert library_api.version_manifest({**stored, "relabel": {**LABEL, "by": "someone"}}) != stored["manifest_sha256"]
    # the label is part of the version identity
    assert not publish_dir(lib, char, "character.amy", source=CC0, relabel=LABEL).created
    other = publish_dir(lib, char, "character.amy", source=CC0, relabel={**LABEL, "reason": "x"})
    assert other.created and other.manifest_sha256 != v3.manifest_sha256
    # the label stays: a later carried publish of the same bytes is free...
    carried = publish_dir(lib, char, "character.amy")
    assert (carried.created, carried.rights.license_class) == (True, "free")
    # ...and it labels nothing added after it
    (char / "notes.txt").write_text("v6", encoding="utf-8")
    assert publish_dir(lib, char, "character.amy").rights.license_class == "unknown"


def test_a_label_answers_a_version_that_recorded_no_source(tmp_path):
    lib = _memory()
    doc, files = {"name": "lamp"}, {"parts/lamp.svg": b"<svg>lamp</svg>"}
    assert publish(lib, "prop.lamp", doc, files).rights.license_class == "unknown"
    assert publish(lib, "prop.lamp", doc, files, source=CC0).rights.license_class == "unknown"
    labelled = publish(lib, "prop.lamp", doc, files, source=CC0, relabel=LABEL)
    assert labelled.rights.license_class == "free"


def test_the_label_becomes_the_assets_statement_about_its_bytes(tmp_path):
    """Before the label, the floor held this asset's `unknown` about the head;
    after it, another asset holding the same head and labelled cc0 is free."""
    lib = _memory()
    char = _character(tmp_path)
    _unlabelled_v002(lib, char)
    head = {"parts/head.svg": CARVED}
    assert publish(lib, "prop.head", {"name": "h"}, head, source=CC0).rights.license_class == "unknown"
    publish_dir(lib, char, "character.amy", source=CC0, relabel=LABEL)
    assert publish(lib, "prop.head2", {"name": "h"}, head, source=CC0).rights.license_class == "free"


@pytest.mark.parametrize(
    "case",
    [
        "asset-level private",
        "carried private",
        "per-part private",
        "another asset's private bytes",
        "a private parent",
    ],
)
def test_a_label_never_relaxes_a_private_statement(tmp_path, case):
    lib = _memory()
    files = {"parts/head.svg": CARVED, "parts/arm.svg": b"<svg>arm</svg>"}
    doc: dict = {"name": "x"}
    derived: list[str] = []
    if case == "asset-level private":
        publish(lib, "prop.x", doc, files, source=PRIVATE)
    elif case == "carried private":
        publish(lib, "prop.x", doc, files, source=PRIVATE)
        # v002 carries the private label; the changed arm is a gap
        files = {**files, "parts/arm.svg": b"<svg>arm 2</svg>"}
        v2 = publish(lib, "prop.x", doc, files)
        assert v2.rights.license_class == "private"
        assert library_api.read_version(lib, "prop.x", "v002")["unlabelled"] == ["parts/arm.svg"]
    elif case == "per-part private":
        digest = library_api.content_hash(CARVED)
        doc = {
            "name": "x",
            "skins": {"default": {"slots": {"head": {"head": {
                "path": "parts/head.svg", "source": {**PRIVATE, "sha256": digest},
            }}}}},
        }
        publish(lib, "character.x", doc, files)
    elif case == "another asset's private bytes":
        publish(lib, "prop.chair", {"name": "chair"}, {"parts/c.svg": CARVED}, source=PRIVATE)
        publish(lib, "prop.x", doc, files)  # no source: unknown
    elif case == "a private parent":
        publish(lib, "prop.film", {"name": "film"}, {"parts/f.svg": b"<svg>f</svg>"}, source=PRIVATE)
        derived = ["prop.film@v001"]
        publish(lib, "prop.x", doc, files, derived_from=derived)
    asset_id = "character.x" if case == "per-part private" else "prop.x"
    labelled = publish(lib, asset_id, doc, files, source=CC0, relabel=LABEL, derived_from=derived)
    assert labelled.rights.license_class == "private", labelled.rights.reasons


def test_a_label_does_not_answer_another_assets_gap(tmp_path):
    """Its scope is the asset's own chain: the same bytes unlabelled in another
    asset, or a gap in a version it derives from, are that asset's to label."""
    lib = _memory()
    head = {"parts/head.svg": CARVED}
    publish(lib, "prop.other", {"name": "o"}, head)  # unknown: no source
    publish(lib, "prop.x", {"name": "x"}, head)
    assert publish(lib, "prop.x", {"name": "x"}, head, source=CC0, relabel=LABEL).rights.license_class == "unknown"
    publish(lib, "prop.parent", {"name": "p"}, {"parts/p.svg": b"<svg>p</svg>"})
    child = publish(
        lib, "prop.child", {"name": "c"}, {"parts/c.svg": b"<svg>c</svg>"},
        source=CC0, relabel=LABEL, derived_from=["prop.parent@v001"],
    )
    assert child.rights.license_class == "unknown"


@pytest.mark.parametrize(
    "statement, expected",
    [
        (PRIVATE, "private"),
        # looser than the walk's own `unknown`: a merge first would keep the
        # `unknown`, leave it out as the walk's, and lose this one
        ({"provider": "a-studio", "license": "cc-by-4.0", "attribution": "a studio"}, "attribution"),
    ],
)
def test_a_same_named_librarys_statement_is_not_hidden_by_the_walk(tmp_path, statement, expected):
    """The walk leaves out only statements of versions it reads in full,
    BEFORE two libraries' statements under one asset key are merged."""
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.x", {"name": "x"}, {"parts/head.svg": CARVED}, source=statement)
    default = open_library("cutan")
    publish(default, "prop.x", {"name": "x"}, {"parts/head.svg": CARVED})
    labelled = publish(default, "prop.x", {"name": "x"}, {"parts/head.svg": CARVED},
                       source=CC0, relabel=LABEL)
    assert labelled.rights.license_class == expected


def test_a_same_named_twin_version_is_not_taken_for_the_walks_own(tmp_path):
    """Two libraries named ``cutan`` can hold versions with the SAME manifest
    (same doc, bytes, source and ``previous`` reference) whose ``previous``
    resolves to different versions — so they say different things. The walk
    leaves out only the statements of the versions it read, in the library it
    read them from: the twin's private statement still binds."""
    head = {"parts/head.svg": CARVED}
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.x", {"name": "x", "source": PRIVATE}, head)
    twin = publish(study, "prop.x", {"name": "x"}, head)  # private through its v001
    default = open_library("cutan")
    publish(default, "prop.x", {"name": "x", "draft": True}, head)
    mine = publish(default, "prop.x", {"name": "x"}, head)  # unknown through its v001
    # Lineage pins now make the twins' manifests differ (review-269 B1); the
    # walk must not mistake one for the other either way.
    assert mine.manifest_sha256 != twin.manifest_sha256
    labelled = publish(default, "prop.x", {"name": "x"}, head, source=CC0, relabel=LABEL)
    assert labelled.rights.license_class == "private", labelled.rights.reasons


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"relabel": LABEL}, "needs the source="),
        ({"relabel": {"by": "tests"}, "source": CC0}, "who and why"),
        ({"relabel": LABEL, "source": CC0, "relicense": LABEL}, "exclusive"),
    ],
)
def test_a_label_is_explicit_and_recorded(kwargs, match):
    with pytest.raises(LibraryError, match=match):
        publish(_memory(), "prop.lamp", {"name": "lamp"}, **kwargs)


def test_the_cli_names_the_way_out_and_takes_the_label(tmp_path):
    char = _character(tmp_path)
    _unlabelled_v002(open_library("cutan"), char)
    args = ["library", "publish", str(char), "character.amy", "--package", "cutan",
            "--license", "cc0-1.0", "--provider", "me"]
    r = runner.invoke(build_app(), args)
    assert r.exit_code == 0, r.output
    assert "[unknown]" in r.output and "--relabel-by" in r.output
    r = runner.invoke(build_app(), [*args, "--relabel-by", "me", "--relabel-reason", "my carving"])
    assert r.exit_code == 0, r.output
    assert "[free]" in r.output and "--relabel-by" not in r.output


# ============================================================ an#264


@pytest.fixture
def checked_out(tmp_path):
    """The issue's steps 1-2: a factory character published `--license cc0`, checked out."""
    lib = open_library("cutan")
    char = _character(tmp_path, "h")
    publish_dir(lib, char, "character.h", source=CC0)
    project = init_project(tmp_path / "proj")
    checkout(lib, project, "cutan:character.h@v001")
    return lib, project, project / "assets" / "characters" / "h"


def _unverified(project: Path) -> list[str]:
    return [e.asset for e in collect_credits(build_project_mall(project)).unverified]


def test_an_unedited_checkout_is_covered_by_its_label(checked_out):
    _, project, copy = checked_out
    assert _unverified(project) == []
    origin = json.loads((copy / "character.json").read_text(encoding="utf-8"))["metadata"]["library_origin"]
    assert origin["checked_out"]["source"]["license"] == "cc0-1.0"
    assert "parts/head.svg" in origin["checked_out"]["files"]


def test_a_part_re_carved_in_the_copy_is_unverified_as_in_the_library(checked_out):
    """The issue's steps 3-5: credits and a publish of the copy agree."""
    lib, project, copy = checked_out
    (copy / "parts" / "head.svg").write_bytes(CARVED)
    assert _unverified(project) == ["characters/h/parts/head.svg"]
    entry = next(
        e for e in collect_credits(build_project_mall(project)).unverified
        if e.asset.endswith("head.svg")
    )
    assert "since the library check-out" in entry.source.extra["reason"]
    assert publish_dir(lib, copy, "character.h").rights.license_class == "unknown"


def test_a_file_added_to_the_copy_is_unverified(checked_out):
    lib, project, copy = checked_out
    (copy / "reference.png").write_bytes(b"a reference image")
    assert _unverified(project) == ["characters/h/reference.png"]
    assert publish_dir(lib, copy, "character.h").rights.license_class == "unknown"


def test_a_source_a_person_writes_in_the_copy_speaks_for_it(checked_out):
    lib, project, copy = checked_out
    (copy / "parts" / "head.svg").write_bytes(CARVED)
    path = copy / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["source"] = {"provider": "me", "license": "cc-by-4.0", "attribution": "head by me"}
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert _unverified(project) == []
    assert publish_dir(lib, copy, "character.h").rights.license_class == "attribution"


def test_removing_the_checked_out_label_is_unverified_never_silence(checked_out):
    _, project, copy = checked_out
    path = copy / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    del doc["source"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "characters/h" in _unverified(project)


def test_a_descriptors_own_source_beside_an_asset_label_is_held_the_same_way(tmp_path):
    """The check-out writes nothing into a descriptor that has its own source,
    but the asset-level label is still carried by a publish of the copy."""
    lib = open_library("cutan")
    char = _character(tmp_path, "d")
    path = char / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["source"] = {"provider": "me", "license": "cc0-1.0", "author": "a person"}
    path.write_text(json.dumps(doc), encoding="utf-8")
    publish_dir(lib, char, "character.d", source=CC0)
    project = init_project(tmp_path / "proj")
    checkout(lib, project, "cutan:character.d@v001")
    copy = project / "assets" / "characters" / "d"
    (copy / "parts" / "head.svg").write_bytes(CARVED)
    assert _unverified(project) == ["characters/d/parts/head.svg"]
    assert publish_dir(lib, copy, "character.d").rights.license_class == "unknown"


def test_an_older_checkout_is_relinked_with_its_digests(checked_out):
    """A copy checked out before the digests were recorded is upgraded in place
    by checking it out again, without --overwrite."""
    lib, project, copy = checked_out
    path = copy / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    del doc["metadata"]["library_origin"]["checked_out"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    result = checkout(lib, project, "cutan:character.h@v001")
    assert result.changed
    (copy / "parts" / "head.svg").write_bytes(CARVED)
    assert _unverified(project) == ["characters/h/parts/head.svg"]


def test_a_legacy_generated_source_without_a_digest_speaks_for_nothing(tmp_path):
    """R2b-N3: a DiceBear source made before an#259 pins nothing, so a file
    added under it is unverified in credits and unknown in the library."""
    from an.characters.licenses import dicebear_source

    char = _character(tmp_path, "lee")
    path = char / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["source"] = dicebear_source("lorelei", seed="lee").model_dump(mode="json", exclude_none=True)
    assert "sha256" not in doc["source"]
    path.write_text(json.dumps(doc), encoding="utf-8")
    (char / "parts" / "hat.png").write_bytes(b"a hat nobody labelled")
    report = collect_credits({"characters": _FolderOf(char)})
    assert "characters/lee/parts/hat.png" in [e.asset for e in report.unverified]
    assert publish_dir(_memory(), char, "character.lee").rights.license_class == "unknown"


class _FolderOf(dict):
    """A one-entry characters store whose files are those of ``folder``."""

    def __init__(self, folder: Path):
        super().__init__({folder.name: json.loads((folder / "character.json").read_text("utf-8"))})
        self._folder = folder

    def file_digests(self, key: str):
        return {
            p.relative_to(self._folder).as_posix(): library_api.content_hash(p.read_bytes())
            for p in sorted(self._folder.rglob("*"))
            if p.is_file() and p.name != "character.json"
        }


# ============================================================ ride-alongs


def test_an_unreadable_statement_memory_refuses(tmp_path):
    """R2b-N1 (mutant M10b): a memory that exists but cannot be listed fails closed."""
    digest = library_api.content_hash(CARVED)
    folder = registry._statements_dir(digest)
    folder.parent.mkdir(parents=True)
    folder.write_text("not a folder", encoding="utf-8")  # there, but not listable
    with pytest.raises(RegistryError, match="cannot be read"):
        registry.remembered_statements(digest)
    with pytest.raises(RegistryError, match="cannot be read"):
        publish(open_library("an"), "prop.stool", {"name": "s"}, {"parts/s.svg": CARVED}, source=CC0)


def test_the_registry_warns_whenever_it_is_created_from_nothing(tmp_path):
    """R2b-N2: a registry deleted wholesale (roots and statements together)
    looks exactly like a first use, so the warning cannot wait for a library
    to be discoverable."""
    import shutil
    import warnings

    assert not registry.machine_registry_dir().exists()
    study = open_library("cutan", root=tmp_path / "study-lib")
    with pytest.warns(RegistryWarning, match="created from nothing"):
        publish(study, "prop.chair", {"name": "chair"}, {"parts/c.svg": CARVED}, source=PRIVATE)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RegistryWarning)  # it exists now: silent
        publish(study, "prop.lamp", {"name": "lamp"}, source=PRIVATE)
    shutil.rmtree(registry.machine_registry_dir())  # deleted wholesale
    with pytest.warns(RegistryWarning, match="no other library is discoverable"):
        stool = publish(open_library("an"), "prop.stool", {"name": "s"}, {"parts/s.svg": CARVED}, source=CC0)
    # the limit the warning names: the study library at a custom root is gone from the floor
    assert stool.rights.license_class == "free"
    library_api.reindex(study)  # ... until it is written to or reindexed
    again = publish(open_library("an"), "prop.stool2", {"name": "s"}, {"parts/s.svg": CARVED}, source=CC0)
    assert again.rights.license_class == "private"


# ============================================================ an#269: the factory's own bytes


def _strip_stamps(char: Path) -> None:
    """The character as a factory made it BEFORE stamps existed: no source anywhere."""
    path = char / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.pop("source", None)
    for skin in doc["skins"].values():
        for slot in skin["slots"].values():
            for att in slot.values():
                att.pop("source", None)
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_a_fresh_factory_character_is_free_beside_an_older_unlabelled_copy(tmp_path):
    """The e2e's finding 4: an older, unlabelled asset holding the same factory
    bytes is silent about them, and silence does not outrank the factory's
    verified stamp — no flag needed."""
    old = new_character(tmp_path / "old", name="alice", use_dicebear=False).parent
    _strip_stamps(old)
    other = open_library("cutan", root=tmp_path / "elsewhere")
    assert publish_dir(other, old, "character.alice").rights.license_class == "unknown"
    fresh = new_character(tmp_path / "fresh", name="alice", use_dicebear=False).parent
    r = publish_dir(open_library("cutan"), fresh, "character.alice-reiniger")
    assert r.rights.license_class == "free", r.rights.reasons


def test_the_factory_record_is_written_by_new_character_only(tmp_path):
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    drawing = library_api.content_hash((char / "amy.svg").read_bytes())
    head = library_api.content_hash((char / "parts" / "head.svg").read_bytes())
    from an.characters.factory import FACTORY_PROVIDER

    assert FACTORY_PROVIDER in registry.generated_by(drawing)
    assert FACTORY_PROVIDER in registry.generated_by(head)
    assert registry.generated_by(library_api.content_hash(CARVED)) == frozenset()
    assert "record_generated" not in registry.__all__


@pytest.mark.parametrize("claim", ["a person's cc0", "a forged factory stamp"])
def test_a_hand_written_cc0_does_not_label_unlabelled_carved_bytes(tmp_path, claim):
    """The attack: carved bytes published with no label elsewhere, then reused
    under a per-part cc0 pinned to their digest. Only the factory's record
    verifies a stamp, so the other asset's silence still binds; a relicence
    is the way out."""
    from an.characters.factory import FACTORY_LICENSE, FACTORY_PROVIDER

    lib = open_library("cutan")
    publish(lib, "prop.carving", {"name": "c"}, {"parts/head.svg": CARVED})  # unlabelled
    digest = library_api.content_hash(CARVED)
    source = (
        {"provider": "me", "license": "cc0-1.0", "sha256": digest}
        if claim == "a person's cc0"
        else {"provider": FACTORY_PROVIDER, "license": FACTORY_LICENSE, "sha256": digest}
    )
    doc = {
        "name": "x",
        "source": {"provider": "me", "license": "cc0-1.0"},
        "skins": {"default": {"slots": {"head": {"head": {"path": "parts/head.svg", "source": source}}}}},
    }
    r = publish(lib, "character.x", doc, {"parts/head.svg": CARVED}, source=CC0)
    assert r.rights.license_class == "unknown", r.rights.reasons
    assert any("same bytes as cutan:prop.carving" in reason for reason in r.rights.reasons)
    freed = publish(lib, "character.x", doc, {"parts/head.svg": CARVED}, source=CC0,
                    relicense={"by": "tests", "reason": "I carved it from my own drawing"})
    assert freed.rights.license_class == "free"


def test_the_factory_record_never_relaxes_a_private_statement(tmp_path):
    """A study (made before stamps) whose asset-level private label covers the
    factory's bytes still binds them: only silence gives way."""
    study = new_character(tmp_path / "study", name="alice", use_dicebear=False).parent
    _strip_stamps(study)
    publish_dir(open_library("cutan", root=tmp_path / "study-lib"), study, "character.study",
                source=PRIVATE)
    fresh = new_character(tmp_path / "fresh", name="alice", use_dicebear=False).parent
    r = publish_dir(open_library("cutan"), fresh, "character.alice")
    assert r.rights.license_class == "private"


def test_a_re_carved_part_under_a_stale_factory_stamp_is_not_the_factorys(tmp_path):
    """The record verifies a stamp only where the stamp pins the file's bytes."""
    lib = open_library("cutan")
    publish(lib, "prop.carving", {"name": "c"}, {"parts/head.svg": CARVED})  # unlabelled
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    (char / "parts" / "head.svg").write_bytes(CARVED)
    assert publish_dir(lib, char, "character.amy").rights.license_class == "unknown"


def test_silence_gives_way_but_a_private_statement_beside_it_still_binds(tmp_path):
    old = new_character(tmp_path / "old", name="alice", use_dicebear=False).parent
    _strip_stamps(old)
    publish_dir(open_library("cutan", root=tmp_path / "elsewhere"), old, "character.alice")
    publish_dir(open_library("cutan", root=tmp_path / "study-lib"), old, "character.study",
                source=PRIVATE)
    fresh = new_character(tmp_path / "fresh", name="alice", use_dicebear=False).parent
    r = publish_dir(open_library("cutan"), fresh, "character.alice")
    assert r.rights.license_class == "private"
    assert not any("cutan:character.alice@" in reason for reason in r.rights.reasons)


def test_only_the_factorys_own_stamp_is_verified_by_its_record(tmp_path):
    """Bytes the factory drew, itemised by someone else's claim instead of the
    factory's stamp, get no help from the record: two pieces of evidence, both."""
    lib = open_library("cutan")
    char = new_character(tmp_path, name="amy", use_dicebear=False).parent
    head = (char / "parts" / "head.svg").read_bytes()
    publish(lib, "prop.old", {"name": "o"}, {"parts/head.svg": head})  # unlabelled
    digest = library_api.content_hash(head)
    doc = {
        "name": "x",
        "skins": {"default": {"slots": {"head": {"head": {
            "path": "parts/head.svg",
            "source": {"provider": "me", "license": "cc0-1.0", "sha256": digest},
        }}}}},
    }
    r = publish(lib, "character.x", doc, {"parts/head.svg": head}, source=CC0)
    assert r.rights.license_class == "unknown"
    assert any("same bytes as cutan:prop.old" in reason for reason in r.rights.reasons)


# ============================================================ review-269 B2: stamping is not drawing


def _set_part_source(char: Path, path: str, source: dict) -> None:
    doc_path = char / "character.json"
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    for skin in doc["skins"].values():
        for slot in skin["slots"].values():
            for att in slot.values():
                if att["path"] == path:
                    att["source"] = source
    doc_path.write_text(json.dumps(doc), encoding="utf-8")


def test_stamping_carved_bytes_does_not_make_them_the_factorys(tmp_path):
    """X3 / X3b / X4: the public stamping functions stamp, but record nothing;
    carved bytes another asset holds unlabelled stay `unknown`, then and later."""
    from an.characters.factory import (
        FACTORY_LICENSE, FACTORY_PROVIDER, stamp_factory_descriptor, stamp_factory_parts,
    )

    lib = open_library("cutan")
    publish(lib, "prop.old-carve", {"name": "old"}, {"parts/head.svg": CARVED})  # unlabelled
    x3 = new_character(tmp_path / "x3", name="c3", use_dicebear=False).parent
    (x3 / "parts" / "head.svg").write_bytes(CARVED)
    stamp_factory_parts(x3, {"parts/head.svg"})
    assert publish_dir(lib, x3, "character.c3").rights.license_class == "unknown"
    assert registry.generated_by(library_api.content_hash(CARVED)) == frozenset()
    # X3b: a hand-forged stamp afterwards finds nothing recorded either
    x3b = new_character(tmp_path / "x3b", name="c3b", use_dicebear=False).parent
    (x3b / "parts" / "head.svg").write_bytes(CARVED)
    _set_part_source(x3b, "parts/head.svg", {
        "provider": FACTORY_PROVIDER, "license": FACTORY_LICENSE,
        "sha256": library_api.content_hash(CARVED),
    })
    assert publish_dir(lib, x3b, "character.c3b").rights.license_class == "unknown"
    # X4: the descriptor stamp on a carved source drawing
    drawing = b"<svg>carved drawing</svg>"
    publish(lib, "prop.old-drawing", {"name": "old2"}, {"d.svg": drawing})  # unlabelled
    x4 = new_character(tmp_path / "x4", name="c4", use_dicebear=False).parent
    doc = json.loads((x4 / "character.json").read_text(encoding="utf-8"))
    doc.pop("source")
    doc["source_svg"] = "d.svg"
    (x4 / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    (x4 / "d.svg").write_bytes(drawing)
    (x4 / "c4.svg").unlink()
    stamp_factory_descriptor(x4)
    assert publish_dir(lib, x4, "character.c4").rights.license_class == "unknown"


# ============================================================ review-269 B1: lineage is pinned


@pytest.mark.parametrize("relabel", [False, True])
def test_a_same_named_library_cannot_stand_in_for_a_private_parent(tmp_path, relabel):
    """B1: a recolour derived from a private study parent; later a default-root
    library of the same name gets an unrelated parent under the same reference.
    The next version, on the genre's normal search path, stays private."""
    from an.library import promote

    study_an = open_library("an", root=tmp_path / "study-an")
    publish(study_an, "prop.p", {"name": "p"}, {"parts/p.png": b"FILM-ORIGINAL"}, source=PRIVATE)
    cut = open_library("cutan")
    v1 = publish(cut, "prop.c", {"name": "c"}, {"parts/c.png": b"RECOLOUR"}, source=CC0,
                 derived_from=["an:prop.p@v001"], search=[study_an])
    assert v1.rights.license_class == "private"
    core = open_library("an")
    publish(core, "prop.p", {"name": "other p"}, {"parts/p.png": b"UNRELATED"}, source=CC0)
    v2 = publish(cut, "prop.c", {"name": "c", "v": 2}, {"parts/c.png": b"RECOLOUR"},
                 source=CC0, search=[core], **({"relabel": LABEL} if relabel else {}))
    assert v2.rights.license_class == "private", v2.rights.reasons
    with pytest.raises(library_api.RightsRefusal):
        promote([cut, core], "cutan:prop.c@v002", to=open_library("an", root=tmp_path / "share"))


def test_a_pinned_parent_two_levels_down_is_not_replaced_either(tmp_path):
    """B1 through a `previous` ancestor's `derived_from`, two levels down."""
    study_an = open_library("an", root=tmp_path / "study-an")
    publish(study_an, "prop.p", {"name": "p"}, {"parts/p.png": b"FILM-ORIGINAL"}, source=PRIVATE)
    cut = open_library("cutan")
    publish(cut, "prop.c", {"name": "c"}, {"parts/c.png": b"RECOLOUR"}, source=CC0,
            derived_from=["an:prop.p@v001"], search=[study_an])
    publish(cut, "prop.c", {"name": "c", "v": 2}, {"parts/c.png": b"RECOLOUR 2"}, source=CC0,
            search=[study_an])
    core = open_library("an")
    publish(core, "prop.p", {"name": "other p"}, {"parts/p.png": b"UNRELATED"}, source=CC0)
    v3 = publish(cut, "prop.c", {"name": "c", "v": 3}, {"parts/c.png": b"RECOLOUR 3"},
                 source=CC0, search=[core], relabel=LABEL)
    assert v3.rights.license_class == "private", v3.rights.reasons


def test_a_version_records_the_manifest_of_each_parent(tmp_path):
    lib = _memory()
    publish(lib, "prop.p", {"name": "p"}, source=CC0)
    publish(lib, "prop.c", {"name": "c"}, source=CC0, derived_from=["prop.p@v001"])
    v2 = publish(lib, "prop.c", {"name": "c2"}, source=CC0)
    stored = library_api.read_version(lib, "prop.c", v2.ref.version)
    parent = library_api.read_version(lib, "prop.c", "v001")
    assert stored["lineage"] == {"cutan:prop.c@v001": parent["manifest_sha256"]}
    assert library_api.version_manifest({**stored, "lineage": {}}) != stored["manifest_sha256"]


def test_an_edited_digest_list_makes_credits_stricter_not_cleaner(checked_out):
    """review-269 S1: forging the block's digests unseals it; it then covers no file."""
    _, project, copy = checked_out
    (copy / "parts" / "head.svg").write_bytes(CARVED)
    path = copy / "character.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["metadata"]["library_origin"]["checked_out"]["files"]["parts/head.svg"] = (
        library_api.content_hash(CARVED)
    )
    path.write_text(json.dumps(doc), encoding="utf-8")
    unverified = _unverified(project)
    assert "characters/h/parts/head.svg" in unverified
    assert len(unverified) > 1  # every file, not only the carved one


def test_a_label_answers_a_gap_behind_a_verified_derived_from(tmp_path):
    """The pins are also what lets a chain be verified: an ancestor that
    derives from another asset (pinned, and still that version) can have its
    gap answered by a later label."""
    lib = _memory()
    publish(lib, "prop.p", {"name": "p"}, {"parts/p.svg": b"<svg>p</svg>"}, source=CC0)
    files = {"parts/c.svg": b"<svg>c</svg>"}
    publish(lib, "prop.c", {"name": "c"}, files, source=CC0, derived_from=["prop.p@v001"])
    files = {"parts/c.svg": b"<svg>c, re-carved</svg>"}
    assert publish(lib, "prop.c", {"name": "c"}, files).rights.license_class == "unknown"
    assert publish(lib, "prop.c", {"name": "c"}, files, source=CC0,
                   relabel=LABEL).rights.license_class == "free"
