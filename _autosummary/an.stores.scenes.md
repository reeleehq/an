# an.stores.scenes

Scenes store — wraps the project’s `scene.md` + `ir/scene.json` pair.

Right now an an project contains exactly one scene (“main”), so this store
exposes only the `"main"` key. Future versions can support multi-scene
projects by promoting siblings inside a `scenes/` directory.

Reading returns a `SceneIR`. Writing accepts a `SceneIR` (or a dict that
validates as one) and persists both the JSON and the regenerated Markdown.

### Classes

| [`ScenesStore`](#an.stores.scenes.ScenesStore)(project_dir)   | `MutableMapping` exposing the scene file pair under a project root.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------------|

### *class* an.stores.scenes.ScenesStore(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`MutableMapping` exposing the scene file pair under a project root.

Keys: currently always `"main"`. The store enforces this by raising
`KeyError` for other keys.
