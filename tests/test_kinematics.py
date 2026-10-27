"""The kinematics solver (an#499): the worked cases, determinism, and the
refusals.

Each worked case is a puppet the issue names: a two-link arm reaching a
moving handle while its shoulder is driven (reeleehq/cutan#97), a marionette
on four strings under gravity, a lamp resting on a driven table, a hinge
stopping at its range, and a part unjoined, falling, and rejoined. Screen
coordinates are y-down, so gravity is ``(0, +g)`` and "above" is a smaller y.
"""

from __future__ import annotations

import math
import subprocess
import sys
import textwrap

import numpy as np
import pytest

from an.kinematics import (
    WORLD,
    Body,
    Contact,
    Distance,
    Force,
    Hinge,
    KinematicsError,
    Pin,
    Point,
    Slide,
    Weld,
    digest,
    point_world,
    solve,
    solve_frames,
)

FPS = 24
MARIONETTE_FRAMES = 6 * FPS
DT = 1.0 / FPS
G = (0.0, 980.0)


def _wrap(theta: float) -> float:
    return (theta + math.pi) % (2 * math.pi) - math.pi


# -----------------------------------------------------------------------------
# The two-link arm on a moving handle, shoulder driven (cutan#97)
# -----------------------------------------------------------------------------


def _arm():
    torso = Body("torso", width=40.0, height=80.0)
    upper = Body("upper", x=20.0, y=-30.0, width=50.0, height=10.0, origin=(0.0, 0.5))
    fore = Body("fore", x=70.0, y=-30.0, width=40.0, height=8.0, origin=(0.0, 0.5))
    handle = Body("handle", x=80.0, y=10.0, width=4.0, height=4.0, fixed=True)
    joints = [
        Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
        Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
        Pin(Point("fore", 1.0, 0.5), Point("handle", 0.5, 0.5)),
    ]
    return [torso, upper, fore, handle], joints


def _arm_targets(k: int) -> dict:
    """The torso walks right and bobs; the handle swings on an arc."""
    t = k / FPS
    return {
        "torso": {"x": 15.0 * t, "y": 4.0 * math.sin(2 * math.pi * t)},
        "handle": {"x": 75.0 + 12.0 * math.cos(1.5 * t), "y": 10.0 + 15.0 * math.sin(1.5 * t)},
    }


def test_two_link_arm_follows_a_moving_handle_with_the_shoulder_driven():
    bodies, joints = _arm()
    r = solve_frames(bodies, joints, frames=48, dt=None, targets_at=_arm_targets)
    assert all(u == () for u in r.unsatisfied)
    assert all(v == () for v in r.limit_violations)
    names = r.bodies
    upper, fore = names.index("upper"), names.index("fore")
    rel = [_wrap(r.poses[k, upper, 2] - r.poses[k, fore, 2]) for k in range(48)]
    # The elbow keeps one bend side (its range), and moves smoothly.
    assert all(-2.6 - 1e-3 <= v <= 1e-3 for v in rel)
    assert max(abs(a - b) for a, b in zip(rel, rel[1:])) < 0.2
    # The hand is on the handle, the arm on the shoulder, every frame.
    for k in range(48):
        bodies_k = {b.name: b.posed(x=r.poses[k, i, 0], y=r.poses[k, i, 1], rotation=r.poses[k, i, 2])
                    for i, b in enumerate(bodies)}
        hand = point_world(bodies_k["fore"], Point("fore", 1.0, 0.5))
        grip = point_world(bodies_k["handle"], Point("handle", 0.5, 0.5))
        assert math.dist(hand, grip) < 1e-3


def test_two_link_arm_is_exact_from_a_cold_start_and_takes_the_allowed_bend():
    bodies, joints = _arm()
    r = solve(bodies, joints, targets={"torso": {"x": 0.0, "y": 0.0}})
    assert r.ok and max(r.residuals) < 1e-6
    rel = _wrap(r.pose("upper").rotation - r.pose("fore").rotation)
    assert -2.6 <= rel <= 0.0
    # The other bend side, if asked by the range, is taken instead.
    flipped = [joints[0], Hinge(joints[1].a, joints[1].b, limits=(0.0, 2.6)), joints[2]]
    r2 = solve(bodies, flipped, targets={"torso": {"x": 0.0, "y": 0.0}})
    assert r2.ok and 0.0 <= _wrap(r2.pose("upper").rotation - r2.pose("fore").rotation) <= 2.6


def test_a_handle_out_of_reach_is_refused_and_the_arm_reaches_toward_it():
    bodies, joints = _arm()
    bodies[3] = bodies[3].posed(x=300.0, y=-30.0)
    r = solve(bodies, joints, targets={"torso": {"x": 0.0, "y": 0.0}})
    assert [j for j, _ in r.unsatisfied] == [2] and r.dropped == (2,)
    assert r.residuals[0] < 1e-6 and r.residuals[1] < 1e-6
    # Straight, and pointing at the handle.
    assert abs(_wrap(r.pose("upper").rotation - r.pose("fore").rotation)) < 1e-6
    assert abs(r.pose("fore").rotation) < 1e-6
    # Without dropping, the conflict is reported on every joint it tears.
    torn = solve(bodies, joints, targets={"torso": {"x": 0.0, "y": 0.0}}, drop_conflicts=False)
    assert torn.dropped == () and 2 in [j for j, _ in torn.unsatisfied]


# -----------------------------------------------------------------------------
# The marionette: a driven bar, four strings, gravity
# -----------------------------------------------------------------------------


def _marionette():
    """A torso hung from the bar by a head string, two two-link arms, two
    two-link legs; strings from the bar to both hands and both knees."""
    bar = Body("bar", y=-200.0, width=160.0, height=6.0, fixed=True)
    torso = Body("torso", width=40.0, height=70.0, origin=(0.5, 0.0))
    bodies = [bar, torso]
    joints = [Distance(Point("torso", 0.5, 0.0), Point("bar", 0.5, 0.5), length=200.0, mode="at_most")]
    for side, sx in (("l", -1.0), ("r", 1.0)):
        u = 0.0 if sx < 0 else 1.0
        bodies += [
            Body(f"{side}_upper", x=sx * 20.0, y=5.0, width=8.0, height=30.0, origin=(0.5, 0.0)),
            Body(f"{side}_fore", x=sx * 20.0, y=35.0, width=7.0, height=28.0, origin=(0.5, 0.0)),
            Body(f"{side}_thigh", x=sx * 10.0, y=70.0, width=10.0, height=35.0, origin=(0.5, 0.0)),
            Body(f"{side}_shin", x=sx * 10.0, y=105.0, width=9.0, height=35.0, origin=(0.5, 0.0)),
        ]
        joints += [
            Pin(Point(f"{side}_upper", 0.5, 0.0), Point("torso", u, 5.0 / 70.0)),
            Hinge(Point(f"{side}_fore", 0.5, 0.0), Point(f"{side}_upper", 0.5, 1.0), limits=(-2.4, 2.4)),
            Pin(Point(f"{side}_thigh", 0.5, 0.0), Point("torso", 0.5 + sx * 0.25, 1.0)),
            Hinge(Point(f"{side}_shin", 0.5, 0.0), Point(f"{side}_thigh", 0.5, 1.0), limits=(-2.4, 0.0)),
        ]
    for side, bu in (("l", 0.0), ("r", 1.0)):
        joints += [
            Distance(Point(f"{side}_fore", 0.5, 1.0), Point("bar", bu, 0.5), length=268.0, mode="at_most"),
            Distance(Point(f"{side}_thigh", 0.5, 1.0), Point("bar", 0.5 + (bu - 0.5) * 0.4, 0.5),
                     length=304.0, mode="at_most"),
        ]
    return bodies, joints


def _bar(k: int) -> dict:
    """Two seconds of sway, bob and tilt; then a walk 100 units right over a
    second; then still."""
    t = k / FPS
    if t < 2.0:
        return {"bar": {"x": 40.0 * math.sin(math.pi * t), "y": -200.0 - 20.0 * max(0.0, math.sin(2 * math.pi * t)),
                        "rotation": 0.2 * math.sin(math.pi * t)}}
    return {"bar": {"x": 100.0 * min(1.0, t - 2.0), "y": -200.0, "rotation": 0.0}}


def test_marionette_hangs_from_its_strings_and_follows_the_bar():
    bodies, joints = _marionette()
    r = solve_frames(bodies, joints, frames=MARIONETTE_FRAMES, dt=DT, targets_at=_bar, gravity=G)
    strings = [j for j, joint in enumerate(joints) if isinstance(joint, Distance)]
    # After a frame of settling every string holds (at most its length), and
    # every joint and range holds.
    for k in range(1, MARIONETTE_FRAMES):
        assert r.unsatisfied[k] == (), (k, r.unsatisfied[k])
        assert r.limit_violations[k] == (), (k, r.limit_violations[k])
    names = r.bodies
    torso, bar = names.index("torso"), names.index("bar")
    # It hangs below the bar ...
    assert (r.poses[:, torso, 1] > r.poses[:, bar, 1] + 150.0).all()
    # ... swings while the bar sways (a pendulum, so it lags) ...
    assert np.ptp(r.poses[: 2 * FPS, torso, 0]) > 10.0
    # ... and settles under it once the bar has walked away and stopped.
    assert r.poses[-1, torso, 0] == pytest.approx(100.0, abs=5.0)
    assert abs(r.poses[-1, torso, 2]) < 0.05
    assert len(strings) == 5
    assert all(d == () for d in r.dropped)


# -----------------------------------------------------------------------------
# The lamp on a driven table: one-sided contact
# -----------------------------------------------------------------------------


def _lamp_on_table():
    table = Body("table", y=0.0, width=120.0, height=10.0, origin=(0.5, 0.0), fixed=True)
    lamp = Body("lamp", y=-30.0, width=20.0, height=30.0, origin=(0.5, 0.0))
    top = (Point("table", 0.0, 0.0), Point("table", 1.0, 0.0))
    joints = [Contact(Point("lamp", 0.0, 1.0), *top), Contact(Point("lamp", 1.0, 1.0), *top)]
    return [table, lamp], joints


def test_lamp_rides_a_rising_table_and_falls_back_on_it():
    bodies, joints = _lamp_on_table()

    def table(k):  # rises 30 units over 12 frames, holds, drops back by 30 over 4
        y = -30.0 * min(k, 12) / 12 if k < 24 else -30.0 + 30.0 * min(k - 24, 4) / 4
        return {"table": {"x": 0.0, "y": y}}

    r = solve_frames(bodies, joints, frames=48, dt=DT, targets_at=table, gravity=G)
    lamp, tbl = r.bodies.index("lamp"), r.bodies.index("table")
    bottom = r.poses[:, lamp, 1] + 30.0  # the lamp's base
    top = r.poses[:, tbl, 1]
    # Never through the table top ...
    assert (bottom <= top + 0.25).all()
    # ... carried up while the table rises, and resting on it at the end.
    assert bottom[12] == pytest.approx(top[12], abs=0.25)
    assert bottom[-1] == pytest.approx(top[-1], abs=0.25)
    assert abs(r.poses[-1, lamp, 2]) < 1e-3  # still upright


def test_lamp_falls_off_the_edge_when_the_table_slides_away():
    bodies, joints = _lamp_on_table()
    r = solve_frames(bodies, joints, frames=36, dt=DT, gravity=G,
                     targets_at=lambda k: {"table": {"x": 8.0 * k, "y": 0.0}})
    lamp = r.bodies.index("lamp")
    # Frictionless: the lamp stays put while the table slides from under it
    # (half the table width plus half the lamp's, then it is over the edge).
    assert abs(r.poses[5, lamp, 0]) < 0.05
    assert r.poses[-1, lamp, 1] > 100.0


# -----------------------------------------------------------------------------
# A hinge that stops at its range
# -----------------------------------------------------------------------------


def _swing(limits):
    upper = Body("upper", width=50.0, height=10.0, origin=(0.0, 0.5), fixed=True)
    fore = Body("fore", x=50.0, width=40.0, height=8.0, origin=(0.0, 0.5))
    # The range is the forearm's angle relative to the upper arm (b relative to a).
    return [upper, fore], [Hinge(Point("upper", 1.0, 0.5), Point("fore", 0.0, 0.5), limits=limits)]


def test_a_hinge_stops_at_its_range():
    bodies, joints = _swing((-0.5, 0.6))
    r = solve_frames(bodies, joints, frames=48, dt=DT, gravity=G)
    fore = r.bodies.index("fore")
    assert all(v == () for v in r.limit_violations)
    assert r.poses[:, fore, 2].max() <= 0.6 + 1e-3
    assert r.poses[-1, fore, 2] == pytest.approx(0.6, abs=1e-3)
    # Without the range it swings past it toward hanging straight down.
    free_bodies, free_joints = _swing(None)
    free = solve_frames(free_bodies, free_joints, frames=48, dt=DT, gravity=G)
    assert free.poses[:, fore, 2].max() > 1.2


# -----------------------------------------------------------------------------
# Unjoin, fall, rejoin
# -----------------------------------------------------------------------------


def test_an_unjoined_part_falls_and_is_caught_when_rejoined():
    peg = Body("peg", width=2.0, height=2.0, fixed=True)
    part = Body("part", width=4.0, height=20.0, origin=(0.5, 0.0))
    pin = Pin(Point("part", 0.5, 0.0), Point("peg", 0.5, 0.5))
    loose = Pin(pin.a, pin.b, joined=False)
    r = solve_frames([peg, part], [pin], frames=24, dt=DT, gravity=G,
                     joints_at=lambda k: [loose] if 4 <= k < 10 else [pin])
    y = r.poses[:, 1, 1]
    assert (abs(y[:4]) < 1e-6).all()  # held
    assert (np.diff(y[4:10]) > 0).all()  # falling, faster and faster
    assert (np.diff(y[4:10], 2) > 0).all()
    assert [s[:2] for s in r.snaps] == [(10, 0)] and r.snaps[0][2] == pytest.approx(y[9], rel=1e-9)
    assert all(u == () for u in r.unsatisfied)
    # Rejoined, it is held at the peg again.
    assert abs(y[10]) < 0.25 and abs(y[-1]) < 0.25


# -----------------------------------------------------------------------------
# The other joints and drivers
# -----------------------------------------------------------------------------


def test_weld_holds_the_relative_pose():
    head = Body("head", width=30.0, height=30.0)
    hat = Body("hat", y=-25.0, rotation=0.1, width=30.0, height=20.0)
    weld = Weld(Point("hat", 0.5, 1.0), Point("head", 0.5, 0.0))
    r = solve([head, hat], [weld], targets={"head": {"x": 10.0, "y": 5.0, "rotation": 0.7}})
    assert r.ok
    assert r.pose("hat").rotation - r.pose("head").rotation == pytest.approx(0.1, abs=1e-6)


def test_slide_keeps_a_bead_on_its_groove_within_the_ends():
    bead = Body("bead", x=10.0, y=0.0, width=2.0, height=2.0)
    groove = Slide(Point("bead", 0.5, 0.5), Point(WORLD, 0.0, 0.0), Point(WORLD, 100.0, 0.0))
    r = solve_frames([bead], [groove], frames=24, dt=DT, gravity=G,
                     forces=[Force(Point("bead", 0.5, 0.5), vector=(4000.0, 0.0))])
    x, y = r.poses[:, 0, 0], r.poses[:, 0, 1]
    assert (abs(y) < 0.25).all() and x[-1] == pytest.approx(100.0, abs=0.25)
    assert all(u == () for u in r.unsatisfied)


def test_distance_modes():
    a = Body("a", width=2.0, height=2.0, fixed=True)
    b = Body("b", x=30.0, width=2.0, height=2.0)
    p, q = Point("a", 0.5, 0.5), Point("b", 0.5, 0.5)
    rod = solve([a, b], [Distance(p, q, length=10.0)])
    rope = solve([a, b], [Distance(p, q, length=50.0, mode="at_most")])
    spacer = solve([a, b], [Distance(p, q, length=40.0, mode="at_least")])
    assert rod.pose("b").x == pytest.approx(10.0, abs=1e-6)
    assert rope.pose("b").x == 30.0  # slack: untouched
    assert spacer.pose("b").x == pytest.approx(40.0, abs=1e-6)


def test_a_pull_is_soft_and_a_push_turns_an_off_centre_body():
    a = Body("a", width=10.0, height=10.0)
    pulled = solve([a], [], forces=[Force(Point("a", 0.5, 0.5), toward=(20.0, 0.0), strength=1e-3)])
    assert 0.0 < pulled.pose("a").x < 20.0
    pushed = solve([a], [], dt=DT, forces=[Force(Point("a", 0.5, 0.0), vector=(100.0, 0.0))])
    assert pushed.pose("a").vx > 0 and pushed.pose("a").omega != 0.0


def test_a_soft_rod_stretches_by_its_compliance_whatever_the_iterations():
    """XPBD's claim: compliance is a stiffness independent of the iteration
    count. 1e-4 units per unit of force under a 100-unit weight at 980 is a
    9.8-unit static stretch; it is reported in the residuals, never as a
    failure."""
    anchor = Body("anchor", width=2.0, height=2.0, fixed=True)
    weight = Body("weight", y=50.0, width=10.0, height=10.0)
    rod = Distance(Point("weight", 0.5, 0.5), Point("anchor", 0.5, 0.5), length=50.0, compliance=1e-4)
    runs = [solve_frames([anchor, weight], [rod], frames=3 * FPS, dt=DT, gravity=G, iterations=n) for n in (1, 8)]
    assert runs[0].final[1].y == pytest.approx(runs[1].final[1].y, abs=1e-9)
    assert runs[1].final[1].y - 50.0 == pytest.approx(9.8, abs=0.5)
    assert all(u == () and d == () for u, d in zip(runs[1].unsatisfied, runs[1].dropped))


def test_a_grip_out_of_reach_in_dynamic_mode_is_let_go_and_regripped():
    bodies, joints = _arm()
    nailed = {"torso": {"x": 0.0, "y": 0.0, "rotation": 0.0}}

    def handle(k):  # out 72 units (beyond reach from frame 4) and back by frame 30
        return {**nailed, "handle": {"x": 80.0 + 6.0 * min(k, 12) - 6.0 * min(max(0, k - 18), 12), "y": 10.0}}

    r = solve_frames(bodies, joints, frames=60, dt=DT, targets_at=handle)
    let_go = [k for k, d in enumerate(r.dropped) if d]
    assert let_go and all(r.dropped[k] == (2,) for k in let_go)
    # The structure holds every frame the grip is let go ...
    assert all(j == 2 for k in let_go for j, _ in r.unsatisfied[k])
    # ... the regrip is reported as a snap across the gap, and it holds again.
    regrip = let_go[-1] + 1
    assert [s[:2] for s in r.snaps] == [(regrip, 2)] and r.snaps[0][2] > 1.0
    assert r.unsatisfied[-1] == () and r.dropped[-1] == ()


# -----------------------------------------------------------------------------
# Found by the adversarial review of the first draft (PR #528)
# -----------------------------------------------------------------------------

NAILED = {"torso": {"x": 0.0, "y": 0.0, "rotation": 0.0}}


@pytest.mark.parametrize("dt", [None, DT])
def test_a_grip_just_beyond_reach_gives_up_the_grip_never_the_elbow(dt):
    bodies, joints = _arm()
    bodies[3] = bodies[3].posed(x=20.0 + 90.3 * math.cos(0.8), y=-30.0 + 90.3 * math.sin(0.8))
    r = solve_frames(bodies, joints, frames=6, dt=dt, targets_at=lambda k: NAILED)
    assert all(d == (2,) for d in r.dropped)
    assert all([j for j, _ in u] == [2] for u in r.unsatisfied)


@pytest.mark.parametrize("planks", [3, 8, 12, 20])
def test_a_straight_bridge_pinned_short_buckles_instead_of_dropping_an_anchor(planks):
    """Straight and pushed along its length, no correction has a sideways
    part: the retry's nudge gives it one."""
    length = 10.0
    bodies = [Body(f"p{k}", x=k * length, width=length, height=2.0, origin=(0.0, 0.5)) for k in range(planks)]
    joints = [Pin(Point("p0", 0.0, 0.5), Point(WORLD, 0.0, 0.0))]
    joints += [Pin(Point(f"p{k}", 0.0, 0.5), Point(f"p{k - 1}", 1.0, 0.5)) for k in range(1, planks)]
    joints.append(Pin(Point(f"p{planks - 1}", 1.0, 0.5), Point(WORLD, 0.8 * planks * length, 0.0)))
    r = solve(bodies, joints)
    assert r.ok and r.dropped == ()


def test_an_arm_already_on_its_grip_with_the_elbow_on_the_wrong_side_is_flipped():
    from an.kinematics import two_bone

    torso, upper, fore, handle = _arm()[0]
    t1, t2 = two_bone((20.0, -30.0), (80.0, 10.0), (50.0, 40.0), bend=1)
    upper = upper.posed(rotation=t1)
    fore = fore.posed(x=20.0 + 50.0 * math.cos(t1), y=-30.0 + 50.0 * math.sin(t1), rotation=t2)
    joints = _arm()[1]
    joints[1] = Hinge(joints[1].a, joints[1].b, limits=(-2.6, 0.0), rest=0.0)
    assert not -2.6 <= _wrap(t1 - t2) <= 0.0  # it starts on the forbidden side
    r = solve([torso, upper, fore, handle], joints, targets=NAILED)
    assert r.ok and -2.6 <= _wrap(r.pose("upper").rotation - r.pose("fore").rotation) <= 0.0


def test_a_range_near_half_a_turn_is_kept_at_its_nearer_bound():
    upper = Body("upper", width=50.0, height=10.0, origin=(0.0, 0.5), fixed=True)
    fore = Body("fore", x=50.0, rotation=3.3, width=40.0, height=8.0, origin=(0.0, 0.5))
    hinge = Hinge(Point("upper", 1.0, 0.5), Point("fore", 0.0, 0.5), limits=(0.0, 3.0), rest=0.0)
    r = solve([upper, fore], [hinge])
    assert r.ok and r.pose("fore").rotation == pytest.approx(3.0, abs=1e-3)  # not 0: 0.3 away, not 3.3


def test_the_arm_with_a_hand_bone_keeps_its_grip():
    """reeleehq/cutan#104's shape: upper arm, forearm, and a hand with a
    wrist range, the hand on the handle."""
    torso, upper, fore, handle = _arm()[0]
    hand = Body("hand", x=110.0, y=-30.0, width=12.0, height=8.0, origin=(0.0, 0.5))
    joints = [
        Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
        Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
        Hinge(Point("fore", 1.0, 0.5), Point("hand", 0.0, 0.5), limits=(-0.5, 0.5)),
        Pin(Point("hand", 1.0, 0.5), Point("handle", 0.5, 0.5)),
    ]
    r = solve_frames([torso, upper, fore, hand, handle], joints, frames=48, dt=None, targets_at=_arm_targets)
    assert all(u == () for u in r.unsatisfied) and all(v == () for v in r.limit_violations)
    assert all(d == () for d in r.dropped)


def test_a_body_held_in_one_channel_can_still_be_in_conflict():
    r = solve([Body("b")], [Pin(Point("b", 0.5, 0.5), Point(WORLD, 50.0, 0.0))], targets={"b": {"x": 0.0}})
    assert r.dropped == (0,) and r.unsatisfied == ((0, 50.0),)


# -----------------------------------------------------------------------------
# Determinism: bitwise across runs and processes
# -----------------------------------------------------------------------------

_DETERMINISM_SCRIPT = textwrap.dedent(
    """
    import sys
    sys.path[:0] = {paths!r}
    from tests.test_kinematics import _marionette, _bar, DT, G
    from an.kinematics import solve_frames
    bodies, joints = _marionette()
    r = solve_frames(bodies, joints, frames=48, dt=DT, targets_at=_bar, gravity=G)
    sys.stdout.write(r.poses.tobytes().hex())
    """
)


def test_bitwise_equal_across_two_processes():
    script = _DETERMINISM_SCRIPT.format(paths=list(sys.path))
    outs = [
        subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True).stdout
        for _ in range(2)
    ]
    assert outs[0] and outs[0] == outs[1]
    bodies, joints = _marionette()
    here = solve_frames(bodies, joints, frames=48, dt=DT, targets_at=_bar, gravity=G)
    assert here.poses.tobytes().hex() == outs[0]
    assert digest(here.poses) == digest(np.frombuffer(bytes.fromhex(outs[0])).reshape(here.poses.shape))


# -----------------------------------------------------------------------------
# Refusals
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: solve([Body("b")], [], gravity=G), "gravity needs time"),
        (lambda: solve([Body("b")], [], forces=[Force(Point("b", 0.5, 0.5), vector=(1.0, 0.0))]), "needs time"),
        (lambda: solve([Body("b")], [], dt=0.0), "dt must be positive"),
        (lambda: solve([Body("b"), Body("b")], []), "unique"),
        (lambda: solve([Body(WORLD)], []), "world's name"),
        (lambda: solve([Body("b", width=0.0)], []), "positive width"),
        (lambda: solve([Body("b")], [Pin(Point("b", 0, 0), Point("nope", 0, 0))]), "unknown body 'nope'"),
        (lambda: solve([Body("b")], [Pin(Point(WORLD, 0, 0), Point(WORLD, 1, 1))]), "one body"),
        (lambda: solve([Body("b")], [], targets={"b": {"scale": 2.0}}), "cannot drive"),
        (lambda: solve([Body("a"), Body("b")], [Hinge(Point("a", 0, 0), Point("b", 0, 0), limits=(1.0, -1.0))]),
         "reversed"),
        (lambda: solve([Body("a"), Body("b")], [Hinge(Point("a", 0, 0), Point("b", 0, 0), limits=(-4.0, 0.0))]),
         "within"),
        (lambda: solve_frames([Body("b")], [], frames=3, dt=DT, targets_at=[None]), "entries for 3 frames"),
        (lambda: solve([Body("b", x=math.nan)], []), "not finite"),
        (lambda: solve([Body("b")], [], dt=math.inf), "not finite"),
        (lambda: solve([Body("b")], [], dt=DT, gravity=(0.0, math.nan)), "not finite"),
        (lambda: solve([Body("a"), Body("b")], [Pin(Point("a", 0, 0), Point("b", 0, 0), compliance=math.inf)]),
         "not finite"),
        (lambda: solve([Body("b")], [], targets={"b": {"x": math.inf}}), "not finite"),
    ],
)
def test_refusals_are_typed_and_say_why(call, message):
    with pytest.raises(KinematicsError, match=message):
        call()


def _out_and_back(k: int) -> dict:
    """The handle goes 146 units out (beyond reach), waits three frames, and
    comes back to 64 units along another bearing (an#568's search found it)."""
    out, back, far, near, n_out, n_back = (
        2.060339127936756, 2.324064969246928, 145.70112251312662, 64.26295476397914, 2, 4
    )
    if k < n_out:
        r, a = 60.0 + (far - 60.0) * k / n_out, out
    elif k < n_out + 3:
        r, a = far, out
    else:
        u = min(1.0, (k - n_out - 3) / n_back)
        r, a = far + (near - far) * u, out + (back - out) * u
    return {**NAILED, "handle": {"x": 20.0 + r * math.cos(a), "y": -30.0 + r * math.sin(a)}}


def test_the_frame_after_a_refusal_holds_every_joint_it_keeps():
    """an#568: dynamic mode, the arm swings back to a reachable grip in one
    frame; at one retry it was left ~1 px apart. No joint it keeps fails."""
    bodies, joints = _arm()
    r = solve_frames(bodies, joints, frames=14, dt=DT, targets_at=_out_and_back)
    regrips = [k for k in range(1, 14) if r.dropped[k - 1] and not r.dropped[k]]
    assert regrips and all(d == () for d in r.dropped[8:]), r.dropped  # held again
    for k in range(14):
        assert [j for j, _ in r.unsatisfied[k] if j not in r.dropped[k]] == [], k


def test_a_retry_that_stalls_is_a_conflict_in_dynamic_mode():
    """an#568: the handle comes back from out of reach to 21 units from the
    shoulder, inside the arm's length but past its elbow's range (~26). The
    first retry halves the failure, then it stalls at ~1.2 px for any number
    of passes; it is given up as a conflict (the grip), every other joint
    holding, instead of being left apart as "slow"."""
    out, back, far, near, n_out, n_back, wait = (
        -2.848966291475012, -0.8438582465511009, 159.53659553260178,
        21.222574113529397, 3, 1, 0,
    )  # fmt: skip

    def handle(k):
        if k < n_out:
            r, a = 60.0 + (far - 60.0) * k / n_out, out
        elif k < n_out + wait:
            r, a = far, out
        else:
            u = min(1.0, (k - n_out - wait) / n_back)
            r, a = far + (near - far) * u, out + (back - out) * u
        return {**NAILED, "handle": {"x": 20.0 + r * math.cos(a), "y": -30.0 + r * math.sin(a)}}

    bodies, joints = _arm()
    r = solve_frames(bodies, joints, frames=10, dt=DT, targets_at=handle)
    assert r.dropped[4] == (2,), r.dropped
    for k in range(10):
        assert [j for j, _ in r.unsatisfied[k] if j not in r.dropped[k]] == [], k


def _rope(n: int = 50, link: float = 10.0) -> tuple[list[Body], list[Pin]]:
    """A rope of ``n`` links hung from the world at one end and held at the
    other by a fixed body ``end`` (declared last: the grip)."""
    bodies = [
        Body(f"p{k}", x=k * link, y=0.0, width=link, height=2.0, origin=(0.0, 0.5))
        for k in range(n)
    ]
    bodies.append(
        Body("end", x=n * link * 0.7, y=0.0, width=2.0, height=2.0, fixed=True)
    )
    joints = [Pin(Point("p0", 0.0, 0.5), Point(WORLD, 0.0, 0.0))]
    joints += [
        Pin(Point(f"p{k}", 0.0, 0.5), Point(f"p{k - 1}", 1.0, 0.5)) for k in range(1, n)
    ]
    joints.append(Pin(Point(f"p{n - 1}", 1.0, 0.5), Point("end", 0.5, 0.5)))
    return bodies, joints


@pytest.mark.parametrize("n", [10, 30, 50])
def test_a_rope_gives_up_its_end_never_a_link_and_takes_it_back(n):
    """an#641: the rope's end goes out of reach for 20 frames and comes back.
    Held at both ends the rope is a loop, so a conflict on it is settled by
    giving up the grip (declared last), never an interior link, even when the
    rope, falling, is a little short of converged on links that are on no
    cycle once the end is given up. On main the links were given up from the
    frame the end came back, and the rope came apart by hundreds of px.

    an#645: back within reach, a rope hanging far from its end cannot close
    the gap in one frame; its end is walked to the grip at `regrip_speed`
    and taken back with a small snap (main: never, for 50 links; a jump of
    100 to 250 px for shorter ones)."""
    link = 10.0
    bodies, joints = _rope(n, link)

    def end_at(k):
        x = n * link * (1.3 if 4 <= k < 24 else 0.7)
        return {"end": {"x": x, "y": 0.0}}

    r = solve_frames(
        bodies, joints, frames=60, dt=DT, targets_at=end_at, gravity=(0.0, 980.0)
    )
    assert {j for d in r.dropped for j in d} == {n}, r.dropped
    worst = max((g for u in r.unsatisfied for j, g in u if j != n), default=0.0)
    assert worst < 1.5, worst
    after = [s for s in r.snaps if s[0] >= 24]
    assert after and all(j == n and gap < 25.0 for _k, j, gap in after), r.snaps
    assert r.dropped[-1] == ()  # held at the end
