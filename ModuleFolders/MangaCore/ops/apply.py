from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from ModuleFolders.MangaCore.errors import OperationError
from ModuleFolders.MangaCore.ops.operation import Operation
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.project.textBlock import MangaTextBlock


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _set_nested(target: object, dotted_key: str, value: object) -> None:
    parts = dotted_key.split(".")
    current = target
    for part in parts[:-1]:
        current = getattr(current, part)
    setattr(current, parts[-1], value)


def _get_nested(target: object, dotted_key: str) -> object:
    current = target
    for part in dotted_key.split("."):
        current = getattr(current, part)
    return current


def _find_block(session: MangaProjectSession, page_id: str, block_id: str) -> MangaTextBlock:
    page = session.get_page(page_id)
    for block in page.text_blocks:
        if block.block_id == block_id:
            return block
    raise OperationError(f"Text block not found: {page_id}/{block_id}")


def _build_inverse_op(session: MangaProjectSession, op: Operation) -> Operation:
    if op.type == "Batch":
        return Operation(type="Batch", ops=[_build_inverse_op(session, child) for child in reversed(op.ops)])

    if op.type == "UpdateTextBlock":
        block = _find_block(session, op.page_id, op.block_id)
        inverse_patch = {key: deepcopy(_get_nested(block, key)) for key in op.patch}
        return Operation(type=op.type, page_id=op.page_id, block_id=op.block_id, patch=inverse_patch)

    if op.type == "UpdatePage":
        page = session.get_page(op.page_id)
        inverse_patch = {key: deepcopy(_get_nested(page, key)) for key in op.patch}
        return Operation(type=op.type, page_id=op.page_id, patch=inverse_patch)

    if op.type == "UpdateLayer":
        page = session.get_page(op.page_id)
        inverse_patch = {key: deepcopy(_get_nested(page.layers, key)) for key in op.patch}
        return Operation(type=op.type, page_id=op.page_id, patch=inverse_patch)

    if op.type == "UpdateMask":
        page = session.get_page(op.page_id)
        inverse_patch = {key: deepcopy(_get_nested(page.masks, key)) for key in op.patch}
        return Operation(type=op.type, page_id=op.page_id, patch=inverse_patch)

    if op.type == "AddTextBlock":
        return Operation(type="RemoveTextBlock", page_id=op.page_id, block_id=str(op.payload.get("block_id", "")))

    if op.type == "RemoveTextBlock":
        block = _find_block(session, op.page_id, op.block_id)
        return Operation(type="AddTextBlock", page_id=op.page_id, payload={"block": block.to_dict()})

    raise OperationError(f"Unsupported operation type: {op.type}")


def _apply_without_history(session: MangaProjectSession, op: Operation) -> int:
    if op.type == "Batch":
        return sum(_apply_without_history(session, child) for child in op.ops)

    if op.type == "UpdateTextBlock":
        block = _find_block(session, op.page_id, op.block_id)
        for key, value in op.patch.items():
            _set_nested(block, key, value)
        session.get_page(op.page_id).status = "edited"
        return 1

    if op.type == "UpdatePage":
        page = session.get_page(op.page_id)
        for key, value in op.patch.items():
            _set_nested(page, key, value)
        return 1

    if op.type == "UpdateLayer":
        page = session.get_page(op.page_id)
        for key, value in op.patch.items():
            _set_nested(page.layers, key, value)
        return 1

    if op.type == "UpdateMask":
        page = session.get_page(op.page_id)
        for key, value in op.patch.items():
            _set_nested(page.masks, key, value)
        return 1

    if op.type == "AddTextBlock":
        block_payload = op.payload.get("block")
        if not isinstance(block_payload, dict):
            raise OperationError("AddTextBlock requires payload.block")
        session.get_page(op.page_id).text_blocks.append(MangaTextBlock.from_dict(block_payload))
        return 1

    if op.type == "RemoveTextBlock":
        page = session.get_page(op.page_id)
        page.text_blocks = [block for block in page.text_blocks if block.block_id != op.block_id]
        return 1

    raise OperationError(f"Unsupported operation type: {op.type}")


def apply_operations(session: MangaProjectSession, operations: list[Operation]) -> tuple[int, int]:
    inverse_ops = [_build_inverse_op(session, op) for op in reversed(operations)]
    applied = sum(_apply_without_history(session, op) for op in operations)
    record = session.history.push(forward_ops=operations, inverse_ops=inverse_ops, timestamp=_timestamp())
    session.manifest.updated_at = record.timestamp
    return applied, record.seq


def undo_operations(session: MangaProjectSession) -> tuple[int, int] | None:
    record = session.history.pop_undo()
    if record is None:
        return None
    applied = sum(_apply_without_history(session, op) for op in record.inverse_ops)
    session.manifest.updated_at = _timestamp()
    return applied, record.seq


def redo_operations(session: MangaProjectSession) -> tuple[int, int] | None:
    record = session.history.pop_redo()
    if record is None:
        return None
    applied = sum(_apply_without_history(session, op) for op in record.forward_ops)
    session.manifest.updated_at = _timestamp()
    return applied, record.seq
