# How cut-out and rigged 2D productions organise reusable asset libraries

Research report, 2026-10-01. It feeds the design in [`misc/docs/asset_library_design.md`](../asset_library_design.md) and its ADR in [`misc/docs/adr/`](../adr/). It builds on what the repo already had and does not repeat it: tool-level notes on Spine skins and USD composition arcs are in `report 2 - Animation interchange formats…` (§"USD's composition arcs…", Patterns 4 and 5), the character on-disk shape and the `promote` workflow are in `Real Character Art for an…` (§1.2, §5), and the per-style feature gaps are in `cutout_styles_research.md`. None of those covered how a production organises a *library* of assets across projects. This report does.

**Sources and limits.** Mostly official documentation (Toon Boom, Esoteric Software, Live2D, Rive, Kitsu, the USD working group, OpenAssetIO, W3C, IPTC, SPDX, schema.org). Two Adobe help pages refused automated access, so the Character Animator details come from search excerpts of those pages and from secondary sources; they are marked. The books in §7 were checked against publisher and catalogue pages only, not their full text, and the report says so where it matters.

## Summary and recommendation

Every production tool and tracker surveyed converges on the same small set of ideas. Build the library on them:

1. **Scopes, not one pool.** Harmony Server shares library items at four scopes (Symbols: one project; Job; Environment; an optional Global folder), each visible to everything under it [1]. Kitsu adds a cross-production Asset Library over per-production assets [45]. For `an`: project-local, then the user's library, then shipped or team libraries.
2. **Structure separate from motion.** Harmony's *master template* holds the whole rig with its drawings and pose keys; an *action template* holds keyframes and exposures only and "cannot function independently" of its master [2]. Spine shares a stateless `SkeletonData` across instances [19]. Rigs and motion clips are separate asset kinds, and a clip declares the rig contract it targets.
3. **Variants are swaps into named slots.** Spine skins map slot → placeholder → attachment, placeholders are named for what they represent ("head", not "red head"), and several skins combine at run time [17][20][21]. Harmony drawing substitutions [5], Moho switch layers [12] and Character Animator swap sets [29] are the same idea.
4. **Capability by convention.** Character Animator rigs a puppet automatically from layer names ("Left Eye", "Mouth", "Left Profile") [26][27]; Live2D publishes a standard parameter list so motions are reusable across models [23]; OpenAssetIO resolves entities against sets of *traits* [48]. An agent can answer "has legs, has a side view" from a controlled vocabulary derived from the rig, without looking at pixels.
5. **The turnaround and the mouth chart are data.** Model sheets fix views, expressions and hands [33][34]; Harmony prefixes substitution names by view (`f`, `q`, `s`) [5]; the Preston Blair mouth chart is about ten named shapes [35][36]. Record which views and which viseme vocabulary a rig implements, as queryable facts.
6. **Asset, version, file are three things.** ShotGrid (Asset, Version, PublishedFile) [40][41], ftrack (Asset, AssetVersion, Component) [42] and Kitsu (Entity, OutputFile with a revision, WorkingFile) [43] all separate a stable identity from immutable numbered publishes (v001, v002…) and from the files a publish contains. Consumers pin a version and opt in to updates (Rive Libraries) [31].
7. **Reference or detach, explicitly.** Moho reference layers, Rive components and Kitsu shared assets propagate upstream edits [15][30][45]; Rive also lets a consumer *detach* a copy [31]. A project records which it did.
8. **Content-address the bytes, name the identities.** Git and IPFS store bytes by hash, so identical bytes are stored once and any change gives a new address [73][74]; names and version pointers sit on top.
9. **Facets, not folders.** A faceted classification lets one item sit in several places at once; a folder hierarchy forces one [71][72]. Use controlled vocabularies per facet.
10. **Provenance and rights are required fields.** An SPDX licence expression (`LicenseRef-…` for unlisted terms) [79]; schema.org `creator`, `copyrightHolder`, `isBasedOn`, `usageInfo` [81][82]; PROV `wasDerivedFrom` / `wasAttributedTo` [75]; IPTC's data-mining permission [78]. Publishability is the most restrictive value along the derivation chain, and *unknown* is not publishable.
11. **Approval status is its own axis**, separate from the version number [43][44].
12. **Each asset kind publishes a manifest contract.** USD-WG asset guidelines require a root file, a `defaultPrim`, a `kind` and standard variant sets [46]; Live2D's `model3.json` lists the referenced files and parameter groups (EyeBlink, LipSync) [22]; Rive's view models are "explicit contracts" [31].

## 1. Toon Boom Harmony, Storyboard Pro and Producer

- **Library and templates.** The library is "a storage centre for all production assets"; its items are *templates* [1]. A `.tpl` is a folder on disk [4].
- **Scopes on Harmony Server.** Symbols (one project), Environment (every job and scene in it), Job (every scene in it), and an optional Global library folder visible everywhere [1].
- **Master vs action templates.** A cut-out character's master template "stores the entire rig, structure, drawings, and keyframes of the different poses of your puppet into a single asset", created from the Node view [2]; the docs recommend collapsing the rig under a master peg and grouping it before storing [3]. Action templates come from the Timeline and contain "mainly keyframes and drawing exposures"; import the master first, then apply the action [2]. Single-keyframe action templates hold a head or body's views (front, three-quarter, side), swapped in to turn the character [8].
- **Rig breakdown.** A rig is "a template based on your character's model" with each movable part on its own layer in a hierarchy [6].
- **Drawing substitutions.** Alternative drawings on a layer (mouths, hands), named by view prefix plus number (`f1, f2, s1, q1…`) because the list sorts alphabetically [5].
- **Server hierarchy.** Environment (a production or series) → Job (episode or sequence) → Scene → Element → Drawing; job names are unique and scene names carry environment and job prefixes [7].
- **Storyboard Pro** libraries are on disk, shareable between projects, and hold characters, sets, props, layers, panels, audio, video, 3D models and animations in subfolders [11].
- **Producer** is a web tracker that "tracks asset creation from start to finish" [9]; trade press describes tag-based search for assets linked to shots [10]. No field-level schema was found in Toon Boom's own docs.

## 2. Moho

- **Switch layers** show one sub-layer at a time; they carry lip-sync (one sub-layer per mouth shape) and can be driven by a `MohoSwitch1` data file of frame/sub-layer pairs [12].
- **Smart bones** drive keyframed actions by a bone's rotation; a *dial* is a control bone outside the skeleton (head turns, blinks) [13].
- **Reuse across scenes.** Reference layers stay linked to their original, and a whole file can be imported by reference so a master-rig edit reaches every project using it [15][14].
- **Content packs** are ordinary saved `.moho` files (e.g. 8 rigged characters with smart bones) [16]. No library metadata model was found.

## 3. Spine

- **Skeleton JSON** [18]: `skeleton`, `bones`, `slots` (name, bone, colour, setup-pose attachment, blend), constraints (`ik`, `transform`, `path`), `skins`, `events`, `animations`. Attachment types: region, mesh, linkedmesh, boundingbox, path, point, clipping. Skins map `slotName → {placeholderName → attachment}`; a `default` skin holds unskinned attachments and lookups fall back to it.
- **Skins** [17] hold attachments (and skin-specific bones and constraints) active only while the skin is visible. Two strategies: *variants* (duplicate a skin, replace attachments) and *mix-and-match* (one skin per item, several visible at once). Skin-specific bones let one skeleton and its animations serve different proportions.
- **Runtime** [19]: `SkeletonData` is shared and stateless; an atlas packs images; an `AttachmentLoader` resolves names to regions. Skins compose at run time into a custom avatar [20][21].

## 4. Live2D Cubism, Adobe Character Animator, Rive

- **Live2D.** `model3.json` is the manifest: required `Moc` and `Textures`; optional physics, pose, display info, user data, motion sync, expressions and grouped motions; `Groups` such as EyeBlink and LipSync map to parameter ids [22]. Expressions (`exp3.json`) are parameter overrides with an Add/Multiply/Overwrite blend [24]. The **standard parameter list** exists to make "replace, reuse, etc." possible (`ParamAngleX` −30..30, `ParamEyeLOpen` 0..1, `ParamMouthOpenY`, …) [23].
- **Character Animator.** Layered PSD/AI files become *puppets*; basic rigging is "fully automatic based on specific layer names" [26]. Tags apply to layers and handles; a `+` prefix makes a layer move independently [27][28] (from search excerpts; the pages refused automated access). Head Turner views: Left Profile, Left Quarter, Frontal, Right Quarter, Right Profile, Upward, Downward, at least two required [27]. *Swap sets* group triggers so exactly one child is visible [29]. The layer name is the capability declaration. Viseme tag names were found only in a secondary source [83].
- **Rive.** Each artboard has its own hierarchy, animations and state machines [32]. *Components* are reusable artboards whose instances keep overrides while source edits propagate [30]. *Libraries* publish components and view models across a project's files: each republish is a new version, consumers see an update badge and can stay pinned, a component can be detached, and an export can bundle everything into one file [31].

## 5. Studio pipeline practice

- **Model sheets and turnarounds** keep a character "on model": head and body rotations, hands, basic expressions, annotations [33]; turnaround views are front, 3/4, profile, 3/4 back, back [34].
- **Mouth charts.** The Preston Blair set, as encoded in Papagayo: AI, O, E, U, etc, L, WQ, MBP, FV, rest [35][36].
- **Naming and versions.** CAVE Academy's published-file pattern is `<SHOW>_<assetType>_<assetName>_<step>_<variant>_<lod>_<version>.<ext>` (e.g. `…_character_yuki_model_prim_default_lod0_v001.mb`), variant as a name field (`default`, `damaged`) [37].
- **ShotGrid / Flow Production Tracking.** Asset types default to Character, Environment, Matte Painting, Prop, Vehicle [39]; the Toolkit folder schema groups by asset type with a work area per asset and step [38]; a publish records `version_number` and `published_file_type` [40]; a Version links to many PublishedFiles [41].
- **ftrack.** Asset (name, type) → AssetVersion (the published unit) → Components (files, as metadata) placed in Locations [42].
- **Kitsu / Zou.** Project, AssetType, Asset, Episode, Sequence, Shot, Task, TaskStatus, PreviewFile, OutputFile (with a revision), WorkingFile, plus metadata descriptors for custom fields [43]. *Breakdown/casting* records which assets appear in which shots [44]. The global Asset Library shares assets across productions; updates propagate, and removing an asset from the library does not delete the original [45].
- **USD** as the variant and reference model. An asset has a root file with a `defaultPrim`, a `kind` (component, assembly, group), heavy data behind payloads, relative paths, and at least two standard variant sets [46]; a prim carries several independent variant sets [47].
- **OpenAssetIO.** Entity references are opaque URIs owned by the asset manager; hosts `resolve` them against sets of *traits*, and a specification is a composition of traits [48]. This is a direct model for query by capability.
- **Academic pipeline work.** "openPipeline" (SIGGRAPH 2007) covers teaching and implementing pipelines, including data management [70] (abstract only read).

## 6. Productions

- **South Park.** Only the pilot was physically cut from construction paper; that paper "was then scanned into a massive computer database, which animators now use to create the show", animated mostly in Maya [49][50]. *6 Days to Air* (2011) documents the six-day cycle [51]. No first-party description of how the parts library is structured was found.
- **OverSimplified.** "After Effects for animation, Photoshop for asset creation"; applicants download provided asset files [52]. Nothing verifiable on reuse across episodes.
- **Cartoon Saloon.** *The Breadwinner*'s story-world sequences used Moho rigs with "hundreds of separate layers", composited in Nuke [54][53].
- **Lotte Reiniger.** In her own words: "silhouette marionettes … cut out of black cardboard and thin lead, every limb being cut separately and joined with wire hinges", laid on a glass table lit from below so the hinges disappear [56]; figures of 20–50 pieces, backlit glass planes [57]. Her book: *Shadow Theatres and Shadow Films* (Batsford, 1970) [58]. Her asset unit is the jointed figure, and the joint (pivot) belongs to the asset.
- **Terry Gilliam.** On *Do It Yourself Film Animation Show* (1974) he cut old photographs and illustrations at the joints and moved the pieces under the camera, "the easiest form of animation I know" [59]; sources were mostly Victorian photographs and engravings mixed with his own art [61][60]. A library must record each clipping's original source.
- **Yuri Norstein.** Glass planes about 25–30 cm apart moving laterally and in depth; the hedgehog is layered celluloid with separately attached details; the fog is tracing paper [63], from Francheska Yarbusova's designs [62].
- **Hanna-Barbera limited animation.** Head cels reused with only mouth cels swapped; collars separated the head onto its own cel; drawings held for two or three frames [64]; *Ruff and Reddy* ran about $2,700 per five minutes against $45,000 at MGM by reusing cels [65]. This is where "part swap over a held body" comes from.

## 7. Books

- Winder, Miller-Zarneke and Dowlatabadi, *Producing Animation* (3rd ed.): chapters on the production plan, pre-production, production and "Tracking Production", with sample tracking charts [66]. The asset-tracking text itself was not seen.
- Mark Simon, *Producing Independent 2D Character Animation* (Focal, 2003): production forms and organisational tips [67]; whether it discusses character libraries is unverified.
- Tony White, *How to Make Animated Films*: includes cut-out tutorials [68].
- Richard Williams, *The Animator's Survival Kit* [69], and Whitaker and Halas, *Timing for Animation*: craft references on movement, not sources on asset management.

## 8. Digital asset management in general

- **Facets.** Ranganathan's faceted classification lets an object appear in several places; facets may themselves be hierarchical; facet values come from controlled vocabularies [71][72].
- **Content addressing.** Git is "a content-addressable filesystem" of blobs, trees, commits and tags named by hash [74]; an IPFS CID changes if any byte changes [73].
- **Provenance and rights.** PROV-O: Entity, Activity, Agent; `wasGeneratedBy`, `wasDerivedFrom`, `wasAttributedTo`, `used` [75]. C2PA: a signed manifest with actions and *ingredients* (the source assets) [76]. IPTC: copyright notice, web statement of rights, licensor, usage terms, and since 2023.1 a Data Mining field [77][78]. SPDX: short identifiers and `AND`/`OR`/`WITH` expressions, `LicenseRef-<id>` for unlisted terms [79]. Creative Commons: six licences from BY, SA, NC, ND, plus CC0 and the Public Domain Mark (a label, not a licence) [80]. schema.org CreativeWork: `license`, `creator`, `copyrightHolder`, `isBasedOn`, `creditText`, `usageInfo`, `acquireLicensePage` [81][82].
- **What decides private-study vs publishable:** the licence expression; the `isBasedOn`/`wasDerivedFrom` chain and each source's licence; holder and credit text; NC/ND restrictions; the data-mining permission; a provenance class (own work, commissioned, public domain, study of a protected work, unknown). Publishability is the most restrictive value along the chain; unknown is not publishable.

## Glossary (production term → meaning)

- **Asset**: a reusable, separately tracked production element (character, prop, set, FX), as opposed to a shot [39][43]. **Asset type**: its category [39].
- **Prop**: an object a character handles or that dresses a set [39]. **Set / environment / background**: where a shot happens, often split into planes for multiplane parallax [57][63].
- **Rig / puppet**: a character broken into separately movable parts in a hierarchy [6]. **Bone**: a transform node driving attached art [12][18]. **Slot**: a holder on a bone showing one attachment at a time and setting draw order [18]. **Attachment**: the art in a slot [18]. **Skin**: a named set of attachments (and optionally bones and constraints) filling slots; skins combine [17].
- **Template (.tpl)**: a reusable package in a Harmony library [1]. **Master template**: a whole rig with drawings and pose keys; **action template**: keyframes and exposures only [2]. **Symbol**: a project-scoped library item [1].
- **Drawing substitution** (Harmony) / **switch layer** (Moho) / **swap set** (Character Animator): show one of several drawings in one place — replacement animation [5][12][29]. **Smart bone / dial**: a bone whose rotation drives a stored action [13]. **Reference layer**: a linked copy that follows its original [15]. **Tag**: a semantic role on a layer, often from its name [28]. **Parameter**: a named scalar control with a range [23].
- **Component** (Rive): a reusable artboard instance [30]. **Library** (Rive): a versioned set of published components consumers can pin [31].
- **Model sheet**: the reference that keeps a character on model [33]. **Turnaround**: the character at fixed angles (front, 3/4, side, 3/4 back, back) [34]. **Expression sheet**: a model sheet of facial expressions [33]. **Mouth chart / phoneme set**: the named mouth shapes (visemes) [35]. **Viseme**: the mouth shape for one or more phonemes [35].
- **Variant**: an alternate version of the same asset identity (costume, damage, level of detail); **variant set**: a named axis of mutually exclusive choices [46][47].
- **Publish**: an immutable, registered release of an asset's files [40]. **Version**: a numbered, reviewable iteration (v001…) [37][41]. **Published file / component / output file**: a file record inside a version [41][42][43].
- **Breakdown / casting**: the record of which assets appear in which shots [44].
- **Entity reference / trait**: an opaque asset URI, and a capability-shaped query unit [48].
- **Provenance**: where an asset came from and how it was made [75][76]. **Licence expression**: an SPDX string for its terms [79].

## REFERENCES

1. [Harmony 22 Premium: About the Library & Templates](https://docs.toonboom.com/help/harmony-22/premium/library/about-library.html)
2. [Harmony 20 Premium: About Templates](https://docs.toonboom.com/help/harmony-20/premium/library/about-template.html)
3. [Harmony 22 Premium: Creating Templates](https://docs.toonboom.com/help/harmony-22/premium/library/create-template.html)
4. [Harmony 22 Premium: How to Create and Use Templates](https://docs.toonboom.com/help/harmony-22/premium/getting-started/library.html)
5. [Harmony 20 Premium: Naming Drawing Substitutions](https://docs.toonboom.com/help/harmony-20/premium/rigging/name-draw-substitution.html)
6. [Harmony 22 Premium: How to Rig a Cut-out Character](https://docs.toonboom.com/help/harmony-22/premium/getting-started/character-building.html)
7. [Harmony 21 Premium: About the Database Structure in Harmony Server](https://docs.toonboom.com/help/harmony-21/premium/project-creation/about-database-structure.html)
8. [Harmony 12.1 Advanced: Using Action Templates](https://docs.toonboom.com/help/harmony-12/advanced/Content/_CORE/_Workflow/022_Cut-out_Animation/060_H1_Using_Action_Templates.html)
9. [Toon Boom Producer product page](https://www.toonboom.com/products/producer)
10. [AWN: Toon Boom Rebrands, Unveils Toon Boom Producer](https://www.awn.com/news/toon-boom-rebrands-unveils-toon-boom-producer)
11. [Storyboard Pro 22: About Libraries](https://docs.toonboom.com/help/storyboard-pro-22/storyboard/library/about-library.html)
12. [Moho manual: Switch Layers](https://www.lostmarble.com/moho/manual/switch_layers.html)
13. [Lesterbanks: Tips for Working With Smart Bones in Moho](https://lesterbanks.com/2018/12/tips-smart-bones-moho/)
14. [Moho 13 Changelog (community mirror)](https://github.com/jolexxa/moho-docs/blob/main/docs/Moho%2013%20Changelog.md)
15. [Moho Forum: reference layer](https://lostmarble.net/forum/viewtopic.php?t=34787)
16. [Moho Characters Content Pack](https://moho.lostmarble.com/products/characters-content-pack)
17. [Spine User Guide: Skins](https://en.esotericsoftware.com/spine-skins)
18. [Spine: JSON export format](http://en.esotericsoftware.com/spine-json-format)
19. [Spine: Using Runtimes](http://en.esotericsoftware.com/spine-using-runtimes/)
20. [spine-unity: Mix and Match](http://en.esotericsoftware.com/spine-unity-mix-and-match)
21. [Spine Runtimes Guide: Runtime Skins](https://esotericsoftware.com/spine-runtime-skins)
22. [Live2D CubismSpecs: model3.json](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/model3.json.md)
23. [Live2D: Standard Parameter List](https://docs.live2d.com/en/cubism-editor-manual/standard-parameter-list/)
24. [Live2D CubismSpecs: exp3.json](https://github.com/Live2D/CubismSpecs/blob/master/FileFormats/exp3.json.md)
25. [Live2D: File Types and Extensions](https://docs.live2d.com/en/cubism-editor-manual/file-type-and-extension/)
26. [Wikipedia: Adobe Character Animator](https://en.wikipedia.org/wiki/Adobe_Character_Animator)
27. [Adobe: Prepare artwork in Character Animator](https://helpx.adobe.com/adobe-character-animator/using/prepare-artwork.html) (refused automated access; search excerpts)
28. [Adobe: Behaviors and tags](https://helpx.adobe.com/adobe-character-animator/using/behaviors-and-tags.html) (refused automated access; search excerpts)
29. [Adobe: Triggering and controlling puppets](https://helpx.adobe.com/adobe-character-animator/using/triggering-and-controlling-puppets.html)
30. [Rive docs: Components](https://rive.app/docs/editor/fundamentals/components)
31. [Rive docs: Libraries](https://rive.app/docs/editor/libraries)
32. [Rive docs: Artboards](https://rive.app/docs/editor/fundamentals/artboards)
33. [Wikipedia: Model sheet](https://en.wikipedia.org/wiki/Model_sheet)
34. [CGWire blog: Character Sheets, the Blueprint for Consistent Animation](https://blog.cg-wire.com/character-sheet-animation/)
35. [Gary C. Martin: Preston Blair phoneme series](https://www.garycmartin.com/mouth_shapes.html)
36. [Papagayo: phonemes_preston_blair.py](https://github.com/aziagiles/papagayo/blob/master/phonemes_preston_blair.py)
37. [CAVE Academy: Assets Published File Naming Convention](https://caveacademy.com/wiki/general/published-file-naming-convention/assets-published-file-naming-convention/)
38. [tk-config-default2: asset.yml schema](https://github.com/shotgunsoftware/tk-config-default2/blob/v1.2.12/core/schema/project/assets/asset_type/asset.yml)
39. [ShotGrid python-api: API Reference](https://developers.shotgridsoftware.com/python-api/reference.html)
40. [tk-multi-publish2: Publish API](https://developers.shotgridsoftware.com/tk-multi-publish2/api.html)
41. [Flow PT community: Best practices for PublishedFile and Version entities](https://community.shotgridsoftware.com/t/best-practices-for-publishedfile-and-version-entities/18785)
42. [ftrack Python API: Publishing versions](https://ftrack-python-api.rtd.ftrack.com/en/2.1.2/example/publishing.html)
43. [Gazu (Kitsu client): Specifications](https://gazu.cg-wire.com/specs.html)
44. [Kitsu docs: Breakdown](https://cgwire-kitsu.mintlify.app/assets/breakdown)
45. [Kitsu docs: Asset Library](https://mintlify.wiki/cgwire/kitsu/assets/asset-library)
46. [USD-WG: Asset Structure Guidelines](https://github.com/usd-wg/assets/blob/main/docs/asset-structure-guidelines.md)
47. [OpenUSD: Authoring Variants](https://openusd.org/release/tut_authoring_variants.html)
48. [OpenAssetIO: Entities, Traits and Specifications](http://docs.openassetio.org/OpenAssetIO/entities_traits_and_specifications.html)
49. [South Park Studios FAQ: Do you still use construction paper?](https://www.southparkstudios.com/news/712d55/faq-do-you-still-use-construction-paper-to-animate-the-show)
50. [South Park Studios: Do you hand draw every scene?](https://www.southparkstudios.com/news/78zs1w/fan-question-do-you-hand-draw-every-scene)
51. [Wikipedia: 6 Days to Air](https://en.wikipedia.org/wiki/6_Days_to_Air)
52. [OverSimplified: Create](https://www.oversimplified.tv/create)
53. [Moho: About (Cartoon Saloon testimonials)](https://moho.lostmarble.com/pages/about)
54. [AWN: Bringing the Story World Sequences of The Breadwinner to Life](https://www.awn.com/animationworld/all-details-bringing-story-world-sequences-breadwinner-life)
55. [Wikipedia: Cartoon Saloon](https://en.wikipedia.org/wiki/Cartoon_Saloon)
56. [BFI: Scissors make films — Lotte Reiniger on creating her animations](https://www.bfi.org.uk/sight-and-sound/features/scissors-make-films-lotte-reiniger-creating-her-magical-animations)
57. [Wikipedia: Lotte Reiniger](https://en.wikipedia.org/wiki/Lotte_Reiniger)
58. [Internet Archive: Shadow theatres and shadow films (Reiniger)](https://archive.org/details/shadowtheatressh0000rein)
59. [Open Culture: Terry Gilliam Reveals the Secrets of Monty Python Animations (1974)](https://www.openculture.com/2014/07/terry-gilliam-reveals-the-secrets-of-monty-python-animations.html)
60. [Animation Studies: The Fabulous Adventures of Mystimation](https://blog.animationstudies.org/?p=4032)
61. [Wikipedia: Terry Gilliam](https://en.wikipedia.org/wiki/Terry_Gilliam)
62. [Animation Obsessive: A Guide to Yuri Norstein](https://animationobsessive.substack.com/p/a-guide-to-yuri-norstein-hedgehog)
63. [Wikipedia: Hedgehog in the Fog](https://en.wikipedia.org/wiki/Hedgehog_in_the_Fog)
64. [Illustration History: Hanna-Barbera, The Architects of Saturday Morning](https://www.illustrationhistory.org/essays/hanna-barbera-the-architects-of-saturday-morning)
65. [Wikipedia: The Ruff and Reddy Show](https://en.wikipedia.org/wiki/The_Ruff_and_Reddy_Show)
66. [Routledge: Producing Animation 3e](https://www.routledge.com/Producing-Animation-3e/Winder-Miller-Zarneke-Dowlatabadi/p/book/9781138591264)
67. [Internet Archive: Producing independent 2D character animation (Simon)](https://archive.org/details/producingindepen0000simo)
68. [ScienceDirect: How to Make Animated Films (White)](https://www.sciencedirect.com/book/9780240810331/how-to-make-animated-films)
69. [Wikipedia: The Animator's Survival Kit](https://en.wikipedia.org/wiki/The_Animator%27s_Survival_Kit)
70. [SIGGRAPH History: openPipeline (O'Neill, Mavroidis, Ho)](https://history.siggraph.org/learning/openpipeline-teaching-and-implementing-animation-production-pipelines-in-an-academic-setting-by-oneill-mavroidis-and-ho/)
71. [The Discipline of Organizing: Faceted Classification](https://berkeley.pressbooks.pub/tdo4p/chapter/faceted-classification/)
72. [Hedden: Faceted Classification and Faceted Taxonomies](https://www.hedden-information.com/faceted-classification-and-faceted-taxonomies/)
73. [IPFS docs: Immutability](https://docs.ipfs.tech/concepts/immutability/)
74. [Pro Git: Git Internals — Git Objects](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects)
75. [W3C: PROV-O, The PROV Ontology](https://www.w3.org/TR/prov-o/)
76. [C2PA Technical Specification 2.2](https://spec.c2pa.org/specifications/specifications/2.2/specs/_attachments/C2PA_Specification.pdf)
77. [IPTC Photo Metadata Standard](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata)
78. [IPTC: Exclude images from generative AI (2023.1 Data Mining)](https://iptc.org/news/exclude-images-from-generative-ai-iptc-photo-metadata-standard-2023-1/)
79. [SPDX 3.0.1: License Expressions](https://spdx.github.io/spdx-spec/v3.0.1/annexes/spdx-license-expressions/)
80. [Creative Commons: About CC Licenses](https://creativecommons.org/share-your-work/cclicenses/)
81. [schema.org: CreativeWork](https://schema.org/CreativeWork)
82. [schema.org: usageInfo](https://schema.org/usageInfo)
83. [AnimationGuides: Mouth shapes for lip sync in Character Animator](https://www.animationguides.com/create-mouthshapes-for-lipsync/) (secondary source)
