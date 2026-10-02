"""The voice document decides who speaks a line; ``tts`` is an override (an#305).

The third end-user test rendered a project whose voices name ElevenLabs with a
plain ``an render`` and got every line re-made by the silent offline voice, with
no warning. These tests pin the rule that replaced it:

- with no ``tts``, a line is spoken by its voice's declared ``provider``, and a
  voice that names none by the offline provider — keys unchanged, byte for byte;
- a paid provider chosen that way announces its cost before the first request,
  is never billed for a cached line, and needs no key when everything is cached;
- a line spoken by another provider than its voice declares (an override, or a
  provider ``an`` has no TTS for) is a render finding, and an error under
  ``strict_assets`` before anything is synthesized.

No test reaches the API: ElevenLabs is built with a recording fake client.
"""

from __future__ import annotations

import io
import math
import wave

import numpy as np
import pytest

from an.audio.elevenlabs_tts import ElevenLabsTTS
from an.audio.pipeline import (
    AudioPipelineError,
    VoiceStandInError,
    VoiceStandInWarning,
    audio_key,
    produce_audio_for_scene,
    tts_chooser,
)
from an.audio.offline_lipsync import OfflineLipSync
from an.ir.schema import Dialogue
from an.project import load
from an.render import render_findings, render_project
from tests.test_shot_cache import (  # noqa: F401 — the fixture, by name
    _project,
    _set_shots,
    _shot,
    fake_render,
)

TEXT = "hello there"
EL_VOICE = {"provider": "elevenlabs", "voice_id": "TX3"}
RATE = 16000


def _tone(seconds: float) -> bytes:
    t = np.arange(int(RATE * seconds)) / RATE
    pcm = (0.3 * 32767 * np.sin(2 * math.pi * 150.0 * t)).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return buf.getvalue()


class _Client:
    """Stands in for the ElevenLabs SDK client: records, never calls out."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.text_to_speech = self

    def convert(self, **request):
        self.requests.append(request)
        yield _tone(0.5)


@pytest.fixture
def eleven(monkeypatch):
    """`make_tts("elevenlabs")` builds ElevenLabs on a recording fake client."""
    import an.audio.providers as providers

    client = _Client()
    monkeypatch.setitem(
        providers.TTS_FACTORIES,
        "elevenlabs",
        lambda: ElevenLabsTTS(api_key="test-key", client_factory=lambda _k: client),
    )
    return client


def _speaking(tmp_path, voice: dict | None, *, voice_ref: str = "bob"):
    root = _project(tmp_path, _shot("a", 10.0))
    shot = _shot("a", 10.0)
    shot.duration = 3.0
    shot.dialogue = [Dialogue(speaker="x", text=TEXT, voice_ref=voice_ref)]
    _set_shots(root, shot)
    if voice is not None:
        load(root).mall["voices"][voice_ref] = voice
    return root


def _line(root):
    return load(root).scene.timeline[0].dialogue[0]


def _render(root, **kw):
    kw.setdefault("incremental", False)
    kw.setdefault("echo_warnings", False)
    return render_project(root, **kw)


# -----------------------------------------------------------------------------
# The voice decides
# -----------------------------------------------------------------------------


def test_a_voice_that_names_elevenlabs_is_spoken_by_it_without_a_flag(
    tmp_path, fake_render, eleven, capsys
):
    root = _speaking(tmp_path, EL_VOICE)
    _render(root)
    assert [r["voice_id"] for r in eleven.requests] == ["TX3"]
    assert _line(root).audio_ref == audio_key(
        TEXT, "bob", "elevenlabs", provider_voice="TX3"
    )
    # The cost is said before the request, with the free way out.
    err = capsys.readouterr().err
    assert f"elevenlabs: 1 request(s) for 1 line(s), {len(TEXT)} billed characters" in err
    assert "the voices name elevenlabs" in err and "--tts offline" in err
    assert render_findings(root) == []  # no stand-in: the voice got its provider


def test_a_cached_line_is_never_billed_and_needs_no_key(
    tmp_path, fake_render, eleven, monkeypatch, capsys
):
    """Rendered once with `--tts elevenlabs`: a plain render reads the same keys."""
    import an.audio.providers as providers

    root = _speaking(tmp_path, EL_VOICE)
    _render(root, tts="elevenlabs")
    assert len(eleven.requests) == 1
    capsys.readouterr()
    keyless = ElevenLabsTTS(api_key=None, client_factory=lambda _k: eleven)
    keyless.api_key = None  # whatever this shell exports
    monkeypatch.setitem(providers.TTS_FACTORIES, "elevenlabs", lambda: keyless)
    _render(root)  # the scene is stamped: nothing to synthesize
    _render(root, force_render=True)
    assert len(eleven.requests) == 1
    assert "request(s)" not in capsys.readouterr().err


def test_an_md_edit_restamps_from_the_cache_without_a_request(
    tmp_path, fake_render, eleven
):
    root = _speaking(tmp_path, EL_VOICE)
    _render(root)
    project = load(root)
    scene = project.scene
    line = scene.timeline[0].dialogue[0]
    line.audio_ref = line.viseme_ref = line.viseme_track = line.duration = None
    project.mall["scenes"]["main"] = scene
    _render(root)
    assert len(eleven.requests) == 1


def test_a_missing_key_fails_before_any_request_and_names_the_way_out(
    tmp_path, fake_render, monkeypatch
):
    import an.audio.providers as providers

    client = _Client()
    keyless = ElevenLabsTTS(client_factory=lambda _k: client)
    keyless.api_key = None
    monkeypatch.setitem(providers.TTS_FACTORIES, "elevenlabs", lambda: keyless)
    root = _speaking(tmp_path, EL_VOICE)
    with pytest.raises(AudioPipelineError, match="--tts offline") as e:
        _render(root)
    assert "API key" in str(e.value)
    assert client.requests == [] and list(load(root).mall["audio"]) == []


def test_voices_that_name_no_provider_keep_every_key(tmp_path, fake_render):
    """Byte identity: the offline keys of before an#305, and no finding."""
    root = _speaking(tmp_path, {"voice_id": "Junior"})
    _render(root)
    assert _line(root).audio_ref == audio_key(TEXT, "bob", "offline", provider_voice="Junior")
    plain = load(root).mall["audio"][_line(root).audio_ref]
    other = _speaking(tmp_path / "o", {"voice_id": "Junior"})
    _render(other, tts="offline")
    assert _line(other).audio_ref == _line(root).audio_ref
    assert load(other).mall["audio"][_line(other).audio_ref] == plain
    assert render_findings(root) == []


def test_the_chooser_builds_one_provider_per_name():
    built: list[str] = []

    def make(name):
        built.append(name)
        from an.audio.providers import make_tts

        return make_tts(name)

    mall = {"voices": {"a": {"provider": "mac_say"}, "b": {"provider": "MAC_SAY"}}}
    choose = tts_chooser(None, mall, make=make)
    assert choose("a") is choose("b") and choose("c") is choose("d")
    assert built == ["mac_say", "offline"]


# -----------------------------------------------------------------------------
# Stand-ins are said, and refused under strict
# -----------------------------------------------------------------------------


def test_an_override_to_the_silent_voice_is_a_finding(tmp_path, fake_render):
    root = _speaking(tmp_path, EL_VOICE)
    _render(root, tts="offline")
    (f,) = render_findings(root)
    assert f.severity == "warning"
    assert "voice 'bob' declares provider 'elevenlabs'" in f.description
    assert "SILENT" in f.description and "Drop `--tts`" in f.description


def test_an_override_to_the_silent_voice_is_refused_under_strict(tmp_path, fake_render):
    root = _speaking(tmp_path, EL_VOICE)
    with pytest.raises(VoiceStandInError, match="SILENT"):
        _render(root, tts="offline", strict_assets=True)
    assert list(load(root).mall["audio"]) == []  # refused before synthesis


def test_a_provider_an_does_not_know_falls_back_loudly(tmp_path, fake_render):
    root = _speaking(tmp_path, {"provider": "eleven_labs", "voice_id": "TX3"})
    _render(root)
    (f,) = render_findings(root)
    assert "no TTS provider named 'eleven_labs'" in f.description
    assert "elevenlabs" in f.description and "SILENT" in f.description
    with pytest.raises(VoiceStandInError):
        _render(root, strict_assets=True)


def test_the_pipeline_warns_a_python_caller_too():
    from an.ir.schema import SceneIR, Shot

    scene = SceneIR(
        timeline=[Shot(id="s", dialogue=[Dialogue(speaker="x", text="hi", voice_ref="bob")])]
    )
    mall = {"voices": {"bob": EL_VOICE}, "audio": {}, "visemes": {}}
    with pytest.warns(VoiceStandInWarning, match="SILENT"):
        produce_audio_for_scene(
            scene, mall, tts="offline", lipsync=OfflineLipSync(), announce=None
        )


# -----------------------------------------------------------------------------
# What a render records
# -----------------------------------------------------------------------------


def test_a_plain_render_records_each_voices_own_provider(tmp_path, fake_render):
    from an.build import ShotCache
    from an.build.shot_cache import ROOT_PREFIX
    from tests.test_shot_cache import _env

    root = _speaking(tmp_path, None)
    render_project(root, incremental=ShotCache(environment=_env()), echo_warnings=False)
    store = load(root).mall["shot_cache"]
    (rid,) = [k for k in store if k.startswith(ROOT_PREFIX)]
    assert store[rid].render_provenance["profile"]["tts"] == "voice"


def test_the_cli_defaults_to_each_voices_provider():
    import inspect

    from an.tools import render

    assert inspect.signature(render).parameters["tts"].default == ""
