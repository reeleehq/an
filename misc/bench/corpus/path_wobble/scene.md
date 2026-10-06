# Path Wobble

```yaml meta
title: Path Wobble
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
  id: frame
  store: props
  ref: frame
- kind: prop
  id: route
  store: props
  ref: route
```

```yaml actions
- kind: tween
  target: route
  property: trim_end
  from: 0.0
  to: 1.0
  duration: 0.5
  easing: linear
```
