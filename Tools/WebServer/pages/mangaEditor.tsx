import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';
import { MangaBlocksPanel } from '../components/manga/mangaBlocksPanel';
import { MangaCanvas } from '../components/manga/mangaCanvas';
import { MangaInspector } from '../components/manga/mangaInspector';
import { MangaLayersPanel } from '../components/manga/mangaLayersPanel';
import { MangaPageStrip } from '../components/manga/mangaPageStrip';
import { MangaStatusBar } from '../components/manga/mangaStatusBar';
import { MangaTopBar } from '../components/manga/mangaTopBar';
import { useI18n } from '../contexts/I18nContext';
import { MangaBlockDraft, MangaCanvasCommand, MangaCanvasPointer, MangaEngineCard, MangaLayerControls, MangaOverlayLayerKey, MangaViewMode, translateMangaEnum } from '../components/manga/shared';
import { DataService } from '../services/DataService';
import { MangaJob, MangaPageDetail, MangaProjectSummary, MangaRuntimeValidationResult, MangaSceneSummary } from '../types/manga';

type NoticeTone = 'info' | 'success' | 'warning' | 'error';

const getInitialProjectPath = () => {
  const hash = window.location.hash || '';
  const query = hash.includes('?') ? hash.split('?')[1] : '';
  return new URLSearchParams(query).get('project_path') || '';
};

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

const formatStageLabel = (value: string, t: (key: string) => string) => {
  const key = `manga_stage_${value}`;
  const translated = t(key);
  if (translated !== key) return translated;
  return value
    .split('_')
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
};

const ACTION_LABEL_KEYS: Record<string, string> = {
  'detect current page': 'manga_action_detect',
  'ocr current page': 'manga_action_ocr',
  'translate current page': 'manga_action_generate',
  'translate selected pages': 'manga_action_selected',
  'plan selected pages': 'manga_action_plan',
  'inpaint current page': 'manga_action_inpaint',
  'render current page': 'manga_action_render',
  'validate runtime': 'manga_action_validate_runtime',
  'add block': 'manga_action_add',
  undo: 'manga_action_undo',
  redo: 'manga_action_redo',
  'save project': 'manga_action_save',
  'export pdf': 'manga_export_pdf',
  'export cbz': 'manga_export_cbz',
  'export epub': 'manga_export_epub',
  'export zip': 'manga_export_zip',
  'export rar': 'manga_export_rar',
};

const getActionLabelKey = (action: string) => (
  action.startsWith('download model:')
    ? 'manga_action_prepare_model'
    : ACTION_LABEL_KEYS[action] || 'manga_action_generic'
);

const createDefaultLayerControls = (viewMode: MangaViewMode): MangaLayerControls => ({
  segment: { visible: false, opacity: 0.35 },
  bubble: { visible: false, opacity: 0.35 },
  brush: { visible: false, opacity: 0.35 },
  overlay: { visible: viewMode === 'overlay', opacity: 1 },
});

export const MangaEditor: React.FC = () => {
  const { t } = useI18n();
  const [projectPath, setProjectPath] = useState(getInitialProjectPath());
  const [project, setProject] = useState<MangaProjectSummary | null>(null);
  const [scene, setScene] = useState<MangaSceneSummary | null>(null);
  const [page, setPage] = useState<MangaPageDetail | null>(null);
  const [selectedPageId, setSelectedPageId] = useState('');
  const [selectedPageIds, setSelectedPageIds] = useState<string[]>([]);
  const [activeBlockId, setActiveBlockId] = useState('');
  const [viewMode, setViewMode] = useState<MangaViewMode>('rendered');
  const [isLoading, setIsLoading] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ tone: NoticeTone; message: string } | null>(null);
  const [activeJob, setActiveJob] = useState<MangaJob | null>(null);
  const [runtimeValidation, setRuntimeValidation] = useState<MangaRuntimeValidationResult | null>(null);
  const [blockDrafts, setBlockDrafts] = useState<Record<string, MangaBlockDraft>>({});
  const [canvasCommand, setCanvasCommand] = useState<MangaCanvasCommand>({ kind: 'fit', token: 0 });
  const [canvasZoomPercent, setCanvasZoomPercent] = useState(100);
  const [canvasPointer, setCanvasPointer] = useState<MangaCanvasPointer | null>(null);
  const [layerControls, setLayerControls] = useState<MangaLayerControls>(createDefaultLayerControls('rendered'));

  const selectedCount = selectedPageIds.length || (selectedPageId ? 1 : 0);

  const currentImageUrl = useMemo(() => {
    if (!page) return '';
    if (viewMode === 'original' || viewMode === 'overlay') return page.layers.source_url;
    if (viewMode === 'inpainted') return page.layers.inpainted_url;
    return page.layers.rendered_url;
  }, [page, viewMode]);

  const engineCards = useMemo<MangaEngineCard[]>(() => {
    if (!scene?.engines) return [];

    const buildPackageCard = (pkg: any) => ({
      modelId: String(pkg?.model_id || ''),
      label: String(pkg?.display_name || pkg?.model_id || t('manga_unknown_package')),
      repoId: String(pkg?.repo_id || ''),
      available: Boolean(pkg?.available),
      runtimeSupported: Boolean(pkg?.runtime_supported),
      runtimeEngineId: String(pkg?.runtime_engine_id || ''),
      storagePath: String(pkg?.runtime_assets_path || pkg?.snapshot_path || ''),
    });

    const ocrPackage = buildPackageCard(scene.engines.ocr.package);
    const detectorPackage = buildPackageCard(scene.engines.detect.detector_package);
    const segmenterPackage = buildPackageCard(scene.engines.detect.segmenter_package);
    const inpaintPackage = buildPackageCard(scene.engines.inpaint.package);

    return [
      {
        label: t('manga_engine_ocr'),
        configured: scene.engines.ocr.configured_engine_id,
        runtime: scene.engines.ocr.runtime_engine_id,
        available: Boolean(scene.engines.ocr.package?.available),
        packageLabel: scene.engines.ocr.package?.display_name || scene.engines.ocr.package?.repo_id || t('manga_unknown_package'),
        packages: [ocrPackage].filter((pkg) => pkg.modelId),
      },
      {
        label: t('manga_engine_detect'),
        configured: `${scene.engines.detect.configured_detector_id} / ${scene.engines.detect.configured_segmenter_id}`,
        runtime: `${scene.engines.detect.runtime_detector_id} / ${scene.engines.detect.runtime_segmenter_id}`,
        available: Boolean(scene.engines.detect.detector_package?.available) && Boolean(scene.engines.detect.segmenter_package?.available),
        packageLabel: [
          scene.engines.detect.detector_package?.display_name || scene.engines.detect.detector_package?.repo_id || '',
          scene.engines.detect.segmenter_package?.display_name || scene.engines.detect.segmenter_package?.repo_id || '',
        ].filter(Boolean).join(' + '),
        packages: [detectorPackage, segmenterPackage].filter((pkg) => pkg.modelId),
      },
      {
        label: t('manga_engine_inpaint'),
        configured: scene.engines.inpaint.configured_engine_id,
        runtime: scene.engines.inpaint.runtime_engine_id,
        available: Boolean(scene.engines.inpaint.package?.available),
        packageLabel: scene.engines.inpaint.package?.display_name || scene.engines.inpaint.package?.repo_id || t('manga_unknown_package'),
        packages: [inpaintPackage].filter((pkg) => pkg.modelId),
      },
    ];
  }, [scene, t]);

  const activeBlock = useMemo(
    () => page?.blocks.find((block) => block.block_id === activeBlockId) || null,
    [activeBlockId, page],
  );

  const activeBlockDraft = activeBlockId ? blockDrafts[activeBlockId] || null : null;

  const activeJobSummary = useMemo(() => (
    activeJob
      ? {
          stageLabel: formatStageLabel(activeJob.stage, t),
          progress: activeJob.progress,
          status: activeJob.status,
          message: activeJob.message,
        }
      : null
  ), [activeJob, t]);

  const statusLeftText = page
    ? t('manga_status_page_loaded', page.index, page.width, page.height, page.blocks.length, t(`manga_view_${viewMode}`), canvasZoomPercent)
    : t('manga_status_no_page_loaded');

  const statusCenterText = canvasPointer
    ? t('manga_status_cursor', canvasPointer.x, canvasPointer.y, Math.round(canvasPointer.normalizedX * 100), Math.round(canvasPointer.normalizedY * 100))
    : t('manga_status_cursor_empty');

  const statusRightText = activeJobSummary
    ? `${activeJobSummary.stageLabel} · ${activeJobSummary.progress}% · ${translateMangaEnum('manga_state', activeJobSummary.status, t)}`
    : engineCards.length > 0
      ? engineCards.map((card) => `${card.label}:${card.available ? t('manga_ready') : t('manga_missing')}`).join(' · ')
      : t('manga_idle');

  const showNotice = (tone: NoticeTone, message: string) => {
    setNotice({ tone, message });
    if (tone !== 'error') {
      window.setTimeout(() => {
        setNotice((current) => (current?.message === message ? null : current));
      }, 4000);
    }
  };

  const setDraftsFromPage = (detail: MangaPageDetail) => {
    const nextDrafts: Record<string, MangaBlockDraft> = {};
    for (const block of detail.blocks) {
      nextDrafts[block.block_id] = {
        source_text: block.source_text || '',
        translation: block.translation || '',
        font_family: block.style.font_family,
        font_size: block.style.font_size,
        line_spacing: block.style.line_spacing,
        fill: block.style.fill,
        stroke_color: block.style.stroke_color,
        stroke_width: block.style.stroke_width,
      };
    }
    setBlockDrafts(nextDrafts);
    setActiveBlockId((current) => (
      detail.blocks.some((block) => block.block_id === current)
        ? current
        : detail.blocks[0]?.block_id || ''
    ));
  };

  const updateDraft = (blockId: string, patch: Partial<MangaBlockDraft>) => {
    setBlockDrafts((current) => ({
      ...current,
      [blockId]: {
        ...(current[blockId] || {
          source_text: '',
          translation: '',
          font_family: '',
          font_size: 42,
          line_spacing: 1.2,
          fill: '#111111',
          stroke_color: '#ffffff',
          stroke_width: 2,
        }),
        ...patch,
      },
    }));
  };

  const loadPage = async (projectId: string, pageId: string) => {
    const detail = await DataService.getMangaPage(projectId, pageId);
    setPage(detail);
    setSelectedPageId(pageId);
    setRuntimeValidation(null);
    setDraftsFromPage(detail);
    setScene((current) => (current ? { ...current, current_page_id: pageId } : current));
    try {
      const latestValidation = await DataService.getLatestMangaRuntimeValidation(projectId, pageId);
      setRuntimeValidation(latestValidation);
    } catch {
      setRuntimeValidation(null);
    }
  };

  const refreshScene = async (projectId: string) => {
    const sceneSummary = await DataService.getMangaScene(projectId);
    setScene(sceneSummary);
    return sceneSummary;
  };

  const refreshCurrentPage = async (projectId: string, pageId?: string) => {
    const targetPageId = pageId || selectedPageId || scene?.current_page_id || '';
    if (!targetPageId) return;
    await loadPage(projectId, targetPageId);
  };

  const syncProjectState = async (projectId: string, preferredPageId?: string) => {
    const nextScene = await refreshScene(projectId);
    const nextPageId = preferredPageId || nextScene.current_page_id || nextScene.pages[0]?.page_id || '';
    if (nextPageId) {
      await loadPage(projectId, nextPageId);
    } else {
      setPage(null);
      setSelectedPageId('');
      setActiveBlockId('');
    }
  };

  const waitForJob = async (
    projectId: string,
    initialJob: MangaJob,
    options?: { maxAttempts?: number; intervalMs?: number },
  ) => {
    setActiveJob(initialJob);
    if (!initialJob.job_id || initialJob.status === 'completed' || initialJob.status === 'failed') {
      return initialJob;
    }

    let latest = initialJob;
    const maxAttempts = options?.maxAttempts ?? 90;
    const intervalMs = options?.intervalMs ?? 500;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await delay(intervalMs);
      latest = await DataService.getMangaJob(projectId, initialJob.job_id);
      setActiveJob(latest);
      if (latest.status === 'completed' || latest.status === 'failed') {
        break;
      }
    }
    return latest;
  };

  const withBusyAction = async (action: string, callback: () => Promise<void>) => {
    setBusyAction(action);
    setError('');
    try {
      await callback();
    } catch (err: any) {
      const actionLabel = t(getActionLabelKey(action));
      setError(err.message || t('manga_error_failed_action', actionLabel));
    } finally {
      setBusyAction('');
    }
  };

  const buildChangedOps = () => {
    if (!page) return [];

    const ops: any[] = [];
    for (const block of page.blocks) {
      const draft = blockDrafts[block.block_id];
      if (!draft) continue;

      const patch: Record<string, string | number> = {};
      if (draft.source_text !== (block.source_text || '')) patch.source_text = draft.source_text;
      if (draft.translation !== (block.translation || '')) patch.translation = draft.translation;
      if (draft.font_family !== block.style.font_family) patch['style.font_family'] = draft.font_family;
      if (draft.font_size !== block.style.font_size) patch['style.font_size'] = draft.font_size;
      if (draft.line_spacing !== block.style.line_spacing) patch['style.line_spacing'] = draft.line_spacing;
      if (draft.fill !== block.style.fill) patch['style.fill'] = draft.fill;
      if (draft.stroke_color !== block.style.stroke_color) patch['style.stroke_color'] = draft.stroke_color;
      if (draft.stroke_width !== block.style.stroke_width) patch['style.stroke_width'] = draft.stroke_width;

      if (Object.keys(patch).length > 0) {
        ops.push({
          type: 'UpdateTextBlock',
          page_id: page.page_id,
          block_id: block.block_id,
          patch,
        });
      }
    }
    return ops;
  };

  const applyDraftChanges = async (quiet = false) => {
    if (!project || !page) return 0;

    const ops = buildChangedOps();
    if (ops.length === 0) {
      if (!quiet) showNotice('info', t('manga_notice_no_block_changes'));
      return 0;
    }

    await DataService.applyMangaOps(project.project_id, ops);
    await syncProjectState(project.project_id, page.page_id);
    if (!quiet) showNotice('success', t('manga_notice_saved_block_changes', ops.length));
    return ops.length;
  };

  const openProject = async (pathOverride?: string) => {
    const nextPath = (pathOverride ?? projectPath).trim();
    if (!nextPath) {
      setError(t('manga_error_project_path_required'));
      return;
    }

    setProjectPath(nextPath);
    setError('');
    setIsLoading(true);
    try {
      const opened = await DataService.openMangaProject(nextPath);
      const sceneSummary = await DataService.getMangaScene(opened.project_id);
      setProject(opened);
      setScene(sceneSummary);
      setSelectedPageIds([]);
      setActiveJob(null);
      setActiveBlockId('');

      const firstPageId = sceneSummary.current_page_id || sceneSummary.pages[0]?.page_id || '';
      if (firstPageId) {
        await loadPage(opened.project_id, firstPageId);
      } else {
        setPage(null);
        setSelectedPageId('');
      }
    } catch (err: any) {
      setError(err.message || t('manga_error_open_project_failed'));
    } finally {
      setIsLoading(false);
    }
  };

  const runPagePipelineAction = async (
    action: string,
    runner: (projectId: string, pageId: string) => Promise<MangaJob>,
    options?: {
      syncDraftsBefore?: boolean;
      nextViewMode?: MangaViewMode;
    },
  ) => {
    if (!project || !selectedPageId) return;

    await withBusyAction(action, async () => {
      if (options?.syncDraftsBefore) {
        await applyDraftChanges(true);
      }
      const job = await runner(project.project_id, selectedPageId);
      const settled = await waitForJob(project.project_id, job);
      await syncProjectState(project.project_id, selectedPageId);
      if (options?.nextViewMode) {
        setViewMode(options.nextViewMode);
      }
      showNotice(settled.status === 'completed' ? 'success' : 'warning', settled.message);
    });
  };

  const handleDetectPage = async () => {
    await runPagePipelineAction('detect current page', DataService.detectMangaPage, { nextViewMode: 'original' });
  };

  const handleOcrPage = async () => {
    await runPagePipelineAction('ocr current page', DataService.ocrMangaPage, { nextViewMode: 'overlay' });
  };

  const handleTranslateCurrentPage = async () => {
    await runPagePipelineAction('translate current page', DataService.translateMangaPage, { nextViewMode: 'rendered' });
  };

  const handleInpaintPage = async () => {
    await runPagePipelineAction('inpaint current page', DataService.inpaintMangaPage, { nextViewMode: 'inpainted' });
  };

  const handleRenderPage = async () => {
    await runPagePipelineAction('render current page', DataService.renderMangaPage, {
      syncDraftsBefore: true,
      nextViewMode: 'rendered',
    });
  };

  const handleValidateRuntime = async () => {
    if (!project || !selectedPageId) return;

    await withBusyAction('validate runtime', async () => {
      const result = await DataService.validateMangaRuntime(project.project_id, selectedPageId);
      setRuntimeValidation(result);
      const runtimeCount = result.summary?.runtime_stage_count ?? 0;
      const fallbackCount = result.summary?.fallback_stage_count ?? 0;
      showNotice(
        result.ok ? 'success' : 'warning',
        t('manga_notice_runtime_validation_finished', runtimeCount, fallbackCount),
      );
    });
  };

  const handleDownloadMangaModel = async (modelId: string) => {
    if (!modelId || !project) return;

    await withBusyAction(`download model:${modelId}`, async () => {
      const job = await DataService.startMangaModelDownload(modelId);
      const settled = await waitForJob(project.project_id, job, { maxAttempts: 7200, intervalMs: 500 });
      const result = settled.result || {};
      const modelLabel = String(result.display_name || result.model_id || modelId);
      showNotice(
        settled.status === 'completed' ? 'success' : 'warning',
        settled.status === 'completed'
          ? t('manga_notice_model_prepared', modelLabel)
          : settled.error_message || settled.message || t('manga_notice_model_prepare_warning', modelLabel),
      );
      await refreshScene(project.project_id);
    });
  };

  const handleTranslateSelectedPages = async () => {
    if (!project) return;

    const pageIds = selectedPageIds.length > 0 ? selectedPageIds : (selectedPageId ? [selectedPageId] : []);
    if (pageIds.length === 0) {
      showNotice('warning', t('manga_notice_select_page_for_batch'));
      return;
    }

    await withBusyAction('translate selected pages', async () => {
      const job = await DataService.translateSelectedMangaPages(project.project_id, pageIds);
      const settled = await waitForJob(project.project_id, job);
      await syncProjectState(project.project_id, selectedPageId || pageIds[0]);
      setViewMode('overlay');
      showNotice(settled.status === 'completed' ? 'success' : 'warning', settled.message);
    });
  };

  const handlePlanSelectedPages = async () => {
    if (!project) return;

    const pageIds = selectedPageIds.length > 0 ? selectedPageIds : (selectedPageId ? [selectedPageId] : []);
    if (pageIds.length === 0) {
      showNotice('warning', t('manga_notice_select_page_for_plan'));
      return;
    }

    await withBusyAction('plan selected pages', async () => {
      const job = await DataService.planSelectedMangaPages(project.project_id, pageIds);
      const settled = await waitForJob(project.project_id, job);
      await syncProjectState(project.project_id, selectedPageId || pageIds[0]);
      setViewMode('overlay');
      showNotice(settled.status === 'completed' ? 'success' : 'warning', settled.message);
    });
  };

  const handleSaveProject = async () => {
    if (!project) return;

    await withBusyAction('save project', async () => {
      await applyDraftChanges(true);
      const result = await DataService.saveMangaProject(project.project_id);
      showNotice(result.ok ? 'success' : 'warning', result.ok ? t('manga_notice_project_saved') : result.message || t('manga_notice_project_save_warning'));
    });
  };

  const handleAddBlock = async () => {
    if (!project || !page) return;

    const blockId = `blk_${page.page_id}_manual_${Date.now()}`;
    const width = Math.max(120, Math.round(page.width * 0.24));
    const height = Math.max(90, Math.round(page.height * 0.16));
    const x1 = Math.round((page.width - width) / 2);
    const y1 = Math.round((page.height - height) / 2);

    await withBusyAction('add block', async () => {
      await DataService.applyMangaOps(project.project_id, [
        {
          type: 'AddTextBlock',
          page_id: page.page_id,
          payload: {
            block: {
              block_id: blockId,
              bbox: [x1, y1, x1 + width, y1 + height],
              source_text: '',
              translation: '',
              origin: 'manual',
              placement_mode: 'free_manual',
              editable: true,
            },
          },
        },
      ]);
      await syncProjectState(project.project_id, page.page_id);
      setActiveBlockId(blockId);
      setViewMode('overlay');
      showNotice('success', t('manga_notice_manual_block_added'));
    });
  };

  const handleUndo = async () => {
    if (!project || !page) return;

    await withBusyAction('undo', async () => {
      const result = await DataService.undoMangaOps(project.project_id);
      await syncProjectState(project.project_id, page.page_id);
      showNotice(result.ok ? 'success' : 'warning', result.message || (result.ok ? t('manga_notice_undo_applied') : t('manga_notice_nothing_to_undo')));
    });
  };

  const handleRedo = async () => {
    if (!project || !page) return;

    await withBusyAction('redo', async () => {
      const result = await DataService.redoMangaOps(project.project_id);
      await syncProjectState(project.project_id, page.page_id);
      showNotice(result.ok ? 'success' : 'warning', result.message || (result.ok ? t('manga_notice_redo_applied') : t('manga_notice_nothing_to_redo')));
    });
  };

  const handleExport = async (format: 'pdf' | 'epub' | 'cbz' | 'zip' | 'rar') => {
    if (!project) return;

    await withBusyAction(`export ${format}`, async () => {
      await applyDraftChanges(true);
      const result = await DataService.exportMangaProject(project.project_id, format);
      showNotice(
        result.ok ? 'success' : 'warning',
        result.ok ? t('manga_notice_exported_to', format.toUpperCase(), result.path || '') : t('manga_notice_export_no_file', format.toUpperCase()),
      );
    });
  };

  const togglePageSelection = (pageId: string) => {
    setSelectedPageIds((current) => (
      current.includes(pageId)
        ? current.filter((item) => item !== pageId)
        : [...current, pageId]
    ));
  };

  const toggleLayer = (layer: MangaOverlayLayerKey) => {
    setLayerControls((current) => ({
      ...current,
      [layer]: {
        ...current[layer],
        visible: !current[layer].visible,
      },
    }));
  };

  const setLayerOpacity = (layer: MangaOverlayLayerKey, opacity: number) => {
    setLayerControls((current) => ({
      ...current,
      [layer]: {
        ...current[layer],
        opacity,
      },
    }));
  };

  useEffect(() => {
    setCanvasCommand((current) => ({ kind: 'fit', token: current.token + 1 }));
    setCanvasPointer(null);
  }, [page?.page_id, viewMode]);

  useEffect(() => {
    setLayerControls(createDefaultLayerControls(viewMode));
  }, [page?.page_id, viewMode]);

  useEffect(() => {
    if (projectPath) {
      void openProject(projectPath);
    }
    // Run once on initial mount; hash parsing already seeded projectPath.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="h-screen bg-background text-slate-100 flex flex-col overflow-hidden">
      <MangaTopBar
        projectName={project?.name || t('manga_open_mangaproject')}
        viewMode={viewMode}
        busyAction={busyAction}
        hasProject={Boolean(project)}
        hasPage={Boolean(page)}
        hasSelectedPage={Boolean(selectedPageId)}
        selectedCount={selectedCount}
        currentPageIndex={page?.index || 0}
        pageCount={scene?.pages.length || project?.page_count || 0}
        zoomPercent={canvasZoomPercent}
        onBack={() => { window.location.hash = '/task'; }}
        onSetViewMode={setViewMode}
        onFitCanvas={() => { setCanvasCommand((current) => ({ kind: 'fit', token: current.token + 1 })); }}
        onResetZoom={() => { setCanvasCommand((current) => ({ kind: 'actual', token: current.token + 1 })); }}
        onDetect={() => { void handleDetectPage(); }}
        onOcr={() => { void handleOcrPage(); }}
        onTranslateCurrent={() => { void handleTranslateCurrentPage(); }}
        onTranslateSelected={() => { void handleTranslateSelectedPages(); }}
        onPlanSelected={() => { void handlePlanSelectedPages(); }}
        onInpaint={() => { void handleInpaintPage(); }}
        onRender={() => { void handleRenderPage(); }}
        onValidateRuntime={() => { void handleValidateRuntime(); }}
        onAddBlock={() => { void handleAddBlock(); }}
        onUndo={() => { void handleUndo(); }}
        onRedo={() => { void handleRedo(); }}
        onSave={() => { void handleSaveProject(); }}
        onExportPdf={() => { void handleExport('pdf'); }}
        onExportCbz={() => { void handleExport('cbz'); }}
        onExportEpub={() => { void handleExport('epub'); }}
        onExportZip={() => { void handleExport('zip'); }}
        onExportRar={() => { void handleExport('rar'); }}
      />

      {!project && (
      <div className="m-4 rounded-lg border border-slate-800 bg-slate-950/78 p-4 shadow-2xl shadow-slate-950/30 flex flex-col xl:flex-row gap-3 xl:items-center">
        <input
          type="text"
          value={projectPath}
          onChange={(event) => setProjectPath(event.target.value)}
          placeholder={t('manga_project_path_placeholder')}
          className="flex-1 min-w-0 rounded-lg border border-slate-800 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 outline-none focus:border-primary"
        />
        <div className="flex items-center gap-2">
          <button
            onClick={() => void openProject()}
            disabled={isLoading}
            className="px-4 py-3 rounded-lg bg-primary text-slate-900 font-bold disabled:opacity-60 flex items-center gap-2"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            {t('manga_open_project')}
          </button>
          <button
            onClick={() => setViewMode('overlay')}
            disabled={!page}
            className="px-4 py-3 rounded-lg border border-slate-800 bg-slate-900/80 text-sm text-slate-300 disabled:opacity-50"
          >
            {t('manga_view_overlay')}
          </button>
        </div>
      </div>
      )}

      {notice && (
        <div className={`mx-4 mt-3 rounded-lg border px-4 py-3 text-sm ${
          notice.tone === 'success' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200' :
          notice.tone === 'warning' ? 'border-amber-500/20 bg-amber-500/10 text-amber-200' :
          notice.tone === 'error' ? 'border-rose-500/20 bg-rose-500/10 text-rose-200' :
          'border-cyan-500/20 bg-cyan-500/10 text-cyan-200'
        }`}>
          {notice.message}
        </div>
      )}

      {error && (
        <div className="mx-4 mt-3 rounded-lg border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 flex bg-slate-950">
        <MangaPageStrip
          pages={scene?.pages || []}
          selectedPageId={selectedPageId}
          selectedPageIds={selectedPageIds}
          currentPageId={scene?.current_page_id || ''}
          onSelectPage={(pageId) => { if (project) void loadPage(project.project_id, pageId); }}
          onTogglePageSelection={togglePageSelection}
        />

        <MangaCanvas
          page={page}
          currentImageUrl={currentImageUrl}
          viewMode={viewMode}
          activeBlockId={activeBlockId}
          blockDrafts={blockDrafts}
          activeJob={activeJobSummary}
          layerControls={layerControls}
          zoomCommand={canvasCommand}
          onSelectBlock={setActiveBlockId}
          onViewportChange={setCanvasZoomPercent}
          onPointerChange={setCanvasPointer}
        />

        <aside className="w-[340px] shrink-0 border-l border-slate-900 bg-slate-950/88 overflow-y-auto 2xl:w-[360px]">
          <MangaInspector
            page={page}
            activeBlock={activeBlock}
            activeBlockDraft={activeBlockDraft}
            activeJob={activeJobSummary}
            engineCards={engineCards}
            runtimeValidation={runtimeValidation}
            busyAction={busyAction}
            onDownloadModel={(modelId) => { void handleDownloadMangaModel(modelId); }}
          />
          <MangaLayersPanel
            page={page}
            viewMode={viewMode}
            layerControls={layerControls}
            onToggleLayer={toggleLayer}
            onSetLayerOpacity={setLayerOpacity}
          />
          <MangaBlocksPanel
            page={page}
            blockDrafts={blockDrafts}
            activeBlockId={activeBlockId}
            busyAction={busyAction}
            hasProject={Boolean(project)}
            onSelectBlock={setActiveBlockId}
            onUpdateDraft={updateDraft}
            onSavePageChanges={() => { void applyDraftChanges(); }}
          />
        </aside>
      </div>

      <MangaStatusBar leftText={statusLeftText} centerText={statusCenterText} rightText={statusRightText} />
    </div>
  );
};
