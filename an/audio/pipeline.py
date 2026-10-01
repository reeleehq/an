"""Audio pipeline orchestration: dialogue → audio → visemes → IR mutation.

Phase 3 wires the pieces together. ``produce_audio_for_scene`` walks every
``Dialogue`` in the scene, synthesizes its audio + viseme track via the
configured providers, persists artifacts to ``mall["audio"]`` /
``mall["visemes"]``, and stamps the resulting ``VisemeTrack`` and timing
back onto the ``Dialogue`` line so renderers can find it.

Defaults are the offline providers (silent WAV + deterministic visemes), so
the entire pipeline runs without API keys or external binaries.

>>> from an.audio.pipeline import default_tts, default_lipsync
>>> default_tts().name
'offline'
>>> default_lipsync().name
'offline'
"""

from __future__ import annotations

import json
import sys
import warnings
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import asdict, dataclass
from typing import Any

from an.audio.effects import EFFECT_SAMPLE_RATE, apply_voice_effects, voice_effects
from an.audio.lipsync import LipSyncProvider, Viseme, VisemeTrack
from an.audio.offline_lipsync import OfflineLipSync
from an.audio.offline_tts import OfflineTTS
from an.audio.takes import (
    REROLL_HINT,
    TAKES_RECORD_VERSION,
    TAKES_STORE,
    TakeLostError,
    TakeScorer,
    TakesSpec,
    audio_digest,
    choose_take,
    make_take_scorer,
    read_takes_record,
    scorer_identity,
    takes_choice_part,
    voice_takes,
    write_takes_record,
)
from an.audio.tts import AudioClip, TTSProvider
from an.audio.voices import (
    DEFAULT_VOICE,
    line_voice_id,
    provider_voice,
    voice_applies,
    voice_document,
)
from an.ir.schema import Dialogue, SceneIR, VisemeKeyframe, WordTimingIR
from an.ir.schema import VisemeTrack as IRVisemeTrack
from an.util import _stable_hash


class AudioPipelineError(RuntimeError):
    """The scene declares audio the pipeline cannot produce. Carries detail."""


class TakeDigestWarning(UserWarning):
    """The audio restored for a line's recorded take is not the audio the record names."""


#: Resolve the takes from the voice document (the default of ``takes=``).
_FROM_VOICE: Any = object()
#: ``(TakesSpec) -> TakeScorer`` — the seam that turns a takes spec into its scorer.
TakeScorerFactory = Callable[[TakesSpec], TakeScorer]


def _announce_to_stderr(message: str) -> None:
    """The default ``announce``: one line on stderr, where a CLI user sees it."""
    print(f"an: {message}", file=sys.stderr, flush=True)


def default_tts() -> TTSProvider:
    """The default TTS provider: ``OfflineTTS``."""
    return OfflineTTS()


def default_lipsync() -> LipSyncProvider:
    """The default lip-sync provider: ``OfflineLipSync``."""
    return OfflineLipSync()


def produce_audio_for_dialogue(
    dialogue: Dialogue,
    mall: Mapping[str, MutableMapping] | None = None,
    *,
    tts: TTSProvider | None = None,
    lipsync: LipSyncProvider | None = None,
    effects: Mapping[str, float] | None = None,
    voice_id: str | None = None,
    takes: TakesSpec | None = _FROM_VOICE,
    take_scorer: TakeScorerFactory = make_take_scorer,
) -> tuple[AudioClip, VisemeTrack]:
    """Synthesize audio + visemes for one dialogue line.

    Side effects: when ``mall`` is provided, persists the WAV to
    ``mall["audio"]`` keyed by the content-hash of the dialogue, and persists
    the viseme JSON to ``mall["visemes"]`` similarly. Cache-friendly: a
    second call with identical inputs returns the cached versions.

    ``effects`` (default: what the line's voice declares in ``mall["voices"]``)
    is applied to the synthesized audio BEFORE alignment, so the visemes are
    computed on the audio the viewer hears. The raw synthesis stays cached under
    its own key, so changing an effect never re-pays the TTS.

    ``voice_id`` (default: the line's ``voice_ref``, else ``"default"``) is the
    ``voices``-store key; :func:`produce_audio_for_scene` passes the one
    :func:`an.audio.voices.line_voice_id` resolves, so a character's bound
    voice reaches here (an#194). The provider is handed the voice document's
    own voice id when it names one.

    What the provider's optional ``synthesis_options`` hook derives from the
    voice document and the line (ElevenLabs: ``model_id``, ``voice_settings``,
    ``seed``, and the ``[emotion]``/``direction`` audio tags — an#209) is passed
    to ``synthesize`` and keyed; the text handed to alignment is always the
    bare ``dialogue.text``, never the tagged one.

    ``takes`` (default: what the voice declares for this line — see
    :mod:`an.audio.takes`; ``None`` forces one take) synthesizes several takes,
    scores each with ``take_scorer(spec)`` on the audio the viewer hears, keeps
    the best and records the choice in ``mall["takes"]``. A recorded choice is
    restored from the record and never re-rolled; a recorded take whose audio is
    gone raises :class:`~an.audio.takes.TakeLostError` before any request.
    """
    tts = tts or default_tts()
    lipsync = lipsync or default_lipsync()
    voice_id = voice_id or dialogue.voice_ref or DEFAULT_VOICE
    req = _line_request(
        dialogue, mall, tts, voice_id, effects=effects, takes=takes, take_scorer=take_scorer
    )
    return _produce_line(req, mall, lipsync)


def _produce_line(
    req: "_LineRequest",
    mall: Mapping[str, MutableMapping] | None,
    lipsync: LipSyncProvider,
) -> tuple[AudioClip, VisemeTrack]:
    """The audio and visemes of a resolved request; sets ``req.cache_key`` when
    a best-of-N choice is made here. The visemes are keyed on the audio KEPT."""
    if req.spec is None:
        audio_clip = _load_or_synthesize(
            req.tts, req.text, req.handed_voice, mall, req.raw_key, options=req.options
        )
        if req.cache_key != req.raw_key:
            audio_clip = _load_or_apply_effects(audio_clip, req.effects, mall, req.cache_key)
    else:
        audio_clip = _load_or_choose_take(mall, req)
    viseme_cache_key = viseme_key(req.cache_key, lipsync.name, req.text)
    track = _load_or_align(lipsync, audio_clip, req.text, mall, viseme_cache_key)
    return audio_clip, track


def produce_audio_for_scene(
    scene: SceneIR,
    mall: Mapping[str, MutableMapping] | None = None,
    *,
    tts: TTSProvider | None = None,
    lipsync: LipSyncProvider | None = None,
    take_scorer: TakeScorerFactory = make_take_scorer,
    announce: Callable[[str], None] | None = _announce_to_stderr,
) -> SceneIR:
    """Walk every dialogue line, synthesize, and stamp viseme tracks back.

    Mutates the ``scene`` in place AND returns it (for chaining).
    Stamps ``Dialogue.duration``, ``Dialogue.viseme_track``, and
    ``Dialogue.audio_ref`` (mall["audio"] key) so the renderer can find the
    audio later. Lines with an existing viseme_track AND audio_ref are not
    re-synthesized (idempotent).

    ``Dialogue.start`` is DERIVED on every pass, synthesized or not, by
    :meth:`Dialogue.planned_start`: the line's ``at`` if set, else the previous
    line's end plus its ``pause`` (an#187). So editing a pause re-times the
    shot without touching the audio, and every consumer of ``start`` — the
    mux, the visemes, captions, ducking — follows. A ``start`` on a line that
    was never synthesized is an authored start from before ``at`` existed,
    and is kept as the line's ``at``.

    Every line's request is resolved BEFORE anything is synthesized, so a
    malformed voice (an effect, a ``takes``), a corrupt takes record or a
    recorded take whose audio is gone fails before a credit is spent; and
    ``announce`` (default: a line on stderr; ``None`` for silence) is told, before the first request, what best-of-N takes will bill (requests
    and the provider's characters) and which recorded takes were chosen by an
    older scorer version than the current one (they are kept).
    """
    tts = tts or default_tts()
    lipsync = lipsync or default_lipsync()
    voice_default = DEFAULT_VOICE
    audio_store = mall.get("audio") if mall is not None else None
    viseme_store = mall.get("visemes") if mall is not None else None
    pending: list[tuple[Dialogue, str, _LineRequest]] = []
    resolved: list[_LineRequest] = []
    for shot in scene.timeline:
        if shot.narration:
            # `Shot.narration` is fully modelled in the IR — text, voice_ref,
            # start, duration, viseme_track, audio_ref — and nothing has ever
            # consumed it: this loop walks `shot.dialogue` only, and the cutout
            # compiler has no narration path either. So a narrated shot produced
            # no audio AND no picture, silently. Narrator-over-visuals is the
            # shape of the whole explainer genre, so this is a real gap rather
            # than an oversight, and it is tracked as such.
            raise AudioPipelineError(
                f"shot {shot.id!r} declares {len(shot.narration)} narration "
                "line(s), which the audio pipeline does not synthesise — it "
                "walks shot.dialogue only. Narration produces neither audio nor "
                "video today. Use a dialogue line with an off-screen speaker as "
                "the workaround; the real fix is tracked at "
                "https://github.com/thorwhalen/an/issues/9."
            )
        for line in shot.dialogue:
            if (
                line.start is not None
                and line.audio_ref is None
                and line.at is None
                and line.pause is None
            ):
                line.at = line.start
            voice_id = line_voice_id(line, shot, mall, default=voice_default)
            req = _line_request(line, mall, tts, voice_id, take_scorer=take_scorer)
            resolved.append(req)
            expected_audio_ref = req.cache_key  # None: a best-of-N choice to make
            expected_viseme_ref = viseme_key(
                expected_audio_ref or "", lipsync.name, line.text
            )
            already_done = (
                expected_audio_ref is not None
                and not req.needs_work
                and line.audio_ref == expected_audio_ref
                and line.viseme_ref == expected_viseme_ref
                and line.viseme_track is not None
                and line.duration is not None
                # A line stamped before an#96 by a provider that HAS words is
                # re-aligned once so the words land; a provider without words
                # (offline, Rhubarb) never triggers this, or it would re-align
                # forever. The cache key is unchanged: the sidecar simply grew.
                and (line.word_timings is not None or not _emits_word_timings(lipsync))
                and (audio_store is None or expected_audio_ref in audio_store)
                and (viseme_store is None or expected_viseme_ref in viseme_store)
            )
            if not already_done:
                pending.append((line, voice_id, req))

    messages = [
        takes_cost_message([(line.text, req) for line, _, req in pending], tts, audio_store),
        _older_scorer_message(resolved),
    ]
    if announce is not None:
        for message in filter(None, messages):
            announce(message)

    for line, _voice_id, req in pending:
        # Never synthesized, or the providers changed: synthesize (the
        # content-keyed stores make a mere re-stamp free).
        audio, track = _produce_line(req, mall, lipsync)
        line.duration = audio.duration
        line.viseme_track = _to_ir_viseme_track(track)
        line.word_timings = _to_ir_word_timings(track)
        line.audio_ref = req.cache_key
        line.viseme_ref = viseme_key(req.cache_key, lipsync.name, line.text)
    return retime_dialogue(scene)


def retime_dialogue(scene: SceneIR, *, timed_shots_only: bool = False) -> SceneIR:
    """Stamp every synthesized line's ``start`` from its ``pause`` / ``at``.

    Pure — synthesizes nothing, reads no store — and idempotent. The audio
    pipeline ends with it, and every path that skips the pipeline (``render``
    with ``auto_audio=False``, ``an preview``) runs it too, so a pause edited
    after synthesis is never played at the stale stamp (an#187). A shot is
    re-timed up to its first line with no ``duration`` (never synthesized:
    nothing after it has a known start). Mutates in place and returns
    ``scene``.

    ``timed_shots_only=True`` — what the paths that skip synthesis pass —
    leaves a shot whose lines carry no ``pause``/``at`` exactly as stamped:
    a hand-built scene may stamp ``start`` itself (a test, a fixture), and
    without the pipeline there is no authority to say that stamp is stale.

    >>> from an.ir.schema import Dialogue, SceneIR, Shot
    >>> shot = Shot(id="s", dialogue=[
    ...     Dialogue(speaker="a", text="hi", start=0.0, duration=0.5, audio_ref="k1"),
    ...     Dialogue(speaker="b", text="bye", start=0.5, duration=0.4, audio_ref="k2",
    ...              pause=1.5)])
    >>> [d.start for d in retime_dialogue(SceneIR(timeline=[shot])).timeline[0].dialogue]
    [0.0, 2.0]
    """
    for shot in scene.timeline:
        if timed_shots_only and all(
            line.pause is None and line.at is None for line in shot.dialogue
        ):
            continue
        cursor = 0.0
        for line in shot.dialogue:
            if line.duration is None:
                break
            line.start = line.planned_start(cursor)
            cursor = line.start + float(line.duration)
    return scene


# -----------------------------------------------------------------------------
# Cache keys — the SSOT for what an audio / viseme artifact is a function of
# -----------------------------------------------------------------------------


def audio_key(
    text: str,
    voice_id: str,
    tts_name: str,
    effects: Mapping[str, float] | None = None,
    *,
    provider_voice: str | None = None,
    options: Mapping[str, Any] | None = None,
    takes: Mapping[str, Any] | None = None,
    take: int | None = None,
    roll: int | None = None,
) -> str:
    """Content key of a line's audio: text, voice, provider, and — only when the
    voice declares them — its effects, the provider voice it names (an#194),
    the provider's synthesis options (model, settings, seed, audio tags —
    an#209). With none of them, the payload is exactly the pre-effects one, so
    every key a project already has is unchanged. ``take`` (1, 2, … — never 0)
    and ``roll`` (1, 2, … after ``an voices reroll``) key one candidate take of
    a best-of-N line; take 0 of roll 0 is the single-take request and keeps its
    key. ``takes`` (:func:`an.audio.takes.takes_choice_part`) keys the CHOICE
    among a line's takes — the record in ``mall["takes"]``, not an audio blob.

    >>> audio_key("hi", "default", "offline") == audio_key(
    ...     "hi", "default", "offline", {}, provider_voice=None, options={},
    ...     takes=None, take=0, roll=0)
    True
    """
    payload: dict[str, Any] = {"text": text, "voice": voice_id, "tts": tts_name}
    if effects:
        payload["effects"] = dict(effects)
    if provider_voice:
        payload["provider_voice"] = provider_voice
    if options:
        payload["options"] = dict(options)
    if takes:
        payload["takes"] = dict(takes)
    if take:
        payload["take"] = int(take)
    if roll:
        payload["roll"] = int(roll)
    return _stable_hash(payload)


def synthesis_options(
    tts: TTSProvider,
    line: Any,
    mall: Mapping[str, MutableMapping] | None,
    voice_id: str,
) -> dict[str, Any]:
    """The provider-specific ``synthesize`` kwargs for ``line`` in ``voice_id``.

    ``{}`` for a provider without a ``synthesis_options`` hook (offline,
    mac_say) and for a voice written for another provider — which is what
    keeps their cache keys where they were.
    """
    hook = getattr(tts, "synthesis_options", None)
    if hook is None:
        return {}
    doc = voice_document(mall, voice_id)
    if not voice_applies(doc, tts.name):
        doc = {}
    return dict(
        hook(
            doc,
            emotion=getattr(line, "emotion", None),
            direction=getattr(line, "direction", None),
        )
        or {}
    )


def viseme_key(audio_key_: str, lipsync_name: str, transcript: str) -> str:
    """Content key of a line's viseme track (a function of the audio HEARD)."""
    return _stable_hash(
        {"audio_key": audio_key_, "lipsync": lipsync_name, "transcript": transcript}
    )


def takes_cost_message(
    lines: list[tuple[str, "_LineRequest"]],
    tts: TTSProvider,
    audio_store: Mapping | None,
) -> str:
    """What synthesizing ``lines`` will bill, when any of them takes best-of-N; else ``""``.

    Counts only the requests not already in ``audio_store`` (a cached take is
    free; a recorded take is restored, never billed), and the provider's billed
    characters per request (its ``billed_characters(text, **options)`` hook —
    ElevenLabs counts the audio tags too). A provider without the hook bills no
    characters, and the message says so.
    """
    if not any(req.spec is not None and req.cache_key is None for _, req in lines):
        return ""
    billed = getattr(tts, "billed_characters", None) is not None
    requests = characters = cached = takes_lines = billed_lines = 0
    seen: set[str] = set()  # two lines saying the same thing share their takes
    for text, req in lines:
        if req.spec is not None and req.cache_key is not None:
            continue  # a recorded take: restored from the store
        ident = req.choice_key or req.cache_key
        if ident in seen or (
            req.spec is None and audio_store is not None and ident in audio_store
        ):
            continue
        seen.add(ident)
        before = requests
        for _take, options, key in req.take_requests():
            in_store = audio_store is not None and key in audio_store
            if key in seen or in_store:
                cached += req.spec is not None and in_store
                continue
            seen.add(key)
            requests += 1
            characters += _billed_characters(req.tts, text, options)
        if requests > before:
            billed_lines += 1
            takes_lines += req.spec is not None
    if not requests:
        return ""
    bill = f"{characters:,} billed characters" if billed else "not billed per character"
    return (
        f"best-of-N takes: {requests} {tts.name} request(s) for {billed_lines} line(s) "
        f"({takes_lines} with several takes; {cached} take(s) already cached), {bill}"
    )


def _older_scorer_message(reqs: list["_LineRequest"]) -> str:
    """Which lines keep a take chosen by an older scorer version (kept, reported)."""
    older = [r for r in reqs if r.older_scorer is not None]
    if not older:
        return ""
    first = older[0]
    texts = ", ".join(repr(r.text[:40]) for r in older[:5]) + (" …" if len(older) > 5 else "")
    return (
        f"{len(older)} line(s) keep the take chosen by an older scorer "
        f"({first.scorer.name} {first.older_scorer}; now {first.scorer.version}): "
        f"{texts}. The recorded takes are kept; re-choose one from its cached takes "
        "with `an voices rescore <project> <words of the line>`"
    )


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


@dataclass
class _LineRequest:
    """Everything a line's audio is a function of, resolved once — the SSOT the
    stamp, the cost estimate and the synthesis all read.

    ``cache_key`` is the key of the audio the line KEEPS: for a best-of-N line,
    the chosen take's own heard key (from the record), or ``None`` while a
    choice is still to be made."""

    tts: TTSProvider
    text: str
    voice_id: str
    named: str | None
    options: dict[str, Any]
    effects: Mapping[str, float]
    raw_key: str
    cache_key: str | None
    spec: TakesSpec | None = None
    scorer: TakeScorer | None = None
    choice_key: str | None = None
    record: dict[str, Any] | None = None
    roll: int = 0
    restore: bool = False  # the kept audio is gone, the chosen raw take is cached
    hand_edit: bool = False  # the record's `chosen` was edited by hand
    older_scorer: str | None = None  # the version that chose, when not the current one

    @property
    def handed_voice(self) -> str:
        """The voice id the provider is handed."""
        return self.named or self.voice_id

    @property
    def needs_work(self) -> bool:
        """A recorded take that must be restored, or a hand edit to honour."""
        return self.restore or self.hand_edit

    def take_key(self, take: int, *, heard: bool) -> str:
        """The key of candidate ``take`` of this roll: its raw audio, or (``heard``)
        the audio with the voice's effects applied. Take 0 of roll 0 is the
        single-take request: its keys are the plain line's."""
        return audio_key(
            self.text,
            self.voice_id,
            self.tts.name,
            self.effects if heard else None,
            provider_voice=self.named,
            options=_take_options(self.tts, self.options, take),
            take=take,
            roll=self.roll,
        )

    def take_requests(self):
        """``(take, options, raw_key)`` per candidate take (only take 0 without ``spec``)."""
        n = self.spec.n if self.spec is not None else 1
        for take in range(n):
            yield take, _take_options(self.tts, self.options, take), self.take_key(
                take, heard=False
            )


def _line_request(
    line: Any,
    mall: Mapping[str, MutableMapping] | None,
    tts: TTSProvider,
    voice_id: str,
    *,
    effects: Mapping[str, float] | None = None,
    takes: TakesSpec | None = _FROM_VOICE,
    take_scorer: TakeScorerFactory = make_take_scorer,
    strict: bool = True,
) -> _LineRequest:
    """Resolve ``line``'s audio request in ``voice_id``: keys, options, effects, and —
    for a best-of-N line — its recorded choice.

    ``strict`` (the render) raises :class:`~an.audio.takes.TakeLostError` for a
    recorded take whose audio is gone, and refuses a choice the scorer could not
    make (no ffmpeg) — both before any request.
    """
    if effects is None:
        effects = voice_effects(mall, voice_id)
    named = provider_voice(mall, voice_id, tts_name=tts.name)
    options = synthesis_options(tts, line, mall, voice_id)
    if takes is _FROM_VOICE:
        takes = voice_takes(
            mall,
            voice_id,
            direction=getattr(line, "direction", None),
            tts_name=tts.name,
            repeatable=bool(getattr(tts, "repeatable", False)),
        )
    raw_key = audio_key(line.text, voice_id, tts.name, provider_voice=named, options=options)
    req = _LineRequest(
        tts=tts,
        text=line.text,
        voice_id=voice_id,
        named=named,
        options=options,
        effects=effects,
        raw_key=raw_key,
        cache_key=(
            audio_key(line.text, voice_id, tts.name, effects, provider_voice=named, options=options)
            if takes is None
            else None
        ),
        spec=takes,
    )
    if takes is None:
        return req
    req.scorer = take_scorer(takes)
    req.choice_key = audio_key(
        line.text,
        voice_id,
        tts.name,
        effects,
        provider_voice=named,
        options=options,
        takes=takes_choice_part(req.scorer, takes.n),
    )
    record = read_takes_record(
        mall.get(TAKES_STORE) if mall is not None else None, req.choice_key
    )
    req.record = record
    chosen = record.get("chosen") if record is not None else None
    if chosen is None:  # never chosen, or a rescore / reroll pending
        req.roll = int(record.get("roll", 0)) if record is not None else 0
        check = getattr(req.scorer, "check_available", None)
        if strict and check is not None:
            check()
        return req
    req.roll = int(record.get("roll", 0))
    entry = record["takes"][chosen]
    req.cache_key = req.take_key(chosen, heard=True)
    req.hand_edit = record.get("digest") != entry.get("heard_digest")
    recorded = (record.get("scorer") or {}).get("version")
    if recorded != req.scorer.version:
        req.older_scorer = str(recorded)
    audio_store = mall.get("audio") if mall is not None else None
    if audio_store is not None and req.cache_key not in audio_store:
        if req.take_key(chosen, heard=False) in audio_store:
            req.restore = True
        elif strict:
            raise TakeLostError(
                f"the recorded take {chosen} of {line.text!r} (voice {voice_id!r}, "
                f"sha256 {str(entry.get('heard_digest'))[:12]}) is gone from the audio "
                f"store, raw and processed; nothing was billed. Restore the audio, or "
                f"{REROLL_HINT}"
            )
    return req


def _take_options(tts: TTSProvider, options: Mapping[str, Any], take: int) -> dict[str, Any]:
    """The provider's request for candidate ``take`` (its optional ``take_options`` hook)."""
    hook = getattr(tts, "take_options", None)
    if take == 0 or hook is None:
        return dict(options)
    return dict(hook(options, take))


def _billed_characters(tts: TTSProvider, text: str, options: Mapping[str, Any]) -> int:
    """Characters one request bills (the provider's hook; ``0`` without one)."""
    hook = getattr(tts, "billed_characters", None)
    return int(hook(text, **options)) if hook is not None else 0


def _clip_bytes(clip: AudioClip) -> bytes:
    """The clip's audio bytes, read from its path when it has no bytes in memory."""
    data = clip.bytes_
    if data is None and clip.path is not None:
        data = clip.path.read_bytes()
    if data is None:
        raise AudioPipelineError("the TTS clip carries no audio bytes to score or keep")
    return data


def _load_or_choose_take(
    mall: Mapping[str, MutableMapping] | None, req: _LineRequest
) -> AudioClip:
    """The audio a best-of-N line keeps.

    With a recorded choice: the chosen take, read back — or restored from its
    raw take with the effects re-applied — and checked against the record's
    digest; a hand-edited ``chosen`` is honoured and the record updated. With
    none (or a rescore / reroll pending): the takes of the current roll are
    synthesized where not cached, scored on the audio heard, the best kept
    under its own heard key, and the choice recorded.
    """
    if req.cache_key is not None:
        return _restore_recorded_take(mall, req)

    audio_store = mall.get("audio") if mall is not None else None
    candidates = []
    for take, options, raw_key in req.take_requests():
        raw = _load_or_synthesize(
            req.tts, req.text, req.handed_voice, mall, raw_key, options=options
        )
        heard_key = req.take_key(take, heard=True)
        heard = (
            _load_or_apply_effects(raw, req.effects, mall, heard_key) if req.effects else raw
        )
        data = _clip_bytes(heard)
        candidates.append(
            (take, raw_key, heard_key, _clip_bytes(raw), data, req.scorer.score(data, req.text))
        )
    best = choose_take([c[5] for c in candidates])
    req.cache_key, kept = candidates[best][2], candidates[best][4]
    if audio_store is not None and req.cache_key not in audio_store:
        audio_store[req.cache_key] = kept

    previous = req.record or {}
    record: dict[str, Any] = {
        "record_version": TAKES_RECORD_VERSION,
        "choice_key": req.choice_key,
        "text": req.text,
        "voice": req.voice_id,
        "tts": req.tts.name,
        "roll": req.roll,
        "scorer": scorer_identity(req.scorer),
        "chosen": best,
        "digest": audio_digest(kept),
        "audio_key": req.cache_key,
        "takes": [
            {
                "take": take,
                "audio_key": raw_key,
                "digest": audio_digest(raw),
                "heard_key": heard_key,
                "heard_digest": audio_digest(data),
                "score": list(score.value),
                **dict(score.detail),
            }
            for take, raw_key, heard_key, raw, data, score in candidates
        ],
        "history": list(previous.get("history", [])),
    }
    write_takes_record(mall.get(TAKES_STORE) if mall is not None else None, req.choice_key, record)
    req.record = record
    return _kept_clip(kept, req)


def _restore_recorded_take(
    mall: Mapping[str, MutableMapping] | None, req: _LineRequest
) -> AudioClip:
    """The recorded take, from the store; never a request (see ``_line_request``)."""
    audio_store = mall["audio"]
    record = req.record
    chosen = record["chosen"]
    entry = record["takes"][chosen]
    if req.restore:
        raw = audio_store[req.take_key(chosen, heard=False)]
        kept = apply_voice_effects(raw, req.effects) if req.effects else raw
        audio_store[req.cache_key] = kept
        req.restore = False
    else:
        kept = audio_store[req.cache_key]
    expected = entry.get("heard_digest")
    if expected and audio_digest(kept) != expected:
        warnings.warn(
            f"the audio kept for {req.text!r} (take {chosen}) is not the audio its "
            f"takes record names (sha256 {audio_digest(kept)[:12]}, recorded "
            f"{str(expected)[:12]}): it was replaced, or the effects chain differs on "
            f"this machine. It is used as is; {REROLL_HINT}",
            TakeDigestWarning,
            stacklevel=4,
        )
    if req.hand_edit:
        _honour_hand_edit(mall, req)
    return _kept_clip(kept, req)


def _honour_hand_edit(mall: Mapping[str, MutableMapping], req: _LineRequest) -> None:
    """A hand-edited ``chosen`` wins (ADR 0003 decision 3): the record is updated
    to it, says ``superseded_by: hand``, keeps what it replaced in ``history``,
    and the decision log records it."""
    record = dict(req.record)
    chosen = record["chosen"]
    entry = record["takes"][chosen]
    replaced = next(
        (t.get("take") for t in record["takes"] if t.get("heard_digest") == record.get("digest")),
        None,
    )
    record["history"] = [
        *record.get("history", []),
        {
            "chosen": replaced,
            "digest": record.get("digest"),
            "roll": record.get("roll", 0),
            "scorer": record.get("scorer"),
            "reason": "superseded by a hand edit",
        },
    ]
    record.update(
        digest=entry.get("heard_digest"),
        audio_key=req.cache_key,
        superseded_by="hand",
    )
    write_takes_record(mall.get(TAKES_STORE), req.choice_key, record)
    decisions = mall.get("decisions")
    if decisions is not None and hasattr(decisions, "append"):
        decisions.append(
            kind="takes_hand_edit",
            body={"text": req.text, "voice": req.voice_id, "from_take": replaced,
                  "to_take": chosen, "record": req.choice_key},
        )
    req.record, req.hand_edit = record, False


def _kept_clip(kept: bytes, req: _LineRequest) -> AudioClip:
    """The clip of the kept audio (a WAV at the effect rate when effects ran)."""
    clip = _clip_from_bytes(kept, req.voice_id, req.text)
    if req.effects:
        clip.sample_rate = EFFECT_SAMPLE_RATE
    return clip


def _clip_from_bytes(data: bytes, voice_id: str, text: str) -> AudioClip:
    """A clip read back from the audio store (its duration read from the bytes)."""
    return AudioClip(
        bytes_=data, duration=_wav_duration(data), voice_id=voice_id, transcript=text
    )


def retake_lines(
    scene: SceneIR,
    mall: Mapping[str, MutableMapping],
    match: str,
    *,
    tts: TTSProvider,
    rescore: bool = False,
    take_scorer: TakeScorerFactory = make_take_scorer,
) -> list[str]:
    """Mark the recorded takes of the lines whose text contains ``match`` to be
    chosen again on the next render; one message per matching line.

    ``rescore=True`` re-chooses among the takes already synthesized (with the
    current scorer; nothing billed while they are cached); otherwise a new roll
    of takes is synthesized (billed — the render prints the cost first). Either
    way the replaced choice is kept in the record's ``history``, and the new
    take has its own key, so its visemes and word timings are aligned afresh.
    This is the only way a recorded take is replaced (ADR 0003).
    """
    needle = match.lower()
    out: list[str] = []
    for shot in scene.timeline:
        for line in shot.dialogue:
            if needle not in line.text.lower():
                continue
            voice_id = line_voice_id(line, shot, mall)
            req = _line_request(line, mall, tts, voice_id, take_scorer=take_scorer, strict=False)
            if req.spec is None:
                out.append(f"{line.text!r}: its voice declares no takes under {tts.name}")
                continue
            record = req.record
            if record is None or record.get("chosen") is None:
                out.append(f"{line.text!r}: no take recorded yet; the next render chooses one")
                continue
            roll = int(record.get("roll", 0))
            write_takes_record(
                mall.get(TAKES_STORE),
                req.choice_key,
                {
                    "record_version": TAKES_RECORD_VERSION,
                    "choice_key": req.choice_key,
                    "text": line.text,
                    "voice": voice_id,
                    "tts": tts.name,
                    "roll": roll if rescore else roll + 1,
                    "chosen": None,
                    "pending": "rescore" if rescore else "reroll",
                    "takes": [],
                    "history": [
                        *record.get("history", []),
                        {
                            "chosen": record["chosen"],
                            "digest": record.get("digest"),
                            "roll": roll,
                            "scorer": record.get("scorer"),
                            "reason": "rescore" if rescore else "reroll",
                        },
                    ],
                },
            )
            out.append(
                f"{line.text!r}: take {record['chosen']} released; the next render "
                + ("re-chooses from the cached takes" if rescore else f"synthesizes {req.spec.n} new takes (roll {roll + 1})")
            )
    if not out:
        out.append(f"no dialogue line contains {match!r}")
    return out


def _load_or_apply_effects(
    raw: AudioClip,
    effects: Mapping[str, float],
    mall: Mapping[str, MutableMapping] | None,
    cache_key: str,
) -> AudioClip:
    """The clip with ``effects`` applied, cached under ``cache_key`` (a WAV)."""
    if mall is not None and "audio" in mall and cache_key in mall["audio"]:
        wav = mall["audio"][cache_key]
    else:
        source = raw.bytes_
        if source is None and raw.path is not None:
            source = raw.path.read_bytes()
        if source is None:
            raise AudioPipelineError(
                "a voice declares effects but the TTS clip carries no audio bytes"
            )
        wav = apply_voice_effects(source, effects)
        if mall is not None and "audio" in mall:
            mall["audio"][cache_key] = wav
    return AudioClip(
        bytes_=wav,
        duration=_wav_duration(wav),
        sample_rate=EFFECT_SAMPLE_RATE,
        channels=raw.channels,
        voice_id=raw.voice_id,
        transcript=raw.transcript,
    )


def _to_ir_viseme_track(track: VisemeTrack) -> IRVisemeTrack:
    """Translate the audio-side dataclass to the IR's Pydantic model."""
    return IRVisemeTrack(
        keyframes=[VisemeKeyframe(time=v.time, viseme=v.code) for v in track.visemes]
    )


def _to_ir_word_timings(track: VisemeTrack) -> list[WordTimingIR] | None:
    """The track's word timings as IR models, or ``None`` when it has none.

    Clamped to ``[0, track.duration]`` the way the visemes are: transcribers
    "occasionally round the last word's end past the audio's actual length",
    and a caption cue reads ``line.start + word.end`` (an#96 review).
    """
    if track.words is None:
        return None
    out = []
    for text, start, end in track.words:
        hi = float(track.duration) if track.duration else float(end)
        e = min(max(0.0, float(end)), hi)
        s = min(max(0.0, float(start)), e)
        out.append(WordTimingIR(text=text, start=s, end=e))
    return out


def _emits_word_timings(lipsync: LipSyncProvider) -> bool:
    """Whether ``lipsync`` declares that it fills ``VisemeTrack.words``."""
    return bool(getattr(lipsync, "emits_word_timings", False))


def _load_or_synthesize(
    tts: TTSProvider,
    text: str,
    voice_id: str,
    mall: Mapping[str, MutableMapping] | None,
    cache_key: str,
    *,
    options: Mapping[str, Any] | None = None,
) -> AudioClip:
    if mall is not None and "audio" in mall and cache_key in mall["audio"]:
        wav_bytes = mall["audio"][cache_key]
        # Re-derive duration from WAV header for fidelity.
        duration = _wav_duration(wav_bytes)
        return AudioClip(
            bytes_=wav_bytes, duration=duration, voice_id=voice_id, transcript=text
        )
    clip = tts.synthesize(text, voice_id, **(options or {}))
    if mall is not None and "audio" in mall and clip.bytes_ is not None:
        mall["audio"][cache_key] = clip.bytes_
    return clip


def _load_or_align(
    lipsync: LipSyncProvider,
    audio: AudioClip,
    transcript: str,
    mall: Mapping[str, MutableMapping] | None,
    cache_key: str,
) -> VisemeTrack:
    if mall is not None and "visemes" in mall and cache_key in mall["visemes"]:
        try:
            payload = json.loads(mall["visemes"][cache_key].decode("utf-8"))
            words = payload.get("words")
            cached = VisemeTrack(
                visemes=[
                    Viseme(
                        time=v["time"],
                        code=v["code"],
                        intensity=v.get("intensity", 1.0),
                    )
                    for v in payload.get("visemes", [])
                ],
                convention=payload.get("convention", lipsync.convention),
                duration=payload.get("duration", audio.duration),
                words=(
                    [(str(w[0]), float(w[1]), float(w[2])) for w in words]
                    if words is not None
                    else None
                ),
            )
            # A payload written before an#96 by a provider that HAS words is
            # missing them; re-align once so the sidecar carries them. The key
            # is the same, so the rewrite below replaces the old payload.
            if cached.words is not None or not _emits_word_timings(lipsync):
                return cached
        except Exception:
            # Fall through to recompute; cache content was malformed.
            pass
    track = lipsync.align(audio, transcript)
    if _emits_word_timings(lipsync) and track.words is None:
        # The declaration is what `already_done` trusts: a provider that
        # claims words and returns none would be re-aligned on every run,
        # silently — the exact loop the flag exists to prevent (an#96 review).
        raise AudioPipelineError(
            f"lip-sync provider {lipsync.name!r} declares emits_word_timings but "
            "returned a track with words=None; set the flag False or fill words."
        )
    if mall is not None and "visemes" in mall:
        payload = {
            "visemes": [asdict(v) for v in track.visemes],
            "convention": track.convention,
            "duration": track.duration,
            "words": (
                [[w[0], float(w[1]), float(w[2])] for w in track.words]
                if track.words is not None
                else None
            ),
        }
        mall["visemes"][cache_key] = json.dumps(payload).encode("utf-8")
    return track


def _wav_duration(wav_bytes: bytes) -> float:
    """Compatibility shim: duration of cached audio bytes.

    Tries the stdlib `wave` module first (fast, no subprocess). Falls back to
    ffprobe for non-WAV containers (mp3 from ElevenLabs etc.). Returns 0.0
    if both fail; the renderer will still mux the audio fine because ffmpeg
    sniffs format itself.
    """
    import io
    import wave

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n = wf.getnframes()
            rate = wf.getframerate()
            return n / rate if rate else 0.0
    except wave.Error:
        return _ffprobe_duration(wav_bytes)


def _ffprobe_duration(audio_bytes: bytes) -> float:
    """Use ffprobe to read the duration of an arbitrary audio container."""
    import shutil
    import subprocess
    import tempfile

    if shutil.which("ffprobe") is None:
        return 0.0
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                tmp_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        s = result.stdout.strip()
        return float(s) if s else 0.0
    except Exception:
        return 0.0
    finally:
        import os

        try:
            os.unlink(tmp_path)
        except OSError:
            pass
