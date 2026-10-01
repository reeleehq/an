# an.verify.media_quality

MediaQualityVerifier — post-render quality checks on the actual mp4.

Phase 9. Implements the `Verifier` Protocol using helpers from
`an.verify.media`. Runs only when given a `RenderResult` (skips silently
on pre-render calls). Adds three signals to the orchestrator’s verify pass:

1. **Audio level**: max dB above a floor — catches “AAC stream present but
   silent because the TTS produced empty bytes”.
2. **Silence vs. dialogue**: if the IR contains dialogue, the rendered
   audio shouldn’t be near-silent for most of the duration.
3. **Frame motion**: the mean SSIM between adjacent sampled frames
   shouldn’t be ~1.0 — a frozen render reads as flat.

Each check produces a `Finding` whose severity is “warning” so the run
proceeds; the orchestrator can decide whether to surface or block.

### Classes

| [`MediaQualityVerifier`](#an.verify.media_quality.MediaQualityVerifier)(\*[, max_db_floor, ...])   | Post-render quality checks.   |
|--------------------------------------------------------------------------------------------------|-------------------------------|

### *class* an.verify.media_quality.MediaQualityVerifier(, max_db_floor=-75.0, dialogue_silence_ratio=0.7, frozen_ssim_threshold=0.999, frame_sample_fps=4.0)

Bases: `object`

Post-render quality checks. Implements `Verifier`.
