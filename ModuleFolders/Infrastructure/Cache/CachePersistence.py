"""Coordinate cache writers across threads and processes, including nested saves."""
from contextlib import contextmanager
from pathlib import Path
import threading

from ModuleFolders.Service.Agent.ExternalAgentWriterLease import _interprocess_lock

_lock = threading.RLock()
_transactions = threading.local()


class CacheWriteConflict(ValueError):
    pass


@contextmanager
def cache_write_transaction(path):
    path = Path(path).resolve()
    with _lock:
        active = getattr(_transactions, "paths", set())
        if path in active:
            yield
            return
        with _interprocess_lock(path):
            _transactions.paths = active | {path}
            try:
                yield
            finally:
                _transactions.paths = active
