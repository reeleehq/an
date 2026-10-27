"""Changelog fragments (an#469): one file per PR, folded into ``misc/CHANGELOG.md``."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "misc" / "changelog.py"

_spec = importlib.util.spec_from_file_location("an_changelog_tool", SCRIPT)
tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tool
_spec.loader.exec_module(tool)

LEGACY = "# Changelog\n\nIntro.\n\n## 2026-10-26\n- old one\n\n## 2026-10-25\n- older\n"


def _write(directory: Path, name: str, text: str) -> None:
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")


def test_the_committed_changelog_renders_to_itself_without_fragments():
    text = tool.CHANGELOG.read_text(encoding="utf-8")
    assert tool.render(text, {}) == text


def test_every_committed_fragment_is_well_formed():
    tool.read_fragments()  # raises FragmentError otherwise


def test_two_prs_that_each_add_an_entry_touch_different_files_and_both_render(tmp_path):
    d = tmp_path / "changelog.d"
    _write(d, "2026-10-27-pr-a.md", "- **A** (an#1): a.\n")
    _write(d, "2026-10-27-pr-b.md", "- **B** (an#2): b.\n")
    out = tool.render(LEGACY, tool.read_fragments(d))
    assert out.index("## 2026-10-27") < out.index("## 2026-10-26")  # newest first
    assert out.index("**A**") < out.index("**B**") < out.index("## 2026-10-26")
    assert "- old one" in out and "- older" in out


def test_an_entry_goes_to_the_top_of_its_dates_section_and_a_gap_date_between(tmp_path):
    d = tmp_path / "changelog.d"
    _write(d, "2026-10-26-late.md", "- late\n")
    _write(d, "2026-10-25-x.md", "- x\n")
    _write(d, "2026-10-25-y.md", "- y\n")
    out = tool.render(LEGACY, tool.read_fragments(d))
    assert "## 2026-10-26\n- late\n- old one" in out
    assert "## 2026-10-25\n- x\n- y\n- older" in out
    assert tool.render(LEGACY, {"2026-10-24": [("a.md", "- oldest")]}).endswith(
        "- older\n\n## 2026-10-24\n- oldest\n"
    )


def test_fold_writes_the_entries_and_deletes_the_fragments(tmp_path):
    d, log = tmp_path / "changelog.d", tmp_path / "CHANGELOG.md"
    log.write_text(LEGACY, encoding="utf-8")
    _write(d, "2026-10-27-a.md", "- a\n")
    assert tool.fold(log, d) == 1
    assert "## 2026-10-27\n- a\n" in log.read_text(encoding="utf-8")
    assert not list(d.glob("2026-*.md"))
    assert tool.fold(log, d) == 0  # idempotent


@pytest.mark.parametrize(
    "name, text",
    [
        ("notes.md", "- x\n"),  # no date
        ("2026-10-27-x.md", "no bullet\n"),
        ("2026-10-27-y.md", "## 2026-10-27\n- heading\n"),
    ],
)
def test_a_malformed_fragment_is_refused_with_what_to_do(tmp_path, name, text):
    _write(tmp_path / "changelog.d", name, text)
    with pytest.raises(tool.FragmentError):
        tool.read_fragments(tmp_path / "changelog.d")


def test_the_script_runs_from_the_command_line():
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "check"], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
