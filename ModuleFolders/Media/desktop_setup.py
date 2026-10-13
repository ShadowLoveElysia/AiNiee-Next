"""Nonblocking, user-invoked runtime preparation for the desktop controller."""

import os
from pathlib import Path
import subprocess
import sys
import threading
import json

from ModuleFolders.Media.preferences import PROJECT_ROOT
from ModuleFolders.Media.runtime import cached_probe as probe, clear_probe_cache, runtime_python, subprocess_environment


def stop_setup_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)


def prepare_runtime(app, action: str, *, confirmed: bool = False, model_key: str | None = None,
                    asr_key: str | None = None, download_scope: str = 'all') -> None:
    from tkinter import messagebox

    if app.setup_busy or app.session.active or app.closing:
        if app.session.active:
            app.environment_status.set(app.t("stop_before_setup"))
        return
    if action in {"install", "configure", "download"} and not confirmed:
        from ModuleFolders.Media.model_catalog import get_model
        from ModuleFolders.Media.asr_catalog import get_recognizer
        recognition = get_recognizer(asr_key or (app.recognizer.get() if hasattr(app, 'recognizer') else 'sensevoice'))
        selected = get_model(model_key or app.family.get())
        names = ([recognition.name] if download_scope == 'asr' else [selected.name] if download_scope == 'llm' else
                 [recognition.name, selected.name])
        size = recognition.download_gb if download_scope == 'asr' else selected.download_gb if download_scope == 'llm' else selected.download_gb + recognition.download_gb
        download_hint = app.t('download_models_named_hint', model=' + '.join(names), gb=f'{size:.2f}', path=app.model_root.get())
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
    recognizer = app.recognizer.get() if hasattr(app, 'recognizer') else 'sensevoice'
    asr_device = app.recognition_device.get() if hasattr(app, 'recognition_device') else 'auto'
    endpoint = app.asr_endpoint.get() if hasattr(app, 'asr_endpoint') else 'http://127.0.0.1:8001/v1'
    recognition_kwargs = {'recognizer': recognizer, 'asr_device': asr_device} if recognizer != 'sensevoice' or asr_device != 'auto' else {}
    if endpoint != 'http://127.0.0.1:8001/v1':
        recognition_kwargs['asr_endpoint'] = endpoint
    from ModuleFolders.Media.package_sources import selected_source
    source_variable = getattr(app, "package_source", None)
    package_source = selected_source(source_variable.get() if source_variable else "")
    results = app.setup_results
    # Resolve translated strings on the GUI thread; worker threads never touch Tk.
    text = {key: app.i18n.get("media_" + key) for key in ("environment_ready", "environment_missing", "setup_failed", "setup_complete", "models_missing", "download_progress")}

    def work():
        report = None
        prepared_python = None
        success = False
        setup_error = ""
        try:
            if action == "check":
                report = probe(interpreter, device, family, **recognition_kwargs)
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
                    LiveConfig(model_root, family=family, recognizer=recognizer).validate()
                except ValueError:
                    message += " · " + text["models_missing"]
            else:
                clear_probe_cache()
                args = [sys.executable if action in {"install", "configure"} else interpreter,
                        "-m", "ModuleFolders.Media.runtime", action, "--managed"]
                args += ['--recognizer', asr_key or recognizer, '--asr-device', asr_device]
                args += ['--asr-endpoint', endpoint]
                if action in {"install", "configure"}:
                    args += ["--device", device, "--family", family]
                else:
                    args += ["--model-root", model_root, "--family", family, '--download-scope', download_scope]
                environment = subprocess_environment()
                environment["AINIEE_MEDIA_PACKAGE_SOURCE"] = package_source
                environment['AINIEE_DOWNLOAD_JSON'] = '1'
                environment['UV_NO_PROGRESS'] = 'false'
                environment.pop("HF_HUB_OFFLINE", None)
                environment.pop("TRANSFORMERS_OFFLINE", None)
                if app.closed or app.closing:
                    return
                app.setup_process = subprocess.Popen(args, cwd=PROJECT_ROOT, env=environment,
                                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                     text=True, encoding="utf-8", errors="replace",
                                                     stdin=subprocess.PIPE,
                                                     start_new_session=os.name != "nt")
                try:
                    prepared_python = None
                    setup_error = ""
                    for line in app.setup_process.stdout:
                        try:
                            progress = json.loads(line)
                        except ValueError:
                            from ModuleFolders.Infrastructure.DownloadProgress import safe_installer_line
                            line = safe_installer_line(line)
                            if line:
                                results.put({'type': 'progress', 'message': line})
                            continue
                        if not isinstance(progress, dict):
                            continue
                        if isinstance(progress.get("runtime_python"), str):
                            prepared_python = progress["runtime_python"]
                        if isinstance(progress.get("error_detail"), str):
                            setup_error = progress["error_detail"][:1600]
                        if "model" in progress:
                            from ModuleFolders.Infrastructure.DownloadProgress import format_progress
                            message = format_progress(progress) if progress.get('type') == 'download' else text['download_progress'].format(
                                model=progress['model'], stage=progress.get('stage', progress.get('status', '')))
                            results.put({'type': 'progress', 'message': message,
                                         'download': progress if progress.get('type') == 'download' else None})
                    code = app.setup_process.wait()
                finally:
                    app.setup_process.stdin.close()
                    app.setup_process.stdout.close()
                if code:
                    raise RuntimeError(setup_error or str(code))
                checked_python = (prepared_python or str(runtime_python())) if action in {"install", "configure"} else interpreter
                if not app.closed:
                    if action == "download":
                        try:
                            report = probe(checked_python, device, active_family, **recognition_kwargs)
                        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired):
                            report = None
                    else:
                        report = probe(checked_python, device, family, **recognition_kwargs)
                    if report is not None and not report["ready"] and action != "download":
                        raise RuntimeError("RuntimeNotReady")
                message = text["setup_complete"]
            success = True
        except Exception as exc:
            from ModuleFolders.Media.runtime import RuntimeProbeError
            detail = str(exc) if isinstance(exc, RuntimeProbeError) else type(exc).__name__
            message = text["setup_failed"].format(detail=setup_error or detail)
        results.put({"type": "finished", "message": message, "report": report, "action": action,
                     "success": success, "runtime_python": prepared_python if action in {"install", "configure"} else None,
                     "runtime_signature": ((prepared_python or str(runtime_python())) if action in {"install", "configure"} else interpreter,
                                           device, active_family if action == "download" else family, model_root) +
                                          ((recognizer, asr_device) if hasattr(app, 'recognizer') else ()) +
                                          ((endpoint,) if hasattr(app, 'asr_endpoint') else ())})

    threading.Thread(target=work, name="media-setup", daemon=True).start()
