"""Frames of reference in the scene world (ADR 0009 amendment, P4a): the frame
tree, `in:` on members, viewpoints and streams, lowering by `world_pose`, and
the lints.

The byte-identity pin comes first: scenes written WITHOUT `frames`, `in` or
`at_*` actions (the world PR's vocabulary, the travel included) lower to
exactly the output recorded in ``fixtures/world_lowering_golden.json`` from the
code before frames existed.
"""

from __future__ import annotations

import json
from pathlib import Path

from an.ir.schema import (
    AssetRef,
    Attachment,
    Meta,
    Resolution,
    SceneIR,
    Shot,
    StagePlacement,
    Stream,
    Travel,
    Viewpoint,
    World,
    WorldMember,
)
from an.ir.world import lower_world

GOLDEN = Path(__file__).parent / "fixtures" / "world_lowering_golden.json"
BOX = (-5.0, -20.0, 5.0, 0.0)
W, H = 320, 240
EXTENTS = {k: BOX for k in ("left", "right", "hat", "pole", "car", "sign")}


def _lamp(id: str, **kw) -> WorldMember:
    return WorldMember(kind="prop", id=id, store="props", ref="lamp", **kw)


def _legacy_scenes() -> dict[str, SceneIR]:
    """Scenes in the world PR's vocabulary only (no frames, no `in`, no `at_*`)."""

    def base(**kw) -> SceneIR:
        world = World(
            members=[
                _lamp("left", at=(-0.5, 0.4, 2.0), height=0.8),
                _lamp("right", at=(0.5, 0.4, 2.0), height=0.8),
            ],
            viewpoints={
                "two": Viewpoint(at=(0.0, 0.0, 0.0), focal=300.0),
                "right_cu": Viewpoint(subject="right", size="close_up", focal=300.0),
                "road": Viewpoint(at=(0.0, -1.0, 0.0), focal=300.0),
                "side": Viewpoint(at=(0.0, -1.0, 0.0), look=(90.0, 0.0, 0.0), focal=300.0),
            },
        )
        return SceneIR(
            meta=Meta(fps=24, resolution=Resolution(width=W, height=H)),
            world=world,
            **kw,
        )

    still = base(
        timeline=[
            Shot(id="a", duration=1.0, viewpoint="two"),
            Shot(id="b", duration=1.0, viewpoint="right_cu"),
            Shot(
                id="c",
                duration=1.0,
                viewpoint="two",
                entities=[
                    AssetRef(
                        kind="prop",
                        id="left",
                        store="props",
                        ref="lamp",
                        stage=StagePlacement(at=(-40.0, 0.0), scale=2.0),
                    )
                ],
            ),
        ]
    )
    still.world.members.append(
        _lamp("hat", attached=Attachment(to="right", at=(0.0, -20.0), scale=0.5))
    )

    def travelling(view: str) -> SceneIR:
        s = base(
            timeline=[
                Shot(id="s1", duration=2.0, viewpoint=view),
                Shot(id="s2", duration=2.0, viewpoint=view),
            ]
        )
        s.world.travel = Travel(
            speed=4.0,
            far=30.0,
            streams=[Stream(id="pole", ref="lamp", height=1.5, every=3.0, lane=1.2)],
            plates={"far": ["set/sky"]},
        )
        return s

    return {"still": still, "travel": travelling("road"), "travel_side": travelling("side")}


def _dump(scene: SceneIR) -> dict:
    lowered = lower_world(scene, extents=EXTENTS)
    return {
        "scene": json.loads(lowered.scene.model_dump_json()),
        "notes": [
            [n.shot, n.index, n.severity, n.kind, n.entity, n.message]
            for n in lowered.notes
        ],
    }


def test_scenes_without_frames_lower_exactly_as_before():
    golden = json.loads(GOLDEN.read_text())
    got = {name: _dump(scene) for name, scene in _legacy_scenes().items()}
    assert got == golden


def _regenerate() -> None:
    """Rewrite the golden file. Run ONLY on a tree known to be pre-frames:
    ``python -c "import tests.test_world_frames as t; t._regenerate()"``."""
    GOLDEN.write_text(
        json.dumps({n: _dump(s) for n, s in _legacy_scenes().items()}, indent=1)
    )
