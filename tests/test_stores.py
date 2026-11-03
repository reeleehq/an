"""MutableMapping conformance + project mall sanity."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from an import build_project_mall
from an.ir.schema import Meta, SceneIR, Shot
from an.stores.characters import CharactersStore
from an.stores.decisions import DecisionLogStore
from an.stores.scenes import ScenesStore
from an.stores.voices import VoicesStore


def test_voices_store_basic_crud():
    with tempfile.TemporaryDirectory() as d:
        store = VoicesStore(d)
        assert len(store) == 0
        store["maya"] = {"provider": "elevenlabs", "voice_id": "abc"}
        assert "maya" in store
        assert store["maya"]["provider"] == "elevenlabs"
        assert list(store) == ["maya"]
        del store["maya"]
        assert "maya" not in store
        assert len(store) == 0


def test_characters_store_writes_meta_and_sidecar():
    with tempfile.TemporaryDirectory() as d:
        store = CharactersStore(d)
        store["maya"] = {"name": "Maya", "voice_ref": "maya-warm"}
        assert store["maya"]["name"] == "Maya"
        sidecar = store.sidecar_path("maya", "torso.svg")
        sidecar.write_text("<svg/>", encoding="utf-8")
        # Re-reading the meta shouldn't be disturbed by the sidecar.
        assert store["maya"]["voice_ref"] == "maya-warm"


def test_invalid_keys_rejected():
    with tempfile.TemporaryDirectory() as d:
        store = VoicesStore(d)
        with pytest.raises(KeyError):
            store["bad/key"] = {}
        with pytest.raises(KeyError):
            store[".hidden"] = {}
        with pytest.raises(KeyError):
            store[""] = {}


def test_scenes_store_round_trips_via_mall():
    with tempfile.TemporaryDirectory() as d:
        mall = build_project_mall(d, ensure=True)
        scene = SceneIR(
            meta=Meta(title="round", duration=3.0),
            timeline=[Shot(id="s1", duration=3.0)],
        )
        mall["scenes"]["main"] = scene
        reloaded = mall["scenes"]["main"]
        assert reloaded.meta.title == "round"
        assert reloaded.timeline[0].id == "s1"
        # Both md and json should exist.
        assert (Path(d) / "scene.md").exists()
        assert (Path(d) / "ir" / "scene.json").exists()


def test_scenes_store_only_supports_main_key():
    with tempfile.TemporaryDirectory() as d:
        mall = build_project_mall(d, ensure=True)
        with pytest.raises(KeyError):
            _ = mall["scenes"]["other"]
        with pytest.raises(KeyError):
            mall["scenes"]["other"] = SceneIR()


def test_decision_log_appends_in_order():
    with tempfile.TemporaryDirectory() as d:
        log = DecisionLogStore(Path(d) / "decisions.jsonl")
        log.append(kind="a", body=1)
        log.append(kind="b", body=2)
        log.append(kind="c", body=3)
        assert len(log) == 3
        entries = [log[k] for k in log]
        assert [e["body"] for e in entries] == [1, 2, 3]
        assert [e["kind"] for e in entries] == ["a", "b", "c"]


def test_decision_log_is_append_only():
    with tempfile.TemporaryDirectory() as d:
        log = DecisionLogStore(Path(d) / "decisions.jsonl")
        log.append(kind="a", body=1)
        with pytest.raises(TypeError):
            log["0"] = {"foo": "bar"}
        with pytest.raises(TypeError):
            del log["0"]


def test_mall_keys_match_spec():
    with tempfile.TemporaryDirectory() as d:
        mall = build_project_mall(d, ensure=True)
        assert sorted(mall.keys()) == [
            "audio",
            "captions",
            "characters",
            "contact_sheets",
            "decisions",
            "environments",
            "library_lock",
            "measurements",
            "output",
            "pictures",
            "previews",
            "props",
            "recordings",
            "render_reports",
            "scenes",
            "shot_cache",
            "shots",
            "sounds",
            "sources",
            "styles",
            "takes",
            "transcripts",
            "visemes",
            "voices",
        ]


def test_mall_overrides_swap_stores():
    with tempfile.TemporaryDirectory() as d:
        custom: dict = {}  # plain dict acts as a MutableMapping
        mall = build_project_mall(d, ensure=True, voices=custom)
        mall["voices"]["x"] = {"hello": "world"}
        assert custom["x"] == {"hello": "world"}


def test_scenes_store_is_a_scenes_store():
    """Sanity: the mall's scenes slot is the right type."""
    with tempfile.TemporaryDirectory() as d:
        mall = build_project_mall(d, ensure=True)
        assert isinstance(mall["scenes"], ScenesStore)


def test_a_blob_store_never_lists_a_killed_writes_temp_and_leaves_none(tmp_path):
    """An atomic write stages ``.<name>.<hex>.tmp``: a write leaves none behind,
    and one a killed process left is never a key, only an interrupted write
    (an#674)."""
    from an.stores.artifacts import ShotArtifactStore

    store = ShotArtifactStore(tmp_path)
    store["k"] = b"film"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["k.mp4"]
    planted = tmp_path / ".k.mp4.ab12cd34.tmp"
    planted.write_bytes(b"half a film")
    assert list(store) == ["k"] and len(store) == 1
    assert store.interrupted_writes() == [planted]
    assert VoicesStore(tmp_path / "v").interrupted_writes() == []


def test_a_write_killed_mid_way_leaves_a_temp_interrupted_writes_finds(tmp_path):
    """The temp a REAL killed ``dol.atomic_write`` leaves is what
    ``interrupted_writes`` lists, so a change to dol's temp naming fails here
    rather than silently stopping ``an cache gc`` collecting them (an#674)."""
    import subprocess
    import sys
    import time

    from an.stores.artifacts import ShotArtifactStore

    store = ShotArtifactStore(tmp_path)
    writer = (
        "import sys, time\n"
        "from dol import atomic_write\n"
        "def chunks():\n"
        "    yield b'half a film'\n"
        "    time.sleep(60)\n"
        "    yield b'never'\n"
        "atomic_write(sys.argv[1], chunks())\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", writer, str(store.path_of("k"))])
    try:
        deadline = time.monotonic() + 30
        while not store.interrupted_writes() and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        proc.kill()
        proc.wait()
    (temp,) = store.interrupted_writes()
    assert temp.name.startswith(".k.mp4.") and list(store) == []


@pytest.mark.parametrize("write", ["meta", "audio"])
def test_a_sidecar_write_killed_mid_way_keeps_the_previous_file(tmp_path, write):
    """``meta.json`` and ``audio.wav`` are written atomically: a process killed
    mid-write leaves the previous file whole and a temp that
    ``interrupted_writes`` lists for ``an cache gc`` (an#688)."""
    import subprocess
    import sys
    import time

    from an.stores._common import AudioSidecarStore

    store = AudioSidecarStore(tmp_path)
    store["x"] = {"v": 1}
    store.write_audio("x", b"RIFF old take")
    writer = (
        "import sys, time\n"
        "import an.stores._common as c\n"
        "real = c.atomic_write\n"
        "def slow(data):\n"
        "    yield data[:3]\n"
        "    time.sleep(60)\n"
        "    yield data[3:]\n"
        "c.atomic_write = lambda path, data, **kw: real(path, slow(data), **kw)\n"
        "store = c.AudioSidecarStore(sys.argv[1])\n"
        "if sys.argv[2] == 'meta':\n"
        "    store['x'] = {'v': 2, 'pad': 'y' * 1000}\n"
        "else:\n"
        "    store.write_audio('x', b'RIFF new take')\n"
    )
    import os

    import an

    # the child imports THIS checkout's an, not whichever one is installed
    env = {**os.environ, "PYTHONPATH": str(Path(an.__file__).parents[1])}
    proc = subprocess.Popen(
        [sys.executable, "-c", writer, str(tmp_path), write], env=env
    )
    try:
        deadline = time.monotonic() + 30
        while not store.interrupted_writes() and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        proc.kill()
        proc.wait()
    (temp,) = store.interrupted_writes()
    target = "meta.json" if write == "meta" else "audio.wav"
    assert temp.parent == tmp_path / "x" and temp.name.startswith(f".{target}.")
    assert store["x"] == {"v": 1} and store.read_audio("x") == b"RIFF old take"
    assert list(store) == ["x"]
