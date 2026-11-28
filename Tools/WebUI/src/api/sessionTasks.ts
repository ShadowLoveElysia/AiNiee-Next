import { useSyncExternalStore } from 'react';
import { ApiClient } from './client';
import type { RuntimeIdentity, TaskRequest, TaskStart, TaskStatus } from './contracts';
import { mergeSnapshot, type TaskSnapshot } from './taskSnapshot';

export interface ObservedTask {
  key: string;
  taskId: string;
  runtime?: RuntimeIdentity;
  request?: TaskRequest;
  status: string;
  running: boolean;
  current: boolean;
  queueRun: boolean;
  snapshot?: TaskSnapshot;
}

interface SessionTasks {
  tasks: readonly ObservedTask[];
  listeners: Set<() => void>;
  nextKey: number;
}
const sessions = new WeakMap<ApiClient, SessionTasks>();

function session(api: ApiClient): SessionTasks {
  let value = sessions.get(api);
  if (!value) {
    value = { tasks: [], listeners: new Set(), nextKey: 0 };
    sessions.set(api, value);
  }
  return value;
}

function publish(store: SessionTasks, tasks: readonly ObservedTask[]) {
  store.tasks = tasks;
  store.listeners.forEach((listener) => listener());
}

function matches(task: ObservedTask, taskId: string, runtime?: RuntimeIdentity) {
  return task.taskId === taskId && (!runtime || !task.runtime
    || (task.runtime.runtime_id === runtime.runtime_id && task.runtime.workspace_id === runtime.workspace_id));
}

export function rememberStartedTask(api: ApiClient, request: TaskRequest, response: TaskStart, runtime?: RuntimeIdentity): void {
  rememberStart(api, response, request, runtime, false);
}

export function rememberQueueRun(api: ApiClient, response: TaskStart): void {
  rememberStart(api, response, undefined, undefined, true);
}

function rememberStart(api: ApiClient, response: TaskStart, request: TaskRequest | undefined, runtime: RuntimeIdentity | undefined, queueRun: boolean) {
  if (!response.task_id) return;
  const store = session(api);
  const previous = store.tasks.find((task) => matches(task, response.task_id!, runtime));
  const record: ObservedTask = {
    key: previous?.key || `observed-${++store.nextKey}`, taskId: response.task_id,
    runtime: runtime || previous?.runtime, request: request ? { ...request } : previous?.request,
    status: response.status, running: response.running, current: true, queueRun,
    snapshot: previous?.snapshot,
  };
  publish(store, [...store.tasks.filter((task) => task !== previous).map((task) => ({ ...task, current: false })), record]);
}

export function rememberTaskSnapshot(api: ApiClient, snapshot: TaskSnapshot): void {
  const store = session(api);
  const taskId = snapshot.status.task_id;
  if (!taskId) {
    if (store.tasks.some((task) => task.current)) publish(store, store.tasks.map((task) => ({ ...task, current: false })));
    return;
  }
  const previous = store.tasks.find((task) => matches(task, taskId, snapshot.runtime));
  const record: ObservedTask = {
    key: previous?.key || `observed-${++store.nextKey}`, taskId,
    runtime: snapshot.runtime, request: previous?.request,
    status: snapshot.status.status, running: snapshot.status.running,
    current: true, queueRun: snapshot.status.task_type === 'queue' || previous?.queueRun || false,
    snapshot: mergeSnapshot(previous?.snapshot, snapshot.runtime, snapshot.status),
  };
  const tasks = store.tasks.map((task) => task === previous ? record : task.current ? { ...task, current: false } : task);
  if (!previous) tasks.push(record);
  publish(store, tasks);
}

export function sessionTaskSnapshot(api: ApiClient): readonly ObservedTask[] {
  return session(api).tasks;
}

export async function captureCurrentTask(api: ApiClient, signal?: AbortSignal): Promise<TaskSnapshot> {
  const runtime = await api.request<RuntimeIdentity>('/system/runtime', { signal });
  const status = await api.request<TaskStatus>('/task/status?log_cursor=0', { signal });
  const snapshot = { runtime, status };
  rememberTaskSnapshot(api, snapshot);
  return snapshot;
}

export function useSessionTasks(api: ApiClient): readonly ObservedTask[] {
  return useSyncExternalStore((listener) => {
    const store = session(api);
    store.listeners.add(listener);
    return () => store.listeners.delete(listener);
  }, () => sessionTaskSnapshot(api));
}
