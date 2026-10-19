"""Terminal-only video translation using the shared isolated file worker."""

from pathlib import Path
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from ModuleFolders.Media.preferences import SETTINGS_PATH, read_preferences, save_preferences, validate_preference
from ModuleFolders.Media.video_pipeline import VideoConfig, VideoSession, find_tool, validate_video_input


class VideoTranslationTUI:
    def __init__(self, host, *, settings_path=SETTINGS_PATH, console=None):
        self.host = host
        self.settings_path = Path(settings_path)
        self.console = console or Console()

    def t(self, key, **values):
        return self.host.i18n.get("media_" + key).format(**values)

    def select(self, title, options, *, default=None):
        table = Table(title=title, show_header=False, box=None)
        for index, label in enumerate(options, 1):
            table.add_row(str(index) + ".", Text(label))
        table.add_row("0.", self.host.i18n.get("menu_back"))
        self.console.print(table)
        choice = IntPrompt.ask(self.host.i18n.get("prompt_select"), choices=[str(i) for i in range(len(options) + 1)],
                               default=default, show_choices=False)
        return None if choice == 0 else choice - 1

    def subtitle_mode(self, current=""):
        self.console.print(self.t("video_mode_hint"), markup=False)
        choice = self.select(self.t("video_mode_title"), [self.t("video_soft"), self.t("video_hard")],
                             default={"soft": 1, "hard": 2}.get(current))
        if choice is None:
            return None
        mode = ("soft", "hard")[choice]
        save_preferences({"video_subtitle_mode": mode}, self.settings_path)
        return mode

    def choose_asr(self, data):
        self.console.print(self.t("video_asr_hint"), markup=False)
        choice = self.select(self.t("video_asr_title"),
                             [self.t("video_tui_asr_local"), self.t("video_asr_cloud")], default=1)
        if choice is None:
            return None
        if choice == 0:
            from ModuleFolders.Media.asr_catalog import RECOGNITION_MODELS
            selected = next((i + 1 for i, model in enumerate(RECOGNITION_MODELS) if model.key == data["recognizer"]), 1)
            index = self.select(self.t("recognizer"), [model.name for model in RECOGNITION_MODELS], default=selected)
            if index is None:
                return None
            return {"asr_mode": "local", "recognizer": RECOGNITION_MODELS[index].key}
        from ModuleFolders.Media.cloud_asr import validate_cloud_settings
        changes = {}
        for key, label in (("cloud_asr_endpoint", "video_asr_endpoint"), ("cloud_asr_model", "video_asr_model")):
            changes[key] = validate_preference(key, Prompt.ask(self.t(label), default=data.get(key, "")).strip())
        key_prompt = self.t("video_asr_api_key")
        if data.get("cloud_asr_api_key"):
            key_prompt += " " + self.t("video_asr_key_keep")
        key = Prompt.ask(key_prompt, password=True).strip()
        changes["cloud_asr_api_key"] = key or data.get("cloud_asr_api_key", "")
        validate_cloud_settings(changes["cloud_asr_endpoint"], changes["cloud_asr_model"], changes["cloud_asr_api_key"])
        save_preferences(changes, self.settings_path)
        return {"asr_mode": "cloud", **changes}

    def choose_glossary(self, data):
        self.console.print(self.t("video_glossary_hint"), markup=False)
        choice = self.select(self.t("video_glossary_source"),
                             [self.t("video_glossary_temporary"), self.t("video_glossary_manual")], default=1)
        if choice is None:
            return None
        if choice == 0:
            return {"glossary_mode": "temporary", "glossary": ()}
        profiles = {name: entries for name, entries in data["glossary_profiles"].items() if entries}
        if not profiles:
            raise ValueError(self.t("video_glossary_choose"))
        names = list(profiles)
        selected = self.select(self.t("video_glossary_manual"), names)
        if selected is None:
            return None
        return {"glossary_mode": "manual", "glossary": tuple(profiles[names[selected]])}

    def prepare(self):
        from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS
        from ModuleFolders.Media.preferences import CHOICES
        self.console.print(self.t("video_input"), markup=False)
        source = self.host.file_selector.select_path(start_path=str(Path.cwd()), select_file=True, select_dir=False)
        if not source:
            return None
        source = str(Path(source).expanduser().resolve())
        validate_video_input(source, "soft")
        data = read_preferences(self.settings_path)
        output = Prompt.ask(self.t("video_output"), default=str(Path(source).parent / "AiNiee-Video")).strip().strip('"')
        if not output:
            return None
        source_lang = Prompt.ask(self.t("source_language"), choices=CHOICES["source"], default=data["source"])
        target_lang = Prompt.ask(self.t("target_language"), choices=CHOICES["target"], default=data["target"])
        asr = self.choose_asr(data)
        if asr is None:
            return None
        selected = next((i + 1 for i, model in enumerate(TRANSLATION_MODELS) if model.key == data["family"]), 1)
        index = self.select(self.t("translator"), [model.name for model in TRANSLATION_MODELS], default=selected)
        if index is None:
            return None
        glossary = self.choose_glossary(data)
        if glossary is None:
            return None
        mode = data["video_subtitle_mode"] or self.subtitle_mode()
        if mode is None:
            return None
        find_tool("ffmpeg")
        find_tool("ffprobe")
        config = VideoConfig(
            model_root=str(Path(data["model_root"]).expanduser().resolve()),
            family=TRANSLATION_MODELS[index].key, source_lang=source_lang, target_lang=target_lang,
            device=data["device"], asr_device=data["recognition_device"], asr_endpoint=data["asr_endpoint"],
            context_segments=data["context_segments"], input_path=source,
            cache_ram_mib=data["cache_ram_mib"],
            output_directory=str(Path(output).expanduser().resolve()), subtitle_mode=mode, **asr, **glossary,
        )
        config.validate()
        return config

    def run_job(self, config):
        from ModuleFolders.Media.runtime import selected_python
        data = read_preferences(self.settings_path)
        session = VideoSession()
        started = time.monotonic()
        state = {"stage": "probing", "completed": 0, "total": 0}
        outcome, error, directory = None, None, ""
        cancelling = False

        def render():
            text = Text(self.t("video_cancelling") if cancelling else self.t("video_stage_" + state["stage"]))
            if state["total"]:
                text.append(f"\n{state['completed'] / state['total']:.0%}")
                if state["stage"] != "recognizing":
                    text.append(f"  {state['completed']}/{state['total']}")
            text.append("\n" + self.t("video_tui_elapsed", seconds=round(time.monotonic() - started, 1)))
            text.append("\n" + self.t("video_tui_cancel_hint"))
            return Panel(text, title=self.t("video_title"))

        try:
            session.start(config, interpreter=selected_python(data.get("runtime_python", "")))
            with Live(render(), console=self.console, refresh_per_second=4, transient=True) as display:
                while session.active:
                    try:
                        for event in session.poll():
                            kind = event.get("type")
                            if kind == "video_progress":
                                state.update(stage=event["stage"], completed=event.get("completed", 0), total=event.get("total", 0))
                            elif kind == "video_output":
                                directory = event["directory"]
                            elif kind == "video_complete":
                                outcome = event
                            elif kind in {"video_error", "error"}:
                                error = event["message"]
                            elif kind == "video_cancelled":
                                cancelling = True
                            elif kind == "stopped" and not outcome and not error and not cancelling:
                                error = self.t("process_exit", code=event.get("exit_code"))
                        display.update(render())
                        if session.active:
                            time.sleep(.1)
                    except KeyboardInterrupt:
                        if cancelling:
                            session.close()
                        else:
                            cancelling = True
                            session.stop()
        finally:
            session.close()
        if error:
            self.console.print(self.t("error", message=error), markup=False, style="red")
        elif outcome:
            self.console.print(self.t("video_done", video=outcome["video"], srt=outcome["translated_srt"]), markup=False)
        else:
            self.console.print(self.t("video_cancelled"), markup=False)
        if directory:
            self.console.print(self.t("video_tui_output_path", path=directory), markup=False)
        return outcome

    def translate(self):
        try:
            config = self.prepare()
            if config is not None:
                return self.run_job(config)
        except (ValueError, OSError, RuntimeError) as exc:
            self.console.print(self.t("error", message=str(exc)), markup=False, style="red")
        except (KeyboardInterrupt, EOFError):
            self.console.print(self.t("video_cancelled"), markup=False)
        return None

    def show(self):
        while True:
            self.host.display_banner()
            choice = self.select(self.t("video_title"),
                                 [self.t("video_start"), self.t("settings"), self.t("video_mode_title")])
            if choice is None:
                return
            if choice == 0:
                self.translate()
                Prompt.ask(self.host.i18n.get("msg_press_enter"), default="")
            elif choice == 1:
                from ModuleFolders.Media.tui_settings import show_media_settings
                show_media_settings(self.host)
            else:
                self.subtitle_mode(read_preferences(self.settings_path)["video_subtitle_mode"])


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="AiNiee terminal video translation")
    parser.parse_args(argv)
    from types import SimpleNamespace
    from ModuleFolders.Media.preferences import PROJECT_ROOT
    from ModuleFolders.UserInterface.AppI18N import initialize_i18n
    from ModuleFolders.UserInterface.FileSelector import FileSelector
    _, locale = initialize_i18n(str(PROJECT_ROOT))
    host = SimpleNamespace(i18n=locale, file_selector=FileSelector(locale), display_banner=lambda: None)
    try:
        VideoTranslationTUI(host).show()
    except (KeyboardInterrupt, EOFError):
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
