import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Eraser, MousePointer2, Paintbrush, SquareDashedMousePointer, Type } from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaPageDetail } from '../../types/manga';
import { MangaActiveJobSummary, MangaBlockDraft, MangaCanvasCommand, MangaCanvasPointer, MangaCanvasRuntimeOverlay, MangaLayerControls, MangaViewMode, translateMangaEnum } from './shared';

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

type CanvasTool = 'select' | 'region' | 'text' | 'brush' | 'erase';

interface CreateRegionState {
  pointerId: number;
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
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
  zoomCommand: MangaCanvasCommand;
  onSelectBlock: (blockId: string) => void;
  onUpdateDraft: (blockId: string, patch: Partial<MangaBlockDraft>) => void;
  onCreateBlock: (bbox: number[]) => void;
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

const clampScale = (scale: number, fitScale: number) => {
  const minScale = Math.max(0.05, fitScale * 0.5);
  return Math.max(minScale, Math.min(4, scale));
};

const clampValue = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

const MIN_BLOCK_SIZE = 12;

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

const CANVAS_TOOLS: Array<{ id: CanvasTool; labelKey: string; icon: typeof MousePointer2 }> = [
  { id: 'select', labelKey: 'manga_tool_select', icon: MousePointer2 },
  { id: 'region', labelKey: 'manga_tool_region', icon: SquareDashedMousePointer },
  { id: 'text', labelKey: 'manga_tool_text', icon: Type },
  { id: 'brush', labelKey: 'manga_tool_brush', icon: Paintbrush },
  { id: 'erase', labelKey: 'manga_tool_erase', icon: Eraser },
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
  zoomCommand,
  onSelectBlock,
  onUpdateDraft,
  onCreateBlock,
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
  const [activeTool, setActiveTool] = useState<CanvasTool>('select');
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
      return;
    }
    setScaleMode('actual');
    setPan({ x: 0, y: 0 });
    setScale(1);
  }, [fitScale, page, zoomCommand]);

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

  const handleBlockKeyDown = (
    event: React.KeyboardEvent<HTMLElement>,
    blockId: string,
    bbox: number[],
  ) => {
    if (!page) return;

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
          page ? (activeTool === 'text' ? 'cursor-crosshair' : blockTransform ? 'cursor-default' : dragState ? 'cursor-grabbing' : 'cursor-grab') : ''
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

                {layerControls.overlay.visible && page.blocks.map((block) => {
                  const draft = blockDrafts[block.block_id];
                  const isActive = block.block_id === activeBlockId;
                  const sourceText = draft?.source_text ?? block.source_text ?? '';
                  const translation = draft?.translation ?? block.translation ?? '';
                  const bbox = draft?.bbox || block.bbox;

                  return (
                    <div
                      key={block.block_id}
                      role="button"
                      tabIndex={0}
                      onPointerDown={(event) => beginBlockTransform(event, block.block_id, bbox, 'move')}
                      onKeyDown={(event) => handleBlockKeyDown(event, block.block_id, bbox)}
                      className={`absolute rounded-lg border text-left transition-all ${
                        isActive
                          ? 'cursor-move border-cyan-300 bg-cyan-500/10 shadow-[0_0_0_1px_rgba(34,211,238,0.25)]'
                          : 'cursor-pointer border-amber-300/70 bg-slate-950/20 hover:border-cyan-300/80'
                      }`}
                      style={{
                        ...buildOverlayBoxStyle(bbox),
                        opacity: layerControls.overlay.opacity,
                      }}
                      title={`${block.block_id} | ${buildOverlayLabel(sourceText, translation, block.block_id)}`}
                    >
                      <span className="absolute -top-7 left-0 max-w-full truncate rounded-md bg-slate-950/85 px-2 py-1 text-[10px] font-semibold tracking-[0.12em] text-slate-100">
                        {buildOverlayLabel(sourceText, translation, block.block_id)}
                      </span>
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
