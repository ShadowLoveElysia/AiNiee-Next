import { t } from '../i18n';
import { ArrowLeft, FilePenLine } from 'lucide-react';
import type { TaskRow } from '../api/taskRows';
import { fileName } from '../components/FileImport';

export function CacheEditor({ taskId, task }: { taskId: string; task?: TaskRow }) {
  return <div className="page cache-editor-page">
    <header className="page-heading cache-editor-heading">
      <a className="icon-button" href="#/tasks" aria-label={t('gui.cacheEditor.backToTasks')} title={t('gui.cacheEditor.backToTasks')}><ArrowLeft size={20} /></a>
      <h1>{t('gui.cacheEditor.title')}</h1>
    </header>
    <section className="panel cache-editor-placeholder" aria-labelledby="cache-file-title">
      <span className="empty-icon"><FilePenLine size={28} strokeWidth={1.5} /></span>
      <h2 id="cache-file-title">{task ? fileName(task.name) : t('gui.cacheEditor.taskFile')}</h2>
      <p className="muted">{t('gui.cacheEditor.unavailable')}</p>
      <dl>
        {task?.inputPath && <div><dt>{t('gui.cacheEditor.inputPath')}</dt><dd>{task.inputPath}</dd></div>}
        {task?.outputPath && <div><dt>{t('gui.workspace.outputLocation')}</dt><dd>{task.outputPath}</dd></div>}
        {!task && <div><dt>{t('gui.cacheEditor.taskId')}</dt><dd>{taskId}</dd></div>}
      </dl>
    </section>
  </div>;
}
