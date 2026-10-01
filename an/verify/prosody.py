"""Prosody measurement: how a recorded voice delivers its words, as numbers a target can check.

"Read it like a deadpan narrator" is only checkable if the delivery is a set of
numbers. This module measures one spoken clip — a synthesized dialogue line, a
narration take, a reference recording studied privately — and compares the
measurement to ``[low, high]`` targets, the way :mod:`an.verify.style` does for
a render's cadence. It knows nothing about characters, faces or genres: any
narrated video (cut-out, data-viz, math-viz) has a voice to measure.

What is measured (:data:`METRICS` is the vocabulary a target may use):

- **Rate.** ``articulation_rate_sps`` — syllables per second of *speaking* time
  (pauses excluded), and ``speech_rate_sps`` — syllables per second of the whole
  clip from first to last sound. Syllables come from the ``text`` when given
  (:func:`count_syllables`, an English vowel-group estimate); without a text both
  rates are ``nan``.
- **Pauses.** A pause is a run of non-speech frames of at least
  ``min_pause_s`` between two stretches of speech (the clip's own leading and
  trailing silence never count). ``pause_share`` is pause time over the clip's
  span; ``pauses_per_min``, ``pause_median_s`` and ``pause_p90_s`` describe the
  pauses themselves. A frame is speech when its level is within
  ``speech_floor_db`` of the clip's 95th-percentile level.
- **Pitch.** A YIN fundamental-frequency track (de Cheveigné & Kawahara 2002)
  on speech frames. Movement is reported in **semitones about the clip's own
  median**, so a target transfers between a low and a high voice:
  ``f0_sd_st`` (spread), ``f0_range_st`` (5th to 95th percentile), and
  ``final_drop_st`` — per phrase (speech between pauses of at least
  ``phrase_pause_s``), the median pitch of the phrase's last quarter minus the
  phrase's median, then the median over phrases: negative is a falling ending
  (a flat, final statement), positive a rising one (a question, a setup that
  is not finished). ``f0_median_hz`` is reported for reference, and
  ``register_st`` — the clip's median pitch in semitones above (or below) a
  ``reference_hz`` the caller passes, typically the same voice's neutral
  median — measures a register jump (a character voice, an outburst); it is
  ``nan`` without a reference.
- **Loudness.** ``loudness_range_db``: the 90th minus the 10th percentile of
  the speech frames' level.
- **Emphasis.** ``emphasis_per_s``: syllable-rate peaks of the level envelope
  that stand out — at least ``emphasis_db`` above the clip's median speech level
  or ``emphasis_st`` above its median pitch — per second of speaking time.

**Lines, not performances.** Targets measured per sentence (a range of
per-sentence values) are compared with the median over a set of lines, each
measured alone (:func:`measure_lines`, the CLI's default for several files):
joining lines first spreads the pitch statistics by the register changes
between them.

These are estimators, crude on purpose: numpy only, no model, deterministic.
A target measured with them is only comparable to a clip measured with them,
so change an estimator only together with re-measuring the targets that use it.

The core is a pure function over samples, testable without ffmpeg:

>>> import numpy as np
>>> sr = 16000
>>> t = np.arange(int(0.5 * sr)) / sr
>>> tone = 0.3 * np.sin(2 * np.pi * 150 * t)
>>> clip = np.concatenate([tone, np.zeros(int(0.4 * sr)), tone])
>>> m = measure_prosody(clip, sr, text="one two")
>>> round(m.f0_median_hz), m.pauses, round(m.pause_median_s, 2)
(150, 1, 0.4)
>>> m.syllables, round(m.articulation_rate_sps, 1)
(2, 2.0)

A target is a ``[low, high]`` range; a miss is a warning, and a target nothing
measures is refused:

>>> check_prosody(m, {"pauses_per_min": [0, 200]})
[]
>>> check_prosody(m, {"pauses_per_min": [0, 10]})[0].ir_path
'<prosody>/pauses_per_min'
>>> check_prosody(m, {"swagger": [0, 1]})
Traceback (most recent call last):
...
an.verify.prosody.ProsodyTargetError: unknown prosody target 'swagger'; measurable targets are [...]
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from an.verify._base import Finding, VerificationReport

__all__ = [
    "METRICS",
    "ProsodyStats",
    "ProsodyTargetError",
    "ProsodyDecodeError",
    "measure_prosody",
    "measure_prosody_file",
    "measure_lines",
    "median_stats",
    "pitch_track",
    "count_syllables",
    "join_speech",
    "decode_audio",
    "check_prosody",
    "target_distance",
    "validate_targets",
    "ESTIMATOR_VERSION",
    "prosody_lint",
]

#: Raised whenever an estimator or one of its defaults below changes what a clip
#: measures. Anything that persists a choice made from these numbers (the best
#: take of a line, :mod:`an.audio.takes`) keys on it, so a changed estimator
#: re-chooses instead of trusting numbers it would no longer produce.
ESTIMATOR_VERSION: str = "1"

# --- defaults (every estimator knob; a target measured with them assumes them)
DFLT_SR: int = 16000
DFLT_HOP_S: float = 0.01
DFLT_WINDOW_S: float = 0.025  # YIN integration window and the level frame
DFLT_FMIN_HZ: float = 60.0
DFLT_FMAX_HZ: float = 500.0
DFLT_YIN_THRESHOLD: float = 0.1
DFLT_VOICING_THRESHOLD: float = (
    0.35  # a frame whose best period dips no lower is unvoiced
)
DFLT_SPEECH_FLOOR_DB: float = 30.0
DFLT_MIN_PAUSE_S: float = 0.12
DFLT_PHRASE_PAUSE_S: float = 0.25
DFLT_EMPHASIS_DB: float = 6.0
DFLT_EMPHASIS_ST: float = 3.0
DFLT_PEAK_GAP_S: float = 0.12  # at most ~8 syllable peaks per second
DFLT_FINAL_SHARE: float = 0.25  # the "last quarter" of a phrase
_MIN_VOICED_PER_PHRASE: int = 8  # frames; fewer and a phrase has no contour
_SMOOTH_FRAMES: int = 5  # median filter on the pitch track (isolated-jump guard)
_OCTAVE_WINDOW_FRAMES: int = (
    50  # the local pitch an octave error is folded toward (±0.5 s)
)
_OCTAVE_FOLD_ST: float = (
    7.0  # further than this from the local pitch: try an octave fold
)
_EPS: float = 1e-10

#: The measurable targets, and what each one is.
METRICS: dict[str, str] = {
    "articulation_rate_sps": "syllables per second of speaking time (needs the text)",
    "speech_rate_sps": "syllables per second of the clip's span (needs the text)",
    "pause_share": "share of the span that is pauses",
    "pauses_per_min": "pauses per minute of span",
    "pause_median_s": "median pause length",
    "pause_p90_s": "90th-percentile pause length",
    "f0_median_hz": "median pitch (voice-specific; for reference)",
    "f0_sd_st": "pitch spread, semitones about the median",
    "f0_range_st": "pitch range, 5th to 95th percentile, semitones",
    "final_drop_st": "median phrase ending relative to its phrase, semitones (negative falls)",
    "loudness_range_db": "speech level, 90th minus 10th percentile, dB",
    "emphasis_per_s": "stand-out level peaks per second of speaking time",
    "voiced_share": "share of speaking time with a pitch",
    "register_st": "median pitch relative to reference_hz, semitones (needs a reference)",
}

#: How to move each metric, when a delivery misses its target (rendering with
#: an expressive TTS voice; the words are the generic knobs, not one provider's).
_FIXES: dict[str, tuple[str, str]] = {
    "articulation_rate_sps": (
        "slow the voice (speed) or add commas",
        "raise the voice's speed or cut commas",
    ),
    "speech_rate_sps": (
        "add pauses (ellipses, line breaks, a `(pause)`)",
        "remove pauses or raise the speed",
    ),
    "pause_share": (
        "fewer ellipses and dashes",
        "more ellipses, dashes or split lines with a `(pause)`",
    ),
    "pauses_per_min": (
        "join sentences; fewer commas",
        "more commas, dashes, short sentences",
    ),
    "pause_median_s": (
        "shorter beats (comma rather than ellipsis)",
        "longer beats (ellipsis, a `(pause)` between lines)",
    ),
    "pause_p90_s": ("drop the longest beat", "one longer beat before the punchline"),
    "f0_median_hz": ("another voice", "another voice"),
    "f0_sd_st": (
        "a steadier voice setting or a flat tag ([deadpan])",
        "a looser voice setting or a lively tag ([excited])",
    ),
    "f0_range_st": (
        "a steadier voice setting or a flat tag ([deadpan])",
        "a looser voice setting, CAPS on a stressed word, an exclamation",
    ),
    "final_drop_st": (
        "end on a question or a trailing ellipsis",
        "end on a full stop; a [deadpan] or [matter-of-fact] tag",
    ),
    "loudness_range_db": (
        "a steadier voice setting",
        "a shouted word or a [whispers] aside",
    ),
    "emphasis_per_s": (
        "fewer CAPS and exclamations",
        "CAPS on the stressed word, exclamations",
    ),
    "voiced_share": ("less breath and whisper", "less whisper"),
    "register_st": (
        "a calmer tag, or none",
        "a louder or more excited tag ([excited], [shouting])",
    ),
}


class ProsodyTargetError(ValueError):
    """A prosody target names no metric, or is not a ``[low, high]`` range."""


class ProsodyDecodeError(RuntimeError):
    """An audio file could not be decoded (ffmpeg missing or failing)."""


@dataclass(frozen=True, slots=True)
class ProsodyStats:
    """One clip's delivery, in the units :data:`METRICS` describes.

    ``nan`` means "not measurable on this clip" (no text for a rate, no pause
    for a pause length, no voiced phrase for a contour)."""

    duration_s: float
    span_s: float
    speech_s: float
    syllables: int | None
    pauses: int
    articulation_rate_sps: float
    speech_rate_sps: float
    pause_share: float
    pauses_per_min: float
    pause_median_s: float
    pause_p90_s: float
    f0_median_hz: float
    f0_sd_st: float
    f0_range_st: float
    final_drop_st: float
    loudness_range_db: float
    emphasis_per_s: float
    voiced_share: float
    register_st: float = math.nan

    def as_dict(self, *, ndigits: int = 3) -> dict[str, Any]:
        """The stats as a plain dict, floats rounded (``nan`` becomes ``None``)."""
        return {
            k: (
                None
                if isinstance(v, float) and math.isnan(v)
                else round(v, ndigits)
                if isinstance(v, float)
                else v
            )
            for k, v in asdict(self).items()
        }


# -----------------------------------------------------------------------------
# Text
# -----------------------------------------------------------------------------

_WORD = re.compile(r"[a-zA-Z']+|\d+")
_VOWEL_GROUP = re.compile(r"[aeiouy]+")


def count_syllables(text: str) -> int:
    """An English syllable estimate: vowel groups per word, a silent final ``e``
    dropped, at least one per word; a number counts one per digit.

    Bracketed audio tags (``[sighs]``) are not words and are skipped.

    >>> count_syllables("He did not do the job.")
    6
    >>> count_syllables("[deadpan] Forty-seven criteria.")  # truly 8: an estimate
    7
    """
    text = re.sub(r"\[[^\]]*\]", " ", text)
    total = 0
    for word in _WORD.findall(text.lower()):
        if word.isdigit():
            total += len(word)
            continue
        word = word.replace("'", "")
        n = len(_VOWEL_GROUP.findall(word))
        if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and n > 1:
            n -= 1
        total += max(n, 1)
    return total


# -----------------------------------------------------------------------------
# Frames
# -----------------------------------------------------------------------------


def _frames(x: np.ndarray, length: int, hop: int) -> np.ndarray:
    """Overlapping frames of ``x`` (zero-padded at the end), one per row."""
    n = max(1, 1 + (len(x) - 1) // hop)
    padded = np.concatenate([x, np.zeros(length + hop, dtype=x.dtype)])
    idx = np.arange(length)[None, :] + hop * np.arange(n)[:, None]
    return padded[idx]


def _level_db(x: np.ndarray, sr: int, *, window_s: float, hop_s: float) -> np.ndarray:
    """Frame RMS level in dB (full scale), one value per hop."""
    win, hop = max(1, int(window_s * sr)), max(1, int(hop_s * sr))
    fr = _frames(x, win, hop)
    return 10 * np.log10(np.mean(fr * fr, axis=1) + _EPS)


def pitch_track(
    samples: np.ndarray,
    sr: int,
    *,
    fmin: float = DFLT_FMIN_HZ,
    fmax: float = DFLT_FMAX_HZ,
    hop_s: float = DFLT_HOP_S,
    window_s: float = DFLT_WINDOW_S,
    threshold: float = DFLT_YIN_THRESHOLD,
    voicing_threshold: float = DFLT_VOICING_THRESHOLD,
    chunk: int = 4096,
) -> np.ndarray:
    """A YIN pitch track: Hz per hop, ``nan`` where no period is found.

    >>> sr = 16000
    >>> t = np.arange(sr // 2) / sr
    >>> f0 = pitch_track(np.sin(2 * np.pi * 220 * t), sr)
    >>> round(float(np.nanmedian(f0)))
    220
    >>> bool(np.isnan(pitch_track(np.zeros(sr // 4), sr)).all())
    True
    """
    x = np.asarray(samples, dtype=np.float64)
    hop, w = max(1, int(hop_s * sr)), max(2, int(window_s * sr))
    tmin, tmax = max(2, int(sr / fmax)), int(math.ceil(sr / fmin))
    length = w + tmax + 1
    n_fft = 1 << int(math.ceil(math.log2(length + w)))
    all_frames = _frames(x, length, hop)
    out = np.full(len(all_frames), np.nan)
    taus = np.arange(tmax + 1)
    for start in range(0, len(all_frames), chunk):
        fr = all_frames[start : start + chunk]
        head = fr[:, :w]
        acf = np.fft.irfft(
            np.conj(np.fft.rfft(head, n_fft)) * np.fft.rfft(fr, n_fft), n_fft
        )[:, : tmax + 1]
        sq = np.concatenate(
            [np.zeros((len(fr), 1)), np.cumsum(fr * fr, axis=1)], axis=1
        )
        e_tau = sq[:, taus + w] - sq[:, taus]
        d = np.maximum(sq[:, w : w + 1] + e_tau - 2 * acf, 0.0)
        cum = np.cumsum(d[:, 1:], axis=1)
        cmnd = np.ones_like(d)
        cmnd[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(cum, _EPS)
        silent = sq[:, w] <= _EPS * w
        for i in np.flatnonzero(~silent):
            row = cmnd[i]
            below = np.flatnonzero(row[tmin:] < threshold)
            if below.size:
                tau = tmin + below[0]
            else:  # YIN step 4: the global minimum, if periodic enough to voice
                tau = tmin + int(np.argmin(row[tmin:]))
                if row[tau] >= voicing_threshold:
                    continue
            while tau + 1 <= tmax and row[tau + 1] < row[tau]:
                tau += 1
            if 0 < tau < tmax:  # parabolic refinement
                a, b, c = row[tau - 1], row[tau], row[tau + 1]
                denom = a - 2 * b + c
                shift = 0.5 * (a - c) / denom if abs(denom) > _EPS else 0.0
            else:
                shift = 0.0
            out[start + i] = sr / (tau + shift)
    return out


def _median_filter_nan(f0: np.ndarray, k: int) -> np.ndarray:
    """A running median over voiced frames only, which removes isolated octave jumps."""
    if k <= 1:
        return f0
    out = f0.copy()
    half = k // 2
    for i in np.flatnonzero(~np.isnan(f0)):
        win = f0[max(0, i - half) : i + half + 1]
        out[i] = np.nanmedian(win)
    return out


def _fold_octaves(
    f0: np.ndarray,
    *,
    window: int = _OCTAVE_WINDOW_FRAMES,
    limit_st: float = _OCTAVE_FOLD_ST,
) -> np.ndarray:
    """Fold octave errors (a frame tracked at double or half its pitch) toward
    the local median pitch, the error a period tracker makes on a voice with a
    strong second harmonic or a creak.

    >>> f = np.array([100.0] * 20 + [200.0] * 3 + [100.0] * 20)
    >>> float(np.nanmax(_fold_octaves(f, window=10)))
    100.0
    """
    out = f0.copy()
    idx = np.flatnonzero(~np.isnan(f0))
    if idx.size == 0:
        return out
    for i in idx:
        local = f0[max(0, i - window) : i + window + 1]
        ref = np.nanmedian(local)
        dev = 12 * np.log2(f0[i] / ref)
        if abs(dev) > limit_st:
            folded = f0[i] * (0.5 if dev > 0 else 2.0)
            if abs(12 * np.log2(folded / ref)) < abs(dev):
                out[i] = folded
    return out


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """``(start, stop)`` index pairs of the True runs of ``mask``."""
    if mask.size == 0:
        return []
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def _peaks(env: np.ndarray, *, min_gap: int) -> np.ndarray:
    """Local maxima of ``env``, at least ``min_gap`` frames apart (the larger wins)."""
    if env.size < 3:
        return np.array([], dtype=int)
    cand = np.flatnonzero((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:])) + 1
    kept: list[int] = []
    for i in cand[np.argsort(-env[cand])]:
        if all(abs(i - j) >= min_gap for j in kept):
            kept.append(int(i))
    return np.array(sorted(kept), dtype=int)


def _nan_stat(values: Sequence[float] | np.ndarray, fn) -> float:
    arr = np.asarray(values, dtype=float)
    return float(fn(arr)) if arr.size else math.nan


# -----------------------------------------------------------------------------
# Measurement
# -----------------------------------------------------------------------------


def measure_prosody(
    samples: np.ndarray,
    sr: int,
    *,
    text: str | None = None,
    hop_s: float = DFLT_HOP_S,
    window_s: float = DFLT_WINDOW_S,
    fmin: float = DFLT_FMIN_HZ,
    fmax: float = DFLT_FMAX_HZ,
    speech_floor_db: float = DFLT_SPEECH_FLOOR_DB,
    min_pause_s: float = DFLT_MIN_PAUSE_S,
    phrase_pause_s: float = DFLT_PHRASE_PAUSE_S,
    emphasis_db: float = DFLT_EMPHASIS_DB,
    emphasis_st: float = DFLT_EMPHASIS_ST,
    peak_gap_s: float = DFLT_PEAK_GAP_S,
    final_share: float = DFLT_FINAL_SHARE,
    reference_hz: float | None = None,
) -> ProsodyStats:
    """Measure one clip's delivery (see the module docstring for each metric).

    ``samples`` is mono audio at ``sr`` Hz (any scale); ``text`` is what is said,
    used only to count syllables for the two rates; ``reference_hz`` is the pitch
    ``register_st`` is measured from.
    """
    x = np.asarray(samples, dtype=np.float64).ravel()
    duration = len(x) / sr if sr else 0.0
    nan = math.nan
    level = _level_db(x, sr, window_s=window_s, hop_s=hop_s)
    loud = level[level > -100] if level.size else level
    if loud.size == 0 or not np.isfinite(loud).any() or np.max(loud) <= -90:
        return ProsodyStats(
            duration,
            0.0,
            0.0,
            count_syllables(text) if text else None,
            0,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
            nan,
        )
    speech = level >= np.percentile(level, 95) - speech_floor_db
    on = np.flatnonzero(speech)
    first, last = int(on[0]), int(on[-1]) + 1
    span_frames = last - first
    speech_in = speech[first:last]
    pause_runs = [
        (a, b) for a, b in _runs(~speech_in) if (b - a) * hop_s >= min_pause_s
    ]
    # Short gaps (stop closures) are speech for every purpose below.
    talking = np.ones(span_frames, dtype=bool)
    for a, b in pause_runs:
        talking[a:b] = False
    # n all-silent frames span (n - 1) hops plus one window of silence.
    pause_lengths = [(b - a - 1) * hop_s + window_s for a, b in pause_runs]
    span_s = float(span_frames * hop_s)
    speech_s = float(max(span_s - sum(pause_lengths), 0.0))
    syl = count_syllables(text) if text else None

    f0 = pitch_track(x, sr, fmin=fmin, fmax=fmax, hop_s=hop_s, window_s=window_s)
    f0 = f0[: len(level)]
    if len(f0) < len(level):
        f0 = np.concatenate([f0, np.full(len(level) - len(f0), np.nan)])
    f0 = f0[first:last].copy()
    f0[~talking] = np.nan
    f0 = _median_filter_nan(_fold_octaves(f0), _SMOOTH_FRAMES)
    voiced = ~np.isnan(f0)
    f0_med = float(np.median(f0[voiced])) if voiced.any() else nan
    st = 12 * np.log2(f0 / f0_med) if voiced.any() else np.full_like(f0, np.nan)
    st_v = st[voiced]

    # Phrase endings: speech between pauses of at least phrase_pause_s.
    phrase_mask = np.ones(span_frames, dtype=bool)
    for a, b in pause_runs:
        if (b - a) * hop_s >= phrase_pause_s:
            phrase_mask[a:b] = False
    drops = []
    for a, b in _runs(phrase_mask):
        seg = st[a:b]
        seg = seg[~np.isnan(seg)]
        if seg.size < _MIN_VOICED_PER_PHRASE:
            continue
        tail = seg[int(len(seg) * (1 - final_share)) :]
        drops.append(float(np.median(tail) - np.median(seg)))

    lv = level[first:last]
    lv_talk = lv[talking]
    lv_med = float(np.median(lv_talk))
    kernel = np.ones(3) / 3
    env = np.convolve(lv, kernel, mode="same")
    peaks = [
        p for p in _peaks(env, min_gap=max(1, int(peak_gap_s / hop_s))) if talking[p]
    ]
    emph = [
        p
        for p in peaks
        if env[p] - lv_med >= emphasis_db
        or (not np.isnan(st[p]) and st[p] >= emphasis_st)
    ]
    return ProsodyStats(
        duration_s=duration,
        span_s=span_s,
        speech_s=speech_s,
        syllables=syl,
        pauses=len(pause_lengths),
        articulation_rate_sps=(syl / speech_s) if syl and speech_s else nan,
        speech_rate_sps=(syl / span_s) if syl and span_s else nan,
        pause_share=float(sum(pause_lengths) / span_s) if span_s else nan,
        pauses_per_min=(len(pause_lengths) * 60 / span_s) if span_s else nan,
        pause_median_s=_nan_stat(pause_lengths, np.median),
        pause_p90_s=_nan_stat(pause_lengths, lambda a: np.percentile(a, 90)),
        f0_median_hz=f0_med,
        f0_sd_st=_nan_stat(st_v, np.std),
        f0_range_st=_nan_stat(
            st_v, lambda a: np.percentile(a, 95) - np.percentile(a, 5)
        ),
        final_drop_st=_nan_stat(drops, np.median),
        loudness_range_db=float(
            np.percentile(lv_talk, 90) - np.percentile(lv_talk, 10)
        ),
        emphasis_per_s=(len(emph) / speech_s) if speech_s else nan,
        voiced_share=(float(voiced.sum()) / float(talking.sum()))
        if talking.any()
        else nan,
        register_st=(
            float(12 * math.log2(f0_med / reference_hz))
            if reference_hz and not math.isnan(f0_med)
            else nan
        ),
    )


def join_speech(
    clips: Iterable[np.ndarray],
    sr: int,
    *,
    gap_s: float = 0.0,
    speech_floor_db: float = DFLT_SPEECH_FLOOR_DB,
    hop_s: float = DFLT_HOP_S,
    window_s: float = DFLT_WINDOW_S,
) -> np.ndarray:
    """Clips with their leading and trailing silence trimmed, joined with ``gap_s``
    of silence — so a set of lines measures as one performance without the
    authored gaps between lines counting as the voice's pauses.

    >>> sr = 1000
    >>> c = np.concatenate([np.zeros(200), np.ones(300), np.zeros(200)])
    >>> 0.6 <= len(join_speech([c, c], sr)) / sr < 0.7  # edges blur by one window
    True
    """
    out, gap = [], np.zeros(int(gap_s * sr))
    hop = max(1, int(hop_s * sr))
    for clip in clips:
        x = np.asarray(clip, dtype=np.float64).ravel()
        level = _level_db(x, sr, window_s=window_s, hop_s=hop_s)
        on = (
            np.flatnonzero(level >= np.percentile(level, 95) - speech_floor_db)
            if level.size
            else []
        )
        if len(on) == 0:
            continue
        if out and gap.size:
            out.append(gap)
        out.append(x[on[0] * hop : min(len(x), (on[-1] + 1) * hop)])
    return np.concatenate(out) if out else np.zeros(0)


def decode_audio(
    path: str | Path, *, sr: int = DFLT_SR, ffmpeg: str = "ffmpeg"
) -> np.ndarray:
    """Any audio file ffmpeg reads, as mono float32 samples at ``sr`` Hz."""
    exe = shutil.which(ffmpeg)
    if exe is None:
        raise ProsodyDecodeError(
            f"{ffmpeg!r} not found: install ffmpeg (macOS: `brew install ffmpeg`) to decode audio"
        )
    cmd = [
        exe,
        "-v",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "f32le",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise ProsodyDecodeError(
            f"ffmpeg could not decode {path}: {proc.stderr.decode(errors='replace')[-300:]}"
        )
    return np.frombuffer(proc.stdout, dtype=np.float32)


def measure_prosody_file(
    paths: str | Path | Sequence[str | Path],
    *,
    text: str | None = None,
    sr: int = DFLT_SR,
    **knobs: Any,
) -> ProsodyStats:
    """Measure one audio file, or several joined by :func:`join_speech` (one
    performance). ``text`` is the words of all of them together.

    Joining moves the pitch statistics: each line has its own register, so a
    joined set spreads wider than any of its lines. To compare lines with
    per-sentence targets, use :func:`measure_lines`."""
    if isinstance(paths, (str, Path)):
        samples = decode_audio(paths, sr=sr)
    else:
        samples = join_speech([decode_audio(p, sr=sr) for p in paths], sr)
    return measure_prosody(samples, sr, text=text, **knobs)


def median_stats(stats: Sequence[ProsodyStats]) -> ProsodyStats:
    """The per-field median of several clips' stats (``nan`` ignored); counts
    and durations are summed. How a set of lines is compared with targets
    measured per sentence.

    >>> a = ProsodyStats(1.0, 1.0, 1.0, 3, 0, *[1.0] * 13)
    >>> b = ProsodyStats(2.0, 2.0, 2.0, 5, 1, *[3.0] * 13)
    >>> m = median_stats([a, b])
    >>> m.f0_sd_st, m.syllables, m.span_s
    (2.0, 8, 3.0)
    """
    if not stats:
        raise ValueError("median_stats needs at least one ProsodyStats")
    summed = {"duration_s", "span_s", "speech_s", "syllables", "pauses"}
    out: dict[str, Any] = {}
    for name in ProsodyStats.__dataclass_fields__:
        values = [getattr(s, name) for s in stats]
        if name in summed:
            known = [v for v in values if v is not None]
            out[name] = sum(known) if known else None
            continue
        arr = np.array([v for v in values if v is not None], dtype=float)
        arr = arr[~np.isnan(arr)]
        out[name] = float(np.median(arr)) if arr.size else math.nan
    return ProsodyStats(**out)


def measure_lines(
    paths: Sequence[str | Path],
    *,
    texts: Sequence[str | None] | None = None,
    sr: int = DFLT_SR,
    **knobs: Any,
) -> ProsodyStats:
    """Measure each file on its own (with its own text) and return the
    :func:`median_stats` — the comparison for targets measured per sentence."""
    texts = list(texts) if texts is not None else [None] * len(paths)
    if len(texts) != len(paths):
        raise ValueError(f"{len(paths)} files but {len(texts)} texts")
    return median_stats(
        [
            measure_prosody(decode_audio(p, sr=sr), sr, text=t, **knobs)
            for p, t in zip(paths, texts)
        ]
    )


# -----------------------------------------------------------------------------
# Targets
# -----------------------------------------------------------------------------


def validate_targets(targets: Mapping[str, Any]) -> None:
    """Raise :class:`ProsodyTargetError` unless every target names a metric and is a ``[low, high]`` range.

    >>> validate_targets({"f0_sd_st": [2, 4]})
    >>> validate_targets({"f0_sd_st": [4, 2]})
    Traceback (most recent call last):
    ...
    an.verify.prosody.ProsodyTargetError: prosody target 'f0_sd_st' must be [low, high], got [4, 2]
    """
    for name, rng in targets.items():
        if name not in METRICS:
            raise ProsodyTargetError(
                f"unknown prosody target {name!r}; measurable targets are [{', '.join(sorted(METRICS))}]"
            )
        ok = (
            isinstance(rng, (list, tuple))
            and len(rng) == 2
            and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) for v in rng
            )
        )
        if not ok or rng[0] > rng[1]:
            raise ProsodyTargetError(
                f"prosody target {name!r} must be [low, high], got {rng!r}"
            )


def check_prosody(
    stats: ProsodyStats,
    targets: Mapping[str, Sequence[float]],
    *,
    miss_severity: str = "warning",
    path_prefix: str = "<prosody>",
) -> list[Finding]:
    """One finding per target ``stats`` misses (an ``info`` for one it cannot measure)."""
    validate_targets(targets)
    findings = []
    for name, (lo, hi) in targets.items():
        value = getattr(stats, name)
        path = f"{path_prefix}/{name}"
        if value is None or (isinstance(value, float) and math.isnan(value)):
            findings.append(
                Finding("info", path, f"{name} not measurable on this clip")
            )
            continue
        if lo <= value <= hi:
            continue
        lower, raise_ = _FIXES.get(name, ("", ""))
        fix = lower if value > hi else raise_
        findings.append(
            Finding(
                miss_severity,
                path,
                f"{name} = {value:.3g}, target [{lo}, {hi}]",
                fix or None,
            )
        )
    return findings


def target_distance(
    stats: ProsodyStats,
    targets: Mapping[str, Sequence[float]],
    *,
    unmeasurable: float = 1.0,
) -> tuple[float, float]:
    """How far ``stats`` sits from ``targets``: ``(outside, off_centre)``, lower is closer.

    ``outside`` sums, over the targets, the distance outside ``[low, high]`` in
    units of the range's width (0 for a value inside); a metric this clip cannot
    measure counts ``unmeasurable`` widths, so a broken take never wins by
    having no number. ``off_centre`` sums each value's distance from its range's
    midpoint, in the same units — the tie-break between takes that are all on
    target. A zero-width range counts as one unit wide.

    >>> s = ProsodyStats(1.0, 1.0, 1.0, 3, 0, *[3.0] * 13)
    >>> target_distance(s, {"f0_sd_st": [2, 4]})
    (0.0, 0.0)
    >>> target_distance(s, {"f0_sd_st": [4, 6], "f0_range_st": [1, 5]})
    (0.5, 1.0)
    """
    validate_targets(targets)
    outside = off_centre = 0.0
    for name, (lo, hi) in targets.items():
        value = getattr(stats, name)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            outside += unmeasurable
            off_centre += unmeasurable
            continue
        width = (hi - lo) or 1.0
        outside += max(lo - value, 0.0, value - hi) / width
        off_centre += abs(value - (lo + hi) / 2.0) / width
    return outside, off_centre


def prosody_lint(
    audio: str | Path | Sequence[str | Path] | ProsodyStats,
    targets: Mapping[str, Sequence[float]],
    *,
    text: str | None = None,
    miss_severity: str = "warning",
) -> tuple[ProsodyStats, VerificationReport]:
    """Measure ``audio`` (a path, several paths, or stats already measured) and
    report each target it misses. Passes unless ``miss_severity`` is ``error``."""
    stats = (
        audio
        if isinstance(audio, ProsodyStats)
        else measure_prosody_file(audio, text=text)
    )
    report = VerificationReport()
    for f in check_prosody(stats, targets, miss_severity=miss_severity):
        report.add(f.severity, f.ir_path, f.description, f.suggested_fix)
    return stats, report


def _targets_from(spec_path: str | Path, role: str | None) -> dict[str, Any]:
    """A style spec's ``prosody_targets`` (for ``role``), or a bare targets file."""
    import yaml

    doc = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8")) or {}
    found = doc.get("prosody_targets", doc)
    if role is not None:
        if role not in found:
            raise ProsodyTargetError(
                f"no prosody targets for role {role!r}; have {sorted(found)}"
            )
        found = found[role]
    return dict(found)


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m an.verify.prosody AUDIO... [--targets SPEC --role ROLE] [--text T] [--reference-hz F] [--json]``."""
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m an.verify.prosody", description=__doc__.split("\n")[0]
    )
    p.add_argument(
        "audio",
        nargs="+",
        help="audio file(s); several are measured as one performance",
    )
    p.add_argument(
        "--targets", help="a style spec (its prosody_targets) or a targets YAML"
    )
    p.add_argument("--role", help="the role whose targets apply (narrator, eager, ...)")
    p.add_argument(
        "--text",
        action="append",
        help="the words spoken (for the syllable rates); once per file, or once for all with --joined",
    )
    p.add_argument(
        "--joined",
        action="store_true",
        help="measure several files as one joined performance instead of the median of the lines",
    )
    p.add_argument(
        "--reference-hz",
        type=float,
        help="the voice's neutral median pitch (for register_st)",
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    texts = args.text or []
    if len(args.audio) == 1 or args.joined:
        paths = args.audio[0] if len(args.audio) == 1 else args.audio
        stats = measure_prosody_file(
            paths, text=" ".join(texts) or None, reference_hz=args.reference_hz
        )
    else:
        stats = measure_lines(
            args.audio, texts=texts or None, reference_hz=args.reference_hz
        )
    targets = _targets_from(args.targets, args.role) if args.targets else {}
    findings = check_prosody(stats, targets) if targets else []
    if args.json:
        print(
            json.dumps(
                {"stats": stats.as_dict(), "findings": [asdict(f) for f in findings]},
                indent=2,
            )
        )
        return 0
    d = stats.as_dict()
    for name in METRICS:
        rng = targets.get(name)
        mark = (
            ""
            if rng is None or d[name] is None
            else ("  ok" if rng[0] <= d[name] <= rng[1] else "  MISS")
        )
        print(f"{name:24} {d[name]!s:>9}  {list(rng) if rng else ''}{mark}")
    for f in findings:
        print(
            f"{f.severity}: {f.description}"
            + (f" -> {f.suggested_fix}" if f.suggested_fix else "")
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
