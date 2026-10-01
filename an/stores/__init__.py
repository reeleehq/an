"""Project mall: a dict of dol-backed `MutableMapping` stores.

The mall is the unit of persistence in an. Every long-lived state — assets
(characters, props, environments, voices, styles, sounds), the scene file pair, intermediate
artifacts (audio, viseme tracks, best-of-N take records, per-shot mp4s, the
content-keyed shot cache),
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
...         'pictures', 'previews', 'props', 'render_reports', 'scenes',
...         'shot_cache', 'shots', 'sounds', 'sources', 'styles', 'takes',
...         'visemes', 'voices',
...     ]
True
"""

from __future__ import annotations

from pathlib import Path
from typing import MutableMapping

from an.stores.characters import CharactersStore
from an.stores.decisions import DecisionLogStore
from an.stores.environments import EnvironmentsStore
from an.stores.library_lock import ProjectLock
from an.stores.props import PropsStore
from an.stores.scenes import ScenesStore
from an.stores.sources import SourcesStore
from an.stores.sounds import SoundsStore
from an.stores.styles import StylesStore
from an.stores.voices import VoicesStore
from an.build.shot_cache import shot_cache_store
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
    "CharactersStore",
    "EnvironmentsStore",
    "VoicesStore",
    "StylesStore",
    "PropsStore",
    "ScenesStore",
    "SoundsStore",
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
]


def build_project_mall(
    project_dir: str | Path, *, ensure: bool = False, **overrides: MutableMapping
) -> dict[str, MutableMapping]:
    """Build the standard project mall over ``project_dir``.

    Pass ``ensure=True`` to create the per-store directories on disk if they
    don't exist. Pass keyword overrides to swap in alternate stores (e.g. an
    in-memory `dict` for tests).
    """
    pdir = Path(project_dir)
    if ensure:
        for sub in (
            "assets/characters",
            "assets/environments",
            "assets/props",
            "assets/voices",
            "assets/styles",
            "assets/sounds",
            "assets/sources",
            "ir",
            "artifacts/audio",
            "artifacts/visemes",
            "artifacts/takes",
            "artifacts/shots",
            "artifacts/previews",
            "artifacts/contact_sheets",
            "artifacts/measurements",
            "artifacts/pictures",
            "artifacts/render_reports",
            "output",
            ".an",
        ):
            (pdir / sub).mkdir(parents=True, exist_ok=True)

    mall: dict[str, MutableMapping] = {
        "characters": CharactersStore(pdir / "assets" / "characters"),
        "environments": EnvironmentsStore(pdir / "assets" / "environments"),
        "props": PropsStore(pdir / "assets" / "props"),
        "voices": VoicesStore(pdir / "assets" / "voices"),
        "styles": StylesStore(pdir / "assets" / "styles"),
        "sounds": SoundsStore(pdir / "assets" / "sounds"),
        # Opaque scene sources a whole-shot renderer runs as they are: a Manim
        # shot's `options.source` is a key here (`assets/sources/<key>.py`).
        "sources": SourcesStore(pdir / "assets" / "sources"),
        "scenes": ScenesStore(pdir),
        "audio": AudioArtifactStore(pdir / "artifacts" / "audio"),
        "visemes": VisemeArtifactStore(pdir / "artifacts" / "visemes"),
        # Which take of a best-of-N line was kept, and why (an.audio.takes):
        # the record a re-render trusts instead of re-rolling.
        "takes": TakesArtifactStore(pdir / "artifacts" / "takes"),
        # The per-shot mp4 ARCHIVE, keyed by the author's shot id: written on
        # every render, read by nothing (pillar 11). The cache is below.
        "shots": ShotArtifactStore(pdir / "artifacts" / "shots"),
        # The content-keyed shot cache (ADR 0004): a `lacing.ArtifactStore`,
        # `catalog/<key>.json` + `blobs/<sha256>`. `render_project` reads it.
        "shot_cache": shot_cache_store(pdir / "artifacts" / "shot_cache"),
        "previews": PreviewArtifactStore(pdir / "artifacts" / "previews"),
        # Contact sheets of opaque renders (a Manim shot's settled beats), keyed
        # by the PNG's sha256 so cached provenance keeps pointing at them.
        "contact_sheets": ContactSheetStore(pdir / "artifacts" / "contact_sheets"),
        # Derived, content-keyed: what a clock-owning renderer measured of its
        # content (a Manim shot's length) and its raw picture. Never authored
        # data — the scene keeps what its author wrote (an#279).
        "measurements": MeasurementStore(pdir / "artifacts" / "measurements"),
        "pictures": PictureStore(pdir / "artifacts" / "pictures"),
        # What each render found, keyed like its output (`render_reports/main.json`).
        "render_reports": RenderReportStore(pdir / "artifacts" / "render_reports"),
        "output": OutputStore(pdir / "output"),
        # The SubRip sidecar of each delivered film (an#175), in the SAME
        # directory as the mp4 so `output/main.srt` sits beside
        # `output/main.mp4` — where a player looks for it. The two stores
        # share a folder but not a key space: each lists only its extension.
        "captions": CaptionsStore(pdir / "output"),
        "decisions": DecisionLogStore(pdir / ".an" / "decisions.jsonl"),
        # The asset library's lockfile (`assets.lock.json` at the project root,
        # ADR 0005, an#240): `<store>/<key>` -> the library version checked out
        # there. The single source of truth for a pin; `an validate` checks the
        # scene's `library:` fields against it. Opening it creates nothing.
        "library_lock": ProjectLock(pdir),
    }
    mall.update(overrides)
    return mall
