"""What a cut-out shot render reads: the keyer behind its shot-cache key (ADR 0004).

The cut-out render is a pure function of these, and of nothing else:

- **the compiled document** — :func:`compile_shot` with exactly the arguments
  `CutoutRenderer.render` passes; digested as ``scene_contract_sha256``, so the
  cache key and the bench's contract hash agree about what "the same document"
  means while staying two different things (the key covers more);
- **the bytes of every texture it stages** — SVG included. Raster art already
  carries its digest in the document (an#211); SVG art is addressed by path,
  so an SVG edited in place would otherwise leave the key unchanged. The
  digests go into the KEY only: the wire shape and ``scene_contract_sha256``
  do not move (ADR 0004 decision 2);
- **the version of every easing the document names** (an#239 item 1): a
  compiled keyframe carries a bare name, so a v2 of a curve would change
  pixels under an unchanged document;
- **the dialogue audio it muxes** — each line's ``audio_ref``,
  ``viseme_ref``, start and the digest of the bytes the store returns for it,
  and the picture's length the mux cuts to;
- **the JS runtime** (``runtime_sha256``) and **every render knob**, each
  RESOLVED the way the render resolves it (``pix_fmt=None`` is the module
  default at call time, which is what the bench's lever rebinds), plus the
  pinned Chromium and x264 argv.

The machine — Chromium build, Playwright, ffmpeg, ISA — is the separate
environment part (:func:`cutout_environment`), never mixed into the content.
Fonts need no probe of their own: a text unit's glyphs are outlined in Python
and travel INSIDE the document (``data:`` srcs), so a different face is a
different compiled digest.
"""

from __future__ import annotations

import platform
import time
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from an.build.keys import (
    ABSENT,
    ShotKeyInputs,
    bytes_digest,
    canonical_digest,
    file_digest,
)

#: Keys in the compiled document whose string value names an easing.
EASING_KEYS: frozenset[str] = frozenset({"easing"})


def _render_module():
    # Read at CALL time, attribute by attribute: the bench's levers rebind
    # module globals of the render module (`DETERMINISTIC_X264_ARGS`,
    # `DEFAULT_PIX_FMT`, `runtime_dir`), and a key that bound them at import
    # would not see a lever pulled.
    from an.adapters.cutout import render

    return render


def compiled_document(shot: Any, ctx: Any) -> Any:
    """The document `CutoutRenderer.render` will compile for ``shot`` under ``ctx``.

    The SAME call, argument for argument — `tests/test_shot_cache.py` pins the
    two against each other, so a knob added to one and not the other fails
    there rather than in a stale render.
    """
    from an.adapters.cutout.compile import compile_shot

    r = _render_module()
    return compile_shot(
        shot,
        mall=ctx.mall,
        fps=int(round(ctx.fps)),
        width=ctx.resolution[0],
        height=ctx.resolution[1],
        strict_assets=ctx.strict_assets,
        step_hz=r.effective_step_hz(shot, ctx),
        style_pack=ctx.style_pack,
        default_easing=ctx.default_easing,
    )


def texture_digests(scene_json: Any, mall: Mapping[str, Any]) -> dict[str, str]:
    """``{alias: sha256 of the bytes staged for it}`` for every texture the document declares.

    Resolved exactly as `_stage_scene_assets` resolves them — the prefix map,
    the store's root, the versioned ``src`` stripped — so what is digested is
    what is staged. Inline (``data:``) textures are already in the document and
    are skipped; anything unresolvable is :data:`ABSENT` with its ``src``, so
    it still moves the key the day it appears.
    """
    from an.adapters.cutout.text import INLINE_SRC_PREFIX
    from an.raster import strip_version

    r = _render_module()
    textures = getattr(scene_json.assets, "textures", {}) if scene_json.assets else {}
    out: dict[str, str] = {}
    for alias, asset in textures.items():
        src = getattr(asset, "src", None) or ""
        if not src or src.startswith(INLINE_SRC_PREFIX):
            continue
        prefix = next((p for p in r.ASSET_SRC_PREFIX_TO_STORE if src.startswith(p)), None)
        store = mall.get(r.ASSET_SRC_PREFIX_TO_STORE[prefix]) if prefix else None
        root = getattr(store, "_root", None) if store is not None else None
        path = Path(root) / strip_version(src)[len(prefix) :] if root and prefix else None
        if path is not None and path.is_file():
            out[alias] = file_digest(path)
        else:
            out[alias] = f"{ABSENT}:{src}"
    return out


def easing_versions(doc: Any) -> dict[str, int]:
    """``{name: version}`` for every registered easing the compiled document names.

    A parametrised spec (``cubic-bezier(...)``) or a control-point list carries
    its meaning in the document itself and has no version; a name the registry
    does not know is left to the compiler, which refuses it.

    >>> easing_versions({"animations": {"a": {"channels": [{"keyframes": [
    ...     {"time": 0, "value": 0, "easing": "ease_in_out"},
    ...     {"time": 1, "value": 1, "easing": [0.1, 0.2, 0.3, 0.4]}]}]}}})
    {'ease_in_out': 1}
    """
    from an.timing.easing import UnknownEasingError, easing_entry

    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for k, v in node.items():
                if k in EASING_KEYS and isinstance(v, str):
                    names.add(v)
                else:
                    walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(doc)
    out: dict[str, int] = {}
    for name in sorted(names):
        try:
            out[name] = easing_entry(name).version
        except UnknownEasingError:
            continue
    return out


def muxed_audio(shot: Any, ctx: Any) -> dict[str, Any]:
    """What `_mux_shot` lays under the picture, as data: one entry per muxed line.

    Mirrors `_stage_audio_inputs`: a line without an ``audio_ref`` or a start
    is not muxed, and neither is one whose ref the store does not hold. The
    bytes' digest sits beside the ref because the ref keys the SYNTHESIS
    inputs, not the bytes, and the mux reads the bytes.
    """
    store = ctx.mall.get("audio") if ctx.mall else None
    lines = []
    for line in shot.dialogue:
        if not line.audio_ref or line.start is None:
            continue
        try:
            data = store[line.audio_ref] if store else None
        except KeyError:
            data = None
        lines.append(
            {
                "audio_ref": line.audio_ref,
                "viseme_ref": line.viseme_ref,
                "start": float(line.start),
                "sha256": bytes_digest(data) if data is not None else ABSENT,
            }
        )
    total_frames = max(1, int(round(shot.duration * ctx.fps)))
    return {"lines": lines, "picture_seconds": total_frames / ctx.fps}


def render_knobs(shot: Any, ctx: Any) -> dict[str, Any]:
    """Every `RenderContext` knob, resolved the way `CutoutRenderer.render` resolves it.

    Validated here too — an invalid ``pix_fmt`` or supersample factor raises
    the render's own error before anything launches.
    """
    from an.adapters.cutout.shutter import check_frame_samples
    from an.adapters.cutout.supersample import check_factor
    from an.base import BT709_SCALE_FILTER, MP4_FASTSTART_ARGS

    r = _render_module()
    total_frames = max(1, int(round(shot.duration * ctx.fps)))
    frame_samples = check_frame_samples(
        ctx.frame_samples, total_frames=total_frames, duration=shot.duration
    )
    return {
        "fps": float(ctx.fps),
        "resolution": list(ctx.resolution),
        "supersample": check_factor(ctx.supersample),
        "pix_fmt": r._check_pix_fmt(ctx.pix_fmt),
        "capture": r._check_capture(ctx.capture),
        "step_hz": r.effective_step_hz(shot, ctx),
        "frame_samples": [list(f) for f in frame_samples] if frame_samples else None,
        "strict_assets": bool(ctx.strict_assets),
        "extra": dict(ctx.extra),
        "chromium_args": list(r.DETERMINISTIC_CHROMIUM_ARGS),
        "x264_args": list(r.DETERMINISTIC_X264_ARGS),
        "scale_filter": BT709_SCALE_FILTER,
        "faststart_args": list(MP4_FASTSTART_ARGS),
    }


def cutout_shot_inputs(shot: Any, ctx: Any) -> ShotKeyInputs:
    """The cut-out renderer's :data:`~an.build.keys.ShotKeyer`.

    Compiles the shot (timed, as ``compile_s``) and digests everything the
    render reads beside the document. Compile warnings are re-emitted only when
    asked: on a cache MISS the render compiles again and warns itself, so the
    engine collects them here (``details["warnings"]``) and replays them only
    for a shot it reuses, where they would otherwise never be seen.
    """
    from an.adapters.cutout.serialize import to_dict
    from an.bench.contract import scene_contract_sha256
    from an.bench.environment import runtime_sha256

    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scene_json = compiled_document(shot, ctx)
    compile_s = time.perf_counter() - t0
    doc = to_dict(scene_json)
    parts = {
        "compiled": scene_contract_sha256(doc),
        "textures": canonical_digest(texture_digests(scene_json, ctx.mall)),
        "easings": canonical_digest(easing_versions(doc)),
        "audio": canonical_digest(muxed_audio(shot, ctx)),
        "runtime": runtime_sha256(),
        "knobs": canonical_digest(render_knobs(shot, ctx)),
    }
    return ShotKeyInputs(
        parts=parts,
        compile_s=compile_s,
        details={"warnings": list(caught)},
    )


def cutout_environment() -> dict[str, Any]:
    """The cut-out render's machine: the bench's own probes, minus what is not identity.

    Chromium's build and WebGL identity (one browser launch), Playwright,
    ffmpeg's banner, the ISA and OS family, and the Python imaging stack the
    frame stage decodes and resolves with. The executable PATH is left out — it
    names a home directory, not a build. A failed probe is recorded as its
    error, never as "fine".
    """
    from an.bench.environment import ffmpeg_identity, probe_browser, tool_version

    browser = dict(probe_browser())
    browser.pop("executable_path", None)
    ffmpeg = ffmpeg_identity()
    return {
        "browser": browser,
        "playwright": tool_version("playwright"),
        "ffmpeg": ffmpeg.get("banner") or ffmpeg.get("error"),
        "isa": platform.machine(),
        "system": platform.system(),
        "pillow": tool_version("pillow"),
        "numpy": tool_version("numpy"),
    }
