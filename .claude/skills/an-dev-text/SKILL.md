---
name: an-dev-text
description: Text on screen in the `an` repo (an#155, epic #9 Wave 8) — the `TextDescriptor` prop, tituli as the typesetter, units compiled to SVG-sprite nodes with inline `data:` textures, the camera-immune overlay layer (`CutoutSceneJSON.overlay`), fail-loud fonts and the embedded default face. Load before touching `an/text.py`, `an/adapters/cutout/text.py`, `_build_text_block`, `_check_text_unit_targets`, `_check_text_blocks`, the overlay container in `runtime.js`, `screen_position`'s overlay branch, or anything that puts words, titles, labels, captions or fonts on screen. Triggers on "text", "title card", "label", "caption", "subtitle", "font", "typeface", "glyph", "word by word", "typewriter", "overlay", "HUD", "lower third".
---

# an-dev-text — words on screen

## The model in six lines

- A text block is a **prop** whose document `kind` is `TextDescriptor` (`an/text.py`) — the `PathDescriptor` shape. No scene-IR field, no migration, no new action kind (so the six-place action enumeration does not apply). Overrides merge over the stored document and validate strictly (`resolve_text`); a stored doc may be a reusable style with no `text`.
- **tituli typesets; an consumes.** `layout_text` calls `tituli.block(...)` (wrap, align, one `Run` per unit) and `tituli.run_outline(run)` (the run's glyph contours as SVG `d`, fontTools). Never reimplement metrics or wrapping here — add to tituli (its own repo, own PR) instead.
- Each drawn unit → node `<id>/<unit>_<i>` (i counts DRAWN units; spaces are not units), visual `svg_sprite` `fit: contain`, texture alias `text.<id>.<unit>_<i>`, `src` = `data:image/svg+xml;base64,…`. The block node is the entity; units sit at their box centres so a scale/rotation pivots mid-unit.
- `layer: overlay` → `CutoutSceneJSON.overlay` (a sibling of `scene`); `layer: world` → the scene like any prop.
- Fonts: `font: None` = Pillow's embedded Aileron via `tituli.EMBEDDED`; `font:` = a FILE path (absolute, or relative to the text document's directory in an on-disk props store). The face's sha256 goes to `meta.fonts[<id>]`.
- Reveals are ordinary actions: `an.text.stagger(...)` returns a list of `set` holds + `sequence(delay, tween)` leaves.

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

## Not built (the rest of Wave 8)

- **Captions from lip-sync word timings** — the next slice, an#175 (sub-issue of epic #9): `Dialogue.word_timings` already exist in the IR; caption cue types come from `mixing` (Decision 2: take the dependency, enforce the import boundary with a test).
- A StylePack `text` role (colour is compiler-decided, so it is reachable — add the role and a fixed-scene assertion together, the `REACHABLE_ROLES` rule).
- Text on a path / calligrams (`tituli.along_path`, `rain` already place runs with an `angle`; `run_outline` rotates — the compiler would need per-unit rotation in the node transform instead of in the outline, so a `rotation` tween still pivots at the unit).
- A corpus scene + golden + palette support; scrims/plates (`Layout.plates`) are not drawn.
- Engine stays pinned (Decision 4): nothing here needs dynamic bitmap fonts.
