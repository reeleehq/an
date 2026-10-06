"""Per-file rights that never relax: ``--license-part`` and ``file_sources`` (an#345).

A version can state a licence per file (``file_sources``, sha-pinned), so a
whole-asset ``--license`` no longer has to say "private" about every file a
private part shares a folder with. The rule that makes it safe: a per-file
statement can only ever be stricter than what the bytes already carry, unless
an explicit recorded relicence names those bytes.

The negative tests replay the red-team probe of the design (five scenarios that
relax a floor statement through per-part sources on the code before an#345),
in their ``file_sources`` form: each must now refuse, or state the strict class.
Per-attachment sources keep their behaviour (whether to extend the rule to them
is an#357's question).

In-memory libraries; the root ``conftest.py`` points the machine registry into
a temporary folder.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.credits import credits_for_project
from an.ir.migrate import DocumentMigrationError, migrate
from an.library import LibraryError, checkout, open_library, publish
from an.library import api as library_api
from an.library.api import (
    FILE_SOURCES_FIELD,
    PER_FILE_SCHEMA_VERSION,
    RELICENSE_COVERS,
    VERSION_KIND,
    effective_rights,
    match_license_parts,
    promote,
    read_version,
    reindex,
)
from an.library.rights import RightsRefusal
from an.project import init as init_project

PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
RELICENSE = {"by": "tests", "reason": "the collar is drawn, not carved"}
HEAD = b"\x89PNG a head carved from a film"
HEAD2 = b"\x89PNG another head carved from a film"
COLLAR = b"<svg>a collar drawn by hand</svg>"
STRAY = b"<svg>a factory head nobody uses</svg>"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


def _memory(name: str = "cutan"):
    return open_library(name, records={}, versions={}, blobs={})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _floor(lib, data: bytes) -> dict[str, str]:
    """``{asset_key: class}`` the library's floor index holds about ``data``."""
    return {k: v["class"] for k, v in (lib.blob_rights.get(_sha(data)) or {}).items()}


STU_FILES = {
    "parts/head_1.png": HEAD,
    "parts/head_2.png": HEAD2,
    "parts/collar.svg": COLLAR,
    "factory/head_a.svg": STRAY,
}
HEADS_PRIVATE = {"parts/head_*.png": PRIVATE}


# --------------------------------------------------------------------------- the fix


def test_a_private_part_no_longer_makes_its_neighbours_private():
    """The stu-photo case, fresh: heads private, collar and stray files free."""
    lib = _memory()
    r = publish(
        lib,
        "prop.stu-photo",
        {"name": "stu"},
        STU_FILES,
        source=CC0,
        license_parts=HEADS_PRIVATE,
    )
    assert r.rights.license_class == "private"  # the version holds private heads
    assert _floor(lib, HEAD) == {"cutan:prop.stu-photo": "private"}
    assert _floor(lib, HEAD2) == {"cutan:prop.stu-photo": "private"}
    assert _floor(lib, COLLAR) == {"cutan:prop.stu-photo": "free"}
    assert _floor(lib, STRAY) == {"cutan:prop.stu-photo": "free"}
    version = read_version(lib, "prop.stu-photo", "v001")
    assert version["schema_version"] == PER_FILE_SCHEMA_VERSION
    assert set(version[FILE_SOURCES_FIELD]) == {"parts/head_1.png", "parts/head_2.png"}
    assert version[FILE_SOURCES_FIELD]["parts/head_1.png"]["sha256"] == _sha(HEAD)
    # Another asset holding the collar is not bound — no relicence needed.
    drawn = publish(lib, "prop.stu-drawn", {"name": "d"}, {"c.svg": COLLAR}, source=CC0)
    assert drawn.rights.license_class == "free"
    # ... while one holding a head is.
    copy = publish(lib, "prop.thief", {"name": "t"}, {"h.png": HEAD}, source=CC0)
    assert copy.rights.license_class == "private"


def test_the_stu_photo_history_needs_a_relicence_and_keeps_the_heads_private():
    """v001 said private about every file; v002 frees the collar only by a
    relicence, and the per-file private heads keep binding under it (L1-1, L1-14)."""
    lib = _memory()
    publish(lib, "prop.stu-photo", {"name": "stu"}, STU_FILES, source=PRIVATE)
    assert _floor(lib, COLLAR) == {"cutan:prop.stu-photo": "private"}
    # Without a relicence the collar stays private: v001 said so.
    r = publish(
        lib, "prop.stu-photo", {"name": "stu"}, STU_FILES, source=CC0,
        license_parts=HEADS_PRIVATE,
    )
    assert r.created and _floor(lib, COLLAR) == {"cutan:prop.stu-photo": "private"}
    r = publish(
        lib, "prop.stu-photo", {"name": "stu"}, STU_FILES, source=CC0,
        license_parts=HEADS_PRIVATE, relicense=RELICENSE,
    )
    assert r.rights.license_class == "private"  # the heads, never relicensed away
    assert _floor(lib, COLLAR) == {"cutan:prop.stu-photo": "free"}
    assert _floor(lib, HEAD) == {"cutan:prop.stu-photo": "private"}
    covers = read_version(lib, "prop.stu-photo", r.ref.version)["relicense"][
        RELICENSE_COVERS
    ]
    assert _sha(COLLAR) in covers and _sha(HEAD) not in covers


# --------------------------------------------------------------------------- the probe


def test_t1_a_later_version_cannot_relabel_bytes_its_chain_called_private():
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": HEAD}, source=PRIVATE)
    with pytest.raises(RightsRefusal, match="relicence"):
        publish(
            lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": HEAD},
            source=PRIVATE, license_parts={"parts/lamp.png": CC0},
        )
    assert _floor(lib, HEAD) == {"cutan:prop.lamp": "private"}


def test_t2_dropping_a_file_and_re_adding_it_relaxes_nothing():
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": HEAD}, source=PRIVATE)
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/other.png": b"x"}, source=PRIVATE)
    with pytest.raises(RightsRefusal):
        publish(
            lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": HEAD},
            source=PRIVATE, license_parts={"parts/lamp.png": CC0},
        )


def test_t2_a_dropped_per_file_statement_binds_its_bytes_when_they_return():
    lib = _memory()
    files = {"parts/lamp.png": HEAD, "parts/base.svg": COLLAR}
    publish(lib, "prop.lamp", {"name": "lamp"}, files, source=CC0,
            license_parts={"parts/lamp.png": PRIVATE})
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/base.svg": COLLAR}, source=CC0)
    with pytest.raises(RightsRefusal):
        publish(lib, "prop.lamp", {"name": "lamp"}, files, source=CC0,
                license_parts={"parts/lamp.png": CC0})
    # Re-added with no per-file label at all: the lineage still states it private.
    publish(lib, "prop.lamp", {"name": "lamp"}, files, source=CC0)
    assert _floor(lib, HEAD) == {"cutan:prop.lamp": "private"}


def test_t3_the_same_bytes_at_two_paths_have_one_statement():
    lib = _memory()
    with pytest.raises(LibraryError, match="same bytes"):
        publish(
            lib, "prop.x", {"name": "x"},
            {"parts/a_head.png": HEAD, "spare/z_copy.png": HEAD}, source=CC0,
            license_parts={"parts/a_head.png": PRIVATE, "spare/z_copy.png": CC0},
        )
    # A copy the globs miss takes the strictest statement of its bytes, not the
    # last path's.
    publish(
        lib, "prop.x", {"name": "x"},
        {"parts/a_head.png": HEAD, "spare/z_copy.png": HEAD}, source=CC0,
        license_parts={"parts/a_head.png": PRIVATE},
    )
    assert _floor(lib, HEAD) == {"cutan:prop.x": "private"}


def test_t4_a_derivative_cannot_label_bytes_new_to_a_private_lineage_free():
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": HEAD}, source=PRIVATE)
    with pytest.raises(RightsRefusal, match="prop.lamp@v001"):
        publish(
            lib, "prop.lamp-red", {"name": "red"}, {"parts/lamp.png": HEAD2},
            source=CC0, derived_from=["cutan:prop.lamp@v001"],
            license_parts={"parts/lamp.png": CC0},
        )


def test_t5_a_relicence_never_frees_a_part_labelled_stricter():
    lib = _memory()
    files = {"parts/lamp.png": HEAD, "parts/collar.svg": COLLAR}
    publish(lib, "prop.lamp", {"name": "lamp"}, files, source=PRIVATE)
    r = publish(
        lib, "prop.lamp", {"name": "lamp"}, files, source=CC0,
        license_parts={"parts/lamp.png": PRIVATE}, relicense=RELICENSE,
    )
    assert r.rights.license_class == "private"
    assert _floor(lib, HEAD) == {"cutan:prop.lamp": "private"}
    assert _floor(lib, COLLAR) == {"cutan:prop.lamp": "free"}
    head = read_version(lib, "prop.lamp", "v002")
    assert effective_rights(lib, head, owner=lib).license_class == "private"


# --------------------------------------------------------------------------- carrying


def test_per_file_statements_carry_for_unchanged_bytes_only():
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    # Republished as is: nothing new.
    again = publish(lib, "prop.stu", {"name": "stu"}, STU_FILES)
    assert not again.created
    # A changed collar keeps the others' statements; a changed head is unlabelled.
    edited = {**STU_FILES, "parts/head_1.png": b"\x89PNG re-carved", "parts/collar.svg": b"<svg/>"}
    r = publish(lib, "prop.stu", {"name": "stu"}, edited)
    v = read_version(lib, "prop.stu", r.ref.version)
    assert set(v[FILE_SOURCES_FIELD]) == {"parts/head_2.png"}
    assert "parts/head_1.png" in v["unlabelled"]
    assert r.rights.license_class == "private"
    assert _floor(lib, HEAD2) == {"cutan:prop.stu": "private"}


def test_a_per_file_label_on_unchanged_content_is_a_new_version_not_nothing():
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0)
    with pytest.raises(LibraryError, match="relabel"):
        publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
                license_parts=HEADS_PRIVATE, relabel={"by": "t", "reason": "r"})
    r = publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
                license_parts=HEADS_PRIVATE)
    assert r.created and r.rights.license_class == "private"


def test_a_derivative_does_not_re_spread_the_heads_over_its_collar():
    """L1-11: per-file statements count toward rights, never toward the label of
    the files nothing itemises — at every depth of the lineage."""
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    r = publish(lib, "prop.stu-hat", {"name": "hat"}, STU_FILES, source=CC0,
                derived_from=["cutan:prop.stu@v001"])
    assert r.rights.license_class == "private"
    assert _floor(lib, COLLAR)["cutan:prop.stu-hat"] == "free"
    assert _floor(lib, HEAD)["cutan:prop.stu-hat"] == "private"


def test_promote_carries_the_per_file_statements():
    genre, core = _memory("cutan"), _memory("an")
    publish(genre, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    promote([genre], "cutan:prop.stu@v001", to=core, allow_restricted=True)
    v = read_version(core, "prop.stu", "v001")
    assert set(v[FILE_SOURCES_FIELD]) == {"parts/head_1.png", "parts/head_2.png"}
    assert _floor(core, HEAD) == {"an:prop.stu": "private"}
    assert _floor(core, COLLAR) == {"an:prop.stu": "free"}


def test_reindex_restates_what_publish_stated():
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    before = {d: dict(e) for d, e in lib.blob_rights.items()}
    reindex(lib)
    assert {d: dict(e) for d, e in lib.blob_rights.items()} == before


def test_an_older_reader_refuses_a_version_with_per_file_statements():
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    raw = dict(lib.versions["prop.stu@v001"])
    with pytest.raises(DocumentMigrationError):
        migrate(raw, "0.1.0", kind=VERSION_KIND.name)
    # A version without them is still written at the old schema.
    publish(lib, "prop.plain", {"name": "p"}, {"a.svg": COLLAR}, source=CC0)
    assert lib.versions["prop.plain@v001"]["schema_version"] == "0.1.0"


# --------------------------------------------------------------------------- globs


def test_globs_are_segment_aware_case_exact_and_refuse_misses():
    paths = ["parts/stand.svg", "parts/stand_in/carved_face.svg", "parts/Head_3.PNG"]
    assert list(match_license_parts({"parts/stand*.svg": 1}, paths)) == ["parts/stand.svg"]
    assert set(match_license_parts({"parts/**/*.svg": 1}, paths)) == {
        "parts/stand.svg",
        "parts/stand_in/carved_face.svg",
    }
    with pytest.raises(LibraryError, match="matches no file"):
        match_license_parts({"parts/head_*.png": 1}, ["parts/body.png"])
    with pytest.raises(LibraryError, match="nearly"):
        match_license_parts({"parts/head_*.png": 1}, ["parts/head_1.png", *paths])
    with pytest.raises(LibraryError, match="disjoint"):
        match_license_parts({"parts/*.svg": 1, "parts/stand.*": 2}, paths)


def test_a_part_label_needs_an_asset_label_and_its_own_bytes():
    lib = _memory()
    with pytest.raises(LibraryError, match="asset-level"):
        publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, license_parts=HEADS_PRIVATE)
    with pytest.raises(LibraryError, match="other bytes"):
        publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
                file_sources={"parts/collar.svg": {**CC0, "sha256": _sha(HEAD)}})


# --------------------------------------------------------------------------- project side


def test_a_check_out_carries_each_per_file_statement_into_the_credits(tmp_path: Path):
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    project = tmp_path / "proj"
    init_project(project)
    checkout(lib, project, "cutan:prop.stu@v001")
    report = credits_for_project(project)
    per_file = {
        e.asset.split("/via-library/", 1)[-1]: (e.license_class, e.source.provider)
        for e in report.entries
        if "file:" in e.asset
    }
    assert per_file == {
        "file:parts/head_1.png": ("private", "a-film"),
        "file:parts/head_2.png": ("private", "a-film"),
    }
    assert not report.publishable


def test_the_cli_takes_repeatable_license_parts(tmp_path: Path):
    folder = tmp_path / "stu"
    for rel, data in {**STU_FILES, "prop.json": json.dumps({"name": "stu"}).encode()}.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    root = tmp_path / "lib"
    app = build_app()
    base = ["library", "publish", str(folder), "prop.stu", "--package", "cutan",
            "--root", str(root), "--license", "cc0-1.0", "--provider", "an-tests"]
    # A part whose class differs from the asset's names its own provider.
    out = runner.invoke(app, [*base, "--license-part",
                              "parts/head_*.png=all-rights-reserved-private-study"])
    assert out.exit_code != 0 and "provider=" in out.output
    out = runner.invoke(app, [*base, "--license-part",
                              "parts/head_*.png=all-rights-reserved-private-study,provider=a-film"])
    assert out.exit_code == 0, out.output
    lib = open_library("cutan", root)
    v = read_version(lib, "prop.stu", "v001")
    assert v[FILE_SOURCES_FIELD]["parts/head_1.png"]["provider"] == "a-film"
    assert _floor(lib, COLLAR) == {"cutan:prop.stu": "free"}


# --------------------------------------------------------------------------- review round


def test_r1_a_relicence_that_did_not_hold_the_bytes_frees_nothing():
    lib = _memory()
    files = {"parts/head_1.png": HEAD, "parts/collar.svg": COLLAR}
    publish(lib, "prop.stu", {"name": "stu"}, files, source=CC0,
            license_parts={"parts/head_1.png": PRIVATE})
    publish(lib, "prop.stu", {"name": "stu"}, {"parts/collar.svg": COLLAR},
            source=CC0, relicense=RELICENSE)
    with pytest.raises(RightsRefusal):
        publish(lib, "prop.stu", {"name": "stu"}, files, source=CC0,
                license_parts={"parts/head_1.png": CC0})
    r = publish(lib, "prop.stu", {"name": "stu"}, files, source=CC0)
    assert r.rights.license_class == "private"
    assert _floor(lib, HEAD) == {"cutan:prop.stu": "private"}
    assert publish(lib, "prop.thief", {"name": "t"}, {"h.png": HEAD},
                   source=CC0).rights.license_class == "private"


def test_r2_a_relicence_does_not_cover_a_private_head_moved_to_another_path():
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"},
            {"parts/head_1.png": HEAD, "parts/collar.svg": COLLAR}, source=CC0,
            license_parts={"parts/head_1.png": PRIVATE})
    moved = {"heads/h1.png": HEAD, "parts/collar.svg": COLLAR}
    with pytest.raises(RightsRefusal, match="names"):
        publish(lib, "prop.stu", {"name": "stu"}, moved, source=CC0,
                relicense=RELICENSE)
    # Named, it keeps binding; the relicence frees the collar only.
    r = publish(lib, "prop.stu", {"name": "stu"}, moved, source=CC0,
                relicense=RELICENSE, license_parts={"heads/h1.png": PRIVATE})
    assert r.rights.license_class == "private"
    assert _floor(lib, HEAD) == {"cutan:prop.stu": "private"}
    assert _floor(lib, COLLAR) == {"cutan:prop.stu": "free"}


def test_r3_a_relicensed_derivative_of_per_file_parts_is_under_the_rule():
    lib = _memory()
    publish(lib, "prop.stu", {"name": "stu"}, STU_FILES, source=CC0,
            license_parts=HEADS_PRIVATE)
    with pytest.raises(RightsRefusal):
        publish(lib, "prop.stu-hat", {"name": "hat"}, STU_FILES, source=CC0,
                derived_from=["cutan:prop.stu@v001"], relicense=RELICENSE)
    # Under the rule through its lineage alone, it is written at the schema an
    # older reader refuses.
    publish(lib, "prop.stu-cap", {"name": "cap"}, {"c.svg": COLLAR}, source=CC0,
            derived_from=["cutan:prop.stu@v001"])
    assert read_version(lib, "prop.stu-cap", "v001")["schema_version"] == PER_FILE_SCHEMA_VERSION


def test_m1_what_is_said_about_two_identical_versions_is_kept_apart():
    """Two assets' identical versions share a manifest: the answer must not
    depend on the order of derived_from."""
    for parents in (["cutan:prop.a@v001", "cutan:prop.b@v001"],
                    ["cutan:prop.b@v001", "cutan:prop.a@v001"]):
        lib = _memory()
        publish(lib, "prop.a", {"name": "same"}, {"n.png": HEAD})
        publish(lib, "prop.b", {"name": "same"}, {"n.png": HEAD})
        publish(lib, "prop.a", {"name": "same"}, {"n.png": HEAD}, source=CC0,
                relabel={"by": "t", "reason": "drawn by me"})
        with pytest.raises(RightsRefusal):
            publish(lib, "prop.c", {"name": "c"}, {"n.png": HEAD}, source=CC0,
                    derived_from=parents, license_parts={"n.png": CC0})


def test_s2_an_unreadable_parent_stands_in_as_recorded():
    """A parent written by a newer ``an`` (a schema this one cannot read) no
    longer crashes reindex or the next publish of a version without per-file
    statements."""
    versions: dict = {}
    lib = open_library("cutan", records={}, versions=versions, blobs={})
    publish(lib, "prop.lamp", {"name": "lamp"}, {"a.svg": COLLAR}, source=CC0)
    publish(lib, "prop.lamp-red", {"name": "red"}, {"a.svg": COLLAR}, source=CC0,
            derived_from=["cutan:prop.lamp@v001"])
    key = "prop.lamp@v001"
    versions[key] = {**versions[key], "schema_version": "9.0.0"}
    reindex(lib)
    r = publish(lib, "prop.lamp-red", {"name": "red"}, {"a.svg": COLLAR, "b.svg": STRAY},
                source=CC0)
    assert r.created
