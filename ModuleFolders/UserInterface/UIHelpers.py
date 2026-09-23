import os
import shlex
import subprocess
import sys
import tempfile
from importlib import import_module

from rich.console import Console


console = Console()


def open_in_editor(file_path):
    try:
        if sys.platform == "win32":
            os.startfile(file_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", file_path], check=False)
        else:
            subprocess.run(["xdg-open", file_path], check=False)
        return True
    except Exception as exc:
        console.print(f"[red]Failed to open editor: {exc}[/red]")
        return False


def open_temporary_text(content, *, prefix="ainiee-prompt-"):
    """Open a temporary text file and remove it after the editor closes."""
    file_path = None
    try:
        fd, file_path = tempfile.mkstemp(prefix=prefix, suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(str(content))

        if sys.platform == "win32":
            editor = os.environ.get("AINIEE_TEXT_EDITOR") or os.environ.get("VISUAL") or os.environ.get("EDITOR")
            command = shlex.split(editor, posix=False) if editor else ["notepad.exe"]
            if command:
                command[0] = command[0].strip('"')
            process = subprocess.Popen([*command, file_path])
        elif sys.platform == "darwin":
            process = subprocess.Popen(["open", "-W", file_path])
        else:
            editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
            if editor:
                process = subprocess.Popen([*shlex.split(editor), file_path])
            else:
                process = subprocess.Popen(["xdg-open", file_path])
        process.wait()
        return True
    except (OSError, ValueError):
        return False
    finally:
        if file_path:
            try:
                os.remove(file_path)
            except OSError:
                pass


def get_calibre_lang_code(current_lang):
    lang_map = {"zh_CN": "zh", "ja": "ja", "en": "en"}
    return lang_map.get(current_lang, "en")


def ensure_calibre_available(current_lang, tool_name="ebook-convert.exe"):
    ebook_module = import_module("批量电子书整合")
    return ebook_module.ensureCalibreTool(
        tool_name,
        get_calibre_lang_code(current_lang),
        isInteractive=True,
    )
