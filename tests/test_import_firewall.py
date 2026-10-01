"""The import firewall: no core module imports the stage, a genre, or an engine at module level.

ADR 0001 decision 14 (core study §3): the core must be importable, and usable,
without the 2D stage runtime (``an.stage`` -- today still at its pre-move paths),
without a genre package (``cutan``; today the in-repo cut-out genre), and
without Playwright, Manim or ``manimkit``. Back-ends are optional dependencies
with typed, install-hinting errors; the firewall is about IMPORTS, not about
which extras CI installs.

The pattern is ``walkthru``'s firewall test (import the core, look at what got
loaded), with two changes for a repository this size:

- it runs in a SUBPROCESS, so deleting and re-importing modules can never split
  a registry or a class identity in the test process; and
- every load of a firewalled module is ATTRIBUTED, by a ``sys.meta_path``
  probe, to the innermost core module executing module-level code at that
  moment -- so a violation names the module that has to change, and a package
  ``__init__`` that pulls in the stage (``an.adapters``) is blamed once instead
  of every module that imports a sibling of it.

A static pass (top-level ``import`` statements in every core file, ``if
TYPE_CHECKING:`` blocks excluded) covers what import order hides from the
dynamic one: a module is loaded once, so only its first importer is observed.

**The allow-list only shrinks.** It starts as today's violations, each citing
the issue or PR that removes it. A new violation fails; an entry that no longer
happens fails too ("stale: delete it"), so a fix cannot leave its exemption
behind for the next regression to hide under.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "an"

#: Destined for ``an.stage`` (core study §5, module map): the 2D stage runtime
#: and what it draws for every genre. Outside the firewall.
STAGE: tuple[str, ...] = (
    "an.stage",
    "an.adapters.cutout",  # serialize, render, canvas_capture, ... (moves in an#247 PR B)
    "an.paths",
    "an.text",
    "an.raster",
    "an.environments",
    "an.props",
    "an.preview",
    "an.bench.contract",  # hashes the stage's compiled document
    "an.bench.stage",
    "an.bench.palette",
    "an.data.cutout_runtime",
)

#: A genre: the ``cutan`` distribution, and the in-repo cut-out genre until it
#: moves there (an#225). The bench's corpus runner goes with it "until the core
#: corpus exists" (module map).
GENRE: tuple[str, ...] = (
    "cutan",
    "an.genres.cutout",
    "an.characters",
    "an.expression",
    "an.impacts",
    "an.bench.corpus",
    "an.bench.capture",
    "an.bench.run",
    "an.bench.mutants",
    "an.bench.mutations",
)

#: Engines and back-ends no core module may need in order to import.
ENGINES: tuple[str, ...] = ("playwright", "manim", "manimkit")

FIREWALLED: tuple[str, ...] = STAGE + GENRE + ENGINES

#: Today's violations, ``(core module, firewalled prefix) -> what removes it``.
#: ONLY SHRINKS: see the module docstring.
ALLOWED_TODAY: dict[tuple[str, str], str] = {
    ("an.adapters", "an.adapters.cutout"): (
        "an#247 PR B: the stage registers its own renderer; the package no "
        "longer imports a backend to register it"
    ),
    ("an.render", "an.adapters.cutout"): (
        "an#247 PR B: `style_pack_for` and the cut-out caption branch route "
        "through the engine seam"
    ),
    ("an.bench.imageio", "an.adapters.cutout"): (
        "an#247 PR B: the lossless leg reads the argv and the pixel-format check "
        "from an.media"
    ),
    ("an.tools", "an.preview"): "an#247 PR B: `an preview` imports the stage lazily",
    ("an.tools", "an.characters"): "an#225 (P8): the `an character` namespace registers from cutan",
    ("an.tools", "an.impacts"): "an#225 (P8): the `an impacts` namespace registers from cutan",
    ("an.ir", "an.characters"): (
        "an#225 (P8): the character descriptor's document kind registers from cutan"
    ),
    ("an.ir.validate", "an.characters"): "an#246 (P8): cut-out branches left in core checks",
    ("an.ir.validate", "an.expression"): "an#246 (P8): cut-out branches left in core checks",
    ("an.bench", "an.bench.run"): (
        "an#225 (P8): the cut-out corpus runner moves with cutan; the core "
        "corpus gets its own"
    ),
}


def _matches(name: str, prefixes: tuple[str, ...]) -> str | None:
    """The prefix ``name`` falls under, or ``None``."""
    return next((p for p in prefixes if name == p or name.startswith(p + ".")), None)


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _core_modules() -> list[tuple[str, Path]]:
    """Every module of the ``an`` package that is neither stage nor genre."""
    out = []
    for path in sorted(PACKAGE.rglob("*.py")):
        name = _module_name(path)
        if _matches(name, FIREWALLED) or name.endswith(".conftest"):
            continue
        out.append((name, path))
    return out


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _module_level_imports(path: Path, module: str) -> list[tuple[str, int]]:
    """``(imported name, line)`` for every import executed at module level."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    found: list[tuple[str, int]] = []

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.Import):
                found.extend((a.name, node.lineno) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".")
                    head = parts[: len(parts) - node.level + 1]
                    base = ".".join(head + ([base] if base else []))
                found.append((base, node.lineno))
                # `from an.adapters import cutout` imports a MODULE.
                found.extend((f"{base}.{a.name}", node.lineno) for a in node.names)
            elif isinstance(node, ast.If):
                if not _is_type_checking(node.test):
                    visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body)
                visit(node.orelse)
                visit(node.finalbody)
                for handler in node.handlers:
                    visit(handler.body)
            elif isinstance(node, ast.With):
                visit(node.body)

    visit(tree.body)
    return found


def _static_violations() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for module, path in _core_modules():
        for target, line in _module_level_imports(path, module):
            prefix = _matches(target, FIREWALLED)
            if prefix:
                out.setdefault((module, prefix), f"{path.relative_to(ROOT)}:{line} imports {target}")
    return out


#: Run in a fresh interpreter: import every core module, attributing each first
#: load of a firewalled module to the innermost core module running top-level code.
_PROBE = r"""
import importlib, json, sys
firewalled, core = json.loads(sys.argv[1]), json.loads(sys.argv[2])

def matches(name):
    return next((p for p in firewalled if name == p or name.startswith(p + ".")), None)

seen, failed = {}, {}

class Probe:
    def find_spec(self, name, path=None, target=None):
        prefix = matches(name)
        if prefix:
            frame = sys._getframe(1)
            while frame is not None:
                owner = frame.f_globals.get("__name__", "")
                if frame.f_code.co_name == "<module>" and (owner == "an" or owner.startswith("an.")):
                    break
                frame = frame.f_back
            owner = frame.f_globals["__name__"] if frame is not None else "<outside an>"
            if not matches(owner):
                seen.setdefault(owner + "|" + prefix, name)
        return None

sys.meta_path.insert(0, Probe())
for module in core:
    try:
        importlib.import_module(module)
    except ImportError as e:  # an optional dependency of that module is absent
        failed[module] = f"{type(e).__name__}: {e}"
print(json.dumps({"seen": seen, "failed": failed}))
"""


@pytest.fixture(scope="module")
def dynamic_violations() -> dict[tuple[str, str], str]:
    core = [name for name, _ in _core_modules() if not name.endswith("__main__")]
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(list(FIREWALLED)), json.dumps(core)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    return {
        tuple(key.split("|", 1)): f"loaded {name} at import"
        for key, name in report["seen"].items()
    }


def test_the_classification_names_real_modules():
    """A typo in the lists above would silently widen the core or the firewall."""
    in_repo = [p for p in STAGE + GENRE if p.startswith("an.")]
    known = {_module_name(p) for p in PACKAGE.rglob("*.py")}
    # `an.stage` arrives in an#247 PR B; until then it may be absent.
    missing = [p for p in in_repo if p not in known and p != "an.stage"]
    assert not missing, f"no such module in an/: {missing}"


def test_no_core_module_imports_the_stage_a_genre_or_an_engine_at_module_level():
    """Static: every top-level import of every core module."""
    new = {k: v for k, v in _static_violations().items() if k not in ALLOWED_TODAY}
    assert not new, (
        "a core module imports something behind the firewall at module level. "
        "Import it inside the function that needs it, or move the code to the "
        "stage or the genre (ADR 0001 decision 14):\n"
        + "\n".join(f"  {m} -> {p}: {where}" for (m, p), where in sorted(new.items()))
    )


def test_importing_the_core_loads_nothing_behind_the_firewall(dynamic_violations):
    """Dynamic: what actually loads, through package inits and import-time calls."""
    new = {k: v for k, v in dynamic_violations.items() if k not in ALLOWED_TODAY}
    assert not new, (
        "importing a core module loads a firewalled module (attributed to the "
        "core module running top-level code when it loaded):\n"
        + "\n".join(f"  {m} -> {p}: {how}" for (m, p), how in sorted(new.items()))
    )


def test_the_allow_list_only_shrinks(dynamic_violations):
    """An exemption whose violation is gone must be deleted with the fix."""
    observed = set(_static_violations()) | set(dynamic_violations)
    stale = sorted(k for k in ALLOWED_TODAY if k not in observed)
    assert not stale, (
        "these allow-list entries no longer happen; delete them so the next "
        f"regression cannot hide under them: {stale}"
    )


def test_every_exemption_says_what_removes_it():
    for key, why in ALLOWED_TODAY.items():
        assert "an#" in why, f"{key}: cite the issue or PR that removes it"


@pytest.mark.parametrize("package", ["an.engines", "an.media", "an._shims"])
def test_the_new_core_seams_import_nothing_behind_the_firewall(package):
    """The packages an#247 adds are clean by construction, with no exemption."""
    paths = (
        sorted((PACKAGE / package.split(".", 1)[1]).rglob("*.py"))
        if (PACKAGE / package.split(".", 1)[1]).is_dir()
        else [PACKAGE / (package.split(".", 1)[1] + ".py")]
    )
    bad = []
    for path in paths:
        module = _module_name(path)
        for target, line in _module_level_imports(path, module):
            if _matches(target, FIREWALLED) or target == "an.adapters" or target.startswith(
                "an.adapters."
            ):
                bad.append(f"{path.relative_to(ROOT)}:{line} imports {target}")
    assert not bad, (
        "the engine seam and the media package must not import the stage, a "
        "genre, an engine -- or `an.adapters`, whose package init still imports "
        f"the stage to register it: {bad}"
    )
