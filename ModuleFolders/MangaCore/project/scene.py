from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ScenePageRef:
    page_id: str
    index: int
    status: str
    thumbnail_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "page_id": self.page_id,
            "index": self.index,
            "status": self.status,
            "thumbnail_path": self.thumbnail_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ScenePageRef":
        return cls(
            page_id=str(data.get("page_id", "")),
            index=int(data.get("index", 0)),
            status=str(data.get("status", "idle")),
            thumbnail_path=str(data.get("thumbnail_path", "")),
        )


@dataclass(slots=True)
class MangaScene:
    project_id: str
    current_page_id: str = ""
    render_preset: str = "default"
    export_preset: str = "reader_default"
    pages: list[ScenePageRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "current_page_id": self.current_page_id,
            "render_preset": self.render_preset,
            "export_preset": self.export_preset,
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MangaScene":
        return cls(
            project_id=str(data.get("project_id", "")),
            current_page_id=str(data.get("current_page_id", "")),
            render_preset=str(data.get("render_preset", "default")),
            export_preset=str(data.get("export_preset", "reader_default")),
            pages=[ScenePageRef.from_dict(item) for item in data.get("pages", [])],
        )
