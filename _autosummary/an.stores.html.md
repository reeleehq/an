# an.stores

Project mall: a dict of dol-backed `MutableMapping` stores.

The mall is the unit of persistence in an. Every long-lived state — assets
(characters, props, environments, voices, styles, sounds), the scene file pair, intermediate
artifacts (audio, viseme tracks, per-shot mp4s), final output and its caption
sidecar, and the agent’s
decision log — is keyed inside a store. Stores are dol-backed so the same call
sites work against filesystem, SQLite, S3, etc.

```pycon
>>> import tempfile
>>> from pathlib import Path
>>> with tempfile.TemporaryDirectory() as d:
...     mall = build_project_mall(d, ensure=True)
...     sorted(mall.keys()) == [
...         'audio', 'captions', 'characters', 'decisions', 'environments',
...         'output', 'previews', 'props', 'scenes', 'shots',
...         'sounds', 'styles', 'visemes', 'voices',
...     ]
True
```

### Functions

| [`build_project_mall`](#an.stores.build_project_mall)(project_dir, \*[, ensure])   | Build the standard project mall over `project_dir`.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------|

### Classes

| [`CharactersStore`](#an.stores.CharactersStore)(root_dir)      | Per-character directory store.                                         |
|---------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`EnvironmentsStore`](#an.stores.EnvironmentsStore)(root_dir)    | Per-environment directory store (meta + sidecar art).                  |
| [`VoicesStore`](#an.stores.VoicesStore)(root_dir)          | JSON-only voice descriptors.                                           |
| [`StylesStore`](#an.stores.StylesStore)(root_dir)          | Pure-JSON style descriptors.                                           |
| [`PropsStore`](#an.stores.PropsStore)(root_dir)           | Per-prop directory store.                                              |
| [`ScenesStore`](#an.stores.ScenesStore)(project_dir)       | `MutableMapping` exposing the scene file pair under a project root.    |
| [`SoundsStore`](#an.stores.SoundsStore)(root_dir)          | Per-sound directory store.                                             |
| [`AudioArtifactStore`](#an.stores.AudioArtifactStore)(root_dir)   | TTS-rendered audio clips (.wav).                                       |
| [`VisemeArtifactStore`](#an.stores.VisemeArtifactStore)(root_dir)  | Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity. |
| [`ShotArtifactStore`](#an.stores.ShotArtifactStore)(root_dir)    | Per-shot rendered mp4s.                                                |
| [`PreviewArtifactStore`](#an.stores.PreviewArtifactStore)(root_dir) | Low-res preview renders (mp4 or png sequence wrapper).                 |
| [`OutputStore`](#an.stores.OutputStore)(root_dir)          | Final composited renders.                                              |
| [`DecisionLogStore`](#an.stores.DecisionLogStore)(log_path)     | Append-only JSONL log keyed by ordinal index (as string).              |

### *class* an.stores.AudioArtifactStore(root_dir)

Bases: `_BlobStore`

TTS-rendered audio clips (.wav).

### *class* an.stores.CharactersStore(root_dir)

Bases: `JsonSidecarStore`

Per-character directory store.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = CharactersStore(d)
...     store['maya'] = {'name': 'Maya', 'voice_ref': 'maya-warm'}
...     store['maya']['name']
'Maya'
```

### *class* an.stores.DecisionLogStore(log_path)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

Append-only JSONL log keyed by ordinal index (as string).

Mutating in-place (`__setitem__`, `__delitem__`) is intentionally
forbidden; the log is append-only by design.

```pycon
>>> import tempfile, os
>>> with tempfile.TemporaryDirectory() as d:
...     log = DecisionLogStore(os.path.join(d, 'decisions.jsonl'))
...     _ = log.append(kind='test', body={'x': 1})
...     _ = log.append(kind='test', body={'x': 2})
...     entries = list(log.values())
...     entries[0]['body']['x'], entries[1]['body']['x']
(1, 2)
```

#### append(, kind, body, \*\*extra)

Append one decision; returns its ordinal index.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### *class* an.stores.EnvironmentsStore(root_dir)

Bases: `JsonSidecarStore`

Per-environment directory store (meta + sidecar art).

### *class* an.stores.OutputStore(root_dir)

Bases: `_BlobStore`

Final composited renders.

### *class* an.stores.PreviewArtifactStore(root_dir)

Bases: `_BlobStore`

Low-res preview renders (mp4 or png sequence wrapper).

### *class* an.stores.PropsStore(root_dir)

Bases: `JsonSidecarStore`

Per-prop directory store.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = PropsStore(d)
...     store['lamp'] = {'name': 'Desk lamp'}
...     store['lamp']['name']
'Desk lamp'
```

### *class* an.stores.ScenesStore(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`MutableMapping` exposing the scene file pair under a project root.

Keys: currently always `"main"`. The store enforces this by raising
`KeyError` for other keys.

### *class* an.stores.ShotArtifactStore(root_dir)

Bases: `_BlobStore`

Per-shot rendered mp4s.

### *class* an.stores.SoundsStore(root_dir)

Bases: `JsonSidecarStore`

Per-sound directory store.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = SoundsStore(d)
...     store['hit'] = {'description': 'a stick on a table'}
...     store.write_audio('hit', b'RIFF....')
...     store['hit']['description'], store.read_audio('hit')
('a stick on a table', b'RIFF....')
```

#### AUDIO_NAME *= 'audio.wav'*

`an.sounds` reads
its header for the duration a fade-out needs, deterministically.

* **Type:**
  The sidecar holding the audio bytes. WAV only in v1

### *class* an.stores.StylesStore(root_dir)

Bases: `JsonDirStore`

Pure-JSON style descriptors.

### *class* an.stores.VisemeArtifactStore(root_dir)

Bases: `_BlobStore`

Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity.

### *class* an.stores.VoicesStore(root_dir)

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

### an.stores.build_project_mall(project_dir, , ensure=False, \*\*overrides)

Build the standard project mall over `project_dir`.

Pass `ensure=True` to create the per-store directories on disk if they
don’t exist. Pass keyword overrides to swap in alternate stores (e.g. an
in-memory `dict` for tests).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`MutableMapping`](https://docs.python.org/3/library/typing.html#typing.MutableMapping)]

### Modules

| [`artifacts`](an.stores.artifacts.html.md#module-an.stores.artifacts)       | Artifact stores — derived, regeneratable products of the pipeline.       |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`characters`](an.stores.characters.html.md#module-an.stores.characters)     | Characters store — descriptor + sidecar folder per character.            |
| [`decisions`](an.stores.decisions.html.md#module-an.stores.decisions)       | Decision log — append-only JSONL of agent decisions and user approvals.  |
| [`environments`](an.stores.environments.html.md#module-an.stores.environments) | Environments store — backgrounds, set pieces, and prop bundles.          |
| [`props`](an.stores.props.html.md#module-an.stores.props)               | Props store — descriptor + sidecar folder per prop.                      |
| [`scenes`](an.stores.scenes.html.md#module-an.stores.scenes)             | Scenes store — wraps the project's `scene.md` + `ir/scene.json` pair.    |
| [`sounds`](an.stores.sounds.html.md#module-an.stores.sounds)             | Sounds store — one directory per sound: `sound.json` beside `audio.wav`. |
| [`styles`](an.stores.styles.html.md#module-an.stores.styles)             | Styles store — visual style presets (color palette, line weight, fonts). |
| [`voices`](an.stores.voices.html.md#module-an.stores.voices)             | Voices store — pure JSON; one entry per voice.                           |
