"""The visible events a compiled shot records, by name: what a sound cue's ``event`` may say (an#804).

One vocabulary for every source: the hold layer (:mod:`an.stage.hold`) and the
``topple`` pass (:mod:`an.stage.topple`) emit these names into their reports'
``events`` lists, :class:`an.ir.schema.CueAnchor` validates an ``event`` against
them, and :mod:`an.sound_anchors` resolves one.

>>> sorted(EVENTS)[:3], ALIASES["contact"]
(['bounce', 'grasp', 'hit'], ('grasp', 'place'))
"""

from __future__ import annotations

__all__ = ["ALIASES", "EVENTS", "event_names"]

#: Each event an item or a body can have, and what it means.
EVENTS: dict[str, str] = {
    "grasp": "a hand takes the item (a swap's take included)",
    "place": "the item arrives where it is put (a swap's give included)",
    "release": "the item is let go",
    "land": "it first touches its floor (a dropped item, a toppled body)",
    "bounce": "a bounce or a rock comes back down",
    "rest": "it stops moving",
    "topple": "a body starts to fall over",
    "hit": "a falling body first touches another (the report names it: `on`)",
    "pin": "a toppled body's point reaches its target and stays",
}
#: Names that stand for several events.
ALIASES: dict[str, tuple[str, ...]] = {"contact": ("grasp", "place")}


def event_names() -> str:
    """Every name an ``event`` may say, for a message.

    >>> event_names().startswith("grasp, place, release")
    True
    """
    return ", ".join([*EVENTS, *ALIASES])
