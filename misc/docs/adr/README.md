# Architecture decision records

One file per decision, numbered in the order they were proposed. A record's **status** is one of *Proposed* (written, awaiting the maintainer), *Accepted*, *Superseded by NNNN*, or *Rejected*. Only the maintainer moves a record out of *Proposed*. A superseded record is kept and points at its successor; it is never edited into agreement with the new decision.

Format: Context → Decision → Alternatives considered → Consequences → First slice → Related. The principles every record is checked against are in `misc/docs/design_principles.md`.

| # | Title | Status |
|---|---|---|
| — | [What CI verifies, and what it deliberately does not](../adr_ci_verification_perimeter.md) (predates this folder; kept at its old path because other docs link it) | Accepted, 2026-08-21 |
| 0001 | [`an` is the core; genres are packages that depend on it](0001-core-genre-split.md) | Accepted, 2026-10-01 |
| 0002 | [Capability-based applicability, with a universal default for every aspect](0002-capability-applicability-defaults.md) | Accepted, 2026-10-01 |
| 0003 | [The structured ↔ semantic specification spectrum, and one semantic layer for all genres](0003-structured-semantic-spectrum.md) | Accepted, 2026-10-01 |
| 0004 | [Incremental re-processing through a content-addressed build graph](0004-incremental-reprocessing.md) | Accepted, 2026-10-01 |
| 0005 | [A persistent asset library: flat ids, immutable versions, content-addressed files, derived capability facets](0005-asset-library.md) | Accepted, 2026-10-01 |
| 0006 | [The shared structured-animation contract is authored in `an` and published as a data package](0006-contract-ssot.md) | Accepted, 2026-10-01 (maintainer's choice) |
