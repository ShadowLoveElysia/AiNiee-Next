"""Read-only filesystem metadata for authenticated browser path selection."""
from __future__ import annotations

import os
import string
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from Tools.APIServer.responses import ERROR_RESPONSES

router = APIRouter(prefix="/api/files", tags=["files"])
MAX_DIRECTORY_ENTRIES = 5000


class PathLocation(BaseModel):
    name: str
    path: str


class BrowserEntry(BaseModel):
    name: str
    path: str
    kind: Literal["file", "directory"]


class DirectoryListing(BaseModel):
    path: str
    parent: str | None
    selected_path: str | None = None
    entries: list[BrowserEntry]
    locations: list[PathLocation]
    next_offset: int | None
    truncated: bool


def _locations(project_root: Path) -> list[dict[str, str]]:
    candidates = [("项目目录", project_root), ("用户目录", Path.home())]
    if os.name == "nt":
        candidates.extend((f"{letter}:\\", Path(f"{letter}:\\")) for letter in string.ascii_uppercase)
    else:
        candidates.append(("文件系统", Path("/")))
        candidates.extend((f"{letter.upper()}:\\", Path("/mnt") / letter) for letter in string.ascii_lowercase)
    result = []
    seen = set()
    for name, path in candidates:
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_dir() or str(resolved) in seen:
                continue
        except (OSError, RuntimeError):
            continue
        seen.add(str(resolved))
        result.append({"name": name, "path": str(resolved)})
    return result


def list_directory(path: str, *, project_root: Path, directories_only: bool = False,
                   show_hidden: bool = False, offset: int = 0, limit: int = 200) -> dict:
    """Paths follow the API host's filesystem; never infer browser-local paths."""
    if "\x00" in path:
        raise ValueError("路径包含无效字符")
    if os.name == "nt" and path.replace("/", "\\").startswith("\\\\"):
        raise ValueError("此选择器不浏览网络共享或设备路径")
    candidate = Path(path).expanduser() if path.strip() else project_root
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve(strict=True)
    selected = str(resolved) if resolved.is_file() and not directories_only else None
    directory = resolved.parent if resolved.is_file() else resolved
    if not directory.is_dir():
        raise ValueError("请选择普通文件或文件夹")
    entries = []
    truncated = False
    # Bound both filesystem work and response size, including huge/hidden directories.
    with os.scandir(directory) as items:
        for index, item in enumerate(items):
            if index >= MAX_DIRECTORY_ENTRIES:
                truncated = True
                break
            if not show_hidden and item.name.startswith("."):
                continue
            try:
                if item.is_symlink() or getattr(os.path, "isjunction", lambda _path: False)(item.path):
                    continue
                if item.is_dir():
                    kind = "directory"
                elif not directories_only and item.is_file():
                    kind = "file"
                else:
                    continue
                actual = Path(item.path).resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            entries.append({"name": item.name, "path": str(actual), "kind": kind})
    entries.sort(key=lambda item: (item["kind"] != "directory", item["name"].casefold(), item["name"]))
    next_offset = offset + limit if offset + limit < len(entries) else None
    return {
        "path": str(directory), "parent": str(directory.parent) if directory.parent != directory else None,
        "selected_path": selected, "entries": entries[offset:offset + limit],
        "locations": _locations(project_root), "next_offset": next_offset, "truncated": truncated,
    }


@router.get("/browse", response_model=DirectoryListing, responses=ERROR_RESPONSES,
            openapi_extra={"x-allowed-channels": ["web"]})
def browse_files(request: Request, response: Response, path: str = Query("", max_length=4096),
                 directories_only: bool = False, show_hidden: bool = False,
                 offset: int = Query(0, ge=0, le=MAX_DIRECTORY_ENTRIES),
                 limit: int = Query(200, ge=1, le=500)):
    from ModuleFolders.Infrastructure.ApiSecurity import is_mcp_request
    from Tools.APIServer import application
    if is_mcp_request(request) or not application._has_valid_web_session(request):
        raise HTTPException(403, "路径选择仅供已登录的 Web 界面使用")
    response.headers["Cache-Control"] = "no-store"
    try:
        return list_directory(path, project_root=Path(application.PROJECT_ROOT), directories_only=directories_only,
                              show_hidden=show_hidden, offset=offset, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(404, "路径不存在，请选择其他位置或输入有效路径") from exc
    except PermissionError as exc:
        raise HTTPException(403, "无法访问此目录，请选择有读取权限的位置") from exc
    except NotADirectoryError as exc:
        raise HTTPException(422, "此路径不是文件夹") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, "路径无效，请检查后重试") from exc
    except OSError as exc:
        raise HTTPException(503, "读取目录失败，请确认磁盘或网络位置可用") from exc
