# an.capabilities.subjects

The core’s two non-asset subjects: the engine (a renderer) and the environment.

Core study §2.13: a requirement can name what the **engine** draws (which shot
kinds it claims, which optional members it implements — previz’s rule, “a flag
can never disagree with the code”) and what the **environment** has (ffmpeg, a
browser, LaTeX, an API key). Each gets one minimal, real analyser here, owned by
the core and registered on import of [`an.capabilities`](an.capabilities.html.md#module-an.capabilities):

- `engine` — derived from the renderer object’s *implemented members*:
  `engine.render` (`keys`: the `Shot.renderer` values it claims) and one
  `engine.<member>` per optional member it implements. When the `Engine`
  protocol (P3) lands, its optional members join [`ENGINE_OPTIONAL_MEMBERS`](#an.capabilities.subjects.ENGINE_OPTIONAL_MEMBERS)
  and nothing else changes. A stub whose `render` always raises still claims
  its renderer here — the protocol cannot tell yet, and saying so is better
  than a declared flag that could lie. `space.<name>`: the view spaces it
  lowers (an#257), from a `view_spaces` member, else
  `DFLT_ENGINE_VIEW_SPACES`.
- `environment` — cheap probes only (`PATH` lookups, an import spec, the
  Playwright browser cache, the *presence* of API-key variables — never their
  values). No subprocess, no import of the probed package.

Both analysers take their evidence as `doc` so a test can inject it:
`environment_affordances(probe={"which": {...}, "env": {...}})`.

```pycon
>>> profile = environment_affordances(probe={"which": {"ffmpeg"}, "env": {}, "modules": set(), "browsers": False})
>>> sorted(profile)
['env.ffmpeg']
```

### Module Attributes

| [`ENGINE_OPTIONAL_MEMBERS`](#an.capabilities.subjects.ENGINE_OPTIONAL_MEMBERS)   | Optional engine members a renderer may implement, each afforded as `engine.<member>` when it is a callable attribute of the renderer.   |
|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| [`ENV_TOOLS`](#an.capabilities.subjects.ENV_TOOLS)                 | `capability: (executables, remedy)` — afforded when any executable is on PATH.                                                          |
| [`ENV_KEYS`](#an.capabilities.subjects.ENV_KEYS)                  | `capability: (environment variables, remedy)` — afforded when any is set.                                                               |

### Functions

| [`engine_affordances`](#an.capabilities.subjects.engine_affordances)(renderer)         | What a renderer (or a registered renderer's name) affords, from its members.   |
|---------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`environment_affordances`](#an.capabilities.subjects.environment_affordances)(\*[, probe]) | What this machine affords: tools on PATH, a browser, API keys set.             |

### an.capabilities.subjects.ENGINE_OPTIONAL_MEMBERS *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ('compile', 'preview', 'render_frames', 'seek')*

Optional engine members a renderer may implement, each afforded as
`engine.<member>` when it is a callable attribute of the renderer.

### an.capabilities.subjects.ENV_KEYS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...], [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'env.key.anthropic': (('ANTHROPIC_API_KEY',), 'set ANTHROPIC_API_KEY (needed by \`an iterate\` and the vision verifier)'), 'env.key.elevenlabs': (('ELEVEN_API_KEY', 'ELEVENLABS_API_KEY'), 'set ELEVEN_API_KEY (needed by the ElevenLabs voices)')}*

`capability: (environment variables, remedy)` — afforded when any is set.

### an.capabilities.subjects.ENV_TOOLS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...], [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]* *= {'env.ffmpeg': (('ffmpeg',), 'install ffmpeg (\`brew install ffmpeg\` on macOS, \`apt install ffmpeg\` on Debian)'), 'env.latex': (('latex', 'pdflatex', 'xelatex'), 'install a TeX distribution (MacTeX / TeX Live) so \`latex\` is on PATH'), 'env.node': (('node',), 'install Node.js (\`brew install node\`)'), 'env.rhubarb': (('rhubarb',), 'install Rhubarb Lip Sync (\`brew install rhubarb-lipsync\`)')}*

`capability: (executables, remedy)` — afforded when any executable is on PATH.

### an.capabilities.subjects.engine_affordances(renderer)

What a renderer (or a registered renderer’s name) affords, from its members.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]

```pycon
>>> class Fake:
...     supported_renderers = ("toy",)
...     def render(self, shot, ctx): ...
...     def preview(self, shot): ...
>>> engine_affordances(Fake())
{'engine.render': {'keys': ['toy']}, 'engine.preview': {}}
```

### an.capabilities.subjects.environment_affordances(, probe=None)

What this machine affords: tools on PATH, a browser, API keys set.

`probe` injects the evidence (`which`, `env`, `modules`,
`browsers`); `None` probes the real machine (cheap: no subprocess).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]]
