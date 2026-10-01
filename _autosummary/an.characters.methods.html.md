# an.characters.methods

The cut-out genre’s methods and aspects, and their compile-time resolution (ADR 0002).

The first two aspects of ADR 0002’s first slice, as registry data:

| aspect     | method (spelled)                     | requires     | chain      |
|------------|--------------------------------------|--------------|------------|
| locomotion | `loco.legged_cycle` (`legs`)         | `limbs.legs` | 1st        |
| locomotion | `loco.hem_sway` (`hem`)              | `limbs.legs` | by request |
| locomotion | `loco.rock` (`rock`)                 | nothing      | last link  |
| speech     | `speech.mouth_chart` (`mouth_chart`) | `face.mouth` | 1st        |
| speech     | `speech.pose_only` (`pulse`)         | nothing      | last link  |

**Locomotion is today’s walk/gait chain, moved, not changed** (ADR 0002
decision 8: the gate is byte-identical output). A walk’s `gait` arg is the
author’s request, the descriptor’s `gait` a declared override (reported as
such); with neither, the chain picks `legs` when the character affords a leg
pair and `rock` when it does not — exactly what [`an.motion.walk()`](an.motion.html.md#an.motion.walk) did on
its own. What is new is that the choice is the registry’s, made once, and a
requested gait the rig cannot honour (`hem` on a legless blob) is a
**recorded substitution**: a warning, fatal under `--strict-assets`.

**Speech gains a requirement-free last link.** A character whose face is baked
into its art (`face_overlay: false`) used to speak with a frozen mouth; it now
pulses its head on each syllable (`an.motion.speech_pulse()`, parametrised:
`strength`, `part`, `attack`, `release`; `strength: 0` is a mime).

The asset profile the compiler resolves against is the character analyser’s
(`an.capabilities.affordances`), fed what the compiler actually has: the
descriptor and the art its store holds, or — for a rig drawn from `parts` or
the placeholder — the parts the builder built. Characters only: other entity
kinds have no analyser yet, and keep the preset’s own rig lookup.

Importing this module registers nothing: `an.genres.cutout.CUTOUT` lists
[`CUTOUT_METHODS`](#an.characters.methods.CUTOUT_METHODS) and [`CUTOUT_ASPECTS`](#an.characters.methods.CUTOUT_ASPECTS).

### Module Attributes

| [`LOCOMOTION`](#an.characters.methods.LOCOMOTION)     | The aspect names (persisted in substitution records).       |
|-----------------------------------------------------------------|-------------------------------------------------------------|
| [`CUTOUT_METHODS`](#an.characters.methods.CUTOUT_METHODS) | The genre's methods, as vocabulary entries (kind `method`). |
| [`CUTOUT_ASPECTS`](#an.characters.methods.CUTOUT_ASPECTS) | each chain ends in a method that requires nothing.          |

### Functions

| [`check_declared_speech`](#an.characters.methods.check_declared_speech)(ctx)                         | The cut-out genre's semantic check: each character's declared `speech` resolves.                                             |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| [`compile_profile`](#an.characters.methods.compile_profile)(descriptor, \*[, ...])             | The character's profile, from what the compiler has: the analyser, fed honestly.                                             |
| [`speech_problems`](#an.characters.methods.speech_problems)(declared)                          | Why a character's declared `speech` cannot be honoured (empty: it can).                                                      |
| [`normalise_gait_args`](#an.characters.methods.normalise_gait_args)(args)                          | A walk's args with `gait` as the walk spells it (`legs`/`hem`/`rock`).                                                       |
| [`resolve_walk_gait`](#an.characters.methods.resolve_walk_gait)(entity, \*, args, ...[, policy]) | `(gait, resolution)` of a walk on `entity`: the locomotion method's spelling.                                                |
| [`speech_plan`](#an.characters.methods.speech_plan)(shot, \*, is_character, profile_of)    | Resolve the speech aspect ONCE per speaking character, and say what it adds.                                                 |
| [`substitution_record`](#an.characters.methods.substitution_record)(sub, \*[, entity_ref])         | A [`Substitution`](an.capabilities.html.md#an.capabilities.Substitution) as an `asset_resolution` entry. |
| [`syllable_beats`](#an.characters.methods.syllable_beats)(line, \*[, min_gap_s])              | Syllable onsets of a dialogue line, in seconds from its start.                                                               |

### Classes

| [`SpeechPlan`](#an.characters.methods.SpeechPlan)([actions, no_lip_sync])   | What the speech aspect decided for a shot: the actions it adds, and the speakers whose lip-sync it switched off (the viseme pass skips them).   |
|---------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|

### an.characters.methods.CUTOUT_ASPECTS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Aspect](an.semantic.html.md#an.semantic.Aspect), ...]* *= (Aspect(name='locomotion', chain=('loco.legged_cycle', 'loco.rock'), applies_to=frozenset(), description='how a character travels when it walks.', declared_by='gait', records_fallback=False), Aspect(name='speech', chain=('speech.mouth_chart', 'speech.pose_only'), applies_to=frozenset(), description='how a character shows that it is speaking.', declared_by='speech', records_fallback=True))*

each chain ends in a method that requires nothing.

* **Type:**
  The genre’s aspects

### an.characters.methods.CUTOUT_METHODS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Method](an.semantic.html.md#an.semantic.Method), ...]* *= (Method(id='loco.legged_cycle', kind='method', version='1', name='legs', title='legged walk cycle', description='a legged walk cycle: in profile the legs swing about the hip in opposition, facing the camera the stepping leg lifts; the arms swing against the legs', usage='', params={'type': 'object', 'properties': {'stride': {'type': 'number', 'default': 0.35}, 'lift': {'type': 'number', 'default': 10.0}, 'arm_swing': {'type': 'number', 'default': 0.3}, 'bob': {'type': 'number', 'default': 6.0}}}, examples=({'kind': 'play', 'target': 'ned', 'animation': 'walk', 'args': {'gait': 'legs'}},), requires=(Requirement(capability='limbs.legs', key=None, at_least=None, any_of=()),), levels=frozenset({'a', 'b-name'}), aspects=(), aspect='locomotion', remedies={'limbs.legs': 'split the legs into two slots named leg_l/leg_r, each with its art, pivoted at the hip (an-art-package skill; \`an character new\` builds them)'}), Method(id='loco.hem_sway', kind='method', version='1', name='hem', title='hem sway', description="a robe figure's walk: the leg slots are the two halves of the hem, which tilt in turn about the hip while the body sways and bobs", usage='', params={'type': 'object', 'properties': {'hem_tilt': {'type': 'number', 'default': 0.24}, 'rock': {'type': 'number', 'default': 0.06}, 'bob': {'type': 'number', 'default': 6.0}, 'stride': {'type': 'number', 'default': 0.35}, 'arm_swing': {'type': 'number', 'default': 0.3}}}, examples=({'kind': 'play', 'target': 'ned', 'animation': 'walk', 'args': {'gait': 'hem'}},), requires=(Requirement(capability='limbs.legs', key=None, at_least=None, any_of=()),), levels=frozenset({'a', 'b-name'}), aspects=(), aspect='locomotion', remedies={'limbs.legs': "carve the robe's hem into two halves on slots leg_l/leg_r, pivoted at the hip, and declare \`gait: hem\` in character.json"}), Method(id='loco.rock', kind='method', version='1', name='rock', title='rock and bob', description='no leg moves: the body rocks side to side and bobs once per step while it travels (a blob, a sack, anything drawable)', usage='', params={'type': 'object', 'properties': {'rock': {'type': 'number', 'default': 0.06}, 'bob': {'type': 'number', 'default': 6.0}, 'arm_swing': {'type': 'number', 'default': 0.3}}}, examples=({'kind': 'play', 'target': 'ned', 'animation': 'walk', 'args': {'gait': 'rock'}},), requires=(), levels=frozenset({'a', 'b-name'}), aspects=(), aspect='locomotion', remedies={}), Method(id='speech.mouth_chart', kind='method', version='1', name='mouth_chart', title='mouth chart lip-sync', description="lip-sync on the character's mouth chart: the line's visemes swap the mouth drawings (the nine Rhubarb shapes, or the character's own set)", usage='', params={}, examples=(), requires=(Requirement(capability='face.mouth', key=None, at_least=None, any_of=()),), levels=frozenset({'a', 'b-name'}), aspects=(), aspect='speech', remedies={'face.mouth': "give the character an overlay mouth: a \`mouth\` slot with the viseme set's drawings (\`an character mouths <dir>\`) and face_overlay: true"}), Method(id='speech.pose_only', kind='method', version='1', name='pulse', title='speech pulse', description='no lip-sync: the head (or the body) pulses on each syllable, so a baked face or a mime still reads as speaking', usage='', params={'type': 'object', 'properties': {'strength': {'type': 'number', 'default': 0.06}, 'part': {'type': 'string', 'default': 'head'}, 'attack': {'type': 'number', 'default': 0.06}, 'release': {'type': 'number', 'default': 0.1}}}, examples=('a character with face_overlay: false speaks',), requires=(), levels=frozenset({'a', 'b-name'}), aspects=(), aspect='speech', remedies={}))*

The genre’s methods, as vocabulary entries (kind `method`).

### an.characters.methods.LOCOMOTION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'locomotion'*

The aspect names (persisted in substitution records).

### *class* an.characters.methods.SpeechPlan(actions=(), no_lip_sync=frozenset({}))

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What the speech aspect decided for a shot: the actions it adds, and the
speakers whose lip-sync it switched off (the viseme pass skips them).

### an.characters.methods.check_declared_speech(ctx)

The cut-out genre’s semantic check: each character’s declared `speech` resolves.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.characters.methods.compile_profile(descriptor, , built_parts=(), art_exists=None)

The character’s profile, from what the compiler has: the analyser, fed honestly.

`descriptor` is the migrated `CharacterDescriptor` (or `None` for a
rig drawn from `parts` / the placeholder); `art_exists(rel_path)` the
store’s probe (`None`: the store cannot say, so every declared drawing
counts — the rig builder’s own rule); `built_parts` the part names the
builder built under the entity (for a non-descriptor rig, they ARE its
parts document).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.characters.methods.normalise_gait_args(args)

A walk’s args with `gait` as the walk spells it (`legs`/`hem`/`rock`).

`gait` may name a locomotion method by id (`loco.rock`) or be a choice
`{method, args, version}` — the level-(a) form, and how a scene pins a
method’s version (ADR 0003 decision 2). The choice’s `args` join the
walk’s (an explicit arg wins); a pin that no longer holds, or a method of
another aspect, raises [`VocabularyError`](an.semantic.html.md#an.semantic.VocabularyError).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> normalise_gait_args({"gait": {"method": "loco.legged_cycle", "args": {"stride": 0.5}, "version": "1"}})
{'stride': 0.5, 'gait': 'legs'}
>>> normalise_gait_args({"gait": "hem", "distance": 80})
{'gait': 'hem', 'distance': 80}
```

### an.characters.methods.resolve_walk_gait(entity, , args, descriptor, profile, policy=None)

`(gait, resolution)` of a walk on `entity`: the locomotion method’s spelling.

The request is the walk’s `gait` arg, else the descriptor’s declared
`gait` (an override of the derivation, and reported as one). An explicit
`legs` arg names the limbs itself: a non-empty pair affords legs whatever
the derivation says, `()` affords none.

```pycon
>>> gait, r = resolve_walk_gait("blob", args={"gait": "hem"}, descriptor=None, profile={})
>>> gait, r.substitution.reason, r.substitution.missing
('rock', 'missing', ('limbs.legs',))
```

### an.characters.methods.speech_plan(shot, \*, is_character, profile_of, descriptor_of=<function <lambda>>, has_part, record=None, policy=None)

Resolve the speech aspect ONCE per speaking character, and say what it adds.

The request is the character’s declared `speech` (a method spelling or a
`{method, args, version}` choice); `policy` is the shot/style policy.
The one resolution decides both halves: a speaker resolved to anything but
`speech.mouth_chart` gets no viseme channel (`SpeechPlan.no_lip_sync`),
and one resolved to `speech.pose_only` gets a `speech_pulse` play at each
syllable onset of each timed line — one play per syllable, each built at the
head’s pose at that instant, so it rides an authored head-scale tween rather
than overwriting it; a syllable that starts while the speaker’s previous pulse
is still running is skipped, so the head always settles back. `strength: 0`
is a mime: no pulse at all. An authored `play: speech_pulse` on the speaker
replaces the automatic pulses (nothing is added beside it), but it is not a
declaration: the fall from the mouth chart is still recorded, and only a
declared `speech` makes it the request. Substitutions (a declared method
the rig cannot honour; the fall from the mouth chart to the pulse) go to
`record`, once per speaker. A declared `speech` naming no method of the
aspect, or pinned to a stale version, raises
[`VocabularyError`](an.semantic.html.md#an.semantic.VocabularyError) naming the aspect’s methods
([`speech_problems()`](#an.characters.methods.speech_problems) is `an validate`’s side of it).

* **Return type:**
  [`SpeechPlan`](#an.characters.methods.SpeechPlan)

### an.characters.methods.speech_problems(declared)

Why a character’s declared `speech` cannot be honoured (empty: it can).

An unknown method, a method of another aspect, or a pin to a version the
registry no longer has; the message names the speech methods.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> speech_problems("pulse"), speech_problems(None)
([], [])
>>> speech_problems("flap")[0].startswith("speech 'flap'")
True
```

### an.characters.methods.substitution_record(sub, , entity_ref=None)

A [`Substitution`](an.capabilities.html.md#an.capabilities.Substitution) as an `asset_resolution` entry.

The compiled document’s record generalised (ADR 0002 decision 6):
`kind: method`, `store` the aspect, `ref` what was asked for,
`resolved` what was used, `fallback` whether `--strict-assets` makes
it fatal.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.characters.methods.syllable_beats(line, , min_gap_s=0.18)

Syllable onsets of a dialogue line, in seconds from its start.

From the line’s viseme track (a syllable starts where the mouth opens out
of a closed shape), else its word timings (one beat per word), else one
beat at its start. Beats closer than `min_gap_s` merge.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]
