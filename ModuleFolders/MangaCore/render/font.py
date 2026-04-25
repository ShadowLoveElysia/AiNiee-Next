from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


_REPO_ROOT = Path(__file__).resolve().parents[3]

_FONT_CANDIDATES = {
    "source han sans sc": [
        "manga-translator-ui-main/fonts/msyh.ttc",
        "manga-translator-ui-main/fonts/Arial-Unicode-Regular.ttf",
        "manga-translator-ui-main/fonts/NotoSansMonoCJK-VF.ttf.ttc",
    ],
    "dialogue_default": [
        "manga-translator-ui-main/fonts/anime_ace.ttf",
        "manga-translator-ui-main/fonts/comic shanns 2.ttf",
        "manga-translator-ui-main/fonts/Arial-Unicode-Regular.ttf",
    ],
    "ms gothic": [
        "manga-translator-ui-main/fonts/msgothic.ttc",
        "manga-translator-ui-main/fonts/Arial-Unicode-Regular.ttf",
    ],
}

_FALLBACK_FONTS = [
    "manga-translator-ui-main/fonts/msyh.ttc",
    "manga-translator-ui-main/fonts/Arial-Unicode-Regular.ttf",
    "manga-translator-ui-main/fonts/NotoSansMonoCJK-VF.ttf.ttc",
    "manga-translator-ui-main/fonts/anime_ace.ttf",
]


@lru_cache(maxsize=1)
def list_available_fonts() -> tuple[Path, ...]:
    found: list[Path] = []
    seen: set[Path] = set()
    for relative_path in [*_FALLBACK_FONTS, *[path for paths in _FONT_CANDIDATES.values() for path in paths]]:
        absolute_path = _REPO_ROOT / relative_path
        if absolute_path.exists() and absolute_path not in seen:
            found.append(absolute_path)
            seen.add(absolute_path)
    return tuple(found)


def resolve_font_path(font_family: str = "", font_prediction: str = "") -> Path | None:
    normalized = " ".join(str(font_family or font_prediction or "").lower().split())
    for key, candidates in _FONT_CANDIDATES.items():
        if normalized and (key in normalized or normalized in key):
            for relative_path in candidates:
                absolute_path = _REPO_ROOT / relative_path
                if absolute_path.exists():
                    return absolute_path

    for relative_path in _FALLBACK_FONTS:
        absolute_path = _REPO_ROOT / relative_path
        if absolute_path.exists():
            return absolute_path
    return None


def load_font(size: int, font_family: str = "", font_prediction: str = ""):
    font_path = resolve_font_path(font_family=font_family, font_prediction=font_prediction)
    if font_path is not None:
        try:
            return ImageFont.truetype(str(font_path), max(10, int(size)))
        except OSError:
            pass
    return ImageFont.load_default()
