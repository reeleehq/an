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
    an voices design <project> --library accent=irish,gender=male --no-design   # library candidates by accent (free)
    an voices audition <project> --voices jerry_voice   # the character's lines in each option's voice (billed)
    an voices choose <project> jerry_voice B --by noel   # the writer's pick becomes the voice_id (recorded)
    an voices cast <project> paul_voice <voice_id> --by noel   # a voice picked by hand, recorded the same way
    an voices import <project> takes/ --transcript takes/ --license cc-by-4.0 --recorded-by "J. Doe"
                                                    # a performer's recording becomes the voice (an#490)

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
from an.ir.sync import DEFAULT_SCENE_FILE

__all__ = ["browse_voices", "format_voices", "retake", "import_recorded"]

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
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Release the recorded takes of the lines of ``project`` containing ``line``.

    The plain-function core of ``an voices rescore`` / ``an voices reroll``: see
    :func:`an.audio.pipeline.retake_lines`. ``tts`` must be the provider the
    line is rendered with (its takes are keyed by it). ``scene`` names another
    scene file of the project (``scene.studio.md``, an#554). When no dialogue
    line contains ``line`` nothing was released, and the CLI exits 1 (an#559).
    """
    from an.audio.pipeline import lines_matching, retake_lines
    from an.cli_status import failed
    from an.project import load

    proj = load(project, scene_file=scene)
    messages = retake_lines(proj.scene, proj.mall, line, tts=make(tts), rescore=rescore)
    text = "\n".join(messages)
    return text if lines_matching(proj.scene, line) else failed(text)


def _rescore(
    project: str,
    line: str,
    tts: str = DEFAULT_BROWSE_PROVIDER,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Re-choose the take of each line containing LINE from its cached takes, with
    the current scorer, at the next render (nothing billed while the takes are cached).

    project: the project directory
    line: words of the dialogue line (case-insensitive substring)
    tts: the TTS provider the line is rendered with
    scene: the scene file to read, inside the project (default scene.md; for example scene.studio.md)
    """
    return retake(project, line, rescore=True, tts=tts, scene=scene)


def _reroll(
    project: str,
    line: str,
    tts: str = DEFAULT_BROWSE_PROVIDER,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Synthesize new takes for each line containing LINE at the next render, and
    keep the best (billed: the render prints the cost before the first request).

    project: the project directory
    line: words of the dialogue line (case-insensitive substring)
    tts: the TTS provider the line is rendered with
    scene: the scene file to read, inside the project (default scene.md; for example scene.studio.md)
    """
    return retake(project, line, rescore=False, tts=tts, scene=scene)


_rescore.__name__ = "rescore"  # `an voices rescore`
_reroll.__name__ = "reroll"  # `an voices reroll`


def design(
    project: str,
    voices: str = "",
    model: str = "",
    only_chosen: bool = False,
    library: str = "",
    no_design: bool = False,
    library_limit: int = 0,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Design voice options from each voice document's notes (ElevenLabs Voice Design,
    billed) and/or list candidates from the shared voice library by accent, gender and
    age (free): samples to artifacts/voice_samples/, the options to artifacts/voice_options/.
    Play the samples to the writer (or `an voices audition` first), then `an voices choose`.

    project: the project directory
    voices: comma-separated voice refs (default: every voice document with notes or a library query)
    model: the voice-design model (default: eleven_ttv_v3)
    only_chosen: save only the chosen option as an account voice, at `choose` (previews expire: choose soon)
    library: a shared-library query for every voice without its own `library` key: accent=irish,gender=male,age=middle_aged
    no_design: skip the designed previews: library candidates only, nothing billed
    library_limit: at most this many library candidates per voice (default 8)
    scene: the scene file whose lines a voice without sample_text speaks (default scene.md; for example scene.studio.md)
    """
    from an.audio.voice_design import (
        DFLT_DESIGN_MODEL,
        DFLT_LIBRARY_LIMIT,
        default_library,
        design_project_voices,
    )

    refs = [r.strip() for r in voices.split(",") if r.strip()] or None
    manifest = design_project_voices(
        project,
        refs,
        model_id=model or DFLT_DESIGN_MODEL,
        persist=not only_chosen,
        library=default_library(),  # the CLI opts in: a document's `library` key is honoured
        library_query=library or None,
        library_limit=library_limit or DFLT_LIBRARY_LIMIT,
        design=not no_design,
        scene_file=scene,
    )
    lines = []
    for ref, entry in manifest.items():
        for o in entry["options"]:
            about = f"  {o['name']}: {o['about']}" if o.get("kind") == "library" else ""
            lines.append(
                f"{ref} {o['option']}: {o.get('sample_path') or '(no sample)'}"
                + (f"  (voice_id {o['voice_id']})" if o.get("voice_id") else "")
                + about
            )
    return "\n".join(lines)


def audition(
    project: str,
    voices: str = "",
    options: str = "",
    tts: str = "",
    redo: bool = False,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """An audition reel per option: the character's own lines from the scene, spoken in
    that option's voice with the film's TTS provider, the voice document's model, settings
    and effects (its cues as audio tags), 0.6 s apart, to artifacts/voice_auditions/ (a scene other than scene.md: its own subfolder)
    (billed: one request per line per option; the whole bill is printed first, and a reel
    already made for the same lines, voice and settings is not made again). Play them to
    the writer, then `an voices choose`.

    project: the project directory
    voices: comma-separated voice refs (default: every voice with options)
    options: comma-separated option labels to audition (default: all, e.g. A,B,L1)
    tts: the TTS provider the film renders with (default: elevenlabs)
    redo: make every reel again even when nothing changed (billed again)
    scene: the scene file whose lines the reels speak (default scene.md; for example scene.studio.md)
    """
    from an.audio.voice_design import (
        AUDITION_PATH_KEY,
        DESIGN_PROVIDER,
        _scene_record,
        audition_project_voices,
    )
    from an.ir.sync import resolve_scene_file

    refs = [r.strip() for r in voices.split(",") if r.strip()] or None
    labels = [o.strip() for o in options.split(",") if o.strip()] or None
    manifests = audition_project_voices(
        project,
        refs,
        options=labels,
        tts=make_tts(tts or DESIGN_PROVIDER),
        redo=redo,
        scene_file=scene,
    )
    sf = resolve_scene_file(project, scene)
    return "\n".join(
        f"{ref} {o['option']}: {record[AUDITION_PATH_KEY]}"
        for ref, entry in manifests.items()
        for o in entry["options"]
        if (record := _scene_record(o, sf)) and record.get(AUDITION_PATH_KEY)
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


def cast(
    project: str, voice: str, voice_id: str = "", by: str = "", provider: str = ""
) -> str:
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


def import_recorded(
    project: str,
    audio: str,
    transcript: str = "",
    speaker: str = "",
    speakers: str = "",
    shot: str = "",
    voice: str = "",
    denoise: bool = False,
    license: str = "",
    recorded_by: str = "",
    transcriber: str = "",
    diarize: bool = False,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Import a performer's recording as the voice of its lines: each line is cut out,
    matched to the scene's dialogue (or added to --shot), stored with its provenance,
    and the speaker's character speaks with it — nothing synthesized, nothing billed.

    project: the project directory
    audio: the take(s): a file, a directory, a glob, or comma-separated files (one take with several lines, or one file per line)
    transcript: SRT / WebVTT / TextGrid / word JSON (timed: no transcribing) or plain `speaker: text` lines; a directory pairs by stem
    speaker: the one character every take belongs to
    speakers: label=character pairs for a transcript's or diarizer's labels and file stems, e.g. spk_0=carl,spk_1=ned
    shot: the shot new lines go into (takes matching no scene line)
    voice: the recorded voice document to bind (default <speaker>_recorded)
    denoise: clean each file first (ffmpeg afftdn)
    license: REQUIRED — the licence or permission code you vouch for (cc0-1.0, cc-by-4.0, all-rights-reserved, unknown)
    recorded_by: who recorded the take (the performer), for the credits
    transcriber: the scribed backend when a take must be transcribed (default: scribed's default)
    diarize: ask the transcriber for speaker labels (map them with --speakers)
    scene: the scene file whose lines the takes voice (default scene.md; for example scene.studio.md)
    """
    from an.audio.recorded import DFLT_DENOISE, import_recordings

    report = import_recordings(
        project,
        audio,
        transcript=transcript or None,
        speaker=speaker or None,
        speakers=speakers or None,
        shot=shot or None,
        voice=voice or None,
        denoise=DFLT_DENOISE if denoise else None,
        license=license or None,
        recorded_by=recorded_by or None,
        transcriber=transcriber or None,
        diarize=diarize,
        scene_file=scene,
    )
    return str(report)


import_recorded.__name__ = "import"  # `an voices import`


_dispatch_funcs: list[Callable[..., Any]] = [
    _list,
    _rescore,
    _reroll,
    design,
    audition,
    choose,
    cast,
    import_recorded,
]
