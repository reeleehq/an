"""Sounds store — one directory per sound: ``sound.json`` beside ``audio.wav``.

A sound is an asset like a character or a prop: bytes that end up in a video a
user ships, so it carries its provenance and licence (``source``, an
`an.ir.assets.AssetSource`) and the digest of the bytes the licence is attached
to. The metadata is the mapping's value; the audio is a sidecar read and written
through :meth:`SoundsStore.read_audio` / :meth:`SoundsStore.write_audio`, so no
caller builds a path by hand (pillar 7). `an.sounds` is the typed front door.
"""

from __future__ import annotations

from an.stores._common import JsonSidecarStore


class SoundsStore(JsonSidecarStore):
    """Per-sound directory store.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     store = SoundsStore(d)
    ...     store['hit'] = {'description': 'a stick on a table'}
    ...     store.write_audio('hit', b'RIFF....')
    ...     store['hit']['description'], store.read_audio('hit')
    ('a stick on a table', b'RIFF....')
    """

    META_NAME = "sound.json"
    #: The sidecar holding the audio bytes. WAV only in v1: `an.sounds` reads
    #: its header for the duration a fade-out needs, deterministically.
    AUDIO_NAME = "audio.wav"

    def read_audio(self, key: str) -> bytes:
        path = self._entry_dir(key) / self.AUDIO_NAME
        if not path.exists():
            raise KeyError(f"sound {key!r} has no audio sidecar")
        return path.read_bytes()

    def write_audio(self, key: str, data: bytes) -> None:
        self.sidecar_path(key, self.AUDIO_NAME).write_bytes(data)
