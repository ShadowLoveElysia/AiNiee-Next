"""Fixed media preparation commands used by the API's owned job process."""
import argparse
from dataclasses import asdict
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("applications", "ffmpeg"))
    args = parser.parse_args()
    if args.action == "applications":
        from ModuleFolders.Media.windows_audio import applications
        result = {"applications": [asdict(item) for item in applications()]}
    else:
        from ModuleFolders.Media.video_pipeline import find_tool, tool_progress
        def progress(stage, completed, total):
            print(json.dumps({"type": "download", "stage": stage,
                              "downloaded_bytes": completed, "total_bytes": total}), flush=True)
        with tool_progress(progress):
            result = {name: find_tool(name) for name in ("ffmpeg", "ffprobe")}
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
