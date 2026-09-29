# Cut-out animation styles for `an` — techniques of South Park, OverSimplified, Kurzgesagt, Gilliam, Reiniger and Norstein

*2026-09-29 · scope: production technique, measured screen statistics and a gap analysis against `an` (main @ 13b20a83) for six named styles · requested for: the goal "give an an-enabled agent a script and get a cut-out animation in the style of X" · the style specs built from it live in `.claude/skills/an-style/styles/`, and the measurement is `an.verify.style`*

Tags: **[L n]** = stated by reference n; **[M]** = measured on a short study clip (section 3; the clips are copyrighted footage and are not in the repo); **[U]** = background knowledge or inference I could not verify this session. Untagged numbers are estimates.

## Summary and recommendation

The six styles differ less in engine requirements than in three other things: the cadence of change (what moves on ones, what on twos, how long the holds are), the surface finish (flat fill, paper gap, silhouette, painted glass) and the layers around the picture (sound, text, maps, transitions). `an` already covers the engine core of a cut-out look: rigid rigs with swap channels, visemes, an expression solver, stepped timing, pans, multiplane parallax, StylePack colours, props, motion blur. It lacks mostly the layers around the picture, plus a document that bundles a style's choices so an agent can apply them and check its own output.

Recommendation, in order:

1. Build a **`StyleSpec`** (a superset of the shipped StylePack) carrying colour roles, `step_hz`/cadence, default easing, camera preferences, shot-length and cut-rate targets, and character-construction rules. Add a **style-lint verifier** that measures a render with the statistics used here (unique-frame ratio, cadence histogram, cuts/min, shot length, palette). It rests on two existing seams (StylePack, the `Verifier` protocol) and closes the loop "apply style, render, measure, adjust". The measurement code was about 100 lines; it is now `an.verify.style` (see "What shipped from this" below).
2. Add a **sound layer** (music bed, SFX cues on action events, ducking, a voice-effect chain such as pitch shift). All six styles are defined as much by sound and pacing as by picture, and `an` renders dialogue audio only.
3. Add **on-screen text primitives** (title and date cards, callout labels, captions) with bundled open-licence fonts. OverSimplified, Kurzgesagt and Reiniger (intertitles) lean on them and `an` has no text node. A parallel worker is adding stroked paths and arrows for maps.
4. Add a **motion library** (`play` presets: waddle-walk, hop, pop-in, whip, shake, point, nod, squash-stretch) and a scene-level default easing. Gilliam's rule is "swift, sudden movements are much simpler" [20]; South Park is "intentionally jerky" [1]. Both are timing vocabulary, not engine features.
5. The cheapest style to hit today is **South Park**: rigid shape characters, a mostly locked camera, flat backgrounds, and expressive machinery (visemes, brows, lids, stepped timing) that is already shipped. It lacks the paper-gap shadow, the pitch-shifted voice and a motion library. OverSimplified is next (needs text, map fills, crowds, SFX). Kurzgesagt is the most expensive, and the cost is art volume (about 200 assets per 10-minute video [9]) more than engine.

## What already exists (in-house)

- `an` itself, read-only: `CLAUDE.md` capability map and `.claude/skills/an/SKILL.md` [23]. Section 5 is against that state.
- `misc/docs/wave6_research.md` [23] cites South Park's missing standard half-lid (drawn per shot) and says OverSimplified and Crash Course practice was UNVERIFIED. This report does not settle the OverSimplified question: what follows is public description plus measurement, not insider practice.
- `misc/docs/Real Character Art for an — A 2D Cutout Pipeline Upgrade Plan.md` [23] recommends the "South Park / Adventure Time approach" (one dominant tone per part, colour before line) at 300 px character height.
- `ir discover reports` returned only unrelated reelee/guided reports. There is no in-house report on these six styles.

## What shipped from this

- **Style specs, as files, not yet as a document type.** `.claude/skills/an-style/styles/<style>.yaml`, one per style above, each split into `live` (settings that map onto shipped features: `meta.fps`, `meta.step_hz`, `meta.style_pack` with the StylePack's real roles `skin`, `clothing`, `hair`, `leg`, `pupil`, `sky`, `ground`, an environment preset or plane descriptor, camera moves, easings, tween and shot lengths, character generation and `tint`), `targets` (what the lint measures) and `guidance` (everything `an` does not do yet, stated as such). `tests/test_style_specs.py` checks every `live` key against the code. Several colours in the draft blocks (`outline`, `accent_*`, `card_bg`, `highlight`, `silhouette`, `mid`) are not StylePack roles; they moved to `guidance`. A StylePack reaches environment presets and procedural rigs only, not SVG characters.
- **The style lint.** `an.verify.style` ports the cadence, cut and palette statistics (identical-frame share, pose changes per second, the one/two/three-plus change-interval histogram, longest hold, cuts per minute, mean shot length, mean saturation, dark-pixel share, top-16 colour coverage) with numpy and the ffmpeg binary only; the camera-motion (`phaseCorrelate`) and k-means palette parts were left out because they need OpenCV and scikit-learn. On the six study clips the port reproduces the original script's numbers to three decimals for every cadence and cut statistic (palette statistics within 0.004, because the original sampled pixels at random). One change: the noise floor is capped at 1.0 grey level, because a clip whose every frame changes by the same amount otherwise measures as all holds; the uncapped floor was at most 0.16 on all six clips, so no target moved. `StyleLintVerifier` is a `Verifier`, takes cuts from the IR (exact for an `an` render), and reports a failure to measure above `info`.
- **The procedure**: the `an-style` skill (script → pick a style → state the cost class → set meta and StylePack → shots to the cut-rate and shot-length targets → characters → render → lint → adjust).
- **A worked example**: the `south-park-style` demo in `misc/demos/build_demos.py`.

Not built, and ranked in section 7 and tracked in [an#163](https://github.com/thorwhalen/an/issues/163): `StyleSpec` as a versioned document the compiler reads, a sound layer, text, surface treatments, transitions. The motion library (gap 4) has since shipped as `an.motion` (an#165); the specs map each style's moves to its presets under `live.motion_presets`.

## 1. Evidence and its limits

Web sources were fetched through a summarising fetcher. Several pages (South Park Fandom wiki, TV Tropes, Toolfarm) refused the fetch, so some claims rest on search-result snippets and are marked. Public primary sources on these styles are thin, so I measured six short clips: one 30–60 s window per style, YouTube-transcoded at 360p, windows chosen by me. Each number is an example of a style, not its definition.

## 2. Comparison table (measured; details in section 3)

| Style | Clip fps | Pose changes / s | Change intervals 1 / 2 / 3+ frames | Frames identical to previous | Cuts / min | Mean shot (s) | Mean saturation | Flat-colour coverage (top 16 of 4-bit colours) |
|---|---|---|---|---|---|---|---|---|
| South Park | 29.97 | 10.8 | 50% / 24% / 26% | 64% | 12.4 | 4.2 | 0.38 | 0.60 |
| OverSimplified | 29.97 | 12.3 | 91% / 7% / 2% | 59% | 9.0 | 6.0 | 0.27 | 0.49 |
| Kurzgesagt | 30 | 22.9 | 99% / 1% / 0% | 24% | 7.0 | 7.5 | 0.69 | 0.61 |
| Gilliam | 25 | 16.2 | 77% / 17% / 6% | 35% | 2.0 | 20.0 | 0.35 | 0.38 |
| Reiniger | 30 | 21.2 | 93% / 6% / 1% | 29% | 4.0 | 12.0 | 0.74 | 0.74 |
| Norstein | 25 | 13.8 | 59% / 29% / 9% | 45% | 6.0 | 8.6 | 0.25 | 0.66 |

"Change intervals" are gaps between successive changed frames. A shot where several parts move independently reads as "on ones" even if each part is on twos, so the number says how often the picture as a whole updates, not how each rig is timed. Reiniger, Gilliam and Norstein are uploader transcodes of unknown source rate (Prince Achmed is given as 24 fps, some sources say 18 [16]), so their cadence rows are weak. South Park's excerpt is 29.97 fps, probably a 24p source with pulldown, which manufactures some 2-frame intervals. The 3-frame-and-longer intervals and the 64% identical-frame share are not explained by pulldown alone.

## 3. Study clips and measurements

Six short study clips, kept outside every repository for study use only and never committed (copyright). Downloaded 2026-09-29, at most 360p, at most 60 s each.

| Clip | Source | Window |
|---|---|---|
| southpark | [South Park S20E03 excerpt](https://www.youtube.com/watch?v=kRjHSJVqoac) | 0–30 s |
| oversimplified | [The American Revolution, Part 1](https://www.youtube.com/watch?v=gzALIXcY4pg) | 300–360 s (a first sample at 60–120 s hit a sponsor segment with 3D maps and was discarded; seven downloads for six clips) |
| kurzgesagt | [The Paradox of an Infinite Universe](https://www.youtube.com/watch?v=isdLel273rQ) | 60–120 s |
| gilliam | [Monty Python, Cartoon Religions Ltd.](https://www.youtube.com/watch?v=jDReTBFTxC8) | 0–60 s (last 4 s live action) |
| reiniger | [Prince Achmed (1926), Wak-Wak excerpt](https://www.youtube.com/watch?v=C5SwrNtePmQ) | 0–60 s (subtitled upload) |
| norstein | [Hedgehog in the Fog](https://www.youtube.com/watch?v=mQqgViGenvk) | 60–120 s (burned-in subtitles) |

Method (a measurement script, since ported as `an.verify.style` minus the camera-motion and k-means parts, and a texture script): decode at 320×180; a frame counts as changed above `max(0.25, 2.5 × the 10th-percentile noise floor)` mean absolute difference. A cut is a frame where the 8×8×8 colour-histogram L1 distance exceeds 0.6 and the mean difference exceeds 8, so dissolves and morphs are missed and Gilliam's and Norstein's cut counts are floors. Global camera motion is `cv2.phaseCorrelate` between changed pairs. Palette is k-means (k=8) in Lab. Contact sheets (12 frames per clip) were made for visual reading; they are not in the repo either. "[M, sheet]" below means read off a contact sheet. Median global shift is near zero in all six clips (0.03–0.28 px at 320 wide). Steps with more than 1 px of global shift: 21% Norstein, 12% Kurzgesagt, 2% OverSimplified (21% in the discarded sponsor window). The texture metric did not separate the styles at 360p after transcoding, so South Park's paper grain is not measurable here.

## 4. Per-style technique

### 4.1 South Park (digital emulation of cut-out)

**Lineage.** Inspired by Gilliam's paper cut-outs [1]. The pilot was real construction-paper stop motion under an overhead camera: hundreds of cut-outs "including individual mouth shapes and many of the characters in several different sizes", three months, non-speaking characters rarely moved to save time [3]. Later episodes were computer-made: characters scanned and redrawn in CorelDRAW, animated in Alias|Wavefront PowerAnimator on SGI workstations, then Maya from season five [1][2].

**Character construction.** Flat characters on a virtual plane in 3D space with paper texture applied digitally [2]. The "no-platen" shadow look comes from separating each part by a small gap, as in real cut-out shooting [2]. Characters are simple geometric shapes and flat colour patches, mostly shown from one angle [1]. Early seasons drew the half-lid per shot [23]. Head, torso and limbs are rigid pieces [U]. In the clip, heads appear front and three-quarter [M, sheet]. A forum account says Maya Set Driven Keys switch mouth, hand and head variants [5] (hobbyist source).

**Mouth and lip-sync.** The pilot used a cut-out per mouth shape [3]. A Maya rig switches mouth art by driver [5]. In the clip 50% of change intervals are one frame [M], consistent with mouth swaps at frame rate while the body holds [U]. A set of roughly nine to twelve shapes is typical for mouth-swap lip-sync [U].

**Expressions.** Brows and lids carry most of it; some characters' brows appear only when worried or angry [23]. Eyes are two ovals with pupil dots plus a mouth [U].

**Timing.** "Intentionally jerky" [1]. In the clip: about 10.8 pose changes/s, 64% of frames identical to the previous, hold runs up to 45 frames, 24% of intervals twos and 14% threes [M]. That reads as mixed twos and threes on bodies with mouths on ones. Production is a six-day cycle, episodes typically finished in a week (sometimes 3–4 days), about 70 staff [1][4].

**Motion vocabulary.** Whole-piece slides and rotations, waddle walks, hop-turns, mostly pose-to-pose [U].

**Camera.** Mostly locked off in the clip: median global shift 0.11 px, 3% of steps above 1 px [M]. Later seasons use more virtual-camera depth [U].

**Backgrounds and layering.** Flat layered sets; in the clip a fast-food interior with a window plane behind the characters [M, sheet]. Paper-pilot and computer footage differed visibly until the 2009 HD re-render [3].

**Colour and line.** Primary-ish flat patches [1]. Measured palette: tan `#d7b887`, grey `#c0c6c7`, teal `#67948d`, ochre `#987a43`, near-black `#231316`, brown `#604c36`, red `#7a0a19`, white `#e2e2e2`. 8% near-black pixels (thin dark outline), 0.38 mean saturation [M].

**Text.** Rare: location cards and fake TV graphics [U].

**Transitions.** Hard cuts [U]. 12.4 cuts/min, mean shot 4.15 s (n=7, one dialogue scene) [M].

**Sound.** Voice pitch is raised to sound like fourth graders [1]. Episodes are written and voiced in the last days before air [4].

### 4.2 OverSimplified

**Construction.** Blocky bodies, stick limbs and oversized heads, expressive brows and mouths, no nose or ears, period clothing to tell figures apart [7]. From the WWII videos on, heads got more detail and body shapes more variety [8 (snippet)]. Made in After Effects and Photoshop [7]. In the clip, crowds are dozens of identical pale stick-and-ball figures, soldiers in red coats, on a flat illustrated street set [M, sheet]. Whether figures are tool-rigged or hand-keyed is UNVERIFIED.

**Mouth and expressions.** Not established from sources. In the clip two speaking figures at a table show a small mouth and brow set [M, sheet].

**Timing.** 12.3 pose changes/s, 59% of frames identical, but 91% of change intervals are one frame [M]. That is burst-and-hold: a movement runs on ones for a few frames and then holds (hold runs up to 63 frames). This differs from South Park's steady on-twos feel.

**Camera.** Push-ins on still paintings and prints (a Boston Massacre print in the clip) and pans over maps [M, sheet]. Camera use is scene-dependent: 2% of steps above 1 px shift in this window, 21% in the sponsor window with 3D maps [M].

**Backgrounds.** Detailed; described as a "stage play" rather than cinematic [7]. Flat illustrated sets with period buildings [M, sheet].

**Colour and line.** Flat vector figures on illustrated backgrounds, white cards with black text, strong red/blue territory fills on maps [M]. Palette: off-white `#f0ede7`, grey `#a7b1b9`, near-black `#040404`, brick `#ba5f31`, sage `#67796a`, brown `#5f432f`, dark `#312923`, tan `#cda469`; 0.27 saturation, 20% dark pixels [M].

**Text, maps.** Date cards on black ("DECEMBER 16TH 1773") in bold white sans, small speech text beside figures, top-of-frame bulleted captions [M, sheet]. Maps with flags and shaded territories recur [8 (snippet)][M].

**Transitions.** Hard cuts plus bait-and-switch visual gags [7]. 9 cuts/min, mean 6.0 s, median 4.7 s (n=10) [M].

**Sound.** One narrator performs all character voices in third person; background music from the Kevin MacLeod Creative Commons library [7]. SFX density is high [U].

**Pacing.** Alternates narration and "humorous dramatization" [7]; videos are long (Part 1 listed at 908 s) [U, search listing].

### 4.3 Kurzgesagt

**Construction.** Flat 2D vector art from geometric shapes; characters "rigged with joints so they can be moved smoothly"; artwork "broken down into hundreds of individual layers" [9]. Illustrator for art, After Effects for animation, Cinema 4D more recently for 3D elements [9][10]. Duik is the common After Effects rigging tool [12], but no source ties it to Kurzgesagt. The studio grew from a solo project to about seventy people [11].

**Mouth and expressions.** Characters are birds and blobs with beaks or simple mouths, mostly seen at a distance and not lip-synced [U, clips]. Narration is voiceover only.

**Timing.** 22.9 pose changes/s, 99% of intervals on one frame, only 24% of frames identical [M]. The picture is almost never still: star twinkle, particles, glow pulses and drifting parallax run under the foreground action. The hold is the exception, the opposite of South Park's cadence.

**Motion vocabulary.** Smooth eased tweens with overshoot and settle, pop-in by scale with bounce, drawn-on lines, morphing shapes [U].

**Camera.** Continuous virtual camera with pushes, pulls, pans and parallax; some 3D [10][U]. 12% of steps above 1 px shift [M].

**Backgrounds.** Deep space-style gradient fields with many small layered elements at different depths [9][M, sheet].

**Colour and line.** No outlines; flat fills with soft gradients and glows; strong saturation contrast. Palette: navy `#060e3d`, black `#010210`, mint white `#daf7ea`, indigo `#291275`, plum `#453750`, violet `#5e2cb5`, orange `#d96739`, sky `#5c9ec2`; 0.69 saturation, 35% dark pixels [M]. About 200 unique assets per 10-minute video [9].

**Text, infographics.** Rounded labels with coloured borders, diagrams with animated lines and arcs, comparison panels [M, sheet]; infographics are a listed discipline [10].

**Transitions.** Mostly continuous camera and match-moves; the two sub-second "shots" in the clip are flashes or wipes [M]. 7 cuts/min, mean 7.5 s, median 6.3 s (n=8) [M].

**Sound.** Narrator Steve Taylor since 2013, multiple takes for pacing and emphasis; custom music by Epic Mountain; sound design by Max Frisch since 2017 [9][10].

**Pacing.** Ten-minute videos, 1200+ hours each, about a dozen script revisions, weeks to years of research [9][10].

### 4.4 Terry Gilliam (Monty Python's Flying Circus)

**Construction.** "Bits of paper in front of a camera" rather than cels [20]. Found images (old photographs, engravings, magazine cut-outs) recombined into surreal scenes, "Max Ernst meets Mad Magazine" [20]. Limbs cut from photographs and joined with pins [13]. Light from above, unlike Reiniger [13]. Scenes are photomontage plates with a few moving pieces [M, sheet].

**Mouth and expressions.** Hinged or swapped mouth pieces; in the clip a photographic pink face with a hinged mouth and a cut-open head [M, sheet]. Expression comes from grotesque juxtaposition, not acting.

**Timing.** "Swift, sudden movements are much simpler"; graceful movement "à la Walt Disney is damned near impossible" [20]. Clip (25 fps): 16.2 changes/s, 77% ones and 17% twos, 35% identical, hold runs up to 37 frames [M]. Fast snaps with abrupt transitions.

**Motion vocabulary.** Beheadings, drops, pop-ups, slides from screen edges, object-to-object morphs [20][M].

**Camera.** Locked off; median global shift 0.03 px [M]. The artwork moves in front of the camera.

**Backgrounds.** Photographic and engraved plates, often one flat plate plus movers [M, sheet].

**Colour and line.** No outline; photographic tonal range; high texture (flat residual noise 0.95 versus 0.31–0.46 in the others) and 212 distinct colours over 0.1% coverage versus 77–167 [M].

**Text.** Period-type titles ("CARTOON RELIGIONS LTD"), hand-lettered signs [M, sheet].

**Transitions.** Objects transform across the cut [M, sheet][U]; the 2/min cut count is a floor.

**Sound and pacing.** Comic SFX and Python voices [U]. Shots run long (mean 20 s in the clip) because the shot is the gag [M]. Gilliam calls the technique the "quickest, easiest form of animation that I know" [20][21].

### 4.5 Lotte Reiniger (silhouette films)

**Construction.** Figures cut from black cardboard and thin lead, "every limb being cut separately and joined with wire hinges" [14]; puppets of 20–50 pieces joined with lead wire, with tracing paper [15]. Backgrounds are layers of transparent paper on a glass table lit strongly from below, "which makes the wire hinges disappear and throws up the black figures in relief"; camera overhead [14]. Pure silhouettes: no interior shading, features as negative shape [M, sheet].

**Mouth and expressions.** Expression is pose and profile; no mouth animation as such [M, sheet][U].

**Timing.** Photographed "movement by movement"; timed to music by "carefully measuring the sound track" and computing the number of shots "according to the musical value" [14]. Prince Achmed: 65 min at 24 fps, three years [16]. Clip: 21.2 changes/s, 93% ones (transcode, source cadence unknown) [M].

**Motion vocabulary.** Naturalistic, closely studied walks and flights ("a study of natural movement is very important") [14]; smooth secondary motion in birds and foliage [M, sheet].

**Camera and layering.** An early multiplane rig of backlit glass planes in front of a camera with a manual shutter, 1923–26 [15][17]. Backgrounds from sand, paint and soap on layered negatives, pinholed cardboard for stars, tissue for waves, silver paper for moonlit water [16]. In the clip the camera is locked off and depth comes from layer stacking [M].

**Colour and line.** Tinted monochrome; restored prints reinstate the tinting [16]. Measured: 28% pure black plus blues (`#011945`, `#048def`, `#0068e5`, `#0aaff1`), 0.74 saturation, 46% dark pixels, top-16 coverage 0.74, the flattest of the six [M].

**Text.** Intertitles in an ornamental script, cyan on dark blue with a geometric border [M, sheet].

**Transitions.** Dissolves between painted plates [U]. 4 cuts/min, mean 12 s (n=5) [M].

**Sound.** A composed score (Wolfgang Zeller) with shot counts computed to the music [14][16]; no dialogue.

### 4.6 Yuri Norstein

**Construction.** Figures painted on celluloid with limbs cut apart, leaving blank cel around the figure to reproduce the texture of drawn animation [18]. Characters and backgrounds are broken into pieces on different glass sheets [19]. The look moved from "flat cut-outs" to "smoothly-moving paintings" through the 1970s [18].

**Mouth and expressions.** Little or no lip-sync; expression is body angle, gaze and light [M, sheet][U].

**Timing.** Extremely slow production: three people finished ten minutes of *The Overcoat* in two years, and he was dismissed in 1985 for working too slowly [18]. Clip (25 fps): 13.8 changes/s, 59% ones, 29% twos, 9% threes, 45% identical frames [M], a genuine mix of ones and twos.

**Camera and multiplane.** The camera looks down on glass planes about a meter deep, one every 25–30 cm, each movable sideways and toward or away from the camera [18]. The fog in *Hedgehog in the Fog* is thin tracing paper: over the hedgehog it is nearly invisible, several layers closer to the camera the hedgehog disappears [19]. Fog and depth come from layered translucency, not a blur filter [19]. 20% of steps in the clip show more than 1 px global shift: slow drifts and pushes [M].

**Backgrounds.** Painted, textured, dark; fog, foliage and hedgehog are separate planes [19][M, sheet].

**Colour and line.** Muted: 0.25 saturation, 63% dark pixels, mostly violet-grey to sepia [M]. No outline; soft edges.

**Text, transitions, sound.** No text in the film (the clip's text is burned-in subtitles). Slow dissolves and fog fades [M, sheet][U]; 6 cuts/min, mean 8.6 s, median 5.5 s [M]. Sparse naturalistic sound [U].

## 5. Gap analysis against `an`

Baseline is `an`'s `CLAUDE.md` and `SKILL.md` [23], with cheap checks in the source (easing table, Meta fields, audio pipeline, runtime filter policy).

**Already expressible.** Rigid multi-part rigs with swap channels (mouth shapes, hands, heads, turnaround views are one mechanism), visemes with co-articulation, expression presets, brows and lids, gaze and saccades, procedural fallback characters. Stepped timing (`Meta.step_hz` / `Shot.step_hz`; 15 at 30 fps is twos, 10 is threes; swap channels, blinks, camera exempt). Easing table `linear`, `ease`, `ease_in`, `ease_out`, `ease_in_out`, `step`, plus 4-point cubic-Bézier for numeric channels, so an overshooting Bézier is legal. Nine camera moves plus explicit keys, multiplane planes with a depth ratio, StylePack roles (`skin`, `clothing`, `hair`, `leg`, `pupil`, `sky`, `ground`), props, `tint` (a per-node multiply, so black tint gives a silhouette), alpha entrances, frame-clock motion blur, dialogue audio with content-hash caching.

**Absent, verified in the tree.** No text node in the IR. No shot-transition concept (`render.py` concatenates per-shot mp4s with ffmpeg). No music or SFX track in `an/audio`. No runtime filters, by policy: `runtime.js` comments say a grain filter "in a later wave would randomise every frame".

| Need | Styles | What is missing |
|---|---|---|
| Style bundle and self-check | all | StylePack covers colour roles only; nothing bundles cadence, easing, camera, shot length, construction rules, and nothing measures a render against a target |
| Sound layer | all (central for OverSimplified, Kurzgesagt, Reiniger, Gilliam) | music bed, SFX cues, ducking, voice FX such as pitch shift |
| On-screen text | OverSimplified, Kurzgesagt, Reiniger, Gilliam, South Park (cards) | title and date cards, labels, captions, speech text, bundled fonts |
| Motion vocabulary | all | `play` presets (walk, hop, pop-in, whip, shake, point, squash-stretch), scene-level default easing |
| Deterministic surface treatment | South Park, Gilliam, Reiniger, Norstein, Kurzgesagt (glow) | outline, drop shadow, grain, glow, soft edge, without runtime filters |
| Crowds and map fills | OverSimplified, Kurzgesagt | instancing macro; region fill-colour tweens, unit icons (strokes and arrows are with the parallel worker) |
| Transitions | Reiniger, Norstein, Gilliam (morph), Kurzgesagt (match-moves) | dissolve, fade, wipe at the concat stage, or shot overlap |
| Depth-aware zoom, shake, follow | Kurzgesagt, Norstein | the dolly (deferred in an#110), shake, track-an-entity |
| Views and head turns | South Park, OverSimplified | a facing convention and mirror helper; the swap machinery exists |
| Photo cut-outs | Gilliam | public-domain image ingestion and segmentation (licence question) |
| Hierarchical puppets | Reiniger | rigs are flat today; a 20–50 piece hierarchy is untested |

**Determinism does not forbid the surface treatments.** A paper-gap shadow is an offset darkened duplicate of the sprite, an outline a slightly scaled darker duplicate behind it, grain one static texture plane, a glow an additive-blend gradient sprite. All are ordinary scene nodes with no per-frame randomness. Build them as compile-time expansions of a `StyleSpec` field, not as runtime filters.

**Cost to hit today**

| Style | Feasible today | Missing, in order | Art cost |
|---|---|---|---|
| South Park | rigid shape cast, dialogue, visemes, brows and lids, `step_hz` 12 at 24 fps, locked camera, flat sets, StylePack | motion presets, pitch-shift voice, paper-gap shadow and grain, location cards | Low (procedural or `--offline` characters are close) |
| OverSimplified | stick figures, stage sets, pans and push-ins over stills as props, burst-and-hold tweens | text cards, map fills and crowds, SFX and music, narrator-voices-all convention | Low to medium |
| Reiniger | silhouette via black `tint`, blue-tinted backdrop planes with depth ratios, slow pans | intertitle text, dissolves, score, deep puppet hierarchy | High for puppets; engine mostly present |
| Norstein | multiplane fog via alpha planes with `depth`, slow pushes | depth-aware zoom, soft edges without filters, dissolves | Very high (painted texture art) |
| Gilliam | hard-cut snap timing, pop-ups by alpha and position, static camera | photo cut-out ingestion, morph transitions, SFX | Medium if images are public-domain |
| Kurzgesagt | layered planes, pans, flat vectors | ambient motion library, glow, text and diagrams, sound, dolly | Very high (about 200 assets per video [9]) |

## 6. What this suggests about "in the style of X"

The styles separate on two measurable axes: the share of held frames (South Park and OverSimplified about 60% identical, Kurzgesagt and Reiniger under 30%) and how changes are grouped (South Park mixed twos and threes, OverSimplified bursts on ones). A spec carrying a cadence histogram and hold ratio can be checked by machine. One carrying only `step_hz` cannot express OverSimplified's burst-and-hold, because `step_hz` resamples all tweens onto one grid.

For the cheap styles the art is a constrained shape vocabulary an agent can generate. For Kurzgesagt, Norstein and Reiniger the art is the cost and the engine gap is secondary. An agent should say which case a request falls under before starting.

Sound, text and transitions recur in every style, so building them once as style-neutral features is worth more than any style-specific feature.

## 7. Ranked cross-style feature gap list

Value = how many styles need it and how much of the look it carries. Cost = engineering effort in `an`, not art. Rank is value over cost; the "seam" column is where it would land without a redesign.

| # | Feature | Styles | Value | Cost | Seam in `an` |
|---|---|---|---|---|---|
| 1 | `StyleSpec` document bundling colour roles, cadence, default easing, camera preference, shot targets, construction rules, plus a style-lint verifier comparing a render to `targets` | all six | High: it is the "in the style of X" deliverable and closes the loop | Low to medium: StylePack and the `Verifier` protocol exist; measurement code exists (now `an.verify.style`) | extend `an/styles.py`; new verifier in `an/verify/` |
| 2 | Sound layer: music bed, SFX cues on action events, ducking under dialogue, voice-effect chain (pitch shift) | all six | High: half of every style | Medium: ffmpeg mixing at the concat stage; asset licences (`an-dev-licensing`) | `an/audio/` plus `render.py` mux |
| 3 | On-screen text primitives: title and date cards, labels, captions, speech text, bundled open-licence fonts | OverSimplified, Kurzgesagt, Reiniger, Gilliam, South Park | High | Medium: text rasterisation must stay deterministic; font licensing | new visual kind in the cutout compiler and runtime |
| 4 | Motion library: `play` presets (waddle-walk, hop, pop-in, whip, shake, point, nod, squash-stretch) and a scene-level default easing | all six | High | Low to medium: `play` resolution and the easing table exist | `an/characters/play.py`, `Meta` field |
| 5 | Deterministic surface treatments as compile-time expansions: outline, paper-gap shadow, static grain plane, additive glow sprite | South Park, Gilliam, Reiniger, Norstein, Kurzgesagt | Medium | Medium: no runtime filters, so duplicates and static textures only | `StyleSpec` field expanding in the compiler |
| 6 | Crowd instancing macro and map layer (region fill tweens, unit icons) | OverSimplified, Kurzgesagt | High for history and explainer content | Medium: arrows and strokes are with the parallel worker | new macro over `entities`; map plane kind |
| 7 | Shot transitions: dissolve, fade, wipe, morph-across-cut at the concat stage | Reiniger, Norstein, Gilliam, Kurzgesagt | Medium | Low to medium: per-shot mp4s need an overlap or xfade in `_ffmpeg_concat` | `an/render.py` |
| 8 | Depth-aware zoom (dolly), camera shake, follow-entity | Kurzgesagt, Norstein | Medium | Medium: an#110 deferred the dolly with a reason (zoom multiplies the whole composed expression) | `_add_camera_clips`, `_add_parallax_clips` |
| 9 | Facing and turnaround convention plus mirror helper and head-turn library | South Park, OverSimplified | Medium | Low: swap sets and `scale_x = -1` already work; this is convention and art-package contract | `an-art-package` skill, `asset_sets` |
| 10 | Silhouette render mode (black tint on all parts, face off, tinted backdrop planes) as a named preset | Reiniger | Low to medium | Low: `tint`, `face_overlay` and planes exist | `StyleSpec` field |
| 11 | Hierarchical puppet rigs (20–50 pieces, nested bones) | Reiniger | Medium | Medium to high: rigs are flat today | `an/characters/schema.py`, rig contract |
| 12 | Photo cut-out ingestion (public-domain image to segmented, rigged parts) | Gilliam | Niche to medium | High: segmentation model and licence risk | `an.characters.promote`, `an-dev-licensing` |

Reading the list: items 1 to 4 are style-neutral and unlock all six styles, so they come before any style-specific work. Items 5 to 8 are shared by two to five styles. Items 9 to 12 are single-style or already mostly expressible.

## Open questions

- Per-rig cadence: my measurement is per frame, not per body part. A per-region measurement (mouth versus body) on a locked shot would settle whether South Park's mouths are on ones and bodies on twos, which I infer rather than show.
- South Park's mouth-shape count, head-turn set and walk construction were not found in accessible sources; the AWN article is a 1998-era overview [2].
- OverSimplified's rigging practice and frame rate are unsourced.
- Kurzgesagt's rigging tool is unverified.
- Licences: music and font choices need `an-dev-licensing` review before anything is bundled. Kevin MacLeod tracks are Creative Commons [7]; attribution in the output is likely required.

## REFERENCES

[1] [South Park — Wikipedia](https://en.wikipedia.org/wiki/South_Park)
[2] [Dig This! Using computers to simulate cut-out animation techniques: South Park and Blue's Clues — Animation World Network](https://www.awn.com/animationworld/dig-using-computers-simulate-cut-out-animation-techniques-south-park-and-blues-clues)
[3] [Cartman Gets an Anal Probe — Wikipedia (pilot production)](https://en.wikipedia.org/wiki/Cartman_Gets_an_Anal_Probe)
[4] [6 Days to Air: The Making of South Park — Wikipedia](https://en.wikipedia.org/wiki/6_Days_to_Air:_The_Making_of_South_Park)
[5] [2D SouthPark style animation with Blender? — BlenderArtists forum (low reliability)](https://blenderartists.org/t/2d-southpark-style-animation-with-blender/537023)
[6] [Interview With South Park Animator Edgar Tellez — Concept Art Empire (workflow only, no technical parameters)](https://conceptartempire.com/edgar-tellez-interview/)
[7] [OverSimplified: a YouTube empire — Creator Handbook](https://www.creatorhandbook.net/oversimplified-a-youtube-empire/)
[8] [OverSimplified — YouTube Wiki (search-result snippet only; not fetched)](https://youtube.fandom.com/wiki/OverSimplified)
[9] [The Incredible Amount of Work Behind Kurzgesagt's Beautiful Animated Videos — 10.studio](https://10.studio/the-incredible-amount-of-work-behind-kurzgesagts-beautiful-animated-videos/)
[10] [About our YouTube channel — Kurzgesagt](https://kurzgesagt.org/what-we-do?visit=videos)
[11] [Kurzgesagt — Wikipedia](https://en.wikipedia.org/wiki/Kurzgesagt)
[12] [Duik (Angela) — RxLaboratory, GitHub (After Effects rigging tool; no source ties it to Kurzgesagt)](https://github.com/RxLaboratory/Duik)
[13] [Cutout animation — Wikipedia](https://en.wikipedia.org/wiki/Cutout_animation)
[14] [Scissors make films: Lotte Reiniger on creating her magical animations — BFI Sight and Sound](https://www.bfi.org.uk/sight-and-sound/features/scissors-make-films-lotte-reiniger-creating-her-magical-animations)
[15] [Lotte Reiniger — Wikipedia](https://en.wikipedia.org/wiki/Lotte_Reiniger)
[16] [The Adventures of Prince Achmed — Wikipedia](https://en.wikipedia.org/wiki/The_Adventures_of_Prince_Achmed)
[17] [Multiplane camera — Wikipedia](https://en.wikipedia.org/wiki/Multiplane_camera)
[18] [Yuri Norstein — Wikipedia](https://en.wikipedia.org/wiki/Yuri_Norstein)
[19] [A Guide to Yuri Norstein: Hedgehog in the Fog and Beyond — Animation Obsessive](https://animationobsessive.substack.com/p/a-guide-to-yuri-norstein-hedgehog)
[20] [Terry Gilliam Reveals the Secrets of Monty Python Animations — Open Culture](https://www.openculture.com/2014/07/terry-gilliam-reveals-the-secrets-of-monty-python-animations.html)
[21] [How-To: Cut-out Animation with Monty Python's Terry Gilliam — Make:](https://makezine.com/article/craft/how-to_cut-out_animation_with/)
[22] [Limited animation — Wikipedia](https://en.wikipedia.org/wiki/Limited_animation)
[23] In-house: [thorwhalen/an](https://github.com/thorwhalen/an) at main 13b20a83 — `CLAUDE.md`, `.claude/skills/an/SKILL.md`, `misc/docs/wave6_research.md`, `misc/docs/Real Character Art for an — A 2D Cutout Pipeline Upgrade Plan.md`
