"""The curated MCP tools: plain functions over the vocabulary, the capability registry and a project.

ADR 0003 decision 6: the MCP surface is a curated list, not all of
``_dispatch_funcs``. Each tool here is an ordinary function with simple,
JSON-shaped arguments and results (so :mod:`py2mcp` can project it, and a test
can call it without any MCP stack):

- **queries** — :func:`vocabulary`, :func:`vocabulary_entry`,
  :func:`scene_schema`, :func:`validate_scene`, :func:`describe_character`,
  :func:`applicable_methods`, :func:`why_not_method`;
- **edits** — :func:`apply_patch`, a typed JSON-pointer patch (the ``an
  iterate`` patch shape), validated before anything is written, ``dry_run`` by
  default;
- **long work as jobs** — :func:`start_render` returns a job id at once and
  :func:`job_status` polls it; nothing blocks a client for minutes. The bench
  stays CLI-only.

Every tool loads the installed genres first (explicit discovery, ADR 0001
decision 3): their presets, methods and analysers are part of the answer.

>>> any(e["id"] == "action.tween" for e in vocabulary(kind="action"))
True
"""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

__all__ = [
    "TOOLS",
    "applicable_methods",
    "apply_patch",
    "describe_character",
    "job_status",
    "scene_schema",
    "start_render",
    "validate_scene",
    "vocabulary",
    "vocabulary_entry",
    "why_not_method",
]

#: Concurrent renders a server runs; more wait their turn (a render is a browser).
DFLT_RENDER_WORKERS: int = 1


def _loaded() -> None:
    from an.genres import load

    load()


# -----------------------------------------------------------------------------
# Queries
# -----------------------------------------------------------------------------


def vocabulary(kind: str = "", owner: str = "") -> list[dict[str, Any]]:
    """Every registered vocabulary entry (presets, kinds, easings, camera moves, methods, IR fields).

    Each entry: id, kind, name (how a document spells it), version, title,
    description, accepted spectrum levels, params (JSON Schema with defaults),
    examples, requires. ``kind`` filters (``motion_preset``, ``method``, …),
    ``owner`` filters by who registered it (``an``, a genre).
    """
    from an.semantic import vocabulary as _vocabulary

    _loaded()
    return _vocabulary(kind=kind or None, owner=owner or None)


def vocabulary_entry(entry_id: str) -> dict[str, Any]:
    """One vocabulary entry by id (``motion.walk``, ``loco.legged_cycle``)."""
    from an.semantic import entry

    _loaded()
    return entry(entry_id).to_json()


#: The documents :func:`scene_schema` describes, and where their models live.
_SCHEMAS: dict[str, tuple[str, str]] = {
    "scene": ("an.ir.schema", "SceneIR"),
    "character": ("an.characters.schema", "CharacterDescriptor"),
}


def scene_schema(document: str = "scene") -> dict[str, Any]:
    """The JSON Schema of a document: ``scene`` (the scene IR) or ``character`` (a descriptor)."""
    from importlib import import_module

    _loaded()
    if document not in _SCHEMAS:
        raise ValueError(
            f"document must be one of {sorted(_SCHEMAS)}, got {document!r}"
        )
    module, name = _SCHEMAS[document]
    return getattr(import_module(module), name).model_json_schema()


def validate_scene(project_dir: str) -> dict[str, Any]:
    """Validate the project's scene (schema and semantics): ``{passed, findings}``."""
    from an.orchestrate import validate_project

    _loaded()
    report = validate_project(project_dir)
    return {
        "passed": report.passed,
        "findings": [
            {
                "severity": f.severity,
                "ir_path": f.ir_path,
                "description": f.description,
                "suggested_fix": getattr(f, "suggested_fix", None),
                "location": getattr(f, "location", None),
            }
            for f in report.findings
        ],
    }


def _character(project_dir: str, name: str) -> tuple[dict[str, Any], dict[str, bool]]:
    from an.capabilities import art_in_dir
    from an.stores import build_project_mall

    store = build_project_mall(project_dir)["characters"]
    if name not in store:
        raise KeyError(
            f"no character {name!r} in {project_dir}'s characters store; "
            f"known: {sorted(store)}"
        )
    doc = dict(store[name])
    folder = store.sidecar_path(name, "character.json").parent
    return doc, art_in_dir(folder, exclude=("character.json",))


def describe_character(project_dir: str, name: str) -> dict[str, Any]:
    """What a character affords, and per aspect the default method, the applicable
    ones, and the missing capabilities (with remedies) of the rest."""
    from an.semantic.describe import describe_asset

    _loaded()
    doc, art = _character(project_dir, name)
    return describe_asset(doc, art)


def applicable_methods(aspect: str, project_dir: str, name: str) -> list[str]:
    """The methods of ``aspect`` (``locomotion``, ``speech``, …) that apply to the character."""
    from an.capabilities import affordances
    from an.semantic import applicable

    _loaded()
    doc, art = _character(project_dir, name)
    return [m.id for m in applicable(aspect, affordances(doc, art))]


def why_not_method(method: str, project_dir: str, name: str) -> list[dict[str, str]]:
    """What the character lacks for ``method`` to apply, each with its remedy (empty: it applies)."""
    from an.capabilities import affordances
    from an.semantic import why_not

    _loaded()
    doc, art = _character(project_dir, name)
    return [w.to_json() for w in why_not(method, affordances(doc, art))]


# -----------------------------------------------------------------------------
# Edits
# -----------------------------------------------------------------------------


def apply_patch(
    project_dir: str, patches: list[dict[str, Any]], dry_run: bool = True
) -> dict[str, Any]:
    """Apply typed JSON-pointer patches to the scene, validated before anything is written.

    ``patches`` are ``{op: set|append|delete, path: "timeline/0/duration",
    value: …}`` (the ``an iterate`` patch shape). The patched scene is validated
    (schema and semantics); with ``dry_run=False`` and a passing validation it
    is saved through the scenes store (``scene.md`` and ``ir/scene.json`` stay
    in step) and the edit is recorded in the decisions log.
    """
    from an.ir.schema import SceneIR
    from an.ir.validate import validate_schema, validate_semantic
    from an.iterate import Patch, _apply_patches_to_ir
    from an.project import load

    _loaded()
    project = load(project_dir)
    typed = [Patch.model_validate(p) for p in patches]
    try:
        new_scene = SceneIR.model_validate(_apply_patches_to_ir(project.scene, typed))
    except Exception as e:  # noqa: BLE001 — returned, never swallowed
        return {"valid": False, "applied": False, "error": f"{type(e).__name__}: {e}"}
    mall = project.mall
    report = validate_schema(new_scene).merge(
        validate_semantic(
            new_scene,
            available_voices=mall.get("voices"),
            available_characters=mall.get("characters"),
            available_props=mall.get("props"),
            available_environments=mall.get("environments"),
            available_sounds=mall.get("sounds"),
        )
    )
    out: dict[str, Any] = {
        "valid": report.passed,
        "applied": False,
        "findings": [
            {"severity": f.severity, "ir_path": f.ir_path, "description": f.description}
            for f in report.findings
        ],
    }
    if report.passed and not dry_run:
        mall["scenes"]["main"] = new_scene
        mall["decisions"].append(
            kind="mcp_patch", body={"patches": [p.model_dump() for p in typed]}
        )
        out["applied"] = True
    return out


# -----------------------------------------------------------------------------
# Long work, as jobs
# -----------------------------------------------------------------------------

_JOBS: dict[str, tuple[str, Future]] = {}
_JOBS_LOCK = threading.Lock()
_EXECUTOR: ThreadPoolExecutor | None = None


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _JOBS_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=DFLT_RENDER_WORKERS, thread_name_prefix="an-mcp-job"
            )
        return _EXECUTOR


def _submit(kind: str, fn, /, *args, **kwargs) -> str:
    job = uuid.uuid4().hex[:12]
    future = _executor().submit(fn, *args, **kwargs)
    with _JOBS_LOCK:
        _JOBS[job] = (kind, future)
    return job


def start_render(
    project_dir: str, strict_assets: bool = False, output_name: str = "main"
) -> dict[str, str]:
    """Start rendering the project to an mp4; returns ``{job}`` at once — poll :func:`job_status`."""
    from an.render import render_project

    _loaded()
    job = _submit(
        "render",
        render_project,
        project_dir,
        output_name=output_name,
        strict_assets=strict_assets,
    )
    return {"job": job, "status": "running"}


def job_status(job: str) -> dict[str, Any]:
    """A job's state: ``running``, ``done`` (with its ``result``) or ``failed`` (with its ``error``)."""
    with _JOBS_LOCK:
        if job not in _JOBS:
            raise KeyError(f"no job {job!r}; known: {sorted(_JOBS)}")
        kind, future = _JOBS[job]
    if not future.done():
        return {"job": job, "kind": kind, "status": "running"}
    error = future.exception()
    if error is not None:
        return {
            "job": job,
            "kind": kind,
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        }
    result = future.result()
    return {
        "job": job,
        "kind": kind,
        "status": "done",
        "result": str(result)
        if isinstance(result, Path)
        else json.loads(json.dumps(result, default=str)),
    }


#: The curated surface, in the order a client lists it.
TOOLS: tuple = (
    vocabulary,
    vocabulary_entry,
    scene_schema,
    validate_scene,
    describe_character,
    applicable_methods,
    why_not_method,
    apply_patch,
    start_render,
    job_status,
)
