"""Repository-wide pytest setup: register the in-repo cut-out genre.

Genres are discovered explicitly (ADR 0001 decision 3): importing ``an``
registers none, and ``an.load(project)`` / the CLI call
:func:`an.genres.load`. Most tests and doctests build scenes with the cut-out
genre's kinds (``play``, ``expression``, ``character``, ``[emotion]``)
without going through either, so the session registers it once, here — by the
genre OBJECT, not the entry point, so the suite does not depend on whether the
installed distribution's metadata is current (an editable install made before
the entry point existed has none). Tests of the unloaded core use
:func:`an.genres.without_genres`.

At the repository root so it reaches both ``tests/`` and the doctests under
``an/`` (CI's ``--doctest-modules``).
"""

from __future__ import annotations


def pytest_configure(config):  # noqa: D103 — a pytest hook
    from an.genres import register_genre
    from an.genres.cutout import CUTOUT

    register_genre(CUTOUT)
