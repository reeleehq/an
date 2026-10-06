# Text Swap

```yaml meta
title: Text Swap
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot count (stage)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: environment
  id: paper
  store: environments
  ref: paper
- kind: prop
  id: day
  store: props
  ref: day
  stage:
    at:
    - 60.0
    - 0.0
    scale: 1.0
```

```yaml actions
- kind: set
  target: day
  property: text
  value: d12
  at: 0.125
- kind: set
  target: day/block_0
  property: text
  value: d300
  at: 0.25
```
