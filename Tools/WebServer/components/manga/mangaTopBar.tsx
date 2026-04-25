import React from 'react';
import { ArrowLeft, BookOpen, Download, Loader2, Plus, Redo2, RefreshCw, Save, Sparkles, Undo2 } from 'lucide-react';

type ButtonTone = 'primary' | 'accent' | 'neutral';

import { MangaViewMode } from './shared';

interface ToolbarButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
  tone?: ButtonTone;
  icon?: React.ReactNode;
}

export interface MangaTopBarProps {
  projectName: string;
  viewMode: MangaViewMode;
  busyAction: string;
  hasProject: boolean;
  hasPage: boolean;
  hasSelectedPage: boolean;
  selectedCount: number;
  currentPageIndex: number;
  pageCount: number;
  zoomPercent: number;
  onBack: () => void;
  onSetViewMode: (mode: MangaViewMode) => void;
  onFitCanvas: () => void;
  onResetZoom: () => void;
  onDetect: () => void;
  onOcr: () => void;
  onTranslateCurrent: () => void;
  onTranslateSelected: () => void;
  onPlanSelected: () => void;
  onInpaint: () => void;
  onRender: () => void;
  onAddBlock: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onExportPdf: () => void;
  onExportCbz: () => void;
  onExportEpub: () => void;
  onExportZip: () => void;
  onExportRar: () => void;
}

const TOOLBAR_BUTTON_STYLES: Record<ButtonTone, string> = {
  primary: 'border-cyan-400/30 bg-cyan-500/10 text-cyan-100 hover:bg-cyan-500/15',
  accent: 'border-primary/30 bg-primary/10 text-primary hover:bg-primary/15',
  neutral: 'border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-500 hover:text-slate-100',
};

const ToolbarButton: React.FC<ToolbarButtonProps> = ({
  label,
  onClick,
  disabled = false,
  busy = false,
  tone = 'neutral',
  icon,
}) => (
  <button
    onClick={onClick}
    disabled={disabled}
    className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${TOOLBAR_BUTTON_STYLES[tone]}`}
  >
    {busy ? <Loader2 size={15} className="animate-spin" /> : icon}
    <span>{label}</span>
  </button>
);

export const MangaTopBar: React.FC<MangaTopBarProps> = ({
  projectName,
  viewMode,
  busyAction,
  hasProject,
  hasPage,
  hasSelectedPage,
  selectedCount,
  currentPageIndex,
  pageCount,
  zoomPercent,
  onBack,
  onSetViewMode,
  onFitCanvas,
  onResetZoom,
  onDetect,
  onOcr,
  onTranslateCurrent,
  onTranslateSelected,
  onPlanSelected,
  onInpaint,
  onRender,
  onAddBlock,
  onUndo,
  onRedo,
  onSave,
  onExportPdf,
  onExportCbz,
  onExportEpub,
  onExportZip,
  onExportRar,
}) => {
  return (
    <div className="min-h-16 border-b border-slate-800 bg-surface/80 backdrop-blur px-4 py-3 flex flex-wrap items-center gap-2">
      <button
        onClick={onBack}
        className="h-10 w-10 rounded-lg border border-slate-700 bg-slate-900/70 text-slate-300 hover:text-white hover:border-primary transition-colors flex items-center justify-center"
      >
        <ArrowLeft size={18} />
      </button>

      <div className="flex items-center gap-3 min-w-0 mr-auto">
        <div className="h-10 w-10 rounded-xl bg-cyan-500/10 border border-cyan-400/20 text-cyan-300 flex items-center justify-center">
          <BookOpen size={18} />
        </div>
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Manga Editor</div>
          <div className="font-semibold truncate">{projectName}</div>
          {pageCount > 0 && (
            <div className="mt-1 text-[11px] text-slate-500">
              Page {currentPageIndex || 0} / {pageCount} · Zoom {zoomPercent}%
            </div>
          )}
        </div>
      </div>

      <div className="hidden xl:flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-2 py-1">
        <button
          onClick={onFitCanvas}
          className="px-3 py-2 rounded-lg text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors"
        >
          Fit
        </button>
        <button
          onClick={onResetZoom}
          className="px-3 py-2 rounded-lg text-xs uppercase tracking-[0.2em] text-slate-400 hover:text-slate-100 transition-colors"
        >
          100%
        </button>
        <div className="h-6 w-px bg-slate-800" />
        {(['original', 'overlay', 'rendered', 'inpainted'] as MangaViewMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => onSetViewMode(mode)}
            className={`px-3 py-2 rounded-lg text-xs uppercase tracking-[0.2em] transition-colors ${
              viewMode === mode ? 'bg-primary text-slate-900 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {mode}
          </button>
        ))}
      </div>

      <ToolbarButton
        label="Detect"
        onClick={onDetect}
        disabled={!hasProject || !hasSelectedPage || !!busyAction}
        busy={busyAction === 'detect current page'}
        tone="neutral"
        icon={<RefreshCw size={15} />}
      />
      <ToolbarButton
        label="OCR"
        onClick={onOcr}
        disabled={!hasProject || !hasSelectedPage || !!busyAction}
        busy={busyAction === 'ocr current page'}
        tone="neutral"
        icon={<RefreshCw size={15} />}
      />
      <ToolbarButton
        label="Translate Current"
        onClick={onTranslateCurrent}
        disabled={!hasProject || !hasSelectedPage || !!busyAction}
        busy={busyAction === 'translate current page'}
        tone="primary"
        icon={<Sparkles size={15} />}
      />
      <ToolbarButton
        label={`Translate Selected ${selectedCount > 0 ? `(${selectedCount})` : ''}`}
        onClick={onTranslateSelected}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'translate selected pages'}
        tone="accent"
        icon={<Sparkles size={15} />}
      />
      <ToolbarButton
        label="Plan Selected"
        onClick={onPlanSelected}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'plan selected pages'}
        tone="neutral"
        icon={<RefreshCw size={15} />}
      />
      <ToolbarButton
        label="Inpaint"
        onClick={onInpaint}
        disabled={!hasProject || !hasSelectedPage || !!busyAction}
        busy={busyAction === 'inpaint current page'}
        tone="neutral"
        icon={<RefreshCw size={15} />}
      />
      <ToolbarButton
        label="Render"
        onClick={onRender}
        disabled={!hasProject || !hasSelectedPage || !!busyAction}
        busy={busyAction === 'render current page'}
        tone="neutral"
        icon={<RefreshCw size={15} />}
      />
      <ToolbarButton
        label="Add Block"
        onClick={onAddBlock}
        disabled={!hasProject || !hasPage || !!busyAction}
        busy={busyAction === 'add block'}
        tone="neutral"
        icon={<Plus size={15} />}
      />
      <ToolbarButton
        label="Undo"
        onClick={onUndo}
        disabled={!hasProject || !hasPage || !!busyAction}
        busy={busyAction === 'undo'}
        tone="neutral"
        icon={<Undo2 size={15} />}
      />
      <ToolbarButton
        label="Redo"
        onClick={onRedo}
        disabled={!hasProject || !hasPage || !!busyAction}
        busy={busyAction === 'redo'}
        tone="neutral"
        icon={<Redo2 size={15} />}
      />
      <ToolbarButton
        label="Save"
        onClick={onSave}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'save project'}
        tone="neutral"
        icon={<Save size={15} />}
      />
      <ToolbarButton
        label="PDF"
        onClick={onExportPdf}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'export pdf'}
        tone="neutral"
        icon={<Download size={15} />}
      />
      <ToolbarButton
        label="CBZ"
        onClick={onExportCbz}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'export cbz'}
        tone="neutral"
      />
      <ToolbarButton
        label="EPUB"
        onClick={onExportEpub}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'export epub'}
        tone="neutral"
      />
      <ToolbarButton
        label="ZIP"
        onClick={onExportZip}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'export zip'}
        tone="neutral"
      />
      <ToolbarButton
        label="RAR"
        onClick={onExportRar}
        disabled={!hasProject || !!busyAction}
        busy={busyAction === 'export rar'}
        tone="neutral"
      />
    </div>
  );
};
