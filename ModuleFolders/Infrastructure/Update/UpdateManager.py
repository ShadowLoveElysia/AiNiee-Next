import os
import sys
import shutil
import zipfile
import requests
import time
import subprocess
from datetime import datetime, timezone
import rapidjson as json
from ModuleFolders.Base.Base import Base
from rich.table import Table
from rich.panel import Panel
from rich.prompt import IntPrompt

class UpdateManager(Base):
    GITHUB_REPO = "ShadowLoveElysia/AiNiee-CLI"
    UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    DOWNLOAD_MAIN_URL = f"https://github.com/ShadowLoveElysia/AiNiee-CLI/archive/refs/heads/main.zip"
    DOWNLOAD_TAG_URL = f"https://github.com/ShadowLoveElysia/AiNiee-CLI/archive/refs/tags/{{tag}}.zip"
    # Web Dist 专门下载地址 (假设项目有特定的分发机制或 branch)
    DOWNLOAD_WEB_STABLE_URL = f"https://github.com/ShadowLoveElysia/AiNiee-CLI/releases/latest/download/web-dist.zip"
    DOWNLOAD_WEB_PREVIEW_URL = f"https://github.com/ShadowLoveElysia/AiNiee-CLI/archive/refs/heads/web-dist-dev.zip"
    RAW_VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/Resource/Version/version.json"
    COMMITS_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
    RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    
    # GitHub 代理列表，首位为空表示直接连接
    GITHUB_PROXIES = [
        "", 
        "https://ghproxy.net/",
        "https://mirror.ghproxy.com/",
        "https://github.moeyy.xyz/",
        "https://gh-proxy.com/"
    ]

    def __init__(self, i18n_loader):
        super().__init__()
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.i18n = i18n_loader
        self._msgs = {
            "zh_CN": {
                "checking": "正在检查更新...",
                "no_update": "当前已是最新版本。",
                "downloading": "正在下载最新代码包",
                "downloading_proxy": "正在通过代理下载",
                "extracting": "正在解压更新内容",
                "applying": "正在覆盖安装更新",
                "complete": "更新已完成，正在重启脚本...",
                "fail_all": "所有下载尝试均已失败。",
                "retry_query": "是否继续重试自动下载？(有的时候多试几次就好了) [y/n]: ",
                "manual_guide": "\n[bold yellow]已进入手动更新模式：[/bold yellow]\n1. 请手动下载源码压缩包 (ZIP 格式)\n2. 在项目根目录下创建 [cyan]Update[/cyan] 文件夹\n3. 将下载好的 ZIP 文件放入该文件夹中\n4. 完成后在此处按 [green]Enter (回车键)[/green] 继续...",
                "no_zip_found": "未在 Update 文件夹中找到任何 ZIP 压缩包，请检查后重试。",
                "version_check": "正在检查压缩包版本...",
                "manual_already_latest": "压缩包内的版本与当前一致，无需更新。",
                "menu_title": "更新选项",
                "opt_commit": "最新 Commit (开发版)",
                "opt_release": "稳定 Release (正式版)",
                "opt_cancel": "取消更新",
                "commit_warn": "[bold yellow]提示: 最新 Commit 包含最新功能但可能存在不稳定因素。[/bold yellow]",
                "release_stable": "[bold green]推荐: 稳定 Release 经过测试，适合日常使用。[/bold green]",
                "current_version": "当前版本: {v}",
                "latest_commit": "最新 Commit: {msg} ({date})",
                "latest_release": "最新 Release: {tag} ({name})"
            },
            "ja": {
                "checking": "アップデートを確認中...",
                "no_update": "現在は最新バージョンです。",
                "downloading": "最新のパッケージをダウンロード中",
                "downloading_proxy": "プロキシ経由でダウンロード中",
                "extracting": "アップデート内容を展開中",
                "applying": "アップデートを適用中",
                "complete": "アップデートが完了しました。スクリプトを再起動しています...",
                "fail_all": "すべてのダウンロード試行が失敗しました。",
                "retry_query": "自動ダウンロードを再試行しますか？ [y/n]: ",
                "manual_guide": "\n[bold yellow]手動アップデートモード：[/bold yellow]\n1. ソースコードのZIPファイルをダウンロードしてください\n2. プロジェクト直下に [cyan]Update[/cyan] フォルダを作成してください\n3. ZIPファイルをそのフォルダに配置してください\n4. 配置後、[green]Enter[/green] キーを押してください...",
                "no_zip_found": "Update フォルダに ZIP ファイルが見つかりません。",
                "version_check": "ZIP内のバージョンを確認中...",
                "manual_already_latest": "ZIP内のバージョンは現在と同じです。",
                "menu_title": "更新オプション",
                "opt_commit": "最新 Commit (開発版)",
                "opt_release": "安定 Release (正式版)",
                "opt_cancel": "キャンセル",
                "commit_warn": "[bold yellow]警告: 最新 Commit は不安定な可能性があります。[/bold yellow]",
                "release_stable": "[bold green]推奨: 安定 Release はテスト済みです。[/bold green]",
                "current_version": "現在のバージョン: {v}",
                "latest_commit": "最新 Commit: {msg} ({date})",
                "latest_release": "最新 Release: {tag} ({name})"
            },
            "en": {
                "checking": "Checking for updates...",
                "no_update": "You are already on the latest version.",
                "downloading": "Downloading latest update package",
                "downloading_proxy": "Downloading via proxy",
                "extracting": "Extracting update content",
                "applying": "Applying update",
                "complete": "Update complete, restarting script...",
                "fail_all": "All download attempts failed.",
                "retry_query": "Would you like to retry automatic download? [y/n]: ",
                "manual_guide": "\n[bold yellow]Manual Update Mode:[/bold yellow]\n1. Download the source ZIP file manually\n2. Create an [cyan]Update[/cyan] folder in the project root\n3. Put the ZIP file into that folder\n4. Press [green]Enter[/green] here to continue...",
                "no_zip_found": "No ZIP file found in the Update folder.",
                "version_check": "Checking version in ZIP...",
                "manual_already_latest": "The version in the ZIP is the same as the current one.",
                "menu_title": "Update Options",
                "opt_commit": "Latest Commit (Dev)",
                "opt_release": "Stable Release (RLS)",
                "opt_cancel": "Cancel",
                "commit_warn": "[bold yellow]Note: Latest commit has new features but might be unstable.[/bold yellow]",
                "release_stable": "[bold green]Recommended: Stable Release is tested and suitable for daily use.[/bold green]",
                "current_version": "Current: {v}",
                "latest_commit": "Latest Commit: {msg} ({date})",
                "latest_release": "Latest Release: {tag} ({name})"
            }
        }

    def get_msg(self, key, **kwargs):
        lang = getattr(self.i18n, 'lang', 'en')
        lang_data = self._msgs.get(lang, self._msgs["en"])
        
        # 优先从内部消息表查找
        text = lang_data.get(key)
        
        # 如果内部没有，尝试从主 I18N 加载器查找
        if text is None:
            text = self.i18n.get(key)
            # 如果主加载器也返回了原始 Key，说明都没找到，回退到内部英文表或保持原样
            if text == key:
                text = self._msgs["en"].get(key, key)
        
        if kwargs:
            try: return text.format(**kwargs)
            except: return text
        return text

    def get_local_version_full(self):
        """从 version.json 读取本地完整的版本字符串"""
        try:
            v_path = os.path.join(self.project_root, "Resource", "Version", "version.json")
            if os.path.exists(v_path):
                with open(v_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("version", "AiNiee-Cli V0.0.0")
        except: pass
        return "AiNiee-Cli V0.0.0"

    def fetch_update_info(self):
        """获取 Commit 和 Release 信息"""
        headers = {"User-Agent": "AiNiee-CLI-Updater"}
        commit_info = None
        release_info = None

        # 1. Fetch Latest Commit
        try:
            response = requests.get(self.COMMITS_URL, headers=headers, timeout=5)
            if response.status_code == 200:
                commits = response.json()
                if commits:
                    latest = commits[0]
                    commit_info = {
                        "sha": latest.get("sha"),
                        "message": latest.get("commit", {}).get("message", "").split('\n')[0],
                        "date": latest.get("commit", {}).get("author", {}).get("date", "")[:10],
                        "datetime": latest.get("commit", {}).get("author", {}).get("date", ""),
                        "author": latest.get("commit", {}).get("author", {}).get("name", "Unknown")
                    }
        except: pass
        
        # 2. Fetch Latest Release
        try:
            response = requests.get(self.UPDATE_URL, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                release_info = {
                    "tag": data.get("tag_name"),
                    "name": data.get("name"),
                    "body": data.get("body", ""),
                    "date": data.get("published_at", "")[:10],
                    "datetime": data.get("published_at", "")
                }
        except: pass

        return commit_info, release_info

    def get_local_version(self):
        """获取纯版本号 (例如 2.0.1)"""
        v_full = self.get_local_version_full()
        return v_full.split('V')[-1].strip() if 'V' in v_full else v_full.replace('v', '').strip()

    def _format_time_ago(self, iso_datetime: str, lang: str = "zh_CN") -> str:
        """将ISO时间转换为相对时间（如'7小时前'）"""
        if not iso_datetime:
            return ""
        try:
            dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = now - dt

            seconds = diff.total_seconds()
            minutes = seconds / 60
            hours = minutes / 60
            days = hours / 24

            if lang == "zh_CN":
                if days >= 1:
                    return f"{int(days)}天前"
                elif hours >= 1:
                    return f"{int(hours)}小时前"
                elif minutes >= 1:
                    return f"{int(minutes)}分钟前"
                else:
                    return "刚刚"
            elif lang == "ja":
                if days >= 1:
                    return f"{int(days)}日前"
                elif hours >= 1:
                    return f"{int(hours)}時間前"
                elif minutes >= 1:
                    return f"{int(minutes)}分前"
                else:
                    return "たった今"
            else:
                if days >= 1:
                    return f"{int(days)}d ago"
                elif hours >= 1:
                    return f"{int(hours)}h ago"
                elif minutes >= 1:
                    return f"{int(minutes)}m ago"
                else:
                    return "just now"
        except:
            return ""

    def get_status_bar_info(self, lang: str = "zh_CN") -> dict:
        """
        获取状态栏显示信息

        Returns:
            dict: {
                "commit_text": "最新commit: xxx 7小时前",
                "release_text": "最新release: v2.0.1 3天前",
                "commit_info": {...},
                "release_info": {...}
            }
        """
        commit_info, release_info = self.fetch_update_info()
        result = {
            "commit_text": "",
            "release_text": "",
            "commit_info": commit_info,
            "release_info": release_info
        }

        if commit_info:
            time_ago = self._format_time_ago(commit_info.get("datetime", ""), lang)
            msg = commit_info.get("message", "")[:30]
            if len(commit_info.get("message", "")) > 30:
                msg += "..."
            if lang == "zh_CN":
                result["commit_text"] = f"最新Commit: {msg} {time_ago}"
            elif lang == "ja":
                result["commit_text"] = f"最新Commit: {msg} {time_ago}"
            else:
                result["commit_text"] = f"Latest Commit: {msg} {time_ago}"

        if release_info:
            time_ago = self._format_time_ago(release_info.get("datetime", ""), lang)
            tag = release_info.get("tag", "")
            if lang == "zh_CN":
                result["release_text"] = f"最新Release: {tag} {time_ago}"
            elif lang == "ja":
                result["release_text"] = f"最新Release: {tag} {time_ago}"
            else:
                result["release_text"] = f"Latest Release: {tag} {time_ago}"

        return result

    def check_update(self, silent=False):
        """检查更新 (用于启动时的静默检查)"""
        commit_info, release_info = self.fetch_update_info()
        local_v = self.get_local_version_full()
        
        # 只要有任何一个比本地新（或者只是为了触发提示）
        # 这里简单化处理：如果有 release 或 commit 信息，就认为可以进入更新菜单
        if commit_info or release_info:
            # 实际上由于 Commit 几乎总是更新的，这里我们只在 Release 不同时返回 True 以避免每次启动都提示
            if release_info:
                remote_v = release_info['tag']
                if remote_v.replace('v', '').replace('V', '').strip() != self.get_local_version():
                    if not silent: self.info(f"New release available: {remote_v}")
                    return True, remote_v
            return False, local_v
        
        return False, local_v

    def start_update(self, force=False):
        """开始下载并更新 (重构版本)"""
        self.print(f"[cyan]{self.get_msg('checking')}[/cyan]")
        local_v = self.get_local_version_full()
        commit_info, release_info = self.fetch_update_info()
        
        if not commit_info and not release_info:
            self.error("Failed to fetch update info from GitHub.")
            return

        # 构造选择菜单
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.get_msg("opt_commit"))
        table.add_row("[cyan]2.[/]", self.get_msg("opt_release"))
        table.add_row("[red]0.[/]", self.get_msg("opt_cancel"))
        
        self.print("\n")
        info_panel_text = self.get_msg("current_version", v=local_v) + "\n"
        if commit_info:
            info_panel_text += self.get_msg("latest_commit", msg=commit_info['message'], date=commit_info['date']) + "\n"
        if release_info:
            info_panel_text += self.get_msg("latest_release", tag=release_info['tag'], name=release_info['name'])
            
        self.print(Panel(info_panel_text, title=f"[bold cyan]{self.get_msg('menu_title')}[/bold cyan]", expand=False))
        self.print(table)
        
        choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2"], show_choices=False)
        
        download_url = ""
        target_v = ""
        changelog = ""
        
        if choice == 1:
            if not commit_info:
                self.error("Commit info not available.")
                return
            self.print(f"\n{self.get_msg('commit_warn')}")
            download_url = self.DOWNLOAD_MAIN_URL
            target_v = f"Commit: {commit_info['sha'][:7]}"
            changelog = f"[bold cyan]Latest Commit by {commit_info['author']}:[/bold cyan]\n{commit_info['message']}"
        elif choice == 2:
            if not release_info:
                self.error("Release info not available.")
                return
            self.print(f"\n{self.get_msg('release_stable')}")
            # Use the tag zip for stable release
            download_url = self.DOWNLOAD_TAG_URL.format(tag=release_info['tag'])
            target_v = release_info['tag']
            changelog = f"[bold green]Release: {release_info['name']}[/bold green]\n{release_info['body']}"
        else:
            return

        # 展示详细变更内容
        if changelog:
            self.print("\n")
            self.print(Panel(changelog, title=f"[bold magenta]Updating to {target_v}[/bold magenta]", border_style="cyan"))
            self.print("\n")

        temp_zip = os.path.join(self.project_root, "update_temp.zip")
        
        while True:
            success = False
            for proxy in self.GITHUB_PROXIES:
                try:
                    current_download_url = f"{proxy}{download_url}" if proxy else download_url
                    msg_key = 'downloading_proxy' if proxy else 'downloading'
                    proxy_name = proxy.split('/')[2] if proxy else "Direct"
                    self.print(f"[cyan]{self.get_msg(msg_key)} ({proxy_name})...[/cyan]")
                    
                    response = requests.get(current_download_url, stream=True, timeout=30)
                    response.raise_for_status()
                    
                    with open(temp_zip, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                    
                    success = True
                    break
                except Exception:
                    continue

            if success:
                self._apply_update_from_zip(temp_zip)
                return True
            else:
                self.print(f"[red]{self.get_msg('fail_all')}[/red]")
                try:
                    # Use a simple input for retry if needed, but IntPrompt is cleaner
                    retry = input(self.get_msg('retry_query')).strip().lower()
                    if retry != 'y': break
                except: break
        
        self.start_manual_update()

    def start_manual_update(self):
        """手动更新逻辑"""
        update_dir = os.path.join(self.project_root, "Update")
        if not os.path.exists(update_dir):
            os.makedirs(update_dir)
            
        self.print(self.get_msg('manual_guide'))
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            return False
        
        zips = [f for f in os.listdir(update_dir) if f.lower().endswith('.zip')]
        if not zips:
            self.error(self.get_msg('no_zip_found'))
            return False
            
        zips.sort(key=lambda x: os.path.getmtime(os.path.join(update_dir, x)), reverse=True)
        target_zip = os.path.join(update_dir, zips[0])
        
        self.print(f"[cyan]{self.get_msg('version_check')}[/cyan]")
        try:
            with zipfile.ZipFile(target_zip, 'r') as z:
                v_content = None
                for name in z.namelist():
                    if name.endswith("Resource/Version/version.json"):
                        v_content = z.read(name)
                        break
                
                if v_content:
                    data = json.loads(v_content)
                    v_str = data.get("version", "0.0.0")
                    zip_v = v_str.split('V')[-1].strip() if 'V' in v_str else v_str
                    local_v_full = self.get_local_version_full()
                    local_v = local_v_full.split('V')[-1].strip() if 'V' in local_v_full else local_v_full
                    
                    if zip_v == local_v:
                        self.print(f"[yellow]{self.get_msg('manual_already_latest')}[/yellow]")
                        time.sleep(2)
                        return False
        except Exception:
            pass # 即使检查失败也尝试更新
            
        return self._apply_update_from_zip(target_zip)

    def _apply_update_from_zip(self, zip_path):
        """通用的解压并应用更新逻辑"""
        temp_dir = os.path.join(self.project_root, "update_temp_extract")
        try:
            self.print(f"[cyan]{self.get_msg('extracting')}...[/cyan]")
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            extracted_subdirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
            if not extracted_subdirs: raise Exception("Failed to find extracted content.")
            
            src_dir = os.path.join(temp_dir, extracted_subdirs[0])
            self.print(f"[cyan]{self.get_msg('applying')}...[/cyan]")
            
            for item in os.listdir(src_dir):
                s = os.path.join(src_dir, item)
                d = os.path.join(self.project_root, item)
                if item in [".env", "output", "Resource/profiles", ".git", "__pycache__", ".venv", "Update"]:
                    continue
                if os.path.isdir(s):
                    if os.path.exists(d):
                        if item in ["ModuleFolders", "PluginScripts", "I18N", "Resource"]:
                            if item == "Resource": self._merge_resource_dir(s, d)
                            else:
                                shutil.rmtree(d)
                                shutil.copytree(s, d)
                        else: self._merge_dirs(s, d)
                    else: shutil.copytree(s, d)
                else: shutil.copy2(s, d)

            self.print(f"[bold green]{self.get_msg('complete')}[/bold green]")
            time.sleep(2)
            if "update_temp.zip" in zip_path and os.path.exists(zip_path): 
                os.remove(zip_path)
            if os.path.exists(temp_dir): 
                shutil.rmtree(temp_dir)
            self._restart_script()
            return True
        except Exception as e:
            self.error(f"Update application failed: {e}")
            return False

    def _merge_dirs(self, src, dst):
        for item in os.listdir(src):
            s, d = os.path.join(src, item), os.path.join(dst, item)
            if os.path.isdir(s):
                if not os.path.exists(d): os.makedirs(d)
                self._merge_dirs(s, d)
            else: shutil.copy2(s, d)

    def _merge_resource_dir(self, src, dst):
        for item in os.listdir(src):
            s, d = os.path.join(src, item), os.path.join(dst, item)
            if item in ["config.json", "profiles"]: continue
            if os.path.isdir(s):
                if not os.path.exists(d): os.makedirs(d)
                self._merge_dirs(s, d)
            else: shutil.copy2(s, d)

    def _restart_script(self):
        executable, script_path = sys.executable, os.path.join(self.project_root, "ainiee_cli.py")
        if sys.platform == "win32":
            launch_bat = os.path.join(self.project_root, "Launch.bat")
            if os.path.exists(launch_bat): subprocess.Popen(["cmd.exe", "/c", launch_bat], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else: subprocess.Popen([executable, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            launch_sh = os.path.join(self.project_root, "Launch.sh")
            if os.path.exists(launch_sh): subprocess.Popen(["bash", launch_sh])
            else: subprocess.Popen([executable, script_path])
        sys.exit(0)

    def setup_web_server(self, manual=False):
        """WebServer 独立下载与设置流程"""
        from rich.prompt import Confirm
        
        # 1. 检查运行库环境 (Environment Automatic Preparation)
        deps_missing = False
        try:
            import fastapi
            import uvicorn
        except ImportError:
            deps_missing = True
        
        if deps_missing:
            # 自动检测是否可以使用 uv
            use_uv = False
            try:
                subprocess.run(["uv", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                use_uv = True
            except: pass
            
            tool_name = "uv" if use_uv else "pip"
            msg = self.get_msg('msg_web_install_deps')
            
            # 如果是手动模式，或者检测到缺失，询问是否安装
            # 这里的 msg_web_install_deps 原文是 "检测到缺失运行环境，是否执行 'uv add...' ..."
            # 我们直接使用它即可
            if Confirm.ask(f"[yellow]{msg}[/yellow]"):
                self.print(f"[cyan]Installing dependencies using {tool_name}...[/cyan]")
                
                cmd = ["uv", "add"] if use_uv else [sys.executable, "-m", "pip", "install"]
                pkgs = ["fastapi", "uvicorn[standard]", "pydantic", "python-multipart"]
                
                try:
                    subprocess.run(cmd + pkgs, check=True)
                    self.print("[green]Dependencies installed successfully.[/green]")
                except subprocess.CalledProcessError:
                    self.error(f"Failed to install dependencies with {tool_name}. Please try manually.")

        # 2. 选择安装方式
        if not manual:
            self.print(f"\n[bold yellow]{self.get_msg('msg_web_dist_missing')}[/bold yellow]")
        
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.get_msg("menu_web_setup_1"))
        table.add_row("[cyan]2.[/]", self.get_msg("menu_web_setup_2"))
        table.add_row("[red]0.[/]", self.get_msg("menu_web_setup_3"))
        self.print(table)
        
        choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2"], show_choices=False)
        
        if choice == 1: # GitHub Download
            self.print(f"\n[cyan]{self.get_msg('menu_web_ver_stable')}[/cyan]")
            self.print(f"[yellow]{self.get_msg('menu_web_ver_preview')}[/yellow]")
            ver_choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["1", "2"], default=1)
            
            url = ""
            if ver_choice == 1:
                # Stable: Use Latest Release asset
                url = self.DOWNLOAD_WEB_STABLE_URL
            else:
                # Dev: Use Latest Pre-release asset (web-dist-dev.zip)
                self.print("[cyan]Fetching latest pre-release info...[/cyan]")
                try:
                    # 获取所有 Release
                    releases = requests.get(self.RELEASES_URL, timeout=10).json()
                    # 找到第一个 Prerelease
                    target_release = next((r for r in releases if r.get('prerelease')), None)
                    
                    if target_release:
                        # 找到 web-dist-dev.zip 资源
                        asset = next((a for a in target_release.get('assets', []) if a['name'] == 'web-dist-dev.zip'), None)
                        if asset:
                            url = asset['browser_download_url']
                            self.print(f"[green]Found Pre-release: {target_release['tag_name']}[/green]")
                        else:
                            self.error("Found pre-release but 'web-dist-dev.zip' asset is missing.")
                    else:
                        self.error("No pre-release found.")
                except Exception as e:
                    self.error(f"Failed to fetch pre-release info: {e}")
            
            if not url:
                self.error("Could not determine download URL.")
                return

            if ver_choice == 2:
                self.print(self.get_msg("msg_web_preview_warn"))
            
            temp_zip = os.path.join(self.project_root, "web_dist_temp.zip")
            success = False
            for proxy in self.GITHUB_PROXIES:
                try:
                    # 对于 API 获取的 URL，通常不需要代理前缀（因为是 AWS S3 链接），
                    # 但如果是 GitHub Release 页面链接，则可能需要。
                    # 为了兼容性，如果是 S3 链接 (github-releases.githubusercontent.com)，通常直连较快。
                    # 这里保留原有逻辑，如果 URL 已经是完整链接且不包含 github.com (比如 S3)，可能不需要 proxy
                    
                    target_url = url
                    if proxy and "github.com" in url:
                        target_url = f"{proxy}{url}"
                    
                    self.print(f"[cyan]{self.get_msg('msg_web_downloading')} ({proxy or 'Direct'})...[/cyan]")
                    r = requests.get(target_url, stream=True, timeout=60)
                    r.raise_for_status()
                    with open(temp_zip, 'wb') as f:
                        for chunk in r.iter_content(8192): f.write(chunk)
                    success = True; break
                except: continue
            
            if success:
                self._apply_web_dist(temp_zip)
            else:
                self.error(self.get_msg("msg_web_setup_fail"))

        elif choice == 2: # Local Build
            web_dir = os.path.join(self.project_root, "Tools", "WebServer")
            if not os.path.exists(os.path.join(web_dir, "package.json")):
                self.error("WebServer source files not found.")
                return
            
            self.print(f"[cyan]{self.get_msg('msg_web_build_start')}[/cyan]")
            try:
                subprocess.run("npm install && npm run build", shell=True, cwd=web_dir, check=True)
                self.print(f"[bold green]{self.get_msg('msg_web_setup_ok')}[/bold green]")
            except:
                self.error(self.get_msg("msg_web_setup_fail"))

    def _apply_web_dist(self, zip_path):
        """部署 Web 静态资源 (Smart Extraction)"""
        temp_extract = os.path.join(self.project_root, "web_extract_temp")
        dist_target = os.path.join(self.project_root, "Tools", "WebServer", "dist")
        
        try:
            self.print(f"[cyan]{self.get_msg('msg_web_extracting')}...[/cyan]")
            if os.path.exists(temp_extract): shutil.rmtree(temp_extract)
            with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(temp_extract)
            
            # 扫描包含 index.html 的文件夹 (Reinforced Deployment Logic)
            src_dist = None
            for root, dirs, files in os.walk(temp_extract):
                if "index.html" in files:
                    src_dist = root
                    break
            
            if src_dist:
                # Force rename/move to dist
                if os.path.exists(dist_target): shutil.rmtree(dist_target)
                shutil.copytree(src_dist, dist_target)
                self.print(f"[bold green]{self.get_msg('msg_web_setup_ok')}[/bold green]")
            else:
                raise Exception("index.html not found in package. Invalid distribution.")
                
        except Exception as e:
            self.error(f"Failed to deploy web assets: {e}")
        finally:
            if os.path.exists(zip_path): os.remove(zip_path)
            if os.path.exists(temp_extract): shutil.rmtree(temp_extract)
    def start_manual_update(self):
        """手动更新逻辑"""
        update_dir = os.path.join(self.project_root, "Update")
        if not os.path.exists(update_dir):
            os.makedirs(update_dir)
            
        self.print(self.get_msg('manual_guide'))
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            return False
        
        zips = [f for f in os.listdir(update_dir) if f.lower().endswith('.zip')]
        if not zips:
            self.error(self.get_msg('no_zip_found'))
            return False
            
        zips.sort(key=lambda x: os.path.getmtime(os.path.join(update_dir, x)), reverse=True)
        target_zip = os.path.join(update_dir, zips[0])
        
        self.print(f"[cyan]{self.get_msg('version_check')}[/cyan]")
        try:
            with zipfile.ZipFile(target_zip, 'r') as z:
                v_content = None
                for name in z.namelist():
                    if name.endswith("Resource/Version/version.json"):
                        v_content = z.read(name)
                        break
                
                if v_content:
                    data = json.loads(v_content)
                    v_str = data.get("version", "0.0.0")
                    zip_v = v_str.split('V')[-1].strip() if 'V' in v_str else v_str
                    local_v = self.get_local_version()
                    
                    if zip_v == local_v:
                        self.print(f"[yellow]{self.get_msg('manual_already_latest')}[/yellow]")
                        time.sleep(2)
                        return False
        except Exception:
            pass # 即使检查失败也尝试更新
            
        return self._apply_update_from_zip(target_zip)

    def _apply_update_from_zip(self, zip_path):
        """通用的解压并应用更新逻辑"""
        temp_dir = os.path.join(self.project_root, "update_temp_extract")
        try:
            self.print(f"[cyan]{self.get_msg('extracting')}...[/cyan]")
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            extracted_subdirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
            if not extracted_subdirs: raise Exception("Failed to find extracted content.")
            
            src_dir = os.path.join(temp_dir, extracted_subdirs[0])
            self.print(f"[cyan]{self.get_msg('applying')}...[/cyan]")
            
            for item in os.listdir(src_dir):
                s = os.path.join(src_dir, item)
                d = os.path.join(self.project_root, item)
                if item in [".env", "output", "Resource/profiles", ".git", "__pycache__", ".venv", "Update"]:
                    continue
                if os.path.isdir(s):
                    if os.path.exists(d):
                        if item in ["ModuleFolders", "PluginScripts", "I18N", "Resource"]:
                            if item == "Resource": self._merge_resource_dir(s, d)
                            else:
                                shutil.rmtree(d)
                                shutil.copytree(s, d)
                        else: self._merge_dirs(s, d)
                    else: shutil.copytree(s, d)
                else: shutil.copy2(s, d)

            self.print(f"[bold green]{self.get_msg('complete')}[/bold green]")
            time.sleep(2)
            if "update_temp.zip" in zip_path and os.path.exists(zip_path): 
                os.remove(zip_path)
            if os.path.exists(temp_dir): 
                shutil.rmtree(temp_dir)
            self._restart_script()
            return True
        except Exception as e:
            self.error(f"Update application failed: {e}")
            return False

    def _merge_dirs(self, src, dst):
        for item in os.listdir(src):
            s, d = os.path.join(src, item), os.path.join(dst, item)
            if os.path.isdir(s):
                if not os.path.exists(d): os.makedirs(d)
                self._merge_dirs(s, d)
            else: shutil.copy2(s, d)

    def _merge_resource_dir(self, src, dst):
        for item in os.listdir(src):
            s, d = os.path.join(src, item), os.path.join(dst, item)
            if item in ["config.json", "profiles"]: continue
            if os.path.isdir(s):
                if not os.path.exists(d): os.makedirs(d)
                self._merge_dirs(s, d)
            else: shutil.copy2(s, d)

    def _restart_script(self):
        executable, script_path = sys.executable, os.path.join(self.project_root, "ainiee_cli.py")
        if sys.platform == "win32":
            launch_bat = os.path.join(self.project_root, "Launch.bat")
            if os.path.exists(launch_bat): subprocess.Popen(["cmd.exe", "/c", launch_bat], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else: subprocess.Popen([executable, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            launch_sh = os.path.join(self.project_root, "Launch.sh")
            if os.path.exists(launch_sh): subprocess.Popen(["bash", launch_sh])
            else: subprocess.Popen([executable, script_path])
        sys.exit(0)
