"""Voice loudness: one integrated loudness for every voice of a film (an#315).

TTS providers deliver voices at very different levels — measured on a four-voice
ElevenLabs episode: -16.4, -35.5, -28.4 and -23.4 LUFS, a 19 dB spread that left
one character barely audible. ``meta.voice_loudness`` (:class:`~an.ir.schema.VoiceLoudness`)
asks for one level for all of them:

- each voice's integrated loudness (EBU R128 / ITU-R BS.1770, measured by
  ffmpeg's ``ebur128`` over ALL of that voice's lines in the film, back to
  back: a 0.6 s line has a single 400 ms gating block, and a voice's own
  dynamics between lines — a whisper, a shout — are kept);
- ONE gain per voice, ``target - measured`` plus the voice document's
  ``loudness_offset_db``, rounded to :data:`GAIN_STEP_DB`, then a lookahead
  peak limiter at ``peak_db`` (:func:`limit_peaks`: a sample never passes the
  ceiling, and the gain eases into and out of a peak rather than clipping);
- the result is DERIVED audio, content-keyed in the ``audio`` store by
  (the line's audio, the gain, the ceiling, :data:`LEVEL_VERSION`) — never a
  re-synthesis, never billed — and the line is stamped with it, so the
  per-shot mux, the film mix and every cache key follow it. The gain changes
  no timing: lip-sync, word timings and durations are the source line's.

A voice whose lines are silence (the offline provider) is left as it is. A
voice whose lines are all short is measured looped (:data:`MIN_MEASURE_S`).
The gain is capped at :data:`MAX_GAIN_DB`, and a voice that ends more than
:data:`MISS_WARNING_DB` from its target (capped, or held down by its peaks) is
warned about. ``peak_db`` is a SAMPLE-peak ceiling: an AAC encode can still
overshoot it between samples by a fraction of a dB, so keep a margin.

The gain and the source are stamped on each line (``Dialogue.leveled``): a
render whose voice is unchanged reuses them without decoding or measuring
anything, and a re-measure that moves the gain by less than a step keeps the
previous gain (hysteresis), so one new line rarely re-renders a voice's other
shots.
Without a target, :func:`loudness_report` measures the voices and
:func:`voice_loudness_spread` says when they differ by more than
:data:`SPREAD_WARNING_DB` — the render warns, naming each voice's level.

The measuring and the limiter are the fleet's shared loudness component,
:mod:`mixing.loudness` (an#563; ``mixing`` is a core dependency since an#611):
:func:`mixing.loudness.level_group` measures a voice's lines back to back (looped
to :data:`MIN_MEASURE_S`, channels kept when they agree) and caps the gain, with
ffmpeg's ``ebur128`` injected as its meter (:data:`METER`) so ``an`` takes no
scipy; :func:`mixing.loudness.limit_peaks` is the limiter, moved there unchanged
(so :data:`LEVEL_VERSION` did not move, and a test pins the leveled bytes).
What stays here is ``an``'s own: the voices, the offsets, the hysteresis, the
makeup pass and the content keys. A ``mixing`` too old to have
``mixing.loudness`` raises :class:`VoiceLoudnessError` telling the user to
upgrade it (:func:`an.audio.shared_mixing.mixing_module`, an#621).
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import wave
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from an.audio.shared_mixing import mixing_module

#: Bumped whenever a leveled line's bytes would change for the same inputs
#: (the limiter, its window, the encoding); part of every leveled line's key.
#: A test pins the leveled output to it.
LEVEL_VERSION: int = 1
#: A voice's gain is rounded to this, so a new line that moves its voice's
#: loudness by less than half of it re-renders nothing else (half a dB is
#: below what a listener hears between two lines; the measurement itself is
#: to 0.1 LU).
GAIN_STEP_DB: float = 0.5
#: Below this a voice is silence (BS.1770's absolute gate): never leveled.
SILENCE_LUFS: float = -70.0
#: Voices further apart than this, with no target set, are warned about.
SPREAD_WARNING_DB: float = 6.0
#: The limiter's lookahead and release, seconds: the gain eases into a peak
#: and back out over this much on each side, so nothing below ~20 Hz is
#: modulated within a cycle (a 5 ms release distorted anything under 100 Hz,
#: an#315 review).
LIMITER_WINDOW_S: float = 0.05
#: The largest gain leveling gives a voice; beyond it the voice is mostly
#: noise (room tone measured at -62 LUFS asked for +46 dB). Capped, and warned.
MAX_GAIN_DB: float = 24.0
#: ``loudness_offset_db`` bounds on a voice document.
OFFSET_LIMITS_DB: tuple[float, float] = (-12.0, 12.0)
#: A voice shorter than this is measured looped to this length: EBU R128 gates
#: in 400 ms blocks, and a voice of only short lines would read as silence.
MIN_MEASURE_S: float = 1.0
#: A leveled voice that ends further than this from its target (the limiter
#: held its peaks, or the gain was capped) is warned about.
MISS_WARNING_DB: float = 1.0
#: The loudness meter injected into :mod:`mixing.loudness` (one of its
#: ``METERS``): ffmpeg's ``ebur128``, so ``an`` needs no scipy for its numpy meter.
METER: str = "ffmpeg_ebur128"
#: What installs the shared loudness component.
#: 16-bit full scale.
_INT16_FULL_SCALE: float = 32768.0


class VoiceLoudnessError(RuntimeError):
    """The voices cannot be measured or leveled (no ffmpeg, an unreadable line)."""


class VoiceLoudnessWarning(UserWarning):
    """The film's voices differ in loudness by more than :data:`SPREAD_WARNING_DB`."""


# -----------------------------------------------------------------------------
# PCM in and out
# -----------------------------------------------------------------------------


@dataclass
class _Pcm:
    samples: Any  # float64, shape (n, channels), full scale 1.0
    rate: int


def _require_ffmpeg(doing: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise VoiceLoudnessError(
            f"{doing} needs the ffmpeg binary on PATH (macOS: `brew install ffmpeg`; "
            "Debian/Ubuntu: `apt install ffmpeg`)"
        )


def _component() -> Any:
    """:mod:`mixing.loudness`, or :class:`VoiceLoudnessError` when the installed
    ``mixing`` predates it."""
    return mixing_module(
        "loudness", needed_for="leveling voices", error=VoiceLoudnessError
    )


def _decode(audio: bytes) -> _Pcm:
    """A line's audio as float samples: a 16-bit PCM WAV directly, anything
    else (an MP3 from ElevenLabs) decoded by ffmpeg first."""
    import numpy as np

    from an.audio.effects import EFFECT_SAMPLE_RATE, _ffmpeg_wav, _pcm16_wav

    if not _pcm16_wav(audio):
        _require_ffmpeg("measuring a voice's loudness")
        audio = _ffmpeg_wav(audio, f"aresample={EFFECT_SAMPLE_RATE}", {})
    with wave.open(io.BytesIO(audio), "rb") as w:
        channels, rate = w.getnchannels(), w.getframerate()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").reshape(-1, channels)
    return _Pcm(samples.astype(np.float64) / _INT16_FULL_SCALE, rate)


def _encode(pcm: _Pcm) -> bytes:
    import numpy as np

    ints = np.clip(np.rint(pcm.samples * _INT16_FULL_SCALE), -32768, 32767).astype(
        "<i2"
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(ints.shape[1])
        w.setsampwidth(2)
        w.setframerate(pcm.rate)
        w.writeframes(ints.tobytes())
    return buf.getvalue()


def _at_one_rate(pcms: list[_Pcm]) -> tuple[list[Any], int]:
    """``(segments, rate)``: the lines at the first line's rate (a voice's lines
    share a provider, so a rate; another is resampled), each keeping its
    channels — :func:`mixing.loudness.level_group` joins them back to back,
    keeping channels when they all agree (EBU R128 weights channels) and
    looping a short voice to :data:`MIN_MEASURE_S`."""
    import numpy as np

    if not pcms:
        return [], 48000
    rate = pcms[0].rate
    segments = []
    for p in pcms:
        x = p.samples
        if p.rate != rate and len(x):
            positions = np.arange(0, len(x), p.rate / rate)
            x = np.stack(
                [
                    np.interp(positions, np.arange(len(x)), x[:, c])
                    for c in range(x.shape[1])
                ],
                axis=1,
            )
        segments.append(x)
    return segments, rate


def _meter(data: Any, fs: int) -> float:
    """The meter :func:`mixing.loudness.level_group` is given: this module's
    :func:`integrated_loudness` (looked up at call time, so it can be counted)."""
    return integrated_loudness(_Pcm(data, fs))


def _level_group(pcms: list[_Pcm], *, target_lufs: float, max_gain_db: float):
    """:func:`mixing.loudness.level_group` over a voice's decoded lines:
    ``(gain_db, measured_lufs)``, measured by :data:`METER`."""
    segments, rate = _at_one_rate(pcms)
    return _component().level_group(
        segments,
        rate,
        target_lufs=target_lufs,
        meter=_meter,
        max_gain_db=max_gain_db,
        min_measure_s=MIN_MEASURE_S,
    )


def group_loudness(pcms: list[_Pcm]) -> float:
    """The integrated loudness of a voice's lines, measured back to back."""
    return _level_group(pcms, target_lufs=0.0, max_gain_db=float("inf"))[1]


# -----------------------------------------------------------------------------
# Measuring
# -----------------------------------------------------------------------------


def integrated_loudness(pcm: _Pcm) -> float:
    """EBU R128 integrated loudness (LUFS) of ``pcm``, by :data:`METER` through
    :func:`mixing.loudness.integrated_lufs` (``-inf`` for silence)."""
    component = _component()
    try:
        return component.integrated_lufs(pcm.samples, pcm.rate, meter=METER)
    except RuntimeError as e:  # no ffmpeg, or ffmpeg failed
        raise VoiceLoudnessError(
            f"measuring a voice's loudness: {e} (macOS: `brew install ffmpeg`; "
            "Debian/Ubuntu: `apt install ffmpeg`)"
        ) from e


# -----------------------------------------------------------------------------
# Leveling
# -----------------------------------------------------------------------------


def limit_peaks(samples: Any, *, ceiling: float, window: int = 1) -> Any:
    """``samples`` with no sample above ``ceiling`` (absolute, full scale 1.0):
    :func:`mixing.loudness.limit_peaks` (sample peak), the lookahead limiter
    that moved there unchanged from here (an#563)."""
    return _component().limit_peaks(samples, ceiling=ceiling, window=window)


def leveled_audio(audio: bytes, *, gain_db: float, peak_db: float) -> bytes:
    """``audio`` at ``gain_db``, its peaks held at ``peak_db`` dBFS, as a 16-bit
    PCM WAV of exactly the length of the decoded source (an MP3 source is
    stored decoded, as the mux would decode it)."""
    pcm = _decode(audio)
    ceiling = 10.0 ** (peak_db / 20.0) - 0.5 / _INT16_FULL_SCALE  # held after rounding
    samples = pcm.samples * (10.0 ** (gain_db / 20.0))
    samples = limit_peaks(
        samples, ceiling=ceiling, window=max(1, round(LIMITER_WINDOW_S * pcm.rate))
    )
    return _encode(_Pcm(samples, pcm.rate))


def leveled_key(source: bytes, *, gain_db: float, peak_db: float) -> str:
    """The content key of a leveled line: the sha256 of its source audio's
    BYTES (not the request that made them: a take re-synthesised under the
    same request is other audio, an#315 review), the gain, the ceiling, the
    rate a non-WAV source is decoded at, and :data:`LEVEL_VERSION`.

    >>> leveled_key(b"a", gain_db=1.0, peak_db=-1.5) != leveled_key(b"a", gain_db=1.1, peak_db=-1.5)
    True
    """
    from an.audio.effects import EFFECT_SAMPLE_RATE

    payload = {
        "leveled": hashlib.sha256(source).hexdigest(),
        "decode_rate": EFFECT_SAMPLE_RATE,
        "gain_db": round(float(gain_db), 3),
        "peak_db": round(float(peak_db), 3),
        "version": LEVEL_VERSION,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass
class VoiceLevel:
    """One voice's measured loudness, and the gain leveling gives it."""

    voice: str
    lufs: float
    gain_db: float = 0.0
    lines: int = 0


def voiced_lines(scene: Any, mall: Mapping[str, Any]) -> dict[str, list[Any]]:
    """``{voice id: [line, ...]}`` for every line with audio in the store."""
    from an.audio.voices import line_voice_id

    store = mall.get("audio") if mall else None
    out: dict[str, list[Any]] = {}
    for shot in scene.timeline:
        for line in shot.dialogue:
            if line.audio_ref and store is not None and line.audio_ref in store:
                out.setdefault(line_voice_id(line, shot, mall), []).append(line)
    return out


def loudness_report(scene: Any, mall: Mapping[str, Any]) -> list[VoiceLevel]:
    """Every voice's integrated loudness over its lines, as heard now (a
    leveled line's leveled audio)."""
    store = mall["audio"]
    out = []
    for voice, lines in voiced_lines(scene, mall).items():
        pcms = [_decode(store[line.audio_ref]) for line in lines]
        out.append(VoiceLevel(voice, group_loudness(pcms), lines=len(lines)))
    return out


def voice_loudness_spread(levels: list[VoiceLevel]) -> str | None:
    """What to say when the audible voices differ by more than
    :data:`SPREAD_WARNING_DB`; ``None`` otherwise."""
    audible = [v for v in levels if v.lufs > SILENCE_LUFS]
    if len(audible) < 2:
        return None
    spread = max(v.lufs for v in audible) - min(v.lufs for v in audible)
    if spread <= SPREAD_WARNING_DB:
        return None
    each = ", ".join(
        f"{v.voice} {v.lufs:.1f}" for v in sorted(audible, key=lambda v: -v.lufs)
    )
    return (
        f"the voices differ by {spread:.1f} dB in loudness ({each} LUFS): the "
        "quietest is hard to hear next to the loudest. Level them with "
        "`voice_loudness: -16` in the scene's meta (one gain per voice; nothing "
        "is re-synthesised)"
    )


def _offset(mall: Mapping[str, Any], voice: str) -> float:
    from an.audio.voices import voice_document

    raw = voice_document(mall, voice).get("loudness_offset_db", 0.0)
    lo, hi = OFFSET_LIMITS_DB
    if (
        isinstance(raw, bool)
        or not isinstance(raw, (int, float))
        or not lo <= raw <= hi
    ):
        raise VoiceLoudnessError(
            f"voice {voice!r}: loudness_offset_db must be a number in [{lo:g}, {hi:g}] "
            f"dB, got {raw!r}"
        )
    return float(raw)


def _source(line: Any) -> str:
    """The synthesized audio a line was leveled from (its own when unleveled)."""
    return (line.leveled or {}).get("source") or line.audio_ref


def voiced_sources(scene: Any, mall: Mapping[str, Any]) -> dict[str, list[Any]]:
    """:func:`voiced_lines`, by each line's SOURCE audio (a leveled line's own)."""
    store = mall.get("audio") if mall else None
    from an.audio.voices import line_voice_id

    out: dict[str, list[Any]] = {}
    for shot in scene.timeline:
        for line in shot.dialogue:
            src = _source(line) if line.audio_ref else None
            if src and store is not None and src in store:
                out.setdefault(line_voice_id(line, shot, mall), []).append(line)
    return out


def level_voices(
    scene: Any, mall: Mapping[str, MutableMapping], spec: Any
) -> list[VoiceLevel]:
    """Level every voice of ``scene`` to ``spec`` (:class:`~an.ir.schema.VoiceLoudness`):
    each line is stamped with its leveled audio (made once per source bytes,
    gain and ceiling, in the ``audio`` store) and ``Dialogue.leveled``.
    Returns each voice's level; warns (:class:`VoiceLoudnessWarning`) about a
    voice it had to cap or could not bring within :data:`MISS_WARNING_DB`."""
    import warnings

    store = mall["audio"]
    levels = []
    for voice, lines in voiced_sources(scene, mall).items():
        target = spec.target_lufs + _offset(mall, voice)
        sources = [store[_source(line)] for line in lines]
        recorded = {(line.leveled or {}).get("gain_db") for line in lines}
        previous = recorded.pop() if len(recorded) == 1 else None
        if previous is not None and all(
            line.leveled is not None
            and line.audio_ref
            == leveled_key(src, gain_db=previous, peak_db=spec.peak_db)
            and line.audio_ref in store
            for line, src in zip(lines, sources)
        ):
            levels.append(VoiceLevel(voice, target - previous, previous, len(lines)))
            continue  # nothing changed since this voice was leveled: nothing to measure
        with warnings.catch_warnings(record=True) as capped:
            warnings.simplefilter("always")
            gain, lufs = _level_group(
                [_decode(src) for src in sources],
                target_lufs=target,
                max_gain_db=MAX_GAIN_DB,
            )
        level = VoiceLevel(voice, lufs, lines=len(lines))
        levels.append(level)
        for caught in capped:
            if (
                caught.category is UserWarning
            ):  # the component capped the gain: said per voice
                warnings.warn(
                    f"voice {voice!r}: {caught.message}",
                    VoiceLoudnessWarning,
                    stacklevel=3,
                )
            else:  # anything else is not ours to relabel: pass it on as it was
                warnings.warn_explicit(
                    caught.message, caught.category, caught.filename, caught.lineno
                )
        if not lufs > SILENCE_LUFS:
            for line in lines:
                line.audio_ref, line.leveled = _source(line), None
            continue  # silence (the offline provider): nothing to level
        if previous is not None and abs(gain - previous) < GAIN_STEP_DB:
            gain = previous  # hysteresis: a move under a step re-levels nothing

        def apply(gain_db: float) -> float:
            """Level every line at ``gain_db``; the loudness the voice reaches."""
            level.gain_db = round(round(gain_db / GAIN_STEP_DB) * GAIN_STEP_DB, 3)
            made = []
            for line, src in zip(lines, sources):
                key = leveled_key(src, gain_db=level.gain_db, peak_db=spec.peak_db)
                if key not in store:
                    store[key] = leveled_audio(
                        src, gain_db=level.gain_db, peak_db=spec.peak_db
                    )
                made.append(store[key])
                line.leveled = {"source": _source(line), "gain_db": level.gain_db}
                line.audio_ref = key
            return group_loudness([_decode(m) for m in made])

        reached = apply(gain)
        short = target - reached
        if short >= GAIN_STEP_DB and level.gain_db < MAX_GAIN_DB:
            # The limiter held its peaks and took loudness with them: one
            # makeup pass, the shortfall added (the limiter takes some again).
            reached = apply(min(MAX_GAIN_DB, level.gain_db + short))
        if abs(reached - target) > MISS_WARNING_DB:
            warnings.warn(
                f"voice {voice!r} reaches {reached:.1f} LUFS, not its {target:g}: its "
                "peaks were held at the ceiling (or its gain capped); lower "
                "`target_lufs` or raise `peak_db`",
                VoiceLoudnessWarning,
                stacklevel=3,
            )
    return levels
