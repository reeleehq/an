"""Renderer adapters — facades over backends (the stage, Manim, Remotion, whiteboard).

The Renderer Protocol and registry live in `_base`. The core's own optional
backends are imported here so they self-register on package import. The stage
(``an.stage``, the cut-out renderer) sits behind the import firewall, so it is
named by MODULE and imported the first time the registry is asked anything
(an#247). Backends with missing
system deps still register but their ``render()`` raises a clear error;
``can_render(shot)`` continues to work for routing decisions.
"""

from an.adapters._base import (
    Renderer,
    RendererRegistry,
    RenderContext,
    RenderResult,
    register_lazy_renderer,
    register_renderer,
    get_renderer,
    list_renderers,
)

# The stage registers `cutout` (claiming `stage` too) when imported: a string,
# not an import, so `import an` loads no backend.
register_lazy_renderer("cutout", "an.stage.render")

# Phase 6: register the other backends. They're skeleton-implementations in
# v0.1 — render() raises clearly if the backend isn't usable yet.
from an.adapters.manim_adapter import ManimRenderer
from an.adapters.remotion_adapter import RemotionRenderer
from an.adapters.whiteboard import WhiteboardRenderer

register_renderer(ManimRenderer())
register_renderer(RemotionRenderer())
register_renderer(WhiteboardRenderer())

__all__ = [
    "Renderer",
    "RendererRegistry",
    "RenderContext",
    "RenderResult",
    "register_renderer",
    "get_renderer",
    "list_renderers",
    "register_lazy_renderer",
    "ManimRenderer",
    "RemotionRenderer",
    "WhiteboardRenderer",
]
