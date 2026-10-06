# an.formats

Numbers as text: a declared subset of d3-format, for counters (an#342).

A counter text block ([`an.stage.text.TextDescriptor`](an.stage.text.html.md#an.stage.text.TextDescriptor) `counter`) shows a
number that moves; what it draws is a string, and this module is the one
statement of how the number becomes the string. The format is a \*\*declared
mini-language, not Python’s\*\* `str.format` (which allows attribute access,
states no rounding and is not reproducible in a browser): one d3-format
specifier in braces, with optional literal text around it.

```pycon
>>> format_number(7, "Day {d}")
'Day 7'
>>> format_number(1234567, "{,d}")
'1,234,567'
>>> format_number(21.456, "{.1f} °C")
'21.5 °C'
>>> format_number(0.256, "{.0%}")
'26%'
>>> format_number(1500, "{.2s}")
'1.5k'
```

The subset, and what each specifier means (d3-format’s meaning, so a JavaScript
consumer can reproduce it with `d3.format`):

| `d`   | an integer                                                                                                                                                             |
|-------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `,d`  | an integer with `,` between thousands                                                                                                                                  |
| `.Nf` | fixed point, `N` decimals                                                                                                                                              |
| `.N%` | times 100, fixed point, `N` decimals, then `%`                                                                                                                         |
| `s`   | `N` significant digits (`.Ns`; default 6) with an SI prefix<br/>(`k`, `M`, `G`, …, `m`; `µ` and smaller are refused at<br/>typesetting by a face that lacks the glyph) |

**Rounding is to nearest, ties to even, on the float’s exact value** (Python’s
own correctly rounded formatting): `2.5` → `2` and `3.5` → `4` under
`d`; `0.125` → `0.12` under `.2f`. d3 rounds ties away from zero, so a
JavaScript reproduction must round half to even to agree on exact ties (the
frame grid rarely lands on one). Two further departures from d3’s defaults,
both stated: the minus sign is `-` (U+002D), because the embedded face has no
U+2212, and a value that rounds to zero never carries a sign (`-0.4` → `0`),
which is d3’s own rule.

### Module Attributes

| [`DFLT_SI_PRECISION`](#an.formats.DFLT_SI_PRECISION)   | d3's default of 6 significant digits.   |
|----------------------------------------------------------------------|-----------------------------------------|

### Functions

| [`parse_format`](#an.formats.parse_format)(fmt)         | Parse `fmt`: literal text around exactly one `{specifier}`.   |
|----------------------------------------------------------------------------|---------------------------------------------------------------|
| [`format_number`](#an.formats.format_number)(value, fmt) | `value` drawn as `fmt` says (see the module docstring).       |

### Classes

| [`NumberFormat`](#an.formats.NumberFormat)(prefix, type, precision, comma, ...)   | A parsed format: literal `prefix`, the specifier, literal `suffix`.   |
|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|

### Exceptions

| [`CounterFormatError`](#an.formats.CounterFormatError)   | A counter `format` outside the declared subset.   |
|-----------------------------------------------------------------------|---------------------------------------------------|

### *exception* an.formats.CounterFormatError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A counter `format` outside the declared subset.

### an.formats.DFLT_SI_PRECISION *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 6*

d3’s default of 6 significant digits.

* **Type:**
  `s` with no precision

### *class* an.formats.NumberFormat(prefix, type, precision, comma, suffix)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed format: literal `prefix`, the specifier, literal `suffix`.

### an.formats.format_number(value, fmt)

`value` drawn as `fmt` says (see the module docstring).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> [format_number(v, "{d}") for v in (2.5, 3.5, -0.4, 29.5)]
['2', '4', '0', '30']
>>> format_number(-1234.5, "{,d}")
'-1,234'
```

### an.formats.parse_format(fmt)

Parse `fmt`: literal text around exactly one `{specifier}`.

* **Return type:**
  [`NumberFormat`](#an.formats.NumberFormat)

```pycon
>>> parse_format("Day {d}").prefix
'Day '
>>> parse_format("{.3d}")
Traceback (most recent call last):
...
an.formats.CounterFormatError: counter format '{.3d}': `d` takes no precision (it is an integer); the subset is d, ,d, .Nf, .N%, s, .Ns
```
