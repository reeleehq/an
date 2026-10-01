"""The timing kernel's cross-language contract (an#233; ADR 0001 decision 10).

Four claims, each checked here rather than asserted in a doc:

1. the five committed contract files are what the registries generate today
   (a drift test: regenerating is a deliberate act);
2. ``an.timing`` reproduces every golden vector;
3. ``runtime.js`` — a time-driven engine — reproduces every ``stage.node``
   vector too (the conformance check the core study §2.7 asks of such engines);
4. what the stage actually compiles validates against the schemas: every corpus
   shot's compiled document against ``compiled.schema.json``, its flattened
   actions against ``timeline.schema.json``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import jsonschema
import pytest

from tests._node import requires_node, run_node
from tests.test_cutout_channel_parity import _extract_js_block

from an.base import EASING_PRESETS
from an.timing import contract
from an.timing.contract import (
    COMPILED_SCHEMA_FILE,
    CONTRACT_FILES,
    TIMELINE_SCHEMA_FILE,
    VECTORS_FILE,
    check_vectors,
    contract_drift,
    load_contract_file,
    values_close,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_JS = REPO_ROOT / "an" / "data" / "cutout_runtime" / "runtime.js"


def _validator(name: str) -> jsonschema.Draft202012Validator:
    schema = load_contract_file(name)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def _vectors() -> dict:
    return load_contract_file(VECTORS_FILE)


def _case(name: str) -> dict:
    return next(c for c in _vectors()["cases"] if c["name"] == name)


def _state(case: dict, t: float) -> dict:
    return next(s["state"] for s in case["samples"] if s["t"] == t)


# ------------------------------------------------------------ 1. no drift


def test_every_contract_file_is_committed_and_parses():
    for name in CONTRACT_FILES:
        assert isinstance(load_contract_file(name), dict), name


def test_the_committed_contract_is_what_the_registries_generate():
    """A change to a curve, a kind, a schema or the kernel's evaluation moves a
    committed number. Regenerate with ``python -m an.timing.contract write`` —
    deliberately, saying in the PR which samples moved and why."""
    assert contract_drift() == []


def test_the_drift_check_notices_a_moved_sample(tmp_path):
    """The drift guard, mutation-tested: a committed sample nudged past the
    tolerance must be reported."""
    for name in CONTRACT_FILES:
        (tmp_path / name).write_text(
            (contract.CONTRACT_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    easing = json.loads((tmp_path / "easing.json").read_text(encoding="utf-8"))
    easing["entries"][0]["samples"][3] += 1e-6
    (tmp_path / "easing.json").write_text(contract.dumps(easing), encoding="utf-8")
    assert contract_drift(tmp_path) == [
        "easing.json: differs from what the registries generate"
    ]


# ------------------------------------------------------- 2. an.timing meets them


def test_an_timing_reproduces_every_golden_vector():
    assert check_vectors() == []


def test_a_wrong_vector_is_reported():
    vectors = _vectors()
    case = next(c for c in vectors["cases"] if c["name"] == "an-86-boundary")
    sample = next(s for s in case["samples"] if s["state"].get("hand:hands") == "A")
    sample["state"]["hand:hands"] = "B"
    assert len(check_vectors(vectors)) == 1


def test_the_an86_boundary_holds_the_first_key_until_the_second_key_time():
    """Asserted absolutely, not only by agreement: (t - a) / span rounds to 1.0
    at the float below b, and the swap must still show 'A' there."""
    from an.timing._vectors import BOUNDARY_A, BOUNDARY_B

    below = math.nextafter(BOUNDARY_B, 0.0)
    assert (below - BOUNDARY_A) / (BOUNDARY_B - BOUNDARY_A) == 1.0
    case = _case("an-86-boundary")
    assert _state(case, below) == {"hand:hands": "A"}
    assert _state(case, BOUNDARY_B) == {"hand:hands": "B"}


def test_cross_track_ties_go_to_the_later_track_whether_it_starts_or_ends_there():
    case = _case("an-cross-track-inclusive-end")
    assert _state(case, 1.0)["a:x"] == 20.0  # the later track's clip STARTS at 1.0
    assert _state(case, 3.0)["b:x"] == 10.0  # the later track's clip ENDS at 3.0
    assert _state(case, math.nextafter(3.0, 4.0))["b:x"] == pytest.approx(20.0)


def test_every_case_samples_its_boundaries_and_their_midpoints():
    from an.timing._vectors import _clip_boundaries

    for case in _vectors()["cases"]:
        times = {s["t"] for s in case["samples"]}
        bounds = sorted(
            {
                0.0,
                case["document"]["timeline"]["duration"],
                *_clip_boundaries(case["document"]),
            }
        )
        assert set(bounds) <= times, case["name"]
        assert {(a + b) / 2 for a, b in zip(bounds, bounds[1:])} <= times, case["name"]


def test_values_close_is_the_stated_tolerance():
    assert values_close(1.0, 1.0 + 0.9e-9)
    assert not values_close(1.0, 1.0 + 1.1e-9)
    assert values_close(1e9, 1e9 + 0.9)  # relative above 1
    assert not values_close({"a": 1}, {"a": 1, "b": 2})  # keys exactly
    assert not values_close([1.0], [1.0, 2.0])  # lengths exactly
    assert not values_close(False, 0)  # a bool is not a number


# ---------------------------------------- 3. runtime.js meets the stage vectors


def _runtime_states(cases: list[dict]) -> list[list[dict]]:
    src = RUNTIME_JS.read_text(encoding="utf-8")
    script = "\n".join(
        [
            _extract_js_block(src, "const EASINGS ="),
            _extract_js_block(src, "function cubicBezier"),
            _extract_js_block(src, "function applyEasing"),
            _extract_js_block(src, "function evaluateChannel"),
            _extract_js_block(src, "function wrapTime"),
            src[
                src.index("const RUNTIME_PROPERTIES") : src.index(
                    "// Port of `an/adapters/cutout/timeline.py::evaluate_timeline`"
                )
            ],
            _extract_js_block(src, "function evaluateTimeline"),
            "let scene = null;",
            f"const cases = {json.dumps([{'doc': c['document'], 'times': [s['t'] for s in c['samples']]} for c in cases])};",
            "const out = cases.map(c => { scene = c.doc; return c.times.map(t => evaluateTimeline(t)); });",
            "console.log(JSON.stringify(out));",
        ]
    )
    proc = run_node(script)
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    return json.loads(proc.stdout)


def _stage_cases() -> list[dict]:
    return [c for c in _vectors()["cases"] if c["space"] == "stage.node"]


def test_stage_cases_use_only_easings_the_stage_runtime_implements():
    for case in _stage_cases():
        for anim in case["document"]["animations"].values():
            for ch in anim["channels"]:
                for k in ch["keyframes"]:
                    e = k.get("easing")
                    assert e is None or isinstance(e, list) or e in EASING_PRESETS, (
                        case["name"],
                        e,
                    )


@requires_node
def test_the_stage_runtime_reproduces_every_stage_vector():
    """runtime.js interpolates by VALUE TYPE; the vectors were computed under the
    DECLARED stage.node space. Agreement on every sample is the claim that the
    declarations reproduce the runtime exactly, checked from the runtime's side."""
    cases = _stage_cases()
    assert len(cases) >= 10
    got = _runtime_states(cases)
    mismatches = []
    for case, rows in zip(cases, got):
        for sample, js in zip(case["samples"], rows):
            js_state = {k.replace("::", ":", 1): v for k, v in js.items()}
            if not values_close(sample["state"], js_state):
                mismatches.append(
                    (case["name"], sample["t"], sample["state"], js_state)
                )
    assert not mismatches, mismatches[:5]


# ----------------------------------------------- 4. what the stage emits fits


def test_every_vector_document_validates_against_the_compiled_schema():
    validator = _validator(COMPILED_SCHEMA_FILE)
    for case in _vectors()["cases"]:
        errors = [e.message for e in validator.iter_errors(case["document"])]
        assert not errors, (case["name"], errors[:3])


def test_every_corpus_shot_compiles_to_a_document_the_schema_accepts(tmp_path):
    """The compiled schema is hand-written in the kernel; the stage serializer is
    separate code. A field added to either without the other fails here."""
    from tests.test_pure_pose import _corpus_shots

    from an.adapters.cutout.serialize import to_dict

    validator = _validator(COMPILED_SCHEMA_FILE)
    seen = 0
    for name, shot, _, _, doc in _corpus_shots()(tmp_path):
        errors = [
            f"{list(e.path)}: {e.message}" for e in validator.iter_errors(to_dict(doc))
        ]
        assert not errors, (name, shot.id, errors[:3])
        seen += 1
    assert seen


def test_the_compiled_schema_names_exactly_the_stage_serializer_fields():
    from an.adapters.cutout import serialize as S

    defs = load_contract_file(COMPILED_SCHEMA_FILE)["$defs"]
    pairs = {
        "timeline": S.TimelineJSON,
        "track": S.TrackJSON,
        "placed_clip": S.PlacedClipJSON,
        "animation": S.AnimationClipJSON,
        "channel": S.ChannelJSON,
        "keyframe": S.KeyframeJSON,
    }
    for name, model in pairs.items():
        assert set(defs[name]["properties"]) == set(model.model_fields), name


def test_every_corpus_scene_flattens_to_a_timeline_the_schema_accepts(tmp_path):
    from tests.test_pure_pose import _corpus_shots

    from an.ir.compose import flatten
    from an.timing.flat import flat_timeline_doc

    validator = _validator(TIMELINE_SCHEMA_FILE)
    rows = 0
    for name, shot, _, _, _ in _corpus_shots()(tmp_path):
        flat = [f for action in shot.actions for f in flatten(action)]
        doc = flat_timeline_doc(flat, duration=shot.duration, skip_other=True)
        errors = [e.message for e in validator.iter_errors(doc)]
        assert not errors, (name, shot.id, errors[:3])
        rows += len(doc["actions"])
    assert rows


def test_the_schema_address_pattern_is_the_parser():
    import re

    from an.timing.address import AddressError, parse_address

    pattern = re.compile(contract.ADDRESS_PATTERN)
    texts = [
        "charlie:x",
        "charlie/left_arm:rotation",
        "m:viseme@happy",
        "view:light.color",
        "a/b/c:d.e.f@g",
        "root:pivot_x",
        "e.1:x",
        "a/b.c:x",
        "charlie:",
        ":x",
        "a::b",
        "a/:x",
        "a:x@",
        "a:x@b@c",
        "a:.x",
        "a:x.",
        "a:x..y",
        " a:x",
        "a :x",
        "a:x ",
        "a/b c:x",
        "a:@b",
        "a/ /b:x",
        "a:b/c",
    ]
    for text in texts:
        try:
            parse_address(text)
            parsed = True
        except AddressError:
            parsed = False
        assert parsed == bool(pattern.match(text)), text
