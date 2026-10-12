"""Explicit package indexes shared by media installers and controller setup."""

import os
import sys

SOURCES = {
    "nju": ("https://mirror.nju.edu.cn/pypi/web/simple", "https://mirror.nju.edu.cn/pytorch/whl"),
    "official": ("https://pypi.org/simple", "https://download.pytorch.org/whl"),
}


def selected_source(value="") -> str:
    from ModuleFolders.Media.preferences import read_preferences
    source = value or os.environ.get("AINIEE_MEDIA_PACKAGE_SOURCE") or read_preferences().get("package_source", "nju")
    if source not in SOURCES:
        raise ValueError("Package source must be nju or official")
    return source


def package_indexes(build: str, source="") -> dict:
    if build not in {"cpu", "cu126", "cu128"}:
        raise ValueError("Unsupported Torch build")
    source = selected_source(source)
    pypi, torch_root = SOURCES[source]
    return {"source": source, "pypi": pypi, "torch": pypi if sys.platform == "darwin" else torch_root + "/" + build}
