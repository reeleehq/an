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

#### Casting a voice from its notes (voice design)

When the writer describes a voice in words instead of naming one, put the words in the voice document as `notes` (age, accent, pitch, pace, attitude; 20–1000 characters) and, optionally, `sample_text` (else the voice's own lines are the sample):

```json
{"provider": "elevenlabs", "model_id": "eleven_v3",
 "notes": "A man in his early fifties from rural County Limerick, warm, unhurried, a soft Munster lilt."}
```

Then `an voices design <dir>` (billed: ElevenLabs Voice Design) writes options with samples to `artifacts/voice_samples/<ref>_<A|B|C>.mp3` and the manifest to `artifacts/voice_options/<ref>.json`; play them to the writer; `an voices choose <dir> <ref> B --by "<the writer's name>"` makes the pick the document's `voice_id` and records `chosen_by` / `chosen_at`.

**When the accent is the character, design from notes is not enough** (an#485: every design of "rural Limerick Irish" came out English). Two more routes, in the same manifest:

- **Library candidates by accent.** Put a `library` query on the voice document — `"library": {"accent": "irish", "gender": "male", "age": "middle_aged"}` (filters: `accent`, `gender`, `age`, `language`, `search`) — or pass one to every voice with `an voices design <dir> --library accent=irish,gender=male`; `--no-design` skips the billed designs (a library search and its previews are free). The shared library's voices are human-tagged, often with a region in the description ("Cork", "west of Ireland"): they appear as options `L1`, `L2`, … with their descriptions, and `an voices choose <dir> <ref> L2 --by …` picks one like any other.
- **An audition reel per option.** `an voices audition <dir> [--voices jerry_voice] [--options A,L1,L2]` speaks the character's own lines from the scene in each option's voice, with the film's TTS model, the document's `voice_settings` and `effects` (tempo, pitch, trim) and the lines' `[emotion]`/`{cue}` tags, 0.6 s apart, to `artifacts/voice_auditions/<ref>_<option>.wav` — what the film will sound like, accent drift of the render model included (only `takes` are not applied: one take per line). Billed: one request per line per option; every reel is checked before the first request and the whole bill is printed first; a reel already made for the same lines, voice and settings is never made again (`--redo` forces it). Audition a shortlist, not every candidate.

An accent classifier cannot do the screening (measured: a public accent-ID model gives human-tagged Irish voices a 6–25 % chance of being Irish): play the reels to the writer, whose ear is the judge.

**A voice with `notes` is cast only by a recorded choice** (an#486). Until then a plain `an render` speaks it and reports it (*voices written in words that nobody chose*), and `an render --strict-assets` refuses it before any request — the render stops and asks rather than guess a voice someone other than the writer picked. `an validate` only notes it (an info line), strict or not: a production pack is checked while its voices are still words, and that is the right state for a pack. Pass `--by` with the writer's name: the default is your login name, which only records that someone ran the command. A voice the writer picked by hand (from `an voices list`, or already in the document) is recorded the same way, with no design round and nothing billed: `an voices cast <dir> <ref> [<voice_id>] --by "<writer>"`. For a timing draft before the writer has chosen, set `"provisional": "round-2 timing draft"` (any truthy value; a string says why) beside a `voice_id` on the voice document: the render speaks it and lists it as provisional in its findings and `an validate`; `an voices choose`/`cast` removes the mark. A document without `notes` names its voice by hand and is not judged. Under `--strict-assets` the provider check comes first: `--tts offline` on an ElevenLabs voice is refused as a stand-in before the choice is looked at, so a strict timing draft needs `provisional`, not `--tts offline`.

#### Recorded voices

When the performers are recorded, the recording is the voice (an#490) — nothing is synthesized or billed for those lines:

```
an voices import <dir> takes/ --transcript takes/ --license cc-by-4.0 --recorded-by "J. Doe"
an voices import <dir> carl.wav --transcript carl.srt --speaker carl --license all-rights-reserved
an voices import <dir> session.m4a --denoise --speakers spk_0=carl,spk_1=ned --license cc0-1.0 --diarize
```

- **The audio**: one take holding several lines, or one file per line (`carl-01.wav`: the stem names the speaker); a directory or a glob imports many. Anything ffmpeg decodes; a 16-bit PCM WAV is kept as it is. `--denoise` cleans it first (ffmpeg `afftdn`).
- **The transcript**: an SRT, WebVTT, TextGrid or word-timed JSON times the lines (nothing is transcribed; a JSON's or TextGrid's words become the line's word timings); a plain `speaker: text` file pairs one line per audio file, or is timed against a transcriber's words for a whole take. No transcript: the take is transcribed and the segments are the lines. The transcriber is scribed (`pip install "an[recorded]"`, then a backend): the default is the first **local** backend installed (`scribed[faster-whisper]`); a remote one (`elevenlabs`, `openai` — an upload of the performer's audio, billed) is used only when named with `--transcriber <backend>`. `--diarize` asks for speaker labels. A directory of transcripts pairs with the takes by stem.
- **A transcript an earlier step produced** lives in the project's `transcripts` store (a `lacing` artifact store, `artifacts/transcripts/`; `an.stores.transcripts.record_transcript(mall["transcripts"], key, text)` keeps one): name it as `--transcript artifact:transcripts/<key>` (several: `artifact:transcripts/a,artifact:transcripts/b`, one per take) or pass the `lacing.Artifact` in Python. Each take's provenance then names it (`source.extra.transcript_artifact`) (an#493).
- **Who speaks**: `--speaker` (one performer), `--speakers label=character,…` (a transcript's or diarizer's labels, file stems), `speaker:` prefixes in the transcript, or the scene line the words match.
- **What happens**: each line is cut out (50 ms around the speech), matched to a dialogue line by its words — a take matching none is added to `--shot <id>` or refused — and stored in `assets/recordings/<key>/` with its provenance (`--license` is required: the code you vouch for; `--recorded-by` the performer, listed by `an credits`). The speaker's character gets `voice_ref: <speaker>_recorded`, a voice document with `provider: recorded` (a previous voice is remembered as `replaces`; a speaker who is no character entity gets per-line `voice_ref`s, which an edit of `scene.md` drops). The silence heard between two lines becomes the later line's `(pause …)`, so the shot's rhythm is the performance's; lengthen a shot the report says is too short.
- **Rendering**: a plain `an render` speaks those lines from the store (the `recorded` provider: free, cached by the take's digest, so a re-recorded line is new audio); a line of a recorded voice that has no take **refuses to render** (`an validate` reports it as an error first) — import it or give it another voice. A render's `an credits` lists each take with its performer and permission; a take under `all-rights-reserved` makes the film private, as any private asset does. With word timings the mouth follows the performance under `--lipsync offline` and `--lipsync whisper` alike (no model run). Every import stores the takes it was given; the newest take of a line wins. **One text, one take**: a line's audio is keyed by its voice and text, so two lines of one speaker saying exactly the same words play the same (newest) take — the import warns when it sees that; until a line can carry its own take (an#492), give such lines different words.

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
