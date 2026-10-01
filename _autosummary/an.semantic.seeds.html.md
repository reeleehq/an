# an.semantic.seeds

The core’s vocabulary: views over the kind and easing registries, camera moves, IR fields.

ADR 0003’s first slice seeds the registry with today’s named vocabularies.
The **core’s** share is here (a genre contributes the rest through
[`an.genres.Genre`](an.genres.html.md#an.genres.Genre)):

- **action kinds** and **entity kinds** — *views* over
  [`an.genres.registry`](an.genres.registry.html.md#module-an.genres.registry), so a genre’s kinds appear as entries the moment it
  > registers them, with their owner and [`version`](an.genres.html.md#an.genres.ActionKind.version);
- **easings** — a view over [`an.timing.easing.easing_entries()`](an.timing.easing.html.md#an.timing.easing.easing_entries) (the
  easing canon already carries a version per entry);
- **camera moves** — a view over [`an.ir.camera.CAMERA_MOVES`](an.ir.camera.html.md#an.ir.camera.CAMERA_MOVES), versioned
  in [`CAMERA_MOVE_VERSIONS`](#an.semantic.seeds.CAMERA_MOVE_VERSIONS) (a test fails when a move has none); each is
  a path through the `framing2d` **view space** and requires an engine that
  lowers it (`space.framing2d`, [`an.semantic.views`](an.semantic.views.html.md#module-an.semantic.views), an#257);
- **view spaces** — `framing2d` and `orbit3d` ([`an.semantic.views`](an.semantic.views.html.md#module-an.semantic.views));
- **IR fields** (kind `field`) — what the scene document’s fields accept,
  the notes the `an iterate` prompt used to hand-list. Each says which
  spectrum levels it takes: a field that accepts only (a) says so, and no
  resolver will invent a value for it (ADR 0003 decision 5).

Nothing here imports `an.ir` at module level; the views import their sources
when read.

```pycon
>>> from an.semantic.registry import lookup
>>> lookup("action", "tween").version, lookup("easing", "linear").kind
('1', 'easing')
```

### Module Attributes

| [`CAMERA_MOVE_VERSIONS`](#an.semantic.seeds.CAMERA_MOVE_VERSIONS)     | Version of each named camera move (ADR 0003).      |
|---------------------------------------------------------------------------|----------------------------------------------------|
| [`CAMERA_MOVE_DESCRIPTIONS`](#an.semantic.seeds.CAMERA_MOVE_DESCRIPTIONS) | One sentence per camera move, in production terms. |
| [`CORE_FIELDS`](#an.semantic.seeds.CORE_FIELDS)              | the core).                                         |

### Functions

| [`schema_of_callable`](#an.semantic.seeds.schema_of_callable)(fn, \*[, skip, positional])   | A JSON Schema object for `fn`'s keyword parameters, defaults included.   |
|---------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|

### an.semantic.seeds.CAMERA_MOVE_DESCRIPTIONS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'hold': 'a locked-off camera: no move', 'pan_left': 'truck the camera left across the frame (on a flat stage a pan and a truck look the same)', 'pan_right': 'truck the camera right across the frame', 'pull_out': 'a slow pull out: zoom 1.0 → 0.8 over the shot, eased', 'push_in': 'a slow push in: zoom 1.0 → 1.25 over the shot, eased', 'tilt_down': 'move the camera down across the frame', 'tilt_up': 'move the camera up across the frame (spans the frame height)', 'zoom_in': 'a stronger zoom in: 1.0 → 1.5 over the shot', 'zoom_out': 'a stronger zoom out: 1.0 → 0.7 over the shot'}*

One sentence per camera move, in production terms.

### an.semantic.seeds.CAMERA_MOVE_VERSIONS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'hold': '1', 'pan_left': '1', 'pan_right': '1', 'pull_out': '1', 'push_in': '1', 'tilt_down': '1', 'tilt_up': '1', 'zoom_in': '1', 'zoom_out': '1'}*

Version of each named camera move (ADR 0003). Bump one when its keys change.

### an.semantic.seeds.CORE_FIELDS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Entry](an.semantic.html.md#an.semantic.Entry), ...]* *= (Entry(id='field.meta', kind='field', version='1', name='meta', title='', description="the film's header", usage='meta: {title, author, duration, fps, resolution, default_renderer, notes, default_easing, step_hz, style_pack, sounds, captions}', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot', kind='field', version='1', name='shot', title='', description='one shot of the timeline', usage='timeline: a list of shots, each with id (string, unique), renderer ("cutout" | "manim" | "motion_graphics" | "whiteboard"), duration (seconds, float), camera, entities, actions, dialogue, narration, transition, sounds', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.camera', kind='field', version='1', name='shot.camera', title='', description="the shot's camera", usage='camera: {move: <a camera move>, ...} or explicit {keys: [...]}', params={}, examples=(), requires=(), levels=frozenset({'b-name', 'a'}), aspects=()), Entry(id='field.shot.entities', kind='field', version='1', name='shot.entities', title='', description='who and what is on stage', usage='entities: list of {kind, id, store, ref, ...}; kind MUST be a registered entity kind. A prop needs a PropDescriptor in the props store; it has no placeholder rig, so an unknown ref raises rather than drawing a person.', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.actions', kind='field', version='1', name='shot.actions', title='', description="the shot's animation", usage='actions: list of action dicts whose kind is a registered action kind (the composites sequence, parallel, delay and loop hold children).', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.actions.property', kind='field', version='1', name='shot.actions.property', title='', description='what a set or tween animates', usage="A tween/set action's property is EITHER a transform: alpha, dash_offset, pivot_x, pivot_y, rotation, rotation_rad, scale_x, scale_y, skew_x, skew_y, trim_end, trim_start, x, y — OR 'tint', a per-node colour MULTIPLY whose value is a '#rrggbb' string (the compiler expands it into three numeric channels, so a tween between two colours interpolates per channel; like 'alpha' it cascades to the target's parts). 'alpha' is the fade primitive and cascades to a character's parts. Any other property (opacity, visible, color, width, ...) is refused at compile. A tween with no 'from' starts at the property's rest value: 1.0 for scale_x / scale_y / alpha, '#ffffff' for tint, 0.0 for the rest. A tween with no 'easing' takes the scene's meta.default_easing when set.", params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.actions.easing', kind='field', version='1', name='shot.actions.easing', title='', description='how a tween moves through time', usage="A tween's easing is a registered easing name, a cubic-Bézier 4-list [cx1, cy1, cx2, cy2], or a parametrised curve such as 'cubic-bezier(…)' or 'steps(n)'.", params={}, examples=(), requires=(), levels=frozenset({'b-name', 'a'}), aspects=()), Entry(id='field.shot.dialogue', kind='field', version='1', name='shot.dialogue', title='', description='who says what, and when', usage="dialogue: list of {speaker, text, emotion, voice_ref, pause, at, direction, ...}. Lines play back to back from the shot start. 'pause' (seconds) is silence before a line, after the previous one ends — a beat, a look, a hesitation belongs here, NOT in a new shot. 'at' (seconds) starts a line at that shot time instead; a line takes one or the other, never both (to switch, delete the one you are replacing in the same patch list). 'start' and 'duration' are stamped by the audio pipeline from these on every render — never patch them.", params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.dialogue.direction', kind='field', version='1', name='shot.dialogue.direction', title='', description='how a line is delivered', usage="direction (optional) is a list of delivery cues — ['excited'], ['sighs', 'annoyed'] — that an expressive TTS voice performs; it is never spoken as text and never shown in captions.", params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.narration', kind='field', version='1', name='shot.narration', title='', description="a narrator's lines (not implemented)", usage='narration: list (same shape as dialogue, no speaker pin). NOT IMPLEMENTED — the audio pipeline walks dialogue only, and a shot with narration RAISES. To add a narrator, emit a dialogue line whose speaker is not an entity in the shot; it gets audio and no lip-sync.', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.transition', kind='field', version='1', name='shot.transition', title='', description='how a shot is entered', usage='transition (optional): how the shot is ENTERED — {kind: "cut" | "fade" | "dissolve", duration: seconds, color: \\'#rrggbb\\'}. Omitted = a hard cut. \\'fade\\' dips through color (half out of the previous shot, half into this one; on the first shot, a fade up). \\'dissolve\\' overlaps the two shots by duration, so the film gets that much shorter; never on the first shot. A shot must be long enough to hold its own transition and the next shot\\'s.', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.shot.sounds', kind='field', version='1', name='shot.sounds', title='', description="sound effects on the shot's clock", usage='sounds (optional): SFX cues in SHOT-local time — [{sound: <key in the sounds store>, at, [duration], [gain_db], [loop], [fade_in], [fade_out], [duck_db]}]. Never invent a sound key.', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.meta.sounds', kind='field', version='1', name='meta.sounds', title='', description="sounds on the film's clock (a music bed)", usage='meta.sounds (optional): the same cue shape in FILM time — a music bed is {sound: <key>, loop: true, duck_db: -12, fade_in, fade_out}; duck_db ducks it under every dialogue line.', params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()), Entry(id='field.meta.captions', kind='field', version='1', name='meta.captions', title='', description='captions derived from the dialogue', usage="meta.captions (optional): captions built at render time from the dialogue's word timings — {} for the defaults, or {highlight: '#rrggbb', color, size, anchor, max_chars, max_lines, burn, sidecar, strict}. Never add caption text entities by hand: they are derived from the dialogue.", params={}, examples=(), requires=(), levels=frozenset({'a'}), aspects=()))*

the core).

* **Type:**
  The core’s IR-field entries, registered on import (owner

### an.semantic.seeds.schema_of_callable(fn, , skip=(), positional=False)

A JSON Schema object for `fn`’s keyword parameters, defaults included.

Positional-only and `skip``ped parameters are left out (``target`,
`rest`, `parts` are the compiler’s, not the author’s).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> def f(target, *, height: float = 30.0, label: str = "x", n: int | None = None): ...
>>> schema_of_callable(f, skip=("target",))["properties"]["height"]
{'type': 'number', 'default': 30.0}
```
