"""
设置菜单渲染器 - 基于 ConfigRegistry 动态生成设置菜单
"""

from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm

from ModuleFolders.Infrastructure.TaskConfig.ConfigRegistry import (
    CONFIG_REGISTRY,
    ConfigLevel,
    ConfigType,
    get_config_item,
    is_user_visible,
)


MANGA_ENGINE_CONFIG_STAGES = {
    "manga_detect_engine": "detect",
    "manga_segment_engine": "segment",
    "manga_ocr_engine": "ocr",
    "manga_inpaint_engine": "inpaint",
}


def format_bool_value(value: bool) -> str:
    """格式化布尔值显示"""
    return "[green]ON[/]" if value else "[red]OFF[/]"


def prompt_label(text) -> str:
    return str(text).strip().rstrip(":：").strip()


def format_config_value(key: str, value, config: dict, i18n=None) -> str:
    """根据配置类型格式化显示值"""
    item = get_config_item(key)
    if not item:
        return str(value) if value else ""

    if item.config_type == ConfigType.BOOL:
        return format_bool_value(value)
    elif item.config_type == ConfigType.PATH:
        if i18n:
            return str(value) if value else f"[dim]{i18n.get('label_not_set')}[/dim]"
        return str(value) if value else "[dim]Not Set[/dim]"
    elif item.config_type == ConfigType.INT:
        # 特殊处理线程数
        if key == "user_thread_counts" and value == 0:
            return i18n.get("label_auto") if i18n else "Auto"
        return str(value)
    elif item.config_type == ConfigType.DICT:
        # 字典类型显示为子菜单入口
        return f"[dim]{i18n.get('label_submenu')}[/dim]" if i18n else "[dim]→ Submenu[/dim]"
    elif item.config_type == ConfigType.LIST:
        # 列表类型显示数量
        count = len(value) if isinstance(value, list) else 0
        return f"[dim]{count} {i18n.get('label_items')}[/dim]" if i18n else f"[dim]{count} items[/dim]"
    elif item.config_type == ConfigType.CHOICE:
        if key in MANGA_ENGINE_CONFIG_STAGES:
            display = _format_manga_engine_value(key, value, item.default)
            return str(display) if display else ""
        # 选项类型需要翻译
        if i18n and value:
            translated = i18n.get(f"choice_{value}")
            # 如果翻译结果等于键名本身，说明没有找到翻译，使用原值
            return translated if translated != f"choice_{value}" else str(value)
        return str(value) if value else ""
    else:
        return str(value) if value else ""


def get_level_style(level: ConfigLevel) -> str:
    """获取层级对应的样式"""
    if level == ConfigLevel.ADVANCED:
        return "[bold yellow]"
    return ""


def get_level_suffix(level: ConfigLevel) -> str:
    """获取层级后缀标记"""
    if level == ConfigLevel.ADVANCED:
        return " [yellow]*[/yellow]"
    return ""


def get_online_only_suffix(item, i18n=None) -> str:
    """获取仅在线API标记"""
    if item and item.online_only:
        label = i18n.get("label_online_only") if i18n else "Online Only"
        return f" [cyan]({label})[/cyan]"
    return ""


def is_dependency_met(key: str, config: dict) -> bool:
    """检查配置项的依赖是否满足"""
    item = get_config_item(key)
    if not item or not item.depends_on:
        return True
    # 检查依赖的配置项是否启用
    dep_value = config.get(item.depends_on, False)
    return bool(dep_value)


def _format_manga_engine_value(key: str, value, default: str) -> str:
    """Format MangaCore engine ids with catalog display names when available."""
    raw_value = str(value or default or "").strip()
    if not raw_value:
        return ""
    try:
        from ModuleFolders.MangaCore.pipeline.modelCatalog import get_model_package, normalize_model_id

        model_id = normalize_model_id(raw_value)
        package = get_model_package(model_id)
    except Exception:
        return raw_value
    if package.display_name and package.display_name != package.model_id:
        return f"{package.display_name} ({package.model_id})"
    return package.model_id


class SettingsMenuBuilder:
    """设置菜单构建器"""

    def __init__(self, config: dict, i18n):
        self.config = config
        self.i18n = i18n
        self.menu_items = []  # [(id, key, item)]

    def build_menu_items(self):
        """构建菜单项列表，按分类组织，高级在前，一般项目设置永远在底部。"""
        self.menu_items = []
        idx = 1

        # 定义分类顺序和显示名称
        category_order = [
            ("path", "label_category_path"),
            ("language", "label_category_language"),
            ("translation", "label_category_translation"),
            ("output", "label_category_output"),
            ("format_conversion", "label_category_format_conversion"),
            ("feature", "label_category_feature"),
            ("prompt_feature", "label_category_prompt_feature"),
            ("api", "label_category_api"),
            ("response_check", "label_category_response_check"),
            ("automation", "label_category_automation"),
            ("manga", "label_category_manga"),
            ("advanced", "label_category_advanced"),
            ("project_general", "label_category_project_general"),
        ]

        # 按分类组织配置项
        for category, category_i18n in category_order:
            category_items = []
            for key, item in CONFIG_REGISTRY.items():
                if item.category == category and is_user_visible(key):
                    category_items.append((key, item))

            if category_items:
                # 先添加高级配置，再添加普通配置
                advanced_items = [(k, i) for k, i in category_items if i.level == ConfigLevel.ADVANCED]
                user_items = [(k, i) for k, i in category_items if i.level == ConfigLevel.USER]

                for key, item in advanced_items + user_items:
                    self.menu_items.append((idx, key, item, category_i18n))
                    idx += 1

        return self.menu_items

    def render_table(self) -> Table:
        """渲染设置表格，按分类分组"""
        table = Table(show_header=True, show_lines=False, expand=True)
        table.add_column("ID", style="dim", width=4, no_wrap=True)
        table.add_column(self.i18n.get("label_setting_name"), overflow="fold", ratio=3)
        table.add_column(self.i18n.get("label_value"), style="cyan", ratio=1)

        current_category = None

        for item_tuple in self.menu_items:
            idx, key, item, category_i18n = item_tuple

            # 添加分类标题（分类变化时）
            if current_category != category_i18n:
                if current_category is not None:
                    table.add_section()
                current_category = category_i18n
                # 添加分类标题行
                category_name = self.i18n.get(category_i18n)
                table.add_row("", f"[bold cyan]── {category_name} ──[/bold cyan]", "")

            # 检查依赖是否满足
            dep_met = is_dependency_met(key, self.config)

            # 获取显示名称
            name = self.i18n.get(item.i18n_key) if item.i18n_key else key
            name += get_level_suffix(item.level)
            name += get_online_only_suffix(item, self.i18n)

            # 获取描述（如果有）
            if item.i18n_desc_key:
                desc = self.i18n.get(item.i18n_desc_key)
                if desc and desc != item.i18n_desc_key:
                    name += f"\n  [dim]{desc}[/dim]"

            # 获取当前值
            value = self.config.get(key, item.default)
            display_value = format_config_value(key, value, self.config, self.i18n)

            # 依赖未满足时灰显
            if not dep_met:
                name = f"[dim]{name}[/dim]"
                display_value = f"[dim]{display_value}[/dim]"

            table.add_row(str(idx), name, display_value)

        return table

    def get_item_by_id(self, choice_id: int):
        """根据选择ID获取配置项"""
        for item_tuple in self.menu_items:
            idx, key, item, _ = item_tuple
            if idx == choice_id:
                return key, item
        return None, None

    def requires_confirmation(self, key: str) -> bool:
        """判断是否需要二次确认"""
        item = get_config_item(key)
        return item and item.level == ConfigLevel.ADVANCED

    def handle_input(self, key: str, item, console) -> any:
        """处理用户输入，返回新值"""
        current = self.config.get(key, item.default)

        # 检查依赖是否满足
        if not is_dependency_met(key, self.config):
            dep_item = get_config_item(item.depends_on)
            dep_name = self.i18n.get(dep_item.i18n_key) if dep_item and dep_item.i18n_key else item.depends_on
            console.print(f"[yellow]⚠ {self.i18n.get('warning_dependency_not_met').format(dep_name)}[/yellow]")
            return None

        # MCP 端口会影响外部 MCP 客户端的连接地址，先给用户明确提示再继续输入。
        if key == "mcp_server_port":
            console.print(
                Panel(
                    f"[bold yellow]{self.i18n.get('warning_mcp_port_route_sync')}[/bold yellow]",
                    border_style="yellow",
                    expand=False,
                )
            )

        # 高级配置需要二次确认
        if self.requires_confirmation(key):
            console.print(f"[yellow]⚠ {self.i18n.get('warning_advanced_setting')}[/yellow]")
            if not Confirm.ask(self.i18n.get('confirm_modify_advanced')):
                return None

        # 根据类型处理输入
        if item.config_type == ConfigType.BOOL:
            # 特殊处理：tokens_limit_switch 开启时显示警告
            if key == "tokens_limit_switch" and not current:
                console.print(f"[bold red]⚠ {self.i18n.get('warn_token_mode_severe')}[/bold red]")
                if not Confirm.ask(self.i18n.get('confirm_modify_advanced')):
                    return None
            return not current
        elif item.config_type == ConfigType.INT:
            return IntPrompt.ask(
                self.i18n.get(item.i18n_key),
                default=current
            )
        elif item.config_type == ConfigType.PATH:
            return Prompt.ask(
                self.i18n.get(item.i18n_key),
                default=str(current)
            ).strip().strip('"').strip("'")
        elif item.config_type == ConfigType.DICT:
            # 字典类型：显示子菜单让用户切换各项
            return self._handle_dict_input(key, current, console)
        elif item.config_type == ConfigType.CHOICE:
            if key in MANGA_ENGINE_CONFIG_STAGES:
                return self._handle_manga_engine_choice_input(key, item, current, console)
            # 选择类型：显示选项列表
            return self._handle_choice_input(key, item, current, console)
        else:
            return Prompt.ask(
                self.i18n.get(item.i18n_key),
                default=str(current)
            )

    def _handle_dict_input(self, key: str, current: dict, console) -> dict:
        """处理字典类型的输入，显示子菜单"""
        if not isinstance(current, dict):
            return current

        result = current.copy()
        while True:
            # 清屏并显示子菜单
            console.clear()
            console.print(Panel(f"[bold]{self.i18n.get('setting_response_check')}[/bold]"))

            # 显示当前字典的所有键值
            table = Table(show_header=True, show_lines=False)
            table.add_column("ID", style="dim", width=4)
            table.add_column(self.i18n.get("label_setting_name"))
            table.add_column(self.i18n.get("label_value"), style="cyan")

            keys = list(result.keys())
            for idx, k in enumerate(keys, 1):
                # 尝试翻译键名
                display_key = self.i18n.get(f"check_{k}")
                if display_key == f"check_{k}":
                    display_key = k
                display_val = format_bool_value(result[k]) if isinstance(result[k], bool) else str(result[k])
                table.add_row(str(idx), display_key, display_val)

            console.print(table)
            console.print(f"\n[dim]{self.i18n.get('prompt_toggle_or_back')}[/dim]")

            choice = Prompt.ask(prompt_label(self.i18n.get('prompt_select')))
            if choice.lower() in ('q', 'b', '0', ''):
                break

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(keys):
                    k = keys[idx]
                    if isinstance(result[k], bool):
                        result[k] = not result[k]
            except ValueError:
                pass

        return result

    def _handle_manga_engine_choice_input(self, key: str, item, current, console):
        """处理 MangaCore 引擎选择，未下载/未接入 Runtime 的模型灰显且不可选。"""
        stage = MANGA_ENGINE_CONFIG_STAGES.get(key)
        if not stage:
            return None

        try:
            from ModuleFolders.MangaCore.pipeline.modelCatalog import normalize_model_id
            from ModuleFolders.MangaCore.pipeline.modelStore import MangaModelStore

            manifest = MangaModelStore().build_manager_manifest()
        except Exception as exc:
            console.print(f"[yellow]{self._t('error_config_load', 'Failed to load configuration')}: {exc}[/yellow]")
            return None

        options = list((manifest.get("engine_options") or {}).get(stage) or [])
        if not options:
            console.print(f"[yellow]{self._t('manga_model_no_stage_options', 'No model options are registered for this stage.')}[/yellow]")
            return None

        current_model_id = normalize_model_id(str(current or item.default or ""))
        selectable_indices = {}

        table = Table(show_header=True, show_lines=False, expand=True)
        table.add_column("ID", style="cyan", width=4, no_wrap=True)
        table.add_column(self._t("manga_package", "Package"), overflow="fold", ratio=2)
        table.add_column(self._t("manga_model_hardware", "Hardware"), ratio=1)
        table.add_column(self._t("manga_model_effect", "Effect"), ratio=1)
        table.add_column(self._t("manga_model_status", "Status"), ratio=1)
        table.add_column(self._t("label_value", "Value"), overflow="fold", ratio=2)

        for index, option in enumerate(options, 1):
            model_id = normalize_model_id(str(option.get("model_id") or ""))
            selectable = bool(option.get("selectable"))
            if selectable:
                selectable_indices[index] = model_id

            marker = "[green]●[/green]" if model_id == current_model_id else ""
            id_cell = str(index) if selectable else f"[dim]{index}[/dim]"
            status = self._manga_engine_option_status(option)
            style = "" if selectable else "dim"
            table.add_row(
                id_cell,
                str(option.get("display_name") or model_id),
                str(option.get("hardware_tier") or ""),
                str(option.get("quality_tier") or ""),
                status,
                marker or model_id,
                style=style,
            )
        table.add_row("[red]0[/red]", self._t("menu_exit", "Exit"), "", "", "", "")

        console.print(table)
        console.print(f"[dim]{self._t('manga_model_available_only_hint', 'Only downloaded and runtime-supported model packages can be selected. Missing packages remain visible but disabled.')}[/dim]")

        if not selectable_indices:
            console.print(f"[yellow]{self._t('manga_model_no_selectable_options', 'No downloaded selectable model is available for this stage yet.')}[/yellow]")
            return None

        choice_input = Prompt.ask(
            prompt_label(self.i18n.get("prompt_select")),
            choices=["0", *(str(index) for index in selectable_indices)],
            default="0",
            show_choices=False,
        )
        if choice_input == "0":
            return None
        try:
            return selectable_indices[int(choice_input)]
        except (ValueError, KeyError):
            return None

    def _handle_choice_input(self, key: str, item, current, console):
        """处理选择类型的输入，显示选项列表"""
        if not item.choices:
            return current

        # 显示选项列表
        table = Table(show_header=False, show_lines=False)
        for idx, choice in enumerate(item.choices, 1):
            # 尝试翻译选项
            display = self.i18n.get(f"choice_{choice}")
            if display == f"choice_{choice}":
                display = choice
            marker = "[green]●[/green]" if choice == current else " "
            table.add_row(f"[cyan]{idx}.[/cyan]", display, marker)

        console.print(table)

        choice_input = Prompt.ask(prompt_label(self.i18n.get('prompt_select')))
        try:
            idx = int(choice_input) - 1
            if 0 <= idx < len(item.choices):
                return item.choices[idx]
        except ValueError:
            pass

        return None

    def _manga_engine_option_status(self, option: dict[str, object]) -> str:
        if option.get("selectable"):
            return self._t("manga_model_selectable", "Selectable")
        reason = str(option.get("disabled_reason") or "")
        if reason == "missing":
            return self._t("manga_model_not_downloaded", "Not downloaded")
        if reason == "unsupported_runtime":
            return self._t("manga_model_unsupported_runtime", "Runtime unsupported")
        return self._t("manga_missing", "Missing")

    def _t(self, key: str, fallback: str) -> str:
        value = self.i18n.get(key) if self.i18n else key
        return fallback if value == key else value
