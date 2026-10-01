"""The ``an`` MCP server: a curated, generated surface over the vocabulary and the capability registry.

ADR 0003 decision 6. The tools are plain functions in :mod:`an.mcp.tools`
(queries, typed edits, long work as start/poll jobs; the bench stays CLI-only);
:func:`an.mcp.server.mk_server` projects them with ``py2mcp``. The MCP stack is
an optional extra and is imported only when a server is built::

    pip install 'an[mcp]'
    python -m an.mcp            # serve over stdio

``import an`` never imports this package, and importing it imports no MCP
dependency (a test holds both).

>>> from an.mcp import TOOL_REFS
>>> "an.mcp.tools:vocabulary" in TOOL_REFS
True
"""

from __future__ import annotations

from an.mcp.tools import TOOLS

#: The tools as ``module:function`` references (``py2mcp.mk_mcp_from_refs``'s input).
TOOL_REFS: tuple[str, ...] = tuple(f"{f.__module__}:{f.__name__}" for f in TOOLS)

__all__ = ["TOOLS", "TOOL_REFS"]
