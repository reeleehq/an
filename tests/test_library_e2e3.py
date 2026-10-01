"""The third end-user test's library and credits findings (an#307).

- Two assets that once shared an unlabelled file (byte-identical tool output)
  no longer block each other's labels once the file is gone; while both still
  hold it, the refusal names what works (finding 7).
- Relabelling unchanged content records the label on the existing version
  instead of minting one (finding 8).
- An asset id can be retired: recorded, hidden from ``find``, never deleted.
- ``vocabulary`` and ``find`` agree on rights (finding 1).
- ``find --near``'s style near miss is offered only where a real mechanism
  reaches it (finding 2).
- The root registry's first-publish warning tells a new registry from a lost
  one, and rebuilds what it can (finding 5).
- Synthesized speech counts as verified under the provider's terms (finding 14).

Temporary roots only (the root ``conftest.py`` redirects the machine registry
and fails a run that writes the real data folder).
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.characters.factory import new_character
from an.credits import speech_credits
from an.library import (
    LibraryError,
    find,
    open_library,
    publish,
    publish_dir,
    vocabulary,
)
from an.library import api as library_api
from an.library import registry
from an.library.registry import RegistryWarning

PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
LABEL = {"by": "tests", "reason": "the tool output is gone; the rest is the factory's"}
#: Byte-identical tool output written into two character folders (an#272's
#: silhouettes were byte-identical for different characters).
SILHOUETTE = b"\x89PNG the same silhouette for everyone"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


def _memory(name: str = "cutan"):
    return open_library(name, records={}, versions={}, blobs={})


def _character(tmp_path: Path, name: str) -> Path:
    return new_character(tmp_path / f"art-{name}", name=name, use_dicebear=False).parent


def _with_tool_output(lib, tmp_path: Path, name: str) -> Path:
    """A fresh factory character published with a tool's output in its folder."""
    char = _character(tmp_path, name)
    (char / "silhouette.png").write_bytes(SILHOUETTE)
    v1 = publish_dir(lib, char, f"character.{name}")
    assert v1.rights.license_class == "unknown"
    return char


# ============================================================ finding 7


def test_two_assets_that_shared_a_removed_file_can_each_be_labelled(tmp_path):
    """The e2e: the silhouettes are removed, then each relabel must answer."""
    lib = _memory()
    alice = _with_tool_output(lib, tmp_path, "alice")
    bob = _with_tool_output(lib, tmp_path, "bob")
    for char, name in ((alice, "alice"), (bob, "bob")):
        (char / "silhouette.png").unlink()
        v2 = publish_dir(lib, char, f"character.{name}")
        assert v2.rights.license_class == "unknown"  # it inherits v001's gap
    for char, name in ((alice, "alice"), (bob, "bob")):
        r = publish_dir(lib, char, f"character.{name}", source=CC0, relabel=LABEL)
        assert (str(r.ref), r.created, r.rights.license_class) == (
            f"cutan:character.{name}@v002", False, "free"
        ), r.rights.reasons
    # the bytes themselves stay unknown wherever they are held
    again = publish(lib, "prop.sil", {"name": "s"}, {"s.png": SILHOUETTE}, source=CC0)
    assert again.rights.license_class == "unknown"


def test_a_removed_file_another_asset_calls_private_still_binds(tmp_path):
    """Only another asset's SILENCE is answered: a private statement never is."""
    lib = _memory()
    publish(lib, "prop.still", {"name": "film still"}, {"s.png": SILHOUETTE}, source=PRIVATE)
    alice = _character(tmp_path, "alice")
    (alice / "silhouette.png").write_bytes(SILHOUETTE)
    assert publish_dir(lib, alice, "character.alice").rights.license_class == "private"
    (alice / "silhouette.png").unlink()
    r = publish_dir(lib, alice, "character.alice", source=CC0, relabel=LABEL)
    assert r.rights.license_class == "private"


def test_a_relabel_still_never_speaks_for_another_assets_file(tmp_path):
    """Both still hold the file: the relabel answers neither, and the advice says
    what works — label the other asset, then repeat this relabel."""
    lib = _memory()
    alice = _with_tool_output(lib, tmp_path, "alice")
    bob = _with_tool_output(lib, tmp_path, "bob")
    first = publish_dir(lib, alice, "character.alice", source=CC0, relabel=LABEL)
    assert first.rights.license_class == "unknown"
    advice = " ".join(first.advice)
    assert "cutan:character.bob@v001" in advice and "relabel that asset" in advice
    assert "--relabel-by" not in advice  # never the advice that just failed
    assert publish_dir(lib, bob, "character.bob", source=CC0, relabel=LABEL).rights.license_class == "free"
    again = publish_dir(lib, alice, "character.alice", source=CC0, relabel=LABEL)
    assert (again.created, again.rights.license_class) == (False, "free")
    head = library_api.read_version(lib, "character.alice", "v001")
    assert len(library_api.version_labels(lib, head)) == 2  # append-only: both outcomes


def test_dropping_the_shared_file_after_a_blocked_label_then_answers(tmp_path):
    """The advice's other way out: a label recorded while the file was still
    shared stays, and a later relabel of the version without the file answers
    the other asset's silence through it."""
    lib = _memory()
    alice = _with_tool_output(lib, tmp_path, "alice")
    _with_tool_output(lib, tmp_path, "bob")
    blocked = publish_dir(lib, alice, "character.alice", source=CC0, relabel=LABEL)
    assert blocked.rights.license_class == "unknown"  # recorded on v001
    (alice / "silhouette.png").unlink()
    r = publish_dir(lib, alice, "character.alice", source=CC0, relabel=LABEL)
    assert (str(r.ref), r.created, r.rights.license_class) == (
        "cutan:character.alice@v002", True, "free"
    ), r.rights.reasons
    # and a plain publish after it keeps it, with no new version
    again = publish_dir(lib, alice, "character.alice")
    assert (again.created, again.rights.license_class) == (False, "free")


def test_the_cli_prints_the_advice_that_fits(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "cli-cutan"))
    lib = open_library("cutan")
    _with_tool_output(lib, tmp_path, "bob")
    alice = _character(tmp_path, "alice")
    (alice / "silhouette.png").write_bytes(SILHOUETTE)
    app = build_app()
    args = ["library", "publish", str(alice), "character.alice", "--package", "cutan"]
    out = runner.invoke(app, args)
    assert out.exit_code == 0, out.output
    labelled = runner.invoke(
        app,
        [*args, "--license", "cc0-1.0", "--provider", "me",
         "--relabel-by", "me", "--relabel-reason", "mine"],
    )
    assert labelled.exit_code == 0, labelled.output
    assert "unchanged" in labelled.output and "cutan:character.bob@v001" in labelled.output
    assert "To label what this asset's own versions never labelled" not in labelled.output


def test_a_derived_from_gap_names_the_parent(tmp_path):
    lib = _memory()
    publish(lib, "prop.vase", {"name": "vase"}, {"v.svg": b"<svg>vase</svg>"})
    red = publish(
        lib, "prop.vase-red", {"name": "red"}, {"r.svg": b"<svg>red</svg>"},
        source=CC0, derived_from=["prop.vase@v001"],
    )
    assert red.rights.license_class == "unknown"
    assert any("relabel cutan:prop.vase@v001 itself" in a for a in red.advice), red.advice


# ============================================================ finding 8


def test_relabelling_unchanged_files_mints_no_version_and_checks_out_labelled(tmp_path):
    from an.credits import collect_credits
    from an.library import checkout
    from an.project import init as init_project
    from an.stores import build_project_mall

    lib = _memory()
    char = _character(tmp_path, "alice")
    (char / "parts" / "scarf.svg").write_bytes(b"<svg>a scarf I drew</svg>")  # hand-added
    assert publish_dir(lib, char, "character.alice").rights.license_class == "unknown"
    r = publish_dir(lib, char, "character.alice", source=CC0, relabel=LABEL)
    assert (str(r.ref), r.created) == ("cutan:character.alice@v001", False)
    assert library_api.show(lib, "character.alice")["rights"]["license_class"] == "free"
    # a check-out carries the label, as a relabel version's would have
    project = init_project(tmp_path / "proj")
    checkout(lib, project, "character.alice@v001")
    report = collect_credits(build_project_mall(project))
    assert report.unverified == [] and report.private == []
    # ...and an unedited re-publish of the copy makes nothing new
    again = publish_dir(lib, project / "assets" / "characters" / "alice", "character.alice")
    assert (again.created, again.rights.license_class) == (False, "free")
    # a label never rewrites the version
    v1 = library_api.read_version(lib, "character.alice", "v001")
    assert library_api.version_manifest(v1) == v1["manifest_sha256"]


def test_a_labelled_version_promotes_with_its_label(tmp_path):
    cutan, core = _memory("cutan"), _memory("an")
    char = _character(tmp_path, "alice")
    (char / "parts" / "scarf.svg").write_bytes(b"<svg>a scarf I drew</svg>")
    publish_dir(cutan, char, "character.alice")
    publish_dir(cutan, char, "character.alice", source=CC0, relabel=LABEL)
    promoted = library_api.promote([cutan, core], "cutan:character.alice@v001", to=core)
    assert promoted.rights.license_class == "free", promoted.rights.reasons
    assert library_api.read_version(core, "character.alice", "v001")["source"] == CC0


def test_a_label_counts_only_for_the_version_it_was_made_on(tmp_path):
    """A label pins its version's manifest: written for other content (a
    same-named library's other ``x@v002``) it says nothing here."""
    lib = _memory()
    char = _with_tool_output(lib, tmp_path, "alice")
    (char / "silhouette.png").unlink()
    publish_dir(lib, char, "character.alice")
    v2 = library_api.read_version(lib, "character.alice", "v002")
    said = {
        "manifest": "0" * 64,
        "source": CC0,
        "relabel": LABEL,
        "rights": {"license_class": "free", "publishable": True, "reasons": []},
    }
    key = f"character.alice@v002/{library_api._label_id(said)}"
    lib.labels[key] = {"kind": "LibraryLabel", "schema_version": "0.1.0", **said,
                       "asset": "character.alice", "version": "v002"}
    assert library_api.version_labels(lib, v2) == []
    assert library_api.effective_rights(lib, v2, owner=lib).license_class == "unknown"


def test_labels_survive_on_disk_and_reindex(tmp_path):
    lib = open_library("cutan", root=tmp_path / "disk")
    char = _with_tool_output(lib, tmp_path, "alice")
    (char / "silhouette.png").unlink()
    publish_dir(lib, char, "character.alice")
    publish_dir(lib, char, "character.alice", source=CC0, relabel=LABEL)
    files = list((tmp_path / "disk" / "library" / "labels").rglob("*.json"))
    assert len(files) == 1 and files[0].parent.name == "v002"
    reopened = open_library("cutan", root=tmp_path / "disk")
    library_api.reindex(reopened)
    hit = find(reopened, kind="character")
    assert [(h.asset_id, h.license_class) for h in hit] == [("character.alice", "free")]
    with pytest.raises(Exception):
        del reopened.labels[next(iter(reopened.labels))]  # append-only


# ============================================================ retire


def test_a_retired_id_is_hidden_never_deleted(tmp_path):
    lib = _memory()
    publish(lib, "prop.lamp", {"name": "lamp"}, source=CC0)
    publish(lib, "prop.dead", {"name": "dead"})
    library_api.retire(lib, "prop.dead", by="tests", reason="superseded by prop.lamp")
    assert [h.asset_id for h in find(lib, kind="prop")] == ["prop.lamp"]
    assert [h.asset_id for h in find(lib, kind="prop", status="retired")] == ["prop.dead"]
    record = library_api.show(lib, "prop.dead@v001")["record"]
    assert record["status"] == "retired"
    assert record["status_history"][-1]["by"] == "tests"
    assert library_api.versions_of(lib, "prop.dead") == ["v001"]  # still readable
    v = library_api.vocabulary(lib)
    assert v["facets"]["kind"] == {"prop": 1} and v["hidden"] == {"retired": 1}
    # publishing into a retired id is refused, unless the publish revives it
    with pytest.raises(LibraryError, match="retired"):
        publish(lib, "prop.dead", {"name": "dead again"})
    revived = publish(lib, "prop.dead", {"name": "dead again"}, status="draft")
    assert revived.created
    assert library_api.show(lib, "prop.dead")["record"]["status"] == "draft"


def test_the_cli_retires(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "cli-cutan"))
    publish(open_library("cutan"), "prop.dead", {"name": "dead"})
    out = runner.invoke(
        build_app(),
        ["library", "retire", "cutan:prop.dead", "--by", "me", "--reason", "dead id"],
    )
    assert out.exit_code == 0, out.output
    assert "retired" in out.output
    found = runner.invoke(build_app(), ["library", "find", "--package", "cutan"])
    assert "prop.dead" not in found.output
    shown = runner.invoke(build_app(), ["library", "find", "--package", "cutan", "--status", "retired"])
    assert "prop.dead" in shown.output


# ============================================================ finding 1


def test_vocabulary_and_find_agree_on_rights(tmp_path):
    """A version stored ``free`` whose bytes another asset later calls unknown:
    find recomputes it, and so must vocabulary."""
    lib = _memory()
    publish(lib, "prop.a", {"name": "a"}, {"x.png": SILHOUETTE}, source=CC0)
    publish(lib, "prop.b", {"name": "b"}, {"x.png": SILHOUETTE})  # silent about the same bytes
    stored = library_api.read_version(lib, "prop.a", "v001")["rights"]["license_class"]
    assert stored == "free"
    found = {h.asset_id: h.license_class for h in find(lib)}
    counts = vocabulary(lib)["facets"]["license_class"]
    assert found == {"prop.a": "unknown", "prop.b": "unknown"}
    assert counts == {"unknown": 2}


# ============================================================ finding 2


def test_a_style_near_miss_is_offered_only_where_a_style_pack_reaches(tmp_path):
    lib = _memory()
    char = _character(tmp_path, "amy")  # a factory character: role-tagged colours
    publish_dir(lib, char, "character.amy", style="reiniger")
    publish(lib, "character.cut", {"kind": "CharacterDescriptor", "name": "cut"}, style="reiniger")
    publish(lib, "prop.lamp", {"name": "lamp"}, style="reiniger")
    near = find(lib, style="south_park", near=True)
    assert [h.asset_id for h in near.near] == ["character.amy"]
    remedy = near.near[0].remedies["style:south_park"]
    assert "style_pack" in remedy and "an character new" in remedy
    assert "build" in remedy  # a recolour never changes a build


# ============================================================ finding 5


def test_a_new_registry_says_so_calmly(tmp_path):
    assert not registry.machine_registry_dir().exists()
    with pytest.warns(RegistryWarning, match="first library write") as caught:
        publish(open_library("cutan", root=tmp_path / "lib"), "prop.a", {"name": "a"}, source=CC0)
    assert not any("is gone" in str(w.message) for w in caught)


def test_a_lost_registry_is_rebuilt_and_says_what_it_could_not_recover(tmp_path):
    cutan = open_library("cutan")
    publish(cutan, "prop.chair", {"name": "chair"}, {"c.png": SILHOUETTE}, source=PRIVATE)
    shutil.rmtree(registry.machine_registry_dir())  # the pollution clean-up
    with pytest.warns(RegistryWarning) as caught:
        publish(cutan, "prop.lamp", {"name": "lamp"}, source=CC0)
    text = " ".join(str(w.message) for w in caught)
    assert "1 asset" in text and "rebuilt" in text and "is gone" not in text
    # the statements the discoverable libraries hold are remembered again
    assert any(
        st.get("class") == "private"
        for _, st in registry.remembered_statements(
            library_api.content_hash(SILHOUETTE)
        )
    )


# ============================================================ finding 14


def _speech(declared: dict | None, provider: str = "elevenlabs"):
    line = NS(voice_ref="bob", speaker="bob", audio_ref="k1")
    scene = NS(timeline=[NS(dialogue=[line], entities=[])])
    doc = {"provider": provider, "voice_id": "TX3", "model_id": "eleven_v3"}
    if declared is not None:
        doc["source"] = declared
    (entry,) = speech_credits({"voices": {"bob": doc}}, scene)
    return entry


@pytest.mark.parametrize(
    "license, cls",
    [
        ("elevenlabs-paid-plan", "free"),
        ("elevenlabs-paid-plan-commercial", "free"),  # the e2e's own spelling
        ("elevenlabs-free-plan", "attribution"),
        ("elevenlabs-whatever", "unknown"),
    ],
)
def test_speech_under_the_providers_terms_counts(license, cls):
    entry = _speech({"provider": "elevenlabs", "license": license})
    assert entry.license_class == cls


def test_another_providers_terms_do_not_count():
    entry = _speech({"provider": "elevenlabs", "license": "elevenlabs-paid-plan"}, provider="openai")
    assert entry.license_class == "unknown"
