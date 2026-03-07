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
    GITHUB_REPO = "ShadowLoveElysia/AiNiee-Next"
    UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    DOWNLOAD_MAIN_URL = f"https://github.com/ShadowLoveElysia/AiNiee-Next/archive/refs/heads/main.zip"
    DOWNLOAD_TAG_URL = f"https://github.com/ShadowLoveElysia/AiNiee-Next/archive/refs/tags/{{tag}}.zip"
    # Web Dist 专门下载地址 (假设项目有特定的分发机制或 branch)
    DOWNLOAD_WEB_STABLE_URL = f"https://github.com/ShadowLoveElysia/AiNiee-Next/releases/latest/download/web-dist.zip"
    DOWNLOAD_WEB_PREVIEW_URL = f"https://github.com/ShadowLoveElysia/AiNiee-Next/archive/refs/heads/web-dist-dev.zip"
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
                "opt_prerelease": "Pre-release (测试版)",
                "opt_cancel": "取消更新",
                "commit_warn": "[bold yellow]提示: 最新 Commit 包含最新功能但可能存在不稳定因素。[/bold yellow]",
                "release_stable": "[bold green]推荐: 稳定 Release 经过测试，适合日常使用。[/bold green]",
                "prerelease_warn": "[bold yellow]提示: Pre-release 是测试版本，可能存在未知问题。[/bold yellow]",
                "current_version": "当前版本: {v}",
                "latest_commit": "最新 Commit: {msg} ({date})",
                "latest_release": "最新 Release: {tag} ({name})",
                "latest_prerelease": "最新 Pre-release: {tag} ({name})"
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
                "opt_prerelease": "Pre-release (テスト版)",
                "opt_cancel": "キャンセル",
                "commit_warn": "[bold yellow]警告: 最新 Commit は不安定な可能性があります。[/bold yellow]",
                "release_stable": "[bold green]推奨: 安定 Release はテスト済みです。[/bold green]",
                "prerelease_warn": "[bold yellow]警告: Pre-release はテスト版で、未知の問題がある可能性があります。[/bold yellow]",
                "current_version": "現在のバージョン: {v}",
                "latest_commit": "最新 Commit: {msg} ({date})",
                "latest_release": "最新 Release: {tag} ({name})",
                "latest_prerelease": "最新 Pre-release: {tag} ({name})"
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
                "opt_prerelease": "Pre-release (Beta)",
                "opt_cancel": "Cancel",
                "commit_warn": "[bold yellow]Note: Latest commit has new features but might be unstable.[/bold yellow]",
                "release_stable": "[bold green]Recommended: Stable Release is tested and suitable for daily use.[/bold green]",
                "prerelease_warn": "[bold yellow]Note: Pre-release is a beta version and may have unknown issues.[/bold yellow]",
                "current_version": "Current: {v}",
                "latest_commit": "Latest Commit: {msg} ({date})",
                "latest_release": "Latest Release: {tag} ({name})",
                "latest_prerelease": "Latest Pre-release: {tag} ({name})"
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

    def _github_headers(self) -> dict:
        return {"User-Agent": "AiNiee-Next-Updater"}

    def _fetch_releases_safe(self, timeout: int = 5):
        """
        安全获取 GitHub releases 列表。
        返回: (releases_list, error_message)
        """
        try:
            response = requests.get(self.RELEASES_URL, headers=self._github_headers(), timeout=timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return [], str(e)

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)], ""

        if isinstance(data, dict):
            return [], str(data.get("message", "Unexpected release response object."))

        return [], f"Unexpected release response type: {type(data).__name__}"

    def _build_release_info(self, release_data: dict) -> dict:
        """从 release JSON 构建统一的版本信息结构。"""
        published_at = str(release_data.get("published_at", "") or "")
        return {
            "tag": str(release_data.get("tag_name", "") or ""),
            "name": str(release_data.get("name", "") or ""),
            "body": str(release_data.get("body", "") or ""),
            "date": published_at[:10],
            "datetime": published_at
        }

    def _select_main_prerelease(self, releases: list):
        """
        选择主程序 Pre-release。
        策略：
        1) 优先最新 dev-build（排除 web-dist 专用预发布）
        2) 其次匹配 V...B（传统 Beta tag）
        3) 最后回退到最新普通 pre-release
        """
        candidates = []
        for release in releases:
            if not isinstance(release, dict):
                continue
            if not release.get("prerelease"):
                continue

            tag = str(release.get("tag_name", "") or "")
            tag_lower = tag.lower()

            # 排除 Web UI 专用 pre-release，避免与主程序预览版冲突
            if "web-dist" in tag_lower:
                continue
            assets = release.get("assets", [])
            if isinstance(assets, list):
                asset_names = [str(a.get("name", "")).lower() for a in assets if isinstance(a, dict)]
                if any(name in ("web-dist-dev.zip", "web-dist.zip") for name in asset_names):
                    continue

            candidates.append(release)

        if not candidates:
            return None

        # GitHub 返回通常已按时间倒序，这里再按发布时间显式排序一次以增强健壮性
        sorted_candidates = sorted(
            candidates,
            key=lambda r: str(r.get("published_at", "") or ""),
            reverse=True
        )

        for release in sorted_candidates:
            tag = str(release.get("tag_name", "") or "").lower()
            name = str(release.get("name", "") or "").lower()
            if "dev-build" in tag or "dev-build" in name:
                return release

        for release in sorted_candidates:
            tag_upper = str(release.get("tag_name", "") or "").upper()
            if "V" in tag_upper and "B" in tag_upper:
                return release

        for release in sorted_candidates:
            tag_lower = str(release.get("tag_name", "") or "").lower()
            name_lower = str(release.get("name", "") or "").lower()
            if "beta" in tag_lower or "beta" in name_lower:
                return release

        return sorted_candidates[0]

    def _select_web_preview_asset(self, releases: list):
        """
        在 pre-release 中选择 Web 预览包资产。
        优先 web-dist-dev.zip，若不存在则回退 web-dist.zip。
        """
        preferred_assets = ("web-dist-dev.zip", "web-dist.zip")
        for release in releases:
            if not isinstance(release, dict):
                continue
            if not release.get("prerelease"):
                continue

            assets = release.get("assets", [])
            if not isinstance(assets, list):
                continue

            for preferred_name in preferred_assets:
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    if asset.get("name") == preferred_name and asset.get("browser_download_url"):
                        return release, asset
        return None, None

    def fetch_update_info(self):
        """获取 Commit, Release 和 Pre-release 信息"""
        headers = self._github_headers()
        commit_info = None
        release_info = None
        prerelease_info = None

        # 1. Fetch Latest Commit
        try:
            response = requests.get(self.COMMITS_URL, headers=headers, timeout=5)
            if response.status_code == 200:
                commits = response.json()
                if isinstance(commits, list) and commits:
                    latest = commits[0]
                    if isinstance(latest, dict):
                        commit_block = latest.get("commit", {})
                        if not isinstance(commit_block, dict):
                            commit_block = {}
                        author_block = commit_block.get("author", {})
                        if not isinstance(author_block, dict):
                            author_block = {}
                        commit_info = {
                            "sha": latest.get("sha"),
                            "message": str(commit_block.get("message", "")).split('\n')[0],
                            "date": str(author_block.get("date", ""))[:10],
                            "datetime": str(author_block.get("date", "")),
                            "author": str(author_block.get("name", "Unknown") or "Unknown")
                        }
        except: pass

        # 2. Fetch Latest Release (stable)
        try:
            response = requests.get(self.UPDATE_URL, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    release_info = self._build_release_info(data)
        except: pass

        # 3. Fetch Latest Pre-release (主程序预览版，优先 dev-build，排除 WebUI 专用 pre-release)
        try:
            releases, _ = self._fetch_releases_safe(timeout=5)
            if releases:
                selected = self._select_main_prerelease(releases)
                if selected:
                    prerelease_info = self._build_release_info(selected)
        except: pass

        return commit_info, release_info, prerelease_info

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
        commit_info, release_info, prerelease_info = self.fetch_update_info()
        result = {
            "commit_text": "",
            "release_text": "",
            "prerelease_text": "",
            "commit_info": commit_info,
            "release_info": release_info,
            "prerelease_info": prerelease_info
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

        if prerelease_info:
            time_ago = self._format_time_ago(prerelease_info.get("datetime", ""), lang)
            tag = prerelease_info.get("tag", "")
            if lang == "zh_CN":
                result["prerelease_text"] = f"最新Beta: {tag} {time_ago}"
            elif lang == "ja":
                result["prerelease_text"] = f"最新Beta: {tag} {time_ago}"
            else:
                result["prerelease_text"] = f"Latest Beta: {tag} {time_ago}"

        return result

    def check_update(self, silent=False):
        """检查更新 (用于启动时的静默检查)"""
        commit_info, release_info, _ = self.fetch_update_info()
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
        commit_info, release_info, prerelease_info = self.fetch_update_info()

        if not commit_info and not release_info and not prerelease_info:
            self.error("Failed to fetch update info from GitHub.")
            return

        # 构造选择菜单
        table = Table(show_header=False, box=None)
        table.add_row("[cyan]1.[/]", self.get_msg("opt_commit"))
        table.add_row("[cyan]2.[/]", self.get_msg("opt_release"))
        table.add_row("[yellow]3.[/]", self.get_msg("opt_prerelease"))
        table.add_row("[red]0.[/]", self.get_msg("opt_cancel"))

        self.print("\n")
        info_panel_text = self.get_msg("current_version", v=local_v) + "\n"
        if commit_info:
            info_panel_text += self.get_msg("latest_commit", msg=commit_info['message'], date=commit_info['date']) + "\n"
        if release_info:
            info_panel_text += self.get_msg("latest_release", tag=release_info['tag'], name=release_info['name']) + "\n"
        if prerelease_info:
            info_panel_text += self.get_msg("latest_prerelease", tag=prerelease_info['tag'], name=prerelease_info['name'])

        self.print(Panel(info_panel_text, title=f"[bold cyan]{self.get_msg('menu_title')}[/bold cyan]", expand=False))
        self.print(table)

        choice = IntPrompt.ask(self.i18n.get('prompt_select'), choices=["0", "1", "2", "3"], show_choices=False)

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
            download_url = self.DOWNLOAD_TAG_URL.format(tag=release_info['tag'])
            target_v = release_info['tag']
            changelog = f"[bold green]Release: {release_info['name']}[/bold green]\n{release_info['body']}"
        elif choice == 3:
            if not prerelease_info:
                self.error("Pre-release info not available.")
                return
            self.print(f"\n{self.get_msg('prerelease_warn')}")
            download_url = self.DOWNLOAD_TAG_URL.format(tag=prerelease_info['tag'])
            target_v = prerelease_info['tag']
            changelog = f"[bold yellow]Pre-release: {prerelease_info['name']}[/bold yellow]\n{prerelease_info['body']}"
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

            # 解压并尝试恢复Unix权限
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
                # 在Unix系统上恢复文件权限
                if sys.platform != "win32":
                    self._restore_unix_permissions(zip_ref, temp_dir)

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

            # 在Unix系统上修复项目目录权限
            if sys.platform != "win32":
                self._fix_project_permissions()

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

    def _restore_unix_permissions(self, zip_ref, extract_dir):
        """在Unix系统上恢复ZIP文件中存储的权限信息"""
        for info in zip_ref.infolist():
            if info.is_dir():
                continue

            extracted_path = os.path.join(extract_dir, info.filename)
            if not os.path.exists(extracted_path):
                continue

            # ZIP文件的external_attr高16位存储Unix权限
            unix_mode = (info.external_attr >> 16) & 0o777

            if unix_mode:
                try:
                    os.chmod(extracted_path, unix_mode)
                except OSError:
                    pass

        # 额外确保常见可执行文件有执行权限
        self._ensure_executable_permissions(extract_dir)

    def _ensure_executable_permissions(self, directory):
        """确保常见可执行文件类型有执行权限"""
        if sys.platform == "win32":
            return

        executable_extensions = {'.sh', '.py', '.pl', '.rb', '.bash'}
        executable_names = {'Launch.sh', 'ainiee_cli.py'}

        for root, dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                _, ext = os.path.splitext(filename)

                # 检查是否需要可执行权限
                needs_exec = (
                    ext.lower() in executable_extensions or
                    filename in executable_names
                )

                if needs_exec:
                    try:
                        # 获取当前权限并添加执行位
                        current_mode = os.stat(filepath).st_mode
                        # 添加用户执行权限，如果有读权限则也添加组和其他的执行权限
                        new_mode = current_mode | 0o111
                        os.chmod(filepath, new_mode)
                    except OSError:
                        pass

    def _fix_project_permissions(self):
        """修复项目目录中的文件权限（仅Unix系统）"""
        if sys.platform == "win32":
            return

        self._ensure_executable_permissions(self.project_root)

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
                    releases, err = self._fetch_releases_safe(timeout=10)
                    if err and not releases:
                        self.error(f"Failed to fetch pre-release info: {err}")
                    else:
                        target_release, asset = self._select_web_preview_asset(releases)
                        if target_release and asset:
                            url = str(asset.get('browser_download_url', '') or '')
                            self.print(
                                f"[green]Found Pre-release: {target_release.get('tag_name', 'unknown')} "
                                f"({asset.get('name', 'asset')})[/green]"
                            )
                        else:
                            self.error("No pre-release with 'web-dist-dev.zip' or 'web-dist.zip' asset found.")
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
