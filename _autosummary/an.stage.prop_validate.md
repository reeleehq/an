# an.stage.prop_validate

Check a prop’s asset folder offline, and say what a prop must be (an#340).

`an props validate <dir>` and `an props contract`: the prop’s twin of
`an character validate` / `an character contract`, in the core because a
prop is the stage’s own rig (`an.stage.props.PropDescriptor`), not a genre’s.
Before it, a carved prop’s layout rules lived in its `prop.json` metadata and
nothing read them.

The rig rules are the stage’s ([`an.stage.rig`](an.stage.rig.md#module-an.stage.rig)), so this validator, `an
validate` and the rig builder say the same thing: a structural problem
([`rig_problems()`](an.stage.rig.md#an.stage.rig.rig_problems)) blocks; where the stage cannot draw a
nested chain ([`chain_draw_order_problems()`](an.stage.rig.md#an.stage.rig.chain_draw_order_problems)), the origin and
the rest pose are advisories here, because they are the stage’s limits or a
likely slip, not a malformed rig.

```pycon
>>> import tempfile
>>> with tempfile.TemporaryDirectory() as d:
...     report = validate_prop(d, name="nothing")
>>> report.passed, report.findings[0].description
(False, "nothing has no prop.json, or it is not a PropDescriptor (kind 'PropDescriptor')")
```

### Module Attributes

| [`PROP_META_NAME`](#an.stage.prop_validate.PROP_META_NAME)   | The descriptor file a prop folder holds (the props store's sidecar name).   |
|-------------------------------------------------------------------|-----------------------------------------------------------------------------|
| [`BLOCKING`](#an.stage.prop_validate.BLOCKING)         | Finding severities, the ones `an character validate` uses.                  |

### Functions

| [`render_prop_contract`](#an.stage.prop_validate.render_prop_contract)()              | What a prop folder must hold, read off the schema and the rig rules (never retyped).   |
|--------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`validate_prop`](#an.stage.prop_validate.validate_prop)(prop_dir, \*[, name]) | Check a prop folder (`prop.json` + `parts/`) against the rig contract, offline.        |

### an.stage.prop_validate.BLOCKING *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'error'*

Finding severities, the ones `an character validate` uses.

### an.stage.prop_validate.PROP_META_NAME *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'prop.json'*

The descriptor file a prop folder holds (the props store’s sidecar name).

### an.stage.prop_validate.render_prop_contract()

What a prop folder must hold, read off the schema and the rig rules (never retyped).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> "nesting" in render_prop_contract()
True
```

### an.stage.prop_validate.validate_prop(prop_dir, , name=None)

Check a prop folder (`prop.json` + `parts/`) against the rig contract, offline.

Blocking: no or an unreadable descriptor, a structural rig problem (an
unknown bone, a bone cycle), an attachment whose art is not in the folder,
a prop that draws nothing. Advisory: a chain the stage cannot draw in its
declared order (the compiler refuses it), the origin, the rest pose, an
unpopulated `AssetSource`.

* **Return type:**
  [`VerificationReport`](an.verify.md#an.verify.VerificationReport)
