"""The asset library's integrity guarantees: rights that survive, paths that stay put, versions that cannot be lost.

Each test here pins a failure the adversarial review of an#236 reproduced:
rights masked or dropped on the way into a project, a hostile library writing
outside a project, racing publishers, a torn file blinding search, a forked
check-out passing for the original, an unrelated asset merged by promotion,
trusted stored rights, deletable blobs. Temporary roots only.
"""

from __future__ import annotations

import ast
import json
import warnings
from pathlib import Path

import pytest

from an.characters.factory import new_character
from an.credits import (
    PrivateStudyWarning,
    collect_credits,
    credits_for_scene,
    warn_if_private_study,
)
from an.ir.sync import markdown_to_ir
from an.library import (
    CheckoutError,
    IntegrityError,
    LibraryError,
    RightsRefusal,
    VersionExistsError,
    check_pins,
    checkout,
    find,
    open_library,
    promote,
    publish,
    publish_dir,
    show,
    verify_checkout,
)
from an.library import api as library_api
from an.library.api import LibraryIndexWarning, read_version
from an.library.lock import ProjectLock
from an.library.root import LibraryLocationWarning
from an.library.stores import LocalFiles, build_library_mall
from an.project import init as init_project
from an.stores import build_project_mall

CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
MIT = {"provider": "an-tests", "license": "mit"}
PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
LIBRARY_PKG = Path(__file__).resolve().parents[1] / "an" / "library"


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def project(tmp_path) -> Path:
    return init_project(tmp_path / "proj")


def _memory(name: str = "an"):
    return open_library(name, records={}, versions={}, blobs={})


def _vase(lib, *, source=PRIVATE, doc=None):
    return publish(
        lib,
        "prop.vase",
        doc or {"name": "vase"},
        {"parts/vase.svg": b"<svg>vase</svg>"},
        source=source,
    )


def _scene_casting(store: str, ref: str, kind: str = "prop"):
    return markdown_to_ir(
        "# Cast\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1.0\n```\n\n"
        "```yaml entities\n"
        f"- {{id: {ref}, kind: {kind}, store: {store}, ref: {ref}}}\n"
        "```\n"
    )


# --------------------------------------------------------------------------- B1


def test_a_carried_source_cannot_mask_a_private_descriptor_source():
    """B1: v001 declared cc0; v002's descriptor says the art is from a film."""
    lib = _memory("cutan")
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0)
    doc = {"name": "lamp", "source": PRIVATE}
    v2 = publish(lib, "prop.lamp", doc)
    assert (v2.created, v2.rights.license_class) == (True, "private")
    assert any("descriptor" in r for r in v2.rights.reasons)
    # the earlier declaration carries forward only where the descriptor is silent
    assert read_version(lib, "prop.lamp", "v002")["source"] is None
    with pytest.raises(RightsRefusal):
        promote([lib], "prop.lamp", to=_memory("an"))


def test_an_explicit_source_counts_beside_the_descriptor_never_instead():
    """B1 / M04: a looser asset-level source does not hide a stricter descriptor."""
    lib = _memory()
    r = publish(lib, "prop.lamp", {"name": "lamp", "source": PRIVATE}, source=CC0)
    assert r.rights.license_class == "private"
    loose = publish(lib, "prop.chair", {"name": "chair", "source": CC0}, source=PRIVATE)
    assert loose.rights.license_class == "private"


RELICENCE = {
    "by": "the maintainer",
    "reason": "licence bought from the studio, 2026-10-01",
}
CARVED = b"\x89PNG carved from a film"


def _carved_lamp(lib):
    return publish(
        lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": CARVED}, source=PRIVATE
    )


@pytest.mark.parametrize(
    "how",
    [
        {"doc": {"name": "lamp", "source": CC0}},  # the descriptor now says cc0
        {"doc": {"name": "lamp"}, "source": CC0},  # or the publisher does
    ],
    ids=["descriptor", "source"],
)
def test_a_later_version_cannot_relabel_the_earlier_versions_private_art(how):
    """R2-B1: v002 with the SAME carved bytes and a cc0 label stays private, and
    promote refuses it. Rights attach to the bytes and the lineage."""
    lib = _memory("cutan")
    _carved_lamp(lib)
    v2 = publish(
        lib,
        "prop.lamp",
        how["doc"],
        {"parts/lamp.png": CARVED},
        source=how.get("source"),
    )
    assert (str(v2.ref), v2.rights.license_class) == ("cutan:prop.lamp@v002", "private")
    assert read_version(lib, "prop.lamp", "v002")["previous"] == "cutan:prop.lamp@v001"
    with pytest.raises(RightsRefusal):
        promote([lib], "prop.lamp", to=_memory("an"))


def test_a_recarve_with_new_bytes_still_inherits_its_predecessor():
    lib = _memory("cutan")
    _carved_lamp(lib)
    v2 = publish(
        lib,
        "prop.lamp",
        {"name": "lamp", "source": CC0},
        {"parts/lamp.png": b"re-carved"},
    )
    assert v2.rights.license_class == "private"
    assert any("previous version cutan:prop.lamp@v001" in r for r in v2.rights.reasons)


def test_a_parts_recorded_source_travels_with_its_bytes_to_a_new_id():
    """No lineage at all: a carved file's own recorded source follows its bytes."""
    lib = _memory("cutan")
    carved = {"lamp": {"lamp": {"path": "parts/lamp.png", "source": PRIVATE}}}
    publish(
        lib,
        "prop.lamp",
        {"name": "lamp", "skins": {"default": {"slots": carved}}},
        {"parts/lamp.png": CARVED},
        source=CC0,
    )
    other = publish(
        lib, "prop.lantern", {"name": "lantern"}, {"art/x.png": CARVED}, source=CC0
    )
    assert other.rights.license_class == "private"
    assert any("same bytes as cutan:prop.lamp@v001" in r for r in other.rights.reasons)


def test_asset_level_private_bytes_copied_into_a_new_id_stay_private():
    """R3 escape (a): the chair's carved part, labelled private only at asset
    level, copied into a new asset marked cc0 — in the descriptor or by source=."""
    lib = _memory("cutan")
    publish(
        lib,
        "prop.chair",
        {"name": "chair"},
        {"parts/chair.svg": CARVED},
        source=PRIVATE,
    )
    stool = publish(
        lib, "prop.stool", {"name": "stool"}, {"parts/stool.svg": CARVED}, source=CC0
    )
    bench = publish(
        lib, "prop.bench", {"name": "bench", "source": CC0}, {"p.svg": CARVED}
    )
    assert (stool.rights.license_class, bench.rights.license_class) == (
        "private",
        "private",
    )
    assert any("same bytes as cutan:prop.chair@v001" in r for r in stool.rights.reasons)
    with pytest.raises(RightsRefusal):
        promote([lib], "prop.stool", to=_memory("an"))


def test_private_bytes_in_a_genre_library_bind_the_core_library_too():
    """R3 escape (b): the core library reads no genre library on its search path,
    but a blob's floor comes from every library on this machine."""
    cutan, core = open_library("cutan"), open_library("an")  # on disk, temp roots
    carved = {"chair": {"chair": {"path": "parts/chair.svg", "source": PRIVATE}}}
    publish(
        cutan,
        "prop.chair",
        {"name": "chair", "skins": {"default": {"slots": carved}}},
        {"parts/chair.svg": CARVED},
        source=CC0,
    )
    copy = publish(
        core, "prop.chair-copy", {"name": "copy"}, {"parts/x.svg": CARVED}, source=CC0
    )
    assert copy.rights.license_class == "private"
    assert [h.license_class for h in find(core, kind="prop")] == ["private"]


def _factory(tmp_path, name):
    from an.characters.factory import new_character

    return new_character(tmp_path / name, name=name, use_dicebear=False).parent


def _carve_head(folder: Path) -> None:
    """Replace the factory's head with carved art; its stale stamp stays behind."""
    (folder / "parts" / "head.svg").write_bytes(
        b"<svg><!-- carved from a film --></svg>"
    )


@pytest.mark.parametrize(
    "carved_first", [True, False], ids=["carved-first", "factory-first"]
)
def test_shared_factory_parts_stay_free_in_either_publish_order(tmp_path, carved_first):
    alice, bob = _factory(tmp_path, "alice"), _factory(tmp_path, "bob")
    _carve_head(alice)
    lib = _memory("cutan")
    steps = [
        lambda: publish_dir(lib, alice, "character.alice", source=PRIVATE),
        lambda: publish_dir(lib, bob, "character.bob", source=MIT),
    ]
    results = [step() for step in (steps if carved_first else steps[::-1])]
    by_id = {r.ref.asset_id: r.rights.license_class for r in results}
    assert by_id == {"character.alice": "private", "character.bob": "free"}
    assert [h.asset_id for h in find(lib, rights="publishable")] == ["character.bob"]


def test_a_stale_factory_stamp_does_not_itemise_re_carved_bytes(tmp_path):
    alice = _factory(tmp_path, "alice")
    _carve_head(alice)
    lib = _memory("cutan")
    publish_dir(lib, alice, "character.alice", source=PRIVATE)
    # Someone copies the carved head AND its (stale) factory stamp into a new asset.
    doc = json.loads((alice / "character.json").read_text(encoding="utf-8"))
    head = doc["skins"]["default"]["slots"]["head"]["head"]
    thief = {
        "kind": "CharacterDescriptor",
        "name": "t",
        "skins": {"default": {"slots": {"head": {"head": head}}}},
    }
    stolen = publish(
        lib,
        "character.thief",
        thief,
        {"parts/head.svg": (alice / "parts" / "head.svg").read_bytes()},
        source=CC0,
    )
    assert stolen.rights.license_class == "private"


def test_reindex_rebuilds_the_floor():
    from an.library import reindex

    lib = _memory("cutan")
    publish(
        lib,
        "prop.chair",
        {"name": "chair"},
        {"parts/chair.svg": CARVED},
        source=PRIVATE,
    )
    lib.blob_rights.clear()  # a lost or stale index
    assert reindex(lib) == 1
    stool = publish(lib, "prop.stool", {"name": "stool"}, {"s.svg": CARVED}, source=CC0)
    assert stool.rights.license_class == "private"


def test_relaxing_takes_an_explicit_recorded_relicence():
    lib = _memory("cutan")
    _carved_lamp(lib)
    with pytest.raises(LibraryError, match="who and why"):
        publish(
            lib,
            "prop.lamp",
            {"name": "lamp"},
            {"parts/lamp.png": CARVED},
            source=CC0,
            relicense={"by": "me"},
        )
    v2 = publish(
        lib,
        "prop.lamp",
        {"name": "lamp"},
        {"parts/lamp.png": CARVED},
        source=CC0,
        relicense=RELICENCE,
    )
    assert v2.rights.license_class == "free"
    assert (
        v2.rights.reasons[-1]
        == f"relicensed by {RELICENCE['by']}: {RELICENCE['reason']}"
    )
    assert read_version(lib, "prop.lamp", "v002")["relicense"] == RELICENCE
    # the relicence covers those bytes from then on; a later edit stays free
    v3 = publish(
        lib, "prop.lamp", {"name": "lamp", "note": "tidied"}, {"parts/lamp.png": CARVED}
    )
    assert v3.rights.license_class == "free"
    assert promote([lib], "prop.lamp", to=_memory("an")).rights.license_class == "free"


def test_a_descriptor_source_can_only_tighten_within_a_version():
    lib = _memory()
    r = publish(lib, "prop.lamp", {"name": "lamp", "source": PRIVATE}, source=CC0)
    assert r.rights.license_class == "private"
    relicensed = publish(
        lib,
        "prop.desk",
        {"name": "desk", "source": PRIVATE},
        source=CC0,
        relicense=RELICENCE,
    )
    assert relicensed.rights.license_class == "free"
    with pytest.raises(LibraryError):
        publish(lib, "prop.chair", {"name": "chair"}, relicense=RELICENCE)


def test_a_licence_only_change_makes_a_new_version():
    """M06: the source is part of the version identity."""
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0)
    again = publish(lib, "prop.lamp", {"name": "lamp"}, source=PRIVATE)
    assert (again.created, str(again.ref)) == (True, "an:prop.lamp@v002")


# --------------------------------------------------------------------------- B2


def test_checkout_carries_private_rights_into_the_project(project):
    """B2: a source set at publish reaches `an credits` and the private-study warning."""
    lib = _memory("cutan")
    _vase(lib)
    checkout(lib, project, "prop.vase")
    mall = build_project_mall(project)
    report = collect_credits(mall)
    assert [e.license_class for e in report.entries] == ["private"]
    scene_report = credits_for_scene(mall, _scene_casting("props", "vase"))
    with pytest.warns(PrivateStudyWarning):
        assert warn_if_private_study(scene_report)


def test_checkout_carries_rights_inherited_from_a_parent(project):
    """B2: a cc0 recolour derived from a private original is private in the project too."""
    lib = _memory("cutan")
    _vase(lib)
    publish(
        lib,
        "prop.vase-blue",
        {"name": "vase", "source": CC0},
        {"parts/vase.svg": b"<svg>blue</svg>"},
        derived_from=["prop.vase"],
    )
    result = checkout(lib, project, "prop.vase-blue")
    assert result.rights.license_class == "private"
    report = collect_credits(build_project_mall(project))
    assert {e.license_class for e in report.entries} == {"free", "private"}
    assert any("cutan:prop.vase@v001" in e.asset for e in report.private)


def test_a_promoted_copy_keeps_its_rights_without_the_genre_library():
    """A parent off the search path falls back to the rights recorded at publish."""
    cutan, core = _memory("cutan"), _memory("an")
    publish(cutan, "prop.lamp", {"name": "lamp"}, source=CC0)
    promote([cutan], "prop.lamp", to=core)
    assert [h.license_class for h in find(core, kind="prop")] == ["free"]


def test_an_unedited_checkout_with_no_metadata_publishes_back_unchanged(project):
    """M26: check-out created `metadata` and `source`; publish removes exactly those."""
    lib = _memory("cutan")
    _vase(lib, source=CC0)
    checkout(lib, project, "prop.vase")
    written = json.loads(
        (project / "assets" / "props" / "vase" / "prop.json").read_text(
            encoding="utf-8"
        )
    )
    assert "metadata" in written and written["source"] == CC0
    back = publish_dir(lib, project / "assets" / "props" / "vase", "prop.vase")
    assert not back.created


# --------------------------------------------------------------------------- B3


def _hostile_version(lib, path: str) -> None:
    """A version whose stored file path escapes, with a manifest computed over it."""
    data = b"pwned"
    ref = lib.blobs.add(data).to_json()
    version = {
        "kind": "LibraryVersion",
        "schema_version": "0.1.0",
        "asset": "prop.trojan",
        "version": "v001",
        "doc_kind": "prop",
        "doc": {"name": "trojan"},
        "files": {path: ref},
        "source": CC0,
        "derived_from": [],
        "rights": {"license_class": "free", "publishable": True, "reasons": []},
    }
    version["manifest_sha256"] = library_api.version_manifest(version)
    lib.versions["prop.trojan@v001"] = version
    lib.records["prop.trojan"] = {"id": "prop.trojan", "kind": "prop", "head": "v001"}


@pytest.mark.parametrize(
    "path", ["../../../escaped.txt", "parts/../../../x.txt", "/abs.txt"]
)
def test_checkout_never_writes_outside_the_project(project, path):
    """B3: a library on the search path may be hostile; its paths are not trusted."""
    lib = _memory("share")
    _hostile_version(lib, path)
    with pytest.raises(IntegrityError):
        checkout(lib, project, "prop.trojan")
    root = project.parent
    assert not [p for p in root.rglob("*.txt") if p.read_bytes() == b"pwned"]


def test_a_tampered_manifest_is_refused(project):
    """M09: the manifest check, not only the blob hashes."""
    blobs, versions = {}, {}
    lib = open_library("an", records={}, versions=versions, blobs=blobs)
    _vase(lib, source=CC0)
    versions["prop.vase@v001"] = {
        **versions["prop.vase@v001"],
        "manifest_sha256": "0" * 64,
    }
    with pytest.raises(IntegrityError, match="manifest"):
        checkout(lib, project, "prop.vase")


# --------------------------------------------------------------------------- S1


def test_the_folder_backend_creates_versions_exclusively(tmp_path):
    files = LocalFiles(tmp_path / "v")
    files.create_only("a/v001.json", b"first")
    with pytest.raises(VersionExistsError):
        files.create_only("a/v001.json", b"second")
    assert files["a/v001.json"] == b"first"
    assert not [p for p in (tmp_path / "v").rglob("*") if p.name.startswith(".tmp-")]


def test_a_publisher_that_loses_the_race_takes_the_next_label(monkeypatch):
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0)
    # Another publisher writes v002 between our read of the labels and our write.
    real = library_api.versions_of
    calls = {"n": 0}

    def stale(library, asset_id):
        calls["n"] += 1
        if calls["n"] == 1:
            library.versions["prop.lamp@v002"] = {"theirs": True}
            return ["v001"]
        return real(library, asset_id)

    monkeypatch.setattr(library_api, "versions_of", stale)
    mine = publish(lib, "prop.lamp", {"name": "lamp 2"})
    assert str(mine.ref) == "an:prop.lamp@v003"
    assert lib.versions["prop.lamp@v003"]["manifest_sha256"] == mine.manifest_sha256


def test_one_damaged_version_does_not_blind_every_search():
    versions: dict = {}
    lib = open_library("an", records={}, versions=versions, blobs={})
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0)
    publish(lib, "prop.chair", {"name": "chair"}, source=CC0)
    versions["prop.chair@v001"] = "{torn"
    with pytest.warns(LibraryIndexWarning, match="prop.chair"):
        hits = [h.asset_id for h in find(lib)]
    assert hits == ["prop.lamp"]


def test_a_torn_write_cannot_happen_on_disk(tmp_path):
    files = LocalFiles(tmp_path / "r")
    files["x.json"] = b"{}"
    files["x.json"] = b'{"a": 1}'
    assert files["x.json"] == b'{"a": 1}' and len(files) == 1


# --------------------------------------------------------------------------- S2


def test_an_art_edited_checkout_is_a_fork_not_the_version(project):
    lib = _memory()
    _vase(lib, source=CC0)
    checkout(lib, project, "prop.vase")
    art = project / "assets" / "props" / "vase" / "parts" / "vase.svg"
    art.write_bytes(b"<svg>edited</svg>")
    assert verify_checkout(lib, project) == {"props/vase": ["parts/vase.svg edited"]}
    with pytest.raises(CheckoutError, match="fork"):
        checkout(lib, project, "prop.vase")
    assert art.read_bytes() == b"<svg>edited</svg>"
    checkout(lib, project, "prop.vase", overwrite=True)
    assert verify_checkout(lib, project) == {"props/vase": []}


# --------------------------------------------------------------------------- S3


def test_promote_refuses_to_merge_an_unrelated_asset_sharing_the_id():
    cutan, core = _memory("cutan"), _memory("an")
    publish(core, "prop.lamp", {"name": "south park lamp"}, source=CC0, title="SP")
    publish(cutan, "prop.lamp", {"name": "reiniger lamp"}, source=CC0)
    with pytest.raises(LibraryError, match="as_id"):
        promote([cutan], "prop.lamp", to=core)
    assert core.records["prop.lamp"]["head"] == "v001"
    r = promote([cutan], "prop.lamp", to=core, as_id="prop.lamp-reiniger")
    assert str(r.ref) == "an:prop.lamp-reiniger@v001"
    # promoting the same asset again follows its own earlier copy
    publish(cutan, "prop.lamp", {"name": "reiniger lamp, fixed"})
    assert promote([cutan], "prop.lamp", to=core, as_id="prop.lamp-reiniger").created


def test_expect_head_guards_a_publish():
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0, expect_head=None)
    with pytest.raises(LibraryError, match="already exists"):
        publish(lib, "prop.lamp", {"name": "another lamp"}, expect_head=None)
    assert publish(lib, "prop.lamp", {"name": "lamp 2"}, expect_head="v001").created


# --------------------------------------------------------------------------- S4


def test_check_pins_reports_a_scene_and_lockfile_that_disagree(project):
    lib = _memory("cutan")
    _vase(lib, source=CC0)
    publish(lib, "prop.vase", {"name": "vase 2"}, {"parts/vase.svg": b"<svg>2</svg>"})
    checkout(lib, project, "prop.vase@v002")
    scene = markdown_to_ir(
        "# Cast\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1.0\n```\n\n"
        "```yaml entities\n"
        '- {id: vase, kind: prop, store: props, ref: vase, library: "cutan:prop.vase@v001"}\n'
        '- {id: cup, kind: prop, store: props, ref: cup, library: "prop.cup@v001"}\n'
        "```\n"
    )
    findings = check_pins(scene, ProjectLock(project))
    assert [f.ir_path for f in findings] == [
        "timeline/0/entities/0/library",
        "timeline/0/entities/1/library",
    ]
    assert "checked out from cutan:prop.vase@v002" in findings[0].description


# --------------------------------------------------------------------------- S5


def test_tampered_stored_rights_are_not_trusted():
    versions: dict = {}
    cutan = open_library("cutan", records={}, versions=versions, blobs={})
    _vase(cutan)
    v = versions["prop.vase@v001"]
    versions["prop.vase@v001"] = {
        **v,
        "rights": {"license_class": "free", "publishable": True, "reasons": []},
    }
    with pytest.raises(RightsRefusal):
        promote([cutan], "prop.vase", to=_memory("an"))
    assert len(find(cutan, rights="publishable")) == 0
    assert show(cutan, "prop.vase")["rights"]["license_class"] == "private"


# --------------------------------------------------------------------------- S6


def test_a_pinned_blob_cannot_be_deleted_and_a_missing_one_is_an_integrity_error(
    project,
):
    backend: dict = {}
    lib = open_library("an", records={}, versions={}, blobs=backend)
    _vase(lib, source=CC0)
    sha = next(iter(backend))
    with pytest.raises(VersionExistsError):
        del lib.blobs[sha]
    del backend[sha]  # what a damaged or partial copy of a library looks like
    with pytest.raises(IntegrityError, match="missing"):
        checkout(lib, project, "prop.vase")


# --------------------------------------------------------------------------- S8


def test_an_unregistered_capability_is_refused_not_answered_with_nothing():
    with pytest.raises(LibraryError, match="limbs.legs"):
        find(_memory(), affords="limbs.leg")


# --------------------------------------------------------------------------- nits


def test_opening_and_searching_a_library_creates_nothing(tmp_path):
    lib = open_library("cutna", root=tmp_path / "typo")
    assert len(find(lib)) == 0
    assert not (tmp_path / "typo").exists()


def test_a_root_inside_a_git_work_tree_warns(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.warns(LibraryLocationWarning):
        open_library("an", root=repo / "lib")
    with warnings.catch_warnings():
        warnings.simplefilter("error", LibraryLocationWarning)
        open_library("an", root=tmp_path / "elsewhere")


def test_curation_can_be_replaced_not_only_added_to():
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0, style="south_park")
    publish(lib, "prop.lamp", {"name": "lamp"}, style="reiniger", replace_curation=True)
    assert lib.records["prop.lamp"]["facets"]["style"] == ["reiniger"]


def test_a_bad_checkout_key_is_a_sentence_not_a_traceback(project):
    lib = _memory()
    _vase(lib, source=CC0)
    with pytest.raises(CheckoutError):
        checkout(lib, project, "prop.vase", key="../up")


def test_the_store_layer_contains_its_keys(tmp_path):
    files = LocalFiles(tmp_path / "s")
    for bad in ("../x", "a/../../x", "/abs", "C:/x", "a\\b"):
        with pytest.raises(KeyError):
            files[bad] = b"x"
    assert not list(tmp_path.rglob("x"))


def test_build_library_mall_wraps_injected_stores_in_every_guard():
    mall = build_library_mall(records={}, versions={}, blobs={})
    ref = mall["blobs"].add(b"x")
    with pytest.raises(VersionExistsError):
        del mall["blobs"][ref.item_id]


# --------------------------------------------------------------------------- M13


_CUT_OUT_MODULES = (
    "an.characters",
    "an.motion",
    "an.adapters",
    "an.expression",
    "an.stage",
)


def test_no_library_module_imports_cut_out_code_at_module_level():
    """M13: the mechanism is core (ADR 0001); genre code is imported lazily.

    `import an` already loads the cut-out modules today, so a sys.modules check
    measures nothing for them. This reads the source: no MODULE-LEVEL import in
    `an/library/` names a cut-out module (imports inside functions are fine).
    """
    offenders = []
    for path in sorted(LIBRARY_PKG.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [
                f"{path.name}: {n}" for n in names if n.startswith(_CUT_OUT_MODULES)
            ]
    assert offenders == []
    assert len(list(LIBRARY_PKG.glob("*.py"))) >= 10  # the scan found the package


# --------------------------------------------------------------------------- round 2


def test_a_placeholder_character_affords_only_its_rest_view():
    """R2-S1: the compiler would draw a stand-in, so nothing but the rest view is afforded."""
    from an.library.api import PlaceholderRigWarning

    lib = _memory()
    with pytest.warns(PlaceholderRigWarning):
        r = publish(lib, "character.ghost", {"name": "ghost"}, source=CC0)
    assert sorted(r.affordances) == ["swap.view"]


@pytest.mark.parametrize(
    "paths",
    [
        ["parts/A.svg", "parts/a.svg"],
        ["parts/é.svg", "parts/é.svg"],  # NFC / NFD
        ["parts", "parts/x.svg"],
    ],
    ids=["case", "unicode-normalisation", "file-and-folder"],
)
def test_colliding_file_paths_are_refused_at_publish(paths):
    """R2-S2: on macOS or Windows they would be one file, or none."""
    with pytest.raises(LibraryError):
        publish(
            _memory(),
            "prop.x",
            {"name": "x"},
            {p: p.encode() for p in paths},
            source=CC0,
        )


def test_a_stored_version_with_colliding_paths_is_refused_before_any_write(project):
    lib = _memory("share")
    blob_a, blob_b = lib.blobs.add(b"A").to_json(), lib.blobs.add(b"a").to_json()
    version = {
        "kind": "LibraryVersion",
        "schema_version": "0.1.0",
        "asset": "prop.twins",
        "version": "v001",
        "doc_kind": "prop",
        "doc": {"name": "twins"},
        "files": {"parts/A.svg": blob_a, "parts/a.svg": blob_b},
        "source": CC0,
        "derived_from": [],
    }
    version["manifest_sha256"] = library_api.version_manifest(version)
    lib.versions["prop.twins@v001"] = version
    lib.records["prop.twins"] = {"id": "prop.twins", "kind": "prop", "head": "v001"}
    with pytest.raises(IntegrityError, match="colliding"):
        checkout(lib, project, "prop.twins")
    assert not (project / "assets" / "props" / "twins").exists()


@pytest.mark.parametrize("path", ["parts/a\x00b.svg", "parts/con.svg", "parts/x.svg."])
def test_unsafe_names_are_integrity_errors_not_tracebacks(project, path):
    """R2-N3: a NUL, a Windows-reserved name, a trailing dot."""
    lib = _memory("share")
    _hostile_version(lib, path)
    with pytest.raises(IntegrityError):
        checkout(lib, project, "prop.trojan")


def test_the_head_never_moves_backwards_under_racing_publishers():
    """R2-S3: a racer's late record write with an older head is corrected."""

    class LateRacer(dict):
        raced = False

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if value.get("head") == "v003" and not LateRacer.raced:
                LateRacer.raced = True  # the other publisher's stale write lands now
                super().__setitem__(key, {**value, "head": "v002"})

    records = LateRacer()
    lib = open_library("an", records=records, versions={}, blobs={})
    for n in range(3):
        publish(lib, "prop.lamp", {"name": f"lamp {n}"}, source=CC0)
    assert LateRacer.raced and records["prop.lamp"]["head"] == "v003"


def test_containment_alone_stops_a_symlinked_folder_in_the_project(project, tmp_path):
    """R2-N1: a clean path through a symlinked `parts/` would land outside."""
    import os

    outside = tmp_path / "outside"
    outside.mkdir()
    entry = project / "assets" / "props" / "vase"
    entry.mkdir(parents=True)
    try:
        os.symlink(outside, entry / "parts", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem or user cannot create symlinks")
    lib = _memory()
    _vase(lib, source=CC0)
    with pytest.raises(IntegrityError, match="outside"):
        checkout(lib, project, "prop.vase")
    assert list(outside.iterdir()) == []


def test_create_only_falls_back_to_an_exclusive_open_without_hard_links(
    tmp_path, monkeypatch
):
    import os

    def no_links(*_a, **_k):
        raise PermissionError("hard links not supported here")

    monkeypatch.setattr(os, "link", no_links)
    files = LocalFiles(tmp_path / "v")
    files.create_only("a/v001.json", b"first")
    with pytest.raises(VersionExistsError):
        files.create_only("a/v001.json", b"second")
    assert files["a/v001.json"] == b"first"
