import { t } from '../i18n';
import type { RequestTransport } from '../platform/adapter';

export interface FieldIssue { field: string; message: string }
export class ApiError extends Error {
  constructor(message: string, public status = 0, public issues: FieldIssue[] = []) {
    super(message);
    this.name = 'ApiError';
  }
}

async function responseError(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
  if (Array.isArray(detail)) {
    const issues = detail.map((item: { loc?: unknown[]; msg?: string }) => ({
      field: String(item.loc?.[1] || ''), message: item.msg === 'Invalid value' ? t('gui.errors.invalidField') : String(item.msg || t('gui.errors.invalidParameter')),
    }));
    return new ApiError(t('gui.errors.checkSettings'), response.status, issues);
  }
  const fallback = response.status === 413 ? t('gui.errors.fileTooLarge') : t('gui.errors.requestFailed', { status: response.status });
  return new ApiError(typeof detail === 'string' ? detail : fallback, response.status);
}

export class ApiClient {
  private ready = false;
  private generation = 0;
  private session: { promise: Promise<void>; controller: AbortController; users: number } | null = null;

  constructor(private transport: RequestTransport) {}

  private async send(url: string, init: RequestInit, timeout: number): Promise<Response> {
    const controller = new AbortController();
    const cancel = () => controller.abort(init.signal?.reason);
    if (init.signal?.aborted) cancel();
    else init.signal?.addEventListener('abort', cancel, { once: true });
    const timer = setTimeout(() => controller.abort(new DOMException(t('gui.errors.timeout'), 'TimeoutError')), timeout);
    try {
      const response = await this.transport(url, { ...init, credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      const body = response.status === 204 ? null : await response.arrayBuffer();
      controller.signal.throwIfAborted();
      return new Response(body, { status: response.status, headers: response.headers });
    } catch (error) {
      if (controller.signal.aborted) throw controller.signal.reason;
      throw new ApiError(error instanceof ApiError ? error.message : t('gui.errors.unavailable'));
    } finally {
      clearTimeout(timer);
      init.signal?.removeEventListener('abort', cancel);
    }
  }

  private async bootstrap(signal?: AbortSignal): Promise<void> {
    signal?.throwIfAborted();
    if (this.ready) return;
    if (!this.session || this.session.controller.signal.aborted) {
      const controller = new AbortController();
      const session = { controller, users: 0, promise: Promise.resolve() };
      session.promise = this.send('/api/session/bootstrap', { method: 'POST', signal: controller.signal }, 15000)
        .then(async (response) => {
          if (!response.ok) throw await responseError(response);
          controller.signal.throwIfAborted();
          this.ready = true;
          this.generation++;
        }).finally(() => { if (this.session === session) this.session = null; });
      this.session = session;
    }
    const session = this.session;
    session.users++;
    let abort: (() => void) | undefined;
    try {
      await Promise.race([
        session.promise,
        new Promise<never>((_, reject) => {
          abort = () => reject(signal?.reason);
          signal?.addEventListener('abort', abort, { once: true });
        }),
      ]);
    } finally {
      if (abort) signal?.removeEventListener('abort', abort);
      session.users--;
      if (session.users === 0 && this.session === session) session.controller.abort();
    }
  }

  async request<T>(path: string, options: { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown; signal?: AbortSignal; timeout?: number } = {}): Promise<T> {
    const { method = 'GET', body, signal, timeout = 15000 } = options;
    await this.bootstrap(signal);
    const generation = this.generation;
    const form = body instanceof FormData;
    const init: RequestInit = {
      method, signal,
      ...(body !== undefined ? { body: form ? body : JSON.stringify(body), headers: form ? undefined : { 'Content-Type': 'application/json' } } : {}),
    };
    let response = await this.send(`/api${path}`, init, timeout);
    if (response.status === 403 && response.headers.get('X-AiNiee-Auth-Required') === 'web-session') {
      if (generation === this.generation) this.ready = false;
      await this.bootstrap(signal);
      if (method !== 'GET') throw new ApiError(t('gui.errors.sessionRestored'), 403);
      response = await this.send(`/api${path}`, init, timeout);
    }
    if (!response.ok) throw await responseError(response);
    try { return await response.json() as T; }
    catch { throw new ApiError(t('gui.errors.invalidResponse')); }
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : t('gui.errors.operationFailed');
}
