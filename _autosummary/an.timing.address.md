# an.timing.address

The address grammar: one way to name an animatable value, in every genre.

```default
<entity>[/<node>…]:<field>[@<qualifier>]
```

- `entity` — what the scene holds (a character, a prop, the camera, a view);
- `/<node>…` — a path inside it (`charlie/left_arm`); `root` is the
  stage’s reserved scene root, which the camera lowers onto;
- `field` — a property the entity kind’s property space declares
  ([`an.timing.spaces`](an.timing.spaces.md#module-an.timing.spaces)). It may be a **dotted** path (`view:light.color`),
  and a dotted segment names a declared field, never a member *inside* a
  composite value: an `orbit` interpolates as one value, so
  `view:camera.azimuth` is addressable only if the space declares
  `camera.azimuth` itself;
- `@<qualifier>` — a variant of the field (`mouth:viseme@happy`, a variant
  swap set), which the stage already emits.

The compiled form’s `(target, property)` pair is exactly
`(entity/nodes, field@qualifier)`, and the golden vectors key every state by
the address string.

```pycon
>>> a = parse_address("charlie/head/mouth:viseme@happy")
>>> a.entity, a.nodes, a.field, a.qualifier
('charlie', ('head', 'mouth'), 'viseme', 'happy')
>>> a.target, a.property
('charlie/head/mouth', 'viseme@happy')
>>> str(parse_address("view:light.color")), parse_address("view:light.color").field_path
('view:light.color', ('light', 'color'))
>>> str(Address.of("root", "pivot_x"))
'root:pivot_x'
>>> parse_address("charlie:")
Traceback (most recent call last):
 ...
an.timing.address.AddressError: 'charlie:': the field is empty
```

### Module Attributes

| [`ENTITY_FIELD_SEP`](#an.timing.address.ENTITY_FIELD_SEP)   | Separators of the grammar; none of them may appear inside a name.   |
|---------------------------------------------------------------------|---------------------------------------------------------------------|

### Functions

| [`format_address`](#an.timing.address.format_address)(target, prop)   | The address string of a compiled `(target, property)` pair, unvalidated (the fast path for keying states; [`Address.of()`](#an.timing.address.Address.of) validates).   |
|---------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`parse_address`](#an.timing.address.parse_address)(text)            | `text` as an [`Address`](#an.timing.address.Address); raises [`AddressError`](#an.timing.address.AddressError) naming the fault.                         |

### Classes

| [`Address`](#an.timing.address.Address)(entity[, nodes, field, qualifier])   | A parsed address.   |
|-----------------------------------------------------------------------------------------------|---------------------|

### Exceptions

| [`AddressError`](#an.timing.address.AddressError)   | A string is not an address under the grammar.   |
|-----------------------------------------------------------------|-------------------------------------------------|

### *class* an.timing.address.Address(entity, nodes=(), field='', qualifier=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed address. `str(address)` writes it back unchanged.

#### *property* field_path *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

The dotted field, split.

#### *classmethod* of(target, prop)

The address of a compiled `(target, property)` pair (validated).

* **Return type:**
  [`Address`](#an.timing.address.Address)

#### *property* property *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

the field and its qualifier.

* **Type:**
  The compiled form’s `property`

#### *property* target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

the entity and its node path.

* **Type:**
  The compiled form’s `target`

### *exception* an.timing.address.AddressError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A string is not an address under the grammar.

### an.timing.address.ENTITY_FIELD_SEP *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ':'*

Separators of the grammar; none of them may appear inside a name.

### an.timing.address.format_address(target, prop)

The address string of a compiled `(target, property)` pair, unvalidated
(the fast path for keying states; [`Address.of()`](#an.timing.address.Address.of) validates).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.timing.address.parse_address(text)

`text` as an [`Address`](#an.timing.address.Address); raises [`AddressError`](#an.timing.address.AddressError) naming the fault.

* **Return type:**
  [`Address`](#an.timing.address.Address)

```pycon
>>> parse_address("charlie/left_arm:rotation").target
'charlie/left_arm'
>>> parse_address("a::b")
Traceback (most recent call last):
 ...
an.timing.address.AddressError: 'a::b': an address has exactly one ':', found 2
```
