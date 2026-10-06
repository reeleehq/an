# an.build.derived

A renderer’s derived stores, as `an cache gc` collects them (an#299).

An opaque renderer keeps intermediates of its own beside the shot cache — Manim
its raw pictures, their measurement records and contact sheets — content-keyed,
so every edit adds entries and nothing removes them. A renderer declares them
here, beside its shot keyer ([`an.build.keys.register_shot_keyer()`](an.build.keys.html.md#an.build.keys.register_shot_keyer)), with
[`register_derived_stores()`](#an.build.derived.register_derived_stores); [`an.build.gc`](an.build.gc.html.md#module-an.build.gc) collects every registered
store under the shot cache’s guarantees.

A declaration ([`DerivedStores`](#an.build.derived.DerivedStores)) names:

- `record_store` — the store whose entries NAME others (Manim’s
  `measurements`: a record names its picture and its contact sheet), deleted
  first, so a record never names something already gone;
- `named_stores` — the stores records name (`pictures`,
  `contact_sheets`);
- `entries(renderer, shot, ctx)` — the record-store keys a render of `shot`
  under `ctx` reads, COMPUTED (never rendered);
- `provenance(render_provenance)` — the entries a cached shot’s provenance
  names, by store;
- `names(record_bytes)` — what one record names, by store; it raises
  [`UnreadableRecordError`](#an.build.derived.UnreadableRecordError) for bytes it cannot read (a record half
  > written by a concurrent render), and the collector then deletes nothing a
  > record could name.

A store belongs to one renderer: a second claim is refused, so one renderer’s
`names` never reads another’s records.

```pycon
>>> spec = DerivedStores(
...     record_store="records", named_stores=("blobs",),
...     entries=lambda renderer, shot, ctx: set(),
...     provenance=lambda provenance: {},
...     names=lambda data: {"blobs": {data.decode()}},
... )
>>> sorted(spec.stores)
['blobs', 'records']
>>> sorted(spec.closure({"records": {"r": b"b1"}}, {"records": {"r"}})["blobs"])
['b1']
```

### Functions

| `derived_stores_for`(renderer_name)                                                               |                                                             |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`register_derived_stores`](#an.build.derived.register_derived_stores)(renderer_name, spec, \*) | Declare `renderer_name`'s derived stores for `an cache gc`. |
| [`registered_derived_stores`](#an.build.derived.registered_derived_stores)()                      | Every declaration, by renderer name.                        |

### Classes

| [`DerivedStores`](#an.build.derived.DerivedStores)(record_store, named_stores, ...)   | One renderer's derived stores (see the module docstring).   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------|

### Exceptions

| [`DerivedStoresRegistrationError`](#an.build.derived.DerivedStoresRegistrationError)   | A derived-store declaration that cannot be collected safely.   |
|-----------------------------------------------------------------------------------|----------------------------------------------------------------|
| [`UnreadableRecordError`](#an.build.derived.UnreadableRecordError)            | A record's bytes cannot be read (half written, damaged).       |

### *class* an.build.derived.DerivedStores(record_store, named_stores, entries, provenance, names)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One renderer’s derived stores (see the module docstring).

#### closure(mall, entries)

`entries` plus what each of its records names. A record that is
absent names nothing; one that cannot be read raises
[`UnreadableRecordError`](#an.build.derived.UnreadableRecordError).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]

#### *property* stores *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Every store, the record store first (the deletion order).

### *exception* an.build.derived.DerivedStoresRegistrationError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A derived-store declaration that cannot be collected safely.

### *exception* an.build.derived.UnreadableRecordError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A record’s bytes cannot be read (half written, damaged).

### an.build.derived.register_derived_stores(renderer_name, spec, , replace=False)

Declare `renderer_name`’s derived stores for `an cache gc`.

Refused: a store another renderer already claims, and a second
registration for the name unless `replace` (a module reloaded passes
the same stores again, which is allowed).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.build.derived.registered_derived_stores()

Every declaration, by renderer name. Loads the renderer registry first
(a backend behind the import firewall declares when it is imported), its
load warnings about unrelated backends silenced: they are the render’s
to give.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`DerivedStores`](#an.build.derived.DerivedStores)]
