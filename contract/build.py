"""Build the data-only contract package (ADR 0006, an#261) from the generated contract files.

The package is ``@thorwhalen/an-contract`` (a working name the maintainer may
change in ``package.json`` before the first publish). It carries nothing but the
contract data ``an`` generates from its registries into ``an/data/timing/``
(``easing.json``, ``kinds.json``, ``timeline.schema.json``,
``compiled.schema.json``, ``timing_vectors.json``, ``vocabulary.json``), plus
this folder's ``package.json`` and ``README.md`` and the repository's licence.
Standard library only, so the publish workflow needs nothing but Python and npm.

Commands (run from anywhere)::

    python contract/build.py build [--out DIR]        # stage the package (default contract/dist)
    python contract/build.py check                    # is the recorded version still right?
    python contract/build.py bump --level minor       # a contract file changed: record it
    python contract/build.py bump --to 1.0.0

**The version tracks the contract, not ``an``.** ``contract.lock.json`` records
the SHA-256 of each contract file (line endings normalised) at the version in
``package.json``. A contract file that changed without a recorded version bump
fails ``check`` (and the test that runs it), so a release of ``an`` that leaves
the contract alone publishes nothing and a contract change cannot ship under an
old version. Bump levels follow the contract's compatibility rules: additive (a
new easing, field kind or vocabulary entry) is ``minor``; a changed meaning of
an existing name is ``major`` and is a gated kernel change (ADR 0006
decision 3).

The files are copied, never edited: the staged ``package.json`` differs from
the committed one only by the ``exports`` map, listed from the data files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

__all__ = [
    "bump",
    "changed_files",
    "check",
    "data_files",
    "digests",
    "main",
    "stage",
]

ROOT: Path = Path(__file__).resolve().parents[1]
PACKAGE_DIR: Path = ROOT / "contract"
DATA_DIR: Path = ROOT / "an" / "data" / "timing"
DFLT_OUT: Path = PACKAGE_DIR / "dist"
LOCK_FILE: Path = PACKAGE_DIR / "contract.lock.json"
PACKAGE_JSON: Path = PACKAGE_DIR / "package.json"
#: Hand-written package files, copied verbatim (the licence comes from the repo root).
PACKAGE_DOCS: tuple[tuple[Path, str], ...] = (
    (PACKAGE_DIR / "README.md", "README.md"),
    (ROOT / "LICENSE", "LICENSE"),
)
LEVELS: tuple[str, ...] = ("patch", "minor", "major")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def data_files(directory: Path = DATA_DIR) -> list[Path]:
    """The contract's data files: every ``*.json`` in the generated folder, sorted."""
    return sorted(directory.glob("*.json"))


def _normalised(path: Path) -> bytes:
    """A file's bytes with line endings as git stores them (a Windows checkout may differ)."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def digests(directory: Path = DATA_DIR) -> dict[str, str]:
    """``{file name: sha256}`` of the contract files."""
    return {
        p.name: hashlib.sha256(_normalised(p)).hexdigest()
        for p in data_files(directory)
    }


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj) -> None:
    path.write_bytes(
        (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )


def recorded() -> dict[str, str]:
    """The digests the lock recorded at the current version."""
    return _read_json(LOCK_FILE)["files"]


def version() -> str:
    return _read_json(PACKAGE_JSON)["version"]


def changed_files(directory: Path = DATA_DIR) -> list[str]:
    """Contract files added, removed or changed since the lock recorded them."""
    now, then = digests(directory), recorded()
    return sorted(n for n in now.keys() | then.keys() if now.get(n) != then.get(n))


def check(directory: Path = DATA_DIR) -> list[str]:
    """Problems with the recorded version (empty: the version matches the files)."""
    problems = []
    if not SEMVER.match(version()):
        problems.append(f"package.json version {version()!r} is not MAJOR.MINOR.PATCH")
    changed = changed_files(directory)
    if changed:
        problems.append(
            f"contract files changed since version {version()} was recorded: {changed}; "
            "run `python contract/build.py bump --level minor` (additive) or `--level major` "
            "(a changed meaning), and commit the lock and package.json"
        )
    return problems


def stage(out: Path = DFLT_OUT, *, directory: Path = DATA_DIR) -> list[str]:
    """Stage the package under ``out`` (emptied first); returns the staged file names.

    The data files are copied byte for byte (line endings normalised); the
    committed ``package.json`` gains an ``exports`` map listing them.
    """
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    names = []
    for path in data_files(directory):
        (out / path.name).write_bytes(_normalised(path))
        names.append(path.name)
    for source, name in PACKAGE_DOCS:
        shutil.copyfile(source, out / name)
        names.append(name)
    manifest = _read_json(PACKAGE_JSON)
    manifest["exports"] = {f"./{n}": f"./{n}" for n in names if n.endswith(".json")}
    manifest["exports"]["./package.json"] = "./package.json"
    _write_json(out / "package.json", manifest)
    return sorted(names + ["package.json"])


def _bumped(current: str, level: str) -> str:
    major, minor, patch = (int(x) for x in SEMVER.match(current).groups())
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def bump(
    *, level: str | None = None, to: str | None = None, directory: Path = DATA_DIR
) -> str:
    """Record the contract files' current digests under a new version; returns it."""
    if (level is None) == (to is None):
        raise ValueError("give exactly one of level= and to=")
    if level is not None and level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    new = to if to is not None else _bumped(version(), level)
    if not SEMVER.match(new):
        raise ValueError(f"{new!r} is not MAJOR.MINOR.PATCH")
    manifest = _read_json(PACKAGE_JSON)
    manifest["version"] = new
    _write_json(PACKAGE_JSON, manifest)
    _write_json(LOCK_FILE, {"files": digests(directory)})
    return new


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build_p = sub.add_parser("build", help="stage the package")
    build_p.add_argument("--out", type=Path, default=DFLT_OUT)
    sub.add_parser(
        "check", help="fail if a contract file changed without a version bump"
    )
    bump_p = sub.add_parser("bump", help="record the current files under a new version")
    group = bump_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--level", choices=LEVELS)
    group.add_argument("--to")
    args = parser.parse_args(argv)
    if args.command == "build":
        problems = check()
        for line in problems:
            print(line)
        if problems:
            return 1
        names = stage(args.out)
        print(f"staged {len(names)} files for version {version()} in {args.out}")
        return 0
    if args.command == "check":
        problems = check()
        for line in problems:
            print(line)
        return 1 if problems else 0
    print(f"version {bump(level=args.level, to=args.to)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
