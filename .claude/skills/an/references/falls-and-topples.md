# Falls and topples: let-go items, bodies falling over, chain reactions

Rigid motion under gravity in the stage plane (stage px, y down). Two motions share one model (`an/stage/rigid.py`): a **drop** (`release`, see `holding-things.md`) and a **topple** (a body turning about its foot). Neither eases into its rest pose: things accelerate and stop when they hit.

## Gravity that reads as weight

The default is 980 px/s² (9.8 m/s² at 100 px per metre). Scale it to the figures: a figure H px tall standing for a person of about 1.7 m wants `9.8 * H / 1.7` (a 400 px figure: about 2200). Say it for the falls only, so the characters' limbs do not start to swing:

```yaml
solve: {ground: 502, gravity: down 2200, mode: pose}
```

## A let-go item

```yaml
- {kind: release, item: musket, at: 8.8}                      # falls straight down, lands on its nearest side
- {kind: release, item: musket, at: 8.8, onto: ground@-650}   # nudged to come to rest centred on x -650
- {kind: release, item: musket, at: 8.8, arc: 60}             # thrown up 60 px first (a toss)
```

It falls from where the hand lets go, spinning at a steady rate, touches the floor with one end, tips onto its side about that end, rocks a little (`bounce`, 0.15 by default; 0 lands dead) and rests on the side of its ink nearest to how it fell. `rotation:` forces the rest angle (it then spins in the air to reach it): leave it out unless the art must lie one way up. A long item carried low by a short arm is already through the floor line when it is let go; it then falls over its low end and lies in front of the line, and `an validate` warns: lift the arm before the release (`{kind: tween, target: stu/arm_l, property: rotation, to: 1.4, duration: 0.3, start: 8.45}`, release at 8.8, lower it after).

## A body falling over: `topple`

```yaml
- {kind: topple, id: cam_falls, body: cam, toward: right, push: 1.3, start: 1.0}
- {kind: topple, id: nap_falls, body: nap, toward: right, after: cam_falls, point: 'sabre@0.03,0.02', until: 'world@407,211'}
```

| field | means | default |
|---|---|---|
| `body` | the entity that falls, as one rigid piece, with everything a part of it holds (a sabre in a figurine's hand) | |
| `toward` | `left` or `right`: it turns about its lowest point on that side | right |
| `push` | rad/s it starts with (a kick, a trip) | 0.6 |
| `start` | when it starts (shot seconds) | |
| `id` | its name, for another topple's `after` | |
| `after` | the topple whose body knocks this one: it starts at the instant they first touch, turning at `knock` × the knocker's speed there over its own height | |
| `knock` | that share | 0.6 |
| `point`, `until` | a point of the body or of an item it holds (`path@u,v`, fractions of that node's drawing, 0,0 its top left; or `path@<bone>`, a bone or landmark of its rig), and where it stops (`path@u,v` or `path@<bone>` of another body, e.g. `han/head@eye_unpatched`, or `world@x,y`): the fall stops there and stays (stuck). On a rig with several root parts name the part a landmark is on (`han/head@…`, not `han@…`) | it falls until another point of it reaches its floor |
| `bounce` | restitution when it hits its floor | 0.15 |

Quote a `@u,v` point in a flow mapping (`point: 'sabre@0.03,0.02'`): unquoted, YAML reads the comma as the end of the entry.

It lands on the floor it stands on (its own foot line, so a camera standing farther back lies farther back). Nothing is cheated, so the compile refuses, with the fix, when:

- the push cannot tip it over its foot: `'cam' rocks back onto its feet ... Give it push: at least 1.06`;
- the knocker never reaches it: `'cam_falls''s 'cam' never touches 'nap' as it falls (it comes within 183 px): move 'nap' into its path`;
- the point's circle about the foot misses the target: `'sabre@0.03,0.02' passes 23 px beyond 'world@407,211' ... Move 'nap' about 30 px to the left`.

Read `meta.extensions.topple` in the compiled shot (`topples`: pivot, final angle, what it carried; `events`: `topple`, `hit` (on whom), `land`, `pin`, `bounce`, `rest`), and time sounds by them: `{sound: crash, at: {when: cam, event: land}}`, `{sound: clink, at: {when: nap, event: pin}}`.

**A trip** is the character's performance, authored: a walk that ends at the leg, a short `tween` of its `rotation` forward and back (or a stumble preset), and the topple of what it caught started at that instant with a `push`.

## Not built yet

- A character toppling as a body (its rig has joints; a trip is authored).
- Sliding and friction: a landing stops where it touches.
- A body coming to rest ON another (the knocker falls on to its own floor, passing where the struck body stood); a release onto a surface or another body.
- Several contacts at once, rolling, and anything in depth (the world layer's `reframe motion: ballistic` is the 3D flight).
