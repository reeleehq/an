# an.audio.voices

Which voice speaks a dialogue line: the character → voice binding (an#194).

A line resolves its voice — a key of the project’s `voices` store — in this
order, first hit wins:

1. the line’s own `voice_ref` (set from Python or `ir/scene.json`);
2. the speaking character’s `voice_ref`: the shot entity whose `id` is the
   line’s `speaker`, read from its descriptor in the `characters` store with
   the entity’s `overrides` merged over it (so `overrides: {voice_ref: x}`
   on the entity re-voices it for one shot);
3. [`DEFAULT_VOICE`](#an.audio.voices.DEFAULT_VOICE).

A voice document may name the TTS provider’s own voice with `voice_id` (a
`say -v` name for `mac_say`, a voice id for ElevenLabs); the provider is
handed that, and otherwise the store key itself. A document that declares
`provider` scopes its provider-specific keys (`voice_id`, and the
`model_id` / `voice_settings` / `seed` ElevenLabs reads — an#209) to that
provider: rendered with another one, the line is handed `"default"`, so an
ElevenLabs-voiced project previews with `mac_say` or `offline` instead of
failing on a foreign voice id. Nothing declared anywhere
resolves every line to `"default"` handed to the provider as `"default"` —
exactly what the pipeline did before this module, so no cache key moves.

```pycon
>>> from an.ir.schema import AssetRef, Dialogue, Shot
>>> shot = Shot(id="s", entities=[
...     AssetRef(kind="character", id="carl", store="characters", ref="carl"),
...     AssetRef(kind="character", id="ned", store="characters", ref="ned",
...              overrides={"voice_ref": "ned_sad"})])
>>> mall = {"characters": {"carl": {"voice_ref": "carl_kid"}, "ned": {"voice_ref": "ned_kid"}},
...         "voices": {"carl_kid": {"voice_id": "Junior"}}}
>>> [line_voice_id(Dialogue(speaker=s, text="hi"), shot, mall) for s in ("carl", "ned", "narrator")]
['carl_kid', 'ned_sad', 'default']
>>> line_voice_id(Dialogue(speaker="carl", text="hi", voice_ref="own"), shot, mall)
'own'
>>> provider_voice(mall, "carl_kid"), provider_voice(mall, "default")
('Junior', None)
>>> mall["voices"]["bob"] = {"provider": "elevenlabs", "voice_id": "abc123"}
>>> provider_voice(mall, "bob", tts_name="elevenlabs"), provider_voice(mall, "bob", tts_name="mac_say")
('abc123', 'default')
```

### Module Attributes

| [`DEFAULT_VOICE`](#an.audio.voices.DEFAULT_VOICE)       | The voice a line gets when neither it nor its speaker names one.                                                     |
|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| [`PROVIDER_VOICE_KEY`](#an.audio.voices.PROVIDER_VOICE_KEY)  | The key, in a voice document, naming the TTS provider's own voice.                                                   |
| [`PROVIDER_KEY`](#an.audio.voices.PROVIDER_KEY)        | The key, in a voice document, naming the TTS provider it is written for.                                             |
| [`CHARACTER_VOICE_KEY`](#an.audio.voices.CHARACTER_VOICE_KEY) | The key, in a character descriptor (or an entity's `overrides`), naming the character's voice in the `voices` store. |

### Functions

| [`line_voice_id`](#an.audio.voices.line_voice_id)(line, shot, mall, \*[, default])   | The `voices`-store key `line` is spoken with (see the module doc).     |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`provider_voice`](#an.audio.voices.provider_voice)(mall, voice_id, \*[, tts_name])   | The provider voice `mall["voices"][voice_id]` names, or `None`.        |
| [`speaker_voice_ref`](#an.audio.voices.speaker_voice_ref)(speaker, shot, mall)           | The voice the speaking character is bound to in `shot`, or `None`.     |
| [`voice_applies`](#an.audio.voices.voice_applies)(doc, tts_name)                     | Whether `doc`'s provider-specific keys apply under the TTS `tts_name`. |
| [`voice_document`](#an.audio.voices.voice_document)(mall, voice_id)                   | `mall["voices"][voice_id]` when it is a mapping, else `{}`.            |

### an.audio.voices.CHARACTER_VOICE_KEY *: str* *= 'voice_ref'*

The key, in a character descriptor (or an entity’s `overrides`), naming
the character’s voice in the `voices` store.

### an.audio.voices.DEFAULT_VOICE *: str* *= 'default'*

The voice a line gets when neither it nor its speaker names one.

### an.audio.voices.PROVIDER_KEY *: str* *= 'provider'*

The key, in a voice document, naming the TTS provider it is written for.

### an.audio.voices.PROVIDER_VOICE_KEY *: str* *= 'voice_id'*

The key, in a voice document, naming the TTS provider’s own voice.

### an.audio.voices.line_voice_id(line, shot, mall, , default='default')

The `voices`-store key `line` is spoken with (see the module doc).

* **Return type:**
  `str`

### an.audio.voices.provider_voice(mall, voice_id, , tts_name=None)

The provider voice `mall["voices"][voice_id]` names, or `None`.

`None` means “hand the provider `voice_id` itself” — a voice that is not
in the store, a document without `voice_id`, or one whose `voice_id` is
its own key (which changes nothing, so it must not move a cache key).
Given `tts_name`, a document written for ANOTHER provider gives
[`DEFAULT_VOICE`](#an.audio.voices.DEFAULT_VOICE) — never a foreign voice id (an#209).

* **Return type:**
  `str` | `None`

### an.audio.voices.speaker_voice_ref(speaker, shot, mall)

The voice the speaking character is bound to in `shot`, or `None`.

`None` when no character entity of the shot has the speaker’s id (an
off-screen narrator), or when neither its descriptor nor its `overrides`
name a voice. A store that is absent, or that does not hold the ref, still
lets the entity’s `overrides` speak.

* **Return type:**
  `str` | `None`

### an.audio.voices.voice_applies(doc, tts_name)

Whether `doc`’s provider-specific keys apply under the TTS `tts_name`.

True when the document names no `provider`, or names this one (case
ignored), or when the caller does not say which provider is speaking.

* **Return type:**
  `bool`

```pycon
>>> voice_applies({}, "offline"), voice_applies({"provider": "ElevenLabs"}, "elevenlabs")
(True, True)
>>> voice_applies({"provider": "elevenlabs"}, "offline")
False
```

### an.audio.voices.voice_document(mall, voice_id)

`mall["voices"][voice_id]` when it is a mapping, else `{}`.

* **Return type:**
  `Mapping`
