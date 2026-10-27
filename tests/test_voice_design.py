"""Voice design from a voice document's notes, and the writer's choice (an voices design/choose)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from an.audio.voice_design import (
    VoiceDesignError,
    choose_project_voice,
    choose_voice_option,
    design_project_voices,
    design_voice_options,
)

NOTES = "A man in his early 50s, rural Yorkshire accent, warm and unhurried."


class FakeDesigner:
    """voxy's two designer methods, recording the calls; nothing is billed."""

    def __init__(self, n=3):
        self.n, self.calls = n, []

    def design_voice_previews(self, description, *, text=None, model_id=None):
        self.calls.append(("previews", description, text, model_id))
        return [
            SimpleNamespace(
                generated_voice_id=f"gen{i}", audio=b"ID3" + bytes([i]), duration_s=2.0
            )
            for i in range(self.n)
        ]

    def design_voice(self, description, *, preview, name):
        gid = getattr(preview, "generated_voice_id", preview)
        self.calls.append(("save", gid, name))
        return SimpleNamespace(segment=f"voice-{gid}")


def test_persist_saves_every_option():
    d, samples = FakeDesigner(), {}
    m = design_voice_options(
        {"j": {"notes": NOTES, "sample_text": "x" * 120}}, samples=samples, designer=d
    )
    assert [o["voice_id"] for o in m["j"]["options"]] == [
        "voice-gen0",
        "voice-gen1",
        "voice-gen2",
    ]
    assert d.calls[0] == ("previews", NOTES, "x" * 120, "eleven_ttv_v3")
    assert samples["j_C"] == b"ID3\x02"


def test_not_persisted_option_is_saved_when_chosen():
    d = FakeDesigner()
    m = design_voice_options(
        {"j": {"notes": NOTES}}, samples={}, designer=d, persist=False
    )
    assert all(o["voice_id"] is None for o in m["j"]["options"])
    assert not [c for c in d.calls if c[0] == "save"]
    assert choose_voice_option(m["j"], "b", ref="j", designer=d) == "voice-gen1"
    with pytest.raises(VoiceDesignError, match="no option 'Z'"):
        choose_voice_option(m["j"], "Z", designer=d)


def test_named_voice_without_notes_is_refused_before_any_call():
    d = FakeDesigner()
    with pytest.raises(VoiceDesignError, match="no 'notes'"):
        design_voice_options(
            {"j": {"provider": "elevenlabs"}}, samples={}, refs=["j"], designer=d
        )
    with pytest.raises(VoiceDesignError, match="characters"):
        design_voice_options(
            {"j": {"notes": "short"}}, samples={}, refs=["j"], designer=d
        )
    assert d.calls == []


def test_project_round_trip(tmp_path):
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(
        json.dumps({"provider": "elevenlabs", "model_id": "eleven_v3", "notes": NOTES}),
        encoding="utf-8",
    )
    d = FakeDesigner(n=2)
    manifest = design_project_voices(proj, designer=d)
    assert (
        proj / "artifacts" / "voice_samples" / "jerry_A.mp3"
    ).read_bytes() == b"ID3\x00"
    assert (
        json.loads(
            (proj / "artifacts" / "voice_options" / "jerry.json").read_text(
                encoding="utf-8"
            )
        )["options"][1]["sample_path"]
        == "artifacts/voice_samples/jerry_B.mp3"
    )
    assert manifest["jerry"]["name_prefix"] == "p"
    doc = choose_project_voice(
        proj, "jerry", "B", designer=d, by="noel", at="2026-10-20T22:00:00+00:00"
    )
    assert doc == {
        "provider": "elevenlabs",
        "model_id": "eleven_v3",
        "notes": NOTES,
        "voice_id": "voice-gen1",
        "chosen_by": "noel",
        "chosen_at": "2026-10-20T22:00:00+00:00",
    }
    assert (
        json.loads(
            (proj / "assets" / "voices" / "jerry.json").read_text(encoding="utf-8")
        )["voice_id"]
        == "voice-gen1"
    )
    assert json.loads(
        (proj / "artifacts" / "voice_options" / "jerry.json").read_text(
            encoding="utf-8"
        )
    )["chosen"] == {
        "option": "B",
        "voice_id": "voice-gen1",
        "chosen_by": "noel",
        "chosen_at": "2026-10-20T22:00:00+00:00",
    }


def test_elevenlabs_designer_calls_the_sdk_shape():
    import base64

    from an.audio.voice_design import ElevenLabsVoiceDesigner

    calls = []

    class TTV:
        def design(self, **kw):
            calls.append(("design", kw))
            return SimpleNamespace(
                previews=[
                    SimpleNamespace(
                        generated_voice_id="g",
                        audio_base_64=base64.b64encode(b"ID3").decode(),
                        duration_secs=1.5,
                    )
                ]
            )

        def create(self, **kw):
            calls.append(("create", kw))
            return SimpleNamespace(voice_id="v1")

    d = ElevenLabsVoiceDesigner(
        api_key="k", client_factory=lambda key: SimpleNamespace(text_to_voice=TTV())
    )
    [p] = d.design_voice_previews(NOTES, text=None)
    assert (p.generated_voice_id, p.audio, p.duration_s) == ("g", b"ID3", 1.5)
    assert calls[0] == (
        "design",
        {
            "voice_description": NOTES,
            "model_id": "eleven_ttv_v3",
            "auto_generate_text": True,
            "request_options": {"timeout_in_seconds": 120},
        },
    )
    assert d.design_voice(NOTES, preview=p, name="n").segment == "v1"
    assert calls[1][1]["generated_voice_id"] == "g"


def _voice_project(tmp_path, doc):
    from an.project import init

    proj = tmp_path / "p"
    init(str(proj))
    (proj / "assets" / "voices").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "voices" / "jerry.json").write_text(
        json.dumps(doc), encoding="utf-8"
    )
    return proj


def _manifest(proj):
    return json.loads(
        (proj / "artifacts" / "voice_options" / "jerry.json").read_text(
            encoding="utf-8"
        )
    )


def test_choosing_again_retires_the_replaced_designed_voice(tmp_path):
    """an#549: the choose step a connector shares (`choose_in_entry`). Choosing
    another option retires the voice it replaces (named in `retired`, never
    deleted; its option no longer names it), choosing it back saves it anew
    from its preview, and the same choice again keeps its first `chosen_at`.
    The voice document keeps its notes and loses `provisional`."""
    proj = _voice_project(tmp_path, {"notes": NOTES, "provisional": True})
    d = FakeDesigner(n=2)
    design_project_voices(proj, designer=d, persist=False)
    choose_project_voice(proj, "jerry", "A", designer=d, by="noel", at="t1")
    doc = choose_project_voice(proj, "jerry", "B", designer=d, by="noel", at="t2")
    assert doc["notes"] == NOTES and "provisional" not in doc
    m = _manifest(proj)
    assert m["retired"] == [
        {"voice_id": "voice-gen0", "option": "A", "name_prefix": "p"}
    ]
    assert [o["voice_id"] for o in m["options"]] == [None, "voice-gen1"]
    assert (
        choose_project_voice(proj, "jerry", "B", designer=d, by="noel")["chosen_at"]
        == "t2"
    )
    saves = len([c for c in d.calls if c[0] == "save"])
    choose_project_voice(proj, "jerry", "A", designer=d, by="noel")
    assert len([c for c in d.calls if c[0] == "save"]) == saves + 1, (
        "saved anew, not taken back"
    )


def test_with_every_option_persisted_no_voice_is_retired_and_going_back_saves_nothing(
    tmp_path,
):
    """`an voices design` saves every option (persist=True): those voices stay
    named on their options, so going back to the first pick needs no preview
    (it may have expired) and saves nothing."""
    proj = _voice_project(tmp_path, {"notes": NOTES})
    d = FakeDesigner(n=3)
    design_project_voices(proj, designer=d)
    choose_project_voice(proj, "jerry", "A", designer=d, by="noel")
    choose_project_voice(proj, "jerry", "B", designer=d, by="noel")
    m = _manifest(proj)
    assert [o["voice_id"] for o in m["options"]] == [
        "voice-gen0",
        "voice-gen1",
        "voice-gen2",
    ]
    assert "retired" not in m
    saves = len([c for c in d.calls if c[0] == "save"])
    assert (
        choose_project_voice(proj, "jerry", "A", designer=d, by="noel")["voice_id"]
        == "voice-gen0"
    )
    assert len([c for c in d.calls if c[0] == "save"]) == saves


def test_a_voice_this_manifest_did_not_save_is_never_retired():
    """A library option's voice is another account's, and a voice cast by hand
    the writer's: replacing either retires nothing and clears nothing."""
    from an.audio.voice_design import choose_in_entry

    entry = {
        "options": [
            {"option": "A", "generated_voice_id": "gA", "voice_id": "vA"},
            {"option": "L1", "kind": "library", "voice_id": "pub1"},
        ]
    }
    choose_in_entry(entry, "L1", by="noel")
    choice = choose_in_entry(entry, "A", by="noel")
    assert (choice.previous, choice.retired) == (
        "pub1",
        None,
    ) and "retired" not in entry
    assert entry["options"][1]["voice_id"] == "pub1"
    entry["chosen"] = {
        "option": None,
        "voice_id": "my-clone",
        "chosen_by": "noel",
        "chosen_at": "t",
    }
    choice = choose_in_entry(entry, "A", by="noel")
    assert (choice.previous, choice.retired) == (
        "my-clone",
        None,
    ) and "retired" not in entry


def test_a_retired_voice_keeps_the_prefix_it_was_saved_under():
    """an#618: a fork chooses in its source's manifest under its own prefix
    (``name_prefix=``), leaving the entry's alone. The voice it replaces is
    retired under the SOURCE's prefix (a fork never gains the right to free
    it), the voice it saves is named and later retired under the fork's, and a
    re-design ledgers each under its own."""
    from an.audio.voice_design import choose_in_entry, merge_redesign

    d = FakeDesigner(n=3)
    entry = design_voice_options(
        {"j": {"notes": NOTES}}, samples={}, designer=d, persist=False,
        name_prefix="src",
    )["j"]  # fmt: skip
    choose_in_entry(entry, "A", by="noel", designer=d, ref="j")
    choice = choose_in_entry(
        entry, "B", by="ann", designer=d, ref="j", name_prefix="fork"
    )
    assert choice.retired == "voice-gen0" and entry["name_prefix"] == "src"
    assert entry["retired"] == [
        {"voice_id": "voice-gen0", "option": "A", "name_prefix": "src"}
    ]
    assert d.calls[-1] == ("save", "gen1", "fork j B")
    assert entry["options"][1]["saved_under"] == "fork"
    choose_in_entry(entry, "C", by="ann", designer=d, ref="j", name_prefix="fork")
    assert entry["retired"][-1] == {
        "voice_id": "voice-gen1", "option": "B", "name_prefix": "fork",
    }  # fmt: skip
    assert "saved_under" not in entry["options"][1], "cleared with its voice"
    redesigned = merge_redesign(
        entry, {"notes": NOTES, "options": [], "name_prefix": "src"}
    )
    assert redesigned["chosen"]["saved_under"] == "fork"
    redesigned["options"] = [{"option": "A", "generated_voice_id": "x"}]
    choose_in_entry(redesigned, "A", by="ann", designer=d, ref="j")
    assert redesigned["retired"][-1] == {
        "voice_id": "voice-gen2", "option": None, "name_prefix": "fork",
    }  # fmt: skip


def test_a_damaged_retired_ledger_is_refused_before_anything_is_chosen():
    from an.audio.voice_design import VoiceDesignError, choose_in_entry

    entry = {
        "options": [
            {"option": "A", "voice_id": "vA"},
            {"option": "B", "voice_id": "vB"},
        ],
        "chosen": {"option": "A", "voice_id": "vA"},
        "retired": {},
    }
    with pytest.raises(VoiceDesignError, match="damaged"):
        choose_in_entry(entry, "B", by="noel")


def test_designing_again_keeps_the_choice_and_retires_what_the_old_design_saved(
    tmp_path,
):
    """an#604: design (every option saved), choose B, design again. The new
    manifest keeps `chosen` (its option cleared: the new B is another voice;
    marked to be retired when replaced) and ledgers every OTHER voice the old
    design saved, so none is orphaned. Choosing the new B then retires the old
    chosen voice, once."""
    proj = _voice_project(tmp_path, {"notes": NOTES})
    first = FakeDesigner(n=3)
    design_project_voices(proj, designer=first)
    choose_project_voice(proj, "jerry", "B", designer=first, by="noel", at="t1")
    again = FakeDesigner(n=3)
    again.design_voice = lambda description, *, preview, name: SimpleNamespace(
        segment=f"new-{getattr(preview, 'generated_voice_id', preview)}"
    )
    design_project_voices(proj, designer=again)
    m = _manifest(proj)
    assert m["chosen"] == {
        "option": None, "voice_id": "voice-gen1", "chosen_by": "noel",
        "chosen_at": "t1", "retire_on_replace": True, "saved_under": "p",
    }  # fmt: skip
    assert sorted(r["voice_id"] for r in m["retired"]) == ["voice-gen0", "voice-gen2"]
    from an.audio.voice_design import choose_in_entry

    entry = _manifest(proj)
    choice = choose_in_entry(entry, "B", by="noel", designer=again)
    assert (choice.previous, choice.retired) == ("voice-gen1", "voice-gen1")
    doc = choose_project_voice(proj, "jerry", "B", designer=again, by="noel")
    assert doc["voice_id"] == "new-gen1"
    assert sorted(r["voice_id"] for r in _manifest(proj)["retired"]) == [
        "voice-gen0", "voice-gen1", "voice-gen2",
    ]  # fmt: skip


def test_a_damaged_manifest_is_refused_before_a_re_design_bills_anything(tmp_path):
    from an.audio.voice_design import VoiceDesignError

    proj = _voice_project(tmp_path, {"notes": NOTES})
    design_project_voices(proj, designer=FakeDesigner(n=2))
    path = proj / "artifacts" / "voice_options" / "jerry.json"
    for damage in (
        "{not json",
        json.dumps({"options": [], "retired": {"voice_id": "x"}}),
    ):
        path.write_text(damage, encoding="utf-8")
        d = FakeDesigner(n=2)
        with pytest.raises(VoiceDesignError, match="damaged"):
            design_project_voices(proj, designer=d)
        assert d.calls == [], "nothing designed, nothing saved"


def test_a_voice_a_voice_document_names_is_never_retired_by_a_re_design(tmp_path):
    """Another character cast by hand to one of jerry's option voices."""
    from an.audio.voice_design import cast_project_voice

    proj = _voice_project(tmp_path, {"notes": NOTES})
    (proj / "assets" / "voices" / "tom.json").write_text(
        json.dumps({"provider": "elevenlabs"}), encoding="utf-8"
    )
    design_project_voices(proj, designer=FakeDesigner(n=2), refs=["jerry"])
    cast_project_voice(proj, "tom", "voice-gen0", by="noel")
    again = FakeDesigner(n=2)
    again.design_voice = lambda description, *, preview, name: SimpleNamespace(
        segment="new"
    )
    design_project_voices(proj, designer=again, refs=["jerry"])
    assert [r["voice_id"] for r in _manifest(proj)["retired"]] == ["voice-gen1"]


def _redesigned(tmp_path):
    """Design jerry, choose B, design again (every option saved both times)."""
    proj = _voice_project(tmp_path, {"notes": NOTES})
    (proj / "assets" / "voices" / "tom.json").write_text(
        json.dumps({"provider": "elevenlabs"}), encoding="utf-8"
    )
    design_project_voices(proj, designer=FakeDesigner(n=3), refs=["jerry"])
    choose_project_voice(proj, "jerry", "B", designer=None, by="noel", at="t1")
    again = FakeDesigner(n=3)
    again.design_voice = lambda description, *, preview, name: SimpleNamespace(
        segment=f"new-{getattr(preview, 'generated_voice_id', preview)}"
    )
    return proj, again


def test_a_carried_choice_another_character_speaks_is_not_retired(tmp_path):
    from an.audio.voice_design import cast_project_voice

    proj, again = _redesigned(tmp_path)
    cast_project_voice(proj, "tom", "voice-gen1", by="noel")  # tom speaks jerry's old B
    design_project_voices(proj, designer=again, refs=["jerry"])
    choose_project_voice(proj, "jerry", "A", designer=again, by="noel")
    assert "voice-gen1" not in [r["voice_id"] for r in _manifest(proj)["retired"]]


def test_casting_by_hand_over_a_carried_choice_retires_it(tmp_path):
    from an.audio.voice_design import cast_project_voice

    proj, again = _redesigned(tmp_path)
    design_project_voices(proj, designer=again, refs=["jerry"])
    cast_project_voice(proj, "jerry", "HAND", by="noel")
    m = _manifest(proj)
    assert "voice-gen1" in [r["voice_id"] for r in m["retired"]]
    assert m["chosen"]["voice_id"] == "HAND" and "retire_on_replace" not in m["chosen"]


@pytest.mark.parametrize(
    "damage",
    [
        {"options": ["x"]},
        {"options": [], "retired": ["x"]},
        {"options": [{"voice_id": [1]}]},
        {"options": [], "chosen": "B"},
    ],
)
def test_a_manifest_damaged_inside_is_refused_before_anything_is_billed(
    tmp_path, damage
):
    from an.audio.voice_design import VoiceDesignError

    proj = _voice_project(tmp_path, {"notes": NOTES})
    (proj / "artifacts" / "voice_options").mkdir(parents=True, exist_ok=True)
    (proj / "artifacts" / "voice_options" / "jerry.json").write_text(
        json.dumps(damage), encoding="utf-8"
    )
    d = FakeDesigner(n=2)
    with pytest.raises(VoiceDesignError, match="damaged"):
        design_project_voices(proj, designer=d)
    assert d.calls == []
