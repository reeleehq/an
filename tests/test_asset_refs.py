"""Asset references stay inside the project (an#483).

A plane's ``art.src`` and a part's ``path`` used to be followed wherever they
pointed: an absolute path or a ``../`` was resolved and parsed, which made
`an validate` (and the pack checkers built on it) a file-existence and
XML-parse oracle on the host. Now a reference outside its asset folder is an
error by name, never a read; the staging step and the rig probe treat it as
absent; and an SVG an asset names is linted by content, whatever its suffix.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path

import pytest

from an.adapters.cutout.render import CutoutAssetWarning, _stage_scene_assets, texture_source
from an.adapters.cutout.serialize import AssetJSON, AssetsJSON, CutoutSceneJSON, NodeJSON, TimelineJSON
from an.environments import EnvironmentDescriptor, Plane, PlaneArt
from an.ir.schema import AssetRef, SceneIR, Shot
from an.ir.validate import validate_semantic
from an.props import PropDescriptor
from an.stage.raster import is_svg_content, svg_problems
from an.stage.rig import part_probe
from an.stores._common import asset_ref_problem, inside_folder
from an.stores.environments import EnvironmentsStore
from an.stores.props import PropsStore

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4" width="4" height="4"><rect width="1" height="1"/></svg>'


# -----------------------------------------------------------------------------
# The rule, by name and by resolution
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel, problem",
    [
        ("parts/head.svg", None),
        ("plates/a b.png", None),
        ("./parts/head.svg", "`.` segment"),
        ("parts//head.svg", "`.` segment"),
        ("parts/./head.svg", "`.` segment"),
        ("parts/head.svg/", "`.` segment"),
        ("/etc/hostname", "absolute"),
        ("\\\\server\\share\\x.svg", "backslash"),
        ("C:\\art\\x.svg", "backslash"),
        ("C:/art/x.svg", "drive"),
        ("../../other/plate.png", "`..`"),
        ("parts/../../x.svg", "`..`"),
        ("parts/../parts/head.svg", "`..`"),
        ("parts\\..\\..\\x.svg", "backslash"),
        ("file:///etc/hostname", "URL"),
        ("http://example.org/x.svg", "URL"),
        ("data:image/svg+xml;base64,AAAA", "URL"),
        ("head.svg\n", "control character"),
        ("", "empty"),
    ],
)
def test_a_reference_is_judged_by_name(rel, problem):
    found = asset_ref_problem(rel)
    assert (found is None) == (problem is None), found
    if problem:
        assert problem in found


def test_a_link_out_of_the_folder_is_outside(tmp_path):
    folder = tmp_path / "asset"
    folder.mkdir()
    (tmp_path / "secret.svg").write_text(SVG, encoding="utf-8")
    assert inside_folder(folder, "parts/head.svg") == folder / "parts/head.svg"
    assert inside_folder(folder, "../secret.svg") is None
    try:
        os.symlink(tmp_path / "secret.svg", folder / "link.svg")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    assert inside_folder(folder, "link.svg") is None


# -----------------------------------------------------------------------------
# Nothing outside is read: the probe, the digest, the staging step
# -----------------------------------------------------------------------------


def _scene_json(**textures):
    return CutoutSceneJSON(
        scene=NodeJSON(name="root"),
        timeline=TimelineJSON(duration=1.0, tracks=[]),
        assets=AssetsJSON(textures=dict(textures), audio={}),
    )


def test_the_staging_step_copies_nothing_from_outside_the_store(tmp_path):
    (tmp_path / "secret.svg").write_text(SVG, encoding="utf-8")
    store = EnvironmentsStore(tmp_path / "envs")
    mall = {"environments": store}
    for src in ("environments/street/../../secret.svg", "environments//secret.svg"):
        assert texture_source(src, mall)[0] is None
    assert texture_source("environments/street/../../secret.svg", mall) == (None, "outside")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _stage_scene_assets(
            _scene_json(x=AssetJSON(src="environments/street/../../secret.svg")), mall, runtime
        )
    (w,) = [w for w in caught if issubclass(w.category, CutoutAssetWarning)]
    assert "not a path inside its asset's own folder in the 'environments' store" in str(w.message)
    assert list(runtime.rglob("*.svg")) == []


def test_the_rig_probe_calls_outside_art_absent(tmp_path):
    (tmp_path / "secret.svg").write_text(SVG, encoding="utf-8")
    store = PropsStore(tmp_path / "props")
    (tmp_path / "props" / "thing" / "parts").mkdir(parents=True)
    (tmp_path / "props" / "thing" / "parts" / "body.svg").write_text(SVG, encoding="utf-8")
    (tmp_path / "props" / "other").mkdir()
    (tmp_path / "props" / "other" / "o.svg").write_text(SVG, encoding="utf-8")
    probe = part_probe(store, art_prefix="props/")
    assert probe("props/thing/parts/body.svg") == (True, (4.0, 4.0))
    assert probe("props/thing/../../secret.svg") == (False, None)
    assert probe("props/thing//secret.svg")[0] is False
    assert probe("props/thing/../other/o.svg")[0] is False  # a sibling asset is outside too
    assert texture_source("props/thing/../other/o.svg", {"props": store}) == (None, "outside")
    try:
        os.symlink(tmp_path / "props" / "other" / "o.svg", tmp_path / "props" / "thing" / "parts" / "link.svg")
    except (OSError, NotImplementedError):
        return
    assert probe("props/thing/parts/link.svg")[0] is False  # a link to a sibling asset: the same
    assert texture_source("props/thing/parts/link.svg", {"props": store}) == (None, "outside")


def test_an_props_validate_refuses_an_outside_part_by_name(tmp_path):
    from an.stage.prop_validate import validate_prop

    store = _prop_store(tmp_path, "../../x.png")
    report = validate_prop(tmp_path / "props" / "thing")
    (f,) = [f for f in report.findings if "an asset reference must be" in f.description]
    assert "'../../x.png', which leaves the asset folder" in f.description
    store["thing"] = {**store["thing"], "skins": {"default": {"slots": {"body": {"body": {"path": "parts/gone.png"}}}}}}
    (f,) = [f for f in validate_prop(tmp_path / "props" / "thing").findings if "gone.png" in f.description]
    assert "is not in the folder" in f.description  # missing stays missing


# -----------------------------------------------------------------------------
# `an validate` says so, before any read
# -----------------------------------------------------------------------------


def _env_store(tmp_path, src, *, name="street"):
    store = EnvironmentsStore(tmp_path / "envs")
    store[name] = json.loads(
        EnvironmentDescriptor(
            name=name, planes=[Plane(name="plate", art=PlaneArt(kind="image", src=src))]
        ).model_dump_json()
    )
    return store


def _prop_store(tmp_path, path):
    store = PropsStore(tmp_path / "props")
    doc = PropDescriptor(name="thing", skins={"default": {"slots": {"body": {"body": {"path": path}}}}})
    data = json.loads(doc.model_dump_json())
    for slot in data["slots"]:
        slot["attachment"] = "body"
    store["thing"] = data
    return store


def _scene(*entities):
    return SceneIR(timeline=[Shot(id="s1", renderer="cutout", duration=1.0, entities=list(entities)),
                             Shot(id="s2", renderer="cutout", duration=1.0, entities=list(entities))])


ENV = AssetRef(kind="environment", id="set", store="environments", ref="street")
PROP = AssetRef(kind="prop", id="thing", store="props", ref="thing")


def _asset_findings(report):
    return [f for f in report.findings if "an asset reference must be" in f.description
            or "self-contained" in f.description]


@pytest.mark.parametrize("src", ["/etc/hostname", "../../secret.svg", "file:///etc/hostname"])
def test_an_environment_plane_outside_its_folder_is_an_error_by_name(tmp_path, src, monkeypatch):
    (tmp_path / "secret.svg").write_text("<not xml", encoding="utf-8")

    def never(*a, **k):  # nothing outside is read: not sized, not sniffed, not parsed
        raise AssertionError(f"read {a[0]!r}")

    for name in ("art_size", "is_svg_content", "svg_problems", "_head", "_parse_svg"):
        monkeypatch.setattr(f"an.stage.raster.{name}", never)
    report = validate_semantic(_scene(ENV), available_environments=_env_store(tmp_path, src))
    findings = _asset_findings(report)
    assert [f.ir_path for f in findings] == ["timeline/0/entities/0", "timeline/1/entities/0"]  # every shot that uses it
    f = findings[0]
    assert f.severity == "error" and f"plane plate names {src!r}" in f.description
    assert "not xml" not in f.description


def test_the_files_are_read_once_per_asset(tmp_path, monkeypatch):
    store = _env_store(tmp_path, "plate.svg")
    (tmp_path / "envs" / "street" / "plate.svg").write_text(SVG, encoding="utf-8")
    calls = []
    real = __import__("an.stage.raster", fromlist=["svg_problems"]).svg_problems
    monkeypatch.setattr("an.stage.raster.svg_problems", lambda src: calls.append(src) or real(src))
    validate_semantic(_scene(ENV), available_environments=store)
    assert len(calls) == 1


def test_a_part_outside_its_folder_is_an_error(tmp_path):
    report = validate_semantic(_scene(PROP), available_props=_prop_store(tmp_path, "../../x.png"))
    assert any("part body/body names '../../x.png', which leaves the asset folder" in f.description
               for f in _asset_findings(report))


def test_a_source_svg_and_colour_roles_are_judged_too(tmp_path):
    store = _prop_store(tmp_path, "parts/body.png")
    store["thing"] = {**store["thing"], "source_svg": "/tmp/source.svg", "colour_roles": {"../x.svg": {"#fff": "skin"}}}
    found = [f.description for f in _asset_findings(validate_semantic(_scene(PROP), available_props=store))]
    assert any("source_svg names '/tmp/source.svg', which is an absolute path" in d for d in found)
    assert any("colour_roles ../x.svg names '../x.svg', which leaves the asset folder" in d for d in found)


def test_a_link_out_of_the_folder_is_an_error_too(tmp_path):
    (tmp_path / "secret.svg").write_text(SVG, encoding="utf-8")
    store = _env_store(tmp_path, "link.svg")
    try:
        os.symlink(tmp_path / "secret.svg", tmp_path / "envs" / "street" / "link.svg")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    f, _ = _asset_findings(validate_semantic(_scene(ENV), available_environments=store))
    assert "resolves outside the asset's folder" in f.description


def test_an_inside_reference_is_fine(tmp_path):
    store = _env_store(tmp_path, "plate.svg")
    (tmp_path / "envs" / "street" / "plate.svg").write_text(SVG, encoding="utf-8")
    assert _asset_findings(validate_semantic(_scene(ENV), available_environments=store)) == []


# -----------------------------------------------------------------------------
# An SVG is linted by what it is, not what it is called
# -----------------------------------------------------------------------------


def test_svg_is_recognised_by_content():
    assert is_svg_content(SVG.encode())
    assert is_svg_content(b'\xef\xbb\xbf<?xml version="1.0"?>\n<!-- c -->\n<svg/>')
    assert is_svg_content(b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x.dtd" [<!ENTITY e "v">]>\n<!-- c --><svg/>')
    assert is_svg_content(b"<!--" + b" " * 3000 + b"--><?xml-stylesheet href='x'?><svg/>")
    assert is_svg_content('<?xml version="1.0" encoding="UTF-16"?><svg/>'.encode("utf-16"))
    assert not is_svg_content(b"\x89PNG\r\n")
    assert not is_svg_content(b"<svgx/>") and not is_svg_content(b"<html><svg/></html>")
    assert not is_svg_content(b"") and not is_svg_content(b"just text")


def test_svg_problems_name_code_pictures_and_outside_links():
    bad = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
           '<script>x()</script><foreignObject/><image xlink:href="../x.png"/>'
           '<rect fill="url(#g)"/><rect fill="url(http://x/y)"/>'
           '<style>@import url(x.css);</style><use href="#a"/></svg>')
    problems = svg_problems(bad)
    assert problems[0] == "forbidden element(s): foreignObject, image, script"
    assert "'../x.png'" in problems[1] and "url(http://x/y)" in problems[1] and "<style> imports" in problems[1]
    assert "more" not in problems[1] and len(problems) == 2
    four = bad.replace("<use href=\"#a\"/>", "<use href=\"#a\"/><a href=\"https://x\"/>")
    assert "and 1 more" in svg_problems(four)[1]
    assert svg_problems(SVG) == []
    assert svg_problems(SVG.encode()) == [] and svg_problems(b"<svg" + b" " * 5000 + b"/>") == []  # bytes of any length
    assert svg_problems("<svg")[0].startswith("not valid XML")
    assert svg_problems(b"<!DOCTYPE svg [<!ENTITY e 'v'>]><svg><script/></svg>") == ["forbidden element(s): script"]


@pytest.mark.parametrize("name", ["plate.svg", "plate.SVG", "plate.txt"])
def test_a_referenced_svg_with_a_script_is_an_error_whatever_its_suffix(tmp_path, name):
    store = _env_store(tmp_path, name)
    (tmp_path / "envs" / "street" / name).write_text(
        SVG.replace("<rect", '<script>x()</script><image href="http://x/y.png"/><rect'), encoding="utf-8")
    findings = _asset_findings(validate_semantic(_scene(ENV), available_environments=store))
    assert [f.severity for f in findings] == ["error"] * 4  # two problems, each on both shots
    assert "forbidden element(s): image, script" in findings[0].description
    assert "links outside the file: 'http://x/y.png'" in findings[1].description


ART = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>'


@pytest.mark.parametrize(
    "prolog",
    ["<!-- made by a-b (v1) -->", "<!DOCTYPE svg>", '<?xml version="1.0"?><?xml-stylesheet href="x"?>'],
)
def test_the_staging_step_puts_the_root_on_a_line_of_its_own(tmp_path, prolog):
    """an#525: PixiJS's SVG sniffing (a multiline regex) cannot skip these
    prologs when the root follows on the same line, and the whole shot failed
    at load. Checks the staged bytes, not Pixi: the render is a developer-machine check."""
    store = PropsStore(tmp_path / "props")
    parts = tmp_path / "props" / "thing" / "parts"
    parts.mkdir(parents=True)
    (parts / "body.svg").write_text(f"{prolog}{ART}", encoding="utf-8")
    (parts / "clean.svg").write_text(ART, encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    for name in ("body", "clean"):
        _stage_scene_assets(
            _scene_json(x=AssetJSON(src=f"props/thing/parts/{name}.svg")), {"props": store}, runtime
        )
    assert (runtime / "props/thing/parts/body.svg").read_text(encoding="utf-8") == f"{prolog}\n{ART}"
    assert (runtime / "props/thing/parts/clean.svg").read_text(encoding="utf-8") == ART


def test_a_data_uri_svg_gets_the_same_repair():
    import base64

    from an.stage.text_layout import svg_data_uri

    uri = svg_data_uri(f"<!-- a-b -->{ART}")
    assert base64.b64decode(uri.split(",", 1)[1]) == f"<!-- a-b -->\n{ART}".encode()
