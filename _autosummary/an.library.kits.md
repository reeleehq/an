# an.library.kits

Kits: a curated, versioned set of library assets that a project checks out in one call.

A production in a named style needs a *set* of assets — the style’s StylePack and
voice documents, a date-card environment, recurring props, the base cast — not
one. A **kit** is the library’s answer: an asset of kind `kit` whose document
lists the members, each pinned to a concrete version, so a kit version always
means the same set of bytes. [`publish_kit()`](#an.library.kits.publish_kit) makes one; [`checkout_kit()`](#an.library.kits.checkout_kit)
checks every member out through the ordinary `checkout()`
(its pin in `assets.lock.json`, its rights, its credits) and records the kit
beside them (`ProjectLock.kits`, [`an.stores.library_lock`](an.stores.library_lock.md#module-an.stores.library_lock)).

The document (kind `Kit`, versioned like every document kind):

```json
{"kind": "Kit", "schema_version": "0.1.0", "name": "reiniger-base",
 "members": [{"ref": "style.reiniger@v003", "key": null},
             {"ref": "cutan:character.alice@v002", "key": "alice"}],
 "note": "what a Reiniger-style short starts from"}
```

Three rules, each the point rather than a detail:

- **Members are pinned.** `latest` and unversioned references are resolved when
  the kit is published, so re-checking out an old kit version never drifts. A
  member reference with no `<library>:` prefix resolves in the kit’s own
  library first, then along the search path.
- **Kits do not nest** (v1). A member of kind `kit` is refused, at publish and
  at check-out: a nested set would make the lockfile’s record of a kit’s members
  a tree, and no one has asked for one.
- **Rights stay per member.** The kit’s own document is its author’s, so its
  rights come from the `source=` the publisher gives, like any document; the
  members’ rights are NOT rolled into the kit’s record, because each member
  carries its own at check-out (and `an credits` reads them there).

A check-out resolves and checks every member before it writes any: a missing
member, a nested kit, a corrupt blob or a project entry that is a fork refuses
the whole kit and leaves the project as it was.

```pycon
>>> doc = Kit(name="base", members=[KitMember(ref="style.reiniger@v001")])
>>> [m.ref for m in doc.members], doc.schema_version
(['style.reiniger@v001'], '0.1.0')
```

### Module Attributes

| [`KIT_SCHEMA_VERSION`](#an.library.kits.KIT_SCHEMA_VERSION)   | Schema version of the kit document (its own document kind).   |
|-----------------------------------------------------------------------|---------------------------------------------------------------|

### Functions

| [`checkout_kit`](#an.library.kits.checkout_kit)(libraries, project_dir, ref, \*)      | Check every member of a kit out into a project, pin each, and record the kit.            |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`publish_kit`](#an.library.kits.publish_kit)(library, asset_id, members, \*[, ...]) | Publish a kit — a pinned set of assets — as the next version of `asset_id` in `library`. |

### Classes

| [`Kit`](#an.library.kits.Kit)(\*\*data)       | The kit document: a name, its pinned members, and a note saying what it is for.   |
|----------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`KitMember`](#an.library.kits.KitMember)(\*\*data) | One member of a kit: a pinned reference and the project key it lands under.       |

### an.library.kits.KIT_SCHEMA_VERSION *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= '0.1.0'*

Schema version of the kit document (its own document kind).

### *class* an.library.kits.Kit(\*\*data)

Bases: `BaseModel`

The kit document: a name, its pinned members, and a note saying what it is for.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* an.library.kits.KitMember(\*\*data)

Bases: `BaseModel`

One member of a kit: a pinned reference and the project key it lands under.

`key=None` takes the check-out’s default (the asset id’s slug).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'allow'}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### an.library.kits.checkout_kit(libraries, project_dir, ref, , overwrite=False, upgrade=False, mall=None, lock=None)

Check every member of a kit out into a project, pin each, and record the kit.

libraries: where the kit and its members resolve
project_dir: the project to check out into
ref: `[<library>:]<kit asset id>[@<version>]`; `latest` is resolved now
overwrite: replace project entries that are not exactly their member’s version
upgrade: update in place a member’s entry pinned to an earlier version of

> that member, unedited since (`checkout()`)

mall: the project mall (default: `build_project_mall(project_dir)`)
lock: the lockfile (default: the mall’s `library_lock` store); it needs a

> `kits` section, as [`ProjectLock`](an.stores.library_lock.md#an.stores.library_lock.ProjectLock) has

Returns one [`CheckoutResult`](an.library.md#an.library.CheckoutResult) per member, in the
kit’s order. Each member is checked out by `checkout()`
under its `key` and pinned in `assets.lock.json` as any check-out is; the
kit itself is recorded under the lockfile’s `kits` section (its pinned
reference, manifest and the members’ lockfile keys), so `an library` readers
and a human can see which kit the project came from. Checking the same kit out
again is idempotent.

All members are resolved and checked before the first is written: a missing
member, a member that is itself a kit, a corrupt stored file, or a project
entry that is a fork (without `overwrite`) raises `CheckoutError`
and the project is untouched.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`CheckoutResult`](an.library.md#an.library.CheckoutResult)]

### an.library.kits.publish_kit(library, asset_id, members, , search=None, name=None, note=None, \*\*curation)

Publish a kit — a pinned set of assets — as the next version of `asset_id` in `library`.

library: the owning library (writes never go to a search path)
asset_id: `kit.<slug>`
members: each a library reference (`[<library>:]<asset_id>[@<version>]`), a

> `(reference, key)` pair, or a mapping `{"ref": …, "key": …}`; `key` is
> the name the member takes in the project’s store (default: the asset’s slug)

search: further libraries where member references resolve (the owning library
: is always searched first, as in [`publish()`](an.library.api.md#an.library.api.publish))

name: the kit’s name in its document (default: the asset id’s slug)
note: what the kit is for, stored in the document and on the version
curation: everything else [`publish()`](an.library.api.md#an.library.api.publish) takes — `source=`

> (the kit document is its author’s own authoring: its rights come from
> this, never from its members), `title`, `style`, `tags`, …

Every member must resolve; `latest` and unversioned references are pinned to
the concrete version now, so the kit version is reproducible. A member that is
itself a kit, one with no project store, or two members landing in one
`(store, key)` are refused.

```pycon
>>> lib = open_library("an", records={}, versions={}, blobs={})
>>> _ = publish(lib, "style.noir", {"name": "noir"}, source={"provider": "me", "license": "cc0-1.0"})
>>> r = publish_kit(lib, "kit.noir-base", ["style.noir"], source={"provider": "me", "license": "cc0-1.0"})
>>> lib.versions["kit.noir-base@v001"]["doc"]["members"]
[{'ref': 'style.noir@v001', 'key': None}]
```

* **Return type:**
  [`PublishResult`](an.library.api.md#an.library.api.PublishResult)
