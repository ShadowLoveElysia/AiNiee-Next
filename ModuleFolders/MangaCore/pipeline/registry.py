from __future__ import annotations


class PipelineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, object] = {}

    def register(self, stage: str, engine: object) -> None:
        self._engines[stage] = engine

    def get(self, stage: str) -> object | None:
        return self._engines.get(stage)
