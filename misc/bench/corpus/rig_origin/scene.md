# Rig Origin

```yaml meta
title: Rig Origin
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
```

## Shot topple (cutout)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: prop
  id: footed
  store: props
  ref: footed
  stage:
    at:
    - -70.0
    - 60.0
    scale: 0.4
- kind: prop
  id: centred
  store: props
  ref: centred
  stage:
    at:
    - 70.0
    - 60.0
    scale: 0.4
```

```yaml actions
- kind: tween
  target: footed
  property: rotation
  to: -0.4
  duration: 0.5
  from: 0.0
  easing: linear
```
