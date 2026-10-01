"""The cut-out animation genre, declared as one object (still inside ``an``).

ADR 0001 §First slice: the cut-out genre's IR extensions register through the
same door any genre uses — the ``an.genres`` entry point (``pyproject.toml``
declares ``cutout_animation = "an.genres.cutout:CUTOUT"``) — instead of being
wired into the core. :data:`CUTOUT` lists:

- **action kinds** ``play`` (:mod:`an.characters.registration`) and
  ``expression`` (:mod:`an.expression.registration`);
- **entity kind** ``character``, whose nodes are stage nodes (``stage.node``);
- the **``[emotion]``** dialogue sugar;
- its **semantic checks**: ``play`` and ``expression`` resolution, brow
  acting on a character whose brows cannot act (an#252), the turn
  checks (contradicted ``from_direction``, a mouth hidden while speaking) and
  view continuity across a cut, placed in the report where they always were;
- its **capabilities** and the **character analyser** (ADR 0002:
  :mod:`an.library.character`), its **vocabulary** (motion and expression
  presets, IR-field notes: :mod:`an.characters.vocabulary`; the methods:
  :mod:`an.characters.methods`) and its **aspects**, ``locomotion``,
  ``speech`` and ``expression``, each with a default chain that ends in a
  method requiring nothing.

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

from an.characters.methods import (
    CUTOUT_ASPECTS,
    CUTOUT_METHODS,
    check_brow_acting,
    check_declared_speech,
)
from an.characters.registration import CHARACTER, PLAY
from an.characters.vocabulary import CUTOUT_VOCABULARY
from an.expression.registration import EMOTION, EXPRESSION
from an.genres import CompilePass, Genre, SemanticCheck
from an.ir import validate as _validate
from an.library.character import CHARACTER_ANALYSER, CHARACTER_CAPABILITIES

#: The genre's persisted slug (also :data:`an.genre.CUTOUT_ANIMATION_SLUG`).
CUTOUT_GENRE_NAME: str = "cutout_animation"

#: The cut-out passes over the STAGE's compiler (an#247; ADR 0001 decision 4),
#: between the stage's own (`an.stage.compile.STAGE_COMPILE_PASSES`: scene 100,
#: actions 200, camera 600, parallax 700, checks 900), and the ``rig``: the
#: builder of a ``character``'s subtree inside the scene pass. Named by
#: ``"module:function"`` so this declaration imports no engine; the bodies still
#: live in `an.stage.compile` until `cutan` (an#225) takes them.
CUTOUT_COMPILE_PASSES: tuple[CompilePass, ...] = (
    CompilePass("speech", "an.stage.compile:_speech_pass", order=150,
                description="the speech aspect: pulses for speakers that do not lip-sync"),
    CompilePass("swap_pose", "an.stage.compile:_swap_pose_pass", order=300,
                description="what whole-character swaps pose"),
    CompilePass("view_spans", "an.stage.compile:_view_span_pass", order=310,
                description="which view each character is in, when"),
    CompilePass("visemes", "an.stage.compile:_viseme_pass", order=400,
                description="lip-sync: a viseme channel per dialogue line"),
    CompilePass("face", "an.stage.compile:_face_pass", order=500,
                description="blinks, expressions, gaze, the silent mouth"),
    CompilePass("rig", "an.stage.compile:_build_character_entity", order=1,
                builds="character", description="a character's rig and art"),
)

CUTOUT = Genre(
    CUTOUT_GENRE_NAME,
    title="Animation (cut-out)",
    description=(
        "2D cut-out animation: rigged characters (skeletons of bones with "
        "slots), replacement animation, expressions, lip-sync and turnarounds, "
        "drawn by the stage engine"
    ),
    package="an",
    # Its assets and projects live under the cut-out genre's own data root
    # (`~/.local/share/cutan`, plan §1 decision 7), whatever ships the code.
    library="cutan",
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
            "cutout.brow_acting",
            check_brow_acting,
            order=41.5,
            description=(
                "an expression that moves the brows targets a character whose "
                "brows can act (else it reads through the lids and mouth only)"
            ),
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
            "cutout.declared_speech",
            check_declared_speech,
            order=100.6,
            description="a character's declared `speech` names a speech method at a current version",
        ),
        SemanticCheck(
            "cutout.character_refs",
            _validate.check_character_refs,
            order=100.5,
            description="a character ref missing from the store draws the placeholder rig",
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
    capabilities=CHARACTER_CAPABILITIES,
    analysers=(CHARACTER_ANALYSER,),
    vocabulary=(*CUTOUT_VOCABULARY, *CUTOUT_METHODS),
    aspects=CUTOUT_ASPECTS,
    compile_passes=CUTOUT_COMPILE_PASSES,
)

__all__ = ["CUTOUT", "CUTOUT_GENRE_NAME"]
