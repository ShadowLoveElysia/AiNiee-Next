from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, ClassVar, Iterator

from ModuleFolders.MangaCore.ops.history import OperationHistory
from ModuleFolders.MangaCore.project.manifest import MangaProjectManifest
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.scene import MangaScene


class LazyPageDict(dict[str, MangaPage]):
    """Dictionary-compatible page store that loads page details on first access."""

    def __init__(
        self,
        *args,
        known_page_ids: list[str] | None = None,
        loader: Callable[[str], MangaPage] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._known_page_ids = list(known_page_ids or [])
        self._known_page_id_set = set(self._known_page_ids)
        self._loader = loader

    def set_loader(self, loader: Callable[[str], MangaPage] | None) -> None:
        self._loader = loader

    def set_known_page_ids(self, page_ids: list[str]) -> None:
        self._known_page_ids = list(page_ids)
        self._known_page_id_set = set(page_ids)

    def add_known_page_id(self, page_id: str) -> None:
        if page_id in self._known_page_id_set:
            return
        self._known_page_ids.append(page_id)
        self._known_page_id_set.add(page_id)

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, key) or (isinstance(key, str) and key in self._known_page_id_set)

    def __missing__(self, key: str) -> MangaPage:
        if key not in self._known_page_id_set or self._loader is None:
            raise KeyError(key)
        page = self._loader(key)
        dict.__setitem__(self, page.page_id, page)
        return page

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def _ordered_keys(self) -> list[str]:
        keys = list(self._known_page_ids)
        for key in dict.keys(self):
            if key not in self._known_page_id_set:
                keys.append(key)
        return keys

    def _load_all(self) -> None:
        for key in self._ordered_keys():
            self[key]

    def __iter__(self):
        return iter(self._ordered_keys())

    def __len__(self) -> int:
        return len(self._ordered_keys())

    def keys(self):
        return self._ordered_keys()

    def values(self):
        self._load_all()
        return dict.values(self)

    def items(self):
        self._load_all()
        return dict.items(self)

    def loaded_values(self):
        return dict.values(self)


@dataclass(slots=True)
class MangaProjectSession:
    project_path: Path
    output_root: Path
    manifest: MangaProjectManifest
    scene: MangaScene
    pages: dict[str, MangaPage]
    page_loader: Callable[[str], MangaPage] | None = None
    config_snapshot: dict[str, object] = field(default_factory=dict)
    history: OperationHistory = field(default_factory=OperationHistory)
    dirty_page_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        page_ids = [page_ref.page_id for page_ref in self.scene.pages]
        if isinstance(self.pages, LazyPageDict):
            self.pages.set_known_page_ids(page_ids)
            self.pages.set_loader(self.page_loader)
        elif self.page_loader is not None:
            self.pages = LazyPageDict(self.pages, known_page_ids=page_ids, loader=self.page_loader)

    def has_page(self, page_id: str) -> bool:
        if page_id in self.pages:
            return True
        return any(page_ref.page_id == page_id for page_ref in self.scene.pages)

    def get_page(self, page_id: str) -> MangaPage:
        page = dict.get(self.pages, page_id) if isinstance(self.pages, LazyPageDict) else self.pages.get(page_id)
        if page is not None:
            return page
        if not self.has_page(page_id) or self.page_loader is None:
            raise KeyError(page_id)
        page = self.page_loader(page_id)
        self.pages[page.page_id] = page
        return page

    def set_page(self, page: MangaPage) -> None:
        self.pages[page.page_id] = page
        if isinstance(self.pages, LazyPageDict) and page.page_id not in self.pages._known_page_id_set:
            self.pages.add_known_page_id(page.page_id)
        self.mark_page_dirty(page.page_id)

    def mark_page_dirty(self, page_id: str) -> None:
        self.dirty_page_ids.add(page_id)

    def mark_all_pages_dirty(self) -> None:
        self.dirty_page_ids.update(page_ref.page_id for page_ref in self.scene.pages)

    def clear_page_dirty(self, page_id: str) -> None:
        self.dirty_page_ids.discard(page_id)

    def iter_pages(self) -> Iterator[MangaPage]:
        for page_ref in sorted(self.scene.pages, key=lambda item: item.index):
            yield self.get_page(page_ref.page_id)

    def load_all_pages(self) -> list[MangaPage]:
        return list(self.iter_pages())

    def loaded_pages(self) -> list[MangaPage]:
        if isinstance(self.pages, LazyPageDict):
            return list(self.pages.loaded_values())
        return list(self.pages.values())


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
