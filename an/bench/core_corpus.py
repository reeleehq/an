"""The core corpus: what ``an`` renders with no character and no genre (ADR 0001 decision 7).

Before any module leaves ``an`` for ``cutan`` (P8), the core keeps a pixel gate
of its own: **paths, text, planes, camera and transitions**, rendered by the
stage engine (``an.stage``) with no character, with goldens and contract hashes
of their own. These scenes are :data:`CORE_FIXTURES`:

========== ===================================================================
scene      what it is the gate for
========== ===================================================================
path_draw  paths — dash phase, trim, arrowheads, a StylePack's stroke role
stage_pan  planes and the camera's TRANSLATION — parallax at three depths
text_card  text — overlay words revealed one by one, a world label — under
           the camera's ZOOM and ROLL (the overlay holds still, the world does not)
text_swap  text content over time — a `texts` replacement set swapped twice,
           right-aligned (an#341)
text_counter a counter — one block counting 1 to 30, lowered at compile (an#342)
front_plane a foreground plane, animated and addressed `<env>/<plane>` (an#343)
after_plane a prop placed between two planes under a pan (an#344)
transitions a fade in from black and a DISSOLVE between two stage shots: the
           film's composed frames, which is what is delivered, are the goldens
rig_origin a multi-bone prop placed by its declared ``origin`` (an#338) and
           toppling about it, beside the same rig placed by its bones' extent
rig_rest   a tripod whose legs are ONE drawing splayed by their bones' rest
           rotation (an#339), tilting as a whole with the splay intact
========== ===================================================================

They live beside the cut-out corpus in ``misc/bench/corpus/`` and run in the
same ``an bench`` (the cut-out corpus imports them, in
:mod:`an.bench.corpus`), so they are blessed by the same protocol and their
contract hashes are checked by the same default-leg guard. What makes them the
CORE corpus is what they need: ``tests/test_core_corpus.py`` renders every one
of them with NO GENRE REGISTERED and checks each pinned frame against its bless
record. That they render with no cut-out CODE is proven too, since the move
(an#225): the same tests run with every cut-out module poisoned. The cut-out
corpus lives in ``cutan`` (``cutan.bench``); this module, the scenes and their
goldens stay.

This module is CORE (behind no firewall): the fixture type, the pinned render
knobs, the throwaway copy and the browser-free contract hash moved here from
:mod:`an.bench.corpus` and :mod:`an.bench.capture` (genre), which re-export
them. Nothing here imports the stage at module level.

>>> sorted(CORE_FIXTURES)
['after_plane', 'front_plane', 'path_draw', 'rig_origin', 'rig_rest', 'stage_pan', 'text_card', 'text_counter', 'text_swap', 'transitions']
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

#: Rendering knobs pinned for every bench capture, recorded verbatim into the
#: ledger. NOT flags: a bench whose render knobs vary per invocation produces
#: incomparable rows.
#:
#: ``auto_audio=False`` because audio cannot move a pixel and would otherwise
#: make the frames depend on the audio cache's warm/cold state; ``parallel=1``
#: because a timing-sensitive pool is one more thing to explain if the pixels
#: ever do differ; ``strict_assets=True`` because a stand-in asset renders
#: happily as a DIFFERENT picture (an#33).
BENCH_RENDER_KWARGS: dict[str, Any] = {
    "auto_audio": False,
    "parallel": 1,
    "strict_assets": True,
}


@dataclass(frozen=True, slots=True)
class Fixture:
    """A corpus scene: where it lives, how to build it, what it must render."""

    path: str
    #: Run against the throwaway copy before loading, to regenerate build
    #: products the repo does not track.
    prepare: Callable[[Path], None] | None = None
    #: Visual kinds the staged scene MUST contain — see the module docstring.
    expect_visual_kinds: frozenset = frozenset()
    #: Times (seconds, into the scene's CONCATENATED timeline) at which a
    #: golden frame is blessed. Two per scene, the second chosen so something
    #: has actually moved — `--bless` refuses a pair whose two frames are
    #: pixel-identical, which is not hypothetical: `promote_demo`'s frame 0 and
    #: its `duration/2` frame differ by exactly **zero** pixels.
    golden_frames: tuple[float, ...] = field(default_factory=tuple)
    #: One line saying what moves between the two golden times. Carried as data
    #: because "pick a time where something moved" is a rule that decays into a
    #: habit, and the reason is what a reviewer needs when a golden goes red.
    golden_note: str = ""


#: Where the bench-owned fixtures live. NOT under `examples/`, and the reason
#: is mechanical rather than tidiness: `.gitignore` excludes every
#: `examples/*/assets/`, so a corpus scene that needs committed art cannot live
#: there without a carve-out per scene. `misc/` is not ignored at all.
#:
#: The second reason is that a metrics fixture must **hold still**. These four
#: carry their whole rig as committed files and have no ``prepare`` step, so
#: their pixels are a function of the repo alone — where `promote_demo`'s are a
#: function of `cutan.characters.promote`, and would need re-blessing whenever that
#: changes.
CORPUS_DIRNAME: str = "misc/bench/corpus"


#: The core corpus (see the module docstring).
CORE_FIXTURES: dict[str, Fixture] = {
    "path_draw": Fixture(
        path=f"{CORPUS_DIRNAME}/path_draw",
        expect_visual_kinds=frozenset({"path"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "two stroked paths (an#160, an#161), both dashed and both coloured "
            "by a StylePack's `stroke` role: a marching-ants frame whose "
            "`dash_offset` runs 0 -> 20 px, and a cubic arrow that draws itself "
            "on (`trim_end` 0 -> 1) with its head on the moving tip. What "
            "moves between the goldens is the ROUTE growing (frame 0 shows "
            "none of it) and the frame's dashes sliding 6.7 px along their "
            "path; a regression in trim, in the dash phase, in the "
            "anchored-at-the-path-start rule that keeps a dash from crawling "
            "as the tip advances, or in the pack reaching a path, moves a "
            "golden. Butt caps, so a dash's ends are exact rather than "
            "rounded past their length."
        ),
    ),
    "stage_pan": Fixture(
        path=f"{CORPUS_DIRNAME}/stage_pan",
        expect_visual_kinds=frozenset({"rect"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "three coloured blocks at depths 0.25 / 1.0 / 2.0 under a "
            "zoom-free pan (an#111). What moves between the goldens is the "
            "SEPARATION: the blocks start aligned and end 10 / 40 / 80 px "
            "apart, which is the parallax and nothing else. Frame 8, not the "
            "mid-frame: the camera travels 5 px per frame and the far plane "
            "moves a quarter of that, so only every fourth frame lands every "
            "block on an exact pixel boundary — at any other frame the "
            "anti-aliased edge changes the exact-colour mask's SIZE, and a "
            "centroid measured against a different shape is not a "
            "displacement (the measurement refuses it outright). "
            "Zoom is held constant on purpose: the x = 0 probe that cancels "
            "it in the JSON half does not reach a centroid, which sits at the "
            "plane's own offset."
        ),
    ),
    "text_card": Fixture(
        path=f"{CORPUS_DIRNAME}/text_card",
        expect_visual_kinds=frozenset({"rect", "svg_sprite"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "text under a camera push-in and roll (an#279, the core corpus): "
            "two OVERLAY words fading in one after the other (`word_1` starts "
            "0.125 s after `word_0`) and a WORLD label on a plane block, while "
            "the camera zooms 1.0 -> 1.3 and rolls 0.12 rad. What moves between "
            "the goldens: the words' alpha (frame 0 shows neither), the label "
            "and block growing and turning with the camera, and the overlay "
            "title NOT turning — a regression that put overlay text in the "
            "world, broke per-word addressing or the camera's zoom/roll moves "
            "a golden. The face is Pillow's embedded Aileron, so the glyphs "
            "do not depend on the machine's fonts."
        ),
    ),
    "text_swap": Fixture(
        path=f"{CORPUS_DIRNAME}/text_swap",
        expect_visual_kinds=frozenset({"rect", "svg_sprite"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "a text block's CONTENT changing within one shot (an#341): one "
            "right-aligned `unit: block` label whose `texts` set is swapped "
            'twice, "Day 1" -> "Day 12" at 0.125 s (the entity-level `set '
            'day text d12`) -> "Day 300" at 0.25 s (the `day/block_0` path). '
            "What moves between the goldens is the string, growing LEFTWARDS "
            "from a fixed right edge: a regression in the swap set, in the "
            "per-key geometry anchored on the `align` edge, or in the "
            "entity-level fan-out moves a golden."
        ),
    ),
    "text_counter": Fixture(
        path=f"{CORPUS_DIRNAME}/text_counter",
        expect_visual_kinds=frozenset({"rect", "svg_sprite"}),
        golden_frames=(0.0, 12 / 24),
        golden_note=(
            "a calendar counting 1 to 30 with ONE text block (an#342): a "
            "right-aligned `counter: {format: '{d}', start: 1}` under one linear "
            "`tween day value -> 30` over 1 s, lowered at compile to a replacement "
            "set of the strings the frames show. Frame 0 shows 1; frame 12's "
            "value is exactly 15.5, which nearest-half-even rounding shows as 16 "
            "(15 would mean ties away from even, 15/17 a sampling or set-time "
            "shift). A regression in the sampling grid, the half-frame set "
            "time, the rounding or the right-edge geometry moves a golden."
        ),
    ),
    "front_plane": Fixture(
        path=f"{CORPUS_DIRNAME}/front_plane",
        expect_visual_kinds=frozenset({"rect", "svg_sprite"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "an environment cut by `characters_after` with an ANIMATED "
            "foreground plane (an#343): `stage` draws `sky` and `hill` behind a "
            "world text label and `rail` in front of it, in its own container "
            "with `scope: stage`, so the rail is addressed `stage/rail` (never "
            "`stage__front/rail`) and its `y` tween rises from 60 to 0 over the "
            "label. What moves between the goldens is the rail crossing the "
            "label: a regression in the runtime's scoped indexing (the channel "
            "would name nothing and the load throws), in the cut, or in the "
            "draw order moves a golden."
        ),
    ),
    "after_plane": Fixture(
        path=f"{CORPUS_DIRNAME}/after_plane",
        expect_visual_kinds=frozenset({"rect", "svg_sprite"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "a prop placed BETWEEN two planes under a pan (an#344): a far sky "
            "(depth 0.25), a disc with `stage.after: set/sky`, then a wall in "
            "two pieces with a window gap and a sill, all at depth 1.0, while "
            "the camera pans 60 px. The disc is drawn behind the walls and "
            "rides the sky's parallax through its band wrapper: between the "
            "goldens the walls move 40 px and the sky and disc 10 px. A "
            "regression in the draw order (the disc over the wall), in the "
            "wrapper's compensation (the disc sliding against the sky), or "
            "in the band containers' addressing moves a golden."
        ),
    ),
    "transitions": Fixture(
        path=f"{CORPUS_DIRNAME}/transitions",
        expect_visual_kinds=frozenset({"rect", "path"}),
        golden_frames=(2 / 24, 9 / 24, 15 / 24),
        golden_note=(
            "the delivered film's COMPOSED frames (an#279, the core corpus): "
            "`dusk` fades in from black over 0.25 s, then `dawn` dissolves in "
            "over 0.25 s (frames 6-11 are the blend; the film is 12 + 12 - 6 = "
            "18 frames). Frame 2 is mid-fade, frame 9 mid-dissolve (both "
            "pictures at once), frame 15 `dawn` alone with its arrow. A "
            "regression in the fade colour, the dissolve weights, the overlap "
            "arithmetic or the order of the shots moves a golden. The only "
            "fixture measured on the film's frames rather than the shots' — "
            "what the delivered mp4 shows (an.bench.capture's film segment)."
        ),
    ),
    "rig_origin": Fixture(
        path=f"{CORPUS_DIRNAME}/rig_origin",
        expect_visual_kinds=frozenset({"svg_sprite"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "two copies of one three-bone signpost rig (base, post, sign) at "
            "the same `stage.at` height (an#338): `footed` declares its "
            "`origin` at the foot of its base, so its foot stands ON the "
            "placement line; `centred` declares none, so the middle of its "
            "bones' extent lands there and it hangs lower. `footed` tweens "
            "`rotation` 0 -> -0.4 rad, which turns it about the declared "
            "origin: between the goldens its sign swings left while its foot "
            "does not move, and `centred` does not move at all. A regression "
            "that ignored `origin` (both posts at one height), placed parts "
            "about the wrong point, or broke the shared rig builder moves a "
            "golden."
        ),
    ),
    "rig_rest": Fixture(
        path=f"{CORPUS_DIRNAME}/rig_rest",
        expect_visual_kinds=frozenset({"svg_sprite"}),
        golden_frames=(0.0, 8 / 24),
        golden_note=(
            "a tripod prop whose three legs are ONE drawing on three bones "
            "with `rotation_deg` 22 / 0 / -22 (an#339): the splay is the bones' "
            "rest pose, not pixels. The whole tripod tweens `rotation` 0 -> 0.3 "
            "rad about its declared origin (the centre foot), and the splayed "
            "legs ride it: at frame 8 the rig is tilted 0.2 rad with the splay "
            "intact. A regression that dropped the rest pose (three parallel "
            "legs), applied it twice, or let the entity's rotation replace a "
            "leg's instead of composing with it moves a golden."
        ),
    ),
}


#: Copied for the render, but never these: they are the previous render's
#: output, and one of them silently extends this one's frame sequence.
#: Matched on the **basename**, at any depth — that is exactly what
#: ``shutil.ignore_patterns`` does, and it is why ``artifacts/shots`` cannot be
#: spelled here. See :data:`IGNORED_RELPATHS_ON_COPY`.
IGNORED_ON_COPY: tuple[str, ...] = (".an", "output", ".anima")

#: Excluded by their path **relative to the project root**, POSIX-spelled.
#: ``mall["shots"]`` is ``<project>/artifacts/shots``, and ``artifacts/``
#: itself is kept on purpose — it holds the audio cache, whose warm/cold state
#: this module records rather than destroys.
#:
#: Neither spelling belongs in :data:`IGNORED_ON_COPY`, and **both fail
#: silently**. ``shutil.ignore_patterns`` returns a closure handed the NAMES
#: inside one directory, which it ``fnmatch.filter``s — so ``"artifacts/shots"``
#: can never match anything (no name contains a separator) and a bare
#: ``"shots"`` would delete every directory of that name **anywhere** in the
#: tree, a character rig's included.
IGNORED_RELPATHS_ON_COPY: tuple[str, ...] = ("artifacts/shots",)

#: Where the renderer leaves its per-shot working tree inside the project.
RENDER_WORK_RELPATH: str = ".an/render_work"

#: How a shot's frames are named on disk. One constant rather than the literal
#: repeated at each glob site.
FRAME_PNG_GLOB: str = "frame_*.png"


class CaptureError(RuntimeError):
    """A capture could not produce something the metrics need."""


def _ignore_for(fixture_dir: Path):
    """``copytree``'s ``ignore``, for basenames **and** project-relative paths.

    ``copytree`` calls this once per directory with ``(that directory, the
    names in it)``, so a path-shaped exclusion has to be reconstructed from the
    directory it is handed — which is precisely why ``shutil.ignore_patterns``
    cannot express one, and why asking it to do so is a silent no-op rather
    than an error.
    """
    by_name = shutil.ignore_patterns(*IGNORED_ON_COPY)

    def ignore(path: str, names: list[str]) -> set[str]:
        try:
            here = Path(path).relative_to(fixture_dir).as_posix()
        except ValueError as e:
            # Never seen: `copytree` builds every path it passes here by
            # joining onto the one it was given. Raised rather than quietly
            # degrading to basenames-only, because under-excluding is the
            # defect this function exists to fix and it leaves no trace.
            raise CaptureError(
                f"stage_copy was asked about {path!r}, which is not under the "
                f"fixture root {fixture_dir}, so the path-relative exclusions "
                f"{IGNORED_RELPATHS_ON_COPY} could not be applied to it"
            ) from e
        prefix = "" if here == "." else f"{here}/"
        return set(by_name(path, names)) | {
            n for n in names if prefix + n in IGNORED_RELPATHS_ON_COPY
        }

    return ignore


def stage_copy(fixture_dir: Path, base: Path) -> Path:
    """Copy a fixture into ``base``, leaving the previous render behind.

    Split out of :func:`capture_fixture` so the exclusion is testable without
    rendering anything — which matters, because the failure it prevents is
    silent. ``frames/`` is never cleared and ffmpeg's image2 demuxer reads the
    contiguous ``frame_%06d.png`` run from 0, so a longer previous render is
    appended to this one's source leg and to nothing else.

    Two kinds of exclusion, because one kind cannot say both things:
    :data:`IGNORED_ON_COPY` by basename at any depth, and
    :data:`IGNORED_RELPATHS_ON_COPY` by path from the project root — which is
    the only way to drop ``artifacts/shots`` while keeping ``artifacts/audio``.
    """
    base.mkdir(parents=True, exist_ok=True)
    work_copy = base / fixture_dir.name
    if work_copy.exists():
        shutil.rmtree(work_copy)
    shutil.copytree(fixture_dir, work_copy, ignore=_ignore_for(fixture_dir))
    return work_copy


def compiled_contract_sha256(fixture: Fixture, *, repo_root: Path) -> str:
    """The ``scene_contract_sha256`` a render of ``fixture`` would record — no browser.

    Compiles every timeline shot the way the cutout renderer does (the scene's
    size, fps, style pack, default easing and stepped-timing policy, with
    ``strict_assets`` as the bench sets it) in a throwaway copy, and hashes the
    documents. It is the default-leg twin of :func:`capture_fixture`: the
    contract hash is a function of the compiled JSON alone, so the guards that
    check it — against the newest ledger row and against each golden's bless
    record — run on every PR, not only in the labelled browser lane.

    It is the contract of a bench render, which passes no overrides: a render
    given its own ``step_hz``, fps or resolution compiles something else.
    """
    from an.stage.compile import compile_shot, style_pack_for
    from an.stage.serialize import to_dict
    from an.bench.contract import scenes_contract_sha256
    from an.ir.schema import resolve_step_hz
    from an.project import load

    with tempfile.TemporaryDirectory(prefix="an-contract-") as tmp:
        work = stage_copy(Path(repo_root) / fixture.path, Path(tmp))
        if fixture.prepare is not None:
            fixture.prepare(work)
        project = load(work)
        meta = project.scene.meta
        style_pack = style_pack_for(meta, project.mall.get("styles") or {})
        docs = [
            to_dict(
                compile_shot(
                    shot,
                    mall=project.mall,
                    fps=int(round(meta.fps)),
                    width=meta.resolution.width,
                    height=meta.resolution.height,
                    strict_assets=BENCH_RENDER_KWARGS["strict_assets"],
                    step_hz=resolve_step_hz(shot, meta.step_hz),
                    style_pack=style_pack,
                    default_easing=meta.default_easing,
                )
            )
            for shot in project.scene.timeline
        ]
    return scenes_contract_sha256(docs)


#: The id the bench gives an ASSEMBLED film's frames (transitions, a sound
#: layer) when it measures them as one segment — what the delivered mp4 shows.
FILM_SEGMENT_ID: str = "film"

#: Where an assembled scene's composed frames are written, under the render's
#: work directory, by :func:`compose_film_frames` (the film itself is a concat
#: of segments and never holds them, an#260).
FILM_FRAMES_RELPATH: str = "film_frames"


def frames_dir_for(work_dir: Path, shot_id: str) -> Path:
    """Where a render left the frames of ``shot_id`` (or of the composed film).

    >>> frames_dir_for(Path("w"), "film").as_posix(), frames_dir_for(Path("w"), "a").as_posix()
    ('w/film_frames', 'w/shot_a/frames')
    """
    if shot_id == FILM_SEGMENT_ID:
        return Path(work_dir) / FILM_FRAMES_RELPATH
    from an.engines.frame_stage import SHOT_WORKSPACE_PATTERN

    return Path(work_dir) / SHOT_WORKSPACE_PATTERN.format(shot_id=shot_id) / "frames"


def compose_film_frames(scene: Any, work_dir: Path) -> Path | None:
    """An assembled scene's composed frames, written under ``work_dir`` from its
    shots' frames (:func:`an.assemble.write_film_frames`); ``None`` for a scene
    that is a plain concatenation of its shots."""
    from an.assemble import film_timeline, needs_assembly, write_film_frames
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

    fps = scene.meta.fps
    if not needs_assembly(scene, fps=fps):
        return None
    dirs = [frames_dir_for(work_dir, shot.id) for shot in scene.timeline]
    out = Path(work_dir) / FILM_FRAMES_RELPATH
    write_film_frames(
        film_timeline(list(scene.timeline), fps=fps),
        lambda i, j: dirs[i] / (DEFAULT_FRAME_PNG_PATTERN % j),
        out,
    )
    return out


def render_fixture(fixture: Fixture, *, repo_root: Path, base: Path) -> Path:
    """Render ``fixture`` cold, the way the bench does, in a copy under ``base``.

    Through the core API only (``an.project.load`` + ``an.render.render``) —
    no bench capture code — so it runs with the cut-out genre absent. Returns
    the render's work directory.
    """
    from an.project import load
    from an.render import render

    work = stage_copy(Path(repo_root) / fixture.path, Path(base))
    if fixture.prepare is not None:
        fixture.prepare(work)
    project = load(work)
    render(project, **BENCH_RENDER_KWARGS, incremental=False)
    compose_film_frames(project.scene, work / RENDER_WORK_RELPATH)
    return work / RENDER_WORK_RELPATH


def golden_agreement(
    name: str, work_dir: Path, *, chromium_build: str, root: Path | None = None
) -> dict[str, tuple[str, str]]:
    """``{frame key: (blessed sha256, today's sha256)}`` for every frame the
    committed bless record of ``name`` pins, read from a render's work dir.

    Decoded pixels, never file bytes (``an.bench.golden``'s criterion).
    """
    from an.bench.golden import load_manifest, pixels_sha256
    from an.bench.png import read_png
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN

    record = load_manifest(name, chromium_build, root=root)
    if record is None:
        raise CaptureError(
            f"no bless record for {name!r} at Chromium {chromium_build}: bless it "
            f'(`an bench --scenes {name} --bless "<why>"`)'
        )
    out = {}
    for frame in record["frames"]:
        png = frames_dir_for(work_dir, frame["shot_id"]) / (
            DEFAULT_FRAME_PNG_PATTERN % frame["local_index"]
        )
        out[frame["frame_key"]] = (frame["sha256"], pixels_sha256(read_png(png)))
    return out
