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

from an.credits import collect_credits
from an.sound_fetch import (
    FILE_SHA256_FIELD,
    add_sound_from_url,
    foley_fetcher,
)
from an.sounds import SoundError
from an.stores import build_project_mall

#: foley and its optional audio deps, bound by :func:`_foley_deps` when present:
#: a module-level import would make the whole file vanish from collection
#: without them (tests/test_browser_gate.py), rather than skip.
np = foley = encode = AcquisitionMethod = LicenseRecord = SoundRecord = None
MemoryIndex = SoundLibrary = apply_license_flags = generated_license = None


@pytest.fixture(autouse=True)
def _foley_deps():
    """Skip each test unless numpy, soundfile and foley are installed, and bind
    the names this module uses from them."""
    global np, foley, encode, AcquisitionMethod, LicenseRecord, SoundRecord
    global MemoryIndex, SoundLibrary, apply_license_flags, generated_license
    np = pytest.importorskip("numpy")
    pytest.importorskip("soundfile")
    foley = pytest.importorskip("foley")
    from foley.audio import encode
    from foley.base import AcquisitionMethod, LicenseRecord, SoundRecord
    from foley.index import MemoryIndex, SoundLibrary
    from foley.licensing import apply_license_flags
    from foley.sources.base import generated_license


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
    assert "UNVERIFIED" not in text
    sections = _sections(text)
    owed = sections["MUST BE DISPLAYED"]
    assert list(owed) == ["sounds/door"]
    assert '"Door creak" by amy' in owed["sounds/door"]
    assert "CC BY 4.0" in owed["sounds/door"]
    free = sections["No attribution required"]
    assert set(free) == {"sounds/rain", "sounds/door_ai"}
    assert "USD 1,000,000" in free["sounds/door_ai"]
    assert "USD 1,000,000" not in free["sounds/rain"]
    ai = sections["AI-GENERATED"]
    assert list(ai) == ["sounds/door_ai"]
    assert ai["sounds/door_ai"] == (
        "AI-generated with stable-audio-open-1.0: disclosure recommended; "
        "not publish-ready, Art. 50 pending: machine_readable_mark, provenance_manifest"
    )
    assert [e.asset for e, _ in report.ai_generated] == ["sounds/door_ai"]


def _sections(text: str) -> dict[str, dict[str, str]]:
    """A credits report as ``{section heading's first words: {asset: rest of its line}}``."""
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("  "):
            asset, _, rest = line.strip().partition(": ")
            current[asset] = rest
        elif line:
            heading = line.split(" (")[0].split(" — ")[0].split(" to ship")[0]
            current = sections.setdefault(heading.rstrip(":"), {})
    return sections


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
    prov = extra["foley_provenance"]
    assert prov["archived_sha256"] == library["sa-7"].content_sha256
    # the fetched media's digest; the stored cut's is the SoundAsset's
    assert extra[FILE_SHA256_FIELD] == prov["sha256"] and src.sha256 is None
    assert prov["flags"]["revenue_cap_usd"] == 1_000_000
    ai = prov["ai_disclosure"]
    assert ai["is_ai_generated"] is True and ai["publish_ready"] is False
    assert ai["pending"] == ["machine_readable_mark", "provenance_manifest"]
    assert "cut" not in extra  # the whole media was kept
    cut = add_sound_from_url(
        mall["sounds"], "short", "foley:fsd-222", fetcher=fetcher, duration=0.1
    )
    assert cut.source.model_extra["cut"] == {"start": 0.0, "end": 0.1}
    assert collect_credits(mall).format().count("of https://freesound.org/s/222/") == 1


@pytest.mark.ffmpeg
def test_a_caller_licence_must_agree_with_the_sources(tmp_path, fetcher):
    sounds = build_project_mall(tmp_path, ensure=True)["sounds"]
    with pytest.raises(SoundError, match="license='cc-by-4.0'.*license='cc0-1.0'"):
        add_sound_from_url(
            sounds, "door", "foley:fsd-222", license="cc0-1.0", fetcher=fetcher
        )
    with pytest.raises(SoundError, match="not overridden"):
        add_sound_from_url(
            sounds, "door", "foley:fsd-222", provider="me", fetcher=fetcher
        )
    with pytest.raises(SoundError, match="author='Thor'"):  # an AI clip has no author
        add_sound_from_url(sounds, "door", "foley:sa-7", author="Thor", fetcher=fetcher)
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

    def broken(sound_id):
        raise RuntimeError("transcode failed")

    with pytest.raises(SoundError, match="foley:sa-7.*RuntimeError: transcode failed"):
        foley_fetcher("foley:sa-7", export=broken)
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
