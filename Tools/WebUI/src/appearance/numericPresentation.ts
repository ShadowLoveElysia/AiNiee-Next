import { t } from '../i18n';

export interface NumericDescription {
  key: string;
  type: string;
  minimum: number | null;
  maximum: number | null;
  default?: unknown;
}

const commonRanges: Record<string, readonly [number, number]> = {
  user_thread_counts: [0, 32], threads: [0, 32], external_agent_max_batches: [1, 32],
  lines_limit: [1, 100], tokens_limit: [400, 8192], thinking_budget: [-1, 32768],
  custom_rpm_limit: [0, 1000], custom_tpm_limit: [0, 1000000],
  request_timeout: [10, 300], timeout: [10, 300], cache_save_interval: [1, 300],
  media_cache_ram_mib: [0, 4096], proofread_archive_limit: [0, 100],
  webserver_port: [1024, 10000], mcp_server_port: [1024, 10000], skills_server_port: [1024, 10000],
};

export function sliderRange(field: NumericDescription) {
  const key = field.key.replace(/^queue-runtime-/, '').replace(/^queue-/, '');
  const defaults = typeof field.default === 'number' && Number.isFinite(field.default) ? field.default : 0;
  const suggested = commonRanges[key];
  const minimum = field.minimum ?? 0;
  const naturalMaximum = field.type === 'float' ? Math.max(1, minimum + 1, defaults * 2) : Math.max(100, minimum + 100, defaults * 2);
  let min = Math.max(field.minimum ?? -Infinity, suggested?.[0] ?? minimum);
  let max = Math.min(field.maximum ?? Infinity, suggested?.[1] ?? field.maximum ?? naturalMaximum);
  if (max < min) {
    min = field.minimum ?? Math.min(min, field.maximum ?? min);
    max = field.maximum ?? Math.max(min, naturalMaximum);
  }
  if (field.type === 'int') { min = Math.ceil(min); max = Math.floor(max); }
  const step = field.type === 'int' ? 1 : max - min <= 1 ? .01 : max - min <= 10 ? .1 : 1;
  return { min, max, step };
}

export function numericIssue(input: string, field: NumericDescription): string {
  const text = input.trim();
  const syntax = field.type === 'int' ? /^[+-]?\d+$/ : /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[+-]?\d+)?$/i;
  if (!syntax.test(text) || !Number.isFinite(Number(text))) return t(field.type === 'int' ? 'gui.numeric.integerRequired' : 'gui.numeric.numberRequired');
  const value = Number(text);
  if (field.type === 'int' && !Number.isSafeInteger(value)) return t('gui.numeric.integerTooLarge');
  if (field.minimum !== null && value < field.minimum) return t('gui.numeric.minimum', { minimum: field.minimum });
  if (field.maximum !== null && value > field.maximum) return t('gui.numeric.maximum', { maximum: field.maximum });
  return '';
}
