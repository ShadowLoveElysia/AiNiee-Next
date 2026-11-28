import { useEffect, useId, useRef, useState } from 'react';
import type { SettingDescription } from '../api/settingsContracts';
import { settingChoiceLabel } from '../appearance/settingLabels';
import { t } from '../i18n';
import { NumericField } from './NumericField';
import { PathField } from './PathField';
import { useApiClient } from '../api/ApiContext';

type Field = Pick<SettingDescription, 'key' | 'type' | 'choices' | 'minimum' | 'maximum'> & Partial<Pick<SettingDescription, 'default'>>;
interface Props {
  field: Field; value: unknown; label: string; description?: string; disabled?: boolean; issue?: string;
  onChange: (value: unknown) => void; onValidityChange?: (message: string) => void;
}

function JsonValue({ field, value, disabled, id, label, onChange, onValidityChange }: Props & { id: string }) {
  const serialized = JSON.stringify(value ?? (field.type === 'list' ? [] : {}), null, 2);
  const [text, setText] = useState(serialized);
  const [issue, setIssue] = useState('');
  const emitted = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (emitted.current !== serialized) { setText(serialized); setIssue(''); }
    emitted.current = undefined;
  }, [serialized]);
  const change = (input: string) => {
    setText(input);
    try {
      const parsed: unknown = JSON.parse(input);
      if (field.type === 'list' ? !Array.isArray(parsed) : !parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(field.type === 'list' ? 'gui.controls.jsonArrayRequired' : 'gui.controls.jsonObjectRequired');
      }
      emitted.current = JSON.stringify(parsed, null, 2);
      setIssue(''); onValidityChange?.(''); onChange(parsed);
    } catch (error) {
      const key = error instanceof SyntaxError ? 'gui.controls.jsonInvalid' : error instanceof Error ? error.message : 'gui.controls.jsonRequired';
      setIssue(key); onValidityChange?.(t(key));
    }
  };
  return <><textarea id={id} aria-label={label} rows={5} value={text} disabled={disabled} spellCheck={false}
    aria-invalid={!!issue} className="schema-json" onChange={(event) => change(event.target.value)} />
    {issue && <span className="field-error">{t(issue)}</span>}</>;
}

export function SchemaField(props: Props) {
  const api = useApiClient();
  const { field, value, label, description, disabled, issue, onChange, onValidityChange } = props;
  const id = useId();
  const scalar = value === undefined || value === null ? '' : String(value);
  const numeric = field.type === 'int' || field.type === 'float';
  const choices = field.type === 'choice' && field.choices.length > 0;
  return <div className={`schema-field ${field.type === 'bool' ? 'schema-field-toggle' : ''}`} data-setting-key={field.key}>
    <div className="schema-field-label"><label htmlFor={id}>{label}</label>
      {description && <p id={`${id}-description`}>{description}</p>}
    </div>
    <div className="schema-field-control">
      {field.type === 'bool' ? <input id={id} type="checkbox" role="switch" checked={value === true} disabled={disabled}
        aria-describedby={description ? `${id}-description` : undefined} onChange={(event) => onChange(event.target.checked)} />
        : field.type === 'dict' || field.type === 'list' ? <JsonValue {...props} id={id} />
        : choices ? <select id={id} value={JSON.stringify(value)} disabled={disabled} aria-invalid={!!issue}
          onChange={(event) => onChange(JSON.parse(event.target.value) as unknown)}>
          {!field.choices.some((choice) => JSON.stringify(choice) === JSON.stringify(value)) && <option value={JSON.stringify(value)}>{scalar || t('gui.controls.notSet')}</option>}
          {field.choices.map((choice, index) => <option key={index} value={JSON.stringify(choice)}>{settingChoiceLabel(field.key, choice)}</option>)}
        </select>
        : numeric ? <NumericField field={field} id={id} value={value} label={label} description={description} disabled={disabled}
          issue={issue} onChange={onChange} onValidityChange={onValidityChange} />
        : field.type === 'path' ? <PathField api={api} id={id} value={scalar} label={label} disabled={disabled} issue={issue}
          mode={field.key.endsWith('input_path') ? 'any' : 'directory'} onChange={onChange} />
        : <input id={id} value={scalar} disabled={disabled} type="text" aria-invalid={!!issue}
          onChange={(event) => onChange(event.target.value)} />}
      {issue && !numeric && <span className="field-error">{issue}</span>}
    </div>
  </div>;
}
