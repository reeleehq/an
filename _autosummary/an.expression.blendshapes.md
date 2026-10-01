# an.expression.blendshapes

The 52-coefficient blendshape vocabulary, as an import/export mapping (an#98).

Reproduced only from the MediaPipe “Blendshape V2” model card (Apache-2.0,
[https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf),
sha256 `c8e9cf60a39998f4b341740623917590e050d1c97004e2de4568d84e026445ae`,
appendix “List of predicted blendshapes”, transcribed from the rendered page —
the text layer drops the “ft” ligature). Compatible with the ARKit-style
52-coefficient convention; no identifier here carries that name, by rule
(research `misc/docs/wave6_research.md` §3).

These are **not rig channels**: most have no cutout meaning. They exist so a
tracked or imported face can be mapped onto the axes in
[`an.expression.axes`](an.expression.axes.md#module-an.expression.axes) and back, unipolar in `[0, 1]` with rest 0 and
left/right split — the card’s contract.

```pycon
>>> len(BLENDSHAPE_V2_NAMES)
52
>>> from_blendshapes({"browInnerUp": 1.0, "eyeBlinkLeft": 1.0})
{'brow_height_l': 1.0, 'brow_height_r': 1.0, 'brow_angle_l': 1.0, 'brow_angle_r': 1.0, 'lid_open_l': -1.0}
```

### Functions

| [`from_blendshapes`](#an.expression.blendshapes.from_blendshapes)(coefficients)   | Fold unipolar coefficients onto the axes (summed, then clamped).   |
|-----------------------------------------------------------------------------------|--------------------------------------------------------------------|

### an.expression.blendshapes.from_blendshapes(coefficients)

Fold unipolar coefficients onto the axes (summed, then clamped).

Unknown names raise — a misspelt coefficient must not vanish quietly.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float)]
