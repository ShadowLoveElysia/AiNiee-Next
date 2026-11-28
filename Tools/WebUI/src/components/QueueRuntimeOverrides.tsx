import { useState } from 'react';
import { t } from '../i18n';
import { Plus, X } from 'lucide-react';
import { ApiClient } from '../api/client';
import type { RuntimeParameter } from '../api/queueContracts';
import type { SettingDescription } from '../api/settingsContracts';
import { useResource } from '../api/useResource';
import { translateSetting } from '../appearance/settingLabels';
import { Feedback, Loading } from './Feedback';
import { SchemaField } from './SchemaField';

export function QueueRuntimeOverrides({ api, values, disabled, onChange, onValidity }: {
  api: ApiClient; values: Record<string, unknown>; disabled: boolean;
  onChange: (values: Record<string, unknown>) => void; onValidity: (key: string, message: string) => void;
}) {
  const schema = useResource<{ parameters: RuntimeParameter[] }>(api, '/task/runtime-parameters');
  const [selected, setSelected] = useState('');
  const parameters = schema.data?.parameters || [];
  const available = parameters.filter(({ key }) => !(key in values));
  const label = (parameter: RuntimeParameter) => translateSetting(parameter.label, parameter.key);
  const remove = (key: string) => {
    const next = { ...values }; delete next[key]; onValidity(key, ''); onChange(next);
  };
  return <div className="runtime-overrides-editor">
    {schema.loading && !schema.data && <Loading />}
    {schema.error && <Feedback message={schema.error} retry={schema.retry} />}
    {parameters.length > 0 && <div className="runtime-add-row">
      <select aria-label={t('gui.queue.choose_runtime')} value={selected} disabled={disabled} onChange={(event) => setSelected(event.target.value)}>
        <option value="">{t('gui.queue.choose_override')}</option>
        {available.map((parameter) => <option key={parameter.key} value={parameter.key}>{label(parameter)}</option>)}
      </select>
      <button type="button" className="text-button" disabled={disabled || !selected} onClick={() => {
        const parameter = parameters.find(({ key }) => key === selected);
        if (!parameter) return;
        onChange({ ...values, [selected]: parameter.default ?? (parameter.type === 'bool' ? false : parameter.type === 'object' || parameter.type === 'dict' ? {} : '') });
        setSelected('');
      }}><Plus size={15} />{t('gui.queue.add_parameter')}</button>
    </div>}
    <div className="queue-editor-grid">{Object.entries(values).map(([key, value]) => {
      const parameter = parameters.find((item) => item.key === key);
      const type = parameter?.type === 'object' ? 'dict' : parameter?.type || (typeof value === 'boolean' ? 'bool' : typeof value === 'number' ? 'float' : typeof value === 'object' ? 'dict' : 'string');
      return <div key={key} className="runtime-parameter">
        <SchemaField field={{ key: `queue-runtime-${key}`, type: type as SettingDescription['type'], choices: parameter?.choices || [], minimum: parameter?.minimum ?? null, maximum: parameter?.maximum ?? null }}
          value={value} label={parameter ? label(parameter) : key} disabled={disabled || !parameter}
          onChange={(next) => onChange({ ...values, [key]: next })} onValidityChange={(message) => onValidity(key, message)} />
        <button type="button" className="icon-button" aria-label={t('gui.queue.remove_override', { name: parameter ? label(parameter) : key })} disabled={disabled} onClick={() => remove(key)}><X size={15} /></button>
      </div>;
    })}</div>
  </div>;
}
