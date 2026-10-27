"""Verification protocol — same interface for human, lint, vision-LM, MoVer.

Every public name here is imported on first use (PEP 562), not when the package
is: :mod:`an.verify.constraints`, the constraint lints ``an validate`` runs
(an#497), is imported by ``an.ir`` on every ``import an``, and the media verifier
behind this package pulls in numpy, which the validate path has no use for.
The cut-out style lint is ``cutan.verify.style`` (an#225).
"""

from importlib import import_module

__all__ = [
    "Verifier",
    "Finding",
    "VerificationReport",
    "Severity",
    "LayoutLintVerifier",
    "HumanInTheLoopVerifier",
    "MediaQualityVerifier",
    "VisionLMVerifier",
]

#: Where each public name lives; its module is imported when the name is first asked for.
_HOMES: dict[str, str] = {
    "Verifier": "an.verify._base",
    "Finding": "an.verify._base",
    "VerificationReport": "an.verify._base",
    "Severity": "an.verify._base",
    "LayoutLintVerifier": "an.verify.layout",
    "HumanInTheLoopVerifier": "an.verify.human",
    "MediaQualityVerifier": "an.verify.media_quality",
    "VisionLMVerifier": "an.verify.vision",
}


def __getattr__(name: str):
    home = _HOMES.get(name)
    if home is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(home), name)
    globals()[name] = value  # once: the next access is an ordinary attribute
    return value
