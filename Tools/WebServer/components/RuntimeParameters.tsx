import React, { useEffect, useId, useState } from 'react';
import { useI18n } from '../contexts/I18nContext';
import { useGlobal } from '../contexts/GlobalContext';

export type RuntimeValues = Record<string, string | number | boolean>;
export type StepValues = Record<string, { enabled?: boolean; runtime_overrides?: RuntimeValues }>;

interface Parameter {
  key: string; group: string; type: string; label: string; description: string;
  minimum?: number; maximum?: number; choices: string[]; depends_on?: string; default?: string | number | boolean; steps?: string[];
}

export const RuntimeParameters: React.FC<{
  value: RuntimeValues; onChange: (value: RuntimeValues) => void; disabled?: boolean;
  title?: string; hiddenKeys?: string[]; stepType?: string;
}> = ({ value, onChange, disabled = false, title, hiddenKeys = [], stepType }) => {
  const { t } = useI18n();
  const { config } = useGlobal();
  const id = useId();
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const [error, setError] = useState('');
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/task/runtime-parameters', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(t('runtime_load_failed'));
        return response.json();
      }).then(data => setParameters(data.parameters))
      .catch(reason => { if (!controller.signal.aborted) setError(String(reason.message)); });
    return () => controller.abort();
  }, []);
  const set = (key: string, next?: string | number | boolean) => {
    const updated = { ...value };
    if (next === undefined) delete updated[key]; else updated[key] = next;
    if (key === 'platform') delete updated.model;
    onChange(updated);
  };
  const groups = [...new Set(parameters.filter(p => !hiddenKeys.includes(p.key) && (!stepType || p.steps?.includes(stepType))).map(p => p.group))];
  const inputClass = 'w-full min-h-10 rounded border border-slate-600 bg-slate-900 px-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50';
  return <details className="rounded-lg border border-slate-700 p-3">
    <summary className="cursor-pointer text-sm font-semibold text-slate-200 focus-visible:outline focus-visible:outline-2">
      {title || t('runtime_parameters_title')} · {Object.keys(value).length}
    </summary>
    <p className="my-3 text-sm text-slate-300">{t('runtime_parameters_hint')}</p>
    {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    <fieldset disabled={disabled} className="min-w-0 space-y-3">
      {groups.map(group => <details key={group} className="rounded border border-slate-700 p-3">
        <summary className="cursor-pointer text-sm text-slate-200">{t(`runtime_group_${group}`)}</summary>
        <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
          {parameters.filter(p => p.group === group && !hiddenKeys.includes(p.key) && (!stepType || p.steps?.includes(stepType))).map(p => {
            const current = value[p.key];
            const fieldId = `${id}-${p.key}`;
            const inherited = current === undefined;
            const interfaceId = String(value.platform || (stepType === 'polish' ? config?.api_settings?.polish : config?.api_settings?.translate) || config?.target_platform || '');
            const interfaceConfig = config?.platforms?.[interfaceId];
            const modelList = interfaceConfig?.model_datas || [];
            const options = p.key === 'platform' ? Object.keys(config?.platforms || {}) : p.choices;
            const interfaceKeys = ['model', 'temperature', 'top_p', 'think_switch', 'think_depth', 'thinking_budget', 'max_output_tokens', 'structured_output_mode'];
            const effective = current ?? (interfaceKeys.includes(p.key) ? interfaceConfig?.[p.key as keyof typeof interfaceConfig] : (config as any)?.response_check_switch?.[p.key] ?? (config as any)?.[p.key]) ?? p.default;

            return <div key={p.key} className="min-w-0 space-y-1">
              <label htmlFor={fieldId} className="block text-sm text-slate-200">{t(p.label)}</label>
              {p.type === 'bool' ? <select id={fieldId} className={inputClass} value={inherited ? '' : String(current)} onChange={event => set(p.key, event.target.value === '' ? undefined : event.target.value === 'true')}>
                <option value="">{t('runtime_inherit')}</option><option value="true">{t('runtime_on')}</option><option value="false">{t('runtime_off')}</option>
              </select> : options.length > 0 ? <select id={fieldId} className={inputClass} value={String(current ?? '')} onChange={event => set(p.key, event.target.value || undefined)}>
                <option value="">{t('runtime_inherit')}</option>{options.map(option => <option key={option} value={option}>{option}</option>)}
              </select> : <>
                <input id={fieldId} className={inputClass} type={p.type === 'int' || p.type === 'float' ? 'number' : 'text'}
                  value={current === undefined ? '' : String(current)} placeholder={t('runtime_inherit')}
                  aria-invalid={Boolean(invalid[p.key])} aria-describedby={`${fieldId}-error`}
                  onBlur={event => { const input = event.currentTarget; setInvalid(previous => ({ ...previous, [p.key]: input.validationMessage })); }}
                  min={p.minimum ?? undefined} max={p.maximum ?? undefined} step={p.type === 'float' ? 'any' : 1}
                  list={p.key === 'model' ? `${fieldId}-models` : undefined}
                  onChange={event => {
                    const raw = event.target.value;
                    set(p.key, raw === '' ? undefined : p.type === 'int' || p.type === 'float' ? Number(raw) : raw);
                  }} />
                {p.key === 'model' && <datalist id={`${fieldId}-models`}>{(Array.isArray(modelList) ? modelList : []).map((model: string) => <option key={model} value={model} />)}</datalist>}
              </>}
              <p id={`${fieldId}-error`} role={invalid[p.key] ? "alert" : undefined} className="text-xs text-red-300">{invalid[p.key] || ""}</p>
              <p className="text-xs text-slate-400">{t('runtime_effective')}: {effective === undefined || effective === null ? t('runtime_inherit') : typeof effective === 'boolean' ? t(effective ? 'runtime_on' : 'runtime_off') : String(effective)} · {t(inherited ? 'runtime_source_default' : 'runtime_source_override')}</p>
              {p.description && <p className="text-xs text-slate-300">{t(p.description)}</p>}
              {p.depends_on && <p className="text-xs text-slate-400">{t('runtime_depends_on')} {t(parameters.find(item => item.key === p.depends_on)?.label || p.depends_on)}</p>}
            </div>;
          })}
        </div>
      </details>)}
      {value.translation_consistency_enhancement === true && <p role="status" className="text-sm text-amber-200">{t('runtime_sequential_notice')}</p>}
      <button type="button" className="min-h-10 rounded border border-slate-600 px-3 text-sm text-slate-200 focus-visible:ring-2 focus-visible:ring-primary" onClick={() => onChange({})}>{t('runtime_reset')}</button>
    </fieldset>
  </details>;
};

export function RuntimeSteps({ value, onChange, disabled, steps }: {
  value: StepValues; onChange: (value: StepValues) => void; disabled?: boolean; steps: string[];
}) {
  const { t } = useI18n();
  return <div className="space-y-2">{steps.map(step => <div key={step} className="space-y-2">
    <label className="flex items-center gap-2 text-sm text-slate-200">
      {t(`workflow_step_${step}`)}
      <select disabled={disabled} className="min-h-10 rounded border border-slate-600 bg-slate-900 px-2 focus:ring-2 focus:ring-primary"
        value={value[step]?.enabled === undefined ? '' : String(value[step].enabled)}
        onChange={event => {
          const enabled = event.target.value === '' ? undefined : event.target.value === 'true';
          onChange({ ...value, [step]: { ...value[step], enabled } });
        }}>
        <option value="">{t('runtime_inherit')}</option><option value="true">{t('runtime_on')}</option><option value="false">{t('runtime_off')}</option>
      </select>
    </label>
    <RuntimeParameters
    stepType={step}
    title={`${t('runtime_step')} · ${t(`workflow_step_${step}`)}`}
    disabled={disabled} value={value[step]?.runtime_overrides || {}}
    onChange={runtime_overrides => onChange({ ...value, [step]: { ...value[step], runtime_overrides } })} />
  </div>)}</div>;
}
