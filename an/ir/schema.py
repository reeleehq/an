"""Pydantic v2 models for the Scene IR.

Design principles (locked in from the architectural plan):

- **Renderer-agnostic.** No cutout-specific or Manim-specific fields here. Backend
  adapters compile shots into their own internal formats. This module only knows
  what every shot has in common.
- **Versioned envelope.** Every IR document carries `version` and
  `compatible_version`. Migrations live in `an.ir.migrate`.
- **Forward-compatible reads.** Top-level model has ``extra="allow"`` so a future
  field doesn't crash an older reader.
- **Open `Action` union** (ADR 0001 decision 2). The union holds the core
  kinds (``set``, ``tween``, ``sequence``, ``parallel``, ``delay``, ``loop``)
  and ONE open member, :class:`ExtensionAction`, which a callable
  discriminator selects for any other ``kind``. A genre registers its kinds
  (:mod:`an.genres`); a document's ``kind: play`` then validates to the
  registered model, and before registration it stays an ``ExtensionAction``
  that round-trips untouched and that validate, flatten and the compiler
  refuse by name. The union is never rebuilt at registration.
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

from pydantic import (
    AliasChoices,
    model_serializer,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    SerializeAsAny,
    Tag,
    field_validator,
    model_validator,
)

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
)
from an.genres.registry import (
    CORE_OWNER,
    EntityKind,
    action_kind,
    entity_kind,
    register_entity_kind,
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


#: A camera shake's defaults (an#429): how long a jolt lasts, how far the frame
#: jumps (a fraction of the frame HEIGHT, so it reads the same at any
#: resolution: 0.015 is about 11 px at 720p), and how many times a second it
#: jumps. Art direction, chosen to read as an impact rather than a tremor.
DFLT_SHAKE_DURATION: float = 0.4
DFLT_SHAKE_AMPLITUDE: float = 0.015
DFLT_SHAKE_FREQUENCY: float = 24.0


class CameraShake(_IRModel):
    """A jolt of the frame inside a shot (an#429): seeded screen-space jitter.

    >>> CameraShake(at=1.0).duration
    0.4

    Layered on whatever the camera does (a `move`, `keys`, or nothing): the
    pan and zoom are the root's pivot and scale, a shake is its screen
    position, so the two add without either knowing the other. The jitter is
    deterministic (``seed``) and, with ``decay``, falls linearly to rest by
    the end; the frame is exactly at rest before ``at`` and after it.
    """

    #: When the jolt starts, in shot seconds.
    at: Seconds = 0.0
    #: How long it lasts.
    duration: float = Field(default=DFLT_SHAKE_DURATION, gt=0.0, allow_inf_nan=False)
    #: How far the frame jumps at most, as a fraction of the frame height.
    amplitude: float = Field(default=DFLT_SHAKE_AMPLITUDE, ge=0.0, allow_inf_nan=False)
    #: Jumps per second.
    frequency: float = Field(default=DFLT_SHAKE_FREQUENCY, gt=0.0, allow_inf_nan=False)
    #: Fall linearly to rest over the duration (an impact); off, it holds its
    #: amplitude to the end (a rumble).
    decay: bool = True
    #: Which jitter: the same seed draws the same jolt on every machine.
    seed: int = 0


class CameraFollow(_IRModel):
    """A camera that follows an entity (an#445): the frame keeps ``target``
    where it stood at the shot's start.

    >>> CameraFollow(target="bob").axes
    'x'

    ``target`` is an entity id or one of its nodes (``bob/head``); ``axes`` is
    which way the camera tracks it (``x``: a side-scrolling walk, ``xy``: both).
    Resolved at compile time from the compiled motion (the target's position at
    every frame), so planes parallax with it like any camera move.
    """

    target: PathStr
    axes: Literal["x", "y", "xy"] = "x"


class _CameraShakes(_IRModel):
    """The camera's layers beside its move: shakes (an#429) and a follow
    (an#445), kept apart from :class:`Camera`'s own block so its move
    vocabulary reads only moves (``test_loud_discards``)."""

    #: Jolts of the frame layered on the move or keys. `None`, not `[]`, for
    #: the reason `Camera.keys` gives.
    shake: list[CameraShake] | None = None
    #: Track an entity instead of a named move or keys (an#445).
    follow: CameraFollow | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_shake(self, handler):
        """No shake or follow, no key: every document written before an#429
        dumps byte-identically (the round-trip guard reads every committed scene)."""
        data = handler(self)
        if isinstance(data, dict):
            for name in ("shake", "follow"):
                if data.get(name) is None:
                    data.pop(name, None)
        return data


class Camera(_CameraShakes):
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
    #: `an.stage.compile.CAMERA_MOVES`; validate and the compiler are
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

    **`after` landed in an#344** (a studio set's sky disc between a sky plane
    and a holed wall plate): it names the anchor the entity is drawn right
    after. `depth` is still not a field: an entity takes the depth of the plane
    it is placed after. The paragraphs below are the record of why both were
    deferred, kept because `depth`'s reason still holds.

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
    #: What this entity is drawn immediately after (an#344): an environment
    #: plane (``"set/skyline"``) or another placed entity (``"grid"``).
    #: ``None`` = the default band, where the environment's
    #: ``characters_after`` cuts. A plane's parallax carries an entity placed
    #: after it; an entity placed after an entity rides the default depth.
    after: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_after(self, handler):
        """``after: null`` is never written: every stored scene stays as it was."""
        data = handler(self)
        if isinstance(data, dict) and self.after is None:
            data.pop("after", None)
        return data


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
    #:
    #: A ``str`` in the schema, not a ``Literal`` (ADR 0001 decision 2): the
    #: values are the REGISTERED entity kinds (:mod:`an.genres`) — the core's
    #: ``environment``, ``prop`` and ``voice``, a genre's ``character`` — and
    #: ``an validate`` checks it against that registry, naming the genre that
    #: provides an unregistered one.
    kind: str
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

    #: The asset-library version this entry was checked out from (ADR 0005
    #: decision 8): ``"[<library>:]<asset_id>@<version>"``, e.g.
    #: ``"cutan:character.alice-reiniger@v003"`` (grammar:
    #: :func:`an.library.ids.parse_ref`, a pinned version required: ``vNNN`` or
    #: ``sha256:<prefix>``, never ``latest``). ``None`` — the
    #: default, and every document written before the library existed — means
    #: the asset is the project's own. Today the strategy is check-out, so
    #: ``ref`` still names the project-store key the compiler reads and this
    #: field is the pin beside it; live reference resolves it instead, later.
    #:
    #: Additive and omit-when-unset, like ``stage``: an unset ``library``
    #: leaves no trace in a dump, so no stored scene changes and no schema
    #: version moves.
    library: str | None = None

    #: Joints this entity declares (:class:`JointSpec`, ADR 0008): its parts'
    #: limits, its strings, its pins to other entities; ``a`` is relative to
    #: the entity. Omitted when empty, so no stored scene changes.
    joints: list["JointSpec"] = Field(default_factory=list)

    @field_validator("library")
    @classmethod
    def _check_library_ref(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Imported here, not at module top: the IR must not depend on the
        # library package at import time (it imports the IR's neighbours).
        from an.library.ids import parse_ref

        return str(parse_ref(v, require_pin=True))

    @model_serializer(mode="wrap")
    def _omit_unset_stage(self, handler):
        """Serialize ``stage: null`` and ``library: null`` out of existence when unset.

        The precedent is `serialize._omit_unset_step_hz`, and the reason is
        the same one scaled down: every committed `ir/scene.json` in this repo
        — corpus fixtures, examples, and whatever a user has on disk — was
        written before this field existed. A defaulted `null` on every
        `AssetRef` would rewrite all of them on the next `an sync`, and
        `test_every_speaking_corpus_scene_ir_is_reproducible_from_its_md`
        would be red until each was regenerated. A field nobody set should
        leave no trace (an#108; ``library`` joined it under ADR 0005).
        """
        data = handler(self)
        if self.stage is None:
            data.pop("stage", None)
        if self.library is None:
            data.pop("library", None)
        if not self.joints:
            data.pop("joints", None)
        return data


# -----------------------------------------------------------------------------
# The scene world (ADR 0009): one world, and shots as viewpoints onto it.
# The models are here beside `Camera`; the geometry and the lowering live in
# `an.ir.world`, as the camera's resolver lives in `an.ir.camera`.
# -----------------------------------------------------------------------------

#: A finite coordinate: pydantic writes `inf`/`nan` as JSON null and refuses
#: it on the next read (the `StagePlacement.at` lesson, an#108).
_Coord = Annotated[float, Field(allow_inf_nan=False)]
#: A world position ``(x, y, z)``: the stage's axes extended with depth — `x`
#: right, `y` DOWN, `z` away from the viewer. The unit is the author's.
Point3 = tuple[_Coord, _Coord, _Coord]
Point2 = tuple[_Coord, _Coord]

#: The horizontal field of view a viewpoint has when it names neither `fov`
#: nor `focal`: a normal lens, neither wide nor long.
DFLT_FOV_DEG: float = 50.0

#: Shot sizes, by where the frame cuts the subject (the film convention, see
#: ADR 0009): ``name: (top, bottom, fill)``. ``top``/``bottom`` are the band of
#: the subject's box the frame shows, as fractions of its height from the top
#: (``0.35``: head and shoulders; ``0.55``: the waist); ``fill`` is how much of
#: the frame's height that band fills. A genre may later supply landmarks from
#: its rig (a seam, not built); until then these are human proportions.
SHOT_SIZES: dict[str, tuple[float, float, float]] = {
    "wide": (0.0, 1.0, 0.5),
    "full": (0.0, 1.0, 0.9),
    "medium": (0.0, 0.55, 0.9),
    "close_up": (0.0, 0.35, 0.9),
}

#: A travel's depth range, in world units: nearer than `near` an instance has
#: passed the camera (and is hidden); beyond `far` it is effectively at infinity
#: (the far plate's job, not a stream's).
DFLT_TRAVEL_NEAR: float = 0.5
DFLT_TRAVEL_FAR: float = 60.0
#: How far a stream instance's screen position may stray from the fitted
#: tweens between two of their keys, in pixels: the fitting's tolerance.
DFLT_TRAVEL_TOLERANCE_PX: float = 1.0
#: The most actions one shot's travel may lower to before the lowering
#: refuses and names the knobs: a 10 s road with three streams is about four
#: thousand; a minute of dense road markings would be fifty thousand, which
#: is a document the runtime pays for on every frame.
DFLT_TRAVEL_MAX_ACTIONS: int = 20_000


#: The root of the frame tree: the world itself. Always present, never declared.
WORLD_FRAME: str = "world"
#: The frame a `travel` with a `speed` is sugar for (viewpoints and members
#: ride it by default; streams stay in the world).
VEHICLE_FRAME: str = "vehicle"
#: How a frame follows its parent: `rigid` takes the parent's whole pose,
#: `far` only its rotation (what is at infinity turns with the camera and never
#: translates).
FRAME_COUPLINGS: tuple[str, ...] = ("rigid", "far")
#: The key an element's frame is written under in a document (`frame` is the
#: field; `in` is not a name Python lets a field have).
FRAME_KEY: str = "in"
_FRAME_FIELD = Field(default=None, validation_alias=AliasChoices(FRAME_KEY, "frame"))


def _frame_key(data: Any) -> Any:
    """``data`` with the ``frame`` field written under the document's key
    ``in`` (and left out when unset: a scene that names no frame stores none)."""
    if isinstance(data, dict):
        frame = data.pop("frame", None)
        if frame is not None:
            data[FRAME_KEY] = frame
    return data


def _omit_none(data: Any, *keys: str) -> Any:
    """``data`` without the ``keys`` whose value is ``None``: a field nobody set
    leaves no trace in a stored document (the `stage`/`library` rule)."""
    if isinstance(data, dict):
        for key in keys:
            if data.get(key) is None:
                data.pop(key, None)
    return data


class Attachment(_IRModel):
    """A member that goes where another member goes (ADR 0009 decision 1).

    >>> Attachment(to="paul", at=(8.0, 70.0), scale=0.9).to
    'paul'

    ``at`` is the offset in the HOST's native units (its art's pixels at
    ``stage.scale`` 1) and ``scale`` the size relative to the host, so the
    pair is derived from the host's placement in every framing. Without
    ``at`` the member is added whenever the host is, with no placement of
    its own: another pass places it (the cut-out genre's body attachments,
    from the host's bones).
    """

    to: str
    at: Point2 | None = None
    scale: float = Field(default=1.0, gt=0, allow_inf_nan=False)

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        data = handler(self)
        if isinstance(data, dict) and self.scale == 1.0:
            data.pop("scale", None)
        return _omit_none(data, "at")


class WorldMember(AssetRef):
    """An entity of the scene's world: the same reference a shot's entity
    carries, at a world position with a size (ADR 0009 decision 1).

    >>> m = WorldMember(kind="character", id="paul", store="characters", ref="paul",
    ...                 at=(0.45, 0.65, 1.6), height=1.75)
    >>> m.at, m.height
    ((0.45, 0.65, 1.6), 1.75)

    ``at`` is where the entity's placement point stands (a character's feet,
    a prop's origin) in world units; exactly one of ``height``/``width`` (its
    size in world units) or ``units_per_px`` (world units per native pixel, for art
    whose extent cannot be measured) sizes it. A member is ``attached`` to
    another instead of positioned, or it is an environment (present in every
    framed shot, placed by nothing: plates are per shot). ``after`` is the
    draw anchor a shot's ``stage.after`` would be. A member never carries
    ``stage``: the viewpoint places it.
    """

    at: Point3 | None = None
    height: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    units_per_px: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    attached: Attachment | None = None
    after: str | None = None
    #: The frame of reference this member is in (document key ``in``); unset
    #: means the world's default frame (:meth:`World.default_frame`). An
    #: environment's ``frame`` is the default of its planes; ``planes`` names
    #: the exceptions, ``{plane name: frame}`` (one environment can hold a
    #: cabin plate and a sky plate).
    frame: str | None = _FRAME_FIELD
    planes: dict[str, str] | None = None

    @model_validator(mode="after")
    def _one_way_to_place_it(self) -> "WorldMember":
        where = f"world member {self.id!r}"
        if self.stage is not None:
            raise ValueError(
                f"{where} carries `stage`: a member is placed by each shot's "
                "viewpoint. Give it `at: [x, y, z]` and a size instead."
            )
        sizes = [
            k
            for k in ("height", "width", "units_per_px")
            if getattr(self, k) is not None
        ]
        if self.planes is not None and self.kind != "environment":
            raise ValueError(
                f"{where} is not an environment: only an environment has `planes` "
                "(which frame each of its planes is in)."
            )
        if self.kind == "environment":
            if self.at is not None or self.attached is not None or sizes:
                raise ValueError(
                    f"{where} is an environment: it has no position or size (its "
                    "plates are drawn per shot); list it with its reference only "
                    "(and, when its plates are in frames, `in` / `planes`)."
                )
            return self
        if self.attached is not None and self.frame is not None:
            raise ValueError(
                f"{where} is attached to {self.attached.to!r}: it is in its host's "
                "frame; drop `in`."
            )
        if (self.at is None) == (self.attached is None):
            raise ValueError(
                f"{where} needs exactly one of `at: [x, y, z]` or `attached: "
                "{to: <member>}`."
            )
        if self.at is not None and len(sizes) != 1:
            raise ValueError(
                f"{where} needs exactly one of `height`, `width` (world units) or "
                f"`units_per_px` (world units per native pixel); it has {sizes or 'none'}."
            )
        if self.attached is not None and sizes:
            raise ValueError(
                f"{where} is attached to {self.attached.to!r}: its size is the "
                "attachment's `scale`, relative to the host; drop "
                f"{sizes}."
            )
        if self.attached is not None and self.attached.to == self.id:
            raise ValueError(f"{where} is attached to itself.")
        return self

    @model_serializer(mode="wrap")
    def _omit_unset_world_fields(self, handler):
        data = handler(self)
        if isinstance(data, dict) and not self.joints:
            data.pop("joints", None)
        return _frame_key(
            _omit_none(
                data,
                "stage",
                "library",
                "at",
                "height",
                "width",
                "units_per_px",
                "attached",
                "after",
                "frame",
                "planes",
            )
        )


class Weld(_IRModel):
    """A held item: ``item`` stays at ``offset`` from ``by`` between ``start`` and
    ``until`` (catalogue A4). Pick-up is ``start``, release is ``until``.

    >>> Weld(item="cup", by="paul/hand_r", start=1.0, until=3.0).by
    'paul/hand_r'

    ``by`` is a node path (an entity, or a bone of it) and ``item`` an entity id,
    both in the shot. ``offset`` is where the item's centre sits from the carrier's
    centre, in scene px; without it, the offset the two have at ``start`` is the
    one that must hold. ``until`` ``None`` is the end of the shot. A declaration
    only: a lint reads it, nothing is composed from it.
    """

    item: str
    by: str
    start: Seconds = 0.0
    until: Seconds | None = None
    offset: Point2 | None = None

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        return _omit_none(handler(self), "until", "offset")


# -----------------------------------------------------------------------------
# The constraint layer (ADR 0008, an#512): joints between bodies, and how a
# shot is solved. The models are here beside `Weld`; the verbs that change a
# joint over time (`pin`, `pull`, `join`, `unjoin`) are in `an.ir.joints`, the
# reading of bodies from a rig in `an.stage.rig`, the solve in `an.stage.solve`.
# -----------------------------------------------------------------------------

#: The joint types a scene declares. ``string`` (a distance held at most) and
#: ``rod`` (a distance held exactly) are the puppeteer's names for a
#: ``distance`` with its ``mode`` set.
JOINT_TYPES: tuple[str, ...] = (
    "pin",
    "hinge",
    "weld",
    "distance",
    "string",
    "rod",
    "slide",
    "contact",
)
#: The types that join a point to a segment (``b`` is its start, ``end`` its end).
SEGMENT_JOINT_TYPES: frozenset[str] = frozenset({"slide", "contact"})
#: The types that may name only ``a``: a rig part's own joint to its parent.
PART_JOINT_TYPES: frozenset[str] = frozenset({"hinge", "weld"})
#: How a distance holds its length; ``string`` and ``rod`` imply one.
DISTANCE_MODES: tuple[str, ...] = ("equal", "at_most", "at_least")
IMPLIED_DISTANCE_MODE: dict[str, str] = {"string": "at_most", "rod": "equal"}

#: The pull of gravity a ``down`` with no number means, in scene px per second²
#: (a 1080-px frame is about 1.1 m of a standing figure, so 980 is earth's g at
#: roughly one pixel per millimetre: the conventional animation default).
DFLT_GRAVITY: float = 980.0
#: Where each named gravity direction pulls, on the stage's y-down axes.
GRAVITY_DIRECTIONS: dict[str, tuple[float, float]] = {
    "down": (0.0, 1.0),
    "up": (0.0, -1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
}
#: The spellings of no gravity.
NO_GRAVITY: frozenset[str] = frozenset({"none", "off"})


def gravity_vector(spec: Any) -> tuple[float, float] | None:
    """The acceleration a gravity declaration means, or ``None`` for none.

    ``spec`` is how a style pack or a shot spells it: ``"down 980"``, ``"down"``
    (:data:`DFLT_GRAVITY`), ``"none"``, a number (down at that strength), or a
    mapping ``{strength, direction}`` (the shape the ``gravity`` lint reads).

    >>> gravity_vector("down 500"), gravity_vector("none"), gravity_vector(None)
    ((0.0, 500.0), None, None)
    >>> gravity_vector({"direction": "left"})
    (-980.0, 0.0)
    >>> gravity_vector("sideways")
    Traceback (most recent call last):
    ...
    ValueError: gravity 'sideways': say a direction (down, up, left, right) and an optional strength in px/s², e.g. 'down 980', or 'none'
    """
    if spec is None:
        return None
    direction, strength = "down", DFLT_GRAVITY
    if isinstance(spec, bool):
        raise ValueError(f"gravity {spec!r}: say 'down 980' or 'none'")
    if isinstance(spec, (int, float)):
        strength = float(spec)
    elif isinstance(spec, str):
        words = spec.lower().split()
        if len(words) == 1 and words[0] in NO_GRAVITY:
            return None
        if not words or words[0] not in GRAVITY_DIRECTIONS or len(words) > 2:
            raise ValueError(
                f"gravity {spec!r}: say a direction ({', '.join(GRAVITY_DIRECTIONS)}) "
                "and an optional strength in px/s², e.g. 'down 980', or 'none'"
            )
        direction = words[0]
        if len(words) == 2:
            try:
                strength = float(words[1])
            except ValueError:
                raise ValueError(f"gravity {spec!r}: {words[1]!r} is not a number") from None
    elif hasattr(spec, "get"):
        direction = str(spec.get("direction") or "down").lower()
        if direction in NO_GRAVITY:
            return None
        if direction not in GRAVITY_DIRECTIONS:
            raise ValueError(f"gravity direction {direction!r}: one of {list(GRAVITY_DIRECTIONS)}")
        if spec.get("strength") is not None:
            strength = float(spec.get("strength"))
    else:
        raise ValueError(f"gravity {spec!r}: say 'down 980' or 'none'")
    if not (strength >= 0.0 and strength < float("inf")):
        raise ValueError(f"gravity strength must be a finite non-negative number, got {strength}")
    if strength == 0.0:
        return None
    dx, dy = GRAVITY_DIRECTIONS[direction]
    return (dx * strength + 0.0, dy * strength + 0.0)


class JointSpec(_IRModel):
    """A declared relation between two bodies (ADR 0008 decision 3).

    >>> JointSpec(type="hinge", a="lamp/upper", limits=(-40, 90)).id
    'lamp/upper'
    >>> JointSpec(type="pin", a="paul/fore_r@hand_r", b="wheel@grip", name="grip").id
    'grip'

    A **body** is a node path (``paul/fore_r``, or an entity id for an entity
    with one root part), and a **point** on it follows ``@``: a fraction of the
    body's extent (``@0.5,1``), or the name of a bone of its rig (``@hand_r``:
    a bone with no slot is a landmark). With no ``@`` the point is the body's
    pivot for ``a`` and the centre of its extent for ``b``. ``world@x,y`` is a
    point of the stage, in scene px from its centre (``StagePlacement.at``'s
    ruler).

    - ``pin``: the two points coincide; ``hinge`` adds an angle range
      (``limits``, degrees about the rest pose, ``a``'s body relative to
      ``b``'s); ``weld`` holds the rest angle too. A ``hinge`` or ``weld`` that
      names only ``a`` (a rig part) is that part's own joint to its parent:
      its ``limits`` override the bone's.
    - ``distance`` keeps ``length`` (default: the distance at rest) per
      ``mode``; ``string`` is a distance held at most, ``rod`` exactly.
    - ``slide`` keeps ``a`` on the segment ``b`` to ``end``; ``contact`` keeps
      it on the segment's free side (above a left-to-right segment).

    ``give`` is the joint's softness (compliance, px per unit of pull; 0 is
    rigid). ``name`` is what ``join`` and ``unjoin`` call it (default: ``a``).
    On an entity (``AssetRef.joints``) ``a`` is relative to the entity
    (``fore_r@hand_r``, ``@0.5,0``) and ``b`` is a path in the shot.
    """

    type: Literal[
        "pin", "hinge", "weld", "distance", "string", "rod", "slide", "contact"
    ]
    a: str
    b: str | None = None
    end: str | None = None
    limits: tuple[_Coord, _Coord] | None = None
    length: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    mode: Literal["equal", "at_most", "at_least"] | None = None
    give: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    name: str | None = None

    @property
    def id(self) -> str:
        """What ``join`` and ``unjoin`` call this joint."""
        return self.name or self.a

    @property
    def distance_mode(self) -> str:
        """The mode of a distance-like joint (``equal`` unless said or implied)."""
        return self.mode or IMPLIED_DISTANCE_MODE.get(self.type, "equal")

    @model_validator(mode="after")
    def _well_formed(self) -> "JointSpec":
        where = f"joint {self.id!r} ({self.type})"
        if self.b is None and self.type not in PART_JOINT_TYPES:
            raise ValueError(f"{where} needs `b`: the body (or `world@x,y`) it joins `a` to.")
        if (self.end is not None) != (self.type in SEGMENT_JOINT_TYPES):
            raise ValueError(
                f"{where}: `end` (the segment's far end, with `b` its start) is for "
                "slide and contact joints, and they need it."
            )
        if self.limits is not None:
            if self.type != "hinge":
                raise ValueError(f"{where}: only a hinge has `limits`.")
            lo, hi = self.limits
            if not -180.0 <= lo <= hi <= 180.0:
                raise ValueError(
                    f"{where}: limits {list(self.limits)} must be [lo, hi] degrees "
                    "with -180 <= lo <= hi <= 180."
                )
        distance_like = self.type in ("distance", "string", "rod")
        if (self.length is not None or self.mode is not None) and not distance_like:
            raise ValueError(f"{where}: `length` and `mode` are for distance, string and rod joints.")
        if self.mode is not None and self.type in IMPLIED_DISTANCE_MODE and self.mode != IMPLIED_DISTANCE_MODE[self.type]:
            raise ValueError(
                f"{where}: a {self.type} is held {IMPLIED_DISTANCE_MODE[self.type]}; "
                "use `type: distance` for another mode."
            )
        return self

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        data = handler(self)
        if isinstance(data, dict) and not self.give:
            data.pop("give", None)
        return _omit_none(data, "b", "end", "limits", "length", "mode", "name")


class SolveSettings(_IRModel):
    """How a shot's joints are solved: a per-shot override of the style pack's
    ``gravity`` and ``damping``, and the solve's mode and effort (ADR 0008
    decision 4).

    >>> SolveSettings(gravity="down 500").gravity_vector()
    (0.0, 500.0)
    >>> SolveSettings(mode="pose").model_dump()
    {'mode': 'pose'}

    ``mode`` unset is ``dynamic`` when gravity or a string acts (follow-through,
    baked from frame 0) and ``pose`` otherwise (projection to convergence from
    the previous frame: dead still between keys). ``gravity`` unset is the
    style pack's; ``"none"`` switches the pack's off for this shot.
    """

    mode: Literal["pose", "dynamic"] | None = None
    gravity: Any = None
    damping: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    iterations: int | None = Field(default=None, ge=1)
    substeps: int | None = Field(default=None, ge=1)

    @field_validator("gravity")
    @classmethod
    def _gravity_reads(cls, v: Any) -> Any:
        gravity_vector(v)
        return v

    def gravity_vector(self) -> tuple[float, float] | None:
        """This shot's own gravity (``None`` also when it says nothing)."""
        return gravity_vector(self.gravity)

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        return _omit_none(handler(self), "mode", "gravity", "damping", "iterations", "substeps")


# `AssetRef` (and the world member that extends it) name `JointSpec` before it is
# defined: resolve the forward reference now that it is.
AssetRef.model_rebuild()
WorldMember.model_rebuild()


class Viewpoint(_IRModel):
    """A pinhole camera onto the world, or a composition that resolves to one
    (ADR 0009 decision 2).

    >>> Viewpoint(at=(0.0, 0.0, 0.0), vanish=(0.0, -262.0)).vanish
    (0.0, -262.0)
    >>> Viewpoint(subject="paul", size="close_up", subject_at=(190.0, 0.0)).size
    'close_up'

    A camera: ``at`` (world), its look as ``look: [yaw, pitch, roll]`` in
    degrees (yaw turns right, pitch looks down, roll turns the picture clockwise), or
    ``look_at`` (a world point), or ``vanish`` (where the ``+z`` direction
    lands on screen, in pixels from the frame centre: the road's vanishing
    point), and ``fov`` (horizontal, degrees) or ``focal`` (pixels).

    A composition: ``subject`` (a member, or a list), ``size`` (a `SHOT_SIZES`
    name) or ``distance`` (world units), and ``subject_at`` (where the
    subject's band lands on screen, pixels; the centre by default). The
    camera is computed on the look direction so the band fills the frame as
    the size says. ``hide`` names members this shot leaves out.
    """

    at: Point3 | None = None
    look: tuple[_Coord, _Coord, _Coord] = (0.0, 0.0, 0.0)
    look_at: Point3 | None = None
    vanish: Point2 | None = None
    fov: float | None = Field(default=None, gt=0, lt=180, allow_inf_nan=False)
    focal: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    subject: str | list[str] | None = None
    size: str | None = None
    distance: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    subject_at: Point2 = (0.0, 0.0)
    hide: list[str] = Field(default_factory=list)
    #: The frame this camera is mounted in (document key ``in``); its ``at`` and
    #: ``look`` are in that frame's units. Unset: the world's default frame.
    frame: str | None = _FRAME_FIELD

    @model_validator(mode="after")
    def _one_front_door(self) -> "Viewpoint":
        if self.fov is not None and self.focal is not None:
            raise ValueError(
                "a viewpoint sets `fov` or `focal`, not both: they are two spellings "
                "of one lens."
            )
        if self.look_at is not None and self.vanish is not None:
            raise ValueError("a viewpoint sets `look_at` or `vanish`, not both.")
        if (self.look_at is not None or self.vanish is not None) and (
            self.look[0] or self.look[1]
        ):
            raise ValueError(
                "a viewpoint's `look_at`/`vanish` sets its yaw and pitch; `look` may "
                "then only carry a roll ([0, 0, roll])."
            )
        if self.size is not None and self.size not in SHOT_SIZES:
            raise ValueError(
                f"unknown shot size {self.size!r}; the sizes are {sorted(SHOT_SIZES)}."
            )
        if self.subject is None:
            for key in ("size", "distance"):
                if getattr(self, key) is not None:
                    raise ValueError(
                        f"`{key}` needs `subject: <member>`: it frames a subject."
                    )
        else:
            if (
                self.at is not None
                or self.look_at is not None
                or self.vanish is not None
            ):
                raise ValueError(
                    "a viewpoint with a `subject` computes its own position: drop `at`, "
                    "`look_at` and `vanish` (keep `look` for the angle)."
                )
            if self.size is not None and self.distance is not None:
                raise ValueError(
                    "`size` or `distance`, not both: each sets the distance."
                )
            if isinstance(self.subject, list) and not self.subject:
                raise ValueError("`subject: []` frames nothing.")
        return self

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if tuple(self.look) == (0.0, 0.0, 0.0):
                data.pop("look", None)
            if tuple(self.subject_at) == (0.0, 0.0):
                data.pop("subject_at", None)
            if not self.hide:
                data.pop("hide", None)
        return _frame_key(
            _omit_none(
                data,
                "at",
                "look_at",
                "vanish",
                "fov",
                "focal",
                "subject",
                "size",
                "distance",
                "frame",
            )
        )


class Stream(_IRModel):
    """A row of one prop along a travel's direction (ADR 0009 decision 4).

    >>> Stream(id="tree", ref="olive_tree", height=4.0, every=(1.0, 3.0), lane=(-3.0, -2.0)).id
    'tree'

    Instances ``<id>_<k>`` stand ``every`` world units apart along the
    direction (a range is seeded-uniform), ``lane`` to the right of it
    (negative: left), at height ``y``; sized like a member. They are
    positioned in the world once, so every shot sees the same instances in
    the same places at the same film time.
    """

    id: str
    ref: str
    kind: str = "prop"
    store: str = "props"
    height: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    width: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    units_per_px: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    every: _Coord | tuple[_Coord, _Coord]
    lane: _Coord | tuple[_Coord, _Coord] = 0.0
    y: _Coord = 0.0
    after: str | None = None
    seed: int = 0
    #: The frame the row stands in (document key ``in``); unset: the world.
    frame: str | None = _FRAME_FIELD

    @model_validator(mode="after")
    def _spacing_is_positive(self) -> "Stream":
        lo, hi = (
            (self.every, self.every)
            if isinstance(self.every, (int, float))
            else self.every
        )
        if not (0 < lo <= hi):
            raise ValueError(
                f"stream {self.id!r}: `every` must be positive (got {self.every!r})."
            )
        sizes = [
            k
            for k in ("height", "width", "units_per_px")
            if getattr(self, k) is not None
        ]
        if len(sizes) != 1:
            raise ValueError(
                f"stream {self.id!r} needs exactly one of `height`, `width` or `units_per_px`."
            )
        return self

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if self.kind == "prop":
                data.pop("kind", None)
            if self.store == "props":
                data.pop("store", None)
            if self.lane == 0.0:
                data.pop("lane", None)
            if self.y == 0.0:
                data.pop("y", None)
            if self.seed == 0:
                data.pop("seed", None)
        return _frame_key(
            _omit_none(data, "height", "width", "units_per_px", "after", "frame")
        )


#: What a plane under a travel may be declared as: at infinity, or rigid with
#: the vehicle the viewpoints are mounted on.
TRAVEL_PLATE_ROLES: tuple[str, ...] = ("far", "vehicle")


class Travel(_IRModel):
    """The viewpoints moving through the world in film time (ADR 0009 decision 4).

    >>> t = Travel(speed=20.0, streams=[Stream(id="pole", ref="pole", height=6.0, every=12.0, lane=2.0)])
    >>> t.direction, t.speed
    ((0.0, 0.0, 1.0), 20.0)

    The vehicle the members and viewpoints ride moves at ``speed`` world units
    per second of FILM time along ``direction``; ``streams`` stream past
    between ``near`` and ``far``. ``plates`` declares every plane a framed
    shot's environment holds as ``far`` (at infinity; its parallax factor
    must be 0) or ``vehicle`` (rigid with the camera): ``{"far":
    ["set/rear_view"], "vehicle": ["set/cabin"]}``. A plane in neither is a
    validate warning, because a plate with near objects baked in stands
    still while the streams move.
    """

    direction: Point3 = (0.0, 0.0, 1.0)
    speed: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    near: float = Field(default=DFLT_TRAVEL_NEAR, gt=0, allow_inf_nan=False)
    far: float = Field(default=DFLT_TRAVEL_FAR, gt=0, allow_inf_nan=False)
    tolerance_px: float = Field(
        default=DFLT_TRAVEL_TOLERANCE_PX, gt=0, allow_inf_nan=False
    )
    max_actions: int = Field(default=DFLT_TRAVEL_MAX_ACTIONS, gt=0)
    streams: list[Stream] = Field(default_factory=list)
    plates: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _well_formed(self) -> "Travel":
        if not any(self.direction):
            raise ValueError("a travel's `direction` must not be the zero vector.")
        if self.direction[0] == 0.0 and self.direction[2] == 0.0:
            raise ValueError(
                "a travel's `direction` must have a horizontal component: a stream's "
                "`lane` is measured to its right."
            )
        if not self.near < self.far:
            raise ValueError(
                f"a travel needs `near` < `far` (got {self.near} and {self.far})."
            )
        unknown = sorted(set(self.plates) - set(TRAVEL_PLATE_ROLES))
        if unknown:
            raise ValueError(
                f"travel plates may be {list(TRAVEL_PLATE_ROLES)}; got {unknown}."
            )
        seen: dict[str, int] = {}
        for s in self.streams:
            seen[s.id] = seen.get(s.id, 0) + 1
        dupes = sorted(k for k, n in seen.items() if n > 1)
        if dupes:
            raise ValueError(f"streams with duplicate ids: {dupes}.")
        return self

    @model_serializer(mode="wrap")
    def _omit_defaults(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if tuple(self.direction) == (0.0, 0.0, 1.0):
                data.pop("direction", None)
            if self.speed is None:
                data.pop("speed", None)
            if self.near == DFLT_TRAVEL_NEAR:
                data.pop("near", None)
            if self.far == DFLT_TRAVEL_FAR:
                data.pop("far", None)
            if self.tolerance_px == DFLT_TRAVEL_TOLERANCE_PX:
                data.pop("tolerance_px", None)
            if self.max_actions == DFLT_TRAVEL_MAX_ACTIONS:
                data.pop("max_actions", None)
            if not self.streams:
                data.pop("streams", None)
            if not self.plates:
                data.pop("plates", None)
        return data


class FrameMoving(_IRModel):
    """A frame translating at a constant velocity: sugar for a frame whose
    ``at`` grows by ``direction × speed`` per second of FILM time.

    >>> FrameMoving(direction=(0.0, 0.0, 1.0), speed=20.0).speed
    20.0
    """

    direction: Point3 = (0.0, 0.0, 1.0)
    speed: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _has_a_direction(self) -> "FrameMoving":
        if not any(self.direction):
            raise ValueError(
                "a moving frame's `direction` must not be the zero vector."
            )
        return self

    @model_serializer(mode="wrap")
    def _omit_defaults(self, handler):
        data = handler(self)
        if isinstance(data, dict) and tuple(self.direction) == (0.0, 0.0, 1.0):
            data.pop("direction", None)
        return data


class Frame(_IRModel):
    """A frame of reference: a pose (position and orientation) over film time,
    relative to its ``parent`` (ADR 0009 amendment, an#501).

    >>> Frame(moving=FrameMoving(speed=20.0)).parent
    'world'
    >>> Frame(parent="vehicle", coupling="far").coupling
    'far'

    ``at`` and ``look`` (``[yaw, pitch, roll]``, as a viewpoint's) are the pose
    in the parent's units at film time 0; ``moving`` adds a constant velocity;
    a ``set``/``tween`` of ``<frame>:at_x|at_y|at_z|yaw|pitch|roll`` in a shot
    replaces the channel for that shot. ``coupling: far`` follows the parent's
    rotation and none of its translation: the frame of what is at infinity (a
    sky, a range of mountains).
    """

    parent: str = WORLD_FRAME
    at: Point3 = (0.0, 0.0, 0.0)
    look: tuple[_Coord, _Coord, _Coord] = (0.0, 0.0, 0.0)
    coupling: Literal["rigid", "far"] = "rigid"
    moving: FrameMoving | None = None

    @model_serializer(mode="wrap")
    def _omit_defaults(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if self.parent == WORLD_FRAME:
                data.pop("parent", None)
            if tuple(self.at) == (0.0, 0.0, 0.0):
                data.pop("at", None)
            if tuple(self.look) == (0.0, 0.0, 0.0):
                data.pop("look", None)
            if self.coupling == "rigid":
                data.pop("coupling", None)
        return _omit_none(data, "moving")


class World(_IRModel):
    """A scene's world: members at positions, the named viewpoints that are
    its coverage, and its travel (ADR 0009).

    >>> world = World(members=[
    ...     WorldMember(kind="character", id="jerry", store="characters", ref="jerry", at=(-0.45, 0.65, 1.6), height=1.75),
    ...     WorldMember(kind="prop", id="wheel", store="props", ref="wheel", attached=Attachment(to="jerry")),
    ... ], viewpoints={"two_shot": Viewpoint(at=(0.0, 0.0, 0.0))})
    >>> [m.id for m in world.members], sorted(world.viewpoints)
    (['jerry', 'wheel'], ['two_shot'])
    """

    members: list[WorldMember] = Field(default_factory=list)
    viewpoints: dict[str, Viewpoint] = Field(default_factory=dict)
    travel: Travel | None = None
    #: The frames of reference, ``{name: Frame}``; ``world`` is the implicit
    #: root and a travel with a ``speed`` adds ``vehicle``.
    frames: dict[str, Frame] = Field(default_factory=dict)

    def all_frames(self) -> dict[str, Frame]:
        """The declared frames plus the one a ``travel`` with a ``speed`` is
        sugar for (``vehicle``, moving along the travel's direction).

        >>> World(travel=Travel(speed=4.0)).all_frames()["vehicle"].moving.speed
        4.0
        """
        frames = dict(self.frames)
        if self.travel is not None and self.travel.speed is not None:
            frames[VEHICLE_FRAME] = Frame(
                moving=FrameMoving(
                    direction=self.travel.direction, speed=self.travel.speed
                )
            )
        return frames

    def default_frame(self) -> str:
        """The frame a member or viewpoint is in when it names none: the
        travel's ``vehicle`` (members ride it) when there is one, else the world.

        >>> World().default_frame(), World(travel=Travel(speed=1.0)).default_frame()
        ('world', 'vehicle')
        """
        if self.travel is not None and self.travel.speed is not None:
            return VEHICLE_FRAME
        return WORLD_FRAME

    @model_validator(mode="after")
    def _frames_are_a_tree(self) -> "World":
        sugar = self.travel is not None and self.travel.speed is not None
        if sugar and VEHICLE_FRAME in self.frames:
            raise ValueError(
                f"`frames.{VEHICLE_FRAME}` is declared and so is a `travel` with a "
                f"`speed`, which already is the `{VEHICLE_FRAME}` frame. Keep one: "
                f"drop the travel's `speed` (the travel then only holds the streams) "
                f"and put the motion in `frames.{VEHICLE_FRAME}.moving`."
            )
        names = {WORLD_FRAME, *self.all_frames()}
        things = {m.id for m in self.members} | {
            st.id for st in (self.travel.streams if self.travel is not None else ())
        }
        clash = sorted(set(self.frames) & things)
        if clash:
            raise ValueError(
                f"{clash} names both a frame and a member or stream: an action on "
                "`<name>:at_x` could mean either. Rename the frame."
            )
        for name, frame in self.frames.items():
            if not name or "/" in name or name == WORLD_FRAME:
                raise ValueError(
                    f"frame name {name!r}: a bare identifier other than "
                    f"{WORLD_FRAME!r} (the implicit root), please."
                )
            if frame.parent not in names:
                raise ValueError(
                    f"frame {name!r} has parent {frame.parent!r}, which is not a "
                    f"frame; the frames are {sorted(names)}."
                )
        for name in self.frames:
            seen, cur = [], name
            while cur != WORLD_FRAME:
                if cur in seen:
                    raise ValueError(
                        "frames form a cycle: " + " -> ".join([*seen, cur]) + ". "
                        "Each frame's `parent` must lead to `world`."
                    )
                seen.append(cur)
                cur = self.all_frames()[cur].parent

        def check(where: str, frame: str | None) -> None:
            if frame is not None and frame not in names:
                raise ValueError(
                    f"{where} is `in: {frame}`, which is not a frame; the frames "
                    f"are {sorted(names)}. Declare it under `world.frames`."
                )

        for m in self.members:
            check(f"world member {m.id!r}", m.frame)
            for plane, frame in (m.planes or {}).items():
                check(f"world member {m.id!r} plane {plane!r}", frame)
        for vname, vp in self.viewpoints.items():
            check(f"viewpoint {vname!r}", vp.frame)
        for stream in self.travel.streams if self.travel is not None else ():
            check(f"stream {stream.id!r}", stream.frame)
        return self

    @model_validator(mode="after")
    def _members_are_a_set(self) -> "World":
        seen: dict[str, int] = {}
        for m in self.members:
            seen[m.id] = seen.get(m.id, 0) + 1
        dupes = sorted(k for k, n in seen.items() if n > 1)
        if dupes:
            raise ValueError(f"world members with duplicate ids: {dupes}.")
        for m in self.members:
            hops, host = 0, m
            while host.attached is not None:
                nxt = seen.get(host.attached.to)
                if nxt is None:
                    raise ValueError(
                        f"world member {host.id!r} is attached to {host.attached.to!r}, "
                        "which is not a member."
                    )
                host = next(x for x in self.members if x.id == host.attached.to)
                hops += 1
                if hops > len(self.members):
                    raise ValueError(
                        f"world member {m.id!r}: its attachments form a cycle."
                    )
        for name, vp in self.viewpoints.items():
            if not name or "/" in name:
                raise ValueError(f"viewpoint name {name!r}: a bare identifier, please.")
        return self

    @model_serializer(mode="wrap")
    def _omit_unset(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if not self.viewpoints:
                data.pop("viewpoints", None)
            if not self.frames:
                data.pop("frames", None)
        return _omit_none(data, "travel")


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


class ExtensionAction(_ActionBase):
    """An action of a kind the core does not define: the IR's one open member.

    The schema's ``Action`` union selects this for any ``kind`` other than the
    core's (ADR 0001 decision 2). When a genre has REGISTERED that kind
    (:func:`an.genres.registry.register_action_kind`), validating a document
    yields the registered model instead — a ``PlayAction`` for ``kind: play`` —
    so code downstream sees typed actions. Before registration the action
    stays an ``ExtensionAction``: its fields are kept as extras and round-trip
    byte for byte, and :meth:`resolved` (called by ``flatten``, ``an validate``
    and the compiler) refuses it naming the genre that provides it.

    Every genre's action model subclasses this, which is what lets a typed
    instance sit in the union and serialize with its own fields.

    >>> ExtensionAction(kind="wave", target="flag").model_dump()
    {'name': None, 'kind': 'wave', 'target': 'flag'}
    """

    kind: str

    def __init__(self, /, **data: Any) -> None:
        if type(self) is ExtensionAction:
            registered = action_kind(data.get("kind"))  # type: ignore[arg-type]
            if registered is not None and registered.model is not ExtensionAction:
                # The validator below would hand back ANOTHER model, which
                # `__init__` cannot return (review-244 N1): say what works.
                raise TypeError(
                    f"kind {data.get('kind')!r} is registered with its own model, "
                    f"{registered.model.__name__}: construct that, or call "
                    "ExtensionAction.model_validate(...) to get it from a dict"
                )
        super().__init__(**data)

    @model_validator(mode="wrap")
    @classmethod
    def _as_registered_kind(cls, data: Any, handler: Any) -> Any:
        """A registered kind validates to its own model; anything else stays open."""
        if cls is ExtensionAction:
            if isinstance(data, dict):
                registered = action_kind(data.get("kind"))  # type: ignore[arg-type]
                if registered is not None and registered.model is not cls:
                    return registered.model.model_validate(data)
            elif type(data) is ExtensionAction:
                return data.resolved(strict=False)
        return handler(data)

    def resolved(self, *, strict: bool = True) -> "ExtensionAction":
        """This action as its registered model.

        A typed instance is returned as is. A bare ``ExtensionAction`` is
        validated by the model its kind registered — or, unregistered, raises
        :class:`~an.genres.registry.UnregisteredKindError` (``strict``) or
        comes back unchanged (``strict=False``).
        """
        if type(self) is not ExtensionAction:
            return self
        registered = action_kind(self.kind)
        if registered is None or registered.model is ExtensionAction:
            if strict:
                raise unregistered_action_kind(self.kind)
            return self
        return registered.model.model_validate(self.model_dump(exclude_unset=True))


def unregistered_action_kind(kind: str, *, where: str = "") -> Exception:
    """The error for an action ``kind`` no loaded genre registered.

    It names the installed genres whose declaration provides the kind, read
    without loading them (:func:`an.genres.providers_of`).
    """
    from an.genres import providers_of  # lazy: discovery reads entry points
    from an.genres.registry import UnregisteredKindError, action_kind_names

    return UnregisteredKindError(
        "action kind",
        kind,
        known=action_kind_names(),
        providers=providers_of(kind, registry="action kinds"),
        where=where,
    )


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


#: The ``kind`` of every action the core defines (the static union members).
CORE_ACTION_KINDS: tuple[str, ...] = (
    "set",
    "tween",
    "sequence",
    "parallel",
    "delay",
    "loop",
)

#: The union tag of the open member.
EXTENSION_TAG: str = "extension"


def _action_tag(value: Any) -> str:
    """The union member for ``value``: its own ``kind`` if core, else the open one."""
    kind = (
        value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    )
    return kind if kind in CORE_ACTION_KINDS else EXTENSION_TAG


#: Every action: the core kinds plus :class:`ExtensionAction` for any other
#: ``kind`` (a registered genre kind validates to its own model through it).
#: ``SerializeAsAny`` makes a typed genre instance (a ``PlayAction``) serialize
#: with its own fields rather than the open member's.
Action = Annotated[
    Union[
        Annotated[SetAction, Tag("set")],
        Annotated[TweenAction, Tag("tween")],
        Annotated[SequenceAction, Tag("sequence")],
        Annotated[ParallelAction, Tag("parallel")],
        Annotated[DelayAction, Tag("delay")],
        Annotated[LoopAction, Tag("loop")],
        Annotated[SerializeAsAny[ExtensionAction], Tag(EXTENSION_TAG)],
    ],
    Discriminator(_action_tag),
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


#: One delivery cue of a dialogue line's ``direction`` (an#209): words, spaces,
#: apostrophes, hyphens — ``excited``, ``clears throat``, ``in a hurry``.
_DIRECTION_CUE_RE = re.compile(r"[\w'][\w' -]*")


class Dialogue(_IRModel):
    """One line of spoken dialogue.

    ``start`` and ``duration`` are None until the audio pipeline runs (TTS
    gives us a real duration); the pipeline stamps them then, deriving
    ``start`` from the author's ``pause`` / ``at`` (:meth:`planned_start`).
    """

    speaker: str  # the entity id this line belongs to
    text: str
    voice_ref: str | None = None  # key in the voices store; None = default
    start: Seconds | None = None
    duration: Seconds | None = None
    emotion: str | None = None
    #: How strongly ``emotion`` shows, 0..1 (an#253): ``maya [angry 0.4]: …``
    #: in ``scene.md``, a typed parameter on the (b-name) emotion. ``None`` is
    #: full strength, and is omitted from JSON.
    emotion_intensity: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False
    )
    viseme_track: VisemeTrack | None = None
    #: The provider's word timings, line-relative; ``None`` when the provider
    #: has none (offline, Rhubarb) or the line was stamped before an#96.
    word_timings: list[WordTimingIR] | None = None
    audio_ref: str | None = None  # mall["audio"] key (content-hash of TTS input)
    viseme_ref: str | None = None  # mall["visemes"] key (content-hash of lipsync input)
    #: Stamped by voice leveling (an#315): ``{"source": <the synthesized
    #: line's audio_ref>, "gain_db": <its voice's gain>}`` when ``audio_ref``
    #: is the leveled audio. ``None`` — unleveled — is omitted from JSON.
    leveled: dict | None = None
    #: DERIVED (an#397): seconds from the line's start to the end of its
    #: AUDIBLE speech — its take's own trailing silence left out — stamped
    #: with ``duration`` from the line's audio. The next line's ``pause`` counts
    #: from here (a line with no pause still follows the whole take).
    #: ``None`` (silent audio, a line its voice's ``trim_silence`` already cut to
    #: the tail the author keeps, a line stamped before an#397) counts from the
    #: end of ``duration``, as before. Never written to JSON: it is read off
    #: the line's stored audio on every pass (the audio pipeline, and a render
    #: that skips synthesis), so ``scene.json`` and its fixtures do not change.
    spoken: Seconds | None = Field(default=None, exclude=True)
    #: Seconds of silence before this line, after the previous line's speech
    #: ends (the shot start, for the first line) — ``(pause 1.5)`` in ``scene.md``.
    pause: Seconds | None = Field(default=None, ge=0, allow_inf_nan=False)
    #: Where this line starts, in SHOT seconds, whatever came before it —
    #: ``(at 3.0)`` in ``scene.md``. ``start`` is what the audio pipeline
    #: DERIVES from ``at``/``pause`` on every pass; these two are what the
    #: author wrote (an#187).
    at: Seconds | None = Field(default=None, ge=0, allow_inf_nan=False)
    #: How the line is DELIVERED — cues such as ``["excited"]`` or
    #: ``["sighs", "annoyed"]``, ``{excited}`` in ``scene.md`` (an#209). A TTS
    #: model that takes inline audio tags (ElevenLabs v3/v4) receives them as
    #: ``[excited] Hi!``; others ignore them. Never part of ``text``, so
    #: captions and lip-sync alignment never see a cue.
    direction: list[str] | None = None

    @field_validator("direction")
    @classmethod
    def _clean_direction(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cues = [str(c).strip() for c in value]
        bad = [c for c in cues if not _DIRECTION_CUE_RE.fullmatch(c)]
        if bad:
            raise ValueError(
                f"direction cue(s) {bad} are not cues: a cue is words, spaces, "
                "apostrophes and hyphens (`excited`, `clears throat`), with no "
                "brackets — the provider adds its own"
            )
        return cues or None

    @model_validator(mode="after")
    def _one_timing(self) -> "Dialogue":
        for key in ("pause", "at"):  # -0.0 would be written `(pause -0)`
            if getattr(self, key) == 0:
                object.__setattr__(self, key, 0.0)
        if self.pause is not None and self.at is not None:
            raise ValueError(
                f"dialogue line {self.text!r} sets both `pause` and `at`; a line "
                "starts either a pause after the previous line or at a shot time, "
                "not both — keep one"
            )
        return self

    def planned_start(self, cursor: float) -> float:
        """Where this line starts, given the previous line ends at ``cursor``.

        The one rule the audio pipeline stamps into ``start`` and `an validate`
        lays lines out by: ``at`` if set, else ``cursor + pause``. A ``start``
        on a line never synthesized (no ``audio_ref``) was authored — the
        spelling of ``at`` before an#187 — and counts as one; a synthesized
        line's ``start`` is the pipeline's own stamp, re-derived here.

        >>> Dialogue(speaker="a", text="bye", pause=1.5).planned_start(0.8)
        2.3
        >>> Dialogue(speaker="a", text="bye", at=4.0).planned_start(0.8)
        4.0
        >>> Dialogue(speaker="a", text="bye").planned_start(0.8)
        0.8
        """
        if self.at is not None:
            return float(self.at)
        if self.pause is None and self.start is not None and self.audio_ref is None:
            return float(self.start)
        return float(cursor) + float(self.pause or 0.0)

    @model_serializer(mode="wrap")
    def _omit_unset_timing(self, handler):
        """Serialize ``pause``/``at`` out of existence when unset.

        `AssetRef._omit_unset_stage`'s rule: every committed ``ir/scene.json``
        predates these fields, and a defaulted ``null`` on every line would
        rewrite all of them on the next ``an sync``.
        """
        data = handler(self)
        if isinstance(data, dict):
            for key in ("pause", "at", "direction", "leveled", "emotion_intensity"):
                if getattr(self, key) is None:
                    data.pop(key, None)
        return data


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
    - ``wipe`` — overlaps like a dissolve, but a hard edge sweeps across the
      frame in ``direction`` (the way the edge travels: ``left`` brings this
      shot in from the right), this shot on the side it has passed (an#390).
      The edge stands where a dissolve's mix would: ``(j + 1) / (k + 1)`` of
      the way across on overlap frame ``j`` of ``k``. Not on the first shot.
    """

    kind: Literal["cut", "fade", "dissolve", "wipe"] = "cut"
    duration: Seconds = Field(default=DEFAULT_TRANSITION_DURATION, ge=0)
    color: str = DEFAULT_TRANSITION_COLOR
    #: A ``wipe``'s direction; omitted from a dump for every other kind.
    direction: Literal["left", "right", "up", "down"] = "left"
    #: Time passes across this transition (catalogue C1): what is absent from the
    #: shots before it is not missing, it left in the meantime. Omitted from a
    #: dump unless set.
    time_jump: bool = False

    @model_serializer(mode="wrap")
    def _direction_only_for_a_wipe(self, handler):
        data = handler(self)
        if isinstance(data, dict):
            if self.kind != "wipe":
                data.pop("direction", None)
            if not self.time_jump:
                data.pop("time_jump", None)
        return data

    @model_validator(mode="after")
    def _hex_color(self) -> "Transition":
        if not _HEX_COLOR.fullmatch(self.color):
            raise ValueError(f"transition color must be '#rrggbb'; got {self.color!r}")
        return self


class CueAnchor(_IRModel):
    """A sound cue's time, taken from the picture (an#317): when a node reaches a frame row or column.

    ``when`` is a node path in a stage shot (``crawl/line_7``: a text block's
    unit, a prop, a plane); ``reaches`` is ``{"y": px}`` or ``{"x": px}`` in
    the frame's pixels (0 at the top or left), crossed in either direction by
    the node's on-screen centre — the camera, parallax and a crawl's tilt
    included. Resolved when the film is laid out, never written back into the
    scene: a layout change moves the sound with the picture. ``offset`` is
    added after. ``shot`` names the shot to look in, for a cue in
    ``meta.sounds`` (default: the first shot that has the node).

    >>> CueAnchor(when="crawl/line_7", reaches={"y": 840}).axis
    ('y', 840.0)
    """

    when: str
    reaches: dict[str, float]
    offset: float = 0.0
    shot: str | None = None

    @model_validator(mode="after")
    def _one_axis(self) -> "CueAnchor":
        if len(self.reaches) != 1 or next(iter(self.reaches)) not in ("x", "y"):
            raise ValueError(
                f"`reaches` names one frame axis, x or y, got {dict(self.reaches)!r}"
            )
        return self

    @property
    def axis(self) -> tuple[str, float]:
        """``(axis, pixels)``."""
        ((axis, value),) = self.reaches.items()
        return axis, float(value)


class CueUntil(_IRModel):
    """Where a sound cue ends: at another cue's start, plus ``offset`` (an#317).

    ``cue`` is the ``sound`` key of a cue in the same list (the shot's, or
    ``meta.sounds``); the first such cue is meant.
    """

    cue: str
    offset: float = 0.0


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
    #: Seconds, or a :class:`CueAnchor` resolved from the picture when the film
    #: is laid out (an#317).
    at: Annotated[Seconds, Field(ge=0)] | CueAnchor = 0.0
    #: Ends the cue at another cue's start (:class:`CueUntil`), instead of a
    #: fixed ``duration``.
    until: CueUntil | None = None
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


class VoiceLoudness(_IRModel):
    """One loudness for every voice of the film (an#315).

    TTS voices arrive at very different levels (a 19 dB spread measured on one
    episode). Set, the render levels each voice: its integrated loudness over
    ALL its lines (EBU R128), one gain to ``target_lufs`` (plus the voice
    document's ``loudness_offset_db``), peaks held at ``peak_db`` dBFS by a
    lookahead limiter — derived audio, content-keyed, never re-synthesised
    (:mod:`an.audio.loudness`). Unset, the default, levels nothing.

    >>> VoiceLoudness().target_lufs, VoiceLoudness().peak_db
    (-16.0, -1.5)
    >>> VoiceLoudness.model_validate(-20).target_lufs  # a bare number is the target
    -20.0
    """

    #: The level every voice is brought to, LUFS (-16: speech for the web;
    #: -23: EBU R128 broadcast).
    target_lufs: float = Field(default=-16.0, ge=-40.0, le=-5.0)
    #: The highest a sample may reach after the gain, dBFS.
    peak_db: float = Field(default=-1.5, ge=-12.0, le=0.0)

    @model_validator(mode="before")
    @classmethod
    def _a_number_is_the_target(cls, data):
        if isinstance(data, (int, float)) and not isinstance(data, bool):
            return {"target_lufs": data}
        return data


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
    #: A ``str`` in the schema (ADR 0001 decision 2): any name a renderer
    #: registered (``an.adapters.register_renderer``), checked by ``an
    #: validate``. ``cutout`` stays the persisted default (decision 9).
    renderer: str = "cutout"
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
    #: This shot's **policy** (an#348): per aspect, the methods it prefers in
    #: order, over the style pack's (``StylePack.policy``) and under an author's
    #: request — ``{"locomotion": ["loco.glide"]}``. ``None``: the style's.
    policy: dict[str, Any] | None = None
    #: This shot's **viewpoint** onto the scene's world (ADR 0009): the name
    #: of one of ``world.viewpoints`` or an inline :class:`Viewpoint`. ``None``
    #: (the default, and every document written before the world existed)
    #: means the shot is placed by hand, as it always was. Omitted from JSON
    #: when unset, like ``policy``.
    viewpoint: str | Viewpoint | None = None
    #: Items held by something for a span (:class:`Weld`); omitted when empty.
    welds: list[Weld] = Field(default_factory=list)
    #: Joints between this shot's bodies (:class:`JointSpec`, ADR 0008); the
    #: ``solve`` compile pass keeps them at every frame. Omitted when empty.
    joints: list[JointSpec] = Field(default_factory=list)
    #: How this shot is solved (:class:`SolveSettings`): mode, gravity and
    #: damping over the style pack's. ``None`` (omitted): the defaults.
    solve: SolveSettings | None = None

    @field_validator("policy")
    @classmethod
    def _policy_shape(cls, v: Any) -> Any:
        from an.semantic.entries import check_policy_block

        return check_policy_block(v)

    @model_serializer(mode="wrap")
    def _omit_unset_assembly(self, handler):
        """Serialize ``transition``/``sounds``/``policy`` out of existence when unset.

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
            if self.policy is None:
                data.pop("policy", None)
            if self.viewpoint is None:
                data.pop("viewpoint", None)
            if not self.welds:
                data.pop("welds", None)
            if not self.joints:
                data.pop("joints", None)
            if self.solve is None:
                data.pop("solve", None)
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
    #: Like :attr:`Shot.renderer`: a registered renderer's name.
    default_renderer: str = "cutout"
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
    #: leg and pupil colours, the environment presets' sky and ground — and SVG
    #: art whose descriptor tags its colours by role (`colour_roles`, written by
    #: `an character new`). Untagged art is never inferred (inferring a role
    #: from a pixel is what produced an#99's wrong-tone lid); a rig a pack
    #: cannot reach is WARNED about by name at compile.
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
    #: How the film ENDS (an#389): a ``fade`` to its ``color`` over its
    #: ``duration``, on the last shot's last frames (the film's length is
    #: unchanged, and its final frame is the colour; the sound fades with it).
    #: ``None`` (or a ``cut``) ends on the last frame as drawn. A dissolve has
    #: nothing to dissolve into, so it is refused.
    closing_transition: Transition | None = None

    @field_validator("closing_transition")
    @classmethod
    def _closing_is_a_fade(cls, t: Transition | None) -> Transition | None:
        if t is not None and t.kind in ("dissolve", "wipe"):
            raise ValueError(
                f"closing_transition: a {t.kind} has nothing to {t.kind} into at the "
                "film's end; use a fade (to a colour) or a cut"
            )
        return t

    #: One loudness for every voice (:class:`VoiceLoudness`, an#315); ``None``
    #: — the default — levels nothing, and is omitted from JSON.
    voice_loudness: VoiceLoudness | None = None

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
        # `voice_loudness` likewise (an#315).
        if isinstance(data, dict) and self.voice_loudness is None:
            data.pop("voice_loudness", None)
        # `closing_transition` likewise (an#389).
        if isinstance(data, dict) and self.closing_transition is None:
            data.pop("closing_transition", None)
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
    #: The scene's **world** (ADR 0009): its members at world positions, its
    #: named viewpoints and its travel. ``None`` — the default, and every
    #: document written before it existed — is no world at all: every shot is
    #: placed by hand. Omitted from JSON when unset (the `stage` rule), so no
    #: stored scene and no schema version moves.
    world: World | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_world(self, handler):
        data = handler(self)
        if isinstance(data, dict) and self.world is None:
            data.pop("world", None)
        return data


# -----------------------------------------------------------------------------
# The core's entity kinds (``AssetRef.kind``). A genre adds its own
# (:class:`an.genres.EntityKind`); the cut-out genre adds ``character``.
# -----------------------------------------------------------------------------

#: The property space a 2D stage engine's node lives in (:mod:`an.timing.spaces`).
STAGE_NODE_SPACE: str = "stage.node"


def _prop_swap_declaration(entity: Any, mall: Any) -> Any:
    """The ``prop`` kind's swap declaration: a text block's ``text`` set
    (an#341), nothing for any other prop. The stage owns text, so it is
    imported when a shot is compiled or validated, never with the IR."""
    from an.stage.text_layout import text_swap_declaration

    return text_swap_declaration(entity, mall)


#: How long a specimen shot runs (``an library sheet`` draws its first frame).
SPECIMEN_DURATION: float = 0.5
#: The id of a specimen shot.
SPECIMEN_SHOT_ID: str = "specimen"


def stage_specimen(ref: AssetRef) -> Shot:
    """A short shot showing the one stage entity ``ref`` casts, on its own (an#347).

    >>> stage_specimen(AssetRef(kind="prop", id="lamp", store="props", ref="lamp")).entities[0].id
    'lamp'
    """
    return Shot(
        id=SPECIMEN_SHOT_ID,
        renderer="stage",
        duration=SPECIMEN_DURATION,
        entities=[ref],
    )


CORE_ENTITY_KINDS: tuple[EntityKind, ...] = (
    EntityKind(
        "environment",
        space=STAGE_NODE_SPACE,
        store="environments",
        description="the set / background: planes, with parallax, drawn behind",
        specimen=stage_specimen,
    ),
    EntityKind(
        "prop",
        space=STAGE_NODE_SPACE,
        store="props",
        description="a prop or piece of set dressing; also stroked paths and text blocks",
        swap_declaration=_prop_swap_declaration,
        specimen=stage_specimen,
    ),
    EntityKind(
        "voice",
        store="voices",
        description="a voice the audio pipeline speaks with; draws nothing",
    ),
)

for _kind in CORE_ENTITY_KINDS:
    if entity_kind(_kind.name) is None:
        register_entity_kind(_kind, owner=CORE_OWNER)


# The cut-out genre's action models moved to `cutan` (an#225): `PlayAction` and
# `ExpressionAction` are DEFINED beside their action kinds there. These names keep
# resolving (with a MovedModuleWarning) while the genre package is installed.
from an._shims import moved_names as _moved_names  # noqa: E402

__getattr__ = _moved_names(
    __name__,
    {
        "PlayAction": "cutan.characters.registration:PlayAction",
        "ExpressionAction": "cutan.expression.registration:ExpressionAction",
        "DFLT_EXPRESSION_BLEND_S": "cutan.expression.registration:DFLT_EXPRESSION_BLEND_S",
    },
)
