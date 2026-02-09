import React, { useState, useEffect, useRef } from 'react';
import { Save, Plus, Trash2, BookOpen, Ban, AlertTriangle, RefreshCw, Search, ToggleLeft, ToggleRight, Download, Upload, History, Users, Map, PenTool, Languages, FileJson, ChevronDown, Sparkles, Play, Square } from 'lucide-react';
import { GlossaryItem, ExclusionItem, CharacterizationItem, TranslationExampleItem } from '../types';
import { DataService } from '../services/DataService';
import { useI18n } from '../contexts/I18nContext';
import { useGlobal } from '../contexts/GlobalContext';

type TabType = 'glossary' | 'exclusion' | 'characterization' | 'world' | 'style' | 'example' | 'ai_glossary';

export const Rules: React.FC = () => {
    const { t } = useI18n();
    const { config, setConfig, activeTheme } = useGlobal(); // Access global config and active theme
    const [activeTab, setActiveTab] = useState<TabType>('glossary');

    const getThemeColor = () => {
        switch(activeTheme) {
            case 'elysia': return '#ff6699';
            case 'herrscher_of_human': return '#ff8fa3';
            case 'eden': return '#d4af37';
            case 'mobius': return '#00ff41';
            case 'pardofelis': return '#e6b8a2';
            case 'griseo': return '#a2c2e1';
            case 'kevin': return '#00f2ff';
            case 'kalpas': return '#ff4d4d';
            case 'aponia': return '#9d81ba';
            case 'villv': return '#c5a059';
            case 'su': return '#88a070';
            case 'sakura': return '#f4b0c7';
            case 'kosma': return '#1a2a4a';
            case 'hua': return '#d4a017';
            default: return '#06b6d4';
        }
    };
    
    const themeColor = getThemeColor();
    
    // Data State
    const [glossary, setGlossary] = useState<GlossaryItem[]>([]);
    const [exclusion, setExclusion] = useState<ExclusionItem[]>([]);
    const [characterization, setCharacterization] = useState<CharacterizationItem[]>([]);
    const [worldBuilding, setWorldBuilding] = useState<string>("");
    const [writingStyle, setWritingStyle] = useState<string>("");
    const [translationExample, setTranslationExample] = useState<TranslationExampleItem[]>([]);
    
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [hasDraft, setHasDraft] = useState(false);
    
    // Profile State
    const [profiles, setProfiles] = useState<string[]>([]);
    const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
    
    // Filter State
    const [filter, setFilter] = useState('');

    // AI Glossary Analysis State
    const [aiInputPath, setAiInputPath] = useState('');
    const [aiPercent, setAiPercent] = useState(30);
    const [aiLines, setAiLines] = useState<number | undefined>(undefined);
    const [aiStatus, setAiStatus] = useState<any>({ status: 'idle', progress: 0, total: 0, message: '', results: [] });
    const [aiMinFreq, setAiMinFreq] = useState(2);
    const [aiFilename, setAiFilename] = useState('auto_glossary');
    const [aiLogs, setAiLogs] = useState<string[]>([]);
    const [aiUseTempConfig, setAiUseTempConfig] = useState(false);
    const [aiTempPlatform, setAiTempPlatform] = useState('');
    const [aiTempApiKey, setAiTempApiKey] = useState('');
    const [aiTempApiUrl, setAiTempApiUrl] = useState('');
    const [aiTempModel, setAiTempModel] = useState('');
    const [aiTempThreads, setAiTempThreads] = useState<number>(5);

    // Refs
    const draftTimerRef = useRef<any>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        loadData();
        loadProfiles();
        checkDrafts();
    }, []);

    // 切换到AI术语分析标签页时加载当前状态
    useEffect(() => {
        if (activeTab === 'ai_glossary') {
            const loadAnalysisStatus = async () => {
                try {
                    const status = await DataService.getAnalysisStatus();
                    setAiStatus(status);
                    if (status.logs && Array.isArray(status.logs)) {
                        setAiLogs(status.logs);
                    }
                    // 如果正在运行，继续轮询
                    if (status.status === 'running') {
                        pollAnalysisStatus();
                    }
                } catch (e) {
                    console.error("Failed to load analysis status", e);
                }
            };
            loadAnalysisStatus();
        }
    }, [activeTab]);

    const loadProfiles = async () => {
        try {
            const list = await DataService.getRulesProfiles();
            setProfiles(list);
        } catch (e) {
            console.error("Failed to load rules profiles", e);
        }
    };

    const handleProfileSwitch = async (profileName: string) => {
        if (config?.active_rules_profile === profileName) return;
        setLoading(true);
        try {
            const newConfig = await DataService.switchRulesProfile(profileName);
            setConfig(newConfig);
            // Reload data for the new profile
            await loadData(); 
            setIsProfileMenuOpen(false);
        } catch (e) {
            alert("Failed to switch rules profile");
        } finally {
            setLoading(false);
        }
    };

    const loadData = async () => {
        setLoading(true);
        try {
            const [g, e, c, w, s, ex] = await Promise.all([
                DataService.getGlossary(),
                DataService.getExclusion(),
                DataService.getCharacterization(),
                DataService.getWorldBuilding(),
                DataService.getWritingStyle(),
                DataService.getTranslationExample()
            ]);
            setGlossary(g || []);
            setExclusion(e || []);
            setCharacterization(c || []);
            setWorldBuilding(w || "");
            setWritingStyle(s || "");
            setTranslationExample(ex || []);
        } catch (error) {
            console.error("Failed to load rules", error);
        } finally {
            setLoading(false);
        }
    };

    const checkDrafts = async () => {
        try {
            const drafts = await Promise.all([
                DataService.getGlossaryDraft(),
                DataService.getExclusionDraft(),
                DataService.getCharacterizationDraft(),
                DataService.getWorldBuildingDraft(),
                DataService.getWritingStyleDraft(),
                DataService.getTranslationExampleDraft()
            ]);
            if (drafts.some(d => d && (Array.isArray(d) ? d.length > 0 : d.length > 0))) {
                setHasDraft(true);
            }
        } catch {}
    };

    const recoverDraft = async () => {
        if (!confirm(t('msg_recover_draft_confirm'))) return;
        try {
            const [gd, ed, cd, wd, sd, exd] = await Promise.all([
                DataService.getGlossaryDraft(),
                DataService.getExclusionDraft(),
                DataService.getCharacterizationDraft(),
                DataService.getWorldBuildingDraft(),
                DataService.getWritingStyleDraft(),
                DataService.getTranslationExampleDraft()
            ]);
            
            if (gd && gd.length > 0) setGlossary(gd);
            if (ed && ed.length > 0) setExclusion(ed);
            if (cd && cd.length > 0) setCharacterization(cd);
            if (wd) setWorldBuilding(wd);
            if (sd) setWritingStyle(sd);
            if (exd && exd.length > 0) setTranslationExample(exd);
            
            alert(t('msg_draft_recovered'));
        } catch (error) {
            alert("Failed to recover draft.");
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            switch (activeTab) {
                case 'glossary': await DataService.saveGlossary(glossary); break;
                case 'exclusion': await DataService.saveExclusion(exclusion); break;
                case 'characterization': await DataService.saveCharacterization(characterization); break;
                case 'world': await DataService.saveWorldBuilding(worldBuilding); break;
                case 'style': await DataService.saveWritingStyle(writingStyle); break;
                case 'example': await DataService.saveTranslationExample(translationExample); break;
            }
            if (config) {
                await DataService.saveConfig(config);
            }
            alert(t('msg_saved'));
        } catch (error) {
            console.error("Failed to save", error);
            alert("Save failed.");
        } finally {
            setSaving(false);
        }
    };

    const triggerDraftSave = () => {
        if (draftTimerRef.current) clearTimeout(draftTimerRef.current);
        draftTimerRef.current = setTimeout(async () => {
            switch (activeTab) {
                case 'glossary': await DataService.saveGlossaryDraft(glossary); break;
                case 'exclusion': await DataService.saveExclusionDraft(exclusion); break;
                case 'characterization': await DataService.saveCharacterizationDraft(characterization); break;
                case 'world': await DataService.saveWorldBuildingDraft(worldBuilding); break;
                case 'style': await DataService.saveWritingStyleDraft(writingStyle); break;
                case 'example': await DataService.saveTranslationExampleDraft(translationExample); break;
            }
            setHasDraft(true);
        }, 2000); // 2s debounce
    };

    const exportData = () => {
        let data: any;
        let filename = `${activeTab}.json`;
        let isText = false;

        switch (activeTab) {
            case 'glossary': data = glossary; break;
            case 'exclusion': data = exclusion; break;
            case 'characterization': data = characterization; break;
            case 'world': data = worldBuilding; filename = 'world_building.txt'; isText = true; break;
            case 'style': data = writingStyle; filename = 'writing_style.txt'; isText = true; break;
            case 'example': data = translationExample; filename = 'examples.json'; break;
        }

        const blob = new Blob([isText ? data : JSON.stringify(data, null, 4)], { type: isText ? 'text/plain' : 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const importData = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target?.result as string;
            
            try {
                if (activeTab === 'world' || activeTab === 'style') {
                    if (activeTab === 'world') setWorldBuilding(content);
                    else setWritingStyle(content);
                } else {
                    const json = JSON.parse(content);
                    if (Array.isArray(json)) {
                        switch (activeTab) {
                            case 'glossary': setGlossary(json); break;
                            case 'exclusion': setExclusion(json); break;
                            case 'characterization': setCharacterization(json); break;
                            case 'example': setTranslationExample(json); break;
                        }
                    } else {
                        alert(t('msg_import_error_list'));
                        return;
                    }
                }
                triggerDraftSave();
                alert(t('msg_import_success'));
            } catch (err) {
                alert(t('msg_import_error_parse'));
            }
        };
        reader.readAsText(file);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    // --- Toggle Handlers ---
    const toggleSwitch = (field: keyof typeof config) => {
        if (!config) return;
        // @ts-ignore
        setConfig({ ...config, [field]: !config[field] });
    };

    const isLocal = config?.target_platform && ["sakura", "localllm"].includes(config.target_platform.toLowerCase());
    const isOnlineOnlyTab = ['characterization', 'world', 'style', 'example'].includes(activeTab);

    // --- UI Helpers ---
    const TabButton = ({ id, icon: Icon, label }: { id: TabType, icon: any, label: string }) => {
        const isProtected = ['characterization', 'world', 'style', 'example'].includes(id);
        const isActive = activeTab === id;
        const isHerrscher = activeTheme === 'herrscher_of_human';

        return (
            <button
                onClick={() => setActiveTab(id)}
                className={`flex items-center gap-2 px-3 py-2 text-xs md:text-sm rounded-md transition-all shrink-0 border ${
                    isActive 
                        ? (isHerrscher ? 'bg-pink-400/20 text-[#ff4d6d] border-pink-400 shadow-[0_0_15px_rgba(255,143,163,0.4)] font-black' : 'font-bold shadow-md') 
                        : 'text-slate-400 hover:text-slate-200 border-transparent'
                }`}
                style={isActive && !isHerrscher ? { 
                    backgroundColor: `${themeColor}20`, 
                    color: activeTheme === 'default' ? '#000' : themeColor, 
                    borderColor: activeTheme === 'default' ? 'var(--primary)' : `${themeColor}60`,
                    boxShadow: activeTheme !== 'default' ? `0 0 10px ${themeColor}30` : 'none'
                } : {}}
            >
                <Icon size={16} className={isActive ? 'animate-pulse' : ''} /> {label}
                {isProtected && <span className="hidden sm:inline text-[10px] opacity-70 px-1 border border-current rounded uppercase ml-1 font-black">Online</span>}
            </button>
        );
    };

    // --- CRUD Helpers ---
    const addCharacterItem = () => {
        setCharacterization([{ 
            original_name: '', translated_name: '', gender: '', age: '', 
            personality: '', speech_style: '', additional_info: '' 
        }, ...characterization]);
        triggerDraftSave();
    };

    const updateCharacterItem = (originalIdx: number, field: keyof CharacterizationItem, val: string) => {
        const newItems = [...characterization];
        newItems[originalIdx] = { ...newItems[originalIdx], [field]: val };
        setCharacterization(newItems);
        triggerDraftSave();
    };

    const addExampleItem = () => {
        setTranslationExample([{ src: '', dst: '' }, ...translationExample]);
        triggerDraftSave();
    };

    const updateExampleItem = (originalIdx: number, field: keyof TranslationExampleItem, val: string) => {
        const newItems = [...translationExample];
        newItems[originalIdx] = { ...newItems[originalIdx], [field]: val };
        setTranslationExample(newItems);
        triggerDraftSave();
    };

    // --- AI Glossary Analysis Functions ---
    const startAiAnalysis = async () => {
        if (!aiInputPath) { alert('请输入文件路径'); return; }
        try {
            await DataService.startGlossaryAnalysis(
                aiInputPath, aiPercent, aiLines,
                aiUseTempConfig, aiTempPlatform, aiTempApiKey, aiTempApiUrl, aiTempModel, aiTempThreads
            );
            pollAnalysisStatus();
        } catch (e: any) {
            setAiLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] 错误: ${e.message}`]);
        }
    };

    const pollAnalysisStatus = () => {
        const poll = async () => {
            try {
                const status = await DataService.getAnalysisStatus();
                setAiStatus(status);
                // 从后端获取日志
                if (status.logs && Array.isArray(status.logs)) {
                    setAiLogs(status.logs);
                }
                if (status.status === 'running') {
                    setTimeout(poll, 1000);
                }
            } catch (e) {
                console.error(e);
            }
        };
        poll();
    };

    const stopAiAnalysis = async () => {
        try {
            await DataService.stopGlossaryAnalysis();
            setAiLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] 已停止分析`]);
        } catch (e: any) {
            setAiLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] 停止失败: ${e.message}`]);
        }
    };

    const saveAiResults = async () => {
        try {
            const result = await DataService.saveAnalysisResults(aiMinFreq, aiFilename);
            setAiLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${result.message}`]);
            alert(result.message);
            // Reload glossary data
            const g = await DataService.getGlossary();
            setGlossary(g || []);
        } catch (e: any) {
            setAiLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] 保存失败: ${e.message}`]);
            alert('保存失败: ' + e.message);
        }
    };

    // --- Renderers ---

    const isLightCityTheme = ['herrscher_of_human', 'elysia', 'pardofelis', 'griseo'].includes(activeTheme);

    const renderTextEditor = (value: string, setter: (v: string) => void, placeholder: string) => (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className={`flex justify-between items-center p-3 rounded-lg border transition-all ${isLightCityTheme ? 'bg-white/40 border-pink-200/50' : 'bg-slate-900/50 border-slate-800'}`}>
                <div className="flex items-center gap-2">
                    <button 
                        onClick={() => toggleSwitch(activeTab === 'world' ? 'world_building_switch' : 'writing_style_switch')}
                        className={`transition-all hover:scale-110 ${config?.[activeTab === 'world' ? 'world_building_switch' : 'writing_style_switch'] ? (isLightCityTheme ? 'text-pink-500' : 'text-green-400') : 'text-slate-600'}`}
                    >
                        {config?.[activeTab === 'world' ? 'world_building_switch' : 'writing_style_switch'] ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                    </button>
                    <span className={`text-sm font-semibold ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>
                        {activeTab === 'world' ? t('feature_world_building_switch') : t('feature_writing_style_switch')}
                    </span>
                </div>
            </div>
            <textarea
                value={value}
                onChange={(e) => { setter(e.target.value); triggerDraftSave(); }}
                placeholder={placeholder}
                className={`w-full h-96 border rounded-lg p-4 outline-none font-mono text-sm leading-relaxed transition-all bg-slate-950 ${
                    isLightCityTheme 
                        ? 'border-pink-200 text-pink-400 focus:border-pink-400' 
                        : 'border-slate-800 text-slate-300 focus:border-primary'
                }`}
                style={activeTheme !== 'default' ? { borderColor: `${themeColor}40` } : {}}
            />
        </div>
    );

    return (
        <div className="max-w-6xl mx-auto space-y-6 pb-12">
            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center sticky top-0 bg-background/95 backdrop-blur z-20 py-4 border-b border-slate-800 gap-4">
                <div className="flex flex-wrap items-center gap-4 w-full md:w-auto">
                    <h1 className="text-xl md:text-2xl font-bold text-white">{t('menu_glossary_rules')}</h1>
                    
                    {/* Profile Selector */}
                    <div className="relative">
                        <button 
                            onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
                            className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
                        >
                            <FileJson size={14} className="text-primary" />
                            <span className="font-medium max-w-[120px] md:max-w-[150px] truncate">{config?.active_rules_profile || 'Loading...'}</span>
                            <ChevronDown size={14} className={`transition-transform ${isProfileMenuOpen ? 'rotate-180' : ''}`} />
                        </button>
                        
                        {isProfileMenuOpen && (
                            <>
                                <div className="fixed inset-0 z-30" onClick={() => setIsProfileMenuOpen(false)} />
                                <div className="absolute top-full left-0 mt-2 w-48 bg-slate-900 border border-slate-700 rounded-lg shadow-xl z-40 py-1 max-h-60 overflow-y-auto no-scrollbar">
                                    {profiles.map(p => (
                                        <button
                                            key={p}
                                            onClick={() => handleProfileSwitch(p)}
                                            className={`w-full text-left px-4 py-2 text-sm hover:bg-slate-800 transition-colors ${config?.active_rules_profile === p ? 'text-primary font-bold' : 'text-slate-300'}`}
                                        >
                                            {p}
                                        </button>
                                    ))}
                                </div>
                            </>
                        )}
                    </div>
                </div>
                
                <div className="flex items-center gap-2 w-full md:w-auto justify-between md:justify-end">
                    <div className="relative hidden lg:block">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                        <input 
                            type="text" 
                            placeholder={t('ui_rules_filter')}
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:border-primary w-32"
                        />
                    </div>
                    
                    <div className="flex items-center gap-2">
                        <button onClick={exportData} title="Export to File" className="p-2 bg-slate-800 text-slate-300 rounded-lg hover:text-white transition-colors border border-slate-700">
                            <Download size={18} />
                        </button>

                        <button onClick={() => fileInputRef.current?.click()} title="Import from File" className="p-2 bg-slate-800 text-slate-300 rounded-lg hover:text-white transition-colors border border-slate-700">
                            <Upload size={18} />
                            <input type="file" ref={fileInputRef} className="hidden" accept={activeTab === 'world' || activeTab === 'style' ? ".txt" : ".json"} onChange={importData} />
                        </button>

                        {hasDraft && (
                            <button onClick={recoverDraft} title="Recover Unsaved Draft" className="p-2 bg-orange-500/10 text-orange-400 rounded-lg hover:bg-orange-500/20 transition-colors border border-orange-500/30">
                                <History size={18} />
                            </button>
                        )}
                    </div>

                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-2 bg-primary hover:bg-cyan-400 text-slate-900 px-4 py-2 rounded-lg font-bold transition-colors shadow-lg shadow-cyan-500/20 disabled:opacity-50"
                    >
                        {saving ? <RefreshCw size={18} className="animate-spin" /> : <Save size={18} />}
                        <span className="hidden sm:inline">{t('ui_rules_save')}</span>
                    </button>
                </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex gap-2 bg-slate-900/50 p-2 rounded-lg border border-slate-800 overflow-x-auto no-scrollbar whitespace-nowrap">
                <TabButton id="glossary" icon={BookOpen} label={t('ui_rules_glossary')} />
                <TabButton id="exclusion" icon={Ban} label={t('ui_rules_exclusion')} />
                <TabButton id="characterization" icon={Users} label={t('feature_characterization_switch')} />
                <TabButton id="world" icon={Map} label={t('feature_world_building_switch')} />
                <TabButton id="style" icon={PenTool} label={t('feature_writing_style_switch')} />
                <TabButton id="example" icon={Languages} label={t('feature_translation_example_switch')} />
                <TabButton id="ai_glossary" icon={Sparkles} label={t('ui_ai_glossary')} />
            </div>

            {/* Content Area */}
            <div className="bg-surface/50 border border-slate-800 rounded-xl p-4 md:p-6 backdrop-blur-sm min-h-[500px]">
                {loading || !config ? (
                    <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-3">
                        <RefreshCw size={32} className="animate-spin text-primary" />
                        <p>Loading...</p>
                    </div>
                ) : (
                    <>
                        {isLocal && isOnlineOnlyTab && (
                            <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-3 mb-6 shadow-lg animate-pulse">
                                <AlertTriangle size={24} className="text-red-500 shrink-0" />
                                <div>
                                    <h4 className="text-sm font-bold text-red-500 uppercase tracking-wider">Online Only / 仅限在线接口</h4>
                                    <p className="text-xs text-slate-200 mt-1 font-medium">{t('msg_online_features_warning')}</p>
                                </div>
                            </div>
                        )}
                        
                        {/* Tab Content: Glossary */}
                        {activeTab === 'glossary' && (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                <div className="flex justify-between items-center bg-slate-900/50 p-3 rounded-lg border border-slate-800"
                                     style={activeTheme !== 'default' ? { borderColor: `${themeColor}20` } : {}}>
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center gap-2 border-r border-slate-700 pr-4 mr-2">
                                            <button onClick={() => toggleSwitch('prompt_dictionary_switch')} 
                                                className="transition-all hover:scale-110"
                                                style={{ color: config.prompt_dictionary_switch ? themeColor : '#475569' }}
                                            >
                                                {config.prompt_dictionary_switch ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                                            </button>
                                            <span className={`text-sm font-semibold ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('ui_rules_enable_glossary')}</span>
                                        </div>
                                    </div>
                                    <button onClick={() => { setGlossary([{ src: '', dst: '', info: '' }, ...glossary]); triggerDraftSave(); }} 
                                        className="flex items-center gap-1 text-sm font-bold px-3 py-1.5 rounded transition-all hover:scale-105 active:scale-95"
                                        style={{ 
                                            backgroundColor: `${themeColor}20`, 
                                            color: isLightCityTheme ? '#ff4d6d' : themeColor,
                                            border: `1px solid ${themeColor}40`
                                        }}
                                    >
                                        <Plus size={16} /> {t('ui_rules_add')}
                                    </button>
                                </div>
                                <div className="grid gap-3">
                                    {glossary.map((item, originalIdx) => {
                                        if (filter && !item.src?.toLowerCase().includes(filter.toLowerCase())) return null;
                                        return (
                                            <div key={originalIdx} className={`grid grid-cols-12 gap-3 p-3 border rounded-lg transition-colors group ${isLightCityTheme ? 'bg-white/60 border-pink-100 hover:border-pink-300' : 'bg-slate-900 border-slate-800 hover:border-slate-600'}`}
                                                 style={!isLightCityTheme && activeTheme !== 'default' ? { borderColor: `${themeColor}20` } : {}}>
                                                <div className="col-span-4"><input type="text" placeholder={t('ui_rules_source')} value={item.src} onChange={(e) => { const n = [...glossary]; n[originalIdx].src = e.target.value; setGlossary(n); triggerDraftSave(); }} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 outline-none transition-all text-green-300 focus:border-primary" /></div>
                                                <div className="col-span-4"><input type="text" placeholder={t('ui_rules_target')} value={item.dst} onChange={(e) => { const n = [...glossary]; n[originalIdx].dst = e.target.value; setGlossary(n); triggerDraftSave(); }} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 outline-none transition-all text-blue-300 focus:border-primary" /></div>
                                                <div className="col-span-3"><input type="text" placeholder={t('ui_rules_note')} value={item.info || ''} onChange={(e) => { const n = [...glossary]; n[originalIdx].info = e.target.value; setGlossary(n); triggerDraftSave(); }} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 outline-none text-sm transition-all text-slate-400 focus:border-primary" /></div>
                                                <div className="col-span-1 flex justify-end"><button onClick={() => setGlossary(glossary.filter((_, i) => i !== originalIdx))} className={`p-2 transition-colors ${isLightCityTheme ? 'text-pink-300 hover:text-red-500' : 'text-slate-600 hover:text-red-400'}`}><Trash2 size={18} /></button></div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Tab Content: Exclusion */}
                        {activeTab === 'exclusion' && (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                <div className="flex justify-between items-center bg-slate-900/50 p-3 rounded-lg border border-slate-800"
                                     style={activeTheme !== 'default' ? { borderColor: `${themeColor}20` } : {}}>
                                    <div className="flex items-center gap-4">
                                        <div className="flex items-center gap-2 border-r border-slate-700 pr-4 mr-2">
                                            <button onClick={() => toggleSwitch('exclusion_list_switch')} 
                                                className="transition-all hover:scale-110"
                                                style={{ color: config.exclusion_list_switch ? themeColor : '#475569' }}
                                            >
                                                {config.exclusion_list_switch ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                                            </button>
                                            <span className={`text-sm font-semibold ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('ui_rules_enable_exclusion')}</span>
                                        </div>
                                    </div>
                                    <button onClick={() => { setExclusion([{ markers: '', regex: '', info: '' }, ...exclusion]); triggerDraftSave(); }} 
                                        className="flex items-center gap-1 text-sm font-bold px-3 py-1.5 rounded transition-all hover:scale-105 active:scale-95"
                                        style={{ 
                                            backgroundColor: `${themeColor}20`, 
                                            color: isLightCityTheme ? '#ff4d6d' : themeColor,
                                            border: `1px solid ${themeColor}40`
                                        }}
                                    >
                                        <Plus size={16} /> {t('ui_rules_add')}
                                    </button>
                                </div>
                                <div className="grid gap-3">
                                    {exclusion.map((item, originalIdx) => {
                                        if (filter && !item.markers?.toLowerCase().includes(filter.toLowerCase())) return null;
                                        return (
                                            <div key={originalIdx} className={`grid grid-cols-12 gap-3 p-3 border rounded-lg transition-colors group ${isLightCityTheme ? 'bg-white/60 border-pink-100 hover:border-pink-300' : 'bg-slate-900 border-slate-800 hover:border-slate-600'}`}>
                                                <div className="col-span-4"><input type="text" placeholder={t('ui_rules_marker')} value={item.markers} onChange={(e) => { const n = [...exclusion]; n[originalIdx].markers = e.target.value; setExclusion(n); triggerDraftSave(); }} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 outline-none font-mono text-sm transition-all text-orange-300 focus:border-primary" /></div>
                                                <div className="col-span-4"><input type="text" placeholder={t('ui_rules_regex')} value={item.regex || ''} onChange={(e) => { const n = [...exclusion]; n[originalIdx].regex = e.target.value; setExclusion(n); triggerDraftSave(); }} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 outline-none font-mono text-sm transition-all text-purple-300 focus:border-primary" /></div>
                                                <div className="col-span-3"><input type="text" placeholder={t('ui_rules_note')} value={item.info || ''} onChange={(e) => { const n = [...exclusion]; n[originalIdx].info = e.target.value; setExclusion(n); triggerDraftSave(); }} className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 outline-none text-sm transition-all text-slate-400 focus:border-primary" /></div>
                                                <div className="col-span-1 flex justify-end"><button onClick={() => setExclusion(exclusion.filter((_, i) => i !== originalIdx))} className={`p-2 transition-colors ${isLightCityTheme ? 'text-pink-300 hover:text-red-500' : 'text-slate-600 hover:text-red-400'}`}><Trash2 size={18} /></button></div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Tab Content: Characterization */}
                        {activeTab === 'characterization' && (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                <div className="flex justify-between items-center bg-slate-900/50 p-3 rounded-lg border border-slate-800"
                                     style={activeTheme !== 'default' ? { borderColor: `${themeColor}20` } : {}}>
                                    <div className="flex items-center gap-2">
                                        <button onClick={() => toggleSwitch('characterization_switch')} 
                                            className="transition-all hover:scale-110"
                                            style={{ color: config.characterization_switch ? themeColor : '#475569' }}
                                        >
                                            {config.characterization_switch ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                                        </button>
                                        <span className={`text-sm font-semibold ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('feature_characterization_switch')}</span>
                                    </div>
                                    <button onClick={addCharacterItem} 
                                        className="flex items-center gap-1 text-sm font-bold px-3 py-1.5 rounded transition-all hover:scale-105 active:scale-95"
                                        style={{ 
                                            backgroundColor: `${themeColor}20`, 
                                            color: isLightCityTheme ? '#ff4d6d' : themeColor,
                                            border: `1px solid ${themeColor}40`
                                        }}
                                    >
                                        <Plus size={16} /> {t('ui_rules_add')}
                                    </button>
                                </div>
                                <div className="grid gap-4">
                                    {characterization.map((item, originalIdx) => {
                                        if (filter && !item.original_name?.includes(filter) && !item.translated_name?.includes(filter)) return null;
                                        return (
                                            <div key={originalIdx} className={`p-4 border rounded-lg transition-all group space-y-3 ${isLightCityTheme ? 'bg-white/60 border-pink-100 hover:border-pink-300' : 'bg-slate-900 border-slate-800 hover:border-slate-600'}`}>
                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                                    <input type="text" placeholder={t('ui_rules_character_orig')} value={item.original_name} onChange={(e) => updateCharacterItem(originalIdx, 'original_name', e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-green-300 focus:border-primary outline-none transition-all" />
                                                    <input type="text" placeholder={t('ui_rules_character_trans')} value={item.translated_name} onChange={(e) => updateCharacterItem(originalIdx, 'translated_name', e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-blue-300 focus:border-primary outline-none transition-all" />
                                                    <input type="text" placeholder={t('ui_rules_character_gender')} value={item.gender} onChange={(e) => updateCharacterItem(originalIdx, 'gender', e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-300 focus:border-primary outline-none transition-all" />
                                                    <input type="text" placeholder={t('ui_rules_character_age')} value={item.age} onChange={(e) => updateCharacterItem(originalIdx, 'age', e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-300 focus:border-primary outline-none transition-all" />
                                                </div>
                                                <div className="grid grid-cols-2 gap-3">
                                                    <input type="text" placeholder={t('ui_rules_character_personality')} value={item.personality} onChange={(e) => updateCharacterItem(originalIdx, 'personality', e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-300 focus:border-primary outline-none transition-all" />
                                                    <input type="text" placeholder={t('ui_rules_character_speech')} value={item.speech_style} onChange={(e) => updateCharacterItem(originalIdx, 'speech_style', e.target.value)} className="bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-300 focus:border-primary outline-none transition-all" />
                                                </div>
                                                <div className="flex gap-3">
                                                    <input type="text" placeholder={t('ui_rules_character_info')} value={item.additional_info} onChange={(e) => updateCharacterItem(originalIdx, 'additional_info', e.target.value)} className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-400 focus:border-primary outline-none transition-all" />
                                                    <button onClick={() => setCharacterization(characterization.filter((_, i) => i !== originalIdx))} className={`p-2 transition-colors rounded border ${isLightCityTheme ? 'text-pink-300 hover:text-red-500 bg-white/80 border-pink-100' : 'text-slate-600 hover:text-red-400 bg-slate-950 border-slate-800'}`}><Trash2 size={18} /></button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Tab Content: World Building */}
                        {activeTab === 'world' && renderTextEditor(worldBuilding, setWorldBuilding, t('ui_rules_world_placeholder'))}

                        {/* Tab Content: Writing Style */}
                        {activeTab === 'style' && renderTextEditor(writingStyle, setWritingStyle, t('ui_rules_style_placeholder'))}

                        {/* Tab Content: Translation Examples */}
                        {activeTab === 'example' && (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                <div className="flex justify-between items-center bg-slate-900/50 p-3 rounded-lg border border-slate-800"
                                     style={activeTheme !== 'default' ? { borderColor: `${themeColor}20` } : {}}>
                                    <div className="flex items-center gap-2">
                                        <button onClick={() => toggleSwitch('translation_example_switch')} 
                                            className="transition-all hover:scale-110"
                                            style={{ color: config.translation_example_switch ? themeColor : '#475569' }}
                                        >
                                            {config.translation_example_switch ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                                        </button>
                                        <span className={`text-sm font-semibold ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('feature_translation_example_switch')}</span>
                                    </div>
                                    <button onClick={addExampleItem} 
                                        className="flex items-center gap-1 text-sm font-bold px-3 py-1.5 rounded transition-all hover:scale-105 active:scale-95"
                                        style={{ 
                                            backgroundColor: `${themeColor}20`, 
                                            color: isLightCityTheme ? '#ff4d6d' : themeColor,
                                            border: `1px solid ${themeColor}40`
                                        }}
                                    >
                                        <Plus size={16} /> {t('ui_rules_add')}
                                    </button>
                                </div>
                                <div className="grid gap-3">
                                    {translationExample.map((item, originalIdx) => {
                                        if (filter && !item.src?.includes(filter) && !item.dst?.includes(filter)) return null;
                                        return (
                                            <div key={originalIdx} className={`grid grid-cols-12 gap-3 p-3 border rounded-lg transition-colors group ${isLightCityTheme ? 'bg-white/60 border-pink-100 hover:border-pink-300' : 'bg-slate-900 border-slate-800 hover:border-slate-600'}`}>
                                                <div className="col-span-5"><textarea placeholder={t('ui_rules_example_src')} value={item.src} onChange={(e) => updateExampleItem(originalIdx, 'src', e.target.value)} className="w-full h-24 bg-slate-950 border border-slate-700 rounded p-2 text-green-300 focus:border-primary outline-none text-sm resize-none transition-all" /></div>
                                                <div className="col-span-1 flex items-center justify-center text-slate-600">→</div>
                                                <div className="col-span-5"><textarea placeholder={t('ui_rules_example_dst')} value={item.dst} onChange={(e) => updateExampleItem(originalIdx, 'dst', e.target.value)} className="w-full h-24 bg-slate-950 border border-slate-700 rounded p-2 text-blue-300 focus:border-primary outline-none text-sm resize-none transition-all" /></div>
                                                <div className="col-span-1 flex items-center justify-end"><button onClick={() => setTranslationExample(translationExample.filter((_, i) => i !== originalIdx))} className={`p-2 transition-colors rounded border ${isLightCityTheme ? 'text-pink-300 hover:text-red-500 bg-white/80 border-pink-100' : 'text-slate-600 hover:text-red-400 bg-slate-950 border-slate-800'}`}><Trash2 size={18} /></button></div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {activeTab === 'ai_glossary' && (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                {/* Warning */}
                                <div className={`p-3 rounded-lg border ${isLightCityTheme ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-yellow-900/20 border-yellow-700/50 text-yellow-300'}`}>
                                    <div className="flex items-center gap-2">
                                        <AlertTriangle size={16} />
                                        <span className="text-sm">{t('ai_glossary_warning')}</span>
                                    </div>
                                </div>

                                {/* Input Controls */}
                                <div className={`p-4 rounded-lg border ${isLightCityTheme ? 'bg-white/40 border-pink-200/50' : 'bg-slate-900/50 border-slate-800'}`}>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div>
                                            <label className={`text-sm font-medium ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('ai_glossary_input_path')}</label>
                                            <input type="text" value={aiInputPath} onChange={(e) => setAiInputPath(e.target.value)}
                                                className="w-full mt-1 px-3 py-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 focus:border-primary outline-none transition-all"
                                                placeholder="C:/path/to/file.epub" />
                                        </div>
                                        <div className="grid grid-cols-2 gap-2">
                                            <div>
                                                <label className={`text-sm font-medium ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('ai_glossary_percent')}</label>
                                                <input type="number" value={aiPercent} onChange={(e) => setAiPercent(Number(e.target.value))}
                                                    className="w-full mt-1 px-3 py-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 focus:border-primary outline-none transition-all" min={1} max={100} />
                                            </div>
                                            <div>
                                                <label className={`text-sm font-medium ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('ai_glossary_lines')}</label>
                                                <input type="number" value={aiLines || ''} onChange={(e) => setAiLines(e.target.value ? Number(e.target.value) : undefined)}
                                                    className="w-full mt-1 px-3 py-2 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 focus:border-primary outline-none transition-all" placeholder="可选" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* API Config Selection */}
                                    <div className="mt-4 pt-4 border-t border-slate-700">
                                        <div className="flex items-center gap-3 mb-3">
                                            <label className={`text-sm font-medium ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>
                                                {t('ai_glossary_api_config')}:
                                            </label>
                                            <button
                                                onClick={() => setAiUseTempConfig(false)}
                                                className={`px-3 py-1 text-sm rounded transition-all ${!aiUseTempConfig
                                                    ? 'font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                                                style={!aiUseTempConfig ? { backgroundColor: `${themeColor}20`, color: themeColor, border: `1px solid ${themeColor}40` } : { border: '1px solid transparent' }}
                                            >
                                                {t('ai_glossary_use_current')}
                                            </button>
                                            <button
                                                onClick={() => setAiUseTempConfig(true)}
                                                className={`px-3 py-1 text-sm rounded transition-all ${aiUseTempConfig
                                                    ? 'font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                                                style={aiUseTempConfig ? { backgroundColor: `${themeColor}20`, color: themeColor, border: `1px solid ${themeColor}40` } : { border: '1px solid transparent' }}
                                            >
                                                {t('ai_glossary_use_temp')}
                                            </button>
                                        </div>

                                        {aiUseTempConfig && (
                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3 bg-slate-800/50 rounded-lg border border-slate-700">
                                                <div>
                                                    <label className="text-xs text-slate-400">{t('ai_glossary_temp_platform')}</label>
                                                    <input type="text" value={aiTempPlatform} onChange={(e) => setAiTempPlatform(e.target.value)}
                                                        className="w-full mt-1 px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none"
                                                        placeholder="openai / anthropic / google" />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-slate-400">{t('ai_glossary_temp_model')}</label>
                                                    <input type="text" value={aiTempModel} onChange={(e) => setAiTempModel(e.target.value)}
                                                        className="w-full mt-1 px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none"
                                                        placeholder="gpt-4o / claude-3-5-sonnet" />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-slate-400">{t('ai_glossary_temp_threads')}</label>
                                                    <input type="number" value={aiTempThreads} onChange={(e) => setAiTempThreads(Number(e.target.value))}
                                                        className="w-full mt-1 px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none"
                                                        min={1} max={100} placeholder="5" />
                                                </div>
                                                <div>
                                                    <label className="text-xs text-slate-400">{t('ai_glossary_temp_url')}</label>
                                                    <input type="text" value={aiTempApiUrl} onChange={(e) => setAiTempApiUrl(e.target.value)}
                                                        className="w-full mt-1 px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none"
                                                        placeholder="https://api.openai.com" />
                                                </div>
                                                <div className="md:col-span-2">
                                                    <label className="text-xs text-slate-400">{t('ai_glossary_temp_key')}</label>
                                                    <input type="password" value={aiTempApiKey} onChange={(e) => setAiTempApiKey(e.target.value)}
                                                        className="w-full mt-1 px-2 py-1.5 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none"
                                                        placeholder="sk-..." />
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    <div className="flex gap-2 mt-4">
                                        <button onClick={startAiAnalysis} disabled={aiStatus.status === 'running'}
                                            className="flex items-center gap-2 px-4 py-2 rounded font-bold transition-all hover:scale-105 disabled:opacity-50"
                                            style={{ backgroundColor: `${themeColor}20`, color: themeColor, border: `1px solid ${themeColor}40` }}>
                                            <Play size={16} /> {t('ai_glossary_start')}
                                        </button>
                                        <button onClick={stopAiAnalysis} disabled={aiStatus.status !== 'running'}
                                            className="flex items-center gap-2 px-4 py-2 rounded font-bold transition-all hover:scale-105 disabled:opacity-50 bg-red-900/20 text-red-400 border border-red-700/50">
                                            <Square size={16} /> {t('ai_glossary_stop')}
                                        </button>
                                    </div>
                                </div>

                                {/* Status & Logs */}
                                <div className={`p-4 rounded-lg border ${isLightCityTheme ? 'bg-white/40 border-pink-200/50' : 'bg-slate-900/50 border-slate-800'}`}>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className={`text-sm font-medium ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>{t('ai_glossary_status')}: {aiStatus.message || t(`ai_glossary_${aiStatus.status}`)}</span>
                                        {aiStatus.total > 0 && <span className="text-sm text-slate-400">{aiStatus.progress}/{aiStatus.total}</span>}
                                    </div>
                                    {aiStatus.total > 0 && (
                                        <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                                            <div className="h-full transition-all" style={{ width: `${(aiStatus.progress / aiStatus.total) * 100}%`, backgroundColor: themeColor }} />
                                        </div>
                                    )}
                                    <div className="mt-3 h-32 overflow-y-auto bg-slate-950 rounded p-2 text-xs font-mono text-slate-400">
                                        {aiLogs.map((log, i) => <div key={i}>{log}</div>)}
                                    </div>
                                </div>

                                {/* Results Table */}
                                {aiStatus.status === 'completed' && aiStatus.results.length > 0 && (
                                    <div className={`p-4 rounded-lg border ${isLightCityTheme ? 'bg-white/40 border-pink-200/50' : 'bg-slate-900/50 border-slate-800'}`}>
                                        <div className="flex items-center justify-between mb-3">
                                            <span className={`text-sm font-medium ${isLightCityTheme ? 'text-pink-700' : 'text-slate-300'}`}>
                                                {t('ai_glossary_results')} ({aiStatus.results.length})
                                            </span>
                                            <div className="flex items-center gap-2">
                                                <label className="text-xs text-slate-400">{t('ai_glossary_min_freq')}:</label>
                                                <input type="number" value={aiMinFreq} onChange={(e) => setAiMinFreq(Number(e.target.value))}
                                                    className="w-16 px-2 py-1 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none" min={1} />
                                                <input type="text" value={aiFilename} onChange={(e) => setAiFilename(e.target.value)}
                                                    className="w-32 px-2 py-1 bg-slate-950 border border-slate-700 rounded text-sm text-slate-200 outline-none" placeholder="filename" />
                                                <button onClick={saveAiResults}
                                                    className="flex items-center gap-1 px-3 py-1 rounded font-bold text-sm transition-all hover:scale-105"
                                                    style={{ backgroundColor: `${themeColor}20`, color: themeColor, border: `1px solid ${themeColor}40` }}>
                                                    <Save size={14} /> {t('ai_glossary_save')}
                                                </button>
                                            </div>
                                        </div>
                                        <div className="max-h-64 overflow-y-auto">
                                            <table className="w-full text-sm">
                                                <thead className="sticky top-0 bg-slate-900">
                                                    <tr className="text-slate-400 text-left">
                                                        <th className="p-2">{t('ai_glossary_term')}</th>
                                                        <th className="p-2">{t('ai_glossary_type')}</th>
                                                        <th className="p-2 text-right">{t('ai_glossary_count')}</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {aiStatus.results.filter((r: any) => r.count >= aiMinFreq).map((r: any, i: number) => (
                                                        <tr key={i} className="border-t border-slate-800 hover:bg-slate-800/50">
                                                            <td className="p-2 text-cyan-300">{r.src}</td>
                                                            <td className="p-2 text-slate-400">{r.type}</td>
                                                            <td className="p-2 text-right text-yellow-400">{r.count}</td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};
