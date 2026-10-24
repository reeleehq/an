# Joint Pin

```yaml meta
title: Joint Pin
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
```

## Shot reach (cutout)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: prop
  id: puppet
  store: props
  ref: arm
  stage:
    at:
    - -100.0
    - 60.0
- kind: prop
  id: wheel
  store: props
  ref: wheel
  stage:
    at:
    - 10.0
    - 10.0
    after: puppet
```

```yaml actions
- kind: tween
  target: puppet/torso
  property: rotation
  to: 0.2
  duration: 0.5
  from: 0.0
  easing: linear
- kind: pin
  point: puppet/fore@hand
  to: wheel@grip
```
