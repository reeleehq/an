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
| [`EXIT_POLICY`](#an.cli_status.EXIT_POLICY)         | How each core command ends when it fails.         |

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

### an.cli_status.EXIT_POLICY *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'bench': 'failed: refused arguments (an#559)', 'bench-compare': 'failed: --strict and a bad answer (an#559)', 'bench-mutants': 'failed: a survivor, an unknown name, rot; 130 interrupted', 'cache gc': 'refuses', 'cache info': '0', 'check': '0: every backend is optional to some project; the render refuses', 'credits': '0: the inventory; the gate is \`validate --strict-assets\`', 'init': 'refuses', 'iterate': 'failed: the instruction was not applied (an#480)', 'library checkout': 'refuses', 'library find': '0: no match is an answer', 'library kit': 'refuses', 'library promote': 'refuses', 'library publish': 'refuses; an unknown licence is recorded on purpose: 0', 'library reindex': 'refuses', 'library retire': 'refuses', 'library sheet': 'refuses', 'library show': 'refuses', 'library vocabulary': '0', 'preview': 'refuses', 'probe': 'refuses', 'props contract': '0', 'props validate': 'failed: a FAILED report (an#480)', 'render': 'failed: an error finding, though the mp4 exists (an#559)', 'sounds add': 'refuses', 'sync': 'refuses: a scene file that is not there; drift is a warning', 'validate': 'failed: a FAILED report (an#480)', 'voices audition': 'refuses (VoiceDesignError)', 'voices cast': 'refuses (VoiceDesignError)', 'voices choose': 'refuses (VoiceDesignError)', 'voices design': 'refuses (VoiceDesignError)', 'voices import': 'refuses (RecordedVoicesError)', 'voices list': '0: no voices is an answer', 'voices reroll': 'failed: no dialogue line matches (an#559)', 'voices rescore': 'failed: no dialogue line matches (an#559)', 'world show': 'refuses'}*

How each core command ends when it fails. A new command must take a line
here (`tests/test_cli_exit_status.py` holds the list complete), so “it prints a
failure and exits 0” is a decision someone wrote down, never a default.
`failed`: a report that says it failed carries exit 1 (an.cli_status);
`refuses`: a bad argument or state raises (`SystemExit`, a `_REFUSALS`
type), exit 1; `0`: always 0, for the reason given.

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
