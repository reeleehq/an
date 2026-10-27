"""``an world …``: the scene's world from the shell (ADR 0009).

Thin projections of :mod:`an.stage.world`, wired into the CLI by
:data:`an.tools._dispatch_namespaces`.
"""

from __future__ import annotations

import json as _json

from an.ir.sync import DEFAULT_SCENE_FILE

__all__ = ["from_shot", "show"]


def show(
    project_dir: str,
    shot: str = "",
    json: bool = False,
    frames: bool = False,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Print every framed shot as the compiler sees it: each entity's placement derived from the scene's world, and what the world added, replaced or could not place.

    The derived placements are never written to the project; this is how you
    read them. A shot without a viewpoint is not listed: it is placed by hand,
    as it always was.

    project_dir: the an project
    shot: one shot id (default: every framed shot)
    json: print the report as JSON instead of text
    frames: print instead the scene's frames of reference, one line per frame per framed shot: its pose in the world as the shot opens and as it closes
    scene: the scene file to read, inside the project (default scene.md; for example scene.studio.md)
    """
    from an.ir.world import WorldError
    from an.project import load
    from an.stage.world import lower_scene, world_report

    project = load(project_dir, scene_file=scene, sync=False)
    if frames:
        return _show_frames(project, shot=shot, json=json)
    try:
        rows = world_report(lower_scene(project.scene, project.mall))
    except WorldError as e:
        raise SystemExit(f"the scene's world cannot be lowered: {e}") from None
    if shot:
        rows = [r for r in rows if r["shot"] == shot]
        if not rows:
            raise SystemExit(f"shot {shot!r} is not a framed shot of this scene")
    if json:
        text = _json.dumps(rows, indent=2)
        print(text)
        return text
    lines: list[str] = []
    if not rows:
        lines.append(
            "no framed shot: the scene has no `world`, or no shot names a `viewpoint`"
        )
    for row in rows:
        vp = row["viewpoint"]
        lines.append(
            f"## {row['shot']}  viewpoint: {vp if isinstance(vp, str) else _json.dumps(vp)}"
        )
        for e in row["entities"]:
            at = (
                f"at ({e['at'][0]:.4g}, {e['at'][1]:.4g})"
                if e["at"] is not None
                else "at (unplaced)"
            )
            scale = f" scale {e['scale']:.3g}" if e["scale"] is not None else ""
            after = f" after {e['after']}" if e["after"] else ""
            lines.append(f"  {e['kind']:<12}{e['id']:<24}{at}{scale}{after}")
        lines.append(f"  actions: {row['actions']}")
        for n in row["notes"]:
            lines.append(f"  [{n['severity']}] {n['entity']}: {n['message']}")
    text = "\n".join(lines)
    print(text)
    return text


def _show_frames(project, *, shot: str, json: bool) -> str:
    from an.ir.world import WorldError, frame_poses
    from an.stage.world import _film_starts

    try:
        rows = frame_poses(
            project.scene, film_starts=_film_starts(project.scene, fps=None)
        )
    except WorldError as e:
        raise SystemExit(f"the scene's frames cannot be read: {e}") from None
    if shot:
        rows = [r for r in rows if r["shot"] == shot]
        if not rows:
            raise SystemExit(f"shot {shot!r} is not a framed shot of this scene")
    if json:
        text = _json.dumps(rows, indent=2)
        print(text)
        return text

    def pose(p: dict) -> str:
        x, y, z = p["at"]
        look = f" yaw {p['yaw']:.4g}" if p["yaw"] else ""
        look += f" pitch {p['pitch']:.4g}" if p["pitch"] else ""
        return f"at ({x:.4g}, {y:.4g}, {z:.4g}){look}"

    lines: list[str] = []
    if not rows:
        lines.append("no framed shot: no shot names a `viewpoint`")
    for row in rows:
        lines.append(f"## {row['shot']}  viewpoint in: {row['viewpoint_frame']}")
        if not row["frames"]:
            lines.append("  (no frames: everything is in the world)")
        for f in row["frames"]:
            how = " [far]" if f["coupling"] == "far" else ""
            lines.append(
                f"  {f['name']:<16}in {f['parent']:<12}{pose(f['start'])}  ->  {pose(f['end'])}{how}"
            )
    text = "\n".join(lines)
    print(text)
    return text


def from_shot(
    project_dir: str,
    shot: str,
    focal: float = 0.0,
    depth: float = 0.0,
    dry_run: bool = False,
    scene: str = DEFAULT_SCENE_FILE,
) -> str:
    """Give a scene placed by hand a world: invert a master shot's placements through a pinhole camera and write the `world` and the shot's viewpoint into the scene.

    Every entity the shot places by hand (`stage.at`) becomes a world member at
    one depth, its screen position and scale inverted (x = sx·Z/f, height =
    scale·native·Z/f), so the world lowers back to the placements the shot
    already has; its environments become members as they are. The shot keeps
    its `stage` lines (they agree with the world) and names the new viewpoint,
    called after it.
    The other shots then take viewpoints by hand. The scene file is updated
    through the store: the prose around its blocks is kept.

    project_dir: the an project
    shot: the master shot's id
    focal: the lens in pixels (default: the default field of view at the scene's width)
    depth: the depth every member stands at, in world units (default: where the tallest is 1.7 tall, so units read as metres)
    dry_run: print what would be written, and write nothing
    scene: the scene file to read, inside the project (default scene.md)
    """
    from an.project import load
    from an.stage.world import seed_world

    project = load(project_dir, scene_file=scene)
    try:
        new_scene, seeded = seed_world(
            project.scene,
            project.mall,
            shot,
            focal=focal or None,
            depth=depth or None,
        )
    except ValueError as e:
        raise SystemExit(f"an world from-shot: {e}") from None
    lines = [
        f"viewpoint {shot!r}: at (0, 0, 0)"
        + (f", focal {focal:g}" if focal else ", the default field of view"),
        f"members at depth {seeded.depth:.4g}:",
    ]
    for m in seeded.members:
        where = (
            f"at ({m.at[0]:.4g}, {m.at[1]:.4g}, {m.at[2]:.4g}) height {m.height:.4g}"
            if m.at is not None
            else "(an environment)"
        )
        lines.append(f"  {m.kind:<12}{m.id:<24}{where}")
    if seeded.flat:
        lines.append(f"  one depth for all: {seeded.flat}")
    for eid, why in seeded.skipped.items():
        lines.append(f"  left out: {eid}: {why}; it stays placed by hand")
    if dry_run:
        lines.append("(dry run: nothing written)")
    else:
        project.mall["scenes"]["main"] = new_scene
        lines.append(f"written to {scene}")
    return "\n".join(lines)


_dispatch_funcs = [show, from_shot]
