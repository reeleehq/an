"""Bidirectional sync between ``scene.md`` (Narrative Layer) and ``ir/scene.json`` (Scene Graph Layer).

The Markdown form is what humans edit. The JSON form is what the agent and
verifiers operate on. They must round-trip cleanly.

Markdown convention (v0.1, kept simple — extended in P5):

    # <title>

    Optional prose intro (saved to meta.notes).

    ```yaml meta
    title: Park Bench
    duration: 45
    fps: 30
    ```

    ## Shot s1 (cutout)

    Optional prose direction for this shot.

    ```yaml shot
    duration: 15
    camera:
      move: push_in
    ```

    ```dialogue
    charlie: Did you ever wonder why we always meet here?
    maya: Because the pigeons trust us.
    ```

A shot heading is ``## Shot <id> (<renderer>)`` — the parenthesised word names
the RENDERER, and is captured positionally, so the heading is unchanged by the
an#106 rename. Fenced blocks attach to the
nearest enclosing scope. Unknown blocks are preserved as ``options`` so
agent extensions don't get clobbered on round-trip.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
import warnings
from pathlib import Path
from typing import Any

import yaml

from an.base import DEFAULT_DURATION
from pydantic import ValidationError

from an.ir.migrate import (
    SCENE_IR,
    DocumentMigrationError,
    migrate,
    readable_without_migration,
    version_tuple,
)
from an.genres.registry import (
    CORE_OWNER,
    DIALOGUE_BRACKETS,
    UnregisteredKindError,
    action_kind,
    action_kind_names,
    dialogue_sugar,
    dialogue_sugars,
    register_action_kind,
)
from an.ir.schema import AssetRef, Dialogue, Meta, SceneIR, Shot
from an.util import _read_text, _write_json, _write_text


#: Two files whose mtimes are closer than this are "the same age" to `sync`,
#: which then rewrites neither (write order inside one store call must not
#: flip-flop the source of truth).
SYNC_MTIME_TOLERANCE_S: float = 0.5

_FENCE_RE = re.compile(
    r"^```(\w+)(?:\s+(\w+))?\s*\n(.*?)\n```", re.MULTILINE | re.DOTALL
)
_SHOT_HEADING_RE = re.compile(
    r"^##\s+Shot\s+(\S+)(?:\s+\(([^)]+)\))?\s*$", re.MULTILINE
)


class SceneMarkdownError(ValueError):
    """`scene.md` says something this build cannot read — a refusal, not a crash.

    Every parse refusal in this module raises it, so the CLI can tell "the
    human's file needs one edit" apart from "something broke". That
    distinction is the whole point of naming it: an#106's first pass widened
    the CLI's catch to bare ``ValueError`` to print these cleanly, which also
    swallowed ``json.JSONDecodeError`` and ``CutoutCompileError`` — both
    ``ValueError`` subclasses — and turned a failed render into exit 0.
    """


@dataclass(slots=True)
class SyncResult:
    """Outcome of a sync operation."""

    wrote_json: bool = False
    wrote_md: bool = False
    drift_warning: str | None = None


# -----------------------------------------------------------------------------
# Markdown → IR
# -----------------------------------------------------------------------------


def markdown_to_ir(md_text: str) -> SceneIR:
    """Parse the structured Markdown form of a scene into a SceneIR.

    >>> md = '''# Demo
    ...
    ... ```yaml meta
    ... title: Demo
    ... duration: 5
    ... ```
    ...
    ... ## Shot s1 (cutout)
    ...
    ... ```yaml shot
    ... duration: 5
    ... ```
    ...
    ... ```dialogue
    ... charlie: hi
    ... ```
    ... '''
    >>> scene = markdown_to_ir(md)
    >>> scene.meta.title
    'Demo'
    >>> scene.timeline[0].id
    's1'
    >>> scene.timeline[0].dialogue[0].text
    'hi'
    """
    title = _extract_title(md_text)

    # Split into segments: a "global" segment (before any ## Shot heading) and
    # one segment per shot heading.
    parts = _split_by_shots(md_text)
    global_text = parts["__global__"]

    meta_data = _extract_yaml_block(global_text, "meta") or {}
    if "default_style" in meta_data:
        # A REFUSAL, not a silent rename. `scene.md` is the human SSOT and
        # carries no schema version, so nothing here can tell "written before
        # an#106" from "typed today" — and `Meta` is `extra="allow"`, so
        # dropping it would leave the author's declared renderer silently
        # replaced by the default. The stored JSON is migrated instead; a
        # hand-edited md is the author's to fix, once.
        raise SceneMarkdownError(
            "`default_style:` in the meta block was renamed to `default_renderer:` "
            "(an#106): it names the RENDERER that draws the shots, not art "
            "direction. Rename the key."
        )
    if title and "title" not in meta_data:
        meta_data["title"] = title
    meta = Meta(**meta_data)

    shots: list[Shot] = []
    for shot_id, renderer, body in parts["__shots__"]:
        shot_yaml = _extract_yaml_block(body, "shot") or {}
        dialogue_block = _extract_dialogue_block(body, shot_id=shot_id)
        entities_block = _extract_entities_block(body)
        actions_block = _extract_actions_block(body)
        shot_kwargs: dict[str, Any] = {
            "id": shot_id,
            "renderer": renderer or meta.default_renderer,
            "duration": shot_yaml.get("duration", DEFAULT_DURATION),
            "dialogue": dialogue_block,
            "entities": entities_block,
            "actions": actions_block,
        }
        # Camera, options, etc., come straight from the YAML if present.
        if "camera" in shot_yaml:
            shot_kwargs["camera"] = _strip_retired_camera_fields(
                shot_yaml["camera"], shot_id=shot_id
            )
        if "options" in shot_yaml:
            shot_kwargs["options"] = shot_yaml["options"]
        # Whitelisted, like `camera`: this reader enumerates shot keys, so a
        # field added to `Shot` that is not named here silently drops on read
        # (and the writer above enumerates too, so on write) — an#89.
        if "step_hz" in shot_yaml:
            shot_kwargs["step_hz"] = shot_yaml["step_hz"]
        # The assembly fields (transitions, the sound layer) and the shot's
        # method policy (an#348): same whitelist.
        for key in ("transition", "sounds", "policy"):
            if key in shot_yaml:
                shot_kwargs[key] = shot_yaml[key]
        shots.append(Shot(**shot_kwargs))

    if meta.duration == 0.0:
        meta.duration = sum(s.duration for s in shots)

    return SceneIR(meta=meta, timeline=shots)


def _extract_title(md_text: str) -> str:
    for line in md_text.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return ""


#: What a camera block's dead fields defaulted to, so a value someone actually
#: TYPED can be told apart from one the writer emitted.
_RETIRED_CAMERA_DEFAULTS: dict[str, Any] = {
    "position": [0.0, 0.0, 0.0],
    "target": [0.0, 0.0, 0.0],
    "focal_length": 50.0,
}


def _strip_retired_camera_fields(camera: Any, *, shot_id: str) -> Any:
    """Drop an#109's removed camera fields from a `scene.md` camera block.

    The stored-JSON side is a registered migration; this is the same rule on
    the surface that carries no schema version. Dropped SILENTLY when the value
    is the default the writer emitted — every `scene.md` this package generated
    since 0.1.0 carries `position`, `target` and `focal_length`, and warning on
    all of them would be noise on exactly the documents that had nothing to do
    with it. A non-default value warns, because that one someone typed.

    Not a refusal, unlike an#106's `default_style:`. That rename would have
    silently replaced the author's declared RENDERER with the default; these
    fields selected nothing at all — they described a 3D camera this package has
    never had, and were read by nothing.
    """
    if not isinstance(camera, dict):
        return camera
    camera = dict(camera)
    authored = {}
    for field, default in _RETIRED_CAMERA_DEFAULTS.items():
        if field not in camera:
            continue
        value = camera.pop(field)
        if isinstance(default, list):
            if not (isinstance(value, (list, tuple)) and list(value) == default):
                authored[field] = value
        elif value != default:
            authored[field] = value
    if authored:
        warnings.warn(
            f"shot {shot_id!r}: camera {sorted(authored)} dropped — an#109 "
            "removed them because they described a 3D camera this package "
            "never had (the cutout camera is `root.pivot` plus `root.scale`). "
            "A non-default value was set, so this is said out loud.",
            stacklevel=3,
        )
    return camera


def _split_by_shots(md_text: str) -> dict[str, Any]:
    """Slice text into a global pre-section and per-shot sections."""
    matches = list(_SHOT_HEADING_RE.finditer(md_text))
    if not matches:
        return {"__global__": md_text, "__shots__": []}
    global_text = md_text[: matches[0].start()]
    shots: list[tuple[str, str | None, str]] = []
    for i, m in enumerate(matches):
        shot_id = m.group(1)
        renderer = m.group(2)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        shots.append((shot_id, renderer, md_text[body_start:body_end]))
    return {"__global__": global_text, "__shots__": shots}


def _extract_yaml_block(text: str, label: str) -> dict[str, Any] | None:
    for m in _FENCE_RE.finditer(text):
        lang, lbl, body = m.group(1), m.group(2), m.group(3)
        if lang == "yaml" and lbl == label:
            data = yaml.safe_load(body) or {}
            if not isinstance(data, dict):
                raise SceneMarkdownError(f"YAML block {label!r} must be a mapping")
            return data
    return None


_DIALOGUE_LINE_RE = re.compile(
    r"^\s*(?P<speaker>[\w-]+)"
    r"(?P<mods>(?:\s*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\}))*)"
    r"\s*:\s*(?P<text>.*?)\s*$"
)
_DIALOGUE_MOD_RE = re.compile(
    r"\[(?P<bracket>[^\]]*)\]|\((?P<paren>[^)]*)\)|\{(?P<brace>[^}]*)\}"
)
#: ``Dialogue`` fields that ``scene.md`` spells ONLY through registered sugar
#: (``maya [happy]: …``). The field is core in v1 (ADR 0001 "stays awkward");
#: its spelling is the genre's.
_SUGAR_ONLY_FIELDS: tuple[str, ...] = ("emotion",)


def _sugar_providers(field_name: str) -> tuple[str, ...]:
    """The installed genres whose dialogue sugar fills ``field_name``."""
    from an.genres import genres_declaring

    return genres_declaring(
        lambda g: any(sugar.field == field_name for sugar in g.dialogue_sugar)
    )


def _unregistered_sugar_message(opener: str, content: str) -> str:
    from an.genres import genres_declaring

    providers = genres_declaring(
        lambda g: any(sugar.opener == opener for sugar in g.dialogue_sugar)
    )
    who = (
        f"the genre(s) {list(providers)} define it but are not loaded — call "
        "`an.genres.load()` (the CLI and `an.load(project)` do)"
        if providers
        else "no installed genre defines it"
    )
    return (
        f"has {opener}{content.strip()}{DIALOGUE_BRACKETS[opener]}, which is "
        f"genre sugar no loaded genre registered: {who}"
    )


#: ``(pause 1.5)``, ``(pause 1.5s)``, ``(at 3)``, ``(at 3.0s)`` — the timing a
#: dialogue line may carry in ``scene.md`` (an#187). Parentheses hold timing,
#: square brackets hold the emotion.
_DIALOGUE_TIMING_RE = re.compile(
    r"^\s*(?P<key>pause|at)\s+(?P<value>\d+(?:\.\d*)?|\.\d+)\s*s?\s*$",
    re.IGNORECASE,
)
_DIALOGUE_GRAMMAR = (
    "`speaker [emotion] {direction} (pause 1.5): text` — the emotion in square "
    "brackets, the delivery direction in braces (comma-separated cues such as "
    "`{sighs, annoyed}`) and the timing in parentheses are each optional: "
    "`(pause <s>)` is silence after the previous line, `(at <s>)` a start in "
    "shot seconds; speaker ids are `[\\w-]+`"
)


def _parse_dialogue_line(line: str, *, where: str) -> Dialogue:
    """One ``speaker [emotion] {direction} (timing): text`` line → a `Dialogue`."""

    def refuse(why: str) -> SceneMarkdownError:
        return SceneMarkdownError(
            f"{where}dialogue line {line!r} {why}. The grammar is "
            f"{_DIALOGUE_GRAMMAR}. A line that does not parse is refused rather "
            "than dropped, so a typo cannot silence a character."
        )

    match = _DIALOGUE_LINE_RE.match(line)
    if not match:
        raise refuse("is not `speaker: text`")
    kwargs: dict[str, Any] = {
        "speaker": match.group("speaker").strip(),
        "text": match.group("text").strip(),
    }
    for mod in _DIALOGUE_MOD_RE.finditer(match.group("mods")):
        if mod.group("brace") is not None:
            if "direction" in kwargs:
                raise refuse("carries two directions; list every cue in one `{...}`")
            cues = [c.strip() for c in mod.group("brace").split(",")]
            if not all(cues):
                raise refuse(
                    f"has {{{mod.group('brace')}}}, an empty direction cue; cues "
                    "are comma-separated, e.g. `{sighs, annoyed}`"
                )
            kwargs["direction"] = cues
            continue
        if mod.group("bracket") is not None:
            # `[…]` is genre SUGAR (the cut-out genre's `[emotion]`), looked up
            # in the registry rather than known here (ADR 0001 decision 4).
            content = mod.group("bracket")
            sugar = dialogue_sugar("[")
            if sugar is None:
                raise refuse(_unregistered_sugar_message("[", content))
            try:
                value = sugar.parse(content)
            except ValueError as e:
                raise refuse(str(e)) from None
            if sugar.field in kwargs:
                raise refuse(f"names two {sugar.name}s")
            kwargs[sugar.field] = value
            continue
        timing = _DIALOGUE_TIMING_RE.match(mod.group("paren"))
        if not timing:
            raise refuse(
                f"has ({mod.group('paren').strip()}), which is not a timing — "
                "an emotion goes in square brackets"
            )
        if "pause" in kwargs or "at" in kwargs:
            raise refuse("carries two timings; a line takes one `pause` or one `at`")
        kwargs[timing.group("key").lower()] = float(timing.group("value"))
    try:
        return Dialogue(**kwargs)
    except ValueError as e:  # pydantic's ValidationError is one
        errors = getattr(e, "errors", None)
        why = "; ".join(err["msg"] for err in errors()) if errors else str(e)
        raise refuse(f"does not validate ({why})") from None


def _format_dialogue_line(line: Dialogue) -> str:
    """The `scene.md` spelling of ``line`` — `_parse_dialogue_line`'s inverse."""
    head = line.speaker
    for sugar in dialogue_sugars():
        content = sugar.format(line)
        if content:
            head += f" {sugar.opener}{content}{sugar.closer}"
    for field_name in _SUGAR_ONLY_FIELDS:
        if getattr(line, field_name, None) and not any(
            s.field == field_name for s in dialogue_sugars()
        ):
            # Writing the line without it would drop it from scene.md, and
            # the next md edit would drop it from the JSON: refuse instead.
            raise UnregisteredKindError(
                "dialogue sugar for",
                field_name,
                known=[s.name for s in dialogue_sugars()],
                providers=_sugar_providers(field_name),
                where=f"dialogue line {line.text!r} has {field_name}={getattr(line, field_name)!r}",
            )
    if line.direction:
        head += " {" + ", ".join(line.direction) + "}"
    for key in ("pause", "at"):
        value = getattr(line, key, None)
        if value is not None:
            head += f" ({key} {_format_seconds(value)})"
    return f"{head}: {line.text}"


def _format_seconds(value: float) -> str:
    """The shortest exact spelling `_DIALOGUE_TIMING_RE` reads back — no exponent.

    >>> [_format_seconds(v) for v in (1.5, 3.0, 1e-05, 1e16, 0.1 + 0.2)]
    ['1.5', '3', '0.00001', '10000000000000000', '0.30000000000000004']
    """
    from decimal import Decimal

    text = format(Decimal(repr(float(value))), "f")
    return text[:-2] if text.endswith(".0") else text


def _extract_dialogue_block(text: str, *, shot_id: str | None = None) -> list[Dialogue]:
    """Parse a ```dialogue block.

    Each non-empty, non-comment line follows
    ``speaker [emotion] {direction} (timing): text`` where the bracketed
    emotion, the braced delivery direction (an#209) and the parenthesised
    timing are optional, in any order. Examples:

        charlie: Hello.
        charlie [happy]: Hello!
        maya [skeptical] (pause 1.5): Sure.
        maya (at 4): Goodbye.
        bob [happy] {excited}: Hi!
        ned {sighs, annoyed}: Fine.

    ``(pause <s>)`` is silence after the previous line ends; ``(at <s>)`` starts
    the line at that shot time (an#187). A line that matches none of those
    shapes is a **parse error**, not a skip: this parser used to drop it
    silently, and ``examples/promote_demo`` was mute for months because its one
    line read ``maya (warm): …`` (an#96).
    """
    out: list[Dialogue] = []
    where = f"shot {shot_id!r}: " if shot_id else ""
    for m in _FENCE_RE.finditer(text):
        lang, _lbl, body = m.group(1), m.group(2), m.group(3)
        if lang != "dialogue":
            continue
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            out.append(_parse_dialogue_line(line, where=where))
    return out


def _extract_entities_block(text: str) -> list[AssetRef]:
    """Parse a ```yaml entities block: a list of AssetRef-shaped dicts."""
    raw = _extract_yaml_list_block(text, "entities")
    if not raw:
        return []
    out: list[AssetRef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise SceneMarkdownError(
                f"each entry under `yaml entities` must be a mapping; got {item!r}"
            )
        out.append(AssetRef(**item))
    return out


def _extract_actions_block(text: str) -> list:
    """Parse a ```yaml actions block: a list of leaf-action dicts.

    Each item's ``kind`` is looked up in the action-kind registry and read by
    that kind's ``read_md`` hook (ADR 0001 decision 4), so a genre's kinds
    parse without an edit here. The core's two:

      - ``{kind: tween, target, property, to, duration, [from_], [easing], [start]}``
      - ``{kind: set,   target, property, value, [at]}`` — `at`, never
        `start`: a `set` is instantaneous, and `start` on one RAISES rather
        than being silently dropped as it was before an#108.

    and, with the cut-out genre loaded, ``play`` (an#7, an#166) and
    ``expression`` (an#98) — see :mod:`an.characters.registration` and
    :mod:`an.expression.registration`.

    A leaf action with a ``start`` key (any kind registered with
    ``md_start=True``) is wrapped in ``sequence(delay(start), action)`` so
    flatten yields the correct absolute time. ``set`` uses ``at`` instead
    (built into the schema). Returns the list of authoring Actions.
    """
    raw = _extract_yaml_list_block(text, "actions")
    if not raw:
        return []
    # Lazy import to avoid a cycle (compose imports schema, schema imports nothing).
    from an.ir import compose as _compose

    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SceneMarkdownError(
                f"each entry under `yaml actions` must be a mapping; got {item!r}"
            )
        kind = item.get("kind")
        registered = action_kind(kind) if isinstance(kind, str) else None
        if registered is None:
            raise SceneMarkdownError(_unknown_md_kind_message(i, kind))
        start = item.pop("start", None) if registered.md_start else None
        if registered.read_md is not None:
            action = registered.read_md(item, index=i)
        else:
            # A kind with no short form (a composite, a genre leaf without md
            # hooks) is written verbatim; it reads back through the schema.
            action = _validate_action(item, index=i)
        if start is not None and float(start) > 0:
            action = _compose.sequence(_compose.delay(float(start)), action)
        out.append(action)
    return out


def _validate_action(item: dict[str, Any], *, index: int) -> Any:
    """A verbatim ``yaml actions`` entry, validated by the schema's union."""
    from pydantic import TypeAdapter

    from an.ir.schema import Action

    try:
        return TypeAdapter(Action).validate_python(item)
    except ValidationError as e:
        raise SceneMarkdownError(f"actions[{index}] is not a valid action: {e}") from e


def _md_kinds() -> list[str]:
    """The action kinds ``scene.md`` can spell, in registration order."""
    return list(action_kind_names())


def _unknown_md_kind_message(index: int, kind: Any) -> str:
    message = (
        f"actions[{index}].kind must be one of {'/'.join(_md_kinds())}; got {kind!r}"
    )
    if isinstance(kind, str):
        from an.genres import providers_of

        providers = providers_of(kind)
        if providers:
            message += (
                f" — `{kind}` is defined by the genre(s) {list(providers)}, which "
                "are installed but not loaded: call `an.genres.load()` (the CLI "
                "and `an.load(project)` do)"
            )
    return message


def _read_tween_md(item: dict[str, Any], *, index: int) -> Any:
    """``{kind: tween, target, property, to, duration, [from_], [easing]}``."""
    from an.ir import compose as _compose

    target = item["target"]
    property_ = item["property"]
    to = item["to"]
    duration = float(item["duration"])
    from_ = item.get("from_") if "from_" in item else item.get("from")
    # An `easing:` key the author did not write stays UNSET, so the
    # scene's `default_easing` reaches it (an#166); `easing: null` is
    # an explicit linear ramp, so presence — not truthiness — decides.
    return _compose.tween(
        target,
        property_,
        to=to,
        duration=duration,
        from_=from_,
        easing=item["easing"] if "easing" in item else _compose.INHERIT,
    )


def _read_set_md(item: dict[str, Any], *, index: int) -> Any:
    """``{kind: set, target, property, value, [at]}``."""
    from an.ir import compose as _compose

    if "start" in item:
        # A REFUSAL, not an alias. `start` is the wrapper key for
        # actions that HAVE a duration — the parser turns it into
        # `sequence(delay(start), action)`. A `set` is instantaneous,
        # so its time IS `at`, and giving one number two names is how
        # a scene ends up with both.
        #
        # It was silently dropped before an#108: `start` is popped only
        # for kinds registered with `md_start`, and this reader reads `at`
        # alone, so `{kind: set, start: 1.0}` compiled to a swap at t=0. The
        # author sees a lamp that is lit from the first frame and no
        # message anywhere.
        raise SceneMarkdownError(
            f"actions[{index}] is a `set` with `start: {item['start']!r}`, "
            "which does nothing: a `set` is instantaneous and its time "
            f"is `at:`. Write `at: {item['start']!r}`."
        )
    return _compose.set_(
        item["target"],
        item["property"],
        item["value"],
        at=float(item.get("at", 0.0)),
    )


def _write_tween_md(leaf: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": "tween",
        "target": leaf.target,
        "property": leaf.property,
        "to": leaf.to_value,
        "duration": leaf.duration,
    }
    if leaf.from_value is not None:
        entry["from"] = leaf.from_value
    # Written exactly when the author set it — `ease_in_out` included,
    # because under a scene `default_easing` an explicit ease_in_out
    # and an unset easing draw different curves (an#166).
    if "easing" in leaf.model_fields_set:
        entry["easing"] = (
            list(leaf.easing) if isinstance(leaf.easing, tuple) else leaf.easing
        )
    return entry


def _write_set_md(leaf: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "kind": "set",
        "target": leaf.target,
        "property": leaf.property,
        "value": leaf.value,
    }
    if leaf.at:
        entry["at"] = leaf.at
    return entry


def _attach_core_md_hooks() -> None:
    """Give the core's ``set`` and ``tween`` (registered by :mod:`an.ir.compose`)
    their ``scene.md`` hooks: this module owns the markdown form."""
    from dataclasses import replace

    from an.ir import compose as _compose  # noqa: F401 — registers the core kinds

    for name, read, write in (
        ("set", _read_set_md, _write_set_md),
        ("tween", _read_tween_md, _write_tween_md),
    ):
        current = action_kind(name)
        if current is not None and current.read_md is None:
            register_action_kind(
                replace(current, read_md=read, write_md=write),
                owner=CORE_OWNER,
                replace=True,
            )


def _extract_yaml_list_block(text: str, label: str) -> list[Any] | None:
    """Parse a ```yaml <label> block whose body is a YAML list."""
    for m in _FENCE_RE.finditer(text):
        lang, lbl, body = m.group(1), m.group(2), m.group(3)
        if lang == "yaml" and lbl == label:
            data = yaml.safe_load(body)
            if data is None:
                return []
            if not isinstance(data, list):
                raise SceneMarkdownError(f"YAML block {label!r} must be a list")
            return data
    return None


# -----------------------------------------------------------------------------
# IR → Markdown
# -----------------------------------------------------------------------------


def ir_to_markdown(scene: SceneIR) -> str:
    """Render a SceneIR back into the structured Markdown form.

    >>> from an.ir.schema import SceneIR, Meta, Shot
    >>> scene = SceneIR(meta=Meta(title="Demo", duration=5.0),
    ...                 timeline=[Shot(id="s1", renderer="cutout", duration=5.0)])
    >>> md = ir_to_markdown(scene)
    >>> "# Demo" in md
    True
    >>> "## Shot s1 (cutout)" in md
    True

    This writes the WHOLE document in the writer's own formatting, and keeps no
    prose but ``meta.notes``. Updating an existing ``scene.md`` goes through
    :func:`merge_markdown`, which keeps the author's text wherever the content
    did not change.
    """
    parts: list[str] = [_md_title_line(scene) + "\n"]
    parts.append(_md_fence(_META_FENCE, _md_meta_body(scene)) + "\n")

    if scene.meta.notes:
        parts.append(scene.meta.notes.rstrip() + "\n")

    for shot in scene.timeline:
        parts.append(_md_shot_text(shot))

    return "\n".join(parts).rstrip() + "\n"


#: A fenced block's identity in ``scene.md``: ``(language, label)``.
FenceKey = tuple[str, "str | None"]

_META_FENCE: FenceKey = ("yaml", "meta")

#: The blocks the writer emits per shot, in the order it emits them.
_SHOT_FENCES: tuple[FenceKey, ...] = (
    ("yaml", "shot"),
    ("yaml", "entities"),
    ("yaml", "actions"),
    ("dialogue", None),
)


def _md_fence(key: FenceKey, body: str) -> str:
    lang, label = key
    opener = f"```{lang} {label}" if label else f"```{lang}"
    return f"{opener}\n{body}\n```"


def _md_title_line(scene: SceneIR) -> str:
    return f"# {scene.meta.title or 'Untitled'}"


def _md_shot_heading(shot: Shot) -> str:
    return f"## Shot {shot.id} ({shot.renderer})"


def _md_meta_body(scene: SceneIR) -> str:
    """The ```yaml meta`` block's body, as the writer spells it."""
    meta_dict = {
        "title": scene.meta.title,
        "author": scene.meta.author,
        "duration": scene.meta.duration,
        "fps": scene.meta.fps,
        "resolution": {
            "width": scene.meta.resolution.width,
            "height": scene.meta.resolution.height,
        },
        "default_renderer": scene.meta.default_renderer,
    }
    if scene.meta.step_hz is not None:
        meta_dict["step_hz"] = scene.meta.step_hz
    # Written only when set, like `step_hz`: this writer ENUMERATES the meta
    # keys, so a field added to `Meta` and not named here silently drops on
    # write — which is the an#89 trap, and the reason a round-trip test is the
    # thing that catches it (an#112).
    if scene.meta.style_pack:
        meta_dict["style_pack"] = scene.meta.style_pack
    if scene.meta.default_easing is not None:  # an#166, same rule
        easing = scene.meta.default_easing
        meta_dict["default_easing"] = (
            list(easing) if isinstance(easing, tuple) else easing
        )
    if scene.meta.sounds:
        meta_dict["sounds"] = [
            c.model_dump(exclude_defaults=True) for c in scene.meta.sounds
        ]
    if scene.meta.captions is not None:  # an#175, same rule
        meta_dict["captions"] = scene.meta.captions.model_dump(exclude_defaults=True)
    return yaml.safe_dump(meta_dict, sort_keys=False).rstrip()


def _md_shot_blocks(shot: Shot) -> dict[FenceKey, str]:
    """The fenced blocks the writer emits for ``shot``: ``{fence: body}``, in order."""
    blocks: dict[FenceKey, str] = {}
    shot_yaml: dict[str, Any] = {"duration": shot.duration}
    if shot.step_hz is not None:
        shot_yaml["step_hz"] = shot.step_hz
    if shot.camera is not None:
        shot_yaml["camera"] = shot.camera.model_dump(exclude_none=True)
    if shot.options:
        shot_yaml["options"] = shot.options
    if shot.transition is not None:
        shot_yaml["transition"] = shot.transition.model_dump(exclude_defaults=True)
    if shot.sounds:
        shot_yaml["sounds"] = [c.model_dump(exclude_defaults=True) for c in shot.sounds]
    if shot.policy is not None:
        shot_yaml["policy"] = shot.policy
    blocks[("yaml", "shot")] = yaml.safe_dump(shot_yaml, sort_keys=False).rstrip()
    if shot.entities:
        entities_dump = [
            e.model_dump(exclude_none=True, exclude_defaults=False)
            for e in shot.entities
        ]
        blocks[("yaml", "entities")] = yaml.safe_dump(
            entities_dump, sort_keys=False
        ).rstrip()
    if shot.actions:
        actions_dump = _actions_to_yaml_list(shot.actions)
        if actions_dump:
            blocks[("yaml", "actions")] = yaml.safe_dump(
                actions_dump, sort_keys=False
            ).rstrip()
    if shot.dialogue:
        blocks[("dialogue", None)] = "\n".join(
            _format_dialogue_line(line) for line in shot.dialogue
        )
    return blocks


def _md_shot_text(shot: Shot) -> str:
    """One shot as the writer spells it: heading, then its blocks."""
    parts = [_md_shot_heading(shot) + "\n"]
    parts += [
        _md_fence(key, body) + "\n" for key, body in _md_shot_blocks(shot).items()
    ]
    return "\n".join(parts)


# -----------------------------------------------------------------------------
# Updating an existing scene.md (an#275)
# -----------------------------------------------------------------------------


class MarkdownMergeWarning(UserWarning):
    """``scene.md`` was regenerated whole, losing the author's prose and formatting."""


def _md_canonical(md_text: str) -> str:
    """What ``md_text`` SAYS, in the writer's spelling: the round trip through the IR.

    Two documents with the same canonical form compile to the same scene;
    formatting, comments and prose do not reach it.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the author was told when it was read
        return ir_to_markdown(markdown_to_ir(md_text))


def merge_markdown(existing: str, scene: SceneIR) -> str:
    r"""``existing`` updated to say what ``scene`` says, rewriting only what changed.

    The writer (:func:`ir_to_markdown`) re-spells everything — an inline
    mapping becomes block style, ``at: 0.0`` is dropped as a default — and
    keeps no prose, so a store write after a render used to rewrite a file the
    author was still editing (an#275). This keeps the author's text instead:

    - if ``existing`` already says what ``scene`` says (same canonical form,
      :func:`_md_canonical`), it is returned UNCHANGED — the common case, a
      pipeline write that only added JSON-side state (audio, visemes);
    - otherwise only the parts whose content differs are rewritten: the title
      line, the ```yaml meta`` block, a shot's heading, and each of a shot's
      fenced blocks (``shot``, ``entities``, ``actions``, ``dialogue``) one by
      one. A new shot is appended in the writer's form, a removed one is
      dropped with its section. Prose, comments and unknown blocks outside a
      rewritten block are never touched.

    The result is checked: it must read back as ``scene`` does. If the patch
    cannot be made to (an unreadable ``existing``, a duplicated shot id), the
    whole document is regenerated and a :class:`MarkdownMergeWarning` says so.

    >>> from an.ir.schema import SceneIR, Meta, Shot
    >>> md = ("# Demo\n\nPrologue the IR does not hold.\n\n"
    ...       "```yaml meta\ntitle: Demo\nduration: 5\n```\n\n"
    ...       "## Shot s1 (cutout)\n\nShe walks in.\n\n```yaml shot\n{duration: 5}\n```\n")
    >>> scene = markdown_to_ir(md)
    >>> merge_markdown(md, scene) == md  # same content: untouched
    True
    >>> scene.timeline[0].duration = 4.0
    >>> out = merge_markdown(md, scene)
    >>> "Prologue the IR does not hold." in out and "She walks in." in out
    True
    >>> markdown_to_ir(out).timeline[0].duration
    4.0
    """
    target = ir_to_markdown(scene)
    try:
        want = _md_canonical(target)
        if _md_canonical(existing) == want:
            return existing
        old = markdown_to_ir(existing)
    except Exception as e:  # the existing file cannot be read: nothing to keep
        warnings.warn(
            f"scene.md was regenerated from the IR: the existing file could not be "
            f"read ({type(e).__name__}: {e}), so its formatting and prose were not kept.",
            MarkdownMergeWarning,
            stacklevel=2,
        )
        return target
    reason = "a shot id appears twice"
    ids = [s.id for s in old.timeline]
    if len(set(ids)) == len(ids):
        merged = _patch_markdown(existing, old, scene)
        try:
            if _md_canonical(merged) == want:
                return merged
            reason = "the patched file did not read back as the scene"
        except Exception as e:  # noqa: BLE001 - a patch that does not parse
            reason = f"the patched file did not parse ({type(e).__name__}: {e})"
    warnings.warn(
        f"scene.md was regenerated from the IR ({reason}); the author's prose and "
        "formatting were not kept. Please report the scene.md that caused it.",
        MarkdownMergeWarning,
        stacklevel=2,
    )
    return target


_H1_RE = re.compile(r"^# (?!#).*$", re.MULTILINE)


def _fences_in(text: str) -> list[tuple[FenceKey, "re.Match[str]"]]:
    return [((m.group(1), m.group(2)), m) for m in _FENCE_RE.finditer(text)]


def _replace_block(text: str, key: FenceKey, body: str | None) -> str:
    """``text`` with its first ``key`` block's body set to ``body``; removed when
    ``body`` is ``None``. The caller has checked the block exists."""
    m = next(m for k, m in _fences_in(text) if k == key)
    if body is not None:
        return text[: m.start(3)] + body + text[m.end(3) :]
    left, right = text[: m.start()].rstrip("\n"), text[m.end() :].lstrip("\n")
    return left + ("\n\n" + right if right else "\n")


def _insert_block(
    text: str, key: FenceKey, body: str, *, order: tuple[FenceKey, ...]
) -> str:
    """``text`` with a new ``key`` block placed where the writer would put it:
    after the nearest block that precedes it in ``order``, else before the
    nearest that follows it, else at the end of ``text``."""
    fences = _fences_in(text)
    block = _md_fence(key, body)
    rank = order.index(key)
    before = [m for k, m in fences if k in order and order.index(k) < rank]
    if before:
        at = before[-1].end()
        return text[:at] + "\n\n" + block + text[at:]
    after = [m for k, m in fences if k in order and order.index(k) > rank]
    if after:
        at = after[0].start()
        return text[:at] + block + "\n\n" + text[at:]
    stripped = text.rstrip("\n")
    return stripped + ("\n\n" if stripped else "") + block + "\n"


def _patch_blocks(
    text: str,
    old: dict[FenceKey, str],
    new: dict[FenceKey, str],
    *,
    order: tuple[FenceKey, ...],
) -> str:
    """Rewrite, insert or remove each block of ``order`` whose content changed."""
    for key in order:
        if old.get(key) == new.get(key):
            continue
        present = any(k == key for k, _ in _fences_in(text))
        if present:
            text = _replace_block(text, key, new.get(key))
        elif key in new:
            text = _insert_block(text, key, new[key], order=order)
    return text


def _patch_markdown(existing: str, old: SceneIR, new: SceneIR) -> str:
    """The block-level patch :func:`merge_markdown` describes (unchecked)."""
    headings = list(_SHOT_HEADING_RE.finditer(existing))
    cut = headings[0].start() if headings else len(existing)
    head = existing[:cut]

    # The title line and the meta block live before the first shot.
    if _md_title_line(old) != _md_title_line(new) or not _H1_RE.search(head):
        line = _md_title_line(new)
        head = (
            _H1_RE.sub(line, head, count=1)
            if _H1_RE.search(head)
            else line + "\n\n" + head
        )
    head = _patch_blocks(
        head,
        {_META_FENCE: _md_meta_body(old)},
        {_META_FENCE: _md_meta_body(new)},
        order=(_META_FENCE,),
    )
    if _META_FENCE not in {k for k, _ in _fences_in(head)}:
        title = _H1_RE.search(head)
        at = title.end() if title else 0
        head = (
            head[:at] + "\n\n" + _md_fence(_META_FENCE, _md_meta_body(new)) + head[at:]
        )

    sections: dict[str, tuple[str, str]] = {}
    for i, m in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(existing)
        sections[m.group(1)] = (m.group(0), existing[m.end() : end])
    old_shots = {s.id: s for s in old.timeline}

    out = [head]
    for shot in new.timeline:
        if shot.id not in sections:
            if not out[-1].endswith("\n\n"):
                out[-1] = out[-1].rstrip("\n") + "\n\n"
            out.append(_md_shot_text(shot))
            continue
        heading, body = sections[shot.id]
        before = old_shots[shot.id]
        if before.renderer != shot.renderer:  # keep what the match took after it
            heading = _md_shot_heading(shot) + heading[len(heading.rstrip()) :]
        body = _patch_blocks(
            body, _md_shot_blocks(before), _md_shot_blocks(shot), order=_SHOT_FENCES
        )
        out.append(heading + body)
    return "".join(out).rstrip("\n") + "\n"


def _actions_to_yaml_list(actions: list) -> list[dict]:
    """Convert authoring Action objects back to the markdown-friendly dicts.

    A leaf whose registered kind has a ``write_md`` hook (the core's set and
    tween, a genre's leaves such as ``play``) is written in its short form,
    and so is the ``sequence(delay(start), <leaf>)`` wrapper the parser
    produces for a ``start:`` key. Anything else — a ``parallel`` (``stagger``
    builds one), a ``loop``, a nested ``sequence``, a genre leaf with no md
    form — is written VERBATIM, as the action's own JSON form, which the reader
    validates back through the schema. Nothing is ever dropped: scene.md is
    what the JSON is regenerated from on the next md edit (review-244 S4/S5).

    An action whose kind no loaded genre registered — a bare
    ``ExtensionAction``, or a typed genre action built in Python while its
    genre is not registered — is REFUSED, naming the genre that provides it.
    """
    from an.ir.compose import iter_actions
    from an.ir.schema import (
        DelayAction,
        ExtensionAction,
        SequenceAction,
        unregistered_action_kind,
    )

    out: list[dict] = []
    for action in actions:
        for node in iter_actions(action):
            if action_kind(getattr(node, "kind", None) or "") is None:
                raise unregistered_action_kind(str(getattr(node, "kind", None)))
        # Unwrap sequence(delay(start), leaf) → leaf with start.
        start = None
        leaf = action
        if (
            isinstance(action, SequenceAction)
            and len(action.children) == 2
            and isinstance(action.children[0], DelayAction)
        ):
            start = action.children[0].duration
            leaf = action.children[1]
        if type(leaf) is ExtensionAction:
            leaf = leaf.resolved()
        registered = action_kind(leaf.kind)
        entry = None
        if registered.write_md is not None and (start is None or registered.md_start):
            entry = registered.write_md(leaf)
        if entry is None:
            out.append(_verbatim_action(action))
            continue
        if start is not None:
            entry["start"] = start
        out.append(entry)
    return out


def _verbatim_action(action: Any) -> dict:
    """``action``'s own JSON form, minus the ``name: null`` noise on every node."""

    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: strip(v) for k, v in value.items() if not (k == "name" and v is None)
            }
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    if type(action) is not dict:
        action = action.model_dump(mode="json")
    return strip(action)


# -----------------------------------------------------------------------------
# Disk-level sync
# -----------------------------------------------------------------------------


class SceneValidationError(ValueError):
    """A stored scene document is not a valid scene — named, with its source.

    The underlying :class:`pydantic.ValidationError` is kept as ``__cause__``
    (and as ``.validation_error``) so a caller that reports **per field** —
    ``an.validate_schema`` builds one Finding per error, each with its own
    ``loc`` — does not have to choose between naming the document and naming
    the field.
    """

    def __init__(self, message: str, validation_error=None) -> None:
        super().__init__(message)
        self.validation_error = validation_error


def scene_from_json_doc(doc: dict, *, source: str | Path | None = None) -> SceneIR:
    """Validate a stored scene document, **migrating it first** (an#105).

    Every path from stored bytes to a :class:`~an.ir.schema.SceneIR` goes
    through here — the store (read **and** write), ``sync()``'s two json-wins
    branches, and ``an.validate_schema``, which is a read path too because a
    dict or a JSON string handed to it *is* a stored document. A test walks the
    package's AST and fails on any other one. Before it existed, `migrate()` was called with
    `kind="CharacterDescriptor"` at every call site in the tree and with a
    scene at none of them — so a registered scene migration never ran, and
    because `SceneIR` is ``extra="allow"``, a renamed field would have landed
    as a **silent default** on every document already on disk. Registering a
    migration and never running it is worse than not registering one, because
    the registry reads as a promise.

    Three outcomes, three different repairs, so they get three messages:

    - a version this build reads (at or above ``COMPATIBLE_VERSION``, at or
      below ``SCHEMA_VERSION``) is taken **as-is** when no migration is
      registered for it — that is exactly what ``an/base.py`` promises, and a
      loader that demanded an exact match would refuse every stored project the
      day the version is bumped;
    - a version from the future is refused as *written by a newer build*,
      because nobody will ever register a downgrade;
    - anything else — an old version with no path, or a malformed field — is
      refused naming the document.

    Migration happens **on read, with no write-back**: the document on disk
    keeps its old version until something saves the scene, so a migration must
    stay registered for as long as any project might hold that version. That is
    deliberate — a loader that rewrote every file it opened would turn `an
    validate` into a mutation — but it means the registry only ever grows.

    >>> scene_from_json_doc({"version": "0.1.0", "meta": {"title": "t"}}).meta.title
    't'
    >>> scene_from_json_doc({"version": "0.0.1"}, source="ir/scene.json")
    ... # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    DocumentMigrationError
    """
    where = str(source) if source is not None else "scene document"
    version = doc.get(SCENE_IR.version_field, SCENE_IR.current_version)
    try:
        migrated = migrate(doc, kind=SCENE_IR.name)
    except DocumentMigrationError as e:
        if readable_without_migration(version, SCENE_IR):
            migrated = dict(doc)  # the declared compat window; read it as it is
        elif (v := version_tuple(version)) is not None and v > version_tuple(
            SCENE_IR.current_version
        ):
            raise DocumentMigrationError(
                f"{where}: written by a newer build (schema {version!r}; this build "
                f"is {SCENE_IR.current_version!r}). Upgrade `an` rather than editing "
                "the document — a downgrade migration is never registered."
            ) from e
        elif v is None:
            raise DocumentMigrationError(
                f"{where}: {SCENE_IR.version_field!r} is {version!r}, which is not a "
                "schema version. Repair the field; the document itself may be fine."
            ) from e
        else:
            raise DocumentMigrationError(f"{where}: {e}") from e
    try:
        return SceneIR.model_validate(migrated)
    except ValidationError as e:
        # Named, like the migration refusal above: the common failure is a
        # corrupt FIELD, and a nameless pydantic traceback is exactly what this
        # boundary exists to replace (an#105 review).
        raise SceneValidationError(f"{where}: {e}", e) from e


def sync(project_dir: str | Path) -> SyncResult:
    """Reconcile ``scene.md`` and ``ir/scene.json`` inside a project directory.

    Strategy in v0.1: Markdown is the human SSOT; if both exist, the JSON is
    regenerated from the Markdown unless mtimes show JSON is newer (which the
    user is told never to do — but we warn instead of silently overwriting).
    """
    pdir = Path(project_dir)
    md_path = pdir / "scene.md"
    json_path = pdir / "ir" / "scene.json"
    result = SyncResult()

    md_exists = md_path.exists()
    json_exists = json_path.exists()

    if md_exists and not json_exists:
        scene = markdown_to_ir(_read_text(md_path))
        _write_json(json_path, json.loads(scene.model_dump_json()))
        result.wrote_json = True
    elif json_exists and not md_exists:
        data = json.loads(_read_text(json_path))
        scene = scene_from_json_doc(data, source=json_path)
        _write_text(md_path, ir_to_markdown(scene))
        result.wrote_md = True
    elif md_exists and json_exists:
        # Use the newer file as source of truth. Markdown is the *human* SSOT,
        # but pipeline stages (audio, lip-sync) write rich state into the JSON
        # that the Markdown can't represent — so when JSON is newer, prefer it.
        # Tolerance: skew within 0.5s is treated as "same" (avoid flip-flopping
        # on every load just because of write-order in ScenesStore).
        md_mtime = md_path.stat().st_mtime
        json_mtime = json_path.stat().st_mtime
        skew = json_mtime - md_mtime
        if skew > SYNC_MTIME_TOLERANCE_S:
            data = json.loads(_read_text(json_path))
            scene = scene_from_json_doc(data, source=json_path)
            existing = _read_text(md_path)
            markdown = merge_markdown(existing, scene)  # an#275: keep the author's text
            if markdown != existing:
                _write_text(md_path, markdown)
            # Equalize mtimes so this regen doesn't immediately flip the next
            # sync into "md is newer → regenerate json (losing pipeline state)".
            import os

            os.utime(md_path, (json_mtime, json_mtime))
            result.wrote_md = True
        elif skew < -SYNC_MTIME_TOLERANCE_S:
            scene = markdown_to_ir(_read_text(md_path))
            _write_json(json_path, json.loads(scene.model_dump_json()))
            import os

            os.utime(json_path, (md_mtime, md_mtime))
            result.wrote_json = True
        # else: within tolerance, no rewrite needed.
    return result


_attach_core_md_hooks()
