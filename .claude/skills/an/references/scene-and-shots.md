# A complete scene.md and the shot types

Reference for the `an` skill (`../SKILL.md`: the index and the essentials).

### A minimal complete `scene.md`

Three shots — a date card, a map with a route drawn on and a territory changing colour, and a two-shot with dialogue — using the recipe's assets. A property holds its REST value until its first action, so anything that should start somewhere else (the title's `alpha`, the territory's first colour) gets a `set` at 0. A shot is `## Shot <id> (cutout)` followed by its fenced blocks; entities are `{kind, id, store, ref}` plus optional `stage`/`overrides`; a text unit is addressed `<id>/line_0` (or `word_N`, `glyph_N`) and a plane `<environment id>/<plane name>`.

<!-- skill-test: scene -->
````markdown
# The Vending Machine

```yaml meta
title: The Vending Machine
duration: 12.0
fps: 24
resolution: {width: 1280, height: 720}
default_renderer: cutout
default_easing: ease_in_out
style_pack: kurzgesagt
sounds:
  - {sound: bed, loop: true, gain_db: -8, duck_db: -12, fade_in: 1.0, fade_out: 1.0}
```

## Shot card (cutout)

```yaml shot
duration: 2.0
camera: {move: hold}
```

```yaml entities
- {kind: environment, id: bg, store: environments, ref: card}
- {kind: prop, id: date, store: props, ref: date}
```

```yaml actions
- {kind: set, target: date/line_0, property: alpha, value: 0.0, at: 0.0}
- {kind: tween, target: date/line_0, property: alpha, from: 0.0, to: 1.0, duration: 0.5, start: 0.2}
```

## Shot map (cutout)

```yaml shot
duration: 3.0
camera: {move: pan_right}
```

```yaml entities
- {kind: environment, id: map, store: environments, ref: map}
- {kind: prop, id: route, store: props, ref: route}
- {kind: prop, id: west_label, store: props, ref: label, overrides: {text: West}, stage: {at: [-250, -110]}}
```

```yaml actions
- {kind: tween, target: route, property: trim_end, to: 1.0, duration: 1.5, start: 0.5}
- {kind: set, target: map/west, property: tint, value: "#ba5f31", at: 0.0}
- {kind: tween, target: map/west, property: tint, to: "#3a5fa0", duration: 1.0, start: 1.5}
```

## Shot talk (cutout)

```yaml shot
duration: 7.0
camera: {move: hold}
```

```yaml entities
- {kind: environment, id: set, store: environments, ref: indoor}
- {kind: character, id: stan, store: characters, ref: stan, stage: {at: [-230, 40], scale: 1.4}}
- {kind: character, id: kyle, store: characters, ref: kyle, stage: {at: [230, 40], scale: 1.4}}
```

```yaml actions
- {kind: tween, target: stan/head, property: rotation, to: 0.15, duration: 0.4, start: 0.3}
- {kind: tween, target: stan/head, property: rotation, to: 0.0, duration: 0.4, start: 0.8}
- {kind: play, target: kyle, animation: hop, args: {height: 30}, start: 4.0}
```

```dialogue
stan: Dude, the school replaced the cafeteria.
kyle [happy]: Then we're rich! I have a quarter!
```
````

Then `an validate my_film` and `an render my_film --strict-assets`. `tests/test_skill_recipe.py` in the `an` repo runs this recipe and this scene, so they stay true.

### A Manim shot: an explainer beat inside the film

For a chart, an equation or a diagram that Manim draws better than cut-out art, a shot can be a **Manim scene file run as it is** (`pip install 'an[manim]'`; `manimkit check` says what else the machine needs). The file is a project asset, `assets/sources/<key>.py` (`mall["sources"]["chart"] = code_bytes`); the shot names it:

````markdown
## Shot chart (manim)

```yaml shot
options: {source: chart, scene: BarChartStory}
```

```dialogue
narrator: Sales doubled, then fell back.
```
````

- **Write no `duration:`.** Manim's own `play`/`wait` calls decide how long the shot runs; `an render` measures it (once per version of the file — the measurement is cached by content in `artifacts/measurements/`) and lays the film out on it. Your `scene.md` is never rewritten by a render; `an sync <dir> --accept-measured` writes the measured lengths into it (only the `duration:` lines change). A `duration:` you write that the render disagrees with is a warning, and the render wins. Size the narration to the scene's beats (`run_time=`, `self.wait()`): narration that runs past the scene holds its last frame, with a warning (`--strict-assets` refuses instead).
- The render runs in a copy of the whole `assets/sources/` folder: a helper module beside the scene file can be imported, and a data file or image under it can be loaded by a path RELATIVE to the scene file (`ImageMobject("logos/acme.png")`); an edit to any of them re-renders. A file read from OUTSIDE that folder — an absolute path, or one the scene computes (`Path.home() / "data.csv"`, an environment variable) — is recorded as the render runs (manimkit's audit hook) and keyed too: editing it re-renders the picture and the shot, leaving it alone reuses both (an#291). A literal absolute path is still warned about, because another machine will not have that file: prefer a path relative to the scene file.
- `scene:` may be omitted when the file defines one `Scene`. Optional: `quality:` (`l`/`m`/`h`/`p`/`k`; default the smallest preset as tall and as fast as the film), `background:` (`#rrggbb`, pads a scene whose aspect differs from the film's), `timeout:` (seconds).
- Everything around the shot comes from `an`: narration (a dialogue line whose speaker is not an entity), captions (sidecar only — a Manim shot has no overlay layer), `sounds` cues, transitions (a `dissolve` into or out of it works), the shot cache (an edited file re-renders; an unchanged one is reused).
- **Look at what the render reports.** Layout problems (text cut off at the frame edge, labels overlapping, shapes off screen) are warned as `assets/sources/chart.py:14: [cut-off] …` — the line of the `play` they appeared after — with the contact sheet's path (`artifacts/contact_sheets/<sha>.png`, the settled beats tiled with their times). Open the contact sheet. A scene that fails is an error at its own line. The same findings are in `artifacts/render_reports/main.json`, and `an validate` lists them (with their `file:line`) for as long as the file is unchanged.
- LaTeX (`MathTex`, `Tex`, numbered axes) needs a TeX install (`env.latex`); without one the scene renders until its first LaTeX use, which fails at that line — use `Text` instead.
- Writing the scene file itself: the `manimkit` skill (storyboard, `manimkit search` for a working example to adapt, `manimkit lint`).

## One world, many shots (the scene space)

When several shots show one scene — a two-shot and the close singles of a conversation, a car and the road behind it — describe the scene ONCE as a `world` and make each shot a `viewpoint` onto it. Every placement then follows from the world: a close-up of Paul shows Jerry beside him because the world says Jerry is there, the wheel in Paul's hands keeps its size relative to him in every framing, and the road's poles rush past at the speed the world says. A shot without a `viewpoint` is placed by hand, as before, and a hand `stage.at` always wins (validate says when it disagrees with the world).

````markdown
```yaml world
members:
- {kind: character, id: jerry, store: characters, ref: jerry, at: [-0.45, 0.65, 1.6], height: 1.75}
- {kind: character, id: paul, store: characters, ref: paul, at: [0.45, 0.65, 1.6], height: 1.75}
- {kind: prop, id: wheel, store: props, ref: wheel_hands, attached: {to: paul}, after: paul}
- {kind: environment, id: set, store: environments, ref: car_cabin}
viewpoints:
  two_shot: {at: [0, 0, 0], vanish: [0, -262], fov: 50}
  paul_single: {subject: paul, size: close_up, subject_at: [150, 0]}
  jerry_single: {subject: jerry, size: close_up, subject_at: [-150, 0]}
travel:
  speed: 20
  far: 60
  streams:
  - {id: dash, ref: road_dash, height: 0.1, every: 12, y: 1.2, after: set/rear_view}
  - {id: pole, ref: pole, height: 6, every: [30, 50], lane: [3, 3.5], y: 1.2, after: set/rear_view}
  - {id: tree, ref: olive_tree, height: 4, every: [10, 40], lane: [-14, -5], y: 1.2, after: set/rear_view}
  plates: {far: [set/rear_view], vehicle: [set/cabin, set/front]}
```

## Shot mountain (cutout)

```yaml shot
duration: 10.0
viewpoint: two_shot
```

## Shot its_big (cutout)

```yaml shot
duration: 6.0
viewpoint: jerry_single
```
````

- **Units are yours** (metres read well); `x` is right, `y` is DOWN (the stage's axis), `z` is away from the viewer. A character's `at` is where its feet stand; `height` is its size in your units (its art's extent is measured for you). An `environment` member is present in every framed shot and placed by nothing: plates are per shot, and a close-up usually has its own.
- **A viewpoint is a camera**: `at`, `look: [yaw, pitch, roll]` in degrees or `look_at: [x, y, z]` or `vanish: [sx, sy]` (where the road's vanishing point lands on screen), and `fov` (horizontal, default 50°) or `focal` (pixels). Or a **composition**: `subject` (one member or a list), `size` (`close_up` head and shoulders, `medium` waist up, `full`, `wide`) or `distance`, and `subject_at` (where the subject lands, pixels from the frame centre). Name the coverage in `viewpoints` and reuse it: two shots on `jerry_single` frame identically, and `cut_continuity` knows a cut between two viewpoints is a cut.
- **What a framed shot lists** is what you place by hand or animate; everything else the frame shows is added for you (`an validate` reports it as info; `an world show <dir>` prints the whole lowered shot). A travel's streams are drawn by a bounded set of entities (one per instance that fits between `near` and `far`), and a shot whose streams would cost more than `max_actions` (20,000 by default) is refused with the knobs to turn: `every`, `far`, `tolerance_px`, the shot's length. `hide: [jerry]` on a viewpoint leaves a member out (a shot that lists it anyway keeps it: the listing wins). A hand `stage: {at: [...]}` on a listed member nudges it and keeps the world's size; add `scale` only to change the size too. Actions stay in the shot's screen pixels, so a 2 px seat bob is 2 px in any framing.
- **A travel** is the viewpoint moving through the world at `speed` units per second of film time; the cast rides with it; `streams` are rows of one prop (`every` units apart, `lane` to the right of the direction, at height `y`), positioned once in the world so that every shot sees the same poles in the same places at the same film time. Under a travel, declare every plane of the shot's environment in `plates`: `far` for what is at infinity (the sky, the horizon, the far range — and NOTHING nearer, which the streams draw; a far plate is `depth: 0`), `vehicle` for what is rigid with the camera (the cabin, the dashboard). A plate with near trees baked in stands still while the poles move, and reads as broken.
- **The line**: `an validate` warns when two members swap sides across a cut (the 180° rule). Keep a conversation's viewpoints on one side of the line between the speakers.
- **Frames of reference** (anything that moves WITH or PAST something else: a car, a deck, a platform, a crane): name the frames before placing anything, `in: <frame>` on members, viewpoints, streams and planes, `world.frames` for the tree. `travel` with a `speed` is sugar for a moving `vehicle` frame. The recipe and the checks are in `references/planes-of-movement.md`; `an world show <dir> --frames` prints the poses.
