# an.library.cli

`an library …` — the asset library from the shell, over the same functions as Python.

Wired into the top-level dispatcher as the `library` namespace
(`an.tools._dispatch_namespaces`), programmatically, per pillar 8: these are
plain functions taking strings and booleans and returning the text to print;
the business logic is [`an.library.api`](an.library.api.md#module-an.library.api).

Lists are comma-separated (`--style reiniger,gilliam`). Every command reads
the library of `--package` (default `an`) at `--root` (default: the
package’s data folder, or `<PKG>_HOME`); the read commands search that
library, then the core `an` library, then `--extra` ones — and the library
a namespaced reference names (`cutan:character.alice@v002` reads `cutan`
with no `--package`; an#251). A refusal (an unknown asset, a private asset
leaving its library, …) prints one sentence and exits non-zero.

Subcommands: `publish`, `find`, `vocabulary`, `show`, `checkout`,
`promote`.

### Functions

| [`checkout`](#an.library.cli.checkout)(project_dir, ref[, key, overwrite, ...])   | Check a library version out into a project, and pin it in assets.lock.json.    |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`find`](#an.library.cli.find)([kind, style, affords, rights, family, ...])   | Find assets: AND across facets, OR within one facet's comma-separated values.  |
| [`promote`](#an.library.cli.promote)(ref[, package, root, core_root, ...])       | Copy a version into the core an library, so other genres can reuse it.         |
| [`publish`](#an.library.cli.publish)(folder, asset_id[, package, root, ...])     | Publish an asset folder as the next version of `asset_id`.                     |
| [`show`](#an.library.cli.show)(ref[, package, root, extra, json_out])         | Show one asset: its record, the resolved version, and its other versions.      |
| [`vocabulary`](#an.library.cli.vocabulary)([package, root, extra])                  | Every facet value with its count, and every capability with its remedy (JSON). |

### an.library.cli.checkout(project_dir, ref, key='', overwrite=False, package='', root='', extra='')

Check a library version out into a project, and pin it in assets.lock.json.

project_dir: the an project
ref: [<library>:]<asset_id>[@<version>] (latest is resolved now and pinned); a <library>: prefix reads that library, no –package needed
key: the key in the project store (default: the asset’s slug)
overwrite: replace an existing entry that is not this version (an unedited folder you just published is recognised without it)
package: the library to read first, then the core an library (default: the reference’s <library>: prefix, else an)
root: that library’s root (with no –package, the root of the library the reference names)
extra: further libraries, by package name, comma-separated

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.cli.find(kind='', style='', affords='', rights='any', family='', origin='', status='', tags='', near=False, package='an', root='', extra='', json_out=False)

Find assets: AND across facets, OR within one facet’s comma-separated values.

kind: character, prop, environment, …
style: styles, comma-separated (any of them)
affords: capabilities the asset must ALL have, e.g. limbs.legs,swap.view:side
rights: any, publishable, or licence classes (free, attribution, private, unknown)
family: families, comma-separated
origin: origins, comma-separated
status: draft, approved, deprecated
tags: tags, comma-separated (any of them)
near: also list assets that only miss capabilities, with the remedy for each
package: the library to search first (then the core an library)
root: that library’s root
extra: further libraries to search, by package name, comma-separated
json_out: print JSON instead of a table

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.cli.promote(ref, package='', root='', core_root='', as_id='', allow_restricted=False)

Copy a version into the core an library, so other genres can reuse it.

ref: [<library>:]<asset_id>[@<version>]
package: the library it is in (a genre’s, e.g. cutan; default: the reference’s <library>: prefix)
root: that library’s root
core_root: the core an library’s root (default: its data folder)
as_id: promote under another id (when the core library has an unrelated asset with this one)
allow_restricted: copy a private or unknown version anyway (it otherwise never leaves its library)

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.cli.publish(folder, asset_id, package='an', root='', title='', family='', style='', origin='', status='', tags='', note='', derived_from='', license='', provider='', author='', source_url='', relicense_by='', relicense_reason='', expect_head='', replace_curation=False, extra='')

Publish an asset folder as the next version of `asset_id`.

folder: the asset folder as it sits in a project (e.g. assets/characters/alice)
asset_id: <kind>.<slug>, e.g. character.alice-reiniger
package: whose library to publish into (an, or a genre such as cutan)
root: that library’s root (default: the package’s data folder)
title: a human title for the record
family: the identity shared across styles and variants (e.g. alice)
style: styles the asset suits, comma-separated
origin: drawn, procedural, dicebear, carved, traced, stock, commissioned, generated
status: draft, approved or deprecated
tags: free tags, comma-separated
note: what changed in this version
derived_from: library references this derives from, comma-separated
license: licence code of the asset as a whole (counted BESIDE the descriptor’s own source and everything it inherits; the strictest wins)
provider: where it came from (required with –license)
author: who made it
source_url: where it was fetched from
relicense_by: who relicenses the asset (with –relicense-reason and –license): the only way to relax inherited rights
relicense_reason: why — recorded on the version and shown in its rights
expect_head: refuse unless the asset’s head is this version, or ‘new’ for an id that must not exist yet
replace_curation: –style/–tags replace the record’s lists instead of adding to them
extra: further libraries where –derived-from resolves, by package name, comma-separated

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.cli.show(ref, package='', root='', extra='', json_out=False)

Show one asset: its record, the resolved version, and its other versions.

ref: [<library>:]<asset_id>[@<version>] (latest by default); a <library>: prefix reads that library
package: the library to read first, then the core an library (default: the reference’s <library>: prefix, else an)
root: that library’s root (with no –package, the root of the library the reference names)
extra: further libraries, by package name, comma-separated
json_out: print the full record and version as JSON

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.library.cli.vocabulary(package='an', root='', extra='')

Every facet value with its count, and every capability with its remedy (JSON).

package: the library to read first (then the core an library)
root: that library’s root
extra: further libraries, by package name, comma-separated

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
