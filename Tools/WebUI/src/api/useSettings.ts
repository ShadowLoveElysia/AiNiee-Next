import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiClient, ApiError, errorMessage } from './client';
import type { SystemMode } from './contracts';
import type { MediaSettingsDocument, SettingDescription, SettingsDocument, SettingsValidation, SettingValues } from './settingsContracts';
import { settingsScope, useSettingsHistory } from './settingsHistory';
import { t } from '../i18n';

interface SavedSettingsChange {
  target: 'profile' | 'media';
  scope: string;
  platform: string;
  before: SettingValues;
  after: SettingValues;
}

const menuKeys = new Set(['ebook_series_settings', 'media_settings', 'api_pool_management', 'automation_settings', 'external_agent_mcp_guide']);
const responseChecks = new Set(['newline_character_count_check', 'return_to_original_text_check', 'residual_original_text_check', 'reply_format_check', 'untranslated_retry_limit', 'untranslated_reduction_rate']);
export const platformSettings = new Set(['think_switch', 'think_depth', 'thinking_budget']);
export const isSettingsValue = (field: SettingDescription) => !menuKeys.has(field.key);
export const isMediaSetting = (field: SettingDescription) => field.submenu === 'media_settings' && field.key.startsWith('media_');
const equal = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

function projectValues(config: SettingValues, schema: SettingDescription[], media: boolean): SettingValues {
  const checks = config.response_check_switch && typeof config.response_check_switch === 'object' ? config.response_check_switch as SettingValues : {};
  return Object.fromEntries(schema.filter((field) => isSettingsValue(field) && isMediaSetting(field) === media)
    .map((field) => [field.key, (responseChecks.has(field.key) ? checks[field.key] : config[media ? field.key.slice(6) : field.key]) ?? (field.key === 'sdk_request_mode' ? 'openai' : field.default)]));
}

function profilePayload(changes: SettingValues, platform: string): SettingValues {
  const body = Object.fromEntries(Object.entries(changes).filter(([key]) => !responseChecks.has(key) && !platformSettings.has(key)));
  const checks = Object.fromEntries(Object.entries(changes).filter(([key]) => responseChecks.has(key)));
  if (Object.keys(checks).length) body.response_check_switch = checks;
  const reasoning = Object.fromEntries(Object.entries(changes).filter(([key]) => platformSettings.has(key)));
  if (Object.keys(reasoning).length) {
    if (!platform) throw new ApiError(t('gui.settingsSave.chooseReasoningPlatform'));
    body.platforms = { [platform]: reasoning };
  }
  return body;
}

export function useSettings(api: ApiClient, active: boolean, invalid: Record<string, string> = {}) {
  const [schema, setSchema] = useState<SettingDescription[]>();
  const [document, setDocument] = useState<SettingsDocument>();
  const [media, setMedia] = useState<SettingsDocument>();
  const [platforms, setPlatforms] = useState<Record<string, SettingValues>>({});
  const [platform, setPlatform] = useState('');
  const [changes, setChanges] = useState<SettingValues>({});
  const [issues, setIssues] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [mediaError, setMediaError] = useState('');
  const [message, setMessage] = useState('');
  const [mode, setMode] = useState<SystemMode['mode']>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [undoError, setUndoError] = useState('');
  const history = useSettingsHistory<SavedSettingsChange>();
  const scope = useRef<string | undefined>(undefined);
  const [pause, setPause] = useState<'none' | 'validation' | 'error' | 'conflict'>('none');
  const [reload, setReload] = useState(0);
  const loaded = useRef(false);
  const request = useRef<AbortController | null>(null);
  const pendingValues = useRef<SettingValues>({});
  const changesRef = useRef<SettingValues>({});
  const documentRef = useRef<SettingsDocument | undefined>(undefined);
  const mediaRef = useRef<SettingsDocument | undefined>(undefined);
  const lastEdit = useRef(0);
  const current = useRef({ schema, mode, platform, invalid, pause, issues, loading });
  current.current = { schema, mode, platform, invalid, pause, issues, loading };
  const commitChanges = useCallback((next: SettingValues) => { changesRef.current = next; setChanges(next); }, []);
  const commitDocument = (next: SettingsDocument) => { documentRef.current = next; setDocument(next); };
  const commitMedia = (next: SettingsDocument) => { mediaRef.current = next; setMedia(next); };
  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (!active || loaded.current || request.current) return;
    const controller = new AbortController(); request.current = controller;
    const signal = controller.signal;
    setLoading(true); setError(''); setMediaError('');
    void (async () => {
      try {
        const [fields, config, systemMode] = await Promise.all([
          api.request<SettingDescription[]>('/system/settings-schema', { signal }),
          api.request<SettingValues>('/config', { signal }),
          api.request<SystemMode>('/system/mode', { signal }),
        ]);
        signal.throwIfAborted();
        const nextScope = settingsScope(config);
        if (scope.current !== undefined && scope.current !== nextScope) history.clear();
        scope.current = nextScope;
        setUndoError('');
        setSchema(fields); setMode(systemMode.mode);
        const rawPlatforms = config.platforms && typeof config.platforms === 'object' ? config.platforms as SettingValues : {};
        const platformValues = Object.fromEntries(Object.entries(rawPlatforms).filter(([, value]) => value && typeof value === 'object')
          .map(([name, value]) => [name, Object.fromEntries(fields.filter((field) => platformSettings.has(field.key))
            .map((field) => [field.key, (value as SettingValues)[field.key] ?? field.default]))]));
        const targets = config.api_settings && typeof config.api_settings === 'object' ? config.api_settings as SettingValues : {};
        const selected = String(targets.translate || config.target_platform || Object.keys(platformValues)[0] || '');
        const resolved = selected in platformValues ? selected : Object.keys(platformValues)[0] || '';
        setPlatforms(platformValues); setPlatform(resolved);
        commitDocument({ values: { ...projectValues(config, fields, false), ...platformValues[resolved] }, revision: String(config._config_revision || ''), profile: String(config.active_profile || '') });
        if (fields.some(isMediaSetting)) {
          try {
            const data = await api.request<MediaSettingsDocument>('/media/settings', { signal });
            signal.throwIfAborted();
            commitMedia({ values: projectValues(data.values, fields, true), revision: data.revision });
          } catch (failure) { if (!signal.aborted) setMediaError(errorMessage(failure)); }
        }
        signal.throwIfAborted();
        loaded.current = true;
      } catch (failure) { if (!signal.aborted) setError(errorMessage(failure)); }
      finally { if (!signal.aborted) { setLoading(false); request.current = null; } }
    })();
    return () => { controller.abort(); if (request.current === controller) request.current = null; };
  }, [active, api, reload]);

  const values = useMemo(() => ({ ...document?.values, ...media?.values, ...changes }), [document, media, changes]);
  const setValue = useCallback((field: SettingDescription, value: unknown) => {
    setMessage(''); setUndoError(''); lastEdit.current = Date.now();
    const baseline = (isMediaSetting(field) ? mediaRef.current : documentRef.current)?.values[field.key];
    const next = { ...changesRef.current };
    // A return to the old baseline is still a new intent while that field is being saved.
    if (equal(value, baseline) && !(field.key in pendingValues.current)) delete next[field.key];
    else next[field.key] = value;
    commitChanges(next);
    setIssues((previous) => { const remaining = { ...previous }; delete remaining[field.key]; return remaining; });
  }, [commitChanges]);

  const save = useCallback(async (retry = false) => {
    const state = current.current;
    const profile = documentRef.current;
    if (request.current || !state.schema || !profile?.revision || state.mode !== 'full' || state.loading
      || state.pause === 'conflict' || (!retry && state.pause === 'error') || Object.values(state.invalid).some(Boolean)) return;
    if (!retry && Object.values(state.issues).some(Boolean)) return;
    const allowed = state.schema.filter((field) => isSettingsValue(field) && field.key !== 'enable_remote_access');
    const selected = Object.fromEntries(allowed.filter((field) => field.key in changesRef.current).map((field) => [field.key, changesRef.current[field.key]]));
    if (!Object.keys(selected).length) return;
    const controller = new AbortController(); request.current = controller; const signal = controller.signal;
    pendingValues.current = selected;
    setSaving(true); setError(''); setMessage(''); setPause('none');
    const acknowledge = (savedValues: SettingValues) => {
      const remaining = { ...changesRef.current };
      for (const [key, value] of Object.entries(savedValues)) {
        if (key in remaining && equal(remaining[key], value)) delete remaining[key];
        delete pendingValues.current[key];
      }
      commitChanges(remaining);
    };
    try {
      const validation = await api.request<SettingsValidation>('/system/settings/validate', { method: 'POST', body: { values: selected }, signal });
      signal.throwIfAborted();
      if (Object.values(current.current.invalid).some(Boolean)) return;
      if (!validation.valid) {
        const relevant = Object.fromEntries(Object.entries(validation.errors).filter(([key]) => equal(changesRef.current[key], selected[key])));
        setIssues(relevant); setPause(Object.keys(relevant).length ? 'validation' : 'none'); return;
      }
      setIssues({});
      const profileChanges = Object.fromEntries(allowed.filter((field) => !isMediaSetting(field) && field.key in selected).map((field) => [field.key, selected[field.key]]));
      const mediaChanges = Object.fromEntries(allowed.filter((field) => isMediaSetting(field) && field.key in selected).map((field) => [field.key.slice(6), selected[field.key]]));
      if (Object.keys(profileChanges).length) {
        if (Object.values(current.current.invalid).some(Boolean)) return;
        const saved = await api.request<{ revision: string }>('/config', { method: 'POST', body: { ...profilePayload(profileChanges, state.platform), _config_revision: profile.revision }, signal });
        signal.throwIfAborted();
        const changed = Object.fromEntries(Object.entries(profileChanges).filter(([key, value]) => !equal(profile.values[key], value)));
        if (Object.keys(changed).length) history.push({ target: 'profile', scope: scope.current || '', platform: state.platform,
          before: Object.fromEntries(Object.keys(changed).map((key) => [key, profile.values[key]])), after: changed });
        commitDocument({ ...profile, values: { ...profile.values, ...profileChanges }, revision: saved.revision });
        const reasoning = Object.fromEntries(Object.entries(profileChanges).filter(([key]) => platformSettings.has(key)));
        if (Object.keys(reasoning).length) setPlatforms((previous) => ({ ...previous, [state.platform]: { ...previous[state.platform], ...reasoning } }));
        acknowledge(profileChanges);
      }
      if (Object.keys(mediaChanges).length) {
        if (Object.values(current.current.invalid).some(Boolean)) return;
        const previous = mediaRef.current;
        if (!previous) throw new ApiError(t('gui.settingsSave.mediaNotLoaded'));
        const saved = await api.request<{ success: boolean; revision: string }>('/media/settings', { method: 'PUT', body: { changes: mediaChanges, expected_revision: previous.revision }, signal });
        signal.throwIfAborted();
        if (!saved.success) throw new ApiError(t('gui.settingsSave.mediaSaveFailed'));
        const prefixed = Object.fromEntries(Object.entries(mediaChanges).map(([key, value]) => [`media_${key}`, value]));
        const changed = Object.fromEntries(Object.entries(prefixed).filter(([key, value]) => !equal(previous.values[key], value)));
        if (Object.keys(changed).length) history.push({ target: 'media', scope: scope.current || '', platform: '',
          before: Object.fromEntries(Object.keys(changed).map((key) => [key, previous.values[key]])), after: changed });
        commitMedia({ values: { ...previous.values, ...prefixed }, revision: saved.revision });
        acknowledge(prefixed);
      }
      if (!Object.keys(changesRef.current).length) setMessage(t('gui.settingsSave.saved'));
    } catch (failure) {
      if (!signal.aborted) {
        const conflict = failure instanceof ApiError && failure.status === 409;
        setPause(conflict ? 'conflict' : 'error');
        setError(conflict ? t('gui.settingsSave.conflict') : t('gui.settingsSave.retryRetained', { error: errorMessage(failure) }));
      }
    } finally {
      if (!signal.aborted) { pendingValues.current = {}; request.current = null; setSaving(false); }
    }
  }, [api, commitChanges, history.push]);

  const undo = async (retry = false) => {
    const state = current.current;
    const entry = history.latest();
    if (!entry || request.current || state.loading || state.mode !== 'full' || state.pause === 'conflict'
      || state.pause === 'error' || Object.keys(changesRef.current).length || Object.values(state.invalid).some(Boolean)
      || Object.values(state.issues).some(Boolean) || (!retry && undoError)) return;
    const fields = state.schema;
    if (!fields) return;
    const controller = new AbortController(); request.current = controller;
    const signal = controller.signal;
    const saved = entry.value;
    setUndoing(true); setUndoError(''); setMessage('');
    const ensureUnchanged = (values: SettingValues) => {
      if (Object.entries(saved.after).some(([key, value]) => !equal(values[key], value))) {
        throw new ApiError(t('gui.settingsSave.undoConflict'), 409);
      }
      if (Object.keys(changesRef.current).length || Object.values(current.current.invalid).some(Boolean)) {
        throw new ApiError(t('gui.settingsSave.undoNewChanges'), 422);
      }
    };
    try {
      const config = await api.request<SettingValues>('/config', { signal });
      signal.throwIfAborted();
      if (settingsScope(config) !== saved.scope) throw new ApiError(t('gui.settingsSave.profileChanged'), 409);
      if (saved.target === 'media') {
        const latest = await api.request<MediaSettingsDocument>('/media/settings', { signal });
        const projected = projectValues(latest.values, fields, true);
        ensureUnchanged(projected);
        const changes = Object.fromEntries(Object.entries(saved.before).map(([key, value]) => [key.slice(6), value]));
        const result = await api.request<{ success: boolean; revision: string }>('/media/settings', {
          method: 'PUT', body: { changes, expected_revision: latest.revision }, signal,
        });
        signal.throwIfAborted();
        if (!result.success) throw new ApiError(t('gui.settingsSave.mediaUndoFailed'));
        commitMedia({ values: { ...projected, ...saved.before }, revision: result.revision });
      } else {
        const rawPlatforms = config.platforms && typeof config.platforms === 'object' ? config.platforms as SettingValues : {};
        const platformValues = Object.fromEntries(Object.entries(rawPlatforms).filter(([, value]) => value && typeof value === 'object')
          .map(([name, value]) => [name, Object.fromEntries(fields.filter((field) => platformSettings.has(field.key))
            .map((field) => [field.key, (value as SettingValues)[field.key] ?? field.default]))]));
        const projected = projectValues(config, fields, false);
        ensureUnchanged({ ...projected, ...platformValues[saved.platform] });
        if (Object.keys(saved.before).some((key) => platformSettings.has(key)) && !(saved.platform in platformValues)) {
          throw new ApiError(t('gui.settingsSave.platformMissing'), 409);
        }
        const revision = config._config_revision;
        if (typeof revision !== 'string' || !revision) throw new ApiError(t('gui.settingsSave.revisionMissing'), 409);
        const result = await api.request<{ revision: string }>('/config', {
          method: 'POST', body: { ...profilePayload(saved.before, saved.platform), _config_revision: revision }, signal,
        });
        signal.throwIfAborted();
        const reasoning = Object.fromEntries(Object.entries(saved.before).filter(([key]) => platformSettings.has(key)));
        if (Object.keys(reasoning).length) platformValues[saved.platform] = { ...platformValues[saved.platform], ...reasoning };
        setPlatforms(platformValues);
        const restored = Object.fromEntries(Object.entries(saved.before).filter(([key]) => !platformSettings.has(key)));
        commitDocument({ values: { ...projected, ...restored, ...platformValues[current.current.platform] }, revision: result.revision,
          profile: String(config.active_profile || '') });
      }
      history.pop(entry);
      setMessage(t('gui.settingsSave.undone'));
    } catch (failure) {
      if (!signal.aborted) {
        const conflict = failure instanceof ApiError && failure.status === 409;
        if (conflict) setPause('conflict');
        setUndoError(t('gui.settingsSave.undoRetained', { error: errorMessage(failure) }));
      }
    } finally {
      if (!signal.aborted) { request.current = null; setUndoing(false); }
    }
  };

  const invalidFields = Object.values(invalid).some(Boolean);
  useEffect(() => {
    if (!Object.keys(changes).length || saving || undoing || loading || invalidFields || pause === 'error' || pause === 'conflict' || Object.values(issues).some(Boolean)) return;
    const timer = setTimeout(() => void save(), Math.max(0, 600 - (Date.now() - lastEdit.current)));
    return () => clearTimeout(timer);
  }, [changes, saving, undoing, loading, invalidFields, pause, issues, save]);

  const discard = () => { if (!request.current) { commitChanges({}); setIssues({}); setMessage(''); setError(''); if (pause !== 'conflict') setPause('none'); } };
  const refresh = () => {
    if (request.current) return;
    discard(); loaded.current = false; setPause('none'); setUndoError(''); setReload((value) => value + 1);
  };
  const refreshIfClean = () => {
    if (request.current || Object.keys(changesRef.current).length || Object.values(current.current.invalid).some(Boolean)) return;
    refresh();
  };
  const selectPlatform = (name: string) => {
    if (request.current || !(name in platforms) || Object.keys(changesRef.current).some((key) => platformSettings.has(key))) return;
    setPlatform(name);
    if (documentRef.current) commitDocument({ ...documentRef.current, values: { ...documentRef.current.values, ...platforms[name] } });
  };
  const canUndo = history.count > 0 && !loading && !saving && !undoing && mode === 'full' && pause === 'none'
    && !undoError && !Object.keys(changes).length && !Object.values(invalid).some(Boolean) && !Object.values(issues).some(Boolean);
  return { schema, document, media, values, changes, issues, error, mediaError, message, mode, loading, saving, conflict: pause === 'conflict', platforms, platform, selectPlatform, setValue,
    undo: () => undo(), retryUndo: () => undo(true), canUndo, undoCount: history.count, undoing, undoError,
    save: () => save(true), retrySave: () => save(true), discard, refresh, refreshIfClean };
}
