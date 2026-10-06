"""Garbage collection of the shot cache: ``an cache gc`` and ``an cache info`` (an#274).

ADR 0004 decision 6: invalidation is by digest, never by deletion, so every
edit leaves the old entries behind — an end user's ``artifacts/shot_cache``
reached 4.9 GB after nine renders of a 16 s film. Collecting them is a
separate, explicit command, and this module is it.

**What is kept (reachable).** An entry is reachable when either

- a render of the project's CURRENT scene would read it — under any knob set
  a recorded render ever used, or under a plain ``an render``'s — computed
  by the render loop's own setup and the engine's own key code, with the
  dialogue stamped from the audio stores as the render stamps it
  (:func:`an.render.cache_entries`); or
- the latest render of an output, under one knob set, on one machine, used it
  — its *root* (:meth:`an.build.ShotCache.record_root`). This keeps what a
  render on ANOTHER machine of a synced project used, which this machine
  cannot recompute (its environment digest differs).

A cache no render of the project has recorded a root in (one written before
an#274) is refused unless ``force``: the current scene's keys alone are then
the only evidence, and a render's knobs or providers that differ from the
defaults would leave its entries looking unreachable.

**A knob set under which the current scene has a line with no audio** (an#306)
— a line edited since the last render under it, or the plain render's
hypothetical knobs for a project only ever spoken by ElevenLabs — has no keys
to compute until that line is synthesised, so nothing in the cache can be its
entry for that shot. It is skipped rather than refused, and what each root
recorded under it is kept whatever ``--max-age`` says, so its unchanged shots
stay. Only when the current scene can be keyed under NO knob set (every one
lacks some line's audio: the scene has lines nothing has synthesised) is the
collection refused — render first. Each knob set is replayed with its OWN
providers (a root's recorded ``tts``), never with a command line's defaults.

Everything else is unreachable: the entries of shots as they were before an
edit, parts cut for an old neighbour, whole-frame entries (``<key>.frames``)
that no render reads since an#260, and unreadable records.

**What is never deleted.** A reachable entry, whatever the caps say (a cap
trims unreachable history only; ``--max-age`` lets an old root stop naming its
entries, never stops its knob set being recomputed). A root. An entry
written after the collection began, or after the start of any render of the
project still in progress (``.an/render_work/runs/<run>/.live``), minus
:data:`CLOCK_SLACK_S`: a render's entries are protected from the moment its
run starts until its root records them. A blob still named by a kept record.

**What a concurrent render can see**, at worst: an entry it looked up being
collected between reading its record and its blob — a miss, so that shot
renders again. Never a wrong picture: every blob is checked against its id
(its sha256) when read, and a reused shot's bytes are copied into the render's
own run directory at lookup, before anything can remove them.

**Deletion is permanent.** ``dol.Files`` would move each file to the OS trash,
which frees nothing (and on macOS asks Finder once per file), so on a
filesystem store the catalog record and the blob are unlinked directly, in the
layout ``lacing.ArtifactStore.from_directory`` documents.

>>> parse_size("2G"), parse_size("500MB"), parse_age("36h"), parse_age("7d")
(2147483648, 524288000, 129600.0, 604800.0)
"""

from __future__ import annotations

import os
import re
import time
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.audio.pipeline import VOICE_TTS, AudioNotCachedError
from an.base import DEFAULT_SUPERSAMPLE
from an.build.shot_cache import (
    FRAMES_SUFFIX,
    PARTS_INFIX,
    ROOT_PREFIX,
    SHOT_CACHE_STORE,
    ShotCache,
    human_bytes,
)

__all__ = [
    "CLOCK_SLACK_S",
    "DEFAULT_PROFILE",
    "HYPOTHETICAL_PROFILES",
    "CacheEntry",
    "CacheGcError",
    "CacheInfo",
    "GcReport",
    "Reachability",
    "cache_info",
    "collect_garbage",
    "inventory",
    "parse_age",
    "parse_size",
    "reachable_entries",
]

#: Seconds before a protection horizon still treated as "after" it: a file
#: system's timestamp granularity, and the gap between a record's provenance
#: time and the moment it lands.
CLOCK_SLACK_S: float = 2.0

#: The render knobs of a plain ``an render`` (and of ``render_project``'s
#: defaults), as :meth:`ShotCache.record_root` records them: ``tts`` is each
#: voice's own provider (an#305). Always among the profiles the current scene
#: is keyed under, so a cache written before roots existed keeps what a plain
#: render of the current scene reads.
DEFAULT_PROFILE: Mapping[str, Any] = {
    "fps": None,
    "resolution": None,
    "strict_assets": False,
    "supersample": DEFAULT_SUPERSAMPLE,
    "pix_fmt": None,
    "capture": None,
    "step_hz": None,
    "tts": VOICE_TTS,
    "lipsync": "offline",
    "language": "en",
}

#: The knob sets a plain render used or uses, recorded by a root or not: today's
#: (:data:`DEFAULT_PROFILE`) and the one before an#305, which spoke every line
#: offline — what a cache written before roots existed was rendered with.
HYPOTHETICAL_PROFILES: tuple[Mapping[str, Any], ...] = (
    DEFAULT_PROFILE,
    {**DEFAULT_PROFILE, "tts": "offline"},
)

_SIZE_UNITS = {"": 1, "B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


class CacheGcError(RuntimeError):
    """The collection cannot be done safely; nothing was deleted."""


def parse_size(text: str) -> int:
    """``"2G"``, ``"500MB"``, ``"1.5GB"``, ``"1048576"`` → bytes (1024-based).

    >>> parse_size("1.5k")
    1536
    """
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([KMGTB]?)B?\s*", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"not a size: {text!r} (try 500MB, 2G)")
    return int(float(m.group(1)) * _SIZE_UNITS[m.group(2).upper()])


def parse_age(text: str) -> float:
    """``"7d"``, ``"36h"``, ``"90m"``, ``"2w"``, ``"30s"`` → seconds.

    >>> parse_age("90m")
    5400.0
    """
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([smhdw])\s*", text, re.IGNORECASE)
    if not m:
        raise ValueError(f"not an age: {text!r} (try 7d, 36h, 90m)")
    return float(m.group(1)) * _AGE_UNITS[m.group(2).lower()]


# -----------------------------------------------------------------------------
# What is in the store
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheEntry:
    """One catalog record: its id, what it holds, its blob, and when it was written."""

    id: str
    role: str
    asset_id: str | None = None
    bytes_size: int = 0
    written_at: float | None = None
    record: Any = None

    @property
    def is_root(self) -> bool:
        return self.role == "root"


def _role_of_id(entry_id: str) -> str:
    if entry_id.startswith(ROOT_PREFIX):
        return "root"
    if entry_id.endswith(FRAMES_SUFFIX):
        return "frames"
    if PARTS_INFIX in entry_id:
        return "parts"
    return "mp4"


def _fs_layout(store: Any) -> tuple[Path, Path] | None:
    """``(catalog_dir, blob_dir)`` of a filesystem store, else ``None``."""
    rootdir = getattr(getattr(store, "blobs", None), "rootdir", None)
    if rootdir is None:
        return None
    blobs = Path(rootdir)
    return blobs.parent / "catalog", blobs


def inventory(store: Any) -> list[CacheEntry]:
    """Every catalog record of ``store``, read once. An unreadable record is
    listed with role ``"unreadable"`` and, on disk, its file's mtime."""
    layout = _fs_layout(store)
    entries = []
    for entry_id in list(store):
        try:
            rec = store[entry_id]
        except Exception:  # noqa: BLE001 — a damaged record is garbage, listed
            written = None
            if layout is not None:
                try:
                    written = (layout[0] / f"{entry_id}.json").stat().st_mtime
                except OSError:
                    pass
            entries.append(CacheEntry(entry_id, "unreadable", written_at=written))
            continue
        written = None
        prov = getattr(rec, "provenance", None)
        if prov is not None:
            written = float(prov.generated_at_time.to_seconds())
        entries.append(
            CacheEntry(
                entry_id,
                getattr(rec, "role", None) or _role_of_id(entry_id),
                asset_id=rec.asset_id,
                bytes_size=int(rec.bytes_size or 0),
                written_at=written,
                record=rec,
            )
        )
    return entries


def _blobs(store: Any) -> dict[str, tuple[int, float | None]]:
    """``{content hash: (size, mtime or None)}`` of every blob in ``store``."""
    layout = _fs_layout(store)
    out: dict[str, tuple[int, float | None]] = {}
    for h in store.iter_blobs():
        if layout is not None:
            try:
                st = (layout[1] / h).stat()
            except OSError:
                continue
            out[h] = (st.st_size, st.st_mtime)
        else:
            data = store.get_blob(h)
            out[h] = (len(data) if data is not None else 0, None)
    return out


# -----------------------------------------------------------------------------
# What is reachable
# -----------------------------------------------------------------------------


@dataclass
class Reachability:
    """What the current scene and the recorded roots keep, and why.

    ``profiles`` are the knob sets the current scene was keyed under;
    ``skipped`` the ones it could not be (``(profile, why)``: a line's audio
    is not cached under it — an#306), whose roots keep what they recorded."""

    from_scene: set[str] = field(default_factory=set)
    from_roots: set[str] = field(default_factory=set)
    profiles: list[dict] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    skipped: list[tuple[dict, str]] = field(default_factory=list)
    #: The renderers' derived-store entries the current scene reads, by store
    #: (a Manim picture, its measurement and contact sheet; an#299).
    derived: dict[str, set[str]] = field(default_factory=dict)

    @property
    def ids(self) -> set[str]:
        return self.from_scene | self.from_roots | set(self.roots)


def _profile_kwargs(profile: Mapping[str, Any]) -> dict[str, Any] | None:
    """A recorded profile as `cache_entries` keywords, or ``None`` when it
    cannot be replayed (the render was given provider INSTANCES, which a
    collector cannot rebuild — that render's root still protects what it used).
    Keys this version does not know (a newer `an` wrote the root) are dropped,
    for the same reason."""
    kw = {k: profile.get(k, v) for k, v in DEFAULT_PROFILE.items()}
    if kw["tts"] is None or kw["lipsync"] is None:
        return None
    if kw["resolution"] is not None:
        kw["resolution"] = tuple(kw["resolution"])
    return kw


def _roots_of(entries: Iterable[CacheEntry], project: str) -> list[CacheEntry]:
    return [
        e
        for e in entries
        if e.is_root
        and e.record is not None
        and (e.record.render_provenance or {}).get("project") == project
    ]


def reachable_entries(
    project: Any,
    store: Any,
    *,
    entries: Iterable[CacheEntry] | None = None,
    engine: ShotCache | None = None,
    root_max_age: float | None = None,
    now: float | None = None,
    force: bool = False,
) -> Reachability:
    """What the project's current scene and its recorded roots reach.

    The current scene is keyed under the knobs of EVERY recorded root (of any
    project, any age: a knob set is a few values, and dropping one would orphan
    that render's entries of the unchanged scene), each with its own recorded
    providers, and under :data:`HYPOTHETICAL_PROFILES` (a plain render's). A
    root younger than ``root_max_age`` seconds (all, when ``None``) also keeps
    the entries it names; roots themselves are always kept.

    A knob set under which some line's audio is not cached cannot be keyed
    without a synthesis (an#306): it is skipped, listed in ``skipped``, and
    every root recorded under it keeps its entries whatever ``root_max_age``.

    ``engine`` computes the keys (its environment seam included); ``None`` is
    a default :class:`~an.build.ShotCache` over ``store``, which probes this
    machine like a render does. Raises :class:`CacheGcError` when the current
    scene's keys cannot be computed for any other reason, or under no knob set
    at all (guessing is never safe), and when no render of THIS project has
    recorded a root yet — a cache written before roots existed (an#274) —
    unless ``force``.
    """
    from an.build.shot_cache import project_id
    from an.render import cache_reach

    now = time.time() if now is None else now
    entries = list(entries) if entries is not None else inventory(store)
    if not force and not _roots_of(entries, project_id(project.root)):
        raise CacheGcError(
            "no render of this project has recorded what it used yet (a cache "
            "written before `an cache gc` existed); nothing was deleted. Render "
            "once (`an render`), then collect — or pass --force to keep only "
            "what the current scene reaches under the default settings and any "
            "recorded ones"
        )
    reach = Reachability()
    # Each knob set, with the roots recorded under it (none: hypothetical).
    candidates: list[tuple[dict, list[CacheEntry]]] = []
    for e in entries:
        if not e.is_root or e.record is None:
            continue
        reach.roots.append(e.id)
        info = e.record.render_provenance or {}
        expired = root_max_age is not None and (
            e.written_at is not None and now - e.written_at > root_max_age
        )
        if not expired:
            reach.from_roots.update(info.get("entries") or ())
        profile = _profile_kwargs(info.get("profile") or {})
        if profile is None:
            continue
        for known, roots in candidates:
            if known == profile:
                roots.append(e)
                break
        else:
            candidates.append((profile, [e]))
    for hypothetical in HYPOTHETICAL_PROFILES:
        profile = _profile_kwargs(hypothetical)
        if all(known != profile for known, _ in candidates):
            candidates.append((profile, []))
    engine = engine or ShotCache(store)
    # One in-memory overlay for every knob set: free speech re-made for one is
    # not made again for the next (an#311 review: `mac_say` takes seconds a line).
    from dataclasses import replace

    from an.audio.pipeline import in_memory_audio_mall

    project = replace(project, mall=in_memory_audio_mall(project.mall))
    for profile, roots in candidates:
        try:
            with warnings.catch_warnings():
                # A stand-in or a missing font warns at compile time; that is
                # the render's message to give, not the collector's.
                warnings.simplefilter("ignore")
                scene_reach = cache_reach(project, engine, **profile)
        except AudioNotCachedError as e:
            # No key until that line is synthesised: nothing cached can be its
            # shot's entry. What the renders under it used stays, whatever age.
            reach.skipped.append((profile, str(e)))
            for root in roots:
                rp = root.record.render_provenance or {}
                reach.from_roots.update(rp.get("entries") or ())
            continue
        except Exception as e:  # noqa: BLE001 — refuse rather than guess
            raise CacheGcError(
                f"cannot compute what the current scene reaches under {profile} "
                f"({type(e).__name__}: {e}); nothing was deleted. Fix what keeps "
                "it from rendering (`an validate`)"
            ) from e
        reach.profiles.append(profile)
        reach.from_scene.update(scene_reach.ids)
        for store, keys in scene_reach.derived.items():
            reach.derived.setdefault(store, set()).update(keys)
    if not reach.profiles:
        why = "; ".join(sorted({why for _, why in reach.skipped}))
        raise CacheGcError(
            "cannot compute what the current scene reaches under any setting a "
            f"render used or a plain render uses ({why}); nothing was deleted. "
            "Render the project first: a line whose audio is not cached yet has "
            "no key until it is synthesised"
        )
    return reach


# -----------------------------------------------------------------------------
# Collection
# -----------------------------------------------------------------------------


@dataclass
class GcReport:
    """What a collection deleted (or, with ``dry_run``, would delete), and why
    the rest was kept."""

    dry_run: bool
    deleted: list[CacheEntry] = field(default_factory=list)
    deleted_blobs: dict[str, int] = field(default_factory=dict)
    kept_reachable: int = 0
    kept_protected: list[str] = field(default_factory=list)
    kept_retained: int = 0
    failed: list[str] = field(default_factory=list)
    bytes_before: int = 0
    reach: Reachability | None = None
    #: The renderers' derived stores (an#299): what was (or would be) deleted,
    #: by store, and the bytes that frees.
    deleted_derived: dict[str, list[str]] = field(default_factory=dict)
    derived_freed: int = 0
    kept_derived: int = 0

    @property
    def freed_bytes(self) -> int:
        return sum(self.deleted_blobs.values())

    def summary(self) -> str:
        verb = "would delete" if self.dry_run else "deleted"
        roles: dict[str, int] = {}
        for e in self.deleted:
            roles[e.role] = roles.get(e.role, 0) + 1
        what = ", ".join(f"{n} {r}" for r, n in sorted(roles.items())) or "nothing"
        after = self.bytes_before - self.freed_bytes
        lines = [
            f"shot cache: {verb} {len(self.deleted)} entries ({what}), "
            f"{human_bytes(self.freed_bytes)} of {human_bytes(self.bytes_before)}; "
            f"{human_bytes(after)} {'would remain' if self.dry_run else 'remains'}",
            f"kept: {self.kept_reachable} reachable"
            + (
                f" (current scene under {len(self.reach.profiles)} knob set(s), "
                f"{len(self.reach.roots)} recorded render(s))"
                if self.reach is not None
                else ""
            )
            + f", {self.kept_retained} within --max-size/--max-age"
            + f", {len(self.kept_protected)} written during a render or this collection",
        ]
        if self.deleted_derived or self.kept_derived:
            n = sum(len(v) for v in self.deleted_derived.values())
            what = ", ".join(
                f"{len(v)} {store}" for store, v in self.deleted_derived.items() if v
            ) or "nothing"
            lines.append(
                f"derived stores: {verb} {n} entries ({what}), "
                f"{human_bytes(self.derived_freed)}; kept {self.kept_derived}"
            )
        if self.reach is not None and self.reach.skipped:
            lines.append(_skipped_line(self.reach.skipped))
        if self.failed:
            lines.append(
                f"could not delete {len(self.failed)} (in use, or already gone): "
                + ", ".join(self.failed[:5])
                + (" ..." if len(self.failed) > 5 else "")
            )
        return "\n".join(lines)


def _skipped_line(skipped: list[tuple[dict, str]]) -> str:
    """One line on the knob sets the current scene could not be keyed under."""
    names = ", ".join(sorted({f"tts={profile.get('tts')}" for profile, _ in skipped}))
    return (
        f"not keyed under {len(skipped)} knob set(s) ({names}): a line's audio is "
        "not cached under it, so it has no key until synthesised; what renders "
        "under it recorded is kept"
    )


def _remove_record(store: Any, entry_id: str, layout, *, horizon: float) -> bool:
    """Delete one catalog record; ``False`` when it was re-written after
    ``horizon`` (a concurrent ``--force-render`` re-recorded the key)."""
    if layout is None:
        del store[entry_id]
        return True
    path = layout[0] / f"{entry_id}.json"
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path.name)
    if path.stat().st_mtime >= horizon:
        return False
    path.unlink()
    return True


def _remove_blob(store: Any, h: str, layout) -> None:
    if layout is not None:
        path = store.blob_path(h)  # contained: never outside the blob dir
        if path is None:
            raise FileNotFoundError(h)
        Path(path).unlink()
        return
    store.delete_blob(h)


def _protection_horizon(project_root: Path, now: float) -> float:
    """Anything written at or after this time is left alone: the earlier of
    this collection's start and every live render's start, less the slack."""
    from an.render import live_runs

    starts = [started for _, started in live_runs(project_root)]
    return min([now, *starts]) - CLOCK_SLACK_S


def collect_garbage(
    project_dir: str | Path,
    *,
    dry_run: bool = False,
    max_size: int | None = None,
    max_age: float | None = None,
    engine: ShotCache | None = None,
    now: float | None = None,
    force: bool = False,
) -> GcReport:
    """Delete the shot-cache entries of ``project_dir`` that nothing reaches.

    With no cap, every unreachable entry goes. With caps, unreachable history
    is kept within them, newest first, and both bind: ``max_age`` (seconds)
    keeps only unreachable entries written more recently than that (and lets a
    recorded render older than that stop protecting its entries); ``max_size``
    (bytes) keeps only those that fit in a cache of that size. Neither ever
    removes a reachable entry, so the cache can stay above ``max_size``.
    ``dry_run`` reports and deletes nothing. ``force`` collects a cache no
    render of this project has recorded a root in (see :func:`reachable_entries`).

    See the module docstring for the reachability and concurrency argument.
    """
    from an.project import load

    project = load(project_dir)
    store = project.mall.get(SHOT_CACHE_STORE)
    report = GcReport(dry_run=dry_run)
    if store is None:
        return report
    now = time.time() if now is None else now
    horizon = _protection_horizon(project.root, now)
    entries = inventory(store)
    blobs = _blobs(store)
    report.bytes_before = sum(size for size, _ in blobs.values())
    report.reach = reach = reachable_entries(
        project, store, entries=entries, engine=engine, root_max_age=max_age, now=now,
        force=force,
    )
    keep_ids = reach.ids

    candidates: list[CacheEntry] = []
    kept: list[CacheEntry] = []
    for e in entries:
        if e.id in keep_ids:
            report.kept_reachable += 1
            kept.append(e)
        elif e.written_at is None or e.written_at >= horizon:
            report.kept_protected.append(e.id)
            kept.append(e)
        else:
            candidates.append(e)

    # Retention caps: the newest unreachable entries first.
    candidates.sort(key=lambda e: e.written_at or 0.0, reverse=True)
    if max_age is not None or max_size is not None:
        counted = {e.asset_id for e in kept if not e.is_root and e.asset_id in blobs}
        size = sum(blobs[h][0] for h in counted)
        doomed = []
        for e in candidates:
            young = max_age is None or now - (e.written_at or 0.0) <= max_age
            extra = (
                blobs[e.asset_id][0]
                if (not e.is_root and e.asset_id in blobs and e.asset_id not in counted)
                else 0
            )
            fits = max_size is None or size + extra <= max_size
            # Both caps bind: an entry stays only when it is young enough AND fits.
            if young and fits:
                report.kept_retained += 1
                kept.append(e)
                if extra:
                    counted.add(e.asset_id)
                    size += extra
            else:
                doomed.append(e)
        candidates = doomed

    # Blobs: those only doomed records name, and orphans from before the horizon.
    # A blob goes when no kept record names it and it predates the horizon:
    # on disk its mtime says so (an orphan included — a render that crashed
    # between blob and record); off disk, only a blob a doomed record names
    # is known to predate it.
    named_by_kept = {e.asset_id for e in kept if not e.is_root}
    named_by_doomed = {e.asset_id for e in candidates if not e.is_root}
    doomed_blobs = {}
    for h, (blob_size, mtime) in blobs.items():
        if h in named_by_kept or (mtime is not None and mtime >= horizon):
            continue
        if mtime is not None or h in named_by_doomed:
            doomed_blobs[h] = blob_size

    report.deleted = candidates
    if dry_run:
        report.deleted_blobs = doomed_blobs
        doomed_ids = {e.id for e in candidates}
        _collect_derived(
            project, reach, [e for e in entries if e.id not in doomed_ids],
            horizon=horizon, now=now, max_age=max_age, max_size=max_size,
            shot_cache_kept_bytes=report.bytes_before - sum(doomed_blobs.values()),
            dry_run=True, report=report,
        )  # fmt: skip
        return report
    layout = _fs_layout(store)
    # Records first, then blobs: a record must never name a blob that is gone.
    removed = []
    for e in candidates:
        try:
            if _remove_record(store, e.id, layout, horizon=horizon):
                removed.append(e)
            else:
                report.kept_protected.append(e.id)
        except (OSError, KeyError):
            report.failed.append(e.id)
    report.deleted = removed
    # A blob whose record could not be removed stays.
    named_by_kept |= {e.asset_id for e in candidates if e not in removed}
    for h, blob_size in doomed_blobs.items():
        if h in named_by_kept:
            continue
        try:
            if layout is not None:
                # Re-checked at the last moment: a render may have stored the
                # same bytes again since the listing (os.replace: a new mtime).
                if (layout[1] / h).stat().st_mtime >= horizon:
                    continue
            _remove_blob(store, h, layout)
        except (OSError, KeyError):
            report.failed.append(h)
            continue
        report.deleted_blobs[h] = blob_size
    # The derived stores, after the shot cache: a shot entry that stays keeps
    # what its provenance names (an#299).
    removed_ids = {e.id for e in removed}
    _collect_derived(
        project, reach, [e for e in entries if e.id not in removed_ids],
        horizon=horizon, now=now, max_age=max_age, max_size=max_size,
        shot_cache_kept_bytes=report.bytes_before - report.freed_bytes,
        dry_run=False, report=report,
    )  # fmt: skip
    return report


# -----------------------------------------------------------------------------
# The renderers' derived stores (an#299)
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DerivedEntry:
    """One entry of a renderer's derived store (a Manim picture, measurement
    record or contact sheet)."""

    store: str
    key: str
    size: int
    written_at: float | None


def _merge(into: dict[str, set[str]], more: Mapping[str, Iterable[str]]) -> None:
    for store, keys in more.items():
        into.setdefault(store, set()).update(keys)


def _derived_inventory(
    mall: Mapping[str, Any], stores: Iterable[str]
) -> dict[str, list[DerivedEntry]]:
    """Each derived store's entries with their size and age. An entry whose
    age cannot be read (a store with no files) has ``written_at=None``, which
    nothing ever deletes."""
    out: dict[str, list[DerivedEntry]] = {}
    for name in stores:
        store = mall.get(name)
        if store is None:
            continue
        path_of = getattr(store, "path_of", None)
        entries = []
        for key in list(store):
            size, mtime = 0, None
            try:
                if path_of is not None:
                    st = Path(path_of(key)).stat()
                    size, mtime = st.st_size, st.st_mtime
                else:
                    size = len(store[key])
            except (OSError, KeyError, TypeError):
                continue  # gone since the listing
            entries.append(DerivedEntry(name, str(key), size, mtime))
        out[name] = entries
    return out


def _derived_keep(
    project: Any,
    specs: Mapping[str, Any],
    reach: Reachability,
    kept_shot_entries: Iterable[CacheEntry],
) -> dict[str, set[str]]:
    """What the current scene reads, and what every kept shot entry's
    provenance names (NOT yet closed over what records name)."""
    keep: dict[str, set[str]] = {}
    _merge(keep, reach.derived)
    for e in kept_shot_entries:
        if e.is_root or e.record is None:
            continue
        spec = specs.get(getattr(e.record, "renderer", None) or "")
        if spec is not None:
            _merge(keep, spec.provenance(e.record.render_provenance or {}))
    return keep


def _closure(
    mall: Mapping[str, Any], specs: Mapping[str, Any], entries: Mapping[str, set[str]]
) -> dict[str, set[str]]:
    out = {store: set(keys) for store, keys in entries.items()}
    for spec in specs.values():
        _merge(out, spec.closure(mall, out))
    return out


def _collect_derived(
    project: Any,
    reach: Reachability,
    kept_shot_entries: list[CacheEntry],
    *,
    horizon: float,
    now: float,
    max_age: float | None,
    max_size: int | None,
    shot_cache_kept_bytes: int,
    dry_run: bool,
    report: GcReport,
) -> None:
    """Collect the registered derived stores (:mod:`an.build.derived`) under
    the shot cache's guarantees.

    Kept: what the current scene reads, what every kept shot entry's
    provenance names, every entry written since the protection horizon — each
    with everything its records name. Unreachable history is trimmed by the
    caps in UNITS — a record with what it alone names — newest first, against
    the ONE ``max_size`` the shot cache's kept bytes already count toward.
    Records go first; then the record stores are listed and read AGAIN, and a
    named entry goes only if no record present now names it — so a render
    racing the collection (a record written after the listing, naming an older
    picture) keeps what it needs. A record that cannot be read (half written)
    stops every named entry from going this run. ``dry_run`` deletes nothing.
    """
    from an.build.derived import UnreadableRecordError, registered_derived_stores

    specs = registered_derived_stores()
    if not specs:
        return
    mall = project.mall
    stores = [s for spec in specs.values() for s in spec.stores]
    record_stores = {spec.record_store for spec in specs.values()}
    inventory_ = _derived_inventory(mall, stores)
    young = {
        store: {e.key for e in es if e.written_at is None or e.written_at >= horizon}
        for store, es in inventory_.items()
    }
    keep = _derived_keep(project, specs, reach, kept_shot_entries)
    _merge(keep, young)
    try:
        keep = _closure(mall, specs, keep)
    except UnreadableRecordError as e:
        report.failed.append(f"derived stores: a kept record is unreadable ({e}); nothing deleted")
        return
    by_key = {(e.store, e.key): e for es in inventory_.values() for e in es}
    records = [
        e for es in inventory_.values() for e in es
        if e.store in record_stores and e.key not in keep.get(e.store, ())
    ]  # fmt: skip

    # A unit: an unreachable record and what it names that nothing kept names.
    def unit(e: DerivedEntry) -> list[DerivedEntry]:
        try:
            named = _closure(mall, specs, {e.store: {e.key}})
        except UnreadableRecordError:
            named = {e.store: {e.key}}
        return [
            by_key[(store, k)]
            for store, ks in named.items()
            for k in ks
            if (store, k) in by_key and k not in keep.get(store, ())
        ]

    if max_age is not None or max_size is not None:
        size = shot_cache_kept_bytes + sum(
            e.size for (store, k), e in by_key.items() if k in keep.get(store, ())
        )
        for e in sorted(records, key=lambda e: e.written_at or 0.0, reverse=True):
            members = [m for m in unit(e) if m.key not in keep.get(m.store, ())]
            extra = sum(m.size for m in members)
            young_enough = max_age is None or now - (e.written_at or 0.0) <= max_age
            if young_enough and (max_size is None or size + extra <= max_size):
                _merge(keep, {m.store: {m.key} for m in members})
                size += extra
        records = [e for e in records if e.key not in keep.get(e.store, ())]

    def gone(e: DerivedEntry) -> bool:
        """Delete ``e`` now (unless re-written since the listing)."""
        if dry_run:
            return True
        store = mall[e.store]
        try:
            path_of = getattr(store, "path_of", None)
            if path_of is not None and Path(path_of(e.key)).stat().st_mtime >= horizon:
                return False
            del store[e.key]
        except (OSError, KeyError):
            report.failed.append(f"{e.store}/{e.key}")
            return False
        return True

    removed_records = set()
    for e in records:
        if gone(e):
            removed_records.add((e.store, e.key))
            report.deleted_derived.setdefault(e.store, []).append(e.key)
            report.derived_freed += e.size
    # The record stores AGAIN, as they are now: whatever a present record
    # names stays, however old its file.
    try:
        present = {
            store: {
                k for k in (mall[store] if mall.get(store) is not None else ())
                if (store, str(k)) not in removed_records
            }
            for store in record_stores
        }  # fmt: skip
        named_now = _closure(mall, specs, present)
    except UnreadableRecordError as e:
        report.failed.append(
            f"derived stores: a record is unreadable ({e}); nothing it could name deleted"
        )
        named_now = None
    deleted = len(removed_records)
    if named_now is not None:
        for (store, k), e in by_key.items():
            if store in record_stores or k in keep.get(store, ()):
                continue
            if k in named_now.get(store, ()):
                continue
            if gone(e):
                deleted += 1
                report.deleted_derived.setdefault(store, []).append(k)
                report.derived_freed += e.size
    report.kept_derived = len(by_key) - deleted


# -----------------------------------------------------------------------------
# Info
# -----------------------------------------------------------------------------


@dataclass
class CacheInfo:
    """The shot cache's size, what it holds, and how much of it is reachable."""

    path: str
    total_bytes: int = 0
    by_role: dict[str, tuple[int, int]] = field(default_factory=dict)
    reachable: tuple[int, int] | None = None
    unreachable: tuple[int, int] | None = None
    orphan_blobs: tuple[int, int] = (0, 0)
    roots: list[dict] = field(default_factory=list)
    reachability_error: str = ""
    skipped: list[tuple[dict, str]] = field(default_factory=list)
    #: The renderers' derived stores (an#299), by store name.
    derived: dict[str, "DerivedUsage"] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"shot cache: {human_bytes(self.total_bytes)} at {self.path}"]
        for role, (n, size) in sorted(self.by_role.items()):
            lines.append(f"  {role:<10} {n:>5} entries  {human_bytes(size):>10}")
        if self.orphan_blobs[0]:
            n, size = self.orphan_blobs
            lines.append(f"  {'(orphan)':<10} {n:>5} blobs    {human_bytes(size):>10}")
        if self.reachable is not None:
            (rn, rs), (un, us) = self.reachable, self.unreachable
            lines.append(
                f"reachable: {rn} entries, {human_bytes(rs)}; unreachable: {un} "
                f"entries, {human_bytes(us)} (what `an cache gc` would delete)"
            )
        else:
            lines.append(f"reachable: unknown ({self.reachability_error})")
        if self.skipped:
            lines.append(_skipped_line(self.skipped))
        for r in self.roots:
            lines.append(
                f"  render of {r['output']!r}, {r['age']} ago, {r['entries']} entries"
                + (f", knobs {r['knobs']}" if r["knobs"] else "")
            )
        if self.derived:
            lines.append("derived stores:")
            for store, u in self.derived.items():
                unreachable = (
                    f"; unreachable: {u.unreachable_entries}, "
                    f"{human_bytes(u.unreachable_bytes)}"
                    if u.unreachable_entries is not None
                    else ""
                )
                lines.append(
                    f"  {store:<14} {u.entries:>5} entries  {human_bytes(u.bytes):>10}"
                    + unreachable
                )
        return "\n".join(lines)


@dataclass
class DerivedUsage:
    """One derived store's size, and how much of it nothing reaches
    (``None``: reachability unknown)."""

    entries: int = 0
    bytes: int = 0
    unreachable_entries: int | None = None
    unreachable_bytes: int | None = None


def _age(seconds: float) -> str:
    for unit, n in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= n:
            return f"{seconds / n:.1f}{unit}"
    return f"{seconds:.0f}s"


def cache_info(
    project_dir: str | Path,
    *,
    reachability: bool = True,
    engine: ShotCache | None = None,
    now: float | None = None,
) -> CacheInfo:
    """What ``project_dir``'s shot cache holds; never fails on reachability
    (it says why it is unknown instead)."""
    from an.project import load

    project = load(project_dir)
    store = project.mall.get(SHOT_CACHE_STORE)
    layout = _fs_layout(store) if store is not None else None
    info = CacheInfo(path=str(layout[1].parent) if layout else SHOT_CACHE_STORE)
    if store is None:
        return info
    now = time.time() if now is None else now
    entries = inventory(store)
    blobs = _blobs(store)
    info.total_bytes = sum(size for size, _ in blobs.values())
    owner: dict[str, str] = {}
    for e in entries:
        n, size = info.by_role.get(e.role, (0, 0))
        extra = 0
        if not e.is_root and e.asset_id in blobs and e.asset_id not in owner:
            owner[e.asset_id] = e.id
            extra = blobs[e.asset_id][0]
        info.by_role[e.role] = (n + 1, size + extra)
    orphans = [h for h in blobs if h not in owner]
    info.orphan_blobs = (len(orphans), sum(blobs[h][0] for h in orphans))
    for e in entries:
        if e.is_root and e.record is not None:
            rp = e.record.render_provenance or {}
            knobs = {
                k: v
                for k, v in (rp.get("profile") or {}).items()
                if DEFAULT_PROFILE.get(k, object()) != v
            }
            info.roots.append(
                {
                    "output": rp.get("output", e.record.shot_id),
                    "age": _age(now - (e.written_at or now)),
                    "entries": len(rp.get("entries") or ()),
                    "knobs": knobs,
                }
            )
    from an.build.derived import UnreadableRecordError, registered_derived_stores

    specs = registered_derived_stores()
    derived_inventory = _derived_inventory(
        project.mall, [s for spec in specs.values() for s in spec.stores]
    )
    for name, es in derived_inventory.items():
        info.derived[name] = DerivedUsage(len(es), sum(e.size for e in es))
    if reachability:
        try:
            reach = reachable_entries(
                project, store, entries=entries, engine=engine, now=now, force=True
            )
        except CacheGcError as e:
            info.reachability_error = str(e)
            return info
        keep, info.skipped = reach.ids, reach.skipped
        kept = [e for e in entries if e.id in keep]
        gone = [e for e in entries if e.id not in keep]
        info.reachable = (len(kept), _unique_size(kept, blobs))
        info.unreachable = (len(gone), _unique_size(gone, blobs, exclude=kept))
        try:
            derived_keep = _closure(
                project.mall, specs, _derived_keep(project, specs, reach, kept)
            )
        except UnreadableRecordError:
            return info  # unknown: a record cannot be read
        for name, es in derived_inventory.items():
            lost = [e for e in es if e.key not in derived_keep.get(name, ())]
            info.derived[name].unreachable_entries = len(lost)
            info.derived[name].unreachable_bytes = sum(e.size for e in lost)
    return info


def _unique_size(
    entries: Iterable[CacheEntry],
    blobs: Mapping[str, tuple[int, Any]],
    *,
    exclude: Iterable[CacheEntry] = (),
) -> int:
    """Bytes of the distinct blobs ``entries`` name, less those ``exclude`` names."""
    skip = {e.asset_id for e in exclude if not e.is_root}
    hashes = {e.asset_id for e in entries if not e.is_root and e.asset_id in blobs} - skip
    return sum(blobs[h][0] for h in hashes)
