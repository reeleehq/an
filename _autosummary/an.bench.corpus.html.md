# an.bench.corpus

The bench corpus: which projects are measured, and what each must actually render.

`expect_visual_kinds` is not belt-and-braces. Every `examples/*/assets/` is
gitignored, and before an#33 a missing character descriptor made the compiler
fall back to the procedural rig with **zero** warnings. The first
cross-architecture capture measured exactly that: three CI runners agreed
perfectly about a picture that was not the picture, and the agreement read as a
clean positive result. It surfaced only because the local machine happened to
hold a *stale* build product and therefore disagreed.

So a fixture declares the render path it must exercise, and the check reads the
scene JSON **the browser actually loaded** — an independent second opinion to
`strict_assets=True`, which trusts the compiler that produced it.

### Module Attributes

| [`SHOT_DIR_GLOB`](#an.bench.corpus.SHOT_DIR_GLOB)   | Per-shot subdirectory naming inside `.an/render_work`, and the staged scene filename.                                                                                             |
|------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DFLT_FIXTURES`](#an.bench.corpus.DFLT_FIXTURES)   | The cut-out scenes of the original corpus moved to `cutan` (`cutan.bench.CUTOUT_FIXTURES`, an#225); this is the core's: `prop_swap` and the core corpus (`an.bench.core_corpus`). |

### Functions

| [`assert_render_path`](#an.bench.corpus.assert_render_path)(name, fixture, kinds)   | Refuse a capture that did not exercise the path its fixture declares.   |
|---------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`iter_shot_dirs`](#an.bench.corpus.iter_shot_dirs)(work_dir, \*, order)        | `(shot_id, shot_dir)` for every rendered shot, in **timeline** order.   |
| [`staged_scene`](#an.bench.corpus.staged_scene)(shot_dir)                     | The compiled scene JSON the browser actually loaded, for one shot.      |
| [`visual_kinds`](#an.bench.corpus.visual_kinds)(scene_json)                   | Every `visual.kind` in a staged scene's node tree.                      |

### Exceptions

| [`CorpusError`](#an.bench.corpus.CorpusError)   | A fixture did not render what it declared.   |
|----------------------------------------------------------------|----------------------------------------------|

### *exception* an.bench.corpus.CorpusError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A fixture did not render what it declared.

### an.bench.corpus.DFLT_FIXTURES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Fixture](an.bench.core_corpus.html.md#an.bench.core_corpus.Fixture)]* *= {'path_draw': Fixture(path='misc/bench/corpus/path_draw', prepare=None, expect_visual_kinds=frozenset({'path'}), golden_frames=(0.0, 0.3333333333333333), golden_note="two stroked paths (an#160, an#161), both dashed and both coloured by a StylePack's \`stroke\` role: a marching-ants frame whose \`dash_offset\` runs 0 -> 20 px, and a cubic arrow that draws itself on (\`trim_end\` 0 -> 1) with its head on the moving tip. What moves between the goldens is the ROUTE growing (frame 0 shows none of it) and the frame's dashes sliding 6.7 px along their path; a regression in trim, in the dash phase, in the anchored-at-the-path-start rule that keeps a dash from crawling as the tip advances, or in the pack reaching a path, moves a golden. Butt caps, so a dash's ends are exact rather than rounded past their length."), 'prop_swap': Fixture(path='misc/bench/corpus/prop_swap', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.375), golden_note="a two-state prop swapping mid-shot (an#108): a desk lamp whose \`lamp\` asset-set goes \`off\` -> \`on\` at t=0.25. What moves between the goldens is a texture SWAP and nothing else — no transform, no easing, no interpolation — which is why this scene is worth a row the other seven cannot provide: every one of them measures a pose changing continuously, so a regression that broke swap resolution alone (the runtime resolves two swap properties on one node by NAME order, and an#87's failure mode was keeping the PREVIOUS texture in silence) would move no golden anywhere in the corpus. Frame 9 rather than the mid-frame: at 24 fps the swap lands on frame 6, so frame 9 is clear of the boundary in a way that does not depend on how the frame containing t=0.25 rounds."), 'stage_pan': Fixture(path='misc/bench/corpus/stage_pan', prepare=None, expect_visual_kinds=frozenset({'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="three coloured blocks at depths 0.25 / 1.0 / 2.0 under a zoom-free pan (an#111). What moves between the goldens is the SEPARATION: the blocks start aligned and end 10 / 40 / 80 px apart, which is the parallax and nothing else. Frame 8, not the mid-frame: the camera travels 5 px per frame and the far plane moves a quarter of that, so only every fourth frame lands every block on an exact pixel boundary — at any other frame the anti-aliased edge changes the exact-colour mask's SIZE, and a centroid measured against a different shape is not a displacement (the measurement refuses it outright). Zoom is held constant on purpose: the x = 0 probe that cancels it in the JSON half does not reach a centroid, which sits at the plane's own offset."), 'text_card': Fixture(path='misc/bench/corpus/text_card', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="text under a camera push-in and roll (an#279, the core corpus): two OVERLAY words fading in one after the other (\`word_1\` starts 0.125 s after \`word_0\`) and a WORLD label on a plane block, while the camera zooms 1.0 -> 1.3 and rolls 0.12 rad. What moves between the goldens: the words' alpha (frame 0 shows neither), the label and block growing and turning with the camera, and the overlay title NOT turning — a regression that put overlay text in the world, broke per-word addressing or the camera's zoom/roll moves a golden. The face is Pillow's embedded Aileron, so the glyphs do not depend on the machine's fonts."), 'text_swap': Fixture(path='misc/bench/corpus/text_swap', prepare=None, expect_visual_kinds=frozenset({'rect', 'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note='a text block\\'s CONTENT changing within one shot (an#341): one right-aligned \`unit: block\` label whose \`texts\` set is swapped twice, "Day 1" -> "Day 12" at 0.125 s (the entity-level \`set day text d12\`) -> "Day 300" at 0.25 s (the \`day/block_0\` path). What moves between the goldens is the string, growing LEFTWARDS from a fixed right edge: a regression in the swap set, in the per-key geometry anchored on the \`align\` edge, or in the entity-level fan-out moves a golden.'), 'transitions': Fixture(path='misc/bench/corpus/transitions', prepare=None, expect_visual_kinds=frozenset({'rect', 'path'}), golden_frames=(0.08333333333333333, 0.375, 0.625), golden_note="the delivered film's COMPOSED frames (an#279, the core corpus): \`dusk\` fades in from black over 0.25 s, then \`dawn\` dissolves in over 0.25 s (frames 6-11 are the blend; the film is 12 + 12 - 6 = 18 frames). Frame 2 is mid-fade, frame 9 mid-dissolve (both pictures at once), frame 15 \`dawn\` alone with its arrow. A regression in the fade colour, the dissolve weights, the overlap arithmetic or the order of the shots moves a golden. The only fixture measured on the film's frames rather than the shots' — what the delivered mp4 shows (an.bench.capture's film segment).")}*

The cut-out scenes of the original corpus moved to `cutan` (`cutan.bench.CUTOUT_FIXTURES`, an#225); this
is the core’s: `prop_swap` and the core corpus (`an.bench.core_corpus`).

### an.bench.corpus.SHOT_DIR_GLOB *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'shot_\*'*

Per-shot subdirectory naming inside `.an/render_work`, and the staged scene
filename. Mirrored from the renderer rather than restated as literals at
each use site.

### an.bench.corpus.assert_render_path(name, fixture, kinds)

Refuse a capture that did not exercise the path its fixture declares.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.bench.corpus.iter_shot_dirs(work_dir, , order)

`(shot_id, shot_dir)` for every rendered shot, in **timeline** order.

`order` is mandatory, and that is the whole point of this signature.
`an/render.py` concatenates `[r.mp4_path for r in shot_results]` built
from `list(scene.timeline)`, while this function’s previous form returned
`sorted(work_dir.glob("shot_*"))` — directory-name order. The two agree
only when the shot ids happen to sort into timeline order, and when they do
not, every encode-side metric pairs source frame *i* of one shot against
decoded frame *i* of another. The `multi_shot` fixture’s ids (`intro`
then `beat`) are chosen so they disagree.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]]

```pycon
>>> import tempfile
>>> from pathlib import Path
>>> d = Path(tempfile.mkdtemp())
>>> for name in ("shot_intro", "shot_beat"): (d / name).mkdir()
>>> [i for i, _ in iter_shot_dirs(d, order=["intro", "beat"])]
['intro', 'beat']
```

### an.bench.corpus.staged_scene(shot_dir)

The compiled scene JSON the browser actually loaded, for one shot.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.corpus.visual_kinds(scene_json)

Every `visual.kind` in a staged scene’s node tree.

Read from the staged file rather than re-compiled, so it reports what was
rendered rather than what a second compile would produce.

Scoped to `scene` and to the `visual` key specifically. A sweep for
every `kind` anywhere in the document — which is what this was before —
also collects an#33’s `asset_resolution` entries, whose `kind` is
`"character"` / `"environment"`. Those are entity kinds, not visual
kinds, and mixing them makes the field mean two things at once.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> sorted(visual_kinds({"scene": {"visual": {"kind": "rect"},
...                                "children": [{"visual": {"kind": "eye"}}]},
...                      "asset_resolution": [{"kind": "character"}]}))
['eye', 'rect']
```
