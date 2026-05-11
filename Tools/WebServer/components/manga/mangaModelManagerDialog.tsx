import React from 'react';
import { Activity, AlertTriangle, ChevronDown, DownloadCloud, PackageCheck, Settings2, X } from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaModelEngineOption, MangaModelManagerManifest } from '../../types/manga';

interface MangaModelManagerDialogProps {
  open: boolean;
  modelManager: MangaModelManagerManifest | null;
  loading?: boolean;
  projectTaskConfig: Record<string, any> | null;
  busyAction: string;
  activeJobProgress: number;
  downloadProgress?: MangaModelDownloadProgress | null;
  hasProject: boolean;
  issueCount: number;
  onClose: () => void;
  onDownloadModel: (modelId: string) => void;
  onDownloadModelPreset: (presetId: string) => void;
  onDownloadAllModels: () => void;
  onSelectMangaEngine: (configKey: string, modelId: string) => void;
}

interface MangaModelDownloadProgress {
  visible: boolean;
  running: boolean;
  failed: boolean;
  progress: number;
  stageLabel: string;
  message: string;
  metric: string;
  detailRows: Array<{ label: string; value: string }>;
  errorMessage?: string;
}

const ENGINE_STAGE_CONFIG_KEYS: Record<string, string> = {
  detect: 'manga_detect_engine',
  segment: 'manga_segment_engine',
  ocr: 'manga_ocr_engine',
  inpaint: 'manga_inpaint_engine',
};

const clampPercent = (value: number) => Math.max(0, Math.min(100, value || 0));

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

const getEngineStageLabel = (stage: string, t: (key: string, ...args: any[]) => string) => {
  if (stage === 'detect') return t('manga_engine_detect');
  if (stage === 'segment') return t('manga_engine_segment');
  if (stage === 'ocr') return t('manga_engine_ocr');
  if (stage === 'inpaint') return t('manga_engine_inpaint');
  return stage;
};

const getProjectEngineConfigValue = (taskConfig: Record<string, any> | undefined, configKey: string, fallback = '') => (
  String(taskConfig?.[configKey] || fallback || '')
);

const resolveModelOptionValue = (value: string, options: MangaModelEngineOption[]) => {
  const rawValue = String(value || '').trim();
  if (!rawValue) return '';
  const direct = options.find((option) => option.model_id === rawValue);
  if (direct) return direct.model_id;
  const alias = options.find((option) => (option.aliases || []).includes(rawValue));
  return alias?.model_id || rawValue;
};

const getModelOptionDisabledLabel = (
  option: MangaModelEngineOption,
  t: (key: string, ...args: any[]) => string,
) => {
  if (option.selectable) return t('manga_ready');
  if (option.disabled_reason === 'unsupported_runtime') return t('manga_model_unsupported_runtime');
  return t('manga_model_not_downloaded');
};

const i18nSlug = (value: string) => (
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
);

const translateCatalogText = (
  prefix: string,
  value: string,
  t: (key: string, ...args: any[]) => string,
) => {
  const key = `${prefix}_${i18nSlug(value)}`;
  const translated = t(key);
  return translated === key ? value : translated;
};

const translateModelDescription = (
  modelId: string,
  fallback: string,
  t: (key: string, ...args: any[]) => string,
) => {
  const key = `manga_model_description_${i18nSlug(modelId)}`;
  const translated = t(key);
  return translated === key ? fallback : translated;
};

const translateModelRuntimeNote = (
  modelId: string,
  note: string,
  t: (key: string, ...args: any[]) => string,
) => {
  const modelKey = `manga_model_note_${i18nSlug(modelId)}_${i18nSlug(note)}`;
  const modelTranslated = t(modelKey);
  if (modelTranslated !== modelKey) return modelTranslated;
  return translateCatalogText('manga_model_note', note, t);
};

const translateModelCaution = (
  value: string,
  t: (key: string, ...args: any[]) => string,
) => translateCatalogText('manga_model_caution', value, t);

export const MangaModelManagerDialog: React.FC<MangaModelManagerDialogProps> = ({
  open,
  modelManager,
  loading = false,
  projectTaskConfig,
  busyAction,
  activeJobProgress,
  downloadProgress,
  hasProject,
  issueCount,
  onClose,
  onDownloadModel,
  onDownloadModelPreset,
  onDownloadAllModels,
  onSelectMangaEngine,
}) => {
  const { t } = useI18n();
  if (!open) return null;

  const modelPresets = modelManager?.presets || [];
  const allModels = modelManager?.models || [];
  const isBusy = Boolean(busyAction);
  const allReady = allModels.length > 0 && allModels.every((model) => Boolean(model.available));
  const progress = downloadProgress?.visible ? downloadProgress : null;

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/78 p-4 backdrop-blur-sm">
      <div className="flex h-[min(70vh,780px)] w-[min(58vw,1040px)] min-w-[720px] max-w-[calc(100vw-2rem)] flex-col rounded-xl border border-slate-800 bg-slate-950 shadow-2xl shadow-black/45 max-md:min-w-0 max-md:h-[86vh] max-md:w-[94vw]">
        <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-300/25 bg-cyan-300/10 text-cyan-100">
              <Settings2 size={16} />
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-bold text-slate-100">{t('manga_panel_model_manager')}</div>
              <div className="truncate text-xs text-slate-500">
                {modelManager
                  ? t('manga_model_default_ocr', modelManager.default_ocr_model_id || '-')
                  : loading
                    ? t('manga_model_manager_loading')
                    : t('manga_model_manager_empty')}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {issueCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-rose-300/25 bg-rose-300/10 px-2 py-1 text-[11px] font-bold text-rose-100">
                <AlertTriangle size={12} />
                {t('manga_model_manager_issue_count', issueCount)}
              </span>
            )}
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-900 hover:text-slate-100"
              title={t('manga_model_manager_close')}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {!modelManager ? (
          <div className="flex flex-1 items-center justify-center px-6 text-sm text-slate-500">
            <div className="flex items-center gap-2">
              {loading && <Activity size={15} className="animate-pulse text-cyan-300" />}
              <span>{loading ? t('manga_model_manager_loading') : t('manga_model_manager_empty')}</span>
            </div>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-[minmax(280px,0.9fr)_minmax(360px,1.2fr)] gap-3 overflow-hidden p-4 max-lg:grid-cols-1">
            <div className="min-h-0 overflow-y-auto pr-1">
              {progress && (
                <div className={`mb-3 rounded-lg border px-3 py-3 ${
                  progress.failed
                    ? 'border-rose-300/25 bg-rose-300/10'
                    : 'border-cyan-300/20 bg-cyan-300/10'
                }`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                        <Activity size={14} className={progress.running ? 'animate-pulse text-cyan-300' : progress.failed ? 'text-rose-300' : 'text-emerald-300'} />
                        <span className="truncate">{t('manga_model_download_dialog_title')}</span>
                      </div>
                      <div className="mt-1 truncate text-[11px] text-slate-500">{progress.stageLabel}</div>
                    </div>
                    <span className="shrink-0 text-xs font-semibold text-slate-300">{progress.metric}</span>
                  </div>
                  <div className="mt-2 text-xs text-slate-300">{progress.message || t('manga_model_download_waiting')}</div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-950/80">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${progress.failed ? 'bg-rose-400' : 'bg-cyan-300'}`}
                      style={{ width: `${progress.progress}%` }}
                    />
                  </div>
                  {progress.detailRows.length > 0 ? (
                    <div className="mt-2 grid gap-2 md:grid-cols-2">
                      {progress.detailRows.map((row) => (
                        <div key={row.label} className="min-w-0 rounded-md border border-slate-800 bg-slate-950/45 px-2 py-1.5">
                          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">{row.label}</div>
                          <div className="mt-0.5 truncate text-[11px] text-slate-200" title={row.value}>{row.value}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-2 text-[11px] text-slate-500">{t('manga_model_download_waiting_detail')}</div>
                  )}
                  {progress.failed && (
                    <div className="mt-2 rounded-md border border-rose-300/20 bg-rose-300/10 px-2 py-1.5 text-[11px] leading-relaxed text-rose-100">
                      {progress.errorMessage || t('manga_model_download_failed')}
                    </div>
                  )}
                </div>
              )}
              <div className="rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Settings2 size={14} className="text-cyan-300" />
                      <div className="truncate text-sm font-semibold text-slate-100">{t('manga_model_engine_selectors')}</div>
                    </div>
                    <div className="mt-1 text-[11px] leading-relaxed text-slate-500">
                      {hasProject ? t('manga_model_engine_selectors_hint') : t('manga_model_engine_selectors_no_project')}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={onDownloadAllModels}
                    disabled={isBusy || allReady}
                    className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-cyan-300/25 bg-cyan-300/10 px-2.5 text-[11px] font-bold text-cyan-100 transition-colors hover:border-cyan-200 disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    {busyAction === 'download all models' ? <Activity size={13} className="animate-pulse" /> : <DownloadCloud size={13} />}
                    {allReady ? t('manga_model_all_ready_short') : t('manga_model_download_all')}
                  </button>
                </div>

                <div className="mt-3 grid gap-2">
                  {Object.entries(ENGINE_STAGE_CONFIG_KEYS).map(([stage, configKey]) => {
                    const options = (modelManager.engine_options?.[stage] || []) as MangaModelEngineOption[];
                    const fallback = stage === 'ocr'
                      ? modelManager.default_ocr_model_id
                      : options[0]?.model_id || '';
                    const currentValue = resolveModelOptionValue(
                      getProjectEngineConfigValue(projectTaskConfig || undefined, configKey, fallback),
                      options,
                    );
                    return (
                      <label key={stage} className="grid gap-1.5">
                        <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
                          {getEngineStageLabel(stage, t)}
                        </span>
                        <select
                          value={currentValue}
                          onChange={(event) => onSelectMangaEngine(configKey, event.target.value)}
                          disabled={!hasProject || isBusy}
                          className="h-9 rounded-lg border border-slate-800 bg-slate-900/80 px-2.5 text-xs text-slate-100 outline-none transition-colors focus:border-cyan-300/55 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {options.length === 0 && (
                            <option value="">{t('manga_model_no_stage_options')}</option>
                          )}
                          {options.map((option) => {
                            const disabled = !option.selectable;
                            const statusLabel = getModelOptionDisabledLabel(option, t);
                            const label = [
                              option.display_name || option.model_id,
                              option.hardware_tier ? translateCatalogText('manga_model_tier', option.hardware_tier, t) : '',
                              option.quality_tier ? translateCatalogText('manga_model_tier', option.quality_tier, t) : '',
                              disabled ? statusLabel : '',
                            ].filter(Boolean).join(' · ');
                            return (
                              <option
                                key={option.model_id}
                                value={option.model_id}
                                disabled={disabled}
                              >
                                {label}
                              </option>
                            );
                          })}
                        </select>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="mt-3 grid gap-2">
                {modelPresets.map((preset) => {
                  const isPreparing = busyAction === `download model preset:${preset.preset_id}`;
                  const progress = isPreparing ? clampPercent(activeJobProgress) : 0;
                  const missingCount = Number(preset.missing_count || 0);
                  return (
                    <div key={preset.preset_id} className="rounded-lg border border-slate-800 bg-slate-900/45 px-3 py-2.5">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <PackageCheck size={14} className={preset.available ? 'text-emerald-300' : 'text-cyan-300'} />
                            <div className="truncate text-sm font-semibold text-slate-100">{preset.display_name || preset.preset_id}</div>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] font-semibold uppercase tracking-[0.1em]">
                            <span className="rounded border border-slate-700 bg-slate-950/60 px-1.5 py-0.5 text-slate-300">
                              {preset.effect_label || translateCatalogText('manga_model_tier', preset.quality_tier, t)}
                            </span>
                            <span className="rounded border border-slate-700 bg-slate-950/60 px-1.5 py-0.5 text-slate-300">
                              {translateCatalogText('manga_model_tier', preset.hardware_tier, t)}
                            </span>
                            <span className="rounded border border-slate-700 bg-slate-950/60 px-1.5 py-0.5 text-slate-300">{t('manga_model_count', preset.model_count || preset.model_ids.length)}</span>
                          </div>
                          <div className="mt-1 text-[11px] leading-relaxed text-slate-500">{preset.description}</div>
                          <div className="mt-1 text-[11px] leading-relaxed text-slate-400">
                            {t('manga_model_details')}: {preset.model_ids.join(', ')}
                          </div>
                        </div>
                        {preset.available ? (
                          <StatusPill tone="emerald">{t('manga_ready')}</StatusPill>
                        ) : (
                          <button
                            type="button"
                            onClick={() => onDownloadModelPreset(preset.preset_id)}
                            disabled={isBusy}
                            className="shrink-0 rounded-md border border-cyan-300/25 bg-cyan-300/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-cyan-100 transition-colors hover:border-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {isPreparing ? t('manga_preparing') : t('manga_prepare')}
                          </button>
                        )}
                      </div>
                      {missingCount > 0 && (
                        <div className="mt-2 text-[11px] text-amber-100">{t('manga_model_missing_count', missingCount)}</div>
                      )}
                      {Array.isArray(preset.recommended_for) && preset.recommended_for.length > 0 && (
                        <div className="mt-2 text-[11px] text-slate-400">
                          {t('manga_model_recommended_for')}: {preset.recommended_for.map((item) => translateCatalogText('manga_model_tag', item, t)).join(', ')}
                        </div>
                      )}
                      {Array.isArray(preset.cautions) && preset.cautions.length > 0 && (
                        <div className="mt-1 text-[11px] leading-relaxed text-amber-100">
                          {preset.cautions.map((item) => translateModelCaution(item, t)).join(' ')}
                        </div>
                      )}
                      {isPreparing && (
                        <div className="mt-2">
                          <div className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
                            <span>{t('manga_model_progress')}</span>
                            <span>{progress}%</span>
                          </div>
                          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-950/85">
                            <div className="h-full bg-cyan-300" style={{ width: `${progress}%` }} />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="min-h-0 overflow-y-auto pr-1">
              <div className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-500">
                {t('manga_model_custom_download')}
              </div>
              <div className="grid gap-2">
                {allModels.map((model) => {
                  const isPreparing = busyAction === `download model:${model.model_id}`;
                  return (
                    <details key={model.model_id} className="group rounded-lg border border-slate-800 bg-slate-900/45">
                      <summary className="flex cursor-pointer list-none items-start justify-between gap-3 px-3 py-2.5">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <PackageCheck size={14} className={model.available ? 'text-emerald-300' : 'text-amber-300'} />
                            <div className="truncate text-sm font-semibold text-slate-100">{model.display_name || model.model_id}</div>
                          </div>
                          <div className="mt-0.5 truncate text-[11px] text-slate-500" title={model.repo_id}>{model.repo_id || model.model_id}</div>
                          <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] uppercase tracking-[0.1em] text-slate-400">
                            {model.stage && <span className="rounded border border-slate-700 px-1.5 py-0.5">{getEngineStageLabel(model.stage, t)}</span>}
                            {model.hardware_tier && <span className="rounded border border-slate-700 px-1.5 py-0.5">{translateCatalogText('manga_model_tier', model.hardware_tier, t)}</span>}
                            {model.quality_tier && <span className="rounded border border-slate-700 px-1.5 py-0.5">{translateCatalogText('manga_model_tier', model.quality_tier, t)}</span>}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {model.available ? (
                            <StatusPill tone="emerald">{t('manga_ready')}</StatusPill>
                          ) : (
                            <button
                              type="button"
                              onClick={(event) => {
                                event.preventDefault();
                                onDownloadModel(model.model_id);
                              }}
                              disabled={isBusy}
                              className="rounded-md border border-amber-300/25 bg-amber-300/10 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100 transition-colors hover:border-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {isPreparing ? t('manga_preparing') : t('manga_prepare')}
                            </button>
                          )}
                          <ChevronDown size={14} className="text-slate-500 transition-transform group-open:rotate-180" />
                        </div>
                      </summary>

                      <div className="space-y-2 border-t border-slate-800 px-3 py-3">
                        <div className="text-xs leading-relaxed text-slate-400">
                          {translateModelDescription(model.model_id, model.description || '', t)}
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-500 max-md:grid-cols-1">
                          <div className="rounded-md border border-slate-800 bg-slate-950/45 px-2 py-1.5">
                            <span className="text-slate-600">ID</span>
                            <div className="mt-0.5 break-all text-slate-300">{model.model_id}</div>
                          </div>
                          <div className="rounded-md border border-slate-800 bg-slate-950/45 px-2 py-1.5">
                            <span className="text-slate-600">{t('manga_storage')}</span>
                            <div className="mt-0.5 truncate text-slate-300" title={model.snapshot_path || model.runtime_assets_path || '-'}>
                              {model.snapshot_path || model.runtime_assets_path || '-'}
                            </div>
                          </div>
                        </div>
                        {Array.isArray(model.recommended_for) && model.recommended_for.length > 0 && (
                          <div className="text-[11px] text-slate-400">
                            {t('manga_model_recommended_for')}: {model.recommended_for.map((item) => translateCatalogText('manga_model_tag', item, t)).join(', ')}
                          </div>
                        )}
                        {Array.isArray(model.aliases) && model.aliases.length > 0 && (
                          <div className="text-[11px] text-slate-500">{t('manga_model_aliases')}: {model.aliases.join(', ')}</div>
                        )}
                        {Array.isArray(model.runtime_notes) && model.runtime_notes.length > 0 && (
                          <div className="space-y-1 text-[11px] text-slate-500">
                            {model.runtime_notes.map((note) => (
                              <div key={note}>- {translateModelRuntimeNote(model.model_id, note, t)}</div>
                            ))}
                          </div>
                        )}
                        {Array.isArray(model.cautions) && model.cautions.length > 0 && (
                          <div className="rounded-md border border-amber-300/20 bg-amber-300/10 px-2 py-1.5 text-[11px] leading-relaxed text-amber-100">
                            {model.cautions.map((item) => translateModelCaution(item, t)).join(' ')}
                          </div>
                        )}
                      </div>
                    </details>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
