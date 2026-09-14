"""非交互校对：复用校对任务，只生成报告，不自动改写译文。"""

import concurrent.futures
import json
import os

from ModuleFolders.Base.Base import Base
from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.RequestLimiter.RequestLimiter import RequestLimiter
from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
from ModuleFolders.Service.Proofreader.ProofreaderTask import ProofreaderTask
from ModuleFolders.Service.Proofreader.ProofreadReport import ProofreadReport, ProofreadReportItem


def run_automation_proofread(config: dict, output_path: str) -> str:
    cache_path = os.path.join(output_path, "cache", "AinieeCacheData.json")
    with open(cache_path, encoding="utf-8-sig") as reader:
        cache = json.load(reader)
    settings = TaskConfig()
    settings.load_config_from_dict(config)
    settings.prepare_for_translation(TaskType.TRANSLATION)
    limiter = RequestLimiter()
    limiter.set_limit(settings.tpm_limit, settings.rpm_limit, config.get("enable_rate_limit", False),
                      config.get("custom_rpm_limit", 0), config.get("custom_tpm_limit", 0))
    report = ProofreadReport(source_file=cache.get("project_id", "project"), model=settings.model)
    batch_size = int(config.get("proofread_batch_size", 20))
    context_lines = int(config.get("proofread_context_lines", 5))
    tasks = []
    checked = 0
    for file_path, file_info in cache.get("files", {}).items():
        raw = file_info.get("items", {})
        rows = raw.values() if isinstance(raw, dict) else raw
        items = []
        for row in rows:
            status = row.get("translation_status")
            if status not in (TranslationStatus.TRANSLATED, TranslationStatus.POLISHED):
                continue
            target = (row.get("polished_text") if status == TranslationStatus.POLISHED else "") or row.get("translated_text")
            if row.get("source_text") and target:
                items.append({"index": row["text_index"], "source": row["source_text"], "translation": target})
        checked += len(items)
        for start in range(0, len(items), batch_size):
            task = ProofreaderTask(settings, limiter)
            task.set_items(items[start:start + batch_size])
            task.set_previous_items(items[max(0, start - context_lines):start])
            task.prepare()
            tasks.append((file_path, task))
    if not tasks:
        raise ValueError("No translated content available for proofreading")
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=settings.actual_thread_counts) as executor:
        pending = {executor.submit(task.run): (path, task) for path, task in tasks}
        for future in concurrent.futures.as_completed(pending):
            if Base.work_status == Base.STATUS.STOPING:
                for other in pending:
                    other.cancel()
                raise RuntimeError("Proofreading stopped")
            path, task = pending[future]
            result = future.result()
            if not result or result.get("skip"):
                failures += 1
                continue
            by_id = {str(item["index"]): item for item in task.items}
            for index, issues in result.get("issues", {}).items():
                item = by_id.get(str(index))
                if item:
                    report.add_item(ProofreadReportItem(
                        index=item["index"], source_text=item["source"], translated_text=item["translation"],
                        ai_check={"has_issues": bool(issues), "issues": issues, "file_path": path,
                                  "corrected_translation": result.get("corrections", {}).get(index, "")},
                    ))
    report.finalize(checked, checked)
    path = report.save(output_path)
    if failures:
        raise RuntimeError(f"Proofreading failed for {failures} batches; partial report: {path}")
    return path
