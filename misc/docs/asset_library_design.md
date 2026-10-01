# The asset library — design

**Status:** Proposed, 2026-10-01. **Decision record:** [ADR 0005](adr/0005-asset-library.md). **Research behind it:** [`research/cutout_asset_management.md`](research/cutout_asset_management.md) (how Toon Boom Harmony, Moho, Spine, Live2D, Character Animator, Rive, ShotGrid, ftrack, Kitsu and USD organise reusable assets; provenance standards). **Principles it serves:** `design_principles.md` — above all principle 2, capability-based applicability, and principle 3, reuse over re-definition. **Sibling records:** ADR 0001 (core/genre split), ADR 0002 (capabilities: the vocabulary and matcher this library indexes), ADR 0004 (incremental re-processing, which keys on the manifest hashes defined here).

This document designs a **persistent, cross-project asset library** for the cut-out genre package (its name is undecided; this document writes `<pkg>`). Nothing here is built yet. Where this says "today", it describes `an` as of v0.1.124.

## 0. The proposal in one screen

```
~/.local/share/<pkg>/                       # the root: XDG data dir, overridable (§3)
  library/records/<asset_id>.json           # one per asset: identity, kind, family, facets, tags, status, head version
  library/versions/<asset_id>/<vNNN>.json   # immutable publish: descriptor + {path: ContentRef} + source + affordances + rights
  library/blobs/<aa>/<sha256>               # every file's bytes, content-addressed and deduplicated (dol.content)
  projects/<project_id>/                    # a video: today's project layout, plus assets.lock.json pinning what it uses
```

- **Two things, not one.** The *library* holds reusable assets across videos and styles. A *project* is one video: a scene plus references to what it uses. Today only the second exists.
- **Flat and faceted, not foldered.** An asset is keyed by one flat id (`character.alice-reiniger`). Style, kind, family, origin, licence class and **affordances** are facets on the record, so one asset can sit in several "places" at once [1][2]. No `style/kind/name` directory tree.
- **Three things per asset: identity, version, file** — as in ShotGrid, ftrack and Kitsu [3][4][5]. A version is immutable (`v001`, `v002`, …); files live once in a content-addressed blob store [6].
- **Affordances are derived, first-class and queryable.** "Has legs", "has a side view", "has a Preston Blair mouth chart" are computed from the descriptor at publish time by registered analysers — never hand-typed beside it — and they are the vocabulary a behaviour's requirements are matched against (principle 2).
- **Projects pin, then check out.** A project names `character.alice-reiniger@v002`; v1 materialises that version's files into the project (copy-on-write, origin recorded, version pinned in a lockfile). Live reference without copying is a later mode behind the same seam.
- **Provenance on every version.** The existing `AssetSource` (an#211) rides on every version and every file; rights roll up along the derivation chain to one `publishable` verdict, and *unknown* is never publishable.
- **Every store is a `MutableMapping`** (`dol`), so the local folders become S3 or a database by injecting a different store, with no change to business logic.

## 1. What is true today

Measured in the code and in the end-user sessions of 2026-09-30, not assumed:

| Today | Consequence |
|---|---|
| The only persistence is the per-project mall (`an.build_project_mall`, `an/stores/`): `characters`, `props`, `environments`, `sounds`, `voices`, `styles`, plus scene, artifact, output and decision stores, all under one project directory. | No asset outlives its video. Reuse means copying a folder by hand; there is no import path between projects. |
| A scene references assets by `AssetRef(kind, id, store, ref, …)` — a key in *this* project's store. | There is nothing for a project to point *at* outside itself. |
| The stores are hand-written `MutableMapping`s over folders (`an/stores/_common.py`), not `dol` stores, and the compiler, renderer and validator reach into `store._root` to find art files (e.g. `render.py`'s asset staging, `compile.py`, `ir/validate.py`). | A store with no filesystem root cannot serve art today. Any library design must either materialise files into a project or fix this leak first. §7 does the former in v1. |
| Provenance is real and enforced: `AssetSource` (`an/ir/assets.py`) on characters, attachments, props, environments, planes, sounds and styles; `license_class` → `attribution`/`free`/`private`/`unknown`; `an credits` and a render-time `PrivateStudyWarning` (an#211). | The library reuses this model rather than inventing one. |
| Capabilities exist only implicitly: `walk` looks for limb pairs by name and falls back to a `rock` gait; `turn` needs a key in the `view` swap set; a descriptor declares `rest_view`, `gait`, `face_overlay`. | Nothing can be *asked* "which characters have legs and a side view?". an#224 (locomotion with declared requirements) needs exactly this. |
| End-user agents stored their work per session and per style: one folder per style, each holding source footage, carving scratch, two full project copies (v1, v2), an `assets/` folder and a `provenance.json`. The three `provenance.json` files use three different free-form schemas, and `assets/` is mall-shaped in one style and not in the other two. | The layout is not reusable: the same character exists in four places, its versions are copies, and its rights are recorded in prose the code cannot read. |

The repo's earlier research covered the *format* of a character (`Real Character Art for an…` §1, §5; `report 2 - Animation interchange formats…`, Patterns 4 and 5: skins decouple skeleton from appearance; define once, reference by id) but not how a production organises a library across projects. The research report above fills that gap; the design below applies it.

## 2. The library and the project

Production tools separate the two the same way. Harmony Server shares library *templates* at four scopes — one project (Symbols), a Job, an Environment, and an optional Global library [7]; Kitsu has per-production assets plus a cross-production Asset Library [8]; Rive publishes versioned components that consumers pin [9].

| | **Library** | **Project** |
|---|---|---|
| What | Reusable assets: characters (rigs/puppets), props, environments and their planes, style packs, voices, sounds, motion clips, reference material (model sheets, turnaround sheets, mouth charts). | One video: `scene.md` ↔ `ir/scene.json`, the assets it uses, its renders, its decision log. |
| Lifetime | Persistent, grows over years, shared across videos and styles. | One production. Disposable after delivery, except as a record. |
| Mutability | Versions are immutable; records are curated. | Freely edited. |
| Production analogue | Harmony library / Kitsu Asset Library / ShotGrid Assets. | Harmony scene / Kitsu shot / a ShotGrid sequence. |
| `an` today | — | `build_project_mall(project_dir)`. |

**Scopes, as a search path.** A process sees an ordered list of libraries: the user's library first, then any extra roots (a team library, a shipped seed library of free assets, later a remote one). An id resolves in the first library that has it. This is Harmony's scope chain [7] reduced to the one mechanism that matters, and it is the seam where a shared or S3 library later plugs in.

## 3. Where it lives

```python
def library_root(*, root=None, app_name="<pkg>") -> Path:
    """The library root. First match wins:
    1. ``root=`` (an explicit path, for tests and power users);
    2. the env var ``<PKG>_HOME`` (one switch for a whole shell or CI job);
    3. the platform data folder: ``$XDG_DATA_HOME/<pkg>``, else ``~/.local/share/<pkg>``
       on Linux and macOS; ``%LOCALAPPDATA%\\<pkg>`` on Windows.
    """
```

Step 3 is exactly what `config2py.get_app_folder(app_name, folder_kind="data")` already resolves (Apache-2.0, already in the fleet, depends only on `dol` and `i2`), so the implementation is a call, not new path logic; adding it as a dependency goes through `tests/test_licence_perimeter.py` as usual. On macOS it deliberately resolves to `~/.local/share`, not `~/Library/Application Support`, which is what the maintainer asked for.

Rules that come with the root (from the fleet's storage rules):

- **The root is never inside a repository.** A store's default is the policy; a default under `~/.local/share` makes committing library content a deliberate act. This matters because the library will hold private-study material (§9) and this repo is public.
- **The root holds the package's runtime data only**: `library/`, `projects/` (§7), and later `backups/<date>/`. Derived, rebuildable things (the search index, a materialisation cache) go to the *cache* folder kind (`~/.cache/<pkg>`), so deleting them loses nothing.
- **Creating the root never raises at import.** A missing or unwritable root degrades to "empty library" with a warning, never to a failed `import`.

## 4. The data model: asset, version, file

Three entities, as in every production tracker surveyed (ShotGrid: Asset → Version → PublishedFile [3]; ftrack: Asset → AssetVersion → Component [4]; Kitsu: Asset → OutputFile revision [5]).

### 4.1 Asset id

One flat, human-readable, filename-safe id: **`<kind>.<slug>`**, e.g. `character.alice-reiniger`, `environment.palace-hall`, `prop.teacup-victorian`, `motion.walk-profile-legs`, `style.reiniger`.

- Readable because agents and people type it; the kind prefix keeps two kinds from colliding on one slug and makes `find(kind=…)` cheap.
- Flat: one level. `kind` is a facet and a prefix, never a directory a user has to navigate.
- The slug is unique within a library; the library refuses a duplicate and suggests a discriminating suffix (`alice` → `alice-reiniger`). Two "Alices" in two styles are **two assets in one family** (§8), not one asset with style folders.
- Ids are persistent identifiers. Renaming is an alias (`records/<old>.json` → `{"moved_to": …}`), never a move, because projects pin them.

### 4.2 The record (identity and curation; small, mutable)

`library/records/<asset_id>.json`:

```json
{
  "id": "character.alice-reiniger",
  "kind": "character",
  "title": "Alice, silhouette",
  "family": "alice",
  "head": "v002",
  "status": "approved",
  "facets": {"style": ["reiniger"], "origin": "carved"},
  "tags": ["victorian", "dress", "profile-only"],
  "created": "2026-09-30T…", "updated": "2026-10-01T…"
}
```

What goes on the record is **curation** — judgements about the asset that can change without its content changing: the styles it suits, free tags, the family it belongs to, its approval status, which version is current. Re-tagging never makes a new version.

### 4.3 The version (content; immutable)

`library/versions/<asset_id>/<vNNN>.json`, written once and never overwritten:

```json
{
  "asset": "character.alice-reiniger",
  "version": "v002",
  "doc_kind": "character",
  "doc": { "schema_version": "0.3.0", "bones": [], "slots": [], "asset_sets": {}, "…": "the CharacterDescriptor, verbatim" },
  "files": {
    "parts/head.svg":      {"_tag": "ContentRef", "itemId": "<sha256>", "mimeType": "image/svg+xml", "size": 4211},
    "parts/head_side.png": {"_tag": "ContentRef", "itemId": "<sha256>", "mimeType": "image/png", "size": 81234}
  },
  "source": { "provider": "…", "license": "all-rights-reserved-private-study", "…": "AssetSource, an#211" },
  "derived_from": ["character.alice-reiniger@v001"],
  "affordances": {"limbs.legs": true, "limbs.arms": true, "views": ["front", "side"], "face.mouth_chart": null, "gait": ["legs", "rock"]},
  "analysers": {"character": "0.1.0"},
  "rights": {"license_class": "private", "publishable": false, "reasons": ["source: all-rights-reserved-private-study"]},
  "manifest_sha256": "<sha256 of the canonical JSON of doc, files, source, derived_from>",
  "published": "2026-10-01T…",
  "note": "re-carved side profiles"
}
```

- **`doc` is the existing descriptor, unchanged** — `CharacterDescriptor`, `PropDescriptor`, `EnvironmentDescriptor`, `StylePack`, `SoundAsset`, a voice document. The library does not define a second character format; it wraps the one `an` already versions and migrates (`an/ir/migrate.py`, keyed by document kind). Reading an old version runs the descriptor migration exactly as a project read does.
- **`files` maps the descriptor's relative paths to `ContentRef`s.** `dol.content.ContentRef` is the fleet's existing token for "bytes stored elsewhere", wire-compatible with zodal's (§10). The relative paths are the ones the descriptor already uses (`parts/…`), so checkout (§7) reproduces today's on-disk shape byte for byte.
- **What is derived from content lives on the version** (`affordances`, `rights`, `manifest_sha256`), because it changes exactly when the content does.
- **`manifest_sha256` is the asset version's content identity.** Two versions with the same manifest hash are the same content; it is also the dependency key incremental re-rendering needs (§7.4).
- **Version labels are `v001`, `v002`, …** — the studio convention [10], readable in conversation, ordered. The label is for people; the manifest hash is for machines.
- **Status is a separate axis** from the version (draft / approved / deprecated), as trackers do it [5]; it lives on the record because approving is curation.

### 4.4 The blobs (bytes; content-addressed)

`library/blobs/<aa>/<sha256>`: every file of every version, keyed by its SHA-256. Identical bytes are stored once — a part shared by v001 and v002, or by two characters, costs nothing twice — and a key can never point at changed bytes [6][11]. This is `dol.content.with_content_addressing` over a folder store; nothing new to write.

## 5. Facets, tags and affordances

Folders force each asset into one place; facets let it be in many at once [1][2]. Every searchable property is a facet with a **controlled vocabulary**, plus free `tags` for everything else.

| Facet | Values (vocabulary) | Cardinality | Where it comes from |
|---|---|---|---|
| `kind` | character, prop, environment, plane, style, voice, sound, motion, reference | one | the id prefix |
| `family` | free slug (`alice`) — the identity across styles and variants | one or none | declared (record) |
| `style` | the style-spec ids (`south_park`, `oversimplified`, `kurzgesagt`, `gilliam`, `reiniger`, `norstein`), plus user-defined sub-genres | many | declared (record) |
| `origin` | `drawn`, `procedural` (the offline factory), `dicebear`, `carved` (cut from footage or images), `traced`, `stock`, `commissioned`, `generated` | one | declared, checked against `source` |
| `license_class` | `free`, `attribution`, `private`, `unknown` (an#211's classes) | one | **derived** from `source` and the derivation chain (§9) |
| `status` | draft, approved, deprecated | one | declared (record) |
| `art` | vector, raster, mixed | one | derived from `files` |
| **affordances** | the registered capability vocabulary (below) | many | **derived** from `doc` by analysers |

### 5.1 Affordances are the point

Vision principle 2 says every behaviour declares what it **requires** and every asset says what it **affords**; the framework then applies a default to anything and proposes the alternatives that fit. The library is where *affords* is stored and searched. The design rules:

1. **Derived, never hand-maintained.** An affordance is computed from the descriptor by an *analyser* registered per asset kind (the same registration pattern as document kinds and migrations). Hand-typed capability tags drift from the art the first time a rig is edited; derived ones cannot. This is Character Animator's lesson — the layer name *is* the capability declaration [12] — and Live2D's standard parameter list [13], applied to `an`'s descriptor.
2. **One vocabulary for requirements and affordances, owned by ADR 0002.** The library's analyser for a kind *is* ADR 0002's `affordances(asset) → set[Capability]`; the keys it emits are the keys a model's `requires` names. The library stores a snapshot and indexes it; the matcher (`applicable`, `why_not`, `resolve`) is ADR 0002's, not re-implemented here. OpenAssetIO's *traits* are the same idea: a host resolves entities against sets of traits [14].
3. **Snapshotted with its analyser's version.** A version records `analysers: {kind: version}`. When an analyser improves, `reindex` recomputes affordances for old versions without touching their content (affordances are derived data, so recomputing is always safe).
4. **Asserted affordances are allowed only where nothing can derive them**, and are marked as such (`"asserted": ["silhouette_reads"]`), so a reader knows which facts were measured.

**Illustrative cut-out vocabulary** (dotted keys; values are booleans, lists or small enums). ADR 0002 owns the final names — capability names become persisted identifiers, so they are chosen there once and versioned like document kinds. Every one below maps to something `an` already reads:

| Key | Afforded when | What uses it |
|---|---|---|
| `limbs.legs`, `limbs.arms` | a leg (arm) pair is found by the names `walk` already resolves (`leg_l`/`leg_r`, `left_leg`/`right_leg`) with pivots at the hip (shoulder) | legged walk, `point`, gestures |
| `limbs.knees`, `limbs.elbows` | a two-segment limb (thigh/shin) | bent-knee gaits (an#224) |
| `views` | the keys of the `view` swap set, plus `rest_view` (front, three_quarter, side, back — `VIEWS`) | `turn`, profile walks, `_check_hidden_mouth_while_speaking` |
| `face.mouth_chart` | the vocabulary of the `viseme` set (e.g. `preston_blair`, `rhubarb`), or null | lip-sync; null → the jaw-bob/pulse default |
| `face.blink`, `face.brows`, `face.gaze`, `face.expressions` | eyelid set; brow parts; `gaze_travel`; `expression_binding` | the expression solver |
| `gait` | the gaits the rig supports (`GAITS`: legs, hem, rock) | an#224's default chain |
| `recolourable` | `colour_roles` present | StylePack roles |
| `hands` | a hands swap set | gestures |
| Environment: `planes`, `parallax`, `pan_width`, `anchors`, `ground_line` | plane count and depths; widest plane vs canvas; named anchors | camera pans, staging |
| Prop: `holdable`, `anchors` | a grip anchor | hand-held props |
| Motion clip: `requires` | the clip's own requirement set (a motion clip is Harmony's *action template*: it targets a rig contract and cannot stand alone [15]) | proposing clips that fit a character |

## 6. Search: how an agent finds "a character with legs and a side view in the Reiniger style"

```python
lib.find(kind="character", style="reiniger", affords=["limbs.legs", "views.side"], rights="publishable")
# -> [Hit(id="character.alice-reiniger", version="v002", score=1.0, missing=[]), …]
```

- **Semantics:** AND across facets, OR within one facet's values; counts per facet value are returned with the hits so an agent (or a UI) can see how to widen or narrow. `rights="publishable"` excludes `private` and `unknown`; the default is `rights="any"`, because study renders are legitimate.
- **Near misses are part of the answer.** With `near=True`, assets that fail only on affordances come back with `missing=["views.side"]` and the remedy the analyser's registry knows (`an character add-views`). That is principle 2's "help them add the structure that makes a desired model applicable", answered at search time.
- **`lib.vocabulary()`** returns every facet with its values and counts. It is what an LLM reads to turn words into a typed query.

How each way of asking resolves (principle 1, the structured ↔ semantic spectrum):

| Ask | Accepted as | Resolved by |
|---|---|---|
| (a) `find(kind=…, style=…, affords=[…])` | typed fields | the index, deterministically |
| (b) "a Reiniger character who can walk in profile" | words | an agent maps words to vocabulary terms using `lib.vocabulary()` (`walk in profile` → `limbs.legs` + `views.side`), records the mapping it used in the project's decision log, then runs (a) |
| (c) "someone who reads as a Victorian lady at thumbnail size" | a goal | (a)/(b) narrow the candidates; a `Verifier` (vision) judges the goal on each candidate's preview; a goal with no verifier is a comment, not a query |

Free text over titles and tags is a convenience on top of (a), not a replacement for facets.

**The index** is derived and rebuildable from the records and versions. v1 scans the JSON into memory — a library of a few thousand assets is milliseconds. The seam is one keyword (`index=`): SQLite FTS, or an embedding index for (b)-style similarity, replaces it without changing `find`.

## 7. How a project uses library assets

### 7.1 The reference

`AssetRef` gains one additive, omit-when-unset field:

```yaml
characters:
  - {id: alice, kind: character, ref: alice, library: "character.alice-reiniger@v002"}
```

Grammar: `<asset_id>@<version>`, where version is `vNNN`, `latest` (floating, authoring only) or `sha256:<prefix>` (exact content). Scenes without the field behave exactly as today.

### 7.2 Check-out (v1 default): copy-on-write materialisation

`checkout(project, "character.alice-reiniger@v002")`:

1. resolves the version (search path, §2) and verifies its manifest hash;
2. writes the descriptor and its files into the project's own store, at the shape `an` already reads (`assets/characters/<ref>/character.json` + `parts/…`), with an `origin` block (`{"library": "character.alice-reiniger@v002", "manifest_sha256": …}`) in the descriptor's `metadata`;
3. pins it in the project's **lockfile** (`assets.lock.json`, a new `library_lock` store in the project mall): ref → asset id, version, manifest hash.

Why check-out is the v1 default and not live reference:

- **Nothing downstream changes.** The compiler, validator and renderer keep reading the project store, including its `_root` (§1). Live reference would have to fix that leak first.
- **A project is self-contained and reproducible.** Zip it, move it to another machine, render it in a year: same bytes. The lockfile says where each asset came from.
- **`an credits` keeps working unchanged**, because `source` travels with the descriptor.
- **Copy-on-write is natural.** Editing a checked-out asset makes it a project-local fork; the descriptor's `origin` still says what it forked from. `publish` sends the edit back as a new version (`derived_from` the one it forked), which is Moho's "update the master rig" and Rive's republish, as an explicit act [9][16].

### 7.3 Reference (later): the same seam, a different strategy

The seam is one keyword on resolution: `resolve="checkout"` (default) or `resolve="reference"`. Reference mode resolves `AssetRef.library` at compile time and stages files straight from the blob store (Kitsu and Moho reference layers propagate upstream edits this way [8][16]). It needs one prerequisite, already visible in the code: the renderer's asset staging (`ASSET_SRC_PREFIX_TO_STORE` in `render.py`) must fetch bytes through the store (a `ContentRef` and `content_url`) instead of copying from `store._root`. That change is independent and worth doing anyway.

### 7.4 Upgrades and incremental re-rendering

- `latest` is resolved once, at check-out, and pinned; a render never silently picks up a new version. `outdated(project)` lists pinned assets whose library head moved (Rive's update badge [9]); `upgrade(project, ref)` re-checks-out after showing what changed.
- The pinned **manifest hash** is the dependency key ADR 0004's content-addressed build graph (on `lacing`, `nw`) needs for "adjust after a draft without re-processing everything": a shot depends on the manifest hashes of the assets it casts, so only shots casting a changed asset re-render. (Today's per-shot store is write-only and keyed by `shot.id`; a read-side cache keyed on content hashes is the stated prerequisite, CLAUDE.md pillar 11.)
- The scene's `AssetRef`s are the project's **breakdown** (casting) in production terms [17]: which assets appear in which shots. Collected across projects, they answer "where is this asset used?" before deprecating it.

### 7.5 Where projects live

Agent-made projects default to `~/.local/share/<pkg>/projects/<project_id>/` instead of a session folder; `an init <dir>` with an explicit directory keeps working anywhere. The project layout itself does not change.

## 8. Variants and versions

Production tools distinguish variation *inside* an asset from variation *between* assets. So does this design:

| Variation | Example | Mechanism | Production analogue |
|---|---|---|---|
| Inside one asset, switchable in a shot | mouths, eyelids, hands, views, expressions, costumes worn in the same film | swap channels / `asset_sets`, skins (already in the descriptor) | Spine skins [18], Harmony drawing substitutions [19], Moho switch layers [20], USD variant sets [21] |
| A new state of the same asset | re-carved profile, fixed pivot | a new **version** (`v002`) | a publish |
| A different asset with the same identity | Alice in South Park style vs Alice in Reiniger style; Alice recoloured | separate assets, same **family**, linked by `derived_from` | USD references with overrides; Kitsu shared assets |
| Motion for a rig | a profile walk cycle, a bow | a separate `motion.*` asset with `requires` | Harmony master vs action templates [15]; Spine's shared `SkeletonData` [22] |

Rules: never encode a style or a variant in a folder or in the version label; never make a swap set into separate assets (it would break in-shot switching); a family groups, it never inherits — each member is a complete asset, so deleting one never breaks another.

## 9. Provenance and rights on every asset

The library adopts an#211's model and closes the gaps the 2026-09-30 sessions hit (one `source` per character, rights in prose):

1. **Every version carries `source: AssetSource`**, and every file may carry its own (`Attachment.source`, `Plane.source` already exist). An asset with no source is published as `license_class: unknown`, never rejected — but it is visible as unknown everywhere.
2. **`derived_from`** records lineage in PROV terms (`wasDerivedFrom` [23]): a carved character derives from its footage (recorded by URL and SHA-256 in `source`, never stored in the library); a recolour derives from its original; v002 derives from v001.
3. **Rights roll up to the most restrictive value** across the asset's own source, its files' sources and everything it derives from: `private` beats `unknown` beats `attribution` beats `free` — a derivative inherits the obligations of its sources, as Creative Commons' attribution and share-alike terms do [24]. The result is stored as `rights: {license_class, publishable, reasons}` on the version, and `publishable` is false for `private` and `unknown`.
4. **Licence strings stay `an`'s existing normalised codes** (`normalise_license`, `PRIVATE_STUDY`, `PUBLIC_DOMAIN`), which already align with SPDX identifiers [25] for the open licences; the private-study code reads as SPDX's `LicenseRef-` escape for unlisted terms. No new licence vocabulary.
5. **Enforcement points:** `find(rights="publishable")`; `an credits` on any project (unchanged); and a hard refusal to copy `private` or `unknown` versions into any library other than the local user library (a team share, a seed library, a remote bucket) without an explicit override. Private-study material never leaves the machine by default.
6. **Reference material is an asset kind too** (`reference.*`: model sheets, turnaround sheets, contact sheets of source frames), with the same rights, because a model sheet carved from a film is as private as the puppet carved from it.

Provenance rule, restated for this repo: the library root is outside every repository; the repo's tests use synthetic fixtures only; a shipped seed library may contain only `free` or `attribution` assets with complete sources.

## 10. The facade: stores, keys, and the road to S3

The library is a mall, like the project:

```python
lib = build_library_mall(root=None)   # root resolved as in §3
lib["records"]   # MutableMapping[str, dict]   key "<asset_id>"           -> records/<asset_id>.json
lib["versions"]  # MutableMapping[str, dict]   key "<asset_id>@<vNNN>"    -> versions/<asset_id>/<vNNN>.json (write-once)
lib["blobs"]     # MutableMapping[str, bytes]  key "<sha256>"             -> blobs/<aa>/<sha256>   (dol.content CAS)
```

- **Real `dol` stores this time** (folder stores with JSON codecs and key transforms), not hand-written ones, so each store is replaced by injection: `build_library_mall(records=…, versions=…, blobs=…)`, the same `**overrides` pattern as `build_project_mall`.
- **To S3 later:** `blobs` becomes an S3-backed `MutableMapping[str, bytes]`, `records`/`versions` an S3 JSON store or a small database. Business logic only ever sees the mapping interface and `ContentRef`s; a fetchable URL is minted on demand with `dol.content.content_url` (a presigned URL is never baked into a record, so persisted manifests never expire). A local read-through cache under the cache folder keeps renders fast.
- **Integrity:** `versions` refuses to overwrite a key; `records` updates its `head` only to a version that exists; blobs are verified against their key on read when cheap.
- **The functions are the API; surfaces are thin.** `add`, `publish`, `find`, `vocabulary`, `show`, `checkout`, `outdated`, `upgrade`, `reindex`, `import_project_assets` are plain functions over the mall. The CLI (`an library …`, or `<pkg> library …`) dispatches to them programmatically as `an.tools` already does; the MCP surface — the one agents will use most — exposes the same functions.

## 11. Core or genre package?

The *mechanism* — records, immutable versions, the blob store, facets, the rights roll-up, check-out — says nothing about rigs, faces or mouths. A data-viz or math-viz genre needs the same library for its glyph sets and templates. By principle 3 and ADR 0001 it belongs in the **core** (`an.library`), parametrised by the app name that picks its root.

The *vocabulary* is genre-specific and registers from the genre package: the cut-out asset kinds' analysers (legs, views, mouth charts), the style facet's values (the style specs), the `motion.*` requirement keys. The cut-out package instantiates its library at `~/.local/share/<pkg>`.

## 12. Migrating the 2026-09-30 session assets (described, not done)

A later issue does this; the design must make it straightforward. The source is three per-style session folders, each with a mall-shaped or nearly mall-shaped `assets/` or `project*/assets/`, a free-form `provenance.json`, and v1/v2 copies.

1. **Import from projects, not from scratch folders.** `import_project_assets(project_dir, *, style=…, family_map=…, origin=…)` publishes each character, prop, environment, sound and style in a project mall. The second-round projects (`project_v2/`) are the most complete; the first round becomes `v001` and the second `v002` of the same asset, with `derived_from` linking them — two copies become two versions.
2. **Map each `provenance.json` into `AssetSource` per asset and per part.** The three schemas differ (`carved_parts{path: …}` in one, a per-asset `AssetSource` dict in another, an `assets[{asset, from, how, license}]` list in the third), so the importer takes a small per-session mapping function; nothing guesses. Footage is recorded by URL and SHA-256, never imported. Every footage-derived asset classifies as `private`.
3. **Not imported:** carving scratch, intermediate frames, non-mall geometry files (they are working files, not publishes), source videos, final renders. Contact sheets that document what was carved may be imported as `reference.*` assets, private.
4. **Facets on import:** `style` from the session folder, `family` from the character name (`alice`, `bob`), `origin: carved`; affordances are derived, not mapped.
5. **Acceptance:** for each migrated project, `an credits` reports the same classes before and after, and a re-render from a fresh check-out matches the original project's render.

## 13. Glossary — the maintainer's words and the production terms

| Plain words | Production term | In this design |
|---|---|---|
| my stash of reusable stuff | asset library | the library (§2) |
| a video I'm making | production / scene (Harmony), shot (trackers) | a project |
| a character, prop or background | asset (character, prop, set/environment) | an asset, keyed `<kind>.<slug>` |
| the pieces of a character | parts → attachments in slots on bones | `doc` + `files` |
| how the pieces connect | rig / puppet; pivots; skeleton | the descriptor's `bones`, `slots` |
| a saved state of an asset | publish, version (v001…) | an immutable version |
| the same character drawn another way | variant (in-asset), or a sibling asset in a family | swap sets/skins; `family` |
| "what it can do" | affordances / traits / capabilities | derived `affordances` |
| "what a move needs" | requirements | a behaviour's `requires` |
| labels | facets (controlled vocabulary) and tags | §5 |
| where it came from, can I publish it | provenance, rights, licence class | `source`, `derived_from`, `rights` |
| the reference drawings | model sheet, turnaround, expression sheet, mouth chart | `reference.*` assets; `views`, `face.mouth_chart` |
| which assets a video uses | breakdown / casting | the project's `AssetRef`s and lockfile |
| a move saved for reuse | action template / animation clip | a `motion.*` asset |

## 14. Decisions for the maintainer

1. **One root per genre (`~/.local/share/<pkg>`) or one shared root for every genre built on `an`** (`~/.local/share/an`, with the genre as a facet)? The design works either way; a shared root lets a data-viz video reuse a cut-out prop.
2. **Check-out as the v1 default** (copy-on-write into the project, pinned) rather than live reference. Recommended for reproducibility and because the renderer's `_root` staging would otherwise have to change first.
3. **Readable ids (`character.alice-reiniger`) rather than opaque ids (ULIDs).** Recommended for agents and conversation; costs a uniqueness check and alias records on rename.
4. **Agent-made projects move to `~/.local/share/<pkg>/projects/`** instead of session folders.
5. **`config2py` as a new dependency** for the root resolution (Apache-2.0), versus ~20 lines of the same XDG logic inline.

## REFERENCES

1. [The Discipline of Organizing: Faceted Classification](https://berkeley.pressbooks.pub/tdo4p/chapter/faceted-classification/)
2. [Hedden: Faceted Classification and Faceted Taxonomies](https://www.hedden-information.com/faceted-classification-and-faceted-taxonomies/)
3. [Flow PT community: Best practices for PublishedFile and Version entities](https://community.shotgridsoftware.com/t/best-practices-for-publishedfile-and-version-entities/18785)
4. [ftrack Python API: Publishing versions](https://ftrack-python-api.rtd.ftrack.com/en/2.1.2/example/publishing.html)
5. [Gazu (Kitsu client): Specifications](https://gazu.cg-wire.com/specs.html)
6. [Pro Git: Git Internals — Git Objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)
7. [Harmony 22 Premium: About the Library & Templates](https://docs.toonboom.com/help/harmony-22/premium/library/about-library.html)
8. [Kitsu docs: Asset Library](https://mintlify.wiki/cgwire/kitsu/assets/asset-library)
9. [Rive docs: Libraries](https://rive.app/docs/editor/libraries)
10. [CAVE Academy: Assets Published File Naming Convention](https://caveacademy.com/wiki/general/published-file-naming-convention/assets-published-file-naming-convention/)
11. [IPFS docs: Immutability](https://docs.ipfs.tech/concepts/immutability/)
12. [Wikipedia: Adobe Character Animator](https://en.wikipedia.org/wiki/Adobe_Character_Animator)
13. [Live2D: Standard Parameter List](https://docs.live2d.com/en/cubism-editor-manual/standard-parameter-list/)
14. [OpenAssetIO: Entities, Traits and Specifications](http://docs.openassetio.org/OpenAssetIO/entities_traits_and_specifications.html)
15. [Harmony 20 Premium: About Templates](https://docs.toonboom.com/help/harmony-20/premium/library/about-template.html)
16. [Moho Forum: reference layer](https://lostmarble.net/forum/viewtopic.php?t=34787)
17. [Kitsu docs: Breakdown](https://cgwire-kitsu.mintlify.app/assets/breakdown)
18. [Spine User Guide: Skins](https://en.esotericsoftware.com/spine-skins)
19. [Harmony 20 Premium: Naming Drawing Substitutions](https://docs.toonboom.com/help/harmony-20/premium/rigging/name-draw-substitution.html)
20. [Moho manual: Switch Layers](https://www.lostmarble.com/moho/manual/switch_layers.html)
21. [OpenUSD: Authoring Variants](https://openusd.org/release/tut_authoring_variants.html)
22. [Spine: Using Runtimes](http://en.esotericsoftware.com/spine-using-runtimes/)
23. [W3C: PROV-O, The PROV Ontology](https://www.w3.org/TR/prov-o/)
24. [Creative Commons: About CC Licenses](https://creativecommons.org/share-your-work/cclicenses/)
25. [SPDX 3.0.1: License Expressions](https://spdx.github.io/spdx-spec/v3.0.1/annexes/spdx-license-expressions/)
