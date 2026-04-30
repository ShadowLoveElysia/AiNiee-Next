import React from 'react';
import {
  Activity,
  ArrowLeft,
  BookOpen,
  ChevronDown,
  Download,
  FileArchive,
  FileText,
  FolderOpen,
  Layers3,
  Loader2,
  Paintbrush,
  Plus,
  Redo2,
  RefreshCw,
  Save,
  ScanLine,
  Sparkles,
  Type,
  Undo2,
} from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaViewMode } from './shared';

type ButtonTone = 'primary' | 'accent' | 'neutral' | 'quiet';

interface ToolbarButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  busy?: boolean;
  tone?: ButtonTone;
  icon?: React.ReactNode;
  compact?: boolean;
}

interface ToolbarGroupProps {
  label: string;
  children: React.ReactNode;
  className?: string;
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
  onSwitchProject: () => void;
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
  onValidateRuntime: () => void;
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

const BUTTON_STYLES: Record<ButtonTone, string> = {
  primary: 'border-primary/35 bg-primary text-slate-950 shadow-[0_8px_28px_rgba(6,182,212,0.22)] hover:bg-cyan-300',
  accent: 'border-emerald-300/30 bg-emerald-400/12 text-emerald-100 hover:bg-emerald-400/18',
  neutral: 'border-slate-700/80 bg-slate-900/70 text-slate-200 hover:border-slate-500 hover:bg-slate-800/80',
  quiet: 'border-transparent bg-transparent text-slate-400 hover:bg-slate-900/70 hover:text-slate-100',
};

const ToolbarButton: React.FC<ToolbarButtonProps> = ({
  label,
  onClick,
  disabled = false,
  busy = false,
  tone = 'neutral',
  icon,
  compact = false,
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    title={label}
    className={`inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border px-3 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-45 ${
      compact ? 'w-10 px-0' : ''
    } ${BUTTON_STYLES[tone]}`}
  >
    {busy ? <Loader2 size={16} className="animate-spin" /> : icon}
    {!compact && <span>{label}</span>}
  </button>
);

const ToolbarGroup: React.FC<ToolbarGroupProps> = ({ label, children, className = '' }) => (
  <div className={`flex shrink-0 items-center gap-1.5 rounded-xl border border-slate-800/85 bg-slate-950/58 p-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] ${className}`}>
    <span className="hidden px-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 lg:inline">
      {label}
    </span>
    {children}
  </div>
);

const BUSY_LABEL_KEYS: Record<string, string> = {
  'detect current page': 'manga_busy_detect',
  'ocr current page': 'manga_busy_ocr',
  'translate current page': 'manga_busy_translate_current',
  'translate selected pages': 'manga_busy_translate_selected',
  'plan selected pages': 'manga_busy_plan_selected',
  'inpaint current page': 'manga_busy_inpaint',
  'render current page': 'manga_busy_render',
  'validate runtime': 'manga_busy_validate_runtime',
  'load runtime validation report': 'manga_busy_load_runtime_report',
  'add block': 'manga_busy_add_block',
  'delete block': 'manga_busy_delete_block',
  'brush mask': 'manga_busy_brush_mask',
  'restore mask': 'manga_busy_restore_mask',
  undo: 'manga_busy_undo',
  redo: 'manga_busy_redo',
  'save project': 'manga_busy_save',
  'export pdf': 'manga_busy_export_pdf',
  'export cbz': 'manga_busy_export_cbz',
  'export epub': 'manga_busy_export_epub',
  'export zip': 'manga_busy_export_zip',
  'export rar': 'manga_busy_export_rar',
};

const getBusyLabelKey = (busyAction: string) => (
  busyAction.startsWith('download model:')
    ? 'manga_busy_prepare_model'
    : BUSY_LABEL_KEYS[busyAction] || 'manga_busy_working'
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
  onSwitchProject,
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
  onValidateRuntime,
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
  const { t } = useI18n();
  const pageLabel = pageCount > 0 ? `${currentPageIndex || 0}/${pageCount}` : t('manga_no_project');
  const isBusy = Boolean(busyAction);
  const busyLabel = busyAction ? t(getBusyLabelKey(busyAction)) : t('manga_llm_ready');

  return (
    <header className="shrink-0 border-b border-slate-800/90 bg-[linear-gradient(180deg,rgba(15,23,42,0.98),rgba(2,6,23,0.96))] text-slate-100 shadow-[0_1px_0_rgba(255,255,255,0.03)]">
      <div className="flex h-12 items-center gap-3 px-3">
        <button
          type="button"
          onClick={onBack}
          title={t('manga_back')}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 bg-slate-900/75 text-slate-300 transition-colors hover:border-primary hover:text-white"
        >
          <ArrowLeft size={17} />
        </button>

        <div className="flex items-center gap-2 pr-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
            <BookOpen size={16} />
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{projectName}</div>
            <div className="text-[11px] text-slate-500">{t('manga_workbench')} · {t('manga_page_short')} {pageLabel} · {zoomPercent}%</div>
          </div>
          <button
            type="button"
            onClick={onSwitchProject}
            disabled={!hasProject || isBusy}
            className="hidden h-7 items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/55 px-2 text-[11px] font-semibold text-slate-400 transition-colors hover:border-primary hover:text-slate-100 disabled:opacity-45 lg:inline-flex"
          >
            <FolderOpen size={13} />
            {t('manga_switch_project')}
          </button>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden rounded-full border border-slate-700/80 bg-slate-900/70 px-3 py-1.5 text-xs text-slate-400 md:block">
            {t('manga_selected')} <span className="font-semibold text-slate-100">{selectedCount}</span>
          </div>
          <div className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${
            isBusy
              ? 'border-amber-300/30 bg-amber-300/10 text-amber-100'
              : 'border-primary/25 bg-primary/10 text-primary'
          }`}>
            {busyLabel}
          </div>
        </div>
      </div>

      <div className="flex min-h-14 items-center gap-2 overflow-x-auto border-t border-slate-900/80 px-3 py-2">
        <ToolbarGroup label={t('manga_toolbar_view')}>
          <div className="flex items-center gap-1 rounded-lg bg-slate-950/65 p-0.5">
            {(['rendered', 'overlay', 'original', 'inpainted'] as MangaViewMode[]).map((mode) => (
              <button
                type="button"
                key={mode}
                onClick={() => onSetViewMode(mode)}
                className={`h-8 rounded-md px-3 text-xs font-semibold capitalize transition-colors ${
                  viewMode === mode
                    ? 'bg-primary text-slate-950'
                    : 'text-slate-400 hover:bg-slate-900 hover:text-slate-100'
                }`}
              >
                {t(`manga_view_${mode}`)}
              </button>
            ))}
          </div>
          <ToolbarButton label={t('manga_fit')} onClick={onFitCanvas} disabled={!hasPage} tone="quiet" icon={<Layers3 size={16} />} compact />
          <ToolbarButton label={t('manga_actual_size')} onClick={onResetZoom} disabled={!hasPage} tone="quiet" icon={<RefreshCw size={16} />} compact />
        </ToolbarGroup>

        <ToolbarGroup label={t('manga_toolbar_pipeline')}>
          <ToolbarButton
            label={t('manga_action_detect')}
            onClick={onDetect}
            disabled={!hasProject || !hasSelectedPage || isBusy}
            busy={busyAction === 'detect current page'}
            icon={<ScanLine size={16} />}
          />
          <ToolbarButton
            label={t('manga_action_ocr')}
            onClick={onOcr}
            disabled={!hasProject || !hasSelectedPage || isBusy}
            busy={busyAction === 'ocr current page'}
            icon={<Type size={16} />}
          />
          <ToolbarButton
            label={t('manga_action_generate')}
            onClick={onTranslateCurrent}
            disabled={!hasProject || !hasSelectedPage || isBusy}
            busy={busyAction === 'translate current page'}
            tone="primary"
            icon={<Sparkles size={16} />}
          />
          <ToolbarButton
            label={t('manga_action_selected')}
            onClick={onTranslateSelected}
            disabled={!hasProject || isBusy}
            busy={busyAction === 'translate selected pages'}
            tone="accent"
            icon={<Sparkles size={16} />}
          />
          <ToolbarButton
            label={t('manga_action_plan')}
            onClick={onPlanSelected}
            disabled={!hasProject || isBusy}
            busy={busyAction === 'plan selected pages'}
            icon={<RefreshCw size={16} />}
          />
        </ToolbarGroup>

        <ToolbarGroup label={t('manga_toolbar_finish')}>
          <ToolbarButton
            label={t('manga_action_inpaint')}
            onClick={onInpaint}
            disabled={!hasProject || !hasSelectedPage || isBusy}
            busy={busyAction === 'inpaint current page'}
            icon={<Paintbrush size={16} />}
          />
          <ToolbarButton
            label={t('manga_action_render')}
            onClick={onRender}
            disabled={!hasProject || !hasSelectedPage || isBusy}
            busy={busyAction === 'render current page'}
            icon={<FileText size={16} />}
          />
          <ToolbarButton
            label={t('manga_action_validate_runtime')}
            onClick={onValidateRuntime}
            disabled={!hasProject || !hasSelectedPage || isBusy}
            busy={busyAction === 'validate runtime'}
            icon={<Activity size={16} />}
          />
        </ToolbarGroup>

        <ToolbarGroup label={t('manga_toolbar_edit')}>
          <ToolbarButton label={t('manga_action_add')} onClick={onAddBlock} disabled={!hasProject || !hasPage || isBusy} busy={busyAction === 'add block'} icon={<Plus size={16} />} compact />
          <ToolbarButton label={t('manga_action_undo')} onClick={onUndo} disabled={!hasProject || !hasPage || isBusy} busy={busyAction === 'undo'} icon={<Undo2 size={16} />} compact />
          <ToolbarButton label={t('manga_action_redo')} onClick={onRedo} disabled={!hasProject || !hasPage || isBusy} busy={busyAction === 'redo'} icon={<Redo2 size={16} />} compact />
          <ToolbarButton label={t('manga_action_save')} onClick={onSave} disabled={!hasProject || isBusy} busy={busyAction === 'save project'} icon={<Save size={16} />} compact />
        </ToolbarGroup>

        <ToolbarGroup label={t('manga_toolbar_export')} className="relative ml-auto">
          <ToolbarButton label={t('manga_format_pdf')} onClick={onExportPdf} disabled={!hasProject || isBusy} busy={busyAction === 'export pdf'} icon={<Download size={16} />} compact />
          <ToolbarButton label={t('manga_format_cbz')} onClick={onExportCbz} disabled={!hasProject || isBusy} busy={busyAction === 'export cbz'} icon={<FileArchive size={16} />} compact />
          <details className="group relative">
            <summary className="flex h-10 cursor-pointer list-none items-center gap-1 rounded-lg border border-transparent bg-transparent px-2 text-xs font-semibold text-slate-400 transition-colors hover:bg-slate-900/70 hover:text-slate-100">
              {t('manga_more_formats')}
              <ChevronDown size={13} className="transition-transform group-open:rotate-180" />
            </summary>
            <div className="absolute right-0 top-12 z-40 grid min-w-32 gap-1 rounded-xl border border-slate-800 bg-slate-950/96 p-1.5 shadow-2xl shadow-slate-950/50">
              <button type="button" onClick={onExportEpub} disabled={!hasProject || isBusy} className="rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-300 hover:bg-slate-900 disabled:opacity-45">{t('manga_format_epub')}</button>
              <button type="button" onClick={onExportZip} disabled={!hasProject || isBusy} className="rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-300 hover:bg-slate-900 disabled:opacity-45">{t('manga_format_zip')}</button>
              <button type="button" onClick={onExportRar} disabled={!hasProject || isBusy} className="rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-300 hover:bg-slate-900 disabled:opacity-45">{t('manga_format_rar')}</button>
            </div>
          </details>
        </ToolbarGroup>
      </div>
    </header>
  );
};
