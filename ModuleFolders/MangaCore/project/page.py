from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.MangaCore.project.layers import MangaLayerSet, MangaMaskSet
from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock


@dataclass(slots=True)
class MangaPage:
    page_id: str
    index: int
    width: int
    height: int
    status: str = "idle"
    thumbnail_path: str = ""
    selected: bool = False
    layers: MangaLayerSet = field(default_factory=MangaLayerSet)
    masks: MangaMaskSet = field(default_factory=MangaMaskSet)
    text_blocks: list[MangaTextBlock] = field(default_factory=list)
    last_pipeline_stage: str = "preparing"

    def to_scene_entry(self) -> dict[str, object]:
        return {
            "page_id": self.page_id,
            "index": self.index,
            "status": self.status,
            "thumbnail_path": self.thumbnail_path,
        }

    def to_meta_dict(self) -> dict[str, object]:
        return {
            "page_id": self.page_id,
            "index": self.index,
            "width": self.width,
            "height": self.height,
            "status": self.status,
            "layers": self.layers.to_dict(),
            "masks": self.masks.to_dict(),
            "text_block_count": len(self.text_blocks),
            "last_pipeline_stage": self.last_pipeline_stage,
        }

    def to_blocks_dict(self) -> list[dict[str, object]]:
        return [block.to_dict() for block in self.text_blocks]

    @classmethod
    def from_disk(
        cls,
        meta: dict[str, object],
        blocks: list[dict[str, object]],
        thumbnail_path: str,
    ) -> "MangaPage":
        return cls(
            page_id=str(meta.get("page_id", "")),
            index=int(meta.get("index", 0)),
            width=int(meta.get("width", 0)),
            height=int(meta.get("height", 0)),
            status=str(meta.get("status", "idle")),
            thumbnail_path=thumbnail_path,
            layers=MangaLayerSet.from_dict(meta.get("layers") if isinstance(meta.get("layers"), dict) else None),
            masks=MangaMaskSet.from_dict(meta.get("masks") if isinstance(meta.get("masks"), dict) else None),
            text_blocks=[MangaTextBlock.from_dict(item) for item in blocks],
            last_pipeline_stage=str(meta.get("last_pipeline_stage", "preparing")),
        )
