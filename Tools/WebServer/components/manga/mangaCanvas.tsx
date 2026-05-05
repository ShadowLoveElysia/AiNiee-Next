import React, { useEffect, useMemo, useRef, useState } from 'react';
import { MousePointer2, Paintbrush, RotateCcw, SquareDashedMousePointer, Type } from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaPageDetail } from '../../types/manga';
import { MangaActiveJobSummary, MangaBlockDraft, MangaBrushStrokePayload, MangaBrushStrokePoint, MangaCanvasCommand, MangaCanvasPointer, MangaCanvasRuntimeOverlay, MangaLayerControls, MangaViewMode, translateMangaEnum } from './shared';

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

type BlockResizeDirection = 'n' | 's' | 'e' | 'w' | 'nw' | 'ne' | 'sw' | 'se';
type BlockTransformMode = 'move' | `resize-${BlockResizeDirection}`;

interface BlockTransformState {
  pointerId: number;
  blockId: string;
  mode: BlockTransformMode;
  startX: number;
  startY: number;
  startBbox: number[];
}

type CanvasTool = 'select' | 'region' | 'text' | 'brush' | 'restore';
type InlineEditField = 'source_text' | 'translation';

interface InlineEditState {
  blockId: string;
  field: InlineEditField;
}

interface CreateRegionState {
  pointerId: number;
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
}

interface BrushStrokeState {
  pointerId: number;
  mode: 'brush' | 'restore';
  radius: number;
  points: MangaBrushStrokePoint[];
}

interface FocusHighlightState {
  bbox: number[];
  label: string;
}

interface MangaRenderLayoutRun {
  text?: string;
  x?: number;
  y?: number;
  rotate_clockwise?: boolean;
}

interface MangaRenderLayoutPlan {
  block_id?: string;
  direction?: string;
  bbox?: number[];
  font_family?: string;
  font_size?: number;
  line_spacing?: number;
  runs?: MangaRenderLayoutRun[];
}

export interface MangaCanvasProps {
  page: MangaPageDetail | null;
  currentImageUrl: string;
  viewMode: MangaViewMode;
  activeBlockId: string;
  blockDrafts: Record<string, MangaBlockDraft>;
  activeJob: MangaActiveJobSummary | null;
  runtimeOverlay: MangaCanvasRuntimeOverlay | null;
  layerControls: MangaLayerControls;
  brushRadius: number;
  zoomCommand: MangaCanvasCommand;
  onSelectBlock: (blockId: string) => void;
  onUpdateDraft: (blockId: string, patch: Partial<MangaBlockDraft>) => void;
  onCreateBlock: (bbox: number[]) => void;
  onDeleteBlock: (blockId: string) => void;
  onApplyBrushStroke: (stroke: MangaBrushStrokePayload) => void;
  onViewportChange: (zoomPercent: number) => void;
  onPointerChange: (pointer: MangaCanvasPointer | null) => void;
}

const buildOverlayLabel = (sourceText: string, translation: string, fallback: string) => {
  const translated = translation.trim();
  const source = sourceText.trim();
  const preview = translated || source || fallback;
  return preview.length > 24 ? `${preview.slice(0, 24)}...` : preview;
};

const buildOverlayBoxStyle = (bbox: number[]): React.CSSProperties => {
  const [x1, y1, x2, y2] = bbox;
  return {
    left: x1,
    top: y1,
    width: Math.max(1, x2 - x1),
    height: Math.max(1, y2 - y1),
  };
};

const areBboxesEqual = (left: number[] = [], right: number[] = []) => (
  left.length >= 4
  && right.length >= 4
  && left.slice(0, 4).every((value, index) => Math.round(Number(value) || 0) === Math.round(Number(right[index]) || 0))
);

const normalizePreviewText = (value: string) => value.replace(/\s+/g, '').trim();

const getRenderLayoutPlans = (page: MangaPageDetail | null) => {
  const plans = page?.quality_gate?.stage_modes?.render?.layout_plans;
  return Array.isArray(plans) ? plans as MangaRenderLayoutPlan[] : [];
};

const isDraftDirtyForPreview = (
  block: MangaPageDetail['blocks'][number],
  draft: MangaBlockDraft | undefined,
) => {
  if (!draft) return false;
  return (
    !areBboxesEqual(draft.bbox, block.bbox)
    || draft.source_text !== (block.source_text || '')
    || draft.translation !== (block.translation || '')
    || draft.font_family !== block.style.font_family
    || draft.font_size !== block.style.font_size
    || draft.line_spacing !== block.style.line_spacing
    || draft.fill !== block.style.fill
    || draft.stroke_color !== block.style.stroke_color
    || draft.stroke_width !== block.style.stroke_width
  );
};

const hasFiniteRunPosition = (run: MangaRenderLayoutRun) => Number.isFinite(Number(run.x)) && Number.isFinite(Number(run.y));

const clampScale = (scale: number, fitScale: number) => {
  const minScale = Math.max(0.05, fitScale * 0.5);
  return Math.max(minScale, Math.min(4, scale));
};

const clampValue = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const MIN_BLOCK_SIZE = 12;
const clampBrushRadius = (radius: number) => Math.max(1, Math.min(256, Math.round(Number(radius) || 24)));

const normalizeBlockBbox = (bbox: number[], pageWidth: number, pageHeight: number) => {
  const values = bbox.slice(0, 4).map((value) => Math.round(Number(value) || 0));
  let [x1, y1, x2, y2] = values.length >= 4 ? values : [0, 0, MIN_BLOCK_SIZE, MIN_BLOCK_SIZE];
  if (x2 < x1) [x1, x2] = [x2, x1];
  if (y2 < y1) [y1, y2] = [y2, y1];

  const minWidth = Math.min(MIN_BLOCK_SIZE, Math.max(1, pageWidth));
  const minHeight = Math.min(MIN_BLOCK_SIZE, Math.max(1, pageHeight));
  x1 = clampValue(x1, 0, Math.max(0, pageWidth - minWidth));
  y1 = clampValue(y1, 0, Math.max(0, pageHeight - minHeight));
  x2 = clampValue(Math.max(x2, x1 + minWidth), x1 + minWidth, pageWidth);
  y2 = clampValue(Math.max(y2, y1 + minHeight), y1 + minHeight, pageHeight);
  return [x1, y1, x2, y2];
};

const transformBlockBbox = (
  state: BlockTransformState,
  clientX: number,
  clientY: number,
  scale: number,
  pageWidth: number,
  pageHeight: number,
) => {
  const dx = Math.round((clientX - state.startX) / Math.max(scale, 0.001));
  const dy = Math.round((clientY - state.startY) / Math.max(scale, 0.001));
  const [startX1, startY1, startX2, startY2] = normalizeBlockBbox(state.startBbox, pageWidth, pageHeight);
  const width = startX2 - startX1;
  const height = startY2 - startY1;

  if (state.mode === 'move') {
    const x1 = clampValue(startX1 + dx, 0, Math.max(0, pageWidth - width));
    const y1 = clampValue(startY1 + dy, 0, Math.max(0, pageHeight - height));
    return [x1, y1, x1 + width, y1 + height].map(Math.round);
  }

  let x1 = startX1;
  let y1 = startY1;
  let x2 = startX2;
  let y2 = startY2;
  const minWidth = Math.min(MIN_BLOCK_SIZE, Math.max(1, pageWidth));
  const minHeight = Math.min(MIN_BLOCK_SIZE, Math.max(1, pageHeight));

  const resizeDirection = state.mode.replace('resize-', '') as BlockResizeDirection;

  if (resizeDirection.includes('w')) {
    x1 = clampValue(startX1 + dx, 0, startX2 - minWidth);
  }
  if (resizeDirection.includes('e')) {
    x2 = clampValue(startX2 + dx, startX1 + minWidth, pageWidth);
  }
  if (resizeDirection.includes('n')) {
    y1 = clampValue(startY1 + dy, 0, startY2 - minHeight);
  }
  if (resizeDirection.includes('s')) {
    y2 = clampValue(startY2 + dy, startY1 + minHeight, pageHeight);
  }

  return [x1, y1, x2, y2].map(Math.round);
};

const moveBlockBbox = (
  bbox: number[],
  dx: number,
  dy: number,
  pageWidth: number,
  pageHeight: number,
) => {
  const [x1, y1, x2, y2] = normalizeBlockBbox(bbox, pageWidth, pageHeight);
  const width = x2 - x1;
  const height = y2 - y1;
  const nextX1 = clampValue(x1 + dx, 0, Math.max(0, pageWidth - width));
  const nextY1 = clampValue(y1 + dy, 0, Math.max(0, pageHeight - height));
  return [nextX1, nextY1, nextX1 + width, nextY1 + height].map(Math.round);
};

const resizeBlockBbox = (
  bbox: number[],
  dx: number,
  dy: number,
  pageWidth: number,
  pageHeight: number,
) => {
  const [x1, y1, x2, y2] = normalizeBlockBbox(bbox, pageWidth, pageHeight);
  const minWidth = Math.min(MIN_BLOCK_SIZE, Math.max(1, pageWidth));
  const minHeight = Math.min(MIN_BLOCK_SIZE, Math.max(1, pageHeight));
  const nextX2 = clampValue(x2 + dx, x1 + minWidth, pageWidth);
  const nextY2 = clampValue(y2 + dy, y1 + minHeight, pageHeight);
  return [x1, y1, nextX2, nextY2].map(Math.round);
};

const fitScaleForBbox = (
  bbox: number[],
  viewport: DOMRect,
  fitScale: number,
) => {
  const [x1, y1, x2, y2] = bbox;
  const width = Math.max(1, x2 - x1);
  const height = Math.max(1, y2 - y1);
  const availableWidth = Math.max(120, viewport.width - 144);
  const availableHeight = Math.max(120, viewport.height - 144);
  const rawScale = Math.min(availableWidth / width, availableHeight / height) * 0.58;
  return clampScale(Math.max(fitScale, Math.min(3.2, rawScale)), fitScale);
};

const panForCenteredBbox = (
  bbox: number[],
  scale: number,
  pageWidth: number,
  pageHeight: number,
) => {
  const [x1, y1, x2, y2] = bbox;
  const centerX = (x1 + x2) / 2;
  const centerY = (y1 + y2) / 2;
  return {
    x: Math.round(-scale * (centerX - (pageWidth / 2))),
    y: Math.round(-scale * (centerY - (pageHeight / 2))),
  };
};

const buildStrokePolyline = (points: MangaBrushStrokePoint[]) => points.map((point) => `${point.x},${point.y}`).join(' ');

const appendBrushPoint = (
  stroke: BrushStrokeState,
  point: MangaBrushStrokePoint,
): BrushStrokeState => {
  const lastPoint = stroke.points[stroke.points.length - 1];
  if (lastPoint && Math.hypot(point.x - lastPoint.x, point.y - lastPoint.y) < 2) {
    return stroke;
  }
  return {
    ...stroke,
    points: [...stroke.points, point],
  };
};

const buildBlockTextStyle = (
  block: MangaPageDetail['blocks'][number],
  draft: MangaBlockDraft | undefined,
): React.CSSProperties => {
  const fontSize = Math.max(8, Number(draft?.font_size ?? block.style.font_size ?? 24));
  const lineSpacing = Math.max(0.8, Number(draft?.line_spacing ?? block.style.line_spacing ?? 1.2));
  const strokeWidth = Math.max(0, Number(draft?.stroke_width ?? block.style.stroke_width ?? 0));
  const strokeColor = String(draft?.stroke_color ?? block.style.stroke_color ?? '#ffffff');
  const fill = String(draft?.fill ?? block.style.fill ?? '#111111');
  const fontFamily = String(draft?.font_family ?? block.style.font_family ?? 'serif');
  const isVertical = block.rendered_direction === 'vertical';

  return {
    color: fill,
    fontFamily,
    fontSize,
    lineHeight: lineSpacing,
    padding: Math.max(4, Math.round(fontSize * 0.12)),
    textOrientation: isVertical ? 'mixed' : undefined,
    WebkitTextStroke: strokeWidth > 0 ? `${strokeWidth}px ${strokeColor}` : undefined,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    writingMode: isVertical ? 'vertical-rl' : 'horizontal-tb',
  };
};

const buildBlockPreviewTextStyle = (
  block: MangaPageDetail['blocks'][number],
  draft: MangaBlockDraft | undefined,
): React.CSSProperties => {
  const isVertical = block.rendered_direction === 'vertical';
  return {
    ...buildBlockTextStyle(block, draft),
    alignItems: isVertical ? 'center' : 'flex-start',
    display: 'flex',
    justifyContent: isVertical ? 'flex-start' : 'center',
    padding: Math.max(2, Math.round(Number(draft?.font_size ?? block.style.font_size ?? 24) * 0.08)),
    textAlign: 'start',
  };
};

const buildRenderPlanRunStyle = (
  block: MangaPageDetail['blocks'][number],
  draft: MangaBlockDraft | undefined,
  plan: MangaRenderLayoutPlan,
  run: MangaRenderLayoutRun,
  bbox: number[],
): React.CSSProperties => {
  const [x1, y1] = bbox;
  const baseStyle = buildBlockTextStyle(block, draft);
  const left = Math.round(Number(run.x) - x1);
  const top = Math.round(Number(run.y) - y1);
  return {
    ...baseStyle,
    fontFamily: String(plan.font_family || baseStyle.fontFamily || block.style.font_family || 'serif'),
    fontSize: Math.max(8, Number(plan.font_size || baseStyle.fontSize || block.style.font_size || 24)),
    left,
    lineHeight: Number(plan.line_spacing || baseStyle.lineHeight || block.style.line_spacing || 1.2),
    padding: 0,
    position: 'absolute',
    top,
    transform: run.rotate_clockwise ? 'rotate(90deg)' : undefined,
    transformOrigin: run.rotate_clockwise ? 'left top' : undefined,
    whiteSpace: 'pre',
    wordBreak: 'normal',
    writingMode: 'horizontal-tb',
  };
};

const isRenderPlanPreviewUsable = (
  plan: MangaRenderLayoutPlan | undefined,
  block: MangaPageDetail['blocks'][number],
  text: string,
) => {
  if (!plan || plan.block_id !== block.block_id || !Array.isArray(plan.runs) || plan.runs.length === 0) {
    return false;
  }
  if (plan.direction && plan.direction !== block.rendered_direction) {
    return false;
  }
  if (Array.isArray(plan.bbox) && !areBboxesEqual(plan.bbox, block.bbox)) {
    return false;
  }
  if (plan.font_family && plan.font_family !== block.style.font_family) {
    return false;
  }
  if (Number.isFinite(Number(plan.font_size)) && Math.round(Number(plan.font_size)) !== Math.round(Number(block.style.font_size))) {
    return false;
  }
  if (!plan.runs.every((run) => hasFiniteRunPosition(run) && String(run.text || ''))) {
    return false;
  }

  const runText = plan.runs.map((run) => String(run.text || '')).join('');
  return Boolean(normalizePreviewText(text) && normalizePreviewText(runText) === normalizePreviewText(text));
};

const CANVAS_TOOLS: Array<{ id: CanvasTool; labelKey: string; icon: typeof MousePointer2 }> = [
  { id: 'select', labelKey: 'manga_tool_select', icon: MousePointer2 },
  { id: 'region', labelKey: 'manga_tool_region', icon: SquareDashedMousePointer },
  { id: 'text', labelKey: 'manga_tool_text', icon: Type },
  { id: 'brush', labelKey: 'manga_tool_brush', icon: Paintbrush },
  { id: 'restore', labelKey: 'manga_tool_restore_brush', icon: RotateCcw },
];

const BLOCK_RESIZE_HANDLES: Array<{ mode: BlockTransformMode; className: string }> = [
  { mode: 'resize-nw', className: 'left-0 top-0 -translate-x-1/2 -translate-y-1/2 cursor-nwse-resize' },
  { mode: 'resize-n', className: 'left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 cursor-ns-resize' },
  { mode: 'resize-ne', className: 'right-0 top-0 translate-x-1/2 -translate-y-1/2 cursor-nesw-resize' },
  { mode: 'resize-e', className: 'right-0 top-1/2 translate-x-1/2 -translate-y-1/2 cursor-ew-resize' },
  { mode: 'resize-w', className: 'left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize' },
  { mode: 'resize-sw', className: 'bottom-0 left-0 -translate-x-1/2 translate-y-1/2 cursor-nesw-resize' },
  { mode: 'resize-s', className: 'bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 cursor-ns-resize' },
  { mode: 'resize-se', className: 'bottom-0 right-0 translate-x-1/2 translate-y-1/2 cursor-nwse-resize' },
];

export const MangaCanvas: React.FC<MangaCanvasProps> = ({
  page,
  currentImageUrl,
  viewMode,
  activeBlockId,
  blockDrafts,
  activeJob,
  runtimeOverlay,
  layerControls,
  brushRadius,
  zoomCommand,
  onSelectBlock,
  onUpdateDraft,
  onCreateBlock,
  onDeleteBlock,
  onApplyBrushStroke,
  onViewportChange,
  onPointerChange,
}) => {
  const { t } = useI18n();
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [fitScale, setFitScale] = useState(1);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [blockTransform, setBlockTransform] = useState<BlockTransformState | null>(null);
  const [createRegion, setCreateRegion] = useState<CreateRegionState | null>(null);
  const [brushStroke, setBrushStroke] = useState<BrushStrokeState | null>(null);
  const [focusHighlight, setFocusHighlight] = useState<FocusHighlightState | null>(null);
  const [activeTool, setActiveTool] = useState<CanvasTool>('select');
  const [inlineEdit, setInlineEdit] = useState<InlineEditState | null>(null);
  const [scaleMode, setScaleMode] = useState<'fit' | 'actual' | 'manual'>('fit');
  const pageRef = useRef<MangaPageDetail | null>(page);
  const scaleRef = useRef(scale);
  const onUpdateDraftRef = useRef(onUpdateDraft);

  const canvasFrameStyle = useMemo<React.CSSProperties | undefined>(() => (
    page
      ? {
          width: page.width,
          height: page.height,
        }
      : undefined
  ), [page]);
  const renderLayoutPlans = useMemo(() => getRenderLayoutPlans(page), [page]);
  const renderLayoutPlanByBlockId = useMemo(() => {
    const next = new Map<string, MangaRenderLayoutPlan>();
    for (const plan of renderLayoutPlans) {
      const blockId = String(plan.block_id || '');
      if (blockId) next.set(blockId, plan);
    }
    return next;
  }, [renderLayoutPlans]);

  useEffect(() => {
    if (!page || !viewportRef.current) {
      setFitScale(1);
      return;
    }

    const viewport = viewportRef.current;
    const updateFitScale = () => {
      const rect = viewport.getBoundingClientRect();
      const nextFitScale = Math.min(
        Math.max(rect.width - 48, 1) / Math.max(page.width, 1),
        Math.max(rect.height - 48, 1) / Math.max(page.height, 1),
      );
      setFitScale(Math.max(0.05, nextFitScale));
    };

    updateFitScale();
    const observer = new ResizeObserver(updateFitScale);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [page]);

  useEffect(() => {
    if (!page) {
      setScale(1);
      setPan({ x: 0, y: 0 });
      setScaleMode('fit');
      onPointerChange(null);
      return;
    }
    setPan({ x: 0, y: 0 });
    setScaleMode('fit');
    setInlineEdit(null);
    setBrushStroke(null);
    setFocusHighlight(null);
  }, [page, viewMode, onPointerChange]);

  useEffect(() => {
    if (page && scaleMode === 'fit') {
      setScale(fitScale);
    }
  }, [fitScale, page, scaleMode]);

  useEffect(() => {
    if (!page) return;
    if (zoomCommand.kind === 'fit') {
      setScaleMode('fit');
      setPan({ x: 0, y: 0 });
      setScale(fitScale);
      setFocusHighlight(null);
      return;
    }
    if (zoomCommand.kind === 'focusBox' && zoomCommand.bbox && viewportRef.current) {
      const bbox = normalizeBlockBbox(zoomCommand.bbox, page.width, page.height);
      const nextScale = fitScaleForBbox(bbox, viewportRef.current.getBoundingClientRect(), fitScale);
      setScaleMode('manual');
      setScale(nextScale);
      setPan(panForCenteredBbox(bbox, nextScale, page.width, page.height));
      setFocusHighlight({
        bbox,
        label: zoomCommand.label || '',
      });
      return;
    }
    setScaleMode('actual');
    setPan({ x: 0, y: 0 });
    setScale(1);
    setFocusHighlight(null);
  }, [fitScale, page, zoomCommand]);

  useEffect(() => {
    if (!focusHighlight) return undefined;
    const timeout = window.setTimeout(() => setFocusHighlight(null), 2200);
    return () => window.clearTimeout(timeout);
  }, [focusHighlight]);

  useEffect(() => {
    onViewportChange(Math.round(scale * 100));
  }, [onViewportChange, scale]);

  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

  useEffect(() => {
    onUpdateDraftRef.current = onUpdateDraft;
  }, [onUpdateDraft]);

  useEffect(() => {
    if (!blockTransform) return;

    const handleBlockPointerMove = (event: PointerEvent) => {
      if (event.pointerId !== blockTransform.pointerId) return;
      const currentPage = pageRef.current;
      if (!currentPage) return;
      event.preventDefault();
      const bbox = transformBlockBbox(
        blockTransform,
        event.clientX,
        event.clientY,
        scaleRef.current,
        currentPage.width,
        currentPage.height,
      );
      onUpdateDraftRef.current(blockTransform.blockId, { bbox });
    };

    const handleBlockPointerEnd = (event: PointerEvent) => {
      if (event.pointerId === blockTransform.pointerId) {
        setBlockTransform(null);
      }
    };

    window.addEventListener('pointermove', handleBlockPointerMove);
    window.addEventListener('pointerup', handleBlockPointerEnd);
    window.addEventListener('pointercancel', handleBlockPointerEnd);
    return () => {
      window.removeEventListener('pointermove', handleBlockPointerMove);
      window.removeEventListener('pointerup', handleBlockPointerEnd);
      window.removeEventListener('pointercancel', handleBlockPointerEnd);
    };
  }, [blockTransform]);

  const getPagePoint = (clientX: number, clientY: number) => {
    if (!page || !viewportRef.current) return null;
    const rect = viewportRef.current.getBoundingClientRect();
    const relativeX = clientX - rect.left - (rect.width / 2) - pan.x;
    const relativeY = clientY - rect.top - (rect.height / 2) - pan.y;
    const x = Math.round((relativeX / Math.max(scale, 0.001)) + (page.width / 2));
    const y = Math.round((relativeY / Math.max(scale, 0.001)) + (page.height / 2));
    return {
      x: clampValue(x, 0, page.width),
      y: clampValue(y, 0, page.height),
      inPage: x >= 0 && y >= 0 && x <= page.width && y <= page.height,
    };
  };

  const updatePointer = (clientX: number, clientY: number) => {
    if (!page) return;
    const point = getPagePoint(clientX, clientY);
    if (!point?.inPage) {
      onPointerChange(null);
      return;
    }
    onPointerChange({
      x: point.x,
      y: point.y,
      normalizedX: point.x / Math.max(page.width, 1),
      normalizedY: point.y / Math.max(page.height, 1),
    });
  };

  const beginBlockTransform = (
    event: React.PointerEvent<HTMLElement>,
    blockId: string,
    bbox: number[],
    mode: BlockTransformMode,
  ) => {
    if (!page || event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.focus();
    onSelectBlock(blockId);
    setBlockTransform({
      pointerId: event.pointerId,
      blockId,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      startBbox: normalizeBlockBbox(bbox, page.width, page.height),
    });
  };

  const startInlineEdit = (
    event: React.SyntheticEvent,
    blockId: string,
    field: InlineEditField,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    onSelectBlock(blockId);
    setInlineEdit({ blockId, field });
  };

  const handleBlockKeyDown = (
    event: React.KeyboardEvent<HTMLElement>,
    blockId: string,
    bbox: number[],
  ) => {
    if (!page) return;

    if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault();
      event.stopPropagation();
      onDeleteBlock(blockId);
      return;
    }

    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      event.stopPropagation();
      onSelectBlock(blockId);
      return;
    }

    if (!event.key.startsWith('Arrow')) return;
    event.preventDefault();
    event.stopPropagation();
    onSelectBlock(blockId);

    const step = event.shiftKey ? 10 : 1;
    if (event.altKey) {
      const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0;
      const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0;
      onUpdateDraft(blockId, { bbox: resizeBlockBbox(bbox, dx, dy, page.width, page.height) });
      return;
    }

    const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0;
    const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0;
    onUpdateDraft(blockId, { bbox: moveBlockBbox(bbox, dx, dy, page.width, page.height) });
  };

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (!page) return;
    event.preventDefault();
    const zoomFactor = event.deltaY < 0 ? 1.1 : 0.9;
    setScaleMode('manual');
    setScale((current) => clampScale(current * zoomFactor, fitScale));
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!page || event.button !== 0) return;
    if (activeTool === 'brush' || activeTool === 'restore') {
      const point = getPagePoint(event.clientX, event.clientY);
      if (!point?.inPage) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      setBrushStroke({
        pointerId: event.pointerId,
        mode: activeTool,
        radius: clampBrushRadius(brushRadius),
        points: [{ x: point.x, y: point.y }],
      });
      return;
    }

    if (activeTool === 'text') {
      const point = getPagePoint(event.clientX, event.clientY);
      if (!point?.inPage) return;
      event.currentTarget.setPointerCapture(event.pointerId);
      setCreateRegion({
        pointerId: event.pointerId,
        startX: point.x,
        startY: point.y,
        currentX: point.x,
        currentY: point.y,
      });
      return;
    }

    event.currentTarget.setPointerCapture(event.pointerId);
    setDragState({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    });
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!page) return;
    updatePointer(event.clientX, event.clientY);
    if (brushStroke?.pointerId === event.pointerId) {
      const point = getPagePoint(event.clientX, event.clientY);
      if (point) {
        setBrushStroke((current) => (
          current?.pointerId === event.pointerId
            ? appendBrushPoint(current, { x: point.x, y: point.y })
            : current
        ));
      }
      return;
    }

    if (createRegion?.pointerId === event.pointerId) {
      const point = getPagePoint(event.clientX, event.clientY);
      if (point) {
        setCreateRegion({
          ...createRegion,
          currentX: point.x,
          currentY: point.y,
        });
      }
      return;
    }
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    setScaleMode('manual');
    setPan({
      x: dragState.originX + (event.clientX - dragState.startX),
      y: dragState.originY + (event.clientY - dragState.startY),
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (brushStroke?.pointerId === event.pointerId) {
      const stroke = brushStroke;
      setBrushStroke(null);
      if (stroke.points.length > 0) {
        onApplyBrushStroke({
          mode: stroke.mode,
          radius: stroke.radius,
          points: stroke.points,
        });
      }
      return;
    }

    if (page && createRegion?.pointerId === event.pointerId) {
      const bbox = normalizeBlockBbox([
        createRegion.startX,
        createRegion.startY,
        createRegion.currentX,
        createRegion.currentY,
      ], page.width, page.height);
      setCreateRegion(null);
      setActiveTool('select');
      onCreateBlock(bbox);
      return;
    }

    if (dragState?.pointerId === event.pointerId) {
      setDragState(null);
    }
  };

  return (
    <main className="flex-1 min-w-0 bg-slate-900 flex flex-col">
      <div className="border-b border-slate-800/90 bg-slate-950/78 px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-xs uppercase tracking-[0.2em] text-slate-500">
        <div className="flex items-center gap-4">
          <span>{t('manga_canvas_title')}</span>
          {page && <span>{t('manga_canvas_page_status', page.index, translateMangaEnum('manga_state', page.status, t))}</span>}
          {page && <span>{t('manga_canvas_block_count', page.blocks.length)}</span>}
          {runtimeOverlay && <span className="text-cyan-300">{t('manga_canvas_runtime_overlay', runtimeOverlay.title)}</span>}
        </div>
        {activeJob && (
          <span className={`${activeJob.status === 'failed' ? 'text-rose-300' : 'text-cyan-300'}`}>
            {activeJob.stageLabel} · {activeJob.progress}%
          </span>
        )}
      </div>

      <div
        ref={viewportRef}
        className={`flex-1 min-h-0 relative overflow-hidden p-6 ${
          page ? (activeTool === 'brush' || activeTool === 'restore' || activeTool === 'text' ? 'cursor-crosshair' : blockTransform ? 'cursor-default' : dragState ? 'cursor-grabbing' : 'cursor-grab') : ''
        } bg-[linear-gradient(45deg,rgba(15,23,42,0.92)_25%,transparent_25%),linear-gradient(-45deg,rgba(15,23,42,0.92)_25%,transparent_25%),linear-gradient(45deg,transparent_75%,rgba(15,23,42,0.92)_75%),linear-gradient(-45deg,transparent_75%,rgba(15,23,42,0.92)_75%)] bg-[length:28px_28px] bg-[position:0_0,0_14px,14px_-14px,-14px_0px]`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={() => onPointerChange(null)}
      >
        <div className="absolute left-4 top-4 z-20 hidden w-12 flex-col items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/88 p-2 shadow-xl shadow-slate-950/40 md:flex">
          {CANVAS_TOOLS.map(({ id, labelKey, icon: ToolIcon }) => {
            const label = t(labelKey);
            return (
              <button
                key={id}
                type="button"
                title={label}
                onClick={() => setActiveTool(id)}
                onPointerDown={(event) => event.stopPropagation()}
                className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
                  activeTool === id ? 'bg-primary text-slate-950' : 'text-slate-400 hover:bg-slate-900 hover:text-slate-100'
                }`}
              >
                <ToolIcon size={16} />
              </button>
            );
          })}
        </div>

        {!page ? (
          <div className="absolute inset-0 flex items-center justify-center text-center text-slate-500">
            <div className="text-xs uppercase tracking-[0.28em] mb-3">{t('manga_canvas_title')}</div>
            <div className="text-lg font-semibold text-slate-300">{t('manga_canvas_empty')}</div>
          </div>
        ) : (
          <>
            <div
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 overflow-visible"
              style={canvasFrameStyle}
            >
              <div
                className="relative h-full w-full rounded-md border border-slate-700/70 bg-black/60 shadow-2xl shadow-slate-950/55 overflow-hidden"
                style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
                  transformOrigin: 'center center',
                }}
              >
                <img
                  src={currentImageUrl}
                  alt={t('manga_page_alt', page.index)}
                  draggable={false}
                  className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                />

                {viewMode === 'overlay' && layerControls.sourceReference.visible && page.layers.source_url && (
                  <img
                    src={page.layers.source_url}
                    alt={t('manga_layer_source_reference')}
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.sourceReference.opacity }}
                  />
                )}

                {layerControls.segment.visible && (
                  <img
                    src={page.masks.segment_url}
                    alt={t('manga_layer_segment_mask')}
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.segment.opacity }}
                  />
                )}

                {layerControls.bubble.visible && (
                  <img
                    src={page.masks.bubble_url}
                    alt={t('manga_layer_bubble_mask')}
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.bubble.opacity }}
                  />
                )}

                {layerControls.brush.visible && (
                  <img
                    src={page.masks.brush_url}
                    alt={t('manga_layer_brush_mask')}
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.brush.opacity }}
                  />
                )}

                {layerControls.restore.visible && (
                  <img
                    src={page.masks.restore_url}
                    alt={t('manga_layer_restore_mask')}
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.restore.opacity }}
                  />
                )}

                {runtimeOverlay?.imageUrl && (
                  <img
                    src={runtimeOverlay.imageUrl}
                    alt={runtimeOverlay.title}
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none mix-blend-screen"
                    style={{ opacity: 0.58 }}
                  />
                )}

                {runtimeOverlay?.boxes.map((box, index) => {
                  const toneClass = box.tone === 'emerald'
                    ? 'border-emerald-300 bg-emerald-400/10 text-emerald-100'
                    : box.tone === 'rose'
                      ? 'border-rose-300 bg-rose-400/10 text-rose-100'
                      : box.tone === 'amber'
                        ? 'border-amber-300 bg-amber-400/10 text-amber-100'
                        : 'border-cyan-300 bg-cyan-400/10 text-cyan-100';
                  return (
                    <div
                      key={`${runtimeOverlay.stage}-${index}`}
                      className={`absolute rounded-md border pointer-events-none ${toneClass}`}
                      style={buildOverlayBoxStyle(box.bbox)}
                    >
                      <span className="absolute -top-6 left-0 max-w-full truncate rounded bg-slate-950/88 px-1.5 py-0.5 text-[10px] font-semibold">
                        {box.label}
                      </span>
                    </div>
                  );
                })}

                {focusHighlight && (
                  <div
                    className="absolute rounded-md border-2 border-rose-300 bg-rose-400/12 pointer-events-none shadow-[0_0_0_2px_rgba(251,113,133,0.24),0_0_28px_rgba(251,113,133,0.38)]"
                    style={buildOverlayBoxStyle(focusHighlight.bbox)}
                  >
                    {focusHighlight.label && (
                      <span className="absolute -top-6 left-0 max-w-full truncate rounded bg-rose-950/90 px-1.5 py-0.5 text-[10px] font-semibold text-rose-50">
                        {focusHighlight.label}
                      </span>
                    )}
                  </div>
                )}

                {createRegion && (
                  <div
                    className="absolute rounded-md border border-dashed border-primary bg-primary/10 pointer-events-none"
                    style={buildOverlayBoxStyle(normalizeBlockBbox([
                      createRegion.startX,
                      createRegion.startY,
                      createRegion.currentX,
                      createRegion.currentY,
                    ], page.width, page.height))}
                  >
                    <span className="absolute -top-6 left-0 rounded bg-slate-950/88 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                      {t('manga_tool_text')}
                    </span>
                  </div>
                )}

                {brushStroke && (
                  <svg
                    className="absolute inset-0 pointer-events-none"
                    width={page.width}
                    height={page.height}
                    viewBox={`0 0 ${page.width} ${page.height}`}
                  >
                    {brushStroke.points.length === 1 ? (
                      <circle
                        cx={brushStroke.points[0].x}
                        cy={brushStroke.points[0].y}
                        r={brushStroke.radius}
                        fill={brushStroke.mode === 'brush' ? 'rgba(34,211,238,0.48)' : 'rgba(251,146,60,0.48)'}
                      />
                    ) : (
                      <polyline
                        points={buildStrokePolyline(brushStroke.points)}
                        fill="none"
                        stroke={brushStroke.mode === 'brush' ? 'rgba(34,211,238,0.62)' : 'rgba(251,146,60,0.62)'}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={brushStroke.radius * 2}
                      />
                    )}
                  </svg>
                )}

                {layerControls.overlay.visible && page.blocks.map((block) => {
                  const draft = blockDrafts[block.block_id];
                  const isActive = block.block_id === activeBlockId;
                  const isInlineEditing = inlineEdit?.blockId === block.block_id;
                  const inlineEditField = inlineEdit?.field || 'translation';
                  const sourceText = draft?.source_text ?? block.source_text ?? '';
                  const translation = draft?.translation ?? block.translation ?? '';
                  const inlineEditValue = inlineEditField === 'source_text' ? sourceText : translation;
                  const inlineEditPlaceholder = inlineEditField === 'source_text'
                    ? block.source_text || block.block_id
                    : sourceText || block.block_id;
                  const bbox = draft?.bbox || block.bbox;
                  const overlayLabel = buildOverlayLabel(sourceText, translation, block.block_id);
                  const previewTextStyle = buildBlockTextStyle(block, draft);
                  const centeredPreviewTextStyle = buildBlockPreviewTextStyle(block, draft);
                  const previewText = translation || sourceText || block.block_id;
                  const renderPlan = renderLayoutPlanByBlockId.get(block.block_id);
                  const canUseRenderPlanPreview = (
                    !isDraftDirtyForPreview(block, draft)
                    && isRenderPlanPreviewUsable(renderPlan, block, translation || sourceText)
                  );

                  return (
                    <div
                      key={block.block_id}
                      role="button"
                      tabIndex={0}
                      onPointerDown={(event) => beginBlockTransform(event, block.block_id, bbox, 'move')}
                      onKeyDown={(event) => handleBlockKeyDown(event, block.block_id, bbox)}
                      onDoubleClick={(event) => {
                        startInlineEdit(event, block.block_id, 'translation');
                      }}
                      className={`absolute rounded-lg border text-left transition-all ${
                        activeTool === 'brush' || activeTool === 'restore' ? 'pointer-events-none' : ''
                      } ${
                        isActive
                          ? 'cursor-move border-cyan-300 bg-transparent shadow-[0_0_0_1px_rgba(34,211,238,0.25)]'
                          : 'cursor-pointer border-amber-300/60 bg-transparent hover:border-cyan-300/80 hover:bg-cyan-400/5'
                      }`}
                      style={{
                        ...buildOverlayBoxStyle(bbox),
                        opacity: layerControls.overlay.opacity,
                      }}
                      title={`${block.block_id} | ${overlayLabel}`}
                    >
                      <span className="absolute -top-7 left-0 max-w-full truncate rounded-md bg-slate-950/85 px-2 py-1 text-[10px] font-semibold tracking-[0.12em] text-slate-100">
                        {overlayLabel}
                      </span>
                      {isActive && (
                        <span className="absolute -top-7 right-0 flex items-center overflow-hidden rounded-md border border-slate-700 bg-slate-950/90 text-[10px] font-bold text-slate-300 shadow-lg shadow-slate-950/35">
                          <button
                            type="button"
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={(event) => startInlineEdit(event, block.block_id, 'source_text')}
                            className={`px-1.5 py-1 transition-colors ${
                              isInlineEditing && inlineEditField === 'source_text'
                                ? 'bg-primary text-slate-950'
                                : 'hover:bg-slate-800 hover:text-slate-100'
                            }`}
                          >
                            {t('manga_ocr_label')}
                          </button>
                          <button
                            type="button"
                            onPointerDown={(event) => event.stopPropagation()}
                            onClick={(event) => startInlineEdit(event, block.block_id, 'translation')}
                            className={`border-l border-slate-700 px-1.5 py-1 transition-colors ${
                              isInlineEditing && inlineEditField === 'translation'
                                ? 'bg-primary text-slate-950'
                                : 'hover:bg-slate-800 hover:text-slate-100'
                            }`}
                          >
                            {t('manga_tl_label')}
                          </button>
                        </span>
                      )}
                      {!isInlineEditing && (
                        canUseRenderPlanPreview ? (
                          <span className="pointer-events-none absolute inset-0 block overflow-hidden rounded-md">
                            {renderPlan?.runs?.map((run, runIndex) => (
                              <span
                                key={`${block.block_id}-run-${runIndex}`}
                                style={buildRenderPlanRunStyle(block, draft, renderPlan, run, bbox)}
                              >
                                {String(run.text || '')}
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span
                            className="pointer-events-none absolute inset-0 block overflow-hidden rounded-md"
                            style={centeredPreviewTextStyle}
                          >
                            {previewText}
                          </span>
                        )
                      )}
                      {isInlineEditing && (
                        <textarea
                          autoFocus
                          value={inlineEditValue}
                          placeholder={inlineEditPlaceholder}
                          onChange={(event) => onUpdateDraft(block.block_id, { [inlineEditField]: event.target.value })}
                          onBlur={() => setInlineEdit(null)}
                          onPointerDown={(event) => event.stopPropagation()}
                          onDoubleClick={(event) => event.stopPropagation()}
                          onKeyDown={(event) => {
                            event.stopPropagation();
                            if (event.key === 'Escape' || ((event.ctrlKey || event.metaKey) && event.key === 'Enter')) {
                              event.preventDefault();
                              setInlineEdit(null);
                            }
                          }}
                          className="absolute inset-0 resize-none rounded-md border border-cyan-300/45 bg-slate-950/92 outline-none shadow-xl shadow-slate-950/50 placeholder:text-slate-600"
                          style={previewTextStyle}
                        />
                      )}
                      {isActive && BLOCK_RESIZE_HANDLES.map((handle) => (
                        <span
                          key={handle.mode}
                          aria-hidden="true"
                          onPointerDown={(event) => beginBlockTransform(event, block.block_id, bbox, handle.mode)}
                          className={`absolute h-3 w-3 rounded-sm border border-cyan-100 bg-slate-950 shadow-[0_0_0_1px_rgba(8,47,73,0.85)] ${handle.className}`}
                        />
                      ))}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="absolute bottom-4 right-4 rounded-lg border border-slate-800 bg-slate-950/85 px-3 py-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {t('manga_canvas_zoom_hint', Math.round(scale * 100))}
            </div>

            {runtimeOverlay && (
              <div className="absolute bottom-4 left-4 max-w-[360px] rounded-lg border border-cyan-300/20 bg-slate-950/88 px-3 py-2 text-xs text-slate-300 shadow-xl shadow-slate-950/40">
                <div className="font-semibold text-cyan-100">{runtimeOverlay.title}</div>
                <div className="mt-1 line-clamp-2 text-slate-500">{runtimeOverlay.message}</div>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
};
