"""Surface treatments, compiled (an#163 gap 5): outline, paper-gap shadow, glow, grain.

Every treatment here is a COMPILE-TIME expansion into ordinary document
content. None is a runtime filter, and none draws anything random at render
time. ``runtime.js`` keeps its rule against per-frame randomness, and its
determinism probe still sees zero filters.

- **Outline and paper-gap shadow**: :class:`~an.adapters.cutout.serialize.UnderlayJSON`
  entries on a part's visual. The runtime draws each one as a copy of the
  part's own visual, BEHIND it, in the part's own container. So the copy takes
  every transform the part takes (tweens, ``play``, the camera, a stage scale)
  and needs no channel of its own. A swap on the part (a viseme, a blink)
  re-textures its copies in the same call.
- **Glow**: one extra child node, first in the entity so it draws behind every
  part. It is a radial-gradient SVG sprite, drawn with the engine's native
  ``add`` blend.
- **Grain**: one seeded noise tile, made here as a palette PNG and tiled on the
  camera-immune overlay under any text, drawn with the native ``multiply``
  blend. The PNG bytes are fully determined by the seed. The deflate stream is
  written as STORED blocks by hand, because a compressor's output is not
  stable across zlib builds (zlib-ng differs), and the texture is part of the
  scene contract.

A scene whose pack sets none of these compiles byte-identically to before.
Nothing here runs without a treatment, and the new wire fields are omitted
when unset.
"""

from __future__ import annotations

import base64
import hashlib
import math
import struct
import zlib
from typing import TYPE_CHECKING

from an.adapters.cutout.serialize import (
    AssetJSON,
    NodeJSON,
    TransformJSON,
    UnderlayJSON,
    VisualJSON,
)

if TYPE_CHECKING:  # pragma: no cover
    from an.styles import Glow, Grain, SurfaceTreatment

__all__ = [
    "OUTLINE_RING",
    "UNDERLAY_KINDS",
    "GLOW_NODE",
    "GRAIN_NODE",
    "GRAIN_LEVELS",
    "ring_offsets",
    "apply_surface",
    "drawn_box",
    "glow_svg",
    "grain_indices",
    "grain_greys",
    "grain_png",
    "grain_node",
    "faded_treated_targets",
]

#: The directions of an SVG part's outline ring: eight unit vectors, stated
#: exactly rather than as ``cos``/``sin`` values, because the offsets go into
#: the scene contract and a libm's last bit is not the same on every machine.
#: Eight copies at radius ``w`` cover the true dilation to within
#: ``w·(1 − cos 22.5°) ≈ 0.08·w`` along a straight or gently curved edge — a
#: quarter pixel at the default 3. At a sharp tip, or a feature thinner than
#: ``w``, the gap between neighbouring copies can reach ``w·sin 22.5° ≈ 0.38·w``.
_R = math.sqrt(0.5)  # correctly rounded by IEEE 754, so the same everywhere
_RING_DIRECTIONS: tuple[tuple[float, float], ...] = (
    (1.0, 0.0),
    (_R, _R),
    (0.0, 1.0),
    (-_R, _R),
    (-1.0, 0.0),
    (-_R, -_R),
    (0.0, -1.0),
    (_R, -_R),
)
OUTLINE_RING: int = len(_RING_DIRECTIONS)

#: The visual kinds a copy can be drawn for. `runtime.js` refuses any other.
#: An eye already draws its own rim, a procedural mouth is a redraw function,
#: and a path is already a line.
UNDERLAY_KINDS: frozenset[str] = frozenset({"rect", "ellipse", "svg_sprite"})

#: The glow's node name inside its entity, and the grain's on the overlay.
#: Leading underscore: no rig slot or entity id is spelled like this, and a
#: collision with an overlay entity still raises in `compile_shot`.
GLOW_NODE: str = "_glow"
GRAIN_NODE: str = "_grain"

#: Grey levels in the grain tile. 16 = a 4-bit palette PNG (half the bytes
#: of an 8-bit one), and finer steps than 8-bit output could show at the small
#: `amount`s grain is used at.
GRAIN_LEVELS: int = 16
_GRAIN_BIT_DEPTH: int = 4  # a 4-bit palette PNG holds exactly GRAIN_LEVELS
assert GRAIN_LEVELS == 1 << _GRAIN_BIT_DEPTH

#: Digits kept from a float before it enters the document (offsets, sizes), so
#: tiny FP noise cannot move the contract.
_DIGITS: int = 6

#: Hex digits of a texture's sha256 kept in its alias (as `text.py` does).
_ALIAS_DIGEST_LEN: int = 12


def ring_offsets(radius: float) -> list[tuple[float, float]]:
    """The outline ring's copy offsets at ``radius`` pixels.

    >>> ring_offsets(2.0)[:3]
    [(2.0, 0.0), (1.414214, 1.414214), (0.0, 2.0)]
    >>> len(ring_offsets(3.0)) == OUTLINE_RING
    True
    """
    return [
        (round(radius * dx, _DIGITS) + 0.0, round(radius * dy, _DIGITS) + 0.0)
        for dx, dy in _RING_DIRECTIONS
    ]


# -----------------------------------------------------------------------------
# Outline, shadow, glow — per entity
# -----------------------------------------------------------------------------


def apply_surface(
    node: NodeJSON,
    surface: "SurfaceTreatment | None",
    *,
    textures: dict[str, AssetJSON],
) -> list[str]:
    """Expand ``surface`` into ``node`` (an entity's subtree), in place.

    Returns what it could not do, for the compiler to warn with (a glow on an
    entity that draws nothing). A no-op for ``None``, which is every entity of
    a scene whose pack sets no treatment. The outline and the shadow go on each part: the entity's
    direct children, and deeper parts too when the treatment is ``nested``.
    The glow is added after the parts are walked, so it never gets an outline
    of its own.

    >>> from an.styles import SurfaceTreatment
    >>> part = NodeJSON(name="torso", visual=VisualJSON(kind="rect", width=40, height=60))
    >>> ent = NodeJSON(name="bob", children=[part])
    >>> apply_surface(ent, SurfaceTreatment(outline={"width": 2}, shadow={}), textures={})
    []
    >>> [(u.grow, u.offsets) for u in part.visual.underlays]
    [(2.0, [(4.0, 4.0)]), (2.0, [(0.0, 0.0)])]
    """
    if surface is None:
        return []
    notes: list[str] = []
    outline, shadow = surface.outline or None, surface.shadow or None

    def treat(part: NodeJSON, *, nested: bool) -> None:
        visual = part.visual
        if visual is not None and visual.kind in UNDERLAY_KINDS:
            lined = outline is not None and (outline.nested or not nested)
            underlays: list[UnderlayJSON] = []
            # Back to front: the shadow first, so the outline draws over it.
            if shadow is not None and (shadow.nested or not nested):
                underlays.append(
                    UnderlayJSON(
                        color=shadow.color,
                        alpha=shadow.alpha,
                        offsets=[(float(shadow.dx), float(shadow.dy))],
                        # The OUTLINED silhouette's shadow: an ungrown copy
                        # offset by less than the outline width would sit
                        # entirely under the outline and never show.
                        grow=float(outline.width) if lined else 0.0,
                    )
                )
            if lined:
                if visual.kind == "svg_sprite":
                    # A ring of copies, not one grown copy: it follows the
                    # art's own silhouette (concave shapes and transparent
                    # margins included), where scaling a copy only grows its box.
                    underlays.append(
                        UnderlayJSON(
                            color=outline.color, offsets=ring_offsets(outline.width)
                        )
                    )
                else:
                    underlays.append(
                        UnderlayJSON(color=outline.color, grow=float(outline.width))
                    )
            if underlays:
                visual.underlays = underlays
        for child in part.children:
            treat(child, nested=True)

    for part in node.children:
        treat(part, nested=False)
    if surface.glow:
        glow = glow_node(surface.glow, node, textures=textures)
        if glow is not None:
            node.children.insert(0, glow)
        else:
            notes.append(f"{node.name!r} has a glow but draws nothing to size it on")
    return notes


def drawn_box(node: NodeJSON) -> tuple[float, float, float, float] | None:
    """``(x0, y0, x1, y1)`` of what ``node``'s parts draw, in its own frame.

    The entity's own visual and every descendant's: rest translations and each
    visual's box and anchor. Rest rotations and
    scales are not applied: the compiled rigs have none below the entity
    root. That is an assumption about the rigs this compiler builds, not
    about arbitrary documents.

    >>> head = NodeJSON(name="h", transform=TransformJSON(y=-50),
    ...                 visual=VisualJSON(kind="ellipse", width=40, height=40))
    >>> drawn_box(NodeJSON(name="e", children=[head]))
    (-20.0, -70.0, 20.0, -30.0)
    """
    xs: list[float] = []
    ys: list[float] = []

    def walk(n: NodeJSON, ox: float, oy: float) -> None:
        x, y = ox + n.transform.x, oy + n.transform.y
        v = n.visual
        if v is not None:
            if v.kind == "path" and v.path is not None:
                half = v.path.stroke_width / 2
                for px, py in v.path.points:
                    xs.extend((x + px - half, x + px + half))
                    ys.extend((y + py - half, y + py + half))
            else:
                centred = v.kind in ("ellipse", "eye", "mouth")
                ax = 0.5 if centred else v.anchor_x
                ay = 0.5 if centred else v.anchor_y
                xs.extend((x - v.width * ax, x + v.width * (1 - ax)))
                ys.extend((y - v.height * ay, y + v.height * (1 - ay)))
        for c in n.children:
            walk(c, x, y)

    # The entity's OWN visual too (a stroked path carries it there), at the
    # origin: the glow lives in the entity's frame, not its parent's.
    walk(node.model_copy(update={"transform": TransformJSON()}), 0.0, 0.0)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _fmt(x: float) -> str:
    return f"{x:.4f}".rstrip("0").rstrip(".")


def glow_svg(
    width: int, height: int, *, color: str, intensity: float, core: float
) -> str:
    """The glow's texture: an elliptical radial gradient filling its box.

    It holds ``intensity`` out to ``core`` (a fraction of the radius) and
    fades to nothing at the edge.

    >>> glow_svg(10, 10, color="#ffffff", intensity=0.5, core=0.4)[:52]
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" h'
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><defs><radialGradient id="g">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="{_fmt(intensity)}"/>'
        f'<stop offset="{_fmt(core)}" stop-color="{color}" '
        f'stop-opacity="{_fmt(intensity)}"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/>'
        f'</radialGradient></defs><rect width="{width}" height="{height}" '
        'fill="url(#g)"/></svg>'
    )


def _inline_texture(textures: dict[str, AssetJSON], kind: str, src: str) -> str:
    """Register an inline (`data:`) texture under a content-addressed alias."""
    digest = hashlib.sha256(src.encode("ascii")).hexdigest()[:_ALIAS_DIGEST_LEN]
    alias = f"surface.{kind}.{digest}"
    textures.setdefault(alias, AssetJSON(src=src))
    return alias


def glow_node(
    glow: "Glow", entity: NodeJSON, *, textures: dict[str, AssetJSON]
) -> NodeJSON | None:
    """The glow sprite for ``entity``, or ``None`` if it draws nothing."""
    box = drawn_box(entity)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    gw = math.ceil(bw + 2 * glow.radius)
    gh = math.ceil(bh + 2 * glow.radius)
    core = min(bw / gw, bh / gh)
    svg = glow_svg(gw, gh, color=glow.color, intensity=glow.intensity, core=core)
    src = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode(
        "ascii"
    )
    alias = _inline_texture(textures, "glow", src)
    return NodeJSON(
        name=GLOW_NODE,
        transform=TransformJSON(
            x=round((x0 + x1) / 2, _DIGITS) + 0.0, y=round((y0 + y1) / 2, _DIGITS) + 0.0
        ),
        visual=VisualJSON(
            kind="svg_sprite",
            asset_id=alias,
            fit="contain",
            width=float(gw),
            height=float(gh),
            blend="add",
        ),
    )


# -----------------------------------------------------------------------------
# Grain — per scene
# -----------------------------------------------------------------------------

_MASK64 = (1 << 64) - 1


def _splitmix64(state: int):
    """SplitMix64 (Steele, Lea & Flood 2014): a stated generator, not a
    library's, so the grain cannot change under a Python or numpy upgrade."""
    while True:
        state = (state + 0x9E3779B97F4A7C15) & _MASK64
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        yield z ^ (z >> 31)


def grain_indices(seed: int, tile: int) -> list[int]:
    """``tile × tile`` grey-level indices in ``[0, GRAIN_LEVELS)``, row-major.

    >>> grain_indices(0, 4)
    [14, 6, 0, 15, 1, 5, 2, 12, 3, 15, 6, 12, 8, 8, 11, 8]
    >>> grain_indices(0, 4) == grain_indices(0, 4) != grain_indices(1, 4)
    True
    """
    shift = 64 - (GRAIN_LEVELS - 1).bit_length()
    gen = _splitmix64(seed & _MASK64)
    return [next(gen) >> shift for _ in range(tile * tile)]


def grain_greys(amount: float) -> list[int]:
    """The palette: level ``n`` multiplies the frame by ``grey/255``, from
    white (level 0) down to ``1 − amount`` (the last level).

    >>> grain_greys(0.06)[:3], grain_greys(0.06)[-1]
    ([255, 254, 253], 240)
    """
    top = GRAIN_LEVELS - 1
    return [round(255 * (1 - amount * n / top)) for n in range(GRAIN_LEVELS)]


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data))
    )


def _stored_zlib(raw: bytes) -> bytes:
    """A zlib stream of STORED deflate blocks: the same bytes on every build."""
    out = bytearray(b"\x78\x01")
    limit = 0xFFFF
    for i in range(0, max(len(raw), 1), limit):
        block = raw[i : i + limit]
        final = 1 if i + limit >= len(raw) else 0
        out += (
            bytes([final]) + struct.pack("<HH", len(block), len(block) ^ 0xFFFF) + block
        )
    out += struct.pack(">I", zlib.adler32(raw))
    return bytes(out)


def grain_png(*, seed: int, amount: float, tile: int) -> bytes:
    """The grain tile as a 4-bit palette PNG: opaque and lossless.

    It is opaque on purpose. With no alpha channel there is no premultiply
    step on load that could differ between engines.
    """
    idx = grain_indices(seed, tile)
    rows = bytearray()
    for y in range(tile):
        rows.append(0)  # filter: none
        row = idx[y * tile : (y + 1) * tile]
        if len(row) % 2:
            row = row + [0]
        rows += bytes((row[i] << 4) | row[i + 1] for i in range(0, len(row), 2))
    ihdr = struct.pack(">IIBBBBB", tile, tile, _GRAIN_BIT_DEPTH, 3, 0, 0, 0)
    plte = b"".join(bytes((g, g, g)) for g in grain_greys(amount))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"PLTE", plte)
        + _png_chunk(b"IDAT", _stored_zlib(bytes(rows)))
        + _png_chunk(b"IEND", b"")
    )


def grain_node(
    grain: "Grain", *, width: int, height: int, textures: dict[str, AssetJSON]
) -> NodeJSON:
    """The grain layer: one tile texture, tiled over the frame in frame pixels.

    It goes on the OVERLAY, which is centred on the canvas and cannot be
    reached by the camera. Each tile sits at an integer frame position at
    scale 1, so at ``supersample`` 1 a texel is exactly one pixel. Tiling is
    done with nodes rather than a ``TilingSprite``, which the runtime does not
    wire (an#110's rule: wire it fully or not at all).
    """
    t = grain.tile
    src = "data:image/png;base64," + base64.b64encode(
        grain_png(seed=grain.seed, amount=grain.amount, tile=t)
    ).decode("ascii")
    alias = _inline_texture(textures, "grain", src)
    tiles = [
        NodeJSON(
            name=f"tile_{j}_{i}",
            transform=TransformJSON(x=-width / 2 + i * t, y=-height / 2 + j * t),
            visual=VisualJSON(
                kind="svg_sprite",
                asset_id=alias,
                fit="contain",
                width=float(t),
                height=float(t),
                anchor_x=0.0,
                anchor_y=0.0,
                blend="multiply",
            ),
        )
        for j in range(math.ceil(height / t))
        for i in range(math.ceil(width / t))
    ]
    return NodeJSON(name=GRAIN_NODE, children=tiles)


def _fades(channel) -> bool:
    """Whether an ``alpha`` channel ever shows a value strictly between 0 and
    1 — a FADE. A hide or a show (every key 0 or 1, stepped between) is not
    one: the copies share the part's container, so its alpha hides or shows
    them with the part, exactly (an#203 — a view's pose hiding the far arm
    was reported as a fade).

    >>> from an.adapters.cutout.serialize import ChannelJSON, KeyframeJSON as K
    >>> hide = ChannelJSON(target="a", property="alpha", keyframes=[
    ...     K(time=0, value=1.0, easing="step"), K(time=1, value=0.0, easing="step")])
    >>> fade = ChannelJSON(target="a", property="alpha", keyframes=[
    ...     K(time=0, value=1.0), K(time=1, value=0.0)])
    >>> _fades(hide), _fades(fade)
    (False, True)
    """
    keys = channel.keyframes
    if any(0.0 < float(k.value) < 1.0 for k in keys):
        return True
    return any(
        a.easing != "step" and float(a.value) != float(b.value)
        for a, b in zip(keys, keys[1:])
    )


def faded_treated_targets(scene: NodeJSON, animations) -> list[str]:
    """The ``alpha`` channel targets that FADE a part carrying underlays.

    A treated part's copies are drawn separately, so a fade shows them
    through the part instead of the background (see `an.styles.Outline`).
    A hide or a show is not a fade (:func:`_fades`), and an alpha on the glow
    node only fades the glow, which is fine.
    """
    treated: set[str] = set()

    def walk(n: NodeJSON, path: str, parents: tuple[str, ...]) -> None:
        here = f"{path}/{n.name}" if path else n.name
        if n.visual is not None and n.visual.underlays:
            treated.update(parents + (here,))
        for c in n.children:
            walk(c, here, parents + (here,))

    for child in scene.children:
        walk(child, "", ())
    hits = {
        ch.target
        for clip in animations.values()
        for ch in clip.channels
        if ch.property == "alpha" and ch.target in treated and _fades(ch)
    }
    return sorted(hits)
