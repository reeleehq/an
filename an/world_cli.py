"""``an world …``: the scene's world from the shell (ADR 0009).

Thin projections of :mod:`an.stage.world`, wired into the CLI by
:data:`an.tools._dispatch_namespaces`.
"""

from __future__ import annotations

import json as _json

__all__ = ["show"]


def show(
    project_dir: str, shot: str = "", json: bool = False, frames: bool = False
) -> str:
    """Print every framed shot as the compiler sees it: each entity's placement derived from the scene's world, and what the world added, replaced or could not place.

    The derived placements are never written to the project; this is how you
    read them. A shot without a viewpoint is not listed: it is placed by hand,
    as it always was.

    project_dir: the an project
    shot: one shot id (default: every framed shot)
    json: print the report as JSON instead of text
    frames: print instead the scene's frames of reference, one line per frame per framed shot: its pose in the world as the shot opens and as it closes
    """
    from an.ir.world import WorldError
    from an.project import load
    from an.stage.world import lower_scene, world_report

    project = load(project_dir)
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


_dispatch_funcs = [show]
