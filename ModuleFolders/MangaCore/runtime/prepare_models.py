import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def main() -> int:
    project_root = _project_root()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from ModuleFolders.Service.HttpService.ModelDownload import main as download_main

    return download_main()


if __name__ == "__main__":
    raise SystemExit(main())
