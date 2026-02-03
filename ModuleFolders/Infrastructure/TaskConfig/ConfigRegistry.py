"""
配置注册表 - 集中管理所有配置项的元数据

配置层级:
- SYSTEM: 系统级，不可见不可改（内部逻辑用）
- ADVANCED: 高级用户可见可改（需要理解后果）
- USER: 普通用户可见可改（安全的常用配置）
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional, Callable


class ConfigLevel(Enum):
    """配置层级"""
    SYSTEM = 0      # 系统级：不可见，不可改
    ADVANCED = 1    # 高级：可见，需谨慎修改
    USER = 2        # 用户级：可见，安全修改


class ConfigType(Enum):
    """配置值类型"""
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    PATH = "path"
    CHOICE = "choice"  # 枚举选择


@dataclass
class ConfigItem:
    """配置项定义"""
    key: str                                    # 配置键名
    default: Any                                # 默认值
    level: ConfigLevel                          # 配置层级
    config_type: ConfigType                     # 值类型
    i18n_key: str = ""                          # 国际化键名（用于显示名称）
    i18n_desc_key: str = ""                     # 国际化键名（用于描述）
    choices: list = field(default_factory=list) # 可选值（用于 CHOICE 类型）
    min_value: Optional[float] = None           # 最小值（用于数值类型）
    max_value: Optional[float] = None           # 最大值（用于数值类型）
    validator: Optional[Callable] = None        # 自定义验证函数
    depends_on: Optional[str] = None            # 依赖的配置项
    category: str = "general"                   # 配置分类


# ============================================================
# 配置注册表
# ============================================================

CONFIG_REGISTRY: dict[str, ConfigItem] = {}


def register_config(item: ConfigItem):
    """注册配置项"""
    CONFIG_REGISTRY[item.key] = item
    return item


def get_config_item(key: str) -> Optional[ConfigItem]:
    """获取配置项定义"""
    return CONFIG_REGISTRY.get(key)


def get_default_value(key: str) -> Any:
    """获取配置项默认值"""
    item = CONFIG_REGISTRY.get(key)
    return item.default if item else None


def get_configs_by_level(level: ConfigLevel) -> list[ConfigItem]:
    """获取指定层级的所有配置项"""
    return [item for item in CONFIG_REGISTRY.values() if item.level == level]


def get_configs_by_category(category: str) -> list[ConfigItem]:
    """获取指定分类的所有配置项"""
    return [item for item in CONFIG_REGISTRY.values() if item.category == category]


def is_user_visible(key: str) -> bool:
    """判断配置是否对用户可见"""
    item = CONFIG_REGISTRY.get(key)
    if not item:
        return False
    return item.level in (ConfigLevel.USER, ConfigLevel.ADVANCED)


def is_user_editable(key: str, is_advanced_user: bool = False) -> bool:
    """判断配置是否可被用户编辑"""
    item = CONFIG_REGISTRY.get(key)
    if not item:
        return False
    if item.level == ConfigLevel.SYSTEM:
        return False
    if item.level == ConfigLevel.ADVANCED:
        return is_advanced_user
    return True


# ============================================================
# 注册所有配置项
# ============================================================

# --- 路径配置 (USER) ---
register_config(ConfigItem(
    key="label_input_path",
    default="",
    level=ConfigLevel.USER,
    config_type=ConfigType.PATH,
    i18n_key="setting_input_path",
    category="path"
))

register_config(ConfigItem(
    key="label_output_path",
    default="",
    level=ConfigLevel.USER,
    config_type=ConfigType.PATH,
    i18n_key="setting_output_path",
    category="path"
))

register_config(ConfigItem(
    key="polishing_output_path",
    default="",
    level=ConfigLevel.USER,
    config_type=ConfigType.PATH,
    i18n_key="setting_polishing_output_path",
    category="path"
))

# --- 语言配置 (USER) ---
register_config(ConfigItem(
    key="source_language",
    default="auto",
    level=ConfigLevel.USER,
    config_type=ConfigType.STRING,
    i18n_key="setting_src_lang",
    category="language"
))

register_config(ConfigItem(
    key="target_language",
    default="Chinese",
    level=ConfigLevel.USER,
    config_type=ConfigType.STRING,
    i18n_key="setting_tgt_lang",
    category="language"
))

# --- 翻译核心配置 (USER) ---
register_config(ConfigItem(
    key="lines_limit",
    default=20,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_lines_limit",
    min_value=1,
    max_value=100,
    category="translation"
))

register_config(ConfigItem(
    key="pre_line_counts",
    default=3,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_pre_line_counts",
    min_value=0,
    max_value=10,
    category="translation"
))

register_config(ConfigItem(
    key="round_limit",
    default=3,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_round_limit",
    min_value=1,
    max_value=10,
    category="translation"
))

register_config(ConfigItem(
    key="retry_count",
    default=3,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_retry_count",
    min_value=0,
    max_value=10,
    category="translation"
))

register_config(ConfigItem(
    key="request_timeout",
    default=60,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_request_timeout",
    min_value=10,
    max_value=600,
    category="translation"
))

register_config(ConfigItem(
    key="user_thread_counts",
    default=0,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_thread_count",
    i18n_desc_key="setting_thread_count_desc",
    min_value=0,
    max_value=100,
    category="translation"
))

# --- 输出配置 (USER) ---
register_config(ConfigItem(
    key="enable_bilingual_output",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_enable_bilingual_output",
    i18n_desc_key="setting_enable_bilingual_output_desc",
    category="output"
))

register_config(ConfigItem(
    key="bilingual_text_order",
    default="translation_first",
    level=ConfigLevel.USER,
    config_type=ConfigType.CHOICE,
    i18n_key="setting_bilingual_order",
    choices=["translation_first", "source_first"],
    depends_on="enable_bilingual_output",
    category="output"
))

register_config(ConfigItem(
    key="output_filename_suffix",
    default="",
    level=ConfigLevel.USER,
    config_type=ConfigType.STRING,
    i18n_key="setting_output_suffix",
    category="output"
))

register_config(ConfigItem(
    key="keep_original_encoding",
    default=True,
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.BOOL,
    i18n_key="setting_keep_encoding",
    i18n_desc_key="setting_keep_encoding_desc",
    category="output"
))

# --- 功能开关 (USER) ---
register_config(ConfigItem(
    key="enable_retry",
    default=True,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_enable_retry",
    category="feature"
))

register_config(ConfigItem(
    key="auto_set_output_path",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_auto_set_output_path",
    category="feature"
))

register_config(ConfigItem(
    key="response_conversion_toggle",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_response_conversion_toggle",
    i18n_desc_key="setting_response_conversion_toggle_desc",
    category="feature"
))

register_config(ConfigItem(
    key="opencc_preset",
    default="s2twp.json",
    level=ConfigLevel.USER,
    config_type=ConfigType.CHOICE,
    i18n_key="setting_opencc_preset",
    choices=["s2t.json", "t2s.json", "s2tw.json", "tw2s.json", "s2twp.json", "tw2sp.json"],
    depends_on="response_conversion_toggle",
    category="feature"
))

register_config(ConfigItem(
    key="enable_cache_backup",
    default=True,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_cache_backup",
    category="feature"
))

register_config(ConfigItem(
    key="cache_backup_limit",
    default=10,
    level=ConfigLevel.USER,
    config_type=ConfigType.INT,
    i18n_key="setting_cache_backup_limit",
    min_value=1,
    max_value=50,
    depends_on="enable_cache_backup",
    category="feature"
))

register_config(ConfigItem(
    key="enable_auto_restore_ebook",
    default=True,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_auto_restore_ebook",
    category="feature"
))

# --- 提示词功能开关 (USER) ---
register_config(ConfigItem(
    key="pre_translation_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_pre_translation_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="post_translation_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_post_translation_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="prompt_dictionary_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_prompt_dictionary_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="exclusion_list_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_exclusion_list_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="characterization_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_characterization_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="world_building_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_world_building_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="writing_style_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_writing_style_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="translation_example_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_translation_example_switch",
    category="prompt_feature"
))

register_config(ConfigItem(
    key="few_shot_and_example_switch",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_few_shot_and_example_switch",
    category="prompt_feature"
))

# --- 数据存储 (SYSTEM) - 不对用户显示 ---
register_config(ConfigItem(
    key="pre_translation_data",
    default={},
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.DICT,
    category="data"
))

register_config(ConfigItem(
    key="post_translation_data",
    default={},
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.DICT,
    category="data"
))

register_config(ConfigItem(
    key="prompt_dictionary_data",
    default=[],
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.LIST,
    category="data"
))

register_config(ConfigItem(
    key="exclusion_list_data",
    default=[],
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.LIST,
    category="data"
))

register_config(ConfigItem(
    key="characterization_data",
    default=[],
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.LIST,
    category="data"
))

register_config(ConfigItem(
    key="translation_example_data",
    default=[],
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.LIST,
    category="data"
))

# --- API故障转移 (ADVANCED) ---
register_config(ConfigItem(
    key="enable_api_failover",
    default=False,
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.BOOL,
    i18n_key="setting_enable_api_failover",
    category="api"
))

register_config(ConfigItem(
    key="api_failover_threshold",
    default=3,
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.INT,
    i18n_key="setting_failover_threshold",
    min_value=1,
    max_value=10,
    depends_on="enable_api_failover",
    category="api"
))

register_config(ConfigItem(
    key="backup_apis",
    default=[],
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.LIST,
    category="api"
))

# --- 响应检查 (ADVANCED) ---
register_config(ConfigItem(
    key="response_check_switch",
    default={
        "newline_character_count_check": False,
        "return_to_original_text_check": False,
        "residual_original_text_check": False,
        "reply_format_check": False,
    },
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.DICT,
    i18n_key="setting_response_check",
    category="response_check"
))

# --- 其他功能开关 (USER) ---
register_config(ConfigItem(
    key="enable_retry_backoff",
    default=True,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_retry_backoff",
    category="feature"
))

register_config(ConfigItem(
    key="enable_session_logging",
    default=True,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_session_logging",
    category="feature"
))

register_config(ConfigItem(
    key="enable_task_notification",
    default=True,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_task_notification",
    category="feature"
))

register_config(ConfigItem(
    key="show_detailed_logs",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="setting_detailed_logs",
    category="feature"
))

register_config(ConfigItem(
    key="auto_process_text_code_segment",
    default=False,
    level=ConfigLevel.USER,
    config_type=ConfigType.BOOL,
    i18n_key="feature_auto_process_text_code_segment",
    category="prompt_feature"
))

# --- 高级配置 (ADVANCED) ---
register_config(ConfigItem(
    key="enable_smart_round_limit",
    default=False,
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.BOOL,
    i18n_key="setting_enable_smart_round_limit",
    i18n_desc_key="setting_enable_smart_round_limit_desc",
    category="advanced"
))

register_config(ConfigItem(
    key="enable_dry_run",
    default=False,
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.BOOL,
    i18n_key="setting_dry_run",
    i18n_desc_key="setting_dry_run_desc",
    category="advanced"
))

register_config(ConfigItem(
    key="tokens_limit_switch",
    default=False,
    level=ConfigLevel.ADVANCED,
    config_type=ConfigType.BOOL,
    i18n_key="setting_tokens_limit_switch",
    i18n_desc_key="setting_tokens_limit_switch_desc",
    category="advanced"
))

# --- 系统级配置 (SYSTEM) - 不对用户显示 ---
register_config(ConfigItem(
    key="translation_project",
    default="AutoType",
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.STRING,
    category="system"
))

register_config(ConfigItem(
    key="actual_thread_counts",
    default=3,
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.INT,
    category="system"
))

register_config(ConfigItem(
    key="apikey_list",
    default=[],
    level=ConfigLevel.SYSTEM,
    config_type=ConfigType.LIST,
    category="system"
))


# ============================================================
# 辅助函数
# ============================================================

def generate_default_config() -> dict:
    """生成包含所有配置默认值的字典"""
    return {item.key: item.default for item in CONFIG_REGISTRY.values()}


def get_user_visible_configs() -> list[ConfigItem]:
    """获取用户可见的所有配置项"""
    return [
        item for item in CONFIG_REGISTRY.values()
        if item.level in (ConfigLevel.USER, ConfigLevel.ADVANCED)
    ]


def get_categories() -> list[str]:
    """获取所有配置分类"""
    return list(set(item.category for item in CONFIG_REGISTRY.values()))


def validate_config_value(key: str, value: Any) -> tuple[bool, str]:
    """
    验证配置值是否合法
    返回: (是否合法, 错误信息)
    """
    item = CONFIG_REGISTRY.get(key)
    if not item:
        return True, ""  # 未注册的配置不验证

    # 类型检查
    if item.config_type == ConfigType.INT:
        if not isinstance(value, int):
            return False, f"配置 {key} 必须是整数"
        if item.min_value is not None and value < item.min_value:
            return False, f"配置 {key} 不能小于 {item.min_value}"
        if item.max_value is not None and value > item.max_value:
            return False, f"配置 {key} 不能大于 {item.max_value}"

    elif item.config_type == ConfigType.BOOL:
        if not isinstance(value, bool):
            return False, f"配置 {key} 必须是布尔值"

    elif item.config_type == ConfigType.CHOICE:
        if value not in item.choices:
            return False, f"配置 {key} 必须是 {item.choices} 之一"

    # 自定义验证
    if item.validator:
        try:
            if not item.validator(value):
                return False, f"配置 {key} 验证失败"
        except Exception as e:
            return False, f"配置 {key} 验证出错: {e}"

    return True, ""
