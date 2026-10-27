"""A deterministic 2D constraint solver: bodies joined at points, driven at a
few of them, settled by gravity (an#499, ADR 0008).

Four nouns and one verb. A :class:`Body` is a rigid rectangle posed by
``(x, y, rotation, scale)``; a :class:`Point` on it is a fraction of its
extent. A joint relates two bodies (or a body and :data:`WORLD`):
:class:`Pin`, :class:`Hinge` (a pin with an angle range), :class:`Weld`,
:class:`Distance` (``equal`` a rod, ``at_most`` a string, ``at_least`` a
spacer), :class:`Slide` (a groove) and :class:`Contact` (one-sided: a foot on
the ground, a lamp on a table). A driver is a target on a body's channels (a
nail: met exactly where the joints allow), a :class:`Force` (a push, or a
soft pull toward a point), or gravity. :func:`solve` does one frame,
:func:`solve_frames` a run of them with the caller's targets and
joined/unjoined joints per frame, and both return a typed result that names
what could not be held instead of raising.

>>> torso = Body("torso", width=40.0, height=80.0)
>>> upper = Body("upper", x=20.0, y=-30.0, width=50.0, height=10.0, origin=(0.0, 0.5))
>>> fore = Body("fore", x=70.0, y=-30.0, width=40.0, height=8.0, origin=(0.0, 0.5))
>>> handle = Body("handle", x=80.0, y=10.0, width=4.0, height=4.0, fixed=True)
>>> arm = [Pin(Point("upper", 0.0, 0.5), Point("torso", 1.0, 0.125)),
...        Hinge(Point("fore", 0.0, 0.5), Point("upper", 1.0, 0.5), limits=(-2.6, 0.0)),
...        Pin(Point("fore", 1.0, 0.5), Point("handle", 0.5, 0.5))]
>>> solve([torso, upper, fore, handle], arm, targets={"torso": {"x": 0.0, "y": 0.0}}).ok
True

Nothing here imports the scene IR or the stage, and nothing names an
animation: bodies are numbers, joints are rows (``# extraction candidate``:
this becomes its own package when a second consumer exists). The compile
pass that reads joints from a scene is P2 (an#512).

**The method, and why** (measured in
``misc/docs/research/puppeteering_2026-10.md`` §4, which compared analytic
two-bone, CCD, FABRIK, PBD and XPBD on the same tasks, and re-measured on
this module by ``misc/docs/research/puppeteering_2026-10/measure_kinematics.py``,
results in ``kinematics_measurements.json`` beside it; CPython 3.12, x86-64,
one core). Extended position-based dynamics on 2D rigid bodies (XPBD,
Macklin et al. 2016; rigid bodies and joints, Müller et al. 2020):
Gauss–Seidel over the joints in a fixed order, each a projection with the
generalized inverse mass ``1/m + (r × n)² / I`` about the body's centre (or
about its pose point while that is held), hinge limits as angular
projections, a fixed count of substeps and iterations. It is the one family
of the five that does chains, strings, rods, contacts, gravity and
unjoining in one loop, and its compliance is a stiffness that does not
depend on the iteration count. Its weakness, slow propagation down long
chains, is covered for the common case by the analytic two-link solve used
as the initial guess for every chain between two held ends (an arm with a
hand is a two-link chain whose second link is the forearm and the hand held
at their current angles), which also makes the elbow's bend side an explicit
choice (the side its range allows, else the side it already has).

- **Convergence per iteration** (the arm above, pose mode, worst residual):
  from the closed-form start, 2e-14 px after one pass; from a cold start,
  5.8 / 3.3 / 0.80 / 0.10 / 0.0014 px after 1 / 2 / 4 / 8 / 16 passes, 5e-14
  after 64. A frame that leaves a joint failing is retried with four times
  the passes, so the default eight reach the sixteen-pass figure when needed.
- **Singularities**: a target at exactly full reach (a straight arm) is met
  with zero residual and a straight elbow; 1 px or 5 px beyond reach the
  grip alone is refused (``dropped``, its gap in ``unsatisfied``), the
  shoulder and elbow hold exactly, and the arm points straight at the
  target; a target on the shoulder itself (inside the nearest reach, where
  the direction is undefined) is refused the same way, the arm left where
  it was rather than guessed. (The torso is nailed in rotation here; free
  to turn, it turns toward the target first.) A chain between two rigidly
  held ends whose ends are outside its reach is refused before any pass.
- **A straight chain pushed along its length** (a rope bridge of 3 to 20
  planks pinned at 0.8 of its length, laid straight): no correction has a
  sideways part, so nothing moves; the retry's start, nudged by 1e-3 rad,
  buckles it, and every joint holds (tests).
- **Stability at frame-exact steps** (a 12-link chain dropped horizontal, 10 s
  at 24 fps, under gravity): at 4 substeps (the default) no frame fails a
  joint and the tip hangs within 0.03° of vertical; at 1 or 2 substeps the
  whip under-converges (worst 3.2 / 0.9 px with the retry, 17 / 3.4 px
  without), reported per frame and never given up (a tree cannot conflict).
  Nothing diverges at any setting.
- **Compliance**: a soft rod (``compliance=1e-4``) under a 100-unit weight
  stretches 11.85 units after one second at 1, 2, 8 and 32 iterations alike,
  to the digit; it settles to the static 9.8.
- **Cost per frame**, dynamic, defaults: 14 ms for five ten-part
  marionettes (50 bodies, 65 joints, 25 strings), no frame failing; 0.9 ms for
  the two-link reach in pose mode. A 50-link rope or chain costs 34-48 ms (the
  retry runs on its failing frames) and under-converges on 40-47 of 48 frames
  (Gauss–Seidel's n² propagation): reported, never cut. Long ropes want more
  substeps, or the FABRIK seam the research names.
- **Determinism**: Python floats and :mod:`math` inside the loop, numpy at the
  boundary; bitwise-equal poses across runs and across processes on one
  platform (``tests/test_kinematics.py``). Not across platforms: a dynamic
  run amplifies a last-ulp libm difference (1e-13 on one frame's input is
  0.014 units 96 frames later), so a cache key is built on the inputs
  (:func:`inputs_digest`, with :data:`SOLVER_VERSION`), never the output.

**A retry that stops converging is a conflict** (an#568). In dynamic mode an
arm swinging back from a refused grip toward one inside its length but past
its elbow's range halved its failure on the first retry, then sat at ~1.2 px
for any number of passes: it was reported as slow and never given up. The
retry now repeats while each round still makes progress (up to
``DFLT_CONVERGE_CAP`` × ``iterations``) and a stall is resolved as a conflict.
On 300 random out-and-back reaches, no frame is left failing in either mode
(126 were, up to 6 px); a 50-link rope with its end out of reach costs ~90
rather than ~40 ms a frame, with 7 rather than 22 frames failing.

Not in this version: friction (a contact is frictionless: a lamp on a table
sliding sideways stays where it is until the edge passes), blending a snap
(a rejoined joint closes its gap in one frame, reported in
:attr:`FramesResult.snaps`), and the stochastic driver ``seed`` is reserved
for.
"""

from an.kinematics.bodies import WORLD, Body, Point, inertia, mass, point_world
from an.kinematics.chains import arc_chain, reach, two_bone
from an.kinematics.joints import (
    Contact,
    Distance,
    Force,
    Hinge,
    Joint,
    Pin,
    Slide,
    Weld,
)
from an.kinematics.solver import (
    DFLT_ITERATIONS,
    DFLT_SUBSTEPS,
    POSE_CHANNELS,
    SOLVER_VERSION,
    FramesResult,
    KinematicsError,
    SolveResult,
    digest,
    inputs_digest,
    quantize,
    resolve_rests,
    solve,
    solve_frames,
)

__all__ = [
    "WORLD",
    "Body",
    "Point",
    "mass",
    "inertia",
    "point_world",
    "Pin",
    "Hinge",
    "Weld",
    "Distance",
    "Slide",
    "Contact",
    "Joint",
    "Force",
    "reach",
    "two_bone",
    "arc_chain",
    "solve",
    "solve_frames",
    "resolve_rests",
    "SolveResult",
    "FramesResult",
    "KinematicsError",
    "quantize",
    "digest",
    "inputs_digest",
    "SOLVER_VERSION",
    "POSE_CHANNELS",
    "DFLT_ITERATIONS",
    "DFLT_SUBSTEPS",
]
