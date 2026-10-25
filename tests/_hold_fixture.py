"""A small project for the hold tests (an#502): a figure that can bend, an item, a stand with a socket.

- ``figure``: a torso (a root part, pivot at the hip) with two one-link arms
  hanging from its shoulders and two legs (root parts); its stage point is its
  feet (``origin`` at the root bone), so the floor under it is its ``stage.at``
  y. View box 400, so 0.8625 scene px per unit at scale 1.
- ``stick``: a bar drawn in a PNG with transparent margins (its ink is 20 x 200
  of a 60 x 260 canvas), with a ``grip`` bone 60 units below its centre.
- ``stand``: a box with a ``hand`` bone above it, rotated 90 degrees: a socket
  that holds things sideways.

Built in a temporary folder by :func:`make_project`; never rendered.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Scene px per view-box unit at stage scale 1 (345 / 400).
K = 345.0 / 400.0

FIGURE = {
    "kind": "PropDescriptor",
    "schema_version": "0.2.0",
    "name": "figure",
    "view_box": [0, 0, 400, 400],
    "origin": [200.0, 400.0],
    "bones": [
        {"name": "root", "x": 200.0, "y": 400.0},
        {"name": "torso", "parent": "root", "x": 0.0, "y": -120.0},
        {"name": "arm_r", "parent": "torso", "x": 40.0, "y": -140.0},
        {"name": "arm_l", "parent": "torso", "x": -40.0, "y": -140.0},
        {"name": "head", "parent": "torso", "x": 0.0, "y": -160.0},
        {"name": "leg_r", "parent": "root", "x": 20.0, "y": -120.0},
        {"name": "leg_l", "parent": "root", "x": -20.0, "y": -120.0},
    ],
    "slots": [
        {"name": "leg_l", "bone": "leg_l", "draw_order": 0, "attachment": "leg"},
        {"name": "leg_r", "bone": "leg_r", "draw_order": 0, "attachment": "leg"},
        {"name": "torso", "bone": "torso", "draw_order": 1, "attachment": "torso"},
        {"name": "head", "bone": "head", "draw_order": 2, "attachment": "head"},
        {"name": "arm_l", "bone": "arm_l", "draw_order": 3, "attachment": "arm"},
        {"name": "arm_r", "bone": "arm_r", "draw_order": 3, "attachment": "arm"},
    ],
    "skins": {
        "default": {
            "name": "default",
            "slots": {
                "leg_l": {"leg": {"path": "parts/leg.svg", "anchor": [0.5, 0.0]}},
                "leg_r": {"leg": {"path": "parts/leg.svg", "anchor": [0.5, 0.0]}},
                "torso": {"torso": {"path": "parts/torso.svg", "anchor": [0.5, 1.0]}},
                "head": {"head": {"path": "parts/head.svg", "anchor": [0.5, 1.0]}},
                "arm_l": {"arm": {"path": "parts/arm.svg", "anchor": [0.5, 0.0]}},
                "arm_r": {"arm": {"path": "parts/arm.svg", "anchor": [0.5, 0.0]}},
            },
        }
    },
}

STICK = {
    "kind": "PropDescriptor",
    "schema_version": "0.2.0",
    "name": "stick",
    "view_box": [0, 0, 400, 400],
    "origin": [200.0, 200.0],
    "bones": [
        {"name": "root", "x": 200.0, "y": 200.0},
        {"name": "grip", "parent": "root", "x": 0.0, "y": 60.0},
    ],
    "slots": [{"name": "body", "bone": "root", "draw_order": 0, "attachment": "body"}],
    "skins": {
        "default": {
            "name": "default",
            "slots": {
                "body": {
                    "body": {
                        "path": "parts/body.png",
                        "anchor": [0.5, 0.5],
                        "width": 60,
                        "height": 260,
                    }
                }
            },
        }
    },
}

STAND = {
    "kind": "PropDescriptor",
    "schema_version": "0.2.0",
    "name": "stand",
    "view_box": [0, 0, 400, 400],
    "origin": [200.0, 400.0],
    "bones": [
        {"name": "root", "x": 200.0, "y": 400.0},
        {"name": "hand", "parent": "root", "x": 0.0, "y": -250.0},
    ],
    "slots": [{"name": "body", "bone": "root", "draw_order": 0, "attachment": "body"}],
    "skins": {
        "default": {
            "name": "default",
            "slots": {
                "body": {"body": {"path": "parts/body.svg", "anchor": [0.5, 1.0]}}
            },
        }
    },
}


def _svg(w: int, h: int, colour: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="{colour}"/></svg>'
    )


def _stick_png(path: Path) -> None:
    from PIL import Image

    im = Image.new("RGBA", (60, 260), (0, 0, 0, 0))
    for x in range(20, 40):
        for y in range(30, 230):
            im.putpixel((x, y), (120, 80, 40, 255))
    im.save(path)


def make_project(root: Path, scene_md: str):
    """A project at ``root`` with the three props and ``scene_md``, loaded."""
    from an.project import init, load

    init(root)
    props = root / "assets" / "props"
    parts = {
        "figure": (
            FIGURE,
            {
                "leg.svg": (16, 120, "#333333"),
                "torso.svg": (60, 160, "#6f8f3f"),
                "head.svg": (60, 60, "#e0b080"),
                "arm.svg": (16, 200, "#2f6f9f"),
            },
        ),
        "stick": (STICK, {}),
        "stand": (STAND, {"body.svg": (80, 150, "#9f6f2f")}),
    }
    for name, (desc, svgs) in parts.items():
        d = props / name
        (d / "parts").mkdir(parents=True, exist_ok=True)
        (d / "prop.json").write_text(json.dumps(desc), encoding="utf-8")
        for fname, (w, h, colour) in svgs.items():
            (d / "parts" / fname).write_text(_svg(w, h, colour), encoding="utf-8")
    _stick_png(props / "stick" / "parts" / "body.png")
    (root / "scene.md").write_text(scene_md, encoding="utf-8")
    json_path = root / "ir" / "scene.json"
    if json_path.exists():
        json_path.unlink()
    return load(root)


def scene(
    actions: str,
    *,
    entities: str = "",
    shot: str = "duration: 4.0\nsolve: {ground: 200}",
    duration: float = 4.0,
) -> str:
    """A one-shot ``scene.md``: the figure at x -100 standing on y 200, the stick
    lying on the floor at x 40, the stand at x 160; ``actions`` as YAML lines."""
    base_entities = """- {kind: prop, id: fig, store: props, ref: figure, stage: {at: [-100, 200]}}
- {kind: prop, id: stand, store: props, ref: stand, stage: {at: [160, 200]}}
- {kind: prop, id: stick, store: props, ref: stick, stage: {at: [40, 150], scale: 0.5, after: fig}, overrides: {held_by: ground}}
"""
    return f"""# Holds

```yaml meta
title: Holds
author: ''
duration: {duration}
fps: 24
resolution:
  width: 640
  height: 480
default_renderer: cutout
```

## Shot s (cutout)

```yaml shot
{shot}
```

```yaml entities
{entities or base_entities}```

```yaml actions
{actions}
```
"""
