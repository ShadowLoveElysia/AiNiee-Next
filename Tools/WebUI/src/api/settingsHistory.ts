import { useCallback, useRef, useState } from 'react';

export interface SettingsHistoryEntry<T> { id: number; value: T }
export const SETTINGS_HISTORY_LIMIT = 10;

export function settingsScope(config: Record<string, unknown>): string {
  return JSON.stringify([config.active_profile ?? '', config.active_rules_profile ?? '']);
}

export function useSettingsHistory<T>() {
  const history = useRef<SettingsHistoryEntry<T>[]>([]);
  const sequence = useRef(0);
  const [entries, setEntries] = useState<readonly SettingsHistoryEntry<T>[]>([]);
  const push = useCallback((value: T) => {
    history.current = [...history.current, { id: ++sequence.current, value: structuredClone(value) }].slice(-SETTINGS_HISTORY_LIMIT);
    setEntries(history.current);
  }, []);
  const pop = useCallback((entry: SettingsHistoryEntry<T>) => {
    if (history.current.at(-1)?.id !== entry.id) return false;
    history.current = history.current.slice(0, -1);
    setEntries(history.current);
    return true;
  }, []);
  const clear = useCallback(() => { history.current = []; setEntries([]); }, []);
  const latest = useCallback(() => history.current.at(-1), []);
  return { entries, count: entries.length, push, pop, clear, latest };
}
