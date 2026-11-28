import { useEffect, useRef, useState } from 'react';
import { t } from '../i18n';
import { ApiClient, ApiError, errorMessage } from './client';
import type { QueueItem, SuccessResponse, TaskStart } from './contracts';
import { rememberQueueRun } from './sessionTasks';

type Action = 'run' | 'stop' | 'remove' | 'move';
// A lost start response must remain visible even after navigating away and back.
const uncertainStarts = new WeakSet<ApiClient>();

export function useQueueActions(api: ApiClient, refresh: () => void) {
  const request = useRef<AbortController | null>(null);
  const [pending, setPending] = useState<Action | null>(null);
  const [error, setError] = useState('');
  const [uncertainStart, setUncertainStart] = useState(() => uncertainStarts.has(api));
  useEffect(() => () => request.current?.abort(), []);

  const perform = async (action: Action, path: string, method: 'POST' | 'PUT' | 'DELETE', body?: unknown) => {
    if (request.current || (action === 'run' && uncertainStarts.has(api))) return false;
    const controller = new AbortController();
    request.current = controller; setPending(action); setError('');
    if (action === 'run') uncertainStarts.add(api);
    try {
      const result = await api.request<SuccessResponse | TaskStart>(path, { method, body, signal: controller.signal });
      if (!result.success) throw new ApiError(('message' in result && result.message) || t('gui.queueActions.failed'), 422);
      if (action === 'run') {
        if (!('task_id' in result) || !result.task_id) throw new ApiError(t('gui.queueActions.missing_id'));
        rememberQueueRun(api, result);
        if (result.status === 'failed') throw new ApiError(result.message || t('gui.queueActions.prepare_failed'), 422);
      }
      if (action === 'run') uncertainStarts.delete(api);
      if (!controller.signal.aborted) setUncertainStart(uncertainStarts.has(api));
      return true;
    } catch (failure) {
      if (action === 'run' && failure instanceof ApiError && failure.status > 0 && failure.status < 500) uncertainStarts.delete(api);
      if (!controller.signal.aborted) {
        const uncertain = uncertainStarts.has(api);
        setUncertainStart(uncertain);
        setError(uncertain ? t('gui.queueActions.start_unconfirmed')
          : errorMessage(failure));
      }
      return false;
    } finally {
      if (!controller.signal.aborted) {
        request.current = null; setPending(null); refresh();
      }
    }
  };

  const path = (item: QueueItem, suffix = '') => `/queue/${encodeURIComponent(item.task_id)}${suffix}?expected_revision=${encodeURIComponent(item.revision)}`;
  return {
    pending, error, uncertainStart,
    run: () => perform('run', '/queue/run', 'POST'),
    stop: (taskId: string) => perform('stop', '/task/stop', 'POST', { task_id: taskId }),
    remove: (item: QueueItem) => perform('remove', path(item), 'DELETE'),
    move: (item: QueueItem, toIndex: number) => perform('move', path(item, '/move'), 'PUT', { to_index: toIndex }),
    acknowledgeStart: () => { uncertainStarts.delete(api); setUncertainStart(false); setError(''); },
  };
}
