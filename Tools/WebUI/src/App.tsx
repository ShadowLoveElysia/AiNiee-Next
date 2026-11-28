import { useEffect, useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import { ApiClient } from './api/client';
import { ApiContext } from './api/ApiContext';
import { applyAnimationPreference, applyTheme, readPreferences, savePreferences, type Preferences, type SidebarMode } from './appearance/preferences';
import { Sidebar, type Page } from './components/Sidebar';
import { PageDeck } from './components/PageDeck';
import { usePageMotion } from './appearance/usePageMotion';
import { Settings } from './pages/Settings';
import { Tasks } from './pages/Tasks';
import { CacheEditor } from './pages/CacheEditor';
import type { TaskRow } from './api/taskRows';
import { Workspace, type Draft } from './pages/Workspace';
import { browserPlatform, type PlatformAdapter } from './platform/adapter';
import { getLanguageRevision, setLocale, subscribeLanguage, t } from './i18n';
import { Feedback } from './components/Feedback';

function route(): Page {
  const path = window.location.hash.slice(2).split(/[/?]/)[0];
  return path === 'polish' || path === 'tasks' || path === 'settings' ? path : 'translate';
}

function cacheTaskId(): string {
  if (!window.location.hash.startsWith('#/tasks/cache?')) return '';
  return new URLSearchParams(window.location.hash.split('?')[1]).get('task_id') || '';
}

function NavigationLayout({ page, mode, animations, children }: { page: Page; mode: SidebarMode; animations: boolean; children: Record<Page, ReactNode> }) {
  const motion = usePageMotion(page, animations);
  return <>
    <Sidebar page={page} mode={mode} position={motion.position} />
    <main id="main-content" tabIndex={-1}>
      <PageDeck page={page} motion={motion}>{children}</PageDeck>
    </main>
  </>;
}

export function App({ platform = browserPlatform }: { platform?: PlatformAdapter }) {
  useSyncExternalStore(subscribeLanguage, getLanguageRevision);
  const [api] = useState(() => new ApiClient(platform.transport));
  const [page, setPage] = useState<Page>(route);
  const [cacheId, setCacheId] = useState(cacheTaskId);
  const [editingTask, setEditingTask] = useState<TaskRow>();
  const [preferences, setPreferences] = useState(() => readPreferences(platform.preferences));
  const [storageError, setStorageError] = useState(false);
  const [languageError, setLanguageError] = useState(false);
  const [translation, setTranslation] = useState<Draft>({ taskType: 'translate', profile: '', source: 'auto', target: '', customSource: '', customTarget: '', outputPath: '' });
  const [polishing, setPolishing] = useState<Draft>({ taskType: 'polish', profile: '', source: 'auto', target: '', customSource: '', customTarget: '', outputPath: '' });
  useEffect(() => {
    const onHash = () => { setPage(route()); setCacheId(cacheTaskId()); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => {
    applyTheme(preferences.theme);
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const change = () => applyTheme(preferences.theme);
    media.addEventListener('change', change);
    return () => media.removeEventListener('change', change);
  }, [preferences.theme]);
  useLayoutEffect(() => applyAnimationPreference(preferences.uiAnimations), [preferences.uiAnimations]);
  useEffect(() => {
    void setLocale(preferences.language).then(() => setLanguageError(false)).catch(() => setLanguageError(true));
  }, [preferences.language]);
  useEffect(() => {
    const sync = () => setPreferences(readPreferences(platform.preferences));
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, [platform]);
  const update = (changes: Partial<Preferences>) => {
    const next = { ...preferences, ...changes };
    setPreferences(next); setStorageError(!savePreferences(next, platform.preferences));
  };
  return <ApiContext.Provider value={api}><div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>{t('gui.common.skipContent')}</a>
    {languageError && <div className="language-error"><Feedback message={t('gui.common.languageLoadFailed')} retry={() => {
      void setLocale(preferences.language).then(() => setLanguageError(false)).catch(() => setLanguageError(true));
    }} /></div>}
    <NavigationLayout page={page} mode={preferences.sidebar} animations={preferences.uiAnimations}>{ {
        translate: <Workspace api={api} kind="translate" active={page === 'translate'} draft={translation} onDraft={setTranslation} />,
        polish: <Workspace api={api} kind="polish" active={page === 'polish'} draft={polishing} onDraft={setPolishing} />,
        tasks: <>
          <div hidden={!!cacheId}><Tasks api={api} active={page === 'tasks' && !cacheId} onEditFile={(task) => {
            setEditingTask(task);
            window.location.hash = `/tasks/cache?task_id=${encodeURIComponent(task.taskId)}`;
          }} /></div>
          {cacheId && <CacheEditor taskId={cacheId} task={editingTask?.taskId === cacheId ? editingTask : undefined} />}
        </>,
        settings: <Settings api={api} active={page === 'settings'} preferences={preferences} update={update} storageError={storageError} />,
    } }</NavigationLayout>
  </div></ApiContext.Provider>;
}
