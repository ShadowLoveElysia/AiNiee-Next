import React from 'react';

import { MangaScenePageSummary } from '../../types/manga';

export interface MangaPageStripProps {
  pages: MangaScenePageSummary[];
  selectedPageId: string;
  selectedPageIds: string[];
  currentPageId: string;
  onSelectPage: (pageId: string) => void;
  onTogglePageSelection: (pageId: string) => void;
}

export const MangaPageStrip: React.FC<MangaPageStripProps> = ({
  pages,
  selectedPageId,
  selectedPageIds,
  currentPageId,
  onSelectPage,
  onTogglePageSelection,
}) => {
  return (
    <aside className="w-[290px] border-r border-slate-900 bg-slate-950/80 overflow-y-auto">
      <div className="px-4 py-3 text-xs uppercase tracking-[0.24em] text-slate-500 border-b border-slate-900">Pages</div>
      <div className="p-3 space-y-3">
        {pages.map((scenePage) => (
          <button
            key={scenePage.page_id}
            onClick={() => onSelectPage(scenePage.page_id)}
            className={`w-full text-left rounded-2xl border overflow-hidden transition-colors ${
              selectedPageId === scenePage.page_id
                ? 'border-primary bg-primary/10 shadow-[0_0_0_1px_rgba(34,211,238,0.18)]'
                : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
            }`}
          >
            <div className="px-3 py-2 border-b border-slate-800/80 flex items-center justify-between">
              <label
                className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500"
                onClick={(event) => event.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={selectedPageIds.includes(scenePage.page_id)}
                  onChange={() => onTogglePageSelection(scenePage.page_id)}
                  className="w-4 h-4 rounded border-slate-700 text-primary bg-slate-950"
                />
                Select
              </label>
              <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{scenePage.status}</span>
            </div>
            <div className="aspect-[2/3] bg-slate-950 flex items-center justify-center overflow-hidden">
              <img src={scenePage.thumbnail_url} alt={scenePage.page_id} className="w-full h-full object-cover" />
            </div>
            <div className="px-3 py-2 flex items-center justify-between gap-3">
              <span className="text-sm font-semibold">Page {scenePage.index}</span>
              {currentPageId === scenePage.page_id && (
                <span className="text-[10px] uppercase tracking-[0.18em] text-primary">Current</span>
              )}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
};
