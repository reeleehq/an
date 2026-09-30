"""Schema and semantic validation for SceneIR documents.

Two layers, called separately so callers can pick how strict to be:

- ``validate_schema`` — Pydantic validation only. Wrong types, missing required
  fields, malformed JSON.
- ``validate_semantic`` — cross-field checks. Unknown asset references,
  zero-duration shots, voice refs missing from a voices store.

Layout-overlap checks (boxes off-screen, text behind sprites) live in
``an.verify.layout``, not here, because they need a render context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from pydantic import ValidationError

from an.base import AUTHORABLE_PROPERTIES, TRANSFORM_PROPERTIES
from an.characters.play import (
    PRESET_SOURCE,
    Facing,
    TurnResolution,
    art_exists_for,
    facing_at,
    play_extent_for,
    play_problems,
    play_source,
    preset_moved_node,
    preset_play_span,
    resolve_turns,
)
from an.audio.effects import VoiceEffectError, voice_effects
from an.audio.voices import speaker_voice_ref
from an.characters.schema import DFLT_VIEW, VIEW_CHANNEL, CharacterDescriptor
from an.expression.binding import expression_problems
from an.ir.camera import CAMERA_MOVES, CameraError, camera_keys
from an.ir.compose import flatten
from an.ir.migrate import DocumentMigrationError, migrate
from an.ir.sync import SceneValidationError, scene_from_json_doc
from an.ir.schema import SceneIR


Severity = Literal["error", "warning", "info"]


@dataclass(slots=True)
class ValidationFinding:
    """A single validation issue with a path into the IR."""

    severity: Severity
    ir_path: str
    description: str


@dataclass(slots=True)
class ValidationReport:
    """Result of running one or more validators.

    ``passed`` is True iff there are no error-severity findings.
    """

    passed: bool = True
    findings: list[ValidationFinding] = field(default_factory=list)

    def add(self, severity: Severity, ir_path: str, description: str) -> None:
        self.findings.append(
            ValidationFinding(
                severity=severity, ir_path=ir_path, description=description
            )
        )
        if severity == "error":
            self.passed = False

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        merged = ValidationReport(passed=self.passed and other.passed)
        merged.findings = self.findings + other.findings
        return merged


# -----------------------------------------------------------------------------
# Schema layer
# -----------------------------------------------------------------------------


def validate_schema(doc: Any) -> ValidationReport:
    """Validate that ``doc`` (dict, JSON string, or SceneIR) conforms to the schema.

    >>> validate_schema({"meta": {"title": "x"}, "timeline": []}).passed
    True
    >>> r = validate_schema({"meta": {"title": "x"}, "timeline": [{"id": "s", "duration": "not-a-number"}]})
    >>> r.passed
    False
    """
    report = ValidationReport()
    try:
        if isinstance(doc, SceneIR):
            return report
        # A dict or a JSON string is a STORED document, so it is migrated first
        # (an#105 review): without this, "validate before you spend" told an
        # agent a stale project was clean, because `extra="allow"` accepts the
        # pre-migration shape and defaults the new fields.
        raw = json.loads(doc) if isinstance(doc, str) else doc
        if not isinstance(raw, dict):
            report.add(
                "error",
                "<root>",
                f"a scene document must be an object, not {type(raw).__name__}",
            )
            return report
        scene_from_json_doc(raw)
    except DocumentMigrationError as e:
        report.add("error", "version", str(e))
    except SceneValidationError as e:
        # Per FIELD, not one finding for the document: `Finding.ir_path` is what
        # routes a fix to the layer that can make it (CLAUDE.md pillar 10).
        underlying = e.validation_error
        if underlying is None:
            report.add("error", "<root>", str(e))
        else:
            for err in underlying.errors():
                loc = "/".join(str(x) for x in err.get("loc", ()))
                report.add("error", loc or "<root>", err.get("msg", "validation error"))
    except ValidationError as e:
        for err in e.errors():
            loc = "/".join(str(x) for x in err.get("loc", ()))
            report.add("error", loc or "<root>", err.get("msg", "validation error"))
    return report


# -----------------------------------------------------------------------------
# Semantic layer
# -----------------------------------------------------------------------------


#: Camera moves the renderer implements. `hold` is a real no-op.
#:
#: **Derived, not duplicated.** This was a hand-maintained frozenset reconciled
#: with the compiler's table by a test — which works, and is not what "a move
#: that validates cannot then raise" means; that means ONE table (an#109
#: review, H-1). It moved to `an.ir.camera`, which is the IR layer, so validate
#: can import it without depending on an adapter.
_RENDERABLE_CAMERA_MOVES: frozenset[str] = frozenset(CAMERA_MOVES)

#: Entity kinds the cutout renderer draws. `voice` is legitimately
#: not drawable — they configure the render rather than appearing in it.
#: an#108: `prop` moved from "declared by the IR but not drawn" to drawn.
#: validate's verdict IS compile's, so this set and the compiler's
#: entity dispatch are pinned equal by test — a validator that passes a
#: scene the compiler refuses is worse than no validator, because it is
#: trusted.
_DRAWABLE_ENTITY_KINDS: frozenset[str] = frozenset({"character", "environment", "prop"})
_CONFIGURING_ENTITY_KINDS: frozenset[str] = frozenset({"voice"})

#: Any property outside the transform vocabulary on a set/tween names a swap
#: SET, which must be declared by the target entity's descriptor (an#87). The
#: vocabulary itself is the shared SSOT in ``an.base`` (importable by every
#: layer); the compiler's rest-value table is asserted equal to it by test.
#:
#: `AUTHORABLE_*`, not `TRANSFORM_*`: `tint` is what an author writes and the
#: compiler expands into three numeric channels, so it is legal input that
#: never appears in a compiled document (an#62). Reading the compiled set here
#: would classify a `tint` tween as a swap-set name and refuse it.
_TRANSFORM_PROPERTIES: frozenset[str] = AUTHORABLE_PROPERTIES

#: The swap sets a descriptor-less (procedural) rig supports — declared as
#: data on its drawn mouth by the compiler (`PROCEDURAL_MOUTH_SETS`). This
#: layer cannot import the adapter, so the value is duplicated here and
#: pinned against the compiler's constant by ``tests/test_swap_channels.py``.
_PROCEDURAL_SWAP_SETS: frozenset[str] = frozenset({"viseme"})


#: Entity kind → (the mall store holding its rig, the descriptor `kind` tag
#: that store's documents carry). `environment` and `voice` are absent because
#: neither has a rig to declare asset sets on.
RIG_STORES: dict[str, tuple[str, str]] = {
    "character": ("characters", "CharacterDescriptor"),
    "prop": ("props", "PropDescriptor"),
}


def _rig_document(entity, stores: Mapping[str, Any]) -> dict | None:
    """The MIGRATED descriptor behind ``entity``, or ``None``.

    Migrated because that is how the compiler reads it: every committed
    pre-0.3.0 character descriptor has no `asset_sets` on disk (0.1.0 carries
    `viseme_map`; `eyelid` is migration-seeded), so the raw dict would refuse
    swaps the compiler accepts.

    Keyed on the entity's KIND rather than on "is it a character", so a prop's
    descriptor is found in the props store (an#108). It also refuses a
    document of the wrong kind in the right store — a `CharacterDescriptor`
    under `assets/props/` is not a prop, and the compiler says so too.
    """
    try:
        store_name, want_kind = RIG_STORES[entity.kind]
    except KeyError:
        return None
    store = stores.get(store_name)
    if store is None:
        return None
    try:
        candidate = store[entity.ref]
    except (KeyError, TypeError):
        return None
    if isinstance(candidate, dict) and candidate.get("kind") == want_kind:
        return migrate(dict(candidate), kind=want_kind)
    return None


def _path_document_problem(entity, store) -> "str | None | bool":
    """For a prop entity: ``False`` when its document is not a path at all,
    ``None`` when it is a valid path, else the reason it is not (an#160)."""
    try:
        doc = store[entity.ref]
    except (KeyError, TypeError):
        return False
    if not isinstance(doc, dict) or doc.get("kind") != "PathDescriptor":
        return False
    from an.paths import resolve_path  # the compiler's own resolver

    try:
        resolve_path(doc, entity.overrides)
    except ValueError as err:
        return (
            f"path {entity.ref!r} (with this entity's overrides) is not a valid "
            f"PathDescriptor — rendering this shot raises: {err}"
        )
    return None


def _check_text_blocks(
    shot,
    path: str,
    report: "ValidationReport",
    stores: Mapping[str, Any],
    *,
    width: int,
    height: int,
) -> set[str]:
    """Typeset every text block the way the compiler will, and report what it
    would refuse (an#155): a font that is not a file, a glyph the face lacks,
    an override the schema does not know — and an authored target inside a
    block that names a unit the block does not build (``word_9`` of a
    three-word title, or any ``word_*`` of a ``unit: glyph`` block).

    Returns the ids of the entities that ARE text blocks, so the entity loop
    does not also judge them as rigs. Needs the props store; without it nothing
    runs (an absent store means the check did not run, never that it failed).
    """
    props = stores.get("props")
    if props is None:
        return set()
    from an.text import (
        font_base_dir,
        layout_text,
        resolve_text,
        text_entity_problem,
    )

    text_ids: set[str] = set()
    built: dict[str, set[str]] = {}
    for j, entity in enumerate(shot.entities):
        if entity.kind != "prop":
            continue
        try:
            doc = props[entity.ref]
        except (KeyError, TypeError):
            continue
        if not isinstance(doc, dict) or doc.get("kind") != "TextDescriptor":
            continue
        if entity.id in text_ids:
            report.add(
                "error",
                f"{path}/entities/{j}",
                f"two text blocks share the id {entity.id!r} — compiling this "
                "shot raises",
            )
        text_ids.add(entity.id)
        try:
            desc = resolve_text(doc, entity.overrides)
            lay = layout_text(
                desc,
                width=width,
                height=height,
                base_dir=font_base_dir(props, entity.ref),
            )
        except ValueError as err:
            report.add(
                "error",
                f"{path}/entities/{j}",
                f"text {entity.ref!r} (with this entity's overrides) cannot be "
                f"set — rendering this shot raises: {err}",
            )
            continue
        problem = text_entity_problem(entity, desc)
        others = {e.id for e in shot.entities if e is not entity}
        if problem is None and desc.layer == "overlay" and entity.id in others:
            problem = (
                f"overlay text {entity.id!r} shares its id with another entity; "
                "the runtime indexes both layers by path"
            )
        if problem is not None:
            report.add(
                "error",
                f"{path}/entities/{j}",
                f"{problem} — compiling this shot raises",
            )
        built[entity.id] = {f"{entity.id}/{u.name}" for u in lay.units}
    for k, action in enumerate(shot.actions):
        for flat in flatten(action):
            target = getattr(flat.action, "target", "") or ""
            root = target.split("/", 1)[0]
            if "/" in target and root in built and target not in built[root]:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"{target!r} is not a unit of text block {root!r} (it builds "
                    f"{sorted(built[root])}) — compiling this shot raises.",
                )
    return text_ids


def _check_trim_targets(
    shot, path: str, report: "ValidationReport", stores: Mapping[str, Any]
) -> None:
    """``trim_start``/``trim_end`` may only target a stroked path's node — the
    entity itself — which the compiler enforces too (an#160).

    Without the props store nothing says which props are paths, so only the
    certain refusals run: a target that is not a PROP entity, or a sub-node,
    is never a path, whichever stores were supplied (an#160 review, M1 — a
    trim on a character used to be refused as a non-transform property, and
    joining the numeric vocabulary must not quietly lose that).
    """
    from an.base import TRIM_PROPERTIES

    props = stores.get("props")
    prop_ids = {e.id for e in shot.entities if e.kind == "prop"}
    if props is None:
        path_ids = prop_ids  # unknowable without the store: give the benefit
    else:
        path_ids = {
            e.id
            for e in shot.entities
            if e.kind == "prop" and _path_document_problem(e, props) is not False
        }
    undashed_ids: set[str] = set()
    if props is not None:
        from an.paths import resolve_path

        for e in shot.entities:
            if e.id in path_ids and e.kind == "prop":
                try:
                    if resolve_path(props[e.ref], e.overrides).dash is None:
                        undashed_ids.add(e.id)
                except (ValueError, KeyError, TypeError):
                    pass  # an invalid path is reported by its own check
    for k, action in enumerate(shot.actions):
        for flat in flatten(action):
            prop = getattr(flat.action, "property", None)
            if prop not in TRIM_PROPERTIES:
                continue
            target = getattr(flat.action, "target", "") or ""
            if target not in path_ids:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"{prop!r} targets {target!r}, which is not a stroked path "
                    f"(paths in this shot: {sorted(path_ids) or 'none'}) — "
                    "compiling this shot raises.",
                )
                continue
            if prop == "dash_offset" and target in undashed_ids:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"'dash_offset' targets {target!r}, a path with no dash "
                    "pattern — an offset would draw nothing and compiling this "
                    "shot raises. Give the path a `dash` length.",
                )


def _check_swap_references(
    shot, path: str, report: "ValidationReport", stores: Mapping[str, Any]
) -> None:
    """A set/tween on a non-transform property must name a declared asset set
    and key of its target entity's descriptor, and a `play` must resolve
    against that descriptor's animations — checked HERE, before the author
    pays for TTS or a Chromium launch, because compile raises on both
    (an#87, an#7). Same charter as `_check_renderable`; needs the store, so
    it runs from `validate_semantic`'s shot loop — and ONLY then: with
    no stores neither check runs, so a bare `validate_semantic(scene)` passes
    a play the compiler will refuse.

    ``stores`` is keyed by MALL NAME, not by entity kind, and `RIG_STORES`
    maps between them — because an#108 gave props the same rig machinery, and
    a check that only knows how to find a *character's* descriptor reports
    "no descriptor declaring asset sets" for a lamp whose descriptor is right
    there in the props store.

    Descriptor-less (procedural) entities get a carve-out for `viseme` — the
    compiler validates its codes against the drawn-mouth shapes — and an
    error for anything else, matching the compiler's verdicts.
    """
    if not stores:
        return
    # PER-KIND, not per-call. an#108's first pass changed the gate from
    # "characters store absent → skip" to "no stores at all → skip", which made
    # `validate_semantic(scene, available_characters=X)` — the signature every
    # caller outside this repo has — report EVERY prop swap as
    # "has no descriptor declaring asset sets" on a scene that compiles fine.
    # A store that was not supplied means the check did not run for that kind;
    # it never means the descriptor is missing.
    rigs = {e.id: e for e in shot.entities if e.kind in RIG_STORES}
    #: Entities whose rig store was not supplied. Their checks are SKIPPED, not
    #: failed: "no store" and "no descriptor" are different facts, and reporting
    #: the first as the second is how a caller who passes only characters gets
    #: an error on every prop swap in a scene that compiles fine.
    unchecked = {
        eid for eid, e in rigs.items() if stores.get(RIG_STORES[e.kind][0]) is None
    }
    # The expression and dialogue-emotion checks below are CHARACTER-only:
    # a prop has no face.
    refs_by_entity = {e.id: e.ref for e in shot.entities if e.kind == "character"}
    available_characters = stores.get("characters")
    # `play` (an#7): resolved against the target entity's MIGRATED descriptor
    # by `an.characters.play` — the SAME code the compiler resolves with, so
    # validate's verdict is compile's (an unknown bone property, a bone with
    # no slot of its own, art missing for a frame, a face slot suppressed by
    # `face_overlay=false` all used to pass here and raise there). Art is
    # checked when the store has a filesystem root; a dict store assumes
    # presence, as the compiler's part probe does.
    #
    # A name the descriptor does not declare — or any name on an entity with
    # no descriptor — falls back to a motion preset (an#166), decided by the
    # same `play_problems`. A preset additionally needs the node it moves to
    # be BUILT, which only the compiler's scene builder knows: the stage is
    # built once per shot, lazily, and only when a preset play is present.
    stage_nodes: set[str] | None = None
    stage_tried = False

    def play_descriptor(entity_id: str) -> CharacterDescriptor | None:
        # `play` resolves against a CHARACTER's animations. A prop has an
        # `animations` field so the shared rig builder can read the same
        # attribute on either document, but nothing seeds it and no author
        # tool writes one — so a `play` on a prop resolves presets only,
        # exactly as the compiler (which reads character descriptors
        # alone) resolves it.
        entity = rigs.get(entity_id)
        doc = _rig_document(entity, stores) if entity is not None else None
        is_character = entity is not None and entity.kind == "character"
        return (
            CharacterDescriptor.model_validate(doc)
            if doc is not None and is_character
            else None
        )

    def extent_descriptor(entity_id: str) -> CharacterDescriptor | None:
        # Only to place a `sequence`'s later siblings, exactly as the compiler
        # does; a descriptor that will not even parse is reported by the loop
        # below, so it must not raise from inside `flatten`.
        if entity_id in unchecked:
            return None
        try:
            return play_descriptor(entity_id)
        except ValidationError:
            return None

    play_extent = play_extent_for(extent_descriptor)
    for k, action in enumerate(shot.actions):
        for flat in flatten(action, play_extent=play_extent):
            leaf = flat.action
            if getattr(leaf, "kind", None) != "play":
                continue
            entity_id = (getattr(leaf, "target", "") or "").split("/", 1)[0]
            if entity_id in unchecked:
                continue
            entity = rigs.get(entity_id)
            is_character = entity is not None and entity.kind == "character"
            desc = play_descriptor(entity_id)
            problems = play_problems(
                desc,
                leaf.animation,
                art_exists=(
                    art_exists_for(stores.get("characters"), entity.ref)
                    if is_character
                    else None
                ),
                args=leaf.args,
                duration=leaf.duration,
                speed=leaf.speed,
                loop=leaf.loop,
            )
            if not problems and play_source(desc, leaf.animation) == PRESET_SOURCE:
                if not stage_tried:
                    stage_tried = True
                    stage_nodes, why = _built_node_paths(shot, stores)
                    if why is not None:
                        # Said out loud, never a silent pass: validate could
                        # not see what compile will look the node up in.
                        report.add(
                            "warning",
                            f"{path}/actions/{k}",
                            "the node a motion-preset `play` moves was NOT "
                            f"checked: the shot's stage did not build ({why}).",
                        )
                end = flat.start + preset_play_span(leaf)
                if end > shot.duration + 1e-9:
                    report.add(
                        "warning",
                        f"{path}/actions/{k}",
                        f"`play` of motion preset {leaf.animation!r} on "
                        f"{entity_id!r} runs to t={end:g}s, past the shot's end "
                        f"({shot.duration:g}s): the rest of the move never shows.",
                    )
                if stage_nodes is not None:
                    node = preset_moved_node(leaf.target, leaf.animation, leaf.args)
                    if node not in stage_nodes:
                        built = sorted(
                            p for p in stage_nodes if p.split("/")[0] == entity_id
                        )
                        problems = [
                            f"motion preset {leaf.animation!r} moves node {node!r}, "
                            f"which the built scene does not carry (built: {built})"
                        ]
            for problem in problems:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"`play` of {leaf.animation!r} on {entity_id!r} cannot "
                    f"resolve: {problem} — compiling this shot raises.",
                )
    # `expression` (an#98) and the dialogue `[emotion]` sugar resolve through
    # `an.expression.binding.expression_problems` — the SAME function the face
    # solver raises with. An unknown preset used to be silence.
    for k, action in enumerate(shot.actions):
        for flat in flatten(action):
            leaf = flat.action
            if getattr(leaf, "kind", None) != "expression":
                continue
            entity_id = (getattr(leaf, "target", "") or "").split("/", 1)[0]
            if entity_id not in refs_by_entity:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"`expression` targets {entity_id!r}, which is not a character "
                    f"entity of this shot (entities: {sorted(refs_by_entity) or 'none'}) "
                    "— it would compile to nothing.",
                )
                continue
            desc = _descriptor_for(refs_by_entity.get(entity_id), available_characters)
            for problem in expression_problems(
                desc, preset=leaf.preset, axes=leaf.axes, who=entity_id
            ):
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"`expression` on {entity_id!r} cannot resolve: {problem} — "
                    "compiling this shot raises.",
                )
    for j, line in enumerate(shot.dialogue):
        emotion = (line.emotion or "").strip().lower()
        if not emotion:
            continue
        desc = _descriptor_for(refs_by_entity.get(line.speaker), available_characters)
        for problem in expression_problems(None, preset=emotion, who=line.speaker):
            report.add("error", f"{path}/dialogue/{j}/emotion", problem)
        if desc is not None and not desc.face_overlay:
            report.add(
                "warning",
                f"{path}/dialogue/{j}/emotion",
                f"{line.speaker!r} has its face baked into the head art "
                "(face_overlay: false), so the [emotion] on this line moves "
                "nothing; the audio still plays.",
            )
    # Flattened, like the compiler: the documented `start:` idiom wraps every
    # leaf in a `sequence`, so walking only top-level actions would miss the
    # common case (an#87 review) — an authoring-time gate that only sees the
    # top level is a gate with a hole in it.
    leaves = [
        (k, flat.action)
        for k, action in enumerate(shot.actions)
        for flat in flatten(action)
    ]
    for k, action in leaves:
        prop = getattr(action, "property", None)
        if prop is None or prop in _TRANSFORM_PROPERTIES:
            continue
        target = getattr(action, "target", "") or ""
        entity_id = target.split("/", 1)[0]
        if entity_id in unchecked:
            continue
        entity = rigs.get(entity_id)
        desc = _rig_document(entity, stores) if entity is not None else None
        if desc is None:
            # The procedural carve-out is a CHARACTER's drawn mouth; a prop
            # with no rig document (a stroked path, an#160) has no swap set at
            # all, which is what the compiler says too.
            is_prop = entity is not None and entity.kind != "character"
            if prop not in _PROCEDURAL_SWAP_SETS or is_prop:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"property {prop!r} is not a transform, and "
                    f"{entity_id!r} has no descriptor declaring asset sets — "
                    "compiling this shot raises. Procedural rigs support "
                    f"exactly {sorted(_PROCEDURAL_SWAP_SETS)} on their mouth.",
                )
            continue
        declared = desc.get("asset_sets") or {}
        if prop not in declared:
            report.add(
                "error",
                f"{path}/actions/{k}",
                f"property {prop!r} names no declared asset set of "
                f"{entity_id!r} (it has: {sorted(declared)}) — compiling "
                "this shot raises."
                + (
                    " A character made before an#197 has no views: "
                    "`an character add-views` draws them."
                    if prop == VIEW_CHANNEL and entity.kind == "character"
                    else ""
                ),
            )
            continue
        keys = declared.get(prop) or {}
        # …and the ART has to be there. The compiler registers only the
        # attachments whose files resolve and then refuses a key whose art is
        # missing, so a key that is DECLARED but undrawable passed validate and
        # raised at compile — with `strict_assets` either way (an#108 review,
        # H3). Same rule the rig builder's probe uses: a store with no
        # filesystem root can answer nothing, so it must assume presence rather
        # than drop every key.
        art_exists = art_exists_for(stores.get(RIG_STORES[entity.kind][0]), entity.ref)
        if art_exists is not None:
            skin = (desc.get("skins") or {}).get("default") or {}
            slots = skin.get("slots") or {}
            drawable = {
                key
                for key, attachment_name in keys.items()
                if any(
                    art_exists(att["path"])
                    for atts in slots.values()
                    if attachment_name in atts
                    for att in (atts[attachment_name],)
                    if isinstance(att, dict) and att.get("path")
                )
            }
            keys = {k_: v_ for k_, v_ in keys.items() if k_ in drawable}
        values = [
            v
            for v in (
                getattr(action, "value", None),
                getattr(action, "from_value", None),
                getattr(action, "to_value", None),
            )
            if v is not None
        ]
        for v in values:
            if not isinstance(v, str) or v not in keys:
                report.add(
                    "error",
                    f"{path}/actions/{k}",
                    f"{v!r} is not a declared key of {entity_id!r}'s "
                    f"{prop!r} set (it has: {sorted(keys)}) — compiling "
                    "this shot raises.",
                )


def _turn_resolution(
    shot, stores: Mapping[str, Any]
) -> tuple[TurnResolution, list[int]] | None:
    """The shot's flat timeline with its turns resolved the way the compiler
    resolves them (:func:`an.characters.play.resolve_turns`, an#203), and the
    top-level action index each flat came from. ``None`` without a characters
    store — the check did not run, which is not the same as passing.

    The rest pose is the identity: validate builds no stage, and the SIGN of
    ``scale_x`` — all a facing is — does not depend on the rest's size.
    """
    if stores.get("characters") is None:
        return None
    rigs = {e.id: e for e in shot.entities if e.kind == "character"}

    def descriptor_of(entity_id: str) -> CharacterDescriptor | None:
        entity = rigs.get(entity_id)
        doc = _rig_document(entity, stores) if entity is not None else None
        try:
            return CharacterDescriptor.model_validate(doc) if doc else None
        except ValidationError:
            return None  # reported by the play check

    extent = play_extent_for(descriptor_of)
    origin: list[int] = []
    flats = []
    for k, action in enumerate(shot.actions):
        for flat in flatten(action, play_extent=extent):
            flats.append(flat)
            origin.append(k)
    resolution = resolve_turns(
        flats,
        descriptor_of=descriptor_of,
        rest_of=lambda _p: {"x": 0.0, "y": 0.0, "rotation": 0.0,
                            "scale_x": 1.0, "scale_y": 1.0, "alpha": 1.0},
    )
    return resolution, origin


def _check_turns(
    shot, path: str, report: "ValidationReport", resolved
) -> None:
    """A ``turn`` whose declared ``from_direction`` contradicts the side the
    timeline before it left the character facing (an#203): the compiler
    keeps what the author wrote, so the character flips to the other side
    before it squashes — a visible jump."""
    if resolved is None:
        return
    resolution, origin = resolved
    for turn in resolution.turns:
        if not turn.contradicted:
            continue
        report.add(
            "warning",
            f"{path}/actions/{origin[turn.index]}",
            f"`turn` on {turn.entity!r} at t={turn.start:g}s declares "
            f"from_direction {turn.declared!r}, but the timeline before it left "
            f"{turn.entity!r} facing {turn.before.direction!r}"
            + (f" in its {turn.before.view!r} view" if turn.before.view else "")
            + ", so it jumps to the other side before it turns. Drop "
            "`from_direction`: a turn infers it from the timeline.",
        )


def _check_view_continuity(
    scene: SceneIR, report: "ValidationReport", resolved: list
) -> None:
    """A character that ends one shot turned (a view other than the default,
    or facing left) and appears in the NEXT shot starts that shot at its rest
    — shots are independent by design (each compiles alone; the per-shot
    archive and `render_project` depend on it), so a view does not carry
    across a cut (an#203). Said as a warning, with the one line that carries
    it on; the next shot setting the view (or ``scale_x``) at t=0 is taken as
    the author's decision either way. ``resolved`` is
    :func:`_turn_resolution` per shot.
    """
    previous: dict[str, tuple[str, Facing]] = {}
    for i, (shot, shot_resolved) in enumerate(zip(scene.timeline, resolved)):
        if shot_resolved is None:
            return  # no characters store: the check did not run
        events = shot_resolved[0].events
        ids = [e.id for e in shot.entities if e.kind == "character"]
        for j, entity_id in enumerate(ids):
            if entity_id not in previous:
                continue
            prev_shot, ended = previous[entity_id]
            start = facing_at(events, entity_id, 0.0)
            turned_view = ended.view not in (None, DFLT_VIEW) and start.view is None
            turned_left = ended.direction == "left" and start.direction is None
            if not (turned_view or turned_left):
                continue
            state = " ".join(
                bit
                for bit in (
                    f"in its {ended.view!r} view" if turned_view else "",
                    "facing left" if turned_left else "",
                )
                if bit
            )
            fix = " and ".join(
                bit
                for bit in (
                    f"`{{kind: set, target: {entity_id}, property: view, value: "
                    f"{ended.view}, at: 0}}`"
                    if turned_view
                    else "",
                    "a negative `scale_x` set at 0" if turned_left else "",
                )
                if bit
            )
            report.add(
                "warning",
                f"timeline/{i}/entities",
                f"{entity_id!r} ends shot {prev_shot!r} {state}, and shot "
                f"{shot.id!r} starts it at its rest — a view does not carry "
                f"across a cut (each shot compiles alone). To continue the "
                f"turn, open shot {shot.id!r} with {fix}; to reset it on "
                "purpose, set the view there anyway.",
            )
        previous = {
            e: (shot.id, facing_at(events, e, float(shot.duration)))
            for e in ids
        }


#: Leaf kinds whose ``target`` is a NODE path the runtime animates. `play` and
#: `expression` target an entity and are resolved by their own checks above.
_NODE_TARGETING_KINDS = frozenset({"set", "tween"})


def _check_action_targets(
    shot,
    path: str,
    report: "ValidationReport",
    stores: Mapping[str, Any],
    *,
    resolution: tuple[int | None, int | None] | None = None,
    skip: frozenset[str] = frozenset(),
) -> None:
    """Every `set`/`tween` target must be a node the compiler BUILDS (an#193).

    Resolved against :func:`_built_node_paths` — the compiler's own stage
    builder, the one a preset `play` is checked against (an#166) — so the rig
    is never restated here; the message is the compiler's
    (:func:`an.adapters.cutout.compile.unknown_target_message`), with "did you
    mean" suggestions from the real paths. A target on an entity whose store
    was not supplied is skipped: without it a stand-in (the placeholder rig,
    the default backdrop) would be built, and its paths are not the asset's.
    ``skip`` names entities another check owns (text blocks: their units are
    checked by `_check_text_blocks`, at the scene's resolution). The runtime's
    camera node (``root``) is a legitimate target, as the compiler says.
    """
    if not stores or shot.renderer != "cutout":
        return
    from an.adapters.cutout.compile import CAMERA_NODE, unknown_target_message

    store_of = {kind: name for kind, (name, _doc) in RIG_STORES.items()}
    store_of["environment"] = "environments"  # its planes are nodes too
    unchecked = {
        e.id
        for e in shot.entities
        if e.kind in store_of and stores.get(store_of[e.kind]) is None
    } | set(skip)
    leaves = [
        (k, flat.action)
        for k, action in enumerate(shot.actions)
        for flat in flatten(action)
        if getattr(flat.action, "kind", None) in _NODE_TARGETING_KINDS
    ]
    targets = [
        (k, a.target)
        for k, a in leaves
        if (a.target or "").split("/", 1)[0] not in unchecked
        and a.target != CAMERA_NODE
    ]
    if not targets:
        return
    built, why = _built_node_paths(shot, stores, resolution=resolution)
    if built is None:
        report.add(
            "warning",
            f"{path}/entities",
            f"animation targets were NOT checked: the shot's stage did not build ({why}).",
        )
        return
    for k, target in targets:
        if target not in built:
            report.add(
                "error",
                f"{path}/actions/{k}",
                f"{unknown_target_message(target, built)} — rendering this shot raises.",
            )


def _built_node_paths(
    shot,
    stores: Mapping[str, Any],
    *,
    resolution: tuple[int | None, int | None] | None = None,
) -> tuple[set[str] | None, str | None]:
    """``(node paths, None)`` — every node path the cutout compiler builds for
    ``shot``'s STAGE (its entities; no actions), from the supplied stores — or
    ``(None, why)`` when the stage does not build. Read off the compiler rather
    than restated: a preset play's node is checked against exactly what compile
    will look it up in (an#166). The failure is RETURNED so the caller reports
    that the check was skipped; swallowing it would be validate saying "fine"
    about a play it never looked at."""
    import warnings

    from an.motion import stage_poses

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # the render's warnings, not validate's
            width, height = resolution or (None, None)
            return (
                set(stage_poses(shot, mall=stores, width=width, height=height)),
                None,
            )
    except Exception as e:  # noqa: BLE001 — reported by the caller, by name
        return None, f"{type(e).__name__}: {e}"


def _descriptor_for(ref, available_characters) -> CharacterDescriptor | None:
    """The MIGRATED descriptor a store holds for ``ref``, or ``None``."""
    if ref is None or available_characters is None:
        return None
    try:
        candidate = available_characters[ref]
    except (KeyError, TypeError):
        return None
    if isinstance(candidate, dict) and candidate.get("kind") == "CharacterDescriptor":
        return CharacterDescriptor.model_validate(
            migrate(dict(candidate), kind="CharacterDescriptor")
        )
    return None


def _check_voice_effects(
    report: "ValidationReport", path: str, k: int, voice_ref: str, voices
) -> None:
    """An unknown or out-of-range ``effects`` entry on a line's voice is an
    error — rendering would raise the same ``VoiceEffectError``."""
    try:
        voice_effects({"voices": voices}, voice_ref)
    except VoiceEffectError as exc:
        report.add(
            "error", f"{path}/dialogue/{k}/voice_ref", f"voice {voice_ref!r}: {exc}"
        )


def _check_camera(shot, path: str, report: "ValidationReport", stores=None) -> None:
    """Every way a camera can fail to render, reported for free (an#109).

    The rule is `_check_renderable`'s: **error wherever the pipeline raises**,
    so validate's verdict and the compiler's agree — and it is kept by calling
    the compiler's own resolver rather than restating its rules. The one
    finding that is NOT a raise is the last, and it is a warning: too few keys
    is a pose rather than a move, which renders as if the camera were absent.
    Nothing breaks, so nothing fails; the author still wrote a camera block
    that does nothing, so it is still worth saying.

    ``width``/``height`` are 1 because nothing here reads the resolved
    distance — only whether resolving RAISES. Passing the real canvas would
    make the check depend on a resolution the IR layer does not have.
    """
    camera = shot.camera
    if camera is None:
        return
    # Every refusal, from the resolver the COMPILER uses. Not a second copy of
    # its rules: `camera_keys` raises exactly where compiling raises, so this
    # cannot drift from what it predicts (an#109 review, H-1).
    try:
        keys = camera_keys(shot, width=1, height=1)
    except CameraError as e:
        report.add("error", path, f"{e} Rendering this shot raises.")
        return
    if camera.keys is not None and len(keys) < 2:
        report.add(
            "warning",
            f"{path}/keys",
            f"{len(keys)} camera key(s) is a pose, not a move: the compiler "
            "needs two to interpolate between, so this renders as if the "
            "camera were absent. Add a second key, or remove the camera.",
        )
    _check_flat_pan(shot, keys, path, report, stores)


def _check_flat_pan(shot, keys, path: str, report: "ValidationReport", stores) -> None:
    """A camera TRANSLATION on a stage with nothing to parallax (an#111).

    A warning, not an error: "pan a single-plane stage" is a legitimate if
    unexciting request, and the render is correct — the whole picture slides.
    But it is also exactly what a FLATTENED parallax looks like, which is the
    null hypothesis the pan measurement exists to exclude, so an author who
    meant depth should be told the stage has none.

    Silent when no store was supplied: "no store" and "no planes" are
    different facts, and reporting the first as the second is the mistake
    an#108's review caught on the prop path.
    """
    # A TRANSLATION, not merely an off-centre camera. The first version asked
    # whether any key had a non-zero x or y, which warns on a pure zoom held at
    # an offset — a scene with no translation at all (an#111 review, M3).
    xs = {round(float(k.x), 9) for k in keys}
    ys = {round(float(k.y), 9) for k in keys}
    if len(xs) < 2 and len(ys) < 2:
        return  # the camera does not translate; a zoom has nothing to parallax
    env_store = (stores or {}).get("environments")
    if env_store is None:
        return
    from an.environments import ENVIRONMENT_DOCUMENT_KIND, EnvironmentDescriptor

    factors: list[tuple[float, float]] = []
    for entity in shot.entities:
        if entity.kind != "environment":
            continue
        try:
            raw = env_store[entity.ref]
        except (KeyError, TypeError):
            continue
        if (
            not isinstance(raw, dict)
            or raw.get("kind") != ENVIRONMENT_DOCUMENT_KIND.name
        ):
            continue
        try:
            # MIGRATED, as the compiler reads it — a pre-flight that validates
            # a document differently from the thing it predicts is its own
            # defect, which is the rule `_rig_document` already follows.
            env = EnvironmentDescriptor.model_validate(
                migrate(dict(raw), kind=ENVIRONMENT_DOCUMENT_KIND.name)
            )
        except Exception:  # noqa: BLE001 — a malformed descriptor is another check's
            continue
        # `factors()`, not `depth`: `parallax` OVERRIDES `depth`, so reading the
        # scalar warns on a stage that parallaxes by override and stays silent
        # on one that is flat by override — both backwards (an#111 review, M3).
        factors.extend(p.factors() for p in env.planes)
    if factors and len({(round(fx, 9), round(fy, 9)) for fx, fy in factors}) > 1:
        return  # a real multiplane stage
    report.add(
        "warning",
        f"{path}",
        "the camera translates over a stage with "
        + (
            f"{len(factors)} plane(s) all moving at the same rate"
            if factors
            else "no declared planes"
        )
        + ". The render is correct — the whole picture slides — but it is also "
        "what a flattened parallax looks like. If depth was the point, give the "
        "environment `planes` with different `depth` values (an#110).",
    )


def _check_renderable(shot, path: str, report: "ValidationReport", stores=None) -> None:
    """Report, at validate time, what compile and render will refuse.

    This is where these checks belong. The compiler and the runtime both refuse
    these scenes now, which is right — but they refuse them *after* the author
    has paid for TTS synthesis or a Chromium launch, and `an validate` is the
    free pre-flight that `iterate()` also runs after applying a model's patches.
    A validator that says "passed" about a scene that cannot render is worse
    than no validator, because it is trusted.

    Severity is `error` wherever the pipeline raises, so validate's verdict and
    the pipeline's verdict agree. A validator that disagrees with the thing it
    predicts is its own defect.
    """
    if shot.camera is not None:
        _check_camera(shot, f"{path}/camera", report, stores=stores)

    for j, entity in enumerate(shot.entities):
        if (
            entity.kind not in _DRAWABLE_ENTITY_KINDS
            and entity.kind not in _CONFIGURING_ENTITY_KINDS
        ):
            report.add(
                "error",
                f"{path}/entities/{j}",
                f"entity kind {entity.kind!r} is declared by the IR but not drawn "
                "by the cutout renderer. Rendering this shot raises.",
            )

    if shot.narration:
        report.add(
            "error",
            f"{path}/narration",
            f"{len(shot.narration)} narration line(s): the audio pipeline walks "
            "shot.dialogue only, so narration produces neither audio nor video. "
            "Rendering this shot raises. Use a dialogue line with an off-screen "
            "speaker as the workaround.",
        )


def _check_step_hz(
    step_hz: float | None, *, fps: int, path: str, report: "ValidationReport"
) -> None:
    """``0 < step_hz <= fps`` (an#89): a pose grid finer than the frame rate
    cannot be shown, and zero or negative is not a rate. The schema already
    refuses ``<= 0`` (``Field(gt=0)``) and the compiler re-checks the whole
    range, because a render never runs validate."""
    if step_hz is None or fps <= 0:  # fps <= 0 is already its own error
        return
    if not (0 < step_hz <= fps):
        report.add(
            "error",
            path,
            f"step_hz must satisfy 0 < step_hz <= fps ({fps}); got {step_hz!r}. "
            f"At {fps} fps, {fps / 2:g} is 'on twos' and {fps / 3:g} 'on threes'.",
        )


def _check_default_easing(spec: Any, *, report: "ValidationReport") -> None:
    """``meta.default_easing`` (an#166) must be an easing the evaluators know:
    it reaches every unnamed tween in the scene, so a typo is not one broken
    tween but all of them. The compiler re-checks, since a render never runs
    validate."""
    if spec is None:
        return
    from an.adapters.cutout.easing import apply_easing

    try:
        apply_easing(spec, 0.5)
    except (ValueError, TypeError) as e:
        report.add("error", "meta/default_easing", f"{spec!r} is not an easing: {e}")


def _check_default_easing_reach(scene: SceneIR, *, report: "ValidationReport") -> None:
    """Warn when ``meta.default_easing`` is set and some tweens spell
    ``ease_in_out`` explicitly — the shape every ``scene.json`` written before
    an#166 has (the old serializer wrote the default out), where the scene
    default silently reaches nothing. Explicit is explicit, so it is a
    warning naming the count, not a rewrite."""
    if scene.meta.default_easing is None:
        return
    from an.ir.schema import TweenAction

    pinned = [
        f"timeline/{i}/actions/{k}"
        for i, shot in enumerate(scene.timeline)
        for k, action in enumerate(shot.actions)
        for flat in flatten(action)
        if isinstance(flat.action, TweenAction)
        and "easing" in flat.action.model_fields_set
        and flat.action.easing == "ease_in_out"
    ]
    if pinned:
        report.add(
            "warning",
            "meta/default_easing",
            f"{len(pinned)} tween(s) name `easing: ease_in_out` explicitly, so "
            f"default_easing {scene.meta.default_easing!r} does not reach them "
            f"(first: {pinned[0]}). A scene.json written before an#166 spells the "
            "old default out on every tween; drop the key where the scene "
            "default is meant.",
        )


#: Keys an#106 retired, and what to write instead. `SceneIR`'s models are
#: `extra="allow"` (deliberately — forward compatibility), so a document that
#: still carries one of these validates cleanly and renders with the DEFAULT
#: renderer. The migration rewrites stored 0.1.x documents, but nothing rewrites
#: a document that is already 0.2.0: an agent patch, a hand edit, or a caller
#: passing `style=` to `Shot(...)` all produce a permanently dead key that no
#: later migration will touch. So it is caught here, at ERROR, by name.
RETIRED_KEYS: dict[str, dict[str, str]] = {
    "meta": {"default_style": "default_renderer"},
    "shot": {"style": "renderer"},
}

#: an#109's removed camera fields. A WARNING, not an error, and the difference
#: is the harm: a surviving `style` silently picks the wrong RENDERER, while
#: these three selected nothing — they described a 3D camera this package never
#: had. What is left is dead weight in a file, so it is worth saying and not
#: worth failing over.
#:
#: Reported at all because the migration cannot reach them: a document already
#: at the current version is never migrated again, so a camera block that came
#: through a sync between the version bump and this check keeps them forever as
#: `extra="allow"` extras, and nothing else looks.
RETIRED_CAMERA_KEYS: frozenset[str] = frozenset({"position", "target", "focal_length"})


def _check_retired_keys(scene: SceneIR, report: "ValidationReport") -> None:
    """One ERROR per retired key still present as an `extra`.

    >>> from an.ir.schema import Meta, SceneIR, Shot
    >>> scene = SceneIR(meta=Meta(), timeline=[Shot(id="s1", style="manim")])
    >>> report = ValidationReport()
    >>> _check_retired_keys(scene, report)
    >>> print(report.findings[0].description)
    `style` was renamed to `renderer` (an#106) and this value is being ignored...
    """
    for key, new in RETIRED_KEYS["meta"].items():
        if key in (scene.meta.model_extra or {}):
            report.add(
                "error",
                f"meta/{key}",
                f"`{key}` was renamed to `{new}` (an#106) and this value is "
                f'being ignored — the schema still ACCEPTS it (`extra="allow"`), '
                f"so nothing else will tell you. Rename it to `{new}`.",
            )
    for i, shot in enumerate(scene.timeline):
        camera_extra = getattr(shot.camera, "model_extra", None) or {}
        stale = sorted(RETIRED_CAMERA_KEYS & set(camera_extra))
        if stale:
            report.add(
                "warning",
                f"timeline[{i}]/camera",
                f"camera carries {stale}, removed in an#109 — they described a "
                "3D camera this package never had (the cutout camera is "
                "`root.pivot` plus `root.scale`) and are read by nothing. "
                "`an sync` drops them; they are harmless until then.",
            )
        for key, new in RETIRED_KEYS["shot"].items():
            if key in (shot.model_extra or {}):
                report.add(
                    "error",
                    f"timeline[{i}]/{key}",
                    f"`{key}` was renamed to `{new}` (an#106) and this value is "
                    f"being ignored — the shot will render with "
                    f"`renderer: {shot.renderer}`. Rename it to `{new}`.",
                )


def validate_semantic(
    scene: SceneIR,
    *,
    available_voices: Mapping[str, Any] | None = None,
    available_characters: Mapping[str, Any] | None = None,
    available_props: Mapping[str, Any] | None = None,
    available_environments: Mapping[str, Any] | None = None,
    available_sounds: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Cross-field semantic checks. Pass live stores in for cross-store checks.

    Both ``available_voices`` and ``available_characters`` accept any mapping;
    ``available_props`` is the same thing for `kind="prop"` entities (an#108),
    and ``available_environments`` lets the flat-pan warning read a stage's
    planes (an#111) —
    without it a prop's swaps are reported as having no descriptor, which is
    validate refusing what compile accepts.
    Voices are consulted via ``__contains__`` only; characters additionally
    via ``__getitem__`` (the swap-reference and `play` checks read descriptor
    dicts, an#87 / an#7). Pass ``None`` to skip those checks — and know that
    skipping them is what it sounds like: a `play` or a swap the compiler
    will refuse passes silently without the store (the CLI, `an validate`,
    always passes it).
    """
    report = ValidationReport()
    #: Only the stores actually supplied — an absent one skips its checks
    #: rather than reporting everything it would have found as missing.
    #: Every store that was actually supplied, keyed by MALL name. The rig
    #: checks look up `RIG_STORES[kind][0]`, so an `environments` entry is
    #: inert to them and available to the checks that need it (an#111's flat-pan
    #: warning reads planes). An absent store means its checks did not RUN —
    #: never that the thing it holds is missing.
    rig_stores = {
        name: store
        for name, store in (
            ("characters", available_characters),
            ("props", available_props),
            ("environments", available_environments),
        )
        if store is not None
    }

    _check_retired_keys(scene, report)
    if scene.meta.duration < 0:
        report.add("error", "meta/duration", "duration must be non-negative")
    if scene.meta.fps <= 0:
        report.add("error", "meta/fps", "fps must be positive")
    _check_step_hz(
        scene.meta.step_hz, fps=scene.meta.fps, path="meta/step_hz", report=report
    )
    _check_default_easing(scene.meta.default_easing, report=report)
    _check_default_easing_reach(scene, report=report)
    if not scene.timeline:
        report.add(
            "warning",
            "timeline",
            "scene has no shots — nothing to render. Add at least one "
            "`## Shot <id> (cutout)` heading to scene.md.",
        )

    seen_shot_ids: set[str] = set()
    turn_resolutions: list = []
    for i, shot in enumerate(scene.timeline):
        path = f"timeline/{i}"
        _check_step_hz(
            shot.step_hz, fps=scene.meta.fps, path=f"{path}/step_hz", report=report
        )
        if not shot.id:
            report.add("error", f"{path}/id", "shot id may not be empty")
        elif shot.id in seen_shot_ids:
            report.add("error", f"{path}/id", f"duplicate shot id: {shot.id!r}")
        seen_shot_ids.add(shot.id)

        if shot.duration <= 0:
            report.add("error", f"{path}/duration", "shot duration must be > 0")

        _check_renderable(shot, path, report, stores=rig_stores)
        _check_swap_references(shot, path, report, rig_stores)
        turn_resolutions.append(_turn_resolution(shot, rig_stores))
        _check_turns(shot, path, report, turn_resolutions[-1])
        _check_trim_targets(shot, path, report, rig_stores)
        text_ids = _check_text_blocks(
            shot,
            path,
            report,
            rig_stores,
            width=scene.meta.resolution.width,
            height=scene.meta.resolution.height,
        )
        _check_action_targets(
            shot,
            path,
            report,
            rig_stores,
            resolution=(
                scene.meta.resolution.width or None,
                scene.meta.resolution.height or None,
            ),
            skip=frozenset(text_ids),
        )

        # Entity references resolve?
        for j, entity in enumerate(shot.entities):
            if entity.kind not in RIG_STORES or entity.id in text_ids:
                continue
            store_name, want_kind = RIG_STORES[entity.kind]
            store = rig_stores.get(store_name)
            if store is None:
                continue  # store not supplied → this check did not run
            if entity.kind == "character":
                # A WARNING: the compiler falls back to the built-in placeholder
                # rig and the scene still renders. Deliberately not escalated —
                # an asset-less project rendering placeholders is a supported
                # way to work.
                if entity.ref not in store:
                    report.add(
                        "warning",
                        f"{path}/entities/{j}",
                        f"character ref {entity.ref!r} not in characters store",
                    )
                continue
            # A stroked path (an#160) is a prop whose document is a
            # `PathDescriptor`; it is checked by the same resolver the
            # compiler builds it with, overrides merged, so the verdicts agree.
            path_problem = _path_document_problem(entity, store)
            if path_problem is not False:
                if path_problem:
                    report.add("error", f"{path}/entities/{j}", path_problem)
                continue
            # A prop has NO placeholder rig — the placeholder IS a humanoid, so
            # falling back would draw a person where the prop should be — which
            # makes an unresolvable prop a hard raise at compile. The pre-flight
            # for a hard raise is an ERROR, and before an#108's review this arm
            # did not exist at all: the harsher outcome had the weaker
            # prediction, and `an validate` said "passed" about a scene that
            # cannot render.
            if _rig_document(entity, rig_stores) is None:
                if entity.ref in store:
                    why = (
                        f"is in the {store_name!r} store but is not a "
                        f"{want_kind} (rendering this shot raises)"
                    )
                else:
                    why = (
                        f"is not in the {store_name!r} store, and a {entity.kind} "
                        "has no placeholder rig (rendering this shot raises)"
                    )
                report.add(
                    "error",
                    f"{path}/entities/{j}",
                    f"{entity.kind} ref {entity.ref!r} {why}",
                )

        # Dialogue voice refs resolve?
        # The line's own voice_ref, else the one its speaker is bound to — the
        # resolver the audio pipeline speaks with (an#194).
        if available_voices is not None:
            for k, line in enumerate(shot.dialogue):
                voice_ref = line.voice_ref or speaker_voice_ref(
                    line.speaker, shot, {"characters": available_characters}
                )
                if voice_ref is None:
                    continue
                if voice_ref not in available_voices:
                    bound = (
                        ""
                        if line.voice_ref
                        else f" (the voice character {line.speaker!r} is bound to)"
                    )
                    report.add(
                        "warning",
                        f"{path}/dialogue/{k}/voice_ref",
                        f"voice ref {voice_ref!r}{bound} not in voices store; "
                        "the TTS provider is handed the name itself",
                    )
                else:
                    _check_voice_effects(report, path, k, voice_ref, available_voices)

        for k, line in enumerate(shot.dialogue):
            if not line.text.strip():
                report.add(
                    "warning", f"{path}/dialogue/{k}/text", "empty dialogue line"
                )
            if not line.speaker:
                report.add(
                    "error",
                    f"{path}/dialogue/{k}/speaker",
                    "dialogue requires a speaker",
                )
        _check_dialogue_fits(shot, path, report)

    _check_view_continuity(scene, report, turn_resolutions)
    _check_assembly(scene, report, sounds=available_sounds)
    return report


#: Slack before a line counts as running past its shot: a frame at 60 fps.
DIALOGUE_OVERRUN_TOLERANCE_S: float = 1 / 60


def _dialogue_layout(shot: Any):
    """``(k, line, start, end, estimated)`` for each dialogue line of ``shot``.

    Where each line WILL play: the audio pipeline's own rule
    (:meth:`an.ir.schema.Dialogue.planned_start`) over the real duration when
    the line was synthesized, else the offline voice's estimate
    (:func:`an.audio.offline_tts.estimate_speech_duration`). Never the stamped
    ``start``, which a pause edited since the last synthesis has made stale.
    """
    from an.audio.offline_tts import estimate_speech_duration

    cursor = 0.0
    for k, line in enumerate(shot.dialogue):
        estimated = line.duration is None
        length = (
            estimate_speech_duration(line.text) if estimated else float(line.duration)
        )
        start = line.planned_start(cursor)
        cursor = start + length
        yield k, line, start, cursor, estimated


def _check_dialogue_fits(shot: Any, path: str, report: "ValidationReport") -> None:
    """Warn when a shot's dialogue runs past the shot's end.

    The audio is cut at the shot end (each shot's mix is trimmed to its
    duration), and the lines play back to back, so a shot shortened below its
    dialogue loses the tail of it — silently, until now (an e2e run shrank an
    8.2 s shot holding 7.1 s of speech to 3.0 s and `an validate` said nothing).

    What is known depends on when this runs. After the audio pipeline, a line
    carries its real ``duration`` and the check is exact. Before it, the
    duration is the offline voice's estimate
    (:func:`an.audio.offline_tts.estimate_speech_duration` — exactly what an
    offline render will give, and an under-estimate for a real voice). Either
    way the lines are laid out by the pipeline's own rule,
    :meth:`an.ir.schema.Dialogue.planned_start` — back to back from the shot
    start, shifted by each line's ``pause`` or pinned by its ``at`` (an#187) —
    so a pause edited after synthesis is judged where it will play, not where
    the stale stamp says.

    Also warns when a speaker's line starts before that speaker's previous
    line ends: one mouth cannot say two lines (an ``at`` can do that; a
    ``pause`` cannot). Two speakers talking over each other is legal.
    """
    speaking_until: dict[str, tuple[int, float]] = {}
    for k, line, start, end, estimated in _dialogue_layout(shot):
        previous = speaking_until.get(line.speaker)
        if previous is not None and start < previous[1] - DIALOGUE_OVERRUN_TOLERANCE_S:
            report.add(
                "warning",
                f"{path}/dialogue/{k}",
                f"line {k} ({line.speaker}) starts at {start:.2f}s, before the "
                f"same speaker's line {previous[0]} ends at {previous[1]:.2f}s"
                + (" (at the offline voice's rate)" if estimated else "")
                + ": one mouth cannot say both. Start it later (its `at`) or "
                "give it a `pause` instead",
            )
        speaking_until[line.speaker] = (k, end)
        if end <= shot.duration + DIALOGUE_OVERRUN_TOLERANCE_S:
            continue
        how = (
            "at the offline voice's rate (a real voice is usually slower)"
            if estimated
            else "as synthesized"
        )
        report.add(
            "warning",
            f"{path}/dialogue/{k}",
            f"line {k} ({line.speaker}) ends at {end:.2f}s {how}, past the shot's "
            f"{shot.duration:g}s end, so its last {end - shot.duration:.2f}s are "
            "cut off: the shot's audio stops where the shot does. Lengthen the "
            f"shot to at least {end:.2f}s, shorten the line, or move it to the "
            "next shot",
        )


def _check_assembly(
    scene: SceneIR, report: "ValidationReport", *, sounds: Mapping[str, Any] | None
) -> None:
    """Transitions and the sound layer (`an.assemble`): what assembling the film
    would refuse is an error here, from the SAME list the assembler raises on."""
    from an.assemble import film_timeline, transition_problems

    fps = scene.meta.fps
    if fps <= 0:
        return  # already its own error
    problems = transition_problems(scene.timeline, fps)
    for i, message in problems:
        report.add("error", f"timeline/{i}/transition", message)
    if not problems:
        timeline = film_timeline(scene.timeline, fps=fps)
        for i, shot in enumerate(scene.timeline):
            # A dissolve plays both shots' audio in the overlap: a line there
            # is heard over the other shot's picture. Legal, and worth a word.
            overlap_out = (
                timeline.dissolve_in[i + 1] / fps
                if i + 1 < len(scene.timeline)
                else 0.0
            )
            overlap_in = timeline.dissolve_in[i] / fps
            for k, _line, start, end, _estimated in _dialogue_layout(shot):
                if (overlap_in and start < overlap_in) or (
                    overlap_out and end > shot.duration - overlap_out
                ):
                    report.add(
                        "warning",
                        f"timeline/{i}/dialogue/{k}",
                        "this line plays during a dissolve, so it is heard over "
                        "the neighbouring shot's picture too; move it clear of "
                        "the overlap or shorten the dissolve",
                    )

    cues = [("meta/sounds", j, c) for j, c in enumerate(scene.meta.sounds)]
    if not problems:
        from an.assemble import film_duration

        length = film_duration(scene)
        for j, cue in enumerate(scene.meta.sounds):
            if cue.at >= length:
                report.add(
                    "warning",
                    f"meta/sounds/{j}/at",
                    f"cue at {cue.at}s starts after the film ends ({length:.3f}s) "
                    "and is dropped; a meta cue's time is film time",
                )
    for i, shot in enumerate(scene.timeline):
        for j, cue in enumerate(shot.sounds):
            cues.append((f"timeline/{i}/sounds", j, cue))
            if cue.at >= shot.duration:
                report.add(
                    "warning",
                    f"timeline/{i}/sounds/{j}/at",
                    f"cue at {cue.at}s starts after shot {shot.id!r} ends "
                    f"({shot.duration}s); a shot cue's time is shot-local",
                )
    if sounds is None:
        return  # store not supplied: the reference checks did not run
    for base, j, cue in cues:
        path = f"{base}/{j}/sound"
        if cue.sound not in sounds:
            report.add(
                "error",
                path,
                f"sound {cue.sound!r} is not in the sounds store (rendering "
                "raises); add it with an.sounds.add_sound",
            )
            continue
        source = (sounds[cue.sound] or {}).get("source") or {}
        if not source.get("license"):
            report.add(
                "warning",
                path,
                f"sound {cue.sound!r} has no recorded licence; `an credits` "
                "reports it UNVERIFIED — unknown is not unencumbered",
            )
