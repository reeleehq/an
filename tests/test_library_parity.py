"""The character analyser says what the compiler finds — over every corpus character.

ADR 0005's guard against facets that lie is ADR 0002's rule: the derivation is
what the compiler actually builds. This compiles each bench-corpus scene, reads
the limb pairs ``walk`` resolves from the built nodes (the compiler's own
``parts_of``), and asserts the analyser's ``limbs.legs`` / ``limbs.arms`` agree,
for SVG descriptors and procedural ``parts`` rigs alike — and that ``face.mouth``
and the turnaround keys of ``swap.view`` match the swap sets the built nodes
carry. A synthetic factory character (four views, nine mouths) joins the
corpus, which has no turnaround. Compile only: no browser, no ffmpeg.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from an.adapters.cutout.compile import compile_shot
from an.ir.sync import markdown_to_ir
from an.library import open_library, publish_dir
from an.motion import WALK_ARM_NAMES, WALK_LEG_NAMES, _limb_pair
from an.stores import build_project_mall

CORPUS = Path(__file__).resolve().parents[1] / "misc" / "bench" / "corpus"
PROJECTS = sorted(
    p for p in CORPUS.iterdir() if any((p / "assets" / "characters").glob("*/"))
)


def test_the_corpus_has_characters_to_compare():
    assert len(PROJECTS) >= 4


def _built(project: Path) -> dict[str, tuple[str, set[str], dict[str, set[str]]]]:
    """``{entity id: (store key, node paths under it, {swap set: keys})}`` as compiled."""
    mall = build_project_mall(project)
    scene = markdown_to_ir((project / "scene.md").read_text(encoding="utf-8"))
    out: dict[str, tuple[str, set[str], dict[str, set[str]]]] = {}
    for shot in scene.timeline:
        nodes: dict[str, object] = {}

        def walk(node, prefix):
            path = f"{prefix}/{node.name}" if prefix else node.name
            nodes[path] = node
            for child in node.children or []:
                walk(child, path)

        walk(compile_shot(shot, mall).scene, "")
        for e in shot.entities:
            if e.kind == "character":
                mine = {p: n for p, n in nodes.items() if f"/{e.id}/" in p}
                sets: dict[str, set[str]] = {}
                for n in mine.values():
                    for name, keys in (
                        (n.visual and n.visual.asset_sets) or {}
                    ).items():
                        sets.setdefault(name, set()).update(keys)
                parts = {p.split(f"/{e.id}/", 1)[1] for p in mine}
                out[e.id] = (e.ref, parts, sets)
    return out


@pytest.fixture(scope="module")
def factory_project(tmp_path_factory) -> Path:
    from an.characters.factory import new_character
    from an.project import init

    project = init(tmp_path_factory.mktemp("parity") / "proj")
    new_character(project / "assets" / "characters", name="alice", use_dicebear=False)
    (project / "scene.md").write_text(
        "# Parity\n\n## Shot s1 (cutout)\n\n```yaml shot\nduration: 1.0\n```\n\n"
        "```yaml entities\n- {id: alice, kind: character, store: characters, ref: alice}\n```\n",
        encoding="utf-8",
    )
    return project


def _assert_parity(project: Path) -> None:
    lib = open_library("an", records={}, versions={}, blobs={})
    built = _built(project)
    assert built, project
    for entity, (ref, parts, sets) in built.items():
        folder = project / "assets" / "characters" / ref
        afford = publish_dir(
            lib,
            folder,
            f"character.{ref.lower()}",
            source={"provider": "t", "license": "mit"},
        ).affordances
        for cap, names in (
            ("limbs.legs", WALK_LEG_NAMES),
            ("limbs.arms", WALK_ARM_NAMES),
        ):
            pair = _limb_pair(None, names, parts)
            derived = afford.get(cap, {}).get("slots")
            assert derived == (list(pair) if pair else None), (entity, cap)
        assert ("face.mouth" in afford) == ("viseme" in sets), (entity, "face.mouth")
        view = afford["swap.view"]
        turnable = set(view["keys"]) - (
            {view["rest"]} if not view["swappable"] else set()
        )
        assert (turnable if view["swappable"] else set()) == sets.get("view", set()), (
            entity,
            "swap.view",
        )


@pytest.mark.parametrize("project", PROJECTS, ids=[p.name for p in PROJECTS])
def test_affordances_match_what_the_compiler_builds(project):
    _assert_parity(project)


def test_a_turnaround_rig_matches_too(factory_project):
    _assert_parity(factory_project)
