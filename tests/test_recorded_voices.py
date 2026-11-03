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
from pathlib import Path

import pytest

from an.audio.lipsync import NullLipSync
from an.audio.pipeline import (
    in_memory_audio_mall,
    produce_audio_for_scene,
    stamp_from_stores,
)
from an.audio.recorded import (
    RECORDINGS_STORE,
    RecordedVoicesError,
    RecordedVoicesWarning,
    RecordingMissingError,
    TranscriberUnavailableError,
    find_recording,
    import_recordings,
)
from an.audio.transcripts import TranscriptSegment
from an.credits import collect_credits, credits_for_scene
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
    path.write_text(text, encoding="utf-8")
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
    # The silence heard between the two lines is the second line's pause: the
    # 1.0 s gap less the 50 ms pad the second cut keeps before its speech.
    assert lines[0].pause is None
    assert lines[1].pause == pytest.approx(0.95)
    assert report.takes[1].pause == pytest.approx(0.95)
    # scene.md says so too (the store's merge writes the dialogue block).
    assert "(pause 0.95" in (root / "scene.md").read_text(encoding="utf-8")


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
    # The second line follows the first line's speech by the recorded pause, so
    # its speech (50 ms into its clip) starts 1.0 s after the first's ends.
    heard = first.spoken if first.spoken is not None else first.duration
    assert second.start == pytest.approx(first.start + heard + 0.95, abs=0.02)
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
        ),
        encoding="utf-8",
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
    assert lines[2].pause == pytest.approx(0.15)


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
    plain.write_text(f"carl: {HELLO}\ncarl: {FINE}\n", encoding="utf-8")
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
    assert report.takes[1].pause == pytest.approx(0.95)


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
    plain.write_text(
        f"{HELLO}\n{FINE}\n", encoding="utf-8"
    )  # no prefixes: the stems say who
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
    (takes / "a.srt").write_text(
        f"1\n00:00:00,100 --> 00:00:00,900\ncarl: {HELLO}\n", encoding="utf-8"
    )
    (takes / "b.srt").write_text(
        f"1\n00:00:00,100 --> 00:00:00,700\ncarl: {FINE}\n", encoding="utf-8"
    )
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


# --- the review's findings, pinned ---------------------------------------------


def test_the_cache_key_reader_restamps_a_recorded_scene_in_memory(tmp_path):
    """`an cache gc` reads a render's keys through `stamp_from_stores`, whose
    providers must reach the recordings store too (review finding 1)."""
    root = _project(tmp_path)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    refs = [d.audio_ref for d in scene.timeline[0].dialogue]
    fresh = load(root).scene  # unstamped: the render's stamps were not saved
    assert all(d.audio_ref is None for d in fresh.timeline[0].dialogue)
    stamped = stamp_from_stores(
        fresh,
        in_memory_audio_mall(proj.mall),
        lipsync=NullLipSync(),
        free_in_memory=True,
    )
    assert [d.audio_ref for d in stamped.timeline[0].dialogue] == refs


def test_overlapping_cues_are_refused_before_anything_is_written(tmp_path):
    root = _project(tmp_path)
    nested = (
        "1\n00:00:01,000 --> 00:00:05,000\ncarl: Hello there, Ned.\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\ncarl: Fine, thanks.\n"
    )
    with pytest.raises(RecordedVoicesError, match="leaves no audio to cut"):
        import_recordings(
            root,
            _take(tmp_path, seconds=6.0),
            transcript=_srt(tmp_path, nested),
            license=LICENSE,
        )
    proj = load(root)
    assert not _records(root)
    assert "carl_recorded" not in proj.mall["voices"]
    assert all(d.voice_ref is None for d in proj.scene.timeline[0].dialogue)


def test_a_renders_credits_name_the_take_and_its_permission(tmp_path):
    root = _project(tmp_path)
    import_recordings(
        root,
        _take(tmp_path),
        transcript=_srt(tmp_path),
        license="all-rights-reserved",
        recorded_by="J. Doe",
    )
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    report = credits_for_scene(proj.mall, scene)
    takes = [e for e in report.entries if e.asset.startswith("recordings/")]
    assert len(takes) == 2
    assert all(
        e.source.author == "J. Doe" and e.source.license == "all-rights-reserved"
        for e in takes
    )
    assert not any(
        e.asset == "speech/carl_recorded" for e in report.entries
    )  # not synthesized
    assert report.publishable is False  # a private take makes the film private


@pytest.mark.genre("cutout_animation")
def test_an_entity_without_a_descriptor_binds_per_line_and_says_so(tmp_path):
    root = _project(tmp_path, character=True)
    proj = load(root)
    del proj.mall["characters"][
        "carl"
    ]  # the entity stays in the shot, its descriptor is gone
    report = import_recordings(
        root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE
    )
    assert any("has no descriptor" in v for v in report.voices)
    lines = load(root).scene.timeline[0].dialogue
    assert [d.voice_ref for d in lines] == ["carl_recorded", "carl_recorded"]


def test_a_nameless_take_that_fits_two_speakers_is_refused(tmp_path):
    root = init(tmp_path / "p")
    proj = load(root)
    scene = _scene((), character=False)
    scene.timeline[0].dialogue = [
        Dialogue(speaker="carl", text="Yeah."),
        Dialogue(speaker="ned", text="Yeah."),
    ]
    proj.mall["scenes"]["main"] = scene
    srt = _srt(
        tmp_path,
        "1\n00:00:00,500 --> 00:00:01,500\nYeah.\n\n2\n00:00:02,500 --> 00:00:03,300\nYeah.\n",
    )
    with pytest.raises(RecordedVoicesError, match="equally well"):
        import_recordings(root, _take(tmp_path), transcript=srt, license=LICENSE)
    assert not _records(root)
    # Named, the first take is carl's line; the second has no free carl line and
    # is added to the shot — and the repeated text is said to play one take.
    report = import_recordings(
        root,
        _take(tmp_path),
        transcript=srt,
        license=LICENSE,
        speaker="carl",
        shot="s1",
    )
    assert [(t.speaker, t.added) for t in report.takes] == [
        ("carl", False),
        ("carl", True),
    ]
    assert any("more than once" in w for w in report.warnings)


def test_validate_reports_a_line_with_no_take(tmp_path):
    from an.orchestrate import validate_project

    root = _project(tmp_path)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    assert not [f for f in validate_project(root).findings if f.severity == "error"]
    proj = load(root)
    proj.scene.timeline[0].dialogue.append(
        Dialogue(speaker="carl", text="Bye now.", voice_ref="carl_recorded")
    )
    proj.mall["scenes"]["main"] = proj.scene
    errors = [f for f in validate_project(root).findings if f.severity == "error"]
    assert len(errors) == 1 and "no take of 'Bye now.'" in errors[0].description


def test_the_same_bytes_under_two_texts_keep_their_own_words(tmp_path):
    root = _project(tmp_path, lines=(HELLO, "Hello there, Fred."))
    words = lambda name: [
        [name.split()[0], 0.5, 0.8],
        ["there", 0.8, 1.1],
        [name.split()[-1].rstrip("."), 1.1, 1.5],
    ]  # noqa: E731
    for text in (HELLO, "Hello there, Fred."):
        transcript = tmp_path / f"{text[-5:-1]}.json"
        transcript.write_text(
            json.dumps(
                {"segments": [{"speaker": "carl", "text": text, "words": words(text)}]}
            ),
            encoding="utf-8",
        )
        import_recordings(
            root,
            _take(tmp_path, seconds=2.0, bursts=((0.5, 1.5),)),
            transcript=transcript,
            license=LICENSE,
        )
    proj = load(root)
    scene = produce_audio_for_scene(
        proj.scene, proj.mall, lipsync=NullLipSync(), announce=None
    )
    first, second = scene.timeline[0].dialogue
    assert [w.text for w in first.word_timings] == ["Hello", "there", "Ned"]
    assert [w.text for w in second.word_timings] == ["Hello", "there", "Fred"]


def test_a_bad_transcript_is_a_refusal_naming_the_file(tmp_path):
    root = _project(tmp_path)
    bad = _srt(
        tmp_path,
        "1\n00:00:xx,500 --> 00:00:01,500\ncarl: Hello there, Ned.\n",
        name="bad.srt",
    )
    with pytest.raises(RecordedVoicesError, match=r"bad\.srt: not a timestamp"):
        import_recordings(root, _take(tmp_path), transcript=bad, license=LICENSE)
    takes = tmp_path / "takes"
    takes.mkdir()
    _take(takes, name="a.wav", seconds=1.0, bursts=((0.1, 0.9),))
    (takes / "other.srt").write_text(
        "1\n00:00:00,100 --> 00:00:00,900\ncarl: Hi.\n", encoding="utf-8"
    )
    with pytest.raises(RecordedVoicesError, match="pairs by stem with a.wav"):
        import_recordings(root, takes, transcript=takes, license=LICENSE)


def test_the_default_transcriber_never_picks_a_remote_backend_silently(
    tmp_path, monkeypatch
):
    import sys
    import types

    from an.audio.recorded import TranscriberUnavailableError, scribed_transcriber

    class _Info:
        def __init__(self, id):
            self.id = id

    calls = []
    fake = types.ModuleType("scribed")
    fake.available_backends = lambda: ["elevenlabs", "openai"]
    fake.find = lambda **criteria: [_Info("faster-whisper"), _Info("vosk")]
    fake.transcribe = lambda path, **kw: calls.append(kw) or []
    monkeypatch.setitem(sys.modules, "scribed", fake)
    with pytest.raises(TranscriberUnavailableError, match="--transcriber"):
        scribed_transcriber()(tmp_path / "take.wav")
    assert calls == []
    fake.available_backends = lambda: ["elevenlabs", "faster-whisper"]
    scribed_transcriber()(tmp_path / "take.wav")
    assert calls[-1]["backend"] == "faster-whisper"
    scribed_transcriber("elevenlabs")(tmp_path / "take.wav")  # named: allowed
    assert calls[-1]["backend"] == "elevenlabs"


# --- a transcript that is a linked artifact in the project store (an#493) -------------


def _recorded_transcript(root, key="take1"):
    from an.stores.transcripts import TRANSCRIPTS_STORE, record_transcript

    store = load(root).mall[TRANSCRIPTS_STORE]
    return record_transcript(store, key, SRT, generated_by="processor:test.asr")


@pytest.mark.parametrize("named", ["by reference", "as the artifact"])
def test_a_transcript_artifact_in_the_store_times_the_take_and_its_provenance_names_it(
    tmp_path, named
):
    root = _project(tmp_path)
    artifact = _recorded_transcript(root)
    transcript = "artifact:transcripts/take1" if named == "by reference" else artifact
    report = import_recordings(
        root, _take(tmp_path), transcript=transcript, license=LICENSE
    )
    assert [t.line for t in report.takes] == ["s1/0", "s1/1"]
    # by reference or as the artifact, the take names the key AND the bytes it read
    expected = f"transcripts/take1@{artifact.asset_id}"
    for record in _records(root).values():
        extra = record["source"]["extra"]
        assert extra["transcript"] == "srt" and extra["transcript_artifact"] == expected


def test_a_file_transcript_records_no_artifact(tmp_path):
    root = _project(tmp_path)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    assert all(
        "transcript_artifact" not in r["source"]["extra"]
        for r in _records(root).values()
    )


def test_a_transcript_artifact_that_is_not_there_is_refused_by_name(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(RecordedVoicesError, match="no transcript 'nope'"):
        import_recordings(
            root,
            _take(tmp_path),
            transcript="artifact:transcripts/nope",
            license=LICENSE,
        )
    with pytest.raises(RecordedVoicesError, match="no transcript 'elsewhere/x'"):
        import_recordings(
            root, _take(tmp_path), transcript="artifact:elsewhere/x", license=LICENSE
        )


def test_a_linked_transcript_is_read_by_its_content_and_its_format(tmp_path):
    """A BOM does not hide the format; a VTT and a plain transcript read as
    they do from a file; a key may hold slashes; the mixed CLI form pairs an
    artifact and a file, one per take."""
    from an.stores.transcripts import linked_transcript, record_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    vtt = "\ufeffWEBVTT\n\n00:00.500 --> 00:01.500\ncarl: Hello.\n"
    art = record_transcript(mall["transcripts"], "session/a", vtt)
    assert art.mime == "text/vtt"
    linked = linked_transcript("artifact:transcripts/session/a", mall)
    assert linked.fmt == "vtt" and linked.ref == f"transcripts/session/a@{art.asset_id}"
    assert (
        linked_transcript("artifact:session/a", mall).ref == linked.ref
    )  # store implied
    record_transcript(mall["transcripts"], "plain", "carl: Hello there, Ned.\n")
    assert linked_transcript("artifact:transcripts/plain", mall).fmt == "plain"
    first, second = (
        _take(tmp_path, "a.wav", bursts=((0.5, 1.5),)),
        _take(tmp_path, "b.wav", bursts=((0.5, 1.5),)),
    )
    record_transcript(mall["transcripts"], "one", f"carl: {HELLO}\n")
    other = tmp_path / "two.txt"
    other.write_text(f"carl: {FINE}\n", encoding="utf-8")
    report = import_recordings(
        root,
        [first, second],
        transcript=f"{other},artifact:transcripts/one".replace(str(other), str(other)),
        license=LICENSE,
        write=False,
    )
    assert len(report.takes) == 2


def test_what_is_not_a_transcript_artifact_is_refused_by_name(tmp_path):
    from an.stores.transcripts import TranscriptLinkError, linked_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    with pytest.raises(TranscriptLinkError, match="not transcript artifacts"):
        linked_transcript("artifact:scenes/main", mall)
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    key = next(iter(load(root).mall[RECORDINGS_STORE]))
    with pytest.raises(TranscriptLinkError, match="not transcript artifacts"):
        linked_transcript(f"artifact:recordings/{key}", mall)


def test_a_linked_transcript_passed_in_and_a_damaged_record(tmp_path):
    """A `LinkedTranscript` already read is taken as it is; a record that does
    not validate is refused by name, not with a traceback; linked text that
    happens to name a local file is still read as text."""
    from an.stores.transcripts import linked_transcript, record_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    record_transcript(mall["transcripts"], "take1", SRT)
    linked = linked_transcript("artifact:transcripts/take1", mall)
    report = import_recordings(
        root, _take(tmp_path), transcript=linked, license=LICENSE, write=False
    )
    assert len(report.takes) == 2
    (root / "artifacts" / "transcripts" / "catalog" / "bad.json").write_text(
        "{not json", encoding="utf-8"
    )
    with pytest.raises(RecordedVoicesError, match="'bad'.*damaged"):
        import_recordings(
            root,
            _take(tmp_path),
            transcript="artifact:transcripts/bad",
            license=LICENSE,
        )
    from an.audio.transcripts import parse_transcript_text

    (tmp_path / "note").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nnot me\n", encoding="utf-8"
    )
    assert parse_transcript_text("note", fmt="plain")[0].text == "note"


def test_a_recorded_reference_reads_back_the_content_it_names(tmp_path):
    """an#607: the provenance a take records (`transcripts/<key>@<sha256>`)
    is a reference too, and it reads the bytes it pinned even after the key was
    recorded again; a key that starts like a mall store is still found."""
    from an.stores.transcripts import linked_transcript, record_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    import_recordings(root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE)
    first = record_transcript(mall["transcripts"], "k", SRT)
    pinned = linked_transcript("artifact:transcripts/k", mall).ref
    record_transcript(mall["transcripts"], "k", "carl: something else\n")
    again = linked_transcript(f"artifact:{pinned}", mall)
    assert again.ref == pinned and again.fmt == "srt" and HELLO in again.text
    assert pinned.endswith(first.asset_id)
    record_transcript(mall["transcripts"], "takes/a", SRT)  # `takes` is a mall store
    assert linked_transcript("artifact:takes/a", mall).ref.startswith(
        "transcripts/takes/a@"
    )


def test_gc_collects_the_transcripts_nothing_names(tmp_path):
    from an.build.gc import collect_garbage
    from an.stores.transcripts import record_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    used = record_transcript(mall["transcripts"], "take", SRT)
    import_recordings(
        root, _take(tmp_path), transcript="artifact:transcripts/take", license=LICENSE
    )
    record_transcript(
        mall["transcripts"], "take", "carl: Hello there, Ned.\n"
    )  # the take still names `used`
    dropped = record_transcript(mall["transcripts"], "scratch", "carl: a draft\n")
    record_transcript(mall["transcripts"], "scratch", "carl: the final draft\n")
    import time

    later = time.time() + 3600  # past the protection horizon of what was just written
    dry = collect_garbage(root, dry_run=True, now=later, force=True)
    assert dry.deleted_derived.get("transcripts") == [dropped.asset_id]
    collect_garbage(root, now=later, force=True)
    store = load(root).mall["transcripts"]
    assert store.get_blob(dropped.asset_id) is None
    assert store.get_blob(used.asset_id) is not None, "a take still names it"


def test_gc_keeps_every_transcript_when_it_cannot_tell_what_is_named(tmp_path):
    """A damaged catalog record might name any blob, a just-written blob may be
    a transcript being recorded, and a remote store cannot say when one was
    written: in each case the sweep keeps it (an#607 review)."""
    import time

    from an.build.gc import GcReport, _collect_transcripts, collect_garbage
    from an.stores.transcripts import in_memory_transcripts_store, record_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    old = record_transcript(mall["transcripts"], "k", "carl: a draft\n")
    record_transcript(mall["transcripts"], "k", "carl: the final draft\n")
    # written just now: inside the protection horizon of a collection run now
    assert not collect_garbage(root, force=True).deleted_derived
    # a damaged record: nothing is collected, however late
    (root / "artifacts" / "transcripts" / "catalog" / "bad.json").write_text(
        "{", encoding="utf-8"
    )
    later = time.time() + 3600
    assert not collect_garbage(root, now=later, force=True).deleted_derived
    assert load(root).mall["transcripts"].get_blob(old.asset_id) is not None
    # a remote (in-memory) store: write times unknown, so nothing goes
    remote = in_memory_transcripts_store()
    record_transcript(remote, "k", "carl: a\n")
    record_transcript(remote, "k", "carl: b\n")
    report = GcReport(dry_run=False)
    _collect_transcripts({"transcripts": remote}, report, horizon=later)
    assert not report.deleted_derived and len(list(remote.iter_blobs())) == 2


def test_a_pinned_reference_reads_its_bytes_after_its_key_is_gone(tmp_path):
    from an.stores.transcripts import linked_transcript, record_transcript

    root = _project(tmp_path)
    mall = load(root).mall
    record_transcript(mall["transcripts"], "k", SRT)
    ref = linked_transcript("artifact:transcripts/k", mall).ref
    del mall["transcripts"]["k"]
    again = linked_transcript(f"artifact:{ref}", mall)
    assert HELLO in again.text and again.fmt == "srt"


def test_lacing_reads_the_reference_and_an_names_what_is_missing():
    """an#670: `lacing.ArtifactRef` parses and `resolve_in_mall` reads; an's
    refusals still say which part is missing, and a pin in capitals is a pin."""
    from an.stores.transcripts import (
        TranscriptLinkError,
        in_memory_transcripts_store,
        linked_transcript,
        pin_of,
        record_transcript,
    )

    store = in_memory_transcripts_store()
    art = record_transcript(store, "k", SRT)
    mall = {"transcripts": store}
    shouting = f"artifact:transcripts/k@{art.asset_id.upper()}"
    assert linked_transcript(shouting, mall).ref == f"transcripts/k@{art.asset_id}"
    assert pin_of(shouting.removeprefix("artifact:")) == art.asset_id
    for item, says in [
        ("take.srt", "not an artifact reference"),
        ("artifact:nope", "no transcript 'nope'"),
        (f"artifact:transcripts/k@{'0' * 64}", "no longer kept"),
    ]:
        with pytest.raises(TranscriptLinkError, match=says):
            linked_transcript(item, mall)
    with pytest.raises(TranscriptLinkError, match="no 'transcripts' store"):
        linked_transcript("artifact:k", {"other": store})
    for key in ("a b", "/a", f"k@{'0' * 64}"):
        with pytest.raises(TranscriptLinkError, match="choose another transcript key"):
            record_transcript(store, key, SRT)
    # What an older an recorded under a key lacing now refuses is still a pin
    # (else `an cache gc` would collect what the take names).
    assert pin_of(f"transcripts/my take@{art.asset_id}") == art.asset_id


def _textgrid(
    tiers: dict[str, list[tuple[float, float, str]]], xmax: float = 4.0
) -> str:
    """A long-form Praat TextGrid with the given interval tiers."""
    out = [
        'File type = "ooTextFile"', 'Object class = "TextGrid"', "xmin = 0",
        f"xmax = {xmax}", "tiers? <exists>", f"size = {len(tiers)}", "item []:",
    ]  # fmt: skip
    for i, (name, intervals) in enumerate(tiers.items(), start=1):
        out += [
            f"    item [{i}]:", '        class = "IntervalTier"', f'        name = "{name}"',
            "        xmin = 0", f"        xmax = {xmax}", f"        intervals: size = {len(intervals)}",
        ]  # fmt: skip
        for j, (a, b, text) in enumerate(intervals, start=1):
            out += [
                f"        intervals [{j}]:", f"            xmin = {a}",
                f"            xmax = {b}", f'            text = "{text}"',
            ]  # fmt: skip
    return "\n".join(out) + "\n"


_TG_TIERS = {
    "utterances": [
        (0.0, 0.5, ""),
        (0.5, 1.5, f"carl: {HELLO}"),
        (1.5, 2.5, ""),
        (2.5, 3.3, f"carl: {FINE}"),
    ],
    "words": [
        (0.5, 0.8, "Hello"),
        (0.8, 1.1, "there"),
        (1.1, 1.5, "Ned"),
        (2.5, 2.9, "Fine"),
        (2.9, 3.3, "thanks"),
    ],
    "phones": [
        (0.0, 0.5, "sil"),
        (0.5, 0.6, "HH"),
        (0.6, 0.7, "AH0"),
        (0.7, 0.8, "L"),
        (0.8, 1.1, "DH"),
        (1.1, 1.5, "N"),
        (2.5, 2.9, "F"),
        (2.9, 3.3, "TH"),
    ],
}
ALIGNED = _textgrid(_TG_TIERS)


def test_a_textgrid_phones_tier_is_read_beside_the_words():
    """an#491: an aligner's phones, per segment, silence dropped."""
    from an.audio.transcripts import parse_textgrid

    hello, fine = parse_textgrid(ALIGNED)
    assert hello.phones == (
        ("HH", 0.5, 0.6), ("AH0", 0.6, 0.7), ("L", 0.7, 0.8), ("DH", 0.8, 1.1), ("N", 1.1, 1.5),
    )  # fmt: skip
    assert fine.phones == (("F", 2.5, 2.9), ("TH", 2.9, 3.3))
    words_only = _textgrid({"words": [(0.5, 0.8, "Hello")]})
    assert parse_textgrid(words_only)[0].phones is None


class _Listening(NullLipSync):
    """Records the phones of every clip it is asked to align."""

    def __init__(self):
        self.heard = []

    def align(self, audio, transcript):
        self.heard.append(audio.phones)
        return super().align(audio, transcript)


def test_a_takes_phones_reach_the_lip_sync_fresh_and_read_back(tmp_path):
    """an#491: imported with a TextGrid's phones, a take keeps them (cut to
    the take, stored with it) and the lip-sync provider is handed them, from a
    fresh take and from audio read back from the store."""
    root = _project(tmp_path)
    grid = tmp_path / "take.TextGrid"
    grid.write_text(ALIGNED, encoding="utf-8")
    import_recordings(root, _take(tmp_path), transcript=grid, license=LICENSE)
    (hello,) = [r for r in _records(root).values() if r["text"] == HELLO]
    assert hello["phones"][0][0] == "HH" and hello["phones"][0][1] == pytest.approx(
        0.05
    )
    for _ in range(2):  # fresh, then read back from the audio store
        proj = load(root)
        for key in list(proj.mall["visemes"]):
            del proj.mall["visemes"][key]
        lipsync = _Listening()
        produce_audio_for_scene(proj.scene, proj.mall, lipsync=lipsync, announce=None)
        first = next(p for p in lipsync.heard if p and p[0][0] == "HH")
        assert first[-1] == (
            "N",
            pytest.approx(0.65),
            pytest.approx(1.05),
        )  # cut at 0.45


def test_textgrid_tiers_are_named_as_aligners_name_them():
    """an#491 review: a phones tier is never read as the words; MFA names its
    tiers per speaker (`carl - words`); silence and markers are not speech."""
    from an.audio.transcripts import parse_textgrid

    phones_first = _textgrid(
        {"phones": [(0.5, 0.6, "HH"), (0.6, 0.9, "AH0")], "words": [(0.5, 0.9, "hey")]}
    )
    (seg,) = parse_textgrid(phones_first)
    assert seg.words == (("hey", 0.5, 0.9),) and seg.phones[0][0] == "HH"
    mfa = _textgrid(
        {
            "carl - words": [(0.5, 0.9, "hey"), (0.9, 1.0, "SIL")],
            "carl - phones": [
                (0.5, 0.6, "HH"),
                (0.6, 0.9, "EY1"),
                (0.9, 1.0, "+breath+"),
            ],
        }
    )
    (seg,) = parse_textgrid(mfa)
    assert seg.words == (("hey", 0.5, 0.9),)
    assert [p[0] for p in seg.phones] == ["HH", "EY1"]


def test_new_phones_on_the_same_audio_reach_the_lip_sync(tmp_path):
    """an#491 review: the same take imported again with phones (it had only
    words) is new audio to the caches, so the lip-sync is asked again."""
    root = _project(tmp_path)
    words_only = _textgrid({k: v for k, v in _TG_TIERS.items() if k != "phones"})
    grid = tmp_path / "take.TextGrid"
    grid.write_text(words_only, encoding="utf-8")
    take = _take(tmp_path)
    import_recordings(root, take, transcript=grid, license=LICENSE)
    proj = load(root)
    produce_audio_for_scene(proj.scene, proj.mall, lipsync=NullLipSync(), announce=None)
    grid.write_text(ALIGNED, encoding="utf-8")
    import_recordings(root, take, transcript=grid, license=LICENSE)
    proj = load(root)
    lipsync = _Listening()
    produce_audio_for_scene(proj.scene, proj.mall, lipsync=lipsync, announce=None)
    assert any(p and p[0][0] == "HH" for p in lipsync.heard), lipsync.heard


def _plain(tmp_path):
    path = tmp_path / "take.txt"
    path.write_text(f"carl: {HELLO}\ncarl: {FINE}\n", encoding="utf-8")
    return path


#: What MFA writes for the take (speaker-prefixed tiers, no utterances tier,
#: lowercase words, `sil` between lines): what the aligner hands back.
MFA_GRID = _textgrid(
    {
        "take - words": [(a, b, w.lower()) for a, b, w in _TG_TIERS["words"]],
        "take - phones": _TG_TIERS["phones"] + [(1.5, 2.5, "sil")],
    }
)


class _Aligner:
    """A fake forced aligner: MFA's TextGrid for any WAV it is handed."""

    phone_alphabet = "arpabet"

    def __init__(self):
        self.heard = []

    def __call__(self, path, text):
        from an.audio.transcripts import parse_textgrid

        self.heard.append((Path(path).suffix, wave.open(str(path)).getnframes(), text))
        return parse_textgrid(MFA_GRID)


def test_a_plain_transcript_timed_by_an_aligner_gets_the_phones_a_textgrid_gives(
    tmp_path,
):
    """an#637: a take imported with a plain transcript and a forced aligner
    (the `align=` seam: it times the KNOWN text, words and phones; here MFA's
    own TextGrid shape) is stored with the same phones as the same take
    imported with a TextGrid, the alphabet beside them, and the aligner is
    handed the take as decoded (a WAV), never the transcriber."""
    grid = tmp_path / "take.TextGrid"
    grid.write_text(ALIGNED, encoding="utf-8")
    by_grid = _project(tmp_path / "g")
    import_recordings(by_grid, _take(tmp_path), transcript=grid, license=LICENSE)
    by_aligner = _project(tmp_path / "a")
    align = _Aligner()
    report = import_recordings(
        by_aligner, _take(tmp_path), transcript=_plain(tmp_path), license=LICENSE,
        align=align,
        transcribe=lambda path: pytest.fail("an aligned take is not transcribed"),
    )  # fmt: skip
    assert align.heard == [(".wav", 4 * RATE, f"{HELLO} {FINE}")]
    want = {r["text"]: r["phones"] for r in _records(by_grid).values()}
    got = {r["text"]: r for r in _records(by_aligner).values()}
    assert {t: r["phones"] for t, r in got.items()} == want
    assert all(r["phone_alphabet"] == "arpabet" for r in got.values())
    assert len(report.takes) == 2


def test_an_aligner_needs_a_plain_transcript(tmp_path):
    """an#637 review: an aligner has no text to align without a plain
    transcript, and a timed one keeps its own times: both are refused rather
    than the aligner going silently unused."""
    root = _project(tmp_path)
    with pytest.raises(RecordedVoicesError, match="has none"):
        import_recordings(root, _take(tmp_path), license=LICENSE, align=_Aligner())
    with pytest.raises(RecordedVoicesError, match="a timed one"):
        import_recordings(
            root, _take(tmp_path), transcript=_srt(tmp_path), license=LICENSE,
            align=_Aligner(),
        )  # fmt: skip


@pytest.mark.ffmpeg
def test_a_take_in_any_format_reaches_the_aligner_as_a_wav(tmp_path):
    """an#637 review: MFA reads few formats; the aligner is handed the take as
    decoded, so an .m4a take aligns too."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not on PATH")
    import subprocess

    m4a = tmp_path / "take.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(_take(tmp_path)), str(m4a)], check=True
    )
    align = _Aligner()
    import_recordings(
        _project(tmp_path),
        m4a,
        transcript=_plain(tmp_path),
        license=LICENSE,
        align=align,
    )
    assert align.heard[0][0] == ".wav"


class _LineAligner(_Aligner):
    """A fake line aligner (an#716): MFA's grid for the lines it is handed,
    which it records."""

    def __init__(self):
        super().__init__()
        self.lines = []

    def align_lines(self, path, lines):
        from an.audio.transcripts import parse_textgrid

        self.lines.append([(s.text, s.start, s.end) for s in lines])
        return parse_textgrid(MFA_GRID)


def test_a_long_take_s_lines_are_aligned_each_in_its_rough_interval(tmp_path):
    """an#716: with several lines and an aligner that aligns lines (MFA), the
    lines are first timed roughly by the transcriber's words, and each is
    aligned within its own interval, padded but never past its neighbour's;
    the phones are those the one-utterance form gives. With no rough words,
    or an aligner without lines, the whole text is one utterance (an#637)."""
    from an.audio.recorded import DFLT_ALIGN_LINE_PAD_S
    from an.audio.transcripts import parse_textgrid

    heard = parse_textgrid(ALIGNED)  # the transcriber's words, roughly where said
    by_lines = _project(tmp_path / "l")
    align = _LineAligner()
    import_recordings(
        by_lines, _take(tmp_path), transcript=_plain(tmp_path), license=LICENSE,
        align=align, transcribe=lambda path: heard,
    )  # fmt: skip
    ((first, second),) = align.lines
    assert first[0] == HELLO and second[0] == FINE
    pad = DFLT_ALIGN_LINE_PAD_S
    assert first[1] == pytest.approx(0.5 - pad) and second[2] == pytest.approx(
        3.3 + pad
    )
    assert first[2] <= second[1], "the intervals never overlap"
    assert align.heard == [], "the one-utterance form is not used"
    by_one = _project(tmp_path / "o")
    import_recordings(
        by_one, _take(tmp_path), transcript=_plain(tmp_path), license=LICENSE,
        align=_Aligner(), transcribe=lambda path: pytest.fail("not transcribed"),
    )  # fmt: skip
    phones = lambda root: {r["text"]: r["phones"] for r in _records(root).values()}  # noqa: E731
    assert phones(by_lines) == phones(by_one)
    unplaced = _LineAligner()
    with pytest.warns(RecordedVoicesWarning, match="one utterance"):
        import_recordings(
            _project(tmp_path / "u"), _take(tmp_path), transcript=_plain(tmp_path),
            license=LICENSE, align=unplaced, transcribe=lambda path: [],
        )  # fmt: skip
    assert unplaced.lines == [] and len(unplaced.heard) == 1


def _heard(*words):
    """A transcriber hearing ``words`` (``(word, start, end)``) in any take."""
    from an.audio.transcripts import TranscriptSegment

    return lambda path: [TranscriptSegment(" ".join(w[0] for w in words), words=words)]


#: The take's words as a transcriber hears them (the fixture's bursts).
HEARD = (("hello", 0.5, 0.8), ("there", 0.8, 1.1), ("ned", 1.1, 1.5),
         ("fine", 2.5, 2.9), ("thanks", 2.9, 3.3))  # fmt: skip


def _import_lines(tmp_path, *, lines=(HELLO, FINE), align=None, **kw):
    """The fixture take imported with a plain transcript of ``lines`` by a
    line aligner (recorded in ``align``), into a fresh project."""
    align = align if align is not None else _LineAligner()
    text = tmp_path / "lines.txt"
    text.write_text("".join(f"carl: {t}\n" for t in lines), encoding="utf-8")
    root = _project(tmp_path / "p", lines=lines)
    import_recordings(
        root, _take(tmp_path), transcript=text, license=LICENSE, align=align, **kw
    )
    return root, align


def test_rough_intervals_never_overlap_when_lines_are_closer_than_two_pads(tmp_path):
    """an#716 review: two lines heard closer than twice the pad meet at the
    midpoint of their gap (`cut_spans`), never overlapping."""
    from an.audio.recorded import DFLT_ALIGN_LINE_PAD_S

    close = HEARD[:2] + (("ned", 1.1, 2.1), ("fine", 2.3, 2.9), ("thanks", 2.9, 3.3))
    assert 2.3 - 2.1 < 2 * DFLT_ALIGN_LINE_PAD_S
    _, align = _import_lines(tmp_path, transcribe=_heard(*close))
    ((first, second),) = align.lines
    assert first[2] == pytest.approx(2.2) == second[1]


def test_a_line_the_transcriber_did_not_hear_falls_back_to_one_utterance(tmp_path):
    """an#716 review: a line the transcriber did not hear between two it did is
    squeezed to nothing; no interval is trusted, and the lines are aligned as
    one utterance, with a warning."""
    lines = (HELLO, "Okay.", FINE)
    squeezed = HEARD[:3] + (("fine", 1.5, 2.9), ("thanks", 2.9, 3.3))
    with pytest.warns(
        RecordedVoicesWarning, match="'Okay.' was not heard"
    ):
        _, align = _import_lines(tmp_path, lines=lines, transcribe=_heard(*squeezed))
    assert align.lines == [] and len(align.heard) == 1


def test_rough_words_that_do_not_fit_the_lines_fall_back_to_one_utterance(tmp_path):
    """an#716 review: words that are not the transcript's (a wrong take, a
    hallucinating transcriber) give no intervals, however confident."""
    wrong = tuple((w, a, b) for (_, a, b), w in zip(HEARD, "a b c d e".split()))
    with pytest.warns(
        RecordedVoicesWarning, match="heard 0 of the transcript's 5 words"
    ):
        _, align = _import_lines(tmp_path, transcribe=_heard(*wrong))
    assert align.lines == [] and len(align.heard) == 1


def test_a_line_aligner_with_no_transcriber_falls_back_to_one_utterance(tmp_path):
    """an#716 review: the import needed no transcriber before rough timing;
    with none to run it still aligns, as one utterance, with a warning."""

    def none_here(path):
        raise TranscriberUnavailableError("no local transcriber is installed")

    with pytest.warns(RecordedVoicesWarning, match="no local transcriber"):
        root, align = _import_lines(tmp_path, transcribe=none_here)
    assert align.lines == [] and len(align.heard) == 1
    assert {r["text"] for r in _records(root).values()} == {HELLO, FINE}


def test_rough_timing_off_never_transcribes(tmp_path):
    """an#716 review: `rough_timing=False` aligns as before an#716, one
    utterance, and never runs the transcriber."""
    _, align = _import_lines(
        tmp_path, rough_timing=False,
        transcribe=lambda path: pytest.fail("not transcribed"),
    )  # fmt: skip
    assert align.lines == [] and len(align.heard) == 1


class _HalfLineAligner(_LineAligner):
    """A line aligner that aligns only the first line (MFA failing the second)."""

    def align_lines(self, path, lines):
        from an.audio.transcripts import parse_textgrid

        self.lines.append([(s.text, s.start, s.end) for s in lines])
        grid = _textgrid(
            {k: [i for i in v if i[1] <= 1.5] for k, v in _TG_TIERS.items()}
        )
        return parse_textgrid(grid)


def test_a_line_the_aligner_left_without_words_is_warned_of_and_kept(tmp_path):
    """an#716 review: a line MFA placed no word in does not vanish into its
    neighbour: it keeps its rough times, has no phones, and is warned of."""
    with pytest.warns(
        RecordedVoicesWarning, match="no word of the line 'Fine, thanks.'"
    ):
        root, _ = _import_lines(
            tmp_path, align=_HalfLineAligner(), transcribe=_heard(*HEARD)
        )
    records = {r["text"]: r for r in _records(root).values()}
    assert records[HELLO].get("phones") and records[FINE].get("phones") is None
    assert records[FINE]["source"]["extra"]["span"] == pytest.approx([2.45, 3.35])


def test_the_mfa_aligner_aligns_lines_from_a_textgrid_of_intervals(tmp_path):
    """an#716: `align_lines` hands MFA a TextGrid with one interval per line
    (spanning the whole take) instead of a `.lab`, and reads its TextGrid."""
    from an.audio.recorded import mfa_aligner
    from an.audio.transcripts import TranscriptSegment, _textgrid_tiers

    given = []

    def run(argv, **kw):
        corpus, out = Path(argv[2]), Path(argv[5])
        assert sorted(f.name for f in corpus.iterdir()) == ["take.TextGrid", "take.wav"]
        given.append(
            _textgrid_tiers((corpus / "take.TextGrid").read_text(encoding="utf-8"))
        )
        out.mkdir()
        (out / "take.TextGrid").write_text(MFA_GRID, encoding="utf-8")
        return type("Done", (), {"returncode": 0, "stderr": b""})()

    lines = [TranscriptSegment(HELLO, 0.25, 1.75), TranscriptSegment(FINE, 2.25, 4.2)]
    said = mfa_aligner(run=run).align_lines(_take(tmp_path), lines)
    assert said and said[0].phones
    assert given == [{"take": [(0.0, 0.25, ""), (0.25, 1.75, HELLO), (1.75, 2.25, ""),
                               (2.25, 4.0, FINE)]}]  # fmt: skip
    # clamped to the file's 4 s


def test_a_textgrid_is_written_as_given_or_refused():
    """an#716 review: `textgrid_text` clamps nothing: an interval out of the
    grid's span or overlapping another is refused; a quote in a tier name is
    escaped, and read back."""
    from an.audio.transcripts import _textgrid_tiers, textgrid_text

    with pytest.raises(ValueError, match="outside"):
        textgrid_text({"take": [(0.5, 2.5, "a")]}, xmax=2.0)
    with pytest.raises(ValueError, match="overlaps"):
        textgrid_text({"take": [(0.5, 1.2, "a"), (1.0, 1.5, "b")]}, xmax=2.0)
    grid = textgrid_text({'the "take"': [(0.5, 1.0, "a")]}, xmax=2.0)
    assert list(_textgrid_tiers(grid)) == ['the "take"']


def test_the_mfa_aligner_runs_mfa_on_a_one_file_corpus_and_reads_its_textgrid(tmp_path):
    """an#637: `mfa_aligner` writes the take and its text as a corpus, runs
    `mfa align` with the alphabet's English model, and reads the TextGrid back;
    without `mfa` it refuses, saying how to install it and its model."""
    from an.audio.recorded import TranscriberUnavailableError, mfa_aligner

    from an.audio.recorded import AlignmentError, aligner_named

    calls = []

    def run(argv, **kw):
        calls.append(argv)
        corpus, out = Path(argv[2]), Path(argv[5])
        assert sorted(f.name for f in corpus.iterdir()) == ["take.lab", "take.wav"]
        assert (corpus / "take.lab").read_text(encoding="utf-8") == "Hello there, Ned."
        out.mkdir()
        (out / "take.TextGrid").write_text(MFA_GRID, encoding="utf-8")
        return type("Done", (), {"returncode": 0, "stderr": b""})()

    align = mfa_aligner(run=run)
    (said,) = align(_take(tmp_path), "Hello there, Ned.")
    assert calls[0][:2] == ["mfa", "align"] and calls[0][3:5] == ["english_us_arpa"] * 2
    assert said.phones[0][0] == "HH" and align.phone_alphabet == "arpabet"
    align(_take(tmp_path), "Hello there, Ned.")
    assert Path(calls[0][2]).name != Path(calls[1][2]).name  # MFA's workspace name
    assert aligner_named("mfa:ipa").phone_alphabet == "ipa"
    with pytest.raises(RecordedVoicesError, match="no aligner 'gentle'"):
        aligner_named("gentle")
    with pytest.raises(TranscriberUnavailableError, match="conda install"):
        mfa_aligner(executable="no-such-mfa-here")(_take(tmp_path), "x")
    with pytest.raises(RecordedVoicesError, match="no MFA model"):
        mfa_aligner(alphabet="klingon")
    failed = mfa_aligner(
        run=lambda argv, **kw: type(
            "F", (), {"returncode": 1, "stdout": b"beam too narrow", "stderr": b""}
        )()
    )
    with pytest.raises(AlignmentError, match="beam too narrow"):
        failed(_take(tmp_path), "x")


def test_mfa_and_gentle_json_give_the_phones_their_textgrid_gives(tmp_path):
    """an#715: a take imported with the Montreal Forced Aligner's JSON
    (`tiers.<name>.entries`) or Gentle's (each word's `phones`, durations from
    its start, `hh_B` position suffixes) is stored with the same phones as with
    the matching TextGrid."""
    words = [w for w in _TG_TIERS["words"] if w[1] <= 1.5]
    phones = [p for p in _TG_TIERS["phones"] if p[2] != "sil" and p[1] <= 1.5]
    grid = tmp_path / "take.TextGrid"
    grid.write_text(_textgrid({"words": words, "phones": phones}), encoding="utf-8")
    mfa = tmp_path / "mfa.json"
    mfa.write_text(json.dumps({"tiers": {
        "take - words": {"type": "interval", "entries": [[a, b, t.lower()] for a, b, t in words]},
        "take - phones": {"type": "interval", "entries": [[a, b, t] for a, b, t in phones]},
    }}), encoding="utf-8")  # fmt: skip
    gentle_words = []
    for a, b, t in words:
        inside = [p for p in phones if a <= p[0] < b]
        gentle_words.append({
            "word": t, "alignedWord": t.lower(), "case": "success", "start": a, "end": b,
            # Gentle's phones are CMU's without stress (`ah_I`), and an
            # unknown word's is `oov`: dropped, as MFA's `spn` is
            "phones": [{"phone": f"{ph.rstrip('012').lower()}_I", "duration": round(e - s, 6)}
                       for s, e, ph in inside],
        })  # fmt: skip
    gentle = tmp_path / "gentle.json"
    gentle.write_text(
        json.dumps({"transcript": HELLO, "words": gentle_words}), encoding="utf-8"
    )

    def phones_of(transcript, name):
        root = _project(tmp_path / name, lines=(HELLO,))
        take = _take(tmp_path / name, bursts=((0.5, 1.5),), seconds=2.0)
        import_recordings(root, take, transcript=transcript, license=LICENSE)
        (record,) = _records(root).values()
        return record["phones"], record.get("phone_alphabet")

    by_grid, grid_alphabet = phones_of(grid, "g")
    assert by_grid and by_grid[0][0] == "HH"
    # each reader states the alphabet its format shows (an#721)
    assert grid_alphabet == "arpabet"
    assert phones_of(mfa, "m") == (by_grid, "arpabet")
    unstressed = [[p.rstrip("012"), a, b] for p, a, b in by_grid]
    assert phones_of(gentle, "j") == (unstressed, "arpabet")


def test_readers_give_every_mfa_speaker_the_alphabet_and_drop_gentle_s_disfluencies():
    """an#721: MFA's `"<speaker> - words"` tiers are read for EVERY speaker,
    the speaker set and the segments in time order; the reader reports the
    phone alphabet its labels show (IPA symbols, ARPAbet stress digits, else
    unknown); Gentle's words not in the transcript (an "um") are dropped."""
    from an.audio.transcripts import parse_json

    two = parse_json({"tiers": {
        "ned - words": {"entries": [[1.0, 1.4, "yo"]]},
        "ned - phones": {"entries": [[1.0, 1.2, "j"], [1.2, 1.4, "əʊ"]]},
        "carl - words": {"entries": [[0.0, 0.3, "hi"], [0.3, 0.6, ""]]},
        "carl - phones": {"entries": [[0.0, 0.1, "HH"], [0.1, 0.3, "AY1"]]},
    }})  # fmt: skip
    assert [(s.speaker, s.text, s.phone_alphabet) for s in two] == [
        ("carl", "hi", "arpabet"),
        ("ned", "yo", "ipa"),
    ]
    assert two[0].phones == (("HH", 0.0, 0.1), ("AY1", 0.1, 0.3))
    unknown = parse_json({"tiers": {
        "words": {"entries": [[0.0, 0.3, "ai"]]},
        "phones": {"entries": [[0.0, 0.1, "ai1"], [0.1, 0.3, "ou3"]]},
    }})  # fmt: skip
    assert unknown[0].phones and unknown[0].phone_alphabet is None
    gentle = parse_json({"transcript": "hi there", "words": [
        {"word": "hi", "case": "success", "start": 0.0, "end": 0.3,
         "phones": [{"phone": "hh_B", "duration": 0.1}, {"phone": "ay_E", "duration": 0.2}]},
        {"word": "um", "case": "not-found-in-transcript", "start": 0.3, "end": 0.6,
         "phones": [{"phone": "ah_B", "duration": 0.1}, {"phone": "m_E", "duration": 0.2}]},
        {"word": "there", "case": "not-found-in-audio"},
    ]})  # fmt: skip
    (seg,) = gentle
    assert seg.text == "hi" and seg.words == (("hi", 0.0, 0.3),)
    assert [p[0] for p in seg.phones] == [
        "HH",
        "AY",
    ] and seg.phone_alphabet == "arpabet"


def test_an_interleaved_mfa_conversation_imports_one_take_per_turn(tmp_path):
    """an#721 review: carl, then ned, then carl again in one MFA alignment is
    three turns, not one carl segment nesting ned's (which the import refused
    as overlapping cues); each turn's phones are its speaker's."""
    root = init(tmp_path / "p")
    proj = load(root)
    scene = _scene((), character=False)
    scene.timeline[0].dialogue = [
        Dialogue(speaker="carl", text="Hi there."),
        Dialogue(speaker="ned", text="Yo Carl."),
        Dialogue(speaker="carl", text="Bye now."),
    ]
    proj.mall["scenes"]["main"] = scene
    mfa = tmp_path / "talk.json"
    mfa.write_text(json.dumps({"tiers": {
        "carl - words": {"entries": [[0.1, 0.3, "hi"], [0.3, 0.6, "there"], [0.6, 0.9, ""],
                                     [2.0, 2.2, "bye"], [2.2, 2.5, "now"]]},
        "carl - phones": {"entries": [[0.1, 0.2, "HH"], [0.2, 0.3, "AY1"],
                                      [2.0, 2.1, "B"], [2.1, 2.2, "AY1"]]},
        "ned - words": {"entries": [[0.9, 1.2, "yo"], [1.2, 1.5, "carl"]]},
        "ned - phones": {"entries": [[0.9, 1.0, "j"], [1.0, 1.2, "əʊ"]]},
    }}), encoding="utf-8")  # fmt: skip
    take = _take(tmp_path, seconds=3.0, bursts=((0.1, 0.6), (0.9, 1.5), (2.0, 2.5)))
    report = import_recordings(root, take, transcript=mfa, license=LICENSE)
    assert [(t.speaker, t.text) for t in report.takes] == [
        ("carl", "Hi there."),
        ("ned", "Yo Carl."),
        ("carl", "Bye now."),
    ]
    by_text = {r["text"]: r for r in _records(root).values()}
    assert [p[0] for p in by_text["Bye now."]["phones"]] == ["B", "AY1"]
    assert by_text["Bye now."]["phone_alphabet"] == "arpabet"
    assert by_text["Yo Carl."]["phone_alphabet"] == "ipa"


def test_a_tier_is_a_speaker_s_only_when_its_name_ends_in_a_known_tier():
    """an#721 review: ``"notes - draft"`` is a tier called that, not the
    tiers of a speaker called notes."""
    from an.audio.transcripts import segments_from_tiers

    segs = segments_from_tiers({
        "carl - words": [(0.0, 0.4, "hi")], "notes - draft": [(0.0, 1.0, "redo")],
    })  # fmt: skip
    assert [(s.speaker, s.text) for s in segs] == [("carl", "hi")]


def test_a_speaker_with_phones_and_no_words_has_no_segment():
    """an#721 review: with several speakers, one whose only tier is its phones
    says nothing; its phones are never read as words (an#491)."""
    from an.audio.transcripts import segments_from_tiers

    segs = segments_from_tiers({
        "carl - words": [(0.0, 0.4, "hi")],
        "ned - phones": [(0.5, 0.7, "Y"), (0.7, 0.9, "OW1")],
    })  # fmt: skip
    assert [(s.speaker, s.text) for s in segs] == [("carl", "hi")]


def test_the_arpabet_alphabet_is_read_from_the_arpabet_inventory():
    """an#721 review: ARPAbet is ASCII labels in one case, each in the 39-phone
    inventory once its stress digit is dropped (cutan's rule); pinyin's tone
    digits are not stress digits."""
    from an.audio.transcripts import ARPABET, IPA, phone_alphabet_of

    assert phone_alphabet_of(["ai1", "ou3"]) is None
    assert phone_alphabet_of(["AH", "T"]) == ARPABET
    assert phone_alphabet_of(["h", "ə"]) == IPA


def test_only_gentle_json_drops_a_word_by_its_case():
    """an#721 review: Gentle's ``case`` is read only in Gentle's JSON
    (``transcript`` and ``words``); another JSON's word with a ``case`` stays."""
    from an.audio.transcripts import parse_json

    (seg,) = parse_json({"words": [
        {"word": "hi", "start": 0.0, "end": 0.3, "case": "x"},
        {"word": "there", "start": 0.3, "end": 0.6},
    ]})  # fmt: skip
    assert seg.text == "hi there"


def test_json_that_is_not_mfa_s_keeps_its_segments_and_oov_is_not_a_phone():
    """an#715 review: a JSON with its own `segments` and an unrelated `tiers`
    key is read as segments, not as MFA's; a malformed MFA entry is said; and
    Gentle's `oov` (an unknown word) is not a phone."""
    from an.audio.transcripts import _gentle_phones, parse_json

    both = {"segments": [{"text": "carl: hi", "start": 0.0, "end": 1.0}],
            "tiers": {"meta": {"note": "x"}}}  # fmt: skip
    assert [s.text for s in parse_json(both)] == ["hi"]
    with pytest.raises(ValueError, match=r"\[start, end, label\]"):
        parse_json({"tiers": {"words": {"entries": [[0.5, "hi"]]}}})
    unknown = {"alignedWord": "<unk>", "start": 0.5, "end": 0.8,
               "phones": [{"phone": "oov_S", "duration": 0.3}]}  # fmt: skip
    assert _gentle_phones(unknown) == []


def test_a_heard_one_word_line_keeps_the_per_line_alignment():
    """an#716 re-review: a short line the transcriber heard ("No.", 0.08 s)
    is judged by its padded interval, so it does not switch the whole take to
    the one-utterance form; an unheard line squeezed between two heard ones
    still does."""
    from an.audio.recorded import DFLT_ROUGH_MIN_LINE_S, _rough_line_intervals, _RoughTimingUnfit
    from an.audio.transcripts import parse_transcript_text

    lines = parse_transcript_text("a: Hello there.\nb: No.\na: Fine thanks.", fmt="plain")
    heard = [("hello", 0.5, 0.9), ("there", 0.9, 1.3), ("no", 2.5, 2.58),
             ("fine", 4.0, 4.3), ("thanks", 4.3, 4.7)]  # fmt: skip
    spans = _rough_line_intervals(lines, heard, total=6.0, pad_s=0.25)
    assert spans[1].end - spans[1].start >= DFLT_ROUGH_MIN_LINE_S
    unheard = [("hello", 0.5, 0.9), ("there", 0.9, 1.3), ("fine", 1.3, 1.6), ("thanks", 1.6, 1.9)]
    with pytest.raises(_RoughTimingUnfit, match="not heard"):
        _rough_line_intervals(lines, unheard, total=6.0, pad_s=0.25, min_coverage=0.0)
