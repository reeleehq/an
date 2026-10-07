"""A factory stamp proved away from the machine that drew it (an#292).

The character factory records its recipe (cutan: `metadata.factory`) and the
core re-derives the bytes through the genre's `credits.factory_redraw` service
when this machine's record is silent. A match is proof; a recipe can never
vouch for bytes the factory does not draw.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from an.credits import collect_credits, factory_recorded
from an.genres import service
from an.library import open_library, publish_dir
from an.library import api as library_api
from an.library import registry
from an.stores import build_project_mall

pytestmark = [
    pytest.mark.genre("cutout_animation"),
    pytest.mark.skipif(  # cutan before thorwhalen/cutan#49
        service("credits.factory_redraw") is None,
        reason="the installed genre records no factory recipe",
    ),
]


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


def _drawn_elsewhere(tmp_path: Path, monkeypatch, **knobs) -> Path:
    """A factory character drawn on "another machine": the record that saw it
    drawn is not this one's."""
    from cutan.characters.factory import new_character

    monkeypatch.setattr(registry, "_account_home", lambda: tmp_path / "machine-a")
    char = new_character(tmp_path / "art", name="amy", use_dicebear=False, **knobs).parent
    monkeypatch.setattr(registry, "_account_home", lambda: tmp_path / "machine-b")
    return char


def _desc(char: Path) -> dict:
    return json.loads((char / "character.json").read_text(encoding="utf-8"))


def _set_desc(char: Path, desc: dict) -> None:
    (char / "character.json").write_text(json.dumps(desc, indent=2), encoding="utf-8")


def test_a_character_drawn_elsewhere_is_the_factorys_work_here(tmp_path, monkeypatch):
    char = _drawn_elsewhere(tmp_path, monkeypatch)
    head = library_api.content_hash((char / "parts" / "head.svg").read_bytes())
    assert not registry.generated_by(head)  # this machine never saw it drawn
    assert factory_recorded(head, descriptor=_desc(char), path="parts/head.svg")
    lib = open_library("cutan")
    assert publish_dir(lib, char, "character.amy").rights.license_class == "free"


def test_carved_bytes_under_a_factory_stamp_and_a_real_recipe_stay_unverified(
    tmp_path, monkeypatch
):
    from cutan.characters.factory import FACTORY_LICENSE, FACTORY_PROVIDER

    char = _drawn_elsewhere(tmp_path, monkeypatch)
    carved = b"<svg>a head nobody has seen</svg>"
    (char / "parts" / "head.svg").write_bytes(carved)
    desc = _desc(char)
    digest = library_api.content_hash(carved)
    for skin in desc["skins"].values():
        for atts in skin["slots"].values():
            for att in atts.values():
                if att.get("path") == "parts/head.svg":
                    att["source"] = {"provider": FACTORY_PROVIDER, "license": FACTORY_LICENSE,
                                     "sha256": digest}
    _set_desc(char, desc)
    assert not factory_recorded(digest, descriptor=desc, path="parts/head.svg")
    lib = open_library("cutan")
    assert publish_dir(lib, char, "character.amy").rights.license_class == "unknown"


def test_an_edited_recipe_proves_nothing(tmp_path, monkeypatch):
    """A recipe edited to say `squat` re-derives another torso: the drawn one
    is not proved by it (bytes the edit does not touch still are)."""
    char = _drawn_elsewhere(tmp_path, monkeypatch)
    desc = _desc(char)
    desc["metadata"]["factory"]["steps"][0]["params"]["build"] = "squat"
    torso = library_api.content_hash((char / "parts" / "torso.svg").read_bytes())
    assert not factory_recorded(torso, descriptor=desc, path="parts/torso.svg")


def test_credits_in_a_project_read_the_proof(tmp_path, monkeypatch):
    from an.project import init

    project = init(tmp_path / "proj")
    char = _drawn_elsewhere(tmp_path, monkeypatch)
    import shutil

    shutil.copytree(char, project / "assets" / "characters" / "amy")
    report = collect_credits(build_project_mall(project))
    assert not report.unverified
    assert all(e.own_work for e in report.entries)


def test_a_file_swapped_in_during_the_run_is_not_proved_by_the_replay(tmp_path, monkeypatch):
    """The replay redraws with the real factory: bytes swapped into ONE run
    (and stamped there) are not what the recipe draws."""
    from cutan.characters import factory

    carved = b"<svg>a head nobody has seen</svg>"
    original = factory.stamp_factory_parts

    def swap_then_stamp(char_dir, paths, **kwargs):
        (Path(char_dir) / "parts" / "head.svg").write_bytes(carved)
        return original(char_dir, paths, **kwargs)

    monkeypatch.setattr(factory, "stamp_factory_parts", swap_then_stamp)
    monkeypatch.setattr(registry, "_account_home", lambda: tmp_path / "machine-a")
    char = factory.new_character(tmp_path / "art", name="zed", use_dicebear=False,
                                 views=False, gaze=False).parent
    monkeypatch.setattr(factory, "stamp_factory_parts", original)
    monkeypatch.setattr(registry, "_account_home", lambda: tmp_path / "machine-b")
    digest = library_api.content_hash(carved)
    assert not factory_recorded(digest, descriptor=_desc(char), path="parts/head.svg")
    assert publish_dir(open_library("cutan"), char, "character.zed").rights.license_class == "unknown"
