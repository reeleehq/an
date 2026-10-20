"""``an voices ...`` — browse a TTS provider's voices from the shell (an#209).

Thin string-typed wrappers dispatched by typer the way ``an character ...`` is;
the business logic is :func:`browse_voices`, a plain function over the
provider factories.

    an voices list --provider elevenlabs
    an voices list --provider elevenlabs --search british
    an voices list --provider mac_say
    an voices rescore <project> "He did not ask"    # re-choose a line's take from its cached takes
    an voices reroll <project> "He did not ask"     # synthesize new takes for it (billed)
    an voices design <project>                      # design options from each voice's notes (billed)
    an voices choose <project> jerry_voice B --by noel   # the writer's pick becomes the voice_id (recorded)
    an voices cast <project> paul_voice <voice_id> --by noel   # a voice picked by hand, recorded the same way

The ``voice_id`` column is what a ``voices``-store document's ``voice_id`` takes.
``rescore`` and ``reroll`` are the only ways a recorded best-of-N take is
replaced (:func:`an.audio.pipeline.retake_lines`); the next ``an render`` does
the choosing, and prints what it will bill first.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any

from an.audio.providers import make_tts
from an.audio.tts import TTSProvider, VoiceMeta

__all__ = ["browse_voices", "format_voices", "retake"]

#: The provider ``an voices list`` browses when none is named.
DEFAULT_BROWSE_PROVIDER = "elevenlabs"


def browse_voices(
    provider: str = DEFAULT_BROWSE_PROVIDER,
    *,
    search: str | None = None,
    make: Callable[[str], TTSProvider] = make_tts,
) -> list[VoiceMeta]:
    """The voices ``provider`` exposes, optionally filtered by ``search``.

    A provider whose ``list_voices`` takes ``search`` (ElevenLabs) filters on
    its server; for the others the filter is a case-insensitive substring over
    the name, id and labels.

    >>> from an.audio.tts import VoiceMeta
    >>> class Fake:
    ...     name = "fake"
    ...     def list_voices(self):
    ...         return [VoiceMeta("v1", "Ada", "fake"), VoiceMeta("v2", "Bob", "fake")]
    >>> [v.name for v in browse_voices("fake", search="ad", make=lambda _: Fake())]
    ['Ada']
    """
    tts = make(provider)
    if "search" in inspect.signature(tts.list_voices).parameters:
        return list(tts.list_voices(search=search))  # type: ignore[call-arg]
    voices = list(tts.list_voices())
    if search:
        needle = search.lower()
        voices = [v for v in voices if needle in _haystack(v)]
    return voices


def format_voices(voices: Iterable[VoiceMeta]) -> str:
    """One line per voice: ``voice_id  name  (labels)``.

    >>> from an.audio.tts import VoiceMeta
    >>> print(format_voices([VoiceMeta("abc", "Ada", "x", extra={"labels": {"accent": "british"}})]))
    abc  Ada  (accent=british)
    """
    lines = []
    for v in voices:
        labels = (v.extra or {}).get("labels") or {}
        tail = ", ".join(f"{k}={val}" for k, val in sorted(labels.items()) if val)
        lines.append(f"{v.voice_id}  {v.name}" + (f"  ({tail})" if tail else ""))
    return "\n".join(lines)


def _haystack(v: VoiceMeta) -> str:
    labels = (v.extra or {}).get("labels") or {}
    return " ".join([v.voice_id, v.name, *map(str, labels.values())]).lower()


def _list(provider: str = DEFAULT_BROWSE_PROVIDER, search: str = "") -> str:
    """List a TTS provider's voices; the first column is the voice_id to put in
    a voices-store document.

    provider: TTS provider name — elevenlabs (needs ELEVEN_API_KEY), mac_say, offline
    search: filter by name, description or labels (e.g. british, deep, female)
    """
    voices = browse_voices(provider, search=search or None)
    if not voices:
        return f"no voices from {provider!r}" + (
            f" matching {search!r}" if search else " (is its API key set?)"
        )
    return format_voices(voices)


_list.__name__ = "list"  # the CLI verb: `an voices list`


def retake(
    project: str,
    line: str,
    *,
    rescore: bool = False,
    tts: str = DEFAULT_BROWSE_PROVIDER,
    make: Callable[[str], TTSProvider] = make_tts,
) -> str:
    """Release the recorded takes of the lines of ``project`` containing ``line``.

    The plain-function core of ``an voices rescore`` / ``an voices reroll``: see
    :func:`an.audio.pipeline.retake_lines`. ``tts`` must be the provider the
    line is rendered with (its takes are keyed by it).
    """
    from an.audio.pipeline import retake_lines
    from an.project import load

    proj = load(project)
    messages = retake_lines(proj.scene, proj.mall, line, tts=make(tts), rescore=rescore)
    return "\n".join(messages)


def _rescore(project: str, line: str, tts: str = DEFAULT_BROWSE_PROVIDER) -> str:
    """Re-choose the take of each line containing LINE from its cached takes, with
    the current scorer, at the next render (nothing billed while the takes are cached).

    project: the project directory
    line: words of the dialogue line (case-insensitive substring)
    tts: the TTS provider the line is rendered with
    """
    return retake(project, line, rescore=True, tts=tts)


def _reroll(project: str, line: str, tts: str = DEFAULT_BROWSE_PROVIDER) -> str:
    """Synthesize new takes for each line containing LINE at the next render, and
    keep the best (billed: the render prints the cost before the first request).

    project: the project directory
    line: words of the dialogue line (case-insensitive substring)
    tts: the TTS provider the line is rendered with
    """
    return retake(project, line, rescore=False, tts=tts)


_rescore.__name__ = "rescore"  # `an voices rescore`
_reroll.__name__ = "reroll"  # `an voices reroll`


def design(
    project: str, voices: str = "", model: str = "", only_chosen: bool = False
) -> str:
    """Design voice options from each voice document's notes (ElevenLabs Voice Design,
    billed): samples to artifacts/voice_samples/, the options to artifacts/voice_options/.
    Play the samples to the writer, then run `an voices choose`.

    project: the project directory
    voices: comma-separated voice refs (default: every voice document with notes)
    model: the voice-design model (default: eleven_ttv_v3)
    only_chosen: save only the chosen option as an account voice, at `choose` (previews expire: choose soon)
    """
    from an.audio.voice_design import DFLT_DESIGN_MODEL, design_project_voices

    refs = [r.strip() for r in voices.split(",") if r.strip()] or None
    manifest = design_project_voices(
        project, refs, model_id=model or DFLT_DESIGN_MODEL, persist=not only_chosen
    )
    return "\n".join(
        f"{ref} {o['option']}: {o['sample_path']}"
        + (f"  (voice_id {o['voice_id']})" if o["voice_id"] else "")
        for ref, entry in manifest.items()
        for o in entry["options"]
    )


def choose(project: str, voice: str, option: str, by: str = "") -> str:
    """Make OPTION (A, B, C...) of `an voices design` the voice's voice_id, and
    record who chose it (chosen_by, chosen_at): a render refuses a voice written
    in words that nobody chose (--strict-assets), or lists it as provisional.

    project: the project directory
    voice: the voice ref (the voice document's name)
    option: the option label the writer chose
    by: who chose: the writer's name. The default, your login name, records only that someone ran this
    """
    from an.audio.voice_design import choose_project_voice

    doc = choose_project_voice(project, voice, option, by=by or None)
    return (
        f"voices/{voice}: voice_id {doc['voice_id']} (option {option.upper()}, "
        f"chosen by {doc['chosen_by']})"
    )


def cast(project: str, voice: str, voice_id: str = "", by: str = "", provider: str = "") -> str:
    """Record a voice picked by hand as the writer's choice (chosen_by, chosen_at),
    without a design round: the document's own voice_id, or VOICE_ID from
    `an voices list`. Nothing is billed.

    project: the project directory
    voice: the voice ref (the voice document's name)
    voice_id: the provider's voice id to cast (default: the one the document names)
    by: who chose: the writer's name (default: your login name)
    provider: the TTS provider the id belongs to (default: keep the document's)
    """
    from an.audio.voice_design import cast_project_voice

    doc = cast_project_voice(
        project, voice, voice_id or None, by=by or None, provider=provider or None
    )
    return f"voices/{voice}: voice_id {doc['voice_id']} (cast by {doc['chosen_by']})"


_dispatch_funcs: list[Callable[..., Any]] = [_list, _rescore, _reroll, design, choose, cast]
