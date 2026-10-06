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
import warnings
from collections.abc import Mapping
from pathlib import Path
from collections.abc import Collection
from typing import TYPE_CHECKING, Annotated, Any, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from an.capabilities.subjects import RIG_HIERARCHY as _RIG_HIERARCHY_CAPABILITY
from an.ir.assets import AssetSource
from an.ir.migrate import (
    KINDS,
    DocumentKind,
    migrate,
    register_migration,
    version_tuple,
)
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
RIG_DOCUMENT_OPTIONAL_FIELDS: tuple[str, ...] = ("origin", "rest_rotation", "nesting")


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


def bones_carry_a_rest_pose(doc: Any) -> bool:
    """Whether any bone of a (raw or model) rig document has a non-zero
    ``rotation_deg`` or a non-unit ``scale_x``/``scale_y``.

    >>> bones_carry_a_rest_pose({"bones": [{"name": "a"}, {"name": "b", "rotation_deg": 22}]})
    True
    >>> bones_carry_a_rest_pose({"bones": [{"name": "a", "scale_x": 1.0}]})
    False
    """
    for bone in _field_of(doc, "bones") or []:
        rotation = _field_of(bone, "rotation_deg", 0.0) or 0.0
        sx = _field_of(bone, "scale_x", 1.0)
        sy = _field_of(bone, "scale_y", 1.0)
        if (
            rotation != 0
            or (sx is not None and sx != 1)
            or (sy is not None and sy != 1)
        ):
            return True
    return False


def protect_legacy_rest_pose(doc: dict[str, Any]) -> dict[str, Any]:
    """The migration step every rig kind runs onto the version that applies the rest pose (an#339).

    Before it, a bone's ``rotation_deg`` and scale reached no node, so a rig
    whose bones carry one was drawn with that pose in its pixels. Such a
    document gets ``rest_rotation: false`` and keeps its picture; a document
    whose bones carry none gets nothing (and every document on the
    maintainer's machine was of that kind when this shipped). Returns ``doc``,
    edited in place; the caller sets the version.

    >>> protect_legacy_rest_pose({"bones": [{"name": "leg", "rotation_deg": -22}]})["rest_rotation"]
    False
    >>> "rest_rotation" in protect_legacy_rest_pose({"bones": [{"name": "root"}]})
    False
    >>> protect_legacy_rest_pose({"bones": [{"name": "leg", "rotation_deg": 5}], "rest_rotation": True})["rest_rotation"]
    True
    """
    if "rest_rotation" not in doc and bones_carry_a_rest_pose(doc):
        doc["rest_rotation"] = False
    return doc


class RestPoseWarning(UserWarning):
    """A rig's bone rest pose was NOT applied, because the document may predate it."""


def rest_pose_protection(
    raw: Any, migrated: Any, *, kind: str = "rig document"
) -> str | None:
    """What to say when the MIGRATION, on this read, kept a rig's pose unapplied (an#407).

    The protective step writes ``rest_rotation: false`` onto a document from
    before the rest pose whose bones carry one, guessing the pose is already in
    its pixels. An author who added a rotation to such a file is the other
    case, and nothing else would tell them why the part did not move. A flag
    the AUTHOR wrote (present in the stored document) is a choice, and silent.

    >>> old = {"schema_version": "0.1.0", "bones": [{"name": "leg", "rotation_deg": 20}]}
    >>> rest_pose_protection(old, {**old, "rest_rotation": False}).startswith("its bones carry")
    True
    >>> rest_pose_protection({**old, "rest_rotation": False}, {**old, "rest_rotation": False}) is None
    True
    """
    if not isinstance(raw, Mapping) or "rest_rotation" in raw:
        return None
    if _field_of(migrated, "rest_rotation") is not False or not bones_carry_a_rest_pose(
        migrated
    ):
        return None
    return (
        "its bones carry a rotation or scale that is NOT applied: `rest_rotation: "
        f"false` keeps the rig as drawn (the migration writes it onto a {kind} from "
        "before bones posed their parts, an#339). If the pose is yours, set "
        "`rest_rotation: true` (or delete the key) and the bones pose the parts"
    )


def legacy_rest_pose_unknown(
    raw: Mapping[str, Any], kind: DocumentKind, *, since: str
) -> bool:
    """The builder guard (an#339): whether ``raw`` may be a pre-rest-pose
    document that its migration could not see.

    ``DocumentKind.version_of`` reads a document with no version field as
    CURRENT, so the protective migration never runs on it. A document like
    that whose bones carry a pose, and which says nothing about
    ``rest_rotation``, is built flat (as it would have been) and warned
    about. A version older than ``since`` is caught too, should a read skip
    the migration.

    >>> k = DocumentKind("Demo", "schema_version", "0.2.0")
    >>> legacy_rest_pose_unknown({"bones": [{"name": "a", "rotation_deg": 9}]}, k, since="0.2.0")
    True
    >>> legacy_rest_pose_unknown({"schema_version": "0.2.0", "bones": [{"name": "a", "rotation_deg": 9}]}, k, since="0.2.0")
    False
    """
    if "rest_rotation" in raw or not bones_carry_a_rest_pose(raw):
        return False
    declared = raw.get(kind.version_field)
    if declared is None:
        return True
    have, want = version_tuple(declared), version_tuple(since)
    return have is not None and want is not None and have < want


#: ``{rig document kind: the version from which its bones' rest pose is applied}``,
#: filled by :func:`register_rest_pose_migration` (an#339). The builder guard
#: reads it to recognise a document older than that version.
REST_POSE_SINCE: dict[str, str] = {}


def register_rest_pose_migration(kind: str, from_version: str, to_version: str) -> None:
    """Register the protective rest-pose step for one rig kind (an#339).

    One call from the module that owns the kind's schema (``an.stage.props``
    for ``PropDescriptor``, ``cutan`` for ``CharacterDescriptor``): it registers
    :func:`protect_legacy_rest_pose` as that kind's ``from -> to`` migration and
    records ``to`` as the version the builder applies the rest pose from.

    >>> register_rest_pose_migration("DemoRig", "1.0", "2.0")
    >>> REST_POSE_SINCE["DemoRig"]
    '2.0'
    >>> from an.ir.migrate import MIGRATIONS
    >>> MIGRATIONS[("DemoRig", "1.0", "2.0")]({"version": "1.0", "bones": []})
    {'version': '1.0', 'bones': []}
    """
    version_field = KINDS[kind].version_field if kind in KINDS else "schema_version"

    @register_migration(kind, from_version, to_version)
    def _step(doc: dict[str, Any]) -> dict[str, Any]:
        protect_legacy_rest_pose(doc)
        if version_field in doc:
            doc[version_field] = to_version
        return doc

    _step.__doc__ = f"{kind} {from_version} -> {to_version}: the bones' rest pose is applied (an#339)."
    REST_POSE_SINCE[kind] = to_version


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

    #: Whether the bones' ``rotation_deg``/``scale_x``/``scale_y`` pose the
    #: built parts (an#339). Unset (or ``True``) they do: the rest pose is the
    #: bones'. ``False`` is written ONLY by the migration onto a document from
    #: before that rule whose bones carry a rotation or scale, because such a
    #: rig was drawn with the pose already in its pixels (the fields were
    #: ignored) and applying them now would pose it twice
    #: (:func:`protect_legacy_rest_pose`).
    rest_rotation: bool | None = None

    #: How slots nest (an#340). Unset or ``"flat"``: a slot nests under its
    #: OWN bone's primary slot only, so limbs are siblings of the torso (the
    #: rigs' long-standing shape). ``"bones"``: a slot nests under the primary
    #: slot of the nearest ancestor bone that has one, to any depth, so a
    #: forearm turns with its upper arm and a sword with its hand (forward
    #: kinematics). :func:`slot_parent_chain` is the rule.
    nesting: Literal["flat", "bones"] | None = None

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

    The anchor of node nesting (:func:`slot_parent_chain`). In the default
    ``flat`` nesting the rigs are flat — arms are siblings of the torso, not
    children (CLAUDE.md pillar 4) — so bone parentage decides *position* only:
    a slot nests under the primary slot of its own bone when it is not that
    slot itself, which puts eyes and mouth under ``head`` and leaves every limb
    a direct child of the entity. ``nesting: bones`` (an#340) follows the bone
    hierarchy to the nearest ancestor's primary slot instead.

    >>> from types import SimpleNamespace as NS
    >>> primary_slot_per_bone(NS(slots=[NS(name="head", bone="head"), NS(name="mouth", bone="head")]))["head"]
    'head'
    """
    return {s.bone: s.name for s in desc.slots if s.name == s.bone}


#: The nesting modes (:attr:`RigDocument.nesting`); unset means the first.
NESTINGS: tuple[str, ...] = ("flat", "bones")
FLAT_NESTING, BONES_NESTING = NESTINGS


class RigError(ValueError):
    """A rig cannot be built as declared (a cycle, or a chain the stage cannot draw)."""


def nesting_of(desc: Any) -> str:
    """``"flat"`` or ``"bones"`` (an#340); unset is flat.

    >>> nesting_of({"nesting": "bones"}), nesting_of({})
    ('bones', 'flat')
    """
    return _field_of(desc, "nesting") or FLAT_NESTING


def slot_parent_chain(desc: Any) -> dict[str, str | None]:
    """``{slot: the slot it nests under, or None}``: THE nesting rule (an#340).

    The builder and a genre's part paths (``cutan``'s ``play.slot_parent``,
    ``slot_node_path``) all read it, so a ``play`` or a preset addresses the
    node the builder made.

    - ``flat`` (unset): a slot nests under its own bone's primary slot (the
      slot named like the bone) when it is not that slot; everything else is a
      child of the entity. Arms are siblings of the torso.
    - ``bones``: the same, and a slot that IS its bone's primary (or whose bone
      has none) nests under the primary slot of the nearest ANCESTOR bone that
      has one, to any depth. A bone cycle stops the walk; ``rig_problems``
      names it and the builder refuses it.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(bones=[NS(name="arm", parent="torso"), NS(name="hand", parent="arm"),
    ...                 NS(name="torso", parent=None)],
    ...          slots=[NS(name="torso", bone="torso"), NS(name="arm", bone="arm"),
    ...                 NS(name="hand", bone="hand"), NS(name="sword", bone="hand")])
    >>> slot_parent_chain(rig)
    {'torso': None, 'arm': None, 'hand': None, 'sword': 'hand'}
    >>> rig.nesting = "bones"
    >>> slot_parent_chain(rig)
    {'torso': None, 'arm': 'torso', 'hand': 'arm', 'sword': 'hand'}
    """
    slots = list(_field_of(desc, "slots") or [])
    primary = {
        _field_of(s, "bone"): _field_of(s, "name")
        for s in slots
        if _field_of(s, "name") == _field_of(s, "bone")
    }
    bones_mode = nesting_of(desc) == BONES_NESTING
    parent_bone = {
        _field_of(b, "name"): _field_of(b, "parent")
        for b in _field_of(desc, "bones") or []
    }
    out: dict[str, str | None] = {}
    for slot in slots:
        name, bone = _field_of(slot, "name"), _field_of(slot, "bone")
        own = primary.get(bone)
        if own is not None and own != name:
            out[name] = own
            continue
        parent = None
        if bones_mode:
            seen = {bone}
            cursor = parent_bone.get(bone)
            while cursor is not None and cursor not in seen:
                seen.add(cursor)
                if cursor in primary:
                    parent = primary[cursor]
                    break
                cursor = parent_bone.get(cursor)
        out[name] = parent
    return out


def slot_node_paths(desc: Any) -> dict[str, str]:
    """``{slot: its node path relative to the entity}`` (``torso/arm/hand``), by
    :func:`slot_parent_chain`; a slot caught in a cycle maps to its own name.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(nesting="bones", bones=[NS(name="a", parent=None), NS(name="b", parent="a")],
    ...          slots=[NS(name="a", bone="a"), NS(name="b", bone="b")])
    >>> slot_node_paths(rig)
    {'a': 'a', 'b': 'a/b'}
    """
    parents = slot_parent_chain(desc)
    out: dict[str, str] = {}
    for name in parents:
        parts, seen, cursor = [], set(), name
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            parts.append(cursor)
            cursor = parents.get(cursor)
        out[name] = "/".join(reversed(parts)) if cursor is None else name
    return out


def rig_problems(desc: Any) -> list[str]:
    """What is structurally wrong with a rig's bones and slots (an#340).

    A bone whose ``parent`` names no bone; a cycle in the bone graph (the one
    form a closed linkage can take in a model where each bone names one
    parent: forward kinematics only, so it is refused); a slot whose ``bone``
    names no bone (it used to land at the origin, silently). Shared by the
    asset validators (``an character validate``, :func:`an.stage.props.validate_prop`).

    >>> from types import SimpleNamespace as NS
    >>> rig_problems(NS(bones=[NS(name="a", parent="b"), NS(name="b", parent="a")],
    ...                 slots=[NS(name="s", bone="nope")]))
    ['bones form a cycle (a closed linkage): a -> b -> a; a rig is a tree (forward kinematics only)', "slot 's' is bound to bone 'nope', which the rig does not declare"]
    """
    bones = list(_field_of(desc, "bones") or [])
    names = {_field_of(b, "name") for b in bones}
    parent_of = {_field_of(b, "name"): _field_of(b, "parent") for b in bones}
    out: list[str] = []
    for bone in bones:
        parent = _field_of(bone, "parent")
        if parent is not None and parent not in names:
            out.append(
                f"bone {_field_of(bone, 'name')!r} names parent {parent!r}, which the rig does not declare"
            )
    reported: set[frozenset] = set()
    for start in sorted(names, key=str):
        path, cursor = [], start
        while cursor is not None and cursor not in path:
            path.append(cursor)
            cursor = parent_of.get(cursor)
        if cursor is not None:
            loop = path[path.index(cursor) :]
            key = frozenset(loop)
            if key not in reported:
                reported.add(key)
                out.append(
                    "bones form a cycle (a closed linkage): "
                    + " -> ".join([*loop, loop[0]])
                    + "; a rig is a tree (forward kinematics only)"
                )
    for slot in _field_of(desc, "slots") or []:
        if _field_of(slot, "bone") not in names:
            out.append(
                f"slot {_field_of(slot, 'name')!r} is bound to bone "
                f"{_field_of(slot, 'bone')!r}, which the rig does not declare"
            )
    return out


def chain_paint_order(desc: Any, *, built: Any = None) -> dict[str | None, list[str]]:
    """How each container of a nested chain must order what it holds (an#403).

    The stage draws a container's items in order: its slot's own visual and its
    child slots' containers (``None`` is the entity's container, which holds the
    root slots and no visual of its own). Sorting those siblings (PixiJS's
    ``sortableChildren`` on a ``zIndex``) gives any order in which every slot's
    SUBTREE is painted contiguously, a far arm behind the torso it nests under
    included. Each item spans the draw orders of its subtree; the items are
    sorted, stably, by that ``(lowest, highest)`` span, starting from the
    builder's own order (:func:`natural_paint_order`), so equal draw orders keep
    their tree order and a chain already painted in declared order is not
    reordered. ``built`` limits it to the slots the builder drew.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(nesting="bones",
    ...          bones=[NS(name="torso", parent=None), NS(name="arm", parent="torso")],
    ...          slots=[NS(name="torso", bone="torso", draw_order=2), NS(name="arm", bone="arm", draw_order=1)])
    >>> chain_paint_order(rig)
    {None: ['torso'], 'torso': ['arm', 'torso']}
    """
    parents = slot_parent_chain(desc)
    keys = _draw_keys(desc)
    names = [n for n in keys if built is None or n in built]
    kids: dict[str | None, list[str]] = {}
    for name in names:
        parent = parents.get(name)
        # A slot caught in a bone cycle maps to itself (`slot_parent_chain`):
        # it is a root here; `rig_problems` refuses the cycle.
        kids.setdefault(
            parent if parent in names and parent != name else None, []
        ).append(name)

    def span(name: str, seen: frozenset = frozenset()) -> tuple:
        below = [span(k, seen | {name}) for k in kids.get(name, []) if k not in seen]
        own = keys[name][0]
        return (min([own, *(b[0] for b in below)]), max([own, *(b[1] for b in below)]))

    held = {
        None: kids.get(None, []),
        **{n: [n, *kids[n]] for n in names if kids.get(n)},
    }
    natural = natural_paint_order(held, keys)
    return {
        container: sorted(
            items,
            key=lambda item, owner=container: (
                (keys[item][0],) * 2 if item == owner else span(item)
            ),
        )
        for container, items in natural.items()
    }


def _draw_keys(desc: Any) -> dict[str, tuple]:
    """``{slot: (draw_order, name)}``: the builder's own order of siblings."""
    return {
        _field_of(s, "name"): (_field_of(s, "draw_order", 0) or 0, _field_of(s, "name"))
        for s in _field_of(desc, "slots") or []
    }


def _painted(order: dict[str | None, list[str]]) -> list[str]:
    """The slots in the order the stage paints them, containers sorted by ``order``."""
    out: list[str] = []

    def paint(container: str | None) -> None:
        for item in order.get(container, []):
            if item == container or item in out:
                if item not in out:
                    out.append(item)
            elif item in order:
                paint(item)
            else:
                out.append(item)

    paint(None)
    return out


def natural_paint_order(order: dict[str | None, list[str]], keys: dict) -> dict:
    """What each container holds in the builder's own order: the slot's visual
    first, then its children by their own ``(draw_order, name)``."""
    return {
        container: ([container] if container is not None else [])
        + sorted((i for i in items if i != container), key=lambda i: keys[i])
        for container, items in order.items()
    }


def global_paint_order(desc: Any, *, built: Any = None) -> list[str]:
    """The node paths of a rig's slots, relative to its entity, in DECLARED
    draw order: the paint list the stage uses when a nested chain interleaves
    with an unrelated part (an#430), which no sort of a container's own items
    can give (:func:`chain_draw_order_problems`). Spine's global slot order:
    each part follows its bone's world transform, and the list says who
    paints over whom. ``built`` limits it to the slots the builder drew.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(nesting="bones",
    ...          bones=[NS(name="arm", parent=None), NS(name="hand", parent="arm"), NS(name="cord", parent=None)],
    ...          slots=[NS(name="arm", bone="arm", draw_order=1), NS(name="cord", bone="cord", draw_order=2),
    ...                 NS(name="hand", bone="hand", draw_order=3)])
    >>> global_paint_order(rig)
    ['arm', 'cord', 'arm/hand']
    """
    keys = _draw_keys(desc)
    paths = slot_node_paths(desc)
    return [paths[n] for n in sorted(keys, key=keys.get) if built is None or n in built]


def _stamp_paint_order(desc: Any, nodes: dict[str, NodeJSON]) -> None:
    """Give the built nodes the ``z_index`` the stage sorts by (an#403), only in
    the containers whose declared order differs from the builder's own (a
    rig whose tree already paints in declared order stays byte-identical)."""
    keys = _draw_keys(desc)
    order = chain_paint_order(desc, built=set(nodes))
    natural = natural_paint_order(order, keys)
    for container, items in order.items():
        if items == natural[container]:
            continue
        for z, item in enumerate(items, start=1):
            if item == container:
                nodes[item].visual.z_index = z
            else:
                nodes[item].z_index = z


def chain_draw_order_problems(desc: Any) -> list[str]:
    """Where a nested chain asks the STAGE for a draw order it cannot give (an#340, an#403).

    The stage sorts the items of each container (:func:`chain_paint_order`), so
    a part nested under one drawn LATER is fine (a far arm behind its torso).
    What it cannot do is interleave two containers: a slot's subtree is always
    painted together, so an unrelated part ordered between a chain's members
    (a leg between the arms and the head) cannot be honoured. Refused by the
    stage compiler; the asset validators only warn. Nothing in ``flat``
    nesting.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(nesting="bones",
    ...          bones=[NS(name="arm", parent=None), NS(name="hand", parent="arm"), NS(name="cord", parent=None)],
    ...          slots=[NS(name="arm", bone="arm", draw_order=1), NS(name="cord", bone="cord", draw_order=2),
    ...                 NS(name="hand", bone="hand", draw_order=3)])
    >>> chain_draw_order_problems(rig)[0].startswith("the stage paints each chain's parts together")
    True
    """
    if nesting_of(desc) != BONES_NESTING:
        return []
    keys = _draw_keys(desc)
    painted = _painted(chain_paint_order(desc))
    for before, after in zip(painted, painted[1:]):
        if keys[after][0] < keys[before][0]:
            return [
                f"the stage paints each chain's parts together (a container's "
                f"items can be reordered, not interleaved with another's; it draws "
                f"depth first), so slot {after!r} (draw_order {keys[after][0]}) "
                f"would paint after {before!r} (draw_order {keys[before][0]}), "
                "against the declared order: keep each chain's parts together in "
                "draw order (no unrelated part between them), or flatten the rig "
                "(`nesting: flat`)"
            ]
    return []


def chain_pose_problems(desc: Any) -> list[str]:
    """A rest pose the stage cannot apply in a nested chain (an#340).

    A node exists only for a bone that carries a slot. A bone with NO slot
    between a part and the part it nests under has no node to rotate or
    scale, so its ``rotation_deg``/``scale_*`` would be lost (its ``x``/``y``
    are kept: positions sum along the chain). Refused at compile, like the
    draw order; give the bone a slot or move its pose to the bone below it.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(nesting="bones", slots=[NS(name="arm", bone="arm"), NS(name="hand", bone="hand")],
    ...          bones=[NS(name="arm", parent=None), NS(name="elbow", parent="arm", rotation_deg=-70),
    ...                 NS(name="hand", parent="elbow")])
    >>> chain_pose_problems(rig)[0].startswith("bone 'elbow' carries no slot")
    True
    """
    if nesting_of(desc) != BONES_NESTING:
        return []
    bones = {_field_of(b, "name"): b for b in _field_of(desc, "bones") or []}
    slot_bone = {
        _field_of(s, "name"): _field_of(s, "bone")
        for s in _field_of(desc, "slots") or []
    }
    out, said = [], set()
    for slot, parent in slot_parent_chain(desc).items():
        if parent is None:
            continue
        # The bones strictly between the part's own bone and its parent's.
        stop, seen = slot_bone.get(parent), set()
        own = slot_bone.get(slot)
        cursor = None if own == stop else _field_of(bones.get(own), "parent")
        while cursor is not None and cursor != stop and cursor not in seen:
            seen.add(cursor)
            bone = bones.get(cursor)
            if (
                bone is not None
                and cursor not in said
                and bones_carry_a_rest_pose({"bones": [bone]})
            ):
                said.add(cursor)
                out.append(
                    f"bone {cursor!r} carries no slot, but sits in the chain from "
                    f"{parent!r} to {slot!r} with a rest rotation or scale: no node "
                    "carries it, so the pose would be lost; give the bone a slot, or "
                    "move its pose onto the bone below it"
                )
            cursor = _field_of(bone, "parent")
    return out


#: The capability a nested chain affords (ADR 0002 decision 1's name, registered
#: by the core in :mod:`an.capabilities.subjects`).
RIG_HIERARCHY: str = _RIG_HIERARCHY_CAPABILITY.name


def rig_affordances(desc: Any) -> dict[str, dict[str, Any]]:
    """What a rig's structure affords, derived from the rig model (an#340).

    ``rig.hierarchy`` when the rig nests in ``bones`` mode and some chain links
    two different bones: ``keys`` are every slot in such a chain (so
    ``rig.hierarchy:forearm_l`` asks for a forearm in a chain), ``count`` the
    deepest chain's number of BONES (``rig.hierarchy>=3`` is "a shoulder, an
    elbow and a hand"), ``chains`` every root-to-leaf chain of slots. Parts on
    one bone (a head with its face) add no depth, and a flat rig affords
    nothing here: that nesting is a drawing convention, not a joint. The core registers it as the ``prop``
    analyser; a genre's analyser composes it for its own kinds.

    >>> from types import SimpleNamespace as NS
    >>> rig = NS(nesting="bones", bones=[NS(name="arm", parent=None), NS(name="hand", parent="arm")],
    ...          slots=[NS(name="arm", bone="arm"), NS(name="hand", bone="hand"), NS(name="sword", bone="hand")])
    >>> rig_affordances(rig)
    {'rig.hierarchy': {'keys': ['arm', 'hand', 'sword'], 'count': 2, 'chains': [['arm', 'hand', 'sword']]}}
    """
    if nesting_of(desc) != BONES_NESTING or rig_problems(desc):
        return {}
    parents = slot_parent_chain(desc)
    has_child = {p for p in parents.values() if p is not None}
    chains = []
    for leaf in sorted(n for n in parents if n not in has_child):
        chain, cursor = [], leaf
        while cursor is not None:
            chain.append(cursor)
            cursor = parents[cursor]
        chains.append(list(reversed(chain)))
    slot_bone = {
        _field_of(s, "name"): _field_of(s, "bone")
        for s in _field_of(desc, "slots") or []
    }

    def joints(chain: list[str]) -> int:
        # Links between DIFFERENT bones: a face part on the head's own bone is
        # a drawing convention, not a joint.
        return 1 + sum(slot_bone[a] != slot_bone[b] for a, b in zip(chain, chain[1:]))

    deep = [c for c in chains if joints(c) > 1]
    if not deep:
        return {}
    return {
        RIG_HIERARCHY: {
            "keys": sorted({slot for c in deep for slot in c}),
            "count": max(joints(c) for c in deep),
            "chains": deep,
        }
    }


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


def rig_rest_problems(desc: Any) -> list[str]:
    """Warnings about a rig's rest pose (an#339), on a model or a raw document.

    A part turns about its NODE's origin, which is the bone plus the drawn
    attachment's ``x``/``y`` offset. A bone with a rest rotation whose part is
    offset therefore turns that part about a point that is not the joint, the
    usual way a splayed leg ends up detached from its hip. The way to turn a
    part about its joint is ``x: 0, y: 0`` on the attachment and the art's
    ``anchor`` at the joint. Nothing is said about a rig that keeps its legacy
    pose (``rest_rotation: false``), since its bones pose nothing.

    >>> doc = {"bones": [{"name": "leg", "rotation_deg": 20}],
    ...        "slots": [{"name": "leg", "bone": "leg"}],
    ...        "skins": {"default": {"slots": {"leg": {"leg": {"path": "p.svg", "y": 40}}}}}}
    >>> rig_rest_problems(doc)[0].startswith("bone 'leg' rests at 20")
    True
    >>> doc["skins"]["default"]["slots"]["leg"]["leg"]["y"] = 0
    >>> rig_rest_problems(doc)
    []
    """
    if _field_of(desc, "rest_rotation") is False:
        return []
    rotated = {
        _field_of(b, "name"): float(_field_of(b, "rotation_deg", 0.0) or 0.0)
        for b in _field_of(desc, "bones") or []
        if (_field_of(b, "rotation_deg", 0.0) or 0.0) != 0
    }
    if not rotated:
        return []
    skins = _field_of(desc, "skins") or {}
    skin = skins.get("default") or next(iter(skins.values()), None)
    skin_slots = _field_of(skin, "slots") or {} if skin is not None else {}
    out = []
    for slot in _field_of(desc, "slots") or []:
        bone = _field_of(slot, "bone")
        if bone not in rotated:
            continue
        available = skin_slots.get(_field_of(slot, "name")) or {}
        if not available:
            continue
        wanted = _field_of(slot, "attachment")
        attachment = (
            available.get(wanted)
            if wanted in available
            else next(iter(available.values()))
        )
        dx = float(_field_of(attachment, "x", 0.0) or 0.0)
        dy = float(_field_of(attachment, "y", 0.0) or 0.0)
        if dx or dy:
            out.append(
                f"bone {bone!r} rests at {rotated[bone]:g} degrees, but slot "
                f"{_field_of(slot, 'name')!r} draws its part offset ({dx:g}, {dy:g}) "
                "from it, so the part turns about that offset point, not the "
                "joint: put the joint in the art's `anchor` and the offset at 0"
            )
    return out


def rest_transform(bone: Any) -> dict[str, float]:
    """The node transform fields a bone's rest pose sets (an#339): its
    ``rotation_deg`` in radians and its scales, ``-0.0`` normalised to ``0.0``.

    Every rest reader composes on the built transform (``play`` deviations,
    swap poses, the face solver, presets, a from-less tween, the runtime's
    load), so this is the whole change. An authored ``rotation`` tween stays
    ABSOLUTE: ``to: 0`` straightens a part whose rest is splayed.

    >>> rest_transform(Bone(name="leg", rotation_deg=-22))["rotation"]
    -0.3839724354387525
    >>> rest_transform(Bone(name="leg", rotation_deg=-0.0))
    {'rotation': 0.0, 'scale_x': 1.0, 'scale_y': 1.0}
    """
    return {
        "rotation": math.radians(float(bone.rotation_deg)) + 0.0,
        "scale_x": float(bone.scale_x) + 0.0,
        "scale_y": float(bone.scale_y) + 0.0,
    }


def _legacy_baked_face_slots(desc: Any, parents: Mapping[str, str | None]) -> set[str]:
    """The builder's pre-an#340 face rule, for a genre that passes no ``skip_slots``.

    With the face baked into the head art (``face_overlay`` false), the eye,
    brow and mouth slots nested under the HEAD BONE's primary slot would
    double the baked features, so they were dropped here. Keyed on the bone,
    not on a slot named "head" (an#88 review). The cut-out genre now passes
    its own set (``cutan.characters.play.suppressed_slots``).
    """
    if _field_of(desc, "face_overlay", True):
        return set()
    head = next(
        (s.name for s in desc.slots if s.bone == "head" and s.name == s.bone), None
    )
    # The face is the slots ON the head bone (not parts of its child bones,
    # which nest under the head too in `nesting: bones`).
    return {
        s.name
        for s in desc.slots
        if head is not None and s.bone == "head" and s.name != head
    }


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
    skip_slots: Collection[str] | None = None,
) -> NodeJSON:
    """Build the scene subtree for a rig (a prop or a character), **from its descriptor**.

    Slots nest by :func:`slot_parent_chain` (``nesting: flat`` or ``bones``,
    an#340). In ``bones`` mode a nested part is placed relative to its parent
    BONE, without inheriting the parent's attachment offset, and its bone's
    rest pose composes through the chain.

    ``skip_slots`` are slots the GENRE says not to build (the cut-out genre's
    baked face: ``cutan.characters.play.suppressed_slots``); a skipped slot's
    nested parts are not built either. ``None`` is the legacy rule for a genre
    that predates the argument (``an.genres.API_LEVEL`` < 5): with
    ``face_overlay`` false, the slots nested under the ``head`` bone's primary
    slot. It is the one place the core still names a bone, and it goes when no
    genre needs it.

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
    raw = dict(desc_data)
    legacy_pose = legacy_rest_pose_unknown(
        raw, document_kind, since=REST_POSE_SINCE.get(document_kind.name)
    )
    migrated = migrate(dict(raw), kind=document_kind.name)  # raw stays as stored
    # A migration that saw the document decided already (it writes
    # `rest_rotation` when it must); the guard is for one it could not see.
    legacy_pose = legacy_pose and "rest_rotation" not in migrated
    desc = descriptor_model.model_validate(migrated)
    if legacy_pose:
        warnings.warn(
            f"{entity.id!r}: its {document_kind.name} declares no "
            f"`{document_kind.version_field}` (or an old one) and its bones carry "
            "a rotation or scale, so it may have been drawn before bones posed "
            "their parts (an#339): built WITHOUT the rest pose, as it always was. "
            f"Add `{document_kind.version_field}` (this build writes "
            f"{document_kind.current_version!r}) to apply the pose, or "
            "`rest_rotation: false` to keep it as drawn and silence this.",
            RestPoseWarning,
            stacklevel=2,
        )
    apply_rest_pose = _field_of(desc, "rest_rotation") is not False and not legacy_pose
    protected = rest_pose_protection(raw, migrated, kind=document_kind.name)
    if protected:
        # The protection is a guess about an old document (an#407): say so, or
        # an author who added a rotation to an old file sees nothing happen.
        warnings.warn(f"{entity.id!r}: {protected}", RestPoseWarning, stacklevel=2)
    bone_of = {b.name: b for b in desc.bones}
    ref = entity.ref or entity.id
    _, _, _, view_box_height = desc.view_box
    k = SCENE_PX_PER_VIEW_BOX / float(view_box_height or 1)

    skin = desc.skins.get("default") or next(iter(desc.skins.values()), Skin())
    bones = bone_positions(desc)
    origin = rig_origin(desc)
    # Shared with a genre's part paths (`cutan.characters.play`) so a `play`
    # resolves against the nesting the builder actually uses (an#7, an#340).
    parents = slot_parent_chain(desc)
    bones_mode = nesting_of(desc) == BONES_NESTING
    if bones_mode:
        # A chain interleaved with an unrelated part is no longer refused
        # here (an#430): it is painted from a global list (`paint_order`),
        # and the compiler refuses it only for an engine that cannot.
        broken = [p for p in rig_problems(desc) if "cycle" in p] + chain_pose_problems(
            desc
        )
        if broken:
            raise RigError(
                f"rig {ref!r} cannot be built with `nesting: bones`: "
                + "; ".join(broken)
            )
    slot_of = {s.name: s for s in desc.slots}
    skip = (
        set(skip_slots)
        if skip_slots is not None
        else _legacy_baked_face_slots(desc, parents)
    )

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
        parent = parents.get(slot.name)
        nested = parent is not None
        if slot.name in skip:
            continue

        resolved = drawn_attachment(desc, skin, slot)
        if resolved is None or resolved[0] not in aliases.get(slot.name, {}):
            continue
        attachment_name, attachment = resolved

        # Position = the slot's bone, plus the attachment's own offset from it.
        # Both are needed: five face parts share one `head` bone, so the bone
        # alone would stack them, and the offset alone would ignore the rig.
        bone_x, bone_y = bone_x0, bone_y0 = bones.get(slot.bone, (0.0, 0.0))
        if nested:
            parent_bone = slot_of[parent].bone
            parent_x, parent_y = bones.get(parent_bone, (0.0, 0.0))
            bone_x, bone_y = bone_x0 - parent_x, bone_y0 - parent_y
            if bones_mode:
                # Relative to the parent BONE: the parent node sits at its bone
                # plus its own attachment offset, which a chain must not inherit.
                drawn_parent = drawn_attachment(desc, skin, slot_of[parent])
                if drawn_parent is not None:
                    bone_x -= drawn_parent[1].x
                    bone_y -= drawn_parent[1].y
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

        # The bone's rest pose (an#339) poses the part that IS on it; a slot
        # nested under a part on the SAME bone gets it from that parent.
        rest = (
            rest_transform(bone_of[slot.bone])
            if apply_rest_pose
            and slot.bone in bone_of
            and not (nested and slot_of[parent].bone == slot.bone)
            else {}
        )
        node = NodeJSON(
            name=slot.name,
            transform=TransformJSON(x=bone_x * k, y=bone_y * k, **rest),
            visual=visual,
        )
        nodes[slot.name] = node
        children_of.setdefault(parent if nested else "", []).append(node)

    for parent_name, kids in children_of.items():
        if parent_name and parent_name in nodes:
            nodes[parent_name].children = kids
    paint_order = None
    if bones_mode:
        if chain_draw_order_problems(desc):
            paint_order = global_paint_order(desc, built=set(nodes))
        else:
            _stamp_paint_order(desc, nodes)

    # A part is drawn only if its whole chain was built: one whose parent was
    # not (its art missing) is an orphan, a hole in the picture like the parent
    # (an#340). One whose parent the genre skipped is meant to go with it.
    attached: set[str] = set()
    pending = list(children_of.get("", []))
    while pending:
        node = pending.pop()
        attached.add(node.name)
        pending.extend(node.children)
    _record_missing_parts(entity, missing_art, drawn=attached, into=resolutions)

    def _skipped_above(name: str) -> bool:
        seen: set[str] = set()
        cursor = parents.get(name)
        while cursor is not None and cursor not in seen:
            if cursor in skip:
                return True
            seen.add(cursor)
            cursor = parents.get(cursor)
        return False

    for name in sorted(set(nodes) - attached):
        if resolutions is None or _skipped_above(name):
            continue
        resolutions.append(
            AssetResolutionJSON(
                id=f"{entity.id}/{name}",
                kind="part",
                store=entity.store,
                ref=entity.ref,
                resolved="orphaned",
                fallback=True,
                detail=(
                    f"slot {name!r} nests under {parents.get(name)!r}, which was not "
                    "built (its art is missing), so it draws nothing either"
                ),
            )
        )

    return NodeJSON(
        name=entity.id,
        transform=TransformJSON(),
        children=children_of.get("", []),
        paint_order=paint_order,
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
