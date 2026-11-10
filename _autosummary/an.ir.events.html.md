# an.ir.events

The visible events a compiled shot records, by name: what a sound cue’s `event` may say (an#804).

One vocabulary for every source: the hold layer ([`an.stage.hold`](an.stage.hold.html.md#module-an.stage.hold)) and the
`topple` pass ([`an.stage.topple`](an.stage.topple.html.md#module-an.stage.topple)) emit these names into their reports’
`events` lists, [`an.ir.schema.CueAnchor`](an.ir.schema.html.md#an.ir.schema.CueAnchor) validates an `event` against
them, and [`an.sound_anchors`](an.sound_anchors.html.md#module-an.sound_anchors) resolves one.

```pycon
>>> sorted(EVENTS)[:3], ALIASES["contact"]
(['bounce', 'grasp', 'hit'], ('grasp', 'place'))
```

### Module Attributes

| [`EVENTS`](#an.ir.events.EVENTS)   | Each event an item or a body can have, and what it means.   |
|-----------------------------------------------------------|-------------------------------------------------------------|
| [`ALIASES`](#an.ir.events.ALIASES)  | Names that stand for several events.                        |

### Functions

| [`event_names`](#an.ir.events.event_names)()   | Every name an `event` may say, for a message.   |
|------------------------------------------------------------------|-------------------------------------------------|

### an.ir.events.ALIASES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]]* *= {'contact': ('grasp', 'place')}*

Names that stand for several events.

### an.ir.events.EVENTS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'bounce': 'a bounce or a rock comes back down', 'grasp': "a hand takes the item (a swap's take included)", 'hit': 'a falling body first touches another (the report names it: \`on\`)', 'land': 'it first touches its floor (a dropped item, a toppled body)', 'pin': "a toppled body's point reaches its target and stays", 'place': "the item arrives where it is put (a swap's give included)", 'release': 'the item is let go', 'rest': 'it stops moving', 'topple': 'a body starts to fall over'}*

Each event an item or a body can have, and what it means.

### an.ir.events.event_names()

Every name an `event` may say, for a message.

```pycon
>>> event_names().startswith("grasp, place, release")
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
