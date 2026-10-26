"""A command that reports a failure exits non-zero (an#480).

`an validate` and `an props validate` printed FAILED and exited 0, so no script
or CI step could tell a failing check from a passing one by its status.
"""

from __future__ import annotations

import os
import time

from typer.testing import CliRunner

from an.__main__ import build_app
from an.cli_status import CommandReport, exit_code_of, failed
from an.project import init

runner = CliRunner()


def _run(*args):
    return runner.invoke(build_app(), list(args))


def test_validate_exits_1_on_a_failed_report_and_0_on_a_pass(tmp_path):
    root = init(tmp_path / "p")
    ok = _run("validate", str(root))
    assert ok.exit_code == 0 and "validation: passed" in ok.output
    scene = root / "scene.md"
    scene.write_text(
        "# T\n\n```yaml meta\ntitle: T\nduration: 1\nfps: 24\ndefault_renderer: cutout\n"
        "style_pack: nosuch\n```\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1\n```\n",
        encoding="utf-8",
    )
    os.utime(scene, (time.time() + 10, time.time() + 10))  # newer than the seed json
    bad = _run("validate", str(root), "--strict-assets")
    assert "validation: FAILED" in bad.output and bad.exit_code == 1


def test_props_validate_exits_1_when_it_reports_FAILED(tmp_path):
    out = _run("props", "validate", "nosuch", "--out-dir", str(tmp_path))
    assert "nosuch: FAILED" in out.output and out.exit_code == 1


def test_a_failed_report_is_still_the_text_python_callers_saw():
    r = failed("x: FAILED")
    assert isinstance(r, str) and r == "x: FAILED" and r.exit_code == 1
    assert exit_code_of("plain") == 0 and exit_code_of(CommandReport("ok")) == 0


def test_a_refused_argument_exits_1(tmp_path):
    out = _run("render", str(init(tmp_path / "p")), "--parallel", "abc")
    assert "invalid --parallel" in out.output and out.exit_code == 1


def test_props_validate_exits_1_on_a_bad_descriptor_and_0_on_a_good_one(tmp_path):
    import shutil
    from pathlib import Path

    lamp = Path(__file__).resolve().parent / "fixtures" / "props" / "lamp"
    shutil.copytree(lamp, tmp_path / "lamp")
    assert _run("props", "validate", "lamp", "--out-dir", str(tmp_path)).exit_code == 0
    (tmp_path / "lamp" / "parts" / "off.svg").unlink()
    bad = _run("props", "validate", "lamp", "--out-dir", str(tmp_path))
    assert "lamp: FAILED" in bad.output and bad.exit_code == 1


def test_string_operations_drop_the_exit_code_so_failed_is_called_last():
    """The documented caveat of `failed()`: composing a report is a plain str."""
    assert exit_code_of(failed("x") + "y") == 0 and exit_code_of(f"{failed('x')}") == 0
