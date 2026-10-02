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
    # The bench runner renders through the stage and serves any corpus (the
    # core's and a genre's: `cutan.bench` runs its own through it), so it is the
    # stage's, not a genre's (the move, an#225).
    "an.bench.corpus",
    "an.bench.capture",
    "an.bench.run",
    "an.bench.mutants",
    "an.bench.mutations",
    "an.data.cutout_runtime",  # old path of the runtime, now an alias
)

#: A genre: the ``cutan`` distribution, and the in-repo cut-out genre until it
#: moves there (an#225). The bench's corpus runner goes with it "until the core
#: corpus exists" (module map).
GENRE: tuple[str, ...] = (
    "cutan",
    # The old `an` paths of what moved: live aliases with a warning. A core module
    # importing one is a core module importing the genre, so they stay classified.
    "an.genres.cutout",
    "an.adapters.cutout.coarticulate",
    "an.adapters.cutout.gaze",
    "an.genre",
    "an.audio.offline_lipsync",
    "an.audio.rhubarb_lipsync",
    "an.audio.whisper_lipsync",
    "an.audio.injectable_lipsync",
    "an.verify.style",
    "an.library.character",
    "an.characters",
    "an.expression",
    "an.impacts",
)

#: Engines and back-ends no core module may need in order to import.
ENGINES: tuple[str, ...] = ("playwright", "manim", "manimkit")

FIREWALLED: tuple[str, ...] = STAGE + GENRE + ENGINES

#: Today's violations, ``(core module, firewalled prefix) -> what removes it``.
#: ONLY SHRINKS: see the module docstring.
ALLOWED_TODAY: dict[tuple[str, str], str] = {}


def _matches(name: str, prefixes: tuple[str, ...]) -> str | None:
    """The prefix ``name`` falls under, or ``None``."""
    return next((p for p in prefixes if name == p or name.startswith(p + ".")), None)


def _side(name: str) -> str | None:
    """``"stage"``, ``"genre"`` or ``"engine"`` by the LONGEST matching prefix; ``None`` for core."""
    hits = [
        (len(p), side)
        for side, prefixes in (("stage", STAGE), ("genre", GENRE), ("engine", ENGINES))
        for p in prefixes
        if name == p or name.startswith(p + ".")
    ]
    return max(hits)[1] if hits else None


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
import an
print(json.dumps({"seen": seen, "failed": failed, "root": an.__file__}))
"""


def _this_tree_first() -> dict[str, str]:
    """The environment for a probe subprocess: THIS checkout's `an` first.

    A developer machine has `an` installed editable from some checkout, and its
    import hook outranks the working directory; a probe run from a worktree
    would otherwise judge the other checkout's code.
    """
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return env


@pytest.fixture(scope="module")
def dynamic_violations() -> dict[tuple[str, str], str]:
    core = [name for name, _ in _core_modules() if not name.endswith("__main__")]
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(list(FIREWALLED)), json.dumps(core)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=_this_tree_first(),
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    # The probe must have imported THIS tree's `an`: a module that cannot be
    # found at all means another installed `an` answered (an editable install
    # of a different checkout outranks the working directory), and every
    # verdict above would be about that one.
    unknown = {m: e for m, e in report["failed"].items() if "No module named 'an." in e}
    assert not unknown, f"the probe imported another tree's `an`: {unknown}"
    assert report.get("root") == str(PACKAGE / "__init__.py"), report.get("root")
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


#: Imports one module with the `an` package STUBBED (so `an/__init__`, which
#: still loads the stage today, does not run) and every firewalled prefix --
#: and `an.adapters`, whose init imports the stage -- made to RAISE. A module
#: already in `sys.modules` cannot hide an import here, which is the dynamic
#: probe's blind spot (review of an#250, S3).
_BLOCKED = r"""
import importlib, json, sys, types
package_dir, blocked, module = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
an = types.ModuleType("an"); an.__path__ = [package_dir]; sys.modules["an"] = an

class Block:
    def find_spec(self, name, path=None, target=None):
        if any(name == p or name.startswith(p + ".") for p in blocked):
            raise ImportError(f"firewalled: {name}")
        return None

sys.meta_path.insert(0, Block())
importlib.import_module(module)
leaked = sorted(m for m in sys.modules if any(m == p or m.startswith(p + ".") for p in blocked))
print(json.dumps(leaked))
"""


def _new_seam_modules() -> list[str]:
    paths = [*sorted((PACKAGE / "engines").rglob("*.py")), *sorted((PACKAGE / "media").rglob("*.py"))]
    return [_module_name(p) for p in paths] + ["an._shims"]


@pytest.mark.parametrize("module", _new_seam_modules())
def test_a_new_seam_imports_with_the_stage_and_the_genre_unimportable(module):
    """Each module of `an.engines`, `an.media` and `an._shims`, imported in a
    fresh interpreter where everything behind the firewall raises on import."""
    blocked = [*FIREWALLED, "an.adapters"]
    result = subprocess.run(
        [sys.executable, "-c", _BLOCKED, str(PACKAGE), json.dumps(blocked), module],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"{module} cannot be imported without the stage, a genre or an engine:\n"
        + result.stderr[-1500:]
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


# -----------------------------------------------------------------------------
# The second perimeter: the STAGE imports no genre (an#296, P8 B0a).
#
# `an.stage` ships inside the `an` distribution and a genre package (`cutan`)
# depends on `an`, so a stage module importing genre code at module level is a
# reverse dependency: it breaks the day the genre's code leaves the repository.
# Three passes: static top-level imports, a dynamic probe attributing every
# load, and (below) function-level imports -- each allow-list only shrinks.
# The dynamic probe is nearly vacuous until P8 B0b: core modules (`an.ir.validate`)
# load `cutan.characters` and `cutan.expression` before any stage module runs, so the
# probe attributes those loads to the core. The static passes are complete.
# -----------------------------------------------------------------------------

#: Today's stage -> genre edges, ``(stage module, genre prefix) -> what removes it``.
#: ONLY SHRINKS.
STAGE_ALLOWED_TODAY: dict[tuple[str, str], str] = {}


def _stage_modules() -> list[tuple[str, Path]]:
    """Every module under ``an/`` that the classification puts on the stage side."""
    return [
        (_module_name(p), p)
        for p in sorted(PACKAGE.rglob("*.py"))
        if _side(_module_name(p)) == "stage" and not _module_name(p).endswith(".conftest")
    ]


def _genre_prefix(name: str) -> str | None:
    """The GENRE prefix ``name`` falls under, when the longest match is a genre one."""
    return _matches(name, tuple(sorted(GENRE, key=len, reverse=True))) if _side(name) == "genre" else None


def _stage_static_violations() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for module, path in _stage_modules():
        for target, line in _module_level_imports(path, module):
            prefix = _genre_prefix(target)
            if prefix:
                out.setdefault((module, prefix), f"{path.relative_to(ROOT)}:{line} imports {target}")
    return out


@pytest.fixture(scope="module")
def stage_dynamic_violations() -> dict[tuple[str, str], str]:
    """The core probe, run over the stage modules with only the GENRE firewalled;
    kept: loads attributed to a STAGE module (a core module's own edges are the
    core perimeter's business)."""
    stage = [name for name, _ in _stage_modules()]
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(list(GENRE)), json.dumps(stage)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=_this_tree_first(),
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report.get("root") == str(PACKAGE / "__init__.py"), report.get("root")
    out = {}
    for key, name in report["seen"].items():
        owner, _prefix = key.split("|", 1)
        prefix = _genre_prefix(name)
        if _side(owner) == "stage" and prefix:
            out.setdefault((owner, prefix), f"loaded {name} at import")
    return out


def test_the_stage_classification_is_not_empty():
    """A rename that emptied the stage side would make the next three tests vacuous."""
    names = {n for n, _ in _stage_modules()}
    assert {"an.stage.compile", "an.stage.props", "an.stage.render"} <= names


def test_no_stage_module_imports_a_genre_at_module_level():
    """Static: every top-level import of every stage module."""
    new = {k: v for k, v in _stage_static_violations().items() if k not in STAGE_ALLOWED_TODAY}
    assert not new, (
        "a stage module imports genre code at module level. The stage ships in "
        "`an` and the genre depends on `an`: register the behaviour from the "
        "genre (a compile pass, an entity- or action-kind hook) instead:\n"
        + "\n".join(f"  {m} -> {p}: {where}" for (m, p), where in sorted(new.items()))
    )


def test_importing_the_stage_loads_no_genre(stage_dynamic_violations):
    new = {k: v for k, v in stage_dynamic_violations.items() if k not in STAGE_ALLOWED_TODAY}
    assert not new, (
        "importing a stage module loads genre code (attributed to the stage "
        "module running top-level code when it loaded):\n"
        + "\n".join(f"  {m} -> {p}: {how}" for (m, p), how in sorted(new.items()))
    )


def test_the_stage_allow_list_only_shrinks(stage_dynamic_violations):
    observed = set(_stage_static_violations()) | set(stage_dynamic_violations)
    stale = sorted(k for k in STAGE_ALLOWED_TODAY if k not in observed)
    assert not stale, (
        "these stage allow-list entries no longer happen; delete them so the "
        f"next regression cannot hide under them: {stale}"
    )


def test_every_stage_exemption_says_what_removes_it():
    for key, why in STAGE_ALLOWED_TODAY.items():
        assert "an#" in why, f"{key}: cite the issue or PR that removes it"


# -- Lazy imports (review of an#298, M5) ---------------------------------------
#
# The CORE perimeter exempts a function-level import on purpose: that is how an
# optional back-end stays optional. For stage -> genre it is no exemption: a
# lazy import of genre code is still a reverse dependency, it just fails later
# -- at render time, without the genre. `an.stage.raster.art_size` sizes EVERY
# SVG (props, environments, `an validate`) through `cutan.characters.svg_utils`, so
# once the characters leave, a character-free prop would need `cutan` to render.


def _all_imports(path: Path, module: str) -> list[tuple[str, int]]:
    """``(imported name, line)`` for every import ANYWHERE in the file (function
    bodies included), ``if TYPE_CHECKING:`` blocks excluded."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    skipped = {
        id(n)
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and _is_type_checking(node.test)
        for n in ast.walk(node)
    }
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Import):
            found.extend((a.name, node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                head = parts[: len(parts) - node.level + 1]
                base = ".".join(head + ([base] if base else []))
            found.append((base, node.lineno))
            found.extend((f"{base}.{a.name}", node.lineno) for a in node.names)
    return found


def _stage_lazy_violations() -> dict[tuple[str, str], str]:
    """Stage -> genre imports that happen only inside functions."""
    out: dict[tuple[str, str], str] = {}
    for module, path in _stage_modules():
        top = {t for t, _ in _module_level_imports(path, module)}
        for target, line in _all_imports(path, module):
            prefix = _genre_prefix(target)
            if prefix and target not in top:
                out.setdefault((module, prefix), f"{path.relative_to(ROOT)}:{line} imports {target}")
    return out


#: Today's LAZY stage -> genre edges. ONLY SHRINKS, like the others.
STAGE_LAZY_ALLOWED_TODAY: dict[tuple[str, str], str] = {}


def test_no_stage_module_imports_a_genre_even_lazily():
    new = {k: v for k, v in _stage_lazy_violations().items() if k not in STAGE_LAZY_ALLOWED_TODAY}
    assert not new, (
        "a stage module imports genre code inside a function. The stage ships "
        "in `an` and must work without the genre: register the behaviour from "
        "the genre instead:\n"
        + "\n".join(f"  {m} -> {p}: {where}" for (m, p), where in sorted(new.items()))
    )


def test_the_stage_lazy_allow_list_only_shrinks():
    stale = sorted(k for k in STAGE_LAZY_ALLOWED_TODAY if k not in _stage_lazy_violations())
    assert not stale, f"delete these stale lazy allow-list entries: {stale}"


def test_every_stage_lazy_exemption_says_what_removes_it():
    for key, why in STAGE_LAZY_ALLOWED_TODAY.items():
        assert "an#" in why, f"{key}: cite the issue or PR that removes it"
