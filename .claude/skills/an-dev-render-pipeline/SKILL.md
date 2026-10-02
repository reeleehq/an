---
name: an-dev-render-pipeline
description: The frame path in the `an` repo, end to end — Pixi rasterisation, Playwright element capture, the PNG stage, the x264 mux, concat and delivery — and what each stage can lose. Use when changing anything that touches a pixel or an encode flag - supersampling, resolution, antialias, `device_scale_factor`, `autoDensity`, downscale filters, `-pix_fmt` / CRF / preset / colour tags, `_capture_frames`, `_ffmpeg_mux`, `an/engines/` (the frame stage, `capture_frames`, `frame_stage_renderer`), `an/media/` (`mp4.py`, `supersample.py`, `shutter.py`, sinks), `_ffmpeg_concat`, `runtime.js`'s PIXI.Application options, or the per-shot mp4 store. Triggers on "supersample", "why is the render soft", "add an encoder flag", "make it render bigger", "downscale", "4:4:4", "faststart", "the frames look wrong", "speed up the render".
---

# The frame path, and what each stage can lose

Authorities, in order: `misc/docs/wave3_research.md` (measured 2026-08-22),
`misc/docs/wave2_research.md`, `misc/docs/wave2_crossarch_verdict.md`, then this
file. **Do not re-derive them.** Four of `wave3_research.md`'s findings are the
*opposite* of the obvious answer, and two of them are the opposite of what epic
#9's brief asks for.

`an-dev-bench` is the sibling skill: this one is about the pixels, that one is
about measuring them. Any change here that could move a pixel needs the
`run-browser-tests` label on its PR —
`gh api -X POST repos/thorwhalen/an/issues/<N>/labels -f 'labels[]=run-browser-tests'`
(`gh pr edit --add-label` silently no-ops on this repo).

---

## 1. The path, stage by stage

**Since an#247 the path is split at the engine seam.** The stage engine
(`StageEngine` in `an/stage/render.py`, moving to `an.stage`) does
steps 1-5 (compile, stage, Chromium, load, determinism probe) and yields a
session; the CORE frame stage (`an.engines.frame_stage_renderer`) validates the
knobs first and owns steps 6-8 for every engine: the capture loop
(`an.engines.capture`, sequential or batched), the resolves (`an.media.supersample`,
`an.media.shutter`) and the mux (`an.media.mp4`). The names below are the old ones;
every one still resolves (the mux/argv/pixel-format names as LIVE aliases).

```
an.render.render(project, …)
  └ RenderContext(fps, resolution, work_dir, mall, strict_assets, supersample, step_hz)
     ↑ per-render knobs live HERE — see §6 for why anywhere else refuses metrics
     │
     ├ per shot (thread pool, DEFAULT_PARALLEL_CAP=4, one Chromium each)
     │   CutoutRenderer.render(shot, ctx)                 an/stage/render.py
     │    1. compile_shot(...)          → CutoutSceneJSON   ← the wire contract; its digest is
     │                                                        `scene_contract_sha256`
     │    2. _stage_job(...)            → <project>/.an/render_work/<shot>/{runtime,frames}
     │    3. _serve_dir + Playwright Chromium, DETERMINISTIC_CHROMIUM_ARGS, headless=True,
     │       viewport = ctx.resolution
     │    3b. page.evaluate → window.anSupersample = ctx.supersample   (BEFORE anLoadScene:
     │                                     that is where the application is built)
     │    4. window.anLoadScene(scene)  → new PIXI.Application({view:#stage, width, height,
     │                                     backgroundColor, antialias:true, resolution:k,
     │                                     autoDensity:false, autoStart:false,
     │                                     preserveDrawingBuffer:true})
     │    5. _determinism_report(page)  → raises on a breached perimeter (enforced by default)
     │    6. _capture_frames            → per frame: anSetTime(t); locator('#stage').screenshot()
     │                                     k=1 → straight to frames/frame_%06d.png, Chromium's
     │                                           own bytes, nothing decoded (OFF IS FREE)
     │                                     k>1 → screenshot to BYTES, block-mean resolve to the
     │                                           declared size, then write
     │                                   — or, ctx.capture="canvas" (THE DEFAULT since an#192, §2b):
     │                                     batches of anCaptureFrames → PNG data URLs →
     │                                     opaque check, the SAME resolves, RGB PNG, on a
     │                                     bounded encode pool. Same decoded frames.
     │    7. _ffmpeg_mux                → silent.mp4  (libx264, yuv420p, DETERMINISTIC_X264_ARGS,
     │                                                 MP4_FASTSTART_ARGS) — an INTERMEDIATE
     │    8. _ffmpeg_add_audio          → <shot>.mp4  (-c:v copy + AAC + MP4_FASTSTART_ARGS;
     │                                                 -c copy RE-LAYS the container, so the
     │                                                 flag must be re-asked for here)
     │
     ├ _render_one → project.mall["shots"][shot.id] = mp4 bytes        ← WRITE-ONLY, see §5
     ├ _ffmpeg_concat  1 shot: shutil.copy  |  ≥2 shots: concat demuxer -c copy
     │                 + MP4_FASTSTART_ARGS on the concat leg (a remux, verified)
     │   — or, ONLY when the scene has a non-cut transition or any sound cue,
     │   an.assemble.assemble_film (an#163, an#260): the film's picture is a
     │   stream-copy concat of VIDEO-ONLY segments — a shot no transition
     │   touches is its own mp4's video stream; a touched shot gives its body
     │   (encoded once by mux_frames) and its window's PNGs; each run of
     │   composed frames (exact integer blends) is encoded on its own; every
     │   segment ≥ MIN_SEGMENT_FRAMES (3) when there are several, or the
     │   concat's DTS go backwards (x264 gives a 1-2-frame stream no B-frame
     │   delay). Video-only, because a concat of the shot mp4s starts 23 ms late
     │   (AAC priming) and advances by container length; then the film audio
     │   rebuilt from sources (dialogue WAVs + sounds-store cues, ducked) and
     │   muxed with -c:v copy + AAC + MP4_FASTSTART_ARGS. Never xfade over
     │   encoded shots: that is a second x264 generation on every frame.
     └ project.mall["output"][name] = bytes
```

**Where each stage can lose something, and how much:**

| stage | loss | measured |
|---|---|---|
| 4 rasterise | AA is MSAA-limited: the edge transition stays ~1 logical pixel however good the geometry is | `aa_probe` `edge_transition_width` 2.8807 at k=1 |
| 6 capture | **nothing, if you leave it alone.** Every documented way of making it capture more pixels *except* `resolution` + `autoDensity:false` loses them again silently — §2. Since an#54 `an bench` **refuses** a capture whose PNGs are not the declared size (`an/bench/run.py::_assert_declared_resolution`, against `ShotCapture.frame_sizes` read from each IHDR), so a supersample that leaves k-times frames on disk fails loudly instead of producing k² scrambled ones. A deliberate supersample must therefore resolve **in the frame stage**, before the PNGs are written — which is what §2 already prescribes. | — |
| 7 encode | **chroma subsampling is FIRST-order**; quantiser damage is second | edge-band error 11.35 (4:2:0 crf23) → 3.79 (4:4:4 crf18); mathematically lossless 4:2:0 only reaches 10.15 |
| 8 audio mux | no pixels (`-c:v copy`), but it **re-lays the container** — this is where `+faststart` was being lost, on EVERY shot | measured on a local example render (these mp4s are gitignored build products; `git ls-files` tracks exactly one, and it was moov-last too): `silent.mp4` was `ftyp moov free mdat`, every delivered file `ftyp free mdat moov` |
| concat | no pixels; `-c copy` does not carry `moov` position across either, so the flag is needed on this leg too | the corpus is **not** inconsistent — before the fix ALL SIX scenes lost it (5 of 6 take the `shutil.copy` path, and that path copies an already-broken file). `file_bytes` and `video_stream_bytes` cannot see the fix in either direction: measured identical |

---

## 2. The measured negatives — do not re-attempt any of these

Each was tried, measured, and refused. They are recorded here so the next
session does not spend the afternoon rediscovering them.

**Setting `tint` on the node an entity channel targets** — a silent no-op, and
the most misleading kind. A PixiJS `Container` has an `alpha` the renderer
multiplies down the tree; it has **no `tint`**. Only the leaves that actually
draw (`Graphics`, `Sprite`, `Mesh`, `Text`) have one. An entity channel targets
the entity ROOT, which is a Container, so `node.tint = packed` there assigns an
own property nothing reads.

Measured (an#62): a full tween to `#ff0000` moved the drawn pixels from
`(0.382, 0.260, 0.502)` to `(0.381, 0.260, 0.502)` — a change of **0.0002**.
That number is the hazard. It is not zero, so a "did anything change?" assertion
passes; it is nowhere near a tint, so the picture is wrong. Whole-frame means are
worse still: the subject covers about a seventh of the canvas, so even a WORKING
tint moves them by a few percent, and a test written on frame means passes either
way.

So `runtime.js` walks the subtree itself (`applyTintDeep`), and the guard measures
**drawn pixels only** and asserts the untinted frame *fails* its own bound. If you
are here because a colour looks wrong, check this before reaching for colour
space — the symptom reads exactly like a conversion problem and is not one.

**`device_scale_factor` on the browser context** — a blind *upscale*. The scene
still rasterises at 1x and Chromium stretches it. Refuted in Wave 2.

**`resolution: k` with `autoDensity: true`** — the same failure through the door
whose name most suggests it is the right one. `autoDensity` sets the canvas *CSS*
size to the logical size, so Chromium composites the k-times backbuffer down
**before** the screenshot: a blind browser downscale with no filter choice and no
record that it happened. Measured on `aa_probe` (declared 320x240):

| Application options | PNG on disk |
|---|---|
| today (neither key present) | 320x240 |
| `resolution: 2, autoDensity: false` | **640x480** |
| `resolution: 2, autoDensity: true` | 320x240 |

> **`autoDensity: false` is the supersample path**, and it is load-bearing.
> Both keys were absent before an#58, so PixiJS's `RESOLUTION: 1` applied
> silently and *both* had to be introduced together.

**Shipped since an#58, opt-in**: `an render --supersample N`, or
`RenderContext.supersample`. Three things about it that are easy to get wrong:

- **The factor reaches `runtime.js` as an injected global** (`window.anSupersample`,
  set immediately before `anLoadScene` — which is where the PixiJS application is
  built, and therefore the only moment it can reach `resolution`). The bench's
  `supersample` lever cannot use that route for exactly this reason: the product
  overwrites the global from `ctx.supersample`, so the lever **overrides the line
  that reads it** instead. That was found by an#54's shape guard reporting
  160x120 frames against a 320x240 declaration.
- **The resolve is `an.media.supersample.block_mean_resolve` (moved there from
  `an.media.supersample` in an#247, which re-exports it) — one
  implementation, three callers**: the renderer, the bench lever, and
  `misc/bench/wave3_ab.py`. A lever that computes the resolve differently from
  the product it examines is a lever measuring nothing, and nothing in CI would
  notice. It is a two-step `uint16` sum with the tie-break spelled out, 2.3x
  faster than the `float64` mean and bit-identical to it — asserted exhaustively
  over every possible 2x2 and 3x3 block, because the disagreement is exactly at
  the half and a random probe finds it only by luck.
- **`2 * remainder` against `area`, never `remainder` against `area // 2`.** An
  odd area has no exact half: at k=3, a remainder of 4 is a true mean of q+4/9,
  which must round DOWN — but `area // 2` is also 4, so a naive tie-break rounds
  it up. k=3 is the factor research §3a says reaches the ceiling on every scene
  that has one.

**Cost, on the SHIPPED path and not on the render alone** — the two differ by
1.6x, so say which you mean. `single_character` at 1920x1080, 60 frames: **125.5
ms/frame at k=1, 508.6 at k=2 (4.05x)**. Research §3b's 2.54x is the *render*
only, measured with a patched runtime and no Python-side resolve. At 320x240 the
same ladder reads 1.0x / 1.08x, because fixed costs dominate — which is why the
corpus cannot inform the factor and must not be used to.

**Lanczos (or bicubic) as the downscale filter** — refuted. It is a photographic
resampler and this is not photographic content; its negative lobes ring on
hard-edged flat fills. `edge_transition_width` at k=2 on `saturated_outline`, the
scene closest to the target idiom: box **2.4921 (+5.2%)**, lanczos **7.3134
(+208.8%)**. The metric's own docstring says "3+ means the picture has gone soft".
Bicubic fails the same way and additionally pins at a suspiciously flat 4.0000 on
three scenes.

> **The correct downscale is a plain k x k block mean, in numpy.** At an integer
> ratio it *is* the supersample resolve, not an approximation — and it measured
> identical to PIL's `Image.BOX` to four decimals on five scenes. No PIL, no
> resampler, no new dependency, and no filter choice to defend.
> ```python
> blocks = frames.reshape(n, h // k, k, w // k, k, c).astype(np.float64)
> resolved = np.rint(blocks.mean(axis=(2, 4))).clip(0, 255).astype(np.uint8)
> ```

**Downscaling in ffmpeg (`-vf scale=…`)** — refused for two independent reasons,
either of which is sufficient: it moves `x264_argv`, which refuses **every**
encode-side metric against every existing ledger row; and it retires the
cross-arch verdict's load-bearing clause that *"ffmpeg never touches a frame"*.
**The downscale runs in the frame stage**, before the PNGs are written.

**Raising the Playwright viewport to match a supersampled backbuffer** —
unnecessary. The viewport stayed at 320x240 while the element screenshot came out
640x480, un-clipped. Capture beyond the viewport works.

**`display:none` on the stage canvas during the render (an#57)** — refuted, and
the refutation is about *what the screenshot actually is*. `_capture_frames` calls
`page.locator('#stage').screenshot(...)`, and Playwright implements an element
screenshot as a **page capture clipped to the element's document rect**
(`screenshotter.js::screenshotElement`, playwright==1.55.0): it first awaits
`_waitAndScrollIntoViewIfNeeded(waitForVisible=true)`, then captures from the
compositor. So there is no spelling that both passes the gate and keeps the
pixels. Measured at 1920x1080:

| spelling | Playwright sees visible? | seek loop | element screenshot |
|---|---|---|---|
| baseline | yes | 16.4 ms/f | works |
| `display:none` | no | 0.7 ms/f | **TimeoutError** |
| `visibility:hidden` | no | 0.7 ms/f | **TimeoutError** |
| `content-visibility:hidden` | *unverified* | — | *unverified* |
| `opacity:0` | **yes** | 0.7 ms/f | **all-white, 1 distinct RGBA** |
| off-screen `fixed;left:-99999px` | **yes** | 0.8 ms/f | **all-white, 1 distinct RGBA** |

`content-visibility:hidden` is listed **unverified** on purpose. Playwright's
visibility predicate is a non-empty bounding box plus computed
`visibility != hidden`, and a canvas under `content-visibility:hidden` keeps its
own replaced-element box — so it plausibly reads as *visible* and belongs in the
second group rather than the first. The guard forbids the spelling either way;
the table does not claim a measurement nobody took.

The Wave 2 number reproduces exactly as Wave 2 stated it — *on the seek loop*
(16.44 → 0.69 ms/f, 24x here; and 0.69 ms is the bare `page.evaluate` round trip,
0.66 ms, so the seek itself becomes free). It is **not free end to end**, because
the element screenshot re-pays the composite. Toggling hide-for-seek /
show-for-shot per frame measured **116.11 ms/f against a 115.30 ms/f baseline** —
no win at all.

**The win is real but it belongs to the capture path, not to the hiding.**
Full-loop medians, interleaved over three rounds at 1080p:

| regime | ms/frame |
|---|---|
| today: visible + `locator.screenshot()` → disk | **115.9** |
| visible + in-page `toDataURL('image/png')` → disk | 34.3 |
| `display:none` + in-page `toDataURL` → disk | **31.5** |

So the capture path is **3.4x** and `display:none` adds a further **1.09x** on
top of it. Isolated: the element screenshot alone costs 100.0 ms/f, `toDataURL`
alone 10.0 ms/f visible and 9.9 ms/f hidden. And contra `wave2_research.md`'s
alpha caveat, the two paths agreed **byte-for-byte in RGBA** on the probe scene
(RGB maxdiff 0, alpha identical, both all-255) — which does not discharge the
pixel gate, because one scene at one time on one machine is not the corpus.

**Do not re-attempt the hiding on its own.** `index.html`'s `#stage` rule carries
the reason, `tests/test_cutout_runtime_files.py::test_the_capture_page_never_stops_compositing_the_stage_canvas`
refuses it, and the mutant `capture_page_stops_compositing_the_canvas` proves
that guard fails when it is reintroduced.

## 2b. The canvas capture path (the default since an#192) — the win above

`RenderContext.capture` / `an render --capture`: `"canvas"` is the default
(`DEFAULT_CAPTURE`, read at call time); `--capture screenshot` still selects
the element-screenshot loop above. The page's
`window.anCaptureFrames(requests)` seeks each requested instant and returns
`app.view.toDataURL('image/png')`; `an/stage/canvas_capture.py` turns
each into the frame the screenshot path writes; `render._capture_frames_canvas`
drives it. **The contract is the DECODED frame**: same RGB array, same mode,
same size — so the mux sees the same frames and the delivered mp4 is
byte-identical. File bytes differ (Pillow's encoder, not Chromium's), which is
why nothing may compare them.

Every trap, and where it is closed — do not reopen any of them:

| trap | what happens | closed by |
|---|---|---|
| row order | `gl.readPixels` is bottom-up; a PNG is top-down. A flipped frame has the declared size and passes every shape check | `toDataURL`, no flip; mutant `canvas_capture_flips_rows` + an in-test flip in the equivalence gate |
| premultiplied alpha | NOT live today (`backgroundAlpha` 1, every measured pixel 255 — though `toDataURL` still hands back an RGBA PNG). Live the day a background is translucent: the drawing buffer is premultiplied, the PNG is not, the screenshot composites over the page's white; all three agree only at alpha 255 | `opaque_rgb` **refuses** any pixel below 255 — never blends |
| `renderer.extract` | re-renders the stage into a render texture that is NOT multisampled — a different picture | the hook reads `app.view` |
| raw RGBA over CDP | 8 MB/frame at 1080p: 830-950 ms/f via in-page base64, 5.9 s/f via Playwright's typed-array serialisation (measured) | the PNG data URL is the transfer encoding (~45 KB) |
| seek order | before an#185 the pose was not a pure function of t: t=0 after t=0.967 differed from a fresh t=0 by 122 px on `single_character` (an ended clip stopped writing, so its node kept the last SEEK's value) | closed at the source: `anSetTime` restores every animated key nothing has started writing to what `anLoadScene` built, and an ended clip holds its END value — so a clip ending between frames now lands on its end value where it used to stop at its last sampled frame (a deliberate change; no golden-corpus clip ends off the grid) — and of keys writing one thing on a node (the swap sets of one visual) only the latest write survives (spec: `timeline.evaluate_timeline`). Guard: `tests/test_pure_pose.py` — node parity, forward-order == pure on every corpus frame (why no golden moved), and every corpus frame captured forward then backward in one page. Instants are still seeked frame then sample, because the page echoes frame numbers in that order |
| dropped / reordered frames | a frame in the wrong file muxes, plays, and is wrong | the page echoes frame numbers; a reply that is not exactly the request writes nothing; every frame 0..N-1 must be written once |
| unbounded buffering | a fast page and a slow encoder hold the whole shot in memory | at most `DEFAULT_CANVAS_MAX_INFLIGHT` frames wait on the pool; the loop blocks on the oldest |
| bytes per round trip | a frame COUNT bounds nothing when a frame is a k-times, many-sample, incompressible canvas: a grain pack at supersample 2 x an 8-sample shutter overflowed the driver's string limit in one reply and the render hung in `browser.close()`; supersample 3 took ~16 GB of Python (an#192 review) | round trips and the encode pool are ALSO bounded in captured pixels (`DEFAULT_CANVAS_BATCH_PIXELS`, two 1080p instants; the pool twice that — at 1080p the batch size does not matter for a flat scene and decides everything for grain: 11.0 s / 0.38 GB at 2 against 17.8 s / 2.1 GB at 8); a frame whose instants alone exceed it is split over round trips and encoded once; `canvas_frame_png` resolves each sample as it decodes it, so one k-times canvas is alive at a time |
| decode/encode cost | ~40-60 ms/f of Pillow at 1080p, the same order as the page's own work | runs on `DEFAULT_CANVAS_ENCODE_WORKERS` threads while the page renders the next batch; Pillow-native alpha check and drop (a numpy `[..., :3]` copy was ~5x slower) |

**The gate** is `tests/test_canvas_capture_equivalence.py` (browser + ffmpeg):
every golden-corpus scene rendered both ways, every frame's decoded array and the
delivered mp4 compared; a 3-shot, 288-frame render in a parallel pool of 3; and
supersample 2 with a 3-sample open shutter through `CutoutRenderer` directly.
**The default flipped to `"canvas"` in an#192**, after that gate held on a
developer machine AND the labelled Linux lane (an#189), and again on the flip
itself. The bench records the resolved path as each scene's
`provenance.capture`, beside `wall_seconds`: no metric moves across the flip,
but timings on either side of it are not comparable.

**Cost** (M1 Max, a heavily loaded machine — load average 120-230 on 10 cores —
so read ratios, not absolutes; interleaved, medians):

- **Golden corpus, 11 scenes, 2 rounds**: the frame stage (`_capture_frames`)
  **29.3 s -> 3.8 s (7.8x)**, ~100 ms/f -> ~12 ms/f at 320x240, where the
  element screenshot's fixed per-call cost is everything. Whole-render
  wall-clock only **462 s -> 383 s (1.2x)**: at corpus size, browser launch,
  compile, audio and ffmpeg dominate, and under that load they are noisy
  (one scene read the other way).
- **1080p, `single_character`, 3 rounds**: frame stage **186 -> 76-82 ms/f
  (~2.3x)**. Here the page's own `toDataURL` (~45 ms/f) and the Python
  decode/re-encode (~40-60 ms/f of CPU, overlapped on the pool) are real work.
- The in-page encoder is the next cost: a readback that reaches Python as
  pixels without a PNG round trip would need a faster channel than CDP (§2b
  table, raw RGBA row).

**`-tune animation`** — measured at **0.8%**. Dropped: it is not a wave, and
adding it moves `x264_argv` and refuses every encode-side metric for nothing.

**Reading the factor off the corpus.** At 320x240 the k ladder reads 1.0x / 1.3x /
1.8x because fixed costs dominate. Read cost off the 1080p ladder: **k=1 0.126
s/frame, k=2 0.319 (2.54x), k=3 0.640 (5.09x)** — sub-quadratic, so the k² worry
is overstated, but the corpus cannot inform the choice.

---

## 3. Every encoder flag, and why it is there

`DETERMINISTIC_X264_ARGS` in `an/media/mp4.py` (moved from
`an/stage/render.py` in an#247, whose old names are LIVE aliases), plus three literals
`mux_frames` (old name `_ffmpeg_mux`) spells inline. **None of these is a default someone liked** — each
is a named constant with a recorded reason.

| flag | why | note |
|---|---|---|
| `-threads 1` | x264's frame-threading is nondeterministic; one thread is what makes an encode reproducible | |
| `-crf 23` | libx264's compiled-in default, **pinned so a build cannot change it silently** | passing it changes nothing today — which is why "an SSIM test fails when CRF is removed" is unsatisfiable |
| `-preset medium` | same: the compiled-in default, pinned | |
| `-vf scale=out_range=tv:out_color_matrix=bt709` (`an.base.BT709_SCALE_FILTER`) | **the conversion, STATED.** an#148: the row below is true on ffmpeg 8/9 and **false on ffmpeg 6.1** — the CI runner's apt build — where the same flags reach only the VUI, so `an` shipped BT.601 planes tagged BT.709. Measured through `_ffmpeg_mux` on flat colours, decoded as raw `yuv420p`: pure red is Y=81 on 6.1.6 and Y=63 on 9.0.1, against BT.601's 81.5 and BT.709's 62.6 | byte-identical to the pre-an#148 output on ffmpeg 9. **The bench's lossless leg carries the same filter** — `an/bench/imageio.py::lossless_encode_command` — or it stops being "the planes libx264 received" and every encode-side metric absorbs the difference as encoder damage |
| `-colorspace bt709` | **changes the encoded planes — on some builds.** Untagged, `an` converted with BT.601 all along; forcing `scale=out_color_matrix=bt601` reproduces the old output byte-for-byte, on ffmpeg 8/9. Kept for the tag it lands; no longer the thing that decides the conversion | the row above is why this row is not sufficient on its own |
| `-color_primaries` / `-color_trc bt709` | **do not reach the bitstream** on their own — ffprobe reports `unknown` for both | kept so the ffmpeg-level intent is explicit |
| `-color_range tv` | a **no-op today** (limited range is already the yuv420p default), pinned so a differently-defaulting build cannot change the output silently | |
| `-x264-params colorprim=…:transfer=…:colormatrix=…` | **this** is what lands all three in the VUI, and it leaves the decoded stream identical | a half-tagged file is worse than an untagged one: the player stops guessing the matrix but still guesses the primaries |
| `-pix_fmt` (`an.stage.render.DEFAULT_PIX_FMT`, per render via `--pix-fmt`) | **the first-order quality lever, and the default is a product constraint, not an encoder-tuning one.** High 4:4:4 Predictive is refused by many hardware decoders, browsers and platforms — flipping the default would hand a design partner a file they cannot play. Read as a MODULE GLOBAL at call time, which is the seam the `pix_fmt` bench lever pulls; a default argument would sever it | 4:4:4 opt-in since an#59, and measured inside the panel: `chroma_edge_dCr` -21% to -75% on every scene |
| `-c:v libx264` (literal) | | |
| `-movflags +faststart` (`an.base.MP4_FASTSTART_ARGS`) | moov atom first, so a browser can start playing before the file finishes downloading | must be re-asked for on **every** leg — `_ffmpeg_mux`, `_ffmpeg_add_audio` AND `_ffmpeg_concat`. `-c copy` re-lays the container and writes `moov` last. Deliberately **not** in `DETERMINISTIC_X264_ARGS`: that tuple is a comparability key and this flag moves no metric. Two further literal copies exist and are out of scope — `cutan/characters/record.py:146` and `an/bench/imageio.py:184` (the latter must stay import-bound; see §4) |

Why the colour tags matter at all: untagged, the *player* picks its matrix by a
height heuristic (BT.601 below ~576 lines). Every shipped `an` example is 320x240
to 640x360, so encode and playback agree **by luck**; at 1080p the same code would
encode BT.601 and be displayed BT.709 — a silent, resolution-dependent colour error.

### There is a third, undeclared x264 site

`cutan/characters/record.py` hand-builds `libx264 / yuv420p / -crf <param> /
+faststart` and does **not** use `DETERMINISTIC_X264_ARGS`. Any "one mux call, no
literals" refactor that only touches `adapters/cutout/render.py` leaves that
divergent copy behind. `an/bench/imageio.py::lossless_encode_command` is a
fourth site, but a deliberate one — and since an#72 it is deliberate in **two
opposite directions at once**, which is the whole point of it:

- It derives `DETERMINISTIC_X264_ARGS` from the tuple at *import* time,
  precisely so the lossless reference **cannot** be moved by a lever (see §4).
  That is what keeps `-crf` out and `-qp 0` in.
- It takes its `-pix_fmt` from the **delivered mp4 itself**, probed with
  `imageio.delivered_pix_fmt` and threaded in by
  `run.lossless_reference(delivered=…)`, so the reference **must** move with
  the delivery. `-pix_fmt` is not an encoder setting: it names what libx264
  *receives*, and being what libx264 received is this leg's entire purpose. A
  leg pinned to `yuv420p` against a 4:4:4 delivery is not a lossless reference,
  it is a different colour pipeline, and every encode-side metric measured
  against it silently acquires the 4:2:0 conversion the reference exists to
  cancel.

**Why a probe and not a re-derivation**: there are *two* seams that set the
delivered format — `RenderContext.pix_fmt` (what `an render --pix-fmt` uses,
passed straight to `_check_pix_fmt` by `render.render`) and the
`DEFAULT_PIX_FMT` module global, which is only its fallback (and which no
registered lever rebinds — `MUTATIONS` has three and `pix_fmt` is not one). A leg that
consults either one covers only that one; an#72's first fix consulted the
global and silently re-pinned on the path a user can actually reach, with every
guard green. Only the file knows which seam won.

---

## 4. Two bench levers are pinned to the exact shape of this code

**Since an#247 the seams live in the core**: the argv and pixel format in
`an.media.mp4` (rebinding the old `an.stage.render` names still lands
there — they are live aliases, `an/_shims.py`; a plain re-export would have
disarmed both levers silently), and the frame-stage seam the `supersample` lever
wraps is `an.engines.capture.capture_frames`, which `frame_stage_renderer` reads
as a module attribute at call time.

The measurement instrument reaches this pipeline **from the outside**, through
seams the product code has by accident of style. Break the style, disarm the
instrument — and it disarms *quietly* in one case.

- **`high_crf` needs `_ffmpeg_mux` to keep reading `DETERMINISTIC_X264_ARGS` as a
  module global at call time.** The lever rebinds the module attribute. Hoisting
  the tuple into a default argument (`def _ffmpeg_mux(..., x264=DETERMINISTIC_X264_ARGS)`)
  binds it at *def* time and the lever silently stops reaching the encode — which
  reads exactly like an instrument that cannot see a CRF change.
- **`disabled_aa` string-matches the literal `antialias: true`** in `runtime.js`
  and refuses unless it finds **exactly one**. Reformatting the PixiJS options
  object breaks it *loudly*, by design — but you will hit it, so expect it.

When adding options to that object, add them **beside** `antialias: true` without
reflowing the line, and keep the count at one.

---

## 5. The shot cache — `mall["shot_cache"]`, keyed by content (an#242)

`render_project` reuses a shot whose key has an entry (ADR 0004 first slice;
`an/build/`, the cut-out keyer in `an/stage/cache_key.py`). Rules for
anyone touching the frame path:

- **A new per-render knob must reach the key.** `cache_key.render_knobs` lists
  every `RenderContext` field the render reads, RESOLVED as the render resolves
  it (`_check_pix_fmt(None)` is the module default at call time). A knob that
  changes pixels and is missing there is a stale-render bug: the old mp4 is
  reused. `tests/test_shot_cache.py` pins `compiled_document` against what
  `CutoutRenderer.render` passes `compile_shot`; extend `render_knobs` in the
  same PR as the knob.
- **Python-side render code is in the key automatically**: the `code` part
  digests every module `an.stage.render` reaches (walked from its
  imports; compile-side modules are excluded in `RENDER_PATH_EXCLUDED`, each
  with its reason). A new module the render path imports is covered; a new
  EXCLUSION needs a reason that its change reaches another part. The runtime
  is `runtime_sha256`, the argv the knobs part, the machine (incl. the x264
  build) the environment digest. `SHOT_KEY_IMPL_VERSION` is only for changes to
  the key's own composition.
- **`render()` is cold by default; only `render_project` caches.** The bench,
  the golden corpus, the cross-arch capture and the demo builds call `render()`,
  so their wall times are real and a lever that rebinds something outside the
  key (the supersample lever's `_capture_frames`) is never answered from cache.
  Do not flip that default, and keep every measuring call site saying
  `incremental=False` itself (`an/bench/capture.py`, `misc/bench/crossarch.py`,
  `misc/demos/build_demos.py`; pinned by `tests/test_shot_cache.py`) — never
  inside `BENCH_RENDER_KWARGS`, which is recorded into ledger rows and compared.
- `mall["shots"]` (`artifacts/shots/<shot.id>.mp4`) is still written on every
  render, reused shots included, and still read by nothing: an archive of the
  latest render per shot id, not a cache. `an iterate` no longer deletes from
  it — invalidation is by digest.
- `artifacts/` is kept by the bench's copy (`IGNORED_ON_COPY`), so a fixture
  carries its `shot_cache/` into a capture; harmless, because `render()` neither
  reads nor writes it.

---

## 6. Where a per-render knob goes, and why it matters more than it looks

Simulated against a real committed ledger row, for a supersample factor:

| placement | consequence |
|---|---|
| `render_kwargs` | it becomes a `COMMON_ENV_PATHS` key → **all 96 metrics refused, no answer at all** |
| a field on the compiled scene JSON | `scene_contract_sha256` moves → **every scene incomparable** |
| **a `RenderContext` field, outside the scene document** | only `runtime_sha256` moves, which is deliberately *not* a comparability key → **30 render-side entries still compare** |

**Put product knobs on `RenderContext`.** It needs no `SCHEMA_VERSION` migration,

The one deliberate exception is `step_hz` (an#89): it lives on `RenderContext`
AND is stamped on the compiled scene's `meta`, because unlike a supersample it
*changes the compiled document* — the resampled keyframes are the contract, so
the hash moves whenever it is set no matter where the knob lives. It is
serialized only when set, so the unset case stays free.
and the knob **must** also be written into per-shot provenance (the dict returned
by `CutoutRenderer.render`, beside `resolution` / `x264_args` / `chromium_args`) —
a row that does not record it cannot be read back later.

The same rule holds for `-pix_fmt`: it is a per-render product knob, not a scene
property.

---

## 7. `an preview` is not the render path

`an/stage/preview.py` reuses the runtime in a live-reloading page. The two paths share
`runtime.js` but **load different HTML** — `index.html` for the render,
`preview.html` for the preview — and that split is already load-bearing and
already enforced: `an.determinism.CAPTURE_PAGE` refuses a render captured from
`preview.html`, because that page carries seven clock calls. So a
render-path-only page property belongs in `index.html`, not behind a runtime
flag; there is no need to invent a query param or a global.

The question this section used to be about is now closed the other way: **nothing
the render path can do stops Chromium compositing the canvas, because the
element screenshot IS the compositor's output.** See §2.

---

## 8. Cost and what is still unmeasured

Costs above are per frame at 1080p. Memory is the unpriced axis: renders fan out
one browser context per shot at a default cap of 4, and the backbuffer scales k²
per context — ~33 MB per context at k=2, ~75 MB at k=3. **Nobody has costed
`parallel x supersample`.**

Also still unmeasured, from `wave3_research.md` §7 — do not assume any of these:

- **Cross-arch pixel identity at a larger backbuffer.** The cross-arch verdict was
  measured at 1x with MSAA 4. It gates whether goldens rendered at k=2 can stay a
  CI gate.
- ~~Whether the compositing win grows with k.~~ **MOOT until the capture path
  changes** — the win is unrealisable while frames come from an element
  screenshot (§2). Worth re-asking only inside an in-page-capture PR, where the
  measured contribution at 1x is 1.09x. The canvas path (§2b) is the
  default since an#192, but still shares `index.html` with the screenshot
  path, which needs the canvas composited — so hiding it means making the
  guard (`test_the_capture_page_never_stops_compositing_the_stage_canvas`) and
  its mutant conditional on the capture path. Not done yet.
- ~~`-f concat -c copy -movflags +faststart` on the pinned ffmpeg build.~~
  **SETTLED — it is a remux, not a transcode** (ffmpeg 8.1, Homebrew, macOS
  arm64, an#57). The concatenated elementary stream is sha256-identical to the
  inputs' streams appended; video packet total, file size, decoded YUV and wall
  time are all unchanged; only the `moov` offset moves. It does **not** create
  the double encode epic #9 wrongly describes.
- 4:4:4 playback compatibility, for the `-pix_fmt` knob's documentation.
- **NEW, and it is the real cost centre:** the Playwright element screenshot is
  **100 ms/frame at 1080p** against `toDataURL`'s 10 ms — a 10x gap that is
  neither GPU readback nor PNG encode (both paths pay those). Playwright's
  `_preparePageForScreenshot` runs `safeNonStallingEvaluateInAllFrames` plus an
  `await document.fonts.ready` on **every call**. Nobody has attributed the
  100 ms, and it is the largest single number in the frame path.

## 9. Standing rules for anything in this file's scope

1. **Never write that a rendering behaviour is "verified in CI."** Say which lane:
   a developer machine, a labelled PR, or an on-demand run.
2. A change that moves a pixel needs the `run-browser-tests` label (§ header).
3. A default chosen by taste ships **opt-in**, with a committed A/B, and the flip
   is its own one-line PR.
4. A knob that affects output and is not recorded in provenance is a
   cache-poisoning vector, not merely an imprecision.
5. **`runtime.js`'s evaluator is held to the timing contract** (an#233). A change
   to `evaluateChannel`, `evaluateTimeline`, `applyEasing`/`EASINGS` or `wrapTime`
   must still reproduce every case of `an/data/timing/timing_vectors.json` — the
   `stage.node` ones by value type, the inline-space ones in their declared space
   (an#287: `meta.entity_spaces` + `meta.spaces`; `tests/test_timing_contract.py`,
   node-run, and `tests/test_stage_engine.py`, in the browser),
   and the Python side must pass `python -m an.timing.contract check`. A kernel
   change is gated on four checks: contract hashes, parity, pure-pose, pixel goldens.
