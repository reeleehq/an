"""What a cut-out shot render reads: the keyer behind its shot-cache key (ADR 0004).

The cut-out render is a pure function of these, and of nothing else:

- **the compiled document** — :func:`compile_shot` with exactly the arguments
  the stage engine passes (``StageEngine.open``, since an#247); digested as ``scene_contract_sha256``, so the
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

- **the render path's Python source** (:func:`render_code_digest`): the
  capture loop, the canvas readback, the supersample and shutter resolves, the
  audio mux — everything that turns the document into an mp4 after compile.
  The Python twin of ``runtime_sha256``: an ``an`` upgrade that changes how a
  shot is encoded (an#195 did, with no knob and no runtime change) re-renders
  every shot instead of serving an old mp4. Computed by walking the imports
  from the REGISTERED renderer's own modules (:func:`render_path_roots`: the
  renderer class, the frame stage its ``render`` comes from, its engine), and
  through the string targets of :func:`an._shims.forward_module_attributes`,
  so a new helper module -- or a module that became a pure re-export shim --
  cannot fall outside it.

The machine — Chromium build, Playwright, the full ffmpeg build and the x264
build it encodes with, ISA — is the separate environment part
(:func:`cutout_environment`), never mixed into the content. Fonts: a text
unit's glyphs are outlined in Python and travel INSIDE the document (``data:``
srcs), so a different face is a different compiled digest; but SVG ART may
carry its own ``<text>``, which Chromium draws with the machine's fonts — so a
shot that stages such a part gets a ``fonts`` part, a digest of the installed
font set (:func:`system_fonts_digest`).
"""

from __future__ import annotations

import ast
import importlib.util
import platform
import shutil
import subprocess
import tempfile
import time
import warnings
from collections.abc import Iterable, Mapping
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

#: The cut-out renderer's historical module -- since an#247 a live alias of
#: ``an.stage.render``, followed through its ``alias_module`` target.
#: The walk is no longer rooted HERE alone: :func:`render_path_roots` derives
#: the roots from the registered renderer, and this module is one of them.
RENDER_PATH_ROOT: str = "an.adapters.cutout.render"

#: Modules the walk does NOT enter, each with the reason its change is already
#: in the key some other way. Everything else it reaches is hashed.
RENDER_PATH_EXCLUDED: dict[str, str] = {
    "an.stage.compile": "its output is the `compiled` part",
    "an.stage.serialize": "its output is the `compiled` part",
    "an.stage.text_layout": "compile-side; only INLINE_SRC_PREFIX is read at render",
    "an.ir.schema": "the IR model; what it means for a render reaches `compiled`/`knobs`",
    "an.adapters._base": "the RenderContext/RenderResult types; their values are `knobs`",
}

#: A byte sequence that marks an SVG part drawing text with the MACHINE's fonts.
SVG_TEXT_MARKERS: tuple[bytes, ...] = (b"<text", b":text")


def _render_module():
    # Read at CALL time, attribute by attribute: the bench's levers rebind
    # module globals of the render module (`DETERMINISTIC_X264_ARGS`,
    # `DEFAULT_PIX_FMT`, `runtime_dir`), and a key that bound them at import
    # would not see a lever pulled.
    from an.stage import render

    return render


def compiled_document(shot: Any, ctx: Any) -> Any:
    """The document the stage engine (``StageEngine.open``) will compile for ``shot`` under ``ctx``.

    The SAME call, argument for argument — `tests/test_shot_cache.py` pins the
    two against each other, so a knob added to one and not the other fails
    there rather than in a stale render.
    """
    from an.stage.compile import compile_shot

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
    from an.stage.text_layout import INLINE_SRC_PREFIX
    from an.stage.raster import strip_version

    r = _render_module()
    textures = getattr(scene_json.assets, "textures", {}) if scene_json.assets else {}
    out: dict[str, str] = {}
    for alias, asset in textures.items():
        src = getattr(asset, "src", None) or ""
        if not src or src.startswith(INLINE_SRC_PREFIX):
            continue
        prefix = next(
            (p for p in r.ASSET_SRC_PREFIX_TO_STORE if src.startswith(p)), None
        )
        store = mall.get(r.ASSET_SRC_PREFIX_TO_STORE[prefix]) if prefix else None
        root = getattr(store, "_root", None) if store is not None else None
        path = (
            Path(root) / strip_version(src)[len(prefix) :] if root and prefix else None
        )
        if path is not None and path.is_file():
            out[alias] = file_digest(path)
            if path.suffix.lower() == ".svg" and _draws_system_text(path):
                out[alias] += ":text"
        else:
            out[alias] = f"{ABSENT}:{src}"
    return out


def _draws_system_text(path: Path) -> bool:
    data = path.read_bytes()
    return any(m in data for m in SVG_TEXT_MARKERS)


#: The calls that make an old module's names LIVE aliases of another module's
#: (:mod:`an._shims`). Their target is a STRING, invisible to an import walk.
FORWARDING_CALLS: frozenset[str] = frozenset({"forward_module_attributes", "alias_module"})


def _forwarding_target(node: ast.AST) -> str | None:
    """The target module of a ``forward_module_attributes(name, "target", ...)`` call."""
    if not isinstance(node, ast.Call) or len(node.args) < 2:
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    target = node.args[1]
    if (
        name in FORWARDING_CALLS
        and isinstance(target, ast.Constant)
        and isinstance(target.value, str)
    ):
        return target.value
    return None


def _module_imports(tree: ast.AST, module: str) -> set[str]:
    """Every ``an.*`` module ``tree`` imports, at any depth (function-local too),
    plus every module a ``forward_module_attributes`` call forwards names to.

    >>> sorted(_module_imports(ast.parse(
    ...     'forward_module_attributes(__name__, "an.media.mp4", ["X"])'), "an.old"))
    ['an.media.mp4']
    """
    out: set[str] = set()
    package = module.rsplit(".", 1)[0]
    for node in ast.walk(tree):
        target = _forwarding_target(node)
        if target is not None:
            out.add(target)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(
                    parts[: len(parts) - node.level + 1] + ([base] if base else [])
                )
            out.add(base)
            # `from an.adapters.cutout import render` imports a MODULE.
            out.update(f"{base}.{a.name}" for a in node.names)
    return {m for m in out if m == "an" or m.startswith("an.")}


def render_path_roots(renderer_type: type | None = None) -> tuple[str, ...]:
    """The modules a renderer's render path starts from, read off the renderer itself.

    The renderer class's module, the module its ``render`` method is defined in
    (the core frame stage, for a ``FrameStageRenderer``), and its default
    engine's module -- so moving the renderer (an#247 PR B) or turning its old
    module into a pure shim moves the roots with it. ``None`` is the cut-out
    renderer, plus :data:`RENDER_PATH_ROOT`.

    >>> "an.engines.frame_stage" in render_path_roots()
    True
    """
    if renderer_type is None:
        from an.stage.render import CutoutRenderer

        renderer_type = CutoutRenderer
    roots = [renderer_type.__module__, renderer_type.render.__module__]
    engine_field = getattr(renderer_type, "__dataclass_fields__", {}).get("engine")
    factory = getattr(engine_field, "default_factory", None) if engine_field else None
    if callable(factory):
        roots.append(type(factory()).__module__)
    roots.append(RENDER_PATH_ROOT)
    return tuple(dict.fromkeys(roots))


def render_path_modules(
    root: str | Iterable[str] | None = None,
    *,
    excluded: Mapping[str, str] = RENDER_PATH_EXCLUDED,
) -> dict[str, Path]:
    """``{module: source path}`` for every ``an`` module the render path reaches.

    ``root`` is one module name or several; ``None`` is :func:`render_path_roots`.

    >>> mods = render_path_modules()
    >>> "an.stage.canvas_capture" in mods and "an.stage.compile" not in mods
    True
    >>> {"an.engines.capture", "an.media.mp4"} <= set(mods)
    True
    """
    if root is None:
        roots = list(render_path_roots())
    elif isinstance(root, str):
        roots = [root]
    else:
        roots = list(root)
    found: dict[str, Path] = {}
    aliases = _alias_index()
    todo = roots
    while todo:
        name = todo.pop()
        if name in found or name in excluded or name == "an":
            continue
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):  # `from m import NAME`: NAME is no module
            continue
        if spec is None or not spec.origin or not spec.origin.endswith(".py"):
            continue
        path = Path(spec.origin)
        found[name] = path
        todo.extend(_source_facts(path, name)[1] - set(found))
        # Every old path that is a live alias of this module (an#247) is part
        # of what serves it: an edit to the shim changes what that name runs.
        todo.extend(set(aliases.get(name, ())) - set(found))
    return dict(sorted(found.items()))


def _alias_index() -> dict[str, list[str]]:
    """``{module: [old module names that are whole-module aliases of it]}``.

    Read off the source of every ``an`` module that calls ``alias_module`` --
    by content, like the walk (the parse is memoised per digest).
    """
    import an

    root = Path(an.__file__).parent
    index: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        data = path.read_bytes()
        if b"alias_module(" not in data:
            continue
        parts = list(path.relative_to(root.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module = ".".join(parts)
        if module == "an._shims":
            continue
        for target in _source_facts(path, module)[1]:
            if target != "an._shims":
                index.setdefault(target, []).append(module)
    return index


#: ``{sha256 of a source file: the an.* modules it imports}``. Keyed on the
#: CONTENT, never on a stat: the bytes are read and hashed every time (a few
#: small files, well under a millisecond), and only the parse is memoised. A
#: stat key — even with ctime and inode — is not portable: on Windows
#: ``st_ctime`` is the creation time, so an edit that restores the mtime would
#: pass for the file it replaced (review S2, and the Windows lane).
_IMPORTS_MEMO: dict[tuple[str, str], frozenset[str]] = {}


def _source_facts(path: Path, module: str) -> tuple[str, frozenset[str]]:
    data = path.read_bytes()
    digest = bytes_digest(data)
    if (digest, module) not in _IMPORTS_MEMO:
        _IMPORTS_MEMO[(digest, module)] = frozenset(
            _module_imports(ast.parse(data), module)
        )
    return digest, _IMPORTS_MEMO[(digest, module)]


def render_code_digest() -> str:
    """sha256 over the source of every module on the render path (by module name)."""
    return canonical_digest(
        {
            name: _source_facts(path, name)[0]
            for name, path in render_path_modules().items()
        }
    )


_FONTS: dict[str, str] = {}


def system_fonts_digest() -> str:
    """A digest of the fonts this machine can draw SVG ``<text>`` with; once per process.

    ``fc-list`` where fontconfig exists (Linux, and macOS with it installed);
    otherwise the listing (name, size, mtime) of the platform's font folders.
    """
    if "fonts" not in _FONTS:
        exe = shutil.which("fc-list")
        if exe:
            out = subprocess.run(
                [exe, "--format", "%{file}|%{family}|%{style}\n"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            listing: Any = sorted(out.splitlines())
        else:
            listing = []
            for d in FONT_DIRS.get(platform.system(), ()):
                root = Path(d).expanduser()
                if root.is_dir():
                    for f in sorted(root.rglob("*")):
                        if f.is_file():
                            st = f.stat()
                            listing.append([str(f), st.st_size, st.st_mtime_ns])
        _FONTS["fonts"] = canonical_digest(listing)
    return _FONTS["fonts"]


#: Font folders listed when ``fc-list`` is absent.
FONT_DIRS: dict[str, tuple[str, ...]] = {
    "Darwin": ("/System/Library/Fonts", "/Library/Fonts", "~/Library/Fonts"),
    "Windows": ("C:/Windows/Fonts",),
    "Linux": (
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "~/.local/share/fonts",
        "~/.fonts",
    ),
}


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
    """Every `RenderContext` knob, resolved the way the frame stage resolves it.

    Validated here too — an invalid ``pix_fmt`` or supersample factor raises
    the render's own error before anything launches.
    """
    from an.base import BT709_SCALE_FILTER, MP4_FASTSTART_ARGS
    from an.media import mp4
    from an.media.shutter import check_frame_samples
    from an.media.supersample import check_factor

    r = _render_module()
    try:
        # What the frame stage itself calls (not the stage's old-name wrapper),
        # so a rebinding the render does not see cannot move the key either.
        pix_fmt = mp4.check_pix_fmt(ctx.pix_fmt)
    except mp4.MediaError as e:
        raise r.CutoutRenderError(str(e)) from e
    total_frames = max(1, int(round(shot.duration * ctx.fps)))
    frame_samples = check_frame_samples(
        ctx.frame_samples, total_frames=total_frames, duration=shot.duration
    )
    return {
        "fps": float(ctx.fps),
        "resolution": list(ctx.resolution),
        "supersample": check_factor(ctx.supersample),
        "pix_fmt": pix_fmt,
        "capture": r._check_capture(ctx.capture),
        "step_hz": r.effective_step_hz(shot, ctx),
        "frame_samples": [list(f) for f in frame_samples] if frame_samples else None,
        "strict_assets": bool(ctx.strict_assets),
        "extra": dict(ctx.extra),
        "chromium_args": list(r.DETERMINISTIC_CHROMIUM_ARGS),
        # Read at call time from where the mux reads it (the `high_crf` seam).
        "x264_args": list(mp4.DETERMINISTIC_X264_ARGS),
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
    from an.stage.serialize import to_dict
    from an.bench.contract import scene_contract_sha256
    from an.bench.environment import runtime_sha256

    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scene_json = compiled_document(shot, ctx)
    compile_s = time.perf_counter() - t0
    doc = to_dict(scene_json)
    textures = texture_digests(scene_json, ctx.mall)
    parts = {
        "compiled": scene_contract_sha256(doc),
        "textures": canonical_digest(textures),
        "easings": canonical_digest(easing_versions(doc)),
        "audio": canonical_digest(muxed_audio(shot, ctx)),
        "runtime": runtime_sha256(),
        "code": render_code_digest(),
        "knobs": canonical_digest(render_knobs(shot, ctx)),
    }
    if any(d.endswith(":text") for d in textures.values()):
        parts["fonts"] = system_fonts_digest()
    # Genres' runtime code staged beside runtime.js (an#247): it draws their
    # visual kinds, so it is an input; absent (no part) when none is registered.
    from an.stage.render import runtime_extensions

    extensions = runtime_extensions()
    if extensions:
        parts["runtime_extensions"] = bytes_digest(extensions.encode("utf-8"))
    return ShotKeyInputs(
        parts=parts,
        compile_s=compile_s,
        details={"warnings": list(caught)},
    )


def ffmpeg_build() -> dict[str, Any]:
    """The whole ``ffmpeg -version`` (every library's version and the configure
    line), not its first line: the banner is unchanged by ``brew upgrade x264``,
    which swaps the dynamically linked encoder under it."""
    exe = shutil.which("ffmpeg")
    if exe is None:
        return {"error": "ffmpeg not on PATH"}
    out = subprocess.run([exe, "-version"], capture_output=True, text=True, check=False)
    return {"version": out.stdout.strip() or out.stderr.strip()}


def x264_build() -> str | None:
    """The x264 build that ACTUALLY encodes: one 16x16 frame, its SEI read back.

    The bench's own comparability key (`an.bench.environment.x264_sei`), so
    the cache and the ledger agree about what "the same encoder" means.
    """
    from an.bench.environment import x264_sei

    exe = shutil.which("ffmpeg")
    if exe is None:
        return None
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "probe.mp4"
        subprocess.run(
            [
                exe,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:d=0.04",
                "-frames:v",
                "1",
                "-c:v",
                "libx264",
                str(out),
            ],
            capture_output=True,
            check=False,
        )
        return x264_sei(out) if out.exists() else None


def cutout_environment() -> dict[str, Any]:
    """The cut-out render's machine: the bench's own probes, minus what is not identity.

    Chromium's build and WebGL identity (one browser launch), Playwright, the
    full ffmpeg build and the x264 build it encodes with (one 16x16 encode),
    the ISA and OS family, and the Python imaging stack the frame stage decodes
    and resolves with. The executable PATH is left out — it names a home
    directory, not a build. A failed probe is recorded as its error, never as
    "fine".
    """
    from an.bench.environment import probe_browser, tool_version

    browser = dict(probe_browser())
    browser.pop("executable_path", None)
    return {
        "browser": browser,
        "playwright": tool_version("playwright"),
        "ffmpeg": ffmpeg_build(),
        "x264": x264_build(),
        "isa": platform.machine(),
        "system": platform.system(),
        "pillow": tool_version("pillow"),
        "numpy": tool_version("numpy"),
    }
