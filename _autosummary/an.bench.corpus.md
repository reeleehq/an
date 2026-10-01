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

| [`SHOT_DIR_GLOB`](#an.bench.corpus.SHOT_DIR_GLOB)       | Per-shot subdirectory naming inside `.an/render_work`, and the staged scene filename.                                                                                                                                  |
|----------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`BENCH_RENDER_KWARGS`](#an.bench.corpus.BENCH_RENDER_KWARGS) | Rendering knobs pinned for every bench capture, recorded verbatim into the ledger.                                                                                                                                     |
| [`CORPUS_DIRNAME`](#an.bench.corpus.CORPUS_DIRNAME)      | Where the bench-owned fixtures live.                                                                                                                                                                                   |
| [`DFLT_FIXTURES`](#an.bench.corpus.DFLT_FIXTURES)       | the descriptor (SVG-sprite) path is 12x more sensitive to a rasteriser flip than the procedural one (2.94% vs 0.24% of pixels under GPU-vs-software), so a procedural-only corpus under-reports the case that matters. |

### Functions

| [`assert_render_path`](#an.bench.corpus.assert_render_path)(name, fixture, kinds)   | Refuse a capture that did not exercise the path its fixture declares.   |
|---------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`iter_shot_dirs`](#an.bench.corpus.iter_shot_dirs)(work_dir, \*, order)        | `(shot_id, shot_dir)` for every rendered shot, in **timeline** order.   |
| [`staged_scene`](#an.bench.corpus.staged_scene)(shot_dir)                     | The compiled scene JSON the browser actually loaded, for one shot.      |
| [`visual_kinds`](#an.bench.corpus.visual_kinds)(scene_json)                   | Every `visual.kind` in a staged scene's node tree.                      |

### Classes

| [`Fixture`](#an.bench.corpus.Fixture)(path[, prepare, ...])   | A corpus scene: where it lives, how to build it, what it must render.   |
|----------------------------------------------------------------------------------|-------------------------------------------------------------------------|

### Exceptions

| [`CorpusError`](#an.bench.corpus.CorpusError)   | A fixture did not render what it declared.   |
|----------------------------------------------------------------|----------------------------------------------|

### an.bench.corpus.BENCH_RENDER_KWARGS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]* *= {'auto_audio': False, 'parallel': 1, 'strict_assets': True}*

Rendering knobs pinned for every bench capture, recorded verbatim into the
ledger. NOT flags: a bench whose render knobs vary per invocation produces
incomparable rows.

`auto_audio=False` because audio cannot move a pixel and would otherwise
make the frames depend on the audio cache’s warm/cold state; `parallel=1`
because a timing-sensitive pool is one more thing to explain if the pixels
ever do differ; `strict_assets=True` because a stand-in asset renders
happily as a DIFFERENT picture (an#33).

### an.bench.corpus.CORPUS_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'misc/bench/corpus'*

Where the bench-owned fixtures live. NOT under `examples/`, and the reason
is mechanical rather than tidiness: `.gitignore` excludes every
`examples/*/assets/`, so a corpus scene that needs committed art cannot live
there without a carve-out per scene. `misc/` is not ignored at all.

The second reason is that a metrics fixture must **hold still**. These four
carry their whole rig as committed files and have no `prepare` step, so
their pixels are a function of the repo alone — where `promote_demo`’s are a
function of `an.characters.promote`, and would need re-blessing whenever that
changes.

### *exception* an.bench.corpus.CorpusError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A fixture did not render what it declared.

### an.bench.corpus.DFLT_FIXTURES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Fixture](#an.bench.corpus.Fixture)]* *= {'aa_probe': Fixture(path='misc/bench/corpus/aa_probe', prepare=None, expect_visual_kinds=frozenset({'rect'}), golden_frames=(0.0, 0.25), golden_note='the fourth bar sweeping horizontally (4,200 px). The three angled bars are pinned and do not move — they are the AA subject.'), 'dialogue': Fixture(path='misc/bench/corpus/dialogue', prepare=None, expect_visual_kinds=frozenset({'rect', 'ellipse', 'mouth', 'eye'}), golden_frames=(0.0, 0.6), golden_note="the mouth mid-line: frame 14 sits on the \`h\`/\`a\` of 'shape' and shows \`A\`, the winner of its 0.14 s window under the an#97 vote; the old drop-not-hold condenser showed \`C\` there, having dropped the \`D\` and \`A\` that followed inside the window. Frame 0 shows \`E\` — the winner of the first window, after the lead pulled the line's opening cues to 0 — where the old path showed the rest. The head is lifted 34 px above its rest by an absolute \`set\` so the placeholder rig's mouth clears the torso. The second golden sits INSIDE the spoken interval; \`single_character\`'s second golden samples after its line ends (its first, at t=0, is on the led first shape) and \`promote_demo\` renders mute in the bench (no visemes in its IR, by design). The visemes are the offline provider's, stamped into the committed ir/scene.json; the bench renders with auto_audio=False and reads them from there."), 'expressions': Fixture(path='misc/bench/corpus/expressions', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.125, 0.375, 0.625, 0.875, 1.125, 1.375, 1.625, 1.875), golden_note="eight 0.25 s shots of one silent synthesized character holding one expression preset each (neutral, happy, sad, angry, surprised, afraid, thinking, skeptical — the two presets whose faces differ only by a mouth form the silent rest does not show, disgusted and amused, are left out), sampled at each shot's mid-frame (an#98). What moves between goldens is the FACE SOLVER's output alone: brow height and angle, the eyelid key, and the mouth form's rest. The character is named \`face\` because its seeded blink phase puts no blink window inside any 0.25 s shot (the blink clock restarts per shot), so no golden straddles a blink; it is lowered by an absolute \`set face y\` so the head clears the frame's top edge at 320x240. Its rig is committed whole (parts and descriptor, \`viseme@happy\`/\`viseme@sad\` variants included) and, since an#99, the eye stack (sclera/pupil/lid slots, a filled closed lid, \`gaze_travel\`), so the pupils also make their seeded ambient saccades — sub-pixel at 320x240 and inside the face crop. The pairwise distinguishability test in tests/test_expression_goldens.py reads these same PNGs."), 'graded_field': Fixture(path='misc/bench/corpus/graded_field', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.1667), golden_note='the white marker sweeping across the gradient (6,270 px). Frame 4, not the obvious mid-scene frame 6: the marker advances by a sub-pixel step, so on frames 0, 1, 6, 8 and 11 it lands on an exact pixel boundary and AA-off changes ZERO pixels there. A blessed pair that no available mutation can move is a gate that cannot go red.'), 'multi_shot': Fixture(path='misc/bench/corpus/multi_shot', prepare=None, expect_visual_kinds=frozenset({'rect', 'ellipse'}), golden_frames=(0.0, 0.25), golden_note='the whole picture: 0.25s is the FIRST frame of the second shot, so the pair spans the concat boundary (75,050 px). A golden pair inside one shot would not notice a shot rendered in the wrong order.'), 'path_draw': Fixture(path='misc/bench/corpus/path_draw', prepare=None, expect_visual_kinds=frozenset({'path'}), golden_frames=(0.0, 0.3333333333333333), golden_note="two stroked paths (an#160, an#161), both dashed and both coloured by a StylePack's \`stroke\` role: a marching-ants frame whose \`dash_offset\` runs 0 -> 20 px, and a cubic arrow that draws itself on (\`trim_end\` 0 -> 1) with its head on the moving tip. What moves between the goldens is the ROUTE growing (frame 0 shows none of it) and the frame's dashes sliding 6.7 px along their path; a regression in trim, in the dash phase, in the anchored-at-the-path-start rule that keeps a dash from crawling as the tip advances, or in the pack reaching a path, moves a golden. Butt caps, so a dash's ends are exact rather than rounded past their length."), 'promote_demo': Fixture(path='examples/promote_demo', prepare=<function \_prepare_promote_demo>, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 2.9167), golden_note="a blink — the compiled eyelid swap shows the closed-eye art at t=2.9167 (an earlier note blamed 'the idle animation', which nothing on the render path consumes). Measured: frame 0 against duration/2 differs by exactly ZERO pixels here, so the obvious second time would have blessed one image twice."), 'prop_swap': Fixture(path='misc/bench/corpus/prop_swap', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.375), golden_note="a two-state prop swapping mid-shot (an#108): a desk lamp whose \`lamp\` asset-set goes \`off\` -> \`on\` at t=0.25. What moves between the goldens is a texture SWAP and nothing else — no transform, no easing, no interpolation — which is why this scene is worth a row the other seven cannot provide: every one of them measures a pose changing continuously, so a regression that broke swap resolution alone (the runtime resolves two swap properties on one node by NAME order, and an#87's failure mode was keeping the PREVIOUS texture in silence) would move no golden anywhere in the corpus. Frame 9 rather than the mid-frame: at 24 fps the swap lands on frame 6, so frame 9 is clear of the boundary in a way that does not depend on how the frame containing t=0.25 rounds."), 'saturated_outline': Fixture(path='misc/bench/corpus/saturated_outline', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.25), golden_note='the head plate rotating through 0.3 rad (1,187 px).'), 'single_character': Fixture(path='examples/single_character', prepare=<function \_declare_procedural_rig.<locals>.prepare>, expect_visual_kinds=frozenset({'rect', 'ellipse'}), golden_frames=(0.0, 1.0), golden_note='a blink (the compiled scale_y squash on the procedural eyes) plus, since an#97, the mouth: 253 pixels differ, 172 from the blink and 81 from the mouth (frame 0 shows the led first shape of the 0.71 s line, frame 24 the closed rest after it, which the frame-ceiled window now samples). Blinks occupy 3.5% of frames, so before the lead frame 0 against duration/2 was a pixel-identical pair on this scene; the mouth now separates them by 81 px.'), 'stage_pan': Fixture(path='misc/bench/corpus/stage_pan', prepare=None, expect_visual_kinds=frozenset({'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="three coloured blocks at depths 0.25 / 1.0 / 2.0 under a zoom-free pan (an#111). What moves between the goldens is the SEPARATION: the blocks start aligned and end 10 / 40 / 80 px apart, which is the parallax and nothing else. Frame 8, not the mid-frame: the camera travels 5 px per frame and the far plane moves a quarter of that, so only every fourth frame lands every block on an exact pixel boundary — at any other frame the anti-aliased edge changes the exact-colour mask's SIZE, and a centroid measured against a different shape is not a displacement (the measurement refuses it outright). Zoom is held constant on purpose: the x = 0 probe that cancels it in the JSON half does not reach a centroid, which sits at the plane's own offset.")}*

the descriptor
(SVG-sprite) path is 12x more sensitive to a rasteriser flip than the
procedural one (2.94% vs 0.24% of pixels under GPU-vs-software), so a
procedural-only corpus under-reports the case that matters.

The four scenes an#38 adds, each for a **measured** reason:

- `graded_field` — a real gradient (98 distinct luma levels down the centre
  column) over a large flat block. Banding has no edge in it, so every
  edge-masked metric is blind to it; and the gradient itself sits OUTSIDE the
  flat mask by construction (`flat_mask` demands a zero 4-neighbour delta),
  which is why the scene carries a flat block too — measured 0.2795 of the
  frame, against 0.0341 for a gradient alone.
- `saturated_outline` — maximally saturated fills under a pure-black 12px
  outline. The shipped examples are 31 colours on white and their measured
  4:2:0 edge error is ~3x smaller, so the chroma metric under-reports exactly
  the artefact class the epic cares about. Highest edge-mask fraction in the
  corpus (0.0566).
- `aa_probe` — three bars pinned at 7, 23 and 45 degrees. Axis-aligned
  `drawRect` edges are bit-identical with MSAA on or off, so a corpus of
  axis-aligned art cannot validate an AA metric at all. Measured under the
  real AA lever (PixiJS `antialias: false`): `edge_transition_width`
  2.9866 -> 2.0000 and `video_stream_bytes` **+6.1%**. That last number is
  why this scene is load-bearing rather than decorative — on
  `single_character` the same lever moves the bytes **-6.1%**, the opposite
  of the declared direction, because AA-off on axis-aligned art removes
  intermediate colours instead of creating a staircase. Family F is only an
  honest witness for `disabled_aa` on a scene with non-axis-aligned edges.
- `multi_shot` — two shots, so `an/render.py`’s `_ffmpeg_concat` is
  exercised at all (a single-shot render short-circuits it to
  `shutil.copy`) and `file_bytes` stops meaning two different things
  depending on shot count. Its shot ids are `intro` then `beat`
  **deliberately**: they sort the other way, so any code that recovers shot
  order from the directory name instead of the timeline pairs source frames
  against the wrong half of the concatenated video, and this fixture is what
  notices.

One measured fact that shapes the set: the \*\*descriptor path is nearly blind
to the AA lever\*\* (96 differing pixels out of 12.4M on `promote_demo`),
because MSAA applies to WebGL geometry and an SVG sprite is a pre-rasterised
texture. So the descriptor scenes are in the corpus for the rasteriser
sensitivity the cross-arch work measured, not as AA witnesses.

* **Type:**
  The corpus. One fixture per render path, deliberately both

### *class* an.bench.corpus.Fixture(path, prepare=None, expect_visual_kinds=frozenset({}), golden_frames=<factory>, golden_note='')

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
