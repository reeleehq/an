"""The curated MCP surface (ADR 0003 decision 6, an#248).

The tools are plain functions and are tested as such, with no MCP stack; the
server projection is tested where the ``an[mcp]`` extra (``py2mcp``) is
installed and skipped where it is not (CI installs no extras). Two import
guarantees hold everywhere: ``import an`` never imports the MCP package, and
importing the MCP package imports no MCP dependency.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from an.mcp import TOOL_REFS, tools

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "characters"
MCP_STACK = ("py2mcp", "fastmcp", "mcp")


def _modules_after(code: str) -> set[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    out = subprocess.run(
        [sys.executable, "-c", code + "; import sys; print(' '.join(sorted(sys.modules)))"],
        capture_output=True,
        text=True,
        check=True,
        env=env,
        cwd=ROOT,
    )
    return set(out.stdout.split())


def test_import_an_does_not_import_the_mcp_surface_or_its_stack():
    loaded = _modules_after("import an")
    assert not {m for m in loaded if m == "an.mcp" or m.startswith("an.mcp.")}
    assert not {m for m in loaded if m.split(".")[0] in MCP_STACK}


def test_importing_the_mcp_package_imports_no_mcp_dependency():
    loaded = _modules_after("import an.mcp, an.mcp.server")
    assert not {m for m in loaded if m.split(".")[0] in MCP_STACK}


def test_the_surface_is_the_curated_list_and_the_bench_is_not_on_it():
    names = [ref.split(":")[1] for ref in TOOL_REFS]
    assert names == [
        "vocabulary",
        "vocabulary_entry",
        "scene_schema",
        "validate_scene",
        "describe_character",
        "applicable_methods",
        "why_not_method",
        "apply_patch",
        "start_render",
        "job_status",
    ]
    assert not [n for n in names if "bench" in n]


@pytest.fixture()
def project(tmp_path):
    from an import init

    root = init(tmp_path / "p")
    shutil.copytree(FIXTURES / "gale", root / "assets" / "characters" / "gale")
    return root


@pytest.mark.genre("cutout_animation")
def test_queries_answer_from_the_registry(project):
    assert {e["kind"] for e in tools.vocabulary()} >= {"method", "motion_preset", "easing"}
    some = next(e for e in tools.vocabulary() if e["kind"] == "method")
    assert tools.vocabulary_entry(some["id"])["name"] == some["name"]
    assert "timeline" in tools.scene_schema()["properties"]
    assert "slots" in tools.scene_schema("character")["properties"]
    with pytest.raises(ValueError):
        tools.scene_schema("nope")


@pytest.mark.genre("cutout_animation")
def test_the_capability_queries_describe_a_character(project):
    d = tools.describe_character(str(project), "gale")
    from an.semantic import aspect

    chain = aspect("locomotion").chain  # the genre's own declaration (an#427)
    assert d["aspects"]["locomotion"]["default"] == chain[0]
    assert "limbs.legs" in d["affordances"]
    assert chain[0] in tools.applicable_methods("locomotion", str(project), "gale")
    assert tools.why_not_method(chain[0], str(project), "gale") == []
    with pytest.raises(KeyError, match="known"):
        tools.describe_character(str(project), "nobody")


def test_a_typed_patch_is_validated_and_dry_run_by_default(project):
    from an.project import load

    before = load(project).scene.meta.title
    r = tools.apply_patch(str(project), [{"op": "set", "path": "meta/title", "value": "New"}])
    assert r["valid"] and not r["applied"]
    assert load(project).scene.meta.title == before
    r = tools.apply_patch(
        str(project), [{"op": "set", "path": "meta/title", "value": "New"}], dry_run=False
    )
    assert r["applied"] and load(project).scene.meta.title == "New"
    bad = tools.apply_patch(str(project), [{"op": "set", "path": "meta/fps", "value": "fast"}])
    assert not bad["valid"] and not bad["applied"]


def test_long_work_is_a_job_you_start_and_poll(project, monkeypatch):
    import an.render

    def fake_render(project_dir, **kwargs):
        time.sleep(0.05)
        return Path(project_dir) / "out.mp4"

    monkeypatch.setattr(an.render, "render_project", fake_render)
    started = tools.start_render(str(project))
    assert started["status"] == "running"
    for _ in range(100):
        status = tools.job_status(started["job"])
        if status["status"] != "running":
            break
        time.sleep(0.02)
    assert status["status"] == "done" and status["result"].endswith("out.mp4")
    with pytest.raises(KeyError):
        tools.job_status("no-such-job")


@pytest.mark.genre("cutout_animation")
def test_the_server_projects_exactly_the_curated_tools():
    pytest.importorskip("py2mcp", reason="the `an[mcp]` extra is optional")
    import asyncio

    from an.mcp.server import mk_server

    server = mk_server()
    listed = sorted(t.name for t in asyncio.run(server.list_tools()))
    assert listed == sorted(ref.split(":")[1] for ref in TOOL_REFS)
    out = asyncio.run(server.call_tool("vocabulary_entry", {"entry_id": "speech.pose_only"}))
    assert '"pulse"' in out.content[0].text
