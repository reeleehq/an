# an.semantic.matcher

The three queries and the policy (ADR 0002 decision 4): `applicable`, `why_not`, `resolve`.

All three are calls to the one matcher, [`an.capabilities.missing()`](an.capabilities.html.md#an.capabilities.missing), over
the methods the vocabulary registry holds for an aspect.

- [`applicable()`](#an.semantic.matcher.applicable) lists the methods of an aspect that apply to the subjects
  (the default chain’s order first).
- [`why_not()`](#an.semantic.matcher.why_not) lists what a method is missing, each term with its remedy —
  the method’s own, else the capability’s.
- [`resolve()`](#an.semantic.matcher.resolve) picks one: the author’s request if it applies; else the first
  applicable choice of the policy (shot before style, `Policy.layered()`);
  else the aspect’s default chain. Every departure from what was asked is a
  [`Substitution`](an.capabilities.html.md#an.capabilities.Substitution) on the result: `missing` when what
  > was asked does not apply, `policy` when a policy chose against the chain
  > (information, never fatal), `noop` when the aspect does not apply at all.

```pycon
>>> from an.semantic.entries import Aspect, Method
>>> from an.semantic.registry import register_aspect, register_entry, drop_owner
>>> _ = register_entry(Method("demo.legs", aspect="demo_move", requires=("limbs.legs",)), owner="demo")
>>> _ = register_entry(Method("demo.slide", aspect="demo_move"), owner="demo")
>>> _ = register_aspect(Aspect("demo_move", chain=("demo.legs", "demo.slide")), owner="demo")
>>> [m.id for m in applicable("demo_move", {})]
['demo.slide']
>>> [w.term for w in why_not("demo.legs", {})]
['limbs.legs']
>>> r = resolve("demo_move", {}, requested="demo.legs", entity="blob")
>>> r.method.id, r.substitution.reason
('demo.slide', 'missing')
>>> drop_owner("demo")
```

### Functions

| [`applicable`](#an.semantic.matcher.applicable)(aspect_name, subjects)                | The methods of `aspect_name` that apply to `subjects`, the default chain's order first.   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`resolve`](#an.semantic.matcher.resolve)(aspect_name, subjects[, requested, ...]) | Choose the method that realises `aspect_name` on `subjects`.                              |
| [`why_not`](#an.semantic.matcher.why_not)(method, subjects)                        | What `method` is missing on `subjects`, each with its remedy (empty: it applies).         |

### Classes

| [`Missing`](#an.semantic.matcher.Missing)(term, remedy)                           | One unmet requirement term and what would meet it.                                                                       |
|--------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| [`Resolution`](#an.semantic.matcher.Resolution)(aspect, method[, args, source, ...]) | What [`resolve()`](#an.semantic.matcher.resolve) chose: the method, its args, where the choice came from. |

### *class* an.semantic.matcher.Missing(term, remedy)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One unmet requirement term and what would meet it.

### *class* an.semantic.matcher.Resolution(aspect, method, args=<factory>, source='chain', substitution=None, considered=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What [`resolve()`](#an.semantic.matcher.resolve) chose: the method, its args, where the choice came from.

`source` is `request`, `policy`, `chain` or `noop`;
`substitution` is the record when the choice departs from what was asked
(`None` when it did not); `considered` is the trail of methods tried
before it, each with what it was missing.

### an.semantic.matcher.applicable(aspect_name, subjects)

The methods of `aspect_name` that apply to `subjects`, the default chain’s order first.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Method`](an.semantic.html.md#an.semantic.Method), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### an.semantic.matcher.resolve(aspect_name, subjects, requested=None, , policy=None, entity='', entity_kind=None)

Choose the method that realises `aspect_name` on `subjects`.

`requested` is the author’s explicit choice (a method id, its spelling
in the aspect — `"hem"` for locomotion —, or `{method, args, version}`);
`policy` the layered shot/style policy; `entity_kind` the asset’s kind,
checked against the aspect’s `applies_to`. Never raises for a method that
does not apply: it falls back and records why.

* **Return type:**
  [`Resolution`](#an.semantic.matcher.Resolution)

### an.semantic.matcher.why_not(method, subjects)

What `method` is missing on `subjects`, each with its remedy (empty: it applies).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Missing`](#an.semantic.matcher.Missing), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]
