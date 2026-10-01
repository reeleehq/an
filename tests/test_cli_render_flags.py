"""`an render` reaches the leaf renderer with every flag it advertises.

The CLI calls `an.orchestrate.render_project`, a wrapper that once
re-declared the leaf's parameters and silently fell behind them: from the day
`--supersample` landed, `an render <dir>` raised ``TypeError`` for everyone,
while the CLI test stubbed the wrapper and stayed green (an#98 review). This
test stubs the LEAF, so the wrapper is exercised for real.
"""

from __future__ import annotations

from pathlib import Path


def test_every_cli_render_flag_reaches_the_leaf_renderer(monkeypatch):
    from an import orchestrate, tools

    seen = {}

    def leaf(project_dir, **kw):
        seen.update(kw)
        return Path("out.mp4")

    monkeypatch.setattr(orchestrate, "_render_project", leaf)
    out = tools.render("proj", tts="mac_say", lipsync="rhubarb", parallel="auto", strict_assets=True, supersample=2, pix_fmt="yuv444p", step_hz=12.0, language="fr", capture="canvas")
    assert out.startswith("rendered:")
    # The shot cache (an#242): the CLI hands the leaf its own engine, so it can
    # report which shots were rendered and which reused.
    from an.build import ShotCache

    assert isinstance(seen.pop("incremental"), ShotCache)
    assert seen == {
        "output_name": "main", "tts": "mac_say", "lipsync": "rhubarb", "parallel": "auto",
        "strict_assets": True, "supersample": 2, "pix_fmt": "yuv444p", "step_hz": 12.0, "language": "fr",
        "capture": "canvas", "force_render": False,
        # The CLI prints the render's findings grouped, after it (an#254).
        "echo_warnings": False,
    }
    seen.clear()
    tools.render("proj", force_render=True, no_cache=True)
    assert seen["force_render"] is True and seen["incremental"] is False
    # And the leaf actually accepts every one of them.
    import inspect

    from an.render import render_project

    params = inspect.signature(render_project).parameters
    assert set(seen) <= set(params), sorted(set(seen) - set(params))
