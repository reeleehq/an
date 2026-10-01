"""Channel evaluation — moved to :mod:`an.timing.channel` (the timing kernel).

This path keeps working for every existing caller; new code imports from
``an.timing``. **This module's names are the executable spec of
``runtime.js``'s ``evaluateChannel``** (with the default ``kind=None``: by value
type), pinned by ``tests/test_cutout_channel_parity.py``.

>>> ch = Channel("a", "x", [Keyframe(0.0, 0.0), Keyframe(1.0, 10.0)])
>>> evaluate(ch, 0.5)
5.0
"""

from __future__ import annotations

from an.timing.channel import Channel, Keyframe, _is_numeric, check_channel, evaluate

__all__ = ["Channel", "Keyframe", "evaluate", "check_channel", "_is_numeric"]
