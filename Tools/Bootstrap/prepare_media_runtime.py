"""Plan and verify standalone media installers without GUI imports."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "verify", "indexes"))
    parser.add_argument("--device", choices=("auto", "cpu", "cuda:0", "vulkan", "mlx", "metal", "mps"), default="auto")
    parser.add_argument("--family", default="")
    parser.add_argument("--format", choices=("bat", "json"), default="bat")
    parser.add_argument("--source", choices=("nju", "official"), default="")
    parser.add_argument("--build", choices=("cpu", "cu126", "cu128"), default="cpu")
    args = parser.parse_args()
    from ModuleFolders.Media.package_sources import selected_source, package_indexes
    source = selected_source(args.source)
    if args.action == "indexes":
        indexes = package_indexes(args.build, source)
        if args.format == "json":
            print(json.dumps(indexes))
        else:
            print(indexes["pypi"])
            print(indexes["torch"])
        return
    from ModuleFolders.Media.model_catalog import get_model
    from ModuleFolders.Media.preferences import read_preferences
    from ModuleFolders.Media.compute import detect_adapters, select_compute
    preferences = read_preferences()
    family = args.family or preferences.get("family", "index")
    model = get_model(family)
    if args.action == "plan":
        adapters = detect_adapters()
        compute = select_compute(args.device, gguf=model.backend == "gguf",
                                 cuda_available=args.device == "cuda:0" or any(row["vendor"] == "nvidia" for row in adapters),
                                 adapters=adapters)
        from ModuleFolders.Media.runtime import cuda_install_build
        build = cuda_install_build(adapters) if compute["asr_device"] == "cuda:0" else "cpu"
        if args.format == "json":
            print(json.dumps({"family": model.key, "model": model.name, "backend": model.backend, "torch_build": build, **compute}))
            return
        print(json.dumps({"model": model.name, "device": compute["translation_device"], "torch_build": build}))
        # Both lines are fixed, validated tokens consumed by the BAT installer.
        print(build)
        print(model.key)
        return
    from ModuleFolders.Media.runtime import probe
    report = probe(sys.executable, args.device, family)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ready"]:
        print("[ERROR] Packages were installed, but inference readiness failed. See missing / compute_error above.")
        raise SystemExit(1)
    from ModuleFolders.Media.preferences import save_preferences
    save_preferences({"runtime_python": sys.executable, "package_source": source})
    print("[OK] Inference libraries and the selected backend are ready.")
    print("Model weights and audio capture still require separate checks in the controller.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
