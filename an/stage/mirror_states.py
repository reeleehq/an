"""Mirror states (an#819): the drawing art uses when it is drawn mirrored.

A carried item mirrors with its carrier (the hold layer composes the hand's
transform, mirror included), which is right for the handle and wrong for
lettering: a "BEST DAD EVER!" mug carried by a character turned to face right
reads backwards. Art says which drawing to use when it is drawn mirrored, per
key of a swap set, in its store document's ``metadata``::

    metadata:
      mirror_states: {best_dad: best_dad_mirror}
      lettering: true

and the stage swaps to it wherever the drawing's net x scale on the set is
negative (its own, every parent's: held, placed, fallen, or mirrored by hand),
so lettering always reads. The ``mirror_states`` compile pass (after the solve
and the topple, before the camera) samples the compiled document on the
render's grid (:func:`an.frame_clock.camera_grid`) and writes one stepped swap
channel per drawing that is ever mirrored with a mapped key; a shot where none
is leaves the document byte for byte as it was. The ``lettering`` check warns
about art declaring ``lettering: true`` drawn mirrored with a drawing that has
no mirror state.

A key maps to a key of the SAME swap set (its mirror drawing is one of the
set's states). The mirror is read before the camera, as the ``light`` check
reads a shaded side.

>>> mirror_states_of({"metadata": {"mirror_states": {"best_dad": "best_dad_mirror"}}})
{'best_dad': 'best_dad_mirror'}
>>> mirror_states_of({"metadata": {}}), mirror_states_of(None)
({}, {})
>>> is_mirrored((-1.0, 0.0, 0.0, 1.0, 0.0, 0.0)), is_mirrored((-1.0, 0.0, 0.0, -1.0, 0.0, 0.0))
(True, False)
"""

from __future__ import annotations

import warnings
from collections.abc import Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: The art-metadata key naming each swap-set key's mirror drawing.
MIRROR_STATES_KEY: str = "mirror_states"
#: The art-metadata key saying the art carries lettering (it must not read mirrored).
LETTERING_KEY: str = "lettering"
#: Where the art's declarations live in its store document.
ART_METADATA_KEY: str = "metadata"
#: The compile pass's order: after ``solve`` (525) and ``topple`` (535), which
#: mirror what they carry or tip, before the camera passes (550+).
MIRROR_STATES_ORDER: int = 540
#: The track the pass's channels are placed on: last at the time it runs, so
#: its channel wins over the authored swaps it already accounts for.
MIRROR_TRACK: str = "__mirror__"


class MirrorStatesError(ValueError):
    """Art declares ``mirror_states`` that do not read."""


class MirrorStatesWarning(UserWarning):
    """A drawing with a mirror state that the stage cannot swap (said, not raised)."""


def art_metadata(document: Any) -> Mapping[str, Any]:
    """The ``metadata`` of an art store document (``{}`` when it has none)."""
    meta = (
        document.get(ART_METADATA_KEY)
        if isinstance(document, Mapping)
        else getattr(document, ART_METADATA_KEY, None)
    )
    return meta if isinstance(meta, Mapping) else {}


def mirror_states_of(document: Any) -> dict[str, str]:
    """``{key: its mirror key}`` the art declares (``{}`` for none); a
    declaration that is not a mapping of names to names raises."""
    raw = art_metadata(document).get(MIRROR_STATES_KEY)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping) or not all(
        isinstance(k, str) and isinstance(v, str) and k and v for k, v in raw.items()
    ):
        raise MirrorStatesError(
            f"`metadata.{MIRROR_STATES_KEY}` maps a swap-set key to the key of its "
            f"mirror drawing, as names (`{{best_dad: best_dad_mirror}}`); got {raw!r}"
        )
    return dict(raw)


def declares_lettering(document: Any) -> bool:
    """Whether the art says it carries lettering (``metadata.lettering: true``)."""
    return art_metadata(document).get(LETTERING_KEY) is True


def is_mirrored(matrix: Sequence[float]) -> bool:
    """Whether an affine ``(a, b, c, d, x, y)`` flips handedness (its net x scale
    is negative, whatever the rotation): its determinant is negative."""
    a, b, c, d = matrix[:4]
    return a * d - b * c < 0


@dataclass(frozen=True)
class DrawingState:
    """What one drawing of an entity shows at one instant."""

    t: float
    path: str  # the drawing's node
    swap_set: str | None  # ``None``: a drawing outside any swap set (or none)
    key: str | None
    mirrored: bool
    #: More than one of its swap sets written at this instant: which one shows
    #: is the runtime's write-group call, so nothing is swapped on it.
    ambiguous: bool = False


def _drawings(
    root: Any, entity_id: str, *, swap_sets_only: bool
) -> list[tuple[str, Any]]:
    from an.stage.tree import walk_children

    prefix = entity_id + "/"
    return [
        (path, node)
        for path, node in walk_children(root)
        if (path == entity_id or path.startswith(prefix))
        and node.visual is not None
        and (node.visual.asset_sets or not swap_sets_only)
    ]


def _rest(visual: Any) -> tuple[str | None, str | None]:
    """The (set, key) whose drawing the node is built with."""
    for name, keys in (visual.asset_sets or {}).items():
        for key, asset in keys.items():
            if asset == visual.asset_id:
                return name, key
    return None, None


def applicable_pairs(
    states: Mapping[str, str], keys: Collection[str]
) -> dict[str, str]:
    """The pairs of ``states`` one swap set can show: both the key and its mirror
    key are among the set's ``keys`` (a set projected onto a slot holds only the
    keys that slot's drawings resolve, so another slot may hold one and not the
    other).

    >>> applicable_pairs({"plain": "flipped", "x": "y"}, {"plain", "flipped", "x"})
    {'plain': 'flipped'}
    """
    return {k: v for k, v in states.items() if k in keys and v in keys}


def drawing_states(
    doc: Any, entity_id: str, times: Sequence[float], *, swap_sets_only: bool = True
) -> Iterator[DrawingState]:
    """Each drawing of ``entity_id`` in the compiled (or assembled) document
    ``doc`` at each of ``times``: the swap set and key in force (the timeline's,
    else the drawing it is built with) and whether it is drawn mirrored on the
    set (before the camera). ``swap_sets_only=False`` includes the drawings
    with no swap set (their set and key are ``None``)."""
    from an.stage.solve import _node_index, _world_matrices
    from an.stage.timeline import timeline_from_scene
    from an.timing.timeline import cut_timeline, evaluate_timeline

    drawings = _drawings(doc.scene, entity_id, swap_sets_only=swap_sets_only)
    if not drawings:
        return
    nodes = _node_index(doc)
    paths = [p for p, _ in drawings]

    def on_a_chain(target: str, _prop: str) -> bool:  # a drawing, or a node holding one
        return any(p == target or p.startswith(target + "/") for p in paths)

    timeline = cut_timeline(timeline_from_scene(doc), where=on_a_chain)
    for t in times:
        pose = evaluate_timeline(timeline, t)
        world = _world_matrices(doc, paths, pose, nodes)
        for path, node in drawings:
            sets = node.visual.asset_sets or {}
            written = [(s, pose[(path, s)]) for s in sets if (path, s) in pose]
            swap_set, key = written[0] if len(written) == 1 else _rest(node.visual)
            yield DrawingState(
                t, path, swap_set, key, is_mirrored(world[path]), len(written) > 1
            )


def mirror_channels(
    doc: Any,
    entity_id: str,
    states: Mapping[str, str],
    times: Sequence[float],
    *,
    shot_id: str = "",
) -> dict[tuple[str, str], list[tuple[float, str]]]:
    """``{(node path, swap set): [(t, key), ...]}``: for each drawing of
    ``entity_id`` that is ever mirrored showing a key with a mirror state its
    set can show (:func:`applicable_pairs`), its key at each change of
    ``times``, the mirror key wherever it is drawn mirrored. Empty when nothing
    needs to change. A mirror key no swap set of the entity holds raises: the
    declaration names a drawing that does not exist."""
    from an.stage.solve import _node_index

    nodes = _node_index(doc)
    held = {
        k
        for path, _ in _drawings(doc.scene, entity_id, swap_sets_only=True)
        for keys in nodes[path].visual.asset_sets.values()
        for k in keys
    }
    missing = sorted({v for k, v in states.items() if k in held and v not in held})
    if missing:
        raise MirrorStatesError(
            f"shot {shot_id!r}: {entity_id!r} declares mirror state(s) {missing} that "
            f"none of its swap sets has (their keys: {sorted(held)}); a mirror "
            "drawing is a key of the same set as the key it mirrors"
        )
    by_drawing: dict[str, list[DrawingState]] = {}
    for s in drawing_states(doc, entity_id, times):
        by_drawing.setdefault(s.path, []).append(s)
    out: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for path, seq in by_drawing.items():
        sets = nodes[path].visual.asset_sets
        pairs = {name: applicable_pairs(states, keys) for name, keys in sets.items()}
        if not any(s.mirrored and s.key in pairs.get(s.swap_set, {}) for s in seq):
            continue
        used = {s.swap_set for s in seq}
        if len(used) != 1 or None in used or any(s.ambiguous for s in seq):
            warnings.warn(
                f"shot {shot_id!r}: {path!r} is drawn mirrored with a key that has a "
                "mirror state, but it shows several swap sets (or a drawing outside "
                "them) in this shot; its mirror state is not applied (one set per "
                "drawing is)",
                MirrorStatesWarning,
                stacklevel=2,
            )
            continue
        (swap_set,) = used
        mapped = pairs[swap_set]
        values = [mapped.get(s.key, s.key) if s.mirrored else s.key for s in seq]
        out[(path, swap_set)] = [
            (s.t, v)
            for i, (s, v) in enumerate(zip(seq, values))
            if i == 0 or v != values[i - 1]
        ]
    return out


def mirror_channel_targets(doc: Any) -> set[tuple[str, str]]:
    """The ``(node path, swap set)`` pairs the ``mirror_states`` pass wrote a
    channel for in the compiled ``doc``."""
    return {
        (c.target, c.property)
        for name, clip in doc.animations.items()
        if name.startswith(MIRROR_TRACK)
        for c in clip.channels
    }


def mirror_states_pass(state: Any) -> None:
    """The ``mirror_states`` compile pass (order :data:`MIRROR_STATES_ORDER`):
    see the module docstring. A no-op for a shot whose entities' art declares
    no mirror state."""
    from an.frame_clock import camera_grid
    from an.stage.compile import (
        AnimationClipJSON,
        ChannelJSON,
        KeyframeJSON,
        PlacedClipJSON,
        TrackJSON,
        _assemble_document,
        _fresh_clip_id,
    )
    from an.stage.solve import _descriptor

    declared = [
        (e.id, states)
        for e in state.shot.entities
        if e.store and (states := mirror_states_of(_descriptor(e, state.mall)))
    ]
    if not declared:
        return
    duration = max(0.001, float(state.shot.duration))
    times = camera_grid(
        duration,
        fps=state.fps,
        step_hz=state.step_hz,
        frame_samples=state.frame_samples,
        sample_fps=state.sample_fps,
    ).times
    doc = _assemble_document(state, background="#000000")
    channels = [
        ChannelJSON(
            target=path,
            property=swap_set,
            keyframes=[KeyframeJSON(time=t, value=v, easing="step") for t, v in keys],
        )
        for entity_id, states in declared
        for (path, swap_set), keys in mirror_channels(
            doc, entity_id, states, times, shot_id=state.shot.id
        ).items()
    ]
    if not channels:
        return
    anim_id = _fresh_clip_id(f"{MIRROR_TRACK}{state.shot.id}", state.animations)
    state.animations[anim_id] = AnimationClipJSON(
        name=anim_id, duration=duration, channels=channels
    )
    state.tracks.append(
        TrackJSON(
            target_root=MIRROR_TRACK,
            clips=[
                PlacedClipJSON(animation_id=anim_id, start_time=0.0, duration=duration)
            ],
        )
    )
