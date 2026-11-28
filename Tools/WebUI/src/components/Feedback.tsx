import { AlertCircle, LoaderCircle, RotateCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { t } from '../i18n';

export function Loading({ children = t('gui.common.loading') }: { children?: string }) {
  return <div className="loading" role="status"><LoaderCircle size={17} className="spin" />{children}</div>;
}

export function QuietLoading({ label }: { label: string }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), 350);
    return () => clearTimeout(timer);
  }, []);
  return <div className="quiet-loading" aria-busy="true" aria-label={label}>{visible && <span />}</div>;
}

export function Feedback({ message, retry, stale = false }: { message: string; retry?: () => void; stale?: boolean }) {
  return <div className="feedback" role="alert">
    <AlertCircle size={18} aria-hidden="true" />
    <span>{stale && t('gui.controls.staleContent')}{message}</span>
    {retry && <button className="text-button" onClick={retry}><RotateCw size={14} />{t('gui.common.retry')}</button>}
  </div>;
}
