---
name: an-dev-path
description: Stroked paths in the `an` repo (an#160, epic #9 Wave 9) — the `PathDescriptor` prop, compile-time Bézier flattening, `trim_start`/`trim_end` as ordinary numeric properties, the arrowhead at the trimmed tip, and the exact Python↔runtime geometry parity. Load before touching `an/paths.py`, `an/adapters/cutout/path.py`, `_build_path_subtree`, `PathJSON`, `pathGeometry`/`drawPath`/`applyTrim` in `runtime.js`, or anything that draws a stroke. Triggers on "path", "stroke", "arrow", "arrowhead", "trim", "draw-on", "route", "connector", "border", "timeline line", "hand-drawn wobble".
---

# an-dev-path — stroked paths, trim, arrowheads

## The model in five lines

- A path is a **prop** whose document `kind` is `PathDescriptor` (`an/paths.py`), in the props store. `_build_prop_subtree` dispatches on the document kind; no scene-IR field, no migration.
- The entity's `overrides` are merged over the stored document and validated **strictly** by `an.paths.resolve_path` — the one call both the compiler and `an validate` make, so their verdicts agree (`tests/test_path.py::test_validate_and_compile_reach_the_same_verdict`).
- Cubic Béziers are **flattened in the compiler** (`an.adapters.cutout.path.flatten_curve`, uniform in the parameter). The wire (`VisualJSON.path`, a `PathJSON`) only ever carries a polyline.
- `trim_start` / `trim_end` are in `an.base.TRANSFORM_PROPERTIES` (rest 0.0 / 1.0), so they tween, step and hold like `alpha`. They are path-only: `_check_trim_target` (compile) and `_check_trim_targets` (validate) refuse any other target, and the runtime's `applyTrim` throws.
- The runtime draws `pathGeometry(points, trim_start, trim_end, head_length, head_width)` → `{stroke, head}`; `an/adapters/cutout/path.py::path_geometry` is its **executable spec**.

## Invariants that are not obvious

1. **Parity is EXACT, not a tolerance** — and that is a design constraint, not luck. Both sides use only IEEE `+ - * / sqrt` in the same order. No `atan2`/`cos`/`sin` (V8 and libm may differ in the last ulp): a direction is a unit vector, the head's normal is `(-uy, ux)`. Python must use `math.sqrt`, never `** 0.5` (`pow` is not correctly rounded). If you add a geometry operation, add it to both sides in the same order, or the parity test goes red.
2. **A tip on a vertex belongs to the INCOMING leg** (`_segment_at`/`pathSegmentAt` return the first non-degenerate segment whose end reaches `s`). That is what keeps the head from flipping to the next leg's direction on the frame the tip reaches a corner.
3. **The head grows in**: while the visible length is shorter than `head_length`, head length and width scale by `visible / head_length`. The stroke stops `HEAD_STROKE_INSET` (half) a head-length back from the tip, inside the head.
4. **A trim tween with no `from_value` starts at the DOCUMENT's trim** (`_SwapVocabulary.path_trims`), not at the global rest 0/1 — otherwise `trim_end: 0` + "tween to 1" drew the whole path from frame 0 (review M2).
5. **Known limitation at sharp corners**: the head is straight along the incoming leg while the stroke's end is measured along the arc, so for a tip within one head-length past a sharp corner the head's base sticks out behind the corner and a small gap can show. Flattened Béziers are smooth enough not to show it; a mitred "head follows the path" is future work.
6. **Trim is order-independent and clamped**: the span is `[clamp(min), clamp(max)]` of the two values, so an overshooting easing cannot draw past the ends.
7. **Byte identity**: `VisualJSON.path` is omit-when-unset (the an#112 rule), so no pre-existing corpus hash moves. Any new `PathJSON` field is safe (it only exists on path visuals), but a new `VisualJSON` field is not — give it its own omit serializer in the same commit.
8. `test_loud_discards.py` exempts `trim_*` from its write-7-and-look loop (`PATH_ONLY`) because they land on the path VISUAL, not the node; `test_path.py::test_the_runtime_applies_trim_to_the_path_visual` is the check that covers them.

## Not built (the rest of Wave 9's path work)

The bench palette (`an/bench/palette.py`) has no branch for path visuals — a corpus scene with a path needs one. StylePack `stroke` role (`REACHABLE_ROLES` is closed and each role is asserted to reach a fixed scene — add the role and a path to that scene together); dashes; variable width / taper; closed and filled shapes (borders as regions); per-point trim easing / multiple heads (tail arrowhead); arc-length-uniform Bézier sampling; a corpus scene + golden for paths (the pixel test is analytic, in the browser lane).

## A style layer on top (hand-drawn wobble, stroke jitter)

The seam is `flatten_curve` → polyline → `pathGeometry`. A wobble is a **compile-time** displacement of the flattened polyline (seeded by entity name, like `blink_phase`), so the runtime and the parity spec stay untouched and the result is deterministic. A per-frame "boil" (jitter that changes on twos) is NOT a displacement of one polyline — it needs either several pre-displaced polylines selected by a step channel (the swap-channel shape) or a seeded runtime noise with a Python twin. Do not add `Math.random` to the runtime: the determinism probe watches for exactly that.
