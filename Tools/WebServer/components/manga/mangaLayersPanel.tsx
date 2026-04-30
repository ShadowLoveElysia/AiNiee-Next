import React from 'react';
import { ChevronDown } from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaPageDetail } from '../../types/manga';
import { MangaLayerControls, MangaOverlayLayerKey, MangaViewMode } from './shared';

export interface MangaLayersPanelProps {
  page: MangaPageDetail | null;
  viewMode: MangaViewMode;
  layerControls: MangaLayerControls;
  brushRadius: number;
  onToggleLayer: (layer: MangaOverlayLayerKey) => void;
  onSetLayerOpacity: (layer: MangaOverlayLayerKey, opacity: number) => void;
  onSetBrushRadius: (radius: number) => void;
}

const LAYER_LABELS: Record<MangaOverlayLayerKey, string> = {
  sourceReference: 'manga_layer_source_reference',
  segment: 'manga_layer_segment_mask',
  bubble: 'manga_layer_bubble_mask',
  brush: 'manga_layer_brush_mask',
  restore: 'manga_layer_restore_mask',
  overlay: 'manga_layer_text_overlay',
};

const getCurrentBaseLabelKey = (page: MangaPageDetail, viewMode: MangaViewMode) => {
  if (viewMode === 'overlay') {
    if (page.layers.rendered_url) return 'manga_layer_rendered';
    if (page.layers.inpainted_url) return 'manga_layer_inpainted';
    return 'manga_layer_source';
  }
  return `manga_view_${viewMode}`;
};

export const MangaLayersPanel: React.FC<MangaLayersPanelProps> = ({
  page,
  viewMode,
  layerControls,
  brushRadius,
  onToggleLayer,
  onSetLayerOpacity,
  onSetBrushRadius,
}) => {
  const { t } = useI18n();
  const layerKeys: MangaOverlayLayerKey[] = viewMode === 'overlay'
    ? ['sourceReference', 'segment', 'bubble', 'brush', 'restore', 'overlay']
    : ['segment', 'bubble', 'brush', 'restore', 'overlay'];
  const baseEntries = page ? [
    [t('manga_layer_current_base'), t(getCurrentBaseLabelKey(page, viewMode))],
    [t('manga_layer_source'), page.layers.source_url],
    [t('manga_layer_rendered'), page.layers.rendered_url],
    [t('manga_layer_inpainted'), page.layers.inpainted_url],
    [t('manga_layer_overlay_json'), page.layers.overlay_text_url],
  ] : [];

  return (
    <div className="border-b border-slate-900 px-3 py-2">
      <details className="group rounded-xl border border-slate-800/85 bg-slate-900/45">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5">
          <div className="min-w-0">
            <div className="text-xs font-bold uppercase tracking-[0.18em] text-slate-400">{t('manga_panel_layers')}</div>
            <div className="mt-0.5 truncate text-[11px] text-slate-500">{page ? t(`manga_view_${viewMode}`) : t('manga_no_page_selected')}</div>
          </div>
          <ChevronDown size={15} className="shrink-0 text-slate-500 transition-transform group-open:rotate-180" />
        </summary>

        <div className="space-y-3 border-t border-slate-800/75 px-3 py-3">
          <div className="grid grid-cols-2 gap-2 text-xs">
            {baseEntries.map(([label, value]) => (
              <div key={label} className="rounded-lg border border-slate-800 bg-slate-950/45 px-2.5 py-2">
                <div className="text-slate-500 uppercase tracking-[0.16em]">{label}</div>
                <div className="truncate mt-1 text-slate-300" title={value}>{value}</div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-slate-200">{t('manga_brush_radius')}</span>
              <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{brushRadius}px</span>
            </div>
            <input
              type="range"
              min="4"
              max="96"
              step="1"
              value={brushRadius}
              onChange={(event) => onSetBrushRadius(Number(event.target.value))}
              className="mt-3 w-full accent-primary"
            />
          </div>

          {layerKeys.map((layerKey) => (
            <div key={layerKey} className="rounded-lg border border-slate-800 bg-slate-950/45 px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    checked={layerControls[layerKey].visible}
                    onChange={() => onToggleLayer(layerKey)}
                    className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-primary"
                  />
                  {t(LAYER_LABELS[layerKey])}
                </label>
                <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">
                  {Math.round(layerControls[layerKey].opacity * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={layerControls[layerKey].opacity}
                onChange={(event) => onSetLayerOpacity(layerKey, Number(event.target.value))}
                className="mt-3 w-full accent-primary"
              />
            </div>
          ))}
        </div>
      </details>
    </div>
  );
};
