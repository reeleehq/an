"""Best-of-N takes: re-roll a line, score every take, keep the best, record the choice.

An expressive TTS model does not repeat itself: ``eleven_v3`` returned three
different files for three byte-identical requests (same text, voice, settings
and seed), and the spread between two takes of one line was larger than the
effect of any voice setting. So the way to land a delivery on its measured
targets is to synthesize a few takes and keep the one that measures closest.

A voice document opts in with ``takes``::

    {"voice_id": "...", "model_id": "eleven_v3",
     "takes": {"n": 3,                                  # takes per line (1 = off)
               "targets": {"articulation_rate_sps": [5.2, 6.3], ...},
               "cues": {"deadpan": {"n": 4, "targets": {...}}}}}

- ``n`` — takes per line; ``1`` (the default) is today's single take, byte for
  byte. A bare integer (``takes: 3``) is ``{"n": 3}``.
- ``targets`` — ``[low, high]`` prosody targets (:data:`an.verify.prosody.METRICS`)
  the default scorer measures each take against. A style's targets are named by
  role in its spec; :func:`style_voice_role` resolves those names into values
  when the style is applied, so the voice document holds numbers, never names.
- ``reference_hz`` — the voice's neutral median pitch, for a ``register_st`` target.
- ``cues`` — per-line opt-in: a line whose ``{direction}`` carries one of these
  cues uses that entry's ``n`` / ``targets`` / ``reference_hz`` over the
  voice's (the first matching cue, in the line's order, wins). So a narrator
  can re-roll only its ``{deadpan}`` punchlines, scored as punchlines.
- ``scorer`` — the scorer's name (default ``prosody``); the scorer itself is a
  seam (:class:`TakeScorer`, the pipeline's ``take_scorer=``).

How the pipeline uses it (:mod:`an.audio.pipeline`):

1. Take ``0`` is the request a single take makes, under the same key — turning
   takes on for a line already synthesized reuses that take and pays for
   ``n - 1`` more. Take ``i`` adds ``take: i`` to its key, and a provider may
   vary its request per take (ElevenLabs offsets a declared ``seed`` by ``i``).
   Every take's raw audio is cached like any line's.
2. Each take is scored on the audio the viewer hears (the voice's effects
   applied, so a ``tempo`` counts toward the rate); the lowest score wins, ties
   to the lower take index. Scoring is deterministic, so with the takes cached
   the same take always wins.
3. The winner is stored under the line's audio key, which gains a ``takes``
   part (``n``, the scorer's name, version and configuration) only when ``n``
   is above 1 — so every existing key is unchanged — and the choice is
   recorded in ``mall["takes"]`` under that key: the chosen take, the sha256 of
   the audio kept, every take's key, digest and score, and the scorer. A
   re-render finds the line's audio and never re-rolls (ADR 0003: nothing
   below the IR is re-asked); a change to the targets, ``n``, the scorer or its
   estimator is a different key and chooses again (ADR 0004).

>>> spec = takes_spec({"n": 3, "targets": {"f0_sd_st": [2, 4]}})
>>> spec.n, spec.scorer, dict(spec.targets)
(3, 'prosody', {'f0_sd_st': [2.0, 4.0]})
>>> takes_spec(None) is None and takes_spec(1) is None
True
>>> doc = {"n": 1, "cues": {"deadpan": {"n": 4, "targets": {"final_drop_st": [-3.6, -1.7]}}}}
>>> takes_spec(doc, direction=["deadpan"]).n, takes_spec(doc, direction=["excited"])
(4, None)
>>> takes_spec({"n": 3})
Traceback (most recent call last):
    ...
an.audio.takes.VoiceTakesError: takes: n=3 with the prosody scorer needs `targets` ([low, high] per metric) to choose by
>>> choose_take([TakeScore((0.5, 1.0)), TakeScore((0.0, 2.0)), TakeScore((0.0, 2.0))])
1
"""

from __future__ import annotations

import hashlib
import io
import math
import shutil
import tempfile
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

#: The key, in a voice document, declaring best-of-N takes.
TAKES_KEY: str = "takes"
#: The name of the store the choices are recorded in.
TAKES_STORE: str = "takes"
#: The scorer a ``takes`` declaration uses when it names none.
DEFAULT_SCORER: str = "prosody"
#: More takes than this per line is refused: each one is a billed request.
MAX_TAKES: int = 10
#: The shape of a record in ``mall["takes"]``; raised when a field changes meaning.
TAKES_RECORD_VERSION: int = 1
#: The prosody scorer's own version (its distance and tie-break); the
#: estimator's version (:data:`an.verify.prosody.ESTIMATOR_VERSION`) is joined to it.
PROSODY_SCORER_VERSION: str = "1"
#: The sample rate takes are decoded at for scoring — the one the targets were measured at.
SCORING_SAMPLE_RATE: int = 16000

_TAKES_FIELDS = frozenset({"n", "scorer", "targets", "reference_hz", "cues"})
_CUE_FIELDS = _TAKES_FIELDS - {"cues"}


class VoiceTakesError(ValueError):
    """A voice's ``takes`` declaration is malformed, or cannot be scored."""


@dataclass(frozen=True)
class TakesSpec:
    """The takes ONE line gets: how many, and what chooses between them."""

    n: int
    scorer: str = DEFAULT_SCORER
    targets: Mapping[str, Sequence[float]] = field(default_factory=dict)
    reference_hz: float | None = None


@dataclass(frozen=True)
class TakeScore:
    """A take's score — compared as a tuple, lower is better — and what it measured."""

    value: tuple[float, ...]
    detail: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class TakeScorer(Protocol):
    """Scores one take of a line. Deterministic: the same bytes score the same.

    ``name``, ``version`` and ``config`` enter the line's audio key, so a scorer
    that would choose differently must differ in one of them.
    """

    name: str
    version: str
    config: Mapping[str, Any]

    def score(self, audio: bytes, text: str) -> TakeScore:
        """Score ``audio`` (any container ffmpeg reads; WAV without it) speaking ``text``."""


# -----------------------------------------------------------------------------
# The declaration
# -----------------------------------------------------------------------------


def _check_entry(raw: Any, *, where: str, allowed: frozenset[str]) -> dict[str, Any]:
    """One ``takes`` mapping (the voice's or a cue's), validated and canonical."""
    if isinstance(raw, bool):
        raise VoiceTakesError(f"{where} must be a number of takes or a mapping, got {raw!r}")
    if isinstance(raw, int):
        raw = {"n": raw}
    if not isinstance(raw, Mapping):
        raise VoiceTakesError(
            f"{where} must be a number of takes or a mapping, got {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise VoiceTakesError(f"unknown {where} key(s) {unknown}; known: {sorted(allowed)}")
    out: dict[str, Any] = {}
    if "n" in raw:
        n = raw["n"]
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_TAKES:
            raise VoiceTakesError(
                f"{where}.n must be an integer from 1 to {MAX_TAKES} (each take is "
                f"a billed request), got {n!r}"
            )
        out["n"] = n
    if "scorer" in raw:
        if not isinstance(raw["scorer"], str) or not raw["scorer"]:
            raise VoiceTakesError(f"{where}.scorer must be a scorer name, got {raw['scorer']!r}")
        out["scorer"] = raw["scorer"]
    if "targets" in raw:
        out["targets"] = _check_targets(raw["targets"], where=f"{where}.targets")
    if raw.get("reference_hz") is not None:
        ref = raw["reference_hz"]
        if isinstance(ref, bool) or not isinstance(ref, (int, float)) or ref <= 0:
            raise VoiceTakesError(f"{where}.reference_hz must be a pitch in Hz, got {ref!r}")
        out["reference_hz"] = float(ref)
    return out


def _check_targets(raw: Any, *, where: str) -> dict[str, list[float]]:
    """Prosody targets as numbers — a role NAME is refused (resolve it when applying the style)."""
    from an.verify.prosody import ProsodyTargetError, validate_targets

    if isinstance(raw, str):
        raise VoiceTakesError(
            f"{where} is the name {raw!r}; a voice document holds the target VALUES. "
            "Resolve a style's role names when applying the style: "
            "an.audio.takes.style_voice_role(spec, role)"
        )
    if not isinstance(raw, Mapping):
        raise VoiceTakesError(f"{where} must be a mapping of metric -> [low, high]")
    try:
        validate_targets(raw)
    except ProsodyTargetError as exc:
        raise VoiceTakesError(f"{where}: {exc}") from exc
    return {k: [float(v) for v in raw[k]] for k in sorted(raw)}


def normalize_takes(raw: Any) -> dict[str, Any]:
    """The canonical ``takes`` declaration of a voice document (``{}`` for none).

    >>> normalize_takes(3)
    {'n': 3}
    >>> normalize_takes({"cues": {"deadpan": 4}})
    {'cues': {'deadpan': {'n': 4}}}
    """
    if raw is None:
        return {}
    out = _check_entry(raw, where=TAKES_KEY, allowed=_TAKES_FIELDS)
    cues = raw.get("cues") if isinstance(raw, Mapping) else None
    if cues is not None:
        if not isinstance(cues, Mapping):
            raise VoiceTakesError(f"{TAKES_KEY}.cues must map a direction cue to takes")
        out["cues"] = {
            str(cue): _check_entry(entry, where=f"{TAKES_KEY}.cues.{cue}", allowed=_CUE_FIELDS)
            for cue, entry in cues.items()
        }
    return out


def takes_spec(raw: Any, *, direction: Sequence[str] | None = None) -> TakesSpec | None:
    """The takes a line with ``direction`` gets from a voice's ``takes``, or ``None`` for one take.

    Raises :class:`VoiceTakesError` for a malformed declaration, and for more
    than one take with nothing to choose by.
    """
    decl = normalize_takes(raw)
    if not decl:
        return None
    entry = {k: v for k, v in decl.items() if k != "cues"}
    for cue in direction or ():
        if cue in decl.get("cues", {}):
            entry.update(decl["cues"][cue])
            break
    n = entry.get("n", 1)
    if n <= 1:
        return None
    scorer = entry.get("scorer", DEFAULT_SCORER)
    if scorer == DEFAULT_SCORER and not entry.get("targets"):
        raise VoiceTakesError(
            f"takes: n={n} with the {DEFAULT_SCORER} scorer needs `targets` "
            "([low, high] per metric) to choose by"
        )
    return TakesSpec(
        n=n,
        scorer=scorer,
        targets=entry.get("targets", {}),
        reference_hz=entry.get("reference_hz"),
    )


def voice_takes(
    mall: Mapping | None,
    voice_id: str,
    *,
    direction: Sequence[str] | None = None,
    tts_name: str | None = None,
) -> TakesSpec | None:
    """The takes ``mall["voices"][voice_id]`` declares for a line with ``direction``.

    ``None`` (one take) for a voice not in the store, one declaring nothing, and
    one written for another provider than ``tts_name`` — a preview under
    ``offline`` or ``mac_say`` never re-rolls (those providers repeat themselves).
    """
    from an.audio.voices import voice_applies, voice_document

    doc = voice_document(mall, voice_id)
    if not doc or not voice_applies(doc, tts_name):
        return None
    return takes_spec(doc.get(TAKES_KEY), direction=direction)


def takes_key_part(scorer: TakeScorer, n: int) -> dict[str, Any]:
    """What a line's audio key gains for best-of-``n`` takes chosen by ``scorer``."""
    return {
        "n": n,
        "scorer": scorer.name,
        "version": scorer.version,
        "config": dict(scorer.config),
    }


# -----------------------------------------------------------------------------
# Scoring and choosing
# -----------------------------------------------------------------------------


def decode_for_scoring(audio: bytes, *, sr: int = SCORING_SAMPLE_RATE):
    """``audio`` as mono float samples at ``sr`` Hz.

    ffmpeg when it is on PATH (how the targets were measured); without it a
    PCM WAV is read and linearly resampled, and anything else is refused.
    """
    import numpy as np

    if shutil.which("ffmpeg") is not None:
        from an.verify.prosody import decode_audio

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "take.bin"
            path.write_bytes(audio)
            return decode_audio(path, sr=sr)
    try:
        with wave.open(io.BytesIO(audio), "rb") as wf:
            width, channels, rate = wf.getsampwidth(), wf.getnchannels(), wf.getframerate()
            frames = wf.readframes(wf.getnframes())
    except wave.Error as exc:
        raise VoiceTakesError(
            "scoring a non-WAV take needs the ffmpeg binary on PATH "
            "(macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg`)"
        ) from exc
    if width != 2:
        raise VoiceTakesError(f"cannot score a {8 * width}-bit WAV without ffmpeg")
    x = np.frombuffer(frames, dtype="<i2").astype(np.float64) / 32768.0
    x = x.reshape(-1, channels).mean(axis=1)
    if rate != sr and x.size:
        t_out = np.arange(int(round(x.size * sr / rate))) / sr
        x = np.interp(t_out, np.arange(x.size) / rate, x)
    return x


class ProsodyTakeScorer:
    """Scores a take by how far its prosody sits from ``[low, high]`` targets.

    The score is :func:`an.verify.prosody.target_distance`: the summed distance
    outside the ranges, then the summed distance from their midpoints (the
    tie-break between takes all on target), in units of each range's width.
    """

    name: str = DEFAULT_SCORER

    def __init__(
        self,
        targets: Mapping[str, Sequence[float]],
        *,
        reference_hz: float | None = None,
        sr: int = SCORING_SAMPLE_RATE,
    ) -> None:
        from an.verify.prosody import ESTIMATOR_VERSION

        self.targets = _check_targets(targets, where="targets")
        self.reference_hz = reference_hz
        self.sr = sr
        self.version = f"{PROSODY_SCORER_VERSION}+estimator{ESTIMATOR_VERSION}"
        self.config: dict[str, Any] = {"targets": self.targets}
        if reference_hz is not None:
            self.config["reference_hz"] = float(reference_hz)

    def score(self, audio: bytes, text: str) -> TakeScore:
        from an.verify.prosody import measure_prosody, target_distance

        samples = decode_for_scoring(audio, sr=self.sr)
        stats = measure_prosody(samples, self.sr, text=text, reference_hz=self.reference_hz)
        outside, off_centre = target_distance(stats, self.targets)
        measured = {
            k: (None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 3))
            for k, v in ((name, getattr(stats, name)) for name in self.targets)
        }
        misses = [
            k for k, (lo, hi) in self.targets.items()
            if measured[k] is None or not lo <= measured[k] <= hi
        ]
        return TakeScore(
            value=(round(outside, 6), round(off_centre, 6)),
            detail={"measured": measured, "misses": misses},
        )


#: Scorer factories by name: ``TakesSpec -> TakeScorer``.
SCORERS: dict[str, Callable[[TakesSpec], TakeScorer]] = {
    DEFAULT_SCORER: lambda spec: ProsodyTakeScorer(spec.targets, reference_hz=spec.reference_hz),
}


def make_take_scorer(spec: TakesSpec) -> TakeScorer:
    """The scorer ``spec`` names, from :data:`SCORERS` (the pipeline's default ``take_scorer``)."""
    try:
        factory = SCORERS[spec.scorer]
    except KeyError:
        raise VoiceTakesError(
            f"unknown take scorer {spec.scorer!r}; known: {sorted(SCORERS)} "
            "(or pass take_scorer= to the audio pipeline)"
        ) from None
    return factory(spec)


def choose_take(scores: Sequence[TakeScore]) -> int:
    """The index of the best take: the lowest score, ties to the lower index."""
    if not scores:
        raise VoiceTakesError("no takes to choose from")
    return min(range(len(scores)), key=lambda i: (tuple(scores[i].value), i))


def audio_digest(audio: bytes) -> str:
    """The sha256 a takes record names a take's audio by."""
    return hashlib.sha256(audio).hexdigest()


# -----------------------------------------------------------------------------
# Applying a style
# -----------------------------------------------------------------------------


def style_voice_role(spec: Mapping[str, Any], role: str) -> dict[str, Any]:
    """The partial voice document a style casts ``role`` as, with target NAMES resolved.

    A style spec (the ``an-style`` skill's ``styles/<name>.yaml``) declares
    ``live.voice.roles.<role>`` and may name a delivery's targets by its key in
    ``prosody_targets`` (``takes: {n: 3, targets: narrator}``). This returns a
    copy whose ``takes`` (and each cue's) hold the target VALUES, ready to merge
    beside a ``voice_id``: ``{**style_voice_role(spec, "narrator"), "voice_id": ...}``.

    >>> spec = {"live": {"voice": {"roles": {"narrator": {"model_id": "eleven_v3",
    ...     "takes": {"n": 2, "targets": "narrator", "cues": {"deadpan": {"targets": "punchline"}}}}}}},
    ...     "prosody_targets": {"narrator": {"f0_sd_st": [3.9, 5.2]}, "punchline": {"f0_sd_st": [2.2, 3.4]}}}
    >>> role = style_voice_role(spec, "narrator")
    >>> role["takes"]["targets"], role["takes"]["cues"]["deadpan"]["targets"]
    ({'f0_sd_st': [3.9, 5.2]}, {'f0_sd_st': [2.2, 3.4]})
    """
    roles = ((spec.get("live") or {}).get("voice") or {}).get("roles") or {}
    if role not in roles:
        raise VoiceTakesError(f"the style casts no voice role {role!r}; roles: {sorted(roles)}")
    named = spec.get("prosody_targets") or {}

    def resolve(entry: Any) -> Any:
        if not isinstance(entry, Mapping):
            return entry
        out = dict(entry)
        targets = out.get("targets")
        if isinstance(targets, str):
            if targets not in named:
                raise VoiceTakesError(
                    f"role {role!r} names targets {targets!r}, which the style's "
                    f"prosody_targets do not have; have {sorted(named)}"
                )
            out["targets"] = dict(named[targets])
        if isinstance(out.get("cues"), Mapping):
            out["cues"] = {cue: resolve(e) for cue, e in out["cues"].items()}
        return out

    doc = dict(roles[role])
    if TAKES_KEY in doc:
        doc[TAKES_KEY] = resolve(doc[TAKES_KEY])
        normalize_takes(doc[TAKES_KEY])  # refuse a bad role at apply time, not at render
    return doc
