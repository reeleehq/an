"""A ``play`` without ``duration`` occupies its NATURAL length in a ``sequence``.

Before, every duration-less play was zero-width there, so
``sequence(play(a, "hop"), play(a, "nod"))`` started both at 0 and they
overlapped. The rule now (one resolver, `an.characters.play.play_extent`, which
`flatten` is handed by the compiler and by `an validate`):

- an explicit ``duration`` is its own extent;
- a motion preset occupies its own length divided by ``speed``;
- a NON-looping descriptor animation occupies its ``duration`` over ``speed``;
- a LOOPING one (``loop`` true, or the animation's own) runs to the shot end
  and occupies ZERO — a sibling after it must not wait for the shot end;
- a play that cannot resolve occupies zero (the verdict is `play_problems`'s;
  `flatten` never raises for it).

MUTATION: make `play_extent` return ``0.0`` for the preset source — the
sequence tests go red; return ``anim.duration`` for a looping animation — the
loop test goes red.
"""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import compile_shot
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.characters.play import play_extent, play_extent_for
from an.ir.compose import (
    delay,
    duration_of,
    flatten,
    parallel,
    play,
    sequence,
    tween,
)
from an.ir.schema import AssetRef, Meta, PlayAction, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.motion import hop, nod
from an.stores.characters import CharactersStore

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "characters"


def _starts(action, **kw):
    return [round(f.start, 6) for f in flatten(action, **kw)]


def test_two_presets_in_a_sequence_run_one_after_the_other():
    assert _starts(sequence(play("a", "hop"), play("a", "nod"))) == [0.0, 0.5]


def test_the_extent_is_the_macro_s_own_length():
    """Not a separate constant: the extent IS what the macro's tree sums to."""
    assert duration_of(sequence(play("a", "hop"))) == pytest.approx(duration_of(hop("a")))
    assert duration_of(sequence(play("a", "nod"))) == pytest.approx(duration_of(nod("a")))


def test_speed_divides_and_duration_stretches():
    assert _starts(sequence(play("a", "hop", speed=2.0), play("a", "nod"))) == [0.0, 0.25]
    assert _starts(sequence(play("a", "hop", duration=2.0), play("a", "nod"))) == [0.0, 2.0]


def test_args_change_the_extent():
    """`shake`'s length follows its own `cycles`/`duration` parameters."""
    short = sequence(play("a", "shake", args={"duration": 0.2}), play("a", "nod"))
    assert _starts(short) == [0.0, 0.2]


def test_parallel_takes_the_longest_and_a_loop_multiplies():
    assert duration_of(parallel(play("a", "hop"), play("a", "nod"))) == pytest.approx(0.5)
    assert duration_of(sequence(delay(1.0), play("a", "hop"))) == pytest.approx(1.5)


def test_an_unresolvable_name_is_zero_width_and_never_raises():
    assert _starts(sequence(play("a", "no_such_thing"), play("a", "nod"))) == [0.0, 0.0]
    bad_args = play("a", "hop", args={"heigth": 3})  # refused by play_problems, elsewhere
    assert play_extent(None, bad_args) == 0.0


# ----------------------------------------------------------- descriptor source


@pytest.fixture()
def gale_store(tmp_path):
    shutil.copytree(FIXTURES / "gale", tmp_path / "gale")
    return CharactersStore(tmp_path)


def _desc(store):
    from an.characters.schema import CharacterDescriptor

    return CharacterDescriptor.model_validate(store["gale"])


def test_a_non_looping_descriptor_animation_occupies_its_natural_length(gale_store):
    desc = _desc(gale_store)  # `blink` is 0.18 s, not looping
    assert play_extent(desc, PlayAction(target="gale", animation="blink")) == pytest.approx(0.18)
    assert play_extent(
        desc, PlayAction(target="gale", animation="blink", speed=2.0)
    ) == pytest.approx(0.09)
    extent = play_extent_for(lambda _eid: desc)
    assert _starts(
        sequence(play("gale", "blink"), tween("gale", "x", to=1.0, duration=1.0)),
        play_extent=extent,
    ) == [0.0, 0.18]


def test_a_looping_descriptor_animation_stays_zero_width(gale_store):
    """`idle_breath` loops (6 s cycle) and runs to the shot end: a sibling after
    it must not wait 6 s."""
    desc = _desc(gale_store)
    assert play_extent(desc, PlayAction(target="gale", animation="idle_breath")) == 0.0
    # …but one the author bounds occupies its window, and `loop=False` on a
    # looping animation plays it once (its natural length).
    assert play_extent(
        desc, PlayAction(target="gale", animation="idle_breath", duration=2.0)
    ) == 2.0
    assert play_extent(
        desc, PlayAction(target="gale", animation="idle_breath", loop=False)
    ) == pytest.approx(6.0)
    # …and `loop=True` on a one-shot loops to the shot end: zero.
    assert play_extent(
        desc, PlayAction(target="gale", animation="blink", loop=True)
    ) == 0.0


def test_the_descriptor_wins_a_preset_name_in_the_extent_too(gale_store):
    """One resolver: the same name resolves to the descriptor's animation for
    the extent exactly as it does for the compiler and validate."""
    d = gale_store["gale"]
    d["animations"]["hop"] = {
        "name": "hop",
        "duration": 1.25,
        "loop": False,
        "tracks": [
            {"target": "bone:torso.y", "type": "linear", "frames": [[0.0, 0.0], [1.25, 0.0]]}
        ],
    }
    gale_store["gale"] = d
    desc = _desc(gale_store)
    assert play_extent(desc, PlayAction(target="gale", animation="hop")) == pytest.approx(1.25)
    assert play_extent(None, PlayAction(target="gale", animation="hop")) == pytest.approx(0.5)


# -------------------------------------------------------- compiler and validate


def _shot(actions, *, duration=3.0):
    return Shot(
        id="s",
        duration=duration,
        entities=[AssetRef(kind="character", id="charlie", store="characters", ref="charlie")],
        actions=list(actions),
    )


def _compile(shot, mall=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the stand-in-rig warning
        return compile_shot(shot, mall)


def test_the_compiler_places_the_second_preset_after_the_first():
    """The nod does not begin until the hop is over (it used to run over it)."""
    scene = _compile(_shot([sequence(play("charlie", "hop"), play("charlie", "nod"))]))
    tl = timeline_from_scene(scene)
    head = ("charlie/head", "rotation")
    rest_head = evaluate_timeline(tl, 0.0).get(head, 0.0)
    for t in (0.1, 0.25, 0.49):
        assert evaluate_timeline(tl, t).get(head, rest_head) == pytest.approx(rest_head), t
    assert any(
        abs(evaluate_timeline(tl, 0.5 + i / 60).get(head, rest_head) - rest_head) > 1e-3
        for i in range(1, 30)
    ), "the nod never moved the head"


def test_validate_sees_the_second_play_past_the_shot_end():
    """Both plays used to sit at 0 and fit a 0.8 s shot; the nod now starts at
    0.5 and runs to 1.0, and validate says so — once, for the nod."""
    shot = _shot([sequence(play("charlie", "hop"), play("charlie", "nod"))], duration=0.8)
    scene = SceneIR(meta=Meta(title="t", duration=0.8), timeline=[shot])
    report = validate_semantic(scene, available_characters={})
    late = [f for f in report.findings if "past the shot's end" in f.description]
    assert len(late) == 1 and "'nod'" in late[0].description
    assert "t=1s" in late[0].description


def test_validate_reads_a_descriptor_animation_extent_through_the_same_resolver(gale_store):
    """`blink` (0.18 s) then a preset: the preset starts at 0.18, so it ends at
    0.68 and overruns a 0.6 s shot. With zero-width plays it would not."""
    shot = Shot(
        id="s",
        duration=0.6,
        entities=[AssetRef(kind="character", id="gale", store="characters", ref="gale")],
        actions=[sequence(play("gale", "blink"), play("gale", "hop"))],
    )
    scene = SceneIR(meta=Meta(title="t", duration=0.6), timeline=[shot])
    report = validate_semantic(scene, available_characters=gale_store)
    late = [f for f in report.findings if "past the shot's end" in f.description]
    assert len(late) == 1 and "t=0.68s" in late[0].description


def test_the_compiler_starts_the_sibling_after_a_descriptor_animation(gale_store):
    """`blink` is 0.18 s: a tween sequenced after it begins at 0.18, not 0."""
    shot = Shot(
        id="s",
        duration=2.0,
        entities=[AssetRef(kind="character", id="gale", store="characters", ref="gale")],
        actions=[
            sequence(
                play("gale", "blink"),
                tween("gale", "x", to=500.0, from_=0.0, duration=1.0, easing="linear"),
            )
        ],
    )
    scene = _compile(shot, {"characters": gale_store})
    tl = timeline_from_scene(scene)
    x = ("gale", "x")
    assert evaluate_timeline(tl, 0.1).get(x, 0.0) == pytest.approx(0.0)
    assert evaluate_timeline(tl, 0.18 + 0.5).get(x) == pytest.approx(250.0)
