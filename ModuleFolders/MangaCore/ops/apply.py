from __future__ import annotations

import base64
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path

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


def _asset_root(session: MangaProjectSession, root_name: str) -> Path:
    if root_name == "output":
        return session.output_root
    if root_name == "project":
        return session.project_path
    raise OperationError(f"Unsupported asset snapshot root: {root_name}")


def _resolve_asset_path(session: MangaProjectSession, root_name: str, relative_path: str) -> Path:
    root = _asset_root(session, root_name).resolve()
    target = (root / relative_path).resolve()
    root_text = os.path.realpath(root)
    target_text = os.path.realpath(target)
    if target_text != root_text and not target_text.startswith(root_text + os.sep):
        raise OperationError("Asset snapshot path escapes its root.")
    return target


def _capture_page_state(session: MangaProjectSession, page_id: str) -> dict[str, object]:
    page = session.get_page(page_id)
    return {
        "status": page.status,
        "last_pipeline_stage": page.last_pipeline_stage,
    }


def _capture_asset_snapshots(session: MangaProjectSession, asset_refs: list[dict[str, object]]) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    for asset_ref in asset_refs:
        root_name = str(asset_ref.get("root", "project"))
        relative_path = str(asset_ref.get("path", ""))
        if not relative_path:
            continue
        target = _resolve_asset_path(session, root_name, relative_path)
        if target.exists():
            snapshots.append(
                {
                    "root": root_name,
                    "path": relative_path,
                    "exists": True,
                    "content_b64": base64.b64encode(target.read_bytes()).decode("ascii"),
                }
            )
        else:
            snapshots.append({"root": root_name, "path": relative_path, "exists": False, "content_b64": ""})
    return snapshots


def capture_page_assets_operation(
    session: MangaProjectSession,
    page_id: str,
    asset_refs: list[dict[str, object]],
) -> Operation:
    return Operation(
        type="RestorePageAssets",
        page_id=page_id,
        payload={
            "page_state": _capture_page_state(session, page_id),
            "assets": _capture_asset_snapshots(session, asset_refs),
        },
    )


def _restore_page_assets(session: MangaProjectSession, op: Operation) -> int:
    page_state = op.payload.get("page_state")
    if isinstance(page_state, dict):
        page = session.get_page(op.page_id)
        if "status" in page_state:
            page.status = str(page_state["status"])
        if "last_pipeline_stage" in page_state:
            page.last_pipeline_stage = str(page_state["last_pipeline_stage"])

    assets = op.payload.get("assets")
    if not isinstance(assets, list):
        return 1

    restored = 0
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        root_name = str(asset.get("root", "project"))
        relative_path = str(asset.get("path", ""))
        if not relative_path:
            continue
        target = _resolve_asset_path(session, root_name, relative_path)
        if not bool(asset.get("exists", True)):
            if target.exists():
                target.unlink()
            restored += 1
            continue
        content_b64 = str(asset.get("content_b64", ""))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(content_b64.encode("ascii")))
        restored += 1

    return max(1, restored)


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

    if op.type == "RestorePageAssets":
        assets = op.payload.get("assets")
        asset_refs = assets if isinstance(assets, list) else []
        return capture_page_assets_operation(session, op.page_id, asset_refs)

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
        page = session.get_page(op.page_id)
        page.text_blocks.append(MangaTextBlock.from_dict(block_payload))
        page.status = "edited"
        return 1

    if op.type == "RemoveTextBlock":
        page = session.get_page(op.page_id)
        page.text_blocks = [block for block in page.text_blocks if block.block_id != op.block_id]
        page.status = "edited"
        return 1

    if op.type == "RestorePageAssets":
        return _restore_page_assets(session, op)

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
