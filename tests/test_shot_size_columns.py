"""A shot size's own columns and the partial-size crop policy (an#769)."""

import dataclasses

import pytest

from an.ir.schema import Viewpoint, World, WorldMember
from an.ir.world import resolve_viewpoint
from an.verify.constraints import JUMP_CUT_SIZE_RATIO, jump_cut_between

# A character-like subject: 3 units tall, its box 96 native px wide and 300 tall
# (cutan's reg rig: the head is as wide as the body box).
BOX = (-48.0, -300.0, 48.0, 0.0)
UNIT = 3.0 / 300.0  # world units per native px
AT = (0.0, 0.0, 10.0)
PORTRAIT = (1080.0, 1920.0)
FOCAL = 900.0


def _world(box=BOX):
    member = WorldMember(kind="prop", id="hero", store="props", ref="hero", at=AT, height=3.0)
    return World(members=[member]), {"hero": box}


def _eye(size, bands=None, *, box=BOX, frame=PORTRAIT):
    world, extents = _world(box)
    vp = Viewpoint(subject="hero", size=size, focal=FOCAL)
    width, height = frame
    return resolve_viewpoint(
        world, vp, extents=extents, width=width, height=height, bands=bands
    )


def _visible_half_width(eye, *, frame=PORTRAIT):
    """Half the frame's width in world units at the subject's depth."""
    depth = AT[2] - eye.at[2]
    return frame[0] / 2.0 * depth / eye.focal


def test_without_columns_the_framing_is_as_before():
    for size in ("wide", "full", "medium", "close_up"):
        plain = _eye(size)
        assert _eye(size, {"hero": {size: (0.0, 0.35 if size == "close_up" else 1.0)}}).at
        assert _eye(size, {}).at == plain.at


def test_a_head_as_wide_as_the_box_shows_more_of_the_face_and_is_still_no_jump_cut():
    """At-aspect, a close-up shows about two thirds of a head as wide as the body box; with
    the head's own columns it shows as much as the size step allows, and the
    medium-to-close-up cut stays more than a jump-cut step."""
    face_half = 48.0 * UNIT
    at_aspect = _visible_half_width(_eye("close_up")) / face_half
    bands = {"hero": {"close_up": (0.0, 0.35, 0.0, 1.0), "medium": (0.0, 0.55, 0.0, 1.0)}}
    close, medium = _eye("close_up", bands), _eye("medium", bands)
    shown = _visible_half_width(close) / face_half
    assert at_aspect < 0.7
    assert shown > at_aspect + 0.15
    assert jump_cut_between(medium, close, [AT]) is None
    # and the medium is still a step nearer than the full shot
    assert jump_cut_between(_eye("full", bands), medium, [AT]) is None


def test_the_policy_crops_only_as_much_as_the_step_needs():
    """The close-up comes in to just past the jump-cut step from the medium, and
    no nearer: the step, not the band's height, is what binds here."""
    bands = {"hero": {"close_up": (0.0, 0.35, 0.0, 1.0), "medium": (0.0, 0.55, 0.0, 1.0)}}
    close, medium = _eye("close_up", bands), _eye("medium", bands)
    ratio = (AT[2] - medium.at[2]) / (AT[2] - close.at[2])
    assert JUMP_CUT_SIZE_RATIO < ratio < JUMP_CUT_SIZE_RATIO * 1.05


def test_a_band_narrower_than_the_frame_is_shown_whole():
    """A head half the box's width fits whole at a height-bound distance: no crop."""
    bands = {"hero": {"close_up": (0.0, 0.35, 0.25, 0.75)}}
    close = _eye("close_up", bands)
    assert _visible_half_width(close) >= 24.0 * UNIT
    # landscape: the height binds, so the columns change nothing
    land = (1920.0, 1080.0)
    assert _eye("close_up", bands, frame=land).at == pytest.approx(_eye("close_up", frame=land).at)


def test_an_off_centre_subject_keeps_its_head_in_frame():
    """An arm reaching right moves the box's centre off the head; the head's own
    columns keep it in frame at medium and close-up (at-aspect lost it)."""
    box = (-30.0, -300.0, 120.0, 0.0)  # head at x -30..30, an arm out to 120
    head = (-30.0 * UNIT, 30.0 * UNIT)  # world x about the member's position
    head_cols = (0.0, 60.0 / 150.0)

    def head_in_frame(eye):
        half = _visible_half_width(eye)
        return eye.at[0] - half <= head[0] and head[1] <= eye.at[0] + half

    assert not head_in_frame(_eye("close_up", box=box))  # the at-aspect band misses it
    bands = {"hero": {"close_up": (0.0, 0.35, *head_cols), "medium": (0.0, 0.55, *head_cols)}}
    assert head_in_frame(_eye("close_up", bands, box=box))
    assert head_in_frame(_eye("medium", bands, box=box))


def test_member_shot_sizes_takes_columns_and_says_what_it_drops(monkeypatch):
    import an.genres.registry as registry
    from an.stage.world import member_shot_sizes

    real = registry.entity_kind

    def hook(member, mall, box):
        return {
            "close_up": (0.0, 0.35, 0.1, 0.9),
            "medium": (0.0, 0.55, 0.9, 0.1),  # columns reversed
            "full": (0.0, 1.0, 0.0),  # three numbers
        }

    def kind(name):
        found = real(name)
        return dataclasses.replace(found, shot_sizes=hook) if name == "prop" else found

    monkeypatch.setattr(registry, "entity_kind", kind)
    world, extents = _world()
    problems = {}
    got = member_shot_sizes(world, {}, extents=extents, problems=problems)
    assert got == {"hero": {"close_up": (0.0, 0.35, 0.1, 0.9)}}
    assert "0 <= left < right <= 1" in problems["hero"]["medium"]
    assert "(top, bottom, left, right)" in problems["hero"]["full"]


def _eye_look(size, bands, *, look, box=BOX, frame=PORTRAIT):
    world, extents = _world(box)
    vp = Viewpoint(subject="hero", size=size, focal=FOCAL, look=look)
    return resolve_viewpoint(
        world, vp, extents=extents, width=frame[0], height=frame[1], bands=bands
    )


@pytest.mark.parametrize("pitch", [-30.0, -10.0, 0.0, 20.0, 40.0])
def test_the_step_holds_off_axis_by_the_check_s_own_measure(pitch):
    """The jump-cut check reads a size where it is framed, the centre of the band the
    camera aims at (`Projection.aim`, an#853), and the policy compares the same
    distance, so a pitched camera, looking up or down, keeps the step: the close-up
    is never read as farther than the medium, nor as a jump cut from it."""
    bands = {"hero": {"close_up": (0.0, 0.35, 0.0, 1.0), "medium": (0.0, 0.55, 0.0, 1.0)}}
    look = (0.0, pitch, 0.0)
    close = _eye_look("close_up", bands, look=look)
    medium = _eye_look("medium", bands, look=look)
    assert jump_cut_between(medium, close, [AT]) is None
    assert close.view(close.aim)[2] < medium.view(medium.aim)[2]


def test_columns_on_the_wider_size_only_still_keep_the_step():
    """A rig that measures a torso but no head: the medium has columns, the
    close-up is the table's. The close-up is still a step nearer."""
    box = (-200.0, -150.0, 200.0, 0.0)  # a wide subject
    bands = {"hero": {"medium": (0.0, 0.55, 0.4, 0.6)}}
    for frame in (PORTRAIT, (1920.0, 1080.0)):
        close = _eye("close_up", bands, box=box, frame=frame)
        medium = _eye("medium", bands, box=box, frame=frame)
        assert jump_cut_between(medium, close, [AT]) is None
        assert close.view(AT)[2] < medium.view(AT)[2]


def test_a_two_shot_is_not_cropped_to_keep_the_step():
    """With two subjects the band union spans the gap between them, so cropping
    its sides would crop the subjects: the policy leaves a group alone."""
    hero = WorldMember(kind="prop", id="a", store="props", ref="hero", at=(-1.5, 0.0, 10.0), height=3.0)
    other = WorldMember(kind="prop", id="b", store="props", ref="hero", at=(1.5, 0.0, 10.0), height=3.0)
    world = World(members=[hero, other])
    extents = {"a": BOX, "b": BOX}
    cols = {"close_up": (0.0, 0.35, 0.0, 1.0), "medium": (0.0, 0.55, 0.0, 1.0)}
    vp = Viewpoint(subject=["a", "b"], size="close_up", focal=FOCAL)
    eye = resolve_viewpoint(world, vp, extents=extents, width=1080, height=1920, bands={"a": cols, "b": cols})
    half = 1080 / 2.0 * (10.0 - eye.at[2]) / FOCAL
    face = 48.0 * UNIT
    assert eye.at[0] - half <= -1.5 - face and 1.5 + face <= eye.at[0] + half
