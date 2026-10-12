"""Pinned, verified Windows and macOS runtimes for GGUF translation."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import platform
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TAG = "b11552"
RUNTIME_DIR = ROOT / "Resource/MediaRuntime/llama-cpp" / TAG
ASSETS = (
    ("llama-b11552-bin-win-cuda-12.4-x64.zip", 265234947,
     "e48331718aa82aa34571cfad8510e6d6b9a8e4dad11a73e065f94f212e280256"),
    ("cudart-llama-bin-win-cuda-12.4-x64.zip", 391443627,
     "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6"),
)
BACKEND_ASSETS = {
    "cuda": ASSETS,
    "vulkan": (("llama-b11552-bin-win-vulkan-x64.zip", 33473578,
                "83dc16325b532ba603034719e8377e28ca5093c5d4370141a6522f1a0250386c"),),
    "cpu": (("llama-b11552-bin-win-cpu-x64.zip", 19528406,
             "c00741179811ff903b515eae28bdeef1f47af6e81c49920c4e68b62954e056d6"),),
}
MAC_ASSETS = {
    "arm64": (("llama-b11552-bin-macos-arm64.tar.gz", 12086252,
               "f4b33fe40d098033fb1a19a8a4a84383c4ca84c37b6a60d9f9a253f349b48c07"),),
    "x86_64": (("llama-b11552-bin-macos-x64.tar.gz", 11615016,
                "b7977620cf5c30b8905caa45d7dbcc08766b5d4a94b3cde66ecf0323a495096f"),),
}


def runtime_assets(backend: str) -> tuple:
    if sys.platform == "darwin":
        architecture = platform.machine().lower()
        if backend not in {"metal", "cpu"} or architecture not in MAC_ASSETS:
            raise RuntimeError("macOS GGUF requires native arm64/x86_64 Python and Metal or CPU")
        return MAC_ASSETS[architecture]
    if backend not in BACKEND_ASSETS:
        raise ValueError("Unsupported llama.cpp backend")
    return BACKEND_ASSETS[backend]


def backend_directory(backend: str) -> Path:
    if sys.platform == "darwin":
        runtime_assets(backend)
        return RUNTIME_DIR / ("macos-" + platform.machine().lower()) / backend
    if backend not in BACKEND_ASSETS:
        raise ValueError("Unsupported llama.cpp backend")
    # Preserve the already-started CUDA download's install directory.
    return RUNTIME_DIR if backend == "cuda" else RUNTIME_DIR / backend


def find_server(backend="cuda") -> Path | None:
    directory = backend_directory(backend)
    if not (directory / "VERIFIED.json").is_file():
        return None
    executable = "llama-server" if sys.platform == "darwin" else "llama-server.exe"
    return next((path for path in directory.glob("**/" + executable)
                 if backend != "cuda" or "vulkan" not in path.parts and "cpu" not in path.parts), None)


def download_verified(url: str, destination: Path, size: int, digest: str, emit=print) -> None:
    import requests

    def valid(path):
        if not path.is_file() or path.stat().st_size != size:
            return False
        checksum = hashlib.sha256()
        with path.open("rb") as stream:
            for data in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                checksum.update(data)
        return checksum.hexdigest() == digest

    if valid(destination):
        return
    if destination.exists():
        raise RuntimeError(f"Existing runtime asset failed verification: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".incomplete")
    parts = destination.with_name(destination.name + ".parts")
    parts.mkdir(exist_ok=True)
    state = parts / "state.json"
    if state.exists():
        prefix = json.loads(state.read_text(encoding="utf-8"))["prefix"]
    else:
        prefix = partial.stat().st_size if partial.exists() else 0
        state.write_text(json.dumps({"prefix": prefix}), encoding="utf-8")
    if not 0 <= prefix <= size:
        raise RuntimeError("Invalid download prefix")
    step = 16 * 1024 * 1024
    ranges = [(start, min(size, start + step)) for start in range(prefix, size, step)]
    def transfer(bounds):
        start, end = bounds
        path = parts / str(start)
        with requests.Session() as session:
            for attempt in range(10):
                offset = path.stat().st_size if path.exists() else 0
                if offset == end - start:
                    emit(json.dumps({"model": destination.name, "stage": "download", "part": start}))
                    return
                if offset > end - start:
                    raise RuntimeError("Invalid download range")
                try:
                    with session.get(url, headers={"Range": f"bytes={start + offset}-{end - 1}"},
                                     stream=True, timeout=(15, 45)) as response:
                        response.raise_for_status()
                        if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start + offset}-{end - 1}/{size}":
                            raise ValueError("Range response mismatch")
                        with path.open("ab") as output:
                            for data in response.iter_content(1024 * 1024):
                                if offset + len(data) > end - start:
                                    raise ValueError("Range exceeds expected size")
                                output.write(data)
                                offset += len(data)
                except (requests.RequestException, ValueError):
                    if attempt == 9:
                        raise RuntimeError(f"Download range failed: {destination.name}") from None
                    time.sleep(2)
            if path.stat().st_size != end - start:
                raise RuntimeError("Incomplete range")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(transfer, ranges))
    with partial.open("r+b" if partial.exists() else "wb") as output:
        output.seek(prefix)
        for start, end in ranges:
            with (parts / str(start)).open("rb") as stream:
                for data in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                    output.write(data)
        output.truncate(size)
    if not valid(partial):
        raise RuntimeError(f"Checksum mismatch: {destination.name}")
    partial.rename(destination)
    for start, end in ranges:
        (parts / str(start)).unlink()
    state.unlink()
    parts.rmdir()


def prepare(emit=print, *, backend="cuda") -> Path:
    if sys.platform != "darwin" and (sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}):
        raise RuntimeError("This GGUF runtime installer requires Windows x64 or macOS")
    assets = runtime_assets(backend)
    directory = backend_directory(backend)
    existing = find_server(backend)
    if existing:
        return existing
    cache = ROOT / "tmp/llama-cpp-b11552"
    cache.mkdir(parents=True, exist_ok=True)
    def asset(job):
        name, size, checksum = job
        path = cache / name
        download_verified(f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{name}",
                          path, size, checksum, emit)
        return path
    with ThreadPoolExecutor(max_workers=2) as pool:
        archives = list(pool.map(asset, assets))
    directory.mkdir(parents=True, exist_ok=True)
    for path in archives:
        if path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                # The data filter rejects escaping links and special files.
                archive.extractall(directory, filter="data")
            continue
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                target = directory / member.filename
                if not target.resolve().is_relative_to(directory.resolve()):
                    raise RuntimeError("Unsafe runtime archive path")
            archive.extractall(directory)
    server = next(directory.rglob("llama-server" if sys.platform == "darwin" else "llama-server.exe"), None)
    if server is None:
        raise RuntimeError("Runtime archive contains no llama-server")
    if sys.platform == "darwin":
        for executable in directory.rglob("llama-*"):
            if executable.is_file() and executable.suffix == "":
                executable.chmod(executable.stat().st_mode | 0o111)
    (directory / "VERIFIED.json").write_text(json.dumps({"tag": TAG, "backend": backend, "assets": assets}, indent=2), encoding="utf-8")
    emit(json.dumps({"model": "llama.cpp " + backend, "stage": "verified"}))
    return server


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=(*BACKEND_ASSETS, "metal"), default="metal" if sys.platform == "darwin" else "cuda")
    args = parser.parse_args()
    print(str(prepare(lambda value: print(value, flush=True), backend=args.backend)), flush=True)
