import locale
import os

import rapidjson as json

from ModuleFolders.Base.Base import Base


class I18NLoader:
    def __init__(self, project_root, lang="en"):
        self.project_root = project_root
        self.lang = lang
        self.data = {}
        self.load_language(lang)

    def load_language(self, lang):
        self.lang = lang
        path = os.path.join(self.project_root, "I18N", f"{lang}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                self.data = json.load(file)
        elif lang != "en":
            self.load_language("en")
        else:
            self.data = {}

    def get(self, key):
        return self.data.get(key, key)


def detect_system_language():
    lang_code = ""
    try:
        lang_code = locale.getdefaultlocale()[0] or ""
    except Exception:
        try:
            lang_code = locale.getlocale()[0] or ""
        except Exception:
            lang_code = ""

    if lang_code.startswith("zh"):
        return "zh_CN"
    if lang_code.startswith("ja"):
        return "ja"
    return "en"


def load_saved_interface_language(project_root):
    config_path = os.path.join(project_root, "Resource", "config.json")
    if not os.path.exists(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.load(file)
        return config.get("interface_language")
    except Exception:
        return None


def initialize_i18n(project_root):
    current_lang = load_saved_interface_language(project_root) or detect_system_language()
    i18n = I18NLoader(project_root, current_lang)
    Base.i18n = i18n
    return current_lang, i18n


def switch_runtime_language(project_root, lang):
    i18n = I18NLoader(project_root, lang)
    Base.i18n = i18n
    return i18n


def get_base_interface_language_name(lang):
    return {
        "zh_CN": "简中",
        "ja": "日语",
        "en": "英语",
    }.get(lang, "英语")
