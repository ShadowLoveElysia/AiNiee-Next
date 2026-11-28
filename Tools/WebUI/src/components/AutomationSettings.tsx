import { useEffect, useRef, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { ApiClient, ApiError, errorMessage } from '../api/client';
import { settingsScope, useSettingsHistory } from '../api/settingsHistory';
import { Feedback, Loading } from './Feedback';
import { SchemaField } from './SchemaField';
import { AutomationEntries } from './AutomationEntries';
import { getIntlLocale, t } from '../i18n';

type Section = 'scheduler' | 'watch_mode' | 'output_collection';
interface Configuration {
  revision: string; scheduler: Record<string, unknown>; watch_mode: Record<string, unknown>; output_collection: Record<string, unknown>;
}
interface Props { api: ApiClient; active: boolean; disabled: boolean; onConfigurationChanged?: () => void }
interface AutomationUndo { section: Section; before: Record<string, unknown>; after: Record<string, unknown>; scope: string }
const sections: { key: Section; name: string; fields: { key: string; type: 'bool' | 'int' | 'path' | 'choice' | 'list'; label: string; choices?: string[]; default: unknown }[] }[] = [
  { key: 'scheduler', name: 'gui.automation.scheduler', fields: [
    { key: 'enabled', type: 'bool', label: 'gui.automation.enableScheduler', default: false },
    { key: 'tasks', type: 'list', label: 'gui.automation.tasks', default: [] },
  ] },
  { key: 'watch_mode', name: 'gui.automation.watch', fields: [
    { key: 'enabled', type: 'bool', label: 'gui.automation.enableWatch', default: false },
    { key: 'scan_interval', type: 'int', label: 'gui.automation.scanInterval', default: 1 },
    { key: 'max_concurrent', type: 'int', label: 'gui.automation.maxConcurrent', default: 2 },
    { key: 'rules', type: 'list', label: 'gui.automation.rules', default: [] },
  ] },
  { key: 'output_collection', name: 'gui.automation.collection', fields: [
    { key: 'enabled', type: 'bool', label: 'gui.automation.enableCollection', default: false },
    { key: 'output_path', type: 'path', label: 'gui.automation.collectionDirectory', default: '' },
    { key: 'collision_policy', type: 'choice', label: 'gui.automation.collisionPolicy', choices: ['rename', 'overwrite'], default: 'rename' },
  ] },
];

export function AutomationSettings({ api, active, disabled, onConfigurationChanged }: Props) {
  const [document, setDocument] = useState<Configuration>();
  const [draft, setDraft] = useState<Configuration>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [paused, setPaused] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [rejected, setRejected] = useState<Partial<Record<Section, string>>>({});
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [refresh, setRefresh] = useState(0);
  const [expression, setExpression] = useState('');
  const [preview, setPreview] = useState('');
  const request = useRef<AbortController | null>(null);
  const scope = useRef<string | undefined>(undefined);
  const history = useSettingsHistory<AutomationUndo>();
  const readConfiguration = async (signal: AbortSignal) => {
    const [config, value] = await Promise.all([
      api.request<Record<string, unknown>>('/config', { signal }),
      api.request<Configuration>('/automation/configuration', { signal }),
    ]);
    if (config._config_revision !== value.revision) throw new ApiError(t('gui.automation.configurationChanging'), 409);
    return { value, scope: settingsScope(config) };
  };
  useEffect(() => {
    if (!active || document) return;
    const controller = new AbortController(); request.current = controller; setBusy(true);
    void readConfiguration(controller.signal).then(({ value, scope: nextScope }) => {
      if (!controller.signal.aborted) {
        if (scope.current !== undefined && scope.current !== nextScope) history.clear();
        scope.current = nextScope;
        setDocument(value); setDraft(value); setInvalid({}); setError('');
      }
    }).catch((failure: unknown) => { if (!controller.signal.aborted) setError(errorMessage(failure)); })
      .finally(() => { if (!controller.signal.aborted) { request.current = null; setBusy(false); } });
    return () => controller.abort();
  }, [api, active, document, refresh]);
  useEffect(() => () => request.current?.abort(), []);
  const changed = sections.filter(({ key }) => document && draft && JSON.stringify(document[key]) !== JSON.stringify(draft[key]));
  const reload = () => {
    setDocument(undefined); setDraft(undefined); setNotice(''); setError(''); setPaused(false); setConflict(false); setRejected({});
    setRefresh((value) => value + 1);
  };
  const save = async (section: Section) => {
    if (!document || !draft || disabled || request.current || Object.entries(invalid).some(([key, message]) => key.startsWith(section + '.') && message)) return;
    const submitted = draft[section];
    const fingerprint = JSON.stringify(submitted);
    const controller = new AbortController(); request.current = controller; setBusy(true); setError(''); setNotice('');
    try {
      const { value: current, scope: currentScope } = await readConfiguration(controller.signal);
      if (currentScope !== scope.current) throw new ApiError(t('gui.tools.profileChanged'), 409);
      if (JSON.stringify(current[section]) !== JSON.stringify(document[section])) throw new ApiError(t('gui.automation.changedElsewhere'), 409);
      const target = section === 'output_collection' ? 'automation_output_collection' : section;
      const result = await api.request<Configuration>(`/automation/configuration/${target}`, {
        method: 'PUT', signal: controller.signal, body: { expected_revision: current.revision, data: submitted },
      });
      if (controller.signal.aborted) return;
      history.push({ section, before: current[section], after: result[section], scope: currentScope });
      setDraft((current) => current && ({ ...current, revision: result.revision,
        ...(JSON.stringify(current[section]) === fingerprint ? { [section]: result[section] } : {}),
      }));
      setDocument((previous) => previous && ({ ...previous, revision: result.revision, [section]: result[section] }));
      setNotice(t('gui.automation.sectionSaved', { section: t(sections.find((item) => item.key === section)!.name) })); onConfigurationChanged?.();
    } catch (failure) {
      if (!controller.signal.aborted) {
        const invalidRequest = failure instanceof ApiError && failure.status === 422;
        if (invalidRequest) setRejected((current) => ({ ...current, [section]: fingerprint }));
        else { setPaused(true); setConflict(failure instanceof ApiError && failure.status === 409); }
        setError(t(invalidRequest ? 'gui.automation.invalidRetained' : 'gui.tools.savePaused', { error: errorMessage(failure) }));
      }
    } finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); } }
  };
  const undo = async () => {
    const entry = history.latest();
    if (!entry || !document || !draft || disabled || request.current || changed.length || conflict || error || Object.values(invalid).some(Boolean)) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setUndoing(true); setError(''); setNotice('');
    try {
      const { value: current, scope: currentScope } = await readConfiguration(controller.signal);
      const { section, before, after } = entry.value;
      if (currentScope !== entry.value.scope || JSON.stringify(current[section]) !== JSON.stringify(after)) {
        throw new ApiError(t('gui.automation.scopeChanged'), 409);
      }
      const target = section === 'output_collection' ? 'automation_output_collection' : section;
      const result = await api.request<Configuration>(`/automation/configuration/${target}`, {
        method: 'PUT', signal: controller.signal, body: { expected_revision: current.revision, data: before },
      });
      controller.signal.throwIfAborted();
      setDocument(result); setDraft(result); setInvalid({}); setRejected({}); history.pop(entry);
      setNotice(t('gui.automation.undone')); onConfigurationChanged?.();
    } catch (failure) {
      if (!controller.signal.aborted) {
        setPaused(true); setConflict(failure instanceof ApiError && failure.status === 409);
        setError(t('gui.tools.undoRetained', { error: errorMessage(failure) }));
      }
    } finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); setUndoing(false); } }
  };
  useEffect(() => {
    if (!draft || !document || disabled || busy || paused) return;
    const next = changed.find(({ key }) => rejected[key] !== JSON.stringify(draft[key])
      && !Object.entries(invalid).some(([field, message]) => field.startsWith(key + '.') && message));
    if (!next) return;
    const timer = setTimeout(() => void save(next.key), 600);
    return () => clearTimeout(timer);
  }, [draft, document, disabled, busy, paused, rejected, invalid]);
  const previewSchedule = async () => {
    if (request.current || !expression.trim()) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setError(''); setPreview('');
    try {
      const result = await api.request<{ next_run: string | null }>('/automation/scheduler/preview', {
        method: 'POST', signal: controller.signal, body: { expression: expression.trim(), trigger_type: 'scheduled' },
      });
      if (!controller.signal.aborted) setPreview(result.next_run ? t('gui.automation.nextRun', { time: new Date(result.next_run).toLocaleString(getIntlLocale()) }) : t('gui.automation.noNextRun'));
    } catch (failure) { if (!controller.signal.aborted) setError(errorMessage(failure)); }
    finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); } }
  };
  return <>
    {error && <Feedback message={error} retry={!document ? reload : paused && !conflict && !busy ? () => { setPaused(false); setError(''); } : undefined} />}
    {!document && busy && <Loading />}
    {draft && document && <>
      <p className="muted settings-tool-hint">{t('gui.automation.saveHint')}</p>
      {sections.map(({ key: section, name, fields }) => <details className="automation-section" key={section}>
        <summary>{t(name)}</summary>
        {fields.map((field) => field.type === 'list' ? <AutomationEntries key={field.key} kind={section as 'scheduler' | 'watch_mode'}
          entries={draft[section][field.key]} disabled={disabled || undoing}
          onValidityChange={(message) => setInvalid((current) => ({ ...current, [`${section}.${field.key}`]: message }))}
          onChange={(value) => { setDraft((current) => current && ({ ...current, [section]: { ...current[section], [field.key]: value } })); setNotice(''); }} />
          : <SchemaField key={field.key} field={{ key: field.key, type: field.type, choices: field.choices || [], minimum: field.type === 'int' ? 1 : null, maximum: field.type === 'int' ? 3600 : null }}
          label={t(field.label)} value={draft[section][field.key] ?? field.default} disabled={disabled || undoing}
          onValidityChange={(message) => setInvalid((current) => ({ ...current, [`${section}.${field.key}`]: message }))}
          onChange={(value) => { setDraft((current) => current && ({ ...current, [section]: { ...current[section], [field.key]: value } })); setNotice(''); }} />)}
      </details>)}
      <div className="settings-schedule-preview"><label htmlFor="schedule-expression">{t('gui.automation.validateSchedule')}</label>
        <div className="settings-tool-actions"><input id="schedule-expression" value={expression} onChange={(event) => { setExpression(event.target.value); setPreview(''); }} placeholder={t('gui.automation.scheduleExample')} />
          <button type="button" className="secondary-button" disabled={disabled || busy || !expression.trim()} onClick={() => void previewSchedule()}>{t('gui.automation.previewSchedule')}</button></div>
        {preview && <p role="status">{preview}</p>}
      </div>
      <div className="settings-tool-actions">
        {history.count > 0 && <button type="button" className="text-button" disabled={disabled || busy || changed.length > 0 || conflict || !!error || Object.values(invalid).some(Boolean)}
          onClick={() => void undo()} aria-label={t('gui.automation.undo')}><RotateCcw size={15} />{t('gui.tools.undoLast')}</button>}
        <button type="button" className="text-button" disabled={busy} onClick={reload}>{changed.length ? t('gui.tools.discardReload') : t('gui.tools.reload')}</button>
      </div>
    </>}
    {(notice || busy || changed.length > 0) && <p className="settings-save-notice" role="status">{busy && document ? t('gui.automation.processing') : changed.length > 0 && !error ? t('gui.tools.pending') : notice}</p>}
  </>;
}
