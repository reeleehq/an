# an.semantic.export

The vocabulary as a published, code-free contract file: `an/data/timing/vocabulary.json`.

ADR 0006 decision 2 (and an#261): the vocabulary registry
([`an.semantic.registry`](an.semantic.registry.md#module-an.semantic.registry)) is authored in `an`; any other engine — the
TypeScript `previz`, `shaping`, the `burns` port — reads it as data. This
module is the exporter, in the pattern of [`an.timing.contract`](an.timing.contract.md#module-an.timing.contract): a builder
([`build_vocabulary()`](#an.semantic.export.build_vocabulary)), a writer ([`write_vocabulary()`](#an.semantic.export.write_vocabulary)), a drift check
([`vocabulary_drift()`](#an.semantic.export.vocabulary_drift)) and a `write`/`check` command line:

```default
python -m an.semantic.export write
python -m an.semantic.export check
```

What it carries, per entry: `id`, `kind`, `name` (how a document spells
it), `version`, `title`, `description`, `levels` (the spectrum levels it
accepts), `params` (a JSON Schema object with defaults), `requires` (the
ADR 0002 requirement terms) and, where the entry has them, `usage`,
`examples`, `aspects` and (methods) `aspect` and `remedies`. Never
`expand`: no code leaves `an`. Camera moves are entries of kind
`camera_move` whose `params.path` lies in a `view_space` entry
(`view.framing2d`, `view.orbit3d`), so an engine reads a move once and
lowers it through the space it affords.

\*\*Only `an`’s own entries\*\* (`owner="an"`) are exported, so the file does
not depend on which genres happen to be loaded, and an installed genre never
edits it. Publishing a genre’s entries is a deliberate act: pass `owners=` and
say so (ADR 0006, Risks: the package is public).

```pycon
>>> doc = build_vocabulary()
>>> doc["version"], doc["owners"]
(1, ['an'])
>>> by_id = {e["id"]: e for e in doc["entries"]}
>>> by_id["camera.push_in"]["params"]["properties"]["path"]["default"][-1]["zoom"] > 1
True
>>> "expand" in by_id["camera.push_in"], by_id["view.framing2d"]["kind"]
(False, 'view_space')
```

### Module Attributes

| [`VOCABULARY_FILE`](#an.semantic.export.VOCABULARY_FILE)           | The vocabulary export's file name, beside the timing contract's files.      |
|----------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`VOCABULARY_FORMAT_VERSION`](#an.semantic.export.VOCABULARY_FORMAT_VERSION) | The shape of the file (not of its entries, which carry their own versions). |

### Functions

| [`build_vocabulary`](#an.semantic.export.build_vocabulary)(\*[, owners])   | The export document: every entry `owners` registered, as data, sorted by id.                |
|-----------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`vocabulary_drift`](#an.semantic.export.vocabulary_drift)([directory])    | How the committed `vocabulary.json` differs from what the registry generates (empty: none). |
| [`write_vocabulary`](#an.semantic.export.write_vocabulary)([directory])    | Regenerate `vocabulary.json` under `directory`.                                             |

### an.semantic.export.VOCABULARY_FILE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'vocabulary.json'*

The vocabulary export’s file name, beside the timing contract’s files.

### an.semantic.export.VOCABULARY_FORMAT_VERSION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

The shape of the file (not of its entries, which carry their own versions).

### an.semantic.export.build_vocabulary(, owners=('an',))

The export document: every entry `owners` registered, as data, sorted by id.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.semantic.export.vocabulary_drift(directory=PosixPath('/home/runner/work/an/an/an/data/timing'))

How the committed `vocabulary.json` differs from what the registry generates (empty: none).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.semantic.export.write_vocabulary(directory=PosixPath('/home/runner/work/an/an/an/data/timing'))

Regenerate `vocabulary.json` under `directory`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
