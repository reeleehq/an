"""The scene tree's paths: the ONE Python statement of how ``runtime.js`` indexes nodes (an#343).

The runtime builds a container per node and indexes it in ``nodeIndex`` under a
slash-joined path; every channel target is such a path. The compiled scene's
top-level ``root`` is synthetic and is not indexed (its children start at the
entity name), and the overlay's children are indexed the same way. Since an#343
a node may carry ``scope``: its CHILDREN are indexed as if they were the
children of the node named ``scope`` in the same parent, so an environment's
foreground container (``set__front``, ``scope="set"``) indexes its planes as
``set/<plane>``, wherever the environment was cut. ``scope=""`` indexes them
as the parent's own children (a wrapper that adds a transform and no path
segment).

>>> from an.stage.serialize import NodeJSON
>>> root = NodeJSON(name="root", children=[
...     NodeJSON(name="set", children=[NodeJSON(name="sky")]),
...     NodeJSON(name="maya"),
...     NodeJSON(name="set__front", scope="set", children=[NodeJSON(name="wall")]),
... ])
>>> sorted(paths(root))
['maya', 'set', 'set/sky', 'set/wall', 'set__front']
>>> [p for _, p in chain(root, "set/wall")]
['root', 'set__front', 'set/wall']

The runtime's own copy of the rule is ``childPrefix`` in ``runtime.js``;
``tests/test_stage_tree.py`` runs it under node against :func:`child_prefix`,
and a lint test there refuses a new hand-rolled walk that joins names.

Works on the wire models (:mod:`an.stage.serialize`) and on their JSON dicts
alike, since the bench reads the staged document as JSON.
"""

from __future__ import annotations

from typing import Any, Iterator

__all__ = [
    "SYNTHETIC_ROOT",
    "child_prefix",
    "join",
    "walk",
    "lineage",
    "walk_children",
    "walk_document",
    "paths",
    "node_at",
    "chain",
]

#: The compiled scene's top-level container: never indexed by the runtime.
SYNTHETIC_ROOT: str = "root"


def _get(node: Any, key: str, default: Any = None) -> Any:
    if isinstance(node, dict):
        return node.get(key, default)
    return getattr(node, key, default)


def _children(node: Any) -> list:
    return list(_get(node, "children", None) or ())


def join(prefix: str, name: str) -> str:
    """``prefix/name``, or ``name`` at the top.

    >>> join("", "set"), join("set", "sky")
    ('set', 'set/sky')
    """
    return f"{prefix}/{name}" if prefix else name


def child_prefix(node: Any, path: str, prefix: str) -> str:
    """The prefix ``node``'s children are indexed under: its own ``path``, or,
    with ``scope``, ``scope`` taken in the parent's prefix (``""``: the
    parent's prefix itself). Mirrors ``childPrefix`` in ``runtime.js``.

    >>> from an.stage.serialize import NodeJSON
    >>> child_prefix(NodeJSON(name="a"), "env/a", "env")
    'env/a'
    >>> child_prefix(NodeJSON(name="a", scope="b"), "env/a", "env")
    'env/b'
    >>> child_prefix(NodeJSON(name="a", scope=""), "env/a", "env")
    'env'
    """
    scope = _get(node, "scope")
    if scope is None:
        return path
    return join(prefix, scope) if scope else prefix


def _walk(node: Any, prefix: str, ancestors: tuple) -> Iterator[tuple[str, Any, tuple]]:
    path = join(prefix, _get(node, "name"))
    yield path, node, ancestors
    inner = child_prefix(node, path, prefix)
    for child in _children(node):
        yield from _walk(child, inner, ancestors + ((node, path),))


def walk(node: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """``(path, node)`` for ``node`` and every descendant, as the runtime
    indexes them, in document order."""
    for path, n, _ in _walk(node, prefix, ()):
        yield path, n


def lineage(node: Any, prefix: str = "") -> Iterator[tuple[str, Any, tuple[str, ...]]]:
    """``(path, node, ancestor paths)`` for ``node`` and every descendant: the
    paths of the containers it is drawn inside, outermost first."""
    for path, n, ancestors in _walk(node, prefix, ()):
        yield path, n, tuple(p for _, p in ancestors)


def walk_children(root: Any) -> Iterator[tuple[str, Any]]:
    """``walk`` over the children of the synthetic ``root`` (not indexed)."""
    for child in _children(root):
        yield from walk(child)


def walk_document(doc: Any) -> Iterator[tuple[str, Any]]:
    """Every indexed ``(path, node)`` of a compiled document: the scene's
    entities, then the overlay's (one index for both layers)."""
    for layer in ("scene", "overlay"):
        root = _get(doc, layer)
        if root is not None:
            yield from walk_children(root)


def paths(root: Any) -> set[str]:
    """Every path the runtime indexes under the synthetic ``root``."""
    return {path for path, _ in walk_children(root)}


def node_at(root: Any, path: str) -> Any:
    """The node the runtime indexes at ``path`` (later wins, as ``nodeIndex``
    does), or raise ``KeyError`` naming the top-level nodes."""
    found = None
    for p, node in walk_children(root):
        if p == path:
            found = node
    if found is None:
        raise KeyError(
            f"no node at {path!r}; the top level has {[_get(c, 'name') for c in _children(root)]}"
        )
    return found


def chain(root: Any, path: str) -> list[tuple[Any, str]]:
    """``[(node, its indexed path)]`` from the synthetic ``root`` down to the
    node at ``path``, every container on the way included (a scoped container
    composes like any parent: it is a container in the runtime too).

    Raises ``KeyError`` naming what is there rather than measuring the wrong node.
    """
    found: list[tuple[Any, str]] | None = None
    for p, node, ancestors in (
        item for child in _children(root) for item in _walk(child, "", ())
    ):
        if p == path:
            found = [*ancestors, (node, p)]
    if found is None:
        near = sorted(
            p for p in paths(root) if p.split("/", 1)[0] == path.split("/", 1)[0]
        )
        raise KeyError(f"no node at {path!r}; under that entity: {near or 'nothing'}")
    return [(root, _get(root, "name")), *found]
