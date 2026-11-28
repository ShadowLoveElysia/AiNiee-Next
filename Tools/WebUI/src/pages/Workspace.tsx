import { t } from '../i18n';
import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { ChevronRight, FileText, History, Languages, ListPlus, LoaderCircle, PenLine, Pin, Play } from 'lucide-react';
import { ApiClient } from '../api/client';
import type { RecentProjects, RecentProject, SystemMode, TaskRequest, TaskType } from '../api/contracts';
import { useTaskSubmission } from '../api/useTaskSubmission';
import { LanguageField, CUSTOM_LANGUAGE } from '../components/LanguageField';
import { useResource } from '../api/useResource';
import { Feedback, QuietLoading } from '../components/Feedback';
import { FileImport, fileName, type DraftFile } from '../components/FileImport';
import { PathField } from '../components/PathField';

export interface Draft { file?: DraftFile; taskType: TaskType; profile: string; rulesProfile?: string; source: string; target: string; customSource: string; customTarget: string; outputPath: string }

export function Workspace({ api, draft, onDraft, kind, active = true }: { api: ApiClient; draft: Draft; onDraft: Dispatch<SetStateAction<Draft>>; kind: 'translate' | 'polish'; active?: boolean }) {
  const profiles = useResource<string[]>(api, '/profiles', active);
  const projects = useResource<RecentProjects>(api, '/system/recent-projects', active);
  const mode = useResource<SystemMode>(api, '/system/mode', active);
  const [uploading, setUploading] = useState(false);
  const outputOptions = useRef<HTMLDetailsElement>(null);
  const submission = useTaskSubmission(api);
  const [localIssues, setLocalIssues] = useState<Record<string, string>>({});
  const issues = { ...submission.issues, ...localIssues };
  useEffect(() => { if (issues.output_path && outputOptions.current) outputOptions.current.open = true; }, [issues.output_path]);
  const invalidate = () => { submission.reset(); setLocalIssues({}); };
  const update = (value: Partial<Draft>) => { invalidate(); onDraft((current) => ({ ...current, ...value })); };
  const readOnly = mode.data?.mode !== 'full' || !!mode.error;
  const disabled = readOnly || submission.busy;
  const selectProject = (project: RecentProject) => update({
    file: { name: fileName(project.path), path: project.path }, profile: project.profile,
    rulesProfile: project.rules_profile, source: 'auto', target: '', customSource: '', customTarget: '',
  });
  const start = (destination: 'run' | 'queue') => {
    if (disabled || uploading) return;
    const errors: Record<string, string> = {};
    if (!draft.file) errors.input_path = t('gui.workspace.selectInput');
    const source = draft.source === CUSTOM_LANGUAGE ? draft.customSource.trim() : draft.source;
    const target = draft.target === CUSTOM_LANGUAGE ? draft.customTarget.trim() : draft.target;
    if (!source) errors.source_lang = t('gui.workspace.enterSource');
    if (draft.target === CUSTOM_LANGUAGE && !target) errors.target_lang = t('gui.workspace.enterTarget');
    setLocalIssues(errors);
    if (Object.keys(errors).length || !draft.file) return;
    const body: TaskRequest = {
      task_type: draft.taskType, input_path: draft.file.path, source_lang: source,
      ...(target ? { target_lang: target } : {}),
      ...(draft.profile ? { profile: draft.profile } : {}),
      ...(draft.rulesProfile ? { rules_profile: draft.rulesProfile } : {}),
      ...(draft.outputPath.trim() ? { output_path: draft.outputPath.trim() } : {}),
    };
    void submission.submit(body, destination);
  };

  return <div className="page workspace-page">
    <header className="page-heading"><h1>{t(kind === 'translate' ? 'gui.nav.translate' : 'gui.nav.polish')}</h1></header>
    <div className="workspace-grid">
      <section className="panel prepare-panel" aria-labelledby={`${kind}-prepare-title`}>
        <div className="panel-heading"><span className="section-icon">{kind === 'translate' ? <Languages size={20} /> : <PenLine size={20} />}</span><h2 id={`${kind}-prepare-title`}>{t(kind === 'translate' ? 'gui.workspace.prepareTranslate' : 'gui.workspace.preparePolish')}</h2></div>
        {mode.error && <Feedback message={mode.error} retry={mode.retry} />}
        {mode.data?.mode === 'monitor' && <Feedback message={t('gui.workspace.readOnly')} />}
        <FileImport api={api} file={draft.file} disabled={disabled} onFile={(file) => update({ file })}
          onBusy={setUploading} issue={issues.input_path} onInvalidate={invalidate} />
        <form onSubmit={(event) => { event.preventDefault(); start('run'); }}>
          <fieldset disabled={disabled} className="task-fields">
          {kind === 'translate' && <label className="combined-task-option"><input type="checkbox" checked={draft.taskType === 'all_in_one'}
            onChange={(event) => update({ taskType: event.target.checked ? 'all_in_one' : 'translate' })} />{t('gui.workspace.translateAndPolish')}</label>}
          <div className="task-configuration-row">
          <div className="field"><label htmlFor={`${kind}-profile`}>{t('gui.workspace.profile')}</label>
            <select id={`${kind}-profile`} value={draft.profile} aria-invalid={!!issues.profile} onChange={(event) => update({ profile: event.target.value, rulesProfile: undefined })}>
              <option value="">{t('gui.workspace.currentProfile')}</option>
              {draft.profile && !profiles.data?.includes(draft.profile) && <option value={draft.profile}>{draft.profile}</option>}
              {profiles.data?.map((profile) => <option key={profile} value={profile}>{profile.replace(/\.json$/, '')}</option>)}
            </select>
            {issues.profile && <span className="field-error">{issues.profile}</span>}
            {profiles.loading && !profiles.data && <QuietLoading label={t('gui.workspace.loadingProfiles')} />}
            {profiles.error && <Feedback message={profiles.error} retry={profiles.retry} stale={!!profiles.data} />}
          </div>
            <LanguageField idPrefix={`${kind}-`} kind="source" value={draft.source} custom={draft.customSource} onChange={(source) => update({ source })}
              onCustom={(customSource) => update({ customSource })} issue={issues.source_lang} />
            <LanguageField idPrefix={`${kind}-`} kind="target" value={draft.target} custom={draft.customTarget} onChange={(target) => update({ target })}
              onCustom={(customTarget) => update({ customTarget })} issue={issues.target_lang} />
          </div>
          <details ref={outputOptions} className="task-output-options">
            <summary>{t('gui.workspace.outputLocation')}</summary>
          <div className="field"><label htmlFor={`${kind}-output`}>{t('gui.workspace.outputLocation')}</label>
            <PathField api={api} id={`${kind}-output`} value={draft.outputPath} label={t('gui.workspace.outputLocation')} mode="directory" disabled={disabled}
              issue={issues.output_path} onChange={(outputPath) => update({ outputPath })} />
            <span className="field-hint">{t('gui.workspace.outputHint')}</span>
            {issues.output_path && <span className="field-error">{issues.output_path}</span>}
          </div>
          </details>
          </fieldset>
          {submission.preview && <div className="preview-result" role="status">
            <strong>{t('gui.workspace.missingPrompts')}</strong>
            {submission.preview.missing_prompts.map((prompt) => <p key={prompt}>{t('gui.workspace.promptNotSelected', { kind: prompt === 'translation' ? t('gui.nav.translate') : prompt === 'polishing' ? t('gui.nav.polish') : prompt })}</p>)}
          </div>}
          {submission.choice && <div className="output-choice" role="group" aria-label={t('gui.workspace.existingOutputActions')}>
            <strong>{t('gui.workspace.outputExists')}</strong>
            <div className="output-path"><code>{submission.choice.preview.resolved_output_path}</code></div>
            <div className="output-actions">
              {submission.choice.preview.cache_exists && <button type="button" className="secondary-button" disabled={submission.busy} onClick={() => void submission.chooseOutput('resume')}>{t('gui.workspace.resume')}</button>}
              <button type="button" className="secondary-button" disabled={submission.busy} onClick={() => void submission.chooseOutput('archive')}>{t('gui.workspace.archiveRestart')}</button>
              <button type="button" className="text-button" disabled={submission.busy} onClick={submission.cancelChoice}>{t('gui.common.cancel')}</button>
            </div>
          </div>}
          {submission.error && <Feedback message={submission.error} />}
          {submission.uncertain && <div className="output-actions">
            <a className="text-button" href="#/tasks">{t('gui.workspace.viewTasks')}</a>
            <button className="text-button" type="button" disabled={submission.busy} onClick={() => void submission.refreshOutcome()}>{t('gui.workspace.refreshStatus')}</button>
            <button className="text-button" type="button" disabled={submission.busy} onClick={submission.allowResubmit}>{t('gui.workspace.allowResubmit')}</button>
          </div>}
          <div className="form-footer">
            <button type="button" className="secondary-button" disabled={disabled || uploading || submission.uncertain} onClick={() => start('queue')}><ListPlus size={17} />{t('gui.workspace.addToQueue')}</button>
            <button type="submit" className="primary-button" disabled={disabled || uploading || submission.uncertain}>
              {submission.busy ? <><LoaderCircle size={17} className="spin" />{t('gui.workspace.submitting')}</> : <><Play size={16} />{t('gui.workspace.start')}</>}
            </button>
          </div>
        </form>
      </section>
      <section className="recent-section" aria-labelledby={`${kind}-recent-title`}>
        <div className="recent-heading"><History size={18} /><h2 id={`${kind}-recent-title`}>{t('gui.workspace.recentProjects')}</h2></div>
        {projects.loading && !projects.data && <QuietLoading label={t('gui.workspace.loadingRecent')} />}
        {projects.error && <Feedback message={projects.error} retry={projects.retry} stale={!!projects.data} />}
        {projects.data?.projects.length === 0 && <div className="recent-empty"><span className="empty-icon"><FolderHistoryIcon /></span><p>{t('gui.workspace.noRecentProjects')}</p></div>}
        <div className="recent-list">{projects.data?.projects.map((project) => <button key={project.path} className="recent-project" onClick={() => selectProject(project)} disabled={uploading || submission.busy}>
          <FileText size={20} strokeWidth={1.5} /><span className="recent-info"><strong title={project.path}>{fileName(project.path)}</strong>
            <span>{project.profile.replace(/\.json$/, '')}</span></span>{project.pinned && <Pin size={13} aria-label={t('gui.workspace.pinned')} />}<ChevronRight size={15} />
        </button>)}</div>
      </section>
    </div>
  </div>;
}

function FolderHistoryIcon() { return <History size={26} strokeWidth={1.2} />; }
