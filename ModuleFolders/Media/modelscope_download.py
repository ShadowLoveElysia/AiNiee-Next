"""Pinned public ModelScope downloads with resumable, verified local files."""

import hashlib
import http.client
import json
from pathlib import Path
import re
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from ModuleFolders.Infrastructure.DownloadProgress import DownloadProgress


ENDPOINT = "https://modelscope.cn"
SUFFIXES = (".safetensors", ".json", ".txt", ".yaml", ".jinja", ".model", ".pt", ".mvn")


def model_files(repo: str, revision: str, filename: str = "") -> list[dict]:
    url = f"{ENDPOINT}/api/v1/models/{quote(repo, safe='/')}/repo/files?"
    url += urlencode({"Revision": revision, "Recursive": "true"})
    with urlopen(url, timeout=30) as response:
        result = json.load(response)
    if result.get("Code") != 200 or not result.get("Success"):
        raise RuntimeError("ModelScope file listing failed")
    files = [item for item in result["Data"]["Files"]
             if item.get("Type") == "blob" and "/" not in item["Path"]
             and not item["Path"].startswith(".")
             and (item["Path"] == filename if filename else
                  item["Path"].endswith(SUFFIXES) or item["Path"].startswith("README"))]
    if not files:
        raise RuntimeError("ModelScope checkpoint files are missing")
    for item in files:
        if (Path(item["Path"]).name != item["Path"] or "\\" in item["Path"]
                or not isinstance(item.get("Size"), int) or item["Size"] < 0
                or not re.fullmatch(r"[0-9a-fA-F]{64}", item.get("Sha256", ""))):
            raise RuntimeError("Invalid ModelScope file metadata")
    return files


def verified(path: Path, size: int, digest: str) -> bool:
    if not path.is_file() or path.stat().st_size != size:
        return False
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            checksum.update(data)
    return checksum.hexdigest() == digest.lower()


def download_file(repo: str, revision: str, item: dict, target: Path, *, progress=None) -> None:
    if progress is None:
        with DownloadProgress(item['Path'], item['Size']) as tracker:
            return download_file(repo, revision, item, target, progress=tracker)
    destination = target / item["Path"]
    size, digest = item["Size"], item["Sha256"]
    if verified(destination, size, digest):
        progress.set_position(item['Path'], size)
        return
    if destination.exists():
        raise RuntimeError(f"Existing model file failed verification: {destination.name}")
    target.mkdir(parents=True, exist_ok=True)
    # Scope partial files to the content hash so revisions cannot share stale data.
    partial = destination.with_name(destination.name + f".{digest[:16]}.incomplete")
    url = f"{ENDPOINT}/api/v1/models/{quote(repo, safe='/')}/repo?"
    url += urlencode({"Revision": revision, "FilePath": item["Path"]})
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        progress.set_position(item['Path'], offset)
        if offset > size:
            raise RuntimeError("Model download exceeds expected size")
        if offset == size:
            break
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                if response.status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if (not match or int(match[1]) != offset or int(match[3]) != size
                            or int(match[2]) != size - 1):
                        raise RuntimeError("Model download range mismatch")
                elif response.status == 200:
                    # Some CDN responses ignore Range; restart rather than append.
                    offset = 0
                    progress.set_position(item['Path'], 0)
                else:
                    raise RuntimeError("Unexpected ModelScope download response")
                with partial.open("ab" if offset else "wb") as output:
                    while data := response.read(1024 * 1024):
                        if offset + len(data) > size:
                            raise RuntimeError("Model download exceeds expected size")
                        output.write(data)
                        offset += len(data)
                        progress.set_position(item['Path'], offset, transferred=len(data))
            if offset == size:
                break
        except (OSError, http.client.HTTPException):
            if attempt == 2:
                raise RuntimeError(f"ModelScope download failed: {destination.name}") from None
        if attempt < 2:
            time.sleep(1)
    progress.publish(force=True, stage='verifying')
    if not verified(partial, size, digest):
        if partial.exists() and partial.stat().st_size == size:
            partial.unlink()
        raise RuntimeError("Model checksum or size verification failed")
    partial.rename(destination)


def download_model(repo: str, revision: str, target: Path, *, filename: str = "") -> None:
    files = model_files(repo, revision, filename)
    print(json.dumps({"model": repo, "source": "modelscope", "stage": "download",
                      "bytes": sum(item["Size"] for item in files)}), flush=True)
    with DownloadProgress(repo, sum(item['Size'] for item in files)) as progress:
        for item in files:
            progress.publish(force=True, stage='download')
            download_file(repo, revision, item, target, progress=progress)
    (target / "MODEL_INFO.json").write_text(json.dumps({"repo": repo, "revision": revision,
                                                      "source": "modelscope", "status": "verified"}, indent=2), encoding="utf-8")
    print(json.dumps({"model": repo, "source": "modelscope", "status": "verified"}), flush=True)
