# an.semantic.digest

Which vocabulary entries a shot names, at which versions: the shot’s vocabulary digest.

ADR 0003 decision 2: the versions of the entries a shot uses are folded into
that shot’s compile key (ADR 0004), so changing what a name means re-renders
the shots that say it — visibly, never silently. [`vocabulary_versions()`](#an.semantic.digest.vocabulary_versions)
walks a shot and collects `{entry id: version}`; [`vocabulary_digest()`](#an.semantic.digest.vocabulary_digest)
hashes it.

**In the shot key.** The content-keyed shot cache (P6, an#242) adds key parts
through `an.build.keys.register_shot_key_part(renderer, name, fn)`; this
digest is the cut-out keyer’s `vocabulary` part
([`register_vocabulary_key_part()`](#an.semantic.digest.register_vocabulary_key_part), called by `an.adapters.cutout`), so
bumping an entry’s version re-renders the shots that use it.

Over-inclusion is deliberate and safe: a `play` of a name that is a motion
preset counts the preset even if the character’s descriptor shadows it, and a
preset that resolves an aspect counts every method of that aspect — a version
bump then re-renders a shot that may not have needed it, never the reverse.

```pycon
>>> from an.ir.schema import Shot, Camera
>>> v = vocabulary_versions(Shot(id="s", camera=Camera(move="push_in")))
>>> v["camera.push_in"]
'1'
```

### Module Attributes

| [`VOCABULARY_KEY_PART`](#an.semantic.digest.VOCABULARY_KEY_PART)   | The name of the shot-key part this digest is folded in under.   |
|------------------------------------------------------------------------|-----------------------------------------------------------------|

### Functions

| [`register_vocabulary_key_part`](#an.semantic.digest.register_vocabulary_key_part)([renderer])   | Fold [`vocabulary_digest()`](#an.semantic.digest.vocabulary_digest) into `renderer`'s shot key, through P6's seam.   |
|---------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| [`vocabulary_key_part`](#an.semantic.digest.vocabulary_key_part)(shot[, ctx])           | The shot-key part (`an.build.keys.ShotKeyPart`): the shot's vocabulary digest.                                             |
| [`vocabulary_digest`](#an.semantic.digest.vocabulary_digest)(shot)                    | The sha256 of [`vocabulary_versions()`](#an.semantic.digest.vocabulary_versions) — one more part of a shot's key.      |
| [`vocabulary_versions`](#an.semantic.digest.vocabulary_versions)(shot)                  | `{entry id: version}` for every registered entry `shot` names, sorted.                                                     |

### an.semantic.digest.VOCABULARY_KEY_PART *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'vocabulary'*

The name of the shot-key part this digest is folded in under.

### an.semantic.digest.register_vocabulary_key_part(renderer='cutout')

Fold [`vocabulary_digest()`](#an.semantic.digest.vocabulary_digest) into `renderer`’s shot key, through P6’s seam.

Idempotent, and tolerant of order: returns `False` (registering nothing)
when `renderer` has no shot keyer yet, `True` once the part is in —
called again, it leaves the registered part alone. The cut-out adapter
calls it right after registering its keyer.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> import an.adapters  # registers the cut-out keyer, and this part with it
>>> register_vocabulary_key_part(), register_vocabulary_key_part("no-such-renderer")
(True, False)
```

### an.semantic.digest.vocabulary_digest(shot)

The sha256 of [`vocabulary_versions()`](#an.semantic.digest.vocabulary_versions) — one more part of a shot’s key.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.semantic.digest.vocabulary_key_part(shot, ctx=None)

The shot-key part (`an.build.keys.ShotKeyPart`): the shot’s vocabulary digest.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.semantic.digest.vocabulary_versions(shot)

`{entry id: version}` for every registered entry `shot` names, sorted.

Names the registry does not know (a descriptor animation, a parametrised
easing) are not entries and add nothing; their effect is in the compiled
document, which the shot key already covers.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
