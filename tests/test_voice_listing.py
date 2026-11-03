"""A provider-neutral voice listing (an#712): rows a host filters on a field
(``is_library``) rather than on a provider's category string, with a host's
own key reaching the provider."""

from __future__ import annotations

from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.voice_listing import VoiceRow, list_voices


class _Voice:
    def __init__(self, voice_id, name, category, **labels):
        self.voice_id, self.name, self.labels = voice_id, name, labels
        self.category, self.description = category, f"{name}'s voice"
        self.preview_url = f"https://example.com/{voice_id}.mp3"


class _Page:
    def __init__(self, voices):
        self.voices, self.next_page_token, self.has_more = voices, None, False


class _Client:
    def __init__(self, voices):
        self._voices = voices
        outer = self

        class _Voices:
            def search(self, **kw):
                outer.searched = kw
                return _Page(outer._voices)

        self.voices = _Voices()


def test_elevenlabs_rows_say_which_voices_nobody_designed():
    keys = []
    client = _Client([_Voice("p1", "Rachel", "premade", accent="american", gender="female"),
                      _Voice("g1", "Jerry", "generated", accent="irish")])  # fmt: skip

    def make(name, *, api_key=None):
        assert name == "elevenlabs"
        keys.append(api_key)
        return ElevenLabsTTS(api_key=api_key, client_factory=lambda _key: client)

    rows = list_voices("elevenlabs", api_key="guest-key", search="r", make=make)
    assert keys == ["guest-key"] and client.searched["search"] == "r"
    assert [(r.voice_id, r.is_library, r.category) for r in rows] == [
        ("p1", True, "premade"),
        ("g1", False, "generated"),
    ]
    assert rows[0] == VoiceRow(
        voice_id="p1", name="Rachel", provider="elevenlabs", language="en",
        gender="female", accent="american", description="Rachel's voice",
        preview_url="https://example.com/p1.mp3", category="premade", is_library=True,
    )  # fmt: skip
    assert set(rows[0].as_dict()) == set(VoiceRow.__dataclass_fields__)


def test_built_in_voices_are_library_voices_and_search_works_locally():
    (row,) = list_voices("offline", search="offline")
    assert row.is_library is True
    assert list_voices("offline", search="nothing-like-it") == []


def test_an_unknown_provider_names_the_known_ones():
    import pytest

    with pytest.raises(ValueError, match="known:"):
        list_voices("nobody")
