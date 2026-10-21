"""Measurements for the research report: run ``python measure.py`` and paste the JSON."""

from __future__ import annotations

import json
import math
import random
import statistics
import time

from puppet_solver import (
    HingeLimit, Pin, Puppet, Stick, String, add, fabrik, length, marionette, polar,
    sub, two_bone_ik, wrap_angle, angle_of,
)

results: dict = {}
rng = random.Random(0)

# 1. Two-bone IK: exactness and cost.
worst = 0.0
t0 = time.perf_counter()
for _ in range(1000):
    l1, l2 = rng.uniform(20, 100), rng.uniform(20, 100)
    r = rng.uniform(abs(l1 - l2) + 1e-3, l1 + l2 - 1e-3)
    target = polar(rng.uniform(-math.pi, math.pi), r)
    t1, t2 = two_bone_ik((0.0, 0.0), l1, l2, target, bend=rng.choice([1, -1]))
    tip = add(polar(t1, l1), polar(t2, l2))
    worst = max(worst, length(sub(tip, target)))
results["two_bone_ik"] = {
    "solves": 1000,
    "worst_tip_error_px": worst,
    "us_per_solve": (time.perf_counter() - t0) / 1000 * 1e6,
}

# 2. FABRIK: iterations and cost by chain length and tolerance.
fab = {}
for n_links in (3, 5, 8, 16):
    for tol in (1e-1, 1e-3):
        iters, errs = [], []
        t0 = time.perf_counter()
        for _ in range(200):
            joints = [(i * 30.0, 0.0) for i in range(n_links + 1)]
            r = rng.uniform(0.2, 0.95) * n_links * 30
            _, n, err = fabrik(joints, polar(rng.uniform(-math.pi, math.pi), r),
                               tolerance=tol, max_iterations=500)
            iters.append(n)
            errs.append(err)
        fab[f"{n_links}_links_tol_{tol:g}"] = {
            "median_iterations": statistics.median(iters),
            "max_iterations": max(iters),
            "hit_cap": sum(1 for n in iters if n >= 500),
            "worst_error_px": max(errs),
            "us_per_solve": (time.perf_counter() - t0) / 200 * 1e6,
        }
results["fabrik"] = fab

# 3. Quasi-static settle: a 6-stick chain hung from a pin, started horizontal.
def hanging_chain(n: int, L: float = 30.0) -> Puppet:
    pos = [(i * L, 0.0) for i in range(n + 1)]
    sticks = [Stick(i, i + 1, L) for i in range(n)]
    return Puppet(positions=pos, sticks=sticks, pins=[Pin(0, lambda t: (0.0, 0.0))])

settle = {}
for n in (3, 6, 12):
    p = hanging_chain(n)
    t0 = time.perf_counter()
    rounds = p.settle(0.0)
    dt_ms = (time.perf_counter() - t0) * 1e3
    tip = p.positions[-1]
    verticality = abs(tip[0]) / (n * 30.0)
    q = hanging_chain(n)
    q.settle(0.0)
    settle[f"{n}_sticks"] = {
        "rounds": rounds,
        "ms": dt_ms,
        "tip_x_over_length": verticality,
        "same_digest_on_rerun": p.digest() == q.digest(),
        "worst_stick_error_px": max(
            abs(length(sub(p.positions[s.j], p.positions[s.i])) - s.length) for s in p.sticks
        ),
    }
results["settle_hanging_chain"] = settle

# 3b. Pose mode per frame: re-settle the 6-stick chain for 48 frames of a moving pin.
p = hanging_chain(6)
p.settle(0.0)
t0 = time.perf_counter()
rounds_per_frame = []
for f in range(48):
    x = 40.0 * math.sin(2 * math.pi * f / 48)
    p.pins = [Pin(0, (lambda x: (lambda t: (x, 0.0)))(x))]
    p.__post_init__()
    rounds_per_frame.append(p.settle(0.0))
results["pose_mode_per_frame_6_sticks_moving_pin"] = {
    "frames": 48,
    "median_rounds": statistics.median(rounds_per_frame),
    "max_rounds": max(rounds_per_frame),
    "ms_per_frame": (time.perf_counter() - t0) / 48 * 1e3,
}

# 4. Dynamic marionette: 10 s at 24 fps, 4 substeps, 8 iterations.
def run_marionette(frames: int = 240, fps: int = 24):
    pup, idx = marionette()
    pup.settle(0.0)
    worst_err, worst_limit = 0.0, 0.0
    t0 = time.perf_counter()
    for f in range(frames):
        t = f / fps
        err = pup.step(t, 1.0 / fps, substeps=4, iterations=8)
        worst_err = max(worst_err, err)
        for lim in pup.limits:
            a, b, c = (pup.positions[k] for k in (lim.a, lim.b, lim.c))
            th = wrap_angle(angle_of(sub(c, b)) - angle_of(sub(a, b)))
            worst_limit = max(worst_limit, max(0.0, lim.lo - th, th - lim.hi))
    return pup, (time.perf_counter() - t0), worst_err, worst_limit

p1, secs1, err1, lim1 = run_marionette()
p2, secs2, err2, lim2 = run_marionette()
results["marionette_dynamic_240_frames"] = {
    "particles": len(p1.positions), "sticks": len(p1.sticks), "strings": len(p1.strings),
    "hinge_limits": len(p1.limits),
    "seconds_total": secs1, "ms_per_frame": secs1 / 240 * 1e3,
    "worst_constraint_error_px_after_last_iteration": err1,
    "worst_hinge_limit_violation_deg": lim1 * 180 / math.pi,
    "same_digest_on_rerun": p1.digest() == p2.digest(),
}

# 5. Pose mode on the marionette: hands pinned by rods, legs settle under gravity.
pup, idx = marionette()
# Reachable targets: 63 px from the neck for a 72 px arm (the first draft asked
# for 85 px, beyond reach, and measured 116 px of conflict: an unreachable rod
# target must be refused or softened, never solved).
pup.pins = [Pin(idx["hand_l"], lambda t: (-60.0, -80.0)), Pin(idx["hand_r"], lambda t: (60.0, -80.0))]
pup.__post_init__()
t0 = time.perf_counter()
rounds = pup.settle(0.0)
results["marionette_pose_settle_hands_pinned"] = {
    "rounds": rounds,
    "ms": (time.perf_counter() - t0) * 1e3,
    "hand_l_at_target": length(sub(pup.positions[idx["hand_l"]], (-60.0, -80.0))) < 1e-9,
    "worst_stick_error_px": max(
        abs(length(sub(pup.positions[s.j], pup.positions[s.i])) - s.length) for s in pup.sticks
    ),
    "feet_below_pelvis": all(pup.positions[idx[k]][1] > pup.positions[idx["pelvis"]][1] for k in ("foot_l", "foot_r")),
}

# 6. Baking cost estimate: channels per frame for this puppet (x, y, rotation per stick).
results["baking"] = {
    "channels": len(p1.sticks) * 3,
    "samples_at_24fps_10s_if_one_key_per_frame": len(p1.sticks) * 3 * 240,
}

print(json.dumps(results, indent=1))
