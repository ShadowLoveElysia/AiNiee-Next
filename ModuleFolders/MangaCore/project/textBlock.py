from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.MangaCore.project.style import TextStyle
from ModuleFolders.MangaCore.types import BBox


@dataclass(slots=True)
class MangaTextBlock:
    block_id: str
    bbox: BBox
    rotation: int = 0
    source_text: str = ""
    translation: str = ""
    ocr_confidence: float = 0.0
    source_direction: str = "vertical"
    rendered_direction: str = "vertical"
    font_prediction: str = "dialogue_default"
    origin: str = "auto_planned"
    placement_mode: str = "bubble_auto"
    editable: bool = True
    style: TextStyle = field(default_factory=TextStyle)
    sprite_path: str = ""
    sprite_transform: dict[str, object] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block_id,
            "bbox": list(self.bbox),
            "rotation": self.rotation,
            "source_text": self.source_text,
            "translation": self.translation,
            "ocr_confidence": self.ocr_confidence,
            "source_direction": self.source_direction,
            "rendered_direction": self.rendered_direction,
            "font_prediction": self.font_prediction,
            "origin": self.origin,
            "placement_mode": self.placement_mode,
            "editable": self.editable,
            "style": self.style.to_dict(),
            "sprite_path": self.sprite_path,
            "sprite_transform": self.sprite_transform,
            "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MangaTextBlock":
        bbox = tuple(int(v) for v in data.get("bbox", [0, 0, 0, 0]))
        return cls(
            block_id=str(data.get("block_id", "")),
            bbox=bbox,  # type: ignore[arg-type]
            rotation=int(data.get("rotation", 0)),
            source_text=str(data.get("source_text", "")),
            translation=str(data.get("translation", "")),
            ocr_confidence=float(data.get("ocr_confidence", 0.0)),
            source_direction=str(data.get("source_direction", "vertical")),
            rendered_direction=str(data.get("rendered_direction", "vertical")),
            font_prediction=str(data.get("font_prediction", "dialogue_default")),
            origin=str(data.get("origin", "auto_planned")),
            placement_mode=str(data.get("placement_mode", "bubble_auto")),
            editable=bool(data.get("editable", True)),
            style=TextStyle.from_dict(data.get("style") if isinstance(data.get("style"), dict) else None),
            sprite_path=str(data.get("sprite_path", "")),
            sprite_transform=dict(data.get("sprite_transform", {})) if isinstance(data.get("sprite_transform"), dict) else {},
            flags=[str(item) for item in data.get("flags", [])] if isinstance(data.get("flags"), list) else [],
        )
