from __future__ import annotations

from dataclasses import asdict, dataclass

from ModuleFolders.MangaCore.constants import DEFAULT_TEXT_STYLE


@dataclass(slots=True)
class TextStyle:
    font_family: str = DEFAULT_TEXT_STYLE["font_family"]
    font_size: int = DEFAULT_TEXT_STYLE["font_size"]
    line_spacing: float = DEFAULT_TEXT_STYLE["line_spacing"]
    fill: str = DEFAULT_TEXT_STYLE["fill"]
    stroke_color: str = DEFAULT_TEXT_STYLE["stroke_color"]
    stroke_width: int = DEFAULT_TEXT_STYLE["stroke_width"]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "TextStyle":
        if not data:
            return cls()
        return cls(
            font_family=str(data.get("font_family", DEFAULT_TEXT_STYLE["font_family"])),
            font_size=int(data.get("font_size", DEFAULT_TEXT_STYLE["font_size"])),
            line_spacing=float(data.get("line_spacing", DEFAULT_TEXT_STYLE["line_spacing"])),
            fill=str(data.get("fill", DEFAULT_TEXT_STYLE["fill"])),
            stroke_color=str(data.get("stroke_color", DEFAULT_TEXT_STYLE["stroke_color"])),
            stroke_width=int(data.get("stroke_width", DEFAULT_TEXT_STYLE["stroke_width"])),
        )
