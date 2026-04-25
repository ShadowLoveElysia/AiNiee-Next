from __future__ import annotations

from ModuleFolders.MangaCore.io.persistence import MangaProjectPersistence
from ModuleFolders.MangaCore.pipeline.engines.detect import DetectEngine, DetectResult
from ModuleFolders.MangaCore.pipeline.engines.inpaint import InpaintEngine, InpaintResult
from ModuleFolders.MangaCore.pipeline.engines.ocr import OcrEngine
from ModuleFolders.MangaCore.pipeline.engines.translate import TranslateEngine, TranslationBatchResult
from ModuleFolders.MangaCore.pipeline.progress import JobRegistry, PipelineJob
from ModuleFolders.MangaCore.project.page import MangaPage
from ModuleFolders.MangaCore.project.session import MangaProjectSession
from ModuleFolders.MangaCore.render.bubbleAssign import BubbleAssignment, TextSeed, assign_bubbles
from ModuleFolders.MangaCore.render.painter import MangaRenderer
from ModuleFolders.MangaCore.render.planner import plan_text_blocks


class MangaPageRunner:
    def __init__(
        self,
        logger=None,
        ocr_engine: OcrEngine | None = None,
        detect_engine: DetectEngine | None = None,
        translate_engine: TranslateEngine | None = None,
        inpaint_engine: InpaintEngine | None = None,
        renderer: MangaRenderer | None = None,
    ) -> None:
        self.logger = logger or (lambda *_args, **_kwargs: None)
        self.ocr_engine = ocr_engine or OcrEngine()
        self.detect_engine = detect_engine or DetectEngine()
        self.translate_engine = translate_engine or TranslateEngine(logger=self.logger)
        self.inpaint_engine = inpaint_engine or InpaintEngine()
        self.renderer = renderer or MangaRenderer()

    def translate_current_page(
        self,
        session: MangaProjectSession,
        page_id: str,
        save_after_run: bool = True,
        refresh_render: bool = True,
    ) -> PipelineJob:
        return self._process_current_page(
            session,
            page_id=page_id,
            save_after_run=save_after_run,
            refresh_render=refresh_render,
            run_translation=True,
        )

    def ocr_current_page(
        self,
        session: MangaProjectSession,
        page_id: str,
        save_after_run: bool = True,
    ) -> PipelineJob:
        return self._process_current_page(
            session,
            page_id=page_id,
            save_after_run=save_after_run,
            refresh_render=False,
            run_translation=False,
        )

    def detect_current_page(
        self,
        session: MangaProjectSession,
        page_id: str,
        save_after_run: bool = True,
    ) -> PipelineJob:
        page = session.get_page(page_id)
        session.scene.current_page_id = page_id
        self._configure_engines(session)
        job = JobRegistry.create(
            project_id=session.manifest.project_id,
            page_id=page_id,
            stage="page_detecting",
            status="running",
            progress=10,
            message="Refreshing cleanup masks for the current page.",
        )

        try:
            seeds = self.ocr_engine.run(session.project_path / page.layers.source)
            assignments = assign_bubbles(seeds, page.width, page.height)
            self._write_seed_artifacts(session, page, seeds, assignments)
            detect_result = self._run_detect_stage(session, page, seeds=seeds, assignments=assignments)
            page.last_pipeline_stage = "page_detecting"
            if save_after_run:
                MangaProjectPersistence.save_session(session)
            updated = JobRegistry.update(
                job.job_id,
                stage="page_completed",
                status="completed",
                progress=100,
                message=(
                    f"Generated {len(detect_result.text_regions)} text region mask(s) and "
                    f"{len(detect_result.bubble_regions)} bubble mask(s)."
                ),
            )
            return updated or job
        except Exception as exc:
            updated = JobRegistry.update(
                job.job_id,
                stage="page_failed",
                status="failed",
                progress=0,
                message=f"Page detect failed: {exc}",
            )
            return updated or job

    def inpaint_current_page(
        self,
        session: MangaProjectSession,
        page_id: str,
        save_after_run: bool = True,
    ) -> PipelineJob:
        page = session.get_page(page_id)
        session.scene.current_page_id = page_id
        self._configure_engines(session)
        job = JobRegistry.create(
            project_id=session.manifest.project_id,
            page_id=page_id,
            stage="page_inpainting",
            status="running",
            progress=10,
            message="Refreshing cleanup masks and rebuilding the inpainted base layer.",
        )

        try:
            seeds = self.ocr_engine.run(session.project_path / page.layers.source)
            assignments = assign_bubbles(seeds, page.width, page.height)
            self._write_seed_artifacts(session, page, seeds, assignments)
            self._run_detect_stage(session, page, seeds=seeds, assignments=assignments)
            inpaint_result = self._run_inpaint_stage(session, page)
            page.last_pipeline_stage = "page_inpainting"
            if save_after_run:
                MangaProjectPersistence.save_session(session)
            updated = JobRegistry.update(
                job.job_id,
                stage="page_completed",
                status="completed",
                progress=100,
                message=self._build_inpaint_message(inpaint_result),
            )
            return updated or job
        except Exception as exc:
            updated = JobRegistry.update(
                job.job_id,
                stage="page_failed",
                status="failed",
                progress=0,
                message=f"Page inpaint failed: {exc}",
            )
            return updated or job

    def translate_selected_pages(
        self,
        session: MangaProjectSession,
        page_ids: list[str],
        generate_text_blocks: bool = True,
        auto_inpaint: bool = False,
        auto_render: bool = False,
    ) -> PipelineJob:
        return self._process_selected_pages(
            session,
            page_ids=page_ids,
            generate_text_blocks=generate_text_blocks,
            run_translation=True,
            auto_inpaint=auto_inpaint,
            auto_render=auto_render,
        )

    def plan_selected_pages(
        self,
        session: MangaProjectSession,
        page_ids: list[str],
        generate_text_blocks: bool = True,
    ) -> PipelineJob:
        return self._process_selected_pages(
            session,
            page_ids=page_ids,
            generate_text_blocks=generate_text_blocks,
            run_translation=False,
            auto_inpaint=False,
            auto_render=False,
        )

    def _configure_engines(self, session: MangaProjectSession) -> None:
        snapshot = session.config_snapshot if isinstance(getattr(session, "config_snapshot", None), dict) else {}
        if hasattr(self.ocr_engine, "configure"):
            self.ocr_engine.configure(snapshot.get("manga_ocr_engine"))
        if hasattr(self.detect_engine, "configure"):
            self.detect_engine.configure(
                detector_id=snapshot.get("manga_detect_engine"),
                segmenter_id=snapshot.get("manga_segment_engine"),
            )
        if hasattr(self.inpaint_engine, "configure"):
            self.inpaint_engine.configure(snapshot.get("manga_inpaint_engine"))

    def _process_current_page(
        self,
        session: MangaProjectSession,
        page_id: str,
        save_after_run: bool,
        refresh_render: bool,
        run_translation: bool,
    ) -> PipelineJob:
        job = JobRegistry.create(
            project_id=session.manifest.project_id,
            page_id=page_id,
            stage="page_ocr",
            status="running",
            progress=5,
            message="Running OCR and typesetting planner for the current page.",
        )
        page = session.get_page(page_id)
        session.scene.current_page_id = page_id
        self._configure_engines(session)

        try:
            JobRegistry.update(
                job.job_id,
                stage="page_ocr",
                progress=20,
                message="OCR started for the current page.",
            )
            seeds = self.ocr_engine.run(session.project_path / page.layers.source)
            JobRegistry.update(
                job.job_id,
                stage="page_typesetting_planning",
                progress=50,
                message=f"OCR completed with {len(seeds)} text seed(s); generating editable blocks.",
            )
            assignments = assign_bubbles(seeds, page.width, page.height)
            blocks = plan_text_blocks(page.page_id, seeds, assignments)

            page.text_blocks = blocks
            page.status = "needs_review" if blocks else "failed"
            page.last_pipeline_stage = "page_typesetting_planning" if blocks else "page_failed"
            self._write_seed_artifacts(session, page, seeds, assignments)

            detect_result = DetectResult(ok=True)
            translation_result = TranslationBatchResult(ok=True)
            inpaint_result = InpaintResult(ok=True)
            translated_blocks = 0

            if run_translation:
                JobRegistry.update(
                    job.job_id,
                    stage="page_detecting",
                    progress=65,
                    message="Generating cleanup masks for the current page.",
                )
                detect_result = self._run_detect_stage(session, page, seeds=seeds, assignments=assignments)
                page.last_pipeline_stage = "page_detecting"

            if run_translation and blocks:
                JobRegistry.update(
                    job.job_id,
                    stage="page_translating",
                    progress=78,
                    message=f"Translating {len(blocks)} planned block(s) for the current page.",
                )
                translation_result = self.translate_engine.translate_blocks(
                    session,
                    blocks,
                    source_lang=session.manifest.source_lang,
                    target_lang=session.manifest.target_lang,
                )
                translated_blocks = self._apply_translation_result(page, translation_result)
                MangaProjectPersistence.write_page_artifact(
                    session,
                    page,
                    "translationResults.json",
                    self._build_translation_artifact(page, translation_result),
                )
                page.last_pipeline_stage = "page_translating"
                page.status = "translated" if translated_blocks == len(blocks) and len(blocks) > 0 else "needs_review"

            if refresh_render and run_translation:
                JobRegistry.update(
                    job.job_id,
                    stage="page_inpainting",
                    progress=90,
                    message="Refreshing the inpainted base layer before preview render.",
                )
                inpaint_result = self._run_inpaint_stage(session, page)
                page.last_pipeline_stage = "page_inpainting"

            if refresh_render:
                JobRegistry.update(
                    job.job_id,
                    stage="page_rendering",
                    progress=95,
                    message="Refreshing rendered page preview from current block data.",
                )
                self.renderer.render_page(session, page)
                page.last_pipeline_stage = "page_rendering"

            if save_after_run or refresh_render:
                MangaProjectPersistence.save_session(session)

            message = self._build_page_message(
                seed_count=len(seeds),
                block_count=len(blocks),
                translated_blocks=translated_blocks,
                run_translation=run_translation,
                translation_result=translation_result,
                detect_result=detect_result,
                inpaint_result=inpaint_result,
                refresh_render=refresh_render,
            )
            updated = JobRegistry.update(
                job.job_id,
                stage="page_completed" if blocks else "page_failed",
                status="completed" if blocks else "failed",
                progress=100 if blocks else 0,
                message=message,
            )
            return updated or job
        except Exception as exc:
            updated = JobRegistry.update(
                job.job_id,
                stage="page_failed",
                status="failed",
                progress=0,
                message=f"Page pipeline failed: {exc}",
            )
            return updated or job

    def _process_selected_pages(
        self,
        session: MangaProjectSession,
        page_ids: list[str],
        generate_text_blocks: bool,
        run_translation: bool,
        auto_inpaint: bool,
        auto_render: bool,
    ) -> PipelineJob:
        job = JobRegistry.create(
            project_id=session.manifest.project_id,
            stage="batch_ocr",
            status="running",
            progress=0,
            message=f"Running OCR/typesetting planner for {len(page_ids)} page(s).",
        )
        self._configure_engines(session)
        processed = 0
        total_blocks = 0
        total_translated_blocks = 0
        translation_warnings = 0
        inpainted_pages = 0
        try:
            for page_id in page_ids:
                page = session.get_page(page_id)
                session.scene.current_page_id = page_id
                JobRegistry.update(
                    job.job_id,
                    stage="batch_ocr",
                    progress=int(processed * 100 / max(1, len(page_ids))),
                    message=f"OCR {processed + 1}/{len(page_ids)} page(s).",
                )
                seeds = self.ocr_engine.run(session.project_path / page.layers.source)
                JobRegistry.update(
                    job.job_id,
                    stage="batch_typesetting_planning",
                    progress=int((processed + 0.4) * 100 / max(1, len(page_ids))),
                    message=f"Planning editable blocks for {processed + 1}/{len(page_ids)} page(s).",
                )
                assignments = assign_bubbles(seeds, page.width, page.height)
                blocks = plan_text_blocks(page.page_id, seeds, assignments) if generate_text_blocks else []
                page.text_blocks = blocks
                page.status = "needs_review" if blocks else "failed"
                page.last_pipeline_stage = "batch_typesetting_planning" if blocks else "batch_failed"
                total_blocks += len(blocks)
                self._write_seed_artifacts(session, page, seeds, assignments)

                if run_translation:
                    JobRegistry.update(
                        job.job_id,
                        stage="batch_detecting",
                        progress=int((processed + 0.55) * 100 / max(1, len(page_ids))),
                        message=f"Generating cleanup masks for page {processed + 1}/{len(page_ids)}.",
                    )
                    self._run_detect_stage(session, page, seeds=seeds, assignments=assignments)
                    page.last_pipeline_stage = "batch_detecting"

                translation_result = TranslationBatchResult(ok=True)
                translated_blocks = 0
                if run_translation and blocks:
                    JobRegistry.update(
                        job.job_id,
                        stage="batch_translating",
                        progress=int((processed + 0.75) * 100 / max(1, len(page_ids))),
                        message=f"Translating planned blocks for page {processed + 1}/{len(page_ids)}.",
                    )
                    translation_result = self.translate_engine.translate_blocks(
                        session,
                        blocks,
                        source_lang=session.manifest.source_lang,
                        target_lang=session.manifest.target_lang,
                    )
                    translated_blocks = self._apply_translation_result(page, translation_result)
                    total_translated_blocks += translated_blocks
                    if not translation_result.ok:
                        translation_warnings += 1
                    MangaProjectPersistence.write_page_artifact(
                        session,
                        page,
                        "translationResults.json",
                        self._build_translation_artifact(page, translation_result),
                    )
                    page.last_pipeline_stage = "batch_translating"
                    page.status = "translated" if translated_blocks == len(blocks) and len(blocks) > 0 else "needs_review"

                if run_translation and auto_inpaint:
                    JobRegistry.update(
                        job.job_id,
                        stage="batch_inpainting",
                        progress=int((processed + 0.88) * 100 / max(1, len(page_ids))),
                        message=f"Refreshing inpainted base for page {processed + 1}/{len(page_ids)}.",
                    )
                    inpaint_result = self._run_inpaint_stage(session, page)
                    if inpaint_result.mask_pixels > 0:
                        inpainted_pages += 1
                    page.last_pipeline_stage = "batch_inpainting"

                if auto_render:
                    JobRegistry.update(
                        job.job_id,
                        stage="batch_rendering",
                        progress=int((processed + 0.95) * 100 / max(1, len(page_ids))),
                        message=f"Refreshing rendered page {processed + 1}/{len(page_ids)}.",
                    )
                    self.renderer.render_page(session, page)
                    page.last_pipeline_stage = "batch_rendering"

                processed += 1
                JobRegistry.update(
                    job.job_id,
                    progress=int(processed * 100 / max(1, len(page_ids))),
                    stage="batch_translating" if run_translation else "batch_typesetting_planning",
                    message=self._build_batch_progress_message(
                        processed=processed,
                        total=len(page_ids),
                        total_blocks=total_blocks,
                        total_translated_blocks=total_translated_blocks,
                        run_translation=run_translation,
                        translation_warnings=translation_warnings,
                        auto_inpaint=auto_inpaint,
                        inpainted_pages=inpainted_pages,
                    ),
                )

            MangaProjectPersistence.save_session(session)
            updated = JobRegistry.update(
                job.job_id,
                stage="batch_completed",
                status="completed",
                progress=100,
                message=self._build_batch_completion_message(
                    page_count=len(page_ids),
                    total_blocks=total_blocks,
                    total_translated_blocks=total_translated_blocks,
                    run_translation=run_translation,
                    translation_warnings=translation_warnings,
                    auto_inpaint=auto_inpaint,
                    inpainted_pages=inpainted_pages,
                ),
            )
            return updated or job
        except Exception as exc:
            updated = JobRegistry.update(
                job.job_id,
                stage="batch_failed",
                status="failed",
                progress=0,
                message=f"Batch page pipeline failed: {exc}",
            )
            return updated or job

    def render_current_page(
        self,
        session: MangaProjectSession,
        page_id: str,
        save_after_run: bool = True,
    ) -> PipelineJob:
        job = JobRegistry.create(
            project_id=session.manifest.project_id,
            page_id=page_id,
            stage="page_rendering",
            status="running",
            progress=20,
            message="Rendering the current page from MangaProject blocks.",
        )
        page = session.get_page(page_id)
        session.scene.current_page_id = page_id

        try:
            self.renderer.render_page(session, page)
            page.last_pipeline_stage = "page_rendering"
            if save_after_run:
                MangaProjectPersistence.save_session(session)
            updated = JobRegistry.update(
                job.job_id,
                stage="page_completed",
                status="completed",
                progress=100,
                message="Rendered the current page preview successfully.",
            )
            return updated or job
        except Exception as exc:
            updated = JobRegistry.update(
                job.job_id,
                stage="page_failed",
                status="failed",
                progress=0,
                message=f"Page render failed: {exc}",
            )
            return updated or job

    def _write_seed_artifacts(
        self,
        session: MangaProjectSession,
        page: MangaPage,
        seeds: list[TextSeed],
        assignments: list[BubbleAssignment],
    ) -> None:
        MangaProjectPersistence.write_page_artifact(session, page, "ocrSeeds.json", [seed.to_dict() for seed in seeds])
        MangaProjectPersistence.write_page_artifact(
            session,
            page,
            "bubbleAssignments.json",
            [assignment.to_dict() for assignment in assignments],
        )

    def _run_detect_stage(
        self,
        session: MangaProjectSession,
        page: MangaPage,
        *,
        seeds: list[TextSeed],
        assignments: list[BubbleAssignment],
    ) -> DetectResult:
        result = self.detect_engine.run(
            session.project_path / page.layers.source,
            page.width,
            page.height,
            seeds=seeds,
            assignments=assignments,
            blocks=page.text_blocks,
        )
        self.detect_engine.write_masks(
            result,
            size=(page.width, page.height),
            segment_path=session.project_path / page.masks.segment,
            bubble_path=session.project_path / page.masks.bubble,
        )
        MangaProjectPersistence.write_page_artifact(session, page, "detectResults.json", result.to_dict())
        return result

    def _run_inpaint_stage(
        self,
        session: MangaProjectSession,
        page: MangaPage,
    ) -> InpaintResult:
        result = self.inpaint_engine.run(
            source_path=session.project_path / page.layers.source,
            segment_mask_path=session.project_path / page.masks.segment,
            brush_mask_path=session.project_path / page.masks.brush,
            output_path=session.project_path / page.layers.inpainted,
        )
        MangaProjectPersistence.write_page_artifact(session, page, "inpaintResults.json", result.to_dict())
        return result

    @staticmethod
    def _apply_translation_result(page: MangaPage, translation_result: TranslationBatchResult) -> int:
        translated_blocks = 0
        for block in page.text_blocks:
            translated_text = translation_result.translations.get(block.block_id, "")
            if translated_text:
                block.translation = translated_text
                block.flags = [flag for flag in block.flags if flag != "needs_translation"]
                if "translated" not in block.flags:
                    block.flags.append("translated")
                translated_blocks += 1
            else:
                block.flags = [flag for flag in block.flags if flag != "translated"]
                if "needs_translation" not in block.flags:
                    block.flags.append("needs_translation")
        return translated_blocks

    @staticmethod
    def _build_translation_artifact(page: MangaPage, translation_result: TranslationBatchResult) -> dict[str, object]:
        return {
            "ok": translation_result.ok,
            "prompt_tokens": translation_result.prompt_tokens,
            "completion_tokens": translation_result.completion_tokens,
            "error_message": translation_result.error_message,
            "missing_block_ids": list(translation_result.missing_block_ids),
            "translations": [
                {
                    "block_id": block.block_id,
                    "source_text": block.source_text,
                    "translation": block.translation,
                }
                for block in page.text_blocks
            ],
        }

    @staticmethod
    def _build_page_message(
        *,
        seed_count: int,
        block_count: int,
        translated_blocks: int,
        run_translation: bool,
        translation_result: TranslationBatchResult,
        detect_result: DetectResult,
        inpaint_result: InpaintResult,
        refresh_render: bool,
    ) -> str:
        if block_count == 0:
            return "No OCR text seeds were found on the page."
        if not run_translation:
            return f"Generated {block_count} editable block(s) from {seed_count} OCR seed(s)."

        parts = [
            f"Generated {block_count} editable block(s)",
            f"prepared {len(detect_result.text_regions)} cleanup region(s)",
        ]
        if translation_result.ok:
            parts.append(f"translated {translated_blocks} block(s)")
        elif translated_blocks > 0:
            parts.append(f"translated {translated_blocks}/{block_count} block(s)")
            parts.append(f"translation warning: {translation_result.error_message}")
        else:
            parts.append(f"translation failed: {translation_result.error_message}")

        if refresh_render:
            parts.append(f"inpainted {inpaint_result.mask_pixels} masked pixel(s)")

        return "; ".join(parts) + "."

    @staticmethod
    def _build_inpaint_message(inpaint_result: InpaintResult) -> str:
        if inpaint_result.mask_pixels == 0:
            return "Inpaint completed, but no cleanup mask pixels were active on the page."
        return (
            f"Refreshed the inpainted base layer using {inpaint_result.configured_engine_id} "
            f"({inpaint_result.runtime_engine_id}) over {inpaint_result.mask_pixels} masked pixel(s)."
        )

    @staticmethod
    def _build_batch_progress_message(
        *,
        processed: int,
        total: int,
        total_blocks: int,
        total_translated_blocks: int,
        run_translation: bool,
        translation_warnings: int,
        auto_inpaint: bool,
        inpainted_pages: int,
    ) -> str:
        if not run_translation:
            return f"Processed {processed}/{total} page(s), generated {total_blocks} block(s)."
        warning_suffix = f" {translation_warnings} page(s) have translation warnings." if translation_warnings else ""
        inpaint_suffix = f" Inpaint refreshed for {inpainted_pages} page(s)." if auto_inpaint else ""
        return (
            f"Processed {processed}/{total} page(s), generated {total_blocks} block(s), "
            f"translated {total_translated_blocks} block(s).{warning_suffix}{inpaint_suffix}"
        )

    @staticmethod
    def _build_batch_completion_message(
        *,
        page_count: int,
        total_blocks: int,
        total_translated_blocks: int,
        run_translation: bool,
        translation_warnings: int,
        auto_inpaint: bool,
        inpainted_pages: int,
    ) -> str:
        if not run_translation:
            return f"Completed {page_count} page(s); generated {total_blocks} editable block(s)."
        warning_suffix = f" {translation_warnings} page(s) need review due to translation warnings." if translation_warnings else ""
        inpaint_suffix = f" Inpaint refreshed for {inpainted_pages} page(s)." if auto_inpaint else ""
        return (
            f"Completed {page_count} page(s); generated {total_blocks} editable block(s) and "
            f"translated {total_translated_blocks} block(s).{warning_suffix}{inpaint_suffix}"
        )
