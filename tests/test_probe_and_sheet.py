"""``an probe`` and ``an library sheet`` (an#347): one frame through the real frame path.

- a probe frame IS the film's frame: the same session and capture loop as
  ``render``, pixel for pixel;
- a sheet draws one specimen per library version (or its art files), each
  captioned with its licence class, and a placeholder for a kind with none;
- both refuse to write not-publishable material where git would pick it up,
  and ``an init`` ignores their default folder.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from an.bench.png import decode_png, encode_png
from an.library import open_library, publish, publish_dir, sheet
from an.library.root import PrivateOutputError, check_private_output
from an.media.grid import tile, trim
from an.probe import ProbeError, frame, frames, probe
from an.project import PROJECT_GITIGNORE, init, load

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "misc" / "bench" / "corpus"
CC0 = {"provider": "an-tests", "license": "cc0-1.0"}
PRIVATE = {"provider": "a-film", "license": "all-rights-reserved-private-study"}


@pytest.fixture(autouse=True)
def _temp_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AN_HOME", str(tmp_path / "roots" / "an"))
    monkeypatch.setenv("CUTAN_HOME", str(tmp_path / "roots" / "cutan"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def _fixture(tmp_path: Path, name: str) -> Path:
    return Path(shutil.copytree(CORPUS / name, tmp_path / name))


# --------------------------------------------------------------------------- pure


def test_tile_and_trim():
    red = encode_png(np.full((10, 20, 3), (255, 0, 0), np.uint8))
    sheet_png = decode_png(tile([red] * 5, cell=32, columns=3, labels=list("abcde")))
    assert sheet_png.shape[1] == 4 + 3 * 36 and sheet_png.shape[0] > 2 * 36
    with pytest.raises(ValueError):
        tile([red], labels=["a", "b"])
    blank = encode_png(np.full((8, 8, 3), 255, np.uint8))
    assert trim(blank) == blank


def test_an_init_ignores_the_probe_folder(tmp_path):
    root = init(tmp_path / "p")
    lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "artifacts/probes/" in lines and list(PROJECT_GITIGNORE) == [
        "artifacts/render_reports/",
        "artifacts/probes/",
    ]


def test_not_publishable_output_is_refused_where_git_would_pick_it_up(tmp_path):
    repo = _git_repo(tmp_path / "repo")
    target = repo / "look.png"
    with pytest.raises(PrivateOutputError, match="allow-private-here"):
        check_private_output(target, publishable=False, what="a frame")
    check_private_output(target, publishable=True, what="a frame")
    check_private_output(target, publishable=False, what="a frame", allow=True)
    (repo / ".gitignore").write_text("*.png\n", encoding="utf-8")
    check_private_output(target, publishable=False, what="a frame")
    # A symlinked folder pointing into the work tree is followed.
    (tmp_path / "out").symlink_to(repo / "sub", target_is_directory=True)
    (repo / "sub").mkdir()
    (repo / ".gitignore").write_text("", encoding="utf-8")
    with pytest.raises(PrivateOutputError):
        check_private_output(tmp_path / "out" / "x.png", publishable=False, what="x")


def test_a_probe_refuses_what_it_cannot_draw(tmp_path):
    root = _fixture(tmp_path, "text_card")
    with pytest.raises(ProbeError, match="no shot"):
        frames(root, "nope", [0.1])
    with pytest.raises(ProbeError, match="outside"):
        frames(root, "card", [9.0])
    with pytest.raises(ProbeError, match="at least one"):
        frames(root, "card", [])


# --------------------------------------------------------------------------- browser


@pytest.mark.browser
@pytest.mark.ffmpeg
def test_a_probe_frame_is_the_films_frame(tmp_path):
    from an.render import render

    root = _fixture(tmp_path, "text_card")
    probed = decode_png(frame(root, "card", 0.3))
    render(load(root), incremental=False, auto_audio=False, echo_warnings=False)
    film = root / ".an" / "render_work" / "shot_card" / "frames" / "frame_000007.png"
    assert np.array_equal(probed, decode_png(film.read_bytes()))  # floor(0.3 * 24) = 7


@pytest.mark.browser
def test_probe_writes_a_grid_into_the_ignored_default_folder(tmp_path):
    root = _fixture(tmp_path, "text_card")
    out = probe(root, "card", [0.1, 0.4])
    assert out.parent == root / "artifacts" / "probes"
    assert decode_png(out.read_bytes()).shape[0] > 0


@pytest.mark.browser
def test_a_probe_of_private_material_is_refused_in_a_repo_but_not_in_its_ignored_folder(
    tmp_path,
):
    repo = _git_repo(tmp_path / "repo")
    root = _fixture(repo, "prop_swap")
    desc = root / "assets" / "props" / "lamp" / "prop.json"
    import json

    doc = json.loads(desc.read_text(encoding="utf-8"))
    doc["source"] = PRIVATE
    desc.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(PrivateOutputError):
        probe(root, "lamp", [0.1], out=root / "look.png")
    # The default folder: ignored (added to this older project's .gitignore).
    assert probe(root, "lamp", [0.1]).is_file()


@pytest.mark.browser
def test_a_sheet_draws_a_specimen_per_version_and_a_placeholder_for_a_kind_without(
    tmp_path,
):
    lib = open_library("an", records={}, versions={}, blobs={})
    publish_dir(lib, CORPUS / "prop_swap" / "assets" / "props" / "lamp", "prop.lamp", source=CC0)
    publish(lib, "voice.narrator", {"name": "narrator"}, source=CC0)
    out = sheet(["an:prop.lamp@v001", "an:voice.narrator@v001"], libraries=[lib],
                out=tmp_path / "s.png", cell=96)
    cells = decode_png(out.read_bytes())
    assert cells.shape[1] == 4 + 2 * 100
    lamp, placeholder = cells[4:100, 4:100], cells[4:100, 104:200]
    assert (lamp < 128).any()  # the lamp is drawn
    assert (placeholder == 200).all()  # the voice is a grey placeholder
    parts = sheet(["an:prop.lamp@v001"], libraries=[lib], out=tmp_path / "p.png",
                  cell=64, parts=True)
    assert decode_png(parts.read_bytes()).shape[1] == 4 + 2 * 68  # two lamp svgs


@pytest.mark.browser
def test_a_private_sheet_is_refused_in_a_repo(tmp_path):
    lib = open_library("an", records={}, versions={}, blobs={})
    publish_dir(lib, CORPUS / "prop_swap" / "assets" / "props" / "lamp", "prop.lamp",
                source=PRIVATE)
    repo = _git_repo(tmp_path / "repo")
    with pytest.raises(PrivateOutputError):
        sheet(["an:prop.lamp@v001"], libraries=[lib], out=repo / "s.png")
    assert sheet(["an:prop.lamp@v001"], libraries=[lib], out=tmp_path / "s.png").is_file()


@pytest.mark.browser
def test_a_parts_sheet_captions_each_file_with_its_own_statement(tmp_path):
    """an#345: a sheet of only the free files of a version with private parts is publishable."""
    lib = open_library("an", records={}, versions={}, blobs={})
    folder = CORPUS / "prop_swap" / "assets" / "props" / "lamp"
    publish_dir(lib, folder, "prop.lamp", source=CC0,
                license_parts={"parts/on.svg": PRIVATE})
    repo = _git_repo(tmp_path / "repo")
    with pytest.raises(PrivateOutputError, match="private"):
        sheet(["an:prop.lamp@v001"], libraries=[lib], out=repo / "p.png", parts=True)
    from an.library.sheets import _part_class
    from an.library.api import read_version

    version = read_version(lib, "prop.lamp", "v001")
    off = (folder / "parts" / "off.svg").read_bytes()
    on = (folder / "parts" / "on.svg").read_bytes()
    assert (_part_class(lib, version, off), _part_class(lib, version, on)) == ("free", "private")


# ------------------------------------------- the sheet's captions and specimens (an#460)


def test_a_caption_keeps_its_licence_class_however_long_the_reference():
    from an.media.grid import fit_caption

    shown = fit_caption(("cutan:prop.desk-oversimplified@v001", " [private]"), 22, len)
    assert shown.endswith(" [private]") and "…" in shown and len(shown) <= 22


def test_a_small_specimen_is_drawn_again_on_a_bigger_canvas(monkeypatch):
    """A text block's size is a fraction of the frame: grow the canvas and it
    grows, so the sheet shows it sharp. A drawing of fixed size keeps the first frame."""
    import an.library.sheets as sheets

    def frame_of(scales):
        def fake(libraries, ref, kind, *, canvas):
            side = max(1, round(canvas * scales))
            calls.append(canvas)
            return encode_png(np.zeros((side, side, 3), np.uint8))

        return fake

    calls: list[int] = []
    monkeypatch.setattr(sheets, "_specimen_frame", frame_of(0.05))  # 768 -> 38 px
    out = sheets._sharp_specimen(None, "an:prop.day@v001", None, {"doc": {}}, 256)
    assert calls[0] == sheets.SPECIMEN_CANVAS and len(calls) == 2
    # grown in proportion, up to the cap: 768 -> 4096, so 38 px -> 205 px
    assert calls[1] == sheets.MAX_SPECIMEN_CANVAS
    assert max(decode_png(out).shape[:2]) == round(sheets.MAX_SPECIMEN_CANVAS * 0.05)

    calls.clear()
    monkeypatch.setattr(sheets, "_specimen_frame", lambda *a, canvas, **k: (calls.append(canvas), encode_png(np.zeros((40, 40, 3), np.uint8)))[1])
    out = sheets._sharp_specimen(None, "an:prop.dot@v001", None, {"doc": {}}, 256)
    assert len(calls) == 2 and decode_png(out).shape[:2] == (40, 40)


@pytest.mark.browser
def test_a_text_props_specimen_fills_its_cell(tmp_path):
    from an.genres import entity_kind
    from an.library.api import read_version
    from an.library.sheets import _sharp_specimen

    lib = open_library("an", records={}, versions={}, blobs={})
    doc = {"kind": "TextDescriptor", "name": "day", "text": "1", "unit": "block"}
    publish(lib, "prop.day", doc, source=CC0)
    version = read_version(lib, "prop.day", "v001")
    data = _sharp_specimen([lib], "an:prop.day@v001", entity_kind("prop"), version, 256)
    # The end-user test's "1" was ~40 px magnified into a 256 px cell; drawn
    # on the grown canvas it is most of the cell (the canvas cap stops it short).
    assert max(decode_png(data).shape[:2]) >= 0.7 * 256
