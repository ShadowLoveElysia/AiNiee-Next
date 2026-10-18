"""Local llama.cpp chat backend with streamed captions and owned process lifetime."""

from collections import deque
import ctypes
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from ModuleFolders.Media.local_backends import translation_prompt


class GgufTranslator:
    def __init__(self, model_path, *, family, device="cuda:0", max_new_tokens=256, on_partial=None,
                 cpu_threads=4, model_name=None, projector=None, context_size=2048):
        from ModuleFolders.Media.gguf_runtime import find_server
        from ModuleFolders.Media.model_catalog import get_model
        from ModuleFolders.Media.runtime import subprocess_environment
        checkpoint = get_model(family) if model_name is None else None
        self.name = (model_name or checkpoint.name).lower()
        self.family = checkpoint.family if checkpoint else family
        self.on_partial = on_partial
        self.max_new_tokens = max_new_tokens
        if not isinstance(cpu_threads, int) or cpu_threads < 1:
            raise ValueError("CPU threads must be positive")
        if not isinstance(context_size, int) or context_size < 2048:
            raise ValueError("Context size must be at least 2048 tokens")
        backend = {"cuda:0": "cuda", "vulkan": "vulkan", "cpu": "cpu", "metal": "metal"}.get(device)
        if backend == "cuda":
            import torch
            from ModuleFolders.Media.compute import cuda_runtime_backend, detect_adapters, selected_cuda_adapters
            backend = cuda_runtime_backend(selected_cuda_adapters(torch, detect_adapters()))
        if backend is None:
            raise ValueError("GGUF requires CUDA, Vulkan, Metal or CPU")
        server = find_server(backend)
        if server is None:
            raise RuntimeError(f"llama.cpp {backend} runtime is missing; use one-click configuration")
        if backend != "cpu":
            listing = subprocess.run([str(server), "--list-devices"], cwd=server.parent,
                                     env=subprocess_environment(), stdin=subprocess.DEVNULL,
                                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            devices = listing.stdout + listing.stderr
            marker = {"vulkan": "Vulkan", "cuda": "CUDA", "cuda-blackwell": "CUDA", "metal": "Metal"}[backend]
            if listing.returncode or not any(line.strip().startswith(marker) and ":" in line for line in devices.splitlines()):
                raise RuntimeError(f"No usable {backend} GPU; update drivers or select CPU")
        model = Path(model_path).resolve()
        if not model.is_file():
            raise FileNotFoundError(model)
        self._process = None
        self._job = None
        self._errors = deque(maxlen=8)
        self.backend = backend
        self._key = secrets.token_urlsafe(24)
        self._http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self._url = f"http://127.0.0.1:{port}"
        # b11552 defaults to an 8 GiB host prompt cache in addition to the
        # resident inference context. Short independent live requests need no
        # archive of previous request states.
        args = [str(server), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                "--api-key", self._key, "-ngl", "0" if backend == "cpu" else "99",
                "-c", str(context_size), "--parallel", "1", "--threads", str(cpu_threads), "--jinja",
                "--cache-ram", "0",
                "--chat-template-kwargs", '{"enable_thinking":false}']
        if projector is not None:
            projector = Path(projector).resolve()
            if not projector.is_file():
                raise FileNotFoundError(projector)
            args += ['--mmproj', str(projector), '--log-disable']
            if backend != 'cpu':
                args += ['--flash-attn', 'auto']
        self._process = subprocess.Popen(args, cwd=server.parent, env=subprocess_environment(),
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        try:
            if os.name == "nt":
                self._attach_kill_job()
            process = self._process
            def read_errors():
                try:
                    for line in process.stderr:
                        # Keep diagnostics in memory; never print command/API key.
                        if self._key not in line:
                            self._errors.append(line.strip())
                finally:
                    process.stderr.close()
            threading.Thread(target=read_errors, name="llama-diagnostics", daemon=True).start()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    detail = next((line for line in reversed(self._errors) if "error" in line.lower()), "")
                    raise RuntimeError(f"llama.cpp {backend} exited during loading (code {process.returncode}): {detail[:220]}")
                try:
                    with self._request("/health", timeout=2):
                        pass
                    break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(.1)
            else:
                raise RuntimeError("llama.cpp model loading timed out")
        except Exception:
            self.close()
            raise

    def _attach_kill_job(self):
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                          "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, int(self._process._handle)):
            error = ctypes.get_last_error()
            kernel.CloseHandle(job)
            raise ctypes.WinError(error)
        self._job = job

    def _request(self, path, body=None, timeout=45):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self._url + path, data=data,
                                         headers={"Authorization": "Bearer " + self._key, "Content-Type": "application/json"})
        return self._http.open(request, timeout=timeout)

    def translate(self, text, *, source_lang, target_lang, context):
        prompt = translation_prompt(text, family=self.family, source_lang=source_lang, target_lang=target_lang, context=context,
                                    glossary=getattr(self, "glossary", ()), max_characters=getattr(self, "max_characters", 0))
        return self.generate(prompt)

    def generate(self, prompt, *, max_new_tokens=None):
        token_limit = self.max_new_tokens if max_new_tokens is None else max_new_tokens
        if token_limit <= 0:
            raise ValueError("Output budget must be positive")
        body = {"messages": [{"role": "user", "content": prompt}], "temperature": 0,
                "max_tokens": token_limit, "stream": True, "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        result = ""
        self.last_metrics = {}
        started = time.perf_counter()
        with self._request("/v1/chat/completions", body) as response:
            for raw in response:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                if line[6:] == "[DONE]":
                    break
                payload = json.loads(line[6:])
                if "error" in payload:
                    raise RuntimeError("llama.cpp returned an inference error")
                if payload.get("timings"):
                    self.last_metrics.update(payload["timings"])
                for choice in payload.get("choices", []):
                    if choice.get("finish_reason") == "length":
                        raise RuntimeError("Translation reached its token limit")
                    content = choice.get("delta", {}).get("content") or ""
                    if content:
                        if "first_text_ms" not in self.last_metrics:
                            self.last_metrics["first_text_ms"] = round((time.perf_counter() - started) * 1000, 2)
                        result += content
                        if self.on_partial:
                            self.on_partial(result)
        self.last_metrics["final_ms"] = round((time.perf_counter() - started) * 1000, 2)
        if "</think>" in result:
            result = result.split("</think>", 1)[1]
        if not result.strip():
            raise RuntimeError("GGUF model returned an empty translation")
        return result.strip()

    def close(self):
        if self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=3)
            self._process = None
        if self._job is not None:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self._job)
            self._job = None

    def __del__(self):
        if hasattr(self, "_process"):
            try:
                self.close()
            except (OSError, AttributeError):
                pass
