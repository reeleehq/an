"""Scene IR — the single source of truth for a scene.

Three layers, per the architectural spec:

- **Narrative** (`scene.md`) — human Markdown with structured fenced blocks.
- **Scene Graph** (`ir/scene.json`) — Pydantic-validated JSON. The SSOT.
- **Render Code** — generated per-backend, disposable.

This subpackage owns layer 2 (the Pydantic schema), the Markdown↔JSON sync that
keeps layer 1 and layer 2 in lock-step, the validators (schema + semantic),
the version migration registry, and the composition combinators that flatten
authoring-time DSL to canonical-form actions.
"""

from an.ir.schema import (
    SceneIR,
    Meta,
    AssetRef,
    Shot,
    Action,
    Dialogue,
    Camera,
    Resolution,
)
from an.ir.compose import (
    set_,
    tween,
    sequence,
    parallel,
    stagger,
    delay,
    loop,
    flatten,
    FlatAction,
)
from an.ir.crowd import crowd, fan_out
from an.ir.validate import (
    validate_schema,
    validate_semantic,
    ValidationReport,
    ValidationFinding,
)
from an.ir.migrate import (
    migrate,
    register_migration,
    register_kind,
    kind_of,
    DocumentKind,
    MIGRATIONS,
    KINDS,
)
from an.ir.sync import markdown_to_ir, ir_to_markdown, sync

__all__ = [
    "SceneIR",
    "Meta",
    "AssetRef",
    "Shot",
    "Action",
    "Dialogue",
    "Camera",
    "Resolution",
    "set_",
    "tween",
    "sequence",
    "parallel",
    "stagger",
    "crowd",
    "fan_out",
    "delay",
    "loop",
    "flatten",
    "FlatAction",
    "validate_schema",
    "validate_semantic",
    "ValidationReport",
    "ValidationFinding",
    "migrate",
    "register_migration",
    "register_kind",
    "kind_of",
    "DocumentKind",
    "KINDS",
    "MIGRATIONS",
    "markdown_to_ir",
    "ir_to_markdown",
    "sync",
]

# Document kinds self-register on import of the package that owns their schema.
# The character descriptor's kind (and its migrations) is registered by `cutan`
# when its genre is loaded (an#225): `migrate()` on an unregistered kind names the
# genre package that provides it.
#
# `play` and `expression` moved to `cutan` with the cut-out genre's action kinds;
# the old names still resolve, with a warning.
from an._shims import moved_names as _moved_names  # noqa: E402

__getattr__ = _moved_names(
    __name__,
    {
        "play": "cutan.characters.registration:play",
        "expression": "cutan.expression.registration:expression",
    },
)
