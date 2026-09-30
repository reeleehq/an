"""Emotion and gaze compose in the RENDERED pixels, over real pupils (an#98).

The compile-level half is `tests/test_gaze.py::test_one_expression_carries_
emotion_and_gaze_and_both_land_in_one_pose`; this is the pixel half. Four
half-second renders of one synthesized rig (eye stack included) at its first
frame — neutral, `angry` alone, a diagonal gaze alone, and ONE expression
naming both. Each contribution's changed pixels (against neutral) must reappear
in the combined frame, and the combined frame must be neither of the two
single-contribution frames. Region-free on purpose: no layout coordinates to
go stale, only set algebra on decoded pixels.

Verified on a developer machine or on a `run-browser-tests` run, not in the
default lane.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = [pytest.mark.browser, pytest.mark.ffmpeg]

#: One frame in: the saccade generator's first step is zero, so frame 0 is the
#: pure sum of the authored contributions.
FRAME: int = 0
#: Drops the synthesized rig into the frame, as the `expressions` corpus does
#: (`set face y 45`) — at rest its head is above the top edge.
FACE_Y: float = 45.0
#: (row0, row1, col0, col1): head and brows, nothing below the collar. The mp4 is
#: lossy, so the body below it carries encoder noise that would swamp the sets.
#: Per-channel difference that counts as a drawn change. The frames come out of
#: a lossy mp4 and the encoder differs per platform (Linux CI measured 2755
#: changed pixels where a Mac measured 2170 at threshold 0), so exact
#: inequality is noise; a brow or a pupil moving is a difference of 100+.
STRONG_CHANGE: int = 32
#: Share of a contribution's changed pixels that must reappear in the combined frame.
OVERLAP_MIN: float = 0.75
FACE_CROP: tuple[int, int, int, int] = (0, 130, 60, 260)


def _render_frame(actions, work: Path):
    import numpy as np
    from PIL import Image

    from an import init
    from an.characters import new_character
    from an.ir.compose import set_
    from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, Shot
    from an.orchestrate import render_project
    from an.project import load

    root = init(work / "p")
    new_character(root / "assets" / "characters", name="g", seed="g", use_dicebear=False)
    proj = load(root)
    proj.scene = SceneIR(
        meta=Meta(title="compose", duration=0.5, fps=12, resolution=Resolution(width=320, height=240)),
        timeline=[
            Shot(
                id="s1", renderer="cutout", duration=0.5,
                entities=[AssetRef(kind="character", id="g", store="characters", ref="g")],
                actions=[set_("g", "y", FACE_Y), *actions],
            )
        ],
    )
    proj.mall["scenes"]["main"] = proj.scene
    mp4 = render_project(root, output_name="out")
    png = work / "frame.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", f"select=eq(n\\,{FRAME})", "-vframes", "1", str(png)],
        check=True, capture_output=True,
    )
    return np.asarray(Image.open(png).convert("RGB")).astype(int)


def test_emotion_and_gaze_both_reach_the_rendered_pixels():
    import numpy as np

    from an.ir.compose import expression

    gaze = {"gaze_x": 1.0, "gaze_y": 1.0}
    variants = {
        "neutral": [],
        "emotion": [expression("g", "angry", blend=0.0)],
        "gaze": [expression("g", None, axes=gaze, blend=0.0)],
        "both": [expression("g", "angry", axes=gaze, blend=0.0)],
    }
    frames = {}
    for name, actions in variants.items():
        with tempfile.TemporaryDirectory() as d:
            frames[name] = _render_frame(actions, Path(d))

    r0, r1, c0, c1 = FACE_CROP

    def changed(a, b):
        delta = np.abs(frames[a] - frames[b]).max(axis=-1)
        return (delta > STRONG_CHANGE)[r0:r1, c0:c1]

    emotion, gaze_px, both = changed("emotion", "neutral"), changed("gaze", "neutral"), changed("both", "neutral")
    assert emotion.any() and gaze_px.any(), "each contribution must draw something by itself"
    assert int((emotion & gaze_px).sum()) < 0.5 * min(int(emotion.sum()), int(gaze_px.sum())), (
        "the two contributions live in different parts of the face"
    )
    for label, own in (("emotion", emotion), ("gaze", gaze_px)):
        overlap = int((own & both).sum())
        assert overlap >= OVERLAP_MIN * int(own.sum()), f"the {label}'s pixels must reappear in the combined frame ({overlap}/{int(own.sum())})"
    assert changed("both", "emotion").any(), "combined is not the emotion alone"
    assert changed("both", "gaze").any(), "combined is not the gaze alone"
    assert int(both.sum()) > max(int(emotion.sum()), int(gaze_px.sum())), "the union moves more than either part"
