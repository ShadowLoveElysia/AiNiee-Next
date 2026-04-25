import React, { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, BookOpen, Download, Loader2, Plus, Redo2, RefreshCw, Save, Sparkles, Undo2 } from 'lucide-react';
import { DataService } from '../services/DataService';
import { MangaJob, MangaPageDetail, MangaProjectSummary, MangaSceneSummary } from '../types/manga';

type ViewMode = 'rendered' | 'original' | 'overlay' | 'inpainted';
type NoticeTone = 'info' | 'success' | 'warning' | 'error';

interface BlockDraft {
  source_text: string;
  translation: string;
  font_size: number;
  fill: string;
  stroke_width: number;
}

const getInitialProjectPath = () => {
  const hash = window.location.hash || '';
  const query = hash.includes('?') ? hash.split('?')[1] : '';
  return new URLSearchParams(query).get('project_path') || '';
};

const delay = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export const MangaEditor: React.FC = () => {
  const [projectPath, setProjectPath] = useState(getInitialProjectPath());
  const [project, setProject] = useState<MangaProjectSummary | null>(null);
  const [scene, setScene] = useState<MangaSceneSummary | null>(null);
  const [page, setPage] = useState<MangaPageDetail | null>(null);
  const [selectedPageId, setSelectedPageId] = useState('');
  const [selectedPageIds, setSelectedPageIds] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>('rendered');
  const [isLoading, setIsLoading] = useState(false);
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<{ tone: NoticeTone; message: string } | null>(null);
  const [activeJob, setActiveJob] = useState<MangaJob | null>(null);
  const [blockDrafts, setBlockDrafts] = useState<Record<string, BlockDraft>>({});

  const currentImageUrl = useMemo(() => {
    if (!page) return '';
    if (viewMode === 'original') return page.layers.source_url;
    if (viewMode === 'inpainted') return page.layers.inpainted_url;
    return page.layers.rendered_url;
  }, [page, viewMode]);

  const showNotice = (tone: NoticeTone, message: string) => {
    setNotice({ tone, message });
    if (tone !== 'error') {
      window.setTimeout(() => {
        setNotice((current) => (current?.message === message ? null : current));
      }, 4000);
    }
  };

  const setDraftsFromPage = (detail: MangaPageDetail) => {
    const nextDrafts: Record<string, BlockDraft> = {};
    for (const block of detail.blocks) {
      nextDrafts[block.block_id] = {
        source_text: block.source_text || '',
        translation: block.translation || '',
        font_size: block.style.font_size,
        fill: block.style.fill,
        stroke_width: block.style.stroke_width,
      };
    }
    setBlockDrafts(nextDrafts);
  };

  const updateDraft = (blockId: string, patch: Partial<BlockDraft>) => {
    setBlockDrafts((current) => ({
      ...current,
      [blockId]: {
        ...(current[blockId] || {
          source_text: '',
          translation: '',
          font_size: 42,
          fill: '#111111',
          stroke_width: 2,
        }),
        ...patch,
      },
    }));
  };

  const loadPage = async (projectId: string, pageId: string) => {
    const detail = await DataService.getMangaPage(projectId, pageId);
    setPage(detail);
    setSelectedPageId(pageId);
    setDraftsFromPage(detail);
    setScene((current) => (current ? { ...current, current_page_id: pageId } : current));
  };

  const refreshScene = async (projectId: string) => {
    const sceneSummary = await DataService.getMangaScene(projectId);
    setScene(sceneSummary);
    return sceneSummary;
  };

  const refreshCurrentPage = async (projectId: string, pageId?: string) => {
    const targetPageId = pageId || selectedPageId || scene?.current_page_id || '';
    if (!targetPageId) return;
    await loadPage(projectId, targetPageId);
  };

  const waitForJob = async (projectId: string, initialJob: MangaJob) => {
    setActiveJob(initialJob);
    if (!initialJob.job_id || initialJob.status === 'completed' || initialJob.status === 'failed') {
      return initialJob;
    }

    let latest = initialJob;
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await delay(350);
      latest = await DataService.getMangaJob(projectId, initialJob.job_id);
      setActiveJob(latest);
      if (latest.status === 'completed' || latest.status === 'failed') {
        break;
      }
    }
    return latest;
  };

  const withBusyAction = async (action: string, callback: () => Promise<void>) => {
    setBusyAction(action);
    setError('');
    try {
      await callback();
    } catch (err: any) {
      setError(err.message || `Failed to ${action}`);
    } finally {
      setBusyAction('');
    }
  };

  const buildChangedOps = () => {
    if (!page) return [];
    const ops: any[] = [];
    for (const block of page.blocks) {
      const draft = blockDrafts[block.block_id];
      if (!draft) continue;
      const patch: Record<string, string | number> = {};
      if (draft.source_text !== (block.source_text || '')) patch.source_text = draft.source_text;
      if (draft.translation !== (block.translation || '')) patch.translation = draft.translation;
      if (draft.font_size !== block.style.font_size) patch['style.font_size'] = draft.font_size;
      if (draft.fill !== block.style.fill) patch['style.fill'] = draft.fill;
      if (draft.stroke_width !== block.style.stroke_width) patch['style.stroke_width'] = draft.stroke_width;
      if (Object.keys(patch).length > 0) {
        ops.push({
          type: 'UpdateTextBlock',
          page_id: page.page_id,
          block_id: block.block_id,
          patch,
        });
      }
    }
    return ops;
  };

  const applyDraftChanges = async (quiet = false) => {
    if (!project || !page) return 0;
    const ops = buildChangedOps();
    if (ops.length === 0) {
      if (!quiet) showNotice('info', 'No block changes to save.');
      return 0;
    }
    await DataService.applyMangaOps(project.project_id, ops);
    await refreshScene(project.project_id);
    await refreshCurrentPage(project.project_id, page.page_id);
    if (!quiet) showNotice('success', `Saved ${ops.length} block change(s).`);
    return ops.length;
  };

  const openProject = async (pathOverride?: string) => {
    const nextPath = (pathOverride ?? projectPath).trim();
    if (!nextPath) {
      setError('Project path is required.');
      return;
    }

    setError('');
    setIsLoading(true);
    try {
      const opened = await DataService.openMangaProject(nextPath);
      const sceneSummary = await DataService.getMangaScene(opened.project_id);
      setProject(opened);
      setScene(sceneSummary);
      setSelectedPageIds([]);
      setActiveJob(null);

      const firstPageId = sceneSummary.current_page_id || sceneSummary.pages[0]?.page_id || '';
      if (firstPageId) {
        await loadPage(opened.project_id, firstPageId);
      } else {
        setPage(null);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to open manga project.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleTranslateCurrentPage = async () => {
    if (!project || !selectedPageId) return;
    await withBusyAction('translate current page', async () => {
      const job = await DataService.translateMangaPage(project.project_id, selectedPageId);
      const settled = await waitForJob(project.project_id, job);
      await refreshScene(project.project_id);
      await refreshCurrentPage(project.project_id, selectedPageId);
      showNotice(settled.status === 'completed' ? 'success' : 'warning', settled.message);
    });
  };

  const handleTranslateSelectedPages = async () => {
    if (!project) return;
    const pageIds = selectedPageIds.length > 0 ? selectedPageIds : (selectedPageId ? [selectedPageId] : []);
    if (pageIds.length === 0) {
      showNotice('warning', 'Select at least one page for batch processing.');
      return;
    }
    await withBusyAction('translate selected pages', async () => {
      const job = await DataService.translateSelectedMangaPages(project.project_id, pageIds);
      const settled = await waitForJob(project.project_id, job);
      const nextScene = await refreshScene(project.project_id);
      await refreshCurrentPage(project.project_id, nextScene.current_page_id || pageIds[0]);
      showNotice(settled.status === 'completed' ? 'success' : 'warning', settled.message);
    });
  };

  const handleSaveProject = async () => {
    if (!project) return;
    await withBusyAction('save project', async () => {
      await applyDraftChanges(true);
      const result = await DataService.saveMangaProject(project.project_id);
      showNotice(result.ok ? 'success' : 'warning', result.ok ? 'Project saved.' : result.message || 'Project save returned a warning.');
    });
  };

  const handleAddBlock = async () => {
    if (!project || !page) return;
    const blockId = `blk_${page.page_id}_manual_${Date.now()}`;
    const width = Math.max(120, Math.round(page.width * 0.24));
    const height = Math.max(90, Math.round(page.height * 0.16));
    const x1 = Math.round((page.width - width) / 2);
    const y1 = Math.round((page.height - height) / 2);
    await withBusyAction('add block', async () => {
      await DataService.applyMangaOps(project.project_id, [
        {
          type: 'AddTextBlock',
          page_id: page.page_id,
          payload: {
            block: {
              block_id: blockId,
              bbox: [x1, y1, x1 + width, y1 + height],
              source_text: '',
              translation: '',
              origin: 'manual',
              placement_mode: 'free_manual',
              editable: true,
            },
          },
        },
      ]);
      await refreshScene(project.project_id);
      await refreshCurrentPage(project.project_id, page.page_id);
      showNotice('success', 'Added a manual text block to the current page.');
    });
  };

  const handleUndo = async () => {
    if (!project || !page) return;
    await withBusyAction('undo', async () => {
      const result = await DataService.undoMangaOps(project.project_id);
      await refreshScene(project.project_id);
      await refreshCurrentPage(project.project_id, page.page_id);
      showNotice(result.ok ? 'success' : 'warning', result.message || (result.ok ? 'Undo applied.' : 'Nothing to undo.'));
    });
  };

  const handleRedo = async () => {
    if (!project || !page) return;
    await withBusyAction('redo', async () => {
      const result = await DataService.redoMangaOps(project.project_id);
      await refreshScene(project.project_id);
      await refreshCurrentPage(project.project_id, page.page_id);
      showNotice(result.ok ? 'success' : 'warning', result.message || (result.ok ? 'Redo applied.' : 'Nothing to redo.'));
    });
  };

  const handleExport = async (format: 'pdf' | 'epub' | 'cbz' | 'zip' | 'rar') => {
    if (!project) return;
    await withBusyAction(`export ${format}`, async () => {
      await applyDraftChanges(true);
      const result = await DataService.exportMangaProject(project.project_id, format);
      showNotice(result.ok ? 'success' : 'warning', result.ok ? `Exported ${format.toUpperCase()} to ${result.path}` : `Export ${format.toUpperCase()} returned no file.`);
    });
  };

  const togglePageSelection = (pageId: string) => {
    setSelectedPageIds((current) => (
      current.includes(pageId)
        ? current.filter((item) => item !== pageId)
        : [...current, pageId]
    ));
  };

  useEffect(() => {
    if (projectPath) {
      void openProject(projectPath);
    }
  }, []);

  return (
    <div className="h-screen bg-background text-slate-100 flex flex-col overflow-hidden">
      <div className="h-16 border-b border-slate-800 bg-surface/80 backdrop-blur px-4 flex items-center gap-3">
        <button
          onClick={() => { window.location.hash = '/task'; }}
          className="h-10 w-10 rounded-lg border border-slate-700 bg-slate-900/70 text-slate-300 hover:text-white hover:border-primary transition-colors flex items-center justify-center"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="h-10 w-10 rounded-xl bg-cyan-500/10 border border-cyan-400/20 text-cyan-300 flex items-center justify-center">
            <BookOpen size={18} />
          </div>
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Manga Editor</div>
            <div className="font-semibold truncate">{project?.name || 'Open MangaProject'}</div>
          </div>
        </div>
        <div className="hidden lg:flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-2 py-1">
          {(['original', 'overlay', 'rendered', 'inpainted'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`px-3 py-2 rounded-lg text-xs uppercase tracking-[0.2em] transition-colors ${
                viewMode === mode ? 'bg-primary text-slate-900 font-bold' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
        <button
          onClick={() => void handleTranslateCurrentPage()}
          disabled={!project || !selectedPageId || !!busyAction}
          className="hidden md:flex items-center gap-2 px-4 py-2 rounded-lg border border-cyan-400/30 bg-cyan-500/10 text-cyan-200 disabled:opacity-50"
        >
          {busyAction === 'translate current page' ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
          Translate Current Page
        </button>
        <button
          onClick={() => void handleTranslateSelectedPages()}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          <Sparkles size={16} /> Translate Selected ({selectedPageIds.length || (selectedPageId ? 1 : 0)})
        </button>
        <button
          onClick={() => void handleAddBlock()}
          disabled={!project || !page || !!busyAction}
          className="hidden md:flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          <Plus size={16} /> Add Block
        </button>
        <button
          onClick={() => void handleUndo()}
          disabled={!project || !page || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          <Undo2 size={16} />
        </button>
        <button
          onClick={() => void handleRedo()}
          disabled={!project || !page || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          <Redo2 size={16} />
        </button>
        <button
          onClick={() => void handleSaveProject()}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          {busyAction === 'save project' ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} Save
        </button>
        <button
          onClick={() => void handleExport('pdf')}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          <Download size={16} /> PDF
        </button>
        <button
          onClick={() => void handleExport('cbz')}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          CBZ
        </button>
        <button
          onClick={() => void handleExport('epub')}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          EPUB
        </button>
        <button
          onClick={() => void handleExport('zip')}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          ZIP
        </button>
        <button
          onClick={() => void handleExport('rar')}
          disabled={!project || !!busyAction}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-slate-300 disabled:opacity-50"
        >
          RAR
        </button>
      </div>

      <div className="px-4 py-3 border-b border-slate-900 bg-slate-950/70 flex flex-col lg:flex-row gap-3 lg:items-center">
        <input
          type="text"
          value={projectPath}
          onChange={(event) => setProjectPath(event.target.value)}
          placeholder="H:/path/to/output/mangaProject"
          className="flex-1 min-w-0 rounded-xl border border-slate-800 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 outline-none focus:border-primary"
        />
        <div className="flex gap-2">
          <button
            onClick={() => void openProject()}
            disabled={isLoading}
            className="px-4 py-3 rounded-xl bg-primary text-slate-900 font-bold disabled:opacity-60 flex items-center gap-2"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Open Project
          </button>
        </div>
        {project && (
          <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
            {scene?.pages.length || 0} pages · current {page?.index || 0}
          </div>
        )}
      </div>

      {notice && (
        <div className={`mx-4 mt-3 rounded-xl border px-4 py-3 text-sm ${
          notice.tone === 'success' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-200' :
          notice.tone === 'warning' ? 'border-amber-500/20 bg-amber-500/10 text-amber-200' :
          notice.tone === 'error' ? 'border-rose-500/20 bg-rose-500/10 text-rose-200' :
          'border-cyan-500/20 bg-cyan-500/10 text-cyan-200'
        }`}>
          {notice.message}
        </div>
      )}

      {error && (
        <div className="mx-4 mt-3 rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0 flex">
        <aside className="w-[290px] border-r border-slate-900 bg-slate-950/80 overflow-y-auto">
          <div className="px-4 py-3 text-xs uppercase tracking-[0.24em] text-slate-500 border-b border-slate-900">Pages</div>
          <div className="p-3 space-y-3">
            {(scene?.pages || []).map((scenePage) => (
              <button
                key={scenePage.page_id}
                onClick={() => { if (project) void loadPage(project.project_id, scenePage.page_id); }}
                className={`w-full text-left rounded-2xl border overflow-hidden transition-colors ${
                  selectedPageId === scenePage.page_id
                    ? 'border-primary bg-primary/10 shadow-[0_0_0_1px_rgba(34,211,238,0.18)]'
                    : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                }`}
              >
                <div className="px-3 py-2 border-b border-slate-800/80 flex items-center justify-between">
                  <label
                    className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      checked={selectedPageIds.includes(scenePage.page_id)}
                      onChange={() => togglePageSelection(scenePage.page_id)}
                      className="w-4 h-4 rounded border-slate-700 text-primary bg-slate-950"
                    />
                    Select
                  </label>
                  <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{scenePage.status}</span>
                </div>
                <div className="aspect-[2/3] bg-slate-950 flex items-center justify-center overflow-hidden">
                  <img src={scenePage.thumbnail_url} alt={scenePage.page_id} className="w-full h-full object-cover" />
                </div>
                <div className="px-3 py-2 flex items-center justify-between">
                  <span className="text-sm font-semibold">Page {scenePage.index}</span>
                  {scene?.current_page_id === scenePage.page_id && (
                    <span className="text-[10px] uppercase tracking-[0.18em] text-primary">Current</span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </aside>

        <main className="flex-1 min-w-0 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.08),_transparent_40%),linear-gradient(180deg,_rgba(15,23,42,0.95),_rgba(2,6,23,1))] flex items-center justify-center p-6">
          {!page ? (
            <div className="text-center text-slate-500">
              <div className="text-xs uppercase tracking-[0.28em] mb-3">Canvas</div>
              <div className="text-lg font-semibold text-slate-300">Open a MangaProject to inspect pages.</div>
            </div>
          ) : (
            <div className="relative max-h-full max-w-full rounded-[28px] border border-slate-700/70 bg-black/60 shadow-2xl overflow-hidden">
              <img
                src={currentImageUrl}
                alt={`Page ${page.index}`}
                className="max-h-[calc(100vh-220px)] max-w-[calc(100vw-760px)] object-contain"
              />
              {viewMode === 'overlay' && (
                <img
                  src={page.layers.source_url}
                  alt={`Overlay ${page.index}`}
                  className="absolute inset-0 h-full w-full object-contain opacity-35 pointer-events-none"
                />
              )}
            </div>
          )}
        </main>

        <aside className="w-[390px] border-l border-slate-900 bg-slate-950/85 flex flex-col">
          <div className="px-4 py-3 border-b border-slate-900">
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Inspector</div>
            <div className="mt-2 text-sm text-slate-300">
              {page ? `${page.width} × ${page.height} · ${page.status}` : 'No page selected'}
            </div>
          </div>
          <div className="px-4 py-3 border-b border-slate-900">
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Layers</div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              {page && [
                ['Source', page.layers.source_url],
                ['Rendered', page.layers.rendered_url],
                ['Inpainted', page.layers.inpainted_url],
                ['Overlay JSON', page.layers.overlay_text_url],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2">
                  <div className="text-slate-500 uppercase tracking-[0.18em]">{label}</div>
                  <div className="truncate mt-1 text-slate-300" title={value}>{value}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs uppercase tracking-[0.24em] text-slate-500">Blocks</div>
              <button
                onClick={() => void applyDraftChanges()}
                disabled={!project || !page || !!busyAction}
                className="px-3 py-2 rounded-lg border border-slate-700 bg-slate-900/60 text-xs uppercase tracking-[0.18em] text-slate-300 disabled:opacity-50"
              >
                Save Page Changes
              </button>
            </div>
            <div className="mt-3 space-y-3">
              {(page?.blocks || []).length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 px-4 py-6 text-sm text-slate-500">
                  No editable text blocks yet. Run `Translate Current Page` or `Translate Selected` to generate OCR-based editable blocks.
                </div>
              )}
              {(page?.blocks || []).map((block) => (
                <div key={block.block_id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-slate-200">{block.block_id}</div>
                    <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{block.origin}</div>
                  </div>
                  <div className="mt-3 text-xs text-slate-500">OCR</div>
                  <textarea
                    value={blockDrafts[block.block_id]?.source_text ?? block.source_text ?? ''}
                    onChange={(event) => updateDraft(block.block_id, { source_text: event.target.value })}
                    className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 min-h-[78px] outline-none focus:border-primary"
                  />
                  <div className="mt-3 text-xs text-slate-500">Translation</div>
                  <textarea
                    value={blockDrafts[block.block_id]?.translation ?? block.translation ?? ''}
                    onChange={(event) => updateDraft(block.block_id, { translation: event.target.value })}
                    className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 min-h-[92px] outline-none focus:border-primary"
                  />
                  <div className="mt-3 grid grid-cols-3 gap-3">
                    <label className="text-xs text-slate-500">
                      Font Size
                      <input
                        type="number"
                        value={blockDrafts[block.block_id]?.font_size ?? block.style.font_size}
                        onChange={(event) => updateDraft(block.block_id, { font_size: Number(event.target.value || block.style.font_size) })}
                        className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                      />
                    </label>
                    <label className="text-xs text-slate-500">
                      Fill
                      <input
                        type="color"
                        value={blockDrafts[block.block_id]?.fill ?? block.style.fill}
                        onChange={(event) => updateDraft(block.block_id, { fill: event.target.value })}
                        className="mt-1 h-[42px] w-full rounded-xl border border-slate-800 bg-slate-950/70 px-1 py-1"
                      />
                    </label>
                    <label className="text-xs text-slate-500">
                      Stroke
                      <input
                        type="number"
                        value={blockDrafts[block.block_id]?.stroke_width ?? block.style.stroke_width}
                        onChange={(event) => updateDraft(block.block_id, { stroke_width: Number(event.target.value || block.style.stroke_width) })}
                        className="mt-1 w-full rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-sm text-slate-200 outline-none focus:border-primary"
                      />
                    </label>
                  </div>
                  <div className="mt-3 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    {block.flags.join(' · ') || 'no flags'}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>

      <div className="h-8 border-t border-slate-900 bg-slate-950/80 px-4 text-[11px] uppercase tracking-[0.2em] text-slate-500 flex items-center justify-between">
        <span>{page ? `Page ${page.index} · ${viewMode}` : 'No page loaded'}</span>
        <span>{activeJob ? `${activeJob.stage} · ${activeJob.status} · ${activeJob.message}` : (busyAction || project?.project_id || 'MangaCore workbench')}</span>
      </div>
    </div>
  );
};
