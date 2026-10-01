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
    TAKES_RECORD_VERSION,
    TAKES_STORE,
    TakeScorer,
    TakesSpec,
    audio_digest,
    choose_take,
    make_take_scorer,
    takes_key_part,
    voice_takes,
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


class TakeLostWarning(UserWarning):
    """A line's recorded best take is gone from the audio store and was chosen again."""


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
    the best under the line's key and records the choice in ``mall["takes"]``.
    A line whose kept take is cached is never re-rolled.
    """
    tts = tts or default_tts()
    lipsync = lipsync or default_lipsync()
    voice_id = voice_id or dialogue.voice_ref or DEFAULT_VOICE
    req = _line_request(
        dialogue, mall, tts, voice_id, effects=effects, takes=takes, take_scorer=take_scorer
    )
    if req.spec is None:
        audio_clip = _load_or_synthesize(
            tts, dialogue.text, req.handed_voice, mall, req.raw_key, options=req.options
        )
        if req.cache_key != req.raw_key:
            audio_clip = _load_or_apply_effects(audio_clip, req.effects, mall, req.cache_key)
    else:
        audio_clip = _load_or_choose_take(tts, dialogue.text, voice_id, mall, req)

    viseme_cache_key = viseme_key(req.cache_key, lipsync.name, dialogue.text)
    track = _load_or_align(lipsync, audio_clip, dialogue.text, mall, viseme_cache_key)
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
    malformed voice (an effect, a ``takes``) fails before a credit is spent;
    and when any line will synthesize best-of-N takes, ``announce`` (default:
    a line on stderr; ``None`` for silence) is told what the run will bill —
    takes and provider characters — before the first request.
    """
    tts = tts or default_tts()
    lipsync = lipsync or default_lipsync()
    voice_default = DEFAULT_VOICE
    audio_store = mall.get("audio") if mall is not None else None
    viseme_store = mall.get("visemes") if mall is not None else None
    pending: list[tuple[Dialogue, str, _LineRequest]] = []
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
            expected_audio_ref = req.cache_key
            expected_viseme_ref = viseme_key(
                expected_audio_ref, lipsync.name, line.text
            )
            already_done = (
                line.audio_ref == expected_audio_ref
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

    if announce is not None:
        message = takes_cost_message(
            [(line.text, req) for line, _, req in pending], tts, audio_store
        )
        if message:
            announce(message)

    for line, voice_id, req in pending:
        # Never synthesized, or the providers changed: synthesize (the
        # content-keyed stores make a mere re-stamp free).
        audio, track = produce_audio_for_dialogue(
            line,
            mall,
            tts=tts,
            lipsync=lipsync,
            effects=req.effects,
            voice_id=voice_id,
            takes=req.spec,
            take_scorer=take_scorer,
        )
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
) -> str:
    """Content key of a line's audio: text, voice, provider, and — only when the
    voice declares them — its effects, the provider voice it names (an#194),
    the provider's synthesis options (model, settings, seed, audio tags —
    an#209) and its best-of-N ``takes`` (the number and the scorer that chose;
    :func:`an.audio.takes.takes_key_part`). With none of them, the payload is
    exactly the pre-effects one, so every key a project already has is
    unchanged. ``take`` (1, 2, … — never 0) keys one candidate take's RAW
    audio; take 0 is the single-take request and keeps its key.

    >>> audio_key("hi", "default", "offline") == audio_key(
    ...     "hi", "default", "offline", {}, provider_voice=None, options={},
    ...     takes=None, take=0)
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
    free), and the provider's billed characters per request (its optional
    ``billed_characters(text, **options)`` hook — ElevenLabs counts the audio
    tags too — else the text's length).
    """
    if not any(req.spec is not None for _, req in lines):
        return ""
    requests = characters = cached = takes_lines = billed_lines = 0
    seen: set[str] = set()  # two lines saying the same thing share their takes
    for text, req in lines:
        if req.cache_key in seen or (
            audio_store is not None and req.cache_key in audio_store
        ):
            continue
        seen.add(req.cache_key)
        before = requests
        for _take, options, key in req.take_requests():
            if key in seen or (audio_store is not None and key in audio_store):
                cached += audio_store is not None and key in audio_store
                continue
            seen.add(key)
            requests += 1
            characters += _billed_characters(req.tts, text, options)
        if requests > before:
            billed_lines += 1
            takes_lines += req.spec is not None
    if not requests:
        return ""
    return (
        f"best-of-N takes: {requests} {tts.name} request(s) for {billed_lines} line(s) "
        f"({takes_lines} with several takes; {cached} take(s) already cached), "
        f"{characters:,} billed characters"
    )


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------


@dataclass
class _LineRequest:
    """Everything a line's audio is a function of, resolved once — the SSOT the
    stamp, the cost estimate and the synthesis all read."""

    tts: TTSProvider
    text: str
    voice_id: str
    named: str | None
    options: dict[str, Any]
    effects: Mapping[str, float]
    raw_key: str
    cache_key: str
    spec: TakesSpec | None = None
    scorer: TakeScorer | None = None

    @property
    def handed_voice(self) -> str:
        """The voice id the provider is handed."""
        return self.named or self.voice_id

    def take_requests(self):
        """``(take, options, raw_key)`` per candidate take (only take 0 without ``spec``)."""
        n = self.spec.n if self.spec is not None else 1
        for take in range(n):
            options = _take_options(self.tts, self.options, take)
            key = (
                self.raw_key
                if take == 0
                else audio_key(
                    self.text,
                    self.voice_id,
                    self.tts.name,
                    provider_voice=self.named,
                    options=options,
                    take=take,
                )
            )
            yield take, options, key


def _line_request(
    line: Any,
    mall: Mapping[str, MutableMapping] | None,
    tts: TTSProvider,
    voice_id: str,
    *,
    effects: Mapping[str, float] | None = None,
    takes: TakesSpec | None = _FROM_VOICE,
    take_scorer: TakeScorerFactory = make_take_scorer,
) -> _LineRequest:
    """Resolve ``line``'s audio request in ``voice_id``: keys, options, effects, takes."""
    if effects is None:
        effects = voice_effects(mall, voice_id)
    named = provider_voice(mall, voice_id, tts_name=tts.name)
    options = synthesis_options(tts, line, mall, voice_id)
    if takes is _FROM_VOICE:
        takes = voice_takes(
            mall, voice_id, direction=getattr(line, "direction", None), tts_name=tts.name
        )
    scorer = take_scorer(takes) if takes is not None else None
    raw_key = audio_key(line.text, voice_id, tts.name, provider_voice=named, options=options)
    cache_key = audio_key(
        line.text,
        voice_id,
        tts.name,
        effects,
        provider_voice=named,
        options=options,
        takes=takes_key_part(scorer, takes.n) if takes is not None else None,
    )
    return _LineRequest(
        tts=tts,
        text=line.text,
        voice_id=voice_id,
        named=named,
        options=options,
        effects=effects,
        raw_key=raw_key,
        cache_key=cache_key,
        spec=takes,
        scorer=scorer,
    )


def _take_options(tts: TTSProvider, options: Mapping[str, Any], take: int) -> dict[str, Any]:
    """The provider's request for candidate ``take`` (its optional ``take_options`` hook)."""
    hook = getattr(tts, "take_options", None)
    if take == 0 or hook is None:
        return dict(options)
    return dict(hook(options, take))


def _billed_characters(tts: TTSProvider, text: str, options: Mapping[str, Any]) -> int:
    """Characters one request bills (the provider's hook, else the text's length)."""
    hook = getattr(tts, "billed_characters", None)
    return int(hook(text, **options)) if hook is not None else len(text)


def _clip_bytes(clip: AudioClip) -> bytes:
    """The clip's audio bytes, read from its path when it has no bytes in memory."""
    data = clip.bytes_
    if data is None and clip.path is not None:
        data = clip.path.read_bytes()
    if data is None:
        raise AudioPipelineError("the TTS clip carries no audio bytes to score or keep")
    return data


def _load_or_choose_take(
    tts: TTSProvider,
    text: str,
    voice_id: str,
    mall: Mapping[str, MutableMapping] | None,
    req: _LineRequest,
) -> AudioClip:
    """The line's kept take: from the store when chosen before, else chosen now.

    Choosing synthesizes the takes not cached (each under its own raw key),
    applies the voice's effects to each in memory, scores what the viewer
    would hear, stores the winner under ``req.cache_key`` and records the
    choice in ``mall["takes"]``. With every take cached the scorer is
    deterministic, so the same take is chosen again.
    """
    audio_store = mall.get("audio") if mall is not None else None
    if audio_store is not None and req.cache_key in audio_store:
        return _clip_from_bytes(audio_store[req.cache_key], voice_id, text)

    candidates = []
    for take, options, key in req.take_requests():
        raw = _load_or_synthesize(tts, text, req.handed_voice, mall, key, options=options)
        heard = _load_or_apply_effects(raw, req.effects, None, key) if req.effects else raw
        data = _clip_bytes(heard)
        candidates.append((take, key, raw, data, req.scorer.score(data, text)))
    best = choose_take([c[4] for c in candidates])
    kept = candidates[best][3]

    record: dict[str, Any] = {
        "record_version": TAKES_RECORD_VERSION,
        "audio_key": req.cache_key,
        "text": text,
        "voice": voice_id,
        "tts": tts.name,
        "scorer": takes_key_part(req.scorer, req.spec.n),
        "chosen": best,
        "digest": audio_digest(kept),
        "takes": [
            {
                "take": take,
                "audio_key": key,
                "digest": audio_digest(_clip_bytes(raw)),
                "score": list(score.value),
                **dict(score.detail),
            }
            for take, key, raw, _, score in candidates
        ],
    }
    takes_store = mall.get(TAKES_STORE) if mall is not None else None
    if takes_store is not None and req.cache_key in takes_store:
        previous = json.loads(bytes(takes_store[req.cache_key]).decode("utf-8"))
        if previous.get("digest") != record["digest"]:
            warnings.warn(
                f"the recorded best take of {text!r} (take {previous.get('chosen')}, "
                f"sha256 {str(previous.get('digest'))[:12]}) is no longer in the audio "
                f"store and could not be restored from its cached takes; kept take "
                f"{best} of {req.spec.n} instead",
                TakeLostWarning,
                stacklevel=3,
            )
            record["supersedes"] = previous.get("digest")
    if audio_store is not None:
        audio_store[req.cache_key] = kept
    if takes_store is not None:
        takes_store[req.cache_key] = json.dumps(record, indent=1, sort_keys=True).encode(
            "utf-8"
        )
    clip = _clip_from_bytes(kept, voice_id, text)
    if req.effects:
        clip.sample_rate = EFFECT_SAMPLE_RATE
    return clip


def _clip_from_bytes(data: bytes, voice_id: str, text: str) -> AudioClip:
    """A clip read back from the audio store (its duration read from the bytes)."""
    return AudioClip(
        bytes_=data, duration=_wav_duration(data), voice_id=voice_id, transcript=text
    )


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
