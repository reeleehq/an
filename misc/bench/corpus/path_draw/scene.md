# Path Draw

```yaml meta
title: Path Draw
author: ''
duration: 0.5
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: cutout
style_pack: poster
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
  target: frame
  property: dash_offset
  from: 0.0
  to: 20.0
  duration: 0.5
  easing: linear
- kind: tween
  target: route
  property: trim_end
  from: 0.0
  to: 1.0
  duration: 0.5
  easing: linear
```
