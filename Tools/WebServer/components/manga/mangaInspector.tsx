import React, { useEffect, useMemo, useState } from 'react';
import { Activity, ChevronDown, ExternalLink, FileJson, ImageIcon, PackageCheck, PlayCircle } from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaPageDetail, MangaRuntimeValidationHistoryItem, MangaRuntimeValidationResult, MangaTextBlock } from '../../types/manga';
import { MangaActiveJobSummary, MangaBlockDraft, MangaEngineCard, translateMangaEnum } from './shared';

export interface MangaInspectorProps {
  page: MangaPageDetail | null;
  activeBlock: MangaTextBlock | null;
  activeBlockDraft: MangaBlockDraft | null;
  activeJob: MangaActiveJobSummary | null;
  engineCards: MangaEngineCard[];
  runtimeValidation: MangaRuntimeValidationResult | null;
  runtimeValidationHistory: MangaRuntimeValidationHistoryItem[];
  activeRuntimeStage: string;
  busyAction: string;
  hasProject: boolean;
  dirtyBlockCount: number;
  activeBlockDirty: boolean;
  onSelectRuntimeStage: (stage: string) => void;
  onLoadRuntimeValidationHistory: (runId: string) => void;
  onValidateRuntime: () => void;
  onDownloadModel: (modelId: string) => void;
}

interface InspectorSectionProps {
  title: string;
  meta?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

const InspectorSection: React.FC<InspectorSectionProps> = ({
  title,
  meta,
  defaultOpen = false,
  children,
}) => (
  <details
    open={defaultOpen}
    className="group rounded-xl border border-slate-800/85 bg-slate-900/48 shadow-[0_16px_42px_rgba(2,6,23,0.18)]"
  >
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
      <div className="min-w-0">
        <div className="truncate text-xs font-bold uppercase tracking-[0.18em] text-slate-400">{title}</div>
        {meta && <div className="mt-0.5 truncate text-[11px] text-slate-500">{meta}</div>}
      </div>
      <ChevronDown size={15} className="shrink-0 text-slate-500 transition-transform group-open:rotate-180" />
    </summary>
    <div className="border-t border-slate-800/75 px-3 py-3">{children}</div>
  </details>
);

const MetricTile: React.FC<{ label: string; value: React.ReactNode; tone?: string }> = ({
  label,
  value,
  tone = 'text-slate-100',
}) => (
  <div className="rounded-lg border border-slate-800 bg-slate-950/55 px-2.5 py-2">
    <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{label}</div>
    <div className={`mt-1 text-sm font-bold ${tone}`}>{value}</div>
  </div>
);

const StatusPill: React.FC<{ children: React.ReactNode; tone?: 'cyan' | 'emerald' | 'amber' | 'rose' | 'slate' }> = ({
  children,
  tone = 'slate',
}) => {
  const classes = {
    cyan: 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100',
    emerald: 'border-emerald-300/25 bg-emerald-300/10 text-emerald-100',
    amber: 'border-amber-300/25 bg-amber-300/10 text-amber-100',
    rose: 'border-rose-300/25 bg-rose-300/10 text-rose-100',
    slate: 'border-slate-700/80 bg-slate-800/60 text-slate-200',
  };

  return (
    <span className={`shrink-0 rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.13em] ${classes[tone]}`}>
      {children}
    </span>
  );
};

const clampPercent = (value: number) => Math.max(0, Math.min(100, value || 0));

const formatDateTime = (value: string) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const getExecutionTone = (mode: string): 'cyan' | 'emerald' | 'amber' | 'rose' | 'slate' => {
  if (mode === 'configured_runtime') return 'emerald';
  if (mode === 'fallback_runtime') return 'cyan';
  if (mode === 'failed') return 'rose';
  return 'amber';
};

const isImageArtifact = (path: string) => /\.(png|jpe?g|webp|gif|bmp)$/i.test(path.split('?')[0] || '');

const formatArtifactText = (value: string) => {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
};

const truncateArtifactText = (value: string) => (
  value.length > 16000 ? `${value.slice(0, 16000)}\n...` : value
);

export const MangaInspector: React.FC<MangaInspectorProps> = ({
  page,
  activeBlock,
  activeBlockDraft,
  activeJob,
  engineCards,
  runtimeValidation,
  runtimeValidationHistory,
  activeRuntimeStage,
  busyAction,
  hasProject,
  dirtyBlockCount,
  activeBlockDirty,
  onSelectRuntimeStage,
  onLoadRuntimeValidationHistory,
  onValidateRuntime,
  onDownloadModel,
}) => {
  const { t } = useI18n();
  const blockWidth = activeBlock ? Math.max(0, activeBlock.bbox[2] - activeBlock.bbox[0]) : 0;
  const blockHeight = activeBlock ? Math.max(0, activeBlock.bbox[3] - activeBlock.bbox[1]) : 0;
  const fontFamily = activeBlockDraft?.font_family ?? activeBlock?.style.font_family ?? '-';
  const fontSize = activeBlockDraft?.font_size ?? activeBlock?.style.font_size ?? 0;
  const lineSpacing = activeBlockDraft?.line_spacing ?? activeBlock?.style.line_spacing ?? 0;
  const fill = activeBlockDraft?.fill ?? activeBlock?.style.fill ?? '#000000';
  const strokeColor = activeBlockDraft?.stroke_color ?? activeBlock?.style.stroke_color ?? '#ffffff';
  const strokeWidth = activeBlockDraft?.stroke_width ?? activeBlock?.style.stroke_width ?? 0;
  const sourcePreview = activeBlockDraft?.source_text ?? activeBlock?.source_text ?? '';
  const translationPreview = activeBlockDraft?.translation ?? activeBlock?.translation ?? '';
  const isBusy = Boolean(busyAction);
  const isRuntimeBusy = busyAction === 'validate runtime';
  const canValidateRuntime = Boolean(hasProject && page && !isBusy);
  const missingEngineCount = engineCards.filter((card) => !card.available).length;
  const missingPackages = engineCards
    .flatMap((card) => card.packages)
    .filter((pkg) => !pkg.available);
  const selectedRuntimeStage = runtimeValidation?.stages.find((stage) => stage.stage === activeRuntimeStage) || runtimeValidation?.stages[0] || null;
  const selectedStageArtifacts = useMemo(() => (
    Object.entries(selectedRuntimeStage?.artifacts || {}).map(([key, path]) => ({
      key,
      path,
      url: selectedRuntimeStage?.artifact_urls?.[key] || '',
      isImage: isImageArtifact(path),
    }))
  ), [selectedRuntimeStage]);
  const [activeArtifactKey, setActiveArtifactKey] = useState('');
  const activeArtifact = selectedStageArtifacts.find((artifact) => artifact.key === activeArtifactKey) || selectedStageArtifacts[0] || null;
  const [artifactText, setArtifactText] = useState('');
  const [artifactError, setArtifactError] = useState('');
  const [artifactLoading, setArtifactLoading] = useState(false);

  useEffect(() => {
    setActiveArtifactKey('');
  }, [activeRuntimeStage, runtimeValidation?.created_at]);

  useEffect(() => {
    setArtifactText('');
    setArtifactError('');
    if (!activeArtifact?.url || activeArtifact.isImage) {
      setArtifactLoading(false);
      return;
    }

    let cancelled = false;
    setArtifactLoading(true);
    fetch(activeArtifact.url)
      .then((response) => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.text();
      })
      .then((text) => {
        if (!cancelled) setArtifactText(truncateArtifactText(formatArtifactText(text)));
      })
      .catch((error: any) => {
        if (!cancelled) setArtifactError(error?.message || String(error));
      })
      .finally(() => {
        if (!cancelled) setArtifactLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeArtifact]);

  return (
    <div className="space-y-3 px-3 py-3">
      <div className="rounded-2xl border border-cyan-300/10 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.16),transparent_45%),rgba(15,23,42,0.72)] px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-200/85">{t('manga_inspector_title')}</div>
            <div className="mt-1 truncate text-sm font-semibold text-slate-100">
              {page ? t('manga_page_summary', page.index, page.width, page.height) : t('manga_no_page_selected')}
            </div>
          </div>
          <StatusPill tone={page ? 'cyan' : 'slate'}>
            {page ? translateMangaEnum('manga_state', page.status, t) : t('manga_idle')}
          </StatusPill>
        </div>
        {activeBlock && (
          <div className="mt-2 truncate text-xs text-slate-500">
            {t('manga_active_block_inline')} <span className="font-semibold text-slate-200">{activeBlock.block_id}</span>
            {activeBlockDirty && <span className="ml-2 text-amber-200">{t('manga_unsaved')}</span>}
          </div>
        )}
        {dirtyBlockCount > 0 && (
          <div className="mt-2 rounded-lg border border-amber-300/20 bg-amber-300/10 px-2.5 py-1.5 text-xs text-amber-100">
            {t('manga_dirty_block_count', dirtyBlockCount)}
          </div>
        )}
      </div>

      <section className="rounded-xl border border-slate-800/85 bg-slate-900/55 px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-slate-400">
              <Activity size={14} className="text-cyan-300" />
              {t('manga_panel_runtime_validation')}
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              {runtimeValidation
                ? t('manga_last_checked', formatDateTime(runtimeValidation.created_at))
                : t('manga_runtime_validation_empty')}
            </div>
          </div>
          <button
            type="button"
            onClick={onValidateRuntime}
            disabled={!canValidateRuntime}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-2.5 text-[11px] font-bold text-cyan-100 transition-colors hover:border-cyan-200 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {isRuntimeBusy ? <Activity size={13} className="animate-pulse" /> : <PlayCircle size={13} />}
            {t('manga_action_validate_runtime')}
          </button>
        </div>

        {runtimeValidation && (
          <div className="mt-3 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold text-slate-100">{t('manga_page_short')} {runtimeValidation.page_index}</div>
              <StatusPill tone={runtimeValidation.ok ? 'emerald' : 'amber'}>
                {runtimeValidation.ok ? t('manga_complete') : t('manga_needs_review')}
              </StatusPill>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <MetricTile label={t('manga_summary_runtime')} value={runtimeValidation.summary?.runtime_stage_count ?? 0} tone="text-emerald-200" />
              <MetricTile label={t('manga_summary_fallback')} value={runtimeValidation.summary?.fallback_stage_count ?? 0} tone="text-amber-200" />
              <MetricTile label={t('manga_summary_seeds')} value={runtimeValidation.summary?.seed_count ?? 0} tone="text-cyan-200" />
            </div>
            <details className="group rounded-lg border border-slate-800 bg-slate-950/38">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                {t('manga_artifact_dir')}
                <ChevronDown size={14} className="transition-transform group-open:rotate-180" />
              </summary>
              <div className="border-t border-slate-800 px-2.5 py-2 text-xs text-slate-400 break-all">{runtimeValidation.output_dir}</div>
            </details>
          </div>
        )}

        {missingPackages.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-300/20 bg-amber-300/10 px-3 py-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-amber-100">
              {t('manga_runtime_missing_models')}
            </div>
            <div className="mt-2 space-y-1.5">
              {missingPackages.map((pkg) => {
                const isPreparing = busyAction === `download model:${pkg.modelId}`;
                return (
                  <div key={pkg.modelId} className="flex items-center justify-between gap-2 text-xs">
                    <span className="min-w-0 truncate text-amber-50" title={pkg.label}>{pkg.label}</span>
                    <button
                      type="button"
                      onClick={() => onDownloadModel(pkg.modelId)}
                      disabled={Boolean(busyAction)}
                      className="shrink-0 rounded-md border border-amber-200/25 bg-amber-200/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {isPreparing ? t('manga_preparing') : t('manga_prepare')}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {runtimeValidationHistory.length > 0 && (
          <details className="group mt-3 rounded-lg border border-slate-800 bg-slate-950/38">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              {t('manga_validation_history')}
              <ChevronDown size={14} className="transition-transform group-open:rotate-180" />
            </summary>
            <div className="grid gap-1.5 border-t border-slate-800 px-2.5 py-2">
              {runtimeValidationHistory.slice(0, 6).map((item) => (
                <button
                  key={item.run_id}
                  type="button"
                  onClick={() => onLoadRuntimeValidationHistory(item.run_id)}
                  disabled={Boolean(busyAction)}
                  className={`grid gap-1 rounded-md border px-2.5 py-2 text-left text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    runtimeValidation?.output_dir === item.output_dir
                      ? 'border-cyan-300/55 bg-cyan-300/10'
                      : 'border-slate-800 bg-slate-900/65 hover:border-cyan-300/40'
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold text-slate-200">{formatDateTime(item.created_at) || item.run_id}</span>
                    <StatusPill tone={item.ok ? 'emerald' : 'amber'}>
                      {item.ok ? t('manga_complete') : t('manga_needs_review')}
                    </StatusPill>
                  </span>
                  <span className="text-slate-500">
                    {t('manga_history_summary', item.runtime_stage_count, item.fallback_stage_count, item.seed_count)}
                  </span>
                </button>
              ))}
            </div>
          </details>
        )}
      </section>

      {runtimeValidation && (
        <InspectorSection
          title={t('manga_validation_stages')}
          meta={t('manga_validation_stage_count', runtimeValidation.stages.length)}
          defaultOpen={!runtimeValidation.ok}
        >
          <div className="space-y-2">
            {runtimeValidation.stages.map((stage) => {
              const mode = stage.execution_mode || (stage.used_runtime ? 'configured_runtime' : 'heuristic_fallback');
              return (
                <button
                  key={stage.stage}
                  type="button"
                  onClick={() => onSelectRuntimeStage(stage.stage)}
                  className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
                    activeRuntimeStage === stage.stage
                      ? 'border-cyan-300/60 bg-cyan-300/10'
                      : 'border-slate-800 bg-slate-950/42 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 truncate text-sm font-semibold text-slate-100">
                      {translateMangaEnum('manga_runtime_stage', stage.stage, t)}
                    </div>
                    <StatusPill tone={getExecutionTone(mode)}>
                      {translateMangaEnum('manga_execution_mode', mode, t)}
                    </StatusPill>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
                    <div>
                      <div className="uppercase tracking-[0.14em]">{t('manga_runtime')}</div>
                      <div className="mt-0.5 truncate text-slate-300" title={stage.runtime_engine_id || '-'}>
                        {stage.runtime_engine_id || '-'}
                      </div>
                    </div>
                    <div>
                      <div className="uppercase tracking-[0.14em]">{t('manga_elapsed')}</div>
                      <div className="mt-0.5 text-slate-300">{t('manga_elapsed_ms', stage.elapsed_ms)}</div>
                    </div>
                  </div>
                  {(stage.warning_message || stage.error_message) && (
                    <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-2.5 py-2 text-xs text-amber-100">
                      {stage.error_message || stage.warning_message}
                    </div>
                  )}
                  {stage.fallback_reason && (
                    <div className="mt-2 rounded-md border border-slate-700/70 bg-slate-900/70 px-2.5 py-2 text-xs text-slate-400">
                      {stage.fallback_reason}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
          {selectedRuntimeStage && Object.keys(selectedRuntimeStage.artifacts || {}).length > 0 && (
            <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  {t('manga_stage_artifacts')}
                </div>
                {activeArtifact?.url && (
                  <a
                    href={activeArtifact.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] font-semibold text-cyan-200 hover:text-cyan-100"
                  >
                    {t('manga_open_artifact')}
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
              <div className="mt-2 grid gap-1.5">
                {selectedStageArtifacts.map((artifact) => (
                  <button
                    key={artifact.key}
                    type="button"
                    onClick={() => setActiveArtifactKey(artifact.key)}
                    className={`grid gap-0.5 rounded-md border px-2.5 py-2 text-left text-xs transition-colors ${
                      activeArtifact?.key === artifact.key
                        ? 'border-cyan-300/55 bg-cyan-300/10'
                        : 'border-slate-800 bg-slate-900/65 hover:border-cyan-300/40'
                    }`}
                  >
                    <span className="flex items-center gap-1.5 font-semibold text-cyan-100">
                      {artifact.isImage ? <ImageIcon size={12} /> : <FileJson size={12} />}
                      {artifact.key}
                    </span>
                    <span className="truncate text-slate-500" title={artifact.path}>{artifact.path}</span>
                  </button>
                ))}
              </div>
              {activeArtifact && (
                <div className="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/70">
                  {activeArtifact.isImage && activeArtifact.url ? (
                    <img
                      src={activeArtifact.url}
                      alt={activeArtifact.key}
                      className="max-h-64 w-full object-contain"
                    />
                  ) : artifactLoading ? (
                    <div className="px-3 py-4 text-sm text-slate-500">{t('manga_loading_artifact')}</div>
                  ) : artifactError ? (
                    <div className="px-3 py-4 text-sm text-rose-200">{t('manga_artifact_load_failed', artifactError)}</div>
                  ) : artifactText ? (
                    <pre className="max-h-80 overflow-auto p-3 text-[11px] leading-relaxed text-slate-300">{artifactText}</pre>
                  ) : (
                    <div className="px-3 py-4 text-sm text-slate-500">{t('manga_artifact_preview_empty')}</div>
                  )}
                </div>
              )}
            </div>
          )}
        </InspectorSection>
      )}

      <section className="rounded-xl border border-slate-800/85 bg-slate-900/48 px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">{t('manga_panel_task_status')}</div>
          {activeJob && <StatusPill tone={activeJob.status === 'failed' ? 'rose' : 'cyan'}>{translateMangaEnum('manga_state', activeJob.status, t)}</StatusPill>}
        </div>
        {activeJob ? (
          <div className="mt-3">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="truncate font-semibold text-slate-100">{activeJob.stageLabel}</span>
              <span className="text-xs text-slate-500">{clampPercent(activeJob.progress)}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-950/80">
              <div
                className={`h-full ${activeJob.status === 'failed' ? 'bg-rose-400' : 'bg-cyan-400'}`}
                style={{ width: `${clampPercent(activeJob.progress)}%` }}
              />
            </div>
            <div className="mt-2 line-clamp-2 text-xs text-slate-400">{activeJob.message || t('manga_waiting_job_details')}</div>
          </div>
        ) : (
          <div className="mt-2 text-sm text-slate-500">{t('manga_no_active_job')}</div>
        )}
      </section>

      <InspectorSection
        title={t('manga_panel_engine_status')}
        meta={missingEngineCount > 0 ? t('manga_engine_missing_count', missingEngineCount) : t('manga_engine_all_ready')}
        defaultOpen={missingEngineCount > 0}
      >
        <div className="grid gap-2">
          {engineCards.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950/38 px-3 py-4 text-sm text-slate-500">
              {t('manga_engine_status_empty')}
            </div>
          )}
          {engineCards.map((card) => (
            <div key={card.label} className="rounded-lg border border-slate-800 bg-slate-950/42 px-3 py-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0 truncate text-sm font-semibold text-slate-100">{card.label}</div>
                <StatusPill tone={card.available ? 'emerald' : 'amber'}>
                  {card.available ? t('manga_ready') : t('manga_missing')}
                </StatusPill>
              </div>
              <div className="mt-1 truncate text-xs text-slate-500" title={card.packageLabel || '-'}>
                {card.packageLabel || t('manga_unknown_package')}
              </div>

              {card.packages.length > 0 && (
                <div className="mt-2 space-y-2">
                  {card.packages.map((pkg) => {
                    const isPreparing = busyAction === `download model:${pkg.modelId}`;
                    const progress = isPreparing ? clampPercent(activeJob?.progress || 0) : 0;
                    return (
                      <div key={pkg.modelId} className="rounded-md border border-slate-800 bg-slate-900/58 px-2.5 py-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <PackageCheck size={13} className={pkg.available ? 'text-emerald-300' : 'text-amber-300'} />
                              <div className="truncate text-xs font-semibold text-slate-200">{pkg.label}</div>
                            </div>
                            <div className="mt-0.5 truncate text-[11px] text-slate-500" title={pkg.repoId || pkg.storagePath}>
                              {pkg.repoId || pkg.storagePath || t('manga_unknown_package')}
                            </div>
                          </div>
                          {pkg.available ? (
                            <StatusPill tone="emerald">{t('manga_ready')}</StatusPill>
                          ) : (
                            <button
                              type="button"
                              onClick={() => onDownloadModel(pkg.modelId)}
                              disabled={Boolean(busyAction)}
                              className="shrink-0 rounded-md border border-amber-300/25 bg-amber-300/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 transition-colors hover:border-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {isPreparing ? t('manga_preparing') : t('manga_prepare')}
                            </button>
                          )}
                        </div>

                        {isPreparing && (
                          <div className="mt-2">
                            <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                              <span>{t('manga_model_progress')}</span>
                              <span>{progress}%</span>
                            </div>
                            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-950/85">
                              <div className="h-full bg-amber-300" style={{ width: `${progress}%` }} />
                            </div>
                          </div>
                        )}

                        <details className="group mt-2">
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                            {t('manga_model_details')}
                            <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
                          </summary>
                          <div className="mt-2 grid grid-cols-1 gap-2 text-[11px] text-slate-500">
                            <div>
                              <div className="uppercase tracking-[0.14em]">{t('manga_runtime')}</div>
                              <div className="mt-0.5 truncate text-slate-300" title={pkg.runtimeEngineId || '-'}>
                                {pkg.runtimeEngineId || '-'}
                              </div>
                            </div>
                            <div>
                              <div className="uppercase tracking-[0.14em]">{t('manga_storage')}</div>
                              <div className="mt-0.5 truncate text-slate-300" title={pkg.storagePath || '-'}>
                                {pkg.storagePath || '-'}
                              </div>
                            </div>
                          </div>
                        </details>

                        {!pkg.runtimeSupported && (
                          <div className="mt-2 text-[11px] text-slate-500">{t('manga_model_no_runtime_bridge')}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <details className="group mt-2 rounded-md border border-slate-800/75 bg-slate-900/40">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  {t('manga_configured')}
                  <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
                </summary>
                <div className="space-y-2 border-t border-slate-800 px-2 py-2 text-[11px] text-slate-500">
                  <div>
                    <div className="uppercase tracking-[0.14em]">{t('manga_configured')}</div>
                    <div className="mt-0.5 break-all text-slate-300">{card.configured || '-'}</div>
                  </div>
                  <div>
                    <div className="uppercase tracking-[0.14em]">{t('manga_runtime')}</div>
                    <div className="mt-0.5 break-all text-slate-300">{card.runtime || '-'}</div>
                  </div>
                </div>
              </details>
            </div>
          ))}
        </div>
      </InspectorSection>

      <InspectorSection
        title={t('manga_panel_active_block')}
        meta={activeBlock ? activeBlock.block_id : t('manga_active_block_empty')}
        defaultOpen={Boolean(activeBlock)}
      >
        {!activeBlock ? (
          <div className="rounded-lg border border-dashed border-slate-800 bg-slate-950/38 px-3 py-4 text-sm text-slate-500">
            {t('manga_active_block_empty')}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-800 bg-slate-950/42 px-3 py-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="truncate font-semibold text-slate-100">{activeBlock.block_id}</div>
                <StatusPill>{activeBlock.origin}</StatusPill>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <MetricTile label={t('manga_field_position')} value={`x ${activeBlock.bbox[0]} / y ${activeBlock.bbox[1]}`} />
                <MetricTile label={t('manga_field_size')} value={`${blockWidth} x ${blockHeight}`} />
                <MetricTile label={t('manga_field_direction')} value={`${activeBlock.source_direction} -> ${activeBlock.rendered_direction}`} />
                <MetricTile label={t('manga_field_confidence')} value={activeBlock.ocr_confidence.toFixed(3)} />
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-950/42 px-3 py-2.5">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{t('manga_text_preview')}</div>
              <div className="mt-2 text-[11px] text-slate-500">{t('manga_ocr_label')}</div>
              <div className="mt-1 line-clamp-4 whitespace-pre-wrap text-sm text-slate-200">{sourcePreview || t('manga_no_ocr_text')}</div>
              <div className="mt-2 text-[11px] text-slate-500">{t('manga_translation_label')}</div>
              <div className="mt-1 line-clamp-5 whitespace-pre-wrap text-sm text-slate-100">{translationPreview || t('manga_no_translation_yet')}</div>
            </div>

            <details className="group rounded-lg border border-slate-800 bg-slate-950/42">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                {t('manga_render_style')}
                <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
              </summary>
              <div className="grid grid-cols-2 gap-2 border-t border-slate-800 px-3 py-3 text-xs">
                <MetricTile label={t('manga_field_font')} value={<span className="break-all">{fontFamily || '-'}</span>} />
                <MetricTile label={t('manga_field_font_prediction')} value={<span className="break-all">{activeBlock.font_prediction || '-'}</span>} />
                <MetricTile label={t('manga_field_font_size')} value={fontSize} />
                <MetricTile label={t('manga_field_line_spacing')} value={lineSpacing} />
                <MetricTile
                  label={t('manga_field_fill')}
                  value={(
                    <span className="flex items-center gap-2">
                      <span className="h-3.5 w-3.5 rounded border border-slate-700" style={{ backgroundColor: fill }} />
                      {fill}
                    </span>
                  )}
                />
                <MetricTile
                  label={t('manga_field_stroke')}
                  value={(
                    <span className="flex items-center gap-2">
                      <span className="h-3.5 w-3.5 rounded border border-slate-700" style={{ backgroundColor: strokeColor }} />
                      {strokeWidth}px
                    </span>
                  )}
                />
              </div>
            </details>

            <details className="group rounded-lg border border-slate-800 bg-slate-950/42">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                {t('manga_block_geometry')}
                <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
              </summary>
              <div className="space-y-2 border-t border-slate-800 px-3 py-3 text-xs text-slate-400">
                <div>{t('manga_field_placement')}: <span className="text-slate-200">{activeBlock.placement_mode} · {activeBlock.editable ? t('manga_editable') : t('manga_locked')}</span></div>
                <div>{t('manga_field_bbox')}: <span className="text-slate-200">{activeBlock.bbox.join(', ')}</span></div>
                <div>{t('manga_field_flags')}: <span className="text-slate-200">{activeBlock.flags.join(', ') || t('manga_no_flags')}</span></div>
              </div>
            </details>
          </div>
        )}
      </InspectorSection>
    </div>
  );
};
