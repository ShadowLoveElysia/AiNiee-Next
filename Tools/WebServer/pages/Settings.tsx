import React, { useState, useEffect } from 'react';
import { Save, RefreshCw, Plus, Trash2, ToggleLeft, ToggleRight, AlertTriangle, Globe, Server, FileJson, CheckCircle, Loader2, Wifi, WifiOff, Edit2, X, Check, ChevronDown, Sparkles } from 'lucide-react';
import { AppConfig, PlatformConfig } from '../types';
import { DataService } from '../services/DataService';
import { PROJECT_TYPES } from '../constants';
import { useI18n } from '../contexts/I18nContext';
import { useGlobal } from '../contexts/GlobalContext';

export const Settings: React.FC = () => {
  const { t, language, setLanguage, availableLanguages } = useI18n();
  const { config, setConfig, activeTheme, triggerRipple, unlockThemeWithNotification, unlockedThemes } = useGlobal(); // Use Global Context
  const elysiaActive = activeTheme === 'elysia';

  const getCharacterName = (id: string) => {
    switch(id) {
        case 'elysia': return '无瑕·爱莉希雅';
        case 'eden': return '黄金·伊甸';
        case 'mobius': return '无限·梅比乌斯';
        case 'pardofelis': return '空梦·帕朵菲莉丝';
        case 'griseo': return '繁星·格蕾修';
        case 'kevin': return '救世·凯文';
        case 'kalpas': return '鏖灭·千劫';
        case 'aponia': return '戒律·阿波尼亚';
        case 'villv': return '螺旋·维尔薇';
        case 'su': return '天慧·苏';
        case 'sakura': return '刹那·樱';
        case 'kosma': return '旭光·科斯魔';
        case 'hua': return '浮生·华';
        case 'herrscher_of_human': return '真我·人之律者';
        default: return '默认主题';
    }
  };

  const getThemeColorClass = () => {
    switch(activeTheme) {
        case 'elysia': return 'text-pink-500';
        case 'herrscher_of_human': return 'text-[#ff8fa3]';
        case 'eden': return 'text-amber-500';
        case 'mobius': return 'text-green-500';
        case 'pardofelis': return 'text-[#7f5539]';
        case 'griseo': return 'text-blue-400';
        case 'kevin': return 'text-sky-500';
        case 'kalpas': return 'text-red-500';
        case 'aponia': return 'text-purple-400';
        case 'villv': return 'text-orange-600';
        case 'su': return 'text-emerald-500';
        case 'sakura': return 'text-pink-400';
        case 'kosma': return 'text-indigo-400';
        case 'hua': return 'text-orange-500';
        default: return 'text-primary';
    }
  };

  const getTabActiveClass = (isSelected: boolean) => {
    if (!isSelected) return 'border-b-2 border-transparent text-slate-400 hover:text-slate-200';
    
    switch(activeTheme) {
        case 'elysia': return 'bg-pink-500/10 text-pink-500 border border-pink-200/50 shadow-[0_0_15px_rgba(255,102,153,0.15)]';
        case 'herrscher_of_human': return 'bg-pink-400/20 text-[#ff4d6d] border border-pink-300 shadow-[0_0_20px_rgba(255,143,163,0.3)]';
        case 'eden': return 'bg-amber-500/10 text-amber-500 border border-amber-500/50';
        case 'mobius': return 'bg-green-500/10 text-green-500 border border-green-500/50';
        case 'pardofelis': return 'bg-orange-200/50 text-[#7f5539] border border-orange-300';
        case 'griseo': return 'bg-blue-100 text-blue-500 border border-blue-200';
        case 'kevin': return 'bg-sky-100 text-sky-600 border border-sky-200';
        case 'kalpas': return 'bg-red-500/10 text-red-500 border border-red-500/50';
        case 'aponia': return 'bg-purple-500/10 text-purple-400 border border-purple-500/30';
        case 'villv': return 'bg-orange-500/10 text-orange-600 border border-orange-500/30';
        case 'su': return 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30';
        case 'sakura': return 'bg-pink-400/10 text-pink-500 border border-pink-400/30';
        case 'kosma': return 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/30';
        case 'hua': return 'bg-orange-500/10 text-orange-500 border border-orange-500/30';
        default: return 'border-b-2 border-primary text-primary';
    }
  };
  
  const [activeTab, setActiveTab] = useState<'general' | 'api' | 'project' | 'features' | 'system' | 'profiles'>('general');
  const [newPoolItem, setNewPoolItem] = useState('');
  const [saving, setSaving] = useState(false);
  
  // Temp Files State
  const [tempFiles, setTempFiles] = useState<{name: string, path: string, size: number}[]>([]);
  const [selectedTempFiles, setSelectedTempFiles] = useState<string[]>([]);
  const [isDeletingFiles, setIsDeletingFiles] = useState(false);
  const [isTempFilesExpanded, setIsTempFilesExpanded] = useState(false);

  // Profile Management State
  const [profiles, setProfiles] = useState<string[]>([]);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [switchingProfile, setSwitchingProfile] = useState<string | null>(null);
  
  // CRUD State
  const [isCreating, setIsCreating] = useState(false);
  const [isCreatingPlatform, setIsCreatingPlatform] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [tempName, setTempName] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  // System Online Status Check
  const [isOnline, setIsOnline] = useState(true);
  
  // Aponia Trigger: Click the warning icon 3 times
  const [warningClicks, setWarningClicks] = useState(0);
  const handleWarningClick = (e: React.MouseEvent) => {
    const newCount = warningClicks + 1;
    setWarningClicks(newCount);
    if (newCount >= 3) {
      unlockThemeWithNotification('aponia');
      setWarningClicks(0);
    }
  };

  // Hua Trigger: Save 5 times
  const [saveCount, setSaveCount] = useState(0);
  const handleHuaSaveCount = () => {
    const next = saveCount + 1;
    setSaveCount(next);
    if (next >= 5) {
      unlockThemeWithNotification('hua');
      setSaveCount(0);
    }
  };

  // --- Elysia Egg Logic ---
  const isElysiaProfile = config?.active_profile?.toLowerCase() === 'elysia';
  const elysiaUnlocked = localStorage.getItem('elysia_unlocked') === 'true' || isElysiaProfile;

  useEffect(() => {
    loadProfiles();
    handleLoadTempFiles();
  }, []);

  const handleToggleElysia = (e: React.MouseEvent) => {
    triggerRipple(e.clientX, e.clientY);
  };

  // Generic Change Handler for Global Config
  const handleChange = (field: keyof AppConfig, value: any) => {
    if (!config) return;
    
    // --- Easter Eggs Triggers ---
    
    // Mobius: Enter "Infinity" or "∞"
    if (typeof value === 'string' && (value.toLowerCase() === 'infinity' || value === '∞')) {
        unlockThemeWithNotification('mobius');
        return;
    }

    // Kevin: Threads 0 or 99
    if (field === 'user_thread_counts') {
        const val = parseInt(value);
        if (val === 0 || val >= 99) {
            unlockThemeWithNotification('kevin');
        }
    }

    // Eden: Failover Threshold 1920 or 999999
    if (field === 'api_failover_threshold') {
        const val = parseInt(value);
        if (val === 1920 || val >= 999999) {
            unlockThemeWithNotification('eden');
        }
    }

    setConfig({ ...config, [field]: value });
  };
  
  // Handle Response Check Switch (Nested Object)
  const handleCheckChange = (key: string, val: boolean) => {
      if (!config) return;
      // 防护：确保 response_check_switch 是对象而非字符串
      const currentSwitch = typeof config.response_check_switch === 'object' && config.response_check_switch !== null
          ? config.response_check_switch
          : { newline_character_count_check: false, return_to_original_text_check: false, residual_original_text_check: false, reply_format_check: false };
      setConfig({
          ...config,
          response_check_switch: {
              ...currentSwitch,
              [key]: val
          }
      });
  };

  const handleSaveConfig = async () => {
    if (!config) return;
    setSaving(true);
    try {
        await DataService.saveConfig(config);
        alert(t('msg_saved'));
    } catch (e) {
        console.error("Failed to save", e);
        alert("Save failed.");
    } finally {
        setSaving(false);
    }
  };

  const handlePlatformChange = (tag: string) => {
      if (!config || !config.platforms[tag]) return;
      const p = config.platforms[tag];
      setConfig({
          ...config,
          target_platform: tag,
          base_url: p.api_url || config.base_url,
          model: p.model || config.model,
          api_settings: { translate: tag, polish: tag }
      });
  };

  const handleCreatePlatform = async () => {
      if (!tempName.trim()) { setActionError("Name cannot be empty"); return; }
      try {
          await DataService.createPlatform(tempName);
          const newConfig = await DataService.getConfig();
          setConfig(newConfig);
          setIsCreatingPlatform(false);
          setTempName('');
      } catch (e: any) { setActionError(e.message); }
  };

  const handlePoolAdd = () => {
    if (!config) return;
    if (newPoolItem && !config.backup_apis.includes(newPoolItem)) {
      handleChange('backup_apis', [...config.backup_apis, newPoolItem]);
      setNewPoolItem('');
    }
  };

  const handlePoolRemove = (item: string) => {
    if (!config) return;
    handleChange('backup_apis', config.backup_apis.filter(i => i !== item));
  };

  const handleLoadTempFiles = async () => {
      const list = await DataService.listTempFiles();
      setTempFiles(list);
  };

  const handleToggleTempFile = (name: string) => {
      setSelectedTempFiles(prev => 
          prev.includes(name) ? prev.filter(f => f !== name) : [...prev, name]
      );
  };

  const handleDeleteTempFiles = async () => {
      if (selectedTempFiles.length === 0) return;
      if (!confirm(`Delete ${selectedTempFiles.length} files?`)) return;
      setIsDeletingFiles(true);
      try {
          await DataService.deleteTempFiles(selectedTempFiles);
          await handleLoadTempFiles();
          setSelectedTempFiles([]);
      } catch (e) {
          alert("Failed to delete files");
      } finally {
          setIsDeletingFiles(false);
      }
  };

  const handleSwitchProfile = async (profileName: string) => {
      if (switchingProfile || renamingId || isCreating) return;
      if (config?.active_profile === profileName) return;
      setSwitchingProfile(profileName);
      try {
          const newConfig = await DataService.switchProfile(profileName);
          setConfig(newConfig);
      } catch (e) {
          console.error("Failed to switch profile", e);
      } finally {
          setSwitchingProfile(null);
      }
  };

  const loadProfiles = async () => {
      setLoadingProfiles(true);
      try {
          const list = await DataService.getProfiles();
          setProfiles(list);
      } catch (e) {
          console.error("Failed to load profiles", e);
      } finally {
          setLoadingProfiles(false);
      }
  };

  const startCreate = () => { setTempName(''); setActionError(null); setIsCreating(true); };
  const cancelCreate = () => { setIsCreating(false); setTempName(''); setActionError(null); };
  const confirmCreate = async () => {
      if (!tempName.trim()) { setActionError("Name cannot be empty"); return; }
      try {
          await DataService.createProfile(tempName, config?.active_profile);
          await loadProfiles();
          setIsCreating(false);
          setTempName('');
      } catch (e: any) { setActionError(e.message); }
  };

  const startRename = (name: string, e: React.MouseEvent) => {
      e.stopPropagation(); setRenamingId(name); setTempName(name); setActionError(null);
  };
  const cancelRename = () => { setRenamingId(null); setTempName(''); setActionError(null); };
  const confirmRename = async (oldName: string) => {
      if (!tempName.trim() || tempName === oldName) { cancelRename(); return; }
      try {
          await DataService.renameProfile(oldName, tempName);
          if (config?.active_profile === oldName) { setConfig({ ...config, active_profile: tempName }); }
          await loadProfiles();
          setRenamingId(null);
      } catch (e: any) { setActionError(e.message); }
  };

  const handleDelete = async (name: string, e: React.MouseEvent) => {
      e.stopPropagation();
      if (!window.confirm(t('msg_profile_delete_confirm').replace('{}', name))) return;
      try { await DataService.deleteProfile(name); await loadProfiles(); } catch (e: any) { alert(e.message); }
  };

  if (!config) {
      return <div className="p-12 text-center text-slate-500 animate-pulse">Loading Configuration...</div>;
  }

    const Toggle = ({ field, label, desc }: { field: keyof AppConfig, label: string, desc?: string }) => {
      return (
        <div className="flex items-center justify-between p-3 border border-slate-700 rounded-lg bg-slate-900/30">
          <div className="mr-4">
            <h4 className="text-slate-200 font-medium text-sm">{label}</h4>
            {desc && <p className="text-xs text-slate-500">{desc}</p>}
          </div>
          <button
            onClick={() => handleChange(field, !config[field])}
            className={`transition-all duration-300 ${config[field] ? getThemeColorClass() : 'text-slate-600'}`}
          >
            {config[field] ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
          </button>
        </div>
      );
    };
  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      <div className="flex justify-between items-center sticky top-0 bg-background/95 backdrop-blur z-20 py-4 border-b border-slate-800">
        <h1 className="text-2xl font-bold text-white">{t('ui_settings_title')}</h1>
        <button 
            onClick={() => { handleSaveConfig(); handleHuaSaveCount(); }}
            disabled={saving}
            className="flex items-center gap-2 bg-primary hover:bg-cyan-400 text-slate-900 px-4 py-2 rounded-lg font-bold transition-colors shadow-lg shadow-primary/20 disabled:opacity-50"
        >
          {saving ? <RefreshCw size={18} className="animate-spin" /> : <Save size={18} />}
          {t('ui_settings_save')}
        </button>
      </div>

      <div className="flex border-b border-slate-800 space-x-1 overflow-x-auto p-1">
        {[
            { id: 'general', label: t('ui_tab_general') },
            { id: 'api', label: t('ui_tab_api') },
            { id: 'project', label: t('ui_tab_project') },
            { id: 'features', label: t('ui_tab_features') },
            { id: 'system', label: t('ui_tab_system') },
            { id: 'profiles', label: t('menu_profiles') }
        ].map((tab) => {
          const isSelected = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-2.5 text-sm font-bold capitalize transition-all duration-300 rounded-xl whitespace-nowrap ${getTabActiveClass(isSelected)}`}
            >
              {tab.label}
              {elysiaActive && isSelected && <Sparkles size={10} className="inline-block ml-1 text-pink-400 animate-pulse" />}
            </button>
          );
        })}
      </div>

      <div className="bg-surface/50 border border-slate-800 rounded-xl p-4 md:p-6 backdrop-blur-sm min-h-[500px]">
        {/* --- GENERAL TAB --- */}
        {activeTab === 'general' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
            {(localStorage.getItem('elysia_unlocked') === 'true' && !isElysiaProfile) && (
              <div className={`col-span-1 md:col-span-2 p-4 rounded-lg flex items-center justify-between animate-in fade-in slide-in-from-top-4 duration-500 ${elysiaActive ? 'bg-pink-500/10 border border-pink-500/20' : 'bg-slate-900/50 border border-slate-700'}`}>
                  <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-full ${elysiaActive ? 'bg-pink-500/20 text-pink-500' : 'bg-slate-800 text-slate-500'}`}>
                          <Sparkles size={20} />
                      </div>
                      <div>
                          <h4 className={`font-bold text-sm ${elysiaActive ? 'text-pink-600' : 'text-slate-300'}`}>真我·主题 (Elysia Theme)</h4>
                          <p className={`text-[10px] ${elysiaActive ? 'text-pink-400' : 'text-slate-500'}`}>在这里，与奇迹相遇。这就是我给你的小惊喜哦♪</p>
                      </div>
                  </div>
                  <button
                    onClick={handleToggleElysia}
                    className={`transition-all duration-300 ${elysiaActive ? 'text-pink-500 scale-110' : 'text-slate-600'}`}
                  >
                    {elysiaActive ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                  </button>
              </div>
            )}

            <div className="col-span-1 md:col-span-2 p-4 bg-slate-900/50 border border-slate-700 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-2">
                    <Globe size={18} className="text-primary" />
                    <span className="text-sm font-semibold text-slate-200">{t('ui_language')}</span>
                </div>
                <div className="flex flex-wrap gap-2 w-full sm:w-auto">
                    {availableLanguages.map(lang => (
                        <button
                            key={lang.code}
                            onClick={() => {
                                setLanguage(lang.code);
                                handleChange('interface_language', lang.code);
                            }}
                            className={`flex-1 sm:flex-none px-3 py-1.5 rounded text-xs font-bold transition-all ${
                                language === lang.code 
                                    ? 'bg-primary text-slate-900 shadow-md shadow-cyan-500/20' 
                                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                            }`}
                        >
                            {lang.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="space-y-2 col-span-1 md:col-span-2">
              <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_input_path')}</label>
              <input type="text" value={config.label_input_path} onChange={(e) => handleChange('label_input_path', e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
            </div>
            <div className="space-y-2 col-span-1 md:col-span-1">
                <label className="text-xs text-slate-500 font-bold uppercase">{t('setting_output_path')}</label>
                <input 
                    type="text"
                    value={config.label_output_path}
                    onChange={(e) => handleChange('label_output_path', e.target.value)}
                    disabled={config.auto_set_output_path}
                    className={`w-full bg-slate-800/50 border border-slate-700 rounded p-2.5 text-sm text-slate-200 focus:border-primary outline-none transition-all ${config.auto_set_output_path ? 'opacity-50 grayscale cursor-not-allowed' : ''}`}
                    placeholder="Auto (beside input folder)"
                />
            </div>

            <div className="col-span-1 md:col-span-2">
                <Toggle 
                  field="auto_set_output_path" 
                  label={t('setting_auto_set_output_path')} 
                  desc="Ignore fixed output path and create output folder beside input file/folder" 
                />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase">{t('prompt_source_lang')}</label>
              <input type="text" value={config.source_language} onChange={(e) => handleChange('source_language', e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase">{t('prompt_target_lang')}</label>
              <input type="text" value={config.target_language} onChange={(e) => handleChange('target_language', e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_thread_count')}</label>
              <input type="number" value={config.user_thread_counts} onChange={(e) => handleChange('user_thread_counts', parseInt(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_request_timeout')}</label>
              <input type="number" value={config.request_timeout} onChange={(e) => handleChange('request_timeout', parseInt(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
            </div>
          </div>
        )}

        {/* --- API TAB --- */}
        {activeTab === 'api' && (
          <div className="space-y-8">
            <div className="p-4 bg-slate-900/50 border border-primary/20 rounded-xl relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-primary" />
                <h3 className="text-primary font-bold mb-4 flex items-center gap-2">
                    <Server size={18} /> Platform Config
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-xs font-semibold text-slate-400 uppercase">{t('label_platform')}</label>
                            <button 
                                onClick={() => setIsCreatingPlatform(true)}
                                className="text-[10px] font-bold text-primary flex items-center gap-1 hover:text-cyan-300 transition-colors"
                            >
                                <Plus size={12} /> {t('menu_api_add_custom') || 'Add New'}
                            </button>
                        </div>
                        
                        {isCreatingPlatform ? (
                            <div className="flex gap-2 animate-in fade-in slide-in-from-top-1 duration-200">
                                <input 
                                    autoFocus
                                    className="flex-1 bg-slate-950 border border-slate-600 rounded px-3 py-1 text-white text-xs"
                                    placeholder="Platform name..."
                                    value={tempName}
                                    onChange={(e) => setTempName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleCreatePlatform()}
                                />
                                <button onClick={() => setIsCreatingPlatform(false)} className="p-1 rounded bg-slate-800 text-slate-400"><X size={14}/></button>
                                <button onClick={handleCreatePlatform} className="p-1 rounded bg-primary text-slate-900"><Check size={14}/></button>
                            </div>
                        ) : (
                            <select 
                                value={config.target_platform} 
                                onChange={(e) => handlePlatformChange(e.target.value)}
                                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm"
                            >
                                {Object.values(config.platforms).map((p: PlatformConfig) => (
                                    <option key={p.tag} value={p.tag}>
                                        {p.name}
                                    </option>
                                ))}
                            </select>
                        )}
                        {actionError && isCreatingPlatform && <p className="text-red-400 text-[10px]">{actionError}</p>}
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs font-semibold text-slate-400 uppercase">{t('label_model')}</label>
                        <input type="text" value={config.model} onChange={(e) => handleChange('model', e.target.value)}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
                    </div>
                    <div className="col-span-1 md:col-span-2 space-y-2">
                        <label className="text-xs font-semibold text-slate-400 uppercase">{t('label_key')}</label>
                        <input type="password" 
                            value={config.platforms[config.target_platform]?.api_key || ''} 
                            onChange={(e) => {
                                const newKey = e.target.value;
                                setConfig({
                                    ...config,
                                    platforms: {
                                        ...config.platforms,
                                        [config.target_platform]: { ...config.platforms[config.target_platform], api_key: newKey }
                                    }
                                });
                            }}
                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" 
                        />
                    </div>
                    <div className="col-span-1 md:col-span-2 space-y-2">
                        <label className="text-xs font-semibold text-slate-400 uppercase">{t('label_url')}</label>
                        <input type="text" value={config.base_url} onChange={(e) => handleChange('base_url', e.target.value)}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
                    </div>

                    <div className="col-span-1 md:col-span-2">
                        <div className="flex items-center justify-between p-3 border border-slate-700 rounded-lg bg-slate-900/30">
                            <div className="mr-4">
                                <h4 className="text-slate-200 font-medium text-sm">{t('自动补全 OpenAI 规范的 Chat 终点')}</h4>
                                <p className="text-xs text-slate-500">{t('如果开启，当 URL 不以 /chat/completions 结尾时，程序将自动尝试补全它')}</p>
                            </div>
                            <button
                                onClick={() => {
                                    const newVal = !config.platforms[config.target_platform]?.auto_complete;
                                    setConfig({
                                        ...config,
                                        platforms: {
                                            ...config.platforms,
                                            [config.target_platform]: { ...config.platforms[config.target_platform], auto_complete: newVal }
                                        }
                                    });
                                }}
                                className={`transition-all duration-300 ${config.platforms[config.target_platform]?.auto_complete ? getThemeColorClass() : 'text-slate-600'}`}
                            >
                                {config.platforms[config.target_platform]?.auto_complete ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Thinking Features - Always show */}
                {true && (
                    <div className="space-y-4 border-t border-slate-700 pt-4">
                        <h4 className="text-slate-300 font-semibold flex items-center gap-2">
                            <Sparkles size={16} className="text-purple-400" />
                            {t('menu_api_think_switch')}
                        </h4>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <div className="space-y-2">
                                <label className="text-xs font-semibold text-slate-400 uppercase">
                                    {t('menu_api_think_switch')}
                                </label>
                                <button
                                    onClick={() => {
                                        const newThinkSwitch = !config.think_switch;
                                        setConfig({
                                            ...config,
                                            think_switch: newThinkSwitch,
                                            platforms: {
                                                ...config.platforms,
                                                [config.target_platform]: {
                                                    ...config.platforms[config.target_platform],
                                                    think_switch: newThinkSwitch
                                                }
                                            }
                                        });
                                    }}
                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-all text-sm font-medium ${
                                        config.think_switch
                                            ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                                            : 'bg-slate-800 text-slate-400 border border-slate-700'
                                    }`}
                                >
                                    {config.think_switch ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                                    {config.think_switch ? 'ON' : 'OFF'}
                                </button>
                            </div>

                            {config.think_switch && (
                                <>
                                    <div className="space-y-2">
                                        <label className="text-xs font-semibold text-slate-400 uppercase">
                                            {t('menu_api_think_depth')}
                                        </label>
                                        {config.platforms[config.target_platform]?.api_format === 'Anthropic' ? (
                                            <select
                                                value={config.think_depth || 'low'}
                                                onChange={(e) => {
                                                    const newDepth = e.target.value;
                                                    setConfig({
                                                        ...config,
                                                        think_depth: newDepth,
                                                        platforms: {
                                                            ...config.platforms,
                                                            [config.target_platform]: {
                                                                ...config.platforms[config.target_platform],
                                                                think_depth: newDepth
                                                            }
                                                        }
                                                    });
                                                }}
                                                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm"
                                            >
                                                <option value="low">Low</option>
                                                <option value="medium">Medium</option>
                                                <option value="high">High</option>
                                            </select>
                                        ) : (
                                            <input
                                                type="number"
                                                value={config.think_depth || 0}
                                                onChange={(e) => {
                                                    const newDepth = parseInt(e.target.value);
                                                    setConfig({
                                                        ...config,
                                                        think_depth: newDepth,
                                                        platforms: {
                                                            ...config.platforms,
                                                            [config.target_platform]: {
                                                                ...config.platforms[config.target_platform],
                                                                think_depth: newDepth
                                                            }
                                                        }
                                                    });
                                                }}
                                                className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm"
                                                min="0"
                                                max="10000"
                                            />
                                        )}
                                    </div>

                                    <div className="space-y-2">
                                        <label className="text-xs font-semibold text-slate-400 uppercase">
                                            {t('menu_api_think_budget')}
                                        </label>
                                        <input
                                            type="number"
                                            value={config.thinking_budget || 4096}
                                            onChange={(e) => {
                                                const newBudget = parseInt(e.target.value);
                                                setConfig({
                                                    ...config,
                                                    thinking_budget: newBudget,
                                                    platforms: {
                                                        ...config.platforms,
                                                        [config.target_platform]: {
                                                            ...config.platforms[config.target_platform],
                                                            thinking_budget: newBudget
                                                        }
                                                    }
                                                });
                                            }}
                                            className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm"
                                            min="1000"
                                            max="100000"
                                        />
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Thinking Mode Warning */}
                        {config.think_switch && (
                            <div className="bg-red-900/30 border border-red-500/30 rounded-lg p-3 mt-4">
                                <div className="flex items-start gap-2">
                                    <AlertTriangle size={16} className="text-red-400 mt-0.5" />
                                    <p className="text-red-300 text-sm">
                                        {['sakura', 'localllm'].includes(config.target_platform?.toLowerCase() || '')
                                            ? t('warning_thinking_online_only')
                                            : t('warning_thinking_compatibility')
                                        }
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            <div className="pt-4 border-t border-slate-800">
               <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
                 <h3 className="text-white font-semibold flex items-center gap-2">
                   <RefreshCw size={16} className="text-accent" /> {t('menu_api_pool_settings')}
                 </h3>
                 <Toggle field="enable_api_failover" label={t('setting_enable_api_failover')} />
               </div>
               
               {config.enable_api_failover && (
                 <div className="space-y-4 bg-slate-900/30 p-4 rounded-lg border border-slate-800">
                   <div className="space-y-2">
                      <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_api_failover_threshold')}</label>
                      <input type="number" value={config.api_failover_threshold} onChange={(e) => handleChange('api_failover_threshold', parseInt(e.target.value))}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
                   </div>
                   
                   <div className="bg-slate-900 rounded-lg p-3 md:p-4 border border-slate-800">
                     <div className="flex gap-2 mb-4">
                        <select 
                          value={newPoolItem} 
                          onChange={(e) => setNewPoolItem(e.target.value)}
                          className="flex-1 bg-slate-800 border border-slate-700 rounded text-sm p-2 text-white"
                        >
                          <option value="">{t('prompt_add_to_pool')}...</option>
                          {Object.keys(config.platforms)
                             .filter(p => !config.backup_apis.includes(p) && p !== config.target_platform)
                             .map(p => (
                            <option key={p} value={p}>{p}</option>
                          ))}
                        </select>
                        <button onClick={handlePoolAdd} className="bg-primary hover:bg-cyan-400 text-slate-900 px-3 rounded text-sm font-bold">
                          <Plus size={16} />
                        </button>
                     </div>
                     <ul className="space-y-2">
                       {config.backup_apis.map((api, idx) => (
                         <li key={idx} className="flex justify-between items-center text-sm bg-slate-900 p-2 rounded border border-slate-700">
                           <span className="text-slate-300">{api}</span>
                           <button onClick={() => handlePoolRemove(api)} className="text-red-400 hover:text-red-300"><Trash2 size={14} /></button>
                         </li>
                       ))}
                       {config.backup_apis.length === 0 && <p className="text-slate-500 text-xs italic p-2">{t('msg_api_pool_empty')}</p>}
                     </ul>
                   </div>
                 </div>
               )}
            </div>
          </div>
        )}

        {/* --- PROJECT TAB --- */}
        {activeTab === 'project' && (
          <div className="space-y-6">
            <div className="space-y-2">
               <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_project_type')}</label>
               <select value={config.translation_project} onChange={(e) => handleChange('translation_project', e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm">
                  {PROJECT_TYPES.map(p => <option key={p} value={p}>{p}</option>)}
               </select>
            </div>

             <div className="p-4 border border-slate-700 rounded-lg bg-slate-900/30">
               <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
                 <div>
                   <h4 className="text-slate-200 font-medium text-sm">{t('setting_limit_mode')}</h4>
                   <p className="text-[10px] text-slate-500">{t('menu_trans_mode_select')}</p>
                 </div>
                 <div className="flex bg-slate-900 rounded-lg p-1 border border-slate-700 w-full sm:w-auto">
                   <button onClick={() => handleChange('tokens_limit_switch', false)}
                      className={`flex-1 sm:flex-none px-4 py-1 text-xs rounded-md transition-all ${!config.tokens_limit_switch ? 'bg-primary text-slate-900 font-bold shadow' : 'text-slate-400'}`}>
                     Line
                   </button>
                   <button onClick={() => handleChange('tokens_limit_switch', true)}
                      className={`flex-1 sm:flex-none px-4 py-1 text-xs rounded-md transition-all ${config.tokens_limit_switch ? 'bg-primary text-slate-900 font-bold shadow' : 'text-slate-400'}`}>
                     Token
                   </button>
                 </div>
               </div>
               
               {!config.tokens_limit_switch ? (
                 <div className="space-y-2">
                   <label className="text-xs font-semibold text-slate-400 uppercase">{t('prompt_limit_val')} (Lines)</label>
                   <input type="number" value={config.lines_limit} onChange={(e) => handleChange('lines_limit', parseInt(e.target.value))}
                     className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
                 </div>
               ) : (
                 <div className="space-y-2">
                   <div className="flex items-center gap-2 text-yellow-500 mb-1">
                     <AlertTriangle size={14} />
                     <span className="text-[10px] font-bold uppercase">{t('warn_token_mode_severe')}</span>
                   </div>
                   <input type="number" value={config.lines_limit * 100} onChange={(e) => handleChange('lines_limit', Math.floor(parseInt(e.target.value)/100))}
                     className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
                 </div>
               )}

               <div className="space-y-2 mt-4 pt-4 border-t border-slate-700">
                  <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_pre_lines') || 'Context Lines (Pre-lines)'}</label>
                  <p className="text-[10px] text-slate-500 mb-1">{t('desc_pre_lines') || 'Number of previous translated lines to include as context for AI.'}</p>
                  <input type="number" value={config.pre_line_counts ?? 3} onChange={(e) => handleChange('pre_line_counts', parseInt(e.target.value) || 0)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
               </div>
             </div>
          </div>
        )}

        {/* --- FEATURES TAB --- */}
        {activeTab === 'features' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
            <Toggle field="pre_translation_switch" label={t('feature_pre_translation_switch')} />
            <Toggle field="post_translation_switch" label={t('feature_post_translation_switch')} />
            <Toggle field="prompt_dictionary_switch" label={t('feature_prompt_dictionary_switch')} />
            <Toggle field="exclusion_list_switch" label={t('feature_exclusion_list_switch')} />
            <Toggle field="characterization_switch" label={t('feature_characterization_switch')} />
            <Toggle field="world_building_switch" label={t('feature_world_building_switch')} />
            <Toggle field="writing_style_switch" label={t('feature_writing_style_switch')} />
            <Toggle field="translation_example_switch" label={t('feature_translation_example_switch')} />
            <Toggle field="few_shot_and_example_switch" label={t('feature_few_shot_and_example_switch')} />
            <Toggle field="auto_process_text_code_segment" label={t('feature_auto_process_text_code_segment')} />

            {/* AI Proofread Settings */}
            <div className="col-span-2 border-t border-slate-700 pt-4 mt-2">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">{t('feature_proofread_section')}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Toggle field="enable_auto_proofread" label={t('feature_enable_auto_proofread')} />
              </div>
            </div>
          </div>
        )}

        {/* --- SYSTEM TAB --- */}
        {activeTab === 'system' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4">
             <Toggle field="show_detailed_logs" label={t('setting_detailed_logs')} />
             <Toggle field="enable_cache_backup" label={t('setting_cache_backup')} />
             <Toggle field="enable_auto_restore_ebook" label={t('setting_auto_restore_ebook')} />
             <Toggle field="enable_xlsx_conversion" label={t('setting_enable_xlsx_conversion')} />
             <Toggle field="enable_dry_run" label={t('setting_dry_run')} />
             <Toggle field="enable_retry" label={t('setting_enable_retry')} />
             <Toggle field="enable_smart_round_limit" label={t('setting_enable_smart_round_limit')} />
             <Toggle field="response_conversion_toggle" label={t('setting_response_conversion_toggle')} />

             <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-400 uppercase">{t('setting_temp_file_limit')}</label>
                <input type="number" value={config.temp_file_limit ?? 10} onChange={(e) => handleChange('temp_file_limit', parseInt(e.target.value) || 0)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
             </div>

             <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-400 uppercase">Cache Editor Page Size</label>
                <input type="number" value={config.cache_editor_page_size ?? 15} onChange={(e) => handleChange('cache_editor_page_size', parseInt(e.target.value) || 15)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-slate-200 focus:border-primary text-sm" />
             </div>

             <div className="col-span-1 md:col-span-2 p-4 bg-slate-900/50 border border-slate-700 rounded-lg space-y-4">
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                        <FileJson size={18} className="text-primary" />
                        <span className="text-sm font-semibold text-slate-200">{t('ui_task_temp_uploaded')} ({tempFiles.length})</span>
                    </div>
                    <div className="flex items-center gap-2">
                        {selectedTempFiles.length > 0 && (
                            <button 
                                onClick={handleDeleteTempFiles}
                                disabled={isDeletingFiles}
                                className="flex items-center gap-1 text-[10px] bg-red-500/10 text-red-400 border border-red-500/20 px-2 py-1 rounded hover:bg-red-500/20 transition-all"
                            >
                                <Trash2 size={12} /> {t('menu_profile_delete')} ({selectedTempFiles.length})
                            </button>
                        )}
                        <button 
                            onClick={() => setIsTempFilesExpanded(!isTempFilesExpanded)}
                            className={`p-1 text-slate-400 hover:text-white transition-transform ${isTempFilesExpanded ? 'rotate-180' : ''}`}
                        >
                            <ChevronDown size={18} />
                        </button>
                    </div>
                </div>

                {isTempFilesExpanded && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 animate-in fade-in slide-in-from-top-2 duration-200">
                        {tempFiles.length === 0 ? (
                            <p className="col-span-full text-center text-xs text-slate-500 py-4 italic">No files found</p>
                        ) : (
                            tempFiles.map(f => (
                                <label key={f.name} className="flex items-center gap-3 p-2 bg-slate-950/50 rounded border border-slate-800 hover:border-slate-700 cursor-pointer group">
                                    <input 
                                        type="checkbox" 
                                        checked={selectedTempFiles.includes(f.name)}
                                        onChange={() => handleToggleTempFile(f.name)}
                                        className="w-4 h-4 rounded border-slate-700 text-primary focus:ring-primary bg-slate-900"
                                    />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs text-slate-300 truncate" title={f.name}>{f.name}</p>
                                        <p className="text-[10px] text-slate-500">{(f.size/1024).toFixed(1)} KB</p>
                                    </div>
                                </label>
                            ))
                        )}
                    </div>
                )}
             </div>

             <div className="col-span-1 md:col-span-2 mt-4">
                 <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between border-b border-slate-700 pb-2 mb-3 gap-2">
                    <h4 className="text-slate-300 font-bold text-sm md:text-base">{t('menu_response_checks')}</h4>
                    <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-[10px] font-bold border transition-colors duration-500 ${
                        isOnline 
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.2)]' 
                            : 'bg-red-500/10 text-red-500 border-red-500/20 shadow-[0_0_10px_rgba(239,68,68,0.2)] animate-pulse'
                    }`}>
                        {isOnline ? <Wifi size={12} /> : <WifiOff size={12} />}
                        {isOnline ? t('ui_system_online') : "SYSTEM OFFLINE"}
                    </div>
                 </div>
                 
                 <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:gap-4">
                     {typeof config.response_check_switch === 'object' && config.response_check_switch !== null && Object.entries(config.response_check_switch).map(([key, val]) => (
                         <div key={key} className="flex items-center justify-between p-3 bg-slate-900/50 rounded border border-slate-800/50">
                             <div className="flex items-center gap-2">
                                <AlertTriangle size={14} className="text-yellow-500 cursor-help" onClick={handleWarningClick} />
                                <span className="text-xs text-slate-300">{t(`check_${key}`) || key}</span>
                             </div>
                             <button onClick={() => handleCheckChange(key, !(val as boolean))} className={`transition-all duration-300 ${val ? getThemeColorClass() + ' scale-110' : 'text-slate-600'}`}>
                                 {val ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                             </button>
                         </div>
                     ))}
                 </div>
             </div>
          </div>
        )}

        {/* --- PROFILES TAB --- */}
        {activeTab === 'profiles' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg md:text-xl font-semibold text-slate-200">{t('menu_profiles')}</h2>
                <div className="flex gap-2">
                    <button 
                      onClick={startCreate} 
                      disabled={isCreating}
                      className="flex items-center gap-2 px-3 py-2 bg-primary/10 border border-primary/20 text-primary rounded-lg hover:bg-primary/20 transition-colors disabled:opacity-50"
                    >
                        <Plus size={16} /> <span className="text-xs font-bold">{t('menu_profile_create')}</span>
                    </button>
                    <button 
                      onClick={loadProfiles} 
                      className="p-2 bg-slate-800 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                      title="Reload Profiles"
                    >
                        <RefreshCw size={18} className={loadingProfiles ? "animate-spin" : ""} />
                    </button>
                </div>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Create Profile Card */}
                {isCreating && (
                    <div className="p-5 rounded-xl border border-primary/50 bg-slate-900/80 shadow-lg shadow-primary/10 flex flex-col gap-3 animate-in fade-in zoom-in-95 duration-200">
                        <h3 className="text-sm font-bold text-slate-300">New Profile Name</h3>
                        <input 
                            autoFocus
                            type="text" 
                            className="bg-slate-950 border border-slate-700 rounded p-2 text-white text-sm focus:border-primary outline-none"
                            placeholder="Enter name..."
                            value={tempName}
                            onChange={(e) => setTempName(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && confirmCreate()}
                        />
                         {actionError && <p className="text-red-400 text-xs">{actionError}</p>}
                        <div className="flex justify-end gap-2 mt-2">
                            <button onClick={cancelCreate} className="p-1.5 rounded bg-slate-800 text-slate-400 hover:text-white"><X size={16}/></button>
                            <button onClick={confirmCreate} className="p-1.5 rounded bg-primary text-slate-900 hover:bg-cyan-400"><Check size={16}/></button>
                        </div>
                    </div>
                )}

                {profiles.map((profileName) => {
                    const isSelected = config?.active_profile === profileName;
                    const isRenaming = renamingId === profileName;
                    
                    return (
                        <div 
                            key={profileName} 
                            onClick={() => !isRenaming && handleSwitchProfile(profileName)}
                            className={`group relative p-4 md:p-5 rounded-xl border cursor-pointer transition-all duration-300 ${
                                isSelected
                                    ? 'bg-primary/10 border-primary ring-1 ring-primary shadow-[0_0_20px_rgba(6,182,212,0.3)] scale-[1.02]' 
                                    : 'bg-slate-900/50 border-slate-700 hover:border-slate-500 hover:bg-slate-800'
                            }`}
                        >
                            <div className="flex items-start justify-between">
                                <div className="flex items-center gap-3 w-full">
                                    <div className={`p-2 rounded-lg shrink-0 ${isSelected ? 'bg-primary/20 text-primary' : 'bg-slate-800 text-slate-400 group-hover:bg-slate-700 group-hover:text-slate-200'}`}>
                                        <FileJson size={20} md:size={24} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        {isRenaming ? (
                                            <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                                                <input 
                                                    autoFocus
                                                    className="w-full bg-slate-950 border border-slate-600 rounded px-1 py-0.5 text-white text-sm"
                                                    value={tempName}
                                                    onChange={(e) => setTempName(e.target.value)}
                                                    onKeyDown={(e) => e.key === 'Enter' && confirmRename(profileName)}
                                                />
                                                <button onClick={cancelRename} className="text-red-400 hover:text-red-300"><X size={14}/></button>
                                                <button onClick={() => confirmRename(profileName)} className="text-green-400 hover:text-green-300"><Check size={14}/></button>
                                            </div>
                                        ) : (
                                            <>
                                                <h3 className={`text-sm md:text-base font-semibold truncate ${isSelected ? 'text-primary' : 'text-slate-200 group-hover:text-white'}`}>{profileName}</h3>
                                                <p className="text-[10px] text-slate-500 uppercase tracking-tighter">JSON Config</p>
                                            </>
                                        )}
                                        {actionError && isRenaming && <p className="text-red-400 text-xs mt-1">{actionError}</p>}
                                    </div>
                                </div>
                                
                                <div className="flex flex-col items-end gap-2 ml-2">
                                    {/* Theme Selector for Unlocked Themes */}
                                    {isSelected && unlockedThemes.length > 1 && (
                                        <div className="relative group/theme" onClick={e => e.stopPropagation()}>
                                            <select 
                                                value={activeTheme}
                                                onChange={(e) => triggerRipple(window.innerWidth / 2, window.innerHeight / 2, e.target.value as any)}
                                                className={`text-[10px] font-bold py-1 pl-2 pr-6 rounded border appearance-none cursor-pointer transition-all ${
                                                    elysiaActive 
                                                        ? 'bg-pink-500/10 border-pink-500/30 text-pink-400 hover:bg-pink-500/20' 
                                                        : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                                                }`}
                                            >
                                                {unlockedThemes.map(tId => (
                                                    <option key={tId} value={tId}>{getCharacterName(tId)}</option>
                                                ))}
                                            </select>
                                            <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-slate-500" />
                                        </div>
                                    )}
                                    
                                    {profileName.toLowerCase() === 'elysia' && !unlockedThemes.includes('elysia') && (
                                        <button 
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                unlockThemeWithNotification('elysia');
                                            }}
                                            className="p-1.5 rounded-lg bg-slate-800 text-slate-500 hover:text-pink-400 transition-all"
                                            title="Magic Toggle"
                                        >
                                            <Sparkles size={16} />
                                        </button>
                                    )}
                                    {switchingProfile === profileName ? (
                                        <Loader2 size={18} className="text-primary animate-spin" />
                                    ) : isSelected && (
                                        <CheckCircle size={18} className="text-primary" />
                                    )}
                                </div>
                            </div>
                            
                            {/* Actions Toolbar */}
                            {!isRenaming && (
                                <div className="mt-4 flex justify-between items-end border-t border-white/5 pt-3">
                                    <div className="flex gap-2 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button 
                                            onClick={(e) => startRename(profileName, e)}
                                            className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-cyan-400 transition-colors" 
                                            title="Rename"
                                        >
                                            <Edit2 size={14} />
                                        </button>
                                        <button 
                                            onClick={(e) => handleDelete(profileName, e)}
                                            className="p-1.5 rounded hover:bg-slate-700 text-slate-400 hover:text-red-400 transition-colors"
                                            title="Delete"
                                            disabled={isSelected} // Cannot delete active
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                    <span className={`text-[10px] font-bold uppercase tracking-widest transition-colors ${isSelected ? 'text-primary' : 'text-slate-500 group-hover:text-primary'}`}>
                                        {switchingProfile === profileName ? 'Loading' : isSelected ? 'Active' : 'Load'}
                                    </span>
                                </div>
                            )}
                        </div>
                    );
                })}
                
                {profiles.length === 0 && !loadingProfiles && !isCreating && (
                    <div className="col-span-full py-12 text-center border-2 border-dashed border-slate-800 rounded-xl">
                        <p className="text-slate-500 text-sm">No profiles found in Resource/profiles/</p>
                    </div>
                )}
            </div>
            
            <div className="p-3 md:p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg flex gap-3">
                <AlertTriangle size={20} className="text-yellow-500 shrink-0 mt-0.5" />
                <div>
                    <h4 className="text-xs md:text-sm font-bold text-yellow-500 uppercase tracking-tight">Warning</h4>
                    <p className="text-[10px] md:text-xs text-slate-400 mt-1">Switching profiles will overwrite your current unsaved settings. Please save any critical changes first.</p>
                </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
