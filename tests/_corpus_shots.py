"""The core corpus's compiled shots, for the tests that check a contract against real documents."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _corpus_shots():
    """``(scene name, shot, fps, project, compiled document)`` for every shot of the bench corpus."""
    import warnings

    from an.adapters.cutout.compile import compile_shot
    from an.bench.capture import stage_copy
    from an.bench.corpus import DFLT_FIXTURES
    from an.project import load

    def shots(tmp):
        for name, fixture in sorted(DFLT_FIXTURES.items()):
            copy = stage_copy(REPO_ROOT / fixture.path, tmp / name)
            if fixture.prepare is not None:
                fixture.prepare(copy)
            project = load(copy)
            meta = project.scene.meta
            for shot in project.scene.timeline:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    doc = compile_shot(
                        shot,
                        mall=project.mall,
                        fps=int(round(meta.fps)),
                        width=meta.resolution.width,
                        height=meta.resolution.height,
                    )
                yield name, shot, meta.fps, project, doc

    return shots
