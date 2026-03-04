import { invoke, isTauri } from '@tauri-apps/api/core';

type DialogLevel = 'info' | 'warning' | 'error';

const browserAlert =
  typeof window !== 'undefined' ? window.alert.bind(window) : () => undefined;
const browserConfirm =
  typeof window !== 'undefined'
    ? window.confirm.bind(window)
    : () => false;

let installed = false;

const DEFAULT_TITLE = 'AiNiee';

function normalizeText(value: unknown): string {
  if (value == null) return '';
  return String(value);
}

async function callNative<T>(
  command: string,
  args: Record<string, unknown>
): Promise<T | null> {
  if (!isTauri()) return null;

  try {
    return await invoke<T>(command, args);
  } catch {
    return null;
  }
}

export async function nativeAlert(
  message: unknown,
  options?: { title?: string; level?: DialogLevel }
): Promise<void> {
  const text = normalizeText(message);
  const title = options?.title || DEFAULT_TITLE;
  const level = options?.level || 'info';

  const ok = await callNative<boolean>('show_native_alert', {
    message: text,
    title,
    level,
  });

  if (ok !== true) {
    browserAlert(text);
  }
}

export async function nativeConfirm(
  message: unknown,
  options?: { title?: string }
): Promise<boolean> {
  const text = normalizeText(message);
  const title = options?.title || DEFAULT_TITLE;

  const result = await callNative<boolean>('show_native_confirm', {
    message: text,
    title,
  });

  if (typeof result === 'boolean') {
    return result;
  }

  return browserConfirm(text);
}

export function installDialogHooks(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  window.alert = (message?: unknown) => {
    void nativeAlert(message).catch(() => {
      browserAlert(normalizeText(message));
    });
  };
}
