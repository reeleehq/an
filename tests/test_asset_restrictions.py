"""``AssetSource.restrictions``: lacing's usage restrictions, checked on top of the licence class (an#743)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from lacing import Use
from pydantic import ValidationError

from an.credits import CreditEntry, CreditsReport
from an.ir.assets import AssetSource, license_class, restriction_breaches
from an.sound_fetch import foley_asset_source

CAP = {"kind": "revenue_cap", "usd": 1_000_000, "terms": "stability-community"}
HUNYUAN = {"kind": "territory_excluded", "codes": ["EU", "GB", "KR"]}


def _source(*restrictions) -> AssetSource:
    return AssetSource(
        provider="foley", license="CC-BY-4.0", restrictions=list(restrictions)
    )


def test_every_lacing_rights_field_is_an_asset_source_field():
    """``AssetSource`` mirrors ``lacing.Rights`` field for field (its docstring,
    foley's pin), except ``title``, which rides as an extra (``foley_asset_source``)."""
    import lacing

    assert set(lacing.Rights.model_fields) - {"title"} <= set(AssetSource.model_fields)


def test_restrictions_are_lacing_restrictions_validated_on_the_way_in():
    import lacing

    s = _source(CAP)
    assert (
        isinstance(s.restrictions[0], lacing.Restriction)
        and s.restrictions[0].usd == 1_000_000
    )
    with pytest.raises(ValidationError):
        _source({"kind": "revenue_cap", "usd": "lots"})
    with pytest.raises(ValidationError):
        AssetSource(provider="p", restrictions="revenue_cap")


@pytest.mark.parametrize("unordered", [{"x"}, frozenset(), dict(CAP)])
def test_an_unordered_collection_of_restrictions_is_refused(unordered):
    with pytest.raises(ValidationError, match="ordered sequence"):
        AssetSource(provider="p", restrictions=unordered)


def test_a_sequence_of_dicts_or_records_is_taken_in_order():
    import lacing

    records = (lacing.Restriction.model_validate(HUNYUAN), CAP)
    for given in (list(records), records, (r for r in records)):
        kinds = [
            r.kind for r in AssetSource(provider="p", restrictions=given).restrictions
        ]
        assert kinds == ["territory_excluded", "revenue_cap"]


def test_an_empty_list_is_left_out_of_a_dump_and_a_full_one_round_trips():
    assert (
        "restrictions" not in AssetSource(provider="p", license="cc0-1.0").model_dump()
    )
    s = _source(CAP, HUNYUAN)
    again = AssetSource.model_validate_json(s.model_dump_json())
    assert again == s and again.model_dump()["restrictions"][1]["codes"] == (
        "EU",
        "GB",
        "KR",
    )


def test_an_old_shaped_source_dumps_as_before_with_its_extras():
    """A source recorded before the field (with an extra, as ``title``) dumps
    without the key in every mode, and the extras still ride along."""
    old = {"provider": "foley", "license": "CC-BY-4.0", "title": "door", "note": None}
    s = AssetSource.model_validate(old)
    assert s.model_dump(exclude_none=True) == {
        "provider": "foley",
        "license": "CC-BY-4.0",
        "extra": {},
        "title": "door",
    }
    assert "restrictions" not in s.model_dump()
    assert s.model_dump()["note"] is None and s.model_dump()["title"] == "door"
    assert '"restrictions"' not in s.model_dump_json()
    assert AssetSource.model_validate_json(s.model_dump_json()) == s


def test_the_licence_still_classifies_and_restrictions_are_checked_on_top():
    s = _source(CAP, HUNYUAN)
    assert license_class(s) == "attribution"
    assert restriction_breaches(s, Use(revenue_usd=10_000, territory="US")) == []
    assert restriction_breaches(s, Use(revenue_usd=10_000, territory="fr")) == [
        "not allowed in EU, GB, KR (the use: FR)"
    ]
    assert len(restriction_breaches(s)) == 2  # an unstated use meets neither
    assert restriction_breaches(s, Use()) == restriction_breaches(s)
    with pytest.raises(TypeError, match="lacing.Use"):
        restriction_breaches(s, {"revenue_usd": 10_000})


def test_an_unknown_kind_is_not_cleared():
    assert restriction_breaches(
        _source({"kind": "no_broadcast"}), Use(revenue_usd=0, territory="US")
    ) == ["an unknown restriction 'no_broadcast': not cleared"]


def test_the_credits_report_flags_what_the_use_breaks():
    entry = CreditEntry("sounds/door", _source(CAP))
    unstated = CreditsReport(entries=[entry])
    assert [(e.asset, why) for e, why in unstated.restricted] == [
        (
            "sounds/door",
            "stability-community: allowed only below $1,000,000 of revenue (state the revenue)",
        )
    ]
    assert unstated.publishable and not unstated.commercial
    text = unstated.format()
    assert (
        "RESTRICTED — 1 restriction(s)" in text
        and "sounds/door: stability-community" in text
    )
    assert unstated.to_dict()["restricted"][0]["asset"] == "sounds/door"

    assert "(state the use with --revenue-usd and --territory)" in text

    small = CreditsReport(entries=[entry], use=Use(revenue_usd=20_000))
    assert (
        small.restricted == []
        and small.commercial
        and "RESTRICTED" not in small.format()
    )


def test_the_hint_to_state_the_use_shows_only_while_part_is_unstated():
    entry = CreditEntry("sounds/door", _source(CAP))
    stated = CreditsReport(
        entries=[entry], use=Use(revenue_usd=2_000_000, territory="US")
    )
    assert "RESTRICTED — 1 restriction(s)" in stated.format()
    assert "--revenue-usd" not in stated.format()
    half = CreditsReport(entries=[entry], use=Use(revenue_usd=2_000_000))
    assert "(state the use with --revenue-usd and --territory)" in half.format()


def test_the_cli_builds_the_use_and_refuses_a_territory_it_cannot_place(tmp_path):
    from an.tools import credits

    with pytest.raises(SystemExit, match="an credits: .*alpha-2"):
        credits(str(tmp_path), territory="Franc")
    with pytest.raises(SystemExit, match="an credits: .*negative"):
        credits(str(tmp_path), revenue_usd=-5)


def test_a_foley_export_carries_its_restrictions_into_the_source():
    src = foley_asset_source(
        {"provider": "stable-audio", "license": "CC-BY-4.0", "restrictions": [CAP]},
        {"sha256": "ab"},
        url="foley:sa-1",
    )
    assert src.restrictions[0].kind == "revenue_cap"


def test_importing_an_and_reading_a_source_does_not_load_lacing():
    code = (
        "import sys, an; from an.ir.assets import AssetSource;"
        "AssetSource(provider='p', license='cc0-1.0');"
        "print('lacing' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"
