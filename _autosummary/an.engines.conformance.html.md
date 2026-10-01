# an.engines.conformance

Conformance of a TIME-driven engine against the timing kernel’s golden vectors.

A time-driven engine evaluates the compiled channels itself (core study §2.7):
`runtime.js` does, in a browser. Its pictures are only comparable with any
other engine’s if the STATE it evaluated at `t` is the kernel’s, so a
time-driven session exposes `state(t)` – the read-back – and this module
holds it to `an/data/timing/timing_vectors.json`, the contract `an.timing`
and `previz` both assert (ADR 0001 decision 10): numbers within the file’s
tolerance, everything else exact, every sample of every case of the session’s
property space.

The engine supplies how to load a vector’s document; the check is the core’s.

```pycon
>>> cases = vector_cases(space="stage.node")
>>> len(cases) >= 10 and all(c["space"] == "stage.node" for c in cases)
True
>>> readback_mismatches(lambda t: {}, {"name": "n", "samples": [{"t": 0.0, "state": {}}]})
[]
```

### Module Attributes

| [`VECTORS_RESOURCE`](#an.engines.conformance.VECTORS_RESOURCE)   | `(package, path inside it)` for [`importlib.resources`](https://docs.python.org/3/library/importlib.resources.html#module-importlib.resources).   |
|---------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|

### Functions

| [`as_contract_state`](#an.engines.conformance.as_contract_state)(state)             | A state in the vectors' spelling: `"target:property"` keys.                                                             |
|---------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`conformance_report`](#an.engines.conformance.conformance_report)(open_case, cases) | Every mismatch over `cases`; `open_case(case)` is a context manager yielding a session loaded with the case's document. |
| [`readback_mismatches`](#an.engines.conformance.readback_mismatches)(state_at, case)  | `(case, t, expected, got)` for every sample whose read-back differs.                                                    |
| [`vector_cases`](#an.engines.conformance.vector_cases)(\*[, space])            | The golden cases, optionally only those of one property space.                                                          |

### an.engines.conformance.VECTORS_RESOURCE *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= ('an.data', 'timing/timing_vectors.json')*

`(package, path inside it)` for [`importlib.resources`](https://docs.python.org/3/library/importlib.resources.html#module-importlib.resources).

* **Type:**
  Where the vectors ship

### an.engines.conformance.as_contract_state(state)

A state in the vectors’ spelling: `"target:property"` keys.

Accepts the kernel’s pose keys (`(target, property)` tuples) and the
runtime’s (`"target::property"`).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

```pycon
>>> as_contract_state({("a", "x"): 1.0, "b::y": 2})
{'a:x': 1.0, 'b:y': 2}
```

### an.engines.conformance.conformance_report(open_case, cases)

Every mismatch over `cases`; `open_case(case)` is a context manager
yielding a session loaded with the case’s document.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.engines.conformance.readback_mismatches(state_at, case)

`(case, t, expected, got)` for every sample whose read-back differs.

`state_at` is a loaded session’s `state` (or anything with its shape).
Compared with the contract’s own rule ([`an.timing.contract.values_close()`](an.timing.contract.html.md#an.timing.contract.values_close)).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

### an.engines.conformance.vector_cases(, space=None)

The golden cases, optionally only those of one property space.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
