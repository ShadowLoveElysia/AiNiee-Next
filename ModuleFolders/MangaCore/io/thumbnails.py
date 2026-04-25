from __future__ import annotations

from pathlib import Path

from PIL import Image

from ModuleFolders.MangaCore.constants import THUMBNAIL_SIZE


def generate_thumbnail(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image.thumbnail(THUMBNAIL_SIZE)
        image.save(target_path, format="WEBP")
