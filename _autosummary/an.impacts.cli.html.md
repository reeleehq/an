# an.impacts.cli

`an impacts ...` — the impact harness from the shell.

Thin string-typed wrappers over [`an.impacts.clip`](an.impacts.clip.html.md#module-an.impacts.clip), dispatched by typer the
same way as `an character ...`: the business logic stays in plain functions
that take real types, and these only parse the list-valued flags.

> an impacts clip ~/.local/share/thoremin/synthetic –kind air –fps 30 –exposure 0.5
> an impacts clip-set ~/.local/share/thoremin/synthetic/set-v1 –fps 24,30,60

### Functions

| [`clip`](#an.impacts.cli.clip)(out_dir[, object, kind, tempo, beats, ...])   | Write one impact clip (video + ground truth) under OUT_DIR.            |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`clip_set`](#an.impacts.cli.clip_set)(out_dir[, objects, kinds, fps, ...])      | Write a benchmark set (the product of the given axes) plus index.json. |

### an.impacts.cli.clip(out_dir, object='stick', kind='surface', tempo='100', beats=16, subdivision=1, pattern='1', lead_in=0.5, tail=0.5, jitter_sd=0.008, jitter_rho=0.0, jitter_bias=0.0, fps=30.0, exposure=0.0, exposure_samples=0, timestamp_jitter_sd=0.0, timestamp_noise_sd=0.0, phase=0.0, timestamps='nominal', width=640, height=360, seed=0, render=True)

Write one impact clip (video + ground truth) under OUT_DIR.

out_dir: parent directory; the clip gets its own sub-directory
object: stick or ball
kind: surface (contact) or air (the stroke turns with nothing to hit)
tempo: a bpm, or beat:bpm pairs for a tempo change, e.g. 0:90,16:120
beats: number of beats
subdivision: grid steps per beat
pattern: per-step stroke heights, cycled; 0 is a rest, e.g. 1,0.5,0.8,0.5
lead_in: seconds before the first beat
tail: seconds after the last beat
jitter_sd: humanisation, seconds (standard deviation of the timing offset; 0 = metronome)
jitter_rho: correlation of consecutive offsets (0 = independent)
jitter_bias: constant lead (negative) or lag (positive), seconds
fps: frame rate (need not be an integer)
exposure: fraction of the frame period the shutter is open (0.5 = 180 degrees)
exposure_samples: instants averaged per open exposure (0 = automatic)
timestamp_jitter_sd: seconds of jitter in WHEN each frame is captured
timestamp_noise_sd: seconds of noise on the REPORTED timestamp only
phase: sub-frame offset of the camera clock, seconds
timestamps: what keypoints.ndjson reports as t: nominal or actual
width: frame width in pixels
height: frame height in pixels
seed: random seed (performance and camera streams derive from it)
render: render the mp4; –no-render writes the truth and keypoints only

* **Return type:**
  `str`

### an.impacts.cli.clip_set(out_dir, objects='stick,ball', kinds='surface,air', fps='24,30,60', exposures='0,0.5', timestamp_jitter_sds='0', seeds='0', render=True)

Write a benchmark set (the product of the given axes) plus index.json.

Every clip shares one performance per seed — an accelerando from 96 to 132
BPM over 24 beats, accented, with 12 ms of drifting human timing — so clips
differ only in object, kind and camera.

out_dir: directory for the set
objects: comma-separated, from stick,ball
kinds: comma-separated, from surface,air
fps: comma-separated frame rates
exposures: comma-separated shutter fractions
timestamp_jitter_sds: comma-separated capture-jitter standard deviations (s)
seeds: comma-separated performance seeds
render: render the videos; –no-render writes the truth and keypoints only

* **Return type:**
  `str`
