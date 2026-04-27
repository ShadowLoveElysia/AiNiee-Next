import React from 'react';

import { useI18n } from '../../contexts/I18nContext';
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

const previewText = (value: string, emptyLabel: string) => {
  const trimmed = value.trim().replace(/\s+/g, ' ');
  return trimmed.length > 46 ? `${trimmed.slice(0, 46)}...` : trimmed || emptyLabel;
};

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
  const { t } = useI18n();
  const blocks = page?.blocks || [];

  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_blocks_title')}</div>
          <div className="mt-1 text-xs text-slate-600">{t('manga_editable_block_count', blocks.length)}</div>
        </div>
        <button
          type="button"
          onClick={onSavePageChanges}
          disabled={!hasProject || !page || !!busyAction}
          className="rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs font-semibold text-slate-300 transition-colors hover:border-primary disabled:opacity-50"
        >
          {t('manga_action_save')}
        </button>
      </div>

      <div className="mt-3 space-y-2">
        {blocks.length === 0 && (
          <div className="rounded-lg border border-dashed border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-500">
            {t('manga_blocks_empty')}
          </div>
        )}

        {blocks.map((block, index) => {
          const draft = blockDrafts[block.block_id];
          const isActive = block.block_id === activeBlockId;
          const sourceText = draft?.source_text ?? block.source_text ?? '';
          const translation = draft?.translation ?? block.translation ?? '';

          return (
            <section
              key={block.block_id}
              className={`rounded-lg border transition-colors ${
                isActive
                  ? 'border-primary/70 bg-primary/10 shadow-[0_0_0_1px_rgba(34,211,238,0.16)]'
                  : 'border-slate-800 bg-slate-900/58 hover:border-slate-700'
              }`}
            >
              <button
                type="button"
                onClick={() => onSelectBlock(block.block_id)}
                className="flex w-full items-center gap-3 px-3 py-2 text-left"
              >
                <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                  isActive ? 'bg-primary text-slate-950' : 'bg-slate-700 text-slate-200'
                }`}>
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1">
                    <span className="rounded-md bg-slate-800 px-1.5 py-0.5 text-[10px] font-bold text-slate-300">{t('manga_ocr_label')}</span>
                    <span className="rounded-md bg-primary/20 px-1.5 py-0.5 text-[10px] font-bold text-primary">{t('manga_tl_label')}</span>
                    <span className="truncate text-sm font-semibold text-slate-200">{previewText(translation || sourceText, t('manga_empty_block'))}</span>
                  </span>
                  <span className="mt-1 block truncate text-xs text-slate-500">
                    {block.origin} · {block.rendered_direction} · bbox {block.bbox.join(', ')}
                  </span>
                </span>
              </button>

              {isActive && (
                <div className="border-t border-slate-800/90 px-3 py-3">
                  <label className="block text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                    {t('manga_ocr_label')}
                    <textarea
                      value={sourceText}
                      onChange={(event) => onUpdateDraft(block.block_id, { source_text: event.target.value })}
                      className="mt-1 min-h-[72px] w-full rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none transition-colors focus:border-primary"
                    />
                  </label>

                  <label className="mt-3 block text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                    {t('manga_translation_label')}
                    <textarea
                      value={translation}
                      onChange={(event) => onUpdateDraft(block.block_id, { translation: event.target.value })}
                      className="mt-1 min-h-[88px] w-full rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 outline-none transition-colors focus:border-primary"
                    />
                  </label>

                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <label className="col-span-3 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {t('manga_field_font')}
                      <input
                        type="text"
                        value={draft?.font_family ?? block.style.font_family}
                        onChange={(event) => onUpdateDraft(block.block_id, { font_family: event.target.value })}
                        className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                      />
                    </label>

                    <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {t('manga_field_size')}
                      <input
                        type="number"
                        value={draft?.font_size ?? block.style.font_size}
                        onChange={(event) => onUpdateDraft(block.block_id, { font_size: Number(event.target.value || block.style.font_size) })}
                        className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950/70 px-2 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                      />
                    </label>

                    <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {t('manga_field_stroke')}
                      <input
                        type="number"
                        value={draft?.stroke_width ?? block.style.stroke_width}
                        onChange={(event) => onUpdateDraft(block.block_id, { stroke_width: Number(event.target.value || block.style.stroke_width) })}
                        className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950/70 px-2 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                      />
                    </label>

                    <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {t('manga_field_leading')}
                      <input
                        type="number"
                        step="0.05"
                        value={draft?.line_spacing ?? block.style.line_spacing}
                        onChange={(event) => onUpdateDraft(block.block_id, { line_spacing: Number(event.target.value || block.style.line_spacing) })}
                        className="mt-1 w-full rounded-md border border-slate-800 bg-slate-950/70 px-2 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                      />
                    </label>

                    <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {t('manga_field_fill')}
                      <input
                        type="color"
                        value={draft?.fill ?? block.style.fill}
                        onChange={(event) => onUpdateDraft(block.block_id, { fill: event.target.value })}
                        className="mt-1 h-10 w-full rounded-md border border-slate-800 bg-slate-950/70 px-1 py-1"
                      />
                    </label>

                    <label className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                      {t('manga_field_border')}
                      <input
                        type="color"
                        value={draft?.stroke_color ?? block.style.stroke_color}
                        onChange={(event) => onUpdateDraft(block.block_id, { stroke_color: event.target.value })}
                        className="mt-1 h-10 w-full rounded-md border border-slate-800 bg-slate-950/70 px-1 py-1"
                      />
                    </label>
                  </div>
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
};
