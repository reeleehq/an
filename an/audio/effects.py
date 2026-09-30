"""Voice effects: a deterministic transform applied to a synthesized line (an#163).

A voice document in the ``voices`` store may declare ``effects``. The one effect
that exists is ``pitch_semitones`` — South Park raises its voices to sound like
fourth graders, and a raised voice is a property of the *character*, not of the
TTS provider, so it lives beside the voice the line already resolves through
rather than in the IR.

>>> normalize_effects({"pitch_semitones": 4})
{'pitch_semitones': 4.0}
>>> normalize_effects({"pitch_semitones": 0}) == normalize_effects(None) == {}
True
>>> round(_pitch_filter(12), 3)
0.5
>>> normalize_effects({"reverb": 1})
Traceback (most recent call last):
    ...
an.audio.effects.VoiceEffectError: unknown voice effect(s) ['reverb']; known: ['pitch_semitones']

Design, in the order the pipeline uses it:

- **The transform runs after synthesis and before alignment.** Lip-sync reads the
  audio the viewer hears. The chain keeps the duration (see below), so word
  timings computed on raw and on shifted audio agree to a frame, but the shifted
  bytes are what is aligned regardless.
- **The cache keys on the effect.** ``effects_key`` is empty for no effect, and
  ``an.audio.pipeline`` adds it to the audio key only when it is non-empty, so a
  project that declares none keeps every key it ever had.
- **Stock ffmpeg only.** The chain is ``aresample → asetrate → aresample →
  atempo``: the sample rate is relabelled by the pitch ratio (pitch and speed both
  move) and ``atempo`` removes the speed change. ``rubberband`` is a better
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
#: The sample rate the chain runs at (and the shifted WAV is written at).
EFFECT_SAMPLE_RATE = 44100
KNOWN_EFFECTS = ("pitch_semitones",)


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


def filter_chain(effects: Mapping[str, float]) -> str:
    """The ffmpeg ``-af`` chain for normalised ``effects`` (``""`` for none)."""
    semitones = effects.get("pitch_semitones")
    if not semitones:
        return ""
    ratio = 2.0 ** (semitones / 12.0)
    rate = EFFECT_SAMPLE_RATE
    return (
        f"aresample={rate},asetrate={rate * ratio:.6f},"
        f"aresample={rate},atempo={1.0 / ratio:.9f}"
    )


def apply_voice_effects(audio: bytes, effects: Mapping[str, float]) -> bytes:
    """``audio`` (any container ffmpeg sniffs) with ``effects`` applied, as WAV bytes.

    Returns the input unchanged for no effects. Raises ``VoiceEffectError`` when
    ffmpeg is missing or fails — never returns unshifted audio for a voice that
    asked for a shift.
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
