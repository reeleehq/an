"""``an library …``: the CLI projection of the library functions (pillar 8).

In-process through typer's ``CliRunner`` over the real app, against temporary
roots only (``AN_HOME`` / ``CUTAN_HOME`` point into ``tmp_path``).
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.characters.factory import new_character
from an.library import open_library, show
from an.library.cli import _dispatch_funcs
from an.project import init as init_project
from an.tools import _dispatch_namespaces

runner = CliRunner()


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))


def _run(*args: str):
    return runner.invoke(build_app(), ["library", *args])


def test_the_library_group_is_wired_with_its_commands_pinned_by_literal():
    """MUTATION: drop a command from `an.library.cli._dispatch_funcs` or the namespace."""
    assert _dispatch_namespaces["library"] is _dispatch_funcs
    app = build_app()
    info = next(g for g in app.registered_groups if g.name == "library")
    assert [c.name for c in info.typer_instance.registered_commands] == [
        "publish",
        "find",
        "vocabulary",
        "show",
        "checkout",
        "promote",
        "retire",
    ]


def test_publish_find_show_checkout_from_the_shell(tmp_path):
    folder = new_character(tmp_path / "art", name="bob", use_dicebear=False).parent
    r = _run(
        "publish",
        str(folder),
        "character.bob",
        "--package",
        "cutan",
        "--style",
        "reiniger,gilliam",
        "--license",
        "cc0-1.0",
        "--provider",
        "an-tests",
    )
    assert r.exit_code == 0, r.output
    assert "cutan:character.bob@v001 [free]" in r.output

    r = _run(
        "find",
        "--package",
        "cutan",
        "--affords",
        "limbs.legs,swap.view:side",
        "--json-out",
    )
    assert r.exit_code == 0, r.output
    assert [h["ref"] for h in json.loads(r.output)["hits"]] == [
        "cutan:character.bob@v001"
    ]

    r = _run("show", "character.bob", "--package", "cutan")
    assert r.exit_code == 0 and "limbs.legs" in r.output and "rights: free" in r.output

    project = init_project(tmp_path / "proj")
    r = _run("checkout", str(project), "character.bob", "--package", "cutan")
    assert r.exit_code == 0, r.output
    assert 'library: "cutan:character.bob@v001"' in r.output
    assert (project / "assets" / "characters" / "bob" / "character.json").is_file()


def test_a_refusal_is_one_sentence_and_a_nonzero_exit():
    r = _run("show", "character.nobody", "--package", "cutan")
    assert r.exit_code == 1
    assert "is in none of the libraries" in r.output
    assert "Traceback" not in r.output


def test_promote_refuses_private_material_from_the_shell(tmp_path):
    folder = new_character(tmp_path / "art", name="carved", use_dicebear=False).parent
    _run(
        "publish",
        str(folder),
        "character.carved",
        "--package",
        "cutan",
        "--license",
        "all-rights-reserved-private-study",
        "--provider",
        "a-film",
    )
    r = _run("promote", "character.carved", "--package", "cutan")
    assert r.exit_code == 1 and "allow_restricted" in r.output
    assert "character.carved" not in open_library("an").records
    r = _run("promote", "character.carved", "--package", "cutan", "--allow-restricted")
    assert r.exit_code == 0, r.output
    assert (
        show(open_library("an"), "character.carved")["record"]["id"]
        == "character.carved"
    )


def test_vocabulary_is_json_an_agent_can_read():
    r = _run("vocabulary", "--package", "cutan")
    assert r.exit_code == 0
    assert "limbs.legs" in json.loads(r.output)["capabilities"]
