# an.stores.artifacts

Artifact stores — derived, regeneratable products of the pipeline.

All artifact stores are content-addressed: the key is meant to be a hash of
the IR slice that produced the artifact. This lets later phases skip re-render
when the inputs haven’t changed.

In Phase 1 these are simple file-backed stores; the content-hash convention is
enforced by the caller (orchestrator), not the store.

### Classes

| [`AudioArtifactStore`](#an.stores.artifacts.AudioArtifactStore)(root_dir)   | TTS-rendered audio clips (.wav).                                                                                                                                                                                  |
|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`CaptionsStore`](#an.stores.artifacts.CaptionsStore)(root_dir)        | SubRip caption sidecars (.srt, UTF-8 bytes), keyed like the output they caption — `captions["main"]` is `output/main.srt` (an#175).                                                                               |
| [`ContactSheetStore`](#an.stores.artifacts.ContactSheetStore)(root_dir)    | Contact sheets (.png): frames of a render at its settled beats, labelled with their time, for a person or an agent to LOOK at (core study §2.10).                                                                 |
| [`MeasurementStore`](#an.stores.artifacts.MeasurementStore)(root_dir)     | Measurements a clock-owning renderer made of its content (.json bytes), keyed by that content's key — DERIVED data, never the author's (an#279): a Manim shot's length, its timeline of beats, its findings.      |
| [`OutputStore`](#an.stores.artifacts.OutputStore)(root_dir)          | Final composited renders.                                                                                                                                                                                         |
| [`PictureStore`](#an.stores.artifacts.PictureStore)(root_dir)         | An opaque renderer's raw picture (.mp4) — a Manim scene's own render, before it is conformed to a film's fps and size, so a change that is not to the picture (narration, fps) does not run Manim again (an#279). |
| [`PreviewArtifactStore`](#an.stores.artifacts.PreviewArtifactStore)(root_dir) | Low-res preview renders (mp4 or png sequence wrapper).                                                                                                                                                            |
| [`RenderReportStore`](#an.stores.artifacts.RenderReportStore)(root_dir)    | What a render found (.json), keyed like the output it describes — `render_reports["main"]` — so `orchestrate` and MCP read the findings that `an render` warned (an#279).                                         |
| [`ShotArtifactStore`](#an.stores.artifacts.ShotArtifactStore)(root_dir)    | Per-shot rendered mp4s.                                                                                                                                                                                           |
| [`TakesArtifactStore`](#an.stores.artifacts.TakesArtifactStore)(root_dir)   | Best-of-N take records (.json bytes), keyed by the line's audio key: which take was kept, its sha256, every take's score and the scorer (an#265).                                                                 |
| [`VisemeArtifactStore`](#an.stores.artifacts.VisemeArtifactStore)(root_dir)  | Lip-sync viseme tracks (.json) — stored as bytes for cache uniformity.                                                                                                                                            |

### *class* an.stores.artifacts.AudioArtifactStore(root_dir)

Bases: `_BlobStore`

TTS-rendered audio clips (.wav).

### *class* an.stores.artifacts.CaptionsStore(root_dir)

Bases: `_BlobStore`

SubRip caption sidecars (.srt, UTF-8 bytes), keyed like the output they
caption — `captions["main"]` is `output/main.srt` (an#175).

### *class* an.stores.artifacts.ContactSheetStore(root_dir)

Bases: `_BlobStore`

Contact sheets (.png): frames of a render at its settled beats, labelled
with their time, for a person or an agent to LOOK at (core study §2.10).

Content-addressed — the key is the sha256 of the PNG bytes — so a shot whose
render is reused from the shot cache still points at its sheet through the
cached provenance, and two shots with one picture share one file.

### *class* an.stores.artifacts.MeasurementStore(root_dir)

Bases: `_BlobStore`

Measurements a clock-owning renderer made of its content (.json bytes),
keyed by that content’s key — DERIVED data, never the author’s (an#279):
a Manim shot’s length, its timeline of beats, its findings.

### *class* an.stores.artifacts.OutputStore(root_dir)

Bases: `_BlobStore`

Final composited renders.

### *class* an.stores.artifacts.PictureStore(root_dir)

Bases: `_BlobStore`

An opaque renderer’s raw picture (.mp4) — a Manim scene’s own render,
before it is conformed to a film’s fps and size, so a change that is not to
the picture (narration, fps) does not run Manim again (an#279).
Content-addressed (the key is the sha256 of the mp4): the measurement
record under the picture key names it, so a record and its picture are
written as one (an#291).

### *class* an.stores.artifacts.PreviewArtifactStore(root_dir)

Bases: `_BlobStore`

Low-res preview renders (mp4 or png sequence wrapper).

### *class* an.stores.artifacts.RenderReportStore(root_dir)

Bases: `_BlobStore`

What a render found (.json), keyed like the output it describes —
`render_reports["main"]` — so `orchestrate` and MCP read the findings
that `an render` warned (an#279).

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
