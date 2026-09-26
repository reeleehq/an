# an.bench.contract

`scene_contract_sha256`: the fact that decides whether two rows are comparable.

Two ledger rows measured on different scenes are not “one better and one
worse” — every metric in them is **uninterpretable** relative to the other.
`edge_transition_width`’s own docstring says so: the absolute value is
scene-dependent, because a deliberately 3px black outline is legitimately
non-flat.

So each row carries a hash of the thing that was actually rendered. Deliberately
a hash of the **staged compiled scene**, not of the project directory: the
directory carries scene mtimes and a decisions log that move on every load, and
hashing it would make every row incomparable with every other for reasons that
never reached a pixel.

### Functions

| [`count_drawable_entities`](#an.bench.contract.count_drawable_entities)(scene_json)   | Top-level entities under the synthetic root.                                |
|----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`count_nodes`](#an.bench.contract.count_nodes)(scene_json)               | Every node in the tree, root included.                                      |
| [`frames_sha256`](#an.bench.contract.frames_sha256)(frame_paths)            | `sha256` over the DECODED pixels of a frame sequence, never file bytes.     |
| [`scene_contract_sha256`](#an.bench.contract.scene_contract_sha256)(scene_json)     | A stable digest of what was rendered.                                       |
| [`scenes_contract_sha256`](#an.bench.contract.scenes_contract_sha256)(scene_jsons)   | The contract digest for a whole scene, across every shot in timeline order. |

### an.bench.contract.count_drawable_entities(scene_json)

Top-level entities under the synthetic root.

Named for what it counts. “n_entities” is ambiguous in this codebase — the
IR’s `shot.entities` includes `voice` refs that configure
the render rather than appearing in it, so the two numbers differ on every
scene with dialogue. Both are recorded; only this one is inside the hash.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> count_drawable_entities({"scene": {"children": [{}, {}]}})
2
```

### an.bench.contract.count_nodes(scene_json)

Every node in the tree, root included.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

```pycon
>>> count_nodes({"scene": {"children": [{"children": [{}]}]}})
3
```

### an.bench.contract.frames_sha256(frame_paths)

`sha256` over the DECODED pixels of a frame sequence, never file bytes.

The gate for `encode_flicker_on_held_pixels`: without it, half-res-then-
nearest-upscale — the most visible possible flat-art regression — reports a
7.1x *improvement*, because a flattened render gives x264 large uniform
skip regions.

Decoded, not file bytes, for the reason the cross-architecture verdict
records: Chromium 1187 -> 1223 changes 144/144 PNG files and **zero**
pixels, so a file-byte digest goes red on the first Playwright bump for a
reason unrelated to animation quality.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.contract.scene_contract_sha256(scene_json)

A stable digest of what was rendered.

Hashed over a *reduced* form rather than the whole document, and the
reduction is the point: the digest must move when the picture’s contract
moves and stay put otherwise. Animation keyframe floats and asset paths are
in; nothing time- or machine-dependent is, because the compiled scene is
already free of both (every escaping set goes through `sorted()`, the
palette hash is `sum(ord(c)) % 5` rather than Python’s `hash()`, and
the staged JSON is written with `sort_keys=True`).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> a = scene_contract_sha256({"meta": {"fps": 24}, "scene": {"children": []}})
>>> a == scene_contract_sha256({"scene": {"children": []}, "meta": {"fps": 24}})
True
>>> len(a)
64
```

### an.bench.contract.scenes_contract_sha256(scene_jsons)

The contract digest for a whole scene, across every shot in timeline order.

A single-shot scene returns **exactly** [`scene_contract_sha256()`](#an.bench.contract.scene_contract_sha256) of its
one staged scene, so every row written before the corpus grew a multi-shot
fixture stays comparable — `an bench --compare` refuses rows whose
contract hash differs, and a gratuitous change here would retire the only
committed row as evidence.

A multi-shot scene hashes the ordered list of per-shot digests, because
hashing only the first shot would let a change to the second one pass as
“the same scene” — which is precisely the claim this digest exists to deny.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> a = {"scene": {"children": []}}
>>> scenes_contract_sha256([a]) == scene_contract_sha256(a)
True
>>> scenes_contract_sha256([a, a]) == scene_contract_sha256(a)
False
```
