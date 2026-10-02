"""The rig model the stage draws: bones, slots, skins and attachments.

A *rig* is the stage's own idea (a skeleton of bones, draw-ordered slots bound to
them, and skins mapping slots to drawable attachments); props use it as well as
characters. It lives in ``an.stage`` so the stage compiler can build a rig
without importing any genre; a genre's descriptor (``cutan``'s
``CharacterDescriptor``) is composed from these types.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from an.ir.assets import AssetSource

#: Canonical character viewBox: 1024x1024 with feet near y≈980. All parts
#: inherit this viewBox at export so PixiJS can use the SVG's intrinsic
#: viewBox without a calibration step.
DEFAULT_VIEW_BOX: tuple[int, int, int, int] = (0, 0, 1024, 1024)


class RigModel(BaseModel):
    """Common config: forward-compatible reads, strict writes."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Bone(RigModel):
    """A skeleton joint with a local transform relative to its parent.

    >>> b = Bone(name="head", parent="torso", x=0, y=-260, pivot="neck")
    >>> b.parent
    'torso'
    """

    name: str
    parent: Optional[str] = None
    x: float = 0.0
    y: float = 0.0
    rotation_deg: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    #: Optional pivot name — must match a circle in the SVG ``skeleton`` group.
    pivot: Optional[str] = None


class Slot(RigModel):
    """A draw-order slot bound to a bone, displaying one attachment at a time.

    >>> s = Slot(name="mouth", bone="head", draw_order=7, attachment="mouth_x")
    >>> s.attachment
    'mouth_x'
    """

    name: str
    bone: str
    draw_order: int = 0
    #: Default attachment name; the active attachment can change at runtime
    #: via animation tracks targeting ``slot:<name>.attachment``.
    attachment: Optional[str] = None


class Attachment(RigModel):
    """A drawable: an SVG path + anchor point (in 0..1 per-axis units).

    >>> a = Attachment(path="parts/head.svg", anchor=(0.5, 0.78))
    >>> a.anchor
    (0.5, 0.78)
    """

    path: str
    #: Anchor in 0..1 per-axis units (Pixi's Sprite.anchor convention).
    anchor: tuple[float, float] = (0.5, 0.5)

    #: Offset from the slot's bone, in view_box units.
    #:
    #: **This is where a part's position lives**, and it is the reference data
    #: model's answer, not an invention: DragonBones puts it in
    #: ``display.transform``, Spine in the region attachment's ``{x, y}``, and
    #: in both the *slot* carries no transform at all. It is what lets five face
    #: parts share one ``head`` bone and still land in different places — before
    #: this field they all stacked on the bone, because the descriptor had no
    #: way to say otherwise and the compiler used hardcoded literals instead.
    x: float = 0.0
    y: float = 0.0
    #: The size the part draws at, in **view_box units** — the rig's units,
    #: the ones ``x``/``y`` and the bones use (an#220). **A declared size
    #: wins** over the art's own extent, as ``Plane.size`` does for plates.
    #: Unset, the art's own extent is the size: an SVG's ``width``/``height``
    #: (else its viewBox), a raster's PIXEL count — so a PNG carved at one
    #: pixel per unit needs nothing, and one carved at any other scale
    #: declares its size here instead of being resampled. The aspect is the
    #: art's, always (an#74): with ONE of the two declared the other follows
    #: the art's aspect; with both, the art is contained in the box
    #: (uniformly scaled to fit, never stretched) and `an character
    #: validate` says when the two aspects disagree. See
    #: :func:`attachment_box`.
    width: Optional[float] = None
    height: Optional[float] = None
    #: Where THIS part's art came from, when it is not the descriptor's
    #: ``source`` — a character composed from several clips, or a carved head
    #: on a CC0 body, credits each (an#220). ``None`` = the descriptor's
    #: ``source`` covers it. `an credits` lists every one; an all-rights-
    #: reserved part makes the render NOT PUBLISHABLE like any other.
    #: Omitted from the stored document when unset.
    source: AssetSource | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_source(self, handler):
        """``source: null`` is written out of existence, as `Plane.source` is:
        an attachment with no source of its own is the attachment every
        stored descriptor already holds."""
        data = handler(self)
        if isinstance(data, dict) and data.get("source") is None:
            data.pop("source", None)
        return data


def attachment_box(
    width: float | None,
    height: float | None,
    art: tuple[float, float] | None,
) -> tuple[float, float] | None:
    """The box a part draws in, in view_box units: the declared size wins, the
    art's aspect is kept (an#220).

    >>> attachment_box(None, None, (40, 20))       # the art's own extent
    (40.0, 20.0)
    >>> attachment_box(120, None, (40, 20))        # width declared: height follows
    (120.0, 60.0)
    >>> attachment_box(None, 30, (40, 20))
    (60.0, 30.0)
    >>> attachment_box(120, 120, (40, 20))         # both: contained, never stretched
    (120.0, 60.0)
    >>> attachment_box(120, 90, None)              # unmeasurable art: the box as declared
    (120.0, 90.0)
    >>> attachment_box(120, None, None) is None    # nothing to take the aspect from
    True
    """
    w = float(width) if width else None
    h = float(height) if height else None
    if art is None or not (art[0] > 0 and art[1] > 0):
        return (w, h) if w and h else None
    aw, ah = float(art[0]), float(art[1])
    if w and h:
        s = min(w / aw, h / ah)
    elif w:
        s = w / aw
    elif h:
        s = h / ah
    else:
        return (aw, ah)
    return (aw * s, ah * s)


class Skin(RigModel):
    """A named outfit/variant: maps slot → {attachment_name → Attachment}.

    >>> skin = Skin(name="default", slots={"mouth": {"mouth_a": Attachment(path="parts/mouth/mouth_a.svg")}})
    >>> skin.slots["mouth"]["mouth_a"].path
    'parts/mouth/mouth_a.svg'
    """

    name: str = "default"
    slots: dict[str, dict[str, Attachment]] = Field(default_factory=dict)


def primary_slot_per_bone(desc: Any) -> dict[str, str]:
    """``{bone name: the slot that IS that bone}``, when one exists.

    Used for node nesting, which is deliberately **not** the bone hierarchy.
    The rigs here are flat by design — arms are siblings of the torso, not
    children (CLAUDE.md pillar 4) — so bone parentage decides *position* only.
    A slot nests under the primary slot of its bone when it is not that slot
    itself, which is what puts eyes and mouth under ``head`` and leaves every
    limb a direct child of the entity.

    >>> from types import SimpleNamespace as NS
    >>> primary_slot_per_bone(NS(slots=[NS(name="head", bone="head"), NS(name="mouth", bone="head")]))["head"]
    'head'
    """
    return {s.bone: s.name for s in desc.slots if s.name == s.bone}


def drawn_attachment(
    desc: Any, skin: Skin, slot: Slot
) -> tuple[str, Attachment] | None:
    """The ``(name, attachment)`` a slot draws by default, or ``None``."""
    available = skin.slots.get(slot.name) or {}
    if not available:
        return None
    name = slot.attachment if slot.attachment in available else next(iter(available))
    return name, available[name]
