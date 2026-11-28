import { useState } from 'react';
import { t } from '../i18n';
import { FolderOpen } from 'lucide-react';
import type { ApiClient } from '../api/client';
import { PathPicker, type PathSelectionMode } from './PathPicker';

export function PathField({ api, id, value, label, mode = 'directory', disabled = false, issue, onChange }: {
  api: ApiClient; id?: string; value: string; label: string; mode?: PathSelectionMode;
  disabled?: boolean; issue?: string; onChange: (path: string) => void;
}) {
  const [choosing, setChoosing] = useState(false);
  return <div className="path-field">
    <input id={id} type="text" aria-label={label} value={value} disabled={disabled} aria-invalid={!!issue}
      onChange={(event) => onChange(event.target.value)} />
    <button type="button" className="secondary-button" disabled={disabled} aria-label={t('gui.path.selectLabel', { label })} onClick={() => setChoosing(true)}><FolderOpen size={16} />{t('gui.common.select')}</button>
    {choosing && <PathPicker api={api} initialPath={value} mode={mode} title={t('gui.path.selectLabel', { label })} onClose={() => setChoosing(false)}
      onSelect={(path) => { onChange(path); setChoosing(false); }} />}
  </div>;
}
