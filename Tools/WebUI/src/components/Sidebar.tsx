import { t } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { Languages, ListTodo, PenLine, Settings2 } from 'lucide-react';
import { PAGE_ORDER, type Page } from '../appearance/navigation';
import type { SidebarMode } from '../appearance/preferences';

export type { Page } from '../appearance/navigation';
const navigation = {
  translate: { label: 'gui.nav.translate', icon: Languages },
  polish: { label: 'gui.nav.polish', icon: PenLine },
  tasks: { label: 'gui.nav.tasks', icon: ListTodo },
  settings: { label: 'gui.nav.settings', icon: Settings2 },
} as const;

export function Sidebar({ page, mode, position }: { page: Page; mode: SidebarMode; position: number }) {
  const sidebar = useRef<HTMLElement>(null);
  const [temporaryOpen, setTemporaryOpen] = useState(false);
  const open = mode === 'fixed' || temporaryOpen;
  useEffect(() => {
    setTemporaryOpen(false);
    const closeOutside = (event: PointerEvent) => {
      if (!sidebar.current?.contains(event.target as Node | null)) setTemporaryOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [mode]);

  return <aside ref={sidebar} className={`sidebar ${open ? 'is-open' : ''}`} aria-label={t('gui.nav.main')} data-mode={mode}
    onPointerDown={() => setTemporaryOpen(true)}
    onFocusCapture={() => setTemporaryOpen(true)}
    onBlurCapture={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setTemporaryOpen(false);
    }}>
    <a className="brand" href="#/translate" aria-label={t('gui.nav.brandTranslate')} title="AiNiee-Next">
      <span className="brand-symbol"><img src="/logo.jpg" alt="AiNiee-Next" /></span>
      <span className="sidebar-label brand-name">AiNiee-Next<span>{t('gui.nav.tagline')}</span></span>
    </a>
    <nav>
      <span className="nav-selection" aria-hidden="true" style={{ transform: `translateY(${position * 54}px)` }} />
      {PAGE_ORDER.map((id) => {
        const { label: labelKey, icon: Icon } = navigation[id];
        const label = t(labelKey);
        return <a key={id} href={`#/${id}`} className={`nav-item ${page === id ? 'active' : ''}`}
          aria-current={page === id ? 'page' : undefined} title={!open ? label : undefined} aria-label={label}>
          <Icon size={20} strokeWidth={1.65} /><span className="sidebar-label">{label}</span>
        </a>;
      })}
    </nav>
  </aside>;
}
