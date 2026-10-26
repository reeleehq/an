"""Markdown ↔ IR sync round-trip + disk-level reconciliation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from an.ir.schema import SceneIR
from an.ir.sync import ir_to_markdown, markdown_to_ir, sync


def test_md_to_ir_extracts_meta_and_dialogue():
    md = """# Demo

```yaml meta
title: Demo
duration: 5
fps: 24
```

## Shot s1 (cutout)

```yaml shot
duration: 5
```

```dialogue
charlie: hello there
maya: hi
```
"""
    scene = markdown_to_ir(md)
    assert scene.meta.title == "Demo"
    assert scene.meta.duration == 5
    assert scene.meta.fps == 24
    assert len(scene.timeline) == 1
    assert scene.timeline[0].id == "s1"
    assert scene.timeline[0].renderer == "cutout"
    assert [d.speaker for d in scene.timeline[0].dialogue] == ["charlie", "maya"]
    assert scene.timeline[0].dialogue[0].text == "hello there"


def test_ir_to_md_round_trip_preserves_structure():
    src_md = """# RT

```yaml meta
title: RT
duration: 3
fps: 30
```

## Shot a (cutout)

```yaml shot
duration: 3
```

```dialogue
charlie: hi
```
"""
    scene_a = markdown_to_ir(src_md)
    regenerated_md = ir_to_markdown(scene_a)
    scene_b = markdown_to_ir(regenerated_md)

    assert scene_a.meta.title == scene_b.meta.title
    assert scene_a.meta.duration == scene_b.meta.duration
    assert len(scene_a.timeline) == len(scene_b.timeline)
    assert scene_a.timeline[0].id == scene_b.timeline[0].id
    assert scene_a.timeline[0].dialogue[0].text == scene_b.timeline[0].dialogue[0].text


def test_sync_writes_json_when_only_md_exists():
    with tempfile.TemporaryDirectory() as d:
        pdir = Path(d)
        (pdir / "scene.md").write_text(
            "# X\n\n```yaml meta\ntitle: X\nduration: 1\n```\n\n"
            "## Shot s1 (cutout)\n\n```yaml shot\nduration: 1\n```\n",
            encoding="utf-8",
        )
        result = sync(pdir)
        assert result.wrote_json
        assert (pdir / "ir" / "scene.json").exists()
        data = json.loads((pdir / "ir" / "scene.json").read_text(encoding="utf-8"))
        scene = SceneIR.model_validate(data)
        assert scene.meta.title == "X"


def test_sync_writes_md_when_only_json_exists():
    with tempfile.TemporaryDirectory() as d:
        pdir = Path(d)
        scene = SceneIR()
        scene.meta.title = "JsonFirst"
        (pdir / "ir").mkdir(parents=True)
        (pdir / "ir" / "scene.json").write_text(
            scene.model_dump_json(), encoding="utf-8"
        )
        result = sync(pdir)
        assert result.wrote_md
        assert (pdir / "scene.md").exists()
        assert "JsonFirst" in (pdir / "scene.md").read_text(encoding="utf-8")


def test_an_unset_duration_is_what_the_shots_lay_out_so_a_dissolve_does_not_warn():
    """an#481: `meta.duration` left out was filled with the plain sum of the
    shots, which `an validate` then compared with the real layout (minus each
    dissolve's overlap) and warned about."""
    from an.ir.sync import markdown_to_ir
    from an.ir.validate import validate_semantic

    md = """# T

```yaml meta
title: T
fps: 24
```

## Shot a (cutout)

```yaml shot
duration: 2
```

## Shot b (cutout)

```yaml shot
duration: 2
transition: {kind: dissolve, duration: 0.6}
```
"""
    from an.assemble import film_duration
    from an.ir.sync import ir_to_markdown

    scene = markdown_to_ir(md)
    # an#557: unset stays unset (0.0), never a derived value; the length is
    # what the shots lay out, asked of `film_duration`.
    assert scene.meta.duration == 0.0
    assert round(film_duration(scene), 4) == 3.4167
    assert not [
        f for f in validate_semantic(scene).findings if f.ir_path == "meta/duration"
    ]
    # ... and the writer does not put a derived value in the file as if authored,
    # so a regenerated file reads back unset, and warns about nothing, again.
    written = ir_to_markdown(scene)
    assert "duration: 3.4" not in written
    assert markdown_to_ir(written).meta.duration == 0.0
    # An authored duration is left as written, and written back.
    authored = markdown_to_ir(md.replace("fps: 24", "fps: 24\nduration: 9"))
    assert authored.meta.duration == 9
    assert markdown_to_ir(ir_to_markdown(authored)).meta.duration == 9


def test_an_unset_duration_round_trips_unset_between_md_and_json():
    """an#557: 0.0 is "unset" on both sides of the md <-> json round trip, and a
    document written before it (a `duration:` line, derived or authored) reads,
    and is written back, exactly as it was."""
    from an.ir.schema import Meta, SceneIR, Shot
    from an.ir.sync import ir_to_markdown, markdown_to_ir, scene_from_json_doc

    unset = SceneIR(meta=Meta(title="U", fps=24), timeline=[Shot(id="a", duration=2.0)])
    md = ir_to_markdown(unset)
    assert "duration: 0" not in md  # the meta block omits it, like `step_hz`
    back = markdown_to_ir(md)
    assert back.meta.duration == 0.0
    assert back.model_dump() == unset.model_dump()
    assert ir_to_markdown(back) == md
    via_json = scene_from_json_doc(json.loads(back.model_dump_json()))
    assert via_json.meta.duration == 0.0
    assert ir_to_markdown(via_json) == md

    # A stored document carrying a value (as the pre-an#557 writer always did)
    # loads with that value and writes it back byte for byte.
    stored = md.replace("author: ''\n", "author: ''\nduration: 2.0\n")
    assert stored != md
    scene = markdown_to_ir(stored)
    assert scene.meta.duration == 2.0
    assert ir_to_markdown(scene) == stored
