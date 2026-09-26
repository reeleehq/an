# an.verify.human

HumanInTheLoopVerifier — opens the rendered mp4 and asks for approval.

Only useful in interactive sessions. Skips silently when there’s no TTY (CI,
agent contexts). The orchestrator can detect the skip via the report’s
informational finding.

### Classes

| [`HumanInTheLoopVerifier`](#an.verify.human.HumanInTheLoopVerifier)(\*[, prompt])   | Open the mp4, prompt the user to approve.   |
|-----------------------------------------------------------------------------------------|---------------------------------------------|

### *class* an.verify.human.HumanInTheLoopVerifier(, prompt='Approve render? [y/N/r=reject]: ')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Open the mp4, prompt the user to approve. Implements `Verifier`.
