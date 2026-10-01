# an.expression.registration

The face side of the cut-out genre, as declarations: `expression` and `[emotion]`.

What the cut-out genre ([`an.genres.cutout`](an.genres.cutout.html.md#module-an.genres.cutout)) registers from here:

- the **\`\`expression\`\` action kind** — [`an.ir.schema.ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction)
  (hold a facial expression, an#98): zero-width in a `sequence` when it runs
  to the shot end, and its `scene.md` spelling;
- the **\`\`[emotion]\`\` dialogue sugar** — `maya [happy]: Hi!` fills
  `an.ir.schema.Dialogue.emotion`, which the expression provider turns
  > into an expression over the line, in memory only.

Plain declarations: importing this module registers nothing.

```pycon
>>> EXPRESSION.name, EMOTION.opener, EMOTION.parse(" Happy ")
('expression', '[', 'happy')
```

### Module Attributes

| [`EMOTION_NAME_RE`](#an.expression.registration.EMOTION_NAME_RE)   | a preset name (`happy`, `wry-smile`).   |
|--------------------------------------------------------------------|-----------------------------------------|

### Functions

| [`expression_duration`](#an.expression.registration.expression_duration)(action, extent)   | An expression's span: its `duration`, else zero (it runs to the shot end).        |
|----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| [`format_emotion`](#an.expression.registration.format_emotion)(line)                  | The `[…]` content for `line`, or `None` when it carries no emotion.               |
| [`parse_emotion`](#an.expression.registration.parse_emotion)(content)                | `[happy]`'s content to the line's emotion, lower-cased; refuse a non-name.        |
| [`read_expression_md`](#an.expression.registration.read_expression_md)(item, \*, index)   | `{kind: expression, target, [preset], [axes], [intensity], [duration], [blend]}`. |
| [`write_expression_md`](#an.expression.registration.write_expression_md)(leaf)             | The `scene.md` entry for `leaf` (`read_expression_md`'s inverse).                 |

### an.expression.registration.EMOTION_NAME_RE *= re.compile('[\\\\w-]+')*

a preset name (`happy`, `wry-smile`).

* **Type:**
  What an emotion name may be

### an.expression.registration.expression_duration(action, extent)

An expression’s span: its `duration`, else zero (it runs to the shot end).

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)

```pycon
>>> expression_duration(ExpressionAction(target="a", duration=2.0), None)
2.0
>>> expression_duration(ExpressionAction(target="a"), None)
0.0
```

### an.expression.registration.format_emotion(line)

The `[…]` content for `line`, or `None` when it carries no emotion.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.expression.registration.parse_emotion(content)

`[happy]`’s content to the line’s emotion, lower-cased; refuse a non-name.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.expression.registration.read_expression_md(item, , index)

`{kind: expression, target, [preset], [axes], [intensity], [duration], [blend]}`.

Landed with its writer and round trip in one commit (an#98): the writer
skips unknown leaves, so a parser-only entry would vanish from scene.md on
the next sync and then from the JSON on the next md edit.

* **Return type:**
  [`ExpressionAction`](an.ir.schema.html.md#an.ir.schema.ExpressionAction)

### an.expression.registration.write_expression_md(leaf)

The `scene.md` entry for `leaf` (`read_expression_md`’s inverse).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]
