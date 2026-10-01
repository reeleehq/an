"""The `genre` marker (P8, an#225): a test that needs a genre package runs where
it is installed and is skipped AND COUNTED elsewhere -- never silently."""

from __future__ import annotations

import pytest

from .conftest import GENRE_ENV_VAR, _genre_gate


class _Item:
    def __init__(self, *genres):
        self._marker = pytest.mark.genre(*genres).mark if genres else None
        self.added = []

    def get_closest_marker(self, name):
        return self._marker if name == "genre" else None

    def add_marker(self, marker):
        self.added.append(marker)


def test_an_absent_genre_skips_and_counts():
    items = [_Item("no_such_genre"), _Item(), _Item("cutout_animation")]
    report = _genre_gate(items, env={})
    assert report["total"] == 2 and report["skipped"] == 1
    assert "no_such_genre" in report["reason"]
    assert [m.name for m in items[0].added] == ["skip"]
    assert items[1].added == [] and items[2].added == []


def test_a_lane_that_promises_the_genres_errors_instead_of_skipping():
    with pytest.raises(pytest.UsageError, match=GENRE_ENV_VAR):
        _genre_gate([_Item("no_such_genre")], env={GENRE_ENV_VAR: "1"})


@pytest.mark.genre("cutout_animation")
def test_the_marker_runs_where_the_genre_is_installed():
    """Today `an` ships the cut-out genre itself, so this runs in every lane."""
    from an.genres import available

    assert "cutout_animation" in available()
