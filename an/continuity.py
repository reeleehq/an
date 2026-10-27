"""Open a shot from another shot's end state (an#542).

A scene that picks up where another left off (the third scene opens on the
last frame of the bedtime scene; back to the studio as the studio scene left
it) used to rebuild that opening by hand: one ``set`` at 0 per lamp veil,
pillow head, robe and aimed musket, each read by eye off the other scene's
actions, and a wrong value was a pop at the cut that nothing checked. A shot
now says where it continues from::

    continue: studio                   # a shot of this scene
    continue: scene.studio.md#studio   # a shot of a sibling scene file

and every entity it shares with that shot (by id) opens at that shot's final
EVALUATED state: the entity's transform, every channel of its nodes (rotation,
swap keys, alpha, tint), and what holds it (a hand: ``held_by`` and
``held_rotation``; the ground: ``held_by: ground``). The shot's own opening
``set`` or ``tween`` of a channel wins over the carried one.

:func:`continue_shots` resolves it before compile, as part of the scene the
compiler sees (:func:`an.stage.world.lower_scene`): the source shot is
compiled (itself lowered and continued first), evaluated at its end by the
runtime's executable spec, and its state written into the continuing shot as
``set`` actions at 0 and hold overrides. The source can be a later shot, or
another scene's; a cycle is refused (:class:`ContinuityError`).

>>> parse_continue("scene.studio.md#studio"), parse_continue("studio")
(('scene.studio.md', 'studio'), (None, 'studio'))
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.ir.schema import SceneIR, SetAction, Shot, TweenAction
from an.ir.world import WorldError

__all__ = [
    "ContinuityError",
    "EntityEnd",
    "continue_shots",
    "end_states",
    "parse_continue",
]

#: What separates a sibling scene file from a shot id in ``continue:``.
CONTINUE_SEPARATOR: str = "#"
#: Transform fields read off an entity's own node: where it stands.
ROOT_TRANSFORM: tuple[str, ...] = ("x", "y", "rotation", "scale_x", "scale_y")
#: Channels never carried across a cut: draw order the hold layer derives each
#: shot, and the mouth, which the new shot's own dialogue drives.
UNCARRIED_PROPERTIES: frozenset[str] = frozenset({"paint_after", "viseme"})
#: Holders that leave an item where it lies, carried as its transform.
_UNHELD: frozenset[str] = frozenset({"staged", "air"})


class ContinuityError(WorldError):
    """A ``continue:`` that cannot be resolved: an unknown shot or scene file,
    a cycle, or a source shot that does not compile. A :class:`WorldError`, so
    it is reported where the scene the compiler sees is (``an validate``)."""


def parse_continue(ref: str) -> tuple[str | None, str]:
    """``(scene file or None, shot id)`` of a ``continue:`` value."""
    file, sep, shot = ref.rpartition(CONTINUE_SEPARATOR)
    if not sep:
        return None, ref.strip()
    if not shot.strip() or not file.strip():
        raise ContinuityError(
            f"continue: {ref!r} names no shot (write `<shot>` or `<scene file>#<shot>`)"
        )
    return file.strip(), shot.strip()


@dataclass
class EntityEnd:
    """One entity as a shot ends: its channels ``{(target, property): value}``
    and what holds it (the hold layer's last holder; ``None`` when no hold
    layer ran)."""

    channels: dict[tuple[str, str], Any] = field(default_factory=dict)
    holder: str | None = None


def end_states(doc: Any, entity_ids: list[str], *, at: float) -> dict[str, EntityEnd]:
    """``{entity id: EntityEnd}`` of a compiled document evaluated at ``at``:
    each entity's own transform, then every animated channel of its nodes."""
    from an.stage.timeline import (
        _node_chain,
        _pose_for,
        evaluate_timeline,
        timeline_from_scene,
        transform_of,
    )

    pose = evaluate_timeline(timeline_from_scene(doc), at)
    holders = (((doc.meta.extensions or {}).get("solve") or {}).get("holds") or {}).get(
        "holders"
    ) or {}
    out: dict[str, EntityEnd] = {}
    for eid in entity_ids:
        try:
            node, path = _node_chain(doc.scene, eid)[-1]
        except Exception:  # noqa: BLE001 — not drawn (a voice): nothing to carry
            continue
        own = _pose_for(pose, path) or {}
        t = transform_of(node, own)
        channels = {(eid, prop): float(getattr(t, prop)) for prop in ROOT_TRANSFORM}
        channels[(eid, "alpha")] = float(
            own.get((path.rsplit("/", 1)[-1], "alpha"), node.transform.alpha)
        )
        for (target, prop), value in pose.items():
            if prop in UNCARRIED_PROPERTIES:
                continue
            if target == path or target.startswith(path + "/"):
                channels[(eid + target[len(path) :], prop)] = value
        timeline = holders.get(eid)
        out[eid] = EntityEnd(channels, timeline[-1][1] if timeline else None)
    return out


def _opened(shot: Shot, *, fps: float) -> set[tuple[str, str]]:
    """``(target, property)`` the shot sets or tweens in its first frame."""
    from an.ir.compose import flatten, parallel

    first = 1.0 / float(fps)
    return {
        (f.action.target, f.action.property)
        for f in flatten(parallel(*shot.actions))
        if isinstance(f.action, (SetAction, TweenAction)) and f.start < first
    }


def _carried(shot: Shot, ends: Mapping[str, EntityEnd], *, fps: float) -> Shot:
    """``shot`` opening as ``ends`` (the shared entities' end states)."""
    from an.stage.hold import AIM_OVERRIDE, ON_OVERRIDE

    opened = _opened(shot, fps=fps)
    sets: list[SetAction] = []
    entities = []
    for entity in shot.entities:
        end = ends.get(entity.id)
        if end is None:
            entities.append(entity)
            continue
        overrides = dict(entity.overrides or {})
        held = end.holder is not None and end.holder not in _UNHELD
        in_hand = held and not end.holder.startswith("ground")
        if held and ON_OVERRIDE not in overrides:
            overrides[ON_OVERRIDE] = "ground" if not in_hand else end.holder
            if in_hand and AIM_OVERRIDE not in overrides:
                overrides[AIM_OVERRIDE] = end.channels[(entity.id, "rotation")]
        for (target, prop), value in end.channels.items():
            if (target, prop) in opened:
                continue  # the shot's own opening wins
            if in_hand and target == entity.id and prop in ROOT_TRANSFORM:
                continue  # the hand places it, aimed by `held_rotation`
            sets.append(SetAction(target=target, property=prop, value=value, at=0.0))
        entities.append(entity.model_copy(update={"overrides": overrides or None}))
    return shot.model_copy(
        update={"entities": entities, "actions": [*sets, *shot.actions]}
    )


def continue_shots(
    scene: SceneIR,
    mall: Mapping[str, Any] | None,
    *,
    fps: float | None = None,
    project_dir: str | Path | None = None,
    read_scene: Callable[[Path, str], SceneIR] | None = None,
    compile_shot: Callable[..., Any] | None = None,
    stack: tuple[tuple[str | None, str], ...] = (),
) -> SceneIR:
    """``scene`` with every ``continue:`` resolved (see the module docstring).

    ``project_dir`` is where a sibling scene file is read from (default: the
    mall's ``scenes`` store root); ``read_scene`` and ``compile_shot`` are the
    loader and compiler (:func:`an.ir.sync.read_scene`,
    :func:`an.stage.compile.compile_shot`); ``stack`` the ``(file, shot)``
    sources being resolved above this call, for the cycle check. A scene
    without ``continue:`` comes back as it is.
    """
    if not any(s.continue_from for s in scene.timeline):
        return scene
    from an.ir.sync import read_scene as _read
    from an.stage.compile import compile_shot as _compile

    read_scene = read_scene or _read
    compile_shot = compile_shot or _compile
    rate = float(fps if fps is not None else scene.meta.fps)
    root = project_dir if project_dir is not None else _project_dir(mall)
    timeline = list(scene.timeline)
    resolved: set[int] = set()

    def source_of(index: int, stack: tuple) -> tuple[Shot, SceneIR]:
        shot = timeline[index]
        file, sid = parse_continue(shot.continue_from)
        key = (file, sid)
        if key in stack:
            chain = " -> ".join(
                f"{f or ''}{CONTINUE_SEPARATOR}{s}" for f, s in (*stack, key)
            )
            raise ContinuityError(
                f"shot {shot.id!r}: `continue: {shot.continue_from}` closes a cycle ({chain})"
            )
        if file is None:
            j = next((k for k, s in enumerate(timeline) if s.id == sid), None)
            if j is None or j == index:
                raise ContinuityError(
                    f"shot {shot.id!r}: `continue: {sid}` names no other shot of this "
                    f"scene (its shots: {[s.id for s in timeline]})"
                )
            if timeline[j].continue_from and j not in resolved:
                resolve(j, (*stack, key))
            return timeline[j], scene
        if root is None:
            raise ContinuityError(
                f"shot {shot.id!r}: `continue: {file}{CONTINUE_SEPARATOR}{sid}` reads "
                "a sibling scene file, and no project folder is known"
            )
        try:
            other = read_scene(Path(root), file)
        except Exception as e:  # noqa: BLE001 — named, not swallowed
            raise ContinuityError(
                f"shot {shot.id!r}: scene file {file!r} cannot be read ({e})"
            ) from e
        from an.stage.world import lower_scene

        other = lower_scene(other, mall, fps=rate, continue_stack=(*stack, key)).scene
        match = next((s for s in other.timeline if s.id == sid), None)
        if match is None:
            raise ContinuityError(
                f"shot {shot.id!r}: {file!r} has no shot {sid!r} "
                f"(its shots: {[s.id for s in other.timeline]})"
            )
        return match, other

    def resolve(index: int, stack: tuple) -> None:
        shot = timeline[index]
        source, owner = source_of(index, stack)
        shared = [
            e.id for e in shot.entities if e.id in {s.id for s in source.entities}
        ]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # the source's own compile reports them
                doc = compile_shot(
                    source,
                    mall=mall,
                    fps=rate,
                    width=int(owner.meta.resolution.width),
                    height=int(owner.meta.resolution.height),
                    default_easing=owner.meta.default_easing,
                )
        except Exception as e:  # noqa: BLE001 — the source's own error, named here
            raise ContinuityError(
                f"shot {shot.id!r} continues {source.id!r}, which does not compile ({e})"
            ) from e
        ends = end_states(doc, shared, at=float(source.duration))
        timeline[index] = _carried(shot, ends, fps=rate)
        resolved.add(index)

    for i, shot in enumerate(timeline):
        if shot.continue_from and i not in resolved:
            resolve(i, stack)
    return scene.model_copy(update={"timeline": timeline})


def _project_dir(mall: Mapping[str, Any] | None) -> Path | None:
    """The project folder a mall was built over: its ``scenes`` store's root."""
    root = getattr((mall or {}).get("scenes"), "_root", None)
    return Path(root) if root is not None else None
