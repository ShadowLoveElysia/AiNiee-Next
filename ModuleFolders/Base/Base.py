import os
import logging
import threading
import traceback
import queue

import rapidjson as json
from rich import print as rich_print
from rich.console import RenderableType
from ModuleFolders.Base.EventManager import EventManager
from ModuleFolders.Infrastructure.LLMRequester.SdkRequestMode import sync_sdk_request_mode_config
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import (
    load_effective_config,
    save_effective_config,
)


class TUIHandler(logging.Handler):
    """自定义 logging.Handler，将日志发射到 TUI 的 TaskUI 实例"""

    # 类级别的全局实例引用
    _instance = None
    _ui = None
    _file_handler = None

    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter('%(message)s'))

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_ui(cls, ui):
        """设置 TaskUI 实例"""
        cls._ui = ui

    @classmethod
    def set_file(cls, file_handle):
        """设置日志文件句柄"""
        cls._file_handler = file_handle

    @classmethod
    def clear(cls):
        """清理 UI 和文件引用"""
        cls._ui = None
        cls._file_handler = None

    def emit(self, record):
        try:
            # 检查是否是 rich 可渲染对象（如 Table, Panel 等）
            if isinstance(record.msg, RenderableType) and not isinstance(record.msg, str):
                # 直接用 rich_print 渲染，不转成字符串
                if self._ui is not None and hasattr(self._ui, 'log'):
                    self._ui.log(record.msg)
                else:
                    rich_print(record.msg)
                return

            msg = self.format(record)
            if not msg:
                return

            # 根据日志级别添加 rich 标签
            level = record.levelno
            if level >= logging.ERROR:
                formatted = f"[[red]{record.levelname}[/]] {msg}"
            elif level >= logging.WARNING:
                formatted = f"[[yellow]{record.levelname}[/]] {msg}"
            elif level >= logging.INFO:
                formatted = f"[[green]{record.levelname}[/]] {msg}"
            else:  # DEBUG
                formatted = f"[[yellow]DEBUG[/]] {msg}"

            # 发送到 TUI
            if self._ui is not None and hasattr(self._ui, 'log'):
                self._ui.log(formatted)
            else:
                # 回退到 rich print
                rich_print(formatted)

        except Exception:
            self.handleError(record)


def get_logger(name: str = "ainiee") -> logging.Logger:
    """获取配置好的 logger 实例"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(TUIHandler.get_instance())
        logger.setLevel(logging.DEBUG)
    return logger


# 事件列表
class Event():

    API_TEST_DONE = 100                             # API 测试完成
    API_TEST_START = 101                            # API 测试开始
    TASK_START = 210                         # 翻译开始
    TASK_UPDATE = 220                        # 翻译状态更新
    TASK_STOP = 230                          # 翻译停止
    TASK_STOP_DONE = 231                     # 翻译停止完成
    TASK_COMPLETED = 232                          # 翻译完成

    TASK_CONTINUE_CHECK = 240                # 继续翻译状态检查
    TASK_CONTINUE_CHECK_DONE = 241           # 继续翻译状态检查完成
    TASK_MANUAL_EXPORT = 250                 # 翻译结果手动导出
    TASK_MANUAL_SAVE_CACHE = 251             # 手动保存缓存文件
    TASK_API_STATUS_REPORT = 260             # API 状态报告
    TUI_SOURCE_DATA = 261                    # TUI 数据传输: 原文
    TUI_RESULT_DATA = 262                    # TUI 数据传输: 译文
    CACHE_FILE_AUTO_SAVE = 300                      # 缓存文件自动保存
    SYSTEM_STATUS_UPDATE = 310               # 系统状态更新 (用于 TUI)

    APP_UPDATE_CHECK: int = 600                             # 检查更新
    APP_UPDATE_CHECK_DONE: int = 610                        # 检查更新完成
    APP_UPDATE_DOWNLOAD: int = 620                          # 下载应用
    APP_UPDATE_DOWNLOAD_UPDATE: int = 630                   # 下载应用更新

    GLOSS_TASK_START = 700                           # 术语表翻译 开始
    GLOSS_TASK_DONE = 701                            # 术语表翻译 完成

    TABLE_TRANSLATE_START = 800                      # 表格翻译 开始
    TABLE_TRANSLATE_DONE = 801                       # 表格翻译 完成
    TABLE_POLISH_START = 810                      # 表格润色 开始
    TABLE_POLISH_DONE = 811                      # 表格润色 完成

    TERM_EXTRACTION_START = 830                  # 术语提取开始
    TERM_EXTRACTION_DONE = 831

    TERM_TRANSLATE_SAVE_START = 832              # 实体提取开始
    TERM_TRANSLATE_SAVE_DONE = 833

    TERM_MULTI_TRANSLATE_START = 834             # 术语多翻译开始
    TERM_MULTI_TRANSLATE_DONE = 835              # 术语多翻译完成

    TRANSLATION_CHECK_START = 840                # 语言检查开始

    TABLE_UPDATE = 898                             # 表格更新
    TABLE_FORMAT = 899                             # 表格重排

    APP_SHUT_DOWN = 99999                          # 应用关闭


# 软件运行状态列表
class Status():

    IDLE = 1000                                     # 无任务
    TASKING = 1001                                  # 任务中
    STOPING = 1002                                  # 停止中
    TASKSTOPPED = 1003                              # 任务已停止

    API_TEST = 2000                                 # 接口测试中
    GLOSS_TASK = 3000                               # 术语表翻译中
    TABLE_TASK = 4001                               # 表格任务中


class Base():

    # 事件列表
    EVENT = Event()

    # 状态列表
    STATUS = Status()

    # 配置文件路径
    CONFIG_PATH = os.path.join(".", "Resource", "config.json")

    # 类线程锁
    CONFIG_FILE_LOCK = threading.Lock()

    # 全局输入队列 (用于 TUI 交互)
    global_input_queue = queue.Queue()

    # UI文本翻译
    @classmethod
    def tra(cls, text):
        i18n = getattr(cls, "i18n", None)
        if i18n is not None:
            return i18n.get(text)
        return text

    # 类级别的 logger
    _logger = None

    @classmethod
    def get_logger(cls):
        if cls._logger is None:
            cls._logger = get_logger("ainiee")
        return cls._logger

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # 默认配置
        self.default = {}

        # 获取事件管理器单例
        self.event_manager_singleton = EventManager()

        # 类变量
        Base.work_status = Base.STATUS.IDLE if not hasattr(Base, "work_status") else Base.work_status

    # 检查是否处于调试模式
    def is_debug(self) -> bool:
        if getattr(Base, "_is_debug", None) == None:
            debug_path = os.path.join(".", "debug.txt")
            Base._is_debug = os.path.isfile(debug_path)

        return Base._is_debug

    # 重置调试模式检查状态
    def reset_debug(self) -> None:
        Base._is_debug = None

    # PRINT (保留兼容性，内部转发到 logger)
    def print(self, msg: str) -> None:
        Base.get_logger().info(msg)

    # DEBUG
    def debug(self, msg: str, e: Exception = None) -> None:
        if self.is_debug() is False:
            return None

        if e is None:
            Base.get_logger().debug(msg)
        else:
            Base.get_logger().debug(f"{msg}\n{e}\n{(''.join(traceback.format_exception(None, e, e.__traceback__))).strip()}")

    # INFO
    def info(self, msg: str) -> None:
        Base.get_logger().info(msg)

    # ERROR
    def error(self, msg: str, e: Exception = None) -> None:
        if e is None:
            Base.get_logger().error(msg)
        else:
            Base.get_logger().error(f"{msg}\n{e}\n{(''.join(traceback.format_exception(None, e, e.__traceback__))).strip()}")

    # WARNING
    def warning(self, msg: str) -> None:
        Base.get_logger().warning(msg)

    def get_parent_window(self):
        """Mock method for compatibility"""
        return None

    # Toast replacements - using logger
    def info_toast(self, title: str, content: str) -> None:
        Base.get_logger().info(f"[TOAST] {title}: {content}")

    def error_toast(self, title: str, content: str) -> None:
        Base.get_logger().error(f"[TOAST] {title}: {content}")

    def success_toast(self, title: str, content: str) -> None:
        Base.get_logger().info(f"[TOAST] {title}: {content}")

    def warning_toast(self, title: str, content: str) -> None:
        Base.get_logger().warning(f"[TOAST] {title}: {content}")

    # 载入配置文件
    def load_config(self) -> dict:
        with Base.CONFIG_FILE_LOCK:
            return load_effective_config(create_missing=False)

    # 保存配置文件
    def save_config(self, new: dict) -> None:
        with Base.CONFIG_FILE_LOCK:
            old = load_effective_config(create_missing=False)

            # 对比新旧数据是否一致
            if old == new:
                return old

            # 更新配置数据
            for k, v in new.items():
                old[k] = v
            prefer_sdk_request_mode = "sdk_request_mode" in new
            sync_sdk_request_mode_config(old, prefer_sdk_request_mode=prefer_sdk_request_mode)
            save_effective_config(old, prefer_sdk_request_mode=prefer_sdk_request_mode)

        return old

    # 更新合并配置
    def fill_config(self, old: dict, new: dict) -> dict:
        """深度合并字典"""
        for k, v in new.items():
            if isinstance(v, dict) and k in old:
                # 递归合并子字典
                old[k] = self.fill_config(old[k], v)
            elif k not in old:
                old[k] = v
        return old

    # 用默认值更新并加载配置文件
    def load_config_from_default(self) -> None:
        # 1. 加载已有配置
        config = self.load_config()  # 从文件读取用户配置

        # 2. 合并默认配置
        config = self.fill_config(
            old=config,  # 用户现有配置
            new=getattr(self, "default", {})  # 当前类的默认配置
        )

        # 3. 返回合并结果
        return config

    # 触发事件
    def emit(self, event: int, data: dict) -> None:
        EventManager.get_singleton().emit(event, data)

    # 订阅事件
    def subscribe(self, event: int, hanlder: callable) -> None:
        EventManager.get_singleton().subscribe(event, hanlder)

    # 取消订阅事件
    def unsubscribe(self, event: int, hanlder: callable) -> None:
        EventManager.get_singleton().unsubscribe(event, hanlder)
