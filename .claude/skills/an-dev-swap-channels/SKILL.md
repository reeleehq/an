---
name: an-dev-swap-channels
description: Moved to the `cutan-dev-swap-channels` skill in the cutan repository (an#225). Use `cutan-dev-swap-channels` for whole-character swaps, `swap_poses`, and the view/eyelid/viseme conventions (the generic swap mechanism itself is in `an-dev-stage`). Triggers on the old name.
---

# an-dev-swap-channels: moved

This skill moved with the cut-out genre to the `cutan` package (github.com/thorwhalen/cutan) as **`cutan-dev-swap-channels`**. Install the genre with `pip install "an[cutout]"`; the skill lives in that repository's `.claude/skills/cutan-dev-swap-channels/`. This stub stays for one release cycle so an agent that looks for the old name finds the new one.
