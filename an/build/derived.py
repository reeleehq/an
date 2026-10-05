"""A renderer's derived stores, as ``an cache gc`` collects them (an#299).

An opaque renderer keeps intermediates of its own beside the shot cache — Manim
its raw pictures, their measurement records and contact sheets — content-keyed,
so every edit adds entries and nothing removes them. A renderer declares them
here, beside its shot keyer (:func:`an.build.keys.register_shot_keyer`), with
:func:`register_derived_stores`; :mod:`an.build.gc` collects every registered
store under the shot cache's guarantees.

A declaration (:class:`DerivedStores`) names:

- ``record_store`` — the store whose entries NAME others (Manim's
  ``measurements``: a record names its picture and its contact sheet), deleted
  first, so a record never names something already gone;
- ``named_stores`` — the stores records name (``pictures``,
  ``contact_sheets``);
- ``entries(renderer, shot, ctx)`` — the record-store keys a render of ``shot``
  under ``ctx`` reads, COMPUTED (never rendered);
- ``provenance(render_provenance)`` — the entries a cached shot's provenance
  names, by store;
- ``names(record_bytes)`` — what one record names, by store; it raises
  :class:`UnreadableRecordError` for bytes it cannot read (a record half
  written by a concurrent render), and the collector then deletes nothing a
  record could name.

A store belongs to one renderer: a second claim is refused, so one renderer's
``names`` never reads another's records.

>>> spec = DerivedStores(
...     record_store="records", named_stores=("blobs",),
...     entries=lambda renderer, shot, ctx: set(),
...     provenance=lambda provenance: {},
...     names=lambda data: {"blobs": {data.decode()}},
... )
>>> sorted(spec.stores)
['blobs', 'records']
>>> sorted(spec.closure({"records": {"r": b"b1"}}, {"records": {"r"}})["blobs"])
['b1']
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DerivedStores",
    "DerivedStoresRegistrationError",
    "UnreadableRecordError",
    "derived_stores_for",
    "register_derived_stores",
    "registered_derived_stores",
]


class UnreadableRecordError(ValueError):
    """A record's bytes cannot be read (half written, damaged)."""


class DerivedStoresRegistrationError(ValueError):
    """A derived-store declaration that cannot be collected safely."""


@dataclass(frozen=True)
class DerivedStores:
    """One renderer's derived stores (see the module docstring)."""

    record_store: str
    named_stores: tuple[str, ...]
    entries: Callable[[Any, Any, Any], set[str]]
    provenance: Callable[[Mapping[str, Any]], dict[str, set[str]]]
    names: Callable[[bytes], dict[str, set[str]]]

    def __post_init__(self) -> None:
        for field_name in ("entries", "provenance", "names"):
            if not callable(getattr(self, field_name)):
                raise DerivedStoresRegistrationError(
                    f"DerivedStores.{field_name} must be callable"
                )
        if self.record_store in self.named_stores:
            raise DerivedStoresRegistrationError(
                f"{self.record_store!r} cannot be both the record store and a named one"
            )

    @property
    def stores(self) -> tuple[str, ...]:
        """Every store, the record store first (the deletion order)."""
        return (self.record_store, *self.named_stores)

    def closure(
        self, mall: Mapping[str, Any], entries: Mapping[str, Iterable[str]]
    ) -> dict[str, set[str]]:
        """``entries`` plus what each of its records names. A record that is
        absent names nothing; one that cannot be read raises
        :class:`UnreadableRecordError`."""
        out = {store: set(keys) for store, keys in entries.items()}
        records = mall.get(self.record_store) if mall else None
        for key in list(out.get(self.record_store, ())):
            if records is None:
                break
            try:
                data = records[key]
            except (KeyError, OSError):
                continue  # absent: names nothing
            for store, keys in self.names(data).items():
                out.setdefault(store, set()).update(keys)
        return out


_REGISTRY: dict[str, DerivedStores] = {}


def register_derived_stores(
    renderer_name: str, spec: DerivedStores, *, replace: bool = False
) -> None:
    """Declare ``renderer_name``'s derived stores for ``an cache gc``.

    Refused: a store another renderer already claims, and a second
    registration for the name unless ``replace`` (a module reloaded passes
    the same stores again, which is allowed)."""
    old = _REGISTRY.get(renderer_name)
    if old is not None and not replace and old.stores != spec.stores:
        raise DerivedStoresRegistrationError(
            f"renderer {renderer_name!r} already declared derived stores {old.stores}"
        )
    for other, theirs in _REGISTRY.items():
        shared = set(theirs.stores) & set(spec.stores)
        if other != renderer_name and shared:
            raise DerivedStoresRegistrationError(
                f"store(s) {sorted(shared)} already belong to renderer {other!r}: "
                "a store has one owner, so one renderer never reads another's records"
            )
    _REGISTRY[renderer_name] = spec


def derived_stores_for(renderer_name: str) -> DerivedStores | None:
    return _REGISTRY.get(renderer_name)


def registered_derived_stores() -> dict[str, DerivedStores]:
    """Every declaration, by renderer name. Loads the renderer registry first
    (a backend behind the import firewall declares when it is imported), its
    load warnings about unrelated backends silenced: they are the render's
    to give."""
    import warnings

    from an.adapters import list_renderers

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            list_renderers()
        except Exception:  # noqa: BLE001 — what did load still declared
            pass
    return dict(_REGISTRY)
