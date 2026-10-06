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
    """The prop folder ``name`` means: a path to the folder (or to its
    ``prop.json``) when it is one, else a KEY under ``out_dir`` (an#459: an
    end user passed the path and was told the prop had no ``prop.json``)."""
    given = Path(name)
    if given.name == "prop.json" and given.is_file():
        return given.parent
    if (given / "prop.json").is_file():
        return given
    return Path(out_dir or Path.cwd() / "assets" / "props") / name


def validate(name: str, out_dir: str = "") -> str:
    """Check a prop's folder (prop.json + parts/) against the rig contract, offline.

    name: the prop's key (its folder name under out_dir), or a path to its
        folder or to its prop.json
    out_dir: parent directory of the keys; defaults to ./assets/props
    """
    from an.stage.prop_validate import validate_prop

    directory = _resolve_dir(name, out_dir)
    if not directory.is_dir():
        where = Path(out_dir or Path.cwd() / "assets" / "props")
        return (
            f"{name}: FAILED\n  no prop folder at {directory}: pass a prop's KEY "
            f"(a folder name under {where}, set by --out-dir), or a path to a "
            "folder that holds a prop.json"
        )
    report = validate_prop(directory, name=directory.name)
    lines = [f"{directory.name}: {'PASSED' if report.passed else 'FAILED'}"]
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
