from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class MangaLayerSet:
    source: str = ""
    overlay_text: str = ""
    inpainted: str = ""
    rendered: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "MangaLayerSet":
        if not data:
            return cls()
        return cls(
            source=str(data.get("source", "")),
            overlay_text=str(data.get("overlay_text", "")),
            inpainted=str(data.get("inpainted", "")),
            rendered=str(data.get("rendered", "")),
        )


@dataclass(slots=True)
class MangaMaskSet:
    segment: str = ""
    bubble: str = ""
    brush: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "MangaMaskSet":
        if not data:
            return cls()
        return cls(
            segment=str(data.get("segment", "")),
            bubble=str(data.get("bubble", "")),
            brush=str(data.get("brush", "")),
        )
