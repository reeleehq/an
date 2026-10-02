"""The `genre` marker (P8, an#225): a test that needs a genre package runs where
it is installed, is skipped AND COUNTED where the genre is declared absent, and
can never vanish quietly -- not through a typo, a broken genre, an undeclared CI
lane, or a module-level skip (review of an#298, M4)."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

from .conftest import (
    GENRE_ENV_VAR,
    _genre_gate,
    genre_count_gaps,
    static_genre_marked,
)

ROOT = Path(__file__).resolve().parents[1]
INSTALLED = ({"cutout_animation"}, {})
ABSENT = (set(), {})


class _Item:
    def __init__(self, *genres, **kwargs):
        self._marker = pytest.mark.genre(*genres, **kwargs).mark
        self.nodeid = "t.py::test_x"
        self.added = []

    def get_closest_marker(self, name):
        return self._marker if name == "genre" else None

    def add_marker(self, marker):
        self.added.append(marker)


class _Unmarked(_Item):
    def get_closest_marker(self, name):
        return None


def test_a_genre_declared_absent_skips_and_counts():
    items = [_Item("cutout_animation"), _Unmarked(), _Item("cutout_animation")]
    report = _genre_gate(items, env={GENRE_ENV_VAR: "0", "CI": "true"}, status=ABSENT)
    assert report["total"] == 2 and report["skipped"] == 2
    assert [m.name for m in items[0].added] == ["skip"] and items[1].added == []


def test_an_installed_genre_runs():
    items = [_Item("cutout_animation")]
    report = _genre_gate(items, env={"CI": "true"}, status=INSTALLED)
    assert report == {"total": 1, "skipped": 0, "reason": ""} and items[0].added == []


def test_a_misspelled_genre_fails_instead_of_skipping():
    with pytest.raises(pytest.UsageError, match="unknown genre"):
        _genre_gate([_Item("cutout")], env={}, status=INSTALLED)


def test_a_keyword_marker_is_refused():
    with pytest.raises(pytest.UsageError, match="positionally"):
        _genre_gate([_Item(name="cutout_animation")], env={}, status=INSTALLED)


def test_an_undeclared_ci_lane_without_the_genre_fails():
    with pytest.raises(pytest.UsageError, match=GENRE_ENV_VAR):
        _genre_gate([_Item("cutout_animation")], env={"CI": "true"}, status=ABSENT)


def test_a_lane_that_promises_the_genres_errors_instead_of_skipping():
    with pytest.raises(pytest.UsageError, match=GENRE_ENV_VAR):
        _genre_gate([_Item("cutout_animation")], env={GENRE_ENV_VAR: "1"}, status=ABSENT)


def test_an_installed_genre_that_does_not_load_fails_with_its_error():
    status = (set(), {"cutout_animation": "GenreAPILevelError: cutan needs API level 9"})
    with pytest.raises(pytest.UsageError, match="API level 9"):
        _genre_gate([_Item("cutout_animation")], env={GENRE_ENV_VAR: "0"}, status=status)


def test_the_count_guard_sees_a_module_taken_out_of_collection(tmp_path):
    """A module-level `importorskip` removes a whole file before any gate runs;
    the static count is what notices."""
    f = tmp_path / "test_genre_thing.py"
    f.write_text(
        textwrap.dedent(
            """
            import pytest
            cutan = pytest.importorskip("cutan")

            @pytest.mark.genre("cutout_animation")
            def test_a():
                pass

            class TestB:
                pytestmark = [pytest.mark.genre("cutout_animation")]
                def test_b(self):
                    pass

            def test_unmarked():
                pass
            """
        ),
        encoding="utf-8",
    )
    static = static_genre_marked([f])
    assert static == {(str(f), "test_a"), (str(f), "test_b")}
    assert genre_count_gaps(static, collected=set()) == sorted(static)
    assert genre_count_gaps(static, collected=static) == []


@pytest.mark.genre("cutout_animation")
def test_the_marker_runs_where_the_genre_is_installed():
    """Today `an` ships the cut-out genre itself, so this runs in every lane."""
    from an.genres import available

    assert "cutout_animation" in available()


def test_every_api_level_is_documented():
    """A bump of `an.genres.API_LEVEL` must say what it adds (review of an#298, L2)."""
    from an.genres import API_LEVEL

    source = (ROOT / "an" / "genres" / "__init__.py").read_text(encoding="utf-8")
    documented = {int(n) for n in re.findall(r"#:\s+(\d+) = ", source)}
    assert documented == set(range(1, API_LEVEL + 1)), documented
