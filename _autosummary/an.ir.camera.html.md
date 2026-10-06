# an.ir.camera

Camera semantics: the named moves, and the one resolver that expands them.

This module exists because the alternative was two hand-maintained tables. The
compiler owned `CAMERA_MOVES` and `an.ir.validate` owned a frozenset of the
same names, reconciled by a test — which works, and is not what “a move that
validates cannot then raise” means. It means *one table*.

It lives under `an/ir/` rather than in the cutout adapter because the IR layer
must not import an adapter, and validate is in the IR layer. The camera is IR
semantics anyway: `Camera`/`CameraKey` are schema models, and a renderer that
cannot honour a move says so through `can_render`, not by keeping its own
vocabulary.

The geometry it encodes, verified numerically against the vendored PixiJS
composition: `root.pivot` IS a 2D camera, because PixiJS composes
`world = position + M·(local − pivot)` and the runtime indexes the centre
container as `root`. `+x` moves the CAMERA right, which moves content left.

### Module Attributes

| [`PAN_FRACTION`](#an.ir.camera.PAN_FRACTION)   | How far a pan travels, as a fraction of the canvas width (a tilt uses the same fraction of the height).   |
|-----------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| [`CAMERA_MOVES`](#an.ir.camera.CAMERA_MOVES)   | The named moves, as KEY LISTS.                                                                            |

### Functions

| [`camera_keys`](#an.ir.camera.camera_keys)(shot, \*, width, height)          | The shot's camera as an explicit key list — the ONE resolver.                            |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| [`camera_shake_offsets`](#an.ir.camera.camera_shake_offsets)(shot, \*, width, height) | The shot's camera shakes as `(time, dx, dy)` screen offsets — the ONE resolver (an#429). |

### Exceptions

| [`CameraError`](#an.ir.camera.CameraError)   | A camera that cannot be resolved into keys.   |
|----------------------------------------------------------------|-----------------------------------------------|

### an.ir.camera.CAMERA_MOVES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Callable](https://docs.python.org/3/library/typing.html#typing.Callable)[[[float](https://docs.python.org/3/builtins/functions.html#float)], [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[CameraKey](an.ir.schema.html.md#an.ir.schema.CameraKey)]]]* *= {'hold': <function <lambda>>, 'pan_left': <function <lambda>>, 'pan_right': <function <lambda>>, 'pull_out': <function <lambda>>, 'push_in': <function <lambda>>, 'tilt_down': <function <lambda>>, 'tilt_up': <function <lambda>>, 'zoom_in': <function <lambda>>, 'zoom_out': <function <lambda>>}*

The named moves, as KEY LISTS. `move` is sugar over `keys` — one code path,
two front doors.

The five zoom moves must desugar to **exactly** the document they produced
before an#109, which is more specific than “a scale tween”: two animations
named `__camera__<shot>_scale_x`/`_scale_y`, one channel each targeting
`root`, keyframes `[(0.0, s0, "ease_in_out"), (duration, s1, null)]`, on two
tracks rooted at `"__camera__"`, and **no pivot channels**. The emitter emits
only the channels that actually vary, which is what makes that true rather
than merely intended — and what keeps every camera scene’s contract hash
where it was.

### *exception* an.ir.camera.CameraError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A camera that cannot be resolved into keys.

A plain `ValueError` subclass so the IR layer can raise it without knowing
about any renderer; the cutout compiler re-raises it as a
`CutoutCompileError` at its own boundary.

### an.ir.camera.PAN_FRACTION *: [float](https://docs.python.org/3/builtins/functions.html#float)* *= 0.3333333333333333*

How far a pan travels, as a fraction of the canvas width (a tilt uses the
same fraction of the height). A third of the frame is a legible move at any
resolution and is the one number a named pan has to choose; an author who
wants a different distance writes `keys` and says so.

### an.ir.camera.camera_keys(shot, , width, height)

The shot’s camera as an explicit key list — the ONE resolver.

`move` and `keys` are two front doors on one path. \*\*Validate calls this
and so does the compiler\*\*, which is what makes “a move that validates
cannot then raise” true by construction rather than by two tables agreeing
— the arrangement it replaced (an#109 review, H-1).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`CameraKey`](an.ir.schema.html.md#an.ir.schema.CameraKey)]

```pycon
>>> from an.ir.schema import Camera, Shot
>>> push = Shot(id="s", renderer="cutout", duration=2.0, camera=Camera(move="push_in"))
>>> [(k.at, k.zoom) for k in camera_keys(push, width=320, height=240)]
[(0.0, 1.0), (2.0, 1.25)]
>>> pan = Shot(id="s", renderer="cutout", duration=2.0, camera=Camera(move="pan_left"))
>>> [(k.at, round(k.x, 3)) for k in camera_keys(pan, width=320, height=240)]
[(0.0, 0.0), (2.0, -106.667)]
```

### an.ir.camera.camera_shake_offsets(shot, , width, height)

The shot’s camera shakes as `(time, dx, dy)` screen offsets — the ONE resolver (an#429).

Empty when the shot has none. Each shake is at rest (`0, 0`) at its
start and its end; between, the frame jumps `frequency` times a second
to a seeded offset of at most `amplitude` × the frame height, scaled
down linearly to rest when `decay`. Validate and the compiler both call
this, so a shake that validates cannot then raise (as with
[`camera_keys()`](#an.ir.camera.camera_keys)).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]]

```pycon
>>> from an.ir.schema import Camera, CameraShake, Shot
>>> s = Shot(id="s", duration=2.0, camera=Camera(shake=[CameraShake(at=1.0, duration=0.25, frequency=8)]))
>>> [(t, round(dx, 2), round(dy, 2)) for t, dx, dy in camera_shake_offsets(s, width=1280, height=720)]
[(1.0, 0.0, 0.0), (1.125, 3.72, 2.79), (1.25, 0.0, 0.0)]
```
