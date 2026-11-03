"""Sounds from a foley library carry their own rights into ``an credits`` (an#729).

The three sounds of foley's own export acceptance (its ``tests/test_export_sound.py``):
a cacheable Freesound CC0 copy, an FSD50K CC BY sound and a Stable Audio clip (AI,
revenue-capped), built into an in-memory foley library, fetched through
``foley_fetcher`` and ``add_sound_from_url`` into a project's sounds store, and read
back by ``collect_credits``. Skipped when foley's optional deps are missing.
"""

from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("soundfile")
foley = pytest.importorskip("foley")

from foley.audio import encode  # noqa: E402
from foley.base import AcquisitionMethod, LicenseRecord, SoundRecord  # noqa: E402
from foley.index import MemoryIndex, SoundLibrary  # noqa: E402
from foley.licensing import apply_license_flags  # noqa: E402
from foley.sources.base import generated_license  # noqa: E402

from an.credits import collect_credits  # noqa: E402
from an.sound_fetch import (  # noqa: E402
    FILE_SHA256_FIELD,
    add_sound_from_url,
    foley_fetcher,
)
from an.sounds import SoundError  # noqa: E402
from an.stores import build_project_mall  # noqa: E402

SR = 48_000
DIM = 4


def _flac(freq: float, *, dur: float = 0.25) -> bytes:
    t = np.linspace(0.0, dur, int(SR * dur), endpoint=False)
    return encode((0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32), SR)


def _freesound_cc0() -> SoundRecord:
    # cacheable: a website download / a dataset copy (an API pull is by reference)
    lic = apply_license_flags(
        LicenseRecord(
            source="freesound",
            source_id="12345",
            source_url="https://freesound.org/s/12345/",
            creator_name="alice",
            license_id="CC0-1.0",
            rights_verified=True,
        )
    )
    return SoundRecord(id="fs-12345", license=lic, caption="rain on window")


def _fsd50k_cc_by() -> SoundRecord:
    lic = apply_license_flags(
        LicenseRecord(
            source="fsd50k",
            source_id="222",
            source_url="https://freesound.org/s/222/",
            creator_name="amy",
            creator_url="https://freesound.org/people/amy/",
            license_id="CC-BY-4.0",
            acquisition_method=AcquisitionMethod.bulk,
            rights_verified=True,
        )
    )
    return SoundRecord(id="fsd-222", license=lic, tags=["door", "creak"])


def _stable_audio() -> SoundRecord:
    lic = generated_license(
        source="stable_audio",
        license_id="Stability-Community",
        generator_model="stable-audio-open-1.0",
        generation_prompt="a wooden door creak",
        generation_seed=7,
    )
    return SoundRecord(id="sa-7", license=lic, caption="a wooden door creak")


@pytest.fixture
def library():
    """foley's three-sound library; a precomputed vector stands in for CLAP."""
    idx = MemoryIndex(dim=DIM)
    embedder = SimpleNamespace(model_id="test/none", dim=DIM)
    lib = SoundLibrary(sounds={}, meta={}, vindex=idx, kindex=idx, embedder=embedder)
    for i, rec in enumerate((_freesound_cc0(), _fsd50k_cc_by(), _stable_audio())):
        lib.add(rec, data=_flac(300 + 100 * i), vector=np.eye(DIM, dtype=np.float32)[i])
    return lib


@pytest.fixture
def fetcher(library):
    return partial(foley_fetcher, export=partial(foley.export_sound, library=library))


@pytest.mark.ffmpeg
def test_credits_list_the_three_foley_sounds_with_their_own_rights(tmp_path, fetcher):
    mall = build_project_mall(tmp_path, ensure=True)
    for key, ref in (("rain", "fs-12345"), ("door", "fsd-222"), ("door_ai", "sa-7")):
        add_sound_from_url(mall["sounds"], key, f"foley:{ref}", fetcher=fetcher)
    report = collect_credits(mall)
    classes = {e.asset: e.license_class for e in report.entries}
    assert classes == {
        "sounds/rain": "free",
        "sounds/door": "attribution",
        "sounds/door_ai": "free",
    }
    text = report.format()
    after = text.partition("MUST BE DISPLAYED to ship this video:")[2]
    owed, _, rest = after.partition("No attribution required")
    assert '"Door creak" by amy' in owed and "CC BY 4.0" in owed
    assert "sounds/rain" in rest and "sounds/door_ai" in rest
    assert "AI-generated with stable-audio-open-1.0" in text
    assert "USD 1,000,000" in text
    assert "UNVERIFIED" not in text


@pytest.mark.ffmpeg
def test_a_foley_source_keeps_its_digests_and_disclosure(tmp_path, fetcher, library):
    mall = build_project_mall(tmp_path, ensure=True)
    asset = add_sound_from_url(mall["sounds"], "door_ai", "foley:sa-7", fetcher=fetcher)
    src = asset.source
    assert (src.provider, src.license, src.url) == (
        "stability-ai",
        "stability-community",
        "foley:sa-7",
    )
    extra = src.model_extra
    assert extra["archived_sha256"] == library["sa-7"].content_sha256
    # the fetched media's digest; the stored cut's is the SoundAsset's
    assert extra[FILE_SHA256_FIELD] and src.sha256 is None
    assert extra["ai_disclosure"]["is_ai_generated"] is True
    assert extra["cut"]["start"] == 0.0


@pytest.mark.ffmpeg
def test_a_caller_licence_must_agree_with_the_sources(tmp_path, fetcher):
    sounds = build_project_mall(tmp_path, ensure=True)["sounds"]
    with pytest.raises(SoundError, match="states license='cc-by-4.0'"):
        add_sound_from_url(
            sounds, "door", "foley:fsd-222", license="cc0-1.0", fetcher=fetcher
        )
    with pytest.raises(SoundError, match="not overridden"):
        add_sound_from_url(
            sounds, "door", "foley:fsd-222", provider="me", fetcher=fetcher
        )
    agreed = add_sound_from_url(
        sounds, "door", "foley:fsd-222", license="CC-BY-4.0", fetcher=fetcher
    )
    assert agreed.source.license == "cc-by-4.0"


def test_a_by_reference_sound_is_refused_with_foleys_reason(library, fetcher):
    lic = apply_license_flags(
        LicenseRecord(source="freesound", license_id="CC0-1.0", rights_verified=True),
        overrides={"cache_bytes_ok": False},
    )
    rec = SoundRecord(id="api-1", license=lic, uri="https://freesound.org/s/9/")
    library.add(rec, vector=np.ones(DIM, np.float32))
    with pytest.raises(SoundError, match="stored by reference"):
        fetcher("foley:api-1")
    with pytest.raises(SoundError, match="foley will not export 'nope'"):
        fetcher("foley:nope")
    with pytest.raises(SoundError, match="not a foley ref"):
        fetcher("https://freesound.org/s/1/")


@pytest.mark.ffmpeg
def test_the_cli_takes_a_foley_ref_without_a_licence(tmp_path, fetcher, monkeypatch):
    from typer.testing import CliRunner

    import an.sound_fetch
    from an.__main__ import build_app

    monkeypatch.setattr(an.sound_fetch, "foley_fetcher", fetcher)
    done = CliRunner().invoke(
        build_app(), ["sounds", "add", str(tmp_path), "door", "foley:fsd-222"]
    )
    assert done.exit_code == 0, done.output
    assert "[cc-by-4.0]" in done.output
