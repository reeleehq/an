"""A lip-sync provider's cache seam (an#727): ``cache_version`` re-keys the
tracks it cached without renaming it; a provider that states none keeps every
key it had."""

from __future__ import annotations

from an.audio.lipsync import NullLipSync, lipsync_cache_id
from an.audio.pipeline import viseme_key


class _Offline(NullLipSync):
    name = "offline"


def test_a_provider_without_a_version_keeps_the_keys_it_had():
    p = _Offline()
    assert lipsync_cache_id(p) == "offline"
    assert viseme_key("a1", lipsync_cache_id(p), "Hi") == viseme_key("a1", "offline", "Hi")


def test_a_version_re_keys_the_track_and_keeps_the_name():
    class Phones(_Offline):
        cache_version = "phones-1"

    before = viseme_key("a1", lipsync_cache_id(_Offline()), "Hi")
    after = viseme_key("a1", lipsync_cache_id(Phones()), "Hi")
    assert after != before and Phones().name == "offline"
