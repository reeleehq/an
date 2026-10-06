# Text Counter

```yaml meta
title: Text Counter
author: ''
duration: 1.25
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot calendar (stage)

```yaml shot
duration: 1.25
```

```yaml entities
- kind: environment
  id: wall
  store: environments
  ref: wall
- kind: prop
  id: day
  store: props
  ref: day
  stage:
    at:
    - 40.0
    - 0.0
    scale: 1.0
```

```yaml actions
- kind: tween
  target: day
  property: value
  to: 30.0
  duration: 1.0
  easing: linear
```
