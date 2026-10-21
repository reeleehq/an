# ADR 0007 — A performer's recording is a voice: recorded takes enter through the TTS provider seam

**Status:** Proposed, 2026-10-21 (built and merged as [an#494](https://github.com/reeleehq/an/pull/494), released in `an` 0.1.243; the maintainer accepts or amends) · **Decider:** the `recorded-voices` session, for the plot-car production · **Related:** [an#490](https://github.com/reeleehq/an/issues/490) (tracking), [an#494](https://github.com/reeleehq/an/pull/494), [cutan#102](https://github.com/reeleehq/cutan/pull/102), [an#491](https://github.com/reeleehq/an/issues/491), [an#492](https://github.com/reeleehq/an/issues/492), [an#493](https://github.com/reeleehq/an/issues/493), [scribed#6](https://github.com/thorwhalen/scribed/issues/6), ADR 0001.

## Context

A production that records its actors has the voices already. The owner asked (2026-10-20) for `an`/`cutan` to start from audio files that contain the voices, transcribe them with precise timing or take that transcription as input, use the recording as the voices, and clean background noise when asked. Nothing should be synthesized or billed for those lines, and the mouths and the shot's timing should follow the performance.

What existed: the audio pipeline already chooses the TTS provider per voice document (an#305) and keys each line's audio by the provider's `synthesis_options`; `cutan.audio` already turns pre-computed word timings into visemes; the sounds store is the pattern for audio with provenance and a digest; `scribed` is the fleet's ASR facade and `voxy.refprep` its denoiser. Nothing in the fleet *read* SRT/WebVTT/TextGrid/word JSON, and no forced aligner fits the production server's disk.

Two constraints shaped the answer: a recorded voice must never fall back to a synthesized one (that is a billed, wrong take), and a take is third-party work — the performer's — so it carries rights like a sound or a plate does.

## Decision

1. **The take is a voice.** A `recorded` TTS provider (`an.audio.recorded.RecordedTTS`, `repeatable`, `billed = False`) serves a line from the project's `recordings` store; a voice document declares `provider: recorded` and the an#305 chooser picks it. Its `synthesis_options` hook keys the line by the take's sha256, so a re-recorded line is new audio under a new key, and it **refuses a line with no take when requests are resolved**, before anything is produced — consistent with a lost best-of-N take (an#265). `make_tts(name, mall=)` hands the project mall to a factory that takes it; `tts_chooser` and `stamp_from_stores` pass it.
2. **The words travel with the clip.** `AudioClip.words` (optional) carries a take's word timings; a lip-sync provider that aligns from words uses them instead of its own transcription (cutan's offline and whisper providers, cutan#102), the pipeline stamps them on the line, and a cache read-back restores them through the provider's `words_for_clip` hook. Phoneme-level alignment lands on the same field family later (an#491).
3. **The binding is the character's.** The import binds the speaker's character descriptor (`voice_ref`) to the recorded voice document (`<speaker>_recorded`, the previous voice kept as `replaces`). A per-line `voice_ref` is the fallback for a speaker with no (described) character entity, and the report says it is fragile: `scene.md` has no spelling for it (an#492).
4. **A take is an asset with rights.** Takes live in `assets/recordings/<key>/` (`RecordingsStore`, sharing `AudioSidecarStore` with sounds) with an `AssetSource` — licence or permission code (required at import, as for `an sounds add`), performer, source file digest and span — and are walked by `an credits`; a render's credits list the takes its lines play, and `speech_credits` emits no synthesized-speech stub for them.
5. **The recording's rhythm is the shot's.** Each line is cut 50 ms around its speech; the silence heard between two lines becomes the later line's `pause` when the author wrote no timing, so `retime_dialogue` reproduces the performance.
6. **Transcripts are read, transcription is a seam.** `an.audio.transcripts` reads SRT, WebVTT, TextGrid, word JSON and plain `speaker: text`, and times a plain transcript against a transcriber's words (difflib opcodes). The transcriber seam defaults to scribed's first installed **local** backend; a remote one, which uploads the performer's audio and may bill, runs only when named. The reader belongs next to the writer in scribed eventually (scribed#6).
7. **Known limitation, stated.** The pipeline keys a line's audio by voice and text, so two lines of one speaker with identical words play the same (newest) take; the import warns, and the fix rides on a per-line voice/take spelling (an#492).

## Alternatives considered

- **Inject the take as the line's `audio_ref` directly, bypassing providers.** Rejected: it would bypass the content keys, effects, leveling, captions, the credits walk and the cache-gc reader, and every path that trusts a key to describe a request.
- **A lip-sync-only path (feed `WordTimingsLipSync`, keep TTS).** Rejected: the recording is the voice, not an alignment aid; the line would still be synthesized and billed.
- **Bind per line as the primary mechanism.** Rejected: a `scene.md` edit regenerates the IR and drops a line's `voice_ref`; a recorded line falling back to synthesis on an edit is the failure this work exists to prevent.
- **Forced alignment as the default aligner.** Rejected for v1: no model fits the production server, and a timed transcript or one file per line needs no model at all; ASR words matched to the given text is the default, a forced aligner the replacement (an#491).
- **Store takes under `artifacts/`.** Rejected: artifacts are derived and content-keyed; a take is authored, rights-bearing material, like a sound.

## Consequences

- **Gains.** A recorded production renders with nothing billed; the mouth and the pauses follow the performance; provenance and permission are recorded and reported; every existing seam (takes, effects, leveling, captions, shot cache, credits) works unchanged because the take enters as a provider.
- **Costs.** A new store, a new CLI verb (`an voices import`), an optional field on `AudioClip`, an optional extra (`an[recorded]` = scribed), and one more place that must be told about a store (validate's `available_recordings`, credits' walk).
- **Risks.** Identical text in one voice (decision 7); a transcript directory pairing nothing or overlapping cues are refused, never guessed; a remote transcriber is never chosen silently. An adversarial review of the first slice found twelve things, eleven fixed before merge and the twelfth is decision 7.

## First slice

Built: [an#494](https://github.com/reeleehq/an/pull/494) (merged 2026-10-21, `an` 0.1.243) and [cutan#102](https://github.com/reeleehq/cutan/pull/102) (the viseme side; held on an unrelated red CI at the time of writing). Follow-ups: phoneme-level alignment ([an#491](https://github.com/reeleehq/an/issues/491)), a `scene.md` spelling for a line's voice ([an#492](https://github.com/reeleehq/an/issues/492)), a transcript from a lacing artifact ([an#493](https://github.com/reeleehq/an/issues/493)), the transcript reader in scribed ([scribed#6](https://github.com/thorwhalen/scribed/issues/6)).

## Related

ADR 0001 (core and genre: the core keeps the provider and the store, the genre keeps the visemes), an#305 (the voice document chooses the provider), an#265 (takes: the record is the resolution, a lost take refuses before any request), an#486 (a voice written in words is cast by the writer: the same stance, that a render never guesses a voice).
