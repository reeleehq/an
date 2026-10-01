"""The timing kernel `an.timing` (an#233): registries, declarations, and the move.

What must hold for the move to be safe, and for the next phase to build on it:

- the old import paths are the kernel's objects (one implementation, not two);
- the legacy easings are bit-for-bit what they were; the CSS and Manim entries
  are the curves their names promise;
- the ``stage.node`` and ``stage.camera`` declarations reproduce today's output
  EXACTLY — on every frame of every golden-corpus shot, the declared evaluation
  equals the value-typed one the runtime implements;
- a genre can add a field kind and a property space without editing `an.timing`.
"""

from __future__ import annotations

import math

import pytest

from an.base import EASING_PRESETS, TRANSFORM_PROPERTIES
from an.timing.spaces import STAGE_CAMERA, STAGE_NODE
from an.timing import (
    Channel,
    Clip,
    DiscreteKind,
    FieldDecl,
    FieldKind,
    Keyframe,
    NumberKind,
    PlacedClip,
    PropertySpace,
    Segment,
    Timeline,
    Track,
    check_channel,
    easing_entries,
    easing_entry,
    evaluate_channel,
    evaluate_timeline,
    kind_from_spec,
    kind_names,
    register_kind,
    register_space,
)
from an.timing.easing import apply_easing, legacy_cubic_bezier

# ---------------------------------------------------------------- the move


def test_the_old_paths_are_the_kernel_objects():
    import an.adapters.cutout.channel as old_channel
    import an.adapters.cutout.clip as old_clip
    import an.adapters.cutout.easing as old_easing
    import an.adapters.cutout.timeline as old_timeline
    import an.timing.channel as channel
    import an.timing.clip as clip
    import an.timing.timeline as timeline

    assert (
        old_channel.evaluate is channel.evaluate
        and old_channel.Channel is channel.Channel
    )
    assert old_clip.evaluate is clip.evaluate and old_clip._wrap_time is clip._wrap_time
    assert old_timeline.evaluate_timeline is timeline.evaluate_timeline
    assert old_timeline.write_group is timeline.write_group
    assert old_timeline.PlacedClip is timeline.PlacedClip
    assert old_easing.cubic_bezier is legacy_cubic_bezier


def test_the_stage_easing_table_is_still_exactly_the_legacy_names():
    from an.adapters.cutout.easing import EASING_FUNCS
    from an.adapters.cutout.easing import apply_easing as stage_apply

    assert set(EASING_FUNCS) == set(EASING_PRESETS)
    with pytest.raises(ValueError, match="unknown easing preset"):
        stage_apply("ease-in", 0.5)  # a kernel curve the stage runtime cannot draw
    assert apply_easing("ease-in", 0.5) > 0  # ...which the kernel knows


def test_the_value_typed_rule_refuses_what_the_runtime_cannot_draw():
    """Review S1: the value-typed rule is runtime.js's, easings included."""
    ch = Channel("root", "x", [Keyframe(0.0, 0.0, "ease-in"), Keyframe(1.0, 10.0)])
    with pytest.raises(ValueError, match="unknown easing preset 'ease-in'"):
        evaluate_channel(ch, 0.5)
    assert (
        evaluate_channel(ch, 0.5, kind=NumberKind()) > 0
    )  # the declared rule knows it


@pytest.mark.parametrize(
    "easing", ["ease-in", "smooth", "steps(4)", "cubic-bezier(0, 0, 1, 1)"]
)
def test_compile_and_validate_refuse_a_tween_easing_the_stage_cannot_draw(easing):
    """Review S1's scenario: before, compile baked a CSS-curve start value and
    runtime.js threw at render; validate passed. Now both refuse."""
    from an.adapters.cutout.compile import compile_shot
    from an.ir.compose import delay, parallel, sequence, tween
    from an.ir.schema import Meta, SceneIR, Shot
    from an.ir.validate import validate_semantic

    lone = Shot(
        id="s",
        renderer="cutout",
        duration=2.0,
        actions=[tween("root", "x", 10.0, 1.0, from_=0.0, easing=easing)],
    )
    chained = Shot(
        id="s",
        renderer="cutout",
        duration=2.0,
        actions=[
            parallel(
                tween("root", "x", 10.0, 1.0, from_=0.0, easing=easing),
                sequence(delay(0.5), tween("root", "x", 20.0, 1.0)),
            )
        ],
    )
    for shot in (lone, chained):
        with pytest.raises(ValueError, match="unknown easing preset"):
            compile_shot(shot, mall=None, fps=24)
    report = validate_semantic(SceneIR(meta=Meta(title="t"), timeline=[lone]))
    assert any(
        easing in f.description for f in report.findings if f.severity == "error"
    )


def test_a_replacement_easing_must_raise_its_version():
    """Review S9: a name's meaning cannot change under a scene silently."""
    from an.timing.easing import EasingEntry, register_easing

    old = easing_entry("smooth")
    same = EasingEntry(
        "smooth",
        lambda u: u,
        family="manim",
        solver="closed-form",
        description="x",
        version=old.version,
    )
    with pytest.raises(ValueError, match="must raise the version"):
        register_easing(same, replace=True)
    assert easing_entry("smooth") is old


def test_parametrised_specs_parse_as_both_languages_do():
    """Review N2: numbers parse alike in Python and JS."""
    assert apply_easing("steps(4.0)", 0.3) == apply_easing("steps(4)", 0.3)
    for bad in (
        "cubic-bezier(1_0, 0, 1, 1)",
        "cubic-bezier(inf, 0, 1, 1)",
        "steps(4.5)",
    ):
        with pytest.raises(ValueError):
            apply_easing(bad, 0.5)


def test_the_default_rule_resolves_its_space_by_name(monkeypatch):
    """Review S8: replacing the registered stage.node space reaches the default
    path (P3 moves the registration, not the kernel)."""
    from an.timing import spaces

    changed = PropertySpace(
        "stage.node",
        (FieldDecl("x", NumberKind(), writes="y"), FieldDecl("y", NumberKind())),
    )
    monkeypatch.setitem(spaces._REGISTRY, "stage.node", changed)
    xs = Clip("x", 1.0, [Channel("a", "x", [Keyframe(0.0, 1.0)])])
    ys = Clip("y", 1.0, [Channel("a", "y", [Keyframe(0.0, 2.0)])])
    tl = Timeline(9.0, [Track("a", [PlacedClip(xs, 0.0), PlacedClip(ys, 2.0)])])
    assert evaluate_timeline(tl, 5.0) == {("a", "y"): 2.0}  # x and y now share a group


# ---------------------------------------------------------------- easings


def _frozen_legacy(name: str, t: float) -> float:
    """The legacy curves exactly as `an/adapters/cutout/easing.py` wrote them."""
    if name == "linear":
        return t
    if name == "ease_in":
        return t * t
    if name == "ease_out":
        return 1.0 - (1.0 - t) ** 2
    if name in ("ease", "ease_in_out"):
        return 2.0 * t * t if t < 0.5 else 1.0 - 2.0 * (1.0 - t) ** 2
    if name == "step":
        return 0.0 if t < 1.0 else 1.0
    raise KeyError(name)


def test_every_legacy_easing_is_bit_identical_to_what_an_drew():
    ts = [i / 997 for i in range(998)] + [
        math.nextafter(1.0, 0.0),
        0.5,
        math.nextafter(0.5, 0.0),
    ]
    for name in EASING_PRESETS:
        assert easing_entry(name).family in ("legacy", "common")
        for t in ts:
            assert apply_easing(name, t) == _frozen_legacy(name, t), (name, t)


def test_css_names_are_the_css_curves_and_ease_is_not_one_of_them():
    for name, points in {
        "ease-in": (0.42, 0, 1, 1),
        "ease-out": (0, 0, 0.58, 1),
        "ease-in-out": (0.42, 0, 0.58, 1),
    }.items():
        spelled = f"cubic-bezier({', '.join(map(str, points))})"
        for i in range(21):
            assert apply_easing(name, i / 20) == apply_easing(spelled, i / 20)
    # 'ease' is an's quadratic (0.125 at 0.25); CSS 'ease' is ~0.41 there.
    assert apply_easing("ease", 0.25) == 0.125
    assert apply_easing("cubic-bezier(0.25, 0.1, 0.25, 1)", 0.25) == pytest.approx(
        0.4085, abs=1e-3
    )


def test_the_two_bezier_solvers_are_different_named_solvers():
    """They agree closely on ordinary curves but not to 1e-9 everywhere — which
    is why the solver is part of the entry and the legacy one is not replaced."""
    ordinary = max(
        abs(
            legacy_cubic_bezier(0.42, 0.0, 0.58, 1.0, t)
            - apply_easing("ease-in-out", t)
        )
        for t in [i / 200 for i in range(201)]
    )
    # A curve whose slope vanishes mid-way: 8 Newton steps do not converge.
    steep = abs(
        legacy_cubic_bezier(1.0, 0.0, 0.0, 1.0, 0.501)
        - apply_easing("cubic-bezier(1, 0, 0, 1)", 0.501)
    )
    assert ordinary < 1e-9 < steep


def test_every_entry_is_versioned_and_names_a_known_solver():
    for entry in easing_entries():
        assert entry.version >= 1 and entry.description, entry.name
        assert apply_easing(entry.name, 0.0) == pytest.approx(
            0.0, abs=1e-12
        ) or entry.name in ("step-start",), entry.name


def test_manim_rate_functions_are_manims():
    rate_functions = pytest.importorskip(
        "manim.utils.rate_functions", reason="manim is an optional extra"
    )
    for entry in easing_entries():
        if entry.family != "manim":
            continue
        theirs = getattr(rate_functions, entry.name)
        for i in range(-2, 203):
            u = i / 200
            assert apply_easing(entry.name, u) == pytest.approx(
                float(theirs(u)), abs=1e-12
            ), (entry.name, u)


def test_an_unknown_easing_still_raises_on_a_swap_channel():
    ch = Channel("a", "hands", [Keyframe(0.0, "A", "eaze"), Keyframe(1.0, "B")])
    with pytest.raises(ValueError, match="unknown easing preset"):
        evaluate_channel(ch, 0.5)
    with pytest.raises(ValueError, match="unknown easing preset"):
        evaluate_channel(ch, 0.5, kind=STAGE_NODE.kind_of("hands"))


# ---------------------------------------------------------------- kinds


def test_every_kind_round_trips_through_its_spec():
    for name in kind_names():
        kind = kind_from_spec(name)
        assert kind_from_spec(kind.to_spec()) == kind


@pytest.mark.parametrize(
    "spec",
    [
        {"kind": "number", "space": "cubic"},
        {"kind": "discrete", "switch_at": 0},
        {"kind": "angle", "unit": "grad"},
        {"kind": "number", "nope": 1},
    ],
)
def test_a_malformed_kind_spec_is_refused(spec):
    with pytest.raises(ValueError):
        kind_from_spec(spec)


def test_discrete_switches_on_time_and_switch_at_one_is_the_key_time():
    b = 9.767899248713501
    a = 0.1524221856720187
    below = math.nextafter(b, 0.0)
    assert (below - a) / (b - a) == 1.0  # the ratio lies...
    assert (
        DiscreteKind(switch_at=1).interpolate("A", "B", 1.0, Segment(below, a, b))
        == "A"
    )
    assert DiscreteKind(switch_at=1).interpolate("A", "B", 1.0, Segment(b, a, b)) == "B"
    # ...and an eased progress past 1 (an overshoot) never switches it.
    assert DiscreteKind().interpolate("A", "B", 5.0, Segment(0.1, 0.0, 1.0)) == "A"


def test_a_declared_kind_beats_the_value_type():
    ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
    assert evaluate_channel(ch, 0.5) == 5.0
    assert evaluate_channel(ch, 0.5, kind=DiscreteKind()) == 10.0
    assert evaluate_channel(ch, 0.49, kind=DiscreteKind()) == 0.0


def test_the_first_instant_of_a_declared_segment_is_the_key_it_leaves():
    ch = Channel("a", "x", [Keyframe(0.0, 0.0, "step-start"), Keyframe(1.0, 10.0)])
    assert evaluate_channel(ch, 0.0, kind=NumberKind()) == 0.0
    assert evaluate_channel(ch, 0.25, kind=NumberKind()) == 10.0


def test_check_channel_names_values_that_do_not_fit_their_kind():
    ch = Channel("a", "zoom", [Keyframe(0.0, 1.0), Keyframe(1.0, -2.0)])
    assert check_channel(ch, NumberKind()) == []
    (problem,) = check_channel(ch, NumberKind(space="log"))
    assert "a:zoom at t=1.0" in problem and "positive" in problem


# ---------------------------------------------------------------- spaces


def test_stage_node_declares_every_transform_property_as_a_plain_number():
    for prop in TRANSFORM_PROPERTIES:
        decl = STAGE_NODE.declaration(prop)
        assert decl is not None and decl.pattern == prop, prop
        assert decl.kind == NumberKind() and decl.unit, prop


def test_stage_node_swaps_are_discrete_at_their_key_time_including_variants():
    for prop in ("viseme", "viseme@happy", "hands", "body_facing", "eyelid@sleepy"):
        assert STAGE_NODE.kind_of(prop) == DiscreteKind(switch_at=1), prop


def test_stage_node_write_groups_are_the_rule_the_runtime_uses():
    """The rule `timeline.py::write_group` had before the move, restated."""
    for prop in [*TRANSFORM_PROPERTIES, "viseme", "viseme@happy", "hands", "x@y"]:
        if prop in TRANSFORM_PROPERTIES:
            want = {"rotation_rad": "rotation"}.get(prop, prop)
        else:
            want = "<swap>"
        assert STAGE_NODE.write_group(prop) == want, prop


def test_the_stage_camera_space_is_the_four_fields_the_compiler_lowers():
    from an.adapters.cutout.compile import _CAMERA_CHANNELS

    lowered = {field for field, _, _ in _CAMERA_CHANNELS}
    declared = {d.pattern for d in STAGE_CAMERA.fields}
    assert declared == lowered == {"x", "y", "zoom", "rotation"}
    for field, prop, _ in _CAMERA_CHANNELS:
        assert STAGE_CAMERA.kind_of(field) == NumberKind()
        assert STAGE_NODE.kind_of(prop) == NumberKind()  # what it lowers onto, on root


def _corpus_timelines(tmp_path):
    from tests.test_pure_pose import _corpus_shots

    from an.adapters.cutout.timeline import timeline_from_scene

    for name, shot, fps, _, doc in _corpus_shots()(tmp_path):
        yield (
            f"{name}/{shot.id}",
            timeline_from_scene(doc),
            max(1, int(round(shot.duration * fps))),
            fps,
        )


def test_the_stage_declarations_reproduce_every_corpus_frame_exactly(tmp_path):
    """The claim that made declared kinds safe to adopt as the default (an#239
    item 2): on every frame of every golden-corpus shot, the DEFAULT evaluation
    (the declared stage.node space since P2) gives the very same pose (==, not
    approx) as the value-typed rule runtime.js runs (``space=VALUE_TYPED``) —
    and as naming the declared space explicitly."""
    from an.timing.spaces import VALUE_TYPED

    frames = 0
    bad = []
    for label, tl, n, fps in _corpus_timelines(tmp_path):
        for i in range(n):
            t = i / float(fps)
            default = evaluate_timeline(tl, t)
            if not (
                default
                == evaluate_timeline(tl, t, space=VALUE_TYPED)
                == evaluate_timeline(tl, t, space=STAGE_NODE)
            ):
                bad.append(f"{label} frame {i}")
            frames += 1
    assert frames and not bad, bad[:10]


def test_every_corpus_channel_fits_its_declared_kind(tmp_path):
    problems = []
    for label, tl, _, _ in _corpus_timelines(tmp_path):
        for track in tl.tracks:
            for placed in track.clips:
                for ch in placed.clip.channels:
                    problems += check_channel(ch, STAGE_NODE.kind_of(ch.property))
    assert not problems, problems[:10]


# ------------------------------------------------- the seam P2 builds on


@pytest.fixture
def genre_kind_and_space():
    """A 'genre' registers a field kind and a property space from outside."""
    from dataclasses import dataclass
    from typing import ClassVar

    from an.timing import kinds, spaces

    @dataclass(frozen=True)
    class Doubling(FieldKind):
        name: ClassVar[str] = "test-doubling"

        def interpolate(self, a, b, u, seg):
            return 2 * (a + (b - a) * u)

    register_kind(Doubling.name, Doubling)
    space = register_space(
        PropertySpace(
            "test.genre.widget",
            (FieldDecl("level", kind_from_spec("test-doubling"), unit="px"),),
        )
    )
    yield space
    kinds._REGISTRY.pop(Doubling.name)
    spaces._REGISTRY.pop(space.name)


def test_a_genre_adds_a_kind_and_a_space_without_editing_the_kernel(
    genre_kind_and_space,
):
    ch = Channel("w", "level", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
    tl = Timeline(1.0, [Track("w", [PlacedClip(Clip("c", 1.0, [ch]))])])
    assert evaluate_timeline(tl, 0.5, space="test.genre.widget") == {
        ("w", "level"): 10.0
    }
    # Per-target resolution: each entity kind brings its own space (P2's shape).
    spaces = {"w": genre_kind_and_space}
    assert evaluate_timeline(
        tl, 0.5, space=lambda target: spaces.get(target, STAGE_NODE)
    ) == {("w", "level"): 10.0}
