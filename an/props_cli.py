"""``an props …`` — a prop's asset folder from the shell (an#340).

A CORE module (``an.tools`` imports it at module level), so it reaches the
stage only inside its functions: the stage is behind the core firewall.

Wired into the top-level dispatcher as the ``props`` namespace
(``an.tools._dispatch_namespaces``), programmatically, per pillar 8: plain
functions taking strings and returning the text to print; the business logic is
:mod:`an.stage.prop_validate`. The prop's twin of ``an character validate`` /
``an character contract``.
"""

from __future__ import annotations

from pathlib import Path


def _resolve_dir(name: str, out_dir: str) -> Path:
    return Path(out_dir or Path.cwd() / "assets" / "props") / name


def validate(name: str, out_dir: str = "") -> str:
    """Check a prop's folder (prop.json + parts/) against the rig contract, offline.

    name: the prop's key (its folder name)
    out_dir: parent directory; defaults to ./assets/props
    """
    from an.stage.prop_validate import validate_prop

    report = validate_prop(_resolve_dir(name, out_dir), name=name)
    lines = [f"{name}: {'PASSED' if report.passed else 'FAILED'}"]
    lines += [
        f"  [{f.severity}] {f.ir_path}: {f.description}"
        + (f"\n      fix: {f.suggested_fix}" if f.suggested_fix else "")
        for f in report.findings
    ]
    return "\n".join(lines)


def contract() -> str:
    """Print what a prop folder must hold, generated from the schema and the rig rules."""
    from an.stage.prop_validate import render_prop_contract

    return render_prop_contract()


_dispatch_funcs = [validate, contract]
