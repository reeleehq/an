"""The pose is a pure function of t (an#185).

`window.anSetTime(t)` used to apply only the keys a clip was PLAYING at ``t``, so
a key whose clip had ended — or not yet started — kept whatever the previous
seek left on the node. Rendering seeks forward, so every render was still
deterministic; a seek backwards (``an preview`` scrubbing, a non-monotone frame
clock, a reordered capture) was a different picture: on ``single_character``,
t=0 after t=29/30 differed from a fresh t=0 by 122 pixels, the eyes caught
mid-blink.

The rule now, per ``(target, property)``: a playing clip's value; else the value
the latest-ending clip reached AT ITS END; else rest (absent from the pose, and
restored by the runtime). Three tiers hold it:

1. the Python spec, `an.adapters.cutout.timeline.evaluate_timeline`, and the
   claim that makes the change safe: on every frame of every golden-corpus scene,
   the old forward-order behaviour (keep the last value applied) and the pure
   pose agree — so no golden frame can move;
2. `runtime.js::evaluateTimeline` against that spec under node;
3. the browser: every frame of every corpus shot captured forward, then again in
   reverse, pixel for pixel.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests._node import requires_node, run_node
from tests.test_cutout_channel_parity import _extract_js_block

from an.adapters.cutout.channel import Channel, Keyframe
from an.adapters.cutout.clip import Clip, LoopMode
from an.adapters.cutout.clip import evaluate as evaluate_clip
from an.adapters.cutout.timeline import (
    PlacedClip,
    Timeline,
    Track,
    evaluate_timeline,
    timeline_from_scene,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_JS = REPO_ROOT / "an" / "data" / "cutout_runtime" / "runtime.js"


def _ramp(name, target="a", prop="x", *, start=0.0, end=10.0, duration=1.0, **kw):
    ch = Channel(target, prop, [Keyframe(0.0, start), Keyframe(duration, end)])
    return Clip(name, duration=duration, channels=[ch], **kw)


def _one(clip, start_time=0.0, **kw):
    return Timeline(10.0, [Track("a", [PlacedClip(clip, start_time, **kw)])])


# ------------------------------------------------------------ 1. the spec


def test_a_key_nothing_has_started_writing_is_at_rest():
    assert evaluate_timeline(_one(_ramp("m"), 2.0), 1.0) == {}


def test_an_ended_clip_holds_its_end_value():
    tl = _one(_ramp("m"), 0.5)
    assert evaluate_timeline(tl, 1.5)[("a", "x")] == 10.0
    assert evaluate_timeline(tl, 9.0)[("a", "x")] == 10.0


def test_the_held_value_is_the_one_at_the_end_not_at_the_last_sample():
    """A looped clip whose window ends mid-cycle holds the value AT the window's
    end — what the timeline says, not whichever frame happened to land last."""
    clip = _ramp("m", loop_mode=LoopMode.LOOP)
    tl = _one(clip, 0.0, duration=2.5)
    assert evaluate_timeline(tl, 3.0)[("a", "x")] == pytest.approx(5.0)


def test_a_playing_clip_beats_a_held_one():
    tl = Timeline(
        10.0,
        [
            Track("a", [PlacedClip(_ramp("long", end=100.0, duration=4.0), 0.0)]),
            Track("a", [PlacedClip(_ramp("short", end=-1.0), 0.5)]),
        ],
    )
    # `short` ended at 1.5 on the later track; `long` is still playing.
    assert evaluate_timeline(tl, 2.0)[("a", "x")] == pytest.approx(50.0)


def test_the_latest_end_holds_and_a_tie_goes_to_the_later_clip():
    early = _ramp("early", end=1.0)
    late = _ramp("late", end=2.0)
    tl = Timeline(10.0, [Track("a", [PlacedClip(late, 1.0), PlacedClip(early, 0.0)])])
    assert evaluate_timeline(tl, 5.0)[("a", "x")] == 2.0  # ends at 2.0 beats 1.0
    tie = Timeline(10.0, [Track("a", [PlacedClip(early, 0.0), PlacedClip(late, 0.0)])])
    assert evaluate_timeline(tie, 5.0)[("a", "x")] == 2.0


def _forward_only(tl, t):
    """The pre-an#185 rule: only the clips PLAYING at t write."""
    out = {}
    for track in tl.tracks:
        for p in track.clips:
            if p.start_time <= t <= p.end_time:
                out.update(evaluate_clip(p.clip, (t - p.start_time) * p.speed))
    return out


def _corpus_shots():
    import warnings

    from an.adapters.cutout.compile import compile_shot
    from an.bench.capture import stage_copy
    from an.bench.corpus import DFLT_FIXTURES
    from an.project import load

    def shots(tmp):
        for name, fixture in sorted(DFLT_FIXTURES.items()):
            copy = stage_copy(REPO_ROOT / fixture.path, tmp / name)
            if fixture.prepare is not None:
                fixture.prepare(copy)
            project = load(copy)
            meta = project.scene.meta
            for shot in project.scene.timeline:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    doc = compile_shot(
                        shot,
                        mall=project.mall,
                        fps=int(round(meta.fps)),
                        width=meta.resolution.width,
                        height=meta.resolution.height,
                    )
                yield name, shot, meta.fps, project, doc

    return shots


def test_forward_order_and_the_pure_pose_agree_on_every_corpus_frame(tmp_path):
    """Why no golden frame moved: rendering seeks 0..N-1 in order, and on that
    path the old keep-the-last-value behaviour and the pure pose give the same
    pose on every frame of every corpus scene. A future scene where a clip ends
    off the frame grid mid-move would make them differ — and this names it."""
    bad = []
    for name, shot, fps, _, doc in _corpus_shots()(tmp_path):
        tl = timeline_from_scene(doc)
        state: dict = {}
        for i in range(max(1, int(round(shot.duration * fps)))):
            t = i / float(fps)
            state.update(_forward_only(tl, t))
            if state != evaluate_timeline(tl, t):
                bad.append(f"{name}/{shot.id} frame {i}")
    assert not bad, bad[:10]


# ------------------------------------------------ 2. runtime.js vs the spec

_TIMES = [-0.1, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 5.0, 9.0]


def _battery() -> list[Timeline]:
    ramp = _ramp("ramp")
    step = Clip(
        "swap",
        1.0,
        [Channel("a", "view", [Keyframe(0.0, "FRONT", "step"), Keyframe(0.5, "SIDE")])],
    )
    return [
        _one(ramp, 0.5),
        _one(ramp, 0.5, speed=2.0),
        _one(_ramp("loop", loop_mode=LoopMode.LOOP), 0.0, duration=2.5),
        _one(_ramp("pp", loop_mode=LoopMode.PING_PONG), 0.25, duration=1.6),
        _one(step, 1.0),
        Timeline(
            10.0,
            [
                Track("a", [PlacedClip(_ramp("long", end=100.0, duration=4.0), 0.0)]),
                Track("a", [PlacedClip(_ramp("short", end=-1.0), 0.5)]),
            ],
        ),
        Timeline(
            10.0,
            [
                Track(
                    "a",
                    [
                        PlacedClip(_ramp("late", end=2.0), 1.0),
                        PlacedClip(_ramp("early", end=1.0), 0.0),
                        PlacedClip(_ramp("tie", end=3.0), 1.0),
                        PlacedClip(_ramp("y", prop="y", end=7.0), 2.0),
                    ],
                )
            ],
        ),
    ]


def _as_scene(tl: Timeline) -> dict:
    animations, tracks = {}, []
    for track in tl.tracks:
        clips = []
        for p in track.clips:
            c = p.clip
            animations[c.name] = {
                "duration": c.duration,
                "loop_mode": c.loop_mode.value,
                "channels": [
                    {
                        "target": ch.target,
                        "property": ch.property,
                        "keyframes": [
                            {"time": k.time, "value": k.value, "easing": k.easing}
                            for k in ch.keyframes
                        ],
                    }
                    for ch in c.channels
                ],
            }
            clips.append(
                {
                    "animation_id": c.name,
                    "start_time": p.start_time,
                    "duration": p.duration,
                    "speed": p.speed,
                }
            )
        tracks.append({"clips": clips})
    return {"timeline": {"tracks": tracks}, "animations": animations}


@requires_node
def test_the_runtime_evaluates_the_timeline_exactly_as_the_spec():
    src = RUNTIME_JS.read_text(encoding="utf-8")
    battery = _battery()
    script = "\n".join(
        [
            _extract_js_block(src, "const EASINGS ="),
            _extract_js_block(src, "function cubicBezier"),
            _extract_js_block(src, "function applyEasing"),
            _extract_js_block(src, "function evaluateChannel"),
            _extract_js_block(src, "function wrapTime"),
            _extract_js_block(src, "function evaluateTimeline"),
            "let scene = null;",
            f"const scenes = {json.dumps([_as_scene(tl) for tl in battery])};",
            f"const times = {json.dumps(_TIMES)};",
            "const out = scenes.map(s => { scene = s; "
            "return times.map(t => evaluateTimeline(t)); });",
            "console.log(JSON.stringify(out));",
        ]
    )
    proc = run_node(script)
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    js = json.loads(proc.stdout)
    mismatches = []
    for i, (tl, row) in enumerate(zip(battery, js)):
        for t, got in zip(_TIMES, row):
            want = {f"{k[0]}::{k[1]}": v for k, v in evaluate_timeline(tl, t).items()}
            if got.keys() != want.keys() or any(
                got[k] != pytest.approx(want[k], rel=1e-12, abs=1e-12)
                if isinstance(want[k], float)
                else got[k] != want[k]
                for k in want
            ):
                mismatches.append((i, t, want, got))
    assert not mismatches, mismatches[:5]


# ------------------------------------------------------ 3. in the browser


def _capture(page, frames: list[int], fps: float) -> dict[int, str]:
    """``{frame: sha256 of the decoded RGB}``, seeking in the order given."""
    import numpy as np

    from an.adapters.cutout.canvas_capture import decode_data_url, opaque_rgb

    reply = page.evaluate(
        "(r) => window.anCaptureFrames(r)",
        [{"frame": i, "times": [i / float(fps)]} for i in frames],
    )
    assert "error" not in reply, reply
    out = {}
    for f in reply["frames"]:
        png = decode_data_url(f["pngs"][0], frame=f["frame"])
        arr = np.asarray(opaque_rgb(png, frame=f["frame"]))
        out[f["frame"]] = hashlib.sha256(arr.tobytes()).hexdigest()
    return out


@pytest.mark.browser
def test_every_corpus_frame_is_the_same_picture_seeked_backwards(tmp_path):
    """Each shot captured 0..N-1 (what a render does), then N-1..0 in the SAME
    page — so every frame k is seeked right after a frame later than it."""
    from playwright.sync_api import sync_playwright

    from an.adapters.cutout.render import (
        _LOAD_SCENE_JS,
        DETERMINISTIC_CHROMIUM_ARGS,
        _serve_dir,
        _stage_job,
    )
    from an.adapters.cutout.serialize import to_dict

    bad = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=list(DETERMINISTIC_CHROMIUM_ARGS), headless=True)
        try:
            for name, shot, fps, project, doc in _corpus_shots()(tmp_path / "src"):
                job = _stage_job(tmp_path / "work" / name, shot.id, doc, mall=project.mall)
                with _serve_dir(job.runtime_dir) as base_url:
                    page = browser.new_page(
                        viewport={"width": doc.meta.width, "height": doc.meta.height}
                    )
                    page.goto(f"{base_url}/index.html")
                    page.wait_for_function("() => window.anLoadScene && window.PIXI")
                    page.evaluate(
                        _LOAD_SCENE_JS, {"scene": to_dict(doc), "timeoutMs": 30000}
                    )
                    n = max(1, int(round(shot.duration * fps)))
                    forward = _capture(page, list(range(n)), fps)
                    backward = _capture(page, list(range(n))[::-1], fps)
                    page.close()
                bad += [f"{name}/{shot.id} frame {k}" for k in forward if forward[k] != backward[k]]
        finally:
            browser.close()
    assert not bad, f"{len(bad)} frames depend on seek order, e.g. {bad[:5]}"
