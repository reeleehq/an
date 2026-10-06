"""Props: a rig whose art is not a person.

A lamp, a sword, a sign. Structurally a prop is what a character already is —
bones, slots, skins, attachments, swap sets — and the cutout compiler builds
both with the **same** rig builder, which is why an#108 made the art store an
argument rather than writing a second one.

What differs is the *descriptor*, and the difference is entirely in the
defaults:

============================  ===============================================
`CharacterDescriptor`         `PropDescriptor`
============================  ===============================================
seven-bone humanoid           one `root` bone
face, eyes, brows, mouth      one `body` slot
`idle_breath` + `blink`       no animations
viseme + eyelid `asset_sets`  none
`face_overlay` matters        no face at all
============================  ===============================================

**Why not `CharacterDescriptor` with `kind: "prop"`.** Three measured reasons,
each of which turns a one-field change into a silent wrong render:

1. `CharacterDescriptor.model_post_init` re-seeds the humanoid skeleton, the
   face slots, the default skin **and** `idle_breath`/`blink` from an empty
   list — so `CharacterDescriptor(name="sword")` is a seven-bone person with a
   blinking face, not an empty rig.
2. The compiler's placeholder fallback draws a **person** where a lamp should
   be (the an#33 failure mode), so a prop whose art fails to resolve renders
   as a humanoid rather than as nothing.
3. `an character validate` scores a correct prop at **22** blocking findings —
   `REQUIRED_PARTS` (12) plus `MOUTH_SHAPES` (9), none of which a lamp has,
   plus "has no character.json", which is the tool saying out loud that it was
   handed the wrong kind of document. (Measured on
   `tests/fixtures/props/lamp/`; an earlier draft of this docstring said 21,
   having added the two lists without running the tool.)

**Why not a new minimal document with `states`.** That is `asset_sets`
renamed: it would need a rename table at the compiler boundary and would cap a
prop at one moving piece. A prop reuses the swap-channel machinery instead, so
a two-state lamp is `asset_sets={"lamp": {"off": ..., "on": ...}}` and
`set lamp on` in the scene — the same words a character's viseme swap uses.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import Field

from an.stage.rig import (
    DEFAULT_VIEW_BOX,
    Attachment,  # noqa: F401
    Bone,
    RigDocument,
    Skin,
    Slot,
    register_rest_pose_migration,
)
from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, register_kind

__all__ = [
    "PROP_SCHEMA_VERSION",
    "PROP_DOCUMENT_KIND",
    "PropDescriptor",
    "default_prop_bones",
    "default_prop_slots",
]

#: 0.2.0 (an#339): the bones' rest pose (``rotation_deg``, ``scale_*``) poses
#: the built parts; the migration protects a 0.1.0 rig that carried one.
PROP_SCHEMA_VERSION = "0.2.0"

#: Its own versioned document, registered from the module that owns the schema
#: — the same rule `CharacterDescriptor` follows, and the reason the migration
#: registry is keyed per KIND: two documents at `0.1.0` that migrate
#: differently is exactly the collision an#77 fixed.
PROP_DOCUMENT_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="PropDescriptor",
        version_field="schema_version",
        current_version=PROP_SCHEMA_VERSION,
    )
)

register_rest_pose_migration(PROP_DOCUMENT_KIND.name, "0.1.0", "0.2.0")

#: The one bone a prop gets when it declares none. Named `root` rather than
#: `body` so the bone and the slot resting on it are not the same word — the
#: compiler nests a slot under its bone's primary slot, and a bone and slot
#: sharing a name reads as self-nesting to anyone debugging it.
DFLT_PROP_BONE = "root"

#: The one slot. `draw_order=0` because a prop with one slot has nothing to be
#: ordered against; a second slot names its own.
DFLT_PROP_SLOT = "body"


def default_prop_bones(view_box: tuple[int, int, int, int] = DEFAULT_VIEW_BOX) -> list[Bone]:
    """One bone, at the CENTRE of the view_box (an#408).

    A part is centred on its bone (anchor 0.5), so with the bone at the centre
    a full-canvas part's art coordinates ARE the rig's: an ``origin`` read off
    the drawing (a foot at ``(512, 1000)`` in a 1024 box) lands where it says.
    Before an#408 the bone sat at ``(0, 0)`` and an origin had to be measured
    from the art's centre. Nothing moves for a prop without an ``origin``: it
    is placed by its bones' extent centre, which is this bone wherever it is.

    >>> [(b.name, b.x, b.y) for b in default_prop_bones()]
    [('root', 512.0, 512.0)]
    """
    x, y, w, h = view_box
    return [Bone(name=DFLT_PROP_BONE, x=x + w / 2.0, y=y + h / 2.0)]


def default_prop_slots() -> list[Slot]:
    """One slot on that bone.

    >>> [(s.name, s.bone, s.draw_order) for s in default_prop_slots()]
    [('body', 'root', 0)]
    """
    return [Slot(name=DFLT_PROP_SLOT, bone=DFLT_PROP_BONE, draw_order=0)]


class PropDescriptor(RigDocument):
    """The on-disk prop schema. Saved as ``prop.json``.

    >>> p = PropDescriptor(name="lamp")
    >>> p.kind
    'PropDescriptor'
    >>> [b.name for b in p.bones], [s.name for s in p.slots]
    (['root'], ['body'])

    A prop is **not** seeded with a face, a skeleton or an idle animation —
    the three things `CharacterDescriptor` fills in from an empty list:

    >>> p.animations, p.asset_sets, p.skins
    ({}, {}, {})

    Two states are the swap-channel machinery a character's viseme already
    uses, not a second vocabulary:

    >>> lamp = PropDescriptor(
    ...     name="lamp",
    ...     skins={"default": Skin(slots={"body": {
    ...         "off": Attachment(path="parts/off.svg"),
    ...         "on": Attachment(path="parts/on.svg"),
    ...     }})},
    ...     asset_sets={"lamp": {"off": "off", "on": "on"}},
    ... )
    >>> sorted(lamp.asset_sets["lamp"])
    ['off', 'on']
    >>> back = PropDescriptor.model_validate_json(lamp.model_dump_json())
    >>> back.skins["default"].slots["body"]["on"].path
    'parts/on.svg'

    A prop stands where it is put by its declared ``origin`` (an#338), in
    view_box units; unset, by the centre of its bones' extent, and the stored
    document does not mention it:

    >>> PropDescriptor(name="tripod", origin=(512, 1010)).origin
    (512.0, 1010.0)
    >>> "origin" in PropDescriptor(name="lamp").model_dump()
    False
    """

    schema_version: str = PROP_SCHEMA_VERSION
    kind: Literal["PropDescriptor"] = "PropDescriptor"

    name: str
    display_name: Optional[str] = None
    view_box: tuple[int, int, int, int] = DEFAULT_VIEW_BOX

    #: Optional source SVG the ``parts/`` folder was sliced from.
    source_svg: Optional[str] = None

    bones: list[Bone] = Field(default_factory=list)
    slots: list[Slot] = Field(default_factory=list)
    skins: dict[str, Skin] = Field(default_factory=dict)

    #: ``{channel: {key: attachment_name}}`` — the same indirection a character
    #: uses for visemes. Empty by default: a prop with no moving parts declares
    #: none, and declaring a channel a rig cannot serve is what makes a swap
    #: silently keep the previous texture.
    asset_sets: dict[str, dict[str, str]] = Field(default_factory=dict)

    #: Present so `play` and the rig builder read the same attribute on either
    #: descriptor. Empty by default — a prop has no `idle_breath` and no
    #: `blink`, and seeding one would animate a lamp.
    animations: dict[str, Any] = Field(default_factory=dict)

    #: Always true, and not a knob. `face_overlay=False` means "the face is
    #: baked into the head art", which makes the builder suppress every slot
    #: nested under the head bone's primary slot. A prop has no head bone, so
    #: the flag can only do harm; it exists because the shared builder reads it.
    face_overlay: Literal[True] = True

    #: Where this art came from and what its licence obliges. ``None`` means
    #: "we made this" — not "unknown". Same field as `CharacterDescriptor`,
    #: because `an credits` should not need to know which store it came from.
    source: AssetSource | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # A rig, not a person: one bone and one slot, and nothing else. The
        # asymmetry with CharacterDescriptor is the point — see this module's
        # docstring for why `kind: "prop"` on a character is not the same
        # thing with fewer fields.
        if not self.bones:
            self.bones = default_prop_bones(self.view_box)
        if not self.slots:
            self.slots = default_prop_slots()


#: The prop analyser's version (an#340): bump when its output can change for the same input.
PROP_ANALYSER_VERSION: str = "0.1.0"


def prop_affordances(doc: Any, art: Any = None) -> dict[str, dict[str, Any]]:
    """A prop's capabilities: what its rig's structure affords (an#340).

    Only a ``PropDescriptor`` is a rig; a path or a text block in the props
    store affords nothing here.

    >>> prop_affordances({"kind": "TextDescriptor"})
    {}
    """
    if not isinstance(doc, dict) or doc.get("kind") != PROP_DOCUMENT_KIND.name:
        return {}
    from an.ir.migrate import migrate
    from an.stage.rig import rig_affordances

    return rig_affordances(migrate(dict(doc), kind=PROP_DOCUMENT_KIND.name))


def register_prop_analyser() -> None:
    """Register the stage's ``prop`` analyser (an#340); idempotent.

    Stage-side, not a core import side effect: the library calls it when it
    loads the genres, before it analyses an asset.
    """
    from an.capabilities import Analyser, register_analyser

    register_analyser(
        Analyser("prop", PROP_ANALYSER_VERSION, prop_affordances), owner="an.stage"
    )
