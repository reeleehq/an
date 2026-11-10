"""Sounds on the frame of their event: a sound's sync point, and cues timed by hold events.

The user, 2026-11-10: "the foley sounds when Stu changes the rifle are not in
sync with the image. There's a delay. The sound happens too late." Two causes,
two fixes: the clips hit 0.31 s and 0.78 s after their first sample (a sound's
``sync`` point, :func:`an.sounds.set_sync`, and the ``an validate`` warning when
it is undeclared), and the cue times were typed by hand (a cue timed by the
hold event it is the sound of: ``at: {when: sabre, event: place}``).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pytest

from tests._hold_fixture import make_project, scene

from an.ir.schema import CueAnchor
from an.ir.validate import validate_semantic
from an.sound_anchors import SoundAnchorError, event_in_document
from an.sounds import (
    SYNTH_SOURCE,
    _wav_bytes,
    add_sound,
    get_sound,
    measure_sync,
    set_sync,
    synth_hit,
    wav_samples,
)
from an.stage.compile import compile_shot

RATE = 44100


def _late_hit(lead_s: float) -> bytes:
    """A clip whose hit comes ``lead_s`` after a quiet scrape."""
    hit, _ = wav_samples(synth_hit(0.2, seed=3))
    scrape = 0.01 * np.sin(np.linspace(0.0, 900.0, int(lead_s * RATE)))
    return _wav_bytes(np.concatenate([scrape, hit]), sample_rate=RATE)


def test_measure_sync_finds_the_hit_after_a_lead_in():
    assert measure_sync(_late_hit(0.78)) == pytest.approx(0.78, abs=0.011)
    assert measure_sync(synth_hit(0.2)) == pytest.approx(0.0, abs=0.011)


def test_set_sync_records_the_point_and_leaves_the_bytes(tmp_path):
    from an.stores.sounds import SoundsStore

    store = SoundsStore(tmp_path)
    audio = _late_hit(0.5)
    add_sound(store, "clink", audio, source=SYNTH_SOURCE)
    assert set_sync(store, "clink").sync == pytest.approx(0.5, abs=0.011)
    asset, data = get_sound(store, "clink")
    assert data == audio and asset.sync == pytest.approx(0.5, abs=0.011)
    assert set_sync(store, "clink", None).sync is None
    with pytest.raises(ValueError, match="outside"):
        set_sync(store, "clink", 9.0)


def test_a_synced_cue_starts_its_file_early_so_the_hit_lands_on_at(tmp_path):
    from an.assemble import _cue_placement
    from an.ir.schema import SoundCue

    cue = SoundCue(sound="clink", at=3.0)
    p = _cue_placement(
        cue, at=3.0, container_end=9.0, path=tmp_path / "c.wav", asset_duration=1.5, sync=0.78
    )
    assert p.at == pytest.approx(2.22) and p.skip == 0.0
    loop = SoundCue(sound="bed", at=3.0, loop=True)
    p = _cue_placement(
        loop, at=3.0, container_end=9.0, path=tmp_path / "b.wav", asset_duration=1.5, sync=0.78
    )
    assert p.at == 3.0  # a bed is placed by its first sample


def _project(tmp_path: Path, sounds: str):
    actions = (
        "- {kind: grasp, by: fig/arm_r, item: stick, start: 0.5}\n"
        "- {kind: release, item: stick, at: 2.0}"
    )
    shot = "duration: 4.0\nsolve: {ground: 200}\nsounds:\n" + sounds
    project = make_project(tmp_path / "p", scene(actions, shot=shot))
    add_sound(project.mall["sounds"], "thud", _late_hit(0.4), source=SYNTH_SOURCE)
    return project


def _compile(project):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return compile_shot(project.scene.timeline[0], project.mall, fps=24, width=640, height=480)


def _lint(project, only):
    report = validate_semantic(
        project.scene,
        available_props=project.mall["props"],
        available_sounds=project.mall["sounds"],
        only=set(only),
    )
    return [(f.severity, f.description) for f in report.findings]


def test_a_cue_timed_by_a_hold_event_resolves_to_that_event(tmp_path):
    project = _project(tmp_path, "- {sound: thud, at: {when: stick, event: land}}\n")
    doc = _compile(project)
    events = doc.meta.extensions["solve"]["holds"]["events"]
    land = next(e["at"] for e in events if e["event"] == "land")
    grasp = next(e["at"] for e in events if e["event"] == "grasp")
    anchor = project.scene.timeline[0].sounds[0].at
    assert event_in_document(doc, anchor, shot_id="s", where="w") == pytest.approx(land)
    contact = CueAnchor(when="stick", event="contact")
    assert event_in_document(doc, contact, shot_id="s", where="w") == pytest.approx(grasp)
    with pytest.raises(SoundAnchorError, match="the events of .stick."):
        event_in_document(
            doc, CueAnchor(when="stick", event="place"), shot_id="s", where="w"
        )


def test_validate_names_a_cued_event_the_shot_does_not_have(tmp_path):
    project = _project(tmp_path, "- {sound: thud, at: {when: stick, event: land, nth: 2}}\n")
    findings = _lint(project, {"cue_event"})
    assert any(sev == "error" and "does not happen" in d for sev, d in findings), findings
    project = _project(tmp_path / "ok", "- {sound: thud, at: {when: stick, event: land}}\n")
    findings = _lint(project, {"cue_event"})
    assert [sev for sev, _ in findings] == ["info"], findings


def test_validate_warns_when_a_cued_hit_is_late_in_its_file(tmp_path):
    project = _project(tmp_path, "- {sound: thud, at: 2.4}\n")
    findings = [d for sev, d in _lint(project, {"assembly"}) if "sync point" in d]
    assert findings and "0.40 s into its file" in findings[0], findings
    set_sync(project.mall["sounds"], "thud")
    assert not [d for _sev, d in _lint(project, {"assembly"}) if "sync point" in d]
