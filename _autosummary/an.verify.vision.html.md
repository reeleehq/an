# an.verify.vision

VisionLMVerifier — Claude vision looks at sampled frames and reports issues.

**Opt-in, not default.** `an.orchestrate.orchestrate`’s default verifier chain
is `[LayoutLintVerifier(), MediaQualityVerifier()]` and this verifier is
deliberately not in it: it costs money and its input is a rendered mp4. The
lazy `anthropic` import and the key check therefore skip *cleanly*, so a caller
without the `vision` extra gets an informational Finding rather than an
`ImportError`. (The docstring here previously claimed the opposite — that the
skips existed “so the orchestrator can keep this verifier in its default
chain”. Nothing in `an/` has ever put it in one.)

**Not configured is a skip. Configured and broken is a failure.** That
distinction is the whole of an#39. Every failure path used to add an `info`
Finding and return, and `VerificationReport.add` flips `passed` only on
`"error"` — so a dead model id, a 500, a refusal and an unparseable reply all
came back byte-identical to a clean bill of health. A verifier that reports
success when it failed to run is worse than no verifier, because it launders an
absence of evidence into evidence of absence.

So the paid call lives behind an injectable seam, [`judge_frames()`](#an.verify.vision.judge_frames), which
takes **frame bytes** (not paths — the real frames live in a
`TemporaryDirectory`, so a cache key over paths would miss 100% of the time)
and returns the model’s **raw text** (so `_parse_issues` stays outside any
recording and parser fixes are testable against it for free). A judge that
cannot answer raises [`VisionJudgeError`](#an.verify.vision.VisionJudgeError); a cassette that has no
recording for a call raises [`CassetteMiss`](#an.verify.vision.CassetteMiss), which derives from
**\`BaseException\`** because every other kind is swallowed twice on the way out
— once by this module’s own handler and once by `orchestrate`’s broad
post-render `except Exception`, which guards every verifier and must stay
broad.

Cost: one Anthropic call carrying `frame_count` base64 PNGs plus a short
prompt. Roughly $0.005 with Haiku.

### Module Attributes

| [`FAILURE_SEVERITY`](#an.verify.vision.FAILURE_SEVERITY)   | Severity for "configured, called, no verdict" — a failed call, or a reply that carried no verdict.   |
|---------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|

### Functions

| [`judge_envelope`](#an.verify.vision.judge_envelope)(frames, \*[, prompt, ...])        | Call the vision model and return a recordable envelope.                                     |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`judge_frames`](#an.verify.vision.judge_frames)(frames, \*[, prompt, ...])          | The paid seam: frame bytes in, the model's raw text reply out.                              |
| [`judge_key`](#an.verify.vision.judge_key)(\*args, \*\*kwargs)                    | The cache key for one [`judge_frames()`](#an.verify.vision.judge_frames) call. |
| [`judge_legibility`](#an.verify.vision.judge_legibility)(frames, text, \*[, judge, ...]) | Score a dense in-line frame strip for lip-sync legibility (an#97).                          |
| [`legibility_prompt`](#an.verify.vision.legibility_prompt)(text)                          | The legibility prompt for one line.                                                         |

### Classes

| [`VisionLMVerifier`](#an.verify.vision.VisionLMVerifier)(\*[, model, frame_count, ...])   | Claude vision Verifier (skip-if-missing-deps).   |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------|

### Exceptions

| [`CassetteMiss`](#an.verify.vision.CassetteMiss)     | A recorded reply was asked for and there is none.              |
|-------------------------------------------------------------------|----------------------------------------------------------------|
| [`VisionJudgeError`](#an.verify.vision.VisionJudgeError) | The judge was configured, was called, and produced no verdict. |

### *exception* an.verify.vision.CassetteMiss

Bases: [`BaseException`](https://docs.python.org/3/builtins/exceptions.html#BaseException)

A recorded reply was asked for and there is none.

Derived from `BaseException` rather than `Exception`, deliberately and
for a measured reason: an `Exception` raised where the API call sits is
caught by this module’s own handler AND by `an.orchestrate`’s post-render
`except Exception`, which guards every verifier and must stay broad. Both
of them report and continue, so a test asserting “this run did not spend”
would pass having verified nothing at all.

Same reasoning, and the same shape, as `tests/conftest.py`’s
`OutboundNetworkAttempt` — whose own docstring names “the verifiers’ broad
handlers” as the reason.

### an.verify.vision.FAILURE_SEVERITY *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'warning'*

Severity for “configured, called, no verdict” — a failed call, or a reply
that carried no verdict.

`warning`, not `error`: a transient 529 must not fail a whole render. And
not `info`, which is the NOT-CONFIGURED severity — reusing it for
“configured and broken” is exactly what made this verifier invisible. Any
non-`info` Finding makes a dead verifier show up in the report.

Set it to `"error"` if a refusal should fail the render; that is a policy
choice, and it is one constant.

### *exception* an.verify.vision.VisionJudgeError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The judge was configured, was called, and produced no verdict.

An `an`-owned type on purpose. Narrowing the catch site to
`anthropic.APIError` looks tighter and is not:
`issubclass(anthropic.NotFoundError, anthropic.APIError)` is True, so a
dead model id would still be swallowed into a pass — and it would put a
vendor class at a catch site in this package’s own control flow.

### *class* an.verify.vision.VisionLMVerifier(, model='claude-haiku-4-5-20251001', frame_count=4, max_tokens=800, api_key=None, judge=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Claude vision Verifier (skip-if-missing-deps).

#### judge

Injected, per “no globals, no service locators” — and because
injection is what makes record-vs-replay drift impossible: the
recorded and replayed paths are the same call through the same
object, differing only in what the store returns.

### an.verify.vision.judge_envelope(frames, \*, prompt='You are reviewing frames from a short animated cartoon. The character\\\\nart is intentionally simple (placeholder geometry: ellipse heads, rect\\\\ntorsos/limbs, curved bezier mouths, eyes drawn as white-sclera + dark\\\\npupils). DO NOT comment on the simplicity of the art itself — that is by\\\\ndesign. DO comment on: \\\\n\\\\n- Characters that are clipped off-screen or overlap badly.\\\\n- Faces that are missing parts (no eyes, mouth not visible, head occluded).\\\\n- Motion that looks broken (limbs detached, character flying off-canvas).\\\\n- Mouth shape that obviously doesn\\\\'t match active speech (e.g. closed lips\\\\n  during a long word).\\\\n- Background obscuring a character.\\\\n\\\\nReply in JSON only, with this shape: \\\\n\\\\n{\\\\n  "issues": [\\\\n    {"severity": "warning"|"error", "where": '<short location hint>', "what": "<one sentence>"}\\\\n  ]\\\\n}\\\\n\\\\nIf everything looks fine, return \`\`{"issues": []}\`\`.\\\\n', model='claude-haiku-4-5-20251001', max_tokens=800, api_key=None)

Call the vision model and return a recordable envelope.

Memoized one level *in* from [`judge_frames()`](#an.verify.vision.judge_frames) because a memoizer hands
the store only `(key, return_value)` — so a seam returning a bare `str`
can record nothing beside the reply, and the provenance that makes a
cassette auditable would be unwritable.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### an.verify.vision.judge_frames(frames, \*, prompt='You are reviewing frames from a short animated cartoon. The character\\\\nart is intentionally simple (placeholder geometry: ellipse heads, rect\\\\ntorsos/limbs, curved bezier mouths, eyes drawn as white-sclera + dark\\\\npupils). DO NOT comment on the simplicity of the art itself — that is by\\\\ndesign. DO comment on: \\\\n\\\\n- Characters that are clipped off-screen or overlap badly.\\\\n- Faces that are missing parts (no eyes, mouth not visible, head occluded).\\\\n- Motion that looks broken (limbs detached, character flying off-canvas).\\\\n- Mouth shape that obviously doesn\\\\'t match active speech (e.g. closed lips\\\\n  during a long word).\\\\n- Background obscuring a character.\\\\n\\\\nReply in JSON only, with this shape: \\\\n\\\\n{\\\\n  "issues": [\\\\n    {"severity": "warning"|"error", "where": '<short location hint>', "what": "<one sentence>"}\\\\n  ]\\\\n}\\\\n\\\\nIf everything looks fine, return \`\`{"issues": []}\`\`.\\\\n', model='claude-haiku-4-5-20251001', max_tokens=800, api_key=None)

The paid seam: frame bytes in, the model’s raw text reply out.

`bytes` rather than `Path` because the real frames live in a
`TemporaryDirectory`, so a key over paths hashes a fresh random string and
misses every time. **Raw text** rather than parsed findings because that
keeps `_parse_issues` outside any recording — a parser fix is then testable
against the recording for free, and record-vs-replay drift is impossible.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.verify.vision.judge_key(\*args, \*\*kwargs)

The cache key for one [`judge_frames()`](#an.verify.vision.judge_frames) call.

Derived from the seam’s **signature**, not from a hand-written allowlist.
An allowlist sets the default to *exclude*, which means a parameter added
later collides with the base key and the recording is served forever for a
request that changed. A false miss is red CI; a false hit is silent and
unrecoverable, so the default has to be *include*.

`apply_defaults()` matters too: without it `judge_frames(frames)` and
the fully-spelled call are two different keys for one request.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> k = judge_key([b"a"], model="m", max_tokens=1, prompt="p")
>>> k == judge_key([b"a"], model="m", max_tokens=1, prompt="p", api_key="secret")
True
>>> k == judge_key([b"a"], model="m", max_tokens=1, prompt="  p  ")
True
>>> k == judge_key([b"b"], model="m", max_tokens=1, prompt="p")
False
```

### an.verify.vision.judge_legibility(frames, text, , judge=None, model='claude-haiku-4-5-20251001', max_tokens=800, api_key=None)

Score a dense in-line frame strip for lip-sync legibility (an#97).

`judge` is the `judge_frames`-shaped seam — the cassette-backed one in
tests, the paid one otherwise. Parsing stays outside the recording.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### an.verify.vision.legibility_prompt(text)

The legibility prompt for one line. The text is part of the key, so a
different line is a different recording.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
