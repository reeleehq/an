# an.verify.layout

LayoutLintVerifier — cheap pre-render checks on the IR.

Runs the same semantic checks as `an.ir.validate.validate_semantic` plus a
few that need a render context (do dialogue lines fit in their shot’s
duration? is the scene’s total duration consistent with the timeline?).

Deliberately runs on the IR alone (RenderResult=None is fine), so the
orchestrator can call it BEFORE rendering and skip a costly render if the
IR is broken.

### Classes

| [`LayoutLintVerifier`](#an.verify.layout.LayoutLintVerifier)()   | Cheap IR-only verifier.   |
|-------------------------------------------------------------------------|---------------------------|

### *class* an.verify.layout.LayoutLintVerifier

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Cheap IR-only verifier. Implements `Verifier`.
