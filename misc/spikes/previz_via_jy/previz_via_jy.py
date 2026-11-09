"""Spike (an#257): render a previz sequence as frames of an ``an`` shot, from Python, through jy.

Not a public API: nothing here is imported by ``an``. It answers three questions
with running code and prints the numbers the README records.

(a) Evaluation. ``jy`` reads ``previz_facade.js`` and makes Python stubs whose call
    returns a JS call STRING (jy has no runtime of its own). ``previz_host.mjs``, a
    long-lived Node process, imports previz's built ``dist/`` and evaluates those
    strings. We time the round trip and read back ``reel.at(t)``.

(b) Drawing. previz's demo engine is a software rasteriser with no DOM, so Node can
    draw it. We wrap it as an ``an`` ``Engine`` and render a shot through
    ``an.engines.frame_stage_renderer`` twice:

    - TIME-driven: the session's ``frame(t)``/``frames(requests)`` let previz evaluate
      and draw (one round trip per batch);
    - STATE-driven: the session exposes a ``timeline`` LOWERED from the previz reel
      (keyframes + transitions -> an ``an.timing`` ``Timeline`` in a
      ``PropertySpace`` built from the sequence's ``space``), the core evaluates
      ``at(t)``, and ``render_states`` hands the states to Node to draw (an#286).

    We also hold the core's evaluation to previz's at every frame time (the kernel
    is shared: an/data/timing/ is the contract previz asserts), and probe the
    page-side alternative: previz's dist loaded into a Playwright page, drawing to a
    canvas, which is where a DOM/WebGL previz engine would have to live.

(c) The adapter. ``an.engines.describe`` and ``engine_affordances`` print what a
    previz ``Engine`` offers, including the ``space.<name>`` capability.

Run from the an worktree root::

    PYTHONPATH=$PWD python misc/spikes/previz_via_jy/previz_via_jy.py --out <scratch dir>

``--previz`` defaults to ``$PP/tt/previz`` (a built checkout: ``dist/`` present).
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import functools
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FACADE = HERE / "previz_facade.js"
HOST = HERE / "previz_host.mjs"

#: The target every lowered channel writes: a previz sequence has ONE view entity.
VIEW_TARGET = "view"
DFLT_WIDTH, DFLT_HEIGHT, DFLT_FPS = 480, 360, 24
#: previz demo engine's own anti-aliasing (samples per axis); an's supersample is separate.
DEMO_SUPERSAMPLE = 2
#: Frames whose PNGs the report names (indices into the shot).
REPORT_FRAMES = (0, 30, 60, 90)
#: Instants per request when timing single round trips.
LATENCY_SAMPLES = 50
#: Frames drawn when timing the engine alone.
DRAW_SAMPLES = 16


def _default_previz_dir() -> Path | None:
    pp = os.environ.get("PP")
    return Path(pp) / "tt" / "previz" if pp else None


# --------------------------------------------------------------------------- (a)
# jy gives the stubs, Node is the runtime


class JsCallError(RuntimeError):
    """The JS side raised; the message carries its stack."""


class PrevizRuntime:
    """A Node process running previz, called through jy-made stubs.

    ``rt.load(seq, w, h, k)`` = ``rt.eval(stubs.load(seq, w, h, k))``: jy builds the
    call string from the facade's signature, the host evaluates it.
    """

    def __init__(self, previz_dir: Path, *, node: str = "node"):
        import jy

        # json.dumps, not jy's default value transformer: the default writes a
        # list of dicts as a Python repr (single quotes, True/None) and does not
        # escape strings, so a previz state would not survive it.
        self.stubs = jy.add_js_funcs(str(FACADE), value_trans=json.dumps)
        self._proc = subprocess.Popen(
            [node, str(HOST), str(previz_dir), str(FACADE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._next_id = 0
        ready = self._read()
        if not ready.get("ok"):
            raise JsCallError(f"previz host failed to start: {ready}")
        self.node_version = ready["value"]["node"]

    def _read(self) -> dict[str, Any]:
        line = self._proc.stdout.readline()
        if not line:
            err = self._proc.stderr.read()
            raise JsCallError(f"previz host exited: {err.strip()}")
        return json.loads(line)

    def eval(self, expr: str) -> Any:
        self._next_id += 1
        self._proc.stdin.write(json.dumps({"id": self._next_id, "expr": expr}) + "\n")
        self._proc.stdin.flush()
        msg = self._read()
        if not msg["ok"]:
            raise JsCallError(msg["error"])
        return msg["value"]

    def __getattr__(self, name: str):
        stub = getattr(self.stubs, name)  # AttributeError for a name jy did not find
        return lambda *a, **k: self.eval(stub(*a, **k))

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.wait(timeout=10)


@contextlib.contextmanager
def previz_runtime(previz_dir: Path) -> Iterator[PrevizRuntime]:
    rt = PrevizRuntime(previz_dir)
    try:
        yield rt
    finally:
        rt.close()


# --------------------------------------------------------------------------- lowering
# a previz reel -> an an.timing Timeline in an an.timing PropertySpace


def _get_path(state: Mapping[str, Any], path: str) -> Any:
    cur: Any = state
    for part in path.split("."):
        cur = cur[part]
    return cur


def _set_path(state: dict[str, Any], path: str, value: Any) -> None:
    *head, last = path.split(".")
    cur = state
    for part in head:
        cur = cur.setdefault(part, {})
    cur[last] = value


def _leaf_paths(state: Mapping[str, Any], prefix: str = "") -> Iterator[str]:
    for k, v in state.items():
        p = f"{prefix}{k}"
        if isinstance(v, Mapping):
            yield from _leaf_paths(v, p + ".")
        else:
            yield p


def view_paths(info: Mapping[str, Any]) -> list[str]:
    """The paths a channel is made for: every declared path, then every leaf not under one."""
    declared = list(info["space"])
    under = lambda p: any(p == d or p.startswith(d + ".") for d in declared)  # noqa: E731
    leaves = {p for s in info["states"] for p in _leaf_paths(s)}
    return declared + sorted(p for p in leaves if not under(p))


def property_space(info: Mapping[str, Any], *, name: str = "previz.view"):
    """The sequence's previz ``Space`` as an ``an.timing`` ``PropertySpace``: same kinds, same specs."""
    from an.timing.kinds import kind_from_spec
    from an.timing.spaces import FieldDecl, PropertySpace

    return PropertySpace(
        name,
        tuple(
            FieldDecl(path, kind_from_spec(spec))
            for path, spec in info["space"].items()
        ),
    )


def lower_reel(info: Mapping[str, Any]):
    """The reel as an ``an.timing`` ``Timeline`` (one clip, one channel per view path).

    One key per segment boundary: a transition's key leaves with its ``timing`` as
    the easing, a dwell's holds. Covers the straight route without per-field
    transition overrides; anything else is refused (that lowering is a follow-up).
    """
    from an.timing.channel import Channel, Keyframe
    from an.timing.clip import Clip
    from an.timing.timeline import PlacedClip, Timeline, Track

    for tr in info["transitions"]:
        if tr and (tr.get("fields") or tr.get("route", "straight") != "straight"):
            raise ValueError(
                "spike lowering covers the straight route without per-field overrides; "
                f"got {tr}"
            )
    states, segments = info["states"], info["segments"]
    channels = []
    for path in view_paths(info):
        keys = []
        for seg in segments:
            src = (
                states[seg["from"]]
                if seg["kind"] == "transition"
                else states[seg["to"]]
            )
            easing = (seg.get("transition") or {}).get("timing", "linear")
            keys.append(Keyframe(seg["start"], _get_path(src, path), easing=easing))
        keys.append(Keyframe(info["duration"], _get_path(states[-1], path)))
        channels.append(Channel(VIEW_TARGET, path, keys))
    clip = Clip("previz", info["duration"], channels)
    return Timeline(info["duration"], [Track(VIEW_TARGET, [PlacedClip(clip, 0.0)])])


def pose_to_state(pose: Mapping[Any, Any]) -> dict[str, Any]:
    """An ``an`` pose (``(target, path) -> value``) as a nested previz state."""
    state: dict[str, Any] = {}
    for (target, path), value in pose.items():
        if target == VIEW_TARGET:
            _set_path(state, path, value)
    return state


def state_to_pose(
    state: Mapping[str, Any], paths: Sequence[str]
) -> dict[tuple[str, str], Any]:
    return {(VIEW_TARGET, p): _get_path(state, p) for p in paths}


# --------------------------------------------------------------------------- (b)/(c)
# the Engine


@dataclass
class PrevizEngine:
    """A previz sequence as an ``an`` ``Engine``; ``drive`` picks who evaluates ``at(t)``.

    ``view_spaces`` is how an engine declares ``space.<name>``
    (``an.capabilities.subjects._derive_engine`` reads it off the RENDERER).
    """

    sequence: Mapping[str, Any]
    previz_dir: Path
    drive: str = "state"
    name: str = "previz"
    view_spaces: tuple[str, ...] = ("orbit3d",)
    demo_supersample: int = DEMO_SUPERSAMPLE
    #: What ``an.engines.describe`` read off the last session opened (for the report).
    last_profile: Any = field(default=None, init=False, repr=False)

    @contextlib.contextmanager
    def open(self, job):
        from an.engines import describe

        w, h = job.size
        k = job.supersample
        with previz_runtime(self.previz_dir) as rt:
            info = rt.load(dict(self.sequence), w * k, h * k, self.demo_supersample)
            session_type = _TimeSession if self.drive == "time" else _StateSession
            session = session_type(rt, info, w * k, h * k)
            self.last_profile = describe(session)
            yield session


@dataclass
class _Session:
    rt: PrevizRuntime
    info: dict[str, Any]
    width: int
    height: int
    paths: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.paths = view_paths(self.info)

    def _pngs(self, b64s: Sequence[str]) -> list[bytes]:
        return [base64.b64decode(s) for s in b64s]

    def provenance(self) -> dict[str, Any]:
        return {
            "previz_drive": "time" if isinstance(self, _TimeSession) else "state",
            "previz_engine": "demo (software raster, Node)",
            "previz_node": self.rt.node_version,
        }


@dataclass
class _TimeSession(_Session):
    """previz evaluates its own reel; the core only asks for instants."""

    def frame(self, t: float) -> bytes:
        return self._pngs(self.rt.renderTimes([t], self.width, self.height))[0]

    def frames(self, requests) -> list[list[bytes]]:
        times = [t for r in requests for t in r.times]
        pngs = self._pngs(self.rt.renderTimes(times, self.width, self.height))
        out, i = [], 0
        for r in requests:
            out.append(pngs[i : i + len(r.times)])
            i += len(r.times)
        return out

    def state(self, t: float) -> dict[tuple[str, str], Any]:
        return state_to_pose(self.rt.statesAt([t])[0], self.paths)


@dataclass
class _StateSession(_Session):
    """The core evaluates the lowered timeline; previz only draws."""

    timeline: Any = field(init=False)
    space: Any = field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.timeline = lower_reel(self.info)
        self.space = property_space(self.info)

    def render(self, state: Mapping[Any, Any]) -> bytes:
        return self.render_states([state])[0]

    def render_states(self, states: Sequence[Mapping[Any, Any]]) -> list[bytes]:
        nested = [pose_to_state(s) for s in states]
        return self._pngs(self.rt.renderStates(nested, self.width, self.height))


# --------------------------------------------------------------------------- the runs


def _max_numeric_diff(a: Any, b: Any) -> float:
    if isinstance(a, Mapping):
        return max((_max_numeric_diff(a[k], b.get(k)) for k in a), default=0.0)
    if isinstance(a, list):
        return max((_max_numeric_diff(x, y) for x, y in zip(a, b)), default=0.0)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b))
    return 0.0 if a == b else float("inf")


def part_a(previz_dir: Path, sequence: Mapping[str, Any], fps: float) -> dict[str, Any]:
    """Start, load, round-trip latency, and a batched read-back of every frame's state."""
    out: dict[str, Any] = {}
    t0 = time.perf_counter()
    with previz_runtime(previz_dir) as rt:
        out["start_s"] = time.perf_counter() - t0
        t1 = time.perf_counter()
        info = rt.load(dict(sequence), DFLT_WIDTH, DFLT_HEIGHT, DEMO_SUPERSAMPLE)
        out["load_s"] = time.perf_counter() - t1
        out["duration_s"] = info["duration"]
        out["call_string_example"] = rt.stubs.statesAt([0.5])
        t2 = time.perf_counter()
        for i in range(LATENCY_SAMPLES):
            rt.statesAt([i / LATENCY_SAMPLES * info["duration"]])
        out["single_state_roundtrip_ms"] = (
            (time.perf_counter() - t2) / LATENCY_SAMPLES * 1e3
        )
        n = max(1, round(info["duration"] * fps))
        times = [i / fps for i in range(n)]
        t3 = time.perf_counter()
        states = rt.statesAt(times)
        out["batched_states_ms"] = (time.perf_counter() - t3) * 1e3
        out["batched_states_n"] = n
        out["state_at_1s"] = states[round(fps)]
        # The engine's own draw cost, with the bridge (a PNG encode and base64 on
        # each side) but without an's frame stage: what the shot render divides into.
        t4 = time.perf_counter()
        rt.renderTimes(times[:DRAW_SAMPLES], DFLT_WIDTH, DFLT_HEIGHT)
        out["node_draw_ms_per_frame"] = (time.perf_counter() - t4) / DRAW_SAMPLES * 1e3
    out["info"] = info
    return out


def kernel_agreement(
    info: Mapping[str, Any], previz_states: Sequence[Any], times: Sequence[float]
):
    """The core's evaluation of the LOWERED reel against previz's own, at every time."""
    from an.timing.timeline import evaluate_timeline

    timeline, space = lower_reel(info), property_space(info)
    worst, mismatched = 0.0, []
    for t, expected in zip(times, previz_states):
        got = pose_to_state(evaluate_timeline(timeline, t, space=space))
        d = _max_numeric_diff(expected, got)
        worst = max(worst, d)
        if d > 1e-9:
            mismatched.append((t, d))
    return {"times": len(times), "max_abs_diff": worst, "mismatched": mismatched[:5]}


def render_shot(previz_dir: Path, sequence, drive: str, out_dir: Path, *, fps, size):
    """One shot through ``frame_stage_renderer``; the mp4 lands under ``out_dir``."""
    from an.adapters._base import RenderContext
    from an.capabilities.subjects import engine_affordances
    from an.engines import frame_stage_renderer
    from an.ir.schema import Shot

    engine = PrevizEngine(sequence, previz_dir, drive=drive)
    renderer = frame_stage_renderer(engine)
    # The frame stage's renderer does not forward its engine's `view_spaces`
    # (a follow-up); set here so the capability shows.
    renderer.view_spaces = engine.view_spaces
    work = out_dir / f"work_{drive}"
    shutil.rmtree(work, ignore_errors=True)
    ctx = RenderContext(mall={}, work_dir=work, fps=fps, resolution=size)
    with previz_runtime(previz_dir) as rt:
        duration = rt.load(dict(sequence), 8, 8, 1)["duration"]
    shot = Shot(id=f"previz_{drive}", duration=duration, renderer="previz")
    t0 = time.perf_counter()
    result = renderer.render(shot, ctx)
    elapsed = time.perf_counter() - t0
    return {
        "mp4": result.mp4_path,
        "frames": len(result.frame_manifest),
        "frame_manifest": result.frame_manifest,
        "render_s": elapsed,
        "ms_per_frame": elapsed / max(1, len(result.frame_manifest)) * 1e3,
        "profile": engine.last_profile,
        "affordances": engine_affordances(renderer),
        "provenance_engine_keys": {
            k: v
            for k, v in result.provenance.items()
            if k.startswith("previz") or k == "engine"
        },
    }


def frames_identical(a: Sequence[Path], b: Sequence[Path]) -> bool:
    import numpy as np
    from PIL import Image

    def px(p):
        with Image.open(p) as im:
            return np.asarray(im.convert("RGB"))

    return all(np.array_equal(px(x), px(y)) for x, y in zip(a, b)) and len(a) == len(b)


@contextlib.contextmanager
def _static_server(root: Path) -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass


_PAGE_SETUP = """async ([base, sequence, w, h, k]) => {
  const { compile } = await import(base + '/dist/core/compile.js');
  const { demoEngine } = await import(base + '/dist/engines/demo/index.js');
  window.__reel = compile(sequence);
  window.__engine = demoEngine({ width: w, height: h, supersample: k });
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  document.body.appendChild(c);
  window.__ctx = c.getContext('2d');
  return window.__reel.duration;
}"""

_PAGE_DRAW = """async (times) => {
  const out = [];
  for (const t of times) {
    const f = await window.__engine.render(window.__reel.at(t), { width: __ctx.canvas.width, height: __ctx.canvas.height });
    __ctx.putImageData(new ImageData(f.data, f.width, f.height), 0, 0);
    out.push(__ctx.canvas.toDataURL('image/png').split(',')[1]);
  }
  return out;
}"""


def page_probe(
    previz_dir: Path, sequence, times: Sequence[float], out_dir: Path, *, size
):
    """previz's dist in a Playwright page (where a DOM/WebGL engine must live): timing and parity."""
    from playwright.sync_api import sync_playwright

    w, h = size
    out_dir.mkdir(parents=True, exist_ok=True)
    with _static_server(previz_dir) as base, sync_playwright() as p:
        t0 = time.perf_counter()
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(base + "/package.json")  # same origin as the modules
        duration = page.evaluate(
            _PAGE_SETUP, [base, dict(sequence), w, h, DEMO_SUPERSAMPLE]
        )
        setup_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        b64s = page.evaluate(_PAGE_DRAW, list(times))
        draw_s = time.perf_counter() - t1
        browser.close()
    paths = []
    for i, s in enumerate(b64s):
        path = out_dir / f"page_{i:04d}.png"
        path.write_bytes(base64.b64decode(s))
        paths.append(path)
    return {
        "duration": duration,
        "setup_s": setup_s,
        "ms_per_frame": draw_s / max(1, len(times)) * 1e3,
        "frames": paths,
    }


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--previz", type=Path, default=_default_previz_dir())
    ap.add_argument(
        "--sequence",
        type=Path,
        default=None,
        help="default: <previz>/examples/orbit.json",
    )
    ap.add_argument(
        "--out", type=Path, default=Path(tempfile.gettempdir()) / "previz_via_jy"
    )
    ap.add_argument("--fps", type=float, default=DFLT_FPS)
    ap.add_argument("--width", type=int, default=DFLT_WIDTH)
    ap.add_argument("--height", type=int, default=DFLT_HEIGHT)
    ap.add_argument(
        "--skip-page", action="store_true", help="skip the Playwright probe"
    )
    args = ap.parse_args(argv)
    if args.previz is None or not (args.previz / "dist" / "index.js").exists():
        raise SystemExit(
            f"need a BUILT previz checkout (dist/index.js); got --previz {args.previz}"
        )
    seq_path = args.sequence or args.previz / "examples" / "orbit.json"
    sequence = json.loads(seq_path.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    size = (args.width, args.height)
    report: dict[str, Any] = {"sequence": seq_path.name, "size": size, "fps": args.fps}

    print("== (a) evaluation through jy + a Node host")
    a = part_a(args.previz, sequence, args.fps)
    info = a.pop("info")
    report["a"] = a
    print(json.dumps(a, indent=2, default=str))

    print("== kernel agreement: an.timing on the lowered reel vs previz's reel.at")
    n = max(1, round(info["duration"] * args.fps))
    dense = sorted(
        {
            *(i / args.fps for i in range(n + 1)),
            *(i * info["duration"] / 997 for i in range(998)),
        }
    )
    with previz_runtime(args.previz) as rt:
        rt.load(dict(sequence), 8, 8, 1)
        previz_states = rt.statesAt(dense)
    drives = ["time", "state"]
    try:
        report["agreement"] = kernel_agreement(info, previz_states, dense)
    except ValueError as e:  # the spike's lowering refuses what it does not cover
        report["agreement"] = {"lowering_refused": str(e)}
        drives.remove("state")
    print(json.dumps(report["agreement"], indent=2, default=str))

    print("== (b) shots through frame_stage_renderer")
    shots = {}
    for drive in drives:
        shots[drive] = render_shot(
            args.previz, sequence, drive, args.out, fps=args.fps, size=size
        )
        s = shots[drive]
        print(
            f"{drive}: {s['frames']} frames, {s['render_s']:.2f} s "
            f"({s['ms_per_frame']:.1f} ms/frame) -> {s['mp4']}"
        )
        print(f"   profile={s['profile']}")
        print(f"   affordances={s['affordances']}")
        print(f"   provenance={s['provenance_engine_keys']}")
    same = "state" in shots and frames_identical(
        shots["time"]["frame_manifest"], shots["state"]["frame_manifest"]
    )
    print(
        f"time-driven and state-driven frames pixel-identical: {same if 'state' in shots else 'n/a'}"
    )
    report["shots"] = {
        d: {k: v for k, v in s.items() if k != "frame_manifest"}
        for d, s in shots.items()
    }
    report["drives_identical"] = same
    report["report_frames"] = [
        str(shots[drives[-1]]["frame_manifest"][i])
        for i in REPORT_FRAMES
        if i < len(shots[drives[-1]]["frame_manifest"])
    ]

    if not args.skip_page:
        print("== (b') page-side: previz dist in a Playwright page")
        manifest = shots["time"]["frame_manifest"]
        sampled = [i for i in REPORT_FRAMES if i < len(manifest)]
        times = [i / args.fps for i in sampled]
        pg = page_probe(args.previz, sequence, times, args.out / "page", size=size)
        node_frames = [manifest[i] for i in sampled]
        pg["identical_to_node"] = frames_identical(pg["frames"], node_frames)
        print(json.dumps(pg, indent=2, default=str))
        report["page"] = pg

    (args.out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"report: {args.out / 'report.json'}")


if __name__ == "__main__":
    main()
