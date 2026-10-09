"""One non-commercial licence class (an#373).

The maintainer's decision (2026-10-09): one ``noncommercial`` class covers
CC BY-NC (and its SA/ND variants, versioned or not) and the ElevenLabs free
plan. ``an credits`` flags it for commercial use and never blocks a private or
personal video: it is publishable, owes its credit, and is not commercial.
"""

from __future__ import annotations

import pytest

from an.credits import CreditEntry, CreditsReport
from an.ir.assets import AssetSource, license_class, license_restriction, requires_attribution
from an.library import open_library, publish
from an.library.api import find
from an.library.rights import LICENSE_CLASS_ORDER, most_restrictive

NC_SOUND = AssetSource(
    provider="freesound", license="cc-by-nc-4.0", attribution="rain by someone (freesound)"
)


def test_the_issue_acceptance_line():
    assert license_class(NC_SOUND) == "noncommercial"
    report = CreditsReport(entries=[CreditEntry("sounds/rain", NC_SOUND)])
    text = report.format()
    assert "NON-COMMERCIAL USE ONLY" in text and "non-commercial use only" in text
    assert "rain by someone" in text  # the credit is still owed and shown
    assert report.publishable and not report.commercial
    assert report.to_dict()["non_commercial"] == ["sounds/rain"]
    assert report.to_dict()["commercial"] is False


@pytest.mark.parametrize(
    "source",
    [NC_SOUND, AssetSource(provider="elevenlabs", license="elevenlabs-free-plan")],
    ids=["cc-by-nc", "elevenlabs-free-plan"],
)
def test_both_non_commercial_terms_get_one_answer(source):
    assert license_class(source) == "noncommercial"
    assert requires_attribution(source) is True
    assert "non-commercial use only" in license_restriction(source)


def test_the_class_sits_between_unknown_and_attribution():
    assert LICENSE_CLASS_ORDER.index("unknown") < LICENSE_CLASS_ORDER.index(
        "noncommercial"
    ) < LICENSE_CLASS_ORDER.index("attribution")
    assert most_restrictive(["attribution", "noncommercial", "free"]) == "noncommercial"
    assert most_restrictive(["noncommercial", "unknown"]) == "unknown"


def test_the_library_offers_it_as_publishable_but_not_commercial():
    lib = open_library("an", records={}, versions={}, blobs={})
    publish(lib, "prop.rain", {"name": "rain"}, {"a.svg": b"<svg/>"},
            source={"provider": "freesound", "license": "cc-by-nc-4.0"})
    publish(lib, "prop.sun", {"name": "sun"}, {"b.svg": b"<svg></svg>"},
            source={"provider": "me", "license": "cc0-1.0"})
    publishable = {h.asset_id for h in find(lib, rights="publishable")}
    commercial = {h.asset_id for h in find(lib, rights="commercial")}
    assert publishable == {"prop.rain", "prop.sun"}
    assert commercial == {"prop.sun"}
    assert {h.asset_id for h in find(lib, rights="noncommercial")} == {"prop.rain"}
