import React from 'react';

import { MangaPageDetail } from '../../types/manga';
import { MangaBlockDraft } from './shared';

export interface MangaBlocksPanelProps {
  page: MangaPageDetail | null;
  blockDrafts: Record<string, MangaBlockDraft>;
  activeBlockId: string;
  busyAction: string;
  hasProject: boolean;
  onSelectBlock: (blockId: string) => void;
  onUpdateDraft: (blockId: string, patch: Partial<MangaBlockDraft>) => void;
  onSavePageChanges: () => void;
}

export const MangaBlocksPanel: React.FC<MangaBlocksPanelProps> = ({
  page,
  blockDrafts,
  activeBlockId,
  busyAction,
  hasProject,
  onSelectBlock,
  onUpdateDraft,
  onSavePageChanges,
}) => {
  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Blocks</div>
        <button
          onClick={onSavePageChanges}
          disabled={!hasProject || !page || !!busyAction}
          className="px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-xs uppercase tracking-[0.18em] text-slate-300 disabled:opacity-50"
        >
          Save Page Changes
        </button>
      </div>

      <div className="mt-3 space-y-3">
        {(page?.blocks || []).length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-500">
            No editable text blocks yet. Run `OCR`, `Translate Current`, `Translate Selected`, or `Plan Selected` to generate editable overlay blocks.
          </div>
        )}

        {(page?.blocks || []).map((block) => {
          const draft = blockDrafts[block.block_id];
          const isActive = block.block_id === activeBlockId;

          return (
            <div
              key={block.block_id}
              onClick={() => onSelectBlock(block.block_id)}
              className={`rounded-2xl border p-4 transition-colors cursor-pointer ${
                isActive
                  ? 'border-primary bg-primary/10 shadow-[0_0_0_1px_rgba(34,211,238,0.18)]'
                  : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold text-slate-200">{block.block_id}</div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{block.origin}</div>
              </div>

              <div className="mt-2 text-xs text-slate-500">
                bbox {block.bbox.join(', ')} · {block.rendered_direction} · {block.flags.join(', ') || 'no flags'}
              </div>

              <div className="mt-3 text-xs text-slate-500">OCR</div>
              <textarea
                value={draft?.source_text ?? block.source_text ?? ''}
                onChange={(event) => onUpdateDraft(block.block_id, { source_text: event.target.value })}
                className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 min-h-[78px] outline-none focus:border-primary"
              />

              <div className="mt-3 text-xs text-slate-500">Translation</div>
              <textarea
                value={draft?.translation ?? block.translation ?? ''}
                onChange={(event) => onUpdateDraft(block.block_id, { translation: event.target.value })}
                className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 min-h-[92px] outline-none focus:border-primary"
              />

              <div className="mt-3 grid grid-cols-3 gap-3">
                <label className="col-span-3 text-xs text-slate-500">
                  Font Family
                  <input
                    type="text"
                    value={draft?.font_family ?? block.style.font_family}
                    onChange={(event) => onUpdateDraft(block.block_id, { font_family: event.target.value })}
                    className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                  />
                </label>

                <label className="text-xs text-slate-500">
                  Font Size
                  <input
                    type="number"
                    value={draft?.font_size ?? block.style.font_size}
                    onChange={(event) => onUpdateDraft(block.block_id, { font_size: Number(event.target.value || block.style.font_size) })}
                    className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                  />
                </label>

                <label className="text-xs text-slate-500">
                  Line Spacing
                  <input
                    type="number"
                    step="0.05"
                    value={draft?.line_spacing ?? block.style.line_spacing}
                    onChange={(event) => onUpdateDraft(block.block_id, { line_spacing: Number(event.target.value || block.style.line_spacing) })}
                    className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                  />
                </label>

                <label className="text-xs text-slate-500">
                  Fill
                  <input
                    type="color"
                    value={draft?.fill ?? block.style.fill}
                    onChange={(event) => onUpdateDraft(block.block_id, { fill: event.target.value })}
                    className="mt-1 h-[42px] w-full rounded-xl border border-slate-800 bg-slate-950/70 px-1 py-1"
                  />
                </label>

                <label className="text-xs text-slate-500">
                  Stroke Color
                  <input
                    type="color"
                    value={draft?.stroke_color ?? block.style.stroke_color}
                    onChange={(event) => onUpdateDraft(block.block_id, { stroke_color: event.target.value })}
                    className="mt-1 h-[42px] w-full rounded-xl border border-slate-800 bg-slate-950/70 px-1 py-1"
                  />
                </label>

                <label className="text-xs text-slate-500">
                  Stroke
                  <input
                    type="number"
                    value={draft?.stroke_width ?? block.style.stroke_width}
                    onChange={(event) => onUpdateDraft(block.block_id, { stroke_width: Number(event.target.value || block.style.stroke_width) })}
                    className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                  />
                </label>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
