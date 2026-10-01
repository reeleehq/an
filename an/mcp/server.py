"""Build and serve the ``an`` MCP server with ``py2mcp`` (the ``an[mcp]`` extra).

``py2mcp`` is imported inside :func:`mk_server`, never at module level, so this
module imports without the extra (CI collects every module's doctests with no
extras installed) and a missing extra is a typed, install-hinting error.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "MCPExtraMissingError",
    "SERVER_INSTRUCTIONS",
    "SERVER_NAME",
    "main",
    "mk_server",
]

SERVER_NAME: str = "an"

#: What a client is told about this server (the model-facing description).
SERVER_INSTRUCTIONS: str = (
    "Structured animation with `an`. Read the vocabulary (`vocabulary`) before "
    "writing any name into a scene: every action kind, preset, camera move, "
    "easing and method is registered and versioned, and a name outside it fails "
    "validation. Ask what a character can do (`describe_character`, "
    "`applicable_methods`, `why_not_method`) before requesting a method. Edit "
    "with `apply_patch` (dry-run first); render with `start_render` and poll "
    "`job_status`."
)


class MCPExtraMissingError(ImportError):
    """The MCP server needs the ``an[mcp]`` extra (``py2mcp``)."""


def mk_server(
    *, name: str = SERVER_NAME, instructions: str = SERVER_INSTRUCTIONS
) -> Any:
    """The FastMCP server with one tool per :data:`an.mcp.TOOL_REFS` entry."""
    try:
        from py2mcp import mk_mcp_from_refs
    except ImportError as e:
        raise MCPExtraMissingError(
            "the an MCP server needs py2mcp: pip install 'an[mcp]'"
        ) from e
    from an.genres import load
    from an.mcp import TOOL_REFS

    load()
    return mk_mcp_from_refs(TOOL_REFS, name=name, instructions=instructions)


def main() -> None:  # pragma: no cover — a long-running stdio server
    """Serve over stdio (``python -m an.mcp``)."""
    mk_server().run()
