# Study the masters: the methods behind cut-out animation, from 38 sources

*2026-10-01 · scope: production methods (rig, replacement, speech, face, locomotion, timing, staging, camera, surface, FX, text, transitions, sound) of 38 cut-out and adjacent sources, a method × source matrix, and a method taxonomy written as candidate ADR 0002 methods · requested for: [an#223](https://github.com/thorwhalen/an/issues/223), phase P11 of `misc/docs/plan_core_and_cutan_2026-10.md` · per-source analyses: [`masters/`](masters/)*

## Summary and recommendation

The aim, from `design_principles.md`, is to find the **methods** that produce the looks, so they can be mixed into new sub-genres, rather than to imitate a studio [1]. This report studies 38 sources chosen for complementary methods. Six of them are the styles already measured in `cutout_styles_research.md` [2], and 32 are new. They are grouped in six families: cut-out film, silhouette and shadow puppetry; collage; limited animation; TV digital cut-out and live puppets; explainers and graphic motion; and multiplane, stop-motion and contrast cases. The set includes nine non-Western or Eastern European traditions: Ōfuji (Japan), Shanghai paper-cut (China), wayang kulit (Indonesia) with Karagöz (Turkey), Mushi Pro (Japan), Zagreb, Norstein, Borowczyk & Lenica, Trnka, and Laloux in Prague.

From them I extracted **82 methods in 13 aspects**. Of these, **37 are built** in `an` today, **17 are partial** and **28 are missing**. Each method is written as a candidate ADR 0002 method: an aspect, what it requires of an asset in the dotted capability grammar, a requirement-free fallback, and the `an` mechanism that exists or is missing (§3) [3].

Three findings matter most for the plan.

1. **Many masters use the end of a default chain as their whole style.** The requirement-free links that ADR 0002 adds as fallbacks are the chosen method of whole traditions, not degenerate cases.
   - Speech with no mouth is used by 8 sources (Reiniger, Ocelot, Ōfuji, Norstein, Trnka, Smallfilms, Zagreb, Laloux).
   - Expression by posture only is used by 6.
   - The glide walk is used by 7.

   So these links should be built as real, art-directable methods. The speech pulse and the glide are already in ADR 0002's first slice and an#224. Building them well buys whole styles, not only safety nets.
2. **The most widely shared gaps sit outside the picture engine.**
   - Narration is used by 9 sources and `Shot.narration` still raises.
   - The articulated hierarchy is used by 9 (an#163 gap 11).
   - Public-domain photo-part ingestion is used by 8.
   - Metamorphosis by replacement is used by 8.
   - Material texture fills are used by 7.
   - Timing counted to music, a stored reuse bank and pop-and-hold as a named method are used by 6 each.

   The full ranked list is in §3.4.
3. **Styles differ more by choice than by capability.** Turn, speech, locomotion, timing and surface are aspects where most rigs afford several methods, and the masters pick different ones on purpose. Peppa Pig and wayang use a single profile even though a view set is possible. Reiniger mimes even when a mouth exists. South Park hops even when its characters have legs. These are exactly ADR 0002 **policies** (decision 4). §4 shows how the `an-style` specs become policies, with three worked examples. One of them is a new sub-genre mixed from four masters.

**Recommendation.** P7 (the capability registry) should register the methods of §3 aspect by aspect, starting with the default chains of §3.3. Each phase whose work a method gap blocks should take its gap from §3.4, in this order: narration (an#9), the speech pulse and posture-only expression (P7's first slice), glide and walk-in-place (an#224 / P10), the reuse bank as ADR 0005 motion clips, then hierarchy. The `an-style` specs gain a `policy:` section once the registry exists (§4). The study order is in §5, and the public-domain study clips usable under plan decision 9 are listed there too.

## What already exists (in-house)

- `misc/docs/cutout_styles_research.md` [2]: six styles with measured cadence, cut and palette statistics; ranked gaps (now an#163). Reused here for S01, S06, S10, S21, S28 and S29, and not re-derived.
- `misc/docs/cutout_framework_review_2026-10.md` §1 [4]: the five-dimension state space (transform, drawing, order, shape, surface) and the animation operators. The aspects below refine those dimensions into the vocabulary of ADR 0002.
- `misc/docs/framework_review_2026-10.md` §1 [5]: the glossary of domain terms. This report uses its terms (replacement animation, turnaround, on twos, multiplane, master controller).
- ADR 0002 [3]: the vocabulary (aspect, method, capability), matcher, policy, and default chains. §3 is written to feed it.
- `.claude/skills/an-style/` [6]: the six style specs (`live` / `targets` / `guidance`). §4 maps them onto policies.
- `misc/docs/report 3 - Facial Animation, Lip Sync & Expression Systems for 2D Cutout Animation.md` [7] covers mouth charts and expression rigs in depth, and is not repeated here.
- `ir discover reports` found nothing else on these sources.

## 1. The sources

Chosen to cover the method space, not the look space. Each family adds methods the others lack. Each analysis gives the source's methods, measurable cues, written analyses and video links (links only; nothing downloaded or committed), plus a copyright hint.

| # | Code | Source | Family | What it contributes that the others do not |
|---|---|---|---|---|
| S01 | `RE` | Lotte Reiniger | [A](masters/a_cutout_film_and_silhouette.md) | deep articulated puppet; timing counted to the score |
| S02 | `OC` | Michel Ocelot | A | silhouette rules that survive paper, CG and stereo; limbs kept off the outline |
| S03 | `OF` | Noburō Ōfuji | A | coloured cellophane: subtractive colour overlap; patterned paper as surface |
| S04 | `WG` | Wan Guchan / Shanghai paper-cut | A | rubber-pellet joints, pre-planned motion paths, torn soft edges |
| S05 | `WK` | Wayang kulit, Karagöz | A | rod-driven arms (IK by hand); perforation as shadow texture |
| S06 | `NO` | Yuri Norstein | A | depth by translucency; multiplane push; soft edges |
| S07 | `FP` | Laloux & Topor, *Fantastic Planet* | A | cut-out in phases (whole-pose replacement) with an engraved surface |
| S08 | `SF` | Smallfilms | A | the cheapest complete method set: glide, narrator, pans over paintings |
| S09 | `PW` | Captain Pugwash | A | real-time lever puppetry of cut-outs |
| S10 | `GI` | Terry Gilliam | [B](masters/b_collage.md) | photographic parts; metamorphosis as the gag |
| S11 | `HS` | Harry Smith | B | engraving vocabulary on black; projection-time frame masks |
| S12 | `VB` | Stan VanDerBeek | B | cut-out and newsreel in one frame |
| S13 | `BL` | Borowczyk & Lenica | B | primitive mechanical motion; the letter as protagonist |
| S14 | `FM` | Frank Film | B | replacement density; two voices in counterpoint |
| S15 | `UP` | UPA | [C](masters/c_limited_animation.md) | pops and holds; colour as mood; camera over paintings |
| S16 | `HB` | Hanna-Barbera TV | C | layered TV rig with a costume seam; walk in place over a repeating pan |
| S17 | `ZG` | Zagreb school | C | even-spaced glides between holds; music as ballet |
| S18 | `MP` | Mushi Pro, Astro Boy; Dezaki | C | the reuse bank; on threes; the painted freeze frame |
| S19 | `CC` | Clutch Cargo / Syncro-Vox | C | a filmed mouth on a still face; real-material FX |
| S20 | `SQ` | Squigglevision | C | line boil |
| S21 | `SP` | South Park | [D](masters/d_tv_digital_cutout.md) | the baseline `an` already hits |
| S22 | `BC` | Blue's Clues | D | photographed craft materials; a live host keyed in; viewer pauses |
| S23 | `PP` | Peppa Pig | D | the single-view design system |
| S24 | `CL` | Charlie and Lola | D | real textures pasted into a digital rig |
| S25 | `AR` | Archer | D | hierarchy plus heavy reuse; painted-over 3D sets |
| S26 | `HI` | Hilda / Mercury Filmworks | D | deep Harmony rigs made to read as drawn: slow timing, lighting in the rig |
| S27 | `CA` | Live Character Animator | D | the puppet as an instrument: audio visemes, live triggers |
| S28 | `OS` | OverSimplified | [E](masters/e_explainers_and_graphics.md) | burst and hold; narrated maps |
| S29 | `KG` | Kurzgesagt | E | never still; the widest method set (20) |
| S30 | `RS` | RSA Animate | E | draw-on with a visible hand; one continuous canvas |
| S31 | `SB` | Saul Bass titles | E | type and logo as characters; cuts on musical counts |
| S32 | `CG` | CGP Grey | E | the explainer floor: icons cut to a voice |
| S33 | `DM` | Disney multiplane; Fleischer setback | [F](masters/f_multiplane_stopmotion_contrast.md) | depth along the lens axis; rack focus; flat figures over a 3D set |
| S34 | `LK` | Laika replacement faces | F | combinatorial split-face replacement |
| S35 | `MM` | *Mary and Max* | F | palette switched per world |
| S36 | `CS` | Cartoon Saloon | F | line style per world; frames within the frame |
| S37 | `TR` | Trnka, *The Hand* | F | a fixed face: expression by angle, light and pose |
| S38 | `VR` | Paper stop motion (Verona Riots) | F | real paper on twos with real shadows |

**Evidence and its limits.** Every per-source claim cites a reference. Video links marked *(search)* were seen in search results and not opened. **No timestamp is given unless verified**. For the six measured styles, the timestamp is the start of the measured window. The other research workers could verify none. Production numbers often come from secondary sources and some conflict; the analyses say so where they do. The ○ marks in the matrix are lighter-weight: a method the source uses but that does not define it, taken from the cited sources or the earlier measurement.

## 2. Method × source matrix

● = a signature method of the source (named in its analysis); ○ = also used. `n` = number of sources using the method. Source codes are in §1. Generated together with §3 from one data table, kept with the cutan lead's working notes (not in the repository), so the two agree.

| Method | RE | OC | OF | WG | WK | NO | FP | SF | PW | GI | HS | VB | BL | FM | UP | HB | ZG | MP | CC | SQ | SP | BC | PP | CL | AR | HI | CA | OS | KG | RS | SB | CG | DM | LK | MM | CS | TR | VR | n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **rig** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `rig.single_piece` |  |  |  |  |  |  |  |  |  | ○ | ● | ○ | ○ | ● | ○ |  | ○ |  | ● |  |  |  |  |  |  |  |  |  |  | ○ | ● | ○ |  |  |  |  |  | ● | 12 |
| `rig.flat_pieces` |  |  | ○ |  |  | ○ |  | ● | ● | ● |  |  |  |  |  | ○ |  | ○ |  |  | ● | ● | ● | ● | ○ |  |  | ● | ○ |  |  | ○ |  |  |  |  |  |  | 15 |
| `rig.hierarchy` | ● | ○ |  | ● | ● |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ● | ○ |  | ○ |  |  |  |  |  |  |  |  |  | 9 |
| `rig.rod_driven` |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `rig.deformation` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ○ |  |  |  |  |  |  |  |  |  |  |  | 2 |
| `rig.draw_order_keys` | ○ | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  | 3 |
| `rig.mask` |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  | 2 |
| `rig.photo_parts` |  |  |  |  |  |  |  |  |  | ● | ● | ● | ● | ● |  |  |  |  | ○ |  |  | ● |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 8 |
| **replacement** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `swap.part` |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  | ● |  | ○ |  | ○ | ● | ○ | ○ | ○ | ○ | ● | ● | ○ | ○ |  |  |  |  | ● | ● |  |  |  | 15 |
| `swap.split_face` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  | ○ |  |  |  | ○ | ○ | ○ |  |  |  |  |  |  | ● |  |  |  |  | 6 |
| `swap.pose` |  |  |  |  |  |  | ● |  |  |  |  |  |  |  | ● | ○ | ○ | ○ |  |  |  |  |  |  | ● |  | ○ |  |  |  |  |  |  |  |  |  |  |  | 7 |
| `swap.view` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  | ○ | ● | ● | ○ |  |  |  |  |  |  |  |  |  |  | 5 |
| `swap.view_blend` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `swap.fixed_profile` | ● | ● | ○ | ○ | ● |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 7 |
| `swap.metamorphosis` |  |  |  |  |  |  |  |  |  | ● | ● | ○ | ○ | ● |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  | ○ | ○ |  |  |  |  |  |  |  | 8 |
| `swap.bank` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ● | ○ | ○ |  |  |  |  | ● |  | ● |  |  |  |  |  |  |  |  |  |  |  | 6 |
| **speech** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `speech.mouth_chart` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  | ● |  | ○ | ○ | ○ | ● | ● | ○ |  |  |  |  |  | ○ | ● |  |  |  | 10 |
| `speech.mouth_flap` |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
| `speech.photo_mouth` |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
| `speech.pose_only` | ● | ● | ● |  |  | ● | ○ | ● |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | 8 |
| `speech.narrator` |  | ○ |  |  |  |  |  | ● |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  | ● |  |  |  |  | ● | ● | ● |  | ● |  |  | ● |  |  |  | 9 |
| **face** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `face.expression_axes` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  | ● |  | ○ |  | ○ | ○ | ● | ● |  |  |  |  |  | ● | ○ |  |  |  | 9 |
| `face.posture_only` | ● | ● |  |  | ● | ● | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | 6 |
| `face.performance` |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  | 2 |
| **locomotion** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `loco.legged_cycle` | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ○ |  |  |  |  |  |  | ○ | ○ |  |  |  |  |  |  |  |  |  |  |  |  | 5 |
| `loco.bob` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ○ | ● | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 4 |
| `loco.glide` |  |  |  |  | ● |  |  | ● | ● | ● |  |  |  |  |  |  | ● | ● | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 7 |
| `loco.walk_in_place` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ● | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 3 |
| **timing** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `timing.on_ones` | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  | ● |  |  |  |  |  | 4 |
| `timing.stepped` |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  | ● |  | ● |  |  | ● |  |  |  |  | ● |  |  |  |  |  |  |  |  | ● |  |  | ● | 7 |
| `timing.per_part_cadence` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ● |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 3 |
| `timing.pop_and_hold` |  |  |  |  |  |  |  |  |  | ● |  |  |  |  | ● |  | ● |  |  |  |  |  |  |  | ○ |  |  | ● |  |  | ● |  |  |  |  |  |  |  | 6 |
| `timing.even_glide` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `timing.sectioning` |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ● |  | ● | ● | ○ |  |  |  |  | ● |  | ○ |  |  |  |  |  |  |  |  |  |  |  | 7 |
| `timing.music_count` | ● |  | ○ |  |  |  |  |  |  |  |  |  |  |  | ○ |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ○ |  |  |  |  |  | 6 |
| `timing.live_performance` |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  | ○ |  |  |  |  |  |  |  |  | 3 |
| `timing.ambient` |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  | 3 |
| `timing.freeze_frame` |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
| `timing.viewer_pause` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| **staging** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `stage.profile_strip` | ● | ● |  | ● | ● |  | ○ | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ○ |  |  |  | ● |  |  |  |  |  |  |  |  |  |  | 9 |
| `stage.multiplane` | ● | ● | ● | ● |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  | ● |  |  | ● |  |  | 8 |
| `stage.translucent_layers` |  |  | ● |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  | 3 |
| `stage.flat_graphic` |  | ○ |  |  |  |  | ● |  |  |  |  |  | ○ |  | ● |  | ● |  |  |  |  |  | ○ | ● |  |  |  |  | ○ |  | ● | ○ |  |  |  | ● |  |  | 11 |
| `stage.world_coding` |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ● |  |  | 3 |
| `stage.composite_3d` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  | ○ | ● |  |  |  |  |  |  |  | ● |  |  |  |  |  | 4 |
| `stage.live_action` |  |  |  |  |  |  |  |  |  |  |  | ● | ○ |  |  |  |  |  | ● |  |  | ● |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  | 5 |
| `stage.frame_in_frame` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  | ● |  |  | 2 |
| `stage.crowd` |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  | ● | ○ |  |  |  |  |  |  |  |  |  | 4 |
| **camera** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `camera.locked` | ● |  |  |  |  |  |  |  | ● | ● | ● |  |  | ○ |  | ○ | ○ |  |  |  | ● |  | ○ |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  | 10 |
| `camera.move_over_still` |  |  |  |  |  |  |  | ● |  |  |  |  | ● |  | ● |  |  | ● | ● |  |  |  |  |  |  |  |  | ● |  | ● |  | ○ |  |  |  |  |  |  | 8 |
| `camera.multiplane_truck` |  |  |  | ○ |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  | ● |  |  | ○ |  |  | 5 |
| `camera.rack_focus` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  | 1 |
| `camera.follow` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  | 1 |
| **surface** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `surface.outline` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  | ● |  | ● |  | ○ |  |  |  |  |  |  |  |  |  |  | ● |  |  | 5 |
| `surface.paper_shadow` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | 2 |
| `surface.silhouette` | ● | ● | ● |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  | 5 |
| `surface.translucent_colour` |  |  | ● |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
| `surface.material_texture` |  |  | ● |  |  | ○ |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ● |  |  |  |  |  |  |  |  |  |  |  | ○ |  | ● | 7 |
| `surface.perforation` | ○ | ○ |  | ● | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 4 |
| `surface.engraving` |  |  |  |  |  |  | ● |  |  | ● | ● |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  | 5 |
| `surface.grain` |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 2 |
| `surface.glow` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  | 1 |
| `surface.soft_edge` |  |  |  | ● |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  | 3 |
| `surface.line_boil` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `surface.light_rig` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  | ● |  |  |  | ● |  | 3 |
| **FX** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `fx.draw_on` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ● | ● |  |  |  |  |  |  |  | 3 |
| `fx.particles` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  | ● |  |  |  |  |  | 2 |
| `fx.real_material` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `fx.smear` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `fx.flash` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  | 2 |
| `fx.frame_mask` |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  | 2 |
| **text** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `text.card` | ● |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ○ |  | ● | ○ |  |  |  |  |  |  | 6 |
| `text.kinetic` |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ | ○ | ○ | ● |  |  |  |  |  |  |  | 5 |
| `text.map_diagram` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● | ● | ● |  | ● |  |  |  |  |  |  | 4 |
| **transitions** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `transition.dissolve` | ● |  |  |  |  | ● |  |  |  |  |  |  |  |  | ● |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 4 |
| `transition.match_morph` |  |  |  |  |  |  |  |  |  | ● | ○ |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  | 4 |
| `transition.continuous` |  |  |  |  |  |  |  |  |  |  |  |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ○ | ● |  |  |  |  |  |  |  |  | 3 |
| **sound** | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
| `sound.score_led` | ● |  | ● |  |  | ● |  |  |  |  |  |  |  |  | ○ |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  | ● |  |  |  | ● |  | 8 |
| `sound.sfx_carry` |  |  |  |  |  |  |  | ○ |  | ○ | ● |  |  |  | ● |  | ○ | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 6 |
| `sound.voice_first` |  | ○ |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  | ● |  |  |  | ● |  |  | ○ |  |  | ● |  |  |  |  |  |  |  |  | 6 |
| `sound.dual_voice` |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |
| `sound.voice_fx` |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | ● |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |

**Reading it.**

- The **rig** rows split the set in two. Flat pieces (15 sources) and articulated hierarchies (9) are almost disjoint. Collage (single pieces and photo parts) is a third cluster.
- The **speech** rows show three equally large camps:
  - mouth chart: 10 sources
  - no lip sync, pose only: 8
  - narrator: 9
- **Timing** is the aspect with the most distinct methods (11), which is why one `step_hz` cannot express most styles.
- **Surface** methods are mostly built, but the ones collage and paper need (material texture, soft edges, translucent colour) are not.

## 3. Method taxonomy, as candidate ADR 0002 methods

### 3.1 Capabilities the methods require

ADR 0002 names capabilities in one dotted grammar (`limbs.legs`, `face.mouth`, `swap.view`, `rig.hierarchy`, `face.eyelids`) and derives them from the asset [3]. Plan decision 4 extends one registry over assets, engines and the environment [8]. The methods below need these capabilities. The ones marked *new* are not in ADR 0002's examples; a capability no asset or engine affords today is marked *never afforded*.

| Capability | Of | Afforded when (derived, never declared) | State |
|---|---|---|---|
| `rig.slots` (count), `rig.pivots` | asset | the descriptor's slots; attachments with anchors | afforded |
| `rig.hierarchy` | asset | bones whose transforms are inherited | never afforded (rigs are flat) |
| `rig.deform` | asset | a mesh or envelope on a part | *new*; never afforded |
| `limbs.legs`, `limbs.arms` | asset | a left/right slot pair with pivots at hip or shoulder (today `_limb_pair`); `limbs.arms` with a hand end for `rig.rod_driven` | afforded |
| `face.mouth` (chart, keys) | asset | a mouth slot with a viseme set; the chart size is a parameter | afforded (9 keys) |
| `face.eyes`, `face.brows`, `face.eyelids` | asset | face slots; an eyelid set with closed-eye art | afforded |
| `swap.<set>` (keys), `swap.view` (keys), `swap.pose` (keys) | asset | a declared swap set; `view`; an entity-level set with `swap_poses` | afforded |
| `art.raster`, `art.path`, `art.vector_roles` | asset | raster attachments; path props; colour-role tags | afforded |
| `art.boil` (n), `art.pattern_fill` | asset | n line variants of a drawing; a texture bound to a fill | *new*; never afforded |
| `plane.depth`, `plane.tileable` | environment | ≥ 2 planes with `depth`; a plane that repeats along an axis | `plane.depth` afforded; `plane.tileable` *new* |
| `audio.bed`, `audio.tempo`, `audio.narration` | pipeline | a bed in `Meta.sounds`; a bed with a known tempo; narration synthesis | bed afforded; tempo and narration *new* |
| `engine.mask`, `engine.blend`, `engine.blur`, `engine.light`, `engine.video_plate` | engine | the stage runtime's feature set | *new*; never afforded by `an.stage` |
| `library.clips` | library | stored clips (ADR 0005 motion-clip kind) whose `requires` the rig meets | *new*; P5 |
| `input.performance` | input | a recorded performance track (webcam, keypad, levers) | *new*; never afforded |

Two consequences for P7.

- **Engine capabilities belong in the same registry.** A method like `camera.rack_focus` is inapplicable because the engine lacks blur, not because of the asset. With engine capabilities in the registry, `why_not` can say so, and a future engine that has blur can afford it without a code change. This is ADR 0002 decision 7's "core registry, genre vocabulary" applied to engines.
- **Most timing, staging and surface methods require nothing.** For those aspects the default chain is short, and the choice is a matter of **policy** (§4).

### 3.2 The methods

Each row is one candidate method. "Requires" is what the matcher checks. "Fallback" is the next link of the default chain, and every chain ends in "(last link)", a method that requires nothing (ADR 0002 decision 5). "`an` today" is the mechanism that exists, or the gap. `n` is how many of the 38 sources use the method.

| Method | Aspect | What it is | Requires (capabilities) | Fallback | `an` today | n |
|---|---|---|---|---|---|---|
| `rig.single_piece` | rig | single-piece cut-out, no joints | nothing | (last link) | **built**: any prop or plane; tweens on the entity | 12 |
| `rig.flat_pieces` | rig | rigid pieces on pivots, transforms not inherited | `rig.slots` (≥ 2), `rig.pivots` | `rig.single_piece` | **built**: flat `Bone`/`Slot` tree | 15 |
| `rig.hierarchy` | rig | articulated hierarchy (forearm follows arm) | `rig.hierarchy` | `rig.flat_pieces`, recorded | **missing**: rigs are flat (an#163 gap 11) | 9 |
| `rig.rod_driven` | rig | end-effector control: the hand is placed, the chain follows (IK) | `rig.hierarchy`, `limbs.arms` | keyed joint rotations | **missing**: no IK or constraints | 1 |
| `rig.deformation` | rig | mesh / envelope deformation, bends | `rig.deform` | rigid piece; squash by scale | **missing**: no deformation | 2 |
| `rig.draw_order_keys` | rig | keyed draw order | `rig.slots` (≥ 2) | static order | **missing**: draw order is static | 3 |
| `rig.mask` | rig | masks: a part clipped by another, soft matte | `engine.mask` | hard-edged parts | **missing**: no clipping | 2 |
| `rig.photo_parts` | rig | parts cut from photographs, engravings, found print | `art.raster` | a vector stand-in, recorded | **partial**: raster parts shipped (an#211); no public-domain ingestion or segmentation | 8 |
| `swap.part` | replacement | drawing substitution on one part (hands, eyes) | `swap.<set>` on the slot | hold the rest drawing | **built**: swap channels (an#87) | 15 |
| `swap.split_face` | replacement | independent upper / lower face channels (combinatorial) | `face.eyes` or `face.brows`, and `face.mouth`, as separate slots | mouth only | **built**: separate face slots + the face solver | 6 |
| `swap.pose` | replacement | whole-pose replacement (phase drawings, pose library) | `swap.pose` | keyed piece transforms | **built**: whole-character swap + `swap_poses` (an#197) | 7 |
| `swap.view` | replacement | turnaround by view swap | `swap.view` | `swap.fixed_profile` (mirror flip) | **built**: `view` set + `turn` preset | 5 |
| `swap.view_blend` | replacement | multi-angle turn with in-betweens, pose-grid blending | `swap.view` (≥ 3 keys), `rig.deform` | `swap.view` | **missing**: one swap at the edge-on midpoint only | 1 |
| `swap.fixed_profile` | replacement | single-view design; a turn is a mirror flip | a side drawing (`swap.view` key `side` or `rest_view: side`) | (last link) | **built**: `rest_view`, negative `scale_x` | 7 |
| `swap.metamorphosis` | replacement | metamorphosis by a replacement series | `swap.<set>` (ordered keys) | `transition.dissolve` | **partial**: stepped swap sets; no continuous morph | 8 |
| `swap.bank` | replacement | reuse bank: stored poses, cycles and cuts reused across episodes | `library.clips` whose requirements the rig meets | author anew | **missing**: presets are code; no stored action library (ADR 0005 motion-clip kind) | 6 |
| `speech.mouth_chart` | speech | lip sync on a mouth chart of n shapes | `face.mouth` (chart) | `speech.mouth_flap` | **built**: 9-shape chart (Rhubarb A–H, X), `viseme@<form>` | 10 |
| `speech.mouth_flap` | speech | flap: 2–3 shapes (open, half, closed) | `face.mouth` (≥ 2 keys) | `speech.pose_only` | **missing**: the chart size is fixed at 9 | 2 |
| `speech.photo_mouth` | speech | photographed or filmed mouth composited into a still face | `face.mouth` with raster keys, or `engine.video_plate` | `speech.mouth_chart` | **partial**: raster mouth keys work; no video | 2 |
| `speech.pose_only` | speech | no lip sync: speech carried by posture, a body pulse, or a narrator | nothing | (last link) | **missing**: a baked face speaks with a frozen mouth (ADR 0002 first slice adds the pulse) | 8 |
| `speech.narrator` | speech | a narrator carries the words; figures mime | `audio.narration` | an off-screen dialogue line | **missing**: `Shot.narration` raises in the audio pipeline | 9 |
| `face.expression_axes` | face | expression by brows, lids and mouth form | `face.brows` or `face.eyelids` | `face.posture_only` | **built**: ten axes, ten presets, the face solver (an#98) | 9 |
| `face.posture_only` | face | fixed face: expression by head angle, light and pose | nothing | (last link) | **missing**: ADR 0002's posture-only link is not built | 6 |
| `face.performance` | face | performance capture: webcam and audio drive the face, keys fire replacements | `input.performance` | keyed authoring | **missing**: nothing records a live performance | 2 |
| `loco.legged_cycle` | locomotion | legged walk cycle | `limbs.legs` (hip pivots), a side or ¾ view | `loco.bob` | **built**: `walk`, gait `legs` (an#214) | 5 |
| `loco.bob` | locomotion | bob / hop walk, legs barely move | nothing | `loco.glide` | **built**: `hop`, `waddle` | 4 |
| `loco.glide` | locomotion | glide: the figure is carried, no leg action (pull-cel) | nothing | (last link) | **partial**: `slide_in`/`slide_out`; no glide gait (an#224) | 7 |
| `loco.walk_in_place` | locomotion | walk in place over a repeating background pan | `limbs.legs`, `plane.tileable` | `loco.glide` | **partial**: walk and pans exist; no repeating plane | 3 |
| `timing.on_ones` | timing | continuous motion on ones | nothing | (last link) | **built**: the default | 4 |
| `timing.stepped` | timing | global stepping on twos / threes | nothing | `timing.on_ones` | **built**: `step_hz` | 7 |
| `timing.per_part_cadence` | timing | per-part cadence (mouth on ones, body on twos) | nothing | `timing.stepped` | **partial**: swaps are exempt from stepping; no per-node grid | 3 |
| `timing.pop_and_hold` | timing | pop / burst and hold | nothing | (last link) | **partial**: authorable; no named method; the style lint measures it | 6 |
| `timing.even_glide` | timing | even spacing, no slow-in / slow-out | nothing | (last link) | **built**: `linear` easing, `default_easing` | 1 |
| `timing.sectioning` | timing | sectioning: only the part that matters moves on a held body | `rig.slots` (≥ 2) | whole-body move | **built**: by authoring | 7 |
| `timing.music_count` | timing | moves and cuts counted to the music | `audio.tempo` | free timing | **missing**: a bed exists; nothing reads its tempo | 6 |
| `timing.live_performance` | timing | real-time performance recorded as the timing | `input.performance` | keyed timing | **missing**: nothing records a performance | 3 |
| `timing.ambient` | timing | never still: ambient secondary motion | nothing | (last link) | **partial**: sine idles; no ambient library | 3 |
| `timing.freeze_frame` | timing | freeze into a painted still (postcard memory) | a painted plate of the frame | a hard hold | **partial**: hold + plate + dissolve, by hand | 2 |
| `timing.viewer_pause` | timing | pauses timed for the viewer | nothing | (last link) | **built**: `Dialogue.pause` (an#187) | 1 |
| `stage.profile_strip` | staging | side-on stage strip, action parallel to the picture plane | nothing | (last link) | **built**: stage placement | 9 |
| `stage.multiplane` | staging | multiplane parallax | `plane.depth` (≥ 2 planes) | one plate | **built**: planes with `depth` (an#110) | 8 |
| `stage.translucent_layers` | staging | depth by layered translucency (fog, cellophane) | `plane.depth`, `engine.blend` | alpha planes | **partial**: alpha only; no blend modes | 3 |
| `stage.flat_graphic` | staging | flat graphic set: no perspective, colour field as mood | nothing | (last link) | **built**: fill planes; art direction | 11 |
| `stage.world_coding` | staging | palette or line style per location | `art.vector_roles` | one look | **partial**: one StylePack per scene; no per-shot pack, no line-style swap | 3 |
| `stage.composite_3d` | staging | flat characters over a 3D or photographic set (setback) | `art.raster` plates | a flat painted plate | **partial**: raster plates; no 3D set | 4 |
| `stage.live_action` | staging | live action in the frame (host, newsreel, lips) | `engine.video_plate` | a still photo plate | **missing**: no video plates | 5 |
| `stage.frame_in_frame` | staging | frames inside the frame (split screen, panels) | `engine.mask` | sequential shots | **missing**: no sub-frames | 2 |
| `stage.crowd` | staging | crowd instancing with variation | nothing | hand-placed copies | **missing**: an#163 gap 6 | 4 |
| `camera.locked` | camera | locked-off camera | nothing | (last link) | **built**: `hold` | 10 |
| `camera.move_over_still` | camera | camera moves over still art as the animation | nothing | `camera.locked` | **built**: pans, push-ins, `Camera.keys` | 8 |
| `camera.multiplane_truck` | camera | depth-aware push: near planes grow, far ones do not | `plane.depth` | uniform zoom + pan | **missing**: the dolly was deferred (an#110) | 5 |
| `camera.rack_focus` | camera | rack focus between planes | `plane.depth`, `engine.blur` | no focus change | **missing**: no blur, by policy | 1 |
| `camera.follow` | camera | the camera follows a subject (the drawing hand) | nothing | fixed framing | **missing**: no follow-entity | 1 |
| `surface.outline` | surface | outline | nothing | (last link) | **built**: `surface.outline` | 5 |
| `surface.paper_shadow` | surface | paper-gap drop shadow | nothing | (last link) | **built**: `surface.shadow` | 2 |
| `surface.silhouette` | surface | silhouette (black fill) | nothing | (last link) | **built**: black `tint` | 5 |
| `surface.translucent_colour` | surface | coloured translucency (cellophane, oiled hide) | `engine.blend` | flat tint at partial alpha | **partial**: alpha + tint; no multiply between parts | 2 |
| `surface.material_texture` | surface | material as the surface (patterned paper, fabric, watercolour) | `art.raster` or `art.pattern_fill` | flat fill | **partial**: raster art; no pattern fill on vector parts | 7 |
| `surface.perforation` | surface | perforation and carving that read as lace in silhouette | art with alpha holes | (last link) | **built**: in the art | 4 |
| `surface.engraving` | surface | engraved, hatched line | art | (last link) | **built**: in the art | 5 |
| `surface.grain` | surface | static paper grain | nothing | (last link) | **built**: `grain` | 2 |
| `surface.glow` | surface | glow | nothing | (last link) | **built**: `surface.glow` | 1 |
| `surface.soft_edge` | surface | soft or torn edges, painted look | `engine.mask` (feather) | hard edge | **missing**: no feathering | 3 |
| `surface.line_boil` | surface | line boil: cycle n traced variants of a held drawing | `art.boil` (n variants) | a static line | **missing**: a looping swap set could carry it; no variant generator | 1 |
| `surface.light_rig` | surface | lighting as a rig or plane layer | `engine.light` or a light plane | none | **missing**: no lighting model | 3 |
| `fx.draw_on` | FX | draw-on reveal of strokes | `art.path` | a fade in | **built**: path `trim` (an#160) | 3 |
| `fx.particles` | FX | particles (rain, smoke, sparkle) | nothing | none, recorded | **missing**: no FX asset kind | 2 |
| `fx.real_material` | FX | real-material FX superimposed (smoke, flame, models) | `engine.video_plate` | drawn FX | **missing**: no video plates | 1 |
| `fx.smear` | FX | smears and speed lines | nothing | none | **missing**: no FX asset kind | 1 |
| `fx.flash` | FX | flash / impact frame | nothing | (last link) | **partial**: fade through white; a fill-plane alpha tween | 2 |
| `fx.frame_mask` | FX | shaped frame mask or colour filter over the frame | `engine.mask` | none | **missing**: no frame mask | 2 |
| `text.card` | text | title, date and intertitle cards | a font | (last link) | **built**: text props over fill planes (an#155) | 6 |
| `text.kinetic` | text | kinetic typography: type as an actor | a font | `text.card` | **built**: text units by word or glyph + tweens | 5 |
| `text.map_diagram` | text | maps, arrows, diagrams | `art.path` | `text.card` | **partial**: paths shipped; region fills open (an#161) | 4 |
| `transition.dissolve` | transitions | dissolve / fade | nothing | a cut | **built**: `Shot.transition` (an#163) | 4 |
| `transition.match_morph` | transitions | match or morph across a cut (visual rhyme) | nothing | `transition.dissolve` | **missing**: transitions are cut, fade and dissolve only | 4 |
| `transition.continuous` | transitions | one continuous canvas, no cuts | nothing | (last link) | **built**: a long shot with camera keys | 3 |
| `sound.score_led` | sound | score-led, no dialogue | `audio.bed` | silence | **built**: `Meta.sounds` bed | 8 |
| `sound.sfx_carry` | sound | SFX carry motion and voice | nothing | (last link) | **built**: `Shot.sounds` cues | 6 |
| `sound.voice_first` | sound | voices recorded first, picture timed to them | nothing | (last link) | **built**: the audio-first pipeline | 6 |
| `sound.dual_voice` | sound | two voice tracks in counterpoint | nothing | one voice | **partial**: overlapping lines via `Dialogue.at` | 1 |
| `sound.voice_fx` | sound | voice effects (pitch) | nothing | (last link) | **built**: voice `effects` (an#163) | 1 |

### 3.3 Default chains per aspect

Read off the fallbacks above. Every chain ends in a method that requires nothing, or in a recorded no-op where the aspect does not apply.

| Aspect | Chain (first applicable wins unless a policy reorders it) | Notes |
|---|---|---|
| rig | `rig.hierarchy` → `rig.flat_pieces` → `rig.single_piece` | a hierarchical method on a flat rig is approximated, recorded (cut-out review §5) |
| turn (replacement) | `swap.view_blend` → `swap.view` → `swap.fixed_profile` | the mirror flip is today's `turn` fallback |
| speech | `speech.mouth_chart` → `speech.mouth_flap` → `speech.pose_only` | the last link is ADR 0002's body or jaw pulse; `speech.photo_mouth` falls back to the chart |
| narration | `speech.narrator` → an off-screen dialogue line | until an#9 lands, the workaround is the fallback |
| expression | `face.performance` → `face.expression_axes` → `face.posture_only` | posture-only is Trnka's and Reiniger's whole method |
| locomotion | `loco.legged_cycle` → `loco.bob` → `loco.glide`; `loco.walk_in_place` → `loco.glide` | matches an#224's legged → hop → glide chain |
| timing | `timing.per_part_cadence` → `timing.stepped` → `timing.on_ones` | timing methods require nothing; the choice is policy |
| staging | `stage.multiplane` → one plate; `stage.live_action` → a still photo plate; `stage.frame_in_frame` → sequential shots | |
| camera | `camera.multiplane_truck` → uniform zoom + pan; `camera.rack_focus` → no focus change; `camera.follow` → fixed framing | engine-gated |
| surface | engine-gated methods fall back to their flat version (`surface.translucent_colour` → tint at alpha; `surface.soft_edge` → hard edge; `surface.material_texture` → flat fill) | |
| FX | `fx.particles` → recorded no-op; `fx.draw_on` → fade in; `transition.match_morph` → `transition.dissolve` → cut | |
| sound | `sound.score_led` (needs `audio.bed`) → silence, recorded | |

### 3.4 Gap list, ranked by how many sources use the method

Missing and partial methods only, sorted by the number of sources (signature uses in brackets). The rank is breadth across the masters, not engineering cost; the cost and the seam for the older gaps are in `cutout_styles_research.md` §7 [2] and an#163.

| # | Method | Aspect | State | Sources (●) | Which | What is missing |
|---|---|---|---|---|---|---|
| 1 | `speech.narrator` | speech | missing | 9 (7) | OC SF UP PP OS KG RS CG MM | `Shot.narration` raises in the audio pipeline |
| 2 | `rig.hierarchy` | rig | missing | 9 (5) | RE OC WG WK FP AR HI CA KG | rigs are flat (an#163 gap 11) |
| 3 | `rig.photo_parts` | rig | partial | 8 (6) | GI HS VB BL FM CC BC CL | raster parts shipped (an#211); no public-domain ingestion or segmentation |
| 4 | `speech.pose_only` | speech | missing | 8 (6) | RE OC OF NO FP SF ZG TR | a baked face speaks with a frozen mouth (ADR 0002 first slice adds the pulse) |
| 5 | `swap.metamorphosis` | replacement | partial | 8 (4) | GI HS VB BL FM ZG RS SB | stepped swap sets; no continuous morph |
| 6 | `loco.glide` | locomotion | partial | 7 (7) | WK SF PW GI ZG MP CC | `slide_in`/`slide_out`; no glide gait (an#224) |
| 7 | `surface.material_texture` | surface | partial | 7 (5) | OF NO SF BC CL CS VR | raster art; no pattern fill on vector parts |
| 8 | `face.posture_only` | face | missing | 6 (5) | RE OC WK NO FP TR | ADR 0002's posture-only link is not built |
| 9 | `timing.pop_and_hold` | timing | partial | 6 (5) | GI UP ZG AR OS SB | authorable; no named method; the style lint measures it |
| 10 | `swap.bank` | replacement | missing | 6 (4) | HB MP CC SQ AR CA | presets are code; no stored action library (ADR 0005 motion-clip kind) |
| 11 | `timing.music_count` | timing | missing | 6 (3) | RE OF UP ZG SB DM | a bed exists; nothing reads its tempo |
| 12 | `camera.multiplane_truck` | camera | missing | 5 (3) | WG NO KG DM CS | the dolly was deferred (an#110) |
| 13 | `stage.live_action` | staging | missing | 5 (3) | VB BL CC BC RS | no video plates |
| 14 | `text.map_diagram` | text | partial | 4 (4) | OS KG RS CG | paths shipped; region fills open (an#161) |
| 15 | `transition.match_morph` | transitions | missing | 4 (3) | GI HS FM KG | transitions are cut, fade and dissolve only |
| 16 | `stage.composite_3d` | staging | partial | 4 (2) | BC CL AR DM | raster plates; no 3D set |
| 17 | `stage.crowd` | staging | missing | 4 (1) | OC AR OS KG | an#163 gap 6 |
| 18 | `stage.world_coding` | staging | partial | 3 (3) | UP MM CS | one StylePack per scene; no per-shot pack, no line-style swap |
| 19 | `surface.light_rig` | surface | missing | 3 (3) | HI DM TR | no lighting model |
| 20 | `loco.walk_in_place` | locomotion | partial | 3 (2) | HB MP CC | walk and pans exist; no repeating plane |
| 21 | `stage.translucent_layers` | staging | partial | 3 (2) | OF NO DM | alpha only; no blend modes |
| 22 | `surface.soft_edge` | surface | missing | 3 (2) | WG NO CS | no feathering |
| 23 | `timing.ambient` | timing | partial | 3 (2) | NO SQ KG | sine idles; no ambient library |
| 24 | `timing.live_performance` | timing | missing | 3 (2) | PW CA RS | nothing records a performance |
| 25 | `timing.per_part_cadence` | timing | partial | 3 (2) | HB MP SP | swaps are exempt from stepping; no per-node grid |
| 26 | `rig.draw_order_keys` | rig | missing | 3 (1) | RE OC HI | draw order is static |
| 27 | `fx.particles` | FX | missing | 2 (2) | KG DM | no FX asset kind |
| 28 | `speech.mouth_flap` | speech | missing | 2 (2) | PW MP | the chart size is fixed at 9 |
| 29 | `face.performance` | face | missing | 2 (1) | PW CA | nothing records a live performance |
| 30 | `fx.flash` | FX | partial | 2 (1) | MP KG | fade through white; a fill-plane alpha tween |
| 31 | `fx.frame_mask` | FX | missing | 2 (1) | HS CS | no frame mask |
| 32 | `rig.deformation` | rig | missing | 2 (1) | HI CA | no deformation |
| 33 | `rig.mask` | rig | missing | 2 (1) | NO CS | no clipping |
| 34 | `speech.photo_mouth` | speech | partial | 2 (1) | VB CC | raster mouth keys work; no video |
| 35 | `stage.frame_in_frame` | staging | missing | 2 (1) | KG CS | no sub-frames |
| 36 | `surface.translucent_colour` | surface | partial | 2 (1) | OF WK | alpha + tint; no multiply between parts |
| 37 | `timing.freeze_frame` | timing | partial | 2 (1) | UP MP | hold + plate + dissolve, by hand |
| 38 | `camera.follow` | camera | missing | 1 (1) | RS | no follow-entity |
| 39 | `camera.rack_focus` | camera | missing | 1 (1) | DM | no blur, by policy |
| 40 | `fx.real_material` | FX | missing | 1 (1) | CC | no video plates |
| 41 | `fx.smear` | FX | missing | 1 (1) | MP | no FX asset kind |
| 42 | `rig.rod_driven` | rig | missing | 1 (1) | WK | no IK or constraints |
| 43 | `sound.dual_voice` | sound | partial | 1 (1) | FM | overlapping lines via `Dialogue.at` |
| 44 | `surface.line_boil` | surface | missing | 1 (1) | SQ | a looping swap set could carry it; no variant generator |
| 45 | `swap.view_blend` | replacement | missing | 1 (1) | HI | one swap at the edge-on midpoint only |

**How to read the top of the list.**

- **Requirement-free defaults** appear at ranks 4, 6 and 8:
  - `speech.pose_only`
  - `loco.glide`
  - `face.posture_only`

  ADR 0002 and an#224 already plan them. The masters show they need parameters (pulse strength, glide bob, which posture per emotion), not only an existence proof.
- **Narration** (rank 1) is the single largest gap, and it is a pipeline gap, not a rig gap. It also blocks the explainer genre.
- **Collage** gaps sit at ranks 3, 5 and 15:
  - photo parts
  - metamorphosis
  - match-morph transitions

  They need public-domain ingestion more than they need engine work. Faithful scans of public-domain engravings carry no new copyright in the US or the EU [9].
- **Hierarchy** (rank 2) and the **reuse bank** (rank 10) are the two structural gaps:
  - hierarchy is a rig option exposed as `rig.hierarchy`, never a new default;
  - the bank is ADR 0005's motion-clip kind with `requires`.

## 4. Style specs as policies

ADR 0002 decision 4 defines a **policy** as a per-aspect method order set by a style, with this precedence: the author's explicit request, then the shot, then the style, then the aspect's default chain [3]. A first-applicable chain cannot say "this show hops even when its characters have legs"; a policy can.

### 4.1 Which methods make a spec a policy

A method can sit in a policy when it is one of **several that apply to the same asset**. Where an asset affords only one method, the chain already decides. The masters choose among applicable methods in these aspects:

| Aspect | The choice the masters make | Methods the policy orders | Today in the `an-style` spec |
|---|---|---|---|
| locomotion | hop or glide although legs exist (South Park, Smallfilms, Zagreb) | `loco.legged_cycle`, `loco.bob`, `loco.glide`, `loco.walk_in_place` | `live.motion_presets` (advisory, nothing checks it) |
| turn | a single profile although a view set exists (Peppa Pig, wayang, Reiniger); a one-frame hard swap (South Park) | `swap.view` (with `duration`), `swap.fixed_profile`, `swap.view_blend` | `live.characters.view`; `guidance.views` |
| speech | mime although a mouth exists (Reiniger, Ocelot, Trnka); a 3-shape flap (Mushi Pro) | `speech.mouth_chart`, `speech.mouth_flap`, `speech.pose_only`, `speech.narrator` | `guidance.expression` |
| expression | posture only although brows exist (Trnka) | `face.expression_axes`, `face.posture_only` | `guidance` |
| timing | on twos, bursts on ones, even glides, sectioning | `timing.*` | `live.meta.step_hz`, `default_easing`, `tween_duration_s`; `targets` |
| surface | silhouette, outline, paper shadow, grain, glow | `surface.*` | `live.style_pack.surface`, `grain`, `characters.tint` |
| camera, transitions, sound | locked vs moving over stills; cut vs dissolve; score vs dialogue | `camera.*`, `transition.*`, `sound.*` | `live.camera.allowed`, `live.transitions`, `live.sound` |

Rig, `swap.part`, `swap.split_face` and `speech.mouth_chart` parameters (chart size) are **not** policy material. They describe the asset, and the matcher decides them.

### 4.2 Worked examples

The `policy:` block below is a proposal for the style document once P7's registry exists. Nothing reads it today, and it must not be added to a spec's `live` section (`tests/test_style_specs.py` checks every `live` key against the code). Method arguments are (a) typed values; method names are (b-name) entries in the versioned vocabulary.

**South Park.** The policy reorders locomotion past an applicable legged walk:

```yaml
policy:
  locomotion: [loco.bob, loco.glide]               # hop and waddle even when legs exist
  turn: [{method: swap.view, args: {duration_frames: 1}}, swap.fixed_profile]   # a hard head swap
  speech: [speech.mouth_chart]
  expression: [face.expression_axes]
  timing: [{method: timing.per_part_cadence, args: {body_step_hz: 12, swaps: ones}}]   # today: step_hz 12, swaps exempt
  surface: [surface.outline, surface.paper_shadow, surface.grain]
  camera: [camera.locked]
```

Against today's `an`:
- every method is built except `timing.per_part_cadence`, which is partial: `step_hz: 12` with swaps exempt already gives "body on twos, mouths on ones";
- for a character with legs, the locomotion line records a **policy choice**, not a substitution, so it is not a warning.

**Reiniger silhouette.** The policy overrides an applicable mouth chart:

```yaml
policy:
  rig: [rig.hierarchy, rig.flat_pieces]            # prefer the articulated puppet; flat is a recorded approximation
  turn: [swap.fixed_profile]                       # profile only, even when a view set exists
  speech: [speech.pose_only]                       # mime, even when a mouth chart exists
  expression: [face.posture_only]
  locomotion: [loco.legged_cycle, loco.glide]
  surface: [surface.silhouette]
  timing: [timing.music_count, timing.on_ones]     # counted to the score; free timing until a tempo is readable
  transitions: [transition.dissolve]
goals:                                             # (c), checked after rendering
  - silhouette_readable: {verifier: limbs_off_outline}   # Ocelot's rule; an.characters.silhouette is the nearest existing check
```

Against today's `an`:
- `rig.hierarchy`, `face.posture_only`, `speech.pose_only` and `timing.music_count` are missing;
- the render takes `rig.flat_pieces`, today's frozen face, and free timing, with **each substitution recorded**;
- once ADR 0002's speech pulse lands, `speech.pose_only` maps to it (pulse strength 0 means a pure mime);
- the spec's `guidance.expression` line ("pose and profile only") becomes two policy lines that a machine can apply.

**A new sub-genre, mixed from four masters: "planned explainer".** It combines Hanna-Barbera's layered rig and walk in place, Mushi Pro's threes and reuse bank, Peppa Pig's single view, and OverSimplified's narrator and maps. None of the four looks like this, and it is cheap:

```yaml
policy:
  turn: [swap.fixed_profile]                                          # Peppa Pig
  speech: [{method: speech.mouth_flap, args: {shapes: 3}}, speech.mouth_chart]   # Mushi Pro
  narration: [speech.narrator]                                        # OverSimplified
  locomotion: [loco.walk_in_place, loco.glide]                        # Hanna-Barbera, Mushi Pro pull-cels
  timing:
    - {method: timing.sectioning}                                     # Hanna-Barbera: only the part that matters moves
    - {method: timing.per_part_cadence, args: {body_step_hz: 8, swaps: twos}}   # Mushi Pro: on threes at 24 fps
  camera: [camera.move_over_still]                                    # UPA, OverSimplified
  reuse: [swap.bank]                                                  # Mushi Pro, Hanna-Barbera
  surface: [surface.outline]
targets: {identical_frame_share: [0.6, 0.8]}                          # an estimate; no master to measure it against
```

Against today's `an`, the substitutions are:

| Requested | What renders instead | Why |
|---|---|---|
| `speech.mouth_flap` | `speech.mouth_chart` (9 shapes) | the chart size is fixed |
| `speech.narrator` | an off-screen dialogue line | narration raises |
| `loco.walk_in_place` | `loco.glide` | no repeating plane |
| `swap.bank` | presets | no stored clips |

All four substitutions are recorded. The remaining lines are built.

This example shows the taxonomy doing its job: a style specified as method choices, rendered as a draft today, and improving line by line as the gaps of §3.4 close, without being rewritten.

## 5. Study order, and public-domain study clips

**Study order.** By what each group unlocks, in the order the plan's phases consume it:

1. **Requirement-free defaults** (Trnka, Reiniger, Ocelot, Smallfilms): `speech.pose_only`, `face.posture_only`. Feeds P7's first slice.
2. **Locomotion** (Smallfilms, Pugwash, Zagreb, wayang for glide; Hanna-Barbera and Mushi Pro for walk in place; Peppa Pig for bob). Feeds an#224 / P10.
3. **Narration** (OverSimplified, Kurzgesagt, Smallfilms, Peppa Pig, RSA, CGP Grey). Feeds an#9.
4. **Replacement and reuse** (Laika, Hanna-Barbera, Mushi Pro, *Fantastic Planet*, Character Animator triggers). Feeds ADR 0005 motion clips.
5. **Hierarchy and rod control** (Reiniger, wayang, Wan Guchan, Hilda, Archer). Feeds `rig.hierarchy`.
6. **Timing** (Zagreb, UPA, OverSimplified, Saul Bass, Reiniger): per-part cadence, pop-and-hold and music count as named, measurable methods.
7. **Depth and surface** (Ōfuji, Norstein, Disney, Cartoon Saloon, Blue's Clues, Charlie and Lola): blend modes, feathered masks, the multiplane truck, pattern fills.
8. **Collage** (Gilliam, Smith, Borowczyk & Lenica, Frank Film, VanDerBeek): public-domain ingestion, metamorphosis, match-morph.
9. **Performance** (Pugwash, Character Animator, RSA): last, because it needs input devices.

**Public-domain study clips (plan decision 9).** New study material must come from public-domain prints, never from YouTube rips [8]. These candidates were found. Each needs the legal check the plan refers to before anything is carved, and nothing is carved or committed by this report.

| Candidate | Where | Status | What it would teach |
|---|---|---|---|
| *Prince Achmed* (Reiniger, 1926) | [archive.org](https://archive.org/details/abenteuer-des-prinzen-achmed-1926-german-english) | US public domain since 2022 [E]; likely protected in Germany to 2051 | articulated silhouette, multiplane |
| *Bagudajō no tōzoku* (1926), *Kujira* (1952) (Ōfuji) | [Commons](https://commons.wikimedia.org/wiki/File:Kujira_(1952).webm) | marked public domain in Japan; US status unchecked | coloured translucency |
| *Popeye the Sailor Meets Sindbad the Sailor* (Fleischer, 1936) | [archive.org](https://archive.org/details/popeye-the-sailor-meets-sindbad-the-sailor-1936) | Public Domain Mark on the item [E] | setback depth, flat figures over a 3D set |
| *The Man with the Golden Arm* titles (Bass, 1955) | [archive.org](https://archive.org/details/the-man-with-the-golden-arm_202407) | US public domain by non-renewal; the score may be protected | kinetic cut paper, cut on the beat (picture only) |
| *Clutch Cargo* (1959) | [archive.org](https://archive.org/details/ClutchCargoOperationMoonBeam) | uploader's Public Domain Mark; contested | Syncro-Vox mouth, camera over stills |

## 6. Where the taxonomy sits on the structured ↔ semantic spectrum

Design principle 1 says a field accepts structured values, semantic names or descriptions, or goals [1]. The taxonomy uses the levels like this:

- **(a) Structured.** A method's **parameters** are typed fields with defaults: `duration_frames`, `shapes`, `body_step_hz`, the pulse strength, the glide bob. They reach the compiler only as values.
- **(b-name) Semantic name.** A **method id** (`loco.glide`) and an ordered **policy** are names in a versioned vocabulary. A name may stay in the IR, but its version is part of the compile key, so changing what `loco.glide` means re-renders visibly (ADR 0003, ADR 0004).
- **(b-LLM) Semantic description.** An agent can resolve a description into a method and its arguments at authoring time, and the resolution is recorded. For example, "Peppa-like turns" becomes `turn: [swap.fixed_profile]`, and "walks in nervously" becomes `loco.legged_cycle` with a short stride. A description never reaches the compiler.
- **(c) Semantic goal.** A **style goal** is checked by a verifier after rendering. The `an-style` targets (held-frame share, cadence histogram, cuts per minute) are (c) today, through `an.verify.style`. New goals the masters suggest include Ocelot's "limbs off the outline" for silhouettes and a per-part cadence check (mouth on ones, body on twos). Each needs a verifier before it counts as a specification.

Capabilities and defaults follow ADR 0002: requirements are data on the method, affordances are derived from the asset, and every aspect's chain ends in a requirement-free method or a recorded no-op (§3.3).

## Open questions

- **Per-part cadence is inferred, not measured,** for South Park and Hanna-Barbera. A per-region measurement (mouth versus body) on a public-domain clip would settle it; *Clutch Cargo* is the obvious test, since only its mouth moves.
- **Peppa Pig's turn and walk methods** come from observation. No production source documents its CelAction rigs.
- **Head-view counts** are unknown for Hilda and Archer. Harmony's documented baseline is 4–5 views, with TV mostly using front to three-quarter [10].
- **Some ○ marks are judgment calls** from the cited sources. A second reader should challenge the matrix before it seeds the registry. Edit the generating table, not the rendered tables, so §2 and §3 stay in step.
- **Copyright statuses are hints, not legal determinations.** Every candidate in §5 needs the legal check before carving.

## REFERENCES

[1] In-house: [`misc/docs/design_principles.md`](../design_principles.md)
[2] In-house: [`misc/docs/cutout_styles_research.md`](../cutout_styles_research.md)
[3] In-house: [`misc/docs/adr/0002-capability-applicability-defaults.md`](../adr/0002-capability-applicability-defaults.md)
[4] In-house: [`misc/docs/cutout_framework_review_2026-10.md`](../cutout_framework_review_2026-10.md) §1
[5] In-house: [`misc/docs/framework_review_2026-10.md`](../framework_review_2026-10.md) §1 (glossary)
[6] In-house: [`.claude/skills/an-style/`](../../../.claude/skills/an-style/SKILL.md)
[7] In-house: [`misc/docs/report 3 - Facial Animation, Lip Sync & Expression Systems for 2D Cutout Animation.md`](<../report 3 - Facial Animation, Lip Sync & Expression Systems for 2D Cutout Animation.md>)
[8] In-house: [`misc/docs/plan_core_and_cutan_2026-10.md`](../plan_core_and_cutan_2026-10.md) §1, decisions 4 and 9
[9] [Old Book Illustrations — terms of use (public-domain status; faithful reproductions)](https://www.oldbookillustrations.com/terms-of-use/)
[10] [Deconstructing Toon Boom's Punk rig with Matt Watts — Toon Boom](https://www.toonboom.com/training-punk-rig)

The per-source references (117) are in each family file under [`masters/`](masters/).
