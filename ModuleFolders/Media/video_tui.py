"""Terminal-only video translation using the shared isolated file worker."""

from pathlib import Path
import time
from dataclasses import replace

from rich.console import Console
from rich.live import Live
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

    def select(self, title, options, *, default=None, styles=None):
        table = Table(title=Text(title, style="bold cyan"), show_header=False, box=None)
        for index, label in enumerate(options, 1):
            style = styles[index - 1] if styles and index <= len(styles) else "white"
            table.add_row(Text(str(index) + ".", style="bold green"), Text(label, style=style))
        table.add_row(Text("0.", style="bold yellow"), Text(self.host.i18n.get("menu_back"), style="dim"))
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
                             [self.t("video_tui_asr_local"), self.t("video_asr_cloud")],
                             default=2 if data.get("video_asr_mode", "local") == "cloud" else 1)
        if choice is None:
            return None
        if choice == 0:
            from ModuleFolders.Media.asr_catalog import RECOGNITION_MODELS
            selected = next((i + 1 for i, model in enumerate(RECOGNITION_MODELS)
                             if model.key == data.get("video_recognizer", data.get("recognizer", "sensevoice"))), 1)
            index = self.select(self.t("recognizer"), [model.name for model in RECOGNITION_MODELS], default=selected)
            if index is None:
                return None
            result = {"asr_mode": "local", "recognizer": RECOGNITION_MODELS[index].key}
            save_preferences({"video_asr_mode": "local", "video_recognizer": result["recognizer"]}, self.settings_path)
            return result
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
        save_preferences({"video_asr_mode": "cloud"}, self.settings_path)
        return {"asr_mode": "cloud", **changes}

    def choose_translation(self, data):
        from ModuleFolders.Media.model_catalog import TRANSLATION_MODELS
        self.console.print(self.t("video_translation_hint"), markup=False)
        selected = next((i + 1 for i, model in enumerate(TRANSLATION_MODELS)
                         if model.key == data.get("video_translation_family", data.get("family"))), 1)
        options = [model.name for model in TRANSLATION_MODELS] + [self.t("video_translation_cloud")]
        styles = ["white"] * len(TRANSLATION_MODELS) + ["bold magenta"]
        try:
            choice = self.select(self.t("video_translation_title"), options, default=selected, styles=styles)
        except (EOFError, StopIteration):
            # Preserve scripted/legacy callers that do not provide the new optional choice.
            choice = 0
        if choice is None:
            return None
        if choice == len(TRANSLATION_MODELS):
            family = data.get("video_translation_family", data.get("family", TRANSLATION_MODELS[0].key))
            save_preferences({"video_translation_mode": "cloud", "video_translation_family": family}, self.settings_path)
            return {"translation_mode": "cloud", "family": family}
        if choice < 0 or choice >= len(TRANSLATION_MODELS):
            return None
        family = TRANSLATION_MODELS[choice].key
        save_preferences({"video_translation_mode": "local", "video_translation_family": family}, self.settings_path)
        return {"translation_mode": "local", "family": family}

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
        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
        from ModuleFolders.Media.video_pipeline import tool_progress
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
        # Prepare FFmpeg before asking model/glossary choices so a missing media
        # runtime fails early (or downloads once) instead of wasting interaction.
        progress = Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                             TextColumn("{task.fields[progress_text]}"), TimeRemainingColumn(), console=self.console)
        task_id = progress.add_task(self.t("video_ffmpeg_check"), total=None, progress_text="")
        def size(value):
            if value < 1024 * 1024:
                return f"{value / 1024:.1f} KiB"
            return f"{value / (1024 * 1024):.1f} MiB"
        def tool_update(stage, completed, total):
            if total:
                detail = f"{size(completed)} / {size(total)} ({completed / total:.0%})"
            elif completed:
                detail = size(completed)
            else:
                detail = ""
            progress.update(task_id, description=self.t("video_ffmpeg_preparing", stage=stage),
                            completed=completed, total=total or None, progress_text=detail)
        with progress:
            with tool_progress(tool_update):
                find_tool("ffmpeg")
                find_tool("ffprobe")
        source_lang = Prompt.ask(self.t("source_language"), choices=CHOICES["source"], default=data["source"])
        target_lang = Prompt.ask(self.t("target_language"), choices=CHOICES["target"], default=data["target"])
        asr = self.choose_asr(data)
        if asr is None:
            return None
        translation = self.choose_translation(data)
        if translation is None:
            return None
        glossary = self.choose_glossary(data)
        if glossary is None:
            return None
        mode = data["video_subtitle_mode"] or self.subtitle_mode()
        if mode is None:
            return None
        config = VideoConfig(
            model_root=str(Path(data["model_root"]).expanduser().resolve()),
            source_lang=source_lang, target_lang=target_lang,
            device=data["device"], asr_device=data["recognition_device"], asr_endpoint=data["asr_endpoint"],
            context_segments=data["context_segments"], input_path=source,
            cache_ram_mib=data["cache_ram_mib"],
            video_encoder=data["video_encoder"],
            asr_interpreter=(__import__("ModuleFolders.Media.runtime", fromlist=["selected_python"]).selected_python(data.get("runtime_python", ""))
                             if asr.get("asr_mode") == "local" and translation.get("translation_mode") == "cloud" else ""),
            output_directory=str(Path(output).expanduser().resolve()), subtitle_mode=mode,
            **asr, **translation, **glossary,
        )
        config.validate()
        return config

    def run_job(self, config):
        from ModuleFolders.Media.runtime import selected_python
        from ModuleFolders.UserInterface.TaskUI import TaskUI
        from types import SimpleNamespace
        data = read_preferences(self.settings_path)
        session = VideoSession()
        started = time.monotonic()
        state = {
            "stage": "probing", "completed": 0, "total": 0,
            "request_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
        }
        outcome, error, directory = None, None, ""
        cancelling = False

        parent = self.host if hasattr(self.host, "config") else SimpleNamespace(config={})
        task_ui = TaskUI(parent_cli=parent, i18n=self.host.i18n)
        task_ui.log(f"[bold cyan]{self.t('video_title')}[/bold cyan]")
        last_stage = None

        def update_task_ui(stage, completed=0, total=0, request_count=0, prompt_tokens=0, completion_tokens=0):
            nonlocal last_stage
            if stage != last_stage:
                task_ui.log(f"[cyan]{self.t('video_stage_' + stage)}[/cyan]")
                last_stage = stage
            action = self.t("video_stage_" + stage)
            task_ui.update_progress(None, {
                "line": completed,
                "total_line": max(total, 1),
                "time": time.monotonic() - started,
                "file_name": Path(config.input_path).name,
                "total_requests": request_count,
                "success_requests": request_count,
                "error_requests": 0,
                "session_requests": request_count,
                "session_token": prompt_tokens + completion_tokens,
                "token": prompt_tokens + completion_tokens,
                "progress_action": action,
                "is_start": stage == "probing" and completed == 0,
            })

        try:
            media_python = selected_python(data.get("runtime_python", ""))
            if config.asr_mode == "local" and config.translation_mode == "cloud":
                config = replace(config, asr_interpreter=media_python)
                interpreter = __import__("sys").executable
            else:
                interpreter = media_python if (config.asr_mode == "local" or config.translation_mode == "local") else __import__("sys").executable
            session.start(config, interpreter=interpreter)
            with Live(task_ui.layout, console=self.console, refresh_per_second=10,
                      screen=True, transient=False) as display:
                while session.active:
                    try:
                        for event in session.poll():
                            kind = event.get("type")
                            if kind == "video_progress":
                                state.update(
                                    stage=event["stage"], completed=event.get("completed", 0),
                                    total=event.get("total", 0),
                                    request_count=event.get("request_count", 0),
                                    prompt_tokens=event.get("prompt_tokens", 0),
                                    completion_tokens=event.get("completion_tokens", 0),
                                )
                                update_task_ui(
                                    state["stage"], state["completed"], state["total"],
                                    state["request_count"], state["prompt_tokens"], state["completion_tokens"],
                                )
                            elif kind == "video_output":
                                directory = event["directory"]
                                task_ui.log(f"[dim]Output folder: {directory}[/dim]")
                            elif kind == "video_log":
                                task_ui.log(f"[dim]{event.get('message', '')}[/dim]")
                            elif kind == "video_complete":
                                outcome = event
                                task_ui.update_status(None, {"status": "normal"})
                                task_ui.log(f"[bold green]{self.t('video_done', video=event['video'], srt=event['translated_srt'])}[/bold green]")
                            elif kind in {"video_error", "error"}:
                                error = event["message"]
                                task_ui.update_status(None, {"status": "error"})
                                task_ui.log(f"[bold red]{error}[/bold red]")
                            elif kind == "video_cancelled":
                                cancelling = True
                                task_ui.update_status(None, {"status": "paused"})
                                task_ui.log(f"[yellow]{self.t('video_cancelled')}[/yellow]")
                            elif kind == "stopped" and not outcome and not error and not cancelling:
                                error = self.t("process_exit", code=event.get("exit_code"))
                                task_ui.update_status(None, {"status": "error"})
                                task_ui.log(f"[bold red]{error}[/bold red]")
                        task_ui.refresh_layout()
                        display.update(task_ui.layout, refresh=True)
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
