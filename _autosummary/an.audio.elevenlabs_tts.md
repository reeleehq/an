# an.audio.elevenlabs_tts

ElevenLabsTTS — real speech via the ElevenLabs API. Requires ELEVEN_API_KEY.

Lazily imports the elevenlabs SDK so the rest of `an` works without it.
If you want real speech, `pip install elevenlabs` and set
`ELEVEN_API_KEY` (or `ELEVENLABS_API_KEY`) in your environment.

**Expressive voices (an#209).** A voice document in the `voices` store may
declare, beside `voice_id`, the `model_id` it speaks with, its
`voice_settings` and a sampling `seed`; a dialogue line’s `[emotion]` and
`{direction}` reach a model that takes inline audio tags (`eleven_v3`,
`eleven_v4` and their variants) as `[excited] Hi!`.
[`ElevenLabsTTS.synthesis_options()`](#an.audio.elevenlabs_tts.ElevenLabsTTS.synthesis_options) turns those into the keyword arguments
[`ElevenLabsTTS.synthesize()`](#an.audio.elevenlabs_tts.ElevenLabsTTS.synthesize) takes — the audio pipeline keys its cache on
exactly that dict, and a voice declaring none of them yields `{}`, so no
existing cache key moves.

```pycon
>>> tts = ElevenLabsTTS(api_key="unused")
>>> tts.synthesis_options({})
{}
>>> tts.synthesis_options({"model_id": "eleven_v3"}, emotion="happy", direction=["sighs"])
{'model_id': 'eleven_v3', 'audio_tags': ['happy', 'sighs']}
>>> tts.synthesis_options({"voice_settings": {"stability": 0.3, "speed": 1.1}})
{'voice_settings': {'speed': 1.1, 'stability': 0.3}}
>>> tagged_text("Hi!", ["excited"])
'[excited] Hi!'
```

### Module Attributes

| [`AUDIO_TAG_MODEL_PREFIXES`](#an.audio.elevenlabs_tts.AUDIO_TAG_MODEL_PREFIXES)   | Model ids that read inline audio tags (`[excited]`, `[sighs]`).                            |
|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| [`VOICE_SETTINGS_RANGES`](#an.audio.elevenlabs_tts.VOICE_SETTINGS_RANGES)      | The `voice_settings` keys the API takes, with the range each accepts (`None` = a boolean). |

### Functions

| [`normalize_voice_settings`](#an.audio.elevenlabs_tts.normalize_voice_settings)(raw)              | The canonical `voice_settings` dict — only what was declared, key-sorted.   |
|---------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`tagged_text`](#an.audio.elevenlabs_tts.tagged_text)(text, tags)                    | `text` with each tag prefixed as `[tag]` — what an audio-tag model reads.   |
| [`takes_audio_tags`](#an.audio.elevenlabs_tts.takes_audio_tags)(model_id, \*[, prefixes]) | Whether `model_id` reads inline audio tags.                                 |

### Classes

| [`ElevenLabsTTS`](#an.audio.elevenlabs_tts.ElevenLabsTTS)(\*[, api_key, model_id, ...])   | ElevenLabs-backed TTSProvider.   |
|------------------------------------------------------------------------------------------------|----------------------------------|

### Exceptions

| [`ElevenLabsVoiceError`](#an.audio.elevenlabs_tts.ElevenLabsVoiceError)   | A voice document declares ElevenLabs settings that are malformed.   |
|-------------------------------------------------------------------------|---------------------------------------------------------------------|

### an.audio.elevenlabs_tts.AUDIO_TAG_MODEL_PREFIXES *: tuple[str, ...]* *= ('eleven_v3', 'eleven_v4')*

Model ids that read inline audio tags (`[excited]`, `[sighs]`). Matched
as prefixes, so `eleven_v3_conversational` and `eleven_v4_turbo` count.
Every other model would speak the brackets, so it never receives a tag.

### *class* an.audio.elevenlabs_tts.ElevenLabsTTS(, api_key=None, model_id='eleven_turbo_v2_5', output_format='mp3_44100_128', audio_tag_model_prefixes=('eleven_v3', 'eleven_v4'), client_factory=None)

Bases: `object`

ElevenLabs-backed TTSProvider. Constructor takes an optional api_key
(falls back to `ELEVEN_API_KEY` / `ELEVENLABS_API_KEY`).

Implements the `TTSProvider` protocol, plus the optional
`synthesis_options` hook the audio pipeline reads (an#209).

#### client_factory

`api_key -> client`; tests inject a fake so nothing reaches the API.

#### list_voices(, search=None)

The account’s voices (its own plus the ones it saved), newest API.

`search` filters by name, description and labels on the server. An
absent key or SDK yields `[]`; a key that is present and a call that
fails RAISES — an empty listing must mean “no voices”, not “it broke”.

* **Return type:**
  `Iterable`[[`VoiceMeta`](an.audio.tts.md#an.audio.tts.VoiceMeta)]

#### synthesis_options(voice, , emotion=None, direction=None)

The `synthesize` keyword arguments a voice document and a line imply.

Only what is declared appears (`{}` for a plain voice), so the audio
cache key — which includes this dict when it is non-empty — is unchanged
for every voice that declares nothing new. `audio_tags` are the line’s
`[emotion]` (unless `neutral`) then its `direction` cues, and only
on a model that reads tags; elsewhere a direction is dropped with a
warning and the emotion stays a face-only cue, as before.

* **Return type:**
  `dict`[`str`, `Any`]

#### synthesize(text, voice_id=None, , model_id=None, voice_settings=None, seed=None, audio_tags=None, \*\*kw)

Speak `text`. The clip’s `transcript` is `text` WITHOUT the tags,
so alignment and captions never read a cue.

* **Return type:**
  [`AudioClip`](an.audio.tts.md#an.audio.tts.AudioClip)

### *exception* an.audio.elevenlabs_tts.ElevenLabsVoiceError

Bases: `ValueError`

A voice document declares ElevenLabs settings that are malformed.

### an.audio.elevenlabs_tts.VOICE_SETTINGS_RANGES *: dict[str, tuple[float, float] | None]* *= {'similarity_boost': (0.0, 1.0), 'speed': (0.7, 1.2), 'stability': (0.0, 1.0), 'style': (0.0, 1.0), 'use_speaker_boost': None}*

The `voice_settings` keys the API takes, with the range each accepts
(`None` = a boolean). `speed` is the API’s documented 0.7–1.2.

### an.audio.elevenlabs_tts.normalize_voice_settings(raw)

The canonical `voice_settings` dict — only what was declared, key-sorted.

Omit-when-unset: `None` and `{}` give `{}`. Unknown keys and values out
of range raise, so a typo cannot silently fall back to the account default.

* **Return type:**
  `dict`[`str`, `Any`]

```pycon
>>> normalize_voice_settings({"style": 1, "stability": 0.25})
{'stability': 0.25, 'style': 1.0}
>>> normalize_voice_settings({"stabilty": 0.5})
Traceback (most recent call last):
    ...
an.audio.elevenlabs_tts.ElevenLabsVoiceError: unknown voice_settings key(s) ['stabilty']; known: ['similarity_boost', 'speed', 'stability', 'style', 'use_speaker_boost']
```

### an.audio.elevenlabs_tts.tagged_text(text, tags)

`text` with each tag prefixed as `[tag]` — what an audio-tag model reads.

* **Return type:**
  `str`

### an.audio.elevenlabs_tts.takes_audio_tags(model_id, , prefixes=('eleven_v3', 'eleven_v4'))

Whether `model_id` reads inline audio tags.

* **Return type:**
  `bool`

```pycon
>>> takes_audio_tags("eleven_v3"), takes_audio_tags("eleven_turbo_v2_5")
(True, False)
```
