from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.Base.Base import Base
from ModuleFolders.MangaCore.export.packageExporter import PackageExportResult, PackageExporter
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.progress import PipelineJob
from ModuleFolders.MangaCore.pipeline.runnerPage import MangaPageRunner
from ModuleFolders.MangaCore.project.session import MangaProjectSession


def _i18n_format(key: str, fallback: str, *args: object) -> str:
    template = fallback
    i18n = getattr(Base, "i18n", None)
    if i18n is not None and hasattr(i18n, "get"):
        value = i18n.get(key)
        if value and value != key:
            template = str(value)
    try:
        return template.format(*args)
    except Exception:
        result = template
        for arg in args:
            result = result.replace("{}", str(arg), 1)
        return result


@dataclass(slots=True)
class MangaBatchRunResult:
    session: MangaProjectSession
    exports: PackageExportResult
    page_job: PipelineJob | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if not self.exports.exported_paths:
            return False
        if self.page_job and self.page_job.status == "failed":
            return False
        if self.page_job and isinstance(self.page_job.result, dict):
            total_blocks = int(self.page_job.result.get("total_blocks") or 0)
            translated_blocks = int(self.page_job.result.get("total_translated_blocks") or 0)
            translation_warnings = int(self.page_job.result.get("translation_warnings") or 0)
            final_blocked_pages = int(self.page_job.result.get("final_blocked_pages") or 0)
            if total_blocks <= 0:
                return False
            if translation_warnings > 0:
                return False
            if translated_blocks < total_blocks:
                return False
            if final_blocked_pages > 0:
                return False
        return True


class MangaBatchRunner:
    def __init__(self, logger=None, progress_callback=None) -> None:
        self.logger = logger or print
        self.progress_callback = progress_callback

    def _log(self, message: str) -> None:
        self.logger(message)

    def _emit_progress(self, **payload: object) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(payload)
        except Exception:
            pass

    def run(
        self,
        *,
        input_path: str,
        output_path: str,
        config_snapshot: dict[str, object] | None = None,
        profile_name: str = "default",
        rules_profile_name: str = "default",
        source_lang: str = "ja",
        target_lang: str = "zh_cn",
    ) -> MangaBatchRunResult:
        self._log("[MangaCore] Preparing manga project structure...")
        self._emit_progress(
            input_path=input_path,
            total_pages=1,
            processed_pages=0,
            stage="preparing",
            message="Preparing manga project.",
        )
        session = MangaProjectPersistence.create_project_from_input(
            input_path=input_path,
            output_root=output_path,
            config_snapshot=config_snapshot,
            profile_name=profile_name,
            rules_profile_name=rules_profile_name,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self._log(f"[MangaCore] Project created at: {session.project_path}")
        page_ids = [page_ref.page_id for page_ref in session.scene.pages]
        page_job: PipelineJob | None = None
        warnings: list[str] = []
        self._emit_progress(
            input_path=input_path,
            total_pages=max(1, len(page_ids)),
            processed_pages=0,
            stage="project_ready",
            message=f"Project created with {len(page_ids)} page(s).",
        )
        if page_ids:
            self._log(f"[MangaCore] Running page pipeline on {len(page_ids)} page(s)...")
            page_job = MangaPageRunner(
                logger=self.logger,
                progress_callback=self.progress_callback,
            ).translate_selected_pages(
                session,
                page_ids=page_ids,
                generate_text_blocks=True,
                auto_inpaint=True,
                auto_render=True,
            )
            self._log(f"[MangaCore] Page pipeline result: {page_job.status} | {page_job.message}")
            if page_job.status == "failed":
                warnings.append(page_job.message or "MangaCore page pipeline failed.")
            if isinstance(page_job.result, dict):
                total_blocks = int(page_job.result.get("total_blocks") or 0)
                translated_blocks = int(page_job.result.get("total_translated_blocks") or 0)
                translation_warnings = int(page_job.result.get("translation_warnings") or 0)
                no_text_pages = int(page_job.result.get("no_text_pages") or 0)
                final_blocked_pages = int(page_job.result.get("final_blocked_pages") or 0)
                if total_blocks <= 0:
                    warnings.append("No OCR text blocks were generated; exported pages may match the source images.")
                elif translated_blocks < total_blocks:
                    warnings.append(f"Only translated {translated_blocks}/{total_blocks} text block(s).")
                if translation_warnings:
                    warnings.append(f"{translation_warnings} page(s) had translation warnings and need review.")
                if no_text_pages:
                    warnings.append(f"{no_text_pages} page(s) had no OCR text blocks.")
                if final_blocked_pages:
                    warnings.append(
                        _i18n_format(
                            "manga_notice_quality_gate_blocked_pages",
                            "Quality gates blocked automatic final output for {} page(s); those pages were kept as drafts.",
                            final_blocked_pages,
                        )
                    )
        self._emit_progress(
            input_path=input_path,
            total_pages=max(1, len(page_ids)),
            processed_pages=len(page_ids),
            stage="exporting",
            message="Exporting final pages and packages.",
        )
        exports = PackageExporter().export(session)
        for key, path in exports.exported_paths.items():
            self._log(f"[MangaCore] Exported {key}: {path}")
        warnings.extend(exports.warnings)
        if warnings:
            for warning in warnings:
                self._log(f"[MangaCore][WARN] {warning}")
        self._emit_progress(
            input_path=input_path,
            total_pages=max(1, len(page_ids)),
            processed_pages=len(page_ids),
            stage="completed",
            message="MangaCore batch completed.",
            translation_warnings=len(warnings),
        )
        return MangaBatchRunResult(session=session, exports=exports, page_job=page_job, warnings=warnings)
