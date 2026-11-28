import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './appearance/bootstrap';
import { App } from './App';
import { readPreferences } from './appearance/preferences';
import { DEFAULT_LOCALE, setLocale } from './i18n';

async function start() {
  try { await setLocale(readPreferences().language); }
  catch { await setLocale(DEFAULT_LOCALE); }
  createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
}
void start();
