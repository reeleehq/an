# an.audio.offline_lipsync

OfflineLipSync — deterministic transcript → viseme track. No network, no binary.

The default lip-sync provider for `an`. Maps each meaningful character of the
transcript to a Rhubarb-convention viseme letter (A–H + X), then distributes
keyframes evenly across the audio’s duration. Repeated visemes get collapsed
into a single keyframe so the mouth doesn’t “stutter” on long vowel runs.

Crude but visible. Use `RhubarbLipSync` for real phoneme alignment once
you’ve installed the Rhubarb binary.

```pycon
>>> from an.audio.tts import AudioClip
>>> ls = OfflineLipSync()
>>> track = ls.align(AudioClip(duration=1.0, transcript="hello"), "hello")
>>> track.convention
'rhubarb'
>>> track.duration
1.0
>>> len(track.visemes) >= 2
True
```

### Classes

| [`OfflineLipSync`](#an.audio.offline_lipsync.OfflineLipSync)(\*[, char_to_viseme])   | Default lip-sync provider: deterministic char-to-viseme mapping.   |
|-----------------------------------------------------------------------------------------|--------------------------------------------------------------------|

### *class* an.audio.offline_lipsync.OfflineLipSync(, char_to_viseme=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Default lip-sync provider: deterministic char-to-viseme mapping.

Implements the `LipSyncProvider` protocol.
