# an.cli_status

A command’s report that also says how the command ended (an#480).

The CLI commands in [`an.tools`](an.tools.html.md#module-an.tools) return their report as a string and the
dispatcher prints it. A string cannot say “this is a failure”, so a command that
reported `FAILED` still exited 0 and no script or CI step could tell it from a
pass. [`CommandReport`](#an.cli_status.CommandReport) is a `str` that carries an `exit_code`: Python
callers, the MCP surface and the doctests see the same text as before, and the
dispatcher (`an.__main__._printing`) exits with the code after printing it.

```pycon
>>> failed("validation: FAILED").exit_code, str(failed("validation: FAILED"))
(1, 'validation: FAILED')
>>> exit_code_of("a plain report"), exit_code_of(failed("x", exit_code=2))
(0, 2)
```

### Module Attributes

| [`FAILURE_EXIT_CODE`](#an.cli_status.FAILURE_EXIT_CODE)   | The status of a command that reports a failure.   |
|----------------------------------------------------------------------|---------------------------------------------------|

### Functions

| [`exit_code_of`](#an.cli_status.exit_code_of)(result)          | The status a command's return value asks for: 0 for anything that is not a [`CommandReport`](#an.cli_status.CommandReport).   |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| [`failed`](#an.cli_status.failed)(text, \*[, exit_code]) | `text` as the report of a command that failed.                                                                                               |

### Classes

| [`CommandReport`](#an.cli_status.CommandReport)(text, \*[, exit_code])   | A command's text with the exit status it asks the CLI to end with.   |
|-----------------------------------------------------------------------------------------|----------------------------------------------------------------------|

### *class* an.cli_status.CommandReport(text, , exit_code=0)

Bases: [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

A command’s text with the exit status it asks the CLI to end with.

* **Return type:**
  [*CommandReport*](#an.cli_status.CommandReport)

### an.cli_status.FAILURE_EXIT_CODE *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

The status of a command that reports a failure.

### an.cli_status.exit_code_of(result)

The status a command’s return value asks for: 0 for anything that is not a
[`CommandReport`](#an.cli_status.CommandReport).

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### an.cli_status.failed(text, , exit_code=1)

`text` as the report of a command that failed.

Call it LAST: any string operation on the result (`+`, an f-string,
`.join`, `.strip()`) returns a plain `str` and the exit code is gone.

* **Return type:**
  [`CommandReport`](#an.cli_status.CommandReport)
