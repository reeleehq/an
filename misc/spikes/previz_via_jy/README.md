# Spike: a previz sequence as an `an` shot, through jy (an#257)

The last open item of [an#257](https://github.com/reeleehq/an/issues/257)'s first slice: "render one previz sequence as an `an` shot through `jy` (or record why another bridge is needed)". This directory holds the running code and this record. Nothing here is imported by `an`, and no public API was added.

**Verdict.** jy alone is not a bridge: it has no JavaScript runtime. It reads JS signatures and gives Python functions that *return the call as a string*. Paired with a runtime that evaluates those strings, it works end to end. A long-lived Node process was enough to render previz's orbit sequence as an `an` shot through `frame_stage_renderer`, in both drive modes, and the two outputs were pixel-identical. Node is enough only because previz's demo engine is a DOM-free software rasteriser. A real previz engine (canvas 2D, WebGL, a chart) can only draw in a browser. **Recommendation: a page-side previz engine, loaded into the frame stage's Playwright page and driven STATE-wise through `render_states` (an#286).** The same page also evaluates time-driven sequences while lowering is incomplete. Keep jy as the stub generator for either transport. Keep the Node host for DOM-free engines and for browserless CI.

## What ran

| file | role |
|---|---|
| `previz_facade.js` | the JS surface Python calls (`load`, `info`, `statesAt`, `renderStates`, `renderTimes`), as plain function declarations so jy can read them |
| `previz_host.mjs` | the runtime jy lacks: a Node process that imports previz's built `dist/`, evaluates the facade, then answers one JSON line per call string (`{"id", "expr"}` in, `{"id", "ok", "value"}` out); frames come back as base64 RGB PNGs encoded in Node (`zlib` only) |
| `previz_via_jy.py` | the Python side: `PrevizRuntime` (jy stubs + the host), a lowering of the previz reel to an `an.timing` `Timeline`, `PrevizEngine` (an `an` `Engine` with a time-driven and a state-driven session), the shot renders, and a Playwright page probe |

`jy.add_js_funcs("previz_facade.js", value_trans=json.dumps)` produces `statesAt([0.5])`-style strings; `PrevizRuntime.__getattr__` sends each one to the host and returns the decoded value. So `rt.renderStates(states, w, h)` from Python is jy's call string, evaluated by Node.

The sequence is previz's `examples/orbit.json`: three keyframes over the demo engine (an orbit camera, a light, two colours, a field of view), 4.5 s.

## Commands

From the an worktree root, with a built previz checkout at `$PP/tt/previz` (`dist/` present; `--previz` overrides):

```sh
PYTHONPATH=$PWD python misc/spikes/previz_via_jy/previz_via_jy.py --out <scratch dir>
PYTHONPATH=$PWD python misc/spikes/previz_via_jy/previz_via_jy.py --sequence <sequence.json> --skip-page --out <scratch dir>
```

It writes `<out>/report.json`, the per-shot frames and mp4s (`<out>/work_{time,state}/shot_previz_{time,state}/`) and the page probe's PNGs (`<out>/page/`). Generated media stays out of git: the spike's run wrote to the session scratchpad, not the repo.

**previz was not modified and not built in place.** Its checkout's `dist/` was newer than every `src/` file. A rebuild of a copy in a scratch directory (`tsc -p tsconfig.build.json`, 1.6 s, offline, with the checkout's `node_modules`) gave a `dist/` identical to the checkout's (`diff -r` empty).

## Timings

An Apple M1 Max, Node v23.11.0, Python 3.12, Playwright 1.55 (Chromium headless shell), previz `903858c`, jy `4abe206`. Shot: 480x360, 24 fps, 108 frames, supersample 1, the demo engine's own anti-aliasing at 2.

| measurement | value |
|---|---|
| Node host start (imports previz `dist/` incl. zod) | 0.35 s |
| `load` (compile the sequence, open the engine) | 2.5 ms |
| one `statesAt([t])` round trip (jy string -> Node -> JSON back) | 0.14 ms |
| all 108 frame states in one round trip | 2.2 ms |
| demo engine draw + PNG encode + transfer, in Node, no frame stage | 66 ms/frame |
| whole shot through `frame_stage_renderer`, time-driven (incl. ffmpeg mux) | 7.6 s, 70 ms/frame |
| whole shot through `frame_stage_renderer`, state-driven (incl. ffmpeg mux) | 7.5 s, 69 ms/frame |
| page probe: Chromium launch + previz loaded in the page | 0.21 s |
| page probe: same draw in the page, out via `canvas.toDataURL` | 68 ms/frame |
| whole script, both shots, the agreement check and the page probe | 18.6 s |

The frame cost is the demo engine's software rasteriser, the same in Node and in Chromium. The bridge and the frame stage add about 3 ms/frame. ffprobe on the delivered mp4: 108 frames, 480x360, 24/1, 4.5 s.

## What worked

- **(a) Evaluation through jy.** jy parsed the facade (including `async function`) and produced the call strings, and the Node host evaluated them against previz's compiled reel. `reel.at(t)` comes back as a plain nested state.
- **The kernel is the same kernel.** Lowering the reel into an `an.timing` `Timeline` (one clip, one channel per view path, a key per segment boundary, the transition's `timing` as the easing) and evaluating it with `an.timing.timeline.evaluate_timeline`, in a `PropertySpace` built straight from the sequence's `space` (`kind_from_spec` on each previz field spec), agrees with previz's own `reel.at` at all 1105 sampled instants. The largest difference is 8.9e-16. `orbit`, `angle`, `color` (OKLab) and `number` all agree, and so does CSS `ease-in-out`.
- **(b) Frames.** `PrevizEngine` rendered through `an.engines.frame_stage_renderer` to an mp4 through an's own sink (`an.media.mp4.mux_shot`). Two sessions:
  - **time-driven**: `frame(t)`, `frames(requests)` (batched, one round trip per 8 frames) and `state(t)`. previz evaluates its own reel. `describe` gives `seekable / time / {batch, readback, provenance}`.
  - **state-driven**: `timeline` (the lowered reel), `space`, `render(state)` and `render_states(states)`. The core evaluates, previz only draws. `describe` gives `seekable / state / {batch, provenance}`.
  The two shots' 108 decoded frames are **pixel-identical**.
- **(b') Page-side.** previz's `dist/core/compile.js` and `dist/engines/demo/index.js` load into a Playwright page by dynamic `import()` from a same-origin static server, with no bundling and no import map (neither module imports `zod`). Frames drawn there and read back through a canvas are pixel-identical to Node's.
- **(c) Capabilities.** With `view_spaces = ("orbit3d",)`, `an.capabilities.subjects.engine_affordances(renderer)` reports `{'engine.render': {'keys': ['previz']}, 'space.orbit3d': {}}`. Provenance carries the engine's own facts (`previz_drive`, `previz_engine`, `previz_node`) beside the core's, with no clash.

## What did not work, or needed a workaround

1. **jy has no runtime.** `jy.add_js_funcs` returns strings. The spike wrote the runtime itself (`previz_host.mjs` + `PrevizRuntime`, about 80 lines). jy also has no JS-to-Python direction.
2. **jy's default value transformer is not safe for data.** `dflt_py_to_js_value_trans` writes a list of dicts as a Python repr (single quotes, `True`, `None`) and leaves strings unescaped, so a list of previz states would not survive the trip. The spike passes `value_trans=json.dumps`.
3. **`frame_stage_renderer` drops the engine's view spaces.** `_derive_engine` reads `view_spaces` off the *renderer*, and `FrameStageRenderer` does not forward its engine's. The spike sets `renderer.view_spaces` by hand.
4. **The lowering covers previz's straight route only.** previz's `daylight` formula (expanded with previz's own `expand`) uses per-field transition overrides and a **sliced easing**, `{"of": "ease-in-out", "slice": [0, 0.67]}`. Neither `an.timing.easing` nor the shared contract (`an/data/timing/`) knows `slice`. So the spike refuses to lower it and renders it time-driven only (144 frames, 70 ms/frame). previz's timing spec is a superset of the contract it asserts. Routes other than `straight`, per-field `switchAt`, cuts and `loop` are also not lowered.
5. **The view-space declaration does not match the kernel's value.** `an.semantic.views.ORBIT_3D` declares scalar fields in radians with a flattened target (`target_x/y/z`), while the kernel's `OrbitKind` (and previz) moves one value `{azimuth, elevation, distance, target[]}` in degrees by default. `ViewField` has only `linear`/`log`/`angle` scalars, so a previz view state (an orbit, colours, a vector) cannot be declared as a `view_space` at all. The engine therefore *claims* `space.orbit3d`, but nothing lowers a `view.orbit3d` move onto previz's `camera` field yet.
6. **Not tested:** a DOM or WebGL previz engine (only the demo engine exists in previz); previz overlays (burned in only where Canvas 2D exists); supersample > 1 and the shutter (the frame stage owns both, and the engine just draws at `k` times the size).

## Recommendation

- **Bridge:** jy as the stub generator, plus a runtime. For real previz engines that runtime is **the frame stage's Playwright page** (a page-side engine). The Node host is the browserless variant for DOM-free engines and CI. Both take the same jy call strings, so one facade serves both.
- **Drive mode:** state-driven is the target. The kernel agreement shows the core can own `at(t)`, and that is what lets `an`'s vocabulary moves (camera moves over view spaces) drive a previz engine. Until the lowering covers previz's timing spec, the same engine offers the time-driven session, which renders anything previz can compile and exposes `state(t)` for conformance against `an/data/timing/timing_vectors.json`.

## Next issues (recommended, not filed)

1. **A page-side previz engine for the frame stage**: an `Engine` that loads a previz engine module into the frame stage's Playwright page, with time-driven and state-driven (`render_states`) sessions, and the Node host as its browserless variant. Decide where it lives (`an` core vs a plugin package).
2. **`frame_stage_renderer` forwards its engine's `view_spaces`**, so an engine's `space.<name>` survives the wrapper and reaches `engine_affordances`.
3. **Lower a previz sequence to an `an.timing` timeline, and back**: per-field timings and `switchAt`, cuts, loops, non-straight routes; add previz's sliced easing (`{of, slice}`) to the shared timing contract, or have previz stop emitting it.
4. **One declaration for view spaces and property spaces**: give `ViewField` a field kind (orbit, color, vector, discrete), or derive a `view_space` from a `PropertySpace`, and make `ORBIT_3D` match `OrbitKind`'s value shape and unit, plus the lowering of `view.orbit3d` onto an orbit field.
5. **jy: a runtime and a JSON-safe default value transformer** (in i2mint/jy): a `JsRuntime` with a Node-subprocess and a Playwright-page implementation (this spike's `PrevizRuntime` is the starter), `json.dumps` as the default transformer, and a name for the JS-to-Python direction.
