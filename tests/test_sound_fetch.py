"""Adding a sound from a URL with its provenance (an#318): the fetch is a seam,
the cut is ffmpeg's and recorded, the licence is the caller's, never guessed."""

from __future__ import annotations

import sys

import pytest
from typer.testing import CliRunner

from an.__main__ import build_app
from an.credits import collect_credits
from an.sound_fetch import Fetched, add_sound_from_url, cut_label, yb_fetcher
from an.sounds import SoundError, get_sound, synth_bed, wav_duration
from an.stores import build_project_mall

PAGE = "https://www.youtube.com/watch?v=abc123"


def _fetcher(seconds: float = 3.0):
    def fetch(url: str) -> Fetched:
        return Fetched(
            audio=synth_bed(seconds),
            url=url,
            id="abc123",
            title="A theme",
            author="A channel",
            provider="youtube",
        )

    return fetch


@pytest.mark.ffmpeg
def test_a_cut_from_a_page_is_stored_with_where_it_came_from(tmp_path):
    mall = build_project_mall(tmp_path, ensure=True)
    asset = add_sound_from_url(
        mall["sounds"], "theme", PAGE, license="cc-by-4.0", fetcher=_fetcher(),
        start=0.5, duration=1.25, fade_out=0.2,
    )
    assert asset.duration == pytest.approx(1.25, abs=0.01)
    source = asset.source
    assert (source.provider, source.id, source.url, source.author) == (
        "youtube", "abc123", PAGE, "A channel")
    assert source.model_extra["cut"] == {"start": 0.5, "end": 1.75, "fade_out": 0.2}
    assert source.model_extra["title"] == "A theme"
    _, wav = get_sound(mall["sounds"], "theme")
    assert wav_duration(wav) == pytest.approx(1.25, abs=0.01)
    text = collect_credits(mall).format()
    assert f"0:00.5–0:01.8 of {PAGE}" in text and "attribution" in text.lower()


@pytest.mark.ffmpeg
def test_no_licence_is_recorded_as_unknown_never_guessed(tmp_path):
    mall = build_project_mall(tmp_path, ensure=True)
    asset = add_sound_from_url(mall["sounds"], "fx", PAGE, license="unknown", fetcher=_fetcher(1.0))
    assert asset.source.license is None
    assert [e.asset for e in collect_credits(mall).unverified] == ["sounds/fx"]


def test_without_yb_the_default_fetcher_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "yb", None)
    with pytest.raises(SoundError, match="pip install yb"):
        yb_fetcher(PAGE)


def test_a_cut_label_needs_a_recorded_cut():
    from an.ir.assets import AssetSource

    assert cut_label(AssetSource(provider="youtube", url=PAGE)) is None


@pytest.mark.ffmpeg
def test_the_cli_requires_a_licence_and_adds_the_sound(tmp_path, monkeypatch):
    import an.sound_fetch as fetch

    monkeypatch.setattr(fetch, "yb_fetcher", _fetcher())
    app, runner = build_app(), CliRunner()
    base = ["sounds", "add", str(tmp_path), "theme", PAGE]
    refused = runner.invoke(app, base)
    assert refused.exit_code != 0 and "--license" in refused.output
    done = runner.invoke(app, [*base, "--license", "cc0-1.0", "--start", "1", "--duration", "0.5"])
    assert done.exit_code == 0, done.output
    assert "sounds/theme: 0.50 s" in done.output
