"""A stored document must load what it dumps.

An end-user agent building an OverSimplified map found that a default
``model_dump_json()`` of a VALID `PathDescriptor` was refused on load: the dump
wrote every default back (``gap: null``, ``dash_offset: 0``,
``samples_per_segment: 24`` on a polyline), and the set-but-inert checks read
``model_fields_set``, so the document refused its own output. It hand-trimmed
the JSON. These are the three documents an author writes by hand for the
stage — a path, a text block, an environment — each dumped the documented way
and read back through the store and the resolver the compiler uses.
"""

from __future__ import annotations

import json

import pytest

from an.environments import EnvironmentDescriptor, Plane, PlaneArt
from an.paths import PathDescriptor, resolve_path
from an.stores import build_project_mall
from an.text import TextDescriptor, resolve_text

PATHS = {
    "default_polyline": PathDescriptor(name="r", points=[(0, 0), (10, 0)]),
    "arrow_draw_on": PathDescriptor(
        name="route",
        points=[(-300, 0), (0, 40), (250, -80)],
        arrowhead=True,
        trim_end=0.0,
        color="#ba5f31",
        width=10,
    ),
    "cubic_dashed": PathDescriptor(
        name="border",
        curve="cubic",
        points=[(0, 0), (40, 60), (80, 60), (120, 0)],
        samples_per_segment=32,
        dash=12,
        gap=6,
        dash_offset=3,
    ),
    "sized_head": PathDescriptor(
        name="h", points=[(0, 0), (0, 100)], arrowhead=True, head_length=30, head_width=20
    ),
}

#: Built lazily: an overlay `anchor` is checked against tituli's anchors, which
#: import Pillow, and a test module must import with every optional dependency
#: absent (`tests/test_browser_gate.py`).
TEXTS = {
    "default": lambda: TextDescriptor(name="t", text="Hi"),
    "date_card": lambda: TextDescriptor(
        name="date",
        text="OCTOBER 1ST, 2026",
        layer="overlay",
        unit="line",
        size=0.1,
        color="#ffffff",
        anchor="center",
    ),
    "tracked": lambda: TextDescriptor(name="g", text="MAP", unit="glyph", tracking=0.1),
}

ENVIRONMENTS = {
    "no_planes": EnvironmentDescriptor(name="plain"),
    "card": EnvironmentDescriptor(
        name="card", planes=[Plane(name="card", art=PlaneArt(color="#040404"), depth=0.0)]
    ),
    "map": EnvironmentDescriptor(
        name="map",
        planes=[
            Plane(name="sea", art=PlaneArt(color="#a7b1b9"), depth=0.0),
            Plane(name="land", art=PlaneArt(color="#cda469"), depth=0.6, size=(1500, 520)),
            Plane(name="fg", depth=1.3, offset=(0, 300), size=(4000, 120)),
        ],
        characters_after="land",
        tags=["map"],  # extra="allow": free-form store keys ride along
    ),
}

ALL = [
    *((f"path:{k}", (lambda v=v: v)) for k, v in PATHS.items()),
    *((f"text:{k}", v) for k, v in TEXTS.items()),
    *((f"env:{k}", (lambda v=v: v)) for k, v in ENVIRONMENTS.items()),
]


@pytest.mark.parametrize("make", [v for _, v in ALL], ids=[k for k, _ in ALL])
def test_model_dump_json_round_trips(make):
    doc = make()
    back = type(doc).model_validate_json(doc.model_dump_json())
    assert back == doc
    # ...and what was not set stays unset, which is what a StylePack role reads.
    assert back.model_fields_set <= doc.model_fields_set | {"kind", "schema_version"}


@pytest.mark.parametrize("make", [v for _, v in ALL], ids=[k for k, _ in ALL])
def test_json_dumps_of_model_dump_round_trips(make):
    """The other documented spelling: ``json.dumps(doc.model_dump(mode="json"))``."""
    doc = make()
    raw = json.dumps(doc.model_dump(mode="json"))
    assert type(doc).model_validate(json.loads(raw)) == doc


def test_through_the_store_and_the_resolvers(tmp_path):
    """The recipe the `an` skill gives: assign ``model_dump(mode="json")`` into
    the project's store; the compiler's resolvers read it back."""
    mall = build_project_mall(tmp_path, ensure=True)
    for key, doc in PATHS.items():
        mall["props"][key] = doc.model_dump(mode="json")
        assert resolve_path(mall["props"][key]) == doc
    for key, make in TEXTS.items():
        doc = make()
        mall["props"][key] = doc.model_dump(mode="json")
        assert resolve_text(mall["props"][key]) == doc
    for key, doc in ENVIRONMENTS.items():
        mall["environments"][key] = doc.model_dump(mode="json")
        assert EnvironmentDescriptor.model_validate(mall["environments"][key]) == doc


def test_an_unset_colour_stays_reachable_by_a_style_pack():
    """The compiler lets a pack's `stroke` role recolour a path only when its
    `color` was never set; a full dump used to mark it set on the way back."""
    back = PathDescriptor.model_validate_json(PATHS["default_polyline"].model_dump_json())
    assert "color" not in back.model_fields_set


def test_a_full_dump_written_by_another_tool_still_loads():
    """A default written out explicitly asks for nothing, so it is not refused —
    the file the e2e agent had to hand-trim loads as written."""
    full = {
        "kind": "PathDescriptor",
        "name": "r",
        "points": [[0, 0], [10, 0]],
        "curve": "polyline",
        "samples_per_segment": 24,
        "dash": None,
        "gap": None,
        "dash_offset": 0.0,
        "arrowhead": False,
        "head_length": None,
        "head_width": None,
    }
    assert PathDescriptor.model_validate(full).name == "r"


@pytest.mark.parametrize(
    "bad",
    [
        {"gap": 4},
        {"dash_offset": 2},
        {"samples_per_segment": 8},
        {"head_length": 10},
    ],
)
def test_a_set_but_inert_value_is_still_refused(bad):
    with pytest.raises(ValueError):
        PathDescriptor(name="r", points=[(0, 0), (10, 0)], **bad)
