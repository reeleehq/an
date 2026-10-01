"""`an.verify.prosody`: the delivery estimators on signals whose answer is known."""

from __future__ import annotations

import json
import math
import shutil
import wave

import numpy as np
import pytest

from an.verify.prosody import (
    METRICS,
    median_stats,
    ProsodyStats,
    ProsodyTargetError,
    check_prosody,
    count_syllables,
    join_speech,
    main,
    measure_prosody,
    pitch_track,
    prosody_lint,
)

SR = 16000


def tone(hz, seconds, *, amp=0.3):
    t = np.arange(int(seconds * SR)) / SR
    hz = np.broadcast_to(np.asarray(hz, dtype=float), t.shape) if np.ndim(hz) else hz
    phase = 2 * np.pi * np.cumsum(np.full(t.shape, hz) / SR)
    return amp * np.sin(phase)


def silence(seconds):
    return np.zeros(int(seconds * SR))


@pytest.mark.parametrize("hz", [90, 150, 260])
def test_pitch_track_finds_a_steady_tone(hz):
    f0 = pitch_track(tone(hz, 0.5), SR)
    assert abs(np.nanmedian(f0) - hz) < 2


def test_a_glide_over_an_octave_measures_about_twelve_semitones():
    m = measure_prosody(tone(np.linspace(120, 240, int(SR * 1.0)), 1.0), SR)
    assert 10 <= m.f0_range_st <= 12.5
    assert m.f0_sd_st > 2.5


def test_a_steady_tone_has_no_pitch_movement():
    m = measure_prosody(tone(150, 1.0), SR)
    assert m.f0_sd_st < 0.1 and abs(m.final_drop_st) < 0.1


def test_a_falling_ending_is_a_negative_final_drop_and_a_rising_one_positive():
    fall = np.concatenate([tone(200, 0.75), tone(150, 0.25)])
    rise = np.concatenate([tone(150, 0.75), tone(200, 0.25)])
    assert measure_prosody(fall, SR).final_drop_st == pytest.approx(12 * math.log2(150 / 200), abs=0.5)
    assert measure_prosody(rise, SR).final_drop_st == pytest.approx(12 * math.log2(200 / 150), abs=0.5)


def test_pauses_are_measured_between_speech_never_at_the_edges():
    clip = np.concatenate(
        [silence(0.5), tone(150, 0.4), silence(0.3), tone(150, 0.4), silence(0.6), tone(150, 0.4), silence(0.5)]
    )
    m = measure_prosody(clip, SR, text="one two three")
    assert m.pauses == 2
    assert m.pause_median_s == pytest.approx(0.45, abs=0.03)
    assert m.span_s == pytest.approx(2.1, abs=0.05)
    assert m.pause_share == pytest.approx(0.9 / 2.1, abs=0.03)
    assert m.articulation_rate_sps == pytest.approx(3 / 1.2, abs=0.15)


def test_a_gap_shorter_than_the_minimum_is_not_a_pause():
    clip = np.concatenate([tone(150, 0.4), silence(0.06), tone(150, 0.4)])
    assert measure_prosody(clip, SR).pauses == 0


def test_loudness_range_and_emphasis_see_a_shouted_word():
    calm = np.concatenate([tone(150, 0.2, amp=0.05) for _ in range(6)])
    shout = np.concatenate([calm, tone(220, 0.5, amp=0.5), calm])
    flat = measure_prosody(np.concatenate([calm, calm]), SR)
    loud = measure_prosody(shout, SR)
    assert loud.loudness_range_db > flat.loudness_range_db + 5
    assert loud.emphasis_per_s > flat.emphasis_per_s


def test_silence_measures_as_nothing_rather_than_failing():
    m = measure_prosody(silence(1.0), SR, text="hello")
    assert m.speech_s == 0 and math.isnan(m.f0_sd_st) and m.syllables == 2


def test_rates_need_the_text():
    m = measure_prosody(tone(150, 1.0), SR)
    assert math.isnan(m.articulation_rate_sps) and m.syllables is None


def test_every_metric_is_a_stats_field():
    fields = set(ProsodyStats.__dataclass_fields__)
    assert set(METRICS) <= fields


@pytest.mark.parametrize(
    "text, n",
    [("Okay!", 2), ("He did not do the job.", 6), ("I was ON slide one.", 5), ("[sighs] Fine.", 1)],
)
def test_count_syllables(text, n):
    assert count_syllables(text) == n


def test_join_speech_drops_the_silence_around_each_clip():
    clip = np.concatenate([silence(0.3), tone(150, 0.5), silence(0.3)])
    joined = join_speech([clip, clip], SR)
    assert 0.95 <= len(joined) / SR <= 1.1
    assert measure_prosody(joined, SR).pauses == 0


def test_targets_are_checked_and_unknown_ones_refused():
    m = measure_prosody(np.concatenate([tone(150, 0.4), silence(0.4), tone(150, 0.4)]), SR)
    assert check_prosody(m, {"pause_share": [0.2, 0.5]}) == []
    miss = check_prosody(m, {"pause_share": [0.0, 0.1]})
    assert miss[0].severity == "warning" and miss[0].suggested_fix
    assert check_prosody(m, {"articulation_rate_sps": [3, 6]})[0].severity == "info"  # no text
    with pytest.raises(ProsodyTargetError):
        check_prosody(m, {"swagger": [0, 1]})
    with pytest.raises(ProsodyTargetError):
        check_prosody(m, {"pause_share": [0.5, 0.1]})


def test_prosody_lint_takes_measured_stats():
    m = measure_prosody(tone(150, 1.0), SR)
    stats, report = prosody_lint(m, {"f0_sd_st": [1.5, 4]})
    assert stats is m and report.passed and report.findings[0].severity == "warning"
    _, strict = prosody_lint(m, {"f0_sd_st": [1.5, 4]}, miss_severity="error")
    assert not strict.passed


def _write_wav(path, samples):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


@pytest.mark.ffmpeg
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg to decode")
def test_the_cli_measures_files_against_a_spec_role(tmp_path, capsys):
    wav = tmp_path / "line.wav"
    _write_wav(wav, np.concatenate([tone(150, 0.4), silence(0.4), tone(150, 0.4)]))
    spec = tmp_path / "spec.yaml"
    spec.write_text("prosody_targets:\n  narrator:\n    pauses_per_min: [30, 80]\n", encoding="utf-8")
    assert main([str(wav), "--targets", str(spec), "--role", "narrator", "--text", "one two"]) == 0
    out = capsys.readouterr().out
    assert "pauses_per_min" in out and "MISS" not in out.split("pauses_per_min")[1].splitlines()[0]
    with pytest.raises(ProsodyTargetError):
        main([str(wav), "--targets", str(spec), "--role", "villain"])


def test_register_is_measured_against_a_reference_pitch():
    m = measure_prosody(tone(200, 0.8), SR, reference_hz=100)
    assert m.register_st == pytest.approx(12, abs=0.2)
    assert math.isnan(measure_prosody(tone(200, 0.8), SR).register_st)


def test_a_set_of_lines_is_compared_by_its_median_not_by_joining():
    low, high = tone(120, 0.6), tone(240, 0.6)
    joined = measure_prosody(join_speech([low, high], SR), SR)
    each = median_stats([measure_prosody(low, SR), measure_prosody(high, SR)])
    assert joined.f0_sd_st > 5  # the octave between the lines reads as movement
    assert each.f0_sd_st < 0.5  # each line is steady


@pytest.mark.ffmpeg
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg to decode")
def test_the_cli_takes_the_median_of_several_lines(tmp_path, capsys):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    _write_wav(a, tone(120, 0.6))
    _write_wav(b, tone(240, 0.6))
    main([str(a), str(b), "--json"])
    lines = json.loads(capsys.readouterr().out)["stats"]["f0_sd_st"]
    main([str(a), str(b), "--joined", "--json"])
    joined = json.loads(capsys.readouterr().out)["stats"]["f0_sd_st"]
    assert lines < 0.5 < 5 < joined
