# an.audio.whisper_lipsync

WhisperLipSync — faster-whisper word timestamps → viseme keyframes.

Phase 9. Bridges the gap between deterministic `OfflineLipSync` (twitchy,
char-distributed) and the system-binary-dependent `RhubarbLipSync`. Uses
`faster-whisper` to transcribe the rendered audio into word-level
timestamps, then distributes visemes within each word’s [start, end] span
based on the word’s letter→viseme mapping (collapsed-duplicates).

This gives ~75% of Rhubarb-quality lip-sync without any system binaries,
just a ~75 MB model download (cached after first use).

Trade-offs vs. OfflineLipSync:

- **Better**: timing is locked to actual word boundaries. Mouth holds shape
  through silent gaps between words instead of cycling through visemes.
- **Same**: viseme codes per phoneme are still our simple letter mapping;
  no IPA/ARPAbet awareness yet (that’s a future upgrade with cmudict).
- **Cost**: ~3–5 seconds CPU inference for a 10s clip on first call;
  subsequent calls in the same process re-use the cached model.

### Classes

| [`WhisperLipSync`](#an.audio.whisper_lipsync.WhisperLipSync)(\*[, model_size, device, ...])   | faster-whisper word timestamps → visemes.   |
|--------------------------------------------------------------------------------------------------|---------------------------------------------|

### *class* an.audio.whisper_lipsync.WhisperLipSync(, model_size='tiny', device='cpu', compute_type='int8', char_to_viseme=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

faster-whisper word timestamps → visemes.

Implements the `LipSyncProvider` protocol. The model is lazy-loaded on
the first call (subsequent calls in the same process reuse the instance
via the class-level `_model` cache).

#### emits_word_timings *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

Whisper aligns from words, so the track carries them (an#96).
