"""
校对报告生成与管理
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus


def correction_target_field(report_item, cache_item) -> str:
    target_field = report_item.ai_check.get("target_field")
    if target_field in ("translated_text", "polished_text"):
        return target_field
    report_text = report_item.translated_text or ""
    if report_text == (cache_item.translated_text or ""):
        return "translated_text"
    if report_text == (cache_item.polished_text or ""):
        return "polished_text"
    return "translated_text"


def apply_report_correction(report_item, cache_item, corrected_text: str) -> str:
    """Share the legacy report's translated/polished write-back semantics."""
    target_field = correction_target_field(report_item, cache_item)
    if target_field == "polished_text":
        cache_item.polished_text = corrected_text
        cache_item.translation_status = TranslationStatus.POLISHED
    else:
        cache_item.translated_text = corrected_text
        cache_item.polished_text = ""
        cache_item.translation_status = TranslationStatus.TRANSLATED
    if cache_item.extra is None:
        cache_item.extra = {}
    cache_item.extra["ai_proofread"] = {"target_field": target_field, "applied": True}
    return target_field


@dataclass
class ProofreadReportMeta:
    """报告元数据"""
    version: str = "1.0"
    created_at: str = ""
    source_file: str = ""
    model: str = ""
    total_items: int = 0
    checked_items: int = 0
    items_with_issues: int = 0


@dataclass
class ProofreadReportSummary:
    """报告摘要"""
    ai_issues: Dict[str, int] = field(default_factory=lambda: {
        "high": 0, "medium": 0, "low": 0
    })
    rule_issues: Dict[str, int] = field(default_factory=dict)


@dataclass
class ProofreadReportItem:
    """报告条目"""
    index: int
    source_text: str
    translated_text: str
    corrected_text: str = ""
    ai_check: Dict[str, Any] = field(default_factory=dict)
    rule_check: Dict[str, Any] = field(default_factory=dict)


class ProofreadReport:
    """校对报告"""

    def __init__(self, source_file: str = "", model: str = ""):
        self.meta = ProofreadReportMeta(
            created_at=datetime.now().isoformat(),
            source_file=source_file,
            model=model
        )
        self.summary = ProofreadReportSummary()
        self.items: List[ProofreadReportItem] = []

    def add_item(self, item: ProofreadReportItem):
        """添加报告条目"""
        self.items.append(item)

        # 更新摘要统计
        if item.ai_check.get("has_issues"):
            for issue in item.ai_check.get("issues", []):
                severity = issue.get("severity", "low")
                self.summary.ai_issues[severity] = \
                    self.summary.ai_issues.get(severity, 0) + 1

        if item.rule_check.get("has_issues"):
            for issue in item.rule_check.get("issues", []):
                rule_name = issue.get("rule_name", "unknown")
                self.summary.rule_issues[rule_name] = \
                    self.summary.rule_issues.get(rule_name, 0) + 1

    def finalize(self, total_items: int, checked_items: int):
        """完成报告"""
        self.meta.total_items = total_items
        self.meta.checked_items = checked_items
        self.meta.items_with_issues = len(self.items)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "meta": asdict(self.meta),
            "summary": {
                "ai_issues": self.summary.ai_issues,
                "rule_issues": self.summary.rule_issues
            },
            "items": [asdict(item) for item in self.items]
        }

    def save(self, output_dir: str) -> str:
        """保存报告到文件"""
        # 确保目录存在
        proofread_dir = os.path.join(output_dir, "proofread")
        os.makedirs(proofread_dir, exist_ok=True)

        # 生成文件名
        source_name = os.path.splitext(
            os.path.basename(self.meta.source_file)
        )[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{source_name}_ai_proofread_{timestamp}.json"
        filepath = os.path.join(proofread_dir, filename)

        # 保存
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        return filepath

    @classmethod
    def load(cls, filepath: str) -> "ProofreadReport":
        """从文件加载报告"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        report = cls()
        report.meta = ProofreadReportMeta(**data.get("meta", {}))
        
        summary_data = data.get("summary", {})
        report.summary.ai_issues = summary_data.get("ai_issues", {})
        report.summary.rule_issues = summary_data.get("rule_issues", {})

        for item_data in data.get("items", []):
            report.items.append(ProofreadReportItem(**item_data))

        return report

    @staticmethod
    def list_reports(output_dir: str) -> List[str]:
        """列出所有校对报告"""
        proofread_dir = os.path.join(output_dir, "proofread")
        if not os.path.exists(proofread_dir):
            return []

        reports = []
        for f in os.listdir(proofread_dir):
            if f.endswith("_ai_proofread_") or "_ai_proofread_" in f:
                reports.append(os.path.join(proofread_dir, f))

        return sorted(reports, reverse=True)
