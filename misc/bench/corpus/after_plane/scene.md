# After Plane

```yaml meta
title: After Plane
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot window (stage)

```yaml shot
duration: 0.5
camera:
  keys:
  - at: 0.0
    x: 0.0
    y: 0.0
    zoom: 1.0
    rotation: 0.0
    easing: linear
  - at: 0.5
    x: 60.0
    y: 0.0
    zoom: 1.0
    rotation: 0.0
```

```yaml entities
- kind: environment
  id: set
  store: environments
  ref: window
- kind: prop
  id: disc
  store: props
  ref: disc
  stage:
    at:
    - -10.0
    - -20.0
    scale: 0.15
    after: set/sky
```
