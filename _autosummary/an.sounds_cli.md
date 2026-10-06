# an.sounds_cli

`an sounds …`: the project’s sounds store from the shell (an#318).

Thin projections of [`an.sounds`](an.sounds.md#module-an.sounds) and [`an.sound_fetch`](an.sound_fetch.md#module-an.sound_fetch), wired into the
CLI by `an.tools._dispatch_namespaces`.

### Functions

| [`add`](#an.sounds_cli.add)(project_dir, key, url[, license, start, ...])   | Add a sound to the project from a URL (a YouTube page, any page yb reads), with its provenance.   |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|

### an.sounds_cli.add(project_dir, key, url, license='', start=0.0, duration=0.0, fade_out=0.0, provider='', author='', description='')

Add a sound to the project from a URL (a YouTube page, any page yb reads), with its provenance.

The audio is fetched with yb (pip install yb yt-dlp), cut with ffmpeg and
stored as WAV; the source records the page, its id, title and channel, the
cut, and the licence you give — `an credits` lists it as “0:07.9–0:08.8 of <url>”.

project_dir: the an project
key: the sound’s key in the project’s sounds store (what a cue names)
url: the page the sound is on
license: the licence code you vouch for (required; “unknown” records that nobody has said, and the sound is UNVERIFIED)
start: seconds into the media where the cut begins
duration: seconds kept (default: to the end)
fade_out: seconds of fade at the end of the cut
provider: override the provider the page reports (default: youtube, or the host)
author: override the author the page reports (default: its channel)
description: what the sound is, for the store

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
