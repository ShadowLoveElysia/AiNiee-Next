from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ModuleFolders.MangaCore.constants import IMAGE_SUFFIXES


@dataclass(slots=True)
class ImportedInput:
    source_type: str
    images: list[Path]
    temp_root: Path | None = None


def create_temp_root(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def natural_key(path: Path) -> tuple[object, ...]:
    parts: list[object] = []
    chunk = ""
    for char in path.name.lower():
        if char.isdigit():
            chunk += char
            continue
        if chunk:
            parts.append(int(chunk))
            chunk = ""
        parts.append(char)
    if chunk:
        parts.append(int(chunk))
    return tuple(parts)


def collect_images(directory: Path) -> list[Path]:
    images = [path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES]
    return sorted(images, key=natural_key)
