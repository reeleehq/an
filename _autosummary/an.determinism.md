# an.determinism

The determinism perimeter: what must stay true for a render to be reproducible.

`an` renders by driving a headless Chromium and screenshotting a WebGL canvas.
Two classes of thing can make that non-reproducible, and they need different
treatment:

**Pinned inputs** — the rasteriser, the browser build, the encoder. Those are
*settings*, and they are pinned unconditionally in
[`an.stage.render`](an.stage.render.md#module-an.stage.render) (an#31, an#34). Nothing here.

**Latent randomness** — machinery that is deterministic today by accident.
The vendored PixiJS carries `Math.random`, `Date.now`, `performance.now` and
`requestAnimationFrame` calls, and `NoiseFilter`’s default seed is
`Math.random()`. All of it is dormant because the runtime creates the app with
`autoStart: false` and drives it with explicit `app.render()` calls, and
because nothing attaches a filter. Neither fact is written down anywhere that
would go red if it stopped being true. That is what this module watches.

The division of labour is deliberate: `runtime.js`’s `anDeterminismReport`
**observes** and this module **judges**. So the rule is a pure function of a
plain dict — testable with no browser, no ffmpeg and no render — and changing
the rule is a Python diff rather than a runtime re-stage.

Enforcement is **on by default**, which is a deliberate deviation from the
issue’s `AN_DETERMINISTIC=1` framing and follows the same reasoning an#31
used for the launch flags: a property that only holds when someone remembers to
export a variable is not a property of the system. An assertion nobody runs is
worse than no assertion, because the perimeter reads as guarded. The escape
hatch is the same variable read the other way — `AN_DETERMINISTIC=0`.

```pycon
>>> capture_violations({"page": "/index.html", "stage_filter_count": 0,
...                     "filtered_node_paths": [], "shared_ticker_started": False,
...                     "auto_start": False})
[]
```

### Module Attributes

| [`AN_DETERMINISTIC_ENV_VAR`](#an.determinism.AN_DETERMINISTIC_ENV_VAR)   | Read as an OFF switch, not an on switch — see the module docstring.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`CAPTURE_PAGE`](#an.determinism.CAPTURE_PAGE)               | The page the capture path must be on.                                 |

### Functions

| [`capture_violations`](#an.determinism.capture_violations)(report, \*[, capture_page])   | Return one sentence per breach of the perimeter; empty means clean.       |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`determinism_enforced`](#an.determinism.determinism_enforced)()                           | Whether to refuse a render whose determinism perimeter has been breached. |

### an.determinism.AN_DETERMINISTIC_ENV_VAR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'AN_DETERMINISTIC'*

Read as an OFF switch, not an on switch — see the module docstring.

### an.determinism.CAPTURE_PAGE *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'index.html'*

The page the capture path must be on. `render.py` stages `preview.html`
into every work dir and it carries seven clock calls, so “which page did the
browser actually load” is a real question with a wrong answer available.

### an.determinism.capture_violations(report, , capture_page='index.html')

Return one sentence per breach of the perimeter; empty means clean.

Each sentence says what was observed, why it makes frames non-reproducible,
and what to do about it — because the reader of this message is the person
who just added the thing, and “determinism violation” alone tells them
nothing.

A missing key is reported rather than defaulted: a report that does not
carry a field cannot testify that the field is fine, and silently reading
`report.get("shared_ticker_started", False)` would turn a stale runtime
into a clean bill of health.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> capture_violations({})[0].startswith("the determinism report is missing")
True
```

### an.determinism.determinism_enforced()

Whether to refuse a render whose determinism perimeter has been breached.

True unless [`AN_DETERMINISTIC_ENV_VAR`](#an.determinism.AN_DETERMINISTIC_ENV_VAR) is explicitly falsey.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> import os
>>> os.environ.pop("AN_DETERMINISTIC", None) and None
>>> determinism_enforced()
True
>>> os.environ["AN_DETERMINISTIC"] = "0"
>>> determinism_enforced()
False
>>> del os.environ["AN_DETERMINISTIC"]
```
