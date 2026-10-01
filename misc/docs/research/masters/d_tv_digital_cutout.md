# Study the masters, family D: TV digital cut-out and performance-driven puppets

*2026-10-01 · part of [`../study_the_masters.md`](../study_the_masters.md) (an#223) · sources S21–S27 · entry format and tags as in [family A](a_cutout_film_and_silhouette.md)*

Digital cut-out on a TV schedule: the closest relatives of what `an` produces. They span the rig axis from Peppa Pig's single view to Hilda's deformer hierarchies, and the timing axis from keyed to performed live.

## S21 · South Park (`SP`) — construction paper, emulated

**What.** Comedy Central, from 1997; paper stop-motion pilot, then computer emulation (PowerAnimator, then Maya). Measured statistics: `cutout_styles_research.md` §4.1 [1].

**Methods.** Flat rigid pieces on a plane with paper texture and a "no-platen" gap shadow (`rig.flat_pieces`, `surface.paper_shadow`, `surface.grain`, `surface.outline`) [2]. Mouths, hands and heads switched by driven keys (`swap.part`, `swap.view`, `speech.mouth_chart`) [1]. Bodies on twos and threes, mouths inferred on ones (`timing.stepped`, `timing.per_part_cadence`) [1]. Waddle and hop walks (`loco.bob`); brows and lids carry the expression (`face.expression_axes`); a locked camera (`camera.locked`); pitch-raised voices (`sound.voice_fx`).

**Cues.** Measured: 64% identical frames, 50% / 24% / 26% one / two / three-plus intervals, 12.4 cuts/min, mean shot 4.2 s, median camera shift 0.11 px [1]; a six-day production cycle [1].

**Contributes.** The baseline of the set: the style `an` already hits, and the one every other source is measured against.

**Written.** [2] AWN, "Dig This! Using computers to simulate cut-out animation techniques: South Park and Blue's Clues"; [3] *6 Days to Air*.

**Video.** [S20E03 excerpt](https://www.youtube.com/watch?v=kRjHSJVqoac&t=0) (the measured window).

**Copyright.** In copyright.

## S22 · Blue's Clues (`BC`) — photographed craft materials, keyed with a live host

**What.** Nickelodeon, 1996–2006; animation process developed by Dave Palmer with Big Pink [2][4].

**Methods.** Characters and props built as real objects from construction paper, fabric, pipe-cleaners and clay, photographed or scanned, never redrawn; the material's texture is the surface (`rig.photo_parts`, `surface.material_texture`) [2]. Cleaned in Photoshop, animated as flat layers in After Effects, edited in Media 100, keyed with Ultimatte (`rig.flat_pieces`) [2]. The live host shot against a colour key and composited into the paper world (`stage.live_action`, `stage.composite_3d`) [2][4]. Deliberate pauses after each question, long enough for the youngest viewers to answer (`timing.viewer_pause`) [4].

**Cues.** Two episodes in eight weeks against sixteen weeks for one done traditionally [2]; 70 animators by 2002 [4]; frame rate not stated.

**Contributes.** Craft material as the art, and the viewer's response as a timing unit.

**Written.** [2] AWN, "Dig This!"; [4] *Blue's Clues*.

**Video.** [*Behind The Clues — 10 Years of Blue*](https://archive.org/details/youtube-pwpC4IxvXTU) (a fan upload of the 2006 special).

**Copyright.** In copyright (Paramount).

## S23 · Peppa Pig (`PP`) — one view, no turnaround

**What.** Astley Baker Davies, London, from 2004; animated in CelAction2D, which rigs drawn pieces on a skeleton (`rig.flat_pieces`) [5][6].

**Methods.** Profile-only characters with both eyes on the visible side of the head; no front view exists (`swap.fixed_profile`) [7]. A left/right turn is most likely a mirrored rig, a snap flip with no in-between [E]. Flat shapes, solid colour, thin outline (`surface.outline`); arm colour changes to stay readable against the background [5]. A side-on stage strip with a ground line and rolling hills (`stage.profile_strip`) [E]. A bouncy bob walk (`loco.bob`) [E]. A narrator plus short lines (`speech.narrator`). CelAction's dope sheet made the workflow learnable in a week by animators new to computers [5].

**Cues.** About 5 min per episode [7]; one head view [E]; mouth count and frame rate unknown.

**Contributes.** The single-view design system: the turnaround problem removed by design. The cheapest legible preschool cut-out.

**Written.** [5] Skwigly, "Peppa Pig, CelAction 2D and the Future of British Animation" (2004); [6] CelAction news, 2009; [7] *Peppa Pig*.

**Video.** *(search)* [Official-channel compilation](https://www.youtube.com/watch?v=20TEMgX2nR4).

**Copyright.** In copyright (Hasbro).

## S24 · Charlie and Lola (`CL`) — picture-book collage, rigged

**What.** Tiger Aspect for CBeebies, 2005–08, from Lauren Child's books [8][9][10].

**Methods.** A paper world: characters keep the books' cut-out look, even the snow is paper snowflakes (`rig.flat_pieces`) [8]. Photographic textures, fabric, wallpaper, photomontage and archive footage collaged around flat characters (`surface.material_texture`, `rig.photo_parts`, `stage.composite_3d`) [8][10]. Animated in CelAction2D [9]. Children's voices recorded first, then storyboard and animatic (`sound.voice_first`) [8]. Flat staging (`stage.flat_graphic`).

**Cues.** 78 × 11 min plus specials; about 50 crew [8][10].

**Contributes.** Real-world textures pasted into a digital rig: the bridge between Blue's Clues' photographed materials and Gilliam's collage.

**Written.** [8] Lauren Child on making the series; [9] CelAction news, 2003; [10] *Charlie and Lola*.

**Video.** [Official channel, series 1 episode 1](https://www.youtube.com/watch?v=WJfBajyEdug).

**Copyright.** In copyright (Tiger Aspect / BBC).

## S25 · Archer (`AR`) — photo-referenced puppets, slide rather than draw

**What.** Floyd County Productions, Atlanta, for FX, 2009–2023 [11][12].

**Methods.** Costumed models photographed as reference, characters drawn as vectors in Illustrator, bodies split into layers with rotation points at the joints and linked into After Effects puppets (`rig.hierarchy`) [11]. A part slides rather than being redrawn: "the guard's forearm and fist will slide upward into Archer's nose" (`timing.pop_and_hold`) [11]. One reusable head rig per year applied to every costume; bodies drawn with dummy heads (`swap.bank`, `swap.pose`) [11]. Dialogue shots lock the body (`timing.sectioning`). Harmony added for drawn in-betweens in fast action from season 7 [12]. Backgrounds modelled in 3D, rendered and painted over; 2D characters sandwiched between layers of a 3D vehicle (`stage.composite_3d`) [11]. Costumes reused as background extras (`stage.crowd`).

**Cues.** About 10–11 weeks per episode with 4–5 in parallel; about 60 staff [11][12]; frame rate and head views unknown.

**Contributes.** Hierarchy plus heavy reuse at adult-TV scale, over painted-over 3D sets.

**Written.** [11] AWN, "Animating 'Archer'" (2014); [12] AWN, "The Minimalist Animation of 'Archer'" (2016); [13] No Film School, "How an Action Scene from 'Archer' Gets Made".

**Video.** *(search)* [Official trailer](https://www.youtube.com/watch?v=iNwLvaWaTqA).

**Copyright.** In copyright (FX / Disney).

## S26 · Hilda and Mercury Filmworks (`HI`) — deep Harmony rigs, roughened

**What.** *Hilda* (Netflix, 2018–2023), Mercury Filmworks, Ottawa; rig mechanics filled in from Mercury's *Kid Cosmic* and *The Duke's Game* write-ups [14][15][16].

**Methods.** Toon Boom Harmony puppets mixed with drawn key poses for a less rigid look [14]. Art cut into small chunks, chained by pegs and deformers into a hierarchy (`rig.hierarchy`, `rig.deformation`) [15]. Master Controllers isolate turns, head tilts, hands and feet (`swap.view`, `swap.view_blend`); deformation switches (`rig.draw_order_keys`); drawing substitution for hands, eyes and mouths (`swap.part`, `speech.mouth_chart`) [15]. Deliberately slow timing, a drawing every 3 or 4 frames (`timing.stepped`) [14]. Lighting built into the rigs and posed with them (`surface.light_rig`) [14]. Backgrounds and characters coloured the same way.

**Cues.** On threes and fours, 6–8 drawings per second at 24 fps [14][E]. Harmony's baseline: 4–5 turnaround views with TV mostly using front to three-quarter, an 8-mouth chart, over a hundred hand swaps on a production rig [17][18].

**Contributes.** The deep rig, deliberately made to read as hand-drawn by slow timing and lighting baked into the rig.

**Written.** [14] Toon Boom, "Mercury Filmworks on the craft and magic behind Hilda"; [15] Toon Boom, "Making of The Duke's Game, Part 2: Rigging, Animation, Comp"; [16] Apt613 podcast with Mercury Filmworks; [17] Toon Boom, "Deconstructing the Punk rig with Matt Watts"; [18] Harmony documentation, the Master Controller.

**Video.** *(search)* [*Hilda* official trailer](https://www.youtube.com/watch?v=jZn-o82dvyk); *(search)* [Toon Boom, a full turnaround deformation rig](https://www.toonboom.com/resources/video-tutorials/video/creating-a-full-character-turnaround-deformation-rig).

**Copyright.** In copyright. Note also *The Amazing World of Gumball*, which puts 2D rigged characters on photographic backgrounds beside CGI, stop-motion and puppet characters in one frame [E].

## S27 · Live Adobe Character Animator (`CA`) — the puppet as an instrument

**What.** *The Simpsons* live segment (Fox, 15 May 2016), *The Late Show*'s cartoon segments (CBS, from 2016), *Our Cartoon President* (Showtime, 2018) [19][20][21].

**Methods.** Layered Photoshop or Illustrator puppets as a tree of groups (`rig.hierarchy`, `rig.deformation`) [19]. Lip sync from audio alone: phonemes detected and mapped to visemes (`speech.mouth_chart`) [19]. Webcam face tracking of head, brows and blinks (`face.performance`, `face.expression_axes`) [21]. Pre-animated stems and replacement drawings fired live from a keypad: arm raises, turns, blinks, entrances, cuts (`swap.bank`, `swap.part`, `timing.live_performance`) [19][20]. Three operators on the *Late Show*: voice, shoulders and gestures, triggers [22]. A Head Turner swaps whole drawn head views (`swap.view`). Hybrid on *Our Cartoon President*: live puppetry for conversations, keyframed work for full-body action, mouths corrected by hand afterwards [21].

**Cues.** 11 visemes from 60+ phonemes; about 11 functional Homer mouths (15 with exaggerated ones); 0.5 s lip-sync latency [19]; a 2,659-layer PSD; a 60-key trigger pad [20]; Head Turner with 7 views [E, a tutorial site]; about 80% of each *Our Cartoon President* episode made live [21].

**Contributes.** Real-time performance: audio-driven visemes plus keyed replacement triggers. The modern descendant of Captain Pugwash (S09).

**Written.** [19] Cartoon Brew, "How 'The Simpsons' Used Adobe Character Animator…"; [20] ProVideo Coalition, "The Simpsons go live"; [21] Adobe blog on *Our Cartoon President*; [22] Collider, interview with Tim Luecke.

**Video.** *(search)* [The Simpsons live segment](https://www.youtube.com/watch?v=k1ZCSd9qPbo); *(search)* [Cartoon Trump on The Late Show](https://www.youtube.com/watch?v=PD9-zrGxrs4).

**Copyright.** In copyright.

## REFERENCES

[1] In-house: [`misc/docs/cutout_styles_research.md`](../../cutout_styles_research.md)
[2] [Dig This! Using computers to simulate cut-out animation techniques: South Park and Blue's Clues — Animation World Network](https://www.awn.com/animationworld/dig-using-computers-simulate-cut-out-animation-techniques-south-park-and-blues-clues)
[3] [6 Days to Air: The Making of South Park — Wikipedia](https://en.wikipedia.org/wiki/6_Days_to_Air:_The_Making_of_South_Park)
[4] [Blue's Clues — Wikipedia](https://en.wikipedia.org/wiki/Blue%27s_Clues)
[5] [Peppa Pig, CelAction 2D and the Future of British Animation — Skwigly, 2004](https://www.skwigly.co.uk/peppa-pig-celaction-2d-and-the-future-of-british-animation/)
[6] [News from 2009 — CelAction](https://www.celaction.com/en/news/archive-2009)
[7] [Peppa Pig — Wikipedia](https://en.wikipedia.org/wiki/Peppa_Pig)
[8] [Lauren Child on the Charlie and Lola television series — Milk Monitor](https://milkmonitor.me/the-charlie-and-lola-television)
[9] [News from 2003 — CelAction](https://www.celaction.com/en/news/archive-2003)
[10] [Charlie and Lola (TV series) — Wikipedia](https://en.wikipedia.org/wiki/Charlie_and_Lola_(TV_series))
[11] [Sarto, Animating 'Archer' — Animation World Network, 2014](https://www.awn.com/animationworld/animating-archer)
[12] [Sarto, The Minimalist Animation of 'Archer' — Animation World Network, 2016](https://www.awn.com/animationworld/minimalist-animation-archer)
[13] [How an Action Scene from 'Archer' Gets Made on Schedule — No Film School, 2014](https://nofilmschool.com/2014/01/animation-how-action-scene-from-archer-gets-made-on-schedule)
[14] [Mercury Filmworks on the craft and magic behind Hilda — Toon Boom, 2022](https://www.toonboom.com/mercury-filmworks-on-the-magic-behind-hilda)
[15] [Making of The Duke's Game, Part 2: Rigging, Animation, Comp — Toon Boom, 2022](https://www.toonboom.com/making-of-the-dukes-game-part-2-rigging-animation-comp)
[16] [Podcast: meet the local animation studio behind Netflix's Hilda — Apt613](https://apt613.ca/podcast-mercury-filmworks/)
[17] [Deconstructing Toon Boom's Punk rig with Matt Watts — Toon Boom](https://www.toonboom.com/training-punk-rig)
[18] [About the Master Controller — Toon Boom Harmony 20 documentation](https://docs.toonboom.com/help/harmony-20/premium/master-controller/about-master-controller.html)
[19] [Failes, How 'The Simpsons' Used Adobe Character Animator to Create a Live Episode — Cartoon Brew, 2016](https://www.cartoonbrew.com/tech/simpsons-used-adobe-character-animator-create-live-episode-139775.html)
[20] [Christiansen, The Simpsons go live: an exclusive inside look — ProVideo Coalition, 2016](https://www.provideocoalition.com/simpsons-go-live-exclusive-inside-look/)
[21] [A surprise presidential win inspires Our Cartoon President on Showtime — Adobe blog, 2018](https://blog.adobe.com/en/publish/2018/07/17/a-surprise-presidential-win-inspires-our-cartoon-president-on-showtime)
[22] [Our Cartoon President: Tim Luecke on the animation — Collider](https://collider.com/our-cartoon-president-animation-tim-luecke-interview/)
