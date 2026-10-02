"""The core corpus: what it proves today, and the proof P8 has to make pass (an#279).

ADR 0001 decision 7: before any module leaves ``an`` for ``cutan`` (P8), the core
keeps a pixel gate of its own — paths, text, planes, camera and transitions on
``an.stage``, with no character, with goldens and contract hashes of their own
(:data:`an.bench.core_corpus.CORE_FIXTURES`).

**What this file proves today: the core corpus renders with NO GENRE
REGISTERED.** In a fresh interpreter the in-distribution cut-out genre and every
``an.genres`` entry point are switched off, so no cut-out action kind, entity
kind or compile pass exists; every core scene compiles to its blessed contract
hash (default leg) and renders to its goldens (labelled lane); and the task
imports no cut-out module the core had not already imported.

**The stronger proof, since the move (an#225):** the same corpus, in an interpreter where
every cut-out module (`cutan` and the old `cutan.characters`-style paths) is POISONED
before ``import an``, loaded or not -- :func:`test_the_core_corpus_compiles_with_the_cut_out_modules_poisoned`
and its render twin. The strict ``xfail`` they carried since #301 is gone: the stage
compiler reaches the genre only through registered hooks, so nothing cut-out runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from an.bench.core_corpus import CORE_FIXTURES
from an.ir.schema import SceneIR
from tests.test_import_firewall import ALLOWED_TODAY, GENRE

ROOT = Path(__file__).resolve().parents[1]

#: Runs in a FRESH interpreter: the genres switched off, then ``task``. Mode
#: ``no-new-import``: cut-out modules the core has already imported stay usable
#: (today's proof). Mode ``poisoned``: EVERY cut-out module raises on import from
#: the first line, before ``import an`` (the proof B0c must make pass).
_NO_GENRE = r"""
import importlib, json, sys
genre, task, names, mode = json.loads(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]), sys.argv[4]

def under(name, prefixes):
    return any(name == p or name.startswith(p + ".") for p in prefixes)

class Block:
    def __init__(self, allow_loaded):
        self.allow_loaded = allow_loaded
    def find_spec(self, name, path=None, target=None):
        if under(name, genre) and not (self.allow_loaded and name in sys.modules):
            raise ImportError(f"cut-out code was asked for: {name}")
        return None

if mode == "poisoned":
    sys.meta_path.insert(0, Block(allow_loaded=False))
# What the CORE drags in by itself (the allow-listed edges P8 removes):
import an, an.render, an.project, an.bench.core_corpus, an.bench.golden, an.bench.png
import an.bench.environment, an.adapters
preloaded = sorted(m for m in sys.modules if under(m, genre))
if mode != "poisoned":
    sys.meta_path.insert(0, Block(allow_loaded=True))
import an.genres as genres
genres.IN_DISTRIBUTION_GENRES = ()
genres.genre_entry_points = lambda **kw: ()

from pathlib import Path
import tempfile
from an.bench.core_corpus import CORE_FIXTURES, compiled_contract_sha256, golden_agreement, render_fixture
out = {}
if task == "contract":
    for name in names:
        out[name] = compiled_contract_sha256(CORE_FIXTURES[name], repo_root=Path.cwd())
else:
    from an.bench.environment import probe_browser
    from an.bench.golden import chromium_build_of

    build = chromium_build_of({"render_side": probe_browser()})
    for name in names:
        with tempfile.TemporaryDirectory() as d:
            work = render_fixture(CORE_FIXTURES[name], repo_root=Path.cwd(), base=Path(d))
            out[name] = golden_agreement(name, work, chromium_build=build)
loaded_after = sorted(m for m in sys.modules if under(m, genre))
print(json.dumps({
    "result": out,
    "genres": list(genres.installed()),
    "preloaded": preloaded,
    "loaded_by_task": sorted(set(loaded_after) - set(preloaded)),
}))
"""

def _run_without_the_genre(task: str, names: list[str], *, mode: str = "no-new-import") -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _NO_GENRE, json.dumps(list(GENRE)), task, json.dumps(names), mode],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _check_isolation(report: dict) -> None:
    assert report["genres"] == [], f"a genre was registered: {report['genres']}"
    assert report["loaded_by_task"] == [], (
        f"rendering the core corpus pulled in cut-out code: {report['loaded_by_task']}"
    )
    # What the core still imports by itself is exactly the allow-listed edges.
    allowed = {target for (_module, target) in ALLOWED_TODAY}
    stray = [
        m for m in report["preloaded"]
        if not any(m == p or m.startswith(p + ".") for p in allowed)
        # what an allow-listed module imports in turn (the bench runner's
        # corpus and capture) rides on its edge until P8 moves it
        and not m.startswith("an.bench.")
    ]
    assert not stray, f"the core imports cut-out modules no allow-list entry covers: {stray}"


def _committed_record(name: str) -> dict:
    records = sorted((ROOT / "misc" / "bench" / "golden" / name).glob("bless-*.json"))
    assert records, f"core scene {name!r} has no bless record"
    return json.loads(records[-1].read_text(encoding="utf-8"))


# ------------------------------------------------------------- default leg


def test_the_core_corpus_is_registered_in_the_bench():
    from an.bench.corpus import DFLT_FIXTURES

    for name, fixture in CORE_FIXTURES.items():
        assert DFLT_FIXTURES[name] is fixture, f"{name} is not run by `an bench`"
        assert len(fixture.golden_frames) >= 2 and fixture.golden_note


def test_the_core_corpus_covers_paths_text_planes_camera_and_transitions(tmp_path):
    """ADR 0001 decision 7's list, read off the scenes rather than their names.

    Loaded from a COPY: `load` syncs scene.md and ir/scene.json, which would
    rewrite a committed fixture.
    """
    from an.bench.core_corpus import stage_copy
    from an.project import load

    seen: set[str] = set()
    for name, fixture in CORE_FIXTURES.items():
        project = load(stage_copy(ROOT / fixture.path, tmp_path / name), check_kinds=False)
        scene: SceneIR = project.scene
        for shot in scene.timeline:
            kinds = {e.kind for e in shot.entities}
            assert "character" not in kinds, f"{name}: the core corpus draws no character"
            for e in shot.entities:
                if e.kind == "prop":
                    doc = project.mall["props"][e.ref]
                    seen.add({"PathDescriptor": "paths", "TextDescriptor": "text"}.get(doc.get("kind"), "props"))
                if e.kind == "environment":
                    seen.add("planes")
            if shot.camera is not None and shot.camera.keys:
                values = {(k.x, k.y, k.zoom, k.rotation) for k in shot.camera.keys}
                if len({v[:2] for v in values}) > 1:
                    seen.add("camera.translate")
                if len({v[2] for v in values}) > 1:
                    seen.add("camera.zoom")
                if len({v[3] for v in values}) > 1:
                    seen.add("camera.rotate")
            if shot.transition is not None:
                seen.add(f"transition.{shot.transition.kind}")
    assert seen >= {
        "paths", "text", "planes", "camera.translate", "camera.zoom", "camera.rotate",
        "transition.fade", "transition.dissolve",
    }, seen  # fmt: skip


def test_the_core_corpus_compiles_with_no_genre_registered_to_its_blessed_contracts():
    """Every core scene compiles with no genre registered, and importing no
    cut-out module the core had not already imported, to exactly the contract
    hash its goldens were blessed under. NOT a proof that no cut-out code runs
    (see the module docstring)."""
    report = _run_without_the_genre("contract", sorted(CORE_FIXTURES))
    _check_isolation(report)
    stale = {
        name: (_committed_record(name)["scene_contract_sha256"][:12], today[:12])
        for name, today in report["result"].items()
        if _committed_record(name)["scene_contract_sha256"] != today
    }
    assert not stale, f"compiled without the genre, the contract moved (blessed, today): {stale}"


# ---------------------------------------------------------- rendering lane


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_the_core_corpus_renders_with_no_genre_registered_to_its_goldens():
    """`an` renders the core corpus — paths, text, planes, camera, a fade and a
    dissolve — with no genre registered, pixel for pixel what was blessed. NOT a
    proof that no cut-out code runs (see the module docstring)."""
    report = _run_without_the_genre("render", sorted(CORE_FIXTURES))
    _check_isolation(report)
    moved = {
        f"{name}/{key}": (blessed[:12], today[:12])
        for name, frames in report["result"].items()
        for key, (blessed, today) in frames.items()
        if blessed != today
    }
    assert not moved, f"pinned frames that moved (blessed, today): {moved}"
    assert all(report["result"][name] for name in CORE_FIXTURES)


# ------------------------------------------- the proof of the move (an#225)


def _poisoned(task: str) -> dict:
    report = _run_without_the_genre(task, sorted(CORE_FIXTURES), mode="poisoned")
    assert report["genres"] == [] and report["preloaded"] == []
    return report


def test_the_core_corpus_compiles_with_the_cut_out_modules_poisoned():
    """ADR 0001 decision 7, for real: every cut-out module raises on import from
    the interpreter's first line — none can be preloaded — and the core corpus
    still compiles to its blessed contracts."""
    report = _poisoned("contract")
    for name, today in report["result"].items():
        assert _committed_record(name)["scene_contract_sha256"] == today, name


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_the_core_corpus_renders_with_the_cut_out_modules_poisoned():
    """The render twin: with every cut-out module poisoned, the core corpus
    renders to its goldens."""
    report = _poisoned("render")
    for frames in report["result"].values():
        assert frames and all(blessed == today for blessed, today in frames.values())
