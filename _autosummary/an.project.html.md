# an.project

Project init/load/save — the on-disk anatomy of an an project.

Layout (from spec §11):

> my-scene/
> ├── an.toml
> ├── scene.md
> ├── ir/scene.json
> ├── assets/{characters,props,environments,voices,styles,sounds}/
> ├── artifacts/{audio,visemes,shots,previews}/
> ├── output/
> └── .an/{decisions.jsonl,verifier_runs/,memory.md}

### Functions

| [`init`](#an.project.init)(project_dir, \*[, name, force])   | Create a fresh an project at `project_dir`.                 |
|-----------------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`load`](#an.project.load)(project_dir)                      | Load an existing project.                                   |
| [`save`](#an.project.save)(project)                          | Persist a Project's current scene back to disk (md + json). |

### Classes

| [`Project`](#an.project.Project)(root, mall, scene)   | A loaded an project: directory + mall + current scene.   |
|-------------------------------------------------------------------------------|----------------------------------------------------------|

### *class* an.project.Project(root, mall, scene)

Bases: `object`

A loaded an project: directory + mall + current scene.

### an.project.init(project_dir, , name=None, force=False)

Create a fresh an project at `project_dir`.

Idempotent unless the directory already contains a non-empty `scene.md`;
pass `force=True` to overwrite. Returns the absolute project root.

* **Return type:**
  `Path`

### an.project.load(project_dir)

Load an existing project. Reconciles scene.md / ir/scene.json first.

* **Return type:**
  [`Project`](#an.project.Project)

### an.project.save(project)

Persist a Project’s current scene back to disk (md + json).

* **Return type:**
  `None`
