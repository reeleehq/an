# an.stores.characters

Characters store — descriptor + sidecar folder per character.

A character’s `character.json` is the Phase 11a CharacterDescriptor
(slot/skin/animation graph + viseme map). Binary parts (SVGs, PNGs) are
sidecars under the same directory at e.g. `parts/head.svg`,
`parts/mouth/mouth_a.svg`, etc.

### Classes

| [`CharactersStore`](#an.stores.characters.CharactersStore)(root_dir)   | Per-character directory store.   |
|------------------------------------------------------------------------------|----------------------------------|

### *class* an.stores.characters.CharactersStore(root_dir)

Bases: `JsonSidecarStore`

Per-character directory store.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     store = CharactersStore(d)
...     store['maya'] = {'name': 'Maya', 'voice_ref': 'maya-warm'}
...     store['maya']['name']
'Maya'
```
