"""Typed MCP-to-API transport helpers without application-runtime dependencies."""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit
import uuid

MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
_PARAMETER = re.compile(r"\{([^{}:]+)(?::([^{}]+))?\}")


def route_response_kind(route: dict[str, Any]) -> str:
    if "multipart/form-data" in (route.get("request_body") or {}).get("content", {}):
        return "multipart"
    if (route.get("transport_metadata") or {}).get("response_kind") == "file":
        return "file"
    for response in (route.get("responses") or {}).values():
        for media_type, content in response.get("content", {}).items():
            if media_type != "application/json" and content.get("schema", {}).get("format") == "binary":
                return "file"
    return "json"


def normalize_public_api_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("An API path is required.")
    normalized = path if path.startswith("/") else f"/{path}"
    parsed = urlsplit(normalized)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Pass only a public API path; put query parameters in query.")
    decoded = normalized
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if (
        not decoded.startswith("/api/")
        or decoded == "/api/internal" or decoded.startswith("/api/internal/")
        or "\\" in decoded
        or any(part in {".", ".."} for part in decoded.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in decoded)
    ):
        raise ValueError("Only public /api/* paths without traversal are available through MCP.")
    return normalized


def render_path_template(path_template: str, path_params: dict[str, Any] | None = None) -> str:
    params = path_params or {}
    required = [match.group(1) for match in _PARAMETER.finditer(path_template)]
    missing = [name for name in required if name not in params]
    if missing:
        raise ValueError(f"Missing path parameter(s) for {path_template}: {', '.join(missing)}")

    def replace(match):
        name, converter = match.groups()
        value = str(params[name])
        if not value or "\\" in value or (converter != "path" and "/" in value):
            raise ValueError(f"Invalid path parameter: {name}")
        if converter == "path" and value.startswith("/"):
            raise ValueError(f"Path parameter must be relative: {name}")
        return quote(value, safe="/" if converter == "path" else "")

    rendered = _PARAMETER.sub(replace, path_template)
    return normalize_public_api_path(rendered)


def match_route(routes: list[dict], method: str, path: str) -> dict | None:
    for route in routes:
        if route["method"].upper() != method.upper():
            continue
        template = route["path"]
        position = 0
        parts = []
        for match in _PARAMETER.finditer(template):
            parts.append(re.escape(template[position:match.start()]))
            parts.append(".+" if match.group(2) == "path" else "[^/]+")
            position = match.end()
        parts.append(re.escape(template[position:]))
        if re.fullmatch("".join(parts), path):
            return route
    return None


def download_api_file(api, path: str, query: dict | None, project_root: str) -> dict:
    """Stream an already-allowlisted file to a unique project-local artifact."""
    import requests

    response = requests.get(
        f"{api.base_url}{path}", params=query,
        headers={**api.headers, "Accept-Encoding": "identity"},
        timeout=api.timeout, stream=True, allow_redirects=False,
    )
    destination = None
    created = False
    try:
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"File download failed with HTTP {response.status_code}.")
        media_type = str(response.headers.get("Content-Type", "application/octet-stream")).split(";", 1)[0].lower()
        if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
            raise ValueError("Encoded file responses are not supported by this download transport.")
        if media_type == "application/json" or media_type.endswith("+json") or media_type == "text/event-stream":
            raise ValueError("The file endpoint returned a non-file response.")
        try:
            expected_size = int(response.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            expected_size = 0
        if expected_size < 0 or expected_size > MAX_DOWNLOAD_BYTES:
            raise ValueError("File download exceeds the 32 MiB limit.")
        project = Path(project_root).resolve()
        folder = (project / "tmp" / "mcp-downloads").resolve()
        if not folder.is_relative_to(project / "tmp"):
            raise ValueError("Download directory must remain inside the project tmp directory.")
        folder.mkdir(parents=True, exist_ok=True)
        suffix = Path(unquote(path)).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = mimetypes.guess_extension(media_type) or ".bin"
        destination = folder / f"{uuid.uuid4().hex}{suffix}"
        digest = hashlib.sha256()
        size = 0
        with destination.open("xb") as output:
            created = True
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("File download exceeds the 32 MiB limit.")
                output.write(chunk)
                digest.update(chunk)
        if expected_size and size != expected_size:
            raise ValueError("File download ended before the declared content length.")
        return {
            "path": str(destination), "filename": destination.name,
            "media_type": media_type, "size": size, "sha256": digest.hexdigest(),
        }
    except BaseException:
        if destination is not None and created:
            destination.unlink(missing_ok=True)
        raise
    finally:
        response.close()
