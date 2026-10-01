# an.bench.imageio

The pinned ffmpeg decodes, and the lossless leg every encode-side metric
is measured against.

\*\*The reference is the lossless encode, not the PNGs — and that is a
correction, made because CI caught the alternative.\*\* The obvious design reads
the source frames back with an explicit conversion
(`-vf scale=out_range=tv:out_color_matrix=bt709 -pix_fmt yuv444p`) and compares
the delivered mp4 against that. Measured against a mathematically lossless
(`-qp 0`) encode of the same frames, that conversion agrees **exactly** on
ffmpeg 8.1 (luma residual 0.0000, max 0) and **does not** on the Linux runner’s
older build (0.6290, max 5). A floor of 0.63 is 42% of `coded_luma_edge_error`’s
whole crf23 value, so on that build every encode-side luma number would have
been measuring a colour-conversion disagreement and reporting it as encoder
damage.

The fix is not a tolerance. It is to stop having a second conversion at all:
`-qp 0` is lossless, so \*\*the qp0 decode’s luma plane IS the plane libx264
received\*\*, on every build, by definition. Referencing the metrics to it
removes the assumption instead of widening it, and it costs nothing extra —
`encode_ringing_excess` already needed that leg.

\*\*That “IS” is a claim about the leg’s INPUT FORMAT as much as its rate
control\*\*, and the leg pinned `-pix_fmt yuv420p` until an#72. Against a 4:4:4
delivery the reference was therefore a *different colour pipeline* from the file
it referenced, and every metric measured against it carried the whole 4:2:0
conversion this leg exists to cancel — as a term that does not cancel and does
vary by build.

The leg now takes its format from the **delivered file itself**
(`delivered_pix_fmt`, threaded in by `run.lossless_reference`). Probing rather
than re-deriving is the load-bearing part: **two** seams set the delivered
format — `RenderContext.pix_fmt`, which `an render --pix-fmt` uses and which the
mux resolves FIRST, and the `DEFAULT_PIX_FMT` module global, which is only its
fallback. A leg that consults either one covers only that one, and an#72’s first
fix consulted the global — so it silently re-pinned on the seam a user can
actually reach, with every guard green.

(No `pix_fmt` lever exists: `MUTATIONS` is `high_crf`/`disabled_aa`/`supersample`
and `_check_registered` enforces it at import. The global’s seam is kept for a
lever that has never been registered — see `an-dev-bench`’s `pix_fmt` row for why
— and outside the product it is driven only by tests. So “the lever rebinds it”
is a statement about a seam’s purpose, not about anything that runs.)

Note which metrics the mismatch reached: `flat_field_deviation`,
`flat_field_p99_dev` and `encode_flicker_on_held_pixels` reduce over RGB, so
chroma reaches them, while the luma-domain metrics never moved —
`coded_luma_edge_error` and `encode_ringing_excess` are identical to the last
digit between a 4:2:0 and a 4:4:4 leg on all ten corpus scenes.

Two things this does NOT change:

- **The chroma metric still references the direct RGB->444 conversion**, because
  its subject *is* the 4:2:0 subsampling that happens during the conversion —
  which is exactly the term this leg cancels, so a lossless-referenced version
  is blind to it whatever format the leg is encoded in. (With a tracking leg
  and a 4:4:4 delivery, both legs are 4:4:4 and the subsampling does not exist
  to be measured; tracking makes the panel honest, not sighted.) It does **not**
  read ~0, though, and that half of the old wording was wrong: measured
  2026-08-29 on four scenes, mean 

  ```
  |dCr|
  ```

   over the edge mask reads 1.71 / 1.90 /
  2.24 / 2.50 against the shipped metric’s 7.19 / 9.29 / 8.04 / 2.93, because it
  measures chroma *quantiser* damage instead (an#72).
- \*\*The PNG conversion is still performed and its distance from the encoder’s
  input is still recorded\*\* (`png_to_encoder_input_luma`), because that number
  is exactly the build-dependence that was hiding inside a hard equality. It is
  provenance now, not a gate.

**an#148 names what the build-dependence WAS, and both legs now pin it.** The
varying term was never this PNG leg — it was the *encoder’s* conversion:
`-colorspace bt709` sets the auto-inserted RGB->YUV matrix on ffmpeg 8/9 and
reaches only the VUI on ffmpeg 6.1, so on 6.1 libx264 received BT.601 planes
while the delivered file was tagged BT.709 (pure red at Y=81, against BT.709’s
62.6). `lossless_encode_command` therefore carries `-vf BT709_SCALE_FILTER`, the
same filter the delivered mux now passes: a lossless leg that converts
differently from the file it references is not “the plane libx264 received” on
any build where the two disagree, whatever its rate control. Keeping the two
spellings identical is why `SOURCE_SCALE_FILTER` is *bound* to
`an.base.BT709_SCALE_FILTER` rather than restating it.

`-map 0:v:0 -fps_mode passthrough` on every mp4 decode: the delivered file
carries an AAC track, and implicit frame-rate conversion would silently re-time
the sequence that every encode-side metric pairs frame-for-frame.

### Module Attributes

| [`SOURCE_SCALE_FILTER`](#an.bench.imageio.SOURCE_SCALE_FILTER)   | without it the encode-side metrics measure a colour-space conversion.                                                                                                                                    |
|------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`YUV_PIX_FMT`](#an.bench.imageio.YUV_PIX_FMT)           | 4 for both legs of every encode-side metric — never `rgb24` for the edge metrics, whose defect was clipping precisely at the saturated fills sitting against black outlines that flat 2D art is made of. |

### Functions

| [`decoded_rgb`](#an.bench.imageio.decoded_rgb)(mp4, \*, height, width)               | `(N, H, W, 3)` uint8 of the delivered mp4.                                      |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`decoded_rgb_command`](#an.bench.imageio.decoded_rgb_command)(mp4)                          | Decode the delivered mp4 to raw RGB.                                            |
| [`decoded_yuv`](#an.bench.imageio.decoded_yuv)(mp4, \*, height, width)               | `(N, 3, H, W)` uint8 planar YUV of the delivered mp4.                           |
| [`decoded_yuv_command`](#an.bench.imageio.decoded_yuv_command)(mp4)                          | Decode the delivered mp4 to planar YUV.                                         |
| [`delivered_pix_fmt`](#an.bench.imageio.delivered_pix_fmt)(mp4)                            | The pixel format `mp4` is actually encoded in, from the file itself.            |
| [`lossless_encode_command`](#an.bench.imageio.lossless_encode_command)(frames_dir, fps, out, \*) | `-qp 0` with otherwise identical flags, for `encode_ringing_excess`.            |
| [`run_raw`](#an.bench.imageio.run_raw)(cmd)                                      | Run an ffmpeg command and return its raw stdout, or raise with the stderr.      |
| [`source_rgb`](#an.bench.imageio.source_rgb)(frames_dir, \*, height, width, frames) | `(N, H, W, 3)` uint8 of the pre-encode PNGs.                                    |
| [`source_rgb_command`](#an.bench.imageio.source_rgb_command)(frames_dir)                    | Decode the pre-encode PNG sequence to raw RGB.                                  |
| [`source_yuv`](#an.bench.imageio.source_yuv)(frames_dir, \*, height, width, frames) | `(N, 3, H, W)` uint8 planar YUV of the pre-encode PNGs, range-pinned.           |
| [`source_yuv_command`](#an.bench.imageio.source_yuv_command)(frames_dir)                    | Decode the pre-encode PNG sequence to planar YUV, **range- and matrix-pinned**. |
| [`video_stream_bytes`](#an.bench.imageio.video_stream_bytes)(mp4)                           | Sum of the video stream's packet sizes — the AAC track excluded.                |

### Exceptions

| [`BenchDecodeError`](#an.bench.imageio.BenchDecodeError)   | ffmpeg could not read something the bench needs.   |
|---------------------------------------------------------------------|----------------------------------------------------|

### *exception* an.bench.imageio.BenchDecodeError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

ffmpeg could not read something the bench needs.

### an.bench.imageio.SOURCE_SCALE_FILTER *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'scale=out_range=tv:out_color_matrix=bt709'*

without it
the encode-side metrics measure a colour-space conversion.

**Bound to the product’s own filter, not restated** (an#148). It used to be a
second copy of the same string, which was harmless only while the delivered
encode had no `-vf` of its own to disagree with. Now that it has one, two
copies is one edit away from the PNG leg and the encoder converting
differently — which is exactly the term the encode-side metrics cannot see
and would report as encoder damage.

* **Type:**
  The pinned conversion applied to the PNG leg. Never remove it

### an.bench.imageio.YUV_PIX_FMT *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'yuv444p'*

4 for both legs of every encode-side metric — never `rgb24` for
the edge metrics, whose defect was clipping precisely at the saturated fills
sitting against black outlines that flat 2D art is made of.

* **Type:**
  Planar 4
* **Type:**
  4

### an.bench.imageio.decoded_rgb(mp4, , height, width)

`(N, H, W, 3)` uint8 of the delivered mp4.

`frames=None`: the run deliberately tolerates the encoder emitting a
different count from the source leg and records it as
`frame_count_disagreement`, so an equality here would turn a recorded
disagreement into a crash. See `_reshape()`.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.bench.imageio.decoded_rgb_command(mp4)

Decode the delivered mp4 to raw RGB.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.bench.imageio.decoded_yuv(mp4, , height, width)

`(N, 3, H, W)` uint8 planar YUV of the delivered mp4. `frames=None` — see [`decoded_rgb()`](#an.bench.imageio.decoded_rgb).

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.bench.imageio.decoded_yuv_command(mp4)

Decode the delivered mp4 to planar YUV.

No `scale` filter here, deliberately: the file carries BT.709 tags
(an#34) so ffmpeg already decodes it in the space the source leg is pinned
to. Adding one would convert twice.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.bench.imageio.delivered_pix_fmt(mp4)

The pixel format `mp4` is actually encoded in, from the file itself.

The delivered encode resolves its format from `RenderContext.pix_fmt`
**or** the module global (`render._check_pix_fmt`), and only the file knows
which won — so the lossless leg cannot re-derive it and be sure of matching.
Re-deriving is what an#72’s first fix did, and it covered the bench lever’s
seam (which rebinds the global) while missing the product’s own
(`an render --pix-fmt`, which sets the context and never touches it).

Probed, not remembered: this is the one source of truth that no future seam
can route around.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.bench.imageio.lossless_encode_command(frames_dir, fps, out, , pix_fmt=None)

`-qp 0` with otherwise identical flags, for `encode_ringing_excess`.

Identical to the delivered encode except for the rate control, so the
difference of the two overshoot means cancels the source-hardness term —
which is the whole reason `encode_ringing_excess` replaced raw overshoot.

**Pinned in its ENCODER SETTINGS, tracking in its INPUT FORMAT** — and the
asymmetry is the correction an#72 turned on. Two module globals reach this
command and they must be reached differently:

- `DETERMINISTIC_X264_ARGS` is bound at IMPORT, above, so a lever that
  rebinds it (`high_crf`) cannot move the reference. The reference has to
  stay lossless, or every encode-side metric is measured against a moving
  target and the lever produces beautiful numbers about nothing.
- `pix_fmt` is resolved at CALL time through the product’s own
  `_check_pix_fmt()`. The bench passes the
  > format **probed off the delivered mp4** ([`delivered_pix_fmt()`](#an.bench.imageio.delivered_pix_fmt));
  > `None` falls back to `DEFAULT_PIX_FMT`, which is right for a caller
  > with no delivered file to match and wrong for one that has it.

The difference is not a preference. `-pix_fmt` is not an encoder setting:
it names **what libx264 receives**, and being what libx264 received is this
leg’s entire purpose (see the module docstring). Pinning it does not keep
the reference lossless — it makes the reference a \*different colour
pipeline\* from the delivered file, so every metric measured against it
silently acquires the whole 4:2:0 conversion the reference exists to
cancel. Measured on the corpus at 4:4:4: family E
(`encode_flicker_on_held_pixels`) changes SIGN on three of ten scenes
between a pinned leg and a tracking one — from as-declared to contrary in
every case — and family D (`flat_field_deviation`) moves by up to 24.8
percentage points. The affected metrics are exactly the RGB-domain ones,
which reduce over three channels so chroma reaches them; the luma-domain
metrics were never affected — `coded_luma_edge_error` and
`encode_ringing_excess` are identical to the last digit between a 4:2:0
and a 4:4:4 leg on all ten scenes.

A default (4:2:0) render is byte-identical to before this change, so no
committed ledger row is invalidated.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.bench.imageio.run_raw(cmd)

Run an ffmpeg command and return its raw stdout, or raise with the stderr.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### an.bench.imageio.source_rgb(frames_dir, , height, width, frames)

`(N, H, W, 3)` uint8 of the pre-encode PNGs.

`frames` is how many PNGs are on disk — the caller counted them — and it
is required rather than derived, so the decode cannot silently return a
different number of them.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.bench.imageio.source_rgb_command(frames_dir)

Decode the pre-encode PNG sequence to raw RGB.

RGB is correct here and only here: the two metrics that use it
(`flat_field_deviation`, `encode_flicker_on_held_pixels`) are masked to the
flat interior and to held pixels, both off-edge by construction, so the
clipping that ruins the edge metrics cannot reach them.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.bench.imageio.source_yuv(frames_dir, , height, width, frames)

`(N, 3, H, W)` uint8 planar YUV of the pre-encode PNGs, range-pinned.

* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### an.bench.imageio.source_yuv_command(frames_dir)

Decode the pre-encode PNG sequence to planar YUV, **range- and matrix-pinned**.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### an.bench.imageio.video_stream_bytes(mp4)

Sum of the video stream’s packet sizes — the AAC track excluded.

`file_bytes` includes the audio track, which the renderer always emits
(silent if there is no dialogue), so it varies with the audio cache’s state.
This one does not.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
