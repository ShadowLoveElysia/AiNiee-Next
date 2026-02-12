import os
import sys

# Silence TF and other C++ logs that break TUI
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'

import re
import time
import signal
import threading
import warnings
import locale
import collections
import glob
import rapidjson as json
import shutil
import subprocess
import argparse
import threading
import requests
import traceback
from datetime import datetime

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TimeElapsedColumn, SpinnerColumn
from rich import print
from rich.text import Text
from rich.align import Align

warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from ModuleFolders.Infrastructure.Tokener.TiktokenLoader import initialize_tiktoken
import ModuleFolders.Infrastructure.Tokener.TiktokenLoader as TiktokenLoaderModule
import ModuleFolders.Domain.FileReader.ReaderUtil as ReaderUtilModule
TiktokenLoaderModule._SUPPRESS_OUTPUT = True
ReaderUtilModule._SUPPRESS_OUTPUT = True
try: initialize_tiktoken()
except Exception: pass

from ModuleFolders.Base.Base import Base, TUIHandler
from ModuleFolders.Base.PluginManager import PluginManager
from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
from ModuleFolders.Domain.FileReader.FileReader import FileReader
from ModuleFolders.Domain.FileOutputer.FileOutputer import FileOutputer
from ModuleFolders.Service.SimpleExecutor.SimpleExecutor import SimpleExecutor
from ModuleFolders.Service.TaskExecutor.TaskExecutor import TaskExecutor
from ModuleFolders.Infrastructure.Update.UpdateManager import UpdateManager
from ModuleFolders.Infrastructure.TaskConfig.SettingsRenderer import SettingsMenuBuilder
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
from ModuleFolders.UserInterface.Editor import TUIEditor
from ModuleFolders.Diagnostic import SmartDiagnostic, DiagnosticFormatter
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Service.HttpService.HttpService import HttpService
from ModuleFolders.UserInterface.FileSelector import FileSelector
from ModuleFolders.UserInterface.InputListener import InputListener
from ModuleFolders.UserInterface.TaskUI import TaskUI
from ModuleFolders.UserInterface.APIManager import APIManager
from ModuleFolders.UserInterface.GlossaryMenu import GlossaryMenu
from ModuleFolders.CLI.OperationLogger import OperationLogger, log_operation



console = Console()

# 角色介绍与翻译示例的校验键值对
FEATURE_REQUIRED_KEYS = {
    "characterization_data": {"original_name", "translated_name", "gender", "age", "personality", "speech_style", "additional_info"},
    "translation_example_data": {"src", "dst"}
}

class I18NLoader:
    def __init__(self, lang="en"):
        self.lang, self.data = lang, {}
        self.load_language(lang)
    def load_language(self, lang):
        path = os.path.join(PROJECT_ROOT, "I18N", f"{lang}.json")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: self.data = json.load(f)
        elif lang != "en": self.load_language("en")
    def get(self, key): return self.data.get(key, key)

config_path = os.path.join(PROJECT_ROOT, "Resource", "config.json")
config = {}
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f: config = json.load(f)

saved_lang = config.get("interface_language")
config_path = os.path.join(PROJECT_ROOT, "Resource", "config.json")
config = {}
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f: config = json.load(f)

saved_lang = config.get("interface_language")
current_lang = saved_lang or (lambda: "zh_CN" if (l := locale.getdefaultlocale()[0]) and l.startswith("zh") else "ja" if l and l.startswith("ja") else "en")()
i18n = I18NLoader(current_lang)
Base.i18n = i18n # Make I18N globally accessible

def mask_key(key):
    if not key: return ""
    if len(key) <= 5: return key[:1] + "***" + key[-1:]
    return key[:2] + "***" + key[-3:]

def open_in_editor(file_path):
    try:
        if sys.platform == 'win32':
            os.startfile(file_path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', file_path])
        else:
            subprocess.run(['xdg-open', file_path])
        return True
    except Exception as e:
        console.print(f"[red]Failed to open editor: {e}[/red]")
        return False


# ============================================================
# Calibre 辅助函数 - 调用批量电子书整合.py中的实现
# ============================================================
from importlib import import_module as _import_module
_ebook_module = _import_module("批量电子书整合")
_getCalibreToolPath = _ebook_module.getCalibreToolPath
_ensureCalibreTool = _ebook_module.ensureCalibreTool

def _get_calibre_lang_code():
    """将当前语言转换为批量电子书整合.py使用的语言代码"""
    lang_map = {"zh_CN": "zh", "ja": "ja", "en": "en"}
    return lang_map.get(current_lang, "en")

def ensure_calibre_available(tool_name="ebook-convert.exe"):
    """确保Calibre可用，如果不可用则询问用户是否下载"""
    return _ensureCalibreTool(tool_name, _get_calibre_lang_code(), isInteractive=True)


class WebLogger:
    def __init__(self, stream=None, show_detailed=False):
        self.last_stats_time = 0
        self.stream = stream or sys.__stdout__
        self.show_detailed = show_detailed
        self.internal_api_url = os.environ.get("AINIEE_INTERNAL_API_URL")
        self.current_source = ""
        self._last_result_time = 0

    def _push_to_web(self, source, translation):
        if not self.internal_api_url: return
        try:
            import httpx
            # 同步发送，但在本地网络下通常极快
            httpx.post(f"{self.internal_api_url}/api/internal/update_comparison", 
                      json={"source": source, "translation": translation},
                      timeout=1.0)
        except: pass

    def log(self, msg):
        # 1. 预处理：将对象转为字符串
        if not isinstance(msg, str):
            from io import StringIO
            with StringIO() as buf:
                temp_console = Console(file=buf, force_terminal=True, width=120)
                temp_console.print(msg)
                msg_str = buf.getvalue()
        else:
            msg_str = msg

        # 2. 拦截实时对照信号
        if "<<<RAW_RESULT>>>" in msg_str:
            if not self.show_detailed: return
            if time.time() - self._last_result_time < 0.5: return
            try:
                data = msg_str.split("<<<RAW_RESULT>>>")[1].strip()
                if data:
                    self._push_to_web(self.current_source, data)
            except: pass
            return

        if msg_str:
            # Strip rich markup for web log stream
            clean = re.sub(r'\[/?[a-zA-Z\s]+\]', '', msg_str)
            try:
                # 确保写入并换行
                self.stream.write(clean.strip() + '\n')
                self.stream.flush()
            except: pass

    def on_source_data(self, event, data):
        """Web 模式下同步原文，用于后续对照发送"""
        if not self.show_detailed: return
        if not isinstance(data, dict): return
        self.current_source = str(data.get("data", ""))

    def on_result_data(self, event, data):
        """Web 模式下接收到译文数据包，推送至 WebServer"""
        if not self.show_detailed: return
        if not isinstance(data, dict): return
        raw_content = str(data.get("data", ""))
        source_content = data.get("source")
        if not raw_content and not source_content: return
        
        if source_content:
            self.current_source = str(source_content)
        
        if raw_content:
            self._push_to_web(self.current_source, raw_content)
            self._last_result_time = time.time()

    def update_progress(self, event, data):
        if not data or not isinstance(data, dict): return

        if time.time() - self.last_stats_time < 0.5:
            return
        self.last_stats_time = time.time()

        d = data
        completed = d.get("line", 0)
        total = d.get("total_line", 1)
        tokens = d.get("token", 0)
        elapsed = d.get("time", 0)
        
        # Success/Error Rate
        total_req = d.get("total_requests", 0)
        success_req = d.get("success_requests", 0)
        error_req = d.get("error_requests", 0)
        
        s_rate = (success_req / total_req * 100) if total_req > 0 else 0
        e_rate = (error_req / total_req * 100) if total_req > 0 else 0
        
        # Use session tokens for TPM calculation if available (Resume Fix)
        calc_tokens = d.get("session_token", tokens)
        calc_requests = d.get("session_requests", d.get("total_requests", 0))
        
        rpm = (calc_requests / (elapsed / 60)) if elapsed > 0 else 0
        tpm_k = (calc_tokens / (elapsed / 60) / 1000) if elapsed > 0 else 0
        
        try:
            self.stream.write(f"[STATS] RPM: {rpm:.2f} | TPM: {tpm_k:.2f}k | Progress: {completed}/{total} | Tokens: {tokens} | S-Rate: {s_rate:.1f}% | E-Rate: {e_rate:.1f}%\n")
            self.stream.flush()
        except: pass

    def update_status(self, event, data):
        pass

class CLIMenu:
    def __init__(self):
        self.root_config_path = os.path.join(PROJECT_ROOT, "Resource", "config.json")
        self.profiles_dir = os.path.join(PROJECT_ROOT, "Resource", "profiles")
        self.rules_profiles_dir = os.path.join(PROJECT_ROOT, "Resource", "rules_profiles")
        os.makedirs(self.rules_profiles_dir, exist_ok=True)
        
        self.config = {}
        self.root_config = {}
        self.active_profile_name = "default"
        self.active_rules_profile_name = "default"
        self.load_config()

        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins_from_directory(os.path.join(PROJECT_ROOT, "PluginScripts"))
        
        # 同步插件启用状态
        if "plugin_enables" in self.root_config:
            self.plugin_manager.update_plugins_enable(self.root_config["plugin_enables"])
            
        self.file_reader, self.file_outputer, self.cache_manager = FileReader(), FileOutputer(), CacheManager()
        self.simple_executor = SimpleExecutor()
        self.task_executor = TaskExecutor(self.plugin_manager, self.cache_manager, self.file_reader, self.file_outputer)
        self.file_selector = FileSelector(i18n)
        self.update_manager = UpdateManager(i18n)
        
        # 输入监听器
        self.input_listener = InputListener()

        # 全局属性供子模块使用
        self.PROJECT_ROOT = PROJECT_ROOT
        self.i18n = i18n

        # 加载 Base 翻译库以供子模块 (Dry Run等) 使用
        Base.current_interface_language = "简中" if current_lang == "zh_CN" else "日语" if current_lang == "ja" else "英语"
        Base.multilingual_interface_dict = Base.load_translations(Base, os.path.join(PROJECT_ROOT, "Resource", "Localization"))

        signal.signal(signal.SIGINT, self.signal_handler)
        self.task_running, self.original_print = False, Base.print
        self.web_server_thread = None

        # 操作记录器 (必须在 _check_web_server_dist 之前初始化，因为 display_banner 会使用它)
        self.operation_logger = OperationLogger()
        if self.config.get("enable_operation_logging", False):
            self.operation_logger.enable()

        # 智能诊断模块
        self.smart_diagnostic = SmartDiagnostic(lang=current_lang)
        self._api_error_count = 0  # API错误计数
        self._api_error_messages = []  # 存储最近的API错误信息
        self._show_diagnostic_hint = False  # 是否显示诊断提示

        # --- WebServer 独立检测 (必须在 operation_logger 和 smart_diagnostic 之后) ---
        self._check_web_server_dist()
        self._api_error_count = 0  # API错误计数
        self._api_error_messages = []  # 存储最近的API错误信息
        self._show_diagnostic_hint = False  # 是否显示诊断提示

        # API管理器
        self.api_manager = APIManager(self)

        # 术语/规则菜单
        self.glossary_menu = GlossaryMenu(self)

    def _check_web_server_dist(self):
        """检查 WebServer 编译产物是否存在"""
        dist_path = os.path.join(PROJECT_ROOT, "Tools", "WebServer", "dist", "index.html")
        if not os.path.exists(dist_path):
            self.display_banner()
            self.update_manager.setup_web_server()

        # 队列日志监控相关
        self._last_queue_log_size = 0
        self._queue_log_monitor_thread = None
        self._queue_log_monitor_running = False

    def handle_monitor_shortcut(self):
        """Handle the 'm' shortcut to open the web monitor."""
        # Detect Local IP
        local_ip = "127.0.0.1"
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except: pass

        if self.web_server_thread is None or not self.web_server_thread.is_alive():
            # Start server in background
            try:
                from Tools.WebServer.web_server import run_server
                import Tools.WebServer.web_server as ws_module

                # Setup handlers (same as in start_web_server)
                ws_module.profile_handlers['create'] = self._host_create_profile
                ws_module.profile_handlers['rename'] = self._host_rename_profile
                ws_module.profile_handlers['delete'] = self._host_delete_profile

                webserver_port = self.config.get("webserver_port", 8000)
                self.web_server_thread = run_server(host="0.0.0.0", port=webserver_port, monitor_mode=True)

                # 设置环境变量，让后续启动的翻译任务能推送数据到这个webserver
                os.environ["AINIEE_INTERNAL_API_URL"] = f"http://127.0.0.1:{webserver_port}"

                Base.print(f"[bold green]{i18n.get('msg_web_server_started_bg')}[/bold green]")
                Base.print(f"[cyan]您可以通过 http://{local_ip}:{webserver_port} 访问网页监控面板[/cyan]")
                
                # Signal TUI takeover if running
                if self.task_running and hasattr(self, "ui") and isinstance(self.ui, TaskUI):
                    self.ui.web_task_manager = ws_module.task_manager
                    self.ui._server_ip = local_ip

                # Always establish web_task_manager connection when server starts
                if hasattr(self, "ui") and self.ui:
                    self.ui.web_task_manager = ws_module.task_manager
                    self.ui._server_ip = local_ip
                    
                    # Push existing logs to web task manager
                    with self.ui._lock:
                        for log_item in self.ui.logs:
                            # Strip existing local timestamp from historical logs
                            # Usually starts with "[HH:MM:SS] "
                            clean_hist = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s+', '', log_item.plain)
                            ws_module.task_manager.push_log(clean_hist)

                    self.ui.taken_over = True
                    self.ui.update_progress(None, {}) # Force UI refresh
            except Exception as e:
                Base.print(f"[red]Failed to start Web Server: {e}[/red]")
                return

        import webbrowser
        # Pass mode=monitor as a query parameter
        webbrowser.open(f"http://127.0.0.1:8000/?mode=monitor#/monitor")

    def handle_queue_editor_shortcut(self):
        """Handle the 'e' shortcut for TUI queue management."""
        try:
            from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
            qm = QueueManager()

            if not qm.tasks:
                self.ui.log(f"[yellow]{i18n.get('msg_queue_empty_cannot_edit')}[/yellow]")
                return

            # 显示队列状态
            self.ui.log(f"[cyan]{i18n.get('msg_queue_status_display')}[/cyan]")
            self.show_queue_status(qm)

            # 显示TUI编辑限制提示
            self.ui.log(f"[yellow]{i18n.get('msg_tui_edit_limitation')}[/yellow]")
            self.ui.log(f"[dim]{i18n.get('msg_use_h_key_for_web')}[/dim]")

        except Exception as e:
            self.ui.log(f"[red]Failed to handle queue editor: {e}[/red]")


    def handle_web_queue_shortcut(self):
        """Handle the 'h' shortcut to open the WebUI queue management page."""
        try:
            self.ui.log(f"[cyan]{i18n.get('msg_queue_web_opening')}[/cyan]")
            self.ensure_web_server_running()
            self.open_queue_page()
        except Exception as e:
            self.ui.log(f"[red]Failed to open web queue manager: {e}[/red]")

    def start_queue_log_monitor(self):
        """启动队列日志监控"""
        if self._queue_log_monitor_running:
            return

        self._queue_log_monitor_running = True
        self._queue_log_monitor_thread = threading.Thread(
            target=self._queue_log_monitor_loop,
            daemon=True
        )
        self._queue_log_monitor_thread.start()

    def stop_queue_log_monitor(self):
        """停止队列日志监控"""
        self._queue_log_monitor_running = False
        if self._queue_log_monitor_thread and self._queue_log_monitor_thread.is_alive():
            self._queue_log_monitor_thread.join(timeout=1.0)

    def _queue_log_monitor_loop(self):
        """队列日志监控主循环"""
        try:
            from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
            qm = QueueManager()
            log_file = qm.get_queue_log_path()

            while self._queue_log_monitor_running:
                try:
                    if os.path.exists(log_file):
                        current_size = os.path.getsize(log_file)
                        if current_size > self._last_queue_log_size:
                            # 文件有新内容，读取新的日志条目
                            self._display_new_queue_logs(log_file)
                            self._last_queue_log_size = current_size

                    time.sleep(1)  # 每秒检查一次

                except Exception as e:
                    # 监控过程中的错误不应该中断监控
                    pass

        except Exception as e:
            # 如果无法启动监控，静默失败
            pass

    def _parse_and_push_stats(self, stats_line):
        """解析[STATS]行并推送统计数据到webserver"""
        try:
            import re
            stats_data = {}

            # 解析RPM
            rpm_match = re.search(r"RPM:\s*([\d\.]+)", stats_line)
            if rpm_match:
                stats_data["rpm"] = float(rpm_match.group(1))

            # 解析TPM
            tpm_match = re.search(r"TPM:\s*([\d\.]+k?)", stats_line)
            if tpm_match:
                tpm_val = tpm_match.group(1).replace('k', '')
                stats_data["tpm"] = float(tpm_val)

            # 解析进度
            progress_match = re.search(r"Progress:\s*(\d+)/(\d+)", stats_line)
            if progress_match:
                stats_data["completedProgress"] = int(progress_match.group(1))
                stats_data["totalProgress"] = int(progress_match.group(2))

            # 解析Tokens
            tokens_match = re.search(r"Tokens:\s*(\d+)", stats_line)
            if tokens_match:
                stats_data["totalTokens"] = int(tokens_match.group(1))
            
            # 解析成功率和错误率
            s_rate_match = re.search(r"S-Rate:\s*([\d\.]+)%", stats_line)
            if s_rate_match:
                stats_data["successRate"] = float(s_rate_match.group(1))
            
            e_rate_match = re.search(r"E-Rate:\s*([\d\.]+)%", stats_line)
            if e_rate_match:
                stats_data["errorRate"] = float(e_rate_match.group(1))

            # 推送统计数据
            if stats_data:
                self._push_stats_to_webserver(stats_data)

        except Exception:
            # 解析失败时静默处理
            pass

    def _push_stats_to_webserver(self, stats_data):
        """推送统计数据到webserver"""
        try:
            response = requests.post(
                "http://127.0.0.1:8000/api/internal/update_stats",
                json=stats_data,
                timeout=1.0
            )
            return response.status_code == 200
        except Exception:
            return False

    def _push_log_to_webserver(self, message, log_type="info"):
        """推送日志消息到webserver"""
        try:
            response = requests.post(
                "http://127.0.0.1:8000/api/internal/push_log",
                json={"message": message, "type": log_type},
                timeout=1.0
            )
            return response.status_code == 200
        except Exception:
            return False

    def _display_new_queue_logs(self, log_file):
        """显示新的队列日志条目并推送数据到webserver"""
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(self._last_queue_log_size)
                new_content = f.read()

            if new_content.strip():
                lines = new_content.strip().split('\n')
                for line in lines:
                    if line.strip():
                        # 移除时间戳前缀，只显示消息内容
                        if '] ' in line and line.startswith('['):
                            message = line.split('] ', 1)[1]
                        else:
                            message = line

                        # 解析统计数据行
                        if "[STATS]" in message:
                            self._parse_and_push_stats(message)

                        # 推送日志消息到webserver
                        self._push_log_to_webserver(message)

                        # 在TUI中显示队列操作日志
                        if hasattr(self, 'ui') and self.ui:
                            self.ui.log(f"[cyan][Queue][/cyan] {message}")

        except Exception as e:
            # 读取日志时出错，静默失败
            pass

    def ensure_web_server_running(self):
        """Ensure web server is running in background, start if needed."""
        # 检查服务器是否已经在运行
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 8000))
            sock.close()

            if result == 0:
                # 服务器已在运行
                self.ui.log(f"[green]{i18n.get('msg_web_server_ready')}[/green]")
                self.start_queue_log_monitor()  # 启动队列日志监控
                return
        except:
            pass

        # 服务器未运行，在后台启动
        try:
            import fastapi
            import uvicorn
        except ImportError:
            self.ui.log("[red]Missing dependencies: fastapi, uvicorn. Cannot start web server.[/red]")
            raise Exception("Missing web server dependencies")

        self.ui.log(f"[cyan]{i18n.get('msg_web_server_starting_background')}[/cyan]")

        # 在后台线程中启动Web服务器
        import threading
        from Tools.WebServer.web_server import run_server

        webserver_port = self.config.get("webserver_port", 8000)
        def start_server():
            try:
                run_server(host="127.0.0.1", port=webserver_port, monitor_mode=False)
            except Exception as e:
                self.ui.log(f"[red]Failed to start web server: {e}[/red]")

        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        # 等待服务器启动
        import time
        for i in range(10):  # 最多等待5秒
            time.sleep(0.5)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('127.0.0.1', 8000))
                sock.close()
                if result == 0:
                    self.ui.log(f"[green]{i18n.get('msg_web_server_ready')}[/green]")

                    # Establish web_task_manager connection
                    try:
                        import Tools.WebServer.web_server as ws_module
                        if hasattr(self, "ui") and self.ui:
                            self.ui.web_task_manager = ws_module.task_manager
                    except Exception as e:
                        self.ui.log(f"[yellow]Warning: Could not establish web connection: {e}[/yellow]")

                    self.start_queue_log_monitor()  # 启动队列日志监控
                    return
            except:
                pass

        # 超时
        self.ui.log(f"[yellow]{i18n.get('msg_web_server_timeout')}[/yellow]")

    def show_queue_status(self, qm):
        """Display current queue status in TUI log."""
        import os

        # 清理过期锁定状态
        if hasattr(qm, 'cleanup_stale_locks'):
            qm.cleanup_stale_locks()

        self.ui.log(f"[bold cyan]═══ {i18n.get('title_queue_status')} ═══[/bold cyan]")

        for i, task in enumerate(qm.tasks):
            # 任务状态颜色
            status_color = "green" if task.status == "completed" else \
                          "yellow" if task.status in ["translating", "polishing"] else \
                          "red" if task.status == "error" else "white"

            # 任务类型简写
            type_str = "T+P" if task.task_type == 4000 else "T" if task.task_type == 1000 else "P"

            # 锁定状态
            lock_icon = "🔒" if (hasattr(qm, 'is_task_actually_processing') and qm.is_task_actually_processing(i)) or task.locked else ""

            # 文件名
            file_name = os.path.basename(task.input_path)

            self.ui.log(f"[{status_color}]{i+1:2d}. [{type_str}] {file_name} - {task.status} {lock_icon}[/{status_color}]")

        self.ui.log(f"[dim]ⓘ {i18n.get('msg_queue_tui_help')}[/dim]")

    def open_queue_page(self):
        """Open the WebUI queue management page in browser."""
        import webbrowser
        # Open queue management page directly
        webbrowser.open("http://127.0.0.1:8000/#/queue")

    def _run_queue_editor(self, queue_manager):
        """运行队列编辑器界面"""
        try:
            # 创建一个简单的队列编辑界面
            from rich.console import Console
            from rich.prompt import IntPrompt, Confirm
            from rich.table import Table
            from rich.panel import Panel

            editor_console = Console()

            def get_localized_status(status):
                status_map = {
                    "waiting": i18n.get("task_status_waiting"),
                    "translating": i18n.get("task_status_translating"),
                    "translated": i18n.get("task_status_translated"),
                    "polishing": i18n.get("task_status_polishing"),
                    "completed": i18n.get("task_status_completed"),
                    "running": i18n.get("task_status_running"),
                    "error": i18n.get("task_status_error"),
                    "stopped": i18n.get("task_status_stopped")
                }
                return status_map.get(status.lower(), status.upper())

            while True:
                # 热重载队列数据
                queue_manager.hot_reload_queue()

                # 清理过期的锁定状态
                if hasattr(queue_manager, 'cleanup_stale_locks'):
                    queue_manager.cleanup_stale_locks()

                # 清屏并显示当前队列状态
                editor_console.clear()
                editor_console.print(Panel.fit(f"[bold cyan]{i18n.get('title_queue_editor')}[/bold cyan]\n{i18n.get('msg_queue_editor_help')}", border_style="cyan"))

                # 显示队列表格
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("#", style="dim", width=3)
                table.add_column(i18n.get('field_status'), width=12)
                table.add_column(i18n.get('field_type'), width=15)
                table.add_column(i18n.get('field_input_path'), width=40)
                table.add_column(i18n.get('field_locked'), width=8, style="red")

                for i, task in enumerate(queue_manager.tasks):
                    status_style = ""
                    if task.status == "completed":
                        status_style = "green"
                    elif task.status == "translating" or task.status == "polishing":
                        status_style = "yellow"
                    elif task.status == "error":
                        status_style = "red"

                    # 使用智能锁定状态检测
                    is_actually_processing = False
                    if hasattr(queue_manager, 'is_task_actually_processing'):
                        is_actually_processing = queue_manager.is_task_actually_processing(i)
                    else:
                        # 降级到传统检测
                        is_actually_processing = task.locked

                    locked_symbol = "🔒" if is_actually_processing else ""

                    # 转换任务类型为可读字符串
                    type_str = "T+P" if task.task_type == 4000 else "T" if task.task_type == 1000 else "P" if task.task_type == 2000 else str(task.task_type)

                    table.add_row(
                        str(i + 1),
                        f"[{status_style}]{get_localized_status(task.status)}[/{status_style}]",
                        type_str,
                        task.input_path[-35:] + "..." if len(task.input_path) > 35 else task.input_path,
                        locked_symbol
                    )

                editor_console.print(table)

                # 显示操作菜单
                editor_console.print(f"\n[bold yellow]{i18n.get('menu_queue_operations')}:[/bold yellow]")
                editor_console.print(f"1. {i18n.get('option_move_up')}")
                editor_console.print(f"2. {i18n.get('option_move_down')}")
                editor_console.print(f"3. {i18n.get('option_remove_task')}")
                editor_console.print(f"4. {i18n.get('option_refresh_queue')}")
                editor_console.print(f"0. {i18n.get('option_return_to_execution')}")

                try:
                    choice = IntPrompt.ask(f"\n{i18n.get('prompt_select_operation')}", console=editor_console, default=0)

                    if choice == 0:
                        break
                    elif choice == 1:  # 上移
                        task_idx = IntPrompt.ask(i18n.get('prompt_enter_task_index'), console=editor_console) - 1
                        if 0 <= task_idx < len(queue_manager.tasks):
                            # 检查任务是否真正被锁定
                            is_locked = False
                            if hasattr(queue_manager, 'is_task_actually_processing'):
                                is_locked = queue_manager.is_task_actually_processing(task_idx)
                            else:
                                is_locked = queue_manager.tasks[task_idx].locked

                            if is_locked:
                                editor_console.print(f"[red]{i18n.get('msg_task_locked_cannot_move')}[/red]")
                            elif queue_manager.move_task_up(task_idx):
                                editor_console.print(f"[green]{i18n.get('msg_task_moved_up')}[/green]")
                            else:
                                editor_console.print(f"[red]{i18n.get('msg_move_failed')}[/red]")
                        else:
                            editor_console.print(f"[red]{i18n.get('msg_invalid_index')}[/red]")
                    elif choice == 2:  # 下移
                        task_idx = IntPrompt.ask(i18n.get('prompt_enter_task_index'), console=editor_console) - 1
                        if 0 <= task_idx < len(queue_manager.tasks):
                            # 检查任务是否真正被锁定
                            is_locked = False
                            if hasattr(queue_manager, 'is_task_actually_processing'):
                                is_locked = queue_manager.is_task_actually_processing(task_idx)
                            else:
                                is_locked = queue_manager.tasks[task_idx].locked

                            if is_locked:
                                editor_console.print(f"[red]{i18n.get('msg_task_locked_cannot_move')}[/red]")
                            elif queue_manager.move_task_down(task_idx):
                                editor_console.print(f"[green]{i18n.get('msg_task_moved_down')}[/green]")
                            else:
                                editor_console.print(f"[red]{i18n.get('msg_move_failed')}[/red]")
                        else:
                            editor_console.print(f"[red]{i18n.get('msg_invalid_index')}[/red]")
                    elif choice == 3:  # 删除任务
                        task_idx = IntPrompt.ask(i18n.get('prompt_enter_task_index'), console=editor_console) - 1
                        if 0 <= task_idx < len(queue_manager.tasks):
                            task = queue_manager.tasks[task_idx]

                            # 使用智能锁定状态检测
                            is_locked = False
                            if hasattr(queue_manager, 'is_task_actually_processing'):
                                is_locked = queue_manager.is_task_actually_processing(task_idx)
                            else:
                                is_locked = task.locked

                            if is_locked:
                                # 显示更详细的锁定信息
                                status_text = ""
                                if task.status == "translating":
                                    if hasattr(task, 'task_type') and task.task_type == 4000:
                                        status_text = i18n.get('task_status_all_in_one_cn')
                                    else:
                                        status_text = i18n.get('task_status_translating_cn')
                                elif task.status == "polishing":
                                    status_text = i18n.get('task_status_polishing_cn')
                                else:
                                    status_text = task.status

                                editor_console.print(f"[red]{i18n.get('msg_task_locked').replace('{}', status_text)}[/red]")
                            else:
                                if Confirm.ask(i18n.get('confirm_remove_task').format(task.input_path), console=editor_console):
                                    if queue_manager.remove_task(task_idx):
                                        editor_console.print(f"[green]{i18n.get('msg_task_removed')}[/green]")
                                    else:
                                        editor_console.print(f"[red]{i18n.get('msg_remove_failed')}[/red]")
                        else:
                            editor_console.print(f"[red]{i18n.get('msg_invalid_index')}[/red]")
                    elif choice == 4:  # 刷新
                        editor_console.print(f"[cyan]{i18n.get('msg_queue_refreshed')}[/cyan]")
                        continue

                    if choice != 4:
                        editor_console.input(f"\n{i18n.get('prompt_press_enter_continue')}")

                except (KeyboardInterrupt, EOFError):
                    break
                except Exception as e:
                    editor_console.print(f"[red]Error: {e}[/red]")
                    editor_console.input(f"\n{i18n.get('prompt_press_enter_continue')}")

            # 返回提示
            if hasattr(self, 'ui') and self.ui:
                self.ui.log(f"[cyan]{i18n.get('msg_queue_editor_closed')}[/cyan]")

        except Exception as e:
            if hasattr(self, 'ui') and self.ui:
                self.ui.log(f"[red]Queue editor error: {e}[/red]")

    def _host_create_profile(self, new_name, base_name=None):
        # Same robust logic as CLI
        if not new_name: raise Exception("Name empty")
        new_path = os.path.join(self.profiles_dir, f"{new_name}.json")
        if os.path.exists(new_path): raise Exception("Exists")
        
        # 1. Preset
        preset = {}
        preset_path = os.path.join(PROJECT_ROOT, "Resource", "platforms", "preset.json")
        if os.path.exists(preset_path):
            with open(preset_path, 'r', encoding='utf-8') as f: preset = json.load(f)
        
        # 2. Base
        base_config = {}
        if not base_name: base_name = self.active_profile_name
        base_path = os.path.join(self.profiles_dir, f"{base_name}.json")
        if os.path.exists(base_path):
            with open(base_path, 'r', encoding='utf-8') as f: base_config = json.load(f)
        
        # 3. Merge
        preset.update(base_config)
        
        # 4. Save
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(preset, f, indent=4, ensure_ascii=False)

    def _host_rename_profile(self, old_name, new_name):
        old_path = os.path.join(self.profiles_dir, f"{old_name}.json")
        new_path = os.path.join(self.profiles_dir, f"{new_name}.json")
        if not os.path.exists(old_path): raise Exception("Not found")
        if os.path.exists(new_path): raise Exception("Target exists")
        
        os.rename(old_path, new_path)
        
        # Update Active if needed
        if self.active_profile_name == old_name:
            self.active_profile_name = new_name
            self.root_config["active_profile"] = new_name
            self.save_config(save_root=True)

    def _host_delete_profile(self, name):
        target = os.path.join(self.profiles_dir, f"{name}.json")
        if not os.path.exists(target): raise Exception("Not found")
        if name == self.active_profile_name: raise Exception("Cannot delete active profile")
        
        # Check count
        cnt = len([f for f in os.listdir(self.profiles_dir) if f.endswith(".json")])
        if cnt <= 1: raise Exception("Cannot delete last profile")
        
        os.remove(target)

    def run_non_interactive(self, args):
        """处理命令行参数，以非交互模式运行任务"""
        # 切换 Profile
        if args.profile:
            self.root_config["active_profile"] = args.profile
            self.save_config(save_root=True)
            self.load_config() # 重新加载配置
            
        if args.rules_profile:
            self.root_config["active_rules_profile"] = args.rules_profile
            self.save_config(save_root=True)
            self.load_config()
        
        # 覆盖基础配置
        if args.source_lang: self.config["source_language"] = args.source_lang
        if args.target_lang: self.config["target_language"] = args.target_lang
        if args.output_path: self.config["label_output_path"] = args.output_path
        if args.project_type: self.config["translation_project"] = args.project_type
        
        # 覆盖并发与重试配置
        if args.threads is not None: self.config["user_thread_counts"] = args.threads
        if args.retry is not None: self.config["retry_count"] = args.retry
        if args.timeout is not None: self.config["request_timeout"] = args.timeout
        if args.rounds is not None: self.config["round_limit"] = args.rounds
        if args.pre_lines is not None: self.config["pre_line_counts"] = args.pre_lines

        # 覆盖切分逻辑
        if args.lines is not None:
            self.config["tokens_limit_switch"] = False
            self.config["lines_limit"] = args.lines
        if args.tokens is not None:
            self.config["tokens_limit_switch"] = True
            self.config["tokens_limit"] = args.tokens

        # 覆盖 API 与平台配置
        if args.platform: self.config["target_platform"] = args.platform
        if args.model: self.config["model"] = args.model
        if args.api_url: self.config["base_url"] = args.api_url
        if args.api_key:
            self.config["api_key"] = args.api_key
            # 同步到具体平台配置中
            tp = self.config.get("target_platform", "")
            if tp and tp in self.config.get("platforms", {}):
                self.config["platforms"][tp]["api_key"] = args.api_key

        # 覆盖高级参数
        if args.think_depth is not None: self.config["think_depth"] = args.think_depth
        if args.thinking_budget is not None: self.config["thinking_budget"] = args.thinking_budget
        if args.failover is not None: self.config["enable_api_failover"] = args.failover == "on"

        self.save_config()

        task_map = {
            'translate': TaskType.TRANSLATION,
            'polish': TaskType.POLISH,
            'all_in_one': TaskType.TRANSLATE_AND_POLISH
        }

        if args.task == 'queue':
            from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
            qm = QueueManager()
            # 检查是否传入了自定义队列文件
            if args.queue_file:
                qm.load_tasks(args.queue_file)
            
            if not qm.tasks:
                    console.print(f"[red]Error: Task queue is empty (File: {qm.queue_file}). Cannot run queue task.[/red]")
                    return
            
            console.print(f"[bold green]Running Task Queue ({len(qm.tasks)} items)...[/bold green]")
            self._is_queue_mode = True  # 标记进入队列模式
            self.start_queue_log_monitor()  # 启动队列日志监控
            qm.start_queue(self)
            # We need to wait for queue to finish if in non-interactive mode
            try:
                while qm.is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                Base.work_status = Base.STATUS.STOPING
            finally:
                self.stop_queue_log_monitor()  # 停止队列日志监控
                self._is_queue_mode = False  # 清除队列模式标记

        elif args.task in task_map:
            if args.task == 'all_in_one':
                # 在非交互模式下，如果传入了 input_path，则使用它
                if args.input_path:
                    # 使用 run_task 组合逻辑，因为 run_all_in_one 内部带 path 选择
                    self.run_task(TaskType.TRANSLATION, target_path=args.input_path, continue_status=args.resume, non_interactive=True, web_mode=args.web_mode, from_queue=True)
                    if Base.work_status != Base.STATUS.STOPING:
                        self.run_task(TaskType.POLISH, target_path=args.input_path, continue_status=True, non_interactive=True, web_mode=args.web_mode)
                else:
                    self.run_all_in_one()
            else:
                self.run_task(
                    task_map[args.task],
                    target_path=args.input_path,
                    continue_status=args.resume,
                    non_interactive=args.non_interactive,
                    web_mode=args.web_mode
                )
        elif args.task == 'export':
            self.run_export_only(
                target_path=args.input_path,
                non_interactive=args.non_interactive
            )


    def _migrate_and_load_profiles(self):
        os.makedirs(self.profiles_dir, exist_ok=True)
        active_profile_path = os.path.join(self.profiles_dir, f"{self.active_profile_name}.json")

        # --- SAFETY CHECK: If custom profile is missing, revert to default ---
        if self.active_profile_name != "default" and not os.path.exists(active_profile_path):
            console.print(f"[bold red]Warning: Active profile '{self.active_profile_name}' not found![/bold red]")
            console.print(f"[yellow]Reverting to 'default' profile to avoid misleading default behavior.[/yellow]")
            
            self.active_profile_name = "default"
            active_profile_path = os.path.join(self.profiles_dir, "default.json") # CRITICAL FIX: Update the path variable!
            
            # Update root config to persist this change
            self.root_config["active_profile"] = "default"
            try:
                with open(self.root_config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.root_config, f, indent=4, ensure_ascii=False)
            except Exception: pass

        # Path to the new master preset file
        master_preset_path = os.path.join(PROJECT_ROOT, "Resource", "platforms", "preset.json")
        
        # Load master preset content once
        master_config_content = {}
        try:
            with open(master_preset_path, 'r', encoding='utf-8') as f:
                master_config_content = json.load(f)
        except Exception as e:
            console.print(f"[red]Error loading master preset from {master_preset_path}: {e}[/red]")
            # Fallback to an empty dict if master preset is unreadable
            master_config_content = {}

        # 2. Load user profile if it exists
        user_config = {}
        profile_exists = os.path.exists(active_profile_path)
        if profile_exists:
            try:
                with open(active_profile_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
            except Exception:
                user_config = {}

        # 3. Merge Settings: Start with base, then overlay user settings
        self.config = master_config_content.copy()
        if isinstance(user_config, dict):
            for k, v in user_config.items():
                if isinstance(v, dict) and k in self.config and isinstance(self.config[k], dict):
                    self.config[k].update(v)
                else:
                    self.config[k] = v

        # 4. Load independent Rules Profile
        rule_keys = [
            "prompt_dictionary_data", "exclusion_list_data", "characterization_data",
            "world_building_content", "writing_style_content", "translation_example_data"
        ]
        
        if self.active_rules_profile_name and self.active_rules_profile_name != "None":
            rules_path = os.path.join(self.rules_profiles_dir, f"{self.active_rules_profile_name}.json")
            if not os.path.exists(rules_path):
                # Create default rules profile if missing
                default_rules = {
                    "prompt_dictionary_data": [], "exclusion_list_data": [], "characterization_data": [],
                    "world_building_content": "", "writing_style_content": "", "translation_example_data": []
                }
                try:
                    with open(rules_path, 'w', encoding='utf-8') as f:
                        json.dump(default_rules, f, indent=4, ensure_ascii=False)
                except: pass
            else:
                try:
                    with open(rules_path, 'r', encoding='utf-8-sig') as f:
                        rules_data = json.load(f)
                    # Apply rules to current config
                    for rk in rule_keys:
                        if rk in rules_data:
                            self.config[rk] = rules_data[rk]
                except: pass

        # 5. If profile was missing or merged, ensure it's saved to disk
        if not profile_exists or not user_config:
            self.save_config()
            if not profile_exists:
                console.print(f"[green]Initialized new profile '{self.active_profile_name}.json' from preset.[/green]")
        
        # Ensure we also save the latest config state to memory for use
        self.save_config()

    def load_config(self):
        # Load root config
        if os.path.exists(self.root_config_path) and os.path.getsize(self.root_config_path) > 0:
            try:
                with open(self.root_config_path, 'r', encoding='utf-8') as f:
                    self.root_config = json.load(f)
                self.active_profile_name = self.root_config.get("active_profile", "default")
                self.active_rules_profile_name = self.root_config.get("active_rules_profile", "default")
            except (json.JSONDecodeError, UnicodeDecodeError):
                 # This can happen if the root config is the old, large settings file. Trigger migration path.
                 self.active_profile_name = "default"
                 self.active_rules_profile_name = "default"
                 self._migrate_and_load_profiles()
                 return
        else:
            self.active_profile_name = "default"
            self.active_rules_profile_name = "default"
        
        self._migrate_and_load_profiles()

    def save_config(self, save_root=False):
        # 1. Save Settings (Exclude rules)
        active_profile_path = os.path.join(self.profiles_dir, f"{self.active_profile_name}.json")
        os.makedirs(os.path.dirname(active_profile_path), exist_ok=True)
        
        rule_keys = [
            "prompt_dictionary_data", "exclusion_list_data", "characterization_data",
            "world_building_content", "writing_style_content", "translation_example_data"
        ]
        
        settings_to_save = {k: v for k, v in self.config.items() if k not in rule_keys}
        with open(active_profile_path, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)

        # 2. Save Rules
        if self.active_rules_profile_name != "None":
            active_rules_path = os.path.join(self.rules_profiles_dir, f"{self.active_rules_profile_name}.json")
            rules_to_save = {k: v for k, v in self.config.items() if k in rule_keys}
            with open(active_rules_path, 'w', encoding='utf-8') as f:
                json.dump(rules_to_save, f, indent=4, ensure_ascii=False)

        # Optionally save the root config (active profile pointers)
        if save_root:
            with open(self.root_config_path, 'w', encoding='utf-8') as f:
                json.dump(self.root_config, f, indent=4, ensure_ascii=False)

    def _update_recent_projects(self, project_path):
        recent = self.root_config.get("recent_projects", [])
        
        # --- Migration & Cleanup ---
        # Convert any old string-only entries to new object format
        new_recent = []
        for item in recent:
            if isinstance(item, str):
                new_recent.append({"path": item, "profile": "default", "rules_profile": "default"})
            elif isinstance(item, dict) and "path" in item:
                new_recent.append(item)
        
        # Remove current project if it exists in list (compare by path)
        new_recent = [i for i in new_recent if i["path"] != project_path]
        
        # Add current project at start
        new_recent.insert(0, {
            "path": project_path,
            "profile": self.active_profile_name,
            "rules_profile": self.active_rules_profile_name
        })
        
        self.root_config["recent_projects"] = new_recent[:5]
        self.save_config(save_root=True)
    def signal_handler(self, sig, frame):
        if self.task_running:
            if getattr(self, "stop_requested", False):
                console.print("\n[bold red]Force quitting immediately...[/bold red]")
                os._exit(1)

            console.print("\n[yellow]Stopping task... (Press Ctrl+C again to force quit)[/yellow]")
            self.stop_requested = True

            # Immediately set status to stop threads faster
            Base.work_status = Base.STATUS.STOPING

            from ModuleFolders.Base.EventManager import EventManager
            EventManager.get_singleton().emit(Base.EVENT.TASK_STOP, {})
        elif getattr(self, "web_server_active", False):
            # Webserver运行时，抛出KeyboardInterrupt让try-except捕获
            raise KeyboardInterrupt
        else:
            sys.exit(0)

    def _fetch_github_status_async(self):
        """后台异步获取 GitHub 状态信息"""
        self._github_fetch_event = threading.Event()
        self._github_fetch_failed = False

        def fetch():
            try:
                lang = getattr(i18n, 'lang', 'en')
                info = self.update_manager.get_status_bar_info(lang)
                # 检查是否真的获取到了数据
                if info and (info.get("commit_text") or info.get("release_text")):
                    self._cached_github_info = info
                    self._github_fetch_failed = False
                else:
                    self._cached_github_info = None
                    self._github_fetch_failed = True
            except:
                self._cached_github_info = None
                self._github_fetch_failed = True
            finally:
                self._github_fetch_event.set()

        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()

    def display_banner(self):
        # 获取版本号
        v_str = "V0.0.0"
        try:
            v_path = os.path.join(PROJECT_ROOT, "Resource", "Version", "version.json")
            if os.path.exists(v_path):
                with open(v_path, 'r', encoding='utf-8') as f:
                    v_data = json.load(f)
                    v_full = v_data.get("version", "")
                    if 'V' in v_full: v_str = "V" + v_full.split('V')[-1].strip()
        except: pass

        # 整理重要设置状态
        src = self.config.get("source_language", "Unknown")
        tgt = self.config.get("target_language", "Unknown")
        conv_on = self.config.get("response_conversion_toggle", False)
        conv_preset = self.config.get("opencc_preset", "None")
        bilingual_order = self.config.get("bilingual_text_order", "translation_first")
        
        # 简繁纠错逻辑: 如果目标是简体但预设包含 s2t (简转繁)
        is_tgt_simplified = any(k in tgt for k in ["简", "Simplified", "zh-cn"])
        is_preset_s2t = "s2t" in conv_preset.lower()
        conv_warning = ""
        if conv_on and is_tgt_simplified and is_preset_s2t:
            conv_warning = f" [bold red]{i18n.get('warn_conv_direction')}[/bold red]"

        # 判断双语与对照状态
        plugin_enables = self.root_config.get("plugin_enables", {})
        is_plugin_bilingual = plugin_enables.get("BilingualPlugin", False)
        
        # 1. 内容双语 (Bilingual Content via Plugin)
        bilingual_content_status = f"[green]{i18n.get('banner_on')}[/green]" if is_plugin_bilingual else f"[red]{i18n.get('banner_off')}[/red]"
        
        # 2. 对照文件 (Bilingual File Generation)
        bilingual_file_on = self.config.get("enable_bilingual_output", False)
        proj_type = self.config.get("translation_project", "AutoType")
        # 只有特定格式支持双语输出
        is_type_support_bilingual = proj_type in ["Txt", "Epub", "Srt"]
        if bilingual_file_on:
            if is_type_support_bilingual:
                bilingual_file_status = f"[green]{i18n.get('banner_on')}[/green] ([cyan]{bilingual_order.replace('_', ' ')}[/cyan])"
            else:
                bilingual_file_status = f"[yellow]{i18n.get('banner_on')} ({i18n.get('banner_unsupported')})[/yellow]"
        else:
            bilingual_file_status = f"[red]{i18n.get('banner_off')}[/red]"
        
        # 3. 对照显示模式 (TUI Detailed View)
        detailed_on = self.config.get("show_detailed_logs", False)
        detailed_status = f"[green]{i18n.get('banner_on')}[/green]" if detailed_on else f"[red]{i18n.get('banner_off')}[/red]"

        # 获取第二行参数
        target_platform = self.config.get("target_platform", "Unknown")
        model_name = self.config.get("model", "Unknown")
        user_threads = self.config.get("user_thread_counts", 0)
        context_lines = self.config.get("pre_line_counts", 3)
        think_on = self.config.get("think_switch", False)
        is_local = target_platform.lower() in ["sakura", "localllm"]

        # 使用 I18N 获取文字
        conv_on_text = i18n.get("banner_on")
        conv_off_text = i18n.get("banner_off")
        
        conv_status = f"[green]{conv_on_text} ({conv_preset})[/green]" if conv_on else f"[red]{conv_off_text}[/red]"
        
        # 第二行状态构建
        threads_display = f"Auto" if user_threads == 0 else str(user_threads)
        think_status = ""
        if not is_local:
            think_text = f"[green]{conv_on_text}[/green]" if think_on else f"[red]{conv_off_text}[/red]"
            think_status = f" | [bold]{i18n.get('banner_think')}:[/bold] {think_text}"

        settings_line_1 = f"| [bold]{i18n.get('banner_langs')}:[/bold] {src}->{tgt} | [bold]{i18n.get('banner_conv')}:[/bold] {conv_status}{conv_warning} | [bold]{i18n.get('banner_bilingual_file')}:[/bold] {bilingual_file_status} | [bold]{i18n.get('banner_bilingual')}:[/bold] {bilingual_content_status} |"
        settings_line_2 = f"| [bold]{i18n.get('banner_api')}:[/bold] {target_platform} | [bold]{i18n.get('banner_threads')}:[/bold] {threads_display} | [bold]{i18n.get('banner_detailed')}:[/bold] {detailed_status}{think_status} |"

        # 提示词状态
        trans_p = self.config.get("translation_prompt_selection", {}).get("last_selected_id", "common")
        polish_p = self.config.get("polishing_prompt_selection", {}).get("last_selected_id", "common")
        if trans_p == "command": trans_p = i18n.get("label_none") or "None"
        if polish_p == "command": polish_p = i18n.get("label_none") or "None"
        settings_line_3 = f"| [bold]{i18n.get('banner_prompts') or 'Prompts'}:[/bold] {i18n.get('banner_trans') or 'Trans'}:[green]{trans_p}[/green] | {i18n.get('banner_polish') or 'Polish'}:[green]{polish_p}[/green] |"

        # 操作记录状态 - 开启时显示详细说明
        op_log_on = self.operation_logger.is_enabled()
        op_log_status = f"[green]{conv_on_text}[/green]" if op_log_on else f"[red]{conv_off_text}[/red]"
        if op_log_on:
            op_log_hint = f" [dim]({i18n.get('banner_op_log_hint_on') or '敏感信息已抹除'})[/dim]"
        else:
            op_log_hint = f" [dim]({i18n.get('banner_op_log_hint_off') or '建议开启以获得更准确的LLM分析'})[/dim]"

        # 自动AI校对状态 - 只在开启时显示，单独一行
        auto_proofread_on = self.config.get("enable_auto_proofread", False)
        auto_proofread_line = ""
        if auto_proofread_on:
            auto_proofread_hint = i18n.get('banner_auto_proofread_hint') or '翻译完成后自动调用AI校对，会产生额外的API费用，请注意API费用'
            auto_proofread_line = f"\n| [bold]{i18n.get('banner_auto_proofread') or '自动校对'}:[/bold] [green]{conv_on_text}[/green] [dim]({auto_proofread_hint})[/dim] |"

        settings_line_4 = f"| [bold]{i18n.get('banner_op_log') or '操作记录'}:[/bold] {op_log_status}{op_log_hint} |{auto_proofread_line}"

        # GitHub 状态栏 (必须显示)
        github_status_line = ""
        github_info = getattr(self, '_cached_github_info', None)

        if github_info:
            parts = []
            if github_info.get("commit_text"):
                parts.append(f"[dim]{github_info['commit_text']}[/dim]")
            if github_info.get("release_text"):
                parts.append(f"[dim]{github_info['release_text']}[/dim]")
            if github_info.get("prerelease_text"):
                parts.append(f"[dim yellow]{github_info['prerelease_text']}[/dim yellow]")
            if parts:
                github_status_line = "\n" + " | ".join(parts)
            else:
                fail_msg = i18n.get('banner_github_fetch_failed') or '无法连接至Github，获取最新Commit和Release失败'
                github_status_line = f"\n[dim red]{fail_msg}[/dim red]"
        else:
            fail_msg = i18n.get('banner_github_fetch_failed') or '无法连接至Github，获取最新Commit和Release失败'
            github_status_line = f"\n[dim red]{fail_msg}[/dim red]"

        # Beta 版本提示
        beta_warning_line = ""
        if 'B' in v_str.upper():
            beta_msg = i18n.get('banner_beta_warning') or '注意:您正处于Beta版本，可能存在一些问题，若您遇到了，请提交issue以供修复/优化'
            beta_warning_line = f"\n[yellow]{beta_msg}[/yellow]"

        profile_display = f"[bold yellow]({self.active_profile_name})[/bold yellow]"
        console.clear()
        
        banner_content = (
            f"[bold cyan]AiNiee-Next[/bold cyan] [bold green]{v_str}[/bold green] {profile_display}\n"
            f"[dim]GUI Original: By NEKOparapa | CLI Version: By ShadowLoveElysia[/dim]\n"
            f"{settings_line_1}\n"
            f"{settings_line_2}\n"
            f"{settings_line_3}\n"
            f"{settings_line_4}"
            f"{github_status_line}"
            f"{beta_warning_line}"
        )
        
        console.print(Panel.fit(banner_content, title="Status", border_style="cyan"))

    def run_wizard(self):
        self.display_banner()
        console.print(Panel("[bold cyan]Welcome to AiNiee-Next! Let's run a quick setup wizard.[/bold cyan]"))
        
        # 1. UI Language
        self.first_time_lang_setup()
        
        # 2. Translation Languages
        console.print(f"\n[bold]1. {i18n.get('setting_src_lang')}/{i18n.get('setting_tgt_lang')}[/bold]")
        self.config["source_language"] = Prompt.ask(i18n.get('prompt_source_lang'), default="auto")
        self.config["target_language"] = Prompt.ask(i18n.get('prompt_target_lang'), default="Chinese")
        
        # 3. API Platform
        console.print(f"\n[bold]2. {i18n.get('menu_api_settings')}[/bold]")
        console.print(f"1. {i18n.get('menu_api_online')}\n2. {i18n.get('menu_api_local')}")
        api_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["1", "2"], default=1)
        self.api_manager.select_api_menu(online=(api_choice == 1))

        # 4. Validation
        console.print(f"\n[bold]3. {i18n.get('menu_api_validate')}[/bold]")
        self.api_manager.validate_api()
        
        # 5. Save and complete
        self.root_config["wizard_completed"] = True
        self.save_config(save_root=True)
        self.save_config() # Save the profile as well
        
        console.print(f"\n[bold green]✓ {i18n.get('msg_saved')} Wizard complete! Entering the main menu...[/bold green]")
        time.sleep(2)

    def _detect_terminal_capability(self):
        """检测终端能力，返回检测结果字典"""
        result = {
            'capable': False,
            'is_windows': sys.platform == 'win32',
            'is_ssh': bool(os.environ.get('SSH_CLIENT') or os.environ.get('SSH_TTY') or os.environ.get('SSH_CONNECTION')),
            'is_windows_terminal': bool(os.environ.get('WT_SESSION')),
            'is_windows_cmd': False,
            'supports_default_terminal': False,  # 是否支持设置默认终端
            'windows_build': 0,
            'colorterm': os.environ.get('COLORTERM', ''),
            'term': os.environ.get('TERM', ''),
            'term_program': os.environ.get('TERM_PROGRAM', ''),
        }

        # Windows Terminal 完全支持
        if result['is_windows_terminal']:
            result['capable'] = True
            return result

        # 检查 TERM_PROGRAM (已知的高质量终端，优先级最高)
        term_program = result['term_program'].lower()
        high_quality_terminals = ('iterm.app', 'vscode', 'hyper', 'tabby', 'wezterm', 'kitty', 'alacritty')
        if term_program in high_quality_terminals:
            result['capable'] = True
            return result

        # SSH 环境需要更严格的检测
        if result['is_ssh']:
            # SSH 环境下，只有 COLORTERM=truecolor/24bit 才能确认支持良好
            # 因为很多 SSH 客户端会伪造 TERM=xterm-256color 但实际支持很差
            if result['colorterm'].lower() in ('truecolor', '24bit'):
                result['capable'] = True
                return result
            # SSH 环境下，即使有 TERM=xterm-256color 也不信任，显示提示
            return result

        # 非 SSH 环境：检查 COLORTERM (truecolor/24bit 表示完整支持)
        if result['colorterm'].lower() in ('truecolor', '24bit'):
            result['capable'] = True
            return result

        # 非 SSH 环境：检查 TERM 变量
        term = result['term'].lower()
        # 现代终端标识
        if any(t in term for t in ['256color', 'kitty', 'alacritty']):
            result['capable'] = True
            return result

        # xterm/screen/tmux 在本地环境通常可以信任
        if any(t in term for t in ['xterm', 'screen', 'tmux', 'rxvt']):
            result['capable'] = True
            return result

        # macOS 默认终端
        if term_program == 'apple_terminal':
            result['capable'] = True
            return result

        # Windows 版本检测
        if result['is_windows']:
            try:
                import platform
                version = platform.version()  # 例如 '10.0.22631'
                build = int(version.split('.')[-1])
                result['windows_build'] = build

                # Windows 11 (build 22000+) 默认就是 Windows Terminal，直接通过
                if build >= 22000:
                    result['capable'] = True
                    return result

                # Windows 10 build 14393+ 支持 ANSI
                if build >= 14393:
                    # Windows 10 22H2 (build 19045) 支持设置默认终端，但默认仍是 CMD
                    if build >= 19045:
                        result['supports_default_terminal'] = True
                    result['is_windows_cmd'] = True
                    # 不设置 capable，让用户选择是否切换到 Windows Terminal
                    return result
            except (ValueError, IndexError):
                pass

            # 如果无法检测版本，且没有其他现代终端标识，标记为可能是旧版 CMD
            if not result['term'] and not result['colorterm']:
                result['is_windows_cmd'] = True

        return result

    def _check_terminal_compatibility(self):
        """检查终端兼容性，如果终端能力不足则提示用户"""
        # 检查是否已经处理过（避免重复提示）
        if self.root_config.get("terminal_check_skipped"):
            return True

        # 检测终端能力
        term_info = self._detect_terminal_capability()

        # 终端能力足够，直接返回
        if term_info['capable']:
            return True

        # 根据不同情况显示不同提示
        if term_info['is_windows_cmd']:
            detected_msg = i18n.get('terminal_compat_detected_cmd')
            hint_msg = i18n.get('terminal_compat_wt_better')
        elif term_info['is_ssh']:
            detected_msg = i18n.get('terminal_compat_detected_ssh')
            hint_msg = i18n.get('terminal_compat_ssh_better')
        else:
            detected_msg = i18n.get('terminal_compat_detected_limited')
            hint_msg = i18n.get('terminal_compat_general_better')

        # 显示终端选择菜单
        console.print("\n")
        console.print(Panel(
            f"[yellow]{detected_msg}[/yellow]\n"
            f"[dim]{hint_msg}[/dim]",
            title=f"[bold]{i18n.get('terminal_compat_title')}[/bold]",
            border_style="yellow"
        ))

        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", i18n.get('terminal_compat_opt_manual'))

        # Windows CMD 才显示自动重启选项
        if term_info['is_windows_cmd']:
            table.add_row("[green]2.[/]", f"{i18n.get('terminal_compat_opt_auto')} [green]{i18n.get('terminal_compat_opt_auto_recommended')}[/green]")
            # 只有 Windows 10 22H2+ 或 Windows 11 才支持设置默认终端
            if term_info.get('supports_default_terminal'):
                table.add_row("[cyan]3.[/]", i18n.get('terminal_compat_opt_auto_default'))
                table.add_row("[dim]4.[/]", i18n.get('terminal_compat_opt_skip'))
                choices = ["1", "2", "3", "4"]
            else:
                table.add_row("[dim]3.[/]", i18n.get('terminal_compat_opt_skip'))
                choices = ["1", "2", "3"]
            default = "2"
        else:
            table.add_row("[dim]2.[/]", i18n.get('terminal_compat_opt_skip'))
            choices = ["1", "2"]
            default = "2"

        console.print(table)

        choice = Prompt.ask(f"\n{i18n.get('prompt_select')}", choices=choices, default=default)

        if choice == "1":
            console.print(f"\n[cyan]{i18n.get('terminal_compat_manual_hint')}[/cyan]")
            console.print(f"[dim]{i18n.get('terminal_compat_manual_search')}[/dim]")
            console.print(f"[dim]{i18n.get('terminal_compat_manual_store')}[/dim]")
            console.print(f"[cyan]{i18n.get('terminal_compat_install_url')}[/cyan]")
            input(f"\n{i18n.get('terminal_compat_press_enter_exit')}")
            sys.exit(0)
        elif choice == "2" and term_info['is_windows_cmd']:
            # 尝试自动使用Windows Terminal重新启动
            try:
                script_path = os.path.abspath(sys.argv[0])
                args = sys.argv[1:] if len(sys.argv) > 1 else []
                cmd = ['wt', 'uv', 'run', script_path] + args
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                console.print(f"[green]{i18n.get('terminal_compat_auto_restarting')}[/green]")
                time.sleep(1)
                sys.exit(0)
            except FileNotFoundError:
                console.print(f"\n[red]{i18n.get('terminal_compat_wt_not_found')}[/red]")
                console.print(f"[dim]{i18n.get('terminal_compat_install_from_store')}[/dim]")
                console.print(f"[cyan]{i18n.get('terminal_compat_install_url')}[/cyan]")
                console.print(f"[yellow]{i18n.get('terminal_compat_continue_anyway')}[/yellow]")
                time.sleep(2)
        elif choice == "3" and term_info['is_windows_cmd'] and term_info.get('supports_default_terminal'):
            # 尝试自动使用Windows Terminal重新启动并设置为默认终端
            try:
                script_path = os.path.abspath(sys.argv[0])
                args = sys.argv[1:] if len(sys.argv) > 1 else []
                cmd = ['wt', 'uv', 'run', script_path] + args
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
                # 打开 Windows 设置页面让用户设置默认终端
                subprocess.Popen(['cmd', '/c', 'start', 'ms-settings:developers'], creationflags=subprocess.CREATE_NO_WINDOW)
                console.print(f"[green]{i18n.get('terminal_compat_auto_restarting')}[/green]")
                time.sleep(1)
                sys.exit(0)
            except FileNotFoundError:
                console.print(f"\n[red]{i18n.get('terminal_compat_wt_not_found')}[/red]")
                console.print(f"[dim]{i18n.get('terminal_compat_install_from_store')}[/dim]")
                console.print(f"[cyan]{i18n.get('terminal_compat_install_url')}[/cyan]")
                console.print(f"[yellow]{i18n.get('terminal_compat_continue_anyway')}[/yellow]")
                time.sleep(2)

        # 标记已处理，避免重复提示
        self.root_config["terminal_check_skipped"] = True
        self.save_config(save_root=True)

        return True

    def main_menu(self):
        # 检查终端兼容性
        self._check_terminal_compatibility()

        if not self.root_config.get("wizard_completed"):
            self.run_wizard()

        # 启动时自动检查更新
        if self.config.get("enable_auto_update", False):
            self.update_manager.check_update(silent=True)

        # 启动时获取 GitHub 状态信息 (后台异步)
        if self.config.get("enable_github_status_bar", True):
            self._fetch_github_status_async()
            # 等待异步获取完成（最多等待3秒）
            if hasattr(self, '_github_fetch_event'):
                self._github_fetch_event.wait(timeout=3)

        while True:
            self.display_banner()
            table = Table(show_header=False, box=None)
            menus = ["start_translation", "start_polishing", "start_all_in_one", "export_only", "editor", "settings", "api_settings", "glossary", "plugin_settings", "task_queue", "profiles", "qa", "update", "update_web", "start_web_server"]
            colors = ["green", "green", "bold green", "magenta", "bold cyan", "blue", "blue", "yellow", "cyan", "bold blue", "cyan", "yellow", "dim", "bold magenta", "magenta"]
            
            for i, (m, c) in enumerate(zip(menus, colors)): 
                label = i18n.get(f"menu_{m}")
                if m == "start_web_server" and label == f"menu_{m}":
                    label = "Start Web Server" # Fallback if not in json
                if m == "task_queue" and label == f"menu_{m}":
                    label = i18n.get("menu_task_queue")
                if m == "start_all_in_one" and label == f"menu_{m}":
                    label = i18n.get("menu_start_all_in_one")
                table.add_row(f"[{c}]{i+1}.[/]", label)
                
            table.add_row("[red]0.[/]", i18n.get("menu_exit")); console.print(table)
            choice = IntPrompt.ask(f"\n{i18n.get('prompt_select')}", choices=[str(i) for i in range(len(menus) + 1)], show_choices=False)
            console.print("\n")

            # 记录用户操作
            menu_names = ["退出", "开始翻译", "开始润色", "翻译&润色", "仅导出", "编辑器", "项目设置", "API设置", "提示词", "插件设置", "任务队列", "配置管理", "帮助QA", "更新", "更新Web", "Web服务器"]
            if choice < len(menu_names):
                self.operation_logger.log(f"主菜单 -> {menu_names[choice]}", "MENU")

            actions = [
                sys.exit,
                lambda: self.run_task(TaskType.TRANSLATION),
                lambda: self.run_task(TaskType.POLISH),
                self.run_all_in_one,
                self.run_export_only,
                self.editor_menu,
                self.settings_menu,
                self.api_manager.api_settings_menu,
                self.glossary_menu.prompt_menu,
                self.plugin_settings_menu,
                self.task_queue_menu,
                self.profiles_menu,
                self.qa_menu,
                self.update_manager.start_update,
                lambda: self.update_manager.setup_web_server(manual=True),
                self.start_web_server
            ]
            actions[choice]()

    def profiles_menu(self):
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_profiles')}[/bold]"))
            
            profiles = [f.replace(".json", "") for f in os.listdir(self.profiles_dir) if f.endswith(".json")]
            
            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", i18n.get("menu_profile_select"))
            table.add_row("[cyan]2.[/]", i18n.get("menu_profile_create"))
            table.add_row("[cyan]3.[/]", i18n.get("menu_profile_rename"))
            table.add_row("[red]4.[/]", i18n.get("menu_profile_delete"))
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_exit')}[/dim]")

            choice = IntPrompt.ask(f"\n{i18n.get('prompt_select')}", choices=["0", "1", "2", "3", "4"], show_choices=False)
            
            if choice == 0:
                break
            elif choice == 1: # Switch Profile
                console.print(Panel(i18n.get("menu_profile_select")))
                p_table = Table(show_header=False, box=None)
                for i, p in enumerate(profiles):
                    p_table.add_row(f"[cyan]{i+1}.[/]", p + (" [green](Active)[/]" if p == self.active_profile_name else ""))
                console.print(p_table)
                console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")
                
                sel_idx = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i) for i in range(len(profiles)+1)], show_choices=False)
                if sel_idx == 0: continue
                
                sel = profiles[sel_idx - 1]
                self.root_config["active_profile"] = sel
                self.save_config(save_root=True)
                self.load_config() # Reload everything
                console.print(f"[green]{i18n.get('msg_active_platform').format(sel)}[/green]"); time.sleep(1)
                break # Exit to main menu to reflect change
            elif choice == 2: # Create New Profile
                new_name = Prompt.ask(i18n.get("prompt_profile_name")).strip()
                if new_name and not os.path.exists(os.path.join(self.profiles_dir, f"{new_name}.json")):
                    shutil.copyfile(
                        os.path.join(self.profiles_dir, f"{self.active_profile_name}.json"),
                        os.path.join(self.profiles_dir, f"{new_name}.json")
                    )
                    console.print(f"[green]{i18n.get('msg_profile_created').format(new_name)}[/green]")
                else:
                    console.print(f"[red]{i18n.get('msg_profile_invalid')}[/red]")
                time.sleep(1)
            elif choice == 3: # Rename Current Profile
                new_name = Prompt.ask(i18n.get("prompt_profile_rename")).strip()
                if new_name and not os.path.exists(os.path.join(self.profiles_dir, f"{new_name}.json")):
                    os.rename(
                        os.path.join(self.profiles_dir, f"{self.active_profile_name}.json"),
                        os.path.join(self.profiles_dir, f"{new_name}.json")
                    )
                    self.active_profile_name = new_name
                    self.root_config["active_profile"] = new_name
                    self.save_config(save_root=True)
                    console.print(f"[green]{i18n.get('msg_profile_renamed').format(new_name)}[/green]")
                else:
                    console.print(f"[red]{i18n.get('msg_profile_invalid')}[/red]")
                time.sleep(1)

            elif choice == 4: # Delete Profile
                if len(profiles) <= 1:
                    console.print(f"[red]{i18n.get('msg_cannot_delete_last')}[/red]"); time.sleep(1); continue

                del_candidates = [p for p in profiles if p != self.active_profile_name]
                console.print(Panel(f"{i18n.get('menu_profile_delete')}"))
                p_table = Table(show_header=False, box=None)
                for i, p in enumerate(del_candidates):
                    p_table.add_row(f"[cyan]{i+1}.[/]", p)
                console.print(p_table)
                console.print(f"\n[dim]0. {i18n.get('menu_cancel')}[/dim]")

                sel_idx = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i) for i in range(len(del_candidates)+1)], show_choices=False)
                if sel_idx == 0: continue
                
                sel = del_candidates[sel_idx - 1]
                if Confirm.ask(f"[bold red]{i18n.get('msg_profile_delete_confirm').format(sel)}[/bold red]"):
                    os.remove(os.path.join(self.profiles_dir, f"{sel}.json"))
                    console.print(f"[green]{i18n.get('msg_profile_deleted').format(sel)}[/green]")
                    profiles = [f.replace(".json", "") for f in os.listdir(self.profiles_dir) if f.endswith(".json")] # Refresh list
                else:
                    console.print(f"[yellow]{i18n.get('msg_delete_cancel')}[/yellow]")
                time.sleep(1)

    def qa_menu(self):
        """智能自查诊断菜单 - 使用新的诊断模块"""
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_diagnostic_title')}[/bold]"))

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", i18n.get("menu_diagnostic_auto"))
            table.add_row("[cyan]2.[/]", i18n.get("menu_diagnostic_browse"))
            table.add_row("[cyan]3.[/]", i18n.get("menu_diagnostic_search"))
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3"], show_choices=False)
            if choice == 0: break

            if choice == 1:  # 自动诊断
                self._diagnostic_auto_menu()
            elif choice == 2:  # 浏览常见问题
                self._diagnostic_browse_menu()
            elif choice == 3:  # 搜索问题
                self._diagnostic_search_menu()

    def _diagnostic_auto_menu(self):
        """自动诊断 - 自动获取最近的错误信息进行诊断"""
        self.display_banner()
        console.print(Panel(f"[bold]{i18n.get('menu_diagnostic_auto')}[/bold]"))

        # 自动获取错误信息
        error_text = ""

        # 优先使用 crash 信息
        if getattr(self, "_last_crash_msg", None):
            error_text = self._last_crash_msg
        # 其次使用 API 错误信息
        elif getattr(self, "_api_error_messages", None) and len(self._api_error_messages) > 0:
            error_text = "\n".join(self._api_error_messages)

        if not error_text.strip():
            console.print(f"[yellow]{i18n.get('msg_no_error_detected')}[/yellow]")
            Prompt.ask(f"\n{i18n.get('msg_press_enter_to_continue')}")
            return

        # 显示检测到的错误
        console.print(Panel(error_text[:500] + ("..." if len(error_text) > 500 else ""),
                           title=f"[bold yellow]{i18n.get('label_error_content')}[/bold yellow]"))

        # 使用诊断模块进行诊断
        result = self.smart_diagnostic.diagnose(error_text)
        formatted = DiagnosticFormatter.format_result(result, current_lang)

        console.print(Panel(formatted, title=f"[bold cyan]{i18n.get('msg_diagnostic_result')}[/bold cyan]"))
        Prompt.ask(f"\n{i18n.get('msg_press_enter_to_continue')}")

    def _diagnostic_browse_menu(self):
        """浏览知识库中的常见问题"""
        kb = self.smart_diagnostic.knowledge_base
        items = list(kb.knowledge_items.values())

        if not items:
            console.print(f"[yellow]{i18n.get('msg_no_match_found')}[/yellow]")
            time.sleep(1)
            return

        # 按分类分组
        categories = {}
        for item in items:
            cat = item.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)

        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_diagnostic_browse')}[/bold]"))

            cat_list = list(categories.keys())
            table = Table(show_header=False, box=None)
            for i, cat in enumerate(cat_list):
                table.add_row(f"[cyan]{i+1}.[/]", cat)
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i) for i in range(len(cat_list)+1)], show_choices=False)
            if choice == 0: break

            # 显示该分类下的问题
            sel_cat = cat_list[choice - 1]
            cat_items = categories[sel_cat]

            while True:
                self.display_banner()
                console.print(Panel(f"[bold]{sel_cat}[/bold]"))

                for i, item in enumerate(cat_items):
                    console.print(f"[cyan]{i+1}.[/] {item.question}")
                console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")

                i_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i) for i in range(len(cat_items)+1)], show_choices=False)
                if i_choice == 0: break

                sel_item = cat_items[i_choice - 1]
                console.print(Panel(sel_item.answer, title=f"[bold green]{sel_item.question}[/bold green]"))
                Prompt.ask(f"\n{i18n.get('msg_press_enter_to_continue')}")

    def _diagnostic_search_menu(self):
        """搜索问题"""
        self.display_banner()
        console.print(Panel(f"[bold]{i18n.get('menu_diagnostic_search')}[/bold]"))

        keyword = Prompt.ask(i18n.get('prompt_search_keyword'))
        if not keyword.strip():
            return

        found_any = False
        self.display_banner()
        console.print(Panel(f"[bold]{i18n.get('msg_diagnostic_result')}[/bold]"))

        # 1. 先尝试规则匹配（用户可能直接输入错误码如 502）
        rule_result = self.smart_diagnostic.rule_matcher.match(keyword)
        if rule_result.is_matched:
            found_any = True
            formatted = DiagnosticFormatter.format_result(rule_result, current_lang)
            console.print(Panel(formatted, title=f"[bold cyan]{i18n.get('label_matched_rule')}: {rule_result.matched_rule}[/bold cyan]"))

        # 2. 使用知识库搜索
        kb = self.smart_diagnostic.knowledge_base
        results = kb.search_by_keywords(keyword, top_k=5)

        if results:
            found_any = True
            for item, score in results:
                console.print(Panel(item.answer, title=f"[bold green]{item.question}[/bold green] [dim](score: {score:.2f})[/dim]"))

        if not found_any:
            console.print(f"[yellow]{i18n.get('msg_no_match_found')}[/yellow]")

        Prompt.ask(f"\n{i18n.get('msg_press_enter_to_continue')}")

    def handle_crash(self, error_msg, temp_config=None):
        """Elegant error handling menu for crashes."""
        self.task_running = False

        # 记录错误发生
        self.operation_logger.log(f"出现报错: {error_msg[:100]}...", "ERROR")

        console.print("\n")
        console.print(Panel(f"[bold yellow]{i18n.get('msg_program_error')}[/bold yellow]", border_style="yellow"))

        # 1. 使用智能诊断模块进行自动诊断
        diag_result = self.smart_diagnostic.diagnose(error_msg)

        # 2. 如果匹配到规则，显示诊断结果
        if diag_result.is_matched:
            formatted = DiagnosticFormatter.format_result(diag_result, current_lang)
            console.print(Panel(formatted, title=f"[bold cyan]{i18n.get('msg_diagnostic_result')}[/bold cyan]", border_style="cyan"))
            console.print("")
        else:
            # 未匹配到规则时，显示通用提示
            transient_keywords = ["401", "403", "429", "500", "Timeout", "Connection", "SSL", "rate_limit", "bad request"]
            if any(k.lower() in error_msg.lower() for k in transient_keywords):
                console.print(f"[bold yellow]![/] [yellow]{i18n.get('msg_api_transient_error')}[/yellow]\n")

        # 3. 环境信息 (灰字显示)
        current_p = temp_config["target_platform"] if temp_config else self.config.get("target_platform", "None")
        current_m = temp_config["model"] if temp_config else self.config.get("model", "None")
        is_temp = " [yellow](Temporary API)[/]" if temp_config else ""
        console.print(f"[dim]Environment: {current_p} - {current_m}{is_temp}[/dim]")

        # 显示报错内容
        console.print(f"[dim]{i18n.get('label_error_content')}: {error_msg}[/dim]\n")

        # 显示用户操作流（如果启用了操作记录）
        if self.operation_logger.is_enabled():
            records = self.operation_logger.get_records()
            if records:
                op_flow = " -> ".join([rec['action'] for rec in records[-10:]])  # 最近10条操作
                console.print(f"[dim]{i18n.get('label_operation_flow') or '操作流程'}: {op_flow}[/dim]\n")

        # 4. 功能选项
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", i18n.get("error_menu_analyze_llm"))
        table.add_row("[cyan]2.[/]", i18n.get("error_menu_analyze_github"))
        table.add_row("[cyan]3.[/]", i18n.get("error_menu_update"))
        table.add_row("[cyan]4.[/]", i18n.get("error_menu_save_log"))
        table.add_row("[cyan]5.[/]", i18n.get("menu_error_temp_api"))
        table.add_row("[red]0.[/]", i18n.get("error_menu_exit"))
        console.print(table)
        
        choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4", "5"], show_choices=False)
        
        if choice == 1: # LLM Analyze
            analysis = self._analyze_error_with_llm(error_msg, temp_config)
            if analysis:
                console.print(Panel(analysis, title=f"[bold cyan]{i18n.get('msg_llm_analysis_result')}[/bold cyan]"))
                
                # 检测是否为代码问题关键词
                code_issue_keywords = ["此为代码问题", "This is a code issue", "これはコードの問題です"]
                if any(kw in analysis for kw in code_issue_keywords):
                    if Confirm.ask(f"\n[bold yellow]{i18n.get('msg_ask_submit_issue')}[/bold yellow]"):
                        self._prepare_github_issue(error_msg, analysis)
                else:
                    Prompt.ask(f"\n{i18n.get('msg_press_enter_to_continue')}")
            self.handle_crash(error_msg, temp_config) 
        elif choice == 2: # GitHub Issue
            analysis = None
            if Confirm.ask(f"{i18n.get('msg_confirm_llm_analyze_first')}"):
                analysis = self._analyze_error_with_llm(error_msg, temp_config)
            
            # 如果已经分析过了，再次确认是否真的是代码问题（如果用户之前在选项 1 已经跳转过这里可能重复，但逻辑上保持一致）
            self._prepare_github_issue(error_msg, analysis)
            self.handle_crash(error_msg, temp_config)
        elif choice == 3: # Update
            self.update_manager.start_update()
        elif choice == 4: # Save Log
            path = self._save_error_log(error_msg)
            console.print(f"[green]{i18n.get('msg_error_saved').format(path=path)}[/green]")
            time.sleep(2)
            self.handle_crash(error_msg, temp_config)
        elif choice == 5: # Temp API
            preset_path = os.path.join(PROJECT_ROOT, "Resource", "platforms", "preset.json")
            if not os.path.exists(preset_path): return
            with open(preset_path, 'r', encoding='utf-8') as f: preset = json.load(f)
            
            platforms = preset.get("platforms", {})
            online_platforms = {k: v for k, v in platforms.items() if v.get("group") in ["online", "custom"]}
            
            sorted_keys = sorted(online_platforms.keys())
            console.print(Panel(i18n.get("prompt_temp_api_platform")))
            p_table = Table(show_header=False, box=None)
            for i, k in enumerate(sorted_keys):
                p_table.add_row(f"[cyan]{i+1}.[/]", online_platforms[k].get("name", k))
            console.print(p_table)
            
            plat_idx = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i) for i in range(len(sorted_keys)+1)], show_choices=False)
            if plat_idx == 0:
                self.handle_crash(error_msg, temp_config)
                return
            
            sel_tag = sorted_keys[plat_idx - 1]
            sel_conf = online_platforms[sel_tag].copy()
            
            # Ask for key settings
            if "api_key" in sel_conf.get("key_in_settings", []) or "api_key" in sel_conf:
                sel_conf["api_key"] = Prompt.ask(i18n.get("prompt_temp_api_key"), password=True).strip()
            
            if "api_url" in sel_conf.get("key_in_settings", []) or sel_tag == "custom":
                sel_conf["api_url"] = Prompt.ask(i18n.get("prompt_temp_api_url"), default=sel_conf.get("api_url", "")).strip()
            
            if "model" in sel_conf.get("key_in_settings", []):
                model_options = sel_conf.get("model_datas", [])
                if model_options:
                    console.print(f"\n[cyan]Suggested Models for {sel_tag}:[/] {', '.join(model_options)}")
                sel_conf["model"] = Prompt.ask(i18n.get("prompt_temp_model"), default=sel_conf.get("model", "")).strip()

            # Thinking settings
            if Confirm.ask(i18n.get("prompt_temp_think_switch"), default=False):
                sel_conf["think_switch"] = True
                if sel_conf.get("api_format") == "Anthropic":
                    sel_conf["think_depth"] = Prompt.ask(i18n.get("prompt_temp_think_depth"), choices=["low", "medium", "high"], default="low")
                else:
                    sel_conf["think_depth"] = Prompt.ask(i18n.get("prompt_temp_think_depth"), default="0")
                console.print(f"[dim]{i18n.get('hint_think_budget') or '提示: 0=关闭, -1=无上限'}[/dim]")
                budget_str = Prompt.ask(i18n.get("prompt_temp_think_budget"), default="4096")
                try:
                    sel_conf["thinking_budget"] = int(budget_str)
                except ValueError:
                    sel_conf["thinking_budget"] = 4096
            else:
                sel_conf["think_switch"] = False

            temp_config = sel_conf
            temp_config["target_platform"] = sel_tag
            
            if temp_config.get("api_key"):
                console.print(f"[green]{i18n.get('msg_temp_api_ok')}[/green]")
                self.handle_crash(error_msg, temp_config)
            else:
                self.handle_crash(error_msg, temp_config)
        else:
            sys.exit(1)

    def _analyze_error_with_llm(self, error_msg, temp_config=None):
        # 检查是否配置了在线 API
        if not temp_config and self.config.get("target_platform", "None").lower() in ["none", "localllm", "sakura"]:
            console.print(f"[yellow]{i18n.get('msg_temp_api_prompt')}[/yellow]")
            console.print(f"[red]{i18n.get('msg_api_not_configured')}[/red]")
            return None
        
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
        import copy

        # 1. 创建影子配置字典
        # 如果是临时配置，从预设文件开始构建，确保环境干净
        if temp_config:
            preset_path = os.path.join(PROJECT_ROOT, "Resource", "platforms", "preset.json")
            try:
                with open(preset_path, 'r', encoding='utf-8') as f:
                    config_shadow = json.load(f)
            except:
                config_shadow = copy.deepcopy(self.config)
            
            plat = temp_config["target_platform"]
            config_shadow["target_platform"] = plat
            config_shadow["api_settings"] = {"translate": plat, "polish": plat}
            if "platforms" not in config_shadow: config_shadow["platforms"] = {}
            if plat not in config_shadow["platforms"]:
                # 如果预设中没有这个平台，创建一个基础结构
                config_shadow["platforms"][plat] = {"api_format": "OpenAI"}
            
            config_shadow["platforms"][plat].update(temp_config)
            # 同步关键外层字段
            config_shadow["base_url"] = temp_config.get("api_url")
            config_shadow["api_key"] = temp_config.get("api_key")
            config_shadow["model"] = temp_config.get("model")
            if temp_config.get("think_switch"):
                config_shadow["think_switch"] = True
                config_shadow["think_depth"] = temp_config.get("think_depth")
                config_shadow["thinking_budget"] = temp_config.get("thinking_budget")
        else:
            config_shadow = copy.deepcopy(self.config)

        # 3. 影子配置落盘 (确保 TaskConfig 运行在最真实的逻辑下)
        temp_cfg_path = os.path.join(PROJECT_ROOT, "Resource", "temp_crash_config.json")
        try:
            with open(temp_cfg_path, 'w', encoding='utf-8') as f:
                json.dump(config_shadow, f, indent=4, ensure_ascii=False)
            
            # 4. 使用标准的 TaskConfig 流程加载
            test_task_config = TaskConfig()
            test_task_config.initialize(config_shadow)
            
            # 抑制初始化时的打印输出
            original_base_print = Base.print
            Base.print = lambda *args, **kwargs: None
            try:
                test_task_config.prepare_for_translation(TaskType.TRANSLATION)
                # 获取最终经过校验和补全的请求参数包
                plat_conf = test_task_config.get_platform_configuration("translationReq")
            finally:
                Base.print = original_base_print

            # 兼容性修正：LLMRequester 有时期望 'model' 而不是 'model_name'
            if "model_name" in plat_conf and "model" not in plat_conf:
                plat_conf["model"] = plat_conf["model_name"]
            
            # 设置适合分析的采样参数
            plat_conf["temperature"] = 1.0
            plat_conf["top_p"] = 1.0
            
            # 5. 执行分析请求
            requester = LLMRequester()
            
            # 从外部文件加载 Prompt
            prompt_path = os.path.join(PROJECT_ROOT, "Resource", "Prompt", "System", "error_analysis.json")
            system_prompt = "You are a Python expert helping a user with a crash."
            try:
                if os.path.exists(prompt_path):
                    with open(prompt_path, 'r', encoding='utf-8') as f:
                        prompts = json.load(f)
                        system_prompt = prompts.get("system_prompt", {}).get(current_lang, prompts.get("system_prompt", {}).get("en", system_prompt))
            except Exception: pass
            
            # 根据用户语言构建user_content
            env_info = f"OS={sys.platform}, Python={sys.version.split()[0]}, App Version={self.update_manager.get_local_version_full()}"

            if current_lang == "zh_CN":
                user_content = (
                    f"程序发生崩溃。\n"
                    f"环境信息: {env_info}\n\n"
                    f"项目文件结构:\n"
                    f"- 核心逻辑: ainiee_cli.py, ModuleFolders/*\n"
                    f"- 用户扩展: PluginScripts/*\n"
                    f"- 资源文件: Resource/*\n\n"
                )
            elif current_lang == "ja":
                user_content = (
                    f"プログラムがクラッシュしました。\n"
                    f"環境情報: {env_info}\n\n"
                    f"プロジェクトファイル構造:\n"
                    f"- コアロジック: ainiee_cli.py, ModuleFolders/*\n"
                    f"- ユーザー拡張: PluginScripts/*\n"
                    f"- リソース: Resource/*\n\n"
                )
            else:
                user_content = (
                    f"The program crashed.\n"
                    f"Environment: {env_info}\n\n"
                    f"Project File Structure:\n"
                    f"- Core Logic: ainiee_cli.py, ModuleFolders/*\n"
                    f"- User Extensions: PluginScripts/*\n"
                    f"- Resources: Resource/*\n\n"
                )

            # 添加用户操作记录（如果启用）
            if self.operation_logger.is_enabled():
                user_content += f"{self.operation_logger.get_formatted_log()}\n\n"

            # 添加Traceback和分析请求
            if current_lang == "zh_CN":
                user_content += (
                    f"错误堆栈:\n{error_msg}\n\n"
                    f"分析要求:\n"
                    f"请分析此崩溃是由外部因素（网络、API Key、环境、SSL）还是内部软件缺陷（AiNiee-Next代码Bug）导致的。\n"
                    f"注意: 网络/SSL/429/401错误通常不是代码Bug，除非代码从根本上误用了库。\n"
                    f"如果错误发生在第三方库（如requests、urllib3、ssl）中且由网络条件引起，则不是代码Bug。\n\n"
                    f"【重要】如果你确定这是AiNiee-Next的代码Bug，必须在回复中包含这句话：「此为代码问题」"
                )
            elif current_lang == "ja":
                user_content += (
                    f"トレースバック:\n{error_msg}\n\n"
                    f"分析要求:\n"
                    f"このクラッシュが外部要因（ネットワーク、APIキー、環境、SSL）によるものか、内部ソフトウェアの欠陥（AiNiee-Nextコードのバグ）によるものかを分析してください。\n"
                    f"注意: ネットワーク/SSL/429/401エラーは、コードがライブラリを根本的に誤用していない限り、コードのバグではありません。\n"
                    f"サードパーティライブラリ（requests、urllib3、sslなど）でネットワーク条件によりエラーが発生した場合、コードのバグではありません。\n\n"
                    f"【重要】これがAiNiee-Nextのコードバグであると確信した場合、回答に必ずこの文を含めてください：「これはコードの問題です」"
                )
            else:
                user_content += (
                    f"Traceback:\n{error_msg}\n\n"
                    f"Strict Analysis Request:\n"
                    f"Analyze if the crash is due to external factors (Network, API Key, Environment, SSL) or internal software defects (Bugs in AiNiee-Next code).\n"
                    f"Note: Network/SSL/429/401 errors are NEVER code bugs unless the code is fundamentally misusing the library.\n"
                    f"If the error occurs in a third-party library (like requests, urllib3, ssl) due to network conditions, it is NOT a code bug.\n\n"
                    f"[IMPORTANT] If you are certain this is a code bug in AiNiee-Next, you MUST include this exact phrase in your response: \"This is a code issue\""
                )
            
            console.print(f"[cyan]{i18n.get('msg_llm_analyzing')}[/cyan]")
            
            skip, think, content, p_t, c_t = requester.sent_request(
                [{"role": "user", "content": user_content}],
                system_prompt,
                plat_conf
            )
            
            if skip:
                console.print(f"[red]LLM Analysis failed: {content}[/red]")
                return None
            return content

        finally:
            # 6. 主动清理影子文件
            if os.path.exists(temp_cfg_path):
                try: os.remove(temp_cfg_path)
                except: pass
        
        if skip:
            console.print(f"[red]LLM Analysis failed: {content}[/red]")
            return None
        return content

    def _prepare_github_issue(self, error_msg, analysis=None):
        env_info = f"- OS: {sys.platform}\n- Python: {sys.version.split()[0]}\n- App Version: {self.update_manager.get_local_version_full()}"
        issue_body = f"## Error Description\n\n```python\n{error_msg}\n```\n\n## Environment\n{env_info}\n"
        if analysis:
            issue_body += f"\n## LLM Analysis Result\n{analysis}\n"
        
        console.print(Panel(issue_body, title="GitHub Issue Template"))
        
        # Localized Guide
        console.print(f"\n[bold cyan]{i18n.get('msg_github_guide')}[/bold cyan]")
        console.print(f"[bold cyan]{i18n.get('msg_github_issue_template')}[/bold cyan]")
        
        import webbrowser
        webbrowser.open("https://github.com/ShadowLoveElysia/AiNiee-Next/issues/new")
        Prompt.ask(f"\n{i18n.get('msg_press_enter_to_continue')}")

    def _save_error_log(self, error_msg):
        log_dir = os.path.join(PROJECT_ROOT, "output", "logs")
        os.makedirs(log_dir, exist_ok=True)
        filename = f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path = os.path.join(log_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Environment: OS={sys.platform}, Python={sys.version}\n")
            f.write(f"Version: {self.update_manager.get_local_version_full()}\n")
            f.write("-" * 40 + "\n")
            f.write(error_msg)
        return path

    def first_time_lang_setup(self):
        global current_lang, i18n
        
        detected = "en"
        if (l := locale.getdefaultlocale()[0]):
            if l.startswith("zh"): detected = "zh_CN"
            elif l.startswith("ja"): detected = "ja"
            
        default_idx = {"zh_CN": 1, "ja": 2, "en": 3}.get(detected, 3)
        
        console.print(Panel(f"[bold cyan]Language Setup / 语言设置 / 言語設定[/bold cyan]"))
        console.print(f"[dim]Detected System Language: {detected}[/dim]\n")
        
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", "中文 (简体)")
        table.add_row("[cyan]2.[/]", "日本語")
        table.add_row("[cyan]3.[/]", "English")
        console.print(table)
        
        c = IntPrompt.ask("\nSelect / 选择 / 選択", choices=["1", "2", "3"], default=default_idx, show_choices=False)
        
        current_lang = {"1": "zh_CN", "2": "ja", "3": "en"}[str(c)]
        self.config["interface_language"] = current_lang
        self.save_config()
        i18n = I18NLoader(current_lang)

    def editor_menu(self):
        """编辑器菜单"""
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_editor') or 'Translation Editor'}[/bold]"))

            # 检查是否有可用的项目
            if not hasattr(self, 'cache_manager') or not self.cache_manager:
                console.print("[red]No cache manager available. Please run a translation task first.[/red]")
                time.sleep(2)
                break

            # 检查是否有可用的项目缓存
            output_path = self.config.get("label_output_path", "./output")
            cache_file = os.path.join(output_path, "cache", "AinieeCacheData.json")

            if not os.path.exists(cache_file):
                console.print(f"[yellow]{i18n.get('editor_no_cache')}[/yellow]")
                console.print(f"[dim]{i18n.get('editor_expected_cache')}: {cache_file}[/dim]")
                input("\nPress Enter to continue...")
                break

            # 显示菜单选项
            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", i18n.get("menu_editor_open_current"))
            table.add_row("[cyan]2.[/]", i18n.get("menu_editor_input_path"))
            table.add_row("[cyan]3.[/]", i18n.get("menu_editor_scan_projects"))
            table.add_row("[cyan]4.[/]", i18n.get("menu_ai_proofread") or "AI自主校对")
            table.add_row("[cyan]5.[/]", i18n.get("menu_view_proofread_report") or "查看校对报告")
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_back') or 'Back'}[/dim]")

            choice = IntPrompt.ask(f"\n{i18n.get('prompt_select') or 'Select'}",
                                 choices=["0", "1", "2", "3", "4", "5"], show_choices=False)

            if choice == 0:
                break
            elif choice == 1:
                self._start_editor_with_current_project()
            elif choice == 2:
                self._input_project_path_for_editor()
            elif choice == 3:
                self._select_project_for_editor()
            elif choice == 4:
                self._ai_proofread_menu()
            elif choice == 5:
                self._view_proofread_reports()

    def _start_editor_with_current_project(self):
        """使用当前项目启动编辑器"""
        try:
            # 获取术语表数据
            glossary_data = getattr(self, 'prompt_dictionary_data', [])

            # 创建编辑器实例
            editor = TUIEditor(
                cache_manager=self.cache_manager,
                config=self.config,
                i18n=i18n,
                glossary_data=glossary_data
            )

            # 获取当前项目路径
            project_path = self.config.get("label_output_path", "./output")

            console.print(f"[green]{i18n.get('editor_starting')}: {os.path.basename(project_path)}[/green]")
            console.print(f"[dim]{i18n.get('editor_quit_tip')}[/dim]")
            time.sleep(1)

            # 启动编辑器
            success = editor.start_editor(project_path)

            if success:
                console.print(f"[green]{i18n.get('editor_session_completed')}[/green]")
            else:
                console.print(f"[red]{i18n.get('editor_failed_start')}[/red]")

        except Exception as e:
            console.print(f"[red]{i18n.get('editor_error_start')}: {e}[/red]")

        input("\nPress Enter to continue...")

    def _input_project_path_for_editor(self):
        """手动输入项目路径进行编辑"""
        try:
            console.print(Panel(f"[bold]{i18n.get('editor_input_path_title')}[/bold]"))
            console.print(f"[dim]{i18n.get('editor_input_path_tip')}[/dim]")
            console.print(f"[dim]{i18n.get('editor_input_path_example')}[/dim]\n")

            # 提示用户输入路径
            project_path = Prompt.ask(i18n.get('editor_project_path_prompt'))

            if not project_path or not project_path.strip():
                console.print(f"[yellow]{i18n.get('editor_path_empty')}[/yellow]")
                input("\nPress Enter to continue...")
                return

            project_path = project_path.strip()

            # 检查路径是否存在
            if not os.path.exists(project_path):
                console.print(f"[red]{i18n.get('editor_path_not_exist')}: {project_path}[/red]")
                input("\nPress Enter to continue...")
                return

            # 检查缓存文件是否存在
            cache_file = os.path.join(project_path, "cache", "AinieeCacheData.json")
            if not os.path.exists(cache_file):
                console.print(f"[red]{i18n.get('editor_cache_not_found')}: {cache_file}[/red]")
                console.print(f"[dim]{i18n.get('editor_cache_path_tip')}[/dim]")
                input("\nPress Enter to continue...")
                return

            # 分析项目信息
            project_info = self._analyze_cache_file(cache_file)
            if not project_info:
                console.print(f"[red]{i18n.get('editor_parse_failed')}[/red]")
                input("\nPress Enter to continue...")
                return

            # 显示项目信息并确认
            console.print(f"\n[green]{i18n.get('editor_found_project')}:[/green] {project_info['name']}")
            console.print(f"[dim]{i18n.get('editor_path_label')}: {project_info['path']}[/dim]")
            console.print(f"[dim]{i18n.get('editor_items_label')}: {project_info['item_count']}[/dim]")
            console.print(f"[dim]{i18n.get('editor_size_label')}: {project_info['size']}[/dim]")

            confirm = Confirm.ask(f"\n{i18n.get('editor_confirm_open')}", default=True)
            if confirm:
                self._start_editor_with_selected_project(project_info)
            else:
                console.print(f"[yellow]{i18n.get('editor_cancelled')}[/yellow]")
                input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            console.print(f"\n[yellow]{i18n.get('editor_cancelled')}[/yellow]")
        except Exception as e:
            console.print(f"[red]{i18n.get('editor_input_error')}: {e}[/red]")
            input("\nPress Enter to continue...")

    def _select_project_for_editor(self):
        """选择项目缓存进行编辑"""
        try:
            console.print(f"[blue]{i18n.get('editor_scanning_cache')}[/blue]")

            # 扫描可用的缓存文件
            cache_projects = self._scan_cache_files()

            if not cache_projects:
                console.print(f"[yellow]{i18n.get('editor_no_cached_projects')}[/yellow]")
                console.print(f"[dim]{i18n.get('editor_cache_pattern_tip')}[/dim]")
                input("\nPress Enter to continue...")
                return

            while True:
                self.display_banner()
                console.print(Panel(f"[bold]{i18n.get('menu_editor_select_project')}[/bold]"))

                # 显示可用的项目
                table = Table(show_header=True, box=None)
                table.add_column("ID", style="cyan", width=4)
                table.add_column(i18n.get("editor_project_name"), style="green")
                table.add_column(i18n.get("editor_project_path"), style="dim")
                table.add_column(i18n.get("editor_item_count"), style="yellow", width=10)
                table.add_column(i18n.get("editor_file_size"), style="blue", width=10)

                for i, project in enumerate(cache_projects):
                    table.add_row(
                        f"{i+1}",
                        project["name"],
                        project["path"],
                        str(project["item_count"]),
                        project["size"]
                    )

                console.print(table)
                console.print(f"\n[dim]0. {i18n.get('menu_back') or 'Back'}[/dim]")

                try:
                    choice = IntPrompt.ask(f"\n{i18n.get('prompt_select') or 'Select'}",
                                         choices=[str(i) for i in range(len(cache_projects) + 1)],
                                         show_choices=False)

                    if choice == 0:
                        break
                    elif 1 <= choice <= len(cache_projects):
                        selected_project = cache_projects[choice - 1]
                        self._start_editor_with_selected_project(selected_project)
                        break

                except (ValueError, KeyboardInterrupt):
                    break

        except Exception as e:
            console.print(f"[red]Error in project selection: {e}[/red]")
            input("\nPress Enter to continue...")

    def _scan_cache_files(self):
        """扫描系统中的缓存文件"""
        cache_projects = []

        # 扫描常见位置的缓存文件（只搜索浅层目录，避免卡住）
        search_paths = [
            ".",  # 当前目录
            "./output",  # 默认输出目录
        ]

        # 添加最近使用的项目路径（如果有的话）
        recent_projects = self.config.get("recent_projects", [])
        search_paths.extend(recent_projects)

        # 添加配置中的输出路径
        label_output = self.config.get("label_output_path", "")
        if label_output:
            search_paths.append(label_output)

        # 移除重复路径
        search_paths = list(set(search_paths))

        for base_path in search_paths:
            try:
                if not os.path.exists(base_path):
                    continue

                # 只搜索一层子目录，避免递归搜索卡住
                cache_files = []

                # 直接查找当前目录下的cache文件
                direct_cache = os.path.join(base_path, "cache", "AinieeCacheData.json")
                if os.path.exists(direct_cache):
                    cache_files.append(direct_cache)

                # 查找一层子目录
                try:
                    for subdir in os.listdir(base_path):
                        subdir_path = os.path.join(base_path, subdir)
                        if os.path.isdir(subdir_path):
                            cache_file = os.path.join(subdir_path, "cache", "AinieeCacheData.json")
                            if os.path.exists(cache_file):
                                cache_files.append(cache_file)
                except PermissionError:
                    pass

                # 也直接查找当前目录下的cache文件
                direct_cache = os.path.join(base_path, "cache", "AinieeCacheData.json")
                if os.path.exists(direct_cache):
                    cache_files.append(direct_cache)

                for cache_file in cache_files:
                    try:
                        project_info = self._analyze_cache_file(cache_file)
                        if project_info and project_info not in cache_projects:
                            cache_projects.append(project_info)
                    except Exception:
                        continue  # 跳过损坏的缓存文件

            except Exception:
                continue  # 跳过无法访问的路径

        # 按最后修改时间排序
        cache_projects.sort(key=lambda x: x["modified_time"], reverse=True)
        return cache_projects

    def _analyze_cache_file(self, cache_file_path):
        """分析缓存文件获取项目信息"""
        try:
            # 获取项目路径（cache文件所在目录的父目录）
            project_path = os.path.dirname(os.path.dirname(cache_file_path))
            project_name = os.path.basename(project_path)

            # 获取文件统计信息
            stat_info = os.stat(cache_file_path)
            file_size = stat_info.st_size
            modified_time = stat_info.st_mtime

            # 尝试解析缓存文件获取条目数量（只统计有翻译内容的）
            item_count = 0
            translated_count = 0
            try:
                with open(cache_file_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # 根据缓存文件结构计算条目数量
                if isinstance(cache_data, dict):
                    # 新格式缓存
                    files_data = cache_data.get("files", {})
                    for file_data in files_data.values():
                        if isinstance(file_data, dict):
                            items = file_data.get("items", [])
                            for item in items:
                                if isinstance(item, dict):
                                    item_count += 1
                                    # 检查是否有翻译内容
                                    translated_text = item.get("translated_text", "") or item.get("polished_text", "")
                                    if translated_text and translated_text.strip():
                                        translated_count += 1
                elif isinstance(cache_data, list) and len(cache_data) > 1:
                    # 旧格式缓存
                    for item in cache_data[1:]:  # 跳过项目信息
                        if isinstance(item, dict):
                            item_count += 1
                            translated_text = item.get("translated_text", "") or item.get("polished_text", "")
                            if translated_text and translated_text.strip():
                                translated_count += 1

            except Exception:
                item_count = 0
                translated_count = 0

            # 如果没有翻译内容，跳过这个项目
            if translated_count == 0:
                return None

            # 格式化文件大小
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"

            return {
                "name": project_name,
                "path": project_path,
                "cache_file": cache_file_path,
                "item_count": translated_count,  # 显示实际有翻译内容的条目数
                "total_items": item_count,  # 保留总条目数用于调试
                "size": size_str,
                "modified_time": modified_time
            }

        except Exception as e:
            # 如果分析失败，返回None
            return None

    def _start_editor_with_selected_project(self, project_info):
        """使用选定的项目启动编辑器"""
        try:
            # 获取术语表数据
            glossary_data = getattr(self, 'prompt_dictionary_data', [])

            # 创建编辑器实例
            editor = TUIEditor(
                cache_manager=self.cache_manager,
                config=self.config,
                i18n=i18n,
                glossary_data=glossary_data
            )

            console.print(f"[green]{i18n.get('editor_starting')}: {project_info['name']}[/green]")
            console.print(f"[dim]{i18n.get('editor_project_info')}: {project_info['path']}[/dim]")
            console.print(f"[dim]{i18n.get('editor_item_info')}: {project_info['item_count']}[/dim]")
            console.print(f"[dim]{i18n.get('editor_quit_tip')}[/dim]")
            time.sleep(1)

            # 启动编辑器
            success = editor.start_editor(project_info['path'])

            if success:
                console.print(f"[green]{i18n.get('editor_session_completed')}[/green]")

                # 将此项目添加到最近使用列表
                self._add_to_recent_projects(project_info['path'])
            else:
                console.print(f"[red]{i18n.get('editor_failed_start')}[/red]")

        except Exception as e:
            console.print(f"[red]{i18n.get('editor_error_start')}: {e}[/red]")
            import traceback
            console.print(f"[dim]Traceback: {traceback.format_exc()}[/dim]")

        input("\nPress Enter to continue...")

    def _add_to_recent_projects(self, project_path):
        """将项目添加到最近使用列表"""
        try:
            recent_projects = self.config.get("recent_projects", [])

            # 移除已存在的相同路径
            if project_path in recent_projects:
                recent_projects.remove(project_path)

            # 添加到列表开头
            recent_projects.insert(0, project_path)

            # 只保留最近的10个项目
            recent_projects = recent_projects[:10]

            # 保存到配置
            self.config["recent_projects"] = recent_projects
            self.save_config()

        except Exception:
            pass  # 静默处理错误，不影响主要功能

    def _ai_proofread_menu(self):
        """AI自主校对菜单"""
        from ModuleFolders.UserInterface.Proofreader import ProofreadTUI

        tui = ProofreadTUI(i18n)

        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_ai_proofread') or 'AI自主校对'}[/bold]"))

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", i18n.get("proofread_start_current") or "开始校对（当前项目）")
            table.add_row("[cyan]2.[/]", i18n.get("proofread_select_project") or "选择项目校对")
            table.add_row("[cyan]3.[/]", i18n.get("proofread_settings") or "校对设置")
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_back') or 'Back'}[/dim]")

            choice = IntPrompt.ask(
                f"\n{i18n.get('prompt_select') or 'Select'}",
                choices=["0", "1", "2", "3"],
                show_choices=False
            )

            if choice == 0:
                break
            elif choice == 1:
                if tui.display_warning():
                    self._start_ai_proofread()
            elif choice == 2:
                if tui.display_warning():
                    self._select_project_for_proofread()
            elif choice == 3:
                self._proofread_settings_menu()

    def _start_ai_proofread(self):
        """开始AI校对当前项目"""
        try:
            output_path = self.config.get("label_output_path", "./output")
            cache_file = os.path.join(output_path, "cache", "AinieeCacheData.json")

            if not os.path.exists(cache_file):
                console.print(f"[red]{i18n.get('proofread_no_cache') or '未找到缓存文件'}[/red]")
                input("\nPress Enter to continue...")
                return

            self._execute_proofread(output_path)

        except Exception as e:
            console.print(f"[red]{i18n.get('proofread_error') or '校对出错'}: {e}[/red]")
            input("\nPress Enter to continue...")

    def _execute_proofread(self, project_path: str):
        """执行校对"""
        from ModuleFolders.Service.Proofreader import (
            RuleBasedChecker, AIProofreader, ProofreadReport
        )
        from ModuleFolders.Service.Proofreader.ProofreadReport import ProofreadReportItem
        from ModuleFolders.UserInterface.Proofreader import ProofreadTUI
        from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus

        tui = ProofreadTUI(i18n)

        # 加载缓存
        cache_file = os.path.join(project_path, "cache", "AinieeCacheData.json")
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # 从 files 结构中提取所有 items
        items = []
        files_data = cache_data.get("files", {})
        for file_path, file_info in files_data.items():
            if isinstance(file_info, dict):
                file_items = file_info.get("items", {})
                if isinstance(file_items, dict):
                    items.extend(file_items.values())
                elif isinstance(file_items, list):
                    items.extend(file_items)

        if not items:
            console.print("[yellow]没有可校对的内容[/yellow]")
            input("\nPress Enter to continue...")
            return

        # 获取源文件名
        source_file = cache_data.get("project_id", "unknown")
        model_name = self.config.get("model", "unknown")

        # 询问校对模式
        console.print(Panel("[bold]选择校对模式[/bold]"))
        console.print("  [1] 仅规则检查 (免费，检查格式问题)")
        console.print("  [2] 规则检查 + AI校对 (消耗API，检查翻译质量)")
        console.print("  [0] 返回")

        mode = IntPrompt.ask("请选择", choices=["0", "1", "2"])
        if mode == 0:
            return

        # 初始化检查器
        rule_checker = RuleBasedChecker()
        report = ProofreadReport(source_file=source_file, model=model_name)

        # 筛选需要校对的条目
        to_check = []
        for item in items:
            status = item.get("translation_status", 0)
            if status not in [TranslationStatus.TRANSLATED, TranslationStatus.POLISHED]:
                continue
            source = item.get("source_text", "")
            target = item.get("translated_text", "") or item.get("polished_text", "")
            if source and target:
                to_check.append({
                    "index": item.get("text_index", 0),
                    "source": source,
                    "translation": target
                })

        console.print(f"[blue]开始校对 {len(to_check)} 条内容...[/blue]")

        # 执行规则检查
        console.print("[dim]执行规则检查...[/dim]")
        for i, item in enumerate(to_check):
            rule_results = rule_checker.check(item["source"], item["translation"])
            if rule_results:
                report_item = ProofreadReportItem(
                    index=item["index"],
                    source_text=item["source"],
                    translated_text=item["translation"],
                    rule_check={
                        "has_issues": True,
                        "issues": [{"rule_name": r.rule_name, "severity": r.severity, "description": r.description} for r in rule_results]
                    }
                )
                report.add_item(report_item)
            if (i + 1) % 100 == 0:
                console.print(f"[dim]规则检查: {i + 1}/{len(to_check)}[/dim]")

        console.print(f"[green]规则检查完成，发现 {len(report.items)} 个问题[/green]")

        # AI校对
        if mode == 2:
            self._execute_ai_proofread(to_check, report, project_path)

        # 完成报告
        report.finalize(len(items), len(to_check))
        report_path = report.save(project_path)
        console.print(f"[green]校对完成，报告已保存: {report_path}[/green]")

        tui.display_summary(report)
        self._handle_proofread_result(report, project_path)

    def _execute_ai_proofread(self, to_check: list, report, project_path: str):
        """执行AI校对 - 批量处理，复用翻译任务逻辑"""
        import concurrent.futures
        from ModuleFolders.Service.Proofreader.ProofreaderTask import ProofreaderTask
        from ModuleFolders.Service.Proofreader.ProofreadReport import ProofreadReportItem
        from ModuleFolders.Infrastructure.RequestLimiter.RequestLimiter import RequestLimiter

        # 初始化TaskConfig (复用翻译配置逻辑)
        task_config = TaskConfig()
        task_config.load_config_from_dict(self.config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)

        # 初始化限流器
        request_limiter = RequestLimiter()
        tpm_limit = self.config.get("tpm_limit", 100000)
        rpm_limit = self.config.get("rpm_limit", 60)
        request_limiter.set_limit(tpm_limit, rpm_limit)

        # 获取批量大小 (和翻译一样使用lines_limit)
        lines_limit = self.config.get("lines_limit", 30)
        pre_line_counts = self.config.get("pre_line_counts", 3)

        # 分割数据为批次
        chunks = []
        previous_chunks = []
        for i in range(0, len(to_check), lines_limit):
            chunk = to_check[i:i + lines_limit]
            chunks.append(chunk)
            # 上文
            start = max(0, i - pre_line_counts)
            previous_chunks.append(to_check[start:i])

        # 生成校对任务
        tasks_list = []
        for i, (chunk, prev_chunk) in enumerate(zip(chunks, previous_chunks)):
            task = ProofreaderTask(task_config, request_limiter)
            task.task_id = f"P-{i+1:03d}"
            task.set_items(chunk)
            task.set_previous_items(prev_chunk)
            task.prepare()
            tasks_list.append(task)

        # 统计数据
        total_tokens = 0
        issues_found = 0
        completed_tasks = 0
        lock = threading.Lock()

        # 任务完成回调
        def task_done_callback(future):
            nonlocal total_tokens, issues_found, completed_tasks
            try:
                result = future.result()
                with lock:
                    completed_tasks += 1  # 无论成功失败都计数

                    if result is None or result.get("skip", True):
                        return

                    total_tokens += result.get("prompt_tokens", 0) + result.get("completion_tokens", 0)

                    # 处理发现的问题 (key是行ID)
                    issues = result.get("issues", {})
                    corrections = result.get("corrections", {})
                    task = future.task_ref

                    # 建立行ID到item的映射
                    id_to_item = {item["index"]: item for item in task.items}

                    for line_id, issue_list in issues.items():
                        item = id_to_item.get(line_id)
                        if item:
                            issues_found += 1
                            report_item = ProofreadReportItem(
                                index=line_id,
                                source_text=item["source"],
                                translated_text=item["translation"],
                                ai_check={
                                    "has_issues": True,
                                    "issues": issue_list,
                                    "corrected_translation": corrections.get(line_id, "")
                                }
                            )
                            report.add_item(report_item)
            except Exception as e:
                with lock:
                    completed_tasks += 1

        # 并发执行任务
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]AI校对"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("•"),
            TextColumn("[cyan]Token: {task.fields[tokens]}"),
            TextColumn("•"),
            TextColumn("[yellow]问题: {task.fields[issues]}"),
            TimeElapsedColumn(),
            console=console,
            refresh_per_second=10
        ) as progress:
            progress_task = progress.add_task("AI校对", total=len(tasks_list), tokens=0, issues=0)

            with concurrent.futures.ThreadPoolExecutor(max_workers=task_config.actual_thread_counts, thread_name_prefix="proofreader") as executor:
                futures = []
                for task in tasks_list:
                    if Base.work_status == Base.STATUS.STOPING:
                        break
                    future = executor.submit(task.run)
                    future.task_ref = task
                    future.add_done_callback(task_done_callback)
                    futures.append(future)

                # 等待所有任务完成，同时更新进度
                while not all(f.done() for f in futures):
                    with lock:
                        progress.update(progress_task, completed=completed_tasks, tokens=total_tokens, issues=issues_found)
                    time.sleep(0.1)

                # 最终更新
                with lock:
                    progress.update(progress_task, completed=len(tasks_list), tokens=total_tokens, issues=issues_found)

        console.print(f"[green]AI校对完成，共消耗 {total_tokens} Token，发现 {issues_found} 个问题[/green]")

    def _handle_proofread_result(self, report, project_path: str):
        """处理校对结果"""
        from ModuleFolders.UserInterface.Proofreader import ProofreadTUI

        tui = ProofreadTUI(i18n)

        while True:
            choice = tui.display_action_menu()

            if choice == "0":
                break
            elif choice == "1":
                self._review_issues(report)
            elif choice == "2":
                self._apply_high_severity_fixes(report, project_path)
            elif choice == "3":
                self._export_proofread_file(report, project_path)
            elif choice == "4":
                console.print(f"[green]报告已保存[/green]")

        input("\nPress Enter to continue...")

    def _review_issues(self, report):
        """逐条审阅问题"""
        if not report.items:
            console.print("[yellow]没有发现问题[/yellow]")
            return

        for i, item in enumerate(report.items):
            console.print(f"\n[bold cyan]═══ 问题 {i + 1}/{len(report.items)} ═══[/bold cyan]")
            console.print(f"[dim]索引: {item.index}[/dim]")

            # 显示原文和译文
            console.print(f"\n[bold]原文:[/bold]")
            console.print(f"  {item.source_text[:200]}{'...' if len(item.source_text) > 200 else ''}")
            console.print(f"\n[bold]译文:[/bold]")
            console.print(f"  {item.translated_text[:200]}{'...' if len(item.translated_text) > 200 else ''}")

            # 显示规则检查问题
            if item.rule_check and item.rule_check.get("has_issues"):
                console.print(f"\n[bold yellow]规则检查问题:[/bold yellow]")
                for issue in item.rule_check.get("issues", []):
                    console.print(f"  • [{issue.get('severity', 'low')}] {issue.get('rule_name', '')}: {issue.get('description', '')}")

            # 显示AI检查问题
            if item.ai_check and item.ai_check.get("has_issues"):
                console.print(f"\n[bold yellow]AI检查问题:[/bold yellow]")
                for issue in item.ai_check.get("issues", []):
                    console.print(f"  • [{issue.get('severity', 'low')}] {issue.get('type', '')}: {issue.get('description', '')}")
                    if issue.get('suggestion'):
                        console.print(f"    建议: {issue.get('suggestion')}")
                if item.ai_check.get("corrected_translation"):
                    console.print(f"\n[bold green]AI建议译文:[/bold green]")
                    console.print(f"  {item.ai_check.get('corrected_translation')}")

            action = Prompt.ask(
                "\n[A]采纳 [S]跳过 [Q]退出 [a/s/q]",
                choices=["a", "s", "q", "A", "S", "Q"],
                default="s"
            )
            if action.lower() == "q":
                break

    def _apply_high_severity_fixes(self, report, project_path: str):
        """应用高危修改，生成AI校对版本的cache文件"""
        # 统计有修正译文的条目数量
        corrections_count = 0
        for item in report.items:
            if item.ai_check and item.ai_check.get("corrected_translation"):
                corrections_count += 1

        if corrections_count == 0:
            console.print("[yellow]没有AI修正译文可应用[/yellow]")
            return

        if not Confirm.ask(f"确认应用 {corrections_count} 个AI修正译文？将生成校对版本的cache文件", default=False):
            return

        # 加载原始cache文件
        cache_path = os.path.join(project_path, "cache", "AinieeCacheData.json")
        if not os.path.exists(cache_path):
            console.print("[red]找不到原始cache文件[/red]")
            return

        try:
            project = CacheManager.read_from_file(cache_path)

            # 应用修正
            applied_count = 0
            for item in report.items:
                if not item.ai_check or not item.ai_check.get("corrected_translation"):
                    continue

                corrected_text = item.ai_check.get("corrected_translation")
                text_index = item.index

                # 在所有文件中查找并更新对应条目
                for cache_file in project.files.values():
                    for cache_item in cache_file.items:
                        if cache_item.text_index == text_index:
                            # 更新译文
                            cache_item.translated_text = corrected_text
                            cache_item.translation_status = TranslationStatus.AI_PROOFREAD
                            applied_count += 1
                            break

            # 保存为AI校对版本的cache文件
            proofread_cache_path = os.path.join(project_path, "cache", "AinieeCacheData_proofread.json")
            import msgspec
            content_bytes = msgspec.json.encode(project)
            with open(proofread_cache_path, "wb") as f:
                f.write(content_bytes)

            console.print(f"[green]已应用 {applied_count} 个修正，校对版本已保存: {proofread_cache_path}[/green]")
            console.print(f"[dim]提示: 导出时可选择使用校对版本[/dim]")

        except Exception as e:
            console.print(f"[red]应用修正失败: {e}[/red]")

    def _export_proofread_file(self, report, project_path: str):
        """导出校对后文件"""
        # 检查是否为电子书格式
        source_file = report.meta.source_file
        ebook_exts = [".epub", ".mobi", ".azw3", ".fb2", ".txt", ".docx", ".pdf", ".htmlz", ".kepub"]
        ext = os.path.splitext(source_file)[1].lower()

        if ext in ebook_exts:
            # 电子书格式，询问导出格式
            console.print(f"\n原文件格式: {ext}")
            console.print("选择导出格式:")
            formats = ["epub", "mobi", "azw3", "fb2", "pdf", "txt", "docx", "htmlz"]
            for i, fmt in enumerate(formats):
                marker = "(原格式)" if f".{fmt}" == ext else ""
                console.print(f"  [{i+1}] {fmt} {marker}")
            console.print("  [0] 取消")

            choice = IntPrompt.ask("请选择", choices=[str(i) for i in range(len(formats)+1)])
            if choice == 0:
                return
            output_format = formats[choice - 1]
        else:
            # 非电子书格式，直接导出原格式
            output_format = ext.lstrip(".")

        console.print(f"[green]导出格式: {output_format}[/green]")
        console.print("[dim]导出功能开发中...[/dim]")

    def _view_proofread_reports(self):
        """查看校对报告"""
        from ModuleFolders.Service.Proofreader import ProofreadReport
        from ModuleFolders.UserInterface.Proofreader import ProofreadTUI

        output_path = self.config.get("label_output_path", "./output")
        reports = ProofreadReport.list_reports(output_path)

        if not reports:
            console.print("[yellow]没有找到校对报告[/yellow]")
            input("\nPress Enter to continue...")
            return

        console.print(Panel("[bold]校对报告列表[/bold]"))
        for i, report_path in enumerate(reports[:10]):
            filename = os.path.basename(report_path)
            console.print(f"  [{i+1}] {filename}")
        console.print("  [0] 返回")

        choice = IntPrompt.ask("请选择", choices=[str(i) for i in range(min(len(reports), 10)+1)])
        if choice == 0:
            return

        report = ProofreadReport.load(reports[choice - 1])
        tui = ProofreadTUI(i18n)
        tui.display_summary(report)
        self._handle_proofread_result(report, output_path)

    def _select_project_for_proofread(self):
        """选择项目进行校对"""
        console.print(Panel("[bold]选择项目[/bold]"))
        console.print("  [1] 手动输入项目路径")
        console.print("  [2] 从扫描结果中选择")
        console.print("  [0] 返回")

        choice = IntPrompt.ask("请选择", choices=["0", "1", "2"])
        if choice == 0:
            return
        elif choice == 1:
            # 手动输入路径
            path = Prompt.ask("请输入项目路径 (包含cache目录的父目录)")
            if not path or path.lower() == 'q':
                return

            cache_file = os.path.join(path, "cache", "AinieeCacheData.json")
            if not os.path.exists(cache_file):
                console.print(f"[red]未找到缓存文件: {cache_file}[/red]")
                input("\nPress Enter to continue...")
                return

            self._execute_proofread(path)
        else:
            # 从扫描结果中选择
            console.print("[dim]正在扫描缓存项目...[/dim]")
            cache_projects = self._scan_cache_files()

            if not cache_projects:
                console.print("[yellow]没有找到可校对的项目[/yellow]")
                input("\nPress Enter to continue...")
                return

            console.print(Panel("[bold]选择项目[/bold]"))
            for i, project in enumerate(cache_projects[:10]):
                console.print(f"  [{i+1}] {project['name']}")
            console.print("  [0] 返回")

            sub_choice = IntPrompt.ask("请选择", choices=[str(i) for i in range(min(len(cache_projects), 10)+1)])
            if sub_choice == 0:
                return

            selected = cache_projects[sub_choice - 1]
            self._execute_proofread(selected['path'])

    def _proofread_settings_menu(self):
        """校对设置菜单"""
        while True:
            self.display_banner()
            console.print(Panel("[bold]校对设置[/bold]"))

            context_lines = self.config.get("proofread_context_lines", 5)
            batch_size = self.config.get("proofread_batch_size", 20)
            threshold = self.config.get("proofread_confidence_threshold", 0.7)

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"上下文行数: {context_lines}")
            table.add_row("[cyan]2.[/]", f"批量大小: {batch_size}")
            table.add_row("[cyan]3.[/]", f"置信度阈值: {threshold}")
            console.print(table)
            console.print(f"\n[dim]0. 返回[/dim]")

            choice = IntPrompt.ask("请选择", choices=["0", "1", "2", "3"])

            if choice == 0:
                break
            elif choice == 1:
                new_val = IntPrompt.ask("上下文行数", default=context_lines)
                self.config["proofread_context_lines"] = new_val
            elif choice == 2:
                new_val = IntPrompt.ask("批量大小", default=batch_size)
                self.config["proofread_batch_size"] = new_val
            elif choice == 3:
                new_val = Prompt.ask("置信度阈值", default=str(threshold))
                self.config["proofread_confidence_threshold"] = float(new_val)

            self.save_config()

    def settings_menu(self):
        """设置菜单 - 基于 ConfigRegistry 动态生成"""
        builder = SettingsMenuBuilder(self.config, i18n)

        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_settings')}[/bold]"))

            # 构建并渲染菜单
            builder.build_menu_items()
            table = builder.render_table()
            console.print(table)

            # 显示图例
            console.print(f"\n[dim][yellow]*[/yellow] = {i18n.get('label_advanced_setting')}[/dim]")
            console.print(f"[dim]0. {i18n.get('menu_exit')}[/dim]")

            # 获取用户选择
            max_choice = len(builder.menu_items)
            choice = IntPrompt.ask(
                f"\n{i18n.get('prompt_select')}",
                choices=[str(i) for i in range(max_choice + 1)],
                show_choices=False
            )

            if choice == 0:
                break

            # 处理用户选择
            key, item = builder.get_item_by_id(choice)
            if key and item:
                # 特殊处理：API池管理入口
                if key == "api_pool_management":
                    self.api_manager.api_pool_menu()
                    continue

                # 特殊处理：自动化设置入口
                if key == "automation_settings":
                    self.automation_menu()
                    continue

                new_value = builder.handle_input(key, item, console)
                if new_value is not None:
                    self.config[key] = new_value
                    self.save_config()

                    # 特殊处理：操作记录开关
                    if key == "enable_operation_logging":
                        if new_value:
                            self.operation_logger.enable()
                        else:
                            self.operation_logger.disable()

    def automation_menu(self):
        """自动化设置菜单"""
        from ModuleFolders.Infrastructure.Automation import SchedulerManager, WatchManager
        from ModuleFolders.Infrastructure.Automation.SchedulerManager import ScheduledTask
        from ModuleFolders.Infrastructure.Automation.WatchManager import WatchRule

        # 初始化管理器（如果尚未初始化）
        if not hasattr(self, 'scheduler_manager'):
            self.scheduler_manager = SchedulerManager()
            self.scheduler_manager.load_from_config(self.config)
        if not hasattr(self, 'watch_manager'):
            self.watch_manager = WatchManager()
            self.watch_manager.load_from_config(self.config)

        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_automation')}[/bold]"))
            console.print(f"[dim]{i18n.get('automation_cooperation_hint')}[/dim]\n")

            # 获取状态
            sched_status = self.scheduler_manager.get_status()
            watch_status = self.watch_manager.get_status()

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"{i18n.get('menu_automation_scheduler')}",
                         f"[{'green' if sched_status['running'] else 'dim'}]{i18n.get('automation_running') if sched_status['running'] else i18n.get('automation_stopped')}[/] ({sched_status['task_count']} {i18n.get('automation_task_count')})")
            table.add_row("[cyan]2.[/]", f"{i18n.get('menu_automation_watch')}",
                         f"[{'green' if watch_status['running'] else 'dim'}]{i18n.get('automation_running') if watch_status['running'] else i18n.get('automation_stopped')}[/] ({watch_status['rule_count']} {i18n.get('automation_task_count')})")
            table.add_row("[cyan]3.[/]", f"{i18n.get('menu_automation_status')}")
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")

            choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3"], show_choices=False)

            if choice == 0:
                # 保存配置
                self.scheduler_manager.save_to_config(self.config)
                self.watch_manager.save_to_config(self.config)
                self.save_config()
                break
            elif choice == 1:
                self.scheduler_submenu()
            elif choice == 2:
                self.watch_submenu()
            elif choice == 3:
                self.automation_status_view()

    def scheduler_submenu(self):
        """定时任务子菜单"""
        from ModuleFolders.Infrastructure.Automation.SchedulerManager import ScheduledTask

        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('scheduler_title')}[/bold]"))
            console.print(f"[dim]{i18n.get('scheduler_usage_hint')}[/dim]\n")

            status = self.scheduler_manager.get_status()

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"{i18n.get('scheduler_enabled')}: [{'green' if status['running'] else 'red'}]{'ON' if status['running'] else 'OFF'}[/]")
            table.add_row("[cyan]2.[/]", i18n.get('scheduler_add_task'))
            table.add_row("[cyan]3.[/]", i18n.get('scheduler_edit_task'))
            table.add_row("[cyan]4.[/]", i18n.get('scheduler_remove_task'))
            table.add_row("[cyan]5.[/]", i18n.get('scheduler_view_logs'))
            console.print(table)

            # 显示任务列表
            tasks = self.scheduler_manager.get_all_tasks()
            if tasks:
                console.print(f"\n[bold]{i18n.get('scheduler_task_list')}:[/bold]")
                task_table = Table(box=None)
                task_table.add_column("ID", style="cyan")
                task_table.add_column(i18n.get('scheduler_task_name'))
                task_table.add_column(i18n.get('scheduler_cron_expr'))
                task_table.add_column(i18n.get('scheduler_next_run'))
                task_table.add_column(i18n.get('label_status'))

                for task in tasks:
                    next_run = task.next_run.strftime("%m-%d %H:%M") if task.next_run else "-"
                    status_str = "[green]●[/]" if task.enabled else "[dim]○[/]"
                    task_table.add_row(task.id, task.name, task.schedule, next_run, status_str)
                console.print(task_table)
            else:
                console.print(f"\n[dim]{i18n.get('scheduler_no_tasks')}[/dim]")

            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")
            choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4", "5"], show_choices=False)

            if choice == 0:
                break
            elif choice == 1:
                if self.scheduler_manager.running:
                    self.scheduler_manager.stop()
                else:
                    self.scheduler_manager.start()
            elif choice == 2:
                self.add_scheduled_task()
            elif choice == 3:
                self.edit_scheduled_task()
            elif choice == 4:
                self.remove_scheduled_task()
            elif choice == 5:
                self.view_automation_logs(self.scheduler_manager.get_logs())

    def add_scheduled_task(self):
        """添加定时任务"""
        from ModuleFolders.Infrastructure.Automation.SchedulerManager import ScheduledTask

        console.print(Panel(f"[bold]{i18n.get('scheduler_add_task')}[/bold]"))

        task_id = Prompt.ask(i18n.get('prompt_task_id_new'))
        if self.scheduler_manager.get_task(task_id):
            console.print(f"[red]{i18n.get('msg_id_exists')}[/red]")
            return

        name = Prompt.ask(i18n.get('scheduler_task_name'))
        schedule = Prompt.ask(i18n.get('scheduler_cron_expr'), default="0 2 * * *")

        # 验证 cron 表达式
        try:
            from ModuleFolders.Infrastructure.Automation.SchedulerManager import CronParser
            CronParser.parse(schedule)
        except ValueError:
            console.print(f"[red]{i18n.get('msg_invalid_cron')}[/red]")
            return

        input_path = Prompt.ask(i18n.get('scheduler_input_path'))
        if not os.path.exists(input_path):
            console.print(f"[red]{i18n.get('msg_path_not_exist')}[/red]")
            return

        # 选择任务类型
        task_types = ["translation", "polishing", "all_in_one"]
        console.print(f"\n{i18n.get('scheduler_task_type')}:")
        for i, t in enumerate(task_types):
            console.print(f"  [cyan]{i+1}.[/] {i18n.get(f'task_type_{t}')}")
        type_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["1", "2", "3"], default=1, show_choices=False)
        task_type = task_types[type_choice - 1]

        # 选择配置
        profiles = self._get_profiles_list(self.profiles_dir)
        console.print(f"\n{i18n.get('scheduler_profile')}:")
        for i, p in enumerate(profiles):
            console.print(f"  [cyan]{i+1}.[/] {p}")
        profile_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i+1) for i in range(len(profiles))], default=1, show_choices=False)
        profile = profiles[profile_choice - 1]

        task = ScheduledTask(
            task_id=task_id,
            name=name,
            schedule=schedule,
            input_path=input_path,
            profile=profile,
            task_type=task_type
        )

        if self.scheduler_manager.add_task(task):
            console.print(f"[green]{i18n.get('scheduler_task_added')}[/green]")
            self.scheduler_manager.save_to_config(self.config)
            self.save_config()

    def edit_scheduled_task(self):
        """编辑定时任务"""
        tasks = self.scheduler_manager.get_all_tasks()
        if not tasks:
            console.print(f"[dim]{i18n.get('scheduler_no_tasks')}[/dim]")
            return

        console.print(Panel(f"[bold]{i18n.get('scheduler_edit_task')}[/bold]"))
        for i, task in enumerate(tasks):
            console.print(f"  [cyan]{i+1}.[/] {task.id} - {task.name}")

        choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i+1) for i in range(len(tasks))] + ["0"], default=0, show_choices=False)
        if choice == 0:
            return

        task = tasks[choice - 1]

        # 编辑选项
        console.print(f"\n[bold]{task.name}[/bold]")
        console.print(f"1. {i18n.get('label_enabled')}: {'ON' if task.enabled else 'OFF'}")
        console.print(f"2. {i18n.get('scheduler_cron_expr')}: {task.schedule}")
        console.print(f"3. {i18n.get('scheduler_input_path')}: {task.input_path}")

        edit_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3"], default=0, show_choices=False)

        if edit_choice == 1:
            self.scheduler_manager.update_task(task.id, enabled=not task.enabled)
        elif edit_choice == 2:
            new_schedule = Prompt.ask(i18n.get('scheduler_cron_expr'), default=task.schedule)
            try:
                from ModuleFolders.Infrastructure.Automation.SchedulerManager import CronParser
                CronParser.parse(new_schedule)
                self.scheduler_manager.update_task(task.id, schedule=new_schedule)
            except ValueError:
                console.print(f"[red]{i18n.get('msg_invalid_cron')}[/red]")
        elif edit_choice == 3:
            new_path = Prompt.ask(i18n.get('scheduler_input_path'), default=task.input_path)
            if os.path.exists(new_path):
                self.scheduler_manager.update_task(task.id, input_path=new_path)
            else:
                console.print(f"[red]{i18n.get('msg_path_not_exist')}[/red]")

        if edit_choice > 0:
            console.print(f"[green]{i18n.get('scheduler_task_updated')}[/green]")
            self.scheduler_manager.save_to_config(self.config)
            self.save_config()

    def remove_scheduled_task(self):
        """删除定时任务"""
        tasks = self.scheduler_manager.get_all_tasks()
        if not tasks:
            console.print(f"[dim]{i18n.get('scheduler_no_tasks')}[/dim]")
            return

        console.print(Panel(f"[bold]{i18n.get('scheduler_remove_task')}[/bold]"))
        for i, task in enumerate(tasks):
            console.print(f"  [cyan]{i+1}.[/] {task.id} - {task.name}")

        choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i+1) for i in range(len(tasks))] + ["0"], default=0, show_choices=False)
        if choice == 0:
            return

        task = tasks[choice - 1]
        if Confirm.ask(i18n.get('scheduler_confirm_remove')):
            self.scheduler_manager.remove_task(task.id)
            console.print(f"[green]{i18n.get('scheduler_task_removed')}[/green]")
            self.scheduler_manager.save_to_config(self.config)
            self.save_config()

    def watch_submenu(self):
        """文件夹监控子菜单"""
        from ModuleFolders.Infrastructure.Automation.WatchManager import WatchRule

        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('watch_title')}[/bold]"))
            console.print(f"[dim]{i18n.get('watch_usage_hint')}[/dim]\n")

            status = self.watch_manager.get_status()

            table = Table(show_header=False, box=None)
            table.add_row("[cyan]1.[/]", f"{i18n.get('watch_enabled')}: [{'green' if status['running'] else 'red'}]{'ON' if status['running'] else 'OFF'}[/]")
            table.add_row("[cyan]2.[/]", i18n.get('watch_add_rule'))
            table.add_row("[cyan]3.[/]", i18n.get('watch_edit_rule'))
            table.add_row("[cyan]4.[/]", i18n.get('watch_remove_rule'))
            table.add_row("[cyan]5.[/]", i18n.get('watch_view_logs'))
            table.add_row("[cyan]6.[/]", i18n.get('watch_clear_history'))
            console.print(table)

            # 显示规则列表
            rules = self.watch_manager.get_all_rules()
            if rules:
                console.print(f"\n[bold]{i18n.get('watch_rule_list')}:[/bold]")
                rule_table = Table(box=None)
                rule_table.add_column("ID", style="cyan")
                rule_table.add_column(i18n.get('watch_path'))
                rule_table.add_column(i18n.get('watch_patterns'))
                rule_table.add_column(i18n.get('watch_mode'))
                rule_table.add_column(i18n.get('label_status'))

                for rule in rules:
                    patterns = ", ".join(rule.file_patterns[:3])
                    if len(rule.file_patterns) > 3:
                        patterns += "..."
                    mode = i18n.get('watch_mode_instant') if rule.auto_start else i18n.get('watch_mode_collect')
                    status_str = "[green]●[/]" if rule.enabled else "[dim]○[/]"
                    rule_table.add_row(rule.id, os.path.basename(rule.watch_path), patterns, mode, status_str)
                console.print(rule_table)
            else:
                console.print(f"\n[dim]{i18n.get('watch_no_rules')}[/dim]")

            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")
            choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4", "5", "6"], show_choices=False)

            if choice == 0:
                break
            elif choice == 1:
                if self.watch_manager.running:
                    self.watch_manager.stop()
                else:
                    self.watch_manager.start()
            elif choice == 2:
                self.add_watch_rule()
            elif choice == 3:
                self.edit_watch_rule()
            elif choice == 4:
                self.remove_watch_rule()
            elif choice == 5:
                self.view_automation_logs(self.watch_manager.get_logs())
            elif choice == 6:
                self.watch_manager.clear_processed_history()
                console.print(f"[green]{i18n.get('watch_history_cleared')}[/green]")

    def add_watch_rule(self):
        """添加监控规则"""
        from ModuleFolders.Infrastructure.Automation.WatchManager import WatchRule

        console.print(Panel(f"[bold]{i18n.get('watch_add_rule')}[/bold]"))

        rule_id = Prompt.ask(i18n.get('prompt_rule_id'))
        if self.watch_manager.get_rule(rule_id):
            console.print(f"[red]{i18n.get('msg_id_exists')}[/red]")
            return

        watch_path = Prompt.ask(i18n.get('watch_path'))
        if not os.path.exists(watch_path):
            console.print(f"[red]{i18n.get('msg_path_not_exist')}[/red]")
            return

        patterns_str = Prompt.ask(f"{i18n.get('watch_patterns')} ({i18n.get('watch_patterns_hint')})", default="*.epub, *.txt, *.srt")
        file_patterns = [p.strip() for p in patterns_str.split(",")]

        # 选择监控模式
        console.print(f"\n{i18n.get('watch_mode')}:")
        console.print(f"  [cyan]1.[/] {i18n.get('watch_mode_instant')} - {i18n.get('watch_mode_instant_desc')}")
        console.print(f"  [cyan]2.[/] {i18n.get('watch_mode_collect')} - {i18n.get('watch_mode_collect_desc')}")
        mode_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["1", "2"], default=1, show_choices=False)
        auto_start = mode_choice == 1

        # 选择任务类型
        task_types = ["translation", "polishing", "all_in_one"]
        console.print(f"\n{i18n.get('watch_task_type')}:")
        for i, t in enumerate(task_types):
            console.print(f"  [cyan]{i+1}.[/] {i18n.get(f'task_type_{t}')}")
        type_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["1", "2", "3"], default=1, show_choices=False)
        task_type = task_types[type_choice - 1]

        # 选择配置
        profiles = self._get_profiles_list(self.profiles_dir)
        console.print(f"\n{i18n.get('watch_profile')}:")
        for i, p in enumerate(profiles):
            console.print(f"  [cyan]{i+1}.[/] {p}")
        profile_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i+1) for i in range(len(profiles))], default=1, show_choices=False)
        profile = profiles[profile_choice - 1]

        # 其他选项
        debounce = IntPrompt.ask(f"{i18n.get('watch_debounce')} ({i18n.get('watch_debounce_hint')})", default=5)
        recursive = Confirm.ask(i18n.get('watch_recursive'), default=False)

        rule = WatchRule(
            rule_id=rule_id,
            watch_path=watch_path,
            file_patterns=file_patterns,
            profile=profile,
            task_type=task_type,
            auto_start=auto_start,
            debounce_seconds=debounce,
            recursive=recursive
        )

        if self.watch_manager.add_rule(rule):
            console.print(f"[green]{i18n.get('watch_rule_added')}[/green]")
            self.watch_manager.save_to_config(self.config)
            self.save_config()

    def edit_watch_rule(self):
        """编辑监控规则"""
        rules = self.watch_manager.get_all_rules()
        if not rules:
            console.print(f"[dim]{i18n.get('watch_no_rules')}[/dim]")
            return

        console.print(Panel(f"[bold]{i18n.get('watch_edit_rule')}[/bold]"))
        for i, rule in enumerate(rules):
            console.print(f"  [cyan]{i+1}.[/] {rule.id} - {rule.watch_path}")

        choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i+1) for i in range(len(rules))] + ["0"], default=0, show_choices=False)
        if choice == 0:
            return

        rule = rules[choice - 1]

        # 编辑选项
        console.print(f"\n[bold]{rule.id}[/bold]")
        console.print(f"1. {i18n.get('label_enabled')}: {'ON' if rule.enabled else 'OFF'}")
        console.print(f"2. {i18n.get('watch_mode')}: {i18n.get('watch_mode_instant') if rule.auto_start else i18n.get('watch_mode_collect')}")
        console.print(f"3. {i18n.get('watch_patterns')}: {', '.join(rule.file_patterns)}")
        console.print(f"4. {i18n.get('watch_debounce')}: {rule.debounce_seconds}s")

        edit_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["0", "1", "2", "3", "4"], default=0, show_choices=False)

        if edit_choice == 1:
            self.watch_manager.update_rule(rule.id, enabled=not rule.enabled)
        elif edit_choice == 2:
            console.print(f"\n{i18n.get('watch_mode')}:")
            console.print(f"  [cyan]1.[/] {i18n.get('watch_mode_instant')} - {i18n.get('watch_mode_instant_desc')}")
            console.print(f"  [cyan]2.[/] {i18n.get('watch_mode_collect')} - {i18n.get('watch_mode_collect_desc')}")
            mode_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["1", "2"], default=1 if rule.auto_start else 2, show_choices=False)
            self.watch_manager.update_rule(rule.id, auto_start=mode_choice == 1)
        elif edit_choice == 3:
            patterns_str = Prompt.ask(i18n.get('watch_patterns'), default=", ".join(rule.file_patterns))
            file_patterns = [p.strip() for p in patterns_str.split(",")]
            self.watch_manager.update_rule(rule.id, file_patterns=file_patterns)
        elif edit_choice == 4:
            debounce = IntPrompt.ask(i18n.get('watch_debounce'), default=rule.debounce_seconds)
            self.watch_manager.update_rule(rule.id, debounce_seconds=debounce)

        if edit_choice > 0:
            console.print(f"[green]{i18n.get('watch_rule_updated')}[/green]")
            self.watch_manager.save_to_config(self.config)
            self.save_config()

    def remove_watch_rule(self):
        """删除监控规则"""
        rules = self.watch_manager.get_all_rules()
        if not rules:
            console.print(f"[dim]{i18n.get('watch_no_rules')}[/dim]")
            return

        console.print(Panel(f"[bold]{i18n.get('watch_remove_rule')}[/bold]"))
        for i, rule in enumerate(rules):
            console.print(f"  [cyan]{i+1}.[/] {rule.id} - {rule.watch_path}")

        choice = IntPrompt.ask(i18n.get('prompt_select'), choices=[str(i+1) for i in range(len(rules))] + ["0"], default=0, show_choices=False)
        if choice == 0:
            return

        rule = rules[choice - 1]
        if Confirm.ask(i18n.get('watch_confirm_remove')):
            self.watch_manager.remove_rule(rule.id)
            console.print(f"[green]{i18n.get('watch_rule_removed')}[/green]")
            self.watch_manager.save_to_config(self.config)
            self.save_config()

    def automation_status_view(self):
        """自动化状态总览"""
        self.display_banner()
        console.print(Panel(f"[bold]{i18n.get('automation_status_title')}[/bold]"))

        sched_status = self.scheduler_manager.get_status()
        watch_status = self.watch_manager.get_status()

        # 调度器状态
        console.print(f"\n[bold]{i18n.get('automation_scheduler_status')}[/bold]")
        sched_table = Table(show_header=False, box=None)
        sched_table.add_row(i18n.get('label_status'), f"[{'green' if sched_status['running'] else 'red'}]{i18n.get('automation_running') if sched_status['running'] else i18n.get('automation_stopped')}[/]")
        sched_table.add_row(i18n.get('automation_task_count'), f"{sched_status['enabled_count']}/{sched_status['task_count']}")
        if sched_status.get('next_task'):
            next_task = sched_status['next_task']
            sched_table.add_row(i18n.get('automation_next_task'), f"{next_task['name']} @ {next_task['next_run']}")
        console.print(sched_table)

        # 监控状态
        console.print(f"\n[bold]{i18n.get('automation_watch_status')}[/bold]")
        watch_table = Table(show_header=False, box=None)
        watch_table.add_row(i18n.get('label_status'), f"[{'green' if watch_status['running'] else 'red'}]{i18n.get('automation_running') if watch_status['running'] else i18n.get('automation_stopped')}[/]")
        watch_table.add_row(i18n.get('automation_task_count'), f"{watch_status['enabled_count']}/{watch_status['rule_count']}")
        watch_table.add_row(i18n.get('watch_pending_files'), str(watch_status['pending_files']))
        watch_table.add_row(i18n.get('automation_total_processed'), str(watch_status['total_processed']))
        console.print(watch_table)

        Prompt.ask(f"\n{i18n.get('msg_press_enter')}")

    def view_automation_logs(self, logs: list):
        """查看自动化日志"""
        self.display_banner()

        if not logs:
            console.print("[dim]No logs available.[/dim]")
        else:
            log_table = Table(box=None)
            log_table.add_column("Time", style="dim")
            log_table.add_column("Level")
            log_table.add_column("Message")

            for log in logs[-20:]:
                level_style = {"info": "green", "warning": "yellow", "error": "red"}.get(log['level'], "white")
                log_table.add_row(log['time'], f"[{level_style}]{log['level'].upper()}[/]", log['message'])

            console.print(log_table)

        Prompt.ask(f"\n{i18n.get('msg_press_enter')}")

    def plugin_settings_menu(self):
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_plugin_settings')}[/bold]"))
            
            # 获取所有加载的插件
            plugins = self.plugin_manager.get_plugins()
            if not plugins:
                console.print(f"[dim]{i18n.get('msg_no_plugins_found')}[/dim]")
                Prompt.ask(f"\n{i18n.get('msg_press_enter')}")
                break

            # 获取当前启用状态
            plugin_enables = self.root_config.get("plugin_enables", {})
            
            table = Table(show_header=True, show_lines=True)
            table.add_column("ID", style="dim")
            table.add_column(i18n.get("label_plugin_name"))
            table.add_column(i18n.get("label_status"), style="cyan")
            table.add_column(i18n.get("label_description"), ratio=1)

            sorted_plugin_names = sorted(plugins.keys())
            for i, name in enumerate(sorted_plugin_names, 1):
                plugin = plugins[name]
                # 优先使用配置中的状态，否则使用插件自带的默认状态
                is_enabled = plugin_enables.get(name, plugin.default_enable)
                status = "[green]ON[/]" if is_enabled else "[red]OFF[/]"
                table.add_row(str(i), name, status, plugin.description)
            
            console.print(table)
            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")
            
            choice = IntPrompt.ask(f"\n{i18n.get('prompt_toggle_plugin')}", choices=[str(i) for i in range(len(sorted_plugin_names) + 1)], show_choices=False)

            if choice == 0:
                break
            
            name = sorted_plugin_names[choice - 1]
            plugin = plugins[name]
            current_state = plugin_enables.get(name, plugin.default_enable)
            plugin_enables[name] = not current_state
            
            # 更新到配置并保存
            self.root_config["plugin_enables"] = plugin_enables
            self.save_config(save_root=True)
            
            # 同步到 PluginManager
            self.plugin_manager.update_plugins_enable(plugin_enables)
            console.print(f"[green]Plugin '{name}' {'enabled' if not current_state else 'disabled'}.[/green]")
            time.sleep(0.5)

    def run_task(self, task_mode, target_path=None, continue_status=False, non_interactive=False, web_mode=False, from_queue=False):
        # 如果是非交互模式，直接跳过菜单
        if target_path is None:
            last_path = self.config.get("label_input_path")
            can_resume = False
            
            if last_path and os.path.exists(last_path):
                abs_last = os.path.abspath(last_path)
                last_parent = os.path.dirname(abs_last)
                last_base = os.path.basename(abs_last)
                if os.path.isfile(last_path):
                    last_base = os.path.splitext(last_base)[0]
                last_opath = os.path.join(last_parent, f"{last_base}_AiNiee_Output")
                if os.path.exists(os.path.join(last_opath, "cache", "AinieeCacheData.json")):
                    can_resume = True

            # Input Mode Selection
            console.clear()
            
            menu_text = f"1. {i18n.get('mode_single_file')}\n2. {i18n.get('mode_batch_folder')}"
            choices = ["0", "1", "2"]
            next_option_idx = 3
            
            if can_resume:
                short_path = last_path if len(last_path) < 60 else "..." + last_path[-57:]
                menu_text += f"\n{next_option_idx}. {i18n.get('mode_resume').format(short_path)}"
                choices.append(str(next_option_idx))
                next_option_idx += 1

            recent_projects = self.config.get("recent_projects", [])
            recent_projects_start_idx = next_option_idx
            
            if recent_projects:
                menu_text += f"\n\n[bold cyan]--- {i18n.get('menu_recent_projects')} ---[/bold cyan]"
                for i, item in enumerate(recent_projects):
                    path = item["path"] if isinstance(item, dict) else item
                    short_path = path if len(path) < 60 else "..." + path[-57:]
                    
                    profile_info = ""
                    if isinstance(item, dict):
                        profile_info = f" [dim]({item.get('profile', 'def')}/{item.get('rules_profile', 'def')})[/dim]"
                    
                    menu_text += f"\n{recent_projects_start_idx + i}. {short_path}{profile_info}"
                    choices.append(str(recent_projects_start_idx + i))

            menu_text += f"\n\n[dim]0. {i18n.get('menu_exit')}[/dim]"
            console.print(Panel(menu_text, title=f"[bold]{i18n.get('menu_input_mode')}[/bold]", expand=False))
            
            prompt_text = i18n.get('prompt_select').strip().rstrip(':').rstrip('：')
            choice = IntPrompt.ask(f"\n{prompt_text}", choices=choices, show_choices=False)
            console.print("\n")
            if choice == 0: return
            
            if can_resume and choice == 3:
                target_path = last_path
                continue_status = True
            elif choice >= recent_projects_start_idx:
                recent_idx = choice - recent_projects_start_idx
                if 0 <= recent_idx < len(recent_projects):
                    item = recent_projects[recent_idx]
                    if isinstance(item, dict):
                        target_path = item["path"]
                        # Auto-switch profiles
                        p_name = item.get("profile")
                        r_p_name = item.get("rules_profile")
                        
                        if p_name and p_name != self.active_profile_name:
                            self.active_profile_name = p_name
                            self.root_config["active_profile"] = p_name
                            console.print(f"[dim]Auto-switched Profile to: {p_name}[/dim]")
                        if r_p_name and r_p_name != self.active_rules_profile_name:
                            self.active_rules_profile_name = r_p_name
                            self.root_config["active_rules_profile"] = r_p_name
                            console.print(f"[dim]Auto-switched Rules Profile to: {r_p_name}[/dim]")
                        
                        if p_name or r_p_name:
                            self.save_config(save_root=True)
                            self.load_config() # Reload to apply merge
                    else:
                        target_path = item
            elif choice == 1: # Single File
                start_path = self.config.get("label_input_path", ".")
                if os.path.isfile(start_path):
                    start_path = os.path.dirname(start_path)
                target_path = self.file_selector.select_path(start_path=start_path, select_file=True, select_dir=False)
            
            elif choice == 2: # Batch Folder
                start_path = self.config.get("label_input_path", ".")
                target_path = self.file_selector.select_path(start_path=start_path, select_file=False, select_dir=True)

            if not target_path:
                return

        # Smart suggestion for folders
        if os.path.isdir(target_path):
            candidates = []
            for ext in ("*.txt", "*.epub"):
                candidates.extend(glob.glob(os.path.join(target_path, ext)))
            
            if len(candidates) == 1:
                file_name = os.path.basename(candidates[0])
                if Confirm.ask(f"\n[cyan]Found a single file '{file_name}' in this directory. Process this file instead of the whole folder?[/cyan]", default=True):
                    target_path = candidates[0]
                    console.print(f"[dim]Switched target to file: {target_path}[/dim]")

        # --- 非交互模式的路径处理 ---
        if not os.path.exists(target_path):
            console.print(f"[red]Error: Input path '{target_path}' not found.[/red]")
            return

        self._update_recent_projects(target_path)
        self.config["label_input_path"] = target_path
        
        # 自动设置输出路径 (如果开启了自动跟随，或者用户未设置输出路径)
        is_auto_output = self.config.get("auto_set_output_path", False)
        if is_auto_output or self.config.get("label_output_path") is None or self.config.get("label_output_path") == "":
            abs_input = os.path.abspath(target_path)
            parent_dir = os.path.dirname(abs_input)
            base_name = os.path.basename(abs_input)
            if os.path.isfile(target_path): base_name = os.path.splitext(base_name)[0]
            opath = os.path.join(parent_dir, f"{base_name}_AiNiee_Output")
            self.config["label_output_path"] = opath
        else:
            opath = self.config.get("label_output_path")

        self.save_config()
        
        # --- NEW: Enhanced Output Directory Handling ---
        if not continue_status and os.path.exists(opath) and not non_interactive:
            cache_exists = os.path.exists(os.path.join(opath, "cache", "AinieeCacheData.json"))
            console.print(Panel(i18n.get("menu_output_exists_prompt"), title=f"[yellow]{i18n.get('menu_output_exists_title')}[/yellow]", expand=False))
            
            options, choices_map = [], {}
            
            if cache_exists:
                options.append(f"1. {i18n.get('option_resume')}")
                choices_map["1"] = "resume"
            else:
                options.append(f"[dim]1. {i18n.get('option_resume')} ({i18n.get('err_resume_no_cache')})[/dim]")

            options.append(f"2. {i18n.get('option_archive')}")
            choices_map["2"] = "archive"
            options.append(f"3. {i18n.get('option_overwrite')}")
            choices_map["3"] = "overwrite"
            options.append(f"0. {i18n.get('option_cancel')}")
            choices_map["0"] = "cancel"

            console.print("\n".join(options))
            
            valid_choices = [k for k, v in choices_map.items() if v != "resume" or cache_exists]
            choice_str = Prompt.ask(f"\n{i18n.get('prompt_select')}", choices=valid_choices, show_choices=False)
            action = choices_map.get(choice_str)

            if action == "resume":
                continue_status = True
            elif action == "archive":
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                backup_path = f"{opath}_backup_{timestamp}"
                try:
                    os.rename(opath, backup_path)
                    console.print(i18n.get('msg_archive_success').format(os.path.basename(backup_path)))
                except OSError as e:
                    console.print(f"[red]Error archiving directory: {e}[/red]")
                    return
                continue_status = False
            elif action == "overwrite":
                if Confirm.ask(i18n.get('msg_overwrite_confirm').format(os.path.basename(opath)), default=False):
                    try:
                        shutil.rmtree(opath)
                        console.print(f"[green]'{os.path.basename(opath)}' deleted.[/green]")
                    except OSError as e:
                        console.print(f"[red]Error deleting directory: {e}[/red]")
                        return
                else:
                    console.print("[yellow]Overwrite cancelled.[/yellow]")
                    return
                continue_status = False
            elif action == "cancel":
                return
        
        # Fallback for non-interactive or simple resume case
        elif not continue_status and os.path.exists(os.path.join(opath, "cache", "AinieeCacheData.json")):
             if non_interactive:
                 continue_status = True
             elif Confirm.ask(f"\n[yellow]Detected existing cache for this file. Resume?[/yellow]", default=True):
                 continue_status = True

        # --- 格式转换询问逻辑 ---
        self.target_output_format = None
        if self.config.get("enable_post_conversion", False) and not non_interactive:
            # 检查是否是电子书格式
            input_ext = os.path.splitext(target_path)[1].lower()
            ebook_exts = [".epub", ".mobi", ".azw3", ".fb2", ".txt", ".docx", ".pdf", ".htmlz", ".kepub"]

            if input_ext in ebook_exts or (os.path.isdir(target_path) and any(
                f.lower().endswith(tuple(ebook_exts)) for f in os.listdir(target_path) if os.path.isfile(os.path.join(target_path, f))
            )):
                if self.config.get("fixed_output_format_switch", False):
                    # 使用固定格式
                    self.target_output_format = self.config.get("fixed_output_format", "epub")
                else:
                    # 询问用户选择格式
                    console.print(f"\n[cyan]{i18n.get('msg_format_conversion_hint')}[/cyan]")
                    format_choices = ["epub", "mobi", "azw3", "fb2", "pdf", "txt", "docx", "htmlz"]

                    table = Table(show_header=False, box=None)
                    for idx, fmt in enumerate(format_choices, 1):
                        table.add_row(f"[cyan]{idx}.[/]", fmt.upper())
                    table.add_row(f"[dim]0.[/dim]", f"[dim]{i18n.get('opt_none')}[/dim]")
                    console.print(table)

                    fmt_choice = IntPrompt.ask(
                        i18n.get('prompt_select_output_format'),
                        choices=[str(i) for i in range(len(format_choices) + 1)],
                        show_choices=False,
                        default=0
                    )
                    if fmt_choice > 0:
                        self.target_output_format = format_choices[fmt_choice - 1]

        console.print(f"[dim]{i18n.get('label_input')}: {target_path}[/dim]")
        console.print(f"[dim]{i18n.get('label_output')}: {opath}[/dim]")

        # 记录任务开始操作
        task_type_name = "翻译" if task_mode == TaskType.TRANSLATION else "润色" if task_mode == TaskType.POLISH else "翻译&润色"
        file_ext = os.path.splitext(target_path)[1].upper() if os.path.isfile(target_path) else "文件夹"
        self.operation_logger.log(f"开始{task_type_name}任务 -> 文件类型:{file_ext}", "TASK")

        # Initialize variables for finally block safety
        current_listener = None
        log_file = None
        task_success = False

        original_stdout, original_stderr = sys.stdout, sys.stderr
        
        # Ensure our UI console uses the REAL stdout to avoid recursion
        self.ui_console = Console(file=original_stdout)

        # Start Logic
        if web_mode:
            self.ui = WebLogger(stream=original_stdout, show_detailed=self.config.get("show_detailed_logs", False))
        else:
            self.ui = TaskUI(parent_cli=self, i18n=i18n)
            # 设置 TUIHandler 的 UI 实例
            TUIHandler.set_ui(self.ui)

        Base.print = self.ui.log
        self.stop_requested = False
        self.live_state = [True] # 必须在这里初始化，防止 LogStream 报错

        # 确保 TaskExecutor 的配置与 CLIMenu 的配置同步
        self.task_executor.config.load_config_from_dict(self.config)
        
        if self.input_listener.disabled and not web_mode:
            self.ui.log("[bold yellow]Warning: Keyboard listener failed to initialize (no TTY found). Hotkeys will be disabled.[/bold yellow]")

        original_ext = os.path.splitext(target_path)[1].lower()
        is_middleware_converted = False
        is_xlsx_converted = False

        # Patch tqdm to avoid conflict with Rich Live
        import ModuleFolders.Service.TaskExecutor.TaskExecutor as TaskExecutorModule
        TaskExecutorModule.tqdm = lambda x, **kwargs: x
        
        # Initialize suppression flags early
        import ModuleFolders.Infrastructure.Tokener.TiktokenLoader as TiktokenLoaderModule
        import ModuleFolders.Domain.FileReader.ReaderUtil as ReaderUtilModule
        TiktokenLoaderModule._SUPPRESS_OUTPUT = True
        ReaderUtilModule._SUPPRESS_OUTPUT = True
        
        # --- NEW: Session Logger & Resume Log Recovery ---
        log_file = None
        if self.config.get("enable_session_logging", True):
            try:
                log_dir = os.path.join(opath, "logs")
                os.makedirs(log_dir, exist_ok=True)
                
                # 生成基于路径的稳定 Hash 标识，用于断点续传时的日志识别
                import hashlib
                file_id = hashlib.md5(os.path.abspath(target_path).encode('utf-8')).hexdigest()[:8]
                log_name = f"session_{file_id}_{time.strftime('%Y%m%d')}.log"
                log_path = os.path.join(log_dir, log_name)
                
                # 如果是断点续传且日志已存在，先读取历史日志到 TUI
                if continue_status and os.path.exists(log_path) and not web_mode:
                    try:
                        with open(log_path, 'r', encoding='utf-8') as f:
                            # 读取最后 50 行
                            history = f.readlines()[-50:]
                            for line in history:
                                if line.strip():
                                    # 剥离历史时间戳后载入 UI
                                    clean_line = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s+', '', line.strip())
                                    self.ui.logs.append(Text(f"[RESUME] {clean_line}", style="dim"))
                    except: pass

                log_file = open(log_path, "a", encoding="utf-8") # 使用追加模式
                # 绑定到 UI 实例以实现实时写入
                if hasattr(self.ui, "log_file"):
                    self.ui.log_file = log_file
            except: pass

        # Redirect stdout/stderr to capture errors in UI
        class LogStream:
            _local = threading.local() # For recursion guard

            def __init__(self, ui, f=None, parent=None): 
                self.ui = ui
                self.f = f
                self.parent = parent
                self._local.is_writing = False

            def write(self, msg): 
                if hasattr(self._local, 'is_writing') and self._local.is_writing:
                    return

                if not msg or msg == '\n': return
                msg_str = str(msg)
                
                # 网页模式下的统计数据行，必须直接通过真正的 stdout 发送
                if "[STATS]" in msg_str:
                    original_stdout.write(msg_str + '\n')
                    original_stdout.flush()
                    return

                # 只有当 UI 没有接管文件日志写入时，才由 LogStream 负责写入
                if self.f and not (hasattr(self.ui, "log_file") and getattr(self.ui, "log_file")):
                    try:
                        self.f.write(f"[{time.strftime('%H:%M:%S')}] {msg_str}\n")
                        self.f.flush()
                    except: pass

                if "[STATUS]" in msg_str:
                    return
                
                self._local.is_writing = True
                try:
                    # Always try to log to UI, which handles takeover logic internally
                    clean_msg = msg_str.strip()
                    if clean_msg:
                        self.ui.log(clean_msg)
                except:
                    pass
                finally:
                    self._local.is_writing = False

            def flush(self): pass
        
        sys.stdout = sys.stderr = LogStream(self.ui, log_file, self)

        # 启动键盘监听
        if not web_mode:
            self.input_listener.start()
            self.input_listener.clear()

        # 定义完成事件
        self.task_running = True; finished = threading.Event(); success = threading.Event()

        from ModuleFolders.Base.EventManager import EventManager

        # --- 任务追踪状态 ---
        self._is_critical_failure = False
        self._last_crash_msg = None
        self._api_error_count = 0  # 重置API错误计数
        self._api_error_messages = []  # 重置API错误信息
        self._show_diagnostic_hint = False  # 重置诊断提示
        self._enter_diagnostic_on_exit = False  # 是否在退出后进入诊断菜单

        def on_complete(e, d): 
            self.ui.log(f"[bold green]✓ {i18n.get('msg_task_completed')}[/bold green]")
            success.set(); finished.set()
        
        def on_stop(e, d):
            # 只有在收到明确的任务停止完成事件时才记录日志
            if e == Base.EVENT.TASK_STOP_DONE:
                self.ui.log(f"[bold yellow]{i18n.get('msg_task_stopped')}[/bold yellow]")

            # 记录是否为熔断导致的停止
            if d and isinstance(d, dict) and d.get("status") == "critical_error":
                self._is_critical_failure = True
                self.ui.log(f"[bold red]熔断：因连续错误过多任务已暂停。[/bold red]")
        
        # 订阅事件
        EventManager.get_singleton().subscribe(Base.EVENT.TASK_COMPLETED, on_complete)
        EventManager.get_singleton().subscribe(Base.EVENT.TASK_STOP_DONE, on_stop)
        EventManager.get_singleton().subscribe(Base.EVENT.SYSTEM_STATUS_UPDATE, on_stop) # 借用 on_stop 处理状态更新
        EventManager.get_singleton().subscribe(Base.EVENT.TASK_UPDATE, self.ui.update_progress)
        EventManager.get_singleton().subscribe(Base.EVENT.SYSTEM_STATUS_UPDATE, self.ui.update_status)
        EventManager.get_singleton().subscribe(Base.EVENT.TUI_SOURCE_DATA, self.ui.on_source_data)
        EventManager.get_singleton().subscribe(Base.EVENT.TUI_RESULT_DATA, self.ui.on_result_data)
        
        last_task_data = {"line": 0, "token": 0, "time": 0}
        def track_last_data(e, d):
            nonlocal last_task_data
            if d and isinstance(d, dict):
                last_task_data = d
        EventManager.get_singleton().subscribe(Base.EVENT.TASK_UPDATE, track_last_data)

        # Wrapper to run task logic (so we can use it with or without Live)
        def run_task_logic():
                nonlocal is_xlsx_converted
                self.ui.log(f"{i18n.get('msg_task_started')}")

                # --- Middleware Conversion Logic (从配置读取) ---
                calibre_enabled = self.config.get("enable_calibre_middleware", True)
                middleware_exts = self.config.get("calibre_middleware_exts", ['.mobi', '.azw3', '.kepub', '.fb2', '.lit', '.lrf', '.pdb', '.pmlz', '.rb', '.rtf', '.tcr', '.txtz', '.htmlz']) if calibre_enabled else []
                xlsx_middleware_exts = self.config.get("xlsx_middleware_exts", ['.xlsx'])

                # We need to access target_path from outer scope.
                # Since we modify it, we should be careful.
                # In python 3, we can use nonlocal for rebind, but target_path is local variable.
                # Let's use a mutable container or just refer to it.
                # Actually, the previous code structure had this logic inside 'with Live'.
                # We will just copy-paste the logic here.

                current_target_path = target_path
                is_middleware_converted_local = False

                if original_ext in middleware_exts:
                    is_middleware_converted_local = True
                    base_name = os.path.splitext(os.path.basename(current_target_path))[0]
                    os.makedirs(opath, exist_ok=True)
                    temp_conv_dir = os.path.join(opath, "temp_conv")

                    potential_epub = os.path.join(temp_conv_dir, f"{base_name}.epub")
                    if os.path.exists(potential_epub) and os.path.getsize(potential_epub) > 0:
                        self.ui.log(i18n.get("msg_epub_reuse").format(os.path.basename(potential_epub)))
                        current_target_path = potential_epub
                    else:
                        # 先检查Calibre是否可用
                        calibre_path = ensure_calibre_available()
                        if not calibre_path:
                            self.ui.log("[red]Calibre is required for this format. Task cancelled.[/red]")
                            time.sleep(2); return

                        self.ui.log(i18n.get("msg_epub_conv_start").format(original_ext))
                        os.makedirs(temp_conv_dir, exist_ok=True)
                        conv_script = os.path.join(PROJECT_ROOT, "批量电子书整合.py")
                        cmd = f'uv run "{conv_script}" -p "{current_target_path}" -f 1 -m novel -op "{temp_conv_dir}" -o "{base_name}" --AiNiee'
                        try:
                            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                            if result.returncode == 0:
                                epubs = [f for f in os.listdir(temp_conv_dir) if f.endswith(".epub")]
                                if epubs:
                                    new_path = os.path.join(temp_conv_dir, epubs[0])
                                    self.ui.log(i18n.get("msg_epub_conv_success").format(os.path.basename(new_path)))
                                    current_target_path = new_path
                                else: raise Exception("No EPUB found")
                            else: raise Exception(f"Conversion failed: {result.stderr}")
                        except Exception as e:
                            self.ui.log(i18n.get("msg_epub_conv_fail").format(e))
                            time.sleep(2); return

                # --- XLSX Middleware Conversion Logic ---
                is_xlsx_converted = False
                if original_ext in xlsx_middleware_exts:
                    is_xlsx_converted = True
                    base_name = os.path.splitext(os.path.basename(current_target_path))[0]
                    # 确保输出目录和临时转换文件夹已创建
                    os.makedirs(opath, exist_ok=True)
                    temp_conv_dir = os.path.join(opath, "temp_xlsx_conv")

                    # 检查是否已存在转换好的CSV文件
                    potential_csv = os.path.join(temp_conv_dir, f"{base_name}.csv")
                    metadata_file = os.path.join(temp_conv_dir, "xlsx_metadata.json")

                    if os.path.exists(potential_csv) and os.path.exists(metadata_file):
                        self.ui.log(i18n.get("msg_xlsx_reuse").format(os.path.basename(potential_csv)))
                        current_target_path = temp_conv_dir  # 指向包含CSV文件的目录
                    else:
                        self.ui.log(i18n.get("msg_xlsx_conv_start").format(original_ext))
                        os.makedirs(temp_conv_dir, exist_ok=True)
                        conv_script = os.path.join(PROJECT_ROOT, "xlsx_converter.py")

                        # 调用XLSX转换器：XLSX -> CSV
                        cmd = f'uv run "{conv_script}" -i "{current_target_path}" -o "{temp_conv_dir}" -m to_csv --ainiee'
                        try:
                            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                            if result.returncode == 0:
                                # 检查转换结果
                                csv_files = [f for f in os.listdir(temp_conv_dir) if f.endswith(".csv")]
                                if csv_files:
                                    self.ui.log(i18n.get("msg_xlsx_conv_success").format(len(csv_files)))
                                    current_target_path = temp_conv_dir  # 指向包含CSV文件的目录
                                else: raise Exception("No CSV files found")
                            else: raise Exception(f"XLSX conversion failed: {result.stderr}")
                        except Exception as e:
                            self.ui.log(i18n.get("msg_xlsx_conv_fail").format(e))
                            time.sleep(2); return

                # --- 1. 文件与缓存加载 ---
                try:
                    # 如果是继续任务，尝试直接加载缓存
                    cache_loaded = False
                    if continue_status:
                        cache_file_path = os.path.join(opath, "cache", "AinieeCacheData.json")
                        if os.path.exists(cache_file_path):
                            self.ui.log(f"[cyan]Resuming from cache: {cache_file_path}[/cyan]")
                            self.cache_manager.load_from_file(opath)
                            cache_loaded = True
                    
                    if not cache_loaded:
                        cache_project = self.file_reader.read_files(self.config.get("translation_project", "AutoType"), current_target_path, self.config.get("exclude_rule_str", ""))
                        if not cache_project:
                            self.ui.log("[red]No files loaded.[/red]")
                            time.sleep(2); raise Exception("Load failed")
                        self.cache_manager.load_from_project(cache_project)
                        
                    total_items = self.cache_manager.get_item_count()
                    translated = self.cache_manager.get_item_count_by_status(TranslationStatus.TRANSLATED)
                    self.ui.update_progress(None, {"line": translated, "total_line": total_items})
                except Exception as e:
                    self.ui.log(f"[red]Error during initialization: {e}[/red]")
                    time.sleep(3); raise e

                # --- 3. 启动任务 ---
                EventManager.get_singleton().emit(
                    Base.EVENT.TASK_START, 
                    {
                        "continue_status": continue_status, 
                        "current_mode": task_mode,
                        "session_input_path": current_target_path,
                        "session_output_path": opath
                    }
                )

                # --- 4. 主循环与输入监听 ---
                is_paused = False
                while not finished.is_set():
                    # 及时介入：如果监测到致命错误（如 Traceback），主动中断循环并进入分析菜单
                    if self._is_critical_failure and not web_mode:
                        self.ui.log(f"[bold red]Detection: Critical error found in logs. Intervening for analysis...[/bold red]")
                        time.sleep(2)
                        break

                    if not web_mode:
                        key = self.input_listener.get_key()
                        if key:
                            if key == 'q':
                                self.ui.log("[bold red]Stop requested via keyboard...[/bold red]")
                                self.signal_handler(None, None)
                            elif key == 'p':
                                if Base.work_status == Base.STATUS.TASKING:
                                    self.ui.log("[bold yellow]Pausing System (Stopping processes)...[/bold yellow]")
                                    # 更新状态通知 TaskExecutor 停止
                                    EventManager.get_singleton().emit(Base.EVENT.TASK_STOP, {})
                                    self.ui.update_status(None, {"status": "paused"})
                                    is_paused = True
                            elif key == 'r':
                                if is_paused:
                                    self.ui.log("[bold green]Resuming System...[/bold green]")
                                    # 使用 continue_status=True 和 silent=True 重新启动
                                    EventManager.get_singleton().emit(
                                        Base.EVENT.TASK_START, 
                                        {
                                            "continue_status": True, 
                                            "current_mode": task_mode,
                                            "session_input_path": current_target_path,
                                            "session_output_path": opath,
                                            "silent": True
                                        }
                                    )
                                    self.ui.update_status(None, {"status": "normal"})
                                    is_paused = False
                            elif key == 'v':
                                self.ui.toggle_log_filter()
                            elif key == '[' or key == ']':
                                cfg = self.task_executor.config
                                if cfg.tokens_limit_switch:
                                    current_val = cfg.tokens_limit
                                    step = 100
                                    new_val = max(100, current_val - step) if key == '[' else min(16000, current_val + step)
                                    cfg.tokens_limit = new_val
                                    self.ui.log(i18n.get('msg_split_limit_changed').format(new_val, "tokens"))
                                else:
                                    current_val = cfg.lines_limit
                                    step = 1
                                    new_val = max(1, current_val - step) if key == '[' else min(100, current_val + step)
                                    cfg.lines_limit = new_val
                                    self.ui.log(i18n.get('msg_split_limit_changed').format(new_val, "lines"))
                            elif key == 'n':
                                current_file_path = self.ui._last_progress_data.get('file_path_full')
                                if current_file_path:
                                    file_name = os.path.basename(current_file_path)
                                    self.ui.log(i18n.get('msg_skipping_file').format(file_name))

                                    # 在队列模式下处理跳过任务
                                    if hasattr(self, '_is_queue_mode') and self._is_queue_mode:
                                        try:
                                            from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
                                            qm = QueueManager()

                                            # 将当前跳过的任务移动到队列末尾
                                            success, message = qm.skip_task_to_end(current_file_path)
                                            if success:
                                                self.ui.log(i18n.get('msg_queue_task_moved_to_end').format(file_name, message.split()[-1]))
                                            else:
                                                self.ui.log(f"[yellow]{i18n.get('msg_queue_task_move_failed')}: {message}[/yellow]")

                                            # 显示下一个任务信息
                                            next_index, next_task = qm.get_next_unlocked_task()
                                            if next_task:
                                                next_file_name = os.path.basename(next_task.input_path)
                                                task_type_name = i18n.get("task_type_translation") if next_task.task_type == TaskType.TRANSLATION else \
                                                                 i18n.get("task_type_polishing") if next_task.task_type == TaskType.POLISH else \
                                                                 i18n.get("task_type_all_in_one") if next_task.task_type == TaskType.TRANSLATE_AND_POLISH else "Unknown"
                                                self.ui.log(i18n.get('msg_queue_next_task').format(next_index + 1, task_type_name, next_file_name))
                                            else:
                                                self.ui.log(i18n.get('msg_queue_no_more_tasks'))
                                        except Exception as e:
                                            pass  # 静默忽略队列查询错误

                                    EventManager.get_singleton().emit("TASK_SKIP_FILE_REQUEST", {"file_path_full": current_file_path})
                            elif key == '-': # 减少线程
                                old_val = self.task_executor.config.actual_thread_counts
                                new_val = max(1, old_val - 1)
                                self.task_executor.config.actual_thread_counts = new_val
                                self.task_executor.config.user_thread_counts = new_val
                                self.config["user_thread_counts"] = new_val
                                self.ui.log(f"[yellow]{i18n.get('msg_thread_changed').format(new_val)}[/yellow]")
                            elif key == '+': # 增加线程
                                old_val = self.task_executor.config.actual_thread_counts
                                new_val = min(100, old_val + 1)
                                self.task_executor.config.actual_thread_counts = new_val
                                self.task_executor.config.user_thread_counts = new_val
                                self.config["user_thread_counts"] = new_val
                                self.ui.log(f"[green]{i18n.get('msg_thread_changed').format(new_val)}[/green]")
                            elif key == 'k': # 热切换 API
                                self.ui.log(f"[cyan]{i18n.get('msg_api_switching_manual')}[/cyan]")
                                EventManager.get_singleton().emit(Base.EVENT.TASK_API_STATUS_REPORT, {"force_switch": True})
                            elif key == 'm': # Open Web Monitor
                                self.handle_monitor_shortcut()
                            elif key == 'e': # Open Queue Editor (Queue mode only)
                                if hasattr(self, '_is_queue_mode') and self._is_queue_mode:
                                    self.handle_queue_editor_shortcut()
                                else:
                                    self.ui.log(f"[yellow]{i18n.get('msg_queue_editor_not_available')}[/yellow]")
                            elif key == 'h': # Open Web Queue Manager (Queue mode only)
                                if hasattr(self, '_is_queue_mode') and self._is_queue_mode:
                                    self.handle_web_queue_shortcut()
                                else:
                                    self.ui.log(f"[yellow]{i18n.get('msg_web_queue_not_available')}[/yellow]")
                            elif key == 'y': # 进入诊断模式 (当检测到多次API错误时)
                                if self._show_diagnostic_hint or self._api_error_count >= 3:
                                    self.ui.log(f"[bold cyan]{i18n.get('msg_entering_diagnostic')}[/bold cyan]")
                                    # 停止当前任务
                                    EventManager.get_singleton().emit(Base.EVENT.TASK_STOP, {})
                                    time.sleep(1)
                                    # 设置标志，退出后进入诊断菜单
                                    self._enter_diagnostic_on_exit = True
                                    self._is_critical_failure = True
                                    break

                    time.sleep(0.1)
                
                return is_middleware_converted_local

        try:
            if web_mode:
                is_middleware_converted = run_task_logic()
            else:
                # 提前启动 Live，确保加载过程可见
                with Live(self.ui.layout, console=self.ui_console, refresh_per_second=10, screen=True, transient=False) as live:
                    is_middleware_converted = run_task_logic()

        except KeyboardInterrupt: self.signal_handler(None, None)
        except Exception as e:
            # Capture and log the error before TUI disappears
            import traceback
            error_full = traceback.format_exc()
            err_msg = f"[bold red]Critical Task Error: {str(e)}[/bold red]"
            if hasattr(self, "ui") and self.ui:
                self.ui.log(err_msg)
            else:
                console.print(err_msg)
            time.sleep(1) # Give a moment for the log to register
            
            # 标记为真正的崩溃
            self._last_crash_msg = error_full
            self._is_critical_failure = True

        finally:
            if not web_mode:
                self.input_listener.stop()
            if log_file: log_file.close()
            
            # --- Ensure Takeover Mode is disabled before UI cleanup ---
            if hasattr(self, "ui") and isinstance(self.ui, TaskUI):
                with self.ui._lock:
                    self.ui.taken_over = False
                # The Live context manager is about to exit, let it do one last clean frame
                time.sleep(0.2)

            sys.stdout, sys.stderr = original_stdout, original_stderr
            self.task_running = False; Base.print = self.original_print
            TUIHandler.clear()  # 清理 TUIHandler 的 UI 引用
            EventManager.get_singleton().unsubscribe(Base.EVENT.TASK_COMPLETED, on_complete)
            EventManager.get_singleton().unsubscribe(Base.EVENT.TASK_STOP_DONE, on_stop)
            EventManager.get_singleton().unsubscribe(Base.EVENT.SYSTEM_STATUS_UPDATE, on_stop)
            EventManager.get_singleton().unsubscribe(Base.EVENT.TASK_UPDATE, self.ui.update_progress)
            EventManager.get_singleton().unsubscribe(Base.EVENT.TASK_UPDATE, track_last_data)
            
            # --- 报错处理逻辑 (仅在致命失败时触发) ---
            if self._is_critical_failure and not success.is_set():
                # 检查是否是用户主动按Y进入诊断模式
                if getattr(self, '_enter_diagnostic_on_exit', False) and not non_interactive:
                    # 用户按Y主动进入诊断，显示诊断菜单
                    self.qa_menu()
                else:
                    # 只有发生了崩溃异常，或触发了 critical_error 熔断，且任务最终未完成时才弹出
                    crash_msg = self._last_crash_msg or "Task was terminated due to exceeding critical error threshold."
                    if not non_interactive:
                        self.handle_crash(crash_msg)
                    else:
                        console.print(f"[bold red]Task failed fatally. Check logs.[/bold red]")
            
            if success.is_set():
                if self.config.get("enable_task_notification", True):
                    try:
                        import winsound
                        winsound.MessageBeep()
                    except ImportError:
                        print("提示：winsound模块在此系统上不可用（Linux/Docker环境）")
                        pass
                    except:
                        print("\a")
                
                # Summary Report
                lines = last_task_data.get("line", 0); tokens = last_task_data.get("token", 0); duration = last_task_data.get("time", 1)
                if not web_mode:
                    report_table = Table(show_header=False, box=None, padding=(0, 2))
                    report_table.add_row(f"[cyan]{i18n.get('label_report_total_lines')}:[/]", f"[bold]{lines}[/]")
                    report_table.add_row(f"[cyan]{i18n.get('label_report_total_tokens')}:[/]", f"[bold]{tokens}[/]")
                    report_table.add_row(f"[cyan]{i18n.get('label_report_total_time')}:[/]", f"[bold]{duration:.1f}s[/]")
                    console.print("\n"); console.print(Panel(report_table, title=f"[bold green]✓ {i18n.get('msg_task_report_title')}[/bold green]", expand=False))
                else:
                    print(f"[STATS] RPM: 0.00 | TPM: 0.00k | Progress: {lines}/{lines} | Tokens: {tokens}") # Final Stat

            if success.is_set() and is_middleware_converted:
                try:
                    temp_dir = os.path.join(opath, "temp_conv")
                    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                except: pass

            # XLSX restoration and cleanup
            if success.is_set() and is_xlsx_converted and self.config.get("enable_auto_restore_xlsx", True):
                try:
                    temp_xlsx_dir = os.path.join(opath, "temp_xlsx_conv")

                    # First, restore CSV back to XLSX
                    self.ui.log("[cyan]Restoring XLSX format...[/cyan]")
                    conv_script = os.path.join(PROJECT_ROOT, "xlsx_converter.py")

                    # Call XLSX converter: CSV -> XLSX
                    cmd = f'uv run "{conv_script}" -i "{temp_xlsx_dir}" -o "{opath}" -m to_xlsx --ainiee'
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

                    if result.returncode == 0:
                        self.ui.log(i18n.get("msg_xlsx_restore_success"))

                        # Clean up temporary CSV files
                        if os.path.exists(temp_xlsx_dir):
                            shutil.rmtree(temp_xlsx_dir)

                    else:
                        self.ui.log(i18n.get("msg_xlsx_restore_fail").format(result.stderr))

                except Exception as e:
                    self.ui.log(f"[yellow]XLSX restoration error: {e}[/yellow]")
            
            if not web_mode and not non_interactive and not from_queue:
                Prompt.ask(f"\n{i18n.get('msg_task_ended')}")
            
            # --- Post-Task Logic (Reverse Conversion) ---
            if task_success and is_middleware_converted and self.config.get("enable_auto_restore_ebook", False):
                 self.ui.log(f"[cyan]Restoring original format...[/cyan]")
                 # ... Reuse existing logic or simplified ...
                 # Since I can't easily reuse the exact block without copying, I'll implement a simple one
                 output_dir = self.config.get("label_output_path")
                 if output_dir:
                     translated_epubs = [f for f in os.listdir(output_dir) if f.endswith(".epub")]
                     if translated_epubs:
                         base_name = os.path.splitext(os.path.basename(target_path))[0] # This is the temp epub name
                         # Wait, target_path was swapped to the temp epub. 
                         # We need to map back to original ext.
                         # Simplified: Just run the restore command
                         conv_script = os.path.join(PROJECT_ROOT, "批量电子书整合.py")
                         cmd = f'uv run "{conv_script}" -p "{target_path}" -f 1 -m novel -op "{temp_conv_dir}" -o "{base_name} --AiNiee"'
                         # Actually the restore logic in original code was complex mapping.
                         # For now, let's skip complex restoration to keep it safe or just log.
                         self.ui.log("[dim]Auto-restore skipped in new architecture (manual restore recommended if needed).[/dim]")

            # --- Post-Task: Format Conversion ---
            if task_success and self.target_output_format:
                output_dir = self.config.get("label_output_path")
                if output_dir:
                    output_files = [f for f in os.listdir(output_dir) if f.endswith(".epub")]
                    if output_files:
                        # 使用新的Calibre检测和下载逻辑
                        calibre_path = ensure_calibre_available()
                        if calibre_path:
                            self.ui.log(f"[cyan]Converting to {self.target_output_format.upper()} format...[/cyan]")
                            for epub_file in output_files:
                                src_path = os.path.join(output_dir, epub_file)
                                dst_name = os.path.splitext(epub_file)[0] + f".{self.target_output_format}"
                                dst_path = os.path.join(output_dir, dst_name)
                                try:
                                    result = subprocess.run(
                                        [calibre_path, src_path, dst_path],
                                        capture_output=True, text=True, timeout=300
                                    )
                                    if result.returncode == 0:
                                        self.ui.log(f"[green]✓ Converted: {dst_name}[/green]")
                                    else:
                                        self.ui.log(f"[yellow]Conversion warning: {result.stderr[:200]}[/yellow]")
                                except Exception as e:
                                    self.ui.log(f"[yellow]Conversion error: {e}[/yellow]")
                        else:
                            self.ui.log("[dim]Format conversion skipped.[/dim]")

            # --- Post-Task: Auto AI Proofread ---
            if task_success and task_mode == TaskType.TRANSLATION and self.config.get("enable_auto_proofread", False):
                if not web_mode:
                    console.print(f"\n[cyan]自动AI校对已开启，正在执行校对...[/cyan]")
                    try:
                        self._execute_proofread(opath)
                    except Exception as e:
                        console.print(f"[yellow]AI校对执行出错: {e}[/yellow]")

            # Summary
            if task_success:
                self.ui.log("[bold green]All Done![/bold green]")
                if self.config.get("enable_task_notification", True):
                    try:
                        import winsound
                        winsound.MessageBeep()
                    except ImportError:
                        print("提示：winsound模块在此系统上不可用（Linux/Docker环境）")
                        pass
                    except:
                        print("\a")
            
            if not non_interactive and not web_mode and not from_queue:
                Prompt.ask(f"\n{i18n.get('msg_task_ended')}")


    def run_all_in_one(self):
        """Sequential execution of translation and then polishing."""
        start_path = self.config.get("label_input_path", ".")
        target_path = self.file_selector.select_path(start_path=start_path)
        if not target_path: return

        # 1. Run Translation
        self.run_task(
            TaskType.TRANSLATION,
            target_path=target_path,
            continue_status=False,
            from_queue=True # Suppress "Press Enter"
        )
        
        # 2. Check stop signal
        if Base.work_status == Base.STATUS.STOPING:
             return

        # 3. Run Polishing
        self.run_task(
            TaskType.POLISH,
            target_path=target_path,
            continue_status=True, # Resume based on translation output
            from_queue=False # Allow "Press Enter" on final completion
        )

    def run_export_only(self, target_path=None, non_interactive=False):
        # 1. Select Target (if in interactive mode)
        if target_path is None:
            last_path = self.config.get("label_input_path")
            can_resume = last_path and os.path.exists(last_path)
            
            console.clear()
            menu_text = f"1. {i18n.get('mode_single_file')}\n2. {i18n.get('mode_batch_folder')}"
            if can_resume:
                short_path = last_path if len(last_path) < 40 else "..." + last_path[-37:]
                menu_text += f"\n3. {i18n.get('mode_resume').format(short_path)}"
            
            console.print(Panel(menu_text, title=f"[bold]{i18n.get('menu_export_only')}[/bold]", expand=False))
            
            choices = ["0", "1", "2"]
            if can_resume:
                choices.append("3")
                
            prompt_txt = i18n.get('prompt_select').strip().rstrip(':').rstrip('：')
            choice = IntPrompt.ask(f"\n{prompt_txt}", choices=choices, show_choices=False)
            
            if choice == 0: return
            
            if choice == 3:
                target_path = last_path
            else:
                is_file_mode = choice == 1
                start_path = self.config.get("label_input_path", ".")
                if is_file_mode and os.path.isfile(start_path):
                    start_path = os.path.dirname(start_path)

                target_path = self.file_selector.select_path(
                    start_path=start_path,
                    select_file=is_file_mode,
                    select_dir=not is_file_mode
                )
            if not target_path: 
                return

        # Smart suggestion for folders
        if os.path.isdir(target_path):
            candidates = []
            for ext in ("*.txt", "*.epub"):
                candidates.extend(glob.glob(os.path.join(target_path, ext)))
            
            if len(candidates) == 1:
                file_name = os.path.basename(candidates[0])
                if Confirm.ask(f"\n[cyan]Found a single file '{file_name}' in this directory. Search for cache based on this file instead of the folder?[/cyan]", default=True):
                    target_path = candidates[0]
                    console.print(f"[dim]Switched target to file: {target_path}[/dim]")

        # 2. Setup paths
        if not os.path.exists(target_path):
            console.print(f"[red]Error: Input path '{target_path}' not found.[/red]")
            return
            
        abs_input = os.path.abspath(target_path)
        parent_dir = os.path.dirname(abs_input)
        base_name = os.path.basename(abs_input)
        if os.path.isfile(target_path):
            base_name = os.path.splitext(base_name)[0]
        opath = os.path.join(parent_dir, f"{base_name}_AiNiee_Output")
        
        # 3. Load cache
        cache_path = os.path.join(opath, "cache", "AinieeCacheData.json")
        proofread_cache_path = os.path.join(opath, "cache", "AinieeCacheData_proofread.json")

        while not os.path.exists(cache_path):
            console.print(f"\n[yellow]Cache not found at default path: {cache_path}[/yellow]")
            if non_interactive:
                console.print(f"[red]Aborting in non-interactive mode.[/red]")
                return
            opath = Prompt.ask(i18n.get('msg_enter_output_path')).strip().strip('"').strip("'")
            if opath.lower() == 'q':
                return
            cache_path = os.path.join(opath, "cache", "AinieeCacheData.json")
            proofread_cache_path = os.path.join(opath, "cache", "AinieeCacheData_proofread.json")

        # 检查是否存在AI校对版本的cache
        use_proofread_cache = False
        if os.path.exists(proofread_cache_path) and not non_interactive:
            console.print(f"\n[cyan]检测到AI校对版本的cache文件[/cyan]")
            console.print("  [1] 使用原始翻译版本")
            console.print("  [2] 使用AI校对版本 (推荐)")
            cache_choice = IntPrompt.ask("请选择", choices=["1", "2"], default="2")
            if cache_choice == 2:
                use_proofread_cache = True
                cache_path = proofread_cache_path
                console.print("[green]将使用AI校对版本导出[/green]")

        try:
            with console.status(f"[cyan]{i18n.get('msg_export_started')}[/cyan]"):
                project = CacheManager.read_from_file(cache_path)
                
                self.task_executor.config.initialize(self.config)
                cfg = self.task_executor.config
                output_config = {
                    "translated_suffix": cfg.output_filename_suffix,
                    "bilingual_suffix": "_bilingual",
                    "bilingual_order": cfg.bilingual_text_order 
                }
                
                self.file_outputer.output_translated_content(
                    self.cache_manager.project if hasattr(self.cache_manager, 'project') and self.cache_manager.project else project,
                    opath, 
                    target_path, 
                    output_config,
                    cfg
                )
            console.print(f"\n[green]✓ {i18n.get('msg_export_completed')}[/green]")
            console.print(f"[dim]Output: {opath}[/dim]")
        except Exception as e:
            console.print(f"[red]Export Error: {e}[/red]")
            
        Prompt.ask(f"\n{i18n.get('msg_press_enter')}")

    def start_web_server(self):
        try:
            import fastapi
            import uvicorn
        except ImportError:
            console.print("[red]Missing dependencies: fastapi, uvicorn. Please install them to use Web Server.[/red]")
            console.print("Try: pip install fastapi uvicorn[standard]")
            Prompt.ask("\nPress Enter to return...")
            return

        from Tools.WebServer.web_server import run_server
        import Tools.WebServer.web_server as ws_module
        
        # --- Inject Host Logic ---
        
        def host_create_profile(new_name, base_name=None):
            # Same robust logic as CLI
            if not new_name: raise Exception("Name empty")
            new_path = os.path.join(self.profiles_dir, f"{new_name}.json")
            if os.path.exists(new_path): raise Exception("Exists")
            
            # 1. Preset
            preset = {}
            preset_path = os.path.join(PROJECT_ROOT, "Resource", "platforms", "preset.json")
            if os.path.exists(preset_path):
                with open(preset_path, 'r', encoding='utf-8') as f: preset = json.load(f)
            
            # 2. Base
            base_config = {}
            if not base_name: base_name = self.active_profile_name
            base_path = os.path.join(self.profiles_dir, f"{base_name}.json")
            if os.path.exists(base_path):
                with open(base_path, 'r', encoding='utf-8') as f: base_config = json.load(f)
            
            # 3. Merge
            preset.update(base_config)
            
            # 4. Save
            with open(new_path, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=4, ensure_ascii=False)

        def host_rename_profile(old_name, new_name):
            old_path = os.path.join(self.profiles_dir, f"{old_name}.json")
            new_path = os.path.join(self.profiles_dir, f"{new_name}.json")
            if not os.path.exists(old_path): raise Exception("Not found")
            if os.path.exists(new_path): raise Exception("Target exists")
            
            os.rename(old_path, new_path)
            
            # Update Active if needed
            if self.active_profile_name == old_name:
                self.active_profile_name = new_name
                self.root_config["active_profile"] = new_name
                self.save_config(save_root=True)

        def host_delete_profile(name):
            target = os.path.join(self.profiles_dir, f"{name}.json")
            if not os.path.exists(target): raise Exception("Not found")
            if name == self.active_profile_name: raise Exception("Cannot delete active profile")
            
            # Check count
            cnt = len([f for f in os.listdir(self.profiles_dir) if f.endswith(".json")])
            if cnt <= 1: raise Exception("Cannot delete last profile")
            
            os.remove(target)

        ws_module.profile_handlers['create'] = host_create_profile
        ws_module.profile_handlers['rename'] = host_rename_profile
        ws_module.profile_handlers['delete'] = host_delete_profile

        # Detect Local IP
        local_ip = "127.0.0.1"
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except: pass

        webserver_port = self.config.get("webserver_port", 8000)
        console.print("[green]Starting Web Server...[/green]")
        console.print("[dim]Press Ctrl+C to stop the server and return to menu.[/dim]")

        server_thread = run_server(host="0.0.0.0", port=webserver_port)

        if server_thread:
            # 等待一小段时间检查服务器是否成功启动
            time.sleep(1.5)
            if not server_thread.is_alive():
                # 服务器启动失败（如端口占用）
                console.print(f"\n[bold red]Web Server failed to start. Please check if port {webserver_port} is already in use.[/bold red]")
                time.sleep(3)  # 给用户3秒查看错误
                return

            import webbrowser
            time.sleep(1)
            console.print(Panel(
                f"Local: [bold cyan]http://127.0.0.1:{webserver_port}[/bold cyan]\n"
                f"Network: [bold cyan]http://{local_ip}:{webserver_port}[/bold cyan]",
                title="Web Server Active",
                border_style="green",
                expand=False
            ))
            webbrowser.open(f"http://127.0.0.1:{webserver_port}")

            self.web_server_active = True
            try:
                while server_thread.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Stopping Web Server and cleaning up...[/yellow]")
            finally:
                ws_module.stop_server()
                time.sleep(3) # Wait for uvicorn shutdown logs to finish
                self.web_server_active = False

    def _get_profiles_list(self, profiles_dir):
        if not os.path.exists(profiles_dir): return []
        return [f.replace(".json", "") for f in os.listdir(profiles_dir) if f.endswith(".json")]

    def task_queue_menu(self):
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager, QueueTaskItem
        qm = QueueManager()

        def get_localized_status(status):
            status_map = {
                "waiting": i18n.get("task_status_waiting"),
                "translating": i18n.get("task_status_translating"),
                "translated": i18n.get("task_status_translated"),
                "polishing": i18n.get("task_status_polishing"),
                "completed": i18n.get("task_status_completed"),
                "running": i18n.get("task_status_running"),
                "error": i18n.get("task_status_error"),
                "stopped": i18n.get("task_status_stopped")
            }
            return status_map.get(status.lower(), status.upper())
        
        while True:
            self.display_banner()
            console.print(Panel(f"[bold]{i18n.get('menu_task_queue')}[/bold]"))
            
            if qm.tasks:
                table = Table(show_header=True, box=None)
                table.add_column(i18n.get("table_column_id"), style="dim")
                table.add_column(i18n.get("table_column_task"))
                table.add_column(i18n.get("table_column_details"))
                table.add_column(i18n.get("table_column_status"))
                
                for i, task in enumerate(qm.tasks):
                    status_style = "green" if task.status == "completed" else "yellow" if task.status == "running" else "dim"
                    type_str = "T+P" if task.task_type == TaskType.TRANSLATE_AND_POLISH else "T" if task.task_type == TaskType.TRANSLATION else "P"
                    details = f"{task.profile or 'def'}/{task.rules_profile or 'def'} | {task.source_lang or 'auto'}->{task.target_lang or 'auto'}"
                    table.add_row(
                        str(i+1),
                        f"[{type_str}] {os.path.basename(task.input_path)}",
                        details,
                        f"[{status_style}]{get_localized_status(task.status)}[/]"
                    )
                console.print(table)
            else:
                console.print(f"[dim]{i18n.get('msg_queue_empty')}[/dim]")
                
            console.print(f"\n[cyan]1.[/] {i18n.get('menu_queue_add')}")
            if qm.tasks:
                console.print(f"[cyan]2.[/] {i18n.get('menu_queue_remove')}")
                console.print(f"[cyan]3.[/] {i18n.get('menu_queue_edit_fine')}")
                console.print(f"[cyan]4.[/] {i18n.get('menu_queue_edit_json')}")
                console.print(f"[cyan]5.[/] {i18n.get('menu_queue_clear')}")
                console.print(f"[bold green]6.[/] {i18n.get('menu_queue_start')}")
                if len(qm.tasks) > 1:  # 只有多于1个任务时才显示排序选项
                    console.print(f"[cyan]7.[/] {i18n.get('menu_queue_reorder')}")

            console.print(f"\n[dim]0. {i18n.get('menu_back')}[/dim]")

            queue_choices = ["0", "1"]
            if qm.tasks:
                queue_choices.extend(["2", "3", "4", "5", "6"])
                if len(qm.tasks) > 1:
                    queue_choices.append("7")

            choice = IntPrompt.ask(f"\n{i18n.get('prompt_select')}", choices=queue_choices, show_choices=False)
            
            if choice == 0: break
            elif choice == 1: # Add Task (Basic)
                # ... (reuse logic)
                t_choice = IntPrompt.ask(i18n.get('prompt_select'), choices=["1", "2", "3"], default=1)
                type_map = {1: TaskType.TRANSLATION, 2: TaskType.POLISH, 3: TaskType.TRANSLATE_AND_POLISH}
                task_type = type_map[t_choice]
                start_path = self.config.get("label_input_path", ".")
                input_path = self.file_selector.select_path(start_path=start_path)
                if input_path:
                    qm.add_task(QueueTaskItem(task_type, input_path))
                    console.print("[green]Task added (default config). Use Edit to customize.[/green]")
                time.sleep(1)

            elif choice == 2: # Remove
                idx = IntPrompt.ask("Enter ID to remove", default=1) - 1
                if qm.remove_task(idx):
                    console.print("[green]Task removed.[/green]")
                else:
                    console.print("[red]Invalid ID or task is running.[/red]")
                time.sleep(1)

            elif choice == 3: # Fine-grained Edit
                idx = IntPrompt.ask("Enter ID to edit", default=1) - 1
                if 0 <= idx < len(qm.tasks):
                    t = qm.tasks[idx]
                    console.print(Panel(f"[bold]{i18n.get('menu_queue_edit_fine')}[/bold]: #{idx+1} {os.path.basename(t.input_path)}"))
                    
                    # 1. Task Type
                    t_type_map = {
                        TaskType.TRANSLATION: i18n.get("task_type_translation"),
                        TaskType.POLISH: i18n.get("task_type_polishing"),
                        TaskType.TRANSLATE_AND_POLISH: i18n.get("task_type_all_in_one")
                    }
                    console.print(f"\n[cyan]{i18n.get('ui_recent_type')}:[/] {t_type_map.get(t.task_type, 'Unknown')}")
                    new_task_type_str = Prompt.ask(f"{i18n.get('prompt_task_type_queue')}{i18n.get('tip_follow_profile')}", 
                                                   choices=list(t_type_map.values()) + [""], 
                                                   default=t_type_map.get(t.task_type, ''))
                    if new_task_type_str:
                        t.task_type = {v: k for k, v in t_type_map.items()}[new_task_type_str]

                    # 2. Input/Output Paths
                    t.input_path = Prompt.ask(f"{i18n.get('setting_input_path')}{i18n.get('tip_follow_profile')}", default=t.input_path)
                    t.output_path = Prompt.ask(f"{i18n.get('setting_output_path')}{i18n.get('tip_follow_profile')}", default=t.output_path or "") or None
                    
                    # 3. Project Type & Languages
                    console.print(f"\n[cyan]{i18n.get('label_current_project_type')}:[/] {t.project_type or self.config.get('translation_project', 'AutoType')}")
                    t.project_type = Prompt.ask(f"{i18n.get('prompt_project_type_queue')}{i18n.get('tip_follow_profile')}", default=t.project_type or "") or None

                    console.print(f"\n[cyan]{i18n.get('label_current_lang')}:[/] {t.source_lang or self.config.get('source_language')} -> {t.target_lang or self.config.get('target_language')}")
                    t.source_lang = Prompt.ask(f"{i18n.get('prompt_source_lang_queue')}{i18n.get('tip_follow_profile')}", default=t.source_lang or "") or None
                    t.target_lang = Prompt.ask(f"{i18n.get('prompt_target_lang_queue')}{i18n.get('tip_follow_profile')}", default=t.target_lang or "") or None

                    # 4. Profiles
                    profiles = self._get_profiles_list(self.profiles_dir)
                    rules = ["None"] + self._get_profiles_list(self.rules_profiles_dir)
                    console.print(f"\n[cyan]{i18n.get('label_profiles')}:[/] {', '.join(profiles)}")
                    t.profile = Prompt.ask(f"{i18n.get('prompt_profile_queue')}{i18n.get('tip_follow_profile')}", default=t.profile or "") or None
                    console.print(f"[cyan]{i18n.get('label_rules_profiles')}:[/] {', '.join(rules)}")
                    t.rules_profile = Prompt.ask(f"{i18n.get('prompt_rules_profile_queue')}{i18n.get('tip_follow_profile')}", 
                                                choices=rules + [""], 
                                                default=t.rules_profile or "") or None

                    # 5. API Overrides
                    current_platform = t.platform or self.config.get("target_platform")
                    console.print(f"\n[cyan]{i18n.get('label_platform_override')}:[/] {current_platform or 'Default'}")
                    platforms_list = list(self.config.get("platforms", {}).keys())
                    t.platform = Prompt.ask(f"{i18n.get('label_platform_override')}{i18n.get('tip_follow_profile')}", 
                                            choices=platforms_list + [""], 
                                            default=t.platform or "") or None
                    
                    if t.platform:
                        # Dynamically get models for selected platform (if API key available in current config)
                        current_api_url = t.api_url or self.config.get("base_url")
                        current_api_key = t.api_key or self.config.get("api_key")
                        platform_config_for_fetch = {
                            "api_url": current_api_url,
                            "api_key": current_api_key,
                            "auto_complete": self.config.get("platforms", {}).get(t.platform, {}).get("auto_complete", False)
                        }
                        available_models = []
                        from ModuleFolders.Infrastructure.LLMRequester.AnthropicRequester import AnthropicRequester
                        from ModuleFolders.Infrastructure.LLMRequester.OpenaiRequester import OpenaiRequester
                        from ModuleFolders.Infrastructure.LLMRequester.GoogleRequester import GoogleRequester

                        if self.config.get("platforms", {}).get(t.platform, {}).get("api_format") == "Anthropic":
                            requester = AnthropicRequester()
                            available_models = requester.get_model_list(platform_config_for_fetch)
                        elif self.config.get("platforms", {}).get(t.platform, {}).get("api_format") == "OpenAI":
                            requester = OpenaiRequester()
                            available_models = requester.get_model_list(platform_config_for_fetch)
                        elif self.config.get("platforms", {}).get(t.platform, {}).get("api_format") == "Google":
                            requester = GoogleRequester()
                            available_models = requester.get_model_list(platform_config_for_fetch)

                        if available_models:
                            console.print(f"[cyan]  可用模型 ({t.platform}):[/] {', '.join(available_models)}")
                            t.model = Prompt.ask(f"{i18n.get('label_model_override')}{i18n.get('tip_follow_profile')}", 
                                                choices=available_models + [""], 
                                                default=t.model or "") or None
                        else:
                            t.model = Prompt.ask(f"{i18n.get('label_model_override')}{i18n.get('tip_follow_profile')}", default=t.model or "") or None
                    else:
                        t.model = Prompt.ask(f"{i18n.get('label_model_override')}{i18n.get('tip_follow_profile')}", default=t.model or "") or None

                    t.api_url = Prompt.ask(f"{i18n.get('label_url_override')}{i18n.get('tip_follow_profile')}", default=t.api_url or "") or None
                    t.api_key = Prompt.ask(f"{i18n.get('label_key_override')}{i18n.get('tip_follow_profile')}", password=True, default=t.api_key or "") or None

                    # 6. Performance Overrides
                    t.threads = IntPrompt.ask(f"{i18n.get('label_threads_override')}{i18n.get('tip_follow_profile')}", default=t.threads if t.threads is not None else 0) or None
                    t.retry = IntPrompt.ask(f"{i18n.get('setting_retry_count')}{i18n.get('tip_follow_profile')}", default=t.retry if t.retry is not None else 0) or None
                    t.timeout = IntPrompt.ask(f"{i18n.get('setting_request_timeout')}{i18n.get('tip_follow_profile')}", default=t.timeout if t.timeout is not None else 0) or None
                    t.rounds = IntPrompt.ask(f"{i18n.get('setting_round_limit')}{i18n.get('tip_follow_profile')}", default=t.rounds if t.rounds is not None else 0) or None
                    t.pre_lines = IntPrompt.ask(f"{i18n.get('setting_pre_line_counts')}{i18n.get('tip_follow_profile')}", default=t.pre_lines if t.pre_lines is not None else 0) or None

                    # 7. Segmentation Overrides
                    current_limit_mode = "lines" if t.lines_limit is not None else "tokens" if t.tokens_limit is not None else ( "lines" if not self.config.get("tokens_limit_switch") else "tokens")

                    limit_choice = Prompt.ask(f"{i18n.get('setting_limit_mode')}{i18n.get('tip_follow_profile')}", 
                                            choices=["lines", "tokens", ""], 
                                            default=current_limit_mode)
                    if limit_choice == "lines":
                        t.lines_limit = IntPrompt.ask(f"{i18n.get('prompt_limit_val')} (Lines){i18n.get('tip_follow_profile')}", default=t.lines_limit or self.config.get("lines_limit")) or None
                        t.tokens_limit = None
                    elif limit_choice == "tokens":
                        t.tokens_limit = IntPrompt.ask(f"{i18n.get('prompt_limit_val')} (Tokens){i18n.get('tip_follow_profile')}", default=t.tokens_limit or self.config.get("tokens_limit")) or None
                        t.lines_limit = None
                    else:
                        t.lines_limit = None
                        t.tokens_limit = None

                    # 8. Thinking Overrides
                    current_think_depth = t.think_depth or self.config.get("think_depth", "low")
                    if t.platform and self.config.get("platforms", {}).get(t.platform, {}).get("api_format") == "Anthropic":
                        t.think_depth = Prompt.ask(f"{i18n.get('prompt_think_depth_claude')}{i18n.get('tip_follow_profile')}", 
                                                choices=["low", "medium", "high", ""], 
                                                default=current_think_depth) or None
                    else:
                        t.think_depth = Prompt.ask(f"{i18n.get('prompt_think_depth')}{i18n.get('tip_follow_profile')}", 
                                                default=current_think_depth) or None
                    console.print(f"[dim]{i18n.get('hint_think_budget') or '提示: 0=关闭, -1=无上限'}[/dim]")
                    budget_str = Prompt.ask(f"{i18n.get('menu_api_think_budget')}{i18n.get('tip_follow_profile')}",
                                            default=str(t.thinking_budget) if t.thinking_budget is not None else "0")
                    try:
                        t.thinking_budget = int(budget_str) if budget_str else None
                    except ValueError:
                        t.thinking_budget = None

                    qm.save_tasks()
                    console.print("[green]Task updated.[/green]")
                else:
                    console.print("[red]Invalid ID.[/red]")
                time.sleep(1)

            elif choice == 4: # Edit JSON
                # ... (keep existing)
                if open_in_editor(qm.queue_file):
                    Prompt.ask(f"\n{i18n.get('msg_press_enter_after_save')}")
                    qm.load_tasks()
                    console.print("[green]Queue reloaded from file.[/green]")
                time.sleep(1)
            elif choice == 5: # Clear
                # ... (keep existing)
                if qm.clear_tasks():
                    console.print("[green]Queue cleared.[/green]")
                else:
                    console.print("[red]Cannot clear while queue is running.[/red]")
                time.sleep(1)
            elif choice == 6: # Start
                # ... (keep existing)
                if not qm.tasks: continue
                if qm.is_running:
                    console.print("[yellow]Queue is already running.[/yellow]")
                    time.sleep(1)
                    continue
                console.print(f"\n[bold green]Starting Queue Processing...[/bold green]")
                self._is_queue_mode = True  # 标记进入队列模式
                self.start_queue_log_monitor()  # 启动队列日志监控
                qm.start_queue(self)
                break

            elif choice == 7: # Reorder Queue
                if len(qm.tasks) <= 1:
                    console.print("[yellow]Need at least 2 tasks to reorder.[/yellow]")
                    time.sleep(1)
                    continue

                console.print(Panel(f"[bold]{i18n.get('menu_queue_reorder')}[/bold]"))
                console.print("\n[cyan]Current Order:[/]")

                # 显示当前队列
                for i, task in enumerate(qm.tasks):
                    type_str = "T+P" if task.task_type == TaskType.TRANSLATE_AND_POLISH else "T" if task.task_type == TaskType.TRANSLATION else "P"
                    console.print(f"  {i+1}. [{type_str}] {os.path.basename(task.input_path)}")

                console.print(f"\n[cyan]{i18n.get('options_label')}:[/]")
                console.print(f"[cyan]1.[/] {i18n.get('menu_queue_move_up')}")
                console.print(f"[cyan]2.[/] {i18n.get('menu_queue_move_down')}")
                console.print(f"[cyan]3.[/] {i18n.get('menu_queue_move_to')}")
                console.print(f"[dim]0. {i18n.get('menu_back')}[/dim]")

                reorder_choice = IntPrompt.ask(f"\n{i18n.get('prompt_select')}", choices=["0", "1", "2", "3"], show_choices=False)

                if reorder_choice == 0:
                    continue
                elif reorder_choice == 1:  # Move Up
                    task_id = IntPrompt.ask(i18n.get('prompt_task_id'), default=1)
                    idx = task_id - 1
                    if qm.move_task_up(idx):
                        console.print(f"[green]{i18n.get('msg_task_moved_up').format(task_id)}[/green]")
                    else:
                        console.print(f"[red]{i18n.get('msg_task_move_failed')}[/red]")
                    time.sleep(1)
                elif reorder_choice == 2:  # Move Down
                    task_id = IntPrompt.ask(i18n.get('prompt_task_id'), default=1)
                    idx = task_id - 1
                    if qm.move_task_down(idx):
                        console.print(f"[green]{i18n.get('msg_task_moved_down').format(task_id)}[/green]")
                    else:
                        console.print(f"[red]{i18n.get('msg_task_move_failed')}[/red]")
                    time.sleep(1)
                elif reorder_choice == 3:  # Move to specific position
                    from_id = IntPrompt.ask(i18n.get('prompt_task_id_from'), default=1)
                    to_id = IntPrompt.ask(i18n.get('prompt_task_id_to'), default=1)
                    from_idx, to_idx = from_id - 1, to_id - 1
                    if qm.move_task(from_idx, to_idx):
                        console.print(f"[green]{i18n.get('msg_task_moved_to').format(from_id, to_id)}[/green]")
                    else:
                        console.print(f"[red]{i18n.get('msg_task_move_failed')}[/red]")
                    time.sleep(1)

        # 如果队列正在运行，等待完成并清除标记
        if hasattr(self, '_is_queue_mode') and self._is_queue_mode:
            try:
                console.print(f"[green]Waiting for queue to complete...[/green]")
                while qm.is_running:
                    time.sleep(1)
            except KeyboardInterrupt:
                Base.work_status = Base.STATUS.STOPING
                console.print(f"\n[bold red]Queue stopped by user.[/bold red]")
            finally:
                self.stop_queue_log_monitor()  # 停止队列日志监控
                self._is_queue_mode = False  # 清除队列模式标记

def main():
    parser = argparse.ArgumentParser(description="AiNiee-Next - A powerful tool for AI-driven translation and polishing.", add_help=False)
    
    # 将 --help 参数单独处理，以便自定义帮助信息
    parser.add_argument('-h', '--help', action='help', default=argparse.SUPPRESS, help='Show this help message and exit.')

    # 核心任务参数
    parser.add_argument('task', nargs='?', choices=['translate', 'polish', 'export', 'all_in_one', 'queue'], help=i18n.get('help_task'))
    parser.add_argument('input_path', nargs='?', help=i18n.get('help_input'))
    
    # 路径与环境
    parser.add_argument('-o', '--output', dest='output_path', help=i18n.get('help_output'))
    parser.add_argument('-p', '--profile', dest='profile', help=i18n.get('help_profile'))
    parser.add_argument('--rules-profile', dest='rules_profile', help="Rules profile to use (Glossary, Characterization, etc.)")
    parser.add_argument('--queue-file', dest='queue_file', help="Path to the task queue JSON file")
    parser.add_argument('-s', '--source', dest='source_lang', help=i18n.get('help_source'))
    parser.add_argument('-t', '--target', dest='target_lang', help=i18n.get('help_target'))
    parser.add_argument('--type', dest='project_type', help="Project type (Txt, Epub, MTool, RenPy, etc.)")
    
    # 运行策略
    parser.add_argument('-r', '--resume', action='store_true', help=i18n.get('help_resume'))
    parser.add_argument('-y', '--yes', action='store_true', dest='non_interactive', help=i18n.get('help_yes'))
    parser.add_argument('--threads', type=int, help="Concurrent thread counts (0 for auto)")
    parser.add_argument('--retry', type=int, help="Max retry counts for failed requests")
    parser.add_argument('--rounds', type=int, help="Max execution rounds")
    parser.add_argument('--timeout', type=int, help="Request timeout in seconds")

    # API 与模型配置
    parser.add_argument('--platform', help="Target platform (e.g., Openai, LocalLLM, sakura)")
    parser.add_argument('--model', help="Model name")
    parser.add_argument('--api-url', help="Base URL for the API")
    parser.add_argument('--api-key', help="API Key")
    parser.add_argument('--think-depth', type=int, help="Reasoning depth (0-10000)")
    parser.add_argument('--thinking-budget', type=int, help="Thinking budget limit")
    parser.add_argument('--failover', choices=['on', 'off'], help="Enable or disable API failover")
    
    parser.add_argument('--web-mode', action='store_true', help="Enable Web Server compatible output mode")

    # 文本处理逻辑
    parser.add_argument('--lines', type=int, help="Lines per request (Line Mode)")
    parser.add_argument('--tokens', type=int, help="Tokens per request (Token Mode)")
    parser.add_argument('--pre-lines', type=int, help="Context lines to include")

    args = parser.parse_args()

    cli = CLIMenu()
    try:
        if args.task and args.input_path:
            cli.run_non_interactive(args)
        else:
            cli.main_menu()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        cli.handle_crash(error_msg)
    finally:
        # Final cleanup for WebServer and its subtasks
        try:
            import Tools.WebServer.web_server as ws_module
            ws_module.stop_server()
        except:
            pass
        sys.exit(0)

if __name__ == "__main__":
    main()
