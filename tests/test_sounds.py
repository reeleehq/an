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


def _wav(frames: bytes, *, width: int = 2, channels: int = 1, rate: int = 8000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def test_a_healthy_wav_is_stored_as_supplied(tmp_path):
    """an#330 review: only a header that overstates or omits its length is
    patched. A trailing chunk or an odd file's pad byte is a healthy WAV, and
    its digest must stay the digest of the file the user has."""
    tone = synth_tone(440.0, 0.25, sample_rate=8000)
    with_list = bytearray(tone + b"LIST\x04\x00\x00\x00abcd")
    with_list[4:8] = (len(with_list) - 8).to_bytes(4, "little")
    odd_u8 = bytearray(_wav(b"\x80" * 2001, width=1) + b"\0")  # 2001 one-byte frames + pad
    odd_u8[4:8] = (len(odd_u8) - 8).to_bytes(4, "little")
    odd_u8 = bytes(odd_u8)
    store = SoundsStore(tmp_path)
    for key, data in (("list", bytes(with_list)), ("odd", odd_u8)):
        asset = add_sound(store, key, data, source=SYNTH_SOURCE)
        assert asset.sha256 == hashlib.sha256(data).hexdigest(), key
    assert store["odd"]["duration"] == pytest.approx(2001 / 8000)


def test_a_zero_data_size_with_audio_after_it_reads_as_unknown_and_empty_is_refused(tmp_path):
    tone = synth_tone(440.0, 0.5, sample_rate=8000)
    assert wav_info(_streaming(tone, data=0))[2] == 4000  # some writers put 0, not ~0
    with pytest.raises(SoundError, match="no audio"):
        add_sound(SoundsStore(tmp_path), "empty", _wav(b""), source=SYNTH_SOURCE)


@pytest.mark.ffmpeg
@pytest.mark.parametrize(
    "args", [["-af", "aformat=channel_layouts=quad"], ["-c:a", "pcm_s24le", "-ac", "2"]]
)
def test_an_extensible_wav_cut_to_a_pipe_keeps_its_format(tmp_path, args):
    """ffmpeg writes WAVE_FORMAT_EXTENSIBLE for >2 channels or >16 bits; the
    re-header patches sizes only, so the channel mask (quad, not 4.0) survives,
    and it is read without `wave` (which refuses it before Python 3.12)."""
    import struct
    import subprocess

    piped = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=0.5", "-ar", "48000",
         *args, "-f", "wav", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    asset = add_sound(SoundsStore(tmp_path), "x", piped, source=SYNTH_SOURCE)
    stored = get_sound(SoundsStore(tmp_path), "x")[1]
    assert asset.duration == pytest.approx(0.5, abs=1e-3)
    fmt_at = stored.index(b"fmt ")
    assert stored[fmt_at:stored.index(b"data")] == piped[fmt_at:piped.index(b"data")]
    assert struct.unpack("<H", stored[fmt_at + 8:fmt_at + 10])[0] == 0xFFFE

    def layout(wav: bytes) -> str:
        return subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=channel_layout",
             "-of", "csv=p=0", "-"],
            input=wav, capture_output=True, check=True,
        ).stdout.decode().strip()  # fmt: skip

    assert layout(stored) == layout(piped)
    if "quad" in str(args):
        assert layout(stored) == "quad"  # not 4.0: the channel mask survived


def test_the_advice_for_a_library_sound_is_to_fix_the_library(tmp_path):
    from an.ir.schema import Meta, SceneIR, Shot, SoundCue
    from an.ir.validate import validate_semantic

    mall = build_project_mall(tmp_path, ensure=True)
    add_sound(mall["sounds"], "theme", synth_tone(440.0, 1.0), source=SYNTH_SOURCE)
    record = dict(mall["sounds"]["theme"])
    record["duration"] = 22369.6213125
    record["metadata"] = {"library_origin": {"ref": "lib/theme@1"}}
    mall["sounds"]["theme"] = record
    scene = SceneIR(
        meta=Meta(title="t", sounds=[SoundCue(sound="theme", at=0.0), SoundCue(sound="theme", at=1.0)]),
        timeline=[Shot(id="a", duration=2.0)],
    )
    found = [f for f in validate_semantic(scene, available_sounds=mall["sounds"]).findings if "22369" in f.description]
    assert len(found) == 2 and all("publish a corrected version" in f.description for f in found)


def test_the_mix_keeps_the_record_for_a_file_it_cannot_measure(tmp_path):
    """A non-WAV placed by hand (with its digest) mixed before an#330 from its
    record; measuring must not turn that into a render error."""
    from an.assemble import film_timeline, mix_plan
    from an.ir.schema import Meta, SceneIR, Shot, SoundCue

    mall = build_project_mall(tmp_path, ensure=True)
    add_sound(mall["sounds"], "theme", synth_tone(440.0, 1.0), source=SYNTH_SOURCE)
    mp3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb" * 64
    record = dict(mall["sounds"]["theme"], sha256=hashlib.sha256(mp3).hexdigest(), duration=0.75)
    mall["sounds"]["theme"] = record
    mall["sounds"].write_audio("theme", mp3)
    scene = SceneIR(
        meta=Meta(title="t", sounds=[SoundCue(sound="theme", at=0.0)]),
        timeline=[Shot(id="a", duration=5.0)],
    )
    plan = mix_plan(scene, film_timeline(scene.timeline, fps=24), mall, tmp_path / "mix")
    assert plan.placements[0].play == pytest.approx(0.75)


# ---------------------------------------------------------------- an#332


def test_a_sound_whose_terms_forbid_keeping_its_bytes_is_refused(tmp_path):
    from an.ir.assets import AssetSource

    store = SoundsStore(tmp_path)
    freesound = {"provider": "freesound", "license": "cc0-1.0", "cacheable": False}
    with pytest.raises(SoundError, match="cacheable=False"):
        add_sound(store, "rain", synth_hit(seed=3), source=freesound)
    assert "rain" not in store
    # Not recorded is not a yes, and not a no: the default is None.
    assert AssetSource(provider="p").cacheable is None
    add_sound(store, "rain", synth_hit(seed=3), source={**freesound, "cacheable": None})


def test_versioned_cc_codes_and_stable_audio_are_classified():
    from an.ir.assets import AssetSource, license_class, provider_terms_restriction

    for code in ("cc-by-3.0", "cc-by-sa-4.0", "CC-BY-4.0"):
        assert license_class(AssetSource(provider="freesound", license=code)) == "attribution"
    # an#373: the NC family is one non-commercial class, versioned or not.
    for code in ("cc-by-nc-4.0", "cc-by-nc-3.0", "CC-BY-NC-4.0", "cc-by-nc-sa-4.0",
                 "cc-by-nc-nd-4.0", "by-nc"):
        assert license_class(AssetSource(provider="freesound", license=code)) == "noncommercial"
    stable = AssetSource(provider="stability", license="stability-community")
    assert license_class(stable) == "free"
    assert "1,000,000" in provider_terms_restriction(stable)
    # Another provider's output is not Stability's to license.
    assert license_class(AssetSource(provider="elevenlabs", license="stability-community")) == "unknown"


def test_credits_name_stable_audios_revenue_cap(tmp_path):
    mall = build_project_mall(tmp_path, ensure=True)
    add_sound(mall["sounds"], "drone", synth_hit(seed=4),
              source={"provider": "stability", "license": "stability-community"})
    text = collect_credits(mall).format()
    assert "1,000,000" in text
