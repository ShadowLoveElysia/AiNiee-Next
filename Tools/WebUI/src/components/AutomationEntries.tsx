import { useRef } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { SchemaField } from './SchemaField';
import { t } from '../i18n';

type Entry = Record<string, unknown>;
type Field = { key: string; type: 'bool' | 'int' | 'string' | 'path' | 'choice' | 'list'; label: string; choices?: string[] };
const commonFields: Field[] = [
  { key: 'enabled', type: 'bool', label: 'gui.automation.enableRule' },
  { key: 'task_type', type: 'choice', label: 'gui.automation.taskType', choices: ['translate', 'polish', 'all_in_one'] },
  { key: 'output_path', type: 'path', label: 'gui.automation.outputDirectory' },
  { key: 'profile', type: 'string', label: 'gui.automation.profile' },
  { key: 'rules_profile', type: 'string', label: 'gui.automation.rulesProfile' },
];
const scheduleFields: Field[] = [
  { key: 'name', type: 'string', label: 'gui.automation.name' },
  { key: 'trigger_type', type: 'choice', label: 'gui.automation.triggerType', choices: ['scheduled', 'queue_added', 'queue_pending'] },
  { key: 'schedule', type: 'string', label: 'gui.automation.schedule' },
  { key: 'input_path', type: 'path', label: 'gui.automation.inputPath' },
  ...commonFields,
];
const watchFields: Field[] = [
  { key: 'watch_path', type: 'path', label: 'gui.automation.watchPath' },
  ...commonFields,
  { key: 'trigger_mode', type: 'choice', label: 'gui.automation.triggerMode', choices: ['file', 'folder'] },
  { key: 'watch_target_type', type: 'choice', label: 'gui.automation.watchTargetType', choices: ['file', 'folder', 'both'] },
  { key: 'file_patterns', type: 'list', label: 'gui.automation.patterns' },
  { key: 'recursive', type: 'bool', label: 'gui.automation.recursive' },
  { key: 'auto_start', type: 'bool', label: 'gui.automation.autoStart' },
  { key: 'debounce_seconds', type: 'int', label: 'gui.automation.debounce' },
  { key: 'move_to_done', type: 'bool', label: 'gui.automation.moveDone' },
  { key: 'done_path', type: 'path', label: 'gui.automation.donePath' },
  { key: 'settle_existing', type: 'bool', label: 'gui.automation.settleExisting' },
  { key: 'series_incremental', type: 'bool', label: 'gui.automation.seriesIncremental' },
];
const structure = { choices: [], minimum: null, maximum: null };

export function AutomationEntries({ kind, entries, disabled, onChange, onValidityChange }: {
  kind: 'scheduler' | 'watch_mode'; entries: unknown; disabled: boolean;
  onChange: (entries: Entry[]) => void; onValidityChange: (message: string) => void;
}) {
  const items = Array.isArray(entries) ? entries as Entry[] : [];
  const errors = useRef(new Map<string, string>());
  const report = (key: string, message: string) => {
    if (message) errors.current.set(key, message); else errors.current.delete(key);
    onValidityChange([...errors.current.values()][0] || '');
  };
  const fields = kind === 'scheduler' ? scheduleFields : watchFields;
  const update = (index: number, item: Entry) => onChange(items.map((current, position) => position === index ? item : current));
  const add = () => {
    const base = { id: crypto.randomUUID(), enabled: false, task_type: 'translate', output_path: '', profile: 'default', rules_profile: '' };
    const entry = kind === 'scheduler' ? { ...base, name: t('gui.automation.newTask'), trigger_type: 'scheduled', schedule: '09:00', input_path: '' }
      : { ...base, watch_path: '', file_patterns: ['*.txt', '*.epub', '*.srt'], recursive: false, auto_start: false,
        debounce_seconds: 5, move_to_done: false, done_path: '', settle_existing: false, series_incremental: false, trigger_mode: 'file', watch_target_type: 'file' };
    onChange([...items, entry]);
  };
  return <div className="automation-entries">
    {items.length === 0 && <p className="muted">{t('gui.automation.noRules')}</p>}
    {items.map((item, index) => <details className="automation-entry" key={String(item.id || index)}>
      <summary>{String(item.name || item.watch_path || t('gui.automation.ruleNumber', { number: index + 1 }))}</summary>
      {fields.filter((field) => !(kind === 'scheduler' && item.trigger_type !== 'scheduled' && ['schedule', 'input_path', 'task_type'].includes(field.key)))
        .map((field) => <SchemaField key={field.key} field={{ ...structure, ...field, choices: field.choices || [], minimum: field.type === 'int' ? 0 : null }}
          label={t(field.label)} value={item[field.key]} disabled={disabled} onValidityChange={(message) => report(`${item.id}:${field.key}`, message)}
          onChange={(value) => update(index, { ...item, [field.key]: value })} />)}
      <details className="automation-advanced"><summary>{t('gui.automation.advanced')}</summary>
        <SchemaField field={{ ...structure, key: 'workflow_steps', type: 'list' }} label={t('gui.automation.workflowSteps')} value={item.workflow_steps || []}
          disabled={disabled} onValidityChange={(message) => report(`${item.id}:workflow`, message)} onChange={(value) => update(index, { ...item, workflow_steps: value })} />
        <SchemaField field={{ ...structure, key: 'full_rule', type: 'dict' }} label={t('gui.automation.fullRule')} value={item}
          disabled={disabled} onValidityChange={(message) => report(`${item.id}:full`, message)} onChange={(value) => update(index, value as Entry)} />
      </details>
      <button type="button" className="text-button danger-button" disabled={disabled} onClick={() => {
        onChange(items.filter((_, position) => position !== index));
        for (const key of errors.current.keys()) if (key.startsWith(`${item.id}:`)) errors.current.delete(key);
        onValidityChange([...errors.current.values()][0] || '');
      }}><Trash2 size={15} />{t('gui.automation.removeRule')}</button>
    </details>)}
    <button type="button" className="text-button" disabled={disabled} onClick={add}><Plus size={15} />{kind === 'scheduler' ? t('gui.automation.addTask') : t('gui.automation.addWatch')}</button>
  </div>;
}
