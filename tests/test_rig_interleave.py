"""A nested chain interleaved with an unrelated part, and the engine capability (an#430).

A slot's subtree is painted together, so sorting one container's items (an#403)
cannot put an unrelated panel BETWEEN an upper arm and its forearm. The rig is
then painted from a global part order (``NodeJSON.paint_order``, Spine's slot
order): each part keeps its place in the transform tree. Whether an engine
can do that is the capability ``engine.paint_order`` (G16 of the genre
review): the stage declares ``container`` and ``global``; the compiler and
``an validate`` refuse, by name, a rig asking an engine for one it lacks.

The fixture is the core corpus's ``rig_interleave`` scene.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from an.ir.schema import AssetRef, Meta, SceneIR, Shot, StagePlacement
from an.stage.compile import CutoutCompileError, compile_shot
from an.stores.props import PropsStore

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "misc" / "bench" / "corpus"


def _mall(tmp_path, scene: str):
    shutil.copytree(CORPUS / scene / "assets" / "props", tmp_path / "props")
    return {"props": PropsStore(tmp_path / "props")}


def _shot(renderer: str = "cutout") -> Shot:
    return Shot(
        id="s1",
        renderer=renderer,
        duration=0.5,
        entities=[AssetRef(kind="prop", id="lamp", store="props", ref="arm_lamp", stage=StagePlacement(at=(0.0, 0.0)))],
    )


def _lamp(scene):
    (lamp,) = [n for n in scene.scene.children if n.name == "lamp"]
    return lamp


def test_an_interleaved_chain_is_painted_from_a_global_order(tmp_path):
    lamp = _lamp(compile_shot(_shot(), mall=_mall(tmp_path, "rig_interleave")))
    assert lamp.paint_order == ["base", "base/upper", "panel", "base/upper/fore", "base/upper/fore/shade"]


def test_a_chain_its_containers_can_order_carries_no_paint_list(tmp_path):
    """Byte identity: only a rig that needs it gets `paint_order`."""
    lamp = _lamp(compile_shot(_shot(), mall=_mall(tmp_path, "rig_chain")))
    assert lamp.paint_order is None
    from an.stage.serialize import to_dict

    assert "paint_order" not in to_dict(lamp)


def test_the_stage_declares_both_paint_orders():
    from an.capabilities import analyse
    from an.stage.render import CutoutRenderer

    profile, _ = analyse("engine", CutoutRenderer())
    assert profile["engine.paint_order"]["keys"] == ["container", "global"]


class _TreeOnlyRenderer:
    """A stage engine that paints parts in tree order only: no `paint_orders`
    (another engine registered for the stage's renderer name)."""

    name = "cutout"
    supported_renderers = ("cutout", "stage")

    def render(self, shot, ctx):  # pragma: no cover - never called
        raise AssertionError


@pytest.fixture()
def tree_only(monkeypatch):
    import an.adapters._base as base

    real = base.get_renderer
    monkeypatch.setattr(
        base, "get_renderer", lambda name: _TreeOnlyRenderer() if name == "cutout" else real(name)
    )


def test_an_engine_without_a_global_paint_order_is_refused_by_name(tmp_path, tree_only):
    with pytest.raises(CutoutCompileError, match=r"engine\.paint_order:global"):
        compile_shot(_shot(), mall=_mall(tmp_path, "rig_interleave"))


def test_an_engine_without_a_container_order_is_refused_for_a_sorted_chain(tmp_path, tree_only):
    """an#403's `z_index` asks for `container`; the compiler says so by name."""
    with pytest.raises(CutoutCompileError, match=r"engine\.paint_order:container"):
        compile_shot(_shot(), mall=_mall(tmp_path, "rig_order"))


def test_validate_agrees_with_compile(tmp_path, monkeypatch):
    from an.ir.validate import validate_semantic

    mall = _mall(tmp_path, "rig_interleave")
    scene = SceneIR(meta=Meta(), timeline=[_shot()])
    ok = validate_semantic(scene, available_props=mall["props"])
    assert not [f for f in ok.findings if "paint_order" in f.description]
    import an.adapters._base as base

    real = base.get_renderer
    monkeypatch.setattr(base, "get_renderer", lambda n: _TreeOnlyRenderer() if n == "cutout" else real(n))
    bad = validate_semantic(scene, available_props=mall["props"])
    assert any("engine.paint_order:global" in f.description and f.severity == "error" for f in bad.findings)
