# Tools/WebServer/web_server.py
import os
import sys
import json
import threading
import subprocess
import time
import collections
import locale
from datetime import datetime
from typing import List, Dict, Any, Optional

# --- Pre-emptive Import for FastAPI & Pydantic ---
try:
    from fastapi import FastAPI, HTTPException, Body, File, UploadFile, Response, BackgroundTasks
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
except ImportError:
    # This error will be caught and handled in ainiee_cli.py
    raise ImportError("Required packages are missing. Please run 'uv add fastapi uvicorn[standard] pydantic python-multipart'.,Or run 'uv sync'")

# --- Add Project Root to Python Path ---
# This ensures that we can import modules from the main project (e.g., ainiee_cli)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UPDATETEMP_PATH = os.path.join(PROJECT_ROOT, "updatetemp") # Define upload directory
TEMP_EDIT_PATH = os.path.join(PROJECT_ROOT, "output", "temp_edit") # Define draft directory

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Global State & Task Management ---

class TaskManager:
    """A singleton class to manage the CLI task execution state."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):  # Prevent re-initialization
            self.process: Optional[subprocess.Popen] = None
            self.status: str = "idle"  # idle, running, stopping, completed, error
            self.logs = collections.deque(maxlen=500)
            self.chart_data = collections.deque(maxlen=60) # 1 min history at 1s intervals
            self.stats: Dict[str, Any] = self._get_initial_stats()
            self.initialized = True
            self.current_source = ""      # 当前批次原文
            self.current_translation = "" # 当前批次译文
            self.api_url = "http://127.0.0.1:8000" # 默认地址
            
            # Use a separate thread to monitor the process output
            self.monitor_thread: Optional[threading.Thread] = None

    def _get_initial_stats(self) -> Dict[str, Any]:
        return {
            "rpm": 0, "tpm": 0, "totalProgress": 0, "completedProgress": 0,
            "totalTokens": 0, "elapsedTime": 0, "status": "idle",
            "currentFile": "N/A", "successRate": 0, "errorRate": 0
        }

    def push_log(self, message: str, type: str = "info"):
        """Directly push a log message from the host process."""
        self.logs.append({"timestamp": time.time(), "message": message, "type": type})

    def push_comparison(self, source: str, translation: str):
        """Update the side-by-side comparison data from the host process."""
        self.current_source = source
        self.current_translation = translation

    def push_stats(self, stats: Dict[str, Any]):
        """Directly push stats from the host process."""
        self.stats.update(stats)
        # Also update chart data
        self.chart_data.append({
            "time": time.strftime('%H:%M:%S'),
            "rpm": self.stats.get("rpm", 0),
            "tpm": self.stats.get("tpm", 0)
        })

    def _log_and_parse(self, stream):
        """Read from a stream, log the output, and parse for stats."""
        # The stream provides correctly decoded strings because of the `encoding` setting in Popen
        for line in iter(stream.readline, ''):
            line = line.strip()
            if not line:
                continue

            # Check for our special stats line
            if line.startswith("[STATS]"):
                try:
                    # Example: [STATS] RPM: 0.00 | TPM: 0.00k | Progress: 0/1435 | Tokens: 0
                    parts = line.split('|')
                    rpm_part = parts[0].split(':')[1].strip()
                    tpm_part = parts[1].split(':')[1].strip().replace('k', '')
                    progress_part = parts[2].split(':')[1].strip()
                    tokens_part = parts[3].split(':')[1].strip()

                    completed, total = map(int, progress_part.split('/'))

                    self.stats["rpm"] = float(rpm_part)
                    self.stats["tpm"] = float(tpm_part) # This is already in k
                    self.stats["completedProgress"] = completed
                    self.stats["totalProgress"] = total
                    self.stats["totalTokens"] = int(tokens_part)
                except (IndexError, ValueError) as e:
                    # Log parsing error if the format is unexpected, but don't crash
                    self.logs.append({"timestamp": time.time(), "message": f"[PARSER_ERROR] Could not parse stats line: {line}. Error: {e}"})
            else:
                            # It's a regular log line
                            self.logs.append({"timestamp": time.time(), "message": line})


    def start_task(self, payload: Dict[str, Any]) -> bool:
        """Starts the ainiee_cli.py script as a subprocess with config overrides."""
        with self._lock:
            if self.status == "running":
                return False
            
            self.status = "running"
            self.logs.clear()
            self.chart_data.clear()
            self.current_source = ""
            self.current_translation = ""
            self.stats = self._get_initial_stats()
            self.stats["status"] = "running"
            self.logs.append({"timestamp": time.time(), "message": "Task starting with parameters from web UI..."})

            # Base command using corrected keys and uv runner
            cli_args = [
                "uv",
                "run",
                os.path.join(PROJECT_ROOT, "ainiee_cli.py"),
                payload["task"], # Use 'task' key
                payload["input_path"],
                "-y",  # Crucial for non-interactive mode
                "--web-mode" # Activate parsable output
            ]
            
            # Add optional arguments based on the payload
            if payload.get("output_path"):
                cli_args.extend(["--output", payload["output_path"]])
            if payload.get("source_lang"):
                cli_args.extend(["--source", payload["source_lang"]])
            if payload.get("target_lang"):
                cli_args.extend(["--target", payload["target_lang"]])
            if payload.get("resume"):
                cli_args.append("--resume")
            
            # Additional Overrides from Payload
            if payload.get("threads") is not None:
                cli_args.extend(["--threads", str(payload["threads"])])
            if payload.get("retry") is not None:
                cli_args.extend(["--retry", str(payload["retry"])])
            if payload.get("timeout") is not None:
                cli_args.extend(["--timeout", str(payload["timeout"])])
            if payload.get("rounds") is not None:
                cli_args.extend(["--rounds", str(payload["rounds"])])
            if payload.get("pre_lines") is not None:
                cli_args.extend(["--pre-lines", str(payload["pre_lines"])])
            
            if payload.get("model"):
                cli_args.extend(["--model", payload["model"]])
            if payload.get("api_url"):
                cli_args.extend(["--api-url", payload["api_url"]])
            if payload.get("api_key"):
                cli_args.extend(["--api-key", payload["api_key"]])
            
            if payload.get("failover") is True:
                cli_args.extend(["--failover", "on"])
            elif payload.get("failover") is False:
                cli_args.extend(["--failover", "off"])

            if payload.get("lines") is not None:
                cli_args.extend(["--lines", str(payload["lines"])])
            if payload.get("tokens") is not None:
                cli_args.extend(["--tokens", str(payload["tokens"])])
            
            if payload.get("profile"):
                cli_args.extend(["--profile", payload["profile"]])
            if payload.get("rules_profile"):
                cli_args.extend(["--rules-profile", payload["rules_profile"]])
            
            # Note: other keys like 'threads' are in the payload but not used here
            # because ainiee_cli.py doesn't have CLI args for them. They are
            # expected to be part of the loaded profile config.

            try:
                # Get the system's preferred console encoding (e.g., 'gbk' on Chinese Windows)
                system_encoding = locale.getpreferredencoding(False)

                # 注入环境变量以便子进程知道 WebServer 的内部接口位置
                import os as system_os
                env = system_os.environ.copy()
                # 获取当前 WebServer 的运行地址
                env["AINIEE_INTERNAL_API_URL"] = task_manager.api_url
                # 强制子进程使用 UTF-8 编码输出，防止在 Windows 下产生编码冲突
                env["PYTHONIOENCODING"] = "utf-8"
                # 标记该进程为后端 Worker，与核心主进程（WebServer）区分
                env["AINIEE_BACKEND_WORKER"] = "1"

                self.process = subprocess.Popen(
                    cli_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace', # 增加解码容错，防止非法字符导致线程崩溃
                    bufsize=1,
                    cwd=PROJECT_ROOT,
                    env=env # 传递环境变量
                )
                
                self.monitor_thread = threading.Thread(target=self._process_monitor)
                self.monitor_thread.daemon = True
                self.monitor_thread.start()

                return True
            except Exception as e:
                self.status = "error"
                self.logs.append({"timestamp": time.time(), "message": f"Failed to start process: {e}"})
                return False

    def _process_monitor(self):
        """Monitors the subprocess, which now provides correctly decoded strings."""
        if self.process and self.process.stdout:
            import re
            # Popen now handles the decoding, so we can iterate over strings directly.
            for line in iter(self.process.stdout.readline, ''):
                line = line.strip()
                if line:
                    self.logs.append({"timestamp": time.time(), "message": line})
                    
                    # 1. Parsing current file
                    if "File:" in line:
                        try: self.stats["currentFile"] = line.split("File:")[1].strip().split("|")[0].strip()
                        except: pass
                    
                    # 2. Parsing [STATS] line (Robust Regex)
                    if "[STATS]" in line:
                        try:
                            # RPM
                            rpm_match = re.search(r"RPM:\s*([\d\.]+)", line)
                            if rpm_match: self.stats["rpm"] = float(rpm_match.group(1))
                            
                            # TPM
                            tpm_match = re.search(r"TPM:\s*([\d\.]+k?)", line)
                            if tpm_match: 
                                tpm_val = tpm_match.group(1).replace('k', '')
                                self.stats["tpm"] = float(tpm_val)
                            
                            # Progress (Completed/Total)
                            prog_match = re.search(r"Progress:\s*(\d+)/(\d+)", line)
                            if prog_match:
                                self.stats["completedProgress"] = int(prog_match.group(1))
                                self.stats["totalProgress"] = int(prog_match.group(2))
                            
                            # Tokens
                            tokens_match = re.search(r"Tokens:\s*(\d+)", line)
                            if tokens_match: self.stats["totalTokens"] = int(tokens_match.group(1))

                            # Success/Error Rate
                            s_rate_match = re.search(r"S-Rate:\s*([\d\.]+)%", line)
                            if s_rate_match: self.stats["successRate"] = float(s_rate_match.group(1))
                            
                            e_rate_match = re.search(r"E-Rate:\s*([\d\.]+)%", line)
                            if e_rate_match: self.stats["errorRate"] = float(e_rate_match.group(1))
                            
                            # Append to Chart Data
                            self.chart_data.append({
                                "time": time.strftime('%H:%M:%S'),
                                "rpm": self.stats["rpm"],
                                "tpm": self.stats["tpm"]
                            })
                            
                        except Exception as e:
                            # Non-fatal parsing error
                            pass
        
        if self.process:
            self.process.wait()
        
        with self._lock:
            if self.status == "running":
                if self.process and self.process.returncode == 0:
                    self.status = "completed"
                    self.stats["status"] = "completed"
                else:
                    self.status = "error"
                    self.stats["status"] = "error"
            self.process = None

    def stop_task(self):
        """Stops the running task."""
        with self._lock:
            if self.status != "running" or not self.process:
                return
            
            self.status = "stopping"
            self.stats["status"] = "stopping"
            self.logs.append({"timestamp": time.time(), "message": "Sending force stop signal..."})
            
            try:
                # Direct force kill as requested (Data safety guaranteed by cache)
                self.process.kill()
                self.process.wait(timeout=2)
            except Exception as e:
                self.logs.append({"timestamp": time.time(), "message": f"Force stop error: {e}"})
            
            self.status = "idle"
            self.stats["status"] = "idle"
            self.logs.append({"timestamp": time.time(), "message": "Task stopped."})


task_manager = TaskManager()

# --- Global System Mode ---
# monitor: Only monitoring is allowed
# full: Full control (default)
SYSTEM_MODE = "full"

# --- Simple In-Memory Caches for API Endpoints ---
_version_cache: Dict[str, Any] = {}
_config_cache: Dict[str, Any] = {}
_profiles_cache: Optional[List[str]] = None

# --- Profile Handlers (Dependency Injection) ---
# Allows the host application (ainiee_cli.py) to override logic
profile_handlers: Dict[str, Any] = {
    "create": None,
    "rename": None,
    "delete": None
}

# --- Pydantic Models for API Requests ---

class AppConfig(BaseModel):
    # This needs to match the structure of the config JSON files
    # Define a few key fields for demonstration
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    actual_thread_counts: Optional[int] = None
    temp_file_limit: Optional[int] = 10
    cache_editor_page_size: Optional[int] = 15
    # Add other fields from your config...
    class Config:
        extra = 'allow' # Allow extra fields not defined here

class ProfileSwitchRequest(BaseModel):
    profile: str

class RulesProfileSwitchRequest(BaseModel):
    profile: str

class ProfileCreateRequest(BaseModel):
    name: str
    base: Optional[str] = None

class ProfileRenameRequest(BaseModel):
    old_name: str
    new_name: str

class ProfileDeleteRequest(BaseModel):
    profile: str

class GlossaryItem(BaseModel):
    src: str
    dst: str
    info: Optional[str] = None

class ExclusionItem(BaseModel):
    markers: str
    info: Optional[str] = None
    regex: Optional[str] = None

class CharacterizationItem(BaseModel):
    original_name: str
    translated_name: str
    gender: Optional[str] = ""
    age: Optional[str] = ""
    personality: Optional[str] = ""
    speech_style: Optional[str] = ""
    additional_info: Optional[str] = ""

class TranslationExampleItem(BaseModel):
    src: str
    dst: str

class StringContent(BaseModel):
    content: str

class PluginEnableRequest(BaseModel):
    name: str
    enabled: bool

class DeleteFileRequest(BaseModel):
    files: List[str]

class QueueTaskItem(BaseModel):
    task_type: int
    input_path: str
    output_path: Optional[str] = None
    profile: Optional[str] = None
    rules_profile: Optional[str] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    project_type: Optional[str] = None
    platform: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    threads: Optional[int] = None
    retry: Optional[int] = None
    timeout: Optional[int] = None
    rounds: Optional[int] = None
    pre_lines: Optional[int] = None
    lines_limit: Optional[int] = None
    tokens_limit: Optional[int] = None
    think_depth: Optional[str] = None
    thinking_budget: Optional[int] = None
    status: Optional[str] = "waiting"

class QueueMoveRequest(BaseModel):
    to_index: int

class QueueReorderRequest(BaseModel):
    new_order: List[int]

class QueueRawRequest(BaseModel):
    content: str

class TaskPayload(BaseModel):
    """Pydantic model that EXACTLY matches the frontend's TaskPayload interface in types.ts"""
    task: str
    input_path: str
    output_path: Optional[str] = None
    project_type: Optional[str] = None
    resume: Optional[bool] = False
    profile: Optional[str] = None # Added profile field
    
    # Overrides
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    threads: Optional[int] = None
    retry: Optional[int] = None
    timeout: Optional[int] = None
    rounds: Optional[int] = None
    pre_lines: Optional[int] = None
    
    # Platform Overrides
    platform: Optional[str] = None
    model: Optional[str] = None
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    failover: Optional[bool] = None
    
    # Limits
    lines: Optional[int] = None
    tokens: Optional[int] = None

# --- FastAPI Application ---

app = FastAPI(title="AiNiee CLI Backend API")

# --- Paths to Resources ---
RESOURCE_PATH = os.path.join(PROJECT_ROOT, "Resource")
VERSION_FILE = os.path.join(RESOURCE_PATH, "Version", "version.json")
PROFILES_PATH = os.path.join(RESOURCE_PATH, "profiles")
RULES_PROFILES_PATH = os.path.join(RESOURCE_PATH, "rules_profiles")
ROOT_CONFIG_FILE = os.path.join(RESOURCE_PATH, "config.json")
WEB_SERVER_PATH = os.path.join(PROJECT_ROOT, "Tools", "WebServer")

# --- Helper Functions ---

def get_config_mode():
    """Checks if the config is in 'profile' mode or 'legacy' single-file mode."""
    if not os.path.exists(ROOT_CONFIG_FILE):
        return "legacy", {}
    try:
        with open(ROOT_CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)
        if "active_profile" in config:
            return "profile", config
        else:
            return "legacy", config
    except (IOError, json.JSONDecodeError):
        return "legacy", {}

def get_active_profile_path() -> str:
    """Gets the full path to the active profile JSON file."""
    mode, config = get_config_mode()
    if mode == "legacy":
        return ROOT_CONFIG_FILE
    
    profile_name = config.get("active_profile", "default")
    return os.path.join(PROFILES_PATH, f"{profile_name}.json")

def get_active_rules_profile_path() -> str:
    """Gets the full path to the active rules profile JSON file."""
    mode, root_config = get_config_mode()
    rules_profile = root_config.get("active_rules_profile", "default")
    os.makedirs(RULES_PROFILES_PATH, exist_ok=True)
    return os.path.join(RULES_PROFILES_PATH, f"{rules_profile}.json")

def save_rule_generic(key: str, value: Any):
    """Helper to save a specific rule key to the active RULES profile."""
    global _config_cache
    target_path = get_active_rules_profile_path()
    try:
        current_rules = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8-sig') as f:
                    current_rules = json.load(f)
            except: pass
        current_rules[key] = value
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(current_rules, f, indent=4, ensure_ascii=False)
        _config_cache.clear()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save rule {key}: {e}")

def save_config_generic(key: str, value: Any):
    """Helper to save a specific key to the active SETTINGS profile."""
    global _config_cache
    target_path = get_active_profile_path()
    try:
        current_config = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8-sig') as f:
                    current_config = json.load(f)
            except: pass
        current_config[key] = value
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=4, ensure_ascii=False)
        _config_cache.clear()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save setting {key}: {e}")

# --- API Endpoints ---

@app.get("/api/system/mode")
async def get_system_mode():
    return {"mode": SYSTEM_MODE}

@app.get("/api/version")
async def get_version():
    global _version_cache
    if "version" in _version_cache:
        return _version_cache["version"]

    if not os.path.exists(VERSION_FILE):
        # Fallback to a default if file is missing
        return {"version": "V0.0.0 (Version file not found)"}
        
    try:
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            version_data = json.load(f)
            _version_cache["version"] = version_data
            return version_data
    except:
        return {"version": "V0.0.0 (Read Error)"}

@app.post("/api/config")
async def save_config(config: AppConfig):
    """
    Saves the provided JSON to the active configuration file (settings only).
    """
    global _config_cache
    target_path = get_active_profile_path()
    
    # Identify keys that belong to rules (to exclude them from settings save)
    rule_keys = [
        "prompt_dictionary_data", "exclusion_list_data", "characterization_data",
        "world_building_content", "writing_style_content", "translation_example_data"
    ]
    
    try:
        config_dict = config.model_dump(exclude_unset=True) if hasattr(config, 'model_dump') else config.dict(exclude_unset=True)
        
        # Filter out rule data to prevent corruption/desync
        settings_only = {k: v for k, v in config_dict.items() if k not in rule_keys}

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(settings_only, f, indent=4, ensure_ascii=False)
        
        _config_cache.clear()
        return {"message": "Settings saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write to config file: {e}")

@app.get("/api/config")
async def get_config():
    """
    Returns the content of the active configuration merged with active rules.
    """
    global _config_cache
    
    mode, root_config = get_config_mode()
    current_profile_name = root_config.get("active_profile", "default")
    current_rules_name = root_config.get("active_rules_profile", "default")

    cache_key = f"{current_profile_name}_{current_rules_name}"
    if cache_key in _config_cache:
        return _config_cache[cache_key]

    # 1. Load Base Config
    profile_path = get_active_profile_path()
    loaded_config = {}
    if os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8-sig') as f:
                loaded_config = json.load(f)
        except: pass

    # 2. Load Rules Config
    rules_config = {}
    if current_rules_name and current_rules_name != "None":
        rules_path = get_active_rules_profile_path()
        if os.path.exists(rules_path):
            try:
                with open(rules_path, 'r', encoding='utf-8-sig') as f:
                    rules_config = json.load(f)
            except: pass

    # 3. Merge (Rules override Profile if keys overlap)
    rule_keys = [
        "prompt_dictionary_data", "exclusion_list_data", "characterization_data",
        "world_building_content", "writing_style_content", "translation_example_data"
    ]
    
    for k in rule_keys:
        if k in rules_config:
            loaded_config[k] = rules_config[k]

    # Meta
    loaded_config["active_profile"] = current_profile_name
    loaded_config["active_rules_profile"] = current_rules_name

    # 防护：确保 response_check_switch 是正确的 dict 类型
    default_check_switch = {
        "newline_character_count_check": False, "return_to_original_text_check": False,
        "residual_original_text_check": False, "reply_format_check": False
    }
    if "response_check_switch" not in loaded_config or not isinstance(loaded_config.get("response_check_switch"), dict):
        loaded_config["response_check_switch"] = default_check_switch

    _config_cache[cache_key] = loaded_config
    return loaded_config

def save_config_generic(key: str, value: Any):
    """Helper to save a specific key to the active profile."""
    global _config_cache
    target_path = get_active_profile_path()
    try:
        # Load existing config to preserve other fields
        current_config = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8-sig') as f:
                    current_config = json.load(f)
            except:
                pass # If file is corrupt, we might overwrite, or maybe backup first? For now, we proceed.
        
        current_config[key] = value
        
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=4, ensure_ascii=False)
            
        _config_cache.clear()
        return True
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save {key}: {e}")

@app.get("/api/glossary", response_model=List[GlossaryItem])
async def get_glossary():
    config = await get_config()
    return config.get("prompt_dictionary_data", [])

@app.post("/api/glossary")
async def save_glossary(items: List[GlossaryItem]):
    save_rule_generic("prompt_dictionary_data", [item.dict() for item in items])
    return {"message": "Glossary saved successfully."}

@app.get("/api/exclusion", response_model=List[ExclusionItem])
async def get_exclusion():
    config = await get_config()
    return config.get("exclusion_list_data", [])

@app.post("/api/exclusion")
async def save_exclusion(items: List[ExclusionItem]):
    save_rule_generic("exclusion_list_data", [item.dict() for item in items])
    return {"message": "Exclusion list saved successfully."}

# --- New Features Endpoints ---

@app.get("/api/characterization", response_model=List[CharacterizationItem])
async def get_characterization():
    config = await get_config()
    return config.get("characterization_data", [])

@app.post("/api/characterization")
async def save_characterization(items: List[CharacterizationItem]):
    save_rule_generic("characterization_data", [item.dict() for item in items])
    return {"message": "Characterization saved."}

@app.get("/api/world_building", response_model=StringContent)
async def get_world_building():
    config = await get_config()
    return {"content": config.get("world_building_content", "")}

@app.post("/api/world_building")
async def save_world_building(data: StringContent):
    save_rule_generic("world_building_content", data.content)
    return {"message": "World building saved."}

@app.get("/api/writing_style", response_model=StringContent)
async def get_writing_style():
    config = await get_config()
    return {"content": config.get("writing_style_content", "")}

@app.post("/api/writing_style")
async def save_writing_style(data: StringContent):
    save_rule_generic("writing_style_content", data.content)
    return {"message": "Writing style saved."}

@app.get("/api/translation_example", response_model=List[TranslationExampleItem])
async def get_translation_example():
    config = await get_config()
    return config.get("translation_example_data", [])

@app.post("/api/translation_example")
async def save_translation_example(items: List[TranslationExampleItem]):
    save_rule_generic("translation_example_data", [item.dict() for item in items])
    return {"message": "Translation examples saved."}

# --- AI Glossary Analysis Endpoints ---

class GlossaryAnalysisRequest(BaseModel):
    input_path: str
    analysis_percent: int = 100
    analysis_lines: Optional[int] = None
    use_temp_config: bool = False
    temp_platform: Optional[str] = None
    temp_api_key: Optional[str] = None
    temp_api_url: Optional[str] = None
    temp_model: Optional[str] = None
    temp_threads: Optional[int] = None

class GlossaryAnalysisStatus(BaseModel):
    status: str  # 'idle', 'running', 'completed', 'error'
    progress: int = 0
    total: int = 0
    message: str = ""
    results: List[dict] = []

# Global state for analysis task
_analysis_state = {
    "status": "idle",
    "progress": 0,
    "total": 0,
    "message": "",
    "results": [],
    "logs": []
}

@app.get("/api/glossary/analysis/status")
async def get_analysis_status():
    return _analysis_state

@app.post("/api/glossary/analysis/start")
async def start_glossary_analysis(request: GlossaryAnalysisRequest):
    global _analysis_state

    if _analysis_state["status"] == "running":
        raise HTTPException(status_code=400, detail="Analysis already running")

    # Reset state
    _analysis_state = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "message": "初始化中...",
        "results": [],
        "logs": [f"[{datetime.now().strftime('%H:%M:%S')}] 开始分析: {request.input_path}"]
    }

    # Start analysis in background thread
    import threading
    thread = threading.Thread(
        target=_run_glossary_analysis,
        args=(request.input_path, request.analysis_percent, request.analysis_lines,
              request.use_temp_config, request.temp_platform, request.temp_api_key,
              request.temp_api_url, request.temp_model, request.temp_threads)
    )
    thread.daemon = True
    thread.start()

    return {"message": "Analysis started"}

def _add_analysis_log(message: str):
    """添加分析日志"""
    global _analysis_state
    timestamp = datetime.now().strftime('%H:%M:%S')
    _analysis_state["logs"].append(f"[{timestamp}] {message}")

def _run_glossary_analysis(input_path: str, analysis_percent: int, analysis_lines: Optional[int],
                           use_temp: bool = False, temp_platform: str = None, temp_key: str = None,
                           temp_url: str = None, temp_model: str = None, temp_threads: int = None):
    global _analysis_state

    try:
        from ModuleFolders.Domain.FileReader.FileReader import FileReader
        from ModuleFolders.Infrastructure.LLMRequester.LLMRequester import LLMRequester
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
        from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
        import concurrent.futures
        import threading
        import re

        # Load config
        config = {}
        config_file = get_active_profile_path()
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

        # Read file
        _analysis_state["message"] = "正在读取文件..."
        _add_analysis_log("正在读取文件...")
        file_reader = FileReader()
        project_type = config.get("translation_project", "auto")
        cache_data = file_reader.read_files(project_type, input_path, "")

        if not cache_data:
            _analysis_state["status"] = "error"
            _analysis_state["message"] = "无法读取文件内容"
            _add_analysis_log("错误: 无法读取文件内容")
            return

        all_items = list(cache_data.items_iter())
        total_lines = len(all_items)

        if total_lines == 0:
            _analysis_state["status"] = "error"
            _analysis_state["message"] = "未找到可分析的文本"
            _add_analysis_log("错误: 未找到可分析的文本")
            return

        # Calculate lines to analyze
        if analysis_lines:
            lines_to_analyze = min(analysis_lines, total_lines)
        else:
            lines_to_analyze = int(total_lines * analysis_percent / 100)
        lines_to_analyze = max(1, lines_to_analyze)

        _add_analysis_log(f"总行数: {total_lines}, 将分析: {lines_to_analyze} 行")

        items_to_analyze = all_items[:lines_to_analyze]
        batch_size = config.get("lines_limit", 20)
        batches = [items_to_analyze[i:i+batch_size] for i in range(0, len(items_to_analyze), batch_size)]

        _analysis_state["total"] = len(batches)
        _analysis_state["message"] = f"准备分析 {lines_to_analyze} 行文本，共 {len(batches)} 批次"
        _add_analysis_log(f"共 {len(batches)} 批次，每批 {batch_size} 行")

        # Load prompt
        prompt_file = os.path.join(PROJECT_ROOT, "Resource", "Prompt", "System", "glossary_extract_zh.txt")
        if not os.path.exists(prompt_file):
            prompt_file = os.path.join(PROJECT_ROOT, "Resource", "Prompt", "System", "glossary_extract_en.txt")

        with open(prompt_file, 'r', encoding='utf-8') as f:
            system_prompt = f.read()

        # Configure request
        task_config = TaskConfig()
        task_config.load_config_from_dict(config)
        task_config.prepare_for_translation(TaskType.TRANSLATION)

        # Use temp config or current config
        if use_temp and temp_platform:
            platform_config = {
                "target_platform": temp_platform,
                "api_key": temp_key or "",
                "api_url": temp_url or "",
                "model": temp_model or ""
            }
            _analysis_state["message"] = f"使用临时配置: {temp_platform}"
            _add_analysis_log(f"使用临时配置: {temp_platform}, 模型: {temp_model or 'default'}")
        else:
            platform_config = task_config.get_platform_configuration("translationReq")
            _add_analysis_log(f"使用当前配置: {platform_config.get('target_platform', 'unknown')}")

        # Collect results
        all_terms = []
        terms_lock = threading.Lock()
        # 只有在使用临时配置时才使用 temp_threads，否则使用当前配置的线程数
        if use_temp and temp_threads and temp_threads > 0:
            thread_count = temp_threads
        else:
            thread_count = task_config.actual_thread_counts
        _add_analysis_log(f"并发线程数: {thread_count}")

        def analyze_batch(batch_info):
            batch_idx, batch = batch_info
            text_content = "\n".join([item.source_text for item in batch])
            messages = [{"role": "user", "content": text_content}]

            try:
                requester = LLMRequester()
                skip, _, response, _, _ = requester.sent_request(messages, system_prompt, platform_config)

                if not skip and response:
                    terms = _parse_glossary_response(response)
                    with terms_lock:
                        all_terms.extend(terms)
                        _analysis_state["progress"] += 1
                        _analysis_state["message"] = f"已完成 {_analysis_state['progress']}/{_analysis_state['total']} 批次"
            except Exception as e:
                with terms_lock:
                    _analysis_state["progress"] += 1

        # Run analysis
        _analysis_state["message"] = "开始并发分析..."
        _add_analysis_log("开始并发分析...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            batch_infos = list(enumerate(batches))
            list(executor.map(analyze_batch, batch_infos))

        # Calculate frequency
        term_freq = _calculate_term_frequency(all_terms)

        # Convert to list format
        results = []
        for term, data in term_freq.items():
            results.append({
                "src": term,
                "type": data["type"],
                "count": data["count"]
            })

        _analysis_state["status"] = "completed"
        _analysis_state["message"] = f"分析完成，发现 {len(results)} 个专有名词"
        _analysis_state["results"] = results
        _add_analysis_log(f"分析完成! 发现 {len(results)} 个专有名词")

    except Exception as e:
        _analysis_state["status"] = "error"
        _analysis_state["message"] = f"分析出错: {str(e)}"
        _add_analysis_log(f"错误: {str(e)}")

def _parse_glossary_response(response: str) -> list:
    import re
    terms = []
    try:
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            json_str = json_match.group()
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and 'src' in item:
                        terms.append({
                            'src': item.get('src', ''),
                            'type': item.get('type', '专有名词')
                        })
    except:
        pass
    return terms

def _calculate_term_frequency(terms: list) -> dict:
    freq = {}
    for term in terms:
        src = term.get('src', '').strip()
        if not src:
            continue
        if src in freq:
            freq[src]['count'] += 1
        else:
            freq[src] = {'count': 1, 'type': term.get('type', '专有名词')}
    return dict(sorted(freq.items(), key=lambda x: x[1]['count'], reverse=True))

@app.post("/api/glossary/analysis/stop")
async def stop_glossary_analysis():
    global _analysis_state
    from ModuleFolders.Base.Base import Base
    Base.work_status = Base.STATUS.STOPING
    _analysis_state["status"] = "idle"
    _analysis_state["message"] = "已停止"
    return {"message": "Analysis stopped"}

class SaveAnalysisRequest(BaseModel):
    min_frequency: int = 1
    filename: str = "auto_glossary"

@app.post("/api/glossary/analysis/save")
async def save_analysis_results(request: SaveAnalysisRequest):
    """保存分析结果为新的rules_profile并自动切换"""
    global _analysis_state, _config_cache

    if _analysis_state["status"] != "completed":
        raise HTTPException(status_code=400, detail="No completed analysis to save")

    # Filter by frequency
    filtered = [r for r in _analysis_state["results"] if r["count"] >= request.min_frequency]

    if not filtered:
        raise HTTPException(status_code=400, detail="No terms after filtering")

    # Convert to glossary format
    glossary_data = [{"src": r["src"], "dst": "", "info": r["type"]} for r in filtered]

    # 新建一个 rules profile 文件
    new_profile_name = request.filename
    new_profile_path = os.path.join(RULES_PROFILES_PATH, f"{new_profile_name}.json")

    # 确保目录存在
    os.makedirs(RULES_PROFILES_PATH, exist_ok=True)

    # 创建新的 rules profile，只包含术语表数据
    new_rules_config = {
        "prompt_dictionary_data": glossary_data
    }

    with open(new_profile_path, 'w', encoding='utf-8') as f:
        json.dump(new_rules_config, f, indent=4, ensure_ascii=False)

    # 自动切换到新创建的 rules profile
    root_config = {}
    if os.path.exists(ROOT_CONFIG_FILE):
        with open(ROOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            root_config = json.load(f)

    root_config["active_rules_profile"] = new_profile_name
    with open(ROOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(root_config, f, indent=4, ensure_ascii=False)

    # 清除缓存以便前端获取最新数据
    _config_cache.clear()

    return {
        "message": f"已保存 {len(glossary_data)} 条术语到新配置 '{new_profile_name}'，并已自动切换",
        "file": new_profile_path,
        "profile": new_profile_name,
        "count": len(glossary_data)
    }

# --- Plugin Management Endpoints ---

@app.get("/api/plugins")
async def get_plugins():
    """
    Returns a list of all loaded plugins and their enable status.
    """
    try:
        # We need an instance of PluginManager to get the loaded plugins
        from ModuleFolders.Base.PluginManager import PluginManager
        pm = PluginManager()
        pm.load_plugins_from_directory(os.path.join(PROJECT_ROOT, "PluginScripts"))
        
        plugins = pm.get_plugins()
        
        # Load enable status from root config
        root_config = {}
        if os.path.exists(ROOT_CONFIG_FILE):
            with open(ROOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                root_config = json.load(f)
        
        plugin_enables = root_config.get("plugin_enables", {})
        
        result = []
        for name, plugin in plugins.items():
            result.append({
                "name": name,
                "description": plugin.description,
                "enabled": plugin_enables.get(name, plugin.default_enable),
                "default_enable": plugin.default_enable
            })
            
        return sorted(result, key=lambda x: x["name"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get plugins: {e}")

@app.post("/api/plugins/toggle")
async def toggle_plugin(request: PluginEnableRequest):
    """
    Toggles a plugin's enable status and saves it to root config.
    """
    try:
        root_config = {}
        if os.path.exists(ROOT_CONFIG_FILE):
            with open(ROOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                root_config = json.load(f)
        
        plugin_enables = root_config.get("plugin_enables", {})
        plugin_enables[request.name] = request.enabled
        root_config["plugin_enables"] = plugin_enables
        
        with open(ROOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(root_config, f, indent=4, ensure_ascii=False)
            
        return {"message": f"Plugin '{request.name}' {'enabled' if request.enabled else 'disabled'}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle plugin: {e}")

@app.get("/api/profiles", response_model=List[str])
async def get_profiles():
    """
    Returns a list of available profile filenames, utilizing cache.
    """
    global _profiles_cache

    if _profiles_cache is not None:
        return _profiles_cache

    if not os.path.isdir(PROFILES_PATH):
        _profiles_cache = ["default"]
        return _profiles_cache
    
    profiles = [f.replace(".json", "") for f in os.listdir(PROFILES_PATH) if f.endswith(".json")]
    _profiles_cache = profiles
    return profiles

@app.get("/api/rules_profiles", response_model=List[str])
async def get_rules_profiles():
    if not os.path.isdir(RULES_PROFILES_PATH):
        os.makedirs(RULES_PROFILES_PATH, exist_ok=True)
        return ["None", "default"]
    profiles = [f.replace(".json", "") for f in os.listdir(RULES_PROFILES_PATH) if f.endswith(".json")]
    return ["None"] + (profiles or ["default"])

# --- Prompt Management Endpoints ---

@app.get("/api/prompts")
async def list_prompt_categories():
    base_dir = os.path.join(PROJECT_ROOT, "Resource", "Prompt")
    if not os.path.exists(base_dir): return []
    return sorted([d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))])

@app.get("/api/prompts/{category}")
async def list_prompts(category: str):
    # category: "Translate", "Polishing", "Local", "Sakura", "System"
    prompt_dir = os.path.join(PROJECT_ROOT, "Resource", "Prompt", category)
    if not os.path.exists(prompt_dir):
        return []
    # Support both .txt and .json (for error_analysis.json)
    files = [f for f in os.listdir(prompt_dir) if f.endswith((".txt", ".json"))]
    return sorted(files)

@app.get("/api/prompts/{category}/{filename}")
async def get_prompt_content(category: str, filename: str):
    # Try literal match first, then fallback to .txt
    file_path = os.path.join(PROJECT_ROOT, "Resource", "Prompt", category, filename)
    if not os.path.exists(file_path):
        if not filename.endswith(".txt"):
            file_path += ".txt"
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Prompt file not found")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read prompt: {e}")

@app.post("/api/prompts/{category}/{filename}")
async def save_prompt_content(category: str, filename: str, data: Dict[str, str] = Body(...)):
    file_path = os.path.join(PROJECT_ROOT, "Resource", "Prompt", category, filename)
    # Check if we should append .txt (only if it doesn't exist and doesn't have an extension)
    if not os.path.exists(file_path) and "." not in filename:
        file_path += ".txt"
        
    content = data.get("content", "")
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"message": "Prompt saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save prompt: {e}")

@app.post("/api/rules_profiles/switch")
async def switch_rules_profile(request: RulesProfileSwitchRequest):
    global _config_cache
    profile_name = request.profile
    
    if profile_name != "None":
        profile_path = os.path.join(RULES_PROFILES_PATH, f"{profile_name}.json")
        if not os.path.exists(profile_path):
            raise HTTPException(status_code=404, detail="Rules profile not found")
    
    try:
        root_config = {}
        if os.path.exists(ROOT_CONFIG_FILE):
            with open(ROOT_CONFIG_FILE, 'r', encoding='utf-8') as f: root_config = json.load(f)
        root_config["active_rules_profile"] = profile_name
        with open(ROOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(root_config, f, indent=4, ensure_ascii=False)
        
        _config_cache.clear()
        return await get_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/profiles/switch")
async def switch_profile(request: ProfileSwitchRequest):
    """
    Switches the active profile, returns the new active config, and invalidates caches.
    """
    global _config_cache, _profiles_cache # Need to clear these caches
    
    profile_name = request.profile
    profile_path = os.path.join(PROFILES_PATH, f"{profile_name}.json")
    
    if not os.path.exists(profile_path):
        raise HTTPException(status_code=404, detail=f"Profile '{profile_name}' not found.")
    
    try:
        # Update the root config to point to the new profile
        root_config = {}
        if os.path.exists(ROOT_CONFIG_FILE):
            with open(ROOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                root_config = json.load(f)
        root_config["active_profile"] = profile_name
        with open(ROOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(root_config, f, indent=4, ensure_ascii=False)
        
        # Invalidate all config caches and profiles cache
        _config_cache.clear()
        _profiles_cache = None

        # Return the content of the new active profile (will be cached by get_config on next call)
        with open(profile_path, 'r', encoding='utf-8-sig') as f:
            new_active_config = json.load(f)
            new_active_config["active_profile"] = profile_name

            # 防护：确保 response_check_switch 是正确的 dict 类型
            default_check_switch = {
                "newline_character_count_check": False,
                "return_to_original_text_check": False,
                "residual_original_text_check": False,
                "reply_format_check": False
            }
            if "response_check_switch" not in new_active_config or not isinstance(new_active_config.get("response_check_switch"), dict):
                new_active_config["response_check_switch"] = default_check_switch
            return new_active_config
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to switch profile: {e}")

@app.post("/api/profiles/create")
async def create_profile(request: ProfileCreateRequest):
    global _profiles_cache
    
    new_name = request.name
    if not new_name or not new_name.strip():
        raise HTTPException(status_code=400, detail="Profile name cannot be empty")

    # Use injected handler if available
    if profile_handlers["create"]:
        try:
            profile_handlers["create"](new_name, request.base)
            _profiles_cache = None
            return {"message": f"Profile '{new_name}' created successfully (via host)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    new_path = os.path.join(PROFILES_PATH, f"{new_name}.json")
    if os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="Profile already exists")

    # Determine base profile to copy from
    base_name = request.base
    if not base_name:
        # Use active profile as base
        mode, config = get_config_mode()
        base_name = config.get("active_profile", "default")
    
    base_path = os.path.join(PROFILES_PATH, f"{base_name}.json")
    preset_path = os.path.join(RESOURCE_PATH, "platforms", "preset.json")

    try:
        # Robust Creation Logic: Preset + Base -> New
        final_config = {}
        
        # 1. Load Preset
        if os.path.exists(preset_path):
            with open(preset_path, 'r', encoding='utf-8') as f:
                final_config = json.load(f)
        
        # 2. Load Base (Overlay)
        if os.path.exists(base_path):
            with open(base_path, 'r', encoding='utf-8') as f:
                base_config = json.load(f)
                # Deep merge could be complex, for now simple update is usually enough for flat configs
                # For nested configs like 'platforms', we might want deep merge, but standard dict update is standard fallback
                final_config.update(base_config)
        elif not final_config:
             # No preset and no base? Empty.
             final_config = {}

        # 3. Save
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(final_config, f, indent=4, ensure_ascii=False)

        _profiles_cache = None # Invalidate cache
        return {"message": f"Profile '{new_name}' created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {e}")

@app.post("/api/profiles/rename")
async def rename_profile(request: ProfileRenameRequest):
    global _profiles_cache, _config_cache
    
    # Use injected handler
    if profile_handlers["rename"]:
        try:
            profile_handlers["rename"](request.old_name, request.new_name)
            _profiles_cache = None
            _config_cache.clear()
            return {"message": f"Renamed '{request.old_name}' to '{request.new_name}' (via host)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    old_path = os.path.join(PROFILES_PATH, f"{request.old_name}.json")
    new_path = os.path.join(PROFILES_PATH, f"{request.new_name}.json")
    
    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Source profile not found")
    if os.path.exists(new_path):
        raise HTTPException(status_code=409, detail="Destination profile name already exists")
        
    try:
        os.rename(old_path, new_path)
        
        # Check if we renamed the active profile
        mode, config = get_config_mode()
        current_active = config.get("active_profile")
        
        if current_active == request.old_name:
            # Update root config to point to new name
            config["active_profile"] = request.new_name
            with open(ROOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            # Clear config cache as the key changed
            _config_cache.clear()
            
        _profiles_cache = None
        return {"message": f"Renamed '{request.old_name}' to '{request.new_name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rename profile: {e}")

@app.post("/api/profiles/delete")
async def delete_profile(request: ProfileDeleteRequest):
    global _profiles_cache
    
    # Use injected handler
    if profile_handlers["delete"]:
        try:
            profile_handlers["delete"](request.profile)
            _profiles_cache = None
            return {"message": f"Profile '{request.profile}' deleted (via host)"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    target_path = os.path.join(PROFILES_PATH, f"{request.profile}.json")
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Profile not found")

    # Check if active
    mode, config = get_config_mode()
    if config.get("active_profile") == request.profile:
        raise HTTPException(status_code=400, detail="Cannot delete the currently active profile. Please switch to another profile first.")

    # Check if it's the last one (optional safety, though frontend should handle)
    profiles = [f for f in os.listdir(PROFILES_PATH) if f.endswith(".json")]
    if len(profiles) <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only remaining profile.")

    try:
        os.remove(target_path)
        _profiles_cache = None
        return {"message": f"Profile '{request.profile}' deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete profile: {e}")

# --- Task API Endpoints ---

class PlatformCreateRequest(BaseModel):
    name: str
    base_config: Optional[Dict[str, Any]] = None

@app.post("/api/platforms/create")
async def create_platform(request: PlatformCreateRequest):
    global _config_cache
    new_name = request.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Platform name cannot be empty")
    
    # Load current platforms from active profile
    profile_path = get_active_profile_path()
    try:
        with open(profile_path, 'r', encoding='utf-8-sig') as f:
            config = json.load(f)
        
        if "platforms" not in config: config["platforms"] = {}
        if new_name in config["platforms"]:
            raise HTTPException(status_code=409, detail="Platform already exists")
        
        # Use template from custom or a default
        template = config["platforms"].get("custom", {
            "tag": "custom", "group": "custom", "name": "Custom API",
            "api_url": "", "api_key": "", "api_format": "OpenAI",
            "model": "gpt-4o", "key_in_settings": ["api_url", "api_key", "model"]
        }).copy()
        
        template["tag"] = new_name
        template["name"] = new_name
        
        if request.base_config:
            template.update(request.base_config)
            
        config["platforms"][new_name] = template
        
        with open(profile_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
            
        _config_cache.clear()
        return {"message": f"Platform '{new_name}' created", "config": template}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/task/run")
async def run_task(payload: TaskPayload):
    if task_manager.status == "running":
        raise HTTPException(status_code=409, detail="A task is already running.")
    
    # 强制同步 Web 端缓存到磁盘，确保子进程能读取到编辑器中最新的修改
    try:
        cm = get_cache_manager()
        if hasattr(cm, 'project') and cm.project and getattr(cm, 'save_to_file_require_flag', False):
            # 获取输出路径（优先使用 payload 里的，如果没有则从当前配置读）
            output_path = payload.output_path or (await get_config()).get("label_output_path")
            if output_path:
                cm.save_to_file_require_path = output_path
                cm.save_to_file()
                cm.save_to_file_require_flag = False
    except Exception as e:
        print(f"Warning: Failed to flush web cache before task start: {e}")

    if not task_manager.start_task(payload.dict()):
        raise HTTPException(status_code=500, detail="Failed to start task process.")
    
    return {"success": True, "message": "Task started successfully."}

@app.post("/api/task/stop")
async def stop_task():
    task_manager.stop_task()
    return {"message": "Stop signal sent."}

@app.get("/api/task/status")
async def get_task_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "stats": task_manager.stats,
        "logs": list(task_manager.logs),
        "chart_data": list(task_manager.chart_data),
        "comparison": {
            "source": task_manager.current_source,
            "translation": task_manager.current_translation
        }
    }

class InternalComparisonPayload(BaseModel):
    source: str
    translation: str

@app.post("/api/internal/update_comparison")
async def internal_update_comparison(payload: InternalComparisonPayload):
    """Internal endpoint for subprocesses to push comparison data."""
    task_manager.current_source = payload.source
    task_manager.current_translation = payload.translation
    return {"status": "ok"}

# --- File Management Endpoints ---

@app.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...), policy: str = "default"):
    """
    Uploads a file to the project's 'updatetemp' directory with limit enforcement.
    policy: 'default' | 'buffer' | 'overwrite'
    """
    try:
        os.makedirs(UPDATETEMP_PATH, exist_ok=True)
        
        # 1. Get current sorted files
        files = []
        for f in os.listdir(UPDATETEMP_PATH):
            fp = os.path.join(UPDATETEMP_PATH, f)
            if os.path.isfile(fp):
                files.append((fp, os.path.getmtime(fp)))
        files.sort(key=lambda x: x[1]) # Oldest first
        
        # 2. Get Limit
        config = await get_config()
        limit = config.get("temp_file_limit", 10)
        count = len(files)
        
        # 3. Logic
        if count < limit:
            pass # Safe to upload
        
        elif count == limit:
            if policy == "default":
                return {
                    "status": "limit_reached", 
                    "limit": limit,
                    "oldest": os.path.basename(files[0][0])
                }
            elif policy == "overwrite":
                try: os.remove(files[0][0])
                except: pass
            elif policy == "buffer":
                pass # Allow +1
        
        elif count >= limit + 1:
            # Force delete oldest to bring back to limit (or limit+1 if we allow swap?)
            # Requirement: "Only to the 12th file... prompt user 'Earliest has been deleted'"
            # If current is 11 (limit+1), adding 12th means we MUST delete 1st.
            # So we delete oldest, and return a warning flag.
            try: os.remove(files[0][0])
            except: pass
            
            # Now count is back to limit (10). Wait, if we had 11, deleting 1 makes 10.
            # Then we save new file -> 11.
            # So we are effectively rotating at limit+1.
            return {
                "status": "forced_delete",
                "limit": limit,
                "deleted": os.path.basename(files[0][0]),
                "path": "" # Will be filled after save
            }

        # 4. Save File
        file_location = os.path.join(UPDATETEMP_PATH, file.filename)
        # Security check
        if not os.path.abspath(file_location).startswith(os.path.abspath(UPDATETEMP_PATH)):
             raise HTTPException(status_code=400, detail="Invalid file path")

        with open(file_location, "wb+") as file_object:
            file_object.write(await file.read())
            
        return {"info": f"file '{file.filename}' saved", "path": file_location}

    except Exception as e:
        # If it was our custom return, don't wrap it in 500
        if isinstance(e, HTTPException): raise e
        # If the return was a dict (status logic above), fastapi handles it? 
        # No, async def returns JSON directly. 
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}")

@app.get("/api/files/temp")
async def list_temp_files():
    """
    Lists files in the 'updatetemp' directory.
    """
    if not os.path.exists(UPDATETEMP_PATH):
        return []
    
    files = []
    for f in os.listdir(UPDATETEMP_PATH):
        full_path = os.path.join(UPDATETEMP_PATH, f)
        if os.path.isfile(full_path):
            files.append({
                "name": f,
                "path": full_path,
                "size": os.path.getsize(full_path)
            })
    return files

@app.delete("/api/files/temp")
async def delete_temp_files(request: DeleteFileRequest):
    """
    Deletes specified files from the 'updatetemp' directory.
    """
    if not os.path.exists(UPDATETEMP_PATH):
        return {"deleted": [], "failed": []}
    
    deleted = []
    failed = []
    
    for filename in request.files:
        # Security: Prevent path traversal
        safe_path = os.path.join(UPDATETEMP_PATH, os.path.basename(filename))
        if os.path.exists(safe_path):
            try:
                os.remove(safe_path)
                deleted.append(filename)
            except Exception as e:
                failed.append({"file": filename, "error": str(e)})
        else:
            failed.append({"file": filename, "error": "File not found"})
            
    return {"deleted": deleted, "failed": failed}

# --- Draft Management Endpoints ---

def save_draft_generic(filename: str, data: Any):
    try:
        os.makedirs(TEMP_EDIT_PATH, exist_ok=True)
        draft_path = os.path.join(TEMP_EDIT_PATH, filename)
        with open(draft_path, 'w', encoding='utf-8') as f:
            # If data is list of models, convert to list of dicts
            if isinstance(data, list) and len(data) > 0 and hasattr(data[0], 'dict'):
                json.dump([item.dict() for item in data], f, indent=4, ensure_ascii=False)
            # If data is simple dict/list/str
            elif hasattr(data, 'dict'):
                json.dump(data.dict(), f, indent=4, ensure_ascii=False)
            else:
                json.dump(data, f, indent=4, ensure_ascii=False)
        return {"message": "Draft saved."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save draft: {e}")

def get_draft_generic(filename: str):
    draft_path = os.path.join(TEMP_EDIT_PATH, filename)
    if not os.path.exists(draft_path):
        return None # Return None to indicate no draft
    try:
        with open(draft_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

@app.post("/api/draft/glossary")
async def save_glossary_draft(items: List[GlossaryItem]):
    return save_draft_generic("glossary_draft.json", items)

@app.get("/api/draft/glossary")
async def get_glossary_draft():
    return get_draft_generic("glossary_draft.json") or []

@app.post("/api/draft/exclusion")
async def save_exclusion_draft(items: List[ExclusionItem]):
    return save_draft_generic("exclusion_draft.json", items)

@app.get("/api/draft/exclusion")
async def get_exclusion_draft():
    return get_draft_generic("exclusion_draft.json") or []

@app.post("/api/draft/characterization")
async def save_characterization_draft(items: List[CharacterizationItem]):
    return save_draft_generic("characterization_draft.json", items)

@app.get("/api/draft/characterization")
async def get_characterization_draft():
    return get_draft_generic("characterization_draft.json") or []

@app.post("/api/draft/translation_example")
async def save_translation_example_draft(items: List[TranslationExampleItem]):
    return save_draft_generic("translation_example_draft.json", items)

@app.get("/api/draft/translation_example")
async def get_translation_example_draft():
    return get_draft_generic("translation_example_draft.json") or []

@app.post("/api/draft/world_building")
async def save_world_building_draft(data: StringContent):
    return save_draft_generic("world_building_draft.json", data.content)

@app.get("/api/draft/world_building")
async def get_world_building_draft():
    res = get_draft_generic("world_building_draft.json")
    if res is None: return {"content": ""}
    return {"content": res}

@app.post("/api/draft/writing_style")
async def save_writing_style_draft(data: StringContent):
    return save_draft_generic("writing_style_draft.json", data.content)

@app.get("/api/draft/writing_style")
async def get_writing_style_draft():
    res = get_draft_generic("writing_style_draft.json")
    if res is None: return {"content": ""}
    return {"content": res}

# --- Cache Management API ---

class CacheItem(BaseModel):
    id: int
    file_path: str
    text_index: int
    source: str
    translation: str
    original_translation: str
    translation_status: int
    modified: bool = False

class CacheUpdateRequest(BaseModel):
    item_id: int
    translation: str

class CacheLoadRequest(BaseModel):
    project_path: str

class ProofreadStartRequest(BaseModel):
    project_path: str

# Global cache manager instance
_cache_manager_instance = None

def get_cache_manager():
    """Get CacheManager singleton instance"""
    global _cache_manager_instance
    try:
        if _cache_manager_instance is None:
            from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
            _cache_manager_instance = CacheManager()
        return _cache_manager_instance
    except ImportError:
        raise HTTPException(status_code=500, detail="CacheManager not available")

@app.get("/api/cache/status")
async def get_cache_status():
    """Get cache loading status and basic info"""
    try:
        cache_manager = get_cache_manager()
        has_project = hasattr(cache_manager, 'project') and cache_manager.project and cache_manager.project.files

        if has_project:
            file_count = len(cache_manager.project.files)
            total_items = cache_manager.get_item_count()
            return {
                "loaded": True,
                "file_count": file_count,
                "total_items": total_items,
                "project_name": getattr(cache_manager.project, 'project_name', 'Unknown Project')
            }
        else:
            return {
                "loaded": False,
                "file_count": 0,
                "total_items": 0,
                "project_name": None
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache status: {e}")

@app.post("/api/cache/load")
async def load_cache(request: CacheLoadRequest):
    """Load cache data from project path"""
    try:
        cache_manager = get_cache_manager()

        # Smart path handling - detect if path already points to cache file or directory
        input_path = request.project_path.strip()

        # Normalize path separators for Windows
        input_path = os.path.normpath(input_path)

        # Determine the correct output_path for CacheManager
        if input_path.endswith("AinieeCacheData.json"):
            # Path points directly to cache file
            output_path = os.path.dirname(os.path.dirname(input_path))  # Remove /cache/AinieeCacheData.json
        elif input_path.endswith("cache"):
            # Path points to cache directory
            output_path = os.path.dirname(input_path)  # Remove /cache
        elif "AinieeCacheData.json" in input_path:
            # Handle case where path contains the filename but endswith failed due to encoding issues
            cache_filename_pos = input_path.find("AinieeCacheData.json")
            if cache_filename_pos != -1:
                cache_dir = input_path[:cache_filename_pos].rstrip(os.path.sep)
                output_path = os.path.dirname(cache_dir)
                input_path = os.path.join(cache_dir, "AinieeCacheData.json")
        else:
            # Path points to project directory (output directory)
            output_path = input_path

        # Validate that cache file exists before attempting to load
        if input_path.endswith("AinieeCacheData.json"):
            # User provided path to cache file directly - use it
            cache_file_to_check = input_path
        elif "AinieeCacheData.json" in input_path:
            # Path contains cache filename somewhere - extract it properly
            cache_filename_pos = input_path.find("AinieeCacheData.json")
            cache_file_to_check = input_path[:cache_filename_pos + len("AinieeCacheData.json")]
        else:
            # User provided project directory - construct cache file path
            cache_file_to_check = os.path.join(output_path, "cache", "AinieeCacheData.json")

        cache_file_to_check = os.path.normpath(cache_file_to_check)

        if not os.path.exists(cache_file_to_check):
            # Try to provide more helpful error information
            cache_dir = os.path.dirname(cache_file_to_check)
            if not os.path.exists(cache_dir):
                raise HTTPException(
                    status_code=404,
                    detail=f"Cache directory not found: {cache_dir}. Please check if the project path is correct."
                )
            else:
                # List files in cache directory to help debug
                try:
                    files_in_cache = os.listdir(cache_dir)
                    raise HTTPException(
                        status_code=404,
                        detail=f"Cache file 'AinieeCacheData.json' not found in {cache_dir}. Found files: {files_in_cache}"
                    )
                except PermissionError:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Cache file not found: {cache_file_to_check}. Permission denied accessing cache directory."
                    )

        # Load cache data - CacheManager expects output_path, not the full cache file path
        cache_manager.load_from_file(output_path)

        if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
            raise HTTPException(status_code=500, detail="Failed to load cache data")

        file_count = len(cache_manager.project.files)
        total_items = cache_manager.get_item_count()

        return {
            "success": True,
            "message": f"Cache loaded successfully. Found {file_count} files with {total_items} items.",
            "file_count": file_count,
            "total_items": total_items
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load cache: {e}")

@app.get("/api/cache/items")
async def get_cache_items(page: int = 1, page_size: Optional[int] = None, search: str = None):
    """Get paginated cache items"""
    try:
        cache_manager = get_cache_manager()

        if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
            raise HTTPException(status_code=400, detail="No cache data loaded")

        # Get page size from config if not provided
        if page_size is None:
            try:
                config = get_config_data()
                page_size = config.get('cache_editor_page_size', 15)
            except:
                page_size = 15

        # Extract items (similar to TUI's _extract_cache_items)
        items = []
        with cache_manager.file_lock:
            for file_path, cache_file in cache_manager.project.files.items():
                for idx, item in enumerate(cache_file.items):
                    if item.source_text and item.source_text.strip():
                        translation = ""
                        if item.translated_text:
                            translation = item.translated_text
                        elif item.polished_text:
                            translation = item.polished_text

                        # Include all items with source text (translated or not)
                        items.append({
                            'id': len(items),
                            'file_path': file_path,
                            'text_index': item.text_index,
                            'source': item.source_text,
                            'translation': translation,
                            'original_translation': translation,
                            'translation_status': item.translation_status,
                            'modified': False
                        })

        # Apply search filter
        if search and search.strip():
            search_lower = search.lower()
            items = [
                item for item in items
                if search_lower in item['source'].lower() or search_lower in item['translation'].lower()
            ]

        # Apply pagination
        total_items = len(items)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = items[start_idx:end_idx]

        total_pages = (total_items + page_size - 1) // page_size

        return {
            "items": paginated_items,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache items: {e}")

class CacheUpdateRequestWithPath(BaseModel):
    item_id: int
    translation: str
    project_path: str

@app.put("/api/cache/items/{item_id}")
async def update_cache_item(item_id: int, request: CacheUpdateRequestWithPath):
    """Update a cache item's translation"""
    try:
        cache_manager = get_cache_manager()

        if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
            raise HTTPException(status_code=400, detail="No cache data loaded")

        # Parse project path same way as load_cache
        input_path = request.project_path.strip()
        input_path = os.path.normpath(input_path)

        # Determine the correct output_path for CacheManager (same logic as load_cache)
        if input_path.endswith("AinieeCacheData.json"):
            output_path = os.path.dirname(os.path.dirname(input_path))
        elif input_path.endswith("cache"):
            output_path = os.path.dirname(input_path)
        elif "AinieeCacheData.json" in input_path:
            # Handle case where path contains the filename but endswith failed
            cache_filename_pos = input_path.find("AinieeCacheData.json")
            if cache_filename_pos != -1:
                cache_dir = input_path[:cache_filename_pos].rstrip(os.path.sep)
                output_path = os.path.dirname(cache_dir)
        else:
            output_path = input_path

        # Find the item to update
        item_found = False
        current_idx = 0

        with cache_manager.file_lock:
            for file_path, cache_file in cache_manager.project.files.items():
                for item in cache_file.items:
                    if item.source_text and item.source_text.strip():
                        if current_idx == item_id:
                            # Update the translation
                            new_translation = request.translation

                            if item.translation_status == 2:  # POLISHED
                                item.polished_text = new_translation
                            else:
                                item.translated_text = new_translation
                                if item.translation_status == 0:
                                    item.translation_status = 1

                            # Save to file
                            cache_manager.require_save_to_file(output_path)
                            item_found = True
                            break

                        current_idx += 1

                if item_found:
                    break

        if not item_found:
            raise HTTPException(status_code=404, detail="Cache item not found")

        return {"success": True, "message": "Cache item updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cache item: {e}")

@app.post("/api/cache/search")
async def search_cache_items(query: str, scope: str = "all", is_regex: bool = False):
    """Search cache items with advanced options"""
    try:
        cache_manager = get_cache_manager()

        if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
            raise HTTPException(status_code=400, detail="No cache data loaded")

        # Use cache manager's search functionality
        results = cache_manager.search_items(query, scope, is_regex, False)

        # Convert results to web format
        search_results = []
        for file_path, line_num, cache_item in results:
            translation = cache_item.translated_text or cache_item.polished_text or ""
            search_results.append({
                "file_path": file_path,
                "line_number": line_num,
                "source": cache_item.source_text,
                "translation": translation,
                "text_index": cache_item.text_index,
                "translation_status": cache_item.translation_status
            })

        return {
            "results": search_results,
            "total_found": len(search_results),
            "query": query,
            "scope": scope
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search cache: {e}")

# --- AI Proofread API ---

# Global state for proofread task
_proofread_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "issues": [],
    "tokens_used": 0,
    "error": None,
    "completed": False
}

@app.get("/api/proofread/status")
async def get_proofread_status():
    """Get AI proofread task status"""
    return _proofread_state

@app.post("/api/proofread/start")
async def start_proofread(request: ProofreadStartRequest, background_tasks: BackgroundTasks):
    """Start AI proofread task"""
    global _proofread_state

    if _proofread_state["running"]:
        raise HTTPException(status_code=400, detail="Proofread task already running")

    cache_manager = get_cache_manager()

    # Smart path handling - same as cache/load
    input_path = request.project_path.strip()
    input_path = os.path.normpath(input_path)

    # Determine the correct output_path
    if input_path.endswith("AinieeCacheData.json"):
        output_path = os.path.dirname(os.path.dirname(input_path))
    elif input_path.endswith("cache"):
        output_path = os.path.dirname(input_path)
    elif "AinieeCacheData.json" in input_path:
        cache_filename_pos = input_path.find("AinieeCacheData.json")
        if cache_filename_pos != -1:
            cache_dir = input_path[:cache_filename_pos].rstrip(os.path.sep)
            output_path = os.path.dirname(cache_dir)
    else:
        output_path = input_path

    # Validate cache file exists
    cache_file_path = os.path.join(output_path, "cache", "AinieeCacheData.json")
    if not os.path.exists(cache_file_path):
        raise HTTPException(status_code=404, detail=f"Cache file not found: {cache_file_path}")

    # Load cache if not already loaded or different path
    try:
        cache_manager.load_from_file(output_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load cache: {e}")

    if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
        raise HTTPException(status_code=400, detail="No cache data loaded")
        raise HTTPException(status_code=400, detail="No cache data loaded")

    # Reset state
    _proofread_state = {
        "running": True,
        "progress": 0,
        "total": 0,
        "issues": [],
        "tokens_used": 0,
        "error": None,
        "completed": False
    }

    # Start background task
    background_tasks.add_task(run_proofread_task)

    return {"status": "started"}

@app.post("/api/proofread/stop")
async def stop_proofread():
    """Stop AI proofread task"""
    global _proofread_state
    _proofread_state["running"] = False
    return {"status": "stopped"}

@app.post("/api/proofread/accept")
async def accept_proofread_issue(issue_id: int):
    """Accept a proofread issue and apply the correction"""
    global _proofread_state

    cache_manager = get_cache_manager()
    if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
        raise HTTPException(status_code=400, detail="No cache data loaded")

    # Find the issue
    issue = None
    for i, iss in enumerate(_proofread_state["issues"]):
        if iss.get("id") == issue_id:
            issue = iss
            break

    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    if not issue.get("corrected_translation"):
        raise HTTPException(status_code=400, detail="No correction available")

    # Apply correction to cache
    try:
        text_index = issue.get("text_index")
        file_path = issue.get("file_path")
        corrected_text = issue.get("corrected_translation")

        cache_file = cache_manager.project.get_file(file_path)
        if cache_file:
            item = cache_file.get_item(text_index)
            if item:
                item.translated_text = corrected_text
                item.translation_status = 4  # AI_PROOFREAD

                # Mark issue as accepted
                issue["accepted"] = True

                return {"status": "accepted", "text_index": text_index}

        raise HTTPException(status_code=404, detail="Cache item not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply correction: {e}")

class ProofreadSingleRequest(BaseModel):
    project_path: str
    file_path: str
    text_index: int
    translation: Optional[str] = None

@app.post("/api/proofread/single_check")
async def check_single_line(request: ProofreadSingleRequest):
    """
    On-demand check for a single line with context.
    Used when user clicks 'AI Analyze' on a specific line in editor.
    """
    try:
        from ModuleFolders.Service.Proofreader.AIProofreader import AIProofreader
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig

        cache_manager = get_cache_manager()
        
        # Ensure project is loaded
        if not hasattr(cache_manager, 'project') or not cache_manager.project.files:
             # Try to load if project is not in memory
             try:
                 load_cache_sync(request.project_path)
             except:
                 raise HTTPException(status_code=400, detail="Project cache not loaded")

        cache_file = cache_manager.project.get_file(request.file_path)
        if not cache_file:
            raise HTTPException(status_code=404, detail="File not found in cache")
        
        item = cache_file.get_item(request.text_index)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Determine target translation: prefer the one sent from web UI (editing state)
        target_translation = request.translation
        if target_translation is None:
            target_translation = item.translated_text or item.polished_text

        # Get context (5 lines before and after)
        list_idx = -1
        for idx, it in enumerate(cache_file.items):
            if it.text_index == request.text_index:
                list_idx = idx
                break
        
        if list_idx == -1:
             raise HTTPException(status_code=404, detail="Item index error")

        context_lines = 5
        start = max(0, list_idx - context_lines)
        end = min(len(cache_file.items), list_idx + context_lines + 1)
        
        context_parts = []
        for i in range(start, end):
            if i != list_idx:
                ctx_item = cache_file.items[i]
                if ctx_item.source_text:
                    # Provide original translation as context if available
                    ctx_trans = ctx_item.translated_text or ctx_item.polished_text or ""
                    context_parts.append(f"[{i}] {ctx_item.source_text[:60]} -> {ctx_trans[:40]}")
        
        context_str = "\n".join(context_parts)
        
        # Load Config
        config = load_config_sync()
        ai_proofreader = AIProofreader(config)
        
        # Run Check
        result = ai_proofreader.proofread_single(
            source=item.source_text,
            translation=target_translation,
            glossary=config.get("prompt_dictionary_data", []),
            context=context_str,
            world_building=config.get("world_building_content", ""),
            writing_style=config.get("writing_style_content", ""),
            characterization=config.get("characterization_data", [])
        )
        
        if not result.has_issues:
            return {"has_issues": False, "message": "AI分析后发现此行并无问题"}
        
        return {
            "has_issues": True,
            "issues": [
                {
                    "type": iss.type,
                    "severity": iss.severity,
                    "description": iss.description,
                    "suggestion": iss.suggestion,
                    "corrected_translation": result.corrected_translation
                } for iss in result.issues
            ],
            "corrected_translation": result.corrected_translation
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

def load_cache_sync(project_path: str):
    """Helper to load cache synchronously if needed"""
    cm = get_cache_manager()
    input_path = os.path.normpath(project_path.strip())
    if input_path.endswith("AinieeCacheData.json"):
        output_path = os.path.dirname(os.path.dirname(input_path))
    elif input_path.endswith("cache"):
        output_path = os.path.dirname(input_path)
    else:
        output_path = input_path
    cm.load_from_file(output_path)


@app.post("/api/proofread/clear")
async def clear_proofread_issues():
    """Clear all proofread issues"""
    global _proofread_state
    _proofread_state["issues"] = []
    _proofread_state["completed"] = False
    return {"status": "cleared"}

def load_config_sync() -> Dict[str, Any]:
    """Synchronously load the merged configuration."""
    mode, root_config = get_config_mode()
    current_profile_name = root_config.get("active_profile", "default")
    current_rules_name = root_config.get("active_rules_profile", "default")

    # Load Base Config
    profile_path = os.path.join(PROFILES_PATH, f"{current_profile_name}.json")
    loaded_config = {}
    if os.path.exists(profile_path):
        try:
            with open(profile_path, 'r', encoding='utf-8-sig') as f:
                loaded_config = json.load(f)
        except: pass

    # Load Rules Config
    rules_config = {}
    if current_rules_name and current_rules_name != "None":
        rules_path = os.path.join(RULES_PROFILES_PATH, f"{current_rules_name}.json")
        if os.path.exists(rules_path):
            try:
                with open(rules_path, 'r', encoding='utf-8-sig') as f:
                    rules_config = json.load(f)
            except: pass

    # Merge
    rule_keys = [
        "prompt_dictionary_data", "exclusion_list_data", "characterization_data",
        "world_building_content", "writing_style_content", "translation_example_data"
    ]
    for k in rule_keys:
        if k in rules_config:
            loaded_config[k] = rules_config[k]

    return loaded_config

def run_proofread_task():
    """Background task to run AI proofread"""
    global _proofread_state

    try:
        from ModuleFolders.Service.Proofreader.AIProofreader import AIProofreader
        from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig

        cache_manager = get_cache_manager()
        config = load_config_sync()

        # Collect items to check
        to_check = []
        with cache_manager.file_lock:
            for file_path, cache_file in cache_manager.project.files.items():
                for item in cache_file.items:
                    if item.translation_status in [1, 2]:  # TRANSLATED or POLISHED
                        source = item.source_text
                        target = item.translated_text or item.polished_text
                        if source and target:
                            to_check.append({
                                "index": len(to_check),
                                "text_index": item.text_index,
                                "file_path": file_path,
                                "source": source,
                                "translation": target
                            })

        _proofread_state["total"] = len(to_check)

        if not to_check:
            _proofread_state["running"] = False
            _proofread_state["completed"] = True
            return

        # Initialize proofreader
        ai_proofreader = AIProofreader(config)

        def progress_callback(current, total, prompt_tokens, completion_tokens):
            _proofread_state["progress"] = current
            _proofread_state["tokens_used"] = prompt_tokens + completion_tokens

        # Process using batching and threading to match CLI logic
        # 1. Determine batch size and threads from config
        # Default lines_limit is usually 20, threads 5
        batch_size = config.get("lines_limit", 20)
        thread_count = config.get("actual_thread_counts", 5) 
        if thread_count <= 0: thread_count = 5

        # 2. Split items into blocks
        blocks = [to_check[i:i + batch_size] for i in range(0, len(to_check), batch_size)]
        
        # 3. Define worker function
        import concurrent.futures
        
        results_lock = threading.Lock()
        
        def process_block(block):
            if not _proofread_state["running"]: return
            
            try:
                # Call the new batch method with full rules
                block_results = ai_proofreader.proofread_lines_block(
                    block,
                    glossary=config.get("prompt_dictionary_data", []),
                    world_building=config.get("world_building_content", ""),
                    writing_style=config.get("writing_style_content", ""),
                    characterization=config.get("characterization_data", [])
                )
                
                with results_lock:
                    # Update state with results
                    for idx, result in block_results.items():
                        original_item = next((item for item in block if item.get("index") == idx), None)
                        
                        if result.has_issues and original_item:
                            for issue in result.issues:
                                _proofread_state["issues"].append({
                                    "id": len(_proofread_state["issues"]) + 1,
                                    "text_index": original_item["text_index"],
                                    "file_path": original_item["file_path"],
                                    "source": original_item["source"],
                                    "original_translation": original_item["translation"],
                                    "corrected_translation": result.corrected_translation,
                                    "issue_type": issue.type,
                                    "severity": issue.severity,
                                    "description": issue.description,
                                    "accepted": False
                                })
                    
                    _proofread_state["progress"] += len(block)
                    p_tok = sum(r.prompt_tokens for r in block_results.values())
                    c_tok = sum(r.completion_tokens for r in block_results.values())
                    _proofread_state["tokens_used"] += (p_tok + c_tok)
                    
            except Exception as e:
                print(f"Error processing block: {e}")

        # 4. Execute with ThreadPool
        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            # We must monitor running state
            futures = []
            for block in blocks:
                if not _proofread_state["running"]: break
                futures.append(executor.submit(process_block, block))
            
            # Wait for completion
            concurrent.futures.wait(futures)

        _proofread_state["running"] = False
        _proofread_state["completed"] = True

    except Exception as e:
        _proofread_state["running"] = False
        _proofread_state["error"] = str(e)
        import traceback
        traceback.print_exc()

# --- Queue Management API ---

def get_queue_manager():
    """Get QueueManager instance"""
    try:
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueManager
        return QueueManager()
    except ImportError:
        raise HTTPException(status_code=500, detail="QueueManager not available")

@app.get("/api/queue")
async def get_queue():
    """Get all tasks in the queue with accurate processing status"""
    try:
        qm = get_queue_manager()

        # 清理过期的锁定状态
        if hasattr(qm, 'cleanup_stale_locks'):
            qm.cleanup_stale_locks()

        tasks = []

        for idx, task in enumerate(qm.tasks):
            # Ensure all tasks have the locked attribute and default status
            if not hasattr(task, 'locked'):
                task.locked = False
            if not hasattr(task, 'status'):
                task.status = "waiting"

            # 获取准确的处理状态
            is_actually_processing = False
            processing_info = None
            if hasattr(qm, 'is_task_actually_processing'):
                is_actually_processing = qm.is_task_actually_processing(idx)

            if hasattr(qm, 'get_task_processing_status'):
                processing_info = qm.get_task_processing_status(idx)

            # 如果任务被标记为locked但实际上没有在处理，则解锁
            if task.locked and not is_actually_processing:
                if hasattr(qm, 'stop_task_processing'):
                    qm.stop_task_processing(idx)
                    task.locked = False

            task_dict = {
                "task_type": task.task_type,
                "input_path": task.input_path,
                "output_path": getattr(task, "output_path", ""),
                "profile": getattr(task, "profile", ""),
                "rules_profile": getattr(task, "rules_profile", ""),
                "source_lang": getattr(task, "source_lang", ""),
                "target_lang": getattr(task, "target_lang", ""),
                "project_type": getattr(task, "project_type", ""),
                "platform": getattr(task, "platform", ""),
                "api_url": getattr(task, "api_url", ""),
                "api_key": getattr(task, "api_key", ""),
                "model": getattr(task, "model", ""),
                "threads": getattr(task, "threads", None),
                "retry": getattr(task, "retry", None),
                "timeout": getattr(task, "timeout", None),
                "rounds": getattr(task, "rounds", None),
                "pre_lines": getattr(task, "pre_lines", None),
                "lines_limit": getattr(task, "lines_limit", None),
                "tokens_limit": getattr(task, "tokens_limit", None),
                "think_depth": getattr(task, "think_depth", ""),
                "thinking_budget": getattr(task, "thinking_budget", None),
                "status": getattr(task, "status", "waiting"),
                "locked": getattr(task, "locked", False),

                # 新增：准确的处理状态信息
                "is_actually_processing": is_actually_processing,
                "is_processing": getattr(task, "is_processing", False),
                "process_start_time": getattr(task, "process_start_time", None),
                "last_activity_time": getattr(task, "last_activity_time", None)
            }
            tasks.append(task_dict)
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue")
async def add_to_queue(item: QueueTaskItem):
    """Add a new task to the queue"""
    try:
        qm = get_queue_manager()
        from ModuleFolders.Service.TaskQueue.QueueManager import QueueTaskItem as QueueTaskItemImpl

        # Create task with proper constructor parameters
        task = QueueTaskItemImpl(
            task_type=item.task_type,
            input_path=item.input_path,
            output_path=item.output_path,
            profile=item.profile,
            rules_profile=item.rules_profile,
            source_lang=item.source_lang,
            target_lang=item.target_lang,
            project_type=item.project_type,
            platform=item.platform,
            api_url=item.api_url,
            api_key=item.api_key,
            model=item.model,
            threads=item.threads,
            retry=item.retry,
            timeout=item.timeout,
            rounds=item.rounds,
            pre_lines=item.pre_lines,
            lines_limit=item.lines_limit,
            tokens_limit=item.tokens_limit,
            think_depth=item.think_depth,
            thinking_budget=item.thinking_budget
        )

        # Ensure the task has proper defaults
        task.status = "waiting"
        task.locked = False

        qm.add_task(task)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/queue/{index}")
async def remove_from_queue(index: int):
    """Remove a task from the queue"""
    try:
        qm = get_queue_manager()
        if qm.remove_task(index):
            return {"success": True}
        else:
            raise HTTPException(status_code=400, detail="Failed to remove task")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/queue/{index}")
async def update_queue_item(index: int, item: QueueTaskItem):
    """Update a task in the queue"""
    try:
        qm = get_queue_manager()
        if index < 0 or index >= len(qm.tasks):
            raise HTTPException(status_code=400, detail="Invalid task index")

        task = qm.tasks[index]
        task.task_type = item.task_type
        task.input_path = item.input_path
        if item.output_path:
            task.output_path = item.output_path
        if item.profile:
            task.profile = item.profile
        if item.rules_profile:
            task.rules_profile = item.rules_profile
        if item.source_lang:
            task.source_lang = item.source_lang
        if item.target_lang:
            task.target_lang = item.target_lang
        if item.project_type:
            task.project_type = item.project_type
        if item.platform:
            task.platform = item.platform
        if item.api_url:
            task.api_url = item.api_url
        if item.api_key:
            task.api_key = item.api_key
        if item.model:
            task.model = item.model
        if item.threads is not None:
            task.threads = item.threads
        if item.retry is not None:
            task.retry = item.retry
        if item.timeout is not None:
            task.timeout = item.timeout
        if item.rounds is not None:
            task.rounds = item.rounds
        if item.pre_lines is not None:
            task.pre_lines = item.pre_lines
        if item.lines_limit is not None:
            task.lines_limit = item.lines_limit
        if item.tokens_limit is not None:
            task.tokens_limit = item.tokens_limit
        if item.think_depth:
            task.think_depth = item.think_depth
        if item.thinking_budget is not None:
            task.thinking_budget = item.thinking_budget

        if qm.update_task(index, task):
            return {"success": True}
        else:
            raise HTTPException(status_code=400, detail="Failed to update task")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue/clear")
async def clear_queue():
    """Clear all tasks from the queue"""
    try:
        qm = get_queue_manager()
        if qm.clear_tasks():
            return {"success": True}
        else:
            raise HTTPException(status_code=400, detail="Failed to clear queue")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue/run")
async def run_queue():
    """Start queue execution"""
    try:
        qm = get_queue_manager()
        # Check if QueueManager has run_queue method, if not use alternative
        if hasattr(qm, 'run_queue'):
            qm.run_queue()
        else:
            # Alternative: set is_running flag or call CLI task execution
            qm.is_running = True
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queue/edit_file")
async def edit_queue_file():
    """Open queue file in external editor"""
    try:
        qm = get_queue_manager()
        # Check if method exists, if not provide fallback
        if hasattr(qm, 'open_queue_editor'):
            qm.open_queue_editor()
        else:
            # Fallback: could open file with system editor
            import subprocess
            import sys
            if sys.platform.startswith('win'):
                subprocess.run(['notepad', qm.queue_file])
            else:
                subprocess.run(['xdg-open', qm.queue_file])
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/queue/raw")
async def get_queue_raw():
    """Get raw queue JSON content"""
    try:
        qm = get_queue_manager()
        # Read the file directly if method doesn't exist
        if hasattr(qm, 'get_queue_json'):
            content = qm.get_queue_json()
        else:
            # Fallback: read file content directly
            try:
                with open(qm.queue_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            except FileNotFoundError:
                content = "[]"
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue/raw")
async def save_queue_raw(request: QueueRawRequest):
    """Save raw queue JSON content"""
    try:
        qm = get_queue_manager()
        if hasattr(qm, 'load_from_json'):
            qm.load_from_json(request.content)
        else:
            # Fallback: save to file directly and reload
            try:
                import rapidjson as json
                # Validate JSON first
                json.loads(request.content)
                # Save to file
                with open(qm.queue_file, 'w', encoding='utf-8') as f:
                    f.write(request.content)
                # Reload tasks
                qm.load_tasks()
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON format")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/queue/{from_index}/move")
async def move_queue_item(from_index: int, request: QueueMoveRequest):
    """Move a task to a different position"""
    try:
        qm = get_queue_manager()

        if from_index < 0 or from_index >= len(qm.tasks) or request.to_index < 0 or request.to_index >= len(qm.tasks):
            raise HTTPException(status_code=400, detail="Invalid task index")

        # Check if tasks can be modified
        if not qm.can_modify_task(from_index):
            raise HTTPException(status_code=400, detail="Source task is locked")

        # Check range between from and to for locked tasks
        start, end = min(from_index, request.to_index), max(from_index, request.to_index)
        for i in range(start, end + 1):
            if i != from_index and not qm.can_modify_task(i):
                raise HTTPException(status_code=400, detail="Cannot move task due to locked tasks in path")

        # Use QueueManager's move_task method
        if qm.move_task(from_index, request.to_index):
            return {"success": True}
        else:
            raise HTTPException(status_code=400, detail="Failed to move task")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/queue/reorder")
async def reorder_queue(request: QueueReorderRequest):
    """Reorder tasks according to new order"""
    try:
        qm = get_queue_manager()
        if len(request.new_order) != len(qm.tasks):
            raise HTTPException(status_code=400, detail="New order length doesn't match queue length")

        # Use QueueManager's reorder_tasks method if available
        if hasattr(qm, 'reorder_tasks'):
            if qm.reorder_tasks(request.new_order):
                return {"success": True}
            else:
                raise HTTPException(status_code=400, detail="Failed to reorder tasks")
        else:
            # Fallback: manual reorder
            # Validate indices first
            for i in request.new_order:
                if i < 0 or i >= len(qm.tasks):
                    raise HTTPException(status_code=400, detail="Invalid task index in new order")

            # Reorder tasks according to new order
            new_tasks = [qm.tasks[i] for i in request.new_order]
            qm.tasks = new_tasks
            qm.save_tasks()
            return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Static File Serving for the React Frontend ---

# This will serve the built React app (index.html, JS, CSS files)
# The React app should be built into a `dist` directory inside `Tools/WebServer`
dist_path = os.path.join(WEB_SERVER_PATH, 'dist')

if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

@app.get("/")
async def serve_index():
    """Serves the main index.html file of the React app."""
    index_path = os.path.join(dist_path, 'index.html')
    if not os.path.exists(index_path):
        # Fallback for development mode where `dist` might not exist
        return {"message": "AiNiee Backend is running. Frontend `dist` directory not found."}
    return FileResponse(index_path)

# --- Main Server Runner Function (to be called from ainiee_cli.py) ---

def run_server(host: str = "127.0.0.1", port: int = 8000, monitor_mode: bool = False):
    """Starts the FastAPI server in a separate thread."""
    global SYSTEM_MODE
    SYSTEM_MODE = "monitor" if monitor_mode else "full"
    
    # 动态记录 WebServer 的地址，以便子进程上报数据
    task_manager.api_url = f"http://{host}:{port}"
    
    try:
        import uvicorn

        def server_task():
            # Use reload=True for development, but it's better to disable it for production
            uvicorn.run(app, host=host, port=port, log_level="info")

        # Running in a daemon thread allows the main TUI to exit cleanly
        thread = threading.Thread(target=server_task, daemon=True)
        thread.start()
        return thread
    except ImportError:
        # This should ideally be handled before calling run_server
        print("Error: Uvicorn is required to run the web server.")
        return None
