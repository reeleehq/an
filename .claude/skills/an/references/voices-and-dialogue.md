# Voices and dialogue

Reference for the `an` skill (`../SKILL.md`: the index and the essentials).

### Voices

One voice document per character, each bound from its descriptor; the pitch is an effect on the voice, and `voice_id` picks the provider's voice (here macOS `say` voices, for `an render --tts mac_say`; under the default offline TTS they are silent but still distinct keys):

```python
from cutan.characters import new_character

ch = root / "assets" / "characters"
new_character(ch, name="carl", use_dicebear=False, voice_ref="carl_voice")
new_character(ch, name="ned", use_dicebear=False, voice_ref="ned_voice")
mall["voices"]["carl_voice"] = {"voice_id": "Junior", "effects": {"pitch_semitones": 5}}
mall["voices"]["ned_voice"] = {"voice_id": "Ralph", "effects": {"pitch_semitones": 2}}
```

Then `carl: Hi!` and `ned: Bye.` in a ```` ```dialogue ```` block speak in two voices at two pitches. For one shot only, an entity's `overrides: {voice_ref: ned_whisper}` re-voices it.

#### Expressive ElevenLabs voices

For real, acted speech declare `provider: elevenlabs` in the voice document, and a plain `an render` speaks it with ElevenLabs (needs `ELEVEN_API_KEY` or `ELEVENLABS_API_KEY` and `pip install elevenlabs`; the cost is printed before the first request; `--tts offline` previews it silently and for free). Browse voices with `an voices list --provider elevenlabs [--search british]` (Python: `an.audio.cli.browse_voices("elevenlabs", search=...)`); the first column is the `voice_id`. A voice document for ElevenLabs may declare (an#209):

- `provider: elevenlabs` — who speaks the voice under a plain `an render`, and the scope of the keys below (an `--tts offline` or `--tts mac_say` preview then speaks in its own default voice, and the render says so);
- `voice_id` — from `an voices list`;
- `model_id` — `eleven_v3` (or `eleven_v4`, `eleven_v4_turbo`, `eleven_v3_conversational`) is the expressive family and the only one that performs audio tags; `eleven_multilingual_v2` is steady and takes `style`; the default when unset is `eleven_turbo_v2_5` (fast, flat);
- `voice_settings` — any of `stability` (0–1; lower = more emotional range, v3 reads only 0.0 "Creative", 0.5 "Natural" and 1.0 "Robust", rounding anything else to the nearest), `similarity_boost` (0–1), `style` (0–1, multilingual_v2), `use_speaker_boost` (bool), `speed` (0.7–1.2); an unknown key or out-of-range value is an `an validate` error;
- `seed` — a non-negative int for more repeatable re-synthesis (`eleven_v3` does not honour it: identical requests return different takes);
- `effects: {tempo: 1.1}` — the speaking rate, since `eleven_v3` ignores `speed` (see *Voice effects* above); measure a plain line with `python -m an.verify.prosody` and set tempo = target rate / measured rate;
- `effects: {trim_silence: true}` — cut the breath and room tone `eleven_v3` pads each line with (see *Voice effects*); a style that keeps its performers' breaths uses `{threshold_db: -45}` (OverSimplified's roles);
- `takes` — best-of-N takes (an#265, `an.audio.takes`): `{n: 3, targets: {articulation_rate_sps: [5.2, 6.3], f0_sd_st: [3.9, 5.2], ...}}` synthesizes each line `n` times, measures every take with `an.verify.prosody` on the audio heard (the tempo included) and keeps the one closest to the `[low, high]` targets; `cues: {deadpan: {n: 3, targets: {...}}}` re-rolls only the lines carrying that `{cue}`, scored against their own targets (`reference_hz` adds the voice's neutral pitch for a `register_st` target). Each take has its own audio key and the line keeps the chosen take's, so its mouth, word timings and captions are aligned on that take. The choice is recorded in `mall["takes"]` (`artifacts/takes/`: the kept take, its sha256, every take's score, the scorer and its version) and the record is what every render reads: the recorded take is restored, never re-billed; a hand edit of its `chosen` wins (logged in the decisions); a newer scorer version KEEPS the recorded take and the render says so (prosody scorer 2 scores a line under 4 syllables, such as "Hi!", only on what it can show — no pause or rate targets, listed as `not_applicable` in the record; picks made before it are kept, and only short lines are reported); a recorded take whose audio is gone stops the render before any request. Replacing a take is explicit: `an voices rescore <dir> "<words of the line>"` re-chooses from the cached takes (nothing billed), `an voices reroll <dir> "<words>"` synthesizes a new roll (billed); the next `an render` does it. Changing `n` or the targets is a new choice, made from the takes already cached; changing only the voice's effects (a `tempo`, a `trim_silence`) KEEPS the recorded take — re-processed from its raw audio, not re-scored, and the render says so — until you `an voices rescore` it. `n` defaults to 1 (one take, every key unchanged); each take is a billed request, take 0 is the single take a line already has, and the render prints the requests and billed characters before the first one. A style names its targets by role: build the voice document with `an.audio.takes.style_voice_role(spec, role)` (the `an-style` skill, step 8c).

On an audio-tag model a line's `[emotion]` (except `neutral`) and its `{direction}` cues are sent as inline tags — `laura [happy] {excited}: Hi!` is spoken as `[happy] [excited] Hi!`. Any cue works (`sighs`, `whispers`, `laughs`, `clears throat`, `sarcastic`, `deadpan`). Tags never enter `text`, so captions, `.srt` and lip-sync alignment see only the words. On a non-tag model a `{direction}` is dropped with a warning (`an validate` says so) and `[emotion]` stays a face-only cue. The audio cache key includes model, settings, seed and tags, so changing any of them re-synthesizes that line only; a voice declaring none of them keeps every key it had.

Two characters — an eager one and a flat, annoyed one:

```python
new_character(ch, name="laura", use_dicebear=False, voice_ref="laura_voice")
new_character(ch, name="callum", use_dicebear=False, voice_ref="callum_voice")
mall["voices"]["laura_voice"] = {
    "provider": "elevenlabs",
    "voice_id": "FGY2WhTYpPnrIDTdsKH5",  # Laura — enthusiast, quirky
    "model_id": "eleven_v3",
    "voice_settings": {"stability": 0.0},  # Creative: big swings
    "effects": {"trim_silence": True},  # start on the word, not on a breath (an#254)
}
mall["voices"]["callum_voice"] = {
    "provider": "elevenlabs",
    "voice_id": "N2lVS1w4EtoT3dr4eOWO",  # Callum — husky trickster
    "model_id": "eleven_v3",
    "voice_settings": {"stability": 0.5, "speed": 0.95},
    "effects": {"trim_silence": True},
}
```

```dialogue
laura [happy] {excited}: Oh my gosh, we are finally going to the fair!
callum {sighs, annoyed}: Great. Crowds. My favourite.
```

then `an render <dir> --lipsync whisper` (the voices name ElevenLabs; `--tts elevenlabs` would also speak voices that name no provider). Voice ids are account-visible voices at the time of writing — pick your own with `an voices list`. Each line is one billed request (`n` with `takes`), cached by content, so re-rendering an unchanged line costs nothing.

### Dialogue timing

- A shot's lines play **back to back from the shot start** unless a line says otherwise. **A beat is a pause, not a shot**: `maya (pause 1.5): Bye.` holds 1.5 s of silence after the previous line's SPEECH ends (the provider's own trailing silence is not counted, an#397), and every later line moves with it; `maya (at 3.0): Bye.` starts the line at 3.0 s into the shot, and the next line follows it. One line takes one or the other. The audio, the mouth, captions and music ducking all follow, and a reaction during the pause is an ordinary action with a `start` (an `expression` with `axes: {gaze_x: …}` for a look, a `play` of `nod`). Splitting a line into its own shot just to get a pause adds cuts a style did not ask for.
- The audio pipeline stamps `start` and `duration` into `ir/scene.json`; `start` is **re-derived from `pause`/`at` on every render and preview** (`an.audio.pipeline.retime_dialogue`), so editing a pause re-times the shot without re-synthesizing anything. Never set `start` yourself — write `pause` or `at` (in `an iterate`, patch `timeline/N/dialogue/K/pause`).
- **A recipe for "X says hi. Y pauses, looks at X, says bye."** — one shot, sized to hold the lines plus the pause:

  ```dialogue
  stan: Hi, Kyle.
  kyle (pause 1.5): Bye.
  ```
  with `{kind: expression, target: kyle, preset: skeptical, axes: {gaze_x: -1.0}, start: 0.7, duration: 1.5}` in ` ```yaml actions ` for the look (gaze toward a character on the left is negative).
- The offline voice is **silent** and lasts 0.05 s + 0.06 s per non-space character, at least 0.4 s (`an.audio.offline_tts.estimate_speech_duration(text)`), so you can size shots before rendering. A real voice (`--tts elevenlabs`, or `--tts mac_say` — a free local voice on macOS) is usually a little slower.
- The shot's audio stops at the shot end. `an validate` warns when a line would run past it — pauses and `at`s included: from the estimate before any synthesis, from the real timing after a render — and `an render` itself reports it (and a line heard during a dissolve) the moment the real timing is known, in its findings summary. A real voice pads its lines with silence: `effects: {trim_silence: true}` on the voice trims it (*Voice effects*). It also warns when an `at` makes a speaker start a line before their previous one ends (two speakers talking over each other is fine).
- There is no narrator track (`Shot.narration` raises). A narrator is a dialogue line whose speaker is not an entity in the shot — audio, no lip-sync, and a warning saying so. A shot with no dialogue is silent unless a `sounds` cue plays.
