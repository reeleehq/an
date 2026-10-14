"""The shared rights vocabulary and the credits report, over core-only sources.

The DiceBear licence table, its snapshot, the acknowledgement gate, the factory
and the legacy-character cases are `cutan` content and are pinned there
(`tests/test_dicebear_provenance.py` in cutan, an#433). What stays here is the
mechanics: `AssetSource`, `requires_attribution`, and `collect_credits` sorting
owed from unverified from clear.
"""

from __future__ import annotations

import json

import pytest

from an.credits import collect_credits
from an.ir.assets import AssetSource, requires_attribution

#: A source a CC BY licence obliges, written by hand: the credits report sorts on
#: the record's licence and attribution, not on who produced it.
_OWED = AssetSource(
    provider="demo", id="a/1", license="cc-by-4.0", attribution="Art by A. Example (CC BY 4.0)"
)
_CLEAR = AssetSource(provider="demo", id="a/2", license="cc0-1.0")


# ------------------------------------------------------- the shared vocabulary


def test_rights_field_names_match_illustration_exactly():
    """No rename table at the boundary — a rename table is where a field
    quietly stops being carried.

    `illustration` is the federation's image-retrieval package and its results
    are the most likely thing to become an `AssetSource`. Its own persistence
    layer already drops these fields (filed as illustration#14), which is
    precisely the failure this pinning is meant to prevent here.

    Pinned by literal rather than by import: `an` must not depend on
    `illustration`. That is the shape `artful` already uses for vocabulary shared
    across packages that must not depend on each other.
    """
    shared = {
        "provider", "id", "url", "license", "license_url", "attribution",
        "source_page_url", "author", "author_url", "cacheable",
    }
    missing = sorted(shared - set(AssetSource.model_fields))
    assert not missing, f"AssetSource is missing shared rights fields: {missing}"


def test_unknown_cost_is_none_not_zero():
    """`None` means unknown; `0.0` means we checked and it was free.

    Collapsing them is the federation's named cost-honesty failure: a
    `0.0`-because-unknown reads as "free" to everything downstream.
    """
    assert AssetSource(provider="p").cost_usd is None
    assert AssetSource(provider="p", cost_usd=0.0).cost_usd == 0.0


@pytest.mark.parametrize(
    "license,expected",
    [
        ("cc0-1.0", False), ("CC0-1.0", False), ("mit", False),
        ("cc-by-4.0", True), ("CC-BY-4.0", True), ("by-sa", True),
        (None, None), ("some-bespoke-thing", None),
    ],
)
def test_attribution_classification_distinguishes_unknown_from_no(license, expected):
    """Three-valued on purpose. "We don't know" is not "nothing owed"."""
    assert requires_attribution(AssetSource(provider="p", license=license)) is expected



# ------------------------------------------------------------------- credits


def _entry(source: AssetSource) -> dict:
    return {"kind": "PropDescriptor", "name": "x", "source": json.loads(source.model_dump_json())}


def test_credits_separates_owed_from_unverified_from_clear():
    """Three lists, never two.

    Folding "unverified" into "owed" cries wolf; folding it into "nothing owed"
    hides a real obligation. Neither is honest.
    """
    mall = {
        "props": {
            "clear": _entry(_CLEAR),
            "owed": _entry(_OWED),
            "unknown": _entry(AssetSource(provider="p", license="mystery")),
        }
    }
    report = collect_credits(mall)
    assert [e.asset for e in report.owed] == ["props/owed"]
    assert [e.asset for e in report.unverified] == ["props/unknown"]
    assert len(report.entries) == 3


def test_the_credits_text_displays_the_attribution_verbatim():
    """A licence recorded and never displayed is not compliance."""
    text = collect_credits({"props": {"lamp": _entry(_OWED)}}).format()
    assert "MUST BE DISPLAYED" in text
    assert _OWED.attribution in text


def test_credits_says_unknown_rather_than_implying_nothing_is_owed():
    mall = {"props": {"x": _entry(AssetSource(provider="p"))}}
    text = collect_credits(mall).format()
    assert "UNVERIFIED" in text
    assert "not the same as unencumbered" in text


def test_a_project_with_no_third_party_art_says_so_plainly():
    assert "no third-party assets" in collect_credits({"characters": {}}).format()


def test_credits_is_a_registered_cli_command():
    """A provenance field with no consumer is decoration."""
    from an.tools import _dispatch_funcs

    assert any(f.__name__ == "credits" for f in _dispatch_funcs)


def test_credits_walks_props_and_environments_not_characters_alone():
    """The PR that gives a store real art is the PR that closes the hole —
    otherwise the report becomes an affirmative false statement about plates
    (an#108, an#110)."""
    from an.credits import collect_credits
    from an.ir.assets import AssetSource

    src = AssetSource(provider="openverse", id="x/1", license="cc-by-4.0")
    raw = json.loads(src.model_dump_json())
    report = collect_credits({
        "characters": {},
        "props": {"lamp": {"kind": "PropDescriptor", "name": "lamp", "source": raw}},
        "environments": {"street": {"kind": "EnvironmentDescriptor", "name": "street", "source": raw}},
    })
    assert sorted(e.asset for e in report.entries) == ["environments/street", "props/lamp"]


def test_a_store_that_cannot_be_LISTED_is_a_gap_not_a_clean_bill():
    """The iteration was unguarded while the per-key read was, and an#110 took
    this walk from one store to three — so one unreadable backing store went
    from "characters are missing" to "`an credits` raises". A credits report
    that cannot run is the one output whose absence is indistinguishable from
    "no third-party assets" (an#110 review, M4)."""
    import warnings

    from an.credits import CreditsWarning, collect_credits

    class Unlistable:
        def __iter__(self):
            raise RuntimeError("backend down")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = collect_credits({"characters": {}, "environments": Unlistable()})
    assert report.entries == []
    assert any(isinstance(w.message, CreditsWarning) for w in caught), [
        str(w.message) for w in caught
    ]
    assert any("GAP" in str(w.message) for w in caught)
