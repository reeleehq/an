"""an#275 (finding 9): a store write UPDATES ``scene.md`` instead of regenerating it.

`an render` writes the audio-stamped scene back through the scenes store, and
the store used to regenerate the markdown from the IR: an inline mapping came
back in block style, ``at: 0.0`` vanished as a default, and every word of prose
was dropped -- so a script editing the file had to be redone against rewritten
text. `merge_markdown` keeps the author's file when it already says what the IR
says, and otherwise rewrites only the blocks whose content changed.
"""

from __future__ import annotations

import os
import warnings

import pytest

from an.ir.sync import (
    MarkdownMergeWarning,
    ir_to_markdown,
    markdown_to_ir,
    merge_markdown,
    sync,
)
from an.stores.scenes import ScenesStore

#: What an author writes: prose everywhere, inline mappings, an explicit
#: default (`at: 0.0`), a comment, and a block the IR does not know.
AUTHORED = """# Alice & Bob

A silhouette film on backlit glass. This paragraph is not in the IR.

```yaml meta
title: Alice & Bob
duration: 4
fps: 24
```

## Shot s1 (cutout)

Alice enters from the left; Bob is already there.

```yaml shot
{duration: 2}
```

```yaml entities
- {kind: character, id: alice, store: characters, ref: alice}
- {kind: character, id: bob, store: characters, ref: bob}
```

```yaml actions
# Alice crosses to the table.
- {kind: tween, target: alice, property: x, to: 120, duration: 1.5}
- {kind: set, target: bob, property: alpha, value: 1.0, at: 0.0}
```

```dialogue
alice: Hi!
```

```text
A director's note in a block nobody parses.
```

## Shot s2 (cutout)

They part.

```yaml shot
{duration: 2}
```

```dialogue
bob: Bye.
```
"""


def _scene():
    return markdown_to_ir(AUTHORED)


def test_unchanged_content_leaves_the_file_byte_for_byte():
    assert merge_markdown(AUTHORED, _scene()) == AUTHORED


def test_json_side_state_does_not_rewrite_the_markdown():
    """What a render adds (audio, visemes) is not in scene.md; the file stays."""
    scene = _scene()
    scene.timeline[0].dialogue[0].audio_ref = "sha256:" + "0" * 64
    assert merge_markdown(AUTHORED, scene) == AUTHORED


def test_a_change_rewrites_only_its_block_and_keeps_every_word_of_prose():
    scene = _scene()
    scene.timeline[1].duration = 3.0
    out = merge_markdown(AUTHORED, scene)
    assert markdown_to_ir(out).timeline[1].duration == 3.0
    for kept in (
        "This paragraph is not in the IR.",
        "Alice enters from the left; Bob is already there.",
        "They part.",
        "# Alice crosses to the table.",
        "- {kind: set, target: bob, property: alpha, value: 1.0, at: 0.0}",
        "```text\nA director's note in a block nobody parses.\n```",
        "```yaml shot\n{duration: 2}\n```",  # s1's block: untouched
    ):
        assert kept in out, kept
    # Exactly one block changed: everything else is the author's text.
    changed = [
        (a, b) for a, b in zip(AUTHORED.splitlines(), out.splitlines()) if a != b
    ]
    assert changed == [("{duration: 2}", "duration: 3.0")], changed


def test_an_added_block_is_inserted_where_the_writer_puts_it():
    from an.ir import compose

    scene = _scene()
    scene.timeline[1].actions.append(compose.tween("bob", "x", to=10.0, duration=1.0))
    out = merge_markdown(AUTHORED, scene)
    s2 = out[out.index("## Shot s2") :]
    assert s2.index("```yaml shot") < s2.index("```yaml actions") < s2.index("```dialogue")
    assert "They part." in s2
    assert len(markdown_to_ir(out).timeline[1].actions) == 1


def test_a_removed_block_and_a_removed_shot_go_with_their_text():
    scene = _scene()
    scene.timeline[0].dialogue = []
    del scene.timeline[1]
    out = merge_markdown(AUTHORED, scene)
    back = markdown_to_ir(out)
    assert [s.id for s in back.timeline] == ["s1"] and not back.timeline[0].dialogue
    assert "They part." not in out and "Alice enters from the left" in out


def test_a_new_shot_is_appended_in_the_writers_form():
    from an.ir.schema import Shot

    scene = _scene()
    scene.timeline.append(Shot(id="s3", renderer="cutout", duration=1.0))
    out = merge_markdown(AUTHORED, scene)
    assert out.startswith(AUTHORED.rstrip("\n"))
    assert out.rstrip().endswith("## Shot s3 (cutout)\n\n```yaml shot\nduration: 1.0\n```")


def test_title_meta_and_renderer_changes_patch_their_lines_only():
    scene = _scene()
    scene.meta.title = "Alice and Bob"
    scene.meta.fps = 30
    scene.timeline[1].renderer = "manim"
    out = merge_markdown(AUTHORED, scene)
    back = markdown_to_ir(out)
    assert (back.meta.title, back.meta.fps, back.timeline[1].renderer) == (
        "Alice and Bob",
        30,
        "manim",
    )
    assert out.startswith("# Alice and Bob\n\nA silhouette film on backlit glass.")
    assert "## Shot s2 (manim)\n\nThey part." in out


def test_an_unreadable_file_is_regenerated_and_says_so():
    scene = _scene()
    with pytest.warns(MarkdownMergeWarning, match="could not be read"):
        out = merge_markdown("```yaml meta\n[not: a mapping\n```\n", scene)
    assert out == ir_to_markdown(scene)


def test_the_merged_file_always_reads_back_as_the_scene():
    """Whatever changed, the merged markdown says what the IR says."""
    from an.ir import compose

    scene = _scene()
    scene.timeline[0].entities = scene.timeline[0].entities[:1]
    scene.timeline[0].actions = [compose.set_("alice", "alpha", 0.5, at=0.25)]
    scene.timeline[1].dialogue[0].text = "Goodbye."
    out = merge_markdown(AUTHORED, scene)
    assert ir_to_markdown(markdown_to_ir(out)) == ir_to_markdown(scene)
    assert "Alice enters from the left; Bob is already there." in out


# ------------------------------------------------------------- through the store


def test_the_store_does_not_rewrite_an_unchanged_scene_md(tmp_path):
    (tmp_path / "scene.md").write_text(AUTHORED, encoding="utf-8")
    sync(tmp_path)  # writes ir/scene.json from the md
    store = ScenesStore(tmp_path)
    scene = store["main"]
    scene.timeline[0].dialogue[0].audio_ref = "sha256:" + "1" * 64  # a render's stamp
    store["main"] = scene
    assert (tmp_path / "scene.md").read_text(encoding="utf-8") == AUTHORED
    assert store["main"].timeline[0].dialogue[0].audio_ref.endswith("1" * 64)


def test_the_store_keeps_the_mtime_equalisation(tmp_path):
    """CLAUDE.md's invariant: the JSON stays newer, inside sync's tolerance, so
    the next sync rewrites neither file -- with or without a markdown write."""
    from an.ir.sync import SYNC_MTIME_TOLERANCE_S

    (tmp_path / "scene.md").write_text(AUTHORED, encoding="utf-8")
    sync(tmp_path)
    store = ScenesStore(tmp_path)
    for change in (False, True):
        scene = store["main"]
        if change:
            scene.timeline[1].duration = 5.0
        store["main"] = scene
        md, js = tmp_path / "scene.md", tmp_path / "ir" / "scene.json"
        skew = js.stat().st_mtime - md.stat().st_mtime
        assert 0 <= skew <= SYNC_MTIME_TOLERANCE_S
        result = sync(tmp_path)
        assert not result.wrote_md and not result.wrote_json
    assert "They part." in (tmp_path / "scene.md").read_text(encoding="utf-8")


def test_sync_from_a_newer_json_updates_the_markdown_in_place(tmp_path):
    (tmp_path / "scene.md").write_text(AUTHORED, encoding="utf-8")
    sync(tmp_path)
    js = tmp_path / "ir" / "scene.json"
    import json

    doc = json.loads(js.read_text(encoding="utf-8"))
    doc["timeline"][0]["duration"] = 2.5
    js.write_text(json.dumps(doc), encoding="utf-8")
    later = (tmp_path / "scene.md").stat().st_mtime + 10
    os.utime(js, (later, later))
    with warnings.catch_warnings():
        warnings.simplefilter("error", MarkdownMergeWarning)
        assert sync(tmp_path).wrote_md
    out = (tmp_path / "scene.md").read_text(encoding="utf-8")
    assert markdown_to_ir(out).timeline[0].duration == 2.5
    assert "Alice enters from the left; Bob is already there." in out


# ------------------------------------------------- a tie between the two files (an#412)


def _tie(tmp_path):
    md, js = tmp_path / "scene.md", tmp_path / "ir" / "scene.json"
    t = md.stat().st_mtime
    os.utime(md, (t, t))
    os.utime(js, (t, t))
    return md, js


def test_an_edit_made_in_the_same_instant_as_the_json_wins_and_says_so(tmp_path):
    """`cp -r film t1 && sed -i ... t1/scene.md` in one second: the two files
    are the same age and disagree. The JSON used to win silently (an#412), and
    the next store write reverted the edit in scene.md (an#411)."""
    from an.ir.sync import SyncTieWarning

    (tmp_path / "scene.md").write_text(AUTHORED, encoding="utf-8")
    sync(tmp_path)
    edited = AUTHORED.replace("to: 120", "to: 80")
    (tmp_path / "scene.md").write_text(edited, encoding="utf-8")
    _tie(tmp_path)
    with pytest.warns(SyncTieWarning, match="source of truth"):
        result = sync(tmp_path)
    assert result.wrote_json and not result.wrote_md
    scene = ScenesStore(tmp_path)["main"]
    assert scene.timeline[0].actions[0].to_value == 80


def test_a_consistent_pair_of_the_same_age_is_left_alone(tmp_path):
    (tmp_path / "scene.md").write_text(AUTHORED, encoding="utf-8")
    sync(tmp_path)
    _tie(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = sync(tmp_path)
    assert not result.wrote_json and not result.wrote_md


def test_a_render_s_write_back_no_longer_reverts_the_edit(tmp_path):
    """The whole an#411 chain: a same-second edit, a load, then the pipeline's
    store write. The edit survives, and so does its flow style and `at: 0.0`."""
    from an.ir.sync import SyncTieWarning

    (tmp_path / "scene.md").write_text(AUTHORED, encoding="utf-8")
    sync(tmp_path)
    edited = AUTHORED.replace("value: 1.0, at: 0.0}", "value: 0.5, at: 0.0}")
    (tmp_path / "scene.md").write_text(edited, encoding="utf-8")
    _tie(tmp_path)
    with pytest.warns(SyncTieWarning):
        sync(tmp_path)
    store = ScenesStore(tmp_path)
    scene = store["main"]
    scene.timeline[0].dialogue[0].audio_ref = "sha256:" + "2" * 64  # a render's stamp
    store["main"] = scene
    assert (tmp_path / "scene.md").read_text(encoding="utf-8") == edited
