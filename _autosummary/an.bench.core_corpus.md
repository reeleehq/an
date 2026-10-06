# an.bench.core_corpus

The core corpus: what `an` renders with no character and no genre (ADR 0001 decision 7).

Before any module leaves `an` for `cutan` (P8), the core keeps a pixel gate
of its own: **paths, text, planes, camera and transitions**, rendered by the
stage engine (`an.stage`) with no character, with goldens and contract hashes
of their own. These scenes are [`CORE_FIXTURES`](#an.bench.core_corpus.CORE_FIXTURES):

They live beside the cut-out corpus in `misc/bench/corpus/` and run in the
same `an bench` (the cut-out corpus imports them, in
[`an.bench.corpus`](an.bench.corpus.md#module-an.bench.corpus)), so they are blessed by the same protocol and their
contract hashes are checked by the same default-leg guard. What makes them the
CORE corpus is what they need: `tests/test_core_corpus.py` renders every one
of them with NO GENRE REGISTERED and checks each pinned frame against its bless
record. That they render with no cut-out CODE is proven too, since the move
(an#225): the same tests run with every cut-out module poisoned. The cut-out
corpus lives in `cutan` (`cutan.bench`); this module, the scenes and their
goldens stay.

This module is CORE (behind no firewall): the fixture type, the pinned render
knobs, the throwaway copy and the browser-free contract hash moved here from
[`an.bench.corpus`](an.bench.corpus.md#module-an.bench.corpus) and [`an.bench.capture`](an.bench.capture.md#module-an.bench.capture) (genre), which re-export
them. Nothing here imports the stage at module level.

```pycon
>>> sorted(CORE_FIXTURES)
['after_plane', 'front_plane', 'path_draw', 'rig_origin', 'stage_pan', 'text_card', 'text_counter', 'text_swap', 'transitions']
```

### Module Attributes

| [`BENCH_RENDER_KWARGS`](#an.bench.core_corpus.BENCH_RENDER_KWARGS)      | Rendering knobs pinned for every bench capture, recorded verbatim into the ledger.                                                                                                                                                           |
|---------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CORPUS_DIRNAME`](#an.bench.core_corpus.CORPUS_DIRNAME)           | Where the bench-owned fixtures live.                                                                                                                                                                                                         |
| [`CORE_FIXTURES`](#an.bench.core_corpus.CORE_FIXTURES)            | The core corpus (see the module docstring).                                                                                                                                                                                                  |
| [`IGNORED_ON_COPY`](#an.bench.core_corpus.IGNORED_ON_COPY)          | they are the previous render's output, and one of them silently extends this one's frame sequence.                                                                                                                                           |
| [`IGNORED_RELPATHS_ON_COPY`](#an.bench.core_corpus.IGNORED_RELPATHS_ON_COPY) | Excluded by their path **relative to the project root**, POSIX-spelled.                                                                                                                                                                      |
| [`RENDER_WORK_RELPATH`](#an.bench.core_corpus.RENDER_WORK_RELPATH)      | Where the renderer leaves its per-shot working tree inside the project.                                                                                                                                                                      |
| [`FRAME_PNG_GLOB`](#an.bench.core_corpus.FRAME_PNG_GLOB)           | How a shot's frames are named on disk.                                                                                                                                                                                                       |
| [`FILM_SEGMENT_ID`](#an.bench.core_corpus.FILM_SEGMENT_ID)          | The id the bench gives an ASSEMBLED film's frames (transitions, a sound layer) when it measures them as one segment — what the delivered mp4 shows.                                                                                          |
| [`FILM_FRAMES_RELPATH`](#an.bench.core_corpus.FILM_FRAMES_RELPATH)      | Where an assembled scene's composed frames are written, under the render's work directory, by [`compose_film_frames()`](#an.bench.core_corpus.compose_film_frames) (the film itself is a concat of segments and never holds them, an#260). |

### Functions

| [`compiled_contract_sha256`](#an.bench.core_corpus.compiled_contract_sha256)(fixture, \*, repo_root)   | The `scene_contract_sha256` a render of `fixture` would record — no browser.                                                                                                                                                                                           |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`compose_film_frames`](#an.bench.core_corpus.compose_film_frames)(scene, work_dir)               | An assembled scene's composed frames, written under `work_dir` from its shots' frames ([`an.assemble.write_film_frames()`](an.assemble.md#an.assemble.write_film_frames)); `None` for a scene that is a plain concatenation of its shots. |
| [`frames_dir_for`](#an.bench.core_corpus.frames_dir_for)(work_dir, shot_id)                  | Where a render left the frames of `shot_id` (or of the composed film).                                                                                                                                                                                                 |
| [`golden_agreement`](#an.bench.core_corpus.golden_agreement)(name, work_dir, \*, ...[, root])  | `{frame key: (blessed sha256, today's sha256)}` for every frame the committed bless record of `name` pins, read from a render's work dir.                                                                                                                              |
| [`render_fixture`](#an.bench.core_corpus.render_fixture)(fixture, \*, repo_root, base)       | Render `fixture` cold, the way the bench does, in a copy under `base`.                                                                                                                                                                                                 |
| [`stage_copy`](#an.bench.core_corpus.stage_copy)(fixture_dir, base)                      | Copy a fixture into `base`, leaving the previous render behind.                                                                                                                                                                                                        |

### Classes

| [`Fixture`](#an.bench.core_corpus.Fixture)(path[, prepare, ...])   | A corpus scene: where it lives, how to build it, what it must render.   |
|----------------------------------------------------------------------------------|-------------------------------------------------------------------------|

### Exceptions

| [`CaptureError`](#an.bench.core_corpus.CaptureError)   | A capture could not produce something the metrics need.   |
|-----------------------------------------------------------------|-----------------------------------------------------------|

### an.bench.core_corpus.BENCH_RENDER_KWARGS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]* *= {'auto_audio': False, 'parallel': 1, 'strict_assets': True}*

Rendering knobs pinned for every bench capture, recorded verbatim into the
ledger. NOT flags: a bench whose render knobs vary per invocation produces
incomparable rows.

`auto_audio=False` because audio cannot move a pixel and would otherwise
make the frames depend on the audio cache’s warm/cold state; `parallel=1`
because a timing-sensitive pool is one more thing to explain if the pixels
ever do differ; `strict_assets=True` because a stand-in asset renders
happily as a DIFFERENT picture (an#33).

### an.bench.core_corpus.CORE_FIXTURES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Fixture](#an.bench.core_corpus.Fixture)]* *= {'after_plane': Fixture(path='misc/bench/corpus/after_plane', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="a prop placed BETWEEN two planes under a pan (an#344): a far sky (depth 0.25), a disc with \`stage.after: set/sky\`, then a wall in two pieces with a window gap and a sill, all at depth 1.0, while the camera pans 60 px. The disc is drawn behind the walls and rides the sky's parallax through its band wrapper: between the goldens the walls move 40 px and the sky and disc 10 px. A regression in the draw order (the disc over the wall), in the wrapper's compensation (the disc sliding against the sky), or in the band containers' addressing moves a golden."), 'front_plane': Fixture(path='misc/bench/corpus/front_plane', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="an environment cut by \`characters_after\` with an ANIMATED foreground plane (an#343): \`stage\` draws \`sky\` and \`hill\` behind a world text label and \`rail\` in front of it, in its own container with \`scope: stage\`, so the rail is addressed \`stage/rail\` (never \`stage_\_front/rail\`) and its \`y\` tween rises from 60 to 0 over the label. What moves between the goldens is the rail crossing the label: a regression in the runtime's scoped indexing (the channel would name nothing and the load throws), in the cut, or in the draw order moves a golden."), 'path_draw': Fixture(path='misc/bench/corpus/path_draw', prepare=None, expect_visual_kinds=frozenset({'path'}), golden_frames=(0.0, 0.3333333333333333), golden_note="two stroked paths (an#160, an#161), both dashed and both coloured by a StylePack's \`stroke\` role: a marching-ants frame whose \`dash_offset\` runs 0 -> 20 px, and a cubic arrow that draws itself on (\`trim_end\` 0 -> 1) with its head on the moving tip. What moves between the goldens is the ROUTE growing (frame 0 shows none of it) and the frame's dashes sliding 6.7 px along their path; a regression in trim, in the dash phase, in the anchored-at-the-path-start rule that keeps a dash from crawling as the tip advances, or in the pack reaching a path, moves a golden. Butt caps, so a dash's ends are exact rather than rounded past their length."), 'rig_origin': Fixture(path='misc/bench/corpus/rig_origin', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="two copies of one three-bone signpost rig (base, post, sign) at the same \`stage.at\` height (an#338): \`footed\` declares its \`origin\` at the foot of its base, so its foot stands ON the placement line; \`centred\` declares none, so the middle of its bones' extent lands there and it hangs lower. \`footed\` tweens \`rotation\` 0 -> -0.4 rad, which turns it about the declared origin: between the goldens its sign swings left while its foot does not move, and \`centred\` does not move at all. A regression that ignored \`origin\` (both posts at one height), placed parts about the wrong point, or broke the shared rig builder moves a golden."), 'stage_pan': Fixture(path='misc/bench/corpus/stage_pan', prepare=None, expect_visual_kinds=frozenset({'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="three coloured blocks at depths 0.25 / 1.0 / 2.0 under a zoom-free pan (an#111). What moves between the goldens is the SEPARATION: the blocks start aligned and end 10 / 40 / 80 px apart, which is the parallax and nothing else. Frame 8, not the mid-frame: the camera travels 5 px per frame and the far plane moves a quarter of that, so only every fourth frame lands every block on an exact pixel boundary — at any other frame the anti-aliased edge changes the exact-colour mask's SIZE, and a centroid measured against a different shape is not a displacement (the measurement refuses it outright). Zoom is held constant on purpose: the x = 0 probe that cancels it in the JSON half does not reach a centroid, which sits at the plane's own offset."), 'text_card': Fixture(path='misc/bench/corpus/text_card', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="text under a camera push-in and roll (an#279, the core corpus): two OVERLAY words fading in one after the other (\`word_1\` starts 0.125 s after \`word_0\`) and a WORLD label on a plane block, while the camera zooms 1.0 -> 1.3 and rolls 0.12 rad. What moves between the goldens: the words' alpha (frame 0 shows neither), the label and block growing and turning with the camera, and the overlay title NOT turning — a regression that put overlay text in the world, broke per-word addressing or the camera's zoom/roll moves a golden. The face is Pillow's embedded Aileron, so the glyphs do not depend on the machine's fonts."), 'text_counter': Fixture(path='misc/bench/corpus/text_counter', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.5), golden_note="a calendar counting 1 to 30 with ONE text block (an#342): a right-aligned \`counter: {format: '{d}', start: 1}\` under one linear \`tween day value -> 30\` over 1 s, lowered at compile to a replacement set of the strings the frames show. Frame 0 shows 1; frame 12's value is exactly 15.5, which nearest-half-even rounding shows as 16 (15 would mean ties away from even, 15/17 a sampling or set-time shift). A regression in the sampling grid, the half-frame set time, the rounding or the right-edge geometry moves a golden."), 'text_swap': Fixture(path='misc/bench/corpus/text_swap', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note='a text block\\'s CONTENT changing within one shot (an#341): one right-aligned \`unit: block\` label whose \`texts\` set is swapped twice, "Day 1" -> "Day 12" at 0.125 s (the entity-level \`set day text d12\`) -> "Day 300" at 0.25 s (the \`day/block_0\` path). What moves between the goldens is the string, growing LEFTWARDS from a fixed right edge: a regression in the swap set, in the per-key geometry anchored on the \`align\` edge, or in the entity-level fan-out moves a golden.'), 'transitions': Fixture(path='misc/bench/corpus/transitions', prepare=None, expect_visual_kinds=frozenset({'rect', 'path'}), golden_frames=(0.08333333333333333, 0.375, 0.625), golden_note="the delivered film's COMPOSED frames (an#279, the core corpus): \`dusk\` fades in from black over 0.25 s, then \`dawn\` dissolves in over 0.25 s (frames 6-11 are the blend; the film is 12 + 12 - 6 = 18 frames). Frame 2 is mid-fade, frame 9 mid-dissolve (both pictures at once), frame 15 \`dawn\` alone with its arrow. A regression in the fade colour, the dissolve weights, the overlap arithmetic or the order of the shots moves a golden. The only fixture measured on the film's frames rather than the shots' — what the delivered mp4 shows (an.bench.capture's film segment).")}*

The core corpus (see the module docstring).

### an.bench.core_corpus.CORPUS_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'misc/bench/corpus'*

Where the bench-owned fixtures live. NOT under `examples/`, and the reason
is mechanical rather than tidiness: `.gitignore` excludes every
`examples/*/assets/`, so a corpus scene that needs committed art cannot live
there without a carve-out per scene. `misc/` is not ignored at all.

The second reason is that a metrics fixture must **hold still**. These four
carry their whole rig as committed files and have no `prepare` step, so
their pixels are a function of the repo alone — where `promote_demo`’s are a
function of `cutan.characters.promote`, and would need re-blessing whenever that
changes.

### *exception* an.bench.core_corpus.CaptureError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A capture could not produce something the metrics need.

### an.bench.core_corpus.FILM_FRAMES_RELPATH *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'film_frames'*

Where an assembled scene’s composed frames are written, under the render’s
work directory, by [`compose_film_frames()`](#an.bench.core_corpus.compose_film_frames) (the film itself is a concat
of segments and never holds them, an#260).

### an.bench.core_corpus.FILM_SEGMENT_ID *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'film'*

The id the bench gives an ASSEMBLED film’s frames (transitions, a sound
layer) when it measures them as one segment — what the delivered mp4 shows.

### an.bench.core_corpus.FRAME_PNG_GLOB *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'frame_\*.png'*

How a shot’s frames are named on disk. One constant rather than the literal
repeated at each glob site.

### *class* an.bench.core_corpus.Fixture(path, prepare=None, expect_visual_kinds=frozenset({}), golden_frames=<factory>, golden_note='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A corpus scene: where it lives, how to build it, what it must render.

#### expect_visual_kinds *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)*

Visual kinds the staged scene MUST contain — see the module docstring.

#### golden_frames *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[float](https://docs.python.org/3/builtins/functions.html#float), ...]*

Times (seconds, into the scene’s CONCATENATED timeline) at which a
golden frame is blessed. Two per scene, the second chosen so something
has actually moved — `--bless` refuses a pair whose two frames are
pixel-identical, which is not hypothetical: `promote_demo`’s frame 0 and
its `duration/2` frame differ by exactly **zero** pixels.

#### golden_note *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

One line saying what moves between the two golden times. Carried as data
because “pick a time where something moved” is a rule that decays into a
habit, and the reason is what a reviewer needs when a golden goes red.

#### prepare *: [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)], [None](https://docs.python.org/3/builtins/constants.html#None)] | [None](https://docs.python.org/3/builtins/constants.html#None)*

Run against the throwaway copy before loading, to regenerate build
products the repo does not track.

### an.bench.core_corpus.IGNORED_ON_COPY *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('.an', 'output', '.anima')*

they are the previous render’s
output, and one of them silently extends this one’s frame sequence.
Matched on the **basename**, at any depth — that is exactly what
`shutil.ignore_patterns` does, and it is why `artifacts/shots` cannot be
spelled here. See [`IGNORED_RELPATHS_ON_COPY`](#an.bench.core_corpus.IGNORED_RELPATHS_ON_COPY).

* **Type:**
  Copied for the render, but never these

### an.bench.core_corpus.IGNORED_RELPATHS_ON_COPY *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('artifacts/shots',)*

Excluded by their path **relative to the project root**, POSIX-spelled.
`mall["shots"]` is `<project>/artifacts/shots`, and `artifacts/`
itself is kept on purpose — it holds the audio cache, whose warm/cold state
this module records rather than destroys.

Neither spelling belongs in [`IGNORED_ON_COPY`](#an.bench.core_corpus.IGNORED_ON_COPY), and \*\*both fail
silently\*\*. `shutil.ignore_patterns` returns a closure handed the NAMES
inside one directory, which it `fnmatch.filter``s — so ``"artifacts/shots"`
can never match anything (no name contains a separator) and a bare
`"shots"` would delete every directory of that name **anywhere** in the
tree, a character rig’s included.

### an.bench.core_corpus.RENDER_WORK_RELPATH *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '.an/render_work'*

Where the renderer leaves its per-shot working tree inside the project.

### an.bench.core_corpus.compiled_contract_sha256(fixture, , repo_root)

The `scene_contract_sha256` a render of `fixture` would record — no browser.

Compiles every timeline shot the way the cutout renderer does (the scene’s
size, fps, style pack, default easing and stepped-timing policy, with
`strict_assets` as the bench sets it) in a throwaway copy, and hashes the
documents. It is the default-leg twin of `capture_fixture()`: the
contract hash is a function of the compiled JSON alone, so the guards that
check it — against the newest ledger row and against each golden’s bless
record — run on every PR, not only in the labelled browser lane.

It is the contract of a bench render, which passes no overrides: a render
given its own `step_hz`, fps or resolution compiles something else.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.core_corpus.compose_film_frames(scene, work_dir)

An assembled scene’s composed frames, written under `work_dir` from its
shots’ frames ([`an.assemble.write_film_frames()`](an.assemble.md#an.assemble.write_film_frames)); `None` for a scene
that is a plain concatenation of its shots.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.bench.core_corpus.frames_dir_for(work_dir, shot_id)

Where a render left the frames of `shot_id` (or of the composed film).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> frames_dir_for(Path("w"), "film").as_posix(), frames_dir_for(Path("w"), "a").as_posix()
('w/film_frames', 'w/shot_a/frames')
```

### an.bench.core_corpus.golden_agreement(name, work_dir, , chromium_build, root=None)

`{frame key: (blessed sha256, today's sha256)}` for every frame the
committed bless record of `name` pins, read from a render’s work dir.

Decoded pixels, never file bytes (`an.bench.golden`’s criterion).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.bench.core_corpus.render_fixture(fixture, , repo_root, base)

Render `fixture` cold, the way the bench does, in a copy under `base`.

Through the core API only (`an.project.load` + `an.render.render`) —
no bench capture code — so it runs with the cut-out genre absent. Returns
the render’s work directory.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.bench.core_corpus.stage_copy(fixture_dir, base)

Copy a fixture into `base`, leaving the previous render behind.

Split out of `capture_fixture()` so the exclusion is testable without
rendering anything — which matters, because the failure it prevents is
silent. `frames/` is never cleared and ffmpeg’s image2 demuxer reads the
contiguous `frame_%06d.png` run from 0, so a longer previous render is
appended to this one’s source leg and to nothing else.

Two kinds of exclusion, because one kind cannot say both things:
[`IGNORED_ON_COPY`](#an.bench.core_corpus.IGNORED_ON_COPY) by basename at any depth, and
[`IGNORED_RELPATHS_ON_COPY`](#an.bench.core_corpus.IGNORED_RELPATHS_ON_COPY) by path from the project root — which is
the only way to drop `artifacts/shots` while keeping `artifacts/audio`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
