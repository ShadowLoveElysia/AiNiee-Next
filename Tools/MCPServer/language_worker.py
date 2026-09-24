"""One full-file language scan, with stdout reserved for a single JSON result."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    from Tools.MCPServer.file_tools import FileToolError, detect_file_language

    try:
        request = json.loads(sys.stdin.buffer.read())
        with contextlib.redirect_stdout(sys.stderr):
            result = detect_file_language(request["path"], project_type=request.get("project_type", "auto"))
        payload = {"ok": True, "result": result}
    except FileToolError as exc:
        payload = {"ok": False, "error_code": exc.code, "error": str(exc)}
    except Exception:
        payload = {"ok": False, "error_code": "LANGUAGE_SCAN_FAILED", "error": "Language scan failed in the source reader."}
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
