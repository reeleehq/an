"""Verification protocol — same interface for human, lint, vision-LM, MoVer.

``StyleLintVerifier`` is imported on first use, not here: ``an.verify.style`` is
also a script (``python -m an.verify.style``), and a package that imports the
module it is about to run as ``__main__`` makes ``runpy`` warn that it is
already in ``sys.modules``.
"""

from an.verify._base import (
    Verifier,
    Finding,
    VerificationReport,
    Severity,
)
from an.verify.layout import LayoutLintVerifier
from an.verify.human import HumanInTheLoopVerifier
from an.verify.media_quality import MediaQualityVerifier
from an.verify.vision import VisionLMVerifier

__all__ = [
    "Verifier",
    "Finding",
    "VerificationReport",
    "Severity",
    "LayoutLintVerifier",
    "HumanInTheLoopVerifier",
    "MediaQualityVerifier",
    "VisionLMVerifier",
    "StyleLintVerifier",
]


def __getattr__(name: str):
    if name == "StyleLintVerifier":
        from an.verify.style import StyleLintVerifier

        return StyleLintVerifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
