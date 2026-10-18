"""Launch the desktop live translator without loading the batch engine."""

import argparse
import multiprocessing
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AiNiee live translation with a separate subtitle window")
    parser.add_argument("--model-root", help="Directory containing SenseVoiceSmall and translation model folders")
    parser.add_argument("--start", action="store_true", help="Start capture after opening the controller")
    parser.add_argument("--video", action="store_true", help="Open file video translation in the media controller")
    parser.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        from ModuleFolders.Media.desktop import DesktopApp
        app = DesktopApp(model_root=args.model_root, auto_start=args.start, managed=args.managed)
        if args.video:
            app.root.after_idle(app.show_video_window)
        app.run()
    except Exception as exc:
        if args.managed:
            from ModuleFolders.Media.diagnostics import emit_diagnostic
            emit_diagnostic({"type": "error", "message": type(exc).__name__})
        print(f"Cannot open live translation: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
