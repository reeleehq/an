# an.characters.dicebear

DiceBear HTTP API client + best-effort post-processing.

DiceBear ([https://www.dicebear.com](https://www.dicebear.com)) hosts deterministic SVG avatar
generators. We pin to API `9.x` for stability — DiceBear pins styles to
API versions and 9.x is supported through 2028 (research §4.1, caveats).

The styles we care about — `adventurer`, `lorelei`, `avataaars` —
emit SVGs with internal groups but the group naming is style-specific and
not stable across versions. Rather than parse it heuristically (which
would silently break on a future style version), we wrap the DiceBear SVG
in a [`wrap_dicebear_for_an()`](#an.characters.dicebear.wrap_dicebear_for_an) envelope: the original SVG becomes a
single `head` part, and the rest of the rig is filled in from defaults.
That gives a usable cutout puppet immediately, at the cost of less
articulation (you can’t, e.g., blink an avataaars-style avatar — the eyes
are baked into the head).

```pycon
>>> # The wrapping is offline and deterministic.
>>> wrapped = wrap_dicebear_for_an('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><circle cx="40" cy="40" r="35"/></svg>', name='maya')
>>> 'id="head"' in wrapped
True
```

### Module Attributes

| [`DICEBEAR_API_VERSION`](#an.characters.dicebear.DICEBEAR_API_VERSION)   | 9.x and 10.x are both Active with End of Life "None" — the April 2028 date sometimes cited is the EOL of the DEPRECATED 5.x-8.x line, not of this one.   |
|-------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DICEBEAR_DEFAULT_STYLE`](#an.characters.dicebear.DICEBEAR_DEFAULT_STYLE) | The default avatar style.                                                                                                                                |

### Functions

| [`fetch_dicebear`](#an.characters.dicebear.fetch_dicebear)(seed, \*[, style, ...])            | Fetch an avatar SVG from DiceBear's HTTP API.                     |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`wrap_dicebear_for_an`](#an.characters.dicebear.wrap_dicebear_for_an)(avatar_svg, \*, name[, ...]) | Wrap a DiceBear avatar SVG into the canonical `an` cutout layout. |

### an.characters.dicebear.DICEBEAR_API_VERSION *= '9.x'*

9.x and 10.x are both Active with End of Life “None” —
the April 2028 date sometimes cited is the EOL of the DEPRECATED 5.x-8.x line,
not of this one. The pin is right; the reason previously given for it was not.

* **Type:**
  Pinned major. NOTE

### an.characters.dicebear.DICEBEAR_DEFAULT_STYLE *= 'lorelei'*

The default avatar style. CC0 1.0 — no attribution duty falls on anyone who
renders with stock settings.

The previous default (`adventurer`) is CC BY 4.0, so every character created
with default flags carried an undischarged attribution obligation, recorded
nowhere. `lorelei` is not merely “a CC0 one”: it is the only CC0 *human* style
shaped like a head-and-shoulders bust, which is what the rig needs —
`wrap_dicebear_for_an` pastes the whole avatar in as the single `head` part,
so the other CC0 human styles (`notionists`, `open-peeps`) render half-body
characters and would put a torso on a torso. It is also by the same artist as
`adventurer`, so the demo art barely shifts. `pixel-art` is the CC0 fallback.

All 27 styles stay requestable; only the default moves. See
`an/characters/licenses.py` for the per-style table.

### an.characters.dicebear.fetch_dicebear(seed, , style='lorelei', api_version='9.x', timeout_s=10.0, extra_params=None)

Fetch an avatar SVG from DiceBear’s HTTP API.

Returns the SVG string. Raises [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError) if the API call
fails (network error, HTTP error, non-SVG response).

The URL pattern is:

```default
https://api.dicebear.com/<api_version>/<style>/svg?seed=<seed>
```

Pass `extra_params` to forward style-specific options (e.g.
`backgroundColor=transparent`).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.characters.dicebear.wrap_dicebear_for_an(avatar_svg, , name, canvas_size=1024, head_size=600)

Wrap a DiceBear avatar SVG into the canonical `an` cutout layout.

The avatar becomes the `head` part; `torso`, `arm_l`, `arm_r`,
`leg_l`, `leg_r` are filled with simple colored rounded-rects so the
character is immediately renderable as a stick-figure-with-real-face.
The user can later replace any part by dropping a hand-drawn SVG into
`parts/<part>.svg`.

`head_size` is the head’s width in canvas pixels; the rest of the rig
scales accordingly.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
