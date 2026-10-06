# an.semantic.docs

The vocabulary section of the downstream `an` skill, generated from the registry.

ADR 0003 decision 6’s third generated surface. The skill keeps its prose; the
table between the two markers is rendered here and checked by a test, so a
preset, a method or a version cannot change without the skill saying so:

```default
python -m an.semantic.docs --write .claude/skills/an/SKILL.md
```

Each owner renders only its own rows (an#354): `an`’s skill carries the core
vocabulary, and a genre keeps its rows in its own skill, regenerated and checked
there with `--owner <genre>`, so a genre change cannot turn `an` red.

```pycon
>>> "| `walk` |" in skill_vocabulary_section() or "| `tween` |" in skill_vocabulary_section()
True
```

### Functions

| [`replace_section`](#an.semantic.docs.replace_section)(text, section)        | `text` with the block between the markers replaced by `section`.                  |
|----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`skill_vocabulary_section`](#an.semantic.docs.skill_vocabulary_section)(\*[, owner]) | The markdown between the markers: one table per kind, then the methods by aspect. |

### an.semantic.docs.replace_section(text, section)

`text` with the block between the markers replaced by `section`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> replace_section(f"a\n{BEGIN_MARKER}\nold\n{END_MARKER}\nb", "new").splitlines()[2]
'new'
```

### an.semantic.docs.skill_vocabulary_section(, owner='an')

The markdown between the markers: one table per kind, then the methods by aspect.

Only the rows `owner` registered: the core by default, a genre’s own with
`owner=<genre>` (its skill points back here for the core rows).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
