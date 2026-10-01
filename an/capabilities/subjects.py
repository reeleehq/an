"""The core's two non-asset subjects: the engine (a renderer) and the environment.

Core study §2.13: a requirement can name what the **engine** draws (which shot
kinds it claims, which optional members it implements — previz's rule, "a flag
can never disagree with the code") and what the **environment** has (ffmpeg, a
browser, LaTeX, an API key). Each gets one minimal, real analyser here, owned by
the core and registered on import of :mod:`an.capabilities`:

- ``engine`` — derived from the renderer object's *implemented members*:
  ``engine.render`` (``keys``: the ``Shot.renderer`` values it claims) and one
  ``engine.<member>`` per optional member it implements. When the ``Engine``
  protocol (P3) lands, its optional members join :data:`ENGINE_OPTIONAL_MEMBERS`
  and nothing else changes. A stub whose ``render`` always raises still claims
  its renderer here — the protocol cannot tell yet, and saying so is better
  than a declared flag that could lie. ``space.<name>``: the view spaces it
  lowers (an#257), from a ``view_spaces`` member, else
  :data:`DFLT_ENGINE_VIEW_SPACES`.
- ``environment`` — cheap probes only (``PATH`` lookups, an import spec —
  ``env.manim`` is ``manim`` and ``manimkit`` both importable —, the
  Playwright browser cache, the *presence* of API-key variables — never their
  values). No subprocess, no import of the probed package.

Both analysers take their evidence as ``doc`` so a test can inject it:
``environment_affordances(probe={"which": {...}, "env": {...}})``.

>>> profile = environment_affordances(probe={"which": {"ffmpeg"}, "env": {}, "modules": set(), "browsers": False})
>>> sorted(profile)
['env.ffmpeg']
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Mapping
from typing import Any

from an.capabilities import (
    KEYS_PARAM,
    Analyser,
    register_analyser,
    register_capability,
)

__all__ = [
    "ENGINE_ANALYSER_VERSION",
    "ENGINE_OPTIONAL_MEMBERS",
    "ENVIRONMENT_ANALYSER_VERSION",
    "ENV_TOOLS",
    "ENV_KEYS",
    "ENV_MODULES",
    "engine_affordances",
    "environment_affordances",
]

#: "2": `engine.measure_duration` joined the derivation (an#279).
ENGINE_ANALYSER_VERSION: str = "2"
#: "2": `env.manim` joined the derivation (an#279).
ENVIRONMENT_ANALYSER_VERSION: str = "2"

#: Optional engine members a renderer may implement, each afforded as
#: ``engine.<member>`` when it is a callable attribute of the renderer.
#: ``measure_duration`` is how a whole-shot renderer that OWNS ITS CLOCK (Manim:
#: only its own ``play``/``wait`` calls decide how long a shot runs) says so —
#: the core asks it for the length before laying out the film (an#279).
ENGINE_OPTIONAL_MEMBERS: tuple[str, ...] = (
    "compile",
    "preview",
    "render_frames",
    "seek",
    "measure_duration",
)

#: ``capability: (executables, remedy)`` — afforded when any executable is on PATH.
ENV_TOOLS: dict[str, tuple[tuple[str, ...], str]] = {
    "env.ffmpeg": (
        ("ffmpeg",),
        "install ffmpeg (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Debian)",
    ),
    "env.node": (("node",), "install Node.js (`brew install node`)"),
    "env.latex": (
        ("latex", "pdflatex", "xelatex"),
        "install a TeX distribution (MacTeX / TeX Live) so `latex` is on PATH",
    ),
    "env.rhubarb": (
        ("rhubarb",),
        "install Rhubarb Lip Sync (`brew install rhubarb-lipsync`)",
    ),
}

#: ``capability: (environment variables, remedy)`` — afforded when any is set.
ENV_KEYS: dict[str, tuple[tuple[str, ...], str]] = {
    "env.key.anthropic": (
        ("ANTHROPIC_API_KEY",),
        "set ANTHROPIC_API_KEY (needed by `an iterate` and the vision verifier)",
    ),
    "env.key.elevenlabs": (
        ("ELEVEN_API_KEY", "ELEVENLABS_API_KEY"),
        "set ELEVEN_API_KEY (needed by the ElevenLabs voices)",
    ),
}

#: ``capability: (python modules, remedy)`` — afforded when EVERY module is
#: importable (an import spec only: the module is never imported to find out).
ENV_MODULES: dict[str, tuple[tuple[str, ...], str]] = {
    "env.manim": (
        ("manim", "manimkit"),
        "pip install 'an[manim]' (Manim Community Edition and manimkit; on Linux "
        "first `apt install libcairo2-dev libpango1.0-dev`)",
    ),
}

ENV_BROWSER = register_capability(
    "env.browser",
    description="Playwright with a Chromium build, which the stage engine renders in",
    remedy="pip install 'an[cutout]' && playwright install chromium",
    subject="environment",
)
for _name, (_exes, _remedy) in ENV_TOOLS.items():
    register_capability(
        _name,
        description=f"`{_exes[0]}` is on PATH",
        remedy=_remedy,
        subject="environment",
    )
for _name, (_modules, _remedy) in ENV_MODULES.items():
    register_capability(
        _name,
        description=f"the {', '.join(_modules)} Python package(s) are importable",
        remedy=_remedy,
        subject="environment",
    )
for _name, (_vars, _remedy) in ENV_KEYS.items():
    register_capability(
        _name,
        description=f"the {_vars[0]} environment variable is set (its value is never read)",
        remedy=_remedy,
        subject="environment",
    )
ENGINE_RENDER = register_capability(
    "engine.render",
    description="the engine renders shots (keys: the Shot.renderer values it claims)",
    remedy="register a renderer that claims the shot's `renderer` (an.adapters.register_renderer)",
    subject="engine",
)
for _member in ENGINE_OPTIONAL_MEMBERS:
    register_capability(
        f"engine.{_member}",
        description=f"the engine implements the optional `{_member}` member",
        remedy=f"use an engine that implements `{_member}`",
        subject="engine",
    )


def _real_probe() -> dict[str, Any]:
    from an.check_requirements import playwright_browser_dirs

    exes = {e for exes, _ in ENV_TOOLS.values() for e in exes}
    browsers = any(
        name.startswith("chromium")
        for directory in playwright_browser_dirs()
        if os.path.isdir(directory)
        for name in os.listdir(directory)
    )
    return {
        "which": {e for e in exes if shutil.which(e)},
        "env": {v for vs, _ in ENV_KEYS.values() for v in vs if os.environ.get(v)},
        "modules": {
            m
            for m in ("playwright", *(m for ms, _ in ENV_MODULES.values() for m in ms))
            if importlib.util.find_spec(m) is not None
        },
        "browsers": browsers,
    }


def _derive_environment(
    doc: Mapping[str, Any] | None, art: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    probe = dict(doc) if doc else _real_probe()
    out: dict[str, dict[str, Any]] = {}
    for name, (exes, _) in ENV_TOOLS.items():
        found = [e for e in exes if e in probe.get("which", ())]
        if found:
            out[name] = {KEYS_PARAM: found}
    for name, (variables, _) in ENV_KEYS.items():
        if any(v in probe.get("env", ()) for v in variables):
            out[name] = {}
    for name, (modules, _) in ENV_MODULES.items():
        if all(m in probe.get("modules", ()) for m in modules):
            out[name] = {}
    if "playwright" in probe.get("modules", ()) and probe.get("browsers"):
        out[ENV_BROWSER.name] = {}
    return out


#: The view spaces an engine lowers (an#257), for a renderer that does not
#: declare them itself in a ``view_spaces`` member. A stopgap with one entry:
#: the stage engine re-renders a framing2d view (its ``stage.camera`` property
#: space). When P3's ``Engine`` protocol gives engines a ``view_spaces`` member,
#: the stage engine declares it and this table empties.
DFLT_ENGINE_VIEW_SPACES: dict[str, tuple[str, ...]] = {"cutout": ("framing2d",)}
#: The capability prefix of a view space an engine lowers (``space.framing2d``).
VIEW_SPACE_PREFIX: str = "space."


def _derive_engine(renderer: Any, art: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    claims = tuple(getattr(renderer, "supported_renderers", ()) or ())
    if callable(getattr(renderer, "render", None)) and claims:
        out[ENGINE_RENDER.name] = {KEYS_PARAM: list(claims)}
    for member in ENGINE_OPTIONAL_MEMBERS:
        if callable(getattr(renderer, member, None)):
            out[f"engine.{member}"] = {}
    spaces = getattr(renderer, "view_spaces", None)
    if spaces is None:
        spaces = DFLT_ENGINE_VIEW_SPACES.get(getattr(renderer, "name", ""), ())
    for space in spaces:
        out[VIEW_SPACE_PREFIX + space] = {}
    return out


register_analyser(
    Analyser(
        "environment",
        ENVIRONMENT_ANALYSER_VERSION,
        _derive_environment,
        subject="environment",
    )
)
register_analyser(
    Analyser("engine", ENGINE_ANALYSER_VERSION, _derive_engine, subject="engine")
)


def environment_affordances(
    *, probe: Mapping[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    """What this machine affords: tools on PATH, a browser, API keys set.

    ``probe`` injects the evidence (``which``, ``env``, ``modules``,
    ``browsers``); ``None`` probes the real machine (cheap: no subprocess).
    """
    return _derive_environment(probe, {})


def engine_affordances(renderer: Any) -> dict[str, dict[str, Any]]:
    """What a renderer (or a registered renderer's name) affords, from its members.

    >>> class Fake:
    ...     supported_renderers = ("toy",)
    ...     def render(self, shot, ctx): ...
    ...     def preview(self, shot): ...
    >>> engine_affordances(Fake())
    {'engine.render': {'keys': ['toy']}, 'engine.preview': {}}
    """
    if isinstance(renderer, str):
        from an.adapters import get_renderer

        renderer = get_renderer(renderer)
    return _derive_engine(renderer, {})
