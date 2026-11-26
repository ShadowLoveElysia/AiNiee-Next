type DialogLevel = 'info' | 'warning' | 'error';

const browserAlert =
  typeof window !== 'undefined' ? window.alert.bind(window) : () => undefined;
const browserConfirm =
  typeof window !== 'undefined'
    ? window.confirm.bind(window)
    : () => false;

function normalizeText(value: unknown): string {
  if (value == null) return '';
  return String(value);
}

export async function nativeAlert(
  message: unknown,
  _options?: { title?: string; level?: DialogLevel }
): Promise<void> {
  browserAlert(normalizeText(message));
}

export async function nativeConfirm(
  message: unknown,
  _options?: { title?: string }
): Promise<boolean> {
  return browserConfirm(normalizeText(message));
}
