"""
命令行非交互运行模块
从 ainiee_cli.py 分离
"""
import time

from rich.console import Console

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType


console = Console()


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
            self.host.config["think_depth"] = args.think_depth
        if args.thinking_budget is not None:
            self.host.config["thinking_budget"] = args.thinking_budget
        if args.failover is not None:
            self.host.config["enable_api_failover"] = args.failover == "on"

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
