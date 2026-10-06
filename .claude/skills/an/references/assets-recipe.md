# The assets: one recipe

Reference for the `an` skill (`../SKILL.md`: the index and the essentials).

### The assets: one recipe

Text, paths, plane environments and StylePacks are pydantic documents; `model_dump(mode="json")` into the project's store writes the file the compiler reads (`assets/props/<key>/prop.json`, `assets/environments/<key>/meta.json`, `assets/styles/<key>.json`). The dump holds only what you set, so it always loads back.

<!-- skill-test: recipe -->
```python
from pathlib import Path

from cutan.characters import new_character
from an.stage.environments import EnvironmentDescriptor, Plane, PlaneArt
from an.stage.paths import PathDescriptor
from an.project import init
from an.sounds import SYNTH_SOURCE, add_sound, synth_bed
from an.stores import build_project_mall
from an.styles import StylePack
from an.stage.text import TextDescriptor

root = init(Path("my_film"))  # = `an init my_film`
mall = build_project_mall(root)

for name in (
    "stan",
    "kyle",
):  # = `an character new <name> --offline --out-dir my_film/assets/characters`
    new_character(root / "assets" / "characters", name=name, use_dicebear=False)

# A title card: one fill plane with no `size` covers the canvas; depth 0 never pans.
mall["environments"]["card"] = EnvironmentDescriptor(
    name="card",
    planes=[Plane(name="bg", art=PlaneArt(kind="fill", color="#040404"), depth=0.0)],
).model_dump(mode="json")

# A backdrop with no drawn plate: gradient planes (an#275), CSS's vocabulary.
# Linear `angle` in degrees (0 up, 90 right, 180 = default, down); radial `center`/`radius`
# in fractions of the box. With no `size` it covers the canvas and is shaped over the frame.
# `role: glass` lets a StylePack's `gradients: {glass: {...}}` repaint the plane.
mall["environments"]["dusk"] = EnvironmentDescriptor(
    name="dusk",
    planes=[
        Plane(
            name="sky",
            art=PlaneArt(kind="gradient", gradient={"stops": ["#141a33", "#f2c48a"]}),
            depth=0.2,
        ),
        Plane(
            name="glow",
            art=PlaneArt(
                kind="gradient",
                role="glass",
                gradient={"type": "radial", "stops": ["#fff3d2", "#fff3d200"]},
            ),
            size=(800.0, 600.0),
        ),
    ],
).model_dump(mode="json")

# A map: sea, land, and a WHITE territory, so a `tint` tween can colour it (tint multiplies).
mall["environments"]["map"] = EnvironmentDescriptor(
    name="map",
    planes=[
        Plane(name="sea", art=PlaneArt(kind="fill", color="#a7b1b9"), depth=0.0),
        # depth 1.0 = the character plane: pans exactly with props (the route, labels)
        Plane(
            name="land",
            art=PlaneArt(kind="fill", color="#cda469"),
            depth=1.0,
            size=(1100, 420),
        ),
        Plane(
            name="west",
            art=PlaneArt(kind="fill", color="#ffffff"),
            depth=1.0,
            offset=(-250, 0),
            size=(400, 300),
        ),
    ],
).model_dump(mode="json")

# Words: an overlay title (the camera never moves it) and a reusable world label.
mall["props"]["date"] = TextDescriptor(
    name="date",
    text="OCTOBER 1ST, 2026",
    layer="overlay",
    unit="line",
    size=0.1,
    color="#ffffff",
).model_dump(mode="json")
mall["props"]["label"] = TextDescriptor(
    name="label", text="label", size=0.05, color="#1a1a1a"
).model_dump(mode="json")

# A route arrow that starts hidden (trim_end 0), drawn on by a trim_end tween.
mall["props"]["route"] = PathDescriptor(
    name="route",
    points=[(-300, 60), (0, -40), (260, 30)],
    arrowhead=True,
    trim_end=0.0,
    color="#ba5f31",
    width=10,
).model_dump(mode="json")

# Art direction, named by `style_pack:` in the meta block.
mall["styles"]["south_park"] = StylePack(
    name="south_park", roles={"sky": "#c0c6c7", "ground": "#987a43"}
).model_dump(mode="json")

# A sound: WAV bytes plus where they came from. synth_bed is an honest stand-in.
add_sound(mall["sounds"], "bed", synth_bed(12.0), source=SYNTH_SOURCE)
```

Every document refuses what it cannot draw: a `TextDescriptor` needs `name` and exactly ONE of `text` (one string), `texts` (a replacement set, `unit: block`) or `counter` (a number, `unit: block`) — giving `text` beside `counter` is refused, an `anchor` is overlay-only, a `PathDescriptor` refuses `gap`/`dash_offset` without `dash` and `head_length` without `arrowhead`, a `Plane` refuses an unknown key.
