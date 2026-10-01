# ADR 0005 — A persistent asset library: flat ids, immutable versions, content-addressed files, derived capability facets

**Status:** Proposed, 2026-10-01 · **Decider:** the maintainer · **Related:** the design, [`misc/docs/asset_library_design.md`](../asset_library_design.md); the research, [`misc/docs/research/cutout_asset_management.md`](../research/cutout_asset_management.md); ADR 0001 (core/genre split), ADR 0002 (capabilities), ADR 0004 (incremental re-processing); an#211 (licence classes, `AssetSource`), an#220 (per-part sources), an#224 (locomotion by capability); pillar 7 (`dol`-backed stores)

## Context

`an` persists everything per project: `build_project_mall(project_dir)` holds the characters, props, environments, sounds, voices and style packs of one video, and a scene's `AssetRef` points into that project's own stores. Nothing outlives its video. The end-user agents of 2026-09-30 therefore stored their work per session and per style: the same character existed in four folders, its two rounds were copies rather than versions, and its rights were recorded in three incompatible free-form `provenance.json` files that no code reads. The maintainer asked for storage behind a `MutableMapping` facade, rooted at `~/.local/share/<package>`, organised for reuse across videos *and* styles, with a flat store and tags instead of folder hierarchies, and informed by production practice.

Production practice is consistent (the research report surveys Toon Boom Harmony, Moho, Spine, Live2D, Character Animator, Rive, ShotGrid, ftrack, Kitsu, USD and OpenAssetIO): a library is separate from a production and shared at several scopes; an asset's identity, its immutable numbered versions and its files are three entities; variation inside an asset is a swap into a named slot, while a different look is a different asset; consumers pin versions and either reference or detach; capability is read from a controlled vocabulary on the rig, not from the pixels.

Two facts about the code shape the decision. The project stores are hand-written folder mappings, and the compiler, validator and renderer read `store._root` to find art files, so a store without a folder cannot serve art today. And provenance is already modelled and enforced (`AssetSource`, `license_class`, `an credits`, the private-study warning), so the library must reuse it, not replace it.

## Decision

1. **A library separate from the project.** The library is persistent and cross-project; a project is one video that references library assets. Libraries form an ordered search path (the user's library first, then extra roots such as a team share, a shipped seed library or a remote bucket).
2. **Root.** `root=` argument, else the `<PKG>_HOME` env var, else the platform data folder (`$XDG_DATA_HOME/<pkg>`, `~/.local/share/<pkg>`, `%LOCALAPPDATA%\<pkg>`), resolved with `config2py`'s data-folder logic. Never inside a repository. Rebuildable things go to the cache folder. Agent-made projects default to `<root>/projects/<project_id>/`.
3. **Flat, readable ids**: `<kind>.<slug>` (`character.alice-reiniger`). Unique per library; renames are aliases, never moves.
4. **Three entities.** A *record* per asset (identity and curation: kind, family, declared facets, tags, status, head version; mutable). A *version* per publish (`v001`, `v002`, …; immutable, write-once): the existing descriptor document verbatim, its files as `dol.content.ContentRef`s, its `AssetSource`, `derived_from`, derived affordances with the analyser version, the rolled-up rights, and a `manifest_sha256` that is its content identity. *Blobs*: every file once, keyed by SHA-256.
5. **Facets over folders.** `kind`, `family`, `style`, `origin`, `license_class`, `status`, `art` and **affordances** are facets with controlled vocabularies; free tags for the rest. What derives from content (affordances, rights, art type) lives on the version; curation (style fit, tags, status) lives on the record.
6. **Affordances are derived, first-class, and use ADR 0002's vocabulary.** Each kind's analyser is ADR 0002's `affordances(asset)`; the library snapshots and indexes it, recomputes it on `reindex` when the analyser's version changes, and marks any asserted (non-derivable) fact as asserted. `find(…, affords=[…], near=True)` returns near misses with the missing capabilities and their remedies.
7. **Search** is `find(kind, style, affords, rights, …)` with AND across facets and OR within, plus `vocabulary()` so an agent can map words to terms (spectrum (b)) and a verifier for goal-level asks (spectrum (c)). The index is derived and replaceable behind one keyword.
8. **Projects pin and check out.** `AssetRef` gains an additive, omit-when-unset `library: "<asset_id>@<version>"`. The v1 resolution strategy is **check-out**: materialise the version into the project's existing store layout, record its origin, pin it in a project lockfile; editing it forks it; `publish` sends it back as a new version. Live **reference** is the same seam (`resolve=`) once the renderer stages art through the store instead of `store._root`.
9. **Variants.** Swappable variation stays inside the asset (swap sets, skins, views). A new state is a new version. A different look of the same character is a sibling asset in the same `family`, linked by `derived_from`. Motion clips are their own kind and declare `requires`.
10. **Rights on every version.** `AssetSource` on the version and per file; rights roll up as the most restrictive class across the asset, its files and everything it derives from; `unknown` and `private` are not publishable. `private` or `unknown` versions are never copied out of the local user library without an explicit override.
11. **Stores are `dol` `MutableMapping`s, injected.** `build_library_mall(root=None, **overrides)` → `records`, `versions` (write-once), `blobs` (content-addressed). Moving to S3 is an injection; URLs are minted on demand, never stored.
12. **Placement.** The mechanism is core (`an.library`, ADR 0001). Kinds' analysers, the style vocabulary and motion requirements register from the genre package.

## Alternatives considered

- **Folders by style, then kind, then name** (what the sessions did). Easy to browse. Rejected: an asset reused across styles must live in one folder or be copied, and the copies drift; the maintainer named this as the problem.
- **Keep the per-project mall and copy folders between projects.** No new code. Rejected: no identity, no versions, no search, rights lost on copy.
- **Pure content addressing for assets too** (an asset *is* its hash). Maximal integrity. Rejected as the identity: people and agents need a stable name that survives edits. Kept for files and as each version's manifest hash.
- **Opaque ids (ULIDs) with a display name.** Collision-free. Rejected for v1 because agents and the maintainer type and read ids; a uniqueness check and alias records cost less than a lookup on every mention.
- **Live reference as the default.** No copies, edits propagate. Deferred, not rejected: it needs the renderer's `_root` staging changed first, and check-out gives reproducible, portable projects meanwhile.
- **Hand-typed capability tags.** Simple. Rejected: they drift from the art (ADR 0002's reasoning); derived facets cannot.
- **Adopt a production tracker (Kitsu, ShotGrid) or USD as the store.** Mature. Rejected as dependencies: they are server products or 3D-centric; their entity models (asset, version, file; breakdown; variant sets; traits) are adopted as concepts.

## Consequences

- **Gains.** Assets outlive their videos and are reused across styles; an agent can ask for "a character with legs and a side view in the Reiniger style" and get either a hit or a remedy; projects become reproducible (pinned manifest hashes) and their dependency keys feed ADR 0004; rights are machine-readable everywhere and the private-study boundary is enforced at the library's edge.
- **Costs.** A new subsystem (records, versions, blobs, index, check-out, publish); a new dependency (`config2py`) unless the XDG logic is inlined; capability names and asset ids become persisted identifiers; check-out duplicates bytes between the library and each project until reference mode exists.
- **Risks.** Analysers that disagree with the compiler would make facets lie; ADR 0002's rule that the derivation is what the compiler actually finds is the guard. A library holding private-study material must stay off every published channel; the default root and the export refusal are the guards.

## First slice

1. `an.library`: root resolution, `build_library_mall`, `publish`, `find`, `vocabulary`, `show`, `checkout` (check-out only), with synthetic fixtures in tests.
2. One analyser (characters: legs, arms, views, mouth chart, gait), shared with ADR 0002's first slice.
3. `AssetRef.library` and the project lockfile.
4. `an library` CLI over the same functions; MCP after.
5. A later issue migrates the 2026-09-30 session assets with `import_project_assets` (design §12).

## Related

- `misc/docs/asset_library_design.md` — the full design, layout, examples, glossary and the open decisions.
- `misc/docs/research/cutout_asset_management.md` — the production and standards research, with references.
- `misc/docs/design_principles.md` — principles 2 and 3.
