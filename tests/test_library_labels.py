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
    # the label is part of the version identity
    assert not publish_dir(lib, char, "character.amy", source=CC0, relabel=LABEL).created
    other = publish_dir(lib, char, "character.amy", source=CC0, relabel={**LABEL, "reason": "x"})
    assert other.created
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


def test_a_same_named_librarys_private_statement_is_not_hidden_by_the_walk(tmp_path):
    """The walk leaves out only statements of versions it reads in full,
    BEFORE two libraries' statements under one asset key are merged."""
    study = open_library("cutan", root=tmp_path / "study-lib")
    publish(study, "prop.x", {"name": "x"}, {"parts/head.svg": CARVED}, source=PRIVATE)
    default = open_library("cutan")
    publish(default, "prop.x", {"name": "x"}, {"parts/head.svg": CARVED})
    labelled = publish(default, "prop.x", {"name": "x"}, {"parts/head.svg": CARVED},
                       source=CC0, relabel=LABEL)
    assert labelled.rights.license_class == "private"


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
