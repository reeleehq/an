"""Rights conflicts: inform, don't block (an#357).

The maintainer's decision (2026-10-09): a later statement about some bytes —
a per-part ``Attachment.source`` or a per-file ``file_sources`` entry — that is
freer than an earlier statement about the same bytes is KEPT, never discarded;
the stricter one binds; the library records a rights conflict naming both,
and shows it in ``an credits``, ``an library show``, ``an library sheet`` and
``an validate`` as a warning. Nothing refuses because of a conflict unless the
user opts in (``strict_assets``); a relicence resolves one deliberately.

The probe scenarios T1-T5 (the red-team probe of the an#331 design, which
relaxed the floor through per-part sources) are replayed here in their
per-part form; ``tests/test_library_file_sources.py`` holds their per-file form.

In-memory libraries; the root ``conftest.py`` points the machine registry into
a temporary folder.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.credits import credits_for_project
from an.library import checkout, open_library, publish
from an.library.api import (
    CONFLICTS_KEY,
    RightsConflictWarning,
    read_version,
    reindex,
    reindex_changes,
    show,
    version_conflicts,
)
from an.library.rights import RightsRefusal
from an.orchestrate import _rights_conflict_findings
from an.project import init as init_project
from an.project import load
from an.ir.validate import ValidationReport

PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
CARVED = b"\x89PNG carved from a film"
RECARVED = b"\x89PNG re-carved from the private lamp"
DRAWN = b"<svg>drawn by hand</svg>"
RELICENSE = {"by": "tests", "reason": "the stand is drawn"}
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
    return {k: v["class"] for k, v in (lib.blob_rights.get(_sha(data)) or {}).items()}


def _att(path: str, src: dict, data: bytes) -> dict:
    """A descriptor whose one attachment at ``path`` carries ``src`` pinned to ``data``."""
    pinned = {**src, "sha256": _sha(data)}
    return {"skins": {"default": {"slots": {"s": {"a": {"path": path, "source": pinned}}}}}}


def _conflicted(lib, *args, **kw):
    """Refused under ``strict_assets``; recorded with a warning otherwise."""
    with pytest.raises(RightsRefusal, match="strict-assets"):
        publish(lib, *args, strict_assets=True, **kw)
    with pytest.warns(RightsConflictWarning):
        result = publish(lib, *args, **kw)
    assert result.created and result.conflicts
    return result


# --------------------------------------------------------------------------- the probe, per part


def _t1(lib):
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": CARVED}, source=PRIVATE)
    return _conflicted(
        lib, "prop.lamp", {"name": "lamp", **_att("parts/lamp.png", CC0, CARVED)},
        {"parts/lamp.png": CARVED},
    ), CARVED


def _t2(lib):
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": CARVED}, source=PRIVATE)
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/other.png": b"x"}, source=PRIVATE)
    return _conflicted(
        lib, "prop.lamp", {"name": "lamp", **_att("parts/lamp.png", CC0, CARVED)},
        {"parts/lamp.png": CARVED}, source=PRIVATE,
    ), CARVED


def _t3(lib):
    doc = {"name": "x", "skins": {"default": {"slots": {
        "a": {"a": {"path": "parts/a_head.png", "source": {**PRIVATE, "sha256": _sha(CARVED)}}},
        "b": {"b": {"path": "spare/z_copy.png", "source": {**CC0, "sha256": _sha(CARVED)}}},
    }}}}
    return _conflicted(
        lib, "prop.lamp", doc, {"parts/a_head.png": CARVED, "spare/z_copy.png": CARVED},
        source=CC0,
    ), CARVED


def _t4(lib):
    publish(lib, "prop.base", {"name": "base"}, {"parts/lamp.png": CARVED}, source=PRIVATE)
    return _conflicted(
        lib, "prop.lamp", {"name": "red", **_att("parts/lamp.png", CC0, RECARVED)},
        {"parts/lamp.png": RECARVED}, source=CC0, derived_from=["cutan:prop.base@v001"],
    ), RECARVED


@pytest.mark.parametrize("scenario", [_t1, _t2, _t3, _t4], ids=["T1", "T2", "T3", "T4"])
def test_a_per_part_source_never_relaxes_the_floor_and_is_kept(scenario):
    lib = _memory()
    result, data = scenario(lib)
    # The stricter binds: in the version, in the floor, and for any other asset.
    assert result.rights.license_class == "private"
    assert _floor(lib, data) == {"cutan:prop.lamp": "private"}
    copy = publish(lib, "prop.stool", {"name": "stool"}, {"s.png": data}, source=CC0)
    assert copy.rights.license_class == "private"
    # The freer statement is kept in the version and named in the conflict,
    # which the floor statement records beside the class.
    version = read_version(lib, "prop.lamp", result.ref.version)
    assert CC0["license"] in json.dumps(version["doc"])
    (conflict,) = result.conflicts
    assert (conflict.claimed_class, conflict.binding_class) == ("free", "private")
    stated = lib.blob_rights[_sha(data)]["cutan:prop.lamp"]
    assert stated[CONFLICTS_KEY] == [conflict.to_dict()]
    # Reindexing states exactly what publish stated.
    before = {d: dict(e) for d, e in lib.blob_rights.items()}
    reindex(lib)
    assert {d: dict(e) for d, e in lib.blob_rights.items()} == before


def test_t5_a_relicence_never_frees_a_part_it_states_private():
    lib = _memory()
    files = {"parts/lamp.png": CARVED, "parts/stand.svg": DRAWN}
    publish(lib, "prop.lamp", {"name": "lamp"}, files, source=PRIVATE)
    r = publish(
        lib, "prop.lamp", {"name": "lamp", **_att("parts/lamp.png", PRIVATE, CARVED)},
        files, source=CC0, relicense=RELICENSE,
    )
    assert r.rights.license_class == "private"
    assert _floor(lib, CARVED) == {"cutan:prop.lamp": "private"}
    assert _floor(lib, DRAWN) == {"cutan:prop.lamp": "free"}  # the relicence frees the stand
    assert not r.conflicts  # the stricter statement is this version's own


def test_a_version_with_no_claim_states_what_it_always_stated():
    """No per-part or per-file statement: no conflict key, the statement as before."""
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, {"a.svg": DRAWN}, source=PRIVATE)
    r = publish(lib, "prop.lamp", {"name": "lamp"}, {"a.svg": DRAWN}, source=CC0)
    assert r.rights.license_class == "private" and not r.conflicts
    assert lib.blob_rights[_sha(DRAWN)]["cutan:prop.lamp"] == {
        "version": "v002",
        "number": 2,
        "class": "private",
        "label": "the asset's own label",
        "manifest": r.manifest_sha256,
    }


def test_a_first_statement_about_bytes_is_no_conflict():
    lib = _memory()
    r = publish(
        lib, "prop.lamp", {"name": "lamp", **_att("parts/lamp.png", CC0, CARVED)},
        {"parts/lamp.png": CARVED, "b.svg": DRAWN}, source=PRIVATE,
    )
    assert not r.conflicts
    assert _floor(lib, CARVED) == {"cutan:prop.lamp": "free"}
    assert _floor(lib, DRAWN) == {"cutan:prop.lamp": "private"}


# --------------------------------------------------------------------------- the dry run


def test_reindex_changes_lists_what_a_rebuild_would_restate_and_writes_nothing():
    lib = _memory()
    _t1(lib)
    digest = _sha(CARVED)
    # The index an older `an` wrote: v002's per-part cc0 replaced v001's private.
    stale = {**lib.blob_rights[digest]["cutan:prop.lamp"], "class": "free"}
    stale.pop(CONFLICTS_KEY)
    lib.blob_rights[digest] = {"cutan:prop.lamp": stale}
    (change,) = reindex_changes(lib)
    assert (change.asset, change.paths, change.before, change.after, change.conflicts) == (
        "cutan:prop.lamp", ("parts/lamp.png",), "free", "private", 1,
    )
    assert lib.blob_rights[digest] == {"cutan:prop.lamp": stale}  # untouched
    reindex(lib)
    assert reindex_changes(lib) == []
    assert _floor(lib, CARVED) == {"cutan:prop.lamp": "private"}


def test_the_cli_reindex_dry_run_lists_asset_keys_and_classes(tmp_path):
    lib = open_library("cutan", tmp_path / "lib")
    _t1(lib)
    digest = _sha(CARVED)
    stale = {**lib.blob_rights[digest]["cutan:prop.lamp"], "class": "free"}
    lib.blob_rights[digest] = {"cutan:prop.lamp": stale}
    base = ["library", "reindex", "--package", "cutan", "--root", str(tmp_path / "lib")]
    out = runner.invoke(build_app(), [*base, "--dry-run"])
    assert out.exit_code == 0, out.output
    assert "cutan:prop.lamp parts/lamp.png: free -> private" in out.output
    assert lib.blob_rights[digest]["cutan:prop.lamp"]["class"] == "free"
    out = runner.invoke(build_app(), base)
    assert out.exit_code == 0, out.output
    assert _floor(lib, CARVED) == {"cutan:prop.lamp": "private"}


# --------------------------------------------------------------------------- where it is shown


def test_show_and_version_conflicts_name_both_statements():
    lib = _memory()
    result, _ = _t1(lib)
    info = show(lib, str(result.ref))
    assert info["rights"]["license_class"] == "private"
    (c,) = info[CONFLICTS_KEY]
    assert c["claimed"] == "parts/lamp.png itemised as cc0-1.0"
    assert "prop.lamp@v001" in c["binding"]
    version = read_version(lib, "prop.lamp", "v002")
    assert version_conflicts(lib, version, owner=lib)[0].to_dict() == c


def test_the_cli_shows_conflicts_and_refuses_them_only_under_strict_assets(tmp_path):
    root = tmp_path / "lib"
    lib = open_library("cutan", root)
    publish(lib, "prop.lamp", {"name": "lamp"}, {"parts/lamp.png": CARVED}, source=PRIVATE)
    folder = tmp_path / "lamp"
    (folder / "parts").mkdir(parents=True)
    (folder / "parts" / "lamp.png").write_bytes(CARVED)
    (folder / "prop.json").write_text(
        json.dumps({"name": "lamp", **_att("parts/lamp.png", CC0, CARVED)}), encoding="utf-8"
    )
    app = build_app()
    base = ["library", "publish", str(folder), "prop.lamp", "--package", "cutan",
            "--root", str(root)]
    out = runner.invoke(app, [*base, "--strict-assets"])
    assert out.exit_code != 0 and "strict-assets" in out.output
    out = runner.invoke(app, base)
    assert out.exit_code == 0, out.output
    assert "1 rights conflict(s)" in out.output
    out = runner.invoke(app, ["library", "show", "cutan:prop.lamp", "--root", str(root)])
    assert out.exit_code == 0, out.output
    assert "rights: private" in out.output
    assert "rights conflicts (1;" in out.output and "itemised as cc0-1.0 (free)" in out.output


def test_a_check_out_carries_the_conflict_into_credits_and_validate(tmp_path):
    lib = _memory()
    result, _ = _t1(lib)
    project = tmp_path / "proj"
    init_project(project)
    checkout(lib, project, str(result.ref))
    report = credits_for_project(project)
    assert not report.publishable
    ((asset, conflict),) = report.conflicts
    assert asset == "props/lamp" and conflict["binding_class"] == "private"
    assert "RIGHTS CONFLICTS (1)" in report.format()
    assert report.to_dict()["rights_conflicts"][0]["asset"] == "props/lamp"
    # validate: a warning on the asset a scene uses, never an error.
    scene = SimpleNamespace(
        timeline=[SimpleNamespace(entities=[SimpleNamespace(store="props", ref="lamp")], sounds=[])],
        meta=SimpleNamespace(sounds=[]),
    )
    findings = ValidationReport()
    _rights_conflict_findings(load(project), scene, findings)
    (finding,) = findings.findings
    assert finding.severity == "warning" and finding.ir_path == "library/props/lamp"
    assert "itemised as cc0-1.0 (free)" in finding.description
    unused = SimpleNamespace(timeline=[], meta=SimpleNamespace(sounds=[]))
    findings = ValidationReport()
    _rights_conflict_findings(load(project), unused, findings)
    assert not findings.findings


# --------------------------------------------------------------------------- review round (an#357)


def test_a_relicence_does_not_launder_what_it_left_uncovered_to_a_derivative():
    """Finding 1 (critical): a relicence that moved a per-file private head
    leaves it uncovered and private; a version DERIVED from it inherits that,
    whether it holds the head or a re-carve of it."""
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, {"a.png": CARVED, "b.svg": DRAWN},
            source=CC0, license_parts={"a.png": PRIVATE})
    with pytest.warns(RightsConflictWarning):
        v2 = publish(lib, "prop.lamp", {"name": "lamp"},
                     {"moved/a.png": CARVED, "b.svg": DRAWN}, source=CC0, relicense=RELICENSE)
    assert v2.rights.license_class == "private"
    child = publish(lib, "prop.child", {"name": "child"}, {"n.svg": b"<svg>new</svg>"},
                    source=CC0, derived_from=["cutan:prop.lamp@v002"])
    assert child.rights.license_class == "private"
    for parent in ("cutan:prop.lamp@v001", "cutan:prop.lamp@v002"):
        re = publish(lib, f"prop.re{parent[-1]}", {"name": "re"}, {"lamp.png": RECARVED},
                     source=CC0, derived_from=[parent])
        assert re.rights.license_class == "private", parent
    from an.library.api import find

    assert "prop.child" not in {h.asset_id for h in find(lib, rights="publishable")}


@pytest.mark.parametrize("relabel", [True, False], ids=["relabel", "plain"])
def test_a_per_part_label_answers_silence_as_before(relabel):
    """Finding 2: an earlier version that recorded no source is silence, not a
    statement. A per-part source pinned to the bytes labels them, as it did
    before an#357 (an#281's rule); being explicit never makes it stricter."""
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, {"a.png": CARVED})
    kw = {"relabel": {"by": "me", "reason": "I drew it"}} if relabel else {}
    r = publish(lib, "prop.lamp", {"name": "lamp", **_att("a.png", CC0, CARVED)},
                {"a.png": CARVED}, source=CC0, **kw)
    assert not r.conflicts
    assert _floor(lib, CARVED) == {"cutan:prop.lamp": "free"}
    if relabel:
        assert r.rights.license_class == "free"


def test_new_bytes_in_a_later_version_are_bound_by_nothing_said_about_other_bytes():
    """Finding 3: a hat added in v002 of a private body is no earlier
    statement's bytes, so its own cc0 label stands, as it does in v001; and
    another asset holding the hat is not made private by it."""
    hat = b"<svg>a cc0 hat</svg>"
    for added_later in (False, True):
        lib = _memory()
        if added_later:
            publish(lib, "prop.b", {"name": "b"}, {"body.png": CARVED}, source=PRIVATE)
        r = publish(lib, "prop.b", {"name": "b", **_att("hat.svg", CC0, hat)},
                    {"body.png": CARVED, "hat.svg": hat}, source=PRIVATE)
        assert not r.conflicts and r.rights.license_class == "private"
        assert _floor(lib, hat) == {"cutan:prop.b": "free"}, added_later
        other = publish(lib, "prop.other", {"name": "o"}, {"h.svg": hat}, source=CC0)
        assert other.rights.license_class == "free"


def test_strict_assets_refuses_only_a_new_version_and_reaches_promote():
    """Finding 5: republishing what the head already is records nothing, so
    `--strict-assets` does not refuse it; `promote` takes it too."""
    from an.library.api import promote

    lib = _memory()
    result, _ = _t1(lib)
    again = publish(lib, "prop.lamp", {"name": "lamp", **_att("parts/lamp.png", CC0, CARVED)},
                    {"parts/lamp.png": CARVED}, strict_assets=True)
    assert not again.created
    core = _memory("an")
    with pytest.raises(RightsRefusal, match="strict-assets"):
        promote([lib], str(result.ref), to=core, allow_restricted=True, strict_assets=True)


def test_validate_and_render_under_strict_assets_refuse_a_conflict(tmp_path):
    from an.render import RenderError, _refuse_rights_conflicts

    lib = _memory()
    result, _ = _t1(lib)
    project = tmp_path / "proj"
    init_project(project)
    checkout(lib, project, str(result.ref))
    scene = SimpleNamespace(
        timeline=[SimpleNamespace(entities=[SimpleNamespace(store="props", ref="lamp")], sounds=[])],
        meta=SimpleNamespace(sounds=[]),
    )
    findings = ValidationReport()
    _rights_conflict_findings(load(project), scene, findings, strict=True)
    assert [f.severity for f in findings.findings] == ["error"]
    loaded = load(project)
    loaded.scene = scene
    with pytest.raises(RenderError, match="strict-assets"):
        _refuse_rights_conflicts(loaded)


def test_a_long_chain_publishes_in_linear_time():
    """Finding 4: one rule per publish, and a chain's own labels are not
    re-walked for every digest. 40 versions of a 30-part asset, every part
    itemised: each publish stays cheap (it was over 3 s at v040)."""
    import time

    lib = _memory()
    slowest = 0.0
    for v in range(40):
        files = {f"parts/p{i}.svg": f"<svg>{i}-{v if i == 0 else 0}</svg>".encode() for i in range(30)}
        slots = {f"s{i}": {"a": {"path": p, "source": {**CC0, "sha256": _sha(b)}}}
                 for i, (p, b) in enumerate(files.items())}
        t = time.perf_counter()
        publish(lib, "prop.x", {"name": "x", "skins": {"default": {"slots": slots}}}, files,
                source=PRIVATE if v == 0 else None)
        slowest = max(slowest, time.perf_counter() - t)
    assert slowest < 1.5, slowest
