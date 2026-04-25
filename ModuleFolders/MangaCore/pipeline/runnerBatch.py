from __future__ import annotations

from dataclasses import dataclass, field

from ModuleFolders.MangaCore.export.packageExporter import PackageExportResult, PackageExporter
from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.runnerPage import MangaPageRunner
from ModuleFolders.MangaCore.project.session import MangaProjectSession


@dataclass(slots=True)
class MangaBatchRunResult:
    session: MangaProjectSession
    exports: PackageExportResult
    warnings: list[str] = field(default_factory=list)


class MangaBatchRunner:
    def __init__(self, logger=None) -> None:
        self.logger = logger or print

    def _log(self, message: str) -> None:
        self.logger(message)

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
        if page_ids:
            self._log(f"[MangaCore] Running page pipeline on {len(page_ids)} page(s)...")
            page_job = MangaPageRunner(logger=self.logger).translate_selected_pages(
                session,
                page_ids=page_ids,
                generate_text_blocks=True,
                auto_inpaint=True,
                auto_render=False,
            )
            self._log(f"[MangaCore] Page pipeline result: {page_job.status} | {page_job.message}")
        exports = PackageExporter().export(session)
        for key, path in exports.exported_paths.items():
            self._log(f"[MangaCore] Exported {key}: {path}")
        warnings = list(exports.warnings)
        if warnings:
            for warning in warnings:
                self._log(f"[MangaCore][WARN] {warning}")
        return MangaBatchRunResult(session=session, exports=exports, warnings=warnings)
