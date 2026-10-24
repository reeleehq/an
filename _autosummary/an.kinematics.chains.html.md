# an.kinematics.chains

Closed-form pieces for chains: the two-link reach and its reachable range.

A two-link chain (an upper arm and a forearm, a thigh and a shin) with its
root held and its tip asked for is the common case of every puppet, and it
has an exact answer by the law of cosines. The solver uses it as the initial
guess for such chains before projecting (so the common case converges in a
round and the bend side is an explicit choice, never an interpolation), and
callers use it directly to ask whether a grip is in reach at all.

```pycon
>>> t1, t2 = two_bone((0.0, 0.0), (5.0, 0.0), (3.0, 4.0))
>>> tip = (3.0 * math.cos(t1) + 4.0 * math.cos(t2), 3.0 * math.sin(t1) + 4.0 * math.sin(t2))
>>> tuple(round(c, 9) for c in tip)
(5.0, 0.0)
>>> two_bone((0.0, 0.0), (8.0, 0.0), (3.0, 4.0)) is None
True
```

### Functions

| [`reach`](#an.kinematics.chains.reach)(l1, l2)                               | The `(nearest, farthest)` distance from the root a two-link chain of lengths `l1` and `l2` can put its tip.                                                                                                         |
|----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`two_bone`](#an.kinematics.chains.two_bone)(root, target, lengths, \*[, bend]) | Absolute angles `(theta1, theta2)` of two links of `lengths` `(l1, l2)` hinged at `root` so that the tip meets `target`; `None` when the target is out of [`reach()`](#an.kinematics.chains.reach). |

### an.kinematics.chains.reach(l1, l2)

The `(nearest, farthest)` distance from the root a two-link chain of
lengths `l1` and `l2` can put its tip.

```pycon
>>> reach(3.0, 4.0)
(1.0, 7.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### an.kinematics.chains.two_bone(root, target, lengths, , bend=1)

Absolute angles `(theta1, theta2)` of two links of `lengths`
`(l1, l2)` hinged at `root` so that the tip meets `target`; `None`
when the target is out of [`reach()`](#an.kinematics.chains.reach).

`bend` is `+1` for a middle joint that deviates counter-clockwise from
the root-to-target line (which, on a y-down screen, reads as clockwise),
`-1` for the other side. Each side is a different pose of the same chain;
which one is right is the author’s (or a hinge range’s) choice.

```pycon
>>> t1, t2 = two_bone((0.0, 0.0), (1.0, 1.0), (1.0, 1.0), bend=1)
>>> round(math.degrees(t1)), round(math.degrees(t2))
(90, 0)
>>> t1, t2 = two_bone((0.0, 0.0), (1.0, 1.0), (1.0, 1.0), bend=-1)
>>> round(math.degrees(t1)), round(math.degrees(t2))
(0, 90)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)
