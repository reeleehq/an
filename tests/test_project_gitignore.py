"""``an.project.gitignored`` reads a ``.gitignore`` line as git does (an#725):
checked against ``git check-ignore`` itself, for ``an``'s own lines and for
every shape a line may take."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from an.project import PROJECT_GITIGNORE, gitignore_matcher, gitignored

_SAMPLE_PATHS = (
    "scene.md",
    "artifacts/render_reports/r.json",
    "artifacts/voice_options/jerry.json.lock",
    "artifacts/voice_options/jerry.json",
    "artifacts/voice_options/sub/x.lock",
    "artifacts/probes/deep/p.png",
    "artifacts/audio/a.wav",
    "deep/x.lock",
    "deep/probes/x.png",
    "a/b/c/d",
    "artifacts/voice_options/a.json",
    "x/foo/y",
    "a",
    "a/z",
    ".env",
    "sub/.env",
    "q/r",
)
_SHAPES = (
    "*.lock",
    "probes",
    "a/*/c",
    "artifacts/v?ice_options/[ab].json",
    "/scene.md",
    "[!b].json",
    "q?r",
    "foo/",
    "a/*",
    ".env",
    "cache//",
)


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
@pytest.mark.parametrize("lines", [PROJECT_GITIGNORE, _SHAPES], ids=["an", "shapes"])
def test_gitignored_agrees_with_git_check_ignore(tmp_path, lines):
    """Each line means what it means to git, for whatever line ``an`` adds
    next (the drift this list once suffered: an#587's lock pattern)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    # bytes, NUL-separated: no newline translation on Windows, no path quoting
    (tmp_path / ".gitignore").write_bytes("".join(f"{line}\n" for line in lines).encode())
    got = subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "core.ignorecase=false"]
        + ["check-ignore", "--no-index", "--stdin", "-z"],
        input="\0".join(_SAMPLE_PATHS).encode() + b"\0",
        capture_output=True,
    )
    ignored = {p for p in got.stdout.decode().split("\0") if p}
    assert {p for p in _SAMPLE_PATHS if gitignored(p, lines=lines)} == ignored


def test_a_line_it_cannot_read_as_git_does_is_refused():
    for line in ("!keep.me", "artifacts/**/x", "# note", "\\*.md", "[^a].txt", "foo ",
                 "[[:alpha:]]x", "", "/"):
        with pytest.raises(ValueError, match="cannot use"):
            gitignore_matcher((line,))
    with pytest.raises(TypeError, match="not one str"):
        gitignored("scene.md", lines="*.lock")
    for rel in ("", "./artifacts/probes/x.png", "artifacts\\probes\\x.png", "a//b", "/a", "a/", "../a"):
        with pytest.raises(ValueError, match="project-relative"):
            gitignored(rel)
