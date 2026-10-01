"""The cases of ``timing_vectors.json``: compiled documents, their spaces, and sample times.

Two seeds, as the core study §6 step 1 asks:

- **keyframe-sequence cases** (the TypeScript kernel's golden cases: every field
  kind, the CSS timings, cuts, dwells, carry-forward), written here as keyframe
  sequences and lowered to the compiled form by :func:`_lower_sequence` — a
  minimal keyframe-sequence front-end (carry-forward, back-fill, transitions as
  segment easings, dwells as holds). Two features have no kernel equivalent and
  are left out of the seed: a timing *slice* (``{of, slice}``) and a per-segment
  ``switchAt`` on a field with more than one transition. CSS ``ease`` is written
  ``cubic-bezier(0.25, 0.1, 0.25, 1)``, because the name ``ease`` is `an`'s
  quadratic (:mod:`an.timing.easing`).
- **`an`'s parity cases**, in the ``stage.node`` space: the channel battery of
  ``tests/test_cutout_channel_parity.py`` and the timeline battery of
  ``tests/test_pure_pose.py``, the an#86 boundary (``(t - a.time) / span``
  rounds to 1.0 while ``t < b.time``), and cross-track inclusive-end ties.

Sample times: every clip start and end, every keyframe's absolute time (per loop
cycle), every midpoint between consecutive ones, a uniform grid, and the case's
own extra times.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Iterable

#: Points of the uniform grid added to every case's sample times.
GRID_STEPS: int = 8
#: CSS ``ease``, spelled so it cannot be read as an's legacy ``ease``.
CSS_EASE: str = "cubic-bezier(0.25, 0.1, 0.25, 1)"
DFLT_TRANSITION_S: float = 1.0
SEQUENCE_ENTITY: str = "view"
SEQUENCE_ANIMATION: str = "sequence"


# -----------------------------------------------------------------------------
# A minimal keyframe-sequence front-end (the seed's lowering, not a public API)
# -----------------------------------------------------------------------------


def _is_bag(x: Any) -> bool:
    return isinstance(x, dict)


def _merge(base: dict, patch: dict, atomic, prefix: str = "") -> dict:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else key
        prev = out.get(key)
        if _is_bag(prev) and _is_bag(value) and not atomic(path):
            out[key] = _merge(prev, value, atomic, path)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _leaves(state: dict, declared: set[str], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in state.items():
        path = f"{prefix}.{key}" if prefix else key
        if path in declared or not _is_bag(value):
            out[path] = value
        else:
            out.update(_leaves(value, declared, path))
    return out


def _timing(spec: Any) -> Any:
    if isinstance(spec, dict):
        raise ValueError(f"timing slices have no kernel equivalent: {spec!r}")
    return CSS_EASE if spec == "ease" else spec


def _kind_spec(spec: dict) -> dict:
    out = dict(spec)
    if "switchAt" in out:
        out["switch_at"] = out.pop("switchAt")
    return out


def _lower_sequence(seq: dict) -> tuple[dict, dict, float]:
    """``(compiled document, space json, duration)`` of a keyframe sequence."""
    space = {path: _kind_spec(spec) for path, spec in seq["space"].items()}
    declared = set(space)

    def atomic(path: str) -> bool:
        return path in declared and space[path]["kind"] != "orbit"

    kfs = seq["keyframes"]
    defaults = seq.get("defaults", {})
    forward: list[dict] = []
    for i, kf in enumerate(kfs):
        forward.append(
            copy.deepcopy(kf["state"])
            if i == 0
            else _merge(forward[-1], kf["state"], atomic)
        )
    states = list(forward)
    for i in range(len(states) - 2, -1, -1):
        states[i] = _merge(states[i + 1], states[i], atomic)
    leaves = [_leaves(s, declared) for s in states]
    paths = list(dict.fromkeys(p for leaf in leaves for p in leaf))

    switch_overrides: dict[str, float] = {}
    keys: dict[str, list[dict]] = {p: [] for p in paths}
    clock = 0.0
    for i, kf in enumerate(kfs):
        if i > 0:
            enter = {**defaults.get("transition", {}), **kf.get("enter", {})}
            fields = {
                **defaults.get("transition", {}).get("fields", {}),
                **kf.get("enter", {}).get("fields", {}),
            }
            duration = enter.get("duration", DFLT_TRANSITION_S)
            if duration > 0:
                for p in paths:
                    own = fields.get(p, {})
                    if "switchAt" in own:
                        if switch_overrides.get(p, own["switchAt"]) != own["switchAt"]:
                            raise ValueError(
                                f"{p}: per-transition switch points differ"
                            )
                        switch_overrides[p] = own["switchAt"]
                    keys[p][-1]["easing"] = _timing(
                        own.get("timing", enter.get("timing"))
                    )
                clock += duration
        for p in paths:
            keys[p].append({"time": clock, "value": leaves[i][p], "easing": None})
        dwell = kf.get("dwell", defaults.get("dwell", 0.0))
        if dwell > 0:
            clock += dwell
            for p in paths:
                keys[p].append({"time": clock, "value": leaves[i][p], "easing": None})
    if len(kfs) > 2 and switch_overrides:
        raise ValueError("a per-transition switch point needs a single transition")
    for p, switch_at in switch_overrides.items():
        space[p] = {"kind": "discrete", "switch_at": switch_at}
    doc = {
        "timeline": {
            "duration": clock,
            "tracks": [
                {
                    "target_root": SEQUENCE_ENTITY,
                    "clips": [
                        {
                            "animation_id": SEQUENCE_ANIMATION,
                            "start_time": 0.0,
                            "duration": clock,
                        }
                    ],
                }
            ],
        },
        "animations": {
            SEQUENCE_ANIMATION: {
                "name": SEQUENCE_ANIMATION,
                "duration": clock,
                "loop_mode": "once",
                "channels": [
                    {"target": SEQUENCE_ENTITY, "property": p, "keyframes": keys[p]}
                    for p in paths
                ],
            }
        },
    }
    space_json = {
        "name": "inline",
        "fields": [{"pattern": p, "spec": s} for p, s in space.items()],
    }
    return doc, space_json, clock


def _seq(space: dict, keyframes: list[dict], **extra: Any) -> dict:
    return {"space": space, "keyframes": keyframes, **extra}


def _kf(
    state: dict, duration: float | None = None, timing: Any = None, **extra: Any
) -> dict:
    out: dict[str, Any] = {"state": state, **extra}
    if duration is not None or timing is not None:
        enter: dict[str, Any] = {}
        if duration is not None:
            enter["duration"] = duration
        if timing is not None:
            enter["timing"] = timing
        out["enter"] = {**enter, **out.pop("enter", {})}
    return out


SEQUENCE_CASES: list[tuple[str, str, dict]] = [
    (
        "number-linear-and-log",
        "A linear number and a log-space number, with a dwell and a CSS ease-in-out.",
        _seq(
            {"x": {"kind": "number"}, "zoom": {"kind": "number", "space": "log"}},
            [
                _kf({"x": -2, "zoom": 1}, dwell=0.5),
                _kf({"x": 3, "zoom": 4}, 1.5, "ease-in-out"),
                _kf({"x": 0, "zoom": 0.25}, 1),
            ],
        ),
    ),
    (
        "angle",
        "Shortest arc in degrees both ways across 0, radians, and wrap off.",
        _seq(
            {
                "yaw": {"kind": "angle"},
                "roll": {"kind": "angle", "unit": "rad"},
                "spin": {"kind": "angle", "wrap": False},
            },
            [
                _kf({"yaw": 350, "roll": 0.1, "spin": 0}),
                _kf({"yaw": 10, "roll": 6.1, "spin": 720}, 1),
                _kf({"yaw": 300, "roll": 3, "spin": -90}, 1, "ease"),
            ],
        ),
    ),
    (
        "vector-and-quaternion",
        "A componentwise vector, and slerp including a target whose sign makes the dot product negative.",
        _seq(
            {"pos": {"kind": "vector"}, "rot": {"kind": "quaternion"}},
            [
                _kf({"pos": [0, 0, 0], "rot": [0, 0, 0, 1]}),
                _kf(
                    {
                        "pos": [1, -2, 4],
                        "rot": [0, 0, 0.7071067811865476, 0.7071067811865476],
                    },
                    1,
                ),
                _kf({"pos": [2, 2, 2], "rot": [-0.5, -0.5, -0.5, -0.5]}, 1, "ease-out"),
            ],
        ),
    ),
    (
        "color",
        "OKLab mixing with premultiplied alpha, in hex and array forms.",
        _seq(
            {
                "fg": {"kind": "color"},
                "bg": {"kind": "color"},
                "tint": {"kind": "color"},
            },
            [
                _kf({"fg": "#ff0000", "bg": "#ffffff", "tint": [0.2, 0.4, 0.6]}),
                _kf({"fg": "#00ff00", "bg": "#0000ff00", "tint": [1, 0.5, 0, 0.5]}, 1),
                _kf({"fg": "#08f", "bg": "#123", "tint": [0, 0, 0]}, 1),
            ],
        ),
    ),
    (
        "color-srgb",
        "Componentwise sRGB mixing (the stage tint's and Manim's rule), hex and array forms.",
        _seq(
            {
                "fg": {"kind": "color", "space": "srgb"},
                "tint": {"kind": "color", "space": "srgb"},
            },
            [
                _kf({"fg": "#ff0000", "tint": [0.2, 0.4, 0.6]}),
                _kf({"fg": "#0000ff80", "tint": [1, 0.5, 0, 0.5]}, 1),
            ],
        ),
    ),
    (
        "orbit",
        "Azimuth across 0, elevation lerp, log distance, target lerp, and an extra member that switches at the middle.",
        _seq(
            {"camera": {"kind": "orbit"}},
            [
                _kf(
                    {
                        "camera": {
                            "azimuth": 340,
                            "elevation": 10,
                            "distance": 2,
                            "target": [0, 0, 0],
                            "projection": "perspective",
                        }
                    }
                ),
                _kf(
                    {
                        "camera": {
                            "azimuth": 30,
                            "elevation": 60,
                            "distance": 8,
                            "target": [1, 2, 3],
                            "projection": "orthographic",
                        }
                    },
                    2,
                ),
            ],
        ),
    ),
    (
        "discrete-and-undeclared",
        "Discrete fields switch on time under a timing whose progress crosses 0.5 three times; a declared and an overridden switch point; undeclared nested fields.",
        _seq(
            {"mode": {"kind": "discrete", "switchAt": 0.25}, "x": {"kind": "number"}},
            [
                _kf({"mode": "one", "x": 0, "ui": {"panel": "left", "visible": True}}),
                _kf(
                    {"mode": "two", "x": 1, "ui": {"panel": "right", "visible": False}},
                    1,
                    "cubic-bezier(0.3, 1.8, 0.7, -0.8)",
                    enter={"fields": {"ui.visible": {"switchAt": 0.8}}},
                ),
            ],
        ),
    ),
    (
        "timings",
        "cubic-bezier with overshoot, and steps with jump-end and jump-none.",
        _seq(
            {"x": {"kind": "number"}},
            [
                _kf({"x": 0}),
                _kf({"x": 10}, 1, "cubic-bezier(0.5, -0.8, 0.5, 1.8)"),
                _kf({"x": 20}, 1, "steps(4)"),
                _kf({"x": 30}, 1, "steps(3, jump-none)"),
            ],
        ),
    ),
    (
        "cuts-dwells-carry-forward",
        "Sequence defaults, a cut in the middle, dwells, carry-forward of omitted fields and back-fill of a field that appears late.",
        _seq(
            {
                "x": {"kind": "number"},
                "y": {"kind": "number"},
                "late": {"kind": "number"},
            },
            [
                _kf({"x": 0, "y": 0}),
                _kf({"x": 4}),
                _kf({"y": 9}, 0, dwell=1),
                _kf({"x": 1, "late": 5}, 1.25),
            ],
            defaults={
                "transition": {"duration": 0.75, "timing": "ease"},
                "dwell": 0.25,
            },
        ),
    ),
    (
        "per-field-timing",
        "A segment-wide timing with per-field overrides on a number and an angle.",
        _seq(
            {"x": {"kind": "number"}, "y": {"kind": "number"}, "a": {"kind": "angle"}},
            [
                _kf({"x": 0, "y": 0, "a": 0}),
                _kf(
                    {"x": 1, "y": 1, "a": 90},
                    2,
                    "ease-in",
                    enter={
                        "fields": {
                            "y": {"timing": "linear"},
                            "a": {"timing": "steps(3)"},
                        }
                    },
                ),
            ],
        ),
    ),
    (
        "loop",
        "A seamless loop: the last keyframe equals the first.",
        _seq(
            {"spin": {"kind": "angle"}},
            [
                _kf({"spin": 0}),
                _kf({"spin": 120}, 1),
                _kf({"spin": 240}, 1),
                _kf({"spin": 0}, 1),
            ],
        ),
    ),
    (
        "orbit-overshoot",
        "An orbit under an overshooting timing: elevation is clamped at the pole, azimuth and distance extrapolate.",
        _seq(
            {"camera": {"kind": "orbit"}},
            [
                _kf({"camera": {"azimuth": 0, "elevation": 0, "distance": 1}}),
                _kf(
                    {"camera": {"azimuth": 90, "elevation": 80, "distance": 4}},
                    1,
                    "cubic-bezier(0.3, 2.2, 0.6, 1.2)",
                ),
            ],
        ),
    ),
    (
        "manim-rate-functions",
        "Manim rate functions as segment easings, including two that end where they began.",
        _seq(
            {"x": {"kind": "number"}},
            [
                _kf({"x": 0}),
                _kf({"x": 10}, 1, "smooth"),
                _kf({"x": 20}, 1, "there_and_back"),
                _kf({"x": 30}, 1, "rush_into"),
                _kf({"x": 40}, 1, "wiggle"),
            ],
        ),
    ),
]


# -----------------------------------------------------------------------------
# an's parity cases (stage.node)
# -----------------------------------------------------------------------------

#: The an#86 boundary keyframes: at nextafter(B, 0), (t - A) / (B - A) == 1.0.
BOUNDARY_A: float = 0.1524221856720187
BOUNDARY_B: float = 9.767899248713501
#: Legacy-solver curves whose evaluation reaches the 8-step Newton loop's slope
#: guard and its clamps (mid-curve for [1, 0, 0, 1], near the ends for the others).
SOLVER_PROBE_BEZIERS: tuple[list[float], ...] = (
    [1.0, 0.0, 0.0, 1.0],
    [0.42, 0.0, 1.0, 1.0],
    [0.0, 0.0, 0.58, 1.0],
)
LEGACY_NAMES: tuple[str, ...] = (
    "linear",
    "ease",
    "ease_in",
    "ease_out",
    "ease_in_out",
    "step",
)


def _key(time: float, value: Any, easing: Any = None) -> dict:
    return {"time": time, "value": value, "easing": easing}


def _anim(
    name: str, duration: float, channels: list[dict], loop_mode: str = "once"
) -> dict:
    return {
        "name": name,
        "duration": duration,
        "loop_mode": loop_mode,
        "channels": channels,
    }


def _channel(target: str, prop: str, keys: list[dict]) -> dict:
    return {"target": target, "property": prop, "keyframes": keys}


def _placed(
    aid: str, start: float = 0.0, *, duration: float | None = None, speed: float = 1.0
) -> dict:
    return {
        "animation_id": aid,
        "start_time": start,
        "duration": duration,
        "speed": speed,
        "blend_in": 0.0,
        "blend_out": 0.0,
    }


def _doc(
    duration: float, tracks: list[list[dict]], animations: dict[str, dict]
) -> dict:
    return {
        "timeline": {
            "duration": duration,
            "tracks": [{"target_root": "", "clips": clips} for clips in tracks],
        },
        "animations": animations,
    }


def _rows_case(
    rows: list[tuple[str, str, list[dict]]], *, clip_duration: float
) -> dict:
    """One clip per row, each on its own track and target, all placed at 0."""
    animations = {}
    tracks = []
    for i, (target, prop, keys) in enumerate(rows):
        aid = f"row{i}"
        animations[aid] = _anim(aid, clip_duration, [_channel(target, prop, keys)])
        tracks.append([_placed(aid)])
    return _doc(clip_duration, tracks, animations)


def _ramp(
    name: str,
    target: str = "a",
    prop: str = "x",
    *,
    start: float = 0.0,
    end: float = 10.0,
    duration: float = 1.0,
    loop_mode: str = "once",
) -> dict:
    return _anim(
        name,
        duration,
        [_channel(target, prop, [_key(0.0, start), _key(duration, end)])],
        loop_mode,
    )


def _an_cases() -> list[dict]:
    overshoots = [[0.5, 2.0, 0.5, 2.0], [0.3, 3.0, 0.7, 0.0]]
    cases = [
        {
            "name": "an-numeric-easings",
            "description": "Every stage easing and legacy-solver Béziers (one overshooting; three that reach the solver's slope guard and clamps) on a 0 to 10 ramp.",
            "document": _rows_case(
                [
                    (f"e{i}", "x", [_key(0.0, 0.0, e), _key(1.0, 10.0)])
                    for i, e in enumerate(
                        [
                            *LEGACY_NAMES,
                            [0.42, 0.0, 0.58, 1.0],
                            overshoots[0],
                            *SOLVER_PROBE_BEZIERS,
                        ]
                    )
                ],
                clip_duration=1.0,
            ),
            "extra_times": [1e-6, 0.146, 0.4, 0.501, 0.66, 0.999, 0.9999999, 1 - 1e-6],
        },
        {
            "name": "an-large-magnitude-bezier",
            "description": "Legacy-solver Béziers from 1e9 to 0: a ULP of easing is amplified by the span, so the solver's loop must match exactly.",
            "document": _rows_case(
                [
                    (f"b{i}", "x", [_key(1.1, 1.0e9, e), _key(1.71, 0.0)])
                    for i, e in enumerate([[0.42, 0.0, 0.58, 1.0], *overshoots])
                ],
                clip_duration=2.0,
            ),
            "extra_times": [1.7099999989999999],
        },
        {
            "name": "an-86-boundary",
            "description": "A swap held on time: at the float just below the second key, (t - a) / span rounds to 1.0, and the first key still shows.",
            "document": _rows_case(
                [
                    (
                        "hand",
                        "hands",
                        [_key(BOUNDARY_A, "A", "step"), _key(BOUNDARY_B, "B")],
                    )
                ],
                clip_duration=10.0,
            ),
            "extra_times": [math.nextafter(BOUNDARY_B, 0.0), BOUNDARY_B],
        },
        {
            "name": "an-swap-holds-under-any-easing",
            "description": "A swap set holds its first key for the whole segment under every easing, overshooting Béziers included, and switches exactly at the second key.",
            "document": _rows_case(
                [
                    (f"s{i}", "hands", [_key(0.0, "A", e), _key(1.0, "B")])
                    for i, e in enumerate([*LEGACY_NAMES, *overshoots])
                ],
                clip_duration=1.0,
            ),
            "extra_times": [
                0.146,
                0.257,
                0.652,
                0.999,
                0.9999999,
                math.nextafter(1.0, 0.0),
            ],
        },
        {
            "name": "an-swap-shapes",
            "description": "A three-key viseme track, duplicate-time keys (the later wins), a single-key channel, and booleans held like any swap value.",
            "document": _rows_case(
                [
                    (
                        "mouth",
                        "viseme",
                        [
                            _key(0.0, "X", "step"),
                            _key(0.4, "C", "step"),
                            _key(1.0, "X", "step"),
                        ],
                    ),
                    (
                        "hand",
                        "hands",
                        [
                            _key(0.0, "A", "step"),
                            _key(0.5, "B", "step"),
                            _key(0.5, "C", "step"),
                            _key(1.0, "D", "step"),
                        ],
                    ),
                    ("lone", "hands", [_key(0.25, "only")]),
                    ("flag", "visible", [_key(0.0, True, "linear"), _key(1.0, False)]),
                ],
                clip_duration=1.0,
            ),
            "extra_times": [0.399, 0.4, 0.499, 0.5, 0.75],
        },
    ]
    plain = _anim(
        "plain",
        1.0,
        [_channel("m", "viseme", [_key(0.0, "A", "step"), _key(0.5, "X")])],
    )
    happy = _anim(
        "happy", 0.5, [_channel("m", "viseme@happy", [_key(0.0, "D", "step")])]
    )
    timelines = [
        (
            "an-held-end-value",
            "A clip placed at 0.5: at rest before, active during, its end value held after.",
            _doc(10.0, [[_placed("ramp", 0.5)]], {"ramp": _ramp("ramp")}),
        ),
        (
            "an-swap-write-group",
            "viseme and viseme@happy share one write group: only the most recently written shows.",
            _doc(
                10.0,
                [[_placed("plain", 0.0), _placed("happy", 1.5), _placed("plain", 2.5)]],
                {"plain": plain, "happy": happy},
            ),
        ),
        (
            "an-alias-write-group",
            "rotation_rad writes rotation: the later write of the two shows.",
            _doc(
                10.0,
                [[_placed("r", 0.0), _placed("rot", 1.25)]],
                {
                    "r": _ramp("r", prop="rotation", end=3.0),
                    "rot": _ramp("rot", prop="rotation_rad", end=1.0),
                },
            ),
        ),
        (
            "an-speed",
            "A clip at double speed occupies half its duration.",
            _doc(10.0, [[_placed("ramp", 0.5, speed=2.0)]], {"ramp": _ramp("ramp")}),
        ),
        (
            "an-loop",
            "A looping clip whose window ends mid-cycle holds the value at the window's end.",
            _doc(
                10.0,
                [[_placed("loop", 0.0, duration=2.5)]],
                {"loop": _ramp("loop", loop_mode="loop")},
            ),
        ),
        (
            "an-ping-pong",
            "A ping-pong clip bounces over its duration.",
            _doc(
                10.0,
                [[_placed("pp", 0.25, duration=1.6)]],
                {"pp": _ramp("pp", loop_mode="ping_pong")},
            ),
        ),
        (
            "an-step-swap-clip",
            "A step swap clip placed at 1.0.",
            _doc(
                10.0,
                [[_placed("swap", 1.0)]],
                {
                    "swap": _anim(
                        "swap",
                        1.0,
                        [
                            _channel(
                                "a",
                                "view",
                                [_key(0.0, "FRONT", "step"), _key(0.5, "SIDE")],
                            )
                        ],
                    )
                },
            ),
        ),
        (
            "an-playing-beats-held",
            "A clip still playing on an earlier track beats one that ended on a later track.",
            _doc(
                10.0,
                [[_placed("long", 0.0)], [_placed("short", 0.5)]],
                {
                    "long": _ramp("long", end=100.0, duration=4.0),
                    "short": _ramp("short", end=-1.0),
                },
            ),
        ),
        (
            "an-latest-end-and-tie",
            "The latest end holds; a tie goes to the later clip; another property is independent.",
            _doc(
                10.0,
                [
                    [
                        _placed("late", 1.0),
                        _placed("early", 0.0),
                        _placed("tie", 1.0),
                        _placed("y", 2.0),
                    ]
                ],
                {
                    "late": _ramp("late", end=2.0),
                    "early": _ramp("early", end=1.0),
                    "tie": _ramp("tie", end=3.0),
                    "y": _ramp("y", prop="y", end=7.0),
                },
            ),
        ),
        (
            "an-cross-track-inclusive-end",
            "A clip is active on [start, end] inclusive: at a shared instant the later track wins, whether its clip starts or ends there.",
            _doc(
                4.0,
                [
                    [_placed("up", 0.0)],
                    [_placed("down", 1.0)],
                    [_placed("late_start", 3.0)],
                    [_placed("ends", 2.0)],
                ],
                {
                    "up": _ramp("up", end=10.0),
                    "down": _ramp("down", start=20.0, end=30.0),
                    "late_start": _ramp("late_start", target="b", start=20.0, end=30.0),
                    "ends": _ramp("ends", target="b", start=0.0, end=10.0),
                },
            ),
        ),
    ]
    extra = {
        "an-cross-track-inclusive-end": [
            1.0,
            math.nextafter(1.0, 2.0),
            3.0,
            math.nextafter(3.0, 4.0),
        ]
    }
    for name, description, doc in timelines:
        cases.append(
            {
                "name": name,
                "description": description,
                "document": doc,
                "extra_times": extra.get(name, []),
            }
        )
    for case in cases:
        case["space"] = "stage.node"
        case["origin"] = "an"
    return cases


# -----------------------------------------------------------------------------
# Sample times
# -----------------------------------------------------------------------------


def _clip_boundaries(doc: dict) -> Iterable[float]:
    animations = doc["animations"]
    for track in doc["timeline"]["tracks"]:
        for p in track["clips"]:
            anim = animations[p["animation_id"]]
            speed = p.get("speed", 1.0)
            natural = p.get("duration") or anim["duration"]
            start = p.get("start_time", 0.0)
            end = start + natural / speed
            yield start
            yield end
            key_times = {k["time"] for ch in anim["channels"] for k in ch["keyframes"]}
            cycle = anim["duration"]
            periods = (
                1
                if anim.get("loop_mode", "once") == "once"
                else math.ceil(natural / cycle) + 1
            )
            for n in range(periods):
                for k in key_times:
                    local = n * cycle + (
                        cycle - k
                        if anim.get("loop_mode") == "ping_pong" and n % 2
                        else k
                    )
                    at = start + local / speed
                    if start <= at <= end:
                        yield at


def sample_times(doc: dict, extra: Iterable[float] = ()) -> list[float]:
    """Every boundary, every midpoint between consecutive boundaries, a grid, and ``extra``."""
    duration = doc["timeline"]["duration"]
    bounds = sorted({0.0, float(duration), *(float(b) for b in _clip_boundaries(doc))})
    mids = [(a + b) / 2 for a, b in zip(bounds, bounds[1:])]
    grid = [duration * i / GRID_STEPS for i in range(GRID_STEPS + 1)]
    return sorted({*bounds, *mids, *grid, *extra})


def cases() -> list[dict]:
    """Every vector case: ``name, description, origin, space, document, times``."""
    out = []
    for name, description, seq in SEQUENCE_CASES:
        doc, space, _ = _lower_sequence(seq)
        out.append(
            {
                "name": name,
                "description": description,
                "origin": "keyframe-sequence",
                "space": space,
                "document": doc,
                "extra_times": [],
            }
        )
    out += _an_cases()
    for case in out:
        case["times"] = sample_times(case["document"], case.pop("extra_times"))
    return out
