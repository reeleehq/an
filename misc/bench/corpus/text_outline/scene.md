# Text Outline

```yaml meta
title: Text Outline
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot label (stage)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: environment
  id: plate
  store: environments
  ref: plate
- kind: prop
  id: label
  store: props
  ref: label
```

```yaml actions
- kind: set
  target: label/word_1
  property: alpha
  value: 0.0
- kind: tween
  target: label/word_1
  property: alpha
  to: 1.0
  duration: 0.25
  from: 0.0
  easing: linear
  start: 0.125
```
