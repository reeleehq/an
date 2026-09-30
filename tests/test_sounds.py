"""The `sounds` store and its front door (`an.sounds`, an#163): provenance per
asset, the digest the licence is attached to, credits, and synthesis that is a
pure function of its arguments."""

from __future__ import annotations

import hashlib

import pytest

from an.credits import collect_credits
from an.sounds import (
    SYNTH_SOURCE,
    SoundError,
    add_sound,
    get_sound,
    synth_bed,
    synth_hit,
    synth_tone,
    wav_info,
)
from an.stores import build_project_mall
from an.stores.sounds import SoundsStore


def test_the_mall_has_a_sounds_store(tmp_path):
    mall = build_project_mall(tmp_path, ensure=True)
    assert isinstance(mall["sounds"], SoundsStore)
    assert (tmp_path / "assets" / "sounds").is_dir()


def test_add_records_provenance_and_the_digest(tmp_path):
    store = SoundsStore(tmp_path)
    data = synth_hit(seed=7)
    asset = add_sound(store, "hit", data, source=SYNTH_SOURCE, description="a thump")
    assert asset.sha256 == hashlib.sha256(data).hexdigest()
    assert store["hit"]["source"]["license"] == "cc0-1.0"
    assert get_sound(store, "hit") == (asset, data)


def test_bytes_that_are_not_the_recorded_ones_are_refused(tmp_path):
    store = SoundsStore(tmp_path)
    add_sound(store, "hit", synth_hit(seed=1), source=SYNTH_SOURCE)
    store.write_audio("hit", synth_hit(seed=2))  # swapped behind its record
    with pytest.raises(SoundError, match="digest"):
        get_sound(store, "hit")


def test_only_wav_is_accepted_and_the_refusal_says_how_to_convert(tmp_path):
    with pytest.raises(SoundError, match="ffmpeg -i"):
        add_sound(SoundsStore(tmp_path), "x", b"ID3 not a wav", source=SYNTH_SOURCE)


def test_a_missing_key_names_the_way_to_add_one(tmp_path):
    with pytest.raises(KeyError, match="add_sound"):
        get_sound(SoundsStore(tmp_path), "nope")


def test_credits_walk_the_sounds_store_and_keep_unknown_apart(tmp_path):
    mall = build_project_mall(tmp_path, ensure=True)
    add_sound(mall["sounds"], "made", synth_tone(440.0, 0.1), source=SYNTH_SOURCE)
    add_sound(
        mall["sounds"], "found", synth_tone(220.0, 0.1),
        source={"provider": "freesound", "id": "123"},  # no licence recorded
    )
    add_sound(
        mall["sounds"], "cc", synth_tone(330.0, 0.1),
        source={"provider": "freesound", "license": "cc-by-4.0",
                "attribution": "Hit by Someone (CC BY 4.0)"},
    )
    report = collect_credits(mall)
    assert {e.asset for e in report.unverified} == {"sounds/found"}
    assert {e.asset for e in report.owed} == {"sounds/cc"}
    assert "sounds/made" in report.format()


def test_synthesis_is_deterministic_and_well_formed():
    for make in (lambda: synth_tone(440.0, 0.2), lambda: synth_hit(seed=4),
                 lambda: synth_bed(1.0)):
        a, b = make(), make()
        assert a == b and a[:4] == b"RIFF"
    assert wav_info(synth_bed(2.0)) == (44100, 1, 88200)
