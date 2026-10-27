"""A command that reports a failure exits non-zero (an#480, an#559).

`an validate` and `an props validate` printed FAILED and exited 0, so no script
or CI step could tell a failing check from a passing one by its status.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.cli_status import EXIT_POLICY, CommandReport, exit_code_of, failed
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


# ------------------------------ an#559: the remaining commands, table-driven


def test_every_core_command_declares_how_it_fails():
    """MUTATION: add a command to `an.tools._dispatch_funcs` without a line in
    `an.cli_status.EXIT_POLICY`, the one place the exit policy is written."""
    from an.__main__ import command_name
    from an.tools import _dispatch_funcs, _dispatch_namespaces

    commands = {command_name(f) for f in _dispatch_funcs} | {
        f"{group} {command_name(f)}"
        for group, funcs in _dispatch_namespaces.items()
        for f in funcs
    }
    assert commands == set(EXIT_POLICY), (
        f"undeclared: {sorted(commands - set(EXIT_POLICY))}; "
        f"gone: {sorted(set(EXIT_POLICY) - commands)}"
    )


def _unreadable_row(tmp_path):
    p = tmp_path / "row.json"
    p.write_text('{"schema_version": "nonsense"}', encoding="utf-8")
    return str(p)


#: ``(argv builder, text the output must hold, exit code)``: each a failure the
#: command reported and, before an#559, exited 0 on (or ended a Python caller's
#: process with `sys.exit`). The passing twin of each is in the tests above or
#: in the command's own test module.
_FAILING = {
    "bench: an unknown scene": (
        lambda tmp: ["bench", "--scenes", "no-such-scene"],
        "unknown corpus scene(s)",
        1,
    ),
    "bench: an unknown lever": (
        lambda tmp: ["bench", "--mutation", "not-a-lever"],
        "unknown mutation",
        1,
    ),
    "bench: a refused lever": (
        lambda tmp: ["bench", "--mutation", "pix_fmt"],
        "is not a lever",
        1,
    ),
    "bench: --bless with --mutation": (
        lambda tmp: ["bench", "--mutation", "high_crf", "--bless", "why"],
        "refusing --bless",
        1,
    ),
    "bench-compare --strict: an unreadable row": (
        lambda tmp: [
            "bench-compare",
            "--before",
            _unreadable_row(tmp),
            "--after",
            _unreadable_row(tmp),
            "--strict",
        ],
        "refused:",
        1,
    ),
    "bench-compare: the same, not strict, is an answer": (
        lambda tmp: [
            "bench-compare",
            "--before",
            _unreadable_row(tmp),
            "--after",
            _unreadable_row(tmp),
        ],
        "refused:",
        0,
    ),
    "bench-mutants: an unknown name": (
        lambda tmp: ["bench-mutants", "--names", "no-such-mutant"],
        "unknown mutant(s)",
        1,
    ),
    "voices rescore: no line matches": (
        lambda tmp: ["voices", "rescore", str(init(tmp / "p")), "zebra-zebra"],
        "no dialogue line contains",
        1,
    ),
}


@pytest.mark.parametrize("case", sorted(_FAILING))
def test_a_reported_failure_exits_with_its_code(case, tmp_path):
    """MUTATION: return the plain text instead of `failed(text)` in any of them."""
    argv, needle, code = _FAILING[case]
    out = _run(*argv(tmp_path))
    assert needle in out.output and out.exit_code == code, (case, out.output)


def test_bench_compare_strict_returns_its_failure_to_a_python_caller(tmp_path):
    """`--strict` used to `sys.exit(1)` from inside the function, ending the
    process of anyone who called it from Python (an#559)."""
    from an.tools import bench_compare

    row = _unreadable_row(tmp_path)
    out = bench_compare(before=row, after=row, strict=True)
    assert out.startswith("refused:") and exit_code_of(out) == 1


def _fake_render(severity):
    """An `_render_project` that renders nothing and reports one finding."""

    def render_project(project_dir, **kw):
        from an.render import _write_render_report
        from an.stores import build_project_mall
        from an.verify._base import Finding

        finding = Finding(severity, "timeline/0", f"a {severity} the render found")
        _write_render_report(
            build_project_mall(project_dir), "main", [("dialogue_fits", finding)]
        )
        return str(Path(project_dir) / "output" / "main.mp4")

    return render_project


@pytest.mark.parametrize("severity, code", [("error", 1), ("warning", 0)])
def test_render_exits_1_when_its_report_lists_an_error(
    severity, code, tmp_path, monkeypatch
):
    """The mp4 exists either way; an error in it must stop `an render && publish`.

    MUTATION: in `an.tools.render`, return `text` whatever the findings say.
    """
    monkeypatch.setattr("an.tools._render_project", _fake_render(severity))
    out = _run("render", str(init(tmp_path / "p")), "--no-cache")
    assert f"a {severity} the render found" in out.output
    assert out.exit_code == code, out.output


def test_voices_rescore_exits_0_when_a_line_matches(tmp_path, monkeypatch):
    """The passing twin of the no-match case: a matched line is not a failure,
    whatever `retake_lines` had to say about it."""
    from types import SimpleNamespace as NS

    scene = NS(timeline=[NS(id="s", dialogue=[NS(text="He did not ask")])])
    monkeypatch.setattr("an.project.load", lambda project, **kw: NS(scene=scene, mall={}))
    monkeypatch.setattr(
        "an.audio.pipeline.retake_lines",
        lambda *a, **k: ["'He did not ask': no take recorded yet"],
    )
    out = _run("voices", "rescore", str(tmp_path), "did not")
    assert "no take recorded yet" in out.output and out.exit_code == 0


def test_bench_mutants_exits_1_on_a_survivor_and_on_rot(monkeypatch):
    """Through the dispatcher: a survivor and a rotted declaration both exit 1,
    and a full catch exits 0 (an#559)."""
    from an.bench import mutants

    def runs(results):
        monkeypatch.setattr(mutants, "run_mutants", lambda wanted: results)

    runs([{"caught": True}, {"caught": False}])
    out = _run("bench-mutants", "--quiet")
    assert "1/2 caught" in out.output and out.exit_code == 1
    runs([{"caught": True}])
    assert _run("bench-mutants", "--quiet").exit_code == 0

    def rot(wanted):
        raise mutants.MutantError("the mutant declarations no longer match")

    monkeypatch.setattr(mutants, "run_mutants", rot)
    out = _run("bench-mutants", "--quiet")
    assert "no longer match" in out.output and out.exit_code == 1
