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
so a composite stage — a carved plate plus a CC0 prop — credits both.
"""

from __future__ import annotations

import warnings

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.ir.assets import AssetSource, LicenseClass, license_class, requires_attribution

__all__ = [
    "CreditsReport",
    "PrivateStudyWarning",
    "collect_credits",
    "credits_for_project",
    "credits_for_scene",
    "warn_if_private_study",
]


@dataclass(frozen=True)
class CreditEntry:
    """One third-party asset and what it obliges."""

    asset: str
    source: AssetSource

    @property
    def attribution_required(self) -> bool | None:
        """``None`` means unknown — which is not the same as ``False``."""
        return requires_attribution(self.source)

    @property
    def license_class(self) -> LicenseClass:
        """``attribution`` / ``free`` / ``private`` / ``unknown`` (an#211)."""
        return license_class(self.source)


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
                {"asset": e.asset, **e.source.model_dump(exclude_none=True)}
                for e in self.entries
            ],
            "attribution_required": [
                {"asset": e.asset, "text": e.source.attribution} for e in self.owed
            ],
            "unverified": [e.asset for e in self.unverified],
            "private_study": [e.asset for e in self.private],
            "publishable": self.publishable,
        }

    def format(self) -> str:
        """Human-readable, and honest about what it does not know."""
        if not self.entries:
            return "credits: no third-party assets recorded."
        lines = [f"credits: {len(self.entries)} third-party asset(s)."]
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
                lines.append(f"  {e.asset}: {text}")
        if self.unverified:
            lines.append("")
            lines.append(
                "UNVERIFIED — licence unknown or unrecognised. Unknown is not "
                "the same as unencumbered; check before shipping:"
            )
            for e in self.unverified:
                lines.append(f"  {e.asset}: license={e.source.license!r}")
        clear = [e for e in self.entries if e.license_class == "free"]
        if clear:
            lines.append("")
            lines.append(f"No attribution required ({len(clear)}):")
            for e in clear:
                lines.append(f"  {e.asset}: {e.source.license}")
        return "\n".join(lines)


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
                else (k for k in (u.split("/", 1)[1] for u in only
                                  if u.startswith(store_name + "/")) if k in store)
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
            if source is None and store_name == "characters":
                source = _reconstruct_legacy_source(descriptor)
            if source is not None:
                report.entries.append(
                    CreditEntry(asset=f"{store_name}/{key}", source=source)
                )
            if store_name == "environments":
                report.entries.extend(_plane_credits(key, descriptor))
    return report


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

    return collect_credits(load(Path(project_dir)).mall)
