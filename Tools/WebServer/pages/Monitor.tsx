import React, { useEffect, useState, useRef } from 'react';
import { StatsPanel } from '../components/StatsPanel';
import { Terminal } from '../components/Terminal';
import { DataService, mergeTaskStatus } from '../services/DataService';
import { useGlobal } from '../contexts/GlobalContext';
import { Activity, LayoutDashboard, Loader2 } from 'lucide-react';
import { useI18n } from '../contexts/I18nContext';

export const Monitor: React.FC = () => {
  const { t } = useI18n();
  const { taskState, setTaskState, config } = useGlobal();
  const intervalRef = useRef<any>(null);
  const cursorRef = useRef({ logs: 0, chart: 0, comparison: 0 });
  const showDetailed = config?.show_detailed_logs || false;
  const [activeTab, setActiveTab] = useState<'console' | 'comparison'>('console');
  const [comparisonChannelStatus, setComparisonChannelStatus] = useState<'idle' | 'waiting' | 'active' | 'stale'>('idle');
  const [comparisonLagSec, setComparisonLagSec] = useState<number | null>(null);

  const resolveComparisonStatus = (taskStatus: string, comparisonSeq: number, comparisonUpdatedAt?: number) => {
    if (!['running', 'starting'].includes(taskStatus)) return { status: 'idle' as const, lagSec: null as number | null };
    if (!comparisonSeq || !comparisonUpdatedAt) return { status: 'waiting' as const, lagSec: null as number | null };
    const lagSec = Math.max(0, Math.floor(Date.now() / 1000 - comparisonUpdatedAt));
    return lagSec <= 20
      ? { status: 'active' as const, lagSec }
      : { status: 'stale' as const, lagSec };
  };

  useEffect(() => {
    let disposed = false;
    let request: AbortController | null = null;
    let firstSnapshot = true;
    let taskId: string | null = null;
    cursorRef.current = { logs: 0, chart: 0, comparison: 0 };
    const poll = async () => {
      if (disposed || request) return;
      const controller = new AbortController();
      request = controller;
      try {
        const requestedCursor = { ...cursorRef.current };
        let data = await DataService.getTaskStatus(
          requestedCursor.logs,
          requestedCursor.chart,
          requestedCursor.comparison,
          undefined,
          controller.signal,
        );
        if (disposed) return;
        const taskChanged = taskId !== (data.task_id || null);
        if (taskChanged && !firstSnapshot) {
          data = await DataService.getTaskStatus(0, 0, 0, data.task_id || undefined, controller.signal);
          if (disposed) return;
        }
        taskId = data.task_id || null;
        const nextCursor = data.cursors || requestedCursor;
        cursorRef.current = {
          logs: nextCursor.logs ?? requestedCursor.logs,
          chart: nextCursor.chart ?? requestedCursor.chart,
          comparison: nextCursor.comparison ?? requestedCursor.comparison
        };
        const comparisonSeq = nextCursor.comparison ?? requestedCursor.comparison ?? 0;
        const comparisonStatus = resolveComparisonStatus(
          data.stats?.status || 'idle',
          comparisonSeq,
          data.comparison_updated_at
        );
        setComparisonChannelStatus(comparisonStatus.status);
        setComparisonLagSec(comparisonStatus.lagSec);
        
        const reset = firstSnapshot || taskChanged;
        setTaskState(prev => mergeTaskStatus(prev, data, requestedCursor, reset));
        firstSnapshot = false;
      } catch (e) {
        if (!controller.signal.aborted) console.error("Polling error", e);
      } finally {
        if (request === controller) request = null;
      }
    };
    intervalRef.current = setInterval(poll, 1000);
    void poll();
    return () => {
      disposed = true;
      request?.abort();
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const comparisonStatusMeta = (() => {
    if (comparisonChannelStatus === 'active') {
      return {
        label: `ACTIVE${comparisonLagSec !== null ? ` · ${comparisonLagSec}s` : ''}`,
        className: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10'
      };
    }
    if (comparisonChannelStatus === 'waiting') {
      return {
        label: 'WAITING',
        className: 'text-amber-300 border-amber-500/30 bg-amber-500/10'
      };
    }
    if (comparisonChannelStatus === 'stale') {
      return {
        label: `DELAYED${comparisonLagSec !== null ? ` · ${comparisonLagSec}s` : ''}`,
        className: 'text-rose-300 border-rose-500/30 bg-rose-500/10'
      };
    }
    return {
      label: 'IDLE',
      className: 'text-slate-300 border-slate-600/40 bg-slate-700/20'
    };
  })();

  return (
    <div className="flex flex-col h-screen bg-slate-950 p-6 space-y-4 overflow-hidden">
      {/* Header */}
      <div className="flex justify-between items-center bg-slate-900/50 border border-slate-800 p-4 rounded-xl backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-tr from-primary to-secondary flex items-center justify-center shadow-lg shadow-primary/20">
            <Activity className="text-white" size={20} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight">
              AiNiee <span className="text-primary">{t('ui_monitor_title') || 'Monitor'}</span>
            </h1>
            <p className="text-xs text-slate-500 font-medium uppercase tracking-widest">{t('ui_monitor_subtitle') || 'Real-time Performance Metrics'}</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          {taskState.isRunning ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs font-bold animate-pulse">
              <Loader2 size={14} className="animate-spin" />
              {t('ui_system_active') || 'SYSTEM ACTIVE'}
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800 border border-slate-700 text-slate-500 text-xs font-bold">
              <div className="w-2 h-2 rounded-full bg-slate-600" />
              {t('ui_system_idle') || 'SYSTEM IDLE'}
            </div>
          )}
          
          <button 
            onClick={() => window.location.hash = '/'}
            className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors border border-transparent hover:border-slate-700"
            title={t('ui_go_to_dashboard') || 'Go to Dashboard'}
          >
            <LayoutDashboard size={20} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      {showDetailed && (
        <div className="flex gap-2 border-b border-slate-800 px-2">
          <button 
            onClick={() => setActiveTab('console')}
            className={`px-6 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${activeTab === 'console' ? 'border-primary text-primary' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
          >
            <Activity size={14} />
            {t('ui_tab_console') || 'METRICS & CONSOLE'}
          </button>
          <button 
            onClick={() => setActiveTab('comparison')}
            className={`px-6 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${activeTab === 'comparison' ? 'border-primary text-primary' : 'border-transparent text-slate-500 hover:text-slate-300'}`}
          >
            <LayoutDashboard size={14} />
            {t('ui_tab_comparison') || 'BILINGUAL VIEW'}
          </button>
        </div>
      )}

      {/* Content Section */}
      <div className="flex-1 min-h-0 flex flex-col space-y-4">
        {(!showDetailed || activeTab === 'console') ? (
            <div className="flex-1 flex flex-col space-y-4 min-h-0 overflow-y-auto">
                <StatsPanel data={taskState.chartData} stats={taskState.stats} />
                <Terminal logs={taskState.logs} height="flex-1" />
            </div>
        ) : (
            <div className="flex-1 flex flex-col space-y-4 min-h-0 overflow-y-auto">
                <StatsPanel data={taskState.chartData} stats={taskState.stats} variant="compact" />
                <div className="px-3 py-2 rounded-lg border border-slate-800 bg-slate-900/40 flex items-center justify-between">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Comparison Channel</span>
                    <span className={`px-2 py-1 rounded border text-[10px] font-mono uppercase tracking-wide ${comparisonStatusMeta.className}`}>
                        {comparisonStatusMeta.label}
                    </span>
                </div>
                <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 min-h-0">
                    {/* Source Pane */}
                    <div className="flex flex-col bg-slate-900/40 border border-magenta/20 rounded-xl overflow-hidden backdrop-blur-sm shadow-inner shadow-magenta/5 min-h-[300px]">
                        <div className="px-4 py-2 bg-magenta/10 border-b border-magenta/20 flex justify-between items-center">
                            <span className="text-[10px] font-bold text-magenta uppercase tracking-widest">Original Source</span>
                            <span className="text-[10px] text-slate-500 font-mono">{(taskState.comparison?.source?.split('\n').length || 0)} Lines</span>
                        </div>
                        <div className="flex-1 p-4 overflow-y-auto font-mono text-sm text-slate-300 leading-relaxed scrollbar-thin scrollbar-thumb-magenta/20 whitespace-pre-wrap">
                            {taskState.comparison?.source || <span className="text-slate-600 italic">Waiting for text...</span>}
                        </div>
                    </div>

                    {/* Translation Pane */}
                    <div className="flex flex-col bg-slate-900/40 border border-primary/20 rounded-xl overflow-hidden backdrop-blur-sm shadow-inner shadow-primary/5 min-h-[300px]">
                        <div className="px-4 py-2 bg-primary/10 border-b border-primary/20 flex justify-between items-center">
                            <span className="text-[10px] font-bold text-primary uppercase tracking-widest">Translation Output</span>
                            <span className="text-[10px] text-slate-500 font-mono">{(taskState.comparison?.translation?.split('\n').length || 0)} Lines</span>
                        </div>
                        <div className="flex-1 p-4 overflow-y-auto font-mono text-sm text-primary-light leading-relaxed scrollbar-thin scrollbar-thumb-primary/20 whitespace-pre-wrap">
                            {taskState.comparison?.translation || <span className="text-slate-600 italic animate-pulse">Processing batch...</span>}
                        </div>
                    </div>
                </div>
            </div>
        )}
      </div>

      {/* Footer info */}
      <div className="flex justify-between items-center text-[10px] text-slate-600 font-mono px-2 uppercase tracking-tighter">
        <span>&copy; 2026 AiNiee Project</span>
        <div className="flex gap-4">
          <span className="truncate max-w-[200px]">{taskState.stats?.currentFile || t('ui_no_file_active') || 'No file active'}</span>
          <span>S-Rate: <span className="text-green-500/80">{(taskState.stats?.successRate || 0).toFixed(1)}%</span></span>
          <span>E-Rate: <span className="text-red-500/80">{(taskState.stats?.errorRate || 0).toFixed(1)}%</span></span>
          <span>RPM: {taskState.stats?.rpm.toFixed(2)}</span>
          <span>TPM: {taskState.stats?.tpm.toFixed(2)}k</span>
        </div>
      </div>
    </div>
  );
};
