# an.stores.voices

Voices store — pure JSON; one entry per voice.

A voice descriptor carries: provider (e.g. `elevenlabs`), provider voice id,
display name, optional cloning source ref, and emotion presets.

### Classes

| [`VoicesStore`](#an.stores.voices.VoicesStore)(root_dir)   | JSON-only voice descriptors.   |
|--------------------------------------------------------------------------|--------------------------------|

### *class* an.stores.voices.VoicesStore(root_dir)

Bases: `JsonDirStore`

JSON-only voice descriptors.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = VoicesStore(d)
...     store['maya-warm'] = {'provider': 'elevenlabs', 'voice_id': 'xyz'}
...     'maya-warm' in store
True
```
