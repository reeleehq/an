"""ManimRenderer — a whole-shot renderer for opaque Manim scene files (an#279).

A Manim shot names a Python scene file and a ``Scene`` class in it; ``an`` runs
that file as it is and treats the result like any other rendered shot:

.. code-block:: yaml

    ## Shot chart (manim)
    ```yaml shot
    options: {source: bar_chart, scene: BarChartStory}
    ```

``options.source`` is a key of the project's ``sources`` store
(``assets/sources/bar_chart.py``); ``options.scene`` the class (optional when the
file defines exactly one). The shot has NO IR inside it — it is (a)-level opaque
source on the structured ↔ semantic spectrum — and gets everything around it
from the core: narration (a dialogue line with an off-screen speaker, muxed under
the picture), captions in the sidecar, sound cues, transitions, film assembly,
the shot cache.

**The files a scene reads.** The render runs in a staged copy of the WHOLE
``sources`` folder (``assets/sources/`` and everything under it), so a scene
imports a sibling module or loads ``ImageMobject("bars/logo.png")`` by a path
relative to its own file, and every one of those bytes is in both keys below. A
string literal that names a file OUTSIDE that folder (an absolute path) is a
finding located at its line: the cache cannot see that file change.

**Manim owns its clock** (core study §4.2): only the file's own ``play`` and
``wait`` calls decide how long it runs. The renderer implements
``measure_duration`` (:class:`~an.adapters._base.ClockOwningRenderer`); the
measurement is derived data, kept in the ``measurements`` store under the
**picture key** — what decides Manim's own output and length: the bytes of the
sources folder, the entry file, the scene, the Manim and manimkit versions, the
quality preset and, only for a file that uses LaTeX, whether TeX is available.
Never the film's fps or size, the encode, or this module's code: those change
how the picture is CONFORMED, not what Manim draws. The core applies it in memory
(:mod:`an.measurements`); the author's scene is never rewritten.

**The picture is cached apart from the shot.** Manim's raw video is stored under
the picture key (``pictures`` store), so a change that is not to the picture —
narration, the film's fps, the background pad, an ``an`` upgrade — re-conforms
and re-muxes without running Manim. The shot key (:func:`manim_shot_inputs`)
is the picture key's inputs plus the conform and encode knobs, the muxed audio
and the render path's code; the machine is the separate environment part
(:func:`manim_environment`).

**Findings** — manimkit's layout warnings, lint and errors, a file read the
cache cannot see, a preset whose frame rate the film's does not divide — are
:class:`~an.verify.Finding` s located by ``file:line`` (``Finding.location``),
stored with the measurement (so a reused shot still reports them) and routed by
the core to ``an render``'s warnings, ``render_reports/<output>.json``,
``orchestrate`` and ``an validate``.

**Capabilities** (ADR 0002, environment subject): ``env.manim`` (``manim`` and
``manimkit`` importable) is required — absent, :class:`ManimNotInstalledError`
with the install command. ``env.latex`` is required only by a file that uses
LaTeX; absent, the scene renders in manimkit's ``no_latex`` mode, so a LaTeX use
fails AT ITS LINE with the remedy instead of deep inside a TeX run.

>>> spec = ManimShotSpec.from_options({"source": "chart", "scene": "Chart"})
>>> spec.source, spec.scene, spec.quality
('chart', 'Chart', None)
>>> choose_quality(fps=30, resolution=(1280, 720))
'm'
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import platform
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any

from an.adapters._base import DurationMeasurement, RenderContext, RenderResult
from an.base import BT709_SCALE_FILTER, MP4_FASTSTART_ARGS
from an.build.keys import (
    ABSENT,
    ShotKeyInputs,
    bytes_digest,
    canonical_digest,
    file_digest,
    register_shot_keyer,
)
from an.frame_clock import frame_count
from an.ir.schema import Shot

if TYPE_CHECKING:  # pragma: no cover - types only
    from an.verify._base import Finding


def _finding(*args: Any, **kwargs: Any) -> "Finding":
    """A :class:`~an.verify.Finding` — imported at call time, because
    ``an.verify`` imports ``an.adapters`` (whose init imports this module)."""
    from an.verify._base import Finding

    return Finding(*args, **kwargs)


__all__ = [
    "CONTACT_SHEET_STORE",
    "DEFAULT_SOURCE_STORE",
    "MEASUREMENT_STORE",
    "PICTURE_STORE",
    "QUALITY_PRESETS",
    "ManimNotInstalledError",
    "ManimQuality",
    "ManimRenderError",
    "ManimRenderer",
    "ManimShotSpec",
    "SourceFile",
    "choose_quality",
    "manim_environment",
    "manim_shot_inputs",
    "store_source_resolver",
]


# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------

#: The ``Shot.renderer`` value this backend claims.
RENDERER_NAME: str = "manim"
#: The project store a shot's ``options.source`` is a key of.
DEFAULT_SOURCE_STORE: str = "sources"
#: Derived, content-keyed stores (see the module docstring).
CONTACT_SHEET_STORE: str = "contact_sheets"
MEASUREMENT_STORE: str = "measurements"
PICTURE_STORE: str = "pictures"
#: Manim's own background colour, used to pad a picture whose aspect differs
#: from the film's. ``options.background`` overrides it.
DEFAULT_BACKGROUND: str = "#000000"
#: How many settled beats the contact sheet shows (manimkit's ``n_frames``).
DEFAULT_SHEET_FRAMES: int = 8
#: Seconds a scene may take to render before it is reported as hung.
DEFAULT_TIMEOUT_S: float = 600.0
#: The shot-relative IR path of a finding about the scene file.
SOURCE_PATH: str = "options/source"
#: How the extra is installed — quoted in every install-hinting error.
INSTALL_HINT: str = (
    "pip install 'an[manim]'  (Manim Community Edition + manimkit; on Linux first "
    "`apt install libcairo2-dev libpango1.0-dev`; `manimkit check` lists the rest)"
)
#: The options a Manim shot reads; anything else is a validation warning.
KNOWN_OPTIONS: frozenset[str] = frozenset(
    {"source", "scene", "quality", "background", "timeout"}
)
#: Seconds two layout-warning times may differ and still name the same beat
#: (manimkit rounds both to 0.01 s).
BEAT_TIME_TOLERANCE_S: float = 0.006
#: Names under the sources folder that are never part of a scene's closure.
IGNORED_SOURCE_PARTS: frozenset[str] = frozenset({"__pycache__", "manimkit_renders"})
#: Extensions that make a string literal read as a FILE the scene loads, for the
#: "outside the sources folder" finding.
FILE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".csv", ".json", ".txt", ".tex",
        ".ttf", ".otf", ".wav", ".mp3", ".npy", ".py", ".md", ".yaml", ".yml",
    }
)  # fmt: skip

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_LINE = re.compile(r"line (\d+)")
_WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class ManimQuality:
    """One of Manim's quality presets: its letter, pixel size and frame rate."""

    letter: str
    width: int
    height: int
    fps: int


#: Manim Community Edition's presets (``-ql`` … ``-qk``), smallest first.
QUALITY_PRESETS: dict[str, ManimQuality] = {
    q.letter: q
    for q in (
        ManimQuality("l", 854, 480, 15),
        ManimQuality("m", 1280, 720, 30),
        ManimQuality("h", 1920, 1080, 60),
        ManimQuality("p", 2560, 1440, 60),
        ManimQuality("k", 3840, 2160, 60),
    )
}


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------


class ManimRenderError(RuntimeError):
    """A Manim shot could not be rendered. Carries the file:line and the fix."""


class ManimNotInstalledError(ManimRenderError, ImportError):
    """``manim`` / ``manimkit`` are not importable (``env.manim`` is absent)."""


# -----------------------------------------------------------------------------
# The shot's options
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ManimShotSpec:
    """What a Manim shot's ``options`` say, checked.

    >>> ManimShotSpec.from_options({"source": "s", "quality": "z"})
    Traceback (most recent call last):
    ...
    an.adapters.manim_adapter.ManimRenderError: options.quality must be one of ['l', 'm', 'h', 'p', 'k'] (Manim's presets), got 'z'
    """

    source: str
    scene: str | None = None
    quality: str | None = None
    background: str = DEFAULT_BACKGROUND
    timeout: float = DEFAULT_TIMEOUT_S

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> "ManimShotSpec":
        source = options.get("source")
        if not isinstance(source, str) or not source:
            raise ManimRenderError(
                "a Manim shot names its scene file: options.source = <key in the "
                f"project's {DEFAULT_SOURCE_STORE!r} store> (the file "
                f"assets/{DEFAULT_SOURCE_STORE}/<key>.py), got {source!r}"
            )
        scene = options.get("scene")
        if scene is not None and (
            not isinstance(scene, str) or not scene.isidentifier()
        ):
            raise ManimRenderError(
                f"options.scene must be the name of a Scene class, got {scene!r}"
            )
        quality = options.get("quality")
        if quality is not None and quality not in QUALITY_PRESETS:
            raise ManimRenderError(
                f"options.quality must be one of {list(QUALITY_PRESETS)} (Manim's "
                f"presets), got {quality!r}"
            )
        background = options.get("background", DEFAULT_BACKGROUND)
        if not isinstance(background, str) or not _HEX_COLOR.match(background):
            raise ManimRenderError(
                f"options.background must be a #rrggbb colour, got {background!r}"
            )
        timeout = options.get("timeout", DEFAULT_TIMEOUT_S)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ManimRenderError(
                f"options.timeout must be positive seconds, got {timeout!r}"
            )
        return cls(
            source=source,
            scene=scene,
            quality=quality,
            background=background.lower(),
            timeout=float(timeout),
        )

    @classmethod
    def from_shot(cls, shot: Shot) -> "ManimShotSpec":
        try:
            return cls.from_options(shot.options or {})
        except ManimRenderError as e:
            raise ManimRenderError(f"shot {shot.id!r}: {e}") from None


def choose_quality(*, fps: float, resolution: tuple[int, int]) -> str:
    """The smallest Manim preset that is at least as tall and as fast as the film.

    The picture is then resampled and scaled to exactly the film's rate and size,
    so a smaller preset would be upscaled (blur) or frame-doubled (judder).

    >>> choose_quality(fps=15, resolution=(640, 360)), choose_quality(fps=30, resolution=(1920, 1080))
    ('l', 'h')
    >>> choose_quality(fps=120, resolution=(8000, 4000))  # nothing is enough: the largest
    'k'
    """
    _width, height = resolution
    for q in QUALITY_PRESETS.values():
        if q.height >= height and q.fps >= fps:
            return q.letter
    return list(QUALITY_PRESETS)[-1]


# -----------------------------------------------------------------------------
# The source, and everything it can read
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceFile:
    """A scene file and its closure, as a resolver read them.

    ``closure`` is every file the render stages into its working directory —
    ``{relative path: bytes}``, the entry file included as ``entry`` — and
    :attr:`digest` covers all of it, so a sibling module or an image the scene
    loads relatively is in the keys. ``display`` is how a finding names the
    entry (``assets/sources/chart.py``; never an absolute path).
    """

    key: str
    entry: str
    closure: Mapping[str, bytes]
    display: str

    @property
    def data(self) -> bytes:
        return self.closure[self.entry]

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="replace")

    @property
    def digest(self) -> str:
        return canonical_digest(
            sorted([path, bytes_digest(data)] for path, data in self.closure.items())
        )


#: ``resolver(spec, mall) -> SourceFile``: where a shot's scene file comes from.
#: The default reads the project's ``sources`` store; a genre (Manim step 2) can
#: supply generated code in memory.
SourceResolver = Callable[["ManimShotSpec", Mapping[str, Any]], SourceFile]


def _store_closure(store: Any) -> dict[str, bytes]:
    """Every file under a filesystem store's folder (recursively), else every
    entry of the mapping as ``<key>.py``."""
    root = getattr(store, "_root", None)
    if root is not None and Path(root).is_dir():
        root = Path(root)
        out = {}
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if any(p.startswith(".") or p in IGNORED_SOURCE_PARTS for p in rel.parts):
                continue
            if path.is_file():
                out[rel.as_posix()] = path.read_bytes()
        return out
    return {
        f"{k}.py": (v.encode("utf-8") if isinstance(v, str) else bytes(v))
        for k, v in ((k, store[k]) for k in store)
    }


def _display_path(store: Any, name: str) -> str:
    root = getattr(store, "_root", None)
    if root is not None:
        return "/".join((*Path(root).parts[-2:], name))  # assets/sources/<name>
    return f"{DEFAULT_SOURCE_STORE}/{name}"


def store_source_resolver(store: str = DEFAULT_SOURCE_STORE) -> SourceResolver:
    """The default resolver: ``options.source`` is a key of the mall's ``store``.

    >>> resolve = store_source_resolver()
    >>> resolve(ManimShotSpec("chart"), {"sources": {"chart": b"x = 1"}}).data
    b'x = 1'
    """

    def resolve(spec: ManimShotSpec, mall: Mapping[str, Any]) -> SourceFile:
        sources = mall.get(store) if mall else None
        if sources is None:
            raise ManimRenderError(
                f"the project has no {store!r} store to read options.source="
                f"{spec.source!r} from (build the mall with an.stores.build_project_mall)"
            )
        if spec.source not in sources:
            known = sorted(str(k) for k in sources)
            raise ManimRenderError(
                f"no scene file {spec.source!r} in the project's {store!r} store "
                f"(expected {_display_path(sources, spec.source + '.py')}); it has: {known}"
            )
        closure = _store_closure(sources)
        entry = f"{spec.source}.py"
        if entry not in closure:  # a mapping whose keys are not file names
            data = sources[spec.source]
            closure[entry] = (
                data.encode("utf-8") if isinstance(data, str) else bytes(data)
            )
        return SourceFile(spec.source, entry, closure, _display_path(sources, entry))

    return resolve


def source_requirements(code: str) -> tuple[str, ...]:
    """The environment capabilities a scene file needs (ADR 0002 requirements).

    ``env.manim`` always; ``env.latex`` when the file uses LaTeX, by manimkit's
    own detector when it is importable, else by the names that need it.

    >>> source_requirements("Text('hi')"), source_requirements("MathTex(r'x^2')")
    (('env.manim',), ('env.manim', 'env.latex'))
    """
    try:
        from manimkit.corpus import uses_latex
    except ImportError:  # the static fallback: the classes that typeset with TeX

        def uses_latex(text: str) -> bool:
            return bool(
                re.search(r"\b(MathTex|Tex|SingleStringMathTex|Matrix)\s*\(", text)
            )

    return ("env.manim", "env.latex") if uses_latex(code) else ("env.manim",)


def _latex_available() -> bool:
    from an.capabilities.subjects import environment_affordances

    return "env.latex" in environment_affordances()


def outside_reads(code: str, closure: Mapping[str, bytes]) -> list[tuple[int, str]]:
    """``(line, path)`` for each string literal naming a file the render cannot
    stage: an absolute path, or a relative one not in the closure.

    >>> outside_reads("ImageMobject('/tmp/logo.png')\\nT('a.png')", {"a.png": b""})
    [(1, '/tmp/logo.png')]
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value.strip()
        if "\n" in text or Path(text).suffix.lower() not in FILE_SUFFIXES:
            continue
        absolute = text.startswith(("/", "~")) or bool(_WINDOWS_ABS.match(text))
        if absolute or Path(text).as_posix().lstrip("./") not in closure:
            out.append((node.lineno, text))
    return sorted(out)


def _module_stem(key: str) -> str:
    """A file stem the runner can import as a module (it is a ``sys.modules`` key)."""
    stem = re.sub(r"\W", "_", key)
    return stem if stem and not stem[0].isdigit() else f"scene_{stem}"


# -----------------------------------------------------------------------------
# Locating findings in the source
# -----------------------------------------------------------------------------


def _scene_lines(code: str, scene: str | None) -> tuple[int | None, list[int] | None]:
    """``(construct line, [line of each play/wait])`` for ``scene`` in ``code``.

    The beat list is returned only when the beats are LINEAR — every
    ``self.play``/``self.wait`` is a statement directly in ``construct`` — so the
    k-th beat of manimkit's timeline IS the k-th call. A loop, a branch or a
    helper method makes the order a run-time fact; then ``None``, and a finding
    is located at ``construct`` rather than at a guessed line.

    >>> code = "class S(Scene):\\n    def construct(self):\\n        self.play(A())\\n        self.wait()\\n"
    >>> _scene_lines(code, "S")
    (2, [3, 4])
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None, None
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    cls = next((c for c in classes if c.name == scene), None) if scene else None
    if cls is None and len(classes) == 1:
        cls = classes[0]
    if cls is None:
        return None, None
    construct = next(
        (
            f
            for f in cls.body
            if isinstance(f, ast.FunctionDef) and f.name == "construct"
        ),
        None,
    )
    if construct is None:
        return cls.lineno, None

    def is_beat(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"play", "wait"}
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        )

    direct = [
        s.value.lineno
        for s in construct.body
        if isinstance(s, ast.Expr) and is_beat(s.value)
    ]
    everywhere = sum(1 for n in ast.walk(cls) if is_beat(n))
    return construct.lineno, (direct if everywhere == len(direct) else None)


def _beat_index(timeline: list[Mapping[str, Any]], t: float) -> int | None:
    """The beat a layout warning at time ``t`` was raised after (its end time)."""
    for i, beat in enumerate(timeline):
        if abs(float(beat.get("t1", -1.0)) - t) <= BEAT_TIME_TOLERANCE_S:
            return i
    for i, beat in enumerate(timeline):
        if float(beat.get("t0", 0.0)) <= t <= float(beat.get("t1", -1.0)):
            return i
    return None


def report_findings(
    report: Any, source: SourceFile, *, scene: str | None = None
) -> list["Finding"]:
    """manimkit's report as shot-relative :class:`Finding` s, located by ``file:line``.

    Layout warnings land on the line of the ``play``/``wait`` they were checked
    after (when the beats are linear, see :func:`_scene_lines`), lint issues on
    their own line, a failed render on the last line of the file in its
    traceback, and a literal path the cache cannot see on its own line.

    >>> class R:  # a report, as manimkit returns it
    ...     ok, lint, error = True, [], None
    ...     timeline = [{"t0": 0.0, "t1": 1.0, "what": "Write"}]
    ...     layout_warnings = [{"t": 1.0, "kind": "cut-off", "message": "Text('wide') runs off the right edge"}]
    >>> code = b"class S(Scene):\\n    def construct(self):\\n        self.play(Write(t))\\n"
    >>> src = SourceFile("c", "c.py", {"c.py": code}, "assets/sources/c.py")
    >>> [(f.severity, f.ir_path, f.location) for f in report_findings(R(), src)]
    [('warning', 'options/source', 'assets/sources/c.py:3')]
    """
    construct_line, beats = _scene_lines(source.text, scene)
    fallback = (
        f"{source.display}:{construct_line}" if construct_line else source.display
    )
    out: list[Finding] = []
    timeline = list(getattr(report, "timeline", None) or [])
    for w in getattr(report, "layout_warnings", None) or []:
        t = float(w.get("t", 0.0))
        k = _beat_index(timeline, t)
        if beats is not None and k is not None and k < len(beats):
            where = f"{source.display}:{beats[k]}"
            beat = timeline[k]
            when = f"after beat {k + 1} ({beat.get('what', '?')}, {beat.get('t0')}–{beat.get('t1')} s)"
        else:
            where, when = fallback, f"at t={t:.2f} s"
        out.append(
            _finding(
                "warning",
                SOURCE_PATH,
                f"[{w.get('kind', 'layout')}] {w.get('message', '')} {when}",
                "move, scale or space the mobjects that play there; look at the "
                "contact sheet",
                location=where,
            )
        )
    for issue in getattr(report, "lint", None) or []:
        m = _LINE.match(str(issue))
        out.append(
            _finding(
                "warning",
                SOURCE_PATH,
                f"lint: {issue}",
                location=f"{source.display}:{m.group(1)}" if m else fallback,
            )
        )
    for line, path in outside_reads(source.text, source.closure):
        out.append(
            _finding(
                "warning",
                SOURCE_PATH,
                f"this scene reads {path!r}, which is not under "
                f"{source.display.rsplit('/', 1)[0]}/: the shot cache cannot see it "
                "change, and another machine will not have it",
                "copy the file under the sources folder and name it by a path "
                "relative to the scene file",
                location=f"{source.display}:{line}",
            )
        )
    if not getattr(report, "ok", True):
        frames = list(getattr(report, "user_frames", None) or [])
        lines = [m.group(1) for f in frames if (m := _LINE.match(str(f)))]
        detail = "; ".join(
            x
            for x in (
                getattr(report, "error", None) or "the render failed",
                f"hint: {report.hint}" if getattr(report, "hint", None) else "",
                f"latex log: {report.latex_log}"
                if getattr(report, "latex_log", None)
                else "",
            )
            if x
        )
        latex = getattr(report, "error_kind", None) in {"latex", "latex-blocked"}
        out.append(
            _finding(
                "error",
                SOURCE_PATH,
                f"Manim render failed ({getattr(report, 'error_kind', None) or 'error'}): {detail}",
                "install LaTeX (env.latex), or use Text instead of MathTex/Tex"
                if latex
                else None,
                location=f"{source.display}:{lines[-1]}" if lines else fallback,
            )
        )
    return out


# -----------------------------------------------------------------------------
# The render seam
# -----------------------------------------------------------------------------

#: ``render_check(file, scene, *, quality, n_frames, out_dir, no_latex, timeout)
#: -> report`` — manimkit's signature and report shape (``ok``, ``video``,
#: ``contact_sheet``, ``timeline``, ``layout_warnings``, ``lint``, ``error``,
#: ``error_kind``, ``user_frames``, ``hint``, ``latex_log``).
RenderCheck = Callable[..., Any]


def _manimkit_render_check() -> RenderCheck:
    if importlib.util.find_spec("manim") is None:
        raise ManimNotInstalledError(
            f"rendering a Manim shot needs Manim (env.manim is absent): {INSTALL_HINT}"
        )
    try:
        from manimkit import render_check
    except ImportError as e:
        raise ManimNotInstalledError(
            f"rendering a Manim shot needs manimkit ({e}): {INSTALL_HINT}"
        ) from e
    return render_check


def _version(package: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(package)
    except PackageNotFoundError:
        return None


def manim_version() -> str:
    """The installed Manim's version — a part of every Manim key."""
    v = _version("manim")
    if v is None:
        raise ManimNotInstalledError(
            f"rendering a Manim shot needs Manim (env.manim is absent): {INSTALL_HINT}"
        )
    return v


def manimkit_version() -> str | None:
    """manimkit's version: its runner decides how Manim is configured."""
    return _version("manimkit")


# -----------------------------------------------------------------------------
# Keys
# -----------------------------------------------------------------------------


def picture_inputs(
    spec: ManimShotSpec, source: SourceFile, ctx: RenderContext
) -> dict[str, Any]:
    """What decides Manim's OWN output and length — and nothing else.

    Not the film's fps or size (they only pick the default preset), not the
    background pad, not the encode, not this module's code: those change how
    the picture is conformed, so they are in the shot key only (review H2).
    """
    quality = spec.quality or choose_quality(
        fps=ctx.fps, resolution=tuple(ctx.resolution)
    )
    needs_latex = "env.latex" in source_requirements(source.text)
    return {
        "sources": source.digest,
        "entry": source.entry,
        "scene": spec.scene,
        "manim": manim_version(),
        "manimkit": manimkit_version(),
        "quality": quality,
        "no_latex": (not _latex_available()) if needs_latex else None,
    }


def picture_key(inputs: Mapping[str, Any]) -> str:
    return canonical_digest(dict(inputs))


def render_code_digest() -> str:
    """The code between Manim's picture and the shot's mp4: this module and the
    core's frame and mp4 sinks (an upgrade that changes the conform or the
    encode re-renders the shot — but never runs Manim again)."""
    import an.media.frames as frames_mod
    import an.media.mp4 as mp4_mod

    files = {
        "adapter": __file__,
        "mp4": mp4_mod.__file__,
        "frames": frames_mod.__file__,
    }
    return canonical_digest(
        {
            k: (file_digest(p) if p and Path(p).is_file() else ABSENT)
            for k, p in files.items()
        }
    )


# -----------------------------------------------------------------------------
# The raw picture: Manim's own render, stored by its key
# -----------------------------------------------------------------------------


@dataclass
class RawPicture:
    """Manim's render of a scene, before it meets a film."""

    key: str
    quality: str
    fps: int
    n_frames: int
    duration: float  # n_frames / fps, exactly what Manim wrote
    video: bytes
    findings: list["Finding"] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    contact_sheet: str | None = None
    log: str = ""

    def record(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "quality": self.quality,
            "fps": self.fps,
            "n_frames": self.n_frames,
            "duration": self.duration,
            "findings": [asdict(f) for f in self.findings],
            "timeline": self.timeline,
            "contact_sheet": self.contact_sheet,
            "log": self.log,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any], video: bytes) -> "RawPicture":
        d = dict(record)
        d["findings"] = [_finding(**f) for f in d.get("findings", [])]
        return cls(video=video, **d)


def _count_frames(video: Path) -> int:
    """Frames in ``video``'s first video stream, counted (not the container's guess)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    try:
        return int(out.stdout.strip().splitlines()[0].strip(","))
    except (ValueError, IndexError):
        raise ManimRenderError(
            f"could not count the frames of Manim's video: {out.stderr.strip()[-400:]}"
        ) from None


def _conform(
    video: Path,
    frames_dir: Path,
    *,
    fps: float,
    resolution: tuple[int, int],
    background: str,
    n_frames: int,
) -> None:
    """Manim's mp4 -> exactly ``n_frames`` PNGs at the film's rate and size.

    Resampled with ffmpeg's ``fps`` filter (nearest frame), scaled to fit and
    padded with the background, so a 16:9 scene in a 4:3 film is letterboxed
    rather than stretched. Short of ``n_frames`` (a held narration, or the
    resampler's rounding) the last frame is HELD; past it, the extra frames
    are dropped — so the shot has exactly the frames the film's timeline gives it.
    """
    from an.media.frames import DEFAULT_FRAME_PNG_PATTERN, frame_path

    width, height = resolution
    vf = (
        f"fps={fps},"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x{background.lstrip('#')},"
        "format=rgb24"
    )
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", vf,
        "-start_number", "0", str(frames_dir / DEFAULT_FRAME_PNG_PATTERN),
    ]  # fmt: skip
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise ManimRenderError(f"ffmpeg failed to launch: {e}") from e
    written = sorted(frames_dir.glob("*.png"))
    if result.returncode != 0 or not written:
        raise ManimRenderError(
            f"conforming the Manim video to {width}x{height} at {fps} fps failed "
            f"(rc={result.returncode}): {result.stderr.strip()[-800:]}"
        )
    for extra in written[n_frames:]:
        extra.unlink()
    last = written[min(len(written), n_frames) - 1]
    for i in range(len(written), n_frames):
        shutil.copyfile(last, frame_path(frames_dir, i))


# -----------------------------------------------------------------------------
# The renderer
# -----------------------------------------------------------------------------


class ManimRenderer:
    """Manim Community Edition, through ``manimkit``: an opaque-source shot renderer.

    Implements :class:`~an.adapters._base.Renderer` and
    :class:`~an.adapters._base.ClockOwningRenderer`. Seams: ``render_check``
    (default :func:`manimkit.render_check`, imported on first use) and
    ``source_resolver`` (default: the project's ``sources`` store,
    :func:`store_source_resolver`). The shot cache keys a shot through the
    REGISTERED instance's resolver; a subclass registers its own keyer
    (``register_shot_keyer(name, manim_shot_inputs, renderer_type=Sub)``).
    """

    name: str = RENDERER_NAME
    supported_renderers: tuple[str, ...] = (RENDERER_NAME,)

    def __init__(
        self,
        *,
        render_check: RenderCheck | None = None,
        source_resolver: SourceResolver | None = None,
    ) -> None:
        self._render_check = render_check
        self.source_resolver = source_resolver or store_source_resolver()
        # The raw pictures of a mall with no `pictures`/`measurements` store
        # (a dict mall in a test): content-keyed, so never stale.
        self._memo: dict[str, RawPicture] = {}

    def can_render(self, shot: Shot) -> bool:
        return shot.renderer in self.supported_renderers

    def resolve(
        self, shot: Shot, ctx: RenderContext
    ) -> tuple[ManimShotSpec, SourceFile]:
        spec = ManimShotSpec.from_shot(shot)
        return spec, self.source_resolver(spec, ctx.mall)

    # -- the clock ---------------------------------------------------------

    def measure_duration(
        self,
        shot: Shot,
        ctx: RenderContext,
        *,
        render: bool = True,
        force: bool = False,
    ) -> DurationMeasurement | None:
        """Manim's length of this shot's scene, from the ``measurements`` store,
        or rendered now (and stored) when there is none — or when ``force``."""
        spec, source = self.resolve(shot, ctx)
        inputs = picture_inputs(spec, source, ctx)
        raw = self._raw(spec, source, inputs, ctx, render=render, force=force)
        if raw is None:
            return None
        findings = list(raw.findings)
        film_fps = float(ctx.fps)
        if raw.fps != film_fps and (raw.fps % film_fps if film_fps else 1):
            findings.append(
                _finding(
                    "info",
                    "options/quality",
                    f"Manim draws this shot at {raw.fps} fps (preset {raw.quality!r}) "
                    f"and the film runs at {film_fps:g} fps, which does not divide "
                    "it: frames are dropped or doubled unevenly (judder)",
                    "render the film at a rate that divides the preset's (15, 30 "
                    "or 60), or choose the preset with options.quality",
                )
            )
        return DurationMeasurement(
            duration=raw.duration, findings=findings, key=raw.key
        )

    # -- the render --------------------------------------------------------

    def render(self, shot: Shot, ctx: RenderContext) -> RenderResult:
        """Render ``shot`` for exactly ``shot.duration`` (``an.render`` settles it
        to the measured length, or longer to hold for its narration)."""
        from an.media.mp4 import ensure_ffmpeg, mux_shot

        spec, source = self.resolve(shot, ctx)
        inputs = picture_inputs(spec, source, ctx)  # raises the install hint first
        ensure_ffmpeg()
        raw = self._raw(spec, source, inputs, ctx, render=True, force=False)
        work = Path(ctx.work_dir) / f"manim_shot_{shot.id}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        video = work / "manim.mp4"
        video.write_bytes(raw.video)
        n = frame_count(shot.duration, ctx.fps)
        frames_dir = work / "frames"
        _conform(
            video, frames_dir, fps=float(ctx.fps), resolution=tuple(ctx.resolution),
            background=spec.background, n_frames=n,
        )  # fmt: skip
        out_mp4 = work / f"{shot.id}.mp4"
        n_audio = mux_shot(
            frames_dir, shot, ctx, work, out_mp4, n_frames=n, pix_fmt=ctx.pix_fmt
        )
        return RenderResult(
            mp4_path=out_mp4,
            duration=n / float(ctx.fps),
            frame_manifest=sorted(frames_dir.glob("*.png")),
            log=raw.log,
            provenance={
                "shot_id": shot.id,
                "renderer": RENDERER_NAME,
                "n_audio_tracks": n_audio,
                "manim": {
                    "source": source.key,
                    "file": source.display,
                    "sources_digest": source.digest,
                    "scene": spec.scene,
                    "quality": raw.quality,
                    "version": inputs["manim"],
                    "picture": raw.key,
                    "measured": raw.duration,
                    "held": max(0.0, n / float(ctx.fps) - raw.duration),
                    "timeline": raw.timeline,
                    "contact_sheet": (
                        {"store": CONTACT_SHEET_STORE, "key": raw.contact_sheet}
                        if raw.contact_sheet
                        else None
                    ),
                    "findings": [asdict(f) for f in raw.findings],
                },
            },
        )

    def _raw(
        self,
        spec: ManimShotSpec,
        source: SourceFile,
        inputs: Mapping[str, Any],
        ctx: RenderContext,
        *,
        render: bool,
        force: bool,
    ) -> RawPicture | None:
        """The raw picture for ``inputs``: stored, or rendered now and stored."""
        key = picture_key(inputs)
        measurements = ctx.mall.get(MEASUREMENT_STORE) if ctx.mall else None
        pictures = ctx.mall.get(PICTURE_STORE) if ctx.mall else None
        if not force:
            if measurements is not None and pictures is not None:
                try:
                    if key in measurements and key in pictures:
                        record = json.loads(measurements[key])
                        return RawPicture.from_record(record, pictures[key])
                except (KeyError, ValueError, TypeError):
                    pass  # an unreadable entry is a miss: rendered again below
            elif key in self._memo:
                return self._memo[key]
        if not render:
            return None
        raw = self._render_raw(spec, source, inputs, key, ctx)
        if measurements is not None and pictures is not None:
            pictures[key] = (
                raw.video
            )  # the picture first: a record never points at nothing
            measurements[key] = json.dumps(raw.record(), sort_keys=True).encode("utf-8")
        else:
            self._memo[key] = raw
        return raw

    def _render_raw(
        self,
        spec: ManimShotSpec,
        source: SourceFile,
        inputs: Mapping[str, Any],
        key: str,
        ctx: RenderContext,
    ) -> RawPicture:
        render_check = self._render_check or _manimkit_render_check()
        root = Path(ctx.work_dir) / "manim" / key[:24]
        if root.exists():
            shutil.rmtree(root)
        src_dir = root / "src"
        for (
            rel,
            data,
        ) in source.closure.items():  # the whole folder: relative reads work
            path = src_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        entry = src_dir / f"{_module_stem(source.key)}.py"
        if entry != src_dir / source.entry:
            entry.write_bytes(source.data)
        report = render_check(
            entry,
            spec.scene,
            quality=inputs["quality"],
            n_frames=DEFAULT_SHEET_FRAMES,
            out_dir=root / "manimkit",
            no_latex=bool(inputs["no_latex"]),
            timeout=spec.timeout,
        )
        findings = report_findings(report, source, scene=spec.scene)
        if not getattr(report, "ok", False) or not getattr(report, "video", None):
            errors = [f for f in findings if f.severity == "error"] or [
                _finding(
                    "error",
                    SOURCE_PATH,
                    "Manim produced no video (a scene with no animation renders an image)",
                    location=source.display,
                )
            ]
            first = errors[0]
            fix = f"\n  fix: {first.suggested_fix}" if first.suggested_fix else ""
            raise ManimRenderError(f"{first.location}: {first.description}{fix}")
        video = Path(report.video)
        preset = QUALITY_PRESETS[inputs["quality"]]
        n = _count_frames(video)
        sheet = None
        sheet_path = getattr(report, "contact_sheet", None)
        store = ctx.mall.get(CONTACT_SHEET_STORE) if ctx.mall else None
        if sheet_path and Path(sheet_path).is_file():
            data = Path(sheet_path).read_bytes()
            sheet = hashlib.sha256(data).hexdigest()
            if store is not None:
                if sheet not in store:
                    store[sheet] = data
                for f in findings:
                    if f.suggested_fix and f.suggested_fix.endswith(
                        "look at the contact sheet"
                    ):
                        f.suggested_fix += f" ({_display_path(store, sheet + '.png')})"
        return RawPicture(
            key=key,
            quality=inputs["quality"],
            fps=preset.fps,
            n_frames=n,
            duration=float(Fraction(n, preset.fps)),
            video=video.read_bytes(),
            findings=findings,
            timeline=list(getattr(report, "timeline", None) or []),
            contact_sheet=sheet,
            log=str(report),
        )


# -----------------------------------------------------------------------------
# The shot cache (ADR 0004): what a Manim shot's render reads
# -----------------------------------------------------------------------------


def _muxed_audio(shot: Shot, ctx: RenderContext) -> dict[str, Any]:
    """The dialogue audio :func:`an.media.mp4.mux_shot` lays under the picture,
    and the picture length it is cut to."""
    store = ctx.mall.get("audio") if ctx.mall else None
    lines = []
    for line in shot.dialogue:
        if not line.audio_ref or line.start is None:
            continue
        try:
            data = store[line.audio_ref] if store is not None else None
        except KeyError:
            data = None
        lines.append(
            {
                "audio_ref": line.audio_ref,
                "start": float(line.start),
                "sha256": bytes_digest(data) if data is not None else ABSENT,
            }
        )
    return {"lines": lines, "picture_frames": frame_count(shot.duration, ctx.fps)}


def _registered_renderer(shot: Shot) -> ManimRenderer:
    """The renderer the render will use for ``shot`` — so the key reads the
    source through ITS resolver (review M3)."""
    from an.adapters._base import _DEFAULT_REGISTRY

    found = _DEFAULT_REGISTRY.find_for(shot)
    return found if isinstance(found, ManimRenderer) else ManimRenderer()


def manim_shot_inputs(shot: Shot, ctx: RenderContext) -> ShotKeyInputs:
    """The Manim renderer's :data:`~an.build.keys.ShotKeyer`.

    Named parts: ``source`` (every file of the sources folder the render
    stages), ``manim`` (the picture's other inputs: entry, scene, Manim and
    manimkit versions, quality, LaTeX mode — :func:`picture_inputs`), ``knobs``
    (fps, size, background and the encode: pixel format, x264 argv, scale
    filter, faststart), ``audio`` (the dialogue muxed under it and the frame
    count it is cut to — a held narration moves it) and ``code``
    (:func:`render_code_digest`). Raises what the render would for a bad shot.
    """
    from an.media import mp4

    spec, source = _registered_renderer(shot).resolve(shot, ctx)
    inputs = picture_inputs(spec, source, ctx)
    try:
        pix_fmt = mp4.check_pix_fmt(ctx.pix_fmt)
    except mp4.MediaError as e:
        raise ManimRenderError(str(e)) from e
    knobs = {
        "fps": float(ctx.fps),
        "resolution": [int(x) for x in ctx.resolution],
        "background": spec.background,
        "pix_fmt": pix_fmt,
        "x264_args": list(mp4.DETERMINISTIC_X264_ARGS),
        "scale_filter": BT709_SCALE_FILTER,
        "faststart_args": list(MP4_FASTSTART_ARGS),
    }
    return ShotKeyInputs(
        parts={
            "source": inputs["sources"],
            "manim": canonical_digest(
                {k: v for k, v in inputs.items() if k != "sources"}
            ),
            "knobs": canonical_digest(knobs),
            "audio": canonical_digest(_muxed_audio(shot, ctx)),
            "code": render_code_digest(),
        },
        details={"source": source.display},
    )


def _first_line(cmd: list[str]) -> str | None:
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, *cmd[1:]], capture_output=True, text=True, check=False
        )
    except OSError as e:
        return f"error: {e}"
    text = (out.stdout or out.stderr).strip()
    return text.splitlines()[0] if text else None


def _fonts_digest() -> str | None:
    """The installed font set (``fc-list``): Manim's ``Text`` draws with system
    fonts through Pango, so a font change is a machine change."""
    exe = shutil.which("fc-list")
    if exe is None:
        return None
    out = subprocess.run(
        [exe, ":", "family", "style"], capture_output=True, text=True, check=False
    )
    return bytes_digest("\n".join(sorted(out.stdout.splitlines())).encode("utf-8"))


def manim_environment() -> dict[str, Any]:
    """The Manim render's machine: Manim's stack, ffmpeg, LaTeX, fonts, the ISA.

    Python package versions (Manim draws with Cairo and Pango through pycairo
    and ManimPango, and writes with PyAV), the full ``ffmpeg -version`` banner
    (the conform and the encode), the LaTeX and dvisvgm builds (a formula's
    glyphs), the installed font set, and the ISA and OS family. Never a path.
    """
    ffmpeg = shutil.which("ffmpeg")
    banner = (
        subprocess.run(
            [ffmpeg, "-version"], capture_output=True, text=True, check=False
        ).stdout.strip()
        if ffmpeg
        else None
    )
    return {
        "packages": {
            name: _version(name)
            for name in (
                "manim",
                "manimkit",
                "manimpango",
                "pycairo",
                "av",
                "numpy",
                "pillow",
            )
        },
        "ffmpeg": banner,
        "latex": _first_line(["latex", "--version"]),
        "dvisvgm": _first_line(["dvisvgm", "--version"]),
        "fonts": _fonts_digest(),
        "isa": platform.machine(),
        "system": platform.system(),
    }


register_shot_keyer(
    RENDERER_NAME,
    manim_shot_inputs,
    environment=manim_environment,
    renderer_type=ManimRenderer,
)


# -----------------------------------------------------------------------------
# `an validate`: a Manim shot's options, and whether this machine can render it
# -----------------------------------------------------------------------------


def _check_manim_shot(ctx: Any) -> None:
    """A Manim shot's ``options`` are well-formed; ``env.manim`` is present."""
    shot = ctx.shot
    if shot.renderer != RENDERER_NAME:
        return
    try:
        ManimShotSpec.from_options(shot.options or {})
    except ManimRenderError as e:
        ctx.report.add("error", f"{ctx.path}/options", str(e))
        return
    unknown = sorted(set(shot.options or {}) - KNOWN_OPTIONS)
    if unknown:
        ctx.report.add(
            "warning",
            f"{ctx.path}/options",
            f"a Manim shot does not read option(s) {unknown}; it reads "
            f"{sorted(KNOWN_OPTIONS)}",
        )
    missing = [m for m in ("manim", "manimkit") if importlib.util.find_spec(m) is None]
    if missing:
        ctx.report.add(
            "warning",
            f"{ctx.path}/renderer",
            f"this machine cannot render a Manim shot ({', '.join(missing)} not "
            f"importable; env.manim is absent): {INSTALL_HINT}",
        )


def _register_check() -> None:
    from an.genres.registry import SemanticCheck, check_names, register_check

    if "manim.shot" not in check_names():
        register_check(
            SemanticCheck(
                "manim.shot",
                _check_manim_shot,
                order=15,
                description="a Manim shot names its scene file; env.manim is present",
            )
        )


_register_check()
