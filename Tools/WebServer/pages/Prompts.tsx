import React, { useState, useEffect } from 'react';
import { Save, Plus, Trash2, FileText, Search, RefreshCw, ChevronRight, AlertTriangle, Check, X, Edit3, Sparkles } from 'lucide-react';
import { DataService } from '../services/DataService';
import { useI18n } from '../contexts/I18nContext';
import { useGlobal } from '../contexts/GlobalContext';

export const Prompts: React.FC = () => {
    const { t } = useI18n();
    const { config, setConfig, activeTheme } = useGlobal();
    
    const [categories, setCategories] = useState<string[]>([]);
    const [activeCategory, setActiveCategory] = useState<string>('');
    const [prompts, setPrompts] = useState<string[]>([]);
    const [selectedPrompt, setSelectedPrompt] = useState<string | null>(null);
    const [content, setContent] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [filter, setFilter] = useState('');
    
    const [isCreating, setIsCreating] = useState(false);
    const [newName, setNewName] = useState('');

    const elysiaActive = activeTheme === 'elysia';

    useEffect(() => {
        loadCategories();
    }, []);

    useEffect(() => {
        if (activeCategory) {
            loadPrompts(activeCategory);
            setSelectedPrompt(null);
            setContent('');
        }
    }, [activeCategory]);

    const loadCategories = async () => {
        try {
            const cats = await DataService.listPromptCategories();
            setCategories(cats);
            if (cats.length > 0 && !activeCategory) {
                setActiveCategory(cats.includes('Translate') ? 'Translate' : cats[0]);
            }
        } catch (e) {
            console.error("Failed to load categories", e);
        }
    };

    const loadPrompts = async (cat: string) => {
        setLoading(true);
        try {
            const list = await DataService.listPrompts(cat);
            setPrompts(list);
        } catch (e) {
            console.error("Failed to load prompts", e);
        } finally {
            setLoading(false);
        }
    };

    const loadPromptContent = async (filename: string) => {
        setLoading(true);
        try {
            const data = await DataService.getPromptContent(activeCategory, filename);
            setContent(data);
            setSelectedPrompt(filename);
            setIsCreating(false);
        } catch (e) {
            console.error("Failed to load prompt content", e);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        if (!selectedPrompt) return;
        setSaving(true);
        try {
            await DataService.savePromptContent(activeCategory, selectedPrompt, content);
            alert(t('msg_saved') || 'Saved successfully');
        } catch (e) {
            alert('Save failed');
        } finally {
            setSaving(false);
        }
    };

    const handleApply = async () => {
        if (!selectedPrompt || !config) return;
        const key = activeCategory === 'Polishing' ? 'polishing_prompt_selection' : 'translation_prompt_selection';
        const newConfig = {
            ...config,
            [key]: {
                last_selected_id: selectedPrompt.replace('.txt', ''),
                prompt_content: content
            }
        };
        try {
            await DataService.saveConfig(newConfig);
            setConfig(newConfig);
            alert(t('msg_prompt_updated') || 'Prompt applied');
        } catch (e) {
            alert('Apply failed');
        }
    };

    const handleCreate = async () => {
        if (!newName.trim()) return;
        const filename = newName.endsWith('.txt') ? newName : newName + '.txt';
        try {
            await DataService.savePromptContent(activeCategory, filename, '');
            await loadPrompts(activeCategory);
            setIsCreating(false);
            setNewName('');
            loadPromptContent(filename);
        } catch (e) {
            alert('Create failed');
        }
    };

    const isSystem = activeCategory === 'System';
    const isSelectionTarget = ['Translate', 'Polishing'].includes(activeCategory);

    const filteredPrompts = prompts.filter(p => p.toLowerCase().includes(filter.toLowerCase()));

    const getThemeColorClass = () => {
        switch(activeTheme) {
            case 'elysia': return 'text-pink-500';
            case 'herrscher_of_human': return 'text-[#ff4d6d]';
            default: return 'text-primary';
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-120px)] max-w-7xl mx-auto space-y-4">
            <div className="flex justify-between items-center border-b border-slate-800 pb-4">
                <div className="flex items-center gap-3">
                    <Edit3 className={getThemeColorClass()} size={24} />
                    <h1 className="text-2xl font-bold text-white">{t('menu_prompt_features') || 'Prompt Management'}</h1>
                </div>
                {selectedPrompt && !isSystem && (
                    <div className="flex gap-3">
                        {isSelectionTarget && (
                            <button 
                                onClick={handleApply}
                                className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-primary border border-primary/30 px-4 py-2 rounded-lg font-bold transition-all"
                            >
                                <Check size={18} /> {t('opt_apply') || 'Apply'}
                            </button>
                        )}
                        <button 
                            onClick={handleSave}
                            disabled={saving}
                            className="flex items-center gap-2 bg-primary hover:bg-cyan-400 text-slate-900 px-4 py-2 rounded-lg font-bold transition-all shadow-lg shadow-primary/20"
                        >
                            {saving ? <RefreshCw size={18} className="animate-spin" /> : <Save size={18} />}
                            {t('ui_settings_save') || 'Save'}
                        </button>
                    </div>
                )}
            </div>

            <div className="flex flex-1 overflow-hidden gap-4">
                {/* Categories & Files Sidebar */}
                <div className="w-72 flex flex-col gap-4 overflow-hidden">
                    {/* Categories */}
                    <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-2 flex flex-wrap gap-1">
                        {categories.map(cat => (
                            <button
                                key={cat}
                                onClick={() => setActiveCategory(cat)}
                                className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${activeCategory === cat ? 'bg-primary text-slate-900' : 'text-slate-400 hover:bg-slate-800'}`}
                            >
                                {cat}
                            </button>
                        ))}
                    </div>

                    {/* File List */}
                    <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-xl flex flex-col overflow-hidden">
                        <div className="p-3 border-b border-slate-800 flex flex-col gap-2">
                            <div className="relative">
                                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                                <input 
                                    type="text" 
                                    placeholder="Filter..." 
                                    value={filter}
                                    onChange={e => setFilter(e.target.value)}
                                    className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white focus:border-primary outline-none"
                                />
                            </div>
                            {!isSystem && (
                                <button 
                                    onClick={() => setIsCreating(true)}
                                    className="w-full flex items-center justify-center gap-2 py-1.5 bg-primary/10 border border-primary/20 text-primary rounded-lg hover:bg-primary/20 transition-all text-xs font-bold"
                                >
                                    <Plus size={14} /> {t('menu_prompt_create') || 'New Prompt'}
                                </button>
                            )}
                        </div>

                        <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
                            {isCreating && (
                                <div className="p-2 bg-slate-800 rounded-lg border border-primary/30 flex flex-col gap-2 animate-in fade-in slide-in-from-top-2">
                                    <input 
                                        autoFocus
                                        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white outline-none"
                                        placeholder="Prompt name..."
                                        value={newName}
                                        onChange={e => setNewName(e.target.value)}
                                        onKeyDown={e => e.key === 'Enter' && handleCreate()}
                                    />
                                    <div className="flex justify-end gap-2">
                                        <button onClick={() => setIsCreating(false)} className="p-1 hover:text-red-400"><X size={14}/></button>
                                        <button onClick={handleCreate} className="p-1 text-primary hover:text-cyan-300"><Check size={14}/></button>
                                    </div>
                                </div>
                            )}
                            {filteredPrompts.map(p => (
                                <button
                                    key={p}
                                    onClick={() => loadPromptContent(p)}
                                    className={`w-full flex items-center justify-between p-2.5 rounded-lg text-left text-xs transition-all group ${selectedPrompt === p ? 'bg-primary/10 border border-primary/30 text-primary font-bold' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-transparent'}`}
                                >
                                    <div className="flex items-center gap-2 truncate">
                                        <FileText size={14} className={selectedPrompt === p ? 'text-primary' : 'text-slate-500'} />
                                        <span className="truncate">{p.replace(/\.(txt|json)$/, '')}</span>
                                    </div>
                                    <ChevronRight size={12} className={`opacity-0 group-hover:opacity-100 transition-opacity ${selectedPrompt === p ? 'opacity-100' : ''}`} />
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Content Editor */}
                <div className="flex-1 bg-slate-900/50 border border-slate-800 rounded-xl flex flex-col overflow-hidden relative">
                    {loading && (
                        <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm z-10 flex items-center justify-center">
                            <RefreshCw className="animate-spin text-primary" size={32} />
                        </div>
                    )}
                    
                    {selectedPrompt ? (
                        <>
                            <div className="p-3 border-b border-slate-800 flex justify-between items-center bg-slate-900/30">
                                <div className="flex flex-col">
                                    <span className="text-[10px] text-slate-500 uppercase font-black tracking-widest">{activeCategory}</span>
                                    <span className="text-sm font-bold text-white">{selectedPrompt}</span>
                                </div>
                                {isSystem && (
                                    <div className="flex items-center gap-2 px-3 py-1 bg-red-500/10 border border-red-500/20 rounded-full">
                                        <AlertTriangle size={12} className="text-red-500" />
                                        <span className="text-[10px] font-bold text-red-500 uppercase tracking-tighter">{t('label_readonly') || 'Read Only'}</span>
                                    </div>
                                )}
                            </div>
                            <textarea
                                value={content}
                                onChange={e => setContent(e.target.value)}
                                readOnly={isSystem}
                                className={`flex-1 w-full bg-slate-950 p-6 font-mono text-sm leading-relaxed outline-none transition-all ${isSystem ? 'text-slate-400 cursor-default' : 'text-slate-200 focus:bg-slate-950/50'}`}
                                placeholder="Prompt content..."
                            />
                        </>
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-slate-500 space-y-4">
                            <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center">
                                <FileText size={32} />
                            </div>
                            <p className="text-sm font-medium">Select a prompt to view or edit</p>
                            {elysiaActive && <Sparkles className="text-pink-400 animate-pulse" size={24} />}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};
