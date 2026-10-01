# an.mcp.server

Build and serve the `an` MCP server with `py2mcp` (the `an[mcp]` extra).

`py2mcp` is imported inside [`mk_server()`](#an.mcp.server.mk_server), never at module level, so this
module imports without the extra (CI collects every module’s doctests with no
extras installed) and a missing extra is a typed, install-hinting error.

### Module Attributes

| [`SERVER_INSTRUCTIONS`](#an.mcp.server.SERVER_INSTRUCTIONS)   | What a client is told about this server (the model-facing description).   |
|------------------------------------------------------------------------|---------------------------------------------------------------------------|

### Functions

| [`main`](#an.mcp.server.main)()                              | Serve over stdio (`python -m an.mcp`).                                                                                         |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| [`mk_server`](#an.mcp.server.mk_server)(\*[, name, instructions]) | The FastMCP server with one tool per [`an.mcp.TOOL_REFS`](an.mcp.html.md#an.mcp.TOOL_REFS) entry. |

### Exceptions

| [`MCPExtraMissingError`](#an.mcp.server.MCPExtraMissingError)   | The MCP server needs the `an[mcp]` extra (`py2mcp`).   |
|-------------------------------------------------------------------------|--------------------------------------------------------|

### *exception* an.mcp.server.MCPExtraMissingError

Bases: [`ImportError`](https://docs.python.org/3/builtins/exceptions.html#ImportError)

The MCP server needs the `an[mcp]` extra (`py2mcp`).

### an.mcp.server.SERVER_INSTRUCTIONS *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'Structured animation with \`an\`. Read the vocabulary (\`vocabulary\`) before writing any name into a scene: every action kind, preset, camera move, easing and method is registered and versioned, and a name outside it fails validation. Ask what a character can do (\`describe_character\`, \`applicable_methods\`, \`why_not_method\`) before requesting a method. Edit with \`apply_patch\` (dry-run first); render with \`start_render\` and poll \`job_status\`.'*

What a client is told about this server (the model-facing description).

### an.mcp.server.main()

Serve over stdio (`python -m an.mcp`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.mcp.server.mk_server(, name='an', instructions='Structured animation with \`an\`. Read the vocabulary (\`vocabulary\`) before writing any name into a scene: every action kind, preset, camera move, easing and method is registered and versioned, and a name outside it fails validation. Ask what a character can do (\`describe_character\`, \`applicable_methods\`, \`why_not_method\`) before requesting a method. Edit with \`apply_patch\` (dry-run first); render with \`start_render\` and poll \`job_status\`.')

The FastMCP server with one tool per [`an.mcp.TOOL_REFS`](an.mcp.html.md#an.mcp.TOOL_REFS) entry.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)
