"""Cutout-style 2D animation backend.

The render path is ``compile.py`` → ``serialize.py`` → ``render.py`` →
``runtime.js`` (the browser evaluates and applies every frame). The Python
evaluation chain (``easing``/``channel``/``clip``/``timeline``) is kept as the
executable spec of the runtime's semantics, pinned by node-backed parity tests;
application lives in ``runtime.js`` alone (an#86).

>>> from an.adapters.cutout import CutoutRenderer, compile_shot
>>> CutoutRenderer().name
'cutout'
"""

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.serialize import (
    AnimationClipJSON,
    AssetJSON,
    AssetResolutionJSON,
    AssetsJSON,
    ChannelJSON,
    CutoutSceneJSON,
    KeyframeJSON,
    NodeJSON,
    PlacedClipJSON,
    TimelineJSON,
    TrackJSON,
    VisualJSON,
)
from an.adapters.cutout.render import CutoutRenderer, CutoutRenderError

__all__ = [
    "CutoutRenderer",
    "CutoutRenderError",
    "compile_shot",
    "CutoutSceneJSON",
    "NodeJSON",
    "VisualJSON",
    "AnimationClipJSON",
    "ChannelJSON",
    "KeyframeJSON",
    "TimelineJSON",
    "TrackJSON",
    "PlacedClipJSON",
    "AssetsJSON",
    "AssetJSON",
    "AssetResolutionJSON",
]


# Register on import so `an.adapters.list_renderers()` finds it.
from an.adapters._base import register_renderer as _register_renderer

_register_renderer(CutoutRenderer())

# ...and how its shots are keyed in the shot cache (ADR 0004). Registered here,
# beside the renderer, so the core `an.build` never names a backend.
from an.adapters.cutout.cache_key import cutout_environment, cutout_shot_inputs
from an.build.keys import register_shot_keyer as _register_shot_keyer

_register_shot_keyer(
    "cutout",
    cutout_shot_inputs,
    environment=cutout_environment,
    renderer_type=CutoutRenderer,
)

# The versions of the vocabulary entries a shot names (ADR 0003 decision 2,
# an#248): a preset whose meaning changes re-renders the shots that play it.
from an.semantic.digest import register_vocabulary_key_part as _register_vocabulary_part

_register_vocabulary_part("cutout")
