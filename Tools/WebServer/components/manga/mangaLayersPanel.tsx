import React from 'react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaPageDetail } from '../../types/manga';
import { MangaLayerControls, MangaOverlayLayerKey, MangaViewMode } from './shared';

export interface MangaLayersPanelProps {
  page: MangaPageDetail | null;
  viewMode: MangaViewMode;
  layerControls: MangaLayerControls;
  onToggleLayer: (layer: MangaOverlayLayerKey) => void;
  onSetLayerOpacity: (layer: MangaOverlayLayerKey, opacity: number) => void;
}

const LAYER_LABELS: Record<MangaOverlayLayerKey, string> = {
  segment: 'manga_layer_segment_mask',
  bubble: 'manga_layer_bubble_mask',
  brush: 'manga_layer_brush_mask',
  overlay: 'manga_layer_text_overlay',
};

export const MangaLayersPanel: React.FC<MangaLayersPanelProps> = ({
  page,
  viewMode,
  layerControls,
  onToggleLayer,
  onSetLayerOpacity,
}) => {
  const { t } = useI18n();
  const baseEntries = page ? [
    [t('manga_layer_current_base'), t(`manga_view_${viewMode}`)],
    [t('manga_layer_source'), page.layers.source_url],
    [t('manga_layer_rendered'), page.layers.rendered_url],
    [t('manga_layer_inpainted'), page.layers.inpainted_url],
    [t('manga_layer_overlay_json'), page.layers.overlay_text_url],
  ] : [];

  return (
    <div className="px-4 py-3 border-b border-slate-900">
      <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_panel_layers')}</div>
      <div className="mt-3 space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs">
          {baseEntries.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
              <div className="text-slate-500 uppercase tracking-[0.18em]">{label}</div>
              <div className="truncate mt-1 text-slate-300" title={value}>{value}</div>
            </div>
          ))}
        </div>

        {(['segment', 'bubble', 'brush', 'overlay'] as MangaOverlayLayerKey[]).map((layerKey) => (
          <div key={layerKey} className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
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
    </div>
  );
};
