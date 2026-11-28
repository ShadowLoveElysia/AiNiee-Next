import { browserPlatform, type PreferenceStorage } from '../platform/adapter';
import { DEFAULT_LOCALE, isLocale, type Locale } from '../i18n';

export type Theme = 'system' | 'light' | 'dark';
export type SidebarMode = 'auto' | 'fixed';
export interface Preferences { theme: Theme; sidebar: SidebarMode; uiAnimations: boolean; language: Locale }
export const PREFERENCES_KEY = 'ainiee.webui.appearance.v1';
const defaults: Preferences = { theme: 'system', sidebar: 'auto', uiAnimations: true, language: DEFAULT_LOCALE };

export function readPreferences(storage: PreferenceStorage = browserPlatform.preferences): Preferences {
  try {
    const data: unknown = JSON.parse(storage.getItem(PREFERENCES_KEY) || 'null');
    if (!data || typeof data !== 'object') return defaults;
    const item = data as { theme?: unknown; sidebar?: unknown; uiAnimations?: unknown; language?: unknown };
    return {
      theme: item.theme === 'light' || item.theme === 'dark' ? item.theme : defaults.theme,
      sidebar: item.sidebar === 'fixed' || item.sidebar === 'pinned-open' ? 'fixed' : 'auto',
      uiAnimations: item.uiAnimations !== false,
      language: isLocale(item.language) ? item.language : DEFAULT_LOCALE,
    };
  } catch {
    return defaults;
  }
}

export function savePreferences(value: Preferences, storage: PreferenceStorage): boolean {
  try {
    storage.setItem(PREFERENCES_KEY, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function applyTheme(theme: Theme): void {
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
}

export function applyAnimationPreference(enabled: boolean): void {
  document.documentElement.dataset.uiAnimations = enabled ? 'on' : 'off';
}
