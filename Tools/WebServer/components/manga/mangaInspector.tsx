import React from 'react';

import { MangaPageDetail, MangaTextBlock } from '../../types/manga';
import { MangaActiveJobSummary, MangaBlockDraft, MangaEngineCard } from './shared';

export interface MangaInspectorProps {
  page: MangaPageDetail | null;
  activeBlock: MangaTextBlock | null;
  activeBlockDraft: MangaBlockDraft | null;
  activeJob: MangaActiveJobSummary | null;
  engineCards: MangaEngineCard[];
}

export const MangaInspector: React.FC<MangaInspectorProps> = ({
  page,
  activeBlock,
  activeBlockDraft,
  activeJob,
  engineCards,
}) => {
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
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Inspector</div>
        <div className="mt-2 text-sm text-slate-300">
          {page ? `${page.width} × ${page.height} · ${page.status}` : 'No page selected'}
        </div>
        {activeBlock && (
          <div className="mt-2 text-xs text-slate-500">
            Active block: <span className="text-slate-200">{activeBlock.block_id}</span>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-b border-slate-900">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Active Block</div>
        {!activeBlock ? (
          <div className="mt-3 rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-4 py-5 text-sm text-slate-500">
            Select a text block from the canvas or block list to inspect placement and style.
          </div>
        ) : (
          <div className="mt-3 space-y-3">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-100">{activeBlock.block_id}</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{activeBlock.origin}</div>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Position</div>
                  <div className="mt-1 text-slate-200">
                    x {activeBlock.bbox[0]} · y {activeBlock.bbox[1]}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Size</div>
                  <div className="mt-1 text-slate-200">
                    {blockWidth} × {blockHeight}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Direction</div>
                  <div className="mt-1 text-slate-200">
                    {activeBlock.source_direction} → {activeBlock.rendered_direction}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Placement</div>
                  <div className="mt-1 text-slate-200">
                    {activeBlock.placement_mode} · {activeBlock.editable ? 'editable' : 'locked'}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Confidence</div>
                  <div className="mt-1 text-slate-200">{activeBlock.ocr_confidence.toFixed(3)}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Flags</div>
                  <div className="mt-1 text-slate-200">{activeBlock.flags.join(', ') || 'no flags'}</div>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Text Preview</div>
              <div className="mt-2 text-xs text-slate-500">OCR</div>
              <div className="mt-1 whitespace-pre-wrap text-sm text-slate-200">{sourcePreview || 'No OCR text'}</div>
              <div className="mt-3 text-xs text-slate-500">Translation</div>
              <div className="mt-1 whitespace-pre-wrap text-sm text-slate-100">{translationPreview || 'No translation yet'}</div>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Render Style</div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Font</div>
                  <div className="mt-1 text-slate-200 break-all">{fontFamily || '-'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Font Prediction</div>
                  <div className="mt-1 text-slate-200 break-all">{activeBlock.font_prediction || '-'}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Font Size</div>
                  <div className="mt-1 text-slate-200">{fontSize}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Line Spacing</div>
                  <div className="mt-1 text-slate-200">{lineSpacing}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Fill</div>
                  <div className="mt-1 flex items-center gap-2 text-slate-200">
                    <span className="h-4 w-4 rounded border border-slate-700" style={{ backgroundColor: fill }} />
                    {fill}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">Stroke</div>
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
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Task Status</div>
        <div className="mt-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
          {activeJob ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-100">{activeJob.stageLabel}</div>
                <div className={`text-[10px] uppercase tracking-[0.18em] ${activeJob.status === 'failed' ? 'text-rose-300' : 'text-cyan-300'}`}>
                  {activeJob.status}
                </div>
              </div>
              <div className="mt-3 h-2 rounded-full bg-slate-950/80 overflow-hidden">
                <div
                  className={`h-full ${activeJob.status === 'failed' ? 'bg-rose-400' : 'bg-cyan-400'}`}
                  style={{ width: `${Math.max(0, Math.min(100, activeJob.progress || 0))}%` }}
                />
              </div>
              <div className="mt-3 text-sm text-slate-300">{activeJob.message || 'Waiting for job details.'}</div>
            </>
          ) : (
            <div className="text-sm text-slate-500">No active page or batch job.</div>
          )}
        </div>
      </div>

      <div className="px-4 py-3 border-b border-slate-900">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Engine Status</div>
        <div className="mt-3 grid gap-2">
          {engineCards.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-4 py-5 text-sm text-slate-500">
              Engine status is not available until a project scene has been loaded.
            </div>
          )}
          {engineCards.map((card) => (
            <div key={card.label} className="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-100">{card.label}</div>
                <div className={`text-[10px] uppercase tracking-[0.18em] ${card.available ? 'text-emerald-300' : 'text-amber-300'}`}>
                  {card.available ? 'ready' : 'missing'}
                </div>
              </div>
              <div className="mt-2 text-xs text-slate-500">Configured</div>
              <div className="text-sm text-slate-300 break-all">{card.configured}</div>
              <div className="mt-2 text-xs text-slate-500">Runtime</div>
              <div className="text-sm text-slate-300 break-all">{card.runtime}</div>
              <div className="mt-2 text-xs text-slate-500">Package</div>
              <div className="text-sm text-slate-300 break-all">{card.packageLabel}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
};
