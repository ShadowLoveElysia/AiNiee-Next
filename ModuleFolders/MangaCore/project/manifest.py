from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class MangaProjectManifest:
    project_id: str
    task_id: str
    name: str
    source_type: str
    created_at: str
    updated_at: str
    source_lang: str = "ja"
    target_lang: str = "zh_cn"
    profile_name: str = "default"
    rules_profile_name: str = "default"
    page_count: int = 0
    status: str = "editable"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MangaProjectManifest":
        return cls(
            project_id=str(data.get("project_id", "")),
            task_id=str(data.get("task_id", "")),
            name=str(data.get("name", "")),
            source_type=str(data.get("source_type", "directory")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            source_lang=str(data.get("source_lang", "ja")),
            target_lang=str(data.get("target_lang", "zh_cn")),
            profile_name=str(data.get("profile_name", "default")),
            rules_profile_name=str(data.get("rules_profile_name", "default")),
            page_count=int(data.get("page_count", 0)),
            status=str(data.get("status", "editable")),
        )
