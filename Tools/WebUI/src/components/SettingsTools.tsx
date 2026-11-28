import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowUp, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { ApiClient, ApiError, errorMessage } from '../api/client';
import { translateSetting } from '../appearance/settingLabels';
import { t } from '../i18n';
import { Feedback, Loading } from './Feedback';
import { AutomationSettings } from './AutomationSettings';
import { AgentPrompt } from './AgentPrompt';
import { settingsScope, useSettingsHistory } from '../api/settingsHistory';

interface Props { api: ApiClient; active: boolean; disabled: boolean; onConfigurationChanged?: () => void }
interface Platform { name: string; local: boolean }
interface PoolDocument { pool: string[]; revision: string; platforms: Platform[]; scope: string }
interface PoolUndo { before: string[]; after: string[]; scope: string }

export const getSettingsTools = () => [
  { id: 'api-pool', title: translateSetting('menu_api_pool_settings', t('gui.tools.poolTitle')) },
  { id: 'automation', title: translateSetting('menu_automation', t('gui.tools.automationTitle')) },
  { id: 'agent-guide', title: translateSetting('setting_external_agent_mcp_guide', t('gui.tools.agentTitle')) },
] as const;

function ToolPanel({ title, visible, children }: { title: string; visible: boolean; children: ReactNode }) {
  const [visited, setVisited] = useState(visible);
  useEffect(() => { if (visible) setVisited(true); }, [visible]);
  return <section className="settings-tool panel" aria-label={title} hidden={!visible}>
    <h2>{title}</h2>{(visited || visible) && <div className="settings-tool-content">{children}</div>}
  </section>;
}

function ApiPool({ api, active, disabled, onConfigurationChanged }: Props) {
  const [document, setDocument] = useState<PoolDocument>();
  const [pool, setPool] = useState<string[]>([]);
  const [candidate, setCandidate] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const request = useRef<AbortController | null>(null);
  const history = useSettingsHistory<PoolUndo>();
  const loadedScope = useRef<string | undefined>(undefined);
  const dirty = !!document && JSON.stringify(document.pool) !== JSON.stringify(pool);
  useEffect(() => {
    if (!active || document) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true);
    void (async () => {
      const raw = await api.request<Record<string, unknown>>('/config', { signal: controller.signal });
      const platforms = await api.request<Platform[]>('/system/platforms', { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (typeof raw._config_revision !== 'string') throw new Error(t('gui.tools.noRevision'));
      const saved = Array.isArray(raw.backup_apis) ? raw.backup_apis.filter((name): name is string => typeof name === 'string') : [];
      const scope = settingsScope(raw);
      if (loadedScope.current !== undefined && loadedScope.current !== scope) history.clear();
      loadedScope.current = scope;
      setDocument({ pool: saved, revision: raw._config_revision, platforms, scope }); setPool(saved); setError('');
    })().catch((failure: unknown) => { if (!controller.signal.aborted) setError(errorMessage(failure)); })
      .finally(() => { if (!controller.signal.aborted) { request.current = null; setBusy(false); } });
    return () => controller.abort();
  }, [api, active, document, refresh]);
  useEffect(() => () => request.current?.abort(), []);
  const reload = () => { setDocument(undefined); setNotice(''); setError(''); setConflict(false); setRefresh((value) => value + 1); };
  const save = async () => {
    if (!document || request.current || disabled || !dirty) return;
    const submitted = [...pool];
    const controller = new AbortController(); request.current = controller; setBusy(true); setError(''); setNotice('');
    try {
      const current = await api.request<Record<string, unknown>>('/config', { signal: controller.signal });
      if (settingsScope(current) !== document.scope) throw new ApiError(t('gui.tools.profileChanged'), 409);
      const currentPool = Array.isArray(current.backup_apis) ? current.backup_apis : [];
      if (JSON.stringify(currentPool) !== JSON.stringify(document.pool)) throw new ApiError(t('gui.tools.poolChanged'), 409);
      if (typeof current._config_revision !== 'string') throw new ApiError(t('gui.tools.noRevision'), 409);
      const response = await api.request<{ revision: string }>('/config', {
        method: 'POST', signal: controller.signal, body: { backup_apis: submitted, _config_revision: current._config_revision },
      });
      if (controller.signal.aborted) return;
      history.push({ before: currentPool as string[], after: submitted, scope: document.scope });
      setDocument({ ...document, pool: submitted, revision: response.revision }); setNotice(t('gui.tools.poolSaved')); onConfigurationChanged?.();
    } catch (failure) {
      if (!controller.signal.aborted) {
        setConflict(failure instanceof ApiError && failure.status === 409);
        setError(t('gui.tools.savePaused', { error: errorMessage(failure) }));
      }
    } finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); } }
  };
  const undo = async () => {
    const entry = history.latest();
    if (!entry || !document || request.current || disabled || dirty || conflict || error) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setUndoing(true); setError(''); setNotice('');
    try {
      const current = await api.request<Record<string, unknown>>('/config', { signal: controller.signal });
      const currentPool = Array.isArray(current.backup_apis) ? current.backup_apis : [];
      if (settingsScope(current) !== entry.value.scope || JSON.stringify(currentPool) !== JSON.stringify(entry.value.after)) {
        throw new ApiError(t('gui.tools.poolScopeChanged'), 409);
      }
      if (typeof current._config_revision !== 'string') throw new ApiError(t('gui.tools.noRevision'), 409);
      const saved = await api.request<{ revision: string }>('/config', {
        method: 'POST', signal: controller.signal,
        body: { backup_apis: entry.value.before, _config_revision: current._config_revision },
      });
      controller.signal.throwIfAborted();
      setDocument({ ...document, pool: [...entry.value.before], revision: saved.revision });
      setPool([...entry.value.before]); history.pop(entry); setNotice(t('gui.tools.poolUndone')); onConfigurationChanged?.();
    } catch (failure) {
      if (!controller.signal.aborted) {
        setConflict(failure instanceof ApiError && failure.status === 409);
        setError(t('gui.tools.undoRetained', { error: errorMessage(failure) }));
      }
    } finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); setUndoing(false); } }
  };
  useEffect(() => {
    if (!dirty || disabled || busy || error) return;
    const timer = setTimeout(() => void save(), 600);
    return () => clearTimeout(timer);
  }, [pool, document, disabled, busy, error]);
  const move = (index: number, delta: number) => setPool((current) => {
    const result = [...current]; [result[index], result[index + delta]] = [result[index + delta], result[index]]; return result;
  });
  const candidates = document?.platforms.filter((platform) => !platform.local && !pool.includes(platform.name)) || [];
  const locked = disabled || undoing;
  return <>
    {error && <Feedback message={error} retry={!document ? reload : !conflict && !busy ? () => setError('') : undefined} />}
    {!document && busy && <Loading />}
    {document && <>
      <p className="muted settings-tool-hint">{t('gui.tools.poolHint')}</p>
      {pool.length === 0 ? <p className="muted">{t('gui.tools.emptyPool')}</p> : <ol className="settings-pool-list">{pool.map((name, index) => <li key={`${name}-${index}`}>
        <span>{name}</span><div className="settings-tool-actions">
          <button type="button" className="icon-button" aria-label={t('gui.tools.moveUp', { name })} disabled={locked || index === 0} onClick={() => move(index, -1)}><ArrowUp size={15} /></button>
          <button type="button" className="icon-button" aria-label={t('gui.tools.moveDown', { name })} disabled={locked || index === pool.length - 1} onClick={() => move(index, 1)}><ArrowDown size={15} /></button>
          <button type="button" className="icon-button" aria-label={t('gui.tools.remove', { name })} disabled={locked} onClick={() => setPool(pool.filter((_, position) => position !== index))}><Trash2 size={15} /></button>
        </div>
      </li>)}</ol>}
      <div className="settings-tool-actions"><select aria-label={t('gui.tools.fallbackPlatform')} value={candidate} disabled={locked || !candidates.length} onChange={(event) => setCandidate(event.target.value)}>
        <option value="">{t('gui.tools.choosePlatform')}</option>{candidates.map((platform) => <option key={platform.name} value={platform.name}>{platform.name}</option>)}
      </select><button type="button" className="secondary-button" disabled={locked || !candidates.some((platform) => platform.name === candidate)}
        onClick={() => { setPool([...pool, candidate]); setCandidate(''); setNotice(''); }}><Plus size={15} />{t('gui.tools.addPool')}</button></div>
      <div className="settings-tool-actions">
        {history.count > 0 && <button type="button" className="text-button" disabled={disabled || busy || dirty || conflict || !!error}
          onClick={() => void undo()} aria-label={t('gui.tools.undoPool')}><RotateCcw size={15} />{t('gui.tools.undoLast')}</button>}
        <button type="button" className="text-button" disabled={busy} onClick={reload}>{dirty ? t('gui.tools.discardReload') : t('gui.tools.reload')}</button>
      </div>
    </>}
    {(notice || busy || dirty) && <p className="settings-save-notice" role="status">{busy && document ? t('gui.tools.saving') : dirty && !error ? t('gui.tools.pending') : notice}</p>}
  </>;
}

export function SettingsTools({ selected, search, ...props }: Props & { selected: string; search: string }) {
  return <div className="settings-tools">
    {getSettingsTools().map(({ id, title }) => {
      const visible = search ? title.toLowerCase().includes(search) : selected === id;
      const active = props.active && visible;
      return <ToolPanel key={id} title={title} visible={visible}>
        {id === 'api-pool' ? <ApiPool {...props} active={active} /> : id === 'automation' ? <AutomationSettings {...props} active={active} /> : <AgentPrompt api={props.api} disabled={props.disabled} />}
      </ToolPanel>;
    })}
  </div>;
}
