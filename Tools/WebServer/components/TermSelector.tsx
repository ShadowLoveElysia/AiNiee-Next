import React, { useState, useEffect } from 'react';
import { RefreshCw, Save, Edit2, Play, CheckCircle2, Trash2, Plus, BookOpen, AlertTriangle } from 'lucide-react';
import { TermItem, TermOption } from '../types';
import { useI18n } from '../contexts/I18nContext';

interface TermSelectorProps {
    terms: TermItem[];
    onSaveAll: (terms: TermItem[]) => void;
    onSaveSingle: (term: TermItem) => void;
    onRetry: (term: TermItem) => Promise<TermOption | null>;
    onCancel: () => void;
    themeColor: string;
    isLightCityTheme: boolean;
}

export const TermSelector: React.FC<TermSelectorProps> = ({
    terms: initialTerms,
    onSaveAll,
    onSaveSingle,
    onRetry,
    onCancel,
    themeColor,
    isLightCityTheme
}) => {
    const { t } = useI18n();
    const [terms, setTerms] = useState<TermItem[]>(initialTerms);
    const [currentRow, setCurrentRow] = useState<number>(0);
    const [isTranslatingAll, setIsTranslatingAll] = useState(false);
    const [processingRows, setProcessingRows] = useState<Set<number>>(new Set());

    // Auto-start first term translation if no options
    useEffect(() => {
        if (terms.length > 0 && terms[0].options.length === 0) {
            handleRetry(0);
        }
    }, []);

    const setRowProcessing = (idx: number, isProcessing: boolean) => {
        setProcessingRows(prev => {
            const next = new Set(prev);
            if (isProcessing) next.add(idx);
            else next.delete(idx);
            return next;
        });
    };

    const handleRetry = async (idx: number) => {
        // Get current item directly from state
        const currentItem = terms[idx];
        if (!currentItem) return;

        setRowProcessing(idx, true);
        try {
            // Call the API with current item
            const newOption = await onRetry(currentItem);

            if (newOption && newOption.dst) {
                // Check if this translation already exists
                const existingDsts = currentItem.options.map(o => o.dst);
                if (existingDsts.includes(newOption.dst)) {
                    alert(t('term_selector_duplicate_hint') || '模型返回的译文和当前译文一致，可能需要人工处理');
                    return;
                }

                setTerms(prevTerms => {
                    const next = [...prevTerms];
                    const item = { ...next[idx] };
                    // Add the new option and select it
                    item.options = [...item.options, newOption];
                    item.selected_index = item.options.length - 1;
                    next[idx] = item;
                    return next;
                });
            }
        } catch (e) {
            console.error("Retry failed for index", idx, e);
        } finally {
            setRowProcessing(idx, false);
        }
    };

    const handleTranslateAll = async () => {
        if (isTranslatingAll) return;
        setIsTranslatingAll(true);
        
        // Identify which rows need translation at the start
        const pendingIndices = terms
            .map((t, i) => (t.options.length === 0 && !t.saved ? i : -1))
            .filter(i => i !== -1);

        for (const idx of pendingIndices) {
            setCurrentRow(idx);
            await handleRetry(idx);
        }
        
        setIsTranslatingAll(false);
    };

    const handleSaveSingle = async (idx: number) => {
        const item = terms[idx];
        const selected = item.options[item.selected_index];
        if (!selected || !selected.dst) {
            alert(t('term_selector_waiting'));
            return;
        }
        
        setRowProcessing(idx, true);
        try {
            await onSaveSingle(item);
            setTerms(prev => {
                const next = [...prev];
                next[idx] = { ...next[idx], saved: true };
                return next;
            });
        } catch (e) {
            alert("Save failed");
        } finally {
            setRowProcessing(idx, false);
        }
    };

    const handleOptionEdit = (termIdx: number, optIdx: number, newDst: string) => {
        setTerms(prev => {
            const next = [...prev];
            const updatedOptions = [...next[termIdx].options];
            updatedOptions[optIdx] = { ...updatedOptions[optIdx], dst: newDst };
            next[termIdx] = { ...next[termIdx], options: updatedOptions };
            return next;
        });
    };

    const handleAddManual = (termIdx: number) => {
        setTerms(prev => {
            const next = [...prev];
            const updatedItem = { ...next[termIdx] };
            updatedItem.options = [...updatedItem.options, { dst: '', info: '手动' }];
            updatedItem.selected_index = updatedItem.options.length - 1;
            next[termIdx] = updatedItem;
            return next;
        });
    };

    return (
        <div className="space-y-4 animate-in fade-in duration-300">
            {/* API Hint Warning */}
            <div className={`p-3 rounded-lg border flex items-start gap-3 ${isLightCityTheme ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-yellow-900/20 border-yellow-700/50 text-yellow-300'}`}>
                <AlertTriangle size={18} className="shrink-0 mt-0.5" />
                <span className="text-sm">{t('term_selector_api_hint')}</span>
            </div>

            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4">
                <div>
                    <h3 className={`text-xl font-bold ${isLightCityTheme ? 'text-pink-700' : 'text-white'}`}>{t('term_selector_title')}</h3>
                    <p className="text-sm text-slate-500 mt-1">{t('term_selector_hint')}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                    <button onClick={handleTranslateAll} disabled={isTranslatingAll}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-sm transition-all hover:scale-105 shadow-lg disabled:opacity-50 ${
                            isTranslatingAll ? 'bg-slate-700 text-slate-400' : 'bg-blue-600 text-white hover:bg-blue-500 shadow-blue-900/20'
                        }`}>
                        {isTranslatingAll ? <RefreshCw size={18} className="animate-spin" /> : <Play size={18} />}
                        {isTranslatingAll ? t('term_selector_translating_all') : t('term_selector_translate_all')}
                    </button>
                    <button onClick={() => onSaveAll(terms.filter(t => !t.saved && t.options.length > 0))}
                        className="flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white rounded-lg font-bold text-sm hover:bg-green-500 hover:scale-105 transition-all shadow-lg shadow-green-900/20">
                        <CheckCircle2 size={18} />
                        {t('term_selector_save_all')}
                    </button>
                    <button onClick={onCancel}
                        className="px-5 py-2.5 bg-slate-800 text-slate-300 rounded-lg font-bold text-sm hover:bg-slate-700 transition-all border border-slate-700">
                        {t('term_selector_cancel')}
                    </button>
                </div>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40 backdrop-blur-sm">
                <table className="w-full text-sm text-left border-collapse">
                    <thead className={`${isLightCityTheme ? 'bg-pink-50 text-pink-700' : 'bg-slate-900 text-slate-400'}`}>
                        <tr>
                            <th className="p-4 w-12 border-b border-slate-800">#</th>
                            <th className="p-4 w-48 border-b border-slate-800">{t('term_selector_header_term')}</th>
                            <th className="p-4 w-32 border-b border-slate-800">{t('term_selector_header_type')}</th>
                            <th className="p-4 w-72 border-b border-slate-800">{t('ai_glossary_info')}</th>
                            <th className="p-4 border-b border-slate-800">{t('term_selector_header_options')}</th>
                            <th className="p-4 w-32 border-b border-slate-800 text-center">{t('term_selector_header_action')}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                        {terms.map((item, idx) => (
                            <tr key={idx} 
                                onClick={() => setCurrentRow(idx)}
                                className={`transition-all cursor-pointer group ${
                                    currentRow === idx ? (isLightCityTheme ? 'bg-pink-100/50' : 'bg-primary/5') : 'hover:bg-slate-800/20'
                                }`}>
                                <td className={`p-4 border-r border-slate-800/50 text-center font-mono ${item.saved ? 'text-green-500 font-bold' : 'text-slate-500'}`}>
                                    {processingRows.has(idx) ? <RefreshCw size={16} className="animate-spin inline" /> : (item.saved ? <CheckCircle2 size={16} className="inline" /> : idx + 1)}
                                </td>
                                <td className="p-4">
                                    <input 
                                        type="text" 
                                        value={item.src} 
                                        onClick={(e) => e.stopPropagation()}
                                        onChange={(e) => {
                                            const newVal = e.target.value;
                                            setTerms(prev => {
                                                const next = [...prev];
                                                next[idx] = { ...next[idx], src: newVal };
                                                return next;
                                            });
                                        }}
                                        className="bg-transparent border-none outline-none focus:bg-slate-950/80 px-2 py-1 rounded w-full text-slate-100 font-medium border-b border-transparent focus:border-primary/30 transition-all"
                                    />
                                </td>
                                <td className="p-4">
                                    <input 
                                        type="text" 
                                        value={item.type} 
                                        onClick={(e) => e.stopPropagation()}
                                        onChange={(e) => {
                                            const newVal = e.target.value;
                                            setTerms(prev => {
                                                const next = [...prev];
                                                next[idx] = { ...next[idx], type: newVal };
                                                return next;
                                            });
                                        }}
                                        className="bg-transparent border-none outline-none focus:bg-slate-950/80 px-2 py-1 rounded w-full text-slate-400 text-xs border-b border-transparent focus:border-primary/30 transition-all"
                                    />
                                </td>
                                <td className="p-4 align-top">
                                    <textarea
                                        value={item.analysis_info || 'null'}
                                        onClick={(e) => e.stopPropagation()}
                                        onChange={(e) => {
                                            const newVal = e.target.value;
                                            setTerms(prev => {
                                                const next = [...prev];
                                                next[idx] = { ...next[idx], analysis_info: newVal };
                                                return next;
                                            });
                                        }}
                                        className="bg-transparent border-none outline-none focus:bg-slate-950/80 px-2 py-1 rounded w-full min-h-[42px] resize-y text-slate-400 text-xs border-b border-transparent focus:border-primary/30 transition-all"
                                    />
                                </td>
                                <td className="p-4">
                                    <div className="flex flex-wrap gap-3 items-center">
                                        {item.options.length === 0 ? (
                                            <div className="flex items-center gap-2 text-slate-600 italic text-xs py-2">
                                                <RefreshCw size={12} className="animate-spin" />
                                                {t('term_selector_waiting')}
                                            </div>
                                        ) : (
                                            item.options.map((opt, optIdx) => (
                                                <div key={optIdx} className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border transition-all ${
                                                    item.selected_index === optIdx 
                                                        ? 'border-primary bg-primary/10 text-primary shadow-[0_0_15px_rgba(6,182,212,0.3)] ring-1 ring-primary/40' 
                                                        : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:bg-slate-800/50'
                                                }`}>
                                                    <input type="radio" 
                                                        className="w-4 h-4 cursor-pointer accent-primary" 
                                                        name={`term-${idx}`} 
                                                        checked={item.selected_index === optIdx}
                                                        onChange={() => {
                                                            setTerms(prev => {
                                                                const next = [...prev];
                                                                next[idx] = { ...next[idx], selected_index: optIdx };
                                                                return next;
                                                            });
                                                        }}
                                                    />
                                                    <input 
                                                        type="text" 
                                                        value={opt.dst}
                                                        placeholder="..."
                                                        onClick={(e) => e.stopPropagation()}
                                                        onChange={(e) => handleOptionEdit(idx, optIdx, e.target.value)}
                                                        className="bg-transparent border-none font-bold text-base outline-none min-w-[120px] focus:bg-slate-950/50 rounded px-1 transition-all"
                                                    />
                                                    <div className="flex items-center border-l border-slate-700/50 ml-1 pl-2 gap-2">
                                                        <select 
                                                            value={opt.info}
                                                            onChange={(e) => {
                                                                const newVal = e.target.value;
                                                                setTerms(prev => {
                                                                    const next = [...prev];
                                                                    const opts = [...next[idx].options];
                                                                    opts[optIdx] = { ...opts[optIdx], info: newVal };
                                                                    next[idx] = { ...next[idx], options: opts };
                                                                    return next;
                                                                });
                                                            }}
                                                            className="bg-transparent border-none text-xs font-bold opacity-70 outline-none cursor-pointer hover:opacity-100 accent-primary"
                                                        >
                                                            <option value="音译">音</option>
                                                            <option value="直译">直</option>
                                                            <option value="意译">意</option>
                                                            <option value="不译">不</option>
                                                            <option value="手动">手</option>
                                                        </select>
                                                        {item.options.length > 1 && (
                                                            <button 
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    setTerms(prev => {
                                                                        const next = [...prev];
                                                                        const opts = [...next[idx].options];
                                                                        opts.splice(optIdx, 1);
                                                                        let sel = next[idx].selected_index;
                                                                        if (sel >= opts.length) sel = Math.max(0, opts.length - 1);
                                                                        next[idx] = { ...next[idx], options: opts, selected_index: sel };
                                                                        return next;
                                                                    });
                                                                }}
                                                                className="text-slate-500 hover:text-red-400 transition-colors p-1 rounded-md hover:bg-red-400/10"
                                                                title="删除此选项"
                                                            >
                                                                <Trash2 size={14} />
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                        {!item.saved && (
                                            <button 
                                                onClick={(e) => { e.stopPropagation(); handleAddManual(idx); }}
                                                className="p-2.5 rounded-xl border border-dashed border-slate-700 text-slate-500 hover:border-primary hover:text-primary hover:bg-primary/5 transition-all"
                                                title={t('term_selector_manual_add')}
                                            >
                                                <Plus size={18} />
                                            </button>
                                        )}
                                    </div>
                                </td>
                                <td className="p-4">
                                    <div className="flex items-center justify-center gap-2 opacity-40 group-hover:opacity-100 transition-opacity">
                                        <button onClick={(e) => { e.stopPropagation(); handleRetry(idx); }} 
                                            disabled={processingRows.has(idx) || isTranslatingAll}
                                            className="p-2.5 hover:bg-primary/20 hover:text-primary rounded-xl transition-all disabled:opacity-30 border border-transparent hover:border-primary/30" 
                                            title={t('term_selector_retry_tooltip')}>
                                            <RefreshCw size={18} className={processingRows.has(idx) ? 'animate-spin' : ''} />
                                        </button>
                                        <button onClick={(e) => { e.stopPropagation(); handleSaveSingle(idx); }} 
                                            disabled={processingRows.has(idx)}
                                            className={`p-2.5 rounded-xl transition-all border ${
                                                item.saved 
                                                    ? 'text-green-500 bg-green-500/10 border-green-500/30' 
                                                    : 'hover:bg-green-500/20 hover:text-green-400 border-transparent hover:border-green-500/30'
                                            }`} title={t('term_selector_save_tooltip')}>
                                            {processingRows.has(idx) ? <RefreshCw size={18} className="animate-spin" /> : <Save size={18} />}
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div className="flex justify-between items-center text-sm text-slate-500 px-3 py-2 bg-slate-900/20 rounded-lg">
                <div className="flex items-center gap-4">
                    <span className="flex items-center gap-1.5"><BookOpen size={14} /> {t('term_selector_summary').replace('{}', terms.length.toString()).replace('{}', terms.filter(t => t.saved).length.toString())}</span>
                </div>
                <div className="flex items-center gap-1.5 opacity-70 italic"><Edit2 size={14} /> {t('term_selector_edit_hint')}</div>
            </div>
        </div>
    );
};
