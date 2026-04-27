import React from 'react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaPageDetail, MangaRuntimeValidationResult, MangaTextBlock } from '../../types/manga';
import { MangaActiveJobSummary, MangaBlockDraft, MangaEngineCard, translateMangaEnum } from './shared';

export interface MangaInspectorProps {
  page: MangaPageDetail | null;
  activeBlock: MangaTextBlock | null;
  activeBlockDraft: MangaBlockDraft | null;
  activeJob: MangaActiveJobSummary | null;
  engineCards: MangaEngineCard[];
  runtimeValidation: MangaRuntimeValidationResult | null;
  busyAction: string;
  onDownloadModel: (modelId: string) => void;
}

export const MangaInspector: React.FC<MangaInspectorProps> = ({
  page,
  activeBlock,
  activeBlockDraft,
  activeJob,
  engineCards,
  runtimeValidation,
  busyAction,
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

  return (
    <>
      <div className="px-4 py-3 border-b border-slate-900">
        <div className="flex items-center gap-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs font-semibold text-slate-200">{t('manga_panel_render')}</div>
          <div className="rounded-lg border border-transparent px-3 py-2 text-xs font-semibold text-slate-500">{t('manga_panel_layers')}</div>
        </div>
        <div className="mt-3 text-sm text-slate-300">
          {page ? `${page.width} × ${page.height} · ${translateMangaEnum('manga_state', page.status, t)}` : t('manga_no_page_selected')}
        </div>
        {activeBlock && (
          <div className="mt-2 text-xs text-slate-500">
            {t('manga_active_block_inline')} <span className="text-slate-200">{activeBlock.block_id}</span>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-b border-slate-900">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_panel_active_block')}</div>
        {!activeBlock ? (
          <div className="mt-3 rounded-lg border border-dashed border-slate-800 bg-slate-900/40 px-4 py-5 text-sm text-slate-500">
            {t('manga_active_block_empty')}
          </div>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-100">{activeBlock.block_id}</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{activeBlock.origin}</div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_position')}</div>
                  <div className="mt-1 text-slate-200">
                    x {activeBlock.bbox[0]} · y {activeBlock.bbox[1]}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_size')}</div>
                  <div className="mt-1 text-slate-200">
                    {blockWidth} × {blockHeight}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_direction')}</div>
                  <div className="mt-1 text-slate-200">
                    {activeBlock.source_direction} → {activeBlock.rendered_direction}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_placement')}</div>
                  <div className="mt-1 text-slate-200">
                    {activeBlock.placement_mode} · {activeBlock.editable ? t('manga_editable') : t('manga_locked')}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_confidence')}</div>
                  <div className="mt-1 text-slate-200">{activeBlock.ocr_confidence.toFixed(3)}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_flags')}</div>
                  <div className="mt-1 text-slate-200">{activeBlock.flags.join(', ') || t('manga_no_flags')}</div>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_text_preview')}</div>
              <div className="mt-2 text-xs text-slate-500">{t('manga_ocr_label')}</div>
              <div className="mt-1 whitespace-pre-wrap text-sm text-slate-200">{sourcePreview || t('manga_no_ocr_text')}</div>
              <div className="mt-3 text-xs text-slate-500">{t('manga_translation_label')}</div>
              <div className="mt-1 whitespace-pre-wrap text-sm text-slate-100">{translationPreview || t('manga_no_translation_yet')}</div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_render_style')}</div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_font')}</div>
                  <div className="mt-1 text-slate-200 break-all">{fontFamily || '-'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_font_prediction')}</div>
                  <div className="mt-1 text-slate-200 break-all">{activeBlock.font_prediction || '-'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_font_size')}</div>
                  <div className="mt-1 text-slate-200">{fontSize}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_line_spacing')}</div>
                  <div className="mt-1 text-slate-200">{lineSpacing}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_fill')}</div>
                  <div className="mt-1 flex items-center gap-2 text-slate-200">
                    <span className="h-4 w-4 rounded border border-slate-700" style={{ backgroundColor: fill }} />
                    {fill}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{t('manga_field_stroke')}</div>
                  <div className="mt-1 flex items-center gap-2 text-slate-200">
                    <span className="h-4 w-4 rounded border border-slate-700" style={{ backgroundColor: strokeColor }} />
                    {strokeColor} · {strokeWidth}px
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-b border-slate-900">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_panel_task_status')}</div>
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
          {activeJob ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-100">{activeJob.stageLabel}</div>
                <div className={`text-[10px] uppercase tracking-[0.18em] ${activeJob.status === 'failed' ? 'text-rose-300' : 'text-cyan-300'}`}>
                  {translateMangaEnum('manga_state', activeJob.status, t)}
                </div>
              </div>
              <div className="mt-3 h-2 rounded-full bg-slate-950/80 overflow-hidden">
                <div
                  className={`h-full ${activeJob.status === 'failed' ? 'bg-rose-400' : 'bg-cyan-400'}`}
                  style={{ width: `${Math.max(0, Math.min(100, activeJob.progress || 0))}%` }}
                />
              </div>
              <div className="mt-3 text-sm text-slate-300">{activeJob.message || t('manga_waiting_job_details')}</div>
            </>
          ) : (
            <div className="text-sm text-slate-500">{t('manga_no_active_job')}</div>
          )}
        </div>
      </div>

      <div className="px-4 py-3 border-b border-slate-900">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_panel_engine_status')}</div>
        <div className="mt-3 grid gap-2">
          {engineCards.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/40 px-4 py-5 text-sm text-slate-500">
              {t('manga_engine_status_empty')}
            </div>
          )}
          {engineCards.map((card) => (
            <div key={card.label} className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-100">{card.label}</div>
                <div className={`text-[10px] uppercase tracking-[0.18em] ${card.available ? 'text-emerald-300' : 'text-amber-300'}`}>
                  {card.available ? t('manga_ready') : t('manga_missing')}
                </div>
              </div>
              <div className="mt-2 text-xs text-slate-500">{t('manga_configured')}</div>
              <div className="text-sm text-slate-300 break-all">{card.configured}</div>
              <div className="mt-2 text-xs text-slate-500">{t('manga_runtime')}</div>
              <div className="text-sm text-slate-300 break-all">{card.runtime}</div>
              <div className="mt-2 text-xs text-slate-500">{t('manga_package')}</div>
              <div className="text-sm text-slate-300 break-all">{card.packageLabel}</div>
              {card.packages.length > 0 && (
                <div className="mt-3 space-y-2">
                  {card.packages.map((pkg) => {
                    const isPreparing = busyAction === `download model:${pkg.modelId}`;
                    return (
                      <div key={pkg.modelId} className="rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-xs font-semibold text-slate-200">{pkg.label}</div>
                            <div className="mt-0.5 truncate text-[11px] text-slate-500" title={pkg.repoId || pkg.storagePath}>
                              {pkg.repoId || pkg.storagePath || t('manga_unknown_package')}
                            </div>
                          </div>
                          {pkg.available ? (
                            <span className="shrink-0 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-emerald-200">
                              {t('manga_ready')}
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => onDownloadModel(pkg.modelId)}
                              disabled={Boolean(busyAction)}
                              className="shrink-0 rounded-md border border-amber-300/25 bg-amber-300/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-100 transition-colors hover:border-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {isPreparing ? t('manga_preparing') : t('manga_prepare')}
                            </button>
                          )}
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-500">
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
                        {!pkg.runtimeSupported && (
                          <div className="mt-2 text-[11px] text-slate-500">{t('manga_model_no_runtime_bridge')}</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="px-4 py-3 border-b border-slate-900">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_panel_runtime_validation')}</div>
        {!runtimeValidation ? (
          <div className="mt-3 rounded-lg border border-dashed border-slate-800 bg-slate-900/40 px-4 py-4 text-sm text-slate-500">
            {t('manga_runtime_validation_empty')}
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm font-semibold text-slate-100">{t('manga_page_short')} {runtimeValidation.page_index}</div>
                <div className={`text-[10px] uppercase tracking-[0.18em] ${runtimeValidation.ok ? 'text-emerald-300' : 'text-amber-300'}`}>
                  {runtimeValidation.ok ? t('manga_complete') : t('manga_needs_review')}
                </div>
              </div>
              <div className="mt-2 text-xs text-slate-500 break-all">{runtimeValidation.output_dir}</div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-2">
                  <div className="uppercase tracking-[0.16em] text-slate-500">{t('manga_summary_runtime')}</div>
                  <div className="mt-1 text-sm font-semibold text-emerald-200">{runtimeValidation.summary?.runtime_stage_count ?? 0}</div>
                </div>
                <div className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-2">
                  <div className="uppercase tracking-[0.16em] text-slate-500">{t('manga_summary_fallback')}</div>
                  <div className="mt-1 text-sm font-semibold text-amber-200">{runtimeValidation.summary?.fallback_stage_count ?? 0}</div>
                </div>
                <div className="rounded-md border border-slate-800 bg-slate-950/50 px-2 py-2">
                  <div className="uppercase tracking-[0.16em] text-slate-500">{t('manga_summary_seeds')}</div>
                  <div className="mt-1 text-sm font-semibold text-cyan-200">{runtimeValidation.summary?.seed_count ?? 0}</div>
                </div>
              </div>
            </div>
            {runtimeValidation.stages.map((stage) => (
              <div key={stage.stage} className="rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold capitalize text-slate-100">{translateMangaEnum('manga_runtime_stage', stage.stage, t)}</div>
                  <div className={`text-[10px] uppercase tracking-[0.18em] ${
                    stage.execution_mode === 'configured_runtime'
                      ? 'text-emerald-300'
                      : stage.execution_mode === 'fallback_runtime'
                        ? 'text-cyan-300'
                        : stage.execution_mode === 'failed'
                          ? 'text-rose-300'
                          : 'text-amber-300'
                  }`}>
                    {translateMangaEnum('manga_execution_mode', stage.execution_mode || (stage.used_runtime ? 'configured_runtime' : 'heuristic_fallback'), t)}
                  </div>
                </div>
                <div className="mt-2 text-xs text-slate-500">{t('manga_runtime')}</div>
                <div className="text-sm text-slate-300 break-all">{stage.runtime_engine_id || '-'}</div>
                <div className="mt-2 text-xs text-slate-500">{t('manga_elapsed_ms', stage.elapsed_ms)}</div>
                {(stage.warning_message || stage.error_message) && (
                  <div className="mt-2 rounded-md border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs text-amber-100">
                    {stage.error_message || stage.warning_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
};
