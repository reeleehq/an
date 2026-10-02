"""Shared pytest configuration — the ``live_api`` gate.

Almost the whole suite is offline by design: TTS and lip-sync default to local
providers, and rendering is ffmpeg + a headless browser. A handful of tests
instead exercise the **real paid APIs** (ElevenLabs, Anthropic) to catch contract
drift that a stub would hide. Those are marked ``live_api`` and governed here.

**A key being present is not consent to spend.** These tests used to be gated on
"the SDK is installed and an API key is exported", which is satisfied by every
developer machine and every agent session that has ever sourced a shell profile —
so a plain ``pytest -q`` silently made real, billed calls. That is what this gate
exists to stop, and it is why the opt-in is a *separate, positive* signal rather
than an inference from the key.

A ``live_api`` test runs only when ALL of these hold:

- :data:`LIVE_API_ENV_VAR` is set to a truthy value — the explicit "yes, spend
  money on this run" signal. Nothing else implies it.
- ``CI`` is unset. CI must never spend, whatever else is configured.
- The test's own SDK and credential are available (each test declares its own).

So the default everywhere — laptop, agent session, CI — is *skip*. Running them is
a deliberate act:

    AN_LIVE_API_TESTS=1 pytest -q -m live_api

and ``pytest -q -m "not live_api"`` is always safe.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from an.live_api import TRUTHY_VALUES, live_api_enabled
from an.live_api import LIVE_API_ENV_VAR as _LIVE_API_ENV_VAR

#: Set this truthy to opt a run in to real, billed API calls. Defined in the
#: PACKAGE (:mod:`an.live_api`) rather than here, because the test suite is not
#: the only thing that must refuse to spend without being asked: the example
#: builders read the same switch, and an example cannot import a conftest.
LIVE_API_ENV_VAR = _LIVE_API_ENV_VAR

#: Markers that opt a test out of the offline network guard.
#:
#: TWO markers, because they are different promises and collapsing them would
#: weaken the one that matters:
#:
#: - ``live_api`` — this test SPENDS MONEY. Gated on an explicit positive opt-in
#:   env var as well, because a key being present is not consent to spend.
#: - ``live`` — this test reaches the network but costs nothing (checking that a
#:   pinned upstream snapshot has not drifted, say). It still must not run in the
#:   hermetic suite, but it needs no spending gate.
#:
#: Marking a free test ``live_api`` would be convenient and would quietly erode
#: what that marker promises.
_NETWORK_OPT_OUT_MARKERS = ("live_api", "live")


#: Apply to any test that makes a real, billed call:
#: ``pytestmark = [requires_live_api, pytest.mark.skipif(...)]`` for its own
#: SDK/credential needs.
requires_live_api = pytest.mark.skipif(
    not live_api_enabled(),
    reason=(
        f"real paid API call — set {LIVE_API_ENV_VAR}=1 to opt in "
        "(a key being present is not consent to spend)"
    ),
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_api: makes a real, billed API call; skipped unless "
        f"{LIVE_API_ENV_VAR} is truthy and CI is unset",
    )
    config.addinivalue_line(
        "markers",
        "live: reaches the network but costs nothing; exempt from the offline "
        "guard, and skipped in CI",
    )
    config.addinivalue_line(
        "markers",
        "browser: needs a headless Chromium via Playwright; gated by the browser "
        f"gate below ({BROWSER_ENV_VAR})",
    )
    config.addinivalue_line(
        "markers",
        "ffmpeg: needs the ffmpeg binary on PATH; gated by the browser gate below",
    )
    config.addinivalue_line(
        "markers",
        "genre(name, ...): needs the named genre(s) installed (P8, an#225: the "
        "cut-out genre moves to `cutan`); skipped AND COUNTED when declared or known "
        f"absent, an error under {GENRE_ENV_VAR}=1, in CI without {GENRE_ENV_VAR}, "
        "and for an unknown or broken genre",
    )
    config.addinivalue_line(
        "markers",
        "writes_anywhere: opts out of the blast-radius guard (an#152). No test "
        "carries it today; adding it needs a stated reason in the test",
    )


# ---------------------------------------------------------------------------
# The offline network guard, Python side.
#
# Adapted near-verbatim from illustration's guard (illustration/conftest.py).
# Deliberately not a third shape: same three patch points, same address
# predicate, same BaseException, same append-then-raise, same teardown
# assertion, same split into two module-level functions so both halves are
# individually testable. Only the opt-out marker differs (`live_api` here).
#
# The RECORDING half is the load-bearing one, and it matters more here than it
# does in illustration, because `an` degrades network failures silently in its
# own code: `an/characters/factory.py` catches the RuntimeError from
# `fetch_dicebear` and falls back to generated geometry. A refusal alone gets
# absorbed and the test stays green; asserting the record at teardown is what
# actually holds the line.
#
# This covers Python only. The cutout renderer drives Chromium, which fetches
# from another process — see `hermetic_browser` below.
# ---------------------------------------------------------------------------

import ipaddress
import socket


class OutboundNetworkAttempt(BaseException):
    """An offline test tried to talk to a non-local host.

    Derived from ``BaseException`` rather than ``Exception`` on purpose: this
    package's fail-soft paths (`new_character`'s ``except RuntimeError``, the
    verifiers' broad handlers) would otherwise catch it and the attempt would
    vanish into a passing test.
    """


#: Hostnames that mean "this machine" without a DNS round trip.
LOCAL_HOSTNAMES = frozenset(
    {"", "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
)


def _is_local_address(address) -> bool:
    """True when ``address`` is loopback, unspecified, or not an IP endpoint.

    Non-tuple addresses (AF_UNIX paths, AF_NETLINK ints) are local by
    construction. A bare hostname that is not a known loopback alias counts as
    outbound, because resolving it is itself a network round trip.

    >>> _is_local_address(("127.0.0.1", 8000))
    True
    >>> _is_local_address(("api.dicebear.com", 443))
    False
    >>> _is_local_address(("::1", 80))
    True
    """
    if not isinstance(address, (tuple, list)) or not address:
        return True
    host = address[0]
    if host is None:
        return True
    host = str(host)
    if host in LOCAL_HOSTNAMES:
        return True
    try:
        ip = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False  # an unresolved name — looking it up is already outbound
    return ip.is_loopback or ip.is_unspecified


def install_network_guard(monkeypatch) -> list:
    """Refuse and record every non-local socket use; return the record list.

    Split out of the fixture so both halves of the guard are reachable from a
    test — see ``tests/test_offline_guard.py``.
    """
    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def refuse(what, target):
        attempts.append(f"{what} {target}")
        raise OutboundNetworkAttempt(
            f"Offline test attempted {what} to {target!r}. This suite is "
            "hermetic: stub the seam that fetches (e.g. pass use_dicebear=False), "
            "or mark the test `live_api` if it genuinely must reach the network."
        )

    def connect(self, address, *args, **kwargs):
        if not _is_local_address(address):
            refuse("connect", str(address))
        return real_connect(self, address, *args, **kwargs)

    def connect_ex(self, address, *args, **kwargs):
        if not _is_local_address(address):
            refuse("connect", str(address))
        return real_connect_ex(self, address, *args, **kwargs)

    def getaddrinfo(host, port, *args, **kwargs):
        if not _is_local_address((host, port)):
            refuse("DNS lookup", str(host))
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return attempts


def fail_on_outbound_attempts(attempts) -> None:
    """Fail the test if the guard recorded anything — the swallow-proof half."""
    if attempts:
        pytest.fail(
            "Offline test performed outbound network I/O: "
            + "; ".join(sorted(set(attempts)))
        )


@pytest.fixture(autouse=True)
def _no_outbound_network(request, monkeypatch):
    """Fail the test if it tries to reach a non-local host.

    Loopback stays open on purpose: the cutout renderer serves its runtime from
    its own ``http://127.0.0.1:<port>`` server (``_serve_dir``), and the preview
    tests fetch from it. Tests marked ``live_api`` opt out.
    """
    if any(request.node.get_closest_marker(m) for m in _NETWORK_OPT_OUT_MARKERS):
        yield []
        return
    attempts = install_network_guard(monkeypatch)
    yield attempts
    fail_on_outbound_attempts(attempts)


# ---------------------------------------------------------------------------
# The offline network guard, browser side.
#
# A socket patch cannot see Chromium: it fetches from another process. Measured
# — with only the Python guard installed, the cutout render tests all PASS while
# Chromium downloads the engine from a CDN. Playwright route interception is
# what closes that, and it is the only mechanism that can distinguish "we
# vendored the engine" from "we vendored it and the page actually uses it".
#
# Not autouse: it is opt-in per test, because it wraps Playwright's Browser
# rather than a global, and only the render/preview tests drive a browser.
# ---------------------------------------------------------------------------

#: What a rendered page may reach: an's own _serve_dir, and nothing else.
BROWSER_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "[::1]"})

#: Schemes that never leave the machine.
BROWSER_LOCAL_SCHEMES = ("data:", "blob:", "file:", "about:")


def _is_local_browser_url(url: str) -> bool:
    """True when a browser request stays on this machine.

    >>> _is_local_browser_url("http://127.0.0.1:53219/index.html")
    True
    >>> _is_local_browser_url("https://cdn.jsdelivr.net/npm/pixi.js@7.4.2/dist/pixi.min.js")
    False
    >>> _is_local_browser_url("data:image/png;base64,iVBORw0K")
    True
    """
    if url.startswith(BROWSER_LOCAL_SCHEMES):
        return True
    from urllib.parse import urlparse

    return (urlparse(url).hostname or "") in BROWSER_LOCAL_HOSTS


@pytest.fixture
def hermetic_browser(monkeypatch):
    """Abort every non-loopback browser request; yield the (allowed, blocked) record.

    Wraps ``Browser.new_page`` because the renderer exposes no hook to install a
    route. Yields a dict with ``allowed`` and ``blocked`` URL lists so a test can
    assert on *what* was requested, not merely that nothing failed — the same
    record-as-well-as-refuse discipline as the Python guard.
    """
    # A plain import, not `importorskip`: every test that requests this fixture is
    # `browser`-marked, so the gate has already established Playwright is present.
    # An importorskip here could only turn an inconsistent state into a silent skip.
    import playwright.sync_api as playwright_api

    record = {"allowed": [], "blocked": []}
    real_new_page = playwright_api.Browser.new_page

    def _route(route, request):
        url = request.url
        if _is_local_browser_url(url):
            record["allowed"].append(url)
            route.fallback()
        else:
            record["blocked"].append(url)
            route.abort("blockedbyclient")

    def new_page(self, *args, **kwargs):
        page = real_new_page(self, *args, **kwargs)
        page.route("**/*", _route)
        return page

    monkeypatch.setattr(playwright_api.Browser, "new_page", new_page)
    yield record


# ---------------------------------------------------------------------------
# The browser gate.
#
# Rendering tests need a headless Chromium (via Playwright) and ffmpeg. Neither
# is installed in CI: `playwright` lives in the `cutout` extra and CI installs
# `.[dev]`. So these tests have never run there — every "verified by rendering"
# claim in this repo is verified on a developer machine (an#22).
#
# That is a deliberate choice, not an oversight: the tests take ~45 s locally,
# but making them run in CI costs a ~200 MB browser download plus an ffmpeg
# install on every push. The decision is to keep PR CI fast and run them
# on demand — `.github/workflows/browser-tests.yml`, dispatched manually.
#
# What is NOT acceptable is how that used to be implemented. Eleven test modules
# each opened with
#
#     playwright = pytest.importorskip("playwright.sync_api", ...)
#
# at MODULE level, which does not skip a browser test — it aborts the module
# import, so the tests are never COLLECTED at all. Measured on this commit's
# parent: 472 tests collected with Playwright installed, 438 without. Of the 34
# that vanished, roughly half need no browser whatsoever — the whole of
# `test_vision_verifier.py`'s JSON-parser suite, `an.verify.media`'s pure-numpy
# SSIM tests (the very primitives Wave 2's ledger is built on), and two
# `skip_render=True` orchestrator tests. They were collateral damage of a skip
# aimed at something else, and nothing reported it, because a test that is not
# collected does not appear in the skip count either.
#
# So the contract here is:
#
#   1. WHICH TESTS EXIST MUST NOT DEPEND ON WHAT IS INSTALLED. Collection always
#      succeeds. Playwright is imported inside test bodies and fixtures, never
#      at module scope. `tests/test_browser_gate.py` asserts the collected node
#      id set is identical with and without Playwright.
#   2. THE GATE IS A MARKER, and it is applied at `pytest_collection_modifyitems`
#      so every gated test is counted and carries a precise reason.
#   3. SKIPPING IS ANNOUNCED. `pytest_terminal_summary` prints one line saying
#      how many rendering tests ran and how many did not, so a green run never
#      quietly means "zero pixels were checked".
#   4. AN EXPLICIT OPT-IN THAT CANNOT BE HONOURED IS AN ERROR, NOT A SKIP. If
#      AN_BROWSER_TESTS is truthy and there is no Chromium, the run aborts. A CI
#      job whose `playwright install` silently failed must go red, not green
#      with 31 skips — that is the same failure this whole section exists to end.
# ---------------------------------------------------------------------------

import functools
import shutil

#: Set truthy to run the browser/rendering tests where they would otherwise be
#: skipped (this is what `.github/workflows/browser-tests.yml` sets); set falsy
#: to force them off on a machine that could run them.
BROWSER_ENV_VAR = "AN_BROWSER_TESTS"

#: How to get a browser, quoted verbatim in the skip reason so it is actionable.
_INSTALL_HINT = "pip install -e '.[cutout]' && playwright install chromium"


#: Explicitly-off spellings. Anything that is neither truthy nor falsy is an
#: ERROR rather than a default, because reading `AN_BROWSER_TESTS=yse` as "off"
#: would silently skip the 24 tests the typo was trying to switch on — the same
#: shape as the bug this whole section exists to end.
_FALSY = frozenset({"0", "false", "no", "off"})


def _env_flag(env, name):
    """Return True/False for an explicitly-set flag, or None when unset.

    Tri-state on purpose: "unset" and "set to 0" are different instructions.

    >>> _env_flag({}, "X") is None
    True
    >>> _env_flag({"X": "1"}, "X")
    True
    >>> _env_flag({"X": "0"}, "X")
    False
    >>> _env_flag({"X": ""}, "X") is None
    True

    An unrecognised value refuses rather than defaulting. Written as a caught
    exception rather than a traceback because three different sets of doctest
    option flags run this file, and a traceback example is the one form whose
    result depends on which set is active.

    >>> try:
    ...     _env_flag({"X": "maybe"}, "X")
    ... except pytest.UsageError as e:
    ...     print(str(e).split(".")[0])
    X='maybe' is neither truthy (1, on, true, yes) nor falsy (0, false, no, off)
    """
    raw = env.get(name)
    if raw is None or not raw.strip():
        return None
    value = raw.strip().lower()
    if value in TRUTHY_VALUES:
        return True
    if value in _FALSY:
        return False
    raise pytest.UsageError(
        f"{name}={raw!r} is neither truthy ({', '.join(sorted(TRUTHY_VALUES))}) nor "
        f"falsy ({', '.join(sorted(_FALSY))}). Refusing to guess: reading an "
        f"unrecognised value as 'off' would silently skip the tests it was "
        f"meant to switch on."
    )


def _is_ci(env) -> bool:
    """Whether this looks like a CI runner.

    Deliberately NOT :func:`_env_flag`. CI systems set ``CI`` to many spellings
    — ``true``, ``1``, ``github_actions``, a job id — so an *unrecognised* value
    must mean CI rather than raise. But ``CI=false`` / ``CI=0`` is a real
    convention (create-react-app and several base images set it), and honouring
    it is what stops a developer's rendering tests vanishing without explanation.

    Note the deliberate asymmetry with :func:`live_api_enabled`, four hundred
    lines up, which treats **any** non-empty ``CI`` as CI. That one gates
    SPENDING, where the conservative direction is the opposite: a machine that
    might be CI must never spend, so an ambiguous value there means "do not".
    Here the cost of a false positive is a silently narrower test run, so an
    ambiguous value means "do".

    >>> _is_ci({})
    False
    >>> _is_ci({"CI": "true"}), _is_ci({"CI": "github_actions"})
    (True, True)
    >>> _is_ci({"CI": "false"}), _is_ci({"CI": "0"}), _is_ci({"CI": ""})
    (False, False, False)
    """
    raw = (env.get("CI") or "").strip().lower()
    return bool(raw) and raw not in _FALSY


@functools.lru_cache(maxsize=1)
def chromium_available() -> bool:
    """Whether a Playwright Chromium can actually be launched.

    Cached: this launches a real browser, and eleven modules used to ask
    independently at import time.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            p.chromium.launch(args=["--no-sandbox"]).close()
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=1)
def ffmpeg_available() -> bool:
    """Whether the ffmpeg binary is on PATH."""
    return shutil.which("ffmpeg") is not None


def requirement_verdict(name, *, opt_in, available, ci, install_hint):
    """Decide what to do about one external requirement.

    Returns ``(action, message)`` where action is one of ``"run"``, ``"skip"``
    or ``"error"``. Pure, so the whole decision matrix is testable without
    touching the environment — see ``tests/test_browser_gate.py``.

    ``opt_in`` is tri-state: True (explicitly requested), False (explicitly
    disabled), None (no instruction).

    >>> requirement_verdict("x", opt_in=None, available=True, ci=False, install_hint="h")[0]
    'run'
    >>> requirement_verdict("x", opt_in=None, available=True, ci=True, install_hint="h")[0]
    'skip'
    >>> requirement_verdict("x", opt_in=True, available=False, ci=True, install_hint="h")[0]
    'error'
    >>> requirement_verdict("x", opt_in=False, available=True, ci=False, install_hint="h")[0]
    'skip'
    """
    if opt_in is False:
        return "skip", f"{name} tests disabled by {BROWSER_ENV_VAR}"
    if opt_in is True:
        if available:
            return "run", ""
        return (
            "error",
            f"{BROWSER_ENV_VAR} asked for {name} tests but {name} is unavailable. "
            f"This is an error rather than a skip on purpose: an explicit request "
            f"that silently degrades to a skip is how a green run comes to mean "
            f"nothing. Install it ({install_hint}) or unset {BROWSER_ENV_VAR}.",
        )
    if ci:
        return (
            "skip",
            f"CI installs no {name} (an#22). Set {BROWSER_ENV_VAR}=1 to opt in, or "
            f"dispatch .github/workflows/browser-tests.yml",
        )
    if not available:
        return "skip", f"no {name}: {install_hint}"
    return "run", ""


#: Populated at collection so `pytest_terminal_summary` can report honestly.
_GATE_REPORT: dict = {}


#: The genre test gate (P8, an#225). Tri-state, like the browser gate:
#: ``1`` in a lane that INSTALLS the genre packages (a genre test that cannot
#: run there is an error), ``0`` in a lane that declares them ABSENT (genre tests
#: skip, counted). Unset: skip locally, but an ERROR in CI -- a CI lane must say
#: which one it is, or an unimportable genre would turn every genre test into a
#: green skip (review of an#298, M4).
GENRE_ENV_VAR = "AN_GENRE_TESTS"

#: The genre names a ``genre`` marker may use. A marker naming anything else is
#: an error, never a skip: a misspelled name would otherwise read as "that genre
#: is not installed" forever (review of an#298, M4). Add a genre here when its
#: first test is marked.
KNOWN_GENRES: frozenset[str] = frozenset({"cutout_animation"})

#: How to get the genres, quoted in the skip reason.
_GENRE_INSTALL_HINT = "pip install -e '.[cutout]' (the cut-out genre, an#225)"


def genre_verdict(names, *, available, broken=None, opt_in=None, ci=False, known=KNOWN_GENRES):
    """``(action, message)`` for a test marked ``@pytest.mark.genre(*names)``.

    The P8 move (an#225) puts the cut-out genre in another distribution, so
    `an`'s own tests that need it can only run where it is installed. Those
    tests are marked, and SKIPPED-AND-COUNTED where the genre is declared or
    known absent -- never `importorskip`ped from a body, which is the silent
    hole of an#22. ``broken`` maps a genre that is installed but does not load
    to its error. Pure, so the whole matrix is testable.

    >>> genre_verdict(["cutout_animation"], available={"cutout_animation"})
    ('run', '')
    >>> genre_verdict(["cutout_animation"], available=set())[0]
    'skip'
    >>> genre_verdict(["cutout_animation"], available=set(), ci=True)[0]
    'error'
    >>> genre_verdict(["cutout_animation"], available=set(), ci=True, opt_in=False)[0]
    'skip'
    >>> genre_verdict(["cutout_animation"], available=set(), opt_in=True)[0]
    'error'
    >>> genre_verdict(["cutout"], available={"cutout_animation"})[0]
    'error'
    >>> genre_verdict(["cutout_animation"], available=set(), broken={"cutout_animation": "boom"}, opt_in=False)[0]
    'error'
    """
    broken = broken or {}
    names = tuple(names)
    if not names:
        return "error", "a `genre` marker names no genre: write @pytest.mark.genre(\"<name>\")"
    unknown = sorted(set(names) - set(known) - set(available) - set(broken))
    if unknown:
        return (
            "error",
            f"`genre` marker names unknown genre(s) {unknown}; known: {sorted(known)}. "
            "A typo must fail, not skip: add a new genre to KNOWN_GENRES in tests/conftest.py.",
        )
    failing = {n: broken[n] for n in names if n in broken}
    if failing:
        return (
            "error",
            "installed genre(s) do not load, so their tests cannot run: "
            + "; ".join(f"{n}: {err}" for n, err in sorted(failing.items())),
        )
    missing = sorted(set(names) - set(available))
    if not missing:
        return "run", ""
    if opt_in is True:
        return (
            "error",
            f"{GENRE_ENV_VAR}=1 says the genres are installed, but {missing} is not "
            f"discoverable. Install it ({_GENRE_INSTALL_HINT}) or set {GENRE_ENV_VAR}=0.",
        )
    if opt_in is False:
        return "skip", f"genre {', '.join(missing)} declared absent ({GENRE_ENV_VAR}=0)"
    if ci:
        return (
            "error",
            f"genre {', '.join(missing)} is not installed and this CI lane does not say "
            f"whether it should be: set {GENRE_ENV_VAR}=1 where the genres are installed, "
            f"{GENRE_ENV_VAR}=0 where they are deliberately absent.",
        )
    return "skip", f"genre {', '.join(missing)} not installed: {_GENRE_INSTALL_HINT}"


def _genre_status():
    """``(available names, {name: load error})`` over every discoverable genre.

    Side effect, stated: resolving a genre imports its declaring module (today
    `an.genres.cutout`, and through it `an.characters`), at collection, in any
    run that selects a genre-marked test. `an.genres.available()` is not used
    because it swallows a genre that fails to import -- which is exactly the
    failure this gate must report.
    """
    from an.genres import GenreError, _resolve, discovered_entry_points

    available, broken = set(), {}
    for ep in discovered_entry_points():
        try:
            available.add(_resolve(ep).name)
        except GenreError as e:
            broken[ep.name] = str(e)
    return available, broken


def _genre_gate(items, env=None, *, status=None):
    """Apply :func:`genre_verdict` to every ``genre``-marked item; its report row."""
    marked = [(i, m) for i in items if (m := i.get_closest_marker("genre")) is not None]
    report = {"total": 0, "skipped": 0, "reason": ""}
    if not marked:
        return report
    env = os.environ if env is None else env
    available, broken = _genre_status() if status is None else status
    opt_in = _env_flag(env, GENRE_ENV_VAR)
    ci = _is_ci(env)
    for item, marker in marked:
        if marker.kwargs:
            raise pytest.UsageError(
                f"{item.nodeid}: the `genre` marker takes genre names positionally, "
                f"not {sorted(marker.kwargs)}"
            )
        action, message = genre_verdict(
            marker.args, available=available, broken=broken, opt_in=opt_in, ci=ci
        )
        if action == "error":
            raise pytest.UsageError(f"{item.nodeid}: {message}")
        report["total"] += 1
        if action == "skip":
            report["skipped"] += 1
            report["reason"] = report["reason"] or message
            item.add_marker(pytest.mark.skip(reason=message))
    return report


# -- The count guard (P8 manifest §5; review of an#298, M4) --------------------
#
# A genre test can also vanish WITHOUT the gate: a module-level
# `pytest.importorskip("cutan")`, or an import of the genre package at the top
# of a test file, takes the whole file out of collection, and the summary line
# above never sees it. So the marked tests are also counted STATICALLY, from
# source, and every one of them in a file this run was asked to collect must
# have been collected.


def static_genre_marked(paths):
    """``{(file, test function)}`` carrying a ``genre`` marker, read by AST.

    A function decorated ``@pytest.mark.genre(...)``, or every ``test_*``
    function of a module (or class) whose ``pytestmark`` names ``genre``.
    """
    import ast

    def names_genre(node):
        return any(
            isinstance(n, ast.Attribute) and n.attr == "genre" for n in ast.walk(node)
        )

    out = set()
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))

        def visit(body, inherited):
            marked_here = inherited or any(
                isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
                and names_genre(n.value)
                for n in body
            )
            for n in body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
                    if marked_here or any(names_genre(d) for d in n.decorator_list):
                        out.add((str(path), n.name))
                elif isinstance(n, ast.ClassDef):
                    visit(n.body, marked_here or any(names_genre(d) for d in n.decorator_list))

        visit(tree.body, False)
    return out


def genre_count_gaps(static, collected):
    """The statically marked tests a run was asked for and did not collect.

    >>> genre_count_gaps({("t.py", "test_a"), ("t.py", "test_b")}, {("t.py", "test_a")})
    [('t.py', 'test_b')]
    """
    return sorted(set(static) - set(collected))


#: Filled at collection: the genre-marked tests the session collected.
_GENRE_COLLECTED: set = set()


def _genre_guard_scope(config):
    """The test files this run asked for, or ``None`` when the run is filtered
    (``-k``, ``-m``, a node id, ``--lf``) and so may legitimately omit tests."""
    opt = config.option
    if getattr(opt, "keyword", "") or getattr(opt, "markexpr", "") or getattr(opt, "lf", False):
        return None
    if any("::" in str(a) for a in config.args):
        return None
    ignored = [Path(str(i)).resolve() for i in (config.getoption("ignore") or [])]
    files = set()
    for arg in config.args:
        path = Path(str(arg)).resolve()
        if path.is_dir():
            files.update(p for p in path.rglob("test_*.py") if ".claude" not in p.parts)
        elif path.is_file() and path.name.startswith("test_"):
            files.add(path)
    return {f for f in files if not any(f == i or i in f.parents for i in ignored)}


def pytest_sessionfinish(session, exitstatus):
    scope = _genre_guard_scope(session.config)
    if not scope:
        return
    gaps = genre_count_gaps(static_genre_marked(sorted(scope)), _GENRE_COLLECTED)
    if gaps:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        lines = "\n  ".join(f"{f}::{n}" for f, n in gaps)
        message = (
            f"genre-marked tests that were never collected (a module-level skip or "
            f"import took them out, so no gate counted them):\n  {lines}"
        )
        if reporter is not None:
            reporter.write_line(message, red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _gate_verdicts(env=None):
    """The (action, message) verdict for each gated requirement."""
    env = os.environ if env is None else env
    opt_in = _env_flag(env, BROWSER_ENV_VAR)
    ci = _is_ci(env)
    return {
        "browser": requirement_verdict(
            "headless browser",
            opt_in=opt_in,
            available=chromium_available(),
            ci=ci,
            install_hint=_INSTALL_HINT,
        ),
        "ffmpeg": requirement_verdict(
            "ffmpeg",
            opt_in=opt_in,
            available=ffmpeg_available(),
            ci=ci,
            install_hint="e.g. `brew install ffmpeg` / `apt-get install ffmpeg`",
        ),
    }


#: How many gated tests actually reached their call phase, per requirement.
#: NOT derived as ``total - skipped``: that is a collection-time PREDICTION, and
#: it was wrong in three ordinary invocations — ``-m "not browser"``, ``-k``, and
#: ``--collect-only`` all print "24 ran" for a run in which nothing ran, because
#: deselection happens after this hook and ``--collect-only`` executes nothing.
#: The line whose whole job is to stop a green run over-reporting was itself
#: over-reporting, in the workflow this very change adds.
_RAN_COUNTS: dict = {}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    """Skip gated tests by marker — never by refusing to collect them.

    ``trylast`` so ``items`` is what the invocation actually selected: pytest's
    own ``-m`` / ``-k`` deselection runs in this same hook, and seeing the
    unfiltered list is what made both the count and the error below wrong.
    """
    verdicts = _gate_verdicts()
    counts = {name: {"total": 0, "skipped": 0} for name in verdicts}
    for item in items:
        gated = [n for n in verdicts if item.get_closest_marker(n) is not None]
        if not gated:
            continue
        # A test needing both a browser and ffmpeg is skipped once, but counted
        # against BOTH lanes — otherwise the ffmpeg line reports "22 ran" for 22
        # tests the browser verdict skipped.
        skipping = [n for n in gated if verdicts[n][0] == "skip"]
        for name in gated:
            counts[name]["total"] += 1
            if skipping:
                counts[name]["skipped"] += 1
        if skipping:
            item.add_marker(pytest.mark.skip(reason=verdicts[skipping[0]][1]))
    _GATE_REPORT.clear()
    _GATE_REPORT.update(
        {
            name: dict(
                counts[name],
                reason=verdicts[name][1] if verdicts[name][0] == "skip" else "",
            )
            for name in verdicts
        }
    )
    _GATE_REPORT["genre"] = _genre_gate(items)
    _GENRE_COLLECTED.clear()
    _GENRE_COLLECTED.update(
        (str(Path(str(item.fspath)).resolve()), getattr(item, "originalname", item.name))
        for item in items
        if item.get_closest_marker("genre") is not None
    )
    _RAN_COUNTS.clear()
    # An explicit opt-in that cannot be honoured is an error — but only for a
    # requirement that gates something this invocation actually selected.
    # Raising unconditionally killed every run on a machine following this
    # repo's own install hint: the `cutout` extra ships `ffmpeg-python`, a
    # wrapper, not the ffmpeg binary, so "Chromium yes, ffmpeg no" is the
    # documented setup — and there `AN_BROWSER_TESTS=1 pytest tests/` aborted
    # with rc=4 before reading a single marker.
    for name, (action, message) in verdicts.items():
        if action == "error" and counts[name]["total"]:
            raise pytest.UsageError(message)


def pytest_runtest_logreport(report):
    """Count what executed, so the summary reports an observation.

    ``report.skipped`` too, and it is not belt-and-braces: a `call`-phase report
    exists for a test that skipped from its own BODY, so the line whose whole
    job is to stop a green run over-reporting was itself over-reporting by a
    second route. Measured — `tests/test_bench_png.py`'s ffmpeg cross-check
    skips on "no rendered example frames in this checkout", which is the normal
    state of a fresh clone, and the summary said "ffmpeg tests: 1 collected,
    1 ran" for a run in which zero pixels reached ffmpeg (an#38 review).
    """
    if report.when != "call" or report.skipped:
        return
    for name in _GATE_REPORT:
        if name in report.keywords:
            _RAN_COUNTS[name] = _RAN_COUNTS.get(name, 0) + 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Say out loud how many rendering tests actually ran.

    Without this, "N passed" is silent about whether any pixel was ever looked
    at, which is exactly how this repo came to believe its renders were tested.
    """
    for name, info in sorted(_GATE_REPORT.items()):
        total = info["total"]
        if not total:
            continue
        ran = _RAN_COUNTS.get(name, 0)
        line = f"{name} tests: {total} collected, {ran} ran"
        if ran < total:
            line += f", {total - ran} did not"
            # Only the gate may claim credit. When the verdict was "run", the
            # shortfall is a deselection or an unrelated skip, and saying "CI
            # installs no browser" there would be a second kind of lie.
            if info["reason"]:
                line += f": {info['reason']}"
        terminalreporter.write_line(line)


# ---------------------------------------------------------------------------
# The blast-radius guard (an#152).
#
# A test may write inside its own `tmp_path`, inside the system temp dir, and
# inside the worktree (the mutation sweep edits real source files on purpose).
# Anywhere else is a bug, and it has been a serious one: a fake `subprocess.run`
# that wrote to `cmd[-1]` zero-truncated the machine's Python launcher four
# times, because `platform.platform()` shells out `file -b <sys.executable>` and
# the fake had been installed on the SHARED `subprocess` module.
#
# Two guards, deliberately, because they fail at different distances from the
# mistake:
#
#   * `_no_writes_outside_the_sandbox` catches the general class, at the moment
#     of the write, naming the test. It patches `Path.write_bytes` /
#     `Path.write_text`, which is where this idiom writes — not a complete
#     filesystem sandbox, and it does not pretend to be one. `os.open`, C
#     extensions and real subprocesses go around it.
#   * `_the_interpreter_survived_the_test` is the backstop for exactly the
#     catastrophe, by SIZE rather than by path, so it holds even when the write
#     took a route the first guard cannot see.
#
# Neither replaces `tests/_fake_subprocess.py`'s refusal, which is closest of
# all to the mistake and gives the best message. Defence in depth here is
# proportionate: the failure mode is "the developer's Python is gone", the
# symptom is silence (a 0-byte interpreter exits 0 printing nothing), and the
# bug lived for weeks behind a `platform` cache that hid it on most orderings.
# ---------------------------------------------------------------------------

import sys as _sys
import tempfile as _tempfile
from pathlib import Path as _Path


def _write_allowed_roots(tmp_path):
    """Where a test may write. Resolved, because `/tmp` is a symlink on macOS.

    **The whole worktree is allowed, deliberately**, and it is the loosest of
    the three. `an bench-mutants` edits real source files in place — that is
    what a mutation sweep is — and `test_bench_mutation.py` drives it, so a
    guard that refused writes under the repo would fail the suite's own
    mutation testing. The guard's subject is writes to the DEVELOPER'S MACHINE
    outside the checkout; a stray file inside the worktree is visible to
    `git status`, which is a second line of defence the rest of the filesystem
    does not have.
    """
    roots = [tmp_path, _Path(_tempfile.gettempdir()), _Path(__file__).parent.parent]
    out = []
    for r in roots:
        try:
            out.append(_Path(r).resolve())
        except OSError:  # pragma: no cover - unresolvable root
            continue
    return out


@pytest.fixture(autouse=True)
def _no_writes_outside_the_sandbox(tmp_path, monkeypatch, request):
    """Fail a test that writes outside `tmp_path`, the temp dir or the worktree.

    Opt out with `@pytest.mark.writes_anywhere` when a test genuinely must —
    and say why in the test, because so far none does.
    """
    if request.node.get_closest_marker("writes_anywhere"):
        yield
        return

    allowed = _write_allowed_roots(tmp_path)
    real_bytes, real_text = _Path.write_bytes, _Path.write_text

    def _check(self):
        try:
            target = _Path(self).resolve()
        except OSError:  # pragma: no cover - unresolvable target
            return
        if any(target == a or a in target.parents for a in allowed):
            return
        raise AssertionError(
            f"{request.node.nodeid} wrote to {target}, which is outside "
            f"tmp_path, the system temp dir and the worktree.\n"
            f"If this came from a faked `subprocess.run`, the argv it caught "
            f"was not the one it was written for — see tests/_fake_subprocess "
            f"and an#152. Mark the test `writes_anywhere` only if the write is "
            f"genuinely intended."
        )

    def guarded_bytes(self, data):
        _check(self)
        return real_bytes(self, data)

    def guarded_text(self, data, *a, **kw):
        _check(self)
        return real_text(self, data, *a, **kw)

    monkeypatch.setattr(_Path, "write_bytes", guarded_bytes)
    monkeypatch.setattr(_Path, "write_text", guarded_text)
    yield


@pytest.fixture(autouse=True)
def _the_interpreter_survived_the_test():
    """Backstop: `sys.executable` must be the same size after the test.

    By SIZE, not by path allowlist, so it catches a truncation that reached the
    file by a route `_no_writes_outside_the_sandbox` cannot see. Cheap — two
    `stat` calls per test — and it fails the test that did it rather than the
    next unlucky one, which matters because the damage is otherwise SILENT: a
    0-byte interpreter exits 0 and prints nothing.

    **It surfaces as a teardown ERROR, not a failure**, because the assertion
    runs after the yield: the test itself is reported `passed` and an `ERROR`
    line follows it. That is cosmetically odd and functionally correct — pytest
    exits non-zero, so the run still fails and CI still goes red. Said out loud
    because "1 passed, 1 error" invites a reader to dismiss it as flakiness,
    and this is the one message in the suite that must not be dismissed.
    """
    exe = _Path(_sys.executable)
    try:
        before = exe.stat().st_size
    except OSError:  # pragma: no cover - no readable interpreter path
        yield
        return
    yield
    try:
        after = exe.stat().st_size
    except OSError:  # pragma: no cover
        after = None
    assert after == before, (
        f"this test changed the size of the running interpreter "
        f"({_sys.executable}): {before} -> {after} bytes. See an#152; the "
        f"cause is a faked `subprocess.run` installed on the SHARED "
        f"`subprocess` module, catching `file -b <sys.executable>` from "
        f"`platform.platform()`."
    )
