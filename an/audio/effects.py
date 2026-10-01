"""Voice effects: a deterministic transform applied to a synthesized line (an#163).

A voice document in the ``voices`` store may declare ``effects``. Two exist:

- ``pitch_semitones`` (an#163) — South Park raises its voices to sound like
  fourth graders; duration-preserving.
- ``tempo`` (an#265) — a pitch-preserving speed ratio (``1.1`` is 10% faster).
  ``eleven_v3`` ignores ``voice_settings.speed`` and no audio tag moves its rate,
  so a narrator that must run at 5.8 syllables/s, or an expressive voice that
  must be slowed to a serene pace, is re-timed here. Unlike the pitch effect it
  CHANGES the line's duration.

A raised voice or a fast narrator is a property of the *character*, not of the
TTS provider, so it lives beside the voice the line already resolves through
rather than in the IR.

>>> normalize_effects({"pitch_semitones": 4})
{'pitch_semitones': 4.0}
>>> normalize_effects({"pitch_semitones": 0}) == normalize_effects({"tempo": 1}) == normalize_effects(None) == {}
True
>>> normalize_effects({"tempo": 1.1, "pitch_semitones": -2})
{'pitch_semitones': -2.0, 'tempo': 1.1}
>>> round(_pitch_filter(12), 3)
0.5
>>> filter_chain({"tempo": 1.25})
'aresample=44100,atempo=1.250000000'
>>> normalize_effects({"reverb": 1})
Traceback (most recent call last):
    ...
an.audio.effects.VoiceEffectError: unknown voice effect(s) ['reverb']; known: ['pitch_semitones', 'tempo']

Design, in the order the pipeline uses it:

- **The transform runs after synthesis and before alignment.** Lip-sync reads the
  audio the viewer hears. The pitch chain keeps the duration, so word timings
  computed on raw and on shifted audio agree to a frame; a ``tempo`` does not,
  which is why the shifted bytes are what is aligned, the line's ``duration`` is
  read from them, and the viseme key derives from the effect-keyed audio key —
  visemes, word timings and captions all follow the audio the viewer hears.
- **The cache keys on the effect.** ``effects_key`` is empty for no effect, and
  ``an.audio.pipeline`` adds it to the audio key only when it is non-empty, so a
  project that declares none keeps every key it ever had.
- **Stock ffmpeg only.** The chain is ``aresample → asetrate → aresample →
  atempo``: the sample rate is relabelled by the pitch ratio (pitch and speed both
  move) and ``atempo`` removes the speed change; a ``tempo`` multiplies into that
  same ``atempo`` factor (``aresample → atempo`` alone when there is no pitch).
  A factor outside ``atempo``'s clean ``[0.5, 2]`` is split into stages, each
  inside it; the pitch-only chain is one stage, character for character what it
  was before ``tempo`` existed. ``rubberband`` is a better
  shifter but is a build option, and its output would differ between machines —
  which a content-hash cache cannot tolerate. The output is bit-exact WAV (no
  encoder tag, no metadata), so two runs produce identical bytes.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

#: Effects a voice document may declare, with the range each accepts.
PITCH_SEMITONES_LIMIT = 12.0  # atempo's stock range is [0.5, 2]: one octave each way
#: ``tempo`` bounds: half to double speed. Outside it speech stops being speech.
TEMPO_LIMITS: tuple[float, float] = (0.5, 2.0)
#: One ``atempo`` stage's clean range; a factor beyond it is chained in stages.
ATEMPO_STAGE_LIMITS: tuple[float, float] = (0.5, 2.0)
#: The sample rate the chain runs at (and the shifted WAV is written at).
EFFECT_SAMPLE_RATE = 44100
KNOWN_EFFECTS = ("pitch_semitones", "tempo")


class VoiceEffectError(ValueError):
    """A voice declares an effect that is unknown, malformed or out of range."""


def normalize_effects(raw: Mapping[str, Any] | None) -> dict[str, float]:
    """The canonical effects dict for a voice's ``effects`` value.

    Omit-when-unset: ``None``, ``{}`` and a zero-valued effect all normalise to
    ``{}``, which the pipeline treats as "no effect" (and keys nothing on).
    Unknown keys raise — an effect that silently does nothing is worse than none.
    """
    if not raw:
        return {}
    if not isinstance(raw, Mapping):
        raise VoiceEffectError(
            f"voice `effects` must be a mapping, got {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - set(KNOWN_EFFECTS))
    if unknown:
        raise VoiceEffectError(
            f"unknown voice effect(s) {unknown}; known: {list(KNOWN_EFFECTS)}"
        )
    out: dict[str, float] = {}
    semitones = raw.get("pitch_semitones")
    if semitones is not None:
        if isinstance(semitones, bool) or not isinstance(semitones, (int, float)):
            raise VoiceEffectError(
                f"pitch_semitones must be a number, got {semitones!r}"
            )
        if abs(semitones) > PITCH_SEMITONES_LIMIT:
            raise VoiceEffectError(
                f"pitch_semitones {semitones} is outside ±{PITCH_SEMITONES_LIMIT:g} "
                "(one octave: the tempo filter's stock range)"
            )
        if semitones != 0:
            out["pitch_semitones"] = float(semitones)
    tempo = raw.get("tempo")
    if tempo is not None:
        if isinstance(tempo, bool) or not isinstance(tempo, (int, float)):
            raise VoiceEffectError(f"tempo must be a number, got {tempo!r}")
        lo, hi = TEMPO_LIMITS
        if not lo <= tempo <= hi:
            raise VoiceEffectError(
                f"tempo {tempo} is outside [{lo:g}, {hi:g}] (a speed ratio: "
                "1.1 is 10% faster, 0.8 is 20% slower)"
            )
        if tempo != 1:
            out["tempo"] = float(tempo)
    return out


def voice_effects(mall: Mapping | None, voice_id: str) -> dict[str, float]:
    """The normalised effects declared by ``mall["voices"][voice_id]``, or ``{}``.

    A voice that is not in the store (the offline default, a raw provider voice
    id) has no effects; so does a store that does not exist.
    """
    voices = mall.get("voices") if mall is not None else None
    if voices is None or voice_id not in voices:
        return {}
    doc = voices[voice_id]
    return normalize_effects(doc.get("effects") if isinstance(doc, Mapping) else None)


def _pitch_filter(semitones: float) -> float:
    """The ``atempo`` factor that cancels the speed change of a pitch shift."""
    return 1.0 / (2.0 ** (semitones / 12.0))


def atempo_stages(
    factor: float, *, limits: tuple[float, float] = ATEMPO_STAGE_LIMITS
) -> list[float]:
    """``factor`` as a product of ``atempo`` stages, each inside ``limits``.

    One stage when ``factor`` already fits (the pitch-only chain, always).

    >>> atempo_stages(1.5)
    [1.5]
    >>> atempo_stages(3.0)
    [2.0, 1.5]
    >>> atempo_stages(0.3)
    [0.5, 0.6]
    """
    lo, hi = limits
    stages: list[float] = []
    while factor > hi:
        stages.append(hi)
        factor /= hi
    while factor < lo:
        stages.append(lo)
        factor /= lo
    return [*stages, factor]


def filter_chain(effects: Mapping[str, float]) -> str:
    """The ffmpeg ``-af`` chain for normalised ``effects`` (``""`` for none)."""
    semitones = effects.get("pitch_semitones") or 0.0
    tempo = effects.get("tempo") or 1.0
    if not semitones and tempo == 1.0:
        return ""
    rate = EFFECT_SAMPLE_RATE
    if semitones:
        ratio = 2.0 ** (semitones / 12.0)
        head = f"aresample={rate},asetrate={rate * ratio:.6f},aresample={rate}"
        factor = tempo / ratio
    else:
        head, factor = f"aresample={rate}", tempo
    return ",".join([head, *(f"atempo={f:.9f}" for f in atempo_stages(factor))])


def apply_voice_effects(audio: bytes, effects: Mapping[str, float]) -> bytes:
    """``audio`` (any container ffmpeg sniffs) with ``effects`` applied, as WAV bytes.

    Returns the input unchanged for no effects. Raises ``VoiceEffectError`` when
    ffmpeg is missing or fails — never returns unprocessed audio for a voice that
    asked for an effect.
    """
    chain = filter_chain(effects)
    if not chain:
        return audio
    if shutil.which("ffmpeg") is None:
        raise VoiceEffectError(
            "this voice declares `effects`, which need the ffmpeg binary on PATH "
            "(macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg`)"
        )
    # Output goes to a real file, not a pipe: ffmpeg cannot seek a pipe to patch
    # the WAV header's sizes, and a header that says "0xFFFFFFFF bytes" makes
    # every downstream duration read wrong.
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "shifted.wav"
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                "pipe:0",
                "-af",
                chain,
                "-map_metadata",
                "-1",
                "-fflags",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                "-c:a",
                "pcm_s16le",
                str(out_path),
            ],
            input=audio,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not out_path.exists():
            raise VoiceEffectError(
                f"ffmpeg failed applying {dict(effects)}: "
                f"{proc.stderr.decode(errors='replace').strip()}"
            )
        return out_path.read_bytes()
