"""The bench corpus: which projects are measured, and what each must actually render.

``expect_visual_kinds`` is not belt-and-braces. Every ``examples/*/assets/`` is
gitignored, and before an#33 a missing character descriptor made the compiler
fall back to the procedural rig with **zero** warnings. The first
cross-architecture capture measured exactly that: three CI runners agreed
perfectly about a picture that was not the picture, and the agreement read as a
clean positive result. It surfaced only because the local machine happened to
hold a *stale* build product and therefore disagreed.

So a fixture declares the render path it must exercise, and the check reads the
scene JSON **the browser actually loaded** — an independent second opinion to
``strict_assets=True``, which trusts the compiler that produced it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Sequence

# Moved to the core (an#279, ADR 0001 decision 7) and re-exported: the fixture
# type, the pinned render knobs and the corpus folder serve the CORE corpus too.
from an.bench.core_corpus import (  # noqa: F401 — re-exported
    BENCH_RENDER_KWARGS,
    CORE_FIXTURES,
    CORPUS_DIRNAME,
    Fixture,
)

#: Per-shot subdirectory naming inside `.an/render_work`, and the staged scene
#: filename. Mirrored from the renderer rather than restated as literals at
#: each use site.
SHOT_DIR_GLOB: str = "shot_*"
FRAMES_DIRNAME: str = "frames"
RUNTIME_DIRNAME: str = "runtime"
STAGED_SCENE_NAME: str = "scene.json"


class CorpusError(RuntimeError):
    """A fixture did not render what it declared."""



#:
#: The cut-out scenes of the original corpus moved to `cutan` (`cutan.bench.CUTOUT_FIXTURES`, an#225); this
#: is the core's: `prop_swap` and the core corpus (`an.bench.core_corpus`).
DFLT_FIXTURES: dict[str, Fixture] = {
    "prop_swap": Fixture(
        path=f"{CORPUS_DIRNAME}/prop_swap",
        expect_visual_kinds=frozenset({"svg_sprite"}),
        golden_frames=(0.0, 0.375),
        golden_note=(
            "a two-state prop swapping mid-shot (an#108): a desk lamp whose "
            "`lamp` asset-set goes `off` -> `on` at t=0.25. What moves between "
            "the goldens is a texture SWAP and nothing else — no transform, no "
            "easing, no interpolation — which is why this scene is worth a row "
            "the other seven cannot provide: every one of them measures a pose "
            "changing continuously, so a regression that broke swap resolution "
            "alone (the runtime resolves two swap properties on one node by "
            "NAME order, and an#87's failure mode was keeping the PREVIOUS "
            "texture in silence) would move no golden anywhere in the corpus. "
            "Frame 9 rather than the mid-frame: at 24 fps the swap lands on "
            "frame 6, so frame 9 is clear of the boundary in a way that does "
            "not depend on how the frame containing t=0.25 rounds."
        ),
    ),
    "stage_pan": CORE_FIXTURES["stage_pan"],
    "path_draw": CORE_FIXTURES["path_draw"],
    **{k: v for k, v in CORE_FIXTURES.items() if k not in ("stage_pan", "path_draw")},
}


def iter_shot_dirs(
    work_dir: Path, *, order: Sequence[str]
) -> Iterator[tuple[str, Path]]:
    """``(shot_id, shot_dir)`` for every rendered shot, in **timeline** order.

    ``order`` is mandatory, and that is the whole point of this signature.
    ``an/render.py`` concatenates ``[r.mp4_path for r in shot_results]`` built
    from ``list(scene.timeline)``, while this function's previous form returned
    ``sorted(work_dir.glob("shot_*"))`` — directory-name order. The two agree
    only when the shot ids happen to sort into timeline order, and when they do
    not, every encode-side metric pairs source frame *i* of one shot against
    decoded frame *i* of another. The ``multi_shot`` fixture's ids (``intro``
    then ``beat``) are chosen so they disagree.

    >>> import tempfile
    >>> from pathlib import Path
    >>> d = Path(tempfile.mkdtemp())
    >>> for name in ("shot_intro", "shot_beat"): (d / name).mkdir()
    >>> [i for i, _ in iter_shot_dirs(d, order=["intro", "beat"])]
    ['intro', 'beat']
    """
    root = Path(work_dir)
    for shot_id in order:
        shot_dir = root / f"shot_{shot_id}"
        if not shot_dir.is_dir():
            raise CorpusError(
                f"the timeline declares shot {shot_id!r} but {shot_dir} does not "
                "exist. The renderer names each shot directory after the shot id, "
                "so a missing one means the render and the timeline disagree."
            )
        yield shot_id, shot_dir


def staged_scene(shot_dir: Path) -> dict:
    """The compiled scene JSON the browser actually loaded, for one shot."""
    path = shot_dir / RUNTIME_DIRNAME / STAGED_SCENE_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def visual_kinds(scene_json: dict) -> set[str]:
    """Every ``visual.kind`` in a staged scene's node tree.

    Read from the staged file rather than re-compiled, so it reports what was
    rendered rather than what a second compile would produce.

    Scoped to ``scene`` and to the ``visual`` key specifically. A sweep for
    every ``kind`` anywhere in the document — which is what this was before —
    also collects an#33's ``asset_resolution`` entries, whose ``kind`` is
    ``"character"`` / ``"environment"``. Those are entity kinds, not visual
    kinds, and mixing them makes the field mean two things at once.

    >>> sorted(visual_kinds({"scene": {"visual": {"kind": "rect"},
    ...                                "children": [{"visual": {"kind": "eye"}}]},
    ...                      "asset_resolution": [{"kind": "character"}]}))
    ['eye', 'rect']
    """
    kinds: set[str] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        visual = node.get("visual")
        if isinstance(visual, dict) and isinstance(visual.get("kind"), str):
            kinds.add(visual["kind"])
        for child in node.get("children") or []:
            walk(child)

    walk(scene_json.get("scene") or {})
    return kinds


def assert_render_path(name: str, fixture: Fixture, kinds: set[str]) -> None:
    """Refuse a capture that did not exercise the path its fixture declares."""
    missing = fixture.expect_visual_kinds - kinds
    if missing:
        raise CorpusError(
            f"fixture {name!r} rendered WITHOUT {sorted(missing)} — it staged "
            f"{sorted(kinds)} instead. Before an#33 a missing character "
            "descriptor made the compiler fall back to the procedural rig "
            "silently, so this capture would have measured a different picture "
            "and filed it as this scene's row."
        )
