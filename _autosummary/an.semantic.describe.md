# an.semantic.describe

Describe an asset: what it affords, and per aspect what applies and what is missing.

ADR 0002’s first slice ends with `an character capabilities <name>`: the
affordances (with the declared overrides the derivation used), and per aspect
the method the default chain picks, the methods that apply, and the
`why_not` of the rest with their remedies. [`describe_asset()`](#an.semantic.describe.describe_asset) is that
answer as data (the MCP surface’s describe-an-asset query returns it);
[`format_description()`](#an.semantic.describe.format_description) is its terminal form. Core code: it names no rig.
Given a `policy` (a style’s, an#348), each aspect also says what it
resolves to under it (`under_policy`), by the same precedence the compiler
uses ([`an.semantic.resolve()`](an.semantic.md#an.semantic.resolve)).

```pycon
>>> from an.semantic.entries import Aspect, Method
>>> from an.semantic.registry import register_aspect, register_entry, drop_owner
>>> _ = register_entry(Method("demo.fly", aspect="demo_travel", requires=("limbs.wings",)), owner="demo")
>>> _ = register_entry(Method("demo.float", aspect="demo_travel"), owner="demo")
>>> _ = register_aspect(Aspect("demo_travel", chain=("demo.fly", "demo.float")), owner="demo")
>>> d = describe_profile({}, aspects=("demo_travel",))
>>> d["aspects"]["demo_travel"]["default"], list(d["aspects"]["demo_travel"]["not_applicable"])
('demo.float', ['demo.fly'])
>>> d = describe_profile({}, aspects=("demo_travel",), policy={"demo_travel": ["demo.fly", "demo.float"]})
>>> u = d["aspects"]["demo_travel"]["under_policy"]
>>> u["method"], u["source"], u["skipped"]
('demo.float', 'policy', [{'method': 'demo.fly', 'missing': ['limbs.wings']}])
>>> drop_owner("demo")
```

### Functions

| [`describe_asset`](#an.semantic.describe.describe_asset)(doc[, art, kind, aspects, policy])   | [`describe_profile()`](#an.semantic.describe.describe_profile) of an asset's derived profile, with the analyser and overrides; `policy` as [`describe_profile()`](#an.semantic.describe.describe_profile)'s.   |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`describe_profile`](#an.semantic.describe.describe_profile)(profile, \*[, kind, ...])          | Per aspect: the method it resolves to, the applicable ones, and why not the rest.                                                                                                                                        |
| [`format_description`](#an.semantic.describe.format_description)(d, \*[, name, policy_label])     | The terminal form of [`describe_asset()`](#an.semantic.describe.describe_asset); `policy_label` names the policy an `under_policy` answer was resolved under (a style's name).                                    |

### an.semantic.describe.describe_asset(doc, art=None, , kind='character', aspects=None, policy=None)

[`describe_profile()`](#an.semantic.describe.describe_profile) of an asset’s derived profile, with the analyser and
overrides; `policy` as [`describe_profile()`](#an.semantic.describe.describe_profile)’s.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.semantic.describe.describe_profile(profile, , kind=None, aspects=None, declared=None, policy=None)

Per aspect: the method it resolves to, the applicable ones, and why not the rest.

`declared` is the asset document’s declared facts: an aspect’s
declaration is read from the field it names (`Aspect.declared_by`: a
character’s `gait`), so the answer is the method the compiler will use.
`policy` (a style’s, anything `an.semantic.Policy.of()` reads) adds
`under_policy` per aspect: the method, where the choice came from, what
that method requires (a genre may say when it holds), and any
substitution or skipped policy entries.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

### an.semantic.describe.format_description(d, , name='', policy_label='the policy')

The terminal form of [`describe_asset()`](#an.semantic.describe.describe_asset); `policy_label` names the
policy an `under_policy` answer was resolved under (a style’s name).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
