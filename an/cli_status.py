"""A command's report that also says how the command ended (an#480).

The CLI commands in :mod:`an.tools` return their report as a string and the
dispatcher prints it. A string cannot say "this is a failure", so a command that
reported ``FAILED`` still exited 0 and no script or CI step could tell it from a
pass. :class:`CommandReport` is a ``str`` that carries an ``exit_code``: Python
callers, the MCP surface and the doctests see the same text as before, and the
dispatcher (``an.__main__._printing``) exits with the code after printing it.

>>> failed("validation: FAILED").exit_code, str(failed("validation: FAILED"))
(1, 'validation: FAILED')
>>> exit_code_of("a plain report"), exit_code_of(failed("x", exit_code=2))
(0, 2)
"""

from __future__ import annotations

#: The status of a command that reports a failure.
FAILURE_EXIT_CODE: int = 1


class CommandReport(str):
    """A command's text with the exit status it asks the CLI to end with."""

    exit_code: int = 0

    def __new__(cls, text: str, *, exit_code: int = 0) -> "CommandReport":
        self = super().__new__(cls, text)
        self.exit_code = exit_code
        return self


def failed(text: str, *, exit_code: int = FAILURE_EXIT_CODE) -> CommandReport:
    """``text`` as the report of a command that failed.

    Call it LAST: any string operation on the result (``+``, an f-string,
    ``.join``, ``.strip()``) returns a plain ``str`` and the exit code is gone.
    """
    return CommandReport(text, exit_code=exit_code)


def exit_code_of(result: object) -> int:
    """The status a command's return value asks for: 0 for anything that is not a
    :class:`CommandReport`."""
    return result.exit_code if isinstance(result, CommandReport) else 0


#: How each core command ends when it fails. A new command must take a line
#: here (`tests/test_cli_exit_status.py` holds the list complete), so "it prints a
#: failure and exits 0" is a decision someone wrote down, never a default.
#: ``failed``: a report that says it failed carries exit 1 (an.cli_status);
#: ``refuses``: a bad argument or state raises (`SystemExit`, a `_REFUSALS`
#: type), exit 1; ``0``: always 0, for the reason given.
EXIT_POLICY: dict[str, str] = {
    "init": "refuses",
    "validate": "failed: a FAILED report (an#480)",
    "sync": "refuses: a scene file that is not there; drift is a warning",
    "check": "0: every backend is optional to some project; the render refuses",
    "render": "failed: an error finding, though the mp4 exists (an#559)",
    "iterate": "failed: the instruction was not applied (an#480)",
    "preview": "refuses",
    "probe": "refuses",
    "credits": "0: the inventory; the gate is `validate --strict-assets`",
    "bench": "failed: refused arguments (an#559)",
    "bench-compare": "failed: --strict and a bad answer (an#559)",
    "bench-mutants": "failed: a survivor, an unknown name, rot; 130 interrupted",
    "voices list": "0: no voices is an answer",
    "voices rescore": "failed: no dialogue line matches (an#559)",
    "voices reroll": "failed: no dialogue line matches (an#559)",
    "voices design": "refuses (VoiceDesignError)",
    "voices audition": "refuses (VoiceDesignError)",
    "voices choose": "refuses (VoiceDesignError)",
    "voices cast": "refuses (VoiceDesignError)",
    "voices import": "refuses (RecordedVoicesError)",
    "library publish": "refuses; an unknown licence is recorded on purpose: 0",
    "library kit": "refuses",
    "library find": "0: no match is an answer",
    "library vocabulary": "0",
    "library show": "refuses",
    "library checkout": "refuses",
    "library promote": "refuses",
    "library retire": "refuses",
    "library sheet": "refuses",
    "library reindex": "refuses",
    "cache info": "0",
    "cache gc": "refuses",
    "sounds add": "refuses",
    "props validate": "failed: a FAILED report (an#480)",
    "props contract": "0",
    "world show": "refuses",
}
