# Rig Rest

```yaml meta
title: Rig Rest
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
```

## Shot splay (cutout)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: prop
  id: tripod
  store: props
  ref: tripod
  stage:
    at:
    - 0.0
    - 100.0
    scale: 0.6
```

```yaml actions
- kind: tween
  target: tripod
  property: rotation
  to: 0.3
  duration: 0.5
  from: 0.0
  easing: linear
```
