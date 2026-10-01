# an.semantic.prompt

The `an iterate` system prompt, generated from the vocabulary registry.

ADR 0003 decision 6: the prompt is one of the three surfaces generated from the
registry, never written by hand. [`vocabulary_prompt()`](#an.semantic.prompt.vocabulary_prompt) renders the IR’s
fields and every registered name — action and entity kinds, motion and
expression presets, camera moves, easings, methods by aspect — each with its
one-sentence description and its params. The *protocol* around it (the patch
operations, the path syntax, the editing rules) is `an iterate`’s own and is
passed in as `preamble` and `postamble`.

```pycon
>>> text = vocabulary_prompt()
>>> "push_in" in text and "tween" in text and "linear" in text
True
```

### Functions

| [`iterate_prompt`](#an.semantic.prompt.iterate_prompt)(\*, preamble, postamble)   | `preamble` + the generated vocabulary + `postamble` (the `an iterate` protocol).   |
|--------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`vocabulary_prompt`](#an.semantic.prompt.vocabulary_prompt)(\*[, kinds])            | The IR fields and every registered name, as prompt text.                           |

### an.semantic.prompt.iterate_prompt(, preamble, postamble)

`preamble` + the generated vocabulary + `postamble` (the `an iterate` protocol).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.semantic.prompt.vocabulary_prompt(, kinds=(('action', "Action kinds (an action's \`kind\`)"), ('entity', "Entity kinds (an entity's \`kind\`)"), ('motion_preset', 'Motion presets (\`play\` by name; \`args\` are the parameters shown)'), ('expression_preset', "Expression presets (an \`expression\`'s \`preset\`, a dialogue line's \`emotion\`)"), ('camera_move', 'Camera moves (\`camera: {move: …}\`)'), ('easing', "Easings (a tween's \`easing\`)")))

The IR fields and every registered name, as prompt text.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
