export type MangaViewMode = 'rendered' | 'original' | 'overlay' | 'inpainted';

export type MangaTranslator = (key: string, ...args: any[]) => string;

export const translateMangaEnum = (prefix: string, value: string, t: MangaTranslator): string => {
  if (!value) return '';
  const key = `${prefix}_${value}`;
  const translated = t(key);
  return translated === key ? value : translated;
};

export interface MangaBlockDraft {
  bbox: number[];
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
  packages: Array<{
    modelId: string;
    label: string;
    repoId: string;
    available: boolean;
    runtimeSupported: boolean;
    runtimeEngineId: string;
    storagePath: string;
    readinessStatus?: string;
    readinessMessageKey?: string;
    readinessMessageArgs?: any[];
    actionHintKey?: string;
    actionHintArgs?: any[];
    missingModules?: string[];
    missingAssetPaths?: string[];
  }>;
}

export interface MangaCanvasCommand {
  kind: 'fit' | 'actual' | 'focusBox';
  token: number;
  bbox?: number[];
  label?: string;
}

export interface MangaCanvasPointer {
  x: number;
  y: number;
  normalizedX: number;
  normalizedY: number;
}

export interface MangaCanvasRuntimeBox {
  bbox: number[];
  label: string;
  tone?: 'cyan' | 'amber' | 'emerald' | 'rose';
}

export interface MangaCanvasRuntimeOverlay {
  stage: string;
  title: string;
  imageUrl: string;
  boxes: MangaCanvasRuntimeBox[];
  message: string;
}

export type MangaBrushStrokeMode = 'brush' | 'restore';

export interface MangaBrushStrokePoint {
  x: number;
  y: number;
}

export interface MangaBrushStrokePayload {
  mode: MangaBrushStrokeMode;
  radius: number;
  points: MangaBrushStrokePoint[];
}

export type MangaOverlayLayerKey = 'sourceReference' | 'segment' | 'bubble' | 'brush' | 'restore' | 'overlay';

export interface MangaLayerControl {
  visible: boolean;
  opacity: number;
}

export type MangaLayerControls = Record<MangaOverlayLayerKey, MangaLayerControl>;
