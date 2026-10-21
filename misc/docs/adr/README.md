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
| 0007 | [A scene space: one world, and shots as viewpoints onto it](0007-scene-world.md) | Proposed, 2026-10-20 (built as its first slice: an#484) |
| 0007 | [A scene space: one world, and shots as viewpoints onto it](0007-scene-space.md) | Proposed, 2026-10-20 (built as its first slice: an#484) |
| 0007 | [A performer's recording is a voice: recorded takes enter through the TTS provider seam](0007-recorded-voices.md) | Proposed, 2026-10-21 (built: an#494) |
| 0008 | [A constraint layer under structured animation: bodies, joints, drivers and frames, solved per frame](0008-constraint-layer.md) | Proposed, 2026-10-21 |
