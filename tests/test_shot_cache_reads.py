"""Recorded reads in the shot cache (ADR 0004 decision 3, an#316).

A shot is keyed on the asset entries its compile READ, not on the whole
project: an edit to an asset re-renders only the shots that read it, and the
render summary names that asset. The measured case was a three-shot film whose
one-prop edit re-rendered all three shots.

No browser, no ffmpeg: the keyer is real, the render is the stand-in of
`tests/test_shot_cache.py`.
"""

from __future__ import annotations

import pytest

from an.adapters._base import RenderContext
from an.build import ShotCache, in_memory_shot_cache_store
from an.build.reads import WHOLE_STORE, RecordingMall, entry_digest, read_digests
from an.build.shot_cache import KEY_FORMAT_CHANGED, explain_change  # noqa: F401
from an.ir.schema import AssetRef
from an.project import load

#: Renders twice and asserts reuse: the source the shot key hashes must not
#: move between the renders, whatever else edits a shared checkout (an#379).
pytestmark = pytest.mark.usefixtures("frozen_source_digests")

from tests.test_shot_cache import (  # noqa: F401 — the fixture is used by name
    _env,
    _FakeCutoutRender,
    _project,
    _render,
    _set_shots,
    _shot,
    fake_render,
)

_LOGO = {"kind": "TextDescriptor", "name": "logo", "text": "PUNIC WARS", "size": 0.2}
_INTRO = {"kind": "TextDescriptor", "name": "intro", "text": "A long time ago", "size": 0.1}


def _prop(pid: str) -> AssetRef:
    return AssetRef(kind="prop", id=pid, store="props", ref=pid)


def _crawl_film(tmp_path):
    """The punic-crawl shape: ``intro`` places one text prop, ``main`` the
    logo, ``end`` nothing."""
    root = _project(
        tmp_path,
        _shot("intro", 10.0, entities=[_prop("intro")]),
        _shot("main", 20.0, entities=[_prop("logo")]),
        _shot("end", 30.0),
    )
    props = load(root).mall["props"]
    props["intro"] = dict(_INTRO)
    props["logo"] = dict(_LOGO)
    return root


def test_an_edit_to_a_prop_rerenders_only_the_shot_that_places_it(tmp_path, fake_render):
    root = _crawl_film(tmp_path)
    report, rendered = _render(root, fake_render)
    assert rendered == ["intro", "main", "end"]

    props = load(root).mall["props"]
    props["logo"] = {**_LOGO, "text": "PUNIC WARS III"}
    report, rendered = _render(root, fake_render)
    assert rendered == ["main"] and report.reused == ["intro", "end"]
    assert report.summary() == (
        "3 shot(s): 1 rendered (main), 2 reused (intro, end); "
        "not reused: asset changed: props/logo (main)"
    )


def test_an_entry_records_the_assets_it_read(tmp_path, fake_render):
    root = _crawl_film(tmp_path)
    report, _ = _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    reads = {o.shot_id: set(store[o.key].reads) for o in report.outcomes}
    assert "props/logo" in reads["main"] and "props/intro" not in reads["main"]
    assert "props/intro" in reads["intro"] and "props/logo" not in reads["intro"]
    assert not any(r.startswith("props/") for r in reads["end"])


def test_a_sound_edit_rerenders_no_picture(tmp_path, fake_render):
    """Sounds are mixed into the FILM (`an.assemble`), never into a shot's
    pictures: a re-cut WAV moves no shot key, so the next render re-mixes and
    reuses every shot."""
    from an.sounds import add_sound

    root = _crawl_film(tmp_path)
    sounds = load(root).mall["sounds"]
    add_sound(sounds, "scratch", _wav(0.1), source={"provider": "test"})
    _render(root, fake_render)
    add_sound(load(root).mall["sounds"], "scratch", _wav(0.2), source={"provider": "test"})
    report, rendered = _render(root, fake_render)
    assert rendered == [] and report.reused == ["intro", "main", "end"]


def _wav(seconds: float) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buf.getvalue()


def test_an_unread_asset_added_or_removed_rerenders_nothing(tmp_path, fake_render):
    root = _crawl_film(tmp_path)
    _render(root, fake_render)
    load(root).mall["props"]["unused"] = {**_LOGO, "name": "unused"}
    _, rendered = _render(root, fake_render)
    assert rendered == []


def test_a_shot_that_gains_a_prop_says_its_document_changed(tmp_path, fake_render):
    root = _crawl_film(tmp_path)
    _render(root, fake_render)
    _set_shots(
        root,
        _shot("intro", 10.0, entities=[_prop("intro")]),
        _shot("main", 20.0, entities=[_prop("logo")]),
        _shot("end", 30.0, entities=[_prop("logo")]),
    )
    report, rendered = _render(root, fake_render)
    assert rendered == ["end"]
    (end,) = [o for o in report.outcomes if o.shot_id == "end"]
    assert end.reason.startswith("asset changed: props/logo")


def test_without_recorded_reads_every_shot_depends_on_the_project(tmp_path, fake_render):
    """``record_reads=False`` is the first slice, kept selectable."""
    root = _crawl_film(tmp_path)
    whole = lambda: ShotCache(environment=_env(), record_reads=False)  # noqa: E731
    _render(root, fake_render, cache=whole())
    load(root).mall["props"]["logo"] = {**_LOGO, "text": "X"}
    report, rendered = _render(root, fake_render, cache=whole())
    assert rendered == ["intro", "main", "end"]
    assert "a project asset changed" in report.summary()


def test_a_keyer_that_does_not_record_reads_keeps_the_project_dependency(tmp_path, monkeypatch):
    """An opaque renderer (a Manim source opens files by path, an#291) cannot
    vouch for its reads: its shots keep the whole-project part."""
    from an.build import keys

    import an.adapters  # noqa: F401 — registers the cut-out keyer
    from an.adapters.cutout.render import CutoutRenderer

    from an.build import every_asset_digest
    from an.build.keys import canonical_digest

    entry = keys._KEYERS["cutout"]
    assert entry.records_reads
    mall = {"audio": {}, "props": {"unread": {"text": "x"}}}
    ctx = RenderContext(mall=mall, work_dir=tmp_path, fps=12, resolution=(160, 120))
    engine = ShotCache(in_memory_shot_cache_store(), environment=_env())
    engine.begin(mall)
    recorded = engine.plan(_shot("a", 1.0), CutoutRenderer(), ctx)
    assert recorded.inputs["assets"] == canonical_digest({})  # read nothing

    monkeypatch.setitem(keys._KEYERS, "cutout", keys._KeyerEntry(
        keyer=entry.keyer, environment=entry.environment,
        renderer_type=entry.renderer_type, parts=dict(entry.parts)))
    engine.begin(mall)
    opaque = engine.plan(_shot("a", 1.0), CutoutRenderer(), ctx)
    assert opaque.inputs["assets"] == every_asset_digest(mall)
    assert recorded.inputs["project"] == opaque.inputs["project"]


def test_a_custom_dependency_reaches_every_shot(tmp_path, fake_render):
    """``dependencies=`` is what EVERY shot depends on, recorded reads or not
    (an#316 review, finding 1)."""
    root = _crawl_film(tmp_path)
    value = {"v": "one"}
    custom = lambda: ShotCache(  # noqa: E731
        environment=_env(), dependencies=lambda mall, project_root=None: value["v"] * 32
    )
    _render(root, fake_render, cache=custom())
    value["v"] = "two"
    report, rendered = _render(root, fake_render, cache=custom())
    assert rendered == ["intro", "main", "end"]
    assert "the library lockfile changed" in report.summary()


def test_an_older_entry_is_said_to_be_another_key_format(tmp_path, fake_render, monkeypatch):
    from an.build import keys, shot_cache

    root = _crawl_film(tmp_path)
    _render(root, fake_render)
    monkeypatch.setattr(keys, "SHOT_KEY_IMPL_VERSION", keys.SHOT_KEY_IMPL_VERSION + 1)
    monkeypatch.setattr(shot_cache, "SHOT_KEY_IMPL_VERSION", keys.SHOT_KEY_IMPL_VERSION)
    report, rendered = _render(root, fake_render)
    assert rendered == ["intro", "main", "end"]
    assert report.summary().endswith(f"not reused: {KEY_FORMAT_CHANGED} (intro, main, end)")


def test_a_render_code_change_names_the_modules_that_moved(tmp_path, fake_render, monkeypatch):
    """an#395: "an's render code changed" says which module(s), from the
    per-module digests each entry keeps beside the ``code`` part."""
    from an.stage import cache_key

    root = _crawl_film(tmp_path)
    modules = cache_key.render_code_modules()
    monkeypatch.setattr(cache_key, "render_code_modules", lambda: dict(modules))
    _render(root, fake_render)
    store = load(root).mall["shot_cache"]
    assert all(store[k].code == modules for k in list(store) if getattr(store[k], "role", "") == "mp4")
    edited = {**modules, "an.stage.compile": "e" * 64}
    monkeypatch.setattr(cache_key, "render_code_modules", lambda: dict(edited))
    monkeypatch.setattr(cache_key, "render_code_digest", lambda: "c" * 64)
    report, rendered = _render(root, fake_render)
    assert rendered == ["intro", "main", "end"]
    assert report.summary().endswith(
        "not reused: an's render code (an.stage.compile) changed (intro, main, end)"
    )


# -----------------------------------------------------------------------------
# The recording view and the explanation, without a project
# -----------------------------------------------------------------------------


def test_the_recording_view_notes_gets_membership_and_listing():
    mall = RecordingMall({"props": {"a": 1, "b": 2}, "audio": {"x": b""}})
    props = mall["props"]
    assert props.get("a") == 1 and "zz" not in props
    assert mall.get("props") is props  # one view per store
    assert set(mall.reads) == {("props", "a"), ("props", "zz")}
    list(props)
    assert ("props", WHOLE_STORE) in mall.reads
    mall["audio"]["x"]  # not an asset store: never recorded
    assert not any(s == "audio" for s, _ in mall.reads)
    assert bool(RecordingMall({"props": {}})["props"]) is False
    assert RecordingMall({"props": {}}).reads == set()


def test_a_whole_store_read_moves_with_any_entry():
    reads = [("props", WHOLE_STORE)]
    assert read_digests({"props": {"a": 1}}, reads) != read_digests({"props": {"a": 1, "b": 2}}, reads)


def test_an_entry_digest_covers_its_files_beside_the_mapping(tmp_path):
    from an.stores.props import PropsStore

    store = PropsStore(tmp_path / "props")
    store["logo"] = dict(_LOGO)
    store["logo2"] = dict(_LOGO)
    before = entry_digest(store, "logo")
    (tmp_path / "props" / "logo" / "font.ttf").write_bytes(b"glyphs")
    assert entry_digest(store, "logo") != before
    # A neighbour whose name starts the same is another entry.
    after = entry_digest(store, "logo")
    (tmp_path / "props" / "logo2" / "font.ttf").write_bytes(b"other")
    assert entry_digest(store, "logo") == after
    # OS clutter is not an asset.
    (tmp_path / "props" / "logo" / ".DS_Store").write_bytes(b"x")
    assert entry_digest(store, "logo") == after
    # Nor is an entry whose name only starts with this one's (review, finding 5).
    store["logo.v2"] = dict(_LOGO)
    (tmp_path / "props" / "logo.v2" / "font.ttf").write_bytes(b"v2")
    assert entry_digest(store, "logo") == after


def test_the_key_digests_the_texture_staging_reads(tmp_path, monkeypatch):
    """One resolver for staging and keying (review, finding 2): whatever file
    staging would copy for a ``src`` is the file the key digests."""
    from types import SimpleNamespace

    from an.build.keys import file_digest
    from an.stage import cache_key, render

    art = tmp_path / "art.svg"
    art.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(render, "texture_source", lambda src, mall: (art, ""))
    doc = SimpleNamespace(assets=SimpleNamespace(textures={"t": SimpleNamespace(src="anywhere/x.svg")}))
    assert cache_key.texture_digests(doc, {}) == {"t": file_digest(art)}


@pytest.mark.parametrize(
    "before, after, expected",
    [
        ({"compiled": "a"}, {"compiled": "b"}, "its document changed"),
        ({"knobs": "a", "environment": "e"}, {"knobs": "b", "environment": "f"},
         "render settings and the render environment changed"),
        ({"compiled": "a"}, {"compiled": "a", "fonts": "f"}, "the system fonts changed"),
        ({"assets": "a"}, {"assets": "b"}, "a project asset changed"),
    ],
)
def test_explain_change_names_the_parts_that_moved(before, after, expected):
    assert explain_change(before, {}, after, {}) == expected


def test_explain_change_names_assets_and_independent_parts():
    got = explain_change(
        {"compiled": "a", "assets": "x", "knobs": "k"}, {"props/logo": "1", "props/b": "1"},
        {"compiled": "b", "assets": "y", "knobs": "j"}, {"props/logo": "2", "props/b": "1"},
    )
    assert got == "asset changed: props/logo and render settings changed"
