"""StylePack: art direction as a document, and the first reader the styles store has had.

The `styles` store was nine lines with no consumer — `rg '\\["styles"\\]'` found
only the mall wiring — while colour lived in three disconnected places: the
compiler's `_CHARACTER_PALETTES`, six literals inside `runtime.js`, and the
character factory, which carried *two disagreeing* palette tables. an#106
retired `AssetRef(kind="style")` because it selected nothing. This is what the
word was reserved for.

**A pack recolours SVG art only where the art says what its colours are.**
The character factory records, per part, which literal it drew as which role
(`CharacterDescriptor.colour_roles`, see :mod:`an.characters.colour_roles`),
and the compiler rewrites exactly those literals into a new, content-addressed
inline texture — palette swapping. Untagged art (hand-drawn, DiceBear) is left
alone and the compiler warns once, naming it: a pack would otherwise have to
infer a role from a pixel, which is what produced an#99's wrong-tone lid. So
the four reasons this module once gave for never touching SVG reduce to one
that still holds — no tags, no recolour. (The texture is inline, so staging and
content addressing are unaffected; the substitution rewrites paint attributes
only, never geometry or ids.)

**A pack must not declare a role it cannot change.** `lip`, `mouth_fill`,
`teeth`, `tongue` and the eye's white are literals inside `runtime.js`; a role
that resolves to nothing is worse than an absent one, and :data:`UNREACHABLE_ROLES`
plus its test is what keeps the list honest.

**No `line.width`.** A first draft carried one, and nothing read it: the
procedural rig's stroke is a `runtime.js` literal and an SVG rig's is inside
its drawing, so the field was written, serialized, and consumed nowhere — the
same shape this module refuses in `UNREACHABLE_ROLES`, and a rule is not a rule
if it exempts the module that states it. It comes back when something reads it.

Colours are **hex strings**, deliberately not DTCG colour objects:
`bench/palette.py` mirrors `runtime.js` verbatim, and a second colour
representation doubles the surface on which the two can silently diverge.

**Surface treatments** (an#163 gap 5) are the pack's second job: an outline, a
paper-gap drop shadow and a glow per drawable entity (:class:`SurfaceTreatment`,
``surface`` with a per-entity ``entity_surfaces`` override), and one static
paper grain over the frame (:class:`Grain`). Every one is a COMPILE-TIME
expansion into ordinary document content — underlay copies of a part's own
visual, a gradient sprite, a seeded noise tile — never a runtime filter, and
never anything random at render time. `an.stage.surface` does the
expanding. The outline and the shadow reach ANY SVG art, role-tagged or not:
they copy a part's texture rather than recolour it. Every width and offset is in
the rig's own pixels, so a treatment scales with the character like paper would.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, register_kind
from an.paint import Gradient

__all__ = [
    "STYLE_SCHEMA_VERSION",
    "STYLE_DOCUMENT_KIND",
    "REACHABLE_ROLES",
    "UNREACHABLE_ROLES",
    "StylePack",
    "resolve_palette",
    "Outline",
    "PaperShadow",
    "Glow",
    "Grain",
    "SurfaceTreatment",
    "surface_for",
]

STYLE_SCHEMA_VERSION = "0.1.0"

STYLE_DOCUMENT_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="StylePack",
        version_field="schema_version",
        current_version=STYLE_SCHEMA_VERSION,
    )
)

#: Roles a pack can actually change, because the COMPILER decides them and
#: stamps them into the document the runtime draws.
#:
#: `skin`, `clothing` and `hair` are `_CHARACTER_PALETTES`' three components;
#: `leg` and `pupil` are the compiler's own literals (`DFLT_LEG_COLOUR`,
#: `DFLT_PUPIL_COLOUR`); `sky` and `ground` are the environment presets';
#: `stroke` is a stroked path's default colour (`an.stage.paths.DFLT_STROKE_COLOUR`,
#: an#161) — the arrowhead is filled in the same colour, so it is not a second
#: role. A path that names its own `color` is art and is left alone.
#: `accessory` (a hat, a sash) exists only in role-tagged SVG art — the
#: factory's `colour_roles` — and reaches the document through the recoloured
#: texture, as do the SVG rig's `skin`, `clothing`, `hair`, `leg` and `pupil`.
#:
#: Every one of these is compiled with a marker colour and asserted to reach
#: the document by `tests/test_styles.py`. `pupil` shipped in this set wired to
#: NOTHING (an#112 review) because the guard checked set membership against the
#: set it was checking — a declared-reachable role that reaches nothing is the
#: same defect as an unreachable one, and it needs the same kind of test.
REACHABLE_ROLES: frozenset[str] = frozenset(
    {"skin", "clothing", "hair", "leg", "pupil", "sky", "ground", "stroke", "accessory"}
)

#: Roles a pack must NOT declare, with what makes each unreachable. These are
#: `runtime.js` literals: `_LIP_COLOR`, `_MOUTH_FILL`, `_TEETH_COLOR`,
#: `_TONGUE_COLOR`, and the eye white's `0xffffff` — none of them read anything
#: from the compiled document, so a pack that named them would be accepted,
#: change nothing, and say nothing. `tests/test_styles.py` reads the literals
#: out of `runtime.js` so this list cannot quietly stop matching it.
UNREACHABLE_ROLES: dict[str, str] = {
    "lip": "cutan's runtime script `_LIP_COLOR`, drawn by makeMouth and never read from the document",
    "mouth_fill": "cutan's runtime script `_MOUTH_FILL`",
    "teeth": "runtime.js `_TEETH_COLOR`",
    "tongue": "runtime.js `_TONGUE_COLOR`",
    "eye_sclera": "runtime.js draws the eye white as a literal 0xffffff in makeEye",
}


# -----------------------------------------------------------------------------
# Surface treatments (an#163 gap 5)
# -----------------------------------------------------------------------------

#: Outline defaults, in RIG pixels (a treatment scales with its character). The
#: colour is a near-black rather than black because that is what the measured
#: styles use (South Park's is `#231316`); on SVG art it is a multiply, see
#: :class:`Outline`.
DFLT_OUTLINE_WIDTH: float = 3.0
DFLT_OUTLINE_COLOUR: str = "#1a1a1a"

#: Paper-gap shadow defaults: down and to the right, like an overhead light a
#: little in front of the table. Rig pixels.
DFLT_SHADOW_DX: float = 4.0
DFLT_SHADOW_DY: float = 4.0
DFLT_SHADOW_COLOUR: str = "#000000"
DFLT_SHADOW_ALPHA: float = 0.35

#: Glow defaults: a warm white halo `radius` rig pixels past the entity's drawn
#: box, `intensity` = the gradient's opacity at its core (it is ADDED to what is
#: behind it, so 1.0 can clip to white).
DFLT_GLOW_COLOUR: str = "#fff4c2"
DFLT_GLOW_RADIUS: float = 60.0
DFLT_GLOW_INTENSITY: float = 0.5

#: Paper grain defaults. `amount` is how far the darkest grain texel multiplies
#: toward black (0.06 = the frame is kept at 94-100 %); `tile` is the noise
#: tile's side in FRAME pixels (the grain lives on the camera-immune overlay).
DFLT_GRAIN_AMOUNT: float = 0.06
DFLT_GRAIN_SEED: int = 0
DFLT_GRAIN_TILE: int = 256

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex_colour(value: str) -> str:
    if not isinstance(value, str) or not _HEX.match(value):
        raise ValueError(f"expected a '#rrggbb' colour, got {value!r}")
    return value


class _Treatment(BaseModel):
    """A precise instruction to draw something, so unknown keys are refused —
    the `Plane` reasoning (an#110): a misspelt `widht` that silently did
    nothing is the failure this package refuses everywhere else."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("color", check_fields=False)
    @classmethod
    def _colour_is_hex(cls, v: str) -> str:
        return _hex_colour(v)


class Outline(_Treatment):
    """A darker, dilated copy drawn behind each part.

    On a procedural part (rect, ellipse) it is the part's own shape grown by
    ``width`` — exact for a rect (rounded corners of radius ``width``, which is
    what dilating by a disk gives) and, for an ellipse, the ellipse with both
    radii grown (exact on the axes and for circles). On an SVG part it is a
    ring of copies of the part's texture offset by ``width`` in
    ``an.stage.surface.OUTLINE_RING`` directions, drawn in ``color``
    as a `tint`: tint MULTIPLIES, so the outline is exactly ``color`` where the
    art is white and darker elsewhere — exact everywhere for black, and within a
    few levels of it for the default near-black.

    ``nested`` extends it to parts nested inside another part (face features
    on the head). Off by default: the pieces of a cut-out are the paper; the
    face is drawn on them. A procedural eye or mouth never gets one (they are
    not copyable shapes); an SVG rig's eyes and mouth do, under ``nested``.

    **Fading a treated part darkens it.** The copies are opaque and drawn
    separately, so at ``alpha`` 0.5 the part shows its outline colour through
    itself rather than the background. A group fade needs the subtree drawn to
    a texture first (a filter), which this package refuses; the compiler warns
    when an ``alpha`` channel reaches a treated part.
    """

    width: float = Field(DFLT_OUTLINE_WIDTH, gt=0)
    color: str = DFLT_OUTLINE_COLOUR
    nested: bool = False


class PaperShadow(_Treatment):
    """The "no-platen" paper-gap shadow: an offset, darkened copy of each part.

    The copy sits in the part's own container, so it follows every tween,
    `play` and swap of the part with no channel of its own. The offset is
    therefore in the PART's frame: a part that rotates takes its shadow round
    with it (a light fixed to the paper, not the room) — invisible at the
    small offsets this is for, and a limit to know for a large one.

    With an outline, the shadow is grown by the outline width so it shows past
    the outline rather than hiding under it: exactly the outlined silhouette on
    a procedural part; on an SVG part one copy scaled about the art's centre, so
    it grows the art's BOX by the width (one copy, because translucent copies
    would compound where they overlap).
    """

    dx: float = DFLT_SHADOW_DX
    dy: float = DFLT_SHADOW_DY
    color: str = DFLT_SHADOW_COLOUR
    alpha: float = Field(DFLT_SHADOW_ALPHA, gt=0, le=1)
    nested: bool = False


class Glow(_Treatment):
    """An additive radial-gradient sprite behind an entity.

    Its box is the entity's drawn box grown by ``radius``, and the gradient is
    an ELLIPSE over that box: it holds ``intensity`` out to the entity's box
    along its shorter axis and fades to nothing at the edge — so on a tall
    entity the halo is fainter at the top and bottom than at the sides.
    Drawn with the engine's native ADD blend (PixiJS 7 does it in the blend
    equation, no filter), as the entity's first child, so it moves with the
    entity and lights the background around it, not the entity itself.
    """

    color: str = DFLT_GLOW_COLOUR
    radius: float = Field(DFLT_GLOW_RADIUS, gt=0)
    intensity: float = Field(DFLT_GLOW_INTENSITY, gt=0, le=1)


class Grain(_Treatment):
    """One static paper-grain texture over the whole frame.

    Seeded noise generated at COMPILE time (``an.stage.surface``),
    tiled on the camera-immune overlay under any text, and MULTIPLIED onto the
    frame — so it only ever darkens, by at most ``amount``. The same seed is the
    same grain on every frame and every machine; nothing is random at render
    time.
    """

    amount: float = Field(DFLT_GRAIN_AMOUNT, gt=0, le=1)
    seed: int = DFLT_GRAIN_SEED
    tile: int = Field(DFLT_GRAIN_TILE, ge=16, le=1024)


class SurfaceTreatment(_Treatment):
    """Which treatments an entity gets. Each is off when absent.

    In ``StylePack.entity_surfaces`` an entry OVERRIDES the pack's ``surface``
    key by key, for the keys it sets: ``{"glow": {...}}`` adds a glow and keeps
    the pack's outline; ``{"outline": false}`` removes the outline. Which keys
    were set survives a dump (only they are serialized), so a pack written with
    ``model_dump()`` and read back means the same thing. ``null`` switches one
    off too, but a dump with ``exclude_none=True`` drops it — and the override
    then silently inherits the pack's treatment — so ``false`` is the spelling
    to store.

    >>> SurfaceTreatment(glow={}).model_dump()
    {'glow': {'color': '#fff4c2', 'radius': 60.0, 'intensity': 0.5}}
    """

    outline: Outline | Literal[False] | None = None
    shadow: PaperShadow | Literal[False] | None = None
    glow: Glow | Literal[False] | None = None

    @model_serializer(mode="wrap")
    def _only_what_was_set(self, handler):
        data = handler(self)
        return {k: v for k, v in data.items() if k in self.model_fields_set}

    def is_empty(self) -> bool:
        return not (self.outline or self.shadow or self.glow)


class StylePack(BaseModel):
    """Art direction for a project. Saved in the `styles` store.

    >>> pack = StylePack(name="noir", roles={"skin": "#d8d8d8", "clothing": "#202028"})
    >>> pack.colour_for("skin")
    '#d8d8d8'
    >>> pack.colour_for("hair") is None
    True

    Per-entity overrides win over roles, which is what makes a pack usable on a
    scene where one character must stay off-palette:

    >>> pack = StylePack(name="noir", roles={"skin": "#d8d8d8"},
    ...                  entities={"maya": {"skin": "#f4c89a"}})
    >>> pack.colour_for("skin", entity="maya"), pack.colour_for("skin", entity="bob")
    ('#f4c89a', '#d8d8d8')

    A role the renderer cannot reach is refused at construction, not ignored:

    >>> StylePack(name="x", roles={"lip": "#800000"})
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: ...
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = STYLE_SCHEMA_VERSION
    kind: Literal["StylePack"] = "StylePack"

    name: str
    #: ``{role: "#rrggbb"}``. Hex strings, not colour objects — see the module
    #: docstring for why a second representation is a liability here.
    roles: dict[str, str] = Field(default_factory=dict)
    #: ``{entity id: {role: "#rrggbb"}}`` — a per-entity override of `roles`.
    entities: dict[str, dict[str, str]] = Field(default_factory=dict)
    source: AssetSource | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    #: Surface treatments for every drawable entity (characters and props);
    #: ``None`` = none. See :class:`SurfaceTreatment` and :func:`surface_for`.
    surface: SurfaceTreatment | None = None
    #: ``{entity id: SurfaceTreatment}`` — per-entity, key-by-key override of
    #: ``surface``.
    entity_surfaces: dict[str, SurfaceTreatment] = Field(default_factory=dict)
    #: One static paper grain over the frame; ``None`` = none.
    grain: Grain | None = None
    #: **Gradient roles** (an#275): ``{role: Gradient}``. A stage plane that
    #: names a ``role`` (``PlaneArt.role``) is drawn with the pack's gradient
    #: for it -- how a style paints every environment's backdrop as backlit
    #: glass or a dusk sky without editing the environments. Role names are the
    #: environments' own, so they are free-form; a role no plane names simply
    #: paints nothing in that scene.
    gradients: dict[str, Gradient] = Field(default_factory=dict)
    #: The style's **policy** (ADR 0002 decision 4, an#348): per aspect, the
    #: methods it prefers, in order (``{"locomotion": ["loco.bounce"]}``: this
    #: show bounces even when its characters have legs). The first that
    #: applies wins; a shot's own ``policy`` comes first, an author's request
    #: before both. ``None`` (the default) leaves every aspect to its chain,
    #: and is not serialized, so a pack without one dumps as before.
    policy: dict[str, Any] | None = None

    @field_validator("policy")
    @classmethod
    def _policy_shape(cls, v: Any) -> Any:
        from an.semantic.entries import check_policy_block

        return check_policy_block(v)

    @model_serializer(mode="wrap")
    def _omit_unset_policy(self, handler):
        data = handler(self)
        if isinstance(data, dict) and self.policy is None:
            data.pop("policy", None)
        return data

    @model_validator(mode="after")
    def _every_role_is_reachable(self) -> "StylePack":
        """Refuse a role the renderer cannot change.

        A role that silently does nothing is worse than an absent one: the
        author sees a field they set, a render that ignores it, and nothing
        anywhere connecting the two. The same rule an#110 applied to
        `repeat`/`TilingSprite` — ship the whole thing or none of it.
        """
        for where, mapping in [("roles", self.roles), *self.entities.items()]:
            for role in mapping:
                if role in UNREACHABLE_ROLES:
                    raise ValueError(
                        f"{where}.{role} is not reachable by a style pack: "
                        f"{UNREACHABLE_ROLES[role]}. Declaring it would change "
                        "nothing and say nothing. Reachable roles are "
                        f"{sorted(REACHABLE_ROLES)}."
                    )
                if role not in REACHABLE_ROLES:
                    raise ValueError(
                        f"{where}.{role} is not a role this renderer knows. "
                        f"Reachable roles are {sorted(REACHABLE_ROLES)}."
                    )
        return self

    @model_validator(mode="after")
    def _no_near_miss_keys(self) -> "StylePack":
        """Refuse an unknown key that is one slip from a real one.

        The pack is ``extra="allow"`` (forward compatibility), which would let
        ``grian: {...}`` or ``entity_surface: {...}`` validate and draw nothing
        — the silent no-op the treatment models refuse with ``extra="forbid"``.
        """
        import difflib

        for key in self.model_extra or {}:
            close = difflib.get_close_matches(
                key, type(self).model_fields, n=1, cutoff=0.8
            )
            if close:
                raise ValueError(
                    f"{key!r} is not a StylePack field; did you mean {close[0]!r}? "
                    "An unknown key is kept but read by nothing."
                )
        return self

    def gradient_for(self, role: str | None) -> Gradient | None:
        """The pack's gradient for ``role``, or ``None`` (the plane keeps its own paint).

        >>> pack = StylePack(name="reiniger", gradients={"glass": {
        ...     "type": "radial", "stops": ["#fff4d6", "#e0a050"]}})
        >>> pack.gradient_for("glass").type, pack.gradient_for("sky"), pack.gradient_for(None)
        ('radial', None, None)
        """
        return None if role is None else self.gradients.get(role)

    def colour_for(self, role: str, *, entity: str | None = None) -> Optional[str]:
        """The colour for ``role``, or ``None`` when the pack does not set it.

        ``None`` rather than a default: the caller holds today's literal, and a
        pack that does not mention a role must leave it exactly as it was —
        which is what keeps a scene with no pack byte-identical.
        """
        if entity is not None:
            override = self.entities.get(entity, {}).get(role)
            if override is not None:
                return override
        return self.roles.get(role)


def resolve_palette(
    pack: "StylePack | None",
    entity: str,
    default: tuple[str, str, str],
) -> tuple[str, str, str]:
    """``(skin, clothing, hair)`` for one entity under ``pack``.

    A **lookup with a default**, not a rewrite: with no pack, or with a pack
    that mentions none of the three, the caller's own literals come back
    unchanged and the compiled document does not move a byte.

    >>> resolve_palette(None, "maya", ("#f4c89a", "#3a6ea5", "#3b2a1a"))
    ('#f4c89a', '#3a6ea5', '#3b2a1a')
    >>> pack = StylePack(name="noir", roles={"clothing": "#202028"})
    >>> resolve_palette(pack, "maya", ("#f4c89a", "#3a6ea5", "#3b2a1a"))
    ('#f4c89a', '#202028', '#3b2a1a')
    """
    if pack is None:
        return default
    skin, clothing, hair = default
    return (
        pack.colour_for("skin", entity=entity) or skin,
        pack.colour_for("clothing", entity=entity) or clothing,
        pack.colour_for("hair", entity=entity) or hair,
    )


def surface_for(pack: "StylePack | None", entity: str) -> SurfaceTreatment | None:
    """The treatments ``entity`` gets under ``pack``, or ``None`` for none.

    ``None`` is the answer for no pack, a pack without treatments, and an
    entity whose override switched everything off — which is what keeps every
    such scene's compiled document byte-identical to before an#163.

    >>> pack = StylePack(name="sp", surface={"outline": {}},
    ...                  entity_surfaces={"sun": {"glow": {}}, "bob": {"outline": False}})
    >>> sorted(surface_for(pack, "sun").model_dump())
    ['glow', 'outline']
    >>> surface_for(pack, "bob") is None
    True
    >>> surface_for(pack, "maya").outline.width
    3.0
    >>> surface_for(None, "maya") is None
    True
    """
    if pack is None:
        return None
    merged: dict[str, Any] = {}
    if pack.surface is not None:
        merged = {k: getattr(pack.surface, k) for k in pack.surface.model_fields_set}
    override = pack.entity_surfaces.get(entity)
    if override is not None:
        merged.update({k: getattr(override, k) for k in override.model_fields_set})
    result = SurfaceTreatment(**{k: v for k, v in merged.items() if v})
    return None if result.is_empty() else result
