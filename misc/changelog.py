"""One changelog fragment per PR, folded into ``misc/CHANGELOG.md`` (an#469).

Two PRs that each append a line under today's date in ``misc/CHANGELOG.md``
conflict, and GitHub's mergeability check ignores the ``merge=union``
attribute, so parallel PRs serialised on a rebase each. Instead a PR adds
``misc/changelog.d/<YYYY-MM-DD>-<slug>.md`` holding its entry (a line starting
``- ``), a file no other PR touches. The changelog's form is unchanged: dated
``## YYYY-MM-DD`` sections, newest first, entries in a section by file name.

    python misc/changelog.py render   # print the changelog as it reads with the fragments
    python misc/changelog.py fold     # write it into misc/CHANGELOG.md, delete the fragments
    python misc/changelog.py check    # the fragments are well formed (what the test runs)

``fold`` is the one step that edits ``misc/CHANGELOG.md``; run it from the
default branch (a maintainer, or a scheduled job), never from a PR branch.
Standard library only.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHANGELOG = HERE / "CHANGELOG.md"
FRAGMENTS_DIR = HERE / "changelog.d"
#: ``2026-10-27-slug.md``: the date the entry belongs under, then a slug.
FRAGMENT_NAME = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})-[\w.-]+\.md")
SECTION = re.compile(r"## (\d{4}-\d{2}-\d{2})\s*$")


class FragmentError(ValueError):
    """A changelog fragment is not shaped as ``<date>-<slug>.md`` holding ``- `` entries."""


def read_fragments(directory: Path = FRAGMENTS_DIR) -> dict[str, list[tuple[str, str]]]:
    """``{date: [(file name, entry), ...]}`` from ``directory``; entries by file name.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     _ = (Path(d) / "2026-10-27-b.md").write_text("- **B** (an#2).\\n")
    ...     _ = (Path(d) / "2026-10-27-a.md").write_text("- **A** (an#1).\\n")
    ...     {k: [n for n, _ in v] for k, v in read_fragments(Path(d)).items()}
    {'2026-10-27': ['2026-10-27-a.md', '2026-10-27-b.md']}
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for path in sorted(directory.glob("*.md")) if directory.is_dir() else ():
        if path.name == "README.md":
            continue
        match = FRAGMENT_NAME.fullmatch(path.name)
        if match is None:
            raise FragmentError(
                f"{path.name}: name it <YYYY-MM-DD>-<slug>.md (the date it belongs under)"
            )
        entry = path.read_text(encoding="utf-8").strip()
        if not entry.startswith("- ") or "\n## " in entry or entry.startswith("## "):
            raise FragmentError(
                f"{path.name}: a fragment is one entry that starts with '- ' (no heading)"
            )
        out.setdefault(match["date"], []).append((path.name, entry))
    return out


def render(changelog: str, fragments: Mapping[str, Iterable[tuple[str, str]]]) -> str:
    """``changelog`` with each fragment's entries at the top of its date's
    section; where the date has none, a new section before the first older one
    (the changelog reads newest first). Nothing else is touched: a date that
    appears twice, prose between sections, trailing blanks all stay as they are.

    >>> text = "# Changelog\\n\\nIntro.\\n\\n## 2026-10-26\\n- old\\n"
    >>> print(render(text, {"2026-10-27": [("a.md", "- new")]}), end="")
    # Changelog
    <BLANKLINE>
    Intro.
    <BLANKLINE>
    ## 2026-10-27
    - new
    <BLANKLINE>
    ## 2026-10-26
    - old
    >>> print(render(text, {"2026-10-26": [("a.md", "- new")]}), end="")
    # Changelog
    <BLANKLINE>
    Intro.
    <BLANKLINE>
    ## 2026-10-26
    - new
    - old
    >>> render(text, {}) == text
    True
    """
    lines = changelog.split("\n")
    for date in sorted(fragments):
        entries = [entry for _, entry in fragments[date]]
        if not entries:
            continue
        headings = [
            (i, m.group(1))
            for i, line in enumerate(lines)
            if (m := SECTION.match(line))
        ]
        same = next((i for i, d in headings if d == date), None)
        if same is not None:
            lines[same + 1 : same + 1] = entries
            continue
        older = next((i for i, d in headings if d < date), None)
        block = [f"## {date}", *entries, ""]
        if older is not None:
            lines[older:older] = block
        else:
            while lines and lines[-1] == "":
                lines.pop()
            lines += ["", *block[:-1], ""]
    return "\n".join(lines)


def fold(changelog: Path = CHANGELOG, directory: Path = FRAGMENTS_DIR) -> int:
    """Write the fragments into ``changelog`` and delete them; how many were folded."""
    fragments = read_fragments(directory)
    count = sum(len(v) for v in fragments.values())
    if count:
        changelog.write_text(
            render(changelog.read_text(encoding="utf-8"), fragments), encoding="utf-8"
        )
        for entries in fragments.values():
            for name, _ in entries:
                (directory / name).unlink()
    return count


def main(argv: list[str] | None = None) -> int:
    command = (argv if argv is not None else sys.argv[1:] or ["render"])[0]
    if command == "render":
        sys.stdout.write(
            render(CHANGELOG.read_text(encoding="utf-8"), read_fragments())
        )
    elif command == "fold":
        print(f"folded {fold()} fragment(s) into {CHANGELOG.name}")
    elif command == "check":
        read_fragments()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
