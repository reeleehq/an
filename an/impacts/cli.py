"""``an impacts ...`` — the impact harness from the shell.

Thin string-typed wrappers over :mod:`an.impacts.clip`, dispatched by typer the
same way as ``an character ...``: the business logic stays in plain functions
that take real types, and these only parse the list-valued flags.

    an impacts clip ~/.local/share/thoremin/synthetic --kind air --fps 30 --exposure 0.5
    an impacts clip-set ~/.local/share/thoremin/synthetic/set-v1 --fps 24,30,60
"""

from __future__ import annotations

from dataclasses import replace

from an.impacts.performance import DEFAULT_LEAD_IN

from an.impacts.clip import (
    BENCHMARK_SPEC,
    DEFAULT_JITTER_SD,
    DEFAULT_TAIL,
    ImpactClipSpec,
    impact_set_specs,
    write_impact_clip,
    write_impact_set,
)

__all__ = ["clip", "clip_set"]


def _floats(text: str) -> tuple[float, ...]:
    """``"1,0.5"`` -> ``(1.0, 0.5)``."""
    return tuple(float(x) for x in text.split(",") if x.strip())


def _words(text: str) -> tuple[str, ...]:
    return tuple(w.strip() for w in text.split(",") if w.strip())


def _tempo(text: str) -> float | tuple[tuple[float, float], ...]:
    """``"100"`` or ``"0:90,16:120"`` (beat:bpm pairs, a tempo change)."""
    if ":" not in text:
        return float(text)
    pairs = [item.split(":") for item in _words(text)]
    return tuple((float(b), float(v)) for b, v in pairs)


def clip(
    out_dir: str,
    object: str = "stick",  # noqa: A002 - the flag users type
    kind: str = "surface",
    tempo: str = "100",
    beats: int = 16,
    subdivision: int = 1,
    pattern: str = "1",
    lead_in: float = DEFAULT_LEAD_IN,
    tail: float = DEFAULT_TAIL,
    jitter_sd: float = DEFAULT_JITTER_SD,
    jitter_rho: float = 0.0,
    jitter_bias: float = 0.0,
    fps: float = 30.0,
    exposure: float = 0.0,
    exposure_samples: int = 0,
    timestamp_jitter_sd: float = 0.0,
    timestamp_noise_sd: float = 0.0,
    phase: float = 0.0,
    timestamps: str = "nominal",
    width: int = 640,
    height: int = 360,
    seed: int = 0,
    render: bool = True,
) -> str:
    """Write one impact clip (video + ground truth) under OUT_DIR.

    out_dir: parent directory; the clip gets its own sub-directory
    object: stick or ball
    kind: surface (contact) or air (the stroke turns with nothing to hit)
    tempo: a bpm, or beat:bpm pairs for a tempo change, e.g. 0:90,16:120
    beats: number of beats
    subdivision: grid steps per beat
    pattern: per-step stroke heights, cycled; 0 is a rest, e.g. 1,0.5,0.8,0.5
    lead_in: seconds before the first beat
    tail: seconds after the last beat
    jitter_sd: humanisation, seconds (standard deviation of the timing offset; 0 = metronome)
    jitter_rho: correlation of consecutive offsets (0 = independent)
    jitter_bias: constant lead (negative) or lag (positive), seconds
    fps: frame rate (need not be an integer)
    exposure: fraction of the frame period the shutter is open (0.5 = 180 degrees)
    exposure_samples: instants averaged per open exposure (0 = automatic)
    timestamp_jitter_sd: seconds of jitter in WHEN each frame is captured
    timestamp_noise_sd: seconds of noise on the REPORTED timestamp only
    phase: sub-frame offset of the camera clock, seconds
    timestamps: what keypoints.ndjson reports as t: nominal or actual
    width: frame width in pixels
    height: frame height in pixels
    seed: random seed (performance and camera streams derive from it)
    render: render the mp4; --no-render writes the truth and keypoints only
    """
    spec = ImpactClipSpec(
        object=object,
        kind=kind,
        tempo=_tempo(tempo),
        beats=beats,
        subdivision=subdivision,
        pattern=_floats(pattern),
        lead_in=lead_in,
        tail=tail,
        jitter_sd=jitter_sd,
        jitter_rho=jitter_rho,
        jitter_bias=jitter_bias,
        fps=fps,
        exposure=exposure,
        exposure_samples=exposure_samples or None,
        timestamp_jitter_sd=timestamp_jitter_sd,
        timestamp_noise_sd=timestamp_noise_sd,
        phase=phase,
        timestamps=timestamps,
        width=width,
        height=height,
        seed=seed,
    )
    return f"wrote {write_impact_clip(spec, out_dir, render=render)}"


def clip_set(
    out_dir: str,
    objects: str = "stick,ball",
    kinds: str = "surface,air",
    fps: str = "24,30,60",
    exposures: str = "0,0.5",
    timestamp_jitter_sds: str = "0",
    seeds: str = "0",
    render: bool = True,
) -> str:
    """Write a benchmark set (the product of the given axes) plus index.json.

    Every clip shares one performance per seed — an accelerando from 96 to 132
    BPM over 24 beats, accented, with 12 ms of drifting human timing — so clips
    differ only in object, kind and camera.

    out_dir: directory for the set
    objects: comma-separated, from stick,ball
    kinds: comma-separated, from surface,air
    fps: comma-separated frame rates
    exposures: comma-separated shutter fractions
    timestamp_jitter_sds: comma-separated capture-jitter standard deviations (s)
    seeds: comma-separated performance seeds
    render: render the videos; --no-render writes the truth and keypoints only
    """
    specs = impact_set_specs(
        base=replace(BENCHMARK_SPEC),
        objects=_words(objects),
        kinds=_words(kinds),
        fps=_floats(fps),
        exposures=_floats(exposures),
        timestamp_jitter_sds=_floats(timestamp_jitter_sds),
        seeds=tuple(int(s) for s in _words(seeds)),
    )

    def progress(i: int, n: int, path) -> None:
        print(f"[{i}/{n}] {path.name}", flush=True)

    root = write_impact_set(out_dir, specs, render=render, progress=progress)
    return f"wrote {len(specs)} clips and {root / 'index.json'}"


_dispatch_funcs = [clip, clip_set]
