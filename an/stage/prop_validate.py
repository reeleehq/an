"""Check a prop's asset folder offline, and say what a prop must be (an#340).

``an props validate <dir>`` and ``an props contract``: the prop's twin of
``an character validate`` / ``an character contract``, in the core because a
prop is the stage's own rig (``an.stage.props.PropDescriptor``), not a genre's.
Before it, a carved prop's layout rules lived in its ``prop.json`` metadata and
nothing read them.

The rig rules are the stage's (:mod:`an.stage.rig`), so this validator, ``an
validate`` and the rig builder say the same thing: a structural problem
(:func:`~an.stage.rig.rig_problems`) blocks; where the stage cannot draw a
nested chain (:func:`~an.stage.rig.chain_draw_order_problems`), the origin and
the rest pose are advisories here, because they are the stage's limits or a
likely slip, not a malformed rig.

>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     report = validate_prop(d, name="nothing")
>>> report.passed, report.findings[0].description
(False, "nothing has no prop.json, or it is not a PropDescriptor (kind 'PropDescriptor')")
"""

from __future__ import annotations

import json
from pathlib import Path

from an.ir.migrate import migrate
from an.stage.props import PROP_DOCUMENT_KIND, PropDescriptor
from an.stage.rig import (
    BONES_NESTING,
    NESTINGS,
    chain_draw_order_problems,
    chain_pose_problems,
    drawn_attachment,
    rig_origin_problems,
    rig_problems,
    rig_rest_problems,
)
from an.stores import asset_ref_problems
from an.verify._base import VerificationReport

#: The descriptor file a prop folder holds (the props store's sidecar name).
PROP_META_NAME: str = "prop.json"

#: Finding severities, the ones ``an character validate`` uses.
BLOCKING: str = "error"
ADVISORY: str = "warning"


def _art_file_problems(file: Path) -> list[str]:
    """The ``file_problems`` hook of :func:`asset_ref_problems`: an art file the
    folder lacks, else what ``an validate`` says of an SVG that is not
    self-contained (one rule, both commands)."""
    from an.ir.validate import _svg_self_containment_problems

    return _svg_self_containment_problems(file) if file.is_file() else ["is not in the folder"]


def validate_prop(
    prop_dir: str | Path, *, name: str | None = None
) -> VerificationReport:
    """Check a prop folder (``prop.json`` + ``parts/``) against the rig contract, offline.

    Blocking: no or an unreadable descriptor, a structural rig problem (an
    unknown bone, a bone cycle), an attachment of any skin whose art is not in the
    folder (or is an SVG that is not self-contained), a prop that draws nothing. Advisory: a chain the stage cannot draw in its
    declared order (the compiler refuses it), the origin, the rest pose, an
    unpopulated ``AssetSource``.
    """
    directory = Path(prop_dir)
    who = name or directory.name
    report = VerificationReport()
    meta = directory / PROP_META_NAME
    try:
        raw = json.loads(meta.read_text(encoding="utf-8"))
        if raw.get("kind") != PROP_DOCUMENT_KIND.name:
            raise ValueError("not a PropDescriptor")
        document = migrate(raw, kind=PROP_DOCUMENT_KIND.name)
        desc = PropDescriptor.model_validate(document)
    except (OSError, ValueError) as e:
        missing = isinstance(e, OSError) or str(e) == "not a PropDescriptor"
        report.add(
            BLOCKING,
            PROP_META_NAME,
            f"{who} has no {PROP_META_NAME}, or it is not a PropDescriptor "
            f"(kind {PROP_DOCUMENT_KIND.name!r})"
            if missing
            else f"{who}'s descriptor is invalid: {e}",
            "Write one with `an.stage.props.PropDescriptor(...).model_dump_json()`; "
            "`an props contract` says what it holds.",
        )
        return report

    for problem in rig_problems(desc):
        report.add(BLOCKING, f"{PROP_META_NAME}#rig", f"{who}: {problem}")
    for problem in chain_pose_problems(desc):
        report.add(
            ADVISORY,
            f"{PROP_META_NAME}#rig",
            f"{who}: {problem} (compiling a shot refuses it)",
        )
    for problem in chain_draw_order_problems(desc):
        # Painted by the stage from a global part order (an#430); an engine
        # without `engine.paint_order:global` refuses it at compile.
        report.add(
            ADVISORY,
            f"{PROP_META_NAME}#rig",
            f"{who}: {problem} -- the stage paints it from a global part order "
            "(`engine.paint_order:global`); an engine without one refuses it",
        )
    for problem in rig_origin_problems(desc) + rig_rest_problems(desc):
        report.add(ADVISORY, f"{PROP_META_NAME}#rig", f"{who}: {problem}")

    skin = desc.skins.get("default") or next(iter(desc.skins.values()), None)
    # The one asset-reference rule (an#483, an#552), over EVERY skin's art (not
    # only the default one: a skin is a swap the scene may ask for); only the
    # skins, since nothing else in prop.json names a file the prop reads.
    for _label, message in asset_ref_problems(
        {"skins": document.get("skins")}, directory, file_problems=_art_file_problems
    ):
        report.add(BLOCKING, f"{PROP_META_NAME}#skins", f"{who}: {message}")
    drawn_any = False
    for slot in desc.slots:
        if skin is not None and drawn_attachment(desc, skin, slot) is not None:
            drawn_any = True
    if not drawn_any:
        report.add(
            BLOCKING,
            f"{PROP_META_NAME}#skins",
            f"{who} draws nothing: no slot resolves to an attachment in its skins",
            'Add a skin, e.g. {"default": {"slots": {"body": {"body": {"path": "parts/body.png"}}}}}',
        )
    if desc.source is None:
        report.add(
            ADVISORY,
            f"{PROP_META_NAME}#source",
            f"{who} declares no AssetSource",
            "Say where the art came from and under which licence (`source`); "
            "unset means we made it.",
        )
    return report


def render_prop_contract() -> str:
    """What a prop folder must hold, read off the schema and the rig rules (never retyped).

    >>> "nesting" in render_prop_contract()
    True
    """
    example = PropDescriptor(name="example")
    lines = [
        f"# Prop contract (prop schema {example.schema_version})",
        "",
        "Checked offline by `an props validate <folder>`.",
        "",
        "## Layout",
        "",
        "    <key>/",
        f"      {PROP_META_NAME:<20}  the descriptor: bones, slots, skins, asset_sets",
        "      parts/                one SVG or PNG/JPEG/WebP per attachment",
        "",
        "## The rig",
        "",
        f"- Positions are in view_box units; the default view_box is {list(example.view_box)}.",
        f"- Unset, a prop is one bone {[b.name for b in example.bones]} and one slot "
        f"{[s.name for s in example.slots]}.",
        "- A bone's `x`/`y` are relative to its parent; its `rotation_deg` and "
        "`scale_x`/`scale_y` are its part's REST pose.",
        "- An attachment's `x`/`y` offset it from its bone; its `anchor` (0..1) is "
        "the point of the art at that position, and the point it turns about.",
        "- `origin: [x, y]` is the point of the art that lands at the entity's "
        "`stage.at` (unset: the middle of the bones' extent).",
        f"- `nesting` is one of {list(NESTINGS)}: `flat` (unset) nests a slot only "
        "under its own bone's primary slot (the slot named like the bone); "
        f"`{BONES_NESTING}` nests it under the nearest ancestor bone's primary "
        "slot, so a hand turns with its forearm and a sword with its hand.",
        "- With nested chains, a part draws OVER its parent: its `draw_order` must "
        "be at least its parent's.",
        "",
        "## Blocking",
        "",
        "- a bone naming an unknown parent, a bone cycle, a slot on an unknown bone;",
        "- an attachment, in any skin, whose art is not in the folder or is an SVG that is not",
        "  self-contained; a prop that draws nothing.",
        "",
        "## Advisory",
        "",
        "- a chain interleaved with an unrelated part (the stage paints it from a",
        "  global part order; an engine without `engine.paint_order:global` refuses it);",
        "- an origin outside the view_box; a rest-rotated bone whose part is offset;",
        "- no `source` (where the art came from, and its licence).",
    ]
    return "\n".join(lines) + "\n"
