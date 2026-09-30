"""Sound assets: what the sound layer plays, where it came from, and a synthesizer.

A :class:`an.ir.schema.SoundCue` names a key in the project's ``sounds`` store;
this module is the typed front door to that store. Every sound carries an
:class:`~an.ir.assets.AssetSource` — provenance and licence — and the sha256 of
the bytes that licence is attached to, because a sound is third-party work far
more often than a character is, and **a licence recorded and never displayed is
not compliance**: ``an credits`` walks this store like the others.

>>> import tempfile
>>> from an.stores.sounds import SoundsStore
>>> with tempfile.TemporaryDirectory() as d:
...     store = SoundsStore(d)
...     asset = add_sound(store, "beep", synth_tone(440.0, 0.25), source=SYNTH_SOURCE)
...     asset.duration, get_sound(store, "beep")[1][:4]
(0.25, b'RIFF')

**v1 stores WAV (PCM) only.** The mix needs each asset's exact length to place
a fade-out, and a WAV header states it without decoding anything; convert other
formats with ffmpeg before adding them.

The synthesizers (:func:`synth_tone`, :func:`synth_hit`, :func:`synth_bed`) are
what the demo and the tests use instead of shipping any third-party audio: pure
numpy, seeded, so the same call writes the same bytes.
"""

from __future__ import annotations

import hashlib
import io
import math
import wave
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from an.base import FILM_AUDIO_SAMPLE_RATE
from an.ir.assets import AssetSource

__all__ = [
    "SYNTH_SOURCE",
    "SoundAsset",
    "SoundError",
    "add_sound",
    "get_sound",
    "synth_bed",
    "synth_hit",
    "synth_tone",
    "wav_info",
]

#: Full scale for the synthesizers' default amplitudes: a little under 0 dBFS
#: so a mix of a bed, a hit and a line does not clip before any gain is set.
DEFAULT_SYNTH_AMPLITUDE: float = 0.3
#: The int16 full-scale value the synthesizers quantize to.
_INT16_FULL_SCALE: int = 32767

#: The provenance of everything :func:`synth_tone` / :func:`synth_hit` /
#: :func:`synth_bed` produce: generated on the user's machine by ``an`` from
#: numbers, so no third party's work is in it.
SYNTH_SOURCE = AssetSource(
    provider="an.sounds",
    id="procedural-synthesis",
    license="cc0-1.0",
    author="an (procedural synthesis, generated locally)",
)


class SoundError(ValueError):
    """A sound the store cannot hold, or holds wrongly."""


class SoundAsset(BaseModel):
    """The ``sound.json`` of one entry in the ``sounds`` store."""

    model_config = ConfigDict(extra="allow")

    source: AssetSource
    #: Digest of ``audio.wav`` as it entered the project; checked on every read.
    sha256: str
    sample_rate: int
    channels: int
    #: Seconds, from the WAV header.
    duration: float
    description: str = ""


def wav_info(data: bytes) -> tuple[int, int, int]:
    """``(sample_rate, channels, frames)`` from a WAV's header.

    >>> wav_info(synth_tone(440.0, 0.5, sample_rate=8000))
    (8000, 1, 4000)
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getframerate(), w.getnchannels(), w.getnframes()
    except (wave.Error, EOFError) as e:
        raise SoundError(
            f"not a PCM WAV file ({e}). The sounds store holds WAV only; convert "
            "with: ffmpeg -i in.mp3 out.wav"
        ) from e


def add_sound(
    store: MutableMapping,
    key: str,
    audio: bytes,
    *,
    source: AssetSource | Mapping[str, Any],
    description: str = "",
) -> SoundAsset:
    """Put ``audio`` (WAV bytes) in ``store`` under ``key``, with its provenance.

    ``source`` is required: a sound with no recorded origin is exactly the
    asset ``an credits`` cannot vouch for. Its ``license`` may be ``None`` —
    that is recorded as UNKNOWN and reported as unverified, never as free.
    """
    source = AssetSource.model_validate(source)
    sample_rate, channels, frames = wav_info(audio)
    asset = SoundAsset(
        source=source,
        sha256=hashlib.sha256(audio).hexdigest(),
        sample_rate=sample_rate,
        channels=channels,
        duration=frames / sample_rate,
        description=description,
    )
    store[key] = asset.model_dump(exclude_none=True)
    store.write_audio(key, audio)
    return asset


def get_sound(store: Mapping, key: str) -> tuple[SoundAsset, bytes]:
    """``(asset, wav_bytes)`` for ``key``, the bytes checked against the digest.

    A mismatch raises: the licence is attached to the digest, so different
    bytes under the same key are an asset nobody recorded.
    """
    try:
        asset = SoundAsset.model_validate(store[key])
    except KeyError:
        raise KeyError(
            f"sound {key!r} is not in the sounds store; add it with "
            "an.sounds.add_sound(mall['sounds'], key, wav_bytes, source=...)"
        ) from None
    audio = store.read_audio(key)
    digest = hashlib.sha256(audio).hexdigest()
    if digest != asset.sha256:
        raise SoundError(
            f"sound {key!r}: audio.wav does not match the digest its licence was "
            f"recorded against ({digest[:12]} != {asset.sha256[:12]}). Re-add it "
            "with add_sound so its provenance describes these bytes."
        )
    return asset, audio


# -----------------------------------------------------------------------------
# Deterministic synthesis — what the demo and tests play instead of third-party
# audio.
# -----------------------------------------------------------------------------


def _wav_bytes(samples: Any, *, sample_rate: int) -> bytes:
    import numpy as np

    pcm = np.rint(np.clip(samples, -1.0, 1.0) * _INT16_FULL_SCALE).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _envelope(n: int, *, sample_rate: int, attack: float, release: float) -> Any:
    import numpy as np

    env = np.ones(n)
    a = min(n, int(round(attack * sample_rate)))
    r = min(n - a, int(round(release * sample_rate)))
    if a:
        env[:a] = np.arange(a) / a
    if r:
        env[n - r :] = np.arange(r, 0, -1) / r
    return env


def synth_tone(
    freq: float,
    duration: float,
    *,
    sample_rate: int = FILM_AUDIO_SAMPLE_RATE,
    amplitude: float = DEFAULT_SYNTH_AMPLITUDE,
    attack: float = 0.005,
    release: float = 0.02,
) -> bytes:
    """A sine at ``freq`` Hz, with short linear ramps so it does not click.

    >>> synth_tone(440.0, 0.1) == synth_tone(440.0, 0.1)
    True
    """
    import numpy as np

    n = int(round(duration * sample_rate))
    t = np.arange(n) / sample_rate
    wave_ = amplitude * np.sin(2 * math.pi * freq * t)
    env = _envelope(n, sample_rate=sample_rate, attack=attack, release=release)
    return _wav_bytes(wave_ * env, sample_rate=sample_rate)


def synth_hit(
    duration: float = 0.35,
    *,
    seed: int = 0,
    thump_hz: float = 90.0,
    decay: float = 0.06,
    sample_rate: int = FILM_AUDIO_SAMPLE_RATE,
    amplitude: float = 2 * DEFAULT_SYNTH_AMPLITUDE,
) -> bytes:
    """A percussive hit: a seeded noise burst over a low thump, decaying fast.

    >>> synth_hit(seed=1) == synth_hit(seed=1), synth_hit(seed=1) == synth_hit(seed=2)
    (True, False)
    """
    import numpy as np

    n = int(round(duration * sample_rate))
    t = np.arange(n) / sample_rate
    noise = np.random.default_rng(seed).uniform(-1.0, 1.0, n)
    body = np.sin(2 * math.pi * thump_hz * t)
    env = np.exp(-t / decay)
    return _wav_bytes(amplitude * env * (0.5 * noise + body), sample_rate=sample_rate)


def synth_bed(
    duration: float,
    *,
    chord: Sequence[float] = (220.0, 277.18, 329.63),
    pulse_hz: float = 2.0,
    sample_rate: int = FILM_AUDIO_SAMPLE_RATE,
    amplitude: float = DEFAULT_SYNTH_AMPLITUDE,
) -> bytes:
    """A music bed: a sustained chord with a gentle pulse, loopable end to end.

    The pulse is a whole number of cycles over ``duration`` when
    ``duration * pulse_hz`` is whole, so a looped bed does not bump at the seam.

    >>> len(synth_bed(1.0)) > 44 and synth_bed(1.0) == synth_bed(1.0)
    True
    """
    import numpy as np

    n = int(round(duration * sample_rate))
    t = np.arange(n) / sample_rate
    tones = sum(np.sin(2 * math.pi * f * t) for f in chord) / max(1, len(chord))
    pulse = 0.75 + 0.25 * np.cos(2 * math.pi * pulse_hz * t)
    return _wav_bytes(amplitude * tones * pulse, sample_rate=sample_rate)
