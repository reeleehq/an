"""The scene tree's paths: ``NodeJSON.scope`` and the one Python statement of the runtime's rule (an#343, D2 of an#331).

- ``scope`` is omit-when-unset (``is None``; ``""`` is a value), so no document
  that does not use it changes;
- ``runtime.js``'s ``childPrefix`` agrees with :func:`an.stage.tree.child_prefix`,
  run under node on the function lifted verbatim from the runtime;
- every hand-rolled children walk that joined names by hand is gone from the
  stage, ``an.motion`` and the bench, and a lint refuses a new one;
- an environment's foreground container indexes its planes as ``<env>/<plane>``,
  ``plane_parents`` says so, and ``<env>__front/<plane>`` is rewritten at compile
  and at validate with a warning, never indexed twice.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from an.adapters.cutout.compile import CutoutCompileWarning, compile_shot
from an.adapters.cutout.serialize import to_dict
from an.ir.compose import tween
from an.ir.schema import AssetRef, Meta, Resolution, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.stage import tree
from an.stage.serialize import NodeJSON
from tests._node import requires_node, run_node

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "an" / "stage" / "runtime" / "runtime.js"

_DOC = {
    "scene": {
        "name": "root",
        "children": [
            {"name": "set", "children": [{"name": "sky"}, {"name": "hill", "children": [{"name": "tree"}]}]},
            {"name": "maya", "children": [{"name": "head"}]},
            {"name": "set__front", "scope": "set", "children": [{"name": "rail"}]},
            {"name": "set__after_0", "scope": "", "children": [{"name": "disc", "children": [{"name": "rim"}]}]},
            {"name": "a", "children": [{"name": "b", "scope": "c", "children": [{"name": "d"}]}]},
        ],
    },
    "overlay": {"name": "overlay", "children": [{"name": "title", "children": [{"name": "word_0"}]}]},
}  # fmt: skip


def test_scope_is_omitted_when_unset_and_kept_when_empty():
    assert "scope" not in NodeJSON(name="a").model_dump()
    assert NodeJSON(name="a", scope="").model_dump()["scope"] == ""
    assert NodeJSON(name="a", scope="set").model_dump()["scope"] == "set"


def test_the_python_rule_indexes_scoped_children_where_the_runtime_does():
    assert [p for p, _ in tree.walk_document(_DOC)] == [
        "set", "set/sky", "set/hill", "set/hill/tree",
        "maya", "maya/head",
        "set__front", "set/rail",
        "set__after_0", "disc", "disc/rim",
        "a", "a/b", "a/c/d",
        "title", "title/word_0",
    ]  # fmt: skip
    # A scoped container composes like any parent: it is in the chain.
    assert [p for _, p in tree.chain(_DOC["scene"], "set/rail")] == ["root", "set__front", "set/rail"]
    with pytest.raises(KeyError, match="set__front/rail"):
        tree.chain(_DOC["scene"], "set__front/rail")


def _lift(src: str, signature: str) -> str:
    start = src.index(signature)
    return src[start : src.index("\n    }", start) + len("\n    }")]


@requires_node
def test_the_runtime_child_prefix_agrees_with_the_python_one():
    """`childPrefix` lifted VERBATIM from runtime.js, walked the way
    `buildSceneTree` walks (its two path lines are asserted below), against
    `an.stage.tree` on one document holding every case."""
    src = RUNTIME.read_text(encoding="utf-8")
    build = _lift(src, "function buildSceneTree(")
    # buildSceneTree's own path rule, which the walk below reproduces.
    assert "const path = pathPrefix ? pathPrefix + '/' + node.name : node.name;" in build
    assert "const inner = childPrefix(node, path, pathPrefix);" in build
    assert "buildSceneTree(child, container, inner);" in build
    script = f"""
    {_lift(src, "function childPrefix(")}
    const out = [];
    function index(node, pathPrefix) {{
        const path = pathPrefix ? pathPrefix + '/' + node.name : node.name;
        out.push(path);
        const inner = childPrefix(node, path, pathPrefix);
        for (const child of node.children || []) index(child, inner);
    }}
    const doc = {json.dumps(_DOC)};
    for (const layer of ['scene', 'overlay']) for (const c of doc[layer].children) index(c, '');
    console.log(JSON.stringify(out));
    """
    proc = run_node(script)
    assert proc.returncode == 0, proc.stderr
    js = json.loads(proc.stdout.strip().splitlines()[-1])
    assert js == [p for p, _ in tree.walk_document(_DOC)]


# --- no hand-rolled walk ----------------------------------------------------------

#: Where the runtime's path rule must come from `an.stage.tree` (an#343).
_LINTED = ("an/stage", "an/motion.py", "an/bench")


def _joins_a_name(node: ast.AST) -> bool:
    """An f-string ``"…/{x.name}"`` (or ``{x['name']}``/``{x.get('name')}``)."""
    if not isinstance(node, ast.JoinedStr):
        return False
    parts = node.values
    for before, value in zip(parts, parts[1:]):
        if not (isinstance(before, ast.Constant) and str(before.value).endswith("/")):
            continue
        if not isinstance(value, ast.FormattedValue):
            continue
        v = value.value
        if isinstance(v, ast.Attribute) and v.attr == "name":
            return True
        if isinstance(v, ast.Subscript) and getattr(v.slice, "value", None) == "name":
            return True
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Attribute)
            and v.func.attr == "get"
            and v.args
            and getattr(v.args[0], "value", None) == "name"
        ):
            return True
    return False


def _walks_children(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute) and n.attr == "children":
            return True
        if isinstance(n, ast.Constant) and n.value == "children":
            return True
    return False


def hand_rolled_walks(source: str) -> list[str]:
    """Functions that walk ``children`` and join node names into paths by hand."""
    found = []
    for fn in ast.walk(ast.parse(source)):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _walks_children(fn) and any(_joins_a_name(n) for n in ast.walk(fn)):
                found.append(fn.name)
    return found


def test_the_lint_catches_a_hand_rolled_walk():
    """The negative test: the detector the sweep below relies on fires."""
    rolled = (
        "def walk(node, prefix):\n"
        "    path = f'{prefix}/{node.name}' if prefix else node.name\n"
        "    for c in node.children:\n"
        "        walk(c, path)\n"
    )
    assert hand_rolled_walks(rolled) == ["walk"]
    assert hand_rolled_walks("def f(node):\n    return [c.name for c in node.children]\n") == []


def test_no_module_walks_the_scene_tree_by_hand():
    offenders = []
    for where in _LINTED:
        base = ROOT / where
        files = [base] if base.is_file() else sorted(base.rglob("*.py"))
        for f in files:
            if f.name == "tree.py" and f.parent.name == "stage":
                continue
            for fn in hand_rolled_walks(f.read_text(encoding="utf-8")):
                offenders.append(f"{f.relative_to(ROOT)}::{fn}")
    assert not offenders, (
        f"{offenders} join node names into paths by hand; use an.stage.tree "
        "(`walk`, `walk_document`, `lineage`, `chain`), which honours `scope`"
    )


# --- the foreground container -------------------------------------------------------

W, H = 320, 240


def _env(**kw) -> dict:
    def plane(name, color):
        return {"name": name, "art": {"kind": "fill", "color": color}, "size": [100.0, 20.0]}

    return {
        "kind": "EnvironmentDescriptor",
        "name": "s",
        "planes": [plane("sky", "#102030"), plane("hill", "#204030"), plane("rail", "#803020")],
        "characters_after": "hill",
        **kw,
    }


def _shot(actions=()) -> Shot:
    return Shot(
        id="s",
        renderer="stage",
        duration=1.0,
        entities=[AssetRef(kind="environment", id="set", store="environments", ref="e")],
        actions=list(actions),
    )


def test_a_foreground_plane_is_addressed_under_the_environment():
    doc = compile_shot(
        _shot([tween("set/rail", "y", 30.0, 1.0, from_=0.0)]),
        {"environments": {"e": _env()}},
        width=W,
        height=H,
    )
    d = to_dict(doc)
    names = [c["name"] for c in d["scene"]["children"]]
    assert names == ["set", "set__front"]
    assert d["scene"]["children"][1]["scope"] == "set"
    assert "scope" not in d["scene"]["children"][0]
    assert {"set/sky", "set/hill", "set/rail"} <= tree.paths(doc.scene)
    targets = {ch.target for a in doc.animations.values() for ch in a.channels}
    assert "set/rail" in targets


def test_the_old_spelling_is_rewritten_with_a_warning_at_compile_and_validate():
    shot = _shot([tween("set__front/rail", "y", 30.0, 1.0, from_=0.0)])
    mall = {"environments": {"e": _env()}}
    with pytest.warns(CutoutCompileWarning, match="set/rail"):
        doc = compile_shot(shot, mall, width=W, height=H)
    targets = {ch.target for a in doc.animations.values() for ch in a.channels}
    assert "set/rail" in targets and "set__front/rail" not in targets
    scene = SceneIR(meta=Meta(duration=1.0, resolution=Resolution(width=W, height=H)), timeline=[shot])
    report = validate_semantic(scene, available_environments=mall["environments"])
    errors = [f.description for f in report.findings if f.severity == "error"]
    warned = [f.description for f in report.findings if f.severity == "warning"]
    assert errors == [], errors
    assert any("retired spelling" in w and "'set/rail'" in w for w in warned), warned


def test_the_rewrite_reaches_a_loop_and_spares_an_entity_named_like_a_container():
    """Review of an#343: a target inside a `loop` (its `child`, not `children`)
    is rewritten too, and an entity whose id really is `<env>__front` keeps it."""
    from an.ir.compose import iter_actions, loop
    from an.stage.compile import retire_front_spelling

    looped = _shot([loop(tween("set__front/rail", "y", 30.0, 0.5, from_=0.0), 2)])
    new, pairs = retire_front_spelling(looped)
    assert pairs == [("set__front/rail", "set/rail")]
    assert [a.target for a in iter_actions(new.actions[0]) if a.kind == "tween"] == ["set/rail"]
    with pytest.warns(CutoutCompileWarning, match="set/rail"):
        compile_shot(looped, {"environments": {"e": _env()}}, width=W, height=H)

    named = Shot(
        id="s",
        renderer="stage",
        duration=1.0,
        entities=[
            AssetRef(kind="environment", id="set", store="environments", ref="e"),
            AssetRef(kind="prop", id="set__front", store="props", ref="t"),
        ],
        actions=[tween("set__front/word_0", "alpha", 0.0, 0.5, from_=1.0)],
    )
    assert retire_front_spelling(named) == (named, [])
