from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import sysconfig
from pathlib import Path


DEFAULT_PACKAGE_NAMES = (
    "torch",
    "torchvision",
    "torchaudio",
    "onnxruntime",
    "onnxruntime-gpu",
)

PACKAGE_IMPORT_DIRS = {
    "torch": ("torch", "torchgen", "functorch"),
    "torchvision": ("torchvision",),
    "torchaudio": ("torchaudio",),
    "onnxruntime": ("onnxruntime",),
    "onnxruntime-gpu": ("onnxruntime",),
}


def _normalize_name(value: str) -> str:
    return value.lower().replace("_", "-")


def _dist_name_variants(package_name: str) -> set[str]:
    normalized = _normalize_name(package_name)
    return {normalized, normalized.replace("-", "_")}


def _site_packages_dirs() -> list[Path]:
    candidates = {
        sysconfig.get_paths().get("purelib", ""),
        sysconfig.get_paths().get("platlib", ""),
    }
    return [Path(path) for path in candidates if path and Path(path).is_dir()]


def _dist_info_dirs(site_packages: Path, package_name: str) -> list[Path]:
    variants = _dist_name_variants(package_name)
    matches: list[Path] = []
    for path in site_packages.glob("*.dist-info"):
        lower_name = path.name.lower()
        if any(lower_name.startswith(f"{variant}-") for variant in variants):
            matches.append(path)
    return matches


def _metadata_is_broken(dist_info_dir: Path) -> bool:
    metadata_path = dist_info_dir / "METADATA"
    if not metadata_path.is_file():
        return True
    try:
        metadata_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return False


def _remove_readonly(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    func(path)


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, onerror=_remove_readonly)
    else:
        path.unlink()


def _remove_package_files(site_packages: Path, package_name: str) -> int:
    removed = 0
    for import_name in PACKAGE_IMPORT_DIRS.get(package_name, (package_name.replace("-", "_"),)):
        package_path = site_packages / import_name
        if package_path.exists():
            print(f"[Repair] Removing package directory: {package_path}")
            _remove_path(package_path)
            removed += 1

    for dist_info_dir in _dist_info_dirs(site_packages, package_name):
        if dist_info_dir.exists():
            print(f"[Repair] Removing dist-info directory: {dist_info_dir}")
            _remove_path(dist_info_dir)
            removed += 1
    return removed


def repair_runtime_metadata(package_names: tuple[str, ...] = DEFAULT_PACKAGE_NAMES) -> int:
    repaired = 0
    site_packages_dirs = _site_packages_dirs()
    if not site_packages_dirs:
        print("[Repair] No site-packages directory found for the current Python environment.")
        return 0

    for site_packages in site_packages_dirs:
        for package_name in package_names:
            dist_info_dirs = _dist_info_dirs(site_packages, package_name)
            broken = [path for path in dist_info_dirs if _metadata_is_broken(path)]
            if not broken:
                continue

            broken_list = ", ".join(str(path) for path in broken)
            print(f"[Repair] Broken metadata detected for {package_name}: {broken_list}")
            repaired += _remove_package_files(site_packages, package_name)

    if repaired:
        print(f"[Repair] Removed {repaired} broken runtime package path(s). Reinstall can continue.")
    else:
        print("[Repair] No broken Manga runtime package metadata found.")
    return repaired


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove broken Manga runtime package metadata before uv resolves installed packages.",
    )
    parser.add_argument(
        "packages",
        nargs="*",
        default=DEFAULT_PACKAGE_NAMES,
        help="Package names to inspect. Defaults to Manga visual runtime packages.",
    )
    args = parser.parse_args(argv)

    try:
        repair_runtime_metadata(tuple(args.packages))
    except Exception as exc:
        print(f"[Repair] Failed to repair Manga runtime package metadata: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
