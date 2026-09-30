"""Character variety and colour roles: the factory's knobs, and a StylePack
reaching role-tagged SVG art.

The e2e style test (South Park and OverSimplified from a four-line script)
found every offline character had the same body in the same crimson top, with
no hat, colour or proportion options, and that a StylePack could not reach an
SVG rig at all — its author regex-edited generated fill literals by hand. Four
rules this file holds:

1. **Every knob's default is the old character, byte for byte** — the art and
   every descriptor field that existed before (the golden digests below were
   taken from the factory before the knobs).
2. **Each knob changes what it says**, and nothing it does not.
3. **Roles are recorded at the source**: the factory writes `colour_roles`, and
   the field round-trips, normalised, and refuses what a swap cannot express.
4. **A pack reaches tagged art and says, once, what it could not reach.**
"""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import warnings
from pathlib import Path

import pydantic
import pytest

from an.adapters.cutout.compile import CutoutCompileWarning, compile_shot
from an.characters import new_character
from an.characters.colour_roles import recolour_svg
from an.characters.factory import BUILDS, HATS, PALETTE_ROLES
from an.characters.schema import (
    FACE_OFFSETS,
    REFERENCE_HEAD_HEIGHT,
    CharacterDescriptor,
)
from an.characters.svg_utils import raster_size
from an.ir.schema import AssetRef, Shot
from an.styles import StylePack

#: The descriptor fields that existed before the knobs. `colour_roles` is new
#: and additive, so it is the one field a default character gained.
DESCRIPTOR_KEYS = (
    "bones", "slots", "skins", "asset_sets", "animations", "face_overlay",
    "gaze_travel", "metadata", "view_box",
)

#: Taken from the factory BEFORE the knobs existed (every SVG it writes, plus
#: `DESCRIPTOR_KEYS`). If a later change moves one on purpose, re-take it and
#: say why in the PR — this is the "defaults reproduce today's output" guard.
GOLDEN_FACTORY_DIGESTS = {
    "kyle": "edc362cc65443bc4",
    "stan": "5653f424b643c17b",
    "maya": "21db2602f0d688f3",
    "nobody": "17e3ce903b4b0374",
}


def _factory_digest(char_dir: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(char_dir.rglob("*.svg"), key=lambda p: p.relative_to(char_dir).as_posix()):
        # Platform-neutral: posix paths, and LF (text mode writes CRLF on Windows).
        h.update(f.relative_to(char_dir).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    desc = json.loads((char_dir / "character.json").read_text("utf-8"))
    h.update(json.dumps({k: desc.get(k) for k in DESCRIPTOR_KEYS}, sort_keys=True).encode())
    return h.hexdigest()[:16]


def _make(tmp: Path, name: str = "c", **knobs) -> Path:
    return new_character(tmp, name=name, use_dicebear=False, **knobs).parent


def _desc(char_dir: Path) -> CharacterDescriptor:
    return CharacterDescriptor.model_validate_json(
        (char_dir / "character.json").read_text("utf-8")
    )


# --- 1. defaults are the old character ------------------------------------------


@pytest.mark.parametrize("name", sorted(GOLDEN_FACTORY_DIGESTS))
def test_the_default_character_is_byte_identical_to_the_pre_knob_factory(tmp_path, name):
    # `views=False`: the turnaround (an#197) only ADDS parts and descriptor
    # entries, which `tests/test_turnaround.py::test_views_are_additive_...`
    # holds against this very character — so the pre-knob digest still pins
    # everything the character had before either.
    assert _factory_digest(_make(tmp_path, name, views=False)) == GOLDEN_FACTORY_DIGESTS[name]


def test_a_default_character_records_no_knob_in_its_metadata(tmp_path):
    meta = _desc(_make(tmp_path)).metadata
    assert not {"build", "hat", "sash", "palette", "head_scale"} & set(meta)


# --- 2. each knob changes what it says ------------------------------------------


def test_palette_colours_the_parts_that_role_names(tmp_path):
    pal = {"skin": "#fbd9b5", "hair": "#3b1f0e", "clothing": "#f06a23",
           "leg": "#3d8b3d", "accessory": "#3f9b3a"}
    c = _make(tmp_path, palette=pal, hat="beanie", sash=True)
    parts = {p.stem: p.read_text("utf-8") for p in (c / "parts").glob("*.svg")}
    assert pal["skin"] in parts["head"] and pal["skin"] in parts["arm_l"]
    assert pal["skin"] in parts["eye_l_closed"], "the gaze lid is the head's skin"
    assert pal["hair"] in parts["head"] and pal["hair"] in parts["brow_r"]
    assert pal["clothing"] in parts["torso"] and pal["clothing"] in parts["arm_r"]
    assert pal["leg"] in parts["leg_l"] and pal["leg"] in parts["leg_r"]
    assert pal["accessory"] in parts["head"] and pal["accessory"] in parts["torso"]
    roles = _desc(c).colour_roles
    assert roles["parts/torso.svg"][pal["clothing"]] == "clothing"
    assert roles["parts/torso.svg"][pal["accessory"]] == "accessory"
    assert roles["parts/head.svg"][pal["accessory"]] == "accessory"
    assert roles["parts/leg_l.svg"] == {pal["leg"]: "leg"}


def test_palette_leaves_unnamed_roles_at_the_seeds_colours(tmp_path):
    plain = _make(tmp_path / "a")
    only_leg = _make(tmp_path / "b", palette={"leg": "#123456"})
    for part in ("head", "torso", "arm_l", "brow_l"):
        assert (plain / "parts" / f"{part}.svg").read_bytes() == (
            only_leg / "parts" / f"{part}.svg"
        ).read_bytes(), part
    assert "#123456" in (only_leg / "parts" / "leg_l.svg").read_text("utf-8")


@pytest.mark.parametrize("bad", [{"lip": "#aa0000"}, {"skin": "peach"}])
def test_a_palette_role_or_colour_the_factory_cannot_draw_is_refused(tmp_path, bad):
    with pytest.raises(ValueError):
        _make(tmp_path, palette=bad)
    assert not (tmp_path / "c").exists(), "refused before anything is written"


def test_two_roles_in_one_part_are_drawn_in_distinct_literals(tmp_path):
    """Palette swapping keys a role by its literal, so a clothing colour equal to
    the outline would recolour the outline too. The factory nudges one step."""
    c = _make(tmp_path, palette={"clothing": "#222222", "hair": "#222222"})
    roles = _desc(c).colour_roles["parts/torso.svg"]
    assert sorted(roles.values()) == ["clothing", "hair"]
    assert "#222222" not in roles, "the outline's literal is not a role key"


@pytest.mark.parametrize("build", sorted(BUILDS))
def test_a_build_sets_the_legs_the_bones_and_the_art_from_one_record(tmp_path, build):
    body = BUILDS[build]
    c = _make(tmp_path, build=build)
    bones = {b.name: b for b in _desc(c).bones}
    assert bones["torso"].y == -body.leg_length == bones["leg_l"].y
    assert raster_size(c / "parts" / "leg_l.svg")[1] == body.leg_length
    assert raster_size(c / "parts" / "torso.svg") == tuple(body.torso_size)
    assert raster_size(c / "parts" / "arm_r.svg")[1] == body.arm_length


def test_builds_differ_the_way_their_names_say(tmp_path):
    legs = {b: BUILDS[b].leg_length for b in BUILDS}
    assert legs["squat"] < legs["stick"] < legs["regular"] < legs["tall"]
    torso = {b: BUILDS[b].torso_size for b in BUILDS}
    assert torso["squat"][0] > torso["squat"][1], "squat is wider than it is tall"
    assert BUILDS["stick"].arm_width < BUILDS["regular"].arm_width / 3


def test_head_scale_scales_the_head_and_its_whole_face(tmp_path):
    s = 1.5
    plain, big = _make(tmp_path / "a"), _make(tmp_path / "b", head_scale=s)
    assert raster_size(big / "parts" / "head.svg")[1] == pytest.approx(REFERENCE_HEAD_HEIGHT * s)
    for part in ("eye_l_open", "pupil_r", "brow_l", "mouth/mouth_a", "mouth/mouth_e_happy"):
        (w0, h0), (w1, h1) = (raster_size(d / "parts" / f"{part}.svg") for d in (plain, big))
        assert (w1, h1) == pytest.approx((w0 * s, h0 * s)), part
    skin = _desc(big).skins["default"].slots
    for slot, (x, y) in FACE_OFFSETS.items():
        for att in skin[slot].values():
            assert (att.x, att.y) == pytest.approx((x * s, y * s)), slot
    assert _desc(big).gaze_travel == pytest.approx({"x": 9.0 * s, "y": 5.0 * s})
    assert _desc(big).metadata["head_scale"] == s


def test_add_gaze_on_a_scaled_rig_redraws_at_the_rigs_scale(tmp_path):
    from an.characters.factory import add_gaze

    c = _make(tmp_path, head_scale=1.5)
    before = {p: raster_size(c / "parts" / f"{p}.svg") for p in ("pupil_l", "eye_r_closed")}
    add_gaze(c)
    assert {p: raster_size(c / "parts" / f"{p}.svg") for p in before} == before
    assert _desc(c).gaze_travel == pytest.approx({"x": 13.5, "y": 7.5})


@pytest.mark.parametrize("hat", [h for h in HATS if h != "none"])
def test_a_hat_is_drawn_on_the_head_in_the_accessory_colour(tmp_path, hat):
    plain, hatted = _make(tmp_path / "a"), _make(tmp_path / "b", hat=hat, palette={"accessory": "#0a0b0c"})
    head = (hatted / "parts" / "head.svg").read_text("utf-8")
    assert "#0a0b0c" in head and head != (plain / "parts" / "head.svg").read_text("utf-8")
    assert raster_size(hatted / "parts" / "head.svg") == raster_size(plain / "parts" / "head.svg"), (
        "the hat is inside the head's drawing, so the face layout does not move"
    )
    assert _desc(hatted).colour_roles["parts/head.svg"]["#0a0b0c"] == "accessory"


def test_a_sash_is_drawn_across_the_torso_under_its_outline(tmp_path):
    torso = (_make(tmp_path, sash=True, palette={"accessory": "#0a0b0c"}) / "parts" / "torso.svg").read_text("utf-8")
    assert "#0a0b0c" in torso and "clip-path" in torso
    assert torso.rindex('fill="none" stroke="#222"') > torso.index("#0a0b0c"), "outline drawn last"


def test_unknown_knob_values_are_refused(tmp_path):
    for knobs in ({"build": "chonky"}, {"hat": "crown"}, {"head_scale": 0}, {"head_scale": 9}):
        with pytest.raises(ValueError):
            _make(tmp_path, **knobs)
    with pytest.raises(ValueError, match="offline head"):
        new_character(tmp_path, name="d", use_dicebear=True, hat="cap")


def test_the_cli_parses_a_palette_and_passes_the_knobs(tmp_path):
    from an.characters.cli import new

    msg = new("k", out_dir=str(tmp_path), offline=True, palette="clothing=#f06a23, leg=#3d8b3d",
              build="squat", head_scale=1.3, hat="beanie", sash=True)
    assert msg.startswith("created"), msg
    meta = _desc(tmp_path / "k").metadata
    assert meta["build"] == "squat" and meta["hat"] == "beanie" and meta["sash"] is True
    assert meta["head_scale"] == 1.3 and meta["palette"]["clothing"] == "#f06a23"
    assert "unknown palette role" in new("j", out_dir=str(tmp_path), offline=True, palette="lip=#aa0000")


# --- 3. the descriptor field ------------------------------------------------------


def test_colour_roles_round_trip_normalised(tmp_path):
    c = CharacterDescriptor(name="m", colour_roles={"parts/torso.svg": {"#A83249": "clothing", "#fa0": "hair"}})
    back = CharacterDescriptor.model_validate_json(c.model_dump_json())
    assert back.colour_roles == {"parts/torso.svg": {"#a83249": "clothing", "#ffaa00": "hair"}}
    assert CharacterDescriptor(name="m").colour_roles == {}, "absent = untagged art"


def test_a_factory_descriptor_round_trips_its_roles(tmp_path):
    c = _make(tmp_path, palette={"clothing": "#f06a23"})
    raw = json.loads((c / "character.json").read_text("utf-8"))
    assert CharacterDescriptor.model_validate(raw).colour_roles == raw["colour_roles"]
    assert raw["colour_roles"]["parts/torso.svg"]["#f06a23"] == "clothing"


@pytest.mark.parametrize(
    "roles",
    [
        {"parts/x.svg": {"#aabbcc": "lip"}},  # not a role a pack can set
        {"parts/x.svg": {"#aabbcc": "skin", "#ABC": "hair"}},  # one literal, two roles
        {"parts/x.svg": {"red": "skin"}},  # not a literal
    ],
)
def test_colour_roles_refuse_what_a_swap_cannot_express(roles):
    with pytest.raises(pydantic.ValidationError):
        CharacterDescriptor(name="m", colour_roles=roles)


# --- 4. the compiler ----------------------------------------------------------------


def _compile(tmp: Path, pack, *, tagged: bool = True, **knobs):
    from an.project import init, load

    root = init(tmp / "p")
    c = new_character(root / "assets" / "characters", name="kyle", use_dicebear=False, **knobs).parent
    if not tagged:
        raw = json.loads((c / "character.json").read_text("utf-8"))
        raw.pop("colour_roles")
        (c / "character.json").write_text(json.dumps(raw), encoding="utf-8")
    shot = Shot(id="s", renderer="cutout", duration=1.0,
                entities=[AssetRef(kind="character", id="kyle", store="characters", ref="kyle")])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        doc = compile_shot(shot, mall=load(root).mall, fps=24, style_pack=pack)
    return doc, [w for w in caught if issubclass(w.category, CutoutCompileWarning)]


def _inline_svgs(doc) -> dict[str, str]:
    return {
        alias: base64.b64decode(a.src.split(",", 1)[1]).decode("utf-8")
        for alias, a in doc.assets.textures.items()
        if a.src.startswith("data:")
    }


def test_a_pack_recolours_role_tagged_svg_art(tmp_path):
    pack = StylePack(name="noir", roles={"clothing": "#202028", "skin": "#d8d8d8", "accessory": "#ff00ff"})
    doc, caught = _compile(tmp_path, pack, hat="cap")
    svgs = _inline_svgs(doc)
    by_part = {alias.split(".")[1]: svg for alias, svg in svgs.items()}
    assert "#202028" in by_part["torso"] and "#202028" in by_part["arm_l"]
    assert "#d8d8d8" in by_part["head"] and "#d8d8d8" in by_part["arm_r"]
    assert "#d8d8d8" in by_part["left_eye"], "the lid follows the skin (an#99)"
    assert "#ff00ff" in by_part["head"]
    assert "leg_l" not in by_part, "a role the pack does not set leaves its part alone"
    assert not caught, "a tagged rig is reached — nothing to warn about"


def test_a_recoloured_texture_is_content_addressed(tmp_path):
    a, _ = _compile(tmp_path / "a", StylePack(name="x", roles={"clothing": "#202028"}))
    b, _ = _compile(tmp_path / "b", StylePack(name="x", roles={"clothing": "#303038"}))
    torso = lambda d: next(k for k in d.assets.textures if k.startswith("kyle.torso.torso."))  # noqa: E731
    assert torso(a) != torso(b)


def test_no_pack_reads_and_rewrites_nothing(tmp_path):
    doc, caught = _compile(tmp_path, None)
    assert not _inline_svgs(doc) and not caught


def test_a_pack_that_sets_none_of_the_rigs_roles_rewrites_nothing(tmp_path):
    doc, caught = _compile(tmp_path, StylePack(name="x", roles={"sky": "#000000"}))
    assert not _inline_svgs(doc) and not caught


def test_untagged_art_is_warned_about_in_one_line(tmp_path):
    doc, caught = _compile(tmp_path, StylePack(name="noir", roles={"skin": "#d8d8d8"}), tagged=False)
    assert not _inline_svgs(doc)
    (w,) = caught
    text = str(w.message)
    assert "could not reach ['kyle']" in text and "\n" not in text
    assert len(text) < 240, "one line, not a paragraph"


def test_the_warning_text_does_not_depend_on_the_shot(tmp_path):
    """Python's registry shows an identical warning once per call site, which is
    what makes it one line per scene — so nothing shot-specific may be in it."""
    _, (a,) = _compile(tmp_path / "a", StylePack(name="n", roles={"skin": "#d8d8d8", "sky": "#000000"}), tagged=False)
    _, (b,) = _compile(tmp_path / "b", StylePack(name="n", roles={"skin": "#d8d8d8", "sky": "#000000"}), tagged=False)
    assert str(a.message) == str(b.message)


def test_add_gaze_on_an_untagged_rig_tags_nothing(tmp_path):
    """The lid's colour on an untagged rig is READ off the head art; recording
    it as `skin` would be inferring a role from a pixel — the pack would then
    repaint the lids and not the face (an#99), and silence the warning."""
    from an.characters.factory import add_gaze

    c = _make(tmp_path, gaze=False)
    raw = json.loads((c / "character.json").read_text("utf-8"))
    raw["colour_roles"] = {}
    (c / "character.json").write_text(json.dumps(raw), encoding="utf-8")
    add_gaze(c)
    assert _desc(c).colour_roles == {}
    add_gaze(c, skin="peachpuff")  # a named colour: a valid fill, never a role key
    assert _desc(c).colour_roles == {}


def test_a_dicebear_rig_is_not_half_tagged_and_the_pack_says_so(tmp_path, monkeypatch):
    """A DiceBear head's skin and hair are its own; tagging them on the body
    alone would repaint the hands and not the face, silently."""
    import an.characters.factory as factory
    from an.project import init, load

    avatar = factory._fallback_face_svg("x")  # any valid SVG will do
    monkeypatch.setattr(factory, "fetch_dicebear", lambda seed, style: avatar)
    root = init(tmp_path / "p")
    new_character(root / "assets" / "characters", name="d", use_dicebear=True)
    roles = _desc(root / "assets" / "characters" / "d").colour_roles
    assert "parts/head.svg" not in roles
    assert not {r for m in roles.values() for r in m.values()} & {"skin", "hair"}
    assert roles["parts/torso.svg"] and "clothing" in roles["parts/torso.svg"].values()
    shot = Shot(id="s", renderer="cutout", duration=1.0,
                entities=[AssetRef(kind="character", id="d", store="characters", ref="d")])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compile_shot(shot, mall=load(root).mall, fps=24,
                     style_pack=StylePack(name="n", roles={"skin": "#d8d8d8", "clothing": "#202028"}))
    msgs = [str(w.message) for w in caught if issubclass(w.category, CutoutCompileWarning)]
    assert any("could not reach ['d (skin)']" in m for m in msgs), msgs


def test_recolour_touches_paint_only():
    svg = '<svg><rect id="a83249" fill="#a83249"/><use href="#a83249"/><g style="stroke:#A83249"/></svg>'
    out = recolour_svg(svg, {"#a83249": "#000000"})
    assert out == '<svg><rect id="a83249" fill="#000000"/><use href="#a83249"/><g style="stroke:#000000"/></svg>'


def test_palette_roles_are_style_pack_roles():
    from an.styles import REACHABLE_ROLES

    assert set(PALETTE_ROLES) <= REACHABLE_ROLES


# --- the pixels ---------------------------------------------------------------------


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_role_recolour_reaches_the_rendered_pixels(tmp_path):
    """The compile-level tests prove the texture changed; this proves the frame
    did. One synthesized rig, rendered with and without a pack whose clothing is
    pure magenta: the magenta must appear where the costume was, and the old
    clothing colour must be gone from the frame.

    Verified on a developer machine or on a `run-browser-tests` run, not in the
    default lane.
    """
    import subprocess

    import numpy as np
    from PIL import Image

    from an.ir.schema import Meta, Resolution, SceneIR
    from an.orchestrate import render_project
    from an.project import init, load

    magenta = np.array([255, 0, 255])

    def frame(pack: StylePack | None, work: Path) -> np.ndarray:
        root = init(work / "p")
        new_character(root / "assets" / "characters", name="k", seed="kyle", use_dicebear=False)
        if pack is not None:
            (root / "assets" / "styles").mkdir(parents=True, exist_ok=True)
            (root / "assets" / "styles" / f"{pack.name}.json").write_text(pack.model_dump_json(), encoding="utf-8")
        proj = load(root)
        proj.scene = SceneIR(
            meta=Meta(title="roles", duration=0.25, fps=12,
                      resolution=Resolution(width=320, height=240),
                      style_pack=pack.name if pack else None),
            timeline=[Shot(id="s1", renderer="cutout", duration=0.25,
                           entities=[AssetRef(kind="character", id="k", store="characters", ref="k")])],
        )
        proj.mall["scenes"]["main"] = proj.scene
        mp4 = render_project(root, output_name="out")
        png = work / "f.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vframes", "1", str(png)],
                       check=True, capture_output=True)
        return np.asarray(Image.open(png).convert("RGB")).astype(int)

    def near(img, rgb, tol=20):
        # Tight: this seed's skin (#8b5a3b) and the lips sit within 40 of the
        # costume's #a83249, and a loose count would measure them too.
        return int((np.abs(img - rgb).max(axis=-1) <= tol).sum())

    plain = frame(None, tmp_path / "a")
    packed = frame(StylePack(name="m", roles={"clothing": "#ff00ff"}), tmp_path / "b")
    clothing = np.array([0xA8, 0x32, 0x49])  # kyle's seed colour (`_palette_for_seed`)
    assert near(plain, clothing) > 200, "the default costume is on screen"
    assert near(plain, magenta) == 0
    assert near(packed, magenta) > 0.8 * near(plain, clothing), "the costume turned magenta"
    assert near(packed, clothing) < 0.05 * near(plain, clothing), "and the old colour is gone"
