"""Verification protocol — same interface for human, lint, vision-LM, MoVer.

Every public name here is imported on first use (PEP 562), not when the package
is: :mod:`an.verify.constraints`, the constraint lints ``an validate`` runs
(an#497), is imported by ``an.ir`` on every ``import an``, and the media verifier
behind this package pulls in numpy, which the validate path has no use for.
``StyleLintVerifier`` moved to ``cutan`` with the cut-out style lint (an#225);
``an.verify.style`` is also a script (``python -m an.verify.style``), and a
package that imports the module it is about to run as ``__main__`` makes
``runpy`` warn that it is already in ``sys.modules``.
"""

from importlib import import_module

from an._shims import moved_names as _moved_names

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

_moved = _moved_names(
    __name__, {"StyleLintVerifier": "cutan.verify.style:StyleLintVerifier"}
)


def __getattr__(name: str):
    home = _HOMES.get(name)
    if home is None:
        return _moved(name)
    value = getattr(import_module(home), name)
    globals()[name] = value  # once: the next access is an ordinary attribute
    return value
