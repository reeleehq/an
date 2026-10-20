"""Recorded voices (an#490): a performer's takes become the voice of their lines.

- an import cuts a take at its transcript's times, stores each line with its
  provenance, and binds the speaker to a ``recorded`` voice document;
- the pipeline speaks those lines from the store, word timings included, and
  bills nothing; a line with no take is refused, never synthesized;
- a re-recorded line is new audio under a new key;
- a take matching no scene line is added only to a shot the author names;
- the credits walk lists the takes with their licence.

No test reaches a transcriber: the ones that need words are handed a fake.
"""

from __future__ import annotations

import io
import json
import math
import shutil
import struct
import wave

import pytest

from an.audio.lipsync import NullLipSync
from an.audio.pipeline import produce_audio_for_scene
from an.audio.recorded import (
    RECORDINGS_STORE,
    RecordedVoicesError,
    RecordingMissingError,
    find_recording,
    import_recordings,
)
from an.audio.transcripts import TranscriptSegment
from an.credits import collect_credits
from an.ir.schema import AssetRef, Dialogue, Meta, Resolution, SceneIR, Shot
from an.project import init, load

RATE = 16000
HELLO, FINE = "Hello there, Ned.", "Fine, thanks."
SRT = (
    "1\n00:00:00,500 --> 00:00:01,500\ncarl: Hello there, Ned.\n\n"
    "2\n00:00:02,500 --> 00:00:03,300\ncarl: Fine, thanks.\n"
)
LICENSE = "cc0-1.0"


def tone_wav(seconds: float, bursts, *, rate: int = RATE, hz: float = 220.0) -> bytes:
    """A 16-bit mono WAV: a tone during each ``(start, end)`` burst, silence elsewhere."""
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        on = any(a <= t < b for a, b in bursts)
        frames += struct.pack(
            "<h", int(12000 * math.sin(2 * math.pi * hz * t)) if on else 0
        )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def _scene(lines, *, character: bool) -> SceneIR:
    entities = (
        [AssetRef(kind="character", id="carl", store="characters", ref="carl")]
        if character
        else []
    )
    return SceneIR(
        meta=Meta(fps=24, resolution=Resolution(width=160, height=120)),
        timeline=[
            Shot(
                id="s1",
                renderer="cutout",
                duration=6.0,
                entities=entities,
                dialogue=[Dialogue(speaker="carl", text=t) for t in lines],
            )
        ],
    )


def _project(tmp_path, lines=(HELLO, FINE), *, character: bool = False):
    root = init(tmp_path / "p")
    proj = load(root)
    if character:
        proj.mall["characters"]["carl"] = {"name": "carl"}
    proj.mall["scenes"]["main"] = _scene(lines, character=character)
    return root


def _take(
    tmp_path, name="take.wav", seconds=4.0, bursts=((0.5, 1.5), (2.5, 3.3)), hz=220.0
):
    path = tmp_path / name
    path.write_bytes(tone_wav(seconds, bursts, hz=hz))
    return path


def _srt(tmp_path, text=SRT, name="take.srt"):
    path = tmp_path / name
    path.write_text(text)
    return path


def _records(root):
    store = load(root).mall[RECORDINGS_STORE]
    return {key: store[key] for key in store}


def test_a_timed_transcript_cuts_the_take_stores_it_and_binds_the_lines(tmp_path):
    root = _project(tmp_path)
    report = import_recordings(
        root,
        _take(tmp_path),
        transcript=_srt(tmp_path),
        license=LICENSE,
        recorded_by="J. Doe",
    )
    assert [t.line for t in report.takes] == ["s1/0", "s1/1"]
    assert not any(t.added for t in report.takes)
    records = _records(root)
    assert len(records) == 2
    by_text = {r["text"]: r for r in records.values()}
    assert set(by_text) == {HELLO, FINE}
    hello = by_text[HELLO]
    assert hello["voice"] == "carl_recorded" and hello["speaker"] == "carl"
    assert (
        hello["source"]["license"] == LICENSE and hello["source"]["author"] == "J. Doe"
    )
    # Cut 50 ms around the speech; the gap to the next line is its pause, not audio.
    assert hello["source"]["extra"]["span"] == pytest.approx([0.45, 1.55])
    assert hello["duration"] == pytest.approx(1.10, abs=0.01)
    assert hello["words"] is None  # an SRT times lines, not words
    proj = load(root)
    voices = proj.mall["voices"]
    assert voices["carl_recorded"]["provider"] == "recorded"
    assert voices["carl_recorded"]["recorded_by"] == "J. Doe"
    lines = proj.scene.timeline[0].dialogue
    # No character entity: the binding is per line, and the report says what that means.
    assert [d.voice_ref for d in lines] == ["carl_recorded", "carl_recorded"]
    assert any("no character entity" in v for v in report.voices)
    # The silence heard between the two lines is the second line's pause.
    assert lines[0].pause is None
    assert lines[1].pause == pytest.approx(1.0)
    assert report.takes[1].pause == pytest.approx(1.0)
    # scene.md says so too (the store's merge writes the dialogue block).
    assert "(pause 1" in (root / "scene.md").read_text()


@pytest.mark.genre("cutout_animation")
def test_a_speaker_with_a_character_is_bound_by_its_descriptor(tmp_path):
    root = _project(tmp_path, character=True)
    proj = load(root)
    proj.mall["characters"]["carl"] = {"name": "carl", "voice_ref": "carl_eleven"}
    proj.mall["voices"]["carl_eleven"] = {"provider": "elevenlabs", "voice_id": "abc"}
    report = import_recordings(
        root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE
    )
    proj = load(root)
    assert proj.mall["characters"]["carl"]["voice_ref"] == "carl_recorded"
    assert proj.mall["voices"]["carl_recorded"]["replaces"] == "carl_eleven"
    assert all(d.voice_ref is None for d in proj.scene.timeline[0].dialogue)
    assert any("replaces 'carl_eleven'" in v for v in report.voices)


def test_the_pipeline_speaks_the_takes_from_the_store(tmp_path):
    root = _project(tmp_path)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    store = proj.mall[RECORDINGS_STORE]
    first, second = scene.timeline[0].dialogue
    for line in (first, second):
        key, record = find_recording(store, "carl_recorded", line.text)
        assert proj.mall["audio"][line.audio_ref] == store.read_audio(key)
        assert line.duration == pytest.approx(record["duration"])
    # The second line follows the first line's speech by the recorded pause.
    heard = first.spoken if first.spoken is not None else first.duration
    assert second.start == pytest.approx(first.start + heard + 1.0, abs=0.02)
    # Idempotent: a second pass re-reads everything and changes no key.
    refs = [d.audio_ref for d in scene.timeline[0].dialogue]
    produce_audio_for_scene(scene, proj.mall, lipsync=NullLipSync(), announce=None)
    assert [d.audio_ref for d in scene.timeline[0].dialogue] == refs


def test_the_words_of_a_word_json_reach_the_line(tmp_path):
    root = _project(tmp_path)
    transcript = tmp_path / "take.json"
    transcript.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "speaker": "carl",
                        "text": HELLO,
                        "words": [
                            ["Hello", 0.5, 0.8],
                            ["there", 0.8, 1.1],
                            ["Ned", 1.1, 1.5],
                        ],
                    },
                    {
                        "speaker": "carl",
                        "text": FINE,
                        "words": [["Fine", 2.5, 2.9], ["thanks", 2.9, 3.3]],
                    },
                ]
            }
        )
    )
    report = import_recordings(
        root, _take(tmp_path), transcript=transcript, license=LICENSE
    )
    assert [t.words for t in report.takes] == [3, 2]
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    first = scene.timeline[0].dialogue[0]
    assert [w.text for w in first.word_timings] == ["Hello", "there", "Ned"]
    assert first.word_timings[0].start == pytest.approx(
        0.05
    )  # clip-relative: cut at 0.45
    assert first.word_timings[-1].end == pytest.approx(1.05)
    assert first.word_timings[-1].end <= first.duration + 1e-6
    # Read back from the audio store (no synthesis), the words are still known.
    proj = load(root)
    for key in list(proj.mall["visemes"]):
        del proj.mall["visemes"][key]
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    assert [w.text for w in scene.timeline[0].dialogue[0].word_timings] == [
        "Hello",
        "there",
        "Ned",
    ]


def test_a_line_with_no_take_is_refused_not_synthesized(tmp_path):
    root = _project(tmp_path)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    proj = load(root)
    proj.scene.timeline[0].dialogue.append(
        Dialogue(speaker="carl", text="Bye now.", voice_ref="carl_recorded")
    )
    with pytest.raises(RecordingMissingError, match="no take of 'Bye now.'"):
        produce_audio_for_scene(
            proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
        )
    assert not list(proj.mall["audio"])  # nothing was made before the refusal


def test_a_rerecorded_line_is_new_audio_under_a_new_key(tmp_path):
    root = _project(tmp_path)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    before = scene.timeline[0].dialogue[0].audio_ref
    proj.mall["scenes"]["main"] = scene
    # The performer records the same lines again, differently.
    retake = _take(tmp_path, name="take2.wav", hz=330.0)
    report = import_recordings(root, retake, transcript=_srt(tmp_path), license=LICENSE)
    assert len(_records(root)) == 4  # the old takes are kept, never deleted
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    after = scene.timeline[0].dialogue[0].audio_ref
    assert after != before
    key = next(t.key for t in report.takes if t.text == HELLO)
    assert proj.mall["audio"][after] == proj.mall[RECORDINGS_STORE].read_audio(key)


def test_a_take_matching_no_line_goes_only_to_a_named_shot(tmp_path):
    root = _project(tmp_path)
    srt = _srt(tmp_path, SRT + "\n3\n00:00:03,500 --> 00:00:03,900\ncarl: Bye now.\n")
    take = _take(tmp_path, bursts=((0.5, 1.5), (2.5, 3.3), (3.5, 3.9)))
    with pytest.raises(RecordedVoicesError, match="--shot"):
        import_recordings(root, take, transcript=srt, license=LICENSE)
    assert not _records(root)  # a refusal writes nothing
    report = import_recordings(root, take, transcript=srt, license=LICENSE, shot="s1")
    added = [t for t in report.takes if t.added]
    assert [(t.line, t.speaker, t.text) for t in added] == [
        ("s1/2", "carl", "Bye now.")
    ]
    lines = load(root).scene.timeline[0].dialogue
    assert [d.text for d in lines] == [HELLO, FINE, "Bye now."]
    assert lines[2].pause == pytest.approx(0.2)


def test_a_wrong_shot_or_a_bad_licence_is_refused_before_anything_is_written(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(RecordedVoicesError, match="licence"):
        import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path))
    with pytest.raises(RecordedVoicesError, match="no shot 'nope'"):
        import_recordings(
            root,
            _take(tmp_path),
            transcript=_srt(tmp_path, SRT.replace("Fine, thanks.", "Something else.")),
            license=LICENSE,
            shot="nope",
        )
    assert not _records(root)


def test_a_plain_transcript_is_timed_by_the_transcriber(tmp_path):
    root = _project(tmp_path)
    plain = tmp_path / "take.txt"
    plain.write_text(f"carl: {HELLO}\ncarl: {FINE}\n")
    heard = [
        TranscriptSegment(
            text="hello there ned fine thanks",
            start=0.5,
            end=3.3,
            words=(
                ("hello", 0.5, 0.8),
                ("there", 0.8, 1.1),
                ("ned", 1.1, 1.5),
                ("fine", 2.5, 2.9),
                ("thanks", 2.9, 3.3),
            ),
        )
    ]
    asked: list = []

    def fake_transcribe(path):
        asked.append(path.name)
        return heard

    report = import_recordings(
        root,
        _take(tmp_path),
        transcript=plain,
        license=LICENSE,
        transcribe=fake_transcribe,
    )
    assert asked == ["take.wav"]
    assert [(t.line, t.words) for t in report.takes] == [("s1/0", 3), ("s1/1", 2)]
    assert report.takes[0].span == pytest.approx((0.45, 1.55))
    assert report.takes[1].pause == pytest.approx(1.0)


def test_no_transcript_means_the_transcriber_segments_are_the_lines(tmp_path):
    root = _project(tmp_path)
    heard = [
        TranscriptSegment(text="Hello there Ned", start=0.5, end=1.5, speaker="spk_0"),
        TranscriptSegment(text="Fine thanks", start=2.5, end=3.3, speaker="spk_0"),
    ]
    report = import_recordings(
        root,
        _take(tmp_path),
        license=LICENSE,
        transcribe=lambda p: heard,
        speakers="spk_0=carl",
    )
    assert [(t.line, t.speaker, t.text) for t in report.takes] == [
        ("s1/0", "carl", HELLO),  # bound to the scene's line: its text is the scene's
        ("s1/1", "carl", FINE),
    ]


def test_a_take_that_needs_transcribing_says_how_when_scribed_is_absent(
    tmp_path, monkeypatch
):
    import builtins

    real_import = builtins.__import__

    def no_scribed(name, *args, **kwargs):
        if name == "scribed":
            raise ImportError("no scribed here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_scribed)
    root = _project(tmp_path)
    with pytest.raises(RecordedVoicesError, match=r"an\[recorded\]"):
        import_recordings(root, _take(tmp_path), license=LICENSE)


def test_one_file_per_line_is_paired_in_order_and_named_by_its_stem(tmp_path):
    root = _project(tmp_path)
    first = _take(tmp_path, name="carl-01.wav", seconds=1.0, bursts=((0.1, 0.9),))
    second = _take(tmp_path, name="carl-02.wav", seconds=0.8, bursts=((0.1, 0.7),))
    plain = tmp_path / "lines.txt"
    plain.write_text(f"{HELLO}\n{FINE}\n")  # no speaker prefixes: the stems say who
    report = import_recordings(root, [first, second], transcript=plain, license=LICENSE)
    assert [(t.line, t.speaker, t.source_file, t.span) for t in report.takes] == [
        ("s1/0", "carl", "carl-01.wav", (0.0, 1.0)),
        ("s1/1", "carl", "carl-02.wav", (0.0, 0.8)),
    ]
    assert report.takes[1].pause is None  # two files: no gap was heard between them


def test_a_directory_of_takes_pairs_transcripts_by_stem(tmp_path):
    root = _project(tmp_path)
    takes = tmp_path / "takes"
    takes.mkdir()
    _take(takes, name="a.wav", seconds=1.0, bursts=((0.1, 0.9),))
    _take(takes, name="b.wav", seconds=0.8, bursts=((0.1, 0.7),))
    (takes / "a.srt").write_text(f"1\n00:00:00,100 --> 00:00:00,900\ncarl: {HELLO}\n")
    (takes / "b.srt").write_text(f"1\n00:00:00,100 --> 00:00:00,700\ncarl: {FINE}\n")
    report = import_recordings(root, takes, transcript=takes, license=LICENSE)
    assert [(t.line, t.source_file) for t in report.takes] == [
        ("s1/0", "a.wav"),
        ("s1/1", "b.wav"),
    ]


def test_the_credits_walk_lists_the_takes_with_their_licence(tmp_path):
    root = _project(tmp_path)
    import_recordings(
        root,
        _take(tmp_path),
        transcript=_srt(tmp_path),
        license="cc-by-4.0",
        recorded_by="J. Doe",
    )
    report = collect_credits(load(root).mall)
    entries = {
        e.asset: e.source for e in report.entries if e.asset.startswith("recordings/")
    }
    assert len(entries) == 2
    assert all(
        s.license == "cc-by-4.0" and s.author == "J. Doe" for s in entries.values()
    )


def test_a_dry_run_writes_nothing(tmp_path):
    root = _project(tmp_path)
    report = import_recordings(
        root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE, write=False
    )
    assert len(report.takes) == 2
    proj = load(root)
    assert (
        not list(proj.mall[RECORDINGS_STORE])
        and "carl_recorded" not in proj.mall["voices"]
    )
    assert all(
        d.voice_ref is None and d.pause is None for d in proj.scene.timeline[0].dialogue
    )


def test_other_lines_of_the_speaker_without_a_take_are_warned_about(tmp_path):
    root = _project(tmp_path, lines=(HELLO, FINE, "Bye now."))
    report = import_recordings(
        root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE
    )
    assert any("1 other line(s) of 'carl' have no take" in w for w in report.warnings)


@pytest.mark.ffmpeg
def test_denoising_runs_the_take_through_ffmpeg(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    root = _project(tmp_path)
    import_recordings(
        root,
        _take(tmp_path),
        transcript=_srt(tmp_path),
        license=LICENSE,
        denoise="afftdn",
    )
    records = list(_records(root).values())
    assert all(r["source"]["extra"]["denoise"] == "afftdn" for r in records)
    assert all(r["sample_rate"] == 44100 for r in records)  # decoded to the film's rate
    with pytest.raises(RecordedVoicesError, match="unknown denoise"):
        import_recordings(
            root,
            _take(tmp_path),
            transcript=_srt(tmp_path),
            license=LICENSE,
            denoise="magic",
        )
