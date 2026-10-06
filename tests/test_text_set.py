"""Text content as a replacement set: ``texts``, ``rest`` and ``unit: block`` (an#341, T1 of an#331).

A text block with ``texts`` is replacement animation applied to text: one
``block_0`` node drawing the rest string, whose ``text`` swap set names every
other string's drawing. Checked where each half can fail:

- the document refuses ``texts`` without ``unit: block``, both or neither of
  ``text``/``texts``, a ``rest`` that is not a key, a key that cannot be a swap key;
- the build: one node, a set naming one content-addressed texture per string, and
  per-key geometry anchored on the ``align`` edge (a right-aligned string grows
  leftwards, on one baseline);
- the declaration goes through the core ``prop`` kind's ``swap_declaration`` hook,
  so the compiler's swap checks and ``an validate`` learn the set with no
  text-specific branch;
- ``set <id> text <key>`` (entity sugar) and ``set <id>/block_0 text <key>`` swap at
  the keyed time; an undeclared key is refused by compile and by validate.
"""

from __future__ import annotations

import pytest

from an.adapters.cutout.compile import CutoutCompileError, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.adapters.cutout.timeline import evaluate_timeline, timeline_from_scene
from an.genres import entity_kind, without_genres
from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, SetAction, Shot
from an.ir.validate import validate_semantic
from an.text import TextDescriptor, resolve_text

W, H = 320, 240

_SET = {"d1": "1", "d12": "12", "d300": "300"}


def _doc(**kw) -> dict:
    return {"kind": "TextDescriptor", "name": "day", "unit": "block", "texts": _SET, **kw}


def _shot(actions=(), *, ref="day", eid="day") -> Shot:
    return Shot(
        id="s",
        renderer="cutout",
        duration=2.0,
        entities=[AssetRef(kind="prop", id=eid, store="props", ref=ref)],
        actions=list(actions),
    )


def _block(doc) -> dict:
    (node,) = to_dict(doc)["scene"]["children"]
    (block,) = node["children"]
    return block


def _errors(shot, mall) -> list[str]:
    scene = SceneIR(
        meta=Meta(duration=2.0, resolution=Resolution(width=W, height=H)), timeline=[shot]
    )
    report = validate_semantic(scene, available_props=mall["props"])
    return [f.description for f in report.findings if f.severity == "error"]


# --- the document ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields, needle",
    [
        ({"texts": _SET}, "needs unit='block'"),
        ({"texts": _SET, "unit": "word"}, "needs unit='block'"),
        ({"texts": _SET, "unit": "block", "text": "x"}, "both were given"),
        ({"unit": "block"}, "neither was given"),
        ({"texts": _SET, "unit": "block", "rest": "d9"}, "not a key of `texts`"),
        ({"text": "x", "rest": "d1"}, "needs `texts`"),
        ({"texts": {"a/b": "1"}, "unit": "block"}, "cannot be a swap key"),
        ({"texts": {"a::b": "1"}, "unit": "block"}, "cannot be a swap key"),
        ({"texts": {"a": "  "}, "unit": "block"}, "only whitespace"),
        ({"texts": {}, "unit": "block"}, "`texts` is empty"),
    ],
)
def test_the_document_refuses_a_set_it_could_not_draw(fields, needle):
    with pytest.raises(ValueError, match=needle):
        TextDescriptor(name="t", **fields)


def test_rest_defaults_to_the_first_key_and_round_trips():
    desc = TextDescriptor(name="t", texts=_SET, unit="block")
    assert desc.rest_key == "d1" and desc.content == "1"
    assert TextDescriptor(name="t", texts=_SET, unit="block", rest="d12").content == "12"
    assert TextDescriptor.model_validate_json(desc.model_dump_json()) == desc
    # A single-string document dumps exactly as before: nothing new is written.
    assert "texts" not in TextDescriptor(name="t", text="hi").model_dump()


def test_a_block_unit_is_one_node_for_a_single_string_too():
    mall = {"props": {"t": {"kind": "TextDescriptor", "name": "t", "text": "two\nlines", "unit": "block"}}}
    (node,) = to_dict(compile_shot(_shot(ref="t", eid="t"), mall, width=W, height=H))["scene"]["children"]
    assert [c["name"] for c in node["children"]] == ["block_0"]
    assert node["children"][0]["visual"].get("asset_sets") is None


# --- the build ------------------------------------------------------------------------


def test_the_block_carries_one_texture_per_string_in_a_text_set():
    doc = compile_shot(_shot(), {"props": {"day": _doc()}}, width=W, height=H)
    block = _block(doc)
    assert block["name"] == "block_0"
    visual = block["visual"]
    key_map = visual["asset_sets"]["text"]
    assert sorted(key_map) == sorted(_SET)
    assert visual["asset_id"] == key_map["d1"], "the rest key is what is drawn first"
    assert len(set(key_map.values())) == 3
    for alias in key_map.values():
        assert alias.startswith("text.day.block_0.")
        assert to_dict(doc)["assets"]["textures"][alias]["src"].startswith("data:")


def test_two_keys_with_one_string_share_one_texture_and_no_geometry():
    mall = {"props": {"day": _doc(texts={"a": "7", "b": "7", "c": "8"})}}
    visual = _block(compile_shot(_shot(), mall, width=W, height=H))["visual"]
    key_map = visual["asset_sets"]["text"]
    assert key_map["a"] == key_map["b"] != key_map["c"]
    assert key_map["a"] not in (visual.get("asset_geometry") or {})


@pytest.mark.parametrize("align", ["right", "left", "center"])
def test_every_key_is_placed_on_the_align_edge_of_the_rest_string(align):
    """A changing string needs a fixed reference point (reviewer G9): with
    ``align: right`` "300" ends where "1" ends, so a counter grows leftwards."""
    visual = _block(
        compile_shot(_shot(), {"props": {"day": _doc(align=align)}}, width=W, height=H)
    )["visual"]
    geometry = visual["asset_geometry"]
    rest_w = visual["width"]
    for key in ("d12", "d300"):
        g = geometry[visual["asset_sets"]["text"][key]]
        assert g["width"] > rest_w, key
        assert g["y"] == 0.0, "one-line keys share the rest string's baseline"
        left, right = g["x"] - g["width"] / 2, g["x"] + g["width"] / 2
        if align == "right":
            assert abs(right - rest_w / 2) <= 1.0, (key, g)
            assert left < -rest_w / 2
        elif align == "left":
            assert abs(left + rest_w / 2) <= 1.0, (key, g)
            assert right > rest_w / 2
        else:
            assert abs(g["x"]) <= 1.0, (key, g)


# --- the declaration and the swap -----------------------------------------------------


def test_the_set_is_declared_through_the_prop_kind_hook():
    mall = {"props": {"day": _doc(), "plain": {"kind": "TextDescriptor", "name": "p", "text": "x"}}}
    declare = entity_kind("prop").swap_declaration
    decl = declare(AssetRef(kind="prop", id="day", store="props", ref="day"), mall)
    assert decl.sets == {"text": {k: k for k in _SET}}
    assert decl.descriptor is None, "a genre's lowering reads a descriptor as a rig"
    assert declare(AssetRef(kind="prop", id="p", store="props", ref="plain"), mall) is None
    assert declare(AssetRef(kind="prop", id="x", store="props", ref="missing"), mall) is None


@pytest.mark.parametrize("target", ["day", "day/block_0"])
def test_a_set_of_text_swaps_the_string_at_the_keyed_time(target):
    actions = [SetAction(target=target, property="text", value="d300", at=1.0)]
    doc = compile_shot(_shot(actions), {"props": {"day": _doc()}}, width=W, height=H)
    tl = timeline_from_scene(doc)
    assert evaluate_timeline(tl, 0.5).get(("day/block_0", "text")) is None
    assert evaluate_timeline(tl, 1.5).get(("day/block_0", "text")) == "d300"


def test_the_swap_compiles_with_no_genre_registered():
    """Core, not cut-out: the declaration and the entity-level fan-out need no genre."""
    actions = [SetAction(target="day", property="text", value="d12", at=0.5)]
    with without_genres():
        doc = compile_shot(_shot(actions), {"props": {"day": _doc()}}, width=W, height=H)
    assert evaluate_timeline(timeline_from_scene(doc), 1.0).get(("day/block_0", "text")) == "d12"


@pytest.mark.parametrize(
    "action, needle, said",
    [
        (SetAction(target="day", property="text", value="d9"), "not a declared key", "'d9' is not a declared key of 'day''s 'text' set (it has: ['d1', 'd12', 'd300'])"),
        (SetAction(target="day/block_0", property="text", value="d9"), "not a declared key", "'d9' is not a declared key of 'day''s 'text' set (it has: ['d1', 'd12', 'd300'])"),
        (SetAction(target="day/block_0", property="txt", value="d1"), "no asset set named", "'txt' names no declared asset set of 'day' (it has: ['text'])"),
    ],
)  # fmt: skip
def test_an_undeclared_key_or_set_is_refused_by_compile_and_by_validate(action, needle, said):
    """Validate names the DECLARED set (read through the kind's hook), not
    merely "this raises": without the hook it would say the block has no
    descriptor at all."""
    mall = {"props": {"day": _doc()}}
    with pytest.raises(CutoutCompileError, match=needle):
        compile_shot(_shot([action]), mall, width=W, height=H)
    errors = _errors(_shot([action]), mall)
    assert len(errors) == 1 and said in errors[0], errors


def test_validate_reports_texts_without_a_block_unit():
    mall = {"props": {"day": {"kind": "TextDescriptor", "name": "d", "texts": _SET}}}
    assert any("needs unit='block'" in e for e in _errors(_shot(), mall))
    with pytest.raises(CutoutCompileError, match="needs unit='block'"):
        compile_shot(_shot(), mall, width=W, height=H)


def test_validate_passes_a_scene_that_compiles():
    actions = [
        SetAction(target="day", property="text", value="d12", at=0.5),
        SetAction(target="day/block_0", property="text", value="d300", at=1.0),
    ]
    mall = {"props": {"day": _doc()}}
    compile_shot(_shot(actions), mall, width=W, height=H)
    assert _errors(_shot(actions), mall) == []


def test_a_glyph_only_one_key_uses_is_refused_at_validate():
    mall = {"props": {"day": _doc(texts={"a": "1", "b": "€"})}}
    assert any("cannot be set" in e for e in _errors(_shot(), mall))


def test_overrides_supply_the_set_per_entity():
    style = {"kind": "TextDescriptor", "name": "s", "unit": "block", "align": "right"}
    desc = resolve_text(style, {"texts": {"x": "1"}})
    assert desc.texts == {"x": "1"} and desc.rest_key == "x"
