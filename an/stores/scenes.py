"""Scenes store — wraps the project's ``scene.md`` + ``ir/scene.json`` pair.

Right now an an project contains exactly one scene ("main"), so this store
exposes only the ``"main"`` key. Future versions can support multi-scene
projects by promoting siblings inside a ``scenes/`` directory.

Reading returns a ``SceneIR``. Writing accepts a ``SceneIR`` (or a dict that
validates as one) and persists the JSON and the Markdown -- the Markdown UPDATED
rather than regenerated (an#275): unchanged content leaves the author's file as it
was, and a change rewrites only the blocks it touches (`an.ir.sync.merge_markdown`).
"""

from __future__ import annotations

import json
import re
from collections.abc import MutableMapping
from pathlib import Path
from typing import Iterator

from an.ir.schema import SceneIR
from an.ir.sync import ir_to_markdown, merge_markdown, scene_from_json_doc
from an.util import _read_text, _write_json, _write_text


class ScenesStore(MutableMapping):
    """`MutableMapping` exposing the scene file pair under a project root.

    Keys: currently always ``"main"``. The store enforces this by raising
    ``KeyError`` for other keys.
    """

    SCENE_KEY = "main"

    def __init__(self, project_dir: str | Path) -> None:
        self._root = Path(project_dir)

    @property
    def md_path(self) -> Path:
        return self._root / "scene.md"

    @property
    def json_path(self) -> Path:
        return self._root / "ir" / "scene.json"

    def __getitem__(self, key: str) -> SceneIR:
        if key != self.SCENE_KEY:
            raise KeyError(key)
        if not self.json_path.exists():
            raise KeyError(key)
        # Migrated on read (an#105): a stored document may predate this build.
        return scene_from_json_doc(
            json.loads(_read_text(self.json_path)), source=self.json_path
        )

    def __setitem__(self, key: str, value: SceneIR | dict) -> None:
        if key != self.SCENE_KEY:
            raise KeyError(f"only the {self.SCENE_KEY!r} key is supported")
        # A DICT goes through the read boundary too (an#105 review): writing a
        # version this build cannot read produced a project `an` refused to open
        # — the store would happily persist `version: "0.0.42"`, and the very
        # next read raised. Symmetric boundaries or none.
        scene = value if isinstance(value, SceneIR) else scene_from_json_doc(value)
        # The markdown FIRST: it can refuse (an action or dialogue sugar no
        # loaded genre can spell), and a refusal must leave the pair as it was,
        # not a new JSON beside a stale md (review-244 N5).
        markdown = ir_to_markdown(scene)
        # The author's file is UPDATED, not regenerated (an#275): unchanged
        # content leaves it byte-for-byte as written, and a change rewrites
        # only the blocks it touches -- never the prose around them.
        existing = _read_text(self.md_path) if self.md_path.exists() else None
        if existing is not None:
            markdown = merge_markdown(existing, scene)
        _write_json(self.json_path, json.loads(scene.model_dump_json()))
        if markdown != existing:
            _write_text(self.md_path, markdown)
        # Equalize mtimes so the JSON wins ties on subsequent sync()s. Pipeline
        # stages (audio, lip-sync) inject rich state into the JSON that the
        # Markdown can't represent — without this, sync() would round-trip
        # md → json and lose them on the next load.
        import os
        import time

        now = time.time()
        os.utime(self.json_path, (now, now + 0.001))
        os.utime(self.md_path, (now, now))

    def patch_shot_durations(self, durations: dict[str, float]) -> None:
        """Set ``duration`` on the named shots WITHOUT regenerating ``scene.md``.

        ``__setitem__`` rewrites the markdown from the IR, which drops every word
        of prose and every comment the IR does not hold. This writes the JSON
        through the read boundary as usual, and patches only each shot's
        ``duration:`` line in the markdown (inserting one into its
        ```` ```yaml shot ```` block, or the block itself, when there is none) —
        what ``an sync --accept-measured`` uses to take a measured duration into
        the authored scene (an#279).
        """
        scene = self[self.SCENE_KEY]
        known = {shot.id for shot in scene.timeline}
        unknown = sorted(set(durations) - known)
        if unknown:
            raise KeyError(f"no shot(s) {unknown} in the scene; it has {sorted(known)}")
        for shot in scene.timeline:
            if shot.id in durations:
                shot.duration = float(durations[shot.id])
        markdown = (
            _read_text(self.md_path) if self.md_path.exists() else ir_to_markdown(scene)
        )
        for shot_id, seconds in durations.items():
            markdown = patch_shot_duration_md(markdown, shot_id, float(seconds))
        _write_json(self.json_path, json.loads(scene.model_dump_json()))
        _write_text(self.md_path, markdown)
        import os
        import time

        now = time.time()
        os.utime(self.json_path, (now, now + 0.001))
        os.utime(self.md_path, (now, now))

    def __delitem__(self, key: str) -> None:
        if key != self.SCENE_KEY:
            raise KeyError(key)
        for p in (self.md_path, self.json_path):
            if p.exists():
                p.unlink()

    def __iter__(self) -> Iterator[str]:
        if self.json_path.exists():
            yield self.SCENE_KEY

    def __len__(self) -> int:
        return 1 if self.json_path.exists() else 0

    def __repr__(self) -> str:
        return f"ScenesStore({str(self._root)!r})"


_SHOT_HEADING = re.compile(r"^## Shot (?P<id>\S+)(?:\s+\([^)]*\))?\s*$")
_FENCE_OPEN_SHOT = re.compile(r"^```yaml shot\s*$")
_DURATION_LINE = re.compile(r"^duration:\s*[^#\n]*?(?P<comment>\s+#.*)?$")


def patch_shot_duration_md(markdown: str, shot_id: str, seconds: float) -> str:
    r"""``markdown`` with shot ``shot_id``'s ``duration:`` set to ``seconds``,
    every other line — prose, comments, formatting — untouched.

    >>> md = "# T\n\nA note.\n\n## Shot a (manim)\n\n```yaml shot\noptions: {source: a}  # the chart\n```\n"
    >>> print(patch_shot_duration_md(md, "a", 3.1))
    # T
    <BLANKLINE>
    A note.
    <BLANKLINE>
    ## Shot a (manim)
    <BLANKLINE>
    ```yaml shot
    duration: 3.1
    options: {source: a}  # the chart
    ```
    <BLANKLINE>
    """
    lines = markdown.split("\n")
    value = (
        f"duration: {seconds:g}"
        if float(f"{seconds:g}") == seconds
        else f"duration: {seconds!r}"
    )
    heading = next(
        (
            i
            for i, ln in enumerate(lines)
            if (m := _SHOT_HEADING.match(ln)) and m["id"] == shot_id
        ),
        None,
    )
    if heading is None:
        raise KeyError(f"scene.md has no `## Shot {shot_id}` heading")
    end = next(
        (i for i in range(heading + 1, len(lines)) if _SHOT_HEADING.match(lines[i])),
        len(lines),
    )
    fence = next(
        (i for i in range(heading + 1, end) if _FENCE_OPEN_SHOT.match(lines[i])), None
    )
    if fence is None:
        lines[heading + 1 : heading + 1] = ["", "```yaml shot", value, "```"]
        return "\n".join(lines)
    close = next((i for i in range(fence + 1, end) if lines[i].startswith("```")), end)
    for i in range(fence + 1, close):
        m = _DURATION_LINE.match(lines[i])
        if m:
            lines[i] = value + (m["comment"] or "")
            return "\n".join(lines)
    lines.insert(fence + 1, value)
    return "\n".join(lines)
