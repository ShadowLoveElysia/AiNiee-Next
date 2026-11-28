import { useEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import { LoaderCircle, X } from 'lucide-react';
import { ApiClient, ApiError, errorMessage } from '../api/client';
import type { SuccessResponse } from '../api/contracts';
import { queueEditorPayload, queueEditorValues, type QueueFieldKey, type QueueRecord, type QueueTaskParameters } from '../api/queueContracts';
import { useResource } from '../api/useResource';
import { Feedback } from './Feedback';
import { SchemaField } from './SchemaField';
import { QueueRuntimeOverrides } from './QueueRuntimeOverrides';
import { CUSTOM_LANGUAGE, isKnownLanguage, LanguageField } from './LanguageField';

type Values = Partial<QueueTaskParameters>;
type Choice = readonly [string, string];
interface EditorField {
  key: QueueFieldKey;
  label: string;
  type?: 'string' | 'int' | 'bool' | 'dict' | 'list' | 'path';
  required?: boolean;
  choices?: readonly Choice[];
  description?: string;
}

function ParameterField({ field, value, disabled, issue, onChange, onValidity }: {
  field: EditorField; value: unknown; disabled: boolean; issue?: string;
  onChange: (value: unknown) => void; onValidity: (message: string) => void;
}) {
  const enabled = field.required || (value !== undefined && value !== null);
  const id = `queue-${field.key}`;
  return <div className="queue-parameter">
    {!field.required && <label className="parameter-override">
      <input type="checkbox" checked={!!enabled} disabled={disabled} onChange={(event) => {
        onValidity(''); onChange(event.target.checked ? field.type === 'bool' ? false : field.type === 'dict' ? {} : field.type === 'list' ? [] : '' : null);
      }} />{t('gui.queue.override', { label: field.label })}
    </label>}
    {field.choices ? <div className="field"><label htmlFor={id}>{field.label}</label>
      <select id={id} disabled={disabled || !enabled} value={String(value ?? '')} aria-invalid={!!issue}
        onChange={(event) => onChange(event.target.value)}>
        <option value="">{field.required ? t('gui.queue.choose') : t('gui.common.inherit')}</option>
        {value != null && value !== '' && !field.choices.some(([key]) => key === String(value)) && <option value={String(value)}>{String(value)}</option>}
        {field.choices.map(([key, label]) => <option value={key} key={key}>{label}</option>)}
      </select>{issue && <span className="field-error">{issue}</span>}
    </div> : <SchemaField field={{ key: id, type: field.type || 'string', choices: [], minimum: null, maximum: null }}
      value={value ?? (field.type === 'bool' ? false : field.type === 'dict' ? {} : field.type === 'list' ? [] : '')}
      label={field.label} description={field.description} disabled={disabled || !enabled} issue={issue}
      onChange={onChange} onValidityChange={onValidity} />}
  </div>;
}

function QueueLanguage({ kind, value, disabled, issue, onChange }: {
  kind: 'source' | 'target'; value: string | null | undefined; disabled: boolean; issue?: string; onChange: (value: string | null) => void;
}) {
  const enabled = value !== null && value !== undefined;
  const known = value === 'auto' || value === '' || isKnownLanguage(value || '');
  const [customSelected, setCustomSelected] = useState(!known && enabled);
  const label = kind === 'source' ? t('gui.queue.source') : t('gui.queue.target');
  return <div className="queue-parameter">
    <label className="parameter-override"><input type="checkbox" checked={enabled} disabled={disabled}
      onChange={(event) => { setCustomSelected(false); onChange(event.target.checked ? kind === 'source' ? 'auto' : '' : null); }} />{t('gui.queue.override', { label })}</label>
    <LanguageField idPrefix="queue-" kind={kind} disabled={disabled || !enabled}
      value={customSelected ? CUSTOM_LANGUAGE : value || (kind === 'source' ? 'auto' : '')}
      custom={customSelected ? value || '' : ''} issue={issue}
      onChange={(next) => { setCustomSelected(next === CUSTOM_LANGUAGE); onChange(next === CUSTOM_LANGUAGE ? '' : next); }} onCustom={onChange} />
  </div>;
}

export function QueueTaskEditor({ api, item, disabled = false, onClose, onSaved }: {
  api: ApiClient; item?: QueueRecord; disabled?: boolean; onClose: () => void; onSaved: () => void;
}) {
  const taskTypes: readonly Choice[] = [['translate', t('gui.tasks.type.translate')], ['polish', t('gui.tasks.type.polish')], ['all_in_one', t('gui.tasks.type.all_in_one')]];
  const numericFields: EditorField[] = [
    { key: 'threads', label: t('gui.queue.threads'), type: 'int' }, { key: 'retry', label: t('gui.queue.retry'), type: 'int' },
    { key: 'timeout', label: t('gui.queue.timeout'), type: 'int' }, { key: 'rounds', label: t('gui.queue.rounds'), type: 'int' },
    { key: 'pre_lines', label: t('gui.queue.pre_lines'), type: 'int' }, { key: 'lines_limit', label: t('gui.queue.lines_limit'), type: 'int' },
    { key: 'tokens_limit', label: t('gui.queue.tokens_limit'), type: 'int' }, { key: 'thinking_budget', label: t('gui.queue.thinking_budget'), type: 'int' },
    { key: 'think_depth', label: t('gui.queue.think_depth'), description: t('gui.queue.think_depth_hint') },
    { key: 'failover', label: t('gui.queue.failover'), type: 'bool' },
  ];
  const outputFields: EditorField[] = [
    { key: 'resume', label: t('gui.queue.resume'), type: 'bool' },
    { key: 'strict_export', label: t('gui.queue.strict_export'), type: 'bool' },
    { key: 'export_format', label: t('gui.queue.export_format'), choices: ['epub', 'mobi', 'azw3', 'fb2', 'pdf', 'txt', 'docx', 'htmlz', 'kepub'].map((value) => [value, value]) },
    { key: 'output_policy', label: t('gui.queue.output_policy'), choices: [['resume', t('gui.queue.policy.resume')], ['archive', t('gui.queue.policy.archive')], ['overwrite', t('gui.queue.policy.overwrite')], ['cancel', t('gui.queue.policy.cancel')]] },
  ];
  const [values, setValues] = useState<Values>(() => queueEditorValues(item));
  const [changed, setChanged] = useState<Set<QueueFieldKey>>(() => new Set());
  const [issues, setIssues] = useState<Record<string, string>>({});
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [reviewRequired, setReviewRequired] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const profiles = useResource<string[]>(api, '/profiles');
  const rules = useResource<string[]>(api, '/rules_profiles');
  const platforms = useResource<{ name: string }[]>(api, '/system/platforms');
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => { request.current?.abort(); element?.close(); };
  }, []);
  const change = (key: QueueFieldKey, value: unknown) => {
    setValues((current) => ({ ...current, [key]: value,
      ...(['output_policy', 'output_path'].includes(key) ? { output_policy_confirmed: false } : {}),
    }));
    setChanged((current) => new Set([...current, key, ...(['output_policy', 'output_path'].includes(key) ? ['output_policy_confirmed' as const] : [])]));
    setIssues((current) => ({ ...current, [key]: '' }));
  };
  const validity = (key: string, message: string) => setInvalid((current) => current[key] === message ? current : { ...current, [key]: message });
  const blocked = disabled || pending || reviewRequired;
  const parameter = (field: EditorField) => <ParameterField key={field.key} field={field} value={values[field.key]}
    disabled={blocked} issue={issues[field.key]} onChange={(value) => change(field.key, value)} onValidity={(message) => validity(field.key, message)} />;
  const destructive = values.output_policy === 'archive' || values.output_policy === 'overwrite';
  const save = async () => {
    if (request.current || blocked || Object.values(invalid).some(Boolean)) return;
    const payload = queueEditorPayload(values, changed, !!item);
    if (!item && !String(values.input_path || '').trim()) { setIssues({ input_path: t('gui.queue.input_required') }); return; }
    if (destructive && !values.output_policy_confirmed) { setIssues({ output_policy_confirmed: t('gui.queue.output_confirmation') }); return; }
    const controller = new AbortController(); request.current = controller; setPending(true); setError(''); setIssues({});
    try {
      const path = item ? `/queue/${encodeURIComponent(item.task_id)}?expected_revision=${encodeURIComponent(item.revision)}` : '/queue';
      const result = await api.request<SuccessResponse>(path, { method: item ? 'PUT' : 'POST', body: payload, signal: controller.signal });
      if (!result.success) throw new ApiError(t('gui.queue.save_failed'), 422);
      if (!controller.signal.aborted) onSaved();
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError) setIssues(Object.fromEntries(failure.issues.map((issue) => [issue.field, issue.message])));
      const uncertain = !(failure instanceof ApiError) || failure.status === 0 || failure.status >= 500;
      const conflict = failure instanceof ApiError && failure.status === 409;
      setReviewRequired(uncertain || conflict);
      setError(conflict ? t('gui.queue.conflict')
        : uncertain ? t('gui.queue.save_unconfirmed') : errorMessage(failure));
    } finally {
      if (!controller.signal.aborted) { request.current = null; setPending(false); }
    }
  };
  return <dialog ref={dialog} className="queue-editor" aria-labelledby="queue-editor-title" onCancel={(event) => { event.preventDefault(); if (!pending) onClose(); }}>
    <header className="dialog-heading"><h2 id="queue-editor-title">{item ? t('gui.queue.edit') : t('gui.tasks.add')}</h2>
      <button type="button" className="icon-button" aria-label={t('gui.queue.close_editor')} disabled={pending} onClick={onClose}><X size={18} /></button>
    </header>
    <form onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <div className="queue-editor-body">
        {disabled && <Feedback message={t('gui.queue.readonly')} />}
        <section aria-label={t('gui.queue.parameters')}><div className="queue-editor-grid">
          {parameter({ key: 'task_type', label: t('gui.tasks.method'), required: true, choices: taskTypes })}
          {parameter({ key: 'input_path', label: t('gui.queue.input_path'), type: 'path', required: true })}
          {parameter({ key: 'output_path', label: t('gui.queue.output_path'), type: 'path' })}
          {parameter({ key: 'profile', label: t('gui.tasks.profile'), choices: (profiles.data || []).map((name) => [name, name.replace(/\.json$/, '')]) })}
          {parameter({ key: 'rules_profile', label: t('gui.queue.rules_profile'), choices: (rules.data || []).map((name) => [name, name === 'None' ? t('gui.queue.no_rules') : name.replace(/\.json$/, '')]) })}
          <QueueLanguage kind="source" value={values.source_lang} disabled={blocked} issue={issues.source_lang} onChange={(value) => change('source_lang', value)} />
          <QueueLanguage kind="target" value={values.target_lang} disabled={blocked} issue={issues.target_lang} onChange={(value) => change('target_lang', value)} />
        </div></section>
        {profiles.error && <Feedback message={profiles.error} retry={profiles.retry} />}
        {rules.error && <Feedback message={rules.error} retry={rules.retry} />}
        <details className="queue-editor-section"><summary>{t('gui.queue.advanced')}</summary>
          <div className="queue-editor-grid">
            {parameter({ key: 'execution_mode', label: t('gui.queue.execution_mode'), choices: [['default_api', t('gui.queue.model_api')], ['external_agent', t('gui.queue.external_agent')]] })}
            {parameter({ key: 'project_type', label: t('gui.queue.project_type') })}
            {parameter({ key: 'polish_mode', label: t('gui.queue.polish_mode'), choices: [['translated_text_polish', t('gui.queue.polish_translation')], ['source_text_polish', t('gui.queue.polish_source')]] })}
          </div>
          {values.execution_mode === 'external_agent' && <p className="muted">{t('gui.queue.external_hint')}</p>}
        <details className="queue-editor-section"><summary>{t('gui.queue.model_connection')}</summary><div className="queue-editor-grid">
          {parameter({ key: 'platform', label: t('gui.queue.platform'), choices: (platforms.data || []).map(({ name }) => [name, name]) })}
          {parameter({ key: 'model', label: t('gui.queue.model') })}
          {parameter({ key: 'api_url', label: t('gui.queue.api_url') })}
        </div><p className="muted">{t('gui.queue.credentials_hint')}</p>
          {platforms.error && <Feedback message={platforms.error} retry={platforms.retry} />}
        </details>
        <details className="queue-editor-section"><summary>{t('gui.queue.execution_batch')}</summary><div className="queue-editor-grid">{numericFields.map(parameter)}</div></details>
        <details className="queue-editor-section"><summary>{t('gui.queue.output_recovery')}</summary><div className="queue-editor-grid">{outputFields.map(parameter)}</div>
          {destructive && <label className="parameter-confirm"><input type="checkbox" disabled={blocked} checked={values.output_policy_confirmed === true}
            onChange={(event) => change('output_policy_confirmed', event.target.checked)} />
            {values.output_policy === 'overwrite' ? t('gui.queue.confirm_overwrite') : t('gui.queue.confirm_archive')}
          </label>}{issues.output_policy_confirmed && <span className="field-error">{issues.output_policy_confirmed}</span>}
        </details>
        <details className="queue-editor-section"><summary>{t('gui.queue.runtime_overrides')}</summary>
          <QueueRuntimeOverrides api={api} values={values.runtime_overrides || {}} disabled={blocked}
            onChange={(value) => change('runtime_overrides', value)} onValidity={(key, message) => validity(`runtime.${key}`, message)} />
          {issues.runtime_overrides && <span className="field-error">{issues.runtime_overrides}</span>}
        </details>
        <details className="queue-editor-section"><summary>{t('gui.queue.workflow_steps')}</summary>
          {parameter({ key: 'workflow_steps', label: t('gui.queue.workflow'), type: 'list', description: t('gui.queue.workflow_hint') })}
          {parameter({ key: 'step_overrides', label: t('gui.queue.step_overrides'), type: 'dict', description: t('gui.queue.step_overrides_hint') })}
        </details>
        </details>
        {error && <Feedback message={error} />}
      </div>
      <footer className="dialog-footer">
        <button type="button" className="secondary-button" disabled={pending} onClick={reviewRequired ? onSaved : onClose}>{reviewRequired ? t('gui.queue.refresh_close') : t('gui.common.cancel')}</button>
        <button type="submit" className="primary-button" disabled={blocked || (!!item && changed.size === 0) || Object.values(invalid).some(Boolean)}>
          {pending && <LoaderCircle size={16} className="spin" />}{pending ? t('gui.queue.saving') : item ? t('gui.queue.save_changes') : t('gui.queue.add_to_queue')}
        </button>
      </footer>
    </form>
  </dialog>;
}
