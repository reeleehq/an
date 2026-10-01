# an.bench.paths

Where the bench reads its corpus from and writes its ledger to.

One module owns every path so the “bench needs a source checkout” constraint is
stated once, with a typed error, rather than surfacing as a `FileNotFoundError`
from inside `shutil.copytree`.

### Module Attributes

| [`LEDGER_DIRNAME`](#an.bench.paths.LEDGER_DIRNAME)   | Ledger rows live here, one file per (date, commit).                                                                                        |
|-------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| [`GOLDEN_DIRNAME`](#an.bench.paths.GOLDEN_DIRNAME)   | Golden frames (an#38 fills this; the path convention ships now so the cassette work and the corpus work do not have to agree on it later). |

### Functions

| [`git_state`](#an.bench.paths.git_state)([root])                                 | `sha` / `branch` / `dirty` for the checkout, or <br/><br/>```<br/>``<br/>```<br/><br/>None\`\`s off-git.   |
|----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [`golden_dir`](#an.bench.paths.golden_dir)([root])                                | The golden-frame directory (an#38).                                                                        |
| [`golden_path`](#an.bench.paths.golden_path)(scene, frame_key, chromium_build, \*) | Where one golden frame lives.                                                                              |
| [`ledger_dir`](#an.bench.paths.ledger_dir)([root])                                | The ledger directory, created if absent.                                                                   |
| [`ledger_path`](#an.bench.paths.ledger_path)(\*[, root, git])                      | `<date>-<sha>[-dirty].json`.                                                                               |
| [`repo_root`](#an.bench.paths.repo_root)()                                       | The source checkout `an` was imported from.                                                                |

### Exceptions

| [`BenchLayoutError`](#an.bench.paths.BenchLayoutError)   | The bench was run somewhere it cannot find the corpus.   |
|---------------------------------------------------------------------|----------------------------------------------------------|

### *exception* an.bench.paths.BenchLayoutError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The bench was run somewhere it cannot find the corpus.

### an.bench.paths.GOLDEN_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'misc/bench/golden'*

Golden frames (an#38 fills this; the path convention ships now so the
cassette work and the corpus work do not have to agree on it later).

### an.bench.paths.LEDGER_DIRNAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'misc/bench/ledger'*

Ledger rows live here, one file per (date, commit). Append-only by
convention: an existing row is evidence about a commit, and editing it
rewrites history that `an bench --compare` (an#40) reads as fact.

### an.bench.paths.git_state(root=None)

`sha` / `branch` / `dirty` for the checkout, or 

```
``
```

None\`\`s off-git.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.bench.paths.golden_dir(root=None)

The golden-frame directory (an#38).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.bench.paths.golden_path(scene, frame_key, chromium_build, , root=None)

Where one golden frame lives.

Keyed on the **Chromium build alone** — no platform or arch segment. The
cross-architecture verdict measured those segments to be inert (zero
differing pixels and zero differing PNG bytes across arm64 macOS, x86-64
Linux and arm64 Linux, across two different SwiftShader JIT backends), so
carrying them would force one committed copy per platform for no
information. What the convention keeps is its real benefit: a Playwright
bump becomes a **new path requiring a deliberate re-bless** rather than a
red test with no explanation.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> golden_path("s", "f0", "140.0.7339.16").name
'f0-chromium140.0.7339.16.png'
```

### an.bench.paths.ledger_dir(root=None)

The ledger directory, created if absent.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### an.bench.paths.ledger_path(, root=None, git=None)

`<date>-<sha>[-dirty].json`.

The `-dirty` suffix is not decoration: a row measured against uncommitted
edits describes no commit, and a filename that claims one would be read by
an#40 as that commit’s evidence.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> ledger_path(git={"sha": "abc1234def", "dirty": True}).name.endswith("-dirty.json")
True
```

### an.bench.paths.repo_root()

The source checkout `an` was imported from.

Raises rather than returning a plausible-but-wrong path, because the
failure it guards is running the bench against an installed wheel: the
corpus lives under `examples/`, which is not packaged, so the first
symptom would be a missing-fixture error three frames deep.

The checkout’s folder name is not asserted: a git worktree or a clone
under another name is still a source checkout.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

```pycon
>>> (repo_root() / "an" / "bench" / "paths.py").is_file()
True
```
