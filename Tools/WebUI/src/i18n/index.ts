import { resolveMessage, type Catalog, type MessageParameters } from './resolver';

export const LOCALES = [
  { value: 'zh_CN', label: '简体中文', intl: 'zh-CN' },
  { value: 'zh_CNTW', label: '繁體中文', intl: 'zh-TW' },
  { value: 'en', label: 'English', intl: 'en' },
  { value: 'ja', label: '日本語', intl: 'ja' },
  { value: 'ko', label: '한국어', intl: 'ko' },
  { value: 'ru', label: 'Русский', intl: 'ru' },
  { value: 'es', label: 'Español', intl: 'es' },
] as const;
export type Locale = typeof LOCALES[number]['value'];
export const DEFAULT_LOCALE: Locale = 'zh_CN';
export const FALLBACK_LOCALE: Locale = 'en';
const projectModules = import.meta.glob<{ default: Catalog }>('../../../../I18N/*.json');
const guiModules = import.meta.glob<{ default: Catalog }>('./locales/*/*.json');
const cache = new Map<Locale, Promise<{ project: Catalog; gui: Catalog }>>();
const listeners = new Set<() => void>();
let locale: Locale = DEFAULT_LOCALE;
let layers: Catalog[] = [];
let revision = 0;
let generation = 0;

export function isLocale(value: unknown): value is Locale {
  return LOCALES.some((item) => item.value === value);
}

async function load(locale: Locale) {
  let pending = cache.get(locale);
  if (!pending) {
    pending = (async () => {
      const projectLoader = projectModules[`../../../../I18N/${locale}.json`];
      const guiLoaders = Object.entries(guiModules).filter(([path]) => path.startsWith(`./locales/${locale}/`));
      if (!projectLoader || guiLoaders.length === 0) throw new Error(`Missing language catalog: ${locale}`);
      const [project, gui] = await Promise.all([
        projectLoader(),
        Promise.all(guiLoaders.map(([, loader]) => loader())),
      ]);
      const merged: Catalog = {};
      for (const catalog of gui) {
        for (const [key, text] of Object.entries(catalog.default)) {
          if (key in merged) throw new Error(`Duplicate GUI language key: ${key}`);
          merged[key] = text;
        }
      }
      return { project: project.default, gui: merged };
    })();
    cache.set(locale, pending);
    void pending.catch(() => cache.delete(locale));
  }
  return pending;
}

export async function setLocale(next: Locale): Promise<boolean> {
  const request = ++generation;
  const [selected, fallback] = await Promise.all([load(next), load(FALLBACK_LOCALE)]);
  if (request !== generation) return false;
  locale = next;
  layers = [selected.gui, selected.project, fallback.gui, fallback.project];
  document.documentElement.lang = getIntlLocale();
  revision++;
  listeners.forEach((listener) => listener());
  return true;
}

export const getLocale = (): Locale => locale;
export const getIntlLocale = (): string => LOCALES.find((item) => item.value === locale)!.intl;
export const getLanguageRevision = (): number => revision;
export function subscribeLanguage(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function t(key: string, parameters?: MessageParameters, fallback?: string): string {
  return resolveMessage(key, layers, parameters, fallback);
}
