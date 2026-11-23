"""Completion audit independent of model inference and output format."""

from collections import Counter
from pathlib import Path

from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.TaskConfig.ConfigProfileService import atomic_write_json
from ModuleFolders.Service.Proofreader.RuleBasedChecker import RuleBasedChecker


class IncompleteExportError(ValueError):
    pass


def build_export_audit(project):
    counts = Counter({key: 0 for key in ("completed", "manual", "incomplete", "excluded", "blank", "checked_current_structure")})
    issues = []
    checker = RuleBasedChecker()
    completed = {TranslationStatus.TRANSLATED, TranslationStatus.POLISHED,
                 TranslationStatus.USER_PROOFREAD, TranslationStatus.AI_PROOFREAD}
    for path, cache_file in project.files.items():
        for item in cache_file.items:
            with item.atomic_scope():
                status, source = item.translation_status, item.source_text
                target = item.polished_text or item.translated_text
                if status == TranslationStatus.EXCLUDED:
                    category = "excluded"
                elif not source.strip():
                    category = "blank"
                elif status not in completed or not target.strip():
                    category = "incomplete"
                elif status == TranslationStatus.USER_PROOFREAD or item.extra.get("proofread_manual_edit"):
                    category = "manual"
                else:
                    category = "completed"
                counts[category] += 1
                if category == "incomplete":
                    issues.append({"file_path": path, "text_index": item.text_index,
                                   "kind": "incomplete", "falls_back_to_source": not bool(target)})
                elif category in {"completed", "manual"}:
                    findings = checker.check(source, target)
                    # Only high severity structural checks block strict export.
                    for finding in findings:
                        issues.append({"file_path": path, "text_index": item.text_index,
                                       "kind": "rule", "rule": finding.rule_name,
                                       "severity": finding.severity})
                    counts["checked_current_structure"] += 1
    blockers = sum(issue["kind"] == "incomplete" or issue.get("severity") == "high" for issue in issues)
    total = sum(counts[key] for key in ("completed", "manual", "incomplete", "excluded", "blank"))
    return {"version": 1, "project_id": project.project_id, "total_items": total, "counts": dict(counts),
            "historical_semantic_checks": "unknown", "blocking_issues": blockers, "issues": issues}


def write_export_audit(report, output_path):
    directory = Path(output_path) / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "export-completion.json"
    atomic_write_json(str(destination), report)
    return destination
