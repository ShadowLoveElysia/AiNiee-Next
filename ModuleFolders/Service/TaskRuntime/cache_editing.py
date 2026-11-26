"""Project-scoped snapshots and serialized editor writes using the cache format."""
from contextlib import contextmanager
import hashlib
from pathlib import Path

from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
from ModuleFolders.Infrastructure.Cache.CachePersistence import cache_write_transaction


class CacheEditConflict(ValueError):
    pass


def resolve_output_path(value: str) -> Path:
    if not value or not value.strip():
        raise ValueError("Project path is required")
    path = Path(value.strip()).expanduser().resolve()
    if path.name == "AinieeCacheData.json":
        if path.parent.name != "cache":
            raise ValueError("Cache file must be inside a project's cache directory")
        return path.parent.parent
    if path.name == "cache" and not (path / "cache/AinieeCacheData.json").is_file():
        return path.parent
    return path


def cache_revision(output_path: str | Path) -> str:
    path = Path(output_path) / "cache/AinieeCacheData.json"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_snapshot(output_path: str | Path):
    path = Path(output_path) / "cache/AinieeCacheData.json"
    project = CacheManager.read_from_file(path)
    return project, project._cache_revision


@contextmanager
def edit_project(output_path: str | Path, *, expected_revision: str | None = None, replacement=None):
    path = Path(output_path) / "cache/AinieeCacheData.json"
    if replacement is None and not path.is_file():
        raise FileNotFoundError(path)
    with cache_write_transaction(path):
        if replacement is None:
            project, revision = read_snapshot(output_path)
        else:
            project = replacement
            revision = cache_revision(output_path) if path.is_file() else None
            project._cache_path = str(path.resolve())
            project._cache_revision = revision
        if expected_revision is not None and revision != expected_revision:
            raise CacheEditConflict("Cache changed since it was loaded; reload and retry")
        manager = CacheManager(subscribe_events=False)
        manager.load_from_project(project)
        manager.save_to_file_require_path = str(output_path)
        yield manager, revision
