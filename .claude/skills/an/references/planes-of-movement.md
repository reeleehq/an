# Planes of movement: putting every element in its frame of reference

For whoever authors a scene (a writer, an agent) with a `world`. Read it before placing anything in a scene where something moves with, or past, something else: a car, a ship's deck, a train window, a moving platform, a crane-mounted camera.

## The one rule

**Before placing anything, say which frame it moves with.** A frame is something rigid that carries other things: the world, a vehicle, a deck, a platform, a crane arm. Every member, plane, stream and camera is in exactly one frame at a time (`in: <frame>`, default the world). A thing drawn in the wrong frame is the whole family of "it looks broken" bugs: the tree that stands still while the poles stream past, the wheel that shrinks between framings, the passenger who floats when the car turns.

## The recipe

1. **Name the frames.** Walk the scene and list what moves as a unit. A drive: `world` (road, poles, trees), `vehicle` (cabin, seats, dashboard, the two men, the wheel), `far` (sky, mountains). A ship: `world`, `deck`, `far`. A platform shot: `world`, `platform`. A crane shot: `world ⊃ dolly ⊃ arm ⊃ camera`. Fewer is better; a frame earns its name by moving differently from its parent. `world` is the implicit root and is never declared.
2. **Say how each frame moves** relative to its parent. `moving: {direction, speed}` is a constant velocity per second of FILM time, in the parent's units (the phase holds across cuts). A `set`/`tween` of `<frame>:at_x|at_y|at_z|yaw|pitch|roll` in a shot moves a frame by hand for that shot (see "Time" below). `look: [yaw, pitch, roll]` is the frame's orientation; its local axes are the viewpoint's (`x` right, `y` DOWN, `z` away).
3. **Put every member in its frame** (`in: vehicle`), with its position in that frame's units. An attached member is in its host's frame; do not give it `in`.
4. **Put every camera in a frame.** The windscreen two-shot and the side-window shot are viewpoints `in: vehicle`; the roadside shot of the car passing is a viewpoint `in: world`; a camera rig is a viewpoint in a chain of frames, and a `tween` of `dolly:at_z` is the dolly move. The same world is seen from each, and the shots agree because nothing was placed twice.
5. **Give every plane a frame.** On the environment member: `in: vehicle` for the cabin plates and `planes: {rear_view: far}` for the sky (one environment can hold both). A plane in a frame with `coupling: far` turns with its parent and never translates: it holds only what is at infinity (the sky, the horizon, the far range). A plate that holds anything nearer (a tree, a house, a pole) is wrong under a moving camera; those are members of the world, or a stream of them.
6. **Let the lowering move things.** A member whose frame moves relative to the camera's, or that an `at_*` action walks, gets sampled keys; one that stays put relative to the camera gets one placement. Do not hand-place (`stage.at`) a member in a frame that moves relative to the camera: the hand wins and the member stands still on screen.

## Motion, by property name

- `<member>:x|y|scale` stay SCREEN pixels, as they always were. Nothing existing changes meaning.
- `<member>:at_x|at_y|at_z` are in the member's frame's units, absolute (a walk from 0.5 to 1.5 on a moving platform is `from: 0.5, to: 1.5`).
- `<frame>:at_x|at_y|at_z|yaw|pitch|roll` move a frame; the channel replaces the frame's declared value for that shot.

**Time.** Like every action, these are in SHOT time and restart each shot: a member or frame the shot animates begins the shot at its declared value, not where the previous shot left it. For motion that must continue across cuts, use `moving` (film time).

## Sugar

`world.travel` with a `speed` is a moving `vehicle` frame: members and viewpoints default to `in: vehicle`, streams to `in: world`, and `plates: {far: [...], vehicle: [...]}` say which planes are at infinity and which ride with the camera. The general form drops the `speed` (the travel then only holds the streams and their knobs) and declares the frame:

```yaml
world:
  frames:
    vehicle: {moving: {direction: [0, 0, 1], speed: 20}}
    far: {parent: vehicle, coupling: far}
  members:
  - {kind: character, id: jerry, store: characters, ref: jerry, in: vehicle, at: [-0.45, 0.65, 1.6], height: 1.75}
  - {kind: environment, id: set, store: environments, ref: car_cabin, in: vehicle, planes: {rear_view: far}}
  viewpoints:
    two_shot: {in: vehicle, at: [0, 0, 0]}
    roadside: {in: world, at: [20, -1, 0], look: [-90, 0, 0], fov: 50}
  travel:
    streams:
    - {id: pole, ref: pole, in: world, height: 6, every: 12, lane: 2}
```

`roadside` sees the car pass from the same description; `two_shot` is the windscreen. Swap `vehicle` for `deck` with a `roll` tween, or for `platform` with a character walking `at_x`, and the recipe is unchanged. `an world show <dir> --frames` prints every frame's world pose as each shot opens and closes.

## What the checker tells you

- **An unknown frame, a frame cycle, a frame declared both in `frames` and as the travel's `vehicle`**: refused when the scene is read, with the fix named.
- **A plane in a moving view that nothing says what it holds** (not in `plates`, no `in`, no `planes`): give it a frame. This is the baked-trees bug.
- **A plane in a far frame whose parallax factor is not 0**: pin it (`depth: 0`).
- **A plane in a frame that moves relative to the camera's frame and is not far**: it would stand still while its frame moves.
- **A member the world moves, given a hand `stage.at`** (`hand_moving`): drop the hand placement or put the member in the camera's frame.
- **A member attached with an offset to a host that moves across the frame** (`attached_moving`): the offset is applied where the host begins the shot.

Not yet: a member leaving one frame for another (`reframe`, with the velocity it had) and a plane at a world depth are filed (an#502, an#503).

## Why it is general

Every 2D and 3D animation tool exposes the same thing under another name: a Harmony peg, an After Effects null, a Blender Child Of constraint, a Maya parent constraint with space switching, Unity and Unreal attachment, a ROS tf frame. Positions compose up the tree; whatever is at infinity turns with the camera and never slides. The car, the deck, the train and the crane differ only in the shape of the tree.
