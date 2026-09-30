"""Pydantic v2 models for the Scene IR.

Design principles (locked in from the architectural plan):

- **Renderer-agnostic.** No cutout-specific or Manim-specific fields here. Backend
  adapters compile shots into their own internal formats. This module only knows
  what every shot has in common.
- **Versioned envelope.** Every IR document carries `version` and
  `compatible_version`. Migrations live in `an.ir.migrate`.
- **Forward-compatible reads.** Top-level model has ``extra="allow"`` so a future
  field doesn't crash an older reader.
- **Discriminated `Action` union.** All authoring-time and flattened actions
  carry a `kind` literal so Pydantic dispatches to the right validator.
- **Time in seconds (float).** Always.

Doctest:

>>> from an.ir.schema import SceneIR, Meta, Shot
>>> scene = SceneIR(
...     meta=Meta(title="Park Bench", duration=45.0),
...     timeline=[Shot(id="s1", renderer="cutout", duration=45.0)],
... )
>>> from an.base import SCHEMA_VERSION
>>> scene.version == SCHEMA_VERSION
True
>>> scene.kind
'SceneIR'
>>> scene.timeline[0].renderer
'cutout'
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Union

from pydantic import model_serializer, BaseModel, ConfigDict, Field, model_validator

from an.base import (
    COMPATIBLE_VERSION,
    DEFAULT_DURATION,
    DEFAULT_FPS,
    DEFAULT_RESOLUTION,
    DEFAULT_DUCK_ATTACK_S,
    DEFAULT_DUCK_RELEASE_S,
    DEFAULT_TRANSITION_COLOR,
    DEFAULT_TRANSITION_DURATION,
    SCHEMA_VERSION,
    EasingSpec,
    PathStr,
    Seconds,
    RendererName,
)


# -----------------------------------------------------------------------------
# Inbound-friendly base: forward-compat reads, strict-ish writes.
# -----------------------------------------------------------------------------


class _IRModel(BaseModel):
    """Common config: allow unknown fields on read so newer documents survive."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# -----------------------------------------------------------------------------
# Leaf / value types
# -----------------------------------------------------------------------------


class Resolution(_IRModel):
    """Pixel dimensions of the rendered output."""

    width: int = DEFAULT_RESOLUTION[0]
    height: int = DEFAULT_RESOLUTION[1]


class CameraKey(_IRModel):
    """One camera pose at one time — the explicit door behind the named moves.

    >>> CameraKey(at=1.0, x=-160.0, zoom=1.25).x
    -160.0

    **Sign convention**, stated because every surveyed tool disagrees: `+x`
    moves the CAMERA right, which moves the content left. `zoom` is on-screen
    magnification, so `1.25` means "everything 25% bigger", and it composes
    through the pivot — a push-in during a pan zooms toward what the camera is
    looking at rather than toward a fixed frame centre. `rotation` is camera
    roll in radians.

    `easing` defaults to **`None`, not `"ease_in_out"`**, and that is not a
    style choice: today's emitter puts `"ease_in_out"` on the first keyframe
    and `null` on the terminal one, so a per-key default of `"ease_in_out"`
    would put it on both and move every camera scene's contract hash. The
    named moves supply the easing they have always supplied.
    """

    at: Seconds = 0.0
    #: Camera position in scene pixels. `+x` moves the camera right.
    x: float = Field(default=0.0, allow_inf_nan=False)
    y: float = Field(default=0.0, allow_inf_nan=False)
    #: On-screen magnification. Must be > 0 — a zero or negative zoom is not a
    #: camera, and the compiler would emit a degenerate root scale.
    zoom: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    #: Camera roll, radians.
    rotation: float = Field(default=0.0, allow_inf_nan=False)
    easing: EasingSpec | None = None


class Camera(_IRModel):
    """Camera state for a shot: a named move, or explicit keys.

    >>> Camera(move="push_in").move
    'push_in'
    >>> Camera(keys=[CameraKey(at=0.0), CameraKey(at=2.0, x=-200.0)]).keys[1].x
    -200.0

    **One code path, two front doors** — the shape the dialogue `[emotion]`
    sugar already uses. A named `move` desugars to a key list; `keys` is that
    list written out. Setting both raises, because a scene that says two
    things about the same camera has no reading that is not a guess.

    `keys` defaults to `None`, not `[]`, and that too is load-bearing: the
    markdown writer dumps the camera with `exclude_none=True`, which KEEPS
    empty lists — an empty default would write `keys: []` into every camera
    block it regenerates.

    `position`, `target` and `focal_length` were removed in an#109. They were
    written into every `scene.md` this package ever generated and read by
    nothing; a registered migration drops them.
    """

    #: A named preset — sugar for `keys`. The cutout renderer's vocabulary is
    #: `an.adapters.cutout.compile.CAMERA_MOVES`; validate and the compiler are
    #: pinned to the same table by test, because a move that validates and then
    #: raises is the failure `_check_renderable` exists to prevent.
    move: str | None = None
    #: The explicit door. `None` = use `move`.
    keys: list[CameraKey] | None = None


# -----------------------------------------------------------------------------
# Asset references
# -----------------------------------------------------------------------------


class StagePlacement(_IRModel):
    """Where an entity stands on the stage, and how big it is.

    >>> StagePlacement(at=(120.0, -40.0), scale=0.5).at
    (120.0, -40.0)
    >>> StagePlacement().at is None
    True

    `at` is in SCENE pixels relative to the stage centre — the same space the
    compiler already places characters in — so an author reads it off the same
    ruler as a camera pivot. `scale` multiplies the rig's own uniform scale.

    **Deliberately only two fields, and the reason has been re-stated because
    the first one expired.** #108 sketched `depth` and `after` as well, deferred
    on the grounds that they belong to a stage vocabulary that had not arrived.
    It arrived the same day: #109 landed the translating camera and #110 landed
    plane environments, and nothing revisited this paragraph — a deferral citing
    a *condition* outlives the condition silently, which is why the reason below
    cites a state instead (an#126).

    The current reason is simply that **nothing reads them and nothing has asked
    to.** Shipping either now would put a knob in the schema that a scene can
    set, that renders identically, and that says nothing — which is worse than
    an absent one, and is the same defect `an.styles.UNREACHABLE_ROLES` refuses
    by construction on the other side of the compiler.

    What each would cost, so the next reader does not re-derive it:

    - `depth` would place a prop on a parallax plane, which means parenting the
      prop into that plane's subtree — and `_track_root_of` makes entity
      identity the first path segment, so every animation target on that prop
      changes shape.
    - `after` would order a prop against planes, which is `characters_after`'s
      problem a second time; that one needed the environment and character
      builders interleaved before any ordering could be expressed at all.

    Neither is hard. Both are unmotivated, and an unmotivated knob in a
    versioned schema is a migration you owe later for a feature nobody used.
    """

    #: ``(x, y)`` in scene pixels from the stage centre. ``None`` = default layout.
    #:
    #: `allow_inf_nan=False` on both fields, and it is not pedantry: pydantic
    #: serializes `inf` and `nan` to JSON **null**, and re-validating that JSON
    #: raises — so a scene file written with either is corrupt one way, and the
    #: author finds out on the next load rather than at the edit that did it
    #: (an#108 review, M-1). `gt=0` already refuses `scale=0` and `scale=-1`; it
    #: does not refuse `inf`.
    at: (
        tuple[
            Annotated[float, Field(allow_inf_nan=False)],
            Annotated[float, Field(allow_inf_nan=False)],
        ]
        | None
    ) = None
    #: Uniform scale multiplier on the built rig. ``1.0`` = the rig's own size.
    scale: float = Field(default=1.0, gt=0, allow_inf_nan=False)


class AssetRef(_IRModel):
    """Reference to an entry in a project store.

    The IR never inlines large assets. Instead it references them by store
    name + key, so the same character/voice/environment is reusable across
    scenes. ``overrides`` lets a single shot tweak presentation without
    forking the asset.

    >>> AssetRef(kind="character", id="maya", store="characters", ref="maya-v1").id
    'maya'
    """

    #: ``"style"`` was retired in an#106: it selected nothing (the compiler
    #: skipped it, nothing read the styles store) and the name belonged to the
    #: renderer selector. Art direction arrives as a StylePack (#112).
    kind: Literal["character", "environment", "voice", "prop"]
    id: str
    store: str  # which store in the project mall
    ref: str  # key inside that store
    overrides: dict[str, Any] | None = None

    #: Where on the stage this entity stands. ``None`` — the default and what
    #: every existing document has — means "wherever the layout puts it",
    #: which for characters is the evenly-spaced row the compiler computes.
    #:
    #: **Additive by construction, and hash-free by construction**: the
    #: contract hashes the COMPILED document, and an `AssetRef` never reaches
    #: it. So this field can grow without retiring a single ledger row.
    stage: StagePlacement | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_stage(self, handler):
        """Serialize ``stage: null`` out of existence when it is unset.

        The precedent is `serialize._omit_unset_step_hz`, and the reason is
        the same one scaled down: every committed `ir/scene.json` in this repo
        — corpus fixtures, examples, and whatever a user has on disk — was
        written before this field existed. A defaulted `null` on every
        `AssetRef` would rewrite all of them on the next `an sync`, and
        `test_every_speaking_corpus_scene_ir_is_reproducible_from_its_md`
        would be red until each was regenerated. A field nobody set should
        leave no trace (an#108).
        """
        data = handler(self)
        if self.stage is None:
            data.pop("stage", None)
        return data


# -----------------------------------------------------------------------------
# Action union — authoring atoms + composition nodes.
# All authoring DSL output, all flattened forms, all serialized actions are
# instances of this discriminated union.
# -----------------------------------------------------------------------------


class _ActionBase(_IRModel):
    """Common fields for all action variants."""

    # Name optional; helpful for editing/debugging but not required.
    name: str | None = None


class SetAction(_ActionBase):
    """Set a property to a value at a specific time. Discrete, no tween."""

    kind: Literal["set"] = "set"
    target: PathStr
    property: str
    value: Any
    at: Seconds = 0.0


class TweenAction(_ActionBase):
    """Animate a property from a start value to an end value over a duration."""

    kind: Literal["tween"] = "tween"
    target: PathStr
    property: str
    to_value: Any
    from_value: Any | None = None
    duration: Seconds = 1.0
    #: The curve. **Unset is not the same as ``"ease_in_out"``** (an#166): a
    #: tween that does not name an easing takes the scene's
    #: :attr:`Meta.default_easing`, and only when that is unset too the
    #: built-in ``"ease_in_out"`` this default spells. "Unset" is
    #: ``"easing" not in model_fields_set`` — the default stays the literal so
    #: every reader of ``.easing`` still sees the curve a scene without a
    #: default draws — and the serializer below omits an unset easing, so the
    #: distinction survives ``scene.json``. ``None`` is an explicit LINEAR
    #: ramp (the evaluators' reading of a null easing), not "unset".
    easing: EasingSpec | None = "ease_in_out"

    @model_serializer(mode="wrap")
    def _omit_unset_easing(self, handler):
        """Serialize an easing nobody wrote out of existence.

        Without this a JSON round trip would turn every unset easing into an
        explicit ``"ease_in_out"``, and the scene's ``default_easing`` would
        silently stop applying to it after the first ``an sync`` (an#166).
        """
        data = handler(self)
        if isinstance(data, dict) and "easing" not in self.model_fields_set:
            data.pop("easing", None)
        return data

    def resolved_easing(self, default: "EasingSpec | None" = None) -> Any:
        """The easing this tween draws with under a scene default of
        ``default`` — the ONE statement of the precedence **tween > scene
        (``Meta.default_easing``) > built-in ``"ease_in_out"``** (an#166).

        >>> TweenAction(target="a", property="x", to_value=1).resolved_easing("linear")
        'linear'
        >>> TweenAction(target="a", property="x", to_value=1, easing="ease_in_out").resolved_easing("linear")
        'ease_in_out'
        >>> TweenAction(target="a", property="x", to_value=1).resolved_easing(None)
        'ease_in_out'
        """
        if "easing" in self.model_fields_set or default is None:
            return self.easing
        return default


class PlayAction(_ActionBase):
    """Play a named animation of the target entity's descriptor (an#7).

    ``animation`` names an entry of ``CharacterDescriptor.animations`` (the
    seeded ``idle_breath`` and ``blink``, or anything an author adds); the
    compiler resolves its tracks into channels on the entity's nodes. A name
    the descriptor does NOT declare — or any name on an entity with no
    descriptor (a procedural rig, a prop) — falls back to the motion presets
    of :data:`an.motion.PRESETS` (``hop``, ``nod``, …), which expand to
    ordinary tweens at the target's built rest pose; a descriptor animation of
    the same name wins (an#166). Both halves are decided by
    :func:`an.characters.play.play_problems`, the one resolver ``an validate``
    and the compiler share. For a preset, ``args`` are its parameters,
    ``duration`` stretches the whole move to that length, ``speed`` divides
    it, and ``loop: true`` is refused (a preset is a one-shot).
    ``duration`` widens/narrows the placement window; ``None`` means the
    animation's own duration — or, when the resolved ``loop`` is true, the
    rest of the shot, because a loop bounded by its own natural duration
    never loops. ``loop`` overrides the animation's declared ``loop``
    (``None`` = use the descriptor's). Inside a ``sequence`` a play with
    ``duration=None`` occupies its NATURAL length — a motion preset's own
    length, a non-looping descriptor animation's ``duration``, both over
    ``speed`` — so the next sibling starts when it ends; a looping one runs to
    the shot end and occupies ZERO (:func:`an.characters.play.play_extent`).
    """

    kind: Literal["play"] = "play"
    target: PathStr
    animation: str  # a key of the entity descriptor's `animations`
    duration: Seconds | None = None  # None = the animation's natural duration
    speed: float = 1.0
    loop: bool | None = None  # None = the descriptor animation's own `loop`
    #: Parameters of a MOTION PRESET (an#166) — ``{"height": 30}`` for a
    #: ``hop`` — passed to its :data:`an.motion.PRESETS` function as keyword
    #: arguments. ``None`` (the default, omitted from JSON) means the preset's
    #: own defaults. A descriptor animation takes none, and one given to it is
    #: refused; ``rest`` is never one — it is read off the built scene.
    args: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_args(self, handler):
        """``args: null`` leaves no trace: every committed ``scene.json`` with
        a ``play`` predates the field (the an#112 omit-when-unset rule)."""
        data = handler(self)
        if isinstance(data, dict) and data.get("args") is None:
            data.pop("args", None)
        return data


#: Default ramp in/out of an expression, seconds (0 = cut). The dialogue
#: `[emotion]` sugar uses its own in `an.expression.provider`.
DFLT_EXPRESSION_BLEND_S: float = 0.15


class ExpressionAction(_ActionBase):
    """Hold a facial expression on an entity (an#98, epic #9 Wave 6).

    ``preset`` names one of :data:`an.expression.presets.PRESETS`; ``axes``
    are per-axis overrides layered on it (axis units, see
    :mod:`an.expression.axes`); ``None`` + no axes is a cheap "return to
    rest". ``duration=None`` runs to the shot end (the looping-play rule) and
    is **zero-width in a sequence**, like a looping ``play``. ``blend`` ramps the
    intensity in and out; two overlapping expressions cross-fade because the
    face solver sums offsets. The dialogue ``speaker [emotion]: …`` bracket is
    sugar for one of these over the line, desugared in memory only.

    A leaf action, flattened like ``play``: the compiler resolves it in the
    face solver (one channel per ``(node, property)``), never per action.

    The ramp is a min over the two ends, so a span shorter than ``2·blend``
    never reaches full intensity (a 0.2 s expression at the default 0.15 s
    blend peaks at 0.67) and a ``duration=0`` expression shows only where a
    frame lands on it with ``blend=0`` — cut the blend for a flash.
    """

    kind: Literal["expression"] = "expression"
    target: PathStr  # the ENTITY; the binding picks the nodes
    preset: str | None = None
    axes: dict[str, float] = Field(default_factory=dict)
    intensity: float = Field(default=1.0, ge=0.0, le=1.0)
    duration: Seconds | None = Field(default=None, ge=0.0)  # None = to the shot end
    blend: Seconds = Field(default=DFLT_EXPRESSION_BLEND_S, ge=0.0)


class SequenceAction(_ActionBase):
    """Composition: run children one after the other."""

    kind: Literal["sequence"] = "sequence"
    children: list["Action"] = Field(default_factory=list)


class ParallelAction(_ActionBase):
    """Composition: run all children simultaneously starting at the same time."""

    kind: Literal["parallel"] = "parallel"
    children: list["Action"] = Field(default_factory=list)


class DelayAction(_ActionBase):
    """Composition: an empty span that consumes time."""

    kind: Literal["delay"] = "delay"
    duration: Seconds


class LoopAction(_ActionBase):
    """Composition: repeat ``child`` ``count`` times."""

    kind: Literal["loop"] = "loop"
    child: "Action"
    count: int = 1


#: Discriminated union of every action variant. Pydantic dispatches on `kind`.
Action = Annotated[
    Union[
        SetAction,
        TweenAction,
        PlayAction,
        ExpressionAction,
        SequenceAction,
        ParallelAction,
        DelayAction,
        LoopAction,
    ],
    Field(discriminator="kind"),
]


# Resolve forward refs for self-referential composition nodes.
SequenceAction.model_rebuild()
ParallelAction.model_rebuild()
LoopAction.model_rebuild()


# -----------------------------------------------------------------------------
# Dialogue & narration
# -----------------------------------------------------------------------------


class VisemeKeyframe(_IRModel):
    """A single mouth-shape keyframe in a viseme track."""

    time: Seconds
    viseme: str  # Rhubarb letter A-H/X, MPEG-4 viseme number, or Azure name


class VisemeTrack(_IRModel):
    """Aligned viseme track produced by the lip-sync stage. Optional in P1."""

    fps_hint: float | None = None
    keyframes: list[VisemeKeyframe] = Field(default_factory=list)


class WordTimingIR(_IRModel):
    """One word of a line and when it was spoken, in seconds from the line's
    start (like :class:`VisemeKeyframe`, never absolute). Stamped by the audio
    pipeline from the provider's word timings when it has them (an#96); JSON
    only — ``scene.md`` never carries it, the way it never carries visemes."""

    text: str
    start: Seconds
    end: Seconds

    @model_validator(mode="after")
    def _ordered(self) -> "WordTimingIR":
        if self.start < 0 or self.end < self.start:
            raise ValueError(
                f"word timing {self.text!r} must satisfy 0 <= start <= end; "
                f"got start={self.start}, end={self.end}"
            )
        return self


class Dialogue(_IRModel):
    """One line of spoken dialogue.

    ``timing`` is None until the audio pipeline runs (TTS gives us a real
    duration); the orchestrator fills it in then.
    """

    speaker: str  # the entity id this line belongs to
    text: str
    voice_ref: str | None = None  # key in the voices store; None = default
    start: Seconds | None = None
    duration: Seconds | None = None
    emotion: str | None = None
    viseme_track: VisemeTrack | None = None
    #: The provider's word timings, line-relative; ``None`` when the provider
    #: has none (offline, Rhubarb) or the line was stamped before an#96.
    word_timings: list[WordTimingIR] | None = None
    audio_ref: str | None = None  # mall["audio"] key (content-hash of TTS input)
    viseme_ref: str | None = None  # mall["visemes"] key (content-hash of lipsync input)


class Narration(_IRModel):
    """Off-screen narration. Same shape as Dialogue minus the speaker pin."""

    text: str
    voice_ref: str | None = None
    start: Seconds | None = None
    duration: Seconds | None = None
    viseme_track: VisemeTrack | None = None
    word_timings: list[WordTimingIR] | None = None
    audio_ref: str | None = None
    viseme_ref: str | None = None


# -----------------------------------------------------------------------------
# Transitions and the sound layer (assembled AFTER the shots render; no
# renderer ever sees these — see `an.assemble`)
# -----------------------------------------------------------------------------

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


class Transition(_IRModel):
    """How a shot is ENTERED — from the previous shot, or (for the first shot)
    from nothing.

    >>> Transition(kind="dissolve", duration=0.5).duration
    0.5
    >>> Transition(kind="fade").color
    '#000000'

    - ``cut`` — the default, and what a shot with no ``transition`` means.
    - ``fade`` — through ``color``: the previous shot's last ``duration / 2``
      fades to the colour and this shot's first ``duration / 2`` fades up from
      it. On the FIRST shot the whole ``duration`` is a fade up from the
      colour. **Holds the film's length**: nothing overlaps.
    - ``dissolve`` — the previous shot's last ``duration`` seconds and this
      shot's first ``duration`` seconds are seen through each other. **The
      film gets ``duration`` shorter** than the sum of its shots: both shots
      play in full, overlapped (the editor's convention — the overlapped
      seconds are each shot's "handle"). Dialogue stays in sync with its own
      shot's picture; audio from both shots is heard in the overlap. Not
      allowed on the first shot.
    """

    kind: Literal["cut", "fade", "dissolve"] = "cut"
    duration: Seconds = Field(default=DEFAULT_TRANSITION_DURATION, ge=0)
    color: str = DEFAULT_TRANSITION_COLOR

    @model_validator(mode="after")
    def _hex_color(self) -> "Transition":
        if not _HEX_COLOR.fullmatch(self.color):
            raise ValueError(f"transition color must be '#rrggbb'; got {self.color!r}")
        return self


class SoundCue(_IRModel):
    """One sound placed on the timeline: an SFX hit, an ambience, a music bed.

    ``sound`` is a key in the project's ``sounds`` store (`an.sounds`), where
    the bytes and their licence live — the IR never inlines audio.

    ``at`` is seconds from the start of whatever holds the cue: a shot's
    ``sounds`` are SHOT-local (they move with the shot, across transitions
    and re-orderings), ``meta.sounds`` are FILM time (a music bed under the
    whole thing).

    >>> SoundCue(sound="hit", at=1.2).gain_db
    0.0
    >>> SoundCue(sound="bed", loop=True, duck_db=-12).duck_db
    -12.0
    """

    sound: str
    at: Seconds = Field(default=0.0, ge=0)
    #: How long it plays. ``None``: the asset's own length, or — when
    #: ``loop`` — to the end of its shot (shot cue) or of the film (meta cue).
    duration: Seconds | None = Field(default=None, gt=0)
    gain_db: float = 0.0
    loop: bool = False
    fade_in: Seconds = Field(default=0.0, ge=0)
    fade_out: Seconds = Field(default=0.0, ge=0)
    #: Attenuation, in dB, while any dialogue line plays; ``None`` never ducks.
    #: A music bed usually wants ``DEFAULT_DUCK_DB``; an SFX hit wants none.
    duck_db: float | None = Field(default=None, le=0)
    duck_attack: Seconds = Field(default=DEFAULT_DUCK_ATTACK_S, gt=0)
    duck_release: Seconds = Field(default=DEFAULT_DUCK_RELEASE_S, gt=0)


# -----------------------------------------------------------------------------
# Captions (built from the dialogue's word timings at render time — see
# `an.captions`; no renderer reads this model directly)
# -----------------------------------------------------------------------------

#: Characters per caption line and lines per caption page: the broadcast
#: convention (BBC / Netflix timed-text guidance: 42 characters, two lines).
DEFAULT_CAPTION_MAX_CHARS: int = 42
DEFAULT_CAPTION_MAX_LINES: int = 2

#: Caption type size as a fraction of frame height — a little under the title
#: default, as captions are read while something else is watched.
DEFAULT_CAPTION_SIZE: float = 0.05


class Captions(_IRModel):
    """Captions for the whole film, built from the dialogue's word timings.

    Present = on; ``meta.captions`` unset (the default) is no captions and no
    trace in any document. One cue list (:func:`an.captions.caption_pages`)
    feeds BOTH outputs, so the picture and the sidecar cannot disagree:

    - ``burn``: each page is drawn as an overlay text block (camera-immune,
      placed at ``anchor`` in the title-safe area), shown for exactly the
      frames the sidecar says;
    - ``sidecar``: a SubRip ``.srt`` written through the ``captions`` store,
      next to the delivered mp4, in FILM time (a dissolve shortens the film,
      and every later cue moves with it).

    >>> Captions().max_chars, Captions().anchor
    (42, 'bottom')
    >>> Captions(highlight="#ffcc00").highlight
    '#ffcc00'
    """

    burn: bool = True
    sidecar: bool = True
    #: Line breaks are made HERE, by character count, and written into both
    #: the burned block and the sidecar — the same lines in both. 42 fits the
    #: title-safe width of a 16:9 or 4:3 frame at the default size; a square
    #: or portrait frame needs fewer (about 32 at 1:1) or a smaller ``size`` —
    #: a line that does not fit is REFUSED before the render, never clipped.
    max_chars: int = Field(default=DEFAULT_CAPTION_MAX_CHARS, ge=1)
    max_lines: int = Field(default=DEFAULT_CAPTION_MAX_LINES, ge=1)
    size: float = Field(default=DEFAULT_CAPTION_SIZE, gt=0, le=1, allow_inf_nan=False)
    color: str = "#1a1a1a"
    #: ``#rrggbb``: the word being spoken is drawn in this colour (karaoke);
    #: ``None`` draws every word in ``color``.
    highlight: str | None = None
    #: One of tituli's nine title-safe anchors.
    anchor: str = "bottom"
    #: ``None`` = the embedded face; else an ABSOLUTE font file path, or one
    #: relative to the project directory.
    font: str | None = None
    #: A line with no word timings is captioned with its words spread evenly
    #: over its duration, with a warning; ``strict`` makes that an error.
    strict: bool = False

    @model_validator(mode="after")
    def _hex_colors(self) -> "Captions":
        for name in ("color", "highlight"):
            value = getattr(self, name)
            if value is not None and not _HEX_COLOR.fullmatch(value):
                raise ValueError(f"captions {name} must be '#rrggbb'; got {value!r}")
        from tituli import ANCHORS  # the typesetter owns the anchor vocabulary

        if self.anchor not in ANCHORS:
            raise ValueError(
                f"unknown captions anchor {self.anchor!r}; choose from {sorted(ANCHORS)}"
            )
        return self


# -----------------------------------------------------------------------------
# Shot
# -----------------------------------------------------------------------------


class Shot(_IRModel):
    """A single rendered unit. A scene is a sequence of shots.

    A shot's ``renderer`` selects the backend that draws it. Every renderer must accept the
    same Shot fields; renderer-specific options go under ``options``.
    """

    id: str
    #: Which RENDERER draws this shot — not art direction. The field was
    #: called `style` until an#106, colliding with the styles store (which
    #: holds art direction) and with `AssetRef(kind="style")`; one word for two
    #: meanings is how a scene came to declare a "style" that selected a
    #: renderer while the thing that actually styles it went unread.
    renderer: RendererName = "cutout"
    duration: Seconds = DEFAULT_DURATION
    camera: Camera | None = None
    entities: list[AssetRef] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    dialogue: list[Dialogue] = Field(default_factory=list)
    narration: list[Narration] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    #: Per-shot override of :attr:`Meta.step_hz` (``None`` = inherit).
    step_hz: float | None = Field(default=None, gt=0)
    #: How this shot is entered (:class:`Transition`); ``None`` is a hard cut.
    transition: Transition | None = None
    #: Sound cues in SHOT-local time (:class:`SoundCue`).
    sounds: list[SoundCue] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_unset_assembly(self, handler):
        """Serialize ``transition``/``sounds`` out of existence when unset.

        `AssetRef._omit_unset_stage`'s rule: every committed ``ir/scene.json``
        predates these fields, and a defaulted ``null`` / ``[]`` on every shot
        would rewrite all of them on the next ``an sync``.
        """
        data = handler(self)
        if isinstance(data, dict):
            if self.transition is None:
                data.pop("transition", None)
            if not self.sounds:
                data.pop("sounds", None)
        return data


def resolve_step_hz(shot: "Shot", scene_step_hz: float | None) -> float | None:
    """The stepped-timing policy ``shot`` renders under: its own ``step_hz``
    when it declares one, else the scene's, else ``None`` (smooth). The ONE
    statement of the shot-over-scene rule — the cutout renderer, the preview
    and the project renderer all call it (an#89 review: three copies).

    >>> resolve_step_hz(Shot(id="s", step_hz=10.0), 15.0)
    10.0
    >>> resolve_step_hz(Shot(id="s"), 15.0)
    15.0
    >>> resolve_step_hz(Shot(id="s"), None) is None
    True
    """
    return shot.step_hz if shot.step_hz is not None else scene_step_hz


# -----------------------------------------------------------------------------
# Top-level Scene IR
# -----------------------------------------------------------------------------


class Meta(_IRModel):
    """Scene metadata."""

    title: str = ""
    author: str = ""
    duration: Seconds = 0.0
    fps: int = DEFAULT_FPS
    resolution: Resolution = Field(default_factory=Resolution)
    default_renderer: RendererName = "cutout"
    notes: str = ""
    #: Stepped timing for AUTHORED TWEENS, in pose updates per second; ``None``
    #: (the default) leaves every tween smooth. At 30 fps, ``15`` is "on twos"
    #: and ``10`` "on threes" — the character-animation practice Spider-Verse
    #: made famous (characters on twos, simulation on ones). The camera is
    #: exempt by construction, as are swap channels (already stepped by
    #: format), compiled blinks and ``play`` clips: only `tween` curves are
    #: resampled — sample-and-hold of the eased curve on a SHOT-wide grid
    #: (every tween in a shot shares it; it restarts at a cut), not a retiming
    #: into holds and fast transitions. A tween's own START and END are always
    #: pose changes too, so a tween that begins or ends off-grid changes pose
    #: on that frame as well as on the grid (a ``set`` at an off-grid ``at``
    #: likewise lands where it was authored). A shot's own ``step_hz``
    #: overrides this. Must be positive (schema) and ``<= fps`` (validate +
    #: compile), an#89.
    step_hz: float | None = Field(default=None, gt=0)

    #: The `StylePack` in the project's `styles` store this scene is drawn
    #: under, by key. ``None`` — the default and what every existing document
    #: has — leaves every colour exactly where it is, which is why adding this
    #: moved no corpus hash (an#112).
    #:
    #: A pack changes what the COMPILER decides: the character palette, the
    #: leg and pupil colours, the environment presets' sky and ground. It does
    #: NOT recolour SVG art — that would need role tagging the descriptor does
    #: not have, and inferring a role from a pixel is what produced an#99's
    #: wrong-tone lid. A rig whose art a pack cannot reach is WARNED about by
    #: name at compile.
    style_pack: str | None = None

    #: The easing every authored ``tween`` that names none is drawn with
    #: (an#166) — ``"linear"`` for a snappy South Park cadence, an overshooting
    #: cubic-Bezier for a bouncy one. Precedence is **tween > this > the
    #: built-in ``"ease_in_out"``** (:meth:`TweenAction.resolved_easing`).
    #: ``None`` — the default and what every existing document has — changes
    #: nothing, and is omitted from JSON like ``style_pack``, so no committed
    #: scene and no compiled document moves. It reaches authored tweens ONLY:
    #: a motion preset writes its own easings, the camera's named moves supply
    #: theirs, and blinks, ``play`` clips and swap channels have none to
    #: inherit. There is no per-shot override yet — style is a scene's.
    default_easing: EasingSpec | None = None
    #: Sound cues in FILM time — a music bed, an ambience under every shot
    #: (:class:`SoundCue`). Empty, the default, is no sound layer at all.
    sounds: list[SoundCue] = Field(default_factory=list)
    #: Captions from the dialogue's word timings (:class:`Captions`, an#175);
    #: ``None`` — the default — is none, omitted from JSON like ``style_pack``.
    captions: Captions | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_style_pack(self, handler):
        """Serialize ``style_pack: null`` out of existence when it is unset.

        The same rule as `AssetRef._omit_unset_stage`, and the same reason:
        every committed `ir/scene.json` in this repo — and whatever a user has
        on disk — predates the field, so a defaulted `null` on every scene's
        meta rewrites all of them on the next `an sync`. A field nobody set
        should leave no trace (an#112).
        """
        data = handler(self)
        # Truthiness, not `is None`: an empty string is not a pack — the
        # resolver already treats it as none — and serializing a visible
        # `style_pack: ""` that does nothing is the shape this omit exists to
        # prevent (an#112 review, L2).
        if isinstance(data, dict) and not data.get("style_pack"):
            data.pop("style_pack", None)
        # The same rule for `default_easing` (an#166), in the same serializer
        # because a model has one.
        if isinstance(data, dict) and data.get("default_easing") is None:
            data.pop("default_easing", None)
        # `sounds` likewise: an empty list is what every existing meta means.
        if isinstance(data, dict) and not self.sounds:
            data.pop("sounds", None)
        # `captions` likewise (an#175): unset is what every existing meta means.
        if isinstance(data, dict) and self.captions is None:
            data.pop("captions", None)
        return data


class SceneIR(_IRModel):
    """Top-level Scene IR document. The SSOT.

    A document is portable, diffable, and renderer-agnostic. Persisted as JSON
    at ``ir/scene.json`` inside an an project.

    >>> from an.base import SCHEMA_VERSION
    >>> doc = SceneIR(meta=Meta(title="Hello"))
    >>> doc.version == SCHEMA_VERSION
    True
    >>> round_tripped = SceneIR.model_validate_json(doc.model_dump_json())
    >>> round_tripped.meta.title
    'Hello'
    """

    version: str = SCHEMA_VERSION
    compatible_version: str = COMPATIBLE_VERSION
    kind: Literal["SceneIR"] = "SceneIR"
    meta: Meta = Field(default_factory=Meta)
    assets: list[AssetRef] = Field(default_factory=list)
    timeline: list[Shot] = Field(default_factory=list)
