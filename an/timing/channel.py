"""Channel: keyframes for a single (target, property) pair, evaluated at time t.

A channel holds a sorted list of `Keyframe`s. ``evaluate(channel, t)`` does a
binary search to find the surrounding keyframes, applies the easing for that
segment, and interpolates between the two values. Keys are half-open: the
segment ``[a.time, b.time)`` belongs to ``a``; before the first key the first
value holds, from the last key on the last value holds; a zero-span segment
(two keys at one time) resolves to the later key.

**Who picks the interpolator.** Two rules, one per caller:

- ``kind=None`` — **by value type**, the rule ``runtime.js``'s
  ``evaluateChannel`` implements, and the default because this function is that
  port's executable spec (``tests/test_cutout_channel_parity.py`` runs the real
  extracted JS against it). Numbers (``int``/``float``, excluding ``bool``)
  interpolate through the segment's easing; everything else holds ``a`` for
  exactly ``[a.time, b.time)`` and switches at ``b.time``. Being runtime.js's
  rule, it accepts only runtime.js's easings
  (:data:`~an.timing.easing.VALUE_TYPED_EASINGS`): a curve the stage cannot
  draw raises here, as it does in the browser, instead of yielding a pose.
- ``kind=<FieldKind>`` — **by declaration** (:mod:`an.timing.kinds`), the
  kernel contract's rule: the declared kind interpolates, a discrete kind
  switches on time, and the first instant of a segment is the key it leaves.
  The stage's declarations (``stage.node``) give the same values as the
  value-type rule on everything the stage compiler emits; a test holds that.

In both, the snap of a held value compares ``t`` against a TIME, never an eased
or derived parameter, because each indirection was measured wrong: an
overshooting cubic-bezier easing crosses 1.0 mid-segment (showing the *second*
key early, or flapping A→B→A within one segment), and even the raw
``(t - a.time) / span`` can round up to 1.0 while ``t < b.time``. And in both,
the easing is *validated* on every segment (an unknown spec raises) so a typo'd
easing name stays loud on a swap channel too.

``bool`` keyframe values are refused upstream by the stage compiler: Python's
``isinstance(True, int)`` would lerp what JS's ``typeof`` snaps.

>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> evaluate(ch, 0.5)
5.0
>>> evaluate(ch, -1.0)  # before first → clamps to first value
0.0
>>> evaluate(ch, 99.0)  # after last → clamps to last value
10.0
>>> sw = Channel("a", "hands", [Keyframe(0.0, "fist"), Keyframe(1.0, "open")])
>>> evaluate(sw, 0.999)  # holds the first key for the whole segment
'fist'
>>> evaluate(sw, 1.0)  # switches exactly at the keyframe
'open'
>>> from an.timing.kinds import AngleKind
>>> spin = Channel("a", "yaw", [Keyframe(0.0, 350.0), Keyframe(1.0, 10.0)])
>>> evaluate(spin, 0.5), evaluate(spin, 0.5, kind=AngleKind())
(180.0, 360.0)
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Any

from an.base import EasingSpec
from an.timing.easing import VALUE_TYPED_EASINGS, apply_easing
from an.timing.kinds import FieldKind, FieldKindError, Segment


@dataclass(slots=True, frozen=True)
class Keyframe:
    """One keyframe: time, value, optional per-segment easing.

    The easing on a keyframe describes the curve **leaving** that keyframe
    toward the next one. The last keyframe's easing is therefore unused.
    """

    time: float
    value: Any
    easing: EasingSpec | None = None


@dataclass(slots=True)
class Channel:
    """Sorted keyframes for one property of one target.

    Construction validates that ``keyframes`` is non-empty and sorted.
    """

    target: str
    property: str
    keyframes: list[Keyframe] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.keyframes:
            raise ValueError(
                f"Channel({self.target!r}, {self.property!r}) requires at least one keyframe"
            )
        # Validate sorted order; cheap and avoids subtle eval bugs.
        prev_t = -float("inf")
        for kf in self.keyframes:
            if kf.time < prev_t:
                raise ValueError(
                    f"Channel({self.target!r}, {self.property!r}) keyframes must be "
                    f"sorted by time; got {kf.time} after {prev_t}"
                )
            prev_t = kf.time


def evaluate(channel: Channel, t: float, *, kind: FieldKind | None = None) -> Any:
    """Evaluate ``channel`` at time ``t`` (see the module docstring for ``kind``)."""
    kfs = channel.keyframes
    if len(kfs) == 1:
        return kfs[0].value
    times = [kf.time for kf in kfs]
    if t >= times[-1]:
        return kfs[-1].value
    if t < times[0]:
        return kfs[0].value
    # Binary search: find rightmost index i such that times[i] <= t.
    i = bisect.bisect_right(times, t) - 1
    a = kfs[i]
    b = kfs[i + 1]
    span = b.time - a.time
    if span <= 0.0:
        return b.value
    u = (t - a.time) / span
    # Validated for every segment (a typo'd easing name must raise on a swap
    # channel too), but *applied* only where the interpolator uses it.
    eased = apply_easing(
        a.easing, u, names=VALUE_TYPED_EASINGS if kind is None else None
    )
    if kind is not None:
        if t == a.time:  # the first instant of a segment is the key it leaves
            return a.value
        try:
            return kind.interpolate(a.value, b.value, eased, Segment(t, a.time, b.time))
        except (TypeError, ArithmeticError) as e:
            raise FieldKindError(
                f"{channel.target}:{channel.property}: cannot interpolate "
                f"{a.value!r} -> {b.value!r} as {kind.to_spec()} at t={t} ({e})"
            ) from e
    if _is_numeric(a.value) and _is_numeric(b.value):
        return a.value + (b.value - a.value) * eased
    # Non-numeric: snap on TIME, never on the (eased or raw) parameter. The
    # value is `a` for exactly [a.time, b.time) — comparing `u >= 1.0` here
    # would be one float-division away from wrong: (t - a.time) / span can
    # round UP to 1.0 while t < b.time, showing `b` one representable float
    # early (found by the an#86 adversarial review). The time comparison has
    # no intermediate arithmetic, so the boundary is exact.
    return b.value if t >= b.time else a.value


def check_channel(channel: Channel, kind: FieldKind) -> list[str]:
    """Why ``channel``'s keyframe values do not fit ``kind`` (empty if they do)."""
    problems = []
    for k in channel.keyframes:
        problem = kind.check(k.value)
        if problem:
            problems.append(
                f"{channel.target}:{channel.property} at t={k.time} ({kind.name}): {problem}"
            )
    return problems


def _is_numeric(v: Any) -> bool:
    """True for values that interpolate. ``bool`` deliberately does not:
    Python's ``bool ⊂ int`` would lerp what JS's ``typeof`` snaps."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)
