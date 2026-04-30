import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, Star } from 'lucide-react';
import { MangaBlocksPanel } from '../components/manga/mangaBlocksPanel';
import { MangaCanvas } from '../components/manga/mangaCanvas';
import { MangaInspector } from '../components/manga/mangaInspector';
import { MangaLayersPanel } from '../components/manga/mangaLayersPanel';
import { MangaPageStrip } from '../components/manga/mangaPageStrip';
import { MangaStatusBar } from '../components/manga/mangaStatusBar';
import { MangaTopBar } from '../components/manga/mangaTopBar';
import { useI18n } from '../contexts/I18nContext';
import { MangaBlockDraft, MangaBrushStrokePayload, MangaCanvasCommand, MangaCanvasPointer, MangaCanvasRuntimeBox, MangaCanvasRuntimeOverlay, MangaEngineCard, MangaLayerControls, MangaOverlayLayerKey, MangaViewMode, translateMangaEnum } from '../components/manga/shared';
import { DataService } from '../services/DataService';
import { MangaJob, MangaOpenProjectSummary, MangaPageDetail, MangaProjectSummary, MangaRuntimeValidationDiffResult, MangaRuntimeValidationHistoryItem, MangaRuntimeValidationResult, MangaRuntimeValidationStage, MangaSceneSummary } from '../types/manga';

type NoticeTone = 'info' | 'success' | 'warning' | 'error';

const getInitialProjectPath = () => {
  const hash = window.location.hash || '';
  const query = hash.includes('?') ? hash.split('?')[1] : '';
  return new URLSearchParams(query).get('project_path') || '';
};

const getInitialPageId = () => {
  const hash = window.location.hash || '';
  const query = hash.includes('?') ? hash.split('?')[1] : '';
  return new URLSearchParams(query).get('page_id') || '';
};

const getInitialViewMode = (): MangaViewMode => {
  const hash = window.location.hash || '';
  const query = hash.includes('?') ? hash.split('?')[1] : '';
  const value = new URLSearchParams(query).get('view');
  return value === 'original' || value === 'overlay' || value === 'inpainted' || value === 'rendered'
    ? value
    : 'rendered';
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
  'load runtime validation report': 'manga_action_runtime_report',
  'diff runtime validation reports': 'manga_action_runtime_diff',
  'delete runtime validation report': 'manga_action_delete_runtime_history',
  'retry runtime validation stage': 'manga_action_retry_runtime_stage',
  'add block': 'manga_action_add',
  'delete block': 'manga_action_delete',
  'brush mask': 'manga_action_brush_mask',
  'restore mask': 'manga_action_restore_mask',
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
  sourceReference: { visible: true, opacity: 0.32 },
  segment: { visible: false, opacity: 0.35 },
  bubble: { visible: false, opacity: 0.35 },
  brush: { visible: false, opacity: 0.35 },
  restore: { visible: false, opacity: 0.42 },
  overlay: { visible: viewMode === 'overlay', opacity: 1 },
});

const RECENT_MANGA_PROJECTS_KEY = 'ainiee:manga:recent-projects';
const PINNED_MANGA_PROJECTS_KEY = 'ainiee:manga:pinned-projects';

const loadStoredProjectPaths = (storageKey: string, limit: number) => {
  try {
    const payload = JSON.parse(window.localStorage.getItem(storageKey) || '[]');
    return Array.isArray(payload) ? payload.filter((value): value is string => typeof value === 'string').slice(0, limit) : [];
  } catch {
    return [];
  }
};

const loadRecentProjectPaths = () => loadStoredProjectPaths(RECENT_MANGA_PROJECTS_KEY, 5);
const loadPinnedProjectPaths = () => loadStoredProjectPaths(PINNED_MANGA_PROJECTS_KEY, 8);

const rememberRecentProjectPath = (path: string) => {
  const next = [path, ...loadRecentProjectPaths().filter((item) => item !== path)].slice(0, 5);
  window.localStorage.setItem(RECENT_MANGA_PROJECTS_KEY, JSON.stringify(next));
  return next;
};

const compactProjectPath = (path: string) => (
  path
    .replace(/\\/g, '/')
    .split('/')
    .filter(Boolean)
    .slice(-3)
    .join('/')
    || path
);

const areBboxesEqual = (left: number[] = [], right: number[] = []) => (
  left.length >= 4
  && right.length >= 4
  && left.slice(0, 4).every((value, index) => Math.round(value) === Math.round(right[index]))
);

const isBlockDirty = (block: MangaPageDetail['blocks'][number], draft?: MangaBlockDraft) => {
  if (!draft) return false;
  return (
    !areBboxesEqual(draft.bbox, block.bbox)
    || draft.source_text !== (block.source_text || '')
    || draft.translation !== (block.translation || '')
    || draft.font_family !== block.style.font_family
    || draft.font_size !== block.style.font_size
    || draft.line_spacing !== block.style.line_spacing
    || draft.fill !== block.style.fill
    || draft.stroke_color !== block.style.stroke_color
    || draft.stroke_width !== block.style.stroke_width
  );
};

const buildProjectAssetUrl = (projectId: string, relativePath: string) => {
  if (!projectId || !relativePath) return '';
  return `/api/manga/projects/${projectId}/assets/${relativePath.split('/').map(encodeURIComponent).join('/')}`;
};

const pickOverlayBaseImageUrl = (page: MangaPageDetail) => (
  page.layers.rendered_url || page.layers.inpainted_url || page.layers.source_url
);

const pickRuntimeStageImageUrl = (stage: MangaRuntimeValidationStage, projectId: string) => {
  const urls = stage.artifact_urls || {};
  const artifacts = stage.artifacts || {};
  if (stage.stage === 'detect') {
    return urls.segment_mask || urls.bubble_mask || buildProjectAssetUrl(projectId, artifacts.segment_mask || artifacts.bubble_mask || '');
  }
  if (stage.stage === 'inpaint') {
    return urls.inpainted || buildProjectAssetUrl(projectId, artifacts.inpainted || '');
  }
  return '';
};

const normalizeRuntimeBoxes = (
  records: unknown,
  labelPrefix: string,
  tone: MangaCanvasRuntimeBox['tone'],
): MangaCanvasRuntimeBox[] => {
  if (!Array.isArray(records)) return [];
  return records.flatMap((record, index) => {
    if (!record || typeof record !== 'object') return [];
    const data = record as Record<string, any>;
    const bbox = Array.isArray(data.bbox)
      ? data.bbox
      : Array.isArray(data.inner_bbox)
        ? data.inner_bbox
        : Array.isArray(data.component_bbox)
          ? data.component_bbox
          : [];
    if (bbox.length < 4) return [];
    const label = String(data.source_text || data.region_id || data.seed_id || data.bubble_id || `${labelPrefix} ${index + 1}`);
    return [{
      bbox: bbox.slice(0, 4).map((value) => Number(value)),
      label: label.length > 24 ? `${label.slice(0, 24)}...` : label,
      tone,
    }];
  });
};

const extractRuntimeRunId = (outputDir: string) => (
  outputDir.replace(/\\/g, '/').split('/').filter(Boolean).pop() || ''
);

export const MangaEditor: React.FC = () => {
  const { t } = useI18n();
  const [projectPath, setProjectPath] = useState(getInitialProjectPath());
  const [recentProjectPaths, setRecentProjectPaths] = useState<string[]>(loadRecentProjectPaths());
  const [pinnedProjectPaths, setPinnedProjectPaths] = useState<string[]>(loadPinnedProjectPaths());
  const [openProjects, setOpenProjects] = useState<MangaOpenProjectSummary[]>([]);
  const [project, setProject] = useState<MangaProjectSummary | null>(null);
  const [scene, setScene] = useState<MangaSceneSummary | null>(null);
  const [page, setPage] = useState<MangaPageDetail | null>(null);
  const [selectedPageId, setSelectedPageId] = useState('');
  const [selectedPageIds, setSelectedPageIds] = useState<string[]>([]);
  const [activeBlockId, setActiveBlockId] = useState('');
  const [viewMode, setViewMode] = useState<MangaViewMode>(getInitialViewMode());
  const [isLoading, setIsLoading] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ tone: NoticeTone; message: string } | null>(null);
  const [activeJob, setActiveJob] = useState<MangaJob | null>(null);
  const [runtimeValidation, setRuntimeValidation] = useState<MangaRuntimeValidationResult | null>(null);
  const [runtimeValidationHistory, setRuntimeValidationHistory] = useState<MangaRuntimeValidationHistoryItem[]>([]);
  const [runtimeValidationDiff, setRuntimeValidationDiff] = useState<MangaRuntimeValidationDiffResult | null>(null);
  const [activeRuntimeStage, setActiveRuntimeStage] = useState('');
  const [blockDrafts, setBlockDrafts] = useState<Record<string, MangaBlockDraft>>({});
  const [canvasCommand, setCanvasCommand] = useState<MangaCanvasCommand>({ kind: 'fit', token: 0 });
  const [canvasZoomPercent, setCanvasZoomPercent] = useState(100);
  const [canvasPointer, setCanvasPointer] = useState<MangaCanvasPointer | null>(null);
  const [layerControls, setLayerControls] = useState<MangaLayerControls>(createDefaultLayerControls('rendered'));
  const [brushRadius, setBrushRadius] = useState(24);

  const selectedCount = selectedPageIds.length || (selectedPageId ? 1 : 0);
  const unpinnedRecentProjectPaths = useMemo(
    () => recentProjectPaths.filter((path) => !pinnedProjectPaths.includes(path)),
    [pinnedProjectPaths, recentProjectPaths],
  );

  const currentImageUrl = useMemo(() => {
    if (!page) return '';
    if (viewMode === 'overlay') return pickOverlayBaseImageUrl(page);
    if (viewMode === 'original') return page.layers.source_url;
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
  const activeBlockDirty = Boolean(activeBlock && isBlockDirty(activeBlock, activeBlockDraft || undefined));

  const dirtyBlockCount = useMemo(() => (
    page?.blocks.filter((block) => isBlockDirty(block, blockDrafts[block.block_id])).length || 0
  ), [blockDrafts, page]);

  const selectedRuntimeStage = useMemo(() => {
    if (!runtimeValidation?.stages.length) return null;
    return runtimeValidation.stages.find((stage) => stage.stage === activeRuntimeStage) || runtimeValidation.stages[0];
  }, [activeRuntimeStage, runtimeValidation]);

  const runtimeOverlay = useMemo<MangaCanvasRuntimeOverlay | null>(() => {
    if (!selectedRuntimeStage) return null;
    const title = translateMangaEnum('manga_runtime_stage', selectedRuntimeStage.stage, t);
    const imageUrl = pickRuntimeStageImageUrl(selectedRuntimeStage, project?.project_id || runtimeValidation?.project_id || '');
    const metrics = selectedRuntimeStage.metrics || {};
    const boxes = selectedRuntimeStage.stage === 'detect'
      ? normalizeRuntimeBoxes(metrics.text_regions, t('manga_runtime_stage_detect'), 'cyan')
      : selectedRuntimeStage.stage === 'ocr'
        ? normalizeRuntimeBoxes(metrics.seeds, t('manga_runtime_stage_ocr'), 'amber')
        : [];
    const message = selectedRuntimeStage.error_message
      || selectedRuntimeStage.warning_message
      || selectedRuntimeStage.fallback_reason
      || translateMangaEnum(
        'manga_execution_mode',
        selectedRuntimeStage.execution_mode || (selectedRuntimeStage.used_runtime ? 'configured_runtime' : 'heuristic_fallback'),
        t,
      );
    if (!imageUrl && boxes.length === 0) return null;
    return {
      stage: selectedRuntimeStage.stage,
      title,
      imageUrl,
      boxes,
      message,
    };
  }, [project?.project_id, runtimeValidation?.project_id, selectedRuntimeStage, t]);

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

  const refreshOpenProjects = async () => {
    try {
      setOpenProjects(await DataService.listOpenMangaProjects());
    } catch {
      setOpenProjects([]);
    }
  };

  const setDraftsFromPage = (detail: MangaPageDetail) => {
    const nextDrafts: Record<string, MangaBlockDraft> = {};
    for (const block of detail.blocks) {
      nextDrafts[block.block_id] = {
        bbox: block.bbox.slice(0, 4),
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
          bbox: [0, 0, 0, 0],
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

  const togglePinnedProjectPath = (path: string) => {
    const trimmedPath = path.trim();
    if (!trimmedPath) return;
    setPinnedProjectPaths((current) => {
      const next = current.includes(trimmedPath)
        ? current.filter((item) => item !== trimmedPath)
        : [trimmedPath, ...current].slice(0, 8);
      window.localStorage.setItem(PINNED_MANGA_PROJECTS_KEY, JSON.stringify(next));
      return next;
    });
  };

  const isProjectPathPinned = (path: string) => pinnedProjectPaths.includes(path.trim());

  const loadPage = async (projectId: string, pageId: string) => {
    const detail = await DataService.getMangaPage(projectId, pageId);
    setPage(detail);
    setSelectedPageId(pageId);
    setRuntimeValidation(null);
    setRuntimeValidationDiff(null);
    setDraftsFromPage(detail);
    setScene((current) => (current ? { ...current, current_page_id: pageId } : current));
    try {
      const latestValidation = await DataService.getLatestMangaRuntimeValidation(projectId, pageId);
      setRuntimeValidation(latestValidation);
      setActiveRuntimeStage(latestValidation?.stages.find((stage) => !stage.ok)?.stage || latestValidation?.stages[0]?.stage || '');
    } catch {
      setRuntimeValidation(null);
      setActiveRuntimeStage('');
    }
    try {
      setRuntimeValidationHistory(await DataService.listMangaRuntimeValidationHistory(projectId, pageId));
    } catch {
      setRuntimeValidationHistory([]);
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
    if (!initialJob.job_id || ['completed', 'failed', 'cancelled'].includes(initialJob.status)) {
      return initialJob;
    }

    let latest = initialJob;
    const maxAttempts = options?.maxAttempts ?? 90;
    const intervalMs = options?.intervalMs ?? 500;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await delay(intervalMs);
      latest = await DataService.getMangaJob(projectId, initialJob.job_id);
      setActiveJob(latest);
      if (['completed', 'failed', 'cancelled'].includes(latest.status)) {
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

  const buildChangedOps = (onlyBlockId?: string) => {
    if (!page) return [];

    const ops: any[] = [];
    for (const block of page.blocks) {
      if (onlyBlockId && block.block_id !== onlyBlockId) continue;
      const draft = blockDrafts[block.block_id];
      if (!draft) continue;

      const patch: Record<string, string | number | number[]> = {};
      if (!areBboxesEqual(draft.bbox, block.bbox)) patch.bbox = draft.bbox.slice(0, 4).map((value) => Math.round(value));
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

  const applyDraftChanges = async (quiet = false, onlyBlockId?: string) => {
    if (!project || !page) return 0;

    const ops = buildChangedOps(onlyBlockId);
    if (ops.length === 0) {
      if (!quiet) showNotice('info', t('manga_notice_no_block_changes'));
      return 0;
    }

    await DataService.applyMangaOps(project.project_id, ops);
    await syncProjectState(project.project_id, page.page_id);
    if (!quiet) showNotice('success', t('manga_notice_saved_block_changes', ops.length));
    return ops.length;
  };

  const applyActiveBlockChanges = async () => {
    if (!activeBlockId) {
      showNotice('info', t('manga_notice_no_block_changes'));
      return;
    }
    await applyDraftChanges(false, activeBlockId);
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
      setRecentProjectPaths(rememberRecentProjectPath(nextPath));

      const requestedPageId = getInitialPageId();
      const firstPageId = (
        requestedPageId && sceneSummary.pages.some((item) => item.page_id === requestedPageId)
          ? requestedPageId
          : sceneSummary.current_page_id || sceneSummary.pages[0]?.page_id || ''
      );
      if (firstPageId) {
        await loadPage(opened.project_id, firstPageId);
      } else {
        setPage(null);
        setSelectedPageId('');
      }
      void refreshOpenProjects();
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
      const job = await DataService.startMangaRuntimeValidation(project.project_id, selectedPageId);
      const settled = await waitForJob(project.project_id, job, { maxAttempts: 7200, intervalMs: 500 });
      if (settled.status === 'cancelled') {
        setRuntimeValidationHistory(await DataService.listMangaRuntimeValidationHistory(project.project_id, selectedPageId));
        showNotice('warning', t('manga_notice_runtime_validation_cancelled'));
        return;
      }
      const result = (
        settled.result && Array.isArray((settled.result as MangaRuntimeValidationResult).stages)
          ? settled.result as MangaRuntimeValidationResult
          : await DataService.getLatestMangaRuntimeValidation(project.project_id, selectedPageId)
      );
      if (!result) {
        throw new Error(settled.error_message || settled.message || t('manga_error_runtime_validation_no_report'));
      }
      setRuntimeValidation(result);
      setRuntimeValidationDiff(null);
      setActiveRuntimeStage(result.stages.find((stage) => !stage.ok)?.stage || result.stages[0]?.stage || '');
      setRuntimeValidationHistory(await DataService.listMangaRuntimeValidationHistory(project.project_id, selectedPageId));
      const runtimeCount = result.summary?.runtime_stage_count ?? 0;
      const fallbackCount = result.summary?.fallback_stage_count ?? 0;
      showNotice(
        result.ok ? 'success' : 'warning',
        t('manga_notice_runtime_validation_finished', runtimeCount, fallbackCount),
      );
    });
  };

  const handleCancelRuntimeValidation = async () => {
    if (!project || !selectedPageId || !activeJob?.job_id) return;
    try {
      const job = await DataService.stopMangaRuntimeValidation(project.project_id, selectedPageId);
      setActiveJob(job);
      showNotice('warning', t('manga_notice_runtime_validation_cancelling'));
    } catch (err: any) {
      setError(err.message || t('manga_error_failed_action', t('manga_action_cancel_runtime_validation')));
    }
  };

  const handleRetryRuntimeValidationStage = async (stage: string) => {
    if (!project || !selectedPageId || !stage) return;

    await withBusyAction('retry runtime validation stage', async () => {
      const job = await DataService.startMangaRuntimeValidationStageRetry(project.project_id, selectedPageId, stage);
      const settled = await waitForJob(project.project_id, job, { maxAttempts: 7200, intervalMs: 500 });
      if (settled.status === 'cancelled') {
        setRuntimeValidationHistory(await DataService.listMangaRuntimeValidationHistory(project.project_id, selectedPageId));
        showNotice('warning', t('manga_notice_runtime_validation_cancelled'));
        return;
      }
      const result = (
        settled.result && Array.isArray((settled.result as MangaRuntimeValidationResult).stages)
          ? settled.result as MangaRuntimeValidationResult
          : await DataService.getLatestMangaRuntimeValidation(project.project_id, selectedPageId)
      );
      if (!result) {
        throw new Error(settled.error_message || settled.message || t('manga_error_runtime_validation_no_report'));
      }
      setRuntimeValidation(result);
      setRuntimeValidationDiff(null);
      setActiveRuntimeStage(stage);
      setRuntimeValidationHistory(await DataService.listMangaRuntimeValidationHistory(project.project_id, selectedPageId));
      showNotice(
        result.ok ? 'success' : 'warning',
        t('manga_notice_runtime_stage_retry_finished', translateMangaEnum('manga_runtime_stage', stage, t)),
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
      if (settled.status === 'completed' && runtimeValidation) {
        showNotice('info', t('manga_notice_model_ready_rerun_runtime'));
      }
    });
  };

  const handleLoadRuntimeValidationHistory = async (runId: string) => {
    if (!project || !selectedPageId || !runId) return;

    await withBusyAction('load runtime validation report', async () => {
      const result = await DataService.getMangaRuntimeValidationHistoryItem(project.project_id, selectedPageId, runId);
      setRuntimeValidation(result);
      setActiveRuntimeStage(result.stages.find((stage) => !stage.ok)?.stage || result.stages[0]?.stage || '');
      showNotice('info', t('manga_notice_runtime_report_loaded'));
    });
  };

  const handleDiffRuntimeValidationHistory = async (beforeRunId: string, afterRunId: string) => {
    if (!project || !selectedPageId || !beforeRunId || !afterRunId || beforeRunId === afterRunId) return;

    await withBusyAction('diff runtime validation reports', async () => {
      const diff = await DataService.diffMangaRuntimeValidationHistory(project.project_id, selectedPageId, beforeRunId, afterRunId);
      setRuntimeValidationDiff(diff);
      showNotice('info', t('manga_notice_runtime_diff_loaded'));
    });
  };

  const handleDeleteRuntimeValidationHistory = async (runId: string) => {
    if (!project || !selectedPageId || !runId) return;
    if (!window.confirm(t('manga_confirm_delete_runtime_history'))) return;

    await withBusyAction('delete runtime validation report', async () => {
      await DataService.deleteMangaRuntimeValidationHistory(project.project_id, selectedPageId, runId);
      const nextHistory = await DataService.listMangaRuntimeValidationHistory(project.project_id, selectedPageId);
      setRuntimeValidationHistory(nextHistory);
      setRuntimeValidationDiff((current) => (
        current?.before_run_id === runId || current?.after_run_id === runId ? null : current
      ));

      if (extractRuntimeRunId(runtimeValidation?.output_dir || '') === runId) {
        const latestValidation = await DataService.getLatestMangaRuntimeValidation(project.project_id, selectedPageId);
        setRuntimeValidation(latestValidation);
        setActiveRuntimeStage(latestValidation?.stages.find((stage) => !stage.ok)?.stage || latestValidation?.stages[0]?.stage || '');
      }

      showNotice('success', t('manga_notice_runtime_history_deleted'));
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

  const handleSwitchProject = () => {
    if (dirtyBlockCount > 0) {
      showNotice('warning', t('manga_notice_save_before_switch'));
      return;
    }
    setProject(null);
    setScene(null);
    setPage(null);
    setSelectedPageId('');
    setSelectedPageIds([]);
    setActiveBlockId('');
    setActiveJob(null);
    setRuntimeValidation(null);
    setRuntimeValidationHistory([]);
    setRuntimeValidationDiff(null);
    setActiveRuntimeStage('');
    setError('');
    void refreshOpenProjects();
  };

  const handleAddBlock = async (bboxOverride?: number[]) => {
    if (!project || !page) return;

    const blockId = `blk_${page.page_id}_manual_${Date.now()}`;
    const width = Math.max(120, Math.round(page.width * 0.24));
    const height = Math.max(90, Math.round(page.height * 0.16));
    const x1 = Math.round((page.width - width) / 2);
    const y1 = Math.round((page.height - height) / 2);
    const bbox = bboxOverride?.length === 4
      ? bboxOverride.slice(0, 4).map((value) => Math.round(value))
      : [x1, y1, x1 + width, y1 + height];

    await withBusyAction('add block', async () => {
      await DataService.applyMangaOps(project.project_id, [
        {
          type: 'AddTextBlock',
          page_id: page.page_id,
          payload: {
            block: {
              block_id: blockId,
              bbox,
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

  const handleDeleteBlock = async (blockIdOverride?: string) => {
    if (!project || !page) return;
    const blockId = blockIdOverride || activeBlockId;
    if (!blockId) {
      showNotice('info', t('manga_notice_no_block_changes'));
      return;
    }

    await withBusyAction('delete block', async () => {
      await DataService.applyMangaOps(project.project_id, [
        {
          type: 'RemoveTextBlock',
          page_id: page.page_id,
          block_id: blockId,
        },
      ]);
      await syncProjectState(project.project_id, page.page_id);
      showNotice('success', t('manga_notice_deleted_block'));
    });
  };

  const handleApplyBrushStroke = async (stroke: MangaBrushStrokePayload) => {
    if (!project || !page || stroke.points.length === 0) return;

    await withBusyAction(stroke.mode === 'restore' ? 'restore mask' : 'brush mask', async () => {
      if (stroke.mode === 'restore') {
        await DataService.applyMangaRestoreMaskStroke(project.project_id, page.page_id, stroke);
        setLayerControls((current) => ({
          ...current,
          restore: {
            ...current.restore,
            visible: true,
            opacity: Math.max(current.restore.opacity, 0.55),
          },
        }));
        setViewMode('rendered');
        await refreshCurrentPage(project.project_id, page.page_id);
        showNotice('success', t('manga_notice_restore_mask_painted'));
        return;
      }

      await DataService.applyMangaBrushMaskStroke(project.project_id, page.page_id, stroke);
      setLayerControls((current) => ({
        ...current,
        brush: {
          ...current.brush,
          visible: false,
        },
      }));
      setViewMode('rendered');
      await refreshCurrentPage(project.project_id, page.page_id);
      showNotice('success', t('manga_notice_brush_mask_painted'));
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

  const handleFocusRuntimeBox = (box: MangaCanvasRuntimeBox) => {
    if (!box.bbox?.length) return;
    setCanvasCommand((current) => ({
      kind: 'focusBox',
      token: current.token + 1,
      bbox: box.bbox,
      label: box.label,
    }));
  };

  const toggleLayer = (layer: MangaOverlayLayerKey) => {
    setLayerControls((current) => {
      const layerControl = current[layer] || createDefaultLayerControls(viewMode)[layer];
      return {
        ...current,
        [layer]: {
          ...layerControl,
          visible: !layerControl.visible,
        },
      };
    });
  };

  const setLayerOpacity = (layer: MangaOverlayLayerKey, opacity: number) => {
    setLayerControls((current) => {
      const layerControl = current[layer] || createDefaultLayerControls(viewMode)[layer];
      return {
        ...current,
        [layer]: {
          ...layerControl,
          opacity,
        },
      };
    });
  };

  useEffect(() => {
    setCanvasCommand((current) => ({ kind: 'fit', token: current.token + 1 }));
    setCanvasPointer(null);
  }, [page?.page_id, viewMode]);

  useEffect(() => {
    const defaults = createDefaultLayerControls(viewMode);
    setLayerControls((current) => ({
      ...defaults,
      sourceReference: current.sourceReference || defaults.sourceReference,
    }));
  }, [page?.page_id, viewMode]);

  useEffect(() => {
    if (!project || !projectPath) return;
    const params = new URLSearchParams();
    params.set('project_path', projectPath);
    if (selectedPageId) params.set('page_id', selectedPageId);
    params.set('view', viewMode);
    window.history.replaceState(null, '', `#/manga?${params.toString()}`);
  }, [project, projectPath, selectedPageId, viewMode]);

  useEffect(() => {
    void refreshOpenProjects();
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
        onSwitchProject={handleSwitchProject}
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
      <div className="mx-4 my-3 max-w-5xl rounded-xl border border-slate-800 bg-slate-950/78 p-3 shadow-2xl shadow-slate-950/30">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-100">{t('manga_project_entry_title')}</div>
            <div className="mt-1 text-xs text-slate-500">{t('manga_project_entry_desc')}</div>
          </div>
          {projectPath.trim() && (
            <button
              type="button"
              onClick={() => togglePinnedProjectPath(projectPath)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-semibold transition-colors ${
                isProjectPathPinned(projectPath)
                  ? 'border-amber-300/35 bg-amber-300/12 text-amber-100'
                  : 'border-slate-800 bg-slate-900/70 text-slate-400 hover:border-amber-300/45 hover:text-amber-100'
              }`}
            >
              <Star size={13} fill={isProjectPathPinned(projectPath) ? 'currentColor' : 'none'} />
              {isProjectPathPinned(projectPath) ? t('manga_unpin_project') : t('manga_pin_project')}
            </button>
          )}
        </div>

        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <div className="shrink-0 text-xs font-bold uppercase tracking-[0.18em] text-slate-500">{t('manga_project_path')}</div>
          <input
            type="text"
            value={projectPath}
            onChange={(event) => setProjectPath(event.target.value)}
            placeholder={t('manga_project_path_placeholder')}
            className="h-8 min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-900/80 px-3 text-xs text-slate-100 placeholder:text-slate-600 outline-none focus:border-primary"
          />
          <button
            onClick={() => void openProject()}
            disabled={isLoading}
            className="inline-flex h-8 items-center justify-center gap-2 rounded-lg bg-primary px-3 text-xs font-bold text-slate-900 disabled:opacity-60"
          >
            {isLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {t('manga_open_project')}
          </button>
        </div>
        {pinnedProjectPaths.length > 0 && (
          <div className="mt-3">
            <div className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-amber-200/80">{t('manga_pinned_projects')}</div>
            <div className="grid gap-2 md:grid-cols-2">
              {pinnedProjectPaths.map((path) => (
                <div key={path} className="flex min-w-0 items-center gap-2 rounded-lg border border-amber-300/20 bg-amber-300/10 px-2 py-1.5">
                  <button
                    type="button"
                    onClick={() => { setProjectPath(path); void openProject(path); }}
                    className="min-w-0 flex-1 text-left"
                    title={path}
                  >
                    <div className="truncate text-xs font-semibold text-amber-100">{compactProjectPath(path)}</div>
                    <div className="truncate text-[11px] text-amber-100/45">{path}</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => togglePinnedProjectPath(path)}
                    title={t('manga_unpin_project')}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-amber-100 hover:bg-amber-300/12"
                  >
                    <Star size={13} fill="currentColor" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
        {openProjects.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            <span className="uppercase tracking-[0.16em]">{t('manga_open_sessions')}</span>
            {openProjects.map((item) => (
              <span key={item.project_id} className="inline-flex max-w-80 items-center gap-1 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-2 py-1 text-cyan-100">
                <button
                  type="button"
                  onClick={() => { setProjectPath(item.project_path); void openProject(item.project_path); }}
                  className="min-w-0 truncate"
                  title={item.project_path}
                >
                  {item.name} · {t('manga_nav_page_count', item.page_count)}
                </button>
                <button
                  type="button"
                  onClick={() => togglePinnedProjectPath(item.project_path)}
                  title={isProjectPathPinned(item.project_path) ? t('manga_unpin_project') : t('manga_pin_project')}
                  className="shrink-0 rounded-full p-0.5 text-cyan-100/80 hover:bg-cyan-300/12"
                >
                  <Star size={11} fill={isProjectPathPinned(item.project_path) ? 'currentColor' : 'none'} />
                </button>
              </span>
            ))}
          </div>
        )}
        {unpinnedRecentProjectPaths.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            <span className="uppercase tracking-[0.16em]">{t('manga_recent_projects')}</span>
            {unpinnedRecentProjectPaths.map((path) => (
              <span key={path} className="inline-flex max-w-72 items-center gap-1 rounded-full border border-slate-800 bg-slate-900/70 px-2 py-1 text-slate-300 transition-colors hover:border-primary">
                <button
                  type="button"
                  onClick={() => { setProjectPath(path); void openProject(path); }}
                  className="min-w-0 truncate"
                  title={path}
                >
                  {compactProjectPath(path)}
                </button>
                <button
                  type="button"
                  onClick={() => togglePinnedProjectPath(path)}
                  title={t('manga_pin_project')}
                  className="shrink-0 rounded-full p-0.5 text-slate-500 hover:bg-slate-800 hover:text-amber-100"
                >
                  <Star size={11} />
                </button>
              </span>
            ))}
          </div>
        )}
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
          runtimeOverlay={runtimeOverlay}
          layerControls={layerControls}
          brushRadius={brushRadius}
          zoomCommand={canvasCommand}
          onSelectBlock={setActiveBlockId}
          onUpdateDraft={updateDraft}
          onCreateBlock={(bbox) => { void handleAddBlock(bbox); }}
          onDeleteBlock={(blockId) => { void handleDeleteBlock(blockId); }}
          onApplyBrushStroke={(stroke) => { void handleApplyBrushStroke(stroke); }}
          onViewportChange={setCanvasZoomPercent}
          onPointerChange={setCanvasPointer}
        />

        <aside className="w-[316px] shrink-0 border-l border-slate-900 bg-slate-950/88 overflow-y-auto 2xl:w-[336px]">
          <MangaInspector
            page={page}
            activeBlock={activeBlock}
            activeBlockDraft={activeBlockDraft}
            activeJob={activeJobSummary}
            engineCards={engineCards}
            runtimeValidation={runtimeValidation}
            runtimeValidationHistory={runtimeValidationHistory}
            runtimeValidationDiff={runtimeValidationDiff}
            activeRuntimeStage={selectedRuntimeStage?.stage || ''}
            busyAction={busyAction}
            hasProject={Boolean(project)}
            canCancelRuntimeValidation={Boolean(activeJob?.stage.startsWith('runtime_validation') && activeJob.status === 'running')}
            dirtyBlockCount={dirtyBlockCount}
            activeBlockDirty={activeBlockDirty}
            onSelectRuntimeStage={setActiveRuntimeStage}
            onLoadRuntimeValidationHistory={(runId) => { void handleLoadRuntimeValidationHistory(runId); }}
            onDiffRuntimeValidationHistory={(beforeRunId, afterRunId) => { void handleDiffRuntimeValidationHistory(beforeRunId, afterRunId); }}
            onDeleteRuntimeValidationHistory={(runId) => { void handleDeleteRuntimeValidationHistory(runId); }}
            onCancelRuntimeValidation={() => { void handleCancelRuntimeValidation(); }}
            onRetryRuntimeValidationStage={(stage) => { void handleRetryRuntimeValidationStage(stage); }}
            onValidateRuntime={() => { void handleValidateRuntime(); }}
            onDownloadModel={(modelId) => { void handleDownloadMangaModel(modelId); }}
            onFocusRuntimeBox={handleFocusRuntimeBox}
          />
          <MangaLayersPanel
            page={page}
            viewMode={viewMode}
            layerControls={layerControls}
            brushRadius={brushRadius}
            onToggleLayer={toggleLayer}
            onSetLayerOpacity={setLayerOpacity}
            onSetBrushRadius={setBrushRadius}
          />
          <MangaBlocksPanel
            page={page}
            blockDrafts={blockDrafts}
            activeBlockId={activeBlockId}
            busyAction={busyAction}
            hasProject={Boolean(project)}
            activeBlockDirty={activeBlockDirty}
            dirtyBlockCount={dirtyBlockCount}
            onSelectBlock={setActiveBlockId}
            onUpdateDraft={updateDraft}
            onSaveActiveBlock={() => { void applyActiveBlockChanges(); }}
            onSavePageChanges={() => { void applyDraftChanges(); }}
            onDeleteActiveBlock={() => { void handleDeleteBlock(); }}
          />
        </aside>
      </div>

      <MangaStatusBar leftText={statusLeftText} centerText={statusCenterText} rightText={statusRightText} />
    </div>
  );
};
