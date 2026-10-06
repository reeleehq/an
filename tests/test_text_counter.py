"""A counter, lowered at compile: ``counter`` and the block-scoped ``value`` (an#342, T2 of an#331).

A counter block's number is an ordinary channel in the IR (``tween <id> value
a→b``, ``set <id> value v``); the stage's ``counters`` pass samples it on the
frame grid and lowers it to the T1 replacement set (an#341). Checked:

- the format mini-language (:mod:`an.formats`): the subset, nearest-half-even
  rounding, the refusals;
- the document: a counter needs ``unit: block`` and excludes ``text``/``texts``;
- the lowering: every frame shows the formatted value of the channel at ``i / fps``
  (a 1 → 30 calendar with one block), sets land half a frame early, ``step_hz`` is
  honoured, a ``value`` leaf inside a sequence moves nothing around it;
- the errors: a from-less tween with no ``start`` and nothing before it, a counter
  with no value at all, a non-number, ``value`` on anything but a counter block
  (compile and validate);
- the pass order, pinned against the registry: after every pass that can add a
  ``value`` action, immediately before ``actions`` (whose swap check reads the
  vocabulary).
"""

from __future__ import annotations

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.formats import CounterFormatError, format_number, parse_format
from an.ir.compose import delay, sequence, tween
from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, SetAction, Shot
from an.ir.validate import validate_semantic
from an.text import TextDescriptor

W, H, FPS = 320, 240, 24


def _doc(**counter) -> dict:
    counter = counter or {"format": "{d}", "start": 1}
    return {
        "kind": "TextDescriptor",
        "name": "day",
        "unit": "block",
        "counter": counter,
        "align": "right",
    }


def _shot(actions=(), *, duration=1.25, entities=None) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=duration,
        entities=entities
        or [AssetRef(kind="prop", id="day", store="props", ref="day")],
        actions=list(actions),
    )


def _shown(doc, *, frames: int, eid: str = "day") -> list[str]:
    """The string each frame ``i / fps`` shows, read back through the evaluator."""
    d = to_dict(doc)
    (node,) = [n for n in d["scene"]["children"] if n["name"] == eid]
    (block,) = node["children"]
    texts = block["visual"]["asset_sets"]["text"]
    rest = next(k for k, a in texts.items() if a == block["visual"]["asset_id"])
    tl = timeline_from_scene(doc)
    out = []
    for i in range(frames):
        key = evaluate_timeline(tl, i / FPS).get((f"{eid}/block_0", "text"), rest)
        out.append(key)
    return out


def _errors(shot, mall) -> list[str]:
    scene = SceneIR(
        meta=Meta(duration=shot.duration, resolution=Resolution(width=W, height=H)),
        timeline=[shot],
    )
    report = validate_semantic(scene, available_props=mall["props"])
    return [f.description for f in report.findings if f.severity == "error"]


# --- the format mini-language ---------------------------------------------------------


@pytest.mark.parametrize(
    "value, fmt, expected",
    [
        (2.5, "{d}", "2"),
        (3.5, "{d}", "4"),
        (29.5, "{d}", "30"),
        (-0.4, "{d}", "0"),
        (-2.6, "{d}", "-3"),
        (1234567.0, "{,d}", "1,234,567"),
        (0.125, "{.2f}", "0.12"),
        (21.456, "{.1f} °C", "21.5 °C"),
        (0.256, "{.0%}", "26%"),
        (0.5, "{.1%}", "50.0%"),
        (1500.0, "{.2s}", "1.5k"),
        (1500.0, "{s}", "1.50000k"),
        (0.0042, "{.2s}", "4.2m"),
        (7.0, "Day {d} of 30", "Day 7 of 30"),
    ],
)
def test_the_format_subset_rounds_to_nearest_half_even(value, fmt, expected):
    assert format_number(value, fmt) == expected


@pytest.mark.parametrize(
    "fmt, needle",
    [
        ("{d} {d}", "exactly one"),
        ("no braces", "exactly one"),
        ("{.3d}", "takes no precision"),
        ("{f}", "needs a precision"),
        ("{%}", "needs a precision"),
        ("{,.1f}", "groups an integer"),
        ("{x}", "is not in it"),
        ("{.0s}", "significant digit"),
        ("{0:d}", "is not in it"),
    ],
)
def test_a_format_outside_the_subset_is_refused_naming_it(fmt, needle):
    with pytest.raises(CounterFormatError, match=needle):
        parse_format(fmt)


def test_a_counter_cannot_show_a_non_finite_number():
    with pytest.raises(CounterFormatError):
        format_number(float("nan"), "{d}")


# --- the document ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields, needle",
    [
        ({"counter": {"format": "{d}"}}, "needs unit='block'"),
        ({"counter": {}, "unit": "block", "text": "x"}, "text and counter were given"),
        ({"counter": {"format": "{q}"}, "unit": "block"}, "is not in it"),
        ({"counter": {"start": float("inf")}, "unit": "block"}, "finite"),
        ({"counter": {"step": 1}, "unit": "block"}, "Extra inputs"),
    ],
)
def test_the_document_refuses_a_counter_it_could_not_draw(fields, needle):
    with pytest.raises(ValueError, match=needle):
        TextDescriptor(name="t", **fields)


# --- the lowering ---------------------------------------------------------------------


def test_the_calendar_counts_1_to_30_with_one_block():
    shot = _shot([tween("day", "value", 30.0, 1.0, easing="linear")])
    doc = compile_shot(shot, {"props": {"day": _doc()}}, width=W, height=H, fps=FPS)
    frames = 30
    expected = [format_number(1 + 29 * min(i / FPS, 1.0), "{d}") for i in range(frames)]
    keys = _shown(doc, frames=frames)
    texts = to_dict(doc)["scene"]["children"][0]["children"][0]["visual"]["asset_sets"]["text"]
    assert [k.removeprefix("v_") for k in keys] == expected
    assert expected[0] == "1" and expected[12] == "16" and expected[-1] == "30"
    # One key per distinct string: 29 steps over 24 frames skip a few numbers.
    assert sorted(texts) == sorted({f"v_{e}" for e in expected})
    # One block, and no texture the document does not draw.
    d = to_dict(doc)
    assert [c["name"] for c in d["scene"]["children"][0]["children"]] == ["block_0"]
    drawn = set(texts.values())
    assert {a for a in d["assets"]["textures"] if a.startswith("text.day.")} == drawn


def test_every_set_lands_half_a_frame_before_the_frame_that_shows_it():
    shot = _shot([tween("day", "value", 30.0, 1.0, easing="linear")])
    doc = to_dict(compile_shot(shot, {"props": {"day": _doc()}}, width=W, height=H, fps=FPS))
    times = sorted(
        k["time"] + clip["start_time"]
        for track in doc["timeline"]["tracks"]
        for clip in track["clips"]
        for ch in doc["animations"][clip["animation_id"]]["channels"]
        if ch["property"] == "text"
        for k in ch["keyframes"]
    )
    assert times, "the lowering emitted no `set text`"
    for t in times:
        frame = t * FPS + 0.5
        assert abs(frame - round(frame)) < 1e-6, t


def test_a_set_of_value_holds_from_its_frame():
    actions = [SetAction(target="day/block_0", property="value", value=7, at=0.5)]
    doc = compile_shot(_shot(actions), {"props": {"day": _doc()}}, width=W, height=H, fps=FPS)
    keys = _shown(doc, frames=30)
    assert keys[11] == "v_1" and keys[12] == "v_7" and keys[-1] == "v_7"


def test_step_hz_steps_the_counter_too():
    shot = _shot([tween("day", "value", 30.0, 1.0, easing="linear")])
    doc = compile_shot(
        shot, {"props": {"day": _doc()}}, width=W, height=H, fps=FPS, step_hz=4
    )
    keys = _shown(doc, frames=30)
    changes = sum(1 for a, b in zip(keys, keys[1:]) if a != b)
    assert 0 < changes <= 5, keys


def test_a_value_leaf_inside_a_sequence_moves_nothing_around_it():
    """The lowered leaf becomes a `delay` of its own length, so the `x` tween
    after it in the same sequence still starts at 1.0 s."""
    mall = {"props": {"day": _doc(), "dot": {"kind": "TextDescriptor", "name": "d", "text": "."}}}
    entities = [
        AssetRef(kind="prop", id="day", store="props", ref="day"),
        AssetRef(kind="prop", id="dot", store="props", ref="dot"),
    ]
    seq = sequence(
        delay(0.25),
        tween("day", "value", 10.0, 0.75, easing="linear"),
        tween("dot", "x", 50.0, 0.25, from_=0.0, easing="linear"),
    )
    doc = compile_shot(_shot([seq], entities=entities), mall, width=W, height=H, fps=FPS)
    tl = timeline_from_scene(doc)
    assert evaluate_timeline(tl, 0.99).get(("dot", "x"), 0.0) == pytest.approx(0.0, abs=1e-6)
    assert evaluate_timeline(tl, 1.125)[("dot", "x")] == pytest.approx(25.0)


def test_a_from_less_tween_starts_from_an_earlier_set():
    actions = [
        SetAction(target="day", property="value", value=10),
        sequence(delay(0.5), tween("day", "value", 20.0, 0.5, easing="linear")),
    ]
    mall = {"props": {"day": _doc(format="{d}")}}
    keys = _shown(compile_shot(_shot(actions), mall, width=W, height=H, fps=FPS), frames=30)
    assert keys[0] == "v_10" and keys[12] == "v_10" and keys[24] == "v_20"


def test_a_from_less_tween_with_nothing_before_it_is_an_error_naming_both():
    mall = {"props": {"day": _doc(format="{d}")}}
    shot = _shot([tween("day", "value", 30.0, 1.0)])
    with pytest.raises(CutoutCompileError, match=r"`counter\.start`.*`set` of `value`"):
        compile_shot(shot, mall, width=W, height=H, fps=FPS)


def test_a_counter_with_no_value_at_all_is_an_error():
    with pytest.raises(CutoutCompileError, match="no value to show"):
        compile_shot(_shot(), {"props": {"day": _doc(format="{d}")}}, width=W, height=H)


def test_a_counter_with_a_start_and_no_action_draws_its_start():
    doc = compile_shot(_shot(), {"props": {"day": _doc(format="{d}", start=5)}}, width=W, height=H)
    assert set(_shown(doc, frames=30)) == {"v_5"}


# --- `value` is block-scoped ----------------------------------------------------------


def test_value_on_a_text_block_that_is_not_a_counter_is_refused_everywhere():
    mall = {"props": {"day": {"kind": "TextDescriptor", "name": "d", "text": "1", "unit": "block"}}}
    shot = _shot([SetAction(target="day", property="value", value=3)])
    with pytest.raises(CutoutCompileError, match="counter text block"):
        compile_shot(shot, mall, width=W, height=H)
    errors = _errors(shot, mall)
    assert len(errors) == 1 and "declares no `counter`" in errors[0], errors


def test_a_non_number_value_is_refused_at_compile_and_validate():
    mall = {"props": {"day": _doc()}}
    shot = _shot([SetAction(target="day", property="value", value="seven")])
    with pytest.raises(CutoutCompileError, match="`value` is a number"):
        compile_shot(shot, mall, width=W, height=H)
    assert any("`value` is a number" in e for e in _errors(shot, mall))


def test_validate_passes_the_calendar():
    shot = _shot([tween("day", "value", 30.0, 1.0, easing="linear")])
    assert _errors(shot, {"props": {"day": _doc()}}) == []


def test_the_counters_pass_runs_after_every_value_source_and_right_before_actions():
    """Pinned against the registry (an#342): a pass that adds a `value` action
    must run before `counters`, and the swap check in `actions` must see the
    lowered set. Every registered pass ordered before `actions` precedes it."""
    from an.stage.compile import compile_passes_for_stage

    names = [p.name for p in compile_passes_for_stage()]
    passes = {p.name: p for p in compile_passes_for_stage()}
    k = names.index("counters")
    assert names[k + 1] == "actions", names
    assert all(passes[n].order < passes["counters"].order for n in names[:k]), names


def test_a_value_tween_inside_a_loop_is_lowered_too():
    """A `loop` keeps its action in `child`, not `children` (review of an#343):
    the lowering reaches it, so no `value` is left for the swap check."""
    from an.ir.compose import loop

    shot = _shot([loop(tween("day", "value", 5.0, 0.5, from_=1.0, easing="linear"), 2)])
    doc = compile_shot(shot, {"props": {"day": _doc()}}, width=W, height=H, fps=FPS)
    keys = _shown(doc, frames=30)
    assert keys[0] == "v_1" and keys[11] == "v_5", keys
    assert keys[12] == "v_1", "the second pass of the loop starts again from 1"
