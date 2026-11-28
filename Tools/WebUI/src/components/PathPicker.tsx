import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Check, ChevronRight, FileText, Folder, FolderOpen, Home, LoaderCircle, X } from 'lucide-react';
import { ApiClient, errorMessage } from '../api/client';
import { t } from '../i18n';
import { Feedback } from './Feedback';

export type PathSelectionMode = 'file' | 'directory' | 'any';
interface PathEntry { name: string; path: string; kind: 'file' | 'directory' }
interface DirectoryListing {
  path: string; parent: string | null; selected_path: string | null;
  entries: PathEntry[]; locations: { name: string; path: string }[];
  next_offset: number | null; truncated: boolean;
}

const locationKeys: Record<string, string> = {
  '项目目录': 'gui.path.projectDirectory',
  '用户目录': 'gui.path.userDirectory',
  '文件系统': 'gui.path.fileSystem',
};
const locationLabel = (name: string) => locationKeys[name] ? t(locationKeys[name]) : name;

export function PathPicker({ api, mode = 'directory', initialPath = '', title = t('gui.path.title'), onSelect, onClose }: {
  api: ApiClient; mode?: PathSelectionMode; initialPath?: string; title?: string;
  onSelect: (path: string) => void; onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const [listing, setListing] = useState<DirectoryListing>();
  const [location, setLocation] = useState(initialPath);
  const [selected, setSelected] = useState<PathEntry>();
  const [showHidden, setShowHidden] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const browse = async (path: string, hidden = showHidden, offset = 0) => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError(''); setSelected(undefined);
    const query = new URLSearchParams({ path, show_hidden: String(hidden), directories_only: String(mode === 'directory'), offset: String(offset) });
    try {
      const result = await api.request<DirectoryListing>(`/files/browse?${query}`, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setListing(result); setLocation(result.path);
      if (result.selected_path) setSelected({ path: result.selected_path, name: result.selected_path.split(/[\\/]/).pop() || result.selected_path, kind: 'file' });
    } catch (failure) { if (!controller.signal.aborted) setError(errorMessage(failure)); }
    finally { if (request.current === controller) { request.current = null; setLoading(false); } }
  };
  useEffect(() => {
    const element = dialog.current; element?.showModal(); void browse(initialPath);
    const leave = () => onClose();
    window.addEventListener('hashchange', leave);
    return () => { request.current?.abort(); element?.close(); window.removeEventListener('hashchange', leave); };
  }, []);
  const selectedPath = selected && (mode !== 'file' || selected.kind === 'file') ? selected.path
    : mode !== 'file' ? listing?.path : undefined;
  const locationChanged = !!listing && location !== listing.path;
  const choose = () => { if (selectedPath && !loading && !error && !locationChanged) onSelect(selectedPath); };

  return <dialog ref={dialog} className="path-picker" aria-label={title} onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header className="dialog-heading"><div><h2>{title}</h2><p className="path-picker-hint">{t('gui.path.hostHint')}</p></div>
      <button type="button" className="icon-button" aria-label={t('gui.path.close')} onClick={onClose}><X size={18} /></button>
    </header>
    <div className="path-picker-body">
      <div className="path-picker-toolbar">
        <button type="button" className="icon-button" title={t('gui.path.projectDirectory')} aria-label={t('gui.path.openProject')} onClick={() => void browse('')}><Home size={18} /></button>
        <button type="button" className="icon-button" title={t('gui.path.parentDirectory')} aria-label={t('gui.path.openParent')} disabled={!listing?.parent || loading}
          onClick={() => listing?.parent && void browse(listing.parent)}><ArrowUp size={18} /></button>
        <input aria-label={t('gui.path.location')} value={location} onChange={(event) => setLocation(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void browse(location); } }} />
        <button type="button" className="secondary-button" disabled={loading} onClick={() => void browse(location)}>{t('gui.path.go')}</button>
      </div>
      <div className="path-picker-locations">
        {listing?.locations.map((item) => <button type="button" key={item.path} className="text-button" title={item.path} onClick={() => void browse(item.path)}>{locationLabel(item.name)}</button>)}
        <label><input type="checkbox" checked={showHidden} onChange={(event) => { setShowHidden(event.target.checked); void browse(listing?.path || '', event.target.checked); }} />{t('gui.path.showHidden')}</label>
      </div>
      {error && <Feedback message={error} retry={() => void browse(location)} />}
      <div className="path-picker-entries" aria-busy={loading} aria-label={t('gui.path.contents')}>
        {loading && <div className="loading" role="status"><LoaderCircle size={16} className="spin" />{t('gui.path.reading')}</div>}
        {!loading && !error && listing?.entries.length === 0 && <p className="muted path-picker-empty">{t('gui.path.empty')}</p>}
        {!error && listing?.entries.map((entry) => <div key={entry.path + entry.name} className={`path-picker-entry ${selected?.path === entry.path ? 'selected' : ''}`}>
          <button type="button" className="path-entry-name" disabled={loading || locationChanged} aria-pressed={selected?.path === entry.path}
            onClick={() => setSelected(entry)} onDoubleClick={() => entry.kind === 'directory' ? void browse(entry.path) : onSelect(entry.path)}>
            {entry.kind === 'directory' ? <Folder size={18} /> : <FileText size={18} />}<span title={entry.path}>{entry.name}</span>
          </button>
          {entry.kind === 'directory' && <button type="button" className="icon-button" disabled={loading} aria-label={t('gui.path.openFolder', { name: entry.name })} onClick={() => void browse(entry.path)}><ChevronRight size={17} /></button>}
        </div>)}
      </div>
      {listing && !error && <div className="path-picker-pagination">
        <button type="button" className="text-button" disabled={loading} onClick={() => void browse(listing.path)}>{t('gui.path.firstPage')}</button>
        {listing.next_offset !== null && <button type="button" className="text-button" disabled={loading} onClick={() => void browse(listing.path, showHidden, listing.next_offset!)}>{t('gui.path.nextPage')}</button>}
        {listing.truncated && <span className="muted">{t('gui.path.truncated')}</span>}
      </div>}
    </div>
    <footer className="dialog-footer path-picker-footer">
      <span className="path-picker-selected" title={selectedPath}>{selectedPath || t('gui.path.chooseFile')}</span>
      <button type="button" className="secondary-button" onClick={onClose}>{t('gui.common.cancel')}</button>
      <button type="button" className="primary-button" disabled={!selectedPath || loading || !!error || locationChanged} onClick={choose}>
        {selected?.kind === 'file' ? <Check size={16} /> : <FolderOpen size={16} />}{t(selected?.kind === 'file' ? 'gui.path.selectFile' : 'gui.path.selectDirectory')}
      </button>
    </footer>
  </dialog>;
}
