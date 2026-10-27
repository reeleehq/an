"""Library candidates by accent, and an audition reel of the scene's own lines (an#485).

Voice design from notes can miss a regional accent entirely; the shared voice
library, human-tagged by region, is the second route, and an audition reel —
the character's lines in each candidate's voice, with the film's TTS model
and the lines' cues — is how the writer hears what the film will sound like.
Nothing here reaches an API: the library, the previews and the TTS are fakes.
"""

from __future__ import annotations

import io
import json
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from an.audio.effects import EFFECT_SAMPLE_RATE
from an.audio.voice_design import (
    AUDITION_SAMPLE_RATE,
    ElevenLabsVoiceLibrary,
    LibraryVoice,
    VoiceDesignError,
    audition_project_voices,
    audition_voice_options,
    choose_project_voice,
    design_project_voices,
    design_voice_options,
    library_query_of,
    parse_library_query,
    plan_auditions,
)
from an.ir.schema import Dialogue
from an.project import init, load
from tests.test_shot_cache import _project, _set_shots, _shot
from tests.test_voice_design import NOTES, FakeDesigner


def _wav(seconds: float, *, rate: int = AUDITION_SAMPLE_RATE, channels: int = 1) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * seconds)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(n)) * channels)
    return out.getvalue()


def _seconds(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav), "rb") as r:
        return r.getnframes() / r.getframerate()


class FakeLibrary:
    def __init__(self, n=2):
        self.n, self.calls = n, []

    def search(self, *, limit, **filters):
        self.calls.append((limit, filters))
        return [
            LibraryVoice(f"lib{i}", f"Dan {i}", f"Cork, {filters.get('accent')}", accent=filters.get("accent"),
                         age="middle_aged", gender="male", preview_url=f"https://x/{i}.mp3" if i else None,
                         owner_id=f"owner{i}")
            for i in range(min(self.n, limit))
        ]

    def preview(self, voice):
        return b"ID3" + voice.voice_id.encode() if voice.preview_url else None


class FakeTTS:
    """The film's provider: records every request, speaks a short tone."""

    name = "elevenlabs"

    def __init__(self, seconds=0.5):
        self.seconds, self.requests = seconds, []

    def synthesize(self, text, voice_id, **kw):
        self.requests.append((text, voice_id, kw))
        return SimpleNamespace(bytes_=_wav(self.seconds), transcript=text)

    def synthesis_options(self, voice, *, emotion=None, direction=None):
        opts = {k: voice[k] for k in ("model_id", "voice_settings") if k in voice}
        tags = ([emotion] if emotion and emotion != "neutral" else []) + list(direction or [])
        if tags:
            opts["audio_tags"] = tags
        return opts

    def billed_characters(self, text, *, audio_tags=None, **_):
        return len(text) + sum(len(t) + 3 for t in audio_tags or ())


# -----------------------------------------------------------------------------
# The library route
# -----------------------------------------------------------------------------


def test_the_query_is_parsed_and_the_documents_own_wins():
    assert parse_library_query("accent=irish, gender=male") == {"accent": "irish", "gender": "male"}
    with pytest.raises(VoiceDesignError, match="unknown filter"):
        parse_library_query("region=cork")
    with pytest.raises(VoiceDesignError, match="unknown filter"):
        library_query_of({"library": {"region": "cork"}})
    assert library_query_of({"library": "accent=scottish"}, "accent=irish") == {"accent": "scottish"}
    assert library_query_of({"library": {"accent": "irish", "age": "young"}})["age"] == "young"


def test_the_elevenlabs_library_maps_the_sdk_shape():
    calls = []

    class Voices:
        def get_shared(self, **kw):
            calls.append(("get_shared", kw))
            return SimpleNamespace(voices=[SimpleNamespace(
                voice_id="v1", name="Dan", description="Cork", accent="irish", age="middle_aged",
                gender="male", language="en", preview_url="https://x/v1.mp3", public_owner_id="o1")])

        def share(self, owner, voice_id, **kw):
            calls.append(("share", owner, voice_id, kw))
            return SimpleNamespace(voice_id="mine")

    lib = ElevenLabsVoiceLibrary(api_key="k", client_factory=lambda _k: SimpleNamespace(voices=Voices()),
                                 fetch=lambda url: b"ID3" + url.encode())
    [v] = lib.search(accent="irish", gender="male", limit=3)
    assert calls[0] == ("get_shared", {"page_size": 3, "request_options": {"timeout_in_seconds": 120},
                                       "accent": "irish", "gender": "male"})
    assert (v.voice_id, v.owner_id, v.accent, v.preview_url) == ("v1", "o1", "irish", "https://x/v1.mp3")
    assert lib.preview(v) == b"ID3https://x/v1.mp3"
    assert lib.add("v1", "o1", name="jerry") == "mine" and calls[-1][:3] == ("share", "o1", "v1")
    with pytest.raises(VoiceDesignError, match="unknown library filter"):
        lib.search(region="cork")


def test_the_library_needs_a_key_and_says_so(monkeypatch):
    monkeypatch.delenv("ELEVEN_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(VoiceDesignError, match="ELEVEN_API_KEY"):
        ElevenLabsVoiceLibrary(client_factory=lambda _k: None).search(accent="irish")


def test_library_candidates_join_the_manifest_after_the_designed_options():
    lib, d, samples = FakeLibrary(), FakeDesigner(n=2), {}
    m = design_voice_options({"j": {"notes": NOTES, "library": {"accent": "irish"}}}, samples=samples,
                             designer=d, library=lib)
    labels = [o["option"] for o in m["j"]["options"]]
    assert labels == ["A", "B", "L1", "L2"]
    assert [o["kind"] for o in m["j"]["options"]] == ["designed", "designed", "library", "library"]
    assert m["j"]["library"] == {"accent": "irish"} and m["j"]["options"][2]["voice_id"] == "lib0"
    assert m["j"]["options"][3]["about"] == "Cork, irish" and m["j"]["options"][3]["sample"] == "j_L2"
    assert m["j"]["options"][2]["sample"] is None  # no preview: no sample, still an option
    assert m["j"]["options"][3]["owner_id"] == "owner1"  # so it can be added to the account later
    assert samples["j_L2"] == b"ID3lib1" and lib.calls == [(8, {"accent": "irish"})]


def test_the_documents_library_key_is_opt_in_for_python_callers():
    """A caller that passes only a designer sees exactly what it saw before: no search, no network."""
    d = FakeDesigner(n=1)
    m = design_voice_options({"j": {"notes": NOTES, "library": {"accent": "irish"}}}, samples={}, designer=d)
    assert [o["option"] for o in m["j"]["options"]] == ["A"] and m["j"]["library"] is None
    with pytest.raises(VoiceDesignError, match="design=False searches the library only"):
        design_voice_options({"j": {"notes": NOTES}}, samples={}, designer=d, design=False)


def test_a_library_only_round_designs_nothing_and_needs_no_notes():
    lib, d = FakeLibrary(), FakeDesigner()
    m = design_voice_options({"p": {"provider": "elevenlabs"}}, samples={}, refs=["p"], designer=d,
                             library=lib, library_query="accent=irish,gender=male", design=False, library_limit=1)
    assert [o["option"] for o in m["p"]["options"]] == ["L1"] and d.calls == []
    assert m["p"]["design_model"] is None and lib.calls == [(1, {"accent": "irish", "gender": "male"})]
    with pytest.raises(VoiceDesignError, match="no library query"):
        design_voice_options({"p": {}}, samples={}, refs=["p"], designer=d, library=lib, design=False)
    with pytest.raises(VoiceDesignError, match="nothing to design from"):
        design_voice_options({"p": {}}, samples={}, designer=d, library=lib)


def test_a_library_pick_is_chosen_like_any_option(tmp_path):
    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(
        json.dumps({"provider": "elevenlabs", "notes": NOTES, "library": {"accent": "irish"}}), encoding="utf-8")
    d = FakeDesigner(n=1)
    m = design_project_voices(proj, designer=d, library=FakeLibrary())
    assert m["jerry"]["options"][2]["sample_path"] == "artifacts/voice_samples/jerry_L2.mp3"
    assert m["jerry"]["options"][1]["sample_path"] is None
    doc = choose_project_voice(proj, "jerry", "l2", designer=d, by="noel")
    assert doc["voice_id"] == "lib1" and doc["chosen_by"] == "noel"
    assert len([c for c in d.calls if c[0] == "save"]) == 1  # the designed option only, at design time


# -----------------------------------------------------------------------------
# The audition reel
# -----------------------------------------------------------------------------


def test_a_reel_is_the_lines_in_order_with_gaps_and_the_lines_cues():
    assert AUDITION_SAMPLE_RATE == EFFECT_SAMPLE_RATE
    tts, reels = FakeTTS(seconds=0.5), {}
    entry = {"options": [{"option": "A", "voice_id": "v1"}, {"option": "L1", "voice_id": "lib0"},
                         {"option": "B", "voice_id": None, "generated_voice_id": "g"}]}
    lines = [("Hi there.", {"model_id": "eleven_v3", "audio_tags": ["sad"]}), ("Bye.", {"model_id": "eleven_v3"})]
    said = []
    out = audition_voice_options(entry, lines, reels=reels, tts=tts, ref="j", options=["a", "L1"], announce=said.append)
    assert said == ["audition: 2 reel(s) x 2 line(s) = 4 request(s) to elevenlabs, 38 characters"]
    assert [r[1] for r in tts.requests] == ["v1", "v1", "lib0", "lib0"]
    assert tts.requests[0] == ("Hi there.", "v1", {"model_id": "eleven_v3", "audio_tags": ["sad"]})
    assert sorted(reels) == ["j_A", "j_L1"]
    assert abs(_seconds(reels["j_A"]) - (0.5 + 0.6) * 2) < 1e-6
    assert [o.get("audition") for o in out["options"]] == ["j_A", "j_L1", None]
    assert out["options"][0]["audition_lines"] == 2 and out["options"][0]["audition_key"]
    assert entry["options"][0].get("audition") is None  # the input is not mutated


def test_a_reel_on_record_is_never_made_twice(tmp_path):
    tts, reels = FakeTTS(), {}
    entry = {"options": [{"option": "A", "voice_id": "v1"}]}
    lines = [("Hi.", {"model_id": "eleven_v3"})]
    out = audition_voice_options(entry, lines, reels=reels, tts=tts, ref="j", announce=None)
    assert len(tts.requests) == 1
    again = audition_voice_options(out, lines, reels=reels, tts=tts, ref="j", announce=None)
    assert len(tts.requests) == 1 and again == out  # same key: nothing billed
    audition_voice_options(out, [("Hi!", {"model_id": "eleven_v3"})], reels=reels, tts=tts, ref="j", announce=None)
    assert len(tts.requests) == 2  # the line changed: made again
    audition_voice_options(out, lines, reels=reels, tts=tts, ref="j", announce=None, redo=True)
    assert len(tts.requests) == 3  # asked for


def test_everything_is_checked_before_the_first_request():
    tts = FakeTTS()
    entry = {"options": [{"option": "B", "voice_id": None, "generated_voice_id": "g"}]}
    with pytest.raises(VoiceDesignError, match="not saved voices"):
        audition_voice_options(entry, [("Hi.", {})], reels={}, tts=tts, ref="j", announce=None)
    with pytest.raises(VoiceDesignError, match="speaks no line"):
        audition_voice_options(entry, [], reels={}, tts=tts, ref="j", announce=None)
    with pytest.raises(VoiceDesignError, match=r"no option \['Z'\]"):
        audition_voice_options({"options": [{"option": "A", "voice_id": "v"}]}, [("Hi.", {})], reels={},
                               tts=tts, ref="j", options=["Z"], announce=None)
    with pytest.raises(VoiceDesignError, match="no options for 'j'"):
        audition_voice_options({"options": []}, [("Hi.", {})], reels={}, tts=tts, ref="j", announce=None)
    assert tts.requests == []
    assert plan_auditions({"options": [{"option": "A", "voice_id": "v"}]}, [("Hi.", {})], ref="j")[0].reel == "j_A"


def test_the_provider_is_asked_for_availability_before_the_first_request():
    class NoKey(FakeTTS):
        def check_available(self):
            raise RuntimeError("no key")

    tts = NoKey()
    with pytest.raises(RuntimeError, match="no key"):
        audition_voice_options({"options": [{"option": "A", "voice_id": "v"}]}, [("Hi.", {})], reels={},
                               tts=tts, ref="j", announce=None)
    assert tts.requests == []


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_a_stereo_or_resampled_line_is_converted_to_the_reels_format():
    class Stereo48(FakeTTS):
        def synthesize(self, text, voice_id, **kw):
            return SimpleNamespace(bytes_=_wav(0.2, rate=48000, channels=2), transcript=text)

    reels = {}
    audition_voice_options({"options": [{"option": "A", "voice_id": "v"}]}, [("Hi.", {})], reels=reels,
                           tts=Stereo48(), ref="j", announce=None)
    with wave.open(io.BytesIO(reels["j_A"]), "rb") as r:
        assert (r.getframerate(), r.getnchannels(), r.getsampwidth()) == (AUDITION_SAMPLE_RATE, 1, 2)
        assert abs(r.getnframes() / r.getframerate() - 0.8) < 0.02


def test_without_ffmpeg_a_non_wav_line_is_a_sentence_naming_the_reel(monkeypatch):
    monkeypatch.setattr("an.audio.effects.shutil.which", lambda name: None)

    class Mp3(FakeTTS):
        def synthesize(self, text, voice_id, **kw):
            return SimpleNamespace(bytes_=b"ID3not-really-mp3", transcript=text)

    with pytest.raises(VoiceDesignError, match="audition reel decodes the provider's audio with ffmpeg"):
        audition_voice_options({"options": [{"option": "A", "voice_id": "v"}]}, [("Hi.", {})], reels={},
                               tts=Mp3(), ref="j", announce=None)


def test_the_voices_effects_are_applied_to_the_reel():
    seen = []

    def fake_apply(audio, effects):
        seen.append(dict(effects))
        return audio

    import an.audio.effects as effects_module

    original = effects_module.apply_voice_effects
    effects_module.apply_voice_effects = fake_apply
    try:
        audition_voice_options({"options": [{"option": "A", "voice_id": "v"}]}, [("Hi.", {})], reels={},
                               tts=FakeTTS(), ref="j", announce=None, effects={"tempo": 1.1})
    finally:
        effects_module.apply_voice_effects = original
    assert seen == [{"tempo": 1.1}]


@pytest.mark.genre("cutout_animation")  # a line's [emotion] is the cut-out genre's sugar
def test_a_project_reel_speaks_the_voices_own_lines_with_the_films_options(tmp_path):
    root = _project(tmp_path, _shot("a", 10.0))
    shot = _shot("a", 10.0)
    shot.duration = 6.0
    shot.dialogue = [
        Dialogue(speaker="x", text="That is a big mountain.", voice_ref="jerry", direction=["excited"]),
        Dialogue(speaker="y", text="Yeah.", voice_ref="paul"),
        Dialogue(speaker="x", text="I'd say.", voice_ref="jerry", emotion="happy"),
    ]
    _set_shots(root, shot)
    mall = load(root).mall
    mall["voices"]["jerry"] = {"provider": "elevenlabs", "model_id": "eleven_v3", "voice_settings": {"stability": 0.5},
                               "notes": NOTES, "library": {"accent": "irish"}}
    mall["voices"]["paul"] = {"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES}
    design_project_voices(root, designer=FakeDesigner(n=1), library=FakeLibrary(n=1))
    tts = FakeTTS(seconds=0.25)
    said = []
    out = audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=said.append)
    assert said == ["audition: 1 reel(s) x 2 line(s) = 2 request(s) to elevenlabs, 49 characters"]
    assert [r[0] for r in tts.requests] == ["That is a big mountain.", "I'd say."]  # jerry's lines only, in order
    assert tts.requests[0][2] == {"model_id": "eleven_v3", "voice_settings": {"stability": 0.5},
                                  "audio_tags": ["excited"]}
    assert tts.requests[1][2]["audio_tags"] == ["happy"]
    reel = Path(root) / "artifacts" / "voice_auditions" / "jerry_L1.wav"
    assert reel.is_file() and abs(_seconds(reel.read_bytes()) - (0.25 + 0.6) * 2) < 1e-6
    assert out["jerry"]["options"][1]["audition_path"] == "artifacts/voice_auditions/jerry_L1.wav"
    manifest = json.loads((Path(root) / "artifacts" / "voice_options" / "jerry.json").read_text(encoding="utf-8"))
    assert manifest["options"][1]["audition_path"] == "artifacts/voice_auditions/jerry_L1.wav"
    assert manifest["options"][0].get("audition") is None
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None)
    assert len(tts.requests) == 2  # on record: nothing billed again
    with pytest.raises(VoiceDesignError, match="no options for 'ghost'"):
        audition_project_voices(root, ["ghost"], tts=tts, announce=None)


def test_a_bad_ref_is_refused_before_any_other_ref_is_billed(tmp_path):
    root = _project(tmp_path, _shot("a", 10.0))
    shot = _shot("a", 10.0)
    shot.duration = 6.0
    shot.dialogue = [Dialogue(speaker="x", text="Hi.", voice_ref="jerry"), Dialogue(speaker="y", text="Yo.", voice_ref="paul")]
    _set_shots(root, shot)
    mall = load(root).mall
    mall["voices"]["jerry"] = {"provider": "elevenlabs", "notes": NOTES}
    mall["voices"]["paul"] = {"provider": "elevenlabs", "notes": NOTES}
    design_project_voices(root, ["jerry"], designer=FakeDesigner(n=2))
    design_project_voices(root, ["paul"], designer=FakeDesigner(n=1))  # paul has no B
    tts = FakeTTS()
    with pytest.raises(VoiceDesignError, match=r"no option \['B'\] for 'paul'"):
        audition_project_voices(root, ["jerry", "paul"], tts=tts, options=["B"], announce=None)
    assert tts.requests == []  # jerry was not billed for paul's mistake


def test_a_reel_is_recorded_as_soon_as_it_is_made(tmp_path):
    root = _project(tmp_path, _shot("a", 10.0))
    shot = _shot("a", 10.0)
    shot.duration = 6.0
    shot.dialogue = [Dialogue(speaker="x", text="Hi.", voice_ref="jerry")]
    _set_shots(root, shot)
    load(root).mall["voices"]["jerry"] = {"provider": "elevenlabs", "notes": NOTES}
    design_project_voices(root, designer=FakeDesigner(n=2))

    class Flaky(FakeTTS):
        def synthesize(self, text, voice_id, **kw):
            if voice_id == "voice-gen1":
                raise RuntimeError("provider down")
            return super().synthesize(text, voice_id, **kw)

    with pytest.raises(RuntimeError, match="provider down"):
        audition_project_voices(root, ["jerry"], tts=Flaky(), announce=None)
    manifest = json.loads((Path(root) / "artifacts" / "voice_options" / "jerry.json").read_text(encoding="utf-8"))
    assert manifest["options"][0]["audition"] == "jerry_A" and manifest["options"][1].get("audition") is None
    tts = FakeTTS()
    audition_project_voices(root, ["jerry"], tts=tts, announce=None)
    assert [r[1] for r in tts.requests] == ["voice-gen1"]  # only the lost reel is made


def test_the_cli_verbs_dispatch():
    from an.audio.cli import _dispatch_funcs

    names = [f.__name__ for f in _dispatch_funcs]
    assert names.index("design") < names.index("audition") < names.index("choose") < names.index("cast")


def test_two_scenes_reels_of_one_voice_coexist_and_each_is_billed_once(tmp_path):
    """an#571: auditioning an option for scene.md and then scene.b.md left only the last
    reel (same file, same manifest field), and re-running the first re-billed it."""
    from an.ir.schema import Meta, SceneIR
    from an.stores import build_project_mall

    root = _project(tmp_path, _shot("a", 10.0))
    one = _shot("a", 10.0)
    one.duration = 4.0
    one.dialogue = [Dialogue(speaker="x", text="Line of the first scene.", voice_ref="jerry")]
    _set_shots(root, one)
    other = _shot("a", 10.0)
    other.duration = 4.0
    other.dialogue = [Dialogue(speaker="x", text="A line of scene b.", voice_ref="jerry")]
    build_project_mall(root, ensure=True, scene_file="scene.b.md")["scenes"]["main"] = SceneIR(
        meta=Meta(title="B"), timeline=[other]
    )
    mall = load(root).mall
    mall["voices"]["jerry"] = {"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES,
                               "library": {"accent": "irish"}}
    design_project_voices(root, designer=FakeDesigner(n=1), library=FakeLibrary(n=1))
    tts = FakeTTS(seconds=0.25)
    kw = {"tts": tts, "options": ["L1"], "announce": None}

    audition_project_voices(root, ["jerry"], **kw)
    audition_project_voices(root, ["jerry"], scene_file="scene.b.md", **kw)
    assert len(tts.requests) == 2
    first = Path(root) / "artifacts" / "voice_auditions" / "jerry_L1.wav"
    second = Path(root) / "artifacts" / "voice_auditions" / "scenes" / "scene.b" / "jerry_L1.wav"
    assert first.is_file() and second.is_file()
    assert [r[0] for r in tts.requests] == ["Line of the first scene.", "A line of scene b."]

    audition_project_voices(root, ["jerry"], **kw)  # either scene again: a hit, nothing billed
    audition_project_voices(root, ["jerry"], scene_file="scene.b.md", **kw)
    assert len(tts.requests) == 2

    manifest = json.loads((Path(root) / "artifacts" / "voice_options" / "jerry.json").read_text(encoding="utf-8"))
    option = manifest["options"][1]
    assert option["audition_path"] == "artifacts/voice_auditions/scenes/scene.b/jerry_L1.wav"  # the latest
    assert option["auditions"]["scene.md"]["audition_path"] == "artifacts/voice_auditions/jerry_L1.wav"
    assert option["auditions"]["scene.b.md"]["audition_path"] == option["audition_path"]


def test_a_scenes_audition_names_its_own_reel_not_the_latest_made(tmp_path, monkeypatch):
    """an#571 review: after scene b ran, re-running scene.md (a hit) must still say scene.md's reel."""
    from an.audio.cli import audition
    from an.ir.schema import Meta, SceneIR
    from an.stores import build_project_mall

    root = _project(tmp_path, _shot("a", 10.0))
    one = _shot("a", 10.0)
    one.dialogue = [Dialogue(speaker="x", text="First scene.", voice_ref="jerry")]
    _set_shots(root, one)
    other = _shot("a", 10.0)
    other.dialogue = [Dialogue(speaker="x", text="Scene b.", voice_ref="jerry")]
    build_project_mall(root, ensure=True, scene_file="scene.b.md")["scenes"]["main"] = SceneIR(
        meta=Meta(title="B"), timeline=[other]
    )
    mall = load(root).mall
    mall["voices"]["jerry"] = {"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES,
                               "library": {"accent": "irish"}}
    design_project_voices(root, designer=FakeDesigner(n=1), library=FakeLibrary(n=1))
    tts = FakeTTS(seconds=0.25)
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None)
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None, scene_file="scene.b.md")
    monkeypatch.setattr("an.audio.providers.make_tts", lambda name: tts)
    out = audition(str(root), voices="jerry", options="L1", scene="scene.md")
    assert out == "jerry L1: artifacts/voice_auditions/jerry_L1.wav"
    out = audition(str(root), voices="jerry", options="L1", scene="scene.b.md")
    assert out == "jerry L1: artifacts/voice_auditions/scenes/scene.b/jerry_L1.wav"
    assert len(tts.requests) == 2


def test_the_pre_per_scene_fields_are_only_the_default_scenes_while_they_are_its_own():
    from an.audio.voice_design import _scene_record
    from an.ir.sync import resolve_scene_file

    default = resolve_scene_file("/p", must_exist=False)
    other = resolve_scene_file("/p", "scene.b.md", must_exist=False)
    legacy = {"audition": "j_A", "audition_key": "k", "audition_path": "artifacts/voice_auditions/j_A.wav"}
    assert _scene_record(legacy, default)["audition_key"] == "k"
    assert _scene_record(legacy, other) is None  # a non-default scene never hits on it
    later = {**legacy, "audition_path": "artifacts/voice_auditions/scenes/scene.b/j_A.wav",
             "auditions": {"scene.b.md": {"audition": "j_A", "audition_key": "k2"}}}
    assert _scene_record(later, default) is None  # the top level is scene b's now


def test_a_manifest_from_before_per_scene_records_keeps_the_default_scenes_reel(tmp_path):
    """an#571 review: running scene b first must not make scene.md pay again for its old reel."""
    from an.ir.schema import Meta, SceneIR
    from an.stores import build_project_mall

    root = _project(tmp_path, _shot("a", 10.0))
    one = _shot("a", 10.0)
    one.dialogue = [Dialogue(speaker="x", text="First scene.", voice_ref="jerry")]
    _set_shots(root, one)
    other = _shot("a", 10.0)
    other.dialogue = [Dialogue(speaker="x", text="Scene b.", voice_ref="jerry")]
    build_project_mall(root, ensure=True, scene_file="scene.b.md")["scenes"]["main"] = SceneIR(
        meta=Meta(title="B"), timeline=[other]
    )
    mall = load(root).mall
    mall["voices"]["jerry"] = {"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES,
                               "library": {"accent": "irish"}}
    design_project_voices(root, designer=FakeDesigner(n=1), library=FakeLibrary(n=1))
    tts = FakeTTS(seconds=0.25)
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None)
    path = Path(root) / "artifacts" / "voice_options" / "jerry.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for o in manifest["options"]:
        o.pop("auditions", None)  # the manifest as an older build wrote it
    path.write_text(json.dumps(manifest), encoding="utf-8")
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None, scene_file="scene.b.md")
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None)
    assert len(tts.requests) == 2  # scene.md's reel from the old manifest was a hit


def _two_scene_project(tmp_path):
    """jerry speaks in scene.md and in scene.b.md; one library option, L1."""
    from an.ir.schema import Meta, SceneIR
    from an.stores import build_project_mall

    root = _project(tmp_path, _shot("a", 10.0))
    one = _shot("a", 10.0)
    one.dialogue = [Dialogue(speaker="x", text="First scene.", voice_ref="jerry")]
    _set_shots(root, one)
    other = _shot("a", 10.0)
    other.dialogue = [Dialogue(speaker="x", text="Scene b.", voice_ref="jerry")]
    build_project_mall(root, ensure=True, scene_file="scene.b.md")["scenes"]["main"] = SceneIR(
        meta=Meta(title="B"), timeline=[other]
    )
    load(root).mall["voices"]["jerry"] = {"provider": "elevenlabs", "model_id": "eleven_v3",
                                          "notes": NOTES, "library": {"accent": "irish"}}
    design_project_voices(root, designer=FakeDesigner(n=1), library=FakeLibrary(n=1))
    return root


def test_two_audition_runs_at_once_keep_each_others_reels(tmp_path):
    """an#587: scene.b.md's run records its reel while scene.md's run, which
    read the manifest before, is synthesizing. scene.md's record must not
    erase it, so a third run of scene.b.md bills nothing."""
    root = _two_scene_project(tmp_path)
    other = FakeTTS(seconds=0.25)

    class Interleaved(FakeTTS):
        def synthesize(self, text, voice_id, **kw):
            if not self.requests:  # the other terminal finishes meanwhile
                audition_project_voices(root, ["jerry"], tts=other, options=["L1"],
                                        announce=None, scene_file="scene.b.md")
            return super().synthesize(text, voice_id, **kw)

    audition_project_voices(root, ["jerry"], tts=Interleaved(seconds=0.25), options=["L1"],
                            announce=None)
    manifest = json.loads((Path(root) / "artifacts" / "voice_options" / "jerry.json")
                          .read_text(encoding="utf-8"))
    (l1,) = [o for o in manifest["options"] if o["option"] == "L1"]
    assert sorted(l1["auditions"]) == ["scene.b.md", "scene.md"]
    billed = len(other.requests)
    audition_project_voices(root, ["jerry"], tts=other, options=["L1"], announce=None,
                            scene_file="scene.b.md")
    assert len(other.requests) == billed


class _Redesigner(FakeDesigner):
    """A second design: new previews, so new voices."""

    def design_voice_previews(self, description, *, text=None, model_id=None):
        out = super().design_voice_previews(description, text=text, model_id=model_id)
        return [SimpleNamespace(**{**vars(p), "generated_voice_id": "re" + p.generated_voice_id}) for p in out]


class _Reversed(FakeLibrary):
    """The same voices, found in the other order (old L1's voice is L2 now)."""

    def search(self, *, limit, **filters):
        return list(reversed(super().search(limit=limit, **filters)))


def test_designing_again_keeps_the_reels_of_a_voice_it_finds_again(tmp_path):
    """an#588: the library finds the same voice for L1 again, so its reel (on
    disk, its content key unchanged) is not billed again; the designed option
    is a new voice, so its reel is."""
    root = _two_scene_project(tmp_path)
    tts = FakeTTS(seconds=0.25)
    audition_project_voices(root, ["jerry"], tts=tts, announce=None)  # A and L1
    billed = len(tts.requests)
    design_project_voices(root, designer=_Redesigner(n=1), library=FakeLibrary(n=1))
    manifest = json.loads((Path(root) / "artifacts" / "voice_options" / "jerry.json")
                          .read_text(encoding="utf-8"))
    (a,) = [o for o in manifest["options"] if o["option"] == "A"]
    assert "auditions" not in a and "audition" not in a  # another voice: no stale reel
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1"], announce=None)
    assert len(tts.requests) == billed
    audition_project_voices(root, ["jerry"], tts=tts, options=["A"], announce=None)
    assert len(tts.requests) == billed + 1


def test_a_voice_found_under_another_label_is_auditioned_again(tmp_path):
    """an#588: reels are kept by (label, voice), since the reel file is named
    by the label: old L1's voice found again as L2 is auditioned again, never
    handed L1's file, which L1's next reel would overwrite."""
    root = _two_scene_project(tmp_path)
    design_project_voices(root, designer=FakeDesigner(n=1), library=FakeLibrary(n=2))
    tts = FakeTTS(seconds=0.25)
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1", "L2"], announce=None)
    billed = len(tts.requests)
    design_project_voices(root, designer=FakeDesigner(n=1), library=_Reversed(n=2))
    audition_project_voices(root, ["jerry"], tts=tts, options=["L1", "L2"], announce=None)
    assert len(tts.requests) == billed + 2


def test_a_reel_recorded_while_a_design_runs_is_kept(tmp_path):
    """an#587 review: an audition records a reel while a re-design is billing;
    the design's write carries it from the manifest as stored then."""
    root = _two_scene_project(tmp_path)
    tts = FakeTTS(seconds=0.25)

    class Busy(_Redesigner):
        def design_voice_previews(self, description, *, text=None, model_id=None):
            audition_project_voices(root, ["jerry"], tts=tts, options=["L1"],
                                    announce=None, scene_file="scene.b.md")
            return super().design_voice_previews(description, text=text, model_id=model_id)

    design_project_voices(root, designer=Busy(n=1), library=FakeLibrary(n=1))
    manifest = json.loads((Path(root) / "artifacts" / "voice_options" / "jerry.json")
                          .read_text(encoding="utf-8"))
    (l1,) = [o for o in manifest["options"] if o["option"] == "L1"]
    assert "scene.b.md" in l1.get("auditions", {})


def test_a_reel_made_for_a_voice_designed_away_meanwhile_is_not_kept(tmp_path):
    """an#649: run A auditions option A; meanwhile A is designed again (another
    voice) and run B auditions the new voice. A's reel is not written over B's
    file (which the manifest says is current), and A is told."""
    from an.audio.voice_design import VoiceDesignWarning

    root = _two_scene_project(tmp_path)
    reel = Path(root) / "artifacts" / "voice_auditions" / "jerry_A.wav"
    b, made_by_b = FakeTTS(seconds=0.5), []

    class Interleaved(FakeTTS):
        def synthesize(self, text, voice_id, **kw):
            if not self.requests:  # the other terminal re-designs and auditions A
                design_project_voices(root, designer=_Redesigner(n=1), library=FakeLibrary(n=1))
                audition_project_voices(root, ["jerry"], tts=b, options=["A"], announce=None)
                made_by_b.append(reel.read_bytes())
            return super().synthesize(text, voice_id, **kw)

    with pytest.warns(VoiceDesignWarning, match="designed again"):
        audition_project_voices(root, ["jerry"], tts=Interleaved(seconds=0.25),
                                options=["A"], announce=None)
    assert made_by_b and reel.read_bytes() == made_by_b[0]
    billed = len(b.requests)
    audition_project_voices(root, ["jerry"], tts=b, options=["A"], announce=None)
    assert len(b.requests) == billed  # B's reel is on record and current
