import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Check, LoaderCircle, Monitor, Moon, Search, Sun, Undo2 } from 'lucide-react';
import type { Preferences, Theme } from '../appearance/preferences';
import { Feedback } from '../components/Feedback';
import { ApiClient } from '../api/client';
import { useSettings, isMediaSetting, isSettingsValue, platformSettings } from '../api/useSettings';
import { SchemaField } from '../components/SchemaField';
import { getSettingsTools, SettingsTools } from '../components/SettingsTools';
import { settingCategory, settingDescription, settingLabel, translateSetting } from '../appearance/settingLabels';
import { isAdvancedSetting, isGuiSetting, batchKeys } from '../appearance/settingsPresentation';
import { BatchSettings } from '../components/BatchSettings';
import type { SettingDescription } from '../api/settingsContracts';
import { LOCALES, t, type Locale } from '../i18n';

export function Settings({ api, active = true, preferences, update, storageError }: {
  api: ApiClient; active?: boolean; preferences: Preferences; update: (value: Partial<Preferences>) => void; storageError: boolean;
}) {
  const [invalid, setInvalid] = useState<Record<string, string>>({});
  const settings = useSettings(api, active, invalid);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('appearance');
  const pageRef = useRef<HTMLDivElement>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(false);
  const [editorRevision, setEditorRevision] = useState(0);
  const [advancedOpen, setAdvancedOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    if (!settings.loading) { setShowSkeleton(false); return; }
    const timer = setTimeout(() => setShowSkeleton(true), 350);
    return () => clearTimeout(timer);
  }, [settings.loading]);
  const fields = useMemo(() => settings.schema?.filter((field) => isSettingsValue(field) && isGuiSetting(field)) || [], [settings.schema]);
  const categories = useMemo(() => [...new Set(fields.map((field) => field.category))], [fields]);
  const search = query.toLowerCase().trim();
  const tools = getSettingsTools();
  const appearanceKeywords = ['appearance', 'theme', 'systemTheme', 'lightTheme', 'darkTheme', 'sidebarMode', 'fixedSidebar', 'uiAnimations', 'interfaceLanguage']
    .map((key) => t(`gui.settings.${key}`)).concat([t('gui.common.automatic'), t('gui.common.enabled'), t('gui.common.disabled'), ...LOCALES.map((item) => item.label)]).join(' ').toLowerCase();
  const showAppearance = search ? appearanceKeywords.includes(search) : category === 'appearance';
  const matchingTool = tools.some(({ title }) => title.toLowerCase().includes(search));
  const filtered = fields.filter((field) => search
    ? `${settingLabel(field)} ${settingDescription(field)} ${field.key}`.toLowerCase().includes(search)
    : category === field.category);
  const showRegistered = !!search || categories.includes(category);
  useLayoutEffect(() => {
    pageRef.current?.closest('.page-slot')?.scrollTo({ top: 0, behavior: 'instant' });
  }, [category]);
  const selectCategory = (name: string) => {
    setCategory(name); setQuery('');
  };
  const categoryButton = (name: string, label: string, changed = false) => <button key={name} type="button"
    aria-label={label} aria-description={changed ? t('gui.settings.pendingChanges') : undefined}
    className={category === name && !search ? 'selected' : ''} aria-current={category === name && !search ? 'page' : undefined}
    onClick={() => selectCategory(name)}><span>{label}</span>{changed && <span className="category-dirty" aria-label={t('gui.settings.pendingChanges')} />}</button>;
  const dirty = Object.keys(settings.changes).length;
  const readOnly = settings.mode !== 'full' || !settings.document?.revision;
  const dependency = (field: SettingDescription): string => {
    if (!field.depends_on) return '';
    const value = settings.values[field.depends_on];
    const enabled = typeof value === 'number' ? value > 0 : !!value;
    const parent = settings.schema?.find((item) => item.key === field.depends_on);
    return enabled ? '' : t('gui.settings.dependency', { setting: parent ? settingLabel(parent) : field.depends_on });
  };
  const refresh = () => {
    if ((dirty || Object.values(invalid).some(Boolean)) && !confirmDiscard) { setConfirmDiscard(true); return; }
    setConfirmDiscard(false); setInvalid({}); setEditorRevision((value) => value + 1); settings.refresh();
  };
  const validity = (key: string, issue: string) => setInvalid((previous) => previous[key] === issue ? previous : ({ ...previous, [key]: issue }));
  const renderField = (field: SettingDescription) => {
    const unmet = dependency(field);
    const unsupported = field.key === 'enable_remote_access';
    const quickToggle = field.key === 'pre_translation_data' ? fields.find((item) => item.key === 'pre_translation_switch')
      : field.key === 'post_translation_data' ? fields.find((item) => item.key === 'post_translation_switch') : undefined;
    const description = [
      field.key === 'line_split_optimization_mode' && settings.values[field.key] === 'tail'
        ? translateSetting('setting_line_split_optimization_mode_tail_desc', settingDescription(field)) : settingDescription(field),
      quickToggle ? '' : unmet, unsupported ? t('gui.settings.remoteAccessInTui') : '',
    ].filter(Boolean).join(t('gui.settings.descriptionSeparator'));
    return <div key={`${field.key}:${editorRevision}`} hidden={!filtered.includes(field)}>
      {quickToggle && <div className="rule-quick-toggle"><label htmlFor={`quick-${quickToggle.key}`}>{settingLabel(quickToggle)}</label>
        <input id={`quick-${quickToggle.key}`} type="checkbox" role="switch" checked={settings.values[quickToggle.key] === true}
          disabled={readOnly || settings.undoing} onChange={(event) => settings.setValue(quickToggle, event.target.checked)} /></div>}
      <SchemaField field={field} label={settingLabel(field)} description={description}
      value={settings.values[field.key] ?? field.default} issue={settings.issues[field.key]}
      disabled={readOnly || settings.undoing || unsupported || !!unmet || (isMediaSetting(field) && !settings.media) || (platformSettings.has(field.key) && !settings.platform)}
      onChange={(value) => settings.setValue(field, value)} onValidityChange={(issue) => validity(field.key, issue)} /></div>;
  };
  const hasBatch = ['lines_limit', 'tokens_limit', 'tokens_limit_switch'].every((key) => fields.some((field) => field.key === key));
  const themes: { value: Theme; label: string; icon: typeof Sun }[] = [
    { value: 'system', label: t('gui.settings.systemTheme'), icon: Monitor },
    { value: 'light', label: t('gui.settings.lightTheme'), icon: Sun },
    { value: 'dark', label: t('gui.settings.darkTheme'), icon: Moon },
  ];
  return <div ref={pageRef} className="page settings-page">
    <header className="page-heading settings-page-heading"><h1>{t('gui.settings.title')}</h1>
      <label className="settings-search"><Search size={17} aria-hidden="true" /><input type="search" aria-label={t('gui.settings.searchLabel')} placeholder={t('gui.settings.searchPlaceholder')} value={query} onChange={(event) => setQuery(event.target.value)} /></label>
    </header>
    <div className="settings-layout">
    <nav className="settings-category-nav" aria-label={t('gui.settings.categories')}>
      {categoryButton('appearance', t('gui.settings.appearance'))}
      <div className="settings-nav-divider" />
      {categories.map((name) => categoryButton(name, settingCategory(name), fields.some((field) => field.category === name && (field.key in settings.changes || !!invalid[field.key]))))}
      <div className="settings-nav-divider" />
      {tools.map(({ id, title }) => categoryButton(id, title))}
    </nav>
    <div className="settings-content">
    <div hidden={!showAppearance}>
    <section className="panel settings-panel" aria-labelledby="appearance-title">
      <h2 id="appearance-title">{t('gui.settings.appearance')}</h2>
      <div className="setting-row"><label htmlFor="gui-language">{t('gui.settings.interfaceLanguage')}</label>
        <select id="gui-language" className="sidebar-mode-select" value={preferences.language}
          onChange={(event) => update({ language: event.target.value as Locale })}>
          {LOCALES.map(({ value, label }) => <option value={value} key={value}>{label}</option>)}
        </select>
      </div>
      <div className="setting-row"><span id="theme-label">{t('gui.settings.theme')}</span>
        <div className="segmented theme-options" role="group" aria-labelledby="theme-label">
          {themes.map(({ value, label, icon: Icon }) => <button key={value} aria-pressed={preferences.theme === value}
            onClick={() => update({ theme: value })}><Icon size={16} />{label}</button>)}
        </div>
      </div>
      <div className="setting-row"><label htmlFor="sidebar-mode">{t('gui.settings.sidebarMode')}</label>
        <select id="sidebar-mode" className="sidebar-mode-select" value={preferences.sidebar}
          onChange={(event) => update({ sidebar: event.target.value === 'fixed' ? 'fixed' : 'auto' })}>
          <option value="auto">{t('gui.common.automatic')}</option>
          <option value="fixed">{t('gui.settings.fixedSidebar')}</option>
        </select>
      </div>
      <div className="setting-row"><label htmlFor="ui-animations">{t('gui.settings.uiAnimations')}</label>
        <select id="ui-animations" className="sidebar-mode-select" value={preferences.uiAnimations ? 'on' : 'off'}
          onChange={(event) => update({ uiAnimations: event.target.value === 'on' })}>
          <option value="on">{t('gui.common.enabled')}</option><option value="off">{t('gui.common.disabled')}</option>
        </select>
      </div>
    </section>
    {storageError && <Feedback message={t('gui.settings.storageFailed')} />}
    </div>
    <div hidden={!showRegistered}>
    <section className="panel registered-settings" aria-labelledby="registered-settings-title">
      <div className="settings-section-heading"><div><h2 id="registered-settings-title">{search ? t('gui.settings.searchResults') : settingCategory(category)}</h2>
        {settings.document?.profile && <span className="muted settings-profile-name">{t('gui.settings.profileName', { name: settings.document.profile.replace(/\.json$/, '') })}</span>}
      </div><button className="text-button" disabled={settings.loading || settings.saving || settings.undoing} onClick={refresh}>{t('gui.settings.reload')}</button></div>
      {confirmDiscard && <div className="settings-discard-confirm" role="group" aria-label={t('gui.settings.confirmReload')}>
        <span>{t('gui.settings.reloadDiscardWarning')}</span>
        <button className="text-button" onClick={refresh}>{t('gui.settings.discardAndReload')}</button>
        <button className="text-button" onClick={() => setConfirmDiscard(false)}>{t('gui.common.cancel')}</button>
      </div>}
      {settings.error && <Feedback message={settings.error} retry={!settings.conflict && dirty ? () => void settings.retrySave() : undefined} />}
      {settings.undoError && <Feedback message={settings.undoError} retry={!settings.conflict ? () => void settings.retryUndo() : undefined} />}
      {settings.mediaError && <Feedback message={t('gui.settings.mediaError', { error: settings.mediaError })} />}
      {settings.mode === 'monitor' && <p className="muted">{t('gui.settings.readOnly')}</p>}
      {!settings.schema && showSkeleton && <div className="settings-skeleton" aria-label={t('gui.settings.loading')} aria-busy="true"><span /><span /><span /></div>}
      {!!settings.schema && <>
        <div className="settings-save-row" role="status" aria-live="polite">
          {settings.saving && <LoaderCircle size={16} className="spin" />}
          <span className="muted">{settings.undoing ? t('gui.settings.undoing') : settings.saving ? t('gui.settings.saving') : Object.values(invalid).some(Boolean) ? t('gui.settings.invalid') : settings.error || Object.keys(settings.issues).length ? t('gui.settings.unsaved') : dirty ? t('gui.settings.waitingSave') : settings.message || ''}</span>
          {settings.message && !dirty && <Check size={16} aria-hidden="true" />}
          {settings.undoCount > 0 && <button type="button" className="text-button" disabled={!settings.canUndo} onClick={() => void settings.undo()}><Undo2 size={15} />{t('gui.settings.undoLast')}<span className="muted">{t('gui.settings.undoCount', { count: settings.undoCount })}</span></button>}
          {(dirty > 0 || Object.values(invalid).some(Boolean)) && <button className="text-button" disabled={settings.saving} onClick={() => { settings.discard(); setInvalid({}); setEditorRevision((value) => value + 1); }}>{t('gui.settings.discardChanges')}</button>}
        </div>
        {filtered.length === 0 && !showAppearance && !matchingTool && <p className="settings-no-results muted">{t('gui.settings.noResults')}</p>}
        {categories.map((name) => <section className="settings-category" key={name} aria-label={settingCategory(name)} hidden={!filtered.some((field) => field.category === name)}>
          {search && <h3>{settingCategory(name)}</h3>}
          {fields.some((field) => field.category === name && platformSettings.has(field.key)) && <div className="field">
            <label htmlFor="reasoning-platform">{t('gui.settings.reasoningPlatform')}</label>
            <select id="reasoning-platform" value={settings.platform} disabled={readOnly || settings.saving || settings.undoing || Object.keys(settings.changes).some((key) => platformSettings.has(key))}
              onChange={(event) => settings.selectPlatform(event.target.value)}>
              {!settings.platform && <option value="">{t('gui.settings.noPlatforms')}</option>}
              {Object.keys(settings.platforms).map((platform) => <option key={platform} value={platform}>{platform}</option>)}
            </select>
          </div>}
          {hasBatch && name === 'translation' && <div hidden={!filtered.some((field) => batchKeys.has(field.key))}>
            <BatchSettings key={`batch:${editorRevision}`} fields={fields} values={settings.values} disabled={readOnly || settings.undoing}
              issues={settings.issues} invalid={invalid} onChange={settings.setValue} onValidityChange={validity} />
          </div>}
          {fields.filter((field) => field.category === name && !isAdvancedSetting(field) && !(hasBatch && batchKeys.has(field.key))).map(renderField)}
          {fields.some((field) => field.category === name && isAdvancedSetting(field)) && <div className="advanced-settings"
            hidden={!filtered.some((field) => field.category === name && isAdvancedSetting(field))}>
            <button type="button" className="advanced-settings-toggle" aria-expanded={!!search || !!advancedOpen[name]}
              onClick={() => setAdvancedOpen((previous) => ({ ...previous, [name]: !previous[name] }))}>
              <span>{t('gui.settings.advanced')}</span><span className="muted">{t('gui.settings.itemCount', { count: fields.filter((field) => field.category === name && isAdvancedSetting(field)).length })}</span>
              {fields.some((field) => field.category === name && isAdvancedSetting(field) && (invalid[field.key] || settings.issues[field.key])) && <span className="field-error">{t('gui.settings.needsReview')}</span>}
            </button>
            <div hidden={!search && !advancedOpen[name]}>{fields.filter((field) => field.category === name && isAdvancedSetting(field)).map(renderField)}</div>
          </div>}

        </section>)}
      </>}
    </section>
    </div>
    {!showRegistered && settings.error && <Feedback message={settings.error} retry={settings.conflict ? refresh : () => void settings.retrySave()} />}
    <SettingsTools selected={category} search={search} api={api} active={active} disabled={readOnly || dirty > 0 || settings.saving || settings.undoing || Object.values(invalid).some(Boolean)} onConfigurationChanged={settings.refreshIfClean} />
    </div>
    </div>
  </div>;
}
