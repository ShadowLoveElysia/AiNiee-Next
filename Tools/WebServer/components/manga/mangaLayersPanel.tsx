import React from 'react';

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
  segment: 'Segment Mask',
  bubble: 'Bubble Mask',
  brush: 'Brush Mask',
  overlay: 'Text Overlay',
};

export const MangaLayersPanel: React.FC<MangaLayersPanelProps> = ({
  page,
  viewMode,
  layerControls,
  onToggleLayer,
  onSetLayerOpacity,
}) => {
  const baseEntries = page ? [
    ['Current Base', viewMode],
    ['Source', page.layers.source_url],
    ['Rendered', page.layers.rendered_url],
    ['Inpainted', page.layers.inpainted_url],
    ['Overlay JSON', page.layers.overlay_text_url],
  ] : [];

  return (
    <div className="px-4 py-3 border-b border-slate-900">
      <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Layers</div>
      <div className="mt-3 space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs">
          {baseEntries.map(([label, value]) => (
            <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2">
              <div className="text-slate-500 uppercase tracking-[0.18em]">{label}</div>
              <div className="truncate mt-1 text-slate-300" title={value}>{value}</div>
            </div>
          ))}
        </div>

        {(['segment', 'bubble', 'brush', 'overlay'] as MangaOverlayLayerKey[]).map((layerKey) => (
          <div key={layerKey} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2">
            <div className="flex items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={layerControls[layerKey].visible}
                  onChange={() => onToggleLayer(layerKey)}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-primary"
                />
                {LAYER_LABELS[layerKey]}
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
