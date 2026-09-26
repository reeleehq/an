# an.stores.decisions

Decision log — append-only JSONL of agent decisions and user approvals.

Each call to `append` writes one line to `.an/decisions.jsonl`. Reading
yields decisions in order. The store exposes a `MutableMapping` interface keyed
by integer index (as a string) for uniformity with the other stores, plus an
`append` convenience method.

### Classes

| [`DecisionLogStore`](#an.stores.decisions.DecisionLogStore)(log_path)   | Append-only JSONL log keyed by ordinal index (as string).   |
|-------------------------------------------------------------------------------|-------------------------------------------------------------|

### *class* an.stores.decisions.DecisionLogStore(log_path)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

Append-only JSONL log keyed by ordinal index (as string).

Mutating in-place (`__setitem__`, `__delitem__`) is intentionally
forbidden; the log is append-only by design.

```pycon
>>> import tempfile, os
>>> with tempfile.TemporaryDirectory() as d:
...     log = DecisionLogStore(os.path.join(d, 'decisions.jsonl'))
...     _ = log.append(kind='test', body={'x': 1})
...     _ = log.append(kind='test', body={'x': 2})
...     entries = list(log.values())
...     entries[0]['body']['x'], entries[1]['body']['x']
(1, 2)
```

#### append(, kind, body, \*\*extra)

Append one decision; returns its ordinal index.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
