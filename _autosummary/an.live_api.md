# an.live_api

The one switch that says “yes, this run may spend money”.

A key being present is not consent to spend. `ELEVEN_API_KEY` (or
`ANTHROPIC_API_KEY`) is exported by every developer shell that has ever
sourced a profile, and by every unattended agent session started from one — so
“has a key” describes the exact population that must *not* be billed silently.
The federation adopted a rule about this after a real incident (video_gen
decision D-vg-audio-02): a code path that can reach a paid API needs an
**explicit positive opt-in env var in addition to the key**.

[`LIVE_API_ENV_VAR`](#an.live_api.LIVE_API_ENV_VAR) is that signal, and this module is its single
definition. `tests/conftest.py` reads it for the `live_api` marker, and
`examples/character_gallery/build.py` reads it before choosing a paid TTS
provider.

**The perimeter this actually draws.** The rule is about provider
*auto-detection* — code that picks a paid provider because a key happened to be
in the environment. It is not a ban on paid work, and two shipped paths reach
paid APIs without consulting this predicate because the caller named them:
`an iterate` (Anthropic) and the vision verifier’s default judge. If you add a
path that CHOOSES a provider rather than being told one, it belongs here — an example is not a test, but it is the file with the most footfall,
and a clean checkout has a cold audio cache, so every line it speaks is a new
charge.

There is deliberately **one** switch, not one per caller: a second variable
would be a second answer to “may this run spend?”, and the two would drift.

```pycon
>>> LIVE_API_ENV_VAR
'AN_LIVE_API_TESTS'
```

### Module Attributes

| [`LIVE_API_ENV_VAR`](#an.live_api.LIVE_API_ENV_VAR)   | Set this truthy to opt a run in to real, billed API calls.   |
|---------------------------------------------------------------------|--------------------------------------------------------------|
| [`TRUTHY_VALUES`](#an.live_api.TRUTHY_VALUES)      | Accepted spellings of "yes".                                 |
| [`CI_ENV_VAR`](#an.live_api.CI_ENV_VAR)         | Set by every CI provider we care about.                      |

### Functions

| [`live_api_enabled`](#an.live_api.live_api_enabled)([env])   | Whether this run has explicitly opted in to paid API calls.   |
|----------------------------------------------------------------------------|---------------------------------------------------------------|

### an.live_api.CI_ENV_VAR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'CI'*

Set by every CI provider we care about. CI must never spend, whatever else
is configured, because nobody is watching the bill in a CI run.

### an.live_api.LIVE_API_ENV_VAR *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'AN_LIVE_API_TESTS'*

Set this truthy to opt a run in to real, billed API calls.

### an.live_api.TRUTHY_VALUES *: [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= frozenset({'1', 'on', 'true', 'yes'})*

Accepted spellings of “yes”. Anything else — including an empty string, the
shape an unset-but-exported variable takes — is “no”.

### an.live_api.live_api_enabled(env=None)

Whether this run has explicitly opted in to paid API calls.

`env` defaults to the process environment; pass a mapping to ask the
question of a hypothetical one without mutating `os.environ`.

Typed `Mapping`, not `dict`: the default IS `os.environ`, an
`os._Environ` that fails `isinstance(..., dict)`, so a `dict`
annotation was false about the function’s own primary argument and pushed
callers into copying the whole environment to satisfy it.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> live_api_enabled({})
False
>>> live_api_enabled({"ELEVEN_API_KEY": "sk-real-key"})  # a key is not consent
False
>>> live_api_enabled({LIVE_API_ENV_VAR: "1"})
True
>>> live_api_enabled({LIVE_API_ENV_VAR: "1", CI_ENV_VAR: "true"})
False
```
