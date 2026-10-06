---
name: an-dev-text
description: Text on screen in the `an` repo (an#155, an#175, epic #9 Wave 8) — the `TextDescriptor` prop, captions from word timings (`an/captions.py`, the SRT sidecar), tituli as the typesetter, units compiled to SVG-sprite nodes with inline `data:` textures, the camera-immune overlay layer (`CutoutSceneJSON.overlay`), fail-loud fonts and the embedded default face. Load before touching `an/stage/text.py`, `an/stage/text_layout.py`, `_build_text_block`, `_check_text_unit_targets`, `_check_text_blocks`, the overlay container in `runtime.js`, `screen_position`'s overlay branch, or anything that puts words, titles, labels, captions or fonts on screen. Triggers on "text", "title card", "label", "caption", "subtitle", "font", "typeface", "glyph", "word by word", "typewriter", "overlay", "HUD", "lower third".
---

# an-dev-text — words on screen

## The model in six lines

- A text block is a **prop** whose document `kind` is `TextDescriptor` (`an/stage/text.py`) — the `PathDescriptor` shape. No scene-IR field, no migration, no new action kind (so the six-place action enumeration does not apply). Overrides merge over the stored document and validate strictly (`resolve_text`); a stored doc may be a reusable style with no `text`.
- **tituli typesets; an consumes.** `layout_text` calls `tituli.block(...)` (wrap, align, one `Run` per unit) and `tituli.run_outline(run)` (the run's glyph contours as SVG `d`, fontTools). Never reimplement metrics or wrapping here — add to tituli (its own repo, own PR) instead.
- Each drawn unit → node `<id>/<unit>_<i>` (i counts DRAWN units; spaces are not units), visual `svg_sprite` `fit: contain`, texture alias `text.<id>.<unit>_<i>`, `src` = `data:image/svg+xml;base64,…`. The block node is the entity; units sit at their box centres so a scale/rotation pivots mid-unit.
- `layer: overlay` → `CutoutSceneJSON.overlay` (a sibling of `scene`); `layer: world` → the scene like any prop.
- Fonts: `font: None` = Pillow's embedded Aileron via `tituli.EMBEDDED`; `font:` = a FILE path (absolute, or relative to the text document's directory in an on-disk props store). The face's sha256 goes to `meta.fonts[<id>]`.
- Reveals are ordinary actions: `an.stage.text.reveal_units(...)` returns a list of `set` holds + `sequence(delay, tween)` leaves.

## Text content over time: the replacement set (an#341)

- `texts: {key: string}` + `rest` + `unit: block` (required with `texts`). `block` typesets with tituli's `line` unit and joins the lines into ONE unit, `block_0` (contours concatenated, boxes unioned). Exactly one of `text`/`texts`.
- The builder (`_text_set_visual`) emits `block_0` drawing the rest string, `asset_sets={"text": {key: alias}}`, and an `asset_geometry` box per alias drawn differently. Alignment is by LAYOUT box (`TextLayout.bounds`: advances and line height, not ink): the `align` edge horizontally, the box centre vertically, so one-line keys share a baseline. An anchored overlay is pinned to the rest string's edge, not re-anchored per key.
- The set is declared by the core `prop` kind's `swap_declaration` (`text_swap_declaration`) with `descriptor=None`: `vocab.descriptors` is what a genre's lowering reads as a RIG (cutan iterates it for `swap_poses`/`rest_view`), so a text block must never land there. Entity-level sugar fans out on `vocab.declared`; the pose record only for entities with a descriptor.
- validate's `_check_swap_references` asks the kind's hook when there is no rig document (`_declared_swap_sets`); `_check_text_blocks` typesets EVERY key, so a glyph only one key uses is reported.
- Runtime: nothing new. A `text` value is a `discrete` string under `stage.node`'s `*`; `applySwap` + `applyKeyGeometry` draw it.

## A counter (an#342)

- `counter: {format, start}` + `unit: block`. `format` is `an/formats.py`'s d3-format subset; rounding is half-even on the float's exact value (Python's formatting), NOT d3's ties-away — a JS reproduction must match it.
- `value` is block-scoped and never in `AUTHORABLE_PROPERTIES` (that set is skipped by validate's field-kind check; a global `value` would un-validate every genre's own). `_check_text_blocks` owns `value` on text blocks; swap and field-kind checks defer; elsewhere the undeclared-set refusal carries `_value_hint`.
- The stage pass `counters` (order 195) must stay after every pass that adds `extra_actions` and immediately before `actions`; `tests/test_text_counter.py` and `tests/test_compile_passes.py` pin it. It samples through `_compile_actions` + the kernel evaluator (never a second interpolation), gives a from-less tween an explicit `from` (the compiler's own from-less rule ignores a set at the same instant), rebuilds the block as a `texts` set and swaps leaves for `delay`s of their length.
- Not built: tabular figures (an#362, tituli#4); the embedded face's digits are already equal-width.

## Outlines (an#313)

- `stroke_width` is the VISIBLE thickness outside the glyph; `unit_svg` strokes the contours at `2 × stroke_width` (round joins) and then fills them, two paths rather than `paint-order`. The unit box grows by `ceil(stroke_width)`.
- Every unit is its own texture, so outlines cannot all sit under all fills: a unit's outline covers its predecessor's fill where they meet. `_warn_if_outlines_overlap` says so (`TextOutlineWarning`). Moving outlines to a separate layer would break per-unit alpha; do not.

## Silent failures this prevents — keep each one refused

1. **A fallback face.** `tituli.resolve_face` NEVER fails: a font path that is missing or unparseable silently becomes Aileron. So `_font_request` checks the file exists AND `layout_text` checks the face tituli used came from that file (`face.path == request`). Remove either and a scene renders in the wrong face with no signal. Tested: missing file, non-font bytes.
2. **Machine-dependent pixels.** A family NAME (`"Helvetica"`) is refused by the schema, and the default asks for `EMBEDDED`, not `"Aileron"` — a machine with Aileron installed would resolve the name to a different file. A relative `font` with an in-memory store RAISES rather than resolving against the CWD.
3. **A box instead of a letter.** A character the face has no glyph for raises (`MissingGlyphError` → `TextLayoutError`, U+ code named). The embedded face is printable ASCII plus `‘’“”…©«°±´·»` — no `–`/`—`/`•`/`é`/`€`, so an en dash in a title raises. English-first, refusing loudly — the epic's scope. Full non-Latin is out of scope.
4. **A target that does not exist.** Units are DERIVED (a 3-word title has no `word_3`; a `unit: glyph` block has no `word_*`). Transform targets are otherwise only runtime-checked, so `_check_text_unit_targets` (compile) and `_check_text_blocks` (validate) refuse them naming the built units.
5. **A reveal that flashes.** Before a tween's window the runtime shows the node's BUILT value (alpha 1), so a delayed fade-in shows the word, then snaps to 0. `stagger` emits a `set from_ at 0` for every delayed unit (the set-hold rule) — that is why `from_` is required. A hand-written reveal needs the same `set`.
6. **The camera reaching the overlay.** The runtime builds the overlay container and does NOT put it in `nodeIndex`; only its children are indexed. Indexing it (or building overlay children under `root`) makes a title zoom with a push-in — `test_in_pixels_a_title_card_holds_still_through_a_push_in` goes red (mutation-tested). `nodeIndex` is ONE namespace for both layers, so three things are refused at compile AND validate (`text_entity_problem` is the shared statement): a text id `root` (it would overwrite the camera's node — the review's repro) or `overlay`; an overlay id equal to a scene entity's; two text blocks with one id. The runtime also throws on an overlay/scene path collision, as the backstop for a hand-written document.
7. **A stale texture.** Aliases are content-addressed (`text.<id>.<unit>.<sha12>`): a name-only alias survived an edit of the words, and the runtime's loader ignores a re-added alias, so `an preview` would have kept the old glyphs.
8. **Every corpus hash moving.** `CutoutSceneJSON.overlay` and `CutoutSceneMetaJSON.fonts` are omit-when-unset, written in the same commit as the fields (the an#112 rule). Any new field on either needs the same.

## Invariants that are not obvious

- **Pixel grid.** Unit boxes are snapped OUTWARD to integers (plus `UNIT_BOX_PAD_PX`) and contain both the layout box and the ink; the texture is `TEXT_TEXTURE_OVERSAMPLE` (2) × the box and fitted back, so at zoom 1 sprite corners land on pixels and sampling is a clean 2:1 box filter. Crisp under a 1.25 push-in; softer under `supersample` > 2 (as SVG rig art is).
- **Sizes are fractions of frame height** (tituli's convention), in both layers. A world label next to a character therefore changes size relative to the rig when the resolution changes — characters are sized in absolute scene px. Documented, not fixed.
- **Metrics come from FreeType via Pillow** (tituli measures with `Face.length`, hinted advances). Glyph positions — and so the contract hash — can differ between Pillow/FreeType builds even with the same font bytes, and for a font FILE between Pillow's two layout engines: RAQM (HarfBuzz: kerning, ligatures) is used whenever libraqm loads, BASIC otherwise. The engine is recorded in `meta.fonts` (`layout:basic|raqm`) so the difference is visible, not explained away; the embedded face is always BASIC. Pinning BASIC would be a tituli change. The first text corpus scene must be checked cross-arch before it is blessed.
- **`x`/`y` on a unit are ABSOLUTE and hold its layout offset** (each unit sits at its box centre relative to the block). A tween `y: 30 → 0` puts every word on one baseline; a slide-in needs per-unit values (`rest_pose(shot, "t/word_3", mall=…)` reads a unit's offset, overlay included). `alpha`/`scale_*`/`rotation` reveals work with shared values because their rest is the identity.
- Whitespace: `\r\n`, `\r` → newline and `\t` → space before typesetting; a non-breaking space is a glyph (the embedded face lacks it → raises in word/line units; a glyph unit skips whitespace units).
- A `.ttc` collection: tituli picks its regular upright face, and `meta.fonts` records the digest of the whole collection. No face index yet.
- **Staging skips `data:` srcs** (`INLINE_SRC_PREFIX` in `_stage_scene_assets`). Other consumers do not know inline srcs or the overlay: `an/bench/palette.py`, `bench/contract.py` (`count_drawable_entities`, `count_nodes`) and the node walk in `bench/corpus.py` read only `scene`, and the palette would record a world text alias as `unstaged:` — fix them before adding a text corpus scene. `fidelity.part_fidelity` skips inline srcs (unreadable).
- **Dependencies**: `tituli` (needs >= 0.0.7 for `run_outline`/`EMBEDDED`; unversioned per the local convention) and `fonttools` declared BY NAME — not `tituli[outlines]` — because `tests/test_licence_perimeter.py` reads requirement names and drops extras.
- `screen_position` is the executable spec of the runtime's composition, overlay included: a path whose root is an overlay child composes with NO root pose.

## Captions (an#175) — `an/captions.py`

- **One page list, two outputs.** `caption_pages(scene, fps=...)` is the only statement of what is captioned on which SHOT-local frames (`start` = first frame showing, `end` = first not). `captioned_shot` turns a shot's pages into overlay text blocks `caption_<k>` + `set` actions (alpha on the block; `tint` per word for `highlight`, over WHITE glyphs because tint multiplies); `caption_cues(pages, film_timeline(...))` + `dump_srt` is the sidecar. Never compute caption timing a second way — `test_the_picture_and_the_sidecar_cannot_disagree_across_a_dissolve` reads the compiled document back through the timeline evaluator and compares frames.
- **Sets land half a frame early** (`(f - 0.5) / fps`), so no float disagreement about `i / fps` between Python and `runtime.js` can move a boundary a frame.
- **Materialised at render time, never written to the scene** (`render._burn_captions`): word timings are the audio pipeline's output and change when a line is re-voiced. The caption style reaches the compiler through `_PropsWithCaptions`, which delegates attributes (`_root`) to the real props store — an author's relative font must still resolve. An EMPTY on-disk store is falsy: never `mall.get("props") or {}` there.
- **Line breaks are made by `wrap_words` (characters), written as explicit newlines into BOTH outputs**; tituli's `max_width` is not used for captions, or the sidecar's lines would differ from the picture's.
- **No word timings** (offline, Rhubarb) → even spacing + `CaptionTimingWarning`; `Captions(strict=True)` raises. Script and timed word counts differing → the timed words are shown (warned).
- **The SubRip cue type is a pinned MIRROR of `mixing.srt`, not an import** (epic #9 Decision 2 departed from, on measurement): `mixing`'s package facade is lazy (importing `mixing.srt` loads no media stack), but INSTALLING it pulls moviepy, opencv-contrib-python, scipy and imageio-ffmpeg, whose wheel ships an `--enable-gpl` ffmpeg binary the licence perimeter (declared metadata only) cannot see. `tests/test_captions.py` pins `Cue`/`dump_srt`/`seconds_to_srt_time` against `mixing` when importable and a literal always, and refuses any `import mixing` under `an/`. Revisit when thorwhalen/mixing#54 (media stack into extras) lands.
- **Film time is the frame grid.** The sidecar places shots at whole frames (`film_timeline`). A concat of shot mp4s used to place them at container lengths, which drifted when a duration was not whole frames, so captioned scenes were routed through `assemble_film`; since each shot's audio is cut to its picture (an#195) the concat is on the grid too (frame i at i/fps plus the constant AAC priming), and that routing is gone (an#200). Guard: `tests/test_delivered_frame_rate.py::test_a_captioned_film_of_off_grid_shots_is_concatenated_on_the_sidecar_grid`.
- **Transitions act on the burned captions like any pixel**: a dissolve blends shot A's last caption with shot B's first (both can be visible at one anchor), a fade takes the caption through the colour; the sidecar cue is simply on. Within a shot, pages never overlap (a page is cut at the next's start; two starting on one frame → the earlier is dropped with a `CaptionWarning`).
- `_check_typesettable` (called from `render` with the resolution) refuses, before any browser: a glyph the face lacks, a line wider than the title-safe area (lower `max_chars`/`size` — 42 chars does not fit a portrait frame), and a word-unit count that differs from the page's words. Timed tokens with spaces ("New York") are split so units and highlight targets stay one to one; unsorted timings are sorted with a warning; a page whose successor starts on the same frame (an abbreviation's sentence break) is merged into it.
- A highlight lit from frame 0 is the `set` AT 0 (a set at -half a frame is overridden by the base-colour set at 0).
- Sidecar hygiene: `sidecar: false` or nothing to caption REMOVES a stale `output/<name>.srt` (a player would load it); a scene with no `captions` leaves an existing file alone (it may be the author's) and warns.
- The embedded face's glyph set applies: a line with an em dash or `é` raises at compile when captions are on (refuse, don't substitute).

## Not built (the rest of Wave 8)

- Captions: WebVTT (the epic assigns it to `lacing`), a scrim/plate behind the caption, speaker labels, captions in `an preview`, a caption corpus scene.
- A StylePack `text` role (colour is compiler-decided, so it is reachable — add the role and a fixed-scene assertion together, the `REACHABLE_ROLES` rule).
- Text on a path / calligrams (`tituli.along_path`, `rain` already place runs with an `angle`; `run_outline` rotates — the compiler would need per-unit rotation in the node transform instead of in the outline, so a `rotation` tween still pivots at the unit).
- A corpus scene + golden + palette support; scrims/plates (`Layout.plates`) are not drawn.
- Engine stays pinned (Decision 4): nothing here needs dynamic bitmap fonts.
