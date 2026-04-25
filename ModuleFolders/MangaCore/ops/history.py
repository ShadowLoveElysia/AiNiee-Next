from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.MangaCore.ops.operation import Operation


@dataclass(slots=True)
class HistoryRecord:
    seq: int
    forward_ops: list[Operation]
    inverse_ops: list[Operation]
    timestamp: str

    def to_log_lines(self) -> list[dict[str, object]]:
        lines: list[dict[str, object]] = []
        for op in self.forward_ops:
            entry = op.to_dict()
            entry["seq"] = self.seq
            entry["timestamp"] = self.timestamp
            lines.append(entry)
        return lines


@dataclass(slots=True)
class OperationHistory:
    next_seq: int = 1
    past: list[HistoryRecord] = field(default_factory=list)
    future: list[HistoryRecord] = field(default_factory=list)

    def push(self, forward_ops: list[Operation], inverse_ops: list[Operation], timestamp: str) -> HistoryRecord:
        record = HistoryRecord(seq=self.next_seq, forward_ops=forward_ops, inverse_ops=inverse_ops, timestamp=timestamp)
        self.past.append(record)
        self.future.clear()
        self.next_seq += 1
        return record

    def pop_undo(self) -> HistoryRecord | None:
        if not self.past:
            return None
        record = self.past.pop()
        self.future.append(record)
        return record

    def pop_redo(self) -> HistoryRecord | None:
        if not self.future:
            return None
        record = self.future.pop()
        self.past.append(record)
        return record
