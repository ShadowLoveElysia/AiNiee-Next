from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from ModuleFolders.MangaCore.ops.history import OperationHistory
from ModuleFolders.MangaCore.project.manifest import MangaProjectManifest
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.scene import MangaScene


@dataclass(slots=True)
class MangaProjectSession:
    project_path: Path
    output_root: Path
    manifest: MangaProjectManifest
    scene: MangaScene
    pages: dict[str, MangaPage]
    config_snapshot: dict[str, object] = field(default_factory=dict)
    history: OperationHistory = field(default_factory=OperationHistory)

    def get_page(self, page_id: str) -> MangaPage:
        return self.pages[page_id]

    def set_page(self, page: MangaPage) -> None:
        self.pages[page.page_id] = page


class SessionRegistry:
    _lock: ClassVar[threading.Lock] = threading.Lock()
    _sessions: ClassVar[dict[str, MangaProjectSession]] = {}

    @classmethod
    def register(cls, session: MangaProjectSession) -> MangaProjectSession:
        with cls._lock:
            cls._sessions[session.manifest.project_id] = session
        return session

    @classmethod
    def get(cls, project_id: str) -> MangaProjectSession | None:
        with cls._lock:
            return cls._sessions.get(project_id)

    @classmethod
    def list_open_projects(cls) -> list[MangaProjectSession]:
        with cls._lock:
            return list(cls._sessions.values())

    @classmethod
    def remove(cls, project_id: str) -> None:
        with cls._lock:
            cls._sessions.pop(project_id, None)
