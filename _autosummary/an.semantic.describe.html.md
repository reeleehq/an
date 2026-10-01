# an.semantic.describe

Describe an asset: what it affords, and per aspect what applies and what is missing.

ADR 0002’s first slice ends with `an character capabilities <name>`: the
affordances (with the declared overrides the derivation used), and per aspect
the method the default chain picks, the methods that apply, and the
`why_not` of the rest with their remedies. [`describe_asset()`](#an.semantic.describe.describe_asset) is that
answer as data (the MCP surface’s describe-an-asset query returns it);
[`format_description()`](#an.semantic.describe.format_description) is its terminal form. Core code: it names no rig.

```pycon
>>> from an.semantic.entries import Aspect, Method
>>> from an.semantic.registry import register_aspect, register_entry, drop_owner
>>> _ = register_entry(Method("demo.fly", aspect="demo_travel", requires=("limbs.wings",)), owner="demo")
>>> _ = register_entry(Method("demo.float", aspect="demo_travel"), owner="demo")
>>> _ = register_aspect(Aspect("demo_travel", chain=("demo.fly", "demo.float")), owner="demo")
>>> d = describe_profile({}, aspects=("demo_travel",))
>>> d["aspects"]["demo_travel"]["default"], list(d["aspects"]["demo_travel"]["not_applicable"])
('demo.float', ['demo.fly'])
>>> drop_owner("demo")
```

### Functions

| [`describe_asset`](#an.semantic.describe.describe_asset)(doc[, art, kind, aspects])   | [`describe_profile()`](#an.semantic.describe.describe_profile) of an asset's derived profile, with the analyser and overrides.   |
|----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| [`describe_profile`](#an.semantic.describe.describe_profile)(profile, \*[, kind, ...])  | Per aspect: the method it resolves to, the applicable ones, and why not the rest.                                                     |
| [`format_description`](#an.semantic.describe.format_description)(d, \*[, name])           | The terminal form of [`describe_asset()`](#an.semantic.describe.describe_asset).                                               |

### an.semantic.describe.describe_asset(doc, art=None, , kind='character', aspects=None)

[`describe_profile()`](#an.semantic.describe.describe_profile) of an asset’s derived profile, with the analyser and overrides.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.semantic.describe.describe_profile(profile, , kind=None, aspects=None, declared=None)

Per aspect: the method it resolves to, the applicable ones, and why not the rest.

`declared` is the asset document’s declared facts: an aspect’s request
is read from the field it names (`Aspect.declared_by`: a character’s
`gait`), so the answer is the method the compiler will use.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.semantic.describe.format_description(d, , name='')

The terminal form of [`describe_asset()`](#an.semantic.describe.describe_asset).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
