"""Voice effects: a deterministic transform applied to a synthesized line (an#163).

A voice document in the ``voices`` store may declare ``effects``. Three exist:

- ``pitch_semitones`` (an#163) — South Park raises its voices to sound like
  fourth graders; duration-preserving.
- ``tempo`` (an#265) — a pitch-preserving speed ratio (``1.1`` is 10% faster).
  ``eleven_v3`` ignores ``voice_settings.speed`` and no audio tag moves its rate,
  so a narrator that must run at 5.8 syllables/s, or an expressive voice that
  must be slowed to a serene pace, is re-timed here. Unlike the pitch effect it
  CHANGES the line's duration.
- ``trim_silence`` (an#254) — cut the silence before the first word and after
  the last, keeping a little of each (``true``, or ``{threshold_db, keep_lead_s,
  keep_tail_s}``). A real voice pads a line: ``eleven_v3`` returned 1.6 s for
  "Hi!" — 0.4 s of breath before the word and 0.65 s of room tone after it — so
  the line started late and the next one ran past its shot. It CHANGES the
  line's duration too, and it is OPT-IN: a voice that values its breaths (a
  style that keeps a performance's natural artifacts) declares nothing, or a
  lower threshold, and keeps them.

A raised voice or a fast narrator is a property of the *character*, not of the
TTS provider, so it lives beside the voice the line already resolves through
rather than in the IR.

>>> normalize_effects({"pitch_semitones": 4})
{'pitch_semitones': 4.0, 'chain_version': 2}
>>> normalize_effects({"pitch_semitones": 0}) == normalize_effects({"tempo": 1}) == normalize_effects(None) == {}
True
>>> normalize_effects({"tempo": 1.1, "pitch_semitones": -2})
{'pitch_semitones': -2.0, 'tempo': 1.1, 'chain_version': 2}
>>> round(_pitch_filter(12), 3)
0.5
>>> filter_chain({"tempo": 1.25})
'aresample=44100,apad=pad_dur=0.25,atempo=1.250000000'
>>> normalize_effects({"trim_silence": True})["trim_silence"]
{'keep_lead_s': 0.1, 'keep_tail_s': 0.2, 'threshold_db': -20.0, 'version': 1}
>>> normalize_effects({"trim_silence": False}) == {}
True
>>> normalize_effects({"reverb": 1})
Traceback (most recent call last):
    ...
an.audio.effects.VoiceEffectError: unknown voice effect(s) ['reverb']; known: ['pitch_semitones', 'tempo', 'trim_silence']

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
- **The trim runs last, in Python**, on the WAV the chain wrote (or on the
  synthesized audio, decoded by ffmpeg only when it is not 16-bit PCM WAV —
  ElevenLabs sends MP3): the level of each :data:`TRIM_WINDOW_S` window is
  compared with the line's loudest, so a quiet voice and a loud one are cut
  alike, and the kept padding is in the seconds the viewer hears. Its
  parameters, resolved (defaults included) with :data:`TRIM_VERSION`, are what
  the key holds, so a changed default re-trims instead of replaying. What it
  cut is RECORDED in the WAV it writes — a standard ``LIST``/``INFO`` comment
  after the samples, which every reader skips — and :func:`trim_record` reads
  it back: the record travels with the bytes it describes and is collected
  with them. A line with nothing above the threshold (the offline voice's
  silence) is left whole.
"""

from __future__ import annotations

import io
import json
import shutil
import struct
import subprocess
import tempfile
import wave
from collections.abc import Mapping
from dataclasses import dataclass
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
#: The effect that cuts a line's leading and trailing silence (an#254).
TRIM_SILENCE = "trim_silence"
KNOWN_EFFECTS = ("pitch_semitones", "tempo", TRIM_SILENCE)

#: ``trim_silence``'s defaults. A window is "speech" when its RMS level is within
#: ``threshold_db`` of the line's loudest window. Measured on two eleven_v3 lines
#: (an#254): the breath before "Hi!" peaks 25 dB under the word and its room
#: tone 35-40 dB under, while each word's own edges stay within 20 dB — so -20
#: cuts the breath and the tail and keeps the word. Lower it (-45) to keep breaths.
DFLT_TRIM_THRESHOLD_DB: float = -20.0
#: Kept before the first window above the threshold: more than the lip-sync
#: anticipation lead (2/24 s), so the mouth can open before the sound.
DFLT_TRIM_KEEP_LEAD_S: float = 0.1
#: Kept after the last window above it: a word's release and decay.
DFLT_TRIM_KEEP_TAIL_S: float = 0.2
#: ``threshold_db`` bounds (relative to the line's loudest window).
TRIM_THRESHOLD_LIMITS: tuple[float, float] = (-80.0, -3.0)
#: ``keep_lead_s`` / ``keep_tail_s`` bounds, seconds.
TRIM_KEEP_LIMITS: tuple[float, float] = (0.0, 2.0)
#: The level-measuring window, seconds. Not keyed itself: a change to it (or
#: to anything else that moves a trimmed line's bytes) is a :data:`TRIM_VERSION`
#: bump — a test pins the trim's output to the version (an#309).
TRIM_WINDOW_S: float = 0.02
#: Bumped whenever a trimmed line's bytes would change (algorithm, window,
#: record tag, rounding); part of every trimmed line's key.
TRIM_VERSION: int = 1
#: The version of the ffmpeg chain every effected line passes (pitch, tempo,
#: and the decode of a non-WAV line before its trim): its filters, rate
#: (:data:`EFFECT_SAMPLE_RATE`), ``atempo`` stages and flags (an#309). Keyed
#: only once it is not the first, so introducing it moved no key; bump it with
#: any change to :func:`filter_chain`, :func:`ffmpeg_argv` or their constants
#: — a test pins them to the version. Moving the key re-processes each line
#: from its raw take, which is cached: nothing is billed.
#:
#: 2 (an#350): silence padded before the ``atempo`` stages and the output cut
#: to exactly ``input / tempo`` — ``atempo`` dropped the last 20-40 ms.
CHAIN_VERSION: int = 2
_FIRST_CHAIN_VERSION: int = 1
#: Seconds of silence appended before the ``atempo`` stages, so their window
#: never eats the line's tail (it dropped 20-40 ms of every short padded clip,
#: an#350); the output is then cut to the exact length the tempo gives.
#: Enough for the slowest stage of :data:`TEMPO_LIMITS` at every pitch.
TEMPO_PAD_S: float = 0.25
#: The prefix of the ``LIST``/``INFO`` comment a trimmed WAV carries.
TRIM_RECORD_TAG: str = "an:trim_silence "


class VoiceEffectError(ValueError):
    """A voice declares an effect that is unknown, malformed or out of range."""


def normalize_effects(raw: Mapping[str, Any] | None) -> dict[str, Any]:
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
    out: dict[str, Any] = {}
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
    trim = _normalize_trim(raw.get(TRIM_SILENCE))
    if trim:
        out[TRIM_SILENCE] = trim
    if out and CHAIN_VERSION != _FIRST_CHAIN_VERSION:
        out["chain_version"] = CHAIN_VERSION
    return out


def _normalize_trim(raw: Any) -> dict[str, Any]:
    """``trim_silence``'s canonical form: ``{}`` when off, else every parameter
    resolved (defaults included) plus :data:`TRIM_VERSION` — what the key holds."""
    if raw is None or raw is False:
        return {}
    if raw is True:
        raw = {}
    if not isinstance(raw, Mapping):
        raise VoiceEffectError(
            f"trim_silence must be true, false or a mapping of threshold_db, "
            f"keep_lead_s, keep_tail_s; got {raw!r}"
        )
    known = {"threshold_db", "keep_lead_s", "keep_tail_s"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise VoiceEffectError(
            f"unknown trim_silence parameter(s) {unknown}; known: {sorted(known)}"
        )
    params = {
        "threshold_db": raw.get("threshold_db", DFLT_TRIM_THRESHOLD_DB),
        "keep_lead_s": raw.get("keep_lead_s", DFLT_TRIM_KEEP_LEAD_S),
        "keep_tail_s": raw.get("keep_tail_s", DFLT_TRIM_KEEP_TAIL_S),
    }
    for name, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise VoiceEffectError(
                f"trim_silence {name} must be a number, got {value!r}"
            )
        lo, hi = TRIM_THRESHOLD_LIMITS if name == "threshold_db" else TRIM_KEEP_LIMITS
        if not lo <= value <= hi:
            raise VoiceEffectError(
                f"trim_silence {name} {value} is outside [{lo:g}, {hi:g}]"
                + (
                    " (dB under the line's loudest window: -20 cuts breaths, "
                    "-45 keeps them)"
                    if name == "threshold_db"
                    else " seconds"
                )
            )
    return {
        **{k: float(v) for k, v in sorted(params.items())},
        "version": TRIM_VERSION,
    }


def voice_effects(mall: Mapping | None, voice_id: str) -> dict[str, Any]:
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


def filter_chain(effects: Mapping[str, Any]) -> str:
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
    return ",".join(
        [
            head,
            f"apad=pad_dur={TEMPO_PAD_S:g}",
            *(f"atempo={f:.9f}" for f in atempo_stages(factor)),
        ]
    )


def decode_chain() -> str:
    """The chain that decodes a non-WAV line (MP3, from ElevenLabs) before its
    trim (part of :data:`CHAIN_VERSION`)."""
    return f"aresample={EFFECT_SAMPLE_RATE}"


def apply_voice_effects(audio: bytes, effects: Mapping[str, Any]) -> bytes:
    """``audio`` (any container ffmpeg sniffs) with ``effects`` applied, as WAV bytes.

    Returns the input unchanged for no effects. Raises ``VoiceEffectError`` when
    ffmpeg is missing or fails — never returns unprocessed audio for a voice that
    asked for an effect. ``trim_silence`` alone on a 16-bit PCM WAV needs no
    ffmpeg (:func:`trim_silence`).
    """
    chain = filter_chain(effects)
    trim = effects.get(TRIM_SILENCE)
    if not chain and not trim:
        return audio
    if chain:
        wav = _ffmpeg_wav(audio, chain, effects)
    elif _pcm16_wav(audio):
        wav = audio
    else:  # MP3 (ElevenLabs) and other containers: decoded, then trimmed
        wav = _ffmpeg_wav(audio, decode_chain(), effects)
    if trim:
        wav = trim_silence(
            wav,
            threshold_db=trim["threshold_db"],
            keep_lead_s=trim["keep_lead_s"],
            keep_tail_s=trim["keep_tail_s"],
        ).audio
    return wav


#: The output options of every WAV the chain writes: bit-exact 16-bit PCM.
_WAV_OUT: tuple[str, ...] = (
    "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
    "-c:a", "pcm_s16le",
)  # fmt: skip


def ffmpeg_argv(
    chain: str, out_path: Path | str, *, source_path: Path | str | None = None
) -> list[str]:
    """The argv that runs ``chain`` over audio on stdin into a bit-exact 16-bit
    PCM WAV at ``out_path`` (part of :data:`CHAIN_VERSION`).

    source_path: also write the input, decoded (:func:`decode_chain`) and
        untouched, there — in the same run, so its length is known whatever
        container came in (an#350: a tempo chain's output is cut to it)

    >>> ffmpeg_argv("aresample=44100", "o.wav")[-3:]
    ['-c:a', 'pcm_s16le', 'o.wav']
    >>> ffmpeg_argv("atempo=2", "o.wav", source_path="s.wav")[-1]
    's.wav'
    """
    head = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        "pipe:0",
    ]
    if source_path is None:
        return [*head, "-af", chain, *_WAV_OUT, str(out_path)]
    graph = f"[0:a]asplit=2[fx][src];[fx]{chain}[out];[src]{decode_chain()}[raw]"
    return [
        *head, "-filter_complex", graph,
        "-map", "[out]", *_WAV_OUT, str(out_path),
        "-map", "[raw]", *_WAV_OUT, str(source_path),
    ]  # fmt: skip


def _ffmpeg_wav(audio: bytes, chain: str, effects: Mapping[str, Any]) -> bytes:
    """``audio`` through the ffmpeg ``chain``, as bit-exact 16-bit PCM WAV."""
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
        # A tempo chain also writes the decoded input: its length is what the
        # output is cut to (an#350; `atempo` drops the tail of its window).
        source_path = Path(tmp) / "source.wav" if "atempo=" in chain else None
        proc = subprocess.run(
            ffmpeg_argv(chain, out_path, source_path=source_path),
            input=audio,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not out_path.exists():
            raise VoiceEffectError(
                f"ffmpeg failed applying {dict(effects)}: "
                f"{proc.stderr.decode(errors='replace').strip()}"
            )
        if source_path is None:
            return out_path.read_bytes()
        seconds = _seconds(source_path.read_bytes()) / (effects.get("tempo") or 1.0)
        return _exact_frames(out_path.read_bytes(), round(seconds * EFFECT_SAMPLE_RATE))


def _seconds(wav: bytes) -> float:
    """The length of a 16-bit PCM WAV, seconds."""
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.getnframes() / w.getframerate()


def _exact_frames(wav: bytes, frames: int) -> bytes:
    """``wav`` (16-bit PCM) cut, or padded with silence, to exactly ``frames`` frames.

    >>> import array
    >>> buf = io.BytesIO()
    >>> with wave.open(buf, "wb") as w:
    ...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(8); w.writeframes(array.array("h", [1] * 10).tobytes())
    >>> [_seconds(_exact_frames(buf.getvalue(), n)) for n in (4, 12)]
    [0.5, 1.5]
    """
    with wave.open(io.BytesIO(wav), "rb") as w:
        params = w.getparams()
        data = w.readframes(min(frames, w.getnframes()))
    width = params.sampwidth * params.nchannels
    data += b"\x00" * (frames * width - len(data))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        w.writeframes(data)
    return out.getvalue()


def _pcm16_wav(audio: bytes) -> bool:
    """Whether ``audio`` is a WAV the stdlib reads as 16-bit PCM."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as w:
            return w.getsampwidth() == 2 and w.getcomptype() == "NONE"
    except (wave.Error, EOFError):
        return False


@dataclass(frozen=True)
class SilenceTrim:
    """What :func:`trim_silence` produced: the trimmed WAV, and what it cut."""

    audio: bytes
    #: Seconds cut before the kept audio, and after it.
    lead_s: float
    tail_s: float
    #: The length of the audio before the trim, seconds.
    source_s: float

    def record(self) -> dict[str, float]:
        """The record the trimmed WAV carries (:func:`trim_record`)."""
        return {
            "lead_s": round(self.lead_s, 6),
            "tail_s": round(self.tail_s, 6),
            "source_s": round(self.source_s, 6),
        }


def speech_end(
    audio: bytes,
    *,
    threshold_db: float = DFLT_TRIM_THRESHOLD_DB,
    window_s: float = TRIM_WINDOW_S,
) -> float | None:
    """Seconds into ``audio`` at which its audible speech ends (an#397); ``None`` when silent or unreadable.

    The end of the last ``window_s`` window whose RMS level is within
    ``threshold_db`` of the loudest window's — :func:`trim_silence`'s rule, so
    a take's own trailing silence (a provider pads ~0.3 s) is not counted. A
    16-bit PCM WAV is read directly; any other container is decoded with ffmpeg
    when it is installed.

    >>> import array, io, wave
    >>> rate = 8000
    >>> samples = array.array("h", [9000, -9000] * (rate // 4) + [0] * rate)  # 0.5 s, then 1 s silent
    >>> buf = io.BytesIO()
    >>> with wave.open(buf, "wb") as w:
    ...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(samples.tobytes())
    >>> round(speech_end(buf.getvalue()), 2)
    0.5
    """
    import numpy as np

    wav = audio
    if not _pcm16_wav(wav):
        if shutil.which("ffmpeg") is None:
            return None
        try:
            wav = _ffmpeg_wav(audio, decode_chain(), {})
        except VoiceEffectError:
            return None
    try:
        with wave.open(io.BytesIO(wav), "rb") as r:
            channels, rate = r.getnchannels(), r.getframerate()
            frames = r.readframes(r.getnframes())
    except (wave.Error, EOFError):
        return None
    samples = np.frombuffer(frames, dtype="<i2").reshape(-1, channels)
    n = len(samples)
    if not n or not rate:
        return None
    mono = samples.astype(np.float64).mean(axis=1)
    win = max(1, int(round(window_s * rate)))
    n_win = -(-n // win)
    padded = np.zeros(n_win * win)
    padded[:n] = mono
    power = (padded.reshape(n_win, win) ** 2).mean(axis=1)
    peak = float(power.max())
    if peak <= 0.0:
        return None
    loud = np.nonzero(power >= peak * 10.0 ** (threshold_db / 10.0))[0]
    return min(n, (int(loud[-1]) + 1) * win) / rate


def trim_silence(
    wav: bytes,
    *,
    threshold_db: float = DFLT_TRIM_THRESHOLD_DB,
    keep_lead_s: float = DFLT_TRIM_KEEP_LEAD_S,
    keep_tail_s: float = DFLT_TRIM_KEEP_TAIL_S,
    window_s: float = TRIM_WINDOW_S,
) -> SilenceTrim:
    """``wav`` (16-bit PCM) cut to its speech, plus ``keep_lead_s`` before it and
    ``keep_tail_s`` after it, and the cut recorded in the WAV it returns.

    Speech is every ``window_s`` window whose RMS level is within
    ``threshold_db`` of the loudest window's; only the edges move, never a pause
    between words. A clip with no sound at all is returned whole (with the
    record of a zero cut), and a pad is never longer than the silence it keeps.

    >>> import array, io, math, wave
    >>> rate = 8000
    >>> tone = [int(9000 * math.sin(i / 3)) for i in range(rate // 2)]
    >>> samples = array.array("h", [0] * rate + tone + [0] * rate)   # 1 s, 0.5 s, 1 s
    >>> buf = io.BytesIO()
    >>> with wave.open(buf, "wb") as w:
    ...     w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    ...     w.writeframes(samples.tobytes())
    >>> cut = trim_silence(buf.getvalue(), keep_lead_s=0.1, keep_tail_s=0.2)
    >>> round(cut.lead_s, 2), round(cut.tail_s, 2), round(cut.source_s, 2)
    (0.9, 0.8, 2.5)
    >>> trim_record(cut.audio) == cut.record()
    True
    >>> with wave.open(io.BytesIO(cut.audio)) as w:
    ...     round(w.getnframes() / w.getframerate(), 2)
    0.8
    """
    import numpy as np

    with wave.open(io.BytesIO(wav), "rb") as r:
        channels, width, rate = r.getnchannels(), r.getsampwidth(), r.getframerate()
        frames = r.readframes(r.getnframes())
    if width != 2:
        raise VoiceEffectError(
            f"trim_silence reads 16-bit PCM; this WAV is {8 * width}-bit"
        )
    samples = np.frombuffer(frames, dtype="<i2").reshape(-1, channels)
    n = len(samples)
    source_s = n / rate if rate else 0.0
    mono = samples.astype(np.float64).mean(axis=1)
    win = max(1, int(round(window_s * rate)))
    n_win = -(-n // win)  # the last, partial window counts too
    padded = np.zeros(n_win * win)
    padded[:n] = mono
    power = (padded.reshape(n_win, win) ** 2).mean(axis=1) if n else np.zeros(0)
    peak = float(power.max()) if n else 0.0
    if peak <= 0.0:
        return _trimmed(samples, 0, n, rate=rate, width=width, source_s=source_s)
    loud = np.nonzero(power >= peak * 10.0 ** (threshold_db / 10.0))[0]
    first, last_end = int(loud[0]) * win, min(n, (int(loud[-1]) + 1) * win)
    start = max(0, first - int(round(keep_lead_s * rate)))
    end = min(n, last_end + int(round(keep_tail_s * rate)))
    return _trimmed(samples, start, end, rate=rate, width=width, source_s=source_s)


def _trimmed(samples, start: int, end: int, *, rate: int, width: int, source_s: float):
    """The :class:`SilenceTrim` of ``samples[start:end]``, its WAV carrying the record."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(samples.shape[1])
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(samples[start:end].astype("<i2").tobytes())
    lead_s, tail_s = start / rate, (len(samples) - end) / rate
    record = SilenceTrim(b"", lead_s, tail_s, source_s).record()
    audio = _with_comment(buf.getvalue(), TRIM_RECORD_TAG + _canonical(record))
    return SilenceTrim(audio, lead_s, tail_s, source_s)


def _canonical(record: Mapping[str, Any]) -> str:
    return json.dumps(dict(record), sort_keys=True, separators=(",", ":"))


def _with_comment(wav: bytes, text: str) -> bytes:
    """``wav`` with a ``LIST``/``INFO``/``ICMT`` chunk appended AFTER its samples
    (readers stop at ``data``; a naive 44-byte reader never sees it), and the
    RIFF size patched to include it."""
    body = text.encode("utf-8") + b"\x00"
    if len(body) % 2:
        body += b"\x00"
    icmt = b"ICMT" + struct.pack("<I", len(body)) + body
    chunk = b"LIST" + struct.pack("<I", 4 + len(icmt)) + b"INFO" + icmt
    out = wav + chunk
    return out[:4] + struct.pack("<I", len(out) - 8) + out[8:]


def trim_record(wav: bytes) -> dict[str, float] | None:
    """What ``trim_silence`` cut from ``wav`` (``lead_s``, ``tail_s``, ``source_s``),
    read from the comment it wrote; ``None`` for audio it did not write."""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        return None
    pos = 12
    while pos + 8 <= len(wav):
        cid, size = wav[pos : pos + 4], struct.unpack("<I", wav[pos + 4 : pos + 8])[0]
        data = wav[pos + 8 : pos + 8 + size]
        if cid == b"LIST" and data[:4] == b"INFO":
            sub = 4
            while sub + 8 <= len(data):
                sid = data[sub : sub + 4]
                ssize = struct.unpack("<I", data[sub + 4 : sub + 8])[0]
                text = (
                    data[sub + 8 : sub + 8 + ssize]
                    .rstrip(b"\x00")
                    .decode("utf-8", "replace")
                )
                if sid == b"ICMT" and text.startswith(TRIM_RECORD_TAG):
                    try:
                        return json.loads(text[len(TRIM_RECORD_TAG) :])
                    except ValueError:
                        return None
                sub += 8 + ssize + (ssize % 2)
        pos += 8 + size + (size % 2)
    return None
