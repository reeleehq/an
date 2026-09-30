"""The name-the-emotion judge (an#98): parser, seam, frozen frames, cassette.

The eight presets are already proven pairwise distinguishable by decoded pixels
(`tests/test_expression_goldens.py`). This is the other half: does a VISION
MODEL, shown one frozen face at a time, name the emotion the preset intends?
The seam is `an.verify.vision.judge_emotion` (parsing outside the recording,
like the legibility judge); the frames are `tests/_emotion_frames.py`; the
replay node skips loudly until the cassette is recorded once:

    AN_LIVE_API_TESTS=1 pytest -q -m live_api -k record_the_emotion_cassette
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from an.verify.vision import (
    _parse_emotion,
    emotion_prompt,
    judge_emotion,
    judge_key,
)

from .conftest import requires_live_api
from ._emotion_frames import EMOTION_LABELS, load_frames

ROOT = Path(__file__).resolve().parents[1]
#: Correct names required out of eight, on the recording. A design value:
#: chance is 1/8, and `thinking`/`skeptical`/`neutral` are the plausible
#: confusions (the two asymmetric presets are one pixel-distance apart). Lower
#: it only with the recorded confusion matrix in the commit message.
MIN_CORRECT: int = 5


# ------------------------------------------------------------ parser and prompt


def test_the_parser_accepts_fenced_json_and_case_and_rejects_invented_labels():
    labels = EMOTION_LABELS
    assert _parse_emotion('{"emotion": "angry"}', labels) == "angry"
    assert _parse_emotion('```json\n{"emotion": " Sad "}\n```', labels) == "sad"
    assert _parse_emotion('{"emotion": "grumpy"}', labels) is None, "not in the set is not a verdict"
    assert _parse_emotion('{"emotion": 3}', labels) is None
    assert _parse_emotion('["angry"]', labels) is None
    assert _parse_emotion("", labels) is None


def test_the_prompt_offers_exactly_the_label_set_and_the_labels_are_the_key():
    prompt = emotion_prompt(EMOTION_LABELS)
    assert all(label in prompt for label in EMOTION_LABELS)
    a = judge_key([b"x"], prompt=emotion_prompt(["a", "b"]), model="m", max_tokens=1)
    b = judge_key([b"x"], prompt=emotion_prompt(["a", "c"]), model="m", max_tokens=1)
    assert a != b


def test_judge_emotion_goes_through_the_injected_seam():
    seen = {}

    def fake(frames, *, prompt, model, max_tokens, api_key=None):
        seen.update(frames=frames, prompt=prompt)
        return '{"emotion": "afraid"}'

    assert judge_emotion([b"png"], labels=EMOTION_LABELS, judge=fake) == "afraid"
    assert seen["prompt"] == emotion_prompt(EMOTION_LABELS) and seen["frames"] == [b"png"]
    assert judge_emotion([b"png"], labels=["happy"], judge=lambda *a, **k: '{"emotion": "afraid"}') is None


def test_the_default_label_set_is_every_preset():
    from an.expression import known_presets

    seen = {}

    def fake(frames, *, prompt, **kw):
        seen["prompt"] = prompt
        return ""

    judge_emotion([b"x"], judge=fake)
    assert all(name in seen["prompt"] for name in known_presets())


# ------------------------------------------------------------ the frozen frames


def test_the_eight_faces_are_frozen_and_pairwise_distinct():
    frames = load_frames()
    assert tuple(frames) == EMOTION_LABELS, "python tests/_emotion_frames.py"
    assert len(set(frames.values())) == len(EMOTION_LABELS)
    keys = {judge_key([png], prompt=emotion_prompt(EMOTION_LABELS)) for png in frames.values()}
    assert len(keys) == len(EMOTION_LABELS), "eight faces, eight recordings"


# ------------------------------------------------------------ replay and record


def test_the_judge_names_the_intended_emotion_replay_only():
    """On the committed cassette; a miss is `CassetteMiss`, never a call. Skips
    (loudly) until it is recorded once."""
    from tests._vision_cassettes import CASSETTE_DIR, memoized_judge

    frames = load_frames()
    prompt = emotion_prompt(EMOTION_LABELS)
    for label, png in frames.items():
        key = judge_key([png], prompt=prompt)
        if not (CASSETTE_DIR / f"{key}.json").is_file():
            pytest.skip(f"no cassette for the {label} face — record once: AN_LIVE_API_TESTS=1 pytest -q -m live_api -k record_the_emotion_cassette")
    judge = memoized_judge(replay_only=True)
    named = {label: judge_emotion([png], labels=EMOTION_LABELS, judge=judge) for label, png in frames.items()}
    assert None not in named.values(), f"a reply named no label: {named}"
    correct = sum(named[label] == label for label in EMOTION_LABELS)
    assert correct >= MIN_CORRECT, f"{correct}/8 named correctly (intended -> named): {named}"


@pytest.mark.live_api
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@requires_live_api  # innermost: pytest reports the first skip it meets, and the opt-in is the one to name
def test_record_the_emotion_cassette():
    """Spends once (~$0.005 x 8) and replays on a hit. Gated on the explicit
    positive opt-in — the marker alone opts out of the network guard."""
    from tests._vision_cassettes import memoized_judge

    frames = load_frames()
    assert len(frames) == len(EMOTION_LABELS), "freeze first: python tests/_emotion_frames.py"
    judge = memoized_judge(replay_only=False)
    for label, png in frames.items():
        assert judge_emotion([png], labels=EMOTION_LABELS, judge=judge) is not None, label


def test_the_recording_test_skips_without_the_opt_in():
    """Observed through pytest itself with the opt-in and `CI` stripped: a bare
    `pytest` must skip the spending test (the marker alone skips nothing)."""
    env = {k: v for k, v in os.environ.items() if k not in ("AN_LIVE_API_TESTS", "CI")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs", "--no-header",
         "tests/test_emotion_judge.py::test_record_the_emotion_cassette"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 skipped" in proc.stdout and "AN_LIVE_API_TESTS" in proc.stdout, proc.stdout
