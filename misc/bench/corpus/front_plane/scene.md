# Front Plane

```yaml meta
title: Front Plane
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot rail (stage)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: environment
  id: stage
  store: environments
  ref: stage
- kind: prop
  id: label
  store: props
  ref: label
  stage:
    at:
    - 0.0
    - 0.0
    scale: 1.0
```

```yaml actions
- kind: tween
  target: stage/rail
  property: y
  from: 60.0
  to: 0.0
  duration: 0.5
  easing: linear
```
