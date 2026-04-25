from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_MODEL_IDS: tuple[str, ...] = (
    "comic-text-bubble-detector",
    "comic-text-detector",
    "paddleocr-vl-1.5",
    "aot-inpainting",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_model_root(project_root: Path) -> Path:
    return project_root / "Resource" / "Models" / "MangaCore"


def _preferred_path(status: dict[str, object]) -> str:
    for key in ("runtime_assets_path", "snapshot_path", "cache_dir", "storage_root"):
        value = str(status.get(key, "") or "").strip()
        if value:
            return value
    return ""


def _source_label(status: dict[str, object]) -> str:
    runtime_engine_id = str(status.get("runtime_engine_id", "") or "").strip()
    if runtime_engine_id:
        return runtime_engine_id
    return str(status.get("repo_id", "") or "").strip()


def main() -> int:
    project_root = _project_root()
    parser = argparse.ArgumentParser(
        description="Prepare default MangaCore model assets in Resource/Models/MangaCore.",
    )
    parser.add_argument(
        "model_ids",
        nargs="*",
        help="Optional model ids to download. Defaults to the MangaCore stack.",
    )
    parser.add_argument(
        "--root-dir",
        default=str(_default_model_root(project_root)),
        help="Override the MangaCore model root directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload models even when they already exist locally.",
    )
    args = parser.parse_args()

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore

    model_ids = tuple(args.model_ids or DEFAULT_MODEL_IDS)
    model_root = Path(args.root_dir).resolve()
    store = MangaModelStore(root_dir=model_root)

    print(f"[MangaCore] Model root: {model_root}")
    print(f"[MangaCore] Target models: {', '.join(model_ids)}")

    failures: list[str] = []
    total = len(model_ids)
    for index, model_id in enumerate(model_ids, start=1):
        try:
            status = store.get_status(model_id)
            if bool(status.get("available")) and not args.force:
                print(
                    f"[{index}/{total}] SKIP {model_id} "
                    f"({_source_label(status) or 'local-cache'}) -> {_preferred_path(status)}"
                )
                continue

            print(f"[{index}/{total}] DOWNLOAD {model_id} ...")
            result = store.download(model_id)
            print(
                f"[{index}/{total}] READY {model_id} "
                f"({_source_label(result) or 'downloaded'}) -> {_preferred_path(result)}"
            )
        except Exception as exc:
            failures.append(model_id)
            print(f"[{index}/{total}] ERROR {model_id}: {exc}", file=sys.stderr)

    if failures:
        print(
            f"[MangaCore] Failed to prepare: {', '.join(failures)}",
            file=sys.stderr,
        )
        return 1

    print("[MangaCore] Default comic runtime assets are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
