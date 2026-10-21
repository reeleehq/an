# A scene space for `an`: one world, many shots (research, 2026-10-20)

Session `scene-space`, 2026-10-20. The decision this informed is ADR 0007 (`../adr/0007-scene-world.md`); the first slice is reeleehq/an#513. Owner's intent: a model of where things are and the space they take, so that every shot of one scene is a camera onto the same world, and close-ups keep the objects and distances the two-shot established. Scope was widened mid-session to the travelling view ([an#484](https://github.com/reeleehq/an/issues/484)): perspective from the world model, streams that keep phase across cuts, plates that hold only what is at infinity.

## 1. The failure, measured

The car scene of "The Plot" placed every entity by hand in screen pixels, shot by shot. Measured on the production (ledger `plot-car.md`, round 2):

- In Paul's close single the seat beside him was empty: Jerry existed in the two-shot (530 px to Paul's left at scale 2.35) and in no close-up. The ad hoc fix derived the close-ups from the two-shot by the affine `new = VP' + k·(old − VP)`, `scale × k` (the production's ad hoc re-fit script), giving a 677 px spacing at scale 3.0. That script is a hand-rolled camera.
- The steering wheel (a prop depicting Paul's hands) was placed by hand in each framing; the body-continuity dry run measured its sockets 163/191 px off the shoulder bones in the close-up against a 41 px tolerance, and 33/49 px off in the two-shot. The wheel-to-Paul size ratio differed between framings because each was eyeballed.
- The receding road (dashes, poles, trees) was about 750 `set`/`tween` actions in screen space, re-fitted by script when the framing changed; near trees baked into the rear plate stood still while the poles moved.

All three are one defect: the scene had no model of its own space, so each shot re-invented it.

## 2. Film grammar: what continuity actually requires

The continuity system is the standard way of planning, shooting and editing so that space stays legible across cuts [1]. Its rules are stated about a scene, not a shot:

- **The axis of action (180° rule).** Cameras stay on one side of the line joining the subjects, so screen direction and the subjects' left/right relation hold across cuts; crossing it makes the characters appear to swap sides [1,2]. Crossing is allowed by a motivated move: a neutral shot on the line, a cutaway, or a camera move that visibly crosses it [2].
- **Eyeline match and looking room.** A subject looking off-screen is followed by what they look at, framed with room in the direction of the look [2,3].
- **Coverage from a master.** A master (establishing) shot fixes the geography; singles, two-shots and over-the-shoulders are cut into it and must agree with it. Katz's *Shot by Shot* and *Cinematic Motion* catalogue the staging variations for dialogue [4,5]; Arijon's *Grammar of the Film Language* is the systematic reference for positioning players and cameras, including the triangle of camera positions on one side of the line [6].
- **Shot sizes are compositions, named by where the frame cuts the body**: close-up (face, cut below the chin or at the shoulders), medium close-up (chest), medium (waist), medium long (knees), full/long (whole figure); the labels differ between traditions, the body landmarks do not [7,8]. The Prose Storyboard Language makes the same point formally: a shot size describes a *composition*, and a shot is a composition plus the screen events that change it [9].

Consequence for a tool: continuity is a property of a **scene model plus cameras**, so lints (line crossing, eyeline, coverage) can only be computed when such a model exists. Shots placed independently in screen space cannot be checked, only eyeballed.

## 3. Virtual cinematography: cameras computed from a scene model

Thirty years of work converge on one architecture: an explicit 3D scene, and cameras derived from compositional intent rather than typed coordinates.

- **Camera primitives and modules.** Drucker and Zeltzer's CamDroid (1995) encapsulates camera tasks as modules whose reasons are expressed as constraints on camera parameters [10]. He, Cohen and Salesin's Virtual Cinematographer (1996) encodes film idioms as hierarchical finite state machines (two-talk, three-talk, moving actor) and uses shared camera modules for the low-level placement, which may also nudge actors to frame a shot well [11].
- **Frame constraints.** Bares et al. (2000) compute a camera from constraints on the frame (visibility, projection size, view angle) [12]; the 2008 Eurographics state-of-the-art review by Christie, Olivier and Normand surveys viewpoint computation, motion planning and editing as one field [13].
- **Narrative planners.** Jhala and Young's Darshak (2010) separates composition, camera parameters and transitions and plans camera directives alongside story events [14]; Elson and Riedl's Cambot (2007) takes a script and an extensible library of cinematic knowledge offline [15].
- **Staging and framing languages.** The Prose Storyboard Language (Ronfard, Gandhi, Boiron, Murukutla; 2015, revised 2022) describes a film shot by shot with a limited vocabulary of compositions (sizes, on-screen placement, profile angles) and events [9]. Louarn, Christie and Lamarche (2018) extend it to **staging**: where actors and objects are placed so that the wanted framings exist, solved by geometric pruning and sampling [16]. Wu and Christie's Film Editing Patterns (2018) express constraints over sequences of shots (size, angle, actor layout) and select cameras and cuts that satisfy them [17].
- **Two-subject framing.** Lino and Christie's toric space (SIGGRAPH 2015) parametrises every camera that puts two targets at chosen screen positions as a 2D manifold, which makes "a two-shot with A at screen-left third and B at screen-right third" a direct computation rather than a search; it is point-based and does not handle occlusion [18].
- **Editing as optimisation.** Galvane et al. (AAAI 2015) catalogue continuity errors (line crossing, jump cuts, size and angle mismatch) and assemble an edit from many cameras by dynamic programming over their cost [19]. Gandhi, Ronfard and Gleicher (2014) derive several framings (pan-tilt-zoom sub-frames) from one wide fixed camera by L1 optimisation over actor positions, which is exactly the "close-ups derived from the master" operation the production did by hand [20].

Consequence: the derived operation in `rewire_scene.py` (close-up = similarity transform of the master about a vanishing point) is the degenerate 2D case of a pinhole projection of one world; the general form is a per-shot camera onto a world with depth.

## 4. 2D animation tools: one stage, a camera object, depth on every layer

Every surveyed 2D tool that supports "shots of one scene" does it with a single stage in Z and a camera object, never with per-shot repositioning (claimed by vendor documentation; not measured here).

- **Multiplane camera.** Ub Iwerks built a horizontal multiplane in 1933; Disney's vertical camera (1937, *The Old Mill*) held up to six or seven glass planes and received a Scientific and Engineering Academy Award in 1938; its purpose was tracking shots through depth [21,22]. Reiniger's 1926 tabletop setup had layers but a fixed camera, hence no parallax [21].
- **Toon Boom Harmony** places background layers at Z positions and moves a Camera layer through them; a Maintain Size tool moves an element in Z without changing its apparent size, i.e. the inverse projection [23,24].
- **Moho** gives every layer a Z value (sky at −20, hill at −2 in the tutorial) and a camera whose moves produce parallax; depth of field is a project setting [25].
- **Adobe Animate** (2017) added layer depth (−5000 to 10000) and a Camera tool with the same Maintain Size option [26].
- **Cartoon Animator 5** is 2D-based but every character and prop holds a Z-depth, adjusted in a 3D top view; layered PSD scenes become Z-ordered objects for parallax cameras [27].
- **Blender Grease Pencil** places 2D strokes in a 3D scene with ordinary 3D cameras, so one scene is shot from any viewpoint [28].
- **Live2D Cubism** is a different animal: parameters and deformers animate one character's art; it has no scene camera, so it does not inform scene layout [29]. **Spine** likewise animates skeletons and leaves the camera to the host engine.

Consequence: the authored primitive in the industry is "an object at a position (with depth) in one scene, and a camera", with lowering to 2D transforms done by the tool. The 2.5D projection is the pinhole: for a billboard facing the camera, on-screen size falls as 1/z and parallax is the ratio of depths [30].

## 5. Generative video and story visualisation: layout is the consistency carrier

The same conclusion is being rediscovered by the generative-video literature, where consistency across shots is the open problem:

- **VideoDirectorGPT** (2023) has an LLM plan per-scene entity *layouts* and consistency groups, then a layout-guided generator keeps entities and backgrounds consistent across scenes [31].
- **CineMaster** (2025) gives the user 3D bounding boxes and camera trajectories as the control signal (rendered to depth maps) because 2D prompts cannot hold object placement and camera together [32].
- **FilmAgent** (2025) stages scripts in Unity 3D spaces with director, cinematographer and actor agents, i.e. a scene model first, then shots [33]. **DirectorAgent** (2026) conditions each shot's first frame on the previous shot's last to preserve layout [34].
- The 2025 camera-trajectory survey and LensCraft treat framing from subject positions as a solved geometric sub-problem (toric space, frame constraints) on which learned systems sit [35,36].

Consequence: whatever generates the art, the thing that carries layout consistency across shots is an explicit world layout plus per-shot cameras. That is the right core for `an` whether a shot is drawn by the cut-out engine, Manim, or a diffusion model later.

## 6. What `an` has today (measured in code, main @ bc8639a6d)

- `AssetRef.stage` is a **screen-space** placement per shot: `at: (x, y)` in scene pixels from the stage centre, `scale`, `after` (draw order against planes and entities). It is additive and hash-free; `at` replaces the computed layout (`an/ir/schema.py`, `_apply_stage_placement`). No depth.
- The camera is 2D (`root.pivot`): named moves, `keys` (x, y, zoom, rotation), `follow` (compiled from `screen_position`), `shake`. A zoom scales every plane equally; a depth-aware dolly is deferred (an#478, `an/stage/environments.py`).
- Environments are planes with a **parallax factor** `depth` (0 = pinned at infinity, 1 = the character plane, >1 foreground) applied to camera translation only; `plane_rect`/`frame_rect`/`uncovered_part` give a framing check at every camera key (an#211).
- `an.stage.timeline.screen_position` and `node_box` compose a node's point or box to the canvas without a browser (an#445, an#467); `an.motion.stage_poses` gives every built node's rest pose.
- `an validate` has a **cut-continuity** check (an#394): an entity that ends one shot at one placement and starts the next at another is a warning unless an opening `set` says so. It is exactly the check that becomes wrong once cuts between framings are the norm.
- `an.ir.crowd` shows the pattern for authoring sugar that lowers to ordinary entities and actions, so renderers see nothing new.
- The production-pack skill tells writers to place in pixels per shot and to re-place a character identically across consecutive shots by hand (`skills/cutan-production-pack/SKILL.md`, "Stage coordinates are pixels from the frame centre"). That instruction is the design gap in words.
- cutan's body-continuity branch (`body-attachment-lint`) declares a prop's sockets in the character's own rig units and places it from the character's `stage.at`/`stage.scale` in a compile pass (order 90), so a world-derived character placement written before that pass makes attachments follow every framing automatically.
- previz direction (an#257): "a camera move is a move of a view through a parameter space, defined once and lowered per engine". A per-shot viewpoint onto a world is that view space for the stage.

## 7. Design implications (the ADR records the decisions)

1. **A scene-level space**: members (the same entity refs the shots use) at `[x, y, z]` in the author's units with a size (`height` or `width`); draw order follows depth; a body-attached member has no position of its own.
2. **Shots are viewpoints onto it**: a pinhole camera (position, look or vanishing point, field of view) or a composition (`on: paul, size: close_up`) resolved to one; named viewpoints in the space are the coverage reused by several shots.
3. **Lowering, not a new renderer**: a viewpoint derives each member's `stage` placement (and the streams' tweens) at the IR level, before any compile pass; the compiled document, the shot-cache key and the renderers are unchanged. The 2D camera stays what it is: a move within the framed picture.
4. **Backward compatible by construction**: no space and no viewpoint means nothing changes, and a hand `stage.at` always wins (with a lint when it disagrees with the world).
5. **Continuity lints become computable**: a member in frame but absent, a listed entity out of frame, a hand placement off the world, a screen-direction flip across a cut, plates under a travelling view that are not declared far or vehicle.
6. **The travelling view is the viewpoint moving through the world in film time**; streams are world rows of props; sampling density follows 1/z.
7. **Genre specifics stay in the genre**: the core measures a member's native extent by compiling its specimen (any registered kind); cutan supplies body attachments, views and faces; an eyeline lint needs the genre's gaze and is filed there.

## REFERENCES

1. [Continuity editing (Vaia study notes)](https://www.vaia.com/en-us/explanations/media-studies/filmmaking/continuity-editing); [Axis of action, How to Film School](https://howtofilmschool.com/dictionary/axis-of-action-180-degree-rule/).
2. [The 180 degree rule, looking space and eyeline match (Learn About Film)](https://learnaboutfilm.com/?p=1666).
3. [What is eyeline continuity in film (Beverly Boy)](https://beverlyboy.com/filmmaking/what-is-eyeline-continuity-in-film/).
4. Katz SD. *Film Directing Shot by Shot: Visualizing from Concept to Screen*. Michael Wiese Productions; 25th anniversary ed. 2019. [Catalogue record](https://bampfa.org/node/182256).
5. Katz SD. *Film Directing Cinematic Motion: A Workshop for Staging Scenes*. 2nd ed. 2004. [Record](https://portal.learningally.org/Book-Details/BookID/GX231).
6. Arijon D. *Grammar of the Film Language*. Silman-James Press. [Publisher page](https://www.silmanjamespress.com/shop/filmmaking-directing/grammar-of-the-film-language/).
7. [Basic shot sizes (Video Production Handbook, LibreTexts)](https://human.libretexts.org/Bookshelves/Theater%2C_Film%2C_and_Storytelling/Video_Production_Handbook/08%3A_Video_Aesthetics/8.01%3A_Basic_Shot_Sizes).
8. [Medium shot (Wikipedia; notes the conflicting traditions)](https://en.wikipedia.org/wiki/Medium_shot).
9. Ronfard R, Gandhi V, Boiron L, Murukutla VA. The Prose Storyboard Language: A Tool for Annotating and Directing Movies. arXiv:1508.07593 (2015, v5 2022); WICED 2022. [arXiv](https://arxiv.org/abs/1508.07593), [Eurographics DL](https://diglib.eg.org/handle/10.2312/wiced20221048).
10. Drucker SM, Zeltzer D. CamDroid: A System for Implementing Intelligent Camera Control. Symposium on Interactive 3D Graphics 1995:139–144. [PDF](https://www.cs.princeton.edu/courses/archive/spr01/cs598b/papers/drucker95.pdf).
11. He L, Cohen MF, Salesin DH. The Virtual Cinematographer: A Paradigm for Automatic Real-Time Camera Control and Directing. SIGGRAPH 1996. [ACM](https://doi.org/10.1145/3596711.3596786), [Microsoft Research](https://www.microsoft.com/en-us/research/?p=150986).
12. Bares W, McDermott S, Boudreaux C, Thainimit S. Virtual 3D Camera Composition from Frame Constraints. ACM Multimedia 2000:177–186. Cited via [Burelli & Jhala, CamOn (AIIDE 2009)](https://vbn.aau.dk/files/188210862/Burelli_Jhala_CamOn_A_Real_Time_Autonomous_Camera_Control_System_AAAI_Conference_On_Artificial_Intelligence_In_Interactive_Digitale.pdf).
13. Christie M, Olivier P, Normand JM. Camera Control in Computer Graphics. Computer Graphics Forum 2008;27(8):2197–2218. [Eurographics DL](https://diglib.eg.org/handle/10.2312/CGF.v27i8pp2197-2218).
14. Jhala A, Young RM. Cinematic Visual Discourse: Representation, Generation, and Evaluation. IEEE Trans. CIAIG 2010;2(2):69–81. [PDF](https://www.cs.uky.edu/~sgware/reading/papers/jhala2010cinematic.pdf).
15. Elson DK, Riedl MO. A Lightweight Intelligent Virtual Cinematography System for Machinima Production. AIIDE 2007. [AAAI](https://ojs.aaai.org/index.php/AIIDE/article/view/18774).
16. Louarn A, Christie M, Lamarche F. Automated Staging for Virtual Cinematography. MIG 2018:4:1–4:10. [dblp](https://dblp.org/pid/63/5800); summarised in [36].
17. Wu HY, Christie M, et al. Thinking Like a Director: Film Editing Patterns for Virtual Cinematographic Storytelling. ACM TOMM 2018. [HAL](https://hal.archives-ouvertes.fr/hal-01950718).
18. Lino C, Christie M. Intuitive and Efficient Camera Control with the Toric Space. ACM Trans. Graph. (SIGGRAPH) 2015. [HAL](https://hal.archives-ouvertes.fr/hal-01142876), [SIGGRAPH history](https://history.siggraph.org/?p=112722).
19. Galvane Q, Ronfard R, Lino C, Christie M. Continuity Editing for 3D Animation. AAAI 2015;29(1):753–762. [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/9288).
20. Gandhi V, Ronfard R, Gleicher M. Multi-Clip Video Editing from a Single Viewpoint. CVMP 2014. [HAL](https://hal.archives-ouvertes.fr/hal-01067093).
21. [Multiplane camera (Wikipedia)](https://en.wikipedia.org/wiki/Multiplane_camera).
22. [Multiplane camera educator guide (Walt Disney Family Museum)](https://www.waltdisney.org/sites/default/files/WDFMMultiplaneEducatorGuide.pdf); [D23](https://d23.com/a-to-z/multiplane-camera).
23. [About Multiplane (Toon Boom Harmony 24 docs)](https://docs.toonboom.com/help/harmony-24/advanced/staging/about-multiplane.html).
24. [Camera motion module (Toon Boom Learn)](https://learn.toonboom.com/modules/camera-motion2/topic/activity-4-camera-motion).
25. [Moho tutorial 6.7: depth and the camera](https://www.lostmarble.com/moho/manual/tut06/07/index.html).
26. [Layer depth and Camera Z-depth (Adobe Animate help)](https://helpx.adobe.com/animate/using/layer-depth.html).
27. [Adjusting the Z values with 3D view (Reallusion Cartoon Animator manual)](https://manual.reallusion.com/Cartoon-Animator/Content/Resources/ENU/05_Scene/Adjusting_the_Z_Values_with_3D_View.htm); [Creating a scene from PSD files](https://manual.reallusion.com/Cartoon-Animator/Content/Resources/5.1/07-PSD-In/Creating-Layered-Scene-Custom.htm).
28. [Grease Pencil introduction (Blender manual)](https://docs.blender.org/manual/es/4.3/grease_pencil/introduction.html); [Cat Purkour: 2D animation in a 3D environment (Blender Studio)](https://studio.blender.org/blog/cat-purkour-combining-2d-animation-in-a-3d-environment).
29. [Live2D by diagrams (Cubism docs)](https://docs.live2d.com/en/cubism-editor-tutorials/figure/).
30. [Perspective projection notes (UNR CS791E)](https://www.cse.unr.edu/~bebis/CS791E/Notes/PerspectiveProjection.pdf); Forsyth & Ponce, *Computer Vision*, ch. 1 ([PDF](https://murray.cds.caltech.edu/images/murray.cds/0/02/Forsyth_1st_edition_ch1.pdf)).
31. Lin H, Zala A, Cho J, Bansal M. VideoDirectorGPT: Consistent Multi-scene Video Generation via LLM-Guided Planning. 2023. [arXiv](https://arxiv.org/abs/2309.15091).
32. Wang Q, et al. CineMaster: A 3D-Aware and Controllable Framework for Cinematic Text-to-Video Generation. 2025. [arXiv](https://arxiv.org/abs/2502.08639).
33. Xu Z, et al. FilmAgent: A Multi-Agent Framework for End-to-End Film Automation in Virtual 3D Spaces. 2025. [arXiv](https://arxiv.org/abs/2501.12909).
34. DirectorAgent (2026). [arXiv 2601.17737 via hyper.ai](https://hyper.ai/fr/papers/2601.17737).
35. LensCraft: Your Professional Virtual Cinematographer. 2025. [arXiv](https://arxiv.org/pdf/2506.00988).
36. Camera Trajectory Generation: A Comprehensive Survey of Methods, Metrics, and Future Directions. 2025. [arXiv](https://arxiv.org/pdf/2506.00974).
