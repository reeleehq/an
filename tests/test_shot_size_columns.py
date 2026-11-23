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
