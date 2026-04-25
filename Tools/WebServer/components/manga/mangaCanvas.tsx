import React, { useEffect, useMemo, useRef, useState } from 'react';

import { MangaPageDetail } from '../../types/manga';
import { MangaActiveJobSummary, MangaBlockDraft, MangaCanvasCommand, MangaCanvasPointer, MangaLayerControls, MangaViewMode } from './shared';

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
}

export interface MangaCanvasProps {
  page: MangaPageDetail | null;
  currentImageUrl: string;
  viewMode: MangaViewMode;
  activeBlockId: string;
  blockDrafts: Record<string, MangaBlockDraft>;
  activeJob: MangaActiveJobSummary | null;
  layerControls: MangaLayerControls;
  zoomCommand: MangaCanvasCommand;
  onSelectBlock: (blockId: string) => void;
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

export const MangaCanvas: React.FC<MangaCanvasProps> = ({
  page,
  currentImageUrl,
  viewMode,
  activeBlockId,
  blockDrafts,
  activeJob,
  layerControls,
  zoomCommand,
  onSelectBlock,
  onViewportChange,
  onPointerChange,
}) => {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [fitScale, setFitScale] = useState(1);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [scaleMode, setScaleMode] = useState<'fit' | 'actual' | 'manual'>('fit');

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

  const updatePointer = (clientX: number, clientY: number) => {
    if (!page || !viewportRef.current) return;
    const rect = viewportRef.current.getBoundingClientRect();
    const relativeX = clientX - rect.left - (rect.width / 2) - pan.x;
    const relativeY = clientY - rect.top - (rect.height / 2) - pan.y;
    const x = Math.round((relativeX / Math.max(scale, 0.001)) + (page.width / 2));
    const y = Math.round((relativeY / Math.max(scale, 0.001)) + (page.height / 2));
    if (x < 0 || y < 0 || x > page.width || y > page.height) {
      onPointerChange(null);
      return;
    }
    onPointerChange({
      x,
      y,
      normalizedX: x / Math.max(page.width, 1),
      normalizedY: y / Math.max(page.height, 1),
    });
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
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    setScaleMode('manual');
    setPan({
      x: dragState.originX + (event.clientX - dragState.startX),
      y: dragState.originY + (event.clientY - dragState.startY),
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragState?.pointerId === event.pointerId) {
      setDragState(null);
    }
  };

  return (
    <main className="flex-1 min-w-0 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.08),_transparent_40%),linear-gradient(180deg,_rgba(15,23,42,0.95),_rgba(2,6,23,1))] flex flex-col">
      <div className="border-b border-slate-900 px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-xs uppercase tracking-[0.2em] text-slate-500">
        <div className="flex items-center gap-4">
          <span>Canvas</span>
          {page && <span>Page {page.index} · {page.status}</span>}
          {page && <span>{page.blocks.length} block(s)</span>}
        </div>
        {activeJob && (
          <span className={`${activeJob.status === 'failed' ? 'text-rose-300' : 'text-cyan-300'}`}>
            {activeJob.stageLabel} · {activeJob.progress}%
          </span>
        )}
      </div>

      <div
        ref={viewportRef}
        className={`flex-1 min-h-0 relative overflow-hidden p-6 ${page ? (dragState ? 'cursor-grabbing' : 'cursor-grab') : ''}`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={() => onPointerChange(null)}
      >
        {!page ? (
          <div className="absolute inset-0 flex items-center justify-center text-center text-slate-500">
            <div className="text-xs uppercase tracking-[0.28em] mb-3">Canvas</div>
            <div className="text-lg font-semibold text-slate-300">Open a MangaProject to inspect pages.</div>
          </div>
        ) : (
          <>
            <div
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 overflow-visible"
              style={canvasFrameStyle}
            >
              <div
                className="relative h-full w-full rounded-[28px] border border-slate-700/70 bg-black/60 shadow-2xl overflow-hidden"
                style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
                  transformOrigin: 'center center',
                }}
              >
                <img
                  src={currentImageUrl}
                  alt={`Page ${page.index}`}
                  draggable={false}
                  className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                />

                {layerControls.segment.visible && (
                  <img
                    src={page.masks.segment_url}
                    alt="Segment mask"
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.segment.opacity }}
                  />
                )}

                {layerControls.bubble.visible && (
                  <img
                    src={page.masks.bubble_url}
                    alt="Bubble mask"
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.bubble.opacity }}
                  />
                )}

                {layerControls.brush.visible && (
                  <img
                    src={page.masks.brush_url}
                    alt="Brush mask"
                    draggable={false}
                    className="absolute inset-0 h-full w-full object-cover pointer-events-none select-none"
                    style={{ opacity: layerControls.brush.opacity }}
                  />
                )}

                {layerControls.overlay.visible && page.blocks.map((block) => {
                  const draft = blockDrafts[block.block_id];
                  const isActive = block.block_id === activeBlockId;
                  const sourceText = draft?.source_text ?? block.source_text ?? '';
                  const translation = draft?.translation ?? block.translation ?? '';

                  return (
                    <button
                      key={block.block_id}
                      onClick={() => onSelectBlock(block.block_id)}
                      onPointerDown={(event) => event.stopPropagation()}
                      className={`absolute rounded-lg border text-left transition-all ${
                        isActive
                          ? 'border-cyan-300 bg-cyan-500/10 shadow-[0_0_0_1px_rgba(34,211,238,0.25)]'
                          : 'border-amber-300/70 bg-slate-950/20 hover:border-cyan-300/80'
                      }`}
                      style={{
                        ...buildOverlayBoxStyle(block.bbox),
                        opacity: layerControls.overlay.opacity,
                      }}
                      title={`${block.block_id} | ${buildOverlayLabel(sourceText, translation, block.block_id)}`}
                    >
                      <span className="absolute -top-7 left-0 max-w-full truncate rounded-md bg-slate-950/85 px-2 py-1 text-[10px] font-semibold tracking-[0.12em] text-slate-100">
                        {buildOverlayLabel(sourceText, translation, block.block_id)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="absolute bottom-4 right-4 rounded-lg border border-slate-800 bg-slate-950/85 px-3 py-2 text-[11px] uppercase tracking-[0.18em] text-slate-400">
              {Math.round(scale * 100)}% · Wheel to zoom · Drag to pan
            </div>
          </>
        )}
      </div>
    </main>
  );
};
