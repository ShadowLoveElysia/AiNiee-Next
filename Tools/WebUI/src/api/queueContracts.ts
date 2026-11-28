import type { QueueItem, TaskType } from './contracts';

export interface QueueTaskParameters {
  task_type: TaskType;
  input_path: string;
  execution_mode?: 'default_api' | 'external_agent' | null;
  output_path?: string | null;
  profile?: string | null;
  rules_profile?: string | null;
  source_lang?: string | null;
  target_lang?: string | null;
  project_type?: string | null;
  platform?: string | null;
  api_url?: string | null;
  model?: string | null;
  threads?: number | null;
  retry?: number | null;
  timeout?: number | null;
  rounds?: number | null;
  pre_lines?: number | null;
  lines_limit?: number | null;
  tokens_limit?: number | null;
  think_depth?: string | number | null;
  thinking_budget?: number | null;
  failover?: boolean | null;
  resume?: boolean | null;
  polish_mode?: string | null;
  runtime_overrides?: Record<string, unknown> | null;
  step_overrides?: Record<string, unknown> | null;
  workflow_steps?: Record<string, unknown>[] | null;
  strict_export?: boolean | null;
  output_policy?: 'resume' | 'archive' | 'overwrite' | 'cancel' | null;
  output_policy_confirmed?: boolean;
  export_format?: string | null;
}

export type QueueRecord = QueueItem & QueueTaskParameters;
export type QueueFieldKey = keyof QueueTaskParameters;
// Canonical DTO fields only: lines/tokens are legacy aliases, status is server-owned,
// and api_key is deliberately excluded because the queue rejects credential storage.
export const QUEUE_FIELDS: QueueFieldKey[] = [
  'task_type', 'input_path', 'execution_mode', 'output_path', 'profile', 'rules_profile',
  'source_lang', 'target_lang', 'project_type', 'platform', 'api_url', 'model', 'threads',
  'retry', 'timeout', 'rounds', 'pre_lines', 'lines_limit', 'tokens_limit', 'think_depth',
  'thinking_budget', 'failover', 'resume', 'polish_mode', 'runtime_overrides',
  'step_overrides', 'workflow_steps', 'strict_export', 'output_policy',
  'output_policy_confirmed', 'export_format',
];

export function queueEditorValues(item?: QueueRecord): Partial<QueueTaskParameters> {
  if (!item) return { task_type: 'translate', input_path: '', source_lang: 'auto' };
  return Object.fromEntries(QUEUE_FIELDS.filter((key) => item[key] !== undefined).map((key) => [key, item[key]]));
}

export function queueEditorPayload(values: Partial<QueueTaskParameters>, changed: ReadonlySet<QueueFieldKey>, editing: boolean) {
  return Object.fromEntries(QUEUE_FIELDS.filter((key) => editing ? changed.has(key) : values[key] !== undefined)
    .map((key) => [key, values[key] ?? null]));
}

export interface RuntimeParameter {
  key: string;
  group: string;
  type: string;
  default: unknown;
  minimum: number | null;
  maximum: number | null;
  choices: unknown[];
  label: string;
  description: string;
  steps: string[];
}
