"""Follow-ups of an#254's render report and trim (an#309): one writer of the
report's shape, no finding reported twice by ``orchestrate``, the trim's fixed
constants pinned to its version, the trim after a pitch/tempo chain without
ffmpeg, and paths made portable at component boundaries."""

from __future__ import annotations

import io
import json
import tempfile
import wave
from pathlib import Path

import pytest

from an.ir.schema import Dialogue
from an.project import load
from tests.test_render_findings import (  # noqa: F401 — the fixture, by name
    _LongTTS,
    _hi_shot,
    _project,
    fake_render,
)


# -----------------------------------------------------------------------------
# L2: one writer of the report's shape
# -----------------------------------------------------------------------------


def test_the_render_report_and_findings_record_are_one_shape(tmp_path, fake_render):
    from an.measurements import findings_record
    from an.render import render_findings, render_project
    from an.verify._base import Finding

    root = _project(tmp_path, _hi_shot(duration=1.0))
    render_project(root, tts=_LongTTS(1.6), incremental=False, echo_warnings=False)
    stored = json.loads(load(root).mall["render_reports"]["main"])["findings"]
    assert stored and all("kind" in r for r in stored)
    pairs = [(r["kind"], f) for r, f in zip(stored, render_findings(load(root).mall, "main"))]
    assert findings_record(pairs) == stored  # the writer IS findings_record
    one = Finding("info", "timeline/0", "note")
    assert findings_record([one], kind="measurement") == [
        {**findings_record([("measurement", one)])[0]}
    ]
    assert findings_record([one], kind="measurement")[0]["kind"] == "measurement"


# -----------------------------------------------------------------------------
# L3: orchestrate reports a finding once
# -----------------------------------------------------------------------------


def test_orchestrate_reports_a_finding_validate_and_the_render_both_have_once(
    tmp_path, fake_render, monkeypatch
):
    import an.orchestrate as orch

    root = _project(tmp_path, _hi_shot(duration=1.0))
    from an.render import render_project

    render_project(root, tts=_LongTTS(1.6), incremental=False, echo_warnings=False)
    report = orch.orchestrate(root, tts=_LongTTS(1.6), verifiers=[])
    found = [
        (f.ir_path, f.description)
        for f in [*report.validation.findings, *(f for v in report.verifications for f in v.findings)]
        if "cut off" in f.description
    ]
    assert len(found) == len(set(found)) == 1, found


# -----------------------------------------------------------------------------
# L4: what changes an effected line's bytes changes only with a keyed version
# -----------------------------------------------------------------------------

#: sha256 of ``trim_silence`` on the decaying-tone fixture, by TRIM_VERSION.
#: NEVER edit a row. A red here means a trimmed line's bytes changed (window,
#: threshold rule, record tag, rounding): bump TRIM_VERSION, which moves every
#: trimmed line's key, and ADD a row. Editing this one would serve the old
#: audio under the old keys — a stale cache nobody sees.
TRIM_GOLDEN = {1: "d959b357542d137b0b766bbb74c54eebee719859aeb6fc2722bec7b34077492e"}

#: sha256 of the ffmpeg chain's pure inputs (filters for a spread of effects,
#: the decode chain, the argv), by CHAIN_VERSION. Same rule: a red means bump
#: CHAIN_VERSION (keyed once it is not 1) and ADD a row. The ffmpeg BUILD is
#: not covered (TakeDigestWarning says so when it shows).
CHAIN_GOLDEN = {
    1: "acf40b7ecb5d4339a03e0ae1c272f349ee27488ee18a4e7999308bc049059d71",
    2: "87790fcc4b37f741b75bd2f5443df78d3cd6452f04947823a4df722dc13cc504",  # an#350: apad before atempo, output cut to input / tempo
}

_CHAIN_SAMPLES = (
    {"pitch_semitones": 3},
    {"tempo": 1.25},
    {"pitch_semitones": 12, "tempo": 0.5},
    {"pitch_semitones": -12, "tempo": 2},
    {"pitch_semitones": -2, "tempo": 1.1},
)


def _decaying_tone(rate: int = 11025) -> bytes:
    """A tone that rises and decays through every level between silence and
    full scale, at a rate whose windows do not land on round seconds: any
    change to where the trim cuts, or to how it rounds, moves its bytes."""
    import array
    import math

    n = rate * 2
    env = [min(1.0, 4 * i / n) * math.exp(-6 * max(0, i - n // 4) / n) for i in range(n)]
    samples = array.array("h", [0] * (rate // 3))
    samples.extend(int(20000 * e * math.sin(i / 3)) for i, e in enumerate(env))
    samples.extend([0] * (rate // 3))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def test_the_trims_bytes_change_only_with_its_version():
    import hashlib

    from an.audio import effects

    digest = hashlib.sha256(effects.trim_silence(_decaying_tone()).audio).hexdigest()
    assert digest == TRIM_GOLDEN[effects.TRIM_VERSION], (
        "a trimmed line's bytes changed: bump TRIM_VERSION and ADD a row to "
        "TRIM_GOLDEN (never edit one)"
    )


def test_the_chain_changes_only_with_its_version():
    import hashlib

    from an.audio import effects

    payload = json.dumps(
        {
            "chains": [
                effects.filter_chain(effects.normalize_effects(e)) for e in _CHAIN_SAMPLES
            ],
            "decode": effects.decode_chain(),
            "argv": effects.ffmpeg_argv("CHAIN", "OUT"),
        },
        sort_keys=True,
    )
    assert hashlib.sha256(payload.encode()).hexdigest() == CHAIN_GOLDEN[effects.CHAIN_VERSION], (
        "the effects chain changed: bump CHAIN_VERSION and ADD a row to "
        "CHAIN_GOLDEN (never edit one)"
    )


def test_a_chain_version_bump_moves_every_effected_key_and_no_other(monkeypatch):
    from an.audio import effects
    from an.audio.pipeline import audio_key

    before = {
        name: effects.normalize_effects(e)
        for name, e in (("tempo", {"tempo": 1.25}), ("trim", {"trim_silence": True}), ("none", {}))
    }
    monkeypatch.setattr(effects, "CHAIN_VERSION", effects.CHAIN_VERSION + 1)
    for name, raw in (("tempo", {"tempo": 1.25}), ("trim", {"trim_silence": True}), ("none", {})):
        after = effects.normalize_effects(raw)
        moved = audio_key("hi", "v", "offline", after) != audio_key("hi", "v", "offline", before[name])
        assert moved == (name != "none"), name


# -----------------------------------------------------------------------------
# L5: the trim runs after a pitch/tempo chain (no ffmpeg needed)
# -----------------------------------------------------------------------------


def _padded_tone(rate: int = 8000) -> bytes:
    import array
    import math

    tone = [int(9000 * math.sin(i / 3)) for i in range(rate // 2)]
    samples = array.array("h", [0] * rate + tone + [0] * rate)  # 1 s, 0.5 s, 1 s
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.mark.parametrize(
    "effect, filt", [({"tempo": 1.25}, "atempo"), ({"pitch_semitones": 3}, "asetrate")]
)
def test_the_trim_runs_after_a_pitch_or_tempo_chain(monkeypatch, effect, filt):
    from an.audio import effects

    source = b"ID3 an mp3 from a provider"
    chains = []

    def fake_chain(audio, chain, fx):  # ffmpeg, played by a padded tone
        assert audio == source  # the chain gets the provider's bytes
        chains.append(chain)
        return _padded_tone()

    monkeypatch.setattr(effects, "_ffmpeg_wav", fake_chain)
    fx = effects.normalize_effects({**effect, "trim_silence": True})
    out = effects.apply_voice_effects(source, fx)
    assert len(chains) == 1 and filt in chains[0]
    with wave.open(io.BytesIO(out)) as w:
        seconds = w.getnframes() / w.getframerate()
    assert seconds == pytest.approx(0.8, abs=0.01)  # 0.1 lead + 0.5 tone + 0.2 tail
    assert effects.trim_record(out) is not None


# -----------------------------------------------------------------------------
# Paths: component boundaries, temp folders
# -----------------------------------------------------------------------------


def test_a_path_sharing_a_prefix_with_the_root_or_home_is_left_whole():
    from an.render import portable_text

    text = "art at /u/me/proj2/a.png and /u/me2/x, inside /u/me/p/assets/b.png"
    assert portable_text(text, root="/u/me/p", home="/u/me") == (
        "art at ~/proj2/a.png and /u/me2/x, inside assets/b.png"
    )


def test_a_temp_path_is_redacted():
    from an.render import portable_text

    tmp = tempfile.gettempdir()
    out = portable_text(f"see {tmp}/an_work/frame.png", root="/u/me/p", home="/u/me")
    assert tmp not in out and "frame.png" in out and out.startswith("see <tmp>")


def test_a_render_keeps_an_older_projects_reports_out_of_git(tmp_path, fake_render):
    from an.render import render_project

    root = _project(tmp_path, _hi_shot(duration=3.0))
    (root / ".gitignore").write_text("output/\n", encoding="utf-8")  # a project from before an#254
    render_project(root, tts=_LongTTS(1.0), incremental=False, echo_warnings=False)
    assert (root / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "output/",
        "artifacts/render_reports/",
    ]


# -----------------------------------------------------------------------------
# The adversarial review's cases (an#309)
# -----------------------------------------------------------------------------


def _report_with(*findings, root=None):
    from an.ir.validate import ValidationReport
    from an.orchestrate import OrchestratorReport

    v = ValidationReport()
    for f in findings:
        v.add(*f)
    return OrchestratorReport(validation=v, root=root)


def test_the_same_path_and_words_at_another_severity_or_place_is_not_a_duplicate():
    from an.verify._base import VerificationReport

    report = _report_with(("warning", "timeline/0", "too long"))
    vr = VerificationReport()
    vr.add("error", "timeline/0", "too long")  # escalated by the render
    vr.add("warning", "timeline/0", "too long", location="a.py:14")  # elsewhere
    vr.add("warning", "timeline/0", "too long")  # the very same: dropped
    report.merge_verification(vr)
    kept = report.verifications[0]
    assert [(f.severity, f.location) for f in kept.findings] == [
        ("error", None), ("warning", "a.py:14"),
    ]  # fmt: skip
    assert not kept.passed and report.success is False


def test_a_finding_that_names_a_path_is_recognised_in_its_portable_form(tmp_path):
    from an.verify._base import VerificationReport

    report = _report_with(
        ("warning", "timeline/0", f"art missing at {tmp_path}/assets/a.png"), root=tmp_path
    )
    vr = VerificationReport()
    vr.add("warning", "timeline/0", "art missing at assets/a.png")  # as the report stores it
    report.merge_verification(vr)
    assert report.verifications[0].findings == []


def test_a_project_that_commits_its_reports_keeps_its_choice(tmp_path):
    from an.project import keep_reports_out_of_git

    chosen = "artifacts/*\r\n!artifacts/render_reports/\r\n"
    (tmp_path / ".gitignore").write_bytes(chosen.encode())
    keep_reports_out_of_git(tmp_path)
    assert (tmp_path / ".gitignore").read_bytes() == chosen.encode()


def test_the_gitignore_keeps_its_line_endings_and_is_never_made_outside_git(tmp_path):
    from an.project import keep_reports_out_of_git

    (tmp_path / "crlf").mkdir()
    (tmp_path / "crlf" / ".gitignore").write_bytes(b"output/\r\n")
    keep_reports_out_of_git(tmp_path / "crlf")
    assert (tmp_path / "crlf" / ".gitignore").read_bytes() == (
        b"output/\r\nartifacts/render_reports/\r\n"
    )
    (tmp_path / "loose").mkdir()
    keep_reports_out_of_git(tmp_path / "loose")  # not in a git work tree
    assert not (tmp_path / "loose" / ".gitignore").exists()
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    keep_reports_out_of_git(tmp_path / "repo")
    assert (tmp_path / "repo" / ".gitignore").read_text(encoding="utf-8") == "artifacts/render_reports/\n"


def test_a_symlinked_gitignore_is_never_written_through(tmp_path):
    import os

    from an.project import keep_reports_out_of_git

    shared = tmp_path / "shared.gitignore"
    shared.write_text("output/\n", encoding="utf-8")
    (tmp_path / "p").mkdir()
    os.symlink(shared, tmp_path / "p" / ".gitignore")
    keep_reports_out_of_git(tmp_path / "p")
    assert shared.read_text(encoding="utf-8") == "output/\n"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("/mnt/data/p/a.png", "/mnt/data/p/a.png"),  # ends like the root, is not it
        ("/backup/u/me/x", "/backup/u/me/x"),  # ends like home, is not it
        ("file:///data/p/a.png", "file://a.png"),  # a URL to a project file
        ("/data/p//a.png", "a.png"),
        ("see /tmp/x.png", "see <tmp>/x.png"),
        ("see /private/tmp/x.png", "see <tmp>/x.png"),
    ],
)
def test_paths_are_replaced_at_whole_components_at_both_ends(text, expected):
    from an.render import portable_text

    assert portable_text(text, root="/data/p", home="/u/me", tmp=None) == expected


def test_a_windows_path_is_found_whatever_its_separators_or_case():
    from an.render import portable_text

    out = portable_text(
        r"at c:\users\ME\p\a.png and C:/Users/me/x.log",
        root=r"C:\Users\me\p",
        home=r"C:\Users\me",
        tmp="/t",
    )
    assert out == r"at a.png and ~/x.log"
