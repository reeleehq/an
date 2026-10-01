"""Clips, loop modes and poses — moved to :mod:`an.timing.clip` (the timing kernel).

This path keeps working for every existing caller; new code imports from
``an.timing``.

>>> from an.adapters.cutout.channel import Channel, Keyframe
>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> clip = Clip("walk", duration=1.0, channels=[ch], loop_mode=LoopMode.LOOP)
>>> evaluate(clip, 1.25)[("a", "x")]  # loop wraps
2.5
"""

from __future__ import annotations

from an.timing.clip import Clip, LoopMode, Pose, _wrap_time, evaluate, merge_poses

__all__ = ["Clip", "LoopMode", "Pose", "evaluate", "merge_poses", "_wrap_time"]
