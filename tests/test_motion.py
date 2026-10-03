"""Motion presets (`an.motion`): the core's authoring macros, without a rig.

What is pinned here, and why:

- presets chain without a jump (each segment names its ``from``);
- nonsense parameters raise rather than expand to a broken move;
- ``as_leaves`` keeps a ``set`` at its absolute time, and a composition tree
  survives ``scene.md`` verbatim;
- the rig presets' old names here are live aliases of ``cutan.motion`` (an#322).

Every preset compiled on a cut-out rig — the core's and the genre's, on the
procedural and a descriptor rig, landing at frame times, rendered — is pinned
in ``cutan``'s ``tests/test_motion_presets.py``, which moved there with the rig
presets.
"""

from __future__ import annotations

import warnings

import pytest

from an.ir.compose import delay, flatten, sequence, set_
from an.ir.schema import Meta, SceneIR, SetAction, Shot, TweenAction
from an.ir.sync import ir_to_markdown, markdown_to_ir
from an.motion import PRESETS, as_leaves, hop, shake, slide_in, squash_stretch


def _shot(actions) -> Shot:
    return Shot(id="s", duration=3.0, entities=[], actions=list(actions))


def test_the_core_presets_need_no_rig():
    assert set(PRESETS) == {
        "pop_in", "hop", "shake", "slide_in", "slide_out", "squash_stretch", "crawl",
    }


def test_presets_chain_without_a_jump():
    """Each segment names its `from`, equal to the previous segment's `to`."""
    leaves = flatten(sequence(hop("c"), squash_stretch("c"), shake("c", cycles=2)))
    last: dict[tuple[str, str], float] = {}
    tweens = [f for f in leaves if isinstance(f.action, TweenAction)]
    for f in sorted(tweens, key=lambda f: f.start):
        key = (f.action.target, f.action.property)
        if key in last:
            assert f.action.from_value == pytest.approx(last[key]), key
        last[key] = f.action.to_value


@pytest.mark.parametrize("bad", [lambda: shake("c", cycles=0), lambda: slide_in("c", from_side="up"),
                                 lambda: shake("c", duration=-1.0), lambda: hop("c", duration=0.0)])
def test_nonsense_parameters_raise(bad):
    with pytest.raises(ValueError):
        bad()


def test_as_leaves_keeps_a_set_at_its_absolute_time():
    leaves = as_leaves(sequence(delay(1.0), set_("charlie", "alpha", 0.5, at=0.25)), start=0.5)
    (leaf,) = leaves
    assert isinstance(leaf, SetAction) and leaf.at == pytest.approx(1.75)
    scene = SceneIR(meta=Meta(title="t"), timeline=[_shot(leaves)])
    (back,) = markdown_to_ir(ir_to_markdown(scene)).timeline[0].actions
    assert back.at == pytest.approx(1.75)


def test_a_composition_tree_survives_scene_md_verbatim():
    """It used not to (the writer dropped composites, and `as_leaves` was the
    workaround). Since an#241's review round the writer keeps an action it has
    no short form for VERBATIM, so a preset's tree round-trips as is;
    `as_leaves` still gives the short, hand-editable form."""
    scene = SceneIR(meta=Meta(title="t"), timeline=[_shot([hop("charlie")])])
    back = markdown_to_ir(ir_to_markdown(scene)).timeline[0]
    assert back.actions == scene.timeline[0].actions


@pytest.mark.genre("cutout_animation")
def test_a_rig_preset_s_old_name_is_a_live_alias_of_the_genre_s():
    import an.motion
    import cutan.motion
    from an._shims import MovedModuleWarning

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        assert an.motion.walk is cutan.motion.walk
        assert an.motion.WALK_LEG_NAMES is cutan.motion.WALK_LEG_NAMES
    assert seen and all(w.category is MovedModuleWarning for w in seen)
    assert "walk" not in PRESETS and "walk" in cutan.motion.PRESETS
