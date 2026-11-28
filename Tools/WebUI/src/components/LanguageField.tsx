import { t } from '../i18n';

const languages = [['Japanese', 'japanese'], ['English', 'english'], ['Chinese', 'chineseSimplified'], ['Traditional Chinese', 'chineseTraditional'], ['Korean', 'korean'], ['French', 'french'], ['German', 'german'], ['Spanish', 'spanish'], ['Russian', 'russian']] as const;
export const CUSTOM_LANGUAGE = '__custom__';
export const isKnownLanguage = (value: string): boolean => languages.some(([language]) => language === value);

export function LanguageField({ kind, value, custom, onChange, onCustom, issue, idPrefix = '', disabled = false }: {
  kind: 'source' | 'target'; value: string; custom: string;
  onChange: (value: string) => void; onCustom: (value: string) => void; issue?: string;
  idPrefix?: string; disabled?: boolean;
}) {
  const label = t(kind === 'source' ? 'gui.language.source' : 'gui.language.target');
  const id = `${idPrefix}${kind}`;
  return <div className="field">
    <label htmlFor={id}>{label}</label>
    <select id={id} value={value} disabled={disabled} aria-invalid={!!issue} onChange={(event) => onChange(event.target.value)}>
      {kind === 'source' ? <option value="auto">{t('gui.language.detect')}</option> : <option value="">{t('gui.common.inherit')}</option>}
      {languages.map(([language, name]) => <option key={language} value={language}>{t(`gui.language.${name}`)}</option>)}
      <option value={CUSTOM_LANGUAGE}>{t('gui.language.custom')}</option>
    </select>
    {value === CUSTOM_LANGUAGE && <input className="custom-language" aria-label={t(kind === 'source' ? 'gui.language.customSource' : 'gui.language.customTarget')} value={custom} disabled={disabled}
      placeholder={t('gui.language.enterName')} maxLength={100} aria-invalid={!!issue} onChange={(event) => onCustom(event.target.value)} />}
    {issue && <span className="field-error">{issue}</span>}
  </div>;
}
