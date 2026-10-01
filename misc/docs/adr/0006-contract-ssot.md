# ADR 0006 — The shared structured-animation contract is authored in `an` and published as a data package

**Status:** Accepted, 2026-10-01 (the maintainer's choice, option C on [an#257](https://github.com/thorwhalen/an/issues/257)) · **Decider:** the maintainer · **Related:** [an#257](https://github.com/thorwhalen/an/issues/257) (previz under `an`; the options and the decision), [an#261](https://github.com/thorwhalen/an/issues/261) (the publishing work), an#248 (P7, the vocabulary export), ADR 0001 decision 10 (the timing kernel is a cross-language contract), ADR 0003 decision 6 (one vocabulary registry), `misc/docs/core_from_three_genres.md` §3 and §7 decision 7; refines §7 decision 7, does not supersede it

## Context

The core study (`misc/docs/core_from_three_genres.md` §3) made the timing kernel a cross-language contract: `easing.json`, `kinds.json`, `timeline.schema.json`, `compiled.schema.json` and `timing_vectors.json`, now in `an/data/timing/`. ADR 0001 decision 10 put them in `an` because `an` is public and the core, and the study's §7 decision 7 (accepted) said the other consumers copy them: "the contract files live in `an` (public) and `previz` copies them, rather than `previz` owning them".

That was decided with one JavaScript consumer in view. There are now three TypeScript ones: `previz` (the TypeScript twin of the kernel, which asserts the golden vectors), `shaping` (whose animation tracks validate against `timeline.schema.json`) and the TypeScript port of `burns` (whose easing comes from the shared table). A fourth kind of content is about to join the files: P7 (an#248) exports the vocabulary registry (ADR 0003 decision 6) as JSON-described entries without code, which any engine, including `previz`'s formulas and the camera moves of an#257, needs to read.

Copying has a known failure mode in this family: the five drifting copies of easing and interpolation that the core study set out to end. A copy is a file nobody is told to refresh, so it drifts silently until a golden vector fails, or fails to exist for the new case. The maintainer asked on an#257 whether the single source of truth should therefore live outside both `an` and `previz`.

Two facts bound the answer. First, every entry in the contract is today generated from or checked against Python registries in `an` (the field-kind registry, the easing registry, and from P7 the vocabulary registry); no JavaScript package authors any entry. Second, `previz` is private and `an` is public, so the contract can only be published from the public side.

## Decision

1. **Authored in `an`.** The contract is authored in `an`'s registries (field kinds, easings, the vocabulary registry, the Pydantic models behind the schemas) and exported to data files. The files in `an/data/timing/` are generated output with a drift test, not hand-edited sources. This keeps ADR 0001 decision 10 and §7 decision 7 intact on authorship.
2. **Published as a data-only package.** CI builds and publishes a package that contains nothing but contract data, for JavaScript consumers: `easing.json`, `kinds.json`, `timeline.schema.json`, `compiled.schema.json`, `timing_vectors.json`, and from P7 the vocabulary export (per entry: id, version, kind, title, description, params schema, requires, levels; no code). The npm name is to be settled in the implementation (for example `@thorwhalen/an-contract`). On the Python side the same files stay reachable through `an` itself (`an/data/`), so Python consumers need no second package.
3. **The package has its own version, tracking the contract.** It is not `an`'s version. It is bumped, and a release is cut, only when a contract file changes; a release of `an` that leaves the contract alone publishes nothing. The version follows the compatibility rules of the contract: additive changes (a new easing, a new field kind, a new vocabulary entry) are minor, a changed meaning of an existing name is major and is gated as a kernel change (unchanged contract hashes, Python/JS parity tests, pure-pose tests, decoded-pixel goldens; ADR 0001 decision 10).
4. **A drift test.** A test in `an` regenerates the files from the registries and asserts that they equal the committed files, and that the committed files equal what the package build would publish. A registry change that is not exported fails CI.
5. **Consumers install, they do not copy.** `previz`, `shaping` and the `burns` TypeScript port depend on the published package at a version range, and their tests load the golden vectors and schemas from it. They add no copies of the files. A consumer that needs a case the vectors lack proposes it to `an` (the case lands in `timing_vectors.json`, the package is released, the consumer bumps its range).
6. **Direction of authorship is one-way.** JavaScript consumers read the contract; they do not write entries into it. A new easing, field kind or vocabulary entry that a JavaScript package wants is added in `an`'s registries.
7. **Revisit trigger.** If a JavaScript package ever needs to author entries (a formula that must be defined first in TypeScript and not mirrored in Python), move to option B: a neutral data package authored as data (JSON Schema, easing and kind tables, vocabulary entries without code, golden vectors), published to PyPI and npm, which `an` and the JavaScript packages both generate and verify their code against. This ADR is then superseded by a new record, not edited.

## Alternatives considered

- **A. Keep the files in `an`; JavaScript consumers copy and assert them** (the status quo of §7 decision 7). Cheapest, with `an` as the author. Rejected as the end state because with three TypeScript consumers and a growing set of files it produces three copies to keep in step by hand, which is the failure the contract exists to end. It is what we do until the package ships, and the consumers' tests are written so that swapping the copy for the package changes the path they load from and nothing else.
- **B. A neutral data-only contract package authored as data, published to PyPI and npm; `an` and `previz` depend on it and generate or verify their code against it.** Language-neutral, with no side privileged. Rejected for now: it adds a repository and a release train, moves authorship out of the Python registries that every entry is derived from today, and solves a problem (JavaScript authoring) that does not yet exist. Kept as the named successor (decision 7).
- **C. A, plus generated publishing** (chosen). Authorship stays where the registries are; JavaScript consumers get a real package with a version they can range over, and a drift test makes publishing a function of the registries.
- **Publish the whole `an` package to npm.** Rejected: `an` is Python; the JavaScript consumers need only data, and shipping a build of the stage runtime or the compiler with them would invite the consumers to depend on internals.
- **A git submodule or a vendored directory sync script.** No new registry account, no token. Rejected: it is copying with extra steps; there is still no version to range over and no install-time error when the contract moves.

## Consequences

- **Gains.** The three TypeScript consumers stop copying; a contract change reaches them as a version bump their CI sees. The vocabulary export that P7 produces has a delivery path from day one. `an` stays the single author, so no new repository or authoring home is created.
- **Costs.** A publish pipeline for a second ecosystem; an npm credential in `an`'s CI (the maintainer's to provide: a `manual-task` is filed when the workflow is ready, per an#261); a package name to claim; a contract version distinct from `an`'s, with its compatibility rules to keep. Consumers carry a dependency where they carried files.
- **Risks.** A release of the data package that does not match the registries would put consumers out of step with `an`; the drift test (decision 4) and publishing only from `an`'s release CI are the guards. A consumer pinned to an old range keeps working against an old contract, which is intended; a major bump is the signal to move. The package is public, so nothing private (for example `previz` formulas not yet released) may be exported into it; the vocabulary export carries only entries a genre has chosen to publish.

## First slice

The work is [an#261](https://github.com/thorwhalen/an/issues/261). **Status, 2026-10-01:** items 1 and 2 are built (the vocabulary export, the drift test, the `contract/` package and its workflow); the first publish waits on the maintainer's `NPM_TOKEN` secret and the package name (a `manual-task` issue); item 3 follows the first publish; item 4 is half done (the shape is in `architecture_as_built.md` §13; the name and first version are recorded when published).

1. Export from the registries to `an/data/timing/` (already the home of the five timing files) plus the vocabulary export once P7 (an#248) lands; the drift test (decision 4).
2. A package definition and a CI job that builds the data-only package and publishes it on a release that changes a contract file, with the contract's own version. The npm token is requested from the maintainer through a `manual-task` when the workflow is ready.
3. Switch the consumers from copied files to the package: `previz` (previz#3), `shaping` (shaping#10), the `burns` TypeScript port (burns#23).
4. Record the package name and the contract's versioning rule in `misc/docs/architecture_as_built.md` §13 when the first release ships.

## Related

- `misc/docs/core_from_three_genres.md` §3 (the core contract, assembled) and §7 decision 7 (contract files live in `an`; this ADR refines it: still authored in `an`, but JavaScript consumers get a published package instead of copies).
- ADR 0001 decision 10 (the timing kernel as a cross-language contract) and ADR 0003 decision 6 (one vocabulary registry, from which the export is generated).
- [an#257](https://github.com/thorwhalen/an/issues/257) — previz under `an`, the camera-move view-space model, the options A/B/C and the decision.
- `misc/docs/design_principles.md` — principle 3 (reuse over re-definition): one authored contract, many readers.
