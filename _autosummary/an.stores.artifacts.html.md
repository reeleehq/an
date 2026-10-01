# an.stores.artifacts

Artifact stores — derived, regeneratable products of the pipeline.

All artifact stores are content-addressed: the key is meant to be a hash of
the IR slice that produced the artifact. This lets later phases skip re-render
when the inputs haven’t changed.

In Phase 1 these are simple file-backed stores; the content-hash convention is
enforced by the caller (orchestrator), not the store.

### Classes

| [`AudioArtifactStore`](#an.stores.artifacts.AudioArtifactStore)(root_dir)   | TTS-rendered audio clips (.wav).                                                                                                                  |
|---------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CaptionsStore`](#an.stores.artifacts.CaptionsStore)(root_dir)        | SubRip caption sidecars (.srt, UTF-8 bytes), keyed like the output they caption — `captions["main"]` is `output/main.srt` (an#175).               |
| [`OutputStore`](#an.stores.artifacts.OutputStore)(root_dir)          | Final composited renders.                                                                                                                         |
| [`PreviewArtifactStore`](#an.stores.artifacts.PreviewArtifactStore)(root_dir) | Low-res preview renders (mp4 or png sequence wrapper).                                                                                            |
| [`ShotArtifactStore`](#an.stores.artifacts.ShotArtifactStore)(root_dir)    | Per-shot rendered mp4s.                                                                                                                           |
| [`TakesArtifactStore`](#an.stores.artifacts.TakesArtifactStore)(root_dir)   | Best-of-N take records (.json bytes), keyed by the line's audio key: which take was kept, its sha256, every take's score and the scorer (an#265). |
| [`VisemeArtifactStore`](#an.stores.artifacts.VisemeArtifactStore)(root_dir)  | Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity.                                                                            |

### *class* an.stores.artifacts.AudioArtifactStore(root_dir)

Bases: `_BlobStore`

TTS-rendered audio clips (.wav).

### *class* an.stores.artifacts.CaptionsStore(root_dir)

Bases: `_BlobStore`

SubRip caption sidecars (.srt, UTF-8 bytes), keyed like the output they
caption — `captions["main"]` is `output/main.srt` (an#175).

### *class* an.stores.artifacts.OutputStore(root_dir)

Bases: `_BlobStore`

Final composited renders.

### *class* an.stores.artifacts.PreviewArtifactStore(root_dir)

Bases: `_BlobStore`

Low-res preview renders (mp4 or png sequence wrapper).

### *class* an.stores.artifacts.ShotArtifactStore(root_dir)

Bases: `_BlobStore`

Per-shot rendered mp4s.

### *class* an.stores.artifacts.TakesArtifactStore(root_dir)

Bases: `_BlobStore`

Best-of-N take records (.json bytes), keyed by the line’s audio key: which
take was kept, its sha256, every take’s score and the scorer (an#265).

### *class* an.stores.artifacts.VisemeArtifactStore(root_dir)

Bases: `_BlobStore`

Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity.
