# Text Card

```yaml meta
title: Text Card
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot card (stage)

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
    x: 0.0
    y: 0.0
    zoom: 1.3
    rotation: 0.12
```

```yaml entities
- kind: environment
  id: slate
  store: environments
  ref: slate
- kind: prop
  id: title
  store: props
  ref: title
- kind: prop
  id: label
  store: props
  ref: label
  stage:
    at:
    - 0.0
    - 30.0
    scale: 1.0
```

```yaml actions
- kind: set
  target: title/word_0
  property: alpha
  value: 0.0
- kind: set
  target: title/word_1
  property: alpha
  value: 0.0
- kind: tween
  target: title/word_0
  property: alpha
  to: 1.0
  duration: 0.25
  from: 0.0
  easing: linear
- kind: tween
  target: title/word_1
  property: alpha
  to: 1.0
  duration: 0.25
  from: 0.0
  easing: linear
  start: 0.125
```
