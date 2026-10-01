"""The second end-user test's library findings (an#271), and two conservative rights gaps (an#281).

- an#271: a style mismatch is offered as a near miss; checking out a
  just-published project asset links it under its own key; ``an credits`` is
  consistent, lists an environment's plates and synthesized speech; ``an
  library show`` counts the descriptor file.
- an#281: an explicit asset-level source stands in for a generator's
  descriptor source (DiceBear's, like the factory's); a changed file that a
  source pinned to its new bytes labels is not ``unlabelled`` under a carried
  label.

Temporary roots only (the root ``conftest.py`` redirects the machine registry
and fails a run that writes the real data folder).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.characters.factory import new_character
from an.credits import collect_credits, credits_for_scene, speech_credits
from an.library import checkout, find, open_library, publish, publish_dir
from an.library.lock import ProjectLock
from an.project import init as init_project
from an.stores import build_project_mall

CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
CARVED = b"<svg>a torso nobody has seen</svg>"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


@pytest.fixture
def project(tmp_path) -> Path:
    return init_project(tmp_path / "proj")


def _environment(project: Path, key: str, *, source: dict | None = None) -> Path:
    folder = project / "assets" / "environments" / key
    (folder / "plates").mkdir(parents=True)
    (folder / "plates" / "hills.svg").write_text("<svg>hills</svg>", encoding="utf-8")
    (folder / "plates" / "reeds.svg").write_text("<svg>reeds</svg>", encoding="utf-8")
    doc = {
        "kind": "EnvironmentDescriptor",
        "name": key,
        "planes": [
            {"name": "sky", "art": {"kind": "fill", "color": "#ffe9b0"}},
            {"name": "hills", "art": {"kind": "image", "src": "plates/hills.svg"}},
            {"name": "reeds", "art": {"kind": "image", "src": "plates/reeds.svg"}},
        ],
    }
    if source:
        doc["source"] = source
    (folder / "meta.json").write_text(json.dumps(doc), encoding="utf-8")
    return folder


# ============================================================ finding 2


def test_a_style_mismatch_is_a_near_miss_with_a_restyle_remedy():
    lib = open_library("cutan", records={}, versions={}, blobs={})
    publish(lib, "prop.lamp", {"name": "lamp"}, style="oversimplified")
    publish(lib, "prop.vase", {"name": "vase"}, style="reiniger")
    plain = find(lib, kind="prop", style="reiniger")
    assert [h.asset_id for h in plain] == ["prop.vase"] and plain.near == []
    near = find(lib, kind="prop", style="reiniger", near=True)
    assert [h.asset_id for h in near] == ["prop.vase"]
    (miss,) = near.near
    assert (miss.asset_id, miss.missing) == ("prop.lamp", ["style:reiniger"])
    assert "restyle" in miss.remedies["style:reiniger"]
    assert "oversimplified" in miss.remedies["style:reiniger"]
    # another facet failing too is not a near miss
    assert find(lib, kind="character", style="reiniger", near=True).near == []


# ============================================================ finding 5


def test_checking_out_a_just_published_character_links_the_original(project):
    folder = new_character(project / "assets" / "characters", name="alice", use_dicebear=False).parent
    lib = open_library("cutan")
    publish_dir(lib, folder, "character.alice-reiniger")
    result = checkout(lib, project, "cutan:character.alice-reiniger@v001")
    assert result.key == "alice" and not (folder.parent / "alice-reiniger").exists()
    assert ProjectLock(project)["characters/alice"]["library"] == "cutan:character.alice-reiniger@v001"


def test_checking_out_a_just_published_environment_links_the_original(project):
    folder = _environment(project, "glass_table", source=CC0)
    lib = open_library("cutan")
    publish_dir(lib, folder, "environment.glass-table-reiniger")
    result = checkout(lib, project, "cutan:environment.glass-table-reiniger@v001")
    assert result.key == "glass_table"
    assert not (folder.parent / "glass-table-reiniger").exists()
    assert "environments/glass_table" in ProjectLock(project)


def test_an_edited_original_is_not_linked_the_copy_lands_beside_it(project):
    folder = new_character(project / "assets" / "characters", name="alice", use_dicebear=False).parent
    lib = open_library("cutan")
    publish_dir(lib, folder, "character.alice-reiniger")
    (folder / "parts" / "head.svg").write_text("<svg>edited</svg>", encoding="utf-8")
    result = checkout(lib, project, "cutan:character.alice-reiniger@v001")
    assert result.key == "alice-reiniger"


def test_a_copy_pinned_to_another_version_is_never_taken_over(project):
    folder = new_character(project / "assets" / "characters", name="alice", use_dicebear=False).parent
    lib = open_library("cutan")
    publish_dir(lib, folder, "character.alice-a")
    assert checkout(lib, project, "cutan:character.alice-a@v001").key == "alice"
    publish_dir(lib, folder, "character.alice-b")  # the same bytes, another asset
    assert checkout(lib, project, "cutan:character.alice-b@v001").key == "alice-b"
    assert ProjectLock(project)["characters/alice"]["library"] == "cutan:character.alice-a@v001"


# ============================================================ finding 15


def test_fresh_factory_characters_read_alike_in_credits(project):
    """Published with no flags and checked out, both are an's own work."""
    lib = open_library("cutan")
    for name in ("alice", "bob"):
        folder = new_character(project / "art", name=name, use_dicebear=False).parent
        publish_dir(lib, folder, f"character.{name}-reiniger")
        checkout(lib, project, f"cutan:character.{name}-reiniger@v001")
    report = collect_credits(build_project_mall(project))
    assert sorted(e.asset for e in report.entries if e.own_work) == [
        "characters/alice-reiniger",
        "characters/bob-reiniger",
    ]
    assert not [e for e in report.entries if not e.own_work]


def test_an_environments_plates_are_listed(project):
    _environment(project, "lit", source=CC0)
    _environment(project, "bare")
    report = collect_credits(build_project_mall(project))
    (lit,) = [e for e in report.entries if e.asset == "environments/lit"]
    assert lit.covers == ("plates/hills.svg", "plates/reeds.svg")
    assert "covers plates/hills.svg, plates/reeds.svg" in report.format()
    assert sorted(e.asset for e in report.unverified) == [
        "environments/bare/planes/hills",
        "environments/bare/planes/reeds",
    ]


def _scene(*lines):
    return NS(timeline=[NS(dialogue=list(lines), entities=[], sounds=[])], meta=NS(sounds=[]))


def test_synthesized_speech_is_listed_with_provider_voice_and_model():
    mall = {
        "voices": {
            "bob": {"provider": "elevenlabs", "voice_id": "TX3", "model_id": "eleven_v3"},
            "alice": {
                "provider": "elevenlabs", "voice_id": "pFZ", "model_id": "eleven_v3",
                "source": {"provider": "elevenlabs", "license": "cc0-1.0"},
            },
            "draft": {"provider": "offline"},
        }
    }
    said = lambda voice, ref="k": NS(voice_ref=voice, speaker=voice, audio_ref=ref)  # noqa: E731
    scene = _scene(said("bob"), said("bob"), said("alice"), said("draft"), said("bob", None))
    entries = {e.asset: e for e in speech_credits(mall, scene)}
    assert sorted(entries) == ["speech/alice", "speech/bob"]
    bob = entries["speech/bob"]
    assert (bob.license_class, bob.source.provider, bob.source.id) == ("unknown", "elevenlabs", "TX3")
    assert bob.source.extra["model"] == "eleven_v3" and bob.source.extra["lines"] == 2
    assert entries["speech/alice"].license_class == "free"
    text = credits_for_scene(mall, scene).format()
    assert "speech/bob: license=None (elevenlabs, voice TX3, model eleven_v3, 2 line(s))" in text


# ============================================================ finding 18


def test_show_counts_the_descriptor_file(project):
    folder = _environment(project, "glass_table", source=CC0)
    publish_dir(open_library("cutan"), folder, "environment.glass-table")
    r = runner.invoke(build_app(), ["library", "show", "cutan:environment.glass-table"])
    assert r.exit_code == 0, r.output
    assert "files: 3 (meta.json + 2)" in r.output


# ============================================================ an#281


def test_an_explicit_label_stands_in_for_a_generated_descriptor_source(tmp_path, project):
    """A DiceBear character with a re-carved torso: `--license` covers it, as
    it does under the factory's own stamp; DiceBear still credits its head."""
    from an.characters.factory import stamp_generated_head
    from an.characters.licenses import dicebear_source

    lib = open_library("cutan")
    char = new_character(tmp_path, name="dee", use_dicebear=False).parent
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    doc.pop("source", None)
    (char / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    stamp_generated_head(char, dicebear_source("lorelei", seed="dee"))
    (char / "parts" / "torso.svg").write_bytes(CARVED)
    elsewhere = open_library("cutan", records={}, versions={}, blobs={})
    assert publish_dir(elsewhere, char, "character.dee").rights.license_class == "unknown"
    labelled = publish_dir(lib, char, "character.dee", source=CC0)
    assert labelled.rights.license_class in ("free", "attribution"), labelled.rights.reasons
    checkout(lib, project, "cutan:character.dee@v001")
    assert not collect_credits(build_project_mall(project)).unverified


def test_a_generated_source_that_owes_attribution_never_gives_way(tmp_path):
    """A CC BY DiceBear style keeps its descriptor source under an explicit
    label: the label cannot drop the attribution it obliges."""
    from an.characters.factory import stamp_generated_head
    from an.characters.licenses import dicebear_source

    lib = open_library("cutan", records={}, versions={}, blobs={})
    char = new_character(tmp_path, name="ada", use_dicebear=False).parent
    doc = json.loads((char / "character.json").read_text(encoding="utf-8"))
    doc.pop("source", None)
    (char / "character.json").write_text(json.dumps(doc), encoding="utf-8")
    stamp_generated_head(char, dicebear_source("adventurer", seed="ada"))
    assert publish_dir(lib, char, "character.ada", source=CC0).rights.license_class == "attribution"
    (char / "parts" / "torso.svg").write_bytes(CARVED)
    assert publish_dir(lib, char, "character.ada-carved", source=CC0).rights.license_class == "unknown"


def test_parts_a_generator_restamps_under_a_carried_label_are_labelled(tmp_path, project):
    """A version labelled cc0 explicitly; `an character mouths` then redraws
    and re-stamps the mouths. The carried label does not cover them, but their
    own stamps do: not `unlabelled`, in the library and in `an credits`."""
    from an.characters.cli import mouths

    lib = open_library("cutan")
    char = new_character(project / "assets" / "characters", name="amy", use_dicebear=False).parent
    publish_dir(lib, char, "character.amy", source=CC0)
    checkout(lib, project, "cutan:character.amy@v001")
    mouths("amy", out_dir=str(char.parent), palette='{"lip": "#aa3355"}')
    assert collect_credits(build_project_mall(project)).unverified == []
    v2 = publish_dir(lib, char, "character.amy")
    assert v2.rights.license_class == "free", v2.rights.reasons
    # a file changed with no stamp of its own is still unlabelled
    (char / "parts" / "torso.svg").write_bytes(CARVED)
    assert [e.asset for e in collect_credits(build_project_mall(project)).unverified] == [
        "characters/amy/parts/torso.svg"
    ]
    assert publish_dir(lib, char, "character.amy").rights.license_class == "unknown"


# ============================================================ review-288


def _set_part(char: Path, path: str, *, source=None, new_path: str | None = None) -> None:
    doc_path = char / "character.json"
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    for skin in doc["skins"].values():
        for slot in skin["slots"].values():
            for att in slot.values():
                if att["path"] == path:
                    if new_path is not None:
                        att["path"] = new_path
                    if source is None:
                        att.pop("source", None)
                    else:
                        att["source"] = source
    doc_path.write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize("how", ["hand-forged", "stamp_factory_parts"])
def test_a_factory_stamp_the_record_does_not_confirm_labels_nothing(tmp_path, project, how):
    """B1 (A1d / A1e): under a carried label, a carved head under a factory
    stamp — typed by hand, or written by the public stamping function — is
    `unknown`, and UNVERIFIED in a check-out's credits."""
    from an.characters.factory import FACTORY_LICENSE, FACTORY_PROVIDER, stamp_factory_parts
    from an.library import api as library_api

    lib = open_library("cutan")
    char = new_character(project / "assets" / "characters", name="amy", use_dicebear=False).parent
    publish_dir(lib, char, "character.amy", source=CC0)
    checkout(lib, project, "cutan:character.amy@v001")
    carved = b"<svg>a head nobody has seen</svg>"
    (char / "parts" / "head.svg").write_bytes(carved)
    if how == "hand-forged":
        _set_part(char, "parts/head.svg", source={
            "provider": FACTORY_PROVIDER, "license": FACTORY_LICENSE,
            "sha256": library_api.content_hash(carved),
        })
    else:
        stamp_factory_parts(char, {"parts/head.svg"})
    unverified = [e.asset for e in collect_credits(build_project_mall(project)).unverified]
    assert unverified == ["characters/amy/parts/head.svg"]
    assert publish_dir(lib, char, "character.amy").rights.license_class == "unknown"


def test_a_fresh_publish_under_a_forged_factory_stamp_is_unknown(tmp_path):
    """V1 (pre-existing on main): no carry, a carved head under a hand-forged
    factory stamp is not the factory's work."""
    from an.characters.factory import FACTORY_LICENSE, FACTORY_PROVIDER
    from an.library import api as library_api

    lib = open_library("cutan", records={}, versions={}, blobs={})
    char = new_character(tmp_path, name="vee", use_dicebear=False).parent
    carved = b"<svg>another unseen head</svg>"
    (char / "parts" / "head.svg").write_bytes(carved)
    _set_part(char, "parts/head.svg", source={
        "provider": FACTORY_PROVIDER, "license": FACTORY_LICENSE,
        "sha256": library_api.content_hash(carved),
    })
    r = publish_dir(lib, char, "character.vee")
    assert r.rights.license_class == "unknown"
    assert any("parts/head.svg" in reason for reason in r.rights.reasons)


def test_a_part_in_a_dot_named_file_is_credited_and_published(tmp_path, project):
    """S2: a file the descriptor names is never OS clutter, whatever its name."""
    char = new_character(project / "assets" / "characters", name="eve", use_dicebear=False).parent
    hidden = b"<svg>carved, hidden</svg>"
    (char / "parts" / ".secret.svg").write_bytes(hidden)
    _set_part(char, "parts/head.svg", new_path="parts/.secret.svg")
    (char / "parts" / "head.svg").unlink()
    unverified = [e.asset for e in collect_credits(build_project_mall(project)).unverified]
    assert "characters/eve/parts/.secret.svg" in unverified
    lib = open_library("cutan")
    r = publish_dir(lib, char, "character.eve")
    assert r.rights.license_class == "unknown"
    from an.library import api as library_api

    stored = library_api.read_version(lib, "character.eve", "v001")
    assert "parts/.secret.svg" in stored["files"]
    # OS clutter nobody names is still left out
    (char / ".DS_Store").write_bytes(b"junk")
    assert not publish_dir(lib, char, "character.eve").created
