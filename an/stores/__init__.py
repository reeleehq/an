"""Project mall: a dict of dol-backed `MutableMapping` stores.

The mall is the unit of persistence in an. Every long-lived state — assets
(characters, props, environments, voices, styles, sounds, recordings), the scene file pair, intermediate
artifacts (audio, viseme tracks, best-of-N take records, per-shot mp4s, the
content-keyed shot cache, linked transcripts),
final output and its caption sidecar, the agent's decision log, and the asset
library's lockfile of pinned check-outs — is keyed inside a store. Stores are
dol-backed so the same call
sites work against filesystem, SQLite, S3, etc.

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
"""

from __future__ import annotations

from pathlib import Path
from typing import MutableMapping

from an.ir.sync import DEFAULT_SCENE_FILE, SceneFile
from an.stores._common import (
    ASSET_REF_RULE,
    asset_ref_problem,
    asset_ref_problems,
    asset_references,
    inside_folder,
    JsonDirStore,
)
from an.stores.characters import CharactersStore
from an.stores.decisions import DecisionLogStore
from an.stores.environments import EnvironmentsStore
from an.stores.library_lock import ProjectLock
from an.stores.props import PropsStore
from an.stores.recordings import RecordingsStore
from an.stores.scenes import ScenesStore
from an.stores.sources import SourcesStore
from an.stores.sounds import SoundsStore
from an.stores.styles import StylesStore
from an.stores.voices import VoicesStore
from an.build.shot_cache import shot_cache_store
from an.stores.transcripts import transcripts_store
from an.stores.artifacts import (
    AudioArtifactStore,
    CaptionsStore,
    ContactSheetStore,
    MeasurementStore,
    OutputStore,
    PictureStore,
    PreviewArtifactStore,
    RenderReportStore,
    ShotArtifactStore,
    TakesArtifactStore,
    VisemeArtifactStore,
)

__all__ = [
    "ASSET_REF_RULE",
    "asset_ref_problem",
    "asset_ref_problems",
    "asset_references",
    "inside_folder",
    "JsonDirStore",
    "CharactersStore",
    "EnvironmentsStore",
    "VoicesStore",
    "StylesStore",
    "PropsStore",
    "ScenesStore",
    "SoundsStore",
    "RecordingsStore",
    "AudioArtifactStore",
    "VisemeArtifactStore",
    "TakesArtifactStore",
    "ShotArtifactStore",
    "PreviewArtifactStore",
    "ContactSheetStore",
    "MeasurementStore",
    "PictureStore",
    "RenderReportStore",
    "SourcesStore",
    "OutputStore",
    "DecisionLogStore",
    "ProjectLock",
    "build_project_mall",
    "UNSTORED_FOLDERS",
]


#: The folders of a project's tree that no store owns, which ``ensure=True``
#: lays out beside the stores' own: ``ir/``, where the scene store writes the
#: default scene's IR (the store's root is the project folder itself).
UNSTORED_FOLDERS = ("ir",)


def build_project_mall(
    project_dir: str | Path,
    *,
    ensure: bool = False,
    scene_file: str | Path | SceneFile = DEFAULT_SCENE_FILE,
    **overrides: MutableMapping,
) -> dict[str, MutableMapping]:
    """Build the standard project mall over ``project_dir``.

    Building it lays out nothing (an#696): every file store makes its folder
    on its first write, a missing one reading as empty. ``ensure=True``
    (``an init``) lays out the tree at once: each store's folder, through the
    store, and the :data:`UNSTORED_FOLDERS`. ``scene_file`` picks the scene
    the ``scenes`` store holds (an#539; ``scene.md`` by default). Pass keyword
    overrides to swap in alternate stores (e.g. an in-memory `dict` for tests).
    """
    pdir = Path(project_dir)
    if ensure:
        for sub in UNSTORED_FOLDERS:
            (pdir / sub).mkdir(parents=True, exist_ok=True)

    def at(store_cls, *parts: str):
        return store_cls(pdir.joinpath(*parts), ensure=ensure)

    mall: dict[str, MutableMapping] = {
        "characters": at(CharactersStore, "assets", "characters"),
        "environments": at(EnvironmentsStore, "assets", "environments"),
        "props": at(PropsStore, "assets", "props"),
        "voices": at(VoicesStore, "assets", "voices"),
        "styles": at(StylesStore, "assets", "styles"),
        "sounds": at(SoundsStore, "assets", "sounds"),
        # A performer's takes of the scene's lines, with their provenance
        # (`an voices import`, an.audio.recorded): what the `recorded` TTS
        # provider hands the pipeline instead of synthesizing.
        "recordings": at(RecordingsStore, "assets", "recordings"),
        # Opaque scene sources a whole-shot renderer runs as they are: a Manim
        # shot's `options.source` is a key here (`assets/sources/<key>.py`).
        "sources": at(SourcesStore, "assets", "sources"),
        "scenes": ScenesStore(pdir, scene_file),
        "audio": at(AudioArtifactStore, "artifacts", "audio"),
        "visemes": at(VisemeArtifactStore, "artifacts", "visemes"),
        # Which take of a best-of-N line was kept, and why (an.audio.takes):
        # the record a re-render trusts instead of re-rolling.
        "takes": at(TakesArtifactStore, "artifacts", "takes"),
        # The per-shot mp4 ARCHIVE, keyed by the author's shot id: written on
        # every render, read by nothing (pillar 11). The cache is below.
        "shots": at(ShotArtifactStore, "artifacts", "shots"),
        # The content-keyed shot cache (ADR 0004): a `lacing.ArtifactStore`,
        # `catalog/<key>.json` + `blobs/<sha256>`. `render_project` reads it.
        "shot_cache": shot_cache_store(pdir / "artifacts" / "shot_cache"),
        # Transcripts an earlier step produced, named where a transcript file
        # is (`artifact:transcripts/<key>`, an#493): a `lacing.ArtifactStore`.
        "transcripts": transcripts_store(pdir / "artifacts" / "transcripts"),
        "previews": at(PreviewArtifactStore, "artifacts", "previews"),
        # Contact sheets of opaque renders (a Manim shot's settled beats), keyed
        # by the PNG's sha256 so cached provenance keeps pointing at them.
        "contact_sheets": at(ContactSheetStore, "artifacts", "contact_sheets"),
        # Derived, content-keyed: what a clock-owning renderer measured of its
        # content (a Manim shot's length) and its raw picture. Never authored
        # data — the scene keeps what its author wrote (an#279).
        "measurements": at(MeasurementStore, "artifacts", "measurements"),
        "pictures": at(PictureStore, "artifacts", "pictures"),
        # What each render found, keyed like its output (`render_reports/main.json`).
        "render_reports": at(RenderReportStore, "artifacts", "render_reports"),
        "output": at(OutputStore, "output"),
        # The SubRip sidecar of each delivered film (an#175), in the SAME
        # directory as the mp4 so `output/main.srt` sits beside
        # `output/main.mp4` — where a player looks for it. The two stores
        # share a folder but not a key space: each lists only its extension.
        "captions": at(CaptionsStore, "output"),
        "decisions": at(DecisionLogStore, ".an", "decisions.jsonl"),
        # The asset library's lockfile (`assets.lock.json` at the project root,
        # ADR 0005, an#240): `<store>/<key>` -> the library version checked out
        # there. The single source of truth for a pin; `an validate` checks the
        # scene's `library:` fields against it. Opening it creates nothing.
        "library_lock": ProjectLock(pdir),
    }
    mall.update(overrides)
    return mall
