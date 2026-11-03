"""A provider-neutral voice listing (an#712): rows a host filters on a field
(``is_stock``) rather than on a provider's category string, with a host's own
key reaching the provider, and an absent key never read as "list the
environment's account"."""

from __future__ import annotations

import pytest

from an.audio.elevenlabs_tts import ElevenLabsTTS, ElevenLabsUnavailableError
from an.audio.offline_tts import OfflineTTS
from an.audio.providers import listable_providers, make_tts
from an.audio.voice_listing import list_voices

_ENV_KEYS = ("ELEVEN_API_KEY", "ELEVENLABS_API_KEY")


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


def test_elevenlabs_rows_say_which_voices_are_stock():
    keys = []
    client = _Client([_Voice("p1", "Rachel", "premade", accent="american", gender="female"),
                      _Voice("g1", "Jerry", "generated", accent="irish"),
                      _Voice("l1", "Dan", "professional", accent="irish")])  # fmt: skip

    def make(name, *, api_key=None):
        assert name == "elevenlabs"
        keys.append(api_key)
        return ElevenLabsTTS(api_key=api_key, client_factory=lambda _key: client)

    rows = list_voices("elevenlabs", api_key="guest-key", search="r", make=make)
    assert keys == ["guest-key"] and client.searched["search"] == "r"
    # a Voice Library voice the account added is not stock: only ``premade`` is
    assert [(r["voice_id"], r["is_stock"], r["category"]) for r in rows] == [
        ("p1", True, "premade"),
        ("g1", False, "generated"),
        ("l1", False, "professional"),
    ]
    assert rows[0] == {
        "voice_id": "p1", "name": "Rachel", "provider": "elevenlabs", "language": "en",
        "gender": "female", "is_stock": True, "accent": "american",
        "description": "Rachel's voice", "preview_url": "https://example.com/p1.mp3",
        "category": "premade",
    }  # fmt: skip


def test_elevenlabs_fills_the_fields_and_keeps_the_extra_keys_one_cycle():
    client = _Client([_Voice("p1", "Rachel", "premade", accent="american")])
    (meta,) = ElevenLabsTTS(api_key="k", client_factory=lambda _k: client).list_voices()
    assert (meta.accent, meta.description, meta.preview_url) == (
        "american", "Rachel's voice", "https://example.com/p1.mp3"
    )  # fmt: skip
    # hosts read these since an#666
    assert meta.extra["preview_url"] == meta.preview_url
    assert meta.extra["description"] == meta.description


def test_built_in_voices_are_stock_and_search_works_locally():
    (row,) = list_voices("offline", search="offline")
    assert row["is_stock"] is True
    assert list_voices("offline", search="nothing-like-it") == []


def test_local_search_reads_the_description():
    from an.audio.tts import VoiceMeta

    class Fake:
        name = "fake"

        def list_voices(self):
            return [VoiceMeta("v1", "Ada", "fake", description="a gravelly baritone")]

    assert [
        r["voice_id"] for r in list_voices("x", search="gravel", make=lambda _: Fake())
    ] == ["v1"]


def test_a_make_that_takes_no_key_serves_a_keyless_listing():
    (row,) = list_voices("offline", make=lambda _name: OfflineTTS())
    assert row["voice_id"] == "default"


def test_an_empty_key_is_refused_not_read_as_the_environments():
    with pytest.raises(ValueError, match="empty api_key"):
        list_voices("elevenlabs", api_key="")


def test_no_key_anywhere_raises_rather_than_listing_nothing(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ElevenLabsUnavailableError, match="API key"):
        list_voices("elevenlabs")
    # the provider's own listing keeps its documented "absent key -> []"
    assert list(ElevenLabsTTS().list_voices()) == []


def test_an_unknown_provider_names_the_known_ones():
    with pytest.raises(ValueError, match="known:"):
        list_voices("nobody")


def test_make_tts_hands_a_hosts_key_to_elevenlabs(monkeypatch):
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    assert make_tts("elevenlabs", api_key="k").api_key == "k"
    assert make_tts("elevenlabs").api_key is None
    # a provider that takes no key is built as before
    assert make_tts("offline", api_key="k").name == "offline"


def test_make_tts_still_hands_the_mall_to_recorded():
    store = {}
    assert make_tts("recorded", mall={"recordings": store}).recordings is store


def test_listable_providers_are_those_that_take_a_key():
    assert listable_providers() == ["elevenlabs"]
    factories = {"own_key": lambda *, api_key=None: None, "keyless": lambda: None}
    assert listable_providers(factories=factories) == ["own_key"]


def test_the_row_type_names_exactly_the_keys_as_row_gives():
    """an#712 re-review: ``VoiceRow`` (a TypedDict) is pinned to what
    ``VoiceMeta.as_row`` returns, so a field added to one reaches the other."""
    from an.audio.tts import VoiceMeta
    from an.audio.voice_listing import VoiceRow

    assert set(VoiceRow.__annotations__) == set(VoiceMeta("v", "n", "p").as_row())
