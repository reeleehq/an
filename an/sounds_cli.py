"""``an sounds …``: the project's sounds store from the shell (an#318).

Thin projections of :mod:`an.sounds` and :mod:`an.sound_fetch`, wired into the
CLI by :data:`an.tools._dispatch_namespaces`.
"""

from __future__ import annotations

__all__ = ["add"]


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
    """Add a sound to the project from a URL (a YouTube page, any page yb reads), with its provenance.

    The audio is fetched with yb (pip install yb yt-dlp), cut with ffmpeg and
    stored as WAV; the source records the page, its id, title and channel, the
    cut, and the licence you give — `an credits` lists it as "0:07.9–0:08.8 of <url>".

    project_dir: the an project
    key: the sound's key in the project's sounds store (what a cue names)
    url: the page the sound is on
    license: the licence code you vouch for (required; "unknown" records that nobody has said, and the sound is UNVERIFIED)
    start: seconds into the media where the cut begins
    duration: seconds kept (default: to the end)
    fade_out: seconds of fade at the end of the cut
    provider: override the provider the page reports (default: youtube, or the host)
    author: override the author the page reports (default: its channel)
    description: what the sound is, for the store
    """
    from an.sound_fetch import add_sound_from_url
    from an.stores import build_project_mall

    if not license:
        raise SystemExit(
            "an sounds add: --license is required (the code you vouch for; "
            "'unknown' records that nobody has said, and the sound is UNVERIFIED)"
        )
    mall = build_project_mall(project_dir, ensure=True)
    asset = add_sound_from_url(
        mall["sounds"],
        key,
        url,
        license=license,
        start=start or None,
        duration=duration or None,
        fade_out=fade_out or None,
        provider=provider or None,
        author=author or None,
        description=description,
    )
    return f"sounds/{key}: {asset.duration:.2f} s from {asset.source.url} [{asset.source.license or 'unknown'}]"


_dispatch_funcs = [add]
