# Transitions

```yaml meta
title: Transitions
author: ''
duration: 0.75
fps: 24
resolution:
  width: 320
  height: 240
default_renderer: stage
```

## Shot dusk (stage)

```yaml shot
duration: 0.5
transition:
  kind: fade
  duration: 0.25
```

```yaml entities
- kind: environment
  id: dusk
  store: environments
  ref: dusk
```

## Shot dawn (stage)

```yaml shot
duration: 0.5
transition:
  kind: dissolve
  duration: 0.25
```

```yaml entities
- kind: environment
  id: dawn
  store: environments
  ref: dawn
- kind: prop
  id: arrow
  store: props
  ref: arrow
```
