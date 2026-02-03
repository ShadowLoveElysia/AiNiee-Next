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


def format_bool_value(value: bool) -> str:
    """格式化布尔值显示"""
    return "[green]ON[/]" if value else "[red]OFF[/]"


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


class SettingsMenuBuilder:
    """设置菜单构建器"""

    def __init__(self, config: dict, i18n):
        self.config = config
        self.i18n = i18n
        self.menu_items = []  # [(id, key, item)]

    def build_menu_items(self):
        """构建菜单项列表，按分类组织，高级在前"""
        self.menu_items = []
        idx = 1

        # 定义分类顺序和显示名称
        category_order = [
            ("path", "label_category_path"),
            ("language", "label_category_language"),
            ("translation", "label_category_translation"),
            ("output", "label_category_output"),
            ("feature", "label_category_feature"),
            ("prompt_feature", "label_category_prompt_feature"),
            ("api", "label_category_api"),
            ("response_check", "label_category_response_check"),
            ("advanced", "label_category_advanced"),
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
        table = Table(show_header=True, show_lines=False)
        table.add_column("ID", style="dim", width=4)
        table.add_column(self.i18n.get("label_setting_name"))
        table.add_column(self.i18n.get("label_value"), style="cyan")

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

            choice = Prompt.ask(self.i18n.get('prompt_select'))
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

        choice_input = Prompt.ask(self.i18n.get('prompt_select'))
        try:
            idx = int(choice_input) - 1
            if 0 <= idx < len(item.choices):
                return item.choices[idx]
        except ValueError:
            pass

        return None
