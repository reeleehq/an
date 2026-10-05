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


# -----------------------------------------------------------------------------
# A WAV written to a pipe (an#330): its header says "as long as there is"
# -----------------------------------------------------------------------------

#: The size a streaming writer (``ffmpeg ... -f wav -``) puts in the RIFF and
#: data headers, because it cannot seek back to write the real one.
STREAMING = 0xFFFFFFFF


def _streaming(wav: bytes, *, riff: int = STREAMING, data: int = STREAMING) -> bytes:
    """``wav`` re-headed the way a pipe writer leaves it."""
    import struct

    i = wav.index(b"data")
    return (
        wav[:4] + struct.pack("<I", riff) + wav[8:i + 4] + struct.pack("<I", data)
        + wav[i + 8:]
    )  # fmt: skip


def test_a_streaming_header_wav_records_its_true_duration(tmp_path):
    """an#330: the header's 0xFFFFFFFF is not a length; the bytes are."""
    true = synth_tone(440.0, 1.5, sample_rate=48000)
    piped = _streaming(true)
    assert wav_info(piped) == wav_info(true) == (48000, 1, 72000)
    store = SoundsStore(tmp_path)
    asset = add_sound(store, "theme", piped, source=SYNTH_SOURCE)
    assert asset.duration == pytest.approx(1.5)
    stored = get_sound(store, "theme")[1]
    import io
    import wave

    with wave.open(io.BytesIO(stored)) as w:  # stored well-formed, digest of THOSE bytes
        assert w.getnframes() == 72000
    assert asset.sha256 == hashlib.sha256(stored).hexdigest()


def test_a_data_size_past_the_end_or_a_ragged_tail_is_cut_to_whole_frames():
    true = synth_tone(440.0, 0.25, sample_rate=8000)  # 2000 frames of 2 bytes
    assert wav_info(_streaming(true, riff=len(true) - 8, data=10**8))[2] == 2000
    assert wav_info(_streaming(true)[:-1])[2] == 1999  # half a frame is no frame
    assert wav_info(true + b"LIST\x04\x00\x00\x00abcd")[2] == 2000  # a chunk after data


@pytest.mark.ffmpeg
def test_a_wav_cut_by_ffmpeg_to_a_pipe_round_trips(tmp_path):
    import subprocess

    piped = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=2.5",
         "-ar", "48000", "-ac", "2", "-f", "wav", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    asset = add_sound(SoundsStore(tmp_path), "cut", piped, source=SYNTH_SOURCE)
    assert asset.duration == pytest.approx(2.5, abs=1e-3)
    assert asset.channels == 2


def test_validate_flags_a_recorded_duration_its_audio_disagrees_with(tmp_path):
    """Stores filled before an#330 carry ~22369 s: say so, and mix the truth."""
    from an.ir.schema import Meta, SceneIR, Shot, SoundCue
    from an.ir.validate import validate_semantic

    mall = build_project_mall(tmp_path, ensure=True)
    add_sound(mall["sounds"], "theme", synth_tone(440.0, 1.0), source=SYNTH_SOURCE)
    record = dict(mall["sounds"]["theme"])
    record["duration"] = 22369.6213125  # what the streaming header made of it
    mall["sounds"]["theme"] = record
    scene = SceneIR(
        meta=Meta(title="t", sounds=[SoundCue(sound="theme", at=0.0)]),
        timeline=[Shot(id="a", duration=2.0)],
    )
    report = validate_semantic(scene, available_sounds=mall["sounds"])
    (f,) = [f for f in report.findings if "22369" in f.description]
    assert f.severity == "warning" and f.ir_path == "meta/sounds/0/sound"
    assert "add_sound" in f.description


def test_the_mix_plays_a_sound_for_its_audios_length_not_its_records(tmp_path):
    """A store filled before an#330 still mixes right: the bytes decide."""
    from an.assemble import film_timeline, mix_plan
    from an.ir.schema import Meta, SceneIR, Shot, SoundCue

    mall = build_project_mall(tmp_path, ensure=True)
    add_sound(mall["sounds"], "theme", synth_tone(440.0, 1.0), source=SYNTH_SOURCE)
    record = dict(mall["sounds"]["theme"])
    record["duration"] = 22369.6213125
    mall["sounds"]["theme"] = record
    scene = SceneIR(
        meta=Meta(title="t", sounds=[SoundCue(sound="theme", at=0.0)]),
        timeline=[Shot(id="a", duration=5.0)],
    )
    plan = mix_plan(scene, film_timeline(scene.timeline, fps=24), mall, tmp_path / "mix")
    (placement,) = plan.placements
    assert placement.play == pytest.approx(1.0)
