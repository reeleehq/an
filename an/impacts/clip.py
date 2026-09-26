"""One impact clip, end to end: spec -> scene -> ground truth -> (video) -> files.

:class:`ImpactClipSpec` is the whole description of a clip as flat, JSON-able
data — it is written verbatim into the sidecar, so any clip can be regenerated
from its own ``truth.json``. :func:`plan_impact_clip` turns it into the scene an
animation would have (props + tweens, a normal `an` Shot) without touching
disk; :func:`write_impact_clip` compiles it, extracts the ground truth, renders
the video (optional — the truth and keypoints need no browser), and writes:

==================  ==========================================================
``clip.mp4``        the rendered video (only with ``render=True``)
``truth.json``      spec, tempo, events (grid / executed / frame evidence),
                    every frame's exposure and sample instants, the stroke
``keypoints.ndjson`` per-frame 2D keypoints at each frame's reported time —
                    observations only, in thoremin's recorder shape
``trajectory.csv``  the continuous trajectory at ``trajectory_hz``
``scene.json``      the `an` Scene IR that was rendered (the camera — rate,
                    shutter, jitter — lives in ``truth.json``'s ``clock``)
==================  ==========================================================

>>> plan = plan_impact_clip(ImpactClipSpec(beats=4, tempo=120))
>>> [e.t_grid for e in plan.events]                        # intended
[0.5, 1.0, 1.5, 2.0]
>>> [round(e.t_impact - e.t_grid, 3) for e in plan.events]  # executed: humanised
[0.003, 0.013, -0.005, 0.006]
>>> len(plan.frames)
75
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from itertools import product
from pathlib import Path
from typing import Any

from an.frame_clock import CapturedFrame, FrameClock
from an.impacts.objects import ImpactObject, PropArt, impact_object
from an.impacts.performance import (
    DEFAULT_LEAD_IN,
    ImpactEvent,
    gaussian_humanizer,
    perform,
    tempo_map,
)
from an.impacts.stroke import (
    DEFAULT_BRAKE,
    DEFAULT_FALL,
    DEFAULT_RISE,
    Stroke,
    build_stroke,
)
from an.impacts.truth import TruthMismatch, ground_truth, keypoint_lines, trajectory_rows
from an.ir.compose import delay, parallel, sequence, tween
from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, Shot, StagePlacement

__all__ = [
    "BENCHMARK_SPEC",
    "CLIP_FILES",
    "DEFAULT_JITTER_SD",
    "DEFAULT_TAIL",
    "DEFAULT_TRAJECTORY_HZ",
    "ImpactClipSpec",
    "ImpactPlan",
    "ImpactSpecError",
    "impact_set_specs",
    "plan_impact_clip",
    "write_impact_clip",
    "write_impact_set",
]

#: Seconds after the last grid beat before the clip ends.
DEFAULT_TAIL: float = 0.5
#: Default humanisation (seconds, standard deviation). See `ImpactClipSpec`.
DEFAULT_JITTER_SD: float = 0.008
#: Samples per second of the dense trajectory in ``trajectory.csv``.
DEFAULT_TRAJECTORY_HZ: float = 1000.0

CLIP_FILES: dict[str, str] = {
    "video": "clip.mp4",
    "truth": "truth.json",
    "keypoints": "keypoints.ndjson",
    "trajectory": "trajectory.csv",
    "scene": "scene.json",
}

_FLOAT_FIELDS = (
    "lead_in", "tail", "jitter_sd", "jitter_rho", "jitter_bias", "rise", "fall",
    "brake", "fps", "exposure", "timestamp_jitter_sd", "timestamp_noise_sd",
    "phase", "trajectory_hz",
)
_INT_FIELDS = ("beats", "subdivision", "width", "height", "seed")


class ImpactSpecError(ValueError):
    """A clip spec that cannot describe a clip."""


_SHOT_ID = "impacts"
_SURFACE_ID = "surface"
_SEED_STREAMS = {"performance": 0, "clock": 1}


@dataclass(frozen=True)
class ImpactClipSpec:
    """Everything that determines a clip. Defaults: a stick hitting a table at 100 BPM.

    Performance: ``tempo`` (a bpm, or ``[(beat, bpm), ...]`` for a tempo
    change), ``beats``, ``subdivision``, ``pattern`` (per-step stroke heights,
    ``0`` = rest), ``lead_in``, ``tail``, and the humanisation ``jitter_sd`` /
    ``jitter_rho`` / ``jitter_bias`` (seconds; see
    :func:`an.impacts.performance.gaussian_humanizer`). Humanised by default
    (``jitter_sd`` = :data:`DEFAULT_JITTER_SD`): on a perfect grid every impact
    of a round tempo lands exactly on a frame at common rates, which is the one
    case a sub-frame estimator cannot be scored on. Set it to 0 for a metronome.

    Motion: ``object`` (``"stick"`` or ``"ball"``), ``kind`` (``"surface"`` or
    ``"air"``), the stroke timings ``rise`` / ``fall`` / ``brake``, and
    ``show_surface`` (``None``: drawn for surface impacts only).

    Camera (:class:`an.frame_clock.FrameClock`): ``fps``, ``exposure``,
    ``exposure_samples``, ``timestamp_jitter_sd`` (when frames are really
    taken), ``timestamp_noise_sd`` (noise on the reported timestamp only),
    ``phase``, ``timestamps``.

    ``seed`` drives two independent streams — the performance's and the
    camera's — so clips that differ only in camera settings share the exact same
    performance.
    """

    object: str = "stick"
    kind: str = "surface"
    tempo: float | tuple[tuple[float, float], ...] = 100.0
    beats: int = 16
    subdivision: int = 1
    pattern: tuple[float, ...] = (1.0,)
    lead_in: float = DEFAULT_LEAD_IN
    tail: float = DEFAULT_TAIL
    jitter_sd: float = DEFAULT_JITTER_SD
    jitter_rho: float = 0.0
    jitter_bias: float = 0.0
    rise: float = DEFAULT_RISE
    fall: float = DEFAULT_FALL
    brake: float = DEFAULT_BRAKE
    show_surface: bool | None = None
    fps: float = 30.0
    exposure: float = 0.0
    exposure_samples: int | None = None
    timestamp_jitter_sd: float = 0.0
    timestamp_noise_sd: float = 0.0
    phase: float = 0.0
    timestamps: str = "nominal"
    width: int = 640
    height: int = 360
    trajectory_hz: float = DEFAULT_TRAJECTORY_HZ
    seed: int = 0

    def __post_init__(self) -> None:
        # Canonical types, so two equal specs have one JSON form and one
        # clip_id: `fps=30` and `fps=30.0` compare equal, and must not name two
        # directories.
        for name in _FLOAT_FIELDS:
            object.__setattr__(self, name, float(getattr(self, name)))
        for name in _INT_FIELDS:
            object.__setattr__(self, name, int(getattr(self, name)))
        if isinstance(self.tempo, (int, float)):
            object.__setattr__(self, "tempo", float(self.tempo))
        else:
            object.__setattr__(self, "tempo", tempo_map(self.tempo).points)
        object.__setattr__(self, "pattern", tuple(float(a) for a in self.pattern))
        for name in ("lead_in", "tail", "trajectory_hz"):
            if not getattr(self, name) > 0:
                raise ImpactSpecError(f"{name} must be > 0; got {getattr(self, name)!r}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(self.tempo, tuple):
            d["tempo"] = [list(p) for p in self.tempo]
        d["pattern"] = list(self.pattern)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ImpactClipSpec":
        """The inverse of :meth:`to_dict`. Refuses fields it does not know —
        dropping one would regenerate a different clip under the same spec."""
        d = dict(d)
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ImpactSpecError(
                f"spec fields {sorted(unknown)} are unknown to this version of an "
                "(written by a newer one?); upgrade an to regenerate this clip"
            )
        if isinstance(d.get("tempo"), list):
            d["tempo"] = tuple(tuple(p) for p in d["tempo"])
        return cls(**d)

    @property
    def clip_id(self) -> str:
        """A readable, deterministic directory name.

        >>> ImpactClipSpec().clip_id[:-8]
        'stick-surface-30fps-e0-'
        >>> ImpactClipSpec().clip_id == ImpactClipSpec().clip_id
        True
        """
        digest = hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True).encode()
        ).hexdigest()[:8]
        return f"{self.object}-{self.kind}-{self.fps:g}fps-e{self.exposure:g}-{digest}"

    def clock(self) -> FrameClock:
        return FrameClock(
            fps=self.fps,
            exposure=self.exposure,
            samples=self.exposure_samples,
            jitter_sd=self.timestamp_jitter_sd,
            phase=self.phase,
            timestamps=self.timestamps,  # type: ignore[arg-type]
            report_noise_sd=self.timestamp_noise_sd,
            seed=_seed(self.seed, "clock"),
        )


def _seed(seed: int, stream: str) -> int:
    """An independent, deterministic sub-seed per stream."""
    return int.from_bytes(hashlib.sha256(f"{seed}:{_SEED_STREAMS[stream]}".encode()).digest()[:4], "big")


@dataclass(frozen=True)
class ImpactPlan:
    """A clip before it touches disk: events, motion, camera, and the Scene IR."""

    spec: ImpactClipSpec
    events: tuple[ImpactEvent, ...]
    obj: ImpactObject
    stroke: Stroke
    frames: tuple[CapturedFrame, ...]
    scene: SceneIR = field(repr=False)

    @property
    def duration(self) -> float:
        return self.stroke.duration

    @property
    def shot(self) -> Shot:
        return self.scene.timeline[0]

    @property
    def props(self) -> tuple[PropArt, ...]:
        return tuple(a for a in (self.obj.art, self.obj.surface_art) if a is not None)


def plan_impact_clip(spec: ImpactClipSpec) -> ImpactPlan:
    """Resolve ``spec`` into events, a stroke, frames and a Scene IR. No I/O."""
    events = perform(
        spec.tempo,
        beats=spec.beats,
        subdivision=spec.subdivision,
        pattern=spec.pattern,
        lead_in=spec.lead_in,
        humanizer=gaussian_humanizer(spec.jitter_sd, rho=spec.jitter_rho, bias=spec.jitter_bias),
        seed=_seed(spec.seed, "performance"),
    )
    # Not rounded: rounding can land the end BELOW the last impact.
    duration = max(max(e.t_grid, e.t_impact) for e in events) + spec.tail
    stroke = build_stroke(
        events,
        kind=spec.kind,  # type: ignore[arg-type]
        duration=duration,
        rise=spec.rise,
        fall=spec.fall,
        brake=spec.brake,
    )
    obj = impact_object(spec.object)
    frames = spec.clock().frames(duration)
    show_surface = spec.kind == "surface" if spec.show_surface is None else spec.show_surface
    scene = _scene(spec, obj, stroke, show_surface=show_surface)
    return ImpactPlan(spec, events, obj, stroke, frames, scene)


def _scene(spec: ImpactClipSpec, obj: ImpactObject, stroke: Stroke, *, show_surface: bool) -> SceneIR:
    """The clip as an ordinary `an` scene: props placed on stage, one tween per segment.

    Each tween is placed by a ``delay`` of exactly its start time, rather than
    chained in a ``sequence``, so every segment boundary — every impact — lands
    on its float without accumulated rounding.
    """
    entities = []
    if show_surface and obj.surface_art is not None:
        entities.append(
            AssetRef(
                kind="prop", id=_SURFACE_ID, store="props", ref=obj.surface_art.ref,
                stage=StagePlacement(at=obj.surface_at),
            )
        )
    entities.append(
        AssetRef(kind="prop", id=obj.name, store="props", ref=obj.art.ref, stage=StagePlacement(at=obj.at))
    )
    # One tween per (segment, channel): every channel is affine in h, so each
    # eased tween is the same easing of h, and a multi-channel object (a
    # forearm plus a stick) stays exact.
    moves = [
        sequence(
            delay(seg.t0),
            tween(
                channel.target,
                channel.property,
                channel.value(seg.h1),
                seg.t1 - seg.t0,
                from_=channel.value(seg.h0),
                easing=seg.easing,
            ),
        )
        for seg in stroke.segments
        for channel in obj.channels
    ]
    shot = Shot(
        id=_SHOT_ID,
        duration=stroke.duration,
        entities=entities,
        actions=[parallel(*moves)],
    )
    meta = Meta(
        title=f"impacts: {spec.clip_id}",
        duration=stroke.duration,
        fps=max(1, round(spec.fps)),
        resolution=Resolution(width=spec.width, height=spec.height),
        notes="Generated by an.impacts; the ground truth is truth.json beside it.",
    )
    return SceneIR(meta=meta, timeline=[shot])


def _install_props(plan: ImpactPlan, mall: dict) -> None:
    store = mall["props"]
    for art in plan.props:
        store[art.ref] = art.descriptor
        for rel, svg in art.parts.items():
            path = store.sidecar_path(art.ref, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(svg, encoding="utf-8")


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("an")
    except PackageNotFoundError:  # pragma: no cover - source checkout without metadata
        return "unknown"


def write_impact_clip(
    spec: ImpactClipSpec,
    out_dir: str | Path,
    *,
    render: bool = True,
    clip_dir: str | None = None,
) -> Path:
    """Write one clip into ``out_dir / (clip_dir or spec.clip_id)``; return that dir.

    With ``render=False`` everything but ``clip.mp4`` is written, and no
    browser is needed: the keypoints and the truth come from the compiled
    document, not from the pixels.
    """
    from an.adapters.cutout.compile import compile_shot
    from an.stores import build_project_mall

    plan = plan_impact_clip(spec)
    target = Path(out_dir).expanduser() / (clip_dir or spec.clip_id)
    with tempfile.TemporaryDirectory(prefix="an-impacts-") as tmp:
        mall = build_project_mall(tmp, ensure=True)
        _install_props(plan, mall)
        compiled = compile_shot(
            plan.shot,
            mall=mall,
            fps=int(round(spec.fps)),  # what CutoutRenderer compiles at, too
            width=spec.width,
            height=spec.height,
            strict_assets=True,
        )
        header = {
            "generator": {"package": "an", "version": _package_version(), "module": __name__},
            "spec": spec.to_dict(),
            "clock": spec.clock().to_dict(),
            "tempo": tempo_map(spec.tempo).to_dict(),
            "clip": {
                "duration": plan.duration,
                "fps": spec.fps,
                "width": spec.width,
                "height": spec.height,
                "frame_count": len(plan.frames),
                "rendered": render,
                "files": {
                    k: v for k, v in CLIP_FILES.items() if render or k != "video"
                },
            },
        }
        truth = ground_truth(
            scene=compiled,
            obj=plan.obj,
            stroke=plan.stroke,
            events=plan.events,
            frames=plan.frames,
            header=header,
        )
        video = _render(plan, mall, Path(tmp), compiled) if render else None
        # Nothing is written until the truth has passed every check and the
        # video (if any) exists, so a refused or failed clip leaves nothing
        # behind that looks like a clip.
        target.mkdir(parents=True, exist_ok=True)
        stale = target / CLIP_FILES["video"]
        if video is not None:
            shutil.copyfile(video, stale)
        elif stale.exists():
            stale.unlink()  # a truth saying `rendered: false` beside an old video
    _write_json(target / CLIP_FILES["truth"], truth)
    _write_json(target / CLIP_FILES["scene"], plan.scene.model_dump(mode="json"))
    (target / CLIP_FILES["keypoints"]).write_text(
        "".join(json.dumps(line) + "\n" for line in keypoint_lines(truth)),
        encoding="utf-8",
    )
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(
        trajectory_rows(scene=compiled, obj=plan.obj, stroke=plan.stroke, hz=spec.trajectory_hz)
    )
    (target / CLIP_FILES["trajectory"]).write_text(buf.getvalue(), encoding="utf-8")
    return target


def _render(plan: ImpactPlan, mall: dict, tmp: Path, compiled: Any) -> Path:
    """Render the shot; refuse if the renderer drew a different document.

    `CutoutRenderer` compiles the shot itself, from arguments it rebuilds out of
    the `RenderContext`. Today that is the same document the truth was read
    from; if a renderer default ever changes (stepped timing switched on, say),
    the video would change and the truth would not — so the document the
    renderer STAGED is compared with the truth's, and a difference raises.
    """
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer
    from an.adapters.cutout.serialize import to_dict

    spec = plan.spec
    # An integral rate goes in as an int, so the mux argv is the ordinary one.
    fps: float = int(spec.fps) if float(spec.fps).is_integer() else spec.fps
    result = CutoutRenderer().render(
        plan.shot,
        RenderContext(
            mall=mall,
            work_dir=tmp / "work",
            fps=fps,  # type: ignore[arg-type]
            resolution=(spec.width, spec.height),
            strict_assets=True,
            frame_samples=tuple(f.samples for f in plan.frames),
        ),
    )
    staged = result.mp4_path.parent / "runtime" / "scene.json"
    drawn = json.loads(staged.read_text(encoding="utf-8"))
    if drawn != json.loads(json.dumps(to_dict(compiled), sort_keys=True)):
        raise TruthMismatch(
            f"the renderer staged a different document ({staged}) from the one the "
            "ground truth was read from; the video and the sidecar would disagree"
        )
    if result.provenance.get("frame_samples") != [list(f.samples) for f in plan.frames]:
        raise TruthMismatch("the renderer did not capture the instants the truth records")
    return result.mp4_path


def _write_json(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


#: A harder default for scoring estimators: an accelerando with accents and
#: human, slightly drifting timing. What :func:`impact_set_specs` varies the
#: camera and the object over.
BENCHMARK_SPEC = ImpactClipSpec(
    tempo=((0.0, 96.0), (24.0, 132.0)),
    beats=24,
    pattern=(1.0, 0.6, 0.8, 0.6),
    jitter_sd=0.012,
    jitter_rho=0.3,
)


def impact_set_specs(
    *,
    base: ImpactClipSpec = BENCHMARK_SPEC,
    objects: Sequence[str] = ("stick", "ball"),
    kinds: Sequence[str] = ("surface", "air"),
    fps: Sequence[float] = (24, 30, 60),
    exposures: Sequence[float] = (0.0, 0.5),
    timestamp_jitter_sds: Sequence[float] = (0.0,),
    seeds: Sequence[int] = (0,),
) -> list[ImpactClipSpec]:
    """The cartesian product of the given axes over ``base``.

    >>> len(impact_set_specs())
    24
    >>> {s.seed for s in impact_set_specs(seeds=(0, 1), fps=(30,))}
    {0, 1}
    """
    return [
        replace(
            base, object=o, kind=k, fps=float(f), exposure=float(e),
            timestamp_jitter_sd=float(j), seed=int(s),
        )
        for o, k, f, e, j, s in product(objects, kinds, fps, exposures, timestamp_jitter_sds, seeds)
    ]


def write_impact_set(
    out_dir: str | Path,
    specs: Iterable[ImpactClipSpec] | None = None,
    *,
    render: bool = True,
    progress: Any = None,
) -> Path:
    """Write every clip in ``specs`` (default: :func:`impact_set_specs`) plus ``index.json``.

    ``progress``, if given, is called with ``(i, n, clip_dir)`` after each clip.
    """
    specs = list(specs) if specs is not None else impact_set_specs()
    root = Path(out_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    index = []
    for i, spec in enumerate(specs):
        clip = write_impact_clip(spec, root, render=render)
        index.append({"clip": clip.name, "spec": spec.to_dict()})
        if progress is not None:
            progress(i + 1, len(specs), clip)
    _write_json(
        root / "index.json",
        {"generator": {"package": "an", "version": _package_version()}, "clips": index},
    )
    return root
