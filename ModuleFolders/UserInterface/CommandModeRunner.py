"""
命令行非交互运行模块
从 ainiee_cli.py 分离
"""
import os
import re
import time

from rich.console import Console

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.MangaFeatureGuard import get_manga_feature_status
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType


console = Console()

_MANGA_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
_MANGA_PACKAGE_SUFFIXES = {
    ".pdf",
    ".zip",
    ".cbz",
    ".rar",
    ".cbr",
}
_MANGA_FILE_SUFFIXES = _MANGA_IMAGE_SUFFIXES | _MANGA_PACKAGE_SUFFIXES


def normalize_cli_path(path: str) -> str:
    raw_path = str(path or "").strip().strip('"').strip("'")
    if not raw_path:
        return ""
    if os.name != "nt":
        normalized = raw_path.replace("\\", "/")
        drive_match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
        if drive_match:
            drive = drive_match.group(1).lower()
            rest = drive_match.group(2)
            raw_path = os.path.join("/mnt", drive, rest)
    return os.path.abspath(os.path.expanduser(raw_path))


def derive_manga_output_path(input_path: str) -> str:
    normalized = normalize_cli_path(input_path)
    base_name = os.path.basename(normalized.rstrip(os.sep))
    suffix = os.path.splitext(base_name)[1].lower()
    if os.path.isfile(normalized) or suffix in _MANGA_FILE_SUFFIXES:
        base_name = os.path.splitext(base_name)[0]
    return os.path.join(os.path.dirname(normalized), f"{base_name}_AiNiee_Output")


def resolve_manga_output_path(config: dict, args, input_path: str) -> str:
    explicit_output = str(getattr(args, "output_path", "") or "").strip()
    if explicit_output:
        return normalize_cli_path(explicit_output)

    configured_output = str(config.get("label_output_path") or "").strip()
    if config.get("auto_set_output_path", False) or not configured_output:
        return derive_manga_output_path(input_path)

    return normalize_cli_path(configured_output)


def is_supported_manga_input_path(input_path: str) -> bool:
    normalized = normalize_cli_path(input_path)
    if os.path.isdir(normalized):
        return True
    if not os.path.isfile(normalized):
        return False
    return os.path.splitext(normalized)[1].lower() in _MANGA_FILE_SUFFIXES


def describe_supported_manga_inputs() -> str:
    return ", ".join(sorted(_MANGA_FILE_SUFFIXES)) + ", or a directory containing supported images"


def resolve_manga_translation_settings(config: dict, args) -> dict[str, str]:
    platforms = config.get("platforms") if isinstance(config.get("platforms"), dict) else {}
    api_settings = config.get("api_settings") if isinstance(config.get("api_settings"), dict) else {}

    platform = str(
        getattr(args, "platform", None)
        or config.get("target_platform", "")
        or api_settings.get("translate")
        or ""
    ).strip()
    platform_config = platforms.get(platform) if platform else {}
    if not isinstance(platform_config, dict):
        platform_config = {}

    model = str(getattr(args, "model", None) or config.get("model") or platform_config.get("model", "") or "").strip()
    api_url = str(
        getattr(args, "api_url", None)
        or config.get("base_url")
        or platform_config.get("api_url", "")
        or ""
    ).strip()
    api_key = str(getattr(args, "api_key", None) or config.get("api_key") or platform_config.get("api_key", "") or "").strip()
    return {
        "platform": platform,
        "model": model,
        "api_url": api_url,
        "api_key_state": "configured" if api_key else "empty",
    }


def validate_manga_translation_settings(settings: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if not settings.get("platform"):
        problems.append("No translation platform is configured.")
    if not settings.get("model"):
        problems.append("No translation model is configured.")
    if not settings.get("api_url"):
        problems.append("No translation API URL is configured.")
    return problems


def format_manga_page_stats(stats: dict[str, object]) -> str:
    labels = (
        ("page_count", "pages"),
        ("total_blocks", "blocks"),
        ("total_translated_blocks", "translated"),
        ("translation_warnings", "translation_warnings"),
        ("no_text_pages", "no_text_pages"),
        ("inpainted_pages", "inpainted_pages"),
    )
    parts = [f"{label}={stats[key]}" for key, label in labels if key in stats]
    return ", ".join(parts)


class CommandModeRunner:
    """CLI 非交互模式任务分发。"""

    def __init__(self, host):
        self.host = host

    def run(self, args):
        if args.task == "mcp":
            # MCP 命令行模式交给专用桥接层处理，保持 ainiee_cli.py 只做委托。
            return self.host.mcp_runtime_bridge.run_mcp_server_from_command(
                transport=getattr(args, "mcp_transport", "stdio"),
            )

        if getattr(args, "manga", False) and args.task != "translate":
            console.print("[red]Error: --manga currently only supports the translate task.[/red]")
            return 2

        if args.profile:
            self.host.root_config["active_profile"] = args.profile
            self.host.save_config(save_root=True)
            self.host.load_config()

        if args.rules_profile:
            self.host.root_config["active_rules_profile"] = args.rules_profile
            self.host.save_config(save_root=True)
            self.host.load_config()

        self._apply_config_overrides(args)
        self.host.save_config()

        task_map = {
            "translate": TaskType.TRANSLATION,
            "polish": TaskType.POLISH,
            "all_in_one": TaskType.TRANSLATE_AND_POLISH,
        }

        if args.task == "queue":
            self._run_queue(args)
            return 0

        if args.task in task_map:
            if not args.input_path:
                console.print("[red]Error: input_path is required for this task.[/red]")
                return 2
            if getattr(args, "manga", False):
                return self._run_manga(args)
            if args.task == "all_in_one":
                self._run_all_in_one(args)
            else:
                self.host.run_task(
                    task_map[args.task],
                    target_path=args.input_path,
                    continue_status=args.resume,
                    non_interactive=args.non_interactive,
                    web_mode=args.web_mode,
                )
            return 0

        if args.task == "export":
            if not args.input_path:
                console.print("[red]Error: input_path is required for export.[/red]")
                return 2
            self.host.run_export_only(
                target_path=args.input_path,
                non_interactive=args.non_interactive,
            )
            return 0

        return 0

    def _apply_config_overrides(self, args):
        if args.source_lang:
            self.host.config["source_language"] = args.source_lang
        if args.target_lang:
            self.host.config["target_language"] = args.target_lang
        if args.output_path:
            self.host.config["label_output_path"] = args.output_path
        if args.project_type:
            self.host.config["translation_project"] = args.project_type

        if args.threads is not None:
            self.host.config["user_thread_counts"] = args.threads
        if args.retry is not None:
            self.host.config["retry_count"] = args.retry
        if args.timeout is not None:
            self.host.config["request_timeout"] = args.timeout
        if args.rounds is not None:
            self.host.config["round_limit"] = args.rounds
        if args.pre_lines is not None:
            self.host.config["pre_line_counts"] = args.pre_lines

        if args.lines is not None:
            self.host.config["tokens_limit_switch"] = False
            self.host.config["lines_limit"] = args.lines
        if args.tokens is not None:
            self.host.config["tokens_limit_switch"] = True
            self.host.config["tokens_limit"] = args.tokens

        if args.platform:
            self.host.config["target_platform"] = args.platform
        if args.model:
            self.host.config["model"] = args.model
        if args.api_url:
            self.host.config["base_url"] = args.api_url
        if args.api_key:
            self.host.config["api_key"] = args.api_key
            target_platform = self.host.config.get("target_platform", "")
            if target_platform and target_platform in self.host.config.get("platforms", {}):
                self.host.config["platforms"][target_platform]["api_key"] = args.api_key

        if args.think_depth is not None:
            think_depth = args.think_depth.strip() if isinstance(args.think_depth, str) else args.think_depth
            if isinstance(think_depth, str) and think_depth.isdigit():
                think_depth = int(think_depth)
            self.host.config["think_depth"] = think_depth
            target_platform = self.host.config.get("target_platform", "")
            if target_platform and target_platform in self.host.config.get("platforms", {}):
                self.host.config["platforms"][target_platform]["think_depth"] = think_depth
        if args.thinking_budget is not None:
            self.host.config["thinking_budget"] = args.thinking_budget
            target_platform = self.host.config.get("target_platform", "")
            if target_platform and target_platform in self.host.config.get("platforms", {}):
                self.host.config["platforms"][target_platform]["thinking_budget"] = args.thinking_budget
        if args.failover is not None:
            self.host.config["enable_api_failover"] = args.failover == "on"
        for manga_key in (
            "manga_ocr_engine",
            "manga_detect_engine",
            "manga_segment_engine",
            "manga_inpaint_engine",
        ):
            manga_value = str(getattr(args, manga_key, "") or "").strip()
            if manga_value:
                self.host.config[manga_key] = manga_value

    def _run_queue(self, args):
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager

        queue_manager = QueueManager()
        if args.queue_file:
            queue_manager.load_tasks(args.queue_file)

        if not queue_manager.tasks:
            console.print(f"[red]Error: Task queue is empty (File: {queue_manager.queue_file}). Cannot run queue task.[/red]")
            return

        console.print(f"[bold green]Running Task Queue ({len(queue_manager.tasks)} items)...[/bold green]")
        self.host._is_queue_mode = True
        self.host.start_queue_log_monitor()
        queue_manager.start_queue(self.host)

        try:
            while queue_manager.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            Base.work_status = Base.STATUS.STOPING
        finally:
            self.host.stop_queue_log_monitor()
            self.host._is_queue_mode = False

    def _run_all_in_one(self, args):
        if args.input_path:
            if not self.host.prompt_selection_guard.ensure_prompts_selected(
                TaskType.TRANSLATE_AND_POLISH,
                interactive=False,
            ):
                return

            translate_ok = self.host.run_task(
                TaskType.TRANSLATION,
                target_path=args.input_path,
                continue_status=args.resume,
                non_interactive=True,
                web_mode=args.web_mode,
                from_queue=True,
                skip_prompt_validation=True,
            )
            if translate_ok and Base.work_status != Base.STATUS.STOPING:
                self.host.run_task(
                    TaskType.POLISH,
                    target_path=args.input_path,
                    continue_status=True,
                    non_interactive=True,
                    web_mode=args.web_mode,
                    skip_prompt_validation=True,
                )
            return

        self.host.run_all_in_one()

    def _run_manga(self, args):
        input_path = normalize_cli_path(args.input_path)
        if not os.path.exists(input_path):
            console.print(f"[red][MangaCore][/red] Input path not found: {input_path}")
            return 2
        if not is_supported_manga_input_path(input_path):
            console.print(f"[red][MangaCore][/red] Unsupported manga input source: {input_path}")
            console.print(f"[yellow][MangaCore][/yellow] Supported inputs: {describe_supported_manga_inputs()}")
            return 2

        manga_status = get_manga_feature_status(require_models=False)
        if not manga_status.available:
            console.print(f"[yellow][MangaCore][/yellow] {manga_status.message}")
            for detail in manga_status.details:
                console.print(f"[yellow][MangaCore][/yellow] {detail}")
            return 2

        from ModuleFolders.MangaCore.bridge.configAdapter import build_cli_config_snapshot
        from ModuleFolders.MangaCore.pipeline.runnerBatch import MangaBatchRunner

        output_path = resolve_manga_output_path(self.host.config, args, input_path)
        self.host.config["label_input_path"] = input_path
        self.host.config["label_output_path"] = output_path
        config_snapshot = build_cli_config_snapshot(self.host, args)

        translation_settings = resolve_manga_translation_settings(self.host.config, args)
        translation_problems = validate_manga_translation_settings(translation_settings)
        if translation_problems:
            console.print("[red][MangaCore][/red] Translation API configuration is incomplete.")
            for problem in translation_problems:
                console.print(f"[red][MangaCore][/red] {problem}")
            console.print("[yellow][MangaCore][/yellow] Configure API settings first, or pass --platform, --model, and --api-url.")
            return 2

        model_status = get_manga_feature_status(config_snapshot=config_snapshot, require_models=True)
        if not model_status.available:
            if getattr(args, "manga_strict_models", False):
                console.print(f"[red][MangaCore][/red] {model_status.message}")
                for detail in model_status.details:
                    console.print(f"[red][MangaCore][/red] {detail}")
                return 2

            console.print(
                "[yellow][MangaCore][/yellow] Default visual model packages are not fully prepared; "
                "first-pass pipeline will use available fallback runtimes where possible."
            )
            for detail in model_status.details:
                console.print(f"[yellow][MangaCore][/yellow] {detail}")

        self.host.save_config()

        console.print(f"[bold cyan][MangaCore][/bold cyan] Input: {input_path}")
        console.print(f"[bold cyan][MangaCore][/bold cyan] Output: {output_path}")
        console.print(
            "[bold cyan][MangaCore][/bold cyan] Translation: "
            f"{translation_settings['platform']} / {translation_settings['model']} "
            f"({translation_settings['api_key_state']} API key)"
        )
        console.print(
            "[bold cyan][MangaCore][/bold cyan] Visual engines: "
            f"ocr={config_snapshot.get('manga_ocr_engine')}, "
            f"detect={config_snapshot.get('manga_detect_engine')}, "
            f"segment={config_snapshot.get('manga_segment_engine')}, "
            f"inpaint={config_snapshot.get('manga_inpaint_engine')}"
        )

        try:
            result = MangaBatchRunner(logger=console.print).run(
                input_path=input_path,
                output_path=output_path,
                config_snapshot=config_snapshot,
                profile_name=self.host.root_config.get("active_profile", "default"),
                rules_profile_name=self.host.root_config.get("active_rules_profile", "default"),
                source_lang=self.host.config.get("source_language", "ja"),
                target_lang=self.host.config.get("target_language", "zh_cn"),
            )
        except Exception as exc:
            console.print(f"[red][MangaCore][/red] Manga batch pipeline failed: {exc}")
            return 1

        console.print(f"[bold green][MangaCore][/bold green] Project ready: {result.session.project_path}")
        if result.page_job:
            console.print(
                f"[bold cyan][MangaCore][/bold cyan] Page pipeline: "
                f"{result.page_job.status} | {result.page_job.message}"
            )
            if isinstance(getattr(result.page_job, "result", None), dict):
                stats = format_manga_page_stats(result.page_job.result)
                if stats:
                    console.print(f"[bold cyan][MangaCore][/bold cyan] Page stats: {stats}")
        if result.exports.exported_paths:
            console.print("[bold green][MangaCore][/bold green] Exported files:")
            for key, path in result.exports.exported_paths.items():
                console.print(f"  - {key}: {path}")
        if result.warnings:
            console.print("[yellow][MangaCore][/yellow] Finished with warning(s):")
            for warning in result.warnings:
                console.print(f"  - {warning}")
        return 0 if result.ok else 1
