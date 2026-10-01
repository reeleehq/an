"""High-level entry points: build and inspect a character.

The :func:`new_character` function wires together fetching/wrapping art,
slicing it into per-part SVGs, generating the default mouth set, and
writing a complete character directory + ``character.json`` descriptor.

Checking one is :mod:`an.characters.validate`'s job, not this module's — it
opens every part and reports :class:`an.verify._base.Finding` s, so a character
problem routes the way every other verifier's does (an#78).

>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     descriptor_path = new_character(d, name='nobody', use_dicebear=False)
...     descriptor_path.parent.name, descriptor_path.name
('nobody', 'character.json')
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import math
import re
import json
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional
from xml.etree import ElementTree as ET


def _stable_hash(seed: str) -> int:
    """Deterministic across processes (unlike Python's `hash()` for strings).

    Python's built-in ``hash()`` is salt-randomized per interpreter run, so
    using it for color derivation produces different palettes each render.
    """
    digest = hashlib.md5(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


from an.characters import drawn as _drawn
from an.characters.licenses import (
    DICEBEAR_STYLE_LICENSES,
    attribution_for,
    dicebear_source,
    requires_acknowledgement,
)
from an.ir.assets import AssetSource
from an.characters.dicebear import (
    DICEBEAR_DEFAULT_STYLE,
    fetch_dicebear,
    wrap_dicebear_for_an,
)
from an.characters.mouth_set import (
    DEFAULT_MOUTH_VARIANTS,
    mouth_attachment_name,
    write_default_mouths,
)
from an.characters.brows import (
    BROW_CANVAS,
    BROW_STROKE,
    BROWS_FEATURE,
    Seat,
    brow_path_d,
    seat_above_brows,
)
from an.characters.colour_roles import distinct_literal, normalise_hex
from an.characters.schema import (
    Bone,
    CharacterDescriptor,
    HEAD_ANCHOR,
    LEG_LENGTH,
    MOUTH_SHAPES,
    REFERENCE_HEAD_HEIGHT,
    REQUIRED_PARTS,
)
from an.characters.svg_utils import (
    extract_part,
    extract_pivots,
    normalize_svg,
    raster_size,
    write_svg,
    SVG_NS,
)


# Each part SVG is a self-contained content-centered drawing. The canonical
# `<name>.svg` (built via wrap_dicebear_for_an) is for human inspection /
# silhouette test; the renderer uses these per-part files directly.


# -----------------------------------------------------------------------------
# Variety knobs: palette, build, head scale, hat, sash
# -----------------------------------------------------------------------------

#: The roles ``new_character(palette=...)`` takes. They are `StylePack` role
#: names on purpose: a palette chosen at authoring time and a pack applied at
#: compile time speak one vocabulary, and the factory records each as a colour
#: role so the pack can reach what the palette drew.
PALETTE_ROLES: tuple[str, ...] = ("skin", "hair", "clothing", "leg", "accessory")

#: The roles a head's own art carries. On a head the factory did not draw
#: (DiceBear) they are left untagged everywhere, never half-tagged.
HEAD_ART_ROLES: frozenset[str] = frozenset({"skin", "hair"})

#: The outline every synthesized body part is stroked in. Untagged: it is the
#: drawing's ink, not a costume colour.
OUTLINE_COLOUR: str = "#222222"
#: The shoe, drawn in the leg part. Untagged.
SHOE_COLOUR: str = "#1a1a1a"
#: The pupil, in its own part (or the pre-gaze open eye). Role ``pupil``.
PUPIL_COLOUR: str = "#1a1a1a"
#: Default hand, trouser and brow colours — the literals the factory always drew.
DFLT_HAND_COLOUR: str = "#f1c9a5"
DFLT_LEG_COLOUR: str = "#3a3a4a"
DFLT_BROW_COLOUR: str = "#3a2a20"

#: Hat and sash colours when the palette names no ``accessory``, picked by seed.
_ACCESSORY_TONES: tuple[str, ...] = (
    "#c0392b",  # red
    "#2e86c1",  # blue
    "#27ae60",  # green
    "#8e44ad",  # purple
    "#e67e22",  # orange
    "#34495e",  # slate
)

#: Hats, drawn inside the offline head's 80x80 drawing. These are the hats as
#: DRAWN; where one is WORN is :func:`_hat_seat`'s: lifted (and, if need be,
#: flattened toward its crown) above the brows' acting range at the character's
#: head scale, so a raised brow never lands on a brim (an#252). The face parts
#: are overlays drawn over the head, so a hat reaching lower would wear the
#: brows on its brim. ``{acc}`` is the accessory colour, ``{ink}`` the outline.
_HAT_SVG: dict[str, str] = {
    "none": "",
    "cap": (
        '<path d="M 12 22 C 12 3 68 3 68 22 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        '<path d="M 10 22 Q 40 16 70 22 Q 40 27 10 22 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        '<circle cx="40" cy="4.5" r="2" fill="{acc}" stroke="{ink}" stroke-width="1"/>'
    ),
    "beanie": (
        '<path d="M 11 24 C 11 2 69 2 69 24 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        '<rect x="9" y="17" width="62" height="8" rx="3" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        '<circle cx="40" cy="5.5" r="5" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
    ),
    "bowler": (
        '<path d="M 20 18 C 20 -1 60 -1 60 18 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        '<rect x="20.5" y="13" width="39" height="4" fill="{ink}"/>'
        '<ellipse cx="40" cy="19" rx="27" ry="4" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
    ),
    "bicorne": (
        '<path d="M 4 21 Q 40 -8 76 21 Q 40 13 4 21 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
    ),
}
#: The hats :func:`new_character` can draw.
HATS: tuple[str, ...] = tuple(_HAT_SVG)
DFLT_HAT: str = "none"
#: The views a hat is measured on against the brows (the back shows none).
_BROW_VIEWS: tuple[str, ...] = ("front", "three_quarter", "side")


def _hat_fragment(
    hat: str, view: str, *, accessory: str, seat: str | None = None
) -> str:
    """The hat seen from ``view``, in the head's drawing, worn at ``seat`` (a
    transform; ``None``: where it is drawn). Empty for no hat."""
    if hat == DFLT_HAT:
        return ""
    svg = (
        _HAT_VIEW_SVG.get(view, {})
        .get(hat, _HAT_SVG[hat])
        .format(acc=accessory, ink=OUTLINE_COLOUR)
    )
    return f'<g transform="{seat}">{svg}</g>' if seat else svg


def _hat_seat(hat: str, head_scale: float) -> Seat:
    """Where ``hat`` is worn on a head drawn at ``head_scale``: above the
    brows' acting range in every view that shows a brow
    (:func:`~an.characters.brows.seat_above_brows`), or as near as it gets —
    ``covers`` then says the brows are hidden, and the factory records it.

    Computed from the live expression vocabulary and view poses, so it is
    recorded on the character (``metadata.hat_seat``) and every redraw reads
    the recorded seat, never a recomputed one (a new preset must not change
    where an existing character's hat sits)."""
    if hat == DFLT_HAT:
        return Seat()
    return seat_above_brows(
        {v: _hat_fragment(hat, v, accessory="#000000") for v in _BROW_VIEWS},
        head_scale=head_scale,
    )


# -----------------------------------------------------------------------------
# Hair: a style (how it sits on the head) and a length (how far it falls)
# -----------------------------------------------------------------------------


#: The four-arc circle approximation's handle length, for a unit radius.
_KAPPA: float = 0.5523


def _disc_d(cx: float, cy: float, r: float) -> str:
    """A circle as a closed path of four cubic arcs (no ``<circle>``: the head's
    first circle is its skin, which `add_gaze` reads the lid's tone off)."""
    k = round(r * _KAPPA, 2)
    return (
        f"M {cx - r:g} {cy:g} "
        f"C {cx - r:g} {cy - k:g} {cx - k:g} {cy - r:g} {cx:g} {cy - r:g} "
        f"C {cx + k:g} {cy - r:g} {cx + r:g} {cy - k:g} {cx + r:g} {cy:g} "
        f"C {cx + r:g} {cy + k:g} {cx + k:g} {cy + r:g} {cx:g} {cy + r:g} "
        f"C {cx - k:g} {cy + r:g} {cx - r:g} {cy + k:g} {cx - r:g} {cy:g} Z"
    )


#: Hair styles: ``peak`` (the factory's original hair, a widow's peak — the
#: default), ``bald``, ``bun`` (the hair gathered in a bun on the crown) and
#: ``curly`` (a halo of curls around the crown). Every style keeps the default
#: hairline over the forehead — none draws lower over the brows (tests) — so a
#: hair style never costs brow acting.
HAIR_STYLES: tuple[str, ...] = ("peak", "bald", "bun", "curly")
DFLT_HAIR_STYLE: str = "peak"
#: Hair lengths: ``short`` (nothing below the crown — the default), ``medium``
#: (falling beside the face to the jaw) and ``long`` (past the chin, in locks
#: that keep clear of the neck and the collar).
HAIR_LENGTHS: tuple[str, ...] = ("short", "medium", "long")
DFLT_HAIR_LENGTH: str = "short"

#: The volume a style draws BEHIND the head (only what clears the skull shows):
#: ``{style: {view: [(cx, cy, r), ...]}}``, in the head's 80x80 drawing. The
#: back view mirrors the front; a profile (facing right) carries it to the back.
_HAIR_VOLUME: dict[str, dict[str, tuple[tuple[float, float, float], ...]]] = {
    "bun": {
        "front": ((40, 9, 8),),
        "back": ((40, 9, 8),),
        "side": ((24, 13, 8),),
        "three_quarter": ((30, 10, 8),),
    },
    "curly": {
        "front": (
            (14, 34, 7),
            (18, 23, 8),
            (27, 15, 8),
            (40, 12, 8),
            (53, 15, 8),
            (62, 23, 8),
            (66, 34, 7),
        ),
        "back": (
            (14, 34, 7),
            (18, 23, 8),
            (27, 15, 8),
            (40, 12, 8),
            (53, 15, 8),
            (62, 23, 8),
            (66, 34, 7),
        ),
        "side": ((13, 40, 7), (15, 28, 8), (23, 18, 8), (35, 13, 8), (48, 13, 7)),
        "three_quarter": (
            (13, 38, 7),
            (16, 26, 8),
            (25, 17, 8),
            (37, 12, 8),
            (50, 13, 7),
            (60, 19, 6),
        ),
    },
}
#: Hair below the crown, ``{length: {view: (path, where)}}``: ``behind`` the
#: head (the front, where it shows beside the face) or ``over`` it (the back of
#: the skull, seen from behind or turned away). Locks stop at the head's
#: drawing edge and keep off the middle below the chin, where the collar is.
_HAIR_FALL: dict[str, dict[str, tuple[str, str]]] = {
    "medium": {
        "front": (
            "M 9 44 C 8 20 20 13 40 13 C 60 13 72 20 71 44 L 71 62 Q 67 66 62 61 "
            "L 18 61 Q 13 66 9 62 Z",
            "behind",
        ),
        "back": ("M 12 42 Q 12 14 40 14 Q 68 14 68 42 L 70 64 Q 40 70 10 64 Z", "over"),
        "side": ("M 13 44 Q 10 56 14 64 Q 22 68 30 62 Q 30 54 32 48 Z", "over"),
        "three_quarter": ("M 12 38 Q 8 52 11 63 Q 17 67 22 61 Q 18 50 20 38 Z", "over"),
    },
    "long": {
        "front": (
            "M 8 44 C 7 20 20 13 40 13 C 60 13 73 20 72 44 L 75 76 Q 70 80 64 76 "
            "L 60 62 L 20 62 L 16 76 Q 10 80 5 76 Z",
            "behind",
        ),
        "back": ("M 12 42 Q 12 14 40 14 Q 68 14 68 42 L 73 76 Q 40 80 7 76 Z", "over"),
        "side": ("M 13 44 Q 9 62 12 78 L 28 78 Q 26 62 32 48 Z", "over"),
        "three_quarter": ("M 12 38 Q 7 58 9 78 L 22 78 Q 18 58 20 38 Z", "over"),
    },
}


def _check_hair(hair_style: str, hair_length: str) -> None:
    if hair_style not in HAIR_STYLES:
        raise ValueError(
            f"unknown hair style {hair_style!r}; known: {', '.join(HAIR_STYLES)}"
        )
    if hair_length not in HAIR_LENGTHS:
        raise ValueError(
            f"unknown hair length {hair_length!r}; known: {', '.join(HAIR_LENGTHS)}"
        )
    if hair_style == "bald" and hair_length != DFLT_HAIR_LENGTH:
        raise ValueError(
            f"a bald head has no hair to grow {hair_length}: pass hair_length="
            f"{DFLT_HAIR_LENGTH!r} with hair_style='bald', or another style"
        )


def _hair_layers(
    view: str, *, hair: str, hair_style: str, hair_length: str
) -> tuple[str, str]:
    """``(behind, over)``: the hair a style and a length add to ``view``'s head,
    drawn behind the skull and over it (after the crown hair). Both empty for
    the defaults, which is what keeps a default head byte-identical."""
    behind: list[str] = []
    over: list[str] = []
    fall = _HAIR_FALL.get(hair_length, {}).get(view)
    if fall is not None:
        d, where = fall
        (behind if where == "behind" else over).append(f'<path d="{d}" fill="{hair}"/>')
    discs = _HAIR_VOLUME.get(hair_style, {}).get(view, ())
    if discs:
        d = " ".join(_disc_d(*c) for c in discs)
        behind.append(f'<path d="{d}" fill="{hair}"/>')
    return "".join(behind), "".join(over)


#: The largest head scale accepted — past it the head no longer fits the
#: 1024-unit view box above a regular body.
MAX_HEAD_SCALE: float = 2.5


@dataclass(frozen=True)
class BodyBuild:
    """The proportions of a synthesized body, in view_box units.

    Every length that decides where a part hangs is here, so the bones the
    factory writes and the art it draws are derived from ONE record and cannot
    disagree — a leg's art is exactly ``leg_length`` tall and its bone sits
    ``leg_length`` above the ground, so it hangs from the hip to the ground at
    every build (tests/test_rig_layout.py).
    """

    #: Torso canvas; the drawn body is inset 20 on every side, and the canvas
    #: bottom sits on the hip.
    torso_size: tuple[float, float] = (256, 256)
    torso_radius: float = 40
    #: The gap between the drawn body and the canvas bottom (the hip). The
    #: regular body's 20 leaves a sliver between body and legs; the other
    #: builds close it.
    torso_inset_bottom: float = 20
    #: Sleeve thickness and the arm canvas's length (sleeve + hand).
    arm_width: float = 36
    arm_length: float = 256
    hand_radius: float = 20
    limb_stroke: float = 4
    leg_width: float = 40
    leg_length: float = LEG_LENGTH
    shoe_size: tuple[float, float] = (32, 18)
    #: The shoulder joint (x from the centre line, height above the hip).
    shoulder: tuple[float, float] = (90, 240)
    #: The hip joints' distance from the centre line.
    hip_x: float = 50
    #: The neck's height above the hip; the head hangs above it.
    neck_height: float = 260


#: Named builds. ``regular`` is today's body, number for number.
BUILDS: dict[str, BodyBuild] = {
    "regular": BodyBuild(),
    # Round and low: a wide, heavily rounded body on short legs, stubby arms —
    # the South Park construction.
    "squat": BodyBuild(
        torso_size=(300, 220),
        torso_radius=80,
        torso_inset_bottom=4,
        arm_width=36,
        arm_length=140,
        hand_radius=18,
        leg_width=50,
        leg_length=96,
        shoe_size=(34, 16),
        shoulder=(118, 168),
        hip_x=46,
        neck_height=214,
    ),
    "tall": BodyBuild(
        torso_size=(224, 320),
        torso_radius=36,
        torso_inset_bottom=4,
        arm_width=32,
        arm_length=320,
        hand_radius=18,
        leg_width=36,
        leg_length=380,
        shoe_size=(30, 16),
        shoulder=(80, 304),
        hip_x=44,
        neck_height=324,
    ),
    # A small blocky body with stick limbs — the OverSimplified construction,
    # usually with a big head (`head_scale`).
    "stick": BodyBuild(
        torso_size=(170, 210),
        torso_radius=14,
        torso_inset_bottom=4,
        arm_width=10,
        arm_length=200,
        hand_radius=9,
        limb_stroke=3,
        leg_width=10,
        leg_length=230,
        shoe_size=(15, 7),
        shoulder=(82, 188),
        hip_x=28,
        neck_height=214,
    ),
}
DFLT_BUILD: str = "regular"


def _check_palette(palette: Optional[Mapping[str, str]]) -> dict[str, str]:
    """The palette with every colour normalised; an unknown role or a malformed
    colour is refused here, before anything is written."""
    out: dict[str, str] = {}
    for role, colour in (palette or {}).items():
        if role not in PALETTE_ROLES:
            raise ValueError(
                f"unknown palette role {role!r}; known: {', '.join(PALETTE_ROLES)}"
            )
        out[role] = normalise_hex(colour)
    return out


def _check_build(build: str) -> BodyBuild:
    if build not in BUILDS:
        raise ValueError(f"unknown build {build!r}; known: {', '.join(BUILDS)}")
    return BUILDS[build]


def _bones_for(body: BodyBuild, *, head_scale: float = 1.0) -> list[Bone]:
    """The default rig's seven bones placed for ``body`` (same names, same
    parents, same pivots — only the lengths move).

    A scaled head hangs lower below its neck (it is anchored at
    :data:`~an.characters.schema.HEAD_ANCHOR`), so the neck is raised by the
    extra overhang: the head overlaps the collar by the same amount at every
    scale instead of swallowing a stick figure's body.
    """
    sx, sy = body.shoulder
    neck = (
        body.neck_height
        + (head_scale - 1.0) * (1.0 - HEAD_ANCHOR[1]) * REFERENCE_HEAD_HEIGHT
    )
    return [
        Bone(name="root", parent=None, x=512, y=980, pivot="root"),
        Bone(name="torso", parent="root", x=0, y=-body.leg_length, pivot="hip"),
        Bone(name="head", parent="torso", x=0, y=-round(neck, 3), pivot="neck"),
        Bone(name="arm_l", parent="torso", x=-sx, y=-sy, pivot="shoulder_l"),
        Bone(name="arm_r", parent="torso", x=sx, y=-sy, pivot="shoulder_r"),
        Bone(
            name="leg_l",
            parent="root",
            x=-body.hip_x,
            y=-body.leg_length,
            pivot="hip_l",
        ),
        Bone(
            name="leg_r", parent="root", x=body.hip_x, y=-body.leg_length, pivot="hip_r"
        ),
    ]


@dataclass(frozen=True)
class _Looks:
    """Every colour one character is drawn in, resolved once from the seed and
    the palette — and made distinct within each part, so each role's literal is
    an exact swap key (:func:`~an.characters.colour_roles.distinct_literal`)."""

    head_svg: str
    head_roles: dict[str, str]
    clothing: str
    accent: str
    hand: str
    leg: str
    brow: str
    accessory: str


def _resolve_looks(
    seed: str,
    palette: Mapping[str, str],
    *,
    hat: str,
    hat_seat: str | None = None,
    hair_style: str = DFLT_HAIR_STYLE,
    hair_length: str = DFLT_HAIR_LENGTH,
) -> _Looks:
    h = _stable_hash(seed)
    ink = OUTLINE_COLOUR
    # The head keeps its own two tables (see `_fallback_face_svg`); the body
    # keeps `_palette_for_seed`'s. That the two disagree is the pre-knob
    # behaviour, kept so a default character is byte-identical — a palette
    # `skin`/`hair` is what makes them agree.
    skin = palette.get("skin") or _SKIN_TONES[h % len(_SKIN_TONES)]
    hair = palette.get("hair") or _HAIR_TONES[(h >> 16) % len(_HAIR_TONES)]
    _, seed_clothing, seed_accent = _palette_for_seed(seed)
    acc = (
        palette.get("accessory") or _ACCESSORY_TONES[(h >> 32) % len(_ACCESSORY_TONES)]
    )

    head_skin = distinct_literal(skin, {ink})
    head_hair = distinct_literal(hair, {head_skin})
    head_acc = distinct_literal(acc, {head_skin, head_hair, ink})
    head_roles = {head_skin: "skin", head_hair: "hair"}
    if hat != DFLT_HAT:
        head_roles[head_acc] = "accessory"

    clothing = distinct_literal(palette.get("clothing") or seed_clothing, {ink})
    accent = distinct_literal(palette.get("hair") or seed_accent, {clothing, ink})
    hand = distinct_literal(palette.get("skin") or DFLT_HAND_COLOUR, {clothing, ink})
    return _Looks(
        head_svg=_fallback_face_svg(
            seed,
            skin=head_skin,
            hair=head_hair,
            hat=hat,
            accessory=head_acc,
            hat_seat=hat_seat,
            hair_style=hair_style,
            hair_length=hair_length,
        ),
        head_roles=head_roles,
        clothing=clothing,
        accent=accent,
        hand=hand,
        leg=distinct_literal(palette.get("leg") or DFLT_LEG_COLOUR, {SHOE_COLOUR}),
        brow=normalise_hex(palette.get("hair") or DFLT_BROW_COLOUR),
        accessory=distinct_literal(acc, {clothing, accent, ink}),
    )


def _scale_face(char_dir: Path, scale: float) -> None:
    """Scale every face part with the head: its art, its offset from the neck,
    and the pupil's travel — so a big head keeps its face in proportion.

    The face offsets are measured from the neck for a head
    :data:`~an.characters.schema.REFERENCE_HEAD_HEIGHT` tall, and a head hangs
    from the neck at a fixed anchor, so scaling the head by ``s`` moves every
    face point by exactly ``s`` — which is why one factor does it all. Recorded
    as ``metadata.head_scale`` so `add_gaze` and `an character mouths` redraw at
    the same size.
    """
    from an.ir.migrate import migrate

    desc_path = char_dir / "character.json"
    raw = json.loads(desc_path.read_text(encoding="utf-8"))
    desc = CharacterDescriptor.model_validate(migrate(raw, kind="CharacterDescriptor"))
    face_slots = {s.name for s in desc.slots if s.bone == "head" and s.name != "head"}
    paths: set[str] = set()
    for skin in desc.skins.values():
        for slot_name, attachments in skin.slots.items():
            if slot_name not in face_slots:
                continue
            for att in attachments.values():
                att.x = round(att.x * scale, 3)
                att.y = round(att.y * scale, 3)
                paths.add(att.path)
    scale_part_files([char_dir / p for p in sorted(paths)], scale)
    if desc.gaze_travel:
        desc.gaze_travel = {k: round(v * scale, 3) for k, v in desc.gaze_travel.items()}
    desc.metadata["head_scale"] = scale
    desc_path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")


def scale_part_files(paths, scale: float) -> None:
    """Rewrite each part SVG's root size by ``scale`` (its drawing untouched):
    the compiler draws a part at its own raster size, so that IS its size on
    screen. Missing files are skipped."""
    for path in paths:
        path = Path(path)
        if not path.is_file() or scale == 1.0:
            continue
        data = path.read_bytes()
        svg = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")  # as read_text reads
        _, h = raster_size(path)
        _drawn.write_derived_text(
            path, data, _sized_to_height(svg, h * scale), encoding="utf-8"
        )


def stage_extent(desc: CharacterDescriptor) -> dict[str, float]:
    """How far a character's art reaches above and below its stage point, in
    scene pixels at ``stage.scale: 1``: ``{"top", "feet", "height"}``.

    The stage point (``stage.at``) is not the feet: the compiler places a rig
    by the middle of its bones' extent, between the neck and the feet, so
    where the feet land depends on the build and the head scale (a squat
    figure's feet sit about half as far below the point as a tall one's).
    Read from the compiler's own placement rule and the head's art, so this is
    what the compiled scene does, not a second guess at it. Multiply by
    ``stage.scale``. The head reaches its drawing's top edge (a hat stays
    inside it).

    >>> e = stage_extent(CharacterDescriptor(name="c"))
    >>> round(e["top"]), round(e["feet"])
    (169, 94)
    """
    from an.adapters.cutout.compile import (
        SCENE_PX_PER_VIEW_BOX,
        _bone_positions,
        _rig_origin,
    )

    bones = _bone_positions(desc)
    origin_y = _rig_origin(bones)[1]
    k = SCENE_PX_PER_VIEW_BOX / float(desc.view_box[3] or 1)
    head_scale = float(desc.metadata.get("head_scale") or 1.0)
    head = desc.skins["default"].slots["head"]
    anchor_y = next(iter(head.values())).anchor[1]
    top = bones["head"][1] - anchor_y * REFERENCE_HEAD_HEIGHT * head_scale
    feet = bones["root"][1]
    return {
        "top": round((origin_y - top) * k, 1),
        "feet": round((feet - origin_y) * k, 1),
        "height": round((feet - top) * k, 1),
    }


def _check_style_is_usable(style: str, *, acknowledge_attribution: bool) -> None:
    """Refuse a style whose licence puts a duty on the user, unless acknowledged.

    Not paternalism: `an` produces videos its user ships, and CC BY obliges them
    to credit an artist they have never heard of, for art they did not know was
    third-party. Making that an explicit flag is the difference between an
    informed choice and an unknowing violation.

    The default style is CC0, so the common path never sees this.
    """
    if not requires_acknowledgement(style) or acknowledge_attribution:
        return
    lic = DICEBEAR_STYLE_LICENSES.get(style)
    owed = attribution_for(style) or "an attribution you must display"
    raise ValueError(
        f"style {style!r} is licensed {lic.license if lic else 'UNVERIFIED'}, "
        "which obliges whoever ships the rendered video to credit the artist. "
        "Accept that duty with acknowledge_attribution=True (or "
        "--acknowledge-attribution on the CLI); the record is "
        "then written to the character's `source` field and `an credits` will "
        f"render it. What you would owe:\n  {owed}\n"
        f"For no obligation at all, use the default style "
        f"({DICEBEAR_DEFAULT_STYLE!r}, CC0)."
    )


def _records_what_it_drew(func):
    """Run a drawing function with its writes logged, then record what it drew (an#269).

    For every function of the factory that draws into a character folder and
    stamps what it drew — ``new_character``, ``add_gaze``, ``add_views`` (and
    ``an character mouths``, through :func:`recording_drawn`): a factory stamp
    counts as the factory's only when this record confirms it (review-288 B1).
    The function returns the character's descriptor path.
    """

    @functools.wraps(func)
    def run(*args, **kwargs):
        with _drawn.drawing() as wrote:
            desc_path = func(*args, **kwargs)
            _record_drawn(Path(desc_path).parent, wrote)
        return desc_path

    return run


@contextlib.contextmanager
def recording_drawn(char_dir: str | Path):
    """Log what the body writes, then record the factory-stamped bytes it wrote at ``char_dir``.

    For a drawing path outside this module (``an character mouths``): only
    bytes written through :mod:`an.characters.drawn` inside the block, and
    stamped by the factory, are recorded.
    """
    with _drawn.drawing() as wrote:
        yield
        _record_drawn(Path(char_dir), wrote)


@_records_what_it_drew
def new_character(
    out_dir: str | Path,
    *,
    name: str,
    seed: Optional[str] = None,
    style: str = DICEBEAR_DEFAULT_STYLE,
    voice_ref: Optional[str] = None,
    use_dicebear: bool = True,
    acknowledge_attribution: bool = False,
    overwrite: bool = False,
    mouth_variants: Optional[dict[str, float]] = None,
    gaze: bool = True,
    palette: Optional[Mapping[str, str]] = None,
    build: str = DFLT_BUILD,
    head_scale: float = 1.0,
    hat: str = DFLT_HAT,
    sash: bool = False,
    views: bool = True,
    hair_style: str = DFLT_HAIR_STYLE,
    hair_length: str = DFLT_HAIR_LENGTH,
) -> Path:
    """Build a complete character on disk.

    **Variety knobs** (every default reproduces the pre-knob character byte for
    byte, which a golden test holds):

    - ``palette`` — ``{role: "#rrggbb"}`` over :data:`PALETTE_ROLES` (``skin``,
      ``hair``, ``clothing``, ``leg``, ``accessory``) — the SAME role names a
      :class:`~an.styles.StylePack` uses. Unset roles keep the seed's colours.
      ``skin`` also paints the hands and the gaze lid; ``hair`` the brows and
      the collar. On a DiceBear head only the body follows (its face is baked).
    - ``build`` — a key of :data:`BUILDS`: ``regular``, ``squat`` (round body,
      short legs), ``tall``, ``stick`` (small blocky body, stick limbs).
    - ``head_scale`` — the head and its whole face (eyes, brows, mouths, their
      offsets, the pupil travel) scaled together, so a big head keeps its face.
    - ``hat`` — a key of :data:`HATS` (offline head only), in ``accessory``,
      worn above the brows' acting range at this head scale (an#252): lifted,
      and flattened toward its crown when lifting is not enough. A hat that
      still covers the brows (a very small head) is recorded in the
      descriptor's ``occluded``, so the character does not afford
      ``face.brows`` and expressions fall to the lids, gaze and mouth.
    - ``hair_style`` — :data:`HAIR_STYLES`: ``peak`` (the default), ``bald``,
      ``bun``, ``curly``; ``hair_length`` — :data:`HAIR_LENGTHS`: ``short``
      (the default), ``medium``, ``long`` (offline head only). Drawn in the
      ``hair`` role (the palette's ``hair`` colours them), in every view.
    - ``sash`` — a diagonal band across the torso, in ``accessory``.
    - ``views`` (an#197) — draw the turnaround: ``back``, ``side`` (a profile
      facing the viewer's right) and ``three_quarter`` beside the front, as a
      ``view`` swap set with a pose per view (:func:`add_views`), so
      :func:`an.motion.turn` can turn the character around. Offline head only
      (a DiceBear face is baked into its art); ignored for a DiceBear head.
      Additive: a shot that never sets a view renders exactly as without it.

    Every colour the factory draws in a role is recorded in the descriptor's
    ``colour_roles`` so a style pack can recolour it later (palette swapping,
    :mod:`an.characters.colour_roles`).

    ``gaze`` (an#99) adds the eye stack — sclera and pupil slots under each
    lid, a filled closed lid, the ``gaze_travel`` clamp — through
    :func:`add_gaze`, so `gaze_x`/`gaze_y` and the ambient saccades reach the
    pupils. Off, the eye is the single pre-stack drawing.

    ``mouth_variants`` (an#98) — ``{form: smile offset}`` — writes one more
    9-shape mouth set per form (``mouth_<shape>_<form>.svg``) and declares it
    as the ``viseme@<form>`` swap set, with its attachments in the default
    skin's ``mouth`` slot, so an expression preset preferring that form
    selects it. ``None`` means :data:`~an.characters.mouth_set.DEFAULT_MOUTH_VARIANTS`
    (happy, sad); ``{}`` means the neutral set only.

    Steps:

    1. Fetch a DiceBear avatar (skip if ``use_dicebear=False`` — useful for
       offline tests).
    2. Wrap it into the canonical ``an`` cutout SVG (skeleton + illustration
       groups), saved as ``<name>.svg``.
    3. Slice each part into ``parts/<part>.svg``.
    4. Write the 9-shape default mouth set into ``parts/mouth/``.
    5. Synthesize a few derived parts (open/closed eyes, brows) so the
       character is complete out of the box.
    6. Emit a ``character.json`` descriptor.

    Returns the path to the created ``character.json``.

    Raises :class:`FileExistsError` if ``out_dir/name`` already exists and
    ``overwrite=False``.
    """
    palette_ = _check_palette(palette)
    body = _check_build(build)
    if not (isinstance(head_scale, (int, float)) and 0 < head_scale <= MAX_HEAD_SCALE):
        raise ValueError(
            f"head_scale must be in (0, {MAX_HEAD_SCALE:g}]; got {head_scale!r}"
        )
    if hat not in HATS:
        raise ValueError(f"unknown hat {hat!r}; known: {', '.join(HATS)}")
    _check_hair(hair_style, hair_length)
    if use_dicebear and (
        hat != DFLT_HAT
        or (hair_style, hair_length) != (DFLT_HAIR_STYLE, DFLT_HAIR_LENGTH)
    ):
        raise ValueError(
            "hats and hair are drawn for the offline head (its geometry is known); "
            "a DiceBear avatar's is not. Pass use_dicebear=False (`--offline`)."
        )
    out = Path(out_dir) / name
    if out.exists():
        if not overwrite:
            raise FileExistsError(out)
        shutil.rmtree(out)
    out.mkdir(parents=True)
    parts_dir = out / "parts"
    parts_dir.mkdir()
    mouth_dir = parts_dir / "mouth"
    mouth_dir.mkdir()

    # Step 1 & 2: source art
    seed_used = seed or name
    seat = _hat_seat(hat, float(head_scale))
    looks = _resolve_looks(
        seed_used,
        palette_,
        hat=hat,
        hat_seat=seat.transform,
        hair_style=hair_style,
        hair_length=hair_length,
    )
    metadata: dict[str, object] = {"art_provenance": "fallback_geometric"}
    source: AssetSource | None = None
    if use_dicebear:
        _check_style_is_usable(style, acknowledge_attribution=acknowledge_attribution)
        try:
            avatar = fetch_dicebear(seed_used, style=style)
            metadata = {
                "art_provenance": "dicebear",
                "dicebear_style": style,
                "dicebear_seed": seed_used,
            }
            source = dicebear_source(style, seed=seed_used)
        except RuntimeError as e:
            avatar = looks.head_svg
            metadata = {
                "art_provenance": "fallback_geometric",
                "dicebear_error": str(e),
            }
    else:
        avatar = looks.head_svg
    head_is_ours = avatar is looks.head_svg

    canonical = wrap_dicebear_for_an(avatar, name=name)
    canonical_path = out / f"{name}.svg"
    _drawn.write_text(canonical_path, canonical, encoding="utf-8")

    # Step 3: write self-contained per-part SVGs (centered, sized to fill
    # their own canvas). Done independently of the canonical for clean
    # texture loading in Pixi.
    tree = normalize_svg(canonical_path)
    pivots = extract_pivots(tree)
    roles: dict[str, dict[str, str]] = {}
    _write_head_part(
        parts_dir / "head.svg", avatar, height=REFERENCE_HEAD_HEIGHT * head_scale
    )
    if head_is_ours:
        roles["parts/head.svg"] = looks.head_roles
    roles["parts/torso.svg"] = _write_torso_part(
        parts_dir / "torso.svg",
        clothing=looks.clothing,
        accent=looks.accent,
        body=body,
        sash=looks.accessory if sash else None,
    )
    for side in ("l", "r"):
        roles[f"parts/arm_{side}.svg"] = _write_arm_part(
            parts_dir / f"arm_{side}.svg",
            side=side,
            color=looks.clothing,
            hand=looks.hand,
            body=body,
        )
        roles[f"parts/leg_{side}.svg"] = _write_leg_part(
            parts_dir / f"leg_{side}.svg", side=side, color=looks.leg, body=body
        )

    # Step 4: default mouths, plus the form variants (an#98)
    variants = (
        DEFAULT_MOUTH_VARIANTS if mouth_variants is None else dict(mouth_variants)
    )
    write_default_mouths(mouth_dir, variants=variants)

    # Step 5: derived parts (eyes, brows)
    _synthesize_eye_open(parts_dir / "eye_l_open.svg", side="l")
    _synthesize_eye_closed(parts_dir / "eye_l_closed.svg", side="l")
    _synthesize_eye_open(parts_dir / "eye_r_open.svg", side="r")
    _synthesize_eye_closed(parts_dir / "eye_r_closed.svg", side="r")
    _synthesize_brow(parts_dir / "brow_l.svg", side="l", color=looks.brow)
    _synthesize_brow(parts_dir / "brow_r.svg", side="r", color=looks.brow)
    for side in ("l", "r"):
        roles[f"parts/eye_{side}_open.svg"] = {PUPIL_COLOUR: "pupil"}
        roles[f"parts/brow_{side}.svg"] = {looks.brow: "hair"}

    # Step 6: descriptor. `face_overlay` is DECLARED here (an#87): a DiceBear
    # avatar has its face baked into the head SVG, so the overlay face parts
    # and the viseme channel are suppressed by this fact — the compiler no
    # longer sniffs metadata.art_provenance, which is provenance again.
    if not head_is_ours:
        # A DiceBear head carries its own skin and hair, which this factory did
        # not draw and cannot tag. Tagging them on the body alone would let a
        # pack repaint the hands and brows and not the face — so the body
        # keeps them untagged too, and the compiler says the pack could not
        # reach this rig's skin/hair.
        roles = {
            part: kept
            for part, m in roles.items()
            if (kept := {lit: r for lit, r in m.items() if r not in HEAD_ART_ROLES})
        }
    descriptor = CharacterDescriptor(
        name=name,
        display_name=name.title(),
        voice_ref=voice_ref,
        source_svg=f"{name}.svg",
        face_overlay=metadata.get("art_provenance") != "dicebear",
        metadata={**metadata, "pivots_detected": list(pivots.keys())},
        source=source,
        colour_roles=roles,
        **(
            {}
            if build == DFLT_BUILD and head_scale == 1.0
            else {"bones": _bones_for(body, head_scale=head_scale)}
        ),
    )
    if seat.covers and head_is_ours:
        # Measured, not guessed: even worn as high and as flat as it goes, the
        # hat overlaps the brows' acting range — said where the capability
        # analyser reads it (`face.brows`), never left to a render to show.
        descriptor.occluded = {
            BROWS_FEATURE: f"the {hat} hat at head_scale {head_scale:g}"
        }
    declare_mouth_variants(descriptor, variants)
    descriptor.metadata["seed"] = seed_used
    # The knobs, recorded only when set — so a default character's descriptor
    # carries nothing it did not carry before them.
    for key, value, default in (
        ("build", build, DFLT_BUILD),
        ("hat", hat, DFLT_HAT),
        # Where the hat was worn, as drawn: a redraw reads this, never a
        # recomputation that a later preset or pose could move (review-278 M2).
        ("hat_seat", seat.transform, None),
        ("hair_style", hair_style, DFLT_HAIR_STYLE),
        ("hair_length", hair_length, DFLT_HAIR_LENGTH),
        ("sash", sash, False),
        ("palette", dict(palette_), {}),
    ):
        if value != default:
            descriptor.metadata[key] = value
    desc_path = out / "character.json"
    desc_path.write_text(descriptor.model_dump_json(indent=2), encoding="utf-8")
    if gaze and descriptor.face_overlay:
        add_gaze(out)  # the lid's fill is read off the head art it just wrote
    if head_scale != 1.0:
        _scale_face(out, head_scale)
    if views and head_is_ours:
        add_views(out)
    # Last, so every part is stamped with the bytes it finally has. A DiceBear
    # head is not this factory's drawing: it keeps the descriptor's source.
    stamp_factory_parts(
        out,
        _attachment_paths(out) - ({"parts/head.svg"} if not head_is_ours else set()),
    )
    if source is None:
        # The descriptor says who made the character (an#251): the factory,
        # pinned to the drawing the parts were cut from.
        stamp_factory_descriptor(out)
    else:
        # DiceBear's source speaks only for DiceBear's bytes (review-259 S1):
        # pinned on the head it drew and on the drawing wrapping it.
        stamp_generated_head(out, source)
    return desc_path


#: The provider of every per-part source the factory stamps on what it draws.
FACTORY_PROVIDER: str = "an character factory"
#: The licence of the factory's own drawings: no rights to clear.
FACTORY_LICENSE: str = "cc0-1.0"
#: Who the factory's descriptor-level source names as the author.
FACTORY_AUTHOR: str = "an (generated locally)"


def factory_source(data: bytes) -> AssetSource:
    """The per-part source of a part this factory drew, pinned to its bytes.

    >>> factory_source(b"<svg/>").license, len(factory_source(b"<svg/>").sha256)
    ('cc0-1.0', 64)
    """
    return AssetSource(
        provider=FACTORY_PROVIDER,
        license=FACTORY_LICENSE,
        sha256=hashlib.sha256(data).hexdigest(),
        cost_usd=0.0,
    )


def factory_descriptor_source(source_svg: bytes) -> AssetSource:
    """The descriptor-level source of a character this factory drew, pinned to its drawing.

    The digest is that of the descriptor's ``source_svg`` — the drawing every
    part was cut from. Like a part stamp it speaks only for bytes it pins: the
    asset library and ``an credits`` read every file of the character that no
    stamp pins (a part re-carved later, a file added by hand) as UNVERIFIED,
    never as the factory's (:func:`an.credits._part_credits`).

    >>> s = factory_descriptor_source(b"<svg/>")
    >>> (s.provider, s.license, len(s.sha256))
    ('an character factory', 'cc0-1.0', 64)
    """
    return AssetSource(
        provider=FACTORY_PROVIDER,
        license=FACTORY_LICENSE,
        author=FACTORY_AUTHOR,
        sha256=hashlib.sha256(source_svg).hexdigest(),
        cost_usd=0.0,
    )


def _record_drawn(char_dir: Path, wrote: Mapping[str, str]) -> None:
    """Record on this machine that the factory drew the stamped bytes at ``char_dir`` (an#269).

    Called ONLY by :func:`new_character`, at its end. ``wrote`` is the log of
    what this call itself wrote, ``{resolved path: sha256}`` of the bytes as
    they were written, computed in memory (:mod:`an.characters.drawn`). A
    digest the factory's own stamp pins there — per part, and the
    descriptor's on the drawing — is recorded only if it is exactly what this
    call wrote at that path: a file swapped in while it ran is not recorded,
    whatever the folder holds when it finishes. What
    verifies a factory stamp in the asset library
    (:func:`an.library.api.factory_drew`): the public stamping functions never
    record, so stamping bytes the factory did not draw (a carved head)
    verifies nothing (review-269 B2). If the record cannot be written, the
    stamps stand unverified — the stricter reading — and a warning says so.
    """
    import warnings

    from an.credits import is_factory_stamp
    from an.library.registry import RegistryError, record_generated

    raw = json.loads((char_dir / "character.json").read_text(encoding="utf-8"))
    stamps = [(raw.get("source_svg"), raw.get("source"))] + [
        (att.get("path"), att.get("source"))
        for skin in (raw.get("skins") or {}).values()
        for slot in (skin.get("slots") or {}).values()
        for att in slot.values()
        if isinstance(att, dict)
    ]
    digests = set()
    for rel, stamp in stamps:
        if not rel or not is_factory_stamp(stamp) or not stamp.get("sha256"):
            continue
        if wrote.get(str((char_dir / rel).resolve())) == stamp["sha256"]:
            digests.add(stamp["sha256"])
    try:
        record_generated(sorted(digests), generator=FACTORY_PROVIDER)
    except RegistryError as e:
        warnings.warn(
            f"{e}; the character is stamped, but its bytes are not recorded as the "
            "factory's, so an older unlabelled asset holding the same bytes keeps "
            "it `unknown` in the asset library",
            stacklevel=3,
        )


def stamp_factory_descriptor(char_dir: str | Path) -> Path:
    """Record the factory as the source of the character it just drew at ``char_dir``.

    Only a descriptor that declares no source is stamped (a DiceBear head
    carries DiceBear's); the stamp pins the bytes of its ``source_svg``. Called
    by :func:`new_character` on what it has just drawn, never on a character
    someone may have edited since.
    """
    from an.characters.schema import CharacterDescriptor
    from an.ir.migrate import migrate

    char_dir = Path(char_dir)
    desc_path = char_dir / "character.json"
    raw = json.loads(desc_path.read_text(encoding="utf-8"))
    desc = CharacterDescriptor.model_validate(migrate(raw, kind="CharacterDescriptor"))
    drawing = char_dir / (desc.source_svg or "")
    if desc.source is not None or not desc.source_svg or not drawing.is_file():
        return desc_path
    desc.source = factory_descriptor_source(drawing.read_bytes())
    desc_path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")
    return desc_path


def stamp_generated_head(char_dir: str | Path, source: AssetSource) -> Path:
    """Pin a generator's ``source`` (DiceBear's) to the bytes it produced at ``char_dir``.

    The head part(s) the generator drew (``parts/head.svg``) carry the source
    with their own digest, and the descriptor carries it with the digest of its
    ``source_svg``. Like the factory's stamps, it then speaks only for those
    bytes: a part re-carved since, or a file added, is UNVERIFIED in ``an
    credits`` and ``unknown`` in the asset library. Called by
    :func:`new_character` on what it has just written.
    """
    from an.characters.schema import CharacterDescriptor
    from an.ir.migrate import migrate

    char_dir = Path(char_dir)
    desc_path = char_dir / "character.json"
    raw = json.loads(desc_path.read_text(encoding="utf-8"))
    desc = CharacterDescriptor.model_validate(migrate(raw, kind="CharacterDescriptor"))

    def pinned(path: Path) -> AssetSource:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return source.model_copy(update={"sha256": digest})

    for skin in desc.skins.values():
        for attachments in skin.slots.values():
            for att in attachments.values():
                file = char_dir / att.path
                if (
                    att.path == "parts/head.svg"
                    and att.source is None
                    and file.is_file()
                ):
                    att.source = pinned(file)
    drawing = char_dir / (desc.source_svg or "")
    if desc.source_svg and drawing.is_file():
        desc.source = pinned(drawing)
    desc_path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")
    return desc_path


def _attachment_paths(char_dir: Path) -> set[str]:
    """Every attachment path the descriptor at ``char_dir`` names."""
    raw = json.loads((char_dir / "character.json").read_text(encoding="utf-8"))
    return {
        att["path"]
        for skin in (raw.get("skins") or {}).values()
        for attachments in (skin.get("slots") or {}).values()
        for att in attachments.values()
        if isinstance(att, dict) and att.get("path")
    }


def stamp_factory_parts(
    char_dir: str | Path,
    paths: "set[str]",
    *,
    skip: tuple[str, ...] = (),
) -> Path:
    """Give each part the factory drew a ``cc0`` per-part source pinned to its digest.

    Rights in the asset library attach to the BYTES (an#236): a file is as
    restricted as the strictest thing any library says about its SHA-256, and an
    asset-level licence speaks for every file the asset does not itemise. The
    factory's parts are byte-identical across characters (the default mouths,
    the eyes), so without this stamp a carved character built on a factory body
    would make every other character's shared parts private. The stamp pins the
    digest, so a part later re-drawn or re-carved no longer matches it and stops
    being itemised as the factory's — the stamp cannot launder new bytes.

    paths: the relative paths this call has just DRAWN — required (an#249
        R4-N1): a stamp says "the factory made these bytes", so only the code
        that made them may write it. Stamping every part by default would label
        a part re-carved since as the factory's ``cc0``. A part carrying some
        other provider's source is never re-stamped.
    """
    from an.characters.schema import CharacterDescriptor
    from an.ir.migrate import migrate

    char_dir = Path(char_dir)
    desc_path = char_dir / "character.json"
    raw = json.loads(desc_path.read_text(encoding="utf-8"))
    desc = CharacterDescriptor.model_validate(migrate(raw, kind="CharacterDescriptor"))
    for skin in desc.skins.values():
        for attachments in skin.slots.values():
            for att in attachments.values():
                file = char_dir / att.path
                if (
                    att.path in skip
                    or att.path not in paths
                    or not file.is_file()
                    or (
                        att.source is not None
                        and att.source.provider != FACTORY_PROVIDER
                    )
                ):
                    continue
                att.source = factory_source(file.read_bytes())
    desc_path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")
    return desc_path


def declare_mouth_variants(
    descriptor: CharacterDescriptor, variants: dict[str, float]
) -> None:
    """Declare a ``viseme@<form>`` set per variant on ``descriptor`` — the set's
    keys map to ``mouth_<shape>_<form>`` attachments, which are added to the
    default skin's ``mouth`` slot with the neutral mouth's geometry. The
    neutral set is the SSOT for which shapes exist; a variant mirrors it.
    """
    from an.characters.schema import VISEME_CHANNEL

    neutral = descriptor.asset_sets.get(VISEME_CHANNEL) or {}
    skin = descriptor.skins.get("default")
    if skin is None or "mouth" not in skin.slots:
        return
    mouth_slot = skin.slots["mouth"]
    for form in variants:
        key_map: dict[str, str] = {}
        for key, attachment in neutral.items():
            # From the KEY, never the attachment name: a promoted hand rig maps
            # `X` to `mouth_shut`, and only `mouth_x_<form>.svg` is ever drawn.
            shape = key.lower()
            if shape not in MOUTH_SHAPES:
                continue
            variant_name = mouth_attachment_name(shape, form)
            template = mouth_slot.get(attachment)
            if template is None:
                continue
            mouth_slot[variant_name] = template.model_copy(
                update={"path": f"parts/mouth/{variant_name}.svg"}
            )
            key_map[key] = variant_name
        if key_map:
            descriptor.asset_sets[f"{VISEME_CHANNEL}@{form}"] = key_map


# -----------------------------------------------------------------------------
# Tiny SVG synthesizers for derived parts (used as offline-friendly defaults)
# -----------------------------------------------------------------------------


#: Hand-picked skin tones in the typical illustrative cartoon range
#: (warm pale → deep brown). Picked so any pair tends to read as distinct.
_SKIN_TONES: tuple[str, ...] = (
    "#fbe1c1",  # pale warm
    "#f4c89a",  # peach
    "#e8b687",  # tan
    "#d8a47f",  # warm tan
    "#c08a5a",  # brown
    "#8b5a3b",  # deep brown
    "#fce0c8",  # very pale
    "#f1c9a5",  # neutral light
)

#: Hair tones (dark earth + a couple of stylized colors).
_HAIR_TONES: tuple[str, ...] = (
    "#1a1a1a",  # near-black
    "#3b2a1a",  # dark brown
    "#5e3a1f",  # brown
    "#a8743f",  # ginger
    "#d4a017",  # blonde
    "#3a2a40",  # dark stylized purple
)


def _fallback_face_svg(
    seed: str,
    *,
    skin: str | None = None,
    hair: str | None = None,
    hat: str = "none",
    accessory: str | None = None,
    hat_seat: str | None = None,
    hair_style: str = DFLT_HAIR_STYLE,
    hair_length: str = DFLT_HAIR_LENGTH,
) -> str:
    """Tiny fallback face SVG used when DiceBear is unavailable.

    Deterministic: same seed → same face (skin tone + hair color picked
    from hand-curated palettes via stable hash, unless given). Crucially: NO eyes /
    brows / mouth baked in — those are added by the overlay slots so
    they can blink and lip-sync. Phase 11d fix for the "four eyes" bug.

    ``hat`` (a key of :data:`HATS`) is drawn over the hair in ``accessory``,
    worn at ``hat_seat`` (:func:`_hat_seat`); ``hair_style`` and
    ``hair_length`` (:data:`HAIR_STYLES`, :data:`HAIR_LENGTHS`) shape the hair.
    The defaults draw exactly the original head.
    """
    h = _stable_hash(seed)
    skin = skin or _SKIN_TONES[h % len(_SKIN_TONES)]
    hair = hair or _HAIR_TONES[(h >> 16) % len(_HAIR_TONES)]
    hat_svg = _hat_fragment(
        hat,
        "front",
        accessory=accessory or _ACCESSORY_TONES[(h >> 32) % len(_ACCESSORY_TONES)],
        seat=hat_seat,
    )
    hat_line = f"\n          {hat_svg}" if hat_svg else ""
    behind, over = _hair_layers(
        "front", hair=hair, hair_style=hair_style, hair_length=hair_length
    )
    behind_line = f"\n          {behind}" if behind else ""
    crown_line = (
        ""
        if hair_style == "bald"
        else f'\n          <path d="{_CROWN_HAIR_D}" fill="{hair}"/>'
    )
    over_line = f"\n          {over}" if over else ""
    return textwrap.dedent(
        f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80">{behind_line}
          <circle cx="40" cy="44" r="28" fill="{skin}"/>{crown_line}{over_line}{hat_line}
        </svg>"""
    )


#: The crown hair of the front head (every style but ``bald``): the hairline.
_CROWN_HAIR_D: str = "M 12 36 Q 40 4 68 36 L 60 24 L 40 14 L 20 24 Z"


#: The eye's geometry in its 64x32 canvas, shared by the four synthesizers so
#: the sclera, the pupil and the lid outline agree (an#99).
EYE_CANVAS: tuple[int, int] = (64, 32)
EYE_CENTRE: tuple[int, int] = (32, 16)
EYE_RX, EYE_RY = 14, 10
PUPIL_R: int = 5
#: The parts a rig gains with `an character add-gaze`. Optional — never in
#: `REQUIRED_PARTS`: a pre-Wave-6 rig without them still renders, and gaze is
#: a no-op on it.
GAZE_PARTS: tuple[str, ...] = ("sclera_l", "sclera_r", "pupil_l", "pupil_r")


def _eye_svg(inner: str, *, gid: str) -> str:
    w, h = EYE_CANVAS
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f'<g id="{gid}">{inner}</g></svg>'
    )


def _synthesize_eye_open(path: Path, *, side: str, outline_only: bool = False) -> Path:
    """The open eye. ``outline_only`` (the gaze stack, an#99) draws the outline
    with a transparent interior, so the sclera and pupil slots beneath show
    through; the default keeps the pre-stack single drawing (white + pupil)."""
    cx, cy = EYE_CENTRE
    if outline_only:
        inner = f'<ellipse cx="{cx}" cy="{cy}" rx="{EYE_RX}" ry="{EYE_RY}" fill="none" stroke="#222" stroke-width="2"/>'
    else:
        inner = (
            f'<ellipse cx="{cx}" cy="{cy}" rx="{EYE_RX}" ry="{EYE_RY}" fill="#ffffff" stroke="#222" stroke-width="2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{PUPIL_R}" fill="#1a1a1a"/>'
        )
    _drawn.write_text(path, _eye_svg(inner, gid=f"eye_{side}_open"), encoding="utf-8")
    return path


def _synthesize_eye_closed(path: Path, *, side: str, fill: str | None = None) -> Path:
    """The closed eye. With ``fill`` (the gaze stack) it is a FILLED skin-tone
    lid — a stroke-only closed eye would show the pupil through it."""
    cx, cy = EYE_CENTRE
    lid = ""
    if fill is not None:
        lid = f'<ellipse cx="{cx}" cy="{cy}" rx="{EYE_RX}" ry="{EYE_RY}" fill="{fill}" stroke="none"/>'
    inner = (
        lid
        + f'<path d="M {cx - 14} {cy + 2} Q {cx} {cy + 8} {cx + 14} {cy + 2}" stroke="#222" stroke-width="3" fill="none" stroke-linecap="round"/>'
    )
    _drawn.write_text(path, _eye_svg(inner, gid=f"eye_{side}_closed"), encoding="utf-8")
    return path


def _synthesize_sclera(path: Path, *, side: str) -> Path:
    cx, cy = EYE_CENTRE
    inner = f'<ellipse cx="{cx}" cy="{cy}" rx="{EYE_RX}" ry="{EYE_RY}" fill="#ffffff" stroke="none"/>'
    _drawn.write_text(path, _eye_svg(inner, gid=f"sclera_{side}"), encoding="utf-8")
    return path


def _synthesize_pupil(path: Path, *, side: str) -> Path:
    cx, cy = EYE_CENTRE
    inner = f'<circle cx="{cx}" cy="{cy}" r="{PUPIL_R}" fill="{PUPIL_COLOUR}"/>'
    _drawn.write_text(path, _eye_svg(inner, gid=f"pupil_{side}"), encoding="utf-8")
    return path


def _skin_fill_of(head_svg: Path) -> str | None:
    """The first solid fill of the head art's first circle/ellipse — the face's
    skin tone on every rig this factory synthesizes; ``None`` if none is found.
    """
    if not head_svg.is_file():
        return None
    m = re.search(
        r"<(?:circle|ellipse)[^>]*fill=\"(#[0-9a-fA-F]{6})\"",
        head_svg.read_text(encoding="utf-8"),
    )
    return m.group(1) if m else None


def gaze_travel_for(
    rx: float = EYE_RX, ry: float = EYE_RY, pupil_r: float = PUPIL_R
) -> dict[str, float]:
    """The pupil's travel per axis, in view-box units: the sclera's clearance
    minus the pupil's radius — the semi-axes of the inner ellipse the gaze
    axes' unit circle maps onto. The compiler clamps the summed gaze to 0.95
    of that circle (`GAZE_ELLIPSE_MARGIN`), which is what keeps the pupil disc
    inside the white at every angle without a runtime mask.

    >>> gaze_travel_for()
    {'x': 9.0, 'y': 5.0}
    """
    return {"x": float(rx - pupil_r), "y": float(ry - pupil_r)}


def _is_factory_eye(path: Path, *, side: str, state: str) -> bool:
    """Whether an eye part is this factory's own drawing (its group id and the
    64x32 canvas) — the only art `add_gaze` may overwrite."""
    if not path.is_file():
        return True  # nothing to lose
    svg = path.read_text(encoding="utf-8")
    w, h = EYE_CANVAS
    return f'id="eye_{side}_{state}"' in svg and f'viewBox="0 0 {w} {h}"' in svg


@_records_what_it_drew
def add_gaze(
    char_dir: str | Path, *, skin: str | None = None, overwrite_eyes: bool = False
) -> Path:
    """Give a character the eye stack (an#99): three sibling slots per eye under
    the head — ``<side>_sclera`` (white fill) below ``<side>_pupil`` below
    ``<side>_eye`` (the existing slot, now the lid, drawn above the pupil) —
    with synthesized parts, an outline-only open eye, a FILLED closed lid, the
    ``gaze_travel`` clamp, and draw orders that put the lid over the pupil.
    Idempotent: a rig that already has the stack is rewritten to the same
    state. Returns the descriptor path.

    The open and closed eye parts are REWRITTEN (outline-only, filled lid), so
    on a rig whose eyes are not this factory's drawings — a promoted hand rig —
    it refuses unless ``overwrite_eyes=True``: the stack's geometry is the
    synthesized eye's, and an illustrator's eyes would be silently replaced
    (an#99 review). Such a rig wants its own outline-only open eye, filled
    lid, sclera and pupil parts drawn to its own geometry.

    This is the **expand** step for a pre-Wave-6 descriptor: no migration
    inserts pupil slots, because their art would be absent and absent art is
    fatal under `strict_assets` — every existing character would stop
    rendering on the bench.
    """
    from an.characters.schema import CharacterDescriptor, FACE_OFFSETS, Attachment, Slot
    from an.ir.migrate import migrate

    char_dir = Path(char_dir)
    desc_path = char_dir / "character.json"
    raw = json.loads(desc_path.read_text(encoding="utf-8"))
    desc = CharacterDescriptor.model_validate(migrate(raw, kind="CharacterDescriptor"))
    if not desc.face_overlay:
        raise ValueError(
            f"{desc.name!r} has its face baked into the head art (face_overlay: false): "
            "the rig builder draws no overlay eye, so an eye stack would never show. "
            "`an character promote` a hand-drawn rig with overlay face parts first."
        )
    parts = char_dir / "parts"
    # Every refusal BEFORE the first write, so a rig that errors is untouched.
    skin_ = desc.skins.get("default")
    if skin_ is None:
        raise ValueError(f"{desc.name!r} has no default skin to add the eye stack to")
    by_name = {s.name: s for s in desc.slots}
    for eye_slot in ("left_eye", "right_eye"):
        if eye_slot not in by_name:
            raise ValueError(
                f"{desc.name!r} has no {eye_slot!r} slot; the eye stack sits under it"
            )
    foreign = [
        f"eye_{side}_{state}.svg"
        for side in ("l", "r")
        for state in ("open", "closed")
        if not _is_factory_eye(
            parts / f"eye_{side}_{state}.svg", side=side, state=state
        )
    ]
    if foreign and not overwrite_eyes:
        raise ValueError(
            f"{desc.name!r}'s eye art is not this factory's ({', '.join(foreign)}): the eye "
            "stack would replace a hand-drawn eye with the synthesized outline and lid. "
            "Draw the rig's own outline-only open eye, filled closed lid, sclera and pupil "
            "parts to its geometry, or pass overwrite_eyes=True (`--overwrite-eyes`) to "
            "accept the synthesized eyes."
        )
    if skin is None:
        # The lid's fill is the HEAD's skin — read off the head art, never
        # re-derived from a seed the descriptor may not carry (an#99 review:
        # a rig built with `--seed` ≠ name got a lid of another tone).
        skin = (
            _skin_fill_of(parts / "head.svg")
            or _palette_for_seed(
                str(
                    desc.metadata.get("seed")
                    or desc.metadata.get("dicebear_seed")
                    or desc.name
                )
            )[0]
        )
    for side in ("l", "r"):
        _synthesize_sclera(parts / f"sclera_{side}.svg", side=side)
        _synthesize_pupil(parts / f"pupil_{side}.svg", side=side)
        _synthesize_eye_open(
            parts / f"eye_{side}_open.svg", side=side, outline_only=True
        )
        _synthesize_eye_closed(parts / f"eye_{side}_closed.svg", side=side, fill=skin)
    # Same size as the rest of the face on a rig drawn with a head scale.
    head_scale = float(desc.metadata.get("head_scale") or 1.0)
    scale_part_files(
        [
            parts / f"{stem}_{side}.svg"
            for side in ("l", "r")
            for stem in ("sclera", "pupil")
        ]
        + [
            parts / f"eye_{side}_{state}.svg"
            for side in ("l", "r")
            for state in ("open", "closed")
        ],
        head_scale,
    )
    # The colours it just drew, as roles — but ONLY on a rig whose art is
    # already tagged, and the lid only when its colour is the head's TAGGED
    # skin literal. On an untagged rig the lid colour was read off the head
    # art (`_skin_fill_of`), and turning that guess into a role is inferring
    # a role from a pixel: a pack would repaint the lids and not the face,
    # an#99's wrong-tone lid again, with the compiler's warning silenced.
    if desc.colour_roles:
        head_roles = desc.colour_roles.get("parts/head.svg", {})
        lid = _hex_or_none(skin)
        for side in ("l", "r"):
            # Pop before re-adding, so a second run writes the same key order
            # (add_gaze is idempotent, byte for byte).
            for stem in ("eye_{}_open", "eye_{}_closed", "pupil_{}"):
                desc.colour_roles.pop(f"parts/{stem.format(side)}.svg", None)
            if lid is not None and head_roles.get(lid) == "skin":
                desc.colour_roles[f"parts/eye_{side}_closed.svg"] = {lid: "skin"}
            desc.colour_roles[f"parts/pupil_{side}.svg"] = {PUPIL_COLOUR: "pupil"}
    had_stack = "left_pupil" in by_name or "right_pupil" in by_name
    for side, eye_slot in (("l", "left_eye"), ("r", "right_eye")):
        eye = by_name[eye_slot]
        x, y = FACE_OFFSETS.get(eye_slot, (0.0, 0.0))
        existing = skin_.slots.get(eye_slot, {})
        template = existing.get("open") or next(iter(existing.values()), None)
        if template is not None:
            x, y = template.x, template.y
        base = eye.draw_order - 1 if had_stack else eye.draw_order
        for kind, order in (("sclera", base - 1), ("pupil", base)):
            slot_name = f"{eye_slot.split('_')[0]}_{kind}"
            stem = f"{kind}_{side}"
            if slot_name not in by_name:
                desc.slots.append(
                    Slot(
                        name=slot_name, bone=eye.bone, draw_order=order, attachment=stem
                    )
                )
                by_name[slot_name] = desc.slots[-1]
            else:
                by_name[slot_name].draw_order = order
            skin_.slots[slot_name] = {
                stem: Attachment(path=f"parts/{stem}.svg", anchor=(0.5, 0.5), x=x, y=y)
            }
        # The lid draws above the pupil: bump it once (idempotent on a rig that
        # already has the stack). On the default rig the lid then TIES the
        # mouth's order and the tie-break is by name, which puts `left_eye`
        # under the mouth and `right_eye` over it — harmless, they never
        # overlap, but do not read the numbers as a strict stack.
        eye.draw_order = base + 1
    desc.gaze_travel = {
        axis: round(v * head_scale, 3) for axis, v in gaze_travel_for().items()
    }
    desc.metadata["gaze_stack"] = "an#99"
    desc_path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")
    return stamp_factory_parts(
        char_dir,
        {
            f"parts/{stem.format(side)}.svg"
            for side in ("l", "r")
            for stem in ("eye_{}_open", "eye_{}_closed", "sclera_{}", "pupil_{}")
        },
    )


def _hex_or_none(colour: str | None) -> str | None:
    """``colour`` normalised, or ``None`` when it is not a hex literal (a named
    SVG colour is a valid fill but cannot be a role key)."""
    try:
        return normalise_hex(colour) if colour else None
    except ValueError:
        return None


def _palette_for_seed(seed: str) -> tuple[str, str, str]:
    """Return ``(skin, clothing, hair)`` deterministic from ``seed``.

    Picks from a small, hand-tuned set so two characters from different
    seeds tend to look distinct.
    """
    palettes = (
        ("#f4c89a", "#3a6ea5", "#3b2a1a"),
        ("#d8a47f", "#a83249", "#1a1a1a"),
        ("#fbe1c1", "#2e7d4f", "#a8743f"),
        ("#e8c39e", "#d97706", "#5e3a1f"),
        ("#f1c9a5", "#7a8fb5", "#3a2a20"),
    )
    idx = _stable_hash(seed) % len(palettes)
    return palettes[idx]


#: Everything XML allows before the root element: prolog, doctype, comments,
#: processing instructions, whitespace.
_SVG_PREAMBLE = re.compile(r"(?:\s|<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^>]*>)*", re.S)
#: The root's start tag, with `>` allowed inside quoted attribute values.
_SVG_OPEN_TAG = re.compile(r"""<svg\b(?:[^>"']|"[^"]*"|'[^']*')*>""")
_SIZE_ATTR = re.compile(r"""\s(width|height)\s*=\s*("[^"]*"|'[^']*')""")


def _sized_to_height(svg: str, height: float) -> str:
    """``svg`` with its root ``width``/``height`` set so it rasterises ``height``
    tall at its own aspect ratio. Only the root tag's attributes change.

    The aspect is the viewBox's — what the browser draws — and the declared
    size is used only when there is no viewBox (a ``%`` size then has no
    meaning and is refused by :func:`raster_size`).

    >>> _sized_to_height('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40"/>', 100)
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 40" width="200" height="100"/>'
    >>> _sized_to_height('<?xml version="1.0"?><!-- <svg> --><svg xmlns="http://www.w3.org/2000/svg" '
    ...                  'viewBox="0 0 10 10" width="100%" data-t="a>b"/>', 5)
    '<?xml version="1.0"?><!-- <svg> --><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" data-t="a>b" width="5" height="5"/>'
    """
    root = ET.fromstring(svg.encode("utf-8"))
    view_box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(view_box) == 4:
        w, h = float(view_box[2]), float(view_box[3])
    else:
        w, h = raster_size(svg)
    width = round(height * w / h, 3)
    at = _SVG_PREAMBLE.match(svg).end()
    match = _SVG_OPEN_TAG.match(svg, at)
    if match is None:
        raise ValueError("the avatar SVG's root element is not <svg>")
    tag = _SIZE_ATTR.sub("", match.group(0))
    if len(view_box) != 4:  # keep the drawing's own units when resized
        tag = tag.replace("<svg", f'<svg viewBox="0 0 {w:g} {h:g}"', 1)
    closer = "/>" if tag.endswith("/>") else ">"
    tag = (
        f'{tag[: -len(closer)].rstrip()} width="{width:g}" height="{height:g}"{closer}'
    )
    return svg[: match.start()] + tag + svg[match.end() :]


def _write_head_part(
    path: Path, avatar_svg: str, *, height: float = REFERENCE_HEAD_HEIGHT
) -> Path:
    """Write the avatar SVG as the head part, sized to the rig's head.

    The compiler draws a part at its own raster size, in view_box units, so
    that size IS the head's size on screen. Written verbatim, the fallback's
    80×80 canvas drew a head a quarter of the size the default face layout
    (:data:`~an.characters.schema.FACE_OFFSETS`) is drawn for, and a DiceBear
    762×762 one nearly three times it (an#168). Only the root's
    ``width``/``height`` change; the drawing and its viewBox are untouched.
    """
    _drawn.write_text(
        path, _head_part_text(avatar_svg, height=height), encoding="utf-8"
    )
    return path


def _head_part_text(avatar_svg: str, *, height: float = REFERENCE_HEAD_HEIGHT) -> str:
    """What :func:`_write_head_part` writes: the avatar sized to ``height``."""
    avatar_svg = _sized_to_height(avatar_svg, height)
    if not avatar_svg.lstrip().startswith("<?xml"):
        avatar_svg = '<?xml version="1.0" encoding="UTF-8"?>\n' + avatar_svg.lstrip()
    return avatar_svg


def _write_torso_part(
    path: Path,
    *,
    clothing: str,
    accent: str,
    body: BodyBuild = BUILDS[DFLT_BUILD],
    sash: str | None = None,
) -> dict[str, str]:
    """The torso SVG: a rounded rect with a slight collar accent, inset 20 in
    its ``body.torso_size`` canvas. ``sash`` draws a diagonal band across it in
    that colour. Returns the part's colour roles."""
    w, h = body.torso_size
    r = body.torso_radius
    hb = h - 20 - body.torso_inset_bottom
    rect = f'x="20" y="20" width="{w - 40:g}" height="{hb:g}" rx="{r:g}" ry="{r:g}"'
    collar = (
        f'<path d="M {w / 2 - 32:g} 20 Q {w / 2:g} 60 {w / 2 + 32:g} 20" stroke="{accent}" '
        f'stroke-width="6" fill="none"/>'
    )
    roles = {clothing: "clothing", accent: "hair"}
    if sash is None:
        inner = (
            f'<rect {rect} fill="{clothing}" stroke="#222" stroke-width="6"/>' + collar
        )
    else:
        # Fill, then the band clipped to the body, then the outline on top, so
        # the band never covers the ink.
        band = 0.16 * min(w, hb)
        inner = (
            f'<clipPath id="torso_body"><rect {rect}/></clipPath>'
            f'<rect {rect} fill="{clothing}"/>'
            f'<path d="M 20 {20 + 0.12 * hb:g} L {w - 20:g} {20 + 0.88 * hb:g}" '
            f'stroke="{sash}" stroke-width="{band:g}" fill="none" '
            'clip-path="url(#torso_body)"/>'
            + collar
            + f'<rect {rect} fill="none" stroke="#222" stroke-width="6"/>'
        )
        roles[sash] = "accessory"
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}">'
        f'<g id="torso">{inner}</g></svg>'
    )
    _drawn.write_text(path, svg, encoding="utf-8")
    return roles


def _write_arm_part(
    path: Path,
    *,
    side: str,
    color: str,
    hand: str = DFLT_HAND_COLOUR,
    body: BodyBuild = BUILDS[DFLT_BUILD],
) -> dict[str, str]:
    """A 64-wide arm SVG, ``body.arm_length`` long, hand at the bottom.
    Returns the part's colour roles."""
    L, aw, hr, sw = body.arm_length, body.arm_width, body.hand_radius, body.limb_stroke
    cy = L - 4 - hr
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 64 {L:g}" width="64" height="{L:g}">'
        f'<g id="arm_{side}">'
        f'<rect x="{(64 - aw) / 2:g}" y="0" width="{aw:g}" height="{cy - 16:g}" '
        f'rx="{aw / 2:g}" ry="{aw / 2:g}" '
        f'fill="{color}" stroke="#222" stroke-width="{sw:g}"/>'
        f'<circle cx="32" cy="{cy:g}" r="{hr:g}" fill="{hand}" stroke="#222" '
        f'stroke-width="{sw:g}"/>'
        "</g></svg>"
    )
    _drawn.write_text(path, svg, encoding="utf-8")
    return {color: "clothing", hand: "skin"}


def _write_leg_part(
    path: Path, *, side: str, color: str, body: BodyBuild = BUILDS[DFLT_BUILD]
) -> dict[str, str]:
    """An 80-wide leg SVG with a shoe at the bottom, hip to ground long.

    Its height is the build's ``leg_length`` — the rig's
    :data:`~an.characters.schema.LEG_LENGTH` by default — so a leg hung from the
    hip bone puts the shoe on the ground (an#168). Returns its colour roles.
    """
    h, lw = body.leg_length, body.leg_width
    srx, sry = body.shoe_size
    cy = h - 6 - sry
    rx = min(6, lw / 2)
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 80 {h:g}" width="80" height="{h:g}">'
        f'<g id="leg_{side}">'
        f'<rect x="{(80 - lw) / 2:g}" y="0" width="{lw:g}" height="{cy - 12:g}" '
        f'rx="{rx:g}" ry="{rx:g}" '
        f'fill="{color}"/>'
        f'<ellipse cx="40" cy="{cy:g}" rx="{srx:g}" ry="{sry:g}" fill="{SHOE_COLOUR}"/>'
        "</g></svg>"
    )
    _drawn.write_text(path, svg, encoding="utf-8")
    return {color: "leg"}


def _synthesize_brow(path: Path, *, side: str, color: str = DFLT_BROW_COLOUR) -> Path:
    """The brow: one stroke (:func:`~an.characters.brows.brow_path_d`), the
    drawing :func:`~an.characters.brows.brow_range` measures."""
    w, h = BROW_CANVAS
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f'<g id="brow_{side}">'
        f'<path d="{brow_path_d(side)}" '
        f'stroke="{color}" stroke-width="{BROW_STROKE:g}" fill="none" stroke-linecap="round"/>'
        "</g></svg>"
    )
    _drawn.write_text(path, svg, encoding="utf-8")
    return path


# -----------------------------------------------------------------------------
# Views: the turnaround (an#197)
# -----------------------------------------------------------------------------

#: How a view's head is drawn, per hat, where it differs from the front
#: (``_HAT_SVG``). Same 80x80 drawing space, same ``{acc}``/``{ink}`` slots. A
#: side view faces the viewer's RIGHT: the cap's peak points that way, and a
#: bicorne worn athwart shows its narrow end.
_HAT_VIEW_SVG: dict[str, dict[str, str]] = {
    "back": {
        # From behind, a cap is its crown: no peak.
        "cap": (
            '<path d="M 12 22 C 12 3 68 3 68 22 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
            '<circle cx="40" cy="4.5" r="2" fill="{acc}" stroke="{ink}" stroke-width="1"/>'
        ),
    },
    "side": {
        "cap": (
            '<path d="M 12 22 C 12 3 68 3 68 22 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
            '<path d="M 56 21 Q 72 16 80 22 Q 70 26 56 24 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
            '<circle cx="40" cy="4.5" r="2" fill="{acc}" stroke="{ink}" stroke-width="1"/>'
        ),
        "bicorne": (
            '<path d="M 22 21 Q 40 -8 58 21 Q 40 14 22 21 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        ),
    },
    "three_quarter": {
        "cap": (
            '<path d="M 12 22 C 12 3 68 3 68 22 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
            '<path d="M 30 22 Q 58 15 76 22 Q 56 27 30 24 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
            '<circle cx="40" cy="4.5" r="2" fill="{acc}" stroke="{ink}" stroke-width="1"/>'
        ),
        "bicorne": (
            '<path d="M 10 21 Q 40 -8 70 21 Q 40 13 10 21 Z" fill="{acc}" stroke="{ink}" stroke-width="1.5"/>'
        ),
    },
}

#: The head (skin) and hair of each non-front view, in the offline head's 80x80
#: drawing — the SAME canvas as the front, so a turn swaps texture only and
#: emits no per-key geometry (an#87; a key on another canvas would carry its
#: own box since an#211, but one canvas keeps the document unchanged). ``{skin}``/``{hair}``/``{ink}``.
#: The ear is outlined in ink: skin on skin would not show. Each view is
#: ``(under, crown hair, over)`` — the crown hair is what a ``bald`` head drops,
#: and a hair style's volume goes before ``under``, a fall after the crown hair.
_VIEW_HEAD_PARTS: dict[str, tuple[str, str, str]] = {
    # From behind: the hair covers the head down to the nape; the ears show.
    "back": (
        '<ellipse cx="12.5" cy="46" rx="3.5" ry="6" fill="{skin}" stroke="{ink}" stroke-width="1"/>'
        '<ellipse cx="67.5" cy="46" rx="3.5" ry="6" fill="{skin}" stroke="{ink}" stroke-width="1"/>'
        '<circle cx="40" cy="44" r="28" fill="{skin}"/>',
        '<path d="M 12 42 Q 12 14 40 14 Q 68 14 68 42 Q 68 58 58 64 Q 40 60 22 64 Q 12 58 12 42 Z" fill="{hair}"/>',
        "",
    ),
    # A profile facing right: the nose past the edge, the ear mid-head, the
    # hair over the crown and down the back of the skull.
    "side": (
        '<circle cx="40" cy="44" r="28" fill="{skin}"/>'
        '<path d="M 66 38 Q 75 44 66.5 49 Z" fill="{skin}"/>',
        '<path d="M 13 50 Q 9 18 40 15 Q 62 14 68 34 L 58 25 Q 46 21 38 27 Q 31 36 32 52 Q 22 60 13 50 Z" fill="{hair}"/>',
        '<ellipse cx="36" cy="47" rx="4" ry="6" fill="{skin}" stroke="{ink}" stroke-width="1"/>',
    ),
    # Turned partway right: the part of the hair and one ear swing left.
    "three_quarter": (
        '<ellipse cx="13" cy="46" rx="3.5" ry="6" fill="{skin}" stroke="{ink}" stroke-width="1"/>'
        '<circle cx="40" cy="44" r="28" fill="{skin}"/>',
        '<path d="M 12 40 Q 22 6 56 16 Q 66 22 68 34 L 58 24 L 42 17 L 24 26 Q 16 32 15 44 Z" fill="{hair}"/>',
        "",
    ),
}


def _view_head_svg(
    view: str,
    *,
    skin: str,
    hair: str,
    hat: str,
    accessory: str,
    hat_seat: str | None = None,
    hair_style: str = DFLT_HAIR_STYLE,
    hair_length: str = DFLT_HAIR_LENGTH,
) -> str:
    """The offline head of ``view`` (not ``front``, which is
    :func:`_fallback_face_svg`), with its hat seen from that side, worn at
    ``hat_seat``, and the hair's style and length seen from that side."""
    hat_svg = _hat_fragment(hat, view, accessory=accessory, seat=hat_seat)
    # The ear's outline is the drawing's ink — unless the skin or hair IS that
    # literal, when a pack recolouring the role would repaint the outline too.
    ink = distinct_literal(OUTLINE_COLOUR, {skin, hair})
    under, crown, over = (
        part.format(skin=skin, hair=hair, ink=ink) for part in _VIEW_HEAD_PARTS[view]
    )
    behind, fall = _hair_layers(
        view, hair=hair, hair_style=hair_style, hair_length=hair_length
    )
    if hair_style == "bald":
        crown = ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80">'
        f"{behind}{under}{crown}{fall}{over}{hat_svg}</svg>"
    )


#: How much of the front body's width each view's torso keeps, and where its
#: collar sits (a fraction of the half-width, toward the facing side).
_VIEW_TORSO_WIDTH: dict[str, float] = {"back": 1.0, "three_quarter": 0.85, "side": 0.62}
_VIEW_COLLAR_SHIFT: dict[str, float] = {"three_quarter": 0.35, "side": 0.55}


def _write_view_torso_part(
    path: Path,
    *,
    view: str,
    clothing: str,
    accent: str,
    body: BodyBuild,
    sash: str | None = None,
) -> dict[str, str]:
    """The torso of ``view`` on the front torso's canvas (the swap is fitted
    into the front's box): narrower as it turns, the collar swinging toward the
    facing side, a plain neckline from behind. Returns the part's colour roles.
    """
    w, h = body.torso_size
    hb = h - 20 - body.torso_inset_bottom
    bw = (w - 40) * _VIEW_TORSO_WIDTH[view]
    x0 = (w - bw) / 2
    r = min(body.torso_radius, bw / 2)
    rect = f'x="{x0:g}" y="20" width="{bw:g}" height="{hb:g}" rx="{r:g}" ry="{r:g}"'
    if view == "back":
        # The neckline from behind: a shallow band, no V.
        collar = (
            f'<path d="M {w / 2 - 28:g} 22 Q {w / 2:g} 30 {w / 2 + 28:g} 22" '
            f'stroke="{accent}" stroke-width="6" fill="none"/>'
        )
    else:
        cx = w / 2 + _VIEW_COLLAR_SHIFT[view] * bw / 2
        half = 32 * _VIEW_TORSO_WIDTH[view] / 2
        collar = (
            f'<path d="M {cx - half:g} 20 Q {cx:g} 50 {cx + half:g} 20" '
            f'stroke="{accent}" stroke-width="6" fill="none"/>'
        )
    roles = {clothing: "clothing", accent: "hair"}
    ink = f'<rect {rect} fill="none" stroke="{OUTLINE_COLOUR}" stroke-width="6"/>'
    if sash is None:
        inner = f'<rect {rect} fill="{clothing}"/>' + collar + ink
    else:
        band = 0.16 * min(w - 40, hb)
        # From behind the band runs the other diagonal.
        y_a, y_b = (0.88, 0.12) if view == "back" else (0.12, 0.88)
        inner = (
            f'<clipPath id="torso_body"><rect {rect}/></clipPath>'
            f'<rect {rect} fill="{clothing}"/>'
            f'<path d="M {x0:g} {20 + y_a * hb:g} L {x0 + bw:g} {20 + y_b * hb:g}" '
            f'stroke="{sash}" stroke-width="{band:g}" fill="none" '
            'clip-path="url(#torso_body)"/>' + collar + ink
        )
        roles[sash] = "accessory"
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="{SVG_NS}" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}">'
        f'<g id="torso_{view}">{inner}</g></svg>'
    )
    _drawn.write_text(path, svg, encoding="utf-8")
    return roles


#: The face slots of the default rig with the eye stack (an#99).
FACE_SLOTS: tuple[str, ...] = (
    "left_eye",
    "right_eye",
    "left_sclera",
    "right_sclera",
    "left_pupil",
    "right_pupil",
    "mouth",
    "left_brow",
    "right_brow",
)
#: The side of the face that turns AWAY in a view facing right: the viewer's
#: left eye, and everything stacked with it.
_FAR_FACE_SLOTS: tuple[str, ...] = (
    "left_eye",
    "left_sclera",
    "left_pupil",
    "left_brow",
)
_NEAR_FACE_SLOTS: tuple[str, ...] = (
    "right_eye",
    "right_sclera",
    "right_pupil",
    "right_brow",
)

#: Profile (facing right): how far the near eye, its stack and brow slide toward
#: the face's edge, and the mouth with them (view_box units at head_scale 1);
#: the mouth is narrowed, seen edge-on.
SIDE_EYE_SHIFT: float = 14.0
SIDE_MOUTH_SHIFT: float = 56.0
SIDE_MOUTH_SQUASH: float = 0.6
#: Profile legs (facing right): both hang from under the body, the near leg
#: (``leg_r``, drawn over the far one) a little forward and the far leg a
#: little back, overlapping at the hip — each hip sits ``SIDE_LEG_OFFSET`` leg
#: widths off the centre line — and splayed so the FEET part: the shoe centres
#: land ``SIDE_FOOT_SPREAD`` leg widths apart, on every build (a stubby leg
#: splays more). Both legs show, even as one silhouette, and a walk in profile
#: has two legs to alternate (an#203). A stick leg is thinner than its shoe,
#: so leg widths alone would leave the two shoes on top of each other — a
#: one-legged stand; the shoes part by at least ``SIDE_FOOT_MIN_SHOES`` shoe
#: lengths (a floor every other build already clears, so they are unchanged).
SIDE_LEG_OFFSET: float = 0.25
SIDE_FOOT_SPREAD: float = 1.8
SIDE_FOOT_MIN_SHOES: float = 2.0
#: Three-quarter (facing right): the whole face slides toward the facing side,
#: the far eye narrows, the far arm tucks in toward the body and the legs in.
THREE_QUARTER_FACE_SHIFT: float = 20.0
THREE_QUARTER_MOUTH_SHIFT: float = 24.0
THREE_QUARTER_FAR_SQUASH: float = 0.85
THREE_QUARTER_ARM_TUCK: float = 0.3
THREE_QUARTER_LEG_TUCK: float = 0.25


def _profile_legs(body: BodyBuild) -> tuple["SlotPose", "SlotPose"]:
    """The far (``leg_l``) and near (``leg_r``) leg of a right-facing profile:
    hips :data:`SIDE_LEG_OFFSET` leg widths either side of the centre line, and
    each leg turned about its hip so the feet are :data:`SIDE_FOOT_SPREAD` leg
    widths apart (and at least :data:`SIDE_FOOT_MIN_SHOES` shoe lengths). The near leg reaches FORWARD (toward +x): a PixiJS rotation
    is clockwise, which swings a hanging foot toward -x, so its angle is
    negative.

    >>> far, near = _profile_legs(BUILDS["regular"])
    >>> far.x + near.x, far.rotation == -near.rotation > 0
    (0.0, True)
    """
    from an.characters.schema import SlotPose

    hip = SIDE_LEG_OFFSET * body.leg_width
    spread = max(
        SIDE_FOOT_SPREAD * body.leg_width, SIDE_FOOT_MIN_SHOES * body.shoe_size[0]
    )
    reach = (spread / 2 - hip) / body.leg_length
    angle = math.asin(max(-1.0, min(1.0, reach)))
    far = SlotPose(x=body.hip_x - hip, rotation=angle)
    near = SlotPose(x=-body.hip_x + hip, rotation=-angle)
    return far, near


def view_poses(
    body: BodyBuild = BUILDS[DFLT_BUILD],
    *,
    head_scale: float = 1.0,
    slots: tuple[str, ...] | None = None,
) -> dict[str, dict[str, "SlotPose"]]:
    """``{view: {slot: SlotPose}}`` for the factory's rig built as ``body`` — what
    a view does besides swapping art: the back hides the face, the side hides
    the far eye and arm and slides the near eye and mouth to the profile edge.

    Face offsets scale with ``head_scale`` (the face was drawn at it), limb
    offsets come from the build's own joints. ``slots`` limits the poses to the
    slots a rig has (a rig without the eye stack has no pupils to pose).

    >>> poses = view_poses()
    >>> sorted(poses)
    ['back', 'front', 'side', 'three_quarter']
    >>> poses["front"], poses["back"]["mouth"].alpha, poses["side"]["arm_r"].x
    ({}, 0.0, -90.0)
    """
    from an.characters.schema import SlotPose

    sx, _ = body.shoulder
    s = head_scale
    side: dict[str, SlotPose] = {n: SlotPose(alpha=0.0) for n in _FAR_FACE_SLOTS}
    side.update({n: SlotPose(x=SIDE_EYE_SHIFT * s) for n in _NEAR_FACE_SLOTS})
    side["mouth"] = SlotPose(x=SIDE_MOUTH_SHIFT * s, scale_x=SIDE_MOUTH_SQUASH)
    side["arm_l"] = SlotPose(alpha=0.0)
    side["arm_r"] = SlotPose(x=-sx)
    side["leg_l"], side["leg_r"] = _profile_legs(body)
    shift = THREE_QUARTER_FACE_SHIFT * s
    tq: dict[str, SlotPose] = {
        n: SlotPose(x=shift, scale_x=THREE_QUARTER_FAR_SQUASH) for n in _FAR_FACE_SLOTS
    }
    tq.update({n: SlotPose(x=shift) for n in _NEAR_FACE_SLOTS})
    tq["mouth"] = SlotPose(x=THREE_QUARTER_MOUTH_SHIFT * s)
    tq["arm_l"] = SlotPose(x=THREE_QUARTER_ARM_TUCK * sx)
    tq["leg_l"] = SlotPose(x=THREE_QUARTER_LEG_TUCK * body.hip_x)
    tq["leg_r"] = SlotPose(x=-THREE_QUARTER_LEG_TUCK * body.hip_x)
    poses = {
        "front": {},
        "three_quarter": tq,
        "side": side,
        "back": {n: SlotPose(alpha=0.0) for n in FACE_SLOTS},
    }
    if slots is not None:
        poses = {
            v: {n: p for n, p in m.items() if n in slots} for v, m in poses.items()
        }
    return poses


@_records_what_it_drew
def add_views(char_dir: str | Path) -> Path:
    """Give a factory character its turnaround (an#197): ``back``, ``side`` and
    ``three_quarter`` head and torso art beside the front, a ``view`` swap set
    projected onto those two slots, and a pose per view (``swap_poses``) — so
    ``{kind: set, target: <entity>, property: view, value: side}`` or
    :func:`an.motion.turn` turns the whole character. Idempotent. Returns the
    descriptor path.

    The views are REDRAWN from the recorded knobs (seed, palette, build, hat,
    hair style and length, sash, head scale), so it refuses a rig whose head is not this factory's
    drawing for them — a DiceBear head (its face is baked, and there is no
    back of it to draw), a promoted hand rig, or an edited head: its views are
    an illustrator's to draw, declared the same way (a ``view`` set whose keys
    name attachments on the head and torso slots, and ``swap_poses``).

    Every colour is role-tagged like the front's, so a StylePack recolours the
    views exactly as it recolours the front (an#191). The existing art is not
    touched: a shot that never sets a view renders byte-identically.
    """
    from an.characters.schema import (
        DFLT_VIEW,
        VIEW_CHANNEL,
        VIEWS,
        CharacterDescriptor,
    )
    from an.ir.migrate import migrate

    char_dir = Path(char_dir)
    desc_path = char_dir / "character.json"
    raw = json.loads(desc_path.read_text(encoding="utf-8"))
    desc = CharacterDescriptor.model_validate(migrate(raw, kind="CharacterDescriptor"))
    meta = desc.metadata
    parts = char_dir / "parts"
    if not desc.face_overlay or meta.get("art_provenance") != "fallback_geometric":
        raise ValueError(
            f"{desc.name!r} is not a character this factory drew offline (its head "
            f"is {meta.get('art_provenance') or 'not recorded'}): its back and "
            "profile cannot be synthesized. Draw them and declare a `view` set "
            "and `swap_poses` (see `an character contract`), or make the "
            "character with `an character new --offline`."
        )
    hat = str(meta.get("hat") or DFLT_HAT)
    hair_style = str(meta.get("hair_style") or DFLT_HAIR_STYLE)
    hair_length = str(meta.get("hair_length") or DFLT_HAIR_LENGTH)
    _check_hair(hair_style, hair_length)
    body = _check_build(str(meta.get("build") or DFLT_BUILD))
    head_scale = float(meta.get("head_scale") or 1.0)
    height = REFERENCE_HEAD_HEIGHT * head_scale
    head_path = parts / "head.svg"
    head_text = head_path.read_text(encoding="utf-8") if head_path.is_file() else None
    # The hat as this factory wears it now, else where it was drawn before
    # hats were seated above the brows (an#252): a character made then keeps
    # its hat where its front has it, in every view.
    looks = None
    # The seat recorded when the character was made; a character made before
    # seats were recorded (an#252) is tried at the current seat and unseated.
    recorded = meta.get("hat_seat")
    seats = (recorded,) if recorded else (_hat_seat(hat, head_scale).transform, None)
    for hat_seat in dict.fromkeys(seats):
        candidate = _resolve_looks(
            str(meta.get("seed") or desc.name),
            _check_palette(meta.get("palette")),
            hat=hat,
            hat_seat=hat_seat,
            hair_style=hair_style,
            hair_length=hair_length,
        )
        if head_text == _head_part_text(candidate.head_svg, height=height):
            looks = candidate
            break
    if looks is None:
        raise ValueError(
            f"{desc.name!r}'s head art is not the factory's drawing for its recorded "
            "seed and knobs (edited by hand?), so views drawn from them would not "
            "match it. Draw the views to the edited head and declare them instead."
        )
    skin_ = desc.skins.get("default")
    if skin_ is None or not {"head", "torso"} <= set(skin_.slots):
        raise ValueError(f"{desc.name!r} has no default skin with a head and a torso")
    head_skin, head_hair = (
        next(lit for lit, r in looks.head_roles.items() if r == role)
        for role in ("skin", "hair")
    )
    head_acc = next(
        (lit for lit, r in looks.head_roles.items() if r == "accessory"),
        _ACCESSORY_TONES[0],
    )
    sash = looks.accessory if meta.get("sash") else None
    roles: dict[str, dict[str, str]] = {}
    for view in VIEWS:
        if view == DFLT_VIEW:
            continue
        head_rel = f"parts/head_{view}.svg"
        _drawn.write_text(
            char_dir / head_rel,
            _head_part_text(
                _view_head_svg(
                    view,
                    skin=head_skin,
                    hair=head_hair,
                    hat=hat,
                    accessory=head_acc,
                    hat_seat=hat_seat,
                    hair_style=hair_style,
                    hair_length=hair_length,
                ),
                height=height,
            ),
            encoding="utf-8",
        )
        roles[head_rel] = dict(looks.head_roles)
        torso_rel = f"parts/torso_{view}.svg"
        roles[torso_rel] = _write_view_torso_part(
            char_dir / torso_rel,
            view=view,
            clothing=looks.clothing,
            accent=looks.accent,
            body=body,
            sash=sash,
        )
    by_slot = {s.name: s for s in desc.slots}
    for slot_name in ("head", "torso"):
        attachments = skin_.slots[slot_name]
        default_name = by_slot[slot_name].attachment if slot_name in by_slot else None
        template = attachments.get(default_name) or next(iter(attachments.values()))
        for view in VIEWS:
            path = (
                template.path if view == DFLT_VIEW else f"parts/{slot_name}_{view}.svg"
            )
            attachments[view] = template.model_copy(update={"path": path})
    desc.asset_sets[VIEW_CHANNEL] = {view: view for view in VIEWS}
    desc.swap_poses[VIEW_CHANNEL] = view_poses(
        body, head_scale=head_scale, slots=tuple(by_slot)
    )
    if desc.colour_roles:  # tagged like the front — never half-tagged
        desc.colour_roles.update(roles)
    meta["views"] = list(VIEWS)
    desc_path.write_text(desc.model_dump_json(indent=2), encoding="utf-8")
    return stamp_factory_parts(
        char_dir,
        {
            f"parts/{slot}_{view}.svg"
            for slot in ("head", "torso")
            for view in VIEWS
            if view != DFLT_VIEW
        },
    )
