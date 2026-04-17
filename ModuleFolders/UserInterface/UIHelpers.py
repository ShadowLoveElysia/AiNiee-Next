import os
import subprocess
import sys
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
