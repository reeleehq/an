"""The published contract package (ADR 0006, an#261): vocabulary export, package build, publish workflow.

Four claims, each checked here:

1. ``an/data/timing/vocabulary.json`` is what the vocabulary registry generates
   (a drift test, like the timing contract's), carries no code, and does not
   depend on which genres are loaded;
2. the package ``contract/build.py`` stages holds exactly the generated contract
   files, byte for byte as committed, and its manifest is sound;
3. the contract's version cannot go stale: a changed contract file without a
   recorded bump fails ``check``;
4. the workflow publishes only with a token and never fails for lack of one.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
import yaml

from an.semantic.export import VOCABULARY_FILE, build_vocabulary, vocabulary_drift
from an.timing import contract as timing_contract

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "contract-package.yml"


@pytest.fixture(scope="module")
def build():
    """``contract/build.py`` as a module (it is a script, not part of the wheel)."""
    spec = importlib.util.spec_from_file_location(
        "_contract_build", REPO_ROOT / "contract" / "build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _generated_files() -> dict[str, object]:
    """Every contract file as the registries generate it today, parsed."""
    generated = {
        name: json.loads(timing_contract.dumps(doc))
        for name, doc in timing_contract.build_contract().items()
    }
    generated[VOCABULARY_FILE] = json.loads(timing_contract.dumps(build_vocabulary()))
    return generated


# ------------------------------------------------- 1. the vocabulary export


def test_the_committed_vocabulary_is_what_the_registry_generates():
    """Regenerate with ``python -m an.semantic.export write``, deliberately,
    and record a contract version bump (``python contract/build.py bump``)."""
    assert vocabulary_drift() == []


def test_the_vocabulary_drift_check_notices_a_changed_entry(tmp_path):
    doc = build_vocabulary()
    doc["entries"][0]["version"] = "999"
    (tmp_path / VOCABULARY_FILE).write_text(
        timing_contract.dumps(doc), encoding="utf-8"
    )
    assert vocabulary_drift(tmp_path) == [
        f"{VOCABULARY_FILE}: differs from what the registry generates"
    ]
    assert vocabulary_drift(tmp_path / "nowhere") == [f"{VOCABULARY_FILE}: missing"]


def test_every_exported_entry_is_complete_data_without_code():
    doc = build_vocabulary()
    ids = [e["id"] for e in doc["entries"]]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    for e in doc["entries"]:
        assert {
            "id",
            "kind",
            "name",
            "version",
            "title",
            "description",
            "levels",
        } <= set(e)
        assert set(e["levels"]) <= set(doc["levels"]), e["id"]
        assert "expand" not in e, e["id"]
    json.dumps(doc, allow_nan=False)  # plain JSON all the way down


def test_camera_moves_are_entries_over_view_spaces():
    by_id = {e["id"]: e for e in build_vocabulary()["entries"]}
    spaces = {e["name"] for e in by_id.values() if e["kind"] == "view_space"}
    assert {"framing2d", "orbit3d"} <= spaces
    moves = [e for e in by_id.values() if e["kind"] == "camera_move"]
    assert {"push_in", "pan_left", "hold"} <= {e["name"] for e in moves}
    push_in = by_id["camera.push_in"]
    assert "space.framing2d" in push_in["requires"]
    axes = set(by_id["view.framing2d"]["params"]["properties"])
    for key in push_in["params"]["properties"]["path"]["default"]:
        assert set(key) - {"at", "easing"} <= axes


def test_the_export_does_not_depend_on_which_genres_are_loaded():
    """Only ``an``'s own entries are published; an installed genre never edits the file."""
    from an import genres

    before = build_vocabulary()
    genres.load()
    assert build_vocabulary() == before


def test_publishing_another_owners_entries_is_explicit():
    from an.semantic import entries

    assert build_vocabulary(owners=["no-such-owner"])["entries"] == []
    assert len(build_vocabulary()["entries"]) == len(entries(owner="an"))


# ------------------------------------------------------ 2. the staged package


def test_the_package_holds_exactly_the_generated_contract_files(build, tmp_path):
    staged = build.stage(tmp_path / "pkg")
    generated = _generated_files()
    assert set(generated) == set(timing_contract.CONTRACT_FILES) | {VOCABULARY_FILE}
    data = {n for n in staged if n.endswith(".json") and n != "package.json"}
    assert data == set(generated)
    for name, expected in generated.items():
        staged_text = (tmp_path / "pkg" / name).read_text(encoding="utf-8")
        assert timing_contract.values_close(json.loads(staged_text), expected), name
        committed = (REPO_ROOT / "an" / "data" / "timing" / name).read_bytes()
        assert (tmp_path / "pkg" / name).read_bytes() == committed.replace(
            b"\r\n", b"\n"
        )


def test_the_staged_manifest_is_the_committed_one_plus_exports(build, tmp_path):
    build.stage(tmp_path / "pkg")
    staged = json.loads((tmp_path / "pkg" / "package.json").read_text(encoding="utf-8"))
    committed = json.loads(
        (REPO_ROOT / "contract" / "package.json").read_text(encoding="utf-8")
    )
    exports = staged.pop("exports")
    assert staged == committed
    assert set(exports) == {"./package.json"} | {f"./{n}" for n in _generated_files()}
    assert all((tmp_path / "pkg" / target[2:]).is_file() for target in exports.values())
    assert committed["name"] == "@thorwhalen/an-contract"
    assert committed["publishConfig"] == {"access": "public"}
    assert re.fullmatch(r"\d+\.\d+\.\d+", committed["version"])
    # not `an`'s own version: the package has its own, tracking the contract
    assert "dependencies" not in committed and "scripts" not in committed


def test_the_readme_says_it_is_generated(build, tmp_path):
    build.stage(tmp_path / "pkg")
    readme = (tmp_path / "pkg" / "README.md").read_text(encoding="utf-8")
    assert "generated" in readme.lower() and "never edit" in readme.lower()
    assert (tmp_path / "pkg" / "LICENSE").is_file()


# --------------------------------------------- 3. the version tracks the files


def test_the_recorded_version_matches_the_contract_files(build):
    """A contract file changed without a bump: run
    ``python contract/build.py bump --level minor`` (additive) or ``--level major``."""
    assert build.check() == []


@pytest.fixture
def sandbox(build, tmp_path, monkeypatch):
    """The data folder, lock and manifest copied somewhere writable."""
    data = tmp_path / "data"
    shutil.copytree(build.DATA_DIR, data)
    monkeypatch.setattr(build, "LOCK_FILE", tmp_path / "contract.lock.json")
    monkeypatch.setattr(build, "PACKAGE_JSON", tmp_path / "package.json")
    shutil.copy(REPO_ROOT / "contract" / "contract.lock.json", build.LOCK_FILE)
    shutil.copy(REPO_ROOT / "contract" / "package.json", build.PACKAGE_JSON)
    return data


def test_a_changed_contract_file_without_a_bump_is_reported(build, sandbox):
    assert build.check(sandbox) == []
    (sandbox / VOCABULARY_FILE).write_text("{}\n", encoding="utf-8")
    problems = build.check(sandbox)
    assert (
        len(problems) == 1 and VOCABULARY_FILE in problems[0] and "bump" in problems[0]
    )


def test_a_line_ending_difference_is_not_a_change(build, sandbox):
    """A Windows checkout may rewrite line endings; the digest is of the text as git stores it."""
    path = sandbox / "easing.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert build.check(sandbox) == []


def test_bump_records_the_files_under_a_new_version(build, sandbox):
    before = build.version()
    major, minor, _ = (int(x) for x in before.split("."))
    (sandbox / VOCABULARY_FILE).write_text("{}\n", encoding="utf-8")
    new = build.bump(level="minor", directory=sandbox)
    assert new == f"{major}.{minor + 1}.0" and build.version() == new
    assert build.check(sandbox) == []
    assert build.bump(level="major", directory=sandbox) == f"{major + 1}.0.0"
    assert build.bump(to="9.8.7", directory=sandbox) == "9.8.7"
    with pytest.raises(ValueError, match="exactly one"):
        build.bump(directory=sandbox)
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        build.bump(to="v2", directory=sandbox)


# ----------------------------------------------------------- 4. the workflow


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_workflow_publishes_only_with_a_token_and_never_fails_without_one():
    doc = _workflow()
    triggers = doc.get("on") or doc[True]  # YAML 1.1 reads a bare `on` as True
    assert "an/data/timing/**" in triggers["push"]["paths"]
    steps = doc["jobs"]["contract-package"]["steps"]
    by_id = {s.get("id"): s for s in steps if s.get("id")}
    decide = by_id["decide"]["run"]
    assert "NPM_TOKEN" in decide and "SKIPPING the npm publish" in decide
    assert "exit 1" not in decide  # the missing token is a notice, not a failure
    publish = next(s for s in steps if s.get("name") == "Publish to npm")
    assert publish["if"] == "steps.decide.outputs.publish == 'true'"
    # the token is read through one job-level env var and handed only to the steps that need it
    assert "secrets.NPM_TOKEN" in json.dumps(doc["jobs"]["contract-package"]["env"])
    assert [s["name"] for s in steps if "secrets.NPM_TOKEN" in json.dumps(s)] == []
    assert doc["permissions"] == {"contents": "read"}
