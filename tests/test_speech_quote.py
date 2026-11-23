"""``an.audio.speech_quote``: what a scene's speech bills, decided by each
provider's own ``billed`` declaration, for the voices the scene actually speaks."""

from types import SimpleNamespace as NS

from an.audio import speech_quote


def _scene(*lines):
    shot = NS(
        entities=(NS(kind="character", id="maya", ref="maya", overrides={}),),
        dialogue=list(lines),
    )
    return NS(timeline=[shot])


def _line(voice_ref=None, speaker="maya"):
    return NS(voice_ref=voice_ref, speaker=speaker, text="Hello there.")


def test_a_voice_the_scene_never_speaks_does_not_make_it_paid():
    mall = {"voices": {"narrator": {"provider": "offline"}, "unused": {"provider": "elevenlabs"}}}
    assert speech_quote(_scene(_line("narrator")), mall) == 0.0


def test_a_character_bound_paid_voice_is_unknown_never_free():
    mall = {
        "characters": {"maya": {"voice_ref": "maya-warm"}},
        "voices": {"maya-warm": {"provider": "ElevenLabs", "voice_id": "xyz"}},
    }
    assert speech_quote(_scene(_line()), mall) is None


def test_free_providers_and_an_unknown_name_speak_for_nothing():
    # an unknown provider name is spoken by the offline default, as the render does
    mall = {"voices": {"a": {"provider": "mac_say"}, "b": {}, "c": {"provider": "nope"}}}
    scene = _scene(_line("a"), _line("b"), _line("c"))
    assert speech_quote(scene, mall) == 0.0


def test_a_provider_that_does_not_declare_billed_counts_as_billed():
    undeclared = NS(name="mystery")
    assert speech_quote(_scene(_line("x")), {}, tts=undeclared) is None


def test_no_dialogue_is_free():
    assert speech_quote(NS(timeline=[NS(entities=(), dialogue=[])]), {}) == 0.0
