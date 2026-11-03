"""``build_project_mall`` with ``ensure=False`` lays out nothing of an's own
(an#696): every file store reads a missing folder as empty and makes it on
its first write; ``ensure=True`` (``an init``) still lays out the tree."""

from __future__ import annotations

from pathlib import Path

from an.stores import build_project_mall

#: The stores lacing builds (``ArtifactStore.from_directory``), which still lay
#: out ``catalog/`` and ``blobs/`` until reeleehq/lacing#155.
_LACING_STORES = ("shot_cache", "transcripts")


def _made(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def test_a_mall_over_an_empty_folder_creates_nothing_and_reads_empty(tmp_path):
    mall = build_project_mall(tmp_path)
    lacing = {f"artifacts/{s}" for s in _LACING_STORES}
    leftover = {p for p in _made(tmp_path) if not any(p.startswith(x) for x in lacing)}
    assert leftover <= {"artifacts"}, leftover
    for name, store in mall.items():
        if name not in _LACING_STORES:
            assert list(store) == [], name


def test_the_first_write_makes_the_folder(tmp_path):
    mall = build_project_mall(tmp_path)
    mall["voices"]["jerry"] = {"provider": "offline"}
    mall["props"]["lamp"] = {"name": "lamp"}
    mall["shots"]["s1"] = b"film"
    mall["decisions"].append(kind="test", body={})
    assert {"assets/voices", "assets/props/lamp", "artifacts/shots", ".an"} <= _made(
        tmp_path
    )
    assert "assets/characters" not in _made(tmp_path)


def test_ensure_still_lays_out_the_tree(tmp_path):
    build_project_mall(tmp_path, ensure=True)
    assert {
        "assets/characters",
        "assets/voices",
        "artifacts/audio",
        "output",
        ".an",
    } <= _made(tmp_path)
