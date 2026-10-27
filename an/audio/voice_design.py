"""Design a project's voices from their written notes, then let the writer choose.

A voice document (``assets/voices/<ref>.json``) may carry the voice in words:
``notes`` (age, accent, pitch, pace, attitude) and, optionally,
``sample_text`` (what the samples say). Voice design turns those words into
candidate voices the writer can LISTEN to, and the writer's choice becomes the
document's ``voice_id``. That is how a regional accent gets cast by the one
person who can hear it (a local ear for a local accent), with nobody else
picking from a stock library.

Two steps, both plain functions over injected stores:

- :func:`design_voice_options`: per voice, ask a *designer* for previews of its
  notes speaking its sample text, store each preview's audio in ``samples`` and
  return the options manifest (``{ref: {"notes", "sample_text", "design_model",
  "options": [{"option": "A", "generated_voice_id", "voice_id", "sample",
  "duration_s"}]}}``). With ``persist=True`` (the default) every preview is saved
  as a durable provider voice at once, because a provider's previews expire; with
  ``persist=False`` only the chosen one is, later (fewer voices in the account,
  but a choice must come before the previews expire).
- :func:`choose_voice_option`: the ``voice_id`` of the chosen option (saving it
  as a voice first when it was not persisted).
- :func:`choose_in_entry`: the choice made in one manifest entry (that
  ``voice_id``, the designed voice it replaces retired, who chose it and
  when), returning the voice document and the replaced voice: the step every
  chooser shares, the CLI's :func:`choose_project_voice` and a connector's alike.

**Two more routes to a voice** (an#485). Design from notes can miss a
regional accent entirely (every design of "rural Limerick Irish" came out
English). So a voice document may also carry a ``library`` query (``{"accent":
"irish", "gender": "male", "age": "middle_aged"}``), or ``an voices design
--library accent=irish,gender=male`` gives one to every voice: the provider's
shared voice library, human-tagged by region, is searched and its candidates
join the same manifest as ``L1``, ``L2``, ... options (:class:`ElevenLabsVoiceLibrary`
behind the ``library=`` seam; a search and a preview cost nothing). And
``an voices audition`` makes an **audition reel** per option: the character's
own lines from the scene, spoken with the film's TTS provider and model, the
line's cues as audio tags, 0.6 s apart (:func:`audition_voice_options`, the
``tts=`` seam), so the writer hears what the film will sound like, accent
drift of the render model included. The writer's ear is the judge: an accent
classifier was measured and cannot screen TTS accents (an#485).

**A choice is recorded, and a render needs one** (an#486). A voice written in
words (``notes``) is cast by the writer, nobody else: ``an voices choose``
writes ``chosen_by`` and ``chosen_at`` beside the ``voice_id``
(:func:`record_choice`), and a voice document that has ``notes`` but no
recorded choice is a render finding, refused under ``--strict-assets`` before
anything is synthesized (:func:`voice_casting_problem`). A timing draft may
speak a stand-in voice only with an explicit ``provisional`` (``true``, or a
string saying why), which every render report lists.

The project-level forms, :func:`design_project_voices` and
:func:`choose_project_voice`, keep the manifest in
``artifacts/voice_options/<ref>.json``, the samples in
``artifacts/voice_samples/<ref>_<option>.mp3``, and write the chosen ``voice_id``
(and ``provider``) into the voice document. ``an voices design`` and ``an voices
choose`` are their CLI.

The designer is a seam (``designer=``): by default
:class:`ElevenLabsVoiceDesigner` (ElevenLabs Voice Design through the
``elevenlabs`` SDK an's ElevenLabs TTS already uses; key in ``ELEVEN_API_KEY``).
voxy's ``ElevenLabsSpeechModel`` is a drop-in (``designer=voxy.get_speech_model("elevenlabs")``),
not the default because voxy brings torch. Anything with these two methods works::

    design_voice_previews(description, *, text, model_id) -> [preview]   # preview.generated_voice_id, .audio, .duration_s
    design_voice(description, *, preview, name) -> profile                # profile.segment is the voice id

Designing is billed by the provider; nothing here is called by a render.

>>> class Fake:
...     def design_voice_previews(self, description, *, text=None, model_id=None):
...         from types import SimpleNamespace as N
...         return [N(generated_voice_id=f"g{i}", audio=b"ID3", duration_s=1.0) for i in range(2)]
...     def design_voice(self, description, *, preview, name):
...         from types import SimpleNamespace as N
...         return N(segment="v-" + getattr(preview, "generated_voice_id", preview))
>>> samples = {}
>>> notes = "A man in his fifties from rural Yorkshire, warm and unhurried."
>>> manifest = design_voice_options({"jerry": {"notes": notes}}, samples=samples, designer=Fake())
>>> [(o["option"], o["voice_id"], o["sample"]) for o in manifest["jerry"]["options"]]
[('A', 'v-g0', 'jerry_A'), ('B', 'v-g1', 'jerry_B')]
>>> sorted(samples)
['jerry_A', 'jerry_B']
>>> choose_voice_option(manifest["jerry"], "B", designer=Fake())
'v-g1'
"""

from __future__ import annotations

import copy
import io
import re
import wave
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from an.ir.sync import DEFAULT_SCENE_FILE

__all__ = [
    "ElevenLabsVoiceDesigner",
    "ElevenLabsVoiceLibrary",
    "LibraryVoice",
    "VoiceDesignError",
    "AuditionJob",
    "announce_auditions",
    "audition_key",
    "audition_project_voices",
    "audition_voice_options",
    "plan_auditions",
    "run_auditions",
    "cast_project_voice",
    "VoiceChoice",
    "carry_over",
    "choose_in_entry",
    "choose_project_voice",
    "choose_voice_option",
    "default_chooser",
    "default_designer",
    "default_library",
    "design_project_voices",
    "design_voice_options",
    "designable_voices",
    "library_query_of",
    "library_voice_options",
    "parse_library_query",
    "provisional_reason",
    "record_choice",
    "sample_text_from_lines",
    "sample_text_of",
    "voice_casting",
    "voice_casting_problem",
]

#: The key, in a voice document, holding the voice in words.
NOTES_KEY = "notes"
#: The key, in a voice document, holding what the designed samples say.
SAMPLE_TEXT_KEY = "sample_text"
#: ElevenLabs Voice Design's model (the expressive one, which reads accents best).
DFLT_DESIGN_MODEL = "eleven_ttv_v3"
#: ElevenLabs' bounds on a voice description and a preview text (characters).
NOTES_LENGTH = (20, 1000)
SAMPLE_TEXT_LENGTH = (100, 1000)
#: Seconds one provider request may take.
DFLT_REQUEST_TIMEOUT_S = 120
#: The provider a designed voice belongs to (written into the voice document).
DESIGN_PROVIDER = "elevenlabs"
#: Labels of the options, in order (past the alphabet: numbers).
OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#: Where the project-level forms keep their records, under the project root.
OPTIONS_DIR = Path("artifacts") / "voice_options"
SAMPLES_DIR = Path("artifacts") / "voice_samples"
#: What a choice writes into the voice document (an#486): who chose the
#: ``voice_id`` and when (UTC, ISO 8601). A voice with ``notes`` and no
#: ``chosen_by`` is not cast: nobody the writer trusts picked it.
CHOSEN_BY_KEY = "chosen_by"
CHOSEN_AT_KEY = "chosen_at"
#: On an option of a voice's options manifest: its ``voice_id`` was saved by a
#: choice (the option was not persisted when designed), so a later choice of
#: another option retires it (:func:`choose_in_entry`, an#549).
SAVED_BY_CHOICE_KEY = "saved_by_choice"
#: A voice a render may speak although nobody chose it: a timing draft. Any
#: truthy value; a string says why, and the render report repeats it.
PROVISIONAL_KEY = "provisional"
#: The verbs that cast a voice, named by every refusal.
CASTING_VERBS = (
    "`an voices design` (options from its notes or a library query), "
    "`an voices audition` (the lines in each option's voice), then "
    "`an voices choose <option> --by <writer>` (the pick, recorded as chosen_by), "
    "or `an voices cast <voice_id> --by <writer>` for a voice picked by hand "
    "(`an voices list`)"
)
#: The key, in a voice document, holding a library search: the provider's
#: shared-library filters (``accent``, ``gender``, ``age``, ``language``,
#: ``search``), e.g. ``{"accent": "irish", "gender": "male", "age": "middle_aged"}``.
LIBRARY_KEY = "library"
#: The filters a library query may carry (the ElevenLabs shared library's).
LIBRARY_FILTERS: tuple[str, ...] = ("accent", "gender", "age", "language", "search")
#: How many library candidates a query yields by default.
DFLT_LIBRARY_LIMIT = 8
#: Labels of library options (``L1``, ``L2``, ...), after the designed ``A``, ``B``, ...
LIBRARY_LABEL_PREFIX = "L"
#: Seconds of silence between two lines of an audition reel.
AUDITION_GAP_S = 0.6
#: Where the project-level audition reels go, under the project root.
AUDITIONS_DIR = Path("artifacts") / "voice_auditions"
#: An audition reel is 16-bit mono WAV at the effects chain's rate.
AUDITION_SAMPLE_RATE = (
    44100  # = an.audio.effects.EFFECT_SAMPLE_RATE (asserted in tests)
)
#: The option keys an audition writes: the reel's key in the reels store, how
#: many lines it holds, and the content key it was made under (voice, lines,
#: options, effects, gap, provider) — a reel is never made twice for the same key.
AUDITION_KEY = "audition"
AUDITION_LINES_KEY = "audition_lines"
AUDITION_CONTENT_KEY = "audition_key"
#: Where the manifest keeps each scene's own record of an option's reel (an#571):
#: ``{scene file name: {audition, audition_lines, audition_key, audition_path}}``.
#: The reel of one scene lives in its own folder
#: (:meth:`an.ir.sync.SceneFile.per_scene_dir`), so two scenes' reels coexist and
#: each scene's skip test reads its own record; the fields at the top of the
#: option stay the latest reel made.
AUDITIONS_KEY = "auditions"
AUDITION_PATH_KEY = "audition_path"
AUDITION_RECORD_KEYS = (
    AUDITION_KEY,
    AUDITION_LINES_KEY,
    AUDITION_CONTENT_KEY,
    AUDITION_PATH_KEY,
)
#: ``announce`` default: a line on stderr (the pipeline's own), so a billed
#: call is never silent unless the caller passes ``None``.
_STDERR = object()


class VoiceDesignError(ValueError):
    """A voice that cannot be designed or chosen (no notes, an unknown option, ...)."""


class ElevenLabsVoiceDesigner:
    """ElevenLabs Voice Design through the ``elevenlabs`` SDK (what an's ElevenLabs
    TTS already uses): the default designer, with voxy's two-method shape.

    api_key: defaults to ``ELEVEN_API_KEY`` / ``ELEVENLABS_API_KEY``
    client_factory: ``api_key -> client``; tests inject a fake so nothing is billed
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client_factory: Any = None,
        timeout_s: float = DFLT_REQUEST_TIMEOUT_S,
    ) -> None:
        import os

        self.api_key = (
            api_key
            or os.environ.get("ELEVEN_API_KEY")
            or os.environ.get("ELEVENLABS_API_KEY")
        )
        self.client_factory = client_factory
        self.timeout_s = timeout_s

    @property
    def _request_options(self) -> dict:
        return {"timeout_in_seconds": int(self.timeout_s)}

    def _client(self):
        if not self.api_key:
            raise VoiceDesignError(
                "voice design needs an ElevenLabs key: set ELEVEN_API_KEY"
            )
        if self.client_factory is not None:
            return self.client_factory(self.api_key)
        try:
            from elevenlabs.client import ElevenLabs  # type: ignore
        except ImportError as e:  # pragma: no cover - depends on the environment
            raise VoiceDesignError(
                "voice design needs the elevenlabs package: pip install elevenlabs"
            ) from e
        return ElevenLabs(api_key=self.api_key)

    def design_voice_previews(
        self,
        description: str,
        *,
        text: str | None = None,
        model_id: str = DFLT_DESIGN_MODEL,
    ):
        """Previews (``generated_voice_id``, ``audio`` mp3 bytes, ``duration_s``) of ``description``."""
        import base64
        from types import SimpleNamespace

        kwargs = {"text": text} if text else {"auto_generate_text": True}
        response = self._client().text_to_voice.design(
            voice_description=description,
            model_id=model_id,
            request_options=self._request_options,
            **kwargs,
        )
        return [
            SimpleNamespace(
                generated_voice_id=p.generated_voice_id,
                audio=base64.b64decode(p.audio_base_64),
                duration_s=getattr(p, "duration_secs", None),
            )
            for p in response.previews
        ]

    def design_voice(self, description: str, *, preview: Any, name: str):
        """Save ``preview`` (or its ``generated_voice_id``) as an account voice; ``.segment`` is its id."""
        from types import SimpleNamespace

        generated_id = getattr(preview, "generated_voice_id", preview)
        voice = self._client().text_to_voice.create(
            voice_name=name,
            voice_description=description,
            generated_voice_id=generated_id,
            request_options=self._request_options,
        )
        return SimpleNamespace(segment=voice.voice_id)

    def delete_voice(self, voice_id: str) -> None:
        """Remove a saved voice from the account (a choice the writer replaced)."""
        self._client().voices.delete(voice_id, request_options=self._request_options)


def default_designer(*, api_key: str | None = None) -> ElevenLabsVoiceDesigner:
    """The designer used when none is given: :class:`ElevenLabsVoiceDesigner`."""
    return ElevenLabsVoiceDesigner(api_key=api_key)


@dataclass(frozen=True)
class LibraryVoice:
    """One candidate from a provider's shared voice library."""

    voice_id: str
    name: str = ""
    description: str = ""
    accent: str | None = None
    age: str | None = None
    gender: str | None = None
    language: str | None = None
    preview_url: str | None = None
    #: The account that shares it (ElevenLabs ``public_owner_id``).
    owner_id: str | None = None


class ElevenLabsVoiceLibrary:
    """ElevenLabs' shared voice library through the ``elevenlabs`` SDK
    (``voices.get_shared``): voices other accounts published, human-tagged by
    accent, age and gender, with a region often in the description ("Cork",
    "west of Ireland"). A search and a preview download cost no credit; speaking
    a library voice at render time is billed like any other.

    api_key: defaults to ``ELEVEN_API_KEY`` / ``ELEVENLABS_API_KEY``
    client_factory: ``api_key -> client``; tests inject a fake so nothing is called
    fetch: ``url -> bytes`` for a preview (default: a plain HTTP GET)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client_factory: Any = None,
        fetch: Callable[[str], bytes] | None = None,
        timeout_s: float = DFLT_REQUEST_TIMEOUT_S,
    ) -> None:
        import os

        self.api_key = (
            api_key
            or os.environ.get("ELEVEN_API_KEY")
            or os.environ.get("ELEVENLABS_API_KEY")
        )
        self.client_factory = client_factory
        self.fetch = fetch
        self.timeout_s = timeout_s

    def _client(self):
        if not self.api_key:
            raise VoiceDesignError(
                "the voice library needs an ElevenLabs key: set ELEVEN_API_KEY"
            )
        if self.client_factory is not None:
            return self.client_factory(self.api_key)
        try:
            from elevenlabs.client import ElevenLabs  # type: ignore
        except ImportError as e:  # pragma: no cover - depends on the environment
            raise VoiceDesignError(
                "the voice library needs the elevenlabs package: pip install elevenlabs"
            ) from e
        return ElevenLabs(api_key=self.api_key)

    def search(
        self, *, limit: int = DFLT_LIBRARY_LIMIT, **filters: Any
    ) -> list[LibraryVoice]:
        """The shared voices matching ``filters`` (:data:`LIBRARY_FILTERS`), at most ``limit``."""
        unknown = sorted(set(filters) - set(LIBRARY_FILTERS))
        if unknown:
            raise VoiceDesignError(
                f"unknown library filter(s) {unknown}; the library takes {list(LIBRARY_FILTERS)}"
            )
        kwargs = {k: v for k, v in filters.items() if v not in (None, "")}
        page = self._client().voices.get_shared(
            page_size=max(1, min(int(limit), 100)),
            request_options={"timeout_in_seconds": int(self.timeout_s)},
            **kwargs,
        )
        out = []
        for v in getattr(page, "voices", None) or ():
            out.append(
                LibraryVoice(
                    voice_id=getattr(v, "voice_id", ""),
                    name=getattr(v, "name", "") or "",
                    description=getattr(v, "description", "") or "",
                    accent=getattr(v, "accent", None),
                    age=getattr(v, "age", None),
                    gender=getattr(v, "gender", None),
                    language=getattr(v, "language", None),
                    preview_url=getattr(v, "preview_url", None),
                    owner_id=getattr(v, "public_owner_id", None),
                )
            )
            if len(out) >= limit:
                break
        return out

    def preview(self, voice: LibraryVoice) -> bytes | None:
        """The voice's own preview clip (mp3 bytes), or ``None`` when it has none."""
        if not voice.preview_url:
            return None
        if self.fetch is not None:
            return self.fetch(voice.preview_url)
        from urllib.request import urlopen

        with urlopen(voice.preview_url, timeout=self.timeout_s) as r:  # noqa: S310 - the provider's own CDN link
            return r.read()

    def add(self, voice_id: str, owner_id: str, *, name: str) -> str:
        """Add the shared voice to the account under ``name``; returns its id.

        A production spoke shared voices by their id directly; ElevenLabs also
        documents adding one (``voices.share``) and a ``voice_not_found`` on a
        library id means it needs this. Free; not called by anything else here.
        """
        voice = self._client().voices.share(
            owner_id,
            voice_id,
            new_name=name,
            request_options={"timeout_in_seconds": int(self.timeout_s)},
        )
        return getattr(voice, "voice_id", None) or voice_id


def default_library(*, api_key: str | None = None) -> ElevenLabsVoiceLibrary:
    """The library used when none is given: :class:`ElevenLabsVoiceLibrary`."""
    return ElevenLabsVoiceLibrary(api_key=api_key)


def parse_library_query(text: str | Mapping | None) -> dict[str, str] | None:
    """A library query from its CLI spelling, ``accent=irish,gender=male``
    (a mapping passes through; empty is ``None``).

    >>> parse_library_query("accent=irish, gender=male")
    {'accent': 'irish', 'gender': 'male'}
    >>> parse_library_query("") is None, parse_library_query({"age": "young"})
    (True, {'age': 'young'})
    >>> parse_library_query("irish")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    an.audio.voice_design.VoiceDesignError: library query 'irish': write it as key=value pairs (accent, gender, age, language, search)
    """
    if text is None:
        return None
    if isinstance(text, Mapping):
        return {str(k): str(v) for k, v in text.items()} or None
    if not str(text).strip():
        return None
    out: dict[str, str] = {}
    for part in str(text).split(","):
        key, sep, value = part.partition("=")
        if not sep or not key.strip() or not value.strip():
            raise VoiceDesignError(
                f"library query {text!r}: write it as key=value pairs ({', '.join(LIBRARY_FILTERS)})"
            )
        if key.strip() not in LIBRARY_FILTERS:
            raise VoiceDesignError(
                f"library query {text!r}: unknown filter {key.strip()!r}; the library takes {list(LIBRARY_FILTERS)}"
            )
        out[key.strip()] = value.strip()
    return out or None


def library_query_of(
    doc: Mapping | None, default: Mapping | None = None
) -> dict[str, str] | None:
    """The document's own ``library`` query, else ``default``, else ``None``.

    >>> library_query_of({"library": {"accent": "irish"}}, {"accent": "scottish"})
    {'accent': 'irish'}
    >>> library_query_of({}, {"accent": "scottish"}), library_query_of({}) is None
    ({'accent': 'scottish'}, True)
    """
    own = doc.get(LIBRARY_KEY) if isinstance(doc, Mapping) else None
    if isinstance(own, Mapping) and own:
        unknown = sorted(set(map(str, own)) - set(LIBRARY_FILTERS))
        if unknown:
            raise VoiceDesignError(
                f"{LIBRARY_KEY!r} on the voice document: unknown filter(s) {unknown}; "
                f"the library takes {list(LIBRARY_FILTERS)}"
            )
        return {str(k): str(v) for k, v in own.items()}
    if isinstance(own, str) and own.strip():
        return parse_library_query(own)
    return parse_library_query(default) if default else None


def library_voice_options(
    query: Mapping[str, Any],
    *,
    samples: MutableMapping[str, bytes],
    ref: str,
    library: Any = None,
    limit: int = DFLT_LIBRARY_LIMIT,
) -> list[dict]:
    """The library candidates for ``query`` as manifest options ``L<n>``, each
    with its preview in ``samples`` (``<ref>_L<n>``) when the library has one
    (``sample`` is ``None`` otherwise), and the sharing account's id
    (``owner_id``) so the voice can be added to the account later.

    >>> class Fake:
    ...     def search(self, *, limit, **f):
    ...         return [LibraryVoice("v1", "Dan", "Cork", accent="irish", preview_url="u", owner_id="o")]
    ...     def preview(self, v):
    ...         return b"ID3"
    >>> samples = {}
    >>> library_voice_options({"accent": "irish"}, samples=samples, ref="j", library=Fake())
    [{'option': 'L1', 'kind': 'library', 'voice_id': 'v1', 'owner_id': 'o', 'name': 'Dan', 'about': 'Cork', 'accent': 'irish', 'age': None, 'gender': None, 'sample': 'j_L1', 'duration_s': None}]
    """
    library = library if library is not None else default_library()
    options = []
    for i, voice in enumerate(library.search(limit=limit, **dict(query))):
        label = f"{LIBRARY_LABEL_PREFIX}{i + 1}"
        key = f"{ref}_{label}"
        audio = library.preview(voice)
        if audio:
            samples[key] = audio
        options.append(
            {
                "option": label,
                "kind": "library",
                "voice_id": voice.voice_id,
                "owner_id": voice.owner_id,
                "name": voice.name,
                "about": voice.description,
                "accent": voice.accent,
                "age": voice.age,
                "gender": voice.gender,
                "sample": key if audio else None,
                "duration_s": None,
            }
        )
    return options


def _label(i: int) -> str:
    return OPTION_LABELS[i] if i < len(OPTION_LABELS) else str(i + 1)


def _clip(text: str, limit: int) -> str:
    """``text`` cut at the last sentence end (else word) within ``limit`` characters.

    >>> _clip("One. Two three. Four", 12)
    'One.'
    >>> _clip("short", 12)
    'short'
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(". "), head.rfind("? "), head.rfind("! "))
    if cut > 0:
        return head[: cut + 1]
    return head.rsplit(" ", 1)[0]


def sample_text_from_lines(
    lines: Iterable[str], *, limit: int = SAMPLE_TEXT_LENGTH[1]
) -> str | None:
    """A sample text from a voice's own dialogue lines, or ``None`` when they are
    too short for a provider preview (then the provider writes one).

    >>> sample_text_from_lines(["Hi."]) is None
    True
    >>> len(sample_text_from_lines(["That's a big mountain over there, I'd say."] * 5)) >= 100
    True
    """
    text = " ".join(
        re.sub(r"\s+", " ", ln).strip() for ln in lines if ln and ln.strip()
    )
    text = _clip(text, limit)
    return text if len(text) >= SAMPLE_TEXT_LENGTH[0] else None


def designable_voices(
    voices: Mapping[str, Mapping], refs: Iterable[str] | None = None
) -> dict[str, Mapping]:
    """The voice documents (of ``refs``, else all) that carry ``notes``.

    Raise :class:`VoiceDesignError` for a named ref that is missing or has no
    usable notes; skip the unnamed ones silently.

    >>> designable_voices({"a": {"notes": "x" * 30}, "b": {}})
    {'a': {'notes': 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'}}
    """
    named = list(refs) if refs is not None else None
    out: dict[str, Mapping] = {}
    for ref in named if named is not None else sorted(voices):
        doc = voices.get(ref) if ref in voices else None
        problem = _notes_problem(doc)
        if problem is None:
            out[ref] = doc
        elif named is not None:
            raise VoiceDesignError(f"voice {ref!r}: {problem}")
    return out


def _notes_problem(doc: Any) -> str | None:
    if not isinstance(doc, Mapping):
        return "no such voice document"
    notes = doc.get(NOTES_KEY)
    lo, hi = NOTES_LENGTH
    if not isinstance(notes, str) or not notes.strip():
        return f"no {NOTES_KEY!r}: write the voice in words (age, accent, pitch, pace, attitude)"
    if not lo <= len(notes.strip()) <= hi:
        return f"{NOTES_KEY!r} is {len(notes.strip())} characters; the designer takes {lo} to {hi}"
    return None


def sample_text_of(doc: Mapping, fallback: str | None = None) -> str | None:
    """The document's ``sample_text`` (clipped), else ``fallback``."""
    text = doc.get(SAMPLE_TEXT_KEY)
    if isinstance(text, str) and text.strip():
        text = _clip(text.strip(), SAMPLE_TEXT_LENGTH[1])
        return text if len(text) >= SAMPLE_TEXT_LENGTH[0] else fallback
    return fallback


def _voice_id_of(profile: Any) -> str:
    for candidate in (
        getattr(profile, "segment", None),
        getattr(profile, "voice_id", None),
        (getattr(profile, "metadata", None) or {}).get("voice_id"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    raise VoiceDesignError(f"the designer returned no voice id ({profile!r})")


def design_voice_options(
    voices: Mapping[str, Mapping],
    *,
    samples: MutableMapping[str, bytes],
    refs: Iterable[str] | None = None,
    designer: Any = None,
    model_id: str = DFLT_DESIGN_MODEL,
    persist: bool = True,
    name_prefix: str = "an",
    lines_of: Callable[[str], Iterable[str]] | None = None,
    library: Any = None,
    library_query: Mapping | str | None = None,
    library_limit: int = DFLT_LIBRARY_LIMIT,
    design: bool = True,
) -> dict[str, dict]:
    """Design options for each voice with notes, and search the library for
    each voice with a query; return the options manifest.

    voices: ``{ref: voice document}`` (a project's ``voices`` store)
    samples: where each option's audio goes, keyed ``<ref>_<option>`` (mp3 bytes)
    refs: the voices to design (default: every one with ``notes`` or ``library``)
    designer: a two-method designer (default: :func:`default_designer`)
    model_id: the provider's voice-design model
    persist: save every option as a durable voice now (else only the chosen one, later)
    name_prefix: prefix of the saved voices' names in the provider account
    lines_of: ``ref -> that voice's dialogue lines``, for a sample text when the
        document has none (else the provider writes one)
    library: the shared-library seam (:func:`default_library` for the CLI),
        searched for every voice that has a ``library`` query of its own or
        gets ``library_query``. **Opt-in**: with neither ``library`` nor
        ``library_query`` given, a document's ``library`` key is left alone
        and nothing reaches the network — a caller that passed only a
        ``designer`` sees exactly what it saw before.
    library_query: the query for voices without their own (``accent=irish,gender=male``)
    library_limit: at most this many library candidates per voice
    design: with ``False``, no designed previews (library candidates only, nothing billed)

    A voice with ``notes`` gets designed options ``A``, ``B``, ...; a voice with
    a query gets library options ``L1``, ``L2``, ...; one with both gets both in
    one manifest, so the writer compares them on the same page.
    """
    use_library = library is not None or library_query is not None
    if not design and not use_library:
        raise VoiceDesignError(
            "design=False searches the library only: pass a library query "
            "(`--library accent=...`), or drop it to design from notes"
        )

    def query_of(doc: Any) -> dict[str, str] | None:
        if not use_library or not isinstance(doc, Mapping):
            return None
        return library_query_of(doc, library_query)

    named = list(refs) if refs is not None else None
    todo: dict[str, Mapping] = {}
    for ref in named if named is not None else sorted(voices):
        doc = voices.get(ref) if ref in voices else None
        notes_problem = _notes_problem(doc)
        if (design and notes_problem is None) or query_of(doc) is not None:
            todo[ref] = doc
        elif named is not None:
            raise VoiceDesignError(
                f"voice {ref!r}: {notes_problem}"
                + (" (and no library query to search with)" if use_library else "")
            )
    if not todo:
        raise VoiceDesignError(
            f"no voice document has {NOTES_KEY!r}"
            + (f" or a {LIBRARY_KEY!r} query" if use_library else "")
            + ": nothing to design from"
        )
    manifest: dict[str, dict] = {}
    for ref, doc in todo.items():
        notes = (doc.get(NOTES_KEY) or "").strip()
        query = query_of(doc)
        fallback = sample_text_from_lines(lines_of(ref)) if lines_of else None
        text = sample_text_of(doc, fallback)
        options: list[dict] = []
        if design and _notes_problem(doc) is None:
            designer = designer if designer is not None else default_designer()
            previews = designer.design_voice_previews(
                notes, text=text, model_id=model_id
            )
            for i, preview in enumerate(previews):
                label = _label(i)
                key = f"{ref}_{label}"
                samples[key] = preview.audio
                voice_id = (
                    _voice_id_of(
                        designer.design_voice(
                            notes, preview=preview, name=f"{name_prefix} {ref} {label}"
                        )
                    )
                    if persist
                    else None
                )
                options.append(
                    {
                        "option": label,
                        "kind": "designed",
                        "generated_voice_id": preview.generated_voice_id,
                        "voice_id": voice_id,
                        "sample": key,
                        "duration_s": getattr(preview, "duration_s", None),
                    }
                )
        if query is not None:
            options += library_voice_options(
                query, samples=samples, ref=ref, library=library, limit=library_limit
            )
        manifest[ref] = {
            "notes": notes or None,
            "sample_text": text,
            "design_model": model_id if design and notes else None,
            "library": query,
            "name_prefix": name_prefix,
            "options": options,
            "chosen": None,
        }
    return manifest


def choose_voice_option(
    entry: Mapping, option: str, *, ref: str = "", designer: Any = None
) -> str:
    """The provider ``voice_id`` of ``option`` in one voice's manifest ``entry``.

    An option that was not persisted is saved as a voice now (its preview must
    not have expired).
    """
    found = next(
        (o for o in entry.get("options", ()) if o.get("option") == str(option).upper()),
        None,
    )
    if found is None:
        labels = ", ".join(o.get("option", "?") for o in entry.get("options", ()))
        raise VoiceDesignError(
            f"no option {option!r}{f' for {ref!r}' if ref else ''} (options: {labels})"
        )
    if found.get("voice_id"):
        return found["voice_id"]
    if not found.get("generated_voice_id"):
        raise VoiceDesignError(
            f"option {found['option']!r}{f' for {ref!r}' if ref else ''} has no voice id to choose"
        )
    designer = designer if designer is not None else default_designer()
    name = f"{entry.get('name_prefix', 'an')} {ref} {found['option']}".strip()
    return _voice_id_of(
        designer.design_voice(
            entry["notes"], preview=found["generated_voice_id"], name=name
        )
    )


# --- the audition reel ---------------------------------------------------------------


@dataclass
class AuditionJob:
    """One reel to make: an option of one voice, the lines it speaks, and the
    content key the reel is recorded under (so it is never made twice)."""

    ref: str
    option: dict
    lines: list[tuple[str, dict[str, Any]]]
    effects: dict[str, Any]
    key: str

    @property
    def reel(self) -> str:
        return f"{self.ref}_{self.option['option']}"


def _reel_wav(audio: bytes, effects: Mapping[str, Any]) -> bytes:
    """``audio`` (the provider's clip, any container) with the voice's
    ``effects`` applied — the tempo, pitch and trim the film applies, so the
    reel is the film's sound (``takes`` are not: one take per line) — as 16-bit
    mono WAV at :data:`AUDITION_SAMPLE_RATE`: an input already so is kept as it
    is, anything else goes through the effects chain's own ffmpeg decoder."""
    from an.audio.effects import (
        VoiceEffectError,
        _ffmpeg_wav,
        apply_voice_effects,
        decode_chain,
    )

    try:
        wav = apply_voice_effects(audio, effects) if effects else audio
        if _is_reel_wav(wav):
            return wav
        return _ffmpeg_wav(wav, f"{decode_chain()},aformat=channel_layouts=mono", {})
    except VoiceEffectError as e:
        raise VoiceDesignError(
            "an audition reel decodes the provider's audio with ffmpeg (and "
            "applies the voice's effects); " + str(e).split(":", 1)[-1].strip()
            if "ffmpeg binary" in str(e)
            else f"an audition line could not be decoded: {e}"
        ) from e


def _is_reel_wav(audio: bytes) -> bool:
    if audio[:4] != b"RIFF":
        return False
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            return (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (
                AUDITION_SAMPLE_RATE,
                1,
                2,
            )
    except (wave.Error, EOFError):
        return False


def _join_wavs(parts: Iterable[bytes], *, gap_s: float) -> bytes:
    """One WAV of ``parts`` (16-bit mono at :data:`AUDITION_SAMPLE_RATE`, as
    :func:`_reel_wav` makes them), with ``gap_s`` of silence after each."""
    out = io.BytesIO()
    silence = b"\x00\x00" * int(round(gap_s * AUDITION_SAMPLE_RATE))
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(AUDITION_SAMPLE_RATE)
        for part in parts:
            with wave.open(io.BytesIO(part), "rb") as r:
                w.writeframes(r.readframes(r.getnframes()))
            w.writeframes(silence)
    return out.getvalue()


def audition_key(
    voice_id: str,
    lines: Iterable[tuple[str, Mapping[str, Any]]],
    *,
    effects: Mapping[str, Any] | None = None,
    gap_s: float = AUDITION_GAP_S,
    tts_name: str = "",
) -> str:
    """The content key of a reel: what it would sound like depends on exactly
    these, so a reel with this key is never made (billed) twice.

    >>> k = audition_key("v", [("Hi.", {"model_id": "m"})], tts_name="elevenlabs")
    >>> k == audition_key("v", [("Hi.", {"model_id": "m"})], tts_name="elevenlabs"), len(k) > 8
    (True, True)
    >>> k != audition_key("v", [("Hi!", {"model_id": "m"})], tts_name="elevenlabs")
    True
    """
    from an.util import _stable_hash

    return _stable_hash(
        {
            "voice_id": voice_id,
            "lines": [(text, dict(opts)) for text, opts in lines],
            "effects": dict(effects or {}),
            "gap_s": gap_s,
            "tts": tts_name,
        }
    )


def plan_auditions(
    entry: Mapping,
    lines: Iterable[tuple[str, Mapping[str, Any]]],
    *,
    ref: str = "",
    options: Iterable[str] | None = None,
    effects: Mapping[str, Any] | None = None,
    gap_s: float = AUDITION_GAP_S,
    tts_name: str = "",
    redo: bool = False,
    recorded: Callable[[dict], Mapping[str, Any] | None] | None = None,
) -> list[AuditionJob]:
    """The reels to make for one voice's manifest ``entry``, every one checked
    BEFORE anything is billed: the named ``options`` exist (default: every
    option with a voice id) and are saved voices, there are ``lines`` to speak,
    and an option whose recorded reel was made under this very key is skipped
    unless ``redo``. ``recorded(option)`` says which record to judge that by
    (default: the option's own fields; the project forms pass the scene's own
    record, an#571). Raises :class:`VoiceDesignError` for any problem.
    """
    lines = [(text, dict(opts)) for text, opts in lines]
    if not lines:
        raise VoiceDesignError(
            f"voice {ref!r} speaks no line in the scene: nothing to audition with"
        )
    all_options = list(entry.get("options", ()))
    labels = {str(o.get("option", "")).upper(): o for o in all_options}
    if options is not None:
        wanted = [str(o).upper() for o in options]
        missing = sorted(set(wanted) - set(labels))
        if missing:
            raise VoiceDesignError(
                f"no option {missing} for {ref!r} (options: {', '.join(labels)})"
            )
        chosen = [labels[w] for w in dict.fromkeys(wanted)]
    else:
        chosen = [o for o in all_options if o.get("voice_id")]
        if not chosen:  # nothing named and nothing auditionable: say which
            chosen = all_options
    if not chosen:
        raise VoiceDesignError(f"no options for {ref!r}: run `an voices design` first")
    unsaved = [o["option"] for o in chosen if not o.get("voice_id")]
    if unsaved:
        raise VoiceDesignError(
            f"option(s) {unsaved} for {ref!r} are not saved voices (designed with "
            "--only-chosen): an audition needs a voice id. Design again without it."
        )
    jobs = []
    for option in chosen:
        key = audition_key(
            option["voice_id"], lines, effects=effects, gap_s=gap_s, tts_name=tts_name
        )
        on_record = (recorded(option) if recorded is not None else option) or {}
        if (
            not redo
            and on_record.get(AUDITION_KEY)
            and on_record.get(AUDITION_CONTENT_KEY) == key
        ):
            continue  # the reel on record IS this reel: never billed twice
        jobs.append(AuditionJob(ref, option, lines, dict(effects or {}), key))
    return jobs


def announce_auditions(jobs: Iterable[AuditionJob], tts: Any) -> str:
    """What making ``jobs`` will bill, in one sentence (``""`` for none).

    >>> class T:
    ...     name = "elevenlabs"
    ...     def billed_characters(self, text, **kw):
    ...         return len(text)
    >>> jobs = [AuditionJob("j", {"option": "A", "voice_id": "v"}, [("Hi.", {}), ("Bye.", {})], {}, "k")]
    >>> announce_auditions(jobs, T())
    'audition: 1 reel(s) x 2 line(s) = 2 request(s) to elevenlabs, 7 characters'
    """
    jobs = list(jobs)
    if not jobs:
        return ""
    n = sum(len(j.lines) for j in jobs)
    count = getattr(tts, "billed_characters", None)
    chars = (
        sum(count(text, **opts) for j in jobs for text, opts in j.lines)
        if callable(count)
        else None
    )
    per = {len(j.lines) for j in jobs}
    shape = (
        f"{len(jobs)} reel(s) x {per.pop()} line(s) = "
        if len(per) == 1
        else f"{len(jobs)} reel(s), "
    )
    return (
        f"audition: {shape}{n} request(s) to {getattr(tts, 'name', 'the provider')}"
        + (f", {chars} characters" if chars is not None else "")
    )


def run_auditions(
    jobs: Iterable[AuditionJob],
    *,
    reels: MutableMapping[str, bytes],
    tts: Any,
    gap_s: float = AUDITION_GAP_S,
    announce: Any = _STDERR,
    on_reel: Callable[[AuditionJob], None] | None = None,
) -> None:
    """Make every reel of ``jobs`` with ``tts`` (``synthesize(text, voice_id,
    **options)`` per line — billed), ``gap_s`` apart, into ``reels`` under the
    job's reel key, and record it on the job's option (``audition``,
    ``audition_lines``, ``audition_key``); ``on_reel`` is called after each
    reel is recorded, so a failure later loses nothing paid for. ``announce``
    (default: a line on stderr; ``None`` for silence) is told the whole bill
    first, and the provider is asked ``check_available()`` before the first
    request."""
    jobs = list(jobs)
    if not jobs:
        return
    if announce is _STDERR:
        from an.audio.pipeline import _announce_to_stderr

        announce = _announce_to_stderr
    if announce is not None:
        announce(announce_auditions(jobs, tts))
    check = getattr(tts, "check_available", None)
    if callable(check):
        check()
    for job in jobs:
        parts = []
        for text, opts in job.lines:
            clip = tts.synthesize(text, job.option["voice_id"], **opts)
            audio = getattr(clip, "bytes_", None)
            if audio is None and getattr(clip, "path", None):
                audio = Path(clip.path).read_bytes()
            if not audio:
                raise VoiceDesignError(
                    f"{getattr(tts, 'name', 'the provider')} returned no audio for {text!r}"
                )
            parts.append(_reel_wav(audio, job.effects))
        reels[job.reel] = _join_wavs(parts, gap_s=gap_s)
        job.option[AUDITION_KEY] = job.reel
        job.option[AUDITION_LINES_KEY] = len(job.lines)
        job.option[AUDITION_CONTENT_KEY] = job.key
        if on_reel is not None:
            on_reel(job)


def audition_voice_options(
    entry: Mapping,
    lines: Iterable[tuple[str, Mapping[str, Any]]],
    *,
    reels: MutableMapping[str, bytes],
    tts: Any,
    ref: str = "",
    options: Iterable[str] | None = None,
    effects: Mapping[str, Any] | None = None,
    gap_s: float = AUDITION_GAP_S,
    announce: Any = _STDERR,
    redo: bool = False,
) -> dict:
    """An audition reel per option of one voice's manifest ``entry``: every line
    of ``lines`` — ``(text, synthesize options)`` pairs, the options being what
    the film's pipeline would send (``model_id``, ``voice_settings``,
    ``audio_tags`` from the line's cues) — spoken in that option's voice by
    ``tts`` (the film's provider), the voice's ``effects`` applied, ``gap_s``
    apart, as one WAV in ``reels`` under ``<ref>_<option>``. Returns a copy of
    the entry with each made reel recorded on its option; the input is not
    changed. :func:`plan_auditions` checks everything before the first
    request; a reel already on record under the same content key is not made
    again unless ``redo`` (so a second call bills nothing).

    >>> from types import SimpleNamespace as N
    >>> import math, struct
    >>> def tone(n):
    ...     import io, wave
    ...     b = io.BytesIO(); w = wave.open(b, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
    ...     w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(n))); w.close()
    ...     return b.getvalue()
    >>> class FakeTTS:
    ...     name = "fake"
    ...     def synthesize(self, text, voice_id, **kw):
    ...         return N(bytes_=tone(4410), transcript=text)
    >>> entry = {"options": [{"option": "A", "voice_id": "v1"}, {"option": "L1", "voice_id": "v2"}]}
    >>> reels = {}
    >>> out = audition_voice_options(entry, [("Hi.", {}), ("Bye.", {"audio_tags": ["sad"]})], reels=reels, tts=FakeTTS(), ref="j", announce=None)
    >>> sorted(reels), [o["audition"] for o in out["options"]]
    (['j_A', 'j_L1'], ['j_A', 'j_L1'])
    >>> again = audition_voice_options(out, [("Hi.", {}), ("Bye.", {"audio_tags": ["sad"]})], reels=reels, tts=FakeTTS(), ref="j", announce=None)
    >>> again == out  # on record under the same key: nothing made, nothing billed
    True
    """
    out = dict(entry)
    out["options"] = [dict(o) for o in entry.get("options", ())]
    jobs = plan_auditions(
        out,
        lines,
        ref=ref,
        options=options,
        effects=effects,
        gap_s=gap_s,
        tts_name=str(getattr(tts, "name", "")),
        redo=redo,
    )
    run_auditions(jobs, reels=reels, tts=tts, gap_s=gap_s, announce=announce)
    return out


def default_chooser() -> str:
    """Who a choice is recorded as when nobody is named: the login name."""
    import getpass

    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no login name on this host
        return "unknown"


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_choice(
    doc: Mapping | None,
    voice_id: str,
    *,
    by: str | None = None,
    at: str | None = None,
    provider: str | None = None,
) -> dict:
    """The voice document with ``voice_id`` chosen by ``by`` at ``at`` (default:
    now, UTC): ``chosen_by`` and ``chosen_at`` beside the ``voice_id``, the
    ``provider`` set when given (``None``, the default, keeps the document's:
    a designed option passes :data:`DESIGN_PROVIDER`; a hand-picked voice of
    another provider passes nothing), and ``provisional`` dropped, since a
    choice is what it stood in for. ``by`` defaults to the login name, which
    says nothing about the writer: a connector or an agent choosing on a
    writer's behalf passes the writer's name.

    >>> doc = record_choice({"notes": "a warm voice", "provisional": True}, "v1",
    ...                     by="noel", at="2026-10-20T22:00:00+00:00", provider="elevenlabs")
    >>> doc == {"notes": "a warm voice", "provider": "elevenlabs", "voice_id": "v1",
    ...         "chosen_by": "noel", "chosen_at": "2026-10-20T22:00:00+00:00"}
    True
    >>> record_choice({"provider": "mac_say"}, "Junior", by="noel", at="t")["provider"]
    'mac_say'
    """
    out = dict(doc or {})
    out.pop(PROVISIONAL_KEY, None)
    if provider:
        out["provider"] = provider
    out["voice_id"] = voice_id
    out[CHOSEN_BY_KEY] = (by or "").strip() or default_chooser()
    out[CHOSEN_AT_KEY] = at or _utc_now()
    return out


def provisional_reason(doc: Mapping | None) -> str | None:
    """Why ``doc`` speaks a voice nobody chose (its ``provisional``, as text), or
    ``None`` when it is not provisional.

    >>> provisional_reason({"provisional": "timing draft"}), provisional_reason({"provisional": True})
    ('timing draft', 'provisional')
    >>> provisional_reason({"provisional": False}) is None, provisional_reason({}) is None
    (True, True)
    """
    if not isinstance(doc, Mapping):
        return None
    value = doc.get(PROVISIONAL_KEY)
    if not value:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else "provisional"


def voice_casting_problem(doc: Mapping | None) -> str | None:
    """Why a render must not speak ``doc`` as it stands, or ``None``.

    A voice written in words (``notes``) is cast only once a choice is recorded
    (``chosen_by`` beside the ``voice_id``), or it is marked ``provisional``. A
    document without ``notes`` names its voice by hand and is not judged here.

    >>> voice_casting_problem({"voice_id": "v1"}) is None
    True
    >>> print(voice_casting_problem({"notes": "a warm voice"}))
    is written in words but no voice is chosen for it: nothing to speak with
    >>> print(voice_casting_problem({"notes": "a warm voice", "voice_id": "v1"}))
    has a voice_id nobody is recorded as choosing (no chosen_by)
    >>> voice_casting_problem({"notes": "n", "voice_id": "v1", "chosen_by": "noel"}) is None
    True
    >>> voice_casting_problem({"notes": "n", "voice_id": "v1", "provisional": "draft"}) is None
    True
    >>> voice_casting_problem({"notes": "n", "provisional": True}) is None  # provisional WHAT?
    False
    """
    if not isinstance(doc, Mapping):
        return None
    notes = doc.get(NOTES_KEY)
    if not isinstance(notes, str) or not notes.strip():
        return None
    voice_id = doc.get("voice_id")
    if not isinstance(voice_id, str) or not voice_id.strip():
        # Not even a provisional voice: nothing names what to speak with (the
        # provider would be handed the document's key as a voice id).
        return (
            "is written in words but no voice is chosen for it: nothing to speak with"
        )
    if provisional_reason(doc) is not None:
        return None
    by = doc.get(CHOSEN_BY_KEY)
    if not isinstance(by, str) or not by.strip():
        return "has a voice_id nobody is recorded as choosing (no chosen_by)"
    return None


def voice_casting(
    voice_refs: Iterable[str], voices: Mapping[str, Any] | None
) -> tuple[list[str], list[str]]:
    """``(uncast, provisional)``: one message per distinct voice of ``voice_refs``
    (the voices a scene's lines speak with) that a render must not speak as it
    stands, and one per voice it speaks provisionally. Each message starts
    with ``voice '<ref>'`` and the uncast ones name the fix.

    >>> voices = {"j": {"notes": "n", "voice_id": "v"}, "p": {"notes": "n", "voice_id": "v",
    ...           "provisional": "round-2 timing draft"}, "k": {"voice_id": "x"}}
    >>> uncast, provisional = voice_casting(["j", "p", "k", "j", "ghost"], voices)
    >>> print(uncast[0])
    voice 'j' has a voice_id nobody is recorded as choosing (no chosen_by). Cast it: `an voices design` (options from its notes or a library query), `an voices audition` (the lines in each option's voice), then `an voices choose <option> --by <writer>` (the pick, recorded as chosen_by), or `an voices cast <voice_id> --by <writer>` for a voice picked by hand (`an voices list`); a timing draft may set `provisional: true` on the voice document instead.
    >>> provisional
    ["voice 'p' is provisional (round-2 timing draft): choose a voice before the cut"]
    """
    uncast: list[str] = []
    provisional: list[str] = []
    seen: set[str] = set()
    for ref in voice_refs:
        if ref in seen or voices is None or ref not in voices:
            continue
        seen.add(ref)
        doc = voices[ref]
        problem = voice_casting_problem(doc)
        if problem is not None:
            uncast.append(
                f"voice {ref!r} {problem}. Cast it: {CASTING_VERBS}; a timing "
                f"draft may set `{PROVISIONAL_KEY}: true` on the voice document instead."
            )
            continue
        reason = provisional_reason(doc)
        if reason is not None:
            provisional.append(
                f"voice {ref!r} is provisional ({reason}): choose a voice before the cut"
            )
    return uncast, provisional


# --- the project-level forms ---------------------------------------------------------


def _project_stores(project_dir: str | Path):
    from an.stores._common import JsonDirStore
    from an.stores.artifacts import _BlobStore
    from an.stores.voices import VoicesStore

    class _Mp3Store(_BlobStore):
        EXT = "mp3"

    root = Path(project_dir)
    return (
        VoicesStore(root / "assets" / "voices"),
        JsonDirStore(root / OPTIONS_DIR),
        _Mp3Store(root / SAMPLES_DIR),
    )


def _project_reels(project_dir: str | Path, scene_file: Any = DEFAULT_SCENE_FILE):
    """The reels store of ``scene_file``: ``artifacts/voice_auditions`` for the
    default scene, its own subfolder for another (an#571)."""
    from an.ir.sync import resolve_scene_file
    from an.stores.artifacts import _BlobStore

    class _WavStore(_BlobStore):
        EXT = "wav"

    sf = resolve_scene_file(project_dir, scene_file)
    return _WavStore(Path(project_dir) / sf.per_scene_dir(AUDITIONS_DIR))


def _scene_record(option: Mapping, sf: Any, reels: Any = None) -> dict | None:
    """``sf``'s own record of ``option``'s reel (an#571), or ``None``. The default
    scene falls back to the top-level fields written before records were per
    scene, but only while they are still its own: once another scene has made a
    reel they describe that one, unless they point into the default folder. A
    record whose reel is no longer in ``reels`` (when given) counts as none."""
    record = (option.get(AUDITIONS_KEY) or {}).get(sf.name)
    if record is None and sf.is_default:
        legacy = {k: option[k] for k in AUDITION_RECORD_KEYS if k in option}
        default_folder = AUDITIONS_DIR.as_posix() + "/"
        path = str(legacy.get(AUDITION_PATH_KEY, ""))
        if (AUDITIONS_KEY not in option) or (
            path.startswith(default_folder) and "/" not in path[len(default_folder) :]
        ):
            record = legacy
    if record and reels is not None:
        reel = record.get(AUDITION_KEY)
        if not reel or not reels.path_of(reel).is_file():
            return None
    return record or None


def _project_lines(
    project_dir: str | Path, scene_file: Any = DEFAULT_SCENE_FILE
) -> Callable[[str], list[str]]:
    """``ref -> the dialogue lines spoken in that voice`` in the project's scene
    (``scene_file``: another scene of the project, an#554)."""
    from an.audio.voices import line_voice_id
    from an.project import load

    proj = load(str(project_dir), scene_file=scene_file)
    by_voice: dict[str, list[str]] = {}
    for shot in proj.scene.timeline:
        for line in getattr(shot, "dialogue", None) or ():
            by_voice.setdefault(line_voice_id(line, shot, proj.mall), []).append(
                line.text
            )
    return lambda ref: by_voice.get(ref, [])


def _project_audition_inputs(
    project_dir: str | Path, tts: Any, *, scene_file: Any = DEFAULT_SCENE_FILE
) -> Callable[[str], tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]]:
    """``ref -> (lines, effects)`` for the lines spoken in that voice: each line
    as ``(text, synthesize options)`` — what the film's audio pipeline would
    send ``tts`` for it (:func:`an.audio.pipeline.synthesis_options`: the
    voice document's model and settings, the line's cues as audio tags) — and
    the voice's normalised ``effects``. Resolved per voice, when asked."""
    from an.audio.effects import voice_effects
    from an.audio.pipeline import synthesis_options
    from an.audio.voices import line_voice_id
    from an.project import load

    proj = load(str(project_dir), scene_file=scene_file)
    by_voice: dict[str, list[Any]] = {}
    for shot in proj.scene.timeline:
        for line in getattr(shot, "dialogue", None) or ():
            by_voice.setdefault(line_voice_id(line, shot, proj.mall), []).append(line)

    def inputs(ref: str):
        lines = [
            (line.text, synthesis_options(tts, line, proj.mall, ref))
            for line in by_voice.get(ref, [])
        ]
        return lines, voice_effects(proj.mall, ref)

    return inputs


def design_project_voices(
    project_dir: str | Path,
    refs: Iterable[str] | None = None,
    *,
    designer: Any = None,
    model_id: str = DFLT_DESIGN_MODEL,
    persist: bool = True,
    name_prefix: str | None = None,
    library: Any = None,
    library_query: Mapping | str | None = None,
    library_limit: int = DFLT_LIBRARY_LIMIT,
    design: bool = True,
    scene_file: Any = DEFAULT_SCENE_FILE,
) -> dict[str, dict]:
    """Design options for the project's voices (and search the library for the
    ones with a query); write manifests and samples; return the manifest.

    A voice document without ``sample_text`` speaks its own lines from the scene
    (``scene_file``: another scene of the project, an#554).
    ``library_query`` (``accent=irish,gender=male``) applies to every voice
    without a ``library`` of its own; ``design=False`` searches the library only.
    """
    from an.ir.sync import resolve_scene_file

    # A scene file named and not there is a refusal, not "no lines" (an#554).
    scene_file = resolve_scene_file(project_dir, scene_file)
    voices, options, samples = _project_stores(project_dir)
    try:
        lines_of = _project_lines(project_dir, scene_file)
    except Exception:  # noqa: BLE001 - no readable scene: the provider writes the sample text
        lines_of = None
    manifest = design_voice_options(
        dict(voices.items()),
        samples=samples,
        refs=refs,
        designer=designer,
        model_id=model_id,
        persist=persist,
        name_prefix=name_prefix or Path(project_dir).resolve().name,
        lines_of=lines_of,
        library=library,
        library_query=library_query,
        library_limit=library_limit,
        design=design,
    )
    for ref, entry in manifest.items():
        for o in entry["options"]:
            o["sample_path"] = (
                str((SAMPLES_DIR / f"{o['sample']}.mp3").as_posix())
                if o.get("sample")
                else None
            )
        if ref in options:
            entry = carry_over(options[ref], entry)
        options[ref] = entry
    return manifest


def carry_over(previous: Mapping, entry: MutableMapping) -> MutableMapping:
    """``entry`` (a voice's options, designed again) keeping what the previous
    design's entry recorded (an#604): its ``chosen`` (the voice the voice
    document names, by whom and when; its ``option`` cleared, since this
    design's option of that label is another voice), and its ``retired``
    ledger, joined by every voice the previous design saved that this one no
    longer names (the chosen one too: it stays named by ``chosen`` until
    another choice replaces it). A library option's voice is another
    account's and is never retired. ``entry`` is returned, updated.

    >>> old = {"name_prefix": "p", "options": [{"option": "A", "voice_id": "v1"},
    ...        {"option": "L1", "kind": "library", "voice_id": "pub"}],
    ...        "chosen": {"option": "A", "voice_id": "v1", "chosen_by": "n", "chosen_at": "t"}}
    >>> new = carry_over(old, {"options": [{"option": "A", "voice_id": "v9"}]})
    >>> new["chosen"]["option"], new["chosen"]["voice_id"], new["retired"]
    (None, 'v1', [{'voice_id': 'v1', 'option': 'A', 'name_prefix': 'p'}])
    """
    named = {o.get("voice_id") for o in entry.get("options", ())}
    retired = [r for r in previous.get("retired") or () if isinstance(r, Mapping)]
    known = {r.get("voice_id") for r in retired}
    for o in previous.get("options", ()):
        voice = o.get("voice_id")
        if (
            voice
            and voice not in named
            and voice not in known
            and o.get("kind") != "library"
        ):
            retired.append(
                {
                    "voice_id": voice,
                    "option": o.get("option"),
                    "name_prefix": previous.get("name_prefix"),
                }
            )
            known.add(voice)
    if retired:
        entry["retired"] = retired
    chosen = previous.get("chosen")
    if isinstance(chosen, Mapping) and chosen.get("voice_id"):
        entry["chosen"] = {**chosen, "option": None}
    return entry


def audition_project_voices(
    project_dir: str | Path,
    refs: Iterable[str] | None = None,
    *,
    options: Iterable[str] | None = None,
    tts: Any = None,
    gap_s: float = AUDITION_GAP_S,
    announce: Any = _STDERR,
    redo: bool = False,
    scene_file: Any = DEFAULT_SCENE_FILE,
) -> dict[str, dict]:
    """An audition reel per option of each voice in ``refs`` (default: every
    voice with a manifest): the voice's own lines from the scene, spoken with
    the film's TTS provider (``tts``, default ElevenLabs — the provider the
    film renders with, so the reel sounds like the film), the voice document's
    model, settings and effects, to ``artifacts/voice_auditions/<ref>_<option>.wav``
    (``.../scenes/<stem>/`` for a scene other than ``scene.md``, so two scenes'
    reels coexist, an#571); the manifest records each reel (``audition_path``,
    and per scene under ``auditions``) as soon as it is made.
    Every voice's reels are planned and checked before the first request, the
    whole bill is announced once, and a reel already on record under the same
    content key is not made again (``redo`` makes them all again). Returns
    the manifests of ``refs``. ``scene_file`` takes the lines from another
    scene of the project (``scene.studio.md``, an#554).
    """
    from an.audio.providers import make_tts
    from an.ir.sync import resolve_scene_file

    sf = resolve_scene_file(project_dir, scene_file)
    tts = tts if tts is not None else make_tts(DESIGN_PROVIDER)
    _, manifests, _ = _project_stores(project_dir)
    reels = _project_reels(project_dir, sf)
    reels_dir = sf.per_scene_dir(AUDITIONS_DIR)
    default_scene = resolve_scene_file(
        project_dir, DEFAULT_SCENE_FILE, must_exist=False
    )
    inputs = _project_audition_inputs(project_dir, tts, scene_file=sf)
    wanted = list(refs) if refs is not None else sorted(manifests)
    if not wanted:
        raise VoiceDesignError("no voice options yet: run `an voices design` first")
    entries: dict[str, dict] = {}
    jobs: list[AuditionJob] = []
    for ref in wanted:
        if ref not in manifests:
            raise VoiceDesignError(
                f"no options for {ref!r}: run `an voices design` first"
            )
        entry = dict(manifests[ref])
        entry["options"] = [dict(o) for o in entry.get("options", ())]
        entries[ref] = entry
        for o in entry[
            "options"
        ]:  # a pre-per-scene reel is the default scene's: keep it so
            if (legacy := _scene_record(o, default_scene)) and AUDITIONS_KEY not in o:
                o[AUDITIONS_KEY] = {default_scene.name: legacy}
        lines, effects = inputs(ref)
        jobs += plan_auditions(
            entry,
            lines,
            ref=ref,
            options=options,
            effects=effects,
            gap_s=gap_s,
            tts_name=str(getattr(tts, "name", "")),
            redo=redo,
            recorded=lambda option: _scene_record(option, sf, reels),
        )

    def record(job: AuditionJob) -> None:
        # run_auditions has put the reel's fields on the option (the latest made);
        # add where it is, and keep this scene's own record beside it.
        job.option[AUDITION_PATH_KEY] = (reels_dir / f"{job.reel}.wav").as_posix()
        made = {k: job.option[k] for k in AUDITION_RECORD_KEYS if k in job.option}
        job.option.setdefault(AUDITIONS_KEY, {})[sf.name] = made
        manifests[job.ref] = entries[
            job.ref
        ]  # written per reel: a later failure loses nothing paid

    run_auditions(
        jobs, reels=reels, tts=tts, gap_s=gap_s, announce=announce, on_reel=record
    )
    return entries


@dataclass(frozen=True)
class VoiceChoice:
    """What :func:`choose_in_entry` did: the voice document; ``previous``, the
    voice the choice displaced (what a voice file written before still
    names; ``None`` when it displaced none); and ``retired``, that voice when
    it went into the ``retired`` ledger (one the choose step itself saved)."""

    document: dict
    previous: str | None = None
    retired: str | None = None


def choose_in_entry(
    entry: MutableMapping,
    option: str,
    *,
    by: str | None = None,
    designer: Any = None,
    ref: str = "",
    at: str | None = None,
    doc: Mapping | None = None,
) -> VoiceChoice:
    """Make ``option`` the choice of one voice's options manifest ``entry``
    (an#549): the one choose step an's ``an voices choose`` and a connector
    (reelee's production pack) share. Returns the voice document
    (:func:`record_choice` of ``doc``, default an empty one: a caller that
    keeps the voice file elsewhere merges these keys into it) and the voice
    it replaced.

    ``entry`` is updated in place: ``chosen`` records the option, its
    ``voice_id``, ``chosen_by`` and ``chosen_at``. Choosing the option already
    chosen reuses its voice (nothing is saved), and keeps its ``chosen_at``
    when the same chooser chooses it again and no ``at`` is given. Choosing
    another one names its voice (saved as a provider voice when it was not,
    :func:`choose_voice_option`, and marked ``saved_by_choice`` on its option)
    and retires the voice it replaces when a choice saved it: its option no
    longer names it, and ``entry["retired"]`` records it (``{voice_id,
    option, name_prefix}``), never deleted here (a copy of the manifest, or a
    voice file already written, may still name it: freeing the provider's
    slot is a separate, explicit act). A voice saved when the options were
    designed (``persist=True``), a library voice and one cast by hand stay
    named where they are. ``by`` defaults to the login name (see
    :func:`record_choice`).

    >>> from types import SimpleNamespace
    >>> class Saver:   # a designer that saves a preview as voice "v<preview>"
    ...     def design_voice(self, notes, *, preview, name): return SimpleNamespace(voice_id="v" + preview)
    >>> entry = {"notes": "n", "options": [{"option": "A", "generated_voice_id": "a"},
    ...                                    {"option": "B", "generated_voice_id": "b"}]}
    >>> choose_in_entry(entry, "a", by="noel", at="t1", designer=Saver()).document["voice_id"]
    'va'
    >>> choice = choose_in_entry(entry, "B", by="noel", at="t2", designer=Saver())
    >>> choice.previous, choice.retired, [o["voice_id"] for o in entry["options"]]
    ('va', 'va', [None, 'vb'])
    >>> choose_in_entry(entry, "B", by="noel").document["chosen_at"]   # the same choice again
    't2'
    """
    if not isinstance(entry.get("retired", []), list):
        raise VoiceDesignError(
            f"the options manifest's `retired` is {type(entry['retired']).__name__}, "
            "not a list: the manifest is damaged; nothing was chosen"
        )
    label = str(option).strip().upper()
    previous = entry.get("chosen") or {}
    chooser = (by or "").strip() or default_chooser()
    displaced = retired = None
    if previous.get("option") == label and previous.get("voice_id"):
        voice_id = previous["voice_id"]
        if at is None and previous.get(CHOSEN_BY_KEY) == chooser:
            at = previous.get(CHOSEN_AT_KEY)
    else:
        option_of = next(
            (o for o in entry.get("options", ()) if o.get("option") == label), None
        )
        saved = option_of is not None and not option_of.get("voice_id")
        voice_id = choose_voice_option(entry, label, ref=ref, designer=designer)
        displaced = (
            previous.get("voice_id") if previous.get("voice_id") != voice_id else None
        )
        retired = _retire(entry, previous, keep=voice_id)
        if option_of is not None:
            option_of["voice_id"] = voice_id
            if saved:
                option_of[SAVED_BY_CHOICE_KEY] = True
    document = record_choice(doc, voice_id, by=chooser, at=at, provider=DESIGN_PROVIDER)
    entry["chosen"] = _chosen_record(label, document)
    return VoiceChoice(document, displaced, retired)


def _chosen_record(option: str | None, document: Mapping) -> dict:
    """An options manifest's ``chosen``: the option (``None``: cast by hand),
    and the voice document's ``voice_id``, ``chosen_by`` and ``chosen_at``."""
    return {
        "option": option,
        "voice_id": document["voice_id"],
        CHOSEN_BY_KEY: document[CHOSEN_BY_KEY],
        CHOSEN_AT_KEY: document[CHOSEN_AT_KEY],
    }


def _retire(entry: MutableMapping, previous: Mapping, *, keep: str) -> str | None:
    """Retire the voice ``previous`` (the choice being replaced) named, when a
    choice saved it (its option is marked ``saved_by_choice``) and it is not
    ``keep``: its option no longer names it, and the ``retired`` ledger does,
    with whose name it carries (a copy of the manifest inherits the row, not
    the right to delete it). Returns the retired voice, or ``None``."""
    old = previous.get("voice_id")
    saved = next(
        (
            o
            for o in entry.get("options", ())
            if o.get("option") == previous.get("option")
            and o.get(SAVED_BY_CHOICE_KEY)
            and o.get("voice_id") == old
        ),
        None,
    )
    if not old or old == keep or previous.get("option") is None or saved is None:
        return None
    retired = entry.setdefault("retired", [])
    saved["voice_id"] = None
    saved.pop(SAVED_BY_CHOICE_KEY, None)
    retired.append(
        {
            "voice_id": old,
            "option": previous.get("option"),
            "name_prefix": entry.get("name_prefix"),
        }
    )
    return old


def choose_project_voice(
    project_dir: str | Path,
    ref: str,
    option: str,
    *,
    designer: Any = None,
    by: str | None = None,
    at: str | None = None,
) -> dict:
    """Write the chosen option's ``voice_id`` into ``assets/voices/<ref>.json``,
    with who chose it (``by``, default the login name) and when (``at``, default
    now), and the choice into its options manifest (:func:`choose_in_entry`);
    return the document."""
    voices, options, _ = _project_stores(project_dir)
    if ref not in options:
        raise VoiceDesignError(f"no options for {ref!r}: run `an voices design` first")
    entry = copy.deepcopy(dict(options[ref]))
    doc = choose_in_entry(
        entry,
        option,
        by=by,
        designer=designer,
        ref=ref,
        at=at,
        doc=voices[ref] if ref in voices else {},
    ).document
    voices[ref] = doc
    options[ref] = entry
    return doc


def cast_project_voice(
    project_dir: str | Path,
    ref: str,
    voice_id: str | None = None,
    *,
    by: str | None = None,
    at: str | None = None,
    provider: str | None = None,
) -> dict:
    """Record a voice picked by hand (from `an voices list`, or the document's
    own ``voice_id``) as the writer's choice for ``ref``: ``voice_id`` (default:
    the one the document already names), ``chosen_by``, ``chosen_at``; no
    options manifest needed and nothing billed. ``provider`` sets the
    document's when given. Returns the document.
    """
    voices, options, _ = _project_stores(project_dir)
    doc = dict(voices[ref]) if ref in voices else None
    if doc is None:
        raise VoiceDesignError(f"no voice document {ref!r} in assets/voices")
    chosen = (voice_id or "").strip() or doc.get("voice_id")
    if not isinstance(chosen, str) or not chosen.strip():
        raise VoiceDesignError(
            f"voice {ref!r} names no voice_id: pass one (`an voices list` shows them)"
        )
    doc = record_choice(doc, chosen, by=by, at=at, provider=provider)
    voices[ref] = doc
    if ref in options:
        entry = dict(options[ref])
        # cast by hand: what it replaces is not retired (the designed voice
        # stays named on its option), and it is never retired itself
        entry["chosen"] = _chosen_record(None, doc)
        options[ref] = entry
    return doc
