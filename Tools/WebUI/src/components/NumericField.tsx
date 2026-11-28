import { useId, useLayoutEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import { numericIssue, sliderRange, type NumericDescription } from '../appearance/numericPresentation';

export interface NumericFieldProps {
  field: NumericDescription; value: unknown; label: string; id?: string; disabled?: boolean; issue?: string; description?: string;
  onChange: (value: number) => void; onValidityChange?: (message: string) => void;
}

export function NumericField({ field, value, label, id, disabled, issue, description, onChange, onValidityChange }: NumericFieldProps) {
  const generatedId = useId();
  const inputId = id || generatedId;
  const scalar = value === undefined || value === null ? '' : String(value);
  const [text, setText] = useState(scalar);
  const [localIssue, setLocalIssue] = useState('');
  const emitted = useRef<string | undefined>(undefined);
  const validity = useRef(onValidityChange);
  validity.current = onValidityChange;
  const range = sliderRange(field);
  useLayoutEffect(() => {
    if (emitted.current !== scalar) {
      setText(scalar); setLocalIssue(''); validity.current?.('');
    }
    emitted.current = undefined;
  }, [scalar, field.key]);
  const change = (input: string) => {
    setText(input);
    const message = numericIssue(input, field);
    setLocalIssue(message); onValidityChange?.(message);
    if (!message) {
      const number = Number(input.trim());
      emitted.current = String(number);
      onChange(number);
    }
  };
  const parsed = Number(text.trim());
  const valid = text.trim() !== '' && Number.isFinite(parsed) && !localIssue;
  const sliderValue = Math.max(range.min, Math.min(range.max, valid ? parsed : typeof value === 'number' ? value : range.min));
  const message = (localIssue ? numericIssue(text, field) : '') || issue;
  const outside = valid && (parsed < range.min || parsed > range.max);
  const describedBy = [description ? `${inputId}-description` : '', `${inputId}-range`, message ? `${inputId}-error` : ''].filter(Boolean).join(' ');
  return <div className="numeric-field">
    <div className="numeric-controls">
      <input className="numeric-slider" type="range" aria-label={t('gui.numeric.sliderLabel', { label })} disabled={disabled || range.min === range.max}
        min={range.min} max={range.max} step={range.step} value={sliderValue}
        aria-describedby={`${inputId}-range`} onChange={(event) => change(event.target.value)} />
      <input className="numeric-input" id={inputId} type="text" role="spinbutton" inputMode={field.type === 'int' ? 'numeric' : 'decimal'}
        aria-label={label} aria-valuenow={valid ? parsed : undefined} aria-valuemin={field.minimum ?? undefined} aria-valuemax={field.maximum ?? undefined}
        aria-invalid={!!message} aria-describedby={describedBy} autoComplete="off" spellCheck={false} disabled={disabled} value={text}
        onChange={(event) => change(event.target.value)} onKeyDown={(event) => {
          if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
          event.preventDefault();
          const start = valid ? parsed : typeof value === 'number' ? value : range.min;
          const next = Math.max(field.minimum ?? -Infinity, Math.min(field.maximum ?? Infinity,
            Number((start + (event.key === 'ArrowUp' ? range.step : -range.step)).toFixed(8))));
          change(String(next));
        }} />
    </div>
    <span className="numeric-range" id={`${inputId}-range`}>{t('gui.numeric.sliderRange', { min: range.min, max: range.max })}{outside ? ` · ${t('gui.numeric.customValue')}` : ''}</span>
    {message && <span className="field-error" id={`${inputId}-error`}>{message}</span>}
  </div>;
}
