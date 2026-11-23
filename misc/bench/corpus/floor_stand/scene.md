# Floor Stand

```yaml meta
title: Floor Stand
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
```

## Shot floor (cutout)

```yaml shot
duration: 0.5
solve:
  ground: 80.0
```

```yaml entities
- kind: prop
  id: post
  store: props
  ref: footed
  stage:
    at:
    - -70.0
    - 80.0
    scale: 0.4
- kind: prop
  id: cup
  store: props
  ref: cup
  stage:
    at:
    - 20.0
    - 80.0
    scale: 0.4
```

```yaml actions
- kind: tween
  target: cup
  property: x
  to: 90.0
  duration: 0.5
  from: 20.0
  easing: linear
```
