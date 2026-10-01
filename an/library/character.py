"""The character analyser: legs, arms, views and mouth chart, derived from the rig.

The first analyser (ADR 0005 first slice, item 2), shared with ADR 0002's first
slice: P7's capability registry adopts :func:`character_affordances` as
``affordances(asset)`` for characters instead of deriving a second time.

**What it reads is what the compiler reads**, or the facets would lie (ADR 0005,
Risks): the limb pairs ``walk`` resolves (:data:`an.motion.WALK_LEG_NAMES`,
:data:`an.motion.WALK_ARM_NAMES`), the ``view`` and ``viseme`` swap sets
(``asset_sets``), the declared facts ``rest_view`` and
``face_overlay``. And **art must be present**: a slot or swap key counts only
when an attachment it names has its file among the asset's files — a descriptor
promising a side view whose drawing is missing does not afford one.

It is genre code (cut-out characters). It lives here until the genre package
exists (plan P8) and imports the cut-out modules lazily so ``import an.library``
stays free of them. **Importing it registers nothing** (P7): the cut-out genre
declares :data:`CHARACTER_CAPABILITIES` and :data:`CHARACTER_ANALYSER` in its
``capabilities`` and ``analysers`` fields (:data:`an.genres.cutout.CUTOUT`), so
they register with the genre, owned by it, and come out with it.

=====================  ====================================================  ==========================
capability             afforded when                                         ``keys``
=====================  ====================================================  ==========================
``limbs.legs``         a leg pair ``walk`` resolves, both with art           —
``limbs.arms``         an arm pair ``walk`` resolves, both with art          —
``swap.view``          always: the rest view, plus every ``view`` key with   the views it can show
                       art (``swappable``: whether it can turn at all)
``face.mouth``         an overlay face (``face_overlay``) whose ``viseme``   the chart (``rhubarb9``
                       set has drawings                                      or ``custom``)
=====================  ====================================================  ==========================
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from an.capabilities import Analyser, Capability

__all__ = [
    "CHARACTER_ANALYSER",
    "CHARACTER_ANALYSER_VERSION",
    "CHARACTER_CAPABILITIES",
    "MOUTH_CHART_RHUBARB",
    "character_affordances",
    "renders_as_placeholder",
]

#: Bump when the derivation can answer differently for the same input.
CHARACTER_ANALYSER_VERSION: str = "0.1.0"
#: The chart name of the nine Rhubarb mouth shapes (A–H, X) — ``an``'s default.
MOUTH_CHART_RHUBARB: str = "rhubarb9"
#: The chart name of any other viseme set.
MOUTH_CHART_CUSTOM: str = "custom"

LIMBS_LEGS = Capability(
    "limbs.legs",
    description="a pair of leg slots with art that a legged walk swings",
    remedy=(
        "add two leg slots named leg_l/leg_r (or left_leg/right_leg) with their art, "
        "pivoted at the hip; `an character new` builds them (an-art-package skill)"
    ),
)
LIMBS_ARMS = Capability(
    "limbs.arms",
    description="a pair of arm slots with art that a walk swings and gestures move",
    remedy=(
        "add two arm slots named arm_l/arm_r (or left_arm/right_arm) with their art, "
        "pivoted at the shoulder (an-art-package skill)"
    ),
)
SWAP_VIEW = Capability(
    "swap.view",
    description=(
        "the turnaround views the character can show (keys); swappable=true when a "
        "`view` swap set lets it turn"
    ),
    remedy=(
        "add turnaround art and list it in the `view` swap set: "
        "`an character add-views <dir>` for an offline character, else draw the views"
    ),
    command="an character add-views",
)
FACE_MOUTH = Capability(
    "face.mouth",
    description="an overlay mouth with a viseme chart that lip-sync drives (keys: the chart)",
    remedy=(
        "give the character an overlay mouth: a `mouth` slot with the viseme set's "
        "drawings (`an character mouths <dir>` writes the default nine) and "
        "face_overlay: true — a face baked into the head art cannot lip-sync"
    ),
    command="an character mouths",
)


def _attachments_with_art(desc: Any, art: Mapping[str, Any]) -> dict[str, set[str]]:
    """``{slot: {attachment names whose file is present}}`` across every skin."""
    out: dict[str, set[str]] = {}
    for skin in desc.skins.values():
        for slot, attachments in skin.slots.items():
            for name, att in attachments.items():
                if att.path in art:
                    out.setdefault(slot, set()).add(name)
    return out


def _keys_with_art(
    swap_set: Mapping[str, str], drawn: Mapping[str, set[str]]
) -> list[str]:
    """The keys of a swap set whose selected attachment is drawn in some slot."""
    names = set().union(*drawn.values()) if drawn else set()
    return [key for key, attachment in swap_set.items() if attachment in names]


def renders_as_placeholder(doc: Mapping[str, Any]) -> bool:
    """Whether the compiler would draw this character only as its placeholder stand-in.

    >>> renders_as_placeholder({"name": "alice"}), renders_as_placeholder({"parts": ["head"]})
    (True, False)
    """
    return doc.get("kind") != "CharacterDescriptor" and not doc.get("parts")


def _parts_rig_affordances(
    doc: Mapping[str, Any],
    leg_names: tuple[tuple[str, str], ...],
    arm_names: tuple[tuple[str, str], ...],
) -> dict[str, dict[str, Any]]:
    """A procedural rig: what the compiler builds from ``parts`` — mirrored, not re-guessed.

    The same branch as ``_build_character_subtree``: a document that is not a
    ``CharacterDescriptor`` is drawn from its declared ``parts``, one node per
    part, with a drawn mouth on the head. A document that declares no parts is
    drawn as the compiler's PLACEHOLDER — a recorded fallback (fatal under
    ``--strict-assets``), not this asset's rig — so it affords nothing but the
    rest view: a stand-in must never answer a search for arms or a mouth.
    """
    from an.adapters.cutout.compile import PROCEDURAL_MOUTH_KEYS
    from an.characters.schema import DEFAULT_VISEME_MAP, DFLT_VIEW

    out: dict[str, dict[str, Any]] = {
        SWAP_VIEW.name: {
            "keys": [DFLT_VIEW],
            "rest": DFLT_VIEW,
            "swappable": False,
            "overrides": [],
        }
    }
    if renders_as_placeholder(doc):
        return out
    parts = set(doc["parts"])
    for cap, names in ((LIMBS_LEGS, leg_names), (LIMBS_ARMS, arm_names)):
        pair = next((p for p in names if all(n in parts for n in p)), None)
        if pair:
            out[cap.name] = {"slots": list(pair)}
    if "head" in parts:
        keys = set(dict(PROCEDURAL_MOUTH_KEYS))
        chart = (
            MOUTH_CHART_RHUBARB
            if keys == set(DEFAULT_VISEME_MAP)
            else MOUTH_CHART_CUSTOM
        )
        out[FACE_MOUTH.name] = {
            "keys": [chart],
            "chart": chart,
            "shapes": sorted(keys),
            "complete": True,
            "variants": [],
        }
    return out


def character_affordances(
    doc: Mapping[str, Any], art: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """The capabilities a character descriptor and its art afford.

    doc: the character descriptor document (any schema version; migrated first)
    art: the files present, ``{relative path: ContentRef JSON}`` (``parts/head.svg``, …)

    Gait is deliberately not here: which walk methods apply is the capability
    matcher's answer (``applicable("locomotion", asset)``, ADR 0002), derived from
    ``limbs.legs``, not a second fact about the asset.

    >>> from an.characters.schema import CharacterDescriptor
    >>> doc = CharacterDescriptor(name="blob").model_dump(mode="json")
    >>> sorted(character_affordances(doc, art={}))   # a descriptor with no art
    ['swap.view']
    """
    from an.characters.schema import (
        DEFAULT_VISEME_MAP,
        DFLT_VIEW,
        VIEW_CHANNEL,
        VIEW_VARIANT_SEP,
        VIEWS,
        VISEME_CHANNEL,
        CharacterDescriptor,
    )
    from an.ir.migrate import migrate
    from an.motion import WALK_ARM_NAMES, WALK_LEG_NAMES

    if doc.get("kind") != CharacterDescriptor.model_fields["kind"].default:
        # Not a descriptor: the compiler draws the procedural rig from the
        # declared `parts` (or its placeholder), with no art files at all.
        return _parts_rig_affordances(doc, WALK_LEG_NAMES, WALK_ARM_NAMES)
    desc = CharacterDescriptor.model_validate(
        migrate(dict(doc), kind="CharacterDescriptor")
    )
    drawn = _attachments_with_art(desc, art)
    out: dict[str, dict[str, Any]] = {}

    def limb_pair(candidates: tuple[tuple[str, str], ...]) -> tuple[str, str] | None:
        return next((p for p in candidates if all(n in drawn for n in p)), None)

    legs = limb_pair(WALK_LEG_NAMES)
    if legs:
        out[LIMBS_LEGS.name] = {"slots": list(legs)}
    arms = limb_pair(WALK_ARM_NAMES)
    if arms:
        out[LIMBS_ARMS.name] = {"slots": list(arms)}

    rest = desc.rest_view or DFLT_VIEW
    view_set = desc.asset_sets.get(VIEW_CHANNEL) or {}
    turnable = _keys_with_art(view_set, drawn)
    views = sorted(
        {rest, *turnable},
        key=lambda v: (VIEWS.index(v) if v in VIEWS else len(VIEWS), v),
    )
    out[SWAP_VIEW.name] = {
        "keys": views,
        "rest": rest,
        "swappable": bool(turnable),
        "overrides": ["rest_view"] if desc.rest_view is not None else [],
    }

    visemes = desc.asset_sets.get(VISEME_CHANNEL) or {}
    shapes = _keys_with_art(visemes, drawn) if desc.face_overlay else []
    if shapes:
        chart = (
            MOUTH_CHART_RHUBARB
            if set(visemes) == set(DEFAULT_VISEME_MAP)
            else MOUTH_CHART_CUSTOM
        )
        variants = sorted(
            name.rpartition(VIEW_VARIANT_SEP)[2]
            for name in desc.asset_sets
            if name.startswith(VISEME_CHANNEL + VIEW_VARIANT_SEP)
        )
        out[FACE_MOUTH.name] = {
            "keys": [chart],
            "chart": chart,
            "shapes": sorted(shapes),
            "complete": len(shapes) == len(visemes),
            "variants": variants,
        }

    return out


#: The capabilities the character analyser derives (declared by the cut-out genre).
CHARACTER_CAPABILITIES: tuple[Capability, ...] = (
    LIMBS_LEGS,
    LIMBS_ARMS,
    SWAP_VIEW,
    FACE_MOUTH,
)
#: The character analyser (declared by the cut-out genre, registered with it).
CHARACTER_ANALYSER: Analyser = Analyser(
    "character", CHARACTER_ANALYSER_VERSION, character_affordances
)
