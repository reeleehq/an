"""The deterministic lip-sync provider: now `cutan.audio.offline_lipsync` (an#225).

This path is a live alias with a warning; ``pip install "an[cutout]"`` provides it. It is
removed once nothing under the local package ecosystem imports it.
"""

from an._shims import moved_to_package

moved_to_package(__name__, "cutan.audio.offline_lipsync")
