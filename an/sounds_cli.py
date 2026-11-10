"""``an sounds …``: the project's sounds store from the shell (an#318).

Thin projections of :mod:`an.sounds` and :mod:`an.sound_fetch`, wired into the
CLI by :data:`an.tools._dispatch_namespaces`.
"""

from __future__ import annotations

__all__ = ["add", "sync"]


def add(
    project_dir: str,
    key: str,
    url: str,
    license: str = "",
    start: float = 0.0,
    duration: float = 0.0,
    fade_out: float = 0.0,
    provider: str = "",
    author: str = "",
    description: str = "",
) -> str:
    """Add a sound to the project from a URL (a YouTube page, any page yb reads) or a foley library (foley:<sound_id>), with its provenance.

    The audio is fetched with yb (pip install yb yt-dlp), or exported by foley
    for a foley:<sound_id> ref, cut with ffmpeg and stored as WAV; the source
    records the page, its id, title and channel, the cut, and the licence you
    give — `an credits` lists it as "0:07.9–0:08.8 of <url>". A foley sound
    carries its own rights (licence, credit, an AI disclosure), so --license may
    be left out; one that disagrees is refused.

    project_dir: the an project
    key: the sound's key in the project's sounds store (what a cue names)
    url: the page the sound is on, or foley:<sound_id>
    license: the licence code you vouch for (required unless the source states its own, as a foley sound does; "unknown" records that nobody has said, and the sound is UNVERIFIED)
    start: seconds into the media where the cut begins
    duration: seconds kept (default: to the end)
    fade_out: seconds of fade at the end of the cut
    provider: override the provider the page reports (default: youtube, or the host)
    author: override the author the page reports (default: its channel)
    description: what the sound is, for the store
    """
    from an.sound_fetch import UNSTATED, add_sound_from_url
    from an.sounds import SoundError
    from an.stores import build_project_mall

    mall = build_project_mall(project_dir, ensure=True)
    try:
        asset = add_sound_from_url(
            mall["sounds"],
            key,
            url,
            license=license or UNSTATED,
            start=start or None,
            duration=duration or None,
            fade_out=fade_out or None,
            provider=provider or None,
            author=author or None,
            description=description,
        )
    except SoundError as e:
        raise SystemExit(f"an sounds add: {e}") from e
    return f"sounds/{key}: {asset.duration:.2f} s from {asset.source.url} [{asset.source.license or 'unknown'}]"


def sync(project_dir: str, key: str, at: str = "auto") -> str:
    """Record where a sound's hit is, so a cue puts the hit (not the file's first sample) at its `at`.

    A clip whose clink comes after a scrape, or after silence, is heard late by
    that lead-in when it is cued by its first sample; `an validate` warns when
    a cued hit is 125 ms or more into its file. Only sound.json changes.

    project_dir: the an project
    key: the sound's key in the project's sounds store
    at: seconds into the file, "auto" to measure it (the first 10 ms within 6 dB of the loudest), or "none" to clear it
    """
    from an.sounds import SoundError, set_sync
    from an.stores import build_project_mall

    mall = build_project_mall(project_dir)
    value: float | str | None
    if at.lower() == "auto":
        value = "auto"
    elif at.lower() == "none":
        value = None
    else:
        try:
            value = float(at)
        except ValueError:
            raise SystemExit(
                f"an sounds sync: --at {at!r}: say seconds, auto or none"
            ) from None
    try:
        asset = set_sync(mall["sounds"], key, value)
    except (SoundError, KeyError) as e:
        raise SystemExit(f"an sounds sync: {e}") from e
    if asset.sync is None:
        return f"sounds/{key}: no sync point (a cue places its first sample)"
    return f"sounds/{key}: its hit is {asset.sync:.2f} s into the file; a cue's `at` is the hit"


_dispatch_funcs = [add, sync]
