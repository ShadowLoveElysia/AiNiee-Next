export type MangaViewMode = 'rendered' | 'original' | 'overlay' | 'inpainted';

export interface MangaBlockDraft {
  source_text: string;
  translation: string;
  font_family: string;
  font_size: number;
  line_spacing: number;
  fill: string;
  stroke_color: string;
  stroke_width: number;
}

export interface MangaActiveJobSummary {
  stageLabel: string;
  progress: number;
  status: string;
  message: string;
}

export interface MangaEngineCard {
  label: string;
  configured: string;
  runtime: string;
  available: boolean;
  packageLabel: string;
}

export interface MangaCanvasCommand {
  kind: 'fit' | 'actual';
  token: number;
}

export interface MangaCanvasPointer {
  x: number;
  y: number;
  normalizedX: number;
  normalizedY: number;
}

export type MangaOverlayLayerKey = 'segment' | 'bubble' | 'brush' | 'overlay';

export interface MangaLayerControl {
  visible: boolean;
  opacity: number;
}

export type MangaLayerControls = Record<MangaOverlayLayerKey, MangaLayerControl>;
