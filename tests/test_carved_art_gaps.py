"""Carved-art gaps from the Alice & Bob rebuilds (an#220).

End-user agents rebuilt a two-character scene three times from art carved out
of real footage. Four things still got in their way:

1. a raster part's declared ``width``/``height`` did not override its pixel
   size, so every PNG had to be resampled by the rig's units-per-pixel;
2. ``walk`` lifted one hem half of a robe figure (it barely read) and swung a
   profile-only character's legs only when told ``view: side`` by hand;
3. one ``source`` per character, so a figure carved from several clips could
   not be credited part by part;
4. a profile head carved with its eye and mouth baked in forced the face slots
   to be hidden in the side view, so blinks and lip-sync vanished there.

Every fixture is synthetic, drawn here with Pillow — the carved art is
copyrighted and never enters the repo. The pixel tests are ``browser``-marked:
they run on a developer machine or a PR labelled ``run-browser-tests``.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.compile import (
    SCENE_PX_PER_VIEW_BOX,
    CutoutCompileWarning,
    compile_shot,
)
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.characters.schema import (
    Attachment,
    CharacterDescriptor,
    SlotPose,
    attachment_box,
    view_variant_sets,
)
from an.ir.compose import delay, play, sequence, set_
from an.ir.schema import (
    AssetRef,
    Dialogue,
    SetAction,
    Shot,
    VisemeKeyframe,
    VisemeTrack,
)

W, H = 320, 180
FPS = 10
#: k for the default 1024-unit view box: scene px per view_box unit.
K = SCENE_PX_PER_VIEW_BOX / 1024.0


# --- fixtures ---------------------------------------------------------------


def _png(path: Path, size, rgba=(200, 30, 30, 255)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, rgba).save(path)
    return path


#: One colour per face drawing, so a pixel says which one is on screen.
FRONT_EYE_OPEN, FRONT_EYE_CLOSED = (0, 200, 200, 255), (0, 0, 250, 255)
SIDE_EYE_OPEN, SIDE_EYE_CLOSED = (250, 250, 0, 255), (250, 0, 250, 255)


def _character(root: Path, name: str = "rae", *, views=True, **fields) -> dict:
    """A raster character on the default rig: every part a PNG, plus (with
    ``views``) a ``front``/``side`` view set on the head and per-view face
    sets — ``eyelid@side`` on both eyes, ``viseme@side`` on the mouth."""
    doc = json.loads(CharacterDescriptor(name=name, **fields).model_dump_json())
    char_dir = root / name
    skin = doc["skins"]["default"]["slots"]
    for slot, attachments in skin.items():
        for att_name, att in attachments.items():
            att["path"] = att["path"].replace(".svg", ".png")
            colour = (90, 60, 30, 255)
            if slot.endswith("_eye"):
                colour = FRONT_EYE_OPEN if att_name == "open" else FRONT_EYE_CLOSED
            _png(char_dir / att["path"], (40, 40), colour)
    doc["source"] = {"provider": "me", "license": "cc0-1.0"}
    if views:
        head = skin["head"]["head"]
        for view in ("front", "side"):
            skin["head"][view] = {**head, "path": f"parts/head_{view}.png"}
            _png(char_dir / f"parts/head_{view}.png", (40, 40), (90, 60, 30, 255))
        doc["asset_sets"]["view"] = {"front": "front", "side": "side"}
        doc["swap_poses"] = {"view": {"front": {}, "side": {
            "left_eye": {"alpha": 0.0}, "left_brow": {"alpha": 0.0},
        }}}
        for eye in ("left_eye", "right_eye"):
            base = skin[eye]["open"]
            for key, colour in (("open", SIDE_EYE_OPEN), ("closed", SIDE_EYE_CLOSED)):
                rel = f"parts/{eye}_{key}_side.png"
                skin[eye][f"{key}_side"] = {**base, "path": rel}
                _png(char_dir / rel, (40, 40), colour)
        doc["asset_sets"]["eyelid@side"] = {"OPEN": "open_side", "CLOSED": "closed_side"}
        mouth = skin["mouth"]
        side_mouths = {}
        for key, att_name in doc["asset_sets"]["viseme"].items():
            rel = f"parts/mouth/{att_name}_side.png"
            mouth[f"{att_name}_side"] = {**mouth[att_name], "path": rel}
            _png(char_dir / rel, (40, 40), (10, 200, 10, 255))
            side_mouths[key] = f"{att_name}_side"
        doc["asset_sets"]["viseme@side"] = side_mouths
    return doc


def _store(tmp_path, *docs):
    from an.stores.characters import CharactersStore

    store = CharactersStore(tmp_path / "chars")
    for doc in docs:
        store[doc["name"]] = doc
    return store


def _ref(name="rae"):
    return AssetRef(kind="character", id=name, store="characters", ref=name)


def _shot(*actions, entities=None, dialogue=(), duration=4.0) -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=duration,
        entities=list(entities or [_ref()]),
        actions=list(actions),
        dialogue=list(dialogue),
    )


def _compile(shot, store, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CutoutCompileWarning)
        return compile_shot(
            shot, mall={"characters": store}, fps=FPS, width=W, height=H, **kw
        )


def _pose(doc, t):
    return evaluate_timeline(timeline_from_scene(doc), t)


def _swap(pose, path):
    """The swap sets written on ``path`` at this instant: ``{set: key}``."""
    return {
        prop: value
        for (target, prop), value in pose.items()
        if target == path and prop.split("@")[0] in ("eyelid", "viseme")
    }


def _node(scene, *path):
    node = scene.scene
    for name in path:
        node = next(c for c in node.children if c.name == name)
    return node


# --- 1. a declared part size wins -------------------------------------------


def test_attachment_box_keeps_the_art_s_aspect():
    assert attachment_box(None, None, (10, 16)) == (10.0, 16.0)
    assert attachment_box(30, None, (10, 16)) == (30.0, 48.0)
    assert attachment_box(None, 32, (10, 16)) == (20.0, 32.0)
    assert attachment_box(30, 30, (10, 16)) == (18.75, 30.0)  # contained


def test_a_declared_width_resizes_a_raster_part_without_resampling_it(tmp_path):
    """The OverSimplified agent upscaled every PNG by its units-per-pixel,
    because the pixel count was the size whatever the descriptor said."""
    doc = _character(tmp_path / "chars", views=False)
    head = doc["skins"]["default"]["slots"]["head"]["head"]
    head["width"] = 120.0  # view_box units; the PNG is 40x40
    scene = _compile(_shot(), _store(tmp_path, doc))
    visual = _node(scene, "rae", "head").visual
    assert (visual.width, visual.height) == pytest.approx((120 * K, 120 * K))
    torso = _node(scene, "rae", "torso").visual  # undeclared: its pixel count
    assert (torso.width, torso.height) == pytest.approx((40 * K, 40 * K))


def test_a_declared_box_of_another_aspect_is_contained_and_validate_says_so(tmp_path):
    from an.characters.validate import validate_character

    doc = _character(tmp_path / "chars", views=False)
    torso = doc["skins"]["default"]["slots"]["torso"]["torso"]
    torso["width"], torso["height"] = 80.0, 40.0
    store = _store(tmp_path, doc)
    visual = _node(_compile(_shot(), store), "rae", "torso").visual
    assert (visual.width, visual.height) == pytest.approx((40 * K, 40 * K))
    report = validate_character(tmp_path / "chars" / "rae")
    (finding,) = [f for f in report.findings if "draws contained" in f.description]
    assert finding.severity == "warning" and "40x40" in finding.description


def test_a_swap_key_is_boxed_by_its_own_declared_size(tmp_path):
    doc = _character(tmp_path / "chars", views=False)
    mouth = doc["skins"]["default"]["slots"]["mouth"]
    mouth["mouth_d"]["height"] = 80.0  # the wide-open mouth, drawn bigger
    scene = _compile(_shot(), _store(tmp_path, doc))
    visual = _node(scene, "rae", "head", "mouth").visual
    (geometry,) = [g for a, g in visual.asset_geometry.items() if ".mouth_d." in a]
    assert (geometry["width"], geometry["height"]) == pytest.approx((80 * K, 80 * K))


# --- 2. walk: the view and the gait come from the character --------------------


def test_a_profile_only_character_walks_as_a_profile_with_nothing_passed(tmp_path):
    """The Reiniger agent had to pass `view: side` to get its legs swinging."""
    doc = _character(tmp_path / "chars", views=False, rest_view="side")
    scene = _compile(
        _shot(play("rae", "walk", args={"steps": 2, "step_s": 0.5})),
        _store(tmp_path, doc),
    )
    contact = _pose(scene, 0.5)
    assert contact[("rae/leg_l", "rotation")] != pytest.approx(0.0)
    assert ("rae/leg_l", "y") not in contact  # swung, not lifted


def test_a_hem_gait_tilts_the_halves_and_sways_the_body(tmp_path):
    """The OverSimplified robe: facing the camera the hem halves tilt in turn
    while the body sways and bobs — what read in the agent's hand-built walk."""
    from an.motion import DFLT_WALK_HEM_TILT

    doc = _character(tmp_path / "chars", views=False, gait="hem")
    scene = _compile(
        _shot(play("rae", "walk", args={"steps": 2, "step_s": 0.5})),
        _store(tmp_path, doc),
    )
    start, mid, contact = (_pose(scene, t) for t in (0.0, 0.25, 0.5))
    assert contact[("rae/leg_l", "rotation")] == pytest.approx(DFLT_WALK_HEM_TILT)
    assert contact[("rae/leg_r", "rotation")] == pytest.approx(-DFLT_WALK_HEM_TILT)
    assert mid[("rae", "rotation")] != pytest.approx(0.0)  # the sway
    assert mid[("rae", "y")] < start[("rae", "y")]  # the bob
    assert ("rae/leg_l", "y") not in contact  # no lift


def test_an_author_s_gait_wins_over_the_character_s(tmp_path):
    doc = _character(tmp_path / "chars", views=False, gait="hem")
    scene = _compile(
        _shot(play("rae", "walk", args={"steps": 2, "step_s": 0.5, "gait": "legs"})),
        _store(tmp_path, doc),
    )
    rest, lifted = _pose(scene, 0.0), _pose(scene, 0.25)
    assert lifted[("rae/leg_l", "y")] < rest[("rae/leg_l", "y")]  # a stepping leg
    assert ("rae/leg_l", "rotation") not in _pose(scene, 0.5)


def test_an_unknown_gait_is_refused_where_it_is_written():
    from pydantic import ValidationError

    from an.motion import walk

    with pytest.raises(ValidationError, match="gait must be one of"):
        CharacterDescriptor(name="x", gait="shuffle")
    with pytest.raises(ValueError, match="gait must be one of"):
        walk("x", gait="shuffle")


def test_unset_view_facts_are_not_written_into_the_descriptor():
    data = json.loads(CharacterDescriptor(name="x").model_dump_json())
    assert "rest_view" not in data and "gait" not in data
    data = json.loads(CharacterDescriptor(name="x", rest_view="side").model_dump_json())
    assert data["rest_view"] == "side"


# --- 3. per-part sources --------------------------------------------------------


def test_credits_list_each_part_s_own_source_once(tmp_path):
    from an.credits import collect_credits

    doc = _character(tmp_path / "chars", views=False)
    clip = {"provider": "youtube", "id": "clip2", "license": "all-rights-reserved",
            "attribution": "carved from clip 2 - private study"}
    slots = doc["skins"]["default"]["slots"]
    slots["head"]["head"]["source"] = clip
    for att in slots["left_eye"].values():  # two attachments, two files
        att["source"] = {"provider": "openverse", "license": "cc0-1.0"}
    report = collect_credits({"characters": _store(tmp_path, doc)})
    assets = {e.asset: e.license_class for e in report.entries}
    assert assets["characters/rae"] == "free"
    assert assets["characters/rae/parts/head.png"] == "private"
    assert {a for a in assets if "left_eye" in a or "eye_l" in a} == {
        "characters/rae/" + att["path"] for att in slots["left_eye"].values()}
    assert not report.publishable
    assert report.format().splitlines()[2].startswith("NOT PUBLISHABLE")


def test_an_attachment_without_a_source_stores_no_source_key():
    assert "source" not in Attachment(path="parts/a.png").model_dump()
    att = Attachment(path="parts/a.png", source={"provider": "me", "license": "pd"})
    assert Attachment.model_validate(att.model_dump()).source.license == "pd"


# --- 4. per-view face sets ------------------------------------------------------


def test_view_sets_are_not_mouth_forms(tmp_path):
    from an.characters.validate import validate_character
    from an.expression.binding import declared_mouth_variants

    doc = _character(tmp_path / "chars")
    _store(tmp_path, doc)
    desc = CharacterDescriptor.model_validate(doc)
    assert view_variant_sets(desc) == {
        "eyelid": {"side": "eyelid@side"}, "viseme": {"side": "viseme@side"}}
    assert declared_mouth_variants(desc) == {}
    report = validate_character(tmp_path / "chars" / "rae")
    assert report.passed, [f.description for f in report.findings if f.severity == "error"]


def test_the_lids_key_on_the_view_s_eyelid_set_while_it_shows(tmp_path):
    """Blinks keep running in the profile, on the profile's own lid art — and
    the front's come back when the character turns back."""
    doc = _character(tmp_path / "chars")
    scene = _compile(
        _shot(
            SetAction(kind="set", target="rae", property="view", value="side", at=1.0),
            SetAction(kind="set", target="rae", property="view", value="front", at=3.0),
        ),
        _store(tmp_path, doc),
    )
    eye = "rae/head/right_eye"
    assert _swap(_pose(scene, 0.5), eye) == {"eyelid": "OPEN"}
    assert _swap(_pose(scene, 1.0), eye) == {"eyelid@side": "OPEN"}  # at the swap
    assert _swap(_pose(scene, 2.0), eye) == {"eyelid@side": "OPEN"}
    assert _swap(_pose(scene, 3.5), eye) == {"eyelid": "OPEN"}
    # some blink lands in the profile, on the profile's closed art
    closed = [t / FPS for t in range(10, 30)
              if _swap(_pose(scene, t / FPS), eye) == {"eyelid@side": "CLOSED"}]
    assert closed, "no blink closed the profile's eye"


def test_a_line_in_profile_speaks_on_the_view_s_mouth(tmp_path):
    doc = _character(tmp_path / "chars")
    line = Dialogue(
        speaker="rae", text="Hi", start=1.5, duration=0.6,
        viseme_track=VisemeTrack(keyframes=[
            VisemeKeyframe(time=0.0, viseme="X"), VisemeKeyframe(time=0.1, viseme="D"),
            VisemeKeyframe(time=0.4, viseme="X")]),
    )
    scene = _compile(
        _shot(SetAction(kind="set", target="rae", property="view", value="side", at=1.0),
              dialogue=[line]),
        _store(tmp_path, doc),
    )
    mouth = "rae/head/mouth"
    assert _swap(_pose(scene, 1.7), mouth) == {"viseme@side": "D"}
    assert _swap(_pose(scene, 1.2), mouth) == {"viseme@side": "X"}  # silent, profile
    assert _swap(_pose(scene, 0.5), mouth) == {"viseme": "X"}  # before the turn
    assert _swap(_pose(scene, 3.0), mouth) == {"viseme@side": "X"}  # after the line


def test_a_blink_played_in_profile_closes_the_profile_s_eye(tmp_path):
    doc = _character(tmp_path / "chars")
    scene = _compile(
        _shot(SetAction(kind="set", target="rae", property="view", value="side", at=0.0),
              sequence(delay(1.0), play("rae", "blink"))),
        _store(tmp_path, doc),
    )
    props = {
        ch.property
        for anim_id, anim in scene.animations.items()
        if anim_id.startswith("__play__")
        for ch in anim.channels
        if ch.target.endswith("_eye")
    }
    assert props == {"eyelid@side"}


def test_an_authored_blink_in_front_does_not_cost_the_profile_its_eye(tmp_path):
    """Review of an#220: an authored lid channel used to switch the solver's
    lids off for the shot — and with them the only path the profile's eye art
    reaches the screen by."""
    doc = _character(tmp_path / "chars")
    scene = _compile(
        _shot(sequence(delay(0.3), play("rae", "blink")),
              SetAction(kind="set", target="rae", property="view", value="side", at=1.0)),
        _store(tmp_path, doc),
    )
    eye = "rae/head/right_eye"
    for t in (1.5, 2.5, 3.5):
        assert _swap(_pose(scene, t), eye) == {"eyelid@side": "OPEN"}
    # authored overrides the AUTO blinks (an#88): none closes the profile's eye
    assert not [t for t in range(10, 40)
                if _swap(_pose(scene, t / FPS), eye) == {"eyelid@side": "CLOSED"}]


def _line(start, duration, *codes):
    step = duration / (len(codes) + 1)
    return Dialogue(
        speaker="rae", text="Hi", start=start, duration=duration,
        viseme_track=VisemeTrack(keyframes=[
            VisemeKeyframe(time=round(k * step, 3), viseme=c) for k, c in enumerate(codes)]),
    )


def _no_two_mouths(scene, *, until=4.0, dt=0.001):
    for k in range(int(until / dt)):
        live = _swap(_pose(scene, k * dt), "rae/head/mouth")
        assert len(live) <= 1, (k * dt, live)


def test_a_line_that_crosses_a_turn_changes_mouth_with_the_view(tmp_path):
    doc = _character(tmp_path / "chars")
    scene = _compile(
        _shot(SetAction(kind="set", target="rae", property="view", value="side", at=0.0),
              SetAction(kind="set", target="rae", property="view", value="front", at=2.0),
              dialogue=[_line(1.5, 1.0, "X", "D", "D", "D", "X")]),
        _store(tmp_path, doc),
    )
    assert set(_swap(_pose(scene, 1.9), "rae/head/mouth")) == {"viseme@side"}
    assert set(_swap(_pose(scene, 2.1), "rae/head/mouth")) == {"viseme"}
    _no_two_mouths(scene)


def test_a_line_ending_on_a_turn_leaves_one_mouth_on_screen(tmp_path):
    """Review of an#220: the hold after a line that ends exactly at a turn
    started on the line's last frame, so two mouth sets tied there."""
    doc = _character(tmp_path / "chars")
    scene = _compile(
        _shot(SetAction(kind="set", target="rae", property="view", value="side", at=0.0),
              SetAction(kind="set", target="rae", property="view", value="front", at=2.0),
              dialogue=[_line(1.3, 0.7, "X", "D", "X")]),
        _store(tmp_path, doc),
    )
    _no_two_mouths(scene)


def test_validate_reports_unreadable_boxed_art_instead_of_crashing(tmp_path):
    from an.characters.validate import validate_character

    doc = _character(tmp_path / "chars", views=False)
    torso = doc["skins"]["default"]["slots"]["torso"]["torso"]
    torso.update(path="parts/torso.svg", width=80.0, height=40.0)
    (tmp_path / "chars" / "rae" / "parts" / "torso.svg").write_text("<svg not xml", encoding="utf-8")
    _store(tmp_path, doc)
    report = validate_character(tmp_path / "chars" / "rae")
    assert any("torso.svg" in f.ir_path for f in report.findings)


def test_a_scene_without_views_compiles_exactly_as_before(tmp_path):
    """Per-view sets change nothing until a view they serve shows."""
    doc = _character(tmp_path / "chars")
    bare = _character(tmp_path / "b" / "chars", views=False)
    a = _compile(_shot(), _store(tmp_path, doc))
    b = _compile(_shot(), _store(tmp_path / "b", bare))
    assert a.animations and a.animations == b.animations
    assert a.timeline == b.timeline


def test_validate_warns_when_a_view_hides_the_mouth_during_a_line(tmp_path):
    from an.ir.schema import Meta, SceneIR
    from an.ir.validate import validate_semantic

    doc = _character(tmp_path / "chars")
    doc["swap_poses"]["view"]["side"]["mouth"] = {"alpha": 0.0}
    store = _store(tmp_path, doc)
    line = Dialogue(speaker="rae", text="Hi", start=1.5, duration=0.6)
    scene = SceneIR(meta=Meta(title="t", duration=4.0), timeline=[_shot(
        set_("rae", "view", "side"), dialogue=[line])])
    report = validate_semantic(scene, available_characters=store)
    hits = [f for f in report.findings if "hides its mouth" in f.description]
    assert hits and hits[0].severity == "warning"
    assert "viseme@side" in hits[0].description
    del doc["swap_poses"]["view"]["side"]["mouth"]
    store = _store(tmp_path / "ok", doc)
    report = validate_semantic(scene, available_characters=store)
    assert not [f for f in report.findings if "hides its mouth" in f.description]


# --- pixels -----------------------------------------------------------------------


#: Tall enough for the whole default rig (345 scene px) to be in frame.
PIXEL_FRAME = (320, 400)


def _render(shot, store, tmp_path):
    from an.adapters._base import RenderContext
    from an.adapters.cutout.render import CutoutRenderer

    return CutoutRenderer().render(
        shot,
        RenderContext(mall={"characters": store}, work_dir=tmp_path / "out", fps=FPS,
                      resolution=PIXEL_FRAME, strict_assets=True),
    )


def _colours(frame):
    import numpy as np
    from PIL import Image

    img = np.asarray(Image.open(frame).convert("RGB")).reshape(-1, 3)
    return {tuple(int(c) for c in px) for px in img}


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_the_profile_blinks_on_its_own_lid_art(tmp_path):
    """Turned to the side, the eye on screen is the profile's (yellow), a blink
    closes it on the profile's closed art (magenta), and the front's white and
    blue lids never show."""
    doc = _character(tmp_path / "chars")
    store = _store(tmp_path, doc)
    shot = _shot(
        SetAction(kind="set", target="rae", property="view", value="side", at=0.0),
        duration=3.0,
    )
    scene = _compile(shot, store)
    eye = "rae/head/right_eye"
    closed_at = next(t / FPS for t in range(30)
                     if _swap(_pose(scene, t / FPS), eye) == {"eyelid@side": "CLOSED"})
    result = _render(shot, store, tmp_path)
    frames = result.frame_manifest
    open_frame = frames[0]
    closed_frame = frames[round(closed_at * FPS)]

    def has(frame, rgba, tol=8):
        return any(all(abs(a - b) <= tol for a, b in zip(px, rgba[:3]))
                   for px in _colours(frame))

    assert has(open_frame, SIDE_EYE_OPEN) and not has(open_frame, FRONT_EYE_OPEN)
    assert has(closed_frame, SIDE_EYE_CLOSED)
    assert not has(closed_frame, FRONT_EYE_CLOSED)


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_in_pixels_a_declared_width_draws_the_part_that_wide(tmp_path):
    """A 40x40 PNG torso declared 400 units wide draws 400 units wide — ten
    times the columns it covers undeclared, at its pixel count."""
    import numpy as np
    from PIL import Image

    widths = {}
    for declared in (None, 400.0):
        root = tmp_path / str(declared)
        doc = _character(root / "chars", views=False)
        slots = doc["skins"]["default"]["slots"]
        for slot, attachments in slots.items():  # everything else transparent
            for att in attachments.values():
                if slot != "torso":
                    _png(root / "chars" / "rae" / att["path"], (40, 40), (0, 0, 0, 0))
        _png(root / "chars" / "rae" / "parts" / "torso.png", (40, 40), (255, 0, 0, 255))
        slots["torso"]["torso"]["width"] = declared
        result = _render(_shot(duration=0.2), _store(root, doc), root)
        img = np.asarray(Image.open(result.frame_manifest[0]).convert("RGB")).astype(int)
        red = (img[..., 0] > 200) & (img[..., 1] < 60) & (img[..., 2] < 60)
        widths[declared] = int(red.any(axis=0).sum())
    assert widths[None] == pytest.approx(40 * K, abs=2)  # its pixel count, x k
    assert widths[400.0] == pytest.approx(400 * K, abs=2)  # its declared width
