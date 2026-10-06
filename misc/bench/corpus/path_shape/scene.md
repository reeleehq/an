# Path Shape

```yaml meta
title: Path Shape
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
```

## Shot draw (cutout)

```yaml shot
duration: 0.5
```

```yaml entities
- kind: prop
  id: badge
  store: props
  ref: badge
- kind: prop
  id: region
  store: props
  ref: region
- kind: prop
  id: border
  store: props
  ref: border
```

```yaml actions
- kind: tween
  target: region
  property: alpha
  from: 0.0
  to: 1.0
  duration: 0.5
  easing: linear
- kind: tween
  target: border
  property: trim_end
  from: 0.0
  to: 1.0
  duration: 0.5
  easing: linear
```
