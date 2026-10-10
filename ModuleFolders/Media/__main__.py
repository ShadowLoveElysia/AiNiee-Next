"""Launch the desktop live translator without loading the batch engine."""

import argparse
import multiprocessing
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AiNiee live translation with a separate subtitle window")
    parser.add_argument("--model-root", help="Directory containing SenseVoiceSmall and translation model folders")
    parser.add_argument("--start", action="store_true", help="Start capture after opening the controller")
    args = parser.parse_args(argv)
    try:
        from ModuleFolders.Media.desktop import DesktopApp
        app = DesktopApp(model_root=args.model_root, auto_start=args.start)
        app.run()
    except (ImportError, RuntimeError) as exc:
        print(f"Cannot open live translation: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
