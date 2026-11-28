import type { QueueItem } from './contracts';
import type { ObservedTask } from './sessionTasks';
import type { TaskSnapshot } from './taskSnapshot';

export interface TaskRow {
  key: string;
  taskId: string;
  name: string;
  inputPath?: string;
  outputPath?: string | null;
  profile?: string | null;
  sourceLanguage?: string | null;
  targetLanguage?: string | null;
  taskType?: string;
  status: string;
  snapshot?: TaskSnapshot;
  queueItem?: QueueItem;
  queueIndex?: number;
  stale: boolean;
}

const terminal = new Set(['completed', 'failed', 'error', 'stopped', 'cancelled', 'interrupted', 'partial', 'polished']);
export const isTerminalStatus = (status: string) => terminal.has(status);

function observedRow(task: ObservedTask): TaskRow {
  const request = task.request;
  const currentFile = task.snapshot?.status.stats.currentFile;
  const input = request?.input_path || (currentFile && currentFile !== 'N/A' ? currentFile : undefined);
  return {
    key: task.key, taskId: task.taskId, name: input || task.taskId,
    inputPath: input, outputPath: request?.output_path, profile: request?.profile,
    sourceLanguage: request?.source_lang, targetLanguage: request?.target_lang,
    taskType: request?.task_type || task.snapshot?.status.task_type || (task.queueRun ? 'queue' : undefined),
    status: task.status, snapshot: task.snapshot, stale: !task.current && !isTerminalStatus(task.status),
  };
}

export function buildTaskRows(queue: QueueItem[] | undefined, observed: readonly ObservedTask[], snapshot?: TaskSnapshot): { active: TaskRow[]; history: TaskRow[] } {
  const active: TaskRow[] = [];
  const history: TaskRow[] = [];
  const used = new Set<string>();
  for (const [index, item] of (queue || []).entries()) {
    const record = observed.find((task) => task.taskId === item.task_id && (!task.runtime || !snapshot
      || (task.runtime.runtime_id === snapshot.runtime.runtime_id && task.runtime.workspace_id === snapshot.runtime.workspace_id)));
    if (record) used.add(record.key);
    const row: TaskRow = {
      key: `queue:${item.task_id}`, taskId: item.task_id, name: item.input_path,
      inputPath: item.input_path, outputPath: item.output_path, profile: item.profile,
      sourceLanguage: item.source_lang, targetLanguage: item.target_lang, taskType: item.task_type,
      status: record?.current ? record.status : item.status,
      snapshot: record?.snapshot, queueItem: item, queueIndex: index, stale: false,
    };
    (isTerminalStatus(row.status) ? history : active).push(row);
  }
  for (const task of observed) {
    if (used.has(task.key)) continue;
    const row = observedRow(task);
    // Queue worker status represents the whole run; its live stop control remains in the header.
    if (task.queueRun && !isTerminalStatus(task.status) && queue?.length) continue;
    (isTerminalStatus(task.status) || !task.current ? history : active).push(row);
  }
  return { active, history: history.reverse() };
}
