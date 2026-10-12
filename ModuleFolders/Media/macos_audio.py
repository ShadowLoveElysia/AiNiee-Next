"""Owned native capture helper with a bounded, in-memory PCM transport."""

from collections import deque
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("native") / "SystemAudio.swift"
SYSTEM_AUDIO = "__ainiee_macos_system_audio__"
SCREEN_AUDIO = "__ainiee_macos_screen_audio__"
HELPER_ROOT = ROOT / "Resource/MediaRuntime/native-audio"


def supported() -> bool:
    try:
        return sys.platform == "darwin" and tuple(map(int, platform.mac_ver()[0].split('.')[:2])) >= (13, 0)
    except ValueError:
        return False


def helper_directory() -> Path:
    return HELPER_ROOT / platform.machine().lower() / "AiNiee Audio Capture.app"


def helper_executable() -> Path:
    return helper_directory() / "Contents/MacOS/AiNieeAudioCapture"


def build_signature() -> str:
    return hashlib.sha256(SOURCE.read_bytes() + b"native-audio-v1-plist").hexdigest()


def helper_ready() -> bool:
    executable = helper_executable()
    try:
        return executable.is_file() and os.access(executable, os.X_OK) and (
            helper_directory() / "Contents/source.sha256").read_text().strip() == build_signature()
    except OSError:
        return False


def prepare_helper(emit=lambda _: None) -> Path:
    if not supported():
        raise RuntimeError("Native system audio requires macOS 13 or newer")
    if helper_ready():
        return helper_executable()
    xcrun = shutil.which("xcrun")
    if not xcrun:
        raise RuntimeError("Install Xcode Command Line Tools with xcode-select --install, then configure inference again")
    compiler = subprocess.run([xcrun, "--find", "swiftc"], capture_output=True, timeout=20)
    if compiler.returncode:
        raise RuntimeError("Install Xcode Command Line Tools with xcode-select --install, then configure inference again")
    architecture = platform.machine().lower()
    if architecture not in {"arm64", "x86_64"}:
        raise RuntimeError("Unsupported macOS capture architecture")
    contents = helper_directory() / "Contents"
    executable = helper_executable()
    executable.parent.mkdir(parents=True, exist_ok=True)
    plist = {"CFBundleIdentifier": "ai.ainiee.system-audio", "CFBundleName": "AiNiee Audio Capture",
             "CFBundleExecutable": executable.name, "CFBundlePackageType": "APPL",
             "CFBundleVersion": "1", "CFBundleShortVersionString": "1.0", "LSUIElement": True,
             "LSMinimumSystemVersion": "13.0",
             "NSAudioCaptureUsageDescription": "Capture system playback for live translation. Audio is processed locally.",
             "NSScreenCaptureUsageDescription": "Capture system playback for live translation on older macOS versions."}
    (contents / "Info.plist").write_bytes(plistlib.dumps(plist))
    emit(json.dumps({"model": "macOS system audio", "stage": "compile"}))
    result = subprocess.run([xcrun, "swiftc", "-swift-version", "5", "-O", "-target", architecture + "-apple-macosx13.0",
                             str(SOURCE), "-o", str(executable), "-framework", "AppKit", "-framework", "CoreAudio",
                             "-framework", "AVFoundation", "-framework", "ScreenCaptureKit", "-framework", "CoreMedia"],
                            cwd=ROOT, capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Compiler diagnostics describe project source; do not include audio or environment.
        detail = '\n'.join(result.stderr.splitlines()[-12:])
        raise RuntimeError("macOS capture build failed; use Xcode 15.3+ Command Line Tools: " + detail)
    codesign = shutil.which('codesign') or '/usr/bin/codesign'
    (contents / "source.sha256").write_text(build_signature(), encoding="ascii")
    try:
        executable_result = subprocess.run([codesign, '--force', '--sign', '-', '--timestamp=none',
                                            '--identifier', 'ai.ainiee.system-audio', str(executable)],
                                           check=True, capture_output=True, text=True, timeout=30)
        subprocess.run([codesign, '--force', '--sign', '-', '--timestamp=none',
                        '--identifier', 'ai.ainiee.system-audio', str(helper_directory())],
                       check=True, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        (contents / "source.sha256").unlink(missing_ok=True)
        detail = getattr(error, 'stderr', '') or str(error)
        detail = ' '.join(str(detail).split())[:800]
        raise RuntimeError("macOS audio helper signing failed (" + detail + "). Verify xcrun --find codesign and Xcode Command Line Tools") from None
    emit(json.dumps({"model": "macOS system audio", "stage": "ready"}))
    return executable


class NativeSystemAudio:
    channels = 1
    name = "macOS system audio"

    def __init__(self, *, screen=False):
        self.screen = screen

    def recorder(self, *, samplerate, channels):
        if samplerate != 16000 or channels != 1:
            raise ValueError("Native capture produces 16 kHz mono PCM")
        return NativeRecorder(screen=self.screen)


class NativeRecorder:
    def __init__(self, *, screen=False):
        self.screen = screen
        self.process = None
        self.blocks = queue.Queue(maxsize=64)
        self.errors = deque(maxlen=4)
        self.failure = None
        self.closed = threading.Event()
        self.pending = bytearray()

    def __enter__(self):
        from ModuleFolders.Media.runtime import subprocess_environment
        executable = prepare_helper()
        self.process = subprocess.Popen([str(executable), "screen" if self.screen else "auto"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        cwd=ROOT, env=subprocess_environment(), bufsize=0)
        process = self.process
        header = queue.Queue(maxsize=1)

        def diagnostics():
            try:
                for line in process.stderr:
                    try:
                        payload = json.loads(line)
                        if isinstance(payload, dict):
                            self.errors.append(f"{payload.get('stage', 'capture')}: {payload.get('status', 0)}")
                    except ValueError:
                        continue
            finally:
                process.stderr.close()

        def receive():
            try:
                line = bytearray()
                while len(line) <= 4096:
                    value = process.stdout.read(1)
                    if not value:
                        raise RuntimeError("Native capture stopped before initialization")
                    if value == b'\n':
                        break
                    line.extend(value)
                else:
                    raise RuntimeError("Invalid native capture header")
                report = json.loads(line)
                if report.get("sample_rate") != 16000 or report.get("channels") != 1 or report.get("format") != "f32le":
                    raise RuntimeError("Invalid native capture format")
                header.put(report)
                while True:
                    block = process.stdout.read(4096)
                    if not block:
                        break
                    if self.closed.is_set():
                        continue
                    try:
                        self.blocks.put_nowait(block)
                    except queue.Full:
                        raise RuntimeError("Native system audio queue overflow; restart capture")
            except Exception as exc:
                self.failure = exc
            finally:
                process.stdout.close()
                self.closed.set()
                if header.empty():
                    try:
                        header.put_nowait(None)
                    except queue.Full:
                        pass

        threading.Thread(target=diagnostics, name="macos-audio-errors", daemon=True).start()
        threading.Thread(target=receive, name="macos-audio-pcm", daemon=True).start()
        try:
            try:
                report = header.get(timeout=90)
            except queue.Empty:
                raise RuntimeError("macOS system audio initialization timed out. Respond to the recording permission prompt and restart capture.") from None
            if not report:
                raise RuntimeError(self.error_message())
            self.backend = report.get("backend", "native")
            return self
        except BaseException:
            self.close()
            raise

    def error_message(self):
        detail = '; '.join(self.errors) or str(self.failure or "No PCM received")
        return ("macOS system audio capture failed (" + detail + "). Allow AiNiee Audio Capture / Terminal "
                "in System Settings > Privacy & Security > Screen & System Audio Recording, then restart. "
                "You can explicitly select ScreenCaptureKit or a microphone; no automatic microphone fallback.")

    def record(self, *, numframes):
        pcm = self.read_pcm(numframes)
        import numpy as np
        return np.frombuffer(pcm, dtype='<f4').copy().reshape(numframes, 1)

    def read_pcm(self, numframes):
        required = numframes * 4
        if numframes <= 0:
            raise ValueError("Frame count must be positive")
        while len(self.pending) < required:
            if self.failure:
                raise RuntimeError(self.error_message())
            if self.closed.is_set() and self.blocks.empty():
                raise RuntimeError(self.error_message())
            try:
                self.pending.extend(self.blocks.get(timeout=max(.032, numframes / 16000)))
            except queue.Empty:
                if self.closed.is_set() or self.process is None or self.process.poll() is not None:
                    raise RuntimeError(self.error_message()) from None
                # ScreenCaptureKit may deliver no buffers during silent playback.
                # Pad whole samples only; retain partial bytes from pipe fragmentation.
                whole = len(self.pending) // 4 * 4
                samples = bytes(self.pending[:whole]) + bytes(required - whole)
                del self.pending[:whole]
                return samples
            if self.closed.is_set() and self.blocks.empty() and len(self.pending) < required:
                raise RuntimeError(self.error_message())
        samples = bytes(self.pending[:required])
        del self.pending[:required]
        return samples

    def close(self):
        self.closed.set()
        if self.process is not None:
            if not self.process.stdin.closed:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process = None

    def __exit__(self, *args):
        self.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build or test native macOS system audio without loading translation models")
    parser.add_argument("--check", action="store_true", help="Build and verify the native helper without requesting capture")
    parser.add_argument("--screen", action="store_true", help="Explicitly use ScreenCaptureKit")
    parser.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error("--seconds must be between 1 and 120")
    if args.check:
        prepare_helper(print)
        print(json.dumps({"helper_ready": helper_ready()}))
        return
    import struct
    total = 0
    peak = 0.0
    with NativeRecorder(screen=args.screen) as recorder:
        started = time.monotonic()
        while time.monotonic() - started < args.seconds:
            pcm = recorder.read_pcm(512)
            peak = max(peak, max(map(abs, struct.unpack('<512f', pcm))))
            total += 512
        print(json.dumps({"backend": recorder.backend, "samples": total, "peak": round(peak, 6),
                          "elapsed_seconds": round(time.monotonic() - started, 2)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
