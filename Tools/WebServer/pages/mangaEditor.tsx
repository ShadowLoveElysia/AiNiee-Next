import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FileArchive, Layers3, Loader2, RefreshCw, Star, X } from 'lucide-react';
import { MangaBlocksPanel } from '../components/manga/mangaBlocksPanel';
import { MangaCanvas } from '../components/manga/mangaCanvas';
import { MangaInspector } from '../components/manga/mangaInspector';
import { MangaLayersPanel } from '../components/manga/mangaLayersPanel';
import { MangaModelManagerDialog } from '../components/manga/mangaModelManagerDialog';
import { MangaPageStrip } from '../components/manga/mangaPageStrip';
import { MangaStatusBar } from '../components/manga/mangaStatusBar';
import { MangaTopBar } from '../components/manga/mangaTopBar';
import { useI18n } from '../contexts/I18nContext';
import { MangaBlockDraft, MangaBrushStrokePayload, MangaCanvasCommand, MangaCanvasPointer, MangaCanvasRuntimeBox, MangaCanvasRuntimeOverlay, MangaEngineCard, MangaLayerControls, MangaOverlayLayerKey, MangaViewMode, translateMangaEnum } from '../components/manga/shared';
import { DataService } from '../services/DataService';
import { MangaExportFormat, MangaExportResult, MangaFontCatalogEntry, MangaJob, MangaModelManagerManifest, MangaOpenProjectSummary, MangaPageDetail, MangaProjectSummary, MangaPsdExportOptions, MangaRuntimeValidationDiffResult, MangaRuntimeValidationHistoryItem, MangaRuntimeValidationResult, MangaRuntimeValidationStage, MangaSceneSummary } from '../types/manga';

type NoticeTone = 'info' | 'success' | 'warning' | 'error';
type PsdExportScope = 'current' | 'selected' | 'all';

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

const PAGE_NEIGHBOR_PRELOAD_RADIUS = 2;
const PAGE_NEAR_PRELOAD_CONCURRENCY = 2;
const PAGE_BACKGROUND_PRELOAD_DELAY_MS = 700;

const buildPageCacheKey = (projectId: string, pageId: string) => `${projectId}:${pageId}`;

const buildPredictivePageOrder = (
  pages: MangaSceneSummary['pages'],
  pageId: string,
) => {
  const currentIndex = pages.findIndex((item) => item.page_id === pageId);
  if (currentIndex < 0) return { nearby: [] as string[], background: [] as string[] };

  const visited = new Set<string>([pageId]);
  const nearby: string[] = [];
  const background: string[] = [];
  const pushAt = (index: number, target: string[]) => {
    const nextPageId = pages[index]?.page_id || '';
    if (!nextPageId || visited.has(nextPageId)) return;
    visited.add(nextPageId);
    target.push(nextPageId);
  };

  for (let distance = 1; distance <= PAGE_NEIGHBOR_PRELOAD_RADIUS; distance += 1) {
    pushAt(currentIndex + distance, nearby);
    pushAt(currentIndex - distance, nearby);
  }
  for (let distance = PAGE_NEIGHBOR_PRELOAD_RADIUS + 1; distance < pages.length; distance += 1) {
    pushAt(currentIndex + distance, background);
    pushAt(currentIndex - distance, background);
  }

  return { nearby, background };
};

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

const formatQualityIssue = (
  issue: any,
  t: (key: string, ...args: any[]) => string,
) => {
  const key = String(issue?.message_key || '');
  if (key) {
    const args = Array.isArray(issue?.message_args) ? issue.message_args : [];
    const translated = t(key, ...args);
    if (translated !== key) return translated;
  }
  return String(issue?.message || issue?.code || '').trim();
};

const getQualityNoticeMessage = (
  job: MangaJob,
  t: (key: string, ...args: any[]) => string,
) => {
  const issues = Array.isArray(job.result?.quality_issues) ? job.result?.quality_issues : [];
  if (!issues.length) return '';
  const issueText = issues
    .map((issue) => formatQualityIssue(issue, t))
    .filter(Boolean)
    .slice(0, 3)
    .join('；');
  return issueText ? t('manga_notice_quality_gate_blocked', issueText) : '';
};

const getRuntimePreflightNoticeMessage = (
  job: MangaJob,
  t: (key: string, ...args: any[]) => string,
) => {
  const issues = Array.isArray(job.result?.runtime_preflight_issues) ? job.result?.runtime_preflight_issues : [];
  if (!issues.length) return '';
  const issueText = issues
    .map((issue) => formatQualityIssue(issue, t))
    .filter(Boolean)
    .slice(0, 3)
    .join('；');
  return issueText ? t('manga_runtime_preflight_failed_detail', issueText) : '';
};

const formatJobMessage = (
  job: MangaJob,
  t: (key: string, ...args: any[]) => string,
) => {
  const runtimePreflightMessage = getRuntimePreflightNoticeMessage(job, t);
  if (runtimePreflightMessage) return runtimePreflightMessage;

  const qualityMessage = getQualityNoticeMessage(job, t);
  if (qualityMessage) return qualityMessage;

  const finalBlockedPages = Number(job.result?.final_blocked_pages || 0);
  if (finalBlockedPages > 0) {
    return t('manga_notice_quality_gate_blocked_pages', finalBlockedPages);
  }

  const key = String(job.message_key || '');
  if (key) {
    const args = Array.isArray(job.message_args) ? job.message_args : [];
    const translated = t(key, ...args);
    if (translated !== key) return translated;
  }
  return String(job.message || '');
};

const isMangaModelDownloadJob = (job: MangaJob | null) => (
  Boolean(job?.stage && (
    job.stage.startsWith('model_download')
    || job.stage.startsWith('model_preset_download')
    || job.stage.startsWith('model_all_download')
  ))
);

const formatBytes = (value: number) => {
  if (!Number.isFinite(value) || value <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let nextValue = value;
  let unitIndex = 0;
  while (nextValue >= 1024 && unitIndex < units.length - 1) {
    nextValue /= 1024;
    unitIndex += 1;
  }
  return `${nextValue >= 10 || unitIndex === 0 ? nextValue.toFixed(0) : nextValue.toFixed(1)} ${units[unitIndex]}`;
};

const formatDownloadProgressMetric = (payload: Record<string, any>, fallbackProgress: number, t: (key: string, ...args: any[]) => string) => {
  const unit = String(payload.unit || '');
  const bytesDownloaded = Number(payload.bytes_downloaded || 0);
  const bytesTotal = Number(payload.bytes_total || 0);
  if (unit === 'files' && bytesTotal > 0) {
    return t('manga_model_download_items', bytesDownloaded, bytesTotal);
  }
  if (bytesTotal > 0) {
    return t('manga_model_download_bytes', formatBytes(bytesDownloaded), formatBytes(bytesTotal));
  }

  const itemIndex = Number(payload.item_index || 0);
  const itemCount = Number(payload.item_count || 0);
  if (itemIndex > 0 && itemCount > 0) {
    return t('manga_model_download_items', itemIndex, itemCount);
  }

  return `${Math.max(0, Math.min(100, Math.round(fallbackProgress || 0)))}%`;
};

const formatI18nPayload = (
  key: string | undefined,
  args: any[] | undefined,
  fallback: string,
  t: (key: string, ...args: any[]) => string,
) => {
  if (!key) return fallback;
  const translated = t(key, ...(Array.isArray(args) ? args : []));
  return translated !== key ? translated : fallback;
};

const getPageQualityNotice = (
  page: MangaPageDetail | null,
  t: (key: string, ...args: any[]) => string,
) => {
  if (!page?.quality_gate?.blocked_from_final) return '';
  const issues = Array.isArray(page.quality_gate.issues) ? page.quality_gate.issues : [];
  const issueText = issues
    .filter((issue) => issue.blocks_final)
    .map((issue) => formatQualityIssue(issue, t))
    .filter(Boolean)
    .slice(0, 3)
    .join('；');
  return issueText
    ? t('manga_quality_gate_draft_only_reason', issueText)
    : t('manga_quality_gate_draft_only');
};

const getExportResultMessage = (
  format: string,
  result: MangaExportResult,
  t: (key: string, ...args: any[]) => string,
) => {
  const formatLabel = format.toUpperCase();
  const blockedPages = Array.isArray(result.blocked_pages) ? result.blocked_pages : [];
  const firstIssue = blockedPages
    .flatMap((blockedPage) => Array.isArray(blockedPage.issues) ? blockedPage.issues : [])
    .map((issue) => formatQualityIssue(issue, t))
    .filter(Boolean)[0] || '';
  const backendMessage = formatI18nPayload(
    result.message_key,
    result.message_args,
    '',
    t,
  );

  if (format === 'psd') {
    const psdCount = Array.isArray(result.psd_paths) ? result.psd_paths.length : 0;
    const scriptCount = Array.isArray(result.script_paths) ? result.script_paths.length : 0;
    const missingFontCount = Array.isArray(result.missing_fonts) ? result.missing_fonts.length : 0;
    const warnings = Array.isArray(result.warnings) ? result.warnings.filter(Boolean) : [];
    const psdComplete = result.ok && result.complete !== false;
    const summary = t(
      psdComplete ? 'manga_notice_psd_export_summary' : 'manga_notice_psd_export_incomplete_summary',
      psdCount,
      scriptCount,
      result.layer_manifest_path || '',
    );
    const details = [
      backendMessage,
      missingFontCount > 0 ? t('manga_notice_psd_missing_fonts', missingFontCount) : '',
      warnings[0] ? t('manga_notice_psd_warning', warnings[0]) : '',
      result.photoshop?.available === false ? t('manga_notice_psd_photoshop_missing') : '',
    ].filter(Boolean);
    return details.length ? `${summary} ${details.join(' ')}` : summary;
  }

  if (result.ok) {
    const exportedMessage = t('manga_notice_exported_to', formatLabel, result.path || '');
    return backendMessage ? `${exportedMessage} ${backendMessage}` : exportedMessage;
  }

  if (blockedPages.length > 0 && firstIssue) {
    return t('manga_export_blocked_by_quality_gate_detail', blockedPages.length, firstIssue);
  }
  return backendMessage || t('manga_notice_export_no_file', formatLabel);
};

const ACTION_LABEL_KEYS: Record<string, string> = {
  'detect current page': 'manga_action_detect',
  'ocr current page': 'manga_action_ocr',
  'translate current page': 'manga_action_generate',
  'translate selected pages': 'manga_action_selected',
  'first pass selected pages': 'manga_action_first_pass',
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
  'export psd': 'manga_export_psd',
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
    || (draft.font_id || '') !== (block.style.font_id || '')
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
  page.layers.inpainted_url || page.layers.source_url
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
  const [loadingPageId, setLoadingPageId] = useState('');
  const selectedPageIdRef = useRef('');
  const pageLoadSeqRef = useRef(0);
  const activeProjectIdRef = useRef('');
  const scenePagesRef = useRef<MangaSceneSummary['pages']>([]);
  const pageCacheRef = useRef<Map<string, MangaPageDetail>>(new Map());
  const pageCacheEpochRef = useRef<Map<string, number>>(new Map());
  const pagePreloadInflightRef = useRef<Set<string>>(new Set());
  const pagePreloadSeqRef = useRef(0);
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
  const [fontCatalog, setFontCatalog] = useState<MangaFontCatalogEntry[]>([]);
  const [modelManager, setModelManager] = useState<MangaModelManagerManifest | null>(null);
  const [modelManagerLoading, setModelManagerLoading] = useState(false);
  const [psdExportOpen, setPsdExportOpen] = useState(false);
  const [psdExportScope, setPsdExportScope] = useState<PsdExportScope>('current');
  const [psdScriptOnly, setPsdScriptOnly] = useState(false);
  const [psdIncludeBlocked, setPsdIncludeBlocked] = useState(true);
  const [psdPackage, setPsdPackage] = useState(false);
  const [psdPhotoshopStatus, setPsdPhotoshopStatus] = useState<NonNullable<MangaExportResult['photoshop']> | null>(null);
  const [psdPhotoshopChecking, setPsdPhotoshopChecking] = useState(false);
  const [lastPsdExportResult, setLastPsdExportResult] = useState<MangaExportResult | null>(null);
  const [psdExportProgressOpen, setPsdExportProgressOpen] = useState(false);
  const [psdExportJob, setPsdExportJob] = useState<MangaJob | null>(null);
  const [psdExportCancelling, setPsdExportCancelling] = useState(false);
  const [modelManagerOpen, setModelManagerOpen] = useState(false);
  const [blockDrafts, setBlockDrafts] = useState<Record<string, MangaBlockDraft>>({});
  const [canvasCommand, setCanvasCommand] = useState<MangaCanvasCommand>({ kind: 'fit', token: 0 });
  const [canvasZoomPercent, setCanvasZoomPercent] = useState(100);
  const [canvasPointer, setCanvasPointer] = useState<MangaCanvasPointer | null>(null);
  const [layerControls, setLayerControls] = useState<MangaLayerControls>(createDefaultLayerControls('rendered'));
  const [brushRadius, setBrushRadius] = useState(24);

  const selectedCount = selectedPageIds.length || (selectedPageId ? 1 : 0);
  const psdScopePageCount = useMemo(() => {
    if (psdExportScope === 'all') return scene?.pages.length || project?.page_count || 0;
    if (psdExportScope === 'selected') return selectedPageIds.length;
    return selectedPageId ? 1 : 0;
  }, [project?.page_count, psdExportScope, scene?.pages.length, selectedPageId, selectedPageIds.length]);
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

    const readinessItems = Array.isArray(scene.runtime_readiness?.items) ? scene.runtime_readiness.items : [];
    const findReadiness = (stage: string, modelId: string) => readinessItems.find((item) => (
      String(item.stage || '') === stage && String(item.model_id || '') === modelId
    ));
    const buildPackageCard = (pkg: any, stage: string) => {
      const modelId = String(pkg?.model_id || '');
      const readiness = findReadiness(stage, modelId);
      return {
        modelId,
        label: String(pkg?.display_name || pkg?.model_id || t('manga_unknown_package')),
        repoId: String(pkg?.repo_id || ''),
        description: String(pkg?.description || ''),
        hardwareTier: String(pkg?.hardware_tier || ''),
        qualityTier: String(pkg?.quality_tier || ''),
        aliases: Array.isArray(pkg?.aliases) ? pkg.aliases.map(String) : [],
        recommendedFor: Array.isArray(pkg?.recommended_for) ? pkg.recommended_for.map(String) : [],
        cautions: Array.isArray(pkg?.cautions) ? pkg.cautions.map(String) : [],
        available: Boolean(pkg?.available),
        runtimeSupported: readiness ? Boolean(readiness.runtime_supported) : Boolean(pkg?.runtime_supported),
        runtimeEngineId: String(readiness?.runtime_engine_id || pkg?.runtime_engine_id || ''),
        storagePath: String(readiness?.storage_path || pkg?.runtime_assets_path || pkg?.snapshot_path || ''),
        readinessStatus: readiness?.status,
        readinessMessageKey: readiness?.message_key,
        readinessMessageArgs: readiness?.message_args,
        actionHintKey: readiness?.action_hint_key,
        actionHintArgs: readiness?.action_hint_args,
        missingModules: readiness?.missing_modules,
        missingAssetPaths: readiness?.missing_asset_paths,
      };
    };

    const ocrPackage = buildPackageCard(scene.engines.ocr.package, 'ocr');
    const detectorPackage = buildPackageCard(scene.engines.detect.detector_package, 'detect');
    const segmenterPackage = buildPackageCard(scene.engines.detect.segmenter_package, 'segment');
    const inpaintPackage = buildPackageCard(scene.engines.inpaint.package, 'inpaint');

    return [
      {
        label: t('manga_engine_ocr'),
        configured: scene.engines.ocr.configured_engine_id,
        runtime: scene.engines.ocr.runtime_engine_id,
        available: ocrPackage.available,
        packageLabel: scene.engines.ocr.package?.display_name || scene.engines.ocr.package?.repo_id || t('manga_unknown_package'),
        packages: [ocrPackage].filter((pkg) => pkg.modelId),
      },
      {
        label: t('manga_engine_detect'),
        configured: `${scene.engines.detect.configured_detector_id} / ${scene.engines.detect.configured_segmenter_id}`,
        runtime: `${scene.engines.detect.runtime_detector_id} / ${scene.engines.detect.runtime_segmenter_id}`,
        available: detectorPackage.available && segmenterPackage.available,
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
        available: inpaintPackage.available,
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
          message: formatJobMessage(activeJob, t),
        }
      : null
  ), [activeJob, t]);

  const modelDownloadProgressPayload = useMemo<Record<string, any>>(() => {
    const payload = activeJob?.result?.progress;
    return payload && typeof payload === 'object' && !Array.isArray(payload)
      ? payload as Record<string, any>
      : {};
  }, [activeJob]);
  const modelDownloadVisible = isMangaModelDownloadJob(activeJob);
  const modelDownloadRunning = activeJob?.status === 'running';
  const modelDownloadPercent = Math.max(0, Math.min(100, Number(activeJob?.progress || 0)));
  const modelDownloadStageLabel = activeJob ? formatStageLabel(activeJob.stage, t) : '';
  const modelDownloadMessage = activeJob ? formatJobMessage(activeJob, t) : '';
  const modelDownloadModelLabel = String(
    modelDownloadProgressPayload.display_name
    || modelDownloadProgressPayload.model_id
    || activeJob?.result?.display_name
    || activeJob?.result?.model_id
    || '',
  );
  const modelDownloadAssetLabel = String(modelDownloadProgressPayload.asset_id || modelDownloadProgressPayload.repo_id || '');
  const modelDownloadMetric = formatDownloadProgressMetric(modelDownloadProgressPayload, modelDownloadPercent, t);
  const modelDownloadModelIndex = Number(modelDownloadProgressPayload.model_index || 0);
  const modelDownloadModelCount = Number(modelDownloadProgressPayload.model_count || 0);
  const modelDownloadItemIndex = Number(modelDownloadProgressPayload.item_index || 0);
  const modelDownloadItemCount = Number(modelDownloadProgressPayload.item_count || 0);
  const modelDownloadDetailRows = [
    modelDownloadModelLabel
      ? {
          label: t('manga_model_download_current_model'),
          value: modelDownloadModelCount > 1 && modelDownloadModelIndex > 0
            ? t('manga_model_download_current_model_indexed', modelDownloadModelLabel, modelDownloadModelIndex, modelDownloadModelCount)
            : modelDownloadModelLabel,
        }
      : null,
    modelDownloadAssetLabel
      ? {
          label: t('manga_model_download_current_asset'),
          value: modelDownloadItemCount > 1 && modelDownloadItemIndex > 0
            ? t('manga_model_download_current_asset_indexed', modelDownloadAssetLabel, modelDownloadItemIndex, modelDownloadItemCount)
            : modelDownloadAssetLabel,
        }
      : null,
    modelDownloadProgressPayload.url
      ? {
          label: t('manga_model_download_source'),
          value: String(modelDownloadProgressPayload.url),
    }
      : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>;
  const modelDownloadProgressState = modelDownloadVisible
    ? {
        visible: true,
        running: modelDownloadRunning,
        failed: activeJob?.status === 'failed',
        progress: modelDownloadPercent,
        stageLabel: modelDownloadStageLabel,
        message: modelDownloadMessage,
        metric: modelDownloadMetric,
        detailRows: modelDownloadDetailRows,
        errorMessage: activeJob?.error_message || '',
      }
    : null;

  const modelManagerIssueCount = useMemo(() => {
    const configuredMissingCount = modelManager
      ? Number(modelManager.missing_count || modelManager.missing_model_ids?.length || 0)
      : engineCards
        .flatMap((card) => card.packages)
        .filter((pkg) => !pkg.available).length;
    const readinessIssueCount = scene?.runtime_readiness?.items?.filter((item) => {
      if (!item?.blocking) return false;
      return String(item.status || '') !== 'missing_model';
    }).length || 0;
    return configuredMissingCount + readinessIssueCount;
  }, [engineCards, modelManager, scene?.runtime_readiness?.items]);

  const pageQualityMessage = getPageQualityNotice(page, t);
  const pageQualityGate = page?.quality_gate || null;

  const statusLeftText = page
    ? t('manga_status_page_loaded', page.index, page.width, page.height, page.blocks.length, t(`manga_view_${viewMode}`), canvasZoomPercent)
    : loadingPageId
      ? t('manga_status_page_loading')
      : t('manga_status_no_page_loaded');

  const statusCenterText = canvasPointer
    ? t('manga_status_cursor', canvasPointer.x, canvasPointer.y, Math.round(canvasPointer.normalizedX * 100), Math.round(canvasPointer.normalizedY * 100))
    : t('manga_status_cursor_empty');

  const statusRightText = activeJobSummary
    ? `${activeJobSummary.stageLabel} · ${activeJobSummary.progress}% · ${translateMangaEnum('manga_state', activeJobSummary.status, t)}`
    : pageQualityGate?.blocked_from_final
      ? t('manga_quality_gate_status_right', pageQualityGate.issue_count || 0)
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

  useEffect(() => {
    selectedPageIdRef.current = selectedPageId;
  }, [selectedPageId]);

  useEffect(() => {
    scenePagesRef.current = scene?.pages || [];
  }, [scene?.pages]);

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
        font_id: block.style.font_id || '',
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
          font_id: '',
          font_family: '',
          font_size: 42,
          line_spacing: 1.2,
          fill: '#111111',
          stroke_color: '#ffffff',
          stroke_width: 0,
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

  const cachePageDetail = (projectId: string, detail: MangaPageDetail) => {
    if (activeProjectIdRef.current !== projectId) return;
    pageCacheRef.current.set(buildPageCacheKey(projectId, detail.page_id), detail);
  };

  const getCachedPageDetail = (projectId: string, pageId: string) => (
    activeProjectIdRef.current === projectId
      ? pageCacheRef.current.get(buildPageCacheKey(projectId, pageId)) || null
      : null
  );

  const invalidateCachedPage = (projectId: string, pageId: string) => {
    if (!projectId || !pageId) return;
    pageCacheRef.current.delete(buildPageCacheKey(projectId, pageId));
    pageCacheEpochRef.current.set(
      buildPageCacheKey(projectId, pageId),
      (pageCacheEpochRef.current.get(buildPageCacheKey(projectId, pageId)) || 0) + 1,
    );
  };

  const invalidateCachedPages = (projectId: string, pageIds: string[]) => {
    Array.from(new Set(pageIds.filter(Boolean))).forEach((pageId) => invalidateCachedPage(projectId, pageId));
  };

  const resetPagePreloadState = (projectId = '') => {
    activeProjectIdRef.current = projectId;
    pageCacheRef.current.clear();
    pageCacheEpochRef.current.clear();
    pagePreloadInflightRef.current.clear();
    pagePreloadSeqRef.current += 1;
  };

  const preloadPageCore = async (
    projectId: string,
    pageId: string,
    seq: number,
  ) => {
    if (!pageId || activeProjectIdRef.current !== projectId) return;
    const cacheKey = buildPageCacheKey(projectId, pageId);
    if (pageCacheRef.current.has(cacheKey) || pagePreloadInflightRef.current.has(cacheKey)) return;
    const cacheEpoch = pageCacheEpochRef.current.get(cacheKey) || 0;
    pagePreloadInflightRef.current.add(cacheKey);
    try {
      const detail = await DataService.getMangaPage(projectId, pageId, { diagnostics: false });
      if (
        activeProjectIdRef.current !== projectId
        || pagePreloadSeqRef.current !== seq
        || (pageCacheEpochRef.current.get(cacheKey) || 0) !== cacheEpoch
      ) return;
      cachePageDetail(projectId, detail);
    } catch {
      // Predictive page loading must never block the active editor path.
    } finally {
      pagePreloadInflightRef.current.delete(cacheKey);
    }
  };

  const schedulePagePreload = (projectId: string, pageId: string) => {
    const pages = scenePagesRef.current;
    if (!projectId || !pageId || pages.length === 0) return;
    const { nearby, background } = buildPredictivePageOrder(pages, pageId);
    pagePreloadSeqRef.current += 1;
    const seq = pagePreloadSeqRef.current;

    const run = async () => {
      for (let start = 0; start < nearby.length; start += PAGE_NEAR_PRELOAD_CONCURRENCY) {
        if (pagePreloadSeqRef.current !== seq || activeProjectIdRef.current !== projectId) return;
        await Promise.all(
          nearby.slice(start, start + PAGE_NEAR_PRELOAD_CONCURRENCY)
            .map((nextPageId) => preloadPageCore(projectId, nextPageId, seq)),
        );
      }

      for (const nextPageId of background) {
        if (pagePreloadSeqRef.current !== seq || activeProjectIdRef.current !== projectId) return;
        await delay(PAGE_BACKGROUND_PRELOAD_DELAY_MS);
        await preloadPageCore(projectId, nextPageId, seq);
      }
    };

    void run();
  };

  const refreshPageDiagnostics = async (projectId: string, pageId: string) => {
    try {
      const qualityGate = await DataService.getMangaPageQuality(projectId, pageId);
      if (activeProjectIdRef.current !== projectId || selectedPageIdRef.current !== pageId) return;
      setPage((current) => (
        current?.page_id === pageId
          ? { ...current, quality_gate: qualityGate }
          : current
      ));
    } catch {
      // Quality diagnostics are non-blocking; the editable page core is still usable.
    }
    try {
      const latestValidation = await DataService.getLatestMangaRuntimeValidation(projectId, pageId);
      if (activeProjectIdRef.current !== projectId || selectedPageIdRef.current !== pageId) return;
      setRuntimeValidation(latestValidation);
      setActiveRuntimeStage(latestValidation?.stages.find((stage) => !stage.ok)?.stage || latestValidation?.stages[0]?.stage || '');
    } catch {
      if (activeProjectIdRef.current !== projectId || selectedPageIdRef.current !== pageId) return;
      setRuntimeValidation(null);
      setActiveRuntimeStage('');
    }
    try {
      const history = await DataService.listMangaRuntimeValidationHistory(projectId, pageId);
      if (activeProjectIdRef.current !== projectId || selectedPageIdRef.current !== pageId) return;
      setRuntimeValidationHistory(history);
    } catch {
      if (activeProjectIdRef.current !== projectId || selectedPageIdRef.current !== pageId) return;
      setRuntimeValidationHistory([]);
    }
  };

  const loadPage = async (projectId: string, pageId: string) => {
    if (!pageId) return;
    const loadSeq = pageLoadSeqRef.current + 1;
    pageLoadSeqRef.current = loadSeq;
    selectedPageIdRef.current = pageId;
    setSelectedPageId(pageId);
    setRuntimeValidation(null);
    setRuntimeValidationDiff(null);
    setRuntimeValidationHistory([]);
    setActiveRuntimeStage('');
    setScene((current) => (current ? { ...current, current_page_id: pageId } : current));

    const cachedDetail = getCachedPageDetail(projectId, pageId);
    if (cachedDetail) {
      setLoadingPageId('');
      setPage(cachedDetail);
      setDraftsFromPage(cachedDetail);
      void refreshPageDiagnostics(projectId, pageId);
      schedulePagePreload(projectId, pageId);
      return;
    }

    setLoadingPageId(pageId);
    setPage((current) => (current?.page_id === pageId ? current : null));
    setBlockDrafts({});
    setActiveBlockId('');
    try {
      const detail = await DataService.getMangaPage(projectId, pageId, { diagnostics: false });
      if (pageLoadSeqRef.current !== loadSeq || activeProjectIdRef.current !== projectId) return;
      cachePageDetail(projectId, detail);
      setPage(detail);
      setLoadingPageId((current) => (current === pageId ? '' : current));
      setDraftsFromPage(detail);
      void refreshPageDiagnostics(projectId, pageId);
      schedulePagePreload(projectId, pageId);
    } finally {
      setLoadingPageId((current) => (current === pageId && pageLoadSeqRef.current === loadSeq ? '' : current));
    }
  };

  const refreshScene = async (projectId: string) => {
    const sceneSummary = await DataService.getMangaScene(projectId, { runtime: false });
    scenePagesRef.current = sceneSummary.pages;
    setScene(sceneSummary);
    return sceneSummary;
  };

  const loadMangaModelManager = async (force = false) => {
    if (modelManager && !force) return modelManager;
    setModelManagerLoading(true);
    try {
      const manifest = await DataService.getMangaModelManager();
      setModelManager(manifest);
      return manifest;
    } finally {
      setModelManagerLoading(false);
    }
  };

  const refreshFontCatalog = async (projectId?: string) => {
    try {
      setFontCatalog(await DataService.listMangaFonts(projectId));
    } catch {
      try {
        setFontCatalog(await DataService.listMangaFonts());
      } catch {
        setFontCatalog([]);
      }
    }
  };

  const refreshCurrentPage = async (projectId: string, pageId?: string) => {
    const targetPageId = pageId || selectedPageId || scene?.current_page_id || '';
    if (!targetPageId) return;
    invalidateCachedPage(projectId, targetPageId);
    await loadPage(projectId, targetPageId);
  };

  const hydrateProjectRuntimeState = async (projectId: string, refresh = false) => {
    try {
      const [runtimeStatus, modelManifest] = await Promise.all([
        DataService.getMangaRuntimeStatus(projectId, refresh),
        DataService.getMangaModelManager(),
      ]);
      setModelManager(modelManifest);
      setScene((current) => (
        current
          ? {
              ...current,
              engines: runtimeStatus.engines,
              runtime_readiness: runtimeStatus.runtime_readiness,
            }
          : current
      ));
    } catch {
      // The editor can continue with the lightweight project manifest; page detail actions will surface concrete errors.
    }
  };

  useEffect(() => {
    void loadMangaModelManager();
  }, []);

  useEffect(() => {
    if (!project?.project_id) return undefined;
    const refreshRuntimeOnFocus = () => {
      void hydrateProjectRuntimeState(project.project_id, true);
    };
    window.addEventListener('focus', refreshRuntimeOnFocus);
    return () => {
      window.removeEventListener('focus', refreshRuntimeOnFocus);
    };
  }, [project?.project_id]);

  const syncProjectState = async (projectId: string, preferredPageId?: string) => {
      const nextScene = await refreshScene(projectId);
      const nextPageId = preferredPageId || nextScene.current_page_id || nextScene.pages[0]?.page_id || '';
      if (nextPageId) {
        invalidateCachedPage(projectId, nextPageId);
        await loadPage(projectId, nextPageId);
      } else {
        setPage(null);
        setSelectedPageId('');
        setLoadingPageId('');
        setActiveBlockId('');
      }
  };

  const waitForJob = async (
    projectId: string,
    initialJob: MangaJob,
    options?: { maxAttempts?: number; intervalMs?: number },
  ) => {
    setActiveJob(initialJob);
    if (isMangaModelDownloadJob(initialJob)) {
      setModelManagerOpen(true);
    }
    if (!initialJob.job_id || ['completed', 'failed', 'cancelled'].includes(initialJob.status)) {
      return initialJob;
    }

    let latest = initialJob;
    const maxAttempts = options?.maxAttempts ?? 90;
    const intervalMs = options?.intervalMs ?? 500;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      await delay(intervalMs);
      latest = projectId
        ? await DataService.getMangaJob(projectId, initialJob.job_id)
        : await DataService.getGlobalMangaJob(initialJob.job_id);
      setActiveJob(latest);
      if (isMangaModelDownloadJob(latest)) {
        setModelManagerOpen(true);
      }
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
      if ((draft.font_id || '') !== (block.style.font_id || '')) patch['style.font_id'] = draft.font_id || '';
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
      resetPagePreloadState(opened.project_id);
      const sceneSummary = opened.scene || await DataService.getMangaScene(opened.project_id, { quality: false, runtime: false });
      scenePagesRef.current = sceneSummary.pages;
      setProject(opened);
      setScene(sceneSummary);
      setSelectedPageIds([]);
      setActiveJob(null);
      setActiveBlockId('');
      setPage(null);
      setLoadingPageId('');
      setRuntimeValidation(null);
      setRuntimeValidationDiff(null);
      setRuntimeValidationHistory([]);
      setActiveRuntimeStage('');
      setBlockDrafts({});
      setRecentProjectPaths(rememberRecentProjectPath(nextPath));
      void refreshFontCatalog(opened.project_id);

      const requestedPageId = getInitialPageId();
      const firstPageId = (
        requestedPageId && sceneSummary.pages.some((item) => item.page_id === requestedPageId)
          ? requestedPageId
          : sceneSummary.current_page_id || sceneSummary.pages[0]?.page_id || ''
      );
      if (firstPageId) {
        setSelectedPageId(firstPageId);
        setScene((current) => (current ? { ...current, current_page_id: firstPageId } : current));
        void loadPage(opened.project_id, firstPageId);
      } else {
        setPage(null);
        setSelectedPageId('');
        setLoadingPageId('');
      }
      void hydrateProjectRuntimeState(opened.project_id, true);
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
      const targetPageId = selectedPageId;
      invalidateCachedPage(project.project_id, targetPageId);
      const job = await runner(project.project_id, targetPageId);
      const settled = await waitForJob(project.project_id, job);
      invalidateCachedPage(project.project_id, targetPageId);
      await syncProjectState(project.project_id, targetPageId);
      if (options?.nextViewMode) {
        setViewMode(options.nextViewMode);
      }
      showNotice(settled.status === 'completed' ? 'success' : 'warning', formatJobMessage(settled, t));
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
    if (!modelId) return;

    await withBusyAction(`download model:${modelId}`, async () => {
      const projectId = project?.project_id || '';
      const job = await DataService.startMangaModelDownload(modelId, projectId);
      const settled = await waitForJob(projectId, job, { maxAttempts: 7200, intervalMs: 500 });
      const result = settled.result || {};
      const modelLabel = String(result.display_name || result.model_id || modelId);
      showNotice(
        settled.status === 'completed' ? 'success' : 'warning',
        settled.status === 'completed'
          ? t('manga_notice_model_prepared', modelLabel)
          : settled.error_message || settled.message || t('manga_notice_model_prepare_warning', modelLabel),
      );
      await loadMangaModelManager(true);
      if (projectId) {
        await refreshScene(projectId);
        await hydrateProjectRuntimeState(projectId, true);
      }
      if (settled.status === 'completed' && runtimeValidation) {
        showNotice('info', t('manga_notice_model_ready_rerun_runtime'));
      }
    });
  };

  const handleDownloadMangaModelPreset = async (presetId: string) => {
    if (!presetId) return;

    await withBusyAction(`download model preset:${presetId}`, async () => {
      const projectId = project?.project_id || '';
      const job = await DataService.startMangaModelPresetDownload(presetId, projectId);
      const settled = await waitForJob(projectId, job, { maxAttempts: 7200, intervalMs: 500 });
      const result = settled.result || {};
      const preset = (result.preset || {}) as Record<string, any>;
      const presetLabel = String(preset.display_name || preset.preset_id || presetId);
      showNotice(
        settled.status === 'completed' ? 'success' : 'warning',
        settled.status === 'completed'
          ? t('manga_notice_model_preset_prepared', presetLabel)
          : settled.error_message || settled.message || t('manga_notice_model_prepare_warning', presetLabel),
      );
      await loadMangaModelManager(true);
      if (projectId) {
        await refreshScene(projectId);
        await hydrateProjectRuntimeState(projectId, true);
      }
      if (settled.status === 'completed' && runtimeValidation) {
        showNotice('info', t('manga_notice_model_ready_rerun_runtime'));
      }
    });
  };

  const handleDownloadAllMangaModels = async () => {
    await withBusyAction('download all models', async () => {
      const projectId = project?.project_id || '';
      const job = await DataService.startMangaAllModelsDownload(projectId);
      const settled = await waitForJob(projectId, job, { maxAttempts: 7200, intervalMs: 500 });
      const result = settled.result || {};
      const missingCount = Number(result.missing_count || 0);
      showNotice(
        settled.status === 'completed' && missingCount === 0 ? 'success' : 'warning',
        settled.status === 'completed'
          ? (
              missingCount > 0
                ? t('manga_notice_all_models_prepare_warning', missingCount)
                : t('manga_notice_all_models_prepared')
            )
          : settled.error_message || settled.message || t('manga_notice_model_prepare_warning', t('manga_model_download_all')),
      );
      await loadMangaModelManager(true);
      if (projectId) {
        await refreshScene(projectId);
        await hydrateProjectRuntimeState(projectId, true);
      }
      if (settled.status === 'completed' && runtimeValidation) {
        showNotice('info', t('manga_notice_model_ready_rerun_runtime'));
      }
    });
  };

  const handleSelectMangaEngine = async (configKey: string, modelId: string) => {
    if (!project || !configKey || !modelId) return;

    await withBusyAction(`select manga engine:${configKey}`, async () => {
      const updated = await DataService.updateMangaProjectConfig(project.project_id, { [configKey]: modelId });
      setProject((current) => (
        current
          ? {
              ...current,
              task_config: {
                ...(current.task_config || {}),
                ...(updated.task_config || {}),
              },
            }
          : current
      ));
      setScene((current) => (
        current
          ? {
              ...current,
              engines: updated.engines,
              runtime_readiness: updated.runtime_readiness,
            }
          : current
      ));
      showNotice('success', t('manga_notice_engine_config_saved', modelId));
      if (runtimeValidation) {
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
      invalidateCachedPages(project.project_id, pageIds);
      const job = await DataService.translateSelectedMangaPages(project.project_id, pageIds);
      const settled = await waitForJob(project.project_id, job);
      invalidateCachedPages(project.project_id, pageIds);
      await syncProjectState(project.project_id, selectedPageId || pageIds[0]);
      setViewMode('overlay');
      showNotice(settled.status === 'completed' ? 'success' : 'warning', formatJobMessage(settled, t));
    });
  };

  const handleFirstPassSelectedPages = async () => {
    if (!project) return;

    const pageIds = selectedPageIds.length > 0 ? selectedPageIds : (selectedPageId ? [selectedPageId] : []);
    if (pageIds.length === 0) {
      showNotice('warning', t('manga_notice_select_page_for_batch'));
      return;
    }

    await withBusyAction('first pass selected pages', async () => {
      invalidateCachedPages(project.project_id, pageIds);
      const job = await DataService.translateSelectedMangaPages(project.project_id, pageIds, {
        autoInpaint: true,
        autoRender: true,
      });
      const settled = await waitForJob(project.project_id, job);
      invalidateCachedPages(project.project_id, pageIds);
      await syncProjectState(project.project_id, selectedPageId || pageIds[0]);
      setViewMode('rendered');
      const settledMessage = formatJobMessage(settled, t);
      const qualityMessage = getQualityNoticeMessage(settled, t);
      const finalBlockedPages = Number(settled.result?.final_blocked_pages || 0);
      const finalBlockedMessage = finalBlockedPages > 0
        ? t('manga_notice_quality_gate_blocked_pages', finalBlockedPages)
        : '';
      const completedWithWarnings = (
        finalBlockedPages > 0
        || /warning|failed|need review|blocked/i.test(String(settled.message || ''))
        || !!qualityMessage
      );
      showNotice(
        settled.status === 'completed' && !completedWithWarnings ? 'success' : 'warning',
        settled.status === 'completed'
          ? (
              completedWithWarnings
                ? `${t('manga_notice_first_pass_finished', pageIds.length)} ${qualityMessage || finalBlockedMessage || settledMessage}`.trim()
                : t('manga_notice_first_pass_finished', pageIds.length)
            )
          : settledMessage,
      );
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
      invalidateCachedPages(project.project_id, pageIds);
      const job = await DataService.planSelectedMangaPages(project.project_id, pageIds);
      const settled = await waitForJob(project.project_id, job);
      invalidateCachedPages(project.project_id, pageIds);
      await syncProjectState(project.project_id, selectedPageId || pageIds[0]);
      setViewMode('overlay');
      showNotice(settled.status === 'completed' ? 'success' : 'warning', formatJobMessage(settled, t));
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
    resetPagePreloadState('');
    setProject(null);
    setScene(null);
    setPage(null);
    setSelectedPageId('');
    setLoadingPageId('');
    setSelectedPageIds([]);
    setActiveBlockId('');
    setBlockDrafts({});
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
      resetPagePreloadState(project.project_id);
      await syncProjectState(project.project_id, page.page_id);
      showNotice(result.ok ? 'success' : 'warning', result.message || (result.ok ? t('manga_notice_undo_applied') : t('manga_notice_nothing_to_undo')));
    });
  };

  const handleRedo = async () => {
    if (!project || !page) return;

    await withBusyAction('redo', async () => {
      const result = await DataService.redoMangaOps(project.project_id);
      resetPagePreloadState(project.project_id);
      await syncProjectState(project.project_id, page.page_id);
      showNotice(result.ok ? 'success' : 'warning', result.message || (result.ok ? t('manga_notice_redo_applied') : t('manga_notice_nothing_to_redo')));
    });
  };

  const refreshPsdPhotoshopStatus = async () => {
    setPsdPhotoshopChecking(true);
    try {
      const status = await DataService.getMangaPsdPhotoshopStatus();
      setPsdPhotoshopStatus(status);
      if (!status.available) setPsdScriptOnly(true);
    } catch (_error) {
      setPsdPhotoshopStatus({ available: false, message: t('manga_psd_photoshop_status_error') });
      setPsdScriptOnly(true);
    } finally {
      setPsdPhotoshopChecking(false);
    }
  };

  const openPsdExportDialog = () => {
    if (!project) return;
    setPsdExportScope(selectedPageIds.length > 0 ? 'selected' : (selectedPageId ? 'current' : 'all'));
    setPsdScriptOnly(false);
    setPsdExportOpen(true);
    void refreshPsdPhotoshopStatus();
  };

  const getPsdExportPageIds = (scope: PsdExportScope) => {
    if (scope === 'all') return [];
    if (scope === 'selected') return selectedPageIds;
    return selectedPageId ? [selectedPageId] : [];
  };

  const handlePsdExportFromDialog = async () => {
    if (!project) return;
    const pageIds = getPsdExportPageIds(psdExportScope);
    if (psdExportScope !== 'all' && pageIds.length === 0) {
      showNotice('warning', t('manga_notice_psd_select_page_scope'));
      return;
    }
    setPsdExportOpen(false);
    const psdOptions: MangaPsdExportOptions = {
      page_ids: pageIds,
      script_only: psdScriptOnly || psdPhotoshopStatus?.available === false,
      include_blocked: psdIncludeBlocked,
      package: psdPackage,
    };

    setPsdExportCancelling(false);
    setPsdExportProgressOpen(true);
    setPsdExportJob({
      job_id: '',
      stage: 'psd_export_preparing',
      status: 'running',
      progress: 0,
      message: t('manga_psd_export_saving_drafts'),
      result: {},
    });

    await withBusyAction('export psd', async () => {
      let latestPsdJob: MangaJob | null = null;
      try {
        await applyDraftChanges(true);
        setPsdExportJob((current) => ({
          job_id: current?.job_id || '',
          stage: 'psd_export_starting',
          status: 'running',
          progress: Math.max(1, Number(current?.progress || 0)),
          message: t('manga_psd_export_starting'),
          result: current?.result || {},
        }));

        const initialJob = await DataService.startMangaPsdExport(project.project_id, psdOptions);
        latestPsdJob = initialJob;
        setPsdExportJob(initialJob);
        setActiveJob(initialJob);

        let latest = initialJob;
        while (!['completed', 'failed', 'cancelled'].includes(latest.status)) {
          await delay(700);
          latest = await DataService.getMangaJob(project.project_id, initialJob.job_id);
          latestPsdJob = latest;
          setPsdExportJob(latest);
          setActiveJob(latest);
        }

        if (latest.status === 'completed' && latest.result) {
          setLastPsdExportResult(latest.result as MangaExportResult);
        }
        setPsdExportCancelling(false);
        setPsdExportJob(latest);
      } catch (err: any) {
        const message = err.message || t('manga_psd_export_failed');
        const failedJob: MangaJob = {
          job_id: latestPsdJob?.job_id || 'psd_export_failed_local',
          stage: 'psd_export_failed',
          status: 'failed',
          progress: Math.max(0, Math.min(100, Number(latestPsdJob?.progress || 0))),
          message,
          error_message: message,
          result: latestPsdJob?.result || {},
        };
        setPsdExportCancelling(false);
        setPsdExportJob(failedJob);
        setActiveJob(failedJob);
        throw err;
      }
    });
  };

  const handleCancelPsdExport = async () => {
    if (!project || !psdExportJob || psdExportJob.status !== 'running' || !psdExportJob.job_id) return;
    setPsdExportCancelling(true);
    try {
      const job = await DataService.stopMangaPsdExport(project.project_id);
      setPsdExportJob(job);
      setActiveJob(job);
    } catch (err: any) {
      setError(err.message || t('manga_psd_export_cancel_failed'));
    }
  };

  const handleExport = async (format: MangaExportFormat, options: MangaPsdExportOptions = {}) => {
    if (!project) return;

    await withBusyAction(`export ${format}`, async () => {
      const psdOptions: MangaPsdExportOptions = { ...options };
      if (format === 'psd') {
        const photoshopStatus = await DataService.getMangaPsdPhotoshopStatus();
        psdOptions.script_only = Boolean(psdOptions.script_only) || !photoshopStatus.available;
        if (!photoshopStatus.available) {
          showNotice('info', t('manga_notice_psd_photoshop_missing'));
        }
      }
      await applyDraftChanges(true);
      const result = await DataService.exportMangaProject(project.project_id, format, psdOptions);
      if (format === 'psd') setLastPsdExportResult(result);
      showNotice(
        result.ok ? 'success' : 'warning',
        getExportResultMessage(format, result, t),
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
    window.history.replaceState(null, '', `#/manga-editor?${params.toString()}`);
  }, [project, projectPath, selectedPageId, viewMode]);

  useEffect(() => {
    void refreshOpenProjects();
    void refreshFontCatalog();
    if (projectPath) {
      void openProject(projectPath);
    }
    // Run once on initial mount; hash parsing already seeded projectPath.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const psdEffectiveScriptOnly = psdScriptOnly || psdPhotoshopStatus?.available === false;
  const psdPhotoshopStatusText = psdPhotoshopChecking
    ? t('manga_psd_photoshop_status_checking')
    : psdPhotoshopStatus?.available
      ? t('manga_psd_photoshop_status_ready', psdPhotoshopStatus.executable_path || psdPhotoshopStatus.source || '')
      : t('manga_psd_photoshop_status_missing');
  const psdExportProgress = Math.max(0, Math.min(100, Number(psdExportJob?.progress || 0)));
  const psdExportRunning = psdExportJob?.status === 'running';
  const psdExportResultPayload = (psdExportJob?.result || {}) as Record<string, any>;
  const psdExportProgressPayload = (
    psdExportResultPayload.progress && typeof psdExportResultPayload.progress === 'object'
      ? psdExportResultPayload.progress
      : psdExportResultPayload
  ) as Record<string, any>;
  const psdExportProgressStage = String(psdExportProgressPayload.stage || psdExportJob?.stage || '');
  const psdExportProgressPageNumber = Number(psdExportProgressPayload.page_number || 0);
  const psdExportProgressPageCount = Number(psdExportProgressPayload.page_count || 0);
  const psdExportOutputKind = String(psdExportProgressPayload.output_kind || (psdEffectiveScriptOnly ? 'jsx' : 'psd')).toUpperCase();
  const psdExportOutputCount = Number(psdExportProgressPayload.output_count || 0);
  const psdExportOutputTargetCount = Number(psdExportProgressPayload.output_target_count || psdExportProgressPageCount || psdScopePageCount || 0);
  const psdExportOutputFailedCount = Number(psdExportProgressPayload.output_failed_count || 0);
  const psdExportElapsedSeconds = Number(psdExportProgressPayload.elapsed_seconds || 0);
  const psdExportPsdDetected = Boolean(psdExportProgressPayload.psd_detected);
  const psdExportStableCheckCount = Number(psdExportProgressPayload.stable_check_count || 0);
  const psdExportStableCheckTarget = Number(psdExportProgressPayload.stable_check_target || 0);
  const psdExportOutputProgressText = psdExportOutputTargetCount > 0
    ? t('manga_psd_export_generated_progress', psdExportOutputCount, psdExportOutputTargetCount, psdExportOutputKind)
    : '';
  const psdExportAttemptDetail = psdExportProgressPageNumber && psdExportProgressPageCount
    ? (
        psdExportOutputFailedCount > 0
          ? t('manga_psd_export_attempt_detail_with_failed', psdExportProgressPageNumber, psdExportProgressPageCount, psdExportOutputFailedCount)
          : t('manga_psd_export_attempt_detail', psdExportProgressPageNumber, psdExportProgressPageCount)
      )
    : '';
  const psdExportProgressMetric = psdExportOutputTargetCount > 0
    ? `${psdExportOutputCount}/${psdExportOutputTargetCount} · ${psdExportProgress}%`
    : `${psdExportProgress}%`;
  const psdExportActualComplete = psdExportJob?.status === 'completed' && psdExportProgressPayload.complete !== false;
  const psdExportActualIncomplete = psdExportProgressPayload.complete === false || psdExportProgressStage === 'psd_export_incomplete';
  const psdExportProgressMessage = psdExportActualComplete
    ? t('manga_psd_export_completed')
    : psdExportJob?.status === 'cancelled'
      ? t('manga_psd_export_cancelled')
      : psdExportActualIncomplete
        ? t('manga_psd_export_incomplete')
      : psdExportJob?.status === 'failed'
        ? (psdExportJob.error_message || t('manga_psd_export_failed'))
        : (psdExportCancelling || psdExportJob?.cancel_requested)
          ? t('manga_psd_export_cancelling')
          : psdExportProgressStage === 'psd_export_preparing'
            ? t('manga_psd_export_saving_drafts')
            : psdExportProgressStage === 'psd_export_starting'
              ? t('manga_psd_export_starting')
              : psdExportProgressStage === 'psd_export_photoshop'
                ? (psdExportOutputProgressText || t('manga_psd_export_running'))
                : psdExportOutputProgressText
                  ? psdExportOutputProgressText
                  : (psdExportJob?.message || t('manga_psd_export_running'));
  const psdExportProgressDetail = psdExportActualComplete
    ? t('manga_psd_export_completed')
    : psdExportActualIncomplete
      ? [
          psdExportOutputProgressText,
          psdExportAttemptDetail,
        ].filter(Boolean).join(' · ')
    : psdExportJob?.status === 'failed'
      ? (psdExportJob.error_message || psdExportJob.message || t('manga_psd_export_failed'))
      : psdExportJob?.status === 'cancelled'
        ? t('manga_psd_export_cancelled')
        : psdExportProgressStage === 'psd_export_photoshop'
          ? [
              psdExportPsdDetected && psdExportStableCheckTarget > 0
                ? t('manga_psd_export_verifying_psd', psdExportStableCheckCount, psdExportStableCheckTarget)
                : t('manga_psd_export_waiting_for_psd', psdExportElapsedSeconds),
              psdExportAttemptDetail,
            ].filter(Boolean).join(' · ')
          : psdExportAttemptDetail
            ? [
              psdExportAttemptDetail,
              psdExportOutputProgressText,
            ].filter(Boolean).join(' · ')
            : (psdExportJob?.message || t('manga_psd_export_waiting'));

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
        onFirstPassSelected={() => { void handleFirstPassSelectedPages(); }}
        onPlanSelected={() => { void handlePlanSelectedPages(); }}
        onInpaint={() => { void handleInpaintPage(); }}
        onRender={() => { void handleRenderPage(); }}
        onValidateRuntime={() => { void handleValidateRuntime(); }}
        onAddBlock={() => { void handleAddBlock(); }}
        onUndo={() => { void handleUndo(); }}
        onRedo={() => { void handleRedo(); }}
        onSave={() => { void handleSaveProject(); }}
        onOpenModelManager={() => {
          setModelManagerOpen(true);
          void loadMangaModelManager();
        }}
        modelManagerIssueCount={modelManagerIssueCount}
        onExportPdf={() => { void handleExport('pdf'); }}
        onExportCbz={() => { void handleExport('cbz'); }}
        onExportEpub={() => { void handleExport('epub'); }}
        onExportZip={() => { void handleExport('zip'); }}
        onExportRar={() => { void handleExport('rar'); }}
        onExportPsd={openPsdExportDialog}
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

      {lastPsdExportResult && (
        <div className="mx-4 mt-3 rounded-lg border border-cyan-300/20 bg-cyan-300/10 px-4 py-3 text-sm text-cyan-100">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 font-bold">
              <Layers3 size={15} />
              {t('manga_psd_result_title')}
            </div>
            <button
              type="button"
              onClick={() => setLastPsdExportResult(null)}
              title={t('manga_psd_result_close')}
              className="flex h-7 w-7 items-center justify-center rounded-md text-cyan-100/70 transition-colors hover:bg-cyan-300/12 hover:text-cyan-50"
            >
              <X size={14} />
            </button>
          </div>
          <div className="mt-2 grid gap-2 text-xs text-cyan-50/80 lg:grid-cols-2">
            <div>{t('manga_psd_result_psd_count', lastPsdExportResult.psd_paths?.length || 0)}</div>
            <div>{t('manga_psd_result_jsx_count', lastPsdExportResult.script_paths?.length || 0)}</div>
            {lastPsdExportResult.path && <div className="truncate" title={lastPsdExportResult.path}>{t('manga_psd_result_package', lastPsdExportResult.path)}</div>}
            {lastPsdExportResult.layer_manifest_path && <div className="truncate" title={lastPsdExportResult.layer_manifest_path}>{t('manga_psd_result_manifest', lastPsdExportResult.layer_manifest_path)}</div>}
            {lastPsdExportResult.photoshop?.source && <div className="truncate">{t('manga_psd_result_photoshop', lastPsdExportResult.photoshop.source)}</div>}
            {(lastPsdExportResult.missing_fonts?.length || 0) > 0 && (
              <div className="truncate" title={(lastPsdExportResult.missing_fonts || []).map((font) => font.requested).join(', ')}>
                {t('manga_psd_result_missing_fonts', lastPsdExportResult.missing_fonts?.length || 0)}
              </div>
            )}
          </div>
          {(lastPsdExportResult.psd_paths?.length || 0) > 0 && (
            <div className="mt-2 rounded-md border border-cyan-300/15 bg-slate-950/35 px-2 py-1.5">
              <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.14em] text-cyan-100/60">{t('manga_psd_result_psd_paths')}</div>
              <div className="space-y-1">
                {(lastPsdExportResult.psd_paths || []).slice(0, 4).map((path) => (
                  <div key={path} className="truncate text-xs text-cyan-50/80" title={path}>{path}</div>
                ))}
              </div>
            </div>
          )}
          {(lastPsdExportResult.script_paths?.length || 0) > 0 && (
            <div className="mt-2 rounded-md border border-cyan-300/15 bg-slate-950/35 px-2 py-1.5">
              <div className="mb-1 text-[11px] font-bold uppercase tracking-[0.14em] text-cyan-100/60">{t('manga_psd_result_jsx_paths')}</div>
              <div className="space-y-1">
                {(lastPsdExportResult.script_paths || []).slice(0, 4).map((path) => (
                  <div key={path} className="truncate text-xs text-cyan-50/80" title={path}>{path}</div>
                ))}
              </div>
            </div>
          )}
          {(lastPsdExportResult.missing_fonts?.length || 0) > 0 && (
            <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-2 py-1.5 text-xs text-amber-100">
              {t(
                'manga_psd_result_missing_font_names',
                (lastPsdExportResult.missing_fonts || [])
                  .map((font) => font.requested || font.block_id)
                  .filter(Boolean)
                  .slice(0, 6)
                  .join(', '),
              )}
            </div>
          )}
          {(lastPsdExportResult.warnings?.length || 0) > 0 && (
            <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-2 py-1.5 text-xs text-amber-100">
              {t('manga_psd_result_warnings', (lastPsdExportResult.warnings || []).slice(0, 2).join(' / '))}
            </div>
          )}
        </div>
      )}

      {pageQualityGate?.blocked_from_final && (
        <div className="mx-4 mt-3 rounded-lg border border-amber-400/25 bg-amber-300/10 px-4 py-3 text-sm text-amber-100">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-bold">{t('manga_quality_gate_title')} · {t('manga_page_badge_final_blocked')}</div>
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-100/75">
              {t('manga_quality_gate_issue_count', pageQualityGate.issue_count || 0)}
            </div>
          </div>
          <div className="mt-1 leading-relaxed">{pageQualityMessage || t('manga_quality_gate_draft_only')}</div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-amber-100/70">
            {pageQualityGate.draft_rendered_path && <span>{t('manga_quality_gate_draft_path', pageQualityGate.draft_rendered_path)}</span>}
            {pageQualityGate.artifact_path && <span>{t('manga_quality_gate_report_path', pageQualityGate.artifact_path)}</span>}
            {pageQualityGate.final_page_path && <span>{t('manga_quality_gate_final_path', pageQualityGate.final_page_path)}</span>}
          </div>
        </div>
      )}

      <MangaModelManagerDialog
        open={modelManagerOpen}
        modelManager={modelManager}
        loading={modelManagerLoading}
        projectTaskConfig={project?.task_config || null}
        busyAction={busyAction}
        activeJobProgress={activeJob?.progress || 0}
        downloadProgress={modelDownloadProgressState}
        hasProject={Boolean(project)}
        issueCount={modelManagerIssueCount}
        onClose={() => setModelManagerOpen(false)}
        onDownloadModel={(modelId) => { void handleDownloadMangaModel(modelId); }}
        onDownloadModelPreset={(presetId) => { void handleDownloadMangaModelPreset(presetId); }}
        onDownloadAllModels={() => { void handleDownloadAllMangaModels(); }}
        onSelectMangaEngine={(configKey, modelId) => { void handleSelectMangaEngine(configKey, modelId); }}
      />

      <div className="flex-1 min-h-0 flex bg-slate-950">
        <MangaPageStrip
          pages={scene?.pages || []}
          selectedPageId={selectedPageId}
          selectedPageIds={selectedPageIds}
          currentPageId={scene?.current_page_id || ''}
          loadingPageId={page?.page_id === loadingPageId ? '' : loadingPageId}
          onSelectPage={(pageId) => { if (project) void loadPage(project.project_id, pageId); }}
          onTogglePageSelection={togglePageSelection}
        />

        <MangaCanvas
          page={page}
          isPageLoading={Boolean(loadingPageId && !page)}
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
            fonts={fontCatalog}
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

      {psdExportOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/78 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-slate-800 bg-slate-950 shadow-2xl shadow-black/40">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-300/25 bg-cyan-300/10 text-cyan-100">
                  <Layers3 size={16} />
                </span>
                <div>
                  <div className="text-sm font-bold text-slate-100">{t('manga_psd_export_title')}</div>
                  <div className="text-xs text-slate-500">{t('manga_psd_export_page_count', psdScopePageCount)}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPsdExportOpen(false)}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-900 hover:text-slate-100"
                title={t('manga_psd_cancel')}
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-4 px-4 py-4">
              <div>
                <div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-slate-500">{t('manga_psd_export_scope')}</div>
                <div className="grid grid-cols-3 gap-2">
                  {([
                    { scope: 'current' as PsdExportScope, label: t('manga_psd_scope_current'), disabled: !selectedPageId },
                    { scope: 'selected' as PsdExportScope, label: t('manga_psd_scope_selected'), disabled: selectedPageIds.length === 0 },
                    { scope: 'all' as PsdExportScope, label: t('manga_psd_scope_all'), disabled: false },
                  ]).map((item) => (
                    <button
                      key={item.scope}
                      type="button"
                      onClick={() => setPsdExportScope(item.scope)}
                      disabled={item.disabled}
                      className={`h-10 rounded-lg border px-3 text-xs font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                        psdExportScope === item.scope
                          ? 'border-cyan-300/45 bg-cyan-300/16 text-cyan-100'
                          : 'border-slate-800 bg-slate-900/70 text-slate-300 hover:border-slate-600 hover:text-slate-100'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-2 text-xs text-slate-300">
                <div className="flex items-center gap-2">
                  {psdPhotoshopChecking && <Loader2 size={14} className="animate-spin text-cyan-200" />}
                  <span>{psdPhotoshopStatusText}</span>
                </div>
              </div>

              <div className="grid gap-2">
                <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-2.5">
                  <span className="text-sm font-semibold text-slate-200">{t('manga_psd_option_script_only')}</span>
                  <input
                    type="checkbox"
                    checked={psdEffectiveScriptOnly}
                    disabled={psdPhotoshopStatus?.available === false}
                    onChange={(event) => setPsdScriptOnly(event.target.checked)}
                    className="h-4 w-4 accent-cyan-300"
                  />
                </label>
                <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-2.5">
                  <span className="text-sm font-semibold text-slate-200">{t('manga_psd_option_include_blocked')}</span>
                  <input
                    type="checkbox"
                    checked={psdIncludeBlocked}
                    onChange={(event) => setPsdIncludeBlocked(event.target.checked)}
                    className="h-4 w-4 accent-cyan-300"
                  />
                </label>
                <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-2.5">
                  <span className="text-sm font-semibold text-slate-200">{t('manga_psd_option_package')}</span>
                  <input
                    type="checkbox"
                    checked={psdPackage}
                    onChange={(event) => setPsdPackage(event.target.checked)}
                    className="h-4 w-4 accent-cyan-300"
                  />
                </label>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-4 py-3">
              <button
                type="button"
                onClick={() => setPsdExportOpen(false)}
                className="inline-flex h-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/70 px-3 text-xs font-bold text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100"
              >
                {t('manga_psd_cancel')}
              </button>
              <button
                type="button"
                onClick={() => { void handlePsdExportFromDialog(); }}
                disabled={Boolean(busyAction) || psdScopePageCount <= 0}
                className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-cyan-300/35 bg-cyan-300 px-3 text-xs font-bold text-slate-950 transition-colors hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-45"
              >
                <FileArchive size={14} />
                {t('manga_psd_start_export')}
              </button>
            </div>
          </div>
        </div>
      )}

      {psdExportProgressOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-slate-950/78 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-slate-800 bg-slate-950 shadow-2xl shadow-black/40">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-300/25 bg-cyan-300/10 text-cyan-100">
                  {psdExportRunning ? <Loader2 size={16} className="animate-spin" /> : <Layers3 size={16} />}
                </span>
                <div>
                  <div className="text-sm font-bold text-slate-100">{t('manga_psd_export_progress_title')}</div>
                  <div className="text-xs text-slate-500">{psdExportProgressMessage}</div>
                </div>
              </div>
              {!psdExportRunning && (
                <button
                  type="button"
                  onClick={() => setPsdExportProgressOpen(false)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-900 hover:text-slate-100"
                  title={t('manga_psd_result_close')}
                >
                  <X size={16} />
                </button>
              )}
            </div>

            <div className="space-y-4 px-4 py-4">
              <div className="rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-3">
                <div className="mb-2 flex items-center justify-between gap-3 text-xs font-semibold text-slate-300">
                  <span>{psdExportProgressMessage}</span>
                  <span>{psdExportProgressMetric}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-cyan-300 transition-all duration-300"
                    style={{ width: `${psdExportProgress}%` }}
                  />
                </div>
              </div>

              <div className="text-xs leading-relaxed text-slate-400">
                {psdExportProgressDetail}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-4 py-3">
              {psdExportRunning ? (
                <button
                  type="button"
                  onClick={() => { void handleCancelPsdExport(); }}
                  disabled={!psdExportJob?.job_id || psdExportCancelling || Boolean(psdExportJob?.cancel_requested)}
                  className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-amber-300/35 bg-amber-300/12 px-3 text-xs font-bold text-amber-100 transition-colors hover:bg-amber-300/18 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {psdExportCancelling || psdExportJob?.cancel_requested ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
                  {t('manga_psd_export_cancel')}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setPsdExportProgressOpen(false)}
                  className="inline-flex h-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/70 px-3 text-xs font-bold text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100"
                >
                  {t('manga_psd_result_close')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <MangaStatusBar leftText={statusLeftText} centerText={statusCenterText} rightText={statusRightText} />
    </div>
  );
};
