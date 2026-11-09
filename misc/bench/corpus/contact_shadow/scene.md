# Contact Shadow

```yaml meta
title: Contact Shadow
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
light:
  key: upper_left
```

## Shot slide (cutout)

```yaml shot
duration: 0.5
solve:
  ground: 80.0
joints:
- type: support
  a: crate
  b: ground
- type: support
  a: ball
  b: ground
```

```yaml entities
- kind: prop
  id: crate
  store: props
  ref: crate
  stage:
    at:
    - -90.0
    - 80.0
- kind: prop
  id: ball
  store: props
  ref: ball
  stage:
    at:
    - 70.0
    - 80.0
```

```yaml actions
- kind: tween
  target: crate
  property: x
  from: -90.0
  to: -30.0
  duration: 0.5
  easing: linear
- kind: tween
  target: ball
  property: y
  from: 80.0
  to: 30.0
  duration: 0.25
  start: 0.05
  easing: linear
```
