"""Project mall: a dict of dol-backed `MutableMapping` stores.

The mall is the unit of persistence in an. Every long-lived state — assets
(characters, props, environments, voices, styles, sounds), the scene file pair, intermediate
artifacts (audio, viseme tracks, per-shot mp4s, the content-keyed shot cache),
final output and its caption sidecar, and the agent's
decision log — is keyed inside a store. Stores are dol-backed so the same call
sites work against filesystem, SQLite, S3, etc.

>>> import tempfile
>>> from pathlib import Path
>>> with tempfile.TemporaryDirectory() as d:
...     mall = build_project_mall(d, ensure=True)
...     sorted(mall.keys()) == [
...         'audio', 'captions', 'characters', 'decisions', 'environments',
...         'output', 'previews', 'props', 'scenes', 'shot_cache', 'shots',
...         'sounds', 'styles', 'visemes', 'voices',
...     ]
True
"""

from __future__ import annotations

from pathlib import Path
from typing import MutableMapping

from an.stores.characters import CharactersStore
from an.stores.decisions import DecisionLogStore
from an.stores.environments import EnvironmentsStore
from an.stores.props import PropsStore
from an.stores.scenes import ScenesStore
from an.stores.sounds import SoundsStore
from an.stores.styles import StylesStore
from an.stores.voices import VoicesStore
from an.build.shot_cache import shot_cache_store
from an.stores.artifacts import (
    AudioArtifactStore,
    CaptionsStore,
    OutputStore,
    PreviewArtifactStore,
    ShotArtifactStore,
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
    "ShotArtifactStore",
    "PreviewArtifactStore",
    "OutputStore",
    "DecisionLogStore",
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
            "ir",
            "artifacts/audio",
            "artifacts/visemes",
            "artifacts/shots",
            "artifacts/previews",
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
        "scenes": ScenesStore(pdir),
        "audio": AudioArtifactStore(pdir / "artifacts" / "audio"),
        "visemes": VisemeArtifactStore(pdir / "artifacts" / "visemes"),
        # The per-shot mp4 ARCHIVE, keyed by the author's shot id: written on
        # every render, read by nothing (pillar 11). The cache is below.
        "shots": ShotArtifactStore(pdir / "artifacts" / "shots"),
        # The content-keyed shot cache (ADR 0004): a `lacing.ArtifactStore`,
        # `catalog/<key>.json` + `blobs/<sha256>`. `render_project` reads it.
        "shot_cache": shot_cache_store(pdir / "artifacts" / "shot_cache"),
        "previews": PreviewArtifactStore(pdir / "artifacts" / "previews"),
        "output": OutputStore(pdir / "output"),
        # The SubRip sidecar of each delivered film (an#175), in the SAME
        # directory as the mp4 so `output/main.srt` sits beside
        # `output/main.mp4` — where a player looks for it. The two stores
        # share a folder but not a key space: each lists only its extension.
        "captions": CaptionsStore(pdir / "output"),
        "decisions": DecisionLogStore(pdir / ".an" / "decisions.jsonl"),
    }
    mall.update(overrides)
    return mall
