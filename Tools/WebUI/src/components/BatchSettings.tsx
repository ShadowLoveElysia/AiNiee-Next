import type { SettingDescription, SettingValues } from '../api/settingsContracts';
import { SchemaField } from './SchemaField';
import { t } from '../i18n';

export function BatchSettings({ fields, values, disabled, issues, invalid = {}, onChange, onValidityChange }: {
  fields: SettingDescription[]; values: SettingValues; disabled: boolean; issues: Record<string, string>;
  invalid?: Record<string, string>;
  onChange: (field: SettingDescription, value: unknown) => void;
  onValidityChange: (key: string, message: string) => void;
}) {
  const mode = fields.find((field) => field.key === 'tokens_limit_switch');
  const lines = fields.find((field) => field.key === 'lines_limit');
  const tokens = fields.find((field) => field.key === 'tokens_limit');
  if (!mode || !lines || !tokens) return null;
  const selected = values.tokens_limit_switch === true ? tokens : lines;
  return <div className="batch-settings" role="group" aria-label={t('gui.batch.size')}>
    <div className="batch-mode-row"><label htmlFor="batch-mode">{t('gui.batch.size')}</label>
      <select id="batch-mode" value={selected.key} disabled={disabled} onChange={(event) => onChange(mode, event.target.value === 'tokens_limit')}>
        <option value="lines_limit">{t('gui.batch.byLines')}</option><option value="tokens_limit">{t('gui.batch.byTokens')}</option>
      </select>
    </div>
    {[lines, tokens].map((field) => <div key={field.key} hidden={field.key !== selected.key}>
      <SchemaField field={field} value={values[field.key] ?? field.default} label={field.key === 'lines_limit' ? t('gui.batch.lines') : t('gui.batch.tokens')}
        disabled={disabled} issue={issues[field.key]} onChange={(value) => onChange(field, value)}
        onValidityChange={(message) => onValidityChange(field.key, message)} />
    </div>)}
    {issues.tokens_limit_switch && <span className="field-error">{issues.tokens_limit_switch}</span>}
    {[lines, tokens].filter((field) => field.key !== selected.key && (issues[field.key] || invalid[field.key])).map((field) =>
      <span className="field-error" key={field.key}>{t('gui.batch.fixOtherMode', { mode: field.key === 'lines_limit' ? t('gui.batch.byLines') : t('gui.batch.byTokens') })}</span>)}
  </div>;
}
