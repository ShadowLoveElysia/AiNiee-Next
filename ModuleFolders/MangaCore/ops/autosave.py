from __future__ import annotations

from dataclasses import dataclass

from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.project.session import MangaProjectSession


@dataclass(slots=True)
class AutoSaveManager:
    session: MangaProjectSession
    dirty: bool = False

    def mark_dirty(self) -> None:
        self.dirty = True

    def flush(self) -> None:
        if not self.dirty:
            return
        MangaProjectPersistence.save_session(self.session)
        self.dirty = False
