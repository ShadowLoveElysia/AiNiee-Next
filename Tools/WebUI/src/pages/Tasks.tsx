import { useEffect, useState } from 'react';
import { getIntlLocale, t } from '../i18n';
import { ChevronDown, FilePenLine, FileText, ListTodo, LoaderCircle, Play, Plus, Square } from 'lucide-react';
import { ApiClient } from '../api/client';
import type { QueueItem, TaskStatus } from '../api/contracts';
import { useTasks } from '../api/useTasks';
import { useSessionTasks } from '../api/sessionTasks';
import { buildTaskRows, type TaskRow } from '../api/taskRows';
import { useQueueActions } from '../api/useQueueActions';
import { Feedback } from '../components/Feedback';
import { fileName } from '../components/FileImport';
import { QueueItemActions } from '../components/QueueItemActions';
import { QueueTaskEditor } from '../components/QueueTaskEditor';
import type { QueueRecord } from '../api/queueContracts';

const taskLabels: Record<string, string> = {
  translate: 'gui.tasks.type.translate', polish: 'gui.tasks.type.polish', all_in_one: 'gui.tasks.type.all_in_one',
  workflow: 'gui.tasks.type.workflow', queue: 'gui.tasks.type.queue',
};
const statusLabels: Record<string, string> = Object.fromEntries([
  'idle', 'waiting', 'pending', 'queued', 'running', 'preparing', 'starting', 'processing', 'completed', 'failed', 'error',
  'stopped', 'stopping', 'paused', 'cancelled', 'interrupted', 'waiting_for_agent', 'agent_disconnected', 'committed',
  'partial', 'translating', 'translated', 'polishing', 'polished', 'workflow', 'staging',
].map((status) => [status, `gui.tasks.status.${status}`]));

function StatusBadge({ status }: { status: string }) {
  const tone = ['failed', 'error'].includes(status) ? 'error' : ['running', 'processing', 'completed'].includes(status) ? 'green' : '';
  return <span className={`status-badge ${tone}`}><span />{statusLabels[status] ? t(statusLabels[status]) : status}</span>;
}

function Progress({ status }: { status: TaskStatus }) {
  const { completedProgress: completed, totalProgress: total } = status.stats;
  if (total <= 0) return null;
  return <div className="task-progress"><div><span>{t('gui.tasks.progress')}</span><span>{completed.toLocaleString(getIntlLocale())} / {total.toLocaleString(getIntlLocale())}</span></div>
    <progress value={Math.max(0, Math.min(completed, total))} max={total} aria-label={t('gui.tasks.progress')} />
  </div>;
}

function TaskDetails({ row }: { row: TaskRow }) {
  const current = row.snapshot?.status;
  return <div className="task-details">
    <dl>
      {row.inputPath && <div><dt>{t('gui.tasks.input_file')}</dt><dd>{row.inputPath}</dd></div>}
      {row.outputPath && <div><dt>{t('gui.tasks.output')}</dt><dd>{row.outputPath}</dd></div>}
      {row.profile && <div><dt>{t('gui.tasks.profile')}</dt><dd>{row.profile.replace(/\.json$/, '')}</dd></div>}
      {(row.sourceLanguage || row.targetLanguage) && <div><dt>{t('gui.tasks.language')}</dt><dd>{row.sourceLanguage === 'auto' ? t('gui.tasks.auto_language') : row.sourceLanguage || t('gui.common.inherit')} → {row.targetLanguage || t('gui.common.inherit')}</dd></div>}
    </dl>
    {row.stale && <p className="muted">{t('gui.tasks.stale')}</p>}
    {current && <><Progress status={current} /><TaskLogs status={current} /></>}
  </div>;
}

function TaskLogs({ status }: { status: TaskStatus }) {
  return <details className="task-logs"><summary>{t('gui.tasks.logs')}<ChevronDown size={15} /></summary>
    {status.logs.length === 0 ? <p className="muted">{t('gui.tasks.no_logs')}</p> : <ol aria-label={t('gui.tasks.logs')}>
      {status.logs.map((log) => <li key={log.seq} className={log.type === 'error' ? 'log-error' : ''}>
        <time>{new Date(log.timestamp * 1000).toLocaleTimeString(getIntlLocale(), { hour12: false })}</time><span>{log.message}</span>
      </li>)}
    </ol>}
  </details>;
}

export function Tasks({ api, active = true, onEditFile }: { api: ApiClient; active?: boolean; onEditFile?: (row: TaskRow) => void }) {
  const { queue, snapshot, queueError, statusError, mode, modeError, refreshing, retry } = useTasks(api, active);
  const actions = useQueueActions(api, retry);
  const observed = useSessionTasks(api);
  const rows = buildTaskRows(queue, observed, snapshot);
  const [selected, setSelected] = useState<string | null>(null);
  const [editor, setEditor] = useState<'new' | QueueRecord | null>(null);
  const [showSkeleton, setShowSkeleton] = useState(false);
  const status = snapshot?.status;
  const queueRun = observed.find((task) => task.current && task.queueRun && task.running && task.snapshot);
  useEffect(() => { setSelected(null); }, [snapshot?.runtime.runtime_id]);
  useEffect(() => { if (selected && !rows.active.some((row) => row.key === selected)) setSelected(null); }, [rows.active, selected]);
  const readOnly = mode !== 'full';
  const stale = !!(queueError || statusError || modeError) || refreshing || !status;
  const busy = !!actions.pending;
  const queueRunning = !!status?.running || !!queue?.some((item) => item.is_actually_processing);
  const protectedItem = (item: QueueItem) => item.protected || item.locked || item.is_actually_processing || !item.revision;
  const cannotEdit = readOnly || stale || busy || queueRunning;
  const cannotStart = cannotEdit || actions.uncertainStart || !rows.active.some((row) => row.queueItem) || !!queue?.some(protectedItem);
  useEffect(() => { if (!active) setEditor(null); }, [active]);
  useEffect(() => {
    if (!active || queue) { setShowSkeleton(false); return; }
    const timer = setTimeout(() => setShowSkeleton(true), 350);
    return () => clearTimeout(timer);
  }, [active, queue]);

  return <div className="page tasks-page">
    <header className="page-heading tasks-heading"><h1>{t('gui.tasks.title')}</h1>
      {status?.running && status.task_id && !readOnly && <button className="secondary-button" disabled={!!(statusError || modeError) || refreshing || busy}
        onClick={() => void actions.stop(status.task_id!)}>
        {actions.pending === 'stop' ? <LoaderCircle size={16} className="spin" /> : <Square size={15} />}
        {status.status === 'stopping' ? t('gui.tasks.retry_stop') : t('gui.tasks.stop')}
      </button>}
    </header>
    {modeError && <Feedback message={modeError} retry={retry} stale={!!mode} />}
    {mode === 'monitor' && <p className="muted task-readonly">{t('gui.tasks.readonly')}</p>}
    {actions.error && <Feedback message={actions.error} />}
    {actions.uncertainStart && <div className="queue-start-recovery">
      {!actions.error && <Feedback message={t('gui.tasks.start_unconfirmed')} />}
      <button className="text-button" onClick={retry} disabled={refreshing}>{t('gui.tasks.refresh_status')}</button>
      <button className="text-button" disabled={stale || busy || queueRunning}
        onClick={actions.acknowledgeStart}>{t('gui.tasks.allow_restart')}</button>
    </div>}
    {statusError && <Feedback message={statusError} retry={retry} stale={!!snapshot} />}
    <div className="tasks-layout">
    <section className="panel queue-panel" aria-labelledby="queue-title">
      <div className="panel-heading queue-heading"><span className="section-icon"><ListTodo size={20} /></span><h2 id="queue-title">{t('gui.tasks.queue')}</h2>
        {!readOnly && <button className="secondary-button queue-add-button" disabled={cannotEdit || !!editor} onClick={() => setEditor('new')}><Plus size={16} />{t('gui.tasks.add')}</button>}
        {!readOnly && <button className="primary-button queue-run-button" disabled={cannotStart || !!editor} onClick={() => void actions.run()}>
          {actions.pending === 'run' ? <LoaderCircle size={16} className="spin" /> : <Play size={15} />}
          {actions.pending === 'run' ? t('gui.tasks.status.starting') : t('gui.tasks.start_queue')}
        </button>}
      </div>
      {queueRun?.snapshot && <details className="queue-run-progress">
        <summary>{t('gui.tasks.queue_progress')}</summary><Progress status={queueRun.snapshot.status} /><TaskLogs status={queueRun.snapshot.status} />
      </details>}
      {queueError && <Feedback message={queueError} retry={retry} stale={!!queue} />}
      {!queue && !queueError && <div className="task-skeleton" aria-busy="true" aria-label={t('gui.tasks.loading_queue')}>
        {showSkeleton && <><span /><span /><span /></>}
      </div>}
      {queue && rows.active.length === 0 && <div className="empty-state"><span className="empty-icon"><ListTodo size={30} strokeWidth={1.25} /></span><p>{t('gui.tasks.empty')}</p></div>}
      {rows.active.length > 0 && <div className="queue-table" role="table" aria-label={t('gui.tasks.queue')} data-stale={!!queueError}>
        <div className="queue-header" role="row"><span role="columnheader">{t('gui.tasks.name')}</span><span role="columnheader">{t('gui.tasks.method')}</span><span role="columnheader">{t('gui.tasks.status_label')}</span><span /></div>
        {rows.active.map((row) => {
          const item = row.queueItem;
          const index = row.queueIndex;
          const expanded = selected === row.key;
          const name = fileName(row.name);
          const queueRows = rows.active.filter((entry) => entry.queueItem);
          const visibleIndex = queueRows.findIndex((entry) => entry.key === row.key);
          const previousIndex = queueRows[visibleIndex - 1]?.queueIndex;
          const nextIndex = queueRows[visibleIndex + 1]?.queueIndex;
          const canMove = (target?: number) => target !== undefined && index !== undefined && !!queue
            && queue.slice(Math.min(index, target), Math.max(index, target) + 1).every((entry) => !protectedItem(entry));
          return <div className="queue-item" key={row.key} role="rowgroup">
            <div className={`queue-row ${expanded ? 'selected' : ''}`} role="row">
              <div role="cell" className="queue-name"><button onClick={() => setSelected(expanded ? null : row.key)} aria-expanded={expanded}>
                <FileText size={18} /><span title={row.name}>{name}</span>
              </button></div>
              <span role="cell">{row.taskType ? (taskLabels[row.taskType] ? t(taskLabels[row.taskType]) : row.taskType) : '—'}</span>
              <span role="cell"><StatusBadge status={row.status} /></span>
              <span role="cell"><button className="icon-button" title={expanded ? t('gui.tasks.collapse_details') : t('gui.tasks.view_details')} aria-label={t(expanded ? 'gui.tasks.collapse_named' : 'gui.tasks.view_named', { name })}
                aria-expanded={expanded} onClick={() => setSelected(expanded ? null : row.key)}><ChevronDown className={expanded ? 'rotated' : ''} size={16} /></button></span>
            </div>
            {expanded && <div role="row"><div role="cell" aria-colspan={4}>
              <TaskDetails row={row} />
              {!readOnly && item && index !== undefined && <QueueItemActions item={item} disabled={cannotEdit || protectedItem(item) || !!editor}
                canMoveUp={canMove(previousIndex)} canMoveDown={canMove(nextIndex)}
                remove={() => actions.remove(item)} move={(direction) => {
                  const target = direction < 0 ? previousIndex : nextIndex;
                  return target === undefined ? Promise.resolve(false) : actions.move(item, target);
                }} edit={() => setEditor(item as QueueRecord)} />}
            </div></div>}
          </div>;
        })}
      </div>}
    </section>
    <aside className="execution-history" aria-labelledby="execution-history-title">
      <h2 id="execution-history-title">{t('gui.tasks.history')}</h2>
      {queue && rows.history.length === 0 && <p className="muted history-empty">{t('gui.tasks.no_history')}</p>}
      {rows.history.map((row) => <details className="history-entry" key={row.key}>
        <summary><FileText size={16} /><span title={row.name}>{fileName(row.name)}</span><StatusBadge status={row.status} />
          {onEditFile && ['completed', 'polished'].includes(row.status) && <button type="button" className="icon-button" title={t('gui.tasks.edit_file')} aria-label={t('gui.tasks.edit_file_named', { name: fileName(row.name) })}
            onClick={(event) => { event.preventDefault(); event.stopPropagation(); onEditFile(row); }}><FilePenLine size={16} /></button>}
        </summary>
        <TaskDetails row={row} />
      </details>)}
    </aside>
    </div>
    {editor && active && <QueueTaskEditor api={api} item={editor === 'new' ? undefined : editor}
      disabled={cannotEdit || (editor !== 'new' && !queue?.some((item) => item.task_id === editor.task_id && !protectedItem(item)))}
      onClose={() => setEditor(null)} onSaved={() => { setEditor(null); retry(); }} />}
  </div>;
}
