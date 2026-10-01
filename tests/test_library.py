"""The asset library (ADR 0005, plan P5): roots, stores, publish, rights, affordances, find, checkout, promote.

Every test runs against a temporary root. The autouse fixture points every
package's root variable (``AN_HOME``, ``CUTAN_HOME``) and ``XDG_DATA_HOME`` at
``tmp_path``, so nothing here can read or write the real ``~/.local/share``.
The characters are synthetic: the offline factory's procedural rigs and
hand-built descriptors, never carved or third-party art.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from an.characters.factory import new_character
from an.characters.schema import CharacterDescriptor
from an.ir.assets import AssetSource
from an.library import (
    AssetIdError,
    AssetNotFoundError,
    CheckoutError,
    IntegrityError,
    LibraryError,
    RightsRefusal,
    VersionExistsError,
    build_library_mall,
    checkout,
    find,
    library_root,
    open_library,
    project_dir,
    promote,
    publish,
    publish_dir,
    resolve,
    search_path,
    show,
    vocabulary,
)
from an.library.affordances import ANALYSERS
from an.library.character import CHARACTER_ANALYSER_VERSION
from an.library.lock import LOCKFILE_NAME, ProjectLock
from an.library.rights import roll_up
from an.project import init as init_project

MIT = {"provider": "an-tests", "license": "mit"}
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    """No test may touch a real library root."""
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def alice_dir(tmp_path) -> Path:
    """A complete procedural character folder: legs, arms, four views, nine mouths."""
    return new_character(tmp_path / "art", name="alice", use_dicebear=False).parent


def _folder_files(folder: Path, *, skip: str = "character.json") -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != skip
    }


def _memory(name: str = "an"):
    return open_library(name, records={}, versions={}, blobs={})


# --------------------------------------------------------------------------- root


def test_root_resolution_order(tmp_path):
    env = {"CUTAN_HOME": "/from/env", "XDG_DATA_HOME": "/xdg"}
    assert library_root("/explicit", package="cutan", environ=env) == Path("/explicit")
    assert library_root(package="cutan", environ=env) == Path("/from/env")
    assert library_root(
        package="cutan", environ={"XDG_DATA_HOME": "/xdg"}, platform="linux"
    ) == Path("/xdg/cutan")


def test_a_relative_xdg_data_home_is_ignored_as_the_spec_requires():
    root = library_root(
        package="an", environ={"XDG_DATA_HOME": "rel/dir"}, platform="darwin"
    )
    assert root.as_posix().endswith(".local/share/an")


def test_macos_resolves_to_local_share_not_application_support():
    root = library_root(package="cutan", environ={}, platform="darwin")
    assert root == Path.home() / ".local" / "share" / "cutan"


def test_windows_uses_localappdata():
    root = library_root(
        package="cutan",
        environ={"LOCALAPPDATA": r"C:\Users\me\AppData\Local"},
        platform="win32",
    )
    assert root.parts[-1] == "cutan" and "AppData" in str(root)


def test_one_root_per_package_and_the_fixture_keeps_them_temporary(tmp_path):
    assert library_root(package="an") == tmp_path / "roots" / "an"
    assert library_root(package="cutan") == tmp_path / "roots" / "cutan"
    assert (
        project_dir("alice-and-bob", package="cutan")
        == tmp_path / "roots" / "cutan" / "projects" / "alice-and-bob"
    )


@pytest.mark.parametrize("bad", ["../up", "a/b", "", ".hidden"])
def test_a_project_id_cannot_escape_the_projects_folder(bad):
    with pytest.raises(ValueError):
        project_dir(bad)


# --------------------------------------------------------------------------- stores


def test_the_on_disk_layout_is_flat_and_readable(tmp_path):
    lib = open_library("cutan")
    publish(
        lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.svg": b"<svg/>"}, source=CC0
    )
    root = tmp_path / "roots" / "cutan" / "library"
    found = sorted(
        p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()
    )
    sha = json.loads(
        (root / "versions" / "prop.lamp" / "v001.json").read_text(encoding="utf-8")
    )["files"]["parts/lamp.svg"]["itemId"]
    assert found == [
        f"blob_rights/{sha[:2]}/{sha}.json",  # the derived floor index
        f"blobs/{sha[:2]}/{sha}",
        "records/prop.lamp.json",
        "versions/prop.lamp/v001.json",
    ]


def test_versions_are_write_once_even_when_injected():
    mall = build_library_mall(records={}, versions={}, blobs={})
    mall["versions"]["prop.a@v001"] = {"x": 1}
    with pytest.raises(VersionExistsError):
        mall["versions"]["prop.a@v001"] = {"x": 1}
    with pytest.raises(VersionExistsError):
        del mall["versions"]["prop.a@v001"]


def test_blobs_stay_content_addressed_when_injected():
    mall = build_library_mall(records={}, versions={}, blobs={})
    with pytest.raises(ValueError):
        mall["blobs"]["0" * 64] = b"not those bytes"


def test_a_key_that_is_not_an_id_never_reaches_the_filesystem(tmp_path):
    mall = build_library_mall(tmp_path / "lib")
    with pytest.raises(AssetIdError):
        mall["records"]["../../escaped"] = {}
    with pytest.raises(AssetIdError):
        mall["versions"]["../x@v001"] = {}
    assert not list(tmp_path.glob("**/escaped*"))


def test_an_unknown_store_override_is_refused():
    with pytest.raises(TypeError):
        build_library_mall(records={}, versions={}, blobs={}, thumbnails={})


# --------------------------------------------------------------------------- publish


def test_publish_numbers_versions_and_an_unchanged_publish_makes_none(alice_dir):
    lib = _memory("cutan")
    first = publish_dir(lib, alice_dir, "character.alice", source=MIT)
    again = publish_dir(lib, alice_dir, "character.alice")
    (alice_dir / "parts" / "head.svg").write_text(
        "<svg><!-- re-carved --></svg>", encoding="utf-8"
    )
    edited = publish_dir(lib, alice_dir, "character.alice", note="re-carved head")
    assert (str(first.ref), first.created) == ("cutan:character.alice@v001", True)
    assert (str(again.ref), again.created) == ("cutan:character.alice@v001", False)
    assert (str(edited.ref), edited.created) == ("cutan:character.alice@v002", True)
    assert lib.records["character.alice"]["head"] == "v002"


def test_identical_bytes_are_stored_once(alice_dir):
    lib = _memory()
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    n = len(lib.blobs)
    (alice_dir / "parts" / "head.svg").write_text("<svg>new</svg>", encoding="utf-8")
    publish_dir(lib, alice_dir, "character.alice")
    assert len(lib.blobs) == n + 1  # one changed file, one new blob


def test_the_manifest_is_the_version_identity_across_libraries(alice_dir):
    a = publish_dir(_memory("an"), alice_dir, "character.alice", source=MIT)
    b = publish_dir(_memory("cutan"), alice_dir, "character.alice", source=MIT)
    assert a.manifest_sha256 == b.manifest_sha256


def test_a_declared_source_carries_forward_to_later_versions(alice_dir):
    lib = _memory()
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    (alice_dir / "parts" / "torso.svg").write_text(
        "<svg>changed</svg>", encoding="utf-8"
    )
    later = publish_dir(lib, alice_dir, "character.alice")
    # The carried MIT speaks for the bytes it was declared on, not for the
    # re-drawn torso (review-259 S1): that one is unlabelled until relabelled.
    assert later.created and later.rights.license_class == "unknown"
    assert any("parts/torso.svg" in r for r in later.rights.reasons)
    (alice_dir / "parts" / "arm_l.svg").write_text("<svg>also</svg>", encoding="utf-8")
    third = publish_dir(lib, alice_dir, "character.alice")
    assert third.rights.license_class == "unknown"  # still unlabelled, carried on
    # like any inherited restriction, it is lifted only by a recorded relicence
    relabelled = publish_dir(
        lib, alice_dir, "character.alice", source=MIT,
        relicense={"by": "tests", "reason": "re-drew the torso and arm myself"},
    )
    assert relabelled.rights.license_class == "free"


def test_re_tagging_is_curation_and_makes_no_version():
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0, style="reiniger")
    r = publish(
        lib,
        "prop.lamp",
        {"name": "lamp"},
        style="gilliam",
        tags="victorian",
        status="approved",
    )
    rec = lib.records["prop.lamp"]
    assert not r.created
    assert rec["facets"]["style"] == ["reiniger", "gilliam"] and rec["tags"] == [
        "victorian"
    ]
    assert rec["status"] == "approved"


@pytest.mark.parametrize(
    "bad", ["Alice", "character", "character/alice", "character.Alice", ".x"]
)
def test_an_asset_id_must_be_kind_dot_slug(bad):
    with pytest.raises(AssetIdError):
        publish(_memory(), bad, {"name": "x"})


def test_an_unregistered_kind_and_a_bad_status_are_refused():
    with pytest.raises(ValueError, match="not registered"):
        publish(_memory(), "spaceship.x", {"name": "x"})
    with pytest.raises(LibraryError):
        publish(_memory(), "prop.x", {"name": "x"}, status="final")


def test_a_file_path_cannot_leave_the_asset():
    with pytest.raises(LibraryError):
        publish(_memory(), "prop.x", {"name": "x"}, {"../outside.svg": b"<svg/>"})


def test_derived_from_must_resolve_and_rights_are_inherited():
    lib = _memory()
    publish(lib, "prop.original", {"name": "o"}, source=PRIVATE)
    with pytest.raises(LibraryError, match="does not resolve"):
        publish(
            lib, "prop.copy", {"name": "c"}, source=CC0, derived_from=["prop.nope@v001"]
        )
    child = publish(
        lib, "prop.copy", {"name": "c"}, source=CC0, derived_from=["prop.original"]
    )
    assert child.rights.license_class == "private"
    assert lib.versions["prop.copy@v001"]["derived_from"] == ["an:prop.original@v001"]


# --------------------------------------------------------------------------- rights


def test_the_most_restrictive_class_wins():
    order = [
        ("a", AssetSource(provider="p", license=lic))
        for lic in ("cc0-1.0", "cc-by-4.0")
    ]
    assert roll_up(order).license_class == "attribution"
    assert roll_up([*order, ("b", None)]).license_class == "unknown"
    assert (
        roll_up([*order, ("b", None), ("c", AssetSource(**PRIVATE))]).license_class
        == "private"
    )


def test_no_source_is_unknown_and_unknown_is_not_publishable():
    r = publish(_memory(), "prop.x", {"name": "x"})
    assert (r.rights.license_class, r.rights.publishable) == ("unknown", False)


def test_a_private_part_makes_the_whole_version_private(alice_dir):
    """Per-part sources are read by the same walk `an credits` runs (an#220)."""
    doc = json.loads((alice_dir / "character.json").read_text(encoding="utf-8"))
    doc["skins"]["default"]["slots"]["head"]["head"]["source"] = PRIVATE
    r = publish(_memory(), "character.alice", doc, _folder_files(alice_dir), source=MIT)
    assert r.rights.license_class == "private"
    assert r.rights.reasons == [
        "parts/head.svg: all-rights-reserved-private-study (private)"
    ]


# --------------------------------------------------------------------------- affordances


def _afford(lib, asset_id):
    return lib.versions[f"{asset_id}@v001"]["affordances"]


def test_a_complete_rig_affords_everything_the_first_analyser_knows(alice_dir):
    lib = _memory()
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    a = _afford(lib, "character.alice")
    assert sorted(a) == [
        "face.brows",  # an#252
        "face.mouth",
        "limbs.arms",
        "limbs.legs",
        "swap.view",
    ]
    assert a["limbs.legs"]["slots"] == ["leg_l", "leg_r"]
    assert a["swap.view"]["keys"] == ["front", "three_quarter", "side", "back"]
    assert a["face.mouth"]["keys"] == ["rhubarb9"] and a["face.mouth"]["variants"] == [
        "happy",
        "sad",
    ]
    assert lib.versions["character.alice@v001"]["analysers"] == {
        "character": CHARACTER_ANALYSER_VERSION
    }


def test_slots_without_their_art_afford_nothing(alice_dir):
    """A descriptor that promises legs whose drawings are missing has no legs."""
    files = {
        p: b
        for p, b in _folder_files(alice_dir).items()
        if not p.startswith("parts/leg_")
    }
    files = {
        p: b
        for p, b in files.items()
        if p not in ("parts/head_side.svg", "parts/torso_side.svg")
    }
    doc = json.loads((alice_dir / "character.json").read_text(encoding="utf-8"))
    lib = _memory()
    publish(lib, "character.alice", doc, files, source=MIT)
    a = _afford(lib, "character.alice")
    assert "limbs.legs" not in a
    assert "side" not in a["swap.view"]["keys"]


def test_a_legless_blob_has_its_rest_view_and_no_gait_capability():
    """Which walks apply is the matcher's answer (ADR 0002), not a stored fact."""
    lib = _memory()
    publish(lib, "character.blob", CharacterDescriptor(name="blob"), source=CC0)
    a = _afford(lib, "character.blob")
    assert sorted(a) == ["swap.view"]
    assert a["swap.view"] == {
        "keys": ["front"],
        "rest": "front",
        "swappable": False,
        "overrides": [],
    }


def test_declared_facts_are_reported_as_the_overrides_they_are():
    doc = CharacterDescriptor(name="silhouette", rest_view="side", gait="hem")
    lib = _memory()
    publish(lib, "character.silhouette", doc, source=CC0)
    a = _afford(lib, "character.silhouette")
    assert a["swap.view"]["keys"] == ["side"] and a["swap.view"]["overrides"] == [
        "rest_view"
    ]


def test_a_baked_face_has_no_mouth_to_lip_sync(alice_dir):
    doc = json.loads((alice_dir / "character.json").read_text(encoding="utf-8"))
    doc["face_overlay"] = False
    lib = _memory()
    publish(lib, "character.baked", doc, _folder_files(alice_dir), source=MIT)
    assert "face.mouth" not in _afford(lib, "character.baked")


def test_a_snapshot_from_an_older_analyser_is_recomputed_not_trusted(alice_dir):
    lib = _memory()
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    backend = lib.versions.store  # the write-once guard's injected dict
    stale = dict(backend["character.alice@v001"])
    stale.update(affordances={}, analysers={"character": "0.0.0"})
    backend["character.alice@v001"] = stale
    assert [h.asset_id for h in find(lib, affords="limbs.legs")] == ["character.alice"]
    assert ANALYSERS["character"].version != "0.0.0"


# --------------------------------------------------------------------------- find


@pytest.fixture
def stocked(alice_dir):
    """A cutan library with alice (legs, views) and a core library with a blob and a lamp."""
    cutan, core = _memory("cutan"), _memory("an")
    publish_dir(
        cutan,
        alice_dir,
        "character.alice",
        source=MIT,
        style="reiniger",
        family="alice",
        tags="dress",
    )
    publish(
        core,
        "character.blob",
        CharacterDescriptor(name="blob"),
        source=PRIVATE,
        style=["reiniger", "south_park"],
    )
    publish(core, "prop.lamp", {"name": "lamp"}, source=CC0, style="gilliam")
    return [cutan, core]


def test_and_across_facets_or_within_one(stocked):
    assert [h.ref for h in find(stocked, style=["gilliam", "south_park"])] == [
        "an:character.blob@v001",
        "an:prop.lamp@v001",
    ]
    assert [h.ref for h in find(stocked, kind="character", style="gilliam")] == []
    assert [
        h.ref for h in find(stocked, kind="character", style="reiniger", family="alice")
    ] == ["cutan:character.alice@v001"]


def test_capabilities_are_all_required_and_keys_are_queryable(stocked):
    assert [
        h.asset_id for h in find(stocked, affords=["limbs.legs", "swap.view:side"])
    ] == ["character.alice"]
    assert [h.asset_id for h in find(stocked, affords=["swap.view:front"])] == [
        "character.alice",
        "character.blob",
    ]
    assert [
        h.asset_id for h in find(stocked, affords=["limbs.legs", "swap.view:profile"])
    ] == []


def test_near_misses_name_what_is_missing_and_how_to_add_it(stocked):
    result = find(
        stocked, kind="character", affords=["limbs.legs", "swap.view:side"], near=True
    )
    assert [h.asset_id for h in result.hits] == ["character.alice"]
    (blob,) = result.near
    assert blob.missing == ["limbs.legs", "swap.view:side"] and blob.score == 0.0
    assert "leg_l" in blob.remedies["limbs.legs"]
    assert "add-views" in blob.remedies["swap.view:side"]
    assert (
        find(stocked, kind="character", affords="limbs.legs").near == []
    )  # only when asked


def test_the_rights_filter(stocked):
    assert {h.asset_id for h in find(stocked, rights="publishable")} == {
        "character.alice",
        "prop.lamp",
    }
    assert {h.asset_id for h in find(stocked, rights="private")} == {"character.blob"}
    assert len(find(stocked)) == 3  # study renders are legitimate: the default is any


def test_counts_cover_the_hits(stocked):
    counts = find(stocked, style="reiniger").counts
    assert counts["kind"] == {"character": 2}
    assert (
        counts["affords"]["swap.view:front"] == 2
        and counts["affords"]["limbs.legs"] == 1
    )


def test_ids_are_namespaced_only_when_federated(stocked):
    cutan, _ = stocked
    assert [h.ref for h in find(cutan, kind="character")] == ["character.alice@v001"]
    assert [h.ref for h in find(stocked, kind="character")][
        0
    ] == "cutan:character.alice@v001"


def test_the_search_path_reads_its_own_library_first(alice_dir):
    cutan, core = _memory("cutan"), _memory("an")
    publish(core, "prop.lamp", {"name": "core lamp"}, source=CC0)
    publish(cutan, "prop.lamp", {"name": "genre lamp"}, source=CC0)
    lib, ref, version = resolve([cutan, core], "prop.lamp")
    assert (lib.name, version["doc"]["name"]) == ("cutan", "genre lamp")
    lib, ref, version = resolve([cutan, core], "an:prop.lamp")
    assert (str(ref), version["doc"]["name"]) == ("an:prop.lamp@v001", "core lamp")
    with pytest.raises(AssetNotFoundError):
        resolve([cutan, core], "other:prop.lamp")


def test_search_path_order_on_disk(tmp_path):
    names = [lib.name for lib in search_path("cutan", extra=["vizan", "an"])]
    assert names == ["cutan", "an", "vizan"]
    assert search_path("cutan")[0].root == tmp_path / "roots" / "cutan"


def test_vocabulary_lists_facets_and_capabilities_with_remedies(stocked):
    v = vocabulary(stocked)
    assert v["facets"]["style"] == {"gilliam": 1, "reiniger": 2, "south_park": 1}
    assert v["capabilities"]["limbs.legs"]["count"] == 1
    assert v["capabilities"]["face.mouth"]["remedy"]


def test_show_resolves_latest_labels_and_hash_prefixes(alice_dir):
    lib = _memory()
    first = publish_dir(lib, alice_dir, "character.alice", source=MIT)
    (alice_dir / "parts" / "head.svg").write_text("<svg>2</svg>", encoding="utf-8")
    publish_dir(lib, alice_dir, "character.alice")
    assert show(lib, "character.alice")["ref"] == "an:character.alice@v002"
    assert show(lib, "character.alice@latest")["versions"] == ["v001", "v002"]
    assert (
        show(lib, f"character.alice@sha256:{first.manifest_sha256[:10]}")["ref"]
        == "an:character.alice@v001"
    )
    with pytest.raises(AssetNotFoundError):
        show(lib, "character.alice@v009")


# --------------------------------------------------------------------------- checkout


@pytest.fixture
def project(tmp_path) -> Path:
    return init_project(tmp_path / "proj")


def test_checkout_reproduces_the_folder_records_its_origin_and_pins_it(
    alice_dir, project
):
    lib = _memory("cutan")
    pub = publish_dir(lib, alice_dir, "character.alice", source=MIT)
    result = checkout(lib, project, "character.alice")
    target = project / "assets" / "characters" / "alice"
    assert _folder_files(target) == _folder_files(alice_dir)  # byte for byte
    doc = json.loads((target / "character.json").read_text(encoding="utf-8"))
    origin = doc["metadata"]["library_origin"]
    assert (origin["library"], origin["manifest_sha256"]) == (
        "cutan:character.alice@v001",
        pub.manifest_sha256,
    )
    assert origin["rights"]["license_class"] == "free"
    assert doc["source"] == MIT  # the asset-level source travels into the copy
    pin = ProjectLock(project)["characters/alice"]
    assert (pin["library"], pin["manifest_sha256"]) == (
        "cutan:character.alice@v001",
        pub.manifest_sha256,
    )
    assert (project / LOCKFILE_NAME).is_file()
    ref = result.asset_ref()
    assert (ref.store, ref.ref, ref.library) == (
        "characters",
        "alice",
        "cutan:character.alice@v001",
    )
    CharacterDescriptor.model_validate(doc)  # the project reads it as any descriptor


def test_checkout_is_idempotent_and_never_clobbers_a_fork(alice_dir, project):
    lib = _memory()
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    (alice_dir / "parts" / "head.svg").write_text("<svg>v2</svg>", encoding="utf-8")
    publish_dir(lib, alice_dir, "character.alice")
    assert checkout(lib, project, "character.alice@v001").changed
    assert not checkout(lib, project, "character.alice@v001").changed
    with pytest.raises(CheckoutError, match="overwrite"):
        checkout(lib, project, "character.alice@v002")
    assert checkout(lib, project, "character.alice@v002", overwrite=True).changed
    head = project / "assets" / "characters" / "alice" / "parts" / "head.svg"
    assert head.read_text(encoding="utf-8") == "<svg>v2</svg>"
    assert (
        checkout(lib, project, "character.alice@v001", key="alice-old").key
        == "alice-old"
    )


def test_an_unedited_checkout_publishes_back_as_the_same_version(alice_dir, project):
    lib = _memory("cutan")
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    checkout(lib, project, "character.alice")
    fork = project / "assets" / "characters" / "alice"
    assert not publish_dir(lib, fork, "character.alice").created
    (fork / "parts" / "arm_l.svg").write_text("<svg>longer arm</svg>", encoding="utf-8")
    edited = publish_dir(lib, fork, "character.alice")
    assert edited.created
    assert lib.versions["character.alice@v002"]["derived_from"] == [
        "cutan:character.alice@v001"
    ]


def test_checkout_verifies_the_bytes(alice_dir, project):
    blobs: dict = {}
    lib = open_library("an", records={}, versions={}, blobs=blobs)
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    some = next(iter(blobs))
    blobs[some] = b"tampered"
    with pytest.raises(IntegrityError):
        checkout(lib, project, "character.alice")


def test_a_kind_without_a_project_store_cannot_be_checked_out(project):
    lib = _memory()
    publish(lib, "motion.walk-profile", {"name": "walk"}, source=CC0)
    with pytest.raises(CheckoutError):
        checkout(lib, project, "motion.walk-profile")


def test_a_checked_out_character_is_cast_from_scene_md(alice_dir, project):
    """The pinned reference survives the scene.md → ir/scene.json round trip."""
    from an.ir.sync import ir_to_markdown, markdown_to_ir

    lib = _memory("cutan")
    publish_dir(lib, alice_dir, "character.alice", source=MIT)
    entity = checkout(lib, project, "character.alice").asset_ref()
    md = (
        "# Library cast\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1.0\n```\n\n"
        "```yaml entities\n"
        f'- {{id: alice, kind: character, store: characters, ref: alice, library: "{entity.library}"}}\n'
        "```\n"
    )
    scene = markdown_to_ir(md)
    assert scene.timeline[0].entities[0].library == "cutan:character.alice@v001"
    again = markdown_to_ir(ir_to_markdown(scene))
    assert again.model_dump_json() == scene.model_dump_json()


# --------------------------------------------------------------------------- promote


def test_promote_copies_to_the_core_library_with_lineage(alice_dir):
    cutan, core = _memory("cutan"), _memory("an")
    publish_dir(
        cutan,
        alice_dir,
        "character.alice",
        source=MIT,
        family="alice",
        style="reiniger",
    )
    r = promote([cutan], "character.alice", to=core)
    assert str(r.ref) == "an:character.alice@v001"
    assert core.versions["character.alice@v001"]["derived_from"] == [
        "cutan:character.alice@v001"
    ]
    assert core.records["character.alice"]["family"] == "alice"
    with pytest.raises(LibraryError, match="already"):
        promote([core], "character.alice", to=core)


@pytest.mark.parametrize("source", [PRIVATE, None])
def test_private_or_unknown_never_leaves_without_an_override(source):
    cutan, core = _memory("cutan"), _memory("an")
    publish(cutan, "prop.carved-chair", {"name": "chair"}, source=source)
    with pytest.raises(RightsRefusal):
        promote([cutan], "prop.carved-chair", to=core)
    assert len(core.records) == 0
    assert promote([cutan], "prop.carved-chair", to=core, allow_restricted=True).created


# --------------------------------------------------------------------------- import firewall


def test_importing_the_library_imports_no_cut_out_module():
    """The mechanism is core (ADR 0001): the character analyser imports its
    cut-out dependencies lazily, so `import an.library` adds none of them to
    what `import an` already loads (P3's firewall will shrink the latter)."""
    code = (
        "import sys, an; before = set(sys.modules); import an.library; "
        "new = set(sys.modules) - before; "
        "print(','.join(sorted(m for m in new if m.startswith(('an.motion', 'an.adapters', 'an.characters')))))"
    )
    # PYTHONPATH pins the tree under test: a bare `import an` in a child process
    # resolves through the editable install, which may be another checkout.
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root)}
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=root,
    )
    assert out.stdout.strip() == ""
