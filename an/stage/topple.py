"""The ``topple`` compile pass: rigid bodies falling over, one knocking the next (:mod:`an.ir.topple`).

Runs after the ``solve`` pass (order :data:`TOPPLE_ORDER`), on the document as
the solve and the hold layer left it, so a figurine falls with the sabre its
hand holds. For each ``topple`` action, in the order they start:

1. **The body** is the entity's drawn ink at the instant it starts (every
   drawn node under it, plus every item a part of it holds then, per the hold
   report), as points on the stage. Its centre of mass is the centroid of
   their convex hull; its moment of inertia comes from the hull
   (:func:`an.stage.rigid.inertia`).
2. **The pivot** is its lowest point on the side it falls ``toward``.
3. **The fall** is :func:`an.stage.rigid.pivot_fall` from ``push`` (or, when
   ``after`` names the topple that knocks it, from that body's speed where it
   first touches this one), until another point of it reaches the floor (then
   a small bounce, :data:`an.stage.rigid.DFLT_BOUNCE`) or ``point`` reaches
   ``until`` (it stays there: nothing is cheated, so a target off the circle
   ``point`` sweeps is a :class:`ToppleError` saying how far to move the body).
4. **The keys**: every frame from its start, the body's entity node and the
   items it holds are turned about the pivot by the fall's angle, written as a
   ``__topple__<entity>`` clip after the solve's (the last clip of a track
   wins its channels).

The report, ``meta.extensions.topple``, lists each topple and its ``events``
(``topple``, ``hit``, ``land``, ``pin``, ``bounce``, ``rest``), which a sound
cue can be timed by (``at: {when: cam, event: land}``, :mod:`an.sound_anchors`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from an.stage.compile import CutoutCompileError

__all__ = ["TOPPLE_EXTENSION", "TOPPLE_ORDER", "ToppleError", "topple_pass"]

#: Where the pass runs: after ``solve`` (525), before the camera follows (550).
TOPPLE_ORDER: int = 535
#: The key of the report in the compiled document's ``meta.extensions``.
TOPPLE_EXTENSION: str = "topple"
#: The clip prefix of the keys a topple writes.
TOPPLE_CLIP_PREFIX: str = "__topple__"
#: A point within this many px of the lowest is on the floor with it.
FOOT_BAND_PX: float = 3.0
#: How far (px) ``point`` may pass from ``until`` and still be on it.
PIN_TOLERANCE_PX: float = 4.0
#: Steps per second when looking for the instant one body first touches another.
CONTACT_HZ: float = 480.0

Point = tuple[float, float]


class ToppleError(CutoutCompileError):
    """A topple that cannot happen as written: the message says why and what to change."""


def _rot_about(p: Point, c: Point, a: float) -> Point:
    s, co = math.sin(a), math.cos(a)
    dx, dy = p[0] - c[0], p[1] - c[1]
    return (c[0] + co * dx - s * dy, c[1] + s * dx + co * dy)


def _centroid(hull: Sequence[Point]) -> Point:
    """The area centroid of a convex polygon (its vertices' mean when degenerate)."""
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(hull, [*hull[1:], hull[0]]):
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < 1e-9:
        n = max(1, len(hull))
        return (sum(p[0] for p in hull) / n, sum(p[1] for p in hull) / n)
    return (cx / (3.0 * area), cy / (3.0 * area))


def _inside(p: Point, hull: Sequence[Point]) -> bool:
    """Whether ``p`` is inside the convex polygon ``hull`` (either winding)."""
    sign = 0
    for a, b in zip(hull, [*hull[1:], hull[0]]):
        c = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(c) < 1e-9:
            continue
        s = 1 if c > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def _touch(a: Sequence[Point], b: Sequence[Point]) -> Point | None:
    """A point where convex polygons ``a`` and ``b`` overlap (a vertex of one inside the other), else ``None``."""
    for p in a:
        if _inside(p, b):
            return p
    for p in b:
        if _inside(p, a):
            return p
    return None


def _affine(doc: Any, path: str, pose: Any) -> tuple[float, ...]:
    """``path``'s node-to-stage affine ``(a, b, c, d, x, y)`` at ``pose`` (before the camera)."""
    from an.stage.timeline import screen_position

    w, h = doc.meta.width / 2.0, doc.meta.height / 2.0

    def at(p: Point) -> Point:
        x, y = screen_position(doc, path, pose=pose, point=p, camera=False)
        return (x - w, y - h)

    o, ex, ey = at((0.0, 0.0)), at((1.0, 0.0)), at((0.0, 1.0))
    return (ex[0] - o[0], ex[1] - o[1], ey[0] - o[0], ey[1] - o[1], o[0], o[1])


def _nodes_under(doc: Any, root: str) -> list[tuple[str, Any]]:
    """``(path, node)`` of entity ``root`` and every node under it (:func:`an.stage.tree.walk_document`)."""
    from an.stage.tree import walk_document

    return [(p, n) for p, n in walk_document(doc) if p == root or p.startswith(root + "/")]


def _ink(doc: Any, mall: Any, path: str, pose: Any) -> list[Point]:
    """The drawn ink of ``path`` and everything under it, as stage points at ``pose``."""
    from an.stage.hold import ink_points
    from an.stage.solve import _apply

    pts: list[Point] = []
    for sub, node in _nodes_under(doc, path.split("/", 1)[0]):
        if not (sub == path or sub.startswith(path + "/")):
            continue
        if node.visual is None or not (node.visual.width and node.visual.height):
            continue
        m = _affine(doc, sub, pose)
        pts.extend(_apply(m, p) for p in ink_points(doc, node, mall))
    return pts


def _point(doc: Any, ref: str, pose: Any, *, where: str) -> Point:
    """A stage point: ``world@x,y``, or ``path@u,v`` (fractions of that node's drawing)."""
    from an.stage.hold import _local_box
    from an.stage.solve import _apply

    name, _, at = ref.partition("@")
    try:
        u, v = (float(s) for s in at.split(","))
    except ValueError:
        raise ToppleError(
            f"{where}: {ref!r} is not a point: say `path@u,v` (fractions of that "
            "node's drawing, 0,0 its top left) or `world@x,y`"
        ) from None
    if name == "world":
        return (u, v)
    node = next((n for p, n in _nodes_under(doc, name.split("/", 1)[0]) if p == name), None)
    if node is None:
        raise ToppleError(f"{where}: {ref!r} names {name!r}, which the shot does not draw")
    drawn = [(p, n) for p, n in _nodes_under(doc, name) if p.startswith(name) and n.visual is not None]
    if node.visual is None and drawn:
        name, node = drawn[0]
    left, top, w, h = _local_box(node)
    return _apply(_affine(doc, name, pose), (left + u * w, top + v * h))


def _decompose(m: Sequence[float]) -> tuple[float, float, float, bool]:
    from an.stage.solve import _decompose as dec

    return dec(tuple(m))


def _flat_topples(shot: Any) -> list[tuple[Any, float, str]]:
    from an.ir.compose import flatten

    out = []
    for k, action in enumerate(shot.actions):
        for flat in flatten(action):
            if getattr(flat.action, "kind", None) == "topple":
                out.append((flat.action, float(flat.start), f"actions/{k}"))
    return out


def topple_pass(state: Any) -> None:
    """The ``topple`` compile pass (order :data:`TOPPLE_ORDER`); a no-op for a shot with no ``topple``."""
    shot = state.shot
    topples = _flat_topples(shot)
    if not topples:
        return
    from an.ir.schema import gravity_vector
    from an.stage.compile import _assemble_document
    from an.stage.hold import DFLT_FALL_GRAVITY, _gravity
    from an.stage.rigid import DFLT_BOUNCE, MAX_BOUNCES, MIN_ROCK, _hull, inertia, pivot_fall
    from an.stage.solve import _compose, _invert, frame_times
    from an.stage.timeline import evaluate_timeline, timeline_from_scene

    doc = _assemble_document(state, background="#000000")
    timeline = timeline_from_scene(doc)
    times = frame_times(shot.duration, fps=state.fps, step_hz=None)
    # Gravity is the falls' (shot, else style pack, else the hold layer's
    # default). The floor is each body's own foot line, not `solve.ground`: in
    # a 2.5D set a body standing farther back falls onto its own line.
    g = (_gravity(shot, state.style_pack) or (0.0, DFLT_FALL_GRAVITY))[1]
    holders = (state.meta_extensions.get("solve") or {}).get("holds", {}).get("holders", {})
    named = {a.id: a for a, _t, _w in topples if a.id}
    bodies = [a.body for a, _t, _w in topples]
    for a, _t, where in topples:
        if bodies.count(a.body) > 1 and not a.id:
            raise ToppleError(f"{where}: {a.body!r} topples more than once: give each topple an `id:`")
    for a, _t, where in topples:
        if a.after is not None and a.after not in named:
            raise ToppleError(
                f"{where}: `after: {a.after}` names no topple of this shot (their ids: {sorted(named)})"
            )
    pose_cache: dict[float, Any] = {}

    def pose(t: float) -> Any:
        if t not in pose_cache:
            pose_cache[t] = evaluate_timeline(timeline, t)
        return pose_cache[t]

    def carried(body: str, t: float) -> list[str]:
        """The items a part of ``body`` holds at ``t`` (per the hold report)."""
        out = []
        for item, timeline_ in holders.items():
            current = None
            for at, holder in timeline_:
                if at <= t + 1e-9:
                    current = holder
            if current and (current == body or current.startswith((body + "/", body + "@"))):
                out.append(item)
        return out

    report: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    plans: dict[str, dict[str, Any]] = {}  # topple id or body -> its fall
    order = sorted(topples, key=lambda x: (x[0].after is not None, x[1]))
    pending = list(order)
    while pending:
        progressed = False
        for entry in list(pending):
            a, t_start, where = entry
            if a.after is not None:
                knocker = plans.get(a.after)
                if knocker is None:
                    continue
                hit = knocker["hits"].get(a.body)
                if hit is None:
                    raise ToppleError(
                        f"{where}: {a.after!r}'s {knocker['body']!r} never touches "
                        f"{a.body!r} as it falls (it comes within {knocker['near'].get(a.body, float('nan')):.0f} px): "
                        f"move {a.body!r} into its path, or start it with `start:` and a `push`"
                    )
                t_start, omega = hit["at"], a.knock * hit["speed"]
            else:
                omega = a.push
            sign = 1.0 if a.toward == "right" else -1.0
            omega = sign * abs(omega)
            p0 = pose(t_start)
            items = carried(a.body, t_start)
            for item in items:
                later = [at for at, _h in holders.get(item, ()) if at > t_start + 1e-6]
                if later:
                    raise ToppleError(
                        f"{where}: {item!r} is held by {a.body!r} when it topples at "
                        f"{t_start:.2f} s, and its holder changes again at {later[0]:.2f} s: "
                        "the hold layer does not see the topple yet, so an item a toppled "
                        "body holds stays with it to the end of the shot (move the later "
                        "gesture before the topple, or into the next shot)"
                    )
            pts = _ink(doc, state.mall, a.body, p0)
            for item in items:
                pts.extend(_ink(doc, state.mall, item, p0))
            if not pts:
                raise ToppleError(f"{where}: {a.body!r} draws nothing to topple")
            hull = _hull(pts)
            com = _centroid(hull)
            low = max(p[1] for p in hull)
            feet = [p for p in hull if p[1] >= low - FOOT_BAND_PX]
            pivot = max(feet, key=lambda p: sign * p[0])
            # It falls onto the floor it stands on (in a 2.5D set, the line of its own feet).
            floor = low
            i_cm = inertia([(p[0] - com[0], p[1] - com[1]) for p in hull])
            r = (com[0] - pivot[0], com[1] - pivot[1])
            if sign * r[0] < 0:
                # Its centre is inside its feet: it tips over only if it turns
                # far enough to bring the centre over the foot.
                rise = math.hypot(*r) + r[1]  # how far the centre must rise (r[1] < 0: above)
                need = math.sqrt(2.0 * g * rise / (i_cm + r[0] ** 2 + r[1] ** 2))
                if abs(omega) < need * 1.02:
                    how = (
                        f"`knock:` at least {a.knock * need * 1.05 / max(1e-9, abs(omega)):.2f}"
                        if a.after is not None
                        else f"`push:` at least {need * 1.05:.2f}"
                    )
                    raise ToppleError(
                        f"{where}: {a.body!r} rocks back onto its feet: it starts at "
                        f"{abs(omega):.2f} rad/s, and tipping over its {a.toward} foot takes "
                        f"{need:.2f} (its centre is {abs(r[0]):.0f} px inside that foot). Give it {how}"
                    )
            # The points that can come down onto the floor: not the feet it stands on.
            others = [p for p in hull if floor - p[1] > FOOT_BAND_PX]
            pin = None
            if a.until is not None:
                if a.point is None:
                    raise ToppleError(f"{where}: `until` needs the `point` of the body that reaches it")
                q = _point(doc, a.point, p0, where=where)
                target = _point(doc, a.until, p0, where=where)
                r_q = math.hypot(q[0] - pivot[0], q[1] - pivot[1])
                r_t = math.hypot(target[0] - pivot[0], target[1] - pivot[1])
                if abs(r_q - r_t) > PIN_TOLERANCE_PX:
                    dy = target[1] - pivot[1]
                    if r_q < abs(dy):
                        raise ToppleError(
                            f"{where}: {a.point!r} sweeps a circle of radius {r_q:.0f} px about "
                            f"{a.body!r}'s foot, and {a.until!r} is {abs(dy):.0f} px "
                            f"{'above' if dy < 0 else 'below'} that foot: it can never reach it. "
                            "Lower the target, or topple a taller body"
                        )
                    root = math.sqrt(r_q * r_q - dy * dy)
                    shifts = [target[0] - pivot[0] - root, target[0] - pivot[0] + root]
                    dx = min(shifts, key=abs)
                    raise ToppleError(
                        f"{where}: {a.point!r} passes {abs(r_q - r_t):.0f} px "
                        f"{'short of' if r_q < r_t else 'beyond'} {a.until!r} as {a.body!r} falls "
                        f"(it sweeps {r_q:.0f} px about its foot, the target is {r_t:.0f} px away). "
                        f"Move {a.body!r} about {abs(dx):.0f} px to the {'right' if dx > 0 else 'left'}"
                    )
                want = math.atan2(target[1] - pivot[1], target[0] - pivot[0]) - math.atan2(
                    q[1] - pivot[1], q[0] - pivot[0]
                )
                want = math.remainder(want, 2 * math.pi)
                if want * sign <= 0:
                    raise ToppleError(
                        f"{where}: {a.until!r} is behind {a.point!r} for a fall to the "
                        f"{a.toward}: topple `toward: {'left' if sign > 0 else 'right'}`"
                    )
                pin = (want, target)

            def floor_gap(angle: float, others=others, pivot=pivot, floor=floor) -> float:
                return min(floor - _rot_about(p, pivot, angle)[1] for p in others) if others else 1.0

            def stop(angle: float, pin=pin) -> float:
                gap = floor_gap(angle)
                if pin is not None:
                    gap = min(gap, sign * (pin[0] - angle))
                return gap

            fall = pivot_fall(com, pivot, gravity=g, omega=omega, inertia_cm=i_cm, stop=stop)
            segments = [(t_start, fall, 0.0)]
            end_t = t_start + fall.duration
            end_angle = fall.turn(fall.duration)
            pinned = pin is not None and abs(end_angle - pin[0]) < 1e-3
            kind = "pin" if pinned else "land"
            events.append({"event": "topple", "item": a.body, "at": round(t_start, 4)})
            events.append({"event": kind, "item": a.body, "at": round(end_t, 4)})
            bounces = []
            if not pinned and fall.stopped:
                e = DFLT_BOUNCE if a.bounce is None else a.bounce
                w = -e * fall.omega_end
                com_end = _rot_about(com, pivot, end_angle)
                for _ in range(MAX_BOUNCES):
                    # Its far end bounces up about the foot and falls back.
                    rock = pivot_fall(
                        com_end, pivot, gravity=g, omega=w, inertia_cm=i_cm,
                        stop=lambda ang: 1e-9 - sign * ang,
                    )
                    if not rock.stopped or max(abs(x) for x in rock.turns) < MIN_ROCK:
                        break
                    segments.append((end_t, rock, end_angle))
                    end_t += rock.duration
                    bounces.append(end_t)
                    w = -e * rock.omega_end
            for b in bounces:
                events.append({"event": "bounce", "item": a.body, "at": round(b, 4)})
            events.append({"event": "rest", "item": a.body, "at": round(end_t, 4)})

            def angle_at(t: float, segments=segments, final=end_angle) -> float:
                if t <= segments[0][0]:
                    return 0.0
                for start, f, base in segments:
                    if t <= start + f.duration:
                        return base + f.turn(t - start)
                return final

            # Who it touches on the way down (for the topples it knocks).
            hits: dict[str, dict[str, float]] = {}
            near: dict[str, float] = {}
            victims = [b.body for b, _t, _w in topples if b.after == (a.id or "")]
            if victims:
                steps = max(2, int(fall.duration * CONTACT_HZ))
                for body in victims:
                    other = _hull(_ink(doc, state.mall, body, p0))
                    for n in range(1, steps + 1):
                        u = fall.duration * n / steps
                        ang = fall.turn(u)
                        moved = [_rot_about(p, pivot, ang) for p in hull]
                        c = _touch(moved, other)
                        near[body] = min(
                            near.get(body, math.inf),
                            min(math.hypot(p[0] - o[0], p[1] - o[1]) for p in moved for o in other),
                        )
                        if c is not None:
                            du = fall.duration / steps
                            w_now = (ang - fall.turn(max(0.0, u - du))) / du
                            speed = abs(w_now) * math.hypot(c[0] - pivot[0], c[1] - pivot[1])
                            # Its own turn rate: the knocker's tip speed over the struck body's height.
                            height = max(1.0, max(p[1] for p in other) - min(p[1] for p in other))
                            hits[body] = {"at": t_start + u, "speed": speed / height}
                            events.append(
                                {"event": "hit", "item": a.body, "at": round(t_start + u, 4), "on": body}
                            )
                            break
            plans[a.id or a.body] = {"body": a.body, "hits": hits, "near": near}
            # The keys: the entity and what it carries, turned about the pivot.
            from an.stage.serialize import (
                AnimationClipJSON,
                ChannelJSON,
                KeyframeJSON,
                PlacedClipJSON,
                TrackJSON,
            )

            channels = []
            for path in [a.body, *items]:
                parent = path.rsplit("/", 1)[0] if "/" in path else None
                values: dict[str, list[tuple[float, float]]] = {
                    p: [] for p in ("x", "y", "rotation", "scale_x", "scale_y")
                }
                node = next(n for p, n in _nodes_under(doc, path.split("/", 1)[0]) if p == path)
                piv = (node.transform.pivot_x or 0.0, node.transform.pivot_y or 0.0) if node.transform else (0.0, 0.0)
                prev_rot = None
                # A key at its start (the pose it has then), then one per frame.
                for tk in [t_start, *(t for t in times if t > t_start + 1e-6)]:
                    ang = angle_at(tk)
                    c, s = math.cos(ang), math.sin(ang)
                    d = (c, s, -s, c, pivot[0] - c * pivot[0] + s * pivot[1], pivot[1] - s * pivot[0] - c * pivot[1])
                    world = _compose(d, _affine(doc, path, pose(tk)))
                    par = _affine(doc, parent, pose(tk)) if parent else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
                    local = _compose(_invert(par), world)
                    theta, sx, sy, mirrored = _decompose(local)
                    if prev_rot is not None:
                        theta = prev_rot + math.remainder(theta - prev_rot, 2 * math.pi)
                    prev_rot = theta
                    x = local[0] * piv[0] + local[2] * piv[1] + local[4]
                    y = local[1] * piv[0] + local[3] * piv[1] + local[5]
                    for prop, v in (
                        ("x", x), ("y", y), ("rotation", theta),
                        ("scale_x", -sx if mirrored else sx), ("scale_y", sy),
                    ):
                        values[prop].append((tk - t_start, v))
                for prop, keys in values.items():
                    if keys:
                        channels.append(
                            ChannelJSON(
                                target=path,
                                property=prop,
                                keyframes=[KeyframeJSON(time=t, value=v, easing="linear") for t, v in keys],
                            )
                        )
            name = f"{TOPPLE_CLIP_PREFIX}{a.id or a.body}"
            # Placed from its start: before it, the body and what it carries move as they did.
            duration = max(0.001, float(shot.duration) - t_start)
            state.animations[name] = AnimationClipJSON(name=name, duration=duration, channels=channels)
            for root in sorted({p.split("/", 1)[0] for p in [a.body, *items]}):
                placed = PlacedClipJSON(animation_id=name, start_time=t_start, duration=duration)
                track = next((tr for tr in state.tracks if tr.target_root == root), None)
                if track is None:
                    state.tracks.append(TrackJSON(target_root=root, clips=[placed]))
                else:
                    track.clips.append(placed)
            report.append(
                {
                    "body": a.body,
                    "where": where,
                    "start": round(t_start, 4),
                    "pivot": [round(pivot[0], 2), round(pivot[1], 2)],
                    "angle": round(math.degrees(end_angle), 2),
                    "ends": kind,
                    "carries": items,
                    **({"after": a.after} if a.after else {}),
                }
            )
            pending.remove(entry)
            progressed = True
        if not progressed:
            stuck = ", ".join(f"{a.body} (after {a.after})" for a, _t, _w in pending)
            raise ToppleError(f"topples that wait on each other and never start: {stuck}")
    state.meta_extensions[TOPPLE_EXTENSION] = {
        "topples": report,
        "events": sorted(events, key=lambda e: e["at"]),
    }
