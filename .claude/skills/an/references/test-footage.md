# Controlled test footage

Reference for the `an` skill (`../SKILL.md`: the index and the essentials).

## When the user wants controlled test footage (impacts, timing ground truth)

`cutan.impacts` generates structured clips of a stick or ball striking a surface, or striking the air (a braked stroke with no contact), on a known tempo grid — with a sidecar keeping the **intended** grid time (`t_grid`), the **executed** impact time (`t_impact`, continuous seconds) and **what each frame shows** (exposure interval, sample instants, keypoints) apart. Use it when someone wants to test whether events can be recovered beyond the frame rate; do not hand-author such scenes.

- `an impacts clip OUT --kind air --fps 30 --exposure 0.5 --jitter-sd 0.012 [--tempo 0:90,16:120] [--no-render]`; `an impacts clip-set OUT --fps 24,30,60` for a benchmark set with `index.json`.
- Python: `write_impact_clip(ImpactClipSpec(...), out_dir, render=True)`; `plan_impact_clip(spec)` for the events/stroke/frames without I/O. `render=False` needs no browser.
- The camera is `an.frame_clock.FrameClock` (fps, exposure, samples, jitter_sd = when frames are taken, report_noise_sd = noise on the reported timestamp, phase, timestamps), reaching the renderer as `RenderContext.frame_samples` — usable for motion blur on any render. With an open shutter a frame's keypoints are the AVERAGE over its exposure; `keypoints_mid` is the mid-exposure position.
- Schema: the `cutan/impacts/truth.py` module docstring.
- Write rendered sets OUTSIDE any repo (e.g. `~/.local/share/<project>/synthetic/`); they are data.
