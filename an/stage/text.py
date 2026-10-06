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
from typing import Any, Literal, Mapping

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from an.ir.assets import AssetSource
from an.ir.migrate import DocumentKind, migrate, omit_unset, register_kind

__all__ = [
    "TEXT_SCHEMA_VERSION",
    "TEXT_DOCUMENT_KIND",
    "TextDescriptor",
    "Counter",
    "TextFontError",
    "TextLayoutError",
    "TextUnit",
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

#: Line height as a multiple of the size.
DFLT_LEADING: float = 1.2

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
    #: ``None`` = the embedded face; else a font FILE path (see the module doc).
    font: str | None = None
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

    @field_validator("color")
    @classmethod
    def _hex(cls, color):
        if not _HEX_COLOUR.fullmatch(color):
            raise ValueError(f"`color` takes a #rrggbb string; got {color!r}")
        return color

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
    merged = {**stored, **dict(overrides or {})}
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

    def label(self) -> str:
        """``"Aileron Regular (embedded) sha256:6985… layout:basic"`` — what the
        compiled document records."""
        where = " (embedded)" if self.embedded else ""
        return (
            f"{self.family} {self.style}{where} sha256:{self.sha256} "
            f"layout:{self.layout_engine}"
        )


@dataclass(frozen=True)
class TextUnit:
    """One addressable unit: its node name, its string, its box and its ink.

    ``box`` is ``(x0, y0, x1, y1)`` in frame pixels, snapped OUTWARD to whole
    pixels and containing both the layout box and the ink, so the sprite's
    corners sit on the pixel grid and nothing is clipped. ``d`` is the unit's
    glyph contours as SVG path data in frame pixels.
    """

    name: str
    text: str
    box: tuple[int, int, int, int]
    d: str

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
        units.append(
            TextUnit(
                name=f"{desc.unit}_{len(units)}",
                text="\n".join(run.text for run, _ in group),
                box=(
                    math.floor(box.x0) - UNIT_BOX_PAD_PX,
                    math.floor(box.y0) - UNIT_BOX_PAD_PX,
                    math.ceil(box.x1) + UNIT_BOX_PAD_PX,
                    math.ceil(box.y1) + UNIT_BOX_PAD_PX,
                ),
                d=" ".join(outline.d for _, outline in group),
            )
        )
    identity = FontIdentity(
        family=face.family,
        style=face.style,
        sha256=face_digest(face),
        embedded=face.path is None,
        layout_engine=_layout_engine_name(face),
    )
    return TextLayout(
        units=tuple(units),
        origin=origin,
        font=identity,
        bounds=(bb.x0 + dx, bb.y0 + dy, bb.x1 + dx, bb.y1 + dy),
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
