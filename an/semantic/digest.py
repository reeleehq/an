"""Which vocabulary entries a shot names, at which versions: the shot's vocabulary digest.

ADR 0003 decision 2: the versions of the entries a shot uses are folded into
that shot's compile key (ADR 0004), so changing what a name means re-renders
the shots that say it — visibly, never silently. :func:`vocabulary_versions`
walks a shot and collects ``{entry id: version}``; :func:`vocabulary_digest`
hashes it.

**Hook.** The content-keyed shot cache (P6, an#242) adds key parts through
``an.build.keys.register_shot_key_part(renderer, name, fn)``; this digest is
the ``vocabulary`` part, registered by :func:`register_vocabulary_key_part`
once that seam exists (it is a no-op returning ``False`` until then).

Over-inclusion is deliberate and safe: a ``play`` of a name that is a motion
preset counts the preset even if the character's descriptor shadows it, and a
preset that resolves an aspect counts every method of that aspect — a version
bump then re-renders a shot that may not have needed it, never the reverse.

>>> from an.ir.schema import Shot, Camera
>>> v = vocabulary_versions(Shot(id="s", camera=Camera(move="push_in")))
>>> v["camera.push_in"]
'1'
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from an.semantic.registry import entries, lookup, methods_of

__all__ = [
    "VOCABULARY_KEY_PART",
    "register_vocabulary_key_part",
    "vocabulary_digest",
    "vocabulary_versions",
]

#: The name of the shot-key part this digest is folded in under.
VOCABULARY_KEY_PART: str = "vocabulary"


def _walk_actions(actions) -> Iterator[Any]:
    for a in actions or ():
        yield a
        for name in ("children",):
            yield from _walk_actions(getattr(a, name, None) or ())
        child = getattr(a, "child", None)
        if child is not None:
            yield from _walk_actions([child])


def _names(shot) -> Iterator[tuple[str, str]]:
    """``(kind, name)`` of every vocabulary name the shot spells."""
    for ent in shot.entities or ():
        yield "entity", ent.kind
    camera = getattr(shot, "camera", None)
    if camera is not None and getattr(camera, "move", None):
        yield "camera_move", camera.move
    for key in getattr(camera, "keys", None) or ():
        if isinstance(getattr(key, "easing", None), str):
            yield "easing", key.easing
    for a in _walk_actions(shot.actions):
        yield "action", a.kind
        easing = getattr(a, "easing", None)
        if isinstance(easing, str):
            yield "easing", easing
        animation = getattr(a, "animation", None)
        if isinstance(animation, str):
            yield "motion_preset", animation
        preset = getattr(a, "preset", None)
        if isinstance(preset, str):
            yield "expression_preset", preset
    if shot.dialogue:
        yield "field", "shot.dialogue"
    for line in shot.dialogue or ():
        emotion = getattr(line, "emotion", None)
        if isinstance(emotion, str):
            yield "expression_preset", emotion


def vocabulary_versions(shot) -> dict[str, str]:
    """``{entry id: version}`` for every registered entry ``shot`` names, sorted.

    Names the registry does not know (a descriptor animation, a parametrised
    easing) are not entries and add nothing; their effect is in the compiled
    document, which the shot key already covers.
    """
    out: dict[str, str] = {}
    for kind, name in _names(shot):
        e = lookup(kind, name)
        if e is None:
            continue
        out[e.id] = e.version
        for aspect_name in e.aspects:
            for m in methods_of(aspect_name):
                out[m.id] = m.version
    return dict(sorted(out.items()))


def vocabulary_digest(shot) -> str:
    """The sha256 of :func:`vocabulary_versions` — one more part of a shot's key."""
    blob = json.dumps(vocabulary_versions(shot), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def registry_digest() -> str:
    """The sha256 of every entry's ``(id, version)`` — what changed in the vocabulary at all."""
    pairs = sorted((e.id, e.version) for e in entries())
    return hashlib.sha256(json.dumps(pairs).encode()).hexdigest()


def register_vocabulary_key_part(renderer: str = "cutout") -> bool:
    """Fold :func:`vocabulary_digest` into ``renderer``'s shot key, through P6's seam.

    Returns whether the seam exists (``an.build.keys.register_shot_key_part``).
    Until the shot cache lands, it is a no-op returning ``False``.
    """
    try:
        from an.build.keys import register_shot_key_part  # type: ignore[import-not-found]
    except ImportError:
        return False
    register_shot_key_part(renderer, VOCABULARY_KEY_PART, lambda shot, *a, **k: vocabulary_digest(shot))
    return True
