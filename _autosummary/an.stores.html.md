# an.stores

Project mall: a dict of dol-backed `MutableMapping` stores.

The mall is the unit of persistence in an. Every long-lived state — assets
(characters, props, environments, voices, styles, sounds, recordings), the scene file pair, intermediate
artifacts (audio, viseme tracks, best-of-N take records, per-shot mp4s, the
content-keyed shot cache, linked transcripts),
final output and its caption sidecar, the agent’s decision log, and the asset
library’s lockfile of pinned check-outs — is keyed inside a store. Stores are
dol-backed so the same call
sites work against filesystem, SQLite, S3, etc.

```pycon
>>> import tempfile
>>> from pathlib import Path
>>> with tempfile.TemporaryDirectory() as d:
...     mall = build_project_mall(d, ensure=True)
...     sorted(mall.keys()) == [
...         'audio', 'captions', 'characters', 'contact_sheets', 'decisions',
...         'environments', 'library_lock', 'measurements', 'output',
...         'pictures', 'previews', 'props', 'recordings', 'render_reports', 'scenes',
...         'shot_cache', 'shots', 'sounds', 'sources', 'styles', 'takes',
...         'transcripts', 'visemes', 'voices',
...     ]
True
```

### Functions

| [`asset_ref_problem`](#an.stores.asset_ref_problem)(rel)                             | Why `rel`, a path an asset document names, is NOT a clean relative path inside the asset's folder, or `None` when it is one (an#483).                                                                                                                                                                                                           |
|-----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`asset_ref_problems`](#an.stores.asset_ref_problems)(doc[, folder, file_problems])   | `(label, message)` for every reference in `doc` ([`asset_references()`](#an.stores.asset_references)) that breaks the asset-reference rule (an#483, an#552); `[]` when none does.                                                                                                                                               |
| [`asset_references`](#an.stores.asset_references)(doc)                              | `(label, path)` for every file path an asset document names (an#552): an environment's image planes (`planes/<name>/art/src`), a rig's attachments (`skins/<skin>/slots/<slot>/<attachment>/path`; labelled `part <skin>:<slot>/<attachment>` outside the default skin), a character's `source_svg` and the files its `colour_roles` keys name. |
| [`inside_folder`](#an.stores.inside_folder)(folder, rel)                         | `folder / rel` when `rel` is a relative path that stays inside `folder` once symlinks are resolved, else `None` (an#483).                                                                                                                                                                                                                       |
| [`build_project_mall`](#an.stores.build_project_mall)(project_dir, \*[, ensure, ...]) | Build the standard project mall over `project_dir`.                                                                                                                                                                                                                                                                                             |

### Classes

| [`CharactersStore`](#an.stores.CharactersStore)(root_dir)              | Per-character directory store.                                                                                                                                                                                    |
|-----------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`EnvironmentsStore`](#an.stores.EnvironmentsStore)(root_dir)            | Per-environment directory store (meta + sidecar art).                                                                                                                                                             |
| [`VoicesStore`](#an.stores.VoicesStore)(root_dir)                  | JSON-only voice descriptors.                                                                                                                                                                                      |
| [`StylesStore`](#an.stores.StylesStore)(root_dir)                  | Pure-JSON style descriptors.                                                                                                                                                                                      |
| [`PropsStore`](#an.stores.PropsStore)(root_dir)                   | Per-prop directory store.                                                                                                                                                                                         |
| [`ScenesStore`](#an.stores.ScenesStore)(project_dir[, scene_file]) | `MutableMapping` exposing the scene file pair under a project root.                                                                                                                                               |
| [`SoundsStore`](#an.stores.SoundsStore)(root_dir)                  | Per-sound directory store.                                                                                                                                                                                        |
| [`RecordingsStore`](#an.stores.RecordingsStore)(root_dir)              | Per-take directory store: `<key>/recording.json` + `<key>/audio.wav`.                                                                                                                                             |
| [`AudioArtifactStore`](#an.stores.AudioArtifactStore)(root_dir)           | TTS-rendered audio clips (.wav).                                                                                                                                                                                  |
| [`VisemeArtifactStore`](#an.stores.VisemeArtifactStore)(root_dir)          | Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity.                                                                                                                                            |
| [`TakesArtifactStore`](#an.stores.TakesArtifactStore)(root_dir)           | Best-of-N take records (.json bytes), keyed by the line's audio key: which take was kept, its sha256, every take's score and the scorer (an#265).                                                                 |
| [`ShotArtifactStore`](#an.stores.ShotArtifactStore)(root_dir)            | Per-shot rendered mp4s.                                                                                                                                                                                           |
| [`PreviewArtifactStore`](#an.stores.PreviewArtifactStore)(root_dir)         | Low-res preview renders (mp4 or png sequence wrapper).                                                                                                                                                            |
| [`ContactSheetStore`](#an.stores.ContactSheetStore)(root_dir)            | Contact sheets (.png): frames of a render at its settled beats, labelled with their time, for a person or an agent to LOOK at (core study §2.10).                                                                 |
| [`MeasurementStore`](#an.stores.MeasurementStore)(root_dir)             | Measurements a clock-owning renderer made of its content (.json bytes), keyed by that content's key — DERIVED data, never the author's (an#279): a Manim shot's length, its timeline of beats, its findings.      |
| [`PictureStore`](#an.stores.PictureStore)(root_dir)                 | An opaque renderer's raw picture (.mp4) — a Manim scene's own render, before it is conformed to a film's fps and size, so a change that is not to the picture (narration, fps) does not run Manim again (an#279). |
| [`RenderReportStore`](#an.stores.RenderReportStore)(root_dir)            | What a render found (.json), keyed like the output it describes — `render_reports["main"]` — so `orchestrate` and MCP read the findings that `an render` warned (an#279).                                         |
| [`SourcesStore`](#an.stores.SourcesStore)(root_dir)                 | Python scene sources (`.py` bytes) — a Manim scene file per key.                                                                                                                                                  |
| [`OutputStore`](#an.stores.OutputStore)(root_dir)                  | Final composited renders.                                                                                                                                                                                         |
| [`DecisionLogStore`](#an.stores.DecisionLogStore)(log_path)             | Append-only JSONL log keyed by ordinal index (as string).                                                                                                                                                         |
| [`ProjectLock`](#an.stores.ProjectLock)(project_dir)               | `<store>/<key> -> pin` over a project's `assets.lock.json`.                                                                                                                                                       |

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

### *class* an.stores.ContactSheetStore(root_dir)

Bases: `_BlobStore`

Contact sheets (.png): frames of a render at its settled beats, labelled
with their time, for a person or an agent to LOOK at (core study §2.10).

Content-addressed — the key is the sha256 of the PNG bytes — so a shot whose
render is reused from the shot cache still points at its sheet through the
cached provenance, and two shots with one picture share one file.

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

### *class* an.stores.MeasurementStore(root_dir)

Bases: `_BlobStore`

Measurements a clock-owning renderer made of its content (.json bytes),
keyed by that content’s key — DERIVED data, never the author’s (an#279):
a Manim shot’s length, its timeline of beats, its findings.

### *class* an.stores.OutputStore(root_dir)

Bases: `_BlobStore`

Final composited renders.

### *class* an.stores.PictureStore(root_dir)

Bases: `_BlobStore`

An opaque renderer’s raw picture (.mp4) — a Manim scene’s own render,
before it is conformed to a film’s fps and size, so a change that is not to
the picture (narration, fps) does not run Manim again (an#279).
Content-addressed (the key is the sha256 of the mp4): the measurement
record under the picture key names it, so a record and its picture are
written as one (an#291).

### *class* an.stores.PreviewArtifactStore(root_dir)

Bases: `_BlobStore`

Low-res preview renders (mp4 or png sequence wrapper).

### *class* an.stores.ProjectLock(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`<store>/<key> -> pin` over a project’s `assets.lock.json`.

Every write rewrites the whole (small) file, sorted, so the lockfile diffs
cleanly under version control. The mapping is the `assets` section;
[`kits`](#an.stores.ProjectLock.kits) is the `kits` section, and a write to either keeps the other.

#### *property* kits *: [MutableMapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Any](https://docs.python.org/3/library/typing.html#typing.Any)]]*

`kit asset id -> record` of the kits checked out into the project.

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

### *class* an.stores.RecordingsStore(root_dir)

Bases: `AudioSidecarStore`

Per-take directory store: `<key>/recording.json` + `<key>/audio.wav`.

#### ENTRY_NOUN *= 'recording'*

What an entry is called in error messages.

### *class* an.stores.RenderReportStore(root_dir)

Bases: `_BlobStore`

What a render found (.json), keyed like the output it describes —
`render_reports["main"]` — so `orchestrate` and MCP read the findings
that `an render` warned (an#279).

### *class* an.stores.ScenesStore(project_dir, scene_file='scene.md')

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`MutableMapping` exposing the scene file pair under a project root.

Keys: currently always `"main"`. The store enforces this by raising
`KeyError` for other keys.

#### patch_shot_durations(durations)

Set `duration` on the named shots WITHOUT regenerating `scene.md`.

`__setitem__` rewrites the markdown from the IR, which drops every word
of prose and every comment the IR does not hold. This writes the JSON
through the read boundary as usual, and patches only each shot’s
`duration:` line in the markdown (inserting one into its

```
``
```

\`\` ``yaml shot ``` block, or the block itself, when there is none) —
what `an sync --accept-measured` uses to take a measured duration into
the authored scene (an#279).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### *property* project_dir *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

The project folder this store’s scene file is in (its sibling scene
files are there too: a `continue:` reads them, an#542).

### *class* an.stores.ShotArtifactStore(root_dir)

Bases: `_BlobStore`

Per-shot rendered mp4s.

### *class* an.stores.SoundsStore(root_dir)

Bases: `AudioSidecarStore`

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

#### ENTRY_NOUN *= 'sound'*

What an entry is called in error messages.

### *class* an.stores.SourcesStore(root_dir)

Bases: `_BlobStore`

Python scene sources (`.py` bytes) — a Manim scene file per key.

### *class* an.stores.StylesStore(root_dir)

Bases: `JsonDirStore`

Pure-JSON style descriptors.

### *class* an.stores.TakesArtifactStore(root_dir)

Bases: `_BlobStore`

Best-of-N take records (.json bytes), keyed by the line’s audio key: which
take was kept, its sha256, every take’s score and the scorer (an#265).

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

### an.stores.asset_ref_problem(rel)

Why `rel`, a path an asset document names, is NOT a clean relative
path inside the asset’s folder, or `None` when it is one (an#483).

An asset reference resolves inside its own folder, never anywhere else:
an absolute path, a `..` that leaves the folder or a URL is refused by
name, before any read — a project may be someone else’s input (a
production pack checked on a server), and a reference that reaches outside
it is a file-existence and XML-parse oracle on the host. The spelling is
held to the library’s rule too (no `.` or empty segment, no backslash),
so a reference that validates here publishes there unchanged.

```pycon
>>> asset_ref_problem("parts/head.svg") is None
True
>>> asset_ref_problem("/etc/hostname")
'is an absolute path'
>>> asset_ref_problem("../../other/plate.png")
'leaves the asset folder (`..`)'
>>> asset_ref_problem("file:///etc/hostname"), asset_ref_problem("C:/art/x.svg")
('is a URL or a drive path (`:`)', 'is a URL or a drive path (`:`)')
>>> asset_ref_problem("./parts/head.svg"), asset_ref_problem("parts\\head.svg"), asset_ref_problem("")
('has an empty or `.` segment', 'uses a backslash (write the path with `/`)', 'is empty')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stores.asset_ref_problems(doc, folder=None, , file_problems=None)

`(label, message)` for every reference in `doc`
([`asset_references()`](#an.stores.asset_references)) that breaks the asset-reference rule (an#483,
an#552); `[]` when none does. The one rule the core and a genre share.

A reference is judged by NAME first ([`asset_ref_problem()`](#an.stores.asset_ref_problem)), and is
never read when its name is bad; with a `folder`, also by where it
resolves ([`inside_folder()`](#an.stores.inside_folder): a link out of the folder is the same
error). `file_problems`, when given, is asked about each file that
passed (the core passes its SVG self-containment check): it is called
for every path that passed the name (and folder) check, whether or not
the file exists, so it must tolerate an absent file. Each message it
returns is appended to `"<label> names <path>, which"`, so it must
begin with a verb (`"is SVG that ..."`, `"is not in the folder"`).
`message` is a whole sentence, label included, so a caller can report
it as is.

```pycon
>>> asset_ref_problems({"source_svg": "../x.svg", "planes": [
...     {"name": "sky", "art": {"kind": "image", "src": "sky.png"}}]})
[('source_svg', "source_svg names '../x.svg', which leaves the asset folder (`..`):
  an asset reference must be a relative path inside the asset's own folder
  (nothing outside it is read)")]
>>> asset_ref_problems({"source_svg": "source.svg"}, ".")
[]
>>> asset_ref_problems({"source_svg": "ok.svg"}, ".",
...                    file_problems=lambda f: [f"is SVG that holds a <script>"])
[('source_svg', "source_svg names 'ok.svg', which is SVG that holds a <script>")]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.stores.asset_references(doc)

`(label, path)` for every file path an asset document names (an#552):
an environment’s image planes (`planes/<name>/art/src`), a rig’s
attachments (`skins/<skin>/slots/<slot>/<attachment>/path`; labelled
`part <skin>:<slot>/<attachment>` outside the default skin), a
character’s `source_svg` and the files its `colour_roles` keys name.

The one list of what an asset document references; the core’s
`an validate` and a genre’s own validator both walk it, so they cannot
disagree about which fields hold a path.

```pycon
>>> asset_references({"planes": [{"name": "sky", "art": {"kind": "image", "src": "sky.png"}},
...                              {"name": "fill", "art": {"kind": "fill"}}]})
[('plane sky', 'sky.png')]
>>> asset_references({"skins": {"default": {"slots": {"body": {"body": {"path": "parts/body.svg"}}}}},
...                   "source_svg": "source.svg", "colour_roles": {"parts/body.svg": {"#fff": "skin"}}})
[('part body/body', 'parts/body.svg'), ('source_svg', 'source.svg'), ('colour_roles parts/body.svg', 'parts/body.svg')]
```

A malformed document names nothing where it is malformed (its schema
check reports it), rather than raising:

```pycon
>>> asset_references({"planes": [{"art": "sky.png"}], "skins": {"default": {"slots": ["body"]}},
...                   "source_svg": 3})
[]
>>> asset_references({"planes": "sky.png", "skins": ["default"]})
[]
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.stores.build_project_mall(project_dir, , ensure=False, scene_file='scene.md', \*\*overrides)

Build the standard project mall over `project_dir`.

Pass `ensure=True` to create the per-store directories on disk if they
don’t exist. `scene_file` picks the scene the `scenes` store holds (an#539;
`scene.md` by default). Pass keyword overrides to swap in alternate stores (e.g. an
in-memory `dict` for tests).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`MutableMapping`](https://docs.python.org/3/library/typing.html#typing.MutableMapping)]

### an.stores.inside_folder(folder, rel)

`folder / rel` when `rel` is a relative path that stays inside
`folder` once symlinks are resolved, else `None` (an#483). The path is
returned as joined, not resolved, so a caller’s own stat and digest see
the same spelling they always did.

```pycon
>>> import tempfile, os
>>> with tempfile.TemporaryDirectory() as d:
...     inside_folder(d, "parts/head.svg") == Path(d) / "parts/head.svg"
...     inside_folder(d, "../head.svg") is None, inside_folder(d, "/etc/hostname") is None
True
(True, True)
```

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### Modules

| [`artifacts`](an.stores.artifacts.html.md#module-an.stores.artifacts)       | Artifact stores — derived, regeneratable products of the pipeline.                       |
|---------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`characters`](an.stores.characters.html.md#module-an.stores.characters)     | Characters store — descriptor + sidecar folder per character.                            |
| [`decisions`](an.stores.decisions.html.md#module-an.stores.decisions)       | Decision log — append-only JSONL of agent decisions and user approvals.                  |
| [`environments`](an.stores.environments.html.md#module-an.stores.environments) | Environments store — backgrounds, set pieces, and prop bundles.                          |
| [`library_lock`](an.stores.library_lock.html.md#module-an.stores.library_lock) | The project lockfile: which library version each checked-out asset came from.            |
| [`props`](an.stores.props.html.md#module-an.stores.props)               | Props store — descriptor + sidecar folder per prop.                                      |
| [`recordings`](an.stores.recordings.html.md#module-an.stores.recordings)     | Recordings store — one directory per recorded take: `recording.json` beside `audio.wav`. |
| [`scenes`](an.stores.scenes.html.md#module-an.stores.scenes)             | Scenes store — wraps the project's `scene.md` + `ir/scene.json` pair.                    |
| [`sounds`](an.stores.sounds.html.md#module-an.stores.sounds)             | Sounds store — one directory per sound: `sound.json` beside `audio.wav`.                 |
| [`sources`](an.stores.sources.html.md#module-an.stores.sources)           | The project's opaque scene sources: files a whole-shot renderer runs as they are.        |
| [`styles`](an.stores.styles.html.md#module-an.stores.styles)             | Styles store — visual style presets (color palette, line weight, fonts).                 |
| [`transcripts`](an.stores.transcripts.html.md#module-an.stores.transcripts)   | Transcripts as linked artifacts in the project store (an#493).                           |
| [`voices`](an.stores.voices.html.md#module-an.stores.voices)             | Voices store — pure JSON; one entry per voice.                                           |
