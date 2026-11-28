import { useEffect, useRef, useState } from 'react';
import { Copy, ExternalLink, LoaderCircle, RefreshCw } from 'lucide-react';
import { ApiClient, errorMessage } from '../api/client';
import { Feedback } from './Feedback';
import { getLocale, t } from '../i18n';

const clients: { name: string; url: string; labelKey?: string }[] = [
  { name: 'Codex CLI', url: 'https://developers.openai.com/codex/mcp/' },
  { name: 'Claude Code', url: 'https://code.claude.com/docs/en/mcp' },
  { name: 'Cursor', url: 'https://cursor.com/docs/mcp' },
  { name: 'VS Code + GitHub Copilot', url: 'https://code.visualstudio.com/docs/agent-customization/mcp-servers' },
  { name: 'Qwen Code', url: 'https://qwenlm.github.io/qwen-code-docs/zh/users/features/mcp/' },
  { name: 'CodeBuddy Code', url: 'https://www.codebuddy.cn/docs/cli/mcp' },
  { name: 'WorkBuddy', url: 'https://www.workbuddy.cn/' },
  { name: 'Qwen Office', labelKey: 'gui.agentGuide.qwenOffice', url: 'https://www.qianwen.com/download' },
  { name: 'Doubao Desktop', labelKey: 'gui.agentGuide.doubaoDesktop', url: 'https://www.doubao.com/download' },
];

export function AgentPrompt({ api, disabled = false }: { api: ApiClient; disabled?: boolean }) {
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const generate = async () => {
    if (request.current || disabled) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api.request<{ prompt: string }>(`/system/external-agent-prompt?language=${getLocale()}`, { signal: controller.signal });
      if (!controller.signal.aborted) setPrompt(result.prompt);
    } catch (failure) { if (!controller.signal.aborted) setError(errorMessage(failure)); }
    finally { if (!controller.signal.aborted) { request.current = null; setBusy(false); } }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(prompt); setNotice(t('gui.agentPrompt.copied')); }
    catch { setNotice(t('gui.agentPrompt.copyFailed')); }
  };
  return <>
    <div className="agent-connection-guide">
      <p className="muted">{t('gui.agentGuide.intro')}</p>
      <ol className="agent-connection-steps">
        <li><strong>{t('gui.agentGuide.chooseClientTitle')}</strong>
          <p>{t('gui.agentGuide.chooseClientBody')}</p>
          <div className="agent-client-examples">{clients.map((client) => <a key={client.name} href={client.url} target="_blank" rel="noopener noreferrer">
            {client.labelKey ? t(client.labelKey) : client.name}<ExternalLink size={13} aria-hidden="true" />
          </a>)}</div>
        </li>
        <li><strong>{t('gui.agentGuide.sendPromptTitle')}</strong><p>{t('gui.agentGuide.sendPromptBody')}</p></li>
        <li><strong>{t('gui.agentGuide.nextTitle')}</strong><p>{t('gui.agentGuide.nextBody')}</p></li>
      </ol>
      <p className="agent-environment-hint muted">{t('gui.agentGuide.environment')}</p>
    </div>
    <div className="settings-tool-actions">
      <button type="button" className="primary-button" disabled={busy || disabled} onClick={() => void generate()}>
        {busy ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}{busy ? t('gui.agentPrompt.generating') : prompt ? t('gui.agentPrompt.regenerate') : t('gui.agentPrompt.generate')}
      </button>
      {prompt && <button type="button" className="secondary-button" disabled={busy} onClick={() => void copy()}><Copy size={16} />{t('gui.agentPrompt.copy')}</button>}
    </div>
    {error && <Feedback message={error} />}
    {prompt && <textarea className="agent-prompt-text" aria-label={t('gui.agentPrompt.label')} value={prompt} readOnly spellCheck={false} rows={16} />}
    {notice && <p className="settings-save-notice" role="status">{notice}</p>}
  </>;
}
