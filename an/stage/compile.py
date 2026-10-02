"""Compile a top-level `Shot` (renderer="cutout") into a `CutoutSceneJSON`.

This is the bridge between the renderer-agnostic `an.ir` types and the
cutout-specific JSON contract that the JS runtime will consume in Phase 2B.

Strategy:

1. **Resolve entities** from the project mall: each `AssetRef` in
   ``shot.entities`` becomes a sub-tree of the cutout scene (a character with
   placeholder rect parts when the character store has no sidecar art yet).
2. **Flatten authoring actions** via `an.ir.compose.flatten` — every
   `tween`/`set`/`play`/composition produces leaf `FlatAction`s with
   absolute times.
3. **Compile each FlatAction to PlacedClipJSON entries** on the appropriate
   track. Tween → a 2-keyframe AnimationClipJSON + a PlacedClipJSON (or, under
   ``step_hz``, a grid of step-eased keyframes — an#89). Set →
   a step channel that HOLDS until the next action on the same
   target/property. Play → a per-instance clip (``__play__{n}``) resolved
   from the target's descriptor animation (an#7).

The compiler is deterministic and side-effect-free (it doesn't write to the
mall). It reads only.

>>> from an.ir.schema import Meta, SceneIR, Shot
>>> from an.stage.compile import compile_shot
>>> shot = Shot(id="s1", renderer="cutout", duration=2.0)
>>> j = compile_shot(shot, mall={"characters": {}})
>>> j.timeline.duration
2.0
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import re
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from an.base import (
    DEFAULT_RESOLUTION,
    TRANSFORM_PROPERTIES,
    TRIM_PROPERTIES,
    swap_set_name_problem,
)
from an.stage.easing import apply_easing
from an.stage.rig import (
    Attachment,
    Bone,
    Skin,
    attachment_box,
    drawn_attachment,
    primary_slot_per_bone,
)
from an.genres import action_kind, action_kind_names, entity_kind, entity_space_resolver
from an.genres.registry import CompilePass
from an.stage.path_geometry import flatten_curve
from an.ir.compose import FlatAction, flatten
from an.ir.schema import (
    CameraKey,
    Action,
    AssetRef,
    SetAction,
    Shot,
    TweenAction,
)

from an.stage.serialize import (
    AnimationClipJSON,
    AssetJSON,
    AssetResolutionJSON,
    AssetsJSON,
    ChannelJSON,
    CutoutSceneJSON,
    CutoutSceneMetaJSON,
    KeyframeJSON,
    NodeJSON,
    PlacedClipJSON,
    TimelineJSON,
    TrackJSON,
    TransformJSON,
    VisualJSON,
    PathJSON,
)
from an.stage.raster import art_size, is_raster, short_digest, versioned_src
from an.ir.camera import CAMERA_MOVES, PAN_FRACTION, CameraError  # noqa: F401  (re-exported)
from an.ir.camera import camera_keys as _camera_keys
from an.ir.migrate import DocumentKind, migrate
from an.stage.environments import PLANE_FILL_SPAN as _PLANE_FILL_SPAN
from an.stage.environments import (
    ENVIRONMENT_DOCUMENT_KIND,
    EnvironmentDescriptor,
    Plane,
)
from an.stage.props import PROP_DOCUMENT_KIND, PropDescriptor
from an.stage.paths import PATH_DOCUMENT_KIND, PathDescriptor, resolve_path
from an.stage.text_layout import build_text_subtree, svg_data_uri, text_document  # noqa: F401  (re-exported)
from an.stage.text import font_base_dir, text_entity_problem
from an.paint import Gradient
from an.styles import STYLE_DOCUMENT_KIND, StylePack, resolve_palette, surface_for
from an.stage.surface import (
    apply_surface,
    faded_treated_targets,
    grain_node,
)







def style_pack_for(scene_meta, styles_store: Mapping) -> "StylePack | None":
    """The `StylePack` a scene declares, or ``None`` (an#112).

    ``None`` for every document written before an#112 and for every scene that
    declares no pack — which is what makes this feature byte-identity-free: the
    no-pack path is a lookup with a default, not a rewrite.

    A declared pack that is missing, or is not a `StylePack`, RAISES. An art
    direction the author asked for and did not get is a different picture that
    renders happily, which is the an#33 failure this package refuses everywhere
    else.
    """
    key = getattr(scene_meta, "style_pack", None)
    if not key:
        return None
    raw = None
    if key in styles_store:
        try:
            raw = styles_store[key]
        except KeyError:
            raw = None
    if not isinstance(raw, dict) or raw.get("kind") != STYLE_DOCUMENT_KIND.name:
        raise CutoutCompileError(
            f"the scene declares style_pack={key!r}, which is "
            + ("not a StylePack" if raw is not None else "not in the styles store")
            + ". A pack the author asked for and did not get is a DIFFERENT "
            "picture that renders happily — the failure an#33 exists to stop. "
            "Create it, or remove `style_pack` from the scene's meta."
        )
    return StylePack.model_validate(migrate(dict(raw), kind=STYLE_DOCUMENT_KIND.name))


def _warn_about_art_a_pack_cannot_reach(
    pack: "StylePack | None", reached: set[str], skipped: set[str]
) -> None:
    """Say, in ONE line, which rigs the pack could not recolour.

    A pack recolours what the COMPILER decides and SVG art whose descriptor
    tags its colour roles (`colour_roles`, written by the character factory).
    Untagged SVG art — hand-drawn, DiceBear — renders exactly as drawn, and the
    author has to hear that from the compiler rather than from the frames.

    The text depends only on the pack and the untagged rigs, never on the shot
    or on what WAS reached, so Python's warning registry shows it once per
    process per distinct set: one line for a scene whose cast does not change,
    not a paragraph per shot (the e2e style test counted ~5 wrapped lines per
    shot). A cast that changes between shots gets one line per distinct set.
    """
    if pack is None or not skipped or not (pack.roles or pack.entities):
        # A pack with no colour roles (surface treatments only, say) has
        # nothing it could have failed to recolour.
        return
    also = (
        " Its surface treatments (outline, shadow, glow) are copies, not "
        "recolours, and those do reach them (an#163)."
        if pack.surface is not None or pack.entity_surfaces
        else ""
    )
    warnings.warn(
        f"style pack {pack.name!r} could not reach {sorted(skipped)}: that SVG "
        "art carries no colour role for what the pack sets (hand-drawn or "
        "DiceBear art is untagged), so it renders as drawn; "
        "`an character new --offline` tags every part." + also,
        CutoutCompileWarning,
        stacklevel=3,
    )


def _has_raster_parts(desc_data: Mapping[str, Any]) -> bool:
    """Whether any attachment of any skin of a rig document is raster art."""
    for skin in (desc_data.get("skins") or {}).values():
        for attachments in ((skin or {}).get("slots") or {}).values():
            for att in (attachments or {}).values():
                if isinstance(att, Mapping) and is_raster(att.get("path") or ""):
                    return True
    return False


def _note_raster_rig(
    entity: AssetRef,
    desc_data: Mapping[str, Any],
    pack: "StylePack | None",
    raster: set[str] | None,
) -> None:
    """Record a rig with raster parts that a colour-setting pack is applied to."""
    if (
        raster is not None
        and pack is not None
        and (pack.roles or pack.entities)
        and _has_raster_parts(desc_data)
    ):
        raster.add(entity.id)


def _warn_raster_parts_not_recoloured(
    pack: "StylePack | None", raster: set[str]
) -> None:
    """Say ONCE that a pack's colours do not reach raster parts (an#211).

    A raster part's colours are pixels, not literals a descriptor can tag, so
    a StylePack leaves it exactly as drawn. Stable text (the pack and the rigs,
    nothing shot-specific), so Python's registry shows it once per process per
    distinct set, like the untagged-art warning beside it.
    """
    if pack is None or not raster:
        return
    warnings.warn(
        f"style pack {pack.name!r}: {sorted(raster)} carry raster (PNG/JPEG/WebP) "
        "parts, which a pack cannot recolour — their colours are pixels, not "
        "tagged literals — so those parts render as drawn. Surface treatments "
        "(outline, shadow, glow) still reach them.",
        CutoutCompileWarning,
        stacklevel=3,
    )











def _warn_surface(notes: list[str]) -> None:
    """Say what a surface treatment could not do (an#163) — never silently."""
    for note in notes:
        warnings.warn(f"surface treatment: {note}", CutoutCompileWarning, stacklevel=3)






PROCEDURAL_MOUTH_SETS: frozenset[str] = frozenset({"viseme"})









#: The authored spelling of a per-node colour multiply, and the three channels
#: the compiler expands it into (an#62).
#:
#: One authored property, three channels, and the split is deliberate. Colour
#: interpolation could have been a third mode in `channel.evaluate` — it lerps
#: numbers and SNAPS everything else (an#86) — but that evaluator has a twin in
#: `runtime.js` kept in step by `tests/test_cutout_channel_parity.py`, and the
#: parity test exists because the two have drifted before. Expanding here means
#: the per-channel lerp IS the existing numeric path and neither evaluator ever
#: learns what a colour is.
#: `#rrggbb` only — no shorthand, no alpha channel. A three-digit form would
#: be a second spelling of the same colour, and `#rrggbbaa` would silently
#: drop its alpha, since `tint` is a multiply and opacity is `alpha`.
_HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{6}")

TINT_PROPERTY: str = "tint"
TINT_COMPONENTS: tuple[str, str, str] = ("tint_r", "tint_g", "tint_b")


def _property_rest_values() -> dict[str, float]:
    """Rest ("identity") value per animatable property, derived from the schema.

    A tween that declares no ``from_value`` starts from the value its property
    has at that moment (an#212, :func:`_value_at`) — and with nothing placed or
    animated before it, that is this rest value. This is not cosmetic: offsets and rotations rest at 0.0, but the
    *multiplicative* properties rest at 1.0, and defaulting all of them to 0.0
    silently breaks the two most obvious uses of a tween — a fade-out (``alpha``
    starting at 0 is already invisible, so the fade never happens and the
    element simply is not there) and a scale move (the subject pops in from
    nothing). Nothing had noticed because the camera builds its own explicit
    keyframes and no example authors a scale or alpha tween.

    **Derived, not restated.** A node's rest pose *is* ``TransformJSON``'s field
    defaults, so reading them off the model keeps one source of truth; a
    hand-maintained copy would be a second place to forget.
    """
    rest = {
        name: float(field.default)
        for name, field in TransformJSON.model_fields.items()
        if isinstance(field.default, (int, float))
        and not isinstance(field.default, bool)
    }
    # `rotation_rad` is an accepted alias for `rotation` in the runtime's
    # property switch; it is not a schema field, so it has to be added here
    # rather than derived.
    rest["rotation_rad"] = rest["rotation"]
    # `tint_r/g/b` (an#62) are the same kind of exception, for a reason worth
    # stating: they are ANIMATION-channel properties the runtime applies, not
    # node rest state. Putting them on `TransformJSON` would add three defaulted
    # fields to every serialized node and move all ten corpus contract hashes —
    # for a feature almost no scene uses — and a node with no tint channel is
    # already untinted, because the runtime's own default is white. They rest at
    # 1.0 because tint is a MULTIPLY: 1.0 is the identity, and the 0.0 default
    # would render every untweened rig black.
    for component in TINT_COMPONENTS:
        rest[component] = 1.0
    # `trim_start`/`trim_end` (an#160) are the same kind of exception: channel
    # properties of a PATH node's visual, not node rest state. The rest is the
    # fully drawn path, so a draw-on names its `from_value` (0).
    rest["trim_start"] = 0.0
    rest["trim_end"] = 1.0
    rest["dash_offset"] = 0.0  # an#161: a path's dash phase, same exception
    return rest


#: See :func:`_property_rest_values`.
_PROPERTY_REST_VALUES: dict[str, float] = _property_rest_values()


#: Every property name the JS runtime's ``applyProperty`` STATIC switch
#: implements — exactly the numeric transform vocabulary (the rest-value SSOT
#: above). This is the Python side of the two-evaluator drift gate:
#: ``tests/test_loud_discards.py`` extracts the runtime's actual switch cases
#: and asserts exact equality with this set, in both directions. It replaced
#: ``pose.py``'s allow-list when the Python applier was deleted (an#86).
#: Any OTHER property is a swap-set name, applied dynamically through the
#: node's ``asset_sets`` projection (an#87) — ``viseme`` left the static
#: switch when that landed, which is precisely what makes it a conventional
#: set name rather than control flow.
RUNTIME_APPLIED_PROPERTIES: frozenset[str] = frozenset(_PROPERTY_REST_VALUES)


class CutoutCompileError(ValueError):
    """A shot cannot be compiled to a cutout scene. Carries actionable detail.

    A ``ValueError`` rather than a ``RuntimeError`` — unlike the rest of this
    package's error tree — because every one of these is "this value is not in
    the known set", which is the existing idiom for argument-level rejection.
    The render-time errors stay ``RuntimeError``: they are failures of the
    machinery, not of the input.
    """


class CutoutCompileWarning(UserWarning):
    """A shot compiles, but something in it will not reach the screen.

    The line between this and :class:`CutoutCompileError` is whether the author
    could plausibly have meant it. An unknown ``camera.move`` is always a
    mistake, so it raises. A speaker with no mouth is usually an off-screen
    narrator and occasionally a typo — refusing it would break the documented
    idiom, and passing in silence is what this whole change is against.
    """


def _rest_value_for(prop: str, target: str) -> float:
    """The identity of ``prop`` — the implicit start of a tween on a node
    nothing has placed or moved (:func:`_built_value`) — or refuse to invent one.

    A property with no numeric identity — a viseme code, a colour — has no
    meaningful "start from rest". Substituting 0.0 does not mean "unchanged", it
    means *zero*, and the renderer will happily apply it: a colour-valued tween
    with an implicit 0.0 start renders its subject solid black for the whole
    shot, silently. So this raises rather than guessing.
    """
    if prop in _PROPERTY_REST_VALUES:
        return _PROPERTY_REST_VALUES[prop]
    raise CutoutCompileError(
        f"tween on {target!r}:{prop!r} has no from_value, and {prop!r} has no "
        f"rest value to start from (known: {sorted(_PROPERTY_REST_VALUES)}). "
        "Give the action an explicit from_value, or use a `set` action if you "
        "meant to change it discretely — a tween cannot interpolate from a "
        "value that does not exist, and defaulting it to 0 would render as "
        "'fully transparent' / 'black' / 'scaled to nothing' rather than as "
        "'unchanged'."
    )


#: Fallback for a property with no declared rest value.
#:
#: Reachable only by a property that is neither a transform field nor an alias —
#: i.e. a discrete one such as ``viseme``, for which no numeric identity is
#: meaningful. Multiplying such a property by an implicit 0.0 is how a
#: colour-valued tween would render its subject solid black, so the compiler
#: refuses instead: see :func:`_rest_value_for`.
_DFLT_PROPERTY_REST_VALUE: float | None = None

# The emotion → brow-tilt table that lived here is retired (an#98): `[emotion]`
# is sugar for an `expression` leaf, resolved by the face solver
# (`_add_face_clips`) from `an.expression.presets`.


def _runtime_node_paths(node: NodeJSON, prefix: str = "") -> set[str]:
    """Every path the JS runtime will index for ``node``'s subtree.

    Mirrors ``buildSceneTree``, including the detail that the synthetic top-level
    ``root`` container is NOT indexed — the compiler emits target paths starting
    at the entity name. Getting that wrong here would make every check below
    off by one segment.
    """
    paths = set()
    path = f"{prefix}/{node.name}" if prefix else node.name
    if prefix or node.name != "root":
        paths.add(path)
        child_prefix = path
    else:
        child_prefix = ""  # skip the synthetic root, as the runtime does
    for child in node.children:
        paths |= _runtime_node_paths(child, child_prefix)
    return paths


#: How many "did you mean" paths an unknown-target message offers.
DFLT_TARGET_SUGGESTIONS: int = 3
#: `difflib` similarity a path must reach to be offered as a suggestion.
_TARGET_SUGGESTION_CUTOFF: float = 0.6
#: The runtime's camera node: indexed by the runtime, absent from the tree.
CAMERA_NODE: str = "root"


def node_path_suggestions(
    target: str, paths: Iterable[str], *, n: int = DFLT_TARGET_SUGGESTIONS
) -> list[str]:
    """The built node paths a mistyped ``target`` most plausibly meant.

    The paths of the SAME entity that end in the same part name — the usual
    mistake is a missing level (``ned/left_brow`` for ``ned/head/left_brow``)
    — or, when there are none, the closest spellings.

    >>> built = ["ned", "ned/head", "ned/head/left_brow", "ned/head/mouth", "ned/arm_l"]
    >>> node_path_suggestions("ned/left_brow", built)
    ['ned/head/left_brow']
    >>> node_path_suggestions("ned/arm_x", built)
    ['ned/arm_l']
    >>> node_path_suggestions("zzz", built)
    []
    """
    import difflib

    paths = sorted(set(paths))
    entity, _, _ = target.partition("/")
    leaf = target.rsplit("/", 1)[-1]
    same_leaf = [
        p
        for p in paths
        if p != target and p.split("/", 1)[0] == entity and p.rsplit("/", 1)[-1] == leaf
    ]
    if same_leaf:  # a part found by name beats any spelling guess
        return same_leaf[:n]
    return difflib.get_close_matches(
        target, paths, n=n, cutoff=_TARGET_SUGGESTION_CUTOFF
    )


def unknown_target_message(target: str, paths: Iterable[str]) -> str:
    """One sentence saying ``target`` is not a built node, with suggestions.

    Shared by the compiler (which raises it) and ``an validate`` (which
    reports it), so the two say the same thing about the same path.

    >>> print(unknown_target_message("ned/mouth", ["ned", "ned/head", "ned/head/mouth"]))
    'ned/mouth' is not a node of the built scene; did you mean 'ned/head/mouth'? (nodes of 'ned': ['ned', 'ned/head', 'ned/head/mouth'])
    """
    paths = sorted(set(paths))
    entity = target.split("/", 1)[0]
    msg = f"{target!r} is not a node of the built scene"
    suggestions = node_path_suggestions(target, paths)
    if suggestions:
        msg += "; did you mean " + " or ".join(repr(s) for s in suggestions) + "?"
    own = [p for p in paths if p.split("/", 1)[0] == entity]
    if own:
        msg += f" (nodes of {entity!r}: {own})"
    else:
        entities = sorted({p.split("/", 1)[0] for p in paths})
        msg += f" (no entity {entity!r}; entities: {entities})"
    return msg


def _check_channel_targets(
    animations: Mapping[str, AnimationClipJSON], paths: frozenset[str], *, shot_id: str
) -> None:
    """Refuse a channel whose target the runtime will not find (an#193).

    The runtime throws on an unknown node from inside the frame loop, which
    reached the author as a JavaScript stack trace from Chromium. Every channel
    is swept here, after every emission pass, so authored, preset and
    generated targets are all held to the tree that was actually built.
    """
    known = paths | {CAMERA_NODE}
    for clip in animations.values():
        for channel in clip.channels:
            if channel.target not in known:
                raise CutoutCompileError(
                    f"shot {shot_id!r}: a {channel.property!r} animation targets "
                    f"an unknown node — {unknown_target_message(channel.target, paths)}."
                )


@dataclass(frozen=True)
class _SwapVocabulary:
    """What the built scene can swap, and what the descriptors declare.

    The compiler's one source of swap truth for a shot (an#87), built AFTER
    the scene tree so ``node_sets`` reflects what actually resolved:

    - ``node_sets`` — node path → set name → {KEY: texture alias}: the per-slot
      projections stamped on each visual (``VisualJSON.asset_sets``). The
      procedural drawn mouth is in here too — it declares its set on its
      visual like everything else, so nothing below names a set specially.
    - ``node_asset_ids`` — node path → the visual's default texture alias,
      which is what makes a set's REST key derivable (the key whose alias is
      the default attachment).
    - ``declared`` — entity id → set name → declared keys, from the MIGRATED
      descriptor. Declared-but-unresolved (art missing) is the escalation
      case; undeclared is an authoring error. Entities without a descriptor
      are absent, and their built nodes' sets ARE their declaration.
    - ``paths`` — every node path the runtime will index (targets check).
    """

    node_sets: dict[str, dict[str, dict[str, str]]]
    node_asset_ids: dict[str, str | None]
    declared: dict[str, dict[str, frozenset[str]]]
    paths: frozenset[str]
    #: entity id → set → {KEY: attachment name}, as DECLARED (an#7 needs the
    #: attachment names: descriptor animation tracks name attachments).
    declared_maps: dict[str, dict[str, dict[str, str]]] = field(default_factory=dict)
    #: entity id → its MIGRATED descriptor (an#7: `play` resolves against
    #: it through `an.characters.play`, the same code `an validate` runs).
    descriptors: dict[str, Any] = field(default_factory=dict)
    #: entity id → `rel_path -> art on disk`, or None when the store cannot
    #: say (then every declared attachment is assumed present — the part
    #: probe's own rule, so resolution and the rig builder agree).
    art_exists: dict[str, Callable[[str], bool] | None] = field(default_factory=dict)
    #: node path → its rest transform, so a descriptor animation's DEVIATIONS
    #: can be turned into the absolute values channels carry.
    node_transforms: dict[str, TransformJSON] = field(default_factory=dict)
    #: entity id → k, the view_box → scene-pixel factor its rig was built with.
    entity_scale: dict[str, float] = field(default_factory=dict)
    #: target → its property space (:func:`an.genres.entity_space_resolver`),
    #: the policy `an validate` checks values with too (review-244 S7).
    space_of: Callable[[str], Any] | None = None
    #: Node paths whose visual is a stroked path — the only nodes a
    #: `trim_start`/`trim_end` channel may target (an#160).
    path_nodes: frozenset[str] = frozenset()
    #: entity id → its kind (`AssetRef.kind`): which entities resolve their
    #: methods on the capability registry (characters, an#248).
    entity_kinds: dict[str, str] = field(default_factory=dict)
    #: path node → {trim property: the value its document starts at}. A trim
    #: tween with no `from_value` starts HERE, not at the global rest value:
    #: a document with `trim_end: 0` authored as "tween trim_end to 1" is a
    #: draw-on, and starting it at 1.0 drew the whole path from frame 0.
    path_trims: dict[str, dict[str, float]] = field(default_factory=dict)

    def swap_capable_paths(self, entity_id: str, set_name: str) -> list[str]:
        """Node paths under ``entity_id`` that can apply ``set_name``."""
        return sorted(
            p
            for p, sets in self.node_sets.items()
            if p.split("/", 1)[0] == entity_id and set_name in sets
        )

    def rest_key(self, path: str, set_name: str) -> str | None:
        """The key a node shows at rest for ``set_name``, or None.

        The key whose alias is the visual's default texture — for an SVG
        mouth the slot's default attachment, for the drawn mouth (whose keys
        map to themselves) the runtime's initial ``X``. Derived, so a viseme
        vocabulary other than Rhubarb's (MPEG-4 numbers, Azure names) still
        knows how to close the mouth.
        """
        key_map = self.node_sets.get(path, {}).get(set_name) or {}
        asset_id = self.node_asset_ids.get(path)
        for key, alias in key_map.items():
            if alias == asset_id:
                return key
        if asset_id is None and "X" in key_map:
            return "X"
        return None


def _swap_vocabulary(
    root: NodeJSON, shot: Shot, mall: Mapping[str, Mapping]
) -> _SwapVocabulary:
    node_sets: dict[str, dict[str, dict[str, str]]] = {}
    node_asset_ids: dict[str, str | None] = {}
    node_transforms: dict[str, TransformJSON] = {}
    path_nodes: set[str] = set()
    path_trims: dict[str, dict[str, float]] = {}

    def walk(node: NodeJSON, prefix: str) -> None:
        path = f"{prefix}/{node.name}" if prefix else node.name
        if prefix or node.name != "root":
            node_transforms[path] = node.transform
            v = node.visual
            if v is not None and v.kind == "path":
                path_nodes.add(path)
                if v.path is not None:
                    path_trims[path] = {
                        "trim_start": v.path.trim_start,
                        "trim_end": v.path.trim_end,
                    }
                    if v.path.dash > 0:  # only a dashed path has an offset
                        path_trims[path]["dash_offset"] = v.path.dash_offset
            if v is not None and v.asset_sets:
                node_sets[path] = v.asset_sets
                node_asset_ids[path] = v.asset_id
            child_prefix = path
        else:
            child_prefix = ""  # skip the synthetic root, as the runtime does
        for child in node.children:
            walk(child, child_prefix)

    walk(root, "")

    declared: dict[str, dict[str, frozenset[str]]] = {}
    declared_maps: dict[str, dict[str, dict[str, str]]] = {}
    descriptors: dict[str, Any] = {}
    art_exists: dict[str, Callable[[str], bool] | None] = {}
    entity_scale: dict[str, float] = {}
    for entity in shot.entities:
        kind = entity_kind(entity.kind)
        declare = kind.swap_declaration if kind is not None else None
        decl = declare(entity, mall) if declare is not None else None
        if decl is None:
            continue
        for channel in decl.sets:
            problem = swap_set_name_problem(channel)
            if problem is not None:
                # The reservation check (an#87): a set named `alpha` would be
                # applied by the runtime's static switch, never as a swap —
                # the descriptor would declare a capability the pipeline
                # silently routes elsewhere.
                raise CutoutCompileError(
                    f"{entity.kind} {entity.ref!r} declares an asset set that "
                    f"cannot be a swap-set name: {problem}. Transform "
                    f"properties are: {sorted(TRANSFORM_PROPERTIES)}."
                )
        declared[entity.id] = {
            channel: frozenset(keys) for channel, keys in decl.sets.items()
        }
        declared_maps[entity.id] = {
            channel: dict(keys) for channel, keys in decl.sets.items()
        }
        descriptors[entity.id] = decl.descriptor
        art_exists[entity.id] = decl.art_exists
        entity_scale[entity.id] = decl.scale

    return _SwapVocabulary(
        node_sets=node_sets,
        node_asset_ids=node_asset_ids,
        declared=declared,
        paths=frozenset(_runtime_node_paths(root)),
        declared_maps=declared_maps,
        descriptors=descriptors,
        art_exists=art_exists,
        node_transforms=node_transforms,
        entity_scale=entity_scale,
        path_nodes=frozenset(path_nodes),
        path_trims=path_trims,
        space_of=entity_space_resolver(shot.entities),
        entity_kinds={e.id: e.kind for e in shot.entities},
    )


def _raise_or_warn_on_asset_fallbacks(
    shot_id: str,
    resolutions: list[AssetResolutionJSON],
    *,
    strict: bool,
) -> None:
    """Make a stand-in asset audible — and, under ``strict``, fatal (an#33).

    The fallback itself is legitimate: a project with no art must still render,
    and that is the only reason ``an`` works out of the box. What is not
    legitimate is that it was *indistinguishable* from the real thing. A
    corpus blessed on a machine where the assets exist and gated on one where
    they do not blesses one picture and gates another, and every tripwire
    reports a clean pass because both sides are internally consistent.

    So: a warning by default (the render is still what the author can get
    today), and an error for any caller that is measuring pixels.
    """
    fallbacks = [r for r in resolutions if r.fallback]
    if not fallbacks:
        return
    lines = [f"  - {r.kind} {r.id!r}: {r.detail}" for r in fallbacks]
    body = (
        f"shot {shot_id!r} rendered {len(fallbacks)} stand-in asset(s):\n"
        + "\n".join(lines)
    )
    if strict:
        raise CutoutCompileError(
            body + "\n\nstrict_assets=True refuses this because the render would be a "
            "DIFFERENT picture that looks like a successful one. Either commit / "
            "regenerate the missing asset, or drop strict_assets if a stand-in "
            "is what you meant."
        )
    warnings.warn(
        body + "\n\nThe render will succeed and look plausible, which is exactly why "
        "this is said out loud. Pass strict_assets=True to make it fatal.",
        CutoutCompileWarning,
        stacklevel=3,
    )


def compile_shot(
    shot: Shot,
    mall: Mapping[str, Mapping] | None = None,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    background: str = "#ffffff",
    strict_assets: bool = False,
    step_hz: float | None = None,
    expression_provider: Any = None,
    style_pack: "StylePack | None" = None,
    default_easing: Any = None,
) -> CutoutSceneJSON:
    """Compile a single cutout-style `Shot` to its JS-runtime JSON form.

    ``default_easing`` (an#166) is the scene's ``meta.default_easing``: the
    curve of every authored tween that names none (tween > this > the built-in
    ``"ease_in_out"``, :meth:`~an.ir.schema.TweenAction.resolved_easing`).
    ``None`` leaves the document byte-identical to before the knob existed.

    ``expression_provider`` (an#98) is the seam that turns authored
    ``expression`` leaves and dialogue ``[emotion]`` sugar into per-axis
    curves for the face solver; ``None`` is the genre's default provider.

    ``step_hz`` (an#89) resamples every authored **tween** onto a SHOT-wide
    pose grid of that many updates per second (multiples of ``1/step_hz`` on
    this shot's clock, shared by every tween in the shot; the grid restarts at
    a cut), each keyframe step-eased, so the character holds each pose for the
    frames between grid points — "on twos" at half the frame rate, "on threes"
    at a third. It is sample-and-hold of the eased curve at the grid instants,
    not a retiming into holds and fast transitions. ``None`` (default) leaves
    tweens smooth and the compiled document byte-identical to before the knob
    existed; anything else must satisfy ``0 < step_hz <= fps`` — checked HERE
    as well as by ``an validate``, because a render never runs validate and a
    non-positive rate used to spin ``step_times`` forever (an#89 review).
    Exempt by construction, because they are separate
    emission sites rather than string-sniffed: the camera (`_add_camera_clips`
    — a stepped character under a translating camera slides in screen space,
    which is why the practice keeps cameras on ones), compiled blinks, `play`
    clips, and swap channels (already stepped by format). The value is
    stamped into ``meta.step_hz`` — only when set — so a serialized scene
    declares its timing policy without moving the contract hash of one that
    has none.

    ``strict_assets`` turns a stand-in asset — the placeholder rig drawn for a
    character whose descriptor is missing, or the default backdrop drawn for an
    unknown environment ref — from a warning into a :class:`CutoutCompileError`.
    Off by default so an asset-less project still renders; on for anything that
    measures pixels, where a stand-in is a wrong answer wearing a right one's
    clothes (an#33).
    """
    from an.stage import STAGE_RENDERER_NAMES

    if shot.renderer not in STAGE_RENDERER_NAMES:
        raise ValueError(
            f"compile_shot expects a stage renderer {STAGE_RENDERER_NAMES}; "
            f"got {shot.renderer!r}"
        )
    if step_hz is not None and not (math.isfinite(step_hz) and 0 < step_hz <= fps):
        raise CutoutCompileError(
            f"step_hz must satisfy 0 < step_hz <= fps ({fps}); got {step_hz!r}. "
            f"At {fps} fps, {fps / 2:g} is 'on twos' and {fps / 3:g} 'on threes'."
        )
    if default_easing is not None:
        _check_default_easing(default_easing)
    state = CompileState(
        shot=shot,
        mall=mall or {},
        fps=fps,
        width=width,
        height=height,
        strict_assets=strict_assets,
        step_hz=step_hz,
        default_easing=default_easing,
        style_pack=style_pack,
        expression_provider=expression_provider,
    )
    replaced = stage_replacements()
    if replaced:
        state.meta_extensions["replaced_compile_passes"] = replaced
    for compile_pass in compile_passes_for_stage():
        compile_pass.resolve()(state)
    return _assemble_document(state, background=background)


@dataclass
class CompileState:
    """What the stage compiler's passes read and write, for one shot (an#247).

    The stage's own passes (:data:`STAGE_COMPILE_PASSES`) and every pass a genre
    registers for the ``"stage"`` compiler (:class:`an.genres.CompilePass`) run
    over one of these, in order; :func:`_assemble_document` turns it into the
    wire document. The fields are the locals ``compile_shot`` used to thread by
    hand, unchanged, so the document is byte-identical.
    """

    shot: Shot
    mall: Mapping[str, Mapping]
    fps: int
    width: int
    height: int
    strict_assets: bool = False
    step_hz: float | None = None
    default_easing: Any = None
    style_pack: "StylePack | None" = None
    expression_provider: Any = None
    textures: dict[str, AssetJSON] = field(default_factory=dict)
    resolutions: list[AssetResolutionJSON] = field(default_factory=list)
    overlay_children: list[NodeJSON] = field(default_factory=list)
    fonts: dict[str, str] = field(default_factory=dict)
    scene_root: NodeJSON | None = None
    vocab: "_SwapVocabulary | None" = None
    animations: dict[str, AnimationClipJSON] = field(default_factory=dict)
    tracks: list[TrackJSON] = field(default_factory=list)
    entity_swaps: list["_EntitySwap"] = field(default_factory=list)
    #: Actions a pass contributes beside the authored ones, compiled with them
    #: by the `actions` pass (the cut-out `speech` pass's pulses, an#248).
    extra_actions: list = field(default_factory=list)
    #: Cut-out passes' products, read by later passes (an empty default is what
    #: a shot with no character produces anyway).
    no_lip_sync: Any = frozenset()
    poses: Any = None
    view_spans: Any = None
    blink_phases: dict[str, float] = field(default_factory=dict)
    gaze_seeds: dict[str, int] = field(default_factory=dict)
    #: The generic slots (an#247): what a genre's pass produces for a later
    #: pass (``products``, by key), and what it adds to the document's meta
    #: (``meta_extensions`` -> ``meta.extensions``, omitted when empty). A new
    #: genre needs no new field here.
    products: dict[str, Any] = field(default_factory=dict)
    meta_extensions: dict[str, Any] = field(default_factory=dict)



def _scene_pass(state: CompileState) -> None:
    """The scene tree, the overlay, the paper grain and the swap vocabulary."""
    shot, width, height = state.shot, state.width, state.height
    state.scene_root = _build_scene_root(
        shot,
        state.mall,
        textures=state.textures,
        resolutions=state.resolutions,
        style_pack=state.style_pack,
        overlay=state.overlay_children,
        fonts=state.fonts,
        width=width,
        height=height,
    )
    style_pack, overlay_children = state.style_pack, state.overlay_children
    if style_pack is not None and style_pack.grain is not None:
        # an#163: the paper grain, FIRST on the overlay so any text draws over
        # it, and on the overlay at all so the camera cannot move or scale it.
        overlay_children.insert(
            0,
            grain_node(
                style_pack.grain, width=width, height=height, textures=state.textures
            ),
        )
    # The vocabulary sees the overlay too: its nodes are indexed by the
    # runtime under their own paths (`title/word_0`), exactly like the scene's,
    # so an authored tween on one is checked like any other target.
    scene_root = state.scene_root
    state.vocab = _swap_vocabulary(
        NodeJSON(name="root", children=scene_root.children + overlay_children)
        if overlay_children
        else scene_root,
        shot,
        state.mall,
    )
    _check_text_unit_targets(shot, state.fonts, state.vocab)
    clash = {n.name for n in overlay_children} & {n.name for n in scene_root.children}
    if clash:
        raise CutoutCompileError(
            f"overlay and scene both build a node named {sorted(clash)}; the "
            "runtime indexes both layers by path, so one would shadow the other"
        )


def _actions_pass(state: CompileState) -> None:
    """The authored actions (sets, tweens, plays, swaps) -> clips and tracks."""
    state.animations, state.tracks = _compile_actions(
        [*state.shot.actions, *state.extra_actions],
        state.shot.duration,
        vocab=state.vocab,
        resolutions=state.resolutions,
        fps=state.fps,
        step_hz=state.step_hz,
        default_easing=state.default_easing,
        entity_swaps=state.entity_swaps,
    )












def _camera_pass(state: CompileState) -> None:
    """The camera (Phase 7): `camera.move`/keys onto the scene root."""
    _add_camera_clips(
        state.shot,
        state.animations,
        state.tracks,
        width=state.width,
        height=state.height,
    )


def _parallax_pass(state: CompileState) -> None:
    """Planes' parallax. After the camera, which reads in the order it happens --
    though not load-bearing: the two write disjoint targets. What IS load-bearing
    is that both resolve the same `camera_keys`."""
    _add_parallax_clips(
        state.shot,
        state.mall,
        state.animations,
        state.tracks,
        width=state.width,
        height=state.height,
    )


def _checks_pass(state: CompileState) -> None:
    """After EVERY emission pass: targets, easings, stand-in assets, faded treatments."""
    # No channel may reach the runtime's frame loop naming a node it will not
    # find (an#193).
    _check_channel_targets(state.animations, state.vocab.paths, shot_id=state.shot.id)
    _check_keyframe_easings(state.animations, shot_id=state.shot.id)
    # AFTER action + viseme compilation, deliberately: a swap key the timeline
    # actually USES whose art is missing is recorded as a fallback during
    # those passes (usage-aware escalation, an#87), and this is the one place
    # that decides warn-vs-raise for every fallback.
    _raise_or_warn_on_asset_fallbacks(
        state.shot.id, state.resolutions, strict=state.strict_assets
    )
    if state.style_pack is not None:
        faded = faded_treated_targets(state.scene_root, state.animations)
        if faded:
            warnings.warn(
                f"an alpha channel fades {faded}, which carry surface treatments "
                "(an#163): their outline/shadow copies are drawn separately, so a "
                "fade shows the outline colour through the part rather than the "
                "background. Fade with the treatment switched off for that entity "
                "(`entity_surfaces: {<id>: {outline: false, shadow: false}}`), or "
                "accept it for a short fade.",
                CutoutCompileWarning,
                stacklevel=3,
            )


#: The STAGE's own compile passes, in order. A genre adds passes between them by
#: registering :class:`an.genres.CompilePass` objects for the ``"stage"``
#: compiler; the in-repo cut-out genre registers ``swap_pose`` (300),
#: ``view_spans`` (310), ``visemes`` (400) and ``face`` (500), and the ``rig``
#: entity builder (:data:`an.genres.cutout.CUTOUT_COMPILE_PASSES`). Held HERE, not in the genre tables, so
#: no ``without_genres()`` can take the stage's own passes away.
STAGE_COMPILE_PASSES: tuple[CompilePass, ...] = (
    CompilePass(
        "scene",
        _scene_pass,
        order=100,
        description="the scene tree, overlay, grain, vocabulary",
    ),
    CompilePass(
        "actions", _actions_pass, order=200, description="authored actions -> clips"
    ),
    CompilePass(
        "camera", _camera_pass, order=600, description="the camera onto the scene root"
    ),
    CompilePass("parallax", _parallax_pass, order=700, description="planes' parallax"),
    CompilePass(
        "checks", _checks_pass, order=900, description="targets, easings, stand-ins"
    ),
)


class CompilePassCollision(CutoutCompileError):
    """A genre registered a pass (or a builder) the stage already has, without ``replace=True``."""


def _merge_over_stage(
    own: Mapping[str, CompilePass], registered: Iterable[CompilePass], key
) -> dict[str, CompilePass]:
    """The stage's own entries, with registered ones added; a registered entry
    that names one of the stage's REPLACES it only when it says ``replace=True``."""
    from an.genres.registry import compile_pass_owner

    merged = dict(own)
    for p in registered:
        k = key(p)
        if k in own and not p.replace:
            raise CompilePassCollision(
                f"genre {compile_pass_owner(p.name)!r} registers compile pass "
                f"{p.name!r}, which would collide with the stage's own "
                f"{'builder for ' + repr(k) if p.builds else 'pass ' + repr(k)}. "
                "Pass `replace=True` on the CompilePass to replace it on purpose "
                "(the compiled document then records it), or rename it."
            )
        merged[k] = p
    return merged


def compile_passes_for_stage() -> tuple[CompilePass, ...]:
    """The stage's passes and every registered one, in run order (stable by name)."""
    from an.genres.registry import compile_passes

    merged = _merge_over_stage(
        {p.name: p for p in STAGE_COMPILE_PASSES},
        compile_passes("stage"),
        key=lambda p: p.name,
    )
    return tuple(sorted(merged.values(), key=lambda p: (p.order, p.name)))


def stage_replacements() -> dict[str, str]:
    """``{stage pass or builder: the genre replacing it}`` -- recorded in the
    compiled document's ``meta.extensions`` when non-empty."""
    from an.genres.registry import compile_pass_owner, compile_passes, entity_builders

    own = {p.name for p in STAGE_COMPILE_PASSES}
    out = {
        p.name: compile_pass_owner(p.name)
        for p in compile_passes("stage")
        if p.replace and p.name in own
    }
    out.update(
        {
            f"builder:{kind}": compile_pass_owner(p.name)
            for kind, p in entity_builders("stage").items()
            if p.replace and kind in STAGE_SCENE_BUILDERS
        }
    )
    return out


def _assemble_document(state: CompileState, *, background: str) -> CutoutSceneJSON:
    """The wire document from what the passes produced."""
    shot, style_pack, overlay_children = (
        state.shot,
        state.style_pack,
        state.overlay_children,
    )
    timeline = TimelineJSON(duration=shot.duration, tracks=state.tracks)

    return CutoutSceneJSON(
        meta=CutoutSceneMetaJSON(
            fps=state.fps,
            width=state.width,
            height=state.height,
            duration=shot.duration,
            background=background,
            blink_phases=state.blink_phases,
            step_hz=state.step_hz,
            gaze_seeds=state.gaze_seeds,
            style_pack=style_pack.name if style_pack is not None else None,
            fonts=state.fonts,
            entity_spaces=(entity_spaces := entity_spaces_of(shot)),
            spaces=space_definitions(entity_spaces),
            extensions=state.meta_extensions,
        ),
        scene=state.scene_root,
        overlay=(
            NodeJSON(name="overlay", children=overlay_children)
            if overlay_children
            else None
        ),
        animations=state.animations,
        timeline=timeline,
        assets=AssetsJSON(textures=state.textures),
        asset_resolution=state.resolutions,
    )


# -----------------------------------------------------------------------------
# Scene tree construction
# -----------------------------------------------------------------------------


def entity_spaces_of(shot: Shot) -> dict[str, str]:
    """``{entity id: space}`` for each entity whose kind declares a space other
    than the kernel default -- what the compiled document records so the
    default evaluator agrees with validate and compile (an#245).

    >>> from an.ir.schema import AssetRef, Shot
    >>> entity_spaces_of(Shot(id="s", entities=[AssetRef(kind="prop", id="p", store="props", ref="p")]))
    {}
    """
    from an.genres import entity_kind
    from an.timing import spaces

    out: dict[str, str] = {}
    for entity in shot.entities:
        kind = entity_kind(entity.kind)
        if kind is not None and kind.space and kind.space != spaces.DFLT_TIMELINE_SPACE:
            out[entity.id] = kind.space
    return out


#: The field kinds ``runtime.js`` implements (its ``FIELD_KINDS`` table; a test
#: pins the two). A declared space using any other kind cannot be drawn by the
#: stage, so the compiler refuses it instead of the browser failing mid-render.
RUNTIME_FIELD_KINDS: frozenset[str] = frozenset(
    {"number", "angle", "vector", "quaternion", "color", "orbit", "discrete"}
)


def space_definitions(entity_spaces: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """``{space name: definition}`` for every space ``entity_spaces`` names --
    what the compiled document embeds as ``meta.spaces`` so ``runtime.js``
    evaluates each declared entity in its space (an#287).

    The definition is :meth:`~an.timing.spaces.PropertySpace.to_json` without
    its prose (a reworded description must not move a contract hash; a
    space's ``version`` does). A space using a field kind the runtime does not
    implement is refused here (:class:`CutoutCompileError`).

    >>> space_definitions({})
    {}
    >>> space_definitions({"cam": "stage.camera"})["stage.camera"]["fields"][0]
    {'pattern': 'x', 'spec': {'kind': 'number'}, 'unit': 'px'}
    """
    from an.timing import spaces

    out: dict[str, dict[str, Any]] = {}
    for name in sorted(set(entity_spaces.values())):
        space = spaces.get_space(name)
        used = {d.kind.name for d in space.fields} | {space.undeclared.name}
        missing = sorted(used - RUNTIME_FIELD_KINDS)
        if missing:
            users = sorted(e for e, s in entity_spaces.items() if s == name)
            raise CutoutCompileError(
                f"entities {users} declare the property space {name!r}, which uses "
                f"field kind(s) {missing} that the stage runtime cannot evaluate "
                f"(it implements {sorted(RUNTIME_FIELD_KINDS)}). Render these "
                "entities with an engine that implements the kind, or declare a "
                "space of core kinds for the stage (an#287)."
            )
        doc = space.to_json()
        doc.pop("description", None)
        doc["fields"] = [
            {k: v for k, v in f.items() if k != "description"} for f in doc["fields"]
        ]
        out[name] = doc
    return out


def _build_scene_root(
    shot: Shot,
    mall: Mapping[str, Mapping],
    *,
    textures: dict[str, AssetJSON] | None = None,
    resolutions: list[AssetResolutionJSON] | None = None,
    style_pack: "StylePack | None" = None,
    overlay: list[NodeJSON] | None = None,
    fonts: dict[str, str] | None = None,
    width: int = 1920,
    height: int = 1080,
) -> NodeJSON:
    """Construct the cutout scene tree under a single root from shot.entities.

    Multiple characters get spread along the x-axis so they don't overlap.
    For N characters, positions are evenly distributed across a fixed band;
    a single character lives at the center.

    ``resolutions`` is an out-parameter, filled the same way ``textures`` is:
    one :class:`AssetResolutionJSON` per drawable entity, in scene order,
    recording what each declared ref actually became.

    ``overlay`` and ``fonts`` are out-parameters too (an#155): an overlay-layer
    text block is built into ``overlay`` — the camera-immune container, not
    this root — and every text block records the face that set it in
    ``fonts`` (entity id -> identity label). ``width``/``height`` are the frame
    a text block is typeset for.
    """
    if textures is None:
        textures = {}
    if resolutions is None:
        resolutions = []
    if overlay is None:
        overlay = []
    if fonts is None:
        fonts = {}
    build = SceneBuild(
        shot=shot,
        mall=mall,
        textures=textures,
        resolutions=resolutions,
        style_pack=style_pack,
        overlay=overlay,
        fonts=fonts,
        width=width,
        height=height,
    )
    _refuse_unregistered_entity_kinds(shot)
    # Builders by phase (an#247): the backdrop (environments, phase 0) first so
    # it sits BEHIND the cast, then the cast (phase 1) in entity order — except
    # for the planes an environment declares as foreground, kept in `in_front`.
    # Before an#110 two fixed loops made a plane in FRONT of the characters
    # structurally unreachable.
    builders = scene_builders()
    for phase in sorted({b.order for b in builders.values()}):
        for entity in shot.entities:
            builder = builders.get(entity.kind)
            if builder is not None and builder.order == phase:
                builder.resolve()(entity, build)
        # `voice` entities are legitimately not drawable: they configure the
        # render rather than appearing in it, and no builder claims them.
    children, in_front = build.children, build.in_front
    reached, skipped, raster = build.reached, build.skipped, build.raster
    # …and last, the foreground planes, over everything.
    children.extend(in_front)
    _warn_about_art_a_pack_cannot_reach(style_pack, reached, skipped)
    _warn_raster_parts_not_recoloured(style_pack, raster)
    return NodeJSON(name="root", children=children)


@dataclass
class SceneBuild:
    """The scene being built, as an entity builder sees it (an#247).

    A builder (:class:`an.genres.CompilePass` with ``builds`` set) appends its
    entity's subtree to ``children`` (or ``overlay``, or ``in_front``) and
    records its textures and resolutions here, exactly as the scene pass did
    by hand.
    """

    shot: Shot
    mall: Mapping[str, Mapping]
    textures: dict[str, AssetJSON]
    resolutions: list[AssetResolutionJSON]
    style_pack: "StylePack | None"
    overlay: list[NodeJSON]
    fonts: dict[str, str]
    width: int
    height: int
    children: list[NodeJSON] = field(default_factory=list)
    in_front: list[NodeJSON] = field(default_factory=list)
    reached: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    raster: set[str] = field(default_factory=set)

    def store(self, name: str) -> Mapping:
        return self.mall.get(name) or {}


def _build_environment_entity(entity: AssetRef, build: SceneBuild) -> None:
    """The stage's backdrop builder: an environment's planes."""
    node, front = _build_environment_subtree(
        entity,
        build.store("environments"),
        textures=build.textures,
        resolutions=build.resolutions,
        style_pack=build.style_pack,
        reached=build.reached,
        canvas=(build.width, build.height),
    )
    build.children.append(node)
    build.in_front.extend(front)


def _build_prop_entity(entity: AssetRef, build: SceneBuild) -> None:
    """The stage's prop builder: a text block, a stroked path or a prop with art."""
    props_store = build.store("props")
    text_doc = text_document(entity, props_store)
    if text_doc is not None:
        sub, layer = _build_text_block(
            entity,
            text_doc,
            props_store,
            textures=build.textures,
            resolutions=build.resolutions,
            fonts=build.fonts,
            width=build.width,
            height=build.height,
        )
        (build.overlay if layer == "overlay" else build.children).append(sub)
        return
    sub = _build_prop_subtree(
        entity,
        props_store,
        textures=build.textures,
        resolutions=build.resolutions,
        style_pack=build.style_pack,
        reached=build.reached,
        raster=build.raster,
    )
    _apply_stage_placement(sub, entity)
    _warn_surface(
        apply_surface(
            sub, surface_for(build.style_pack, entity.id), textures=build.textures
        )
    )
    build.children.append(sub)




#: The stage's own entity builders: phase 0 the backdrop, phase 1 the cast.
STAGE_SCENE_BUILDERS: dict[str, CompilePass] = {
    "environment": CompilePass(
        "environment",
        _build_environment_entity,
        order=0,
        builds="environment",
        description="an environment's planes (the backdrop)",
    ),
    "prop": CompilePass(
        "prop",
        _build_prop_entity,
        order=1,
        builds="prop",
        description="a prop, a stroked path or a text block",
    ),
}


def scene_builders() -> dict[str, CompilePass]:
    """``{entity kind: builder}``: the stage's, and every registered one."""
    from an.genres.registry import entity_builders

    return _merge_over_stage(
        STAGE_SCENE_BUILDERS, entity_builders("stage").values(), key=lambda p: p.builds
    )


# Environment presets — built-in named backdrops. A user-supplied environment
# in the store can override fields by name (sky_color, ground_color, ground_y).
_ENV_PRESETS: dict[str, dict[str, Any]] = {
    "default": {"sky_color": "#cfe9ff", "ground_color": "#7cba6f", "ground_y": 100.0},
    "park": {"sky_color": "#a5d8ff", "ground_color": "#7cba6f", "ground_y": 110.0},
    "indoor": {"sky_color": "#f4e8c8", "ground_color": "#a07a4a", "ground_y": 120.0},
    "night": {"sky_color": "#1a2540", "ground_color": "#2c3e50", "ground_y": 110.0},
    "sunset": {"sky_color": "#f4a261", "ground_color": "#5b4b32", "ground_y": 110.0},
}


def _build_environment_subtree(
    entity: AssetRef,
    env_store: Mapping,
    *,
    textures: dict[str, AssetJSON] | None = None,
    resolutions: list[AssetResolutionJSON] | None = None,
    style_pack: "StylePack | None" = None,
    reached: set[str] | None = None,
    canvas: tuple[int, int] = DEFAULT_RESOLUTION,
) -> tuple[NodeJSON, list[NodeJSON]]:
    """``(the environment node, the planes that go IN FRONT of the characters)``.

    Two paths, and the second is reached only by a document that asks for it.
    A store entry whose `kind` is `EnvironmentDescriptor` **and** which declares
    planes builds them, in list order; anything else — a free-form `meta.json`,
    a preset name, a ref that is neither — takes the path below unchanged,
    which is what keeps every legacy environment byte-identical (an#110).
    Re-expressing the presets as planes would move two ledger hashes for no
    picture change; a richer default look ships as a NEW preset.

    Backdrop path: a sky band + a ground band, full canvas width.

    Picks a preset by ``entity.ref`` (e.g. "park", "night"); the store
    can override any of (sky_color, ground_color, ground_y) by ref.

    A ref that names neither a store entry nor a preset draws the *default*
    backdrop, which is a different picture from the one the author asked for
    — so it is recorded as a fallback (an#33).
    """
    env = _environment_descriptor(entity, env_store)
    if env is not None:
        if resolutions is not None:
            resolutions.append(
                AssetResolutionJSON(
                    id=entity.id,
                    kind="environment",
                    store=entity.store,
                    ref=entity.ref,
                    resolved="planes",
                )
            )
        return _build_plane_subtree(
            entity,
            env,
            textures=textures if textures is not None else {},
            env_store=env_store,
            resolutions=resolutions,
            style_pack=style_pack,
            canvas=canvas,
        )
    preset_key = (entity.ref or "default").lower()
    known_preset = preset_key in _ENV_PRESETS
    preset = dict(_ENV_PRESETS.get(preset_key, _ENV_PRESETS["default"]))
    in_store = entity.ref in env_store
    if resolutions is not None:
        if in_store:
            resolved, fallback, detail = "store", False, ""
        elif known_preset:
            resolved, fallback, detail = "preset", False, ""
        else:
            resolved, fallback, detail = (
                "default",
                True,
                f"environment ref {entity.ref!r} names neither an entry in the "
                f"{entity.store!r} store nor a built-in preset "
                f"({sorted(_ENV_PRESETS)}), so the DEFAULT backdrop was drawn",
            )
        resolutions.append(
            AssetResolutionJSON(
                id=entity.id,
                kind="environment",
                store=entity.store,
                ref=entity.ref,
                resolved=resolved,
                fallback=fallback,
                detail=detail,
            )
        )
    if in_store:
        try:
            override = env_store[entity.ref]
            if isinstance(override, dict):
                unknown = sorted(set(override) - set(preset))
                if unknown:
                    # A warning, not an error. EnvironmentsStore is a
                    # JsonSidecarStore over a free-form meta.json, so `name` /
                    # `description` / `tags` are its natural shape — raising here
                    # would hard-fail ordinary data. The keys still do nothing,
                    # which is the part worth saying.
                    warnings.warn(
                        f"environment {entity.ref!r} declares {unknown}, which the "
                        f"cutout renderer does not read on this path (it uses "
                        f"{sorted(preset)}), so they have no effect on the render. "
                        "For layered plates and parallax, write an "
                        "`EnvironmentDescriptor` with `planes` instead — this is "
                        "the free-form preset-override path, which reads exactly "
                        "those three keys and drops the rest (an#110).",
                        CutoutCompileWarning,
                        stacklevel=2,
                    )
                preset.update({k: v for k, v in override.items() if k in preset})
        except KeyError:
            pass
    # Sky and ground are HUGE rects so they fill the canvas regardless of size.
    # The runtime centers root at canvas/2 and applies camera scale, so 4000px
    # wide rects will always cover.
    huge = 4000.0
    ground_y = float(preset["ground_y"])
    # A lookup with a default, as everywhere else a pack reaches.
    sky_color = (
        style_pack.colour_for("sky", entity=entity.id) if style_pack else None
    ) or str(preset["sky_color"])
    ground_color = (
        style_pack.colour_for("ground", entity=entity.id) if style_pack else None
    ) or str(preset["ground_color"])
    if style_pack is not None and reached is not None:
        reached.add(entity.id)
    # The node is built exactly as before an#110; only the RETURN grew a second
    # element, and it is always empty here — a preset declares no planes, so it
    # has nothing to put in front of the characters.
    node = NodeJSON(
        name=entity.id,
        transform=TransformJSON(),
        children=[
            NodeJSON(
                name="sky",
                transform=TransformJSON(x=0.0, y=-huge / 2 + ground_y),
                visual=VisualJSON(
                    kind="rect", width=huge, height=huge, color=sky_color
                ),
            ),
            NodeJSON(
                name="ground",
                transform=TransformJSON(x=0.0, y=huge / 2 + ground_y),
                visual=VisualJSON(
                    kind="rect", width=huge, height=huge, color=ground_color
                ),
            ),
        ],
    )
    return node, []


def _build_plane_subtree(
    entity: AssetRef,
    env: EnvironmentDescriptor,
    *,
    textures: dict[str, AssetJSON],
    env_store: Mapping,
    resolutions: list[AssetResolutionJSON] | None = None,
    style_pack: "StylePack | None" = None,
    canvas: tuple[int, int] = DEFAULT_RESOLUTION,
) -> tuple[NodeJSON, list[NodeJSON]]:
    """A declared multiplane stage: planes in list order, split by depth-in-front.

    Planes whose art cannot be drawn are DROPPED and recorded as a fallback —
    not replaced with a stand-in, because a plate that is not there has no
    substitute that is not a lie about the picture (an#33). `strict_assets`
    then decides whether that is fatal, at the one place that decides it for
    every fallback.
    """
    probe = _part_probe(env_store, art_prefix=ENVIRONMENT_ART_PREFIX)
    digest = _raster_digest(env_store, art_prefix=ENVIRONMENT_ART_PREFIX)
    ref = entity.ref or entity.id
    nodes: list[NodeJSON] = []
    for plane in env.planes:
        node = _plane_node(
            plane,
            ref=ref,
            textures=textures,
            probe=probe,
            digest=digest,
            style_pack=style_pack,
            canvas=canvas,
        )
        if node is None:
            if resolutions is not None:
                resolutions.append(
                    AssetResolutionJSON(
                        id=entity.id,
                        kind="environment",
                        store=entity.store,
                        ref=entity.ref,
                        resolved="missing-plane",
                        fallback=True,
                        detail=(
                            f"plane {plane.name!r} declares art "
                            f"{plane.art.src!r} which is not in the "
                            f"{entity.store!r} store, so the plane was dropped"
                        ),
                    )
                )
            continue
        nodes.append(node)
    behind, in_front = _split_planes_around_characters(env, nodes)
    front_nodes = (
        [
            NodeJSON(
                name=foreground_node_name(entity.id),
                transform=TransformJSON(),
                children=in_front,
            )
        ]
        if in_front
        else []
    )
    return (
        NodeJSON(name=entity.id, transform=TransformJSON(), children=behind),
        front_nodes,
    )


#: The `assets.textures` `src` prefix an environment plate is addressed under.
ENVIRONMENT_ART_PREFIX: str = "environments/"

#: A `fill` plane with no declared size covers the canvas at any camera scale
#: — defined beside the schema (`an.stage.environments.PLANE_FILL_SPAN`) so the IR
#: layer's framing check reads the same number, re-exported here.
PLANE_FILL_SPAN: float = _PLANE_FILL_SPAN


#: Suffix for the container holding an environment's FOREGROUND planes.
#:
#: The split has to produce two sibling containers, and before an#110's review
#: both were named `entity.id`. The runtime's `nodeIndex` is a flat
#: `path -> container` dict, so the second silently overwrote the first — an
#: authored `set street:x` then moved the foreground half and left the
#: background where it was, with no warning from either side: the compiler's
#: collision check compares `(entity/plane, prop)` and never sees `(entity, x)`,
#: and the runtime's unknown-target throw does not fire because the name IS
#: known, just bound to the wrong one of two. The determinism report's
#: `node_count` under-counted by one per split environment too.
FOREGROUND_SUFFIX: str = "__front"


def foreground_node_name(entity_id: str) -> str:
    """The node name an environment's foreground planes live under.

    >>> foreground_node_name("street")
    'street__front'
    """
    return f"{entity_id}{FOREGROUND_SUFFIX}"


def plane_parents(env: "EnvironmentDescriptor", entity_id: str) -> dict[str, str]:
    """``{plane name: the node path its channels must target}``.

    One rule, computed the same way by the builder and by the parallax pass —
    the alternative is two places deciding which container a plane ended up in,
    which is the class of drift this wave keeps closing.

    >>> from an.stage.environments import EnvironmentDescriptor, Plane
    >>> env = EnvironmentDescriptor(name="e", planes=[Plane(name="a"), Plane(name="b")],
    ...                             characters_after="a")
    >>> plane_parents(env, "street")
    {'a': 'street', 'b': 'street__front'}
    """
    names = [p.name for p in env.planes]
    after = env.characters_after
    cut = names.index(after) + 1 if after in names else len(names)
    return {
        name: (entity_id if i < cut else foreground_node_name(entity_id))
        for i, name in enumerate(names)
    }


def _environment_descriptor(
    entity: AssetRef, env_store: Mapping
) -> "EnvironmentDescriptor | None":
    """The store's `EnvironmentDescriptor` for ``entity``, or ``None``.

    ``None`` means "take the preset path", which is every environment written
    before an#110 — a free-form `meta.json` with colour scalars, or nothing at
    all. That is what keeps the legacy output byte-identical: the plane code
    is not reached unless a document says `kind: EnvironmentDescriptor` AND
    declares planes.
    """
    if entity.ref not in env_store:
        return None
    try:
        raw = env_store[entity.ref]
    except KeyError:
        return None
    if not isinstance(raw, dict) or raw.get("kind") != ENVIRONMENT_DOCUMENT_KIND.name:
        return None
    env = EnvironmentDescriptor.model_validate(
        migrate(dict(raw), kind=ENVIRONMENT_DOCUMENT_KIND.name)
    )
    return env if env.planes else None


def _plane_node(
    plane: Plane,
    *,
    ref: str,
    textures: dict[str, AssetJSON],
    probe=None,
    digest: Callable[[str], str | None] | None = None,
    style_pack: "StylePack | None" = None,
    canvas: tuple[int, int] = DEFAULT_RESOLUTION,
) -> NodeJSON | None:
    """One plane as a scene node, or ``None`` when its art cannot be drawn.

    ``None`` rather than a placeholder: an environment plate that is not on
    disk has no stand-in that is not a lie about the picture (an#33), and the
    caller records it as a fallback so `strict_assets` can decide.

    **A declared `size` is the box; the art's own extent is only the default**
    (an#211). It was the other way round, so a plate's on-screen size came
    from its SVG's `width`/`height` and `Plane.size` was read only for art
    that could not be measured — the author had to rewrite the file to resize
    the plane. The art is fitted into the box by `fit`.
    """
    art = plane.art
    ox, oy = plane.offset
    transform = TransformJSON(x=float(ox), y=float(oy))
    gradient = (style_pack.gradient_for(art.role) if style_pack else None) or art.gradient
    if gradient is not None and art.kind in ("fill", "gradient"):
        return _gradient_plane_node(
            plane, gradient, ref=ref, textures=textures, transform=transform, canvas=canvas
        )
    if art.kind == "fill":
        w, h = plane.size or (PLANE_FILL_SPAN, PLANE_FILL_SPAN)
        return NodeJSON(
            name=plane.name,
            transform=transform,
            visual=VisualJSON(
                kind="rect", width=float(w), height=float(h), color=art.color
            ),
        )
    if not art.src:
        return None
    src = _svg_asset_src(ref, art.src, art_prefix=ENVIRONMENT_ART_PREFIX)
    if probe is not None and not probe(src)[0]:
        return None
    alias = f"{ref}.{plane.name}"
    extent = plane.size or (probe(src)[1] if probe else None)
    sha = digest(src) if digest is not None else None
    if sha:
        alias += "." + sha
        src = versioned_src(src, sha)
    alias = _register_texture(textures, alias, src)
    ax, ay = plane.anchor
    return NodeJSON(
        name=plane.name,
        transform=transform,
        visual=VisualJSON(
            kind="svg_sprite",
            asset_id=alias,
            anchor_x=float(ax),
            anchor_y=float(ay),
            fit=plane.fit,
            **(
                {"width": float(extent[0]), "height": float(extent[1])}
                if extent
                else {}
            ),
        ),
    )


def _gradient_plane_node(
    plane: Plane,
    gradient: "Gradient",
    *,
    ref: str,
    textures: dict[str, AssetJSON],
    transform: TransformJSON,
    canvas: tuple[int, int],
) -> NodeJSON:
    """A gradient plane (an#275): an inline SVG texture on an `svg_sprite`.

    Sized like a `fill` -- the declared `size`, else the span that covers the
    canvas at any camera -- and SHAPED over the declared `size`, else over the
    canvas, so an unsized gradient runs across what the camera frames and its
    end colours hold beyond (:mod:`an.stage.gradients`). A declared size honours
    the plane's `anchor`, as an image does; an unsized one is centred, as a
    fill is (`plane_rect` states the same geometry for `an validate`).
    """
    from an.stage.gradients import gradient_alias, gradient_src, gradient_svg

    box = plane.size or (PLANE_FILL_SPAN, PLANE_FILL_SPAN)
    frame = plane.size or canvas
    src = gradient_src(
        gradient_svg(
            gradient,
            box=(float(box[0]), float(box[1])),
            frame=(float(frame[0]), float(frame[1])),
        )
    )
    alias = _register_texture(textures, gradient_alias(f"{ref}.{plane.name}", src), src)
    anchored = plane.art.kind == "gradient" and plane.size is not None
    ax, ay = plane.anchor if anchored else (0.5, 0.5)
    return NodeJSON(
        name=plane.name,
        transform=transform,
        visual=VisualJSON(
            kind="svg_sprite",
            asset_id=alias,
            fit="stretch",
            width=float(box[0]),
            height=float(box[1]),
            anchor_x=float(ax),
            anchor_y=float(ay),
        ),
    )


def _split_planes_around_characters(
    env: EnvironmentDescriptor, nodes: list[NodeJSON]
) -> tuple[list[NodeJSON], list[NodeJSON]]:
    """``(behind, in_front)`` for the characters, by ``characters_after``.

    `None` puts everything behind — which is what the old two-loop builder did,
    and is why an environment that declares no `characters_after` compiles to
    the same picture. A name that matches no plane puts everything behind too,
    but says so: silently drawing a foreground plane at the back is a wrong
    picture that renders happily.

    >>> from an.stage.environments import EnvironmentDescriptor, Plane
    >>> env = EnvironmentDescriptor(name="e", planes=[Plane(name="a"), Plane(name="b")])
    >>> behind, front = _split_planes_around_characters(env, [NodeJSON(name="a"), NodeJSON(name="b")])
    >>> [n.name for n in behind], [n.name for n in front]
    (['a', 'b'], [])
    >>> env = env.model_copy(update={"characters_after": "a"})
    >>> behind, front = _split_planes_around_characters(env, [NodeJSON(name="a"), NodeJSON(name="b")])
    >>> [n.name for n in behind], [n.name for n in front]
    (['a'], ['b'])
    """
    after = env.characters_after
    if after is None:
        return nodes, []
    names = [n.name for n in nodes]
    if after not in names:
        warnings.warn(
            f"environment {env.name!r} declares characters_after={after!r}, which "
            f"is not one of its planes ({names}). Every plane is drawn BEHIND the "
            "characters, which is the default — a foreground plane silently drawn "
            "at the back is a wrong picture that renders happily.",
            CutoutCompileWarning,
            stacklevel=3,
        )
        return nodes, []
    cut = names.index(after) + 1
    return nodes[:cut], nodes[cut:]


def _add_parallax_clips(
    shot: Shot,
    mall: Mapping[str, Mapping],
    animations: dict[str, AnimationClipJSON],
    tracks: list[TrackJSON],
    *,
    width: int,
    height: int,
) -> None:
    """Compensate each plane for the camera, one factor per plane.

    ``plane.x = x0 + (1 − f) · cam_x`` — so a plane at `f = 1` emits **nothing**
    and rides the camera exactly as every node did before an#110, and a plane
    at `f = 0` is pinned in frame. Screen position works out to
    ``(W/2, H/2) + S · (x0 − f · cam)``, which is the affine expression every
    surveyed engine uses under a different name.

    The camera's own channels are emitted separately, on `root`; these are on
    the plane nodes, so a plane is free to be tweened by the author as long as
    it does not fight this — which is exactly what the collision check below
    refuses.

    **Translation only.** `root.scale` and `root.rotation` multiply the whole
    composed expression, so no per-plane factor can cancel them: a `depth = 0`
    plate still grows under a push-in. Depth-aware zoom is the dolly, deferred.

    Ordering note, since the call site's comment used to overstate it: running
    this after the camera is TIDY, not load-bearing. The two passes write
    disjoint targets (`root:*` versus `entity/plane:*`) and each inspects only
    the other's, so swapping them is picture-equivalent and merely reorders the
    serialized track list (an#110 review, L1).
    """
    keys = camera_keys(shot, width=width, height=height)
    if len(keys) < 2:
        return
    duration = max(0.001, float(shot.duration))
    authored = {
        (channel.target, channel.property)
        for animation in animations.values()
        for channel in animation.channels
    }
    env_store = mall.get("environments") or {}
    for entity in shot.entities:
        if entity.kind != "environment":
            continue
        env = _environment_descriptor(entity, env_store)
        if env is None:
            continue
        _emit_plane_compensation(
            shot.id,
            entity.id,
            env,
            keys,
            duration,
            animations,
            tracks,
            authored=authored,
        )


def _emit_plane_compensation(
    shot_id: str,
    entity_id: str,
    env: EnvironmentDescriptor,
    keys: list[CameraKey],
    duration: float,
    animations: dict[str, AnimationClipJSON],
    tracks: list[TrackJSON],
    *,
    authored: set[tuple[str, str]],
) -> None:
    """The per-plane half of :func:`_add_parallax_clips`."""
    parents = plane_parents(env, entity_id)
    for plane in env.planes:
        fx, fy = plane.factors()
        ox, oy = plane.offset
        target = f"{parents[plane.name]}/{plane.name}"
        for factor, prop, cam_field, rest in (
            (fx, "x", "x", float(ox)),
            (fy, "y", "y", float(oy)),
        ):
            if factor == 1.0:
                continue  # rides the camera; emitting nothing is the point
            values = [
                rest + (1.0 - factor) * float(getattr(k, cam_field)) for k in keys
            ]
            if all(v == rest for v in values):
                continue  # the camera does not move on this axis
            if (target, prop) in authored:
                raise CutoutCompileError(
                    f"shot {shot_id!r}: plane {target!r} has depth {plane.depth} so "
                    f"the stage drives `{prop}` on it, and an action also targets "
                    "it. Compensation clips are appended last and the evaluators "
                    "are later-wins, so the authored channel would be discarded "
                    "silently. Give the plane depth 1.0 to animate it by hand, or "
                    "move the action to a child node."
                )
            anim_id = f"__parallax__{shot_id}_{entity_id}_{plane.name}_{prop}"
            animations[anim_id] = AnimationClipJSON(
                name=anim_id,
                duration=duration,
                channels=[
                    ChannelJSON(
                        target=target,
                        property=prop,
                        keyframes=[
                            KeyframeJSON(time=float(k.at), value=v, easing=k.easing)
                            for k, v in zip(keys, values)
                        ],
                    )
                ],
            )
            tracks.append(
                TrackJSON(
                    target_root="__parallax__",
                    clips=[
                        PlacedClipJSON(
                            animation_id=anim_id, start_time=0.0, duration=duration
                        )
                    ],
                )
            )




def _apply_stage_placement(node: NodeJSON, entity: AssetRef) -> None:
    """Apply ``entity.stage`` to a built subtree, in place.

    A no-op when the entity declares none, which is every document written
    before an#108 — and the reason this is hash-free: an unplaced entity's
    node is the node the old code produced, byte for byte, because neither
    branch runs.

    `at` REPLACES the computed layout rather than offsetting it. Offsetting
    would make a placed character's x depend on how many other characters are
    in the shot, so adding a third character would move the two that were
    explicitly placed — placement that moves is not placement.
    """
    stage = entity.stage
    if stage is None:
        return
    if stage.at is not None:
        node.transform.x, node.transform.y = float(stage.at[0]), float(stage.at[1])
    if stage.scale != 1.0:
        node.transform.scale_x *= float(stage.scale)
        node.transform.scale_y *= float(stage.scale)


def _build_prop_subtree(
    entity: AssetRef,
    props_store: Mapping,
    *,
    textures: dict[str, AssetJSON] | None = None,
    resolutions: list[AssetResolutionJSON] | None = None,
    style_pack: "StylePack | None" = None,
    reached: set[str] | None = None,
    raster: set[str] | None = None,
) -> NodeJSON:
    """Build the subtree for one prop, through the SAME rig builder.

    The only differences from a character are the store, the `props/` art
    prefix, and the descriptor model — which is why an#108 made the first two
    arguments rather than writing a second builder.

    There is deliberately **no placeholder fallback**. A character whose art
    cannot be resolved draws the built-in humanoid, because a scene that still
    renders is more useful than one that raises. That reasoning inverts here:
    the placeholder IS a humanoid, so an unresolvable lamp would render as a
    *person* (the an#33 failure mode, arriving through the fallback meant to
    prevent it). A prop that cannot be resolved raises instead, naming the
    store and the ref.
    """
    if resolutions is None:
        resolutions = []
    meta: dict[str, Any] = {}
    if entity.ref in props_store:
        try:
            value = props_store[entity.ref]
            if isinstance(value, dict):
                meta = value
        except KeyError:
            meta = {}
    if meta.get("kind") == PATH_DOCUMENT_KIND.name:
        return _build_path_subtree(
            entity,
            meta,
            resolutions=resolutions,
            style_pack=style_pack,
            reached=reached,
        )
    if meta.get("kind") != PROP_DOCUMENT_KIND.name:
        raise CutoutCompileError(
            f"prop {entity.id!r} refers to {entity.ref!r} in the "
            f"{entity.store!r} store, which is not a PropDescriptor or a "
            "PathDescriptor"
            + (
                " (the store has no such entry)"
                if not meta
                else f" (kind={meta.get('kind')!r})"
            )
            + ". A prop has no placeholder rig on purpose: the built-in "
            "placeholder is a HUMANOID, so falling back would draw a person "
            "where the prop should be. Create it with a `prop.json` whose "
            f"`kind` is {PROP_DOCUMENT_KIND.name!r}, or remove the entity."
        )
    resolutions.append(
        AssetResolutionJSON(
            id=entity.id,
            kind="prop",
            store=entity.store,
            ref=entity.ref,
            resolved="descriptor",
        )
    )
    _note_raster_rig(entity, meta, style_pack, raster)
    already = len(resolutions)
    node = _build_svg_character_subtree(
        entity,
        meta,
        textures=textures if textures is not None else {},
        probe=_part_probe(props_store, art_prefix=PROP_ART_PREFIX),
        resolutions=resolutions,
        art_prefix=PROP_ART_PREFIX,
        descriptor_model=PropDescriptor,
        document_kind=PROP_DOCUMENT_KIND,
        digest=_raster_digest(props_store, art_prefix=PROP_ART_PREFIX),
    )
    if not _draws_anything(node) and not any(r.fallback for r in resolutions[already:]):
        # Nothing on disk is MISSING — the document simply names no art (no
        # skin, or slots with no attachment) — so `_record_missing_parts` has
        # nothing to say, and the prop used to vanish with `strict_assets`
        # silent (an#211). It is a hole in the picture like any other.
        slots = sorted(s.get("name", "?") for s in meta.get("slots") or []) or ["body"]
        resolutions.append(
            AssetResolutionJSON(
                id=entity.id,
                kind="prop",
                store=entity.store,
                ref=entity.ref,
                resolved="empty",
                fallback=True,
                detail=(
                    f"prop {entity.ref!r} draws NOTHING: none of its slot(s) "
                    f"{slots} resolves to an attachment in its `skins` (no skin, "
                    "or a slot whose `attachment` names none the skin has). "
                    'Add a skin, e.g. {"default": {"slots": '
                    '{"body": {"body": {"path": "parts/body.png"}}}}}'
                ),
            )
        )
    return node


def _draws_anything(node: NodeJSON) -> bool:
    """Whether any node in the subtree carries a visual."""
    return node.visual is not None or any(_draws_anything(c) for c in node.children)


def _build_path_subtree(
    entity: AssetRef,
    document: Mapping[str, Any],
    *,
    resolutions: list[AssetResolutionJSON],
    style_pack: "StylePack | None" = None,
    reached: set[str] | None = None,
) -> NodeJSON:
    """One node whose visual is a stroked path (an#160).

    The entity's ``overrides`` are merged over the stored document and the
    result validated strictly (:func:`an.stage.paths.resolve_path` — the same call
    `an validate` makes). Cubic Béziers are flattened HERE, so the runtime
    draws one geometry kind; what it draws from the result is specified by
    :func:`an.stage.path_geometry.path_geometry`.

    The node is the entity itself, so ``route:trim_end`` and ``route:x``
    address the same thing an author thinks of as "the arrow".

    Colour (an#161): a pack's per-entity ``stroke`` override always wins; its
    ``stroke`` ROLE replaces only the document's DEFAULT colour — a document
    that names its own ``color`` is art, and the compiler warns that the pack
    left it alone rather than recolouring it or staying quiet.
    """
    try:
        desc = resolve_path(document, entity.overrides)
    except ValueError as err:  # pydantic.ValidationError is a ValueError
        raise CutoutCompileError(
            f"path {entity.id!r} ({entity.store!r}/{entity.ref!r}, with its "
            f"overrides) is not a valid PathDescriptor: {err}"
        ) from err
    resolutions.append(
        AssetResolutionJSON(
            id=entity.id,
            kind="prop",
            store=entity.store,
            ref=entity.ref,
            resolved="path",
        )
    )
    points = flatten_curve(
        desc.points, curve=desc.curve, samples=desc.samples_per_segment
    )
    colour = _path_colour(desc, entity, style_pack, reached)
    return NodeJSON(
        name=entity.id,
        visual=VisualJSON(
            kind="path",
            color=colour,
            path=PathJSON(
                points=points,
                stroke_width=desc.width,
                color=colour,
                cap=desc.cap,
                join=desc.join,
                trim_start=desc.trim_start,
                trim_end=desc.trim_end,
                head_length=desc.head_length_px if desc.arrowhead else 0.0,
                head_width=desc.head_width_px if desc.arrowhead else 0.0,
                dash=desc.dash or 0.0,
                gap=desc.gap_px,
                dash_offset=desc.dash_offset,
            ),
        ),
    )


def _build_text_block(
    entity: AssetRef,
    document: Mapping[str, Any],
    props_store: Mapping,
    *,
    textures: dict[str, AssetJSON],
    resolutions: list[AssetResolutionJSON],
    fonts: dict[str, str],
    width: int,
    height: int,
) -> tuple[NodeJSON, str]:
    """A text block (an#155): its node, and the layer it belongs to.

    Every refusal of the typesetting path — a font that is not a file, a
    glyph the face lacks, an override the schema does not know — becomes a
    :class:`CutoutCompileError` naming the entity; nothing falls back.
    """
    try:
        node, desc, lay = build_text_subtree(
            entity,
            document,
            width=width,
            height=height,
            base_dir=font_base_dir(props_store, entity.ref),
            textures=textures,
            resolutions=resolutions,
        )
    except ValueError as err:  # TextFontError, TextLayoutError, ValidationError
        raise CutoutCompileError(
            f"text {entity.id!r} ({entity.store!r}/{entity.ref!r}, with its "
            f"overrides) cannot be set: {err}"
        ) from err
    problem = text_entity_problem(entity, desc)
    if problem is not None:
        raise CutoutCompileError(problem)
    if entity.id in fonts:
        raise CutoutCompileError(
            f"two text blocks in shot share the id {entity.id!r}; a unit path "
            f"({entity.id}/word_0) must name one node"
        )
    _apply_stage_placement(node, entity)
    fonts[entity.id] = lay.font.label()
    return node, desc.layer


def _check_text_unit_targets(
    shot: Shot, fonts: Mapping[str, str], vocab: "_SwapVocabulary"
) -> None:
    """An authored target inside a text block must name a unit it built.

    Transform targets are otherwise runtime-checked; a text block's units are
    DERIVED (``word_3`` exists only if the block has four words, and a block
    of ``unit="glyph"`` has no ``word_*`` at all), so the mistake is easy and
    is refused here, before a browser launches, naming what does exist.
    """
    if not fonts:
        return
    for action in shot.actions:
        for flat in flatten(action):
            target = getattr(flat.action, "target", None)
            if not target or "/" not in target:
                continue
            root = target.split("/", 1)[0]
            if root in fonts and target not in vocab.paths:
                built = sorted(p for p in vocab.paths if p.startswith(root + "/"))
                raise CutoutCompileError(
                    f"action targets {target!r}, which text block {root!r} does "
                    f"not build. Its units are: {built}"
                )


def _path_colour(
    desc: PathDescriptor,
    entity: AssetRef,
    style_pack: "StylePack | None",
    reached: set[str] | None,
) -> str:
    """The colour a path is drawn in under ``style_pack`` (an#161).

    A lookup with a default, like every other role: no pack, or a pack that
    does not mention ``stroke``, returns the document's own colour untouched.
    """
    if style_pack is None:
        return desc.color
    per_entity = style_pack.entities.get(entity.id, {}).get("stroke")
    role = style_pack.roles.get("stroke")
    if per_entity is not None:
        chosen = per_entity
    elif role is not None and "color" not in desc.model_fields_set:
        chosen = role
    else:
        if role is not None:
            warnings.warn(
                f"style pack {style_pack.name!r} sets a `stroke` role but path "
                f"{entity.id!r} names its own `color` ({desc.color}), which is "
                "art rather than a default and is left alone. Drop the "
                "document's `color` to let the pack decide, or set "
                f"`entities.{entity.id}.stroke` in the pack to override it.",
                CutoutCompileWarning,
                stacklevel=3,
            )
        return desc.color
    if reached is not None:
        reached.add(entity.id)
    return chosen




# -----------------------------------------------------------------------------
# Phase 11b: SVG-textured character rig from a CharacterDescriptor
# -----------------------------------------------------------------------------


#: Scene-graph pixels spanned by a descriptor's full ``view_box`` height.
#:
#: The single number that maps descriptor space to scene space. One uniform
#: factor ``k = SCENE_PX_PER_VIEW_BOX / view_box_height`` scales bone positions
#: and part extents alike — uniform by construction, so the compiler cannot
#: violate the invariant that aspect ratio is intrinsic to the art (an#74).
#:
#: 345 is a calibration, not a preference. It is what reproduces the framing the
#: seven deleted ``_SVG_*_SIZE`` constants hand-tuned: at k = 345/1024 = 0.3369,
#: ``saturated-rig``'s own art gives torso 107.8x129.4 against the old 110x130,
#: legs 37.7x118.6 against 38x120. The constants were an approximation of
#: exactly this product, which is the evidence that the rig should have been
#: driving it all along.
SCENE_PX_PER_VIEW_BOX: float = 345.0

#: The fit policy every compiled sprite carries. Named rather than inlined so
#: the one place that decides "the art keeps its shape" is greppable.
CONTAIN_FIT: str = "contain"


#: The `assets.textures` `src` prefix a rig's art is addressed under, which is
#: also the mall store that resolves it (`render.ASSET_SRC_PREFIX_TO_STORE`).
#: A parameter rather than a literal because the rig builder is the same code
#: for a character and for a prop, and the store is the ONLY thing that differs
#: about where their art lives. Two hardcoded copies of `"characters/"` — the
#: `src` builder and the probe's own — reached three call sites, and that is
#: what made "a prop is a rig too" read as a rewrite instead of an argument
#: (an#108).
CHARACTER_ART_PREFIX: str = "characters/"

#: The same, for props. Both are keys of `render.ASSET_SRC_PREFIX_TO_STORE`,
#: which is what decides where the staging step copies the art from.
PROP_ART_PREFIX: str = "props/"


def _svg_asset_src(
    ref: str, rel_path: str, *, art_prefix: str = CHARACTER_ART_PREFIX
) -> str:
    """Path used inside the runtime dir, relative to ``index.html``.

    >>> _svg_asset_src("maya", "parts/head.svg")
    'characters/maya/parts/head.svg'
    >>> _svg_asset_src("lamp", "parts/body.svg", art_prefix="props/")
    'props/lamp/parts/body.svg'
    """
    return f"{art_prefix}{ref}/{rel_path}"


def _register_texture(
    textures: dict[str, AssetJSON],
    alias: str,
    src: str,
) -> str:
    """Add a texture entry if not already present; return ``alias``."""
    if alias not in textures:
        textures[alias] = AssetJSON(src=src)
    return alias


def _part_probe(
    characters_store: Mapping,
    *,
    art_prefix: str = CHARACTER_ART_PREFIX,
) -> Callable[[str], tuple[bool, tuple[float, float] | None]] | None:
    """A probe answering ``(art exists, the size it rasterises at)`` for a part.

    **Two questions, deliberately not one.** Whether the art is *there* decides
    whether the compiler declares a texture for it; whether it can be *measured*
    decides only whether the sprite's box comes from the art or from the
    runtime's fit. Collapsing them is a real bug and it was here: a degenerate
    ``<svg/>`` is unmeasurable but present, and treating that as absent made the
    part vanish from the scene silently — trading an#79's hang for exactly the
    invisible-art failure #76 exists to stop.

    Returns ``None`` when the store has no filesystem root — **not** a probe
    that answers "absent" — because a store that can answer nothing must drop
    no parts rather than all of them.

    Size is read from the SVG root's ``width``/``height``, falling back to the
    viewBox extent as a browser does — or, for PNG/JPEG/WebP art, from the
    image header (an#211): a header parse, not a render, either way. Before
    an#211 a PNG was parsed AS SVG here and the compile died on an XML error.
    """
    root = getattr(characters_store, "_root", None)
    if root is None:
        return None
    base = Path(root)
    prefix = art_prefix

    def probe(src: str) -> tuple[bool, tuple[float, float] | None]:
        if not src.startswith(prefix):
            return False, None
        path = base / src[len(prefix) :]
        if not path.is_file():
            return False, None
        try:
            return True, art_size(path)
        except (OSError, ValueError):
            # Present but unreadable or malformed. Still declared, so the
            # failure is loud at load rather than an absence nobody sees.
            return True, None

    return probe


def _raster_digest(
    store: Mapping,
    *,
    art_prefix: str = CHARACTER_ART_PREFIX,
) -> Callable[[str], str | None]:
    """``digest(src)``: a short content digest for RASTER art, else ``None``.

    A raster texture is addressed by its bytes (an#211): the digest goes into
    the texture's alias, so a re-carved part is a different texture — the
    runtime's loader ignores a re-added alias on hot reload (an#155) — and a
    different compiled contract, whose hash then covers the pixels drawn. SVG
    art keeps its plain alias, which is what keeps every existing document
    byte-identical.
    """
    root = getattr(store, "_root", None)

    def digest(src: str) -> str | None:
        if root is None or not is_raster(src) or not src.startswith(art_prefix):
            return None
        path = Path(root) / src[len(art_prefix) :]
        try:
            return short_digest(path)
        except OSError:
            return None  # absent art is the probe's business, not this one's

    return digest


def _bone_positions(desc: Any) -> dict[str, tuple[float, float]]:
    """Absolute ``(x, y)`` per bone, in view_box units.

    Bone transforms are parent-relative, so a bone's position is the sum along
    its parent chain. A cycle or a dangling parent stops the walk rather than
    looping — a malformed rig is #78's business, not this function's.
    """
    by_name = {b.name: b for b in desc.bones}
    out: dict[str, tuple[float, float]] = {}
    for bone in desc.bones:
        x = y = 0.0
        seen: set[str] = set()
        cursor: Bone | None = bone
        while cursor is not None and cursor.name not in seen:
            seen.add(cursor.name)
            x += cursor.x
            y += cursor.y
            cursor = by_name.get(cursor.parent) if cursor.parent else None
        out[bone.name] = (x, y)
    return out


def _record_missing_parts(
    entity: AssetRef,
    missing: list[tuple[str, str, str]],
    *,
    drawn: set[str],
    into: list[AssetResolutionJSON] | None,
) -> None:
    """Record every declared part whose art is not on disk, as a fallback.

    A skin declares an inventory, and a slot that ends up with nothing to draw
    is a hole in the picture. Recording it here routes it through the one place
    that decides what a stand-in costs: audible always, fatal under
    ``strict_assets`` (an#76). Raising from the compiler instead would put a
    second policy next to that one.

    A slot that still drew *something* — one attachment missing out of several,
    as when a rig ships open eyes but no closed ones — is reported separately
    and NOT as a fallback, because the frame is not wrong, only the inventory
    is incomplete. Conflating the two would make every rig without a blink
    refuse to render under ``strict_assets``.
    """
    if into is None or not missing:
        return
    empty = [m for m in missing if m[0] not in drawn]
    partial = [m for m in missing if m[0] in drawn]
    for slot_name, attachment, path in empty:
        into.append(
            AssetResolutionJSON(
                id=f"{entity.id}/{slot_name}",
                kind="part",
                store=entity.store,
                ref=entity.ref,
                resolved="missing",
                fallback=True,
                detail=(
                    f"slot {slot_name!r} declares attachment {attachment!r} at "
                    f"{path!r}, which is not in the store — the slot draws nothing"
                ),
            )
        )
    for slot_name, attachment, path in partial:
        into.append(
            AssetResolutionJSON(
                id=f"{entity.id}/{slot_name}",
                kind="part",
                store=entity.store,
                ref=entity.ref,
                resolved="incomplete",
                fallback=False,
                detail=(
                    f"slot {slot_name!r} is missing attachment {attachment!r} at "
                    f"{path!r}; the slot still draws, but that key cannot be swapped to"
                ),
            )
        )


def _rig_origin(bones: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """The point in view_box space that the entity's placement refers to.

    The centre of the rig's bone extent, **not** the root bone. The scene root
    positions a character on x only and leaves y at 0, so this point is what
    lands at the frame's vertical centre — and a rig whose root is its ground
    contact (the default puts it at the feet, y=980) would therefore hang its
    whole body above the placement point, head off-frame.

    Centring on the extent makes framing independent of where an author chose
    to put the root, which is a rigging decision and should not be a framing
    one. On the default rig it lands at y=700, within 20 units of the torso
    bone — i.e. it reproduces the convention the deleted `torso_y = 0.0`
    literal encoded, without hardcoding a bone name.
    """
    if not bones:
        return (0.0, 0.0)
    xs = [x for x, _ in bones.values()]
    ys = [y for _, y in bones.values()]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def _build_svg_character_subtree(
    entity: AssetRef,
    desc_data: dict[str, Any],
    *,
    textures: dict[str, AssetJSON],
    probe: Callable[[str], tuple[bool, tuple[float, float] | None]] | None = None,
    resolutions: list[AssetResolutionJSON] | None = None,
    art_prefix: str = CHARACTER_ART_PREFIX,
    descriptor_model: type,
    document_kind: DocumentKind,
    texture_srcs: Mapping[str, str] | None = None,
    digest: Callable[[str], str | None] | None = None,
) -> NodeJSON:
    """Build the scene subtree for a character, **from its descriptor's rig**.

    A part may be SVG or raster (PNG/JPEG/WebP, an#211): the probe measures
    either, and ``digest(src)`` — a content digest for raster art, ``None``
    for SVG — is appended to a raster texture's alias so the texture is
    addressed by its bytes.

    **Every swap key keeps its own geometry** (an#211). A swap re-textures the
    sprite, and the box, anchor and offset were the DEFAULT attachment's, so a
    key drawn on a different canvas was fitted into the wrong box — a closed
    mouth on a thin canvas squashed every open mouth to a fraction of a pixel.
    A key whose box, anchor or offset differs from the drawn attachment's is
    listed in ``VisualJSON.asset_geometry`` and the runtime applies it with the
    texture; a rig whose keys share a canvas emits nothing new.

    ``texture_srcs`` maps a part path to the ``src`` its texture loads from
    instead of the stored file — a style pack's recoloured art
    (:func:`_recoloured_texture_srcs`). Such a texture's alias carries a digest
    of its content, so a different recolour is a different texture (the
    runtime's loader ignores a re-added alias on hot reload, an#155). The part
    is still probed and sized from the stored file, whose geometry is the same.

    Every part's position comes from a bone, every part's extent from its own
    art, and both are scaled by one uniform factor. Nothing here is a module
    constant: the seven ``_SVG_*_SIZE`` values and the four y-offset literals
    this replaced are gone, and gutting ``bones``/``slots``/``skins``/``view_box``
    now changes the output — which it provably did not before (an#73).

    A slot whose art is not on disk is recorded in ``resolutions`` as a fallback,
    which makes it audible by default and fatal under ``strict_assets`` — the
    same treatment a missing *character* already got (an#33), now reaching
    inside the descriptor to the individual part (an#76). It is recorded rather
    than raised here because the decision belongs to one place, and that place
    is :func:`_raise_or_warn_on_asset_fallbacks`.

    ``probe(src) -> (exists, size)`` answers whether a part's art is on disk and
    what size it rasterises at. Existence decides whether a texture is declared
    at all. The sprite's box is the attachment's declared ``width``/``height``
    when it has them — **a declared size wins**, with the art's aspect kept
    (:func:`an.characters.schema.attachment_box`, an#220) — else the art's own
    extent (a raster's pixel count); failing both, the runtime's ``contain``
    fit draws the art at its natural shape — never stretched to a fabricated box.
    """
    # Two documents, one builder. `PropDescriptor` carries the same field NAMES
    # the rig maths reads — view_box, bones, slots, skins, asset_sets,
    # face_overlay — and differs only in what it seeds when they are empty, so
    # the code below never asks which kind it has (an#108).
    desc = descriptor_model.model_validate(
        migrate(dict(desc_data), kind=document_kind.name)
    )
    ref = entity.ref or entity.id
    _, _, _, view_box_height = desc.view_box
    k = SCENE_PX_PER_VIEW_BOX / float(view_box_height or 1)

    skin = desc.skins.get("default") or next(iter(desc.skins.values()), Skin())
    bones = _bone_positions(desc)
    origin = _rig_origin(bones)
    # Shared with `an.characters.play` so a `play` resolves against the
    # nesting the builder actually uses (an#7 review).
    nests_under = primary_slot_per_bone(desc)

    # If the head art has its own face baked in (DiceBear / hand-drawn full
    # avatars), the separate eye/brow/mouth sprites double up with the baked
    # features. Lip-sync stays audio-only for these; hand-rig for dialogue.
    # `face_overlay` is the DECLARED fact (0.3.0, an#87) — the old vendor-name
    # check on metadata.art_provenance lives on only inside the migration.
    head_has_face = not desc.face_overlay

    def _register(slot_name: str, attachment_name: str, attachment: Attachment) -> str:
        # Slot-qualified on purpose: attachment names are a PER-SLOT namespace
        # (both eye slots carry `open`/`closed`), and the old `{entity}.{name}`
        # alias space was silently first-wins on cross-slot collision.
        alias = f"{entity.id}.{slot_name}.{attachment_name}"
        src = (texture_srcs or {}).get(attachment.path)
        if src is None:
            src = _svg_asset_src(ref, attachment.path, art_prefix=art_prefix)
            sha = digest(src) if digest is not None else None
            if sha:
                alias += "." + sha
                src = versioned_src(src, sha)
        else:
            alias += "." + hashlib.sha256(src.encode("ascii")).hexdigest()[:12]
        return _register_texture(textures, alias, src)

    def _box_of(attachment: Attachment) -> tuple[float, float] | None:
        # The declared box wins, keeping the art's aspect; else the art's own
        # extent (from its header) — a raster's pixel count (an#220).
        src = _svg_asset_src(ref, attachment.path, art_prefix=art_prefix)
        return attachment_box(
            attachment.width,
            attachment.height,
            probe(src)[1] if probe else None,
        )

    # Every attachment in the skin is registered, not just the active one, so a
    # swap has its texture already loaded when the key changes.
    #
    # Except the ones whose art is not there. A skin declares an inventory —
    # `eye_l_closed` is in the default skin and in REQUIRED_PARTS, but the bench
    # rigs do not ship it — and declaring a texture the staging step cannot find
    # makes the render fail at load over art no node draws. Registering only
    # what resolves keeps the compiler from fabricating; reporting the gap in
    # the art package is `an character validate`'s job (#78), not this one's.
    aliases: dict[str, dict[str, str]] = {}
    missing_art: list[tuple[str, str, str]] = []
    for slot_name, attachments in skin.slots.items():
        resolved_here: dict[str, str] = {}
        for name, att in attachments.items():
            src = _svg_asset_src(ref, att.path, art_prefix=art_prefix)
            if probe is not None and not probe(src)[0]:
                missing_art.append((slot_name, name, att.path))
                continue
            resolved_here[name] = _register(slot_name, name, att)
        aliases[slot_name] = resolved_here

    nodes: dict[str, NodeJSON] = {}
    children_of: dict[str, list[NodeJSON]] = {}

    for slot in sorted(desc.slots, key=lambda s: (s.draw_order, s.name)):
        parent = nests_under.get(slot.bone)
        nested = parent is not None and parent != slot.name
        # Baked face: drop every slot nested under the HEAD BONE's primary
        # slot — keyed on the bone (the rig's skeleton contract), not on the
        # slot name "head": a rig whose head slot is named otherwise used to
        # get its face overlays (and their blinks) back (an#88 review).
        if nested and head_has_face and parent == nests_under.get("head"):
            continue

        resolved = drawn_attachment(desc, skin, slot)
        if resolved is None or resolved[0] not in aliases.get(slot.name, {}):
            continue
        attachment_name, attachment = resolved

        # Position = the slot's bone, plus the attachment's own offset from it.
        # Both are needed: five face parts share one `head` bone, so the bone
        # alone would stack them, and the offset alone would ignore the rig.
        bone_x, bone_y = bones.get(slot.bone, (0.0, 0.0))
        if nested:
            parent_x, parent_y = bones.get(parent, (0.0, 0.0))
            bone_x, bone_y = bone_x - parent_x, bone_y - parent_y
        else:
            bone_x, bone_y = bone_x - origin[0], bone_y - origin[1]
        bone_x += attachment.x
        bone_y += attachment.y

        extent = _box_of(attachment)
        visual = VisualJSON(
            kind="svg_sprite",
            asset_id=aliases[slot.name][attachment_name],
            anchor_x=attachment.anchor[0],
            anchor_y=attachment.anchor[1],
            fit=CONTAIN_FIT,
            **({"width": extent[0] * k, "height": extent[1] * k} if extent else {}),
        )
        # The per-slot PROJECTION of the descriptor's asset_sets (an#87): a
        # channel projects onto every slot whose attachments its keys name —
        # `viseme` lands on the mouth because the mouth's attachments carry
        # the viseme map's values, `eyelid` lands on BOTH eye slots because
        # both carry `open`/`closed`. No slot names appear here: the skin is
        # the binding. Keys whose art did not resolve are absent from the map
        # (an inventory gap — `_record_missing_parts` records it; a key a
        # channel actually USES escalates via the fallback machinery).
        projected = {
            channel: resolved
            for channel, key_map in desc.asset_sets.items()
            if (
                resolved := {
                    key: aliases[slot.name][name]
                    for key, name in key_map.items()
                    if name in aliases[slot.name]
                }
            )
        }
        if projected:
            visual.asset_sets = projected
            geometry = _swap_key_geometry(
                projected,
                aliases[slot.name],
                skin.slots.get(slot.name, {}),
                drawn=attachment,
                built=extent,
                box_of=_box_of,
                k=k,
            )
            if geometry:
                visual.asset_geometry = geometry

        node = NodeJSON(
            name=slot.name,
            transform=TransformJSON(x=bone_x * k, y=bone_y * k),
            visual=visual,
        )
        nodes[slot.name] = node
        children_of.setdefault(parent if nested else "", []).append(node)

    _record_missing_parts(entity, missing_art, drawn=set(nodes), into=resolutions)

    for parent_name, kids in children_of.items():
        if parent_name and parent_name in nodes:
            nodes[parent_name].children = kids

    return NodeJSON(
        name=entity.id,
        transform=TransformJSON(),
        children=children_of.get("", []),
    )


def _swap_key_geometry(
    projected: Mapping[str, Mapping[str, str]],
    alias_of: Mapping[str, str],
    attachments: Mapping[str, Attachment],
    *,
    drawn: Attachment,
    built: tuple[float, float] | None,
    box_of: Callable[[Attachment], tuple[float, float] | None],
    k: float,
) -> dict[str, dict[str, float]]:
    """``{asset_id: geometry}`` for each swap key drawn unlike the built one.

    The geometry is the key's own fit box (its art's extent × ``k``, the rig's
    one uniform scale), its anchor, and its offset from the drawn attachment
    in scene pixels — so every key is placed and scaled exactly as it would be
    if it were the slot's default. A key whose art cannot be measured keeps
    the built box: there is nothing better to say about it.

    >>> a = Attachment(path="parts/m_x.svg", width=100, height=10)
    >>> b = Attachment(path="parts/m_a.svg", width=100, height=60, y=5)
    >>> _swap_key_geometry({"viseme": {"X": "c.m.x", "A": "c.m.a"}},
    ...                    {"x": "c.m.x", "a": "c.m.a"}, {"x": a, "a": b},
    ...                    drawn=a, built=(100, 10),
    ...                    box_of=lambda att: (att.width, att.height), k=0.5)
    {'c.m.a': {'width': 50.0, 'height': 30.0, 'anchor_x': 0.5, 'anchor_y': 0.5, 'x': 0.0, 'y': 2.5}}
    """
    name_of = {alias: name for name, alias in alias_of.items()}
    built_geometry = (
        (float(built[0]) * k, float(built[1]) * k) if built else None,
        (float(drawn.anchor[0]), float(drawn.anchor[1])),
        (0.0, 0.0),
    )
    out: dict[str, dict[str, float]] = {}
    for key_map in projected.values():
        for alias in key_map.values():
            if alias in out or alias not in name_of:
                continue
            att = attachments.get(name_of[alias])
            if att is None:
                continue
            box = box_of(att)
            if box is None:
                continue
            geometry = (
                (float(box[0]) * k, float(box[1]) * k),
                (float(att.anchor[0]), float(att.anchor[1])),
                (
                    (float(att.x) - float(drawn.x)) * k,
                    (float(att.y) - float(drawn.y)) * k,
                ),
            )
            if geometry == built_geometry:
                continue
            (w, h), (ax, ay), (dx, dy) = geometry
            out[alias] = {
                "width": w,
                "height": h,
                "anchor_x": ax,
                "anchor_y": ay,
                "x": dx,
                "y": dy,
            }
    return out


# -----------------------------------------------------------------------------
# Action → animations + timeline tracks
# -----------------------------------------------------------------------------


class ActionLowering(Protocol):
    """How a genre's action kind becomes clips in the stage compiler (an#225).

    Registered as :attr:`an.genres.ActionKind.lowering`. The stage knows no
    kind by name beyond its own (``tween``, ``set``); a genre's kind supplies:

    - ``extent_resolver(vocab)``: ``action -> seconds`` for a leaf that names no
      duration (or ``None``);
    - ``expand(flat_list, *, vocab, fps, step_hz, default_easing, resolutions)``:
      the flat list with this kind's leaves replaced by what they stand for;
    - ``view_of(entity_swaps, vocab, *, duration)``: ``flat -> view name | None``
      (or ``None``), for kinds whose clips depend on the view in force;
    - ``clip(action, *, anim_id, vocab, fps, view)``: the animation clip of one
      leaf that survived ``expand``.
    """

    def extent_resolver(self, vocab: Any) -> Callable[[Any], float] | None: ...

    def expand(self, flat_list: list, **kw: Any) -> list: ...

    def view_of(
        self, entity_swaps: Any, vocab: Any, *, duration: float
    ) -> Callable[[Any], str | None] | None: ...

    def clip(self, action: Any, **kw: Any) -> AnimationClipJSON: ...


def _lowerings() -> tuple[ActionLowering, ...]:
    """The lowerings genres registered, in action-kind name order."""
    found = (action_kind(n) for n in sorted(action_kind_names()))
    return tuple(k.lowering for k in found if k is not None and k.lowering is not None)


def _lowering_of(action: Any) -> ActionLowering | None:
    """The lowering of ``action``'s kind that produces a clip for it, or ``None``."""
    kind = action_kind(getattr(action, "kind", ""))
    return kind.lowering if kind is not None and getattr(kind.lowering, "clip", None) else None


def _compile_actions(
    actions: list[Action],
    shot_duration: float,
    *,
    vocab: _SwapVocabulary | None = None,
    resolutions: list[AssetResolutionJSON] | None = None,
    fps: int = 30,
    step_hz: float | None = None,
    default_easing: Any = None,
    entity_swaps: list["_EntitySwap"] | None = None,
) -> tuple[dict[str, AnimationClipJSON], list[TrackJSON]]:
    """Flatten authoring actions and convert to animation clips.

    A ``set`` of a swap set on the ENTITY ITSELF fans out to every slot the
    set projects onto (:func:`_fan_out_entity_swaps`, an#197); each such swap
    is appended to ``entity_swaps`` when given, for the pose layer.

    A ``play`` of a MOTION PRESET is replaced by the tweens and settling sets
    it stands for before anything else looks (the ``play`` lowering's ``expand``,
    an#166), so from here on it is ordinary authored motion — stepped under
    ``step_hz`` like any tween, which is what the ``an.motion`` macro spelling
    of the same preset has always been.

    Tweens and plays compile per action. **Set actions compile per
    (target, property) group into step channels that HOLD from each set until
    the next action on that target/property** — the next set joins the same
    channel as a keyframe; a tween ends the hold at its start; with nothing
    following, the hold runs to the shot end (an#87) — the viseme-clip shape.

    Precedence at an instant where both apply is fixed by TRACK ORDER, which
    the evaluators read later-wins: every hold clip is placed BEFORE the
    track's per-action clips, so **an active tween governs** — at the shared
    handoff instant the tween's first frame shows (an end-inclusive hold
    listed after the tween used to mask it, measured), and a set authored
    inside a running tween's window takes effect when that window ends, not
    mid-tween. The previous
    per-set 0.001s placement window had two defects: a set at a
    non-frame-aligned time (``at=3.02`` @30fps, window [3.02, 3.021] between
    samples) silently never fired, and when one did fire its persistence was
    an accident of stateful forward rendering, false under backward scrubbing.

    ``vocab`` (when compiling a real shot) enables the swap checks: an
    authored action on a non-transform property must name a declared asset
    set and key of its target — see :func:`_check_swap_action`.
    """
    animations: dict[str, AnimationClipJSON] = {}
    placed_by_track: dict[str, list[PlacedClipJSON]] = {}

    flat_list: list[FlatAction] = []
    # A duration-less play advances a `sequence` by its NATURAL length, read
    # through the entity's descriptor: the resolver `an validate` uses too.
    lowerings = _lowerings()
    extent = next(
        (r for r in (low.extent_resolver(vocab) for low in lowerings) if r), None
    )
    for action in actions:
        flat_list.extend(flatten(action, play_extent=extent))
    # BEFORE the swap dispatch: `tint` is not in the transform vocabulary, so a
    # leaf still spelling it would be read as an asset-set name (an#62). And
    # before the timeline pass below, so a from-less tint tween starts from
    # the tint in force per channel (an#212).
    flat_list = _expand_tint_actions(flat_list)
    # What a genre's own kinds stand for (a `play` of a motion preset becomes
    # tweens; an `expression` leaf, the face solver's input, becomes nothing).
    for low in lowerings:
        flat_list = low.expand(
            flat_list,
            vocab=vocab,
            fps=fps,
            step_hz=step_hz,
            default_easing=default_easing,
            resolutions=resolutions,
        )
    # AFTER the tint expansion, like the swap dispatch: a `tint` set on a
    # character root is a colour, not a whole-character swap (an#197 review).
    flat_list = _fan_out_entity_swaps(
        flat_list, vocab=vocab, resolutions=resolutions, record=entity_swaps
    )
    swap_props = _swap_property_names(flat_list)
    # The view each entity is in over the shot, for a character with per-view
    # face sets (an#220): a descriptor `play` (a blink) in a profile swaps the
    # profile's eyelids. Read off the fan-out's record, so it sees every turn.
    view_of = None
    if vocab is not None and entity_swaps is not None:
        for low in lowerings:
            view_of = low.view_of(entity_swaps, vocab, duration=shot_duration) or view_of

    if vocab is not None:
        for flat in flat_list:
            _check_trim_target(flat, vocab=vocab)
    if vocab is not None:
        flat_list = [
            flat
            for flat in flat_list
            if _check_swap_action(flat, vocab=vocab, resolutions=resolutions)
        ]

    set_groups: dict[tuple[str, str], list[FlatAction]] = {}
    tween_starts: dict[tuple[str, str], list[float]] = {}
    hold_by_track: dict[str, list[PlacedClipJSON]] = {}
    ordinal = 0
    for flat in flat_list:
        if isinstance(flat.action, SetAction):
            key = (flat.action.target, flat.action.property)
            set_groups.setdefault(key, []).append(flat)
            continue
        if isinstance(flat.action, TweenAction):
            key = (flat.action.target, flat.action.property)
            tween_starts.setdefault(key, []).append(flat.start)
        anim_id, track_root, placed = _compile_one(flat, ordinal=ordinal)
        ordinal += 1
        if anim_id is not None and anim_id not in animations:
            animations[anim_id] = _build_anim_for(
                flat,
                anim_id,
                swap_properties=swap_props,
                vocab=vocab,
                fps=fps,
                step_hz=step_hz,
                default_easing=default_easing,
                view_of=view_of,
            )
        if (
            flat.action.kind == "play"
            and flat.action.duration is None
            and anim_id is not None
            and animations[anim_id].loop_mode == "loop"
        ):
            # A LOOP with no window to fill is a loop that never loops: the
            # placement defaulted to the animation's natural duration, so
            # `play("gale", "idle_breath")` stopped after one cycle — issue
            # #7's title, one layer up (an#7 review). "Keep going" means to
            # the shot end; both evaluators divide the window by `speed`, so
            # the window is stretched by it to land there.
            placed = placed.model_copy(
                update={
                    "duration": max(0.001, (shot_duration - flat.start) * placed.speed)
                }
            )
        placed_by_track.setdefault(track_root, []).append(placed)

    for (target, prop), group in set_groups.items():
        group.sort(key=lambda f: f.start)
        boundaries = sorted(tween_starts.get((target, prop), []))
        # A set holds until the NEXT ACTION on the same (target, property):
        # the next set joins the same channel as a keyframe, but a tween ends
        # the hold at its start so the tween governs from there and its end
        # value persists after it (the runtime's stateful hold, unchanged).
        # Holding to the shot end regardless would let a `set` placed AFTER
        # the tween clips in the track mask the tween for the whole shot —
        # measured, and the most common authoring shape ("set the start
        # pose, then animate") was a no-op tween (an#87 review).
        for run in _set_runs(group, boundaries):
            first = run[0].start
            end = next((b for b in boundaries if b >= first), shot_duration)
            anim_id = f"__set__{ordinal}"
            ordinal += 1
            kfs = []
            for flat in run:
                value = flat.action.value
                _check_keyframe_value(
                    value,
                    target=target,
                    prop=prop,
                    space_of=vocab.space_of if vocab is not None else None,
                )
                if flat.start > shot_duration:
                    warnings.warn(
                        f"set on {target!r}:{prop!r} at t={flat.start} is past "
                        f"the shot's end ({shot_duration}s) and can never show.",
                        CutoutCompileWarning,
                        stacklevel=3,
                    )
                kfs.append(
                    KeyframeJSON(time=flat.start - first, value=value, easing="step")
                )
            duration = max(0.001, end - first)
            animations[anim_id] = AnimationClipJSON(
                name=anim_id,
                duration=duration,
                channels=[ChannelJSON(target=target, property=prop, keyframes=kfs)],
            )
            hold_by_track.setdefault(_track_root_of(target), []).append(
                PlacedClipJSON(
                    animation_id=anim_id, start_time=first, duration=duration
                )
            )
    # Holds FIRST in every track — see the docstring: later-wins evaluation
    # must let an active tween override a hold at the shared instant.
    for root, holds in hold_by_track.items():
        placed_by_track[root] = holds + placed_by_track.get(root, [])

    # Re-pass: every referenced animation must actually exist. Since an#7
    # every `play` mints its own resolved clip, so this can only fire on a
    # placement built by hand; it once fabricated an empty clip instead,
    # which is how `play` came to look wired up while animating nothing.
    for placed_list in placed_by_track.values():
        for p in placed_list:
            if p.animation_id not in animations:
                raise CutoutCompileError(
                    f"placement references animation {p.animation_id!r}, which "
                    "no clip defines."
                )

    tracks = [
        TrackJSON(target_root=root, clips=clips)
        for root, clips in placed_by_track.items()
    ]
    return animations, tracks


def _set_runs(
    sets: list[FlatAction], tween_starts: list[float]
) -> list[list[FlatAction]]:
    """``sets`` (sorted by start) cut into runs that each compile to ONE hold
    clip: a set joins the run before it unless a tween on the same (target,
    property) starts in between — see :func:`_compile_actions`. Shared with
    :func:`_value_at`, so a from-less tween reads the holds the runtime plays."""
    runs: list[list[FlatAction]] = []
    for flat in sets:
        if runs and not any(runs[-1][0].start <= b <= flat.start for b in tween_starts):
            runs[-1].append(flat)
        else:
            runs.append([flat])
    return runs


@dataclass(frozen=True)
class _EntitySwap:
    """A swap set applied to a whole character at one instant (an#197)."""

    entity_id: str
    set_name: str
    time: float
    key: str


def _fan_out_entity_swaps(
    flat_list: list[FlatAction],
    *,
    vocab: _SwapVocabulary | None,
    resolutions: list[AssetResolutionJSON] | None = None,
    record: list[_EntitySwap] | None = None,
) -> list[FlatAction]:
    """A ``set`` of a swap set on the ENTITY ITSELF becomes the same ``set`` on
    every slot the set projects onto — one key turns a whole character (an#197).

    ``{kind: set, target: maya, property: view, value: side}`` swaps the head
    AND the torso to their ``side`` art; each fanned-out swap is then checked
    like any authored one (:func:`_check_swap_action`). The swap is recorded in
    ``record`` so :func:`_swap_pose_layer` can pose the slots the key lists in
    the descriptor's ``swap_poses``. Set-name-agnostic: ``view`` is a
    convention, and a ``hands`` set fans out to both hands the same way.

    Only a character with a descriptor, and only when the entity node does not
    carry the set itself; a tween of a swap on the entity is left to the
    ordinary check, which names the nodes that carry the set.
    """
    if vocab is None:
        return flat_list
    out: list[FlatAction] = []
    for flat in flat_list:
        action = flat.action
        prop = getattr(action, "property", None)
        if (
            not isinstance(action, SetAction)
            or "/" in action.target
            or prop in _PROPERTY_REST_VALUES
            or prop in TRANSFORM_PROPERTIES
            or prop == TINT_PROPERTY
            or action.target not in vocab.descriptors
            or prop in vocab.node_sets.get(action.target, {})
        ):
            out.append(flat)
            continue
        entity_id = action.target
        declared = vocab.declared.get(entity_id, {})
        if prop not in declared:
            raise CutoutCompileError(
                f"action sets {entity_id!r}:{prop!r}, but {entity_id!r}'s "
                f"descriptor declares no asset set named {prop!r} (it has: "
                f"{sorted(declared)}). A property that is not a transform must "
                "name a declared swap set"
                + (
                    " — a character made before an#197 has no views: "
                    "`an character add-views` draws them."
                    if prop == "view"
                    else "."
                )
            )
        if not isinstance(action.value, str) or action.value not in declared[prop]:
            raise CutoutCompileError(
                f"action sets {entity_id!r}:{prop!r} to {action.value!r}, which is "
                f"not a declared key of that set (it has: {sorted(declared[prop])})."
            )
        capable = vocab.swap_capable_paths(entity_id, prop)
        if not capable:
            _record_used_swap_fallback(
                resolutions,
                entity_id,
                entity_id,
                prop,
                detail=(
                    f"the {prop!r} set is declared but none of its art resolved "
                    f"on any node of {entity_id!r}, so the swap to "
                    f"{action.value!r} shows no art (only its pose, if any)"
                ),
            )
        for path in capable:
            out.append(
                FlatAction(
                    start=flat.start,
                    end=flat.end,
                    action=action.model_copy(update={"target": path}),
                )
            )
        if record is not None:
            record.append(_EntitySwap(entity_id, prop, float(flat.start), action.value))
    return out


#: ``(node path, property) -> [(time, value)]``: a step function, first key at 0.
_StepCurve = list[tuple[float, float]]

















def _compile_one(
    flat: FlatAction, *, ordinal: int
) -> tuple[str | None, str, PlacedClipJSON]:
    """Convert one non-set FlatAction into (animation_id, track_root, placed).

    Set actions never reach here — they compile per (target, property) group
    in :func:`_compile_actions` (an#87).
    """
    action = flat.action
    if isinstance(action, TweenAction):
        anim_id = f"__tween__{ordinal}"
        placed = PlacedClipJSON(
            animation_id=anim_id,
            start_time=flat.start,
            duration=action.duration,
        )
        return anim_id, _track_root_of(action.target), placed
    if action.kind == "play":
        # Per-INSTANCE clip (an#7): two plays of one descriptor animation
        # must not share a clip, or the second's loop/speed silently wins
        # for both. `duration=None` keeps the animation's natural duration
        # (the runtime reads a null placement duration as the clip's own).
        anim_id = f"__play__{ordinal}"
        placed = PlacedClipJSON(
            animation_id=anim_id,
            start_time=flat.start,
            duration=action.duration,
            speed=action.speed,
        )
        return anim_id, _track_root_of(action.target), placed
    # A kind some genre registered that this renderer has no clip for: said
    # by name rather than as a bare TypeError (the IR is open, ADR 0001
    # decision 2, so "a kind the cutout compiler does not draw" is a real,
    # reachable case, not a programming error).
    raise CutoutCompileError(
        f"the cutout renderer cannot draw a {getattr(action, 'kind', None)!r} "
        f"action ({type(action).__name__}) on {getattr(action, 'target', '?')!r}: "
        "it compiles set, tween and the cut-out genre's play and expression"
    )


def _check_keyframe_value(
    value: Any,
    *,
    target: str,
    prop: str,
    space_of: Callable[[str], Any] | None = None,
) -> Any:
    """Refuse keyframe values the two evaluators would disagree on.

    ``bool`` is the trap: Python's ``isinstance(True, int)`` would lerp it while
    JS's ``typeof true === 'boolean'`` snaps it — a channel whose value
    interpolates in the spec and snaps in the browser. ``None`` is the other:
    the Python spec would carry it into the pose while the runtime drops null
    values (``runtime.js`` ``evaluateTimeline``), so the two sides render
    different pictures. Neither has a meaning worth keeping: a discrete state
    is a string key, a numeric one is an ``int``/``float``.
    """
    if value is None or isinstance(value, bool):
        raise CutoutCompileError(
            f"keyframe on {target!r}:{prop!r} has value {value!r}; keyframe "
            "values must be numbers (int/float) or string keys — bool and None "
            "evaluate differently in the Python spec and the JS runtime, so "
            "the compiler refuses them rather than pick a side silently."
        )
    # The value must fit the field kind the stage node DECLARES for `prop`
    # (an#239 item 2, the precondition of the declared-kinds default): a
    # string on `x` used to compile, the runtime snapped it, and the declared
    # evaluator now refuses it — so the compiler says so first, by name.
    # The space comes from the target's entity kind (`space_of`, the policy
    # `an validate` uses); without a shot's vocabulary, the stage node's.
    from an.timing.spaces import get_space

    space = space_of(target) if space_of is not None else get_space(STAGE_NODE_SPACE)
    kind = space.kind_of(prop)
    problem = kind.check(value)
    if problem:
        raise CutoutCompileError(
            f"keyframe on {target!r}:{prop!r}: {problem}. `{prop}` is a "
            f"{kind.name} field of a stage node (the {space.name!r} property "
            "space), so a value of another kind cannot be keyed on it."
        )
    return value


def _refuse_unregistered_entity_kinds(shot: Shot) -> None:
    """An entity whose ``kind`` nothing registered is REFUSED, naming the genre
    that provides it — never skipped (review-244 S2). ``AssetRef.kind`` is a
    ``str`` since ADR 0001 decision 2, so the entity dispatch below would
    otherwise draw a typo'd ``kind: enviroment`` as nothing, and the render
    would succeed without its backdrop."""
    from an.genres import providers_of
    from an.genres.registry import (
        UnregisteredKindError,
        entity_kind,
        entity_kind_names,
    )

    for entity in shot.entities:
        if entity_kind(entity.kind) is None:
            error = UnregisteredKindError(
                "entity kind",
                entity.kind,
                known=entity_kind_names(),
                providers=providers_of(entity.kind, registry="entity kinds"),
                where=f"shot {shot.id!r}: entity {entity.id!r}",
            )
            raise CutoutCompileError(str(error)) from error


#: The property space every compiled node lives in (:mod:`an.timing.spaces`).
STAGE_NODE_SPACE: str = "stage.node"


def parse_tint(value: object, *, where: str) -> tuple[float, float, float]:
    """A `#rrggbb` string to three multipliers in 0..1.

    Per-channel in **sRGB** — on the 8-bit values as written — not linear-light.
    `tint` is a multiply the GPU applies in the space the author read the hex
    out of, and a fade between two hex values that did not pass through the
    values between them would surprise whoever wrote them (an#62).
    """
    if not isinstance(value, str) or not _HEX_COLOUR.fullmatch(value):
        raise CutoutCompileError(
            f"{where}: `tint` takes a `#rrggbb` colour string, got {value!r}. "
            f"Hex strings are the house colour representation — the same reason "
            f"`an.styles.StylePack` gives — so there is one spelling of a colour "
            f"in a compiled document rather than two that can disagree."
        )
    raw = value.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _expand_tint_actions(flat_list: list[FlatAction]) -> list[FlatAction]:
    """Rewrite each authored `tint` leaf into three numeric component leaves.

    Done HERE, on the flat list, so everything downstream — the swap-set
    dispatch, the step resampler, the channel builder — sees only numbers and
    needs to know nothing about colour. A `tint` leaf that reached
    `_swap_property_names` would be classified as an asset-set name, because
    that is what "not in the transform vocabulary" means.
    """
    out: list[FlatAction] = []
    for flat in flat_list:
        action = flat.action
        if getattr(action, "property", None) != TINT_PROPERTY:
            out.append(flat)
            continue
        where = f"{type(action).__name__.lower()} on {action.target!r}"
        if isinstance(action, SetAction):
            triples = {"value": parse_tint(action.value, where=where)}
        else:
            triples = {
                field: parse_tint(getattr(action, field), where=where)
                for field in ("from_value", "to_value")
                if getattr(action, field, None) is not None
            }
        for index, component in enumerate(TINT_COMPONENTS):
            replacement = action.model_copy(
                update={
                    "property": component,
                    **{field: v[index] for field, v in triples.items()},
                }
            )
            out.append(dataclasses.replace(flat, action=replacement))
    return out


def _swap_property_names(flat_list: list[FlatAction]) -> frozenset[str]:
    """Property names in ``flat_list`` that are swap sets, not transforms.

    A property outside the transform vocabulary names an asset set (an#87).
    Derived from the actions rather than the descriptors so the STEP-EASING
    rule below applies even when compiling without a mall.
    """
    out = set()
    for flat in flat_list:
        prop = getattr(flat.action, "property", None)
        if prop and prop not in _PROPERTY_REST_VALUES:
            out.add(prop)
    return frozenset(out)


def _build_anim_for(
    flat: FlatAction,
    anim_id: str,
    *,
    swap_properties: frozenset[str] = frozenset(),
    vocab: _SwapVocabulary | None = None,
    fps: int = 30,
    step_hz: float | None = None,
    default_easing: Any = None,
    view_of: Callable[[FlatAction], str | None] | None = None,
) -> AnimationClipJSON:
    action = flat.action
    lowering = _lowering_of(action)
    if lowering is not None:
        return lowering.clip(
            action,
            anim_id=anim_id,
            vocab=vocab,
            fps=fps,
            view=view_of(flat) if view_of is not None else None,
        )
    if isinstance(action, TweenAction):
        from_value = action.from_value
        if from_value is None and vocab is not None:
            from_value = vocab.path_trims.get(action.target, {}).get(action.property)
        if from_value is None:
            from_value = _rest_value_for(action.property, action.target)
        space_of = vocab.space_of if vocab is not None else None
        _check_keyframe_value(
            from_value, target=action.target, prop=action.property, space_of=space_of
        )
        _check_keyframe_value(
            action.to_value,
            target=action.target,
            prop=action.property,
            space_of=space_of,
        )
        easing = _easing_to_json(action.resolved_easing(default_easing))
        # Only an easing the author actually WROTE earns a warning:
        # TweenAction's default is 'ease_in_out', so a swap tween with no
        # easing given would otherwise be told it "asked for" one.
        authored_non_step = (
            action.property in swap_properties
            and "easing" in action.model_fields_set
            and easing != "step"
        )
        if action.property in swap_properties:
            easing = "step"
        if authored_non_step:
            # Swap channels are stepped by FORMAT, not by taste — Spine's
            # attachment keyframes carry {time, name} and no curve field at
            # all. The evaluator already refuses to ease a non-numeric value
            # (the snap is time-based, an#86), so forcing step here changes
            # no pixel; what it changes is honesty — the serialized scene
            # says what will happen. Warn so the author learns the rule
            # rather than wondering where their easing went.
            warnings.warn(
                f"tween on {action.target!r}:{action.property!r} asked for "
                f"easing {action.easing!r}, but {action.property!r} is a swap "
                "set and swap channels are always step-interpolated (a "
                "discrete key cannot be eased). Compiling with easing='step'.",
                CutoutCompileWarning,
                stacklevel=2,
            )
        keyframes = [
            KeyframeJSON(time=0.0, value=from_value, easing=easing),
            KeyframeJSON(time=action.duration, value=action.to_value),
        ]
        # The CONTRACT is this guard: swap properties are never stepped here
        # (they are stepped by format). `_stepped_keyframes`' own non-numeric
        # early return is the defence behind it, so the two are redundant by
        # design — drop this one and the swap test still passes (an#89 review).
        if step_hz is not None and action.property not in swap_properties:
            keyframes = _stepped_keyframes(
                keyframes, start=flat.start, duration=action.duration, step_hz=step_hz
            )
        return AnimationClipJSON(
            name=anim_id,
            duration=action.duration,
            channels=[
                ChannelJSON(
                    target=action.target,
                    property=action.property,
                    keyframes=keyframes,
                )
            ],
        )
    raise TypeError(f"unsupported anim build for {type(action).__name__}")


def step_times(start: float, duration: float, step_hz: float) -> list[float]:
    """Clip-local times at which a stepped tween updates its pose (an#89).

    The grid is SHOT-wide — multiples of ``1/step_hz`` on the shot's clock,
    shared by every tween in the shot — not the tween's own: "on twos" means
    every character changes pose on the same frames, so a tween starting at
    0.033 s updates at the next grid point, not 0.033 s later. (Shots compile
    independently, so the grid restarts at each cut.) Local 0 (the tween's
    start) and ``duration`` (where the end value lands) are always present, so
    a tween shorter than one step is a single step to its end value.

    ``step_hz`` must be positive: with a non-positive rate the walk below never
    reaches ``duration`` — an infinite loop, not an error — so it is refused.

    >>> step_times(0.0, 0.3, 10)
    [0.0, 0.1, 0.2, 0.3]
    >>> [round(t, 3) for t in step_times(0.05, 0.3, 10)]
    [0.0, 0.05, 0.15, 0.25, 0.3]
    >>> step_times(0.0, 0.02, 10)
    [0.0, 0.02]
    """
    if not step_hz > 0:
        raise ValueError(f"step_hz must be positive; got {step_hz!r}")
    eps = 1e-9
    j = math.ceil(start * step_hz - eps)
    times = [0.0]
    while True:
        t = j / step_hz - start
        if t >= duration - eps:
            break
        if t > eps:
            times.append(t)
        j += 1
    times.append(float(duration))
    return times


def _stepped_keyframes(
    keyframes: list[KeyframeJSON], *, start: float, duration: float, step_hz: float
) -> list[KeyframeJSON]:
    """Resample a numeric tween's curve onto the step grid, step-eased.

    The curve is evaluated through the Python spec (`channel.evaluate`) — the
    same evaluator the parity tests hold against the runtime — so a stepped
    tween shows exactly the values the smooth one would at each grid time,
    then holds. Non-numeric (swap) values are left alone: they are stepped by
    format already, and easing never applied to them.
    """
    from an.timing.channel import Channel, Keyframe, evaluate

    if not all(isinstance(k.value, (int, float)) for k in keyframes):
        return keyframes
    channel = Channel(
        "_",
        "_",
        [
            Keyframe(
                k.time,
                k.value,
                tuple(k.easing) if isinstance(k.easing, list) else k.easing,
            )
            for k in keyframes
        ],
    )
    return [
        KeyframeJSON(time=t, value=float(evaluate(channel, t)), easing="step")
        for t in step_times(start, duration, step_hz)
    ]


def _check_default_easing(spec: Any) -> None:
    """Refuse a scene default easing the evaluators would refuse — at compile,
    because a render never runs ``an validate``, and a typo here would
    otherwise surface as a runtime throw on the first tween of every shot."""
    try:
        apply_easing(spec, 0.5)
    except (ValueError, TypeError) as e:
        raise CutoutCompileError(f"meta.default_easing {spec!r}: {e}") from e


def _check_keyframe_easings(
    animations: dict[str, AnimationClipJSON], *, shot_id: str
) -> None:
    """Refuse any keyframe easing the stage runtime cannot draw (an#233 review,
    S1): what compiles is what ``runtime.js`` can evaluate, instead of a throw
    in the browser."""
    for anim_id, anim in animations.items():
        for ch in anim.channels:
            for k in ch.keyframes:
                try:
                    apply_easing(k.easing, 0.5)
                except (ValueError, TypeError) as e:
                    raise CutoutCompileError(
                        f"shot {shot_id!r}: {ch.target}:{ch.property} keyframe at "
                        f"t={k.time} in {anim_id!r}: {e}"
                    ) from e


















def _built_value(target: str, prop: str, *, vocab: _SwapVocabulary | None) -> float:
    """What ``target``'s ``prop`` shows before anything animates it: its BUILT
    transform (a ``stage`` placement, a laid-out ``x``), a path's own trim, or
    the property's identity (:data:`_PROPERTY_REST_VALUES`)."""
    if vocab is not None:
        trim = vocab.path_trims.get(target, {}).get(prop)
        if trim is not None:
            return float(trim)
        transform = vocab.node_transforms.get(target)
        field_name = "rotation" if prop == "rotation_rad" else prop
        if transform is not None and field_name in TransformJSON.model_fields:
            return float(getattr(transform, field_name))
    return _rest_value_for(prop, target)


def _value_at(
    entries: list[tuple[tuple[int, int], FlatAction]],
    prop: str,
    t: float,
    base: float,
    *,
    vocab: _SwapVocabulary | None,
    fps: int,
    step_hz: float | None,
    default_easing: Any,
) -> float:
    """The value one (target, property) shows at ``t``, from the ``set``s and
    tweens in ``entries`` that start at or before it — compiled the way
    :func:`_compile_actions` compiles them (sets as step holds cut by
    :func:`_set_runs`, placed first; tweens after, in authoring order) and
    evaluated by the executable spec of the runtime,
    :func:`~an.stage.timeline.evaluate_timeline`, so the answer is
    the runtime's by construction: an active tween governs, otherwise the
    latest write holds. ``base`` when nothing has written it yet (an#212).

    ``entries`` are one node's writes of ``prop``'s write group (``rotation``
    and ``rotation_rad`` are one). Only the writes that can still show at ``t``
    are compiled — the latest set and whatever did not end before it or before
    the latest-ending finished tween — so a long chain on one property costs
    one short evaluation per tween, not the whole history each time.
    """
    from an.stage.timeline import (
        PlacedClip,
        Timeline,
        Track,
        clip_from_json,
        evaluate_timeline,
        write_group,
    )

    earlier = [(k, f) for k, f in entries if f.start <= t + 1e-12]
    if not earlier:
        return base
    # Prune what cannot show at t: before the latest set (it holds from there,
    # or is cut by a tween that is itself kept), and any tween that ended
    # before the latest-ending one that has ended (a held end loses to a later
    # end). Ties are kept, so later-wins still decides between them.
    last_set = max(
        (f.start for _, f in earlier if isinstance(f.action, SetAction)),
        default=-math.inf,
    )
    ended = max(
        (f.end for _, f in earlier if isinstance(f.action, TweenAction) and f.end < t),
        default=-math.inf,
    )
    cutoff = max(last_set, ended)
    earlier = [
        (k, f)
        for k, f in earlier
        if (f.start >= last_set if isinstance(f.action, SetAction) else f.end >= cutoff)
    ]
    tweens = [
        f
        for _, f in sorted(earlier, key=lambda e: e[0])
        if isinstance(f.action, TweenAction)
    ]
    sets = sorted(
        (f for _, f in earlier if isinstance(f.action, SetAction)),
        key=lambda f: f.start,
    )
    boundaries = sorted(f.start for f in tweens)
    placed: list[PlacedClip] = []
    target = prop = ""
    for run in _set_runs(sets, boundaries):
        first = run[0].start
        end = next((b for b in boundaries if b >= first), t + 1.0)
        target, prop = run[0].action.target, run[0].action.property
        anim = AnimationClipJSON(
            name="_hold",
            duration=max(0.001, end - first),
            channels=[
                ChannelJSON(
                    target=target,
                    property=prop,
                    keyframes=[
                        KeyframeJSON(
                            time=f.start - first, value=f.action.value, easing="step"
                        )
                        for f in run
                    ],
                )
            ],
        )
        placed.append(PlacedClip(clip_from_json(anim), start_time=first))
    for f in tweens:
        target, prop = f.action.target, f.action.property
        anim = _build_anim_for(
            f,
            "_tween",
            vocab=vocab,
            fps=fps,
            step_hz=step_hz,
            default_easing=default_easing,
        )
        placed.append(PlacedClip(clip_from_json(anim), start_time=f.start))
    pose = evaluate_timeline(Timeline(t + 1.0, [Track("", placed)]), t)
    group = write_group(prop)
    # One key of the group survives the evaluation — the most recently written.
    shown = [v for (n, p), v in pose.items() if n == target and write_group(p) == group]
    value = pose.get((target, prop), shown[-1] if shown else None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return base  # a value the compiler refuses later, where it says why
    return float(value)




def _check_swap_action(
    flat: FlatAction,
    *,
    vocab: _SwapVocabulary,
    resolutions: list[AssetResolutionJSON] | None,
) -> bool:
    """Validate one authored action's swap references; decide if it compiles.

    Returns True to keep the action, False to drop it (with a fallback record
    — the usage-aware escalation of an#87: a key the author USES whose art is
    missing is a wrong picture wearing a right one's clothes, so it joins the
    an#33/#76 machinery and turns fatal under ``strict_assets``; an inventory
    gap nobody references stays a non-fatal 'incomplete').

    Raises for the mistakes that are never a stand-in: an undeclared set, an
    undeclared key, a target that cannot carry the set. Transform properties
    pass through untouched — their targets stay runtime-checked, as before.
    """
    action = flat.action
    prop = getattr(action, "property", None)
    if prop is None or prop in _PROPERTY_REST_VALUES:
        return True
    if not isinstance(action, (SetAction, TweenAction)):
        return True
    target = action.target
    entity_id = _track_root_of(target)
    values = (
        [action.value]
        if isinstance(action, SetAction)
        else [v for v in (action.from_value, action.to_value) if v is not None]
    )

    declared_sets = vocab.declared.get(entity_id)
    if declared_sets is None:
        # No descriptor: what the BUILT nodes declare is the vocabulary — the
        # procedural rig's drawn mouth carries its `viseme` set on its visual,
        # exactly as an SVG rig's projections do. Exact key match, like every
        # other set: a lowercase code used to be silently drawn as rest.
        declared_sets = {}
        for path, sets in vocab.node_sets.items():
            if path.split("/", 1)[0] == entity_id:
                for set_name, key_map in sets.items():
                    declared_sets.setdefault(set_name, frozenset())
                    declared_sets[set_name] = declared_sets[set_name] | frozenset(
                        key_map
                    )
        if not declared_sets:
            raise CutoutCompileError(
                f"action targets {target!r}:{prop!r}, which is not a transform "
                f"property, and {entity_id!r} declares no asset sets (no "
                "descriptor, and no built node carries a set). Transform "
                f"properties are: {sorted(TRANSFORM_PROPERTIES)}."
            )

    if prop not in declared_sets:
        raise CutoutCompileError(
            f"action targets {target!r}:{prop!r}, but {entity_id!r}'s "
            f"descriptor declares no asset set named {prop!r} (it has: "
            f"{sorted(declared_sets)}). A property that is not a transform "
            "must name a declared swap set."
        )
    for v in values:
        if not isinstance(v, str) or v not in declared_sets[prop]:
            raise CutoutCompileError(
                f"action sets {target!r}:{prop!r} to {v!r}, which is not a "
                f"declared key of that set (it has: "
                f"{sorted(declared_sets[prop])})."
            )
    if target not in vocab.paths:
        raise CutoutCompileError(
            f"action targets {target!r}, which is not a node in the built "
            f"scene. Known paths: {sorted(vocab.paths)}"
        )

    node_map = vocab.node_sets.get(target, {}).get(prop)
    if node_map is None:
        capable = vocab.swap_capable_paths(entity_id, prop)
        if capable:
            raise CutoutCompileError(
                f"action targets {target!r}:{prop!r}, but the {prop!r} set "
                f"resolves on {capable}, not on that node. Target one of "
                "those paths."
            )
        _record_used_swap_fallback(
            resolutions,
            entity_id,
            target,
            prop,
            detail=(
                f"the {prop!r} set is declared but none of its art resolved, "
                f"so the authored swap on {target!r} cannot be shown; the "
                "channel was dropped"
            ),
        )
        return False
    missing = [str(v) for v in values if str(v) not in node_map]
    if missing:
        _record_used_swap_fallback(
            resolutions,
            entity_id,
            target,
            prop,
            detail=(
                f"the authored swap uses key(s) {missing} of the {prop!r} "
                f"set, whose art did not resolve on {target!r} (resolved "
                f"keys: {sorted(node_map)}); the channel was dropped"
            ),
        )
        return False
    return True


def _check_trim_target(flat: FlatAction, *, vocab: _SwapVocabulary) -> None:
    """``trim_start``/``trim_end`` only on a path node (an#160).

    They are in the numeric vocabulary so that they tween like ``alpha`` —
    which also means the swap checks wave them through, so without this a
    ``trim_end`` on a character would compile and then throw in the browser.
    """
    action = flat.action
    prop = getattr(action, "property", None)
    if prop not in TRIM_PROPERTIES:
        return
    target = action.target
    if (
        prop == "dash_offset"
        and target in vocab.path_nodes
        and prop not in vocab.path_trims.get(target, {})
    ):
        raise CutoutCompileError(
            f"action targets {target!r}:'dash_offset', but the path {target!r} "
            "has no dash pattern, so an offset would draw nothing. Give the "
            "path document a `dash` length (and optionally a `gap`)."
        )
    if target not in vocab.path_nodes:
        raise CutoutCompileError(
            f"action targets {target!r}:{prop!r}, but {prop!r} is a stroked "
            f"path's trim and {target!r} is not a path node. Path nodes in "
            f"this shot: {sorted(vocab.path_nodes) or 'none'} — a path is a "
            "prop whose document kind is 'PathDescriptor'."
        )


def _record_used_swap_fallback(
    resolutions: list[AssetResolutionJSON] | None,
    entity_id: str,
    target: str,
    prop: str,
    *,
    detail: str,
) -> None:
    """A USED swap key with missing art joins the fallback bucket (an#87).

    fallback=True is the load-bearing bit: `_raise_or_warn_on_asset_fallbacks`
    only surfaces fallback entries, so this is what makes the drop audible by
    default and fatal under ``strict_assets`` — where an unreferenced
    inventory gap stays a mute 'incomplete' record, deliberately.
    """
    if resolutions is None:
        return
    resolutions.append(
        AssetResolutionJSON(
            id=entity_id,
            kind="swap",
            store="characters",
            ref=f"{target}:{prop}",
            resolved="dropped",
            fallback=True,
            detail=detail,
        )
    )


def _easing_to_json(spec: Any) -> Any:
    if spec is None:
        return None
    if isinstance(spec, str):
        return spec
    if isinstance(spec, (list, tuple)):
        return list(spec)
    return None


def _track_root_of(target: str) -> str:
    """The first segment of a target path is the track root (the entity name)."""
    return target.split("/", 1)[0] if target else ""


# -----------------------------------------------------------------------------
# Phase 4: dialogue → viseme channels on the speaker's mouth node
# -----------------------------------------------------------------------------












# -----------------------------------------------------------------------------
# Blinks: compiled per eye (an#88) — emitted by the face solver below
# -----------------------------------------------------------------------------






# -----------------------------------------------------------------------------
# The face solver (an#98): one channel per (node, property), summed at compile time
# -----------------------------------------------------------------------------




















# -----------------------------------------------------------------------------
# Phase 7: camera moves wired to root-container scale animation
# -----------------------------------------------------------------------------


# How much each named camera move zooms (final scale relative to start).
#: Which `root` property each `CameraKey` field drives, and the value the key
#: carries when the camera is doing nothing. A channel is emitted ONLY for a
#: property whose keys are not all at rest, which is what keeps `push_in`
#: byte-identical to the document it produced before an#109 — and what makes
#: `pan_left` emit pivots and no scales.
_CAMERA_CHANNELS: tuple[tuple[str, str, float], ...] = (
    ("x", "pivot_x", 0.0),
    ("y", "pivot_y", 0.0),
    ("zoom", "scale_x", 1.0),
    ("zoom", "scale_y", 1.0),
    ("rotation", "rotation", 0.0),
)


def camera_keys(shot: Shot, *, width: int, height: int) -> list[CameraKey]:
    """:func:`an.ir.camera.camera_keys`, with its refusal typed for this adapter.

    The resolver itself lives in the IR layer so `an.ir.validate` can call the
    SAME function — one table, not two reconciled by a test. This wrapper only
    re-raises `CameraError` as a `CutoutCompileError`, which is the compiler's
    own boundary contract: every failure out of `compile_shot` is one type.
    """
    try:
        return _camera_keys(shot, width=width, height=height)
    except CameraError as e:
        raise CutoutCompileError(str(e)) from e


def _add_camera_clips(
    shot: Shot,
    animations: dict[str, AnimationClipJSON],
    tracks: list[TrackJSON],
    *,
    width: int,
    height: int,
) -> None:
    """Emit the shot's camera as channels on the synthetic scene root.

    The root container sits at canvas centre; PixiJS composes
    ``world = position + M·(local − pivot)``, so `root.pivot` IS a 2D camera
    and `root.scale` is its zoom. Both were already applied by the runtime and
    already in ``RUNTIME_APPLIED_PROPERTIES`` before an#109 — which is why a
    translating camera is a COMPILER change with zero runtime change, and is
    therefore checked on every PR rather than only on a labelled one.

    Only properties that actually vary get a channel. That is what keeps the
    five zoom moves byte-identical to the documents they produced before this
    existed, and it is asserted rather than assumed.
    """
    keys = camera_keys(shot, width=width, height=height)
    if len(keys) < 2:
        return  # `hold`, an empty list, or a single pose: nothing to animate
    duration = max(0.001, float(shot.duration))
    # What the author already targeted on `root`. Camera clips are appended
    # LAST and the evaluators are later-wins, so a collision does not error —
    # it silently discards the author's channel. Measured before an#109:
    # `set root scale_x 3.0` together with `camera.move: push_in` evaluated to
    # 1.25 at the shot's end, the authored 3.0 gone, no warning anywhere.
    authored = {
        (channel.target, channel.property)
        for animation in animations.values()
        for channel in animation.channels
    }
    for field, prop, rest in _CAMERA_CHANNELS:
        values = [float(getattr(k, field)) for k in keys]
        if all(v == rest for v in values):
            continue
        if ("root", prop) in authored:
            raise CutoutCompileError(
                f"shot {shot.id!r}: the camera drives `root:{prop}` and an "
                f"action also targets it. Camera clips are appended last and "
                "the evaluators are later-wins, so the authored channel would "
                "be discarded silently — which is why this raises instead. "
                "Move the action to a child node, or express the camera with "
                "`camera.keys` so both live in one place.\n\n"
                "A deliberate divergence from the face solver, which resolves "
                "the same class of collision by warning and letting the author "
                "win: a camera is not a face, and a silently-ignored pan is "
                "worse than a refused compile. Additive folding is the "
                "eventual answer and is not this wave."
            )
        anim_id = f"__camera__{shot.id}_{prop}"
        animations[anim_id] = AnimationClipJSON(
            name=anim_id,
            duration=duration,
            channels=[
                ChannelJSON(
                    target="root",
                    property=prop,
                    keyframes=[
                        KeyframeJSON(time=float(k.at), value=v, easing=k.easing)
                        for k, v in zip(keys, values)
                    ],
                )
            ],
        )
        tracks.append(
            TrackJSON(
                target_root="__camera__",
                clips=[
                    PlacedClipJSON(
                        animation_id=anim_id, start_time=0.0, duration=duration
                    )
                ],
            )
        )
