import { t } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { ApiClient, ApiError, errorMessage } from './client';
import type { SuccessResponse, TaskPreview, TaskRequest, TaskStart, TaskStatus } from './contracts';
import { captureCurrentTask, rememberStartedTask } from './sessionTasks';

type Destination = 'run' | 'queue';
interface OutputChoice { request: TaskRequest; destination: Destination; preview: TaskPreview }

export function useTaskSubmission(api: ApiClient) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [issues, setIssues] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<TaskPreview>();
  const [choice, setChoice] = useState<OutputChoice>();
  const [uncertain, setUncertain] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const reset = () => { if (!request.current) { setError(''); setIssues({}); setPreview(undefined); setChoice(undefined); } };

  const submit = async (body: TaskRequest, destination: Destination, policy?: 'resume' | 'archive', approvedPath?: string | null) => {
    if (request.current || uncertain) return;
    reset();
    const controller = new AbortController(); request.current = controller; setBusy(true);
    let dispatched = false;
    try {
      const signal = controller.signal;
      const result = await api.request<TaskPreview>('/task/preview', { method: 'POST', body, signal });
      if (!result.valid) { setPreview(result); return; }
      if (result.output_exists && (!policy || result.resolved_output_path !== approvedPath || (policy === 'resume' && !result.cache_exists))) {
        setChoice({ request: { ...body, ...(result.resolved_output_path ? { output_path: result.resolved_output_path } : {}) }, destination, preview: result });
        return;
      }
      const payload: TaskRequest = {
        ...body,
        ...(result.resolved_output_path ? { output_path: result.resolved_output_path } : {}),
        output_policy: policy || 'cancel',
        ...(policy === 'archive' ? { output_policy_confirmed: true } : {}),
      };
      const before = destination === 'run' ? await captureCurrentTask(api, signal) : undefined;
      dispatched = true;
      const response = await api.request<TaskStart | SuccessResponse>(destination === 'run' ? '/task/run' : '/queue', { method: 'POST', body: payload, signal, timeout: 30000 });
      if (!response.success) throw new ApiError('message' in response && response.message ? response.message : t('gui.submit.failed'), 409);
      if (destination === 'run') {
        if (!('task_id' in response) || !response.task_id) throw new ApiError(t('gui.submit.missingTaskId'));
        rememberStartedTask(api, payload, response, before?.runtime);
        if (response.status === 'failed') throw new ApiError(response.message || t('gui.submit.prepareFailed'), 422);
      }
      window.location.hash = '/tasks';
    } catch (failure) {
      if (controller.signal.aborted) return;
      const ambiguous = dispatched && (!(failure instanceof ApiError) || failure.status === 0 || failure.status >= 500);
      if (ambiguous) {
        setUncertain(true);
        setError(t('gui.submit.uncertain'));
      } else setError(errorMessage(failure));
      if (failure instanceof ApiError) setIssues(Object.fromEntries(failure.issues.map((issue) => [issue.field, issue.message])));
    } finally {
      request.current = null; setBusy(false);
    }
  };

  const refreshOutcome = async () => {
    if (request.current) return;
    const controller = new AbortController(); request.current = controller; setBusy(true);
    try {
      const status = await api.request<TaskStatus>('/task/status', { signal: controller.signal });
      if (status.running) window.location.hash = '/tasks';
      else setError(t('gui.submit.noRunningTask'));
    } catch (failure) { if (!controller.signal.aborted) setError(errorMessage(failure)); }
    finally { request.current = null; setBusy(false); }
  };
  return { busy, error, issues, preview, choice, uncertain, reset, submit,
    chooseOutput: (policy: 'resume' | 'archive') => choice && submit(choice.request, choice.destination, policy, choice.preview.resolved_output_path),
    cancelChoice: () => setChoice(undefined), refreshOutcome,
    allowResubmit: () => { setUncertain(false); reset(); },
  };
}
