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

__all__ = [
    "ContinuityError",
    "EntityEnd",
    "continue_shots",
    "end_states",
    "opened_channels",
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
#: The plain floor: it holds an item at its own x, on the ground line.
_GROUND: str = "ground"

#: A scene file as continuity keys it (``None``: the scene being resolved).
FileKey = str | None


class ContinuityError(ValueError):
    """A ``continue:`` that cannot be resolved: an unknown shot or scene file,
    a cycle, or a source shot that does not compile. ``shot`` is the shot
    whose ``continue:`` it is: ``an validate`` reports it at that shot's
    ``continue_from``; a render raises it."""

    def __init__(self, message: str, *, shot: str | None = None) -> None:
        super().__init__(message)
        self.shot = shot


def parse_continue(ref: str) -> tuple[FileKey, str]:
    """``(scene file or None, shot id)`` of a ``continue:`` value."""
    file, sep, shot = ref.rpartition(CONTINUE_SEPARATOR)
    if not sep:
        return None, ref.strip()
    if not shot.strip() or not file.strip():
        raise ContinuityError(
            f"continue: {ref!r} names no shot (write `<shot>` or `<scene file>#<shot>`)"
        )
    return Path(file.strip()).as_posix(), shot.strip()


@dataclass
class EntityEnd:
    """One entity as a shot ends: its channels ``{(target, property): value}``
    and what holds it (the hold layer's last holder; ``None`` when no hold
    layer ran)."""

    channels: dict[tuple[str, str], Any] = field(default_factory=dict)
    holder: str | None = None


def end_states(doc: Any, entity_ids: list[str], *, at: float) -> dict[str, EntityEnd]:
    """``{entity id: EntityEnd}`` of a compiled document evaluated at ``at``:
    each entity's own transform (an alias such as ``rotation_rad`` folded into
    the property it writes), then every animated channel of its nodes, one
    per write group."""
    from an.stage.timeline import (
        _node_chain,
        _pose_for,
        evaluate_timeline,
        timeline_from_scene,
        transform_of,
        write_group,
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
        name = path.rsplit("/", 1)[-1]
        folded = {
            (name, write_group(prop)): value
            for (_, prop), value in own.items()
            if write_group(prop) in ROOT_TRANSFORM and isinstance(value, (int, float))
        }
        t = transform_of(node, {**own, **folded})
        channels: dict[tuple[str, str], Any] = {
            (eid, prop): float(getattr(t, prop)) for prop in ROOT_TRANSFORM
        }
        channels[(eid, "alpha")] = float(own.get((name, "alpha"), node.transform.alpha))
        groups = {(eid, write_group(p)) for _, p in channels}
        for (target, prop), value in pose.items():
            if prop in UNCARRIED_PROPERTIES:
                continue
            if target != path and not target.startswith(path + "/"):
                continue
            key = (eid + target[len(path) :], prop)
            group = (key[0], write_group(prop))
            if group in groups and key not in channels:
                continue  # an alias of a channel already carried
            channels[key] = value
            groups.add(group)
        timeline = holders.get(eid)
        out[eid] = EntityEnd(channels, timeline[-1][1] if timeline else None)
    return out


def opened_channels(shot: Shot, *, fps: float) -> set[tuple[str, str]]:
    """``(target, write group)`` the shot itself gives a value in its first
    frame: a ``set``, or a ``tween`` with a ``from``. A tween from where the
    entity is (no ``from``) starts from the carried value, so it opens nothing."""
    from an.ir.compose import flatten, parallel
    from an.stage.timeline import write_group

    first = 1.0 / float(fps)
    return {
        (f.action.target, write_group(f.action.property))
        for f in flatten(parallel(*shot.actions))
        if f.start < first
        and (
            isinstance(f.action, SetAction)
            or (isinstance(f.action, TweenAction) and f.action.from_value is not None)
        )
    }


def _carried(
    shot: Shot,
    ends: Mapping[str, EntityEnd],
    *,
    fps: float,
    placed_by_world: frozenset[str] = frozenset(),
) -> Shot:
    """``shot`` opening as ``ends`` (the shared entities' end states).

    ``placed_by_world``: entities the world places in THIS shot under another
    viewpoint than the source's, whose screen placement is not carried (a cut
    between two framings is a cut; the world places them). A cut from a
    hand-placed shot to a framed one carries the screen placement, as
    ``cut_continuity`` reads such a cut: the author placed the source."""
    from an.stage.hold import (
        AIM_OVERRIDE,
        ON_OVERRIDE,
        _is_place_target,
        _is_surface_target,
    )
    from an.stage.timeline import write_group

    opened = opened_channels(shot, fps=fps)
    present = {e.id for e in shot.entities}
    sets: list[SetAction] = []
    entities = []
    for entity in shot.entities:
        end = ends.get(entity.id)
        if end is None:
            entities.append(entity)
            continue
        overrides = dict(entity.overrides or {})
        skip: set[str] = set(ROOT_TRANSFORM) if entity.id in placed_by_world else set()
        holder = end.holder
        if (
            holder is not None
            and holder not in _UNHELD
            and ON_OVERRIDE not in overrides
        ):
            if holder == _GROUND:
                overrides[ON_OVERRIDE] = holder
                skip.add("y")  # the floor sets its height; it keeps its x
            elif _is_place_target(holder) or (
                _is_surface_target(holder) and _body(holder) in present
            ):
                overrides[ON_OVERRIDE] = holder
                skip |= {"x", "y"}  # the place puts it there
            elif _is_surface_target(holder):
                pass  # its body is not in this shot: the item stays where it was
            elif _body(holder) in present:
                overrides[ON_OVERRIDE] = holder  # the same hand holds it
                overrides.setdefault(
                    AIM_OVERRIDE, end.channels[(entity.id, "rotation")]
                )
                skip |= set(ROOT_TRANSFORM)  # the hand places it, aimed
            # a holder this shot does not have: the item stays where it was
        for (target, prop), value in end.channels.items():
            if (target, write_group(prop)) in opened:
                continue  # the shot's own opening wins
            if target == entity.id and prop in skip:
                continue
            sets.append(SetAction(target=target, property=prop, value=value, at=0.0))
        entities.append(entity.model_copy(update={"overrides": overrides or None}))
    return shot.model_copy(
        update={"entities": entities, "actions": [*sets, *shot.actions]}
    )


def _body(holder: str) -> str:
    """The entity a holder names (``napoleon@hand_r``, ``crate/lid@surface``)."""
    return holder.partition("@")[0].split("/")[0]


def continue_shots(
    scene: SceneIR,
    mall: Mapping[str, Any] | None,
    *,
    fps: float | None = None,
    project_dir: str | Path | None = None,
    read_scene: Callable[[Path, str], SceneIR] | None = None,
    lower_world: Callable[..., SceneIR] | None = None,
    compile_shot: Callable[..., Any] | None = None,
) -> SceneIR:
    """``scene`` (already world-lowered) with every ``continue:`` resolved.

    ``project_dir`` is where a sibling scene file is read from (default: the
    mall's ``scenes`` store's :attr:`~an.stores.scenes.ScenesStore.project_dir`).
    The seams: ``read_scene`` (:func:`an.ir.sync.read_scene`), ``lower_world``
    (``(scene, mall, *, fps) -> scene``, :func:`an.stage.world.lower_scene_world`)
    and ``compile_shot`` (:func:`an.stage.compile.compile_shot`). Each source
    is resolved once, and only the shots a continuation needs are: a sibling
    file's other shots are not compiled. A scene without ``continue:`` comes
    back as it is.
    """
    if not any(s.continue_from for s in scene.timeline):
        return scene
    from an.ir.schema import resolve_step_hz
    from an.ir.sync import read_scene as _read
    from an.ir.world import viewpoint_key
    from an.stage.compile import compile_shot as _compile
    from an.stage.compile import style_pack_for
    from an.stage.world import lower_scene_world

    read_scene = read_scene or _read
    compile_shot = compile_shot or _compile
    lower_world = lower_world or lower_scene_world
    rate = float(fps if fps is not None else scene.meta.fps)
    root = project_dir if project_dir is not None else _project_dir(mall)
    scenes: dict[FileKey, SceneIR] = {None: scene}
    done: dict[tuple[FileKey, int], Shot] = {}
    compiled: dict[tuple[FileKey, int], Any] = {}  # each source compiled once

    def load(file: FileKey, *, asked_by: str) -> SceneIR:
        if file in scenes:
            return scenes[file]
        if root is None:
            raise ContinuityError(
                f"shot {asked_by!r} continues a shot of {file!r}, a sibling scene "
                "file, and no project folder is known",
                shot=asked_by,
            )
        try:
            other = read_scene(Path(root), file)
        except Exception as e:  # noqa: BLE001 — named, not swallowed
            raise ContinuityError(
                f"shot {asked_by!r}: scene file {file!r} cannot be read ({e})",
                shot=asked_by,
            ) from e
        scenes[file] = lower_world(other, mall, fps=rate)
        return scenes[file]

    def where(file: FileKey) -> str:
        return "this scene" if file is None else repr(file)

    def resolved(file: FileKey, index: int, stack: tuple) -> Shot:
        key = (file, index)
        if key in done:
            return done[key]
        owner = load(file, asked_by="?")
        shot = owner.timeline[index]
        if key in stack:
            chain = " -> ".join(
                f"{f or ''}{CONTINUE_SEPARATOR}{scenes[f].timeline[i].id}"
                for f, i in (*stack, key)
            )
            raise ContinuityError(
                f"shot {shot.id!r}: `continue:` closes a cycle ({chain})", shot=shot.id
            )
        if shot.continue_from:
            shot = carried(file, index, shot, (*stack, key))
        done[key] = shot
        return shot

    def carried(file: FileKey, index: int, shot: Shot, stack: tuple) -> Shot:
        src_file, sid = parse_continue(shot.continue_from)
        src_file = file if src_file is None else src_file
        owner = load(src_file, asked_by=shot.id)
        j = next((k for k, s in enumerate(owner.timeline) if s.id == sid), None)
        if j is None:
            raise ContinuityError(
                f"shot {shot.id!r}: `continue: {shot.continue_from}` names no shot "
                f"of {where(src_file)} (its shots: {[s.id for s in owner.timeline]})",
                shot=shot.id,
            )
        source = resolved(src_file, j, stack)
        shared = [
            e.id for e in shot.entities if e.id in {s.id for s in source.entities}
        ]
        if (src_file, j) not in compiled:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")  # the source's compile reports them
                    compiled[(src_file, j)] = compile_shot(
                        source,
                        mall=mall,
                        fps=rate,
                        width=int(owner.meta.resolution.width),
                        height=int(owner.meta.resolution.height),
                        default_easing=owner.meta.default_easing,
                        # as the render compiles it, so the end is its last frame
                        step_hz=resolve_step_hz(source, owner.meta.step_hz),
                        style_pack=style_pack_for(
                            owner.meta, (mall or {}).get("styles") or {}
                        ),
                    )
            except Exception as e:  # noqa: BLE001 — the source's own error, named here
                raise ContinuityError(
                    f"shot {shot.id!r} continues {source.id!r} of {where(src_file)}, "
                    f"which does not compile ({e})",
                    shot=shot.id,
                ) from e
        doc = compiled[(src_file, j)]
        world = scenes[file].world
        members = {m.id for m in world.members} if world is not None else set()
        across = (
            shot.viewpoint is not None
            and source.viewpoint is not None
            and viewpoint_key(shot) != viewpoint_key(source)
        )
        return _carried(
            shot,
            end_states(doc, shared, at=float(source.duration)),
            fps=rate,
            placed_by_world=frozenset(members if across else ()),
        )

    timeline = [
        resolved(None, i, ()) if s.continue_from else s
        for i, s in enumerate(scene.timeline)
    ]
    return scene.model_copy(update={"timeline": timeline})


def _project_dir(mall: Mapping[str, Any] | None) -> Path | None:
    """The project folder a mall was built over, from its ``scenes`` store."""
    root = getattr((mall or {}).get("scenes"), "project_dir", None)
    return Path(root) if root is not None else None
