"""Editor and legacy proofread use cases reusing cache and report services."""
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import os
import re
import tempfile
import uuid

from ModuleFolders.Infrastructure.Cache.CacheManager import CacheManager
from ModuleFolders.Infrastructure.Cache.CacheItem import TranslationStatus
from ModuleFolders.Infrastructure.Cache.CachePersistence import cache_write_transaction
from ModuleFolders.Service.Proofreader.ProofreadReport import (
    ProofreadReport, ProofreadReportItem, apply_report_correction, correction_target_field,
)
from ModuleFolders.Service.Proofreader.ProofreadSuggestion import find_cache_item
from .cache_editing import read_snapshot, cache_path, cache_revision
from .jobs import CancelledJob


def statistics(output_path, cache_variant="main"):
    project, revision = read_snapshot(output_path, cache_variant)
    cache = CacheManager(subscribe_events=False)
    cache.load_from_project(project)
    return {
        "project_id": project.project_id, "project_name": project.project_name,
        "revision": revision, "total_items": cache.get_item_count(),
        "status_counts": dict(Counter(str(item.translation_status) for item in project.items_iter())),
        "hierarchy": cache.get_file_hierarchy(), "cache_variant": cache_variant,
    }


def item_record(project, revision, path, item, cache_variant="main"):
    return {
        "project_id": project.project_id, "revision": revision, "file_path": path,
        "text_index": item.text_index, "source_text": item.source_text,
        "translated_text": item.translated_text or "", "polished_text": item.polished_text or "",
        "translation_status": item.translation_status, "cache_variant": cache_variant,
    }


def read_item(output_path, file_path, text_index, cache_variant="main"):
    project, revision = read_snapshot(output_path, cache_variant)
    item = find_cache_item(project, file_path, text_index)
    if item is None:
        raise KeyError("Cache item not found")
    return item_record(project, revision, file_path, item, cache_variant)


def search(output_path, query, scope, regex, flagged, offset, limit, cache_variant="main"):
    if regex:
        re.compile(query)
    project, revision = read_snapshot(output_path, cache_variant)
    cache = CacheManager(subscribe_events=False)
    cache.load_from_project(project)
    results = cache.search_items(query, scope, regex, flagged)
    return {"items": [item_record(project, revision, path, item, cache_variant) for path, _, item in results[offset:offset + limit]],
            "total": len(results), "offset": offset, "limit": limit}


def list_items(output_path, file_path, offset, limit, cache_variant="main"):
    project, revision = read_snapshot(output_path, cache_variant)
    selected = [(path, item) for path, file in project.files.items() if file_path is None or path == file_path
                for item in file.items]
    return {"items": [item_record(project, revision, path, item, cache_variant) for path, item in selected[offset:offset + limit]],
            "total": len(selected), "offset": offset, "limit": limit}


def list_variants(output_path):
    rows = []
    for variant in ("main", "proofread"):
        path = cache_path(output_path, variant)
        if not path.is_file() or path.is_symlink():
            continue
        rows.append({"variant": variant, "path": str(path), "revision": cache_revision(output_path, variant), "size": path.stat().st_size})
    return {"variants": rows}


def discover_projects(roots):
    projects, errors, seen = [], [], set()
    for value in roots:
        root = Path(value).expanduser().resolve()
        try:
            if not root.is_dir():
                raise FileNotFoundError()
            candidates = [root] + [path for path in root.iterdir() if path.is_dir() and not path.is_symlink()]
            for path in candidates:
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                variants = list_variants(path)["variants"]
                if variants:
                    projects.append({"project_path": key, "variants": variants})
        except OSError:
            errors.append({"path": str(root), "error": "Directory cannot be scanned"})
    return {"projects": projects, "errors": errors}


def apply_edits(cache, edits):
    selected = []
    identities = set()
    for edit in edits:
        identity = (edit.file_path, edit.text_index, edit.field)
        if identity in identities:
            raise ValueError("Duplicate item edit")
        identities.add(identity)
        item = find_cache_item(cache.project, edit.file_path, edit.text_index)
        if item is None:
            raise KeyError("Cache item not found")
        selected.append((edit, item))
    for edit, item in selected:
        if edit.text is not None:
            cache.update_item_text(edit.file_path, edit.text_index, edit.field, edit.text)
            if edit.field != "source_text" and edit.text.strip() and edit.status is None:
                item.translation_status = TranslationStatus.USER_PROOFREAD
        if edit.status is not None:
            item.translation_status = edit.status
    return len(selected)


def replace_items(cache, request):
    pattern = re.compile(request.query) if request.regex else None
    selected = []
    for path, file in cache.project.files.items():
        if request.file_paths and path not in request.file_paths:
            continue
        for item in file.items:
            previous = getattr(item, request.field) or ""
            changed = pattern.sub(request.replacement, previous) if pattern else previous.replace(request.query, request.replacement)
            if previous != changed:
                if request.field == "source_text" and not changed.strip():
                    raise ValueError("Replacement cannot empty source text")
                selected.append((path, item.text_index, changed))
    if not request.preview:
        for path, index, text in selected:
            cache.update_item_text(path, index, request.field, text)
            if request.field != "source_text" and text.strip():
                find_cache_item(cache.project, path, index).translation_status = TranslationStatus.USER_PROOFREAD
    return len(selected)


def analyze_terms(request, config):
    from ModuleFolders.UserInterface.Editor.GlossaryHighlighter import GlossaryHighlighter
    glossary = request.glossary if request.glossary is not None else config.get("prompt_dictionary_data", [])
    if any(not isinstance(item.get(key, ""), str) for item in glossary for key in ("src", "dst")):
        raise ValueError("Glossary source and translation must be strings")
    highlighter = GlossaryHighlighter(glossary)
    return {
        "analysis": highlighter.analyze_text_terms(request.source_text, request.translation),
        "suggestions": highlighter.get_term_suggestions(request.prefix, request.limit),
    }


def report_path(output_path, filename):
    root = Path(output_path) / "proofread"
    if not filename or Path(filename).name != filename or "\\" in filename:
        raise ValueError("Invalid proofread report filename")
    candidate = root / filename
    if candidate.suffix != ".json" or "_ai_proofread_" not in candidate.name:
        raise ValueError("Not a legacy proofread report")
    if root.is_symlink() or candidate.is_symlink() or candidate.resolve().parent != root.resolve():
        raise ValueError("Report must be inside the project's proofread directory")
    if not candidate.is_file():
        raise FileNotFoundError("Proofread report not found")
    return candidate


def list_reports(output_path):
    result = []
    for name in ProofreadReport.list_reports(output_path):
        try:
            path = report_path(output_path, Path(name).name)
            result.append({"name": path.name, "size": path.stat().st_size})
        except (ValueError, FileNotFoundError):
            continue
    return {"reports": result}


def check_project(output_path, request, config, cancelled):
    from ModuleFolders.Service.Proofreader import RuleBasedChecker

    project, revision = read_snapshot(output_path, request.cache_variant)
    checker = RuleBasedChecker()
    rows, report_rows = [], {}
    for path, file in project.files.items():
        for item in file.items:
            if item.translation_status not in {TranslationStatus.TRANSLATED, TranslationStatus.POLISHED}:
                continue
            field = "polished_text" if item.translation_status == TranslationStatus.POLISHED and item.polished_text else "translated_text"
            target = getattr(item, field)
            if not item.source_text or not target:
                continue
            row = {"index": len(rows), "source": item.source_text, "translation": target,
                   "file_path": path, "text_index": item.text_index, "target_field": field}
            rows.append(row)
            issues = checker.check(item.source_text, target)
            if issues:
                report_rows[row["index"]] = _report_item(row, revision, rules=issues)
            if cancelled.is_set():
                raise CancelledJob()
    if request.mode == "rules_and_ai":
        _check_ai(rows, report_rows, request, config, revision, cancelled)
    if cancelled.is_set():
        raise CancelledJob()
    report = ProofreadReport(source_file=f"{project.project_id}-{uuid.uuid4().hex[:12]}", model=str(config.get("model", "")))
    for index in sorted(report_rows):
        report.add_item(report_rows[index])
    report.finalize(sum(len(file.items) for file in project.files.values()), len(rows))
    if (Path(output_path) / "proofread").is_symlink():
        raise ValueError("Proofread directory cannot be a symbolic link")
    path = report.save(output_path)
    from .jobs import CommittedResult
    return CommittedResult({"report_file": Path(path).name, "project_id": project.project_id,
                            "revision": revision, "cache_variant": request.cache_variant, "report": report.to_dict()})


def _report_item(row, revision, *, rules=()):
    return ProofreadReportItem(
        index=row["index"], source_text=row["source"], translated_text=row["translation"],
        ai_check={"file_path": row["file_path"], "text_index": row["text_index"],
                  "target_field": row["target_field"], "cache_revision": revision},
        rule_check={"has_issues": bool(rules), "issues": [asdict(issue) for issue in rules]},
    )


def _check_ai(rows, report_rows, request, config, revision, cancelled):
    from ModuleFolders.Base.Base import Base
    from ModuleFolders.Infrastructure.TaskConfig.TaskConfig import TaskConfig
    from ModuleFolders.Infrastructure.TaskConfig.TaskType import TaskType
    from ModuleFolders.Infrastructure.RequestLimiter.RequestLimiter import RequestLimiter
    from ModuleFolders.Service.Proofreader.ProofreaderTask import ProofreaderTask

    task_config = TaskConfig()
    task_config.load_config_from_dict(config)
    task_config.prepare_for_translation(TaskType.TRANSLATION)
    limiter = RequestLimiter()
    limiter.set_limit(config.get("tpm_limit", 100000), config.get("rpm_limit", 60))
    with Base.independent_request_scope(cancelled):
        for start in range(0, len(rows), request.batch_size):
            if cancelled.is_set():
                raise CancelledJob()
            chunk = rows[start:start + request.batch_size]
            task = ProofreaderTask(task_config, limiter)
            task.set_items(chunk)
            task.set_previous_items(rows[max(0, start - request.context_lines):start])
            task.prepare()
            result = task.run()
            if cancelled.is_set():
                raise CancelledJob()
            if not result or result.get("skip", True):
                raise RuntimeError("AI proofread request did not complete")
            for row in chunk:
                index = row["index"]
                issues = result.get("issues", {}).get(index, [])
                corrected = result.get("corrections", {}).get(index, "")
                if not issues and not corrected:
                    continue
                entry = report_rows.setdefault(index, _report_item(row, revision))
                entry.ai_check.update(has_issues=bool(issues), issues=issues, corrected_translation=corrected)


def apply_legacy_report(cache, output_path, request):
    import msgspec

    report = ProofreadReport.load(report_path(output_path, request.report_file))
    applied, conflicts = 0, []
    for entry in report.items:
        correction = entry.ai_check.get("corrected_translation")
        issues = entry.ai_check.get("issues", [])
        if not correction or not any(issue.get("severity", "low") in request.severities for issue in issues):
            continue
        path = entry.ai_check.get("file_path")
        index = entry.ai_check.get("text_index", entry.index)
        matches = [(name, item) for name, file in cache.project.files.items() for item in file.items
                   if (path is None or name == path) and item.text_index == index
                   and item.source_text == entry.source_text]
        if len(matches) != 1:
            conflicts.append({"index": entry.index, "reason": "Cache item is missing or ambiguous"})
            continue
        _, item = matches[0]
        field = correction_target_field(entry, item)
        if getattr(item, field) != entry.translated_text:
            conflicts.append({"index": entry.index, "reason": "Translation changed since the report"})
            continue
        apply_report_correction(entry, item, correction)
        applied += 1
    destination = Path(output_path) / "cache/AinieeCacheData_proofread.json"
    with cache_write_transaction(destination):
        if destination.exists() and not request.overwrite:
            raise FileExistsError("Proofread cache exists; confirm overwrite explicitly")
        if destination.is_symlink():
            raise ValueError("Proofread cache cannot be a symbolic link")
        fd, staging = tempfile.mkstemp(prefix=".proofread-", dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(msgspec.json.encode(cache.project))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staging, destination)
        finally:
            Path(staging).unlink(missing_ok=True)
    return {"changed": applied, "output_path": str(destination), "conflicts": conflicts}
