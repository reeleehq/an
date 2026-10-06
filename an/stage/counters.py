"""A counter, lowered at compile: a number that reads as text (an#342, T2 of an#331).

A counter block is a text block whose document declares ``counter: {format,
start}`` (:class:`an.stage.text.Counter`). In the IR its number is an ordinary
channel, authored as ``tween <id> value a→b`` and ``set <id> value v``; what the
renderer sees is a replacement set (an#341): one ``block_0`` drawing per string
the frames show, swapped by ``set text <key>``. The number never reaches the
runtime, which has no ``value`` case.

The lowering is the stage's ``counters`` compile pass. It runs after every pass
that can contribute a ``value`` action (a genre pass adds them to
``state.extra_actions`` before the ``actions`` pass) and before the ``actions``
pass, whose swap check reads the vocabulary; ``tests/test_text_counter.py``
pins that order against the registry. For each counter block it:

1. compiles the block's ``value`` leaves as one numeric channel with the
   compiler's own clip builder (:func:`an.stage.compile._compile_actions`), so
   easings, ``step_hz``, the set-hold rule and a from-less tween's start are
   exactly those of every other channel;
2. samples that channel on the frame grid ``i / fps`` (a ``step_hz`` shot's
   channel is already stepped, so its grid is honoured by construction);
3. formats each sample (:mod:`an.formats`), typesets every distinct string once
   and rebuilds the block as a ``texts`` set whose rest is the first frame's
   string;
4. replaces each ``value`` leaf by a ``delay`` of the same length (so no
   sequence around it moves) and adds a ``set <id>/block_0 text <key>`` half a
   frame before the first frame showing each new string (the captions' rule,
   so no float disagreement about ``i / fps`` moves a boundary a frame).

A counter with no ``start`` shows its first action's value until then; a
from-less tween with neither a ``start`` nor an earlier ``value`` action, and a
counter with neither a ``start`` nor any ``value`` action, are compile errors
naming both. A shot with no counter block is untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from an.ir.compose import FlatAction, flatten
from an.ir.schema import AssetRef, DelayAction, SetAction, TweenAction

__all__ = ["VALUE_PROPERTY", "COUNTER_KEY_PREFIX", "lower_counters", "counter_blocks"]

#: The block-scoped property a counter's number is authored on. NOT a global
#: authorable property (an#342): a genre's own ``value`` is untouched.
VALUE_PROPERTY: str = "value"

#: What every generated key of a counter's set starts with.
COUNTER_KEY_PREFIX: str = "v_"

#: The property the scratch channel is compiled under: numeric, no rest table
#: entry needed (every from-less tween is given an earlier key first).
_SCRATCH_PROPERTY: str = "x"

#: Where, between two frames, a counter's ``set`` lands: half a frame before the
#: first frame that shows it (:data:`an.captions._SET_OFFSET_FRAMES`).
_SET_OFFSET_FRAMES: float = 0.5

_KEY_UNSAFE = re.compile(r"[^A-Za-z0-9._%,+-]")


@dataclass(frozen=True)
class _CounterBlock:
    entity: AssetRef
    desc: Any  # TextDescriptor
    document: dict


def counter_blocks(shot, props_store) -> dict[str, _CounterBlock]:
    """``{entity id: block}`` for every text block of ``shot`` that declares a
    counter (an unresolvable document is the builder's to report)."""
    from an.stage.text import resolve_text
    from an.stage.text_layout import text_document

    out: dict[str, _CounterBlock] = {}
    if props_store is None:
        return out
    for entity in shot.entities:
        if entity.kind != "prop":
            continue
        document = text_document(entity, props_store)
        if document is None:
            continue
        try:
            desc = resolve_text(document, entity.overrides)
        except ValueError:
            continue
        if desc.counter is not None:
            out[entity.id] = _CounterBlock(entity, desc, dict(document))
    return out


def _counter_of(leaf: Any, blocks: dict[str, _CounterBlock]) -> str | None:
    """The counter id a ``value`` leaf targets (``<id>`` or ``<id>/block_0``)."""
    if getattr(leaf, "property", None) != VALUE_PROPERTY:
        return None
    if not isinstance(leaf, (SetAction, TweenAction)):
        return None
    root, _, rest = leaf.target.partition("/")
    if root in blocks and rest in ("", "block_0"):
        return root
    return None


def _without_value_leaves(action: Any, blocks: dict[str, _CounterBlock]) -> Any:
    """``action`` with every counter ``value`` leaf replaced by a ``delay`` of
    its own length: a set takes no time, a tween its duration, so nothing
    around it moves."""
    if _counter_of(action, blocks) is not None:
        span = action.duration if isinstance(action, TweenAction) else 0.0
        return DelayAction(duration=span)
    children = getattr(action, "children", None)
    if isinstance(children, list) and children:
        return action.model_copy(
            update={"children": [_without_value_leaves(c, blocks) for c in children]}
        )
    return action


def _key_for(string: str, taken: dict[str, str]) -> str:
    """A swap key for ``string``: readable (``v_12``, ``v_Day_7``), never
    ``/`` or ``::``, unique per string."""
    base = COUNTER_KEY_PREFIX + _KEY_UNSAFE.sub("_", string)
    key, n = base, 1
    while key in taken and taken[key] != string:
        n += 1
        key = f"{base}~{n}"
    taken[key] = string
    return key


def _sampled_strings(
    block: _CounterBlock,
    leaves: list[FlatAction],
    *,
    duration: float,
    fps: int,
    step_hz: float | None,
    default_easing: Any,
) -> list[str]:
    """The string each frame ``i / fps`` of the shot shows."""
    from an.frame_clock import frame_count
    from an.ir.compose import delay, sequence
    from an.stage.compile import CutoutCompileError

    eid, counter = block.entity.id, block.desc.counter
    channel = dict(
        duration=duration, fps=fps, step_hz=step_hz, default_easing=default_easing
    )
    leaves = sorted(leaves, key=lambda f: f.start)
    scratch: list = []
    if counter.start is not None:
        scratch.append(
            SetAction(target=eid, property=_SCRATCH_PROPERTY, value=counter.start)
        )
    defined_from: float | None = 0.0 if counter.start is not None else None
    for flat in leaves:
        leaf = flat.action
        values = (
            [leaf.value]
            if isinstance(leaf, SetAction)
            else [v for v in (leaf.from_value, leaf.to_value) if v is not None]
        )
        for v in values:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise CutoutCompileError(
                    f"counter {eid!r}: `value` is a number, got {v!r} "
                    f"({type(v).__name__}) in {leaf.kind} at {flat.start:g} s"
                )
        moved = leaf.model_copy(update={"target": eid, "property": _SCRATCH_PROPERTY})
        if isinstance(leaf, TweenAction) and leaf.from_value is None:
            if defined_from is None or defined_from > flat.start:
                raise CutoutCompileError(
                    f"counter {eid!r}: the `value` tween at {flat.start:g} s has no "
                    "`from`, and nothing gives the counter a value before it: give "
                    "the document's `counter.start`, or a `set` of `value` (or a "
                    "tween with `from`) at or before it"
                )
            # It starts from what the counter shows at its start: `start`, or
            # the actions before it (a `set` at the same instant included).
            at_start = _evaluate(scratch, eid, [flat.start], **channel)[0]
            moved = moved.model_copy(update={"from_value": at_start})
        if defined_from is None:
            defined_from = flat.start
        if isinstance(leaf, SetAction):
            scratch.append(moved.model_copy(update={"at": flat.start}))
        else:
            scratch.append(
                sequence(delay(flat.start), moved) if flat.start > 0 else moved
            )
    if not scratch:
        raise CutoutCompileError(
            f"counter {eid!r} has no value to show: give the document's "
            "`counter.start`, or `set`/`tween` its `value`"
        )
    frames = [i / fps for i in range(frame_count(duration, fps))]
    samples = _evaluate(scratch, eid, frames, **channel)
    # Before its first action (no `start`) a counter shows that action's value.
    defined = [v for v in samples if v is not None]
    if defined:
        first = defined[0]
    else:  # every action lands after the last frame
        leaf = leaves[0].action
        first = float(leaf.value if isinstance(leaf, SetAction) else leaf.from_value)
    return [counter.show(first if v is None else v) for v in samples]


def _evaluate(
    scratch: list,
    eid: str,
    times: list[float],
    *,
    duration: float,
    fps: int,
    step_hz: float | None,
    default_easing: Any,
) -> list[float | None]:
    """The scratch channel's value at each of ``times``, compiled by the
    compiler's own clip builder and read by the kernel's evaluator."""
    from an.stage.compile import _compile_actions
    from an.timing.timeline import evaluate_timeline, timeline_from_compiled

    if not scratch:
        return [None] * len(times)
    animations, tracks = _compile_actions(
        scratch,
        duration,
        vocab=None,
        fps=fps,
        step_hz=step_hz,
        default_easing=default_easing,
    )
    tl = timeline_from_compiled(
        {
            "timeline": {
                "duration": duration,
                "tracks": [t.model_dump() for t in tracks],
            },
            "animations": {k: a.model_dump() for k, a in animations.items()},
        }
    )
    out: list[float | None] = []
    for t in times:
        v = evaluate_timeline(tl, t).get((eid, _SCRATCH_PROPERTY))
        out.append(None if v is None else float(v))
    return out


def lower_counters(state: Any) -> None:
    """The ``counters`` pass (see the module docstring). A no-op for a shot
    with no counter block, which is every shot written before an#342."""
    from an.stage.compile import CutoutCompileError, _apply_stage_placement
    from an.stage.text_layout import build_text_subtree

    shot = state.shot
    props_store = state.mall.get("props") if state.mall else None
    blocks = counter_blocks(shot, props_store)
    if not blocks:
        return
    authored = [*shot.actions, *state.extra_actions]
    by_counter: dict[str, list[FlatAction]] = {eid: [] for eid in blocks}
    for action in authored:
        for flat in flatten(action):
            eid = _counter_of(flat.action, blocks)
            if eid is not None:
                by_counter[eid].append(flat)
    sets: list[SetAction] = []
    for eid, block in blocks.items():
        shown = _sampled_strings(
            block,
            by_counter[eid],
            duration=shot.duration,
            fps=state.fps,
            step_hz=state.step_hz,
            default_easing=state.default_easing,
        )
        taken: dict[str, str] = {}
        keys = [_key_for(s, taken) for s in shown]
        texts = {k: taken[k] for k in dict.fromkeys(keys)}
        document = {**block.document, **dict(block.entity.overrides or {})}
        document.pop("counter", None)
        document.pop("text", None)
        document.update(texts=texts, rest=keys[0], unit="block")
        entity = block.entity.model_copy(update={"overrides": None})
        try:
            node, _, _ = build_text_subtree(
                entity,
                document,
                width=state.width,
                height=state.height,
                base_dir=_font_dir(props_store, block.entity.ref),
                textures=state.textures,
                resolutions=[],
            )
        except ValueError as err:
            raise CutoutCompileError(f"counter {eid!r} cannot be set: {err}") from err
        _apply_stage_placement(node, block.entity)
        _replace_node(state, eid, node)
        for i in range(1, len(keys)):
            if keys[i] != keys[i - 1]:
                sets.append(
                    SetAction(
                        target=f"{eid}/block_0",
                        property="text",
                        value=keys[i],
                        at=(i - _SET_OFFSET_FRAMES) / state.fps,
                    )
                )
    state.shot = shot.model_copy(
        update={"actions": [_without_value_leaves(a, blocks) for a in shot.actions]}
    )
    state.extra_actions[:] = [
        _without_value_leaves(a, blocks) for a in state.extra_actions
    ]
    state.extra_actions.extend(sets)
    _drop_unused_text_textures(state, blocks)
    from an.stage.compile import _rebuild_vocabulary

    _rebuild_vocabulary(state)


def _font_dir(props_store, ref):
    from an.stage.text import font_base_dir

    return font_base_dir(props_store, ref)


def _replace_node(state: Any, eid: str, node: Any) -> None:
    """Put the rebuilt block where the scene pass built the provisional one."""
    for siblings in (state.scene_root.children, state.overlay_children):
        for k, built in enumerate(siblings):
            if built.name == eid:
                siblings[k] = node
                return
    raise AssertionError(f"counter {eid!r}: the scene pass built no node for it")


def _drop_unused_text_textures(state: Any, blocks: dict[str, _CounterBlock]) -> None:
    """The provisional build's texture is not drawn by anything any more."""
    from an.stage.text_layout import TEXT_TEXTURE_PREFIX

    used: set[str] = set()

    def collect(node) -> None:
        v = node.visual
        if v is not None:
            if v.asset_id:
                used.add(v.asset_id)
            for key_map in (v.asset_sets or {}).values():
                used.update(key_map.values())
        for child in node.children:
            collect(child)

    for root in (state.scene_root, *state.overlay_children):
        collect(root)
    for eid in blocks:
        prefix = f"{TEXT_TEXTURE_PREFIX}{eid}."
        for alias in [
            a for a in state.textures if a.startswith(prefix) and a not in used
        ]:
            del state.textures[alias]
