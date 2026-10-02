"""The cut-out backend's old package: the stage moved to :mod:`an.stage` (an#247).

The render path is ``an.stage.compile`` -> ``an.stage.serialize`` ->
``an.stage.render`` (the stage engine, driven by the core frame stage) ->
``runtime.js``. Every module that moved keeps a LIVE alias here
(``an.adapters.cutout.render`` is ``an.stage.render`` for reading and for
rebinding, :func:`an._shims.alias_module`). ``coarticulate`` and ``gaze`` moved to ``cutan`` (an#225; live aliases with a
warning). What stays here is the
timing re-exports (``channel``, ``clip``, ``timeline``).

The names this package used to export are resolved LAZILY, on first access:
importing ``an.adapters.cutout.coarticulate`` from the stage's compiler must not
load the stage back through this ``__init__``.

>>> from an.adapters.cutout import CutoutRenderer, compile_shot
>>> CutoutRenderer().name
'cutout'
"""

from __future__ import annotations

from importlib import import_module

#: Each exported name -> the module it now lives in.
_EXPORTS: dict[str, str] = {
    "CutoutRenderer": "an.stage.render",
    "CutoutRenderError": "an.stage.render",
    "compile_shot": "an.stage.compile",
    **{
        name: "an.stage.serialize"
        for name in (
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
        )
    },
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name in _EXPORTS:
        return getattr(import_module(_EXPORTS[name]), name)
    if not name.startswith("_"):
        # A submodule reached as an attribute (`an.adapters.cutout.render`),
        # which the eager imports of the old package used to make available.
        try:
            return import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"{__name__}.{name}":
                raise
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
