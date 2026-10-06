"""The rig model the stage draws: bones, slots, skins and attachments.

A *rig* is the stage's own idea (a skeleton of bones, draw-ordered slots bound to
them, and skins mapping slots to drawable attachments); props use it as well as
characters. It lives in ``an.stage`` so the stage compiler can build a rig
without importing any genre; a genre's descriptor (``cutan``'s
``CharacterDescriptor``) is composed from these types.

Two layers live here:

- **the model**: :class:`Bone`, :class:`Slot`, :class:`Attachment`,
  :class:`Skin`, and :class:`RigDocument`, the base of every document that IS a
  rig (``PropDescriptor``, ``CharacterDescriptor``), which carries the fields
  about the rig as a whole (its declared :attr:`RigDocument.origin`);
- **the builder**: :func:`build_rig_subtree`, the ONE function that turns a rig
  document into a scene subtree for props and characters alike (an#108), with
  the helpers a genre needs to call it (:func:`part_probe`,
  :func:`raster_digest`, :func:`art_src`, :func:`bone_positions`,
  :func:`rig_origin`). Public since an#338: before it, ``cutan`` reached the
  builder through private names of the stage compiler, which a second genre
  could not have done. The compiler re-exports the old private spellings.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, migrate
from an.stage.raster import art_size, is_raster, short_digest, versioned_src
from an.stage.serialize import (
    AssetJSON,
    AssetResolutionJSON,
    NodeJSON,
    TransformJSON,
    VisualJSON,
)

if TYPE_CHECKING:
    from an.ir.schema import AssetRef

#: Canonical character viewBox: 1024x1024 with feet near y≈980. All parts
#: inherit this viewBox at export so PixiJS can use the SVG's intrinsic
#: viewBox without a calibration step.
DEFAULT_VIEW_BOX: tuple[int, int, int, int] = (0, 0, 1024, 1024)


class RigModel(BaseModel):
    """Common config: forward-compatible reads, strict writes."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


#: A finite float: pydantic serializes ``inf``/``nan`` to JSON ``null``, which
#: then fails to re-validate, so a document written with one is corrupt one way
#: (the rule ``StagePlacement.at`` follows, an#108 review M-1).
_Finite = Annotated[float, Field(allow_inf_nan=False)]

#: The fields :class:`RigDocument` adds, each written out of the stored
#: document when unset (:func:`omit_unset_rig_fields`), so every descriptor
#: that never set one reads back, and hashes, as it did before the field existed.
RIG_DOCUMENT_OPTIONAL_FIELDS: tuple[str, ...] = ("origin",)


def omit_unset_rig_fields(data: Any) -> Any:
    """Drop every unset :class:`RigDocument` field from a dumped document, in place.

    A subclass that declares its own ``model_serializer`` REPLACES the base's
    (pydantic keeps one per model), so it must call this on its output, or an
    unset ``origin`` reaches every stored descriptor as ``null``.

    >>> omit_unset_rig_fields({"name": "lamp", "origin": None})
    {'name': 'lamp'}
    >>> omit_unset_rig_fields({"origin": [512.0, 1010.0]})
    {'origin': [512.0, 1010.0]}
    """
    if isinstance(data, dict):
        for name in RIG_DOCUMENT_OPTIONAL_FIELDS:
            if data.get(name) is None:
                data.pop(name, None)
    return data


class RigDocument(RigModel):
    """The base of every document that IS a rig: ``PropDescriptor``, ``CharacterDescriptor``.

    Holds what is true of the rig as a whole, not of one bone or slot (which is
    why it is not :class:`RigModel`, the base of :class:`Bone` and the others
    as well). Every field here is omitted from the stored document when unset.

    >>> RigDocument(origin=(512, 1010)).origin
    (512.0, 1010.0)
    >>> RigDocument().model_dump()
    {}
    >>> RigDocument(origin=(float("inf"), 0))
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: 1 validation error for RigDocument
    ...
    """

    #: The point of the art that the entity's placement (``stage.at``) refers
    #: to, in view_box units (an#338). Unset, the rig is placed by the centre
    #: of its bones' extent (:func:`bone_extent_centre`), which is what every
    #: rig did before the field existed; a prop declares its foot (a tripod's,
    #: a figurine's stand) so it stands where it is put whatever its extent.
    origin: tuple[_Finite, _Finite] | None = None

    @model_serializer(mode="wrap")
    def _omit_unset_rig_fields(self, handler):
        return omit_unset_rig_fields(handler(self))


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


# -----------------------------------------------------------------------------
# The rig builder: a rig document -> a scene subtree (props and characters alike)
# -----------------------------------------------------------------------------


#: Scene-graph pixels spanned by a descriptor's full ``view_box`` height.
#:
#: The single number that maps descriptor space to scene space. One uniform
#: factor ``k = SCENE_PX_PER_VIEW_BOX / view_box_height`` scales bone positions
#: and part extents alike — uniform by construction, so the compiler cannot
#: violate the invariant that aspect ratio is intrinsic to the art (an#74).
#:
#: 345 is a calibration, not a preference. It is what reproduces the framing the
#: seven deleted ``_SVG_*_SIZE`` constants hand-tuned: at k = 345/1024 = 0.3369,
#: ``saturated-rig``'s own art gives torso 107.8x129.4 against the old 110x130,
#: legs 37.7x118.6 against 38x120. The constants were an approximation of
#: exactly this product, which is the evidence that the rig should have been
#: driving it all along.
SCENE_PX_PER_VIEW_BOX: float = 345.0

#: The fit policy every compiled sprite carries. Named rather than inlined so
#: the one place that decides "the art keeps its shape" is greppable.
CONTAIN_FIT: str = "contain"


#: The `assets.textures` `src` prefix a rig's art is addressed under, which is
#: also the mall store that resolves it (`render.ASSET_SRC_PREFIX_TO_STORE`).
#: A parameter rather than a literal because the rig builder is the same code
#: for a character and for a prop, and the store is the ONLY thing that differs
#: about where their art lives. Two hardcoded copies of `"characters/"` — the
#: `src` builder and the probe's own — reached three call sites, and that is
#: what made "a prop is a rig too" read as a rewrite instead of an argument
#: (an#108).
CHARACTER_ART_PREFIX: str = "characters/"

#: The same, for props. Both are keys of `render.ASSET_SRC_PREFIX_TO_STORE`,
#: which is what decides where the staging step copies the art from.
PROP_ART_PREFIX: str = "props/"


def art_src(ref: str, rel_path: str, *, art_prefix: str = CHARACTER_ART_PREFIX) -> str:
    """Path used inside the runtime dir, relative to ``index.html``.

    >>> art_src("maya", "parts/head.svg")
    'characters/maya/parts/head.svg'
    >>> art_src("lamp", "parts/body.svg", art_prefix="props/")
    'props/lamp/parts/body.svg'
    """
    return f"{art_prefix}{ref}/{rel_path}"


def _register_texture(
    textures: dict[str, AssetJSON],
    alias: str,
    src: str,
) -> str:
    """Add a texture entry if not already present; return ``alias``."""
    if alias not in textures:
        textures[alias] = AssetJSON(src=src)
    return alias


def part_probe(
    characters_store: Mapping,
    *,
    art_prefix: str = CHARACTER_ART_PREFIX,
) -> Callable[[str], tuple[bool, tuple[float, float] | None]] | None:
    """A probe answering ``(art exists, the size it rasterises at)`` for a part.

    **Two questions, deliberately not one.** Whether the art is *there* decides
    whether the compiler declares a texture for it; whether it can be *measured*
    decides only whether the sprite's box comes from the art or from the
    runtime's fit. Collapsing them is a real bug and it was here: a degenerate
    ``<svg/>`` is unmeasurable but present, and treating that as absent made the
    part vanish from the scene silently — trading an#79's hang for exactly the
    invisible-art failure #76 exists to stop.

    Returns ``None`` when the store has no filesystem root — **not** a probe
    that answers "absent" — because a store that can answer nothing must drop
    no parts rather than all of them.

    Size is read from the SVG root's ``width``/``height``, falling back to the
    viewBox extent as a browser does — or, for PNG/JPEG/WebP art, from the
    image header (an#211): a header parse, not a render, either way. Before
    an#211 a PNG was parsed AS SVG here and the compile died on an XML error.
    """
    root = getattr(characters_store, "_root", None)
    if root is None:
        return None
    base = Path(root)
    prefix = art_prefix

    def probe(src: str) -> tuple[bool, tuple[float, float] | None]:
        if not src.startswith(prefix):
            return False, None
        path = base / src[len(prefix) :]
        if not path.is_file():
            return False, None
        try:
            return True, art_size(path)
        except (OSError, ValueError):
            # Present but unreadable or malformed. Still declared, so the
            # failure is loud at load rather than an absence nobody sees.
            return True, None

    return probe


def raster_digest(
    store: Mapping,
    *,
    art_prefix: str = CHARACTER_ART_PREFIX,
) -> Callable[[str], str | None]:
    """``digest(src)``: a short content digest for RASTER art, else ``None``.

    A raster texture is addressed by its bytes (an#211): the digest goes into
    the texture's alias, so a re-carved part is a different texture — the
    runtime's loader ignores a re-added alias on hot reload (an#155) — and a
    different compiled contract, whose hash then covers the pixels drawn. SVG
    art keeps its plain alias, which is what keeps every existing document
    byte-identical.
    """
    root = getattr(store, "_root", None)

    def digest(src: str) -> str | None:
        if root is None or not is_raster(src) or not src.startswith(art_prefix):
            return None
        path = Path(root) / src[len(art_prefix) :]
        try:
            return short_digest(path)
        except OSError:
            return None  # absent art is the probe's business, not this one's

    return digest


def bone_positions(desc: Any) -> dict[str, tuple[float, float]]:
    """Absolute ``(x, y)`` per bone, in view_box units.

    Bone transforms are parent-relative, so a bone's position is the sum along
    its parent chain. A cycle or a dangling parent stops the walk rather than
    looping — a malformed rig is #78's business, not this function's.
    """
    by_name = {b.name: b for b in desc.bones}
    out: dict[str, tuple[float, float]] = {}
    for bone in desc.bones:
        x = y = 0.0
        seen: set[str] = set()
        cursor: Bone | None = bone
        while cursor is not None and cursor.name not in seen:
            seen.add(cursor.name)
            x += cursor.x
            y += cursor.y
            cursor = by_name.get(cursor.parent) if cursor.parent else None
        out[bone.name] = (x, y)
    return out


def _record_missing_parts(
    entity: AssetRef,
    missing: list[tuple[str, str, str]],
    *,
    drawn: set[str],
    into: list[AssetResolutionJSON] | None,
) -> None:
    """Record every declared part whose art is not on disk, as a fallback.

    A skin declares an inventory, and a slot that ends up with nothing to draw
    is a hole in the picture. Recording it here routes it through the one place
    that decides what a stand-in costs: audible always, fatal under
    ``strict_assets`` (an#76). Raising from the compiler instead would put a
    second policy next to that one.

    A slot that still drew *something* — one attachment missing out of several,
    as when a rig ships open eyes but no closed ones — is reported separately
    and NOT as a fallback, because the frame is not wrong, only the inventory
    is incomplete. Conflating the two would make every rig without a blink
    refuse to render under ``strict_assets``.
    """
    if into is None or not missing:
        return
    empty = [m for m in missing if m[0] not in drawn]
    partial = [m for m in missing if m[0] in drawn]
    for slot_name, attachment, path in empty:
        into.append(
            AssetResolutionJSON(
                id=f"{entity.id}/{slot_name}",
                kind="part",
                store=entity.store,
                ref=entity.ref,
                resolved="missing",
                fallback=True,
                detail=(
                    f"slot {slot_name!r} declares attachment {attachment!r} at "
                    f"{path!r}, which is not in the store — the slot draws nothing"
                ),
            )
        )
    for slot_name, attachment, path in partial:
        into.append(
            AssetResolutionJSON(
                id=f"{entity.id}/{slot_name}",
                kind="part",
                store=entity.store,
                ref=entity.ref,
                resolved="incomplete",
                fallback=False,
                detail=(
                    f"slot {slot_name!r} is missing attachment {attachment!r} at "
                    f"{path!r}; the slot still draws, but that key cannot be swapped to"
                ),
            )
        )


def bone_extent_centre(bones: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """The DEFAULT point in view_box space that the entity's placement refers
    to, when the rig declares no :attr:`RigDocument.origin` (:func:`rig_origin`).

    >>> bone_extent_centre({"root": (512.0, 980.0), "head": (512.0, 420.0)})
    (512.0, 700.0)

    The centre of the rig's bone extent, **not** the root bone. The scene root
    positions a character on x only and leaves y at 0, so this point is what
    lands at the frame's vertical centre — and a rig whose root is its ground
    contact (the default puts it at the feet, y=980) would therefore hang its
    whole body above the placement point, head off-frame.

    Centring on the extent makes framing independent of where an author chose
    to put the root, which is a rigging decision and should not be a framing
    one. On the default rig it lands at y=700, within 20 units of the torso
    bone — i.e. it reproduces the convention the deleted `torso_y = 0.0`
    literal encoded, without hardcoding a bone name.
    """
    if not bones:
        return (0.0, 0.0)
    xs = [x for x, _ in bones.values()]
    ys = [y for _, y in bones.values()]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _field_of(desc: Any, name: str, default: Any = None) -> Any:
    """``desc.<name>`` on a model, ``desc[name]`` on a raw document."""
    if isinstance(desc, Mapping):
        return desc.get(name, default)
    return getattr(desc, name, default)


def declared_origin(desc: Any) -> tuple[float, float] | None:
    """The rig's DECLARED origin as two floats, or ``None`` when it declares none.

    ``desc`` is a model or a raw document (a mapping, as ``an validate`` reads
    it); a descriptor model that predates :class:`RigDocument`, where
    ``origin`` is an ``extra`` key (a list), is read the same way.

    >>> from types import SimpleNamespace as NS
    >>> declared_origin(NS(origin=[512, 1010])), declared_origin(NS())
    ((512.0, 1010.0), None)
    >>> declared_origin({"origin": [0, 5]})
    (0.0, 5.0)
    """
    origin = _field_of(desc, "origin")
    if origin is None:
        return None
    x, y = origin
    return (float(x), float(y))


def rig_origin(desc: Any) -> tuple[float, float]:
    """The point of the rig, in view_box units, that lands at the entity's placement.

    The ONE rule (an#338): the declared :attr:`RigDocument.origin` when the rig
    has one, else the centre of its bones' extent (:func:`bone_extent_centre`).
    :func:`build_rig_subtree` places every part relative to it, and a genre that
    reports where a rig's art reaches from its stage point (``cutan``'s
    ``stage_extent``) reads it too, so the two agree by construction.

    >>> from types import SimpleNamespace as NS
    >>> bones = [NS(name="root", parent=None, x=512, y=980), NS(name="top", parent="root", x=0, y=-560)]
    >>> rig_origin(NS(bones=bones))
    (512.0, 700.0)
    >>> rig_origin(NS(bones=bones, origin=(512, 980)))
    (512.0, 980.0)
    """
    declared = declared_origin(desc)
    if declared is not None:
        return declared
    return bone_extent_centre(bone_positions(desc))


def rig_origin_problems(desc: Any) -> list[str]:
    """What is wrong with a rig's declared origin, as warnings (an#338).

    Nothing when the rig declares none. A non-finite origin (possible only on a
    document read without :class:`RigDocument`, which refuses one) places the
    whole rig nowhere; one outside the ``view_box`` is legal (a hanging sign's
    hook can sit above its art) but is far more often a unit slip (scene pixels
    written where view_box units belong), so it is said, not refused.

    >>> from types import SimpleNamespace as NS
    >>> rig_origin_problems(NS(origin=(512, 1010), view_box=(0, 0, 1024, 1024)))
    []
    >>> rig_origin_problems(NS(origin=(512, 2000), view_box=(0, 0, 1024, 1024)))[0].startswith("origin (512.0, 2000.0) lies outside")
    True
    >>> rig_origin_problems(NS(origin=(float("nan"), 0), view_box=(0, 0, 1024, 1024)))[0][:30]
    'origin (nan, 0.0) is not finit'
    """
    try:
        origin = declared_origin(desc)
    except (TypeError, ValueError):
        return [f"origin {_field_of(desc, 'origin')!r} is not a pair of numbers [x, y]"]
    if origin is None:
        return []
    if not all(math.isfinite(v) for v in origin):
        return [f"origin {origin} is not finite: the rig would be placed nowhere"]
    view_box = tuple(_field_of(desc, "view_box") or DEFAULT_VIEW_BOX)
    vx, vy, vw, vh = view_box
    x, y = origin
    if not (vx <= x <= vx + vw and vy <= y <= vy + vh):
        return [
            f"origin {origin} lies outside the rig's view_box {view_box}: "
            "legal (a hook above the art), but usually a unit slip -- the origin "
            "is in view_box units, the units of the bones, not scene pixels"
        ]
    return []


def build_rig_subtree(
    entity: AssetRef,
    desc_data: dict[str, Any],
    *,
    textures: dict[str, AssetJSON],
    probe: Callable[[str], tuple[bool, tuple[float, float] | None]] | None = None,
    resolutions: list[AssetResolutionJSON] | None = None,
    art_prefix: str = CHARACTER_ART_PREFIX,
    descriptor_model: type,
    document_kind: DocumentKind,
    texture_srcs: Mapping[str, str] | None = None,
    digest: Callable[[str], str | None] | None = None,
) -> NodeJSON:
    """Build the scene subtree for a character, **from its descriptor's rig**.

    A part may be SVG or raster (PNG/JPEG/WebP, an#211): the probe measures
    either, and ``digest(src)`` — a content digest for raster art, ``None``
    for SVG — is appended to a raster texture's alias so the texture is
    addressed by its bytes.

    **Every swap key keeps its own geometry** (an#211). A swap re-textures the
    sprite, and the box, anchor and offset were the DEFAULT attachment's, so a
    key drawn on a different canvas was fitted into the wrong box — a closed
    mouth on a thin canvas squashed every open mouth to a fraction of a pixel.
    A key whose box, anchor or offset differs from the drawn attachment's is
    listed in ``VisualJSON.asset_geometry`` and the runtime applies it with the
    texture; a rig whose keys share a canvas emits nothing new.

    ``texture_srcs`` maps a part path to the ``src`` its texture loads from
    instead of the stored file — a style pack's recoloured art
    (:func:`_recoloured_texture_srcs`). Such a texture's alias carries a digest
    of its content, so a different recolour is a different texture (the
    runtime's loader ignores a re-added alias on hot reload, an#155). The part
    is still probed and sized from the stored file, whose geometry is the same.

    Every part's position comes from a bone, every part's extent from its own
    art, and both are scaled by one uniform factor. Nothing here is a module
    constant: the seven ``_SVG_*_SIZE`` values and the four y-offset literals
    this replaced are gone, and gutting ``bones``/``slots``/``skins``/``view_box``
    now changes the output — which it provably did not before (an#73).

    A slot whose art is not on disk is recorded in ``resolutions`` as a fallback,
    which makes it audible by default and fatal under ``strict_assets`` — the
    same treatment a missing *character* already got (an#33), now reaching
    inside the descriptor to the individual part (an#76). It is recorded rather
    than raised here because the decision belongs to one place, and that place
    is :func:`_raise_or_warn_on_asset_fallbacks`.

    ``probe(src) -> (exists, size)`` answers whether a part's art is on disk and
    what size it rasterises at. Existence decides whether a texture is declared
    at all. The sprite's box is the attachment's declared ``width``/``height``
    when it has them — **a declared size wins**, with the art's aspect kept
    (:func:`an.characters.schema.attachment_box`, an#220) — else the art's own
    extent (a raster's pixel count); failing both, the runtime's ``contain``
    fit draws the art at its natural shape — never stretched to a fabricated box.
    """
    # Two documents, one builder. `PropDescriptor` carries the same field NAMES
    # the rig maths reads — view_box, bones, slots, skins, asset_sets,
    # face_overlay — and differs only in what it seeds when they are empty, so
    # the code below never asks which kind it has (an#108).
    desc = descriptor_model.model_validate(
        migrate(dict(desc_data), kind=document_kind.name)
    )
    ref = entity.ref or entity.id
    _, _, _, view_box_height = desc.view_box
    k = SCENE_PX_PER_VIEW_BOX / float(view_box_height or 1)

    skin = desc.skins.get("default") or next(iter(desc.skins.values()), Skin())
    bones = bone_positions(desc)
    origin = rig_origin(desc)
    # Shared with `an.characters.play` so a `play` resolves against the
    # nesting the builder actually uses (an#7 review).
    nests_under = primary_slot_per_bone(desc)

    # If the head art has its own face baked in (DiceBear / hand-drawn full
    # avatars), the separate eye/brow/mouth sprites double up with the baked
    # features. Lip-sync stays audio-only for these; hand-rig for dialogue.
    # `face_overlay` is the DECLARED fact (0.3.0, an#87) — the old vendor-name
    # check on metadata.art_provenance lives on only inside the migration.
    head_has_face = not desc.face_overlay

    def _register(slot_name: str, attachment_name: str, attachment: Attachment) -> str:
        # Slot-qualified on purpose: attachment names are a PER-SLOT namespace
        # (both eye slots carry `open`/`closed`), and the old `{entity}.{name}`
        # alias space was silently first-wins on cross-slot collision.
        alias = f"{entity.id}.{slot_name}.{attachment_name}"
        src = (texture_srcs or {}).get(attachment.path)
        if src is None:
            src = art_src(ref, attachment.path, art_prefix=art_prefix)
            sha = digest(src) if digest is not None else None
            if sha:
                alias += "." + sha
                src = versioned_src(src, sha)
        else:
            alias += "." + hashlib.sha256(src.encode("ascii")).hexdigest()[:12]
        return _register_texture(textures, alias, src)

    def _box_of(attachment: Attachment) -> tuple[float, float] | None:
        # The declared box wins, keeping the art's aspect; else the art's own
        # extent (from its header) — a raster's pixel count (an#220).
        src = art_src(ref, attachment.path, art_prefix=art_prefix)
        return attachment_box(
            attachment.width,
            attachment.height,
            probe(src)[1] if probe else None,
        )

    # Every attachment in the skin is registered, not just the active one, so a
    # swap has its texture already loaded when the key changes.
    #
    # Except the ones whose art is not there. A skin declares an inventory —
    # `eye_l_closed` is in the default skin and in REQUIRED_PARTS, but the bench
    # rigs do not ship it — and declaring a texture the staging step cannot find
    # makes the render fail at load over art no node draws. Registering only
    # what resolves keeps the compiler from fabricating; reporting the gap in
    # the art package is `an character validate`'s job (#78), not this one's.
    aliases: dict[str, dict[str, str]] = {}
    missing_art: list[tuple[str, str, str]] = []
    for slot_name, attachments in skin.slots.items():
        resolved_here: dict[str, str] = {}
        for name, att in attachments.items():
            src = art_src(ref, att.path, art_prefix=art_prefix)
            if probe is not None and not probe(src)[0]:
                missing_art.append((slot_name, name, att.path))
                continue
            resolved_here[name] = _register(slot_name, name, att)
        aliases[slot_name] = resolved_here

    nodes: dict[str, NodeJSON] = {}
    children_of: dict[str, list[NodeJSON]] = {}

    for slot in sorted(desc.slots, key=lambda s: (s.draw_order, s.name)):
        parent = nests_under.get(slot.bone)
        nested = parent is not None and parent != slot.name
        # Baked face: drop every slot nested under the HEAD BONE's primary
        # slot — keyed on the bone (the rig's skeleton contract), not on the
        # slot name "head": a rig whose head slot is named otherwise used to
        # get its face overlays (and their blinks) back (an#88 review).
        if nested and head_has_face and parent == nests_under.get("head"):
            continue

        resolved = drawn_attachment(desc, skin, slot)
        if resolved is None or resolved[0] not in aliases.get(slot.name, {}):
            continue
        attachment_name, attachment = resolved

        # Position = the slot's bone, plus the attachment's own offset from it.
        # Both are needed: five face parts share one `head` bone, so the bone
        # alone would stack them, and the offset alone would ignore the rig.
        bone_x, bone_y = bones.get(slot.bone, (0.0, 0.0))
        if nested:
            parent_x, parent_y = bones.get(parent, (0.0, 0.0))
            bone_x, bone_y = bone_x - parent_x, bone_y - parent_y
        else:
            bone_x, bone_y = bone_x - origin[0], bone_y - origin[1]
        bone_x += attachment.x
        bone_y += attachment.y

        extent = _box_of(attachment)
        visual = VisualJSON(
            kind="svg_sprite",
            asset_id=aliases[slot.name][attachment_name],
            anchor_x=attachment.anchor[0],
            anchor_y=attachment.anchor[1],
            fit=CONTAIN_FIT,
            **({"width": extent[0] * k, "height": extent[1] * k} if extent else {}),
        )
        # The per-slot PROJECTION of the descriptor's asset_sets (an#87): a
        # channel projects onto every slot whose attachments its keys name —
        # `viseme` lands on the mouth because the mouth's attachments carry
        # the viseme map's values, `eyelid` lands on BOTH eye slots because
        # both carry `open`/`closed`. No slot names appear here: the skin is
        # the binding. Keys whose art did not resolve are absent from the map
        # (an inventory gap — `_record_missing_parts` records it; a key a
        # channel actually USES escalates via the fallback machinery).
        projected = {
            channel: resolved
            for channel, key_map in desc.asset_sets.items()
            if (
                resolved := {
                    key: aliases[slot.name][name]
                    for key, name in key_map.items()
                    if name in aliases[slot.name]
                }
            )
        }
        if projected:
            visual.asset_sets = projected
            geometry = _swap_key_geometry(
                projected,
                aliases[slot.name],
                skin.slots.get(slot.name, {}),
                drawn=attachment,
                built=extent,
                box_of=_box_of,
                k=k,
            )
            if geometry:
                visual.asset_geometry = geometry

        node = NodeJSON(
            name=slot.name,
            transform=TransformJSON(x=bone_x * k, y=bone_y * k),
            visual=visual,
        )
        nodes[slot.name] = node
        children_of.setdefault(parent if nested else "", []).append(node)

    _record_missing_parts(entity, missing_art, drawn=set(nodes), into=resolutions)

    for parent_name, kids in children_of.items():
        if parent_name and parent_name in nodes:
            nodes[parent_name].children = kids

    return NodeJSON(
        name=entity.id,
        transform=TransformJSON(),
        children=children_of.get("", []),
    )


def _swap_key_geometry(
    projected: Mapping[str, Mapping[str, str]],
    alias_of: Mapping[str, str],
    attachments: Mapping[str, Attachment],
    *,
    drawn: Attachment,
    built: tuple[float, float] | None,
    box_of: Callable[[Attachment], tuple[float, float] | None],
    k: float,
) -> dict[str, dict[str, float]]:
    """``{asset_id: geometry}`` for each swap key drawn unlike the built one.

    The geometry is the key's own fit box (its art's extent × ``k``, the rig's
    one uniform scale), its anchor, and its offset from the drawn attachment
    in scene pixels — so every key is placed and scaled exactly as it would be
    if it were the slot's default. A key whose art cannot be measured keeps
    the built box: there is nothing better to say about it.

    >>> a = Attachment(path="parts/m_x.svg", width=100, height=10)
    >>> b = Attachment(path="parts/m_a.svg", width=100, height=60, y=5)
    >>> from an.stage.rig import _swap_key_geometry
    >>> _swap_key_geometry({"viseme": {"X": "c.m.x", "A": "c.m.a"}},
    ...                    {"x": "c.m.x", "a": "c.m.a"}, {"x": a, "a": b},
    ...                    drawn=a, built=(100, 10),
    ...                    box_of=lambda att: (att.width, att.height), k=0.5)
    {'c.m.a': {'width': 50.0, 'height': 30.0, 'anchor_x': 0.5, 'anchor_y': 0.5, 'x': 0.0, 'y': 2.5}}
    """
    name_of = {alias: name for name, alias in alias_of.items()}
    built_geometry = (
        (float(built[0]) * k, float(built[1]) * k) if built else None,
        (float(drawn.anchor[0]), float(drawn.anchor[1])),
        (0.0, 0.0),
    )
    out: dict[str, dict[str, float]] = {}
    for key_map in projected.values():
        for alias in key_map.values():
            if alias in out or alias not in name_of:
                continue
            att = attachments.get(name_of[alias])
            if att is None:
                continue
            box = box_of(att)
            if box is None:
                continue
            geometry = (
                (float(box[0]) * k, float(box[1]) * k),
                (float(att.anchor[0]), float(att.anchor[1])),
                (
                    (float(att.x) - float(drawn.x)) * k,
                    (float(att.y) - float(drawn.y)) * k,
                ),
            )
            if geometry == built_geometry:
                continue
            (w, h), (ax, ay), (dx, dy) = geometry
            out[alias] = {
                "width": w,
                "height": h,
                "anchor_x": ax,
                "anchor_y": ay,
                "x": dx,
                "y": dy,
            }
    return out
