# an.library.root

Where a package’s library lives on disk: one root per package (ADR 0005 §2, plan §1 decisions 7–8).

The root is resolved in this order, first match wins:

1. an explicit `root=` (tests, power users, a team share);
2. the environment variable `<PKG>_HOME` (`AN_HOME`, `CUTAN_HOME`) — one
   switch for a whole shell or CI job;
3. the platform data folder: `$XDG_DATA_HOME/<pkg>` when `XDG_DATA_HOME` is
   set to an absolute path, else `~/.local/share/<pkg>` on Linux and macOS;
   `%LOCALAPPDATA%\<pkg>` on Windows. On macOS this is deliberately
   `~/.local/share`, not `~/Library/Application Support` — the maintainer’s
   choice, and the one the fleet’s storage rules use.

This is the data-folder half of `config2py.get_app_folder`, **vendored** (plan
§1 decision 8): twenty lines are cheaper than a dependency, and the dependency is
taken only if more than this is ever needed.

Under the root, one sub-folder per kind of data, never files at the top:
`library/` (records, versions, blobs) and `projects/` (agent-made videos).
Resolving a root never creates it and never raises at import; the stores create
their folders on first use.

```pycon
>>> env = {"AN_HOME": "/srv/an-lib"}
>>> library_root(package="an", environ=env).as_posix()
'/srv/an-lib'
>>> library_root(package="cutan", environ={"XDG_DATA_HOME": "/data"}, platform="linux").as_posix()
'/data/cutan'
```

### Module Attributes

| [`CORE_PACKAGE`](#an.library.root.CORE_PACKAGE)     | The core package, whose library every genre's search path reads after its own.   |
|-------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`LIBRARY_DIRNAME`](#an.library.root.LIBRARY_DIRNAME)  | The sub-folder of a root that holds the library stores.                          |
| [`PROJECTS_DIRNAME`](#an.library.root.PROJECTS_DIRNAME) | The sub-folder of a root that holds agent-made projects (design §7.5).           |

### Functions

| [`git_worktree_of`](#an.library.root.git_worktree_of)(path)                             | The git work tree containing `path` (or its nearest existing ancestor), if any.   |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`home_env_var`](#an.library.root.home_env_var)(package)                             | The override variable for `package`'s root.                                       |
| [`library_root`](#an.library.root.library_root)([root, package, environ, platform])  | The data root of `package` — its library and its projects live under it.          |
| [`project_dir`](#an.library.root.project_dir)(project_id[, root, package, environ]) | The default directory of the agent-made project `project_id` (design §7.5).       |
| [`projects_root`](#an.library.root.projects_root)([root, package, environ])           | Where agent-made projects go by default: `<root>/projects/`.                      |

### Exceptions

| [`LibraryLocationWarning`](#an.library.root.LibraryLocationWarning)   | Library data, or private material checked out of it, sits inside a git work tree.   |
|---------------------------------------------------------------------------|-------------------------------------------------------------------------------------|

### an.library.root.CORE_PACKAGE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'an'*

The core package, whose library every genre’s search path reads after its own.

### an.library.root.LIBRARY_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'library'*

The sub-folder of a root that holds the library stores.

### *exception* an.library.root.LibraryLocationWarning

Bases: [`UserWarning`](https://docs.python.org/3/builtins/exceptions.html#UserWarning)

Library data, or private material checked out of it, sits inside a git work tree.

ADR 0005 decision 2: a library root is never inside a repository. The default
guarantees it; an explicit `root`, `<PKG>_HOME` or a project in a repo
can break it, and the library may hold private-study material.

### an.library.root.PROJECTS_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'projects'*

The sub-folder of a root that holds agent-made projects (design §7.5).

### an.library.root.git_worktree_of(path)

The git work tree containing `path` (or its nearest existing ancestor), if any.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     git_worktree_of(d) is None
True
```

### an.library.root.home_env_var(package)

The override variable for `package`’s root.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> home_env_var("an"), home_env_var("my-genre")
('AN_HOME', 'MY_GENRE_HOME')
```

### an.library.root.library_root(root=None, , package='an', environ=None, platform=None)

The data root of `package` — its library and its projects live under it.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

root: an explicit root; wins over everything
package: the package whose root this is (`an` for the core library, a

> genre’s own name for its library)

environ: the environment to read (default `os.environ`; injectable for tests)
platform: `sys.platform` value to resolve for (default: this one)

```pycon
>>> library_root("~/x", package="an").name
'x'
```

### an.library.root.project_dir(project_id, root=None, , package='an', environ=None)

The default directory of the agent-made project `project_id` (design §7.5).

`an init <dir>` with an explicit directory keeps working anywhere; this is
the default for projects an agent makes, so they never land in a session’s
working folder or a repository.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> project_dir("alice-and-bob", "/lib").as_posix()
'/lib/projects/alice-and-bob'
>>> project_dir("../escape", "/lib")
Traceback (most recent call last):
ValueError: ...
```

### an.library.root.projects_root(root=None, , package='an', environ=None)

Where agent-made projects go by default: `<root>/projects/`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> projects_root("/lib", package="cutan").as_posix()
'/lib/projects'
```
