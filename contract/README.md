# @thorwhalen/an-contract

The shared structured-animation contract of [`an`](https://github.com/thorwhalen/an), as data: golden vectors, JSON Schemas, easing and field-kind tables, and the code-free vocabulary. No code, no dependencies.

**This package is generated. Never edit its files, and never hand-edit the copies in a consumer.** Every file is written from `an`'s registries by `python -m an.timing.contract write` and `python -m an.semantic.export write`, checked for drift by `an`'s tests, and copied here by CI (`contract/build.py` in the `an` repository). To change a name, a curve, a field kind or a vocabulary entry, change it in `an` and release.

```js
import vectors from "@thorwhalen/an-contract/timing_vectors.json" with { type: "json" };
import vocabulary from "@thorwhalen/an-contract/vocabulary.json" with { type: "json" };
```

## Files

| file | what it is |
| --- | --- |
| `timing_vectors.json` | compiled documents and the state at listed times: what a kernel implementation must reproduce |
| `easing.json` | every registered easing (name, version, family, solver) with sample values |
| `kinds.json` | every field kind with sample interpolations, and the seeded property spaces |
| `timeline.schema.json` | JSON Schema of the authored flat timeline `(start, end, address, change)` |
| `compiled.schema.json` | JSON Schema of the compiled form: tracks, placed clips, loop modes, channels |
| `vocabulary.json` | every vocabulary entry without code: id, version, kind, title, description, params (JSON Schema with defaults), requires, accepted levels; camera moves are entries over the `view.*` space entries |

Numbers agree within `1e-9 * max(1, |x|, |y|)`; strings, booleans, `null`, list lengths and object keys agree exactly. A state is sparse: an address no clip has started writing is absent (at rest).

## Versioning

The version is the contract's own, not `an`'s. It changes only when a contract file changes, and a release is cut only then. An additive change (a new easing, field kind or vocabulary entry) is a minor bump; a changed meaning of an existing name is a major bump (ADR 0006, decision 3). Consumers depend on this package at a version range and load vectors and schemas from it; they do not copy files. A case a consumer needs and the vectors lack is proposed to `an`.

Source: [`contract/`](https://github.com/thorwhalen/an/tree/main/contract) · design: ADR 0006 (`misc/docs/adr/0006-contract-ssot.md`) · MIT.
