# an.stores.artifacts

Artifact stores — derived, regeneratable products of the pipeline.

All artifact stores are content-addressed: the key is meant to be a hash of
the IR slice that produced the artifact. This lets later phases skip re-render
when the inputs haven’t changed.

In Phase 1 these are simple file-backed stores; the content-hash convention is
enforced by the caller (orchestrator), not the store.

### Classes

| [`AudioArtifactStore`](#an.stores.artifacts.AudioArtifactStore)(root_dir)   | TTS-rendered audio clips (.wav).                                       |
|---------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`OutputStore`](#an.stores.artifacts.OutputStore)(root_dir)          | Final composited renders.                                              |
| [`PreviewArtifactStore`](#an.stores.artifacts.PreviewArtifactStore)(root_dir) | Low-res preview renders (mp4 or png sequence wrapper).                 |
| [`ShotArtifactStore`](#an.stores.artifacts.ShotArtifactStore)(root_dir)    | Per-shot rendered mp4s.                                                |
| [`VisemeArtifactStore`](#an.stores.artifacts.VisemeArtifactStore)(root_dir)  | Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity. |

### *class* an.stores.artifacts.AudioArtifactStore(root_dir)

Bases: `_BlobStore`

TTS-rendered audio clips (.wav).

### *class* an.stores.artifacts.OutputStore(root_dir)

Bases: `_BlobStore`

Final composited renders.

### *class* an.stores.artifacts.PreviewArtifactStore(root_dir)

Bases: `_BlobStore`

Low-res preview renders (mp4 or png sequence wrapper).

### *class* an.stores.artifacts.ShotArtifactStore(root_dir)

Bases: `_BlobStore`

Per-shot rendered mp4s.

### *class* an.stores.artifacts.VisemeArtifactStore(root_dir)

Bases: `_BlobStore`

Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity.
