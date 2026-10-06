# an.stage.tree

The scene tree’s paths: the ONE Python statement of how `runtime.js` indexes nodes (an#343).

The runtime builds a container per node and indexes it in `nodeIndex` under a
slash-joined path; every channel target is such a path. The compiled scene’s
top-level `root` is synthetic and is not indexed (its children start at the
entity name), and the overlay’s children are indexed the same way. Since an#343
a node may carry `scope`: its CHILDREN are indexed as if they were the
children of the node named `scope` in the same parent, so an environment’s
foreground container (`set__front`, `scope="set"`) indexes its planes as
`set/<plane>`, wherever the environment was cut. `scope=""` indexes them
as the parent’s own children (a wrapper that adds a transform and no path
segment).

```pycon
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
```

The runtime’s own copy of the rule is `childPrefix` in `runtime.js`;
`tests/test_stage_tree.py` runs it under node against [`child_prefix()`](#an.stage.tree.child_prefix),
and a lint test there refuses a new hand-rolled walk that joins names.

Works on the wire models ([`an.stage.serialize`](an.stage.serialize.md#module-an.stage.serialize)) and on their JSON dicts
alike, since the bench reads the staged document as JSON.

### Module Attributes

| [`SYNTHETIC_ROOT`](#an.stage.tree.SYNTHETIC_ROOT)   | never indexed by the runtime.   |
|-------------------------------------------------------------------|---------------------------------|

### Functions

| [`child_prefix`](#an.stage.tree.child_prefix)(node, path, prefix)   | The prefix `node`'s children are indexed under: its own `path`, or, with `scope`, `scope` taken in the parent's prefix (`""`: the parent's prefix itself).                                                  |
|-------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`join`](#an.stage.tree.join)(prefix, name)                 | `prefix/name`, or `name` at the top.                                                                                                                                                                        |
| [`walk`](#an.stage.tree.walk)(node[, prefix])               | `(path, node)` for `node` and every descendant, as the runtime indexes them, in document order.                                                                                                             |
| [`lineage`](#an.stage.tree.lineage)(node[, prefix])            | `(path, node, ancestor paths)` for `node` and every descendant: the paths of the containers it is drawn inside, outermost first.                                                                            |
| [`walk_children`](#an.stage.tree.walk_children)(root)                | `walk` over the children of the synthetic `root` (not indexed).                                                                                                                                             |
| [`walk_document`](#an.stage.tree.walk_document)(doc)                 | Every indexed `(path, node)` of a compiled document: the scene's entities, then the overlay's (one index for both layers).                                                                                  |
| [`paths`](#an.stage.tree.paths)(root)                        | Every path the runtime indexes under the synthetic `root`.                                                                                                                                                  |
| [`node_at`](#an.stage.tree.node_at)(root, path)                | The node the runtime indexes at `path` (later wins, as `nodeIndex` does), or raise `KeyError` naming the top-level nodes.                                                                                   |
| [`chain`](#an.stage.tree.chain)(root, path)                  | `[(node, its indexed path)]` from the synthetic `root` down to the node at `path`, every container on the way included (a scoped container composes like any parent: it is a container in the runtime too). |

### an.stage.tree.SYNTHETIC_ROOT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'root'*

never indexed by the runtime.

* **Type:**
  The compiled scene’s top-level container

### an.stage.tree.chain(root, path)

`[(node, its indexed path)]` from the synthetic `root` down to the
node at `path`, every container on the way included (a scoped container
composes like any parent: it is a container in the runtime too).

Raises `KeyError` naming what is there rather than measuring the wrong node.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

### an.stage.tree.child_prefix(node, path, prefix)

The prefix `node`’s children are indexed under: its own `path`, or,
with `scope`, `scope` taken in the parent’s prefix (`""`: the
parent’s prefix itself). Mirrors `childPrefix` in `runtime.js`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> from an.stage.serialize import NodeJSON
>>> child_prefix(NodeJSON(name="a"), "env/a", "env")
'env/a'
>>> child_prefix(NodeJSON(name="a", scope="b"), "env/a", "env")
'env/b'
>>> child_prefix(NodeJSON(name="a", scope=""), "env/a", "env")
'env'
```

### an.stage.tree.join(prefix, name)

`prefix/name`, or `name` at the top.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> join("", "set"), join("set", "sky")
('set', 'set/sky')
```

### an.stage.tree.lineage(node, prefix='')

`(path, node, ancestor paths)` for `node` and every descendant: the
paths of the containers it is drawn inside, outermost first.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]]]

### an.stage.tree.node_at(root, path)

The node the runtime indexes at `path` (later wins, as `nodeIndex`
does), or raise `KeyError` naming the top-level nodes.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.stage.tree.paths(root)

Every path the runtime indexes under the synthetic `root`.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.stage.tree.walk(node, prefix='')

`(path, node)` for `node` and every descendant, as the runtime
indexes them, in document order.

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.stage.tree.walk_children(root)

`walk` over the children of the synthetic `root` (not indexed).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.stage.tree.walk_document(doc)

Every indexed `(path, node)` of a compiled document: the scene’s
entities, then the overlay’s (one index for both layers).

* **Return type:**
  [`Iterator`](https://docs.python.org/3/library/typing.html#typing.Iterator)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
