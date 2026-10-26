"""``meta.duration`` 0.0 means "unset" and stays unset (an#557)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from an.ir.schema import Dialogue, Meta, SceneIR, Shot, Transition
from an.ir.sync import ir_to_markdown, sync
from an.stores.scenes import ScenesStore


def _dissolved_scene() -> SceneIR:
    return SceneIR(
        meta=Meta(title="T", fps=24),
        timeline=[
            Shot(id="a", duration=2.0),
            Shot(
                id="b",
                duration=2.0,
                transition=Transition(kind="dissolve", duration=0.6),
            ),
        ],
    )


@pytest.mark.parametrize("derived", [3.4166666666666665, 4.0])
def test_a_stored_derived_duration_never_reaches_the_authors_file(tmp_path, derived):
    """A project stored before an#557: scene.md writes no `duration:`, but
    ir/scene.json holds the length the old reader derived (the layout, an#481,
    or the plain sum before it). A no-op store write leaves scene.md as it was."""
    scene = _dissolved_scene()
    md = ir_to_markdown(scene)
    assert "duration: 3.4" not in md and "\nduration:" not in md.split("## Shot")[0]
    (tmp_path / "scene.md").write_text(md, encoding="utf-8")
    (tmp_path / "ir").mkdir()
    doc = json.loads(scene.model_dump_json())
    doc["meta"]["duration"] = derived
    json_path = tmp_path / "ir" / "scene.json"
    json_path.write_text(json.dumps(doc), encoding="utf-8")
    now = os.stat(tmp_path / "scene.md").st_mtime
    os.utime(json_path, (now, now))  # the store's own equalization

    store = ScenesStore(tmp_path)
    read = store["main"]
    assert read.meta.duration == 0.0
    store["main"] = read
    assert (tmp_path / "scene.md").read_text(encoding="utf-8") == md
    # ... and the pair agrees, so sync has nothing to settle.
    assert not sync(tmp_path).wrote_md


def test_a_store_set_duration_is_written_and_read_back(tmp_path):
    store = ScenesStore(tmp_path)
    scene = _dissolved_scene()
    store["main"] = scene
    scene.meta.duration = 3.4
    store["main"] = scene
    assert "duration: 3.4" in (tmp_path / "scene.md").read_text(encoding="utf-8")
    assert store["main"].meta.duration == 3.4


def test_an_unset_duration_stays_unset_when_a_shot_takes_its_audios_length():
    """`settle_durations` lengthens a clock-owned shot to its dialogue's real
    audio; an unset `meta.duration` is not filled in on the way."""
    from an.assemble import film_duration
    from an.measurements import settle_durations

    class _OwnsItsClock:
        def measure_duration(self, shot, ctx, *, render, force):
            return None  # never measured: judged against its dialogue

    registry = SimpleNamespace(find_for=lambda shot: _OwnsItsClock())
    line = Dialogue(speaker="n", text="a long line", start=0.0, duration=3.0)
    scene = SceneIR(
        meta=Meta(fps=24), timeline=[Shot(id="a", duration=1.0, dialogue=[line])]
    )
    settled, _ = settle_durations(
        scene, SimpleNamespace(fps=24), render=False, registry=registry
    )
    assert settled.timeline[0].duration == pytest.approx(3.0)
    assert settled.meta.duration == 0.0
    assert film_duration(settled) == pytest.approx(3.0)
