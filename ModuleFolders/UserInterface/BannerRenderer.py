import os

import rapidjson as json
from rich.panel import Panel


def _load_version_string(project_root):
    version_text = "V0.0.0"
    try:
        version_path = os.path.join(project_root, "Resource", "Version", "version.json")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as file:
                version_data = json.load(file)
            full_version = version_data.get("version", "")
            if "V" in full_version:
                version_text = "V" + full_version.split("V")[-1].strip()
    except Exception:
        pass
    return version_text


def build_status_banner(cli, project_root):
    i18n = cli.i18n
    version_text = _load_version_string(project_root)

    src = cli.config.get("source_language", "Unknown")
    tgt = cli.config.get("target_language", "Unknown")
    conv_on = cli.config.get("response_conversion_toggle", False)
    conv_preset = cli.config.get("opencc_preset", "None")
    bilingual_order = cli.config.get("bilingual_text_order", "translation_first")

    is_tgt_simplified = any(key in tgt for key in ["简", "Simplified", "zh-cn"])
    is_preset_s2t = "s2t" in conv_preset.lower()
    conv_warning = ""
    if conv_on and is_tgt_simplified and is_preset_s2t:
        conv_warning = f" [bold red]{i18n.get('warn_conv_direction')}[/bold red]"

    plugin_enables = cli.root_config.get("plugin_enables", {})
    is_plugin_bilingual = plugin_enables.get("BilingualPlugin", False)
    bilingual_content_status = (
        f"[green]{i18n.get('banner_on')}[/green]"
        if is_plugin_bilingual
        else f"[red]{i18n.get('banner_off')}[/red]"
    )

    bilingual_file_on = cli.config.get("enable_bilingual_output", False)
    project_type = cli.config.get("translation_project", "AutoType")
    is_type_support_bilingual = project_type in ["Txt", "Epub", "Srt"]
    if bilingual_file_on:
        if is_type_support_bilingual:
            bilingual_file_status = (
                f"[green]{i18n.get('banner_on')}[/green] "
                f"([cyan]{bilingual_order.replace('_', ' ')}[/cyan])"
            )
        else:
            bilingual_file_status = (
                f"[yellow]{i18n.get('banner_on')} ({i18n.get('banner_unsupported')})[/yellow]"
            )
    else:
        bilingual_file_status = f"[red]{i18n.get('banner_off')}[/red]"

    detailed_on = cli.config.get("show_detailed_logs", False)
    detailed_status = (
        f"[green]{i18n.get('banner_on')}[/green]"
        if detailed_on
        else f"[red]{i18n.get('banner_off')}[/red]"
    )
    batch_merge_on = cli.config.get("enable_batch_auto_merge_ebook", False)
    batch_merge_status = (
        f"[green]{i18n.get('banner_on')}[/green]"
        if batch_merge_on
        else f"[red]{i18n.get('banner_off')}[/red]"
    )

    target_platform = cli.config.get("target_platform", "Unknown")
    user_threads = cli.config.get("user_thread_counts", 0)
    think_on = cli.config.get("think_switch", False)
    is_local = target_platform.lower() in ["sakura", "localllm", "murasaki"]

    conv_on_text = i18n.get("banner_on")
    conv_off_text = i18n.get("banner_off")
    conv_status = (
        f"[green]{conv_on_text} ({conv_preset})[/green]"
        if conv_on
        else f"[red]{conv_off_text}[/red]"
    )

    threads_display = "Auto" if user_threads == 0 else str(user_threads)
    think_status = ""
    if not is_local:
        think_text = f"[green]{conv_on_text}[/green]" if think_on else f"[red]{conv_off_text}[/red]"
        think_status = f" | [bold]{i18n.get('banner_think')}:[/bold] {think_text}"

    settings_line_1 = (
        f"| [bold]{i18n.get('banner_langs')}:[/bold] {src}->{tgt} | "
        f"[bold]{i18n.get('banner_conv')}:[/bold] {conv_status}{conv_warning} | "
        f"[bold]{i18n.get('banner_bilingual_file')}:[/bold] {bilingual_file_status} | "
        f"[bold]{i18n.get('banner_bilingual')}:[/bold] {bilingual_content_status} |"
    )
    settings_line_2 = (
        f"| [bold]{i18n.get('banner_api')}:[/bold] {target_platform} | "
        f"[bold]{i18n.get('banner_threads')}:[/bold] {threads_display} | "
        f"[bold]{i18n.get('banner_detailed')}:[/bold] {detailed_status} | "
        f"[bold]{i18n.get('banner_batch_merge')}:[/bold] {batch_merge_status}{think_status} |"
    )

    trans_prompt = cli.config.get("translation_prompt_selection", {}).get("last_selected_id", "common")
    polish_prompt = cli.config.get("polishing_prompt_selection", {}).get("last_selected_id", "common")
    if trans_prompt == "command":
        trans_prompt = i18n.get("label_none") or "None"
    if polish_prompt == "command":
        polish_prompt = i18n.get("label_none") or "None"
    settings_line_3 = (
        f"| [bold]{i18n.get('banner_prompts') or 'Prompts'}:[/bold] "
        f"{i18n.get('banner_trans') or 'Trans'}:[green]{trans_prompt}[/green] | "
        f"{i18n.get('banner_polish') or 'Polish'}:[green]{polish_prompt}[/green] |"
    )

    op_log_on = cli.operation_logger.is_enabled()
    op_log_status = f"[green]{conv_on_text}[/green]" if op_log_on else f"[red]{conv_off_text}[/red]"
    if op_log_on:
        op_log_hint = f" [dim]({i18n.get('banner_op_log_hint_on') or '敏感信息已抹除'})[/dim]"
    else:
        op_log_hint = f" [dim]({i18n.get('banner_op_log_hint_off') or '建议开启以获得更准确的LLM分析'})[/dim]"

    auto_proofread_on = cli.config.get("enable_auto_proofread", False)
    auto_proofread_line = ""
    if auto_proofread_on:
        auto_proofread_hint = (
            i18n.get("banner_auto_proofread_hint")
            or "翻译完成后自动调用AI校对，会产生额外的API费用，请注意API费用"
        )
        auto_proofread_line = (
            f"\n| [bold]{i18n.get('banner_auto_proofread') or '自动校对'}:[/bold] "
            f"[green]{conv_on_text}[/green] [dim]({auto_proofread_hint})[/dim] |"
        )

    settings_line_4 = (
        f"| [bold]{i18n.get('banner_op_log') or '操作记录'}:[/bold] "
        f"{op_log_status}{op_log_hint} |{auto_proofread_line}"
    )

    github_info = getattr(cli, "_cached_github_info", None)
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
            fail_msg = i18n.get("banner_github_fetch_failed") or "无法连接至Github，获取最新Commit和Release失败"
            github_status_line = f"\n[dim red]{fail_msg}[/dim red]"
    else:
        fail_msg = i18n.get("banner_github_fetch_failed") or "无法连接至Github，获取最新Commit和Release失败"
        github_status_line = f"\n[dim red]{fail_msg}[/dim red]"

    beta_warning_line = ""
    if "B" in version_text.upper():
        beta_msg = (
            i18n.get("banner_beta_warning")
            or "注意:您正处于Beta版本，可能存在一些问题，若您遇到了，请提交issue以供修复/优化"
        )
        beta_warning_line = f"\n[yellow]{beta_msg}[/yellow]"

    profile_display = f"[bold yellow]({cli.active_profile_name})[/bold yellow]"
    banner_content = (
        f"[bold cyan]AiNiee-Next[/bold cyan] [bold green]{version_text}[/bold green] {profile_display}\n"
        f"[dim]{i18n.get('label_project_credit')}[/dim]\n"
        f"[dim]{i18n.get('label_manga_core_credit')}[/dim]\n"
        f"{settings_line_1}\n"
        f"{settings_line_2}\n"
        f"{settings_line_3}\n"
        f"{settings_line_4}"
        f"{github_status_line}"
        f"{beta_warning_line}"
    )
    return Panel.fit(banner_content, title="Status", border_style="cyan")
