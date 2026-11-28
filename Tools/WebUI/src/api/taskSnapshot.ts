import type { RuntimeIdentity, TaskStatus } from './contracts';

export interface TaskSnapshot { runtime: RuntimeIdentity; status: TaskStatus }
export const LOG_LIMIT = 500;

export function sameRun(previous: TaskSnapshot | undefined, runtime: RuntimeIdentity, status: TaskStatus): boolean {
  return !!previous && previous.runtime.runtime_id === runtime.runtime_id
    && previous.runtime.workspace_id === runtime.workspace_id && previous.status.task_id === status.task_id;
}

export function mergeSnapshot(previous: TaskSnapshot | undefined, runtime: RuntimeIdentity, status: TaskStatus): TaskSnapshot {
  const reset = !sameRun(previous, runtime, status) || status.cursors_reset.logs;
  const logs = new Map((reset ? [] : previous!.status.logs).map((log) => [log.seq, log]));
  status.logs.forEach((log) => logs.set(log.seq, log));
  return { runtime, status: { ...status, logs: [...logs.values()].sort((a, b) => a.seq - b.seq).slice(-LOG_LIMIT) } };
}

export function pollDelay(running: boolean, hidden: boolean, failures: number): number {
  const normal = hidden ? 15000 : running ? 1000 : 5000;
  return Math.min(60000, normal * 2 ** Math.min(failures, 6));
}
