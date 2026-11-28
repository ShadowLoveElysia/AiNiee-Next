import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiClient, errorMessage } from './client';
import { t } from '../i18n';
import type { QueueItem, RuntimeIdentity, SystemMode, TaskStatus } from './contracts';
import { mergeSnapshot, pollDelay, sameRun, type TaskSnapshot } from './taskSnapshot';
import { rememberTaskSnapshot } from './sessionTasks';

interface TasksState {
  queue?: QueueItem[];
  snapshot?: TaskSnapshot;
  mode?: SystemMode['mode'];
  queueError: string;
  statusError: string;
  modeError: string;
  refreshing: boolean;
}

export function useTasks(api: ApiClient, active = true) {
  const [state, setState] = useState<TasksState>({ queueError: '', statusError: '', modeError: '', refreshing: true });
  const [attempt, setAttempt] = useState(0);
  const snapshotRef = useRef<TaskSnapshot | undefined>(undefined);
  useEffect(() => {
    if (!active) return;
    setState((previous) => ({ ...previous, refreshing: true }));
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;
    let failures = 0;
    let snapshot = snapshotRef.current;
    const signal = controller.signal;
    const poll = async () => {
      if (signal.aborted || inFlight) return;
      clearTimeout(timer); inFlight = true;
      let failed = false;
      let identity: RuntimeIdentity | undefined;
      try {
        const mode = await api.request<SystemMode>('/system/mode', { signal });
        if (signal.aborted) return;
        setState((previous) => ({ ...previous, mode: mode.mode, modeError: '' }));
      } catch (failure) {
        if (signal.aborted) return;
        failed = true;
        setState((previous) => ({ ...previous, modeError: errorMessage(failure) }));
      }
      try {
        identity = await api.request<RuntimeIdentity>('/system/runtime', { signal });
        const changedRuntime = snapshot && (snapshot.runtime.runtime_id !== identity.runtime_id || snapshot.runtime.workspace_id !== identity.workspace_id);
        const cursor = changedRuntime ? 0 : snapshot?.status.cursors.logs || 0;
        let status = await api.request<TaskStatus>(`/task/status?log_cursor=${cursor}`, { signal });
        // A task can switch between polls with a cursor larger than its entire log.
        if (snapshot && !sameRun(snapshot, identity, status) && cursor !== 0) {
          status = await api.request<TaskStatus>('/task/status?log_cursor=0', { signal });
        }
        if (signal.aborted) return;
        snapshot = mergeSnapshot(snapshot, identity, status);
        snapshotRef.current = snapshot;
        rememberTaskSnapshot(api, snapshot);
        setState((previous) => ({ ...previous, snapshot, statusError: '',
          ...(changedRuntime ? { queueError: t('gui.common.runtimeChanged') } : {}),
        }));
      } catch (failure) {
        if (signal.aborted) return;
        failed = true;
        setState((previous) => ({ ...previous, statusError: errorMessage(failure) }));
      }
      try {
        if (!identity) throw new Error(t('gui.common.queueRefreshFailed'));
        const queue = await api.request<QueueItem[]>('/queue', { signal });
        if (!signal.aborted) setState((previous) => ({ ...previous, queue, queueError: '' }));
      } catch (failure) {
        if (signal.aborted) return;
        failed = true;
        setState((previous) => ({ ...previous, queueError: errorMessage(failure) }));
      } finally {
        inFlight = false;
        failures = failed ? failures + 1 : 0;
        if (!signal.aborted) setState((previous) => ({ ...previous, refreshing: false }));
        if (!signal.aborted) timer = setTimeout(() => void poll(), pollDelay(snapshot?.status.running || false, document.hidden, failures));
      }
    };
    const visibility = () => {
      if (inFlight) return;
      clearTimeout(timer);
      timer = setTimeout(() => void poll(), document.hidden ? 15000 : 0);
    };
    document.addEventListener('visibilitychange', visibility);
    void poll();
    return () => { controller.abort(); clearTimeout(timer); document.removeEventListener('visibilitychange', visibility); };
  }, [api, attempt, active]);
  const retry = useCallback(() => {
    setState((previous) => ({ ...previous, refreshing: true }));
    setAttempt((value) => value + 1);
  }, []);
  return { ...state, retry };
}
