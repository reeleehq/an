"""The open document model (an#241, ADR 0001 decisions 2-4, 9, 11).

The core's action union is open (core kinds + one ``ExtensionAction``), genres
register their kinds, entity kinds, checks and md sugar through one declarative
object, discovered explicitly through the ``an.genres`` entry point. These tests
hold the claims the issue's acceptance makes:

- a document with ``kind: play`` validates to ``PlayAction`` only after the
  cut-out genre is registered (the ADR's first-slice gate);
- an unregistered kind is an error that names the genre providing it — at
  validate, flatten, compile and ``scene.md`` read/write — never a crash or a
  silent drop, and the document round-trips untouched meanwhile;
- importing ``an`` registers no genre; ``an.genres.load()`` does, idempotently;
- persisted identifiers and the wire shape do not move: every committed
  ``scene.json`` round-trips, and the timing contract lists core entries only
  however many genres are loaded (review-237 S3);
- target values are validated generically against the entity kind's space, and
  the compiler refuses what the declared evaluator would (an#239 item 2).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

import an.genres as genres
from an.genres import (
    ActionKind,
    EntityKind,
    Genre,
    RegistryError,
    SemanticCheck,
    UnregisteredKindError,
    action_kind,
    register_genre,
    without_genres,
)
from an.genres.cutout import CUTOUT
from an.ir.compose import delay, duration_of, flatten, play, sequence, stagger, tween
from an.ir.schema import (
    AssetRef,
    ExpressionAction,
    ExtensionAction,
    PlayAction,
    SceneIR,
    Shot,
)

REPO = Path(__file__).resolve().parents[1]

PLAY_DOC = {
    "timeline": [
        {
            "id": "s1",
            "duration": 2.0,
            "entities": [
                {"kind": "character", "id": "c", "store": "characters", "ref": "c"}
            ],
            "actions": [{"kind": "play", "target": "c", "animation": "hop"}],
        }
    ]
}


def _declared_entry_point() -> EntryPoint:
    """The `an.genres` entry point `pyproject.toml` declares (read from the file,
    so the test does not depend on how current the installed metadata is)."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    section = text.split('[project.entry-points."an.genres"]', 1)[1]
    match = re.search(r'^(\w+)\s*=\s*"([^"]+)"', section, re.M)
    assert match, "pyproject.toml declares no an.genres entry point"
    return EntryPoint(match.group(1), match.group(2), genres.ENTRY_POINT_GROUP)


@pytest.fixture
def declared_entry_points(monkeypatch):
    """Discovery sees exactly the entry point this repository declares."""
    eps = (_declared_entry_point(),)
    monkeypatch.setattr(genres, "genre_entry_points", lambda **_: eps)
    return eps


# ----------------------------------------------------------------- the gate


def test_kind_play_validates_only_after_the_cut_out_genre_is_registered():
    """ADR 0001 §First slice: the same document, before and after registration."""
    with without_genres():
        before = SceneIR.model_validate(PLAY_DOC).timeline[0].actions[0]
        assert type(before) is ExtensionAction
        register_genre(CUTOUT)
        after = SceneIR.model_validate(PLAY_DOC).timeline[0].actions[0]
        assert type(after) is PlayAction
        # …and an action read BEFORE registration is validated by the
        # registered model on its way through flatten (late registration).
        assert type(flatten(before)[0].action) is PlayAction


def test_entry_point_load_registers_the_genre_and_is_idempotent(declared_entry_points):
    assert declared_entry_points[0].value == "an.genres.cutout:CUTOUT"
    assert declared_entry_points[0].name == "cutout_animation"
    with without_genres():
        assert action_kind("play") is None
        assert genres.load() == ("cutout_animation",)
        assert genres.load() == ("cutout_animation",)  # no-op the second time
        assert action_kind("play").model is PlayAction
        assert action_kind("expression").model is ExpressionAction
        assert genres.installed_genre("cutout_animation") is CUTOUT


def test_importing_an_registers_no_genre():
    """Decision 3: discovery is explicit. A fresh interpreter that imports the
    whole package (and the genre declaration itself) has registered nothing."""
    code = (
        "import an, an.genres, an.genres.cutout\n"
        "from an.genres.registry import action_kind_names, entity_kind_names, check_names\n"
        "print(an.genres.installed(), 'play' in action_kind_names(),"
        " 'character' in entity_kind_names(), any(n.startswith('cutout.') for n in check_names()))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=REPO
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "() False False False", out.stdout


# --------------------------------------------- unregistered: named, never lost


def test_an_unregistered_kind_round_trips_untouched():
    with without_genres():
        scene = SceneIR.model_validate(PLAY_DOC)
        dumped = json.loads(scene.model_dump_json())
    assert dumped["timeline"][0]["actions"] == [
        {"name": None, "kind": "play", "target": "c", "animation": "hop"}
    ]
    assert dumped["timeline"][0]["entities"][0]["kind"] == "character"


def test_flatten_refuses_an_unregistered_kind_naming_its_genre(declared_entry_points):
    with without_genres():
        action = SceneIR.model_validate(PLAY_DOC).timeline[0].actions[0]
        with pytest.raises(UnregisteredKindError) as err:
            flatten(sequence(delay(1.0), action))
        message = str(err.value)
        assert "'play' is not registered" in message
        assert "cutout_animation (an)" in message
        assert "an.genres.load()" in message
        with pytest.raises(UnregisteredKindError):
            duration_of(action)


def test_validate_reports_unregistered_kinds_and_keeps_going(declared_entry_points):
    """One error per unregistered kind, naming its genre — not a crash in a
    later check that flattens the shot."""
    from an.ir.validate import validate_semantic

    with without_genres():
        scene = SceneIR.model_validate(PLAY_DOC)
        report = validate_semantic(scene, available_characters={})
    errors = {
        f.ir_path: f.description for f in report.findings if f.severity == "error"
    }
    assert "action kind 'play' is not registered" in errors["timeline/0/actions/0"]
    assert "cutout_animation (an)" in errors["timeline/0/actions/0"]
    assert (
        "entity kind 'character' is not registered" in errors["timeline/0/entities/0"]
    )
    assert not report.passed


def test_validate_holds_a_registered_kind_to_its_own_model():
    """A `play` read before its genre loaded, and invalid for `PlayAction`, is
    reported field by field once the genre is registered."""
    from an.ir.validate import validate_semantic

    doc = json.loads(json.dumps(PLAY_DOC))
    doc["timeline"][0]["actions"] = [{"kind": "play", "target": "c"}]  # no animation
    with without_genres():
        scene = SceneIR.model_validate(doc)
        register_genre(CUTOUT)
        report = validate_semantic(scene)
    assert any(
        f.ir_path == "timeline/0/actions/0/animation"
        and "Field required" in f.description
        for f in report.findings
    ), report.findings


def test_validate_reports_an_unregistered_renderer():
    from an.ir.validate import validate_semantic

    report = validate_semantic(SceneIR(timeline=[Shot(id="s", renderer="vizan")]))
    assert [f.ir_path for f in report.findings if f.severity == "error"] == [
        "timeline/0/renderer"
    ]


def test_the_compiler_refuses_an_unregistered_kind_by_name():
    from an.adapters.cutout.compile import compile_shot

    with without_genres():
        shot = SceneIR.model_validate(PLAY_DOC).timeline[0]
        with pytest.raises(UnregisteredKindError, match="'play' is not registered"):
            compile_shot(shot)


def test_scene_md_refuses_genre_kinds_and_sugar_until_loaded(declared_entry_points):
    from an.ir.sync import SceneMarkdownError, ir_to_markdown, markdown_to_ir

    md = (
        "# T\n\n## Shot s1 (cutout)\n\n"
        "```yaml actions\n- kind: play\n  target: c\n  animation: hop\n```\n"
    )
    dialogue_md = "# T\n\n## Shot s1 (cutout)\n\n```dialogue\nc [happy]: Hi!\n```\n"
    with without_genres():
        with pytest.raises(SceneMarkdownError, match="cutout_animation") as err:
            markdown_to_ir(md)
        assert "must be one of set/tween; got 'play'" in str(err.value)
        with pytest.raises(SceneMarkdownError, match=r"\[happy\].*cutout_animation"):
            markdown_to_ir(dialogue_md)
        # Writing a scene whose emotion has no sugar to spell it REFUSES rather
        # than dropping it (the next md edit would drop it from the JSON).
        scene = SceneIR(
            timeline=[
                Shot(
                    id="s1",
                    dialogue=[{"speaker": "c", "text": "Hi!", "emotion": "happy"}],
                )
            ]
        )
        with pytest.raises(UnregisteredKindError, match="emotion"):
            ir_to_markdown(scene)
        unloaded = SceneIR.model_validate(PLAY_DOC)
        with pytest.raises(UnregisteredKindError):
            ir_to_markdown(unloaded)
    # Loaded (the session's state): both read, and write back.
    assert markdown_to_ir(dialogue_md).timeline[0].dialogue[0].emotion == "happy"
    scene = markdown_to_ir(md)
    assert type(scene.timeline[0].actions[0]) is PlayAction
    assert markdown_to_ir(ir_to_markdown(scene)) == scene


# ------------------------------------------------------------ registration


def test_a_genre_adds_a_kind_without_editing_the_core():
    """The whole point of the seam: a new genre's action kind flattens, reads and
    writes in scene.md, and validates, with no edit to compose, sync or validate."""
    from typing import Literal

    from an.ir.sync import ir_to_markdown, markdown_to_ir

    class WaveAction(ExtensionAction):
        kind: Literal["wave"] = "wave"
        target: str
        duration: float = 1.0

    wave = ActionKind(
        "wave",
        WaveAction,
        duration=lambda a, _extent: a.duration,
        read_md=lambda item, *, index: WaveAction(**item),
        write_md=lambda a: {"kind": "wave", "target": a.target, "duration": a.duration},
    )
    seen = []
    check = SemanticCheck(
        "vizan.saw_a_wave", lambda ctx: seen.append(ctx.index), order=55
    )
    flag = EntityKind("flag", space="stage.node", store="props")
    demo = Genre(
        "vizan_demo", action_kinds=(wave,), entity_kinds=(flag,), checks=(check,)
    )
    with without_genres():
        register_genre(demo)
        doc = {
            "timeline": [
                {
                    "id": "s",
                    "entities": [
                        {"kind": "flag", "id": "f", "store": "props", "ref": "f"}
                    ],
                    "actions": [
                        {"kind": "wave", "target": "f", "duration": 0.5},
                        {
                            "kind": "tween",
                            "target": "f",
                            "property": "x",
                            "to_value": 1.0,
                        },
                    ],
                }
            ]
        }
        scene = SceneIR.model_validate(doc)
        action = scene.timeline[0].actions[0]
        assert type(action) is WaveAction
        flat = flatten(sequence(action, tween("f", "x", to=1.0, duration=1.0)))
        assert [(f.start, f.end) for f in flat] == [(0.0, 0.5), (0.5, 1.5)]
        round_tripped = markdown_to_ir(ir_to_markdown(scene))
        assert type(round_tripped.timeline[0].actions[0]) is WaveAction
        from an.ir.validate import validate_semantic

        report = validate_semantic(scene)
        assert seen == [0]
        assert not [f for f in report.findings if "not registered" in f.description]
    assert action_kind("wave") is None  # gone with the genre


def test_registration_is_all_or_nothing_and_cannot_replace_core_kinds():
    from an.ir.schema import TweenAction

    class Bad(ExtensionAction):
        kind: str = "tween"

    clash = Genre("bad", action_kinds=(ActionKind("tween", TweenAction),))
    partial = Genre(
        "partial",
        entity_kinds=(EntityKind("gizmo"),),
        action_kinds=(ActionKind("nope", Bad),),  # model's kind default is wrong
    )
    with without_genres():
        with pytest.raises(RegistryError, match="already registered"):
            register_genre(clash)
        with pytest.raises(RegistryError):
            register_genre(partial)
        assert genres.entity_kind("gizmo") is None  # rolled back
        assert genres.installed() == ()


def test_the_cut_out_genre_is_one_plain_inspectable_object():
    assert CUTOUT.name == "cutout_animation"  # the persisted nw slug, unchanged
    provides = CUTOUT.provides()
    assert provides["action kinds"] == ("play", "expression")
    assert provides["entity kinds"] == ("character",)
    assert provides["dialogue sugar"] == ("emotion",)
    assert set(provides["checks"]) == {
        "cutout.play",
        "cutout.expression",
        "cutout.turns",
        "cutout.hidden_mouth_while_speaking",
        "cutout.view_continuity",
    }


def test_the_nw_genre_slug_is_the_genre_name():
    pytest.importorskip("nw")
    from an.genre import CUTOUT_ANIMATION_SLUG

    assert CUTOUT_ANIMATION_SLUG == CUTOUT.name


def test_the_contract_files_list_core_entries_only_with_genres_loaded():
    """Review-237 S3: a loaded genre (here the cut-out one, plus a genre that
    adds a space and a field kind) leaves `an`'s contract files unchanged."""
    from an.timing.contract import contract_drift
    from an.timing.kinds import DiscreteKind
    from an.timing.spaces import FieldDecl, PropertySpace

    extra = Genre(
        "drift_probe",
        spaces=(PropertySpace("drift_probe.thing", (FieldDecl("*", DiscreteKind()),)),),
        field_kinds=(("drift_probe_kind", lambda **kw: DiscreteKind(**kw)),),
    )
    with without_genres():
        register_genre(CUTOUT)
        register_genre(extra)
        assert contract_drift() == []


# ----------------------------------------------- spaces: generic targets


def test_validate_holds_target_values_to_the_entity_kinds_space():
    """Generic target validation (ADR 0001 decision 11): a string on a stage
    node's `x` is refused by `an validate` and by the compiler, which is the
    precondition of the declared-kinds default (an#239 item 2)."""
    from an.adapters.cutout.compile import CutoutCompileError, compile_shot
    from an.ir.validate import validate_semantic

    shot = Shot(
        id="s",
        duration=1.0,
        entities=[AssetRef(kind="prop", id="lamp", store="props", ref="lamp")],
        actions=[tween("lamp", "x", to="10", duration=1.0)],
    )
    report = validate_semantic(SceneIR(timeline=[shot]))
    assert any(
        f.ir_path == "timeline/0/actions/0"
        and "lamp:x is a number field of a prop (stage.node)" in f.description
        for f in report.findings
    ), report.findings
    character = Shot(
        id="s",
        duration=1.0,
        entities=[AssetRef(kind="character", id="c", store="characters", ref="c")],
        actions=[tween("c", "x", to="10", duration=1.0)],
    )
    with pytest.raises(CutoutCompileError, match="number field of a stage node"):
        compile_shot(character)


def test_the_default_evaluation_is_the_declared_space():
    from an.timing import spaces
    from an.timing.channel import Channel, Keyframe
    from an.timing.clip import Clip
    from an.timing.kinds import FieldKindError
    from an.timing.timeline import PlacedClip, Timeline, Track, evaluate_timeline

    tl = Timeline(
        1.0,
        [
            Track(
                "a",
                [
                    PlacedClip(
                        Clip(
                            "m",
                            1.0,
                            [
                                Channel(
                                    "a", "x", [Keyframe(0.0, "0"), Keyframe(1.0, "1")]
                                )
                            ],
                        ),
                        0.0,
                    )
                ],
            )
        ],
    )
    assert spaces.DFLT_TIMELINE_SPACE == "stage.node"
    # The value-typed rule snaps an ill-typed value; the declared default refuses it.
    assert evaluate_timeline(tl, 0.5, space=spaces.VALUE_TYPED)[("a", "x")] == "0"
    with pytest.raises(FieldKindError):
        evaluate_timeline(tl, 0.5)


# ---------------------------------------------------------------- stagger


def test_stagger_is_a_core_combinator_of_core_kinds():
    s = stagger(0.5, play("a", "hop", duration=1.0), play("b", "hop", duration=1.0))
    assert s.kind == "parallel"
    assert [(f.start, f.end) for f in flatten(sequence(delay(1.0), s))] == [
        (1.0, 2.0),
        (1.5, 2.5),
    ]
    assert duration_of(s) == 1.5


# ------------------------------------------------- persisted shapes unchanged


def _committed_scene_documents():
    out = subprocess.run(
        ["git", "ls-files", "*scene.json"], capture_output=True, text=True, cwd=REPO
    )
    paths = [REPO / p for p in out.stdout.split()] if out.returncode == 0 else []
    if not paths:
        paths = sorted(REPO.glob("**/ir/scene.json"))
    return [p for p in paths if p.exists()]


@pytest.mark.parametrize("unloaded", [False, True], ids=["genre-loaded", "core-only"])
def test_every_committed_scene_json_round_trips_with_or_without_the_genre(unloaded):
    """Decision 9: the open union changes no persisted shape. Every committed
    scene document dumps back to exactly what it migrates to (the version
    stamp is the migration's, nothing else moves) — typed under the genre, and
    through `ExtensionAction` without it."""
    from an.ir.migrate import migrate
    from an.ir.sync import scene_from_json_doc

    paths = _committed_scene_documents()
    assert paths
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        expected = migrate(json.loads(json.dumps(doc)), kind="SceneIR")
        if unloaded:
            with without_genres():
                scene = scene_from_json_doc(doc, source=path)
                dumped = json.loads(scene.model_dump_json())
        else:
            scene = scene_from_json_doc(doc, source=path)
            dumped = json.loads(scene.model_dump_json())
        assert dumped == expected, path
