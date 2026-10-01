"""The engine seam (an#247): any seekable engine becomes a ``Renderer`` with no edit to the core.

Two engines are written HERE, outside ``an/engines`` and ``an/media``, the way a
package that is not ``an`` would write them:

- a TIME-driven one (it evaluates its own document), and
- a STATE-driven one shaped like ``burns``: the state is a crop rectangle over a
  still image, the core evaluates ``at(t)`` from an ``an.timing`` timeline, and
  the engine only crops.

They are the proof that ``frame_stage_renderer`` owns the clock, the capture
loop, the resolves and the sink: neither engine implements any of them.
Offline except the one test marked ``ffmpeg``, which muxes for real.
"""

from __future__ import annotations

import io
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

from an.adapters._base import RenderContext, Renderer
from an.engines import (
    DRIVE_STATE,
    DRIVE_TIME,
    TIER_LIVE,
    TIER_SEEKABLE,
    FrameJob,
    FrameRequest,
    FrameStageError,
    StateDrivenAdapter,
    UnseekableEngineError,
    capture_frames,
    describe,
    frame_stage_renderer,
)
from an.ir.schema import Shot
from an.media.frames import frame_path

W, H = 8, 6


def _png(rgb: np.ndarray) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8)).save(out, format="PNG")
    return out.getvalue()


def _decoded(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


# ------------------------------------------------------------ two outside engines


class GreyRamp:
    """Time-driven: the frame at ``t`` is a flat grey of level ``round(100 * t)``."""

    name = "grey-ramp"

    def __init__(self, *, batch: bool = False):
        self.batch = batch
        self.opened: list[FrameJob] = []

    @contextmanager
    def open(self, job: FrameJob):
        self.opened.append(job)
        k = job.supersample
        size = (job.size[1] * k, job.size[0] * k)
        yield (_BatchedRamp if self.batch else _Ramp)(size)


class _Ramp:
    def __init__(self, size):
        self.size = size
        self.seeks: list[float] = []

    def state(self, t):
        return {("plate", "level"): round(100 * t)}

    def frame(self, t):
        self.seeks.append(t)
        level = self.state(t)[("plate", "level")]
        return _png(np.full((*self.size, 3), level))

    def provenance(self):
        return {"ramp": "grey"}


class _BatchedRamp(_Ramp):
    def __init__(self, size):
        super().__init__(size)
        self.round_trips = 0
        self.resolved = 0

    def frames(self, requests):
        self.round_trips += 1
        return [[self.frame(t) for t in r.times] for r in requests]

    def resolve(self, samples, *, frame, factor, size):
        from an.media.shutter import mean_png_bytes

        self.resolved += 1
        return mean_png_bytes(samples, factor=factor)


class CropOverStill:
    """State-driven, ``burns``-shaped: the state is a crop rectangle; the core evaluates it."""

    name = "crop"

    def __init__(self, still: np.ndarray, timeline):
        self.still = still
        self.timeline = timeline

    @contextmanager
    def open(self, job: FrameJob):
        yield _CropSession(self.still, self.timeline, job.size)


class _CropSession:
    def __init__(self, still, timeline, size):
        self.still, self.timeline, self.size = still, timeline, size
        self.states = []

    def render(self, state):
        from PIL import Image

        self.states.append(dict(state))
        x = int(state.get(("camera", "x"), 0))
        crop = self.still[:, x : x + self.size[0]]
        return _png(np.asarray(Image.fromarray(crop).resize(self.size)))


def _crop_timeline(duration=1.0, travel=4.0):
    from an.timing.channel import Channel, Keyframe
    from an.timing.clip import Clip
    from an.timing.timeline import PlacedClip, Timeline, Track

    ch = Channel("camera", "x", [Keyframe(0.0, 0.0), Keyframe(duration, travel)])
    return Timeline(duration, [Track("camera", [PlacedClip(Clip("pan", duration, [ch]), 0.0)])])


@pytest.fixture
def no_mux(monkeypatch):
    """Stop at the sink: record what it was handed instead of running ffmpeg."""
    import an.media.mp4 as mp4

    calls = []

    def fake_mux_shot(frames_dir, shot, ctx, work_dir, output_mp4, *, n_frames, pix_fmt=None):
        calls.append({"frames": sorted(Path(frames_dir).glob("*.png")), "n": n_frames, "pix_fmt": pix_fmt})
        Path(output_mp4).write_bytes(b"")
        return 0

    monkeypatch.setattr(mp4, "ensure_ffmpeg", lambda: None)
    monkeypatch.setattr(mp4, "mux_shot", fake_mux_shot)
    return calls


def _ctx(tmp_path, **kw):
    return RenderContext(mall={}, work_dir=tmp_path, fps=kw.pop("fps", 10), resolution=(W, H), **kw)


# -------------------------------------------------------------- the protocol


def test_capabilities_are_read_from_members_never_from_flags():
    assert describe(_Ramp((H, W))).drive == DRIVE_TIME
    assert "readback" in describe(_Ramp((H, W))).features
    profile = describe(_BatchedRamp((H, W)))
    assert {"batch", "resolve", "readback", "provenance"} <= profile.features
    assert describe(_CropSession(None, None, (W, H))).drive == DRIVE_STATE

    class Live:
        def apply(self, state): ...
        def settle(self): ...
        def capture(self): ...

    assert describe(Live()).tier == TIER_LIVE
    assert describe(_Ramp((H, W))).tier == TIER_SEEKABLE
    # A flag cannot claim what a member does not provide.
    class Liar:
        features = ("bounds", "alpha")
        traits = {"alpha": True}

    assert describe(Liar()).tier is None and not describe(Liar()).features


def test_a_live_engine_is_refused_by_name_never_silently_captured(tmp_path, no_mux):
    class LiveOnly:
        name = "live"

        @contextmanager
        def open(self, job):
            class S:
                def apply(self, state): ...
                def settle(self): ...
                def capture(self): return b""

            yield S()

    renderer = frame_stage_renderer(LiveOnly())
    with pytest.raises(FrameStageError, match="live tier is declared, not built"):
        renderer.render(Shot(id="s", duration=0.2), _ctx(tmp_path))


def test_the_renderer_is_a_renderer_and_claims_what_it_is_told():
    r = frame_stage_renderer(GreyRamp(), renderers=("ramp", "legacy-ramp"))
    assert isinstance(r, Renderer)
    assert r.name == "grey-ramp"
    assert r.can_render(Shot(id="a", renderer="legacy-ramp"))
    assert not r.can_render(Shot(id="b", renderer="cutout"))
    with pytest.raises(TypeError, match="lacks: open"):
        frame_stage_renderer(type("NoOpen", (), {"name": "x"})())


# ---------------------------------------------------------- the core owns the clock


def test_the_core_owns_the_clock_and_writes_every_frame(tmp_path, no_mux):
    engine = GreyRamp()
    result = frame_stage_renderer(engine).render(Shot(id="s", duration=0.5), _ctx(tmp_path))
    job = engine.opened[0]
    assert job.total_frames == 5 and [r.times for r in job.requests()] == [
        (0.0,), (0.1,), (0.2,), (0.3,), (0.4,)
    ]
    assert [p.name for p in result.frame_manifest] == [
        frame_path(Path("."), i).name for i in range(5)
    ]
    assert [int(_decoded(p)[0, 0, 0]) for p in result.frame_manifest] == [0, 10, 20, 30, 40]
    assert result.provenance["engine"] == "grey-ramp"
    assert result.provenance["ramp"] == "grey", "the session's own provenance is merged"
    assert result.provenance["frame_count"] == 5
    assert no_mux[0]["n"] == 5
    assert result.mp4_path == tmp_path / "shot_s" / "s.mp4"


def test_a_lone_frame_at_supersample_one_reaches_disk_untouched(tmp_path):
    """Off is free: the engine's own bytes, nothing decoded or re-encoded."""
    session = _Ramp((H, W))
    capture_frames(session, [FrameRequest(0, (0.3,))], tmp_path)
    assert frame_path(tmp_path, 0).read_bytes() == session.frame(0.3)


def test_supersampling_is_resolved_in_the_frame_stage(tmp_path, no_mux):
    result = frame_stage_renderer(GreyRamp()).render(
        Shot(id="s", duration=0.2), _ctx(tmp_path, supersample=2)
    )
    for path in result.frame_manifest:
        assert _decoded(path).shape == (H, W, 3), "the declared size, never k times it"
    assert result.provenance["supersample"] == 2


def test_an_open_shutter_averages_the_instants_of_a_frame(tmp_path, no_mux):
    samples = ((0.0, 0.2), (0.3, 0.5))
    result = frame_stage_renderer(GreyRamp()).render(
        Shot(id="s", duration=0.5), _ctx(tmp_path, fps=4, frame_samples=samples)
    )
    assert [int(_decoded(p)[0, 0, 0]) for p in result.frame_manifest] == [10, 40]
    assert result.provenance["frame_samples"] == [[0.0, 0.2], [0.3, 0.5]]


def test_a_batched_session_is_driven_in_round_trips_with_its_own_resolve(tmp_path):
    session = _BatchedRamp((H, W))
    requests = [FrameRequest(i, (i / 10,)) for i in range(7)]
    capture_frames(session, requests, tmp_path, size=(W, H), batch=3)
    assert session.round_trips == 3
    assert session.resolved == 7, "the session's resolve replaces the core's"
    assert sorted(p.name for p in tmp_path.glob("*.png")) == [
        frame_path(tmp_path, i).name for i in range(7)
    ]


def test_a_dropped_frame_is_refused_not_muxed(tmp_path):
    class Dropping(_BatchedRamp):
        def frames(self, requests):
            return super().frames(requests)[:-1]

    with pytest.raises(FrameStageError, match="returned 1 frame"):
        capture_frames(Dropping((H, W)), [FrameRequest(0, (0.0,)), FrameRequest(1, (0.1,))], tmp_path)


def test_core_errors_leave_as_the_renderers_own_type(tmp_path, monkeypatch):
    class MyRenderError(RuntimeError):
        pass

    import an.media.mp4 as mp4

    monkeypatch.setattr(mp4, "ensure_ffmpeg", lambda: None)
    renderer = frame_stage_renderer(GreyRamp(), error=MyRenderError)
    with pytest.raises(MyRenderError, match="pix_fmt='rgb24' is not one of"):
        renderer.render(Shot(id="s", duration=0.1), _ctx(tmp_path, pix_fmt="rgb24"))


# --------------------------------------------------------- a state-driven engine


def test_a_state_driven_engine_gets_states_the_core_evaluated(tmp_path, no_mux):
    """``burns``-shaped: the engine never sees a time, only crop rectangles."""
    still = np.zeros((H, W + 4, 3), np.uint8)
    still[:, :, 0] = np.arange(W + 4) * 20  # a red ramp across the still
    engine = CropOverStill(still, _crop_timeline(duration=1.0, travel=4.0))
    result = frame_stage_renderer(engine).render(Shot(id="pan", duration=1.0), _ctx(tmp_path, fps=4))
    # The camera pans 4 px over the shot, so the left edge's red climbs 20 per px.
    lefts = [int(_decoded(p)[0, 0, 0]) for p in result.frame_manifest]
    assert lefts == [0, 20, 40, 60]


def test_the_state_adapter_reads_back_what_it_handed_over():
    session = _CropSession(None, _crop_timeline(), (W, H))
    adapter = StateDrivenAdapter(session)
    assert adapter.state(0.5) == {("camera", "x"): 2.0}
    assert not hasattr(adapter, "frames"), "a state-driven batch would bypass `state`"


def test_an_engine_with_neither_drive_mode_says_what_to_add(tmp_path, no_mux):
    class Blank:
        name = "blank"

        @contextmanager
        def open(self, job):
            yield object()

    with pytest.raises(FrameStageError, match=r"Add frame\(t\) and state\(t\)"):
        frame_stage_renderer(Blank()).render(Shot(id="s", duration=0.1), _ctx(tmp_path))
    with pytest.raises(UnseekableEngineError):
        frame_stage_renderer(Blank(), error=UnseekableEngineError).render(
            Shot(id="s", duration=0.1), _ctx(tmp_path)
        )


# ---------------- what the core owns, pinned (review of an#250, S1 and S6)


def test_the_frame_count_rounds_it_never_truncates(tmp_path, no_mux):
    """0.17 s at 10 fps is 1.7 frames: two, as `an.frame_clock.frame_count` says."""
    result = frame_stage_renderer(GreyRamp()).render(Shot(id="s", duration=0.17), _ctx(tmp_path))
    assert result.provenance["frame_count"] == 2 and len(result.frame_manifest) == 2


def test_a_sequential_sessions_own_resolve_is_used_even_at_supersample_one(tmp_path):
    """The byte passthrough is the CORE's resolve's shortcut, never a bypass of
    an engine that asked to normalise its own frames."""

    class Normalising(_Ramp):
        calls = 0

        def resolve(self, samples, *, frame, factor, size):
            type(self).calls += 1
            return b"normalised"

    capture_frames(Normalising((H, W)), [FrameRequest(0, (0.1,))], tmp_path)
    assert Normalising.calls == 1
    assert frame_path(tmp_path, 0).read_bytes() == b"normalised"


def test_the_recorded_argv_follows_the_high_crf_lever(tmp_path, no_mux):
    """The provenance the frame stage writes, not just the module global."""
    from an.bench.mutations import HIGH_CRF, LEVERS

    with LEVERS["high_crf"].apply():
        result = frame_stage_renderer(GreyRamp()).render(Shot(id="s", duration=0.1), _ctx(tmp_path))
    argv = result.provenance["x264_args"]
    assert argv[argv.index("-crf") + 1] == HIGH_CRF


def test_frames_left_by_a_longer_earlier_render_are_cleared(tmp_path, no_mux):
    renderer = frame_stage_renderer(GreyRamp())
    renderer.render(Shot(id="s", duration=0.5), _ctx(tmp_path))
    result = renderer.render(Shot(id="s", duration=0.3), _ctx(tmp_path))
    assert len(result.frame_manifest) == 3
    assert no_mux[-1]["frames"] == result.frame_manifest


def test_a_state_driven_session_is_evaluated_in_its_own_space(tmp_path, no_mux):
    """A log-space zoom from 1 to 4 is 2 at the midpoint (linear would say 2.5)."""
    from an.timing.channel import Channel, Keyframe
    from an.timing.clip import Clip
    from an.timing.kinds import NumberKind
    from an.timing.spaces import FieldDecl, PropertySpace
    from an.timing.timeline import PlacedClip, Timeline, Track

    zoom = Channel("camera", "zoom", [Keyframe(0.0, 1.0), Keyframe(1.0, 4.0)])
    timeline = Timeline(1.0, [Track("camera", [PlacedClip(Clip("z", 1.0, [zoom]), 0.0)])])
    seen = []

    class Zoomer:
        name = "zoomer"

        @contextmanager
        def open(self, job):
            class S:
                space = PropertySpace("demo.camera", (FieldDecl("zoom", NumberKind(space="log")),))

                def __init__(self):
                    self.timeline = timeline

                def render(self, state):
                    seen.append(state[("camera", "zoom")])
                    return _png(np.zeros((H, W, 3)))

            yield S()

    frame_stage_renderer(Zoomer()).render(Shot(id="s", duration=1.0), _ctx(tmp_path, fps=2))
    assert seen[1] == pytest.approx(2.0)


def test_the_engines_own_check_runs_before_it_is_opened(tmp_path, no_mux):
    class Picky(GreyRamp):
        name = "picky"

        def check(self, ctx):
            raise ValueError("no such capture path")

    engine = Picky()
    with pytest.raises(ValueError, match="no such capture path"):
        frame_stage_renderer(engine).render(Shot(id="s", duration=0.1), _ctx(tmp_path))
    assert engine.opened == []


def test_an_engine_cannot_restate_what_the_core_recorded(tmp_path, no_mux):
    """S1: a session claiming another argv, pixel format, frame count or name
    would make the record lie about the file."""

    class Liar(GreyRamp):
        name = "liar"

        @contextmanager
        def open(self, job):
            session = _Ramp((job.size[1], job.size[0]))
            session.provenance = lambda: {"x264_args": ["-crf", "0"], "pix_fmt": "yuv444p"}
            yield session

    with pytest.raises(FrameStageError, match=r"\['pix_fmt', 'x264_args'\]"):
        frame_stage_renderer(Liar()).render(Shot(id="s", duration=0.1), _ctx(tmp_path))


# ------------------------------------------------------------------ the real mux


@pytest.mark.ffmpeg
def test_an_outside_engine_renders_a_playable_mp4(tmp_path):
    """End to end with ffmpeg: the pinned argv, the shot's silent audio, the frame count."""
    import subprocess

    still = np.zeros((48, 80, 3), np.uint8)
    still[:, :, 1] = 200
    engine = CropOverStill(still, _crop_timeline(duration=0.5, travel=16.0))
    ctx = RenderContext(mall={}, work_dir=tmp_path, fps=12, resolution=(64, 48))
    result = frame_stage_renderer(engine).render(Shot(id="pan", duration=0.5), ctx)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(result.mp4_path)],
        capture_output=True, text=True, check=True,
    )
    assert int(probe.stdout.strip()) == 6
    assert result.provenance["x264_args"] and result.provenance["pix_fmt"] == "yuv420p"
