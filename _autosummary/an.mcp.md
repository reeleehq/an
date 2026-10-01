# an.mcp

The `an` MCP server: a curated, generated surface over the vocabulary and the capability registry.

ADR 0003 decision 6. The tools are plain functions in [`an.mcp.tools`](an.mcp.tools.md#module-an.mcp.tools)
(queries, typed edits, long work as start/poll jobs; the bench stays CLI-only);
[`an.mcp.server.mk_server()`](an.mcp.server.md#an.mcp.server.mk_server) projects them with `py2mcp`. The MCP stack is
an optional extra and is imported only when a server is built:

```default
pip install 'an[mcp]'
python -m an.mcp            # serve over stdio
```

`import an` never imports this package, and importing it imports no MCP
dependency (a test holds both).

```pycon
>>> from an.mcp import TOOL_REFS
>>> "an.mcp.tools:vocabulary" in TOOL_REFS
True
```

### Module Attributes

| [`TOOL_REFS`](#an.mcp.TOOL_REFS)   | The tools as `module:function` references (`py2mcp.mk_mcp_from_refs`'s input).   |
|--------------------------------------------------------------|----------------------------------------------------------------------------------|

### an.mcp.TOOL_REFS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('an.mcp.tools:vocabulary', 'an.mcp.tools:vocabulary_entry', 'an.mcp.tools:scene_schema', 'an.mcp.tools:validate_scene', 'an.mcp.tools:describe_character', 'an.mcp.tools:applicable_methods', 'an.mcp.tools:why_not_method', 'an.mcp.tools:apply_patch', 'an.mcp.tools:start_render', 'an.mcp.tools:job_status')*

The tools as `module:function` references (`py2mcp.mk_mcp_from_refs`’s input).

### Modules

| [`server`](an.mcp.server.md#module-an.mcp.server)   | Build and serve the `an` MCP server with `py2mcp` (the `an[mcp]` extra).                           |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| [`tools`](an.mcp.tools.md#module-an.mcp.tools)     | The curated MCP tools: plain functions over the vocabulary, the capability registry and a project. |
