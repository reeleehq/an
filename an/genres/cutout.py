"""The cut-out animation genre, declared as one object (still inside ``an``).

ADR 0001 §First slice: the cut-out genre's IR extensions register through the
same door any genre uses — the ``an.genres`` entry point (``pyproject.toml``
declares ``cutout_animation = "an.genres.cutout:CUTOUT"``) — instead of being
wired into the core. :data:`CUTOUT` lists:

- **action kinds** ``play`` (:mod:`an.characters.registration`) and
  ``expression`` (:mod:`an.expression.registration`);
- **entity kind** ``character``, whose nodes are stage nodes (``stage.node``);
- the **``[emotion]``** dialogue sugar;
- its **semantic checks**: ``play`` and ``expression`` resolution, the turn
  checks (contradicted ``from_direction``, a mouth hidden while speaking) and
  view continuity across a cut, placed in the report where they always were.

Its ``name`` is the persisted genre slug ``cutout_animation``, the one
:mod:`an.genre` declares to ``nw`` (ADR 0001 decision 9: persisted
identifiers do not change). When the ``cutan`` package exists (P8), this object
moves there and registers through the same entry point from that distribution;
nothing in the core's dispatch changes.

Importing this module registers nothing: :func:`an.genres.load` (or
:func:`an.genres.register_genre`) does.

>>> CUTOUT.provides()["action kinds"]
('play', 'expression')
"""

from __future__ import annotations

from an.characters.registration import CHARACTER, PLAY
from an.expression.registration import EMOTION, EXPRESSION
from an.genres import Genre, SemanticCheck
from an.ir import validate as _validate

#: The genre's persisted slug (also :data:`an.genre.CUTOUT_ANIMATION_SLUG`).
CUTOUT_GENRE_NAME: str = "cutout_animation"

CUTOUT = Genre(
    CUTOUT_GENRE_NAME,
    title="Animation (cut-out)",
    description=(
        "2D cut-out animation: rigged characters (skeletons of bones with "
        "slots), replacement animation, expressions, lip-sync and turnarounds, "
        "drawn by the stage engine"
    ),
    package="an",
    action_kinds=(PLAY, EXPRESSION),
    entity_kinds=(CHARACTER,),
    checks=(
        SemanticCheck(
            "cutout.play",
            _validate.check_play_actions,
            order=40,
            description="a `play` resolves against its target's animations or a motion preset",
        ),
        SemanticCheck(
            "cutout.expression",
            _validate.check_expression_actions,
            order=41,
            description="an `expression` and a dialogue `[emotion]` resolve",
        ),
        SemanticCheck(
            "cutout.turns",
            _validate.check_turns,
            order=60,
            description="a `turn`'s declared from_direction agrees with the timeline",
        ),
        SemanticCheck(
            "cutout.hidden_mouth_while_speaking",
            _validate.check_hidden_mouth_while_speaking,
            order=61,
            description="no line is spoken while the speaker's view hides its mouth",
        ),
        SemanticCheck(
            "cutout.view_continuity",
            _validate.check_view_continuity,
            stage="finish",
            order=10,
            description="a view does not silently reset across a cut",
        ),
    ),
    dialogue_sugar=(EMOTION,),
)

__all__ = ["CUTOUT", "CUTOUT_GENRE_NAME"]
