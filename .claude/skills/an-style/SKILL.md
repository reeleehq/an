---
name: an-style
description: Use when the user wants a script or scene made "in the style of" a named cut-out animation look — South Park, OverSimplified, Kurzgesagt, Terry Gilliam / Monty Python, Lotte Reiniger silhouettes, Yuri Norstein / Hedgehog in the Fog — or asks what a style needs, how expensive it is, or whether a render looks like the style. Triggers on "in the style of", "make it look like South Park", "OverSimplified-style", "Kurzgesagt look", "silhouette film", "Monty Python cut-outs", "does this match the style", "style lint". Applies a style spec to an `an` scene, renders, measures the render against the spec's targets, and adjusts.
---

# an-style — script to cut-out animation in the style of X

A style here is a file: `styles/<name>.yaml` beside this skill, one per style. Each has three parts, and the difference between them is the whole point:

- **`live`** — settings that map onto shipped `an` features. Apply every one. `tests/test_style_specs.py` checks each key against the code (a real `Meta`, a `StylePack` whose roles are reachable, camera moves and easings that exist, a valid `EnvironmentDescriptor`), so if it is in `live`, `an` can do it.
- **`targets`** — `[low, high]` ranges for statistics measured on a render by `an.verify.style` (the style lint). Measured on one short clip per style, so they are starting points, not definitions.
- **`guidance`** — what the style needs and `an` does NOT do yet (sound layer, text, moves with no `an.motion` preset, surface treatments like the paper-gap shadow, transitions other than a hard cut). Apply by hand where you can; otherwise **tell the user which were omitted**. Never imply the render has them.

Styles shipped: `south_park`, `oversimplified`, `kurzgesagt`, `gilliam`, `reiniger`, `norstein`. The measurements and sources behind them are in `misc/docs/cutout_styles_research.md`. For the scene format itself, the `an` skill is the reference.

## The procedure

1. **Pick the spec** and **state its `cost_class` to the user before starting**, with its `cost_note`. `low` (South Park) and `low_to_medium` (OverSimplified) are shape vocabularies an agent can generate with `an character new --offline`. `high` and `very_high` (Reiniger, Kurzgesagt, Norstein) mean the art is the cost: `an` can stage and time them, but offline characters are stand-ins, and the user should know that before a render, not after. Also list the `guidance` items that will be missing.
2. **Set the meta** from `live.meta` into the ` ```yaml meta ` block: `fps`, `step_hz` when the spec has one (at 24 fps, `12` is on twos; the camera, blinks, swap channels including mouths, and descriptor `play` clips are never stepped), `default_easing` (the style's house curve — `linear` for South Park, `step` for Gilliam; every tween that names no easing takes it), and `style_pack` when the spec has one.
3. **Save the StylePack** from `live.style_pack` as `assets/styles/<name>.json` (an `an.styles.StylePack`; `json.dumps(pack.model_dump())`). Know its reach: roles recolour **environment presets and procedural rigs only**. SVG characters (anything from `an character new`) keep their drawn colours, and the compiler warns naming them — that warning is expected, not a bug. Colours the spec lists under `guidance` (outline, accents, card backgrounds) are not StylePack roles; the reachable roles are `skin`, `clothing`, `hair`, `leg`, `pupil`, `sky`, `ground`.
4. **Set the environment** from `live.environment`: a `preset` goes in the entity's `ref`; a `descriptor` is saved as `assets/environments/<name>/meta.json` (an `an.environments.EnvironmentDescriptor`) and referenced by that name. Plane `depth` is a parallax ratio (1.0 = character plane); a zoom is uniform across planes, so pair far plates with pans.
5. **Cut the script into shots** to `live.shots` (`mean_s`, `range_s`) and to the `cuts_per_min` target: shots = script duration × cuts_per_min / 60, roughly. Every shot boundary is a hard cut. Give each shot `camera: {move: <live.camera.default>}` and use only moves in `live.camera.allowed`. Follow the coverage and structure hints in `guidance` (two-shot then single close for South Park; narrated map, dramatization, date card for OverSimplified).
6. **Make the characters** per `live.characters`: `generate: offline` is `an character new <name> --offline`; `generate: promote` means hand-cut SVG art promoted with `an.characters.promote` (see `examples/promote_demo/`). `tint` is a `set` of the `tint` property on each character root at `at: 0` (black makes a silhouette). Frame them with `stage: {at: [x, y], scale: s}` on the entity; small characters barely move the frame statistics, so close framing matters for the cadence targets too.
7. **Author the motion** with tween lengths inside `live.tween_duration_s`; leave `easing` off a tween to take the scene's `default_easing`, and name one from `live.easing` only where the move wants a different curve (an overshoot pop-in). Cadence comes from the pattern of motion and holds, not from `step_hz` alone: South Park is short snaps on twos between holds while a character talks; OverSimplified is bursts on ones then long holds; Kurzgesagt is never still. Dialogue `[emotion]` tags drive brows, lids and the mouth form. `live.motion_presets` names the style's moves in `an.motion` (`pop_in`, `hop`, `shake`, `nod`, `point`, `slide_in`, `slide_out`, `squash_stretch`, `waddle`): write each as a `play` of its name in the ` ```yaml actions ` block — `{kind: play, target: stan, animation: waddle, args: {steps: 4, travel: 120}, start: 0.5}` — which builds it at the character's own rest pose (the `an` skill's *Motion presets* has the rules); presets keep their own easings and are stepped by `step_hz` like any tween. `guidance.motion_vocabulary_unmapped` lists the moves with no preset.
8. **Render**: `an render <dir> --strict-assets`.
9. **Measure**: `python -m an.verify.style <dir>/output/main.mp4 .claude/skills/an-style/styles/<name>.yaml` prints every metric and one warning per missed target, each with the knob that moves it. In Python, `an.verify.style.style_lint(mp4, spec, shot_durations=[...])`, or `StyleLintVerifier(spec)` as a `Verifier` (it takes the cuts from the IR, exactly). The CLI detects cuts from pixels, which misses dissolves; pass the shot list when you have it.
10. **Adjust and re-render** on the misses, then report the final numbers to the user next to the targets, and say which misses remain and why.

## Reading the lint

- `identical_frame_share` too high: more motion while characters talk (gesture beats of 0.25–0.3 s), closer framing, fewer dead holds. Too low: stepped timing, shorter tweens, real holds between moves.
- `one_frame_interval_share` too low for OverSimplified or Gilliam: drop `step_hz`. Too high for South Park: set it.
- `cuts_per_min` and `mean_shot_s` are coarse on a short clip: under 30 s, one cut moves `cuts_per_min` by 60 / duration, and the lint says so. An 8 s clip cannot hit South Park's 10–14 cuts/min and 3–5.5 s mean shot at once; report that rather than contort the edit.
- Palette targets (`mean_saturation`, `dark_pixel_share`, `top16_colour_coverage`) move with the backdrop (StylePack `sky`/`ground`, plane fills) and the art, not with timing.
- The estimator sees change as mean grey difference over a 320×180 frame. A mouth swap on a small character is below its threshold: that is how the targets were measured too, so it is consistent, but it means lip-sync alone cannot lower the held-frame share.

## Worked example

`misc/demos/build_demos.py`'s `south-park-style` demo applies `styles/south_park.yaml` to a four-line script (two 4 s shots: a two-shot, then a single close), renders it, and lints it. It predates `an.motion` and `default_easing`, so its moves are hand-written tweens with their easings spelled out. Its first pass with only the `live` settings and default framing measured `identical_frame_share` 0.96 against a 0.55–0.70 target; closer framing plus arm-and-head gesture beats while each character talks brought it to about 0.64, inside the range. `cuts_per_min` stays at 7.5 (one cut in 8 s), a structural miss of a short clip.

## What never to do

- Never put a `guidance` item in the scene as if it worked (a `text:` block, a `voice_fx`, an `outline` role). Name every one you could not express to the user as omitted.
- Never claim a render "is in the style of X" without the lint numbers beside the targets.
- Never commit study footage of a real show or film anywhere (copyright). The targets came from clips kept outside every repository.
- Never tune a spec's `targets` to make a render pass. Targets change only with a new measurement of the real style, recorded in the research doc.
