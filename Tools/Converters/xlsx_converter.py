# /// script
# dependencies = [
#   "pandas",
#   "openpyxl",
#   "xlsxwriter",
# ]
# ///

import os
import sys
import argparse
import json
import pandas as pd
from pathlib import Path
import shutil

class XlsxConverter:
    """XLSX文件转换器，支持XLSX ↔ CSV转换"""

    def __init__(self, input_path: str, output_dir: str, mode: str = "to_csv"):
        """
        初始化转换器

        Args:
            input_path: 输入文件路径(XLSX或CSV目录)
            output_dir: 输出目录
            mode: 转换模式 'to_csv' 或 'to_xlsx'
        """
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.mode = mode
        self.metadata_file = self.output_dir / "xlsx_metadata.json"

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def xlsx_to_csv(self):
        """将XLSX文件转换为多个CSV文件（每个工作表一个CSV）"""
        if not self.input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {self.input_path}")

        if not self.input_path.suffix.lower() == ".xlsx":
            raise ValueError(f"输入文件必须是XLSX格式: {self.input_path}")

        print(f"正在读取XLSX文件: {self.input_path}")

        # 读取所有工作表
        try:
            # 使用openpyxl引擎以保持更好的格式兼容性
            xlsx_file = pd.ExcelFile(self.input_path, engine='openpyxl')
            sheet_names = xlsx_file.sheet_names

            print(f"发现 {len(sheet_names)} 个工作表: {', '.join(sheet_names)}")

            # 保存元数据信息
            metadata = {
                "original_file": str(self.input_path),
                "original_name": self.input_path.stem,
                "sheet_names": sheet_names,
                "conversion_mode": "xlsx_to_csv"
            }

            csv_files = []

            # 转换每个工作表为CSV
            for i, sheet_name in enumerate(sheet_names):
                print(f"正在处理工作表: {sheet_name}")

                # 读取工作表
                df = pd.read_excel(self.input_path, sheet_name=sheet_name, engine='openpyxl')

                # 跳过空工作表
                if df.empty:
                    print(f"  工作表 '{sheet_name}' 为空，跳过")
                    continue

                # 生成CSV文件名，使用安全的文件名
                safe_sheet_name = self._safe_filename(sheet_name)
                if len(sheet_names) == 1:
                    # 如果只有一个工作表，直接使用原文件名
                    csv_filename = f"{self.input_path.stem}.csv"
                else:
                    # 多个工作表时，加上工作表名后缀
                    csv_filename = f"{self.input_path.stem}_{i:02d}_{safe_sheet_name}.csv"

                csv_path = self.output_dir / csv_filename

                # 保存为CSV（使用UTF-8编码以确保中文兼容性）
                df.to_csv(csv_path, index=False, encoding='utf-8-sig')
                csv_files.append({
                    "sheet_name": sheet_name,
                    "csv_file": csv_filename,
                    "sheet_index": i
                })

                print(f"  已转换为: {csv_filename}")

            # 更新元数据
            metadata["csv_files"] = csv_files

            # 保存元数据
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            print(f"转换完成! 生成了 {len(csv_files)} 个CSV文件")
            print(f"元数据已保存到: {self.metadata_file}")

            return csv_files

        except Exception as e:
            print(f"转换失败: {e}")
            raise

    def csv_to_xlsx(self):
        """将CSV文件转换回XLSX文件"""
        if not self.metadata_file.exists():
            raise FileNotFoundError(f"元数据文件不存在: {self.metadata_file}")

        # 读取元数据
        with open(self.metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        print(f"正在恢复XLSX文件: {metadata['original_name']}.xlsx")

        # 输出XLSX文件路径
        output_xlsx = self.output_dir / f"{metadata['original_name']}.xlsx"

        try:
            # 使用ExcelWriter创建XLSX文件
            with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:

                for csv_info in metadata["csv_files"]:
                    sheet_name = csv_info["sheet_name"]
                    csv_file = csv_info["csv_file"]
                    csv_path = self.output_dir / csv_file

                    if not csv_path.exists():
                        print(f"警告: CSV文件不存在，跳过工作表 '{sheet_name}': {csv_path}")
                        continue

                    print(f"正在恢复工作表: {sheet_name}")

                    # 读取CSV文件
                    df = pd.read_csv(csv_path, encoding='utf-8-sig')

                    # 写入工作表
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            print(f"XLSX文件已恢复: {output_xlsx}")
            return str(output_xlsx)

        except Exception as e:
            print(f"回转失败: {e}")
            raise

    def _safe_filename(self, filename: str) -> str:
        """生成安全的文件名，移除或替换非法字符"""
        # 替换文件名中的非法字符
        invalid_chars = '<>:"/\\|?*'
        safe_name = filename
        for char in invalid_chars:
            safe_name = safe_name.replace(char, '_')

        # 限制长度并去除首尾空格
        return safe_name.strip()[:50]

    def convert(self):
        """执行转换操作"""
        if self.mode == "to_csv":
            return self.xlsx_to_csv()
        elif self.mode == "to_xlsx":
            return self.csv_to_xlsx()
        else:
            raise ValueError(f"不支持的转换模式: {self.mode}")

def main():
    """主函数 - 处理命令行参数"""
    parser = argparse.ArgumentParser(
        description="XLSX文件转换工具 - 支持XLSX ↔ CSV转换",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument('-i', '--input', required=True,
                       help="输入文件路径 (XLSX文件或包含CSV的目录)")
    parser.add_argument('-o', '--output', required=True,
                       help="输出目录路径")
    parser.add_argument('-m', '--mode', choices=['to_csv', 'to_xlsx'], default='to_csv',
                       help="转换模式:\n  to_csv: XLSX -> CSV (默认)\n  to_xlsx: CSV -> XLSX")
    parser.add_argument('--ainiee', action='store_true',
                       help="AiNiee模式标记（与主程序兼容）")

    args = parser.parse_args()

    try:
        # 创建转换器
        converter = XlsxConverter(
            input_path=args.input,
            output_dir=args.output,
            mode=args.mode
        )

        # 执行转换
        result = converter.convert()

        # 输出结果信息
        if args.mode == "to_csv":
            print(f"成功转换了 {len(result)} 个工作表到CSV格式")
        else:
            print(f"成功恢复XLSX文件: {result}")

        return 0

    except Exception as e:
        print(f"错误: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())