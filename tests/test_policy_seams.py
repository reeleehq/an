"""The seams a style's policy reaches the core through (an#348, ADR 0002 decision 4).

A shot's ``policy`` and a StylePack's are declared fields: shape-checked on
read, absent from a dump when unset (so every existing document is
byte-identical), and a ``yaml shot`` block keeps a shot's through ``scene.md``.
``an validate`` hands registered checks the ``styles`` store, so a genre can
check the pack the scene names before a render.
"""

from __future__ import annotations

import pytest

from an.genres import Genre, SemanticCheck, register_genre, without_genres
from an.ir.schema import SceneIR, Shot
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.ir.validate import validate_semantic
from an.styles import StylePack

GLIDE = {"locomotion": ["loco.glide", {"method": "loco.hop", "args": {"height": 20}}]}


def test_an_unset_policy_is_not_serialized():
    assert "policy" not in Shot(id="s").model_dump(mode="json")
    assert "policy" not in StylePack(name="noir").model_dump(mode="json")


def test_a_policy_is_kept_as_authored_and_round_trips():
    shot = Shot(id="s", policy=GLIDE)
    assert shot.model_dump(mode="json")["policy"] == GLIDE
    assert Shot.model_validate(shot.model_dump(mode="json")).policy == GLIDE
    pack = StylePack(name="south_park", policy={"locomotion": ["loco.bounce"]})
    assert StylePack.model_validate(pack.model_dump(mode="json")).policy == pack.policy


@pytest.mark.parametrize(
    "bad", [["loco.glide"], {"locomotion": [{"method": "loco.hop", "colour": 1}]}, {"locomotion": [3]}]
)
def test_a_malformed_policy_is_refused_on_read(bad):
    with pytest.raises(ValueError, match="policy"):
        Shot(id="s", policy=bad)
    with pytest.raises(ValueError, match="policy"):
        StylePack(name="x", policy=bad)


def test_a_yaml_shot_block_keeps_its_policy():
    scene = SceneIR.model_validate({"timeline": [{"id": "s", "policy": GLIDE}, {"id": "t"}]})
    md = ir_to_markdown(scene)
    assert "policy:" in md
    again = markdown_to_ir(md)
    assert again.timeline[0].policy == GLIDE
    assert again.timeline[1].policy is None
    assert markdown_to_ir(ir_to_markdown(again)).timeline[0].policy == GLIDE


def test_validate_hands_checks_the_styles_store():
    seen = []
    check = SemanticCheck(
        "demo.reads_the_pack",
        lambda ctx: seen.append((ctx.stores.get("styles") or {}).get(ctx.scene.meta.style_pack)),
        stage="scene",
    )
    scene = SceneIR.model_validate({"meta": {"style_pack": "noir"}, "timeline": [{"id": "s"}]})
    pack = StylePack(name="noir", policy={"locomotion": ["loco.bounce"]}).model_dump(mode="json")
    with without_genres():
        register_genre(Genre("demo_policy", checks=(check,)))
        validate_semantic(scene, available_styles={"noir": pack})
        validate_semantic(scene)  # no store: the check sees none
    assert seen == [pack, None]


def test_a_genre_lowering_receives_the_compile_products():
    """The lowering's one view of compile state (an#348): what an earlier pass
    left in ``CompileState.products`` (a style's policy) reaches both the
    extent resolver and the expansion."""
    from typing import Literal

    from an.genres import ActionKind
    from an.ir.schema import ExtensionAction
    from an.stage.compile import _compile_actions

    class Nudge(ExtensionAction):
        kind: Literal["demo_nudge"] = "demo_nudge"
        target: str = "x"

    seen = []

    class Lowering:
        def extent_resolver(self, vocab, *, products):
            seen.append(("extent", dict(products)))
            return None

        def expand(self, flat_list, *, products, **kw):
            seen.append(("expand", dict(products)))
            return [f for f in flat_list if f.action.kind != "demo_nudge"]

        def view_of(self, entity_swaps, vocab, *, duration):
            return None

        clip = None

    kind = ActionKind("demo_nudge", Nudge, duration=lambda a, _e: 0.5, lowering=Lowering())
    products = {"demo.policy": {"locomotion": ["loco.glide"]}}
    with without_genres():
        register_genre(Genre("demo_products", action_kinds=(kind,)))
        _compile_actions([Nudge()], 1.0, products=products)
        _compile_actions([], 1.0)  # no products: an empty mapping, never None
    assert seen == [("extent", products), ("expand", products), ("extent", {}), ("expand", {})]
