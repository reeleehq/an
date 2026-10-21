"""The measured method comparison the lead asked for: analytic two-bone, CCD,
FABRIK, position-based (PBD) and XPBD on the same tasks, with bitwise
determinism (``repr`` of every output float equal across two runs) as a hard
requirement. ``python compare.py`` prints JSON."""

from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import dataclass, field

from puppet_solver import (
    HingeLimit, Pin, Puppet, Stick, add, angle_of, fabrik, length, polar, sub,
    two_bone_ik, wrap_angle,
)

DEG = math.pi / 180

# -----------------------------------------------------------------------------
# CCD with hinge limits (angles, root fixed)
# -----------------------------------------------------------------------------


def ccd(
    root, lengths, angles, target, *, limits=None, tolerance=1e-3, max_iterations=100
):
    """Cyclic coordinate descent on absolute link angles. ``limits[i]`` bounds
    the RELATIVE angle at joint i (i >= 1) as ``(lo, hi)``. Returns
    ``(angles, iterations, tip error)``."""
    th = list(angles)
    n = len(th)

    def joints():
        pts = [root]
        for i in range(n):
            pts.append(add(pts[-1], polar(th[i], lengths[i])))
        return pts

    pts = joints()
    err = length(sub(pts[-1], target))
    it = 0
    while err > tolerance and it < max_iterations:
        it += 1
        for i in range(n - 1, -1, -1):
            pts = joints()
            j, tip = pts[i], pts[-1]
            if length(sub(tip, j)) == 0.0:
                continue
            delta = wrap_angle(angle_of(sub(target, j)) - angle_of(sub(tip, j)))
            if i > 0 and limits and limits[i] is not None:
                lo, hi = limits[i]
                rel = wrap_angle(th[i] - th[i - 1])
                delta = max(lo - rel, min(hi - rel, delta))
            for k in range(i, n):
                th[k] += delta
        pts = joints()
        err = length(sub(pts[-1], target))
    return th, it, err


# -----------------------------------------------------------------------------
# Soft constraints: PBD stiffness vs XPBD compliance
# -----------------------------------------------------------------------------


@dataclass
class SoftRodSim:
    """A weight on an elastic rod hung from a pin: particle 1 below particle 0."""

    rest: float = 100.0
    gravity: float = 980.0
    mode: str = "xpbd"  # or "pbd"
    stiffness: float = 0.5  # PBD k in (0, 1]
    compliance: float = 1e-4  # XPBD alpha (m/N); 0 = rigid
    pos: list = field(default_factory=lambda: [(0.0, 0.0), (0.0, 100.0)])
    prev: list = field(default_factory=list)

    def run(self, *, seconds=3.0, dt=1 / 60, iterations=8, damping=0.1) -> float:
        p = [(0.0, 0.0), (0.0, self.rest)]
        q = list(p)
        steps = int(seconds / dt)
        for _ in range(steps):
            # Verlet on the free particle 1
            v = (0.0, (p[1][1] - q[1][1]) * (1 - damping))
            q[1] = p[1]
            p[1] = (0.0, p[1][1] + v[1] + self.gravity * dt * dt)
            lam = 0.0
            for _ in range(iterations):
                d = p[1][1] - p[0][1]
                c = d - self.rest
                if self.mode == "pbd":
                    p[1] = (0.0, p[1][1] - self.stiffness * c)
                else:
                    alpha_t = self.compliance / (dt * dt)
                    w = 1.0  # inverse mass of the free particle; the pin has 0
                    dlam = (-c - alpha_t * lam) / (w + alpha_t)
                    lam += dlam
                    p[1] = (0.0, p[1][1] + w * dlam)
        return p[1][1] - self.rest  # extension at rest


# -----------------------------------------------------------------------------
# Tasks
# -----------------------------------------------------------------------------

results: dict = {}


def bitwise(a, b) -> bool:
    return repr(a) == repr(b)


# Task A: two-link arm (42.43 + 30) reaching 48 targets on a circle, elbow limit:
# relative angle in [-150, -30] degrees (bends one way, never past 30 deg of straight).
L1, L2 = math.hypot(30, 30), 30.0
ROOT = (0.0, -60.0)
TARGETS = [add(ROOT, polar(-20 * DEG + 2 * math.pi * k / 48, 55.0)) for k in range(48)]
LIMIT = (-150 * DEG, -30 * DEG)


def task_a_analytic():
    out, t0 = [], time.perf_counter()
    for tg in TARGETS:
        sol = two_bone_ik(ROOT, L1, L2, tg, bend=-1)
        out.append(sol)
    return out, (time.perf_counter() - t0) / len(TARGETS) * 1e6


def task_a_ccd(tol=1e-3):
    th = [90 * DEG, 90 * DEG]  # hanging straight down
    out, iters, errs, t0 = [], [], [], time.perf_counter()
    for tg in TARGETS:
        th, it, err = ccd(ROOT, (L1, L2), th, tg, limits=[None, LIMIT], tolerance=tol)
        out.append(tuple(th)); iters.append(it); errs.append(err)
    return out, iters, errs, (time.perf_counter() - t0) / len(TARGETS) * 1e6


def task_a_fabrik(tol=1e-3):
    pts = [ROOT, add(ROOT, (0.0, L1)), add(ROOT, (0.0, L1 + L2))]
    out, iters, errs, t0 = [], [], [], time.perf_counter()
    for tg in TARGETS:
        pts, it, err = fabrik(pts, tg, tolerance=tol, max_iterations=500)
        th = (angle_of(sub(pts[1], pts[0])), angle_of(sub(pts[2], pts[1])))
        out.append(th); iters.append(it); errs.append(err)
    return out, iters, errs, (time.perf_counter() - t0) / len(TARGETS) * 1e6


def task_a_pbd():
    """Particles root (pinned), elbow, tip; the tip pulled to the target by a
    goal (a tight string), the elbow limited; warm-started frame to frame."""
    pup = Puppet(
        positions=[ROOT, add(ROOT, (0.0, L1)), add(ROOT, (0.0, L1 + L2))],
        sticks=[Stick(0, 1, L1), Stick(1, 2, L2)],
        pins=[Pin(0, lambda t: ROOT)],
        limits=[HingeLimit(0, 1, 2, LIMIT[0] + math.pi, LIMIT[1] + math.pi)],
        gravity=(0.0, 0.0),
    )
    out, iters, errs, t0 = [], [], [], time.perf_counter()
    for tg in TARGETS:
        from puppet_solver import String
        pup.strings = [String(2, (lambda g: (lambda t: g))(tg), 0.0)]
        n = pup.settle(0.0, eps=1e-4, dt=1 / 60, iterations=8)
        th = (angle_of(sub(pup.positions[1], pup.positions[0])),
              angle_of(sub(pup.positions[2], pup.positions[1])))
        out.append(th); iters.append(n); errs.append(length(sub(pup.positions[2], tg)))
    return out, iters, errs, (time.perf_counter() - t0) / len(TARGETS) * 1e6


def limit_violation(angles):
    worst = 0.0
    for t1, t2 in angles:
        rel = wrap_angle(t2 - t1)
        worst = max(worst, LIMIT[0] - rel, rel - LIMIT[1], 0.0)
    return worst / DEG


def frame_coherence(angles):
    """Largest frame-to-frame change of any link angle (degrees): a pop."""
    worst = 0.0
    for (a1, a2), (b1, b2) in zip(angles, angles[1:]):
        worst = max(worst, abs(wrap_angle(b1 - a1)), abs(wrap_angle(b2 - a2)))
    return worst / DEG


def tip_error(angles):
    worst = 0.0
    for (t1, t2), tg in zip(angles, TARGETS):
        tip = add(add(ROOT, polar(t1, L1)), polar(t2, L2))
        worst = max(worst, length(sub(tip, tg)))
    return worst


task_a = {}
a1, us = task_a_analytic(); a2, _ = task_a_analytic()
task_a["analytic_two_bone"] = {
    "worst_tip_error_px": tip_error(a1), "limit_violation_deg": limit_violation(a1),
    "worst_frame_to_frame_deg": frame_coherence(a1), "us_per_frame": us,
    "bitwise_identical_rerun": bitwise(a1, a2), "iterations": "closed form",
}
c1, it, er, us = task_a_ccd(); c2, *_ = task_a_ccd()
task_a["ccd_with_limits"] = {
    "worst_tip_error_px": tip_error(c1), "limit_violation_deg": limit_violation(c1),
    "worst_frame_to_frame_deg": frame_coherence(c1), "us_per_frame": us,
    "median_iterations": statistics.median(it), "max_iterations": max(it),
    "bitwise_identical_rerun": bitwise(c1, c2),
}
f1, it, er, us = task_a_fabrik(); f2, *_ = task_a_fabrik()
task_a["fabrik_no_limits"] = {
    "worst_tip_error_px": tip_error(f1), "limit_violation_deg": limit_violation(f1),
    "worst_frame_to_frame_deg": frame_coherence(f1), "us_per_frame": us,
    "median_iterations": statistics.median(it), "max_iterations": max(it),
    "bitwise_identical_rerun": bitwise(f1, f2),
}
p1, it, er, us = task_a_pbd(); p2, *_ = task_a_pbd()
task_a["pbd_goal_with_limits_warm_start"] = {
    "worst_tip_error_px": tip_error(p1), "limit_violation_deg": limit_violation(p1),
    "worst_frame_to_frame_deg": frame_coherence(p1), "us_per_frame": us,
    "median_iterations": statistics.median(it), "max_iterations": max(it),
    "bitwise_identical_rerun": bitwise(p1, p2),
}
results["task_A_two_link_reach_48_targets_elbow_limit"] = task_a

# Task A': the same arm, a target beyond reach (85 px for a 72 px arm).
far = add(ROOT, (-80.0, -30.0))
unreach = {}
unreach["analytic_two_bone"] = "None (refused)"
th, it, err = ccd(ROOT, (L1, L2), [90 * DEG, 90 * DEG], far, limits=[None, LIMIT])
unreach["ccd_with_limits"] = {"tip_error_px": err, "iterations": it, "note": "straightens toward the target up to the limit"}
pts, it, err = fabrik([ROOT, add(ROOT, (0.0, L1)), add(ROOT, (0.0, L1 + L2))], far)
unreach["fabrik"] = {"tip_error_px": err, "iterations": it, "note": "points the chain at the target in one pass"}
pup = Puppet(positions=[ROOT, add(ROOT, (0.0, L1)), add(ROOT, (0.0, L1 + L2))],
             sticks=[Stick(0, 1, L1), Stick(1, 2, L2)], pins=[Pin(0, lambda t: ROOT), Pin(2, lambda t: far)],
             gravity=(0.0, 0.0))
n = pup.settle(0.0)
unreach["pbd_hard_pin_both_ends"] = {
    "worst_stick_error_px": max(abs(length(sub(pup.positions[s.j], pup.positions[s.i])) - s.length) for s in pup.sticks),
    "rounds": n, "note": "a hard pin beyond reach is a permanent conflict; must be refused (lint) or softened (goal)",
}
results["task_A_prime_unreachable_target"] = unreach

# Task B: a 6-stick chain hanging from a pin that moves: PBD settle vs the closed form
# (every link vertical below its parent). FABRIK/CCD have no gravity: N/A.
def hang_closed_form(x, n=6, L=30.0):
    return [(x, i * L) for i in range(n + 1)]

pup = Puppet(positions=[(i * 30.0, 0.0) for i in range(7)], sticks=[Stick(i, i + 1, 30.0) for i in range(6)],
             pins=[Pin(0, lambda t: (0.0, 0.0))])
pup.settle(0.0)
worst, rounds, t0 = 0.0, [], time.perf_counter()
poses_1 = []
for f in range(48):
    x = 40.0 * math.sin(2 * math.pi * f / 48)
    pup.pins = [Pin(0, (lambda x: (lambda t: (x, 0.0)))(x))]; pup.__post_init__()
    rounds.append(pup.settle(0.0))
    ref = hang_closed_form(x)
    worst = max(worst, max(length(sub(p, r)) for p, r in zip(pup.positions, ref)))
    poses_1.append(list(pup.positions))
ms = (time.perf_counter() - t0) / 48 * 1e3
pup2 = Puppet(positions=[(i * 30.0, 0.0) for i in range(7)], sticks=[Stick(i, i + 1, 30.0) for i in range(6)],
              pins=[Pin(0, lambda t: (0.0, 0.0))])
pup2.settle(0.0)
poses_2 = []
for f in range(48):
    x = 40.0 * math.sin(2 * math.pi * f / 48)
    pup2.pins = [Pin(0, (lambda x: (lambda t: (x, 0.0)))(x))]; pup2.__post_init__()
    pup2.settle(0.0); poses_2.append(list(pup2.positions))
results["task_B_hanging_chain_moving_pin_pose_mode"] = {
    "pbd_settle": {"worst_error_vs_closed_form_px": worst, "median_rounds": statistics.median(rounds),
                    "max_rounds": max(rounds), "ms_per_frame": ms, "bitwise_identical_rerun": bitwise(poses_1, poses_2)},
    "fabrik": "N/A (no gravity, no settle)", "ccd": "N/A (no gravity, no settle)",
    "closed_form": "exact for a free-hanging tree; not available once strings or a second pin couple the chain",
}

# Task C: soft constraint stiffness vs iteration count (Macklin 2016's claim).
soft = {}
for mode in ("pbd", "xpbd"):
    ext = {}
    for its in (1, 2, 8, 32):
        sim = SoftRodSim(mode=mode, stiffness=0.2, compliance=2e-4)
        ext[f"iterations_{its}"] = sim.run(iterations=its)
    vals = list(ext.values())
    soft[mode] = {**ext, "spread_px": max(vals) - min(vals)}
results["task_C_soft_rod_extension_vs_iterations"] = soft

print(json.dumps(results, indent=1))
