"""What a rendered video owes, and to whom.

`an` composes work it did not create into a video its user ships. Recording where
that work came from (`an.ir.assets.AssetSource`) is half the job; the other half
is being able to *produce* the credits, because **a licence recorded and never
displayed is not compliance** — it is a note to oneself.

So this module walks a project's reachable assets and answers three questions a
user actually has:

- what third-party work is in this video?
- may I ship it at all? (an#211 — material that is all rights reserved, used
  for private study only, is recognised and said LOUDLY: the report opens with
  it, and a render that uses it ends with a warning that it is not
  publishable);
- what must I display, verbatim, to ship it?
- is anything in here unverified?

The last is the one that matters most and is easiest to lose. An asset with no
licence is reported as **UNKNOWN**, never as "nothing owed": those are different
answers, and collapsing them is exactly how an obligation goes missing.

Public domain (`pd`, `public-domain`, `cc-pdm-1.0`, `cc0-*`) is recognised as
nothing owed, and an environment's planes may each carry their own `source`,
so a composite stage — a carved plate plus a CC0 prop — credits both. A
character's (or prop's) attachments may too (an#220): a figure composed from
parts carved out of several clips credits each clip, part by part.
"""

from __future__ import annotations

import hashlib
import json
import warnings

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.ir.assets import AssetSource, LicenseClass, license_class, requires_attribution
from an.stores._common import is_os_junk

__all__ = [
    "CreditsReport",
    "is_factory_stamp",
    "is_generated_source",
    "PrivateStudyWarning",
    "collect_credits",
    "credits_for_project",
    "credits_for_scene",
    "speech_credits",
    "warn_if_private_study",
]


@dataclass(frozen=True)
class CreditEntry:
    """One third-party asset and what it obliges."""

    asset: str
    source: AssetSource
    #: Files this source speaks for that have none of their own, listed so
    #: they are visible in the report (an environment's plates: an#271).
    covers: tuple[str, ...] = ()

    @property
    def attribution_required(self) -> bool | None:
        """``None`` means unknown — which is not the same as ``False``."""
        return requires_attribution(self.source)

    @property
    def license_class(self) -> LicenseClass:
        """``attribution`` / ``free`` / ``private`` / ``unknown`` (an#211)."""
        return license_class(self.source)

    @property
    def own_work(self) -> bool:
        """Whether ``an`` itself made it (the character factory, the sound
        synthesizer) — recorded, but not third-party work and nothing owed."""
        return self.source.provider in _own_work_providers() and (
            self.license_class == "free"
        )


def _own_work_providers() -> frozenset[str]:
    """The providers of the sources ``an`` writes on what it generates itself."""
    from an.characters.factory import FACTORY_PROVIDER
    from an.sounds import SYNTH_SOURCE

    return frozenset({FACTORY_PROVIDER, SYNTH_SOURCE.provider})


@dataclass
class CreditsReport:
    """Everything a project owes, split by whether we actually know."""

    entries: list[CreditEntry] = field(default_factory=list)

    @property
    def owed(self) -> list[CreditEntry]:
        """Entries that definitely require an attribution."""
        return [e for e in self.entries if e.license_class == "attribution"]

    @property
    def private(self) -> list[CreditEntry]:
        """Entries that may NOT be published: all rights reserved, private
        study only (an#211). A video containing any of them is not shippable,
        whatever else it credits."""
        return [e for e in self.entries if e.license_class == "private"]

    @property
    def publishable(self) -> bool:
        """``False`` when any entry is private-study material."""
        return not self.private

    @property
    def unverified(self) -> list[CreditEntry]:
        """Entries whose licence we could not classify.

        Deliberately its own list rather than folded into :attr:`owed`. Folding
        them in cries wolf; folding them into "nothing owed" hides a real
        obligation. Neither is honest, so they are counted separately — the same
        reason `priv`'s upkeep keeps `unavailable` apart from `findings`.
        """
        return [e for e in self.entries if e.license_class == "unknown"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "assets": [
                {
                    "asset": e.asset,
                    **e.source.model_dump(exclude_none=True),
                    **({"covers": list(e.covers)} if e.covers else {}),
                }
                for e in self.entries
            ],
            "attribution_required": [
                {"asset": e.asset, "text": e.source.attribution} for e in self.owed
            ],
            "unverified": [e.asset for e in self.unverified],
            "private_study": [e.asset for e in self.private],
            "own_work": [e.asset for e in self.entries if e.own_work],
            "publishable": self.publishable,
        }

    def format(self) -> str:
        """Human-readable, and honest about what it does not know."""
        own = [e for e in self.entries if e.own_work]
        third_party = [e for e in self.entries if not e.own_work]
        made_here = (
            f"{len(own)} asset(s) made by an itself (nothing owed)" if own else ""
        )
        if not third_party:
            if not own:
                return "credits: no third-party assets recorded."
            lines = [f"credits: no third-party assets recorded; {made_here}."]
            lines.append("")
            lines.append(f"Made by an itself, nothing owed ({len(own)}):")
            lines += [f"  {e.asset}: {e.source.provider}" for e in own]
            return "\n".join(lines)
        lines = [
            f"credits: {len(third_party)} third-party asset(s)"
            + (f"; {made_here}." if own else ".")
        ]
        if self.private:
            lines.append("")
            lines.append(
                f"NOT PUBLISHABLE — {len(self.private)} asset(s) are all rights "
                "reserved, for PRIVATE STUDY ONLY. A video containing them must "
                "not be published, uploaded or shared, credited or not:"
            )
            for e in self.private:
                lines.append(f"  {e.asset}: {_private_label(e.source)}")
        if self.owed:
            lines.append("")
            lines.append("MUST BE DISPLAYED to ship this video:")
            for e in self.owed:
                text = e.source.attribution or (
                    f"(licence {e.source.license!r} requires attribution but none "
                    "was recorded — the record is incomplete)"
                )
                lines.append(f"  {e.asset}: {text}{_detail(e)}")
        if self.unverified:
            lines.append("")
            lines.append(
                "UNVERIFIED — licence unknown or unrecognised. Unknown is not "
                "the same as unencumbered; check before shipping:"
            )
            for e in self.unverified:
                lines.append(f"  {e.asset}: license={e.source.license!r}{_detail(e)}")
        clear = [e for e in third_party if e.license_class == "free"]
        if clear:
            lines.append("")
            lines.append(f"No attribution required ({len(clear)}):")
            for e in clear:
                lines.append(f"  {e.asset}: {e.source.license}{_detail(e)}")
        if own:
            lines.append("")
            lines.append(f"Made by an itself, nothing owed ({len(own)}):")
            lines += [f"  {e.asset}: {e.source.provider}" for e in own]
        return "\n".join(lines)


def _detail(e: CreditEntry) -> str:
    """What a report line adds after the licence: a speech take's provider,
    voice and model, and the files a source covers."""
    out = ""
    extra = e.source.extra or {}
    if SPEECH_EXTRA_MODEL in extra or e.asset.startswith(SPEECH_PREFIX):
        bits = [e.source.provider, f"voice {e.source.id}" if e.source.id else ""]
        if extra.get(SPEECH_EXTRA_MODEL):
            bits.append(f"model {extra[SPEECH_EXTRA_MODEL]}")
        if extra.get("lines"):
            bits.append(f"{extra['lines']} line(s)")
        out += " (" + ", ".join(b for b in bits if b) + ")"
    if e.covers:
        out += f" — covers {', '.join(e.covers)}"
    return out


def _private_label(source: AssetSource) -> str:
    where = source.source_page_url or source.url or source.id or source.provider
    return f"license={source.license!r}, from {where}"


class CreditsWarning(UserWarning):
    """A credits walk could not read something it was asked to read."""


class PrivateStudyWarning(UserWarning):
    """A render used material that is all rights reserved, private study only.

    Raised as a warning at the END of a render (an#211), so the last thing the
    author reads about the mp4 is that it must not be published.
    """


def collect_credits(
    mall: Mapping[str, Any], *, only: "set[str] | None" = None
) -> CreditsReport:
    """Walk a project mall and gather every recorded :class:`AssetSource`.

    ``only`` restricts the walk to those ``store/key`` names (what a render
    used, :func:`credits_for_scene`) — nothing else is read.

    Four stores carry provenance: characters, **props** (an#108),
    **environments** (an#110) and **sounds**. Each was added by the PR that gave that store
    real art, which is the rule rather than a coincidence — a walk that skips a
    store holding third-party plates does not return less information, it
    returns an affirmative false statement to exactly the people who need the
    opposite. **Sounds** joined with the sound layer (an#163) — a sound is
    third-party work more often than any other asset. Styles will join when a
    StylePack has art (#112).

    Legacy reconstruction runs on characters only: it recovers a DiceBear
    record from `metadata.dicebear_*`, which no other store has ever written.
    """
    report = CreditsReport()
    for store_name in ("characters", "props", "environments", "sounds"):
        store = mall.get(store_name)
        if store is None:
            continue
        try:
            keys = sorted(
                store
                if only is None
                else (
                    k
                    for k in (
                        u.split("/", 1)[1]
                        for u in only
                        if u.startswith(store_name + "/")
                    )
                    if k in store
                )
            )
        except Exception:  # noqa: BLE001 — see below
            # The ITERATION, not just the per-key read. an#110 took this walk
            # from one store to three, so an unreadable backing store went from
            # "characters are missing" to "`an credits` raises" — and a credits
            # report that cannot run is the one output whose absence is
            # indistinguishable from "no third-party assets", which is the
            # false compliance statement this module exists to avoid.
            warnings.warn(
                f"the {store_name!r} store could not be listed, so its assets are "
                "absent from this report. That is a GAP, not a clean bill: "
                "re-run when the store is readable.",
                CreditsWarning,
                stacklevel=2,
            )
            continue
        for key in keys:
            try:
                descriptor = store[key]
            except Exception:  # noqa: BLE001 — an unreadable entry is not a credit
                continue
            source = getattr(descriptor, "source", None)
            if source is None and isinstance(descriptor, Mapping):
                raw = descriptor.get("source")
                source = _source_or_unknown(raw, f"{store_name}/{key}") if raw else None
                left = _checked_out(descriptor)
                if source is None and left is not None and left.get("source"):
                    # The label a library check-out left here was removed: what
                    # the copy is now, nobody has said (an#264). Never silence.
                    source = AssetSource(
                        provider="unknown",
                        extra={
                            "reason": "the source a library check-out left on this "
                            "copy was removed since"
                        },
                    )
            if source is None and store_name == "characters":
                source = _reconstruct_legacy_source(descriptor)
            found: list[CreditEntry] = []
            if source is not None:
                found.append(CreditEntry(asset=f"{store_name}/{key}", source=source))
            if store_name == "environments":
                planes = _plane_credits(key, descriptor)
                plates = _unsourced_plates(descriptor)
                if found:
                    # The environment's source speaks for its plates: say which.
                    found[0] = CreditEntry(found[0].asset, found[0].source, plates)
                else:
                    # No source anywhere: each plate is unverified, never silent.
                    planes += [
                        CreditEntry(
                            asset=f"environments/{key}/planes/{name}",
                            source=AssetSource(
                                provider="unknown",
                                extra={
                                    "reason": "a plate with no source, in an "
                                    "environment that declares none",
                                    "file": src,
                                },
                            ),
                        )
                        for name, src in _unsourced_plate_names(descriptor)
                    ]
                found.extend(planes)
            if store_name in ("characters", "props"):
                parts = _part_credits(
                    store_name, key, descriptor, digests=_digests_of(store, key)
                )
                # A part stamped with the descriptor's own source (DiceBear's
                # head) owes what the descriptor owes: one credit, not two.
                said = {_source_identity(source)} if source is not None else set()
                found.extend(e for e in parts if _source_identity(e.source) not in said)
            # A check-out's recorded contributors that say exactly what this
            # entry already says (the same source restated by the version it
            # follows) are one statement, not two credits.
            shown = [_source_identity(e.source) for e in found]
            found.extend(
                e
                for e in _library_origin_credits(store_name, key, descriptor)
                if _source_identity(e.source) not in shown
            )
            report.entries.extend(found)
    return report


def _source_identity(source: AssetSource) -> str:
    """What a source says, whichever bytes it pins (its ``sha256`` left out)."""
    return source.model_dump_json(exclude_defaults=True, exclude={"sha256"})


def referenced_paths(descriptor: Any) -> frozenset[str]:
    """Every file a descriptor itself names: its drawing, its parts, its plates.

    Such a file is never operating-system clutter, whatever its name: a part
    stored as ``parts/.secret.svg`` is drawn, so it is credited and published
    (review-288 S2).

    >>> sorted(referenced_paths({"source_svg": "a.svg", "skins": {"default": {"slots":
    ...     {"head": {"head": {"path": "parts/.h.svg"}}}}}}))
    ['a.svg', 'parts/.h.svg']
    """
    raw = descriptor if isinstance(descriptor, Mapping) else None
    if raw is None and hasattr(descriptor, "model_dump"):
        raw = descriptor.model_dump(mode="json")
    raw = raw or {}
    out: set[str] = set()
    if isinstance(raw.get("source_svg"), str):
        out.add(raw["source_svg"])
    for skin in (raw.get("skins") or {}).values():
        for attachments in (
            ((skin or {}).get("slots") or {}).values()
            if isinstance(skin, Mapping)
            else ()
        ):
            for att in (
                (attachments or {}).values() if isinstance(attachments, Mapping) else ()
            ):
                if isinstance(att, Mapping) and isinstance(att.get("path"), str):
                    out.add(att["path"])
    for plane in raw.get("planes") or []:
        art = plane.get("art") if isinstance(plane, Mapping) else None
        if isinstance(art, Mapping) and isinstance(art.get("src"), str):
            out.add(art["src"])
    return frozenset(out)


def is_clutter(rel: str, referenced: frozenset[str] = frozenset()) -> bool:
    """OS clutter (:func:`an.stores._common.is_os_junk`) that the descriptor does not name."""
    return is_os_junk(rel) and rel not in referenced


def _digests_of(store: Any, key: str) -> Callable[[], Mapping[str, str] | None]:
    """A lazy ``{relative path: sha256}`` of the files beside ``store[key]``.

    Read only when a provenance stamp has to be checked against the bytes it
    claims (a factory stamp is only true of the bytes it pins). A store may
    provide them itself (``file_digests(key)`` — the asset library does, for a
    version that is not on disk); a folder store is hashed from its sidecars;
    anything else gives ``None``: unknowable, so stamps are taken as written.
    Operating-system clutter is not an asset (:func:`an.stores._common.is_os_junk`,
    the rule a publish and a check-out apply too).
    """
    memo: list[Mapping[str, str] | None] = []

    def compute() -> Mapping[str, str] | None:
        provided = getattr(store, "file_digests", None)
        if callable(provided):
            return provided(key)
        meta = getattr(store, "META_NAME", None)
        sidecar = getattr(store, "sidecar_path", None)
        if meta is None or not callable(sidecar):
            return None
        try:
            entry = Path(sidecar(key, meta)).parent
            if not entry.is_dir():
                return None
            out: dict[str, str] = {}
            try:
                named = referenced_paths(store[key])
            except Exception:  # noqa: BLE001 — unreadable: clutter by name alone
                named = frozenset()
            for path in sorted(entry.rglob("*")):
                rel = path.relative_to(entry).as_posix()
                if not path.is_file() or rel == meta or is_clutter(rel, named):
                    continue
                out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
            return out
        except (OSError, ValueError):
            return None

    def get() -> Mapping[str, str] | None:
        if not memo:
            memo.append(compute())
        return memo[0]

    return get


#: Where a library check-out records itself in a descriptor (ADR 0005); the
#: library writes it (`an.library.api.ORIGIN_KEY`), this walk only reads it.
LIBRARY_ORIGIN_KEY: str = "library_origin"
#: The origin-block entry a check-out of a version with an asset-level source
#: writes (an#264): ``{"source": <the descriptor's source as the check-out left
#: it>, "files": {path: sha256}}``. That label was declared on those bytes, so
#: in the copy it speaks only for them — as the library reads it when the copy
#: is published back (a carried source covers only files unchanged since).
CHECKED_OUT_KEY: str = "checked_out"


def _origin_of(raw: Mapping[str, Any]) -> Mapping[str, Any] | None:
    metadata = raw.get("metadata")
    origin = metadata.get(LIBRARY_ORIGIN_KEY) if isinstance(metadata, Mapping) else None
    return origin if isinstance(origin, Mapping) else None


def same_source(a: Any, b: Any) -> bool:
    """Whether two recorded sources say the same thing, however they were serialised.

    A tool that rewrites a descriptor through its model (``an character
    mouths``) writes every default out (``"attribution": null``…); that is
    still the source a check-out left there, not a new one a person wrote.

    >>> same_source({"provider": "me", "license": "cc0-1.0"},
    ...             {"provider": "me", "license": "cc0-1.0", "attribution": None, "extra": {}})
    True
    >>> same_source({"provider": "me"}, {"provider": "you"}), same_source(None, None)
    (False, True)
    """
    if a is None or b is None:
        return a is b

    def norm(raw: Any) -> Any:
        try:
            return AssetSource.model_validate(dict(raw)).model_dump(
                mode="json", exclude_none=True, exclude_defaults=True
            )
        except (TypeError, ValueError):
            return raw

    return norm(a) == norm(b)


def checked_out_seal(source: Any, files: Mapping[str, str]) -> str:
    """The digest binding a ``checked_out`` block's source to its file digests.

    >>> len(checked_out_seal({"provider": "me"}, {"a.svg": "00"}))
    64
    """
    payload = json.dumps(
        {"source": source, "files": dict(files)}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _checked_out(raw: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The ``checked_out`` block of a library check-out, if this copy has one.

    A block whose seal does not match what it says (an edited digest list) is
    read as covering NO file: an origin block may make credits stricter, never
    cleaner (review-269 S1).
    """
    block = (_origin_of(raw) or {}).get(CHECKED_OUT_KEY)
    if not isinstance(block, Mapping) or not isinstance(block.get("files"), Mapping):
        return None
    if block.get("seal") != checked_out_seal(block.get("source"), block["files"]):
        return {**block, "files": {}}
    return block


def _library_origin_credits(
    store_name: str, key: str, descriptor: Any
) -> list[CreditEntry]:
    """The sources a library check-out recorded BESIDE the descriptor (an#234).

    A library version's rights can come from places the descriptor does not
    hold: a source the publisher declared for the asset as a whole, and the
    rights of every version it derives from (a recolour of a carved puppet is
    as private as the puppet). Check-out records those contributors in
    ``metadata.library_origin.sources``; without this walk they would vanish
    from the project, and the private-study warning would never fire for
    checked-out study material — the false clean bill this module exists to
    prevent.

    >>> d = {"metadata": {"library_origin": {"library": "cutan:prop.vase@v001",
    ...     "sources": [{"label": "asset", "source": {"provider": "film",
    ...                  "license": "all-rights-reserved"}}]}}}
    >>> [(e.asset, e.license_class) for e in _library_origin_credits("props", "vase", d)]
    [('props/vase/via-library/asset', 'private')]
    """
    raw = descriptor if isinstance(descriptor, Mapping) else None
    if raw is None and hasattr(descriptor, "model_dump"):
        raw = descriptor.model_dump(mode="json")
    origin = _origin_of(raw or {})
    if origin is None:
        return []
    out: list[CreditEntry] = []
    for item in origin.get("sources") or []:
        if not isinstance(item, Mapping):
            continue
        asset = f"{store_name}/{key}/via-library/{item.get('label', '?')}"
        raw_source = item.get("source")
        source = (
            _source_or_unknown(raw_source, asset)
            if raw_source
            else AssetSource(
                provider="unknown", extra={"library": origin.get("library")}
            )
        )
        out.append(CreditEntry(asset=asset, source=source))
    return out


def _source_or_unknown(raw: Any, asset: str) -> AssetSource:
    """``raw`` as an `AssetSource`; a malformed one is reported UNVERIFIED.

    A `source` that is not a record (a bare string, a list) is still a claim
    somebody wrote about provenance. Raising would make a credits walk — and
    the check at the end of every render — fail on an asset the render may
    not even use; dropping it would be a false clean bill. Unknown is honest.
    """
    try:
        return AssetSource.model_validate(raw)
    except ValueError:
        warnings.warn(
            f"{asset}: its `source` is not an AssetSource record ({raw!r}); it is "
            "reported with an UNKNOWN licence.",
            CreditsWarning,
            stacklevel=3,
        )
        return AssetSource(provider="unknown", extra={"raw": raw})


def _unsourced_plate_names(descriptor: Any) -> list[tuple[str, str]]:
    """``(plane name, file)`` of every image plane that declares no source of its own."""
    raw = descriptor if isinstance(descriptor, Mapping) else None
    if raw is None and hasattr(descriptor, "model_dump"):
        raw = descriptor.model_dump(mode="json")
    out: list[tuple[str, str]] = []
    for plane in (raw or {}).get("planes") or []:
        if not isinstance(plane, Mapping) or plane.get("source"):
            continue
        art = plane.get("art")
        if isinstance(art, Mapping) and art.get("kind") == "image" and art.get("src"):
            out.append((str(plane.get("name", "?")), str(art["src"])))
    return out


def _unsourced_plates(descriptor: Any) -> tuple[str, ...]:
    return tuple(src for _, src in _unsourced_plate_names(descriptor))


def _plane_credits(key: str, descriptor: Any) -> list[CreditEntry]:
    """One entry per plane that declares its OWN `source` (an#211).

    A composite stage — a plate carved from a film under one licence, a CC0
    prop under another — cannot be described by one environment `source`, and
    a credits walk that reads only that one silently drops the second.
    """
    raw = descriptor if isinstance(descriptor, Mapping) else {}
    out: list[CreditEntry] = []
    for plane in raw.get("planes") or []:
        if not isinstance(plane, Mapping) or not plane.get("source"):
            continue
        source = _source_or_unknown(
            plane["source"], f"environments/{key}/planes/{plane.get('name', '?')}"
        )
        out.append(
            CreditEntry(
                asset=f"environments/{key}/planes/{plane.get('name', '?')}",
                source=source,
            )
        )
    return out


def _part_credits(
    store_name: str,
    key: str,
    descriptor: Any,
    *,
    digests: Callable[[], Mapping[str, str] | None] | None = None,
) -> list[CreditEntry]:
    """One entry per part (attachment) that declares its OWN `source` (an#220).

    A character carved from several clips — a head from one, the arms from
    another — cannot be credited by one descriptor `source`. Keyed by the part's
    PATH, once, whichever slots or skins name it: the credit is for the art,
    and one file used by two attachments is one piece of work.

    **A stamp is true only of the bytes it pins** (an#249, an#251, review-259).
    The character factory stamps each part it draws, and the descriptor, as its
    own ``cc0`` work; a DiceBear head and the drawing wrapping it carry
    DiceBear's source the same way; each pinned to a SHA-256 (a descriptor's
    stamp pins its ``source_svg``). With the files' ``digests`` known:

    - a part whose pinned digest matches its file is itemised by that source
      (the factory's own is not listed: not third-party, nothing owed);
    - a part whose pinned digest no longer matches (re-drawn or re-carved since)
      speaks for nothing: it is UNVERIFIED, unless the descriptor declares a
      source a PERSON wrote, which then speaks for it. A stale claim that is
      ``private`` is still listed as such — stricter never gives way;
    - under a generator's descriptor-level source (the factory's, DiceBear's),
      every file no stamp pins is UNVERIFIED: a generator made claims only about
      the bytes it produced. A LEGACY generated source that pins no digest
      (DiceBear before an#259) pins nothing, so it speaks for nothing either
      (an#264, R2b-N3) — the factory re-pins it on its next touch
      (``stamp_generated_head``);
    - in a library check-out, the source the check-out left in the descriptor
      (the version's asset-level label, ``metadata.library_origin.checked_out``)
      was declared on the version's bytes: while the descriptor still holds it,
      a file changed or added since the check-out is UNVERIFIED (an#264) — what
      the library says when the copy is published back. A source a person
      writes in its place speaks for the copy as it is.

    The asset library reads the same walk (:mod:`an.library.rights`), so the
    library and ``an credits`` agree about which bytes are the factory's.

    >>> d = {"skins": {"default": {"slots": {"head": {"head": {
    ...     "path": "parts/head.png",
    ...     "source": {"provider": "youtube", "license": "all-rights-reserved"}}}}}}}
    >>> [e.asset for e in _part_credits("characters", "bob", d)]
    ['characters/bob/parts/head.png']
    """
    raw = descriptor if isinstance(descriptor, Mapping) else None
    if raw is None and hasattr(descriptor, "model_dump"):
        raw = descriptor.model_dump(mode="json")
    raw = raw or {}
    own = raw.get("source")
    generated = is_generated_source(own)
    # Only a source a person wrote speaks for parts nothing itemises; a source a
    # machine wrote (the factory's, DiceBear's) speaks for what it pins.
    covered = isinstance(own, Mapping) and not generated

    def known() -> Mapping[str, str] | None:  # hashed only if a stamp needs it
        return digests() if digests is not None else None

    out: dict[str, CreditEntry] = {}
    pinned: set[str] = set()
    pinned_here: set[str] = set()  # a source pinned to the file's CURRENT bytes
    stale: set[str] = set()
    unconfirmed: set[str] = (
        set()
    )  # factory stamps the factory's record does not confirm
    for skin in (raw.get("skins") or {}).values():
        if not isinstance(skin, Mapping):
            continue
        for attachments in (skin.get("slots") or {}).values():
            if not isinstance(attachments, Mapping):
                continue
            for att in attachments.values():
                if not isinstance(att, Mapping) or att.get("source") is None:
                    continue  # an empty `{}` is still a claim: reported UNKNOWN
                path = str(att.get("path", "?"))
                source = att["source"]
                sha = _stamp_digest(source) if isinstance(source, Mapping) else None
                if sha is not None:
                    files = known()
                    if files is None or sha == files.get(path):
                        pinned.add(path)
                        if files is not None:
                            pinned_here.add(path)
                    else:
                        stale.add(path)  # a claim about other bytes
                else:
                    pinned.add(path)
                if is_factory_stamp(source):
                    if path in stale:
                        continue  # a stamp about other bytes: unverified below, as stale
                    if sha is not None and factory_recorded(sha):
                        continue  # this package drew it: nothing owed, not third-party
                    # A stamp in a descriptor proves nothing: unconfirmed by the
                    # factory's own record, it labels nothing (review-288 B1).
                    pinned.discard(path)
                    pinned_here.discard(path)
                    stale.discard(path)
                    unconfirmed.add(path)
                    continue
                asset = f"{store_name}/{key}/{path}"
                if asset not in out:
                    out[asset] = CreditEntry(
                        asset=asset, source=_source_or_unknown(source, asset)
                    )
    left = _checked_out(raw)
    since = (
        left["files"]
        if covered and left is not None and same_source(left.get("source"), own)
        else None
    )
    if not covered or since is not None:
        unpinned = set(stale - pinned) | unconfirmed if not covered else set()
        files = known() if generated or since is not None else None
        changed: set[str] = set()
        if files is not None and since is not None:
            # As the library reads a carried label: every file changed or
            # added since, unless a source pinned to its new bytes labels it
            # (an.library.api.publish; an#281).
            changed = {
                path
                for path, digest in files.items()
                if since.get(path) != digest and path not in pinned_here
            }
            unpinned |= changed
        elif files is not None:
            svg = raw.get("source_svg")
            unpinned |= {
                path
                for path, digest in files.items()
                if path not in pinned
                and not (
                    path == svg
                    and digest == _stamp_digest(own)
                    and (not is_factory_stamp(own) or factory_recorded(digest))
                )
            }
        for path in sorted(unpinned):
            asset = f"{store_name}/{key}/{path}"
            if asset in out and out[asset].license_class == "private":
                continue  # a stale claim stricter than unknown still binds
            # Otherwise it replaces a stale claim's entry: that speaks for other bytes.
            out[asset] = CreditEntry(
                asset=asset,
                source=AssetSource(
                    provider="unknown",
                    extra={
                        NOBODY_LABELLED: True,
                        "reason": (
                            "changed or added since the library check-out: the "
                            "label it carried speaks only for the bytes it was "
                            "declared on"
                            if path in changed
                            else "a factory stamp the factory's own record of what "
                            "it drew does not confirm"
                            if path in unconfirmed
                            else "the stamp on this part no longer matches its bytes "
                            "(re-drawn or re-carved)"
                            if path in stale
                            else "no stamp pins these bytes, and the descriptor's "
                            "source was written by a generator, not a person"
                        )
                    },
                ),
            )
    return [out[a] for a in sorted(out)]


#: The ``extra`` flag of an entry no person's source speaks for: a part no
#: stamp pins under a generated descriptor source, a stale or unconfirmed stamp,
#: a file changed since a check-out. Nobody STATED anything about those bytes —
#: a gap, which an explicit, recorded label answers (an#307), unlike a source
#: someone wrote with a licence nobody recognises.
NOBODY_LABELLED: str = "nobody_labelled"


def nobody_labelled(source: Any) -> bool:
    """Whether a credits entry's source is the walk's own placeholder for bytes nobody labelled.

    >>> nobody_labelled(AssetSource(provider="unknown", extra={NOBODY_LABELLED: True}))
    True
    >>> nobody_labelled(AssetSource(provider="unknown"))
    False
    """
    return isinstance(source, AssetSource) and bool(
        (source.extra or {}).get(NOBODY_LABELLED)
    )


#: Providers whose descriptor-level source a GENERATOR writes (the character
#: factory, DiceBear through the factory): such a source speaks only for the
#: bytes a stamp pins, never for a part re-carved or added since.
GENERATED_PROVIDERS: frozenset[str] = frozenset({"dicebear"})


def gives_way_to_a_label(raw: Any) -> bool:
    """Whether an explicit asset-level label may stand in for this descriptor source (an#281).

    A generator's own source that owes nothing — the factory's stamp, or a
    DiceBear style under a free licence — speaks only for the bytes it pins,
    so an explicit label may speak for the rest in its place. One that owes
    something (a CC BY style) never gives way: replacing it would drop the
    attribution it obliges.

    >>> gives_way_to_a_label({"provider": "dicebear", "license": "cc0-1.0"})
    True
    >>> gives_way_to_a_label({"provider": "dicebear", "license": "cc-by-4.0"})
    False
    >>> gives_way_to_a_label({"provider": "a person", "license": "cc0-1.0"})
    False
    """
    if is_factory_stamp(raw):
        return True
    if not is_generated_source(raw):
        return False
    try:
        return license_class(AssetSource.model_validate(dict(raw))) == "free"
    except (TypeError, ValueError):
        return False


def factory_recorded(digest: str) -> bool:
    """Whether this machine's record says the character factory drew the bytes ``digest``.

    The record (``an.library.registry.generated_by``) is written only by the
    factory's own drawing code, from the bytes it wrote; a factory stamp in a
    descriptor counts as the factory's only when the record confirms it
    (review-288 B1). Read fail-safe: unreadable is unconfirmed.
    """
    from an.characters.factory import FACTORY_PROVIDER
    from an.library.registry import generated_by

    return FACTORY_PROVIDER in generated_by(str(digest).removeprefix("sha256:"))


def is_generated_source(raw: Any) -> bool:
    """Whether a descriptor's source was written by a generator rather than a person.

    >>> is_generated_source({"provider": "dicebear", "license": "cc0-1.0"})
    True
    >>> is_generated_source({"provider": "a-film", "license": "all-rights-reserved"})
    False
    """
    return is_factory_stamp(raw) or (
        isinstance(raw, Mapping) and raw.get("provider") in GENERATED_PROVIDERS
    )


def _stamp_digest(raw: Any) -> str | None:
    sha = str((raw or {}).get("sha256") or "").strip().lower()
    return sha.removeprefix("sha256:") or None


def is_factory_stamp(raw: Any) -> bool:
    """Whether a source is the character factory's own stamp (an#236, an#251).

    The factory stamps every part it draws ``cc0`` with the part's digest, and
    the descriptor with its ``source_svg``'s, so the asset library can tell its
    shared parts from carved ones. It is ``an``'s own work, not third-party: a
    credits report lists what is OWED, and listing fifty generated parts per
    character would bury the one carved head.
    """
    from an.characters.factory import FACTORY_LICENSE, FACTORY_PROVIDER

    # Both fields: a record naming the factory but another licence is not the
    # factory's stamp — it is a claim, and is reported (and counted) as one.
    return (
        isinstance(raw, Mapping)
        and raw.get("provider") == FACTORY_PROVIDER
        and raw.get("license") == FACTORY_LICENSE
    )


_is_factory_stamp = is_factory_stamp


#: Where synthesized speech is listed in a report.
SPEECH_PREFIX: str = "speech/"
#: The ``extra`` key of a speech entry naming the provider's model.
SPEECH_EXTRA_MODEL: str = "model"
#: Providers whose speech is ``an``'s own (silence, for tests and drafts).
OWN_SPEECH_PROVIDERS: frozenset[str] = frozenset({"offline"})


def speech_credits(mall: Mapping[str, Any], scene: Any) -> list[CreditEntry]:
    """One entry per voice whose lines a render synthesized with a named provider (an#271).

    Read from what the audio pipeline already keeps — no record of its own:
    the scene's lines that carry an ``audio_ref`` (stamped when synthesized),
    each line's voice as the pipeline resolves it
    (:func:`an.audio.voices.line_voice_id`), and that voice's document in
    ``mall["voices"]`` (its ``provider``, ``voice_id`` and ``model_id``). A
    voice document may declare its own ``source`` (the provider's terms, the
    licence the user holds); otherwise the speech is listed UNVERIFIED — the
    provider's terms decide what is owed, and nobody recorded them. The licence
    that counts for synthesized speech is a provider-terms code
    (:data:`an.ir.assets.PROVIDER_TERMS`: ``elevenlabs-paid-plan`` is ``free``,
    ``elevenlabs-free-plan`` owes a credit), or any licence ``an`` recognises;
    it is read as the voice's provider's, so another provider's terms count for
    nothing (an#307). A voice
    whose document names no provider (the offline default) is not listed:
    which provider spoke it is not recorded anywhere.

    >>> from types import SimpleNamespace as NS
    >>> line = NS(voice_ref="bob", speaker="bob", audio_ref="k1")
    >>> scene = NS(timeline=[NS(dialogue=[line], entities=[])])
    >>> mall = {"voices": {"bob": {"provider": "elevenlabs", "voice_id": "TX3",
    ...                            "model_id": "eleven_v3"}}}
    >>> [(e.asset, e.license_class, e.source.extra["model"]) for e in speech_credits(mall, scene)]
    [('speech/bob', 'unknown', 'eleven_v3')]
    >>> mall["voices"]["bob"]["source"] = {"provider": "elevenlabs", "license": "elevenlabs-paid-plan"}
    >>> [e.license_class for e in speech_credits(mall, scene)]
    ['free']
    """
    from an.audio.voices import line_voice_id, voice_document

    lines: dict[str, int] = {}
    for shot in getattr(scene, "timeline", None) or []:
        for line in getattr(shot, "dialogue", None) or []:
            if not getattr(line, "audio_ref", None):
                continue
            voice = line_voice_id(line, shot, mall)
            lines[voice] = lines.get(voice, 0) + 1
    out: list[CreditEntry] = []
    for voice, n in sorted(lines.items()):
        doc = voice_document(mall, voice)
        provider = str(doc.get("provider") or "")
        if not provider or provider.lower() in OWN_SPEECH_PROVIDERS:
            continue
        said = {
            SPEECH_EXTRA_MODEL: doc.get("model_id"),
            "voice": voice,
            "lines": n,
        }
        declared = doc.get("source")
        if isinstance(declared, Mapping):
            base = _source_or_unknown(declared, f"{SPEECH_PREFIX}{voice}")
            if base.provider != "unknown" and base.provider.lower() != provider.lower():
                # Terms declared for another provider say nothing about this one's speech.
                said["declared_provider"] = base.provider
            source = base.model_copy(
                update={
                    # The provider that SPOKE it: its own terms are the ones that count
                    # (an.ir.assets.PROVIDER_TERMS), whatever the declaration names.
                    "provider": provider,
                    "id": base.id or doc.get("voice_id"),
                    "extra": {**(base.extra or {}), **said},
                }
            )
        else:
            source = AssetSource(
                provider=provider,
                id=doc.get("voice_id") or voice,
                extra={
                    **said,
                    "reason": "synthesized speech: the provider's terms decide what "
                    "is owed; declare them as the voice's `source`",
                },
            )
        out.append(CreditEntry(asset=f"{SPEECH_PREFIX}{voice}", source=source))
    return out


def credits_for_scene(mall: Mapping[str, Any], scene: Any) -> CreditsReport:
    """Credits for exactly the assets ``scene`` draws or plays (an#211).

    :func:`collect_credits` walks the whole project; a render owes only what it
    used, and a private-study plate sitting unused in the store must not make
    an unrelated render "not publishable". Kept: every entry under a
    ``store/ref`` some shot's entity names, and every sound a cue names.
    """
    used: set[str] = set()
    for shot in getattr(scene, "timeline", None) or []:
        for entity in shot.entities:
            if entity.store and entity.ref:
                used.add(f"{entity.store}/{entity.ref}")
        for cue in getattr(shot, "sounds", None) or []:
            used.add(f"sounds/{cue.sound}")
    for cue in getattr(getattr(scene, "meta", None), "sounds", None) or []:
        used.add(f"sounds/{cue.sound}")
    full = collect_credits(mall, only=used)
    return CreditsReport(
        entries=[
            e
            for e in full.entries
            if any(e.asset == u or e.asset.startswith(u + "/") for u in used)
        ]
        + speech_credits(mall, scene)
    )


def warn_if_private_study(report: CreditsReport, *, output: Any = None) -> bool:
    """Warn, loudly, when ``report`` holds private-study material.

    Returns whether it warned. Called at the end of a render, so the warning is
    the last word about the file; ``output`` names it.
    """
    if report.publishable:
        return False
    what = f"{output} " if output else "this render "
    warnings.warn(
        f"{what}is NOT PUBLISHABLE: it contains {len(report.private)} asset(s) "
        "that are all rights reserved, for private study only — "
        + ", ".join(e.asset for e in report.private)
        + ". Keep it private; do not upload, publish or share it. "
        "`an credits <project>` lists them.",
        PrivateStudyWarning,
        stacklevel=2,
    )
    return True


def _reconstruct_legacy_source(descriptor: Any) -> AssetSource | None:
    """Recover provenance from a descriptor written before ``source`` existed.

    **The users most at risk are the ones with no ``source`` field**, because
    every character created before it existed used a CC BY default. Reporting
    those as "no third-party assets recorded" is not an absence of information —
    it is an affirmative, false compliance statement, made to exactly the people
    who need the opposite.

    The evidence is right there in the same file: `new_character` has always
    written ``metadata.dicebear_style`` and ``metadata.dicebear_seed``. So this
    reconstructs the record rather than shrugging.

    Returns ``None`` only when the art genuinely was not third-party (the
    offline geometric fallback), which is the one case where "nothing owed" is
    the true answer.
    """
    metadata = getattr(descriptor, "metadata", None)
    if metadata is None and isinstance(descriptor, Mapping):
        metadata = descriptor.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    style = metadata.get("dicebear_style")
    if not style:
        return None  # fallback_geometric — we made it, nothing is owed
    from an.characters.licenses import DICEBEAR_STYLE_LICENSES, dicebear_source

    seed = str(metadata.get("dicebear_seed") or "")
    if style in DICEBEAR_STYLE_LICENSES:
        return dicebear_source(style, seed=seed)
    # An unrecognised style is UNKNOWN, never "nothing owed".
    return AssetSource(provider="dicebear", id=f"{style}/{seed}", license=None)


def credits_for_project(project_dir: str | Path) -> CreditsReport:
    """Credits for the project at ``project_dir``."""
    from an.project import load

    project = load(Path(project_dir))
    report = collect_credits(project.mall)
    report.entries.extend(speech_credits(project.mall, project.scene))
    return report
