#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug脚本 - 测试操作记录功能
真正调用主程序的LLM分析模块
"""

import os
import sys
import random
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# 导入主程序
from ainiee_cli import CLIMenu, console, i18n

# 随机操作池
MENU_ACTIONS = [
    ("主菜单 -> API设置", "MENU"),
    ("主菜单 -> 项目设置", "MENU"),
    ("主菜单 -> 提示词", "MENU"),
    ("主菜单 -> 插件设置", "MENU"),
    ("主菜单 -> 配置管理", "MENU"),
]

CONFIG_ACTIONS = [
    ("选择平台: OpenAI", "CONFIG"),
    ("选择平台: Claude", "CONFIG"),
    ("选择平台: Gemini", "CONFIG"),
    ("保存API配置", "CONFIG"),
    ("修改源语言: Japanese", "CONFIG"),
    ("修改目标语言: Chinese", "CONFIG"),
    ("修改线程数: 5", "CONFIG"),
]

TASK_ACTIONS = [
    ("选择文件模式: 单文件", "TASK"),
    ("选择文件: novel.epub", "TASK"),
    ("选择文件: game.json", "TASK"),
    ("选择文件夹: ./input/", "TASK"),
]

FILE_TYPES = [".EPUB", ".TXT", ".JSON", ".SRT", ".DOCX"]


def simulate_random_operations(cli: CLIMenu):
    """模拟随机用户操作"""
    print("\n[1] 模拟随机用户操作...")

    # 随机生成 5-12 条操作
    num_actions = random.randint(5, 12)
    all_actions = MENU_ACTIONS + CONFIG_ACTIONS + TASK_ACTIONS

    for _ in range(num_actions):
        action, category = random.choice(all_actions)
        cli.operation_logger.log(action, category)

    # 最后是开始翻译
    file_type = random.choice(FILE_TYPES)
    cli.operation_logger.log("主菜单 -> 开始翻译", "MENU")
    cli.operation_logger.log(f"开始翻译任务 -> 文件类型:{file_type}", "TASK")

    print(f"   已随机生成 {num_actions + 2} 条操作")

    # 显示操作记录
    print("\n[2] 当前操作记录:")
    for rec in cli.operation_logger.get_records():
        print(f"   [{rec['time']}] [{rec['category']}] {rec['action']}")


def trigger_key_error():
    """触发典型的配置KeyError"""
    config = {
        "target_platform": "OpenAI",
        "source_language": "Japanese",
        # 缺少 translation_prompt_selection - 用户忘记选择提示词
    }

    # 这会触发 KeyError
    prompt_id = config["translation_prompt_selection"]["last_selected_id"]
    return prompt_id


def main():
    print("=" * 60)
    print("操作记录功能测试 - 调用真实LLM分析模块")
    print("=" * 60)

    # 初始化主程序
    print("\n[0] 初始化CLIMenu...")
    cli = CLIMenu()

    # 确保操作记录器已启用
    if not cli.operation_logger.is_enabled():
        cli.operation_logger.enable()
    print(f"   操作记录器状态: {'已启用' if cli.operation_logger.is_enabled() else '已禁用'}")

    # 模拟随机操作
    simulate_random_operations(cli)

    # 触发错误
    print("\n[3] 触发配置KeyError...")
    try:
        trigger_key_error()
    except KeyError:
        error_msg = traceback.format_exc()
        print("   错误已触发!")

        # 调用真实的handle_crash
        print("\n[4] 调用真实的 handle_crash 方法...")
        print("=" * 60)
        cli.handle_crash(error_msg)


if __name__ == "__main__":
    main()
