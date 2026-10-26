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
    """``text`` as the report of a command that failed."""
    return CommandReport(text, exit_code=exit_code)


def exit_code_of(result: object) -> int:
    """The status a command's return value asks for: 0 for anything that is not a
    :class:`CommandReport`."""
    return getattr(result, "exit_code", 0) if isinstance(result, CommandReport) else 0
