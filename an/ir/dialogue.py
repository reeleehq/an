"""Where each dialogue line of a shot will play (an#767): the layout ``an validate`` and the genres' checks share.

:func:`dialogue_layout` is the audio pipeline's own rule
(:meth:`an.ir.schema.Dialogue.planned_start`: a line's ``at``, else back to back
after the previous line plus its ``pause``) over each line's real duration when
it was synthesized, else the offline voice's estimate. A check that judges a
line by when it plays (a speaker's eyeline, a line run past its shot, two lines
in one mouth) reads it here, never the stamped ``start``, which a pause edited
since the last synthesis has made stale.

>>> from an.ir.schema import Dialogue, Shot
>>> shot = Shot(id="s", duration=9.0, dialogue=[
...     Dialogue(speaker="a", text="hi", duration=1.0),
...     Dialogue(speaker="b", text="bye", duration=0.5, pause=0.25),
... ])
>>> [(p.k, p.start, p.end, p.estimated) for p in dialogue_layout(shot)]
[(0, 0.0, 1.0, False), (1, 1.25, 1.75, False)]
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, NamedTuple

__all__ = ["LinePlacement", "dialogue_layout"]


class LinePlacement(NamedTuple):
    """One line of a shot and where it plays (shot-local seconds).

    A tuple, so ``for k, line, start, end, estimated in dialogue_layout(shot)``
    reads it as the private layout it replaces did.
    """

    #: The line's index in ``shot.dialogue``.
    k: int
    line: Any
    start: float
    end: float
    #: Whether ``end`` comes from the offline estimate (the line has no audio yet).
    estimated: bool


def dialogue_layout(
    shot: Any, *, tempo_of: Callable[[Any], float] | None = None
) -> Iterator[LinePlacement]:
    """A :class:`LinePlacement` for each dialogue line of ``shot``, in order.

    A line synthesized plays for its ``duration``; one not yet synthesized for
    the offline voice's estimate (:func:`an.audio.offline_tts.estimate_speech_duration`)
    divided by its voice's ``tempo``, ``tempo_of(line)`` (an#265: the effect
    applies under every provider; default 1).
    """
    from an.audio.offline_tts import estimate_speech_duration

    cursor = 0.0
    for k, line in enumerate(shot.dialogue):
        estimated = line.duration is None
        length = (
            estimate_speech_duration(line.text) / (tempo_of(line) if tempo_of else 1.0)
            if estimated
            else float(line.duration)
        )
        start = line.planned_start(cursor)
        cursor = start + length
        yield LinePlacement(k, line, start, cursor, estimated)
