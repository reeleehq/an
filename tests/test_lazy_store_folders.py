"""``build_project_mall`` lays out nothing of an's own (an#696): every file
store reads a missing folder as empty and makes it on its first write, never on
a read; ``ensure=True`` (``an init``) still lays out the tree."""

from __future__ import annotations

from pathlib import Path

from an.stores import build_project_mall


def _with_parents(paths) -> set[str]:
    """``paths`` and every folder above them, as relative posix paths."""
    return {
        "/".join(p.split("/")[: i + 1]) for p in paths for i in range(p.count("/") + 1)
    }


#: The folders lacing's two stores (``ArtifactStore.from_directory``) still make
#: on construction. When reeleehq/lacing#155 lands, the first test fails: delete
#: this and expect an empty folder.
_LACING_FOLDERS = _with_parents(
    f"artifacts/{store}/{sub}"
    for store in ("shot_cache", "transcripts")
    for sub in ("catalog", "blobs")
)

#: The tree ``an init`` laid out before an#696, by its hardcoded list, plus
#: lacing's folders: what ``ensure=True`` must still lay out, exactly.
_INIT_TREE_BEFORE_696 = (
    "assets/characters",
    "assets/environments",
    "assets/props",
    "assets/voices",
    "assets/styles",
    "assets/sounds",
    "assets/recordings",
    "assets/sources",
    "ir",
    "artifacts/audio",
    "artifacts/visemes",
    "artifacts/takes",
    "artifacts/shots",
    "artifacts/previews",
    "artifacts/contact_sheets",
    "artifacts/measurements",
    "artifacts/pictures",
    "artifacts/render_reports",
    "output",
    ".an",
)


def _made(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def test_a_mall_over_an_empty_folder_creates_nothing_and_reads_empty(tmp_path):
    mall = build_project_mall(tmp_path)
    assert _made(tmp_path) == _LACING_FOLDERS  # lacing#155: then, nothing at all
    for name, store in mall.items():
        assert list(store) == [], name
        assert len(store) == 0, name
    for name in ("props", "voices", "audio", "characters"):
        assert mall[name].interrupted_writes() == [], name
    assert _made(tmp_path) == _LACING_FOLDERS


def test_reads_through_a_missing_key_create_nothing(tmp_path):
    from an.build.gc import collect_garbage
    from an.credits import _digests_of, collect_credits
    from an.library.checkout import _entry_dir

    mall = build_project_mall(tmp_path)
    before = _made(tmp_path)
    assert "ghost" not in mall["props"]
    assert mall["props"].sidecar_path("ghost", "parts/arm.svg").name == "arm.svg"
    assert _digests_of(mall["props"], "ghost")() is None  # the is_dir guard is live
    assert _entry_dir(mall["characters"], "ghost") is not None
    collect_credits(mall, only={"props/ghost", "characters/ghost"})
    assert _made(tmp_path) == before
    (tmp_path / "scene.md").write_text("# Title\n", encoding="utf-8")
    collect_garbage(tmp_path, dry_run=True, force=True)  # `an cache gc --dry-run`
    assert _made(tmp_path) == before | {"scene.md"}


def test_the_first_write_makes_the_folder(tmp_path):
    mall = build_project_mall(tmp_path)
    mall["voices"]["jerry"] = {"provider": "offline"}
    mall["props"]["lamp"] = {"name": "lamp"}
    mall["shots"]["s1"] = b"film"
    mall["decisions"].append(kind="test", body={})
    mall["sounds"].write_audio("boom", b"RIFF....")
    with mall["styles"].locked("noir"):
        pass
    assert {
        "assets/voices",
        "assets/props/lamp",
        "assets/sounds/boom",
        "assets/styles",
        "artifacts/shots",
        ".an",
    } <= _made(tmp_path)
    assert "assets/characters" not in _made(tmp_path)


def test_ensure_lays_out_the_same_tree_as_before(tmp_path):
    build_project_mall(tmp_path, ensure=True)
    assert _made(tmp_path) == _with_parents(_INIT_TREE_BEFORE_696) | _LACING_FOLDERS


def test_an_init_lays_out_the_same_folders_as_before(tmp_path):
    from an.project import init

    pdir = init(tmp_path / "p")
    folders = {p.relative_to(pdir).as_posix() for p in pdir.rglob("*") if p.is_dir()}
    assert folders == _with_parents(_INIT_TREE_BEFORE_696) | _LACING_FOLDERS
