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

import re
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from pathlib import Path
from typing import Any

__all__ = [
    "ElevenLabsVoiceDesigner",
    "VoiceDesignError",
    "cast_project_voice",
    "choose_project_voice",
    "choose_voice_option",
    "default_chooser",
    "default_designer",
    "design_project_voices",
    "design_voice_options",
    "designable_voices",
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
#: A voice a render may speak although nobody chose it: a timing draft. Any
#: truthy value; a string says why, and the render report repeats it.
PROVISIONAL_KEY = "provisional"
#: The verbs that cast a voice, named by every refusal.
CASTING_VERBS = (
    "`an voices design` (options from its notes) then `an voices choose <option> "
    "--by <writer>` (the pick, recorded as chosen_by), or `an voices cast "
    "<voice_id> --by <writer>` for a voice picked by hand (`an voices list`)"
)


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
) -> dict[str, dict]:
    """Design options for each voice with notes; return the options manifest.

    voices: ``{ref: voice document}`` (a project's ``voices`` store)
    samples: where each option's audio goes, keyed ``<ref>_<option>`` (mp3 bytes)
    refs: the voices to design (default: every one with ``notes``)
    designer: a two-method designer (default: :func:`default_designer`)
    model_id: the provider's voice-design model
    persist: save every option as a durable voice now (else only the chosen one, later)
    name_prefix: prefix of the saved voices' names in the provider account
    lines_of: ``ref -> that voice's dialogue lines``, for a sample text when the
        document has none (else the provider writes one)
    """
    todo = designable_voices(voices, refs)
    if not todo:
        raise VoiceDesignError(
            f"no voice document has {NOTES_KEY!r}: nothing to design from"
        )
    designer = designer if designer is not None else default_designer()
    manifest: dict[str, dict] = {}
    for ref, doc in todo.items():
        notes = doc[NOTES_KEY].strip()
        fallback = sample_text_from_lines(lines_of(ref)) if lines_of else None
        text = sample_text_of(doc, fallback)
        previews = designer.design_voice_previews(notes, text=text, model_id=model_id)
        options = []
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
                    "generated_voice_id": preview.generated_voice_id,
                    "voice_id": voice_id,
                    "sample": key,
                    "duration_s": getattr(preview, "duration_s", None),
                }
            )
        manifest[ref] = {
            "notes": notes,
            "sample_text": text,
            "design_model": model_id,
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
    designer = designer if designer is not None else default_designer()
    name = f"{entry.get('name_prefix', 'an')} {ref} {found['option']}".strip()
    return _voice_id_of(
        designer.design_voice(
            entry["notes"], preview=found["generated_voice_id"], name=name
        )
    )


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
        return "is written in words but no voice is chosen for it: nothing to speak with"
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
    voice 'j' has a voice_id nobody is recorded as choosing (no chosen_by). Cast it: `an voices design` (options from its notes) then `an voices choose <option> --by <writer>` (the pick, recorded as chosen_by), or `an voices cast <voice_id> --by <writer>` for a voice picked by hand (`an voices list`); a timing draft may set `provisional: true` on the voice document instead.
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


def _project_lines(project_dir: str | Path) -> Callable[[str], list[str]]:
    """``ref -> the dialogue lines spoken in that voice`` in the project's scene."""
    from an.audio.voices import line_voice_id
    from an.project import load

    proj = load(str(project_dir))
    by_voice: dict[str, list[str]] = {}
    for shot in proj.scene.timeline:
        for line in getattr(shot, "dialogue", None) or ():
            by_voice.setdefault(line_voice_id(line, shot, proj.mall), []).append(
                line.text
            )
    return lambda ref: by_voice.get(ref, [])


def design_project_voices(
    project_dir: str | Path,
    refs: Iterable[str] | None = None,
    *,
    designer: Any = None,
    model_id: str = DFLT_DESIGN_MODEL,
    persist: bool = True,
    name_prefix: str | None = None,
) -> dict[str, dict]:
    """Design options for the project's voices; write manifests and samples; return the manifest.

    A voice document without ``sample_text`` speaks its own lines from the scene.
    """
    voices, options, samples = _project_stores(project_dir)
    try:
        lines_of = _project_lines(project_dir)
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
    )
    for ref, entry in manifest.items():
        for o in entry["options"]:
            o["sample_path"] = str((SAMPLES_DIR / f"{o['sample']}.mp3").as_posix())
        options[ref] = entry
    return manifest


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
    now; :func:`record_choice`); return the document."""
    voices, options, _ = _project_stores(project_dir)
    if ref not in options:
        raise VoiceDesignError(f"no options for {ref!r}: run `an voices design` first")
    entry = dict(options[ref])
    voice_id = choose_voice_option(entry, option, ref=ref, designer=designer)
    doc = record_choice(
        voices[ref] if ref in voices else {},
        voice_id,
        by=by,
        at=at,
        provider=DESIGN_PROVIDER,
    )
    voices[ref] = doc
    entry["chosen"] = {
        "option": str(option).upper(),
        "voice_id": voice_id,
        CHOSEN_BY_KEY: doc[CHOSEN_BY_KEY],
        CHOSEN_AT_KEY: doc[CHOSEN_AT_KEY],
    }
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
        entry["chosen"] = {
            "option": None,
            "voice_id": chosen,
            CHOSEN_BY_KEY: doc[CHOSEN_BY_KEY],
            CHOSEN_AT_KEY: doc[CHOSEN_AT_KEY],
        }
        options[ref] = entry
    return doc
