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
RUNTIME_JS = REPO_ROOT / "an" / "stage" / "runtime" / "runtime.js"


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
    problems = check_vectors(vectors)
    # Both rules are held: the declared stage.node space AND the value-typed
    # default every stage caller uses (review S2).
    assert len(problems) == 2
    assert any("(declared)" in p for p in problems)
    assert any("(value-typed)" in p for p in problems)


def test_the_vectors_catch_the_an86_ratio_bug_on_the_default_path(monkeypatch):
    """Review S2's mutation, as a test: re-introduce the an#86 bug (snap on the
    ratio) in the value-typed rule only; the contract check must fail."""
    import an.timing.channel as channel

    real = channel.evaluate

    def ratio_snap(ch, t, *, kind=None):
        if kind is None and any(isinstance(k.value, str) for k in ch.keyframes):
            kfs = ch.keyframes
            times = [k.time for k in kfs]
            if times[0] <= t < times[-1]:
                import bisect

                i = bisect.bisect_right(times, t) - 1
                a, b = kfs[i], kfs[i + 1]
                if b.time > a.time:
                    return (
                        b.value if (t - a.time) / (b.time - a.time) >= 1.0 else a.value
                    )
        return real(ch, t, kind=kind)

    import an.timing.clip as clip

    monkeypatch.setattr(clip, "_evaluate_channel", ratio_snap)
    problems = check_vectors()
    assert problems and all("(value-typed)" in p for p in problems)
    assert any("an-86-boundary" in p for p in problems)


#: The committed case set. A case leaving the contract is a contract change and
#: must be made here too, deliberately (review S7).
EXPECTED_CASES: frozenset[str] = frozenset(
    {
        "number-linear-and-log",
        "angle",
        "vector-and-quaternion",
        "color",
        "color-srgb",
        "orbit",
        "discrete-and-undeclared",
        "timings",
        "cuts-dwells-carry-forward",
        "per-field-timing",
        "loop",
        "orbit-overshoot",
        "manim-rate-functions",
        "an-numeric-easings",
        "an-large-magnitude-bezier",
        "an-86-boundary",
        "an-swap-holds-under-any-easing",
        "an-swap-shapes",
        "an-held-end-value",
        "an-swap-write-group",
        "an-alias-write-group",
        "an-speed",
        "an-loop",
        "an-ping-pong",
        "an-step-swap-clip",
        "an-playing-beats-held",
        "an-latest-end-and-tie",
        "an-cross-track-inclusive-end",
    }
)


def test_the_vector_case_set_is_pinned():
    assert {c["name"] for c in _vectors()["cases"]} == EXPECTED_CASES


def test_drift_names_a_removed_case(tmp_path, monkeypatch):
    for name in CONTRACT_FILES:
        (tmp_path / name).write_text(
            (contract.CONTRACT_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    from an.timing import _vectors as seeds

    real = seeds.cases
    monkeypatch.setattr(
        seeds, "cases", lambda: [c for c in real() if c["name"] != "an-loop"]
    )
    assert f"{VECTORS_FILE}: cases removed: ['an-loop']" in contract_drift(tmp_path)


def test_a_genre_registration_never_reaches_the_core_contract():
    """Review S3: an installed genre registers kinds, spaces, easings, a solver
    and a family on import; an's contract files must not change."""
    from dataclasses import dataclass
    from typing import ClassVar

    from an.timing import easing, kinds, spaces
    from an.timing.easing import (
        EasingEntry,
        register_easing,
        register_family,
        register_solver,
    )
    from an.timing.kinds import FieldKind, register_kind
    from an.timing.spaces import FieldDecl, PropertySpace, register_space

    @dataclass(frozen=True)
    class Points(FieldKind):
        name: ClassVar[str] = "test-points"

    register_family("test-penner", owner="test-genre")
    register_solver("test-spring", "a spring integrator", owner="test-genre")
    register_easing(
        EasingEntry(
            "test-bounce",
            lambda u: u,
            family="test-penner",
            solver="test-spring",
            description="a test curve",
        ),
        owner="test-genre",
    )
    register_kind(Points.name, Points, owner="test-genre")
    register_space(
        PropertySpace("test.character", (FieldDecl("*", Points()),)), owner="test-genre"
    )
    try:
        assert contract_drift() == []
    finally:
        easing._REGISTRY.pop("test-bounce")
        easing._OWNERS.pop("test-bounce")
        easing._resolve_cached.cache_clear()
        easing._FAMILIES.pop("test-penner")
        easing.SOLVERS.pop("test-spring")
        easing._SOLVER_OWNERS.pop("test-spring")
        kinds._REGISTRY.pop(Points.name)
        kinds._OWNERS.pop(Points.name)
        spaces._REGISTRY.pop("test.character")
        spaces._OWNERS.pop("test.character")


def test_easing_json_does_not_publish_css_ease_under_the_name_ease():
    """Ruling 1 (ADR 0001 decision 10, amended): 'ease' is an's curve; the CSS
    curve is reachable only through the published import alias."""
    doc = load_contract_file("easing.json")
    assert "ease" not in doc["css_hyphenated_curves"]
    assert doc["css_import_aliases"] == {"ease": "cubic-bezier(0.25, 0.1, 0.25, 1)"}
    (entry,) = [e for e in doc["entries"] if e["name"] == "ease"]
    assert entry["family"] == "legacy"


def test_the_solver_fallbacks_are_sampled():
    """Review S6: the CSS bisection and the legacy slope guard are reached by a
    committed sample, so a port without them fails the contract."""
    doc = load_contract_file("easing.json")
    specs = [p["spec"] for p in doc["parametric"]]
    assert "cubic-bezier(1, 0, 0, 1)" in specs and [1.0, 0.0, 0.0, 1.0] in specs
    assert {1e-6, 0.501, 1 - 1e-6} <= set(doc["sample_u"])


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


def _runtime_kernel(src: str | None = None) -> str:
    """The runtime's evaluation code, lifted out of the shipped runtime.js: the
    legacy easings, the value-typed channel, and the declared-space block
    (an#287) that sits between ``RUNTIME_PROPERTIES`` and ``evaluateTimeline``."""
    src = RUNTIME_JS.read_text(encoding="utf-8") if src is None else src
    return "\n".join(
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
        ]
    )


def _run_kernel(body: str, *, src: str | None = None):
    proc = run_node(_runtime_kernel(src) + "\n" + body)
    assert proc.returncode == 0, f"node failed: {proc.stderr}"
    return json.loads(proc.stdout)


def _runtime_states(cases: list[dict], *, src: str | None = None) -> list[list[dict]]:
    """Each case's states as runtime.js evaluates its SELF-DESCRIBING document
    (:func:`an.engines.conformance.case_document`: a non-default space travels
    in ``meta.entity_spaces`` + ``meta.spaces``, as the compiler writes it)."""
    from an.engines.conformance import case_document

    docs = [
        {"doc": case_document(c), "times": [s["t"] for s in c["samples"]]}
        for c in cases
    ]
    return _run_kernel(
        "let scene = null;\n"
        f"const cases = {json.dumps(docs)};\n"
        "const out = cases.map(c => { scene = c.doc; return c.times.map(t => evaluateTimeline(t)); });\n"
        "console.log(JSON.stringify(out));",
        src=src,
    )


def _mismatches(cases: list[dict], got: list[list[dict]]) -> list[tuple]:
    out = []
    for case, rows in zip(cases, got):
        for sample, js in zip(case["samples"], rows):
            js_state = {k.replace("::", ":", 1): v for k, v in js.items()}
            if not values_close(sample["state"], js_state):
                out.append((case["name"], sample["t"], sample["state"], js_state))
    return out


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
    mismatches = _mismatches(cases, _runtime_states(cases))
    assert not mismatches, mismatches[:5]


def _declared_cases() -> list[dict]:
    return [c for c in _vectors()["cases"] if c["space"] != "stage.node"]


@requires_node
def test_the_stage_runtime_reproduces_every_vector_in_its_declared_space():
    """an#287: a document whose entity declares a space (``meta.entity_spaces``,
    defined in ``meta.spaces``) is evaluated by that space's field kinds and
    write groups -- log numbers, angles, vectors, quaternions, OKLab and sRGB
    colours, orbits, discrete switch points -- and the contract's easings. Every
    inline-space case, every sample."""
    cases = _declared_cases()
    assert len(cases) >= 10
    mismatches = _mismatches(cases, _runtime_states(cases))
    assert not mismatches, mismatches[:5]


@requires_node
def test_a_runtime_that_ignores_the_declared_spaces_fails_the_vectors():
    """The check can fail: the pre-an#287 runtime (every target by value type)
    disagrees with the declared-space cases."""
    src = RUNTIME_JS.read_text(encoding="utf-8")
    marker = "const spaceOf = documentSpaces(scene);"
    assert src.count(marker) == 1
    ignoring = src.replace(marker, "const spaceOf = null;")
    # Cases whose easings the value-typed rule also accepts (null), so the
    # failure is the interpolation, not a refused curve.
    names = {"color", "orbit", "loop"}
    cases = [c for c in _declared_cases() if c["name"] in names]
    failing = {m[0] for m in _mismatches(cases, _runtime_states(cases, src=ignoring))}
    assert failing == names


@requires_node
def test_the_runtime_kinds_reproduce_kinds_json():
    """Every sample interpolation of every core kind in ``kinds.json``."""
    doc = load_contract_file("kinds.json")
    rows = [
        {"spec": ex["spec"], **s}
        for kind in doc["kinds"]
        for ex in kind["examples"]
        for s in ex["samples"]
    ]
    got = _run_kernel(
        f"const rows = {json.dumps(rows)};\n"
        "console.log(JSON.stringify(rows.map(r => {\n"
        "  const k = makeKind(r.spec);\n"
        "  return 'segment' in r\n"
        "    ? k(r.a, r.b, 0.0, {t: r.t, start: r.segment[0], end: r.segment[1]})\n"
        "    : k(r.a, r.b, r.u, {t: r.u, start: 0.0, end: 1.0});\n"
        "})));"
    )
    bad = [(r, g) for r, g in zip(rows, got) if not values_close(r["value"], g)]
    assert not bad, bad[:5]
    assert {k["kind"] for k in doc["kinds"]} <= set(_runtime_field_kinds())


@requires_node
def test_the_runtime_easings_reproduce_easing_json():
    """Every named and parametrised curve in ``easing.json`` -- the legacy
    table, CSS (both solvers' fallbacks are sampled) and Manim -- at every
    sampled u, through the declared rule's ``applyContractEasing``."""
    doc = load_contract_file("easing.json")
    specs = [e["name"] for e in doc["entries"]] + [p["spec"] for p in doc["parametric"]]
    expected = [e["samples"] for e in doc["entries"]] + [
        p["samples"] for p in doc["parametric"]
    ]
    got = _run_kernel(
        f"const specs = {json.dumps(specs)}; const us = {json.dumps(doc['sample_u'])};\n"
        "console.log(JSON.stringify(specs.map(s => us.map(u => applyContractEasing(s, u)))));"
    )
    bad = [
        (spec, u, e, g)
        for spec, exp, row in zip(specs, expected, got)
        for u, e, g in zip(doc["sample_u"], exp, row)
        if not values_close(e, g)
    ]
    assert not bad, bad[:5]


def _runtime_field_kinds() -> list[str]:
    import re

    src = RUNTIME_JS.read_text(encoding="utf-8")
    table = _extract_js_block(src, "const FIELD_KINDS =")
    return re.findall(r"^        (\w+): ", table, flags=re.MULTILINE)


def test_the_compilers_runtime_kinds_are_the_runtimes():
    """``an.stage.compile.RUNTIME_FIELD_KINDS`` (what the compiler lets reach
    the browser) is exactly runtime.js's ``FIELD_KINDS`` table."""
    from an.stage.compile import RUNTIME_FIELD_KINDS

    assert set(_runtime_field_kinds()) == RUNTIME_FIELD_KINDS


def test_an_timing_reads_every_vector_back_from_its_self_describing_document():
    """The Python side of the same claim: ``timeline_from_compiled`` evaluates
    a case's document by the space it carries, with no space passed."""
    from an.engines.conformance import as_contract_state, case_document
    from an.timing.timeline import evaluate_timeline, timeline_from_compiled

    bad = []
    for case in _vectors()["cases"]:
        tl = timeline_from_compiled(case_document(case))
        for sample in case["samples"]:
            got = as_contract_state(evaluate_timeline(tl, sample["t"]))
            if not values_close(sample["state"], got):
                bad.append((case["name"], sample["t"]))
    assert not bad, bad[:5]


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
