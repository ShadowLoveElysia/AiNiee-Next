import { getIntlLocale, t } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { FileText, FolderOpen, LoaderCircle, Upload, X } from 'lucide-react';
import { ApiClient, errorMessage } from '../api/client';
import type { UploadResult } from '../api/contracts';
import { Feedback } from './Feedback';
import { PathPicker } from './PathPicker';

export interface DraftFile { path: string; name: string; size?: number }
export const fileName = (path: string) => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path;

export function FileImport({ api, file, disabled, onFile, onBusy, issue, onInvalidate }: {
  api: ApiClient; file?: DraftFile; disabled: boolean; onFile: (file?: DraftFile) => void;
  onBusy: (busy: boolean) => void; issue?: string; onInvalidate: () => void;
}) {
  const request = useRef<AbortController | null>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [uploadName, setUploadName] = useState('');
  const [error, setError] = useState('');
  const [choosingPath, setChoosingPath] = useState(false);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => setError(''), [file?.path]);
  const cancel = () => {
    request.current?.abort(); request.current = null; setUploadName(''); onBusy(false);
    setError(t('gui.fileImport.cancelled'));
  };
  const upload = async (files: FileList | File[]) => {
    if (disabled || request.current || files.length === 0) return;
    if (files.length !== 1) { setError(t('gui.fileImport.singleFile')); return; }
    const selected = files[0];
    const controller = new AbortController();
    request.current = controller; setError(''); setUploadName(selected.name); onBusy(true); onInvalidate();
    const body = new FormData(); body.append('file', selected);
    try {
      const result = await api.request<UploadResult>('/files/upload', { method: 'POST', body, signal: controller.signal, timeout: 120000 });
      if (controller.signal.aborted) return;
      if ('status' in result) setError(t('gui.fileImport.limitReached', { count: result.limit }));
      else onFile({ path: result.path, name: selected.name, size: selected.size });
    } catch (failure) {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    } finally {
      if (request.current === controller) { request.current = null; setUploadName(''); onBusy(false); }
    }
  };
  return <div className="import-section" onDragEnter={(event) => {
    event.preventDefault(); if (!disabled && !uploadName) { depth.current++; setDragging(true); }
  }} onDragOver={(event) => event.preventDefault()} onDragLeave={(event) => {
    event.preventDefault(); if (--depth.current <= 0) { depth.current = 0; setDragging(false); }
  }} onDrop={(event) => {
    event.preventDefault(); depth.current = 0; setDragging(false); void upload(event.dataTransfer.files);
  }}>
    {uploadName ? <div className="file-row"><LoaderCircle className="spin" size={24} />
      <div className="file-info"><strong title={uploadName}>{uploadName}</strong><span>{t('gui.fileImport.importing')}</span></div>
      <button className="text-button" onClick={cancel}>{t('gui.common.cancel')}</button>
    </div> : file ? <div className={`file-row ${dragging ? 'dragging' : ''}`}>
      <span className="file-icon"><FileText size={24} strokeWidth={1.5} /></span>
      <div className="file-info"><strong title={file.name}>{file.name}</strong>
        <span title={file.path}>{file.size === undefined ? file.path : new Intl.NumberFormat(getIntlLocale(), { maximumFractionDigits: 1 }).format(file.size / 1024) + ' KB'}</span>
      </div>
      <button className="text-button" disabled={disabled} onClick={() => setChoosingPath(true)}>{t('gui.fileImport.replace')}</button>
      <button className="icon-button" disabled={disabled} title={t('gui.fileImport.remove')} aria-label={t('gui.fileImport.remove')} onClick={() => { onFile(undefined); setError(''); }}><X size={17} /></button>
    </div> : <button type="button" className={`dropzone ${dragging ? 'dragging' : ''}`} disabled={disabled} onClick={() => setChoosingPath(true)}>
      <span className="upload-icon"><Upload size={26} strokeWidth={1.5} /></span>
      <strong>{t('gui.fileImport.dropHere')}</strong><span className="choose-file"><FolderOpen size={16} />{t('gui.fileImport.selectPath')}</span>
    </button>}
    {choosingPath && <PathPicker api={api} mode="any" initialPath={file?.path} title={t('gui.fileImport.selectInputPath')} onClose={() => setChoosingPath(false)}
      onSelect={(path) => { onFile({ path, name: fileName(path) }); setError(''); setChoosingPath(false); }} />}
    {(error || issue) && <Feedback message={error || issue!} />}
  </div>;
}
