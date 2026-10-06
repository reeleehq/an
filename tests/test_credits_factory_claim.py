"""A descriptor's factory stamp is "made by an itself" only when the factory's record confirms it (an#413).

The second end-user test found a library character listed by `an credits` under
"Made by an itself" while the library reported its rights `unknown` and credits
itself listed every one of its files as UNVERIFIED. The descriptor's stamp was
taken at its word; a part's stamp never was (review-288 B1). Now both read one
rule: a factory stamp counts only when this machine's factory record confirms
the bytes it pins, and only while the file still holds them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from an.credits import collect_credits
from an.library import open_library, publish_dir
from an.project import init as init_project
from an.stores import build_project_mall
from cutan.characters.factory import new_character

pytestmark = pytest.mark.genre("cutout_animation")


def _roots(monkeypatch, base: Path) -> None:
    monkeypatch.setenv("AN_HOME", str(base / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(base / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(base / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(base / "localappdata"))


@pytest.fixture(autouse=True)
def _machine(tmp_path, monkeypatch):
    _roots(monkeypatch, tmp_path / "machine-a")


def _project_with(tmp_path: Path, char: Path) -> Path:
    project = init_project(tmp_path / "film")
    shutil.copytree(char, project / "assets" / "characters" / char.name)
    return project


def _amy(tmp_path: Path) -> Path:
    return new_character(tmp_path / "art", name="amy", use_dicebear=False).parent


def _credits(project: Path):
    return collect_credits(build_project_mall(project))


def test_a_fresh_factory_character_is_an_s_own_work(tmp_path):
    report = _credits(_project_with(tmp_path, _amy(tmp_path)))
    assert "characters/amy" in [e.asset for e in report.entries if e.own_work]
    assert not [e for e in report.entries if e.license_class == "unknown"]


def test_an_unconfirmed_stamp_is_unverified_as_the_library_says(tmp_path, monkeypatch):
    """Bob's case: the factory stamps are there, but THIS machine's record does
    not know the bytes (drawn elsewhere). Credits and the library agree."""
    char = _amy(tmp_path)
    # A machine whose factory record is empty: the record lives under the
    # account's home as the OS records it, not under an environment variable.
    from an.library import registry

    monkeypatch.setattr(registry, "_account_home", lambda: tmp_path / "machine-b")
    report = _credits(_project_with(tmp_path, char))
    assert not [e for e in report.entries if e.own_work], "nothing is an's own here"
    entry = next(e for e in report.entries if e.asset == "characters/amy")
    assert entry.license_class == "unknown"
    assert "does not confirm" in entry.source.extra["reason"]
    rights = publish_dir(open_library("cutan"), char, "character.amy").rights
    assert rights.license_class == "unknown"


def test_a_stamp_about_a_drawing_changed_since_is_unverified(tmp_path):
    char = _amy(tmp_path)
    (char / "amy.svg").write_text("<svg>redrawn by hand</svg>", encoding="utf-8")
    report = _credits(_project_with(tmp_path, char))
    entry = next(e for e in report.entries if e.asset == "characters/amy")
    assert not entry.own_work and "changed since" in entry.source.extra["reason"]
