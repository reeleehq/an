# Study the masters, family F: multiplane, stop motion and contrast cases

*2026-10-01 · part of [`../study_the_masters.md`](../study_the_masters.md) (an#223) · sources S33–S38 · entry format and tags as in [family A](a_cutout_film_and_silhouette.md)*

These are not cut-out, and most were chosen as **contrasts**. Each isolates one method in an extreme form that cut-out can borrow: depth by planes, combinatorial replacement, a fixed face, palette as world-coding, flat decorative staging, and real paper re-placed by hand.

## S33 · Disney multiplane, *The Old Mill* (`DM`), with Fleischer's setback

**What.** Walt Disney Productions, *The Old Mill* (1937, dir. Wilfred Jackson), the first use of the vertical multiplane camera built by Bill Garity [1][2]. Contrast: the Fleischer Stereoptical "setback" (*Popeye the Sailor Meets Sindbad the Sailor*, 1936) [3].

**Methods.** Art split into planes painted on glass, stacked under a downward camera (`stage.multiplane`) [1][2]. A push moves the near planes towards the camera while the far plane stays, so the moon does not grow as it would under a zoom (`camera.multiplane_truck`) [2]. Rack focus from a dew-covered web in the foreground to the distant mill (`camera.rack_focus`) [1]. Separate lighting per plane (`surface.light_rig`); rain, lightning, ripples and reflections drawn on their own levels, with distorting "ripple glass" (`fx.particles`, `stage.translucent_layers`) [1]. Full animation on ones (`timing.on_ones`); score-led, no dialogue (`sound.score_led`, with the moves timed to it, `timing.music_count`). Fleischer: a 3D miniature set on a turntable behind a vertical glass platen holding the cels, turned a little each frame to fake a tracking shot (`stage.composite_3d`) [3].

**Cues.** Up to 7 planes [4]; up to about 10 operators per frame [1]; 9 min [1]; plane spacing unknown.

**Contributes.** Depth by moving planes along the lens axis, focus as a tool for attention, and (Fleischer) flat figures over a real 3D set.

**Written.** [1] Cartoon Research, "The Old Mill Celebrates 80th Anniversary"; [2] Walt Disney Family Museum, Multiplane Educator Guide; [3] Animation Studies blog, "The Fleischer Studio's 'Setback' Camera vs. Disney Realism"; [4] *Multiplane camera*.

**Video.** *(search)* [*The Old Mill*](https://www.youtube.com/watch?v=qwcOiEaQFAw) (the opening is the rack focus); [*Popeye the Sailor Meets Sindbad the Sailor* (1936)](https://archive.org/details/popeye-the-sailor-meets-sindbad-the-sailor-1936).

**Copyright.** *The Old Mill*: Disney, protected in the US until about 2033 [E]. *Sindbad*: marked Public Domain Mark 1.0 on archive.org; the Fleischer Popeye two-reelers are widely held to be US public domain [E]. The best public-domain candidate in the set for a **setback / depth** study clip, after the legal check.

## S34 · Laika replacement faces (`LK`) — combinatorial replacement

**What.** Laika, Portland: *Coraline* (2009, dir. Henry Selick) and later features; faces by Brian McLean and Martin Meunier [5][6][7].

**Methods.** The face split at the eye line into an upper half (brows and eyes) and a lower half (mouth), so the expression space is the product of the two sets (`swap.split_face`) [5]. Facial animation done first in Maya, then 3D-printed and hand-painted; halves attached with magnets; the seam painted out in post (`swap.part`) [6][7]. Parts stored as a numbered library sorted by mood. Expression carried by the face swaps (`face.expression_axes`); mouths from the same library (`speech.mouth_chart`).

**Cues.** 207,336 possible Coraline face combinations, 17,633 for Mother [5]; 6,333 faces [E, headline figure]; 24 fps capture [6]; Coraline makes 16 expressions in 35 s [5].

**Contributes.** The arithmetic of split channels: a few dozen upper and lower parts give tens of thousands of expressions. The direct model for independent eye/brow and mouth swap channels, which `an` already has.

**Written.** [5] Laika Hidden Worlds, *Coraline*; [6] Post Magazine cover story, February 2009; [7] 3DPrint.com, Brian McLean on 3D-printed faces.

**Video.** *(search)* [Laika, "Character Counts: Making the Colorful Cast of Coraline"](https://www.youtube.com/watch?v=OcTM1VN5SYE); *(search)* [Laika, "Biggest Smallest World"](https://www.youtube.com/watch?v=azdzJs-Y6DQ).

**Copyright.** In copyright.

## S35 · Adam Elliot, *Mary and Max* (`MM`) — palette as world, a large mouth library

**What.** Clay feature, Melodrama Pictures, Melbourne, 2009 [8][9][10].

**Methods.** Sculpted replacement mouths swapped per frame, pupils separate (`swap.part`, `speech.mouth_chart`) [8]. On twos: twelve moves per second of 24 fps film (`timing.stepped`) [8]. One palette per world: Melbourne sepia and brown, New York black, white and grey, with rare red accents (`stage.world_coding`) [8][9]. Slow pacing carried by a narrator (`speech.narrator`).

**Cues.** 1,026 mouths, Max alone more than 30; 394 pupils; 212 puppets [8]; 4 s per animator per day [8] against about 5 s [9].

**Contributes.** Palette switched by location, the clearest case of world-coding in the set.

**Written.** [8] Screen Education study guide; [9] AWN, "'Mary and Max': Elliot and Clayography"; [10] *Mary and Max*.

**Video.** *(search)* [The making of *Mary and Max*](https://www.youtube.com/watch?v=UUVzPaBANkw).

**Copyright.** In copyright.

## S36 · Cartoon Saloon (`CS`) — flat decorative staging, line style per world

**What.** Kilkenny: *The Secret of Kells* (2009), *Song of the Sea* (2014), *Wolfwalkers* (2020) [11][12][13].

**Methods.** *Kells*: flat with false perspective, "like medieval art"; a thick "stained glass" outer line added digitally (`stage.flat_graphic`, `surface.outline`) [11]. *Wolfwalkers*: woodcut-style line for the town, scratchy pencil and watercolour for the forest, the heroine's line changing over her arc (`stage.world_coding`, `surface.engraving`, `surface.material_texture`) [12][13]. Graphic-novel staging: triptychs, split screens, frames within the frame (`stage.frame_in_frame`, `fx.frame_mask`) [12]. Pop-up-book planes over a ground surface (`stage.multiplane`, `camera.multiplane_truck`) [13]. Soft painted edges in the forest (`surface.soft_edge`, `rig.mask`).

**Cues.** About 3.5 min of "Wolfvision" sequences [12]; frame rates and layer counts unknown.

**Contributes.** Line style as a per-world surface, and the frame within the frame. Both transfer to cut-out directly.

**Written.** [11] AWN, "Moore Illuminates 'The Secret of Kells'"; [12] befores & afters, "Wolfwalkers and the art of staging shots"; [13] VFX Voice, "Running with Wolves".

**Video.** *(search)* ["Wolfwalkers — A Hand-Drawn World"](https://www.youtube.com/watch?v=lRSo6-8SsHM).

**Copyright.** In copyright.

## S37 · Jiří Trnka, *The Hand* (`TR`) — a fixed face

**What.** Czech puppet film *Ruka* (1965), Krátký Film Praha, Trnka's last [14][15].

**Methods.** Carved faces with one fixed expression; no replacement faces, no lip sync, which Trnka called "barbaric" for puppets (`face.posture_only`, `speech.pose_only`) [14]. Emotion from head angle, the profile against the light, body pose and silhouette (`surface.light_rig`) [14][15]. Light and colour carry the story: the sky darkens, the hand turns from white to black [16]. Music instead of dialogue (`sound.score_led`).

**Cues.** Zero replacement faces, zero mouth shapes [14].

**Contributes.** The opposite of Laika: one rest face, and expression from rotation, light, pose and timing. The cheapest expressive mode, and the requirement-free end of the expression chain.

**Written.** [14] Film Comment, "The Puppet Master"; [15] Senses of Cinema, "The Passion of the Peasant Poet"; [16] Fantasy/Animation on *Ruka*.

**Video.** *(search)* [*Ruka* (1965), an unofficial upload](https://vimeo.com/60337657).

**Copyright.** In copyright (likely until about 2053 [E]).

## S38 · Paper stop motion: Verona Riots, "Live For The Moment" (`VR`) — real paper, re-placed

**What.** Music video by Nívola Uyá (illustration, cutting) and Alberto Serrano (photography, animation), Mallorca, 2014 [17][18].

**Methods.** Real paper figures cut with scalpel and scissors and placed with tweezers and pins; isolated figures moved inside floral compositions (`rig.single_piece`, `surface.material_texture`) [17]. No joints: a piece is re-placed each frame rather than pinned and rotated. Each composition photographed for two frames (`timing.stepped`) [17]. Real paper casts real shadows (`surface.paper_shadow`). Very little computer work [18].

**Cues.** 5,160 frames, 2,580 compositions, so on twos; about 400 paper elements [17].

**Contributes.** A measured on-twos paper reference with physical shadows: a target for what `surface.paper_shadow` and `surface.material_texture` imitate.

**Written.** [17] Última Hora, 25 May 2014; [18] Nívola Uyá's making-of post.

**Video.** [Vimeo 98802719](https://vimeo.com/98802719) (title confirmed by search; the page was not fetched).

**Copyright.** In copyright.

## REFERENCES

[1] [The Old Mill Celebrates 80th Anniversary — Cartoon Research](https://cartoonresearch.com/index.php/the-old-mill-celebrates-80th-anniversary/)
[2] [Multiplane Camera Educator Guide — Walt Disney Family Museum](https://www.waltdisney.org/sites/default/files/030114_MultiplaneGuideFINAL.pdf)
[3] [The Fleischer Studio's 'Setback' Camera vs. Disney Realism — Animation Studies blog](https://blog.animationstudies.org/the-fleischer-studios-setback-camera-vs-disney-realism/)
[4] [Multiplane camera — Wikipedia](https://en.wikipedia.org/wiki/Multiplane_camera)
[5] [Coraline — Laika Hidden Worlds](https://www.laikahiddenworlds.com/coraline)
[6] [Coraline animated via stop motion — Post Magazine, February 2009](https://postmagazine.com/publications/2009/February-1-2009/COVER-STORY-CORALINE-ANIMATED-VIA-STOP-MOTION/)
[7] [Brian McLean talks 3D printed faces for Laika stop-motion animation — 3DPrint.com](https://3dprint.com/238607/brian-mclean-talks-3d-printed-faces-for-laika-stop-motion-animation/)
[8] [Mary and Max study guide — Screen Education](https://www.chicagofilmfestival.com/wp-content/uploads/2014/12/Study-Guide-MaryandMax.pdf)
[9] ['Mary and Max': Elliot and Clayography — Animation World Network](https://www.awn.com/animationworld/mary-and-max-elliot-and-clayography)
[10] [Mary and Max — Wikipedia](https://en.wikipedia.org/wiki/Mary_and_Max)
[11] [Moore Illuminates 'The Secret of Kells' — Animation World Network](https://www.awn.com/animationworld/moore-illuminates-secret-kells)
[12] ['Wolfwalkers' and the art of staging shots — befores & afters, 2020](https://beforesandafters.com/2020/12/16/wolfwalkers-and-the-art-of-staging-shots/)
[13] [Cartoon Saloon: Running with Wolves in Wolfwalkers — VFX Voice](https://vfxvoice.com/cartoon-saloon-running-with-wolves-in-wolfwalkers/)
[14] [The Puppet Master: the complete Jiří Trnka — Film Comment](https://www.filmcomment.com/deep-focus-puppet-master-complete-jiri-trnka/)
[15] [The Passion of the Peasant Poet: Jiří Trnka — Senses of Cinema, 2013](https://www.sensesofcinema.com/2013/cteq/the-passion-of-the-peasant-poet-jiri-trnka-a-midsummer-nights-dream-and-the-hand/)
[16] [Political oppression and resistance in Jiří Trnka's Ruka — Fantasy/Animation](https://www.fantasy-animation.org/current-posts/political-oppression-and-resistance-in-ji-trnkas-ruka-the-hand-1965)
[17] [Los recortes de papel de Nívola Uyá animan la música de Verona Riots — Última Hora, 2014](https://www.ultimahora.es/noticias/cultura/2014/05/25/124966/recortes-papel-nivola-uya-animan-musica-verona-riots.html)
[18] [Making-of del videoclip stop motion Live For The Moment — Nívola Uyá](https://nivolauya.com/making-of-del-videoclip-stop-motion-live-for-the-moment/)
