# an.stores.scenes

Scenes store — wraps the project’s `scene.md` + `ir/scene.json` pair.

Right now an an project contains exactly one scene (“main”), so this store
exposes only the `"main"` key. Future versions can support multi-scene
projects by promoting siblings inside a `scenes/` directory.

Reading returns a `SceneIR`. Writing accepts a `SceneIR` (or a dict that
validates as one) and persists the JSON and the Markdown – the Markdown UPDATED
rather than regenerated (an#275): unchanged content leaves the author’s file as it
was, and a change rewrites only the blocks it touches (`an.ir.sync.merge_markdown`).

### Functions

| [`patch_shot_duration_md`](#an.stores.scenes.patch_shot_duration_md)(markdown, shot_id, ...)   | `markdown` with shot `shot_id`'s `duration:` set to `seconds`, every other line — prose, comments, formatting — untouched.   |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|

### Classes

| [`ScenesStore`](#an.stores.scenes.ScenesStore)(project_dir)   | `MutableMapping` exposing the scene file pair under a project root.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------------|

### *class* an.stores.scenes.ScenesStore(project_dir)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

`MutableMapping` exposing the scene file pair under a project root.

Keys: currently always `"main"`. The store enforces this by raising
`KeyError` for other keys.

#### patch_shot_durations(durations)

Set `duration` on the named shots WITHOUT regenerating `scene.md`.

`__setitem__` rewrites the markdown from the IR, which drops every word
of prose and every comment the IR does not hold. This writes the JSON
through the read boundary as usual, and patches only each shot’s
`duration:` line in the markdown (inserting one into its

```
``
```

\`\` ``yaml shot ``` block, or the block itself, when there is none) —
what `an sync --accept-measured` uses to take a measured duration into
the authored scene (an#279).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.stores.scenes.patch_shot_duration_md(markdown, shot_id, seconds)

`markdown` with shot `shot_id`’s `duration:` set to `seconds`,
every other line — prose, comments, formatting — untouched.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> md = "# T\n\nA note.\n\n## Shot a (manim)\n\n```yaml shot\noptions: {source: a}  # the chart\n```\n"
>>> print(patch_shot_duration_md(md, "a", 3.1))
# T

A note.

## Shot a (manim)

```yaml shot
duration: 3.1
options: {source: a}  # the chart
```

```text
<BLANKLINE>
```
