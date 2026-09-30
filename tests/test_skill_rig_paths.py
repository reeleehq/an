"""The `an` skill's list of rig node paths is generated from the code (an#196).

End-user agents addressed ``ned/left_brow`` and ``wellington/mouth`` — nodes no
rig builds, because the face lives under ``<entity>/head/``. The skill lists
the paths each rig builds; this test regenerates that list from the compiler's
own stage builder (`an.motion.stage_poses`) and fails when the skill's copy
drifts, printing the block to paste. It also pins the arm facts the skill
states (which side each arm hangs on).
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import pytest

from an.characters import new_character
from an.ir.schema import AssetRef, Shot
from an.motion import rest_pose, stage_poses
from an.project import init
from an.stores import build_project_mall

SKILL = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "an" / "SKILL.md"
BLOCK_RE = re.compile(
    r"(<!-- rig-paths:begin[^>]*-->\n)(.*?)(<!-- rig-paths:end -->)", re.S
)
ENTITY = "c"

#: (label in the skill, character-store ref, `new_character` kwargs or None
#: for "no descriptor": the placeholder rig).
RIGS = (
    ("`an character new --offline` (default)", "made", {}),
    ("`new_character(..., gaze=False)`", "no_gaze", {"gaze": False}),
    ("no descriptor (the placeholder rig)", "missing", None),
)


def _shot(ref: str) -> Shot:
    return Shot(
        id="s",
        entities=[AssetRef(kind="character", id=ENTITY, store="characters", ref=ref)],
    )


def _rigs_mall(root: Path):
    """A project at ``root`` holding one character per descriptor-backed rig."""
    root = init(root)
    mall = build_project_mall(root)
    for _label, ref, kwargs in RIGS:
        if kwargs is not None:
            new_character(
                root / "assets" / "characters", name=ref, use_dicebear=False, **kwargs
            )
    return mall


@pytest.fixture(scope="module")
def mall(tmp_path_factory):
    return _rigs_mall(tmp_path_factory.mktemp("rigs") / "p")


def rig_paths_block(mall) -> str:
    """The skill's generated block: one table row per rig."""
    rows = ["| rig | node paths |", "|---|---|"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the placeholder's stand-in warning
        for label, ref, _kwargs in RIGS:
            paths = sorted(stage_poses(_shot(ref), mall=mall))
            rows.append(f"| {label} | {', '.join(f'`{p}`' for p in paths)} |")
    return "\n".join(rows) + "\n"


def test_the_skill_lists_the_paths_the_rigs_build(mall):
    match = BLOCK_RE.search(SKILL.read_text(encoding="utf-8"))
    assert match, "the rig-paths markers are missing from the an skill"
    expected = rig_paths_block(mall)
    assert match.group(2) == expected, (
        "the an skill's rig node paths drifted from what the compiler builds; "
        f"replace the block between the rig-paths markers with:\n\n{expected}"
    )


def test_face_parts_live_under_the_head(mall):
    paths = stage_poses(_shot("made"), mall=mall)
    assert f"{ENTITY}/head/mouth" in paths and f"{ENTITY}/mouth" not in paths
    assert f"{ENTITY}/head/left_brow" in paths


def test_arm_l_hangs_on_the_viewers_left(mall):
    """What the skill says about the sign of an arm rotation rests on this."""
    shot = _shot("made")
    left = rest_pose(shot, f"{ENTITY}/arm_l", mall=mall)["x"]
    right = rest_pose(shot, f"{ENTITY}/arm_r", mall=mall)["x"]
    assert left < 0 < right


if __name__ == "__main__":  # pragma: no cover — regenerate the block by hand
    import tempfile

    print(rig_paths_block(_rigs_mall(Path(tempfile.mkdtemp()) / "p")))
