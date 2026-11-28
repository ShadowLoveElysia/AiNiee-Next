import { useEffect, useState } from 'react';
import { ApiClient, errorMessage } from './client';

export function useResource<T>(api: ApiClient, path: string, active = true) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    void api.request<T>(path, { signal: controller.signal }).then((value) => {
      if (!controller.signal.aborted) { setData(value); setError(''); }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, path, revision, active]);
  return { data, error, loading, retry: () => setRevision((value) => value + 1) };
}
