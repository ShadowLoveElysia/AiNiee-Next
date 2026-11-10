"""Pinned Windows FFmpeg builds selected for the installed NVIDIA driver."""

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time

from ModuleFolders.Media.compute import detect_nvidia_devices
from ModuleFolders.Media.package_download import checksum


@dataclass(frozen=True)
class FFmpegBuild:
    version: str
    minimum_driver: str
    nvenc_api: str
    size: int
    sha256: str

    @property
    def filename(self):
        return f"ffmpeg-{self.version}-essentials_build.zip"


# These requirements belong to the exact Gyan archives, not FFmpeg versions in general.
WINDOWS_BUILDS = (
    FFmpegBuild("9.0.2", "610.00", "13.1", 114768076,
                "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"),
    FFmpegBuild("8.0.1", "570.0", "13.0", 106259850,
                "e2aaeaa0fdbc397d4794828086424d4aaa2102cef1fb6874f6ffd29c0b88b673"),
    FFmpegBuild("7.0.2", "551.76", "12.2", 91406388,
                "d5308d30872b2739cf53169df61faba8639d39a19b20b91e611c177ef676f64c"),
    FFmpegBuild("6.1.1", "531.61", "12.1", 87520045,
                "742e32fc9f92681f9f254b925e1b613fdd8074ba40749d4879aefdb009b94cc5"),
    FFmpegBuild("5.1.2", "471.41", "11.1", 82880955,
                "ff9f2ecae5e21818400712d13657547a2353ef58a88e6e3f58c91efc49081a4a"),
)
GITHUB_RELEASES = "https://github.com/GyanD/codexffmpeg/releases/download"
GITHUB_MIRROR = "https://gh-proxy.com/"
_PREPARE_LOCK = threading.RLock()
_READY_TOOLS = {}
_DRIVER_UNSET = object()
_DRIVER_VERSION = _DRIVER_UNSET


def driver_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{3}\.\d{1,2}", value.strip()):
        return None
    major, minor = value.strip().split(".")
    return int(major), int(minor.ljust(2, "0"))


def select_windows_build(driver=None):
    version = driver_version(driver)
    if version is None:
        return WINDOWS_BUILDS[0]
    return next((build for build in WINDOWS_BUILDS if version >= driver_version(build.minimum_driver)), None)


def download_urls(build):
    upstream = f"{GITHUB_RELEASES}/{build.version}/{build.filename}"
    return GITHUB_MIRROR + upstream, upstream


def nvidia_driver_version():
    global _DRIVER_VERSION
    if _DRIVER_VERSION is _DRIVER_UNSET:
        drivers = [row.get("driver_version") for row in detect_nvidia_devices(include_driver=True)]
        drivers = [value for value in drivers if driver_version(value) is not None]
        _DRIVER_VERSION = min(drivers, key=driver_version) if drivers else None
    return _DRIVER_VERSION


def _run_ffmpeg(executable, options):
    return subprocess.run(
        [str(executable), "-hide_banner", *options],
        stdin=subprocess.DEVNULL, capture_output=True, timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )


def nvenc_probe(executable):
    """Initialize a real encoder with one synthetic frame and no output file."""
    result = _run_ffmpeg(executable, [
        "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=30",
        "-frames:v", "1", "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23",
        "-pix_fmt", "yuv420p", "-f", "null", "-",
    ])
    return result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def _tool_pair(directory):
    paths = tuple(directory / name for name in ("ffmpeg.exe", "ffprobe.exe"))
    return tuple(str(path.resolve()) for path in paths) if all(path.is_file() for path in paths) else None


def _installed_build(directory, build):
    pair = _tool_pair(directory / "bin")
    if pair is None:
        return None
    try:
        manifest = json.loads((directory / "VERIFIED.json").read_text(encoding="utf-8"))
        if manifest.get("archive_sha256") != build.sha256:
            return None
        hashes = manifest["binaries"]
        if all(checksum(Path(path)) == hashes.get(Path(path).name) for path in pair):
            return pair
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return None


def _validate_build(pair, build, driver, progress):
    version = _run_ffmpeg(pair[0], ["-version"])
    if version.returncode or not re.search(rb"ffmpeg version " + re.escape(build.version.encode()) + rb"(?:[-\s])", version.stdout):
        raise RuntimeError("Downloaded FFmpeg version does not match the selected build")
    probe = _run_ffmpeg(pair[1], ["-version"])
    if probe.returncode or not re.search(rb"ffprobe version " + re.escape(build.version.encode()) + rb"(?:[-\s])", probe.stdout):
        raise RuntimeError("Downloaded ffprobe version does not match FFmpeg")
    filters = _run_ffmpeg(pair[0], ["-filters"])
    encoders = _run_ffmpeg(pair[0], ["-encoders"])
    if filters.returncode or b" subtitles " not in filters.stdout:
        raise RuntimeError("Downloaded FFmpeg lacks the libass subtitles filter")
    if encoders.returncode or any(name not in encoders.stdout for name in (b"libx264", b"h264_nvenc")):
        raise RuntimeError("Downloaded FFmpeg lacks the required H.264 encoders")
    if driver_version(driver) is not None and driver_version(driver) >= driver_version(build.minimum_driver):
        ready, detail = nvenc_probe(pair[0])
        if not ready and "Driver does not support the required nvenc API version" in detail:
            raise RuntimeError("Downloaded FFmpeg failed the NVENC initialization test: " + detail[-1800:])
        if ready:
            progress(f"FFmpeg {build.version}: NVENC verified (driver {driver}, API {build.nvenc_api})", 1, 1)
        else:
            progress(f"FFmpeg {build.version}: NVENC unavailable; see export diagnostics", 1, 1)


@contextmanager
def _installation_lock(runtime, progress):
    """Serialize shared download parts and installation across Windows processes."""
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / ".install.lock").open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        if os.name != "nt":
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return
        import msvcrt
        deadline = time.monotonic() + 1800
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN) and getattr(error, "winerror", None) not in (33, 36):
                    raise
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for another FFmpeg installation") from None
                progress("Waiting for another FFmpeg installation", 0, 0)
                time.sleep(0.5)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _download_archive(root, build, progress):
    from requests import RequestException
    from ModuleFolders.Media.gguf_runtime import download_verified

    archive = root / "tmp/ffmpeg" / build.filename
    failures = []
    for label, url in zip(("China mirror", "official fallback"), download_urls(build), strict=True):
        progress(f"FFmpeg {build.version}: connecting ({label})", 0, build.size)
        events = queue.SimpleQueue()

        def receive_progress():
            try:
                event = json.loads(events.get(timeout=0.1))
            except queue.Empty:
                return
            progress(f"FFmpeg {build.version}: {event.get('stage', 'downloading')} ({label})",
                     event.get("downloaded_bytes", 0), event.get("total_bytes") or build.size)

        try:
            # UI callbacks must stay on the caller thread, including Tk variables.
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(download_verified, url, archive, build.size, build.sha256, emit=events.put)
                while not future.done() or not events.empty():
                    receive_progress()
                future.result()
            return archive
        except (OSError, RuntimeError, ValueError, RequestException) as exc:
            category = "NetworkError" if isinstance(exc, RequestException) else str(exc)[:180]
            failures.append(f"{label}: {category}")
            progress(f"FFmpeg {build.version}: failed ({label})", 0, build.size)
    raise RuntimeError("FFmpeg download failed (" + " | ".join(failures) + ")") from None


def _prepare_build(root, build, driver, progress, extract):
    runtime = root / "Resource/MediaRuntime/ffmpeg"
    with _installation_lock(runtime, progress):
        return _install_build(runtime, root, build, driver, progress, extract)


def _install_build(runtime, root, build, driver, progress, extract):
    directory = runtime / "builds" / ("gyan-" + build.version)
    existing = _installed_build(directory, build)
    if existing:
        return existing
    archive = _download_archive(root, build, progress)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".preparing-", dir=directory.parent) as temporary:
        staging = Path(temporary)
        extract(archive, staging / "bin")
        pair = _tool_pair(staging / "bin")
        if pair is None:
            raise RuntimeError("FFmpeg archive is missing its executable pair")
        _validate_build(pair, build, driver, progress)
        manifest = {"version": build.version, "nvenc_api": build.nvenc_api,
                    "archive_sha256": build.sha256,
                    "binaries": {Path(path).name: checksum(Path(path)) for path in pair}}
        (staging / "VERIFIED.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Publish a complete pair; the previous runtime and user-supplied tools stay intact.
        if directory.exists():
            existing = _installed_build(directory, build)
            if existing:
                return existing
            raise RuntimeError(f"Existing FFmpeg build failed verification: {directory}")
        for attempt in range(20):
            try:
                staging.rename(directory)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.25)
    return _tool_pair(directory / "bin")


def ensure_windows_ffmpeg(ffmpeg, ffprobe, *, root, progress, extract):
    """Reuse working tools, repairing only project-managed incompatible builds."""
    with _PREPARE_LOCK:
        pair = (ffmpeg, ffprobe) if ffmpeg and ffprobe else None
        runtime = root / "Resource/MediaRuntime/ffmpeg"
        if pair and not all(Path(path).resolve().is_relative_to(runtime.resolve()) for path in pair):
            return pair
        driver = nvidia_driver_version()
        key = (str(root), driver, pair)
        cached = _READY_TOOLS.get(key)
        if cached and all(Path(path).is_file() for path in cached):
            return cached
        compatible = select_windows_build(driver)
        if pair:
            if driver is None or compatible is None:
                return pair
            try:
                ready, detail = nvenc_probe(ffmpeg)
            except (OSError, subprocess.TimeoutExpired):
                ready, detail = False, ""
            if ready:
                _READY_TOOLS[key] = pair
                return pair
            # GPU/session/VRAM failures are not fixed by downloading older binaries.
            mismatch = "Driver does not support the required nvenc API version" in detail
            missing = "Unknown encoder 'h264_nvenc'" in detail
            if not mismatch and not missing:
                _READY_TOOLS[key] = pair
                return pair
            progress(f"NVIDIA {driver}: selecting compatible FFmpeg {compatible.version}", 0, 0)
        build = compatible or WINDOWS_BUILDS[0]
        selected = _prepare_build(root, build, driver, progress, extract)
        _READY_TOOLS[key] = selected
        return selected
