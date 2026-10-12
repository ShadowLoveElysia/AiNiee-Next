"""Nonblocking, user-invoked runtime preparation for the desktop controller."""

import os
from pathlib import Path
import subprocess
import sys
import threading
import json

from ModuleFolders.Media.preferences import PROJECT_ROOT
from ModuleFolders.Media.runtime import probe, runtime_python, subprocess_environment


def stop_setup_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)


def prepare_runtime(app, action: str, *, confirmed: bool = False, model_key: str | None = None) -> None:
    from tkinter import messagebox

    if app.setup_busy or app.session.active or app.closing:
        if app.session.active:
            app.environment_status.set(app.t("stop_before_setup"))
        return
    if action in {"install", "configure", "download"} and not confirmed:
        from ModuleFolders.Media.model_catalog import get_model
        selected = get_model(model_key or app.family.get())
        download_hint = app.t("download_selected_hint", model=selected.name,
                              gb=f"{selected.download_gb + .94:.2f}", path=app.model_root.get())
        title = app.t("download_models" if action == "download" else "configure_inference" if action == "configure" else "install_runtime")
        if not messagebox.askyesno(title,
                                  app.t("configure_hint" if action == "configure" else "install_hint") if action != "download" else download_hint, parent=app.root):
            return
    app.setup_busy = True
    app.start_button.configure(state="disabled")
    for button in app.setup_buttons:
        button.configure(state="disabled")
    app.environment_status.set(app.t("checking_environment" if action == "check" else "preparing_runtime"))
    if app.managed:
        from ModuleFolders.Media.diagnostics import emit_diagnostic
        emit_diagnostic({"type": "status", "message": "checking_environment" if action == "check" else "preparing_runtime"})
    interpreter, device = app.runtime_interpreter, app.device.get()
    model_root, family = app.model_root.get(), model_key or app.family.get()
    active_family = app.family.get()
    results = app.setup_results
    # Resolve translated strings on the GUI thread; worker threads never touch Tk.
    text = {key: app.i18n.get("media_" + key) for key in ("environment_ready", "environment_missing", "setup_failed", "setup_complete", "models_missing", "download_progress")}

    def work():
        report = None
        prepared_python = None
        success = False
        try:
            if action == "check":
                report = probe(interpreter, device, family)
                detail = ", ".join(report["missing"]) if report["missing"] else (report["gpu"] or "CPU")
                if device.startswith("cuda") and not report["cuda"]:
                    detail += " · CUDA unavailable"
                if report.get("compute"):
                    detail += " · " + report["compute"]["translation_device"]
                if report.get("compute_error"):
                    detail += " · " + report["compute_error"]
                message = text["environment_ready" if report["ready"] else "environment_missing"].format(detail=detail)
                from ModuleFolders.Media.live_session import LiveConfig
                try:
                    LiveConfig(model_root, family=family).validate()
                except ValueError:
                    message += " · " + text["models_missing"]
            else:
                args = [sys.executable if action in {"install", "configure"} else interpreter,
                        "-m", "ModuleFolders.Media.runtime", action, "--managed"]
                if action in {"install", "configure"}:
                    args += ["--device", device, "--family", family]
                else:
                    args += ["--model-root", model_root, "--family", family]
                environment = subprocess_environment()
                environment.pop("HF_HUB_OFFLINE", None)
                environment.pop("TRANSFORMERS_OFFLINE", None)
                if app.closed or app.closing:
                    return
                app.setup_process = subprocess.Popen(args, cwd=PROJECT_ROOT, env=environment,
                                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                     text=True, encoding="utf-8", errors="replace",
                                                     stdin=subprocess.PIPE,
                                                     start_new_session=os.name != "nt")
                try:
                    prepared_python = None
                    for line in app.setup_process.stdout:
                        try:
                            progress = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(progress.get("runtime_python"), str):
                            prepared_python = progress["runtime_python"]
                        if "model" in progress:
                            results.put({"type": "progress", "message":
                                text["download_progress"].format(model=progress["model"], stage=progress.get("stage", progress.get("status", "")))})
                    code = app.setup_process.wait()
                finally:
                    app.setup_process.stdin.close()
                    app.setup_process.stdout.close()
                if code:
                    raise RuntimeError(str(code))
                checked_python = (prepared_python or str(runtime_python())) if action in {"install", "configure"} else interpreter
                if not app.closed:
                    if action == "download":
                        try:
                            report = probe(checked_python, device, active_family)
                        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
                            report = None
                    else:
                        report = probe(checked_python, device, family)
                    if report is not None and not report["ready"] and action != "download":
                        raise RuntimeError("RuntimeNotReady")
                message = text["setup_complete"]
            success = True
        except Exception as exc:
            message = text["setup_failed"].format(detail=type(exc).__name__)
        results.put({"type": "finished", "message": message, "report": report, "action": action,
                     "success": success, "runtime_python": prepared_python if action in {"install", "configure"} else None,
                     "runtime_signature": ((prepared_python or str(runtime_python())) if action in {"install", "configure"} else interpreter,
                                           device, active_family if action == "download" else family, model_root)})

    threading.Thread(target=work, name="media-setup", daemon=True).start()
