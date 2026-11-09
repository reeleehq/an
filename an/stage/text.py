"""Words on screen: title cards, labels, and text you can animate word by word.

Epic #9 Wave 8, first slice; the design question was an#155. A text block is a
**prop** whose document ``kind`` is ``TextDescriptor`` — the shape stroked paths
took (:mod:`an.stage.paths`) — so a scene names it with an ordinary
``AssetRef(kind="prop", ...)``, its ``overrides`` supply the per-shot string,
and nothing in the scene IR changed (no field, no migration).

>>> title = TextDescriptor(name="title", text="Words on screen", layer="overlay")
>>> title.kind, title.unit, title.layer
('TextDescriptor', 'word', 'overlay')

**Typesetting is not done here.** The sibling package ``tituli`` owns it —
shaping, real glyph metrics, wrapping, alignment, the title-safe area — and
emits a ``Layout`` of placed ``Run``s, one per unit. :func:`layout_text` asks it
for that layout and for each run's glyph contours (``tituli.run_outline``), and
the compiler turns each unit into one node whose visual is an SVG sprite
converted at compile time. The runtime never learns what text is, so fonts
never reach the frame path and the determinism perimeter is unchanged.

**Units are addressable, so text animates with ordinary tweens.** A block of
``unit="word"`` builds ``<id>/word_0``, ``<id>/word_1``, …; ``"glyph"`` and
``"line"`` likewise. ``index`` counts DRAWN units in reading order (spaces are
not units). :func:`reveal_units` is a Python-side generator of ordinary actions
for a staggered reveal — a preset, not a new IR node (the general combinator is
:func:`an.ir.compose.stagger`):

>>> from an.ir.compose import flatten
>>> reveal = reveal_units("title", 3, "alpha", to=1.0, from_=0.0, duration=0.3, step=0.1)
>>> [(f.action.target, round(f.start, 3)) for a in reveal for f in flatten(a)
...  if f.action.kind == "tween"]
[('title/word_0', 0.0), ('title/word_1', 0.1), ('title/word_2', 0.2)]

**Two layers.** ``layer="world"`` is in the scene and moves with the camera, like
any prop. ``layer="overlay"`` is drawn in a second top-level container the
camera never touches — a title card stays exactly where it is through a
push-in while an in-world label grows with the scene.

**Fonts fail loudly and never depend on the machine.** ``font=None`` is the
face Pillow embeds (Aileron, CC0 — "No Rights Reserved"), requested through
``tituli.EMBEDDED`` so the installed fonts are never consulted: the same bytes
on every machine with the same Pillow, and no typeface is vendored in this
package. ``font`` otherwise names a font FILE (``.ttf``/``.otf``/``.ttc``),
absolute or relative to the text document's directory in the props store;
a path that is not a file, or a file the typesetter could not use, RAISES
(:class:`TextFontError`). A family NAME is refused on purpose: resolving one
would make the picture depend on what a machine has installed. A character
the face has no glyph for raises too — ``an`` is English-first and refuses
loudly rather than drawing a box. The face's identity (sha256 of its bytes) is
recorded in the compiled document.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from an.base import asset_overrides
from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, migrate, omit_unset, register_kind

__all__ = [
    "TEXT_SCHEMA_VERSION",
    "TEXT_DOCUMENT_KIND",
    "TextDescriptor",
    "Counter",
    "TextFontError",
    "TextLayoutError",
    "TextOutlineWarning",
    "TextHaloWarning",
    "TextUnit",
    "HaloPaint",
    "halo_paint",
    "halo_engine_problem",
    "HALO_FILTER_PRIMITIVES",
    "TextLayout",
    "FontIdentity",
    "resolve_text",
    "font_base_dir",
    "text_entity_problem",
    "RESERVED_TEXT_IDS",
    "layout_text",
    "unit_names",
    "layout_text_set",
    "text_set_keys",
    "TEXT_SET",
    "BLOCK_UNIT",
    "reveal_units",
    "DFLT_TEXT_COLOUR",
    "DFLT_TEXT_SIZE",
]

TEXT_SCHEMA_VERSION = "0.1.0"

#: Its own versioned document kind, registered from the module that owns the
#: schema (the rule `PathDescriptor` and `PropDescriptor` follow).
TEXT_DOCUMENT_KIND: DocumentKind = register_kind(
    DocumentKind(
        name="TextDescriptor",
        version_field="schema_version",
        current_version=TEXT_SCHEMA_VERSION,
    )
)

#: Type size as a FRACTION OF FRAME HEIGHT (tituli's convention): 0.06 is
#: 65 px at 1080p, and the same block reads the same at 720p and at 4K.
DFLT_TEXT_SIZE: float = 0.06

#: Ink when the document names none — a near-black that reads on the default
#: white background.
DFLT_TEXT_COLOUR: str = "#1a1a1a"

#: The outline's ink when a block sets ``stroke_width`` and names no
#: ``stroke_color`` (an#313): the near-black of the default fill.
DFLT_TEXT_STROKE_COLOUR: str = "#1a1a1a"

#: Line height as a multiple of the size.
DFLT_LEADING: float = 1.2
#: The OpenType features a counter block asks for (an#362): tabular figures,
#: so "11" is as wide as "88" and a counting number does not jitter.
COUNTER_FEATURES: tuple[str, ...] = ("tnum",)

#: Font file suffixes a `font` path may carry.
FONT_SUFFIXES: tuple[str, ...] = (".ttf", ".otf", ".ttc")

#: Entity ids a text block may not take: the runtime indexes the scene's
#: container as ``root`` (the camera's target), and the overlay container is
#: named ``overlay``. An overlay block called ``root`` would overwrite the
#: camera's node in the runtime's index and take the push-in with it.
RESERVED_TEXT_IDS: frozenset[str] = frozenset({"root", "overlay"})

#: Line breaks and tabs are normalised before typesetting (a CRLF string pasted
#: into `overrides.text` must not raise "no glyph for '\\r'").
_WHITESPACE_NORMALISATION: tuple[tuple[str, str], ...] = (
    ("\r\n", "\n"),
    ("\r", "\n"),
    ("\t", " "),
)

#: Pixels of clear margin around each unit's texture box, so anti-aliased ink
#: at the box edge is never clipped.
UNIT_BOX_PAD_PX: int = 1

#: An 8-bit channel's maximum: a tituli colour's alpha over this is a fraction.
_ALPHA_MAX: int = 255

#: How far a halo's Gaussian is drawn past its dilation, in standard
#: deviations: the unit's box grows by ``spread + ceil(this x blur)`` so the
#: glow is never clipped. tituli's own reach (``tituli.render._BLUR_REACH``).
HALO_BLUR_REACH: int = 3

#: How far past the ink a halo still visibly covers a NEIGHBOUR's glyphs, in
#: standard deviations past the dilation: at 2 the default halo's glow is down
#: to ~3 % (``gain`` 2 x the Gaussian tail 0.023 x ``opacity`` 0.65). What
#: :class:`TextHaloWarning` measures against.
HALO_COVER_SIGMAS: float = 2.0

#: The SVG filter primitives a halo is drawn with (an#701), in the order the
#: unit's texture chains them: what the shot's engine must afford as
#: ``engine.svg_filter`` keys, or the text is refused at compile.
HALO_FILTER_PRIMITIVES: tuple[str, ...] = (
    "feMorphology",
    "feGaussianBlur",
    "feComponentTransfer",
    "feFlood",
    "feComposite",
)

_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")

Layer = Literal["world", "overlay"]
Unit = Literal["word", "glyph", "line", "block"]

#: The unit that typesets the whole string as ONE node, ``block_0`` (an#341):
#: what a replacement set swaps, since per-word units of different strings do
#: not line up.
BLOCK_UNIT: str = "block"

#: The swap set a text block with ``texts`` declares (an#341).
TEXT_SET: str = "text"


class TextFontError(ValueError):
    """A text block's font cannot be used: not a file, not a font, or not the
    face the typesetter actually used. Raised instead of falling back, because
    a fallback face is a different picture wearing the right one's clothes."""


class TextLayoutError(ValueError):
    """The text cannot be set as asked (a glyph the face lacks, nothing to draw)."""


class Counter(BaseModel):
    """A counter block's number-to-text rule (an#342): ``format`` in the
    declared d3-format subset (:mod:`an.formats`), and the value shown before
    any ``value`` action (``start``; ``None`` = the first action's value).

    >>> Counter(format="Day {d}", start=1).format
    'Day {d}'
    """

    model_config = ConfigDict(extra="forbid")

    format: str = "{d}"
    start: float | None = Field(default=None, allow_inf_nan=False)

    @model_serializer(mode="wrap")
    def _dump_what_was_authored(self, handler):
        return omit_unset(self, handler(self))

    @field_validator("format")
    @classmethod
    def _declared_subset(cls, fmt):
        from an.formats import parse_format

        parse_format(fmt)  # raises CounterFormatError (a ValueError), naming the subset
        return fmt

    def show(self, value: float) -> str:
        """``value`` as this counter draws it."""
        from an.formats import format_number

        return format_number(value, self.format)


#: The numeric fields of a tituli ``Halo``, checked here because a dataclass
#: does not check its own types: a string ``spread`` would fail in a filter.
_HALO_NUMBERS: tuple[str, ...] = ("spread", "blur", "gain", "opacity")


def _as_halo(value: Any) -> Any:
    """A text block's ``halo`` as a ``tituli.Halo`` (or ``None``), refusing
    what tituli would not draw: an unknown field, a non-number, a negative
    size, an opacity outside [0, 1], a colour tituli cannot parse.

    >>> _as_halo(True).spread, _as_halo({"blur": 0.2}).blur, _as_halo(None)
    (0.03, 0.2, None)
    >>> _as_halo({"glow": 1})
    Traceback (most recent call last):
    ...
    ValueError: `halo` has no field(s) ['glow']; it takes tituli's Halo fields ['blur', 'color', 'gain', 'opacity', 'spread']
    """
    if value is None or value is False:
        return None
    import dataclasses

    from tituli import Halo, parse_color

    if value is True:
        return Halo()
    if isinstance(value, Halo):
        fields = dataclasses.asdict(value)
    elif isinstance(value, Mapping):
        known = {f.name for f in dataclasses.fields(Halo)}
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(
                f"`halo` has no field(s) {unknown}; it takes tituli's Halo "
                f"fields {sorted(known)}"
            )
        fields = dict(value)
    else:
        raise ValueError(
            f"`halo` takes true, a mapping of tituli's Halo fields or a "
            f"tituli.Halo; got {value!r}"
        )
    for name in _HALO_NUMBERS:
        number = fields.get(name, 0.0)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"`halo.{name}` takes a number; got {number!r}")
        if not math.isfinite(number):
            raise ValueError(f"`halo.{name}` must be finite; got {number!r}")
    if isinstance(fields.get("color"), list):  # JSON has no tuples
        fields["color"] = tuple(fields["color"])
    if fields.get("color") is not None:
        try:
            parse_color(fields["color"])
        except (ValueError, TypeError) as err:
            raise ValueError(
                f"`halo.color` {fields['color']!r} is not a colour tituli reads: {err}"
            ) from None
    return Halo(**fields)  # its own checks raise ValueError (negative, opacity)


class TextDescriptor(BaseModel):
    """The on-disk text schema, saved as a prop's ``prop.json``.

    ``extra="forbid"`` (the `PathDescriptor` precedent): a text block is a
    precise instruction, and a misspelt ``colour`` that silently did nothing is
    the defect class this package refuses. Set-but-inert combinations raise too:

    >>> TextDescriptor(name="t", text="hi", anchor="top")
    Traceback (most recent call last):
    ...
    pydantic_core._pydantic_core.ValidationError: 1 validation error for TextDescriptor
      Value error, `anchor` places a block in the title-safe area of the FRAME, which only an overlay has; a world-layer block is placed with the entity's `stage.at` [type=value_error, input_value=..., input_type=dict]
    ...
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["TextDescriptor"] = "TextDescriptor"
    schema_version: str = TEXT_SCHEMA_VERSION
    name: str
    #: The words. Explicit newlines break lines; ``max_width`` wraps. Exactly
    #: one of ``text`` and ``texts`` is given.
    text: str | None = Field(default=None, min_length=1)
    #: A replacement set (an#341): ``{key: string}``, every string one drawing
    #: of the block, swapped by ``set <id> text <key>`` — replacement animation
    #: applied to text. Keys obey the swap-key rules (no ``/``, no ``::``).
    #: Requires ``unit="block"``.
    texts: dict[str, str] | None = None
    #: The key drawn when nothing has been set; default: the first key.
    rest: str | None = None
    #: A number that reads as text (an#342): ``tween <id> value a→b`` and
    #: ``set <id> value v`` are lowered at compile to a replacement set of the
    #: strings the frames show. Requires ``unit="block"``; no ``text``/``texts``.
    counter: Counter | None = None
    layer: Layer = "world"
    #: What one addressable node is: a word, a glyph, a whole line, or the
    #: whole block (``block_0``, one node however many lines).
    unit: Unit = "word"
    #: Fraction of frame height.
    size: float = Field(default=DFLT_TEXT_SIZE, gt=0, le=1, allow_inf_nan=False)
    #: ``#rrggbb``.
    color: str = DFLT_TEXT_COLOUR
    #: An outline around every glyph (an#313, OverSimplified's white labels
    #: edged in black): its visible thickness OUTSIDE the glyph, in scene
    #: pixels, drawn under the fill in the same texture, so a per-unit
    #: reveal shows outline and fill together. ``0`` = none.
    stroke_width: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    #: The outline's ``#rrggbb``; needs ``stroke_width``.
    stroke_color: str = DFLT_TEXT_STROKE_COLOUR
    #: A soft glow under every unit (an#701): tituli's own ``Halo`` (one
    #: vocabulary for both packages), given as ``true`` (the default halo), a
    #: mapping of its fields (``color``, ``spread``, ``blur``, ``gain``,
    #: ``opacity``; sizes in em) or a ``tituli.Halo``. ``color`` unset is the
    #: opposite of ``color`` (``tituli.color.ink_for``). Drawn in each unit's
    #: own texture, under the outline and the fill, with SVG filters the
    #: shot's engine must afford (``engine.svg_filter``).
    halo: Any = Field(
        default=None,
        json_schema_extra={
            "anyOf": [
                {"type": "boolean"},
                {
                    "type": "object",
                    "properties": {
                        "color": {},
                        "spread": {"type": "number", "minimum": 0},
                        "blur": {"type": "number", "minimum": 0},
                        "gain": {"type": "number", "minimum": 0},
                        "opacity": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]
        },
    )
    #: ``None`` = the embedded face; else a font FILE path (see the module doc).
    font: str | None = None
    #: OpenType features to apply, by tag (an#362): ``["tnum"]`` sets tabular
    #: figures. ``None`` = the block's default: a ``counter`` asks for
    #: :data:`COUNTER_FEATURES`, anything else for none. Whether the face
    #: has them is recorded with it (``meta.fonts``, ``features:``).
    features: list[str] | None = None
    align: Literal["left", "center", "right"] = "center"
    #: Wrap width as a fraction of frame WIDTH; ``None`` = break only at newlines.
    max_width: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    leading: float = Field(default=DFLT_LEADING, gt=0, allow_inf_nan=False)
    #: Extra advance per glyph, in em. Only with ``unit="glyph"``: tituli sets a
    #: tracked string one run per glyph, so a word unit would not exist.
    tracking: float = Field(default=0.0, allow_inf_nan=False)
    #: Overlay only: one of tituli's nine anchors (``"top"``, ``"bottom-left"``,
    #: ``"center"``, …) inside the title-safe area. ``None`` centres the block
    #: on the node origin (the frame centre, or ``stage.at``).
    anchor: str | None = None
    source: AssetSource | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _dump_what_was_authored(self, handler):
        """Dump only the fields the author set (plus ``kind``/``schema_version``),
        so ``model_validate_json(d.model_dump_json())`` always round-trips — the
        set-but-inert checks read ``model_fields_set``, and a full dump would
        mark every default as set (:func:`an.ir.migrate.omit_unset`)."""
        return omit_unset(self, handler(self))

    @field_validator("color", "stroke_color")
    @classmethod
    def _hex(cls, color):
        if not _HEX_COLOUR.fullmatch(color):
            raise ValueError(f"`color` takes a #rrggbb string; got {color!r}")
        return color

    @field_validator("halo", mode="before")
    @classmethod
    def _a_tituli_halo(cls, halo):
        return _as_halo(halo)

    @field_validator("text")
    @classmethod
    def _something_to_draw(cls, text):
        if text is not None and not text.strip():
            raise ValueError("`text` is only whitespace, so it would draw nothing")
        return text

    @field_validator("texts")
    @classmethod
    def _a_set_of_drawings(cls, texts):
        if texts is None:
            return texts
        if not texts:
            raise ValueError("`texts` is empty, so the block would draw nothing")
        from an.base import SWAP_SET_NAME_FORBIDDEN_SUBSTRINGS

        for key, string in texts.items():
            bad = [b for b in SWAP_SET_NAME_FORBIDDEN_SUBSTRINGS if b in key]
            if not key or bad:
                raise ValueError(
                    f"`texts` key {key!r} cannot be a swap key"
                    + (f" (it contains {bad[0]!r}, which is reserved)" if bad else "")
                )
            if not string.strip():
                raise ValueError(
                    f"`texts[{key!r}]` is only whitespace, so it would draw nothing"
                )
        return texts

    @property
    def rest_key(self) -> str | None:
        """The key a block with ``texts`` shows at rest (``rest``, else the
        first key); ``None`` for a single-string block."""
        if self.texts is None:
            return None
        return self.rest if self.rest is not None else next(iter(self.texts))

    @property
    def typeset_features(self) -> tuple[str, ...]:
        """The features the block is set with: its own, else a counter's
        tabular figures (an#362), so a number does not change width as it counts.

        >>> TextDescriptor(name="n", counter={"format": "{d}"}, unit="block").typeset_features
        ('tnum',)
        >>> TextDescriptor(name="t", text="x").typeset_features
        ()
        """
        if self.features is not None:
            return tuple(self.features)
        return COUNTER_FEATURES if self.counter is not None else ()

    @property
    def content(self) -> str:
        """The string the block draws at rest (a counter: its ``start``, else
        zero, until the compiler lowers its ``value`` channel)."""
        if self.counter is not None:
            return self.counter.show(self.counter.start or 0.0)
        return self.texts[self.rest_key] if self.texts is not None else self.text

    @model_validator(mode="after")
    def _nothing_set_is_ignored(self) -> "TextDescriptor":
        given = [
            name
            for name in ("text", "texts", "counter")
            if getattr(self, name) is not None
        ]
        if len(given) != 1:
            raise ValueError(
                "a text block draws `text` (one string), `texts` (a replacement "
                "set, an#341) or `counter` (a number, an#342); "
                + (
                    f"{' and '.join(given)} were given"
                    if given
                    else "neither was given"
                )
            )
        if given[0] != "text" and self.unit != BLOCK_UNIT:
            raise ValueError(
                f"`{given[0]}` swaps the WHOLE string, so it needs unit='block' (one "
                f"node, `block_0`); got unit={self.unit!r}. Per-{self.unit} units "
                "of different strings do not line up, and a tween on one could "
                "not say which string it meant."
            )
        if self.rest is not None:
            if self.texts is None:
                raise ValueError(
                    "`rest` names the key a replacement set shows at rest; it "
                    "needs `texts`"
                )
            if self.rest not in self.texts:
                raise ValueError(
                    f"`rest` is {self.rest!r}, which is not a key of `texts` "
                    f"(it has: {sorted(self.texts)})"
                )
        if self.anchor is not None:
            if self.layer != "overlay":
                raise ValueError(
                    "`anchor` places a block in the title-safe area of the FRAME, "
                    "which only an overlay has; a world-layer block is placed with "
                    "the entity's `stage.at`"
                )
            from tituli import ANCHORS

            if self.anchor not in ANCHORS:
                raise ValueError(
                    f"unknown anchor {self.anchor!r}; choose from {sorted(ANCHORS)}"
                )
        if "stroke_color" in self.model_fields_set and not self.stroke_width:
            raise ValueError(
                "`stroke_color` colours an outline, and `stroke_width` is 0, so "
                "nothing would draw it; give `stroke_width` (scene px)"
            )
        if self.tracking and self.unit != "glyph":
            raise ValueError(
                f"`tracking` sets a string one run per GLYPH, so unit={self.unit!r} "
                "would not exist; use unit='glyph' or drop tracking"
            )
        if self.font is not None and not self.font.lower().endswith(FONT_SUFFIXES):
            raise ValueError(
                f"`font` must name a font FILE ({'/'.join(FONT_SUFFIXES)}); got "
                f"{self.font!r}. A family name is refused on purpose: resolving "
                "one would make the picture depend on the machine's installed "
                "fonts. Leave it unset for the embedded face."
            )
        return self


def resolve_text(
    document: Mapping[str, Any], overrides: Mapping[str, Any] | None = None
) -> TextDescriptor:
    """The text block an entity draws: its stored document with ``overrides`` on top.

    Validated strictly AFTER the merge, so a stored document may be a reusable
    style with no ``text`` of its own, and each entity supplies the words:

    >>> style = {"kind": "TextDescriptor", "name": "label", "size": 0.04}
    >>> resolve_text(style, {"text": "Paris"}).text
    'Paris'
    """
    stored = migrate(dict(document), kind=TEXT_DOCUMENT_KIND.name)
    merged = {**stored, **asset_overrides(overrides)}
    return TextDescriptor.model_validate(merged)


def font_base_dir(props_store: Mapping, ref: str) -> Path | None:
    """What a relative ``font`` path resolves against: the text document's own
    directory in an on-disk props store — ``None`` for an in-memory one, where a
    relative path then RAISES rather than resolving against the working
    directory (which would make the picture depend on where you ran it)."""
    root = getattr(props_store, "_root", None)
    return Path(root) / ref if root is not None else None


# -----------------------------------------------------------------------------
# Layout (through tituli)
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class FontIdentity:
    """Which face drew a block — by its bytes, not its name."""

    family: str
    style: str
    sha256: str
    embedded: bool

    #: Pillow's layout engine for this face (``basic`` or ``raqm``). Recorded
    #: because it moves glyph ADVANCES: RAQM (HarfBuzz) applies kerning and
    #: ligatures and is used for a font file whenever libraqm can be loaded,
    #: so the same bytes can set differently on two machines. The embedded
    #: face is always ``basic``.
    layout_engine: str = "basic"
    #: The requested OpenType features this face applied (an#362): a tag
    #: asked for and missing here was not in the font. Labelled only when
    #: there is one, so a block without features labels as before.
    features: tuple[str, ...] = ()

    def label(self) -> str:
        """``"Aileron Regular (embedded) sha256:6985… layout:basic"`` — what the
        compiled document records."""
        where = " (embedded)" if self.embedded else ""
        return (
            f"{self.family} {self.style}{where} sha256:{self.sha256} "
            f"layout:{self.layout_engine}"
            + (f" features:{','.join(self.features)}" if self.features else "")
        )


@dataclass(frozen=True)
class HaloPaint:
    """A tituli ``Halo`` resolved for one unit: frame pixels and one colour.

    What a unit's texture draws (an#701): the glyphs' alpha dilated by
    ``spread`` (whole pixels, as tituli rounds it), blurred with a Gaussian
    of standard deviation ``blur``, multiplied by ``gain`` and clipped to
    opaque, then laid in ``color`` at ``alpha`` (the halo's ``opacity`` times
    its colour's own alpha) — tituli's ``glow`` and ``draw_halo``, step for
    step.
    """

    color: str
    alpha: float
    spread: int
    blur: float
    gain: float

    @property
    def reach(self) -> int:
        """Whole pixels the glow reaches past the ink: the unit's box grows by it."""
        return self.spread + math.ceil(HALO_BLUR_REACH * self.blur)

    @property
    def cover(self) -> float:
        """Pixels past the ink where the glow still visibly covers another
        unit's glyphs (:data:`HALO_COVER_SIGMAS`)."""
        return self.spread + HALO_COVER_SIGMAS * self.blur


def halo_paint(halo: Any, *, em: float, ink: str) -> HaloPaint:
    """``halo`` (a ``tituli.Halo``) at a type size of ``em`` pixels, under
    glyphs drawn in ``ink``: its em sizes in pixels, its colour (unset = the
    opposite of the ink, ``tituli.color.ink_for``) and its final alpha.

    >>> from tituli import Halo
    >>> p = halo_paint(Halo(), em=100, ink="#ffffff")
    >>> p.color, p.spread, p.blur, p.gain, p.alpha, p.reach
    ('#111111', 3, 10.0, 2.0, 0.65, 33)
    >>> halo_paint(Halo(color="#ffd40080", opacity=1.0), em=40, ink="#000000").alpha
    0.5019607843137255
    """
    from tituli import ink_for, parse_color
    from tituli.color import relative_luminance

    if halo.color is not None:
        r, g, b, a = parse_color(halo.color)
    else:
        r, g, b, a = parse_color(ink_for(luminance=relative_luminance(ink)))
    return HaloPaint(
        color=f"#{r:02x}{g:02x}{b:02x}",
        alpha=halo.opacity * a / _ALPHA_MAX,
        spread=max(0, round(halo.spread * em)),
        blur=halo.blur * em,
        gain=float(halo.gain),
    )


@dataclass(frozen=True)
class TextUnit:
    """One addressable unit: its node name, its string, its box and its ink.

    ``box`` is ``(x0, y0, x1, y1)`` in frame pixels, snapped OUTWARD to whole
    pixels and containing both the layout box and the ink, so the sprite's
    corners sit on the pixel grid and nothing is clipped. ``d`` is the unit's
    glyph contours as SVG path data in frame pixels. ``halo`` is the glow
    drawn under it (an#701), ``None`` for none.
    """

    name: str
    text: str
    box: tuple[int, int, int, int]
    d: str
    halo: HaloPaint | None = None

    @property
    def size(self) -> tuple[int, int]:
        """``(width, height)`` of ``box``."""
        return self.box[2] - self.box[0], self.box[3] - self.box[1]

    @property
    def center(self) -> tuple[float, float]:
        """The box centre in frame pixels — where the unit's node sits."""
        return (self.box[0] + self.box[2]) / 2.0, (self.box[1] + self.box[3]) / 2.0


@dataclass(frozen=True)
class TextLayout:
    """A placed block: its units, its reference point, and the face that set it.

    ``origin`` is the block's reference point in frame pixels — the frame
    centre, or its title-safe anchor position — which is where the block's own
    node sits; each unit's node is placed relative to it.
    """

    units: tuple[TextUnit, ...]
    origin: tuple[float, float]
    font: FontIdentity
    #: The block's LAYOUT box ``(x0, y0, x1, y1)`` in frame pixels: advances
    #: and line heights, not ink, so two strings of one face share a baseline
    #: and their ``align`` edges can be lined up (an#341).
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def _font_request(desc: TextDescriptor, base_dir: Path | None) -> tuple[str, ...]:
    from tituli import EMBEDDED

    if desc.font is None:
        return (EMBEDDED,)
    path = Path(desc.font).expanduser()
    if not path.is_absolute():
        if base_dir is None:
            raise TextFontError(
                f"text {desc.name!r}: font {desc.font!r} is a relative path, and "
                "there is no directory to resolve it against (the props store "
                "has no filesystem root). Give an absolute path, or keep the "
                "font beside the text document in an on-disk props store."
            )
        path = Path(base_dir) / path
    if not path.is_file():
        raise TextFontError(
            f"text {desc.name!r}: font {desc.font!r} is not a file (looked at "
            f"{path}). A missing font is refused rather than replaced: a "
            "substitute face is a different picture."
        )
    return (str(path),)


def layout_text(
    desc: TextDescriptor,
    *,
    width: int,
    height: int,
    base_dir: Path | str | None = None,
) -> TextLayout:
    """Set ``desc`` on a ``width`` x ``height`` frame and take each unit's contours.

    ``base_dir`` is what a relative ``font`` path resolves against — the text
    document's own directory in the props store. A block with ``texts`` is set
    with its rest string (:func:`layout_text_set` sets every one).

    >>> lay = layout_text(TextDescriptor(name="t", text="Hello big world"), width=1920, height=1080)
    >>> [u.name for u in lay.units]
    ['word_0', 'word_1', 'word_2']
    >>> lay.origin
    (960.0, 540.0)
    >>> lay.font.family, lay.font.embedded
    ('Aileron', True)
    >>> [u.name for u in layout_text(TextDescriptor(name="t", text="two\\nlines", unit="block"), width=1920, height=1080).units]
    ['block_0']
    """
    return _layout_string(
        desc, desc.content, width=width, height=height, base_dir=base_dir
    )


def text_set_keys(desc: TextDescriptor) -> dict[str, str]:
    """``{key: key}`` for a block's replacement set — the ``text`` set as a
    swap declaration states it (``{}`` for a single-string block).

    >>> text_set_keys(TextDescriptor(name="t", texts={"a": "1", "b": "2"}, unit="block"))
    {'a': 'a', 'b': 'b'}
    """
    return {key: key for key in (desc.texts or {})}


def layout_text_set(
    desc: TextDescriptor,
    *,
    width: int,
    height: int,
    base_dir: Path | str | None = None,
) -> dict[str, TextLayout]:
    """Every string of a block's replacement set, set once: ``{key: layout}``.

    Each is set exactly as a single-string block would be, so each is centred
    (or anchored) on its own; lining their ``align`` edges up is the
    builder's job (:func:`an.stage.text_layout.build_text_subtree`). A block
    with no ``texts`` returns ``{}``.

    >>> lays = layout_text_set(TextDescriptor(name="t", texts={"a": "1", "b": "22"}, unit="block"), width=320, height=240)
    >>> sorted(lays), [lay.units[0].name for lay in lays.values()]
    (['a', 'b'], ['block_0', 'block_0'])
    """
    return {
        key: _layout_string(desc, string, width=width, height=height, base_dir=base_dir)
        for key, string in (desc.texts or {}).items()
    }


def _layout_string(
    desc: TextDescriptor,
    text: str,
    *,
    width: int,
    height: int,
    base_dir: Path | str | None,
) -> TextLayout:
    from tituli import (
        TextStyle,
        block,
        face_digest,
        run_outline,
        safe_area,
    )
    from tituli.geometry import anchor_box
    from tituli.outlines import MissingGlyphError

    request = _font_request(desc, Path(base_dir) if base_dir is not None else None)
    style = TextStyle(
        family=request,
        features=desc.typeset_features,
        size=desc.size,
        tracking=desc.tracking,
        leading=desc.leading,
        align=desc.align,
    )
    max_w = desc.max_width * width if desc.max_width is not None else None
    for old, new in _WHITESPACE_NORMALISATION:
        text = text.replace(old, new)
    # tituli sets lines; a block is its lines drawn as ONE unit (below).
    typeset_unit = "line" if desc.unit == BLOCK_UNIT else desc.unit
    lay = block(text, style, float(height), max_width=max_w, unit=typeset_unit)
    _refuse_plates(desc, lay)
    if desc.halo is not None:
        # The block's halo rides on its runs, tituli's own carrier for it
        # (tituli#19): one place says which glow a unit draws, whether the
        # document asked for it or the layout came with one (an#682).
        lay = lay.with_halo(desc.halo)
    runs = [r for r in lay.runs if r.text.strip()]
    if not runs:
        raise TextLayoutError(f"text {desc.name!r} lays out to nothing drawable")
    face = runs[0].face
    if desc.font is not None and face.path != request[0]:
        raise TextFontError(
            f"text {desc.name!r}: font {desc.font!r} is a file, but the typesetter "
            f"could not use it and set the text in {face.family!r} instead. "
            "Refused rather than drawn in the wrong face — is it a font file?"
        )

    bb = lay.bbox()
    if desc.anchor is not None:
        cx, cy = anchor_box(
            safe_area(width, height), (bb.width, bb.height), desc.anchor
        ).center
    else:
        cx, cy = width / 2.0, height / 2.0
    origin = (float(round(cx)), float(round(cy)))
    dx = origin[0] - (bb.x0 + bb.x1) / 2.0
    dy = origin[1] - (bb.y0 + bb.y1) / 2.0

    inked = []  # (run, outline) of every run with ink, in reading order
    for run in (r.translated(dx, dy) for r in runs):
        try:
            outline = run_outline(run)
        except MissingGlyphError as err:
            raise TextLayoutError(
                f"text {desc.name!r}: {err}. `an` sets English-first text and "
                "refuses a character the face cannot draw rather than drawing a "
                "box; give a `font` file that has it, or change the words."
            ) from err
        if outline.bbox is not None:
            inked.append((run, outline))
    if desc.stroke_width and desc.unit in ("word", "glyph"):
        _warn_if_outlines_overlap(desc, inked)
    if desc.unit == BLOCK_UNIT:
        # One unit for the whole block: the lines' contours in one path, the
        # union of their boxes (an#341).
        groups = [inked] if inked else []
    else:
        groups = [[pair] for pair in inked]
    units: list[TextUnit] = []
    for group in groups:
        box = group[0][0].bbox().union(group[0][1].bbox)
        for run, outline in group[1:]:
            box = box.union(run.bbox()).union(outline.bbox)
        halo = _unit_halo(desc, group)
        # The outline reaches `stroke_width` past the ink (an#313), the
        # halo its `reach` (an#701); the box holds the further of the two.
        pad = UNIT_BOX_PAD_PX + math.ceil(
            max(desc.stroke_width, halo.reach if halo is not None else 0)
        )
        units.append(
            TextUnit(
                name=f"{desc.unit}_{len(units)}",
                text="\n".join(run.text for run, _ in group),
                box=(
                    math.floor(box.x0) - pad,
                    math.floor(box.y0) - pad,
                    math.ceil(box.x1) + pad,
                    math.ceil(box.y1) + pad,
                ),
                d=" ".join(outline.d for _, outline in group),
                halo=halo,
            )
        )
    _warn_if_halos_cover(desc, groups, units)
    identity = FontIdentity(
        family=face.family,
        style=face.style,
        sha256=face_digest(face),
        embedded=face.path is None,
        layout_engine=_layout_engine_name(face),
        features=face.applied_features,
    )
    return TextLayout(
        units=tuple(units),
        origin=origin,
        font=identity,
        bounds=(bb.x0 + dx, bb.y0 + dy, bb.x1 + dx, bb.y1 + dy),
    )


def _refuse_plates(desc: TextDescriptor, lay: Any) -> None:
    """Refuse a layout carrying tituli ``plates`` (scrims, boxes, rules drawn
    under the runs): ``an`` draws a block's units and nothing else, so a
    plate would be silently left off the film. ``tituli.block`` makes none
    today; this guards against that changing, the way an#682 guarded halos,
    until ``an`` draws one (an#701's review)."""
    plates = tuple(getattr(lay, "plates", ()) or ())
    if plates:
        kinds = sorted({getattr(p, "kind", "?") for p in plates})
        raise TextLayoutError(
            f"text {desc.name!r}: `tituli.block` returned {len(plates)} plate(s) "
            f"({', '.join(kinds)}) under the text, which `an` does not draw: it "
            "would leave the scrim off. Give the block a plate as an environment "
            "plane or a prop behind it, or a `halo` for legibility over footage."
        )


def _unit_halo(desc: TextDescriptor, group: Sequence[Any]) -> HaloPaint | None:
    """The glow one unit draws: the halo its runs carry (the block's own
    ``halo``, or one the layout came with — an#682's refusal is lifted for
    what ``an`` can draw), resolved at the runs' type size.

    A unit is one texture with one underlay, so a ``block`` unit whose lines
    carry DIFFERENT halos (or some none) is refused, naming them, rather than
    drawn with one of them."""
    halos = {getattr(run, "halo", None) for run, _ in group}
    if len(halos) > 1:
        lines = [run.text for run, _ in group]
        raise TextLayoutError(
            f"text {desc.name!r}: one {desc.unit} unit ({lines[:3]}"
            f"{', ...' if len(lines) > 3 else ''}) has runs carrying different "
            "halos, and a unit draws ONE glow under its glyphs. Set one `halo` "
            "on the block, or use `unit: line` so each line is its own unit."
        )
    (halo,) = halos
    if halo is None:
        return None
    run = group[0][0]
    return halo_paint(halo, em=run.face.size, ink=desc.color)


class TextOutlineWarning(UserWarning):
    """A unit's outline is wide enough to cover its neighbour's glyphs."""


def _warn_if_outlines_overlap(desc: TextDescriptor, inked: list) -> None:
    """Each unit is its own texture, so a unit's outline is drawn OVER the
    fill of the unit before it wherever the two meet (an#313): two units on
    one line closer than twice ``stroke_width`` show it. Said once, naming
    the remedies, rather than drawn silently."""
    import warnings

    reach = 2 * desc.stroke_width
    for (a, oa), (b, ob) in zip(inked, inked[1:]):
        ink_a, ink_b = oa.bbox, ob.bbox
        same_line = ink_a.y0 < ink_b.y1 and ink_b.y0 < ink_a.y1
        if same_line and ink_b.x0 - ink_a.x1 < reach:
            warnings.warn(
                f"text {desc.name!r}: a {desc.stroke_width:g} px outline reaches "
                f"across the gap between {a.text!r} and {b.text!r}, so each "
                f"{desc.unit}'s outline covers part of the one before it (every "
                "unit is its own texture). Use a thinner `stroke_width`, a larger "
                "`size`, or `unit: line`/`block` for a heavy outline.",
                TextOutlineWarning,
                stacklevel=4,
            )
            return


class TextHaloWarning(UserWarning):
    """A unit's halo reaches far enough to dim a neighbouring unit's glyphs."""


def _warn_if_halos_cover(
    desc: TextDescriptor, groups: Sequence[Any], units: Sequence[TextUnit]
) -> None:
    """Each unit is its own texture, so a unit's halo is drawn OVER every
    earlier unit's fill wherever it reaches (an#701) — tituli draws every
    halo first and every text after, which per-unit alpha rules out here (the
    an#313 trade). Two units whose inks are closer than the glow's visible
    ``cover`` show it; said once, naming the remedies."""
    import warnings

    inks = []
    for group in groups:
        ink = group[0][1].bbox
        for _, outline in group[1:]:
            ink = ink.union(outline.bbox)
        inks.append(ink)
    for j, (unit_b, ink_b) in enumerate(zip(units, inks)):
        if unit_b.halo is None:
            continue
        cover = unit_b.halo.cover
        for unit_a, ink_a in zip(units[:j], inks[:j]):
            gap_x = max(ink_a.x0 - ink_b.x1, ink_b.x0 - ink_a.x1)
            gap_y = max(ink_a.y0 - ink_b.y1, ink_b.y0 - ink_a.y1)
            if gap_x < cover and gap_y < cover:
                warnings.warn(
                    f"text {desc.name!r}: the halo of {unit_b.text!r} reaches "
                    f"{cover:.1f} px past its ink, over {unit_a.text!r} (every "
                    f"{desc.unit} is its own texture, so a later unit's glow is "
                    "drawn over an earlier one's glyphs). Use a smaller "
                    "`halo.spread`/`halo.blur`, or `unit: line`/`block`.",
                    TextHaloWarning,
                    stacklevel=4,
                )
                return


def halo_engine_problem(units: Sequence[TextUnit], renderer: str | None) -> str | None:
    """What stops ``renderer`` drawing these units' halos, or ``None``.

    A halo is SVG filters in the unit's texture (:data:`HALO_FILTER_PRIMITIVES`);
    an engine that does not afford them as ``engine.svg_filter`` keys would
    draw the glyphs with no glow, so the compiler raises on this and ``an
    validate`` reports it. A renderer that is not registered is left to its
    own check.

    >>> halo_engine_problem([], "stage") is None
    True
    """
    if renderer is None or not any(u.halo is not None for u in units):
        return None
    from an.capabilities.subjects import ENGINE_SVG_FILTER, missing_engine_terms

    lacking = missing_engine_terms(
        renderer, [f"{ENGINE_SVG_FILTER.name}:{p}" for p in HALO_FILTER_PRIMITIVES]
    )
    if not lacking:
        return None
    return (
        f"a text `halo` is drawn with SVG filters ({lacking}), which renderer "
        f"{renderer!r} does not afford: {ENGINE_SVG_FILTER.remedy}"
    )


def _layout_engine_name(face) -> str:
    from PIL import ImageFont

    engine = getattr(face.pil, "layout_engine", ImageFont.Layout.BASIC)
    return "raqm" if engine == ImageFont.Layout.RAQM else "basic"


def text_entity_problem(entity: Any, desc: TextDescriptor) -> str | None:
    """What is wrong with WHERE this entity puts its block, or ``None``.

    The one statement of the placement rules, called by the compiler (which
    raises) and by ``an validate`` (which reports) so the two agree:

    - a reserved id (:data:`RESERVED_TEXT_IDS`) — ``root`` would hijack the
      camera's node in the runtime's index;
    - ``anchor`` and ``stage.at`` together — two answers to one question.
    """
    if entity.id in RESERVED_TEXT_IDS:
        return (
            f"text entity id {entity.id!r} is reserved ({sorted(RESERVED_TEXT_IDS)}): "
            "the runtime names its own containers so, and `root` is the camera"
        )
    stage = getattr(entity, "stage", None)
    if desc.anchor is not None and stage is not None and stage.at is not None:
        return (
            f"text {entity.id!r} declares both `anchor: {desc.anchor}` and "
            f"`stage.at: {list(stage.at)}`; they are two answers to where the "
            "block goes. Keep one."
        )
    return None


def unit_names(
    desc: TextDescriptor,
    *,
    width: int,
    height: int,
    base_dir: Path | str | None = None,
) -> list[str]:
    """The node names a block builds — what ``<id>/<name>`` targets may address."""
    lay = layout_text(desc, width=width, height=height, base_dir=base_dir)
    return [u.name for u in lay.units]


# -----------------------------------------------------------------------------
# Presets: Python-side generators of ordinary composition
# -----------------------------------------------------------------------------


def reveal_units(
    entity_id: str,
    count: int,
    property: str,
    *,
    to: Any,
    from_: Any,
    duration: float,
    step: float,
    start: float = 0.0,
    unit: Unit = "word",
    easing: Any = "ease_out",
) -> list:
    """Tween ``property`` from ``from_`` to ``to`` on units ``0..count-1`` of a
    text block, each ``step`` seconds after the last — a word-by-word (or
    letter-by-letter) reveal. Unit ``i`` starts at ``start + i*step``.

    A unit whose tween starts later also gets a ``set`` to ``from_`` at 0, which
    HOLDS until its tween begins (the compiler's set-hold rule) — without it the
    word would show its built value until its turn and then snap to ``from_``.
    That is also why ``from_`` is required.

    Returns a LIST of top-level actions — ``set``, a bare ``tween``, or the
    ``sequence(delay(start), tween)`` wrapper the ``scene.md`` parser itself
    produces for a ``start:`` key — so ``shot.actions.extend(stagger(...))``
    round-trips through ``scene.md`` in its short form, one entry per unit.

    Named ``stagger`` until an#241 gave the core a general combinator of that
    name (:func:`an.ir.compose.stagger`, any actions, one ``parallel``);
    ``an.stage.text.stagger`` stays as an alias of this function so old imports
    keep working.

    >>> [a.kind for a in reveal_units("t", 2, "alpha", to=1, from_=0, duration=0.2, step=0.1)]
    ['tween', 'set', 'sequence']
    """
    from an.ir import compose as c

    if count < 1:
        raise ValueError(f"reveal_units needs at least one unit; got count={count}")
    out = []
    for i in range(count):
        target = f"{entity_id}/{unit}_{i}"
        tween = c.tween(
            target, property, to=to, from_=from_, duration=duration, easing=easing
        )
        at = start + i * step
        if at > 0:
            out.append(c.set_(target, property, from_, at=0.0))
            out.append(c.sequence(c.delay(at), tween))
        else:
            out.append(tween)
    return out


#: The pre-an#241 name of :func:`reveal_units`, kept so old imports work.
stagger = reveal_units
