"""Measure the shipped solver, ``an.kinematics`` (an#499): the numbers its
package docstring quotes.

Run from the repository root: ``python misc/docs/research/puppeteering_2026-10/measure_kinematics.py``.
It prints one JSON document: convergence per iteration on the two-link reach,
behaviour at the singularities (a straight arm, a target at the root),
stability at frame-exact steps, the iteration independence of a compliant
joint, and the cost per frame of ~50 bodies. Pure CPU, a few seconds.
"""

from __future__ import annotations

import json
import math
import platform
import time

from an.kinematics import (
    WORLD,
    Body,
    Distance,
    Hinge,
    Pin,
    Point,
    solve,
    solve_frames,
)
from an.kinematics.solver import resolve_rests

FPS = 24
DT = 1.0 / FPS
G = (0.0, 980.0)


def arm(handle_at):
    torso = Body("torso", width=40.0, height=80.0)
    upper = Body("upper", x=20.0, y=-30.0, width=50.0, height=10.0, origin=(0.0, 0.5))
    fore = Body("fore", x=70.0, y=-30.0, width=40.0, height=8.0, origin=(0.0, 0.5))
    handle = Body("handle", x=handle_at[0], y=handle_at[1], width=4.0, height=4.0, fixed=True)
    joints = [
        Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
        Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
        Pin(Point("fore", 1.0, 0.5), Point("handle", 0.5, 0.5)),
    ]
    return [torso, upper, fore, handle], joints


HELD = {"torso": {"x": 0.0, "y": 0.0}}
#: The torso nailed in rotation too, so the shoulder cannot swing toward a target.
NAILED = {"torso": {"x": 0.0, "y": 0.0, "rotation": 0.0}}


def convergence():
    """Worst residual (px) on the reach after n passes, seeded and not."""
    out = {}
    for seeded in (True, False):
        row = {}
        for n in (1, 2, 4, 8, 16, 64):
            r = solve(*arm((80.0, 10.0)), targets=HELD, iterations=n, seed_chains=seeded, retry=1, drop_conflicts=False)
            row[n] = max(r.residuals)
        out["closed-form start" if seeded else "cold start"] = row
    return out


def singularities():
    """A target at exactly full reach, just beyond, and at the shoulder."""
    shoulder = (20.0, -30.0)
    out = {}
    for label, at in {
        "at full reach (straight)": (shoulder[0] + 90.0, shoulder[1]),
        "1 px beyond reach": (shoulder[0] + 91.0, shoulder[1]),
        "5 px beyond reach": (shoulder[0] + 95.0, shoulder[1]),
        "at the shoulder (inside the 10 px nearest reach)": shoulder,
    }.items():
        r = solve(*arm(at), targets=NAILED)
        out[label] = {
            "unsatisfied": [j for j, _ in r.unsatisfied],
            "dropped": list(r.dropped),
            "residuals": list(r.residuals),
            "elbow angle": r.pose("fore").rotation - r.pose("upper").rotation,
        }
    return out


def chain(n, *, length=10.0, hanging=False):
    """``n`` links pinned end to end from the world: started horizontal (a
    whip when dropped), or ``hanging`` straight down at rest."""
    rot = math.pi / 2 if hanging else 0.0
    bodies = [Body(f"l{k}", x=0.0 if hanging else k * length, y=k * length if hanging else 0.0,
                   rotation=rot, width=length, height=2.0, origin=(0.0, 0.5)) for k in range(n)]
    joints = [Pin(Point("l0", 0.0, 0.5), Point(WORLD, 0.0, 0.0))]
    if hanging:  # held by a driven hook instead of the world
        bodies.insert(0, Body("hook", y=-1.0, width=2.0, height=2.0, fixed=True))
        joints = [Pin(Point("l0", 0.0, 0.5), Point("hook", 0.5, 0.5))]
    joints += [Pin(Point(f"l{k}", 0.0, 0.5), Point(f"l{k - 1}", 1.0, 0.5)) for k in range(1, n)]
    return bodies, joints


def stability():
    """A 12-link chain dropped from horizontal at 24 fps (a whip), per
    substep count, without and with the retry: the worst residual over the
    run, the frames with a failing joint, the frames that dropped one, and the
    tip's final angle from hanging straight down."""
    out = {}
    for substeps in (1, 2, 4, 8):
        for retry in (1, 4):
            bodies, joints = chain(12)
            r = solve_frames(bodies, joints, frames=10 * FPS, dt=DT, gravity=G, substeps=substeps, retry=retry)
            tip = r.final[-1]
            out[f"substeps={substeps} retry={retry}"] = {
                "worst residual": max((v for frame in r.unsatisfied for _, v in frame), default=0.0),
                "frames with a failing joint": sum(1 for f in r.unsatisfied if f),
                "frames that dropped a joint": sum(1 for d in r.dropped if d),
                "tip angle from vertical (deg)": math.degrees(abs(_wrap(tip.rotation - math.pi / 2))),
                "finite": all(math.isfinite(b.x) for b in r.final),
            }
    return out


def _wrap(theta):
    return (theta + math.pi) % (2 * math.pi) - math.pi


def compliance():
    """A soft rod (compliance 1e-4, so a static stretch of 1e-4 × m g = 9.8
    px) holding a weight under gravity: its extension after a second, per
    iteration count (XPBD's claim: the same at every count)."""
    out = {}
    for n in (1, 2, 8, 32):
        anchor = Body("anchor", width=2.0, height=2.0, fixed=True)
        weight = Body("weight", y=50.0, width=10.0, height=10.0)
        rod = Distance(Point("weight", 0.5, 0.5), Point("anchor", 0.5, 0.5), length=50.0, compliance=1e-4)
        r = solve_frames([anchor, weight], [rod], frames=FPS, dt=DT, gravity=G, iterations=n)
        out[n] = r.final[1].y - 50.0
    return out


def cost():
    """Milliseconds per frame (dynamic, defaults) for 50 bodies: a 50-link
    chain, and five ten-part puppets on strings."""
    from tests.test_kinematics import _bar, _marionette  # the test's marionette

    out = {}

    def timed(label, *args, **kwargs):
        t = time.perf_counter()
        r = solve_frames(*args, **kwargs)
        out[label] = {"ms per frame": (time.perf_counter() - t) / kwargs["frames"] * 1e3,
                      "frames with a failing joint": sum(1 for f in r.unsatisfied if f),
                      "frames that dropped a joint": sum(1 for d in r.dropped if d)}

    bodies, joints = chain(50, hanging=True)
    timed("50-link rope, its hook swung 60 units", bodies, joints, frames=48, dt=DT, gravity=G,
          targets_at=lambda k: {"hook": {"x": 60.0 * math.sin(math.pi * k / 48), "y": -1.0}})
    bodies, joints = chain(50)
    timed("50-link chain dropped from horizontal (a whip)", bodies, joints, frames=48, dt=DT, gravity=G)

    crowd_bodies, crowd_joints, targets = [], [], {}
    for p in range(5):
        bodies, joints = _marionette()
        rename = {b.name: f"p{p}_{b.name}" for b in bodies}
        crowd_bodies += [Body(rename[b.name], x=b.x + 300.0 * p, y=b.y, width=b.width, height=b.height,
                              origin=b.origin, fixed=b.fixed) for b in bodies]

        def moved(pt, rename=rename):
            return Point(rename.get(pt.body, pt.body), pt.u, pt.v)

        for j in resolve_rests(bodies, joints):
            fields = {k: moved(getattr(j, k)) for k in ("a", "b") if hasattr(j, k)}
            crowd_joints.append(type(j)(**{**j.__dict__, **fields}))
        targets[p] = rename["bar"]

    def crowd_targets(k):
        bar = _bar(k)["bar"]
        return {name: {**bar, "x": bar["x"] + 300.0 * p} for p, name in targets.items()}

    timed(f"5 marionettes ({len(crowd_bodies)} bodies, {len(crowd_joints)} joints)",
          crowd_bodies, crowd_joints, frames=48, dt=DT, gravity=G, targets_at=crowd_targets)

    t = time.perf_counter()
    for _ in range(200):
        solve(*arm((80.0, 10.0)), targets=HELD)
    out["two-link reach, pose mode"] = {"ms per frame": (time.perf_counter() - t) / 200 * 1e3}
    return out


if __name__ == "__main__":
    print(json.dumps({
        "python": platform.python_version(),
        "machine": platform.machine(),
        "convergence (worst residual, px, by passes)": convergence(),
        "singularities": singularities(),
        "stability (12-link whip, 10 s at 24 fps)": stability(),
        "compliance (soft rod's extension, px, by iterations)": compliance(),
        "cost (ms per frame)": cost(),
    }, indent=2, default=float))
