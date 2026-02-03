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


def format_config_value(key: str, value, config: dict) -> str:
    """根据配置类型格式化显示值"""
    item = get_config_item(key)
    if not item:
        return str(value) if value else ""

    if item.config_type == ConfigType.BOOL:
        return format_bool_value(value)
    elif item.config_type == ConfigType.PATH:
        return str(value) if value else "[dim]Not Set[/dim]"
    elif item.config_type == ConfigType.INT:
        # 特殊处理线程数
        if key == "user_thread_counts" and value == 0:
            return "Auto"
        return str(value)
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


class SettingsMenuBuilder:
    """设置菜单构建器"""

    def __init__(self, config: dict, i18n):
        self.config = config
        self.i18n = i18n
        self.menu_items = []  # [(id, key, item)]

    def build_menu_items(self):
        """构建菜单项列表，高级在前，基础在后"""
        self.menu_items = []
        idx = 1

        # 先添加高级配置
        for key, item in CONFIG_REGISTRY.items():
            if item.level == ConfigLevel.ADVANCED and is_user_visible(key):
                self.menu_items.append((idx, key, item))
                idx += 1

        # 再添加用户配置
        for key, item in CONFIG_REGISTRY.items():
            if item.level == ConfigLevel.USER and is_user_visible(key):
                self.menu_items.append((idx, key, item))
                idx += 1

        return self.menu_items

    def render_table(self) -> Table:
        """渲染设置表格"""
        table = Table(show_header=True, show_lines=False)
        table.add_column("ID", style="dim", width=4)
        table.add_column(self.i18n.get("label_setting_name"))
        table.add_column(self.i18n.get("label_value"), style="cyan")

        current_level = None

        for idx, key, item in self.menu_items:
            # 添加分隔线（层级变化时）
            if current_level != item.level:
                if current_level is not None:
                    table.add_section()
                current_level = item.level

            # 获取显示名称
            name = self.i18n.get(item.i18n_key) if item.i18n_key else key
            name += get_level_suffix(item.level)

            # 获取当前值
            value = self.config.get(key, item.default)
            display_value = format_config_value(key, value, self.config)

            table.add_row(str(idx), name, display_value)

        return table

    def get_item_by_id(self, choice_id: int):
        """根据选择ID获取配置项"""
        for idx, key, item in self.menu_items:
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

        # 高级配置需要二次确认
        if self.requires_confirmation(key):
            console.print(f"[yellow]⚠ {self.i18n.get('warning_advanced_setting')}[/yellow]")
            if not Confirm.ask(self.i18n.get('confirm_modify_advanced')):
                return None

        # 根据类型处理输入
        if item.config_type == ConfigType.BOOL:
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
        else:
            return Prompt.ask(
                self.i18n.get(item.i18n_key),
                default=str(current)
            )
