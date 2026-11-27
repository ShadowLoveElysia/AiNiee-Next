"""Noninteractive maintenance backed by the same updater and Manga plans as TUI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote, urlsplit

from ModuleFolders.Infrastructure.MangaRuntimeInstaller import MangaRuntimeInstaller
from ModuleFolders.Infrastructure.Update.UpdateManager import UpdateManager
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    config_revision, config_transaction, load_effective_config, patch_effective_config,
)
from ModuleFolders.UserInterface.AppI18N import I18NLoader
from .jobs import CancelledJob, CommittedResult
from .manager import resolve_task_worker_python
from .processes import OwnedProcessTree, launch_options, mark_worker_environment

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def updater():
    instance = UpdateManager(I18NLoader(str(PROJECT_ROOT), "en"))
    instance.project_root = str(PROJECT_ROOT)
    return instance


def update_info():
    instance = updater()
    commit, stable, preview = instance.fetch_update_info()
    return {"local_version": instance.get_local_version_full(), "commit": commit,
            "stable": stable, "preview": preview}


def _check_cancel(cancel):
    if cancel.is_set():
        raise CancelledJob()


def _run_owned(command, cancel, *, env=None, cwd=None):
    _check_cancel(cancel)
    environment = dict(env or os.environ)
    marker = mark_worker_environment(environment, nested=True)
    started = time.time()
    process = subprocess.Popen(command, cwd=cwd or PROJECT_ROOT, env=environment,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               **launch_options())
    tree = OwnedProcessTree(process, owner_id=marker, launched_at=started)
    try:
        while process.poll() is None:
            if cancel.wait(.1):
                break
    finally:
        # Keep job ownership until all descendants are confirmed gone.
        while not tree.terminate(timeout=2):
            time.sleep(.1)
    _check_cancel(cancel)
    if process.returncode:
        raise RuntimeError("Maintenance command failed")


def _download(instance, url, destination, cancel):
    import requests
    from ModuleFolders.Infrastructure.DownloadProgress import stream_response

    parsed = urlsplit(url)
    if parsed.hostname != "github.com" or not parsed.path.startswith(f"/{instance.GITHUB_REPO}/"):
        raise ValueError("Only the project's GitHub release packages are supported")
    for proxy in instance.GITHUB_PROXIES:
        _check_cancel(cancel)
        try:
            with requests.get(f"{proxy}{url}", stream=True, timeout=(10, 30)) as response:
                response.raise_for_status()
                original = response.iter_content

                def chunks(*args, **kwargs):
                    received = 0
                    for chunk in original(*args, **kwargs):
                        _check_cancel(cancel)
                        received += len(chunk)
                        if received > 512 * 1024 ** 2:
                            raise ValueError("Update download exceeds 512 MiB")
                        yield chunk

                response.iter_content = chunks
                stream_response(response, destination, "Update package", quiet=True)
            return
        except CancelledJob:
            raise
        except (requests.RequestException, OSError, RuntimeError, ValueError):
            destination.unlink(missing_ok=True)
    raise RuntimeError("Update package could not be downloaded")


def _update_url(instance, target, channel):
    if target == "web":
        if channel == "stable":
            return instance.DOWNLOAD_WEB_STABLE_URL
        if channel == "preview":
            releases, _ = instance._fetch_releases_safe(timeout=10)
            _, asset = instance._select_web_preview_asset(releases)
            if asset:
                return str(asset.get("browser_download_url", ""))
        raise ValueError("Web updates support stable, preview, local or build")
    if channel == "main":
        return instance.DOWNLOAD_MAIN_URL
    _, stable, preview = instance.fetch_update_info()
    release = stable if channel == "stable" else preview
    if not release or not release.get("tag"):
        raise ValueError("Requested release is unavailable")
    return instance.DOWNLOAD_TAG_URL.format(tag=quote(str(release["tag"]), safe=""))


def apply_update(request, cancel):
    instance = updater()
    _check_cancel(cancel)
    if request.channel == "build":
        if request.target != "web":
            raise ValueError("Only the Web frontend supports local build")
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("npm is unavailable")
        web = PROJECT_ROOT / "Tools/WebServer"
        for args in (("install",), ("run", "build")):
            _run_owned([npm, *args], cancel, cwd=web)
        return CommittedResult({"success": True, "target": "web", "restart_required": False})
    work_root = PROJECT_ROOT / "tmp" / "maintenance"
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="update-", dir=work_root) as folder:
        archive = Path(folder) / "package.zip"
        if request.channel == "local":
            name = request.archive_name or ""
            if not name or Path(name).name != name or "\\" in name or not name.lower().endswith(".zip"):
                raise ValueError("Supply a ZIP filename from the project's Update directory")
            origin = PROJECT_ROOT / "Update" / name
            if origin.is_symlink() or not origin.is_file():
                raise ValueError("Local update archive does not exist")
            shutil.copyfile(origin, archive)
        else:
            _download(instance, _update_url(instance, request.target, request.channel), archive, cancel)
        _check_cancel(cancel)
        if request.target == "application":
            instance._apply_update_from_zip(str(archive), restart=False, strict=True)
        else:
            instance._apply_web_dist(str(archive), strict=True)
    return CommittedResult({"success": True, "target": request.target,
                            "restart_required": request.target == "application"})


def manga_runtime(*, probe=False):
    interpreter = resolve_task_worker_python(str(PROJECT_ROOT))
    installer = MangaRuntimeInstaller(PROJECT_ROOT, interpreter)
    code = """import importlib.metadata as metadata,json
packages={}
for name in ('torch','torchvision','onnxruntime','onnxruntime-gpu','torchaudio'):
 try: packages[name]=metadata.version(name)
 except metadata.PackageNotFoundError: packages[name]='missing'
result={'packages':packages,'cuda_available':None,'onnxruntime_providers':[],'probe_errors':{}}
if __import__('sys').argv[1]=='probe':
 try:
  import torch
  result['cuda_available']=torch.cuda.is_available()
 except Exception as error: result['probe_errors']['torch']=type(error).__name__
 try:
  import onnxruntime
  result['onnxruntime_providers']=onnxruntime.get_available_providers()
 except Exception as error: result['probe_errors']['onnxruntime']=type(error).__name__
print(json.dumps(result))
"""
    result = subprocess.run([interpreter, "-c", code, "probe" if probe else "packages"], capture_output=True, text=True, timeout=30, check=True)
    details = json.loads(result.stdout)
    config = load_effective_config(create_missing=False)
    from ModuleFolders.MangaCore.pipeline.modelStore import MANGA_ENGINE_STAGE_CONFIG_KEYS
    keys = (*installer.DEVICE_CONFIG_KEYS, *MANGA_ENGINE_STAGE_CONFIG_KEYS.values())
    return {"interpreter": interpreter, "platform": installer._platform_summary(),
            "backends": installer._installable_backends(), "devices": installer._config_devices(),
            "packages": details["packages"], "configured": {key: config.get(key) for key in keys},
            "recommended_backend": installer._recommended_backend()["key"],
            "probe_performed": probe, "cuda_available": details["cuda_available"],
            "onnxruntime_providers": details["onnxruntime_providers"], "probe_errors": details["probe_errors"]}


def install_manga_runtime(backend, cancel):
    interpreter = resolve_task_worker_python(str(PROJECT_ROOT))
    installer = MangaRuntimeInstaller(PROJECT_ROOT, interpreter)
    if installer._backend_by_key(backend) is None:
        raise ValueError("Runtime backend is unavailable on this platform")
    uv = installer._uv_executable()
    if not uv:
        raise RuntimeError("uv is unavailable")
    repair = PROJECT_ROOT / "ModuleFolders/MangaCore/runtime/repair_runtime_metadata.py"
    if repair.is_file():
        _run_owned([interpreter, str(repair)], cancel, env=installer._uv_env())
    _run_owned([uv, "pip", "uninstall", "--python", interpreter, *installer.CONFLICT_PACKAGE_NAMES],
               cancel, env=installer._uv_env())
    for plan in installer._backend_install_plans(backend):
        args = ["install", "--python", interpreter, *plan["install_args"]]
        try:
            environment = installer._uv_env()
            environment["UV_LINK_MODE"] = "copy"
            _run_owned([uv, "pip", *args], cancel, env=environment)
        except RuntimeError as exc:
            if isinstance(exc, CancelledJob):
                raise
            continue
        _check_cancel(cancel)
        patch_effective_config({key: backend for key in installer.DEVICE_CONFIG_KEYS})
        return CommittedResult({"success": True, "backend": backend, "restart_required": True})
    raise RuntimeError("Manga runtime installation failed")


@config_transaction()
def set_manga_defaults(request):
    installer = MangaRuntimeInstaller(PROJECT_ROOT)
    changes = {}
    if request.preset_id:
        from ModuleFolders.MangaCore.pipeline.modelCatalog import get_model_preset
        from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore
        preset = get_model_preset(request.preset_id)
        store = MangaModelStore()
        if not all(store.get_status(model_id).get("available") for model_id in preset.model_ids):
            raise ValueError("Download all preset model packages before selecting it")
        changes.update(preset.config_overrides)
    if request.device is not None:
        if request.device not in installer._config_devices():
            raise ValueError("Device is unavailable on this platform")
        changes.update({key: request.device for key in installer.DEVICE_CONFIG_KEYS})
    if request.engines:
        from ModuleFolders.MangaCore.pipeline.modelStore import MANGA_ENGINE_STAGE_CONFIG_KEYS, MangaModelStore
        options = MangaModelStore().build_manager_manifest()["engine_options"]
        for stage, model_id in request.engines.items():
            if stage not in MANGA_ENGINE_STAGE_CONFIG_KEYS or not any(
                row.get("model_id") == model_id and row.get("selectable") for row in options.get(stage, [])
            ):
                raise ValueError("Engine must be downloaded and selectable for its stage")
            changes[MANGA_ENGINE_STAGE_CONFIG_KEYS[stage]] = model_id
    current = patch_effective_config(changes, expected_revision=request.expected_revision)
    return {"success": True, "revision": config_revision(current), "restart_required": False}
