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
from typing import Any, Collection, Literal, Mapping

from pydantic import ValidationError

from an.base import AUTHORABLE_PROPERTIES, TRANSFORM_PROPERTIES
from an.audio.effects import TRIM_SILENCE, VoiceEffectError, voice_effects
from an.audio.voices import speaker_voice_ref
from an.stores._common import art_exists_for
from an.ir.camera import CAMERA_MOVES, CameraError, camera_keys
from an.ir.compose import flatten
from an.ir.migrate import DocumentMigrationError, migrate
from an.ir.sync import SceneValidationError, scene_from_json_doc
from an.ir.schema import SceneIR
from an.base import SUPPORTED_RENDERERS
from an.genres.registry import (
    CORE_OWNER,
    SemanticCheck,
    UnregisteredKindError,
    action_kind,
    check_names,
    checks as registered_checks,
    entity_kind,
    entity_kind_names,
    register_check,
)


Severity = Literal["error", "warning", "info"]


@dataclass(slots=True)
class ValidationFinding:
    """A single validation issue with a path into the IR."""

    severity: Severity
    ir_path: str
    description: str
    #: ``"<file>:<line>"`` when the thing to fix is an opaque source a shot runs
    #: (a Manim scene file, an#279) rather than the IR; ``None`` otherwise.
    location: str | None = None


@dataclass(slots=True)
class ValidationReport:
    """Result of running one or more validators.

    ``passed`` is True iff there are no error-severity findings.
    """

    passed: bool = True
    findings: list[ValidationFinding] = field(default_factory=list)

    def add(
        self,
        severity: Severity,
        ir_path: str,
        description: str,
        *,
        location: str | None = None,
    ) -> None:
        self.findings.append(
            ValidationFinding(
                severity=severity,
                ir_path=ir_path,
                description=description,
                location=location,
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
_CORE_RIG_STORES: dict[str, tuple[str, str]] = {
    "prop": ("props", "PropDescriptor"),
}


def rig_stores() -> dict[str, tuple[str, str]]:
    """``{entity kind: (mall store, descriptor kind)}`` for every kind that has a rig.

    The core's own (``prop``) plus the kinds genres register with a
    ``descriptor_kind`` (the cut-out genre's ``character``): derived from the
    registry, not a table the core edits (an#246).

    >>> rig_stores()["prop"]
    ('props', 'PropDescriptor')
    """
    out = dict(_CORE_RIG_STORES)
    for name in entity_kind_names():
        kind = entity_kind(name)
        if kind is not None and kind.store and kind.descriptor_kind:
            out[name] = (kind.store, kind.descriptor_kind)
    return out


def _has_procedural_rig(kind: str) -> bool:
    """Whether entities of ``kind`` have a procedural fallback rig (a genre says so)."""
    registered = entity_kind(kind)
    return registered is not None and registered.placeholder_on_missing


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
        store_name, want_kind = rig_stores()[entity.kind]
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
    from an.stage.paths import resolve_path  # the compiler's own resolver

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
    from an.stage.text import (
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
        from an.stage.paths import resolve_path

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


def _rig_scope(shot, stores: Mapping[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """``(rigged entities by id, ids whose rig store was not supplied)``.

    PER-KIND, not per-call. an#108's first pass changed the gate from
    "characters store absent → skip" to "no stores at all → skip", which made
    `validate_semantic(scene, available_characters=X)` — the signature every
    caller outside this repo has — report EVERY prop swap as "has no
    descriptor declaring asset sets" on a scene that compiles fine. A store
    that was not supplied means the check did not run for that kind; it never
    means the descriptor is missing: those entities' checks are SKIPPED, not
    failed.
    """
    rigs = {e.id: e for e in shot.entities if e.kind in rig_stores()}
    unchecked = {
        eid for eid, e in rigs.items() if stores.get(rig_stores()[e.kind][0]) is None
    }
    return rigs, unchecked


def _check_swap_references(
    shot, path: str, report: "ValidationReport", stores: Mapping[str, Any]
) -> None:
    """A set/tween on a non-transform property must name a declared asset set
    and key of its target entity's descriptor — checked HERE, before the
    author pays for TTS or a Chromium launch, because compile raises on it
    (an#87). Same charter as `_check_renderable`; needs the store, so with no
    stores it does not run.

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
    rigs, unchecked = _rig_scope(shot, stores)
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
        registered = entity_kind(entity.kind) if entity is not None else None
        swap_checks = registered.swap_checks if registered is not None else None
        if desc is None:
            # The procedural carve-out is a CHARACTER's drawn mouth; a prop
            # with no rig document (a stroked path, an#160) has no swap set at
            # all, which is what the compiler says too.
            is_prop = entity is not None and not _has_procedural_rig(entity.kind)
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
                + (swap_checks.missing_set_hint(prop) if swap_checks else ""),
            )
            continue
        keys = declared.get(prop) or {}
        if swap_checks is not None and "/" not in target:
            # A swap on the CHARACTER ITSELF (an#197) is fanned out by the
            # compiler to every slot the set projects onto — so it is checked
            # per slot, through the resolvers the compiler's fan-out and
            # `play: turn` share (an#201), not by the per-node rule below.
            if swap_checks.whole_entity(
                action,
                desc,
                prop,
                keys,
                entity_id,
                where=f"{path}/actions/{k}",
                report=report,
                art_exists=art_exists_for(
                    stores.get(rig_stores()[entity.kind][0]), entity.ref
                ),
            ):
                continue
        # …and the ART has to be there. The compiler registers only the
        # attachments whose files resolve and then refuses a key whose art is
        # missing, so a key that is DECLARED but undrawable passed validate and
        # raised at compile — with `strict_assets` either way (an#108 review,
        # H3). Same rule the rig builder's probe uses: a store with no
        # filesystem root can answer nothing, so it must assume presence rather
        # than drop every key.
        art_exists = art_exists_for(
            stores.get(rig_stores()[entity.kind][0]), entity.ref
        )
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


#: Leaf kinds whose ``target`` is a NODE path the runtime animates. `play` and
#: `expression` target an entity and are resolved by their own checks above.
_NODE_TARGETING_KINDS = frozenset({"set", "tween"})

#: Authorable properties that are compiler SUGAR, never a channel: ``tint`` is
#: a ``#rrggbb`` string the compiler expands into three numbers (an#62), so it
#: is not a field of any space.
_AUTHORING_SUGAR_PROPERTIES: frozenset[str] = (
    AUTHORABLE_PROPERTIES - TRANSFORM_PROPERTIES
)


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
    (:func:`an.stage.compile.unknown_target_message`), with "did you
    mean" suggestions from the real paths. A target on an entity whose store
    was not supplied is skipped: without it a stand-in (the placeholder rig,
    the default backdrop) would be built, and its paths are not the asset's.
    ``skip`` names entities another check owns (text blocks: their units are
    checked by `_check_text_blocks`, at the scene's resolution). The runtime's
    camera node (``root``) is a legitimate target, as the compiler says.
    """
    from an.stage import STAGE_RENDERER_NAMES

    if not stores or shot.renderer not in STAGE_RENDERER_NAMES:
        return
    from an.stage.compile import CAMERA_NODE, unknown_target_message

    store_of = {kind: name for kind, (name, _doc) in rig_stores().items()}
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


def _check_voice_effects(
    report: "ValidationReport", path: str, k: int, voice_ref: str, voices, *, line
) -> None:
    """An unknown or out-of-range ``effects`` entry, or a malformed ``takes``
    declaration (an#265), on a line's voice is an error — rendering would raise
    the same ``VoiceEffectError`` / ``VoiceTakesError`` before any request."""
    from an.audio.takes import TAKES_KEY, VoiceTakesError, takes_spec
    from an.audio.voices import voice_document

    try:
        voice_effects({"voices": voices}, voice_ref)
    except VoiceEffectError as exc:
        report.add(
            "error", f"{path}/dialogue/{k}/voice_ref", f"voice {voice_ref!r}: {exc}"
        )
    try:
        takes_spec(
            voice_document({"voices": voices}, voice_ref).get(TAKES_KEY),
            direction=line.direction,
        )
    except VoiceTakesError as exc:
        report.add(
            "error", f"{path}/dialogue/{k}/voice_ref", f"voice {voice_ref!r}: {exc}"
        )
    _check_elevenlabs_voice(report, path, k, voice_ref, voices, line=line)


def _check_elevenlabs_voice(
    report: "ValidationReport", path: str, k: int, voice_ref: str, voices, *, line
) -> None:
    """An ElevenLabs voice's malformed ``voice_settings``/``seed``/``model_id``
    is an error (synthesis would raise it); a ``direction`` its model cannot
    read is a warning — the cue is dropped (an#209)."""
    import warnings

    from an.audio.elevenlabs_tts import ElevenLabsTTS, ElevenLabsVoiceError
    from an.audio.voices import voice_applies, voice_document

    doc = voice_document({"voices": voices}, voice_ref)
    tts = ElevenLabsTTS(api_key="validate-never-calls")
    if not doc.get("provider") or not voice_applies(doc, tts.name):
        return
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            tts.synthesis_options(doc, emotion=line.emotion, direction=line.direction)
    except ElevenLabsVoiceError as exc:
        report.add(
            "error", f"{path}/dialogue/{k}/voice_ref", f"voice {voice_ref!r}: {exc}"
        )
        return
    for w in caught:
        report.add("warning", f"{path}/dialogue/{k}/direction", str(w.message))


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
    from an.stage.environments import ENVIRONMENT_DOCUMENT_KIND, EnvironmentDescriptor

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


def _check_framing(
    shot, path: str, report: "ValidationReport", stores, *, width: int, height: int
) -> None:
    """Warn when a camera pose shows past the edge of the stage (an#211).

    A close-up on a plate that only just fills the frame shows its edge — a
    band of background colour, the top of a tree cut off — and renders
    happily. The check is the compiler's geometry evaluated at every camera
    key (or the resting frame when there is no move): the region the pose
    frames (`an.stage.environments.frame_rect`) against the union of every plane's
    drawn rect with its parallax compensation at that pose
    (`an.stage.environments.plane_rect`).

    **Keys suffice for a move without roll.** Between two keys x, y and zoom
    share one eased parameter; a plane edge minus a frame edge is then a
    linear term plus ``±canvas/(2·zoom)``, which is convex in it, so the
    worst gap on each side is at a key. Two stated limits: an easing that
    OVERSHOOTS (a cubic Bézier outside [0, 1]) can pass a key, and a gap
    BETWEEN two plates crossed mid-move is seen only if a key frames it. A
    rolling camera is checked at its keys, conservatively.

    Silent — not "covered" — when it cannot know: no environments store, an
    environment that is not a plane descriptor (a preset draws 4000-pixel
    bands, which cover), a shot with no environment, or a plane whose drawn
    size depends on art that cannot be measured.
    """
    env_store = (stores or {}).get("environments")
    envs = [e for e in shot.entities if e.kind == "environment"]
    if env_store is None or not envs or not (width and height):
        return
    from an.stage.environments import (
        ENVIRONMENT_DOCUMENT_KIND,
        EnvironmentDescriptor,
        frame_rect,
        plane_rect,
        uncovered_part,
    )

    planes: list[tuple[Any, tuple[float, float] | None]] = []
    root = getattr(env_store, "_root", None)
    for entity in envs:
        try:
            raw = env_store[entity.ref]
        except (KeyError, TypeError):
            return  # a preset or the default backdrop: huge bands, covered
        if (
            not isinstance(raw, dict)
            or raw.get("kind") != ENVIRONMENT_DOCUMENT_KIND.name
        ):
            return
        try:
            env = EnvironmentDescriptor.model_validate(
                migrate(dict(raw), kind=ENVIRONMENT_DOCUMENT_KIND.name)
            )
        except Exception:  # noqa: BLE001 — a malformed descriptor is another check's
            return
        if not env.planes:
            return  # compiles to the preset backdrop
        for plane in env.planes:
            planes.append((plane, _plane_art_size(root, entity.ref, plane)))
    try:
        keys = camera_keys(shot, width=width, height=height)
    except CameraError:
        return  # `_check_camera` reports it
    from an.ir.schema import CameraKey

    if len(keys) < 2:
        keys = [CameraKey()]  # no move: the resting frame
    for key in keys:
        rects = [
            plane_rect(plane, art, camera=(float(key.x), float(key.y)))
            for plane, art in planes
        ]
        if any(r is None for r in rects):
            return
        view = frame_rect(
            x=float(key.x),
            y=float(key.y),
            zoom=float(key.zoom),
            rotation=float(key.rotation),
            width=float(width),
            height=float(height),
        )
        hole = uncovered_part(view, rects)  # type: ignore[arg-type]
        if hole is None:
            continue
        sides = [
            name
            for name, gap in (
                ("left", hole[0] <= view[0]),
                ("top", hole[1] <= view[1]),
                ("right", hole[2] >= view[2]),
                ("bottom", hole[3] >= view[3]),
            )
            if gap
        ]
        pose = (
            f"the camera key at {float(key.at):g}s (x {float(key.x):g}, "
            f"y {float(key.y):g}, zoom {float(key.zoom):g})"
            if shot.camera is not None and len(keys) > 1
            else "the resting frame"
        )
        report.add(
            "warning",
            f"{path}/camera" if shot.camera is not None else f"{path}/entities",
            f"{pose} shows scene region "
            f"{_fmt_rect(view)} but the environment planes leave "
            f"{_fmt_rect(hole)} uncovered"
            + (f" (the {'/'.join(sides)} edge)" if sides else "")
            + ": the edge of the plate shows as background colour. Make the "
            "plate bigger (`size`), move it (`offset`), or frame less.",
        )
        return  # one finding per shot: the first pose that shows an edge


def _plane_art_size(root, ref, plane) -> tuple[float, float] | None:
    """The measured extent of an image plane's art, or ``None``."""
    if plane.art.kind != "image" or not plane.art.src or root is None:
        return None
    from pathlib import Path

    from an.stage.raster import art_size

    try:
        return art_size(Path(root) / str(ref) / plane.art.src)
    except (OSError, ValueError):
        return None


def _fmt_rect(r) -> str:
    return "x {:g}..{:g}, y {:g}..{:g}".format(
        round(r[0], 1), round(r[2], 1), round(r[1], 1), round(r[3], 1)
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
        if entity_kind(entity.kind) is None:
            continue  # unregistered: `entity_kinds` reported it, naming its genre
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
    from an.stage.easing import apply_easing

    try:
        apply_easing(spec, 0.5)
    except (ValueError, TypeError) as e:
        report.add("error", "meta/default_easing", f"{spec!r} is not an easing: {e}")


def _check_tween_easings(scene: SceneIR, *, report: "ValidationReport") -> None:
    """Every tween's own easing must be one the evaluators know (an#233 review,
    S1) — what compile refuses and the stage runtime cannot draw, validate says
    first, so validate and the player agree."""
    from an.stage.easing import apply_easing
    from an.ir.schema import TweenAction

    for i, shot in enumerate(scene.timeline):
        for k, action in enumerate(shot.actions):
            for flat in flatten(action):
                tw = flat.action
                if (
                    not isinstance(tw, TweenAction)
                    or "easing" not in tw.model_fields_set
                ):
                    continue
                try:
                    apply_easing(tw.easing, 0.5)
                except (ValueError, TypeError) as e:
                    report.add(
                        "error",
                        f"timeline/{i}/actions/{k}",
                        f"tween {tw.target}:{tw.property} easing {tw.easing!r} is "
                        f"not an easing the renderer draws: {e}",
                    )


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


@dataclass
class ValidationContext:
    """What a registered semantic check (:class:`an.genres.SemanticCheck`) reads.

    ``stores`` holds only the stores actually supplied, keyed by MALL name (an
    absent one means its checks did not RUN — never that what it holds is
    missing). ``shot`` and ``index`` are set while the ``shot`` stage runs.
    ``memo`` is shared by every check of one ``validate_semantic`` call, so
    two checks that need the same derived fact compute it once
    (:meth:`cached`).
    """

    scene: SceneIR
    report: ValidationReport
    stores: dict[str, Any]
    voices: Mapping[str, Any] | None = None
    characters: Mapping[str, Any] | None = None
    sounds: Mapping[str, Any] | None = None
    #: The project's asset-library lockfile (``mall["library_lock"]``, an#240);
    #: ``None`` means the pin checks did not run.
    library_lock: Mapping[str, Any] | None = None
    shot: Any = None
    index: int | None = None
    memo: dict[Any, Any] = field(default_factory=dict)

    @property
    def path(self) -> str:
        """The IR path of the current shot (``timeline/<index>``)."""
        return f"timeline/{self.index}"

    def cached(self, key: Any, compute: Any) -> Any:
        """``compute()``, once per ``key`` per validation."""
        if key not in self.memo:
            self.memo[key] = compute()
        return self.memo[key]


def validate_semantic(
    scene: SceneIR,
    *,
    available_voices: Mapping[str, Any] | None = None,
    available_characters: Mapping[str, Any] | None = None,
    available_props: Mapping[str, Any] | None = None,
    available_environments: Mapping[str, Any] | None = None,
    available_sounds: Mapping[str, Any] | None = None,
    available_library_lock: Mapping[str, Any] | None = None,
    only: "Collection[str] | None" = None,
    fps: float | None = None,
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

    ``available_library_lock`` is the project's asset-library lockfile
    (``mall["library_lock"]``): with it, every scene ``library:`` pin is checked
    against the lockfile (``warning`` on disagreement) and every pinned
    check-out against its library version (``info`` when it has been edited).

    The checks are a REGISTRY (:func:`an.genres.registry.register_check`):
    the core's own register below, a genre's when it is loaded (the cut-out
    genre's `play`, `expression`, turn and view checks), and they run in
    stages — ``scene``, then ``shot`` once per shot, then ``finish`` — each by
    its ``order``. An action or entity kind no loaded genre registered is one
    error naming the genre that provides it; checks that would trip over it
    skip that shot rather than crash.

    ``only`` runs just the registered checks of those names (what ``an render``
    does after synthesis, :func:`post_synthesis_findings`); ``fps`` is the one
    the film is assembled at when it is not the scene's (``an render --fps``),
    which decides how long a dissolve's overlap is.
    """
    ctx = ValidationContext(
        scene=scene,
        report=ValidationReport(),
        stores={
            name: store
            for name, store in (
                ("characters", available_characters),
                ("props", available_props),
                ("environments", available_environments),
            )
            if store is not None
        },
        voices=available_voices,
        characters=available_characters,
        sounds=available_sounds,
        library_lock=available_library_lock,
        memo={_RENDER_FPS: fps} if fps is not None else {},
    )

    def selected(stage: str):
        return [c for c in registered_checks(stage) if only is None or c.name in only]

    for check in selected("scene"):
        _run_check(check, ctx)
    for i, shot in enumerate(scene.timeline):
        ctx.shot, ctx.index = shot, i
        for check in selected("shot"):
            _run_check(check, ctx)
    ctx.shot = ctx.index = None
    for check in selected("finish"):
        _run_check(check, ctx)
    return ctx.report


def _run_check(check: Any, ctx: ValidationContext) -> None:
    """Run one check; an unregistered kind it trips over was already reported
    (by ``action_kinds`` / ``entity_kinds``), so it costs that check, not the
    whole report."""
    try:
        check.run(ctx)
    except (UnregisteredKindError, ValidationError):
        if not ctx.memo.get(_KIND_PROBLEM_REPORTED):
            raise


#: Set in the memo once an action or entity kind problem — unregistered, or a
#: genre kind its own model refuses — has been reported as a finding.
_KIND_PROBLEM_REPORTED = "kind problem reported"


# -----------------------------------------------------------------------------
# The core's checks, as registered entries (the order is the report's order)
# -----------------------------------------------------------------------------


def _core_retired_keys(ctx: ValidationContext) -> None:
    _check_retired_keys(ctx.scene, ctx.report)


def _core_meta(ctx: ValidationContext) -> None:
    scene, report = ctx.scene, ctx.report
    if scene.meta.duration < 0:
        report.add("error", "meta/duration", "duration must be non-negative")
    if scene.meta.fps <= 0:
        report.add("error", "meta/fps", "fps must be positive")
    _check_step_hz(
        scene.meta.step_hz, fps=scene.meta.fps, path="meta/step_hz", report=report
    )


def _core_easings(ctx: ValidationContext) -> None:
    _check_default_easing(ctx.scene.meta.default_easing, report=ctx.report)
    _check_tween_easings(ctx.scene, report=ctx.report)
    _check_default_easing_reach(ctx.scene, report=ctx.report)


def _core_has_shots(ctx: ValidationContext) -> None:
    if not ctx.scene.timeline:
        ctx.report.add(
            "warning",
            "timeline",
            "scene has no shots — nothing to render. Add at least one "
            "`## Shot <id> (cutout)` heading to scene.md.",
        )


def _core_action_kinds(ctx: ValidationContext) -> None:
    """Every action's kind is registered, and a registered genre kind read
    before its genre loaded validates against its own model (ADR 0001
    decision 2: the schema accepts any ``kind``; this is where it is held).
    Runs first, over every shot, so the checks after it can skip what it
    reported instead of crashing on it."""
    from an.ir.compose import iter_actions
    from an.ir.schema import ExtensionAction, unregistered_action_kind

    for i, shot in enumerate(ctx.scene.timeline):
        for k, top in enumerate(shot.actions):
            where = f"timeline/{i}/actions/{k}"
            for action in iter_actions(top):
                # EVERY node, whatever its type: a typed genre action built in
                # Python (`an.play(...)`) while its genre is not loaded is as
                # unregistered as a bare `ExtensionAction` (review-244 S3).
                if action_kind(str(getattr(action, "kind", ""))) is None:
                    ctx.memo[_KIND_PROBLEM_REPORTED] = True
                    ctx.report.add(
                        "error", where, str(unregistered_action_kind(action.kind))
                    )
                    continue
                if type(action) is not ExtensionAction:
                    continue
                try:
                    action.resolved()
                except ValidationError as e:
                    ctx.memo[_KIND_PROBLEM_REPORTED] = True
                    for err in e.errors():
                        loc = "/".join(str(x) for x in err.get("loc", ()))
                        ctx.report.add(
                            "error",
                            where + (f"/{loc}" if loc else ""),
                            f"`{action.kind}` action: {err.get('msg', 'invalid')}",
                        )


def _core_entity_kinds(ctx: ValidationContext) -> None:
    """Every entity's ``kind`` is a registered entity kind (ADR 0001 decision
    2: ``AssetRef.kind`` is a ``str`` in the schema, held here)."""
    from an.genres import providers_of
    from an.genres.registry import entity_kind_names

    located = [("assets", j, e) for j, e in enumerate(ctx.scene.assets)] + [
        (f"timeline/{i}/entities", j, e)
        for i, shot in enumerate(ctx.scene.timeline)
        for j, e in enumerate(shot.entities)
    ]
    for where, j, entity in located:
        if entity_kind(entity.kind) is not None:
            continue
        ctx.memo[_KIND_PROBLEM_REPORTED] = True
        error = UnregisteredKindError(
            "entity kind",
            entity.kind,
            known=entity_kind_names(),
            providers=providers_of(entity.kind, registry="entity kinds"),
        )
        ctx.report.add("error", f"{where}/{j}", str(error))


def _known_renderers() -> set[str]:
    from an.adapters._base import list_renderers

    return set(SUPPORTED_RENDERERS) | set(list_renderers())


def _renderer_problem(name: str) -> str | None:
    known = _known_renderers()
    if name in known:
        return None
    return (
        f"renderer {name!r} is not registered; known: {sorted(known)}. A "
        "renderer registers with `an.adapters.register_renderer`."
    )


def _core_renderer(ctx: ValidationContext) -> None:
    """The shot's ``renderer`` names a renderer this build has: a built-in one
    (:data:`an.base.SUPPORTED_RENDERERS`) or one registered with
    ``an.adapters.register_renderer``."""
    problem = _renderer_problem(ctx.shot.renderer)
    if problem:
        ctx.report.add("error", f"{ctx.path}/renderer", problem)


def registered_kind_problems(scene: SceneIR) -> ValidationReport:
    """The findings of the three registry checks alone — every action kind,
    entity kind and renderer the scene names must be registered — without the
    rest of ``validate_semantic`` (no stores, no rig builds; cheap)."""
    ctx = ValidationContext(scene=scene, report=ValidationReport(), stores={})
    _core_action_kinds(ctx)
    _core_entity_kinds(ctx)
    for i, shot in enumerate(scene.timeline):
        problem = _renderer_problem(shot.renderer)
        if problem:
            ctx.report.add("error", f"timeline/{i}/renderer", problem)
    problem = _renderer_problem(scene.meta.default_renderer)
    if problem:
        ctx.report.add("error", "meta/default_renderer", problem)
    return ctx.report


class UnregisteredInSceneError(UnregisteredKindError):
    """A scene names kinds or renderers nothing registered: refused at load.

    Raised by :func:`require_registered_kinds` — what ``an.load(project)``
    (and so ``an render``) runs, so a typo'd ``kind:`` or ``renderer:`` can no
    longer render silently wrong now that the schema holds them as ``str``
    (review-244 S2). ``findings`` keeps each one with its IR path.
    """

    def __init__(self, findings: list, *, where: str = "") -> None:
        self.findings = findings
        ValueError.__init__(
            self,
            (f"{where}: " if where else "")
            + "the scene names what no loaded genre or renderer registered:\n"
            + "\n".join(f"  {f.ir_path}: {f.description}" for f in findings),
        )


def require_registered_kinds(scene: SceneIR, *, where: str = "") -> SceneIR:
    """``scene``, or :class:`UnregisteredInSceneError` naming every action
    kind, entity kind and renderer it uses that is not registered."""
    report = registered_kind_problems(scene)
    errors = [f for f in report.findings if f.severity == "error"]
    if errors:
        raise UnregisteredInSceneError(errors, where=where)
    return scene


def _core_shot_basics(ctx: ValidationContext) -> None:
    shot, path, report = ctx.shot, ctx.path, ctx.report
    _check_step_hz(
        shot.step_hz, fps=ctx.scene.meta.fps, path=f"{path}/step_hz", report=report
    )
    seen_shot_ids = ctx.memo.setdefault("seen shot ids", set())
    if not shot.id:
        report.add("error", f"{path}/id", "shot id may not be empty")
    elif shot.id in seen_shot_ids:
        report.add("error", f"{path}/id", f"duplicate shot id: {shot.id!r}")
    seen_shot_ids.add(shot.id)
    if shot.duration <= 0:
        report.add("error", f"{path}/duration", "shot duration must be > 0")


def _core_renderable(ctx: ValidationContext) -> None:
    _check_renderable(ctx.shot, ctx.path, ctx.report, stores=ctx.stores)


def _core_framing(ctx: ValidationContext) -> None:
    res = ctx.scene.meta.resolution
    _check_framing(
        ctx.shot, ctx.path, ctx.report, ctx.stores, width=res.width, height=res.height
    )


def _core_swap_references(ctx: ValidationContext) -> None:
    _check_swap_references(ctx.shot, ctx.path, ctx.report, ctx.stores)


def _core_trim_targets(ctx: ValidationContext) -> None:
    _check_trim_targets(ctx.shot, ctx.path, ctx.report, ctx.stores)


def _text_ids(ctx: ValidationContext) -> list:
    """The current shot's text-block entity ids (checked by `_check_text_blocks`,
    once; the target and entity-reference checks skip them)."""
    res = ctx.scene.meta.resolution
    return ctx.cached(
        ("text ids", ctx.index),
        lambda: _check_text_blocks(
            ctx.shot,
            ctx.path,
            ctx.report,
            ctx.stores,
            width=res.width,
            height=res.height,
        ),
    )


def _core_text_blocks(ctx: ValidationContext) -> None:
    _text_ids(ctx)


def _core_action_targets(ctx: ValidationContext) -> None:
    res = ctx.scene.meta.resolution
    _check_action_targets(
        ctx.shot,
        ctx.path,
        ctx.report,
        ctx.stores,
        resolution=(res.width or None, res.height or None),
        skip=frozenset(_text_ids(ctx)),
    )


def _core_field_kinds(ctx: ValidationContext) -> None:
    """Generic target validation against the property space (ADR 0001 decision
    11): every value a ``set``/``tween`` writes must fit the field kind its
    target's space declares — resolved by :func:`an.genres.entity_space_resolver`,
    the same policy the compiler's keyframe check uses, so validate and compile
    agree (review-244 S7). A string on a stage node's ``x`` is refused here, as
    the compiler refuses it. Entities with no registered kind are reported by
    ``entity_kinds``; an entity kind with no space (a voice) has no fields."""
    from an.genres import entity_space_resolver

    shot = ctx.shot
    space_of = entity_space_resolver(shot.entities)
    kinds = {e.id: e.kind for e in shot.entities}
    for k, top in enumerate(shot.actions):
        for flat in flatten(top):
            leaf = flat.action
            if getattr(leaf, "kind", None) not in _NODE_TARGETING_KINDS:
                continue
            prop = leaf.property
            if prop in _AUTHORING_SUGAR_PROPERTIES:
                continue  # expanded by the compiler before any channel exists
            owner = kinds.get(leaf.target.split("/", 1)[0])
            registered = entity_kind(owner) if owner is not None else None
            if owner is not None and (registered is None or registered.space is None):
                continue
            space = space_of(leaf.target)
            field_kind = space.kind_of(prop)
            for value in (
                getattr(leaf, "value", None),
                getattr(leaf, "from_value", None),
                getattr(leaf, "to_value", None),
            ):
                if value is None:
                    continue
                problem = field_kind.check(value)
                if problem:
                    who = f"a {owner}" if owner is not None else "the stage"
                    ctx.report.add(
                        "error",
                        f"{ctx.path}/actions/{k}",
                        f"{leaf.target}:{prop} is a {field_kind.name} field of "
                        f"{who} ({space.name}): {problem} — compiling this "
                        "shot raises.",
                    )


def _core_entity_refs(ctx: ValidationContext) -> None:
    """Entity references resolve?"""
    shot, path, report, mall_stores = ctx.shot, ctx.path, ctx.report, ctx.stores
    text_ids = _text_ids(ctx)
    for j, entity in enumerate(shot.entities):
        if entity.kind not in rig_stores() or entity.id in text_ids:
            continue
        store_name, want_kind = rig_stores()[entity.kind]
        store = mall_stores.get(store_name)
        if store is None:
            continue  # store not supplied → this check did not run
        registered = entity_kind(entity.kind)
        if registered is not None and registered.placeholder_on_missing:
            continue  # its genre reports a missing ref with its own check
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
        if _rig_document(entity, mall_stores) is None:
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


def _core_voices(ctx: ValidationContext) -> None:
    """Dialogue voice refs resolve? The line's own voice_ref, else the one its
    speaker is bound to — the resolver the audio pipeline speaks with (an#194)."""
    shot, path, report = ctx.shot, ctx.path, ctx.report
    available_voices = ctx.voices
    if available_voices is None:
        return
    for k, line in enumerate(shot.dialogue):
        voice_ref = line.voice_ref or speaker_voice_ref(
            line.speaker, shot, {"characters": ctx.characters}
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
            _check_voice_effects(
                report, path, k, voice_ref, available_voices, line=line
            )


def _core_dialogue_lines(ctx: ValidationContext) -> None:
    shot, path, report = ctx.shot, ctx.path, ctx.report
    for k, line in enumerate(shot.dialogue):
        if not line.text.strip():
            report.add("warning", f"{path}/dialogue/{k}/text", "empty dialogue line")
        if not line.speaker:
            report.add(
                "error",
                f"{path}/dialogue/{k}/speaker",
                "dialogue requires a speaker",
            )


def _core_dialogue_fits(ctx: ValidationContext) -> None:
    effects_of = _voice_effects_of(ctx.shot, ctx.voices, ctx.characters)
    _check_dialogue_fits(ctx.shot, ctx.path, ctx.report, effects_of=effects_of)


def _voice_effects_of(shot: Any, voices: Any, characters: Any):
    """``line -> effects`` of the voice each line of ``shot`` is spoken with.

    A voice's ``effects`` re-time every render, offline included (``tempo``,
    an#265; ``trim_silence``, an#254). ``{}`` when no voices are known or the
    voice's effects are malformed (that is its own error)."""
    if not voices:
        return lambda line: {}

    def effects_of(line: Any) -> dict:
        ref = line.voice_ref or speaker_voice_ref(
            line.speaker, shot, {"characters": characters}
        )
        if ref is None:
            ref = "default"
        try:
            return voice_effects({"voices": voices}, ref)
        except VoiceEffectError:
            return {}

    return effects_of


def _tempo_of(effects_of):
    """``line -> tempo`` from ``line -> effects`` (``1.0`` when undeclared)."""
    if effects_of is None:
        return None
    return lambda line: float(effects_of(line).get("tempo", 1.0))


def _core_assembly(ctx: ValidationContext) -> None:
    _check_assembly(ctx.scene, ctx.report, sounds=ctx.sounds)


def _core_dialogue_in_dissolve(ctx: ValidationContext) -> None:
    _check_dialogue_in_dissolves(
        ctx.scene,
        ctx.report,
        fps=ctx.memo.get(_RENDER_FPS),
        effects_of_shot=lambda shot: _voice_effects_of(
            shot, ctx.voices, ctx.characters
        ),
    )


#: A memo key: the fps a render uses, when it is not the scene's (``--fps``).
_RENDER_FPS = "render fps"


def _add_findings(report: ValidationReport, findings: Any) -> None:
    for f in findings:
        fix = f" Fix: {f.suggested_fix}" if f.suggested_fix else ""
        report.add(f.severity, f.ir_path, f"{f.description}.{fix}")


def _readable_lock(ctx: ValidationContext) -> dict[str, Any] | None:
    """The lockfile's pins, read once — or a finding saying it cannot be read."""

    def read() -> dict[str, Any] | None:
        try:
            return {k: ctx.library_lock[k] for k in ctx.library_lock}
        except Exception as e:  # noqa: BLE001 — reported, never a traceback
            ctx.report.add(
                "warning",
                "assets.lock.json",
                f"the asset library's lockfile cannot be read ({type(e).__name__}: "
                f"{e}), so no library pin was checked. Check the assets out again "
                "(an library checkout --overwrite) to rewrite it.",
            )
            return None

    if ctx.library_lock is None:
        return None
    return ctx.cached("library lock", read)


def _core_library_pins(ctx: ValidationContext) -> None:
    """Every scene ``library:`` pin agrees with the lockfile, the source of truth (an#240)."""
    lock = _readable_lock(ctx)
    if lock is None or not any(
        e.library for shot in ctx.scene.timeline for e in shot.entities
    ):
        return
    from an.library.checkout import check_pins

    _add_findings(ctx.report, check_pins(ctx.scene, lock))


def _core_library_checkouts(ctx: ValidationContext) -> None:
    """Every pinned check-out is still its version byte for byte; an edit is ``info`` (a fork)."""
    lock = _readable_lock(ctx)
    if not lock:
        return
    from an.library.checkout import drift_findings

    stores = dict(ctx.stores)
    if ctx.sounds is not None:
        stores["sounds"] = ctx.sounds
    supplied = {k: v for k, v in lock.items() if k.partition("/")[0] in stores}
    try:
        findings = drift_findings(mall=stores, lock=supplied)
    except Exception as e:  # noqa: BLE001 — a library that cannot be read is a finding
        ctx.report.add(
            "warning",
            "assets.lock.json",
            f"the pinned check-outs could not be compared with their library "
            f"versions ({type(e).__name__}: {e})",
        )
        return
    _add_findings(ctx.report, findings)


# -----------------------------------------------------------------------------
# The cut-out genre's checks, as context functions. The genre object
# (`an.genres.cutout.CUTOUT`) registers them; the core never runs them on its
# own. They live here until the genre package exists (P8 moves them).
# -----------------------------------------------------------------------------


def _register_core_checks() -> None:
    """The core's checks. The gaps in ``order`` are where the cut-out genre's
    land (its `play` and `expression` checks at 40-41, turns at 60-61, view
    continuity at 10 of ``finish``), which keeps a report's order exactly
    what it was when all of them were one function."""
    for check in (
        SemanticCheck("retired_keys", _core_retired_keys, stage="scene", order=10),
        SemanticCheck("meta", _core_meta, stage="scene", order=20),
        SemanticCheck("easings", _core_easings, stage="scene", order=30),
        SemanticCheck("has_shots", _core_has_shots, stage="scene", order=40),
        SemanticCheck("action_kinds", _core_action_kinds, stage="scene", order=1),
        SemanticCheck("entity_kinds", _core_entity_kinds, stage="scene", order=2),
        SemanticCheck("renderer", _core_renderer, order=3),
        SemanticCheck("shot_basics", _core_shot_basics, order=10),
        SemanticCheck("renderable", _core_renderable, order=20),
        SemanticCheck("framing", _core_framing, order=30),
        SemanticCheck("swap_references", _core_swap_references, order=50),
        SemanticCheck("trim_targets", _core_trim_targets, order=70),
        SemanticCheck("text_blocks", _core_text_blocks, order=80),
        SemanticCheck("action_targets", _core_action_targets, order=90),
        SemanticCheck("field_kinds", _core_field_kinds, order=95),
        SemanticCheck("entity_refs", _core_entity_refs, order=100),
        SemanticCheck("voices", _core_voices, order=110),
        SemanticCheck("dialogue_lines", _core_dialogue_lines, order=120),
        SemanticCheck("dialogue_fits", _core_dialogue_fits, order=130),
        SemanticCheck("assembly", _core_assembly, stage="finish", order=20),
        SemanticCheck(
            "dialogue_in_dissolve",
            _core_dialogue_in_dissolve,
            stage="finish",
            order=21,
            description="no line is heard during a dissolve (over the other shot's picture)",
        ),
        SemanticCheck(
            "library_pins",
            _core_library_pins,
            stage="finish",
            order=30,
            description="a scene's `library:` pins agree with assets.lock.json",
        ),
        SemanticCheck(
            "library_checkouts",
            _core_library_checkouts,
            stage="finish",
            order=31,
            description="a pinned check-out is still its library version (info when edited)",
        ),
    ):
        if check.name not in check_names(owner=CORE_OWNER):
            register_check(check, owner=CORE_OWNER)


#: Slack before a line counts as running past its shot: a frame at 60 fps.
DIALOGUE_OVERRUN_TOLERANCE_S: float = 1 / 60


def _dialogue_layout(shot: Any, *, tempo_of=None):
    """``(k, line, start, end, estimated)`` for each dialogue line of ``shot``.

    Where each line WILL play: the audio pipeline's own rule
    (:meth:`an.ir.schema.Dialogue.planned_start`) over the real duration when
    the line was synthesized, else the offline voice's estimate
    (:func:`an.audio.offline_tts.estimate_speech_duration`) divided by the
    line's voice ``tempo`` (``tempo_of(line)``; an#265 — the effect applies
    under every provider). Never the stamped ``start``, which a pause edited
    since the last synthesis has made stale.
    """
    from an.audio.offline_tts import estimate_speech_duration

    cursor = 0.0
    for k, line in enumerate(shot.dialogue):
        estimated = line.duration is None
        length = (
            estimate_speech_duration(line.text) / (tempo_of(line) if tempo_of else 1.0)
            if estimated
            else float(line.duration)
        )
        start = line.planned_start(cursor)
        cursor = start + length
        yield k, line, start, cursor, estimated


def _check_dialogue_fits(
    shot: Any, path: str, report: "ValidationReport", *, effects_of=None
) -> None:
    """Warn when a shot's dialogue runs past the shot's end
    (:func:`shot_dialogue_overruns`).

    Also warns when a speaker's line starts before that speaker's previous
    line ends: one mouth cannot say two lines (an ``at`` can do that; a
    ``pause`` cannot). Two speakers talking over each other is legal.
    """
    speaking_until: dict[str, tuple[int, float]] = {}
    for k, line, start, end, estimated in _dialogue_layout(
        shot, tempo_of=_tempo_of(effects_of)
    ):
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
    for k, message in shot_dialogue_overruns(shot, effects_of=effects_of):
        report.add("warning", f"{path}/dialogue/{k}", message)


def shot_dialogue_overruns(
    shot: Any,
    *,
    effects_of=None,
    synthesized_only: bool = False,
    tolerance_s: float = DIALOGUE_OVERRUN_TOLERANCE_S,
) -> list[tuple[int, str]]:
    """``(k, message)`` for each line of ``shot`` that ends past the shot's end.

    The ONE overrun check: ``an validate`` runs it, the audio pipeline runs it
    after synthesis (:func:`an.audio.pipeline.dialogue_overruns`), and ``an
    render`` reports it from the rendered timing (:func:`post_synthesis_findings`).

    The audio is cut at the shot end (each shot's mix is trimmed to its
    duration), and the lines play back to back, so a shot shortened below its
    dialogue loses the tail of it — silently, until now (an e2e run shrank an
    8.2 s shot holding 7.1 s of speech to 3.0 s and `an validate` said nothing).

    What is known depends on when this runs. After the audio pipeline, a line
    carries its real ``duration`` and the check is exact. Before it, the
    duration is the offline voice's estimate
    (:func:`an.audio.offline_tts.estimate_speech_duration` over the voice's
    ``tempo`` — exactly what an offline render will give, and an
    under-estimate for a real voice). Either
    way the lines are laid out by the pipeline's own rule,
    :meth:`an.ir.schema.Dialogue.planned_start` — back to back from the shot
    start, shifted by each line's ``pause`` or pinned by its ``at`` (an#187) —
    so a pause edited after synthesis is judged where it will play, not where
    the stale stamp says. ``effects_of`` (``line -> `` its voice's normalised
    effects) supplies the tempo, and — for a synthesized line whose voice does
    not trim — the fix of trimming the silence a real voice pads a line with.

    >>> from an.ir.schema import Dialogue, Shot
    >>> shot = Shot(id="s", duration=1.0, dialogue=[
    ...     Dialogue(speaker="a", text="hi", start=0.2, duration=1.3, audio_ref="k")])
    >>> [(k, m[:44]) for k, m in shot_dialogue_overruns(shot)]
    [(0, 'line 0 (a) ends at 1.30s as synthesized, pas')]
    """
    out = []
    tempo_of = _tempo_of(effects_of)
    for k, line, _start, end, estimated in _dialogue_layout(shot, tempo_of=tempo_of):
        if end <= shot.duration + tolerance_s or (synthesized_only and estimated):
            continue
        tempo = tempo_of(line) if (tempo_of and estimated) else 1.0
        how = (
            "at the offline voice's rate"
            + (f" and its voice's tempo {tempo:g}" if tempo != 1.0 else "")
            + " (a real voice is usually slower)"
            if estimated
            else "as synthesized"
        )
        trims = TRIM_SILENCE in (effects_of(line) if effects_of else {})
        fix = (
            f"Lengthen the shot to at least {end:.2f}s, shorten the line, or move "
            "it to the next shot"
            + (
                ""
                if estimated or trims
                else ", or trim the silence a voice pads a line with (`effects: "
                "{trim_silence: true}` on its voice document)"
            )
        )
        out.append(
            (
                k,
                f"line {k} ({line.speaker}) ends at {end:.2f}s {how}, past the shot's "
                f"{shot.duration:g}s end, so its last {end - shot.duration:.2f}s are "
                f"cut off: the shot's audio stops where the shot does. {fix}",
            )
        )
    return out


#: The registered checks whose answer depends on what synthesis produced — a
#: line's real length, hence where it starts and ends — and that ``an render``
#: therefore runs again AFTER the audio pipeline, on the timing it will mux
#: (:func:`post_synthesis_findings` runs exactly these, by name, through the
#: registry). A check added later that reads ``Dialogue.duration`` or ``start``
#: belongs here; ``tests/test_render_findings.py`` lists the ones that do.
POST_SYNTHESIS_CHECKS: tuple[str, ...] = (
    "dialogue_fits",
    "dialogue_in_dissolve",
    "cutout.hidden_mouth_while_speaking",
)


def post_synthesis_findings(
    scene: SceneIR,
    *,
    fps: float | None = None,
    checks: tuple[str, ...] = POST_SYNTHESIS_CHECKS,
    **stores: Mapping[str, Any] | None,
) -> list[tuple[str, ValidationFinding]]:
    """``(check, finding)`` for each finding the synthesized timing gives.

    The SAME registered checks ``an validate`` runs, selected by name
    (:data:`POST_SYNTHESIS_CHECKS`): dialogue past its shot's end, a speaker
    overlapping themself, a line heard during a dissolve, a line spoken while
    the speaker's view hides its mouth. ``an render`` calls this once the audio
    pipeline has stamped every line's real ``duration``, so what ``an validate``
    could only estimate is reported exactly, at the moment it becomes known
    (an#254). ``fps`` is the render's (it decides the dissolve overlaps);
    default the scene's. ``stores`` are :func:`validate_semantic`'s
    ``available_*`` keywords. A check no loaded genre registered is skipped.
    """
    out: list[tuple[str, ValidationFinding]] = []
    for name in checks:
        report = validate_semantic(scene, only=(name,), fps=fps, **stores)
        out += [(name, f) for f in report.findings]
    return out


def _check_dialogue_in_dissolves(
    scene: SceneIR,
    report: "ValidationReport",
    *,
    fps: float | None = None,
    effects_of_shot=None,
) -> None:
    """A dissolve plays both shots' audio in the overlap: a line there is heard
    over the other shot's picture. Legal, and worth a word — with where the line
    plays and where the overlap is, laid out like :func:`shot_dialogue_overruns`
    (real durations once synthesized, the offline estimate over the voice's
    ``tempo`` before). Silent when the transitions themselves are refused."""
    from an.assemble import film_timeline, transition_problems

    fps = fps if fps is not None else scene.meta.fps
    if not fps or fps <= 0 or transition_problems(scene.timeline, fps):
        return
    timeline = film_timeline(scene.timeline, fps=fps)
    n = len(scene.timeline)
    for i, shot in enumerate(scene.timeline):
        overlap_out = timeline.dissolve_in[i + 1] / fps if i + 1 < n else 0.0
        overlap_in = timeline.dissolve_in[i] / fps
        effects_of = effects_of_shot(shot) if effects_of_shot else None
        layout = _dialogue_layout(shot, tempo_of=_tempo_of(effects_of))
        for k, line, start, end, estimated in layout:
            where = []
            if overlap_in and start < overlap_in:
                where.append(
                    f"the dissolve from shot {scene.timeline[i - 1].id!r} "
                    f"(0-{overlap_in:.2f}s)"
                )
            if overlap_out and end > shot.duration - overlap_out:
                where.append(
                    f"the dissolve into shot {scene.timeline[i + 1].id!r} "
                    f"({shot.duration - overlap_out:.2f}-{shot.duration:g}s)"
                )
            if not where:
                continue
            trims = TRIM_SILENCE in (effects_of(line) if effects_of else {})
            report.add(
                "warning",
                f"timeline/{i}/dialogue/{k}",
                f"this line plays during a dissolve: line {k} ({line.speaker}) "
                f"plays {start:.2f}-{end:.2f}s"
                + (" (at the offline voice's rate)" if estimated else "")
                + f", inside {' and '.join(where)}, so it is heard over the "
                "neighbouring shot's picture too; move it clear of the overlap or "
                "shorten the dissolve"
                + (
                    ""
                    if estimated or trims
                    else ", or trim the silence its voice pads it with (`effects: "
                    "{trim_silence: true}`)"
                ),
            )


def _check_assembly(
    scene: SceneIR,
    report: "ValidationReport",
    *,
    sounds: Mapping[str, Any] | None,
) -> None:
    """Transitions and the sound layer (`an.assemble`): what assembling the film
    would refuse is an error here, from the SAME list the assembler raises on."""
    from an.assemble import transition_problems

    fps = scene.meta.fps
    if fps <= 0:
        return  # already its own error
    problems = transition_problems(scene.timeline, fps)
    for i, message in problems:
        report.add("error", f"timeline/{i}/transition", message)

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
    durations: dict[str, str | None] = {}  # one read of each sound, however many cues
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
        if cue.sound not in durations:
            durations[cue.sound] = _sound_duration_problem(sounds, cue.sound)
        if durations[cue.sound]:
            report.add("warning", path, durations[cue.sound])
        source = (sounds[cue.sound] or {}).get("source") or {}
        if not source.get("license"):
            report.add(
                "warning",
                path,
                f"sound {cue.sound!r} has no recorded licence; `an credits` "
                "reports it UNVERIFIED — unknown is not unencumbered",
            )


def _sound_duration_problem(sounds: Mapping[str, Any], key: str) -> str | None:
    """What is wrong with a sound's recorded ``duration``, if its audio says
    otherwise (an#330: a WAV cut to a pipe recorded its streaming header,
    ~22369 s). The mix measures the audio itself, so this only says the record
    is wrong — and how to fix it where it came from."""
    from an.sounds import DURATION_TOLERANCE_S, SoundError, wav_duration

    record = sounds[key] or {}
    read_audio = getattr(sounds, "read_audio", None)
    try:
        recorded = float(record.get("duration"))
    except (TypeError, ValueError):
        return None
    if read_audio is None:
        return None
    try:
        actual = wav_duration(read_audio(key))
    except (SoundError, OSError, KeyError):
        return None  # unreadable audio is the render's error to raise, with its fix
    if abs(recorded - actual) <= DURATION_TOLERANCE_S:
        return None
    from_library = bool((record.get("metadata") or {}).get("library_origin"))
    fix = (
        "it was checked out from a library: publish a corrected version there "
        "(re-adding it here would fork the pin)"
        if from_library
        else "re-add it with an.sounds.add_sound (which measures the audio)"
    )
    return (
        f"sound {key!r} records a duration of {recorded:g} s but its audio is "
        f"{actual:g} s (a WAV written to a pipe states no length, or the file "
        f"was cut); the mix uses the audio's. Fix the record: {fix}"
    )


_register_core_checks()
