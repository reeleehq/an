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

### an.bench.corpus.DFLT_FIXTURES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Fixture](an.bench.core_corpus.md#an.bench.core_corpus.Fixture)]* *= {'after_plane': Fixture(path='misc/bench/corpus/after_plane', prepare=None, expect_visual_kinds=frozenset({'svg_sprite', 'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="a prop placed BETWEEN two planes under a pan (an#344): a far sky (depth 0.25), a disc with \`stage.after: set/sky\`, then a wall in two pieces with a window gap and a sill, all at depth 1.0, while the camera pans 60 px. The disc is drawn behind the walls and rides the sky's parallax through its band wrapper: between the goldens the walls move 40 px and the sky and disc 10 px. A regression in the draw order (the disc over the wall), in the wrapper's compensation (the disc sliding against the sky), or in the band containers' addressing moves a golden."), 'front_plane': Fixture(path='misc/bench/corpus/front_plane', prepare=None, expect_visual_kinds=frozenset({'svg_sprite', 'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="an environment cut by \`characters_after\` with an ANIMATED foreground plane (an#343): \`stage\` draws \`sky\` and \`hill\` behind a world text label and \`rail\` in front of it, in its own container with \`scope: stage\`, so the rail is addressed \`stage/rail\` (never \`stage_\_front/rail\`) and its \`y\` tween rises from 60 to 0 over the label. What moves between the goldens is the rail crossing the label: a regression in the runtime's scoped indexing (the channel would name nothing and the load throws), in the cut, or in the draw order moves a golden."), 'path_draw': Fixture(path='misc/bench/corpus/path_draw', prepare=None, expect_visual_kinds=frozenset({'path'}), golden_frames=(0.0, 0.3333333333333333), golden_note="two stroked paths (an#160, an#161), both dashed and both coloured by a StylePack's \`stroke\` role: a marching-ants frame whose \`dash_offset\` runs 0 -> 20 px, and a cubic arrow that draws itself on (\`trim_end\` 0 -> 1) with its head on the moving tip. What moves between the goldens is the ROUTE growing (frame 0 shows none of it) and the frame's dashes sliding 6.7 px along their path; a regression in trim, in the dash phase, in the anchored-at-the-path-start rule that keeps a dash from crawling as the tip advances, or in the pack reaching a path, moves a golden. Butt caps, so a dash's ends are exact rather than rounded past their length."), 'prop_swap': Fixture(path='misc/bench/corpus/prop_swap', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.375), golden_note="a two-state prop swapping mid-shot (an#108): a desk lamp whose \`lamp\` asset-set goes \`off\` -> \`on\` at t=0.25. What moves between the goldens is a texture SWAP and nothing else — no transform, no easing, no interpolation — which is why this scene is worth a row the other seven cannot provide: every one of them measures a pose changing continuously, so a regression that broke swap resolution alone (the runtime resolves two swap properties on one node by NAME order, and an#87's failure mode was keeping the PREVIOUS texture in silence) would move no golden anywhere in the corpus. Frame 9 rather than the mid-frame: at 24 fps the swap lands on frame 6, so frame 9 is clear of the boundary in a way that does not depend on how the frame containing t=0.25 rounds."), 'rig_chain': Fixture(path='misc/bench/corpus/rig_chain', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="a desk-lamp prop with \`nesting: bones\` (an#340): base -> upper arm -> forearm, and a shade NESTED on the forearm's bone (the sword in the hand). The upper arm (rest 30 deg) tweens 0.52 -> -0.3 rad, the forearm (rest -70 deg, relative to the upper arm) -1.22 -> -0.4, the shade 0 -> 0.6: each turns about its joint and carries what hangs from it. A regression that flattened the chain (forearm left behind by the upper arm), inherited a parent's attachment offset, or applied a rest pose twice moves a golden."), 'rig_order': Fixture(path='misc/bench/corpus/rig_order', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="a nested chain drawn BEHIND the part it hangs from (an#403): \`rig_chain\`'s desk lamp in \`nesting: bones\` with the whole arm (upper, forearm, shade: draw orders 1-3) behind its base (4). The base's container sorts its own drawing after the arm (\`sortableChildren\`, \`z_index\`), which the stage used to refuse. Between the goldens the arm swings as in \`rig_chain\`; where it passes over the base the base is in front. A regression in the runtime's sort, the compiler's \`z_index\` or the chain refusal moves a golden."), 'rig_origin': Fixture(path='misc/bench/corpus/rig_origin', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="two copies of one three-bone signpost rig (base, post, sign) at the same \`stage.at\` height (an#338): \`footed\` declares its \`origin\` at the foot of its base, so its foot stands ON the placement line; \`centred\` declares none, so the middle of its bones' extent lands there and it hangs lower. \`footed\` tweens \`rotation\` 0 -> -0.4 rad, which turns it about the declared origin: between the goldens its sign swings left while its foot does not move, and \`centred\` does not move at all. A regression that ignored \`origin\` (both posts at one height), placed parts about the wrong point, or broke the shared rig builder moves a golden."), 'rig_rest': Fixture(path='misc/bench/corpus/rig_rest', prepare=None, expect_visual_kinds=frozenset({'svg_sprite'}), golden_frames=(0.0, 0.3333333333333333), golden_note="a tripod prop whose three legs are ONE drawing on three bones with \`rotation_deg\` 22 / 0 / -22 (an#339): the splay is the bones' rest pose, not pixels. The whole tripod tweens \`rotation\` 0 -> 0.3 rad about its declared origin (the centre foot), and the splayed legs ride it: at frame 8 the rig is tilted 0.2 rad with the splay intact. A regression that dropped the rest pose (three parallel legs), applied it twice, or let the entity's rotation replace a leg's instead of composing with it moves a golden."), 'stage_pan': Fixture(path='misc/bench/corpus/stage_pan', prepare=None, expect_visual_kinds=frozenset({'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="three coloured blocks at depths 0.25 / 1.0 / 2.0 under a zoom-free pan (an#111). What moves between the goldens is the SEPARATION: the blocks start aligned and end 10 / 40 / 80 px apart, which is the parallax and nothing else. Frame 8, not the mid-frame: the camera travels 5 px per frame and the far plane moves a quarter of that, so only every fourth frame lands every block on an exact pixel boundary — at any other frame the anti-aliased edge changes the exact-colour mask's SIZE, and a centroid measured against a different shape is not a displacement (the measurement refuses it outright). Zoom is held constant on purpose: the x = 0 probe that cancels it in the JSON half does not reach a centroid, which sits at the plane's own offset."), 'text_card': Fixture(path='misc/bench/corpus/text_card', prepare=None, expect_visual_kinds=frozenset({'svg_sprite', 'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="text under a camera push-in and roll (an#279, the core corpus): two OVERLAY words fading in one after the other (\`word_1\` starts 0.125 s after \`word_0\`) and a WORLD label on a plane block, while the camera zooms 1.0 -> 1.3 and rolls 0.12 rad. What moves between the goldens: the words' alpha (frame 0 shows neither), the label and block growing and turning with the camera, and the overlay title NOT turning — a regression that put overlay text in the world, broke per-word addressing or the camera's zoom/roll moves a golden. The face is Pillow's embedded Aileron, so the glyphs do not depend on the machine's fonts."), 'text_counter': Fixture(path='misc/bench/corpus/text_counter', prepare=None, expect_visual_kinds=frozenset({'svg_sprite', 'rect'}), golden_frames=(0.0, 0.5), golden_note="a calendar counting 1 to 30 with ONE text block (an#342): a right-aligned \`counter: {format: '{d}', start: 1}\` under one linear \`tween day value -> 30\` over 1 s, lowered at compile to a replacement set of the strings the frames show. Frame 0 shows 1; frame 12's value is exactly 15.5, which nearest-half-even rounding shows as 16 (15 would mean ties away from even, 15/17 a sampling or set-time shift). A regression in the sampling grid, the half-frame set time, the rounding or the right-edge geometry moves a golden."), 'text_outline': Fixture(path='misc/bench/corpus/text_outline', prepare=None, expect_visual_kinds=frozenset({'svg_sprite', 'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note="OUTLINED text (an#313, OverSimplified's labels): white words with a 4 px near-black outline over a mid-blue plate and a pale stripe, the second word fading in from 0.125 s. Frame 0 shows the first word alone, outline and all, and NO outline where the second word will be (the outline lives in the word's own texture, so its alpha hides both); frame 8 shows both, legible over the blue and the stripe alike. A regression in the outline's width, its order under the fill, the box growth that keeps it unclipped, or per-word alpha moves a golden."), 'text_swap': Fixture(path='misc/bench/corpus/text_swap', prepare=None, expect_visual_kinds=frozenset({'svg_sprite', 'rect'}), golden_frames=(0.0, 0.3333333333333333), golden_note='a text block\\'s CONTENT changing within one shot (an#341): one right-aligned \`unit: block\` label whose \`texts\` set is swapped twice, "Day 1" -> "Day 12" at 0.125 s (the entity-level \`set day text d12\`) -> "Day 300" at 0.25 s (the \`day/block_0\` path). What moves between the goldens is the string, growing LEFTWARDS from a fixed right edge: a regression in the swap set, in the per-key geometry anchored on the \`align\` edge, or in the entity-level fan-out moves a golden.'), 'transitions': Fixture(path='misc/bench/corpus/transitions', prepare=None, expect_visual_kinds=frozenset({'path', 'rect'}), golden_frames=(0.08333333333333333, 0.375, 0.625), golden_note="the delivered film's COMPOSED frames (an#279, the core corpus): \`dusk\` fades in from black over 0.25 s, then \`dawn\` dissolves in over 0.25 s (frames 6-11 are the blend; the film is 12 + 12 - 6 = 18 frames). Frame 2 is mid-fade, frame 9 mid-dissolve (both pictures at once), frame 15 \`dawn\` alone with its arrow. A regression in the fade colour, the dissolve weights, the overlap arithmetic or the order of the shots moves a golden. The only fixture measured on the film's frames rather than the shots' — what the delivered mp4 shows (an.bench.capture's film segment).")}*

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
