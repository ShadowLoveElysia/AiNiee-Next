from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ModuleFolders.MangaCore.types import BBox


@dataclass(slots=True)
class PositionedTextRun:
    text: str
    x: int
    y: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class LayoutPlan:
    block_id: str
    direction: str
    bbox: BBox
    font_family: str
    font_size: int
    line_spacing: float
    column_spacing: int = 0
    runs: list[PositionedTextRun] = field(default_factory=list)
    fit_ok: bool = True
    score: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block_id,
            "direction": self.direction,
            "bbox": list(self.bbox),
            "font_family": self.font_family,
            "font_size": self.font_size,
            "line_spacing": self.line_spacing,
            "column_spacing": self.column_spacing,
            "runs": [run.to_dict() for run in self.runs],
            "fit_ok": self.fit_ok,
            "score": self.score,
            "warnings": list(self.warnings),
        }
