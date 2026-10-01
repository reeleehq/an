"""Whether an art package is one the compiler can actually render.

The artist-facing contract, checked offline. Wave 4 (#78) exists because the
previous check had no teeth in two separate ways:

- **It checked file existence only.** A part that was present but drew nothing
  passed, and then rendered invisibly — the one failure mode with no diagnostic
  anywhere in the pipeline (``misc/docs/wave4_research.md`` §4).
- **It returned a bespoke report type**, so the orchestrator's typed-error
  routing did not apply to any character problem. Findings here are
  :class:`an.verify._base.Finding`, the same type every verifier emits, with
  ``ir_path`` pointing at the file or slot that needs the fix.

Everything here is offline and free: no render, no browser, no network. That is
the point — an illustrator should be able to run it before delivering, and a
contract they cannot check themselves is a contract that gets them paid for work
that cannot land.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator

from an.base import swap_set_name_problem
from an.ir.migrate import migrate
from an.characters.schema import (
    EYELID_CHANNEL,
    VISEME_CHANNEL,
    CHARACTER_DOCUMENT_KIND,
    MOUTH_SHAPES,
    REQUIRED_PARTS,
    CharacterDescriptor,
)
from an.characters.svg_utils import SVG_NS, extract_pivots
from an.raster import RASTER_SUFFIXES, has_alpha, image_size, is_raster
from an.verify._base import Finding, VerificationReport

#: Elements an art package may not contain.
#:
#: Not a security perimeter — the renderer loads these files into a headless
#: browser we control — but a portability one: each of these makes a part render
#: differently, or not at all, depending on the rasteriser, and a part that
#: depends on script execution is not a drawing.
PROHIBITED_ELEMENTS: dict[str, str] = {
    "script": "executable content; a part is a drawing, not a program",
    "foreignObject": "embeds non-SVG content that most rasterisers drop",
    "image": (
        "raster embed; ship the raster as its own part instead "
        "(parts/<name>.png, with alpha — an#211)"
    ),
}

#: The part file formats an art package may ship: SVG, or raster with the
#: suffixes `an.raster` reads (an#211). Order is the lookup order for a
#: required part, so an SVG wins when both exist.
PART_SUFFIXES: tuple[str, ...] = (".svg", *RASTER_SUFFIXES)

#: Elements that put ink on the canvas. A part containing none of these is
#: blank, whatever else it contains.
DRAWABLE_ELEMENTS: frozenset[str] = frozenset(
    {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "use"}
)

#: Severity for a problem that stops the part rendering correctly.
BLOCKING: str = "error"

#: Severity for a problem worth fixing that still renders.
ADVISORY: str = "warning"


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _iter_parts(char_dir: Path) -> Iterator[tuple[str, Path]]:
    """``(relative name, path)`` for every part an art package ships — SVG or
    raster (an#211)."""
    parts = char_dir / "parts"
    if not parts.is_dir():
        return
    for path in sorted(parts.rglob("*")):
        if path.is_file() and path.suffix.lower() in PART_SUFFIXES:
            yield path.relative_to(parts).as_posix(), path


def _part_file(parts_dir: Path, stem: str) -> Path | None:
    """The file a part named ``stem`` ships as, in any accepted format."""
    for suffix in PART_SUFFIXES:
        candidate = parts_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _check_raster_part(rel: str, path: Path, report: VerificationReport) -> None:
    """A raster part (an#211): readable, transparent around the art, not blank.

    The same three questions an SVG part answers, asked of pixels: can the
    loader read it (BLOCKING — an unreadable texture fails the load), does it
    draw anything (BLOCKING — a fully transparent part is the invisible-art
    failure `DRAWABLE_ELEMENTS` exists for), and is it a cut-out at all
    (ADVISORY — a part with no alpha draws its whole rectangle, background
    included, which is legitimate for a plate and almost never for a limb).
    """
    ir_path = f"parts/{rel}"
    try:
        image_size(path)
    except (OSError, ValueError) as e:
        report.add(
            BLOCKING,
            ir_path,
            f"{rel} is not a readable PNG/JPEG/WebP: {e}",
            "Re-export it as a PNG with an alpha channel.",
        )
        return
    alpha = has_alpha(path)
    if alpha is False:
        report.add(
            ADVISORY,
            ir_path,
            f"{rel} has no alpha channel, so it draws its whole rectangle — "
            "background and all — over whatever is behind it",
            "Cut it out: export a PNG with a transparent background.",
        )
    if alpha and _fully_transparent(path):
        report.add(
            BLOCKING,
            ir_path,
            f"{rel} is fully transparent: it draws nothing",
            "Put the art in it, or delete the part and the slot that names it. "
            "A blank part renders invisibly with no error anywhere.",
        )


def _fully_transparent(path: Path) -> bool:
    """Whether every pixel's alpha is 0. ``False`` when it cannot be decoded
    here (Pillow absent) — an unrun check is not a finding."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover — Pillow arrives with tituli
        return False
    try:
        with Image.open(path) as im:
            return im.convert("RGBA").getchannel("A").getbbox() is None
    except (OSError, ValueError):
        return False


def _check_part(rel: str, path: Path, report: VerificationReport) -> None:
    """Open one part and report what would go wrong at render time."""
    ir_path = f"parts/{rel}"
    if is_raster(path):
        _check_raster_part(rel, path, report)
        return
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        report.add(
            BLOCKING,
            ir_path,
            f"{rel} is not parseable XML: {e}",
            "Re-export it. A malformed part makes the asset loader never settle, "
            "so the render hangs rather than failing (an#79).",
        )
        return

    descendants = [_localname(el.tag) for el in root.iter()]

    for name, why in PROHIBITED_ELEMENTS.items():
        if name in descendants:
            report.add(
                BLOCKING,
                ir_path,
                f"{rel} contains <{name}>: {why}",
                f"Remove the <{name}>.",
            )

    if not DRAWABLE_ELEMENTS.intersection(descendants):
        report.add(
            BLOCKING,
            ir_path,
            f"{rel} contains no drawable element "
            f"({', '.join(sorted(DRAWABLE_ELEMENTS))})",
            "Draw something, or delete the part and the slot that names it. A "
            "geometry-less part renders invisibly with no error anywhere — the "
            "failure this check exists for.",
        )

    view_box = root.get("viewBox")
    if not view_box:
        report.add(
            ADVISORY,
            ir_path,
            f"{rel} declares no viewBox, so its size depends on the rasteriser",
            "Add a viewBox matching the art's extent.",
        )
        return
    try:
        numbers = [float(v) for v in view_box.split()]
    except ValueError:
        numbers = []
    if len(numbers) != 4:
        report.add(
            BLOCKING, ir_path, f"{rel} has a malformed viewBox {view_box!r}", None
        )
        return
    if numbers[2] <= 0 or numbers[3] <= 0:
        report.add(
            BLOCKING,
            ir_path,
            f"{rel} has a zero-or-negative viewBox extent {view_box!r}",
            "A zero-dimension part makes the asset loader never settle (an#79).",
        )
        return

    width, height = root.get("width"), root.get("height")
    if width and height:
        try:
            declared = (float(width.rstrip("px")), float(height.rstrip("px")))
        except ValueError:
            return
        vb_aspect = numbers[2] / numbers[3]
        declared_aspect = declared[0] / declared[1] if declared[1] else 0
        if declared_aspect and abs(vb_aspect - declared_aspect) > 0.01 * vb_aspect:
            report.add(
                ADVISORY,
                ir_path,
                f"{rel} rasterises at {declared[0]:g}x{declared[1]:g} but its viewBox "
                f"is {numbers[2]:g}x{numbers[3]:g}, so the art is letterboxed inside "
                f"its own texture",
                "Make width/height match the viewBox extent. This is the defect "
                "an#75 fixed in `extract_part`; a hand-authored part can reintroduce it.",
            )


def validate_character(
    char_dir: str | Path, *, name: str | None = None
) -> VerificationReport:
    """Check an art package against the contract, offline.

    Reports a :class:`~an.verify._base.Finding` per problem: a missing or
    unparseable descriptor, absent required parts or mouth shapes, a part that
    draws nothing, a prohibited construct, a letterboxed part, a joint name
    colliding with a part id, and an unpopulated ``AssetSource``.

    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as d:
    ...     report = validate_character(d, name="nobody")
    >>> report.passed
    False
    >>> any("character.json" in f.description for f in report.findings)
    True
    """
    directory = Path(char_dir)
    who = name or directory.name
    report = VerificationReport()

    if not directory.is_dir():
        report.add(BLOCKING, who, f"{directory} does not exist", None)
        return report

    descriptor: CharacterDescriptor | None = None
    desc_path = directory / "character.json"
    if not desc_path.exists():
        report.add(
            BLOCKING,
            "character.json",
            f"{who} has no character.json",
            "Run `an character new`, or write one; without it nothing knows the rig.",
        )
    else:
        try:
            # Validate the MIGRATED document — the one the compiler renders.
            # Both committed corpus rigs are 0.1.0 on disk; read raw, the
            # 0.3.0 model default `eyelid` set would be checked against
            # un-renamed `eye_l_open` attachments and every one of them would
            # fail its own validator (an#87 review).
            descriptor = CharacterDescriptor.model_validate(
                migrate(
                    json.loads(desc_path.read_text(encoding="utf-8")),
                    kind=CHARACTER_DOCUMENT_KIND.name,
                )
            )
        except (ValueError, json.JSONDecodeError) as e:
            report.add(
                BLOCKING, "character.json", f"{who}'s descriptor is invalid: {e}", None
            )

    parts_dir = directory / "parts"
    for part in REQUIRED_PARTS:
        if _part_file(parts_dir, part) is None:
            report.add(
                BLOCKING,
                f"parts/{part}.svg",
                f"{who} is missing required part {part!r}",
                "Draw it, or drop the slot that names it from the descriptor.",
            )
    for shape in MOUTH_SHAPES:
        if _part_file(parts_dir / "mouth", f"mouth_{shape}") is None:
            report.add(
                BLOCKING,
                f"parts/mouth/mouth_{shape}.svg",
                f"{who} is missing mouth shape {shape!r}",
                "Run `an character mouths` to generate the default set.",
            )

    for rel, path in _iter_parts(parts_dir.parent):
        _check_part(rel, path, report)

    _check_asset_sets(directory, descriptor, report, who=who)
    _check_raster_colour_roles(descriptor, report, who=who)
    _check_declared_boxes(directory, descriptor, report, who=who)
    _check_swap_poses(descriptor, report, who=who)
    _check_view_variants(descriptor, report, who=who)

    _check_mouth_variants(descriptor, report, who=who)
    _check_gaze_stack(descriptor, report, who=who)
    _check_face_overlay_declaration(descriptor, report, who=who)
    _check_declared_speech(descriptor, report, who=who)
    _check_joint_names(directory, descriptor, report)

    if descriptor is not None and descriptor.source is None:
        report.add(
            ADVISORY,
            "character.json",
            f"{who} declares no AssetSource",
            "Record where the art came from. `None` means 'we made this', which is "
            "a claim — and a licence defect is the only failure that reaches "
            "backwards through finished work.",
        )
    return report


def _check_asset_sets(
    directory: Path,
    descriptor: CharacterDescriptor | None,
    report: VerificationReport,
    *,
    who: str,
) -> None:
    """Every asset-set key must be swappable, and swap without moving (an#87).

    Three checks per declared channel:

    - **Every key's attachment name resolves in at least one slot of the
      active skin** — BLOCKING, because the compiler's projection silently
      omits an unresolvable key, and a channel then freezes on it (the old
      silent-freeze bug, now a loud runtime error for hand-written scenes and
      a dropped-with-warning for compiled ones — either way the art package
      is what is wrong).
    - **A key whose attachment resolves but whose FILE is missing** —
      ADVISORY, the inventory-gap class (`a rig without a blink still
      renders`); it escalates only when a shot actually uses the key.

    Differing geometry between a set's keys is NOT a finding any more: each
    key carries its own box, anchor and offset through to the runtime
    (an#211). It used to be an advisory about DECLARED geometry only, which
    missed the case that actually broke — keys drawn on canvases of different
    sizes, fitted into the default key's box (a thin closed mouth squashed
    every open mouth to a fraction of a pixel).
    """
    if descriptor is None:
        return
    skin = descriptor.skins.get("default") or next(
        iter(descriptor.skins.values()), None
    )
    if skin is None:
        return
    for channel, key_map in descriptor.asset_sets.items():
        problem = swap_set_name_problem(channel)
        if problem is not None:
            report.add(
                BLOCKING,
                f"character.json#asset_sets.{channel}",
                f"{who} declares an asset set that cannot be a swap-set name: "
                f"{problem}",
                "Rename the set; the transform vocabulary and '/' / '::' are reserved.",
            )
            continue
        for key, attachment_name in key_map.items():
            holding_slots = [
                slot_name
                for slot_name, attachments in skin.slots.items()
                if attachment_name in attachments
            ]
            if not holding_slots:
                report.add(
                    BLOCKING,
                    f"character.json#asset_sets.{channel}.{key}",
                    f"{who}'s {channel!r} set maps {key!r} to attachment "
                    f"{attachment_name!r}, which no slot of the skin carries — "
                    "the key can never be swapped to",
                    "Name an attachment that exists in a slot, or drop the key.",
                )
                continue
            for slot_name in holding_slots:
                att = skin.slots[slot_name][attachment_name]
                if not (directory / att.path).exists():
                    # BLOCKING when this is the slot's default (or only)
                    # art — the slot then draws NOTHING and the compiler
                    # records a fallback; ADVISORY for a spare key, the
                    # inventory-gap class ("a rig without a blink still
                    # renders"), which escalates only when a shot uses it.
                    default_name = next(
                        (s.attachment for s in descriptor.slots if s.name == slot_name),
                        None,
                    )
                    only_art = len(skin.slots[slot_name]) == 1
                    severity = (
                        BLOCKING
                        if only_art or attachment_name == default_name
                        else ADVISORY
                    )
                    report.add(
                        severity,
                        f"{att.path}",
                        f"{who}'s {channel!r}.{key!r} resolves to {att.path}, "
                        "which is not on disk; "
                        + (
                            "it is the slot's default art, so the slot draws nothing"
                            if severity == BLOCKING
                            else "a shot that uses the key will drop it (fatal "
                            "under strict_assets)"
                        ),
                        "Draw the file, or drop the key from the set.",
                    )


def _check_raster_colour_roles(
    descriptor: CharacterDescriptor | None, report: VerificationReport, *, who: str
) -> None:
    """A colour role on a raster part does nothing (an#211) — ADVISORY.

    A StylePack recolours SVG art by rewriting the literals `colour_roles`
    tags; a raster's colours are pixels, so the compiler skips the entry and
    the part renders as drawn.
    """
    if descriptor is None:
        return
    for rel_path in sorted(descriptor.colour_roles):
        if is_raster(rel_path):
            report.add(
                ADVISORY,
                f"character.json#colour_roles.{rel_path}",
                f"{who} tags colour roles on {rel_path}, a raster part — a style "
                "pack cannot recolour pixels, so the roles do nothing",
                "Drop the entry, or ship that part as SVG if it must follow a pack.",
            )


#: How far a declared box's aspect may differ from its art's before the
#: containment is worth saying (a rounding of a pixel or two is not).
DECLARED_ASPECT_TOLERANCE: float = 0.01


def _check_declared_boxes(
    directory: Path,
    descriptor: CharacterDescriptor | None,
    report: VerificationReport,
    *,
    who: str,
) -> None:
    """An attachment that declares BOTH ``width`` and ``height`` in an aspect
    its art does not have is drawn contained, not stretched (an#220) —
    ADVISORY, naming the size it actually draws at, so the author sees the
    box they asked for is not the one on screen.
    """
    if descriptor is None:
        return
    from an.characters.schema import attachment_box
    from an.raster import art_size

    seen: set[str] = set()
    for skin in descriptor.skins.values():
        for slot_name, attachments in skin.slots.items():
            for name, att in attachments.items():
                if not (att.width and att.height) or att.path in seen:
                    continue
                seen.add(att.path)
                try:
                    art = art_size(directory / att.path)
                except Exception:  # noqa: BLE001 — unreadable art is reported elsewhere
                    continue
                if not (art[0] > 0 and art[1] > 0):
                    continue
                w, h = float(att.width), float(att.height)
                if abs((w / h) / (art[0] / art[1]) - 1.0) <= DECLARED_ASPECT_TOLERANCE:
                    continue
                cw, ch = attachment_box(w, h, art)
                report.add(
                    ADVISORY,
                    f"character.json#skins.{skin.name}.slots.{slot_name}.{name}",
                    f"{who}'s {slot_name}.{name} declares a {w:g}x{h:g} box, but "
                    f"{att.path} is {art[0]:g}x{art[1]:g} — a different aspect, so it "
                    f"draws contained at {cw:g}x{ch:g} (a part is never stretched)",
                    "Declare only `width` (or only `height`) and let the art's aspect "
                    "give the other.",
                )


def _check_view_variants(
    descriptor: CharacterDescriptor | None, report: VerificationReport, *, who: str
) -> None:
    """A per-view face set (``eyelid@side``, ``viseme@side``, an#220) must vary a
    set the rig has, and should carry that set's keys — ADVISORY, because a
    key the variant lacks falls back to the neutral set's art, which is the
    front drawing in a profile.
    """
    if descriptor is None:
        return
    from an.characters.schema import VIEW_CHANNEL, VIEWS, view_variant_sets

    known_views = set(VIEWS) | set(descriptor.asset_sets.get(VIEW_CHANNEL) or {})
    if descriptor.rest_view is not None and descriptor.rest_view not in known_views:
        report.add(
            ADVISORY,
            "character.json#rest_view",
            f"{who} declares rest_view {descriptor.rest_view!r}, which is not a view "
            f"(known: {sorted(known_views)}) — nothing that reads the view matches it",
            "Name the view the default art is drawn in, e.g. `side`.",
        )
    for base, per_view in view_variant_sets(descriptor).items():
        base_keys = set(descriptor.asset_sets.get(base) or {})
        for view, set_name in per_view.items():
            missing = sorted(base_keys - set(descriptor.asset_sets[set_name]))
            if missing:
                report.add(
                    ADVISORY,
                    f"character.json#asset_sets.{set_name}",
                    f"{who}'s {set_name!r} lacks the keys {missing} its {base!r} set "
                    f"has; in the {view!r} view those keys show the {base!r} art",
                    f"Draw the missing {view} shapes, or accept the fallback.",
                )


def _check_swap_poses(
    descriptor: CharacterDescriptor | None,
    report: VerificationReport,
    *,
    who: str,
) -> None:
    """``swap_poses`` must pose declared keys of declared sets, on slots the rig
    has (an#197) — BLOCKING, because the compiler skips a pose it cannot place
    and the turn then shows a face the view was meant to hide.
    """
    if descriptor is None:
        return
    slots = {s.name for s in descriptor.slots}
    for set_name, per_key in descriptor.swap_poses.items():
        where = f"character.json#swap_poses.{set_name}"
        keys = descriptor.asset_sets.get(set_name)
        if keys is None:
            report.add(
                BLOCKING,
                where,
                f"{who} poses the {set_name!r} set, which it does not declare "
                f"(asset_sets: {sorted(descriptor.asset_sets)})",
                "Declare the set in asset_sets, or drop its poses.",
            )
            continue
        for key, poses in per_key.items():
            if key not in keys:
                report.add(
                    BLOCKING,
                    f"{where}.{key}",
                    f"{who} poses {key!r}, which is not a key of its {set_name!r} "
                    f"set (keys: {sorted(keys)}) — no swap can ever show it",
                    "Pose a declared key, or declare the key.",
                )
            unknown = sorted(set(poses) - slots)
            if unknown:
                report.add(
                    BLOCKING,
                    f"{where}.{key}",
                    f"{who}'s {set_name!r}.{key!r} pose names slot(s) {unknown} the "
                    f"rig does not have (slots: {sorted(slots)})",
                    "Name the slots as the descriptor's `slots` do.",
                )


def _check_gaze_stack(
    descriptor: CharacterDescriptor | None, report: VerificationReport, *, who: str
) -> None:
    """A rig without pupil slots takes `gaze_x`/`gaze_y` as a no-op (an#99) —
    an `info` Finding, not a defect: the expand step is `an character add-gaze`."""
    if descriptor is None or not descriptor.face_overlay:
        return
    slots = {s.name for s in descriptor.slots}
    pupils = {"left_pupil", "right_pupil"} & slots
    if pupils and pupils != {"left_pupil", "right_pupil"}:
        report.add(
            BLOCKING,
            "character.json#slots",
            f"{who} has one pupil slot ({sorted(pupils)}) — the gaze axes yoke both eyes",
            f"Run `an character add-gaze {who}` to complete the stack.",
        )
        return
    if not pupils:
        report.add(
            "info",
            "character.json#slots",
            f"{who} has no pupil slot, so gaze (`gaze_x`/`gaze_y`, ambient saccades) "
            "moves nothing on it",
            f"Run `an character add-gaze {who}` to add the eye stack.",
        )
        return
    # Once pupils exist, `closed` art is MANDATORY: the blink squash scales the
    # lid node only, so a rig without closed art would squash the outline while
    # the white and the pupil stayed put (research §9).
    skin = descriptor.skins.get("default")
    closed = descriptor.asset_sets.get(EYELID_CHANNEL, {}).get("CLOSED")
    for eye_slot in ("left_eye", "right_eye"):
        attachments = (skin.slots.get(eye_slot) if skin else None) or {}
        if closed not in attachments:
            report.add(
                BLOCKING,
                f"character.json#skins.default.slots.{eye_slot}",
                f"{who} has pupil slots but {eye_slot!r} carries no closed-lid attachment "
                f"({closed!r}); a blink would squash the lid outline over a pupil that stays put",
                f"Run `an character add-gaze {who}` (it draws a filled closed lid), or add the art.",
            )


def _check_mouth_variants(
    descriptor: CharacterDescriptor | None, report: VerificationReport, *, who: str
) -> None:
    """The `viseme@<form>` variant sets (an#98), three rules:

    - a variant must name a known expression preset's mouth form — BLOCKING,
      because nothing can ever select a form no preset prefers;
    - a variant lacking keys the neutral set has — ADVISORY: a line using
      those keys falls back to the neutral set (with a warning) rather than
      showing the variant;
    - an overlay face that declares a variant but no neutral ``viseme`` set —
      BLOCKING: the resolver's fallback has nowhere to land and a speaking
      line raises.
    """
    if descriptor is None:
        return
    from an.expression.binding import declared_mouth_variants
    from an.expression.presets import PRESETS

    forms_known = {p.mouth_form for p in PRESETS.values() if p.mouth_form}
    neutral = descriptor.asset_sets.get(VISEME_CHANNEL)
    variants = declared_mouth_variants(descriptor)
    for form, set_name in variants.items():
        if form not in forms_known:
            report.add(
                BLOCKING,
                f"character.json#asset_sets.{set_name}",
                f"{who} declares {set_name!r}, but no expression preset prefers a "
                f"{form!r} mouth form (forms: {sorted(forms_known)}) — nothing can select it",
                "Name a preset's form, or drop the set.",
            )
        if neutral is not None:
            missing = sorted(set(neutral) - set(descriptor.asset_sets[set_name]))
            if missing:
                report.add(
                    ADVISORY,
                    f"character.json#asset_sets.{set_name}",
                    f"{who}'s {set_name!r} lacks the keys {missing} the neutral set "
                    "has; a line using them shows the neutral mouth instead (with a warning)",
                    "Draw the missing shapes for the variant, or accept the fallback.",
                )
    if variants and neutral is None and descriptor.face_overlay:
        report.add(
            BLOCKING,
            f"character.json#asset_sets.{VISEME_CHANNEL}",
            f"{who} declares mouth variants {sorted(variants.values())} but no neutral "
            f"{VISEME_CHANNEL!r} set — a line whose expression has no variant has no "
            "mouth to fall back on and raises",
            f"Declare the {VISEME_CHANNEL!r} set.",
        )


#: Provenance values that historically MEANT a baked face. The compiler no
#: longer reads them (the declared `face_overlay` field does the job, an#87);
#: this check is what keeps a hand-authored current-schema descriptor honest.
_BAKED_FACE_PROVENANCES: tuple[str, ...] = ("dicebear", "external_avatar")


def _check_declared_speech(
    descriptor: CharacterDescriptor | None, report: VerificationReport, *, who: str
) -> None:
    """A declared ``speech`` must name a speech method at a current version
    (an#248): it is resolved on the capability registry, so a typo or a stale
    pin would otherwise only surface at compile."""
    if descriptor is None or descriptor.speech is None:
        return
    from an.characters.methods import speech_problems
    from an.genres import load

    load()
    for problem in speech_problems(descriptor.speech):
        report.add(
            BLOCKING,
            "character.json#speech",
            f"{who}: {problem}",
            "Declare a speech method (`pulse`, `mouth_chart`, or "
            "`{method: pulse, args: {strength: 0}}` for a mime), or remove `speech`.",
        )


def _check_face_overlay_declaration(
    descriptor: CharacterDescriptor | None, report: VerificationReport, *, who: str
) -> None:
    """A baked-face provenance with `face_overlay=True` is almost certainly a
    mistake — the overlay eyes/brows/mouth will draw over the baked face.

    Before 0.3.0 the provenance string WAS the switch; a descriptor written
    to that convention at the current schema version declares the opposite
    of what its author meant, and nothing infers it any more (a declared
    fact is only worth having if nothing second-guesses it). Advisory, since
    a hand-drawn "external" avatar with real overlay parts is legitimate.
    """
    if descriptor is None or not descriptor.face_overlay:
        return
    provenance = (descriptor.metadata or {}).get("art_provenance")
    if provenance in _BAKED_FACE_PROVENANCES:
        report.add(
            ADVISORY,
            "character.json#face_overlay",
            f"{who} declares face_overlay=true but its art_provenance is "
            f"{provenance!r}, which usually means the face is baked into the "
            "head art — the overlay eyes/brows/mouth will draw over it",
            "Set face_overlay: false if the face is baked in (the compiler "
            "reads only that field now), or leave it if the avatar really "
            "has separate face parts.",
        )


def _check_joint_names(
    directory: Path,
    descriptor: CharacterDescriptor | None,
    report: VerificationReport,
) -> None:
    """A pivot id that is also a part id is ambiguous, structurally.

    `_find_by_id` prefers the `<g>` over a same-id `<circle>` precisely because
    this collision happens. That is a workaround for a missing namespace, and
    this is the check that makes the namespace real: if a drawing calls a joint
    `head` and also calls a part `head`, extraction picks one by a rule nobody
    reading the drawing can see.
    """
    canonical = next(directory.glob("*.svg"), None)
    if canonical is None:
        return
    try:
        pivots = set(extract_pivots(canonical))
    except (OSError, ET.ParseError, ValueError):
        return
    part_ids = {Path(rel).stem for rel, _ in _iter_parts(directory)}
    for clash in sorted(pivots & part_ids):
        report.add(
            ADVISORY,
            f"{canonical.name}#{clash}",
            f"{clash!r} names both a joint and a part",
            "Rename the joint. Extraction resolves the collision by preferring "
            "the group, which is a rule the drawing does not show.",
        )


def format_report(report: VerificationReport, *, name: str) -> str:
    """A short human-readable rendering, for the CLI."""
    verdict = "OK" if report.passed else "FAILED"
    lines = [f"character {name!r}: {verdict} ({len(report.findings)} finding(s))"]
    for finding in report.findings:
        lines.append(f"  [{finding.severity}] {finding.ir_path}: {finding.description}")
        if finding.suggested_fix:
            lines.append(f"      -> {finding.suggested_fix}")
    return "\n".join(lines)


def render_contract() -> str:
    """The artist-facing spec, generated from the schema and the checks above.

    Every line here is read out of a live object: the required parts and mouth
    shapes from :mod:`an.characters.schema`, the slot and attachment layout from
    a freshly-built descriptor, the prohibitions from
    :data:`PROHIBITED_ELEMENTS`, and the drawable set from
    :data:`DRAWABLE_ELEMENTS`. Nothing is retyped, so the document and the
    validator cannot disagree.
    """
    descriptor = CharacterDescriptor(name="example")
    skin = descriptor.skins["default"]
    view_box = descriptor.view_box

    lines = [
        f"# Art package contract (character schema {descriptor.schema_version})",
        "",
        "Everything below is checked offline by `an character validate`.",
        "",
        "## Layout",
        "",
        "    <name>/",
        "      character.json        the descriptor: bones, slots, skins, asset_sets",
        "      <name>.svg            the canonical drawing, with a <g id='skeleton'>",
        "      parts/                one SVG (or PNG) per attachment",
        "        mouth/              the viseme set",
        "",
        "## Coordinate space",
        "",
        f"All positions are in view_box units; the default is {list(view_box)}.",
        "A bone's position is relative to its parent; an attachment's is relative",
        "to its bone. The whole rig is scaled by one uniform factor at compile",
        "time, so **aspect ratio is intrinsic to the art** — a part is placed and",
        "uniformly scaled, never stretched to fit a box.",
        "",
        "## Joints",
        "",
        'Draw a `<g id="skeleton">` of named `<circle>` elements; each bone names',
        "the joint it stands for, and those coordinates become the rig:",
        "",
    ]
    for bone in descriptor.bones:
        joint = bone.pivot or "(no joint; keeps its default placement)"
        lines.append(f"    {bone.name:<10} <- {joint}")
    lines += [
        "",
        "A joint id must not also be a part id.",
        "",
        "## Required parts",
        "",
        "    " + ", ".join(REQUIRED_PARTS),
        "",
        f"    mouth/: {', '.join('mouth_' + s for s in MOUTH_SHAPES)}",
        "",
        "## Slots and their attachments",
        "",
    ]
    for slot in sorted(descriptor.slots, key=lambda s: (s.draw_order, s.name)):
        available = sorted(skin.slots.get(slot.name, {}))
        lines.append(
            f"    {slot.name:<11} bone={slot.bone:<8} draw_order={slot.draw_order}  "
            f"{', '.join(available)}"
        )
    lines += [
        "",
        "A slot's name is its scene-graph node name, which is what `scene.md`",
        "targets. Attachment names are a separate namespace and follow the files.",
        "",
        "## Every part SVG",
        "",
        "  - declares a viewBox, and `width`/`height` matching its extent",
        "    (otherwise the art is letterboxed inside its own texture)",
        "  - contains at least one of: " + ", ".join(sorted(DRAWABLE_ELEMENTS)),
        "  - contains none of:",
    ]
    for name, why in PROHIBITED_ELEMENTS.items():
        lines.append(f"      <{name}> — {why}")
    lines += [
        "",
        "## Raster parts",
        "",
        "A part may instead be raster: " + ", ".join(RASTER_SUFFIXES) + " (an#211) —",
        "art carved from a scan or a frame keeps its shading. Point the",
        "attachment's `path` at it (`parts/head.png`); a required part may ship",
        "in any of these formats. Every raster part",
        "",
        "  - has an alpha channel (a PNG with transparency), or it draws its",
        "    whole rectangle, background and all",
        "  - draws something (not fully transparent)",
        "  - is drawn at its pixel size x the rig's one uniform scale, like an",
        "    SVG part at its width/height — one pixel is one view_box unit —",
        "    unless the attachment declares `width` and/or `height` (view_box",
        "    units, an#220): a declared size wins, so art carved at any",
        "    resolution is sized without resampling. One of the two is enough —",
        "    the other follows the art's aspect; with both, the art is contained",
        "    in the box, never stretched",
        "  - is NOT recoloured by a style pack (its colours are pixels); outline",
        "    and shadow treatments still apply",
        "",
        "Swap keys (visemes, eyelids, views) may be drawn on canvases of",
        "different sizes: each key is placed with its own box, anchor and offset.",
    ]
    from an.characters.schema import DFLT_VIEW, VIEW_CHANNEL, VIEWS

    lines += [
        "",
        "## Optional: views (a turnaround)",
        "",
        f"To let a scene turn the character, declare a `{VIEW_CHANNEL}` asset set whose",
        f"keys are views ({', '.join(VIEWS)}; `side` faces the viewer's RIGHT —",
        "a negative scale_x mirrors it) and whose values are attachment names",
        "carried by every slot whose art changes with the view (the head and",
        f"torso, typically; `{DFLT_VIEW}` names the slot's default art). Draw each",
        "view on the same canvas as the default part where you can (a key on another",
        "canvas is placed by its own box, anchor and offset — an#211).",
        "Then say what else each view does in `swap_poses` —",
        f'`{{"{VIEW_CHANNEL}": {{"back": {{"mouth": {{"alpha": 0}}}}}}}}`:',
        "x/y offsets (view_box units), scale_x/scale_y/alpha factors, per slot.",
        "The back view hides the face this way; a profile hides the far eye.",
        "`an character new --offline` draws all of this for its own characters.",
        "",
        "A face drawn differently in a view gets its OWN set rather than being",
        "hidden (an#220): `eyelid@side` ({OPEN, CLOSED} -> the profile's eye",
        "attachments, on the eye slots) and `viseme@side` (the profile's mouth",
        "shapes, on the mouth slot) are used whenever that view is in force —",
        "blinks, expressions and lip-sync keep running in profile. Art drawn",
        "only in profile (no front at all) declares `rest_view: side` instead.",
        "A robe whose leg slots are the two halves of its hem declares",
        "`gait: hem`, so a walk tilts the halves in turn and sways the body.",
    ]
    lines += [
        "",
        "## Provenance",
        "",
        "Populate `source` unless the art is your own. A licence defect is the",
        "only failure that reaches backwards through finished work. A part",
        "whose art came from elsewhere than the rest (another clip, a CC0",
        "prop) carries its own `source` on its attachment; `an credits` lists",
        "each (an#220).",
    ]
    return "\n".join(lines)
