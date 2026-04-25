from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class BlobStore:
    project_root: Path

    def page_dir(self, page_key: str) -> Path:
        return self.project_root / "pages" / page_key

    def thumbs_dir(self) -> Path:
        return self.project_root / "thumbs"

    def cache_dir(self) -> Path:
        return self.project_root / "cache"

    def exports_dir(self) -> Path:
        return self.project_root / "exports"
