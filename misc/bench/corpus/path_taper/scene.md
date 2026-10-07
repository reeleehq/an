# Path Taper

```yaml meta
title: Path Taper
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
  id: brush
  store: props
  ref: brush
- kind: prop
  id: arrow
  store: props
  ref: arrow
```

```yaml actions
- kind: tween
  target: arrow
  property: trim_end
  from: 0.0
  to: 1.0
  duration: 0.5
  easing: linear
```
