"""Project-scoped snapshots and serialized editor writes using the cache format."""
from contextlib import contextmanager
import hashlib
from pathlib import Path

from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
from ModuleFolders.Infrastructure.Cache.CachePersistence import cache_write_transaction


class CacheEditConflict(ValueError):
    pass


def cache_path(output_path, cache_variant="main"):
    filenames = {"main": "AinieeCacheData.json", "proofread": "AinieeCacheData_proofread.json"}
    if cache_variant not in filenames:
        raise ValueError("Unsupported cache variant")
    return Path(output_path) / "cache" / filenames[cache_variant]


def resolve_output_path(value: str) -> Path:
    if not value or not value.strip():
        raise ValueError("Project path is required")
    path = Path(value.strip()).expanduser().resolve()
    if path.name in {"AinieeCacheData.json", "AinieeCacheData_proofread.json"}:
        if path.parent.name != "cache":
            raise ValueError("Cache file must be inside a project's cache directory")
        return path.parent.parent
    if path.name == "cache" and not (path / "cache/AinieeCacheData.json").is_file():
        return path.parent
    return path


def cache_revision(output_path: str | Path, cache_variant="main") -> str:
    path = cache_path(output_path, cache_variant)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_snapshot(output_path: str | Path, cache_variant="main"):
    path = cache_path(output_path, cache_variant)
    project = CacheManager.read_from_file(path)
    return project, project._cache_revision


@contextmanager
def edit_project(output_path: str | Path, *, expected_revision: str | None = None, replacement=None, cache_variant="main"):
    path = cache_path(output_path, cache_variant)
    if replacement is None and not path.is_file():
        raise FileNotFoundError(path)
    with cache_write_transaction(path):
        if replacement is None:
            project, revision = read_snapshot(output_path, cache_variant)
        else:
            project = replacement
            revision = cache_revision(output_path, cache_variant) if path.is_file() else None
            project._cache_path = str(path.resolve())
            project._cache_revision = revision
        if expected_revision is not None and revision != expected_revision:
            raise CacheEditConflict("Cache changed since it was loaded; reload and retry")
        manager = CacheManager(subscribe_events=False)
        manager.load_from_project(project)
        manager.save_to_file_require_path = str(output_path)
        manager.save_cache_filename = path.name
        yield manager, revision
