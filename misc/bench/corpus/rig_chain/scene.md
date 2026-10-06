# Rig Chain

```yaml meta
title: Rig Chain
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
```

## Shot pose (cutout)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: prop
  id: lamp
  store: props
  ref: arm_lamp
  stage:
    at:
    - 0.0
    - 105.0
    scale: 0.6
```

```yaml actions
- kind: tween
  target: lamp/base/upper
  property: rotation
  to: -0.3
  duration: 0.5
  from: 0.5235987755982988
  easing: linear
- kind: tween
  target: lamp/base/upper/fore
  property: rotation
  to: -0.4
  duration: 0.5
  from: -1.2217304763960306
  easing: linear
- kind: tween
  target: lamp/base/upper/fore/shade
  property: rotation
  to: 0.6
  duration: 0.5
  from: 0.0
  easing: linear
```
