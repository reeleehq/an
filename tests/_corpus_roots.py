"""Where the committed scenes live: this repository, and the ``cutan`` checkout when there is one.

The cut-out corpus (``examples/``, ``misc/bench/corpus/``) moved to ``cutan`` (an#225).
``an`` still holds invariants about EVERY committed scene (dialogue stamped where its
derivation puts it, an IR reproducible from its markdown, the old concat path), so its
genre lane installs ``cutan`` from a source checkout and these helpers read both trees.
Where ``cutan`` is absent, or installed from a wheel (no ``examples/``), only this tree
is read, and the tests that need the cut-out scenes are ``genre``-marked anyway.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def corpus_roots() -> list[Path]:
    """``[this repository]`` plus the ``cutan`` source checkout, when installed from one."""
    roots = [ROOT]
    try:
        from cutan.bench import REPO_ROOT
    except ImportError:
        return roots
    if (REPO_ROOT / "examples").is_dir():
        roots.append(REPO_ROOT)
    return roots


def corpus_glob(pattern: str) -> list[Path]:
    """Every file matching ``pattern`` under any corpus root, sorted per root."""
    return [p for root in corpus_roots() for p in sorted(root.glob(pattern))]


def corpus_relative(path: Path) -> str:
    """``path`` relative to the corpus root that holds it, POSIX-spelled (a test id)."""
    for root in corpus_roots():
        if root == path or root in path.parents:
            return path.relative_to(root).as_posix()
    return path.as_posix()
