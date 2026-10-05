"""``an cache …`` — the shot cache from the shell (an#274).

Wired into the top-level dispatcher as the ``cache`` namespace
(``an.tools._dispatch_namespaces``), programmatically, per pillar 8: plain
functions taking strings and booleans and returning the text to print; the
business logic is :mod:`an.build.gc`.

Subcommands: ``info`` (size, entries, how much the current scene reaches) and
``gc`` (delete what nothing reaches; ``--dry-run`` first).
"""

from __future__ import annotations

from an.build.gc import (
    CacheGcError,
    cache_info,
    collect_garbage,
    parse_age,
    parse_size,
)


def info(project_dir: str, no_reachability: bool = False) -> str:
    """Show the project's shot cache: its size, its entries by kind, and how much of it the current scene still reaches.

    project_dir: path to an an project
    no_reachability: skip computing what the current scene reaches (which compiles every shot and probes this machine's browser, like a render's first second)
    """
    return cache_info(project_dir, reachability=not no_reachability).summary()


def gc(
    project_dir: str,
    dry_run: bool = False,
    max_size: str = "",
    max_age: str = "",
    force: bool = False,
) -> str:
    """Delete the shot-cache entries nothing reaches: not the current scene (under the default render settings or any a recorded render used), and not the latest render of each output on each machine.

    Never deletes a reachable entry, nor anything written since a render of this project still in progress began. A render running meanwhile can at worst re-render a shot, never use a wrong one.

    project_dir: path to an an project
    dry_run: report what would be deleted, delete nothing
    max_size: keep the most recently written unreachable entries that fit in a cache of this size (e.g. 2G, 500MB) — the shot cache and the Manim stores together; reachable entries are never removed, so the cache can stay above it
    max_age: keep only the unreachable entries written within this age (e.g. 7d, 36h); a recorded render older than it stops naming its entries, but the current scene under its settings is still kept (and when the current scene cannot be keyed under its settings, a line's audio not cached under them, its entries are kept whatever its age)
    force: collect a cache no render of this project has recorded what it used in (one written before `an cache gc` existed): keep only what the current scene reaches (a setting whose audio is no longer cached is not kept; an#311)
    """
    try:
        report = collect_garbage(
            project_dir,
            dry_run=dry_run,
            max_size=parse_size(max_size) if max_size else None,
            max_age=parse_age(max_age) if max_age else None,
            force=force,
        )
    except (CacheGcError, ValueError) as e:
        raise SystemExit(f"an cache gc: {e}") from e
    return report.summary()


_dispatch_funcs = [info, gc]
