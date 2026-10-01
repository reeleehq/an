"""The core's vocabulary: views over the kind and easing registries, camera moves, IR fields.

ADR 0003's first slice seeds the registry with today's named vocabularies.
The **core's** share is here (a genre contributes the rest through
:class:`an.genres.Genre`):

- **action kinds** and **entity kinds** — *views* over
  :mod:`an.genres.registry`, so a genre's kinds appear as entries the moment it
  registers them, with their owner and :attr:`~an.genres.ActionKind.version`;
- **easings** — a view over :func:`an.timing.easing.easing_entries` (the
  easing canon already carries a version per entry);
- **camera moves** — a view over :data:`an.ir.camera.CAMERA_MOVES`, versioned
  in :data:`CAMERA_MOVE_VERSIONS` (a test fails when a move has none); each is
  a path through the ``framing2d`` **view space** and requires an engine that
  lowers it (``space.framing2d``, :mod:`an.semantic.views`, an#257);
- **view spaces** — ``framing2d`` and ``orbit3d`` (:mod:`an.semantic.views`);
- **IR fields** (kind ``field``) — what the scene document's fields accept,
  the notes the ``an iterate`` prompt used to hand-list. Each says which
  spectrum levels it takes: a field that accepts only (a) says so, and no
  resolver will invent a value for it (ADR 0003 decision 5).

Nothing here imports ``an.ir`` at module level; the views import their sources
when read.

>>> from an.semantic.registry import lookup
>>> lookup("action", "tween").version, lookup("easing", "linear").kind
('1', 'easing')
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

from an.genres.registry import CORE_OWNER
from an.semantic.entries import Entry
from an.semantic.registry import register_entry, register_view

__all__ = [
    "CAMERA_MOVE_DESCRIPTIONS",
    "CAMERA_MOVE_VERSIONS",
    "CORE_FIELDS",
    "schema_of_callable",
]

#: Version of each named camera move (ADR 0003). Bump one when its keys change.
CAMERA_MOVE_VERSIONS: dict[str, str] = {
    "hold": "1",
    "push_in": "1",
    "pull_out": "1",
    "zoom_in": "1",
    "zoom_out": "1",
    "pan_left": "1",
    "pan_right": "1",
    "tilt_up": "1",
    "tilt_down": "1",
}

#: One sentence per camera move, in production terms.
CAMERA_MOVE_DESCRIPTIONS: dict[str, str] = {
    "hold": "a locked-off camera: no move",
    "push_in": "a slow push in: zoom 1.0 → 1.25 over the shot, eased",
    "pull_out": "a slow pull out: zoom 1.0 → 0.8 over the shot, eased",
    "zoom_in": "a stronger zoom in: 1.0 → 1.5 over the shot",
    "zoom_out": "a stronger zoom out: 1.0 → 0.7 over the shot",
    "pan_left": "truck the camera left across the frame (on a flat stage a pan and a truck look the same)",
    "pan_right": "truck the camera right across the frame",
    "tilt_up": "move the camera up across the frame (spans the frame height)",
    "tilt_down": "move the camera down across the frame",
}


# -----------------------------------------------------------------------------
# Params as JSON Schema
# -----------------------------------------------------------------------------

_JSON_TYPES: dict[type, str] = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
}


def _json_type(annotation: Any, default: Any) -> dict[str, Any]:
    text = (
        annotation
        if isinstance(annotation, str)
        else getattr(annotation, "__name__", "")
    )
    for py, js in _JSON_TYPES.items():
        if (
            text == py.__name__
            or text.startswith(py.__name__ + " ")
            or text in (f"{py.__name__} | None",)
        ):
            return {"type": js}
    if text in ("Seconds",):
        return {"type": "number"}
    if isinstance(default, bool):
        return {"type": "boolean"}
    if isinstance(default, (int, float)):
        return {"type": "number"}
    if isinstance(default, str):
        return {"type": "string"}
    if "tuple" in text or "list" in text:
        return {"type": "array"}
    return {}


def schema_of_callable(
    fn: Any, *, skip: Iterable[str] = (), positional: bool = False
) -> dict[str, Any]:
    """A JSON Schema object for ``fn``'s keyword parameters, defaults included.

    Positional-only and ``skip``ped parameters are left out (``target``,
    ``rest``, ``parts`` are the compiler's, not the author's).

    >>> def f(target, *, height: float = 30.0, label: str = "x", n: int | None = None): ...
    >>> schema_of_callable(f, skip=("target",))["properties"]["height"]
    {'type': 'number', 'default': 30.0}
    """
    skip = set(skip)
    props: dict[str, Any] = {}
    for name, p in inspect.signature(fn).parameters.items():
        if name in skip or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.kind is p.POSITIONAL_ONLY or (
            p.kind is p.POSITIONAL_OR_KEYWORD
            and not positional
            and p.default is p.empty
        ):
            continue
        default = None if p.default is p.empty else p.default
        spec = _json_type(p.annotation, default)
        if p.default is not p.empty:
            spec["default"] = list(default) if isinstance(default, tuple) else default
        props[name] = spec
    return {"type": "object", "properties": props}


# -----------------------------------------------------------------------------
# Views
# -----------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _schema_of(model: type) -> dict[str, Any]:
    """The action model's JSON Schema (ADR 0003 decision 5), without its ``kind``."""
    try:
        schema = dict(model.model_json_schema())
    except Exception:  # noqa: BLE001 — a model pydantic cannot describe: its field names
        schema = {
            "type": "object",
            "properties": {f: {} for f in getattr(model, "model_fields", {})},
        }
    props = dict(schema.get("properties") or {})
    props.pop("kind", None)
    schema["properties"] = props
    return schema


def _action_kinds() -> Iterable[tuple[Entry, str]]:
    from an.genres import registry as r

    for name in r.action_kind_names():
        kind = r.action_kind(name)
        yield (
            Entry(
                f"action.{name}",
                "action",
                version=kind.version,
                name=name,
                description=kind.description,
                params=_schema_of(kind.model),
                levels=frozenset({"a"}),
            ),
            r.action_kind_owner(name) or CORE_OWNER,
        )


def _entity_kinds() -> Iterable[tuple[Entry, str]]:
    from an.genres import registry as r

    for name in r.entity_kind_names():
        kind = r.entity_kind(name)
        yield (
            Entry(
                f"entity.{name}",
                "entity",
                version=kind.version,
                name=name,
                description=kind.description,
                usage=(f"its nodes are {kind.space} nodes" if kind.space else "")
                + (f"; ref keys into the {kind.store!r} store" if kind.store else ""),
                levels=frozenset({"a"}),
            ),
            r._ENTITY_KINDS.owners.get(name, CORE_OWNER),
        )


#: The usage note of an easing a scene document may name today.
IR_EASING_USAGE: str = "a tween's `easing` may name it"


def ir_easing_names() -> frozenset[str]:
    """The easings a scene document's tween may name today (what the evaluators draw).

    The timing kernel registers more (the CSS and Manim families, P1); those
    are vocabulary entries — versioned, digestible — but not yet values a tween
    may take, so the generated prompt and skill list only these.
    """
    from an.timing.easing import VALUE_TYPED_EASINGS

    return frozenset(VALUE_TYPED_EASINGS)


def _easings() -> Iterable[tuple[Entry, str]]:
    from an.timing import easing as ez

    in_ir = ir_easing_names()
    for e in ez.easing_entries():
        yield (
            Entry(
                f"easing.{e.name}",
                "easing",
                version=str(e.version),
                name=e.name,
                description=e.description,
                usage=(
                    IR_EASING_USAGE
                    if e.name in in_ir
                    else f"the timing kernel's ({e.family} family); not yet a value a tween may name"
                ),
            ),
            ez._OWNERS.get(e.name) or CORE_OWNER,
        )


#: How the engines lower a framing move (an#257), said once for every move.
CAMERA_MOVE_USAGE: str = (
    "spelled `camera: {move: <name>}` on a shot (sugar over `camera.keys`). A path "
    "through the framing2d view space (`params.path`, time 0..1 over the shot; x/y "
    "in frame widths/heights, zoom a ratio): the stage engine re-renders the scene "
    "into the moving frame (no resolution loss); a crop engine moves a crop over "
    "fixed pixels"
)


def camera_move_path(name: str) -> list[dict[str, Any]]:
    """The move as keys in the framing2d view space, read off :data:`an.ir.camera.CAMERA_MOVES`.

    Derived, never restated: the move's own key list at a unit duration, with
    every axis the move changes (x/y in frame spans, as ``camera_keys`` scales
    them); ``hold`` is the empty path.

    >>> camera_move_path("push_in"), camera_move_path("pan_left")
    ([{'at': 0.0, 'zoom': 1.0}, {'at': 1.0, 'zoom': 1.25}], [{'at': 0.0, 'x': 0.0}, {'at': 1.0, 'x': -1.0}])
    """
    from an.ir.camera import CAMERA_MOVES
    from an.semantic.views import FRAMING_2D

    rest = {k: v["default"] for k, v in FRAMING_2D.entry.params["properties"].items()}
    keys = CAMERA_MOVES[name](1.0)
    moved = [
        a for a, r in rest.items() if any(float(getattr(k, a, r)) != r for k in keys)
    ]
    return [
        {"at": float(k.at), **{a: float(getattr(k, a, rest[a])) for a in moved}}
        for k in keys
    ]


def _camera_moves() -> Iterable[tuple[Entry, str]]:
    from an.ir.camera import CAMERA_MOVES
    from an.semantic.views import FRAMING_2D

    for name in CAMERA_MOVES:
        yield (
            Entry(
                f"camera.{name}",
                "camera_move",
                version=CAMERA_MOVE_VERSIONS.get(name, "1"),
                name=name,
                description=CAMERA_MOVE_DESCRIPTIONS.get(name, ""),
                usage=CAMERA_MOVE_USAGE,
                params={
                    "type": "object",
                    "properties": {
                        "space": {
                            "const": FRAMING_2D.entry.term,
                            "default": FRAMING_2D.entry.term,
                        },
                        "path": {"type": "array", "default": camera_move_path(name)},
                    },
                },
                requires=(FRAMING_2D.requirement,),
            ),
            CORE_OWNER,
        )


register_view("action_kinds", _action_kinds)
register_view("entity_kinds", _entity_kinds)
register_view("easings", _easings)
register_view("camera_moves", _camera_moves)


# -----------------------------------------------------------------------------
# The scene document's fields (core)
# -----------------------------------------------------------------------------


def _quoted(names: Iterable[str]) -> str:
    """``"a" | "b"``: an enumeration as the scene document spells its values."""
    return " | ".join('"' + n + '"' for n in names)


def _field(
    path: str, usage: str, *, levels=("a",), description: str = "", **kw
) -> Entry:
    return Entry(
        f"field.{path}",
        "field",
        name=path,
        description=description,
        usage=usage,
        levels=frozenset(levels),
        **kw,
    )


def _core_fields() -> tuple[Entry, ...]:
    from an.base import (
        COLOUR_PROPERTY,
        SUPPORTED_RENDERERS,
        TRANSFORM_PROPERTIES,
        TRANSITION_KINDS,
    )

    authored = sorted(
        p for p in TRANSFORM_PROPERTIES if not p.startswith(COLOUR_PROPERTY + "_")
    )
    return (
        _field(
            "meta",
            "meta: {title, author, duration, fps, resolution, default_renderer, "
            "notes, default_easing, step_hz, style_pack, sounds, captions}",
            description="the film's header",
        ),
        _field(
            "shot",
            "timeline: a list of shots, each with id (string, unique), renderer "
            f"({_quoted(SUPPORTED_RENDERERS)}), duration "
            "(seconds, float), camera, entities, actions, dialogue, narration, "
            "transition, sounds",
            description="one shot of the timeline",
        ),
        _field(
            "shot.camera",
            "camera: {move: <a camera move>, ...} or explicit {keys: [...]}",
            levels=("a", "b-name"),
            description="the shot's camera",
        ),
        _field(
            "shot.entities",
            "entities: list of {kind, id, store, ref, ...}; kind MUST be a "
            "registered entity kind. A prop needs a PropDescriptor in the props "
            "store; it has no placeholder rig, so an unknown ref raises rather "
            "than drawing a person.",
            description="who and what is on stage",
        ),
        _field(
            "shot.actions",
            "actions: list of action dicts whose kind is a registered action kind "
            "(the composites sequence, parallel, delay and loop hold children).",
            description="the shot's animation",
        ),
        _field(
            "shot.actions.property",
            "A tween/set action's property is EITHER a transform: "
            f"{', '.join(authored)} — OR {COLOUR_PROPERTY!r}, a per-node colour "
            "MULTIPLY whose value is a '#rrggbb' string (the compiler expands it "
            "into three numeric channels, so a tween between two colours "
            "interpolates per channel; like 'alpha' it cascades to the target's "
            "parts). 'alpha' is the fade primitive and cascades to a character's "
            "parts. Any other property (opacity, visible, color, width, ...) is "
            "refused at compile. A tween with no 'from' starts at the property's "
            "rest value: 1.0 for scale_x / scale_y / alpha, '#ffffff' for tint, "
            "0.0 for the rest. A tween with no 'easing' takes the scene's "
            "meta.default_easing when set.",
            description="what a set or tween animates",
        ),
        _field(
            "shot.actions.easing",
            "A tween's easing is a registered easing name, a cubic-Bézier "
            "4-list [cx1, cy1, cx2, cy2], or a parametrised curve such as "
            "'cubic-bezier(…)' or 'steps(n)'.",
            levels=("a", "b-name"),
            description="how a tween moves through time",
        ),
        _field(
            "shot.dialogue",
            "dialogue: list of {speaker, text, emotion, voice_ref, pause, at, "
            "direction, ...}. Lines play back to back from the shot start. "
            "'pause' (seconds) is silence before a line, after the previous one "
            "ends — a beat, a look, a hesitation belongs here, NOT in a new shot. "
            "'at' (seconds) starts a line at that shot time instead; a line takes "
            "one or the other, never both (to switch, delete the one you are "
            "replacing in the same patch list). 'start' and 'duration' are "
            "stamped by the audio pipeline from these on every render — never "
            "patch them.",
            description="who says what, and when",
        ),
        _field(
            "shot.dialogue.direction",
            "direction (optional) is a list of delivery cues — ['excited'], "
            "['sighs', 'annoyed'] — that an expressive TTS voice performs; it is "
            "never spoken as text and never shown in captions.",
            description="how a line is delivered",
        ),
        _field(
            "shot.narration",
            "narration: list (same shape as dialogue, no speaker pin). NOT "
            "IMPLEMENTED — the audio pipeline walks dialogue only, and a shot with "
            "narration RAISES. To add a narrator, emit a dialogue line whose "
            "speaker is not an entity in the shot; it gets audio and no lip-sync.",
            description="a narrator's lines (not implemented)",
        ),
        _field(
            "shot.transition",
            "transition (optional): how the shot is ENTERED — {kind: "
            f"{_quoted(TRANSITION_KINDS)}, duration: seconds, "
            "color: '#rrggbb'}. Omitted = a hard cut. 'fade' dips through color "
            "(half out of the previous shot, half into this one; on the first "
            "shot, a fade up). 'dissolve' overlaps the two shots by duration, so "
            "the film gets that much shorter; never on the first shot. A shot "
            "must be long enough to hold its own transition and the next shot's.",
            description="how a shot is entered",
        ),
        _field(
            "shot.sounds",
            "sounds (optional): SFX cues in SHOT-local time — [{sound: <key in "
            "the sounds store>, at, [duration], [gain_db], [loop], [fade_in], "
            "[fade_out], [duck_db]}]. Never invent a sound key.",
            description="sound effects on the shot's clock",
        ),
        _field(
            "meta.sounds",
            "meta.sounds (optional): the same cue shape in FILM time — a music "
            "bed is {sound: <key>, loop: true, duck_db: -12, fade_in, fade_out}; "
            "duck_db ducks it under every dialogue line.",
            description="sounds on the film's clock (a music bed)",
        ),
        _field(
            "meta.captions",
            "meta.captions (optional): captions built at render time from the "
            "dialogue's word timings — {} for the defaults, or {highlight: "
            "'#rrggbb', color, size, anchor, max_chars, max_lines, burn, sidecar, "
            "strict}. Never add caption text entities by hand: they are derived "
            "from the dialogue.",
            description="captions derived from the dialogue",
        ),
    )


#: The core's IR-field entries, registered on import (owner: the core).
CORE_FIELDS: tuple[Entry, ...] = _core_fields()
for _e in CORE_FIELDS:
    register_entry(_e, owner=CORE_OWNER)


def _register_view_spaces() -> None:
    """The core's view spaces (an#257): an entry each, and the engine capability to lower it."""
    from an.capabilities import register_capability
    from an.semantic.views import CORE_VIEW_SPACES

    for space in CORE_VIEW_SPACES:
        register_entry(space.entry, owner=CORE_OWNER)
        register_capability(space.capability, owner=CORE_OWNER)


_register_view_spaces()
