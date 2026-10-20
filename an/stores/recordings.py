"""Recordings store — one directory per recorded take: ``recording.json`` beside ``audio.wav``.

A recording is a performer's take of one dialogue line, imported from an audio
file (``an voices import``, :mod:`an.audio.recorded`). Like a sound, it is bytes
that end up in a film a user ships, so its record carries provenance and rights
(``source``, an :class:`~an.ir.assets.AssetSource`: who recorded it, under which
licence or permission, from which file and span) and the digest of the bytes the
licence is attached to; ``an credits`` walks this store like the others. The
record also says which voice and line the take belongs to and, when they are
known, the words it contains and when (:data:`an.audio.recorded.RECORD_VERSION`
names the shape).

>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = RecordingsStore(d)
...     store['carl--hello--1a2b3c4d'] = {'voice': 'carl_recorded', 'text': 'Hello.'}
...     store.write_audio('carl--hello--1a2b3c4d', b'RIFF....')
...     store['carl--hello--1a2b3c4d']['text'], store.read_audio('carl--hello--1a2b3c4d')
('Hello.', b'RIFF....')
"""

from __future__ import annotations

from an.stores._common import AudioSidecarStore


class RecordingsStore(AudioSidecarStore):
    """Per-take directory store: ``<key>/recording.json`` + ``<key>/audio.wav``."""

    META_NAME = "recording.json"
    ENTRY_NOUN = "recording"
