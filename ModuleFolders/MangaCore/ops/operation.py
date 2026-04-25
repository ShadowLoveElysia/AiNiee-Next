from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Operation:
    type: str
    page_id: str = ""
    block_id: str = ""
    patch: dict[str, object] = field(default_factory=dict)
    payload: dict[str, object] = field(default_factory=dict)
    ops: list["Operation"] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "page_id": self.page_id,
            "block_id": self.block_id,
            "patch": dict(self.patch),
            "payload": dict(self.payload),
            "ops": [op.to_dict() for op in self.ops],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Operation":
        nested_ops = [cls.from_dict(item) for item in data.get("ops", [])] if isinstance(data.get("ops"), list) else []
        return cls(
            type=str(data.get("type", "")),
            page_id=str(data.get("page_id", "")),
            block_id=str(data.get("block_id", "")),
            patch=dict(data.get("patch", {})) if isinstance(data.get("patch"), dict) else {},
            payload=dict(data.get("payload", {})) if isinstance(data.get("payload"), dict) else {},
            ops=nested_ops,
        )
